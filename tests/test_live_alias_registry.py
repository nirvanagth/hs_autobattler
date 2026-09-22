"""Tracked live CardID alias and observed coverage contracts."""

import json
from pathlib import Path

from hearthstone.engine.configs import CARD_DB, SPELL_DB


ROOT = Path(__file__).resolve().parent.parent


def test_alias_registry_is_unique_and_references_internal_content() -> None:
    payload = json.loads((ROOT / "benchmarks/live_card_aliases_v1.json").read_text())
    aliases = payload["aliases"]
    internal_ids = {str(getattr(value, "value", value)) for value in CARD_DB | SPELL_DB}
    assert set(aliases) <= internal_ids
    live_ids = [entry["live_card_id"] for entry in aliases.values()]
    assert len(live_ids) == len(set(live_ids))
    assert len(aliases) == 239


def test_partial_live_coverage_report_is_honestly_pending() -> None:
    report = json.loads(
        (ROOT / "benchmarks/hsbg_live_alias_coverage_partial_v1.json").read_text()
    )
    assert report["observed_normal_minion_ids"] == 227
    assert report["mapped_observed_minion_ids"] == 111
    assert report["normal_minion_alias_coverage"] < 0.5
    assert report["spell_alias_coverage"] < 0.1
