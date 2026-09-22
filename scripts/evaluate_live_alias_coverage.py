"""Measure exact alias coverage over sanitized live CardIDs."""

from __future__ import annotations

import argparse
import json
from pathlib import Path


def read_jsonl(path: Path):
    for line in path.read_text().splitlines():
        if line:
            yield json.loads(line)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--aliases", required=True)
    parser.add_argument("--cards-json", required=True)
    parser.add_argument("--events", action="append", required=True)
    parser.add_argument("--out", required=True)
    args = parser.parse_args()
    aliases = json.loads(Path(args.aliases).read_text())["aliases"]
    reverse = {entry["live_card_id"]: internal for internal, entry in aliases.items()}
    public_cards = {
        card["id"]: card
        for card in json.loads(Path(args.cards_json).read_text())
        if card.get("set") == "BATTLEGROUNDS"
    }
    observed = {
        event["card_id"]
        for raw_path in args.events
        for event in read_jsonl(Path(raw_path))
        if event.get("card_id")
    }
    observed_known = observed & set(public_cards)
    observed_minions = {
        card_id
        for card_id in observed_known
        if public_cards[card_id].get("type") == "MINION"
        and not card_id.endswith(("_G", "_Gt"))
    }
    observed_spells = {
        card_id
        for card_id in observed_known
        if public_cards[card_id].get("type") in {"SPELL", "BATTLEGROUND_SPELL"}
    }
    report = {
        "schema_version": 1,
        "observed_live_card_ids": len(observed),
        "observed_ids_in_public_dataset": len(observed_known),
        "observed_normal_minion_ids": len(observed_minions),
        "mapped_observed_minion_ids": len(observed_minions & set(reverse)),
        "normal_minion_alias_coverage": (
            len(observed_minions & set(reverse)) / len(observed_minions)
            if observed_minions
            else 1.0
        ),
        "observed_spell_ids": len(observed_spells),
        "mapped_observed_spell_ids": len(observed_spells & set(reverse)),
        "spell_alias_coverage": (
            len(observed_spells & set(reverse)) / len(observed_spells)
            if observed_spells
            else 1.0
        ),
        "mapped_live_to_internal": {
            live_id: reverse[live_id] for live_id in sorted(observed & set(reverse))
        },
    }
    output = Path(args.out)
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = output.with_suffix(".tmp")
    temporary.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    temporary.replace(output)
    print(json.dumps({key: value for key, value in report.items() if not isinstance(value, dict)}, indent=2))


if __name__ == "__main__":
    main()
