# F1 verified full-tier lobby

Date: 2026-09-21
Status: complete

F1 validates a narrow, fully audited Tier-6 vertical slice rather than claiming
complete live-patch coverage. The frozen runtime profile contains 65 verified
Tier 1--6 shop minions, 5 Tier-7 discovery minions, 4 generated tokens, and 12
unique pool/generated spells. Every omitted item is explicit.

Behavior-v6 emits `MINION_SUMMONED` for normal minion play, repairing the real
Tavern path for summon listeners. Behavior-v5 remains the default and its
end-to-end frozen-platform verifier still passes.

## Lifecycle gate

```text
games=100000
seed_base=700000
max_rounds=200
behavior_version=6
max_tier=6
```

Results:

- 100,000/100,000 lobbies completed;
- 21.38 average rounds;
- 29.1 games/s;
- seat win shares ranged from 12.281% to 12.698%;
- no card-conservation, pairing, placement, winner, or termination violation.

The profile gained generated-dependency metadata while the long gate was
running. The gate-start and final profiles produce the identical runtime pool,
SHA-256 `958081c23e1d49ae9d5a5ec7ff0c8092fc83020535692d2c7bc98603f6aa22ae`.
Both profile hashes and this equivalence are frozen in
`benchmarks/hsbg_8p_fulltier_v1.json`.

The F1 gate passes. High-tier breadth should continue to grow in separately
verified batches, but the complete Tavern tier lifecycle is operational. The
next phase is the curated hero and armor system.
