"""Suggest exact-name internal↔live CardID aliases from HearthstoneJSON."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
import unicodedata
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from hearthstone.engine.configs import CARD_DB, SPELL_DB


def normalize_name(name: str) -> str:
    normalized = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]+", "", normalized.casefold())


def is_normal_battlegrounds_card(card: dict) -> bool:
    card_id = str(card.get("id", ""))
    if card.get("set") != "BATTLEGROUNDS":
        return False
    if card_id.endswith("_G") or card_id.endswith("_Gt"):
        return False
    card_type = card.get("type")
    if card_type == "MINION":
        return card.get("battlegroundsPremiumDbfId") is not None
    return card_type in {"SPELL", "BATTLEGROUND_SPELL"}


def build_aliases(cards_json: list[dict]) -> dict:
    by_name_type: dict[tuple[str, str], list[dict]] = defaultdict(list)
    for card in cards_json:
        if is_normal_battlegrounds_card(card):
            normalized_type = (
                "SPELL"
                if card.get("type") in {"SPELL", "BATTLEGROUND_SPELL"}
                else str(card.get("type", ""))
            )
            by_name_type[(normalize_name(str(card.get("name", ""))), normalized_type)].append(card)
    aliases = {}
    unresolved = {}
    for kind, database, live_type in (
        ("card", CARD_DB, "MINION"),
        ("spell", SPELL_DB, "SPELL"),
    ):
        for internal_id, data in database.items():
            raw_id = str(getattr(internal_id, "value", internal_id))
            candidates = by_name_type.get((normalize_name(data["name"]), live_type), [])
            if kind == "card":
                tier_matches = [
                    card
                    for card in candidates
                    if int(card.get("techLevel", data["tier"])) == int(data["tier"])
                ]
                candidates = tier_matches or candidates
            candidate_ids = sorted({str(card["id"]) for card in candidates})
            if len(candidate_ids) == 1:
                aliases[raw_id] = {
                    "kind": kind,
                    "live_card_id": candidate_ids[0],
                    "match": "exact_normalized_name_and_tier"
                    if kind == "card"
                    else "exact_normalized_name",
                }
            else:
                unresolved[raw_id] = {
                    "kind": kind,
                    "name": data["name"],
                    "candidate_live_card_ids": candidate_ids,
                    "reason": "no_unique_exact_match",
                }
    return {
        "schema_version": 1,
        "aliases": dict(sorted(aliases.items())),
        "unresolved": dict(sorted(unresolved.items())),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--cards-json", required=True)
    parser.add_argument("--out", required=True)
    args = parser.parse_args()
    source = Path(args.cards_json)
    payload = build_aliases(json.loads(source.read_text()))
    payload["source_sha256"] = hashlib.sha256(source.read_bytes()).hexdigest()
    encoded = json.dumps(payload, indent=2, sort_keys=True) + "\n"
    output = Path(args.out)
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = output.with_suffix(".tmp")
    temporary.write_text(encoded)
    temporary.replace(output)
    print(
        json.dumps(
            {
                "aliases": len(payload["aliases"]),
                "unresolved": len(payload["unresolved"]),
            }
        )
    )


if __name__ == "__main__":
    main()
