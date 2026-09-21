"""Single-agent Gymnasium wrapper for the restricted eight-player lobby."""

from __future__ import annotations

import json
import random
from dataclasses import dataclass

import gymnasium as gym
import numpy as np
from gymnasium import spaces

from hearthstone.engine.configs import CARD_DB
from hearthstone.engine.enums import BattleOutcome, Tags, UnitType
from hearthstone.engine.lobby import LobbyGame, PublicUnitSnapshot
from hearthstone.env.card_vocab import STABLE_V1
from hearthstone.env.hs_env import (
    MAX_ATK,
    MAX_CARDS_IN_GAME,
    MAX_COST,
    MAX_GOLD,
    MAX_HP,
    MAX_SPELL_DISCOUNT,
    MAX_TIER,
    HearthstoneEnv,
)
from hearthstone.env.smart_bot import smart_bot_turn


@dataclass(frozen=True)
class LobbyObservationSchema:
    entity_features: int = 38
    global_features: int = 7
    board_slots: int = 7
    hand_slots: int = 10
    store_slots: int = 7
    discover_slots: int = 3
    opponent_slots: int = 7
    opponent_meta_features: int = 8
    opponent_board_slots: int = 7
    version: int = 1

    @property
    def own_size(self) -> int:
        return self.global_features + (
            self.board_slots
            + self.hand_slots
            + self.store_slots
            + self.discover_slots
        ) * self.entity_features

    @property
    def opponent_stride(self) -> int:
        return self.opponent_meta_features + self.opponent_board_slots * self.entity_features

    @property
    def total_size(self) -> int:
        return self.own_size + self.opponent_slots * self.opponent_stride


LOBBY_OBSERVATION_SCHEMA = LobbyObservationSchema()
PLACEMENT_REWARDS = {1: 1.0, 2: 0.6, 3: 0.3, 4: 0.1, 5: -0.1, 6: -0.3, 7: -0.6, 8: -1.0}


class BattlegroundsLobbyEnv(HearthstoneEnv):
    """Player 0 versus seven SmartBots in a shared-pool LobbyGame."""

    def __init__(self, *, max_tier: int = 3, seed: int = 0) -> None:
        super().__init__(max_tier=max_tier, card_vocab_scheme=STABLE_V1)
        self._lobby_seed = seed
        self.game = LobbyGame(max_tier=max_tier, seed=seed)
        self.my_player_id = 0
        self.enemy_id = 1
        # Match smart_bot_turn's authoritative per-turn budget. Target prompts
        # consume separate Gym steps, so the wrapper must not be stricter.
        self.max_actions_in_turn = 40
        self.max_steps_per_episode = 1000
        self.lobby_schema = LOBBY_OBSERVATION_SCHEMA
        self.observation_space = spaces.Box(
            low=0,
            high=MAX_CARDS_IN_GAME,
            shape=(self.lobby_schema.total_size,),
            dtype=np.float32,
        )
        self._lobby_obs_buffer = np.zeros(
            self.lobby_schema.total_size, dtype=np.float32
        )
        self.lobby_environment_contract = {
            "name": "hsbg_8p_tier3_research",
            "behavior_version": 4,
            "observation_schema_version": self.lobby_schema.version,
            "action_schema_version": 1,
            "observation_size": int(self.lobby_schema.total_size),
            "action_count": int(self.action_space.n),
            "num_players": int(self.game.num_players),
            "max_tier": int(max_tier),
            "base_engine_contract": self.environment_contract,
        }
        self.lobby_environment_contract_json = json.dumps(
            self.lobby_environment_contract, sort_keys=True, separators=(",", ":")
        )

    def reset(
        self,
        *,
        seed: int | None = None,
        options: dict[str, object] | None = None,
    ) -> tuple[np.ndarray, dict[str, object]]:
        gym.Env.reset(self, seed=seed)
        del options
        episode_seed = self._lobby_seed if seed is None else seed
        random.seed(episode_seed)
        np.random.seed(episode_seed)
        self.game = LobbyGame(max_tier=self._max_tier, seed=episode_seed)
        self.steps_taken = 0
        self.actions_in_turn = 0
        self.is_targeting = False
        self.pending_spell_hand_index = None
        self.pending_target_kind = None
        return self._get_lobby_obs(), {}

    def step(self, action: int):
        self.steps_taken += 1
        self.actions_in_turn += 1
        truncated = self.steps_taken >= self.max_steps_per_episode
        player = self.game.players[self.my_player_id]
        action_type, kwargs = self._decode_lobby_action(action, player)

        if action_type in {"WAIT_FOR_TARGET", "CANCEL_CAST"}:
            return self._get_lobby_obs(), 0.0, False, truncated, {}

        success, _, _ = self.game.step(self.my_player_id, action_type, **kwargs)
        if not success:
            return self._get_lobby_obs(), 0.0, False, truncated, {}

        reward = -0.005
        if action_type == "END_TURN":
            reward = 0.0
            self.actions_in_turn = 0
            self._play_lobby_bots()
            result = next(
                (
                    combat
                    for combat in self.game.last_combat_results
                    if combat.player_id == self.my_player_id
                    or (
                        not combat.is_ghost
                        and combat.opponent_id == self.my_player_id
                    )
                ),
                None,
            )
            if result is not None:
                if result.player_id == self.my_player_id:
                    outcome = result.outcome
                else:
                    outcome = (
                        BattleOutcome.LOSE
                        if result.outcome == BattleOutcome.WIN
                        else BattleOutcome.WIN
                        if result.outcome == BattleOutcome.LOSE
                        else result.outcome
                    )
                if outcome == BattleOutcome.WIN:
                    reward += 1.0
                elif outcome == BattleOutcome.LOSE:
                    reward -= 1.0

        terminated = (
            self.my_player_id not in self.game.active_player_ids
            or self.game.game_over
        )
        placement = self.game.placements.get(self.my_player_id)
        if terminated and placement is not None:
            reward += 10.0 * PLACEMENT_REWARDS[placement]
        info = {
            "placement": placement,
            "active_players": self.game.active_count,
            "lobby_turn": self.game.turn_count,
        }
        return self._get_lobby_obs(), float(reward), terminated, truncated, info

    def _decode_lobby_action(self, action: int, player):
        if player.is_discovering:
            return (
                ("DISCOVER_CHOICE", {"index": action - 2})
                if 2 <= action <= 4
                else ("INVALID_DURING_DISCOVERY", {})
            )
        if self.is_targeting:
            if 2 <= action <= 8:
                hand_index = self.pending_spell_hand_index or 0
                self.pending_spell_hand_index = None
                self.pending_target_kind = None
                self.is_targeting = False
                return "PLAY", {"hand_index": hand_index, "target_index": action - 2}
            if action == 0:
                if self.pending_target_kind == "MAGNETIZE":
                    hand_index = self.pending_spell_hand_index or 0
                    self.pending_spell_hand_index = None
                    self.pending_target_kind = None
                    self.is_targeting = False
                    return "PLAY", {"hand_index": hand_index, "insert_index": -1}
                self.pending_spell_hand_index = None
                self.pending_target_kind = None
                self.is_targeting = False
                return "CANCEL_CAST", {}
            return "INVALID_NEED_TARGET", {}
        if action == 0:
            return "END_TURN", {}
        if action == 32:
            return "UPGRADE", {}
        if action == 33:
            self.game.step(self.my_player_id, "FREEZE")
            return "END_TURN", {}
        action_type, kwargs = self._decode_action_for_engine(action)
        if action_type == "PLAY":
            hand_index = kwargs["hand_index"]
            if hand_index < len(player.hand):
                card = player.hand[hand_index]
                card_id = (
                    card.spell.card_id
                    if card.spell
                    else card.unit.card_id if card.unit else None
                )
                from hearthstone.engine.spells import SPELLS_REQUIRE_TARGET

                if card_id in SPELLS_REQUIRE_TARGET:
                    self.pending_spell_hand_index = hand_index
                    self.pending_target_kind = "SPELL"
                    self.is_targeting = True
                    return "WAIT_FOR_TARGET", {}
                if card.unit and card.unit.has_magnetic and any(
                    UnitType.MECH in unit.types for unit in player.board
                ):
                    self.pending_spell_hand_index = hand_index
                    self.pending_target_kind = "MAGNETIZE"
                    self.is_targeting = True
                    return "WAIT_FOR_TARGET", {}
        return action_type, kwargs

    def action_masks(self, player_idx: int | None = None) -> np.ndarray:
        masks = super().action_masks(player_idx)
        if self.is_targeting and self.pending_target_kind == "MAGNETIZE":
            masks[0] = True  # play the Magnetic card as a standalone minion
        return masks

    def _play_lobby_bots(self) -> None:
        for player_id in sorted(self.game.active_player_ids):
            if player_id != self.my_player_id:
                smart_bot_turn(self.game, player_id)

    def _get_lobby_obs(self) -> np.ndarray:
        schema = self.lobby_schema
        buf = self._lobby_obs_buffer
        buf[:] = 0.0
        player = self.game.players[self.my_player_id]
        buf[0] = player.gold / MAX_GOLD
        buf[1] = player.tavern_tier / MAX_TIER
        buf[2] = max(0, player.health) / MAX_HP
        buf[3] = player.up_cost / 10.0
        buf[4] = player.spell_discount / MAX_SPELL_DISCOUNT
        buf[5] = float(player.is_discovering)
        buf[6] = float(self.is_targeting)

        offset = schema.global_features
        self._encode_zone_fast(player.board, buf, offset, 7, "BOARD")
        offset += 7 * schema.entity_features
        self._encode_zone_fast(player.hand, buf, offset, 10, "HAND")
        offset += 10 * schema.entity_features
        self._encode_zone_fast(player.store, buf, offset, 7, "STORE")
        offset += 7 * schema.entity_features
        discovery = player.discovery.options if player.is_discovering else []
        self._encode_zone_fast(discovery, buf, offset, 3, "DISCOVER")
        offset = schema.own_size

        last_opponent = self.game.last_opponent[self.my_player_id]
        for opponent in self.game.public_opponent_states(self.my_player_id):
            base = offset
            buf[base + 0] = 1.0
            buf[base + 1] = opponent.player_id / 7.0
            buf[base + 2] = max(0, opponent.health) / MAX_HP
            buf[base + 3] = opponent.tavern_tier / MAX_TIER
            buf[base + 4] = float(opponent.alive)
            buf[base + 5] = float(opponent.player_id == last_opponent)
            buf[base + 6] = float(opponent.last_seen_board is not None)
            buf[base + 7] = (
                min(opponent.turns_since_seen or 0, 50) / 50.0
                if opponent.last_seen_board is not None else 1.0
            )
            if opponent.last_seen_board is not None:
                board_offset = base + schema.opponent_meta_features
                for slot, unit in enumerate(opponent.last_seen_board.units[:7]):
                    self._encode_public_unit(
                        unit,
                        buf,
                        board_offset + slot * schema.entity_features,
                    )
            offset += schema.opponent_stride
        return buf.copy()

    def _encode_public_unit(
        self, snapshot: PublicUnitSnapshot, buf: np.ndarray, offset: int
    ) -> None:
        data = CARD_DB.get(snapshot.card_id, {})
        buf[offset + 0] = 1.0
        buf[offset + 2] = float(self.static_id_map.get(snapshot.card_id, 0))
        buf[offset + 3] = 3.0 / MAX_COST
        buf[offset + 4] = snapshot.tier / MAX_TIER
        buf[offset + 6] = snapshot.attack / MAX_ATK
        buf[offset + 7] = snapshot.health / MAX_HP
        tag_names = set(snapshot.tags)
        for index, tag in enumerate(
            (
                Tags.TAUNT,
                Tags.DIVINE_SHIELD,
                Tags.WINDFURY,
                Tags.POISONOUS,
                Tags.VENOMOUS,
                Tags.REBORN,
                Tags.CLEAVE,
                Tags.MAGNETIC,
                Tags.IMMEDIATE_ATTACK,
            )
        ):
            buf[offset + 8 + index] = float(tag.name in tag_names)
        buf[offset + 17] = float(snapshot.is_golden)
        buf[offset + 18] = float(data.get("is_token", False))
        buf[offset + 19] = float(data.get("deathrattle", False))
        trigger_flags = self._trigger_cache.get(snapshot.card_id, self._default_triggers)
        for index, enabled in enumerate(trigger_flags):
            buf[offset + 20 + index] = float(enabled)
        type_values = set(snapshot.types)
        for index, unit_type in enumerate(self.all_types):
            buf[offset + 26 + index] = float(unit_type.value in type_values)
