"""Matched sequence behavior cloning for feed-forward and GRU lobby policies."""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

import numpy as np
import torch
import torch.nn as nn
import torch.nn.functional as F
from torch.utils.data import DataLoader, Dataset

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

from lobby_model import LobbyPointerAgent
from model import encode_twohot
from hearthstone.env.lobby_env import BattlegroundsLobbyEnv


class EpisodeDataset(Dataset):
    def __init__(self, arrays: dict[str, np.ndarray], episode_ids: np.ndarray):
        self.arrays = arrays
        self.indices = [np.flatnonzero(arrays["episode_ids"] == episode) for episode in episode_ids]

    def __len__(self) -> int:
        return len(self.indices)

    def __getitem__(self, index: int):
        rows = self.indices[index]
        return tuple(torch.from_numpy(self.arrays[key][rows]) for key in (
            "obs", "masks", "actions", "returns"
        ))


def collate_episodes(batch):
    batch_size = len(batch)
    max_steps = max(item[0].shape[0] for item in batch)
    obs_size = batch[0][0].shape[1]
    observations = torch.zeros(batch_size, max_steps, obs_size)
    masks = torch.zeros(batch_size, max_steps, 34, dtype=torch.bool)
    actions = torch.zeros(batch_size, max_steps, dtype=torch.long)
    returns = torch.zeros(batch_size, max_steps)
    valid = torch.zeros(batch_size, max_steps, dtype=torch.bool)
    for index, (episode_obs, episode_masks, episode_actions, episode_returns) in enumerate(batch):
        steps = episode_obs.shape[0]
        observations[index, :steps] = episode_obs
        masks[index, :steps] = episode_masks
        actions[index, :steps] = episode_actions
        returns[index, :steps] = episode_returns
        valid[index, :steps] = True
    return observations, masks, actions, returns, valid


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dataset", required=True)
    parser.add_argument("--out", required=True)
    parser.add_argument("--use-memory", action="store_true")
    parser.add_argument("--epochs", type=int, default=10)
    parser.add_argument("--batch-size", type=int, default=8,
                        help="complete episodes per batch")
    parser.add_argument("--lr", type=float, default=3e-4)
    parser.add_argument("--critic-coef", type=float, default=0.5)
    parser.add_argument("--val-frac", type=float, default=0.1)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--d-model", type=int, default=128)
    parser.add_argument("--n-heads", type=int, default=4)
    parser.add_argument("--n-layers", type=int, default=4)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    np.random.seed(args.seed)
    torch.manual_seed(args.seed)
    device = torch.device(
        "cuda" if torch.cuda.is_available()
        else "mps" if torch.backends.mps.is_available()
        else "cpu"
    )
    data = np.load(args.dataset)
    arrays = {
        "obs": data["obs"].astype(np.float32),
        "masks": data["masks"].astype(np.bool_),
        "actions": data["actions"].astype(np.int64),
        "returns": data["returns"].astype(np.float32),
        "episode_ids": data["episode_ids"].astype(np.int32),
    }
    contract = json.loads(str(data["lobby_environment_contract"].item()))
    probe = BattlegroundsLobbyEnv(max_tier=int(contract["max_tier"]))
    if probe.lobby_environment_contract != contract:
        raise ValueError("lobby dataset contract does not match runtime environment")
    legal = arrays["masks"][np.arange(len(arrays["actions"])), arrays["actions"]]
    if not legal.all():
        raise ValueError(f"lobby dataset contains {(~legal).sum()} illegal expert labels")

    episodes = np.unique(arrays["episode_ids"])
    rng = np.random.default_rng(args.seed)
    rng.shuffle(episodes)
    n_val = max(1, int(len(episodes) * args.val_frac))
    val_episodes = episodes[:n_val]
    train_episodes = episodes[n_val:]
    train_loader = DataLoader(
        EpisodeDataset(arrays, train_episodes),
        batch_size=args.batch_size,
        shuffle=True,
        collate_fn=collate_episodes,
    )
    val_loader = DataLoader(
        EpisodeDataset(arrays, val_episodes),
        batch_size=args.batch_size,
        shuffle=False,
        collate_fn=collate_episodes,
    )

    agent = LobbyPointerAgent(
        num_card_ids=probe.num_card_ids,
        d_model=args.d_model,
        n_heads=args.n_heads,
        n_layers=args.n_layers,
        use_memory=args.use_memory,
    ).to(device)
    optimizer = torch.optim.AdamW(agent.parameters(), lr=args.lr)
    output = Path(args.out)
    output.parent.mkdir(parents=True, exist_ok=True)
    best_accuracy = -1.0
    started = time.time()

    for epoch in range(1, args.epochs + 1):
        agent.train()
        train_correct = train_rows = 0
        train_loss_sum = 0.0
        for observations, masks, actions, returns, valid in train_loader:
            observations = observations.to(device)
            masks = masks.to(device)
            actions = actions.to(device)
            returns = returns.to(device)
            valid = valid.to(device)
            action_logits, value_logits, _ = agent.forward_sequence(observations)
            valid_logits = action_logits[valid].masked_fill(~masks[valid], -1e8)
            valid_actions = actions[valid]
            actor_loss = F.cross_entropy(valid_logits, valid_actions)
            target_twohot = encode_twohot(returns[valid], agent.base.bins)
            value_loss = -(
                target_twohot * F.log_softmax(value_logits[valid], dim=-1)
            ).sum(dim=-1).mean()
            loss = actor_loss + args.critic_coef * value_loss
            optimizer.zero_grad()
            loss.backward()
            nn.utils.clip_grad_norm_(agent.parameters(), 1.0)
            optimizer.step()
            rows = valid_actions.numel()
            train_loss_sum += loss.item() * rows
            train_correct += (valid_logits.argmax(dim=-1) == valid_actions).sum().item()
            train_rows += rows

        agent.eval()
        val_correct = val_rows = 0
        with torch.no_grad():
            for observations, masks, actions, _returns, valid in val_loader:
                observations = observations.to(device)
                masks = masks.to(device)
                actions = actions.to(device)
                valid = valid.to(device)
                action_logits, _, _ = agent.forward_sequence(observations)
                valid_logits = action_logits[valid].masked_fill(~masks[valid], -1e8)
                valid_actions = actions[valid]
                val_correct += (valid_logits.argmax(dim=-1) == valid_actions).sum().item()
                val_rows += valid_actions.numel()
        train_accuracy = train_correct / train_rows
        val_accuracy = val_correct / val_rows
        print(
            f"[epoch {epoch}/{args.epochs}] loss={train_loss_sum / train_rows:.4f} "
            f"train_acc={train_accuracy:.4f} val_acc={val_accuracy:.4f} "
            f"elapsed={time.time() - started:.0f}s",
            flush=True,
        )
        if val_accuracy > best_accuracy:
            best_accuracy = val_accuracy
            torch.save(
                {
                    "model": agent.state_dict(),
                    "args": vars(args),
                    "val_acc": val_accuracy,
                    "lobby_environment_contract": contract,
                },
                output,
            )
            print(f"  [save] {output}", flush=True)
    print(f"[done] best_val_acc={best_accuracy:.4f}")


if __name__ == "__main__":
    main()
