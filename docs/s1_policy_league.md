# S1 policy league

Date: 2026-09-20
Status: in progress

## Research question

Can population training improve an eight-player policy against a diverse,
archived holdout set without hiding a regression behind performance against
one fixed bot?

## Implemented foundation

- Immutable policy entries bind an ID to an artifact SHA-256, policy kind,
  environment contract, and metadata.
- Aggregate Elo updates are order independent. A batch is updated from its
  observed score rate with square-root game-count weighting.
- PFSP samples opponents in deterministic policy-ID order with weight
  `(1 - learner_score_rate)^2` and a nonzero exploration floor.
- Neural opponents with unequal environment contracts cannot be sampled or
  rated together. Heuristic adapters can explicitly support multiple contracts.
- Promotion requires results for at least three independent holdout policies,
  200 games for the candidate and incumbent against each holdout, positive
  mean score improvement, and no holdout regression worse than two points.
- `LobbyArena` keeps targeting and action-budget state separate for every seat,
  so archived neural policies can act together in one shared-pool lobby.
- Mixed-lobby evaluation rotates the candidate seat, samples the other seven
  seats with PFSP, records full placements, and derives per-opponent pairwise
  outcomes for the league.

## Local population

The gitignored registry `artifacts/league/lobby_v1.json` contains:

- SmartBot (`smart_lobby_v1`);
- feed-forward E2 checkpoints for seeds 17, 42, and 73;
- GRU E2 checkpoints for seeds 17, 42, and 73.

The canonical feed-forward seed 42 policy is the bootstrap main. This is only
an initial reference and did not pass a promotion gate. Registry SHA-256 before
recording any league games:

```text
89342513ddf07f4038fac36ffc7096b3eb03123370dc0a3f6ea25e08042177d2
```

## Smoke result

Command:

```bash
PYTHONPATH=src:cpp/build:. .venv/bin/python \
  scripts/evaluate_lobby_league.py \
  --league artifacts/league/lobby_v1.json \
  --candidate ff_s42 --episodes 2 --seed-base 219000 --device cpu \
  --out artifacts/league/smoke_ff_s42.json
```

Both mixed-policy lobbies terminated with unique complete placements. The
candidate placed fourth and sixth. This run verifies execution only and is too
small for a performance claim. Report SHA-256:

```text
159c6973e88aadb0e61eb4ceac1d1595e25215c0f7ce12faa10af8a0a0f1e565
```

## Next experiment

`LeagueLobbyEnv` now rotates the learner seat, samples seven archived opponents
with PFSP, preserves seat-order recruit decisions, and returns round plus final
placement rewards. `scripts/train_lobby_league_ppo.py` initializes the
feed-forward learner from an immutable parent and applies conservative PPO with
teacher KL. It refuses to overwrite a candidate and stores the league and
parent hashes in the checkpoint.

A 128-step CPU smoke from `ff_s42` completed one rollout/update at 52.6 steps/s
and saved a reloadable checkpoint. Its SHA-256 is:

```text
ccef4b1e489ad7028868ec5e07af2fd727554ceedbd9ad321a618216eac7630d
```

This smoke is an execution check, not a performance result. The next experiment
is a fixed-budget, multi-seed training run followed by disjoint selection and
holdout schedules. S1 stays open until three consecutive gated promotions
succeed. Failed candidates and all per-opponent outcomes remain in the league.

For paired evaluation, `scripts/make_lobby_league_schedule.py` freezes every
seed, candidate seat, and seven-opponent lineup before any candidate is tested.
`evaluate_lobby_league.py --schedule ...` verifies the source-league hash, so
the parent and all candidates face exactly the same realized lobby contexts.

## Promotion round 1

Three 32,768-step pilot runs started from `ff_s42`. On the common 40-lobby
selection schedule, mean placements were 2.75, 2.35, and 2.20 for seeds 17,
42, and 73, versus 4.65 for the parent. Seed 73 was selected before opening the
holdout schedule.

On 240 disjoint holdout lobbies, `pilot_s73` achieved mean placement 2.804,
82.9% Top-4, and 30.0% wins. The parent achieved 4.838, 46.3%, and 7.9%.
Paired placement improvement was +2.033 with a 95% bootstrap interval of
[+1.771, +2.304]. Pairwise score improved against all six archived opponents;
the mean improvement was +0.290 and the worst was +0.245. Every opponent had
273--297 comparisons for each policy.

The guarded promotion gate passed and `pilot_s73` became league main. This is
the first of three successive promotions required to complete S1. Exact hashes
and metrics are frozen in `benchmarks/hsbg_league_s1_v1.json`.
