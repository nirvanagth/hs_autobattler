"""Tests for DAgger collection and episode-safe aggregation."""

from __future__ import annotations

import random

import numpy as np

from hearthstone.env.hs_env import HearthstoneEnv
from scripts.dagger_aggregate import select_complete_episodes
from scripts.dagger_collect import query_expert_preserving_rng


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
