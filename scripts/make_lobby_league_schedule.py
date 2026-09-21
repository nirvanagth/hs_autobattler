"""Freeze deterministic PFSP lineups for paired league evaluation."""

from __future__ import annotations

import argparse
import json
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
    parser.add_argument("--out", required=True)
    args = parser.parse_args()
    league_path = Path(args.league).resolve()
    league = PolicyLeague.load(league_path)
    games = []
    seen = set()
    for episode in range(args.episodes):
        seed = args.seed_base + episode
        opponents = league.sample_opponents(
            args.reference,
            7,
            seed=seed,
            exponent=args.pfsp_exponent,
        )
        seen.update(opponents)
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
