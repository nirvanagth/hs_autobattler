"""Versioned card-id mappings for model observations.

The historical mapping sorted the currently loaded card database. Adding a
card therefore shifted unrelated embedding rows. ``stable_v1`` assigns indices
from the project's canonical id namespaces, so existing rows remain stable
when a patch appends cards.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Iterable


LEGACY_SORTED = "legacy_sorted"
STABLE_V1 = "stable_v1"
CARD_VOCAB_SCHEMES = (LEGACY_SORTED, STABLE_V1)
STABLE_V1_SIZE = 2048
_STABLE_V1_CONTRACT = "numeric=id;tNNN=800+N;SNNN=1000+N;size=2048"


def canonical_card_id(card_id: object) -> str:
    return str(getattr(card_id, "value", card_id))


def stable_v1_index(card_id: object) -> int:
    raw = canonical_card_id(card_id)
    if raw.isdigit():
        index = int(raw)
    elif raw.startswith("t") and raw[1:].isdigit():
        index = 800 + int(raw[1:])
    elif raw.startswith("S") and raw[1:].isdigit():
        index = 1000 + int(raw[1:])
    else:
        raise ValueError(f"card id {raw!r} is unsupported by {STABLE_V1}")
    if not 0 < index < STABLE_V1_SIZE:
        raise ValueError(f"card id {raw!r} maps outside {STABLE_V1_SIZE} rows")
    return index


def build_card_vocabulary(
    card_ids: Iterable[object], scheme: str
) -> tuple[dict[object, int], int, tuple[str, ...], str]:
    ids = list(card_ids)
    if scheme == LEGACY_SORTED:
        ids.sort()
        mapping = {card_id: i + 1 for i, card_id in enumerate(ids)}
        vocabulary = tuple(canonical_card_id(card_id) for card_id in ids)
        payload = json.dumps(vocabulary, separators=(",", ":"))
        digest = hashlib.sha256(payload.encode("utf-8")).hexdigest()
        return mapping, len(ids) + 1, vocabulary, digest
    if scheme != STABLE_V1:
        raise ValueError(f"unknown card vocabulary scheme: {scheme}")

    mapping = {card_id: stable_v1_index(card_id) for card_id in ids}
    if len(set(mapping.values())) != len(mapping):
        raise ValueError("stable_v1 produced a card-id collision")
    vocabulary = tuple(
        f"{index}:{canonical_card_id(card_id)}"
        for card_id, index in sorted(mapping.items(), key=lambda item: item[1])
    )
    digest = hashlib.sha256(
        f"{STABLE_V1}:{_STABLE_V1_CONTRACT}".encode("utf-8")
    ).hexdigest()
    return mapping, STABLE_V1_SIZE, vocabulary, digest
