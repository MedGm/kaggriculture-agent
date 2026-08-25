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
