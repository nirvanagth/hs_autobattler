"""Public-observation and lifecycle tests for the eight-player Gym wrapper."""

from __future__ import annotations

import numpy as np
import torch

from hearthstone.engine.entities import Unit
from hearthstone.engine.enums import CardIDs
from hearthstone.env.lobby_env import BattlegroundsLobbyEnv
from hearthstone.lobby_arena import CENTRAL_OBSERVATION_SIZE
from scripts.lobby_model import LobbyPointerAgent
from scripts.lobby_bc_collect import smart_pick_action
from scripts.evaluate_lobby_models import paired_comparison


def test_lobby_observation_shape(lobby_env: BattlegroundsLobbyEnv) -> None:
    obs, _ = lobby_env.reset(seed=42)
    assert obs.shape == (2958,)
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


def test_next_opponent_is_public_at_recruit_start(
    lobby_env: BattlegroundsLobbyEnv,
) -> None:
    obs, _ = lobby_env.reset(seed=42)
    next_opponent = lobby_env.game.next_opponent(0)
    assert next_opponent is not None
    states = lobby_env.game.public_opponent_states(0)
    assert [state.player_id for state in states if state.is_next_opponent] == [next_opponent]
    slot = next(index for index, state in enumerate(states) if state.player_id == next_opponent)
    base = (
        lobby_env.lobby_schema.own_size
        + slot * lobby_env.lobby_schema.opponent_stride
    )
    assert obs[base + 8] == 1.0


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


def test_lobby_feedforward_model_shapes(lobby_env: BattlegroundsLobbyEnv) -> None:
    obs, _ = lobby_env.reset(seed=42)
    model = LobbyPointerAgent(
        num_card_ids=lobby_env.num_card_ids,
        d_model=64,
        n_heads=4,
        n_layers=2,
        use_memory=False,
    ).eval()
    with torch.no_grad():
        actions, values, hidden = model(torch.from_numpy(obs).unsqueeze(0))
    assert actions.shape == (1, 34)
    assert values.shape == (1, 255)
    assert hidden is None


def test_central_critic_and_auxiliary_heads_do_not_change_actor_input(
    lobby_env: BattlegroundsLobbyEnv,
) -> None:
    obs, _ = lobby_env.reset(seed=42)
    model = LobbyPointerAgent(
        num_card_ids=lobby_env.num_card_ids,
        d_model=32,
        n_heads=4,
        n_layers=1,
        central_value_dim=CENTRAL_OBSERVATION_SIZE,
        auxiliary_heads=True,
    ).eval()
    public = torch.from_numpy(obs).unsqueeze(0)
    zeros = torch.zeros(1, CENTRAL_OBSERVATION_SIZE)
    ones = torch.ones(1, CENTRAL_OBSERVATION_SIZE)
    with torch.no_grad():
        logits_zero, values, _, outcomes, damage = model.forward_with_aux(
            public, critic_obs=zeros
        )
        logits_one, _, _, _, _ = model.forward_with_aux(public, critic_obs=ones)
    assert torch.equal(logits_zero, logits_one)
    assert values.shape == (1, 255)
    assert outcomes.shape == (1, 3)
    assert damage.shape == (1,)


def test_lobby_recurrent_sequence_matches_stepwise_execution(
    lobby_env: BattlegroundsLobbyEnv,
) -> None:
    observations = []
    obs, _ = lobby_env.reset(seed=5)
    observations.append(obs.copy())
    for _ in range(2):
        obs, _, done, truncated, _ = lobby_env.step(0)
        assert not done and not truncated
        observations.append(obs.copy())
    sequence = torch.from_numpy(np.stack(observations)).unsqueeze(0)
    model = LobbyPointerAgent(
        num_card_ids=lobby_env.num_card_ids,
        d_model=64,
        n_heads=4,
        n_layers=2,
        use_memory=True,
    ).eval()
    with torch.no_grad():
        sequence_logits, _, sequence_hidden = model.forward_sequence(sequence)
        hidden = None
        step_logits = []
        for step in range(sequence.shape[1]):
            logits, _, hidden = model(sequence[:, step], hidden)
            step_logits.append(logits)
    assert torch.allclose(sequence_logits, torch.stack(step_logits, dim=1), atol=1e-5)
    assert torch.allclose(sequence_hidden, hidden, atol=1e-5)


def test_smart_action_query_skips_upgrade_blocked_by_lobby_cap(
    lobby_env: BattlegroundsLobbyEnv,
) -> None:
    lobby_env.reset(seed=42)
    player = lobby_env.game.players[0]
    player.tavern_tier = 3
    player.gold = 10
    lobby_env.game.turn_count = 7
    # A full-ish board makes SmartBot attempt its normal upgrade branch first.
    player.board = [
        Unit.create_from_db(
            CardIDs.ANNOY_O_TRON,
            lobby_env.game.tavern.get_next_uid(),
            owner_id=0,
        )
        for _ in range(6)
    ]

    action = smart_pick_action(lobby_env)

    assert action != 32
    assert lobby_env.action_masks()[action]


def test_lobby_paired_comparison_uses_shared_seeds() -> None:
    reference = [
        {"seed": 1, "placement": 5, "placement_utility": -0.1, "top4": False, "win": False},
        {"seed": 2, "placement": 3, "placement_utility": 0.3, "top4": True, "win": False},
    ]
    challenger = [
        {"seed": 1, "placement": 2, "placement_utility": 0.6, "top4": True, "win": False},
        {"seed": 2, "placement": 1, "placement_utility": 1.0, "top4": True, "win": True},
    ]
    result = paired_comparison(reference, challenger, samples=1000)
    assert result["n"] == 2
    assert result["placement_improvement"]["mean"] == 2.5
    assert result["win_advantage"]["mean"] == 0.5
