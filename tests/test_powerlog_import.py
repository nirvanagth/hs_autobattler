"""Privacy-safe Power.log parsing, reconstruction, and comparison tests."""

import json
from pathlib import Path

from hearthstone.traces.conformance import compare_states, compare_transition_streams
from hearthstone.traces.powerlog import (
    event_json,
    battlegrounds_session_ids,
    load_power_log,
    parse_power_log,
    reconstruct_transitions,
    reconstruct_action_transitions,
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
    assert {event.session_index for event in result.events} == {0}
    assert battlegrounds_session_ids(result.events) == {0}


def test_reconstruction_builds_top_level_play_transition() -> None:
    transitions = reconstruct_transitions(load_power_log(FIXTURE).events)
    assert len(transitions) == 1
    transition = transitions[0]
    assert transition["block_type"] == "PLAY"
    assert transition["source_entity_id"] == 10
    assert transition["session_index"] == 0
    before = next(
        entity for entity in transition["before"]["entities"] if entity["entity_id"] == 10
    )
    after = next(entity for entity in transition["after"]["entities"] if entity["entity_id"] == 10)
    assert before["tags"]["ZONE"] == "HAND"
    assert after["tags"]["ZONE"] == "PLAY"
    assert before["tags"]["ATK"] == 3
    assert after["tags"]["ATK"] == 5


def test_reconstruction_classifies_battlegrounds_control_cards() -> None:
    lines = [
        "CREATE_GAME\n",
        "BLOCK_START BlockType=PLAY Entity=[id=44 cardId=TB_BaconShop_8p_Reroll_Button]\n",
        "BLOCK_END\n",
    ]
    transition = reconstruct_transitions(parse_power_log(lines).events)[0]
    assert transition["source_card_id"] == "TB_BaconShop_8p_Reroll_Button"
    assert transition["action_type"] == "ROLL"


def test_action_classifier_ignores_nested_button_blocks_and_golden_minions() -> None:
    lines = [
        "CREATE_GAME\n",
        "BLOCK_START BlockType=POWER Entity=[id=44 cardId=TB_BaconShop_8p_Reroll_Button]\n",
        "BLOCK_END\n",
        "BLOCK_START BlockType=ATTACK Entity=[id=45 cardId=TB_BaconUps_079]\n",
        "BLOCK_END\n",
        "BLOCK_START BlockType=PLAY Entity=[id=46 cardId=TB_BaconUps_079]\n",
        "BLOCK_END\n",
        "BLOCK_START BlockType=PLAY Entity=[id=47 cardId=TB_BaconShopTechUp02_Button]\n",
        "BLOCK_END\n",
    ]
    transitions = reconstruct_action_transitions(parse_power_log(lines).events)
    assert [item["action_type"] for item in transitions] == ["PLAY_CARD", "UPGRADE"]


def test_nested_recruit_action_is_extracted_inside_trigger_block() -> None:
    lines = [
        "CREATE_GAME\n",
        "BLOCK_START BlockType=TRIGGER Entity=[id=1 cardId=TB_BaconShop_8P_PlayerE]\n",
        "BLOCK_START BlockType=PLAY Entity=[id=44 cardId=BG_TEST_MINION]\n",
        "BLOCK_END\n",
        "BLOCK_END\n",
    ]
    actions = reconstruct_action_transitions(parse_power_log(lines).events)
    assert len(actions) == 1
    assert actions[0]["action_type"] == "PLAY_CARD"
    assert actions[0]["source_card_id"] == "BG_TEST_MINION"


def test_parser_is_deterministic() -> None:
    first = [event_json(event) for event in load_power_log(FIXTURE).events]
    second = [event_json(event) for event in load_power_log(FIXTURE).events]
    assert first == second


def test_create_game_resets_state_between_sessions() -> None:
    lines = [
        "CREATE_GAME\n",
        "FULL_ENTITY - Creating ID=1 CardID=BG_FIRST\n",
        "tag=ZONE value=PLAY\n",
        "BLOCK_START BlockType=PLAY Entity=1\n",
        "BLOCK_END\n",
        "CREATE_GAME\n",
        "FULL_ENTITY - Creating ID=2 CardID=BG_SECOND\n",
        "tag=ZONE value=PLAY\n",
        "BLOCK_START BlockType=PLAY Entity=2\n",
        "BLOCK_END\n",
    ]
    result = parse_power_log(lines)
    transitions = reconstruct_transitions(result.events)
    assert [item["session_index"] for item in transitions] == [0, 1]
    assert [entity["card_id"] for entity in transitions[1]["after"]["entities"]] == ["BG_SECOND"]


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
