"""Restricted-pool eight-player Battlegrounds lobby core.

This module deliberately does not modify the frozen 1v1 ``Game``. It reuses
the authoritative Tavern and combat managers while adding simultaneous lobby
combat, deterministic pairings, ghosts, damage caps, elimination, and placement.
"""

from __future__ import annotations

import random
from dataclasses import dataclass
from typing import Any

from .card_def import GOLDEN_TRIGGER_REGISTRY, TRIGGER_REGISTRY
from .combat import CombatManager
from .configs import TIER_UPGRADE_COSTS, TIER_UPGRADE_COSTS_V8
from .cpp_bridge import get_cpp_engine
from .entities import Player, Unit
from .enums import BattleOutcome
from .event_system import EventManager
from .heroes import HERO_DB, HERO_IDS, assign_hero
from .pool import CardPool, SpellPool
from .tavern import TavernManager


@dataclass(frozen=True)
class LobbyPairing:
    player_id: int
    opponent_id: int | None
    is_ghost: bool = False


@dataclass(frozen=True)
class LobbyCombatResult:
    round_number: int
    player_id: int
    opponent_id: int | None
    is_ghost: bool
    outcome: BattleOutcome
    raw_damage: int
    applied_damage: int


@dataclass(frozen=True)
class PublicUnitSnapshot:
    card_id: str
    attack: int
    health: int
    tier: int
    is_golden: bool
    tags: tuple[str, ...]
    types: tuple[str, ...]

    @staticmethod
    def from_unit(unit: Unit) -> PublicUnitSnapshot:
        return PublicUnitSnapshot(
            card_id=str(getattr(unit.card_id, "value", unit.card_id)),
            attack=unit.cur_atk,
            health=unit.cur_hp,
            tier=unit.tier,
            is_golden=unit.is_golden,
            tags=tuple(sorted(tag.name for tag in unit.tags)),
            types=tuple(sorted(unit_type.value for unit_type in unit.types)),
        )


@dataclass(frozen=True)
class PublicBoardSnapshot:
    seen_on_turn: int
    tavern_tier: int
    units: tuple[PublicUnitSnapshot, ...]

    @staticmethod
    def from_player(player: Player, turn: int) -> PublicBoardSnapshot:
        return PublicBoardSnapshot(
            seen_on_turn=turn,
            tavern_tier=player.tavern_tier,
            units=tuple(PublicUnitSnapshot.from_unit(unit) for unit in player.board),
        )


@dataclass(frozen=True)
class PublicOpponentState:
    player_id: int
    health: int
    tavern_tier: int
    alive: bool
    is_next_opponent: bool
    last_seen_board: PublicBoardSnapshot | None
    turns_since_seen: int | None
    hero_id: str = "NONE"
    armor: int = 0
    hero_power_cooldown: int = 0


class LobbyGame:
    """Eight-player lobby using a shared minion pool and pairwise combat."""

    def __init__(
        self,
        *,
        num_players: int = 8,
        max_tier: int = 3,
        starting_health: int = 30,
        damage_cap: int = 15,
        damage_cap_active_threshold: int = 4,
        seed: int = 0,
        behavior_version: int = 5,
        content_profile: dict[str, Any] | None = None,
        hero_ids: list[str] | None = None,
    ) -> None:
        if not 2 <= num_players <= 8:
            raise ValueError("num_players must be between 2 and 8")
        if not 1 <= max_tier <= 6:
            raise ValueError("max_tier must be between 1 and 6")
        self.num_players = num_players
        self.max_tier = max_tier
        self.damage_cap = damage_cap
        self.damage_cap_active_threshold = damage_cap_active_threshold
        self.seed = seed
        self.behavior_version = behavior_version
        if content_profile is not None:
            if int(content_profile["behavior_version"]) != behavior_version:
                raise ValueError("content profile behavior version mismatch")
            if int(content_profile["max_tier"]) != max_tier:
                raise ValueError("content profile max tier mismatch")
        self.content_profile = content_profile
        random.seed(seed)
        self._pair_rng = random.Random(seed ^ 0x8A77_10BB)

        # Shops are restricted by ``max_tier``; the pool retains higher tiers
        # so triple discoveries remain representable during later extensions.
        card_ids = (
            set(content_profile["included_card_ids"]) if content_profile else None
        )
        spell_ids = (
            set(content_profile["included_spell_ids"]) if content_profile else None
        )
        self.pool = CardPool(max_tier=7, included_card_ids=card_ids)
        self.spell_pool = SpellPool(included_spell_ids=spell_ids)
        self.event_manager = EventManager(TRIGGER_REGISTRY, GOLDEN_TRIGGER_REGISTRY)
        self.tavern = TavernManager(
            self.pool,
            self.spell_pool,
            event_manager=self.event_manager,
            emit_play_summon_event=behavior_version >= 6,
            upgrade_costs=(TIER_UPGRADE_COSTS_V8 if behavior_version >= 8 else TIER_UPGRADE_COSTS),
        )
        self.combat = CombatManager(event_manager=self.event_manager)
        self.players = [
            Player(uid=index, board=[], hand=[], health=starting_health)
            for index in range(num_players)
        ]
        if behavior_version >= 7 and hero_ids is None:
            hero_ids = list(HERO_IDS[:num_players])
        if hero_ids is not None:
            if behavior_version < 7:
                raise ValueError("heroes require behavior_version >= 7")
            if len(hero_ids) != num_players:
                raise ValueError("hero count must match player count")
            for player, hero_id in zip(self.players, hero_ids):
                if hero_id not in HERO_DB:
                    raise ValueError(f"unknown hero: {hero_id}")
                assign_hero(player, hero_id)

        self.turn_count = 1
        self.game_over = False
        self.winner_id: int | None = None
        self.active_player_ids: set[int] = set(range(num_players))
        self.players_ready = {index: False for index in range(num_players)}
        self.placements: dict[int, int] = {}
        self.elimination_order: list[int] = []
        self.ghost_snapshots: dict[int, Player] = {}
        self.pair_counts: dict[tuple[int, int], int] = {}
        self.last_opponent: dict[int, int | None] = {
            index: None for index in range(num_players)
        }
        self.ghost_byes: dict[int, int] = {index: 0 for index in range(num_players)}
        self.last_pairings: list[LobbyPairing] = []
        self.last_combat_results: list[LobbyCombatResult] = []
        self.last_seen_boards: dict[int, dict[int, PublicBoardSnapshot]] = {
            viewer: {} for viewer in range(num_players)
        }

        for player in self.players:
            self.tavern.start_turn(player, self.turn_count)
        self.current_pairings = self.create_pairings()

    @property
    def active_count(self) -> int:
        return len(self.active_player_ids)

    def step(
        self, player_idx: int, action_type: str, **kwargs: Any
    ) -> tuple[bool, bool, str]:
        if self.game_over:
            return True, True, "Game Over"
        if player_idx not in self.active_player_ids:
            return False, False, "Player eliminated"
        player = self.players[player_idx]
        if player.is_discovering and action_type != "DISCOVER_CHOICE":
            return False, False, "Must choose discovery"
        if self.players_ready[player_idx] and action_type != "END_TURN":
            return False, False, "Player already ready"

        success = False
        info = "Unknown Action"
        if action_type == "END_TURN":
            self.tavern.end_turn(player)
            self.players_ready[player_idx] = True
            success, info = True, "Ready"
        elif action_type == "BUY":
            success, info = self.tavern.buy_unit(player, kwargs.get("index", -1))
        elif action_type == "SELL":
            success, info = self.tavern.sell_unit(player, kwargs.get("index", -1))
        elif action_type == "ROLL":
            success, info = self.tavern.roll_tavern(player)
        elif action_type == "UPGRADE":
            if player.tavern_tier >= self.max_tier:
                return False, False, "Lobby tier cap reached"
            success, info = self.tavern.upgrade_tavern(player)
        elif action_type == "FREEZE":
            success, info = self.tavern.toggle_freeze(player)
        elif action_type == "HERO_POWER":
            success, info = self.tavern.activate_hero_power(
                player, kwargs.get("target_index", -1)
            )
        elif action_type == "PLAY":
            success, info = self.tavern.play_unit(
                player,
                kwargs.get("hand_index", -1),
                kwargs.get("insert_index", len(player.board)),
                kwargs.get("target_index", -1),
            )
        elif action_type == "SWAP":
            success, info = self.tavern.swap_units(
                player, kwargs.get("index_a", -1), kwargs.get("index_b", -1)
            )
        elif action_type == "DISCOVER_CHOICE":
            success, info = self.tavern.make_discovery_choice(
                player, kwargs.get("index", -1)
            )

        if self._all_active_ready():
            self.resolve_combat_round()
        return success, self.game_over, info

    def _all_active_ready(self) -> bool:
        return all(self.players_ready[player_id] for player_id in self.active_player_ids)

    def create_pairings(self) -> list[LobbyPairing]:
        """Greedy deterministic pairing minimizing repeats and immediate rematches."""
        remaining = sorted(self.active_player_ids)
        pairings: list[LobbyPairing] = []
        ghost_player: int | None = None
        if len(remaining) % 2:
            ghost_player = min(
                remaining,
                key=lambda player_id: (self.ghost_byes[player_id], player_id),
            )
            remaining.remove(ghost_player)

        while remaining:
            player_id = remaining.pop(0)
            opponent_id = min(
                remaining,
                key=lambda candidate: (
                    self.pair_counts.get(tuple(sorted((player_id, candidate))), 0),
                    self.last_opponent[player_id] == candidate,
                    candidate,
                ),
            )
            remaining.remove(opponent_id)
            pairings.append(LobbyPairing(player_id, opponent_id, False))

        if ghost_player is not None:
            ghost_owner = self.elimination_order[-1] if self.elimination_order else None
            pairings.append(
                LobbyPairing(
                    player_id=ghost_player,
                    opponent_id=ghost_owner,
                    is_ghost=ghost_owner is not None,
                )
            )
            self.ghost_byes[ghost_player] += 1
        return pairings

    def public_opponent_states(self, viewer_id: int) -> list[PublicOpponentState]:
        """Return only information legally available to one player."""
        if not 0 <= viewer_id < self.num_players:
            raise ValueError(f"invalid viewer id: {viewer_id}")
        states = []
        next_opponent = self.next_opponent(viewer_id)
        for player in self.players:
            if player.uid == viewer_id:
                continue
            snapshot = self.last_seen_boards[viewer_id].get(player.uid)
            states.append(
                PublicOpponentState(
                    player_id=player.uid,
                    health=player.health,
                    tavern_tier=player.tavern_tier,
                    alive=player.uid in self.active_player_ids,
                    is_next_opponent=player.uid == next_opponent,
                    last_seen_board=snapshot,
                    turns_since_seen=(
                        self.turn_count - snapshot.seen_on_turn
                        if snapshot is not None else None
                    ),
                    hero_id=player.hero_id,
                    armor=player.armor,
                    hero_power_cooldown=player.hero.power_cooldown,
                )
            )
        return states

    def next_opponent(self, player_id: int) -> int | None:
        for pairing in self.current_pairings:
            if pairing.player_id == player_id:
                return pairing.opponent_id
            if not pairing.is_ghost and pairing.opponent_id == player_id:
                return pairing.player_id
        return None

    def _record_mutual_observation(self, first: Player, second: Player) -> None:
        self.last_seen_boards[first.uid][second.uid] = PublicBoardSnapshot.from_player(
            second, self.turn_count
        )
        self.last_seen_boards[second.uid][first.uid] = PublicBoardSnapshot.from_player(
            first, self.turn_count
        )

    def _resolve_pair(self, first: Player, second: Player) -> tuple[BattleOutcome, int]:
        # The fast combat prelude can materialize hand-based start-of-combat
        # summons, so pass copies to keep every recruit board persistent and to
        # make all lobby damage simultaneous.
        first_combat = first.combat_copy()
        second_combat = second.combat_copy()
        if get_cpp_engine() is not None:
            return self.combat.resolve_combat_fast(first_combat, second_combat)
        return self.combat.resolve_combat(first_combat, second_combat)

    def resolve_combat_round(self) -> list[LobbyCombatResult]:
        if not self._all_active_ready():
            raise RuntimeError("cannot resolve combat before all active players are ready")
        active_before = self.active_count
        pairings = self.current_pairings
        pending_damage = {player_id: 0 for player_id in self.active_player_ids}
        results: list[LobbyCombatResult] = []

        for pairing in pairings:
            first = self.players[pairing.player_id]
            if pairing.opponent_id is None:
                results.append(
                    LobbyCombatResult(
                        self.turn_count,
                        pairing.player_id,
                        None,
                        False,
                        BattleOutcome.DRAW,
                        0,
                        0,
                    )
                )
                continue

            if pairing.is_ghost:
                second = self.ghost_snapshots[pairing.opponent_id].combat_copy()
                self.last_seen_boards[first.uid][pairing.opponent_id] = (
                    PublicBoardSnapshot.from_player(second, self.turn_count)
                )
            else:
                second = self.players[pairing.opponent_id]
                self._record_mutual_observation(first, second)

            outcome, raw_damage = self._resolve_pair(first, second)
            raw_damage = abs(raw_damage)
            applied_damage = (
                min(raw_damage, self.damage_cap)
                if active_before > self.damage_cap_active_threshold
                else raw_damage
            )
            if outcome == BattleOutcome.LOSE:
                pending_damage[first.uid] += applied_damage
                first.lost_last_combat = True
                if not pairing.is_ghost:
                    second.lost_last_combat = False
            elif outcome == BattleOutcome.WIN:
                first.lost_last_combat = False
                if not pairing.is_ghost:
                    pending_damage[second.uid] += applied_damage
                    second.lost_last_combat = True
            else:
                first.lost_last_combat = False
                if not pairing.is_ghost:
                    second.lost_last_combat = False

            results.append(
                LobbyCombatResult(
                    self.turn_count,
                    pairing.player_id,
                    pairing.opponent_id,
                    pairing.is_ghost,
                    outcome,
                    raw_damage,
                    applied_damage,
                )
            )
            if not pairing.is_ghost:
                key = tuple(sorted((first.uid, second.uid)))
                self.pair_counts[key] = self.pair_counts.get(key, 0) + 1
                self.last_opponent[first.uid] = second.uid
                self.last_opponent[second.uid] = first.uid

        for player_id, damage in pending_damage.items():
            self.players[player_id].take_damage(damage)

        eliminated = sorted(
            (
                player_id
                for player_id in self.active_player_ids
                if self.players[player_id].health <= 0
            ),
            key=lambda player_id: (self.players[player_id].health, player_id),
        )
        for offset, player_id in enumerate(eliminated):
            self.placements[player_id] = active_before - offset
            self.ghost_snapshots[player_id] = self.players[player_id].combat_copy()
            self.elimination_order.append(player_id)
            self._release_player_cards(self.players[player_id])
            self.active_player_ids.remove(player_id)
            self.players_ready[player_id] = False

        self.last_pairings = pairings
        self.last_combat_results = results
        if self.active_count <= 1:
            self.game_over = True
            if self.active_player_ids:
                self.winner_id = next(iter(self.active_player_ids))
                self.placements[self.winner_id] = 1
            elif self.placements:
                # Tavern self-damage can leave every remaining player at or
                # below zero before simultaneous combat damage is applied.
                # Placement tie-breaking above is deterministic, so rank 1 is
                # still a well-defined lobby winner.
                self.winner_id = min(
                    self.placements, key=lambda player_id: self.placements[player_id]
                )
            return results

        self.turn_count += 1
        for player_id in sorted(self.active_player_ids):
            self.players_ready[player_id] = False
            self.tavern.start_turn(self.players[player_id], self.turn_count)
        self.current_pairings = self.create_pairings()
        return results

    def _release_player_cards(self, player: Player) -> None:
        card_ids: list[str] = []

        def add_unit(unit: Unit) -> None:
            card_ids.extend([unit.card_id] * unit.pool_copies)
            for card_id, copies in unit.absorbed_pool_copies.items():
                card_ids.extend([card_id] * copies)

        for unit in player.board:
            add_unit(unit)
        for hand_card in player.hand:
            if hand_card.unit:
                add_unit(hand_card.unit)
        for store_item in player.store:
            if store_item.unit:
                add_unit(store_item.unit)
        self.pool.return_cards(card_ids)
        player.board.clear()
        player.hand.clear()
        player.store.clear()
