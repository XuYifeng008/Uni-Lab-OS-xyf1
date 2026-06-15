# 2026-06-15 开发与 Debug 日志

## 背景与目标

今天的开发工作主要围绕来煜液体处理器与 GreenLab 电化学反应仪的联动展开，目标是把真实硬件路径从“单设备可调试”推进到“可由 UniLabOS 设备图加载、可在工作流中执行取枪头、移液、排液、丢枪头和电化学反应控制”的状态。

涉及的主要模块包括：

- `unilabos/devices/liquid_handling/laiyu/`：来煜液体处理器入口、真实硬件后端、SOPA 移液器驱动、XYZ 步进电机驱动和电化学台面配置。
- `unilabos/devices/GreenLab/`：GreenLab 电化学反应仪驱动和本地测试脚本。
- `unilabos/registry/devices/greenlab.yaml`：GreenLab 设备注册表与 Action Schema。
- `unilabos/test/experiments/greenlab_electrochem_01.json`：来煜液体处理器 + GreenLab 电化学实验设备图。

截至日志整理时，工作区相关改动规模约为：

- 11 个相关文件发生改动。
- 约 2642 行新增、291 行删除。
- 最大改动集中在 `electro_deck.json` 和 GreenLab 注册表/驱动。

## 今日主要开发内容

### 1. 来煜真实硬件后端接入

对 `backend/laiyu_v_backend.py` 做了硬件执行路径调整，使 PyLabRobot 标准液体处理操作能够落到来煜硬件控制器上。

重点处理了以下动作：

- `pick_up_tips()`：根据枪头资源绝对坐标、offset 和枪头长度计算实际工作坐标，移动到目标枪头位后执行 `pickup_tip()`。
- `drop_tips()`：根据丢枪头资源坐标移动到废弃位置，调用 `eject_tip()`，并在动作完成后抬升到安全高度。
- `aspirate()`：根据液体资源坐标移动到吸液位置，调用 SOPA 吸液动作。
- `dispense()`：根据目标资源坐标移动到排液位置，调用 SOPA 排液动作。

今天重点修正了取枪头和丢枪头后的安全 Z 轴回退逻辑。此前动作失败或异常时，设备可能停留在较低 Z 位，后续移动存在碰撞风险。现在关键动作使用 `try/finally` 保证执行完成后回到 `machine_config.safe_z_height`。

坐标换算中保留了当前来煜台面的坐标约定：

- PyLabRobot 资源坐标以 deck 为基准。
- 来煜工作坐标中 Y 轴方向与资源配置里的 Y 方向相反，因此硬件移动时使用 `y=-y`。
- Z 坐标根据 `total_height - (resource_z + tip_length) + offset_z` 计算。

### 2. `TransformXYZHandler` 适配工作流调用

对 `laiyu.py` 中的 `TransformXYZHandler` 做了更贴近 UniLabOS 工作流调用的封装。

主要变化：

- 支持从图文件中读取 `backend` 字典配置，并按 `type: UniLiquidHandlerLaiyuBackend` 实例化真实后端。
- 支持 `total_height` 透传给真实后端，用于 Z 轴坐标换算。
- 在 `add_liquid()`、`aspirate()`、`dispense()`、`drop_tips()` 等入口中统一处理 `use_channels`、空列表参数和默认 spread。
- 新增 `_normalize_use_channels()`，避免工作流传入空通道列表时直接导致底层动作没有可用通道。
- 新增 `_none_if_empty()`，把空列表参数转换成 `None`，避免上层抽象在 flow rate、offset、liquid height 等可选参数上误判。

这个调整主要解决“工作流 JSON 参数与 PyLabRobot/UniLabOS 抽象层期望不完全一致”的问题，使图文件里的动作参数可以更稳定地下传。

### 3. SOPA 与 XYZ 共用串口问题

今天调试的一个核心问题是 SOPA 移液器与 XYZ 步进电机在真实设备上可能复用同一个 RS485 串口。

问题表现：

- SOPA 指令和 XYZ Modbus RTU 指令使用不同协议。
- 两类设备共用串口时，如果 SOPA 的残留响应还在输入缓冲区，后续 XYZ 读取 Modbus 响应时会读到混合数据。
- 结果可能表现为 CRC 校验失败、响应长度不足、未收到响应或三轴控制偶发失败。

对应修改：

- `sopa_pipette_driver.py` 中为 SOPA 串口通信增加 `threading.RLock()`，便于与 XYZ 控制器共用同一把锁。
- `pipette_controller.py` 中识别 `xyz_port == pipette_port` 的情况，允许 XYZ 控制器复用 SOPA 已打开的串口对象和锁。
- `pipette_controller.py` 新增 `_prepare_xyz_serial_bus()`，在切换到 XYZ Modbus 通信前清理 SOPA 残留响应。
- `xyz_stepper_driver.py` 中新增/加强串口输入缓冲清理、完整 Modbus RTU 帧读取和帧提取逻辑。

`xyz_stepper_driver.py` 当前的处理策略：

- 发送 Modbus 指令前等待输入缓冲区进入安静状态。
- 写入指令后按响应长度读取完整帧，而不是简单读取当前缓冲。
- 从混合数据中查找目标从站地址。
- 根据功能码推断响应长度。
- 使用 CRC 校验确认候选帧是否为合法 Modbus 帧。
- 如果候选帧前存在 SOPA 噪声，则跳过噪声并继续解析。

这个改动是今天真实硬件 debug 的关键点之一，目标是降低共享 RS485 总线下的协议串扰。

### 4. 电化学台面配置

今天新增/扩展了 `config/electro_deck.json`，用于描述来煜电化学实验台面。

配置中包含：

- deck 坐标系：左上角原点，X 向右，Y 向下，Z 向上，单位 mm。
- 模块 1：96 枪头盒。
- 模块 2：12 管试管架。
- 模块 3：30 管 LC 小瓶架。
- 模块 4：3 个 50 mL 大瓶位。
- 模块 5：GreenLab 电化学反应模块。
- 每个模块的尺寸、位置、孔位网格、容量、孔径/深度等几何信息。
- 安全边距、校准点和整体 deck metadata。

同时更新了 `electro_deck.md` 中的零散记录，用于保留手工测量得到的尺寸信息，例如枪头盒尺寸、孔间距、试管架尺寸、LC 小瓶架尺寸和反应器通道相对位置。

这些配置被 `greenlab_electrochem_01.json` 引用，用于生成完整实验设备图。

### 5. GreenLab 电化学反应仪动作封装

今天对 `greenlab_electrochemical.py` 做了较大扩展，使它更适合通过 UniLabOS JSON 工作流调用。

新增/调整内容：

- 新增 `_reaction_parameters`，按通道缓存已经设置的反应参数。
- 新增 `_normalize_enum()`，兼容 Python 枚举、整数和字符串三类参数输入。
- `set_output_mode()`、`set_alternate_mode()`、`set_stirrer()` 支持从工作流 JSON 中传入整数或字符串，而不再只接受 Python 枚举对象。
- 新增 `set_reaction_parameters()`，用于只设置反应参数，不立即打开通道。
- 调整 `start_reaction()`，允许不传完整参数时复用此前保存的通道参数。
- 新增/保留 `stop_reaction()` 和 `end_reaction()`，用于关闭指定通道并可选择停止搅拌。

拆分 `set_reaction_parameters()` 和 `start_reaction()` 的主要原因是工作流中常见的流程是：

1. 先把样品通过来煜液体处理器转移到反应位。
2. 设置 GreenLab 通道参数。
3. 到达正确时机后再打开反应通道。
4. 反应结束后关闭通道和搅拌。

如果参数设置和通道开启绑定在一个动作中，工作流编排时不够清晰，也不利于调试。

### 6. GreenLab 注册表补全

今天新增/补全了 `unilabos/registry/devices/greenlab.yaml`。

重点注册了面向工作流的动作：

- `set_reaction_parameters`：参数设置，不打开通道。
- `start_reaction`：开始反应，可使用已保存参数。
- `end_reaction`：结束反应，关闭通道，并可同时停止搅拌。

注册表中补充了：

- 初始化参数 schema：`port`、`baudrate`、`slave_id`、`timeout`、`rts_toggle`。
- 状态字段：`status`、`is_connected`。
- Action goal 默认值。
- JSON Schema 描述、取值范围和枚举约束。

这部分改动的目标是让 GreenLab 设备能被 UniLabOS 注册表正确发现，并在工作流编辑/执行链路中暴露可用动作。

### 7. 电化学实验图

新增 `unilabos/test/experiments/greenlab_electrochem_01.json`，用于描述来煜液体处理器与 GreenLab 电化学反应仪的组合实验场景。

设备节点包括：

- `liquid_handler`：类为 `liquid_handler.laiyu`，真实硬件后端 `UniLiquidHandlerLaiyuBackend`，串口为 `COM8`。
- `greenlab_1`：类为 `greenlab_electrochemical`，串口为 `COM7`，波特率 `115200`，从站地址 `1`。
- `deck`：`TransformXYZDeck`，挂载来煜电化学台面资源。

图中还包含了来自 `electro_deck.json` 的台面布局信息，例如模块数量、孔位数量、台面使用范围、安全边距和校准点。

## 今日 Debug 记录

### 问题 1：GreenLab 工作流参数类型不匹配

现象：

- 工作流 JSON 中更自然地传入 `mode: 0`、`alternate_mode: 0`、`stirrer_speed: 500` 等普通 JSON 值。
- 原驱动方法偏向接受 Python 枚举对象，例如 `OutputMode.CONSTANT_VOLTAGE`。
- 通过注册表/Action 传参时，枚举对象不会自然出现在 JSON 里，导致参数类型不匹配或驱动内部访问 `.value` / `.name` 时出错。

定位：

- 检查 `set_output_mode()`、`set_alternate_mode()`、`set_stirrer()` 的参数签名和内部实现。
- 发现方法直接使用 `mode.value`、`mode.name`、`control.value` 等枚举属性。
- 工作流侧更适合用整数枚举值和 JSON schema 限制范围。

处理：

- 新增 `_normalize_enum()` 统一转换逻辑。
- 允许输入枚举对象、整数、数字字符串、枚举名字符串。
- 转换失败时写入错误日志并返回失败结果。
- 驱动对外方法签名改为 `Union[Enum, int, str]`。

结果：

- GreenLab 动作可以通过 JSON 传入 `0/1/2` 这类枚举值。
- 注册表 schema 可以直接用 `enum: [0, 1]`、`enum: [0, 1, 2]` 描述。

### 问题 2：参数设置和启动反应耦合

现象：

- 电化学实验流程需要先设置参数，再等待液体处理动作完成，最后启动反应。
- 如果只保留一个 `start_reaction()`，会让“写参数”和“开通道”混在一起。

定位：

- 从实验编排角度看，参数设置和反应启动是两个不同阶段。
- GreenLab 通道参数需要被保存，后续启动时可复用。

处理：

- 新增 `set_reaction_parameters()`。
- 参数设置成功后写入 `_reaction_parameters[channel]`。
- `start_reaction()` 在未显式传入 mode/voltage/current/stirrer_speed 时，从缓存参数中读取。
- 未设置参数且启动时未传 mode 时，返回明确错误：“请先设置反应参数，或在开始反应时传入 mode”。

结果：

- 工作流可以按“加液 -> 设置参数 -> 开始反应 -> 结束反应”拆成清晰节点。
- 反应参数更容易在日志和返回值中追踪。

### 问题 3：来煜后端取枪头/丢枪头后的安全高度

现象：

- 取枪头或丢枪头动作后，如果设备留在较低 Z 位，后续 XY 移动可能扫到枪头盒、试管架或反应模块。
- 真实硬件调试中，安全高度回退比模拟环境更重要。

定位：

- 检查 `pick_up_tips()` 和 `drop_tips()` 的动作顺序。
- 发现动作完成后需要明确抬升，而不是依赖后续动作顺带抬升。

处理：

- 在取枪头和丢枪头动作中加入 `try/finally`。
- 无论 `pickup_tip()` / `eject_tip()` 成功与否，都尝试回到 `machine_config.safe_z_height`。
- 取枪头回退时使用较低速度 `speed=100`，减少硬件冲击。

结果：

- 降低异常路径下设备停留低位的风险。
- 后续调试可以优先观察水平移动和坐标偏差，而不是先处理明显碰撞风险。

### 问题 4：SOPA 和 XYZ 共享 RS485 串口导致响应串扰

现象：

- SOPA 移液器和 XYZ 步进电机共用 `COM8` 时，XYZ Modbus 通信偶发解析失败。
- 失败可能表现为：
  - 未收到响应。
  - 响应长度不足。
  - CRC 校验失败。
  - 读到不属于目标从站的字节。

定位：

- SOPA 协议和 XYZ Modbus RTU 协议混用同一串口。
- 串口输入缓冲区中可能残留 SOPA 响应。
- 原读取逻辑对“混合数据 + 延迟响应”的容错不足。

处理：

- SOPA 驱动增加可重入锁。
- XYZ 控制器复用 SOPA 串口时，也复用 SOPA 的锁。
- 切换到 XYZ 前主动 drain 输入缓冲区。
- XYZ 响应读取从“读一段 bytes”调整为“解析完整 Modbus 帧”。
- 对候选帧做目标地址、功能码、长度、CRC 校验。

结果：

- 共享串口场景下，协议串扰的可恢复性更好。
- Debug 日志中能看到被清理或跳过的噪声数据，后续定位更直接。

### 问题 5：设备图与资源类型映射

现象：

- 最近一次启动日志显示 UniLabOS 注册表可以收集到 `greenlab_electrochemical` 和 `liquid_handler.laiyu`。
- Web 服务和资源同步流程能继续启动。
- 但日志中仍出现 `未知类型 tip_rack` 警告。

定位：

- 该警告来自资源树转换到 PyLabRobot 资源字典的过程。
- 当前电化学实验图中存在大量从台面配置生成的枪头、孔位和模块资源。
- 部分资源类型命名可能还没有完全匹配 UniLabOS 资源转换层支持的类型。

处理：

- 今天主要先保证设备注册、图加载和核心动作链路推进。
- `tip_rack` 类型警告暂未完全闭环，需要后续继续检查资源 registry、container/deck 定义和 `node_to_plr_dict` 映射规则。

当前状态：

- 启动过程已经能走到注册表收集和服务启动。
- 资源类型警告是后续需要重点处理的遗留问题。

## 运行与验证记录

今天产生了多份运行日志，集中在 `unilabos_data/logs/`。最近一次相关启动日志显示：

- HTTPClient 初始化完成，远程地址为 `https://leap-lab.bohrium.com/api/v1`。
- UniLab Registry 完成 devices、device_comms 注册。
- 注册表收集到 `greenlab_electrochemical`。
- 注册表收集到 `liquid_handler.laiyu`。
- Uvicorn 应用启动完成。
- 资源 UUID 被批量设置。
- 仍存在 `未知类型 tip_rack` 警告。

这些信息说明：

- GreenLab 注册表文件已能被发现。
- 来煜液体处理器注册入口仍能被发现。
- 电化学实验图中的资源树可以进入资源处理流程。
- 资源类型映射仍需继续清理。

## 当前文件改动摘要

### 来煜液体处理器

- `laiyu.py`
  - 增强真实后端初始化。
  - 适配 backend dict 配置。
  - 规范化 `use_channels` 和空列表参数。
  - 让 `add_liquid`、`aspirate`、`dispense`、`drop_tips` 更适合工作流调用。

- `backend/laiyu_v_backend.py`
  - 调整取枪头、丢枪头、吸液、排液的硬件坐标执行路径。
  - 增加动作后的安全 Z 回退。
  - 保留打印输出用于硬件 debug。

- `controllers/pipette_controller.py`
  - 支持 SOPA 与 XYZ 复用同一串口。
  - 增加共享串口识别。
  - 增加切换 XYZ 前的串口缓冲清理。

- `drivers/sopa_pipette_driver.py`
  - 增加可重入锁，支持共享串口通信互斥。

- `drivers/xyz_stepper_driver.py`
  - 增强 Modbus RTU 响应读取。
  - 增加输入缓冲清理。
  - 增加混合数据中的合法帧提取。
  - 增强 CRC 错误日志。

- `controllers/coordinate_origin.json`
  - 更新来煜坐标原点/校准信息，用于真实设备坐标换算。

### 电化学台面

- `config/electro_deck.json`
  - 新增/扩展完整电化学台面布局。
  - 包含枪头盒、试管架、LC 小瓶架、大瓶位、GreenLab 反应模块。
  - 包含 deck metadata、安全边距和校准点。

- `config/electro_deck.md`
  - 记录台面测量尺寸、孔间距和物料类型说明。

### GreenLab

- `greenlab_electrochemical.py`
  - 增强 JSON 参数兼容。
  - 增加反应参数缓存。
  - 拆分参数设置、开始反应、结束反应动作。

- `test_greenlab.py`
  - 调整本地测试参数或测试路径，用于配合当前 GreenLab 驱动调试。

- `registry/devices/greenlab.yaml`
  - 新增 GreenLab 设备注册。
  - 补充初始化参数、状态字段和工作流 Action Schema。

### 实验图

- `unilabos/test/experiments/greenlab_electrochem_01.json`
  - 新增来煜液体处理器 + GreenLab 电化学反应仪组合实验图。
  - 配置来煜真实后端串口 `COM8`。
  - 配置 GreenLab 串口 `COM7`。
  - 挂载电化学 deck 资源与模块布局。

## 遗留问题与后续计划

### 1. `tip_rack` 资源类型警告

需要继续确认：

- `tip_rack` 是否应改为已注册的标准资源类型。
- `container.yaml` 或 deck/container 资源定义是否需要新增别名。
- `node_to_plr_dict` 对来煜自定义资源类型的处理是否需要扩展。

建议后续优先解决该问题，因为它会影响工作流动作中资源对象是否能被稳定转换为 PyLabRobot 资源。

### 2. 真实硬件坐标还需要逐点校准

当前坐标逻辑已基本成形，但仍建议在真实设备上逐点验证：

- 枪头盒 A01、H12。
- 12 管架边角孔。
- 30 管架边角孔。
- 3 个 50 mL 大瓶位。
- GreenLab 各反应通道中心点。
- 丢枪头位置。

每个点建议记录：

- 资源配置坐标。
- 计算后的工作坐标。
- 实际移动偏差。
- 是否需要单点 offset 或模块级 offset。

### 3. 共享串口稳定性需要长时间测试

今天已增强共享串口下的帧解析，但仍建议做连续动作压力测试：

- SOPA 查询状态 -> XYZ 移动 -> SOPA 吸液 -> XYZ 移动 -> SOPA 排液。
- 连续循环至少 20-50 次。
- 记录 CRC 失败次数、重试次数和动作耗时。
- 如果仍有偶发失败，考虑增加协议层重试或在 SOPA/XYZ 切换前加入更明确的 bus settle delay。

### 4. GreenLab 真实设备动作需要分级验证

建议按以下顺序验证：

1. 仅连接 GreenLab，读取输出模式寄存器。
2. 设置输出模式为恒压。
3. 设置单通道电压但不打开通道。
4. 调用 `set_reaction_parameters()`。
5. 调用 `start_reaction()` 打开一个空载或安全负载通道。
6. 调用 `end_reaction()` 关闭通道。
7. 验证搅拌启停。

不要直接从完整实验图开始长时间反应，先把单动作验证闭环。

### 5. 文档和示例仍需同步

后续建议补充：

- `docs/readme.md` 中加入 `greenlab_electrochem_01.json` 的运行示例。
- 单独写一份“来煜 + GreenLab 电化学实验调试 SOP”。
- 把串口参数、坐标系、校准步骤和常见错误整理成 checklist。

## 今日结论

今天的主要进展是把来煜液体处理器真实硬件路径、GreenLab 电化学反应动作和电化学台面设备图串到了同一条开发线上。代码层面已经补齐了工作流参数适配、GreenLab Action Schema、来煜后端安全移动、SOPA/XYZ 共享串口互斥和 Modbus 帧解析。

当前还不能认为整套实验完全闭环。最重要的后续风险是资源类型映射警告、真实硬件坐标校准和共享串口长时间稳定性。下一步建议优先解决 `tip_rack` 资源类型警告，然后按单点硬件动作逐步验证完整实验流程。
