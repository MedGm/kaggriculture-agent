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
