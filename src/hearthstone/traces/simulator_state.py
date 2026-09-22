"""Normalize simulator state into the Power.log conformance schema."""

from __future__ import annotations

from hearthstone.engine.entities import Player, Unit
from hearthstone.engine.lobby import LobbyGame


def _card_id(value) -> str:
    return str(getattr(value, "value", value))


def _unit_entity(unit: Unit, controller: int, zone: str, position: int) -> dict:
    return {
        "entity_id": unit.uid,
        "card_id": _card_id(unit.card_id),
        "tags": {
            "CONTROLLER": controller,
            "ZONE": zone,
            "ZONE_POSITION": position,
            "ATK": unit.cur_atk,
            "HEALTH": unit.max_hp,
            "DAMAGE": max(0, unit.max_hp - unit.cur_hp),
            "TECH_LEVEL": unit.tier,
        },
    }


def normalize_player(player: Player) -> list[dict]:
    entities = [
        {
            "entity_id": -(player.uid + 1),
            "card_id": player.hero_id if player.hero_id != "NONE" else None,
            "tags": {
                "CONTROLLER": player.uid,
                "PLAYER_ID": player.uid,
                "ZONE": "HERO",
                "ZONE_POSITION": 0,
                "HEALTH": player.health,
                "ARMOR": player.armor,
                "TECH_LEVEL": player.tavern_tier,
            },
        }
    ]
    entities.extend(
        _unit_entity(unit, player.uid, "PLAY", index + 1)
        for index, unit in enumerate(player.board)
    )
    for index, card in enumerate(player.hand):
        if card.unit:
            entities.append(_unit_entity(card.unit, player.uid, "HAND", index + 1))
        elif card.spell:
            entities.append(
                {
                    "entity_id": card.uid,
                    "card_id": _card_id(card.spell.card_id),
                    "tags": {
                        "CONTROLLER": player.uid,
                        "ZONE": "HAND",
                        "ZONE_POSITION": index + 1,
                        "COST": card.spell.cost,
                        "TECH_LEVEL": card.spell.tier,
                    },
                }
            )
    for index, item in enumerate(player.store):
        if item.unit:
            entities.append(_unit_entity(item.unit, player.uid, "SHOP", index + 1))
        elif item.spell:
            entities.append(
                {
                    "entity_id": -(100000 + player.uid * 100 + index),
                    "card_id": _card_id(item.spell.card_id),
                    "tags": {
                        "CONTROLLER": player.uid,
                        "ZONE": "SHOP",
                        "ZONE_POSITION": index + 1,
                        "COST": item.spell.cost,
                        "TECH_LEVEL": item.spell.tier,
                    },
                }
            )
    return entities


def normalize_lobby(lobby: LobbyGame) -> dict:
    return {
        "entities": [
            entity
            for player in sorted(lobby.players, key=lambda item: item.uid)
            for entity in normalize_player(player)
        ]
    }
