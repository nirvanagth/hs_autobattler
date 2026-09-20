"""Collect DAgger labels on states visited by the current neural policy.

The learner normally controls the environment. At every visited state the ES
expert is queried without advancing Python or NumPy RNG state, and its action
is stored as the supervised label. ``beta`` optionally executes the expert
action to keep early rounds near the expert state distribution.
"""

from __future__ import annotations

import argparse
import random
import sys
import time
from pathlib import Path
from typing import Callable

import numpy as np
import torch
import torch.nn.functional as F

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

from bc_collect import discounted_returns, es_pick_action, file_sha256
from evaluate_checkpoints import load_agent, resolve_device
from hearthstone.env.hs_env import HearthstoneEnv


def query_expert_preserving_rng(
    env: HearthstoneEnv,
    weights: np.ndarray,
    expert_fn: Callable[[HearthstoneEnv, np.ndarray], int] = es_pick_action,
) -> int:
    """Query an expert without perturbing future environment randomness."""
    python_state = random.getstate()
    numpy_state = np.random.get_state()
    try:
        return int(expert_fn(env, weights))
    finally:
        random.setstate(python_state)
        np.random.set_state(numpy_state)


def learner_action(
    agent: torch.nn.Module,
    obs: np.ndarray,
    mask: np.ndarray,
    device: torch.device,
) -> tuple[int, float]:
    with torch.inference_mode():
        obs_tensor = torch.as_tensor(obs, dtype=torch.float32, device=device).unsqueeze(0)
        mask_tensor = torch.as_tensor(mask, dtype=torch.bool, device=device).unsqueeze(0)
        logits, _ = agent(obs_tensor)
        logits = logits.masked_fill(~mask_tensor, -1e8)
        probabilities = F.softmax(logits, dim=-1)
        confidence, action = probabilities.max(dim=-1)
    return int(action.item()), float(confidence.item())


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--checkpoint", required=True)
    parser.add_argument("--weights", default="artifacts/es_bot/best.npz")
    parser.add_argument("--episodes", type=int, default=1000)
    parser.add_argument("--beta", type=float, default=0.1)
    parser.add_argument("--gamma", type=float, default=0.999)
    parser.add_argument("--seed", type=int, default=10_000)
    parser.add_argument("--max-tier", type=int, default=6)
    parser.add_argument(
        "--opponent-mode", choices=("smart", "es", "mixed"), default="mixed"
    )
    parser.add_argument("--es-opponent-ratio", type=float, default=0.5)
    parser.add_argument("--device", choices=("auto", "cpu", "mps"), default="auto")
    parser.add_argument("--out", default="artifacts/dagger/round_1.npz")
    parser.add_argument("--log-every", type=int, default=100)
    args = parser.parse_args()
    if not 0.0 <= args.beta <= 1.0:
        parser.error("--beta must be in [0, 1]")
    if not 0.0 <= args.es_opponent_ratio <= 1.0:
        parser.error("--es-opponent-ratio must be in [0, 1]")
    return args


def main() -> None:
    args = parse_args()
    checkpoint_path = Path(args.checkpoint).resolve()
    weights_path = Path(args.weights).resolve()
    device = resolve_device(args.device)
    agent, metadata = load_agent(checkpoint_path, device)
    expert_weights = np.load(weights_path)["weights"].astype(np.float32)
    dagger_rng = np.random.default_rng(args.seed ^ 0xDA66_E001)

    env = HearthstoneEnv(
        max_tier=args.max_tier,
        card_vocab_scheme=metadata["card_vocab_scheme"],
    )

    all_obs: list[np.ndarray] = []
    all_masks: list[np.ndarray] = []
    all_expert_actions: list[int] = []
    all_learner_actions: list[int] = []
    all_executed_actions: list[int] = []
    all_confidences: list[float] = []
    all_rewards: list[float] = []
    all_returns: list[np.float32] = []
    all_episode_ids: list[int] = []
    board_powers: list[float] = []
    episode_outcomes: list[int] = []

    disagreements = 0
    expert_executions = 0
    t0 = time.time()

    for episode in range(args.episodes):
        use_es_opponent = (
            args.opponent_mode == "es"
            or (
                args.opponent_mode == "mixed"
                and dagger_rng.random() < args.es_opponent_ratio
            )
        )
        env.set_es_bot(expert_weights if use_es_opponent else None)
        obs, _ = env.reset(seed=args.seed + episode)
        episode_rewards: list[float] = []
        episode_start = len(all_obs)
        done = truncated = False

        while not (done or truncated):
            mask = env.action_masks().copy()
            policy_action, confidence = learner_action(agent, obs, mask, device)
            expert_action = query_expert_preserving_rng(env, expert_weights)
            execute_expert = dagger_rng.random() < args.beta
            action = expert_action if execute_expert else policy_action

            all_obs.append(obs.astype(np.float32, copy=True))
            all_masks.append(mask.astype(np.bool_, copy=True))
            all_expert_actions.append(expert_action)
            all_learner_actions.append(policy_action)
            all_executed_actions.append(action)
            all_confidences.append(confidence)
            all_episode_ids.append(episode)
            disagreements += int(policy_action != expert_action)
            expert_executions += int(execute_expert)

            obs, reward, done, truncated, _ = env.step(action)
            episode_rewards.append(float(reward))
            all_rewards.append(float(reward))

        all_returns.extend(discounted_returns(episode_rewards, args.gamma))
        board_powers.append(env.get_board_power())
        player = env.game.players[env.my_player_id]
        enemy = env.game.players[env.enemy_id]
        episode_outcomes.append(
            1 if player.health > 0 >= enemy.health
            else -1 if enemy.health > 0 >= player.health
            else 0
        )
        assert len(all_obs) - episode_start == len(episode_rewards)

        if (episode + 1) % args.log_every == 0:
            steps = len(all_obs)
            elapsed = time.time() - t0
            print(
                f"[ep {episode + 1}/{args.episodes}] steps={steps:,} "
                f"disagree={disagreements / steps:.3f} "
                f"confidence={np.mean(all_confidences):.3f} "
                f"fps={steps / elapsed:.0f}",
                flush=True,
            )

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(
        out_path,
        obs=np.stack(all_obs).astype(np.float32),
        masks=np.stack(all_masks).astype(np.bool_),
        actions=np.asarray(all_expert_actions, dtype=np.int64),
        expert_actions=np.asarray(all_expert_actions, dtype=np.int64),
        learner_actions=np.asarray(all_learner_actions, dtype=np.int64),
        executed_actions=np.asarray(all_executed_actions, dtype=np.int64),
        learner_confidence=np.asarray(all_confidences, dtype=np.float32),
        disagreements=(
            np.asarray(all_expert_actions, dtype=np.int64)
            != np.asarray(all_learner_actions, dtype=np.int64)
        ),
        rewards=np.asarray(all_rewards, dtype=np.float32),
        returns=np.asarray(all_returns, dtype=np.float32),
        episode_ids=np.asarray(all_episode_ids, dtype=np.int32),
        board_powers=np.asarray(board_powers, dtype=np.float32),
        episode_outcomes=np.asarray(episode_outcomes, dtype=np.int8),
        gamma=np.float32(args.gamma),
        card_vocab_hash=np.array(env.card_vocab_hash),
        card_vocab_scheme=np.array(env.card_vocab_scheme),
        card_vocabulary=np.asarray(env.card_id_vocabulary),
        teacher_weights_sha256=np.array(file_sha256(weights_path)),
        policy_checkpoint_sha256=np.array(file_sha256(checkpoint_path)),
        dagger_beta=np.float32(args.beta),
        opponent_mode=np.array(args.opponent_mode),
        source=np.array("dagger"),
        source_is_dagger=np.ones(len(all_obs), dtype=np.bool_),
    )

    total = len(all_obs)
    print(f"[done] {total:,} samples -> {out_path}")
    print(f"  disagreement={disagreements / total:.3f}")
    print(f"  expert_execution={expert_executions / total:.3f}")
    print(f"  mean_confidence={np.mean(all_confidences):.3f}")
    print(f"  learner_winrate={np.mean(np.asarray(episode_outcomes) == 1):.3f}")


if __name__ == "__main__":
    main()
