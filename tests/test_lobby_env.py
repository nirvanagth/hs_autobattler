"""Public-observation and lifecycle tests for the eight-player Gym wrapper."""

from __future__ import annotations

import numpy as np

from hearthstone.engine.entities import Unit
from hearthstone.engine.enums import CardIDs
from hearthstone.env.lobby_env import BattlegroundsLobbyEnv


def test_lobby_observation_shape(lobby_env: BattlegroundsLobbyEnv) -> None:
    obs, _ = lobby_env.reset(seed=42)
    assert obs.shape == (2951,)
    assert obs.shape == lobby_env.observation_space.shape
    assert np.isfinite(obs).all()


def test_hidden_current_board_does_not_change_observation(
    lobby_env: BattlegroundsLobbyEnv,
) -> None:
    obs, _ = lobby_env.reset(seed=42)
    hidden = Unit.create_from_db(
        CardIDs.ANNOY_O_TRON,
        lobby_env.game.tavern.get_next_uid(),
        owner_id=2,
    )
    lobby_env.game.players[2].board.append(hidden)
    after_hidden_mutation = lobby_env._get_lobby_obs()
    assert np.array_equal(obs, after_hidden_mutation)


def test_last_seen_board_is_exposed_after_observation(
    lobby_env: BattlegroundsLobbyEnv,
) -> None:
    lobby_env.reset(seed=42)
    opponent = lobby_env.game.players[1]
    opponent.board.append(
        Unit.create_from_db(
            CardIDs.ANNOY_O_TRON,
            lobby_env.game.tavern.get_next_uid(),
            owner_id=1,
        )
    )
    lobby_env.game._record_mutual_observation(lobby_env.game.players[0], opponent)
    obs = lobby_env._get_lobby_obs()
    base = lobby_env.lobby_schema.own_size
    assert obs[base + 6] == 1.0  # has_seen
    board_offset = base + lobby_env.lobby_schema.opponent_meta_features
    assert obs[board_offset] == 1.0  # entity present
    assert obs[board_offset + 2] > 0.0  # stable card id


def test_end_turn_drives_all_bots_and_advances_round(
    lobby_env: BattlegroundsLobbyEnv,
) -> None:
    lobby_env.reset(seed=42)
    _, reward, terminated, truncated, info = lobby_env.step(0)
    assert not terminated
    assert not truncated
    assert lobby_env.game.turn_count == 2
    assert info["active_players"] == 8
    assert np.isfinite(reward)


def test_empty_agent_eventually_receives_placement(
    lobby_env: BattlegroundsLobbyEnv,
) -> None:
    lobby_env.reset(seed=7)
    terminated = truncated = False
    info = {}
    for _ in range(100):
        mask = lobby_env.action_masks()
        action = 0 if mask[0] else int(np.flatnonzero(mask)[0])
        _, _, terminated, truncated, info = lobby_env.step(action)
        if terminated or truncated:
            break
    assert terminated
    assert not truncated
    assert info["placement"] in range(2, 9)
