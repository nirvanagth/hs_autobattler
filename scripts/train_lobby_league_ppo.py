"""Conservative PPO for one learner seat against a PFSP lobby population."""

from __future__ import annotations

import argparse
import copy
import json
import random
import sys
import time
from pathlib import Path

import numpy as np
import torch
import torch.nn as nn
import torch.nn.functional as F
from torch.distributions import Categorical

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

from evaluate_checkpoints import resolve_device
from hearthstone.league import PolicyLeague, file_sha256
from lobby_league_runtime import LeagueLobbyEnv
from lobby_model import LobbyPointerAgent
from model import decode_value, encode_twohot
from train_ppo import compute_gae, get_ent_coef


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--league", required=True)
    parser.add_argument("--parent-id", required=True)
    parser.add_argument("--out", required=True)
    parser.add_argument("--total-timesteps", type=int, default=327_680)
    parser.add_argument("--n-steps", type=int, default=2048)
    parser.add_argument("--n-minibatches", type=int, default=8)
    parser.add_argument("--update-epochs", type=int, default=4)
    parser.add_argument("--lr", type=float, default=1e-4)
    parser.add_argument("--gamma", type=float, default=0.999)
    parser.add_argument("--gae-lambda", type=float, default=0.95)
    parser.add_argument("--clip-coef", type=float, default=0.2)
    parser.add_argument("--ent-coef", type=float, default=0.01)
    parser.add_argument("--ent-coef-end", type=float, default=0.002)
    parser.add_argument("--ent-decay-frac", type=float, default=0.75)
    parser.add_argument("--vf-coef", type=float, default=0.5)
    parser.add_argument("--bc-kl-coef", type=float, default=0.1)
    parser.add_argument("--bc-kl-decay-frac", type=float, default=0.75)
    parser.add_argument("--target-kl", type=float, default=0.03)
    parser.add_argument("--max-grad-norm", type=float, default=0.5)
    parser.add_argument("--pfsp-exponent", type=float, default=2.0)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--device", choices=("auto", "cpu", "mps"), default="auto")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    if args.total_timesteps < args.n_steps:
        raise ValueError("total timesteps must be at least one rollout")
    if args.n_steps % args.n_minibatches:
        raise ValueError("n-steps must be divisible by n-minibatches")
    output = Path(args.out).resolve()
    if output.exists():
        raise FileExistsError(f"refusing to overwrite immutable candidate: {output}")

    random.seed(args.seed)
    np.random.seed(args.seed)
    torch.manual_seed(args.seed)
    device = resolve_device(args.device)
    league_path = Path(args.league).resolve()
    league = PolicyLeague.load(league_path)
    parent = league.entries[args.parent_id]
    parent_path = Path(parent.artifact_path)
    parent_checkpoint = torch.load(parent_path, map_location=device)
    model_args = parent_checkpoint["args"]
    if bool(model_args["use_memory"]):
        raise ValueError("league PPO currently supports feed-forward learners only")

    env = LeagueLobbyEnv(
        league,
        args.parent_id,
        seed=args.seed,
        device=device,
        pfsp_exponent=args.pfsp_exponent,
    )
    if parent.environment_contract != env.lobby_environment_contract:
        raise ValueError("parent policy contract does not match league environment")
    agent = LobbyPointerAgent(
        num_card_ids=env.arena.env.num_card_ids,
        d_model=int(model_args["d_model"]),
        n_heads=int(model_args["n_heads"]),
        n_layers=int(model_args["n_layers"]),
        use_memory=False,
    ).to(device)
    agent.load_state_dict(parent_checkpoint["model"])
    teacher = copy.deepcopy(agent).eval()
    for parameter in teacher.parameters():
        parameter.requires_grad_(False)
    optimizer = torch.optim.Adam(agent.parameters(), lr=args.lr, eps=1e-5)

    observation_size = env.observation_space.shape[0]
    observations = torch.zeros((args.n_steps, observation_size), device=device)
    actions = torch.zeros(args.n_steps, dtype=torch.long, device=device)
    old_logprobs = torch.zeros(args.n_steps, device=device)
    rewards = torch.zeros(args.n_steps, device=device)
    dones = torch.zeros(args.n_steps, device=device)
    values = torch.zeros(args.n_steps, device=device)
    masks = torch.zeros((args.n_steps, env.action_space.n), dtype=torch.bool, device=device)

    next_observation_np, _ = env.reset(seed=args.seed)
    next_observation = torch.as_tensor(
        next_observation_np, dtype=torch.float32, device=device
    )
    total_updates = args.total_timesteps // args.n_steps
    minibatch_size = args.n_steps // args.n_minibatches
    global_step = 0
    episode_placements: list[int] = []
    started = time.time()

    for update in range(1, total_updates + 1):
        agent.eval()
        for step in range(args.n_steps):
            observations[step] = next_observation
            mask = torch.as_tensor(env.action_masks(), dtype=torch.bool, device=device)
            masks[step] = mask
            with torch.no_grad():
                logits, value_logits, _ = agent(next_observation.unsqueeze(0))
                distribution = Categorical(logits=logits.masked_fill(~mask.unsqueeze(0), -1e8))
                action = distribution.sample()
                value = decode_value(value_logits, agent.base.bins)
            actions[step] = action
            old_logprobs[step] = distribution.log_prob(action)
            values[step] = value
            next_observation_np, reward, terminated, truncated, info = env.step(
                int(action.item())
            )
            done = terminated or truncated
            rewards[step] = reward
            dones[step] = float(done)
            global_step += 1
            if done:
                if info["placement"] is not None:
                    episode_placements.append(int(info["placement"]))
                next_observation_np, _ = env.reset()
            next_observation = torch.as_tensor(
                next_observation_np, dtype=torch.float32, device=device
            )

        with torch.no_grad():
            _, next_value_logits, _ = agent(next_observation.unsqueeze(0))
            next_value = decode_value(next_value_logits, agent.base.bins)
        advantages, returns = compute_gae(
            rewards.unsqueeze(1),
            values.unsqueeze(1),
            dones.unsqueeze(1),
            next_value,
            args.gamma,
            args.gae_lambda,
        )
        advantages = advantages.squeeze(1)
        returns = returns.squeeze(1)

        agent.train()
        indices = np.arange(args.n_steps)
        ent_coef = get_ent_coef(
            update,
            total_updates,
            args.ent_coef,
            args.ent_coef_end,
            args.ent_decay_frac,
        )
        bc_kl_coef = args.bc_kl_coef * max(
            0.0,
            1.0 - update / max(1, int(total_updates * args.bc_kl_decay_frac)),
        )
        losses: list[float] = []
        approximate_kls: list[float] = []
        stop_early = False
        for _epoch in range(args.update_epochs):
            np.random.shuffle(indices)
            for start in range(0, args.n_steps, minibatch_size):
                batch = indices[start : start + minibatch_size]
                logits, value_logits, _ = agent(observations[batch])
                masked_logits = logits.masked_fill(~masks[batch], -1e8)
                distribution = Categorical(logits=masked_logits)
                new_logprob = distribution.log_prob(actions[batch])
                logratio = new_logprob - old_logprobs[batch]
                ratio = logratio.exp()
                with torch.no_grad():
                    approximate_kl = ((ratio - 1.0) - logratio).mean()
                    approximate_kls.append(float(approximate_kl))
                normalized_advantage = advantages[batch]
                normalized_advantage = (
                    normalized_advantage - normalized_advantage.mean()
                ) / (normalized_advantage.std() + 1e-8)
                policy_loss = torch.max(
                    -normalized_advantage * ratio,
                    -normalized_advantage
                    * torch.clamp(ratio, 1 - args.clip_coef, 1 + args.clip_coef),
                ).mean()
                value_target = encode_twohot(returns[batch], agent.base.bins)
                value_loss = -(
                    value_target * F.log_softmax(value_logits, dim=-1)
                ).sum(dim=-1).mean()
                with torch.no_grad():
                    teacher_logits, _, _ = teacher(observations[batch])
                    teacher_probs = F.softmax(
                        teacher_logits.masked_fill(~masks[batch], -1e8), dim=-1
                    )
                bc_kl = F.kl_div(
                    F.log_softmax(masked_logits, dim=-1),
                    teacher_probs,
                    reduction="batchmean",
                )
                loss = (
                    policy_loss
                    + args.vf_coef * value_loss
                    - ent_coef * distribution.entropy().mean()
                    + bc_kl_coef * bc_kl
                )
                optimizer.zero_grad()
                loss.backward()
                nn.utils.clip_grad_norm_(agent.parameters(), args.max_grad_norm)
                optimizer.step()
                losses.append(float(loss.detach()))
                if approximate_kl > 1.5 * args.target_kl:
                    stop_early = True
                    break
            if stop_early:
                break
        recent = episode_placements[-20:]
        print(
            f"[update {update}/{total_updates}] step={global_step} "
            f"loss={np.mean(losses):.4f} kl={np.mean(approximate_kls):.4f} "
            f"episodes={len(episode_placements)} "
            f"recent_place={np.mean(recent) if recent else float('nan'):.3f} "
            f"fps={global_step / (time.time() - started):.1f}",
            flush=True,
        )

    output.parent.mkdir(parents=True, exist_ok=True)
    training_contract = {
        "league_path": str(league_path),
        "league_sha256": file_sha256(league_path),
        "parent_id": args.parent_id,
        "parent_sha256": parent.artifact_sha256,
        "pfsp_exponent": args.pfsp_exponent,
        "seed": args.seed,
        "timesteps": global_step,
    }
    saved_args = dict(model_args)
    saved_args.update(vars(args))
    torch.save(
        {
            "model": agent.state_dict(),
            "optimizer": optimizer.state_dict(),
            "global_step": global_step,
            "args": saved_args,
            "lobby_environment_contract": env.lobby_environment_contract,
            "league_training_contract": training_contract,
            "episode_placements": episode_placements,
        },
        output,
    )
    summary_path = output.with_suffix(".json")
    summary_payload = json.dumps(
        {
            "schema_version": 1,
            "checkpoint": str(output),
            "checkpoint_sha256": file_sha256(output),
            "training_contract": training_contract,
            "episodes": len(episode_placements),
            "mean_placement": (
                float(np.mean(episode_placements)) if episode_placements else None
            ),
        },
        indent=2,
        sort_keys=True,
    )
    summary_temporary = summary_path.with_suffix(".tmp")
    summary_temporary.write_text(summary_payload)
    summary_temporary.replace(summary_path)
    print(f"[saved] {output}")


if __name__ == "__main__":
    main()
