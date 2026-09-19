#!/usr/bin/env python3
"""Evaluate trained checkpoints against fixed opponents.

Runs each checkpoint greedily (masked argmax) against four opponents:
  es     - parametric ES bot (artifacts/es_kaggle/artifacts/best.npz)
  smart  - score-based SmartBot (the env default opponent)
  bc     - BC-pretrained transformer, also greedy
  random - random-action bot (random buys / plays / discovery picks)

Results are written incrementally to a JSON file after every matchup, so
interrupting with Ctrl+C never loses completed matchups. Re-running skips
matchups that are already complete.

Usage:
    PYTHONPATH=src python scripts/evaluate_checkpoints.py
    PYTHONPATH=src python scripts/evaluate_checkpoints.py --matchups es smart --games-es 50
    PYTHONPATH=src python scripts/evaluate_checkpoints.py --checkpoints artifacts/ppo/final.pt
"""

from __future__ import annotations

import argparse
import json
import random
import sys
import time
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

import torch

from model import HSTransformerAgent
from hearthstone.env.hs_env import HearthstoneEnv
import hearthstone.env.hs_env as hs_env_module

MATCHUPS = ("es", "smart", "bc", "random")
MATCHUP_LABELS = {
    "es": "ES bot",
    "smart": "SmartBot",
    "bc": "BC greedy",
    "random": "Random bot",
}
# card_ids the PPO checkpoints were trained with; only used if the
# checkpoint's own embedding shape cannot be recovered.
DEFAULT_CARD_IDS = 202


# ----------------------------------------------------------------------------
# Device / model loading
# ----------------------------------------------------------------------------

def resolve_device(name: str) -> torch.device:
    """Pick a torch device. 'auto' prefers mps on Apple Silicon."""
    if name == "cpu":
        return torch.device("cpu")
    if name == "mps":
        if torch.backends.mps.is_available():
            return torch.device("mps")
        print("[warn] mps requested but not available, falling back to cpu")
        return torch.device("cpu")
    # auto: cuda -> mps -> cpu
    if torch.cuda.is_available():
        return torch.device("cuda")
    if torch.backends.mps.is_available():
        return torch.device("mps")
    return torch.device("cpu")


def infer_num_card_ids(state_dict, default: int = DEFAULT_CARD_IDS) -> int:
    """Recover num_card_ids from the checkpoint's card embedding shape.

    The live card pool may have changed since training, so the embedding
    size must come from the checkpoint itself, not the current env.
    """
    key = "encoder.emb_card.weight"
    if key in state_dict:
        return int(state_dict[key].shape[0])
    for k, v in state_dict.items():
        if v.dim() == 2 and "emb" in k and v.shape[0] > 50:
            return int(v.shape[0])
    return default


def load_agent(path: Path, device: torch.device):
    """Load a checkpoint (PPO or BC pretrain) into an eval-mode agent."""
    ckpt = torch.load(path, map_location=device)
    sd = ckpt["model"]
    saved_args = ckpt.get("args", {}) or {}
    d_model = int(saved_args.get("d_model", 128))
    n_heads = int(saved_args.get("n_heads", 4))
    n_layers = int(saved_args.get("n_layers", 4))
    num_card_ids = infer_num_card_ids(sd)
    agent = HSTransformerAgent(
        n_actions=34,
        d_model=d_model,
        n_heads=n_heads,
        n_layers=n_layers,
        num_card_ids=num_card_ids,
    ).to(device)
    agent.load_state_dict(sd)
    agent.eval()
    meta = {
        "d_model": d_model,
        "n_heads": n_heads,
        "n_layers": n_layers,
        "num_card_ids": num_card_ids,
        "global_step": ckpt.get("global_step"),
    }
    return agent, meta


def load_es_weights(path: Path) -> np.ndarray:
    data = np.load(path)
    key = "weights" if "weights" in data.files else data.files[0]
    return np.asarray(data[key], dtype=np.float32)


# ----------------------------------------------------------------------------
# Policies
# ----------------------------------------------------------------------------

def greedy_action(agent, obs: np.ndarray, masks: np.ndarray,
                  device: torch.device) -> int:
    """Masked argmax over action logits."""
    with torch.no_grad():
        o = torch.as_tensor(
            np.asarray(obs, dtype=np.float32), device=device
        ).unsqueeze(0)
        logits, _ = agent(o)
        m = torch.as_tensor(
            np.asarray(masks, dtype=bool), device=device
        ).unsqueeze(0)
        logits = logits.masked_fill(~m, -1e8)
        return int(torch.argmax(logits, dim=-1).item())


class BCAdapter:
    """Wrap a transformer agent as a neural opponent for the env.

    Matches the .predict(obs, action_masks=..., deterministic=...) protocol
    used by HearthstoneEnv._neural_enemy_turn.
    """

    def __init__(self, agent, device: torch.device):
        self.agent = agent
        self.device = device

    def predict(self, obs, action_masks=None, deterministic=True):
        action = greedy_action(self.agent, obs, action_masks, self.device)
        return action, None


def random_bot_turn(game, p_idx) -> None:
    """Random bot: play random hand cards, buy random store items, END_TURN.

    Mirrors HearthstoneEnv._simple_bot_turn but picks discovery options
    uniformly at random instead of always taking the first one.
    """
    player = game.players[p_idx]

    def random_discover():
        if player.is_discovering and player.discovery.options:
            idx = random.randrange(len(player.discovery.options))
            game.step(p_idx, "DISCOVER_CHOICE", index=idx)

    random_discover()

    attempts = 0
    while len(player.hand) > 0 and len(player.board) < 7 and attempts < 15:
        hand_size_before = len(player.hand)
        game.step(p_idx, "PLAY", hand_index=0, insert_index=-1)
        if len(player.hand) == hand_size_before:
            break
        random_discover()
        attempts += 1

    it = 0
    while player.gold >= 3 and player.store and it < 5:
        it += 1
        idx = random.randrange(len(player.store))
        game.step(p_idx, "BUY", index=idx)
        if player.hand:
            game.step(p_idx, "PLAY", hand_index=len(player.hand) - 1,
                      insert_index=-1)
            random_discover()

    game.step(p_idx, "END_TURN")


# ----------------------------------------------------------------------------
# Episode / matchup runners
# ----------------------------------------------------------------------------

def play_episode(env: HearthstoneEnv, agent, device: torch.device,
                 seed: int) -> dict:
    obs, _ = env.reset(seed=seed)
    max_tier = 0
    done = False
    while not done:
        me = env.game.players[env.my_player_id]
        if me.tavern_tier > max_tier:
            max_tier = me.tavern_tier
        masks = env.action_masks()
        action = greedy_action(agent, obs, masks, device)
        obs, _reward, terminated, truncated, _info = env.step(action)
        done = terminated or truncated

    p0 = env.game.players[env.my_player_id]
    p1 = env.game.players[env.enemy_id]
    if p0.health > 0 >= p1.health:
        outcome = "win"
    elif p1.health > 0 >= p0.health:
        outcome = "loss"
    else:
        outcome = "draw"
    return {
        "outcome": outcome,
        "hp_diff": float(p0.health - p1.health),
        "board_power": float(env.get_board_power()),
        "max_tier": int(max_tier),
        "turns": int(env.game.turn_count),
    }


def run_matchup(env_factory, agent, device: torch.device, games: int,
                seed: int, label: str) -> dict:
    wins = losses = draws = 0
    hp_diffs, board_powers, max_tiers, turns = [], [], [], []
    t0 = time.time()
    progress_every = max(1, games // 10)
    for i in range(games):
        ep = play_episode(env_factory(), agent, device, seed + i)
        if ep["outcome"] == "win":
            wins += 1
        elif ep["outcome"] == "loss":
            losses += 1
        else:
            draws += 1
        hp_diffs.append(ep["hp_diff"])
        board_powers.append(ep["board_power"])
        max_tiers.append(ep["max_tier"])
        turns.append(ep["turns"])
        done_n = i + 1
        if done_n % progress_every == 0 or done_n == games:
            el = time.time() - t0
            print(f"  [{label}] {done_n}/{games} games "
                  f"(W {wins} L {losses} D {draws}) {el:.0f}s",
                  flush=True)
    return {
        "games": games,
        "wins": wins,
        "losses": losses,
        "draws": draws,
        "win_rate": round(100.0 * wins / games, 2),
        "avg_hp_diff": round(float(np.mean(hp_diffs)), 2),
        "avg_board_power": round(float(np.mean(board_powers)), 2),
        "avg_max_tier": round(float(np.mean(max_tiers)), 2),
        "avg_turns": round(float(np.mean(turns)), 2),
    }


# ----------------------------------------------------------------------------
# Results IO
# ----------------------------------------------------------------------------

def load_results(path: Path) -> dict:
    if path.exists():
        try:
            with open(path) as f:
                return json.load(f)
        except (json.JSONDecodeError, OSError) as e:
            print(f"[warn] could not read existing results {path}: {e}")
    return {}


def save_results(path: Path, results: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    with open(tmp, "w") as f:
        json.dump(results, f, indent=2)
    tmp.replace(path)


def print_matchup_summary(ckpt_name: str, matchup: str, stats: dict) -> None:
    print(f"[eval] {ckpt_name} vs {MATCHUP_LABELS[matchup]}: "
          f"{stats['games']} games | "
          f"W {stats['wins']} L {stats['losses']} D {stats['draws']} | "
          f"win {stats['win_rate']:.1f}% | "
          f"hp_diff {stats['avg_hp_diff']:+.1f} | "
          f"board {stats['avg_board_power']:.1f} | "
          f"max_tier {stats['avg_max_tier']:.1f} | "
          f"turns {stats['avg_turns']:.1f}")


def print_final_table(results: dict) -> None:
    print("\n" + "=" * 80)
    print("EVALUATION SUMMARY")
    print("=" * 80)
    for ckpt_name, per_matchup in results.items():
        print(f"\n## {ckpt_name}")
        print(f"{'matchup':<10} {'games':>6} {'W':>4} {'L':>4} {'D':>4} "
              f"{'win%':>7} {'hp_diff':>8} {'board':>7} {'tier':>5} {'turns':>6}")
        for matchup in MATCHUPS:
            s = per_matchup.get(matchup)
            if not s:
                continue
            print(f"{MATCHUP_LABELS[matchup]:<10} {s['games']:>6} {s['wins']:>4} "
                  f"{s['losses']:>4} {s['draws']:>4} {s['win_rate']:>7.1f} "
                  f"{s['avg_hp_diff']:>+8.1f} {s['avg_board_power']:>7.1f} "
                  f"{s['avg_max_tier']:>5.1f} {s['avg_turns']:>6.1f}")
    print()


# ----------------------------------------------------------------------------
# CLI
# ----------------------------------------------------------------------------

def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="Evaluate PPO/BC checkpoints against fixed opponents.")
    p.add_argument("--checkpoints", nargs="*", default=[
        "artifacts/ppo/final.pt",
        "artifacts/ppo/ckpt_3276800.pt",
        "artifacts/ppo/ckpt_1638400.pt",
    ], help="checkpoint .pt files to evaluate; missing files are skipped")
    p.add_argument("--es-weights", default="artifacts/es_kaggle/artifacts/best.npz",
                   help="ES bot weights .npz file")
    p.add_argument("--bc-checkpoint", default="artifacts/bc/bc_pretrain.pt",
                   help="BC checkpoint .pt used as the 'bc' opponent")
    p.add_argument("--games-es", type=int, default=200,
                   help="games per checkpoint vs ES bot")
    p.add_argument("--games-smart", type=int, default=100,
                   help="games per checkpoint vs SmartBot")
    p.add_argument("--games-bc", type=int, default=100,
                   help="games per checkpoint vs BC greedy")
    p.add_argument("--games-random", type=int, default=50,
                   help="games per checkpoint vs random bot")
    p.add_argument("--matchups", nargs="*", choices=list(MATCHUPS),
                   default=list(MATCHUPS),
                   help="subset of matchups to run (default: all)")
    p.add_argument("--seed", type=int, default=42,
                   help="base seed; game i uses seed+i")
    p.add_argument("--out", default="artifacts/eval/results.json",
                   help="JSON results file, written incrementally")
    p.add_argument("--device", choices=["auto", "mps", "cpu"], default="auto",
                   help="torch device (auto prefers mps on Apple Silicon)")
    return p.parse_args()


def resolve(p: str) -> Path:
    path = Path(p)
    return path if path.is_absolute() else ROOT / path


def main() -> None:
    args = parse_args()
    device = resolve_device(args.device)
    print(f"[eval] device={device}")

    games_per_matchup = {
        "es": args.games_es,
        "smart": args.games_smart,
        "bc": args.games_bc,
        "random": args.games_random,
    }

    # ---- resolve checkpoints (warn + skip missing) ----
    ckpt_paths = []
    for c in args.checkpoints:
        rp = resolve(c)
        if not rp.exists():
            print(f"[warn] checkpoint not found, skipping: {rp}")
            continue
        ckpt_paths.append(rp)
    if not ckpt_paths:
        print("[error] no checkpoints to evaluate")
        sys.exit(1)

    matchups = [m for m in MATCHUPS if m in args.matchups]

    # ---- opponent resources ----
    es_weights = None
    if "es" in matchups:
        rp = resolve(args.es_weights)
        if rp.exists():
            es_weights = load_es_weights(rp)
            print(f"[eval] ES weights loaded from {rp}")
        else:
            print(f"[warn] ES weights not found, skipping 'es' matchup: {rp}")
            matchups.remove("es")

    bc_agent = None
    if "bc" in matchups:
        rp = resolve(args.bc_checkpoint)
        if rp.exists():
            bc_agent, bc_meta = load_agent(rp, device)
            print(f"[eval] BC opponent loaded from {rp} "
                  f"(d_model={bc_meta['d_model']} "
                  f"card_ids={bc_meta['num_card_ids']})")
        else:
            print(f"[warn] BC checkpoint not found, skipping 'bc' matchup: {rp}")
            matchups.remove("bc")

    out_path = resolve(args.out)
    results = load_results(out_path)

    def make_factory(matchup):
        if matchup == "es":
            def factory():
                env = HearthstoneEnv(max_tier=6)
                env.set_es_bot(es_weights)
                return env
        elif matchup == "bc":
            def factory():
                env = HearthstoneEnv(max_tier=6)
                env.set_opponent(BCAdapter(bc_agent, device))
                return env
        else:
            def factory():
                return HearthstoneEnv(max_tier=6)
        return factory

    try:
        for ckpt_path in ckpt_paths:
            ckpt_name = ckpt_path.stem
            print(f"\n[eval] loading checkpoint {ckpt_path}")
            agent, meta = load_agent(ckpt_path, device)
            print(f"[eval]   arch d_model={meta['d_model']} "
                  f"n_heads={meta['n_heads']} n_layers={meta['n_layers']} "
                  f"card_ids={meta['num_card_ids']} "
                  f"global_step={meta['global_step']}")
            results.setdefault(ckpt_name, {})

            for matchup in matchups:
                games = games_per_matchup[matchup]
                existing = results[ckpt_name].get(matchup)
                if existing and existing.get("games") == games:
                    print(f"[eval] {ckpt_name} vs {MATCHUP_LABELS[matchup]}: "
                          f"already done ({games} games), skipping")
                    continue
                print(f"[eval] {ckpt_name} vs {MATCHUP_LABELS[matchup]} "
                      f"({games} games, seed={args.seed})")
                factory = make_factory(matchup)
                if matchup == "random":
                    # _play_enemy_turn falls back to the module-global
                    # smart_bot_turn; swap it for the random bot here.
                    orig = hs_env_module.smart_bot_turn
                    hs_env_module.smart_bot_turn = random_bot_turn
                    try:
                        stats = run_matchup(factory, agent, device, games,
                                            args.seed, MATCHUP_LABELS[matchup])
                    finally:
                        hs_env_module.smart_bot_turn = orig
                else:
                    stats = run_matchup(factory, agent, device, games,
                                        args.seed, MATCHUP_LABELS[matchup])
                results[ckpt_name][matchup] = stats
                save_results(out_path, results)
                print_matchup_summary(ckpt_name, matchup, stats)
    except KeyboardInterrupt:
        print("\n[eval] interrupted by user; partial results are saved.")

    print_final_table(results)
    print(f"[eval] results written to {out_path}")


if __name__ == "__main__":
    main()
