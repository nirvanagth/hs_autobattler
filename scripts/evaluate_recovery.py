"""Evaluate policy recovery after controlled mistakes on an expert prefix.

Each candidate sees the same deterministic ES-controlled prefix. At the first
normal Tavern decision on the target turn, the clean variant hands control to
the candidate, while perturbed variants execute one legal non-expert action
before handing over control. Raw per-seed outcomes are saved for paired tests.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import sys
import time
from collections import defaultdict
from pathlib import Path
from typing import Any

import numpy as np
import torch

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

from bc_collect import file_sha256
from dagger_collect import learner_action, query_expert_preserving_rng
from evaluate_checkpoints import load_agent, resolve_device
from hearthstone.env.hs_env import HearthstoneEnv


PERTURBATIONS = (
    "random_nonexpert",
    "wrong_buy",
    "sell_strongest",
    "waste_roll",
    "premature_end",
)


def parse_run(spec: str) -> tuple[str, Path]:
    if "=" not in spec:
        raise ValueError(f"run must be LABEL=CHECKPOINT, got {spec!r}")
    label, raw_path = spec.split("=", 1)
    if not label or not raw_path:
        raise ValueError(f"run must be LABEL=CHECKPOINT, got {spec!r}")
    path = Path(raw_path).resolve()
    if not path.is_file():
        raise FileNotFoundError(path)
    return label, path


def deterministic_rng(seed: int, perturbation: str, target_turn: int) -> np.random.Generator:
    payload = f"{seed}:{perturbation}:{target_turn}".encode("utf-8")
    digest = hashlib.sha256(payload).digest()
    return np.random.default_rng(int.from_bytes(digest[:8], "little"))


def random_nonexpert_action(
    legal_actions: list[int], expert_action: int, rng: np.random.Generator
) -> int | None:
    alternatives = [action for action in legal_actions if action != expert_action]
    non_end = [action for action in alternatives if action != 0]
    candidates = non_end or alternatives
    if not candidates:
        return None
    return int(candidates[int(rng.integers(len(candidates)))])


def choose_perturbation(
    env: HearthstoneEnv,
    mask: np.ndarray,
    expert_action: int,
    perturbation: str,
    rng: np.random.Generator,
) -> tuple[int | None, str]:
    legal = np.flatnonzero(mask).astype(int).tolist()

    if perturbation == "wrong_buy":
        choices = [action for action in legal if 2 <= action <= 8 and action != expert_action]
        if choices:
            return int(choices[int(rng.integers(len(choices)))]), perturbation
    elif perturbation == "sell_strongest":
        player = env.game.players[env.my_player_id]
        candidates = [
            (unit.cur_atk + unit.cur_hp, 9 + index)
            for index, unit in enumerate(player.board)
            if 9 + index in legal and 9 + index != expert_action
        ]
        if candidates:
            return max(candidates)[1], perturbation
    elif perturbation == "waste_roll":
        if 1 in legal and expert_action != 1:
            return 1, perturbation
    elif perturbation == "premature_end":
        if 0 in legal and expert_action != 0:
            return 0, perturbation
    elif perturbation != "random_nonexpert":
        raise ValueError(f"unknown perturbation: {perturbation}")

    fallback = random_nonexpert_action(legal, expert_action, rng)
    return fallback, "random_nonexpert_fallback"


def outcome_score(env: HearthstoneEnv) -> tuple[float, str]:
    player = env.game.players[env.my_player_id]
    enemy = env.game.players[env.enemy_id]
    if player.health > 0 >= enemy.health:
        return 1.0, "win"
    if enemy.health > 0 >= player.health:
        return 0.0, "loss"
    return 0.5, "draw"


def play_recovery_episode(
    *,
    agent: torch.nn.Module,
    device: torch.device,
    card_vocab_scheme: str,
    expert_weights: np.ndarray,
    opponent: str,
    seed: int,
    target_turn: int,
    perturbation: str | None,
) -> dict[str, Any]:
    env = HearthstoneEnv(max_tier=6, card_vocab_scheme=card_vocab_scheme)
    env.set_es_bot(expert_weights if opponent == "es" else None)
    obs, _ = env.reset(seed=seed)
    handed_off = False
    perturbation_applied = perturbation is None
    expert_action_at_handoff: int | None = None
    injected_action: int | None = None
    applied_kind: str | None = None
    steps = 0

    while True:
        player = env.game.players[env.my_player_id]
        mask = env.action_masks().copy()
        normal_decision = not player.is_discovering and not env.is_targeting

        if not handed_off and env.game.turn_count >= target_turn and normal_decision:
            expert_action_at_handoff = query_expert_preserving_rng(env, expert_weights)
            if perturbation is None:
                action, _ = learner_action(agent, obs, mask, device)
                handed_off = True
            else:
                rng = deterministic_rng(seed, perturbation, target_turn)
                action, applied_kind = choose_perturbation(
                    env, mask, expert_action_at_handoff, perturbation, rng
                )
                if action is None:
                    action = expert_action_at_handoff
                else:
                    perturbation_applied = action != expert_action_at_handoff
                    injected_action = action
                    handed_off = perturbation_applied
        elif handed_off:
            action, _ = learner_action(agent, obs, mask, device)
        else:
            action = query_expert_preserving_rng(env, expert_weights)

        obs, _reward, terminated, truncated, _info = env.step(action)
        steps += 1
        if terminated or truncated:
            break

    score, outcome = outcome_score(env)
    player = env.game.players[env.my_player_id]
    enemy = env.game.players[env.enemy_id]
    return {
        "seed": seed,
        "target_turn": target_turn,
        "perturbation": perturbation or "clean",
        "perturbation_applied": perturbation_applied,
        "applied_kind": applied_kind,
        "expert_action": expert_action_at_handoff,
        "injected_action": injected_action,
        "score": score,
        "outcome": outcome,
        "health_margin": player.health - enemy.health,
        "final_board_power": env.get_board_power(),
        "turns": env.game.turn_count,
        "steps": steps,
        "truncated": truncated,
    }


def mean_interval(values: list[float]) -> dict[str, float | int | None]:
    array = np.asarray(values, dtype=np.float64)
    n = len(array)
    if n == 0:
        return {"n": 0, "mean": None, "ci_low": None, "ci_high": None}
    mean = float(array.mean())
    if n == 1:
        return {"n": 1, "mean": mean, "ci_low": mean, "ci_high": mean}
    half_width = 1.959963984540054 * float(array.std(ddof=1)) / math.sqrt(n)
    return {
        "n": n,
        "mean": mean,
        "ci_low": mean - half_width,
        "ci_high": mean + half_width,
    }


def aggregate(records: list[dict[str, Any]]) -> dict[str, Any]:
    grouped: dict[tuple[str, str, int], list[dict[str, Any]]] = defaultdict(list)
    for record in records:
        grouped[(record["candidate"], record["perturbation"], record["target_turn"])].append(record)

    result: dict[str, Any] = {}
    for (candidate, perturbation, target_turn), rows in grouped.items():
        key = f"{candidate}|turn={target_turn}|{perturbation}"
        applicable = [row for row in rows if row["perturbation_applied"]]
        result[key] = {
            "episodes": len(rows),
            "applicable_episodes": len(applicable),
            "score": mean_interval([row["score"] for row in applicable]),
            "health_margin": mean_interval(
                [float(row["health_margin"]) for row in applicable]
            ),
            "win_rate": sum(row["outcome"] == "win" for row in applicable)
            / max(1, len(applicable)),
        }

    clean_by_key = {
        (row["candidate"], row["target_turn"], row["seed"]): row
        for row in records if row["perturbation"] == "clean"
    }
    recovery: dict[str, Any] = {}
    for (candidate, perturbation, target_turn), rows in grouped.items():
        if perturbation == "clean":
            continue
        deltas, hp_deltas = [], []
        for row in rows:
            if not row["perturbation_applied"]:
                continue
            clean = clean_by_key[(candidate, target_turn, row["seed"])]
            deltas.append(float(row["score"] - clean["score"]))
            hp_deltas.append(float(row["health_margin"] - clean["health_margin"]))
        key = f"{candidate}|turn={target_turn}|{perturbation}"
        recovery[key] = {
            "score_delta_from_clean": mean_interval(deltas),
            "health_delta_from_clean": mean_interval(hp_deltas),
        }
    candidate_order = list(dict.fromkeys(row["candidate"] for row in records))
    comparisons: dict[str, Any] = {}
    if len(candidate_order) >= 2:
        reference = candidate_order[0]
        row_map = {
            (
                row["candidate"],
                row["target_turn"],
                row["perturbation"],
                row["seed"],
            ): row
            for row in records
        }
        target_turns = sorted({row["target_turn"] for row in records})
        perturbations = sorted(
            {row["perturbation"] for row in records if row["perturbation"] != "clean"}
        )
        seeds = sorted({row["seed"] for row in records})
        for challenger in candidate_order[1:]:
            for target_turn in target_turns:
                for perturbation in perturbations:
                    direct_score, recovery_score = [], []
                    direct_hp, recovery_hp = [], []
                    for seed in seeds:
                        keys = {
                            "reference_clean": (reference, target_turn, "clean", seed),
                            "reference_error": (reference, target_turn, perturbation, seed),
                            "challenger_clean": (challenger, target_turn, "clean", seed),
                            "challenger_error": (challenger, target_turn, perturbation, seed),
                        }
                        if not all(key in row_map for key in keys.values()):
                            continue
                        rows = {name: row_map[key] for name, key in keys.items()}
                        if not (
                            rows["reference_error"]["perturbation_applied"]
                            and rows["challenger_error"]["perturbation_applied"]
                        ):
                            continue
                        direct_score.append(
                            rows["challenger_error"]["score"]
                            - rows["reference_error"]["score"]
                        )
                        direct_hp.append(
                            rows["challenger_error"]["health_margin"]
                            - rows["reference_error"]["health_margin"]
                        )
                        recovery_score.append(
                            (
                                rows["challenger_error"]["score"]
                                - rows["challenger_clean"]["score"]
                            )
                            - (
                                rows["reference_error"]["score"]
                                - rows["reference_clean"]["score"]
                            )
                        )
                        recovery_hp.append(
                            (
                                rows["challenger_error"]["health_margin"]
                                - rows["challenger_clean"]["health_margin"]
                            )
                            - (
                                rows["reference_error"]["health_margin"]
                                - rows["reference_clean"]["health_margin"]
                            )
                        )
                    key = (
                        f"{challenger}_vs_{reference}|turn={target_turn}|{perturbation}"
                    )
                    comparisons[key] = {
                        "perturbed_score_advantage": mean_interval(direct_score),
                        "perturbed_health_advantage": mean_interval(direct_hp),
                        "recovery_score_advantage": mean_interval(recovery_score),
                        "recovery_health_advantage": mean_interval(recovery_hp),
                    }
    return {"groups": result, "recovery": recovery, "comparisons": comparisons}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--run", action="append", required=True, help="LABEL=CHECKPOINT")
    parser.add_argument("--weights", default="artifacts/es_bot/best.npz")
    parser.add_argument("--opponent", choices=("smart", "es"), default="smart")
    parser.add_argument("--episodes", type=int, default=100)
    parser.add_argument("--seed-base", type=int, default=40_000)
    parser.add_argument("--target-turns", nargs="+", type=int, default=[5])
    parser.add_argument(
        "--perturbations", nargs="+", choices=PERTURBATIONS,
        default=["random_nonexpert", "sell_strongest", "premature_end"],
    )
    parser.add_argument("--device", choices=("auto", "cpu", "mps"), default="cpu")
    parser.add_argument("--out", default="artifacts/recovery/results.json")
    parser.add_argument("--log-every", type=int, default=25)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    device = resolve_device(args.device)
    weights_path = Path(args.weights).resolve()
    expert_weights = np.load(weights_path)["weights"].astype(np.float32)

    candidates = []
    vocab_contract = None
    for spec in args.run:
        label, path = parse_run(spec)
        agent, metadata = load_agent(path, device)
        contract = (metadata["card_vocab_scheme"], metadata["card_vocab_hash"])
        if vocab_contract is not None and contract != vocab_contract:
            raise ValueError("all candidates must use the same card vocabulary")
        vocab_contract = contract
        candidates.append((label, path, agent, metadata))

    records: list[dict[str, Any]] = []
    scenarios: list[str | None] = [None, *args.perturbations]
    total = len(candidates) * len(args.target_turns) * len(scenarios) * args.episodes
    completed = 0
    t0 = time.time()

    for label, path, agent, metadata in candidates:
        for target_turn in args.target_turns:
            for perturbation in scenarios:
                for offset in range(args.episodes):
                    record = play_recovery_episode(
                        agent=agent,
                        device=device,
                        card_vocab_scheme=metadata["card_vocab_scheme"],
                        expert_weights=expert_weights,
                        opponent=args.opponent,
                        seed=args.seed_base + offset,
                        target_turn=target_turn,
                        perturbation=perturbation,
                    )
                    record["candidate"] = label
                    record["checkpoint_sha256"] = metadata["checkpoint_sha256"]
                    records.append(record)
                    completed += 1
                    if completed % args.log_every == 0:
                        elapsed = time.time() - t0
                        print(
                            f"[recovery] {completed}/{total} episodes "
                            f"({completed / elapsed:.2f} eps/s)",
                            flush=True,
                        )

    report = {
        "schema_version": 1,
        "config": {
            "runs": [
                {"label": label, "path": str(path), "sha256": metadata["checkpoint_sha256"]}
                for label, path, _agent, metadata in candidates
            ],
            "teacher_path": str(weights_path),
            "teacher_sha256": file_sha256(weights_path),
            "opponent": args.opponent,
            "episodes": args.episodes,
            "seed_base": args.seed_base,
            "target_turns": args.target_turns,
            "perturbations": args.perturbations,
        },
        "summary": aggregate(records),
        "episodes": records,
    }
    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = out_path.with_suffix(".tmp")
    tmp_path.write_text(json.dumps(report, indent=2))
    tmp_path.replace(out_path)
    print(f"[saved] {out_path}")


if __name__ == "__main__":
    main()
