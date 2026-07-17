#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""同一进程内按串口端口共享 RS485 总线。"""

import logging
import os
import threading
import time
from contextlib import contextmanager
from dataclasses import dataclass, field
from typing import Dict, Iterator, Optional

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

    def drain_until_quiet(
        self,
        quiet_period: float = 0.2,
        max_wait: float = 1.0,
        log_prefix: str = "清理 RS485 残留数据",
    ) -> bytes:
        """读取输入缓冲直到总线保持短暂安静。调用方应持有总线锁。"""
        if not self.serial_conn or not self.serial_conn.is_open:
            return b""

        drained = b""
        deadline = time.time() + max_wait
        quiet_deadline = time.time() + quiet_period

        while time.time() < deadline:
            waiting = self.serial_conn.in_waiting
            if waiting:
                drained += self.serial_conn.read(waiting)
                quiet_deadline = time.time() + quiet_period
                continue

            if time.time() >= quiet_deadline:
                break

            time.sleep(0.01)

        if drained:
            logger.debug("%s: %s", log_prefix, " ".join(f"{b:02X}" for b in drained))

        return drained

    @contextmanager
    def transaction(
        self,
        pre_drain: bool = True,
        post_drain: bool = True,
        pre_quiet: float = 0.2,
        pre_max_wait: float = 1.0,
        post_quiet: float = 0.2,
        post_max_wait: float = 1.0,
        log_prefix: str = "RS485事务",
    ) -> Iterator[None]:
        """一次 RS485 发-等-收事务，期间独占总线并清理事务边界残留。"""
        with self.lock:
            if pre_drain:
                self.drain_until_quiet(
                    quiet_period=pre_quiet,
                    max_wait=pre_max_wait,
                    log_prefix=f"{log_prefix}开始前清理残留数据",
                )
            try:
                yield
            finally:
                if post_drain:
                    self.drain_until_quiet(
                        quiet_period=post_quiet,
                        max_wait=post_max_wait,
                        log_prefix=f"{log_prefix}结束后清理残留数据",
                    )


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
