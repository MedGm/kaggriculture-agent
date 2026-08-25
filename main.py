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

TASK_PRIORITY = {
    "WATER": 0, "FEED": 0,
    "HARVEST": 1,
    "DIG": 2, "BUILD_COOP": 2, "BUILD_PASTURE": 2, "DELIVER": 2,
    "FERTILIZE": 3, "CARE": 3,
    "PLANT": 4,
    "COLLECT_FERTILIZER": 5,
}

ANIMALS = {
    "GOOSE": {"cost": 300, "structure": "COOP"},
    "COW":   {"cost": 400, "structure": "PASTURE"},
    "SHEEP": {"cost": 500, "structure": "PASTURE"},
}
ANIMAL_TARGET = {"GOOSE": 1, "COW": 1, "SHEEP": 1}
COOP_TARGET = 1
PASTURE_TARGET = 2

# The shed sits at the board center, on none of the 4 tiles adjacent to it —
# for boardSize=10, those are (half-1,half-1),(half,half-1),(half-1,half),(half,half).
SHED_ADJACENT_TILES = [(4, 4), (5, 4), (4, 5), (5, 5)]


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
            elif tile.get("kind") in ("COOP", "PASTURE") and tile.get("animal") is not None:
                if not tile["fed_today"]:
                    task_type = "FEED"
                elif tile["yield_units"] > 0:
                    task_type = "HARVEST"
                elif not tile["cared_today"]:
                    task_type = "CARE"
                elif tile.get("fertilizer_available"):
                    task_type = "COLLECT_FERTILIZER"
            # Empty COOP/PASTURE (animal is None): handled by animal_setup_tasks,
            # not here, since placing an animal needs shed-wide context (do we
            # own one yet?), not just this tile's state.
            if task_type is not None:
                tasks.append({
                    "type": task_type, "x": x, "y": y,
                    "priority": TASK_PRIORITY[task_type],
                })
    return tasks


def _animal_structures(tiles):
    coop_tiles = []
    pasture_tiles = []
    for y, row in enumerate(tiles):
        for x, tile in enumerate(row):
            if isinstance(tile, dict) and tile.get("kind") == "COOP":
                coop_tiles.append((x, y, tile))
            elif isinstance(tile, dict) and tile.get("kind") == "PASTURE":
                pasture_tiles.append((x, y, tile))
    return coop_tiles, pasture_tiles


def _empty_tiles(tiles):
    return [(x, y) for y, row in enumerate(tiles) for x, tile in enumerate(row) if tile is None]


def animal_setup_tasks(tiles, shed, inventories=None):
    # An animal counts as "available to deliver" whether it's still in the
    # shed or already picked up into a unit's inventory — otherwise the
    # DELIVER task vanishes the instant PICKUP empties the shed slot, and
    # the carrying unit's cargo becomes invisible to task generation (it
    # just picks up the next animal instead of finishing the delivery).
    inventories = inventories or []

    def available(animal):
        return shed.get(animal, 0) + sum(inv.get(animal, 0) for inv in inventories)

    coop_tiles, pasture_tiles = _animal_structures(tiles)
    tasks = []
    empties = iter(_empty_tiles(tiles))
    if len(coop_tiles) < COOP_TARGET:
        pos = next(empties, None)
        if pos:
            tasks.append({"type": "BUILD_COOP", "x": pos[0], "y": pos[1], "priority": TASK_PRIORITY["BUILD_COOP"]})
    if len(pasture_tiles) < PASTURE_TARGET:
        pos = next(empties, None)
        if pos:
            tasks.append({"type": "BUILD_PASTURE", "x": pos[0], "y": pos[1], "priority": TASK_PRIORITY["BUILD_PASTURE"]})

    unoccupied_coops = [(x, y) for x, y, t in coop_tiles if t.get("animal") is None]
    if unoccupied_coops and available("GOOSE") > 0:
        x, y = unoccupied_coops[0]
        tasks.append({"type": "DELIVER", "x": x, "y": y, "priority": TASK_PRIORITY["DELIVER"], "animal": "GOOSE"})

    placed_pasture_animals = [t.get("animal") for _, _, t in pasture_tiles if t.get("animal") is not None]
    for x, y in [(x, y) for x, y, t in pasture_tiles if t.get("animal") is None]:
        if "COW" not in placed_pasture_animals and available("COW") > 0:
            tasks.append({"type": "DELIVER", "x": x, "y": y, "priority": TASK_PRIORITY["DELIVER"], "animal": "COW"})
            placed_pasture_animals.append("COW")
        elif "SHEEP" not in placed_pasture_animals and available("SHEEP") > 0:
            tasks.append({"type": "DELIVER", "x": x, "y": y, "priority": TASK_PRIORITY["DELIVER"], "animal": "SHEEP"})
            placed_pasture_animals.append("SHEEP")
    return tasks


def animal_buy_orders(tiles, shed, cash):
    coop_tiles, pasture_tiles = _animal_structures(tiles)
    placed = {"GOOSE": 0, "COW": 0, "SHEEP": 0}
    for _, _, t in coop_tiles + pasture_tiles:
        animal = t.get("animal")
        if animal in placed:
            placed[animal] += 1

    orders = []
    remaining_cash = cash
    for animal, target in ANIMAL_TARGET.items():
        have = placed[animal] + shed.get(animal, 0)
        if have >= target:
            continue
        cost = ANIMALS[animal]["cost"]
        if remaining_cash >= cost:
            orders.append(["BUY_ANIMAL", animal, 1])
            remaining_cash -= cost
    return orders


def nearest_shed_tile(unit_pos):
    return min(SHED_ADJACENT_TILES, key=lambda t: abs(t[0] - unit_pos[0]) + abs(t[1] - unit_pos[1]))


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


def dispatch_unit(unit_pos, task, crop_for_plant, unit_inventory=None):
    if task is None:
        return ["PASS"]
    if task["type"] == "DELIVER":
        animal = task["animal"]
        carrying = (unit_inventory or {}).get(animal, 0) > 0
        target = (task["x"], task["y"]) if carrying else nearest_shed_tile(unit_pos)
        if unit_pos != target:
            direction = step_toward(unit_pos, target)
            return [direction] if direction else ["PASS"]
        return ["PLACE", animal] if carrying else ["PICKUP", animal, 1]
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


FEED_STOCK_TARGET = 5


def feed_restock_order(shed_wheat, live_animal_count, wheat_price, cash):
    # Feed supply must not depend on the farm's own wheat crop: with animals
    # added, FEED (priority 0) competes with WATER/PLANT for the same single
    # farmer, so relying on home-grown wheat starved feeding (and the wheat
    # crop itself) for the first week in testing. Buying wheat directly
    # decouples "animals get fed" from "the farmer got around to farming."
    if live_animal_count <= 0 or shed_wheat >= FEED_STOCK_TARGET:
        return []
    needed = FEED_STOCK_TARGET - shed_wheat
    affordable = int(cash // wheat_price) if wheat_price > 0 else 0
    amount = min(needed, affordable)
    if amount <= 0:
        return []
    return [["BUY_PRODUCT", "WHEAT", amount]]


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
    tasks = build_task_queue(tiles, day, has_fertilizer) + animal_setup_tasks(tiles, shed, inventories)

    units = [(fx, fy)] + list(hand_positions)
    assignment = assign_units(units, tasks)

    crop_for_plant = choose_plant_crop(rotation, planted_counts, seeds_owned)

    farmer_inventory = inventories[0] if inventories else {}
    farmer_op = dispatch_unit((fx, fy), assignment[0], crop_for_plant, farmer_inventory)
    hand_ops = [
        dispatch_unit(
            pos, assignment[i + 1], crop_for_plant,
            inventories[i + 1] if i + 1 < len(inventories) else {},
        )
        for i, pos in enumerate(hand_positions)
    ]

    pending_fertilize_tasks = sum(1 for t in tasks if t["type"] == "FERTILIZE")
    live_animal_count = sum(
        1 for row in tiles for tile in row
        if isinstance(tile, dict) and tile.get("kind") in ("COOP", "PASTURE") and tile.get("animal") is not None
    )

    # Sells come first: unsold shed items are worthless at game end, so
    # converting produce to cash must never be crowded out of the 10-order
    # cap by restocking (a real match showed 5+ active crops' seed restocks
    # eating the whole order budget while sellable inventory piled up unsold).
    # Feed restock comes right after: a starved animal escapes permanently,
    # so protecting existing animal investment outranks buying new ones.
    market_orders = []
    market_orders += throttled_sell_orders(shed, prices)
    market_orders += feed_restock_order(shed.get("WHEAT", 0), live_animal_count, prices.get("WHEAT", 25), cash)
    market_orders += animal_buy_orders(tiles, shed, cash)
    market_orders += seed_restock_orders(seeds_owned, rotation, cash)
    market_orders += fertilizer_restock_order(
        has_fertilizer, pending_fertilize_tasks, prices.get("FERTILIZER", 100), cash,
    )
    market_orders += hire_orders(me["hires_today"], len(tasks), len(units), cash)
    market_orders += land_orders(me["unlocked_quadrants"], tiles, cash)
    market_orders = market_orders[:10]

    return {"farmer": farmer_op, "hands": hand_ops, "market": market_orders}


def agent(obs):
    try:
        return _agent_impl(obs)
    except Exception:
        return {"farmer": ["PASS"], "hands": [], "market": []}
