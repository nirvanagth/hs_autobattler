"""Aggregate the matched M1 pilot across seeds and freeze artifact hashes."""

from __future__ import annotations

import argparse
import json
import statistics
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from hearthstone.league import file_sha256


def mean_std(values: list[float]) -> dict[str, float]:
    return {
        "mean": statistics.mean(values),
        "sample_std": statistics.stdev(values) if len(values) > 1 else 0.0,
    }


def summarize(root: Path, conditions: list[str], seeds: list[int]) -> dict:
    manifest_path = root / "manifest.json"
    manifest = json.loads(manifest_path.read_text())
    reused = manifest.get("reused_checkpoints", {})
    comparison_path = root / "selection_comparison.json"
    comparison = json.loads(comparison_path.read_text())
    result = {
        "schema_version": 1,
        "manifest_sha256": file_sha256(manifest_path),
        "schedule_sha256": file_sha256(root / "selection_schedule.json"),
        "comparison_sha256": file_sha256(comparison_path),
        "conditions": {},
    }
    for condition in conditions:
        metrics = {name: [] for name in ("placement", "top4", "win", "paired_delta")}
        checkpoints = {}
        reports = {}
        for seed in seeds:
            run_id = f"{condition}_seed{seed}"
            run_dir = root / run_id
            checkpoint = Path(
                reused.get(run_id, {}).get(
                    "path", run_dir / f"{run_id}.pt"
                )
            )
            report_path = run_dir / "selection.json"
            report = json.loads(report_path.read_text())
            metrics["placement"].append(float(report["mean_placement"]))
            metrics["top4"].append(float(report["top4_rate"]))
            metrics["win"].append(float(report["win_rate"]))
            metrics["paired_delta"].append(
                float(comparison["comparisons"][run_id]["placement_improvement"]["mean"])
            )
            checkpoints[str(seed)] = file_sha256(checkpoint)
            reports[str(seed)] = file_sha256(report_path)
        result["conditions"][condition] = {
            name: mean_std(values) for name, values in metrics.items()
        }
        result["conditions"][condition]["checkpoint_sha256"] = checkpoints
        result["conditions"][condition]["report_sha256"] = reports
    result["ranking"] = sorted(
        conditions,
        key=lambda name: result["conditions"][name]["placement"]["mean"],
    )
    return result


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", required=True)
    parser.add_argument("--conditions", nargs="+", required=True)
    parser.add_argument("--seeds", nargs="+", type=int, required=True)
    parser.add_argument("--out", required=True)
    args = parser.parse_args()
    payload = summarize(Path(args.root), args.conditions, args.seeds)
    output = Path(args.out)
    temporary = output.with_suffix(".tmp")
    temporary.write_text(json.dumps(payload, indent=2, sort_keys=True))
    temporary.replace(output)
    print(json.dumps(payload, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
