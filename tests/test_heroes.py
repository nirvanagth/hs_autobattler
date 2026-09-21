"""F2 reference hero, armor, cooldown, and targeting scenarios."""

import pytest

from hearthstone.engine.entities import StoreItem, Unit
from hearthstone.engine.enums import CardIDs, SpellIDs
from hearthstone.engine.game import Game
from hearthstone.engine.heroes import HERO_DB
from hearthstone.engine.lobby import LobbyGame
from hearthstone.env.lobby_env import BattlegroundsLobbyEnv


HERO_IDS = [
    "BULWARK",
    "QUARTERMASTER",
    "SCHOLAR",
    "BLOOD_BROKER",
    "INVESTOR",
    "GILDER",
    "TRAINER",
    "SHOP_SMITH",
]


def hero_game(hero_id: str) -> tuple[Game, object]:
    game = Game(max_tier=3, behavior_version=7, hero_ids=[hero_id, "BULWARK"])
    return game, game.players[0]


def test_reference_roster_has_eight_unique_mechanic_heroes() -> None:
    assert list(HERO_DB) == HERO_IDS
    assert len({hero.power_kind for hero in HERO_DB.values()}) == 8


def test_armor_absorbs_damage_before_health_and_copies() -> None:
    _, player = hero_game("BULWARK")
    starting_armor = HERO_DB["BULWARK"].armor
    assert (player.health, player.armor) == (30, starting_armor)
    assert player.take_damage(6) == (6, 0)
    remaining_armor = starting_armor - 6
    assert (player.health, player.armor) == (30, remaining_armor)
    assert player.take_damage(remaining_armor + 5) == (remaining_armor, 5)
    assert (player.health, player.armor) == (25, 0)
    copied = player.combat_copy()
    assert copied.hero_id == "BULWARK"
    assert copied.armor == 0


def test_heroes_are_rejected_before_behavior_v7() -> None:
    with pytest.raises(ValueError, match="behavior_version"):
        Game(behavior_version=6, hero_ids=["BULWARK", "TRAINER"])


def test_lobby_assigns_all_eight_heroes_and_armor() -> None:
    lobby = LobbyGame(behavior_version=7, hero_ids=HERO_IDS, seed=5)
    assert [player.hero_id for player in lobby.players] == HERO_IDS
    assert [player.armor for player in lobby.players] == [
        HERO_DB[hero_id].armor for hero_id in HERO_IDS
    ]


def test_quartermaster_grants_nonstacking_free_refresh_each_turn() -> None:
    game, player = hero_game("QUARTERMASTER")
    assert player.free_refreshes == 1
    game.tavern.start_turn(player, 2)
    assert player.free_refreshes == 1


def test_scholar_refunds_gold_after_upgrade() -> None:
    game, player = hero_game("SCHOLAR")
    player.gold = 10
    cost = player.up_cost
    assert game.step(0, "UPGRADE")[0]
    assert player.gold == 10 - cost + 1


def test_blood_broker_uses_armor_and_adds_coin() -> None:
    game, player = hero_game("BLOOD_BROKER")
    armor_before = player.armor
    assert game.step(0, "HERO_POWER")[0]
    assert player.armor == armor_before - 1
    assert player.health == 30
    assert [card.spell.card_id for card in player.hand if card.spell] == [
        SpellIDs.TAVERN_COIN
    ]
    assert not game.step(0, "HERO_POWER")[0]


def test_investor_enforces_turn_limit_and_two_turn_cooldown() -> None:
    game, player = hero_game("INVESTOR")
    player.gold = 5
    assert game.step(0, "HERO_POWER")[0]
    assert (player.gold, player.gold_next_turn) == (4, 2)
    game.tavern.start_turn(player, 2)
    assert not game.step(0, "HERO_POWER")[0]
    game.tavern.start_turn(player, 3)
    assert game.step(0, "HERO_POWER")[0]


def test_gilder_is_targeted_and_once_per_game() -> None:
    game, player = hero_game("GILDER")
    unit = Unit.create_from_db(CardIDs.CORD_PULLER, 5001, player.uid)
    player.board = [unit]
    assert not game.step(0, "HERO_POWER")[0]
    assert game.step(0, "HERO_POWER", target_index=0)[0]
    assert unit.is_golden
    game.tavern.start_turn(player, 2)
    player.board.append(Unit.create_from_db(CardIDs.RISEN_RIDER, 5002, player.uid))
    assert not game.step(0, "HERO_POWER", target_index=1)[0]


def test_trainer_and_shop_smith_validate_zones_and_costs() -> None:
    trainer_game, trainer = hero_game("TRAINER")
    board_unit = Unit.create_from_db(CardIDs.CORD_PULLER, 6001, trainer.uid)
    trainer.board = [board_unit]
    trainer.gold = 3
    before = (board_unit.cur_atk, board_unit.cur_hp)
    assert trainer_game.step(0, "HERO_POWER", target_index=0)[0]
    assert (board_unit.cur_atk, board_unit.cur_hp) == (
        before[0] + 1,
        before[1] + 1,
    )
    assert trainer.gold == 2

    smith_game, smith = hero_game("SHOP_SMITH")
    shop_unit = Unit.create_from_db(CardIDs.CORD_PULLER, 6002, smith.uid)
    smith.store.clear()
    smith.store.append(StoreItem(unit=shop_unit))
    smith.gold = 3
    before_shop = (shop_unit.cur_atk, shop_unit.cur_hp)
    assert smith_game.step(0, "HERO_POWER", target_index=0)[0]
    assert (shop_unit.cur_atk, shop_unit.cur_hp) == (
        before_shop[0] + 2,
        before_shop[1] + 2,
    )


def test_hero_lobby_observation_and_action_contract_is_versioned() -> None:
    legacy = BattlegroundsLobbyEnv(behavior_version=6)
    hero_env = BattlegroundsLobbyEnv(behavior_version=7, hero_ids=HERO_IDS)
    legacy_obs, _ = legacy.reset(seed=12)
    hero_obs, _ = hero_env.reset(seed=12)
    assert legacy_obs.shape == (2958,)
    assert legacy.action_space.n == 34
    assert hero_obs.shape == (2984,)
    assert hero_env.action_space.n == 35
    contract = hero_env.lobby_environment_contract
    assert contract["name"] == "hsbg_8p_heroes_research"
    assert contract["observation_schema_version"] == 2
    assert contract["action_schema_version"] == 2
    assert contract["hero_roster"] == HERO_IDS
    assert len(contract["hero_registry_sha256"]) == 64


def test_no_target_hero_power_is_action_34() -> None:
    env = BattlegroundsLobbyEnv(
        behavior_version=7,
        hero_ids=["BLOOD_BROKER", *HERO_IDS[1:]],
    )
    env.reset(seed=13)
    player = env.game.players[0]
    assert env.action_masks()[34]
    armor_before = player.armor
    _, _, terminated, truncated, _ = env.step(34)
    assert not terminated and not truncated
    assert player.armor == armor_before - 1
    assert not env.action_masks()[34]


def test_board_target_hero_power_uses_two_step_action_contract() -> None:
    env = BattlegroundsLobbyEnv(
        behavior_version=7,
        hero_ids=["GILDER", *HERO_IDS[1:]],
    )
    env.reset(seed=14)
    player = env.game.players[0]
    unit = Unit.create_from_db(CardIDs.CORD_PULLER, 7001, player.uid)
    player.board = [unit]
    assert env.action_masks()[34]
    env.step(34)
    mask = env.action_masks()
    assert mask[2] and mask.sum() == 1
    env.step(2)
    assert unit.is_golden


def test_store_target_hero_power_masks_only_unit_slots() -> None:
    env = BattlegroundsLobbyEnv(
        behavior_version=7,
        hero_ids=["SHOP_SMITH", *HERO_IDS[1:]],
    )
    env.reset(seed=15)
    assert env.action_masks()[34]
    env.step(34)
    mask = env.action_masks()
    unit_slots = sum(item.unit is not None for item in env.game.players[0].store[:7])
    assert int(mask[9:16].sum()) == unit_slots
    assert int(mask.sum()) == unit_slots
