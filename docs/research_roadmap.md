# HS Autobattler research roadmap

Last updated: 2026-09-21

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

### S1. Policy league — COMPLETE

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

Promotion 1/3: a three-seed 32,768-step pilot selected `pilot_s73`, which then
improved paired mean placement by +2.033, 95% CI [+1.771, +2.304], on 240
disjoint holdout lobbies. It improved against all six archived opponents and
passed the gate. Two further consecutive promotions are required.

Promotion 2/3: three more matched seeds selected `round2_s142`. On 240 new
holdout lobbies it improved paired mean placement by +0.779, 95% CI [+0.546,
+1.013], and improved pairwise score against every one of seven archived
opponents. One further consecutive promotion is required.

Promotion 3/3: `round3_s217` passed the predeclared gate on another 240-lobby
holdout. Mean pairwise score improved +0.0218 and worst-opponent regression was
-0.0100. Mean placement improved +0.154, but its 95% CI [-0.008, +0.321]
crossed zero; this final step is therefore a gate pass, not evidence of a
statistically clear placement gain. S1 is complete.

## Phase M — representation and planning

### M1. Centralized critic and auxiliary combat tasks — COMPLETE (HYPOTHESES NOT SUPPORTED)

- Public-information actor, privileged training-only critic.
- Combat outcome and expected-damage auxiliary heads.
- Ablate auxiliary representation learning against oracle reward shaping.

Progress: the 8,282-value privileged critic observation, centralized value
encoder, public-feature combat outcome/damage heads, and league-PPO losses are
implemented. Deterministic CRN lobby-oracle shaping is also wired into the same
trainer. Leakage, repeatability, end-to-end training, and checkpoint reload
smokes pass. See
`docs/m1_central_critic.md`.

Result: a five-condition, three-seed pilot found only a small centralized-
critic signal and no additive auxiliary/oracle benefit. A 32,768-step,
three-seed confirmation reversed the central-critic signal: mean placement was
2.852 versus 2.705 for the public critic, with much higher seed variance. Both
were worse than the unchanged parent at 2.233. No M1 policy was promoted.

### M2. Search — COMPLETE (HYPOTHESIS NOT SUPPORTED)

- Deterministic Tavern snapshot/restore.
- Depth-1 action evaluation, then policy/value-guided MCTS.
- Multiple determinizations for random shop outcomes.

Gate: search improves matched holdout performance enough to justify latency.

Result: deterministic snapshot/restore and a public-information depth-one
planner were implemented. On 40 paired lobbies, search changed mean placement
from 3.900 to 4.625 (delta -0.725, 95% CI [-1.575, +0.100]) while increasing
inference latency from 3.44 to 80.16 ms/decision. The gate failed, so deeper
MCTS was not implemented. See `docs/m2_search.md`.

## Phase F — fidelity and generalization

The next objective is external validity beyond the frozen Tier-3 simulator.
See `docs/phase_f_fidelity_roadmap.md` for deliverables and gates.

### F0. Executable content and fidelity audit — COMPLETE

- Machine-readable mechanic/handler/test manifest for every card and spell.
- Explicit verified/partial/unsupported classifications.
- Benchmark construction rejects silent unsupported mechanics.

Gate: every card in a proposed active pool is handler-complete and covered by
deterministic scenario tests.

Result: all 257 configured entries are audited. A strict behavior-v6 Tier-3
profile admits 53 shop minions, 4 next-tier discovery minions, and 5 Tavern
spells; every admitted item is scenario-verified and every exclusion is
explicit. A 1,000-lobby conservation smoke passed.

### F1. Verified full-tier lobby — COMPLETE

Gate: behavior-contract v6 plus 100,000 conservation-safe Tier-6 lobbies.

Result: the verified full-tier profile passed 100,000 lobbies at 29.1 games/s,
21.38 average rounds, and 12.281%--12.698% seat win shares. See
`docs/f1_fulltier_lobby.md` and `benchmarks/hsbg_8p_fulltier_v1.json`.

### F2. Curated hero and armor system — COMPLETE

Gate: 8--16 scenario-tested heroes and a validated matchup matrix.

Result: eight versioned reference heroes, armor-first damage, observation/action
schema v2, and active/passive/target/cooldown/once mechanics are implemented.
A 4,000-lobby rotating-seat matrix passed the balance gate. See
`docs/f2_hero_system.md` and `benchmarks/hsbg_8p_heroes_v1.json`.

### F3. External trace conformance — NEXT, DATA-DEPENDENT

Gate: 10,000+ real recruit transitions with at least 99.5% agreement on
deterministic state fields.

### F4. Content curriculum and policy transfer — PENDING

Gate: improve full-tier holdouts without losing more than two score points on
the frozen Tier-3 benchmark.

### F5. Held-out content and patch generalization — PENDING

Gate: multi-seed improvement across unseen card/hero/configuration splits with
no catastrophic archived-configuration regression.

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
