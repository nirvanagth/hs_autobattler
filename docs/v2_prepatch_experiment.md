# Model V2 pre-patch experiment

Date: 2026-09-19  
Code: `8fd02f5` (`main`)  
Purpose: validate the entity-aligned pointer actor and conservative PPO before
the 2026-09-22 pool update. These numbers describe the frozen pre-patch 1v1
environment, not live eight-player Battlegrounds performance.

## Artifacts

| Artifact | SHA-256 |
|---|---|
| `artifacts/v2_prepatch/bc_dataset.npz` | `4e730f9ef8bc8522864d3115a6523c1618ee9873f3391e931b0ea64b213bcb0b` |
| `artifacts/v2_prepatch/bc_pretrain.pt` | `b6688851f324ffd64df08c1dc2591ef8602ecf3c6c9cb31a58bfc37b2d7c4877` |
| `artifacts/v2_prepatch/ppo_bc_1m/final.pt` | `b35af0073e0ca687d351ae3b264eb9c9b39148e6598f63ffb37897906163c4bb` |
| `artifacts/es_bot/best.npz` | `0b18c9a10e2da4fc2cc04104003ae8d75e5c0bfdb68449acc169c559db8ed7c1` |

Artifacts are intentionally gitignored. The tracked JSON evaluation reports
are also stored under `artifacts/v2_prepatch/` locally.

## Behavior cloning

- 5,000 ES episodes, 640,267 decisions.
- Stable-v1 card vocabulary and episode-level train/validation split.
- Mean terminal board power: 28.64; maximum: 71.2.
- Pointer actor plus categorical critic, 15 epochs.
- Best held-out action accuracy: 99.2%.

Paired-seat evaluation:

| Candidate | Opponent | Games | W-L-D | Win rate | HP diff |
|---|---:|---:|---:|---:|---:|
| Pointer BC | New ES | 200 | 118-82-0 | **59.0%** | +4.7 |
| Pointer BC | SmartBot | 200 | 167-32-1 | **83.5%** | +20.7 |

The old flat BC had 83.8% transition-level validation accuracy and measured
about 46% against SmartBot in a 50-game smoke test. The pointer actor therefore
improves both imitation accuracy and actual play strength.

## PPO experiments

The first pilot used the earlier entropy schedule (`0.04 -> 0.01`). Entropy
grew from 0.06 to 0.71 and rollout reward became negative by 410k steps. It was
stopped after preserving 164k and 328k checkpoints. The 328k checkpoint scored
43% against ES and 79% against SmartBot.

A BC-teacher KL term was then added in commit `8fd02f5`. A 1M-step run used:

```text
lr=3e-5
entropy=0.005 -> 0.001
bc_kl_coef=0.1
bc_kl_decay_frac=2.0
opponents=50% new ES / 50% SmartBot
```

This kept rollout reward positive and policy entropy below 0.13. It prevented
catastrophic forgetting, but did not improve the policy beyond BC:

| Candidate | Opponent | Games | W-L-D | Win rate | HP diff |
|---|---:|---:|---:|---:|---:|
| PPO 1M final | New ES | 200 | 99-101-0 | **49.5%** | +0.4 |
| PPO 1M final | SmartBot | 200 | 165-34-1 | **82.5%** | +19.9 |

The 50-game checkpoint sweep was too noisy: the final checkpoint initially
scored 62% against ES, but the 200-game paired result was 49.5%. Promotion must
therefore use at least 200 paired-seat games and confidence intervals.

## Decision

1. Keep `bc_pretrain.pt` as the current best pre-patch policy.
2. Do not extend the present PPO run to 5M steps.
3. Improve action-level credit assignment before the next PPO run. The next
   experiment should wire a deterministic, common-random-number C++ combat
   potential into the reward and ablate sparse reward versus potential shaping.
4. Preserve the BC-teacher KL path as a safety constraint.
5. Re-audit the card pool after the 2026-09-22 patch before training a candidate
   intended to track the live game.
