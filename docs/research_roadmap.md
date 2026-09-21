# HS Autobattler research roadmap

Last updated: 2026-09-20

## Objective

Build a reproducible auto-battler research platform that can support credible
claims about structured policies, covariate shift, reinforcement learning,
self-play, partial observability, and search. Progress is gated by experiments;
model or environment complexity is not added without a measurable reason.

## Operating rules

1. Freeze and hash the environment, card vocabulary, teacher, dataset, and
   checkpoint for every experiment.
2. Use paired player-0/player-1 evaluation and separate selection/holdout seeds.
3. Promote a policy only after at least 200 paired games per primary opponent.
4. Report raw outcomes, confidence intervals, HP margin, and per-action metrics.
5. Change one research variable per matched experiment.
6. Update `docs/research_context.md` after every completed task or decision.
7. Keep artifacts under versioned gitignored directories; commit their hashes
   and the tracked result summary.

## Phase R — research-grade 1v1 benchmark

### R0. Structured imitation foundation — COMPLETE

- Entity-aligned pointer actor and stable card vocabulary.
- Episode-level BC with critic pretraining.
- Deterministic paired-seat evaluation.
- BC-teacher KL for conservative PPO.
- Deterministic common-random-number MC-oracle reward.
- DAgger collection and aggregation.

Gate result: Pointer BC reached 59.0% vs new ES and 83.5% vs SmartBot;
DAgger R1 reached 58.0% vs ES and 87.5% vs SmartBot.

### R1. Recovery benchmark — COMPLETE (HYPOTHESIS NOT SUPPORTED)

Research question: does DAgger improve recovery from learner-induced errors?

Deliverables:

- `scripts/evaluate_recovery.py` with deterministic expert prefixes.
- Controlled perturbations: wrong buy, sell strongest, wasted roll, premature
  end, and random non-expert legal action.
- Raw per-seed results and paired recovery deltas.
- Comparison of Pointer BC and DAgger R1 against SmartBot and ES.

Gate:

- At least 100 paired seeds per perturbation during development and 200 for the
  final claim.
- DAgger must improve mean recovery score or reduce recovery degradation on
  holdout seeds without losing more than two win-rate points on clean play.

Result: the tooling and paired raw-result benchmark were completed for turn-5
errors against SmartBot and ES (100 seeds each). DAgger recovery advantages were
small and every 95% interval crossed zero. The gate was not met, so the result
was recorded as negative and the experiment was not expanded to 200 seeds.

### R2. Matched representation and learning ablations — COMPLETE

Train at least three seeds with identical data and budgets:

- Flat BC.
- Pointer BC.
- Pointer BC + DAgger (weights 1x, 5x, 10x).
- Pointer BC + sparse PPO.
- Pointer BC + KL-PPO.
- Pointer BC + KL-PPO + oracle potential.

Gate: publish mean, standard deviation, paired confidence intervals, wall-clock
cost, and parameter count. No conclusion may rely on a single training seed.

Progress:

- **R2-A representation — COMPLETE.** Three matched seeds showed Pointer versus
  Flat gains of +16.1 action-accuracy points, +40.8 ES win-rate points, and
  +37.5 SmartBot win-rate points. See `docs/r2_representation_ablation.md`.
- **R2-B DAgger disagreement weights — COMPLETE.** Three matched seeds selected
  5x as the balanced default: 60.67 ± 1.04% vs ES and 87.00 ± 0.87% vs
  SmartBot. See `docs/r2_dagger_weight_ablation.md`.
- **R2-C PPO/reward variants — COMPLETE.** KL-PPO was the only condition to
  improve both opponent means over the 5x DAgger parent. Oracle consistently
  reduced ES performance versus matched KL. See `docs/r2_ppo_ablation.md`.

### R3. Freeze the benchmark — COMPLETE

- Assign an explicit environment behavior version and fixed card-pool snapshot.
- Add raw-result export, Wilson intervals, paired bootstrap, and policy rating.
- Produce a one-command experiment runner and immutable experiment manifest.

Gate: a fresh checkout can reproduce a smoke run and validate artifact hashes.

Result: `benchmarks/hsbg_1v1_v1.json` freezes behavior v2, schemas, pool,
opponents, dataset, and evaluation suite. New artifacts enforce the contract;
evaluation stores raw episodes, Wilson intervals, and paired bootstraps; the
one-command verifier passed. See `docs/r3_benchmark_freeze.md`.

## Phase E — full environment structure

### E1. Restricted-pool eight-player skeleton — COMPLETE

- Eight players, shared pool, pairings, ghosts, damage cap, elimination, and
  placement reward.
- Start with a Tier-3 frozen pool; content completeness is a separate axis.

Gate: 100,000 bot games without pairing, pool, elimination, or conservation
violations.

Result: 100,000/100,000 SmartBot lobbies passed at 32.1 games/s with 24.31
average rounds and near-uniform seat winners. See `docs/e1_lobby_core.md`.

### E2. Public opponent information and memory — COMPLETE (NO GRU GAIN)

- Last-seen boards, turns-since-seen, health/armor, and opponent identity.
- Recurrent memory benchmark versus feed-forward policies.

Result: public-information observations and next-opponent scheduling were
implemented. Three matched seeds found no stable GRU benefit: feed-forward mean
placement 4.713 versus GRU 4.770, with paired intervals crossing zero. See
`docs/e2_memory_benchmark.md`.

## Phase S — population self-play

### S1. Policy league — IN PROGRESS

- Historical checkpoints, ES variants, exploiters, PFSP sampling, and
  Elo/TrueSkill-style ratings.
- Promotion against the full league, not one fixed bot.

Gate: three successive promoted policies improve holdout league rating without
catastrophic regression against archived opponents.

Progress: the immutable registry, order-independent aggregate Elo, contract-
safe deterministic PFSP, multi-opponent promotion gate, per-seat action state,
and shared-pool mixed-policy evaluator are implemented. A seven-policy local
population passed a two-lobby execution smoke test. This is infrastructure,
not a promotion result. See `docs/s1_policy_league.md`.

## Phase M — representation and planning

### M1. Centralized critic and auxiliary combat tasks — PENDING

- Public-information actor, privileged training-only critic.
- Combat outcome and expected-damage auxiliary heads.
- Ablate auxiliary representation learning against oracle reward shaping.

### M2. Search — PENDING

- Deterministic Tavern snapshot/restore.
- Depth-1 action evaluation, then policy/value-guided MCTS.
- Multiple determinizations for random shop outcomes.

Gate: search improves matched holdout performance enough to justify latency.

## Promotion ladder

```text
unit tests
  -> deterministic smoke
  -> held-out action/recovery metrics
  -> 200+ paired games vs fixed suite
  -> multi-seed matched experiment
  -> league promotion
  -> larger environment
```
