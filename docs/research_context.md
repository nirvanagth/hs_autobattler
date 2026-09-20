# HS Autobattler persistent research context

Last updated: 2026-09-20

This file is the handoff point for future work. Read it together with
`docs/research_roadmap.md` and `docs/v2_prepatch_experiment.md` before changing
the model, environment, reward, or training pipeline.

## Repository

- Actual checkout: `/Users/tianhaogu/Projects/hs_autobattler`
- Branch/remote: `main` tracking `mine/main`
- The Codex workspace path under `Documents/ChatGPT` is not this repository.
- Current tracked head when this context was written: `cab769f` plus subsequent
  roadmap/recovery work.

Common command prefix:

```bash
cd /Users/tianhaogu/Projects/hs_autobattler
PYTHONPATH=src:cpp/build:. .venv/bin/python ...
```

## Current platform state

- Python Tavern engine and optional C++ combat engine.
- 1v1, 30-health environment; not yet full eight-player Battlegrounds.
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
   flat against ES. The next question is whether this is recovery robustness.

## Current task

Roadmap item: **R1 Recovery benchmark**.

Immediate implementation target:

```text
scripts/evaluate_recovery.py
```

It must:

- replay a deterministic ES prefix to a target turn;
- inject a controlled legal error without consuming environment RNG;
- hand control to each candidate policy;
- run clean and perturbed variants on the same seeds;
- save raw episode results plus paired recovery deltas;
- support both SmartBot and ES opponents;
- compare `bc_pretrain.pt` and `bc_dagger_round1.pt`.

Do not begin R2 until R1 results have been recorded and its gate evaluated.

## Update protocol

After each task:

1. Run focused tests and the full suite.
2. Save versioned artifacts without overwriting prior experiments.
3. Record commands, hashes, results, and negative findings.
4. Update the status in `research_roadmap.md` and this file's current task.
5. Commit and push to `mine/main`.

