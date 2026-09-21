"""Runtime policies and Gym environment for eight-player league work."""

from __future__ import annotations

import sys
from pathlib import Path

import gymnasium as gym
import numpy as np
import torch

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

from evaluate_lobby_models import load_model
from hearthstone.engine.enums import BattleOutcome
from hearthstone.env.lobby_env import PLACEMENT_REWARDS
from hearthstone.env.smart_bot import smart_bot_turn
from hearthstone.league import PolicyLeague
from hearthstone.lobby_arena import LobbyArena


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

    def begin_episode(self) -> None:
        self.hidden.clear()

    def play_turn(self, arena: LobbyArena, player_id: int) -> int:
        def select(observation, mask, seat):
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
            return action

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
    ) -> None:
        super().__init__()
        if learner_reference_id not in league.entries:
            raise KeyError(learner_reference_id)
        self.league = league
        self.learner_reference_id = learner_reference_id
        self.pfsp_exponent = pfsp_exponent
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
        return self.arena.observation(self.learner_seat), self._info()

    def action_masks(self) -> np.ndarray:
        return self.arena.action_mask(self.learner_seat)

    def _combat_reward(self) -> float:
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
                return 1.0
            if outcome == BattleOutcome.LOSE:
                return -1.0
            return 0.0
        return 0.0

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
        if result.accepted and result.action_type == "END_TURN":
            self._play_opponents(before_learner=False)
            reward += self._combat_reward()

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
        return (
            self.arena.observation(self.learner_seat),
            float(reward),
            terminated,
            truncated,
            self._info(),
        )
