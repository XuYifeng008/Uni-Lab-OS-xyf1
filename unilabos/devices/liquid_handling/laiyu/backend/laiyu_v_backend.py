      
import json
from typing import List, Optional, Union

from pylabrobot.liquid_handling.backends.backend import (
  LiquidHandlerBackend,
)
from pylabrobot.liquid_handling.standard import (
  Drop,
  DropTipRack,
  MultiHeadAspirationContainer,
  MultiHeadAspirationPlate,
  MultiHeadDispenseContainer,
  MultiHeadDispensePlate,
  Pickup,
  PickupTipRack,
  ResourceDrop,
  ResourceMove,
  ResourcePickup,
  SingleChannelAspiration,
  SingleChannelDispense,
)
from pylabrobot.resources import Resource, Tip

import rclpy
from rclpy.node import Node
from sensor_msgs.msg import JointState
import time
from rclpy.action import ActionClient
from unilabos_msgs.action import SendCmd
import re
import logging

from unilabos.devices.ros_dev.liquid_handler_joint_publisher import JointStatePublisher
from unilabos.devices.liquid_handling.laiyu.controllers.pipette_controller import PipetteController, TipStatus

logger = logging.getLogger(__name__)


class UniLiquidHandlerLaiyuBackend(LiquidHandlerBackend):
  """Chatter box backend for device-free testing. Prints out all operations."""

  # GreenLab 孔位 Z 偏移（工作坐标：safe_z≈0 为最高，数值越大枪头越低）
  # source(吸液) 比 target(排液) 再低 30mm；占位值，现场可再标定
  _greenlab_wells = {f"module_5_GreenLab_P{i}" for i in range(1, 7)}
  _greenlab_aspirate_z_offset_mm = -15.0  # GreenLab 为 source：枪头更深
  _greenlab_dispense_z_offset_mm = -50.0   # GreenLab 为 target：相对吸液浅 30mm
  _default_flow_rate = 2000
  _min_flow_rate = 100
  _max_flow_rate = 2000

  _pip_length = 5
  _vol_length = 8
  _resource_length = 20
  _offset_length = 16
  _flow_rate_length = 10
  _blowout_length = 10
  _lld_z_length = 10
  _kwargs_length = 15
  _tip_type_length = 12
  _max_volume_length = 16
  _fitting_depth_length = 20
  _tip_length_length = 16
  # _pickup_method_length = 20
  _filter_length = 10

  def __init__(
    self,
    num_channels: int = 8,
    tip_length: float = 96.0,
    total_height: float = 259.0,
    # ===== 串口配置（修改这里）=====
    # port 是 SOPA 移液器串口；xyz_port 是 XYZ 三轴串口。
    # 不填 xyz_port 时保持旧逻辑，XYZ 与 SOPA 共用 port。
    port: str = "/dev/ttyUSB0",
    address: int = 4,
    baudrate: int = 115200,
    timeout: float = 5.0,
    xyz_port: Optional[str] = None,
    xyz_baudrate: Optional[int] = None,
    xyz_timeout: Optional[float] = None,
  ):
    """Initialize a chatter box backend."""
    super().__init__()
    self._num_channels = num_channels
    self.tip_length = tip_length
    self.total_height = total_height
# rclpy.init()
    if not rclpy.ok():
        rclpy.init()
    self.joint_state_publisher = None
    self.hardware_interface = PipetteController(
      port=port,
      address=address,
      baudrate=baudrate,
      timeout=timeout,
      xyz_port=xyz_port,
      xyz_baudrate=xyz_baudrate,
      xyz_timeout=xyz_timeout,
    )

  async def setup(self):
    # self.joint_state_publisher = JointStatePublisher()
    # self.hardware_interface.xyz_controller.connect_device()
    # self.hardware_interface.xyz_controller.home_all_axes()
    await super().setup()
    self.hardware_interface.connect()
    self.hardware_interface.initialize()

    print("Setting up the liquid handler.")

  async def stop(self):
    print("Stopping the liquid handler.")

  def serialize(self) -> dict:
    return {**super().serialize(), "num_channels": self.num_channels}

  @classmethod
  def _normalize_flow_rate(cls, flow_rate: Optional[float]) -> int:
    if flow_rate is None:
      return cls._default_flow_rate
    return int(min(max(flow_rate, cls._min_flow_rate), cls._max_flow_rate))

  def pipette_aspirate(self, volume: float, flow_rate: Optional[float] = None):

    self.hardware_interface.pipette.set_max_speed(self._normalize_flow_rate(flow_rate))
    res = self.hardware_interface.pipette.aspirate(volume=volume)
    
    if not res:
        logger.error(f"吸取失败，当前体积: {self.hardware_interface.current_volume}")
        return

    self.hardware_interface.current_volume += volume 

  def pipette_dispense(self, volume: float, flow_rate: Optional[float] = None):

    self.hardware_interface.pipette.set_max_speed(self._normalize_flow_rate(flow_rate))
    res = self.hardware_interface.pipette.dispense(volume=volume)
    if not res:
        logger.error(f"排液失败，当前体积: {self.hardware_interface.current_volume}")
        return
    self.hardware_interface.current_volume -= volume

  @property
  def num_channels(self) -> int:
    return self._num_channels

  async def assigned_resource_callback(self, resource: Resource):
    print(f"Resource {resource.name} was assigned to the liquid handler.")

  async def unassigned_resource_callback(self, name: str):
    print(f"Resource {name} was unassigned from the liquid handler.")

  @classmethod
  def _is_greenlab_well(cls, resource: Resource) -> bool:
    return resource.name in cls._greenlab_wells

  @classmethod
  def _greenlab_z_offset(cls, resource: Resource, role: str) -> float:
    """按 GreenLab 作为 source/target 返回 Z 偏移。

    role: \"aspirate\"（source，更深）或 \"dispense\"（target，较浅）
    """
    if not cls._is_greenlab_well(resource):
      return 0.0
    if role == "aspirate":
      return cls._greenlab_aspirate_z_offset_mm
    return cls._greenlab_dispense_z_offset_mm

  async def pick_up_tips(self, ops: List[Pickup], use_channels: List[int], **backend_kwargs):
    print("Picking up tips:")
    # print(ops.tip)
    header = (
      f"{'pip#':<{UniLiquidHandlerLaiyuBackend._pip_length}} "
      f"{'resource':<{UniLiquidHandlerLaiyuBackend._resource_length}} "
      f"{'offset':<{UniLiquidHandlerLaiyuBackend._offset_length}} "
      f"{'tip type':<{UniLiquidHandlerLaiyuBackend._tip_type_length}} "
      f"{'max volume (µL)':<{UniLiquidHandlerLaiyuBackend._max_volume_length}} "
      f"{'fitting depth (mm)':<{UniLiquidHandlerLaiyuBackend._fitting_depth_length}} "
      f"{'tip length (mm)':<{UniLiquidHandlerLaiyuBackend._tip_length_length}} "
      # f"{'pickup method':<{ChatterboxBackend._pickup_method_length}} "
      f"{'filter':<{UniLiquidHandlerLaiyuBackend._filter_length}}"
    )
    # print(header)

    for op, channel in zip(ops, use_channels):
      offset = f"{round(op.offset.x, 1)},{round(op.offset.y, 1)},{round(op.offset.z, 1)}"
      row = (
        f"  p{channel}: "
        f"{op.resource.name[-30:]:<{UniLiquidHandlerLaiyuBackend._resource_length}} "
        f"{offset:<{UniLiquidHandlerLaiyuBackend._offset_length}} "
        f"{op.tip.__class__.__name__:<{UniLiquidHandlerLaiyuBackend._tip_type_length}} "
        f"{op.tip.maximal_volume:<{UniLiquidHandlerLaiyuBackend._max_volume_length}} "
        f"{op.tip.fitting_depth:<{UniLiquidHandlerLaiyuBackend._fitting_depth_length}} "
        f"{op.tip.total_tip_length:<{UniLiquidHandlerLaiyuBackend._tip_length_length}} "
        # f"{str(op.tip.pickup_method)[-20:]:<{ChatterboxBackend._pickup_method_length}} "
        f"{'Yes' if op.tip.has_filter else 'No':<{UniLiquidHandlerLaiyuBackend._filter_length}}"
      )
      # print(row)
      # print(op.resource.get_absolute_location())
    
    self.tip_length = ops[0].tip.total_tip_length
    coordinate = ops[0].resource.get_absolute_location(x="c",y="c")
    offset_xyz = ops[0].offset
    x = coordinate.x + offset_xyz.x
    y = coordinate.y + offset_xyz.y
    # z = self.total_height - (coordinate.z + self.tip_length) + offset_xyz.z
    z = self.total_height - (coordinate.z) + offset_xyz.z
    # print("moving")
    self.hardware_interface._update_tip_status()
    if self.hardware_interface.tip_status == TipStatus.TIP_ATTACHED:
        print("已有枪头，无需重复拾取")
        return
    self.hardware_interface.xyz_controller.move_to_work_coord_safe(x=x, y=-y, z=z,speed=300)
    try:
        if not self.hardware_interface.pickup_tip():
            raise RuntimeError("取枪头失败：硬件未检测到已装枪头")
    finally:
        self.hardware_interface.xyz_controller.move_to_work_coord_safe(z=self.hardware_interface.xyz_controller.machine_config.safe_z_height,speed=200)
    # self.joint_state_publisher.send_resource_action(ops[0].resource.name, x, y, z, "pick",channels=use_channels)
    #   goback()




  async def drop_tips(self, ops: List[Drop], use_channels: List[int], **backend_kwargs):
    print("Dropping tips:")
    header = (
      f"{'pip#':<{UniLiquidHandlerLaiyuBackend._pip_length}} "
      f"{'resource':<{UniLiquidHandlerLaiyuBackend._resource_length}} "
      f"{'offset':<{UniLiquidHandlerLaiyuBackend._offset_length}} "
      f"{'tip type':<{UniLiquidHandlerLaiyuBackend._tip_type_length}} "
      f"{'max volume (µL)':<{UniLiquidHandlerLaiyuBackend._max_volume_length}} "
      f"{'fitting depth (mm)':<{UniLiquidHandlerLaiyuBackend._fitting_depth_length}} "
      f"{'tip length (mm)':<{UniLiquidHandlerLaiyuBackend._tip_length_length}} "
      # f"{'pickup method':<{ChatterboxBackend._pickup_method_length}} "
      f"{'filter':<{UniLiquidHandlerLaiyuBackend._filter_length}}"
    )
    # print(header)

    for op, channel in zip(ops, use_channels):
      offset = f"{round(op.offset.x, 1)},{round(op.offset.y, 1)},{round(op.offset.z, 1)}"
      row = (
        f"  p{channel}: "
        f"{op.resource.name[-30:]:<{UniLiquidHandlerLaiyuBackend._resource_length}} "
        f"{offset:<{UniLiquidHandlerLaiyuBackend._offset_length}} "
        f"{op.tip.__class__.__name__:<{UniLiquidHandlerLaiyuBackend._tip_type_length}} "
        f"{op.tip.maximal_volume:<{UniLiquidHandlerLaiyuBackend._max_volume_length}} "
        f"{op.tip.fitting_depth:<{UniLiquidHandlerLaiyuBackend._fitting_depth_length}} "
        f"{op.tip.total_tip_length:<{UniLiquidHandlerLaiyuBackend._tip_length_length}} "
        # f"{str(op.tip.pickup_method)[-20:]:<{ChatterboxBackend._pickup_method_length}} "
        f"{'Yes' if op.tip.has_filter else 'No':<{UniLiquidHandlerLaiyuBackend._filter_length}}"
      )
      # print(row)

    coordinate = ops[0].resource.get_absolute_location(x="c",y="c")
    offset_xyz = ops[0].offset
    x = coordinate.x + offset_xyz.x
    y = coordinate.y + offset_xyz.y
    z = self.total_height - (coordinate.z + self.tip_length) + offset_xyz.z -20
    # print(x, y, z)
    # print("moving")
    self.hardware_interface._update_tip_status()
    if self.hardware_interface.tip_status == TipStatus.NO_TIP:
        print("无枪头，无需丢弃")
        return
    self.hardware_interface.xyz_controller.move_to_work_coord_safe(x=x, y=-y, z=z,speed=300)
    try:
        if not self.hardware_interface.eject_tip():
            raise RuntimeError("丢弃枪头失败：硬件未确认枪头已弹出")
    finally:
        self.hardware_interface.xyz_controller.move_to_work_coord_safe(z=self.hardware_interface.xyz_controller.machine_config.safe_z_height)  

  async def aspirate(
    self,
    ops: List[SingleChannelAspiration],
    use_channels: List[int],
    **backend_kwargs,
  ):
    print("Aspirating:")
    header = (
      f"{'pip#':<{UniLiquidHandlerLaiyuBackend._pip_length}} "
      f"{'vol(ul)':<{UniLiquidHandlerLaiyuBackend._vol_length}} "
      f"{'resource':<{UniLiquidHandlerLaiyuBackend._resource_length}} "
      f"{'offset':<{UniLiquidHandlerLaiyuBackend._offset_length}} "
      f"{'flow rate':<{UniLiquidHandlerLaiyuBackend._flow_rate_length}} "
      f"{'blowout':<{UniLiquidHandlerLaiyuBackend._blowout_length}} "
      f"{'lld_z':<{UniLiquidHandlerLaiyuBackend._lld_z_length}}  "
      # f"{'liquids':<20}" # TODO: add liquids
    )
    for key in backend_kwargs:
      header += f"{key:<{UniLiquidHandlerLaiyuBackend._kwargs_length}} "[-16:]
    # print(header)

    for o, p in zip(ops, use_channels):
      offset = f"{round(o.offset.x, 1)},{round(o.offset.y, 1)},{round(o.offset.z, 1)}"
      row = (
        f"  p{p}: "
        f"{o.volume:<{UniLiquidHandlerLaiyuBackend._vol_length}} "
        f"{o.resource.name[-20:]:<{UniLiquidHandlerLaiyuBackend._resource_length}} "
        f"{offset:<{UniLiquidHandlerLaiyuBackend._offset_length}} "
        f"{str(o.flow_rate):<{UniLiquidHandlerLaiyuBackend._flow_rate_length}} "
        f"{str(o.blow_out_air_volume):<{UniLiquidHandlerLaiyuBackend._blowout_length}} "
        f"{str(o.liquid_height):<{UniLiquidHandlerLaiyuBackend._lld_z_length}} "
        # f"{o.liquids if o.liquids is not None else 'none'}"
      )
      for key, value in backend_kwargs.items():
        if isinstance(value, list) and all(isinstance(v, bool) for v in value):
          value = "".join("T" if v else "F" for v in value)
        if isinstance(value, list):
          value = "".join(map(str, value))
        row += f" {value:<15}"
      # print(row)
    coordinate = ops[0].resource.get_absolute_location(x="c",y="c")
    offset_xyz = ops[0].offset
    x = coordinate.x + offset_xyz.x
    y = coordinate.y + offset_xyz.y
    z = self.total_height - (coordinate.z + self.tip_length) + offset_xyz.z
    z += self._greenlab_z_offset(ops[0].resource, "aspirate")
    # print(x, y, z)
    # print("moving")

    # 判断枪头是否存在
    if not self.hardware_interface.tip_status == TipStatus.TIP_ATTACHED:
        raise RuntimeError("无枪头，无法吸液")
    # 判断吸液量是否超过枪头容量
    flow_rate = self._normalize_flow_rate(backend_kwargs.get("flow_rate"))
    # PyLabRobot 将 blow_out_air_volume 写入 op，而非 backend_kwargs
    blow_out_air_volume = ops[0].blow_out_air_volume if ops[0].blow_out_air_volume is not None else 0
    if self.hardware_interface.current_volume + ops[0].volume + blow_out_air_volume > self.hardware_interface.max_volume:
        logger.error(f"吸液量超过枪头容量: {self.hardware_interface.current_volume + ops[0].volume} > {self.hardware_interface.max_volume}")
        return

    # 移动到吸液位置
    self.hardware_interface.xyz_controller.move_to_work_coord_safe(x=x, y=-y, z=z,speed=300)
    self.pipette_aspirate(volume=ops[0].volume, flow_rate=flow_rate)


    self.hardware_interface.xyz_controller.move_to_work_coord_safe(z=self.hardware_interface.xyz_controller.machine_config.safe_z_height)
    if blow_out_air_volume >0: 
        self.pipette_aspirate(volume=blow_out_air_volume, flow_rate=flow_rate)




  async def dispense(
    self,
    ops: List[SingleChannelDispense],
    use_channels: List[int],
    **backend_kwargs,
  ):
    # print("Dispensing:")
    header = (
      f"{'pip#':<{UniLiquidHandlerLaiyuBackend._pip_length}} "
      f"{'vol(ul)':<{UniLiquidHandlerLaiyuBackend._vol_length}} "
      f"{'resource':<{UniLiquidHandlerLaiyuBackend._resource_length}} "
      f"{'offset':<{UniLiquidHandlerLaiyuBackend._offset_length}} "
      f"{'flow rate':<{UniLiquidHandlerLaiyuBackend._flow_rate_length}} "
      f"{'blowout':<{UniLiquidHandlerLaiyuBackend._blowout_length}} "
      f"{'lld_z':<{UniLiquidHandlerLaiyuBackend._lld_z_length}}  "
      # f"{'liquids':<20}" # TODO: add liquids
    )
    for key in backend_kwargs:
      header += f"{key:<{UniLiquidHandlerLaiyuBackend._kwargs_length}} "[-16:]
    # print(header)

    for o, p in zip(ops, use_channels):
      offset = f"{round(o.offset.x, 1)},{round(o.offset.y, 1)},{round(o.offset.z, 1)}"
      row = (
        f"  p{p}: "
        f"{o.volume:<{UniLiquidHandlerLaiyuBackend._vol_length}} "
        f"{o.resource.name[-20:]:<{UniLiquidHandlerLaiyuBackend._resource_length}} "
        f"{offset:<{UniLiquidHandlerLaiyuBackend._offset_length}} "
        f"{str(o.flow_rate):<{UniLiquidHandlerLaiyuBackend._flow_rate_length}} "
        f"{str(o.blow_out_air_volume):<{UniLiquidHandlerLaiyuBackend._blowout_length}} "
        f"{str(o.liquid_height):<{UniLiquidHandlerLaiyuBackend._lld_z_length}} "
        # f"{o.liquids if o.liquids is not None else 'none'}"
      )
      for key, value in backend_kwargs.items():
        if isinstance(value, list) and all(isinstance(v, bool) for v in value):
          value = "".join("T" if v else "F" for v in value)
        if isinstance(value, list):
          value = "".join(map(str, value))
        row += f" {value:<{UniLiquidHandlerLaiyuBackend._kwargs_length}}"
      # print(row)
    coordinate = ops[0].resource.get_absolute_location(x="c",y="c")
    offset_xyz = ops[0].offset
    x = coordinate.x + offset_xyz.x
    y = coordinate.y + offset_xyz.y
    z = self.total_height - (coordinate.z + self.tip_length) + offset_xyz.z
    z += self._greenlab_z_offset(ops[0].resource, "dispense")
    # print(x, y, z)
    # print("moving")

    # 判断枪头是否存在
    if not self.hardware_interface.tip_status == TipStatus.TIP_ATTACHED:
        raise RuntimeError("无枪头，无法排液")
    # 判断排液量是否超过枪头容量
    flow_rate = self._normalize_flow_rate(backend_kwargs.get("flow_rate"))
    # PyLabRobot 将 blow_out_air_volume 写入 op，而非 backend_kwargs
    blow_out_air_volume = ops[0].blow_out_air_volume if ops[0].blow_out_air_volume is not None else 0
    if self.hardware_interface.current_volume - ops[0].volume - blow_out_air_volume < 0:
        logger.error(f"排液量超过枪头容量: {self.hardware_interface.current_volume - ops[0].volume - blow_out_air_volume} < 0")
        return

    
    # 移动到排液位置  
    self.hardware_interface.xyz_controller.move_to_work_coord_safe(x=x, y=-y, z=z,speed=300)
    self.pipette_dispense(volume=ops[0].volume, flow_rate=flow_rate)


    self.hardware_interface.xyz_controller.move_to_work_coord_safe(z=self.hardware_interface.xyz_controller.machine_config.safe_z_height)
    if blow_out_air_volume > 0: 
        self.pipette_dispense(volume=blow_out_air_volume, flow_rate=flow_rate)
    # self.joint_state_publisher.send_resource_action(ops[0].resource.name, x, y, z, "",channels=use_channels)

  async def pick_up_tips96(self, pickup: PickupTipRack, **backend_kwargs):
    print(f"Picking up tips from {pickup.resource.name}.")

  async def drop_tips96(self, drop: DropTipRack, **backend_kwargs):
    print(f"Dropping tips to {drop.resource.name}.")

  async def aspirate96(
    self, aspiration: Union[MultiHeadAspirationPlate, MultiHeadAspirationContainer]
  ):
    if isinstance(aspiration, MultiHeadAspirationPlate):
      resource = aspiration.wells[0].parent
    else:
      resource = aspiration.container
    print(f"Aspirating {aspiration.volume} from {resource}.")

  async def dispense96(self, dispense: Union[MultiHeadDispensePlate, MultiHeadDispenseContainer]):
    if isinstance(dispense, MultiHeadDispensePlate):
      resource = dispense.wells[0].parent
    else:
      resource = dispense.container
    print(f"Dispensing {dispense.volume} to {resource}.")

  async def pick_up_resource(self, pickup: ResourcePickup):
    print(f"Picking up resource: {pickup}")

  async def move_picked_up_resource(self, move: ResourceMove):
    print(f"Moving picked up resource: {move}")

  async def drop_resource(self, drop: ResourceDrop):
    print(f"Dropping resource: {drop}")

  def can_pick_up_tip(self, channel_idx: int, tip: Tip) -> bool:
    return True
    
