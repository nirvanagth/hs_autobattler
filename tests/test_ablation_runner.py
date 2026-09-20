"""Tests for the matched ablation orchestrator."""

from pathlib import Path

from scripts.run_matched_ablation import build_eval_command, build_train_command


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
