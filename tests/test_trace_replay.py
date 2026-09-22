"""Frozen overlap selection and behavior-v7 replay tests."""

import json
import subprocess
import sys
from pathlib import Path

import pytest

from hearthstone.traces.replay import (
    build_overlap_contract,
    replay_transition,
    select_replayable_transition,
    sha256_file,
    summarize_replay_decisions,
    validate_overlap_contract,
)


ROOT = Path(__file__).resolve().parent.parent
PROFILE_PATH = ROOT / "benchmarks/hsbg_content_profile_v7_fulltier.json"
ALIASES_PATH = ROOT / "benchmarks/live_card_aliases_v1.json"
CONTRACT_PATH = ROOT / "benchmarks/hsbg_trace_overlap_contract_v1.json"


def _entity(entity_id, card_id, controller, zone, position=None, **tags):
    entity_tags = {"CONTROLLER": controller, "ZONE": zone, **tags}
    if position is not None:
        entity_tags["ZONE_POSITION"] = position
    return {"entity_id": entity_id, "card_id": card_id, "tags": entity_tags}


def _contract():
    return json.loads(CONTRACT_PATH.read_text())


def _profile():
    return json.loads(PROFILE_PATH.read_text())


def _buy_transition(extra_before=None):
    target_before = _entity(
        323,
        "BGS_119",
        13,
        "PLAY",
        1,
        ATK=2,
        HEALTH=1,
        TECH_LEVEL=1,
    )
    target_after = _entity(
        323,
        "BGS_119",
        5,
        "HAND",
        1,
        ATK=2,
        HEALTH=1,
        TECH_LEVEL=1,
    )
    button_before = _entity(324, "TB_BaconShop_DragBuy", 5, "PLAY", COST=3)
    button_after = _entity(324, "TB_BaconShop_DragBuy", 5, "REMOVEDFROMGAME", COST=3)
    bob = _entity(68, "TB_BaconShopBob_SKIN_BZ", 13, "PLAY", HEALTH=30)
    before_entities = [bob, target_before, button_before]
    before_entities.extend(extra_before or [])
    return {
        "transition_index": 7,
        "session_index": 2,
        "action_type": "BUY",
        "block_type": "PLAY",
        "source_entity_id": 324,
        "source_card_id": "TB_BaconShop_DragBuy",
        "before": {"entities": before_entities},
        "after": {"entities": [bob, target_after, button_after]},
    }


def test_overlap_contract_is_reproducible_and_hash_pinned() -> None:
    profile = _profile()
    aliases = json.loads(ALIASES_PATH.read_text())
    rebuilt = build_overlap_contract(
        profile,
        aliases,
        profile_sha256=sha256_file(PROFILE_PATH),
        aliases_sha256=sha256_file(ALIASES_PATH),
    )
    assert rebuilt == _contract()
    assert rebuilt["behavior_version"] == 7
    assert len(rebuilt["alias_registry"]["supported_live_aliases"]) == 81
    validate_overlap_contract(rebuilt, PROFILE_PATH, ALIASES_PATH)


def test_overlap_contract_rejects_changed_dependency_hash(tmp_path) -> None:
    changed_profile = tmp_path / "profile.json"
    changed_profile.write_text(PROFILE_PATH.read_text() + " ")
    with pytest.raises(ValueError, match="content profile hash"):
        validate_overlap_contract(_contract(), changed_profile, ALIASES_PATH)


def test_buy_selection_infers_player_shop_and_index() -> None:
    decision = select_replayable_transition(_buy_transition(), _contract())
    assert decision.eligible
    assert decision.comparison_mode == "deterministic"
    assert decision.player_controller == 5
    assert decision.shop_controller == 13
    assert decision.source_internal_id == "104"
    assert decision.simulator_action == "BUY"
    assert decision.action_kwargs == {"index": 0}


def test_unmapped_relevant_card_excludes_transition() -> None:
    unknown_board_card = _entity(
        900,
        "BG_UNKNOWN",
        5,
        "PLAY",
        1,
        ATK=4,
        HEALTH=4,
        TECH_LEVEL=1,
    )
    decision = select_replayable_transition(_buy_transition([unknown_board_card]), _contract())
    assert not decision.eligible
    assert decision.reasons == ("unmapped_board_card",)


def test_buy_transition_replays_into_behavior_v7() -> None:
    transition = _buy_transition()
    contract = _contract()
    decision = select_replayable_transition(transition, contract)
    result = replay_transition(transition, decision, contract, _profile(), seed=2_020_007)
    assert result["accepted"]
    assert result["simulator_before"]["shop"][0]["internal_card_id"] == "104"
    assert result["simulator_after"]["shop"] == []
    assert result["simulator_after"]["hand"][0]["internal_card_id"] == "104"


def test_upgrade_transition_replays_tavern_tier() -> None:
    unrelated_unknown = _entity(
        900,
        "BG_UNKNOWN",
        5,
        "PLAY",
        1,
        ATK=4,
        HEALTH=4,
        TECH_LEVEL=1,
    )
    before_button = _entity(
        689,
        "TB_BaconShopTechUp02_Button",
        5,
        "PLAY",
        COST=4,
        TECH_LEVEL=2,
    )
    after_button = _entity(
        836,
        "TB_BaconShopTechUp03_Button",
        5,
        "PLAY",
        COST=7,
        TECH_LEVEL=3,
    )
    transition = {
        "transition_index": 8,
        "session_index": 2,
        "action_type": "UPGRADE",
        "block_type": "PLAY",
        "source_entity_id": 689,
        "source_card_id": "TB_BaconShopTechUp02_Button",
        "before": {"entities": [before_button, unrelated_unknown]},
        "after": {"entities": [after_button, unrelated_unknown]},
    }
    contract = _contract()
    decision = select_replayable_transition(transition, contract)
    assert decision.eligible
    result = replay_transition(transition, decision, contract, _profile(), seed=2)
    assert result["accepted"]
    assert result["simulator_before"]["tavern_tier"] == 1
    assert result["simulator_after"]["tavern_tier"] == 2


def test_unobserved_freeze_state_is_explicitly_excluded() -> None:
    transition = {
        "transition_index": 9,
        "session_index": 2,
        "action_type": "FREEZE",
        "block_type": "PLAY",
        "source_entity_id": 308,
        "source_card_id": "TB_BaconShopLockAll_Button",
        "before": {"entities": []},
        "after": {"entities": []},
    }
    decision = select_replayable_transition(transition, _contract())
    assert not decision.eligible
    assert decision.reasons == ("freeze_state_unobserved",)


def test_selection_summary_counts_each_exclusion_reason() -> None:
    eligible = select_replayable_transition(_buy_transition(), _contract())
    excluded = select_replayable_transition(
        _buy_transition([_entity(999, "BG_UNKNOWN", 5, "HAND", 1, ATK=1, HEALTH=1)]),
        _contract(),
    )
    summary = summarize_replay_decisions([eligible, excluded])
    assert summary["eligible_transitions"] == 1
    assert summary["eligible_action_counts"] == {"BUY": 1}
    assert summary["eligible_comparison_mode_counts"] == {"deterministic": 1}
    assert summary["exclusion_reason_counts"] == {"unmapped_hand_card": 1}


def test_replay_cli_does_not_store_input_paths(tmp_path) -> None:
    private_input = tmp_path / "private_player_name.jsonl"
    private_input.write_text(json.dumps(_buy_transition()) + "\n")
    output = tmp_path / "replay"
    subprocess.run(
        [
            sys.executable,
            str(ROOT / "scripts/replay_trace_actions.py"),
            "--transitions",
            str(private_input),
            "--contract",
            str(CONTRACT_PATH),
            "--profile",
            str(PROFILE_PATH),
            "--aliases",
            str(ALIASES_PATH),
            "--out-dir",
            str(output),
        ],
        check=True,
        cwd=ROOT,
        capture_output=True,
        text=True,
    )
    encoded = "\n".join(path.read_text() for path in output.iterdir())
    assert "private_player_name" not in encoded
    assert json.loads((output / "report.json").read_text())["replay"]["accepted"] == 1
