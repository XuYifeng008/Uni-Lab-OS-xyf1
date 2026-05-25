#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
GreenLab 电反应仪驱动测试脚本

用于验证驱动的基本功能，包括连接、读写寄存器、控制通道等
"""

import sys
import time
import logging
from pathlib import Path

# 添加项目路径
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))

from unilabos.devices.GreenLab import (
    GreenLabElectrochemical,
    OutputMode,
    AlternateMode,
    StirrerControl,
    FaultStatus
)


def test_connection(device):
    """测试设备连接"""
    print("\n" + "="*50)
    print("测试1: 设备连接")
    print("="*50)

    if device.is_connected:
        print("✓ 设备连接成功")
        print(f"  状态: {device.status}")
        return True
    else:
        print("✗ 设备连接失败")
        print(f"  状态: {device.status}")
        return False


def test_output_mode(device):
    """测试输出模式设置"""
    print("\n" + "="*50)
    print("测试2: 输出模式控制")
    print("="*50)

    # 设置恒压模式
    print("设置恒压模式...")
    if device.set_output_mode(OutputMode.CONSTANT_VOLTAGE):
        print("✓ 恒压模式设置成功")

        # 读取确认
        mode = device.get_output_mode()
        if mode == OutputMode.CONSTANT_VOLTAGE:
            print(f"✓ 读取确认: {mode.name}")
        else:
            print(f"✗ 读取不匹配: {mode}")
            return False
    else:
        print("✗ 恒压模式设置失败")
        return False

    time.sleep(0.5)

    # 设置恒流模式
    print("\n设置恒流模式...")
    if device.set_output_mode(OutputMode.CONSTANT_CURRENT):
        print("✓ 恒流模式设置成功")

        mode = device.get_output_mode()
        if mode == OutputMode.CONSTANT_CURRENT:
            print(f"✓ 读取确认: {mode.name}")
        else:
            print(f"✗ 读取不匹配: {mode}")
            return False
    else:
        print("✗ 恒流模式设置失败")
        return False

    return True


def test_channel_control(device):
    """测试通道控制"""
    print("\n" + "="*50)
    print("测试3: 通道控制")
    print("="*50)

    test_channel = 1

    # 设置恒压模式
    device.set_output_mode(OutputMode.CONSTANT_VOLTAGE)

    # 设置电压
    test_voltage = 5.0
    print(f"设置通道{test_channel}电压为 {test_voltage}V...")
    if device.set_channel_voltage(test_channel, test_voltage):
        print("✓ 电压设置成功")
    else:
        print("✗ 电压设置失败")
        return False

    time.sleep(0.5)

    # 打开通道
    print(f"打开通道{test_channel}...")
    if device.set_channel_switch(test_channel, True):
        print("✓ 通道已打开")
    else:
        print("✗ 通道打开失败")
        return False

    time.sleep(1)

    # 读取电压和电流
    print(f"\n读取通道{test_channel}状态...")
    voltage = device.get_channel_voltage(test_channel)
    current = device.get_channel_current(test_channel)

    if voltage is not None:
        print(f"✓ 当前电压: {voltage}V")
    else:
        print("✗ 读取电压失败")
        return False

    if current is not None:
        print(f"✓ 当前电流: {current}mA")
    else:
        print("✗ 读取电流失败")
        return False

    # 关闭通道
    print(f"\n关闭通道{test_channel}...")
    if device.set_channel_switch(test_channel, False):
        print("✓ 通道已关闭")
    else:
        print("✗ 通道关闭失败")
        return False

    return True


def test_stirrer_control(device):
    """测试搅拌控制"""
    print("\n" + "="*50)
    print("测试4: 搅拌控制")
    print("="*50)

    test_speed = 500

    # 启动搅拌
    print(f"启动搅拌，转速 {test_speed} rpm...")
    if device.set_stirrer(StirrerControl.FORWARD, test_speed):
        print("✓ 搅拌已启动")
    else:
        print("✗ 搅拌启动失败")
        return False

    time.sleep(1)

    # 读取转速
    print("读取当前转速...")
    speed = device.get_stirrer_speed()
    if speed is not None:
        print(f"✓ 当前转速: {speed} rpm")
    else:
        print("✗ 读取转速失败")
        return False

    time.sleep(1)

    # 停止搅拌
    print("\n停止搅拌...")
    if device.set_stirrer(StirrerControl.OFF):
        print("✓ 搅拌已停止")
    else:
        print("✗ 搅拌停止失败")
        return False

    return True


def test_fault_status(device):
    """测试故障状态读取"""
    print("\n" + "="*50)
    print("测试5: 故障状态")
    print("="*50)

    for channel in range(1, 7):
        fault = device.get_channel_fault_status(channel)
        if fault is not None:
            print(f"✓ 通道{channel}故障状态: {fault.name}")
        else:
            print(f"✗ 通道{channel}故障状态读取失败")
            return False

    return True


def test_advanced_functions(device):
    """测试高级功能"""
    print("\n" + "="*50)
    print("测试6: 高级功能")
    print("="*50)

    test_channel = 2

    # 启动反应
    print(f"启动通道{test_channel}反应...")
    result = device.start_reaction(
        channel=test_channel,
        mode=OutputMode.CONSTANT_VOLTAGE,
        voltage=3.0,
        stirrer_speed=400
    )

    if result['success']:
        print("✓ 反应启动成功")
        print(f"  详情: {result}")
    else:
        print("✗ 反应启动失败")
        print(f"  错误: {result.get('message')}")
        return False

    time.sleep(2)

    # 获取通道状态
    print(f"\n获取通道{test_channel}状态...")
    status = device.get_channel_status(test_channel)
    print(f"✓ 通道状态:")
    print(f"  - 通道号: {status['channel']}")
    print(f"  - 启用: {status['enabled']}")
    print(f"  - 电压: {status['voltage']}V")
    print(f"  - 电流: {status['current']}mA")
    print(f"  - 故障状态: {status['fault_status']}")

    time.sleep(1)

    # 停止反应
    print(f"\n停止通道{test_channel}反应...")
    result = device.stop_reaction(test_channel)

    if result['success']:
        print("✓ 反应停止成功")
    else:
        print("✗ 反应停止失败")
        return False

    return True


def test_all_channels_status(device):
    """测试获取所有通道状态"""
    print("\n" + "="*50)
    print("测试7: 所有通道状态")
    print("="*50)

    all_status = device.get_all_channels_status()

    print("所有通道状态:")
    for status in all_status:
        print(f"  通道{status['channel']}: "
              f"电压={status['voltage']}V, "
              f"电流={status['current']}mA, "
              f"故障={status['fault_status']}")

    return True


def run_all_tests(device):
    """运行所有测试"""
    tests = [
        ("设备连接", test_connection),
        ("输出模式控制", test_output_mode),
        ("通道控制", test_channel_control),
        ("搅拌控制", test_stirrer_control),
        ("故障状态", test_fault_status),
        ("高级功能", test_advanced_functions),
        ("所有通道状态", test_all_channels_status),
    ]

    results = []

    print("\n" + "="*50)
    print("GreenLab 电反应仪驱动测试")
    print("="*50)

    for test_name, test_func in tests:
        try:
            result = test_func(device)
            results.append((test_name, result))
        except Exception as e:
            print(f"\n✗ 测试异常: {e}")
            import traceback
            traceback.print_exc()
            results.append((test_name, False))

    # 打印测试总结
    print("\n" + "="*50)
    print("测试总结")
    print("="*50)

    passed = sum(1 for _, result in results if result)
    total = len(results)

    for test_name, result in results:
        status = "✓ 通过" if result else "✗ 失败"
        print(f"{status}: {test_name}")

    print(f"\n总计: {passed}/{total} 测试通过")

    return passed == total


def main():
    """主函数"""
    import argparse

    parser = argparse.ArgumentParser(description="GreenLab电反应仪驱动测试")
    parser.add_argument("--port", default="COM8",
                       help="串口端口 (默认: COM8)")
    parser.add_argument("--baudrate", type=int, default=115200,
                       help="串口波特率 (默认: 115200)")
    parser.add_argument("--slave", type=int, default=1,
                       help="从站地址 (默认: 1)")
    parser.add_argument("--no-rts-toggle", action="store_true",
                       help="关闭 RS485 RTS 方向控制")
    parser.add_argument("--test", choices=[
        "connection", "output_mode", "channel", "stirrer",
        "fault", "advanced", "all_status", "all"
    ], default="all", help="要运行的测试 (默认: all)")

    args = parser.parse_args()

    # 配置日志
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
    )

    # 创建设备实例
    print(f"串口: {args.port}, 波特率: {args.baudrate}")
    device = None
    try:
        device = GreenLabElectrochemical(
            port=args.port,
            baudrate=args.baudrate,
            slave_id=args.slave,
            rts_toggle=not args.no_rts_toggle,
        )
    except (ImportError, ValueError) as e:
        print(f"\n初始化失败: {e}")
        sys.exit(1)

    try:
        # 运行测试
        if args.test == "all":
            success = run_all_tests(device)
        else:
            test_map = {
                "connection": test_connection,
                "output_mode": test_output_mode,
                "channel": test_channel_control,
                "stirrer": test_stirrer_control,
                "fault": test_fault_status,
                "advanced": test_advanced_functions,
                "all_status": test_all_channels_status,
            }
            success = test_map[args.test](device)

        # 返回退出码
        sys.exit(0 if success else 1)

    except KeyboardInterrupt:
        print("\n\n测试被用户中断")
        sys.exit(1)
    except Exception as e:
        print(f"\n\n测试失败: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
    finally:
        # 确保断开连接
        if device is not None:
            print("\n断开设备连接...")
            device.disconnect()
            print("完成")


if __name__ == "__main__":
    main()
