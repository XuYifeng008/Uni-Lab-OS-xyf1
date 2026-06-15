# LaiYu 液体处理器模块

本文档说明 `unilabos.devices.liquid_handling.laiyu` 当前代码的实际结构、运行入口和配置方式。

## 模块定位

`laiyu` 模块用于接入铼羽液体处理设备。当前主要有两条代码路径：

- UniLabOS 设备图入口：`laiyu.py` 中的 `TransformXYZHandler`，由注册表中的 `liquid_handler.laiyu` 使用。
- 底层硬件控制：`backend/laiyu_v_backend.py`、`controllers/`、`drivers/`，用于通过 SOPA 移液器和 XYZ 步进电机执行取枪头、吸液、排液、丢枪头等动作。

历史文件 `core/LaiYu_Liquid.py`、`core/laiyu_liquid_res.py` 保留了早期封装和资源创建函数，但不是当前设备图中的主入口。维护时应优先看 `laiyu.py` 和 `backend/laiyu_v_backend.py`。

## 当前目录结构

```text
unilabos/devices/liquid_handling/laiyu/
├── laiyu.py                    # UniLabOS 液体处理器入口，定义 TransformXYZHandler/Deck/Container
├── backend/
│   ├── __init__.py             # 导出 UniLiquidHandlerLaiyuBackend
│   ├── laiyu_v_backend.py      # 当前硬件后端，桥接 PyLabRobot 操作到铼羽控制器
│   └── laiyu_backend.py        # 早期模拟后端，当前未从 backend 包导出
├── controllers/
│   ├── pipette_controller.py   # 移液器高级控制，组合 SOPA 与可选 XYZ 控制
│   └── xyz_controller.py       # XYZ 坐标、回零、安全移动等高级控制
├── drivers/
│   ├── sopa_pipette_driver.py  # SOPA 气动移液器 RS485 驱动
│   └── xyz_stepper_driver.py   # XYZ 步进电机 RS485/Modbus 驱动
├── config/
│   └── deckconfig.json         # 铼羽台面几何配置，见下文说明
├── core/
│   ├── LaiYu_Liquid.py         # 早期主类/后端封装
│   ├── laiyu_liquid_res.py     # 早期资源定义和便捷创建函数
│   └── abstract_protocol.py    # 早期材料/转移协议辅助模型
├── docs/
│   └── readme.md               # 本文档
└── tests/
    └── test_deck_config.py     # 台面配置检查脚本，当前路径也带有历史遗留问题
```

## 设备注册入口

铼羽液体处理器在 `unilabos/registry/devices/liquid_handler.yaml` 中注册为 `liquid_handler.laiyu`，实际 Python 类为：

```text
unilabos.devices.liquid_handling.laiyu.laiyu:TransformXYZHandler
```

资源 `TransformXYZDeck` 在 `unilabos/registry/resources/laiyu/deck.yaml` 中注册：

```text
unilabos.devices.liquid_handling.laiyu.laiyu:TransformXYZDeck
```

因此，在图文件里通常不直接实例化 `UniLiquidHandlerLaiyuBackend`，而是通过液体处理器设备节点的 `backend` 配置选择模拟或真实硬件。

## 关键类

### `TransformXYZHandler`

位置：`laiyu.py`

这是 UniLabOS 当前使用的液体处理器入口类，继承 `LiquidHandlerAbstract`。

初始化参数包括：

- `deck`：工作台资源，通常来自图文件中的 `TransformXYZDeck`
- `host`、`port`、`timeout`：非模拟后端的连接参数
- `channel_num`：通道数，默认 `1`
- `simulator`：是否使用模拟/RViz 后端，默认 `True`
- `backend_kwargs`：透传给上层液体处理抽象

当前 `TransformXYZHandler` 中 `add_liquid`、`aspirate`、`dispense`、`pick_up_tips` 等方法本身多为空实现，实际标准动作主要依赖 `LiquidHandlerAbstract` 与后端对象完成。

### `UniLiquidHandlerLaiyuBackend`

位置：`backend/laiyu_v_backend.py`

这是当前硬件后端。它继承 PyLabRobot 的 `LiquidHandlerBackend`，把 PyLabRobot 标准操作转换为铼羽硬件动作：

- `setup()`：初始化 ROS2/rclpy，连接并初始化 `PipetteController`
- `pick_up_tips()`：移动到枪头位，检查枪头状态并执行取枪头流程
- `drop_tips()`：移动到丢枪头位置并退枪头
- `aspirate()`：根据目标资源绝对坐标移动，并调用 SOPA 吸液
- `dispense()`：根据目标资源绝对坐标移动，并调用 SOPA 排液

后端内部使用：

- `PipetteController(port=...)`
- `XYZController`
- `TipStatus`
- PyLabRobot 资源的 `get_absolute_location()`

### `PipetteController`

位置：`controllers/pipette_controller.py`

高级移液控制器，封装 SOPA 移液器驱动和可选 XYZ 控制器。默认移液器 RS485 地址为 `4`，波特率为 `115200`。

它维护：

- 当前枪头状态：`TipStatus.NO_TIP` / `TIP_ATTACHED` / `TIP_USED`
- 当前体积：`current_volume`
- 最大体积：默认 `1000 ul`
- 液体类型参数：`WATER`、`SERUM`、`VISCOUS`、`VOLATILE`、`CUSTOM`

### `XYZController`

位置：`controllers/xyz_controller.py`

高级 XYZ 运动控制器，继承 `XYZStepperController`。主要职责包括：

- 串口连接和轴使能
- 回零与坐标原点管理
- 机械坐标/工作坐标转换
- 安全高度移动
- 行程限制检查

默认机械参数在 `MachineConfig` 中，例如：

- X/Y 步距：`204.8 steps/mm`
- Z 步距：`3276.8 steps/mm`
- 最大行程：X `340 mm`、Y `250 mm`、Z `200 mm`

### 驱动层

`drivers/sopa_pipette_driver.py` 提供 SOPA 气动移液器底层驱动，包含连接、初始化、吸液、排液、状态查询等能力。

`drivers/xyz_stepper_driver.py` 提供步进电机底层驱动，包含 Modbus/RS485 通信、电机状态、轴控制、XYZ 组合控制等能力。

## 图文件示例

当前仓库中有两个示例图：

- `unilabos/test/experiments/test_laiyu.json`：真实硬件示例，`simulator=false`，后端类型为 `UniLiquidHandlerLaiyuBackend`，串口示例为 `COM8`
- `unilabos/test/experiments/test_laiyu_v.json`：模拟/RViz 示例，`simulator=true`，后端类型为 `UniLiquidHandlerRvizBackend`

真实硬件节点的关键配置形如：

```json
{
  "id": "liquid_handler",
  "class": "liquid_handler",
  "config": {
    "deck": {
      "_resource_child_name": "deck",
      "_resource_type": "unilabos.devices.liquid_handling.laiyu.laiyu:TransformXYZDeck",
      "name": "deck"
    },
    "backend": {
      "type": "UniLiquidHandlerLaiyuBackend",
      "port": "COM8"
    },
    "simulator": false,
    "total_height": 232.5
  }
}
```

模拟模式节点的关键配置形如：

```json
{
  "backend": {
    "type": "UniLiquidHandlerRvizBackend"
  },
  "simulator": true,
  "total_height": 300,
  "joint_config": "TransformXYZDeck",
  "simulate_rviz": true
}
```

运行示例：

```bash
unilab --graph unilabos/test/experiments/test_laiyu_v.json --backend simple --visual rviz
```

真实硬件运行前需要确认串口号、设备供电、RS485 地址、运动范围和安全高度。

## 台面配置 `deckconfig.json`

`config/deckconfig.json` 是铼羽台面几何配置文件，包含：

- 台面尺寸和坐标系：左上角原点，X 向右，Y 向下，Z 向上，单位 mm
- 8 管位置模块
- 96 深孔板
- 敞口玻璃瓶固定座
- 96 枪头盒
- 每个孔位/枪头位的坐标、尺寸、体积、形状
- 安全边距和校准点

需要注意：当前 `core/laiyu_liquid_res.py` 和 `tests/test_deck_config.py` 中仍有历史路径写法，会尝试读取 `controllers/deckconfig.json` 或 `config/deck.json`。实际文件位于：

```text
unilabos/devices/liquid_handling/laiyu/config/deckconfig.json
```

因此，如果要继续使用 `core/laiyu_liquid_res.py` 的资源创建函数，应先修正其配置加载路径。当前设备图示例则主要通过图文件中的资源节点和位置数据定义台面。

## 直接使用底层控制器

硬件调试时可直接使用控制器或驱动层。示例：

```python
from unilabos.devices.liquid_handling.laiyu.controllers import PipetteController

controller = PipetteController(port="COM8")

if controller.connect():
    controller.initialize()
    # 后续按控制器实际方法执行移液器动作
    controller.disconnect()
```

直接控制 XYZ：

```python
from unilabos.devices.liquid_handling.laiyu.controllers import XYZController

xyz = XYZController(port="COM8", baudrate=115200)
xyz.connect_device()
xyz.home_all_axes()
xyz.move_to_work_coord_safe(x=0, y=-150, z=0)
xyz.disconnect_device()
```

底层驱动可从 `drivers` 包导入：

```python
from unilabos.devices.liquid_handling.laiyu.drivers import SOPAPipette, SOPAConfig

config = SOPAConfig(port="COM8", address=4, baudrate=115200)
pipette = SOPAPipette(config)
pipette.connect()
pipette.initialize()
pipette.disconnect()
```

## 已知注意事项

- `unilabos/devices/liquid_handling/laiyu/__init__.py` 当前为空，不应从 `unilabos.devices.liquid_handling.laiyu` 直接导入公开 API。
- 旧文档中的 `unilabos.devices.laiyu_liquid` 路径当前不存在。
- `backend/__init__.py` 当前只导出 `UniLiquidHandlerLaiyuBackend`，未导出 `create_laiyu_backend`。
- `backend/laiyu_backend.py` 是早期模拟后端，当前主路径使用 `laiyu_v_backend.py`。
- `TransformXYZHandler` 中多个动作方法是空实现，实际行为需结合 `LiquidHandlerAbstract` 和后端调用链验证。
- `drop_tips()` 中 `self.hardware_interface.eject_tip` 当前看起来只是属性访问，若退枪头动作不生效，需要检查是否应改为方法调用。
- 真实硬件运行前必须校验 `total_height`、枪头长度、资源坐标和安全 Z 高度，否则存在撞机风险。

## 维护建议

后续维护建议优先处理以下问题：

1. 统一 `deckconfig.json` 的加载路径，避免资源层和测试脚本读取不到当前配置。
2. 明确 `TransformXYZHandler` 与 `UniLiquidHandlerLaiyuBackend` 的职责边界，删除或标注早期未使用入口。
3. 补充真实硬件动作的最小集成测试，至少覆盖取枪头、吸液、排液、丢枪头的后端调用链。
4. 将图文件中的铼羽资源坐标与 `deckconfig.json` 的台面坐标建立明确关系，避免同一台面维护两套坐标来源。
