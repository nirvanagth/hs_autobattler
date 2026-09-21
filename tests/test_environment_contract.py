"""Research artifact compatibility-contract tests."""

from hearthstone.env.environment_contract import (
    BEHAVIOR_VERSION,
    card_pool_digest,
    contract_json,
    parse_contract,
)
from hearthstone.env.hs_env import HearthstoneEnv


def test_environment_contract_is_deterministic() -> None:
    first = HearthstoneEnv(card_vocab_scheme="stable_v1")
    second = HearthstoneEnv(card_vocab_scheme="stable_v1")
    assert first.environment_contract == second.environment_contract
    assert first.environment_contract["behavior_version"] == BEHAVIOR_VERSION
    assert len(first.environment_contract["card_pool_digest"]) == 64
    assert first.environment_contract["card_pool_digest"] == card_pool_digest()


def test_environment_contract_captures_tier_frontier() -> None:
    tier_three = HearthstoneEnv(max_tier=3, card_vocab_scheme="stable_v1")
    tier_six = HearthstoneEnv(max_tier=6, card_vocab_scheme="stable_v1")
    assert tier_three.environment_contract != tier_six.environment_contract
    assert tier_three.environment_contract["max_tier"] == 3


def test_environment_contract_json_roundtrip() -> None:
    env = HearthstoneEnv(card_vocab_scheme="stable_v1")
    encoded = contract_json(env.environment_contract)
    assert parse_contract(encoded) == env.environment_contract


def test_behavior_version_is_explicit_and_defaults_to_frozen_v5() -> None:
    assert HearthstoneEnv(max_tier=3).environment_contract["behavior_version"] == 5
    assert (
        HearthstoneEnv(max_tier=3, behavior_version=6).environment_contract[
            "behavior_version"
        ]
        == 6
    )
