"""Single-agent Gymnasium wrapper for the restricted eight-player lobby."""

from __future__ import annotations

import hashlib
import json
import random
from dataclasses import dataclass

import gymnasium as gym
import numpy as np
from gymnasium import spaces

from hearthstone.engine.configs import CARD_DB
from hearthstone.engine.enums import BattleOutcome, Tags, UnitType
from hearthstone.engine.lobby import LobbyGame, PublicUnitSnapshot
from hearthstone.engine.heroes import (
    HERO_DB,
    HERO_IDS,
    HERO_ID_TO_INDEX,
    HeroPowerTarget,
    hero_power_available,
    hero_registry_sha256,
)
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
    opponent_meta_features: int = 9
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
HERO_LOBBY_OBSERVATION_SCHEMA = LobbyObservationSchema(
    global_features=12,
    opponent_meta_features=12,
    version=2,
)
PLACEMENT_REWARDS = {1: 1.0, 2: 0.6, 3: 0.3, 4: 0.1, 5: -0.1, 6: -0.3, 7: -0.6, 8: -1.0}


class BattlegroundsLobbyEnv(HearthstoneEnv):
    """Player 0 versus seven SmartBots in a shared-pool LobbyGame."""

    def __init__(
        self,
        *,
        max_tier: int = 3,
        seed: int = 0,
        behavior_version: int = 5,
        content_profile: dict[str, object] | None = None,
        hero_ids: list[str] | None = None,
    ) -> None:
        super().__init__(
            max_tier=max_tier,
            card_vocab_scheme=STABLE_V1,
            behavior_version=behavior_version,
        )
        self._lobby_seed = seed
        self._content_profile = content_profile
        self._hero_ids = list(hero_ids) if hero_ids is not None else None
        self.game = LobbyGame(
            max_tier=max_tier,
            seed=seed,
            behavior_version=behavior_version,
            content_profile=content_profile,
            hero_ids=self._hero_ids,
        )
        self.my_player_id = 0
        self.enemy_id = 1
        # Match smart_bot_turn's authoritative per-turn budget. Target prompts
        # consume separate Gym steps, so the wrapper must not be stricter.
        self.max_actions_in_turn = 40
        self.max_steps_per_episode = 1000
        self.lobby_schema = (
            HERO_LOBBY_OBSERVATION_SCHEMA
            if behavior_version >= 7
            else LOBBY_OBSERVATION_SCHEMA
        )
        if behavior_version >= 7:
            self.action_space = spaces.Discrete(35)
            self._mask_buffer = np.zeros(35, dtype=np.bool_)
        self.observation_space = spaces.Box(
            low=0,
            high=MAX_CARDS_IN_GAME,
            shape=(self.lobby_schema.total_size,),
            dtype=np.float32,
        )
        self._lobby_obs_buffer = np.zeros(
            self.lobby_schema.total_size, dtype=np.float32
        )
        lobby_name = (
            "hsbg_8p_tier3_research"
            if behavior_version == 5 and max_tier == 3 and content_profile is None
            else "hsbg_8p_heroes_research"
            if behavior_version >= 7
            else "hsbg_8p_fulltier_research"
            if max_tier == 6
            else f"hsbg_8p_verified_tier{max_tier}_research"
        )
        self.lobby_environment_contract = {
            "name": lobby_name,
            "behavior_version": behavior_version,
            "observation_schema_version": self.lobby_schema.version,
            "action_schema_version": 2 if behavior_version >= 7 else 1,
            "observation_size": int(self.lobby_schema.total_size),
            "action_count": int(self.action_space.n),
            "num_players": int(self.game.num_players),
            "max_tier": int(max_tier),
            "base_engine_contract": self.environment_contract,
        }
        if content_profile is not None:
            canonical_profile = json.dumps(
                content_profile, sort_keys=True, separators=(",", ":")
            ).encode()
            self.lobby_environment_contract["content_profile_sha256"] = (
                hashlib.sha256(canonical_profile).hexdigest()
            )
        if behavior_version >= 7:
            roster = self._hero_ids or list(HERO_IDS[: self.game.num_players])
            canonical_roster = json.dumps(roster, separators=(",", ":")).encode()
            self.lobby_environment_contract["hero_schema_version"] = 1
            self.lobby_environment_contract["hero_registry_sha256"] = (
                hero_registry_sha256()
            )
            self.lobby_environment_contract["hero_roster"] = roster
            self.lobby_environment_contract["hero_roster_sha256"] = hashlib.sha256(
                canonical_roster
            ).hexdigest()
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
        self.game = LobbyGame(
            max_tier=self._max_tier,
            seed=episode_seed,
            behavior_version=self._behavior_version,
            content_profile=self._content_profile,
            hero_ids=self._hero_ids,
        )
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
            if self.pending_target_kind == "HERO_BOARD":
                if 2 <= action <= 8:
                    self.is_targeting = False
                    self.pending_target_kind = None
                    return "HERO_POWER", {"target_index": action - 2}
                if action == 0:
                    self.is_targeting = False
                    self.pending_target_kind = None
                    return "CANCEL_CAST", {}
                return "INVALID_NEED_HERO_TARGET", {}
            if self.pending_target_kind == "HERO_STORE":
                if 9 <= action <= 15:
                    self.is_targeting = False
                    self.pending_target_kind = None
                    return "HERO_POWER", {"target_index": action - 9}
                if action == 0:
                    self.is_targeting = False
                    self.pending_target_kind = None
                    return "CANCEL_CAST", {}
                return "INVALID_NEED_HERO_TARGET", {}
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
        if action == 34 and self._behavior_version >= 7:
            hero = HERO_DB.get(player.hero_id)
            if hero is None:
                return "INVALID_HERO_POWER", {}
            if hero.target == HeroPowerTarget.FRIENDLY_BOARD:
                self.is_targeting = True
                self.pending_target_kind = "HERO_BOARD"
                return "WAIT_FOR_TARGET", {}
            if hero.target == HeroPowerTarget.FRIENDLY_STORE:
                self.is_targeting = True
                self.pending_target_kind = "HERO_STORE"
                return "WAIT_FOR_TARGET", {}
            return "HERO_POWER", {"target_index": -1}
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
        player_id = self.my_player_id if player_idx is None else player_idx
        player = self.game.players[player_id]
        if self.is_targeting and self.pending_target_kind == "HERO_STORE":
            masks[:] = False
            for index, item in enumerate(player.store[:7]):
                masks[9 + index] = item.unit is not None
            return masks
        if self.is_targeting and self.pending_target_kind == "HERO_BOARD":
            masks[:] = False
            hero = HERO_DB.get(player.hero_id)
            for index in range(min(len(player.board), 7)):
                masks[2 + index] = not (
                    hero is not None
                    and hero.power_kind == "MAKE_GOLDEN"
                    and player.board[index].is_golden
                )
            return masks
        if self.is_targeting and self.pending_target_kind == "MAGNETIZE":
            masks[0] = True  # play the Magnetic card as a standalone minion
        if (
            self._behavior_version >= 7
            and not self.is_targeting
            and not player.is_discovering
            and self.actions_in_turn < self.max_actions_in_turn
        ):
            masks[34] = hero_power_available(player)
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
        if self._behavior_version >= 7:
            buf[7] = player.armor / MAX_HP
            buf[8] = HERO_ID_TO_INDEX.get(player.hero_id, 0) / max(1, len(HERO_IDS))
            buf[9] = min(player.hero.power_cooldown, 10) / 10.0
            buf[10] = min(player.hero.power_uses, 10) / 10.0
            buf[11] = float(hero_power_available(player))

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
            buf[base + 8] = float(opponent.is_next_opponent)
            if self._behavior_version >= 7:
                buf[base + 9] = (
                    HERO_ID_TO_INDEX.get(opponent.hero_id, 0) / max(1, len(HERO_IDS))
                )
                buf[base + 10] = opponent.armor / MAX_HP
                buf[base + 11] = min(opponent.hero_power_cooldown, 10) / 10.0
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
