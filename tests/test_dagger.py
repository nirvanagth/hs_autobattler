"""Tests for DAgger collection and episode-safe aggregation."""

from __future__ import annotations

import random

import numpy as np

from hearthstone.env.hs_env import HearthstoneEnv
from scripts.dagger_aggregate import select_complete_episodes
from scripts.dagger_collect import query_expert_preserving_rng
from scripts.evaluate_recovery import (
    aggregate,
    choose_perturbation,
    deterministic_rng,
    random_nonexpert_action,
)


def test_expert_query_preserves_python_and_numpy_rng() -> None:
    env = HearthstoneEnv()
    env.reset(seed=42)
    weights = np.zeros(23, dtype=np.float32)

    def consuming_expert(_env, _weights):
        random.random()
        np.random.random()
        return 0

    python_state = random.getstate()
    numpy_state = np.random.get_state()
    expected_python = random.random()
    expected_numpy = np.random.random()
    random.setstate(python_state)
    np.random.set_state(numpy_state)

    assert query_expert_preserving_rng(env, weights, consuming_expert) == 0
    assert random.random() == expected_python
    assert np.random.random() == expected_numpy


def test_dagger_sampling_keeps_complete_episodes() -> None:
    episode_ids = np.asarray([0, 0, 1, 1, 1, 2, 2, 3], dtype=np.int32)
    selected = select_complete_episodes(episode_ids, target_rows=4, seed=7)

    assert selected.sum() >= 4
    for episode in np.unique(episode_ids):
        rows = selected[episode_ids == episode]
        assert rows.all() or not rows.any()


def test_dagger_sampling_is_deterministic() -> None:
    episode_ids = np.repeat(np.arange(10, dtype=np.int32), 3)
    first = select_complete_episodes(episode_ids, target_rows=12, seed=99)
    second = select_complete_episodes(episode_ids, target_rows=12, seed=99)
    assert np.array_equal(first, second)


def test_recovery_perturbation_is_legal_and_nonexpert() -> None:
    rng = deterministic_rng(42, "random_nonexpert", 5)
    action = random_nonexpert_action([0, 1, 2, 5], expert_action=2, rng=rng)
    assert action in {1, 5}


def test_premature_end_perturbation() -> None:
    env = HearthstoneEnv()
    env.reset(seed=42)
    mask = env.action_masks().copy()
    action, kind = choose_perturbation(
        env,
        mask,
        expert_action=2,
        perturbation="premature_end",
        rng=deterministic_rng(42, "premature_end", 5),
    )
    assert action == 0
    assert kind == "premature_end"


def test_recovery_aggregate_computes_paired_delta() -> None:
    rows = [
        {
            "candidate": "bc",
            "perturbation": "clean",
            "target_turn": 5,
            "seed": 1,
            "perturbation_applied": True,
            "score": 1.0,
            "outcome": "win",
            "health_margin": 10,
        },
        {
            "candidate": "bc",
            "perturbation": "premature_end",
            "target_turn": 5,
            "seed": 1,
            "perturbation_applied": True,
            "score": 0.0,
            "outcome": "loss",
            "health_margin": -5,
        },
    ]
    report = aggregate(rows)
    delta = report["recovery"]["bc|turn=5|premature_end"]
    assert delta["score_delta_from_clean"]["mean"] == -1.0
    assert delta["health_delta_from_clean"]["mean"] == -15.0


def test_recovery_aggregate_compares_candidate_recovery() -> None:
    rows = []
    for candidate, clean, perturbed in (("bc", 1.0, 0.0), ("dagger", 1.0, 0.5)):
        rows.extend(
            [
                {
                    "candidate": candidate,
                    "perturbation": "clean",
                    "target_turn": 5,
                    "seed": 1,
                    "perturbation_applied": True,
                    "score": clean,
                    "outcome": "win",
                    "health_margin": 10,
                },
                {
                    "candidate": candidate,
                    "perturbation": "sell_strongest",
                    "target_turn": 5,
                    "seed": 1,
                    "perturbation_applied": True,
                    "score": perturbed,
                    "outcome": "loss",
                    "health_margin": 0 if candidate == "bc" else 5,
                },
            ]
        )
    comparison = aggregate(rows)["comparisons"][
        "dagger_vs_bc|turn=5|sell_strongest"
    ]
    assert comparison["perturbed_score_advantage"]["mean"] == 0.5
    assert comparison["recovery_score_advantage"]["mean"] == 0.5
