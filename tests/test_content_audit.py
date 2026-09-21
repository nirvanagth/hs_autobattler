"""Executable content-manifest audit tests."""

from pathlib import Path

import pytest

from hearthstone.engine.content_audit import (
    build_content_manifest,
    build_content_profile,
    content_manifest_json,
    load_verification_index,
    validate_content_admission,
)


ROOT = Path(__file__).resolve().parent.parent


def audited_manifest(behavior_version: int = 5):
    verified = load_verification_index(
        ROOT / "benchmarks/content_scenarios_v1.json", test_root=ROOT / "tests"
    )
    return build_content_manifest(
        test_root=ROOT / "tests",
        verified_scenarios=verified,
        behavior_version=behavior_version,
    )


def test_manifest_covers_every_configured_card_and_spell() -> None:
    manifest = audited_manifest()
    assert manifest["summary"]["cards"] == 229
    assert manifest["summary"]["spells"] == 28
    assert len({entry["id"] for entry in manifest["cards"]}) == 229
    assert len({entry["id"] for entry in manifest["spells"]}) == 28


def test_manifest_is_deterministic() -> None:
    first = content_manifest_json(audited_manifest())
    second = content_manifest_json(audited_manifest())
    assert first == second


def test_tracked_manifest_matches_runtime_inventory() -> None:
    generated = content_manifest_json(audited_manifest())
    assert generated == (ROOT / "benchmarks/hsbg_content_audit_v1.json").read_text()


def test_tracked_v6_manifest_matches_runtime_inventory() -> None:
    generated = content_manifest_json(audited_manifest(6))
    assert generated == (ROOT / "benchmarks/hsbg_content_audit_v6.json").read_text()


def test_explicit_scenario_index_promotes_verified_content() -> None:
    manifest = audited_manifest()
    aureate = next(entry for entry in manifest["cards"] if entry["symbol"] == "AUREATE_LAUREATE")
    assert "tests/test_card_def.py" in aureate["test_reference_files"]
    assert aureate["classification"] == "verified"
    assert aureate["verified_scenarios"]


def test_every_entry_has_an_explicit_supported_status() -> None:
    manifest = audited_manifest()
    allowed = {"verified", "implemented_unverified", "partial", "unsupported"}
    assert {entry["classification"] for entry in manifest["cards"]} <= allowed
    assert {entry["classification"] for entry in manifest["spells"]} <= allowed


def test_current_tier3_shop_exposes_known_legacy_incomplete_cards() -> None:
    manifest = audited_manifest()
    incomplete = [
        entry["symbol"]
        for entry in manifest["cards"]
        if entry["shop_eligible_tier3"] and not entry["handler_complete"]
    ]
    assert incomplete == ["ANCESTRAL_AUTOMATON", "DEFLECT_O_BOT", "WAVELING"]


def test_declared_no_op_effect_is_reported() -> None:
    manifest = audited_manifest()
    crewmate = next(
        entry for entry in manifest["cards"] if entry["symbol"] == "WHEELED_CREWMATE"
    )
    assert "declared_no_op_effect:BattlecryModifyMechanic" in crewmate["issues"]


def test_content_admission_requires_both_handlers_and_scenarios() -> None:
    manifest = audited_manifest()
    assert validate_content_admission(
        manifest, card_ids=["102"], spell_ids=["S003", "S006"]
    ) == {"accepted": 3, "cards": 1, "spells": 2}
    with pytest.raises(ValueError, match="unverified_card:101"):
        validate_content_admission(manifest, card_ids=["101"], spell_ids=[])
    with pytest.raises(ValueError, match="incomplete_card:335"):
        validate_content_admission(manifest, card_ids=["335"], spell_ids=[])


def test_current_tier1_shop_passes_verified_admission() -> None:
    manifest = audited_manifest()
    tier_one = [
        entry["id"]
        for entry in manifest["cards"]
        if entry["shop_eligible_tier3"] and entry["tier"] == 1
    ]
    assert validate_content_admission(
        manifest, card_ids=tier_one, spell_ids=[]
    )["cards"] == 15


def test_handler_complete_tier2_cards_pass_verified_admission() -> None:
    manifest = audited_manifest()
    tier_two = [
        entry["id"]
        for entry in manifest["cards"]
        if entry["shop_eligible_tier3"]
        and entry["tier"] == 2
        and entry["handler_complete"]
    ]
    assert validate_content_admission(
        manifest, card_ids=tier_two, spell_ids=[]
    )["cards"] == 17


def test_handler_complete_tier1_to_tier3_cards_pass_verified_admission() -> None:
    manifest = audited_manifest()
    admitted = [
        entry["id"]
        for entry in manifest["cards"]
        if entry["shop_eligible_tier3"] and entry["handler_complete"]
    ]
    assert len(admitted) == 51
    assert validate_content_admission(
        manifest, card_ids=admitted, spell_ids=[]
    )["accepted"] == 51


def test_v6_resolves_play_as_summon_gaps_and_admits_53_shop_cards() -> None:
    manifest = audited_manifest(6)
    admitted = [
        entry["id"]
        for entry in manifest["cards"]
        if entry["shop_eligible_tier3"] and entry["handler_complete"]
    ]
    assert len(admitted) == 53
    assert validate_content_admission(
        manifest, card_ids=admitted, spell_ids=[]
    )["accepted"] == 53
    rejected = [
        entry["symbol"]
        for entry in manifest["cards"]
        if entry["shop_eligible_tier3"] and not entry["handler_complete"]
    ]
    assert rejected == ["WAVELING"]


def test_v6_tier3_profile_admits_all_verified_shop_content() -> None:
    profile = build_content_profile(audited_manifest(6), max_tier=3)
    assert len(profile["shop_card_ids"]) == 53
    assert len(profile["next_tier_discovery_card_ids"]) == 4
    assert len(profile["generated_card_ids"]) == 4
    assert len(profile["included_card_ids"]) == 61
    assert len(profile["pool_spell_ids"]) == 5
    assert len(profile["generated_spell_ids"]) == 7
    assert len(profile["included_spell_ids"]) == 10
    assert "WAVELING" in [entry["symbol"] for entry in profile["excluded_cards"]]
    assert not profile["excluded_spells"]


def test_v6_fulltier_profile_has_verified_content_at_every_tier() -> None:
    profile = build_content_profile(audited_manifest(6), max_tier=6)
    assert len(profile["shop_card_ids"]) == 65
    assert len(profile["next_tier_discovery_card_ids"]) == 5
    assert len(profile["included_spell_ids"]) == 12
    by_id = {entry["id"]: entry for entry in audited_manifest(6)["cards"]}
    included_tiers = {by_id[content_id]["tier"] for content_id in profile["shop_card_ids"]}
    assert included_tiers == {1, 2, 3, 4, 5, 6}
