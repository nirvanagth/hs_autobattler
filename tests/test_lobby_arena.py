"""Multi-policy lobby action driver tests."""

import numpy as np
import torch

from hearthstone.env.smart_bot import smart_bot_turn
from hearthstone.league import PolicyEntry, PolicyLeague, file_sha256
from hearthstone.lobby_arena import LobbyArena
from scripts.lobby_league_runtime import LeagueLobbyEnv


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
    while not (terminated or truncated):
        action = int(np.flatnonzero(env.action_masks())[0])
        _, _, terminated, truncated, info = env.step(action)
    assert info["placement"] in range(1, 9)
    assert env.learner_seat not in env.arena.game.active_player_ids
