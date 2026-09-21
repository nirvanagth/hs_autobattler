"""Paired evaluation for feed-forward and recurrent eight-player policies."""

from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path

import numpy as np
import torch

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

from lobby_model import LobbyPointerAgent
from evaluate_checkpoints import file_sha256, resolve_device
from hearthstone.env.lobby_env import BattlegroundsLobbyEnv, PLACEMENT_REWARDS


def parse_run(spec: str) -> tuple[str, Path]:
    label, raw_path = spec.split("=", 1)
    path = Path(raw_path).resolve()
    if not path.is_file():
        raise FileNotFoundError(path)
    return label, path


def load_model(path: Path, device: torch.device):
    checkpoint = torch.load(path, map_location=device)
    args = checkpoint["args"]
    contract = checkpoint["lobby_environment_contract"]
    probe = BattlegroundsLobbyEnv(max_tier=int(contract["max_tier"]))
    if probe.lobby_environment_contract != contract:
        raise ValueError("checkpoint lobby contract does not match runtime")
    model = LobbyPointerAgent(
        num_card_ids=probe.num_card_ids,
        d_model=int(args["d_model"]),
        n_heads=int(args["n_heads"]),
        n_layers=int(args["n_layers"]),
        use_memory=bool(args["use_memory"]),
    ).to(device)
    model.load_state_dict(checkpoint["model"])
    return model.eval(), contract


def mean_interval(values: list[float]) -> dict[str, float | int]:
    array = np.asarray(values, dtype=np.float64)
    mean = float(array.mean())
    half = (
        1.959963984540054 * float(array.std(ddof=1)) / math.sqrt(len(array))
        if len(array) > 1 else 0.0
    )
    return {"n": len(array), "mean": mean, "ci_low": mean - half, "ci_high": mean + half}


def evaluate(model, contract, device, episodes: int, seed_base: int):
    records = []
    for offset in range(episodes):
        env = BattlegroundsLobbyEnv(max_tier=int(contract["max_tier"]), seed=seed_base + offset)
        obs, _ = env.reset(seed=seed_base + offset)
        hidden = None
        total_reward = 0.0
        terminated = truncated = False
        info = {}
        while not (terminated or truncated):
            mask = env.action_masks().copy()
            with torch.inference_mode():
                logits, _, hidden = model(
                    torch.as_tensor(obs, dtype=torch.float32, device=device).unsqueeze(0),
                    hidden,
                )
                mask_tensor = torch.as_tensor(mask, dtype=torch.bool, device=device).unsqueeze(0)
                action = int(logits.masked_fill(~mask_tensor, -1e8).argmax(dim=-1).item())
            obs, reward, terminated, truncated, info = env.step(action)
            total_reward += reward
        placement = int(info["placement"])
        records.append(
            {
                "seed": seed_base + offset,
                "placement": placement,
                "placement_utility": PLACEMENT_REWARDS[placement],
                "top4": placement <= 4,
                "win": placement == 1,
                "turns": int(info["lobby_turn"]),
                "return": total_reward,
            }
        )
    return records


def summarize(records):
    return {
        "games": len(records),
        "mean_placement": mean_interval([float(row["placement"]) for row in records]),
        "placement_utility": mean_interval(
            [float(row["placement_utility"]) for row in records]
        ),
        "top4_rate": float(np.mean([row["top4"] for row in records])),
        "win_rate": float(np.mean([row["win"] for row in records])),
        "mean_turns": float(np.mean([row["turns"] for row in records])),
        "episodes": records,
    }


def paired_comparison(reference, challenger, seed: int = 42, samples: int = 10_000):
    reference_map = {row["seed"]: row for row in reference}
    challenger_map = {row["seed"]: row for row in challenger}
    seeds = sorted(set(reference_map) & set(challenger_map))
    metrics = {
        "placement_improvement": np.asarray(
            [reference_map[s]["placement"] - challenger_map[s]["placement"] for s in seeds],
            dtype=np.float64,
        ),
        "utility_advantage": np.asarray(
            [challenger_map[s]["placement_utility"] - reference_map[s]["placement_utility"] for s in seeds],
            dtype=np.float64,
        ),
        "top4_advantage": np.asarray(
            [float(challenger_map[s]["top4"]) - float(reference_map[s]["top4"]) for s in seeds],
            dtype=np.float64,
        ),
        "win_advantage": np.asarray(
            [float(challenger_map[s]["win"]) - float(reference_map[s]["win"]) for s in seeds],
            dtype=np.float64,
        ),
    }
    rng = np.random.default_rng(seed)
    indices = rng.integers(0, len(seeds), size=(samples, len(seeds)))
    result = {"n": len(seeds)}
    for name, values in metrics.items():
        means = values[indices].mean(axis=1)
        result[name] = {
            "mean": float(values.mean()),
            "ci_low": float(np.quantile(means, 0.025)),
            "ci_high": float(np.quantile(means, 0.975)),
        }
    return result


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--run", action="append", required=True, help="LABEL=CHECKPOINT")
    parser.add_argument("--episodes", type=int, default=200)
    parser.add_argument("--seed-base", type=int, default=150_000)
    parser.add_argument("--device", choices=("auto", "cpu", "mps"), default="cpu")
    parser.add_argument("--out", required=True)
    args = parser.parse_args()
    device = resolve_device(args.device)
    report = {"schema_version": 1, "seed_base": args.seed_base, "runs": {}}
    for spec in args.run:
        label, path = parse_run(spec)
        model, contract = load_model(path, device)
        records = evaluate(model, contract, device, args.episodes, args.seed_base)
        report["runs"][label] = {
            "checkpoint": str(path),
            "checkpoint_sha256": file_sha256(path),
            "use_memory": model.use_memory,
            **summarize(records),
        }
        summary = report["runs"][label]
        print(
            f"[{label}] placement={summary['mean_placement']['mean']:.3f} "
            f"top4={summary['top4_rate']:.3f} win={summary['win_rate']:.3f}",
            flush=True,
        )
    labels = list(report["runs"])
    comparisons = {}
    for reference_index, reference in enumerate(labels):
        for challenger in labels[reference_index + 1:]:
            comparisons[f"{challenger}_minus_{reference}"] = paired_comparison(
                report["runs"][reference]["episodes"],
                report["runs"][challenger]["episodes"],
                seed=args.seed_base,
            )
    report["paired_comparisons"] = comparisons
    output = Path(args.out)
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = output.with_suffix(".tmp")
    temporary.write_text(json.dumps(report, indent=2))
    temporary.replace(output)
    print(f"[saved] {output}")


if __name__ == "__main__":
    main()
