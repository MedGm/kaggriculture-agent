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
