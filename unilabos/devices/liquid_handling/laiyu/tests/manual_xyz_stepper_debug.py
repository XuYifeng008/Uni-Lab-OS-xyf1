#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
来裕 XYZ 三轴步进电机独立调试脚本。

默认只读取状态，不会移动电机。执行移动、回零、速度模式前请确认机械行程、
限位和急停条件安全。
"""

from __future__ import annotations

import argparse
import logging
import sys
import time
from pathlib import Path
from typing import Iterable


PROJECT_ROOT = Path(__file__).resolve().parents[5]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from unilabos.devices.liquid_handling.laiyu.drivers.xyz_stepper_driver import (  # noqa: E402
    MotorAxis,
    MotorPosition,
    XYZStepperController,
)


AXIS_MAP = {
    "x": MotorAxis.X,
    "y": MotorAxis.Y,
    "z": MotorAxis.Z,
}


def parse_axis(value: str) -> MotorAxis:
    try:
        return AXIS_MAP[value.lower()]
    except KeyError as exc:
        raise argparse.ArgumentTypeError("轴必须是 x、y 或 z") from exc


def format_position(axis: MotorAxis, pos: MotorPosition, controller: XYZStepperController) -> str:
    degrees = controller.steps_to_degrees(pos.steps)
    revolutions = controller.steps_to_revolutions(pos.steps)
    return (
        f"{axis.name}: status={pos.status.name}, steps={pos.steps}, "
        f"degrees={degrees:.3f}, revolutions={revolutions:.6f}, "
        f"speed={pos.speed}, current={pos.current}"
    )


def print_positions(controller: XYZStepperController, axes: Iterable[MotorAxis] = MotorAxis) -> None:
    for axis in axes:
        pos = controller.get_motor_status(axis)
        print(format_position(axis, pos, controller))


def print_results(title: str, results: dict[MotorAxis, bool]) -> None:
    print(title)
    for axis, ok in results.items():
        print(f"  {axis.name}: {'OK' if ok else 'FAILED'}")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="使用 xyz_stepper_driver.py 单独调试来裕 XYZ 三轴电机"
    )
    parser.add_argument("--port", required=True, help="串口号，例如 Windows: COM3，Linux: /dev/ttyUSB0")
    parser.add_argument("--baudrate", type=int, default=115200, help="波特率，默认 115200")
    parser.add_argument("--timeout", type=float, default=1.0, help="串口超时时间，默认 1 秒")
    parser.add_argument("--response-delay", type=float, default=0.03, help="发送后等待响应时间，默认 0.03 秒")
    parser.add_argument("--debug", action="store_true", help="打印调试日志和 Modbus 报文")

    subparsers = parser.add_subparsers(dest="command", required=True)

    subparsers.add_parser("status", help="读取三轴状态，不移动电机")

    scan_parser = subparsers.add_parser("scan", help="扫描 Modbus 地址")
    scan_parser.add_argument("--start", type=int, default=1, help="起始地址，默认 1")
    scan_parser.add_argument("--end", type=int, default=4, help="结束地址，默认 4")

    enable_parser = subparsers.add_parser("enable", help="使能电机")
    enable_parser.add_argument("--axis", type=parse_axis, help="只使能指定轴；不填则使能三轴")

    disable_parser = subparsers.add_parser("disable", help="失能电机")
    disable_parser.add_argument("--axis", type=parse_axis, help="只失能指定轴；不填则失能三轴")

    home_parser = subparsers.add_parser("home", help="回零")
    home_parser.add_argument("--axis", type=parse_axis, help="只回零指定轴；不填则回零三轴")
    home_parser.add_argument("--wait", action="store_true", help="等待回零完成")
    home_parser.add_argument("--wait-timeout", type=float, default=30.0, help="等待超时，默认 30 秒")

    stop_parser = subparsers.add_parser("stop", help="紧急停止")
    stop_parser.add_argument("--axis", type=parse_axis, help="只停止指定轴；不填则停止三轴")

    move_steps_parser = subparsers.add_parser("move-steps", help="按绝对步数移动")
    move_steps_parser.add_argument("--axis", type=parse_axis, required=True, help="目标轴: x/y/z")
    move_steps_parser.add_argument("--position", type=int, required=True, help="目标绝对位置，单位: steps")
    move_steps_parser.add_argument("--speed", type=int, default=5000, help="速度，默认 5000")
    move_steps_parser.add_argument("--acceleration", type=int, default=1000, help="加速度，默认 1000")
    move_steps_parser.add_argument("--precision", type=int, default=100, help="到位精度，默认 100")
    move_steps_parser.add_argument("--wait", action="store_true", help="等待移动完成")
    move_steps_parser.add_argument("--wait-timeout", type=float, default=30.0, help="等待超时，默认 30 秒")

    move_degrees_parser = subparsers.add_parser("move-degrees", help="按绝对角度移动")
    move_degrees_parser.add_argument("--axis", type=parse_axis, required=True, help="目标轴: x/y/z")
    move_degrees_parser.add_argument("--degrees", type=float, required=True, help="目标绝对角度")
    move_degrees_parser.add_argument("--speed", type=int, default=5000, help="速度，默认 5000")
    move_degrees_parser.add_argument("--acceleration", type=int, default=1000, help="加速度，默认 1000")
    move_degrees_parser.add_argument("--precision", type=int, default=100, help="到位精度，默认 100")
    move_degrees_parser.add_argument("--wait", action="store_true", help="等待移动完成")
    move_degrees_parser.add_argument("--wait-timeout", type=float, default=30.0, help="等待超时，默认 30 秒")

    speed_parser = subparsers.add_parser("speed-mode", help="速度模式连续运行，需用 stop 停止")
    speed_parser.add_argument("--axis", type=parse_axis, required=True, help="目标轴: x/y/z")
    speed_parser.add_argument("--speed", type=int, required=True, help="速度，正负表示方向")
    speed_parser.add_argument("--acceleration", type=int, default=1000, help="加速度，默认 1000")
    speed_parser.add_argument(
        "--duration",
        type=float,
        default=0.0,
        help="运行指定秒数后自动急停；默认 0 表示不自动停止",
    )

    return parser


def run_command(controller: XYZStepperController, args: argparse.Namespace) -> None:
    if args.command == "status":
        print_positions(controller)
        return

    if args.command == "scan":
        found = controller.scan_addresses(args.start, args.end)
        if not found:
            print(f"地址 {args.start}-{args.end} 未发现响应")
            return
        print(f"发现 {len(found)} 个响应地址:")
        for address, pos in found.items():
            print(
                f"  addr={address}: status={pos.status.name}, steps={pos.steps}, "
                f"speed={pos.speed}, current={pos.current}"
            )
        return

    if args.command == "enable":
        if args.axis:
            print(f"{args.axis.name}: {'OK' if controller.enable_motor(args.axis, True) else 'FAILED'}")
        else:
            print_results("使能结果:", controller.enable_all_axes(True))
        print_positions(controller)
        return

    if args.command == "disable":
        if args.axis:
            print(f"{args.axis.name}: {'OK' if controller.enable_motor(args.axis, False) else 'FAILED'}")
        else:
            print_results("失能结果:", controller.enable_all_axes(False))
        print_positions(controller)
        return

    if args.command == "home":
        axes = [args.axis] if args.axis else list(MotorAxis)
        results = {axis: controller.home_axis(axis) for axis in axes}
        print_results("回零命令发送结果:", results)
        if args.wait:
            for axis in axes:
                ok = controller.wait_for_completion(axis, args.wait_timeout)
                print(f"{axis.name} 等待完成: {'OK' if ok else 'TIMEOUT'}")
        print_positions(controller, axes)
        return

    if args.command == "stop":
        if args.axis:
            print(f"{args.axis.name}: {'OK' if controller.emergency_stop(args.axis) else 'FAILED'}")
            print_positions(controller, [args.axis])
        else:
            print_results("急停结果:", controller.stop_all_axes())
            print_positions(controller)
        return

    if args.command == "move-steps":
        ok = controller.move_to_position(
            args.axis,
            args.position,
            speed=args.speed,
            acceleration=args.acceleration,
            precision=args.precision,
        )
        print(f"{args.axis.name} 移动命令发送: {'OK' if ok else 'FAILED'}")
        if args.wait:
            ok = controller.wait_for_completion(args.axis, args.wait_timeout)
            print(f"{args.axis.name} 等待完成: {'OK' if ok else 'TIMEOUT'}")
        print_positions(controller, [args.axis])
        return

    if args.command == "move-degrees":
        steps = controller.degrees_to_steps(args.degrees)
        print(f"{args.degrees} degrees -> {steps} steps")
        ok = controller.move_to_position_degrees(
            args.axis,
            args.degrees,
            speed=args.speed,
            acceleration=args.acceleration,
            precision=args.precision,
        )
        print(f"{args.axis.name} 移动命令发送: {'OK' if ok else 'FAILED'}")
        if args.wait:
            ok = controller.wait_for_completion(args.axis, args.wait_timeout)
            print(f"{args.axis.name} 等待完成: {'OK' if ok else 'TIMEOUT'}")
        print_positions(controller, [args.axis])
        return

    if args.command == "speed-mode":
        ok = controller.set_speed_mode(args.axis, args.speed, args.acceleration)
        print(f"{args.axis.name} 速度模式命令发送: {'OK' if ok else 'FAILED'}")
        if args.duration > 0:
            print(f"运行 {args.duration} 秒后自动急停...")
            time.sleep(args.duration)
            print(f"{args.axis.name} 急停: {'OK' if controller.emergency_stop(args.axis) else 'FAILED'}")
        print_positions(controller, [args.axis])
        return

    raise ValueError(f"未知命令: {args.command}")


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()

    logging.getLogger().setLevel(logging.DEBUG if args.debug else logging.INFO)

    controller = XYZStepperController(
        args.port,
        baudrate=args.baudrate,
        timeout=args.timeout,
        response_delay=args.response_delay,
    )
    if not controller.connect():
        print(f"无法连接串口: {args.port}", file=sys.stderr)
        return 1

    try:
        run_command(controller, args)
        return 0
    finally:
        controller.disconnect()


if __name__ == "__main__":
    raise SystemExit(main())
