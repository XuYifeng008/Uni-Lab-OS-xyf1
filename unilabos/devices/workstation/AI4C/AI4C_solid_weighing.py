"""
AI4C 固态称量子设备驱动。

通过 AI4C_plc 设备转发所有 PLC I/O：
- 状态通过订阅 AI4C_plc 发布的 ROS topic 缓存到本地
- 写操作和阻塞等待通过 _execute_driver_command action 调用 AI4C_plc.read_variable / write_variable
"""

import json
import threading
import time
from typing import Any, Optional

from rclpy.action import ActionClient
from std_msgs.msg import Bool
from unilabos_msgs.action import StrSingleInput

from unilabos.registry.decorators import ActionInputHandle, DataSource, action, device, not_action, topic_config
from unilabos.resources.resource_tracker import JSON_UNILABOS_PARAM, PARAM_SAMPLE_UUIDS
from unilabos.utils.decorator import subscribe
from unilabos.utils.log import logger


@device(
    id="AI4C_solid_weighing",
    display_name="AI4C 固态称量",
    category=["balance", "AI4C"],
    description="AI4C 固态称量子设备，通过 AI4C_plc 转发 PLC 读写",
    icon="AI4C.webp",
)
class AI4CSolidWeighingDevice:
    def __init__(
        self,
        plc_device_id: str = "AI4C_plc",
        plc_action_timeout: float = 10.0,
        state_max_age: float = 2.0,
        *args,
        **kwargs,
    ):
        self.plc_device_id = plc_device_id
        self.plc_action_timeout = plc_action_timeout
        self.state_max_age = state_max_age
        self._ros_node = None
        self._plc_command_client: Optional[ActionClient] = None
        self._plc_state: dict[str, Any] = {}
        self._plc_state_ts: dict[str, float] = {}
        self._state_lock = threading.RLock()

    @not_action
    def post_init(self, ros_node) -> None:
        """ROS 节点就绪后创建跨设备 action client。"""
        self._ros_node = ros_node
        self._plc_command_client = ActionClient(
            ros_node,
            StrSingleInput,
            f"/devices/{self.plc_device_id}/_execute_driver_command",
            callback_group=ros_node.callback_group,
        )

    # ──────────── 状态缓存工具 ────────────

    @not_action
    def _set_plc_state(self, key: str, value: Any) -> None:
        with self._state_lock:
            self._plc_state[key] = value
            self._plc_state_ts[key] = time.time()

    @not_action
    def _get_plc_state(self, key: str, max_age: Optional[float] = None) -> Any:
        max_age = self.state_max_age if max_age is None else max_age
        with self._state_lock:
            if key not in self._plc_state:
                raise RuntimeError(f"PLC 状态尚未收到: {key}")
            age = time.time() - self._plc_state_ts[key]
            if age > max_age:
                raise RuntimeError(f"PLC 状态已过期: {key}, age={age:.2f}s")
            return self._plc_state[key]

    # ──────────── 订阅回调（@subscribe 装饰器静态注册）────────────

    @not_action
    @subscribe("/devices/AI4C_plc/solid_weighing_occupied", msg_type=Bool)
    def on_solid_weighing_occupied(self, msg: Bool) -> None:
        self._set_plc_state("solid_weighing_occupied", bool(msg.data))

    @not_action
    @subscribe("/devices/AI4C_plc/powder_in_solid_weighing_occupied", msg_type=Bool)
    def on_powder_in_solid_weighing_occupied(self, msg: Bool) -> None:
        self._set_plc_state("powder_in_solid_weighing_occupied", bool(msg.data))

    # ──────────── PLC 通信工具 ────────────

    @not_action
    def _wait_future(self, future, timeout: float, description: str):
        done = threading.Event()
        future.add_done_callback(lambda _future: done.set())
        if not done.wait(timeout):
            raise TimeoutError(f"{description} 超时 ({timeout}s)")
        return future.result()

    @not_action
    def _call_plc_command(self, function_name: str, function_args: dict[str, Any]) -> Any:
        if self._plc_command_client is None:
            raise RuntimeError("AI4C_plc action client 尚未初始化")

        if not self._plc_command_client.wait_for_server(timeout_sec=self.plc_action_timeout):
            raise TimeoutError(f"等待 AI4C_plc 命令服务超时: {self.plc_device_id}")

        command = {
            "function_name": function_name,
            "function_args": function_args,
            JSON_UNILABOS_PARAM: {PARAM_SAMPLE_UUIDS: {}},
        }
        goal = StrSingleInput.Goal()
        goal.string = json.dumps(command, ensure_ascii=False)

        goal_handle = self._wait_future(
            self._plc_command_client.send_goal_async(goal),
            self.plc_action_timeout,
            f"发送 PLC 命令 {function_name}",
        )
        if not goal_handle.accepted:
            raise RuntimeError(f"AI4C_plc 拒绝执行命令: {function_name}")

        result_wrapper = self._wait_future(
            goal_handle.get_result_async(),
            self.plc_action_timeout,
            f"等待 PLC 命令 {function_name} 返回",
        )
        result = result_wrapper.result
        result_info = json.loads(result.return_info or "{}")
        if not result.success or not result_info.get("suc", False):
            raise RuntimeError(result_info.get("error") or f"AI4C_plc 命令失败: {function_name}")
        return result_info.get("return_value")

    @not_action
    def _read_plc_variable(self, node_name: str, use_cache: bool = True) -> Any:
        return self._call_plc_command(
            "read_variable",
            {"node_name": node_name, "use_cache": use_cache},
        )

    @not_action
    def _write_plc_variable(self, node_name: str, value: Any) -> None:
        self._call_plc_command(
            "write_variable",
            {"node_name": node_name, "value": value},
        )

    @not_action
    def _read_bool_with_topic_fallback(self, state_key: str, node_name: str) -> bool:
        try:
            return bool(self._get_plc_state(state_key))
        except RuntimeError:
            logger.warning(f"订阅状态不可用，改为强制读取 PLC 节点: {node_name}")
            return bool(self._read_plc_variable(node_name, use_cache=False))

    @not_action
    def _wait_plc_bool(
        self,
        node_name: str,
        expected: bool,
        timeout: float = 300.0,
        interval: float = 0.2,
        description: str = None,
    ) -> bool:
        desc = description or node_name
        logger.info(f"等待 {desc} 变为 {expected}...")
        start = time.time()
        while True:
            if bool(self._read_plc_variable(node_name, use_cache=False)) is expected:
                logger.info(f"✓ {desc} 已变为 {expected}")
                return True
            if time.time() - start >= timeout:
                logger.error(f"✗ 等待 {desc} 超时 ({timeout}s)")
                return False
            time.sleep(interval)

    # ──────────── 状态查询 ────────────

    @not_action
    def is_solid_weighing_occupied(self) -> bool:
        return self._read_bool_with_topic_fallback(
            "solid_weighing_occupied", "Solid_Weighing_Occupied"
        )

    @not_action
    def is_powder_in_solid_weighing_occupied(self) -> bool:
        return self._read_bool_with_topic_fallback(
            "powder_in_solid_weighing_occupied", "Powder_In_Solid_Weighing_Occupied"
        )

    # ──────────── 状态 topic（供 Leap Lab 展示和其他设备订阅）────────────

    @topic_config(period=2.0)
    def solid_weighing_occupied(self) -> Optional[bool]:
        """固态称量台是否已有孔板（来自 PLC topic 订阅缓存）。"""
        try:
            return bool(self._get_plc_state("solid_weighing_occupied"))
        except RuntimeError:
            return None

    @topic_config(period=2.0)
    def powder_in_solid_weighing_occupied(self) -> Optional[bool]:
        """固态称量台是否已有粉桶（来自 PLC topic 订阅缓存）。"""
        try:
            return bool(self._get_plc_state("powder_in_solid_weighing_occupied"))
        except RuntimeError:
            return None

    # ──────────── actions ────────────

    @action(auto_prefix=True, description="步骤3/9：打开固态称量门")
    def open_solid_weighing_door(self) -> dict:
        logger.info("打开固态称重门...")
        self._write_plc_variable("Solid_Weighing_Close_Door", False)
        self._write_plc_variable("Solid_Weighing_Open_Door", True)
        if self._wait_plc_bool(
            "Solid_Weighing_Open_Door_Complete", True, description="固态称重门打开完成"
        ):
            return {"success": True, "message": "固态称重门打开完成"}
        logger.error("固态称重门打开超时")
        return {"success": False, "message": "固态称重门打开超时"}

    @action(auto_prefix=True, description="步骤7/13：关闭固态称量门")
    def close_solid_weighing_door(self) -> dict:
        logger.info("关闭固态称重门...")
        self._write_plc_variable("Solid_Weighing_Open_Door", False)
        self._write_plc_variable("Solid_Weighing_Close_Door", True)
        if self._wait_plc_bool(
            "Solid_Weighing_Close_Door_Complete", True, description="固态称重门关闭完成"
        ):
            return {"success": True, "message": "固态称重门关闭完成"}
        logger.error("固态称重门关闭超时")
        return {"success": False, "message": "固态称重门关闭超时"}

    @action(
        auto_prefix=True,
        description="步骤8：触发固态称量",
        handles=[
            ActionInputHandle(
                key="solid_weighing_gram",
                data_type="ai4c_solid_weighing_gram",
                label="称重目标值",
                data_key="gram",
                data_source=DataSource.HANDLE,
                description="固体称量目标值（克）",
            ),
            ActionInputHandle(
                key="solid_weighing_tolerance",
                data_type="ai4c_solid_weighing_tolerance",
                label="称重误差",
                data_key="tolerance",
                data_source=DataSource.HANDLE,
                description="固体称量允许误差（克）",
            ),
            ActionInputHandle(
                key="solid_weighing_slot",
                data_type="ai4c_solid_weighing_slot",
                label="称量槽位",
                data_key="slot",
                data_source=DataSource.HANDLE,
                description="固体称量槽位编号",
            ),
        ],
    )
    def trigger_solid_weighing(
        self, gram: int = 10, tolerance: int = 1, slot: int = 1
    ) -> dict:
        logger.info(f"触发固体称重: gram={gram}, tolerance={tolerance}, slot={slot}")

        if not self.is_solid_weighing_occupied():
            logger.error("固态称重位置没有孔板，无法触发称量")
            return {"success": False, "message": "固态称重位置没有孔板，无法触发称量"}

        if not self.is_powder_in_solid_weighing_occupied():
            logger.error("固态称重位置没有粉桶，无法触发称量")
            return {"success": False, "message": "固态称重位置没有粉桶，无法触发称量"}

        self._write_plc_variable("Solid_Weighing_Weight_in_Grams", gram)
        self._write_plc_variable("Solid_Weighing_Error", tolerance)
        self._write_plc_variable("Solid_Weighing_Slot_Position", slot)
        self._write_plc_variable("Solid_Weighing_Processing_Allowed", True)

        if not self._wait_plc_bool(
            "Solid_Weighing_Processing_Complete", True, description="固体称重完成"
        ):
            self._write_plc_variable("Solid_Weighing_Processing_Allowed", False)
            logger.error("固体称重超时")
            return {"success": False, "message": "固体称重超时"}

        self._write_plc_variable("Solid_Weighing_Processing_Allowed", False)

        if not self._wait_plc_bool(
            "Solid_Weighing_Processing_Complete", False, description="固体称重完成信号复位"
        ):
            logger.error("固体称重完成，但完成信号复位超时")
            return {"success": False, "message": "固体称重完成，但完成信号复位超时"}

        logger.info("固体称重完成")
        return {"success": True, "message": "固体称重完成"}
