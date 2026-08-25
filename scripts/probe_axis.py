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
