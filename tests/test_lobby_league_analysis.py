"""Paired league report analysis tests."""

import pytest

from scripts.compare_lobby_league import compare


def report(policy_id, placements, schedule="abc"):
    games = []
    for seed, placement in enumerate(placements):
        games.append(
            {
                "seed": seed,
                "candidate_seat": 0,
                "candidate_placement": placement,
                "lineup": [policy_id, "a", "b", "c", "d", "e", "f", "g"],
                "placements": list(range(1, 9)),
            }
        )
    return {"candidate_id": policy_id, "schedule_sha256": schedule, "games": games}


def test_compare_reports_paired_improvements() -> None:
    result = compare(report("parent", [5, 6]), report("new", [3, 4]), seed=7)
    assert result["placement_improvement"]["mean"] == 2.0
    assert result["top4_advantage"]["mean"] == 1.0


def test_compare_rejects_different_schedules() -> None:
    with pytest.raises(ValueError, match="same frozen schedule"):
        compare(report("parent", [5], "a"), report("new", [3], "b"), seed=7)
