"""F0 admission scenarios for current Tier-3 shop minions."""

from hearthstone.engine import card_def
from hearthstone.engine.card_def import AVENGE_REGISTRY
from hearthstone.engine.combat import _execute_avenge
from hearthstone.engine.entities import HandCard, Spell
from hearthstone.engine.enums import CardIDs, MechanicType, SpellIDs, Tags, UnitType
from hearthstone.engine.event_system import EntityRef, Event, EventType, PosRef, Zone


def test_annoy_o_module_has_magnetic_taunt_divine_shield(mock_unit) -> None:
    module = mock_unit(CardIDs.ANNOY_O_MODULE)
    assert module.tags >= {Tags.MAGNETIC, Tags.TAUNT, Tags.DIVINE_SHIELD}


def test_deadly_spore_venomous_is_consumed_after_attack(combat_players) -> None:
    players, boards, combat = combat_players(
        [CardIDs.DEADLY_SPORE], [CardIDs.ROT_HIDE_GNOLL]
    )
    spore, target = boards[0][0], boards[1][0]
    combat.perform_attack(spore, target, players)
    assert target.cur_hp <= 0
    assert Tags.VENOMOUS not in spore.tags


def test_timecapn_hooktail_gains_attack_on_friendly_spell(
    empty_game, player, mock_unit
) -> None:
    hooktail = mock_unit(CardIDs.TIMECAPN_HOOKTAIL, owner_id=player.uid)
    player.board.append(hooktail)
    player.hand.append(
        HandCard(uid=empty_game.tavern.get_next_uid(), spell=Spell.create_from_db(SpellIDs.TAVERN_COIN))
    )
    before = hooktail.cur_atk
    assert empty_game.step(player.uid, "PLAY", hand_index=0)[0]
    assert hooktail.cur_atk == before + 1


def test_wildfire_elemental_cleave_hits_adjacent_targets(combat_players) -> None:
    players, boards, combat = combat_players(
        [CardIDs.WILDFIRE_ELEMENTAL],
        [CardIDs.MICROBOT, CardIDs.MICROBOT, CardIDs.MICROBOT],
    )
    attacker = boards[0][0]
    attacker.perm_hp_add = 20
    attacker.recalc_stats()
    attacker.restore_stats()
    combat.perform_attack(attacker, boards[1][1], players)
    assert all(unit.cur_hp <= 0 for unit in boards[1])


def test_breakout_mastermind_activate_pays_two_and_gets_murloc(
    empty_game, player, mock_unit
) -> None:
    mastermind = mock_unit(CardIDs.BREAKOUT_MASTERMIND, owner_id=player.uid)
    player.board.append(mastermind)
    player.gold = 4
    empty_game.event_manager.process_event(
        Event(
            event_type=EventType.END_OF_TURN,
            source_pos=PosRef(side=player.uid, zone=Zone.HERO, slot=0),
        ),
        {player.uid: player},
        empty_game.tavern.get_next_uid,
        card_pool=empty_game.pool,
    )
    assert player.gold == 2
    drawn = [card.unit for card in player.hand if card.unit]
    assert len(drawn) == 1
    assert UnitType.MURLOC in drawn[0].types or UnitType.ALL in drawn[0].types


def test_dustbone_devastator_avenge_buffs_undead(
    empty_game, player, mock_unit
) -> None:
    devastator = mock_unit(CardIDs.DUSTBONE_DEVASTATOR, owner_id=player.uid)
    undead = mock_unit(CardIDs.RISEN_RIDER, owner_id=player.uid)
    player.board = [devastator, undead]
    effect = AVENGE_REGISTRY[CardIDs.DUSTBONE_DEVASTATOR]
    assert effect.threshold == 3
    before = (undead.cur_atk, undead.cur_hp)
    _execute_avenge(devastator, effect, {player.uid: player}, player.uid)
    assert (undead.cur_atk, undead.cur_hp) == (before[0] + 2, before[1] + 1)


def test_mama_mrrglton_buffs_other_murloc_attack(
    empty_game, player, mock_unit
) -> None:
    ally = mock_unit(CardIDs.TAD, owner_id=player.uid)
    mama = mock_unit(CardIDs.MAMA_MRRGLTON, owner_id=player.uid)
    player.board.append(ally)
    player.hand.append(HandCard(uid=mama.uid, unit=mama))
    before = (ally.cur_atk, ally.cur_hp)
    assert empty_game.step(player.uid, "PLAY", hand_index=0)[0]
    assert (ally.cur_atk, ally.cur_hp) == (before[0] + 3, before[1])


def test_meteorite_crasher_buffs_after_other_elemental_sold(
    empty_game, player, mock_unit
) -> None:
    crasher = mock_unit(CardIDs.METEORITE_CRASHER, owner_id=player.uid)
    elemental = mock_unit(CardIDs.CRACKLING_CYCLONE, owner_id=player.uid)
    player.board = [crasher, elemental]
    before = (crasher.cur_atk, crasher.cur_hp)
    assert empty_game.step(player.uid, "SELL", index=1)[0]
    assert (crasher.cur_atk, crasher.cur_hp) == (before[0] + 4, before[1] + 4)


def test_papa_mrrglton_buffs_other_murloc_health(
    empty_game, player, mock_unit
) -> None:
    ally = mock_unit(CardIDs.TAD, owner_id=player.uid)
    papa = mock_unit(CardIDs.PAPA_MRRGLTON, owner_id=player.uid)
    player.board.append(ally)
    player.hand.append(HandCard(uid=papa.uid, unit=papa))
    before = (ally.cur_atk, ally.cur_hp)
    assert empty_game.step(player.uid, "PLAY", hand_index=0)[0]
    assert (ally.cur_atk, ally.cur_hp) == (before[0], before[1] + 3)


def test_private_investigator_activate_banks_gold_next_turn(
    empty_game, player, mock_unit
) -> None:
    investigator = mock_unit(CardIDs.PRIVATE_INVESTIGATOR, owner_id=player.uid)
    player.board.append(investigator)
    player.gold = 3
    empty_game.event_manager.process_event(
        Event(
            event_type=EventType.END_OF_TURN,
            source_pos=PosRef(side=player.uid, zone=Zone.HERO, slot=0),
        ),
        {player.uid: player},
        empty_game.tavern.get_next_uid,
    )
    assert player.gold == 2
    assert player.gold_next_turn == 2


def test_sand_swirler_battlecry_increases_elemental_attack_bonus(
    empty_game, player, mock_unit
) -> None:
    swirler = mock_unit(CardIDs.SAND_SWIRLER, owner_id=player.uid)
    player.hand.append(HandCard(uid=swirler.uid, unit=swirler))
    before = player.mechanics.get_stat(MechanicType.ELEMENTAL_BUFF_BONUS)
    assert empty_game.step(player.uid, "PLAY", hand_index=0)[0]
    after = player.mechanics.get_stat(MechanicType.ELEMENTAL_BUFF_BONUS)
    assert after == (before[0] + 2, before[1])


def test_deep_sea_angler_rally_casts_spell_on_right(
    empty_game, player, mock_unit, monkeypatch
) -> None:
    angler = mock_unit(CardIDs.DEEP_SEA_ANGLER, owner_id=player.uid)
    target = mock_unit(CardIDs.TRENCH_FIGHTER, owner_id=player.uid)
    player.board = [angler, target]
    monkeypatch.setattr(card_def, "_random_tavern_spell_id", lambda: SpellIDs.BANANA)
    before = (target.cur_atk, target.cur_hp)
    empty_game.event_manager.process_event(
        Event(
            event_type=EventType.ATTACK_DECLARED,
            source=EntityRef(angler.uid),
            source_pos=PosRef(side=player.uid, zone=Zone.BOARD, slot=0),
        ),
        {player.uid: player},
        empty_game.tavern.get_next_uid,
    )
    assert (target.cur_atk, target.cur_hp) == (before[0] + 2, before[1] + 2)


def test_waverider_buffs_leftmost_naga_and_grants_windfury(
    empty_game, player, mock_unit
) -> None:
    waverider = mock_unit(CardIDs.WAVERIDER, owner_id=player.uid)
    left = mock_unit(CardIDs.TRENCH_FIGHTER, owner_id=player.uid)
    right = mock_unit(CardIDs.DEEP_SEA_ANGLER, owner_id=player.uid)
    player.board = [waverider, left, right]
    before_waverider = (waverider.cur_atk, waverider.cur_hp)
    before_left = (left.cur_atk, left.cur_hp)
    before_right = (right.cur_atk, right.cur_hp)
    empty_game.event_manager.process_event(
        Event(
            event_type=EventType.START_OF_COMBAT,
            source_pos=PosRef(side=player.uid, zone=Zone.HERO, slot=-1),
        ),
        {player.uid: player},
        empty_game.tavern.get_next_uid,
    )
    assert (waverider.cur_atk, waverider.cur_hp) == (
        before_waverider[0] + 3,
        before_waverider[1] + 3,
    )
    assert waverider.has_windfury
    assert (left.cur_atk, left.cur_hp) == before_left
    assert (right.cur_atk, right.cur_hp) == before_right
