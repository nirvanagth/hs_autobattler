"""Deterministic executable-content coverage audit."""

from __future__ import annotations

import inspect
import ast
import json
import re
from collections import Counter, defaultdict
from dataclasses import fields, is_dataclass
from enum import Enum
from pathlib import Path
from typing import Any

from . import card_def
from .card_def import ALL_CARDS, AVENGE_REGISTRY, TRIGGER_REGISTRY
from .configs import CARD_DB, ROTATED_OUT, SPELL_DB
from .enums import CardIDs, SpellIDs, Tags
from .spells import EFFECT_FACTORIES, SPELLS_REQUIRE_TARGET, SPELL_TRIGGER_REGISTRY


CONTENT_AUDIT_SCHEMA_VERSION = 1
VERIFICATION_INDEX_SCHEMA_VERSION = 1

# Properties alone do not implement Stealth targeting semantics in combat.
SUPPORTED_GENERIC_TAGS = {
    Tags.IMMEDIATE_ATTACK,
    Tags.TAUNT,
    Tags.DIVINE_SHIELD,
    Tags.WINDFURY,
    Tags.POISONOUS,
    Tags.REBORN,
    Tags.VENOMOUS,
    Tags.CLEAVE,
    Tags.MAGNETIC,
    Tags.IMMUNE,
}

# Legacy TavernManager emits MINION_PLAYED but not MINION_SUMMONED when a unit
# is played from hand. These handlers work for generated summons but do not yet
# implement the full live-game meaning of "summon".
INCOMPLETE_PLAY_AS_SUMMON_EFFECTS = {
    "OnFriendlySummonedTypeBuff",
    "OnSummonedTypeBuffRandomOther",
    "OtherSummonScalingAura",
    "OnSummonAutomatonBuffAutomatons",
}


def _value(value: Any) -> Any:
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, set):
        return sorted(_value(item) for item in value)
    if isinstance(value, (list, tuple)):
        return [_value(item) for item in value]
    return value


def _symbols(enum_type: type[Enum]) -> dict[str, str]:
    return {str(member.value): name for name, member in enum_type.__members__.items()}


def scan_test_references(test_root: Path) -> dict[tuple[str, str], list[str]]:
    references: dict[tuple[str, str], set[str]] = defaultdict(set)
    for path in sorted(test_root.glob("test_*.py")):
        source = path.read_text()
        relative = path.relative_to(test_root.parent).as_posix()
        for symbol in re.findall(r"CardIDs\.([A-Z][A-Z0-9_]*)", source):
            references[("card", symbol)].add(relative)
        for symbol in re.findall(r"SpellIDs\.([A-Z][A-Z0-9_]*)", source):
            references[("spell", symbol)].add(relative)
    return {key: sorted(paths) for key, paths in references.items()}


def _collected_test_nodes(path: Path, relative: str) -> set[str]:
    tree = ast.parse(path.read_text(), filename=str(path))
    nodes = set()
    for item in tree.body:
        if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)) and item.name.startswith(
            "test_"
        ):
            nodes.add(f"{relative}::{item.name}")
        if isinstance(item, ast.ClassDef):
            for child in item.body:
                if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)) and child.name.startswith(
                    "test_"
                ):
                    nodes.add(f"{relative}::{item.name}::{child.name}")
    return nodes


def load_verification_index(
    path: Path, *, test_root: Path
) -> dict[tuple[str, str], list[str]]:
    payload = json.loads(path.read_text())
    if payload.get("schema_version") != VERIFICATION_INDEX_SCHEMA_VERSION:
        raise ValueError("unsupported content verification index schema")
    known_ids = {"card": set(CARD_DB), "spell": set(SPELL_DB)}
    available_nodes = set()
    for test_path in sorted(test_root.glob("test_*.py")):
        relative = test_path.relative_to(test_root.parent).as_posix()
        available_nodes.update(_collected_test_nodes(test_path, relative))
    result = {}
    for plural, kind in (("cards", "card"), ("spells", "spell")):
        for content_id, nodes in payload.get(plural, {}).items():
            if content_id not in known_ids[kind]:
                raise ValueError(f"unknown verified {kind}: {content_id}")
            if not nodes:
                raise ValueError(f"verified {kind} has no scenario tests: {content_id}")
            missing = sorted(set(nodes) - available_nodes)
            if missing:
                raise ValueError(f"missing scenario test nodes for {content_id}: {missing}")
            result[(kind, content_id)] = sorted(set(nodes))
    return result


def _recognized_effect_classes() -> set[str]:
    source = inspect.getsource(card_def.build_trigger_registry)
    return set(re.findall(r"isinstance\(eff, ([A-Za-z][A-Za-z0-9_]*)\)", source))


def _generated_dependencies(effect: object) -> list[dict[str, str]]:
    if not is_dataclass(effect):
        return []
    dependencies = []
    for field_info in fields(effect):
        if field_info.name not in {"card_id", "token_id", "spell_id"}:
            continue
        raw_value = getattr(effect, field_info.name)
        if not raw_value:
            continue
        value = str(_value(raw_value))
        kind = "spell" if field_info.name == "spell_id" else "card"
        dependencies.append({"field": field_info.name, "kind": kind, "id": value})
    return dependencies


def _test_files(
    references: dict[tuple[str, str], list[str]], kind: str, symbol: str | None
) -> list[str]:
    return references.get((kind, symbol), []) if symbol is not None else []


def build_content_manifest(
    *,
    test_root: Path | None = None,
    verified_scenarios: dict[tuple[str, str], list[str]] | None = None,
    behavior_version: int = 5,
) -> dict[str, Any]:
    references = scan_test_references(test_root) if test_root is not None else {}
    verified_scenarios = verified_scenarios or {}
    card_symbols = _symbols(CardIDs)
    spell_symbols = _symbols(SpellIDs)
    recognized_effects = _recognized_effect_classes()
    card_entries = []

    if len({str(_value(card.card_id)) for card in ALL_CARDS}) != len(ALL_CARDS):
        raise ValueError("duplicate card ids in ALL_CARDS")

    for card in sorted(ALL_CARDS, key=lambda item: str(_value(item.card_id))):
        card_id = str(_value(card.card_id))
        symbol = card_symbols.get(card_id)
        issues = []
        supported_effects = []
        unsupported_effects = []
        dependencies = []
        for effect in card.effects:
            effect_name = type(effect).__name__
            runtime_class = getattr(card_def, effect_name, None)
            supported = (
                effect_name in recognized_effects
                and runtime_class is not None
                and type(effect) is runtime_class
            )
            (supported_effects if supported else unsupported_effects).append(effect_name)
            dependencies.extend(_generated_dependencies(effect))
            if (
                effect_name == "BattlecryModifyMechanic"
                and getattr(effect, "atk", 0) == 0
                and getattr(effect, "hp", 0) == 0
            ):
                issues.append("declared_no_op_effect:BattlecryModifyMechanic")
            if (
                behavior_version < 6
                and effect_name in INCOMPLETE_PLAY_AS_SUMMON_EFFECTS
            ):
                issues.append("missing_minion_summoned_event_on_play")
        for dependency in dependencies:
            target = SPELL_DB if dependency["kind"] == "spell" else CARD_DB
            if dependency["id"] not in target:
                issues.append(
                    f"missing_{dependency['kind']}_dependency:{dependency['id']}"
                )
        unsupported_tags = sorted(
            tag.name for tag in card.tags if tag not in SUPPORTED_GENERIC_TAGS
        )
        if unsupported_tags:
            issues.append("unsupported_tags:" + ",".join(unsupported_tags))
        if unsupported_effects:
            issues.append("unsupported_effects:" + ",".join(unsupported_effects))
        trigger_defs = list(TRIGGER_REGISTRY.get(card.card_id, []))
        trigger_events = sorted({trigger.event_type.name for trigger in trigger_defs})
        if card.deathrattle and "MINION_DIED" not in trigger_events:
            issues.append("deathrattle_metadata_without_trigger")
        scenario_tests = verified_scenarios.get(("card", card_id), [])
        if issues:
            classification = "partial" if supported_effects else "unsupported"
        elif scenario_tests:
            classification = "verified"
        else:
            classification = "implemented_unverified"
        card_entries.append(
            {
                "kind": "card",
                "id": card_id,
                "symbol": symbol,
                "name": card.name,
                "tier": card.tier,
                "tribes": sorted(unit_type.value for unit_type in card.types),
                "tags": sorted(tag.name for tag in card.tags),
                "is_token": card.is_token,
                "rotated_out": card.card_id in ROTATED_OUT,
                "shop_eligible_tier3": (
                    not card.is_token
                    and card.card_id not in ROTATED_OUT
                    and card.tier <= 3
                ),
                "effect_types": [type(effect).__name__ for effect in card.effects],
                "supported_effect_types": supported_effects,
                "unsupported_effect_types": unsupported_effects,
                "trigger_events": trigger_events,
                "trigger_count": len(trigger_defs),
                "avenge_registered": card.card_id in AVENGE_REGISTRY,
                "has_multiplier": card.multiplier is not None,
                "generated_dependencies": dependencies,
                "test_reference_files": _test_files(references, "card", symbol),
                "verified_scenarios": scenario_tests,
                "classification": classification,
                "handler_complete": not issues,
                "issues": issues,
            }
        )

    spell_entries = []
    for spell_id_raw, data in sorted(SPELL_DB.items(), key=lambda item: str(_value(item[0]))):
        spell_id = str(_value(spell_id_raw))
        symbol = spell_symbols.get(spell_id)
        effect_code = str(data.get("effect", ""))
        issues = []
        if effect_code not in EFFECT_FACTORIES:
            issues.append(f"unsupported_spell_effect:{effect_code}")
        if spell_id_raw not in SPELL_TRIGGER_REGISTRY:
            issues.append("missing_spell_trigger")
        scenario_tests = verified_scenarios.get(("spell", spell_id), [])
        if issues:
            classification = "unsupported"
        elif scenario_tests:
            classification = "verified"
        else:
            classification = "implemented_unverified"
        spell_entries.append(
            {
                "kind": "spell",
                "id": spell_id,
                "symbol": symbol,
                "name": data["name"],
                "tier": int(data["tier"]),
                "cost": int(data["cost"]),
                "effect": effect_code,
                "requires_target": spell_id_raw in SPELLS_REQUIRE_TARGET,
                "is_temporary": bool(data.get("is_temporary", False)),
                "in_pool": bool(data.get("pool", True)),
                "test_reference_files": _test_files(references, "spell", symbol),
                "verified_scenarios": scenario_tests,
                "classification": classification,
                "handler_complete": not issues,
                "issues": issues,
            }
        )

    entries = card_entries + spell_entries
    classifications = Counter(entry["classification"] for entry in entries)
    active_cards = [entry for entry in card_entries if entry["shop_eligible_tier3"]]
    summary = {
        "cards": len(card_entries),
        "spells": len(spell_entries),
        "classifications": dict(sorted(classifications.items())),
        "handler_complete": sum(entry["handler_complete"] for entry in entries),
        "handler_incomplete": sum(not entry["handler_complete"] for entry in entries),
        "tier3_shop_cards": len(active_cards),
        "tier3_shop_handler_incomplete": sum(
            not entry["handler_complete"] for entry in active_cards
        ),
        "cards_with_test_references": sum(
            bool(entry["test_reference_files"]) for entry in card_entries
        ),
        "spells_with_test_references": sum(
            bool(entry["test_reference_files"]) for entry in spell_entries
        ),
    }
    return {
        "schema_version": CONTENT_AUDIT_SCHEMA_VERSION,
        "behavior_version": behavior_version,
        "summary": summary,
        "cards": card_entries,
        "spells": spell_entries,
    }


def content_manifest_json(manifest: dict[str, Any]) -> str:
    return json.dumps(manifest, indent=2, sort_keys=True) + "\n"


def validate_content_admission(
    manifest: dict[str, Any],
    *,
    card_ids: list[str],
    spell_ids: list[str],
    require_verified: bool = True,
) -> dict[str, int]:
    entries = {
        (entry["kind"], entry["id"]): entry
        for entry in manifest["cards"] + manifest["spells"]
    }
    failures = []
    accepted = 0
    for kind, content_ids in (("card", card_ids), ("spell", spell_ids)):
        for content_id in content_ids:
            entry = entries.get((kind, content_id))
            if entry is None:
                failures.append(f"unknown_{kind}:{content_id}")
                continue
            if not entry["handler_complete"]:
                failures.append(
                    f"incomplete_{kind}:{content_id}:{','.join(entry['issues'])}"
                )
                continue
            if require_verified and entry["classification"] != "verified":
                failures.append(f"unverified_{kind}:{content_id}")
                continue
            accepted += 1
    if failures:
        raise ValueError("content admission failed: " + "; ".join(failures))
    return {"accepted": accepted, "cards": len(card_ids), "spells": len(spell_ids)}


def build_content_profile(
    manifest: dict[str, Any], *, max_tier: int
) -> dict[str, Any]:
    cards = [
        entry
        for entry in manifest["cards"]
        if not entry["is_token"]
        and not entry["rotated_out"]
        and entry["tier"] <= min(7, max_tier + 1)
    ]
    spells = [
        entry
        for entry in manifest["spells"]
        if entry["in_pool"] and entry["tier"] <= max_tier
    ]
    shop_cards = [
        entry["id"]
        for entry in cards
        if entry["tier"] <= max_tier and entry["classification"] == "verified"
    ]
    discovery_cards = [
        entry["id"]
        for entry in cards
        if entry["tier"] == max_tier + 1
        and entry["classification"] == "verified"
    ]
    included_cards = shop_cards + discovery_cards
    included_spells = [
        entry["id"] for entry in spells if entry["classification"] == "verified"
    ]
    validate_content_admission(
        manifest,
        card_ids=included_cards,
        spell_ids=included_spells,
    )
    return {
        "schema_version": 1,
        "behavior_version": manifest["behavior_version"],
        "max_tier": max_tier,
        "shop_card_ids": shop_cards,
        "next_tier_discovery_card_ids": discovery_cards,
        "included_card_ids": included_cards,
        "included_spell_ids": included_spells,
        "excluded_cards": [
            {
                "id": entry["id"],
                "symbol": entry["symbol"],
                "classification": entry["classification"],
                "issues": entry["issues"],
            }
            for entry in cards
            if entry["classification"] != "verified"
        ],
        "excluded_spells": [
            {
                "id": entry["id"],
                "symbol": entry["symbol"],
                "classification": entry["classification"],
                "issues": entry["issues"],
            }
            for entry in spells
            if entry["classification"] != "verified"
        ],
    }
