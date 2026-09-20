# R2-A matched representation ablation

Date: 2026-09-20  
Source commit: `9b72cf8`  
Dataset: `artifacts/v2_prepatch/bc_dataset.npz`  
Dataset SHA-256: `4e730f9ef8bc8522864d3115a6523c1618ee9873f3391e931b0ea64b213bcb0b`

## Contract

- Variants: flat pooled actor versus entity-aligned pointer actor.
- Seeds: 17, 42, 73.
- 15 epochs, batch size 512, learning rate 3e-4.
- Same episode-level data split procedure and categorical critic objective.
- Evaluation: 200 paired-seat games against new ES and 200 against SmartBot.
- Shared holdout seed base: 80,000.
- Flat parameters: 2,238,753.
- Pointer parameters: 2,449,801.

Manifest SHA-256:
`d31ccacfd30a937ab65e82257fda3084b70df16d101258bfae920e0b3d228d40`

## Results

| Variant | Seed | Held-out action accuracy | ES win rate | SmartBot win rate |
|---|---:|---:|---:|---:|
| Flat | 17 | 82.68% | 17.5% | 54.0% |
| Flat | 42 | 83.59% | 14.0% | 46.0% |
| Flat | 73 | 82.83% | 11.5% | 46.5% |
| Pointer | 17 | 99.04% | 57.0% | 87.5% |
| Pointer | 42 | 99.16% | 56.5% | 84.0% |
| Pointer | 73 | 99.19% | 52.0% | 87.5% |

Mean ± sample standard deviation:

| Variant | Action accuracy | ES win rate | SmartBot win rate |
|---|---:|---:|---:|
| Flat | 83.03 ± 0.49% | 14.33 ± 3.01% | 48.83 ± 4.48% |
| Pointer | **99.13 ± 0.08%** | **55.17 ± 2.75%** | **86.33 ± 2.02%** |

Pointer minus Flat:

- +16.10 percentage points held-out action accuracy.
- +40.84 points ES win rate.
- +37.50 points SmartBot win rate.

The seed ranges do not overlap on any primary metric. Pointer has about 9.4%
more parameters, but that increase cannot explain the flat actor's proven
permutation-invariance failure: swapping Tavern entities leaves its fixed-slot
logits unchanged. A parameter-matched control can be added later, but the
structural representation claim already has direct invariance and gameplay
evidence.

## Artifact hashes

| Artifact | SHA-256 |
|---|---|
| Flat seed17 | `4799873d94feec5b46823c8e203771eea74fac8b3f03d88c16f55623ddddca10` |
| Flat seed73 | `313620767479151a7ef311dd907f7f1c728a2ee1564f41db1a3dbc95d738269c` |
| Pointer seed17 | `a7ca8743e52dab0169acb63faf68e804c97b73d6ee142ccc3957ddcbb5ef53dc` |
| Pointer seed73 | `c8421a2693b7e22693a4fdbeac3c169f25d6d7a914d8794d833ca0677f10de94` |

Seed42 artifacts are recorded in `docs/v2_prepatch_experiment.md`.

## Decision

R2-A passes its gate. The pointer actor is the default representation for all
future work. Flat remains only as a historical/control baseline. The next
matched subtask is R2-B: DAgger disagreement-weight ablation at 1x, 5x, and 10x.

