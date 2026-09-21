"""M1 cross-seed summary tests."""

import json

from scripts.summarize_m1_ablation import summarize


def test_summary_ranks_conditions_by_mean_placement(tmp_path) -> None:
    (tmp_path / "manifest.json").write_text('{"reused_checkpoints": {}}')
    (tmp_path / "selection_schedule.json").write_text("{}")
    comparisons = {"comparisons": {}}
    for condition, placements in {"first": (2.0, 4.0), "second": (1.0, 2.0)}.items():
        for seed, placement in zip((1, 2), placements):
            run_id = f"{condition}_seed{seed}"
            run_dir = tmp_path / run_id
            run_dir.mkdir()
            (run_dir / f"{run_id}.pt").write_bytes(run_id.encode())
            (run_dir / "selection.json").write_text(
                json.dumps(
                    {
                        "mean_placement": placement,
                        "top4_rate": 0.5,
                        "win_rate": 0.25,
                    }
                )
            )
            comparisons["comparisons"][run_id] = {
                "placement_improvement": {"mean": 4.0 - placement}
            }
    (tmp_path / "selection_comparison.json").write_text(json.dumps(comparisons))
    result = summarize(tmp_path, ["first", "second"], [1, 2])
    assert result["ranking"] == ["second", "first"]
    assert result["conditions"]["first"]["placement"]["mean"] == 3.0
