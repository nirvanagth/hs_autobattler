"""CLI for immutable policy-league registries."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from hearthstone.league import PolicyEntry, PolicyLeague, file_sha256


def checkpoint_contract(path: Path):
    if path.suffix != ".pt":
        return None
    import torch

    checkpoint = torch.load(path, map_location="cpu")
    return checkpoint.get("lobby_environment_contract") or checkpoint.get(
        "environment_contract"
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--league", required=True)
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("init")
    add = subparsers.add_parser("add")
    add.add_argument("--id", required=True)
    add.add_argument("--kind", required=True)
    add.add_argument("--artifact", required=True)
    record = subparsers.add_parser("record")
    record.add_argument("--first", required=True)
    record.add_argument("--second", required=True)
    record.add_argument("--wins", type=int, required=True)
    record.add_argument("--losses", type=int, required=True)
    record.add_argument("--draws", type=int, default=0)
    import_report = subparsers.add_parser("import-lobby-report")
    import_report.add_argument("--report", required=True)
    sample = subparsers.add_parser("sample")
    sample.add_argument("--learner", required=True)
    sample.add_argument("--count", type=int, default=8)
    sample.add_argument("--seed", type=int, default=42)
    bootstrap = subparsers.add_parser("bootstrap")
    bootstrap.add_argument("--id", required=True)
    bootstrap.add_argument("--evidence", default="{}")
    promote = subparsers.add_parser("promote")
    promote.add_argument("--id", required=True)
    promote.add_argument("--holdout", action="append", required=True)
    promote.add_argument("--min-games", type=int, default=200)
    promote.add_argument("--min-opponents", type=int, default=3)
    promote.add_argument("--min-mean-improvement", type=float, default=0.0)
    promote.add_argument("--max-regression", type=float, default=0.02)
    promote.add_argument("--evidence", default="{}")
    subparsers.add_parser("status")
    args = parser.parse_args()
    path = Path(args.league)

    if args.command == "init":
        if path.exists():
            raise FileExistsError(path)
        league = PolicyLeague()
        league.save(path)
    else:
        league = PolicyLeague.load(path)
        if args.command == "add":
            artifact = Path(args.artifact).resolve()
            league.add_policy(
                PolicyEntry(
                    policy_id=args.id,
                    kind=args.kind,
                    artifact_path=str(artifact),
                    artifact_sha256=file_sha256(artifact),
                    environment_contract=checkpoint_contract(artifact),
                )
            )
            league.save(path)
        elif args.command == "record":
            league.record_series(
                args.first,
                args.second,
                wins=args.wins,
                losses=args.losses,
                draws=args.draws,
            )
            league.save(path)
        elif args.command == "import-lobby-report":
            imported = league.import_lobby_report(Path(args.report))
            league.save(path)
            print(json.dumps({"imported": imported, "report": args.report}))
        elif args.command == "sample":
            print(json.dumps(league.sample_opponents(args.learner, args.count, seed=args.seed)))
        elif args.command == "bootstrap":
            league.bootstrap_main(args.id, json.loads(args.evidence))
            league.save(path)
        elif args.command == "promote":
            league.promote(
                args.id,
                args.holdout,
                json.loads(args.evidence),
                min_games=args.min_games,
                min_opponents=args.min_opponents,
                min_mean_improvement=args.min_mean_improvement,
                max_regression=args.max_regression,
            )
            league.save(path)

    if args.command != "sample":
        current = PolicyLeague.load(path)
        print(json.dumps(current.to_dict(), indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
