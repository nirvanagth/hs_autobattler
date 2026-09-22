"""Aggregate sanitized trace imports without retaining source paths."""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from hearthstone.traces.powerlog import (
    ACTION_CLASSIFIER_VERSION,
    classify_battlegrounds_action,
)


def read_jsonl(path: Path):
    for line in path.read_text().splitlines():
        if line:
            yield json.loads(line)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--import-dir", action="append", required=True)
    parser.add_argument("--target-actions", type=int, default=10000)
    parser.add_argument("--out", required=True)
    args = parser.parse_args()
    inputs = []
    action_counts: Counter[str] = Counter()
    card_ids = set()
    trace_schema_versions = set()
    totals: Counter[str] = Counter()
    for index, raw_directory in enumerate(args.import_dir, start=1):
        directory = Path(raw_directory)
        metadata = json.loads((directory / "metadata.json").read_text())
        trace_schema_versions.add(int(metadata.get("schema_version", 1)))
        input_record = {
            "input_index": index,
            "source_sha256": metadata["source_sha256"],
            "event_stream_sha256": metadata["event_stream_sha256"],
            "sessions": metadata["sessions"],
            "battlegrounds_sessions": metadata["battlegrounds_sessions"],
            "events": metadata["events"],
            "top_level_transitions": metadata["transitions"],
            "action_transitions": 0,
        }
        inputs.append(input_record)
        for key in (
            "sessions",
            "battlegrounds_sessions",
            "events",
            "transitions",
        ):
            totals[key] += int(metadata[key])
        for event in read_jsonl(directory / "events.jsonl"):
            if event.get("card_id"):
                card_ids.add(event["card_id"])
        for transition in read_jsonl(directory / "action_transitions.jsonl"):
            action_type = classify_battlegrounds_action(
                transition.get("source_card_id"), transition.get("block_type")
            )
            if action_type is not None:
                totals["action_transitions"] += 1
                input_record["action_transitions"] += 1
                action_counts[action_type] += 1
    remaining = max(0, args.target_actions - totals["action_transitions"])
    report = {
        "schema_version": 2,
        "trace_schema_version": (
            next(iter(trace_schema_versions)) if len(trace_schema_versions) == 1 else None
        ),
        "source_trace_schema_versions": sorted(trace_schema_versions),
        "action_classifier_version": ACTION_CLASSIFIER_VERSION,
        "inputs": inputs,
        "totals": {
            "sessions": totals["sessions"],
            "battlegrounds_sessions": totals["battlegrounds_sessions"],
            "events": totals["events"],
            "top_level_transitions": totals["transitions"],
            "action_transitions": totals["action_transitions"],
            "unique_live_card_ids": len(card_ids),
            "action_counts": dict(sorted(action_counts.items())),
        },
        "gate": {
            "target_action_transitions": args.target_actions,
            "remaining_action_transitions": remaining,
            "status": "passed" if remaining == 0 else "pending_more_data",
        },
        "privacy": {
            "source_paths_stored": False,
            "raw_lines_stored": False,
            "entity_names_stored": False,
        },
    }
    output = Path(args.out)
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = output.with_suffix(".tmp")
    temporary.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    temporary.replace(output)
    print(json.dumps(report["totals"], indent=2, sort_keys=True))
    print(json.dumps(report["gate"], indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
