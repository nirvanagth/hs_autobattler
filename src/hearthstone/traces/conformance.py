"""Deterministic normalized-state conformance comparison."""

from __future__ import annotations

from collections import Counter


def _slot_key(entity: dict) -> tuple:
    tags = entity.get("tags", {})
    return (
        tags.get("CONTROLLER"),
        tags.get("ZONE"),
        tags.get("ZONE_POSITION"),
    )


def compare_states(expected: dict, actual: dict) -> dict:
    expected_slots = {_slot_key(entity): entity for entity in expected.get("entities", [])}
    actual_slots = {_slot_key(entity): entity for entity in actual.get("entities", [])}
    mismatches = []
    for slot in sorted(set(expected_slots) | set(actual_slots), key=str):
        expected_entity = expected_slots.get(slot)
        actual_entity = actual_slots.get(slot)
        if expected_entity is None:
            mismatches.append({"category": "extra_entity", "slot": slot})
            continue
        if actual_entity is None:
            mismatches.append({"category": "missing_entity", "slot": slot})
            continue
        if expected_entity.get("card_id") != actual_entity.get("card_id"):
            mismatches.append(
                {
                    "category": "card_id",
                    "slot": slot,
                    "expected": expected_entity.get("card_id"),
                    "actual": actual_entity.get("card_id"),
                }
            )
        expected_tags = expected_entity.get("tags", {})
        actual_tags = actual_entity.get("tags", {})
        for tag in sorted(set(expected_tags) | set(actual_tags)):
            if expected_tags.get(tag) != actual_tags.get(tag):
                mismatches.append(
                    {
                        "category": f"tag:{tag}",
                        "slot": slot,
                        "expected": expected_tags.get(tag),
                        "actual": actual_tags.get(tag),
                    }
                )
    counts = Counter(item["category"] for item in mismatches)
    compared_fields = sum(
        1 + len(entity.get("tags", {})) for entity in expected.get("entities", [])
    )
    return {
        "match": not mismatches,
        "compared_fields": compared_fields,
        "mismatch_count": len(mismatches),
        "mismatch_categories": dict(sorted(counts.items())),
        "mismatches": mismatches,
    }


def compare_transition_streams(expected: list[dict], actual: list[dict]) -> dict:
    actual_by_index = {item["transition_index"]: item for item in actual}
    category_counts: Counter[str] = Counter()
    examples = []
    exact = 0
    compared_fields = 0
    for expected_transition in expected:
        index = expected_transition["transition_index"]
        actual_transition = actual_by_index.get(index)
        if actual_transition is None:
            category_counts["missing_transition"] += 1
            continue
        comparison = compare_states(
            expected_transition["after"], actual_transition["after"]
        )
        compared_fields += comparison["compared_fields"]
        if comparison["match"]:
            exact += 1
        else:
            category_counts.update(comparison["mismatch_categories"])
            if len(examples) < 100:
                examples.append(
                    {
                        "transition_index": index,
                        "block_type": expected_transition.get("block_type"),
                        "mismatches": comparison["mismatches"][:20],
                    }
                )
    extra = len(set(actual_by_index) - {item["transition_index"] for item in expected})
    if extra:
        category_counts["extra_transition"] += extra
    mismatches = sum(category_counts.values())
    return {
        "expected_transitions": len(expected),
        "actual_transitions": len(actual),
        "exact_transitions": exact,
        "exact_transition_rate": exact / len(expected) if expected else 1.0,
        "compared_fields": compared_fields,
        "mismatch_count": mismatches,
        "field_agreement_rate": (
            max(0.0, 1.0 - mismatches / compared_fields)
            if compared_fields
            else 1.0
        ),
        "mismatch_categories": dict(sorted(category_counts.items())),
        "examples": examples,
    }
