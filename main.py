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
