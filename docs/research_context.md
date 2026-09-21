# HS Autobattler persistent research context

Last updated: 2026-09-20

This file is the handoff point for future work. Read it together with
`docs/research_roadmap.md` and `docs/v2_prepatch_experiment.md` before changing
the model, environment, reward, or training pipeline.

## Repository

- Actual checkout: `/Users/tianhaogu/Projects/hs_autobattler`
- Branch/remote: `main` tracking `mine/main`
- The Codex workspace path under `Documents/ChatGPT` is not this repository.
- Current tracked head when this context was written: `921d2ae` plus subsequent
  roadmap/R2 work.

Common command prefix:

```bash
cd /Users/tianhaogu/Projects/hs_autobattler
PYTHONPATH=src:cpp/build:. .venv/bin/python ...
```

## Current platform state

- Python Tavern engine and optional C++ combat engine.
- Frozen 1v1 benchmark plus a restricted-pool, 30-health eight-player lobby.
- 34-action masked policy.
- Pointer actor with stable-v1 card vocabulary.
- Episode-aware BC, categorical critic, conservative PPO, deterministic
  MC-oracle reward, and DAgger.
- Latest full test result before R1: 863 passed, 33 skipped.

Important commits:

- `9019ab8`: entity-aligned pointer pipeline.
- `8fd02f5`: BC-teacher KL PPO.
- `f7a64f0`: deterministic MC-oracle potential reward.
- `45f1ba5`: DAgger pipeline.
- `3070d0b`: mandatory Discover/target choices override action cap.
- `cab769f`: DAgger R1 result report.

## Current best artifacts

Artifacts are local and gitignored. Do not overwrite them.

### Pointer BC — strongest against ES

Path: `artifacts/v2_prepatch/bc_pretrain.pt`  
SHA-256: `b6688851f324ffd64df08c1dc2591ef8602ecf3c6c9cb31a58bfc37b2d7c4877`

- 59.0% vs new ES over 200 paired-seat games.
- 83.5% vs SmartBot over 200 paired-seat games.

### DAgger R1 — strongest mixed-opponent policy

Path: `artifacts/v2_prepatch/bc_dagger_round1.pt`  
SHA-256: `a4c05fc416e4af9ead9837950c3e365a11d05c50764ffe07fee2cd35e4b5fb6c`

- 58.0% vs new ES over 200 paired-seat games.
- 87.5% vs SmartBot over 200 paired-seat games.

DAgger R1 used 2,000 learner-controlled episodes, 297,593 states, 1.4%
learner/expert disagreement, a 30% aggregate fraction, and 5x disagreement
weight. A Discover/action-cap deadlock produced 741 invalid repeated rows; BC
dropped them and commit `3070d0b` fixed the environment for future rounds.

### ES teacher

Path: `artifacts/es_bot/best.npz`  
SHA-256: `0b18c9a10e2da4fc2cc04104003ae8d75e5c0bfdb68449acc169c559db8ed7c1`

## Decisions already established

1. Flat pooled action logits are structurally unable to bind unordered entities
   to fixed action slots. Do not return to the flat actor as the main policy.
2. Pointer BC is a strong baseline; transition accuracy alone is insufficient,
   but its 99.2% episode-held-out accuracy translated into much stronger play.
3. High-entropy PPO catastrophically forgets BC. Conservative KL-PPO prevents
   collapse but did not exceed BC in a 200-game confirmation.
4. Deterministic oracle shaping is safe and reproducible but did not
   significantly exceed BC; the best 328k checkpoint matched BC against ES.
5. Fifty-game checkpoint selection is too noisy. Use at least 200 paired games
   for promotion.
6. DAgger improved SmartBot robustness by four points while remaining roughly
   flat against ES. A controlled recovery benchmark did not support error
   recovery as the mechanism.

## R1 recovery result

Tracked implementation: `scripts/evaluate_recovery.py`  
Smart raw report SHA-256:
`320874403f13484106bfe6d911063f3b17157911355d607cae672565f1598706`  
ES raw report SHA-256:
`5c96c6bffd9b1367a1cd373027868006636da34796957dcce0eceb0b3aa3b10a`

Design: deterministic ES prefix through the first normal decision on turn 5,
then clean handoff or one injected random non-expert action, strongest-minion
sale, or premature end. Pointer BC and DAgger R1 used the same 100 seeds.

Key paired recovery advantages (DAgger minus BC):

- Smart, sell strongest: +0.020 score, 95% CI [-0.008, +0.048];
  +1.06 HP, CI [-0.15, +2.27].
- Smart, premature end: -0.010 score, CI [-0.030, +0.010].
- ES, sell strongest: +0.015 score, CI [-0.026, +0.056].
- ES, premature end: +0.020 score, CI [-0.048, +0.088].

All intervals crossed zero. R1 therefore did not establish that recovery from a
single turn-5 mistake explains DAgger's SmartBot improvement. Do not present the
recovery mechanism as a positive claim.

## Current task

Roadmap item: **S1 Policy league**.

R2-A is complete. Three-seed matched results:

- Flat: 83.03 ± 0.49% action accuracy, 14.33 ± 3.01% vs ES,
  48.83 ± 4.48% vs SmartBot.
- Pointer: 99.13 ± 0.08% action accuracy, 55.17 ± 2.75% vs ES,
  86.33 ± 2.02% vs SmartBot.

See `docs/r2_representation_ablation.md`. Pointer is now mandatory for future
mainline experiments.

R2-B is complete. Three-seed disagreement-weight results:

- 0x: 55.17 ± 2.75% ES, 86.33 ± 2.02% SmartBot.
- 1x: 57.67 ± 1.76% ES, 86.00 ± 0.50% SmartBot.
- 5x: 60.67 ± 1.04% ES, 87.00 ± 0.87% SmartBot.
- 10x: 58.83 ± 3.01% ES, 87.50 ± 1.00% SmartBot.

Five-times disagreement weight is promoted as the balanced DAgger default.
See `docs/r2_dagger_weight_ablation.md`.

R2-C is complete. Three-seed matched PPO results:

- Plain PPO: 60.33 ± 2.02% ES, 86.17 ± 1.61% SmartBot.
- KL-PPO: 61.83 ± 1.76% ES, 88.17 ± 0.58% SmartBot.
- KL+Oracle: 60.33 ± 0.76% ES, 88.17 ± 0.29% SmartBot.

Promote 5x DAgger + teacher-KL PPO. Oracle remains a negative-result ablation.
See `docs/r2_ppo_ablation.md`.

R3 is complete. Frozen benchmark `hsbg_1v1_v1` is tracked in
`benchmarks/hsbg_1v1_v1.json`. Environment behavior v2, schemas, card-pool
digest, opponents, dataset, and evaluation suite are immutable. New artifacts
persist and validate this contract. `scripts/verify_research_platform.py`
passed its complete smoke pipeline; the full suite passed 875 tests with 33
skips. See `docs/r3_benchmark_freeze.md`.

E1 is complete. `LobbyGame` implements the restricted Tier-3 eight-player
lifecycle and passed 100,000 SmartBot lobbies with exact pool conservation,
pairing uniqueness, complete placements, and bounded termination. Average game
length was 24.31 rounds at 32.1 games/s; seat win shares were 12.27%–12.67%.
See `docs/e1_lobby_core.md`.

E2 is complete. `BattlegroundsLobbyEnv` exposes a 2,958-value no-leak public
observation with scheduled opponent and stale last-seen boards. On 2,000 lobby
episodes and three matched seeds, feed-forward mean placement was 4.713 and GRU
was 4.770; pooled paired intervals crossed zero. Do not enable recurrent memory
by default until a self-play teacher uses opponent history. See
`docs/e2_memory_benchmark.md` and `benchmarks/hsbg_8p_tier3_v1.json`.

Immediate implementation target:

```text
league-aware eight-player training against the archived PFSP population
```

S1 progress:

- immutable policy entries, artifact verification, and ratings are implemented;
- aggregate Elo is order independent and PFSP rejects incompatible neural
  environment contracts;
- promotion is blocked unless candidate and incumbent each have 200 games
  against at least three holdouts, the mean improves, and no holdout falls by
  more than two score points;
- `LobbyArena` and `scripts/evaluate_lobby_league.py` run multiple archived
  neural policies and SmartBot together in one shared-pool lobby;
- a two-game mixed-population smoke completed with full placements. It is not
  performance evidence. See `docs/s1_policy_league.md`.
- `LeagueLobbyEnv` and `scripts/train_lobby_league_ppo.py` connect that
  population to conservative feed-forward PPO; a 128-step end-to-end smoke
  completed successfully.
- paired league evaluation freezes seed, learner seat, and all seven opponent
  IDs in a hash-bound schedule shared by the parent and every candidate.
- S1 promotion round 1 passed: `pilot_s73` improved holdout mean placement from
  4.838 to 2.804 over 240 paired lobbies; paired improvement +2.033, 95% CI
  [+1.771, +2.304]. All six per-opponent score deltas were positive, with
  +0.245 worst case and +0.290 mean. It is now the league main. See
  `benchmarks/hsbg_league_s1_v1.json`.
- S1 promotion round 2 passed: `round2_s142` improved holdout mean placement
  from 2.712 to 1.933 on 240 new paired lobbies; improvement +0.779, 95% CI
  [+0.546, +1.013]. Its worst of seven archived-opponent score deltas was
  +0.092. It is now the league main.

Next extension/execution target:

- train the third-generation candidate from `round2_s142` against the updated
  PFSP population;
- repeat frozen selection and disjoint holdout evaluation;
- require one more gated promotion before completing S1.

Do not begin the eight-player environment phase until R2 results have been
recorded and the benchmark freeze task R3 is complete.

## Update protocol

After each task:

1. Run focused tests and the full suite.
2. Save versioned artifacts without overwriting prior experiments.
3. Record commands, hashes, results, and negative findings.
4. Update the status in `research_roadmap.md` and this file's current task.
5. Commit and push to `mine/main`.
