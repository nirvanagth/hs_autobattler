"""Paired bootstrap comparisons for frozen-schedule league evaluations."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np


def interval(values: np.ndarray, *, seed: int, samples: int = 10_000):
    rng = np.random.default_rng(seed)
    indices = rng.integers(0, len(values), size=(samples, len(values)))
    means = values[indices].mean(axis=1)
    return {
        "n": len(values),
        "mean": float(values.mean()),
        "ci_low": float(np.quantile(means, 0.025)),
        "ci_high": float(np.quantile(means, 0.975)),
    }


def compare(reference: dict, challenger: dict, *, seed: int) -> dict:
    if reference["schedule_sha256"] != challenger["schedule_sha256"]:
        raise ValueError("reports do not share the same frozen schedule")
    reference_games = reference["games"]
    challenger_games = challenger["games"]
    if len(reference_games) != len(challenger_games):
        raise ValueError("report game counts differ")

    placement_improvements = []
    top4_advantages = []
    win_advantages = []
    for reference_game, challenger_game in zip(reference_games, challenger_games):
        for key in ("seed", "candidate_seat"):
            if reference_game[key] != challenger_game[key]:
                raise ValueError(f"paired game mismatch on {key}")
        seat = int(reference_game["candidate_seat"])
        reference_opponents = reference_game["lineup"].copy()
        challenger_opponents = challenger_game["lineup"].copy()
        reference_opponents.pop(seat)
        challenger_opponents.pop(seat)
        if reference_opponents != challenger_opponents:
            raise ValueError("paired game opponent lineups differ")
        reference_place = int(reference_game["candidate_placement"])
        challenger_place = int(challenger_game["candidate_placement"])
        placement_improvements.append(reference_place - challenger_place)
        top4_advantages.append(float(challenger_place <= 4) - float(reference_place <= 4))
        win_advantages.append(float(challenger_place == 1) - float(reference_place == 1))

    return {
        "reference_id": reference["candidate_id"],
        "challenger_id": challenger["candidate_id"],
        "placement_improvement": interval(
            np.asarray(placement_improvements, dtype=np.float64), seed=seed
        ),
        "top4_advantage": interval(
            np.asarray(top4_advantages, dtype=np.float64), seed=seed + 1
        ),
        "win_advantage": interval(
            np.asarray(win_advantages, dtype=np.float64), seed=seed + 2
        ),
    }


def parse_spec(spec: str) -> tuple[str, Path]:
    label, raw_path = spec.split("=", 1)
    return label, Path(raw_path)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--reference", required=True)
    parser.add_argument("--challenger", action="append", required=True)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--out", required=True)
    args = parser.parse_args()
    reference_path = Path(args.reference)
    reference = json.loads(reference_path.read_text())
    comparisons = {}
    for offset, spec in enumerate(args.challenger):
        label, path = parse_spec(spec)
        challenger = json.loads(path.read_text())
        comparisons[label] = compare(reference, challenger, seed=args.seed + offset * 10)
    payload = {
        "schema_version": 1,
        "reference": str(reference_path),
        "schedule_sha256": reference["schedule_sha256"],
        "comparisons": comparisons,
    }
    output = Path(args.out)
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = output.with_suffix(".tmp")
    temporary.write_text(json.dumps(payload, indent=2, sort_keys=True))
    temporary.replace(output)
    print(json.dumps(payload, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
