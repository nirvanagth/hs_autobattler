"""Privacy-safe Power.log parsing, reconstruction, and comparison tests."""

import json
from pathlib import Path

from hearthstone.traces.conformance import compare_states, compare_transition_streams
from hearthstone.traces.powerlog import (
    event_json,
    load_power_log,
    reconstruct_transitions,
)
from hearthstone.traces.simulator_state import normalize_lobby
from hearthstone.engine.lobby import LobbyGame


ROOT = Path(__file__).resolve().parent.parent
FIXTURE = ROOT / "tests/fixtures/powerlog_synthetic.txt"


def test_parser_redacts_names_and_unknown_tag_values() -> None:
    result = load_power_log(FIXTURE)
    serialized = "\n".join(event_json(event) for event in result.events)
    assert "Private Player Name" not in serialized
    assert "Account#1234" not in serialized
    assert result.ignored_tag_counts == {"SECRET_ACCOUNT": 1}
    assert [event.event_type for event in result.events].count("full_entity") == 2


def test_reconstruction_builds_top_level_play_transition() -> None:
    transitions = reconstruct_transitions(load_power_log(FIXTURE).events)
    assert len(transitions) == 1
    transition = transitions[0]
    assert transition["block_type"] == "PLAY"
    assert transition["source_entity_id"] == 10
    before = next(
        entity for entity in transition["before"]["entities"] if entity["entity_id"] == 10
    )
    after = next(
        entity for entity in transition["after"]["entities"] if entity["entity_id"] == 10
    )
    assert before["tags"]["ZONE"] == "HAND"
    assert after["tags"]["ZONE"] == "PLAY"
    assert before["tags"]["ATK"] == 3
    assert after["tags"]["ATK"] == 5


def test_parser_is_deterministic() -> None:
    first = [event_json(event) for event in load_power_log(FIXTURE).events]
    second = [event_json(event) for event in load_power_log(FIXTURE).events]
    assert first == second


def test_conformance_reports_field_categories() -> None:
    expected = {
        "entities": [
            {
                "entity_id": 10,
                "card_id": "BG_TEST_MINION",
                "tags": {"CONTROLLER": 1, "ZONE": "PLAY", "ZONE_POSITION": 1, "ATK": 5},
            }
        ]
    }
    actual = json.loads(json.dumps(expected))
    assert compare_states(expected, actual)["match"]
    actual["entities"][0]["tags"]["ATK"] = 4
    report = compare_states(expected, actual)
    assert not report["match"]
    assert report["mismatch_categories"] == {"tag:ATK": 1}


def test_simulator_lobby_normalization_is_deterministic() -> None:
    first = normalize_lobby(LobbyGame(seed=31))
    second = normalize_lobby(LobbyGame(seed=31))
    assert first == second
    assert len(first["entities"]) > 8


def test_transition_conformance_aggregates_exact_and_mismatch_rates() -> None:
    state = {
        "entities": [
            {
                "entity_id": 1,
                "card_id": "A",
                "tags": {"CONTROLLER": 1, "ZONE": "PLAY", "ZONE_POSITION": 1, "ATK": 2},
            }
        ]
    }
    expected = [
        {"transition_index": 0, "block_type": "PLAY", "after": state},
        {"transition_index": 1, "block_type": "POWER", "after": state},
    ]
    changed = json.loads(json.dumps(state))
    changed["entities"][0]["tags"]["ATK"] = 1
    actual = [
        {"transition_index": 0, "block_type": "PLAY", "after": state},
        {"transition_index": 1, "block_type": "POWER", "after": changed},
    ]
    report = compare_transition_streams(expected, actual)
    assert report["exact_transition_rate"] == 0.5
    assert report["mismatch_categories"] == {"tag:ATK": 1}
