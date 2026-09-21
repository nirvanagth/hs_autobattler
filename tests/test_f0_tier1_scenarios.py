"""F0 admission scenarios for every current Tier-1 shop minion."""

from hearthstone.engine.entities import HandCard, Spell
from hearthstone.engine.enums import CardIDs, MechanicType, SpellIDs, Tags
from hearthstone.engine.event_system import EntityRef, Event, EventType, PosRef, Zone


def test_cord_puller_deathrattle_summons_microbot(combat_players) -> None:
    players, boards, combat = combat_players([CardIDs.CORD_PULLER], [CardIDs.MICROBOT])
    boards[0][0].cur_hp = 0
    combat.cleanup_dead(boards, [0, 0], players)
    assert [unit.card_id for unit in boards[0]] == [CardIDs.MICROBOT]


def test_crackling_cyclone_has_combat_keywords(mock_unit) -> None:
    cyclone = mock_unit(CardIDs.CRACKLING_CYCLONE)
    assert cyclone.has_divine_shield
    assert cyclone.has_windfury


def test_flighty_scout_summons_copy_from_hand_at_combat_start(
    empty_game, player, mock_unit
) -> None:
    scout = mock_unit(CardIDs.FLIGHTY_SCOUT, owner_id=player.uid)
    player.hand.append(HandCard(uid=scout.uid, unit=scout))
    empty_game.event_manager.process_event(
        Event(
            event_type=EventType.START_OF_COMBAT,
            source_pos=PosRef(side=player.uid, zone=Zone.HERO, slot=0),
        ),
        {player.uid: player},
        empty_game.tavern.get_next_uid,
    )
    assert [unit.card_id for unit in player.board] == [CardIDs.FLIGHTY_SCOUT]
    assert player.hand[0].unit is scout


def test_harmless_bonehead_deathrattle_summons_two_skeletons(combat_players) -> None:
    players, boards, combat = combat_players(
        [CardIDs.HARMLESS_BONEHEAD], [CardIDs.MICROBOT]
    )
    boards[0][0].cur_hp = 0
    combat.cleanup_dead(boards, [0, 0], players)
    assert [unit.card_id for unit in boards[0]] == [CardIDs.SKELETON] * 2


def test_ominous_seer_battlecry_discounts_spells(empty_game, player, mock_unit) -> None:
    seer = mock_unit(CardIDs.OMINOUS_SEER, owner_id=player.uid)
    player.hand.append(HandCard(uid=seer.uid, unit=seer))
    assert player.spell_discount == 0
    assert empty_game.step(player.uid, "PLAY", hand_index=0)[0]
    assert player.spell_discount == 1


def test_razorfen_geomancer_battlecry_adds_two_gems(
    empty_game, player, mock_unit
) -> None:
    geomancer = mock_unit(CardIDs.RAZORFEN_GEOMANCER, owner_id=player.uid)
    player.hand.append(HandCard(uid=geomancer.uid, unit=geomancer))
    assert empty_game.step(player.uid, "PLAY", hand_index=0)[0]
    assert [card.spell.card_id for card in player.hand if card.spell] == [
        SpellIDs.BLOOD_GEM,
        SpellIDs.BLOOD_GEM,
    ]


def test_risen_rider_has_taunt_and_reborn(mock_unit) -> None:
    rider = mock_unit(CardIDs.RISEN_RIDER)
    assert rider.tags >= {Tags.TAUNT, Tags.REBORN}


def test_river_skipper_sell_draws_tier_one_unit(empty_game, player, mock_unit) -> None:
    skipper = mock_unit(CardIDs.RIVER_SKIPPER, owner_id=player.uid)
    player.board.append(skipper)
    assert empty_game.step(player.uid, "SELL", index=0)[0]
    drawn = [card.unit for card in player.hand if card.unit]
    assert len(drawn) == 1
    assert drawn[0].tier == 1
    assert drawn[0].pool_copies == 1


def test_rot_hide_gnoll_buffs_after_other_friendly_death(combat_players) -> None:
    players, boards, combat = combat_players(
        [CardIDs.ROT_HIDE_GNOLL, CardIDs.MICROBOT], [CardIDs.MICROBOT]
    )
    gnoll = boards[0][0]
    before = gnoll.cur_atk
    boards[0][1].cur_hp = 0
    combat.cleanup_dead(boards, [0, 0], players)
    assert gnoll.cur_atk == before + 1


def test_tusked_camper_rally_uses_current_blood_gem(combat_players) -> None:
    players, boards, combat = combat_players([CardIDs.TUSKED_CAMPER], [CardIDs.MICROBOT])
    camper = boards[0][0]
    players[0].mechanics.modify_stat(MechanicType.BLOOD_GEM, 2, 3)
    before = (camper.cur_atk, camper.cur_hp)
    combat.event_manager.process_event(
        Event(
            event_type=EventType.ATTACK_DECLARED,
            source=EntityRef(camper.uid),
            source_pos=PosRef(side=players[0].uid, zone=Zone.BOARD, slot=0),
        ),
        players,
        combat.get_uid,
    )
    assert (camper.cur_atk, camper.cur_hp) == (before[0] + 3, before[1] + 4)


def test_wrath_weaver_reacts_to_other_demon_play(empty_game, player, mock_unit) -> None:
    weaver = mock_unit(CardIDs.WRATH_WEAVER, owner_id=player.uid)
    demon = mock_unit(CardIDs.PICKY_EATER, owner_id=player.uid)
    player.board.append(weaver)
    player.hand.append(HandCard(uid=demon.uid, unit=demon))
    before = (player.health, weaver.cur_atk, weaver.cur_hp)
    assert empty_game.step(player.uid, "PLAY", hand_index=0)[0]
    assert (player.health, weaver.cur_atk, weaver.cur_hp) == (
        before[0] - 1,
        before[1] + 2,
        before[2] + 1,
    )


def test_molten_rock_battlecry_scales_other_elemental(
    empty_game, player, mock_unit
) -> None:
    ally = mock_unit(CardIDs.CRACKLING_CYCLONE, owner_id=player.uid)
    molten = mock_unit(CardIDs.MOLTEN_ROCK, owner_id=player.uid)
    player.board.append(ally)
    player.hand.append(HandCard(uid=molten.uid, unit=molten))
    before = (ally.cur_atk, ally.cur_hp)
    assert empty_game.step(player.uid, "PLAY", hand_index=0)[0]
    expected = 2 + player.tavern_tier
    assert (ally.cur_atk, ally.cur_hp) == (before[0] + expected, before[1] + expected)


def test_fleeing_fugitive_gains_health_when_targeted_by_spell(
    empty_game, player, mock_unit
) -> None:
    fugitive = mock_unit(CardIDs.FLEEING_FUGITIVE, owner_id=player.uid)
    player.board.append(fugitive)
    spell = Spell.create_from_db(SpellIDs.BANANA)
    player.hand.append(HandCard(uid=9001, spell=spell))
    before = (fugitive.cur_atk, fugitive.cur_hp)
    assert empty_game.step(player.uid, "PLAY", hand_index=0, target_index=0)[0]
    assert (fugitive.cur_atk, fugitive.cur_hp) == (before[0] + 2, before[1] + 3)


def test_mini_myrmidon_copies_first_spellcraft_once_per_turn(
    empty_game, player, mock_unit
) -> None:
    myrmidon = mock_unit(CardIDs.MINI_MYRMIDON, owner_id=player.uid)
    player.board.append(myrmidon)
    for _ in range(2):
        spell = Spell.create_from_db(SpellIDs.MINI_MYRMIDON_SPELLCRAFT)
        player.hand.append(HandCard(uid=empty_game.tavern.get_next_uid(), spell=spell))
        assert empty_game.step(player.uid, "PLAY", hand_index=0, target_index=0)[0]
    copies = [
        card for card in player.hand
        if card.spell and card.spell.card_id == SpellIDs.MINI_MYRMIDON_SPELLCRAFT
    ]
    assert len(copies) == 1
    assert (myrmidon.cur_atk, myrmidon.cur_hp) == (7, 6)
