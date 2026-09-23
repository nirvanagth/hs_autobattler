"""Privacy-safe Hearthstone Power.log parser and state reconstructor."""

from __future__ import annotations

import hashlib
import json
import re
from collections import Counter
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Iterable


POWERLOG_SCHEMA_VERSION = 3
PARSER_VERSION = 3
ACTION_CLASSIFIER_VERSION = 3

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

BG_ACTION_CARD_IDS = {
    "TB_BaconShop_DragBuy": "BUY",
    "TB_BaconShop_DragBuy_Spell": "BUY",
    "TB_BaconShop_DragSell": "SELL",
    "TB_BaconShop_8p_Reroll_Button": "ROLL",
    "TB_BaconShopLockAll_Button": "FREEZE",
    "TB_BaconShop_8p_Upgrade_Button": "UPGRADE",
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
    session_index: int
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
    marker = "DebugPrintPower() - "
    return line.split(marker, 1)[1].strip() if marker in line else line.strip()


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


class PowerLogStreamParser:
    """Stateful line parser used by both batch imports and live capture."""

    def __init__(self) -> None:
        self.current_entity: int | None = None
        self.block_stack: list[str] = []
        self.session_index = -1
        self.sequence = 0
        self.total_lines = 0
        self.ignored_lines = 0
        self.ignored_tag_counts: Counter[str] = Counter()

    def feed_line(self, line: str) -> TraceEvent | None:
        self.total_lines += 1
        text = _payload(line)
        event: TraceEvent | None = None
        if "CREATE_GAME" in text:
            self.session_index += 1
            self.block_stack.clear()
            self.current_entity = None
            event = TraceEvent(self.sequence, self.session_index, "create_game", block_depth=0)
        elif "FULL_ENTITY" in text or "SHOW_ENTITY" in text or "CHANGE_ENTITY" in text:
            event_name = (
                "full_entity"
                if "FULL_ENTITY" in text
                else "show_entity" if "SHOW_ENTITY" in text else "change_entity"
            )
            entity_id = _entity_id(text)
            card_match = re.search(r"\bCardID=([^\s\]]*)", text, re.IGNORECASE)
            card_id = _safe_card_id(card_match.group(1)) if card_match else None
            self.current_entity = entity_id
            event = TraceEvent(
                self.sequence,
                self.session_index,
                event_name,
                entity_id=entity_id,
                card_id=card_id,
                block_depth=len(self.block_stack),
            )
        elif "TAG_CHANGE" in text:
            tag_match = re.search(r"\btag=([A-Z0-9_]+)\s+value=(.+)$", text)
            entity_text = text.split("tag=", 1)[0].split("Entity=", 1)[-1]
            if tag_match:
                tag = tag_match.group(1)
                if tag in ALLOWED_TAGS:
                    event = TraceEvent(
                        self.sequence,
                        self.session_index,
                        "tag_change",
                        entity_id=_entity_id(entity_text),
                        tag=tag,
                        value=_safe_value(tag_match.group(2)),
                        block_depth=len(self.block_stack),
                    )
                else:
                    self.ignored_tag_counts[tag] += 1
        elif text.startswith("tag=") and self.current_entity is not None:
            tag_match = re.match(r"tag=([A-Z0-9_]+)\s+value=(.+)$", text)
            if tag_match:
                tag = tag_match.group(1)
                if tag in ALLOWED_TAGS:
                    event = TraceEvent(
                        self.sequence,
                        self.session_index,
                        "entity_tag",
                        entity_id=self.current_entity,
                        tag=tag,
                        value=_safe_value(tag_match.group(2)),
                        block_depth=len(self.block_stack),
                    )
                else:
                    self.ignored_tag_counts[tag] += 1
        elif "BLOCK_START" in text:
            block_match = re.search(r"\bBlockType=([A-Z_]+)", text)
            block_type = block_match.group(1) if block_match else "UNKNOWN"
            card_match = re.search(r"\bcardId=([^\s\]]*)", text, re.IGNORECASE)
            event = TraceEvent(
                self.sequence,
                self.session_index,
                "block_start",
                entity_id=_entity_id(text.split("Entity=", 1)[-1]),
                card_id=_safe_card_id(card_match.group(1)) if card_match else None,
                block_type=block_type,
                block_depth=len(self.block_stack),
            )
            self.block_stack.append(block_type)
        elif "BLOCK_END" in text:
            block_type = self.block_stack.pop() if self.block_stack else "UNKNOWN"
            event = TraceEvent(
                self.sequence,
                self.session_index,
                "block_end",
                block_type=block_type,
                block_depth=len(self.block_stack),
            )
        if event is not None:
            self.sequence += 1
            return event
        self.ignored_lines += 1
        return None

    def feed(self, lines: Iterable[str]) -> list[TraceEvent]:
        return [event for line in lines if (event := self.feed_line(line)) is not None]


def parse_power_log(lines: Iterable[str]) -> ParseResult:
    parser = PowerLogStreamParser()
    events = parser.feed(lines)
    return ParseResult(
        events=events,
        total_lines=parser.total_lines,
        ignored_lines=parser.ignored_lines,
        ignored_tag_counts=parser.ignored_tag_counts,
    )


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
    session_index = -1
    for event in events:
        if event.event_type == "create_game":
            state = TraceState()
            root_frame = None
            session_index = event.session_index
            continue
        if event.event_type == "block_start" and event.block_depth == 0:
            source_card_id = event.card_id
            if source_card_id is None and event.entity_id in state.entities:
                source_card_id = state.entities[event.entity_id]["card_id"]
            root_frame = {
                "block_type": event.block_type,
                "source_entity_id": event.entity_id,
                "source_card_id": source_card_id,
                "action_type": classify_battlegrounds_action(source_card_id, event.block_type),
                "session_index": session_index,
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


def battlegrounds_session_ids(events: Iterable[TraceEvent]) -> set[int]:
    prefixes = ("BG", "BGS_", "TB_Bacon")
    return {
        event.session_index
        for event in events
        if event.card_id is not None and event.card_id.startswith(prefixes)
    }


def classify_battlegrounds_action(card_id: str | None, block_type: str | None = None) -> str | None:
    # User recruit actions enter Power.log as PLAY blocks. The same source card
    # can appear in nested POWER/TRIGGER/ATTACK blocks; counting those produces
    # multiple false actions per click. In particular, TB_BaconUps_* identifies
    # golden minions and must never be treated as a tavern upgrade button.
    if card_id is None or block_type != "PLAY":
        return None
    if card_id in BG_ACTION_CARD_IDS:
        return BG_ACTION_CARD_IDS[card_id]
    upper = card_id.upper()
    if re.fullmatch(r"TB_BaconShopTechUp(?:\d+)?_Button", card_id, re.IGNORECASE):
        return "UPGRADE"
    if "HERO_" in upper or "_HP_" in upper:
        return "HERO_POWER"
    if "BUTTON" in upper:
        return "SPECIAL_ACTION"
    return "PLAY_CARD"


def reconstruct_action_transitions(events: Iterable[TraceEvent]) -> list[dict]:
    state = TraceState()
    frames: list[dict] = []
    transitions = []
    for event in events:
        if event.event_type == "create_game":
            state = TraceState()
            frames.clear()
            continue
        if event.event_type == "block_start":
            source_card_id = event.card_id
            if source_card_id is None and event.entity_id in state.entities:
                source_card_id = state.entities[event.entity_id]["card_id"]
            action_type = classify_battlegrounds_action(source_card_id, event.block_type)
            if action_type is not None:
                frames.append(
                    {
                        "depth": event.block_depth,
                        "block_type": event.block_type,
                        "source_entity_id": event.entity_id,
                        "source_card_id": source_card_id,
                        "action_type": action_type,
                        "session_index": event.session_index,
                        "before": state.snapshot(),
                    }
                )
        state.apply(event)
        if event.event_type == "block_end":
            matching_index = next(
                (
                    index
                    for index in range(len(frames) - 1, -1, -1)
                    if frames[index]["depth"] == event.block_depth
                    and frames[index]["block_type"] == event.block_type
                ),
                None,
            )
            if matching_index is not None:
                frame = frames.pop(matching_index)
                transitions.append(
                    {
                        "transition_index": len(transitions),
                        **{key: value for key, value in frame.items() if key != "depth"},
                        "after": state.snapshot(),
                    }
                )
    return transitions


def load_power_log(path: Path) -> ParseResult:
    with path.open(errors="replace") as handle:
        return parse_power_log(handle)
