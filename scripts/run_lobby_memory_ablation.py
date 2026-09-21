"""Resumable matched feed-forward versus GRU lobby benchmark."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

from run_matched_ablation import atomic_json, file_sha256, git_head, parse_reuse


def build_train_command(dataset, output, variant, seed, epochs, batch_size, lr):
    command = [
        sys.executable,
        str(ROOT / "scripts/lobby_bc_train.py"),
        "--dataset", str(dataset),
        "--out", str(output),
        "--seed", str(seed),
        "--epochs", str(epochs),
        "--batch-size", str(batch_size),
        "--lr", str(lr),
    ]
    if variant == "gru":
        command.append("--use-memory")
    return command


def parse_args():
    parser = argparse.ArgumentParser()
    parser.add_argument("--dataset", required=True)
    parser.add_argument("--output-root", required=True)
    parser.add_argument("--seeds", nargs="+", type=int, default=[17, 42, 73])
    parser.add_argument("--epochs", type=int, default=5)
    parser.add_argument("--batch-size", type=int, default=8)
    parser.add_argument("--lr", type=float, default=3e-4)
    parser.add_argument("--eval-episodes", type=int, default=200)
    parser.add_argument("--eval-seed", type=int, default=170_000)
    parser.add_argument("--reuse", action="append", default=[])
    parser.add_argument("--dry-run", action="store_true")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    dataset = Path(args.dataset).resolve()
    output_root = Path(args.output_root).resolve()
    reuse = parse_reuse(args.reuse)
    config = {
        "schema_version": 1,
        "source_commit": git_head(),
        "dataset": str(dataset),
        "dataset_sha256": file_sha256(dataset),
        "seeds": args.seeds,
        "epochs": args.epochs,
        "batch_size": args.batch_size,
        "learning_rate": args.lr,
        "eval_episodes": args.eval_episodes,
        "eval_seed": args.eval_seed,
    }
    manifest = output_root / "manifest.json"
    if manifest.exists():
        if json.loads(manifest.read_text()) != config:
            raise ValueError(f"manifest mismatch: {manifest}")
    elif not args.dry_run:
        atomic_json(manifest, config)

    state_path = output_root / "state.json"
    state = json.loads(state_path.read_text()) if state_path.exists() else {"runs": {}}
    environment = os.environ.copy()
    environment["PYTHONUNBUFFERED"] = "1"
    environment["PYTHONPATH"] = f"{ROOT / 'src'}:{ROOT / 'cpp/build'}:{ROOT}"
    checkpoints = {}

    for variant in ("ff", "gru"):
        for seed in args.seeds:
            run_id = f"{variant}_seed{seed}"
            run_dir = output_root / run_id
            checkpoint = reuse.get((variant, seed), run_dir / f"{run_id}.pt")
            checkpoints[run_id] = checkpoint
            if checkpoint.exists():
                state["runs"].setdefault(run_id, {})["checkpoint"] = str(checkpoint)
                continue
            command = build_train_command(
                dataset, checkpoint, variant, seed, args.epochs, args.batch_size, args.lr
            )
            print(f"[{run_id}] {' '.join(command)}", flush=True)
            if args.dry_run:
                continue
            run_dir.mkdir(parents=True, exist_ok=True)
            state["runs"].setdefault(run_id, {})["train"] = {"status": "running"}
            atomic_json(state_path, state)
            log_path = run_dir / "train.log"
            with log_path.open("w") as log:
                result = subprocess.run(
                    command, cwd=ROOT, env=environment,
                    stdout=log, stderr=subprocess.STDOUT, check=False
                )
            state["runs"][run_id]["train"] = {
                "status": "complete" if result.returncode == 0 else "failed",
                "returncode": result.returncode,
                "log": str(log_path),
            }
            state["runs"][run_id]["checkpoint"] = str(checkpoint)
            atomic_json(state_path, state)
            if result.returncode:
                raise RuntimeError(f"{run_id} failed; see {log_path}")

    evaluation = output_root / "evaluation.json"
    if not evaluation.exists():
        command = [
            sys.executable,
            str(ROOT / "scripts/evaluate_lobby_models.py"),
        ]
        for run_id, checkpoint in checkpoints.items():
            command.extend(["--run", f"{run_id}={checkpoint}"])
        command.extend(
            [
                "--episodes", str(args.eval_episodes),
                "--seed-base", str(args.eval_seed),
                "--out", str(evaluation),
                "--device", "cpu",
            ]
        )
        print(f"[evaluation] {' '.join(command)}", flush=True)
        if not args.dry_run:
            with (output_root / "eval.log").open("w") as log:
                result = subprocess.run(
                    command, cwd=ROOT, env=environment,
                    stdout=log, stderr=subprocess.STDOUT, check=False
                )
            state["evaluation"] = {
                "status": "complete" if result.returncode == 0 else "failed",
                "returncode": result.returncode,
            }
            atomic_json(state_path, state)
            if result.returncode:
                raise RuntimeError(f"lobby evaluation failed; see {output_root / 'eval.log'}")
    if not args.dry_run:
        print(f"[done] {state_path}")


if __name__ == "__main__":
    main()
