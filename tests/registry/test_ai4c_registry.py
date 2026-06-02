from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import sys

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

from unilabos.registry.ast_registry_scanner import scan_directory  # noqa: E402


def test_ai4c_station_registers_only_first_four_step_actions():
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
