# tests/test_market.py
import main


def test_seed_restock_buys_wheat_fallback_when_broke():
    orders = main.seed_restock_orders(
        seeds_owned={}, rotation={"WHEAT": 0.5, "CARROT": 0.5}, cash=15,
    )
    assert orders == [["BUY_SEED", "WHEAT", 1]]


def test_seed_restock_tops_up_each_rotation_crop_when_affordable():
    orders = main.seed_restock_orders(
        seeds_owned={"WHEAT": 0, "CARROT": 0}, rotation={"WHEAT": 0.5, "CARROT": 0.5}, cash=1000,
    )
    assert ["BUY_SEED", "WHEAT", 3] in orders
    assert ["BUY_SEED", "CARROT", 3] in orders


def test_seed_restock_skips_crop_already_stocked():
    orders = main.seed_restock_orders(
        seeds_owned={"WHEAT": 5, "CARROT": 0}, rotation={"WHEAT": 0.5, "CARROT": 0.5}, cash=1000,
    )
    assert all(order[1] != "WHEAT" for order in orders)
    assert ["BUY_SEED", "CARROT", 3] in orders


def test_fertilizer_restock_buys_when_pending_and_broke_of_it():
    orders = main.fertilizer_restock_order(
        has_fertilizer=False, pending_fertilize_tasks=2, fertilizer_price=100, cash=500,
    )
    assert orders == [["BUY_PRODUCT", "FERTILIZER", 1]]


def test_fertilizer_restock_skips_when_no_pending_tasks():
    orders = main.fertilizer_restock_order(
        has_fertilizer=False, pending_fertilize_tasks=0, fertilizer_price=100, cash=500,
    )
    assert orders == []


def test_fertilizer_restock_skips_when_already_stocked():
    orders = main.fertilizer_restock_order(
        has_fertilizer=True, pending_fertilize_tasks=2, fertilizer_price=100, cash=500,
    )
    assert orders == []


def test_fertilizer_restock_skips_when_unaffordable():
    orders = main.fertilizer_restock_order(
        has_fertilizer=False, pending_fertilize_tasks=2, fertilizer_price=100, cash=50,
    )
    assert orders == []


def test_throttled_sell_caps_per_resource_per_turn():
    orders = main.throttled_sell_orders(
        shed={"WHEAT": 25}, prices={"WHEAT": 25},
    )
    assert orders == [["SELL", "WHEAT", 10]]


def test_throttled_sell_sells_full_amount_under_cap():
    orders = main.throttled_sell_orders(shed={"WHEAT": 4}, prices={"WHEAT": 25})
    assert orders == [["SELL", "WHEAT", 4]]


def test_throttled_sell_skips_near_price_floor():
    orders = main.throttled_sell_orders(shed={"MELON": 4}, prices={"MELON": 3})
    assert orders == []


def test_throttled_sell_forces_full_sell_when_shed_nearly_full():
    shed = {"MELON": 4, "WHEAT": 87}  # total 91 >= 90 force threshold
    orders = main.throttled_sell_orders(shed=shed, prices={"MELON": 3, "WHEAT": 25})
    assert ["SELL", "MELON", 4] in orders
    assert ["SELL", "WHEAT", 87] in orders


def test_fib_cost_matches_documented_sequence():
    assert [main.fib_cost(n) for n in range(8)] == [1, 1, 2, 3, 5, 8, 13, 21]


def test_hire_orders_hires_when_backlog_high_and_affordable():
    # backlog threshold: pending_task_count > 5 * (unit_count + hires_today already accounted via unit_count)
    orders = main.hire_orders(hires_today=0, pending_task_count=10, unit_count=1, cash=1000)
    assert orders == [["HIRE"]]


def test_hire_orders_skips_when_backlog_low():
    orders = main.hire_orders(hires_today=0, pending_task_count=3, unit_count=1, cash=1000)
    assert orders == []


def test_hire_orders_skips_when_cash_too_low():
    orders = main.hire_orders(hires_today=5, pending_task_count=100, unit_count=1, cash=10)
    assert orders == []  # fib_cost(5)=8 + 200 reserve > 10


def test_land_orders_buys_when_utilized_and_affordable():
    tiles = [[{"kind": "WEED"}] * 5 for _ in range(5)]  # all 25 tiles occupied
    orders = main.land_orders(unlocked_quadrants=["NW"], tiles=tiles, cash=2000)
    assert orders == [["BUY_LAND"]]


def test_land_orders_skips_when_underutilized():
    tiles = [[None] * 5 for _ in range(5)]  # nothing planted, 0% utilization
    orders = main.land_orders(unlocked_quadrants=["NW"], tiles=tiles, cash=2000)
    assert orders == []


def test_land_orders_skips_when_unaffordable():
    tiles = [[{"kind": "WEED"}] * 5 for _ in range(5)]
    orders = main.land_orders(unlocked_quadrants=["NW"], tiles=tiles, cash=500)
    assert orders == []  # next cost is 1000
