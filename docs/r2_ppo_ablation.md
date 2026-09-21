# R2-C matched PPO and reward ablation

Date: 2026-09-20  
Parent policies: corresponding-seed 5x DAgger checkpoints  
Source commit: `4bc77f5`

## Contract

- Variants: plain PPO, BC-teacher KL PPO, and KL PPO + deterministic MC oracle.
- Seeds: 17, 42, 73.
- 327,680 environment steps per run.
- Learning rate 3e-5; entropy 0.005 -> 0.001.
- Eight environments, 2,048 rollout steps, 16 minibatches.
- Mixed opponents: 50% new ES and 50% SmartBot.
- KL coefficient 0.1 with decay fraction 2.0 where enabled.
- Oracle: 64 common-random-number combats, scale 1.0.
- Evaluation: 200 paired-seat games per opponent; seed base 80,000.

Manifest SHA-256:
`0b2ca4e0084316bdd6394a846d43d4d3a4049c9e53cf4c91a9307ff0e6f34a6a`

## Results

| Variant | Seed | ES win rate | SmartBot win rate |
|---|---:|---:|---:|
| Plain PPO | 17 | 60.0% | 85.5% |
| Plain PPO | 42 | 62.5% | 85.0% |
| Plain PPO | 73 | 58.5% | 88.0% |
| KL-PPO | 17 | 60.0% | 88.5% |
| KL-PPO | 42 | 62.0% | 88.5% |
| KL-PPO | 73 | 63.5% | 87.5% |
| KL+Oracle | 17 | 59.5% | 88.0% |
| KL+Oracle | 42 | 60.5% | 88.5% |
| KL+Oracle | 73 | 61.0% | 88.0% |

Mean ± sample standard deviation:

| Variant | ES win rate | SmartBot win rate | Mean train FPS |
|---|---:|---:|---:|
| 5x DAgger parent | 60.67 ± 1.04% | 87.00 ± 0.87% | — |
| Plain PPO | 60.33 ± 2.02% | 86.17 ± 1.61% | 579 |
| KL-PPO | **61.83 ± 1.76%** | **88.17 ± 0.58%** | 536 |
| KL+Oracle | 60.33 ± 0.76% | **88.17 ± 0.29%** | 518 |

Plain PPO does not improve the parent mean and increases variance. KL-PPO
improves SmartBot performance for every seed and gives +1.17 points on both
opponent means. Oracle is 0.5, 1.5, and 2.5 ES points below corresponding KL
runs, does not improve SmartBot mean, and reduces throughput.

With three seeds the KL effect remains modest. Treat it as the promoted
configuration for the next stage, not as a definitive general RL claim. Oracle
is a consistent negative result at scale 1.0.

## Promoted artifacts

- KL seed17: `2adc6ebe2c56e20ad28ecacc7725f13e96b90df44bd1ba71ecc393c1614512a8`
- KL seed42: `9b2428d2c8e6e2224c132c265d5f50a478579df46a99175efc7494ca032ca51b`
- KL seed73: `aa2a07ba7e8605dadae7bf6a5931d12c37dc422353f708f0b278708db19a2178`

## Decision

R2-C passes its configuration-selection gate. Use 5x DAgger initialization plus
teacher-KL PPO as the default online fine-tuning path. Keep Oracle available as
an ablation, but do not enable it by default. Proceed to benchmark freeze R3.
