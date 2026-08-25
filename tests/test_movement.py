import main


def test_step_toward_same_position_returns_none():
    assert main.step_toward((3, 3), (3, 3)) is None


def test_step_toward_prefers_larger_axis_gap_x():
    # dx=3, dy=1 -> move along x first
    direction = main.step_toward((0, 0), (3, 1))
    dx, dy = main.DIRECTION_DELTAS[direction]
    assert (dx, dy) == (1, 0)


def test_step_toward_prefers_larger_axis_gap_y():
    direction = main.step_toward((0, 0), (1, 3))
    dx, dy = main.DIRECTION_DELTAS[direction]
    assert (dx, dy) == main.DIRECTION_DELTAS["SOUTH"] if main.DIRECTION_DELTAS["SOUTH"][1] > 0 else main.DIRECTION_DELTAS["NORTH"]
    # simpler equivalent check: moving toward larger y matches whichever of
    # NORTH/SOUTH has a positive dy, since target y (3) > unit y (0)
    expected = "SOUTH" if main.DIRECTION_DELTAS["SOUTH"][1] == 1 else "NORTH"
    assert direction == expected


def test_step_toward_matches_sign_of_gap():
    for direction, (dx, dy) in main.DIRECTION_DELTAS.items():
        unit_pos = (5, 5)
        target = (5 + dx, 5 + dy)
        assert main.step_toward(unit_pos, target) == direction
