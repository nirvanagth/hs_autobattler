"""F0 admission scenarios for current Tier-2 shop minions."""

from hearthstone.engine.entities import HandCard, Spell, StoreItem
from hearthstone.engine.enums import CardIDs, MechanicType, SpellIDs, UnitType
from hearthstone.engine.event_system import EntityRef, Event, EventType, PosRef, Zone


def test_mechagnome_interpreter_buffs_played_mech(empty_game, player, mock_unit) -> None:
    interpreter = mock_unit(CardIDs.MECHAGNOME_INTERPRETER, owner_id=player.uid)
    player.hand.append(HandCard(uid=interpreter.uid, unit=interpreter))
    before = (interpreter.cur_atk, interpreter.cur_hp)
    assert empty_game.step(player.uid, "PLAY", hand_index=0)[0]
    assert (interpreter.cur_atk, interpreter.cur_hp) == (before[0] + 2, before[1] + 1)


def test_humming_bird_buffs_friendly_beasts_at_combat_start(
    empty_game, player, mock_unit
) -> None:
    bird = mock_unit(CardIDs.HUMMING_BIRD, owner_id=player.uid)
    beast = mock_unit(CardIDs.MANASABER, owner_id=player.uid)
    player.board = [bird, beast]
    before = [(unit.cur_atk, unit.cur_hp) for unit in player.board]
    empty_game.event_manager.process_event(
        Event(
            event_type=EventType.START_OF_COMBAT,
            source_pos=PosRef(side=player.uid, zone=Zone.BOARD, slot=-1),
        ),
        {player.uid: player},
        empty_game.tavern.get_next_uid,
    )
    assert [(unit.cur_atk, unit.cur_hp) for unit in player.board] == [
        (before[0][0] + 1, before[0][1]),
        (before[1][0] + 1, before[1][1]),
    ]


def test_nerubian_deathswarmer_buffs_all_friendly_undead(
    empty_game, player, mock_unit
) -> None:
    ally = mock_unit(CardIDs.RISEN_RIDER, owner_id=player.uid)
    deathswarmer = mock_unit(CardIDs.NERUBIAN_DEATHSWARMER, owner_id=player.uid)
    player.board.append(ally)
    player.hand.append(HandCard(uid=deathswarmer.uid, unit=deathswarmer))
    ally_atk = ally.cur_atk
    assert empty_game.step(player.uid, "PLAY", hand_index=0)[0]
    assert ally.cur_atk == ally_atk + 1
    assert deathswarmer.cur_atk == deathswarmer.base_atk + 1


def test_oozeling_gladiator_adds_two_slimy_shields(
    empty_game, player, mock_unit
) -> None:
    gladiator = mock_unit(CardIDs.OOZELING_GLADIATOR, owner_id=player.uid)
    player.hand.append(HandCard(uid=gladiator.uid, unit=gladiator))
    assert empty_game.step(player.uid, "PLAY", hand_index=0)[0]
    assert [card.spell.card_id for card in player.hand if card.spell] == [
        SpellIDs.SLIMY_SHIELD,
        SpellIDs.SLIMY_SHIELD,
    ]


def test_sellemental_sell_adds_water_droplet(empty_game, player, mock_unit) -> None:
    sellemental = mock_unit(CardIDs.SELLEMENTAL, owner_id=player.uid)
    player.board.append(sellemental)
    assert empty_game.step(player.uid, "SELL", index=0)[0]
    assert [card.unit.card_id for card in player.hand if card.unit] == [
        CardIDs.WATER_DROPLET
    ]


def test_tad_sell_draws_murloc_from_pool(empty_game, player, mock_unit) -> None:
    tad = mock_unit(CardIDs.TAD, owner_id=player.uid)
    player.board.append(tad)
    assert empty_game.step(player.uid, "SELL", index=0)[0]
    drawn = [card.unit for card in player.hand if card.unit]
    assert len(drawn) == 1
    assert UnitType.MURLOC in drawn[0].types or UnitType.ALL in drawn[0].types


def test_mind_muck_consumes_shop_for_friendly_demon(
    empty_game, player, mock_unit
) -> None:
    ally = mock_unit(CardIDs.WRATH_WEAVER, owner_id=player.uid)
    muck = mock_unit(CardIDs.MIND_MUCK, owner_id=player.uid)
    food = mock_unit(CardIDs.CRACKLING_CYCLONE, owner_id=player.uid)
    player.board.append(ally)
    player.hand.append(HandCard(uid=muck.uid, unit=muck))
    player.store.clear()
    player.store.append(StoreItem(unit=food))
    before_total = (ally.cur_atk + muck.cur_atk, ally.cur_hp + muck.cur_hp)
    assert empty_game.step(player.uid, "PLAY", hand_index=0)[0]
    assert not player.store
    after_total = (
        sum(unit.cur_atk for unit in player.board),
        sum(unit.cur_hp for unit in player.board),
    )
    # Mind Muck contributes the consumed 2/1, while Wrath Weaver also gains
    # 2/1 from the friendly Demon play. The random recipient does not matter.
    assert after_total == (
        before_total[0] + food.cur_atk + 2,
        before_total[1] + food.cur_hp + 1,
    )


def test_ancestral_automaton_handler_scales_when_summon_event_is_emitted(
    empty_game, player, mock_unit
) -> None:
    first = mock_unit(CardIDs.ANCESTRAL_AUTOMATON, owner_id=player.uid)
    second = mock_unit(CardIDs.ANCESTRAL_AUTOMATON, owner_id=player.uid)
    player.board.append(first)
    player.board.append(second)
    first_before = (first.cur_atk, first.cur_hp)
    second_before = (second.cur_atk, second.cur_hp)
    empty_game.event_manager.process_event(
        Event(
            event_type=EventType.MINION_SUMMONED,
            source=EntityRef(second.uid),
            source_pos=PosRef(side=player.uid, zone=Zone.BOARD, slot=1),
        ),
        {player.uid: player},
        empty_game.tavern.get_next_uid,
    )
    assert (first.cur_atk, first.cur_hp) == (first_before[0] + 3, first_before[1] + 2)
    assert (second.cur_atk, second.cur_hp) == (
        second_before[0] + 3,
        second_before[1] + 2,
    )


def test_metallic_hunter_deathrattle_adds_pointy_arrow(combat_players) -> None:
    players, boards, combat = combat_players(
        [CardIDs.METALLIC_HUNTER], [CardIDs.MICROBOT]
    )
    boards[0][0].cur_hp = 0
    combat.cleanup_dead(boards, [0, 0], players)
    assert [card.spell.card_id for card in players[0].hand if card.spell] == [
        SpellIDs.POINTY_ARROW
    ]


def test_thousandth_paper_drake_attack_updates_elemental_mechanic(
    combat_players,
) -> None:
    players, boards, combat = combat_players(
        [CardIDs.THOUSANDTH_PAPER_DRAKE], [CardIDs.MICROBOT]
    )
    drake = boards[0][0]
    before = players[0].mechanics.get_stat(MechanicType.ELEMENTAL_BUFF_BONUS)
    combat.event_manager.process_event(
        Event(
            event_type=EventType.ATTACK_DECLARED,
            source=EntityRef(drake.uid),
            source_pos=PosRef(side=players[0].uid, zone=Zone.BOARD, slot=0),
        ),
        players,
        combat.get_uid,
    )
    after = players[0].mechanics.get_stat(MechanicType.ELEMENTAL_BUFF_BONUS)
    assert after == (before[0] + 1, before[1])


def test_lava_lurker_buffs_itself_when_targeted_by_spell(
    empty_game, player, mock_unit
) -> None:
    lurker = mock_unit(CardIDs.LAVA_LURKER, owner_id=player.uid)
    player.board.append(lurker)
    player.hand.append(HandCard(uid=9001, spell=Spell.create_from_db(SpellIDs.BANANA)))
    before = (lurker.cur_atk, lurker.cur_hp)
    assert empty_game.step(player.uid, "PLAY", hand_index=0, target_index=0)[0]
    assert (lurker.cur_atk, lurker.cur_hp) == (before[0] + 3, before[1] + 3)


def test_thaumaturgist_additional_buff_fires_every_third_spell(
    empty_game, player, mock_unit
) -> None:
    thaumaturgist = mock_unit(CardIDs.THAUMATURGIST, owner_id=player.uid)
    player.board.append(thaumaturgist)
    before = (thaumaturgist.cur_atk, thaumaturgist.cur_hp)
    for _ in range(3):
        player.hand.append(
            HandCard(uid=empty_game.tavern.get_next_uid(), spell=Spell.create_from_db(SpellIDs.BANANA))
        )
        assert empty_game.step(player.uid, "PLAY", hand_index=0, target_index=0)[0]
    assert (thaumaturgist.cur_atk, thaumaturgist.cur_hp) == (
        before[0] + 10,
        before[1] + 10,
    )
