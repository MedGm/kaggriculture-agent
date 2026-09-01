import main


def _grid(size=10):
    return [[None for _ in range(size)] for _ in range(size)]


def test_zone_animals_maps_each_animal_to_its_fixed_slot():
    lookup = {animal: xy for animal, _, xy in main.ZONE_ANIMALS}
    assert lookup == {
        "GOOSE": main.ANIMAL_ZONE["COOP"],
        "COW": main.ANIMAL_ZONE["PASTURE_1"],
        "SHEEP": main.ANIMAL_ZONE["PASTURE_2"],
    }


def test_tile_at_reads_xy_from_row_major_grid():
    tiles = _grid()
    tiles[3][4] = {"kind": "COOP", "animal": None}
    assert main._tile_at(tiles, (4, 3)) == {"kind": "COOP", "animal": None}


def test_animal_hand_hire_order_fires_once_per_day():
    assert main.animal_hand_hire_order(hires_today=0) == [["HIRE"]]
    assert main.animal_hand_hire_order(hires_today=1) == []
    assert main.animal_hand_hire_order(hires_today=5) == []


def test_animal_buy_orders_buys_all_three_when_affordable():
    tiles = _grid()
    orders = main.animal_buy_orders(tiles, shed={}, cash=10000)
    assert ["BUY_ANIMAL", "GOOSE", 1] in orders
    assert ["BUY_ANIMAL", "COW", 1] in orders
    assert ["BUY_ANIMAL", "SHEEP", 1] in orders


def test_animal_buy_orders_skips_already_placed_animal():
    tiles = _grid()
    x, y = main.ANIMAL_ZONE["COOP"]
    tiles[y][x] = {"kind": "COOP", "animal": "GOOSE"}
    orders = main.animal_buy_orders(tiles, shed={}, cash=10000)
    assert all(o[1] != "GOOSE" for o in orders)
    assert ["BUY_ANIMAL", "COW", 1] in orders
    assert ["BUY_ANIMAL", "SHEEP", 1] in orders


def test_animal_buy_orders_skips_owned_but_unplaced_animal():
    tiles = _grid()
    orders = main.animal_buy_orders(tiles, shed={"COW": 1}, cash=10000)
    assert all(o[1] != "COW" for o in orders)


def test_animal_buy_orders_respects_cash_limit():
    tiles = _grid()
    orders = main.animal_buy_orders(tiles, shed={}, cash=350)
    assert orders == [["BUY_ANIMAL", "GOOSE", 1]]


def _animal_tile(animal, fed_today=True, yield_units=0, cared_today=True, fertilizer_available=False):
    kind = "COOP" if animal == "GOOSE" else "PASTURE"
    return {
        "kind": kind, "animal": animal, "fed_today": fed_today,
        "yield_units": yield_units, "cared_today": cared_today,
        "fertilizer_available": fertilizer_available,
    }


def _tiles_with(assignments):
    tiles = _grid()
    for xy, tile in assignments.items():
        x, y = xy
        tiles[y][x] = tile
    return tiles


def test_dispatch_animal_hand_feeds_when_carrying_wheat():
    goose_xy = main.ANIMAL_ZONE["COOP"]
    tiles = _tiles_with({goose_xy: _animal_tile("GOOSE", fed_today=False)})
    op = main.dispatch_animal_hand(goose_xy, {"WHEAT": 2}, tiles, shed={})
    assert op == ["FEED"]


def test_dispatch_animal_hand_moves_toward_unfed_animal_when_carrying_wheat():
    goose_xy = main.ANIMAL_ZONE["COOP"]
    tiles = _tiles_with({goose_xy: _animal_tile("GOOSE", fed_today=False)})
    op = main.dispatch_animal_hand((0, 0), {"WHEAT": 2}, tiles, shed={})
    assert op == [main.step_toward((0, 0), goose_xy)]


def test_dispatch_animal_hand_picks_up_wheat_when_unfed_and_empty_handed():
    goose_xy = main.ANIMAL_ZONE["COOP"]
    tiles = _tiles_with({goose_xy: _animal_tile("GOOSE", fed_today=False)})
    shed_pos = main.nearest_shed_tile(goose_xy)
    op = main.dispatch_animal_hand(shed_pos, {}, tiles, shed={"WHEAT": 3})
    assert op == ["PICKUP", "WHEAT", 1]  # only 1 animal unfed -> pick up 1


def test_dispatch_animal_hand_caps_wheat_pickup_at_shed_stock():
    goose_xy = main.ANIMAL_ZONE["COOP"]
    cow_xy = main.ANIMAL_ZONE["PASTURE_1"]
    tiles = _tiles_with({
        goose_xy: _animal_tile("GOOSE", fed_today=False),
        cow_xy: _animal_tile("COW", fed_today=False),
    })
    shed_pos = main.nearest_shed_tile(goose_xy)
    op = main.dispatch_animal_hand(shed_pos, {}, tiles, shed={"WHEAT": 1})
    assert op == ["PICKUP", "WHEAT", 1]  # 2 unfed but shed only has 1


def test_dispatch_animal_hand_does_not_pass_when_no_wheat_anywhere():
    goose_xy = main.ANIMAL_ZONE["COOP"]
    tiles = _tiles_with({goose_xy: _animal_tile("GOOSE", fed_today=False)})
    shed_pos = main.nearest_shed_tile(goose_xy)
    op = main.dispatch_animal_hand(shed_pos, {}, tiles, shed={"WHEAT": 0})
    assert op == ["PASS"]


def test_dispatch_animal_hand_harvests_ready_product_before_building():
    goose_xy = main.ANIMAL_ZONE["COOP"]
    tiles = _tiles_with({goose_xy: _animal_tile("GOOSE", yield_units=2)})
    op = main.dispatch_animal_hand(goose_xy, {}, tiles, shed={})
    assert op == ["HARVEST"]


def test_dispatch_animal_hand_builds_empty_zone_tile():
    tiles = _grid()  # all zone tiles empty
    coop_xy = main.ANIMAL_ZONE["COOP"]
    op = main.dispatch_animal_hand(coop_xy, {}, tiles, shed={})
    assert op == ["BUILD_COOP"]


def test_dispatch_animal_hand_delivers_owned_animal_from_shed():
    cow_xy = main.ANIMAL_ZONE["PASTURE_1"]
    tiles = _tiles_with({
        main.ANIMAL_ZONE["COOP"]: {"kind": "COOP", "animal": None},
        cow_xy: {"kind": "PASTURE", "animal": None},
        main.ANIMAL_ZONE["PASTURE_2"]: {"kind": "PASTURE", "animal": None},
    })
    shed_pos = main.nearest_shed_tile(cow_xy)
    op = main.dispatch_animal_hand(shed_pos, {}, tiles, shed={"COW": 1})
    assert op == ["PICKUP", "COW", 1]


def test_dispatch_animal_hand_places_carried_animal_at_its_slot():
    cow_xy = main.ANIMAL_ZONE["PASTURE_1"]
    tiles = _tiles_with({
        main.ANIMAL_ZONE["COOP"]: {"kind": "COOP", "animal": None},
        cow_xy: {"kind": "PASTURE", "animal": None},
        main.ANIMAL_ZONE["PASTURE_2"]: {"kind": "PASTURE", "animal": None},
    })
    op = main.dispatch_animal_hand(cow_xy, {"COW": 1}, tiles, shed={})
    assert op == ["PLACE", "COW"]


def test_dispatch_animal_hand_cares_for_fed_animal_with_no_yield():
    goose_xy = main.ANIMAL_ZONE["COOP"]
    tiles = _tiles_with({
        goose_xy: _animal_tile("GOOSE", cared_today=False),
        main.ANIMAL_ZONE["PASTURE_1"]: _animal_tile("COW"),
        main.ANIMAL_ZONE["PASTURE_2"]: _animal_tile("SHEEP"),
    })
    op = main.dispatch_animal_hand(goose_xy, {}, tiles, shed={})
    assert op == ["CARE"]


def test_dispatch_animal_hand_collects_fertilizer_last():
    goose_xy = main.ANIMAL_ZONE["COOP"]
    tiles = _tiles_with({
        goose_xy: _animal_tile("GOOSE", fertilizer_available=True),
        main.ANIMAL_ZONE["PASTURE_1"]: _animal_tile("COW"),
        main.ANIMAL_ZONE["PASTURE_2"]: _animal_tile("SHEEP"),
    })
    op = main.dispatch_animal_hand(goose_xy, {}, tiles, shed={})
    assert op == ["COLLECT_FERTILIZER"]


def test_dispatch_animal_hand_passes_when_fully_idle():
    goose_xy = main.ANIMAL_ZONE["COOP"]
    tiles = _tiles_with({
        goose_xy: _animal_tile("GOOSE"),  # fed, no yield, cared, no fertilizer
        main.ANIMAL_ZONE["PASTURE_1"]: _animal_tile("COW"),
        main.ANIMAL_ZONE["PASTURE_2"]: _animal_tile("SHEEP"),
    })
    op = main.dispatch_animal_hand(goose_xy, {}, tiles, shed={})
    assert op == ["PASS"]


def test_dispatch_animal_hand_moves_toward_empty_zone_tile_when_not_at_it():
    tiles = _grid()  # all zone tiles empty
    coop_xy = main.ANIMAL_ZONE["COOP"]
    op = main.dispatch_animal_hand((0, 0), {}, tiles, shed={})
    assert op == [main.step_toward((0, 0), coop_xy)]


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


def test_setup_complete_true_when_all_three_placed():
    tiles = _grid()
    placements = {
        main.ANIMAL_ZONE["COOP"]: {"kind": "COOP", "animal": "GOOSE"},
        main.ANIMAL_ZONE["PASTURE_1"]: {"kind": "PASTURE", "animal": "COW"},
        main.ANIMAL_ZONE["PASTURE_2"]: {"kind": "PASTURE", "animal": "SHEEP"},
    }
    for (x, y), tile in placements.items():
        tiles[y][x] = tile
    assert main.setup_complete(tiles) is True


def test_setup_complete_false_when_one_missing():
    tiles = _grid()
    x, y = main.ANIMAL_ZONE["COOP"]
    tiles[y][x] = {"kind": "COOP", "animal": "GOOSE"}
    assert main.setup_complete(tiles) is False


def test_setup_complete_false_on_fresh_farm():
    tiles = _grid()
    assert main.setup_complete(tiles) is False


def test_dispatch_setup_helper_targets_sheep_end_first_on_fresh_farm():
    tiles = _grid()  # all zone tiles empty
    sheep_pasture_xy = main.ANIMAL_ZONE["PASTURE_2"]
    op = main.dispatch_setup_helper(sheep_pasture_xy, {}, tiles, shed={})
    assert op == ["BUILD_PASTURE"]


def test_dispatch_setup_helper_differs_from_animal_hand_on_same_fresh_input():
    tiles = _grid()
    hand_pos = main.ANIMAL_ZONE["COOP"]
    main_op = main.dispatch_animal_hand(hand_pos, {}, tiles, shed={})
    helper_op = main.dispatch_setup_helper(hand_pos, {}, tiles, shed={})
    assert main_op == ["BUILD_COOP"]
    assert helper_op != ["BUILD_COOP"]


def test_dispatch_setup_helper_never_feeds_harvests_cares_or_collects():
    x, y = main.ANIMAL_ZONE["COOP"]
    tiles = _grid()
    tiles[y][x] = {
        "kind": "COOP", "animal": "GOOSE", "fed_today": False,
        "yield_units": 5, "cared_today": False, "fertilizer_available": True,
    }
    op = main.dispatch_setup_helper((x, y), {}, tiles, shed={})
    assert op[0] not in ("FEED", "HARVEST", "CARE", "COLLECT_FERTILIZER")


def test_dispatch_setup_helper_delivers_owned_animal_from_shed():
    tiles = _grid()
    tiles[main.ANIMAL_ZONE["COOP"][1]][main.ANIMAL_ZONE["COOP"][0]] = {"kind": "COOP", "animal": None}
    tiles[main.ANIMAL_ZONE["PASTURE_1"][1]][main.ANIMAL_ZONE["PASTURE_1"][0]] = {"kind": "PASTURE", "animal": None}
    tiles[main.ANIMAL_ZONE["PASTURE_2"][1]][main.ANIMAL_ZONE["PASTURE_2"][0]] = {"kind": "PASTURE", "animal": None}
    shed_pos = main.nearest_shed_tile((0, 0))
    op = main.dispatch_setup_helper(shed_pos, {}, tiles, shed={"SHEEP": 1})
    assert op == ["PICKUP", "SHEEP", 1]


def test_dispatch_setup_helper_returns_pass_when_nothing_to_do():
    tiles = _grid()
    for animal, kind, xy in main.ZONE_ANIMALS:
        x, y = xy
        tiles[y][x] = {"kind": kind, "animal": animal}
    op = main.dispatch_setup_helper(main.ANIMAL_ZONE["COOP"], {}, tiles, shed={})
    assert op == ["PASS"]


def test_second_hand_hire_order_fires_below_two_hires():
    assert main.second_hand_hire_order(hires_today=0) == [["HIRE"]]
    assert main.second_hand_hire_order(hires_today=1) == [["HIRE"]]
    assert main.second_hand_hire_order(hires_today=2) == []
    assert main.second_hand_hire_order(hires_today=5) == []
