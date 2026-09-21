# Phase F: environment fidelity and generalization roadmap

Date: 2026-09-21
Status: planned; F0 is next

## Objective

Move from a strong policy inside one restricted Tier-3 simulator to a platform
whose conclusions survive larger content pools, hero asymmetry, and held-out
environment configurations. The goal is research-grade external validity, not
an unverified imitation of every live Battlegrounds patch.

Current inventory:

- 229 minion definitions: 220 non-token and 9 token cards;
- non-token tiers: 24/29/46/50/37/25/9 for Tier 1 through Tier 7;
- 28 spell definitions;
- the frozen eight-player benchmark activates only Tier 1--3;
- no first-class hero identity, armor-tier, or hero-power subsystem.

## Operating decision

Do not expand the observation/model first. A configured card may currently act
as a stat-only body when its mechanic is absent, which is more dangerous than
excluding it: training can exploit silent simulator errors. Content enters the
active pool only after its mechanics and invariants are declared and tested.

## F0. Executable content and fidelity audit — NEXT

Deliverables:

1. Generate a versioned manifest for every minion and spell containing tier,
   tribe, keywords, native/play triggers, handler registrations, generated-card
   dependencies, and test references.
2. Classify content as `verified`, `implemented_unverified`, `partial`, or
   `unsupported`; fail benchmark construction if partial/unsupported content
   enters an active pool.
3. Add scenario fixtures for buy/play/sell/end-turn/start-combat/deathrattle and
   pool-provenance transitions.
4. Produce coverage by tier, tribe, keyword, and effect family rather than one
   misleading global percentage.

Gate:

- 100% of a proposed active pool is handler-complete and scenario-tested;
- no silent fallback from a declared mechanic to a vanilla unit;
- manifest and scenario outputs are deterministic and hashable.

Stop rule: do not start large-scale training during F0.

Progress:

- **F0-A inventory — COMPLETE.** The deterministic audit covers all 229
  minions and 28 spells, including effect classes, trigger events, generated
  dependencies, tags, rotation/shop eligibility, and test references. The
  tracked manifest is `benchmarks/hsbg_content_audit_v1.json` with SHA-256
  `bd3522293a9195941de7ac5f65ee7af5a7593a8dca425b01f73a193aa962cb6a`.
- The audit found six inconsistencies. Active Tier-3 Waveling has Deathrattle
  metadata without a death trigger; rotated Wheeled Crewmate has a no-op effect;
  Heroic Underdog lacks Stealth targeting semantics; Gentle Djinni and
  Indomitable Mount have mismatched Deathrattles; Deathly Striker has mismatched
  metadata. They remain explicitly partial.
- The Waveling mismatch is retained in legacy behavior-v5 so frozen results do
  not change silently. Behavior-v6 must fix or exclude it before admission.
  Of 54 Tier-3 shop cards, 53 are handler-complete. This does not mean
  scenario-verified: 251 entries remain conservatively
  classified `implemented_unverified` until dedicated scenario IDs are indexed.

Next: add the explicit scenario-verification index and behavior-v6 active-pool
admission validator; then resolve all six partial definitions before Tier-6.

## F1. Verified full-tier lobby — PENDING

Build a Tier-6 vertical slice from verified content only. Add or validate shop
odds, tier upgrades, triple discoveries, Tier-7 generation, Tavern spells,
damage/armor rules, card return provenance, and ghost behavior. Content breadth
may be smaller than the live game initially, but every active mechanic must be
correct.

Gate:

- behavior-contract v6 and a frozen `hsbg_8p_fulltier_v1` benchmark;
- 100,000 deterministic stress lobbies with exact pool conservation,
  termination, placement, pairing, and no invalid-action loops;
- per-seat win shares inside a preregistered tolerance;
- old Tier-3 benchmark remains reproducible or receives an explicit versioned
  migration report.

## F2. Curated hero and armor system — PENDING

Introduce hero identity, armor, passive/active hero powers, targets, cooldowns,
and once-per-game state. Start with 8--16 heroes chosen to cover distinct
mechanic families; do not attempt the full live roster in one step.

Gate:

- each hero has deterministic scenario tests and observation/action contracts;
- private hero state cannot leak through public observations;
- seat-swapped mirror tests are symmetric when heroes are exchanged;
- a full hero matchup matrix has no unexplained dominant or broken policy.

## F3. External trace conformance — PENDING, DATA-DEPENDENT

Add a versioned importer for user-provided Power.log/replay traces. Separate
parsing, state reconstruction, and simulator comparison so private data never
enters tracked artifacts. Compare legal actions, economy, shops, board/hand
transitions, triples, and deterministic combat preconditions. Random outcomes
are checked as distributions or invariants when exact RNG seeds are unavailable.

Gate:

- at least 10,000 recruit transitions across multiple games and patches;
- at least 99.5% exact agreement on deterministic state fields;
- every mismatch is categorized, reproducible, and either fixed or excluded by
  the benchmark contract;
- no training claim is made against a live patch without a conformance report.

If suitable traces are unavailable, F3 is deferred explicitly; it must not be
replaced by self-play evidence from the same simulator.

## F4. Content curriculum and policy transfer — PENDING

Transfer `round3_s217` rather than training blindly from scratch:

1. distill/BC on Tier-3 states to preserve established behavior;
2. progressively enable Tier 4, 5, and 6 verified content;
3. collect DAgger data from learner-induced states;
4. run conservative league PPO only after imitation stabilizes;
5. archive policies by environment contract so incompatible patches cannot be
   mixed accidentally.

Gate:

- three matched seeds per curriculum stage;
- no more than two placement-score points of regression on frozen Tier-3;
- positive improvement on the new full-tier holdout suite;
- promotion against at least three content configurations, not one fixed pool.

## F5. Held-out content and patch generalization — PENDING

Create explicit train/selection/holdout splits over tribe bans, card packages,
heroes, and environment versions. Compare fine-tuning, adapter heads, and
domain randomization. Revisit recurrence or search only if a diagnostic shows a
specific failure they can address.

Gate:

- report mean/seed SD and paired intervals on unseen configurations;
- a policy must outperform the frozen main across the configuration suite with
  no catastrophic archived-config regression;
- publish performance versus inference/training cost and simulator fidelity.

## Promotion ladder for Phase F

```text
content manifest
  -> deterministic mechanic scenarios
  -> 100k full-tier stress lobbies
  -> external trace conformance
  -> multi-seed curriculum
  -> multi-configuration league holdout
  -> promotion
```

## Explicit non-goals

- Do not add MCTS until a counterfactual value-ranking benchmark is positive.
- Do not enable centralized critic, combat auxiliaries, or oracle shaping by
  default; M1 did not support them.
- Do not claim live-game strength from simulator self-play alone.
- Do not chase every seasonal system (quests, anomalies, trinkets, Duos) before
  the core minion/spell/hero vertical slice passes conformance.
