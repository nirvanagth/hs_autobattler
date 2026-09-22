"""Deterministic and invariant trace replay comparison tests."""

import json
import subprocess
import sys
from pathlib import Path

from hearthstone.traces.replay_conformance import (
    compare_canonical_states,
    compare_invariants,
    compare_replay_results,
)


ROOT = Path(__file__).resolve().parent.parent
CONTRACT = json.loads((ROOT / "benchmarks/hsbg_trace_overlap_contract_v1.json").read_text())


def _item(entity_id, internal_id, position, tier=1, attack=2, health=2, damage=0):
    return {
        "entity_id": entity_id,
        "internal_card_id": internal_id,
        "position": position,
        "tier": tier,
        "attack": attack,
        "health": health,
        "damage": damage,
    }


def _state(tier=1, cost=5, board=None, hand=None, shop=None):
    return {
        "tavern_tier": tier,
        "upgrade_cost": cost,
        "board": board or [],
        "hand": hand or [],
        "shop": shop or [],
    }


def _result(action_type, before, after, simulator_after, mode="deterministic"):
    return {
        "input_index": 1,
        "transition_index": 2,
        "session_index": 3,
        "action_type": action_type,
        "comparison_mode": mode,
        "accepted": True,
        "trace_before": before,
        "trace_after": after,
        "simulator_before": before,
        "simulator_after": simulator_after,
    }


def test_canonical_zone_comparison_ignores_entity_id() -> None:
    expected = _state(board=[_item(10, "104", 1)])
    actual = _state(board=[_item(999, "104", 1)])
    comparison = compare_canonical_states(expected, actual, ["board"])
    assert comparison["match"]
    assert comparison["field_agreement_rate"] == 1.0


def test_upgrade_cost_mismatch_is_categorized() -> None:
    result = _result(
        "UPGRADE",
        _state(tier=3, cost=8),
        _state(tier=4, cost=11),
        _state(tier=4, cost=9),
    )
    report = compare_replay_results([result], CONTRACT)
    assert report["deterministic"]["evaluable"] == 1
    assert report["deterministic"]["mismatched"] == 1
    assert report["mismatch_categories"] == {"upgrade_cost": 1}


def test_deferred_upgrade_post_state_is_excluded() -> None:
    result = _result(
        "UPGRADE",
        _state(tier=2, cost=7),
        _state(tier=2, cost=7),
        _state(tier=3, cost=8),
    )
    report = compare_replay_results([result], CONTRACT)
    assert report["deterministic"]["evaluable"] == 0
    assert report["exclusion_reason_counts"] == {"trace_post_state_deferred": 1}


def test_final_upgrade_is_inferred_when_button_disappears() -> None:
    result = _result(
        "UPGRADE",
        _state(tier=5, cost=7),
        _state(tier=None, cost=None),
        _state(tier=6, cost=0),
    )
    report = compare_replay_results([result], CONTRACT)
    assert report["deterministic"]["exact"] == 1


def test_random_sell_compares_zone_and_tier_invariants() -> None:
    trace_before = _state(board=[_item(10, "115", 1)])
    trace_after = _state(hand=[_item(11, "102", 1, tier=1)])
    simulator_before = _state(board=[_item(10, "115", 1)])
    simulator_after = _state(hand=[_item(99, "101", 1, tier=1)])
    result = _result(
        "SELL",
        trace_before,
        trace_after,
        simulator_after,
        mode="invariant_only",
    )
    result["simulator_before"] = simulator_before
    comparison = compare_invariants(result)
    assert comparison["match"]
    report = compare_replay_results([result], CONTRACT)
    assert report["invariants"] == {
        "candidates": 1,
        "passed": 1,
        "failed": 0,
        "pass_rate": 1.0,
    }


def test_conformance_cli_does_not_store_input_path(tmp_path) -> None:
    result = _result(
        "UPGRADE",
        _state(tier=1, cost=5),
        _state(tier=2, cost=7),
        _state(tier=2, cost=7),
    )
    replay_path = tmp_path / "private_player_name.jsonl"
    replay_path.write_text(json.dumps(result) + "\n")
    output = tmp_path / "report.json"
    subprocess.run(
        [
            sys.executable,
            str(ROOT / "scripts/compare_trace_replays.py"),
            "--replay-results",
            str(replay_path),
            "--contract",
            str(ROOT / "benchmarks/hsbg_trace_overlap_contract_v1.json"),
            "--out",
            str(output),
        ],
        check=True,
        cwd=ROOT,
        capture_output=True,
        text=True,
    )
    encoded = output.read_text()
    assert "private_player_name" not in encoded
    assert json.loads(encoded)["conformance_gate"]["status"] == "passed"


def test_behavior_v8_trace_conformance_benchmark_passes() -> None:
    report = json.loads((ROOT / "benchmarks/hsbg_trace_conformance_v2.json").read_text())
    assert report["conformance_gate"]["status"] == "passed"
    assert report["comparison"]["deterministic"]["exact"] == 28
    assert report["comparison"]["deterministic"]["mismatched"] == 0
    assert report["comparison"]["invariants"]["failed"] == 0
