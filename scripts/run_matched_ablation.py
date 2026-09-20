"""Resumable matched BC representation ablations.

The runner freezes one dataset, seed list, training budget, evaluation suite,
and source revision in a manifest. Each run has an independent log and result
file. Existing completed artifacts are reused only when explicitly declared.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
SCHEMA_VERSION = 1


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def git_head() -> str:
    return subprocess.check_output(
        ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True
    ).strip()


def parse_reuse(specs: list[str]) -> dict[tuple[str, int], Path]:
    result: dict[tuple[str, int], Path] = {}
    for spec in specs:
        if "=" not in spec or ":" not in spec.split("=", 1)[0]:
            raise ValueError(f"reuse must be VARIANT:SEED=CHECKPOINT, got {spec!r}")
        identity, raw_path = spec.split("=", 1)
        variant, raw_seed = identity.split(":", 1)
        path = Path(raw_path).resolve()
        if not path.is_file():
            raise FileNotFoundError(path)
        result[(variant, int(raw_seed))] = path
    return result


def atomic_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(payload, indent=2))
    temporary.replace(path)


def build_train_command(
    *,
    dataset: Path,
    checkpoint: Path,
    variant: str,
    seed: int,
    epochs: int,
    batch_size: int,
    learning_rate: float,
) -> list[str]:
    return [
        sys.executable,
        str(ROOT / "scripts" / "bc_train.py"),
        "--dataset", str(dataset),
        "--out", str(checkpoint),
        "--actor-type", variant,
        "--seed", str(seed),
        "--epochs", str(epochs),
        "--batch-size", str(batch_size),
        "--lr", str(learning_rate),
    ]


def build_eval_command(
    *,
    checkpoint: Path,
    es_weights: Path,
    output: Path,
    games_es: int,
    games_smart: int,
    seed: int,
) -> list[str]:
    return [
        sys.executable,
        str(ROOT / "scripts" / "evaluate_checkpoints.py"),
        "--checkpoints", str(checkpoint),
        "--es-weights", str(es_weights),
        "--matchups", "es", "smart",
        "--games-es", str(games_es),
        "--games-smart", str(games_smart),
        "--seed", str(seed),
        "--out", str(output),
        "--device", "cpu",
    ]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dataset", required=True)
    parser.add_argument("--output-root", required=True)
    parser.add_argument("--es-weights", default="artifacts/es_bot/best.npz")
    parser.add_argument("--variants", nargs="+", choices=("flat", "pointer"),
                        default=["flat", "pointer"])
    parser.add_argument("--seeds", nargs="+", type=int, default=[17, 42, 73])
    parser.add_argument("--epochs", type=int, default=15)
    parser.add_argument("--batch-size", type=int, default=512)
    parser.add_argument("--lr", type=float, default=3e-4)
    parser.add_argument("--games-es", type=int, default=200)
    parser.add_argument("--games-smart", type=int, default=200)
    parser.add_argument("--eval-seed", type=int, default=80_000)
    parser.add_argument("--phase", choices=("train", "eval", "all"), default="all")
    parser.add_argument("--reuse", action="append", default=[])
    parser.add_argument("--dry-run", action="store_true")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    dataset = Path(args.dataset).resolve()
    output_root = Path(args.output_root).resolve()
    es_weights = Path(args.es_weights).resolve()
    if not dataset.is_file():
        raise FileNotFoundError(dataset)
    if not es_weights.is_file():
        raise FileNotFoundError(es_weights)
    reuse = parse_reuse(args.reuse)

    config = {
        "schema_version": SCHEMA_VERSION,
        "source_commit": git_head(),
        "dataset": str(dataset),
        "dataset_sha256": file_sha256(dataset),
        "es_weights": str(es_weights),
        "es_weights_sha256": file_sha256(es_weights),
        "variants": args.variants,
        "seeds": args.seeds,
        "epochs": args.epochs,
        "batch_size": args.batch_size,
        "learning_rate": args.lr,
        "games_es": args.games_es,
        "games_smart": args.games_smart,
        "eval_seed": args.eval_seed,
    }
    manifest_path = output_root / "manifest.json"
    if manifest_path.exists():
        existing = json.loads(manifest_path.read_text())
        if existing != config:
            raise ValueError(
                f"existing experiment manifest differs from requested config: {manifest_path}"
            )
    elif not args.dry_run:
        atomic_json(manifest_path, config)

    state_path = output_root / "state.json"
    state = json.loads(state_path.read_text()) if state_path.exists() else {"runs": {}}
    commands: list[tuple[str, str, list[str], Path]] = []

    for variant in args.variants:
        for seed in args.seeds:
            run_id = f"{variant}_seed{seed}"
            run_dir = output_root / run_id
            checkpoint = run_dir / f"{run_id}.pt"
            evaluation = run_dir / "evaluation.json"
            reused = reuse.get((variant, seed))
            if reused is not None:
                checkpoint = reused
                state["runs"].setdefault(run_id, {})["reused_checkpoint"] = str(reused)

            if args.phase in {"train", "all"} and reused is None and not checkpoint.exists():
                commands.append(
                    (
                        run_id,
                        "train",
                        build_train_command(
                            dataset=dataset,
                            checkpoint=checkpoint,
                            variant=variant,
                            seed=seed,
                            epochs=args.epochs,
                            batch_size=args.batch_size,
                            learning_rate=args.lr,
                        ),
                        run_dir / "train.log",
                    )
                )
            if args.phase in {"eval", "all"} and not evaluation.exists():
                commands.append(
                    (
                        run_id,
                        "eval",
                        build_eval_command(
                            checkpoint=checkpoint,
                            es_weights=es_weights,
                            output=evaluation,
                            games_es=args.games_es,
                            games_smart=args.games_smart,
                            seed=args.eval_seed,
                        ),
                        run_dir / "eval.log",
                    )
                )

    for run_id, phase, command, log_path in commands:
        print(f"[{run_id}:{phase}] {' '.join(command)}", flush=True)
        if args.dry_run:
            continue
        log_path.parent.mkdir(parents=True, exist_ok=True)
        run_state = state["runs"].setdefault(run_id, {})
        run_state[phase] = {"status": "running", "command": command}
        atomic_json(state_path, state)
        environment = os.environ.copy()
        environment["PYTHONUNBUFFERED"] = "1"
        environment["PYTHONPATH"] = f"{ROOT / 'src'}:{ROOT / 'cpp' / 'build'}:{ROOT}"
        with log_path.open("w") as log:
            result = subprocess.run(
                command,
                cwd=ROOT,
                env=environment,
                stdout=log,
                stderr=subprocess.STDOUT,
                check=False,
            )
        run_state[phase] = {
            "status": "complete" if result.returncode == 0 else "failed",
            "returncode": result.returncode,
            "command": command,
            "log": str(log_path),
        }
        atomic_json(state_path, state)
        if result.returncode != 0:
            raise RuntimeError(f"{run_id} {phase} failed; see {log_path}")

    if not args.dry_run:
        print(f"[done] state={state_path}")


if __name__ == "__main__":
    main()
