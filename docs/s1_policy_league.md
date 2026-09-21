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

Implement a league-aware eight-player learner, archive each candidate before
evaluation, then use fixed selection seeds and disjoint holdout seeds. S1 stays
open until three consecutive gated promotions succeed. Failed candidates and
all per-opponent outcomes remain part of the population.
