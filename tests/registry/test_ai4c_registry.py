from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import sys

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

from unilabos.registry.ast_registry_scanner import scan_directory  # noqa: E402
from unilabos.devices.workstation.AI4C.AI4C_plc import AI4CPLCDevice  # noqa: E402


<<<<<<< HEAD
def test_ai4c_plc_get_variables_defaults_to_all_loaded_csv_nodes():
    plc = AI4CPLCDevice.__new__(AI4CPLCDevice)
    plc._variables_to_find = {
        "机械臂空闲": {},
        "固体称量占位": {},
        "当前磁搅流程步": {},
    }
    plc._reverse_mapping = {
        "机械臂空闲": "Robotic_Arm_Idle",
        "固体称量占位": "Solid_Weighing_Occupied",
        "当前磁搅流程步": "Magnetic_Stirrer_Current_Step",
    }
    values = {
        "机械臂空闲": True,
        "固体称量占位": False,
        "当前磁搅流程步": 3,
    }
    plc.get_node_value = lambda node_name, use_cache=True: values[node_name]

    assert plc.get_variables() == {
        "Robotic_Arm_Idle": True,
        "Solid_Weighing_Occupied": False,
        "Magnetic_Stirrer_Current_Step": 3,
    }


def test_ai4c_plc_get_variables_accepts_aliases_and_raw_node_names():
    plc = AI4CPLCDevice.__new__(AI4CPLCDevice)
    plc._variables_to_find = {
        "Robotic_Arm_Idle": {},
        "Solid_Weighing_Occupied": {},
    }
    values = {
        "Robotic_Arm_Idle": True,
        "Solid_Weighing_Occupied": False,
    }
    plc.get_node_value = lambda node_name, use_cache=True: values[node_name]

    assert plc.get_variables(["robotic_arm_idle", "Solid_Weighing_Occupied"]) == {
        "robotic_arm_idle": True,
        "Solid_Weighing_Occupied": False,
    }


def test_ai4c_plc_registers_only_plc_actions_and_status_variables():
    plc_file = REPO_ROOT / "unilabos/devices/workstation/AI4C/AI4C_plc.py"

    with ThreadPoolExecutor(max_workers=1) as executor:
        result = scan_directory(
            plc_file.parent,
            python_path=REPO_ROOT,
            executor=executor,
            include_files=[plc_file],
        )

    plc_meta = result["devices"]["AI4C_plc"]

    assert plc_meta["category"] == ["custom"]
    assert plc_meta["display_name"] == "AI4C PLC"
    assert set(plc_meta["actions"]) == {
        "init_workstation",
        "start_heart_beat",
        "stop_heart_beat",
    }
    assert "pick_well_plate_from_loading_rack" not in plc_meta["actions"]
    assert "trigger_solid_weighing" not in plc_meta["actions"]
    assert "trigger_magnetic_stirrer" not in plc_meta["actions"]

    assert set(plc_meta["status_properties"]) >= {
        "robotic_arm_idle",
        "solid_weighing_occupied",
        "powder_in_solid_weighing_occupied",
        "pipetting_station_occupied",
        "magnetic_stirrer_occupied",
        "hplc_workstation_occupied",
        "robotic_arm_current_step",
        "solid_weighing_current_step",
        "magnetic_stirrer_current_step",
    }


=======
>>>>>>> hydration_01
def test_ai4c_station_registers_first_twenty_five_step_actions():
    ai4c_file = REPO_ROOT / "unilabos/devices/workstation/AI4C/AI4C.py"

    with ThreadPoolExecutor(max_workers=1) as executor:
        result = scan_directory(
            ai4c_file.parent,
            python_path=REPO_ROOT,
            executor=executor,
            include_files=[ai4c_file],
        )

    ai4c_meta = result["devices"]["AI4C_station"]

    assert ai4c_meta["category"] == ["workstation"]
    assert ai4c_meta["display_name"] == "AI4C 工作站"
    assert set(ai4c_meta["actions"]) == {
        "init_workstation",
        "pick_well_plate_from_loading_rack",
        "open_solid_weighing_door",
        "place_well_plate_to_solid_weighing",
        "pick_powder_cylinder_from_stack",
        "place_powder_cylinder_to_solid_weighing",
        "close_solid_weighing_door",
        "trigger_solid_weighing",
        "pick_powder_cylinder_from_solid_weighing",
        "place_powder_cylinder_to_solid_weighing_stack",
        "pick_well_plate_from_solid_weighing",
        "place_well_plate_to_pipetting_station",
        "trigger_pipetting",
        "pick_well_plate_from_pipetting_station",
        "place_well_plate_to_magnetic_stirrer",
        "trigger_magnetic_stirrer",
        "pick_well_plate_from_magnetic_stirrer",
        "place_well_plate_to_hplc_station",
        "trigger_hplc",
        "pick_well_plate_from_hplc_station",
        "place_well_plate_to_unloading_rack",
    }
    pick_handles = ai4c_meta["actions"]["pick_well_plate_from_loading_rack"]["action_args"]["handles"]
    assert pick_handles == [
        {
            "_call": "unilabos.registry.decorators:ActionInputHandle",
            "key": "loading_rack_position",
            "data_type": "ai4c_loading_rack_position",
            "label": "上料架位置",
            "data_key": "position",
            "data_source": "HANDLE",
            "description": "孔板所在上料架位置，范围 1-8",
        }
    ]
    powder_pick_handles = ai4c_meta["actions"]["pick_powder_cylinder_from_stack"]["action_args"]["handles"]
    assert powder_pick_handles == [
        {
            "_call": "unilabos.registry.decorators:ActionInputHandle",
            "key": "powder_stack_position",
            "data_type": "ai4c_powder_stack_position",
            "label": "粉桶堆栈位置",
            "data_key": "position",
            "data_source": "HANDLE",
            "description": "粉桶所在堆栈位置，范围 1-25",
        }
    ]
    weighing_handles = ai4c_meta["actions"]["trigger_solid_weighing"]["action_args"]["handles"]
    assert weighing_handles == [
        {
            "_call": "unilabos.registry.decorators:ActionInputHandle",
            "key": "solid_weighing_gram",
            "data_type": "ai4c_solid_weighing_gram",
            "label": "称重目标值",
            "data_key": "gram",
            "data_source": "HANDLE",
            "description": "固体称量目标值",
        },
        {
            "_call": "unilabos.registry.decorators:ActionInputHandle",
            "key": "solid_weighing_tolerance",
            "data_type": "ai4c_solid_weighing_tolerance",
            "label": "称重误差",
            "data_key": "tolerance",
            "data_source": "HANDLE",
            "description": "固体称量允许误差",
        },
        {
            "_call": "unilabos.registry.decorators:ActionInputHandle",
            "key": "solid_weighing_slot",
            "data_type": "ai4c_solid_weighing_slot",
            "label": "称量槽位",
            "data_key": "slot",
            "data_source": "HANDLE",
            "description": "固体称量槽位",
        },
    ]
    powder_return_handles = ai4c_meta["actions"]["place_powder_cylinder_to_solid_weighing_stack"]["action_args"]["handles"]
    assert powder_return_handles == [
        {
            "_call": "unilabos.registry.decorators:ActionInputHandle",
            "key": "powder_stack_return_position",
            "data_type": "ai4c_powder_stack_position",
            "label": "粉桶放回堆栈位置",
            "data_key": "position",
            "data_source": "HANDLE",
            "description": "粉桶放回的堆栈位置，范围 1-25",
        }
    ]
    pipetting_handles = ai4c_meta["actions"]["trigger_pipetting"]["action_args"]["handles"]
    assert pipetting_handles == [
        {
            "_call": "unilabos.registry.decorators:ActionInputHandle",
            "key": "pipetting_param",
            "data_type": "ai4c_pipetting_param",
            "label": "移液参数",
            "data_key": "param",
            "data_source": "HANDLE",
            "description": "移液站参数",
        }
    ]
    magnetic_handles = ai4c_meta["actions"]["trigger_magnetic_stirrer"]["action_args"]["handles"]
    assert magnetic_handles == [
        {
            "_call": "unilabos.registry.decorators:ActionInputHandle",
            "key": "magnetic_stirrer_speed",
            "data_type": "ai4c_magnetic_stirrer_speed",
            "label": "搅拌速度",
            "data_key": "speed",
            "data_source": "HANDLE",
            "description": "磁力搅拌速度",
        },
        {
            "_call": "unilabos.registry.decorators:ActionInputHandle",
            "key": "magnetic_stirrer_temperature",
            "data_type": "ai4c_magnetic_stirrer_temperature",
            "label": "搅拌温度",
            "data_key": "temperature",
            "data_source": "HANDLE",
            "description": "磁力搅拌温度",
        },
        {
            "_call": "unilabos.registry.decorators:ActionInputHandle",
            "key": "magnetic_stirrer_minutes",
            "data_type": "ai4c_magnetic_stirrer_minutes",
            "label": "搅拌时间",
            "data_key": "mins",
            "data_source": "HANDLE",
            "description": "磁力搅拌时间，单位分钟",
        },
    ]
    hplc_handles = ai4c_meta["actions"]["trigger_hplc"]["action_args"]["handles"]
    assert hplc_handles == [
        {
            "_call": "unilabos.registry.decorators:ActionInputHandle",
            "key": "hplc_param",
            "data_type": "ai4c_hplc_param",
            "label": "HPLC 参数",
            "data_key": "param",
            "data_source": "HANDLE",
            "description": "HPLC 加工参数",
        }
    ]
    unloading_handles = ai4c_meta["actions"]["place_well_plate_to_unloading_rack"]["action_args"]["handles"]
    assert unloading_handles == [
        {
            "_call": "unilabos.registry.decorators:ActionInputHandle",
            "key": "unloading_rack_position",
            "data_type": "ai4c_unloading_rack_position",
            "label": "下料架位置",
            "data_key": "position",
            "data_source": "HANDLE",
            "description": "孔板放置的下料架位置，范围 1-8",
        }
    ]
    assert ai4c_meta["auto_methods"] == {}


def test_ai4c_station_registry_entry_keeps_display_name():
    from unilabos.registry.registry import Registry

    registry = Registry()
    entry = registry._build_device_entry_from_ast(
        "AI4C_station",
        {
            "module": "unilabos.devices.workstation.AI4C.AI4C:AI4CDevice",
            "file_path": "unilabos/devices/workstation/AI4C/AI4C.py",
            "category": ["workstation"],
            "description": "AI4C 水合工作站",
            "display_name": "AI4C 工作站",
            "icon": "AI4C.webp",
            "version": "1.0.0",
            "device_type": "python",
            "handles": [],
            "actions": {},
            "status_properties": {},
            "init_params": [],
            "auto_methods": {},
            "import_map": {},
        },
    )

    assert entry["display_name"] == "AI4C 工作站"


def test_ai4c_pick_plate_action_exports_loading_rack_position_handle():
    from unilabos.registry.registry import Registry

    registry = Registry()
    entry = registry._build_device_entry_from_ast(
        "AI4C_station",
        {
            "module": "unilabos.devices.workstation.AI4C.AI4C:AI4CDevice",
            "file_path": "unilabos/devices/workstation/AI4C/AI4C.py",
            "category": ["workstation"],
            "description": "AI4C 水合工作站",
            "display_name": "AI4C 工作站",
            "icon": "AI4C.webp",
            "version": "1.0.0",
            "device_type": "python",
            "handles": [],
            "actions": {
                "pick_well_plate_from_loading_rack": {
                    "action_args": {
                        "action_type": None,
                        "auto_prefix": True,
                        "description": "步骤2：从上料架抓取孔板",
                        "handles": [
                            {
                                "_call": "unilabos.registry.decorators:ActionInputHandle",
                                "key": "loading_rack_position",
                                "data_type": "ai4c_loading_rack_position",
                                "label": "上料架位置",
                                "data_key": "position",
                                "data_source": "HANDLE",
                                "description": "孔板所在上料架位置，范围 1-8",
                            }
                        ],
                    },
                    "params": [{"name": "position", "type": "int", "default": 1, "required": False}],
                    "return_type": "dict",
                    "is_async": False,
                    "docstring": "",
                }
            },
            "status_properties": {},
            "init_params": [],
            "auto_methods": {},
            "import_map": {},
        },
    )

    action = entry["class"]["action_value_mappings"]["auto-pick_well_plate_from_loading_rack"]
    assert action["handles"] == {
        "input": [
            {
                "handler_key": "loading_rack_position",
                "data_type": "ai4c_loading_rack_position",
                "label": "上料架位置",
                "data_key": "position",
                "data_source": "handle",
                "description": "孔板所在上料架位置，范围 1-8",
                "io_type": "source",
            }
        ],
        "output": [],
    }
