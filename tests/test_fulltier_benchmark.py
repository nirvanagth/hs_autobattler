"""Frozen full-tier benchmark contract tests."""

import json
from pathlib import Path

from hearthstone.env.lobby_env import BattlegroundsLobbyEnv
from scripts.verify_fulltier_platform import runtime_pool_digest


ROOT = Path(__file__).resolve().parent.parent


def test_fulltier_benchmark_matches_runtime_contract() -> None:
    benchmark = json.loads(
        (ROOT / "benchmarks/hsbg_8p_fulltier_v1.json").read_text()
    )
    profile = json.loads((ROOT / benchmark["content"]["profile_path"]).read_text())
    env = BattlegroundsLobbyEnv(
        max_tier=6,
        behavior_version=6,
        content_profile=profile,
    )
    assert env.lobby_environment_contract == benchmark["environment_contract"]
    assert runtime_pool_digest(profile) == benchmark["content"]["runtime_pool_sha256"]


def test_fulltier_lifecycle_gate_is_complete_and_seat_balanced() -> None:
    benchmark = json.loads(
        (ROOT / "benchmarks/hsbg_8p_fulltier_v1.json").read_text()
    )
    gate = benchmark["lifecycle_gate"]
    assert gate["status"] == "passed"
    assert gate["games"] == 100000
    assert sum(gate["winner_counts"].values()) == 100000
    assert gate["max_seat_win_rate"] - gate["min_seat_win_rate"] < 0.005
