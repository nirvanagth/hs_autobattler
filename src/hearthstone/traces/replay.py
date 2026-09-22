"""Conservative overlap selection and behavior-v7 trace replay."""

from __future__ import annotations

import hashlib
import json
import random
from collections import Counter
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Iterable

from hearthstone.engine.entities import HandCard, HeroState, Spell, StoreItem, Unit
from hearthstone.engine.game import Game
from hearthstone.engine.pool import CardPool, SpellPool
from hearthstone.engine.spells import SPELLS_REQUIRE_TARGET
from hearthstone.traces.powerlog import (
    ACTION_CLASSIFIER_VERSION,
    classify_battlegrounds_action,
)


OVERLAP_CONTRACT_SCHEMA_VERSION = 1
REPLAY_RESULT_SCHEMA_VERSION = 1


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def build_overlap_contract(
    profile: dict[str, Any],
    aliases: dict[str, Any],
    *,
    profile_sha256: str,
    aliases_sha256: str,
) -> dict[str, Any]:
    """Freeze the live/internal overlap and action replay policy."""
    included_cards = set(profile["included_card_ids"])
    included_spells = set(profile["included_spell_ids"])
    supported_aliases = {}
    for internal_id, entry in sorted(aliases["aliases"].items()):
        kind = entry["kind"]
        if (kind == "card" and internal_id not in included_cards) or (
            kind == "spell" and internal_id not in included_spells
        ):
            continue
        supported_aliases[entry["live_card_id"]] = {
            "internal_id": internal_id,
            "kind": kind,
            "match": entry["match"],
        }
    return {
        "schema_version": OVERLAP_CONTRACT_SCHEMA_VERSION,
        "action_classifier_version": ACTION_CLASSIFIER_VERSION,
        "behavior_version": int(profile["behavior_version"]),
        "content_profile": {
            "sha256": profile_sha256,
            "max_tier": int(profile["max_tier"]),
            "internal_card_ids": sorted(included_cards),
            "internal_spell_ids": sorted(included_spells),
        },
        "alias_registry": {
            "sha256": aliases_sha256,
            "source_sha256": aliases["source_sha256"],
            "supported_live_aliases": supported_aliases,
        },
        "action_policy": {
            "BUY": {
                "status": "replay",
                "comparison_mode": "deterministic",
                "comparison_fields": ["board", "hand", "shop"],
            },
            "SELL": {
                "status": "replay",
                "comparison_mode": "deterministic",
                "comparison_fields": ["board", "hand", "shop"],
            },
            "PLAY_CARD": {
                "status": "replay",
                "comparison_mode": "deterministic",
                "comparison_fields": ["board", "hand", "shop"],
            },
            "ROLL": {
                "status": "replay",
                "comparison_mode": "invariant_only",
                "comparison_fields": ["shop_size", "shop_tier_bounds"],
            },
            "UPGRADE": {
                "status": "replay",
                "comparison_mode": "deterministic",
                "comparison_fields": ["tavern_tier", "upgrade_cost"],
            },
            "FREEZE": {"status": "exclude", "reason": "freeze_state_unobserved"},
            "HERO_POWER": {
                "status": "exclude",
                "reason": "live_hero_roster_unsupported",
            },
            "SPECIAL_ACTION": {
                "status": "exclude",
                "reason": "special_action_semantics_unsupported",
            },
        },
        "state_contract": {
            "hydrated_fields": [
                "board",
                "hand",
                "shop",
                "tavern_tier",
                "upgrade_cost",
                "visible_attack",
                "visible_health",
                "visible_damage",
            ],
            "synthetic_fields": ["gold", "hero_identity", "rng_seed"],
            "excluded_exact_fields": [
                "gold",
                "hero_state",
                "frozen_state",
                "random_shop_identity_after_roll",
                "unlogged_enchantments",
            ],
        },
    }


def validate_overlap_contract(
    contract: dict[str, Any], profile_path: Path, aliases_path: Path
) -> None:
    if contract.get("schema_version") != OVERLAP_CONTRACT_SCHEMA_VERSION:
        raise ValueError("unsupported overlap contract schema")
    if contract.get("action_classifier_version") != ACTION_CLASSIFIER_VERSION:
        raise ValueError("action classifier version does not match overlap contract")
    if contract.get("behavior_version") != 7:
        raise ValueError("trace replay requires behavior version 7")
    if sha256_file(profile_path) != contract["content_profile"]["sha256"]:
        raise ValueError("content profile hash does not match overlap contract")
    if sha256_file(aliases_path) != contract["alias_registry"]["sha256"]:
        raise ValueError("alias registry hash does not match overlap contract")


@dataclass(frozen=True)
class ReplayDecision:
    eligible: bool
    action_type: str
    comparison_mode: str | None
    reasons: tuple[str, ...]
    player_controller: int | None
    shop_controller: int | None
    source_internal_id: str | None
    simulator_action: str | None
    action_kwargs: dict[str, int]

    def to_dict(self) -> dict[str, Any]:
        value = asdict(self)
        value["reasons"] = list(self.reasons)
        return value


def _entity_map(snapshot: dict[str, Any]) -> dict[int, dict[str, Any]]:
    return {
        int(entity["entity_id"]): entity
        for entity in snapshot.get("entities", [])
        if entity.get("entity_id") is not None
    }


def _tags(entity: dict[str, Any] | None) -> dict[str, Any]:
    return entity.get("tags", {}) if entity else {}


def _position(entity: dict[str, Any]) -> int:
    return int(_tags(entity).get("ZONE_POSITION", 0) or 0)


def _is_live_content(entity: dict[str, Any]) -> bool:
    card_id = entity.get("card_id")
    tags = _tags(entity)
    if not card_id or _position(entity) <= 0:
        return False
    if "ATK" in tags and "HEALTH" in tags:
        return True
    return "COST" in tags and "TECH_LEVEL" in tags


def _zone_entities(
    snapshot: dict[str, Any], controller: int | None, zone: str
) -> list[dict[str, Any]]:
    if controller is None:
        return []
    entities = [
        entity
        for entity in snapshot.get("entities", [])
        if _tags(entity).get("CONTROLLER") == controller
        and _tags(entity).get("ZONE") == zone
        and _is_live_content(entity)
    ]
    return sorted(entities, key=lambda item: (_position(item), item["entity_id"]))


def _find_source_entity(transition: dict[str, Any]) -> dict[str, Any] | None:
    source_id = transition.get("source_entity_id")
    for snapshot_name in ("before", "after"):
        entity = _entity_map(transition[snapshot_name]).get(source_id)
        if entity is not None:
            return entity
    return None


def _find_shop_controller(transition: dict[str, Any], player_controller: int | None) -> int | None:
    before = transition["before"]
    after_by_id = _entity_map(transition["after"])
    for entity in before.get("entities", []):
        card_id = entity.get("card_id") or ""
        tags = _tags(entity)
        if (
            card_id.startswith("TB_BaconShopBob")
            and tags.get("ZONE") == "PLAY"
            and tags.get("CONTROLLER") != player_controller
        ):
            return int(tags["CONTROLLER"])
    if transition.get("action_type") == "BUY":
        for entity in before.get("entities", []):
            candidate = after_by_id.get(entity["entity_id"])
            if candidate is None:
                continue
            before_tags = _tags(entity)
            after_tags = _tags(candidate)
            if (
                _is_live_content(entity)
                and before_tags.get("ZONE") == "PLAY"
                and before_tags.get("CONTROLLER") != player_controller
                and after_tags.get("ZONE") == "HAND"
                and after_tags.get("CONTROLLER") == player_controller
            ):
                return int(before_tags["CONTROLLER"])
    return None


def _alias_map(contract: dict[str, Any]) -> dict[str, dict[str, str]]:
    return contract["alias_registry"]["supported_live_aliases"]


def _unmapped_zone_reasons(
    snapshot: dict[str, Any],
    controller: int | None,
    zone: str,
    aliases: dict[str, dict[str, str]],
    label: str,
) -> list[str]:
    return [
        f"unmapped_{label}_card"
        for entity in _zone_entities(snapshot, controller, zone)
        if entity.get("card_id") not in aliases
    ]


def _changed_board_target(transition: dict[str, Any], player_controller: int) -> int | None:
    before_board = _zone_entities(transition["before"], player_controller, "PLAY")
    after_by_id = _entity_map(transition["after"])
    changed_ids = []
    for entity in before_board:
        if entity["entity_id"] == transition.get("source_entity_id"):
            continue
        after = after_by_id.get(entity["entity_id"])
        if after is None:
            continue
        before_view = {key: _tags(entity).get(key) for key in ("ATK", "HEALTH", "DAMAGE")}
        after_view = {key: _tags(after).get(key) for key in ("ATK", "HEALTH", "DAMAGE")}
        if before_view != after_view or entity.get("card_id") != after.get("card_id"):
            changed_ids.append(entity["entity_id"])
    if len(changed_ids) != 1:
        return None
    return next(
        index for index, entity in enumerate(before_board) if entity["entity_id"] == changed_ids[0]
    )


def select_replayable_transition(
    transition: dict[str, Any], contract: dict[str, Any]
) -> ReplayDecision:
    """Classify one sanitized transition and infer simulator arguments."""
    action_type = classify_battlegrounds_action(
        transition.get("source_card_id"), transition.get("block_type")
    )
    action_type = str(action_type or "UNKNOWN")
    policy = contract["action_policy"].get(action_type)
    if policy is None:
        return ReplayDecision(
            False,
            action_type,
            None,
            ("unsupported_action",),
            None,
            None,
            None,
            None,
            {},
        )
    if policy["status"] != "replay":
        return ReplayDecision(
            False,
            action_type,
            None,
            (policy["reason"],),
            None,
            None,
            None,
            None,
            {},
        )

    source = _find_source_entity(transition)
    if source is None:
        return ReplayDecision(
            False,
            action_type,
            policy["comparison_mode"],
            ("missing_source_entity",),
            None,
            None,
            None,
            None,
            {},
        )
    controller = _tags(source).get("CONTROLLER")
    if not isinstance(controller, int):
        return ReplayDecision(
            False,
            action_type,
            policy["comparison_mode"],
            ("missing_player_controller",),
            None,
            None,
            None,
            None,
            {},
        )

    aliases = _alias_map(contract)
    shop_controller = _find_shop_controller(transition, controller)
    source_alias = aliases.get(str(transition.get("source_card_id") or ""))
    source_internal_id = source_alias["internal_id"] if source_alias else None
    reasons: list[str] = []
    kwargs: dict[str, int] = {}
    simulator_action = action_type

    if action_type == "UPGRADE":
        simulator_action = "UPGRADE"
    elif action_type == "SELL":
        board = _zone_entities(transition["before"], controller, "PLAY")
        reasons.extend(
            _unmapped_zone_reasons(transition["before"], controller, "PLAY", aliases, "board")
        )
        after_by_id = _entity_map(transition["after"])
        candidates = [
            (index, entity)
            for index, entity in enumerate(board)
            if _tags(after_by_id.get(entity["entity_id"])).get("ZONE") != "PLAY"
        ]
        if len(candidates) != 1:
            reasons.append("sell_target_not_inferred")
        else:
            kwargs["index"] = candidates[0][0]
            source_internal_id = aliases.get(candidates[0][1].get("card_id"), {}).get("internal_id")
        simulator_action = "SELL"
    elif action_type == "BUY":
        if shop_controller is None:
            reasons.append("missing_shop_controller")
        for zone_controller, zone, label in (
            (controller, "PLAY", "board"),
            (controller, "HAND", "hand"),
            (shop_controller, "PLAY", "shop"),
        ):
            reasons.extend(
                _unmapped_zone_reasons(transition["before"], zone_controller, zone, aliases, label)
            )
        store = _zone_entities(transition["before"], shop_controller, "PLAY")
        after_by_id = _entity_map(transition["after"])
        candidates = [
            (index, entity)
            for index, entity in enumerate(store)
            if _tags(after_by_id.get(entity["entity_id"])).get("ZONE") == "HAND"
            and _tags(after_by_id.get(entity["entity_id"])).get("CONTROLLER") == controller
        ]
        if len(candidates) != 1:
            reasons.append("buy_target_not_inferred")
        else:
            kwargs["index"] = candidates[0][0]
            source_internal_id = aliases.get(candidates[0][1].get("card_id"), {}).get("internal_id")
        simulator_action = "BUY"
    elif action_type == "PLAY_CARD":
        for zone_controller, zone, label in (
            (controller, "PLAY", "board"),
            (controller, "HAND", "hand"),
            (shop_controller, "PLAY", "shop"),
        ):
            reasons.extend(
                _unmapped_zone_reasons(transition["before"], zone_controller, zone, aliases, label)
            )
        hand = _zone_entities(transition["before"], controller, "HAND")
        source_indexes = [
            index
            for index, entity in enumerate(hand)
            if entity["entity_id"] == transition.get("source_entity_id")
        ]
        if len(source_indexes) != 1:
            reasons.append("play_source_not_in_hand")
        else:
            kwargs["hand_index"] = source_indexes[0]
        if source_alias is None:
            reasons.append("play_source_unmapped")
        else:
            target_index = _changed_board_target(transition, controller)
            if source_alias["kind"] == "spell":
                if source_internal_id in SPELLS_REQUIRE_TARGET and target_index is None:
                    reasons.append("play_spell_target_not_inferred")
                elif target_index is not None:
                    kwargs["target_index"] = target_index
            else:
                after_source = _entity_map(transition["after"]).get(
                    transition.get("source_entity_id")
                )
                if _tags(after_source).get("ZONE") != "PLAY":
                    reasons.append("play_destination_not_supported")
                else:
                    kwargs["insert_index"] = max(0, _position(after_source) - 1)
                    if target_index is not None:
                        kwargs["target_index"] = target_index
        simulator_action = "PLAY"
    elif action_type == "ROLL":
        if shop_controller is None:
            reasons.append("missing_shop_controller")
        for zone_controller, zone, label in (
            (controller, "PLAY", "board"),
            (shop_controller, "PLAY", "shop"),
        ):
            reasons.extend(
                _unmapped_zone_reasons(transition["before"], zone_controller, zone, aliases, label)
            )
        simulator_action = "ROLL"

    return ReplayDecision(
        not reasons,
        action_type,
        policy["comparison_mode"],
        tuple(sorted(set(reasons))),
        controller,
        shop_controller,
        source_internal_id,
        simulator_action,
        kwargs,
    )


def _internal_alias(entity: dict[str, Any], contract: dict[str, Any]) -> dict[str, str]:
    return _alias_map(contract)[entity["card_id"]]


def _unit_from_trace(entity: dict[str, Any], internal_id: str, owner_id: int) -> Unit:
    unit = Unit.create_from_db(internal_id, int(entity["entity_id"]), owner_id)
    tags = _tags(entity)
    observed_atk = int(tags.get("ATK", unit.cur_atk))
    observed_health = int(tags.get("HEALTH", unit.max_hp))
    unit.perm_atk_add += observed_atk - unit.cur_atk
    unit.perm_hp_add += observed_health - unit.max_hp
    unit.recalc_stats()
    unit.cur_hp = max(0, unit.max_hp - int(tags.get("DAMAGE", 0) or 0))
    unit.cur_atk = observed_atk
    return unit


def _store_item_from_trace(
    entity: dict[str, Any], alias: dict[str, str], owner_id: int
) -> StoreItem:
    if alias["kind"] == "spell":
        return StoreItem(spell=Spell.create_from_db(alias["internal_id"]))
    return StoreItem(unit=_unit_from_trace(entity, alias["internal_id"], owner_id))


def _hand_card_from_trace(entity: dict[str, Any], alias: dict[str, str], owner_id: int) -> HandCard:
    if alias["kind"] == "spell":
        return HandCard(
            uid=int(entity["entity_id"]),
            spell=Spell.create_from_db(alias["internal_id"]),
        )
    unit = _unit_from_trace(entity, alias["internal_id"], owner_id)
    return HandCard(uid=unit.uid, unit=unit)


def _active_upgrade(snapshot: dict[str, Any], controller: int) -> dict[str, Any] | None:
    candidates = [
        entity
        for entity in snapshot.get("entities", [])
        if (entity.get("card_id") or "").startswith("TB_BaconShopTechUp")
        and _tags(entity).get("CONTROLLER") == controller
        and _tags(entity).get("ZONE") == "PLAY"
    ]
    return candidates[-1] if candidates else None


def _remove_pool_copy(game: Game, internal_id: str) -> None:
    for cards in game.pool.tiers.values():
        if internal_id in cards:
            cards.remove(internal_id)
            return


def _hydrate_game(
    transition: dict[str, Any],
    decision: ReplayDecision,
    contract: dict[str, Any],
    profile: dict[str, Any],
    seed: int,
) -> Game:
    random_state = random.getstate()
    random.seed(seed)
    try:
        game = Game(
            max_tier=int(profile["max_tier"]),
            behavior_version=7,
            content_profile=profile,
        )
        included_cards = set(profile["included_card_ids"])
        included_spells = set(profile["included_spell_ids"])
        game.pool = CardPool(max_tier=7, included_card_ids=included_cards)
        game.spell_pool = SpellPool(included_spell_ids=included_spells)
        game.tavern.pool = game.pool
        game.tavern.spell_pool = game.spell_pool
        player = game.players[0]
        player.board = []
        player.hand = []
        player.economy.store = []
        player.hero = HeroState()
        player.gold = 100
        player.spell_discount = 0
        player.free_refreshes = 0
        player.discovery.is_active = False
        player.discovery.options = []
        player.pending_discovery_request = None

        before = transition["before"]
        controller = int(decision.player_controller)
        aliases = _alias_map(contract)
        board = _zone_entities(before, controller, "PLAY")
        hand = _zone_entities(before, controller, "HAND")
        store = _zone_entities(before, decision.shop_controller, "PLAY")
        for entity in board:
            alias = aliases.get(entity["card_id"])
            if alias is None:
                continue
            unit = _unit_from_trace(entity, alias["internal_id"], player.uid)
            player.board.append(unit)
            _remove_pool_copy(game, alias["internal_id"])
        for entity in hand:
            alias = aliases.get(entity["card_id"])
            if alias is None:
                continue
            player.hand.append(_hand_card_from_trace(entity, alias, player.uid))
            if alias["kind"] == "card":
                _remove_pool_copy(game, alias["internal_id"])
        for entity in store:
            alias = aliases.get(entity["card_id"])
            if alias is None:
                continue
            player.store.append(_store_item_from_trace(entity, alias, player.uid))
            if alias["kind"] == "card":
                _remove_pool_copy(game, alias["internal_id"])

        upgrade = _active_upgrade(before, controller)
        if upgrade is not None:
            next_tier = int(_tags(upgrade).get("TECH_LEVEL", 2))
            player.tavern_tier = max(1, next_tier - 1)
            player.up_cost = int(_tags(upgrade).get("COST", player.up_cost))
        max_entity_id = max(_entity_map(before), default=1000)
        game.tavern._uid_counter = max(1000, max_entity_id + 1000)
        game.players_ready = {0: False, 1: False}
        return game
    finally:
        random.setstate(random_state)


def _canonical_item(
    *,
    entity_id: int | None,
    internal_id: str,
    position: int,
    attack: int | None = None,
    health: int | None = None,
    damage: int | None = None,
) -> dict[str, Any]:
    return {
        "entity_id": entity_id,
        "internal_card_id": internal_id,
        "position": position,
        "attack": attack,
        "health": health,
        "damage": damage,
    }


def canonical_simulator_player(game: Game) -> dict[str, Any]:
    player = game.players[0]
    board = [
        _canonical_item(
            entity_id=unit.uid,
            internal_id=str(unit.card_id),
            position=index + 1,
            attack=unit.cur_atk,
            health=unit.max_hp,
            damage=max(0, unit.max_hp - unit.cur_hp),
        )
        for index, unit in enumerate(player.board)
    ]
    hand = []
    for index, card in enumerate(player.hand):
        if card.unit:
            hand.append(
                _canonical_item(
                    entity_id=card.uid,
                    internal_id=str(card.unit.card_id),
                    position=index + 1,
                    attack=card.unit.cur_atk,
                    health=card.unit.max_hp,
                    damage=max(0, card.unit.max_hp - card.unit.cur_hp),
                )
            )
        elif card.spell:
            hand.append(
                _canonical_item(
                    entity_id=card.uid,
                    internal_id=str(card.spell.card_id),
                    position=index + 1,
                )
            )
    store = []
    for index, item in enumerate(player.store):
        if item.unit:
            store.append(
                _canonical_item(
                    entity_id=item.unit.uid,
                    internal_id=str(item.unit.card_id),
                    position=index + 1,
                    attack=item.unit.cur_atk,
                    health=item.unit.max_hp,
                    damage=max(0, item.unit.max_hp - item.unit.cur_hp),
                )
            )
        elif item.spell:
            store.append(
                _canonical_item(
                    entity_id=None,
                    internal_id=str(item.spell.card_id),
                    position=index + 1,
                )
            )
    return {
        "tavern_tier": player.tavern_tier,
        "upgrade_cost": player.up_cost,
        "board": board,
        "hand": hand,
        "shop": store,
    }


def canonical_trace_player(
    snapshot: dict[str, Any], decision: ReplayDecision, contract: dict[str, Any]
) -> dict[str, Any]:
    aliases = _alias_map(contract)

    def convert(entities: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
        result = []
        for entity in entities:
            tags = _tags(entity)
            alias = aliases.get(entity.get("card_id"))
            result.append(
                {
                    "entity_id": entity.get("entity_id"),
                    "live_card_id": entity.get("card_id"),
                    "internal_card_id": alias["internal_id"] if alias else None,
                    "position": _position(entity),
                    "attack": tags.get("ATK"),
                    "health": tags.get("HEALTH"),
                    "damage": tags.get("DAMAGE", 0) if "HEALTH" in tags else None,
                }
            )
        return result

    controller = int(decision.player_controller)
    upgrade = _active_upgrade(snapshot, controller)
    return {
        "tavern_tier": (
            max(1, int(_tags(upgrade).get("TECH_LEVEL", 2)) - 1) if upgrade is not None else None
        ),
        "upgrade_cost": (
            int(_tags(upgrade).get("COST"))
            if upgrade is not None and _tags(upgrade).get("COST") is not None
            else None
        ),
        "board": convert(_zone_entities(snapshot, controller, "PLAY")),
        "hand": convert(_zone_entities(snapshot, controller, "HAND")),
        "shop": convert(_zone_entities(snapshot, decision.shop_controller, "PLAY")),
    }


def replay_transition(
    transition: dict[str, Any],
    decision: ReplayDecision,
    contract: dict[str, Any],
    profile: dict[str, Any],
    *,
    seed: int,
) -> dict[str, Any]:
    if not decision.eligible or decision.simulator_action is None:
        raise ValueError("cannot replay an ineligible transition")
    game = _hydrate_game(transition, decision, contract, profile, seed)
    simulator_before = canonical_simulator_player(game)
    random_state = random.getstate()
    random.seed(seed)
    try:
        accepted, _, info = game.step(0, decision.simulator_action, **decision.action_kwargs)
    finally:
        random.setstate(random_state)
    return {
        "schema_version": REPLAY_RESULT_SCHEMA_VERSION,
        "transition_index": transition["transition_index"],
        "session_index": transition["session_index"],
        "action_type": decision.action_type,
        "comparison_mode": decision.comparison_mode,
        "decision": decision.to_dict(),
        "accepted": accepted,
        "info": info,
        "trace_before": canonical_trace_player(transition["before"], decision, contract),
        "trace_after": canonical_trace_player(transition["after"], decision, contract),
        "simulator_before": simulator_before,
        "simulator_after": canonical_simulator_player(game),
    }


def summarize_replay_decisions(decisions: Iterable[ReplayDecision]) -> dict[str, Any]:
    decisions = list(decisions)
    eligible = [decision for decision in decisions if decision.eligible]
    return {
        "transitions": len(decisions),
        "eligible_transitions": len(eligible),
        "eligibility_rate": len(eligible) / len(decisions) if decisions else 1.0,
        "eligible_action_counts": dict(
            sorted(Counter(item.action_type for item in eligible).items())
        ),
        "eligible_comparison_mode_counts": dict(
            sorted(Counter(str(item.comparison_mode) for item in eligible).items())
        ),
        "exclusion_reason_counts": dict(
            sorted(
                Counter(
                    reason
                    for decision in decisions
                    if not decision.eligible
                    for reason in decision.reasons
                ).items()
            )
        ),
    }
