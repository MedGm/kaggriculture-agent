# Kaggriculture V1 Crop-Heuristic Agent Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a crops-only heuristic Kaggriculture agent (`main.py`) that beats the `random` and `starter` baseline agents locally.

**Architecture:** Single-file, stateless-per-turn agent. Each turn: scan farm tiles into a priority-ordered task list (water > harvest > dig weed > fertilize > plant), greedily assign the farmer + hands to tasks by (priority, Manhattan distance), move-or-act, then build a capped, priority-ordered list of market orders (seed/fertilizer restock, throttled sells, ROI-gated hire, utilization-gated land buy). All decision functions are pure (tiles/obs in, list out) so they're unit-testable without a live environment.

**Tech Stack:** Python 3, `kaggle-environments` (dev/test only — not a runtime import in `main.py`), `pytest`.

**Spec:** [docs/superpowers/specs/2026-08-25-crop-heuristic-agent-design.md](../specs/2026-08-25-crop-heuristic-agent-design.md)

## Global Constraints

- Submission is a single `main.py` at repo root exposing `agent(obs)` — no other runtime files, no external deps beyond stdlib (Kaggle sandbox: 100MiB, 1.6 vCPU, 6.5GiB RAM, no guaranteed internet).
- `agent()` must never raise — any exception falls back to `{"farmer": ["PASS"], "hands": [], "market": []}`.
- `maxMarketOrdersPerTurn` = 10 — the combined market-order list must be capped to 10, priority order: fertilizer/seed restock > sells > hire > land.
- V1 is crops-only: WHEAT, CARROT, TOMATO, STRAWBERRY, MELON. No animals, no coop/pasture, no feed/care logic.
- Per-crop data (seed cost, base price, first/max yield day, ongoing flag) exactly as documented in the spec's Object Types table — do not invent different numbers.
- Board coordinates: `tiles[y][x]`, unit positions `[x, y]`. The mapping from `NORTH`/`SOUTH`/`EAST`/`WEST` to `(dx, dy)` is **not stated in the docs** and must be empirically confirmed in Task 1 before any movement code is written.
- **Deviation from spec's data-flow note:** the design doc mentions a small persisted sell-throttle counter carried across turns. This plan implements per-turn sell caps instead (cap units sold *per resource per turn*, naturally spreading a large shed stock across multiple turns since leftover stays in the shed and is reconsidered next turn) — same throttling behavior, zero cross-turn state, simpler and still fully stateless. This supersedes that one line of the spec; nothing else changes.

---

## File Structure

- `main.py` — everything: constants, pure planning/market functions, `agent(obs)` entrypoint. Single file per submission constraint.
- `tests/conftest.py` — adds repo root to `sys.path` so tests can `import main`.
- `tests/test_agent_smoke.py` — error-handling fallback tests.
- `tests/test_movement.py` — direction-delta and `step_toward` tests.
- `tests/test_rotation.py` — `bonus_window_start`, `rotation_plan`, `choose_plant_crop` tests.
- `tests/test_planner.py` — `build_task_queue`, `assign_units`, `dispatch_unit` tests.
- `tests/test_market.py` — `seed_restock_orders`, `fertilizer_restock_order`, `throttled_sell_orders`, `fib_cost`, `hire_orders`, `land_orders` tests.
- `tests/test_integration.py` — full-turn `agent(obs)` test against a synthetic observation dict (no live env).
- `scripts/probe_axis.py` — one-off script (kept for documentation) that determines the `NORTH`/`SOUTH`/`EAST`/`WEST` → `(dx, dy)` mapping using a live `kaggle_environments` episode.
- `scripts/local_eval.py` — manual pre-submit gate: runs `main.py` against `random` and `starter` baselines, prints final money for both sides.

---

## Task 1: Scaffolding + movement axis determination

**Files:**
- Create: `main.py`
- Create: `tests/conftest.py`
- Create: `tests/test_agent_smoke.py`
- Create: `scripts/probe_axis.py`

**Interfaces:**
- Produces: `main.py` module importable as `main`; `main.agent(obs) -> dict`; `main.DIRECTION_DELTAS: dict[str, tuple[int,int]]` (keys `"NORTH"`, `"SOUTH"`, `"EAST"`, `"WEST"`, values `(dx, dy)`).

- [ ] **Step 1: Install the environment package for local testing**

Run: `pip install -U kaggle-environments pytest`
Expected: installs successfully (needed for `scripts/probe_axis.py` and later manual eval; not a runtime dependency of `main.py` itself).

- [ ] **Step 2: Write the axis-probe script**

```python
# scripts/probe_axis.py
"""One-off script: determines which (dx, dy) each movement op produces.
Run once; paste the printed DIRECTION_DELTAS dict into main.py.
"""
from kaggle_environments import make


def probe_agent(obs):
    if obs["step"] == 0:
        return {"farmer": ["NORTH"], "hands": [], "market": []}
    return {"farmer": ["PASS"], "hands": [], "market": []}


def passive_agent(obs):
    return {"farmer": ["PASS"], "hands": [], "market": []}


def main():
    env = make("kaggriculture", configuration={"episodeSteps": 4}, debug=True)
    env.run([probe_agent, passive_agent])
    before = env.steps[0][0].observation
    after = env.steps[1][0].observation
    fx0, fy0 = before["farms"][0]["farmer"]
    fx1, fy1 = after["farms"][0]["farmer"]
    print(f"Before NORTH: x={fx0} y={fy0}")
    print(f"After NORTH:  x={fx1} y={fy1}")
    print(f"NORTH delta: dx={fx1 - fx0} dy={fy1 - fy0}")


if __name__ == "__main__":
    main()
```

- [ ] **Step 3: Run the probe and record the result**

Run: `python scripts/probe_axis.py`
Expected: prints a `dx=0 dy=<nonzero>` line. Record the sign of `dy` for `NORTH` — this determines `DIRECTION_DELTAS`. (If the farmer started already at `y=0` and didn't move — board edge — rerun with `"SOUTH"` instead and negate the result.)

- [ ] **Step 4: Write `main.py` skeleton with confirmed direction deltas**

```python
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

# Confirmed via scripts/probe_axis.py: NORTH decreases y (row index), consistent
# with tiles[y][x] having row 0 at the top of the board.
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
```

(Replace the `DIRECTION_DELTAS` values with whatever Step 3 actually showed if it differs from the standard row-0-at-top convention.)

- [ ] **Step 5: Write `tests/conftest.py`**

```python
# tests/conftest.py
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
```

- [ ] **Step 6: Write the smoke test**

```python
# tests/test_agent_smoke.py
import main


def test_agent_survives_empty_obs():
    result = main.agent({})
    assert result == {"farmer": ["PASS"], "hands": [], "market": []}


def test_agent_survives_malformed_obs():
    result = main.agent({"player": 0, "farms": None})
    assert result == {"farmer": ["PASS"], "hands": [], "market": []}
```

- [ ] **Step 7: Run tests to verify they pass**

Run: `pytest tests/test_agent_smoke.py -v`
Expected: 2 passed.

- [ ] **Step 8: Commit**

```bash
git add main.py tests/conftest.py tests/test_agent_smoke.py scripts/probe_axis.py
git commit -m "Scaffold agent entrypoint and confirm movement axis orientation"
```

---

## Task 2: Rotation planning (`bonus_window_start`, `rotation_plan`, `choose_plant_crop`)

**Files:**
- Modify: `main.py`
- Create: `tests/test_rotation.py`

**Interfaces:**
- Consumes: `main.CROPS` (Task 1).
- Produces: `main.bonus_window_start(crop: str) -> int`; `main.rotation_plan(day: int, cash: float, tile_count: int) -> dict[str, float]` (fractions sum to 1.0); `main.choose_plant_crop(rotation: dict[str, float], planted_counts: dict[str, int], seeds_owned: dict[str, int]) -> str | None`.

- [ ] **Step 1: Write failing tests**

```python
# tests/test_rotation.py
import main


def test_bonus_window_start_wheat():
    # max_yield_day=4 -> ceil(4/2)=2
    assert main.bonus_window_start("WHEAT") == 2


def test_bonus_window_start_melon():
    # max_yield_day=10 -> ceil(10/2)=5
    assert main.bonus_window_start("MELON") == 5


def test_rotation_plan_phase1_low_cash():
    plan = main.rotation_plan(day=1, cash=300, tile_count=25)
    assert plan == {"WHEAT": 0.5, "CARROT": 0.5}


def test_rotation_plan_phase2_mid_cash():
    plan = main.rotation_plan(day=10, cash=800, tile_count=25)
    assert plan == {"WHEAT": 0.3, "CARROT": 0.2, "MELON": 0.5}


def test_rotation_plan_phase3_high_cash():
    plan = main.rotation_plan(day=20, cash=2000, tile_count=25)
    assert plan == {
        "WHEAT": 0.2,
        "CARROT": 0.1,
        "MELON": 0.4,
        "TOMATO": 0.15,
        "STRAWBERRY": 0.15,
    }


def test_choose_plant_crop_picks_biggest_deficit():
    rotation = {"WHEAT": 0.5, "CARROT": 0.5}
    planted_counts = {"WHEAT": 8, "CARROT": 2}  # total 10; CARROT is under target
    seeds_owned = {"WHEAT": 5, "CARROT": 5}
    assert main.choose_plant_crop(rotation, planted_counts, seeds_owned) == "CARROT"


def test_choose_plant_crop_skips_crops_with_no_seed():
    rotation = {"WHEAT": 0.5, "CARROT": 0.5}
    planted_counts = {"WHEAT": 8, "CARROT": 2}
    seeds_owned = {"WHEAT": 5, "CARROT": 0}  # CARROT is preferred but unowned
    assert main.choose_plant_crop(rotation, planted_counts, seeds_owned) == "WHEAT"


def test_choose_plant_crop_returns_none_with_no_seeds():
    rotation = {"WHEAT": 0.5, "CARROT": 0.5}
    assert main.choose_plant_crop(rotation, {}, {}) is None
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_rotation.py -v`
Expected: FAIL — `AttributeError: module 'main' has no attribute 'bonus_window_start'` (and similar for the other two).

- [ ] **Step 3: Implement in `main.py`**

Append to `main.py`:

```python
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
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_rotation.py -v`
Expected: 7 passed.

- [ ] **Step 5: Commit**

```bash
git add main.py tests/test_rotation.py
git commit -m "Add rotation planning: phase thresholds and crop-deficit selection"
```

---

## Task 3: Task queue builder (`build_task_queue`)

**Files:**
- Modify: `main.py`
- Create: `tests/test_planner.py`

**Interfaces:**
- Consumes: `main.CROPS`, `main.bonus_window_start` (Task 2), `main.TASK_PRIORITY` (Task 1).
- Produces: `main.build_task_queue(tiles: list[list], day: int, has_fertilizer: bool) -> list[dict]`. Each task dict: `{"type": str, "x": int, "y": int, "priority": int}` (`FERTILIZE`/`WATER`/`HARVEST`/`DIG` have no extra fields; `PLANT` tasks carry no crop — the crop is chosen once per turn by the caller via `choose_plant_crop` and applied to all `PLANT` tasks that turn).

- [ ] **Step 1: Write failing tests**

```python
# tests/test_planner.py
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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_planner.py -v`
Expected: FAIL — `AttributeError: module 'main' has no attribute 'build_task_queue'`.

- [ ] **Step 3: Implement in `main.py`**

Append to `main.py`:

```python
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
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_planner.py -v`
Expected: 8 passed.

- [ ] **Step 5: Commit**

```bash
git add main.py tests/test_planner.py
git commit -m "Add task-queue builder scanning farm tiles into prioritized tasks"
```

---

## Task 4: Unit assignment (`assign_units`)

**Files:**
- Modify: `main.py`
- Modify: `tests/test_planner.py`

**Interfaces:**
- Consumes: task dicts from `build_task_queue` (Task 3).
- Produces: `main.assign_units(units: list[tuple[int, int]], tasks: list[dict]) -> list[dict | None]` — same length as `units`; each entry is the assigned task dict or `None` if idle.

- [ ] **Step 1: Write failing tests**

Append to `tests/test_planner.py`:

```python
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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_planner.py -v`
Expected: FAIL — `AttributeError: module 'main' has no attribute 'assign_units'`.

- [ ] **Step 3: Implement in `main.py`**

Append to `main.py`:

```python
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
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_planner.py -v`
Expected: 12 passed.

- [ ] **Step 5: Commit**

```bash
git add main.py tests/test_planner.py
git commit -m "Add greedy priority-then-distance unit assignment"
```

---

## Task 5: Movement (`step_toward`) and dispatch (`dispatch_unit`)

**Files:**
- Modify: `main.py`
- Create: `tests/test_movement.py`
- Modify: `tests/test_planner.py`

**Interfaces:**
- Consumes: `main.DIRECTION_DELTAS` (Task 1), assigned task dicts (Task 4).
- Produces: `main.step_toward(unit_pos: tuple[int, int], target: tuple[int, int]) -> str | None` (a direction name, or `None` if already there); `main.dispatch_unit(unit_pos: tuple[int, int], task: dict | None, crop_for_plant: str | None) -> list` (an op list ready to place under `"farmer"` or an entry of `"hands"`, e.g. `["WATER"]`, `["PLANT", "WHEAT"]`, `["NORTH"]`, `["PASS"]`).

- [ ] **Step 1: Write failing tests**

```python
# tests/test_movement.py
import main


def test_step_toward_same_position_returns_none():
    assert main.step_toward((3, 3), (3, 3)) is None


def test_step_toward_prefers_larger_axis_gap_x():
    # dx=3, dy=1 -> move along x first
    direction = main.step_toward((0, 0), (3, 1))
    dx, dy = main.DIRECTION_DELTAS[direction]
    assert (dx, dy) == (1, 0)


def test_step_toward_prefers_larger_axis_gap_y():
    direction = main.step_toward((0, 0), (1, 3))
    dx, dy = main.DIRECTION_DELTAS[direction]
    assert (dx, dy) == main.DIRECTION_DELTAS["SOUTH"] if main.DIRECTION_DELTAS["SOUTH"][1] > 0 else main.DIRECTION_DELTAS["NORTH"]
    # simpler equivalent check: moving toward larger y matches whichever of
    # NORTH/SOUTH has a positive dy, since target y (3) > unit y (0)
    expected = "SOUTH" if main.DIRECTION_DELTAS["SOUTH"][1] == 1 else "NORTH"
    assert direction == expected


def test_step_toward_matches_sign_of_gap():
    for direction, (dx, dy) in main.DIRECTION_DELTAS.items():
        unit_pos = (5, 5)
        target = (5 + dx, 5 + dy)
        assert main.step_toward(unit_pos, target) == direction
```

Append to `tests/test_planner.py`:

```python
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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_movement.py tests/test_planner.py -v`
Expected: FAIL — `AttributeError: module 'main' has no attribute 'step_toward'` (and `dispatch_unit`).

- [ ] **Step 3: Implement in `main.py`**

Append to `main.py`:

```python
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
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_movement.py tests/test_planner.py -v`
Expected: all passed.

- [ ] **Step 5: Commit**

```bash
git add main.py tests/test_movement.py tests/test_planner.py
git commit -m "Add movement stepping and per-unit task dispatch"
```

---

## Task 6: Market orders — seed/fertilizer restock and throttled sells

**Files:**
- Modify: `main.py`
- Create: `tests/test_market.py`

**Interfaces:**
- Consumes: `main.CROPS` (Task 1).
- Produces: `main.seed_restock_orders(seeds_owned: dict, rotation: dict, cash: float) -> list[list]`; `main.fertilizer_restock_order(has_fertilizer: bool, pending_fertilize_tasks: int, fertilizer_price: int, cash: float) -> list[list]`; `main.throttled_sell_orders(shed: dict, prices: dict) -> list[list]`.

- [ ] **Step 1: Write failing tests**

```python
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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_market.py -v`
Expected: FAIL — missing attributes.

- [ ] **Step 3: Implement in `main.py`**

Append to `main.py`:

```python
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
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_market.py -v`
Expected: 11 passed.

- [ ] **Step 5: Commit**

```bash
git add main.py tests/test_market.py
git commit -m "Add seed/fertilizer restock and per-turn throttled sell orders"
```

---

## Task 7: Market orders — hire and land

**Files:**
- Modify: `main.py`
- Modify: `tests/test_market.py`

**Interfaces:**
- Consumes: nothing new.
- Produces: `main.fib_cost(n: int) -> int`; `main.hire_orders(hires_today: int, pending_task_count: int, unit_count: int, cash: float) -> list[list]`; `main.land_orders(unlocked_quadrants: list[str], tiles: list[list], cash: float) -> list[list]`.

- [ ] **Step 1: Write failing tests**

Append to `tests/test_market.py`:

```python
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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_market.py -v`
Expected: FAIL — missing `fib_cost`, `hire_orders`, `land_orders`.

- [ ] **Step 3: Implement in `main.py`**

Append to `main.py`:

```python
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
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_market.py -v`
Expected: 18 passed.

- [ ] **Step 5: Commit**

```bash
git add main.py tests/test_market.py
git commit -m "Add fib-cost hire ROI gate and utilization-gated land purchase"
```

---

## Task 8: Full-turn integration (`_agent_impl`)

**Files:**
- Modify: `main.py`
- Create: `tests/test_integration.py`

**Interfaces:**
- Consumes: every function from Tasks 2–7.
- Produces: fully wired `main._agent_impl(obs) -> dict` with keys `"farmer"`, `"hands"`, `"market"` (market list capped at 10, `"farmer"`/`"hands"` entries are valid op lists).

- [ ] **Step 1: Write failing integration test**

```python
# tests/test_integration.py
import main


def _synthetic_obs():
    tiles = [[None for _ in range(10)] for _ in range(10)]
    return {
        "player": 0,
        "day": 0,
        "hour": 0,
        "farms": [
            {
                "money": 3000,
                "tiles": tiles,
                "farmer": [4, 4],
                "hands": [],
                "unlocked_quadrants": ["NW"],
                "hires_today": 0,
            },
            {
                "money": 3000,
                "tiles": [[None for _ in range(10)] for _ in range(10)],
                "farmer": [4, 4],
                "hands": [],
                "unlocked_quadrants": ["NW"],
                "hires_today": 0,
            },
        ],
        "market": {
            "inventory": {k: 10000 for k in ["WHEAT", "CARROT", "TOMATO", "STRAWBERRY", "MELON", "FERTILIZER"]},
            "prices": {"WHEAT": 25, "CARROT": 35, "TOMATO": 60, "STRAWBERRY": 120, "MELON": 250, "FERTILIZER": 100},
        },
        "town": {"unlocked_shops": []},
        "private": {
            "shed": {},
            "seeds": {},
            "inventories": [{}],
        },
    }


def test_agent_returns_well_formed_action_on_fresh_farm():
    result = main.agent(_synthetic_obs())
    assert set(result.keys()) == {"farmer", "hands", "market"}
    assert isinstance(result["farmer"], list) and result["farmer"]
    assert isinstance(result["hands"], list)
    assert isinstance(result["market"], list)
    assert len(result["market"]) <= 10


def test_agent_buys_wheat_seed_on_empty_farm_with_no_seeds():
    result = main.agent(_synthetic_obs())
    assert ["BUY_SEED", "WHEAT", 3] in result["market"] or ["BUY_SEED", "WHEAT", 1] in result["market"]


def test_agent_plants_on_empty_tile_when_seed_owned():
    obs = _synthetic_obs()
    obs["private"]["seeds"] = {"WHEAT": 5}
    result = main.agent(obs)
    # Farmer stands on (4,4), an empty tile -> should plant directly (no move needed).
    assert result["farmer"] == ["PLANT", "WHEAT"]


def test_agent_caps_market_orders_at_ten():
    obs = _synthetic_obs()
    obs["private"]["shed"] = {
        "WHEAT": 50, "CARROT": 50, "TOMATO": 50, "STRAWBERRY": 50, "MELON": 50,
    }
    obs["private"]["seeds"] = {"WHEAT": 0, "CARROT": 0, "TOMATO": 0, "STRAWBERRY": 0, "MELON": 0}
    result = main.agent(obs)
    assert len(result["market"]) <= 10
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_integration.py -v`
Expected: FAIL — `_agent_impl` still returns the Task 1 stub (`{"farmer": ["PASS"], ...}`), so the plant/seed assertions fail.

- [ ] **Step 3: Implement `_agent_impl` in `main.py`**

Replace the Task 1 stub:

```python
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

    units = [(fx, fy)] + list(hand_positions)
    assignment = assign_units(units, tasks)

    crop_for_plant = choose_plant_crop(rotation, planted_counts, seeds_owned)

    farmer_op = dispatch_unit((fx, fy), assignment[0], crop_for_plant)
    hand_ops = [
        dispatch_unit(pos, assignment[i + 1], crop_for_plant)
        for i, pos in enumerate(hand_positions)
    ]

    pending_fertilize_tasks = sum(1 for t in tasks if t["type"] == "FERTILIZE")

    market_orders = []
    market_orders += seed_restock_orders(seeds_owned, rotation, cash)
    market_orders += fertilizer_restock_order(
        has_fertilizer, pending_fertilize_tasks, prices.get("FERTILIZER", 100), cash,
    )
    market_orders += throttled_sell_orders(shed, prices)
    market_orders += hire_orders(me["hires_today"], len(tasks), len(units), cash)
    market_orders += land_orders(me["unlocked_quadrants"], tiles, cash)
    market_orders = market_orders[:10]

    return {"farmer": farmer_op, "hands": hand_ops, "market": market_orders}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_integration.py -v`
Expected: 4 passed.

- [ ] **Step 5: Run the full test suite**

Run: `pytest -v`
Expected: all tests across every file pass (Tasks 1–8 combined).

- [ ] **Step 6: Commit**

```bash
git add main.py tests/test_integration.py
git commit -m "Wire task planning and market orders into full agent turn logic"
```

---

## Task 9: Manual local evaluation against baselines

**Files:**
- Create: `scripts/local_eval.py`

**Interfaces:**
- Consumes: `main.py` (loaded by `kaggle_environments` as a file path, not imported directly).
- Produces: printed final-money comparison; no new importable interface (this is a dev tool, not part of the pytest suite per the spec's testing section).

- [ ] **Step 1: Write the evaluation script**

```python
# scripts/local_eval.py
"""Manual pre-submit gate: run main.py against baseline agents and report results."""
from kaggle_environments import make


def run_match(opponent_name, episode_steps=720):
    env = make("kaggriculture", configuration={"episodeSteps": episode_steps}, debug=True)
    env.run(["main.py", opponent_name])
    final = env.steps[-1]
    my_money = final[0].observation["farms"][0]["money"]
    opp_money = final[1].observation["farms"][1]["money"]
    print(f"vs {opponent_name}: main.py=${my_money:.0f}  opponent=${opp_money:.0f}  "
          f"{'WIN' if my_money > opp_money else 'LOSS' if my_money < opp_money else 'TIE'}")


if __name__ == "__main__":
    run_match("random")
    run_match("starter")
```

- [ ] **Step 2: Run it against both baselines**

Run: `python scripts/local_eval.py`
Expected: two result lines printed, e.g. `vs random: main.py=$X  opponent=$Y  WIN`. If either match is a LOSS, treat this as a signal to revisit rotation thresholds (`PHASE2_CASH_THRESHOLD`, `PHASE3_CASH_THRESHOLD` in `main.py`) before proceeding — not a blocking failure, since baseline-beating margins will need empirical tuning, but don't submit a build that loses to `random`.

- [ ] **Step 3: Commit**

```bash
git add scripts/local_eval.py
git commit -m "Add manual local-eval script for pre-submit baseline comparison"
```

---

## Task 10: Submission dry run

**Files:** none (verification only).

- [ ] **Step 1: Verify `main.py` has zero non-stdlib imports**

Run: `python -c "import ast, sys; tree = ast.parse(open('main.py').read()); imports = [n.names[0].name for n in ast.walk(tree) if isinstance(n, (ast.Import, ast.ImportFrom)) for _ in [1]] if False else None; print('manual check: only stdlib imports (math) should appear in main.py')"`

Actually run instead: `grep -n "^import\|^from" main.py`
Expected: only `import math` (or equivalent stdlib-only imports) — no `kaggle_environments` import inside `main.py` itself (that's a dev/test-only dependency).

- [ ] **Step 2: Verify the file loads standalone**

Run: `python -c "import importlib.util; spec = importlib.util.spec_from_file_location('m', 'main.py'); m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m); print(m.agent({}))"`
Expected: prints `{'farmer': ['PASS'], 'hands': [], 'market': []}` with no traceback.

- [ ] **Step 3: Report readiness**

No commit needed — this task only verifies submission-readiness. If the user wants to submit, run the `kaggle competitions submit kaggriculture -f main.py -m "..."` command from `AGENTS.md`, with their confirmation first (it's a shared/visible action against a live competition).
