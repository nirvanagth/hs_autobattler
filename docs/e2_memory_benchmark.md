# E2 public information and memory benchmark

Date: 2026-09-20  
Benchmark: `hsbg_8p_tier3_v1`

## Environment

The 2,958-value observation contains:

- the controlled player's full Tavern state;
- all seven opponents' public health, Tavern tier, and alive state;
- the next scheduled opponent;
- each opponent's last board observed in combat;
- whether an opponent has ever been seen and turns since that observation.

Tests verify that mutating an unobserved current opponent board does not change
the observation. Pairings are scheduled at recruit start so next-opponent data
is public before actions are selected.

The stepwise SmartBot teacher initially averaged placement 6.1 because masked
invalid upgrade attempts were incorrectly converted to END. The action query
now lets the expert continue until its first legal action. A 500-game parity
check then produced mean placement 4.26 versus 4.5 for a symmetric seat.

## Dataset and training

- 2,000 eight-player games.
- 158,699 controlled-player decisions.
- Mean teacher placement 4.30; top-four rate 54.8%; win rate 13.75%.
- Dataset SHA-256:
  `34ac273db379bf049a6992cd4886f33e745d1b78ce8c92ebc21ee43f5acf6b5c`.
- Feed-forward and GRU policies share the same pointer encoder, data, complete
  episode batches, five epochs, and seeds 17/42/73.

## Results

| Model | Seed | Held-out accuracy | Mean placement | Top 4 | Win |
|---|---:|---:|---:|---:|---:|
| Feed-forward | 17 | 89.25% | 4.855 | 40.5% | 10.5% |
| Feed-forward | 42 | 88.00% | 4.875 | 43.5% | 6.5% |
| Feed-forward | 73 | 89.07% | 4.410 | 50.0% | 13.0% |
| GRU | 17 | 90.18% | 4.430 | 49.0% | 14.0% |
| GRU | 42 | 89.81% | 4.730 | 44.0% | 12.0% |
| GRU | 73 | 88.45% | 5.150 | 35.0% | 7.0% |

Across training seeds:

| Model | Mean placement | Top 4 | Win |
|---|---:|---:|---:|
| Feed-forward | **4.713 ± 0.263** | **44.67 ± 4.86%** | 10.00 ± 3.28% |
| GRU | 4.770 ± 0.362 | 42.67 ± 7.09% | **11.00 ± 3.61%** |

Pooling all 600 paired episodes, GRU placement improvement was -0.057 with a
95% bootstrap interval [-0.212, +0.095]. Top-four advantage was -2.0 points
[-5.67, +1.67], and win advantage was +1.0 point [-1.5, +3.5].

## Decision

E2 does not establish a stable recurrent-memory benefit. The explicit
last-seen board state may already be close to sufficient for this memoryless
SmartBot teacher, and seed73 regressed strongly. Keep feed-forward as the
default lobby imitation policy. Revisit GRU only after population self-play
creates opponent-dependent behavior that can reward temporal inference.

