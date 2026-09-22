"""Exact live CardID alias suggestion tests."""

from scripts.build_live_card_aliases import build_aliases, normalize_name


def test_name_normalization_handles_punctuation_and_accents() -> None:
    assert normalize_name("Timecap'n Hooktail") == "timecapnhooktail"
    assert normalize_name("Sin’dorei Straight Shot") == "sindoreistraightshot"


def test_builder_accepts_battleground_spell_type() -> None:
    payload = build_aliases(
        [
            {
                "id": "BG28_810",
                "name": "Tavern Coin",
                "type": "BATTLEGROUND_SPELL",
                "set": "BATTLEGROUNDS",
            }
        ]
    )
    assert payload["aliases"]["S001"]["live_card_id"] == "BG28_810"
