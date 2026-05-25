#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
GreenLab 电反应仪驱动 for Uni-Lab OS

支持通过Modbus RTU协议控制GreenLab电反应仪，包括：
- 6通道恒流/恒压输出控制
- 搅拌电机控制
- 实时电压/电流监测
- 故障状态监测与复位
"""

import time
import logging
from enum import Enum
from typing import Optional, Dict, Any, List, Tuple

try:
    from pymodbus.client import ModbusSerialClient
except ImportError:
    ModbusSerialClient = None  # type: ignore[misc, assignment]

try:
    import serial  # noqa: F401  # pyserial，Modbus RTU 依赖
except ImportError:
    serial = None  # type: ignore[misc, assignment]

try:
    from unilabos.device_comms.universal_driver import UniversalDriver
except ImportError:
    # Fallback for standalone testing
    class UniversalDriver:
        """Fallback UniversalDriver for standalone testing"""
        def __init__(self):
            self.success = False


class OutputMode(Enum):
    """输出模式枚举"""
    CONSTANT_VOLTAGE = 0  # 恒压模式
    CONSTANT_CURRENT = 1  # 恒流模式


class AlternateMode(Enum):
    """交替模式枚举"""
    NO_ALTERNATE = 0      # 无交替
    LOW_FREQ_ALTERNATE = 1  # 低频交替
    HIGH_FREQ_ALTERNATE = 2  # 高频交替


class StirrerControl(Enum):
    """搅拌电机控制枚举"""
    OFF = 0           # 关闭
    FORWARD = 1       # 正转
    REVERSE = 2       # 反转


class FaultStatus(Enum):
    """故障状态枚举"""
    NO_FAULT = 0                    # 无故障
    HIGH_RESISTANCE = 1             # 内阻大，电流为0
    CURRENT_OVER_LIMIT = 2          # 电流超限制
    COUNTDOWN_NOT_SET = 3           # 请设置倒计时时间
    VOLTAGE_OVER_OR_RESISTANCE = 4  # 电压超限或电阻过大


class RTUModbusSerialClient(ModbusSerialClient):
    """带 RS485 RTS 方向控制的 Modbus RTU 客户端

    GreenLab 官方 Modbus Poll 配置启用了 RTSToggle，半双工 RS485 需要切换收发方向。
    """

    def __init__(self, *args, rts_toggle: bool = True, **kwargs):
        super().__init__(*args, **kwargs)
        self.rts_toggle = rts_toggle

    def _set_transmit_mode(self, transmit: bool) -> None:
        if not self.rts_toggle or not self.socket:
            return
        # 与 Modbus Poll 配置一致: DTR=1, RTSToggle=1
        level = transmit
        self.socket.rts = level
        self.socket.dtr = level
        time.sleep(0.002)

    def send(self, request: bytes, addr: tuple | None = None) -> int:
        self._set_transmit_mode(True)
        return super().send(request, addr)

    def recv(self, size: int | None = None) -> bytes:
        self._set_transmit_mode(False)
        return super().recv(size)


class GreenLabElectrochemical(UniversalDriver):
    """GreenLab 电反应仪驱动

    支持6通道电化学反应控制，包括恒流/恒压输出、搅拌控制等功能
    """

    # Modbus寄存器地址映射
    REG_OUTPUT_MODE = 0              # 输出模式 (0:恒压, 1:恒流)
    REG_ALTERNATE_MODE = 1           # 交替模式
    REG_LOW_FREQ_TIME = 2            # 低频交替时间(S)
    REG_HIGH_FREQ_TIME = 3           # 高频交替时间(ms)

    # 通道开关控制 (地址5-10)
    REG_CHANNEL_SWITCH_BASE = 5      # 通道1-6开关控制基地址

    # 电压设置 (地址11-16)
    REG_VOLTAGE_SET_BASE = 11        # 通道1-6电压设置基地址

    # 电流设置 (地址17-22)
    REG_CURRENT_SET_BASE = 17        # 通道1-6电流设置基地址

    # 搅拌控制
    REG_STIRRER_CONTROL = 24         # 搅拌电机控制开关
    REG_STIRRER_SPEED = 25           # 搅拌电机转速

    # 设备配置
    REG_DEVICE_ADDRESS = 26          # 设备地址
    REG_DEVICE_BAUDRATE = 27         # 设备波特率

    # 故障状态 (地址50-55)
    REG_FAULT_STATUS_BASE = 50       # 通道1-6故障状态基地址

    # 当前电压读取 (地址56-61)
    REG_VOLTAGE_READ_BASE = 56       # 通道1-6当前电压基地址

    # 当前电流读取 (地址62-67)
    REG_CURRENT_READ_BASE = 62       # 通道1-6当前电流基地址

    # 当前转速读取
    REG_SPEED_READ = 68              # 当前转速

    def __init__(self,
                 port: str = 'COM8',
                 baudrate: int = 115200,
                 slave_id: int = 1,
                 timeout: int = 3,
                 rts_toggle: bool = True,
                 inter_frame_delay: float = 0.05):
        """初始化GreenLab电反应仪驱动

        Args:
            port: 串口端口 (Modbus RTU)，例如 'COM3' 或 '/dev/ttyUSB0'
            baudrate: 串口波特率，默认115200 (可选: 2400/4800/9600/19200/57600/115200)
            slave_id: Modbus从站地址，默认1
            timeout: 通信超时时间(秒)，默认3
            rts_toggle: RS485 半双工方向控制，默认True（与官方 Modbus Poll 配置一致）
            inter_frame_delay: 帧间延迟(秒)，默认0.05
        """
        super().__init__()

        if ModbusSerialClient is None:
            raise ImportError("未安装 pymodbus，请执行: pip install pymodbus")

        if serial is None:
            raise ImportError("未安装 pyserial，请执行: pip install pyserial")

        if not port:
            raise ValueError("必须指定 port 串口参数")

        self.slave_id = slave_id
        self.timeout = timeout
        self.rts_toggle = rts_toggle
        self.inter_frame_delay = inter_frame_delay
        self.client = None

        # 状态属性
        self._status = "Disconnected"
        self._is_connected = False
        self._channel_states = {i: False for i in range(1, 7)}  # 6个通道状态
        self._stirrer_running = False

        # ROS2 action result properties
        self.success = False
        self.return_info = ""

        # Setup logging
        self.logger = logging.getLogger(f"GreenLab-{port}")

        # 初始化Modbus RTU客户端
        try:
            self.client = RTUModbusSerialClient(
                port=port,
                baudrate=baudrate,
                parity='N',
                stopbits=1,
                bytesize=8,
                timeout=timeout,
                rts_toggle=rts_toggle,
            )
        except RuntimeError as e:
            raise ImportError(
                "Modbus RTU 需要 pyserial，请执行: pip install pyserial"
            ) from e
        self.logger.info(
            f"初始化Modbus RTU客户端: {port}, 波特率: {baudrate}, "
            f"从站: {slave_id}, RTS: {rts_toggle}"
        )

        # 连接设备
        self._connect()

    def _connect(self):
        """连接到设备并验证 Modbus 通信"""
        try:
            self._status = "Connecting"
            if not self.client.connect():
                self._is_connected = False
                self._status = "Connection Failed"
                self.logger.error("串口打开失败")
                return

            # 串口打开成功，进一步验证 Modbus 是否响应
            probe = self._read_register(self.REG_OUTPUT_MODE)
            if probe is not None:
                self._is_connected = True
                self._status = "Connected"
                self.logger.info(f"设备连接成功，输出模式寄存器值: {probe[0]}")
            else:
                self._is_connected = False
                self._status = "Modbus No Response"
                self.logger.error(
                    "串口已打开但 Modbus 无响应。请检查: "
                    "1) 波特率(默认115200); "
                    "2) 从站地址(默认1); "
                    "3) RS485 A/B 接线; "
                    "4) rts_toggle 参数(自动方向转换器可设 False)"
                )
        except Exception as e:
            self._is_connected = False
            self._status = f"Error: {str(e)}"
            self.logger.error(f"连接异常: {e}")

    def _modbus_delay(self) -> None:
        """帧间延迟，避免连续请求过快"""
        if self.inter_frame_delay > 0:
            time.sleep(self.inter_frame_delay)

    def disconnect(self):
        """断开设备连接"""
        client = getattr(self, "client", None)
        if client:
            client.close()
            self._is_connected = False
            self._status = "Disconnected"
            logger = getattr(self, "logger", None)
            if logger:
                logger.info("设备已断开")

    @property
    def status(self) -> str:
        """获取设备状态"""
        return self._status

    @property
    def is_connected(self) -> bool:
        """设备是否已连接"""
        return self._is_connected

    # ==================== 基础读写方法 ====================

    def _read_register(self, address: int, count: int = 1) -> Optional[List[int]]:
        """读取保持寄存器

        Args:
            address: 寄存器地址
            count: 读取数量

        Returns:
            寄存器值列表，失败返回None
        """
        try:
            self._modbus_delay()
            response = self.client.read_holding_registers(
                address, count=count, device_id=self.slave_id
            )
            if response.isError():
                self.logger.error(f"读取寄存器失败: 地址{address}, 错误: {response}")
                return None
            return response.registers
        except Exception as e:
            self.logger.error(f"读取寄存器异常: {e}")
            return None

    def _write_register(self, address: int, value: int) -> bool:
        """写入单个保持寄存器

        Args:
            address: 寄存器地址
            value: 写入值

        Returns:
            成功返回True，失败返回False
        """
        try:
            self._modbus_delay()
            response = self.client.write_register(
                address, value, device_id=self.slave_id
            )
            if response.isError():
                self.logger.error(f"写入寄存器失败: 地址{address}, 值{value}")
                return False
            return True
        except Exception as e:
            self.logger.error(f"写入寄存器异常: {e}")
            return False

    # ==================== 输出模式控制 ====================

    def set_output_mode(self, mode: OutputMode) -> bool:
        """设置输出模式

        Args:
            mode: 输出模式 (CONSTANT_VOLTAGE=恒压, CONSTANT_CURRENT=恒流)

        Returns:
            成功返回True
        """
        success = self._write_register(self.REG_OUTPUT_MODE, mode.value)
        if success:
            self.logger.info(f"设置输出模式: {mode.name}")
        return success

    def get_output_mode(self) -> Optional[OutputMode]:
        """获取当前输出模式"""
        result = self._read_register(self.REG_OUTPUT_MODE)
        if result:
            return OutputMode(result[0])
        return None

    def set_alternate_mode(self, mode: AlternateMode,
                          low_freq_time: int = 0,
                          high_freq_time: int = 0) -> bool:
        """设置交替模式

        Args:
            mode: 交替模式
            low_freq_time: 低频交替时间(秒)，范围1-6000
            high_freq_time: 高频交替时间(毫秒)，范围5-1000

        Returns:
            成功返回True
        """
        success = self._write_register(self.REG_ALTERNATE_MODE, mode.value)

        if success and mode == AlternateMode.LOW_FREQ_ALTERNATE:
            if not (1 <= low_freq_time <= 6000):
                self.logger.warning(f"低频交替时间超出范围: {low_freq_time}")
                return False
            success = self._write_register(self.REG_LOW_FREQ_TIME, low_freq_time)

        if success and mode == AlternateMode.HIGH_FREQ_ALTERNATE:
            if not (5 <= high_freq_time <= 1000):
                self.logger.warning(f"高频交替时间超出范围: {high_freq_time}")
                return False
            success = self._write_register(self.REG_HIGH_FREQ_TIME, high_freq_time)

        if success:
            self.logger.info(f"设置交替模式: {mode.name}")
        return success

    # ==================== 通道控制 ====================

    def set_channel_switch(self, channel: int, enable: bool) -> bool:
        """设置通道开关

        Args:
            channel: 通道号 (1-6)
            enable: True=打开, False=关闭

        Returns:
            成功返回True
        """
        if not (1 <= channel <= 6):
            self.logger.error(f"通道号超出范围: {channel}")
            return False

        address = self.REG_CHANNEL_SWITCH_BASE + (channel - 1)
        success = self._write_register(address, 1 if enable else 0)

        if success:
            self._channel_states[channel] = enable
            self.logger.info(f"通道{channel} {'打开' if enable else '关闭'}")

        return success

    def set_channel_voltage(self, channel: int, voltage: float) -> bool:
        """设置通道电压(恒压模式)

        Args:
            channel: 通道号 (1-6)
            voltage: 电压值(V)，范围0-30.00V，精度0.01V

        Returns:
            成功返回True
        """
        if not (1 <= channel <= 6):
            self.logger.error(f"通道号超出范围: {channel}")
            return False

        if not (0 <= voltage <= 30.0):
            self.logger.error(f"电压超出范围: {voltage}V")
            return False

        # 转换为寄存器值 (精度0.01V)
        reg_value = int(voltage * 100)
        address = self.REG_VOLTAGE_SET_BASE + (channel - 1)

        success = self._write_register(address, reg_value)
        if success:
            self.logger.info(f"通道{channel}设置电压: {voltage}V")

        return success

    def set_channel_current(self, channel: int, current: float) -> bool:
        """设置通道电流(恒流模式)

        Args:
            channel: 通道号 (1-6)
            current: 电流值(mA)，范围0-100.0mA，精度0.1mA

        Returns:
            成功返回True
        """
        if not (1 <= channel <= 6):
            self.logger.error(f"通道号超出范围: {channel}")
            return False

        if not (0 <= current <= 100.0):
            self.logger.error(f"电流超出范围: {current}mA")
            return False

        # 转换为寄存器值 (精度0.1mA)
        reg_value = int(current * 10)
        address = self.REG_CURRENT_SET_BASE + (channel - 1)

        success = self._write_register(address, reg_value)
        if success:
            self.logger.info(f"通道{channel}设置电流: {current}mA")

        return success

    def get_channel_voltage(self, channel: int) -> Optional[float]:
        """读取通道当前电压

        Args:
            channel: 通道号 (1-6)

        Returns:
            电压值(V)，失败返回None
        """
        if not (1 <= channel <= 6):
            self.logger.error(f"通道号超出范围: {channel}")
            return None

        address = self.REG_VOLTAGE_READ_BASE + (channel - 1)
        result = self._read_register(address)

        if result:
            # 转换为实际电压值 (精度0.01V)
            return result[0] / 100.0
        return None

    def get_channel_current(self, channel: int) -> Optional[float]:
        """读取通道当前电流

        Args:
            channel: 通道号 (1-6)

        Returns:
            电流值(mA)，失败返回None
        """
        if not (1 <= channel <= 6):
            self.logger.error(f"通道号超出范围: {channel}")
            return None

        address = self.REG_CURRENT_READ_BASE + (channel - 1)
        result = self._read_register(address)

        if result:
            # 转换为实际电流值 (精度0.1mA)
            return result[0] / 10.0
        return None

    def get_channel_fault_status(self, channel: int) -> Optional[FaultStatus]:
        """读取通道故障状态

        Args:
            channel: 通道号 (1-6)

        Returns:
            故障状态枚举，失败返回None
        """
        if not (1 <= channel <= 6):
            self.logger.error(f"通道号超出范围: {channel}")
            return None

        address = self.REG_FAULT_STATUS_BASE + (channel - 1)
        result = self._read_register(address)

        if result:
            return FaultStatus(result[0])
        return None

    def reset_channel_fault(self, channel: int) -> bool:
        """复位通道故障状态

        Args:
            channel: 通道号 (1-6)

        Returns:
            成功返回True
        """
        if not (1 <= channel <= 6):
            self.logger.error(f"通道号超出范围: {channel}")
            return False

        address = self.REG_FAULT_STATUS_BASE + (channel - 1)
        success = self._write_register(address, 0)

        if success:
            self.logger.info(f"通道{channel}故障已复位")

        return success

    # ==================== 搅拌控制 ====================

    def set_stirrer(self, control: StirrerControl, speed: int = 500) -> bool:
        """设置搅拌电机

        Args:
            control: 搅拌控制 (OFF=关闭, FORWARD=正转, REVERSE=反转)
            speed: 转速(rpm)，范围200-1000

        Returns:
            成功返回True
        """
        # 设置转速
        if control != StirrerControl.OFF:
            if not (200 <= speed <= 1000):
                self.logger.error(f"转速超出范围: {speed}rpm")
                return False

            if not self._write_register(self.REG_STIRRER_SPEED, speed):
                return False

        # 设置控制模式
        success = self._write_register(self.REG_STIRRER_CONTROL, control.value)

        if success:
            self._stirrer_running = (control != StirrerControl.OFF)
            self.logger.info(f"搅拌电机: {control.name}, 转速: {speed}rpm")

        return success

    def get_stirrer_speed(self) -> Optional[int]:
        """读取当前搅拌转速

        Returns:
            转速(rpm)，失败返回None
        """
        result = self._read_register(self.REG_SPEED_READ)
        if result:
            return result[0]
        return None

    # ==================== 高级功能 ====================

    def start_reaction(self,
                      channel: int,
                      mode: OutputMode,
                      voltage: float = 0.0,
                      current: float = 0.0,
                      stirrer_speed: int = 0) -> Dict[str, Any]:
        """启动电化学反应

        Args:
            channel: 通道号 (1-6)
            mode: 输出模式 (CONSTANT_VOLTAGE或CONSTANT_CURRENT)
            voltage: 电压值(V)，恒压模式时使用
            current: 电流值(mA)，恒流模式时使用
            stirrer_speed: 搅拌转速(rpm)，0表示不启动搅拌

        Returns:
            包含操作结果的字典
        """
        self.logger.info(f"启动通道{channel}反应: 模式={mode.name}, 电压={voltage}V, 电流={current}mA")

        # 设置输出模式
        if not self.set_output_mode(mode):
            self.success = False
            self.return_info = "设置输出模式失败"
            return {"success": False, "message": "设置输出模式失败"}

        # 设置电压或电流
        if mode == OutputMode.CONSTANT_VOLTAGE:
            if not self.set_channel_voltage(channel, voltage):
                self.success = False
                self.return_info = "设置电压失败"
                return {"success": False, "message": "设置电压失败"}
        else:
            if not self.set_channel_current(channel, current):
                self.success = False
                self.return_info = "设置电流失败"
                return {"success": False, "message": "设置电流失败"}

        # 启动搅拌(如果需要)
        if stirrer_speed > 0:
            if not self.set_stirrer(StirrerControl.FORWARD, stirrer_speed):
                self.logger.warning("启动搅拌失败，继续执行")

        # 打开通道
        if not self.set_channel_switch(channel, True):
            self.success = False
            self.return_info = "打开通道失败"
            return {"success": False, "message": "打开通道失败"}

        self.success = True
        self.return_info = f"通道{channel}反应已启动"
        return {
            "success": True,
            "message": f"通道{channel}反应已启动",
            "channel": channel,
            "mode": mode.name,
            "voltage": voltage,
            "current": current,
            "stirrer_speed": stirrer_speed
        }

    def stop_reaction(self, channel: int, stop_stirrer: bool = True) -> Dict[str, Any]:
        """停止电化学反应

        Args:
            channel: 通道号 (1-6)
            stop_stirrer: 是否同时停止搅拌

        Returns:
            包含操作结果的字典
        """
        self.logger.info(f"停止通道{channel}反应")

        # 关闭通道
        if not self.set_channel_switch(channel, False):
            self.success = False
            self.return_info = "关闭通道失败"
            return {"success": False, "message": "关闭通道失败"}

        # 停止搅拌(如果需要)
        if stop_stirrer:
            self.set_stirrer(StirrerControl.OFF)

        self.success = True
        self.return_info = f"通道{channel}反应已停止"
        return {
            "success": True,
            "message": f"通道{channel}反应已停止",
            "channel": channel
        }

    def get_channel_status(self, channel: int) -> Dict[str, Any]:
        """获取通道完整状态

        Args:
            channel: 通道号 (1-6)

        Returns:
            包含通道状态的字典
        """
        voltage = self.get_channel_voltage(channel)
        current = self.get_channel_current(channel)
        fault = self.get_channel_fault_status(channel)

        return {
            "channel": channel,
            "enabled": self._channel_states.get(channel, False),
            "voltage": voltage,
            "current": current,
            "fault_status": fault.name if fault else "UNKNOWN",
            "timestamp": time.time()
        }

    def get_all_channels_status(self) -> List[Dict[str, Any]]:
        """获取所有通道状态

        Returns:
            包含所有通道状态的列表
        """
        return [self.get_channel_status(i) for i in range(1, 7)]

    def emergency_stop(self) -> bool:
        """紧急停止所有通道

        Returns:
            成功返回True
        """
        self.logger.warning("执行紧急停止")

        success = True
        # 关闭所有通道
        for channel in range(1, 7):
            if not self.set_channel_switch(channel, False):
                success = False

        # 停止搅拌
        self.set_stirrer(StirrerControl.OFF)

        if success:
            self.logger.info("紧急停止完成")
        else:
            self.logger.error("紧急停止部分失败")

        return success

    def __del__(self):
        """析构函数，确保断开连接"""
        try:
            self.disconnect()
        except Exception:
            pass


if __name__ == "__main__":
    # 测试代码
    import argparse

    parser = argparse.ArgumentParser(description="GreenLab电反应仪驱动测试")
    parser.add_argument("--port", default="COM8", help="串口端口")
    parser.add_argument("--baudrate", type=int, default=115200, help="串口波特率")
    parser.add_argument("--slave", type=int, default=1, help="从站地址")
    parser.add_argument("--no-rts-toggle", action="store_true",
                        help="关闭 RS485 RTS 方向控制（自动方向转换器时使用）")

    args = parser.parse_args()

    # 配置日志
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
    )

    # 创建驱动实例
    device = GreenLabElectrochemical(
        port=args.port,
        baudrate=args.baudrate,
        slave_id=args.slave,
        rts_toggle=not args.no_rts_toggle,
    )

    try:
        if device.is_connected:
            print(f"设备状态: {device.status}")

            # 测试：启动通道1恒压反应
            print("\n=== 测试启动通道1恒压反应 ===")
            result = device.start_reaction(
                channel=1,
                mode=OutputMode.CONSTANT_VOLTAGE,
                voltage=5.0,
                stirrer_speed=500
            )
            print(f"结果: {result}")

            # 等待5秒
            time.sleep(5)

            # 读取通道状态
            print("\n=== 读取通道1状态 ===")
            status = device.get_channel_status(1)
            print(f"通道状态: {status}")

            # 停止反应
            print("\n=== 停止通道1反应 ===")
            result = device.stop_reaction(1)
            print(f"结果: {result}")

        else:
            print(f"设备连接失败: {device.status}")

    finally:
        device.disconnect()
