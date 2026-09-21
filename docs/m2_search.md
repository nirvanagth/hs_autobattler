# M2 search

Date: 2026-09-21
Status: complete; depth-one hypothesis not supported

## Implementation

- `LobbyArena.snapshot()` captures a deep copy of the complete lobby, every
  seat's action/target state, and Python/NumPy RNG state.
- `LobbyArena.restore()` restores from a reusable snapshot, enabling common-
  random-number branches without mutating the live game.
- `DepthOnePlanner` expands every legal Tavern action, batches the resulting
  public observations through the policy/value network, and combines leaf
  value with a small policy-prior term.
- End-turn is evaluated as stopping in the current public state rather than
  simulating hidden opponents. Freeze-and-end evaluates the public frozen shop.
  Consequently search decisions do not gain access to private opponent state.
- Evaluation records actual inference latency and number of expanded actions.

Tests verify exact replay of a stochastic roll after restore, non-mutation of
the live state, legality of the selected action, and actor/critic information
separation.

## Result

The current `round3_s217` main was evaluated with and without depth-one search
on the same 40 lobby seeds, learner seats, and opponent lineups.

| Mode | Mean placement | Top-4 | Win | Latency/decision |
|---|---:|---:|---:|---:|
| Direct policy | 3.900 | 60.0% | 12.5% | 3.44 ms |
| Depth-one search | 4.625 | 50.0% | 20.0% | 80.16 ms |

The paired placement change was -0.725 with 95% CI [-1.575, +0.100]. Search
expanded 11.01 actions per decision and cost 23.3 times as much latency. The
win-rate increase is inconsistent with the worse placement and small sample.

The gate failed: depth-one value search did not improve robust placement and
was far more expensive. Deeper MCTS is not justified until a value model is
shown to rank counterfactual Tavern states accurately. Exact hashes are frozen
in `benchmarks/hsbg_m2_depth1_v1.json`.
