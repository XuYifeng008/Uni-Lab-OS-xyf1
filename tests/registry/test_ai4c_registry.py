from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import ast
import sys

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

from unilabos.registry.ast_registry_scanner import scan_directory  # noqa: E402


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


def test_ai4c_plc_status_properties_match_runtime_methods():
    ai4c_plc_file = REPO_ROOT / "unilabos/devices/workstation/AI4C/AI4C_plc.py"

    with ThreadPoolExecutor(max_workers=1) as executor:
        result = scan_directory(
            ai4c_plc_file.parent,
            python_path=REPO_ROOT,
            executor=executor,
            include_files=[ai4c_plc_file],
        )

    plc_meta = result["devices"]["AI4C_plc"]
    module = ast.parse(ai4c_plc_file.read_text())
    plc_class = next(
        node for node in module.body if isinstance(node, ast.ClassDef) and node.name == plc_meta["class_name"]
    )
    runtime_methods = {node.name for node in plc_class.body if isinstance(node, ast.FunctionDef)}

    assert set(plc_meta["status_properties"]) <= runtime_methods


def test_ai4c_plc_get_variable_status_action_registered():
    ai4c_plc_file = REPO_ROOT / "unilabos/devices/workstation/AI4C/AI4C_plc.py"

    with ThreadPoolExecutor(max_workers=1) as executor:
        result = scan_directory(
            ai4c_plc_file.parent,
            python_path=REPO_ROOT,
            executor=executor,
            include_files=[ai4c_plc_file],
        )

    plc_meta = result["devices"]["AI4C_plc"]
    assert "get_variable_status" in plc_meta["actions"]
    assert plc_meta["actions"]["get_variable_status"]["action_args"]["description"] == "获取指定 PLC 变量的状态"


def test_ai4c_plc_get_variable_status_runtime():
    from unittest.mock import patch, MagicMock
    import unilabos.devices.workstation.base_opcua_client
    with patch("unilabos.devices.workstation.base_opcua_client.OpcUaClientWithSubscription.__init__", return_value=None):
        from unilabos.devices.workstation.AI4C.AI4C_plc import AI4CPLCDevice
        dev = AI4CPLCDevice(url="opc.tcp://localhost:4840")
        dev._name_mapping = {"Powder_Cylinder_InPut[24]": "粉筒_InPut[24]"}
        dev._reverse_mapping = {"粉筒_InPut[24]": "Powder_Cylinder_InPut[24]"}
        dev._variables_to_find = {"粉筒_InPut[24]": {}}
        
        # Mock get_variables
        dev.get_variables = MagicMock(return_value={"粉筒_InPut[24]": True})
        
        # Test with English name
        res = dev.get_variable_status("Powder_Cylinder_InPut[24]")
        dev.get_variables.assert_called_once_with(["粉筒_InPut[24]"], use_cache=False)
        assert res == {"Powder_Cylinder_InPut[24]": True}
        
        # Test with Chinese name
        dev.get_variables.reset_mock()
        dev.get_variables.return_value = {"粉筒_InPut[24]": True}
        res = dev.get_variable_status("粉筒_InPut[24]")
        dev.get_variables.assert_called_once_with(["粉筒_InPut[24]"], use_cache=False)
        assert res == {"粉筒_InPut[24]": True}


def test_ai4c_plc_csv_path_resolution():
    from unittest.mock import patch
    import os
    with patch("unilabos.devices.workstation.base_opcua_client.OpcUaClientWithSubscription.__init__", return_value=None), \
         patch("unilabos.devices.workstation.AI4C.AI4C_plc.AI4CPLCDevice.load_nodes_from_csv") as mock_load:
        from unilabos.devices.workstation.AI4C.AI4C_plc import AI4CPLCDevice
        import unilabos.devices.workstation.AI4C.AI4C_plc as AI4C_plc
        
        # Test absolute path
        abs_path = "/tmp/test.csv"
        dev = AI4CPLCDevice(url="opc.tcp://localhost:4840", csv_path=abs_path)
        mock_load.assert_called_once_with(abs_path)
        
        # Test relative path / filename
        mock_load.reset_mock()
        filename = "ai4c_sim_updated.csv"
        dev = AI4CPLCDevice(url="opc.tcp://localhost:4840", csv_path=filename)
        current_dir = os.path.dirname(os.path.abspath(AI4C_plc.__file__))
        expected_path = os.path.join(current_dir, filename)
        mock_load.assert_called_once_with(expected_path)

