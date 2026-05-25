# GreenLab 电反应仪设备配置示例

## Modbus TCP 配置示例

```yaml
# device_config.yaml
greenlab_reactor_1:
  type: greenlab_electrochemical
  config:
    ip: "192.168.1.100"
    modbus_port: 502
    slave_id: 1
    timeout: 3
```

## Modbus RTU 配置示例

```yaml
# device_config.yaml
greenlab_reactor_1:
  type: greenlab_electrochemical
  config:
    port: "COM3"  # Windows
    # port: "/dev/ttyUSB0"  # Linux
    baudrate: 9600
    slave_id: 1
    timeout: 3
```

## 多设备配置示例

```yaml
# device_config.yaml
# 配置多台GreenLab设备（通过不同的从站地址）

greenlab_reactor_1:
  type: greenlab_electrochemical
  config:
    ip: "192.168.1.100"
    slave_id: 1

greenlab_reactor_2:
  type: greenlab_electrochemical
  config:
    ip: "192.168.1.100"
    slave_id: 2

greenlab_reactor_3:
  type: greenlab_electrochemical
  config:
    ip: "192.168.1.100"
    slave_id: 3
```

## JSON 格式配置示例

```json
{
  "nodes": [
    {
      "id": "greenlab_1",
      "type": "greenlab_electrochemical",
      "config": {
        "ip": "192.168.1.100",
        "modbus_port": 502,
        "slave_id": 1,
        "timeout": 3
      }
    }
  ]
}
```

## 实验流程配置示例

```yaml
# experiment_workflow.yaml
workflow:
  name: "电化学合成实验"
  
  devices:
    reactor:
      type: greenlab_electrochemical
      config:
        ip: "192.168.1.100"
        slave_id: 1
  
  steps:
    - name: "初始化"
      actions:
        - device: reactor
          action: set_output_mode
          params:
            mode: 0  # 恒压模式
    
    - name: "启动反应"
      actions:
        - device: reactor
          action: start_reaction
          params:
            channel: 1
            mode: 0
            voltage: 5.0
            stirrer_speed: 500
    
    - name: "监测反应"
      duration: 600  # 10分钟
      interval: 30   # 每30秒采集一次
      actions:
        - device: reactor
          action: get_channel_status
          params:
            channel: 1
    
    - name: "停止反应"
      actions:
        - device: reactor
          action: stop_reaction
          params:
            channel: 1
            stop_stirrer: true
```

## Python 配置示例

```python
# config.py
DEVICE_CONFIG = {
    'greenlab_reactor_1': {
        'type': 'greenlab_electrochemical',
        'config': {
            'ip': '192.168.1.100',
            'modbus_port': 502,
            'slave_id': 1,
            'timeout': 3
        }
    }
}

# 实验参数
EXPERIMENT_PARAMS = {
    'voltage': 5.0,        # V
    'current': 50.0,       # mA
    'stirrer_speed': 500,  # rpm
    'duration': 600,       # seconds
}
```

## 网络配置建议

### 静态IP配置（推荐）

为GreenLab设备配置静态IP地址，避免DHCP导致的IP变化：

```
设备IP: 192.168.1.100
子网掩码: 255.255.255.0
网关: 192.168.1.1
```

### 防火墙配置

确保Modbus TCP端口（502）未被防火墙阻止：

**Windows:**
```powershell
# 允许Modbus TCP端口
netsh advfirewall firewall add rule name="Modbus TCP" dir=in action=allow protocol=TCP localport=502
```

**Linux:**
```bash
# 允许Modbus TCP端口
sudo ufw allow 502/tcp
```

## 串口配置建议

### Windows

1. 确认COM端口号：
   - 打开"设备管理器"
   - 展开"端口(COM和LPT)"
   - 找到USB转RS485适配器的COM端口号

2. 配置串口参数：
   ```python
   config = {
       'port': 'COM3',
       'baudrate': 9600,
       'slave_id': 1
   }
   ```

### Linux

1. 确认串口设备：
   ```bash
   ls /dev/ttyUSB*
   # 或
   ls /dev/ttyACM*
   ```

2. 添加用户到dialout组（避免权限问题）：
   ```bash
   sudo usermod -a -G dialout $USER
   # 需要重新登录生效
   ```

3. 配置串口参数：
   ```python
   config = {
       'port': '/dev/ttyUSB0',
       'baudrate': 9600,
       'slave_id': 1
   }
   ```

## 故障排查配置

### 启用详细日志

```python
import logging

# 设置日志级别为DEBUG
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s [%(levelname)s] %(name)s: %(message)s',
    handlers=[
        logging.FileHandler('greenlab_debug.log'),
        logging.StreamHandler()
    ]
)
```

### 增加超时时间

对于网络延迟较大的环境：

```yaml
config:
  ip: "192.168.1.100"
  timeout: 10  # 增加到10秒
```

### 测试连接

使用测试脚本验证连接：

```bash
# TCP模式
python test_greenlab.py --mode tcp --ip 192.168.1.100 --test connection

# RTU模式
python test_greenlab.py --mode rtu --port COM3 --test connection
```

## 性能优化配置

### 批量操作

对于需要同时控制多个通道的场景，建议批量设置：

```python
# 不推荐：逐个设置
for channel in range(1, 7):
    device.set_channel_voltage(channel, 5.0)
    device.set_channel_switch(channel, True)

# 推荐：先设置所有参数，最后统一打开
device.set_output_mode(OutputMode.CONSTANT_VOLTAGE)
for channel in range(1, 7):
    device.set_channel_voltage(channel, 5.0)
# 统一打开
for channel in range(1, 7):
    device.set_channel_switch(channel, True)
```

### 减少轮询频率

对于不需要高频监测的场景，适当降低采样频率：

```python
# 每10秒采样一次，而不是每秒
import time
while running:
    status = device.get_channel_status(1)
    # 处理数据...
    time.sleep(10)  # 10秒间隔
```

## 安全配置建议

1. **限制网络访问**
   - 将GreenLab设备放在独立的VLAN中
   - 只允许特定IP访问Modbus端口

2. **定期备份配置**
   - 记录设备的从站地址、波特率等配置
   - 保存实验参数和校准数据

3. **紧急停止按钮**
   - 在实验程序中实现紧急停止功能
   - 使用`emergency_stop()`方法

4. **故障监测**
   - 定期检查通道故障状态
   - 设置电压/电流异常报警

```python
# 故障监测示例
def monitor_faults(device):
    for channel in range(1, 7):
        fault = device.get_channel_fault_status(channel)
        if fault != FaultStatus.NO_FAULT:
            print(f"警告: 通道{channel}故障 - {fault.name}")
            # 发送报警通知...
```
