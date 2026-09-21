"""Versioned behavior-v6 event semantics without mutating frozen v5."""

import json
from pathlib import Path

from hearthstone.engine.entities import HandCard, Unit
from hearthstone.engine.enums import CardIDs, SpellIDs
from hearthstone.engine.game import Game
from hearthstone.engine.lobby import LobbyGame
from hearthstone.env.lobby_env import BattlegroundsLobbyEnv


ROOT = Path(__file__).resolve().parent.parent


def play_second_automaton(behavior_version: int):
    game = Game(max_tier=3, behavior_version=behavior_version)
    player = game.players[0]
    first = Unit.create_from_db(
        CardIDs.ANCESTRAL_AUTOMATON, game.tavern.get_next_uid(), player.uid
    )
    second = Unit.create_from_db(
        CardIDs.ANCESTRAL_AUTOMATON, game.tavern.get_next_uid(), player.uid
    )
    player.board = [first]
    player.hand = [HandCard(uid=second.uid, unit=second)]
    before = [(unit.cur_atk, unit.cur_hp) for unit in (first, second)]
    assert game.step(0, "PLAY", hand_index=0)[0]
    after = [(unit.cur_atk, unit.cur_hp) for unit in (first, second)]
    return before, after


def test_v5_preserves_legacy_missing_summon_event() -> None:
    before, after = play_second_automaton(5)
    assert after == before


def test_v6_play_emits_summon_event_for_automaton() -> None:
    before, after = play_second_automaton(6)
    assert after == [
        (before[0][0] + 3, before[0][1] + 2),
        (before[1][0] + 3, before[1][1] + 2),
    ]


def test_v6_play_triggers_deflect_o_bot_for_mech() -> None:
    game = Game(max_tier=3, behavior_version=6)
    player = game.players[0]
    deflect = Unit.create_from_db(
        CardIDs.DEFLECT_O_BOT, game.tavern.get_next_uid(), player.uid
    )
    mech = Unit.create_from_db(
        CardIDs.CORD_PULLER, game.tavern.get_next_uid(), player.uid
    )
    player.board = [deflect]
    player.hand = [HandCard(uid=mech.uid, unit=mech)]
    before = deflect.cur_atk
    assert game.step(0, "PLAY", hand_index=0)[0]
    assert deflect.cur_atk == before + 2
    assert deflect.has_divine_shield


def test_v6_lobby_profile_excludes_unverified_content() -> None:
    profile = json.loads(
        (ROOT / "benchmarks/hsbg_content_profile_v6_tier3.json").read_text()
    )
    lobby = LobbyGame(
        max_tier=3,
        behavior_version=6,
        content_profile=profile,
        seed=31,
    )
    allowed_cards = set(profile["included_card_ids"])
    allowed_spells = set(profile["included_spell_ids"])
    assert {
        str(getattr(card_id, "value", card_id))
        for tier in lobby.pool.tiers.values()
        for card_id in tier
    } <= allowed_cards
    assert {
        str(getattr(spell_id, "value", spell_id))
        for tier in lobby.spell_pool.tiers.values()
        for spell_id in tier
    } <= allowed_spells
    assert "335" not in allowed_cards  # Waveling remains partial.


def test_v6_lobby_environment_contract_hashes_content_profile() -> None:
    profile = json.loads(
        (ROOT / "benchmarks/hsbg_content_profile_v6_tier3.json").read_text()
    )
    first = BattlegroundsLobbyEnv(
        max_tier=3,
        behavior_version=6,
        content_profile=profile,
    )
    second = BattlegroundsLobbyEnv(
        max_tier=3,
        behavior_version=6,
        content_profile=profile,
    )
    assert first.lobby_environment_contract["behavior_version"] == 6
    assert first.lobby_environment_contract == second.lobby_environment_contract
    assert len(first.lobby_environment_contract["content_profile_sha256"]) == 64


def test_v6_fulltier_profile_supports_tier7_triple_discovery() -> None:
    profile = json.loads(
        (ROOT / "benchmarks/hsbg_content_profile_v6_fulltier.json").read_text()
    )
    game = Game(
        max_tier=6,
        behavior_version=6,
        content_profile=profile,
    )
    player = game.players[0]
    player.tavern_tier = 6
    golden = Unit.create_from_db(
        CardIDs.AUREATE_LAUREATE,
        game.tavern.get_next_uid(),
        player.uid,
        is_golden=True,
        pool_copies=3,
    )
    player.hand = [HandCard(uid=golden.uid, unit=golden)]
    assert game.step(0, "PLAY", hand_index=0)[0]
    reward_index = next(
        index
        for index, card in enumerate(player.hand)
        if card.spell and card.spell.card_id == SpellIDs.TRIPLET_REWARD
    )
    assert game.step(0, "PLAY", hand_index=reward_index)[0]
    allowed_tier7 = set(profile["next_tier_discovery_card_ids"])
    assert len(player.discovery.options) == 3
    assert {
        str(getattr(option.unit.card_id, "value", option.unit.card_id))
        for option in player.discovery.options
        if option.unit
    } <= allowed_tier7
