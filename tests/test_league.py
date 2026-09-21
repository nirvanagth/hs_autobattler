"""Policy league registry, rating, and PFSP tests."""

from pathlib import Path

import pytest

from hearthstone.league import PolicyEntry, PolicyLeague, file_sha256


def entry(
    policy_id: str,
    path: Path,
    *,
    kind: str = "test",
    contract: dict | None = None,
) -> PolicyEntry:
    return PolicyEntry(
        policy_id=policy_id,
        kind=kind,
        artifact_path=str(path),
        artifact_sha256=file_sha256(path),
        environment_contract=contract,
    )


def test_policy_entries_are_immutable(tmp_path: Path) -> None:
    artifact = tmp_path / "policy.bin"
    artifact.write_bytes(b"policy")
    league = PolicyLeague()
    league.add_policy(entry("main", artifact))
    league.add_policy(entry("main", artifact))
    with pytest.raises(ValueError, match="immutable"):
        league.add_policy(
            PolicyEntry("main", "other", str(artifact), file_sha256(artifact))
        )


def test_result_updates_both_matchups_and_zero_sum_rating(tmp_path: Path) -> None:
    first = tmp_path / "first"
    second = tmp_path / "second"
    first.write_bytes(b"a")
    second.write_bytes(b"b")
    league = PolicyLeague()
    league.add_policy(entry("first", first))
    league.add_policy(entry("second", second))
    league.record_result("first", "second", 1.0)
    assert league.matchups["first"]["second"].score_rate == 1.0
    assert league.matchups["second"]["first"].score_rate == 0.0
    assert league.ratings["first"] + league.ratings["second"] == 2000.0


def test_pfsp_prefers_opponents_learner_struggles_against(tmp_path: Path) -> None:
    league = PolicyLeague()
    for policy_id in ("learner", "easy", "hard"):
        artifact = tmp_path / policy_id
        artifact.write_text(policy_id)
        league.add_policy(entry(policy_id, artifact))
    league.record_series("learner", "easy", wins=90, losses=10)
    league.record_series("learner", "hard", wins=10, losses=90)
    sampled = league.sample_opponents("learner", 1000, seed=42)
    assert sampled.count("hard") > 5 * sampled.count("easy")


def test_series_rating_is_independent_of_result_order(tmp_path: Path) -> None:
    leagues = []
    for suffix in ("a", "b"):
        league = PolicyLeague()
        for policy_id in ("first", "second"):
            artifact = tmp_path / f"{suffix}_{policy_id}"
            artifact.write_text(policy_id)
            league.add_policy(entry(policy_id, artifact))
        leagues.append(league)
    leagues[0].record_series("first", "second", wins=60, losses=40)
    leagues[1].record_series("second", "first", wins=40, losses=60)
    assert leagues[0].ratings == leagues[1].ratings


def test_pfsp_excludes_incompatible_neural_contracts(tmp_path: Path) -> None:
    league = PolicyLeague()
    specs = {
        "learner": ("neural", {"name": "lobby"}),
        "compatible": ("neural", {"name": "lobby"}),
        "wrong_env": ("neural", {"name": "1v1"}),
        "smart": ("heuristic", None),
    }
    for policy_id, (kind, contract) in specs.items():
        artifact = tmp_path / policy_id
        artifact.write_text(policy_id)
        league.add_policy(entry(policy_id, artifact, kind=kind, contract=contract))
    sampled = league.sample_opponents("learner", 100, seed=42)
    assert "wrong_env" not in sampled
    assert set(sampled) == {"compatible", "smart"}


def test_promotion_requires_three_well_sampled_holdouts(tmp_path: Path) -> None:
    league = PolicyLeague()
    for policy_id in ("incumbent", "candidate", "h1", "h2", "h3"):
        artifact = tmp_path / policy_id
        artifact.write_text(policy_id)
        league.add_policy(entry(policy_id, artifact))
    league.bootstrap_main("incumbent", {"reason": "initial"})
    for holdout in ("h1", "h2", "h3"):
        league.record_series("incumbent", holdout, wins=100, losses=100)
        league.record_series("candidate", holdout, wins=110, losses=90)

    too_narrow = league.evaluate_promotion("candidate", ["h1", "h2"])
    assert not too_narrow.eligible
    decision = league.promote(
        "candidate", ["h1", "h2", "h3"], {"experiment": "matched"}
    )
    assert decision.eligible
    assert league.main_policy_id == "candidate"
    assert league.promotion_history[-1]["evidence"]["gate"]["mean_improvement"] == pytest.approx(0.05)


def test_promotion_rejects_catastrophic_holdout_regression(tmp_path: Path) -> None:
    league = PolicyLeague()
    for policy_id in ("incumbent", "candidate", "h1", "h2", "h3"):
        artifact = tmp_path / policy_id
        artifact.write_text(policy_id)
        league.add_policy(entry(policy_id, artifact))
    league.bootstrap_main("incumbent", {})
    for holdout in ("h1", "h2"):
        league.record_series("incumbent", holdout, wins=100, losses=100)
        league.record_series("candidate", holdout, wins=120, losses=80)
    league.record_series("incumbent", "h3", wins=100, losses=100)
    league.record_series("candidate", "h3", wins=80, losses=120)
    decision = league.evaluate_promotion("candidate", ["h1", "h2", "h3"])
    assert not decision.eligible
    assert decision.worst_improvement == pytest.approx(-0.1)


def test_save_load_and_artifact_verification(tmp_path: Path) -> None:
    artifact = tmp_path / "policy"
    artifact.write_bytes(b"stable")
    path = tmp_path / "league.json"
    league = PolicyLeague()
    league.add_policy(entry("main", artifact))
    league.bootstrap_main("main", {"reason": "initial"})
    league.save(path)
    loaded = PolicyLeague.load(path)
    assert loaded.main_policy_id == "main"
    artifact.write_bytes(b"changed")
    with pytest.raises(ValueError, match="hash mismatch"):
        PolicyLeague.load(path)
