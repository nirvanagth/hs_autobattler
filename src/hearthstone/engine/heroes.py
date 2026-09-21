"""Versioned reference heroes used to validate hero-system mechanics."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from enum import Enum
from typing import TYPE_CHECKING, Any

from .entities import HandCard, Spell
from .enums import SpellIDs

if TYPE_CHECKING:
    from .entities import Player


HERO_SCHEMA_VERSION = 1


class HeroPowerTarget(str, Enum):
    NONE = "none"
    FRIENDLY_BOARD = "friendly_board"
    FRIENDLY_STORE = "friendly_store"


@dataclass(frozen=True)
class HeroDef:
    hero_id: str
    name: str
    armor: int
    power_kind: str
    target: HeroPowerTarget = HeroPowerTarget.NONE
    cost: int = 0
    cooldown: int = 0
    once_per_game: bool = False
    params: dict[str, Any] | None = None


HERO_DB: dict[str, HeroDef] = {
    "BULWARK": HeroDef("BULWARK", "Bulwark", 25, "PASSIVE_ARMOR"),
    "QUARTERMASTER": HeroDef(
        "QUARTERMASTER", "Quartermaster", 16, "PASSIVE_FREE_REFRESH"
    ),
    "SCHOLAR": HeroDef("SCHOLAR", "Tavern Scholar", 3, "PASSIVE_UPGRADE_GOLD"),
    "BLOOD_BROKER": HeroDef(
        "BLOOD_BROKER",
        "Blood Broker",
        12,
        "BLOOD_FOR_COIN",
        cooldown=1,
        params={"damage": 1, "coins": 1},
    ),
    "INVESTOR": HeroDef(
        "INVESTOR",
        "Patient Investor",
        3,
        "BANK_GOLD",
        cost=1,
        cooldown=2,
        params={"gold_next_turn": 2},
    ),
    "GILDER": HeroDef(
        "GILDER",
        "The Gilder",
        7,
        "MAKE_GOLDEN",
        target=HeroPowerTarget.FRIENDLY_BOARD,
        once_per_game=True,
    ),
    "TRAINER": HeroDef(
        "TRAINER",
        "Battle Trainer",
        0,
        "BUFF_BOARD",
        target=HeroPowerTarget.FRIENDLY_BOARD,
        cost=1,
        params={"atk": 1, "hp": 1},
    ),
    "SHOP_SMITH": HeroDef(
        "SHOP_SMITH",
        "Shop Smith",
        10,
        "BUFF_STORE",
        target=HeroPowerTarget.FRIENDLY_STORE,
        cost=1,
        cooldown=1,
        params={"atk": 2, "hp": 2},
    ),
}
HERO_IDS = tuple(HERO_DB)
HERO_ID_TO_INDEX = {hero_id: index + 1 for index, hero_id in enumerate(HERO_IDS)}


def hero_registry_payload() -> dict[str, Any]:
    return {
        "schema_version": HERO_SCHEMA_VERSION,
        "heroes": {
            hero_id: {
                "name": hero.name,
                "armor": hero.armor,
                "power_kind": hero.power_kind,
                "target": hero.target.value,
                "cost": hero.cost,
                "cooldown": hero.cooldown,
                "once_per_game": hero.once_per_game,
                "params": hero.params or {},
            }
            for hero_id, hero in HERO_DB.items()
        },
    }


def hero_registry_sha256() -> str:
    encoded = json.dumps(
        hero_registry_payload(), sort_keys=True, separators=(",", ":")
    ).encode()
    return hashlib.sha256(encoded).hexdigest()


def assign_hero(player: Player, hero_id: str) -> None:
    hero = HERO_DB[hero_id]
    player.hero.hero_id = hero_id
    player.hero.armor = hero.armor
    player.hero.power_cooldown = 0
    player.hero.power_uses = 0
    player.hero.power_used_this_turn = False


def on_start_turn(player: Player) -> None:
    player.hero.power_used_this_turn = False
    player.hero.power_cooldown = max(0, player.hero.power_cooldown - 1)
    hero = HERO_DB.get(player.hero.hero_id)
    if hero and hero.power_kind == "PASSIVE_FREE_REFRESH":
        player.free_refreshes = max(1, player.free_refreshes)


def on_tavern_upgrade(player: Player) -> None:
    hero = HERO_DB.get(player.hero.hero_id)
    if hero and hero.power_kind == "PASSIVE_UPGRADE_GOLD":
        player.gold += 1


def _validate_target(player: Player, hero: HeroDef, target_index: int) -> bool:
    if hero.target == HeroPowerTarget.NONE:
        return target_index == -1
    if hero.target == HeroPowerTarget.FRIENDLY_BOARD:
        if not 0 <= target_index < len(player.board):
            return False
        return not (
            hero.power_kind == "MAKE_GOLDEN" and player.board[target_index].is_golden
        )
    if hero.target == HeroPowerTarget.FRIENDLY_STORE:
        return 0 <= target_index < len(player.store) and player.store[target_index].unit is not None
    return False


def hero_power_available(player: Player) -> bool:
    hero = HERO_DB.get(player.hero.hero_id)
    if hero is None or hero.power_kind.startswith("PASSIVE_"):
        return False
    if player.hero.power_used_this_turn or player.hero.power_cooldown > 0:
        return False
    if hero.once_per_game and player.hero.power_uses > 0:
        return False
    if player.gold < hero.cost:
        return False
    if hero.power_kind == "BLOOD_FOR_COIN" and len(player.hand) >= 10:
        return False
    if hero.target == HeroPowerTarget.FRIENDLY_BOARD:
        if hero.power_kind == "MAKE_GOLDEN":
            return any(not unit.is_golden for unit in player.board)
        return bool(player.board)
    if hero.target == HeroPowerTarget.FRIENDLY_STORE:
        return any(item.unit is not None for item in player.store)
    return True


def use_hero_power(player: Player, target_index: int = -1) -> tuple[bool, str]:
    hero = HERO_DB.get(player.hero.hero_id)
    if hero is None or hero.power_kind.startswith("PASSIVE_"):
        return False, "Hero has no active power"
    if player.hero.power_used_this_turn:
        return False, "Hero power already used this turn"
    if player.hero.power_cooldown > 0:
        return False, "Hero power is on cooldown"
    if hero.once_per_game and player.hero.power_uses > 0:
        return False, "Hero power already used this game"
    if player.gold < hero.cost:
        return False, "Not enough gold"
    if not _validate_target(player, hero, target_index):
        return False, "Invalid hero power target"

    params = hero.params or {}
    if hero.power_kind == "BLOOD_FOR_COIN":
        player.take_damage(int(params["damage"]))
        for _ in range(int(params["coins"])):
            if len(player.hand) < 10:
                player.hand.append(
                    HandCard(
                        uid=-(player.hero.power_uses + 1),
                        spell=Spell.create_from_db(SpellIDs.TAVERN_COIN),
                    )
                )
    elif hero.power_kind == "BANK_GOLD":
        player.gold_next_turn += int(params["gold_next_turn"])
    elif hero.power_kind == "MAKE_GOLDEN":
        unit = player.board[target_index]
        if unit.is_golden:
            return False, "Target is already golden"
        unit.is_golden = True
        unit.base_atk *= 2
        unit.base_hp *= 2
        unit.recalc_stats()
        unit.restore_stats()
    elif hero.power_kind == "BUFF_BOARD":
        unit = player.board[target_index]
        unit.perm_atk_add += int(params["atk"])
        unit.perm_hp_add += int(params["hp"])
        unit.recalc_stats()
    elif hero.power_kind == "BUFF_STORE":
        unit = player.store[target_index].unit
        assert unit is not None
        unit.perm_atk_add += int(params["atk"])
        unit.perm_hp_add += int(params["hp"])
        unit.recalc_stats()
    else:
        return False, f"Unknown hero power: {hero.power_kind}"

    player.gold -= hero.cost
    player.hero.power_used_this_turn = True
    player.hero.power_uses += 1
    player.hero.power_cooldown = hero.cooldown
    return True, f"Used {hero.name} hero power"
