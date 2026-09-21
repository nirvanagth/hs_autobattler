# E1 restricted Tier-3 eight-player lobby core

Date: 2026-09-20

## Scope

`src/hearthstone/engine/lobby.py` adds a separate eight-player lifecycle without
modifying the frozen 1v1 `Game` API:

- eight players using one shared `CardPool`;
- deterministic greedy pairings that minimize repeats and immediate rematches;
- odd-player ghost combat using the latest eliminated board;
- simultaneous combat damage;
- 15-damage cap while more than four players remain;
- deterministic simultaneous-elimination tie breaking;
- complete placements 1 through 8;
- release of eliminated players' board, hand, store, golden, and magnetized
  pool copies;
- Tier-3 Tavern frontier for the first lobby research stage.

## Bugs exposed by shared-pool stress

1. Effect-golden minions were returned as three pool copies even when only one
   copy had been acquired. `Unit.pool_copies` now tracks exact provenance.
2. Effect-generated collectible minions were returned to the pool despite not
   being drawn from it. Generated/summoned units now carry zero pool copies.
3. A board-only triplet with a full hand removed three minions and discarded
   the Golden result. Formation is now deferred until hand space exists.
4. Simultaneous death of every remaining player left `winner_id=None`.
   Deterministic placement tie breaking now selects rank 1.
5. Discover candidate iteration used a hash-order-dependent set. Candidates are
   now sorted, making trajectories invariant to `PYTHONHASHSEED`.

These shared engine fixes advance the current 1v1 contract to behavior v5 and
the tracked runtime benchmark to `hsbg_1v1_v3`.

## Verification

Focused lobby tests: 9 passed.  
Full repository suite: 886 passed, 33 skipped.

Stress command:

```bash
PYTHONPATH=src:cpp/build:. .venv/bin/python scripts/stress_lobby.py \
  --games 100000 --seed 100000 --max-rounds 200 --log-every 5000
```

Result:

```text
100,000 / 100,000 games passed
32.1 games/second
24.31 average rounds
winners={0:12349, 1:12570, 2:12412, 3:12643,
         4:12672, 5:12522, 6:12268, 7:12564}
```

Every round checked participant uniqueness. Every game checked exact card-pool
conservation, bounded termination, winner validity, and complete unique
placements. The seat win shares range from 12.27% to 12.67%.

## Decision

E1 passes. The lifecycle core is ready to become an RL environment. E2 will add
public opponent observations (`last_seen_board`, health, tier, and
turns-since-seen) and a recurrent policy benchmark while preserving the frozen
1v1 contracts.

