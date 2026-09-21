"""Runtime policies and Gym environment for eight-player league work."""

from __future__ import annotations

import random
import sys
import time
from pathlib import Path

import gymnasium as gym
import numpy as np
import torch

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

from evaluate_lobby_models import load_model
from hearthstone.engine.enums import BattleOutcome
from hearthstone.engine.cpp_bridge import get_cpp_engine
from hearthstone.env.lobby_env import PLACEMENT_REWARDS
from hearthstone.env.smart_bot import smart_bot_turn
from hearthstone.league import PolicyLeague
from hearthstone.lobby_arena import LobbyArena
from lobby_search import DepthOnePlanner


class LoadedPolicy:
    def begin_episode(self) -> None:
        pass

    def play_turn(self, arena: LobbyArena, player_id: int) -> int:
        raise NotImplementedError


class SmartPolicy(LoadedPolicy):
    def play_turn(self, arena: LobbyArena, player_id: int) -> int:
        smart_bot_turn(arena.game, player_id)
        return 1


class NeuralPolicy(LoadedPolicy):
    def __init__(self, checkpoint: Path, device: torch.device) -> None:
        self.model, self.contract = load_model(checkpoint, device)
        self.device = device
        self.hidden: dict[int, torch.Tensor | None] = {}
        self.decisions = 0
        self.elapsed_seconds = 0.0

    def begin_episode(self) -> None:
        self.hidden.clear()

    def play_turn(self, arena: LobbyArena, player_id: int) -> int:
        def select(observation, mask, seat):
            started = time.perf_counter()
            with torch.inference_mode():
                logits, _, hidden = self.model(
                    torch.as_tensor(
                        observation, dtype=torch.float32, device=self.device
                    ).unsqueeze(0),
                    self.hidden.get(seat),
                )
                mask_tensor = torch.as_tensor(
                    mask, dtype=torch.bool, device=self.device
                ).unsqueeze(0)
                action = int(
                    logits.masked_fill(~mask_tensor, -1e8).argmax(dim=-1).item()
                )
            self.hidden[seat] = hidden
            self.elapsed_seconds += time.perf_counter() - started
            self.decisions += 1
            return action

        return arena.play_action_turn(player_id, select)


class SearchPolicy(NeuralPolicy):
    def __init__(
        self,
        checkpoint: Path,
        device: torch.device,
        *,
        policy_prior_weight: float = 0.05,
    ) -> None:
        super().__init__(checkpoint, device)
        if self.model.use_memory:
            raise ValueError("depth-one search currently requires a feed-forward policy")
        self.planner = DepthOnePlanner(
            self.model, device, policy_prior_weight=policy_prior_weight
        )
        self.expanded_actions = 0

    def play_turn(self, arena: LobbyArena, player_id: int) -> int:
        def select(_observation, _mask, seat):
            started = time.perf_counter()
            result = self.planner.choose_action(arena, seat)
            self.elapsed_seconds += time.perf_counter() - started
            self.decisions += 1
            self.expanded_actions += result.expanded_actions
            return result.action

        return arena.play_action_turn(player_id, select)


def load_policies(
    league: PolicyLeague, device: torch.device
) -> dict[str, LoadedPolicy]:
    policies: dict[str, LoadedPolicy] = {}
    for policy_id, entry in league.entries.items():
        if entry.kind == "heuristic_lobby_smart":
            policies[policy_id] = SmartPolicy()
        elif entry.kind == "neural_lobby_pointer":
            policy = NeuralPolicy(Path(entry.artifact_path), device)
            if policy.contract != entry.environment_contract:
                raise ValueError(f"checkpoint contract mismatch for {policy_id}")
            policies[policy_id] = policy
    return policies


class LeagueLobbyEnv(gym.Env[np.ndarray, int]):
    """One learning seat against seven PFSP-sampled archived policies."""

    def __init__(
        self,
        league: PolicyLeague,
        learner_reference_id: str,
        *,
        seed: int,
        device: torch.device,
        pfsp_exponent: float = 2.0,
        reward_mode: str = "sparse",
        oracle_n_combats: int = 64,
        oracle_scale: float = 1.0,
        oracle_gamma: float = 0.999,
    ) -> None:
        super().__init__()
        if learner_reference_id not in league.entries:
            raise KeyError(learner_reference_id)
        self.league = league
        self.learner_reference_id = learner_reference_id
        self.pfsp_exponent = pfsp_exponent
        if reward_mode not in {"sparse", "oracle_potential"}:
            raise ValueError(f"unsupported reward mode: {reward_mode}")
        if reward_mode == "oracle_potential" and get_cpp_engine() is None:
            raise RuntimeError("oracle_potential requires the C++ combat engine")
        self.reward_mode = reward_mode
        self.oracle_n_combats = oracle_n_combats
        self.oracle_scale = oracle_scale
        self.oracle_gamma = oracle_gamma
        self._oracle_rng = random.Random(seed ^ 0xC311_71C)
        self._oracle_seed = 0
        self._oracle_opponent: list[tuple] | None = None
        self._oracle_opponent_tier = 1
        self._oracle_potential = 0.0
        self.seed_base = seed
        self.episode_index = 0
        self.arena = LobbyArena(max_tier=3, seed=seed)
        self.policies = load_policies(league, device)
        self.observation_space = self.arena.env.observation_space
        self.action_space = self.arena.env.action_space
        self.lobby_environment_contract = self.arena.environment_contract
        self.learner_seat = 0
        self.lineup: list[str | None] = []
        self.decisions = 0

    def _play_opponents(self, *, before_learner: bool) -> None:
        seats = sorted(self.arena.game.active_player_ids)
        for seat in seats:
            if (seat < self.learner_seat) != before_learner:
                continue
            if seat == self.learner_seat or self.arena.game.players_ready[seat]:
                continue
            policy_id = self.lineup[seat]
            if policy_id is None or policy_id not in self.policies:
                raise ValueError(f"unavailable opponent policy: {policy_id}")
            self.policies[policy_id].play_turn(self.arena, seat)

    def reset(self, *, seed=None, options=None):
        super().reset(seed=seed)
        del options
        episode_seed = self.seed_base + self.episode_index if seed is None else int(seed)
        self.episode_index += 1
        self._oracle_rng.seed(episode_seed ^ 0xC311_71C)
        self.arena.reset(seed=episode_seed)
        for policy in self.policies.values():
            policy.begin_episode()
        self.learner_seat = episode_seed % self.arena.game.num_players
        opponents = self.league.sample_opponents(
            self.learner_reference_id,
            self.arena.game.num_players - 1,
            seed=episode_seed,
            exponent=self.pfsp_exponent,
            include_learner=True,
        )
        opponent_iter = iter(opponents)
        self.lineup = [
            None if seat == self.learner_seat else next(opponent_iter)
            for seat in range(self.arena.game.num_players)
        ]
        missing = sorted(set(filter(None, self.lineup)) - set(self.policies))
        if missing:
            raise ValueError(f"sampled policies are not runnable: {missing}")
        self.decisions = 0
        self._play_opponents(before_learner=True)
        if self.reward_mode == "oracle_potential":
            self._prepare_oracle()
            self._oracle_potential = self._evaluate_oracle()
        return self.arena.observation(self.learner_seat), self._info()

    def action_masks(self) -> np.ndarray:
        return self.arena.action_mask(self.learner_seat)

    def central_observation(self) -> np.ndarray:
        return self.arena.central_observation()

    def _combat_signal(self) -> tuple[float, int, float]:
        for result in self.arena.game.last_combat_results:
            if result.player_id == self.learner_seat:
                outcome = result.outcome
            elif not result.is_ghost and result.opponent_id == self.learner_seat:
                outcome = (
                    BattleOutcome.LOSE
                    if result.outcome == BattleOutcome.WIN
                    else BattleOutcome.WIN
                    if result.outcome == BattleOutcome.LOSE
                    else result.outcome
                )
            else:
                continue
            if outcome == BattleOutcome.WIN:
                return 1.0, 2, result.applied_damage / self.arena.game.damage_cap
            if outcome == BattleOutcome.LOSE:
                return -1.0, 0, -result.applied_damage / self.arena.game.damage_cap
            return 0.0, 1, 0.0
        return 0.0, 1, 0.0

    def _prepare_oracle(self) -> None:
        opponent_id = self.arena.game.next_opponent(self.learner_seat)
        self._oracle_seed = self._oracle_rng.getrandbits(32)
        if opponent_id is None:
            self._oracle_opponent = None
            return
        if opponent_id in self.arena.game.active_player_ids:
            opponent = self.arena.game.players[opponent_id]
        else:
            opponent = self.arena.game.ghost_snapshots.get(opponent_id)
        if opponent is None or not opponent.board:
            self._oracle_opponent = None
            return
        self._oracle_opponent = [
            self.arena.env._unit_to_cpp(unit) for unit in opponent.board
        ]
        self._oracle_opponent_tier = opponent.tavern_tier

    def _evaluate_oracle(self) -> float:
        player = self.arena.game.players[self.learner_seat]
        if not player.board or self._oracle_opponent is None:
            return 0.0
        engine = get_cpp_engine()
        if engine is None:
            return 0.0
        results = engine.fast_combat_batch(
            [self.arena.env._unit_to_cpp(unit) for unit in player.board],
            self._oracle_opponent,
            self._oracle_seed,
            self.oracle_n_combats,
            tavern_tier_0=player.tavern_tier,
            tavern_tier_1=self._oracle_opponent_tier,
        )
        return sum(
            1.0 if outcome == 2 else 0.5 if outcome == 1 else 0.0
            for outcome, _damage in results
        ) / len(results)

    def _info(self) -> dict[str, object]:
        return {
            "learner_seat": self.learner_seat,
            "lineup": self.lineup.copy(),
            "placement": self.arena.game.placements.get(self.learner_seat),
            "lobby_turn": self.arena.game.turn_count,
        }

    def step(self, action: int):
        self.decisions += 1
        result = self.arena.apply_action(self.learner_seat, int(action))
        reward = -0.005 if result.accepted and result.action_type != "END_TURN" else 0.0
        combat_target_valid = False
        combat_outcome = 1
        combat_damage = 0.0
        if result.accepted and result.action_type == "END_TURN":
            self._play_opponents(before_learner=False)
            combat_reward, combat_outcome, combat_damage = self._combat_signal()
            reward += combat_reward
            combat_target_valid = True

        terminated = (
            self.learner_seat not in self.arena.game.active_player_ids
            or self.arena.game.game_over
        )
        truncated = self.decisions >= 1000
        placement = self.arena.game.placements.get(self.learner_seat)
        if terminated and placement is not None:
            reward += 10.0 * PLACEMENT_REWARDS[placement]
        if (
            result.accepted
            and result.action_type == "END_TURN"
            and not terminated
            and not truncated
        ):
            self._play_opponents(before_learner=True)
        oracle_shaping = 0.0
        if self.reward_mode == "oracle_potential":
            if terminated or truncated:
                next_potential = 0.0
            else:
                if result.accepted and result.action_type == "END_TURN":
                    self._prepare_oracle()
                next_potential = self._evaluate_oracle()
            oracle_shaping = self.oracle_scale * (
                self.oracle_gamma * next_potential - self._oracle_potential
            )
            self._oracle_potential = next_potential
            reward += oracle_shaping
        info = self._info()
        info.update(
            {
                "combat_target_valid": combat_target_valid,
                "combat_outcome": combat_outcome,
                "combat_damage": combat_damage,
                "oracle_shaping": oracle_shaping,
                "oracle_potential": self._oracle_potential,
            }
        )
        return (
            self.arena.observation(self.learner_seat),
            float(reward),
            terminated,
            truncated,
            info,
        )
