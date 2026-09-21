# R3 frozen benchmark contract

Date: 2026-09-20  
Benchmark: `hsbg_1v1_v1`

## Frozen contract

The tracked manifest is `benchmarks/hsbg_1v1_v1.json`. It pins:

- environment name and behavior version;
- observation and action schema versions;
- observation/entity/action dimensions;
- Tavern tier frontier;
- stable card vocabulary contract;
- active card-pool digest;
- BC dataset, ES teacher, and SmartBot source hashes;
- paired-seat evaluation size and holdout seed base;
- required raw and statistical metrics.

Current environment identity:

```text
name=hsbg_1v1_research
behavior_version=2
observation_schema_version=1
action_schema_version=1
observation_size=1036
entity_features=38
action_count=34
max_tier=6
card_vocab_scheme=stable_v1
card_pool_digest=58bf222f245ef7d5d8b1b9e4efeca855a74ea6a4b9b7c4689da3d032a4e75fae
```

## Artifact enforcement

New BC datasets, DAgger datasets, BC checkpoints, and PPO checkpoints persist
the environment contract. Training and evaluation reject an artifact when its
recorded contract differs from the runtime environment. Legacy artifacts with
no contract remain explicitly loadable for the already-recorded historical
experiments; they are not exact-resume evidence for future benchmark versions.

## Statistical evaluation

`scripts/evaluate_checkpoints.py` now stores every episode's seed, candidate
seat, outcome, HP margin, board power, tier, and turns. It reports Wilson win
intervals and generates deterministic paired bootstrap comparisons whenever
multiple candidates share an evaluation suite. Duplicate checkpoint stems are
disambiguated by parent directory.

## Fresh-checkout verifier

Run:

```bash
PYTHONPATH=src:cpp/build:. .venv/bin/python scripts/verify_research_platform.py
```

The verifier checks the native engine, frozen contract, SmartBot source hash,
focused tests, BC collection, BC training, PPO, checkpoint compatibility, raw
evaluation output, and cleanup in a temporary directory. `--full-tests` runs
the full suite instead of the focused gate.

Verified result when R3 closed: 875 passed, 33 skipped in the full repository
suite, plus a successful end-to-end quick verifier.

## Decision

R3 passes. `hsbg_1v1_v1` is immutable. Any intentional rule, pool, observation,
or action change must create a new behavior/schema version and benchmark
manifest rather than silently changing v1. The roadmap may proceed to the
restricted-pool eight-player skeleton while retaining v1 for regression tests.

Subsequent E1 stress work exercised that policy:

- `hsbg_1v1_v2` / behavior v3 records exact pool-copy provenance.
- `hsbg_1v1_v3` / behavior v5 makes Discover ordering independent of
  `PYTHONHASHSEED` and prevents board-only triplets from disappearing when the
  hand is full.

The earlier manifests remain tracked historical contracts; the verifier targets
v3 by default on the current branch.
