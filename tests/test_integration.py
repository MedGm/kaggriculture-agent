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


def test_agent_routes_first_hand_to_animal_duty_and_rest_to_crops():
    obs = _synthetic_obs()
    obs["farms"][0]["hands"] = [[3, 4], [7, 7]]  # hand 0 on the COOP zone tile, hand 1 elsewhere
    obs["private"]["seeds"] = {"WHEAT": 5}
    obs["private"]["inventories"] = [{}, {}, {}]  # farmer, hand0 (animal), hand1 (crop)
    result = main.agent(obs)
    assert len(result["hands"]) == 2
    # hand 0 stands exactly on the COOP zone tile with no animal placed yet -> BUILD_COOP.
    assert result["hands"][0] == ["BUILD_COOP"]
    # hand 1 is a normal crop hand: some valid op, not an animal-only op.
    assert result["hands"][1][0] not in ("FEED", "BUILD_COOP", "BUILD_PASTURE", "PLACE", "CARE", "COLLECT_FERTILIZER")


def test_agent_market_orders_include_mandatory_hire_first_when_no_hires_yet():
    obs = _synthetic_obs()
    result = main.agent(obs)
    assert result["market"][0] == ["HIRE"]


def test_agent_routes_second_hand_to_setup_helper_when_zone_incomplete():
    obs = _synthetic_obs()
    # hand0 = animal hand (on COOP zone tile, empty -> BUILD_COOP is its job).
    # hand1 = second hand, placed at the SHEEP pasture zone tile (also empty).
    coop_xy = main.ANIMAL_ZONE["COOP"]
    sheep_xy = main.ANIMAL_ZONE["PASTURE_2"]
    obs["farms"][0]["hands"] = [list(coop_xy), list(sheep_xy)]
    obs["private"]["inventories"] = [{}, {}, {}]
    result = main.agent(obs)
    assert len(result["hands"]) == 2
    assert result["hands"][0] == ["BUILD_COOP"]
    # hand1 standing on the SHEEP pasture zone tile, empty -> helper builds it directly.
    assert result["hands"][1] == ["BUILD_PASTURE"]


def test_agent_folds_second_hand_into_crop_work_once_zone_complete():
    obs = _synthetic_obs()
    for animal, kind, xy in main.ZONE_ANIMALS:
        x, y = xy
        obs["farms"][0]["tiles"][y][x] = {
            "kind": kind, "animal": animal, "fed_today": True,
            "yield_units": 0, "cared_today": True, "fertilizer_available": False,
        }
    obs["farms"][0]["hands"] = [[4, 4], [7, 7]]  # hand0 at shed, hand1 elsewhere
    obs["private"]["inventories"] = [{}, {}, {}]
    obs["private"]["seeds"] = {"WHEAT": 5}
    result = main.agent(obs)
    assert len(result["hands"]) == 2
    # hand1's op must NOT be a setup op (no zone tiles left to build/deliver) --
    # it's now a normal crop-hand op from the ordinary dispatch_unit pipeline.
    assert result["hands"][1][0] not in ("BUILD_COOP", "BUILD_PASTURE", "PICKUP", "PLACE")


def test_agent_market_orders_include_both_mandatory_hires_first():
    obs = _synthetic_obs()
    result = main.agent(obs)
    assert result["market"][0] == ["HIRE"]
    assert result["market"][1] == ["HIRE"]
