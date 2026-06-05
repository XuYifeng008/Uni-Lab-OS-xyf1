"""
AI4C 磁搅子设备驱动。

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

from unilabos.registry.decorators import ActionInputHandle, DataSource, action, device, not_action
from unilabos.resources.resource_tracker import JSON_UNILABOS_PARAM, PARAM_SAMPLE_UUIDS
from unilabos.utils.decorator import subscribe
from unilabos.utils.log import logger


NODE_PROCESSING_REQUEST = "Magnetic_Stirrer_Processing_Request"
NODE_SPEED = "Magnetic_Stirrer_Speed_Parameter"
NODE_TEMPERATURE = "Magnetic_Stirrer_Temperature_Parameter"
NODE_TIME = "Magnetic_Stirrer_Time_Parameter"
NODE_PARAMETERS_SENT = "Magnetic_Stirrer_Parameters_Sent"
NODE_PARAMETERS_EXECUTED = "Magnetic_Stirrer_Parameters_Executed"
NODE_PROCESSING_COMPLETE = "Magnetic_Stirrer_Processing_Complete"
NODE_OCCUPIED = "Magnetic_Stirrer_Occupied"
NODE_INITIALIZATION_COMPLETE = "Magnetic_Stirrer_Initialization_Complete"

NODE_LABEL_ZH = {
    NODE_PROCESSING_REQUEST: "磁搅请求加工",
    NODE_SPEED: "磁搅参数速度",
    NODE_TEMPERATURE: "磁搅参数温度",
    NODE_TIME: "磁搅参数时间",
    NODE_PARAMETERS_SENT: "磁搅参数已下发",
    NODE_PARAMETERS_EXECUTED: "磁搅参数已执行",
    NODE_PROCESSING_COMPLETE: "磁搅加工完成",
    NODE_OCCUPIED: "磁搅占位",
    NODE_INITIALIZATION_COMPLETE: "磁搅初始化完成",
}


@device(
    id="AI4C_magnetic_stirrer",
    display_name="AI4C 磁搅",
    category=["workstation", "AI4C"],
    description="AI4C 磁力搅拌子设备，通过 AI4C_plc 转发 PLC 读写",
    icon="AI4C.webp",
)
class AI4CMagneticStirrerDevice:
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
        """ROS 节点就绪后，创建跨设备 PLC 命令客户端。"""
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
    @subscribe("/devices/AI4C_plc/magnetic_stirrer_occupied", msg_type=Bool)
    def on_magnetic_stirrer_occupied(self, msg: Bool) -> None:
        self._set_plc_state("magnetic_stirrer_occupied", bool(msg.data))

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
    def _log_opc_request(self, operation: str, node_name: str, value: Any = None) -> None:
        label_zh = NODE_LABEL_ZH.get(node_name, node_name)
        if operation == "read":
            logger.info(f"正在请求读取 OPC 变量: {node_name} ({label_zh})")
        elif operation == "write":
            logger.info(f"正在请求写入 OPC 变量: {node_name} ({label_zh}) = {value}")
        else:
            logger.info(f"正在请求 OPC 变量({operation}): {node_name} ({label_zh})")

    @not_action
    def _read_plc_variable(self, node_name: str, use_cache: bool = True, log_request: bool = True) -> Any:
        if log_request:
            self._log_opc_request("read", node_name)
        return self._call_plc_command(
            "read_variable",
            {
                "node_name": node_name,
                "use_cache": use_cache,
            },
        )

    @not_action
    def _write_plc_variable(self, node_name: str, value: Any) -> None:
        self._log_opc_request("write", node_name, value)
        self._call_plc_command(
            "write_variable",
            {
                "node_name": node_name,
                "value": value,
            },
        )

    @not_action
    def _read_bool_with_topic_fallback(self, state_key: str, node_name: str) -> bool:
        try:
            self._log_opc_request("read(ROS订阅缓存)", node_name)
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
        state_key: Optional[str] = None,
    ) -> bool:
        desc = description or node_name
        label_zh = NODE_LABEL_ZH.get(node_name, node_name)
        logger.info(f"开始轮询 OPC 变量: {node_name} ({label_zh})，期望={expected}")
        logger.info(f"等待 {desc} 变为 {expected}...")
        start = time.time()
        while True:
            if state_key:
                value = self._read_bool_with_topic_fallback(state_key, node_name)
            else:
                value = bool(self._read_plc_variable(node_name, use_cache=False, log_request=False))

            if value is expected:
                logger.info(f"✓ {desc} 已变为 {expected}")
                label_zh = NODE_LABEL_ZH.get(node_name)
                if label_zh:
                    logger.info(f"{label_zh}步骤已成功")
                return True

            if time.time() - start >= timeout:
                logger.error(f"✗ 等待 {desc} 超时 ({timeout}s)")
                return False

            time.sleep(interval)

    @not_action
    def is_occupied(self) -> bool:
        """磁搅工位是否有孔板。"""
        return self._read_bool_with_topic_fallback("magnetic_stirrer_occupied", NODE_OCCUPIED)

    @not_action
    def is_initialization_complete(self) -> bool:
        """磁搅是否初始化完成。"""
        return bool(self._read_plc_variable(NODE_INITIALIZATION_COMPLETE, use_cache=False))

    @action(
        auto_prefix=True,
        description="触发磁力搅拌",
        handles=[
            ActionInputHandle(
                key="magnetic_stirrer_speed",
                data_type="ai4c_magnetic_stirrer_speed",
                label="搅拌速度",
                data_key="speed",
                data_source=DataSource.HANDLE,
                description="磁力搅拌速度",
            ),
            ActionInputHandle(
                key="magnetic_stirrer_temperature",
                data_type="ai4c_magnetic_stirrer_temperature",
                label="搅拌温度",
                data_key="temperature",
                data_source=DataSource.HANDLE,
                description="磁力搅拌温度",
            ),
            ActionInputHandle(
                key="magnetic_stirrer_minutes",
                data_type="ai4c_magnetic_stirrer_minutes",
                label="搅拌时间",
                data_key="mins",
                data_source=DataSource.HANDLE,
                description="磁力搅拌时间，单位分钟",
            ),
        ],
    )
    def trigger_magnetic_stirrer(self, speed: int = 100, temperature: int = 30, mins: int = 1) -> dict:
        logger.info("触发磁力搅拌...")

        if not self._wait_plc_bool(
            NODE_PROCESSING_REQUEST,
            True,
            description="等待磁力搅拌请求加工信号",
        ):
            return {
                "success": False,
                "message": "等待磁力搅拌请求加工信号超时",
            }

        if not self.is_occupied():
            logger.error("磁力搅拌位置没有孔板")
            return {
                "success": False,
                "message": "磁力搅拌位置没有孔板",
            }
        logger.info(f"{NODE_LABEL_ZH[NODE_OCCUPIED]}步骤已成功")

        self._write_plc_variable(NODE_SPEED, speed)
        self._write_plc_variable(NODE_TEMPERATURE, temperature)
        self._write_plc_variable(NODE_TIME, mins)
        self._write_plc_variable(NODE_PARAMETERS_SENT, True)

        if not self._wait_plc_bool(
            NODE_PARAMETERS_EXECUTED,
            True,
            description="等待搅拌参数已执行",
        ):
            logger.error("搅拌参数执行失败")
            return {
                "success": False,
                "message": "搅拌参数执行失败",
            }

        self._write_plc_variable(NODE_PARAMETERS_SENT, False)
        logger.info("搅拌参数已执行")

        if self._wait_plc_bool(
            NODE_PROCESSING_COMPLETE,
            True,
            description="等待搅拌完成",
            timeout=mins * 60.0 + 100.0,
        ):
            logger.info("搅拌完成")
            return {
                "success": True,
                "message": "搅拌完成",
            }

        logger.error("搅拌失败")
        return {
            "success": False,
            "message": "搅拌失败，动作超时",
        }
