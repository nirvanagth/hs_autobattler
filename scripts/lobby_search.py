"""Public-observation depth-one Tavern search."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import torch

from hearthstone.lobby_arena import LobbyArena
from model import decode_value


@dataclass(frozen=True)
class SearchResult:
    action: int
    scores: dict[int, float]
    expanded_actions: int


class DepthOnePlanner:
    """Evaluate legal recruit actions without exposing private state to policy."""

    def __init__(
        self,
        model,
        device: torch.device,
        *,
        policy_prior_weight: float = 0.05,
        action_cost: float = 0.005,
    ) -> None:
        self.model = model
        self.device = device
        self.policy_prior_weight = policy_prior_weight
        self.action_cost = action_cost

    def choose_action(self, arena: LobbyArena, player_id: int) -> SearchResult:
        observation = arena.observation(player_id)
        mask = arena.action_mask(player_id)
        legal_actions = [int(action) for action in np.flatnonzero(mask)]
        if not legal_actions:
            raise RuntimeError("search received a state with no legal actions")
        with torch.inference_mode():
            root_logits, _, _ = self.model(
                torch.as_tensor(
                    observation, dtype=torch.float32, device=self.device
                ).unsqueeze(0)
            )
            mask_tensor = torch.as_tensor(
                mask, dtype=torch.bool, device=self.device
            ).unsqueeze(0)
            root_log_probs = torch.log_softmax(
                root_logits.masked_fill(~mask_tensor, -1e8), dim=-1
            )[0]

        snapshot = arena.snapshot()
        child_observations = []
        valid_actions = []
        immediate_rewards = []
        for action in legal_actions:
            arena.restore(snapshot)
            if action == 0 and not arena.player_states[player_id].is_targeting:
                accepted = True
            elif action == 33:
                accepted, _, _ = arena.game.step(player_id, "FREEZE")
            else:
                accepted = arena.apply_action(player_id, action).accepted
            if accepted:
                child_observations.append(arena.observation(player_id))
                valid_actions.append(action)
                immediate_rewards.append(
                    0.0 if action in {0, 33} else -self.action_cost
                )
        arena.restore(snapshot)
        if not valid_actions:
            raise RuntimeError("no legal action could be simulated")

        child_batch = torch.as_tensor(
            np.stack(child_observations), dtype=torch.float32, device=self.device
        )
        with torch.inference_mode():
            _, value_logits, _ = self.model(child_batch)
            values = decode_value(value_logits, self.model.base.bins)
            priors = root_log_probs[valid_actions]
            scores_tensor = (
                values
                + torch.as_tensor(immediate_rewards, device=self.device)
                + self.policy_prior_weight * priors
            )
        scores = {
            action: float(score)
            for action, score in zip(valid_actions, scores_tensor.cpu().tolist())
        }
        best_action = max(valid_actions, key=lambda action: (scores[action], -action))
        return SearchResult(best_action, scores, len(valid_actions))
