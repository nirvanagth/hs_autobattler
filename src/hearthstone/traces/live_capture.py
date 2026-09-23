"""Incrementally preserve privacy-safe Power.log events before log rotation."""

from __future__ import annotations

import hashlib
import json
import os
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from hearthstone.traces.powerlog import (
    PARSER_VERSION,
    POWERLOG_SCHEMA_VERSION,
    PowerLogStreamParser,
    TraceEvent,
    battlegrounds_session_ids,
    event_json,
    event_stream_sha256,
    reconstruct_action_transitions,
    reconstruct_transitions,
)


LIVE_CAPTURE_SCHEMA_VERSION = 1


def _atomic_text(path: Path, text: str) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(text)
    temporary.replace(path)


def read_sanitized_events(path: Path) -> list[TraceEvent]:
    return [TraceEvent(**json.loads(line)) for line in path.read_text().splitlines() if line]


def finalize_capture_directory(directory: Path, *, recovered: bool = False) -> dict[str, Any]:
    """Build transitions from an interrupted or completed sanitized capture."""
    events_path = directory / "events.jsonl"
    events = read_sanitized_events(events_path) if events_path.exists() else []
    transitions = reconstruct_transitions(events)
    action_transitions = reconstruct_action_transitions(events)
    _atomic_text(
        directory / "transitions.jsonl",
        "".join(
            json.dumps(item, sort_keys=True, separators=(",", ":")) + "\n" for item in transitions
        ),
    )
    _atomic_text(
        directory / "action_transitions.jsonl",
        "".join(
            json.dumps(item, sort_keys=True, separators=(",", ":")) + "\n"
            for item in action_transitions
        ),
    )
    metadata_path = directory / "metadata.json"
    metadata = json.loads(metadata_path.read_text()) if metadata_path.exists() else {}
    metadata.update(
        {
            "capture_schema_version": LIVE_CAPTURE_SCHEMA_VERSION,
            "schema_version": POWERLOG_SCHEMA_VERSION,
            "parser_version": PARSER_VERSION,
            "status": "recovered" if recovered else "finalized",
            "events": len(events),
            "transitions": len(transitions),
            "action_transitions": len(action_transitions),
            "event_stream_sha256": event_stream_sha256(events),
            "privacy": {
                "raw_lines_stored": False,
                "entity_names_stored": False,
                "source_path_stored": False,
            },
        }
    )
    _atomic_text(metadata_path, json.dumps(metadata, indent=2, sort_keys=True) + "\n")
    return metadata


class SanitizedLiveCapture:
    """Capture one physical Power.log without persisting its source path."""

    def __init__(self, output_dir: Path) -> None:
        self.output_dir = output_dir
        self.output_dir.mkdir(parents=True, exist_ok=False)
        self.parser = PowerLogStreamParser()
        self.events: list[TraceEvent] = []
        self.bg_sessions: set[int] = set()
        self.written_sequences: set[int] = set()
        self.pending = b""
        self.source_offset = 0
        self.source_digest = hashlib.sha256()
        self.started_at = datetime.now(timezone.utc).isoformat()
        self._write_metadata(status="capturing")

    @property
    def selected_events(self) -> list[TraceEvent]:
        return [event for event in self.events if event.session_index in self.bg_sessions]

    def _write_metadata(self, *, status: str) -> None:
        selected = self.selected_events
        metadata = {
            "capture_schema_version": LIVE_CAPTURE_SCHEMA_VERSION,
            "schema_version": POWERLOG_SCHEMA_VERSION,
            "parser_version": PARSER_VERSION,
            "status": status,
            "started_at": self.started_at,
            "updated_at": datetime.now(timezone.utc).isoformat(),
            "source_bytes_observed": self.source_offset,
            "source_sha256_observed": self.source_digest.hexdigest(),
            "total_lines": self.parser.total_lines,
            "ignored_lines": self.parser.ignored_lines,
            "ignored_tag_counts": dict(sorted(self.parser.ignored_tag_counts.items())),
            "sessions": self.parser.session_index + 1,
            "battlegrounds_sessions": len(self.bg_sessions),
            "events": len(selected),
            "transitions": None,
            "action_transitions": None,
            "event_stream_sha256": event_stream_sha256(selected),
            "privacy": {
                "raw_lines_stored": False,
                "entity_names_stored": False,
                "source_path_stored": False,
            },
        }
        _atomic_text(
            self.output_dir / "metadata.json",
            json.dumps(metadata, indent=2, sort_keys=True) + "\n",
        )

    def _flush_new_events(self) -> None:
        new_events = [
            event for event in self.selected_events if event.sequence not in self.written_sequences
        ]
        if not new_events:
            return
        with (self.output_dir / "events.jsonl").open("a") as handle:
            for event in new_events:
                handle.write(event_json(event) + "\n")
                self.written_sequences.add(event.sequence)
            handle.flush()
            os.fsync(handle.fileno())

    def ingest_bytes(self, data: bytes) -> int:
        """Consume newly appended raw bytes and persist only sanitized events."""
        if not data:
            return 0
        self.source_digest.update(data)
        self.source_offset += len(data)
        chunks = (self.pending + data).splitlines(keepends=True)
        self.pending = b""
        if chunks and not chunks[-1].endswith((b"\n", b"\r")):
            self.pending = chunks.pop()
        new_events = self.parser.feed(chunk.decode("utf-8", errors="replace") for chunk in chunks)
        self.events.extend(new_events)
        self.bg_sessions.update(battlegrounds_session_ids(new_events))
        self._flush_new_events()
        self._write_metadata(status="capturing")
        return len(new_events)

    def read_available(self, source: Path) -> int:
        size = source.stat().st_size
        if size < self.source_offset:
            raise RuntimeError("source_truncated")
        with source.open("rb") as handle:
            handle.seek(self.source_offset)
            return self.ingest_bytes(handle.read())

    def finalize(self, *, recovered: bool = False) -> dict[str, Any]:
        if self.pending:
            event = self.parser.feed_line(self.pending.decode("utf-8", errors="replace"))
            if event is not None:
                self.events.append(event)
                self.bg_sessions.update(battlegrounds_session_ids([event]))
            self.pending = b""
        self._flush_new_events()
        self._write_metadata(status="capturing")
        return finalize_capture_directory(self.output_dir, recovered=recovered)


def recover_incomplete_captures(output_root: Path) -> list[Path]:
    recovered = []
    if not output_root.exists():
        return recovered
    for metadata_path in sorted(output_root.glob("capture_*/metadata.json")):
        metadata = json.loads(metadata_path.read_text())
        if metadata.get("status") == "capturing":
            finalize_capture_directory(metadata_path.parent, recovered=True)
            recovered.append(metadata_path.parent)
    return recovered
