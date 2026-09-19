"""Behavior cloning pretrain on ES bot trajectories.

Loads expert episodes from artifacts/bc_dataset.npz. The actor is trained with
masked cross-entropy and, when Monte-Carlo returns are present, the categorical
critic is pretrained at the same time.

Saves a checkpoint compatible with `train_ppo.py --resume`:
    {"model": state_dict, "global_step": 0, "args": {...}}

Usage:
    python scripts/bc_train.py --epochs 10 --batch-size 256
    python scripts/bc_train.py --epochs 10 --wandb --run-name bc_v1
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

import numpy as np
import torch
import torch.nn as nn
import torch.nn.functional as F
from torch.utils.data import DataLoader, TensorDataset

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

from model import HSTransformerAgent, encode_twohot
from hearthstone.env.hs_env import HearthstoneEnv
from hearthstone.env.card_vocab import CARD_VOCAB_SCHEMES, LEGACY_SORTED


def parse_args():
    p = argparse.ArgumentParser()
    p.add_argument("--dataset", default="artifacts/bc_dataset.npz")
    p.add_argument("--out", default="artifacts/bc/bc_pretrain.pt")
    # Train
    p.add_argument("--epochs", type=int, default=10)
    p.add_argument("--batch-size", type=int, default=256)
    p.add_argument("--lr", type=float, default=3e-4)
    p.add_argument("--weight-decay", type=float, default=0.0)
    p.add_argument("--max-grad-norm", type=float, default=1.0)
    p.add_argument("--critic-coef", type=float, default=0.5)
    p.add_argument("--val-frac", type=float, default=0.05)
    p.add_argument("--seed", type=int, default=42)
    # Model (must match train_ppo.py for resume compatibility)
    p.add_argument("--d-model", type=int, default=128)
    p.add_argument("--n-heads", type=int, default=4)
    p.add_argument("--n-layers", type=int, default=4)
    p.add_argument("--actor-type", choices=("flat", "pointer"), default="pointer")
    p.add_argument("--max-tier", type=int, default=6)
    p.add_argument("--card-vocab-scheme", choices=CARD_VOCAB_SCHEMES, default=None)
    # Logging
    p.add_argument("--wandb", action="store_true")
    p.add_argument("--wandb-project", default="hs_autobattler")
    p.add_argument("--run-name", default=None)
    return p.parse_args()


def main():
    args = parse_args()

    np.random.seed(args.seed)
    torch.manual_seed(args.seed)

    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    print(f"[device] {device}")

    # ---- Load dataset ----
    data = np.load(args.dataset)
    obs = torch.from_numpy(data["obs"]).float()
    masks = torch.from_numpy(data["masks"]).bool()
    actions = torch.from_numpy(data["actions"]).long()
    episode_ids = (
        torch.from_numpy(data["episode_ids"]).long()
        if "episode_ids" in data else None
    )
    returns = torch.from_numpy(data["returns"]).float() if "returns" in data else None
    dataset_vocab_scheme = (
        str(data["card_vocab_scheme"].item())
        if "card_vocab_scheme" in data else None
    )
    teacher_weights_sha256 = (
        str(data["teacher_weights_sha256"].item())
        if "teacher_weights_sha256" in data else None
    )
    if (
        args.card_vocab_scheme is not None
        and dataset_vocab_scheme is not None
        and args.card_vocab_scheme != dataset_vocab_scheme
    ):
        raise ValueError(
            f"--card-vocab-scheme={args.card_vocab_scheme} does not match "
            f"dataset scheme {dataset_vocab_scheme}"
        )
    args.card_vocab_scheme = (
        args.card_vocab_scheme or dataset_vocab_scheme or LEGACY_SORTED
    )
    print(f"[data] {len(actions):,} samples, obs_dim={obs.shape[1]}")

    # ---- Sanity: every recorded action must be legal under its mask ----
    legal_check = masks[torch.arange(len(actions)), actions]
    illegal = (~legal_check).sum().item()
    if illegal > 0:
        print(f"[warn] {illegal}/{len(actions)} samples have action masked illegal — dropping")
        keep = legal_check
        obs, masks, actions = obs[keep], masks[keep], actions[keep]
        if episode_ids is not None:
            episode_ids = episode_ids[keep]
        if returns is not None:
            returns = returns[keep]

    # ---- Train/val split ----
    n = len(actions)
    if episode_ids is not None:
        unique_episodes = torch.unique(episode_ids)
        episode_perm = unique_episodes[torch.randperm(len(unique_episodes))]
        n_val_episodes = max(1, int(len(unique_episodes) * args.val_frac))
        val_episodes = episode_perm[:n_val_episodes]
        val_rows = torch.isin(episode_ids, val_episodes)
        val_idx = torch.where(val_rows)[0]
        train_idx = torch.where(~val_rows)[0]
        print(
            f"[split] episode-level train_episodes="
            f"{len(unique_episodes) - n_val_episodes:,} "
            f"val_episodes={n_val_episodes:,}"
        )
    else:
        print("[warn] dataset has no episode_ids; using legacy transition-level split")
        perm = torch.randperm(n)
        n_val = int(n * args.val_frac)
        val_idx = perm[:n_val]
        train_idx = perm[n_val:]

    value_targets = returns if returns is not None else torch.zeros(n)
    train_ds = TensorDataset(
        obs[train_idx], masks[train_idx], actions[train_idx], value_targets[train_idx]
    )
    val_ds = TensorDataset(
        obs[val_idx], masks[val_idx], actions[val_idx], value_targets[val_idx]
    )
    train_loader = DataLoader(
        train_ds, batch_size=args.batch_size, shuffle=True,
        num_workers=0, pin_memory=(device.type == "cuda"),
    )
    val_loader = DataLoader(
        val_ds, batch_size=args.batch_size, shuffle=False,
        num_workers=0, pin_memory=(device.type == "cuda"),
    )
    print(f"[split] train={len(train_ds):,} val={len(val_ds):,}")

    # ---- Need num_card_ids from env (must match RL training!) ----
    tmp_env = HearthstoneEnv(
        max_tier=args.max_tier, card_vocab_scheme=args.card_vocab_scheme
    )
    num_card_ids = tmp_env.num_card_ids
    card_vocab_hash = tmp_env.card_vocab_hash
    dataset_vocab_hash = (
        str(data["card_vocab_hash"].item()) if "card_vocab_hash" in data else None
    )
    if dataset_vocab_hash is not None and dataset_vocab_hash != card_vocab_hash:
        raise ValueError(
            "BC dataset card vocabulary does not match the current environment: "
            f"dataset={dataset_vocab_hash}, current={card_vocab_hash}"
        )
    del tmp_env
    print(f"[env] num_card_ids={num_card_ids}")

    # ---- Model ----
    agent = HSTransformerAgent(
        n_actions=34,
        d_model=args.d_model,
        n_heads=args.n_heads,
        n_layers=args.n_layers,
        num_card_ids=num_card_ids,
        actor_type=args.actor_type,
    ).to(device)
    n_params = sum(p.numel() for p in agent.parameters())
    print(f"[model] {n_params:,} params")

    optimizer = torch.optim.AdamW(
        agent.parameters(), lr=args.lr, weight_decay=args.weight_decay
    )

    # ---- Wandb ----
    run = None
    if args.wandb:
        import wandb
        run = wandb.init(
            project=args.wandb_project,
            name=args.run_name or f"bc_{args.seed}",
            config=vars(args),
        )

    # ---- Train ----
    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    best_val_acc = 0.0
    global_step = 0
    t0 = time.time()

    for epoch in range(1, args.epochs + 1):
        agent.train()
        train_loss_sum = train_actor_loss_sum = train_value_loss_sum = 0.0
        train_correct, train_count = 0, 0
        for batch_obs, batch_mask, batch_act, batch_return in train_loader:
            batch_obs = batch_obs.to(device, non_blocking=True)
            batch_mask = batch_mask.to(device, non_blocking=True)
            batch_act = batch_act.to(device, non_blocking=True)
            batch_return = batch_return.to(device, non_blocking=True)

            action_logits, value_logits = agent(batch_obs)
            action_logits = action_logits.masked_fill(~batch_mask, -1e8)
            actor_loss = F.cross_entropy(action_logits, batch_act)
            if returns is not None:
                target_twohot = encode_twohot(batch_return, agent.bins)
                value_loss = -(
                    target_twohot * F.log_softmax(value_logits, dim=-1)
                ).sum(dim=-1).mean()
            else:
                value_loss = torch.zeros((), device=device)
            loss = actor_loss + args.critic_coef * value_loss

            optimizer.zero_grad()
            loss.backward()
            nn.utils.clip_grad_norm_(agent.parameters(), args.max_grad_norm)
            optimizer.step()

            train_loss_sum += loss.item() * batch_act.size(0)
            train_actor_loss_sum += actor_loss.item() * batch_act.size(0)
            train_value_loss_sum += value_loss.item() * batch_act.size(0)
            train_correct += (action_logits.argmax(-1) == batch_act).sum().item()
            train_count += batch_act.size(0)
            global_step += batch_act.size(0)

        train_loss = train_loss_sum / max(1, train_count)
        train_actor_loss = train_actor_loss_sum / max(1, train_count)
        train_value_loss = train_value_loss_sum / max(1, train_count)
        train_acc = train_correct / max(1, train_count)

        # ---- Val ----
        agent.eval()
        val_loss_sum, val_correct, val_count = 0.0, 0, 0
        with torch.no_grad():
            for batch_obs, batch_mask, batch_act, _batch_return in val_loader:
                batch_obs = batch_obs.to(device, non_blocking=True)
                batch_mask = batch_mask.to(device, non_blocking=True)
                batch_act = batch_act.to(device, non_blocking=True)
                action_logits, _ = agent(batch_obs)
                action_logits = action_logits.masked_fill(~batch_mask, -1e8)
                loss = F.cross_entropy(action_logits, batch_act)
                val_loss_sum += loss.item() * batch_act.size(0)
                val_correct += (action_logits.argmax(-1) == batch_act).sum().item()
                val_count += batch_act.size(0)

        val_loss = val_loss_sum / max(1, val_count)
        val_acc = val_correct / max(1, val_count)
        elapsed = time.time() - t0

        print(
            f"[ep {epoch:2d}/{args.epochs}] "
            f"train_loss={train_loss:.4f} actor={train_actor_loss:.4f} "
            f"critic={train_value_loss:.4f} acc={train_acc:.3f}  "
            f"val_loss={val_loss:.4f} acc={val_acc:.3f}  "
            f"({elapsed:.0f}s)"
        )

        if run is not None:
            run.log({
                "bc/train_loss": train_loss,
                "bc/train_actor_loss": train_actor_loss,
                "bc/train_value_loss": train_value_loss,
                "bc/train_acc": train_acc,
                "bc/val_loss": val_loss,
                "bc/val_acc": val_acc,
                "bc/epoch": epoch,
            }, step=global_step)

        # ---- Save best ----
        if val_acc > best_val_acc:
            best_val_acc = val_acc
            torch.save({
                "model": agent.state_dict(),
                "global_step": 0,
                "args": vars(args),
                "val_acc": val_acc,
                "card_vocab_hash": card_vocab_hash,
                "teacher_weights_sha256": teacher_weights_sha256,
            }, out_path)
            print(f"  [save] {out_path} (val_acc={val_acc:.3f})")

    print(f"[done] best val_acc={best_val_acc:.3f}, ckpt: {out_path}")
    if run is not None:
        run.finish()


if __name__ == "__main__":
    main()
