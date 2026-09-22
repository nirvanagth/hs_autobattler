"""Field-scoped conformance checks for behavior-v7 trace replay results."""

from __future__ import annotations

import copy
from collections import Counter
from typing import Any, Iterable


ITEM_FIELDS = ("internal_card_id", "tier", "attack", "health", "damage")
ZONE_FIELDS = {"board", "hand", "shop"}


def _comparable_state(state: dict[str, Any], fields: list[str]) -> tuple[bool, list[str]]:
    reasons = []
    for field in fields:
        if field in ZONE_FIELDS:
            if any(item.get("internal_card_id") is None for item in state.get(field, [])):
                reasons.append(f"unmapped_trace_{field}_card")
        elif state.get(field) is None:
            reasons.append(f"missing_trace_{field}")
    return not reasons, sorted(set(reasons))


def compare_canonical_states(
    expected: dict[str, Any], actual: dict[str, Any], fields: list[str]
) -> dict[str, Any]:
    """Compare canonical states using only fields declared by the contract."""
    mismatch_categories: Counter[str] = Counter()
    examples = []
    compared_fields = 0
    matching_fields = 0
    for field in fields:
        if field not in ZONE_FIELDS:
            compared_fields += 1
            if expected.get(field) == actual.get(field):
                matching_fields += 1
            else:
                mismatch_categories[field] += 1
                examples.append(
                    {
                        "category": field,
                        "expected": expected.get(field),
                        "actual": actual.get(field),
                    }
                )
            continue

        expected_by_position = {int(item["position"]): item for item in expected.get(field, [])}
        actual_by_position = {int(item["position"]): item for item in actual.get(field, [])}
        for position in sorted(set(expected_by_position) | set(actual_by_position)):
            expected_item = expected_by_position.get(position)
            actual_item = actual_by_position.get(position)
            compared_fields += 1
            if expected_item is None:
                mismatch_categories[f"{field}:extra_item"] += 1
                examples.append(
                    {
                        "category": f"{field}:extra_item",
                        "position": position,
                        "actual": actual_item,
                    }
                )
                continue
            if actual_item is None:
                mismatch_categories[f"{field}:missing_item"] += 1
                examples.append(
                    {
                        "category": f"{field}:missing_item",
                        "position": position,
                        "expected": expected_item,
                    }
                )
                continue
            matching_fields += 1
            for item_field in ITEM_FIELDS:
                expected_value = expected_item.get(item_field)
                if expected_value is None:
                    continue
                compared_fields += 1
                if expected_value == actual_item.get(item_field):
                    matching_fields += 1
                else:
                    mismatch_categories[f"{field}:{item_field}"] += 1
                    examples.append(
                        {
                            "category": f"{field}:{item_field}",
                            "position": position,
                            "expected": expected_value,
                            "actual": actual_item.get(item_field),
                        }
                    )
    return {
        "match": not mismatch_categories,
        "compared_fields": compared_fields,
        "matching_fields": matching_fields,
        "field_agreement_rate": (matching_fields / compared_fields if compared_fields else 1.0),
        "mismatch_categories": dict(sorted(mismatch_categories.items())),
        "examples": examples,
    }


def _upgrade_expected_after(result: dict[str, Any]) -> dict[str, Any]:
    expected = copy.deepcopy(result["trace_after"])
    before = result["trace_before"]
    if before.get("tavern_tier") == 5 and expected.get("tavern_tier") is None:
        expected["tavern_tier"] = 6
        expected["upgrade_cost"] = 0
    return expected


def _is_deferred_upgrade(result: dict[str, Any], fields: list[str]) -> bool:
    if result["action_type"] != "UPGRADE":
        return False
    before = result["trace_before"]
    after = result["trace_after"]
    simulator_before = result["simulator_before"]
    simulator_after = result["simulator_after"]
    return all(before.get(field) == after.get(field) for field in fields) and any(
        simulator_before.get(field) != simulator_after.get(field) for field in fields
    )


def _new_tiers(before: list[dict[str, Any]], after: list[dict[str, Any]]) -> list[int]:
    before_ids = {item.get("entity_id") for item in before if item.get("entity_id") is not None}
    tiers = [
        int(item["tier"])
        for item in after
        if item.get("entity_id") not in before_ids and item.get("tier") is not None
    ]
    return sorted(tiers)


def compare_invariants(result: dict[str, Any]) -> dict[str, Any]:
    """Compare RNG-independent zone deltas and generated-card tiers."""
    mismatches: Counter[str] = Counter()
    examples = []
    compared_fields = 0
    matching_fields = 0
    for zone in ("board", "hand", "shop"):
        expected_delta = len(result["trace_after"].get(zone, [])) - len(
            result["trace_before"].get(zone, [])
        )
        actual_delta = len(result["simulator_after"].get(zone, [])) - len(
            result["simulator_before"].get(zone, [])
        )
        compared_fields += 1
        if expected_delta == actual_delta:
            matching_fields += 1
        else:
            category = f"{zone}:size_delta"
            mismatches[category] += 1
            examples.append(
                {
                    "category": category,
                    "expected": expected_delta,
                    "actual": actual_delta,
                }
            )

        expected_tiers = _new_tiers(
            result["trace_before"].get(zone, []), result["trace_after"].get(zone, [])
        )
        actual_tiers = _new_tiers(
            result["simulator_before"].get(zone, []),
            result["simulator_after"].get(zone, []),
        )
        compared_fields += 1
        if expected_tiers == actual_tiers:
            matching_fields += 1
        else:
            category = f"{zone}:new_tiers"
            mismatches[category] += 1
            examples.append(
                {
                    "category": category,
                    "expected": expected_tiers,
                    "actual": actual_tiers,
                }
            )
    return {
        "match": not mismatches,
        "compared_fields": compared_fields,
        "matching_fields": matching_fields,
        "field_agreement_rate": matching_fields / compared_fields,
        "mismatch_categories": dict(sorted(mismatches.items())),
        "examples": examples,
    }


def compare_replay_results(
    results: Iterable[dict[str, Any]], contract: dict[str, Any]
) -> dict[str, Any]:
    """Aggregate deterministic conformance and RNG-invariant evidence."""
    results = list(results)
    deterministic_counts: Counter[str] = Counter()
    invariant_counts: Counter[str] = Counter()
    exclusion_reasons: Counter[str] = Counter()
    mismatch_categories: Counter[str] = Counter()
    by_action: dict[str, Counter[str]] = {}
    examples = []
    compared_fields = 0
    matching_fields = 0
    precondition_fields = 0
    precondition_matching_fields = 0

    for result in results:
        action_type = result["action_type"]
        action_counts = by_action.setdefault(action_type, Counter())
        action_counts["candidates"] += 1
        if not result.get("accepted"):
            exclusion_reasons["simulator_rejected_action"] += 1
            action_counts["excluded"] += 1
            continue
        if result["comparison_mode"] == "invariant_only":
            invariant_counts["candidates"] += 1
            comparison = compare_invariants(result)
            invariant_counts["passed" if comparison["match"] else "failed"] += 1
            action_counts["invariant_passed" if comparison["match"] else "invariant_failed"] += 1
            if not comparison["match"] and len(examples) < 50:
                examples.append(
                    {
                        "input_index": result.get("input_index"),
                        "transition_index": result["transition_index"],
                        "action_type": action_type,
                        "stage": "invariant",
                        "mismatches": comparison["examples"],
                    }
                )
            continue

        deterministic_counts["candidates"] += 1
        fields = contract["action_policy"][action_type]["comparison_fields"]
        pre_available, pre_reasons = _comparable_state(result["trace_before"], fields)
        if not pre_available:
            exclusion_reasons.update(f"precondition:{reason}" for reason in pre_reasons)
            action_counts["excluded"] += 1
            continue
        precondition = compare_canonical_states(
            result["trace_before"], result["simulator_before"], fields
        )
        precondition_fields += precondition["compared_fields"]
        precondition_matching_fields += precondition["matching_fields"]
        if not precondition["match"]:
            exclusion_reasons["precondition_mismatch"] += 1
            action_counts["excluded"] += 1
            if len(examples) < 50:
                examples.append(
                    {
                        "input_index": result.get("input_index"),
                        "transition_index": result["transition_index"],
                        "action_type": action_type,
                        "stage": "precondition",
                        "mismatches": precondition["examples"][:20],
                    }
                )
            continue
        if _is_deferred_upgrade(result, fields):
            exclusion_reasons["trace_post_state_deferred"] += 1
            action_counts["excluded"] += 1
            continue

        expected_after = (
            _upgrade_expected_after(result) if action_type == "UPGRADE" else result["trace_after"]
        )
        post_available, post_reasons = _comparable_state(expected_after, fields)
        if not post_available:
            exclusion_reasons.update(f"postcondition:{reason}" for reason in post_reasons)
            action_counts["excluded"] += 1
            continue
        comparison = compare_canonical_states(expected_after, result["simulator_after"], fields)
        deterministic_counts["evaluable"] += 1
        action_counts["evaluable"] += 1
        compared_fields += comparison["compared_fields"]
        matching_fields += comparison["matching_fields"]
        if comparison["match"]:
            deterministic_counts["exact"] += 1
            action_counts["exact"] += 1
        else:
            deterministic_counts["mismatched"] += 1
            action_counts["mismatched"] += 1
            mismatch_categories.update(comparison["mismatch_categories"])
            if len(examples) < 50:
                examples.append(
                    {
                        "input_index": result.get("input_index"),
                        "transition_index": result["transition_index"],
                        "action_type": action_type,
                        "stage": "postcondition",
                        "mismatches": comparison["examples"][:20],
                    }
                )

    evaluable = deterministic_counts["evaluable"]
    invariant_candidates = invariant_counts["candidates"]
    return {
        "replay_results": len(results),
        "deterministic": {
            "candidates": deterministic_counts["candidates"],
            "evaluable": evaluable,
            "excluded": deterministic_counts["candidates"] - evaluable,
            "exact": deterministic_counts["exact"],
            "mismatched": deterministic_counts["mismatched"],
            "exact_transition_rate": (
                deterministic_counts["exact"] / evaluable if evaluable else 1.0
            ),
            "compared_fields": compared_fields,
            "matching_fields": matching_fields,
            "field_agreement_rate": (matching_fields / compared_fields if compared_fields else 1.0),
        },
        "preconditions": {
            "compared_fields": precondition_fields,
            "matching_fields": precondition_matching_fields,
            "field_agreement_rate": (
                precondition_matching_fields / precondition_fields if precondition_fields else 1.0
            ),
        },
        "invariants": {
            "candidates": invariant_candidates,
            "passed": invariant_counts["passed"],
            "failed": invariant_counts["failed"],
            "pass_rate": (
                invariant_counts["passed"] / invariant_candidates if invariant_candidates else 1.0
            ),
        },
        "exclusion_reason_counts": dict(sorted(exclusion_reasons.items())),
        "mismatch_categories": dict(sorted(mismatch_categories.items())),
        "by_action": {
            action: dict(sorted(counts.items())) for action, counts in sorted(by_action.items())
        },
        "examples": examples,
    }
