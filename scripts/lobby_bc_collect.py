"""Collect SmartBot demonstrations in the eight-player lobby environment."""

from __future__ import annotations

import argparse
import hashlib
import random
import sys
import time
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

from bc_collect import _action_kwargs_to_int, discounted_returns
from hearthstone.env.lobby_env import BattlegroundsLobbyEnv
from hearthstone.env.smart_bot import _best_board_unit_idx, score_unit, smart_bot_turn


class _SmartActionSnoop(Exception):
    pass


def smart_pick_action(env: BattlegroundsLobbyEnv) -> int:
    player = env.game.players[env.my_player_id]
    mask = env.action_masks().copy()
    if env.is_targeting:
        if env.pending_target_kind == "MAGNETIZE":
            return 0  # SmartBot's direct policy plays Magnetic cards as bodies.
        targets = np.flatnonzero(mask[2:9]) + 2
        if not len(targets):
            return 0
        best = _best_board_unit_idx(player)
        return 2 + best if best >= 0 and mask[2 + best] else int(targets[0])
    if player.is_discovering and player.discovery.options:
        best_index, best_score = 0, float("-inf")
        for index, option in enumerate(player.discovery.options):
            if option.unit:
                value = option.unit.tier * 10 + option.unit.cur_atk + option.unit.cur_hp
            else:
                value = 0
            if value > best_score:
                best_index, best_score = index, value
        return 2 + best_index

    captured = []
    real_step = env.game.step

    def snoop(player_id, action_type, **kwargs):
        candidate = _action_kwargs_to_int(action_type, kwargs)
        if 0 <= candidate < len(mask) and mask[candidate]:
            captured.append((action_type, dict(kwargs)))
            raise _SmartActionSnoop()
        return False, False, "Masked by environment"

    python_state = random.getstate()
    numpy_state = np.random.get_state()
    env.game.step = snoop  # type: ignore[method-assign]
    try:
        smart_bot_turn(env.game, env.my_player_id)
    except _SmartActionSnoop:
        pass
    finally:
        env.game.step = real_step  # type: ignore[method-assign]
        random.setstate(python_state)
        np.random.set_state(numpy_state)
    if not captured:
        return 0
    action = _action_kwargs_to_int(*captured[0])
    return action if mask[action] else int(np.flatnonzero(mask)[0])


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--episodes", type=int, default=1000)
    parser.add_argument("--seed", type=int, default=120_000)
    parser.add_argument("--gamma", type=float, default=0.999)
    parser.add_argument("--out", default="artifacts/lobby/bc_dataset.npz")
    parser.add_argument("--log-every", type=int, default=100)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    env = BattlegroundsLobbyEnv(max_tier=3, seed=args.seed)
    observations = []
    masks = []
    actions = []
    rewards = []
    returns = []
    episode_ids = []
    placements = []
    t0 = time.time()

    for episode in range(args.episodes):
        obs, _ = env.reset(seed=args.seed + episode)
        episode_rewards = []
        terminated = truncated = False
        while not (terminated or truncated):
            mask = env.action_masks().copy()
            action = smart_pick_action(env)
            observations.append(obs.astype(np.float32, copy=True))
            masks.append(mask.astype(np.bool_, copy=True))
            actions.append(action)
            episode_ids.append(episode)
            obs, reward, terminated, truncated, info = env.step(action)
            rewards.append(reward)
            episode_rewards.append(reward)
        returns.extend(discounted_returns(episode_rewards, args.gamma))
        placements.append(info.get("placement", 8))
        if (episode + 1) % args.log_every == 0:
            elapsed = time.time() - t0
            print(
                f"[lobby-bc] {episode + 1}/{args.episodes} "
                f"steps={len(actions):,} fps={len(actions) / elapsed:.0f} "
                f"avg_place={np.mean(placements):.2f}",
                flush=True,
            )

    output = Path(args.out)
    output.parent.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(
        output,
        obs=np.stack(observations).astype(np.float32),
        masks=np.stack(masks).astype(np.bool_),
        actions=np.asarray(actions, dtype=np.int64),
        rewards=np.asarray(rewards, dtype=np.float32),
        returns=np.asarray(returns, dtype=np.float32),
        episode_ids=np.asarray(episode_ids, dtype=np.int32),
        placements=np.asarray(placements, dtype=np.int8),
        gamma=np.float32(args.gamma),
        lobby_environment_contract=np.array(env.lobby_environment_contract_json),
        source=np.array("smartbot_8p"),
    )
    digest = hashlib.sha256(output.read_bytes()).hexdigest()
    print(f"[done] {len(actions):,} rows -> {output}")
    print(f"[sha256] {digest}")


if __name__ == "__main__":
    main()
