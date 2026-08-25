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
    assert ["BUY_SEED", "WHEAT", 8] in result["market"] or ["BUY_SEED", "WHEAT", 1] in result["market"]


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
