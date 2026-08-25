# tests/test_agent_smoke.py
import main


def test_agent_survives_empty_obs():
    result = main.agent({})
    assert result == {"farmer": ["PASS"], "hands": [], "market": []}


def test_agent_survives_malformed_obs():
    result = main.agent({"player": 0, "farms": None})
    assert result == {"farmer": ["PASS"], "hands": [], "market": []}
