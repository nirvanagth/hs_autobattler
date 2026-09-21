"""Multi-policy driver for the restricted eight-player lobby."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

import numpy as np

from hearthstone.engine.lobby import LobbyGame
from hearthstone.env.lobby_env import BattlegroundsLobbyEnv


@dataclass
class PlayerActionState:
    actions_in_turn: int = 0
    is_targeting: bool = False
    pending_spell_hand_index: int | None = None
    pending_target_kind: str | None = None


@dataclass(frozen=True)
class LobbyActionResult:
    accepted: bool
    action_type: str
    info: str


ActionSelector = Callable[[np.ndarray, np.ndarray, int], int]


class LobbyArena:
    """Expose legal observations and actions independently for all eight seats.

    ``BattlegroundsLobbyEnv`` remains the single-agent Gym interface. This
    adapter reuses its frozen observation/action codec while maintaining the
    targeting and action-budget state that each independently acting player
    needs in a population match.
    """

    def __init__(self, *, max_tier: int = 3, seed: int = 0) -> None:
        self.env = BattlegroundsLobbyEnv(max_tier=max_tier, seed=seed)
        self.max_tier = max_tier
        self.seed = seed
        self.player_states: dict[int, PlayerActionState] = {}
        self.reset(seed=seed)

    @property
    def game(self) -> LobbyGame:
        return self.env.game

    @property
    def environment_contract(self) -> dict[str, object]:
        return self.env.lobby_environment_contract

    def reset(self, *, seed: int | None = None) -> None:
        episode_seed = self.seed if seed is None else seed
        self.env.reset(seed=episode_seed)
        self.player_states = {
            player_id: PlayerActionState()
            for player_id in range(self.game.num_players)
        }

    def _activate(self, player_id: int) -> PlayerActionState:
        if not 0 <= player_id < self.game.num_players:
            raise ValueError(f"invalid player id: {player_id}")
        state = self.player_states[player_id]
        self.env.my_player_id = player_id
        self.env.actions_in_turn = state.actions_in_turn
        self.env.is_targeting = state.is_targeting
        self.env.pending_spell_hand_index = state.pending_spell_hand_index
        self.env.pending_target_kind = state.pending_target_kind
        return state

    def _store(self, player_id: int) -> None:
        state = self.player_states[player_id]
        state.actions_in_turn = self.env.actions_in_turn
        state.is_targeting = self.env.is_targeting
        state.pending_spell_hand_index = self.env.pending_spell_hand_index
        state.pending_target_kind = self.env.pending_target_kind

    def observation(self, player_id: int) -> np.ndarray:
        self._activate(player_id)
        observation = self.env._get_lobby_obs()
        self._store(player_id)
        return observation

    def action_mask(self, player_id: int) -> np.ndarray:
        self._activate(player_id)
        mask = self.env.action_masks(player_idx=player_id).copy()
        self._store(player_id)
        return mask

    def apply_action(self, player_id: int, action: int) -> LobbyActionResult:
        if player_id not in self.game.active_player_ids:
            return LobbyActionResult(False, "ELIMINATED", "Player eliminated")
        if self.game.players_ready[player_id]:
            return LobbyActionResult(False, "ALREADY_READY", "Player already ready")

        self._activate(player_id)
        self.env.actions_in_turn += 1
        player = self.game.players[player_id]
        action_type, kwargs = self.env._decode_lobby_action(action, player)
        if action_type == "WAIT_FOR_TARGET":
            self._store(player_id)
            return LobbyActionResult(True, action_type, "Waiting for target")
        if action_type == "CANCEL_CAST":
            self._store(player_id)
            return LobbyActionResult(True, action_type, "Cast cancelled")
        if action_type.startswith("INVALID") or action_type == "UNKNOWN":
            self._store(player_id)
            return LobbyActionResult(False, action_type, "Invalid action")

        success, _, info = self.game.step(player_id, action_type, **kwargs)
        if success and action_type == "END_TURN":
            self.env.actions_in_turn = 0
        self._store(player_id)
        return LobbyActionResult(success, action_type, info)

    def play_action_turn(
        self,
        player_id: int,
        select_action: ActionSelector,
        *,
        max_decisions: int = 80,
    ) -> int:
        """Play one complete Tavern turn and return the decision count."""
        decisions = 0
        while (
            player_id in self.game.active_player_ids
            and not self.game.players_ready[player_id]
        ):
            if decisions >= max_decisions:
                raise RuntimeError(
                    f"policy exceeded {max_decisions} decisions for player {player_id}"
                )
            observation = self.observation(player_id)
            mask = self.action_mask(player_id)
            action = int(select_action(observation, mask, player_id))
            if not 0 <= action < len(mask) or not mask[action]:
                raise ValueError(
                    f"policy selected masked action {action} for player {player_id}"
                )
            result = self.apply_action(player_id, action)
            if not result.accepted:
                raise RuntimeError(
                    f"masked action failed for player {player_id}: "
                    f"action={action}, type={result.action_type}, info={result.info}"
                )
            decisions += 1
        return decisions
