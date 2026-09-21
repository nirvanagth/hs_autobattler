"""Tests for the matched ablation orchestrator."""

from pathlib import Path

from scripts.run_matched_ablation import build_eval_command, build_train_command
from scripts.run_matched_ppo_ablation import (
    build_train_command as build_ppo_train_command,
)
from scripts.evaluate_checkpoints import paired_bootstrap, wilson_interval
from scripts.run_lobby_memory_ablation import (
    build_train_command as build_lobby_train_command,
)


def test_train_command_pins_variant_seed_and_budget(tmp_path: Path) -> None:
    command = build_train_command(
        dataset=tmp_path / "data.npz",
        checkpoint=tmp_path / "flat.pt",
        variant="flat",
        seed=17,
        epochs=3,
        batch_size=64,
        learning_rate=1e-4,
        parent_checkpoint=tmp_path / "parent.pt",
    )
    assert command[command.index("--actor-type") + 1] == "flat"
    assert command[command.index("--seed") + 1] == "17"
    assert command[command.index("--epochs") + 1] == "3"
    assert command[command.index("--resume") + 1] == str(tmp_path / "parent.pt")


def test_eval_command_uses_fixed_seed_suite(tmp_path: Path) -> None:
    command = build_eval_command(
        checkpoint=tmp_path / "pointer.pt",
        es_weights=tmp_path / "es.npz",
        output=tmp_path / "eval.json",
        games_es=200,
        games_smart=200,
        seed=80_000,
    )
    assert command[command.index("--games-es") + 1] == "200"
    assert command[command.index("--games-smart") + 1] == "200"
    assert command[command.index("--seed") + 1] == "80000"


def test_ppo_ablation_changes_only_variant_controls(tmp_path: Path) -> None:
    common = dict(
        parent=tmp_path / "parent.pt",
        output_dir=tmp_path / "run",
        seed=17,
        timesteps=327_680,
        learning_rate=3e-5,
        entropy_start=0.005,
        entropy_end=0.001,
        n_envs=8,
        n_steps=2048,
        n_minibatches=16,
    )
    plain = build_ppo_train_command(variant="ppo", **common)
    oracle = build_ppo_train_command(variant="oracle", **common)
    assert plain[plain.index("--bc-kl-coef") + 1] == "0"
    assert plain[plain.index("--reward-mode") + 1] == "sparse"
    assert oracle[oracle.index("--bc-kl-coef") + 1] == "0.1"
    assert oracle[oracle.index("--reward-mode") + 1] == "oracle_potential"
    assert oracle[oracle.index("--oracle-n-combats") + 1] == "64"


def test_wilson_interval_contains_observed_rate() -> None:
    low, high = wilson_interval(60, 100)
    assert low < 0.6 < high


def test_paired_bootstrap_uses_seed_and_seat_pairs() -> None:
    left = [
        {"seed": 1, "candidate_seat": 0, "outcome": "win"},
        {"seed": 1, "candidate_seat": 1, "outcome": "draw"},
    ]
    right = [
        {"seed": 1, "candidate_seat": 0, "outcome": "loss"},
        {"seed": 1, "candidate_seat": 1, "outcome": "draw"},
    ]
    result = paired_bootstrap(left, right, seed=42, samples=1000)
    assert result["n"] == 2
    assert result["mean"] == 0.5


def test_lobby_memory_ablation_switches_only_gru_flag(tmp_path: Path) -> None:
    common = (
        tmp_path / "data.npz",
        tmp_path / "model.pt",
    )
    feedforward = build_lobby_train_command(*common, "ff", 17, 5, 8, 3e-4)
    recurrent = build_lobby_train_command(*common, "gru", 17, 5, 8, 3e-4)
    assert "--use-memory" not in feedforward
    assert recurrent[-1] == "--use-memory"
