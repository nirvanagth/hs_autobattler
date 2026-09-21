"""Multi-policy lobby action driver tests."""

import numpy as np
import pytest
import torch

from hearthstone.engine.cpp_bridge import get_cpp_engine
from hearthstone.env.smart_bot import smart_bot_turn
from hearthstone.league import PolicyEntry, PolicyLeague, file_sha256
from hearthstone.lobby_arena import CENTRAL_OBSERVATION_SIZE, LobbyArena
from scripts.lobby_league_runtime import LeagueLobbyEnv
from scripts.lobby_bc_collect import smart_pick_action
from scripts.lobby_model import LobbyPointerAgent
from scripts.lobby_search import DepthOnePlanner


def test_player_targeting_state_is_isolated() -> None:
    arena = LobbyArena(seed=7)
    arena.player_states[0].is_targeting = True
    arena.player_states[0].pending_target_kind = "SPELL"
    assert arena.observation(0)[6] == 1.0
    assert arena.observation(1)[6] == 0.0


def test_masked_end_turn_advances_only_after_all_players_ready() -> None:
    arena = LobbyArena(seed=11)
    starting_turn = arena.game.turn_count
    for player_id in range(7):
        result = arena.apply_action(player_id, 0)
        assert result.accepted
        assert arena.game.turn_count == starting_turn
    result = arena.apply_action(7, 0)
    assert result.accepted
    assert arena.game.turn_count == starting_turn + 1


def test_central_observation_contains_hidden_shop_state() -> None:
    arena = LobbyArena(seed=9)
    public_before = arena.observation(0)
    central_before = arena.central_observation()
    hidden_store = arena.game.players[1].store[0]
    assert hidden_store.unit is not None
    hidden_store.unit.cur_atk += 7
    assert np.array_equal(public_before, arena.observation(0))
    assert not np.array_equal(central_before, arena.central_observation())
    assert arena.central_observation().shape == (CENTRAL_OBSERVATION_SIZE,)


def test_snapshot_restore_replays_random_tavern_action() -> None:
    arena = LobbyArena(seed=21)
    before = arena.observation(0)
    snapshot = arena.snapshot()
    first = arena.apply_action(0, 1)
    first_child = arena.observation(0)
    assert first.accepted
    assert not np.array_equal(before, first_child)
    arena.restore(snapshot)
    assert np.array_equal(before, arena.observation(0))
    second = arena.apply_action(0, 1)
    assert second.accepted
    assert np.array_equal(first_child, arena.observation(0))


def test_depth_one_search_is_non_mutating_and_returns_legal_action() -> None:
    arena = LobbyArena(seed=22)
    model = LobbyPointerAgent(
        num_card_ids=arena.env.num_card_ids,
        d_model=32,
        n_heads=4,
        n_layers=1,
    ).eval()
    before = arena.observation(0)
    mask = arena.action_mask(0)
    result = DepthOnePlanner(model, torch.device("cpu")).choose_action(arena, 0)
    assert mask[result.action]
    assert result.expanded_actions == int(mask.sum())
    assert np.array_equal(before, arena.observation(0))


def test_action_policy_can_finish_a_full_lobby() -> None:
    arena = LobbyArena(seed=13)

    def first_legal(_observation, mask, _player_id):
        return int(np.flatnonzero(mask)[0])

    while not arena.game.game_over:
        for player_id in sorted(arena.game.active_player_ids):
            if player_id == 0:
                arena.play_action_turn(player_id, first_legal)
            else:
                smart_bot_turn(arena.game, player_id)
    assert sorted(arena.game.placements.values()) == list(range(1, 9))


def test_league_training_env_rotates_seat_and_finishes(tmp_path) -> None:
    artifact = tmp_path / "smart.py"
    artifact.write_text("smart")
    league = PolicyLeague()
    league.add_policy(
        PolicyEntry(
            policy_id="smart",
            kind="heuristic_lobby_smart",
            artifact_path=str(artifact),
            artifact_sha256=file_sha256(artifact),
        )
    )
    league.bootstrap_main("smart", {})
    env = LeagueLobbyEnv(league, "smart", seed=8, device=torch.device("cpu"))
    observation, info = env.reset(seed=11)
    assert observation.shape == env.observation_space.shape
    assert info["learner_seat"] == 3
    terminated = truncated = False
    combat_targets = 0
    while not (terminated or truncated):
        action = int(np.flatnonzero(env.action_masks())[0])
        _, _, terminated, truncated, info = env.step(action)
        if info["combat_target_valid"]:
            combat_targets += 1
            assert info["combat_outcome"] in (0, 1, 2)
            assert -1.0 <= info["combat_damage"] <= 1.0
    assert info["placement"] in range(1, 9)
    assert env.learner_seat not in env.arena.game.active_player_ids
    assert combat_targets > 0


@pytest.mark.skipif(get_cpp_engine() is None, reason="C++ combat engine unavailable")
def test_lobby_oracle_potential_is_deterministic(tmp_path) -> None:
    artifact = tmp_path / "smart.py"
    artifact.write_text("smart")
    league = PolicyLeague()
    league.add_policy(
        PolicyEntry(
            policy_id="smart",
            kind="heuristic_lobby_smart",
            artifact_path=str(artifact),
            artifact_sha256=file_sha256(artifact),
        )
    )

    def rollout():
        env = LeagueLobbyEnv(
            league,
            "smart",
            seed=15,
            device=torch.device("cpu"),
            reward_mode="oracle_potential",
            oracle_n_combats=8,
        )
        env.reset(seed=15)
        shaping = []
        for _ in range(30):
            env.arena._activate(env.learner_seat)
            action = smart_pick_action(env.arena.env)
            _, _, terminated, truncated, info = env.step(action)
            shaping.append(info["oracle_shaping"])
            if terminated or truncated:
                break
        return shaping

    first = rollout()
    second = rollout()
    assert first == second
    assert all(np.isfinite(first))
    assert any(abs(value) > 0 for value in first)
