"""Manual pre-submit gate: run main.py against baseline agents and report results."""
import os
from kaggle_environments import make


def run_match(opponent_name, episode_steps=720):
    # Ensure we're in the project root where main.py lives
    script_dir = os.path.dirname(os.path.abspath(__file__))
    project_root = os.path.dirname(script_dir)
    os.chdir(project_root)

    env = make("kaggriculture", configuration={"episodeSteps": episode_steps}, debug=False)
    env.run(["main.py", opponent_name])
    final = env.steps[-1]
    my_money = final[0].observation["farms"][0]["money"]
    opp_money = final[1].observation["farms"][1]["money"]
    print(f"vs {opponent_name}: main.py=${my_money:.0f}  opponent=${opp_money:.0f}  "
          f"{'WIN' if my_money > opp_money else 'LOSS' if my_money < opp_money else 'TIE'}")


if __name__ == "__main__":
    run_match("random")
    run_match("starter")
