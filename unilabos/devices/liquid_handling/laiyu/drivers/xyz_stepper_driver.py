#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
XYZ三轴步进电机B系列驱动程序
支持RS485通信，Modbus协议
"""

import serial
import struct
import time
import logging
import threading
from typing import Optional, Tuple, Dict, Any
from enum import Enum
from dataclasses import dataclass

from unilabos.devices.liquid_handling.laiyu.drivers.rs485_bus import RS485Bus, get_rs485_bus

# 配置日志
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class MotorAxis(Enum):
    """电机轴枚举"""
    X = 1
    Y = 2
    Z = 3


class MotorStatus(Enum):
    """电机状态枚举"""
    STANDBY = 0x0000  # 待机/到位
    RUNNING = 0x0001  # 运行中
    COLLISION_STOP = 0x0002  # 碰撞停
    FORWARD_LIMIT_STOP = 0x0003  # 正光电停
    REVERSE_LIMIT_STOP = 0x0004  # 反光电停


class ModbusFunction(Enum):
    """Modbus功能码"""
    READ_HOLDING_REGISTERS = 0x03
    WRITE_SINGLE_REGISTER = 0x06
    WRITE_MULTIPLE_REGISTERS = 0x10


@dataclass
class MotorPosition:
    """电机位置信息"""
    steps: int
    speed: int
    current: int
    status: MotorStatus


class ModbusException(Exception):
    """Modbus通信异常"""
    pass


class StepperMotorDriver:
    """步进电机驱动器基类"""
    
    # 寄存器地址常量
    REG_STATUS = 0x00
    REG_POSITION_HIGH = 0x01
    REG_POSITION_LOW = 0x02
    REG_ACTUAL_SPEED = 0x03
    REG_EMERGENCY_STOP = 0x04
    REG_CURRENT = 0x05
    REG_ENABLE = 0x06
    REG_PWM_OUTPUT = 0x07
    REG_ZERO_SINGLE = 0x0E
    REG_ZERO_COMMAND = 0x0F
    
    # 位置模式寄存器
    REG_TARGET_POSITION_HIGH = 0x10
    REG_TARGET_POSITION_LOW = 0x11
    REG_POSITION_SPEED = 0x13
    REG_POSITION_ACCELERATION = 0x14
    REG_POSITION_PRECISION = 0x15
    
    # 速度模式寄存器
    REG_SPEED_MODE_SPEED = 0x61
    REG_SPEED_MODE_ACCELERATION = 0x62
    
    # 设备参数寄存器
    REG_DEVICE_ADDRESS = 0xE0
    REG_DEFAULT_SPEED = 0xE7
    REG_DEFAULT_ACCELERATION = 0xE8
    
    def __init__(self, port: str, baudrate: int = 115200, timeout: float = 1.0, response_delay: float = 0.03):
        """
        初始化步进电机驱动器
        
        Args:
            port: 串口端口名
            baudrate: 波特率
            timeout: 通信超时时间
        """
        self.port = port
        self.baudrate = baudrate
        self.timeout = timeout
        self.response_delay = response_delay
        self.serial_conn: Optional[serial.Serial] = None
        self.lock = threading.RLock()
        self._serial_bus: Optional[RS485Bus] = None
        
    def connect(self) -> bool:
        """
        建立串口连接
        
        Returns:
            连接是否成功
        """
        try:
            self._serial_bus = get_rs485_bus(self.port, self.baudrate, self.timeout)
            self.serial_conn = self._serial_bus.open(
                bytesize=serial.EIGHTBITS,
                parity=serial.PARITY_NONE,
                stopbits=serial.STOPBITS_ONE,
                write_timeout=self.timeout,
                xonxoff=False,
                rtscts=False,
                dsrdtr=False,
            )
            self.lock = self._serial_bus.lock
            logger.info(f"已连接到串口: {self.port}")
            return True
        except Exception as e:
            logger.error(f"串口连接失败: {e}")
            return False
    
    def disconnect(self) -> None:
        """关闭串口连接"""
        if self._serial_bus:
            self._serial_bus.release()
            self._serial_bus = None
            self.serial_conn = None
            logger.info("串口连接已释放")
        elif self.serial_conn and self.serial_conn.is_open:
            self.serial_conn.close()
            logger.info("串口连接已关闭")
    
    def __enter__(self):
        """上下文管理器入口"""
        if self.connect():
            return self
        raise ModbusException("无法建立串口连接")
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        """上下文管理器出口"""
        self.disconnect()
    
    @staticmethod
    def calculate_crc(data: bytes) -> bytes:
        """
        计算Modbus CRC校验码
        
        Args:
            data: 待校验的数据
            
        Returns:
            CRC校验码 (2字节)
        """
        crc = 0xFFFF
        for byte in data:
            crc ^= byte
            for _ in range(8):
                if crc & 0x0001:
                    crc >>= 1
                    crc ^= 0xA001
                else:
                    crc >>= 1
        return struct.pack('<H', crc)
    
    def _send_command(self, slave_addr: int, data: bytes) -> bytes:
        """
        发送Modbus命令并接收响应
        
        Args:
            slave_addr: 从站地址
            data: 命令数据
            
        Returns:
            响应数据
            
        Raises:
            ModbusException: 通信异常
        """
        if not self.serial_conn or not self.serial_conn.is_open:
            raise ModbusException("串口未连接")
        
        with self.lock:
            # 构建完整命令
            command = bytes([slave_addr]) + data
            crc = self.calculate_crc(command)
            full_command = command + crc
            
            response = b""
            max_attempts = 5
            for attempt in range(1, max_attempts + 1):
                # 共享 RS485 总线时，SOPA 可能还有延迟响应；等待输入缓冲安静后再发 Modbus。
                self._drain_input_buffer(quiet_period=0.2, max_wait=1.5)
                self.serial_conn.reset_output_buffer()
                
                # 发送命令
                self.serial_conn.write(full_command)
                self.serial_conn.flush()
                logger.debug(f"发送命令: {' '.join(f'{b:02X}' for b in full_command)}")
                
                # 等待设备处理并按 Modbus RTU 响应长度读取完整帧。
                time.sleep(self.response_delay)
                response = self._read_modbus_response(slave_addr)
                if response:
                    break

                if attempt < max_attempts:
                    logger.warning(
                        "未收到有效 Modbus 响应，准备重试: addr=%s attempt=%s/%s",
                        slave_addr,
                        attempt + 1,
                        max_attempts,
                    )

            if not response:
                raise ModbusException(
                    f"未收到响应: addr={slave_addr}, cmd={' '.join(f'{b:02X}' for b in full_command)}"
                )
            
            logger.debug(f"接收响应: {' '.join(f'{b:02X}' for b in response)}")
            
            # 验证CRC
            if len(response) < 3:
                raise ModbusException("响应数据长度不足")
            
            data_part = response[:-2]
            received_crc = response[-2:]
            calculated_crc = self.calculate_crc(data_part)
            
            if received_crc != calculated_crc:
                raise ModbusException(
                    "CRC校验失败: "
                    f"response={' '.join(f'{b:02X}' for b in response)}, "
                    f"expected={' '.join(f'{b:02X}' for b in calculated_crc)}, "
                    f"actual={' '.join(f'{b:02X}' for b in received_crc)}"
                )
            
            if response[1] & 0x80:
                error_code = response[2] if len(response) > 2 else None
                raise ModbusException(f"设备返回异常响应: function=0x{response[1]:02X}, error={error_code}")
            
            return response

    def _drain_input_buffer(self, quiet_period: float = 0.2, max_wait: float = 1.5) -> bytes:
        """清空输入缓冲，并等待短暂静默，避免 SOPA 残留响应混入 Modbus 帧。"""
        assert self.serial_conn is not None

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
            logger.debug("清理串口残留数据: %s", " ".join(f"{b:02X}" for b in drained))

        return drained

    @staticmethod
    def _calculate_sopa_checksum(data: bytes) -> int:
        """SOPA 响应校验为所有字节低 8 位累加和。"""
        return sum(data) & 0xFF

    def _find_complete_sopa_frame(self, data: bytes) -> Optional[Tuple[int, int]]:
        """在混合串口数据中定位一帧完整 SOPA 响应，返回 [start, end)。"""
        for start, byte in enumerate(data):
            if byte not in (ord("/"), ord("[")):
                continue

            # SOPA 帧以 E 结尾，E 后还有 1 字节 checksum。
            for tail in range(start + 2, len(data) - 1):
                if data[tail] != ord("E"):
                    continue
                end = tail + 2
                frame = data[start:end]
                if self._calculate_sopa_checksum(frame[:-1]) == frame[-1]:
                    return start, end

        return None

    def _discard_sopa_noise(self, data: bytes) -> bytes:
        """丢弃已完整到达的 SOPA 帧，以及帧前被污染的残留字节。"""
        buffer = data
        discarded = b""

        while True:
            frame_range = self._find_complete_sopa_frame(buffer)
            if frame_range is None:
                break

            start, end = frame_range
            discarded += buffer[:end]
            buffer = buffer[end:]

        if discarded:
            logger.debug(
                "丢弃混入 Modbus 读取的 SOPA/噪声数据: %s",
                " ".join(f"{b:02X}" for b in discarded),
            )

        return buffer

    def _read_modbus_response(self, expected_slave_addr: int) -> bytes:
        """读取一帧 Modbus RTU 响应。"""
        assert self.serial_conn is not None

        response_buffer = b""
        deadline = time.time() + self.timeout

        while time.time() < deadline:
            waiting = self.serial_conn.in_waiting
            if waiting:
                response_buffer += self.serial_conn.read(waiting)
                frame = self._extract_modbus_frame(response_buffer, expected_slave_addr)
                if frame is not None:
                    return frame

                cleaned_buffer = self._discard_sopa_noise(response_buffer)
                if len(cleaned_buffer) != len(response_buffer):
                    response_buffer = cleaned_buffer
                    continue

                if bytes([expected_slave_addr]) not in response_buffer and len(response_buffer) > 0:
                    logger.debug(
                        "丢弃不含目标 Modbus 地址的缓冲数据: %s",
                        " ".join(f"{b:02X}" for b in response_buffer),
                    )
                    response_buffer = b""
            else:
                time.sleep(0.01)

        if response_buffer:
            logger.debug(
                "未解析到完整 Modbus 帧，缓冲区数据: %s",
                " ".join(f"{b:02X}" for b in response_buffer),
            )

        return b""

    def _extract_modbus_frame(self, data: bytes, expected_slave_addr: int) -> Optional[bytes]:
        """从混合串口数据中提取目标从站的一帧合法 Modbus RTU 响应。"""
        search_start = 0

        while search_start < len(data):
            start = data.find(bytes([expected_slave_addr]), search_start)
            if start < 0:
                if data:
                    logger.debug("丢弃非 Modbus 数据: %s", " ".join(f"{b:02X}" for b in data))
                return None

            candidate = data[start:]
            expected_len = self._expected_response_length(candidate)
            if expected_len is None:
                search_start = start + 1
                continue

            if len(candidate) < expected_len:
                return None

            frame = candidate[:expected_len]
            received_crc = frame[-2:]
            calculated_crc = self.calculate_crc(frame[:-2])
            if received_crc == calculated_crc:
                if start > 0:
                    logger.debug(
                        "跳过 Modbus 帧前噪声: %s",
                        " ".join(f"{b:02X}" for b in data[:start]),
                    )
                return frame

            logger.debug(
                "丢弃 CRC 不匹配的候选帧: %s",
                " ".join(f"{b:02X}" for b in frame),
            )
            search_start = start + 1

        return None

    @staticmethod
    def _expected_response_length(response: bytes) -> Optional[int]:
        """根据功能码推断响应帧长度。"""
        if len(response) < 2:
            return None

        function_code = response[1]
        if function_code & 0x80:
            return 5 if len(response) >= 3 else None

        if function_code == ModbusFunction.READ_HOLDING_REGISTERS.value:
            if len(response) < 3:
                return None
            return 3 + response[2] + 2

        if function_code in (
            ModbusFunction.WRITE_SINGLE_REGISTER.value,
            ModbusFunction.WRITE_MULTIPLE_REGISTERS.value,
        ):
            return 8

        return None
    
    def read_registers(self, slave_addr: int, start_addr: int, count: int) -> list:
        """
        读取保持寄存器
        
        Args:
            slave_addr: 从站地址
            start_addr: 起始地址
            count: 寄存器数量
            
        Returns:
            寄存器值列表
        """
        data = struct.pack('>BHH', ModbusFunction.READ_HOLDING_REGISTERS.value, start_addr, count)
        response = self._send_command(slave_addr, data)
        
        if len(response) < 5:
            raise ModbusException("响应长度不足")
        
        if response[1] != ModbusFunction.READ_HOLDING_REGISTERS.value:
            raise ModbusException(f"功能码错误: {response[1]:02X}")
        
        byte_count = response[2]
        values = []
        for i in range(0, byte_count, 2):
            value = struct.unpack('>H', response[3+i:5+i])[0]
            values.append(value)
        
        return values
    
    def write_single_register(self, slave_addr: int, addr: int, value: int) -> bool:
        """
        写入单个寄存器
        
        Args:
            slave_addr: 从站地址
            addr: 寄存器地址
            value: 寄存器值
            
        Returns:
            写入是否成功
        """
        data = struct.pack('>BHH', ModbusFunction.WRITE_SINGLE_REGISTER.value, addr, value)
        response = self._send_command(slave_addr, data)
        
        return len(response) >= 8 and response[1] == ModbusFunction.WRITE_SINGLE_REGISTER.value
    
    def write_multiple_registers(self, slave_addr: int, start_addr: int, values: list) -> bool:
        """
        写入多个寄存器
        
        Args:
            slave_addr: 从站地址
            start_addr: 起始地址
            values: 寄存器值列表
            
        Returns:
            写入是否成功
        """
        byte_count = len(values) * 2
        data = struct.pack('>BHHB', ModbusFunction.WRITE_MULTIPLE_REGISTERS.value, 
                          start_addr, len(values), byte_count)
        
        for value in values:
            data += struct.pack('>H', value)
        
        response = self._send_command(slave_addr, data)
        
        return len(response) >= 8 and response[1] == ModbusFunction.WRITE_MULTIPLE_REGISTERS.value


class XYZStepperController(StepperMotorDriver):
    """XYZ三轴步进电机控制器"""
    
    # 电机配置常量
    STEPS_PER_REVOLUTION = 16384  # 每圈步数
    
    def __init__(
        self,
        port: str,
        baudrate: int = 115200,
        timeout: float = 1.0,
        axis_addresses: Optional[Dict[MotorAxis, int]] = None,
        response_delay: float = 0.03,
    ):
        """
        初始化XYZ三轴步进电机控制器
        
        Args:
            port: 串口端口名
            baudrate: 波特率
            timeout: 通信超时时间
        """
        super().__init__(port, baudrate, timeout, response_delay=response_delay)
        self.axis_addresses = axis_addresses or {
            MotorAxis.X: 1,
            MotorAxis.Y: 2,
            MotorAxis.Z: 3
        }

    def probe_address(self, address: int) -> Optional[MotorPosition]:
        """探测指定 Modbus 地址是否有步进电机响应。"""
        try:
            values = self.read_registers(address, self.REG_STATUS, 6)
            status = MotorStatus(values[0])
            position_high = values[1]
            position_low = values[2]
            speed = values[3]
            current = values[5]
            position = (position_high << 16) | position_low
            if position > 0x7FFFFFFF:
                position -= 0x100000000
            return MotorPosition(position, speed, current, status)
        except Exception as e:
            logger.debug(f"地址 {address} 探测无响应或解析失败: {e}")
            return None

    def scan_addresses(self, start: int = 1, end: int = 4) -> Dict[int, MotorPosition]:
        """
        扫描 Modbus 地址。

        默认扫描 1-4，覆盖文档中的 X/Y/Z(1-3) 和 SOPA 推荐地址 4。
        """
        found: Dict[int, MotorPosition] = {}
        for address in range(start, end + 1):
            position = self.probe_address(address)
            if position is not None:
                found[address] = position
        return found

    def test_connection(self) -> Dict[MotorAxis, bool]:
        """测试文档默认的 X/Y/Z 地址是否可响应。"""
        return {axis: self.probe_address(address) is not None for axis, address in self.axis_addresses.items()}
    
    def degrees_to_steps(self, degrees: float) -> int:
        """
        将角度转换为步数
        
        Args:
            degrees: 角度值
            
        Returns:
            对应的步数
        """
        return int(degrees * self.STEPS_PER_REVOLUTION / 360.0)
    
    def steps_to_degrees(self, steps: int) -> float:
        """
        将步数转换为角度
        
        Args:
            steps: 步数
            
        Returns:
            对应的角度值
        """
        return steps * 360.0 / self.STEPS_PER_REVOLUTION
    
    def revolutions_to_steps(self, revolutions: float) -> int:
        """
        将圈数转换为步数
        
        Args:
            revolutions: 圈数
            
        Returns:
            对应的步数
        """
        return int(revolutions * self.STEPS_PER_REVOLUTION)
    
    def steps_to_revolutions(self, steps: int) -> float:
        """
        将步数转换为圈数
        
        Args:
            steps: 步数
            
        Returns:
            对应的圈数
        """
        return steps / self.STEPS_PER_REVOLUTION
    
    def get_motor_status(self, axis: MotorAxis) -> MotorPosition:
        """
        获取电机状态信息
        
        Args:
            axis: 电机轴
            
        Returns:
            电机位置信息
        """
        addr = self.axis_addresses[axis]
        
        # 读取状态、位置、速度、电流
        values = self.read_registers(addr, self.REG_STATUS, 6)
        
        try:
            status = MotorStatus(values[0])
        except ValueError as exc:
            raise ModbusException(f"{axis.name}轴返回未知状态码: 0x{values[0]:04X}") from exc
        position_high = values[1]
        position_low = values[2]
        speed = values[3]
        current = values[5]
        
        # 合并32位位置
        position = (position_high << 16) | position_low
        # 处理有符号数
        if position > 0x7FFFFFFF:
            position -= 0x100000000
        
        return MotorPosition(position, speed, current, status)
    
    def emergency_stop(self, axis: MotorAxis) -> bool:
        """
        紧急停止电机
        
        Args:
            axis: 电机轴
            
        Returns:
            操作是否成功
        """
        addr = self.axis_addresses[axis]
        return self.write_single_register(addr, self.REG_EMERGENCY_STOP, 0x0000)
    
    def enable_motor(self, axis: MotorAxis, enable: bool = True) -> bool:
        """
        使能/失能电机
        
        Args:
            axis: 电机轴
            enable: True为使能，False为失能
            
        Returns:
            操作是否成功
        """
        addr = self.axis_addresses[axis]
        value = 0x0001 if enable else 0x0000
        return self.write_single_register(addr, self.REG_ENABLE, value)
    
    def move_to_position(self, axis: MotorAxis, position: int, speed: int = 5000, 
                        acceleration: int = 1000, precision: int = 100) -> bool:
        """
        移动到指定位置
        
        Args:
            axis: 电机轴
            position: 目标位置(步数)
            speed: 运行速度(rpm)
            acceleration: 加速度(rpm/s)
            precision: 到位精度
            
        Returns:
            操作是否成功
        """
        addr = self.axis_addresses[axis]
        
        # 处理32位位置
        if position < 0:
            position += 0x100000000
        
        position_high = (position >> 16) & 0xFFFF
        position_low = position & 0xFFFF
        
        values = [
            position_high,     # 目标位置高位
            position_low,      # 目标位置低位
            0x0000,           # 保留
            speed,            # 速度
            acceleration,     # 加速度
            precision         # 精度
        ]
        
        return self.write_multiple_registers(addr, self.REG_TARGET_POSITION_HIGH, values)
    
    def set_speed_mode(self, axis: MotorAxis, speed: int, acceleration: int = 1000) -> bool:
        """
        设置速度模式运行
        
        Args:
            axis: 电机轴
            speed: 运行速度(rpm)，正值正转，负值反转
            acceleration: 加速度(rpm/s)
            
        Returns:
            操作是否成功
        """
        addr = self.axis_addresses[axis]
        
        # 处理负数
        if speed < 0:
            speed = 0x10000 + speed  # 补码表示
        
        values = [0x0000, speed, acceleration, 0x0000]
        
        return self.write_multiple_registers(addr, 0x60, values)
    
    def home_axis(self, axis: MotorAxis) -> bool:
        """
        轴归零操作
        
        Args:
            axis: 电机轴
            
        Returns:
            操作是否成功
        """
        addr = self.axis_addresses[axis]
        return self.write_single_register(addr, self.REG_ZERO_SINGLE, 0x0001)
    
    def wait_for_completion(self, axis: MotorAxis, timeout: float = 30.0) -> bool:
        """
        等待电机运动完成
        
        Args:
            axis: 电机轴
            timeout: 超时时间(秒)
            
        Returns:
            是否在超时前完成
        """
        start_time = time.time()
        
        while time.time() - start_time < timeout:
            status = self.get_motor_status(axis)
            if status.status == MotorStatus.STANDBY:
                return True
            time.sleep(0.1)
        
        logger.warning(f"{axis.name}轴运动超时")
        return False
    
    def move_xyz(self, x: Optional[int] = None, y: Optional[int] = None, z: Optional[int] = None,
                speed: int = 5000, acceleration: int = 1000) -> Dict[MotorAxis, bool]:
        """
        同时控制XYZ轴移动
        
        Args:
            x: X轴目标位置
            y: Y轴目标位置
            z: Z轴目标位置
            speed: 运行速度
            acceleration: 加速度
            
        Returns:
            各轴操作结果字典
        """
        results = {}
        
        if x is not None:
            results[MotorAxis.X] = self.move_to_position(MotorAxis.X, x, speed, acceleration)
        
        if y is not None:
            results[MotorAxis.Y] = self.move_to_position(MotorAxis.Y, y, speed, acceleration)
        
        if z is not None:
            results[MotorAxis.Z] = self.move_to_position(MotorAxis.Z, z, speed, acceleration)
        
        return results
    
    def move_xyz_degrees(self, x_deg: Optional[float] = None, y_deg: Optional[float] = None, 
                        z_deg: Optional[float] = None, speed: int = 5000, 
                        acceleration: int = 1000) -> Dict[MotorAxis, bool]:
        """
        使用角度值同时移动多个轴到指定位置
        
        Args:
            x_deg: X轴目标角度（度）
            y_deg: Y轴目标角度（度）
            z_deg: Z轴目标角度（度）
            speed: 移动速度
            acceleration: 加速度
            
        Returns:
            各轴移动操作结果
        """
        # 将角度转换为步数
        x_steps = self.degrees_to_steps(x_deg) if x_deg is not None else None
        y_steps = self.degrees_to_steps(y_deg) if y_deg is not None else None
        z_steps = self.degrees_to_steps(z_deg) if z_deg is not None else None
        
        return self.move_xyz(x_steps, y_steps, z_steps, speed, acceleration)
    
    def move_xyz_revolutions(self, x_rev: Optional[float] = None, y_rev: Optional[float] = None, 
                           z_rev: Optional[float] = None, speed: int = 5000, 
                           acceleration: int = 1000) -> Dict[MotorAxis, bool]:
        """
        使用圈数值同时移动多个轴到指定位置
        
        Args:
            x_rev: X轴目标圈数
            y_rev: Y轴目标圈数
            z_rev: Z轴目标圈数
            speed: 移动速度
            acceleration: 加速度
            
        Returns:
            各轴移动操作结果
        """
        # 将圈数转换为步数
        x_steps = self.revolutions_to_steps(x_rev) if x_rev is not None else None
        y_steps = self.revolutions_to_steps(y_rev) if y_rev is not None else None
        z_steps = self.revolutions_to_steps(z_rev) if z_rev is not None else None
        
        return self.move_xyz(x_steps, y_steps, z_steps, speed, acceleration)
    
    def move_to_position_degrees(self, axis: MotorAxis, degrees: float, speed: int = 5000, 
                               acceleration: int = 1000, precision: int = 100) -> bool:
        """
        使用角度值移动单个轴到指定位置
        
        Args:
            axis: 电机轴
            degrees: 目标角度（度）
            speed: 移动速度
            acceleration: 加速度
            precision: 精度
            
        Returns:
            移动操作是否成功
        """
        steps = self.degrees_to_steps(degrees)
        return self.move_to_position(axis, steps, speed, acceleration, precision)
    
    def move_to_position_revolutions(self, axis: MotorAxis, revolutions: float, speed: int = 5000, 
                                   acceleration: int = 1000, precision: int = 100) -> bool:
        """
        使用圈数值移动单个轴到指定位置
        
        Args:
            axis: 电机轴
            revolutions: 目标圈数
            speed: 移动速度
            acceleration: 加速度
            precision: 精度
            
        Returns:
            移动操作是否成功
        """
        steps = self.revolutions_to_steps(revolutions)
        return self.move_to_position(axis, steps, speed, acceleration, precision)
    
    def stop_all_axes(self) -> Dict[MotorAxis, bool]:
        """
        紧急停止所有轴
        
        Returns:
            各轴停止结果字典
        """
        results = {}
        for axis in MotorAxis:
            results[axis] = self.emergency_stop(axis)
        return results
    
    def enable_all_axes(self, enable: bool = True) -> Dict[MotorAxis, bool]:
        """
        使能/失能所有轴
        
        Args:
            enable: True为使能，False为失能
            
        Returns:
            各轴操作结果字典
        """
        results = {}
        for axis in MotorAxis:
            results[axis] = self.enable_motor(axis, enable)
        return results
    
    def get_all_positions(self) -> Dict[MotorAxis, MotorPosition]:
        """
        获取所有轴的位置信息
        
        Returns:
            各轴位置信息字典
        """
        positions = {}
        for axis in MotorAxis:
            positions[axis] = self.get_motor_status(axis)
        return positions
    
    def home_all_axes(self) -> Dict[MotorAxis, bool]:
        """
        所有轴归零
        
        Returns:
            各轴归零结果字典
        """
        results = {}
        for axis in MotorAxis:
            results[axis] = self.home_axis(axis)
        return results
