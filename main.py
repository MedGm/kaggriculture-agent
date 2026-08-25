# main.py
"""Kaggriculture V1: crops-only heuristic agent."""
import math

CROPS = {
    "WHEAT":      {"seed_cost": 10,  "base_price": 25,  "first_yield_day": 2,  "max_yield_day": 4,  "ongoing": False},
    "CARROT":     {"seed_cost": 20,  "base_price": 35,  "first_yield_day": 2,  "max_yield_day": 3,  "ongoing": False},
    "TOMATO":     {"seed_cost": 50,  "base_price": 60,  "first_yield_day": 8,  "max_yield_day": 11, "ongoing": True},
    "STRAWBERRY": {"seed_cost": 100, "base_price": 120, "first_yield_day": 10, "max_yield_day": 16, "ongoing": True},
    "MELON":      {"seed_cost": 80,  "base_price": 250, "first_yield_day": 10, "max_yield_day": 10, "ongoing": False},
}

# Confirmed via scripts/probe_axis.py (real run, not the placeholder guess):
#   Before NORTH: x=4 y=4
#   After NORTH:  x=4 y=3
#   NORTH delta: dx=0 dy=-1
# NORTH decreases y (row index), consistent with tiles[y][x] having row 0 at
# the top of the board.
DIRECTION_DELTAS = {
    "NORTH": (0, -1),
    "SOUTH": (0, 1),
    "EAST": (1, 0),
    "WEST": (-1, 0),
}

TASK_PRIORITY = {"WATER": 0, "HARVEST": 1, "DIG": 2, "FERTILIZE": 3, "PLANT": 4}


def agent(obs):
    try:
        return _agent_impl(obs)
    except Exception:
        return {"farmer": ["PASS"], "hands": [], "market": []}


def _agent_impl(obs):
    return {"farmer": ["PASS"], "hands": [], "market": []}


PHASE2_CASH_THRESHOLD = 400
PHASE3_CASH_THRESHOLD = 1500


def bonus_window_start(crop):
    return math.ceil(CROPS[crop]["max_yield_day"] / 2)


def rotation_plan(day, cash, tile_count):
    if cash < PHASE2_CASH_THRESHOLD:
        return {"WHEAT": 0.5, "CARROT": 0.5}
    if cash < PHASE3_CASH_THRESHOLD:
        return {"WHEAT": 0.3, "CARROT": 0.2, "MELON": 0.5}
    return {
        "WHEAT": 0.2,
        "CARROT": 0.1,
        "MELON": 0.4,
        "TOMATO": 0.15,
        "STRAWBERRY": 0.15,
    }


def choose_plant_crop(rotation, planted_counts, seeds_owned):
    total = sum(planted_counts.values())
    best_crop = None
    best_deficit = None
    for crop, target_fraction in rotation.items():
        if seeds_owned.get(crop, 0) <= 0:
            continue
        deficit = target_fraction * total - planted_counts.get(crop, 0)
        if best_deficit is None or deficit > best_deficit:
            best_deficit = deficit
            best_crop = crop
    return best_crop


def _fertilize_eligible(tile, day, has_fertilizer):
    if not has_fertilizer:
        return False
    crop = tile["crop"]
    if CROPS[crop]["ongoing"]:
        return False  # V1 scope: fertilize one-time crops only
    if tile["fertilized_until_day"] >= day:
        return False
    age = day - tile["planted_day"]
    return bonus_window_start(crop) <= age <= CROPS[crop]["max_yield_day"]


def build_task_queue(tiles, day, has_fertilizer):
    tasks = []
    for y, row in enumerate(tiles):
        for x, tile in enumerate(row):
            task_type = None
            if tile is None:
                task_type = "PLANT"
            elif tile == "LOCKED":
                continue
            elif tile.get("kind") == "WEED":
                task_type = "DIG"
            elif tile.get("kind") == "PLANT":
                if not tile["watered_today"]:
                    task_type = "WATER"
                elif tile["yield_units"] > 0:
                    task_type = "HARVEST"
                elif _fertilize_eligible(tile, day, has_fertilizer):
                    task_type = "FERTILIZE"
            # COOP / PASTURE: no-op in V1 (no animals)
            if task_type is not None:
                tasks.append({
                    "type": task_type, "x": x, "y": y,
                    "priority": TASK_PRIORITY[task_type],
                })
    return tasks


def assign_units(units, tasks):
    assignment = [None] * len(units)
    remaining_units = list(range(len(units)))
    remaining_tasks = list(range(len(tasks)))
    while remaining_units and remaining_tasks:
        best = None
        for ui in remaining_units:
            ux, uy = units[ui]
            for ti in remaining_tasks:
                task = tasks[ti]
                dist = abs(ux - task["x"]) + abs(uy - task["y"])
                key = (task["priority"], dist, ui, ti)
                if best is None or key < best[0]:
                    best = (key, ui, ti)
        _, ui, ti = best
        assignment[ui] = tasks[ti]
        remaining_units.remove(ui)
        remaining_tasks.remove(ti)
    return assignment


def step_toward(unit_pos, target):
    ux, uy = unit_pos
    tx, ty = target
    dx, dy = tx - ux, ty - uy
    if dx == 0 and dy == 0:
        return None
    if abs(dx) >= abs(dy):
        wanted = (1 if dx > 0 else -1, 0)
    else:
        wanted = (0, 1 if dy > 0 else -1)
    for direction, delta in DIRECTION_DELTAS.items():
        if delta == wanted:
            return direction
    return None


def dispatch_unit(unit_pos, task, crop_for_plant):
    if task is None:
        return ["PASS"]
    target = (task["x"], task["y"])
    if unit_pos != target:
        direction = step_toward(unit_pos, target)
        return [direction] if direction else ["PASS"]
    if task["type"] == "PLANT":
        return ["PLANT", crop_for_plant] if crop_for_plant else ["PASS"]
    return [task["type"]]


SEED_RESTOCK_TARGET = 3
SELL_CAP_PER_TURN = 10
SELL_FLOOR_PRICE = 5
SHED_FORCE_SELL_THRESHOLD = 90


def seed_restock_orders(seeds_owned, rotation, cash):
    orders = []
    remaining_cash = cash
    for crop in rotation:
        owned = seeds_owned.get(crop, 0)
        if owned >= SEED_RESTOCK_TARGET:
            continue
        cost = CROPS[crop]["seed_cost"] * SEED_RESTOCK_TARGET
        if remaining_cash >= cost:
            orders.append(["BUY_SEED", crop, SEED_RESTOCK_TARGET])
            remaining_cash -= cost
    if not orders and seeds_owned.get("WHEAT", 0) < 1 and remaining_cash >= CROPS["WHEAT"]["seed_cost"]:
        orders.append(["BUY_SEED", "WHEAT", 1])
    return orders


def fertilizer_restock_order(has_fertilizer, pending_fertilize_tasks, fertilizer_price, cash):
    if has_fertilizer or pending_fertilize_tasks <= 0:
        return []
    if cash < fertilizer_price:
        return []
    return [["BUY_PRODUCT", "FERTILIZER", 1]]


def throttled_sell_orders(shed, prices):
    total_in_shed = sum(shed.values())
    force = total_in_shed >= SHED_FORCE_SELL_THRESHOLD
    orders = []
    for item, qty in shed.items():
        if qty <= 0:
            continue
        price = prices.get(item, 1)
        if not force and price <= SELL_FLOOR_PRICE:
            continue
        amount = qty if force else min(qty, SELL_CAP_PER_TURN)
        orders.append(["SELL", item, amount])
    return orders


LAND_COSTS = [1000, 2000, 4000]
LAND_UTILIZATION_THRESHOLD = 0.8
LAND_CASH_RESERVE = 200
HIRE_TASKS_PER_UNIT = 5
HIRE_CASH_RESERVE = 200


def fib_cost(n):
    a, b = 1, 1
    for _ in range(n):
        a, b = b, a + b
    return a


def hire_orders(hires_today, pending_task_count, unit_count, cash):
    if pending_task_count <= HIRE_TASKS_PER_UNIT * unit_count:
        return []
    cost = fib_cost(hires_today)
    if cash < cost + HIRE_CASH_RESERVE:
        return []
    return [["HIRE"]]


def land_orders(unlocked_quadrants, tiles, cash):
    num_owned = len(unlocked_quadrants)
    if num_owned >= len(LAND_COSTS) + 1:
        return []
    total = sum(1 for row in tiles for tile in row if tile != "LOCKED")
    if total == 0:
        return []
    occupied = sum(1 for row in tiles for tile in row if tile not in (None, "LOCKED"))
    utilization = occupied / total
    if utilization < LAND_UTILIZATION_THRESHOLD:
        return []
    cost = LAND_COSTS[num_owned - 1]
    if cash < cost + LAND_CASH_RESERVE:
        return []
    return [["BUY_LAND"]]
