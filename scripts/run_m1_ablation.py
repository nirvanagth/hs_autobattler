"""Resumable matched M1 centralized-critic/auxiliary/oracle ablation."""

from __future__ import annotations

import argparse
import concurrent.futures
import json
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

from hearthstone.league import PolicyLeague, file_sha256
from run_matched_ablation import atomic_json, git_head


CONDITION_FLAGS = {
    "public": [],
    "central": ["--central-critic"],
    "central_aux": ["--central-critic", "--auxiliary-coef", "0.2"],
    "central_oracle": [
        "--central-critic",
        "--reward-mode",
        "oracle_potential",
    ],
    "central_aux_oracle": [
        "--central-critic",
        "--auxiliary-coef",
        "0.2",
        "--reward-mode",
        "oracle_potential",
    ],
}


def train_command(args, condition: str, seed: int, checkpoint: Path) -> list[str]:
    return [
        sys.executable,
        str(ROOT / "scripts/train_lobby_league_ppo.py"),
        "--league",
        str(Path(args.league).resolve()),
        "--parent-id",
        args.parent_id,
        "--out",
        str(checkpoint),
        "--total-timesteps",
        str(args.total_timesteps),
        "--n-steps",
        str(args.n_steps),
        "--n-minibatches",
        str(args.n_minibatches),
        "--update-epochs",
        str(args.update_epochs),
        "--oracle-n-combats",
        str(args.oracle_n_combats),
        "--device",
        args.device,
        "--seed",
        str(seed),
        *CONDITION_FLAGS[condition],
    ]


def evaluation_command(
    args, label: str, checkpoint: Path | None, schedule: Path, output: Path
) -> list[str]:
    command = [
        sys.executable,
        str(ROOT / "scripts/evaluate_lobby_league.py"),
        "--league",
        str(Path(args.league).resolve()),
        "--candidate",
        label,
        "--schedule",
        str(schedule),
        "--device",
        args.eval_device,
        "--out",
        str(output),
    ]
    if checkpoint is not None:
        command.extend(["--candidate-checkpoint", str(checkpoint)])
    return command


def run_command(task: tuple[str, list[str], Path]) -> tuple[str, int]:
    run_id, command, log_path = task
    log_path.parent.mkdir(parents=True, exist_ok=True)
    environment = os.environ.copy()
    environment["PYTHONUNBUFFERED"] = "1"
    environment["PYTHONPATH"] = f"{ROOT / 'src'}:{ROOT / 'cpp/build'}:{ROOT}"
    with log_path.open("w") as log:
        result = subprocess.run(
            command,
            cwd=ROOT,
            env=environment,
            stdout=log,
            stderr=subprocess.STDOUT,
            check=False,
        )
    return run_id, result.returncode


def execute(tasks, jobs: int, state: dict, state_path: Path, dry_run: bool) -> None:
    for run_id, command, _log in tasks:
        print(f"[{run_id}] {' '.join(command)}", flush=True)
    if dry_run or not tasks:
        return
    with concurrent.futures.ThreadPoolExecutor(max_workers=jobs) as executor:
        futures = {executor.submit(run_command, task): task for task in tasks}
        for future in concurrent.futures.as_completed(futures):
            run_id, returncode = future.result()
            state["runs"].setdefault(run_id, {})["returncode"] = returncode
            state["runs"][run_id]["status"] = (
                "complete" if returncode == 0 else "failed"
            )
            atomic_json(state_path, state)
            print(f"[{run_id}] returncode={returncode}", flush=True)
            if returncode:
                raise RuntimeError(f"{run_id} failed; see its log")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--league", required=True)
    parser.add_argument("--parent-id", required=True)
    parser.add_argument("--output-root", required=True)
    parser.add_argument(
        "--reuse-root",
        help="reuse matching checkpoints from another immutable experiment root",
    )
    parser.add_argument(
        "--conditions", nargs="+", choices=tuple(CONDITION_FLAGS), default=list(CONDITION_FLAGS)
    )
    parser.add_argument("--seeds", nargs="+", type=int, default=[317, 342, 373])
    parser.add_argument("--total-timesteps", type=int, default=8192)
    parser.add_argument("--n-steps", type=int, default=1024)
    parser.add_argument("--n-minibatches", type=int, default=8)
    parser.add_argument("--update-epochs", type=int, default=4)
    parser.add_argument("--oracle-n-combats", type=int, default=16)
    parser.add_argument("--eval-episodes", type=int, default=40)
    parser.add_argument("--eval-seed", type=int, default=400_000)
    parser.add_argument("--eval-min-per-policy", type=int, default=0)
    parser.add_argument("--device", choices=("cpu", "mps"), default="cpu")
    parser.add_argument("--eval-device", choices=("cpu", "mps"), default="cpu")
    parser.add_argument("--jobs", type=int, default=3)
    parser.add_argument("--phase", choices=("train", "eval", "all"), default="all")
    parser.add_argument("--dry-run", action="store_true")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    output_root = Path(args.output_root).resolve()
    league_path = Path(args.league).resolve()
    league = PolicyLeague.load(league_path)
    parent = league.entries[args.parent_id]
    reuse_root = Path(args.reuse_root).resolve() if args.reuse_root else None
    compatible_opponents = [
        policy_id
        for policy_id in league.entries
        if policy_id != args.parent_id
        and league.policies_are_compatible(args.parent_id, policy_id)
    ]
    if (
        args.phase in {"eval", "all"}
        and args.eval_min_per_policy * len(compatible_opponents)
        > args.eval_episodes * 7
    ):
        raise ValueError(
            "evaluation schedule cannot satisfy minimum coverage: "
            f"{len(compatible_opponents)} policies * {args.eval_min_per_policy} "
            f"> {args.eval_episodes * 7} seats"
        )
    reused_checkpoints = {}
    if reuse_root is not None:
        for condition in args.conditions:
            for seed in args.seeds:
                run_id = f"{condition}_seed{seed}"
                checkpoint = reuse_root / run_id / f"{run_id}.pt"
                if not checkpoint.is_file():
                    raise FileNotFoundError(checkpoint)
                reused_checkpoints[run_id] = {
                    "path": str(checkpoint),
                    "sha256": file_sha256(checkpoint),
                }
    config = {
        "schema_version": 1,
        "source_commit": git_head(),
        "league": str(league_path),
        "league_sha256": file_sha256(league_path),
        "parent_id": args.parent_id,
        "parent_sha256": parent.artifact_sha256,
        "conditions": args.conditions,
        "condition_flags": {name: CONDITION_FLAGS[name] for name in args.conditions},
        "seeds": args.seeds,
        "total_timesteps": args.total_timesteps,
        "n_steps": args.n_steps,
        "n_minibatches": args.n_minibatches,
        "update_epochs": args.update_epochs,
        "oracle_n_combats": args.oracle_n_combats,
        "eval_episodes": args.eval_episodes,
        "eval_seed": args.eval_seed,
        "eval_min_per_policy": args.eval_min_per_policy,
        "reused_checkpoints": reused_checkpoints,
    }
    manifest_path = output_root / "manifest.json"
    if manifest_path.exists():
        if json.loads(manifest_path.read_text()) != config:
            raise ValueError(f"manifest mismatch: {manifest_path}")
    elif not args.dry_run:
        atomic_json(manifest_path, config)
    state_path = output_root / "state.json"
    state = json.loads(state_path.read_text()) if state_path.exists() else {"runs": {}}

    checkpoints = {}
    if args.phase in {"train", "all"}:
        tasks = []
        for condition in args.conditions:
            for seed in args.seeds:
                run_id = f"{condition}_seed{seed}"
                checkpoint = (
                    reuse_root / run_id / f"{run_id}.pt"
                    if reuse_root is not None
                    else output_root / run_id / f"{run_id}.pt"
                )
                checkpoints[run_id] = checkpoint
                if reuse_root is None and not checkpoint.exists():
                    tasks.append(
                        (
                            f"train:{run_id}",
                            train_command(args, condition, seed, checkpoint),
                            output_root / run_id / "train.log",
                        )
                    )
        execute(tasks, args.jobs, state, state_path, args.dry_run)
    else:
        for condition in args.conditions:
            for seed in args.seeds:
                run_id = f"{condition}_seed{seed}"
                checkpoints[run_id] = (
                    reuse_root / run_id / f"{run_id}.pt"
                    if reuse_root is not None
                    else output_root / run_id / f"{run_id}.pt"
                )

    if args.phase in {"eval", "all"}:
        schedule = output_root / "selection_schedule.json"
        if not schedule.exists() and not args.dry_run:
            subprocess.run(
                [
                    sys.executable,
                    str(ROOT / "scripts/make_lobby_league_schedule.py"),
                    "--league",
                    str(league_path),
                    "--reference",
                    args.parent_id,
                    "--episodes",
                    str(args.eval_episodes),
                    "--seed-base",
                    str(args.eval_seed),
                    "--min-per-policy",
                    str(args.eval_min_per_policy),
                    "--out",
                    str(schedule),
                ],
                cwd=ROOT,
                check=True,
            )
        tasks = []
        parent_evaluation = output_root / "selection_parent.json"
        if not parent_evaluation.exists():
            tasks.append(
                (
                    "eval:parent",
                    evaluation_command(
                        args, args.parent_id, None, schedule, parent_evaluation
                    ),
                    output_root / "selection_parent.log",
                )
            )
        for run_id, checkpoint in checkpoints.items():
            evaluation = output_root / run_id / "selection.json"
            if not evaluation.exists():
                tasks.append(
                    (
                        f"eval:{run_id}",
                        evaluation_command(args, run_id, checkpoint, schedule, evaluation),
                        output_root / run_id / "selection.log",
                    )
                )
        execute(tasks, args.jobs, state, state_path, args.dry_run)
        comparison = output_root / "selection_comparison.json"
        if not comparison.exists() and not args.dry_run:
            command = [
                sys.executable,
                str(ROOT / "scripts/compare_lobby_league.py"),
                "--reference",
                str(parent_evaluation),
                "--seed",
                str(args.eval_seed),
                "--out",
                str(comparison),
            ]
            for run_id in sorted(checkpoints):
                command.extend(
                    [
                        "--challenger",
                        f"{run_id}={output_root / run_id / 'selection.json'}",
                    ]
                )
            subprocess.run(command, cwd=ROOT, check=True)
    if not args.dry_run:
        print(f"[done] {output_root}")


if __name__ == "__main__":
    main()
