import main


def _grid(*rows):
    """Build a tiles[y][x] grid from rows of single-tile-or-None values."""
    return [list(row) for row in rows]


def test_build_task_queue_empty_tile_is_plant():
    tiles = _grid([None])
    tasks = main.build_task_queue(tiles, day=5, has_fertilizer=False)
    assert tasks == [{"type": "PLANT", "x": 0, "y": 0, "priority": 4}]


def test_build_task_queue_weed_is_dig():
    tiles = _grid([{"kind": "WEED"}])
    tasks = main.build_task_queue(tiles, day=5, has_fertilizer=False)
    assert tasks == [{"type": "DIG", "x": 0, "y": 0, "priority": 2}]


def test_build_task_queue_unwatered_plant_is_water():
    tile = {
        "kind": "PLANT", "crop": "WHEAT", "planted_day": 3,
        "watered_today": False, "consecutive_unwatered": 1,
        "yield_units": 0, "max_lifespan_step": -1, "fertilized_until_day": -1,
    }
    tasks = main.build_task_queue(_grid([tile]), day=4, has_fertilizer=False)
    assert tasks == [{"type": "WATER", "x": 0, "y": 0, "priority": 0}]


def test_build_task_queue_watered_plant_with_yield_is_harvest():
    tile = {
        "kind": "PLANT", "crop": "WHEAT", "planted_day": 0,
        "watered_today": True, "consecutive_unwatered": 0,
        "yield_units": 3, "max_lifespan_step": -1, "fertilized_until_day": -1,
    }
    tasks = main.build_task_queue(_grid([tile]), day=2, has_fertilizer=False)
    assert tasks == [{"type": "HARVEST", "x": 0, "y": 0, "priority": 1}]


def test_build_task_queue_eligible_one_time_crop_is_fertilize():
    # WHEAT: bonus window starts at day 2 (age), max_yield_day=4, ongoing=False.
    # planted_day=0, day=2 -> age=2, in window, watered, no pending yield, fertilizer on hand.
    tile = {
        "kind": "PLANT", "crop": "WHEAT", "planted_day": 0,
        "watered_today": True, "consecutive_unwatered": 0,
        "yield_units": 0, "max_lifespan_step": -1, "fertilized_until_day": -1,
    }
    tasks = main.build_task_queue(_grid([tile]), day=2, has_fertilizer=True)
    assert tasks == [{"type": "FERTILIZE", "x": 0, "y": 0, "priority": 3}]


def test_build_task_queue_ongoing_crop_never_fertilized_in_v1():
    tile = {
        "kind": "PLANT", "crop": "TOMATO", "planted_day": 0,
        "watered_today": True, "consecutive_unwatered": 0,
        "yield_units": 0, "max_lifespan_step": -1, "fertilized_until_day": -1,
    }
    tasks = main.build_task_queue(_grid([tile]), day=8, has_fertilizer=True)
    assert tasks == []


def test_build_task_queue_skips_locked_and_structure_tiles():
    tiles = _grid(["LOCKED", {"kind": "COOP", "animal": None}])
    tasks = main.build_task_queue(tiles, day=5, has_fertilizer=False)
    assert tasks == []


def test_build_task_queue_scans_full_grid_row_major():
    tiles = [
        [None, {"kind": "WEED"}],
        [None, None],
    ]
    tasks = main.build_task_queue(tiles, day=1, has_fertilizer=False)
    coords = {(t["x"], t["y"]) for t in tasks}
    assert coords == {(0, 0), (1, 0), (0, 1), (1, 1)}


def test_assign_units_nearest_task_wins():
    units = [(0, 0), (5, 5)]
    tasks = [
        {"type": "WATER", "x": 1, "y": 0, "priority": 0},
        {"type": "WATER", "x": 4, "y": 5, "priority": 0},
    ]
    result = main.assign_units(units, tasks)
    assert result[0] == tasks[0]
    assert result[1] == tasks[1]


def test_assign_units_priority_beats_distance():
    # Unit 0 is closer to the low-priority PLANT task, but the WATER task
    # (priority 0) must be claimed first even though it's farther.
    units = [(0, 0)]
    tasks = [
        {"type": "PLANT", "x": 1, "y": 0, "priority": 4},
        {"type": "WATER", "x": 9, "y": 9, "priority": 0},
    ]
    result = main.assign_units(units, tasks)
    assert result[0]["type"] == "WATER"


def test_assign_units_leftover_units_are_idle():
    units = [(0, 0), (1, 1)]
    tasks = [{"type": "WATER", "x": 0, "y": 0, "priority": 0}]
    result = main.assign_units(units, tasks)
    assert result[0] == tasks[0]
    assert result[1] is None


def test_assign_units_no_tasks_all_idle():
    units = [(0, 0), (1, 1)]
    result = main.assign_units(units, [])
    assert result == [None, None]


def test_dispatch_unit_moves_toward_task():
    task = {"type": "WATER", "x": 5, "y": 5, "priority": 0}
    op = main.dispatch_unit((0, 5), task, crop_for_plant=None)
    assert op == [main.step_toward((0, 5), (5, 5))]


def test_dispatch_unit_acts_when_on_task_tile():
    task = {"type": "WATER", "x": 5, "y": 5, "priority": 0}
    op = main.dispatch_unit((5, 5), task, crop_for_plant=None)
    assert op == ["WATER"]


def test_dispatch_unit_plant_includes_crop():
    task = {"type": "PLANT", "x": 2, "y": 2, "priority": 4}
    op = main.dispatch_unit((2, 2), task, crop_for_plant="WHEAT")
    assert op == ["PLANT", "WHEAT"]


def test_dispatch_unit_no_task_passes():
    op = main.dispatch_unit((0, 0), None, crop_for_plant=None)
    assert op == ["PASS"]


def test_build_task_queue_skips_animal_zone_tiles_even_when_empty():
    x, y = main.ANIMAL_ZONE["COOP"]
    tiles = [[None for _ in range(10)] for _ in range(10)]
    tasks = main.build_task_queue(tiles, day=1, has_fertilizer=False)
    assert not any(t["x"] == x and t["y"] == y for t in tasks)


def test_build_task_queue_still_plants_non_zone_empty_tiles():
    tiles = [[None for _ in range(10)] for _ in range(10)]
    tasks = main.build_task_queue(tiles, day=1, has_fertilizer=False)
    # (0,0) is not in the animal zone -> still a PLANT candidate.
    assert {"type": "PLANT", "x": 0, "y": 0, "priority": 4} in tasks
