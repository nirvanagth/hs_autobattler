"""One-command verification of the research artifact pipeline."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from hearthstone.engine.cpp_bridge import get_cpp_engine
from hearthstone.env.es_bot import N_WEIGHTS
from hearthstone.env.hs_env import HearthstoneEnv


DEFAULT_BENCHMARK = ROOT / "benchmarks" / "hsbg_1v1_v1.json"


def file_sha256(path: Path) -> str:
    import hashlib

    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def run(command: list[str], environment: dict[str, str]) -> None:
    print(f"[verify] {' '.join(command)}", flush=True)
    subprocess.run(command, cwd=ROOT, env=environment, check=True)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--full-tests", action="store_true")
    parser.add_argument("--report", default=None)
    parser.add_argument("--benchmark", default=str(DEFAULT_BENCHMARK))
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    native = get_cpp_engine()
    if native is None:
        raise RuntimeError(
            "C++ combat engine is required; build it and include cpp/build in PYTHONPATH"
        )
    env = HearthstoneEnv(card_vocab_scheme="stable_v1")
    contract = env.environment_contract
    benchmark_path = Path(args.benchmark).resolve()
    benchmark = json.loads(benchmark_path.read_text())
    if benchmark.get("environment_contract") != contract:
        raise RuntimeError(
            "runtime environment does not match frozen benchmark contract: "
            f"runtime={contract}, frozen={benchmark.get('environment_contract')}"
        )
    smart_source = ROOT / benchmark["opponents"]["smartbot_source"]["path"]
    expected_smart_hash = benchmark["opponents"]["smartbot_source"]["sha256"]
    actual_smart_hash = file_sha256(smart_source)
    if actual_smart_hash != expected_smart_hash:
        raise RuntimeError(
            "SmartBot source does not match frozen benchmark: "
            f"runtime={actual_smart_hash}, frozen={expected_smart_hash}"
        )

    process_environment = os.environ.copy()
    process_environment["PYTHONUNBUFFERED"] = "1"
    process_environment["PYTHONPATH"] = (
        f"{ROOT / 'src'}:{ROOT / 'cpp' / 'build'}:{ROOT}"
    )
    python = sys.executable

    if args.full_tests:
        run([python, "-m", "pytest", "tests", "-q"], process_environment)
    else:
        run(
            [
                python,
                "-m",
                "pytest",
                "tests/test_environment_contract.py",
                "tests/test_model_v2.py",
                "tests/test_dagger.py",
                "tests/test_ablation_runner.py",
                "-q",
            ],
            process_environment,
        )

    with tempfile.TemporaryDirectory(prefix="hs_research_verify_") as raw_dir:
        temp = Path(raw_dir)
        weights = temp / "teacher.npz"
        dataset = temp / "bc.npz"
        bc_checkpoint = temp / "bc.pt"
        ppo_dir = temp / "ppo"
        evaluation = temp / "evaluation.json"
        np.savez(weights, weights=np.zeros(N_WEIGHTS, dtype=np.float32))

        run(
            [
                python, "scripts/bc_collect.py",
                "--weights", str(weights),
                "--episodes", "2",
                "--log-every", "2",
                "--out", str(dataset),
            ],
            process_environment,
        )
        run(
            [
                python, "scripts/bc_train.py",
                "--dataset", str(dataset),
                "--out", str(bc_checkpoint),
                "--epochs", "1",
                "--batch-size", "64",
                "--d-model", "64",
                "--n-heads", "4",
                "--n-layers", "2",
            ],
            process_environment,
        )
        run(
            [
                python, "scripts/train_ppo.py",
                "--resume", str(bc_checkpoint),
                "--out-dir", str(ppo_dir),
                "--total-timesteps", "64",
                "--n-envs", "2",
                "--n-steps", "32",
                "--n-minibatches", "4",
                "--update-epochs", "1",
                "--d-model", "64",
                "--n-heads", "4",
                "--n-layers", "2",
                "--opponent-mode", "smart",
                "--save-interval", "100",
                "--eval-interval", "100",
            ],
            process_environment,
        )
        run(
            [
                python, "scripts/evaluate_checkpoints.py",
                "--checkpoints", str(ppo_dir / "final.pt"),
                "--bc-checkpoint", str(bc_checkpoint),
                "--matchups", "smart",
                "--games-smart", "2",
                "--out", str(evaluation),
                "--device", "cpu",
            ],
            process_environment,
        )
        evaluation_payload = json.loads(evaluation.read_text())
        candidate_keys = [
            key for key in evaluation_payload if not key.startswith("__")
        ]
        if len(candidate_keys) != 1:
            raise AssertionError("smoke evaluation did not emit exactly one candidate")
        stats = evaluation_payload[candidate_keys[0]]["smart"]
        if len(stats.get("episodes", [])) != 2:
            raise AssertionError("smoke evaluation did not preserve raw episodes")

    report = {
        "status": "ok",
        "native_module": str(Path(native.__file__).resolve()),
        "environment_contract": contract,
        "benchmark": str(benchmark_path),
        "benchmark_name": benchmark["benchmark_name"],
        "full_tests": args.full_tests,
    }
    if args.report:
        report_path = Path(args.report)
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text(json.dumps(report, indent=2))
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
