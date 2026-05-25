# GreenLab 电反应仪驱动使用指南

## 概述

GreenLab 电反应仪驱动支持通过 Modbus RTU/TCP 协议控制 GreenLab 6通道电化学反应仪。

## 功能特性

- ✅ 6通道独立控制
- ✅ 恒流/恒压输出模式
- ✅ 低频/高频交替模式
- ✅ 搅拌电机控制（正转/反转，200-1000 rpm）
- ✅ 实时电压/电流监测
- ✅ 故障状态监测与复位
- ✅ 紧急停止功能

## 硬件连接

### Modbus RTU 模式（串口）

```
PC ──[USB转RS485]── GreenLab电反应仪
```

**连接参数：**
- 波特率：9600（默认，可选：2400/4800/9600/19200/57600/115200）
- 数据位：8
- 停止位：1
- 校验位：无
- 从站地址：1（默认，可在设备上修改为1-254）

### Modbus TCP 模式（以太网）

```
PC ──[以太网]── GreenLab电反应仪
```

**连接参数：**
- IP地址：根据设备配置（例如：192.168.1.100）
- 端口：502（Modbus标准端口）
- 从站地址：1

## 安装依赖

```bash
pip install pymodbus
```

## 快速开始

### 1. 独立测试（不依赖Uni-Lab框架）

```python
from unilabos.devices.GreenLab import GreenLabElectrochemical, OutputMode, StirrerControl

# Modbus TCP模式
device = GreenLabElectrochemical(ip="192.168.1.100", slave_id=1)

# 或 Modbus RTU模式
# device = GreenLabElectrochemical(port="COM3", baudrate=9600, slave_id=1)

# 启动通道1恒压反应
result = device.start_reaction(
    channel=1,
    mode=OutputMode.CONSTANT_VOLTAGE,
    voltage=5.0,           # 5V
    stirrer_speed=500      # 500 rpm
)
print(result)

# 读取通道状态
status = device.get_channel_status(1)
print(f"电压: {status['voltage']}V, 电流: {status['current']}mA")

# 停止反应
device.stop_reaction(1)
device.disconnect()
```

### 2. 在Uni-Lab中使用

#### 设备图文件配置（JSON格式）

```json
{
  "nodes": [
    {
      "id": "greenlab_1",
      "type": "greenlab_electrochemical",
      "config": {
        "ip": "192.168.1.100",
        "modbus_port": 502,
        "slave_id": 1
      }
    }
  ]
}
```

#### 启动Uni-Lab

```bash
unilab --graph device_graph.json --config config.py --backend ros
```

#### 通过ROS2 Action调用

```python
# 在其他节点中调用
from rclpy.action import ActionClient

# 启动反应
goal = {
    "channel": 1,
    "mode": 0,  # 0=恒压, 1=恒流
    "voltage": 5.0,
    "stirrer_speed": 500
}
action_client.send_goal_async("greenlab_1/start_reaction", goal)
```

## API 参考

### 输出模式

```python
from unilabos.devices.GreenLab import OutputMode

OutputMode.CONSTANT_VOLTAGE  # 恒压模式
OutputMode.CONSTANT_CURRENT  # 恒流模式
```

### 交替模式

```python
from unilabos.devices.GreenLab import AlternateMode

AlternateMode.NO_ALTERNATE        # 无交替
AlternateMode.LOW_FREQ_ALTERNATE  # 低频交替（1-6000秒）
AlternateMode.HIGH_FREQ_ALTERNATE # 高频交替（5-1000毫秒）
```

### 搅拌控制

```python
from unilabos.devices.GreenLab import StirrerControl

StirrerControl.OFF      # 关闭
StirrerControl.FORWARD  # 正转
StirrerControl.REVERSE  # 反转
```

### 主要方法

#### 输出模式控制

```python
# 设置输出模式
device.set_output_mode(OutputMode.CONSTANT_VOLTAGE)

# 设置交替模式
device.set_alternate_mode(
    AlternateMode.LOW_FREQ_ALTERNATE,
    low_freq_time=10  # 10秒交替
)
```

#### 通道控制

```python
# 打开/关闭通道
device.set_channel_switch(channel=1, enable=True)

# 设置电压（恒压模式）
device.set_channel_voltage(channel=1, voltage=5.0)  # 5V

# 设置电流（恒流模式）
device.set_channel_current(channel=1, current=50.0)  # 50mA

# 读取电压
voltage = device.get_channel_voltage(channel=1)

# 读取电流
current = device.get_channel_current(channel=1)

# 读取故障状态
fault = device.get_channel_fault_status(channel=1)

# 复位故障
device.reset_channel_fault(channel=1)
```

#### 搅拌控制

```python
# 启动搅拌（正转，500 rpm）
device.set_stirrer(StirrerControl.FORWARD, speed=500)

# 读取当前转速
speed = device.get_stirrer_speed()

# 停止搅拌
device.set_stirrer(StirrerControl.OFF)
```

#### 高级功能

```python
# 启动反应（一键配置）
result = device.start_reaction(
    channel=1,
    mode=OutputMode.CONSTANT_VOLTAGE,
    voltage=5.0,
    current=0.0,
    stirrer_speed=500
)

# 停止反应
result = device.stop_reaction(channel=1, stop_stirrer=True)

# 获取通道状态
status = device.get_channel_status(channel=1)
# 返回: {
#   "channel": 1,
#   "enabled": True,
#   "voltage": 5.02,
#   "current": 23.5,
#   "fault_status": "NO_FAULT",
#   "timestamp": 1234567890.123
# }

# 获取所有通道状态
all_status = device.get_all_channels_status()

# 紧急停止所有通道
device.emergency_stop()
```

## 参数范围

| 参数 | 范围 | 精度 | 说明 |
|------|------|------|------|
| 电压 | 0-30V | 0.01V | 恒压模式输出电压 |
| 电流 | 0-100mA | 0.1mA | 恒流模式输出电流 |
| 搅拌转速 | 200-1000 rpm | 1 rpm | 搅拌电机转速 |
| 低频交替时间 | 1-6000秒 | 1秒 | 低频交替周期 |
| 高频交替时间 | 5-1000毫秒 | 1毫秒 | 高频交替周期 |

## 故障状态说明

| 状态码 | 名称 | 说明 | 处理方法 |
|--------|------|------|----------|
| 0 | NO_FAULT | 无故障 | - |
| 1 | HIGH_RESISTANCE | 内阻大，电流为0 | 检查电极连接 |
| 2 | CURRENT_OVER_LIMIT | 电流超限制 | 降低电流设定值 |
| 3 | COUNTDOWN_NOT_SET | 请设置倒计时时间 | 设置反应时间 |
| 4 | VOLTAGE_OVER_OR_RESISTANCE | 电压超限或电阻过大 | 检查负载 |

## Modbus寄存器映射

详细的寄存器映射请参考 `副本电反应地址表 - V10.xls`。

### 主要寄存器

| 地址 | 功能 | 读写 | 范围 |
|------|------|------|------|
| 0 | 输出模式 | RW | 0=恒压, 1=恒流 |
| 1 | 交替模式 | RW | 0=无, 1=低频, 2=高频 |
| 5-10 | 通道1-6开关 | RW | 0=关, 1=开 |
| 11-16 | 通道1-6电压设置 | RW | 0-3000 (0.01V) |
| 17-22 | 通道1-6电流设置 | RW | 0-1000 (0.1mA) |
| 24 | 搅拌控制 | RW | 0=关, 1=正转, 2=反转 |
| 25 | 搅拌转速 | RW | 200-1000 rpm |
| 50-55 | 通道1-6故障状态 | RW | 写0复位 |
| 56-61 | 通道1-6当前电压 | R | 0-3000 (0.01V) |
| 62-67 | 通道1-6当前电流 | R | 0-1000 (0.1mA) |
| 68 | 当前转速 | R | rpm |

## 故障排查

### 连接失败

1. **检查物理连接**
   - RTU模式：确认USB转RS485适配器已正确连接
   - TCP模式：确认网线连接，设备IP地址正确

2. **检查通信参数**
   - 波特率是否匹配（默认9600）
   - 从站地址是否正确（默认1）
   - TCP端口是否正确（默认502）

3. **检查设备电源**
   - 确认设备已上电
   - 检查设备指示灯状态

### 读写失败

1. **检查寄存器地址**
   - 确认使用的寄存器地址在有效范围内
   - 参考地址表文档

2. **检查数据范围**
   - 电压：0-30V
   - 电流：0-100mA
   - 转速：200-1000 rpm

3. **检查通信超时**
   - 增加timeout参数值
   - 检查网络延迟

### 通道无输出

1. **检查通道开关**
   - 确认通道已打开：`set_channel_switch(channel, True)`

2. **检查输出模式**
   - 恒压模式：确认已设置电压值
   - 恒流模式：确认已设置电流值

3. **检查故障状态**
   - 读取故障状态：`get_channel_fault_status(channel)`
   - 如有故障，复位后重试：`reset_channel_fault(channel)`

## 示例代码

### 示例1：恒压电解实验

```python
from unilabos.devices.GreenLab import GreenLabElectrochemical, OutputMode
import time

device = GreenLabElectrochemical(ip="192.168.1.100")

# 启动恒压电解
device.start_reaction(
    channel=1,
    mode=OutputMode.CONSTANT_VOLTAGE,
    voltage=3.0,
    stirrer_speed=600
)

# 监测10分钟
for i in range(60):
    status = device.get_channel_status(1)
    print(f"时间: {i*10}s, 电压: {status['voltage']}V, 电流: {status['current']}mA")
    time.sleep(10)

# 停止反应
device.stop_reaction(1)
device.disconnect()
```

### 示例2：恒流充电实验

```python
from unilabos.devices.GreenLab import GreenLabElectrochemical, OutputMode

device = GreenLabElectrochemical(port="COM3", baudrate=9600)

# 启动恒流充电
device.start_reaction(
    channel=2,
    mode=OutputMode.CONSTANT_CURRENT,
    current=50.0,  # 50mA
    stirrer_speed=0  # 不启动搅拌
)

# 监测电压变化
import time
for i in range(30):
    voltage = device.get_channel_voltage(2)
    current = device.get_channel_current(2)
    print(f"电压: {voltage}V, 电流: {current}mA")
    
    # 电压达到4.2V时停止
    if voltage >= 4.2:
        print("充电完成")
        break
    
    time.sleep(10)

device.stop_reaction(2)
device.disconnect()
```

### 示例3：多通道并行实验

```python
from unilabos.devices.GreenLab import GreenLabElectrochemical, OutputMode

device = GreenLabElectrochemical(ip="192.168.1.100")

# 设置恒压模式
device.set_output_mode(OutputMode.CONSTANT_VOLTAGE)

# 启动搅拌
device.set_stirrer(StirrerControl.FORWARD, speed=500)

# 启动多个通道
voltages = [2.0, 2.5, 3.0, 3.5, 4.0, 4.5]
for channel, voltage in enumerate(voltages, start=1):
    device.set_channel_voltage(channel, voltage)
    device.set_channel_switch(channel, True)
    print(f"通道{channel}已启动，电压: {voltage}V")

# 监测所有通道
import time
for i in range(10):
    all_status = device.get_all_channels_status()
    print(f"\n=== 时间: {i*30}s ===")
    for status in all_status:
        if status['enabled']:
            print(f"通道{status['channel']}: {status['voltage']}V, {status['current']}mA")
    time.sleep(30)

# 停止所有通道
device.emergency_stop()
device.disconnect()
```

## 技术支持

如有问题，请参考：
- 设备手册：`副本电反应地址表 - V10.xls`
- Modbus配置：`MODBUS-RTU - V2/` 目录
- Uni-Lab文档：`docs/developer_guide/add_device.md`

## 许可证

本驱动遵循 DP Technology Proprietary License，请勿未经授权重新分发。
