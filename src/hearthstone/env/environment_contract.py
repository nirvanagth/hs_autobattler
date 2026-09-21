"""Versioned compatibility contract for research artifacts."""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass
from enum import Enum
from functools import lru_cache
from typing import Any

from hearthstone.engine.configs import CARD_DB, ROTATED_OUT, SPELL_DB, TIER_COPIES


ENVIRONMENT_NAME = "hsbg_1v1_research"
BEHAVIOR_VERSION = 2
OBSERVATION_SCHEMA_VERSION = 1
ACTION_SCHEMA_VERSION = 1


def _normalize(value: Any) -> Any:
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, dict):
        return {
            str(_normalize(key)): _normalize(item)
            for key, item in sorted(value.items(), key=lambda pair: str(pair[0]))
        }
    if isinstance(value, (set, frozenset)):
        return sorted((_normalize(item) for item in value), key=str)
    if isinstance(value, (list, tuple)):
        return [_normalize(item) for item in value]
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    return repr(value)


@lru_cache(maxsize=1)
def card_pool_digest() -> str:
    """Digest card/spell stats, pool membership, and copy counts."""
    payload = {
        "cards": _normalize(CARD_DB),
        "spells": _normalize(SPELL_DB),
        "rotated_out": _normalize(ROTATED_OUT),
        "tier_copies": _normalize(TIER_COPIES),
    }
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


@dataclass(frozen=True)
class EnvironmentContract:
    name: str
    behavior_version: int
    observation_schema_version: int
    action_schema_version: int
    observation_size: int
    entity_features: int
    action_count: int
    max_tier: int
    card_vocab_scheme: str
    card_vocab_hash: str
    card_pool_digest: str

    def metadata(self) -> dict[str, str | int]:
        return asdict(self)


def build_environment_contract(
    *,
    observation_size: int,
    entity_features: int,
    action_count: int,
    max_tier: int,
    card_vocab_scheme: str,
    card_vocab_hash: str,
) -> EnvironmentContract:
    return EnvironmentContract(
        name=ENVIRONMENT_NAME,
        behavior_version=BEHAVIOR_VERSION,
        observation_schema_version=OBSERVATION_SCHEMA_VERSION,
        action_schema_version=ACTION_SCHEMA_VERSION,
        observation_size=int(observation_size),
        entity_features=int(entity_features),
        action_count=int(action_count),
        max_tier=int(max_tier),
        card_vocab_scheme=card_vocab_scheme,
        card_vocab_hash=card_vocab_hash,
        card_pool_digest=card_pool_digest(),
    )


def parse_contract(value: object) -> dict[str, str | int] | None:
    if value is None:
        return None
    if isinstance(value, dict):
        return value
    if isinstance(value, bytes):
        value = value.decode("utf-8")
    if hasattr(value, "item"):
        value = value.item()
    if isinstance(value, str):
        parsed = json.loads(value)
        if not isinstance(parsed, dict):
            raise ValueError("environment contract JSON must contain an object")
        return parsed
    raise ValueError(f"unsupported environment contract representation: {type(value)}")


def contract_json(contract: dict[str, str | int]) -> str:
    return json.dumps(contract, sort_keys=True, separators=(",", ":"))
