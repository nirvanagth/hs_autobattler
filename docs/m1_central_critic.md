# M1 centralized critic and combat auxiliaries

Date: 2026-09-21
Status: in progress

## Hypotheses

1. A training-only centralized critic can reduce value-target variance without
   leaking private information into the deployed actor.
2. Predicting the next combat outcome and normalized signed damage from public
   actor features can improve the representation more reliably than turning a
   simulator estimate directly into reward.

## Implemented data path

- The actor input remains the frozen 2,958-value public observation.
- The optional critic input contains every seat's current Tavern state,
  including board, hand, shop, discovery state, alive flag, and ready flag.
  Its size is 8,282 values and it is never passed to the actor or auxiliary
  heads.
- Every successfully completed recruit turn exposes a three-class combat
  outcome and signed applied damage divided by the 15-point damage cap.
- Optional outcome and damage heads consume only public actor features.
- Optional deterministic oracle shaping evaluates the learner against the
  scheduled opponent's training-only current board. It reuses one Monte Carlo
  seed throughout a recruit turn and applies a potential difference, so no
  private feature is added to the deployed actor.
- League PPO supports independent `--central-critic`, `--auxiliary-coef`, and
  `--damage-coef` switches. Older checkpoints load without the new heads, and
  resulting checkpoints retain enough architecture metadata for evaluation.

## Leakage and execution checks

Tests establish that changing an unseen opponent shop changes the centralized
critic observation but leaves the actor observation unchanged. Actor logits
are identical for different critic-only inputs. A 128-step centralized-critic
plus auxiliary-loss smoke completed at 28.3 steps/s and its checkpoint was
successfully loaded into the normal public-observation evaluator.

Smoke checkpoint SHA-256:

```text
a35ea06cebfec3b6263cabd43d924325cc6c0ee0dd1aaf71174f923b4f31d7bd
```

This smoke is not performance evidence.

A separate 128-step centralized-critic plus 16-sample oracle smoke also passed.
Checkpoint SHA-256:

```text
3f2d1a811a7fec7d30b3a3015c9433422dbc2b05c2c566f8619d23086582dd29
```

## Planned matched ablation

Hold the S1 `round3_s217` parent, league, seed set, budget, and evaluation
schedule fixed. Compare:

1. public critic, no auxiliary loss;
2. centralized critic, no auxiliary loss;
3. centralized critic plus combat outcome/damage auxiliaries;
4. centralized critic plus deterministic combat-oracle reward;
5. centralized critic plus both auxiliaries and oracle reward.

Run three training seeds per condition. Select using a frozen selection set and
make claims only on a disjoint holdout set.
