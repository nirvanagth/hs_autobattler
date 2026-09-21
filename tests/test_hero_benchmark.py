"""Frozen behavior-v7 hero benchmark tests."""

import json
from pathlib import Path

from hearthstone.engine.heroes import HERO_IDS, hero_registry_payload, hero_registry_sha256
from hearthstone.env.lobby_env import BattlegroundsLobbyEnv
from hearthstone.league import file_sha256


ROOT = Path(__file__).resolve().parent.parent


def test_tracked_hero_registry_matches_runtime() -> None:
    tracked = json.loads((ROOT / "benchmarks/hero_registry_v1.json").read_text())
    assert tracked == hero_registry_payload()
    assert hero_registry_sha256() == (
        "d7e61cd93768c17ca072e8b01752eb45e30d146d876ea8603c58c0d663c5f4b8"
    )


def test_hero_benchmark_matches_runtime_contract() -> None:
    benchmark = json.loads((ROOT / "benchmarks/hsbg_8p_heroes_v1.json").read_text())
    artifacts = benchmark["artifacts"]
    assert file_sha256(ROOT / artifacts["hero_registry_path"]) == artifacts[
        "hero_registry_file_sha256"
    ]
    assert file_sha256(ROOT / artifacts["content_profile_path"]) == artifacts[
        "content_profile_file_sha256"
    ]
    profile = json.loads((ROOT / artifacts["content_profile_path"]).read_text())
    env = BattlegroundsLobbyEnv(
        max_tier=6,
        behavior_version=7,
        content_profile=profile,
        hero_ids=list(HERO_IDS),
    )
    assert env.lobby_environment_contract == benchmark["environment_contract"]


def test_hero_matrix_passes_declared_balance_gate() -> None:
    benchmark = json.loads((ROOT / "benchmarks/hsbg_8p_heroes_v1.json").read_text())
    matrix = benchmark["matrix"]
    gate = benchmark["gate"]
    assert matrix["status"] == "passed"
    assert matrix["max_mean_placement"] - matrix["min_mean_placement"] <= gate[
        "max_mean_placement_spread"
    ]
    assert matrix["max_win_rate"] - matrix["min_win_rate"] <= gate[
        "max_win_rate_spread"
    ]
    assert max(
        abs(matrix["min_pairwise_score_rate"] - 0.5),
        abs(matrix["max_pairwise_score_rate"] - 0.5),
    ) <= gate["max_pairwise_deviation_from_half"]
