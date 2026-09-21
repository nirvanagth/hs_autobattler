"""Feed-forward and recurrent pointer policies for eight-player observations."""

from __future__ import annotations

import sys
from pathlib import Path

import torch
import torch.nn as nn

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

from model import HSTransformerAgent
from hearthstone.env.lobby_env import LOBBY_OBSERVATION_SCHEMA


class LobbyPointerAgent(nn.Module):
    """Pointer actor with public-opponent encoding and optional GRU memory."""

    def __init__(
        self,
        *,
        num_card_ids: int = 2048,
        d_model: int = 128,
        n_heads: int = 4,
        n_layers: int = 4,
        use_memory: bool = False,
    ) -> None:
        super().__init__()
        self.d_model = d_model
        self.use_memory = use_memory
        self.schema = LOBBY_OBSERVATION_SCHEMA
        self.base = HSTransformerAgent(
            n_actions=34,
            d_model=d_model,
            n_heads=n_heads,
            n_layers=n_layers,
            num_card_ids=num_card_ids,
            actor_type="pointer",
        )
        self.opponent_encoder = nn.Sequential(
            nn.Linear(self.schema.opponent_stride, d_model),
            nn.SiLU(),
            nn.Linear(d_model, d_model),
        )
        opponent_layer = nn.TransformerEncoderLayer(
            d_model=d_model,
            nhead=n_heads,
            dim_feedforward=2 * d_model,
            dropout=0.0,
            batch_first=True,
            norm_first=False,
        )
        self.opponent_transformer = nn.TransformerEncoder(opponent_layer, num_layers=1)
        self.fusion = nn.Sequential(
            nn.Linear(2 * d_model, d_model),
            nn.SiLU(),
            nn.Linear(d_model, d_model),
        )
        self.memory = nn.GRUCell(d_model, d_model) if use_memory else None

    def _encode_flat(
        self, obs: torch.Tensor
    ) -> tuple[torch.Tensor, torch.Tensor]:
        if obs.ndim != 2 or obs.shape[1] != self.schema.total_size:
            raise ValueError(
                f"expected [B, {self.schema.total_size}], got {tuple(obs.shape)}"
            )
        batch = obs.shape[0]
        own = obs[:, : self.schema.own_size]
        legacy_enemy_padding = torch.zeros(batch, 3, device=obs.device, dtype=obs.dtype)
        own_legacy = torch.cat([own, legacy_enemy_padding], dim=-1)
        own_features, own_tokens = self.base._encode_with_tokens(own_legacy)

        opponent_rows = obs[:, self.schema.own_size :].view(
            batch, self.schema.opponent_slots, self.schema.opponent_stride
        )
        opponent_tokens = self.opponent_encoder(opponent_rows)
        opponent_tokens = self.opponent_transformer(opponent_tokens)
        opponent_features = opponent_tokens.mean(dim=1)
        fused = self.fusion(torch.cat([own_features, opponent_features], dim=-1))
        return fused, own_tokens

    def forward(
        self,
        obs: torch.Tensor,
        hidden: torch.Tensor | None = None,
    ) -> tuple[torch.Tensor, torch.Tensor, torch.Tensor | None]:
        features, own_tokens = self._encode_flat(obs)
        next_hidden = None
        policy_features = features
        if self.memory is not None:
            if hidden is None:
                hidden = torch.zeros_like(features)
            next_hidden = self.memory(features, hidden)
            policy_features = next_hidden
        assert self.base.pointer_actor is not None
        action_logits = self.base.pointer_actor(
            policy_features,
            own_tokens,
            is_discovering=obs[:, 5] > 0.5,
            is_targeting=obs[:, 6] > 0.5,
        )
        value_logits = self.base.critic(policy_features.detach())
        return action_logits, value_logits, next_hidden

    def forward_sequence(
        self,
        observations: torch.Tensor,
        hidden: torch.Tensor | None = None,
    ) -> tuple[torch.Tensor, torch.Tensor, torch.Tensor | None]:
        if observations.ndim != 3:
            raise ValueError("sequence observations must be [B, T, D]")
        batch, steps, width = observations.shape
        flat = observations.reshape(batch * steps, width)
        flat_features, flat_tokens = self._encode_flat(flat)
        features = flat_features.view(batch, steps, self.d_model)

        if self.memory is not None:
            current = (
                torch.zeros(batch, self.d_model, device=observations.device)
                if hidden is None else hidden
            )
            recurrent = []
            for step in range(steps):
                current = self.memory(features[:, step], current)
                recurrent.append(current)
            policy_features = torch.stack(recurrent, dim=1)
            next_hidden = current
        else:
            policy_features = features
            next_hidden = None

        pointer_features = policy_features.reshape(batch * steps, self.d_model)
        assert self.base.pointer_actor is not None
        action_logits = self.base.pointer_actor(
            pointer_features,
            flat_tokens,
            is_discovering=flat[:, 5] > 0.5,
            is_targeting=flat[:, 6] > 0.5,
        ).view(batch, steps, 34)
        value_logits = self.base.critic(pointer_features.detach()).view(
            batch, steps, -1
        )
        return action_logits, value_logits, next_hidden
