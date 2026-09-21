"""M1 ablation runner command tests."""

from argparse import Namespace
from pathlib import Path

from scripts.run_m1_ablation import CONDITION_FLAGS, train_command


def arguments():
    return Namespace(
        league="league.json",
        parent_id="parent",
        total_timesteps=8192,
        n_steps=1024,
        n_minibatches=8,
        update_epochs=4,
        oracle_n_combats=16,
        device="cpu",
    )


def test_ablation_matrix_has_all_predeclared_conditions() -> None:
    assert set(CONDITION_FLAGS) == {
        "public",
        "central",
        "central_aux",
        "central_oracle",
        "central_aux_oracle",
    }


def test_condition_flags_are_added_to_training_command() -> None:
    command = train_command(arguments(), "central_aux_oracle", 317, Path("model.pt"))
    assert "--central-critic" in command
    assert "--auxiliary-coef" in command
    assert "--reward-mode" in command
    assert "oracle_potential" in command
