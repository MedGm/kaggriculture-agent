import main


def _grid(size=10):
    return [[None for _ in range(size)] for _ in range(size)]


def test_animal_setup_tasks_builds_coop_and_pasture_on_fresh_farm():
    tiles = _grid()
    tasks = main.animal_setup_tasks(tiles, shed={})
    types = {t["type"] for t in tasks}
    assert "BUILD_COOP" in types
    assert "BUILD_PASTURE" in types


def test_animal_setup_tasks_stops_building_once_targets_met():
    tiles = _grid()
    tiles[0][0] = {"kind": "COOP", "animal": "GOOSE"}
    tiles[0][1] = {"kind": "PASTURE", "animal": "COW"}
    tiles[0][2] = {"kind": "PASTURE", "animal": "SHEEP"}
    tasks = main.animal_setup_tasks(tiles, shed={})
    assert tasks == []


def test_animal_setup_tasks_delivers_owned_animal_to_empty_structure():
    tiles = _grid()
    tiles[0][0] = {"kind": "COOP", "animal": None}
    tasks = main.animal_setup_tasks(tiles, shed={"GOOSE": 1})
    assert {"type": "DELIVER", "x": 0, "y": 0, "priority": 2, "animal": "GOOSE"} in tasks


def test_animal_setup_tasks_keeps_delivering_animal_already_in_unit_inventory():
    # Once PICKUP moves the animal out of the shed, shed count hits 0 — the
    # DELIVER task must persist as long as SOME unit still carries it, or a
    # carrying unit's cargo becomes permanently invisible to task generation.
    tiles = _grid()
    tiles[0][0] = {"kind": "COOP", "animal": None}
    tasks = main.animal_setup_tasks(tiles, shed={}, inventories=[{"GOOSE": 1}])
    assert {"type": "DELIVER", "x": 0, "y": 0, "priority": 2, "animal": "GOOSE"} in tasks


def test_animal_setup_tasks_does_not_deliver_unowned_animal():
    tiles = _grid()
    tiles[0][0] = {"kind": "COOP", "animal": None}
    tasks = main.animal_setup_tasks(tiles, shed={})
    assert all(t["type"] != "DELIVER" for t in tasks)


def test_animal_setup_tasks_assigns_cow_then_sheep_to_distinct_pastures():
    tiles = _grid()
    tiles[0][0] = {"kind": "PASTURE", "animal": None}
    tiles[0][1] = {"kind": "PASTURE", "animal": None}
    tasks = main.animal_setup_tasks(tiles, shed={"COW": 1, "SHEEP": 1})
    delivered = {(t["x"], t["y"]): t["animal"] for t in tasks if t["type"] == "DELIVER"}
    assert set(delivered.values()) == {"COW", "SHEEP"}


def test_animal_buy_orders_buys_missing_animals_when_affordable():
    tiles = _grid()
    orders = main.animal_buy_orders(tiles, shed={}, cash=10000)
    assert ["BUY_ANIMAL", "GOOSE", 1] in orders
    assert ["BUY_ANIMAL", "COW", 1] in orders
    assert ["BUY_ANIMAL", "SHEEP", 1] in orders


def test_animal_buy_orders_skips_already_owned_or_placed():
    tiles = _grid()
    tiles[0][0] = {"kind": "COOP", "animal": "GOOSE"}
    orders = main.animal_buy_orders(tiles, shed={"COW": 1}, cash=10000)
    assert all(o[1] != "GOOSE" for o in orders)
    assert all(o[1] != "COW" for o in orders)
    assert ["BUY_ANIMAL", "SHEEP", 1] in orders


def test_animal_buy_orders_respects_cash_limit():
    tiles = _grid()
    orders = main.animal_buy_orders(tiles, shed={}, cash=350)
    # Only GOOSE (300) affordable; COW (400) and SHEEP (500) are not.
    assert orders == [["BUY_ANIMAL", "GOOSE", 1]]


def test_feed_restock_buys_up_to_target_when_low():
    orders = main.feed_restock_order(shed_wheat=0, live_animal_count=1, wheat_price=25, cash=1000)
    assert orders == [["BUY_PRODUCT", "WHEAT", 5]]


def test_feed_restock_skips_when_no_live_animals():
    orders = main.feed_restock_order(shed_wheat=0, live_animal_count=0, wheat_price=25, cash=1000)
    assert orders == []


def test_feed_restock_skips_when_already_stocked():
    orders = main.feed_restock_order(shed_wheat=5, live_animal_count=2, wheat_price=25, cash=1000)
    assert orders == []


def test_feed_restock_buys_partial_amount_when_cash_limited():
    orders = main.feed_restock_order(shed_wheat=0, live_animal_count=1, wheat_price=25, cash=60)
    assert orders == [["BUY_PRODUCT", "WHEAT", 2]]


def test_nearest_shed_tile_picks_closest():
    assert main.nearest_shed_tile((0, 0)) == (4, 4)
    assert main.nearest_shed_tile((9, 9)) == (5, 5)


def test_dispatch_unit_deliver_moves_to_shed_when_not_carrying():
    task = {"type": "DELIVER", "x": 0, "y": 0, "priority": 2, "animal": "GOOSE"}
    op = main.dispatch_unit((0, 0), task, crop_for_plant=None, unit_inventory={})
    assert op == [main.step_toward((0, 0), main.nearest_shed_tile((0, 0)))]


def test_dispatch_unit_deliver_picks_up_at_shed():
    task = {"type": "DELIVER", "x": 0, "y": 0, "priority": 2, "animal": "GOOSE"}
    shed_pos = main.nearest_shed_tile((0, 0))
    op = main.dispatch_unit(shed_pos, task, crop_for_plant=None, unit_inventory={})
    assert op == ["PICKUP", "GOOSE", 1]


def test_dispatch_unit_deliver_moves_to_structure_when_carrying():
    task = {"type": "DELIVER", "x": 0, "y": 0, "priority": 2, "animal": "GOOSE"}
    op = main.dispatch_unit((5, 5), task, crop_for_plant=None, unit_inventory={"GOOSE": 1})
    assert op == [main.step_toward((5, 5), (0, 0))]


def test_dispatch_unit_deliver_places_at_structure():
    task = {"type": "DELIVER", "x": 0, "y": 0, "priority": 2, "animal": "GOOSE"}
    op = main.dispatch_unit((0, 0), task, crop_for_plant=None, unit_inventory={"GOOSE": 1})
    assert op == ["PLACE", "GOOSE"]


def test_build_task_queue_feeds_unfed_animal():
    tile = {"kind": "PASTURE", "animal": "COW", "fed_today": False, "yield_units": 0, "cared_today": False, "fertilizer_available": False}
    tasks = main.build_task_queue([[tile]], day=5, has_fertilizer=False)
    assert tasks == [{"type": "FEED", "x": 0, "y": 0, "priority": 0}]


def test_build_task_queue_harvests_fed_animal_with_yield():
    tile = {"kind": "PASTURE", "animal": "COW", "fed_today": True, "yield_units": 2, "cared_today": False, "fertilizer_available": False}
    tasks = main.build_task_queue([[tile]], day=5, has_fertilizer=False)
    assert tasks == [{"type": "HARVEST", "x": 0, "y": 0, "priority": 1}]


def test_build_task_queue_cares_for_fed_animal_with_no_yield():
    tile = {"kind": "PASTURE", "animal": "COW", "fed_today": True, "yield_units": 0, "cared_today": False, "fertilizer_available": False}
    tasks = main.build_task_queue([[tile]], day=5, has_fertilizer=False)
    assert tasks == [{"type": "CARE", "x": 0, "y": 0, "priority": 3}]


def test_build_task_queue_collects_fertilizer_from_cared_animal():
    tile = {"kind": "PASTURE", "animal": "COW", "fed_today": True, "yield_units": 0, "cared_today": True, "fertilizer_available": True}
    tasks = main.build_task_queue([[tile]], day=5, has_fertilizer=False)
    assert tasks == [{"type": "COLLECT_FERTILIZER", "x": 0, "y": 0, "priority": 5}]


def test_build_task_queue_empty_structure_produces_no_task():
    tile = {"kind": "COOP", "animal": None}
    tasks = main.build_task_queue([[tile]], day=5, has_fertilizer=False)
    assert tasks == []
