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
    battlegrounds_session_ids,
    load_power_log,
    reconstruct_transitions,
    reconstruct_action_transitions,
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
    parser.add_argument("--quiet", action="store_true")
    parser.add_argument("--battlegrounds-only", action="store_true")
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
    bg_sessions = battlegrounds_session_ids(result.events)
    selected_events = (
        [event for event in result.events if event.session_index in bg_sessions]
        if args.battlegrounds_only
        else result.events
    )
    transitions = reconstruct_transitions(selected_events)
    action_transitions = reconstruct_action_transitions(selected_events)
    events_text = "".join(event_json(event) + "\n" for event in selected_events)
    transitions_text = "".join(
        json.dumps(item, sort_keys=True, separators=(",", ":")) + "\n"
        for item in transitions
    )
    action_transitions_text = "".join(
        json.dumps(item, sort_keys=True, separators=(",", ":")) + "\n"
        for item in action_transitions
    )
    _atomic_text(output / "events.jsonl", events_text)
    _atomic_text(output / "transitions.jsonl", transitions_text)
    _atomic_text(output / "action_transitions.jsonl", action_transitions_text)
    metadata = {
        "schema_version": POWERLOG_SCHEMA_VERSION,
        "parser_version": PARSER_VERSION,
        "source_sha256": hashlib.sha256(source.read_bytes()).hexdigest(),
        "total_lines": result.total_lines,
        "sessions": len(
            {
                event.session_index
                for event in result.events
                if event.session_index >= 0
            }
        ),
        "battlegrounds_sessions": len(bg_sessions),
        "battlegrounds_only": args.battlegrounds_only,
        "events": len(selected_events),
        "transitions": len(transitions),
        "action_transitions": len(action_transitions),
        "ignored_lines": result.ignored_lines,
        "ignored_tag_counts": dict(sorted(result.ignored_tag_counts.items())),
        "event_stream_sha256": event_stream_sha256(selected_events),
        "privacy": {
            "raw_lines_stored": False,
            "entity_names_stored": False,
            "source_path_stored": False,
        }
    }
    _atomic_text(output / "metadata.json", json.dumps(metadata, indent=2, sort_keys=True) + "\n")
    if not args.quiet:
        print(json.dumps(metadata, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
