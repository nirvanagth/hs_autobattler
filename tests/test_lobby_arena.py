"""Multi-policy lobby action driver tests."""

import numpy as np

from hearthstone.env.smart_bot import smart_bot_turn
from hearthstone.lobby_arena import LobbyArena


def test_player_targeting_state_is_isolated() -> None:
    arena = LobbyArena(seed=7)
    arena.player_states[0].is_targeting = True
    arena.player_states[0].pending_target_kind = "SPELL"
    assert arena.observation(0)[6] == 1.0
    assert arena.observation(1)[6] == 0.0


def test_masked_end_turn_advances_only_after_all_players_ready() -> None:
    arena = LobbyArena(seed=11)
    starting_turn = arena.game.turn_count
    for player_id in range(7):
        result = arena.apply_action(player_id, 0)
        assert result.accepted
        assert arena.game.turn_count == starting_turn
    result = arena.apply_action(7, 0)
    assert result.accepted
    assert arena.game.turn_count == starting_turn + 1


def test_action_policy_can_finish_a_full_lobby() -> None:
    arena = LobbyArena(seed=13)

    def first_legal(_observation, mask, _player_id):
        return int(np.flatnonzero(mask)[0])

    while not arena.game.game_over:
        for player_id in sorted(arena.game.active_player_ids):
            if player_id == 0:
                arena.play_action_turn(player_id, first_legal)
            else:
                smart_bot_turn(arena.game, player_id)
    assert sorted(arena.game.placements.values()) == list(range(1, 9))
