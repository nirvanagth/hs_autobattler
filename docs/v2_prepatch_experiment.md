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
| `artifacts/v2_prepatch/ppo_oracle_1m/ckpt_327680.pt` | `b234ba91069efed9c54727cf46d563d3a044e1aed4580749d010e74763b2f6b5` |
| `artifacts/v2_prepatch/ppo_oracle_1m/final.pt` | `ad5a0c61d41fa1b366378b89f1c6e68739e46ea146fe3b15a918f742a8841aab` |
| `artifacts/v2_prepatch/dagger_round1.npz` | `e32dd99561b7fb7436bb42b2f56c228b5d72c5d4ee14bfa1c80fe3ffdf86cff6` |
| `artifacts/v2_prepatch/bc_dagger_round1.npz` | `baa923563f9d1a480f805a0889476932aeddc857987ef43cfc7bce88a0f1212b` |
| `artifacts/v2_prepatch/bc_dagger_round1.pt` | `a4c05fc416e4af9ead9837950c3e365a11d05c50764ffe07fee2cd35e4b5fb6c` |
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

## Deterministic MC-oracle ablation

Commit `f7a64f0` wired the C++ combat oracle into a potential-based reward:

```text
r_oracle = scale * (gamma * Phi(next_state) - Phi(current_state))
Phi = expected combat score from 64 simulations
```

The opponent board and combat base seed are frozen within each Tavern turn, so
adjacent board states use common random numbers. Oracle RNG is isolated from
game RNG; sparse and oracle benchmarks produced identical action trajectories.
Environment-only throughput fell from about 10.7k to 6.35k steps/s, while full
PPO throughput fell from about 570 to 494 FPS. Mean shaping stayed near zero,
with mean absolute per-action shaping about 0.055 at scale 1.0.

The oracle run used the same 1M-step PPO settings and initialization as the
sparse run. Paired-seat confirmation results:

| Candidate | Opponent | Games | W-L-D | Win rate | HP diff |
|---|---:|---:|---:|---:|---:|
| Oracle PPO 328k | New ES | 200 | 118-82-0 | **59.0%** | +4.7 |
| Oracle PPO 328k | SmartBot | 100 | 84-16-0 | **84.0%** | +22.0 |
| Oracle PPO 819k | New ES | 200 | 113-86-1 | **56.5%** | +3.7 |
| Oracle PPO 819k | SmartBot | 100 | 84-15-1 | **84.0%** | +21.6 |

The early oracle checkpoint matches BC against ES and is nominally +0.5 points
against SmartBot, which is not statistically significant. Longer oracle
training again drifts below BC. Deterministic potential shaping is therefore a
safe credit signal at this scale, but not yet a demonstrated policy improvement.

## DAgger round 1

Commit `45f1ba5` added learner-state collection, RNG-neutral ES queries,
episode-safe aggregation, checkpoint fine-tuning, and 5x loss weight for
learner/expert disagreements.

- Learner: the best pointer BC checkpoint.
- 2,000 learner-controlled episodes (`beta=0`).
- Mixed opponents: 50% new ES and 50% SmartBot.
- 297,593 learner-visited states; 1.4% learner/expert disagreement.
- Aggregated dataset: 914,721 rows, 30.0% DAgger.
- Five fine-tuning epochs at `lr=1e-4`.
- Held-out accuracy: 99.3% overall, 99.4% base, 99.2% DAgger.

Paired-seat evaluation:

| Candidate | Opponent | Games | W-L-D | Win rate | HP diff |
|---|---:|---:|---:|---:|---:|
| DAgger R1 | New ES | 200 | 116-81-3 | **58.0%** | +4.6 |
| DAgger R1 | SmartBot | 200 | 175-25-0 | **87.5%** | +22.5 |

Compared with pointer BC, DAgger is -1 point against ES (not significant at
this sample size) and +4 points against SmartBot. This supports the intended
benefit: recovery on learner-induced states improved without a large loss on
the expert distribution.

The collector exposed an environment deadlock: once the per-turn action cap
was reached, END incorrectly masked out mandatory Discover choices, while
`step()` rejected END during discovery. This produced 741 repeated invalid
labels across a few truncated episodes. Training dropped those rows, and commit
`3070d0b` moved the action-cap rule behind Discover/targeting masks.

## Decision

1. Keep `bc_pretrain.pt` as the strongest ES-facing policy and
   `bc_dagger_round1.pt` as the strongest mixed-opponent policy.
2. Do not extend the present PPO run to 5M steps.
3. Keep deterministic oracle shaping available, but do not promote it as an
   improvement based on this run. The next credit-assignment experiment should
   use an auxiliary combat/value objective or a second DAgger round collected
   after the mandatory-choice fix rather than simply extending PPO.
4. Preserve the BC-teacher KL path as a safety constraint.
5. Re-audit the card pool after the 2026-09-22 patch before training a candidate
   intended to track the live game.
