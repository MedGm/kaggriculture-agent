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

ANIMALS = {
    "GOOSE": {"cost": 300, "structure": "COOP"},
    "COW":   {"cost": 400, "structure": "PASTURE"},
    "SHEEP": {"cost": 500, "structure": "PASTURE"},
}

# Fixed tile assignment (never dynamic): each animal always targets the same
# slot. All three are inside the always-unlocked NW starting quadrant, close
# to the shed-adjacent tile (4,4), so the dedicated animal hand's daily
# route is short and predictable.
ANIMAL_ZONE = {"COOP": (3, 4), "PASTURE_1": (3, 3), "PASTURE_2": (2, 4)}
ZONE_ANIMALS = [
    ("GOOSE", "COOP", ANIMAL_ZONE["COOP"]),
    ("COW", "PASTURE", ANIMAL_ZONE["PASTURE_1"]),
    ("SHEEP", "PASTURE", ANIMAL_ZONE["PASTURE_2"]),
]
ANIMAL_ZONE_TILES = {xy for _, _, xy in ZONE_ANIMALS}


def _tile_at(tiles, xy):
    x, y = xy
    return tiles[y][x]

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


PHASE2_CASH_THRESHOLD = 250
PHASE3_CASH_THRESHOLD = 900


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
                if (x, y) not in ANIMAL_ZONE_TILES:
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


SEED_RESTOCK_TARGET = 8
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


def throttled_sell_orders(shed, prices, wheat_reserve=0):
    total_in_shed = sum(shed.values())
    force = total_in_shed >= SHED_FORCE_SELL_THRESHOLD
    orders = []
    for item, qty in shed.items():
        sellable = qty
        if item == "WHEAT" and not force:
            sellable = max(0, qty - wheat_reserve)
        if sellable <= 0:
            continue
        price = prices.get(item, 1)
        if not force and price <= SELL_FLOOR_PRICE:
            continue
        amount = sellable if force else min(sellable, SELL_CAP_PER_TURN)
        orders.append(["SELL", item, amount])
    return orders


LAND_COSTS = [1000, 2000, 4000]
LAND_UTILIZATION_THRESHOLD = 0.6
LAND_CASH_RESERVE = 150
HIRE_TASKS_PER_UNIT = 3
HIRE_CASH_RESERVE = 100
MAX_HIRES_PER_DAY = 6  # fib_cost(6)=13; beyond this, per-hand cost outgrows a day's output


def fib_cost(n):
    a, b = 1, 1
    for _ in range(n):
        a, b = b, a + b
    return a


def hire_orders(hires_today, pending_task_count, unit_count, cash):
    if hires_today >= MAX_HIRES_PER_DAY:
        return []
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


def animal_hand_hire_order(hires_today):
    return [["HIRE"]] if hires_today == 0 else []


def animal_buy_orders(tiles, shed, cash):
    orders = []
    remaining_cash = cash
    for animal, _structure_kind, xy in ZONE_ANIMALS:
        tile = _tile_at(tiles, xy)
        already_placed = isinstance(tile, dict) and tile.get("animal") == animal
        owned_unplaced = shed.get(animal, 0) > 0
        if already_placed or owned_unplaced:
            continue
        cost = ANIMALS[animal]["cost"]
        if remaining_cash >= cost:
            orders.append(["BUY_ANIMAL", animal, 1])
            remaining_cash -= cost
    return orders


def nearest_shed_tile(pos):
    return (4, 4)


def _move_or_act(pos, target_xy, op):
    if pos != target_xy:
        direction = step_toward(pos, target_xy)
        return [direction] if direction else ["PASS"]
    return [op] if op else None


def dispatch_animal_hand(hand_pos, hand_inventory, tiles, shed):
    hand_inventory = hand_inventory or {}
    unfed, ready_harvest, uncared, fertilizer_ready = [], [], [], []
    needs_build, needs_deliver = [], []

    for animal, structure_kind, xy in ZONE_ANIMALS:
        tile = _tile_at(tiles, xy)
        if tile is None:
            needs_build.append((structure_kind, xy))
        elif tile.get("animal") is None:
            if shed.get(animal, 0) > 0 or hand_inventory.get(animal, 0) > 0:
                needs_deliver.append((animal, xy))
        elif tile.get("animal") == animal:
            if not tile["fed_today"]:
                unfed.append((animal, xy))
            elif tile["yield_units"] > 0:
                ready_harvest.append((animal, xy))
            elif not tile["cared_today"]:
                uncared.append((animal, xy))
            elif tile.get("fertilizer_available"):
                fertilizer_ready.append((animal, xy))

    def nearest(candidates):
        return min(candidates, key=lambda a: abs(a[1][0] - hand_pos[0]) + abs(a[1][1] - hand_pos[1]))

    if unfed:
        if hand_inventory.get("WHEAT", 0) > 0:
            _, xy = nearest(unfed)
            return _move_or_act(hand_pos, xy, "FEED")
        shed_pos = nearest_shed_tile(hand_pos)
        if hand_pos != shed_pos:
            direction = step_toward(hand_pos, shed_pos)
            return [direction] if direction else ["PASS"]
        amount = min(len(unfed), shed.get("WHEAT", 0))
        if amount <= 0:
            return ["PASS"]
        return ["PICKUP", "WHEAT", amount]

    if ready_harvest:
        _, xy = nearest(ready_harvest)
        return _move_or_act(hand_pos, xy, "HARVEST")

    if needs_build:
        structure_kind, xy = needs_build[0]
        return _move_or_act(hand_pos, xy, f"BUILD_{structure_kind}")

    if needs_deliver:
        animal, xy = needs_deliver[0]
        if hand_inventory.get(animal, 0) > 0:
            moved = _move_or_act(hand_pos, xy, None)
            return moved if moved is not None else ["PLACE", animal]
        shed_pos = nearest_shed_tile(hand_pos)
        if hand_pos != shed_pos:
            direction = step_toward(hand_pos, shed_pos)
            return [direction] if direction else ["PASS"]
        return ["PICKUP", animal, 1]

    if uncared:
        _, xy = nearest(uncared)
        return _move_or_act(hand_pos, xy, "CARE")

    if fertilizer_ready:
        _, xy = nearest(fertilizer_ready)
        return _move_or_act(hand_pos, xy, "COLLECT_FERTILIZER")

    return ["PASS"]


# agent() must be the LAST callable defined in this file: kaggle_environments
# loads a file-based agent submission via the last callable in the module
# namespace (kaggle_environments/agent.py get_last_callable), not by name.
# _agent_impl must therefore be defined BEFORE agent, so agent stays last.
def _agent_impl(obs):
    player = obs["player"]
    day = obs["day"]
    me = obs["farms"][player]
    private = obs["private"]
    tiles = me["tiles"]
    cash = me["money"]
    fx, fy = me["farmer"]
    hand_positions = [tuple(h) for h in me["hands"]]
    shed = private["shed"]
    seeds_owned = private["seeds"]
    inventories = private["inventories"]
    prices = obs["market"]["prices"]

    tile_count = sum(1 for row in tiles for tile in row if tile != "LOCKED")
    rotation = rotation_plan(day, cash, tile_count)

    planted_counts = {}
    for row in tiles:
        for tile in row:
            if isinstance(tile, dict) and tile.get("kind") == "PLANT":
                planted_counts[tile["crop"]] = planted_counts.get(tile["crop"], 0) + 1

    has_fertilizer = shed.get("FERTILIZER", 0) > 0
    tasks = build_task_queue(tiles, day, has_fertilizer)

    animal_hand_pos = hand_positions[0] if hand_positions else None
    crop_hand_positions = hand_positions[1:] if hand_positions else []

    crop_units = [(fx, fy)] + crop_hand_positions
    assignment = assign_units(crop_units, tasks)

    crop_for_plant = choose_plant_crop(rotation, planted_counts, seeds_owned)

    farmer_op = dispatch_unit((fx, fy), assignment[0], crop_for_plant)
    crop_hand_ops = [
        dispatch_unit(pos, assignment[i + 1], crop_for_plant)
        for i, pos in enumerate(crop_hand_positions)
    ]

    hand_ops = list(crop_hand_ops)
    if animal_hand_pos is not None:
        animal_hand_inventory = inventories[1] if len(inventories) > 1 else {}
        hand_ops = [dispatch_animal_hand(animal_hand_pos, animal_hand_inventory, tiles, shed)] + crop_hand_ops

    live_animal_count = sum(
        1 for _, _, xy in ZONE_ANIMALS
        if isinstance(_tile_at(tiles, xy), dict) and _tile_at(tiles, xy).get("animal") is not None
    )

    pending_fertilize_tasks = sum(1 for t in tasks if t["type"] == "FERTILIZE")

    # Order: mandatory animal-hire first (guarantees hands[0] is the animal
    # hand), then sells (with a wheat reserve for feeding), then the rest
    # exactly as V1.3.
    market_orders = []
    market_orders += animal_hand_hire_order(me["hires_today"])
    market_orders += throttled_sell_orders(shed, prices, wheat_reserve=live_animal_count)
    market_orders += animal_buy_orders(tiles, shed, cash)
    market_orders += seed_restock_orders(seeds_owned, rotation, cash)
    market_orders += fertilizer_restock_order(
        has_fertilizer, pending_fertilize_tasks, prices.get("FERTILIZER", 100), cash,
    )
    market_orders += hire_orders(me["hires_today"], len(tasks), len(crop_units), cash)
    market_orders += land_orders(me["unlocked_quadrants"], tiles, cash)
    market_orders = market_orders[:10]

    return {"farmer": farmer_op, "hands": hand_ops, "market": market_orders}


def agent(obs):
    try:
        return _agent_impl(obs)
    except Exception:
        return {"farmer": ["PASS"], "hands": [], "market": []}
