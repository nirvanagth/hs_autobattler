"""Executable content-manifest audit tests."""

from pathlib import Path

from hearthstone.engine.content_audit import (
    build_content_manifest,
    content_manifest_json,
)


ROOT = Path(__file__).resolve().parent.parent


def test_manifest_covers_every_configured_card_and_spell() -> None:
    manifest = build_content_manifest(test_root=ROOT / "tests")
    assert manifest["summary"]["cards"] == 229
    assert manifest["summary"]["spells"] == 28
    assert len({entry["id"] for entry in manifest["cards"]}) == 229
    assert len({entry["id"] for entry in manifest["spells"]}) == 28


def test_manifest_is_deterministic() -> None:
    first = content_manifest_json(build_content_manifest(test_root=ROOT / "tests"))
    second = content_manifest_json(build_content_manifest(test_root=ROOT / "tests"))
    assert first == second


def test_tracked_manifest_matches_runtime_inventory() -> None:
    generated = content_manifest_json(build_content_manifest(test_root=ROOT / "tests"))
    assert generated == (ROOT / "benchmarks/hsbg_content_audit_v1.json").read_text()


def test_manifest_exposes_test_references_without_claiming_verification() -> None:
    manifest = build_content_manifest(test_root=ROOT / "tests")
    aureate = next(entry for entry in manifest["cards"] if entry["symbol"] == "AUREATE_LAUREATE")
    assert "tests/test_card_def.py" in aureate["test_reference_files"]
    assert aureate["classification"] == "implemented_unverified"
    assert not aureate["verified_scenarios"]


def test_every_entry_has_an_explicit_supported_status() -> None:
    manifest = build_content_manifest(test_root=ROOT / "tests")
    allowed = {"verified", "implemented_unverified", "partial", "unsupported"}
    assert {entry["classification"] for entry in manifest["cards"]} <= allowed
    assert {entry["classification"] for entry in manifest["spells"]} <= allowed


def test_current_tier3_shop_has_no_handler_incomplete_cards() -> None:
    manifest = build_content_manifest(test_root=ROOT / "tests")
    assert manifest["summary"]["tier3_shop_handler_incomplete"] == 0


def test_declared_no_op_effect_is_reported() -> None:
    manifest = build_content_manifest(test_root=ROOT / "tests")
    crewmate = next(
        entry for entry in manifest["cards"] if entry["symbol"] == "WHEELED_CREWMATE"
    )
    assert "declared_no_op_effect:BattlecryModifyMechanic" in crewmate["issues"]
