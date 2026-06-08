from unilabos.devices.workstation.AI4C.AI4C_robot_arm import AI4CRobotArmDevice


def default_plc_state():
    return {
        "robotic_arm_idle": True,
        "loading_rack_occupied": {str(i): i == 1 for i in range(1, 9)},
        "solid_weighing_occupied": False,
        "powder_in_solid_weighing_occupied": False,
        "pipetting_station_occupied": False,
        "magnetic_stirrer_occupied": False,
        "hplc_workstation_occupied": False,
    }


def default_plc_reads():
    reads = {
        "Powder_Cylinder_InPut[5]": True,
        "Well_Plate_Unloading_Rack_InPut[0]": False,
    }
    for index in range(25):
        reads.setdefault(f"Powder_Cylinder_InPut[{index}]", index == 5)
    return reads


def make_robot(plc_state=None, plc_reads=None):
    robot = AI4CRobotArmDevice()
    robot._plc_writes = []
    robot._plc_reads = plc_reads if plc_reads is not None else default_plc_reads()

    for key, value in (plc_state or default_plc_state()).items():
        robot._set_plc_state(key, value)

    robot._write_plc_variable = lambda node_name, value: robot._plc_writes.append((node_name, value))
    robot._read_plc_variable = lambda node_name, use_cache=True: robot._plc_reads.get(node_name, False)
    robot._wait_plc_bool = lambda node_name, expected, timeout=300.0, interval=0.2, description=None: True
    return robot


def test_robot_arm_actions_write_expected_plc_variables():
    cases = [
        (
            "pick_well_plate_from_loading_rack",
            {"position": 1},
            [
                ("Robotic_Arm_Target_Position_Code", 6),
                ("Robotic_Arm_Target_Pick_Place_Code", 1),
                ("Robotic_Arm_Action_Code", 1),
                ("Robotic_Arm_Action_Trigger", True),
                ("Robotic_Arm_Action_Trigger", False),
            ],
        ),
        (
            "place_well_plate_to_solid_weighing",
            {},
            [
                ("Robotic_Arm_Target_Position_Code", 2),
                ("Robotic_Arm_Target_Pick_Place_Code", 1),
                ("Robotic_Arm_Action_Code", 2),
                ("Robotic_Arm_Action_Trigger", True),
                ("Robotic_Arm_Action_Trigger", False),
            ],
        ),
        (
            "pick_powder_cylinder_from_stack",
            {"position": 6},
            [
                ("Robotic_Arm_Target_Position_Code", 1),
                ("Robotic_Arm_Target_Pick_Place_Code", 6),
                ("Robotic_Arm_Action_Code", 1),
                ("Robotic_Arm_Action_Trigger", True),
                ("Robotic_Arm_Action_Trigger", False),
            ],
        ),
        (
            "place_powder_cylinder_to_solid_weighing",
            {},
            [
                ("Robotic_Arm_Target_Position_Code", 2),
                ("Robotic_Arm_Target_Pick_Place_Code", 1),
                ("Robotic_Arm_Action_Code", 3),
                ("Robotic_Arm_Action_Trigger", True),
                ("Robotic_Arm_Action_Trigger", False),
            ],
        ),
        (
            "pick_powder_cylinder_from_solid_weighing",
            {},
            [
                ("Robotic_Arm_Target_Position_Code", 2),
                ("Robotic_Arm_Target_Pick_Place_Code", 1),
                ("Robotic_Arm_Action_Code", 4),
                ("Robotic_Arm_Action_Trigger", True),
                ("Robotic_Arm_Action_Trigger", False),
            ],
            {"powder_in_solid_weighing_occupied": True},
        ),
        (
            "place_powder_cylinder_to_solid_weighing_stack",
            {"position": 7},
            [
                ("Robotic_Arm_Target_Position_Code", 1),
                ("Robotic_Arm_Target_Pick_Place_Code", 7),
                ("Robotic_Arm_Action_Code", 2),
                ("Robotic_Arm_Action_Trigger", True),
                ("Robotic_Arm_Action_Trigger", False),
            ],
            None,
            {"Powder_Cylinder_InPut[6]": False},
        ),
        (
            "pick_well_plate_from_solid_weighing",
            {},
            [
                ("Robotic_Arm_Target_Position_Code", 2),
                ("Robotic_Arm_Target_Pick_Place_Code", 1),
                ("Robotic_Arm_Action_Code", 1),
                ("Robotic_Arm_Action_Trigger", True),
                ("Robotic_Arm_Action_Trigger", False),
            ],
            {"solid_weighing_occupied": True},
        ),
        (
            "place_well_plate_to_pipetting_station",
            {},
            [
                ("Robotic_Arm_Target_Position_Code", 3),
                ("Robotic_Arm_Target_Pick_Place_Code", 1),
                ("Robotic_Arm_Action_Code", 2),
                ("Robotic_Arm_Action_Trigger", True),
                ("Robotic_Arm_Action_Trigger", False),
            ],
        ),
        (
            "pick_well_plate_from_pipetting_station",
            {},
            [
                ("Robotic_Arm_Target_Position_Code", 3),
                ("Robotic_Arm_Target_Pick_Place_Code", 1),
                ("Robotic_Arm_Action_Code", 1),
                ("Robotic_Arm_Action_Trigger", True),
                ("Robotic_Arm_Action_Trigger", False),
            ],
            {"pipetting_station_occupied": True},
        ),
        (
            "place_well_plate_to_unloading_rack",
            {"position": 8},
            [
                ("Robotic_Arm_Target_Position_Code", 7),
                ("Robotic_Arm_Target_Pick_Place_Code", 8),
                ("Robotic_Arm_Action_Code", 2),
                ("Robotic_Arm_Action_Trigger", True),
                ("Robotic_Arm_Action_Trigger", False),
            ],
            None,
            {"Well_Plate_Unloading_Rack_InPut[7]": False},
        ),
    ]

    for case in cases:
        method_name, kwargs, expected_writes, *overrides = case
        plc_state_override = overrides[0] if overrides and isinstance(overrides[0], dict) else {}
        plc_reads_override = overrides[1] if len(overrides) > 1 else {}

        state = default_plc_state()
        state.update(plc_state_override)
        reads = default_plc_reads()
        reads.update(plc_reads_override)

        robot = make_robot(plc_state=state, plc_reads=reads)
        result = getattr(robot, method_name)(**kwargs)

        assert result["success"] is True
        assert robot._plc_writes == expected_writes


def test_robot_arm_rejects_invalid_positions_without_writing():
    robot = make_robot()

    assert robot.pick_well_plate_from_loading_rack(position=0)["success"] is False
    assert robot.pick_well_plate_from_loading_rack(position=9)["success"] is False
    assert robot.pick_powder_cylinder_from_stack(position=0)["success"] is False
    assert robot.pick_powder_cylinder_from_stack(position=26)["success"] is False
    assert robot.place_powder_cylinder_to_solid_weighing_stack(position=0)["success"] is False
    assert robot.place_powder_cylinder_to_solid_weighing_stack(position=26)["success"] is False
    assert robot.place_well_plate_to_unloading_rack(position=0)["success"] is False
    assert robot.place_well_plate_to_unloading_rack(position=9)["success"] is False
    assert robot._plc_writes == []


def test_robot_arm_rejects_gate_failures_without_writing():
    cases = [
        ("place_well_plate_to_solid_weighing", {}, {"robotic_arm_idle": False}),
        (
            "pick_well_plate_from_loading_rack",
            {"position": 1},
            {"loading_rack_occupied": {str(i): False for i in range(1, 9)}},
        ),
        ("place_well_plate_to_solid_weighing", {}, {"solid_weighing_occupied": True}),
        ("place_powder_cylinder_to_solid_weighing", {}, {"powder_in_solid_weighing_occupied": True}),
        ("pick_powder_cylinder_from_solid_weighing", {}, {"powder_in_solid_weighing_occupied": False}),
        ("pick_well_plate_from_solid_weighing", {}, {"solid_weighing_occupied": False}),
        ("place_well_plate_to_pipetting_station", {}, {"pipetting_station_occupied": True}),
        ("pick_well_plate_from_pipetting_station", {}, {"pipetting_station_occupied": False}),
        (
            "place_well_plate_to_unloading_rack",
            {"position": 1},
            {},
            {"Well_Plate_Unloading_Rack_InPut[0]": True},
        ),
    ]

    for case in cases:
        method_name, kwargs, state_override, *read_overrides = case
        reads = default_plc_reads()
        if read_overrides:
            reads.update(read_overrides[0])

        state = default_plc_state()
        state.update(state_override)
        robot = make_robot(plc_state=state, plc_reads=reads)

        result = getattr(robot, method_name)(**kwargs)
        assert result["success"] is False
        assert robot._plc_writes == []


def test_robot_arm_reports_timeout_without_resetting_trigger():
    robot = make_robot()
    robot._wait_plc_bool = lambda *args, **kwargs: False

    result = robot.place_well_plate_to_solid_weighing()

    assert result == {
        "success": False,
        "message": "将孔板放置到固态称重完成失败，机械臂动作未完成",
    }
    assert robot._plc_writes == [
        ("Robotic_Arm_Target_Position_Code", 2),
        ("Robotic_Arm_Target_Pick_Place_Code", 1),
        ("Robotic_Arm_Action_Code", 2),
        ("Robotic_Arm_Action_Trigger", True),
    ]
