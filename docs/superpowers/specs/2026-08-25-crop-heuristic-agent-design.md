# Kaggriculture V1: Crops-Only Heuristic Agent — Design

## Goal

Build a rule-based agent for the Kaggriculture Kaggle simulation competition that beats the
built-in `starter` and `random` baselines using a crop-only strategy (no animals in V1).
Optimize for cash growth over the 720-turn / 30-day season via wheat/carrot early game,
melon and ongoing crops (tomato/strawberry) as cash and land allow.

## Non-Goals (V1)

- No animals (goose/cow/sheep, coops/pastures, feeding/care loop) — deferred to V2.
- No opponent modeling / adaptive counter-play — plays the same strategy regardless of
  opponent behavior.
- No learned/optimized policy — pure heuristics, no training loop.

## Architecture

- Single `main.py`, submitted as-is (Kaggle requires `main.py` at submission root; single
  file avoids tar.gz packaging).
- Sections within the file: constants (game data tables), planner (task queue + unit
  assignment), market logic (buy/sell/hire/land), agent entrypoint (`agent(obs)`).
- **Stateless per turn**: every decision is re-derived fresh from `obs` each call, since
  `obs["farms"][player]["tiles"]` is a full, authoritative view of farm state. The only
  value carried across calls is a small per-resource sell-throttle counter (module-level
  dict, reset at the start of each in-game day) — if the process restarts and this resets
  early, the agent just re-throttles conservatively, no correctness impact.
- Local test loop via `kaggle_environments.make(...)` + `env.run([main.py, "random"/"starter"])`.

## Components & Data Flow

Per turn, `agent(obs)` runs a one-way pipeline: obs → task queue → unit assignment →
action dict. No mutation of `obs`.

1. **Task queue builder** — single scan over `me["tiles"]`, emitting tagged tasks:
   `WATER`, `HARVEST`, `DIG` (weed), `FERTILIZE`, `PLANT` (empty tile, per rotation
   target). Priority order: water > harvest > dig weed > fertilize > plant. (Feed/care
   tasks omitted in V1 — no animals.)
2. **Assignment** — greedy nearest-unit-to-highest-priority-task match for the farmer and
   each hand, using Manhattan distance. Not globally optimal, but cheap and sufficient
   given small unit counts. Each tile is claimed once matched, so no two units double-book
   the same task in a turn.
3. **Move-or-act** — if the assigned unit isn't on its target tile, emit a single-step
   move (N/S/E/W) toward it; if already there, emit the task's op. Units with no task
   move toward the shed (staging for next pickup/plant cycle) rather than thrashing.
4. **Rotation plan** — pure function `(day, cash, tile_count) -> {crop: target_fraction}`
   driving what new `PLANT` tasks target:
   - Phase 1 (day 0+): wheat/carrot split (fast cash, low seed-cost risk).
   - Phase 2 (cash ≥ melon-seed affordability buffer): shift new plantings toward melon
     (high base price, weak scarcity reaction, but crashes hard on glut — sell throttled).
   - Phase 3 (surplus cash + high idle-tile churn): introduce tomato/strawberry to reduce
     replant frequency via ongoing yields.
   - If the target crop's seed cost exceeds available cash, fall back to wheat (cheapest)
     rather than blocking the plant task.
5. **Market orders** — built as an independent pass after farm tasks:
   - Seed restock: top up seed inventory to cover near-term queued `PLANT` tasks.
   - Throttled `SELL`: per-resource cap per turn, spread over multiple turns to avoid
     walking the price down; skip a resource near the $1 floor unless shed is >90% full
     (forced sell to avoid end-of-day discard).
   - `HIRE`: ROI-gated — hire only if the estimated marginal value of the current task
     backlog exceeds `fib(hires_today)` cost for that hire.
   - `BUY_LAND`: only once unlocked-tile utilization exceeds ~80%.
   - `BUY_PRODUCT FERTILIZER`: top up fertilizer stock (gated by the same cash-surplus
     signal as rotation-plan Phase 2/3) whenever the task queue has pending `FERTILIZE`
     tasks and shed fertilizer is 0 — V1 has no animals, so fertilizer only comes from
     the market, never from `COLLECT_FERTILIZER`.

## Error Handling & Edge Cases

- `agent()` wraps per-turn logic in try/except; any exception falls back to
  `{"farmer": ["PASS"], "hands": [], "market": []}`. A crash mid-episode is an automatic
  loss, so this is the top-priority safety net.
- Shed >90% full forces sell-throttle override (avoid discard-on-drop at end of day).
- No affordable seed + empty tile + no other task → unit idles toward the shed instead of
  looping in place.
- Hand spawned on a locked tile: no special-casing needed — locked tiles never produce a
  valid task target, so assignment naturally routes the unit off it via move-toward-task
  or move-toward-shed.
- Two units cannot race the same tile: assignment marks a tile claimed once matched per
  turn.

## Testing

- Local harness script (not committed — scratch use only) running
  `env.run([main.py, "starter"])` and `env.run([main.py, "random"])`, asserting final
  money beats baseline across multiple seeded runs (variance from weed-spawn RNG and
  opponent randomness).
- Unit-level checks on pure functions with no env dependency:
  - `rotation_plan(day, cash, tile_count)` → expected crop split, given fixed inputs.
  - Task-queue builder given a synthetic tile grid → expected task list.
  - Assignment given synthetic units + tasks → expected pairing.
- Manual replay inspection: dump `replay.json` from a full local run, spot-check for
  stuck units, weed accumulation, and price crashes on sell.
- No CI — this is a single competition submission script; testing is a pre-submit gate,
  run manually before each `kaggle competitions submit`.

## Open Questions / Future Work (not blocking V1)

- V2: add animals (goose/cow/sheep) once the crop loop is validated and stable.
- Tune rotation-plan phase thresholds (cash buffers, tile-churn signal, fertilizer
  purchase volume) empirically against replay data once V1 is running.
