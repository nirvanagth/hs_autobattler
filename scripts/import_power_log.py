"""Import a private Power.log into sanitized deterministic JSONL artifacts."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from hearthstone.traces.powerlog import (
    PARSER_VERSION,
    POWERLOG_SCHEMA_VERSION,
    event_json,
    event_stream_sha256,
    load_power_log,
    reconstruct_transitions,
)


def _atomic_text(path: Path, text: str) -> None:
    temporary = path.with_suffix(".tmp")
    temporary.write_text(text)
    temporary.replace(path)


def _validate_output(output: Path) -> None:
    resolved = output.resolve()
    artifacts = (ROOT / "artifacts").resolve()
    if resolved.is_relative_to(ROOT.resolve()) and not resolved.is_relative_to(artifacts):
        raise ValueError("sanitized trace output inside the repository must be under artifacts/")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", required=True)
    parser.add_argument("--out-dir", required=True)
    args = parser.parse_args()
    source = Path(args.input)
    output = Path(args.out_dir)
    if not source.is_file():
        raise FileNotFoundError(source)
    _validate_output(output)
    if (output / "metadata.json").exists():
        raise FileExistsError(f"refusing to overwrite imported trace: {output}")
    output.mkdir(parents=True, exist_ok=True)
    result = load_power_log(source)
    transitions = reconstruct_transitions(result.events)
    events_text = "".join(event_json(event) + "\n" for event in result.events)
    transitions_text = "".join(
        json.dumps(item, sort_keys=True, separators=(",", ":")) + "\n"
        for item in transitions
    )
    _atomic_text(output / "events.jsonl", events_text)
    _atomic_text(output / "transitions.jsonl", transitions_text)
    metadata = {
        "schema_version": POWERLOG_SCHEMA_VERSION,
        "parser_version": PARSER_VERSION,
        "source_sha256": hashlib.sha256(source.read_bytes()).hexdigest(),
        "total_lines": result.total_lines,
        "events": len(result.events),
        "transitions": len(transitions),
        "ignored_lines": result.ignored_lines,
        "ignored_tag_counts": dict(sorted(result.ignored_tag_counts.items())),
        "event_stream_sha256": event_stream_sha256(result.events),
        "privacy": {
            "raw_lines_stored": False,
            "entity_names_stored": False,
            "source_path_stored": False,
        }
    }
    _atomic_text(output / "metadata.json", json.dumps(metadata, indent=2, sort_keys=True) + "\n")
    print(json.dumps(metadata, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
