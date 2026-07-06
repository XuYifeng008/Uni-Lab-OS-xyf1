#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""同一进程内按串口端口共享 RS485 总线。"""

import logging
import os
import threading
from dataclasses import dataclass, field
from typing import Dict, Optional

import serial

logger = logging.getLogger(__name__)


def _port_key(port: str) -> str:
    """统一同一串口的缓存键，避免 COM3/com3 被当成不同端口。"""
    return os.path.normcase(port)


@dataclass
class RS485Bus:
    """一个物理 RS485 串口总线的进程内共享状态。"""

    port: str
    baudrate: int
    timeout: float
    serial_conn: Optional[serial.Serial] = None
    lock: threading.RLock = field(default_factory=threading.RLock)
    ref_count: int = 0

    def open(self, **serial_kwargs) -> serial.Serial:
        """打开或复用串口，并记录引用计数。"""
        with self.lock:
            if self.serial_conn and self.serial_conn.is_open:
                if self.serial_conn.baudrate != self.baudrate:
                    raise ValueError(
                        f"串口 {self.port} 已以 {self.serial_conn.baudrate} 波特率打开，"
                        f"不能再以 {self.baudrate} 打开"
                    )
            else:
                self.serial_conn = serial.Serial(
                    port=self.port,
                    baudrate=self.baudrate,
                    timeout=self.timeout,
                    **serial_kwargs,
                )
                logger.info("已打开共享 RS485 总线: %s", self.port)

            self.ref_count += 1
            return self.serial_conn

    def release(self) -> None:
        """释放一个使用者；最后一个使用者释放时关闭串口。"""
        with self.lock:
            if self.ref_count > 0:
                self.ref_count -= 1

            if self.ref_count == 0 and self.serial_conn and self.serial_conn.is_open:
                self.serial_conn.close()
                logger.info("已关闭共享 RS485 总线: %s", self.port)


_buses: Dict[str, RS485Bus] = {}
_registry_lock = threading.RLock()


def get_rs485_bus(port: str, baudrate: int, timeout: float) -> RS485Bus:
    """获取同一进程内某个串口端口的唯一 RS485 总线对象。"""
    key = _port_key(port)
    with _registry_lock:
        bus = _buses.get(key)
        if bus is None:
            bus = RS485Bus(port=port, baudrate=baudrate, timeout=timeout)
            _buses[key] = bus
        elif bus.baudrate != baudrate:
            raise ValueError(
                f"串口 {port} 已注册为 {bus.baudrate} 波特率，不能再以 {baudrate} 使用"
            )
        return bus
