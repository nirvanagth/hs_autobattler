"""Restricted-pool eight-player lobby lifecycle tests."""

from __future__ import annotations

from typing import Callable

from hearthstone.engine.entities import Player, Unit
from hearthstone.engine.enums import BattleOutcome
from hearthstone.engine.lobby import LobbyGame
from hearthstone.env.smart_bot import smart_bot_turn


def test_lobby_starts_eight_players_on_one_shared_pool(
    lobby_factory: Callable[..., LobbyGame],
) -> None:
    lobby = lobby_factory(seed=42)
    assert lobby.active_count == 8
    assert len({id(lobby.tavern.pool), id(lobby.pool)}) == 1
    assert all(player.store for player in lobby.players)
    assert all(player.turn_number == 1 for player in lobby.players)


def test_pairings_cover_every_active_player_once(
    lobby_factory: Callable[..., LobbyGame],
) -> None:
    lobby = lobby_factory(seed=42)
    pairings = lobby.create_pairings()
    participants = []
    for pairing in pairings:
        participants.append(pairing.player_id)
        assert pairing.opponent_id is not None
        participants.append(pairing.opponent_id)
    assert len(pairings) == 4
    assert sorted(participants) == list(range(8))


def test_pairing_avoids_immediate_rematches(
    lobby_factory: Callable[..., LobbyGame],
    monkeypatch,
) -> None:
    lobby = lobby_factory(seed=7)
    monkeypatch.setattr(lobby, "_resolve_pair", lambda _a, _b: (BattleOutcome.DRAW, 0))
    lobby.players_ready = {player_id: True for player_id in lobby.active_player_ids}
    first = lobby.resolve_combat_round()
    first_pairs = {
        tuple(sorted((result.player_id, result.opponent_id)))
        for result in first if result.opponent_id is not None
    }
    second_pairs = {
        tuple(sorted((pairing.player_id, pairing.opponent_id)))
        for pairing in lobby.create_pairings() if pairing.opponent_id is not None
    }
    assert first_pairs.isdisjoint(second_pairs)


def test_damage_cap_applies_while_more_than_four_alive(
    lobby_factory: Callable[..., LobbyGame],
    monkeypatch,
) -> None:
    lobby = lobby_factory(seed=4, damage_cap=15, damage_cap_active_threshold=4)
    monkeypatch.setattr(lobby, "_resolve_pair", lambda _a, _b: (BattleOutcome.WIN, 50))
    lobby.players_ready = {player_id: True for player_id in lobby.active_player_ids}
    results = lobby.resolve_combat_round()
    assert all(result.applied_damage == 15 for result in results)
    damaged = [player for player in lobby.players if player.health == 15]
    assert len(damaged) == 4
    assert lobby.active_count == 8


def test_elimination_assigns_placement_and_winner(
    lobby_factory: Callable[..., LobbyGame],
    monkeypatch,
) -> None:
    lobby = lobby_factory(
        num_players=2,
        seed=3,
        starting_health=5,
        damage_cap_active_threshold=2,
    )
    monkeypatch.setattr(lobby, "_resolve_pair", lambda _a, _b: (BattleOutcome.WIN, 5))
    lobby.players_ready = {0: True, 1: True}
    lobby.resolve_combat_round()
    assert lobby.game_over
    assert lobby.winner_id == 0
    assert lobby.placements == {1: 2, 0: 1}
    assert 1 in lobby.ghost_snapshots


def test_simultaneous_all_dead_still_has_deterministic_winner(
    lobby_factory: Callable[..., LobbyGame],
    monkeypatch,
) -> None:
    lobby = lobby_factory(num_players=2, seed=3, starting_health=0)
    monkeypatch.setattr(lobby, "_resolve_pair", lambda _a, _b: (BattleOutcome.DRAW, 0))
    lobby.players_ready = {0: True, 1: True}
    lobby.resolve_combat_round()
    assert lobby.game_over
    assert lobby.winner_id is not None
    assert lobby.placements[lobby.winner_id] == 1


def test_odd_lobby_pairs_one_player_with_recent_ghost(
    lobby_factory: Callable[..., LobbyGame],
) -> None:
    lobby = lobby_factory(num_players=3, seed=11)
    lobby.elimination_order.append(99)
    lobby.ghost_snapshots[99] = Player(uid=99, board=[], hand=[])
    pairings = lobby.create_pairings()
    ghost_pairings = [pairing for pairing in pairings if pairing.is_ghost]
    assert len(ghost_pairings) == 1
    assert ghost_pairings[0].opponent_id == 99


def test_opponent_board_is_hidden_until_combat(
    lobby_factory: Callable[..., LobbyGame],
) -> None:
    lobby = lobby_factory(num_players=2, seed=12)
    lobby.players[1].board.append(
        Unit.create_from_db("101", lobby.tavern.get_next_uid(), owner_id=1)
    )
    opponent = lobby.public_opponent_states(0)[0]
    assert opponent.health == lobby.players[1].health
    assert opponent.tavern_tier == lobby.players[1].tavern_tier
    assert opponent.last_seen_board is None
    assert opponent.turns_since_seen is None


def test_combat_updates_last_seen_without_leaking_future_mutations(
    lobby_factory: Callable[..., LobbyGame],
    monkeypatch,
) -> None:
    lobby = lobby_factory(num_players=2, seed=13)
    lobby.players[1].board.append(
        Unit.create_from_db("101", lobby.tavern.get_next_uid(), owner_id=1)
    )
    monkeypatch.setattr(lobby, "_resolve_pair", lambda _a, _b: (BattleOutcome.DRAW, 0))
    lobby.players_ready = {0: True, 1: True}
    lobby.resolve_combat_round()

    seen = lobby.public_opponent_states(0)[0]
    assert seen.last_seen_board is not None
    assert len(seen.last_seen_board.units) == 1
    assert seen.turns_since_seen == 1

    lobby.players[1].board.clear()
    still_stale = lobby.public_opponent_states(0)[0]
    assert still_stale.last_seen_board is not None
    assert len(still_stale.last_seen_board.units) == 1


def test_eliminated_cards_return_to_shared_pool(
    lobby_factory: Callable[..., LobbyGame],
) -> None:
    lobby = lobby_factory(num_players=2, seed=5)
    card_id = lobby.pool.tiers[1].pop()
    copies_after_draw = lobby.pool.tiers[1].count(card_id)
    unit = Unit.create_from_db(card_id, lobby.tavern.get_next_uid(), owner_id=0)
    lobby.players[0].board.append(unit)
    lobby._release_player_cards(lobby.players[0])
    assert lobby.pool.tiers[1].count(card_id) == copies_after_draw + 1


def test_smart_bots_advance_multiple_lobby_rounds(
    lobby_factory: Callable[..., LobbyGame],
) -> None:
    lobby = lobby_factory(seed=19, max_tier=3)
    for expected_turn in range(2, 5):
        for player_id in sorted(lobby.active_player_ids):
            smart_bot_turn(lobby, player_id)
        assert lobby.turn_count == expected_turn
        assert not lobby.game_over
