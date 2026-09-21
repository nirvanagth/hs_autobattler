"""Resumable matched PPO ablation: plain, teacher-KL, and KL+oracle."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

from run_matched_ablation import atomic_json, file_sha256, git_head


VARIANTS = ("ppo", "kl", "oracle")


def parse_parents(specs: list[str]) -> dict[int, Path]:
    result: dict[int, Path] = {}
    for spec in specs:
        if "=" not in spec:
            raise ValueError(f"parent must be SEED=CHECKPOINT, got {spec!r}")
        raw_seed, raw_path = spec.split("=", 1)
        path = Path(raw_path).resolve()
        if not path.is_file():
            raise FileNotFoundError(path)
        result[int(raw_seed)] = path
    return result


def build_train_command(
    *,
    parent: Path,
    output_dir: Path,
    variant: str,
    seed: int,
    timesteps: int,
    learning_rate: float,
    entropy_start: float,
    entropy_end: float,
    n_envs: int,
    n_steps: int,
    n_minibatches: int,
) -> list[str]:
    command = [
        sys.executable,
        str(ROOT / "scripts" / "train_ppo.py"),
        "--resume", str(parent),
        "--out-dir", str(output_dir),
        "--total-timesteps", str(timesteps),
        "--seed", str(seed),
        "--lr", str(learning_rate),
        "--ent-coef", str(entropy_start),
        "--ent-coef-end", str(entropy_end),
        "--ent-decay-frac", "1.0",
        "--n-envs", str(n_envs),
        "--n-steps", str(n_steps),
        "--n-minibatches", str(n_minibatches),
        "--save-interval", "10",
        "--eval-interval", "10",
    ]
    if variant == "ppo":
        command.extend(["--bc-kl-coef", "0", "--reward-mode", "sparse"])
    elif variant == "kl":
        command.extend(
            [
                "--bc-kl-coef", "0.1",
                "--bc-kl-decay-frac", "2.0",
                "--reward-mode", "sparse",
            ]
        )
    elif variant == "oracle":
        command.extend(
            [
                "--bc-kl-coef", "0.1",
                "--bc-kl-decay-frac", "2.0",
                "--reward-mode", "oracle_potential",
                "--oracle-n-combats", "64",
                "--oracle-scale", "1.0",
            ]
        )
    else:
        raise ValueError(variant)
    return command


def build_eval_command(
    checkpoint: Path,
    es_weights: Path,
    output: Path,
    games_es: int,
    games_smart: int,
    eval_seed: int,
) -> list[str]:
    return [
        sys.executable,
        str(ROOT / "scripts" / "evaluate_checkpoints.py"),
        "--checkpoints", str(checkpoint),
        "--es-weights", str(es_weights),
        "--matchups", "es", "smart",
        "--games-es", str(games_es),
        "--games-smart", str(games_smart),
        "--seed", str(eval_seed),
        "--out", str(output),
        "--device", "cpu",
    ]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-root", required=True)
    parser.add_argument("--parent", action="append", required=True,
                        help="SEED=POINTER_DAGGER_CHECKPOINT")
    parser.add_argument("--es-weights", default="artifacts/es_bot/best.npz")
    parser.add_argument("--variants", nargs="+", choices=VARIANTS,
                        default=list(VARIANTS))
    parser.add_argument("--seeds", nargs="+", type=int, default=[17, 42, 73])
    parser.add_argument("--timesteps", type=int, default=327_680)
    parser.add_argument("--lr", type=float, default=3e-5)
    parser.add_argument("--ent-coef", type=float, default=0.005)
    parser.add_argument("--ent-coef-end", type=float, default=0.001)
    parser.add_argument("--n-envs", type=int, default=8)
    parser.add_argument("--n-steps", type=int, default=2048)
    parser.add_argument("--n-minibatches", type=int, default=16)
    parser.add_argument("--games-es", type=int, default=200)
    parser.add_argument("--games-smart", type=int, default=200)
    parser.add_argument("--eval-seed", type=int, default=80_000)
    parser.add_argument("--phase", choices=("train", "eval", "all"), default="all")
    parser.add_argument("--dry-run", action="store_true")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    parents = parse_parents(args.parent)
    if set(args.seeds) != set(parents):
        raise ValueError(f"parent seeds {sorted(parents)} != requested seeds {sorted(args.seeds)}")
    output_root = Path(args.output_root).resolve()
    es_weights = Path(args.es_weights).resolve()
    if not es_weights.is_file():
        raise FileNotFoundError(es_weights)

    config = {
        "schema_version": 1,
        "source_commit": git_head(),
        "parents": {
            str(seed): {"path": str(path), "sha256": file_sha256(path)}
            for seed, path in sorted(parents.items())
        },
        "es_weights": str(es_weights),
        "es_weights_sha256": file_sha256(es_weights),
        "variants": args.variants,
        "seeds": args.seeds,
        "timesteps": args.timesteps,
        "learning_rate": args.lr,
        "entropy_start": args.ent_coef,
        "entropy_end": args.ent_coef_end,
        "n_envs": args.n_envs,
        "n_steps": args.n_steps,
        "n_minibatches": args.n_minibatches,
        "games_es": args.games_es,
        "games_smart": args.games_smart,
        "eval_seed": args.eval_seed,
    }
    manifest_path = output_root / "manifest.json"
    if manifest_path.exists():
        if json.loads(manifest_path.read_text()) != config:
            raise ValueError(f"manifest mismatch: {manifest_path}")
    elif not args.dry_run:
        atomic_json(manifest_path, config)

    state_path = output_root / "state.json"
    state = json.loads(state_path.read_text()) if state_path.exists() else {"runs": {}}
    commands: list[tuple[str, str, list[str], Path]] = []
    for variant in args.variants:
        for seed in args.seeds:
            run_id = f"{variant}_seed{seed}"
            run_dir = output_root / run_id
            checkpoint = run_dir / "final.pt"
            evaluation = run_dir / "evaluation.json"
            if args.phase in {"train", "all"} and not checkpoint.exists():
                commands.append(
                    (
                        run_id,
                        "train",
                        build_train_command(
                            parent=parents[seed],
                            output_dir=run_dir,
                            variant=variant,
                            seed=seed,
                            timesteps=args.timesteps,
                            learning_rate=args.lr,
                            entropy_start=args.ent_coef,
                            entropy_end=args.ent_coef_end,
                            n_envs=args.n_envs,
                            n_steps=args.n_steps,
                            n_minibatches=args.n_minibatches,
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
                            checkpoint,
                            es_weights,
                            evaluation,
                            args.games_es,
                            args.games_smart,
                            args.eval_seed,
                        ),
                        run_dir / "eval.log",
                    )
                )

    environment = os.environ.copy()
    environment["PYTHONUNBUFFERED"] = "1"
    environment["PYTHONPATH"] = f"{ROOT / 'src'}:{ROOT / 'cpp' / 'build'}:{ROOT}"
    for run_id, phase, command, log_path in commands:
        print(f"[{run_id}:{phase}] {' '.join(command)}", flush=True)
        if args.dry_run:
            continue
        log_path.parent.mkdir(parents=True, exist_ok=True)
        run_state = state["runs"].setdefault(run_id, {})
        run_state[phase] = {"status": "running", "command": command}
        atomic_json(state_path, state)
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
