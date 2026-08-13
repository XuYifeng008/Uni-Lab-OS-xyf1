import asyncio
import collections
import contextlib
import json
import time
from typing import Any, List, Dict, Optional, TypedDict, Union, Sequence, Iterator, Literal, cast

from pylabrobot.liquid_handling import (
    LiquidHandlerBackend,
    Pickup,
    SingleChannelAspiration,
    Drop,
    SingleChannelDispense,
    PickupTipRack,
    DropTipRack,
    MultiHeadAspirationPlate, ChatterBoxBackend, LiquidHandlerChatterboxBackend,
)
from pylabrobot.liquid_handling.standard import (
    MultiHeadAspirationContainer,
    MultiHeadDispenseContainer,
    MultiHeadDispensePlate,
    ResourcePickup,
    ResourceMove,
    ResourceDrop,
)
from pylabrobot.resources import Tip, Deck, Plate, Well, TipRack, Resource, Container, Coordinate, TipSpot, Trash

from unilabos.devices.liquid_handling.liquid_handler_abstract import (
    LiquidHandlerAbstract,
    TransferLiquidReturn,
)
from unilabos.devices.liquid_handling.rviz_backend import UniLiquidHandlerRvizBackend
from unilabos.devices.liquid_handling.laiyu.backend.laiyu_v_backend import UniLiquidHandlerLaiyuBackend
from unilabos.registry.placeholder_type import ResourceSlot
from unilabos.resources.resource_tracker import ResourceTreeSet



class TransformXYZDeck(Deck):
    """Laiyu 的专用 Deck 类，继承自 Deck。

    该类定义了 Laiyu 的工作台布局和槽位信息。
    """

    def __init__(self, name: str, size_x: float, size_y: float, size_z: float):
        super().__init__(size_x=size_x, size_y=size_y, size_z=size_z, name=name)
        self.name = name

class TransformXYZBackend(LiquidHandlerBackend):
    def __init__(self, name: str, host: str, port: int, timeout: float):
        super().__init__()
        self.host = host
        self.port = port
        self.timeout = timeout

class TransformXYZRvizBackend(UniLiquidHandlerRvizBackend):
    def __init__(self, name: str, channel_num: int):
        super().__init__(channel_num)
        self.name = name


class TransformXYZContainer(Plate, TipRack):
    """Laiyu 的专用 Container 类，继承自 Plate和TipRack。

    该类定义了 Laiyu 的工作台布局和槽位信息。
    """

    def __init__(
        self,
        name: str,
        size_x: float,
        size_y: float,
        size_z: float,
        category: str,
        ordering: collections.OrderedDict,
        model: Optional[str] = None,
    ):
        super().__init__(name, size_x, size_y, size_z, category=category, ordering=ordering, model=model)
        self._unilabos_state = {}

    def load_state(self, state: Dict[str, Any]) -> None:
        """从给定的状态加载工作台信息。"""
        super().load_state(state)
        self._unilabos_state = state

    def serialize_state(self) -> Dict[str, Dict[str, Any]]:
        data = super().serialize_state()
        data.update(self._unilabos_state)
        return data

class TransformXYZHandler(LiquidHandlerAbstract):
    support_touch_tip = False

    def __init__(
        self,
        deck: Deck,
        host: str = "127.0.0.1",
        port: int = 9999,
        timeout: float = 10.0,
        channel_num=1,
        simulator=True,
        backend=None,
        total_height: float = 259.0,
        tip_length: float = 96.0,
        **backend_kwargs
    ):
        # Handle case where deck is passed as a dict (from serialization)
        if isinstance(deck, dict):
            # Try to create a TransformXYZDeck from the dict
            if 'name' in deck and 'size_x' in deck and 'size_y' in deck and 'size_z' in deck:
                deck = TransformXYZDeck(
                    name=deck['name'],
                    size_x=deck.get('size_x', 100),
                    size_y=deck.get('size_y', 100),
                    size_z=deck.get('size_z', 100)
                )
            else:
                # Fallback: create a basic deck
                deck = TransformXYZDeck(name='deck', size_x=100, size_y=100, size_z=100)

        if simulator:
            self._unilabos_backend = TransformXYZRvizBackend(name="laiyu",channel_num=channel_num)
        else:
            if isinstance(backend, dict):
                backend_config = backend.copy()
                backend_type = backend_config.pop("type", "UniLiquidHandlerLaiyuBackend")
                if backend_type != "UniLiquidHandlerLaiyuBackend":
                    raise ValueError(f"Unsupported Laiyu backend type: {backend_type}")
                backend_config.setdefault("total_height", total_height)
                backend_config.setdefault("tip_length", tip_length)
                self._unilabos_backend = UniLiquidHandlerLaiyuBackend(**backend_config)
            elif backend is not None:
                self._unilabos_backend = backend
            else:
                self._unilabos_backend = UniLiquidHandlerLaiyuBackend(
                    port=str(port),
                    timeout=timeout,
                    total_height=total_height,
                    tip_length=tip_length,
                    **backend_kwargs,
                )
        super().__init__(backend=self._unilabos_backend, deck=deck, simulator=simulator, channel_num=channel_num)
        # transfer_liquid 期间为 True：源孔吸液前用待取液体润洗枪头；mix 会临时关闭
        self._pre_wet_on_aspirate = False

    def _normalize_use_channels(self, use_channels: Optional[Sequence[int]]) -> Optional[List[int]]:
        if use_channels is None:
            return None
        channels = list(use_channels)
        if channels:
            return channels
        return list(range(self.channel_num)) if self.channel_num > 0 else [0]

    @staticmethod
    def _none_if_empty(value):
        if value is None:
            return None
        try:
            return None if len(value) == 0 else value
        except TypeError:
            return value

    async def add_liquid(
        self,
        asp_vols: Union[List[float], float],
        dis_vols: Union[List[float], float],
        reagent_sources: Sequence[Container],
        targets: Sequence[Container],
        *,
        use_channels: Optional[List[int]] = None,
        flow_rates: Optional[List[Optional[float]]] = None,
        offsets: Optional[List[Coordinate]] = None,
        liquid_height: Optional[List[Optional[float]]] = None,
        blow_out_air_volume: Optional[List[Optional[float]]] = None,
        spread: Optional[Literal["wide", "tight", "custom"]] = "wide",
        is_96_well: bool = False,
        delays: Optional[List[int]] = None,
        mix_time: Optional[int] = None,
        mix_vol: Optional[int] = None,
        mix_rate: Optional[int] = None,
        mix_liquid_height: Optional[float] = None,
        none_keys: List[str] = [],
    ):
        return await super().add_liquid(
            asp_vols=asp_vols,
            dis_vols=dis_vols,
            reagent_sources=reagent_sources,
            targets=targets,
            use_channels=self._normalize_use_channels(use_channels),
            flow_rates=self._none_if_empty(flow_rates),
            offsets=self._none_if_empty(offsets),
            liquid_height=self._none_if_empty(liquid_height),
            blow_out_air_volume=self._none_if_empty(blow_out_air_volume),
            spread=spread,
            is_96_well=is_96_well,
            delays=delays,
            mix_time=mix_time,
            mix_vol=mix_vol,
            mix_rate=mix_rate,
            mix_liquid_height=mix_liquid_height,
            none_keys=none_keys,
        )

    async def aspirate(
        self,
        resources: Sequence[Container],
        vols: List[float],
        use_channels: Optional[List[int]] = None,
        flow_rates: Optional[List[Optional[float]]] = None,
        offsets: Optional[List[Coordinate]] = None,
        liquid_height: Optional[List[Optional[float]]] = None,
        blow_out_air_volume: Optional[List[Optional[float]]] = None,
        spread: Literal["wide", "tight", "custom"] = "wide",
        **backend_kwargs,
    ):
        if "pre_wet" not in backend_kwargs:
            backend_kwargs["pre_wet"] = self._pre_wet_on_aspirate
        return await super().aspirate(
            resources,
            vols,
            self._normalize_use_channels(use_channels),
            self._none_if_empty(flow_rates),
            self._none_if_empty(offsets),
            self._none_if_empty(liquid_height),
            self._none_if_empty(blow_out_air_volume),
            spread or "wide",
            **backend_kwargs,
        )

    async def dispense(
        self,
        resources: Sequence[Container],
        vols: List[float],
        use_channels: Optional[List[int]] = None,
        flow_rates: Optional[List[Optional[float]]] = None,
        offsets: Optional[List[Coordinate]] = None,
        liquid_height: Optional[List[Optional[float]]] = None,
        blow_out_air_volume: Optional[List[Optional[float]]] = None,
        spread: Literal["wide", "tight", "custom"] = "wide",
        **backend_kwargs,
    ):
        return await super().dispense(
            resources,
            vols,
            self._normalize_use_channels(use_channels),
            self._none_if_empty(flow_rates),
            self._none_if_empty(offsets),
            self._none_if_empty(liquid_height),
            self._none_if_empty(blow_out_air_volume),
            spread or "wide",
            **backend_kwargs,
        )

    async def drop_tips(
        self,
        tip_spots: Sequence[Union[TipSpot, Trash]],
        use_channels: Optional[List[int]] = None,
        offsets: Optional[List[Coordinate]] = None,
        allow_nonzero_volume: bool = False,
        **backend_kwargs,
    ):
        return await super().drop_tips(
            tip_spots,
            self._normalize_use_channels(use_channels),
            self._none_if_empty(offsets),
            allow_nonzero_volume,
            **backend_kwargs,
        )

    async def mix(
        self,
        targets: Sequence[Container],
        mix_time: int = None,
        mix_vol: Optional[int] = None,
        height_to_bottom: Optional[float] = None,
        offsets: Optional[Coordinate] = None,
        mix_rate: Optional[float] = None,
        none_keys: List[str] = [],
    ):
        # mix 内部也走 aspirate/dispense，不能当成「初次吸液」去润洗
        saved = self._pre_wet_on_aspirate
        self._pre_wet_on_aspirate = False
        try:
            return await super().mix(targets, mix_time, mix_vol, height_to_bottom, offsets, mix_rate, none_keys)
        finally:
            self._pre_wet_on_aspirate = saved

    async def pick_up_tips(
        self,
        tip_spots: List[TipSpot],
        use_channels: Optional[List[int]] = None,
        offsets: Optional[List[Coordinate]] = None,
        **backend_kwargs,
    ):
        return await super().pick_up_tips(
            tip_spots,
            self._normalize_use_channels(use_channels),
            self._none_if_empty(offsets),
            **backend_kwargs,
        )

    async def transfer_liquid(
        self,
        sources: Sequence[Container],
        targets: Sequence[Container],
        tip_racks: Sequence[TipRack],
        *,
        use_channels: Optional[List[int]] = None,
        asp_vols: Union[List[float], float],
        dis_vols: Union[List[float], float],
        asp_flow_rates: Optional[List[Optional[float]]] = None,
        dis_flow_rates: Optional[List[Optional[float]]] = None,
        offsets: Optional[List[Coordinate]] = None,
        touch_tip: bool = False,
        liquid_height: Optional[List[Optional[float]]] = None,
        blow_out_air_volume: Optional[List[Optional[float]]] = None,
        spread: Literal["wide", "tight", "custom"] = "wide",
        is_96_well: bool = False,
        mix_stage: Optional[Literal["none", "before", "after", "both"]] = "none",
        mix_times: Optional[List[int]] = None,
        mix_vol: Optional[int] = None,
        mix_rate: Optional[int] = None,
        mix_liquid_height: Optional[float] = None,
        delays: Optional[List[int]] = None,
        none_keys: List[str] = [],
    ):
        if not sources or not targets or asp_vols is None or dis_vols is None:
            return None
        # 每根新枪头的源孔吸液前润洗；mix 已在 mix() 中排除
        self._pre_wet_on_aspirate = True
        try:
            return await super().transfer_liquid(
                sources=sources,
                targets=targets,
                tip_racks=tip_racks,
                use_channels=self._normalize_use_channels(use_channels),
                asp_vols=asp_vols,
                dis_vols=dis_vols,
                asp_flow_rates=self._none_if_empty(asp_flow_rates),
                dis_flow_rates=self._none_if_empty(dis_flow_rates),
                offsets=self._none_if_empty(offsets),
                touch_tip=touch_tip,
                liquid_height=self._none_if_empty(liquid_height),
                blow_out_air_volume=self._none_if_empty(blow_out_air_volume),
                spread=spread,
                is_96_well=is_96_well,
                mix_stage=mix_stage,
                mix_times=mix_times,
                mix_vol=mix_vol,
                mix_rate=mix_rate,
                mix_liquid_height=mix_liquid_height,
                delays=delays,
                none_keys=none_keys,
            )
        finally:
            self._pre_wet_on_aspirate = False

    async def return_tips(
        self,
        use_channels: Optional[List[int]] = None,
        allow_nonzero_volume: bool = False,
        offsets: Optional[List[Coordinate]] = None,
        **backend_kwargs,
    ):
        return await super().return_tips(
            use_channels=self._normalize_use_channels(use_channels),
            allow_nonzero_volume=allow_nonzero_volume,
            offsets=self._none_if_empty(offsets),
            **backend_kwargs,
        )

    async def multi_transfer_reuse_tip(
        self,
        sources: List[ResourceSlot],
        targets: List[ResourceSlot],
        tip_racks: List[ResourceSlot],
        *,
        use_channels: Optional[List[int]] = None,
        volumes: Union[List[float], float],
        offsets: Optional[List[Coordinate]] = None,
        touch_tip: bool = False,
        liquid_height: Optional[List[Optional[float]]] = None,
        blow_out_air_volume: Optional[List[Optional[float]]] = None,
        spread: Literal["wide", "tight", "custom"] = "wide",
        is_96_well: bool = False,
        mix_stage: Optional[Literal["none", "before", "after", "both"]] = "none",
        mix_times: Optional[Union[List[int], int]] = None,
        mix_vol: Optional[int] = None,
        mix_rate: Optional[int] = None,
        mix_liquid_height: Optional[float] = None,
        delays: Optional[List[int]] = None,
        none_keys: List[str] = [],
    ) -> Optional[TransferLiquidReturn]:
        """一根枪头完成多次吸放液，结束后放回取枪头原位。

        volumes[i] 同时作为第 i 次吸液与放液体积；吸/放流速固定为 50。
        sources/targets/tip_racks 需标注 ResourceSlot，以便 JsonCommandAsync 解析为 PLR 实例。
        """
        _ = none_keys
        if is_96_well:
            raise ValueError("multi_transfer_reuse_tip 暂不支持 96 通道模式")
        if not sources or not targets or volumes is None:
            return None

        # JsonCommandAsync 解析后应为 PLR Container / TipRack 实例
        source_containers = cast(Sequence[Container], sources)
        target_containers = cast(Sequence[Container], targets)
        tip_rack_list = cast(Sequence[TipRack], tip_racks)
        if any(isinstance(x, dict) for x in list(source_containers) + list(target_containers) + list(tip_rack_list)):
            raise TypeError(
                "sources/targets/tip_racks 未解析为资源实例（仍为 dict）。"
                "请确认参数类型为 List[ResourceSlot] 且走 UniLabJsonCommandAsync。"
            )

        use_channels = self._normalize_use_channels(use_channels)
        if use_channels is None:
            use_channels = list(range(self.channel_num)) if self.channel_num > 0 else [0]
        if len(use_channels) != 1:
            raise ValueError("multi_transfer_reuse_tip 仅支持单通道（use_channels 长度为 1）")

        offsets = self._none_if_empty(offsets)
        liquid_height = self._none_if_empty(liquid_height)
        blow_out_air_volume = self._none_if_empty(blow_out_air_volume)

        if isinstance(volumes, (int, float)):
            vol_list = [float(volumes)]
        else:
            vol_list = [float(v) for v in volumes]

        if mix_times is not None and not isinstance(mix_times, (int, float)):
            try:
                mix_times = mix_times[0] if len(mix_times) > 0 else None
            except Exception:
                try:
                    mix_times = next(iter(mix_times))
                except Exception:
                    mix_times = None
        if mix_times is not None:
            mix_times = int(mix_times)

        if not tip_rack_list:
            raise ValueError("`tip_racks` 至少需要提供一个 TipRack")
        # 与 transfer_liquid 相同：按 tip_rack 自动取下一个未用枪头
        if not hasattr(self, "current_tip") or getattr(self, "tip_racks", None) != tip_rack_list:
            self.set_tiprack(tip_rack_list)

        num_sources = len(source_containers)
        num_targets = len(target_containers)
        flow_rate = 50.0
        pairs: List[tuple] = []

        if num_sources == 1:
            if len(vol_list) == 1 and num_targets > 1:
                vol_list = vol_list * num_targets
            if len(vol_list) != num_targets:
                raise ValueError(f"`volumes` 长度 {len(vol_list)} 必须与 `targets` 长度 {num_targets} 一致")
            pairs = [(source_containers[0], target_containers[i], vol_list[i]) for i in range(num_targets)]
        elif num_targets == 1 and num_sources > 1:
            if len(vol_list) == 1 and num_sources > 1:
                vol_list = vol_list * num_sources
            if len(vol_list) != num_sources:
                raise ValueError(f"`volumes` 长度 {len(vol_list)} 必须与 `sources` 长度 {num_sources} 一致")
            pairs = [(source_containers[i], target_containers[0], vol_list[i]) for i in range(num_sources)]
        elif num_sources == num_targets:
            if len(vol_list) == 1 and num_targets > 1:
                vol_list = vol_list * num_targets
            if len(vol_list) != num_targets:
                raise ValueError(f"`volumes` 长度 {len(vol_list)} 必须与 `targets` 长度 {num_targets} 一致")
            pairs = [(source_containers[i], target_containers[i], vol_list[i]) for i in range(num_targets)]
        else:
            raise ValueError(
                f"不支持的移液模式: {num_sources} sources -> {num_targets} targets。"
                "支持 1->N、N->1 或 N->N。"
            )

        tip: List[TipSpot] = []
        for _ in range(len(use_channels)):
            next_tip = next(self.current_tip)
            if isinstance(next_tip, TipSpot):
                tip.append(next_tip)
            elif isinstance(next_tip, (list, tuple)):
                tip.extend(next_tip)
            else:
                raise TypeError(f"从 tip_rack 取到的不是 TipSpot: {type(next_tip)} / {next_tip!r}")
        await self.pick_up_tips(tip, use_channels=use_channels)

        try:
            for i, (src, tgt, vol) in enumerate(pairs):
                if mix_stage in ["before", "both"] and mix_times is not None and mix_times > 0:
                    await self.mix(
                        targets=[tgt],
                        mix_time=mix_times,
                        mix_vol=mix_vol,
                        offsets=offsets if offsets else None,
                        height_to_bottom=mix_liquid_height if mix_liquid_height else None,
                        mix_rate=mix_rate if mix_rate else None,
                    )

                await self.aspirate(
                    resources=[src],
                    vols=[vol],
                    use_channels=use_channels,
                    flow_rates=[flow_rate],
                    offsets=[offsets[i]] if offsets and len(offsets) > i else None,
                    liquid_height=[liquid_height[i]] if liquid_height and len(liquid_height) > i else None,
                    blow_out_air_volume=(
                        [blow_out_air_volume[i]] if blow_out_air_volume and len(blow_out_air_volume) > i else None
                    ),
                    spread=spread or "wide",
                    pre_wet=(i == 0),  # 复用枪头：仅第一次吸液前润洗
                )
                await self._custom_delay_if_configured(delays, 0)
                await self.dispense(
                    resources=[tgt],
                    vols=[vol],
                    use_channels=use_channels,
                    flow_rates=[flow_rate],
                    offsets=[offsets[i]] if offsets and len(offsets) > i else None,
                    liquid_height=[liquid_height[i]] if liquid_height and len(liquid_height) > i else None,
                    blow_out_air_volume=(
                        [blow_out_air_volume[i]] if blow_out_air_volume and len(blow_out_air_volume) > i else None
                    ),
                    spread=spread or "wide",
                )
                await self._custom_delay_if_configured(delays, 1)

                if mix_stage in ["after", "both"] and mix_times is not None and mix_times > 0:
                    await self.mix(
                        targets=[tgt],
                        mix_time=mix_times,
                        mix_vol=mix_vol,
                        offsets=offsets if offsets else None,
                        height_to_bottom=mix_liquid_height if mix_liquid_height else None,
                        mix_rate=mix_rate if mix_rate else None,
                    )
                await self._custom_delay_if_configured(delays, 1)
                if touch_tip:
                    await self.touch_tip([tgt])
        finally:
            # 全部移液完成后，枪头放回取枪头原位
            await self.return_tips(use_channels=use_channels)

        return TransferLiquidReturn(
            sources=ResourceTreeSet.from_plr_resources(list(source_containers), known_newly_created=False).dump(),  # type: ignore
            targets=ResourceTreeSet.from_plr_resources(list(target_containers), known_newly_created=False).dump(),  # type: ignore
        )
