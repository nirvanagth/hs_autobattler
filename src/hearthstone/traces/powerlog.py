"""Privacy-safe Hearthstone Power.log parser and state reconstructor."""

from __future__ import annotations

import hashlib
import json
import re
from collections import Counter
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Iterable, Iterator


POWERLOG_SCHEMA_VERSION = 1
PARSER_VERSION = 1

ALLOWED_TAGS = {
    "ARMOR",
    "ATK",
    "BACON_HERO_CAN_BE_DRAFTED",
    "BACON_HERO_POWER_ACTIVATED",
    "CARDTYPE",
    "CONTROLLER",
    "COST",
    "DAMAGE",
    "HEALTH",
    "NUM_TURNS_IN_PLAY",
    "PLAYER_ID",
    "TECH_LEVEL",
    "TURN",
    "ZONE",
    "ZONE_POSITION",
}
DETERMINISTIC_TAGS = {
    "ARMOR",
    "ATK",
    "CONTROLLER",
    "COST",
    "DAMAGE",
    "HEALTH",
    "PLAYER_ID",
    "TECH_LEVEL",
    "TURN",
    "ZONE",
    "ZONE_POSITION",
}

_SAFE_TOKEN = re.compile(r"^[A-Za-z0-9_+\-]+$")
_ENTITY_ID_PATTERNS = (
    re.compile(r"\bid=(\d+)\b", re.IGNORECASE),
    re.compile(r"\bID=(\d+)\b"),
    re.compile(r"\bEntityID=(\d+)\b", re.IGNORECASE),
    re.compile(r"^\s*(\d+)\s*$"),
)


@dataclass(frozen=True)
class TraceEvent:
    sequence: int
    event_type: str
    entity_id: int | None = None
    card_id: str | None = None
    tag: str | None = None
    value: str | int | None = None
    block_type: str | None = None
    block_depth: int = 0


@dataclass
class ParseResult:
    events: list[TraceEvent] = field(default_factory=list)
    total_lines: int = 0
    ignored_lines: int = 0
    ignored_tag_counts: Counter[str] = field(default_factory=Counter)


def _payload(line: str) -> str:
    return line.split(" - ", 1)[1].strip() if " - " in line else line.strip()


def _entity_id(text: str) -> int | None:
    for pattern in _ENTITY_ID_PATTERNS:
        match = pattern.search(text)
        if match:
            return int(match.group(1))
    return None


def _safe_card_id(value: str) -> str | None:
    value = value.strip()
    return value if value and _SAFE_TOKEN.fullmatch(value) else None


def _safe_value(value: str) -> str | int | None:
    value = value.strip()
    if re.fullmatch(r"-?\d+", value):
        return int(value)
    return value if _SAFE_TOKEN.fullmatch(value) else None


def parse_power_log(lines: Iterable[str]) -> ParseResult:
    result = ParseResult()
    current_entity: int | None = None
    block_stack: list[str] = []
    for line in lines:
        result.total_lines += 1
        text = _payload(line)
        event: TraceEvent | None = None
        if "CREATE_GAME" in text:
            event = TraceEvent(len(result.events), "create_game", block_depth=len(block_stack))
        elif "FULL_ENTITY" in text or "SHOW_ENTITY" in text or "CHANGE_ENTITY" in text:
            event_name = (
                "full_entity"
                if "FULL_ENTITY" in text
                else "show_entity"
                if "SHOW_ENTITY" in text
                else "change_entity"
            )
            entity_id = _entity_id(text)
            card_match = re.search(r"\bCardID=([^\s\]]*)", text, re.IGNORECASE)
            card_id = _safe_card_id(card_match.group(1)) if card_match else None
            current_entity = entity_id
            event = TraceEvent(
                len(result.events),
                event_name,
                entity_id=entity_id,
                card_id=card_id,
                block_depth=len(block_stack),
            )
        elif "TAG_CHANGE" in text:
            tag_match = re.search(r"\btag=([A-Z0-9_]+)\s+value=(.+)$", text)
            entity_text = text.split("tag=", 1)[0].split("Entity=", 1)[-1]
            if tag_match:
                tag = tag_match.group(1)
                if tag in ALLOWED_TAGS:
                    event = TraceEvent(
                        len(result.events),
                        "tag_change",
                        entity_id=_entity_id(entity_text),
                        tag=tag,
                        value=_safe_value(tag_match.group(2)),
                        block_depth=len(block_stack),
                    )
                else:
                    result.ignored_tag_counts[tag] += 1
        elif text.startswith("tag=") and current_entity is not None:
            tag_match = re.match(r"tag=([A-Z0-9_]+)\s+value=(.+)$", text)
            if tag_match:
                tag = tag_match.group(1)
                if tag in ALLOWED_TAGS:
                    event = TraceEvent(
                        len(result.events),
                        "entity_tag",
                        entity_id=current_entity,
                        tag=tag,
                        value=_safe_value(tag_match.group(2)),
                        block_depth=len(block_stack),
                    )
                else:
                    result.ignored_tag_counts[tag] += 1
        elif "BLOCK_START" in text:
            block_match = re.search(r"\bBlockType=([A-Z_]+)", text)
            block_type = block_match.group(1) if block_match else "UNKNOWN"
            event = TraceEvent(
                len(result.events),
                "block_start",
                entity_id=_entity_id(text.split("Entity=", 1)[-1]),
                block_type=block_type,
                block_depth=len(block_stack),
            )
            block_stack.append(block_type)
        elif "BLOCK_END" in text:
            block_type = block_stack.pop() if block_stack else "UNKNOWN"
            event = TraceEvent(
                len(result.events),
                "block_end",
                block_type=block_type,
                block_depth=len(block_stack),
            )
        if event is not None:
            result.events.append(event)
        else:
            result.ignored_lines += 1
    return result


def event_json(event: TraceEvent) -> str:
    return json.dumps(asdict(event), sort_keys=True, separators=(",", ":"))


def event_stream_sha256(events: Iterable[TraceEvent]) -> str:
    digest = hashlib.sha256()
    for event in events:
        digest.update(event_json(event).encode())
        digest.update(b"\n")
    return digest.hexdigest()


class TraceState:
    def __init__(self) -> None:
        self.entities: dict[int, dict] = {}

    def apply(self, event: TraceEvent) -> None:
        if event.entity_id is None:
            return
        entity = self.entities.setdefault(
            event.entity_id, {"entity_id": event.entity_id, "card_id": None, "tags": {}}
        )
        if event.card_id is not None:
            entity["card_id"] = event.card_id
        if event.tag is not None and event.value is not None:
            entity["tags"][event.tag] = event.value

    def snapshot(self) -> dict:
        return {
            "entities": [
                {
                    "entity_id": entity_id,
                    "card_id": entity["card_id"],
                    "tags": {
                        key: value
                        for key, value in sorted(entity["tags"].items())
                        if key in DETERMINISTIC_TAGS
                    },
                }
                for entity_id, entity in sorted(self.entities.items())
            ]
        }


def reconstruct_transitions(events: Iterable[TraceEvent]) -> list[dict]:
    state = TraceState()
    root_frame: dict | None = None
    transitions = []
    for event in events:
        if event.event_type == "block_start" and event.block_depth == 0:
            root_frame = {
                "block_type": event.block_type,
                "source_entity_id": event.entity_id,
                "before": state.snapshot(),
            }
        state.apply(event)
        if event.event_type == "block_end" and event.block_depth == 0 and root_frame:
            transitions.append(
                {
                    "transition_index": len(transitions),
                    **root_frame,
                    "after": state.snapshot(),
                }
            )
            root_frame = None
    return transitions


def load_power_log(path: Path) -> ParseResult:
    with path.open(errors="replace") as handle:
        return parse_power_log(handle)
