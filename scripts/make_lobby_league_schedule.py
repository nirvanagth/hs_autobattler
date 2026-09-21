"""Freeze deterministic PFSP lineups for paired league evaluation."""

from __future__ import annotations

import argparse
import json
import random
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from hearthstone.league import PolicyLeague, file_sha256


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--league", required=True)
    parser.add_argument("--reference", required=True)
    parser.add_argument("--episodes", type=int, default=200)
    parser.add_argument("--seed-base", type=int, default=220_000)
    parser.add_argument("--pfsp-exponent", type=float, default=2.0)
    parser.add_argument("--min-per-policy", type=int, default=0)
    parser.add_argument("--out", required=True)
    args = parser.parse_args()
    league_path = Path(args.league).resolve()
    league = PolicyLeague.load(league_path)
    compatible = sorted(
        policy_id
        for policy_id in league.entries
        if policy_id != args.reference
        and league.policies_are_compatible(args.reference, policy_id)
    )
    total_slots = args.episodes * 7
    required_slots = args.min_per_policy * len(compatible)
    if required_slots > total_slots:
        raise ValueError(
            f"minimum coverage needs {required_slots} slots, only {total_slots} available"
        )
    opponent_pool = [
        policy_id for policy_id in compatible for _ in range(args.min_per_policy)
    ]
    opponent_pool.extend(
        league.sample_opponents(
            args.reference,
            total_slots - required_slots,
            seed=args.seed_base,
            exponent=args.pfsp_exponent,
        )
    )
    random.Random(args.seed_base ^ 0x51A9_2026).shuffle(opponent_pool)
    games = []
    seen = set(opponent_pool)
    for episode in range(args.episodes):
        seed = args.seed_base + episode
        opponents = opponent_pool[episode * 7 : (episode + 1) * 7]
        games.append(
            {
                "seed": seed,
                "candidate_seat": episode % 8,
                "opponents": opponents,
            }
        )
    if len(seen) < 3:
        raise ValueError(f"schedule needs at least three holdouts; got {sorted(seen)}")
    payload = {
        "schema_version": 1,
        "league_sha256": file_sha256(league_path),
        "sampling_reference": args.reference,
        "pfsp_exponent": args.pfsp_exponent,
        "min_per_policy": args.min_per_policy,
        "holdout_policy_ids": sorted(seen),
        "games": games,
    }
    output = Path(args.out)
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = output.with_suffix(".tmp")
    temporary.write_text(json.dumps(payload, indent=2, sort_keys=True))
    temporary.replace(output)
    print(f"[saved] {len(games)} games, holdouts={sorted(seen)} -> {output}")


if __name__ == "__main__":
    main()
