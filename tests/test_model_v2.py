"""Regression tests for the entity-aligned actor and PPO episode boundaries."""

from __future__ import annotations

import torch

from hearthstone.env.hs_env import HearthstoneEnv
from hearthstone.env.card_vocab import STABLE_V1, build_card_vocabulary
from scripts.bc_collect import discounted_returns
from scripts.model import HSTransformerAgent
from scripts.train_ppo import compute_gae


def _make_pointer_agent(env: HearthstoneEnv) -> HSTransformerAgent:
    torch.manual_seed(7)
    agent = HSTransformerAgent(
        d_model=64,
        n_heads=4,
        n_layers=2,
        num_card_ids=env.num_card_ids,
        actor_type="pointer",
    )
    # Pointer output layers are intentionally zero-initialized. Give them a
    # deterministic non-zero probe so the equivariance assertion is meaningful.
    assert agent.pointer_actor is not None
    for module in agent.pointer_actor.modules():
        if isinstance(module, torch.nn.Linear):
            torch.nn.init.normal_(module.weight, std=0.05)
            if module.bias is not None:
                torch.nn.init.normal_(module.bias, std=0.05)
    return agent.eval()


def test_pointer_actor_store_permutation_is_equivariant() -> None:
    env = HearthstoneEnv()
    obs, _ = env.reset(seed=42)
    assert len(env.game.players[0].store) >= 2

    original = torch.from_numpy(obs.copy()).unsqueeze(0)
    swapped = original.clone()
    ef = env.entity_features
    offset = env._off_store
    first = swapped[:, offset : offset + ef].clone()
    swapped[:, offset : offset + ef] = swapped[:, offset + ef : offset + 2 * ef]
    swapped[:, offset + ef : offset + 2 * ef] = first

    agent = _make_pointer_agent(env)
    with torch.no_grad():
        logits_original, _ = agent(original)
        logits_swapped, _ = agent(swapped)

    # Store slot actions follow the entities that were swapped.
    assert torch.allclose(logits_original[:, 2], logits_swapped[:, 3], atol=1e-5)
    assert torch.allclose(logits_original[:, 3], logits_swapped[:, 2], atol=1e-5)
    assert torch.allclose(logits_original[:, 4:9], logits_swapped[:, 4:9], atol=1e-5)
    # Global actions are invariant to Tavern display order.
    assert torch.allclose(logits_original[:, [0, 1, 32, 33]],
                          logits_swapped[:, [0, 1, 32, 33]], atol=1e-5)


def test_pointer_actor_produces_action_schema_shape() -> None:
    env = HearthstoneEnv()
    obs, _ = env.reset(seed=1)
    agent = _make_pointer_agent(env)
    with torch.no_grad():
        action_logits, value_logits = agent(torch.from_numpy(obs).unsqueeze(0))
    assert action_logits.shape == (1, 34)
    assert value_logits.shape == (1, 255)


def test_compute_gae_stops_at_current_transition_terminal() -> None:
    rewards = torch.tensor([[1.0], [2.0]])
    values = torch.tensor([[10.0], [20.0]])
    # Transition 0 terminates; transition 1 belongs to the autoreset episode.
    dones = torch.tensor([[1.0], [0.0]])
    next_value = torch.tensor([30.0])

    advantages, returns = compute_gae(
        rewards,
        values,
        dones,
        next_value,
        gamma=1.0,
        gae_lambda=1.0,
    )

    assert torch.allclose(advantages[:, 0], torch.tensor([-9.0, 12.0]))
    assert torch.allclose(returns[:, 0], torch.tensor([1.0, 32.0]))


def test_discounted_returns_are_episode_local() -> None:
    returns = discounted_returns([1.0, 2.0, 3.0], gamma=0.5)
    assert returns == [torch.tensor(2.75).item(), 3.5, 3.0]


def test_card_vocabulary_hash_is_deterministic() -> None:
    first = HearthstoneEnv()
    second = HearthstoneEnv()
    assert first.card_vocab_hash == second.card_vocab_hash
    assert len(first.card_vocab_hash) == 64
    assert len(first.card_id_vocabulary) + 1 == first.num_card_ids


def test_stable_card_vocabulary_does_not_shift_existing_ids() -> None:
    original, size, _, digest = build_card_vocabulary(
        ["101", "201", "S001", "t001"], STABLE_V1
    )
    extended, extended_size, _, extended_digest = build_card_vocabulary(
        ["101", "122", "201", "S001", "S017", "t001"], STABLE_V1
    )
    assert original["101"] == extended["101"] == 101
    assert original["201"] == extended["201"] == 201
    assert original["S001"] == extended["S001"] == 1001
    assert original["t001"] == extended["t001"] == 801
    assert size == extended_size == 2048
    assert digest == extended_digest


def test_stable_card_vocabulary_encodes_live_observations() -> None:
    env = HearthstoneEnv(card_vocab_scheme=STABLE_V1)
    obs, _ = env.reset(seed=42)
    assert env.num_card_ids == 2048
    first_store_id = obs[env._off_store + 2]
    assert 0 < first_store_id < env.num_card_ids
