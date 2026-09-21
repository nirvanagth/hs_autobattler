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

## F0. Executable content and fidelity audit — COMPLETE

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
  `e6e708e903a7b1a7a72a30962ee6a3e21c753535be65be9f40f3a8907afab662`.
- The audit initially found six inconsistencies. Integration scenarios then
  exposed a missing `MINION_SUMMONED` event on normal play, affecting summon
  listeners. The manifest now identifies ten partial definitions.
- The Waveling mismatch is retained in legacy behavior-v5 so frozen results do
  not change silently. Behavior-v6 must fix or exclude it before admission.
  Of 54 Tier-3 shop cards, 51 are handler-complete. This does not mean
  scenario-verified: 177 entries remain conservatively
  classified `implemented_unverified` until dedicated scenario IDs are indexed.

- **F0-B verification/admission — COMPLETE.** The tracked
  `benchmarks/content_scenarios_v1.json` maps content IDs to exact pytest node
  IDs; loading fails on unknown content or missing test nodes. The first 38
  minions and two spells were initially explicitly verified. The admission API rejects
  both handler-incomplete content and handler-complete content lacking scenario
  verification.

- **F0-C Tier-1 scenarios — COMPLETE.** Fourteen new behavior scenarios cover
  every previously unverified current Tier-1 shop minion. All 15 current Tier-1
  shop cards now pass verified admission. The index totals 52 verified minions
  and two verified spells.

- **F0-D Tier-2 scenarios — COMPLETE.** Twelve new scenarios plus six existing
  dedicated suites cover all 18 current Tier-2 shop cards. Seventeen pass
  verified admission. Ancestral Automaton remains partial because its handler
  works for explicit summon events but legacy Tavern play never emits one. The
  manifest now reports 70 verified, 177 implemented-unverified, and 10 partial.

- **F0-E Tier-3 scenarios — COMPLETE.** Thirteen new behavior scenarios cover
  every handler-complete current Tier-3 shop card. Nineteen of 21 Tier-3 cards
  pass verified admission; Deflect-o-Bot and Waveling remain partial for known
  integration/metadata defects. Across the current Tier 1--3 shop, 51 of 54
  cards now pass strict admission. The other three are Ancestral Automaton,
  Deflect-o-Bot, and Waveling. The full manifest is 83 verified, 164
  implemented-unverified, and 10 partial.

- **F0-F behavior-v6 summon semantics — COMPLETE.** Normal minion play emits
  `MINION_SUMMONED` only when `behavior_version >= 6`; default v5 behavior and
  its frozen platform verifier remain unchanged. Integration tests show that
  Ancestral Automaton and Deflect-o-Bot now trigger through real Tavern play.
  The v6 audit (`benchmarks/hsbg_content_audit_v6.json`, SHA-256
  `a0d5fe10a17b3d216ed103bc8b360a3b4192f4971323e49b07aa89e053e2657e`)
  admits 53/54 current shop minions; only Waveling remains partial.

- **F0-G verified profile — COMPLETE.** Coin, Banana, Pointy Arrow, Fortify,
  and Apple now have explicit spell scenarios. The strict v6 Tier-3 profile
  contains 53 shop minions, 4 verified Tier-4 triple-discovery minions, 4
  generated tokens, 5 Tavern-pool spells, and all verified generated spells;
  Waveling and every unverified Tier-4 card are explicitly
  excluded. Profile SHA-256:
  `53c488fce380619a1740a3f47bd7e7ce961e4aa986b6c01f2e5227c11d458967`.
  A 1,000-lobby smoke passed exact card conservation, pairing,
  placement, and termination checks at 25.8 games/s with 24.90 average rounds.

F0 gate result: every item admitted by the v6 profile is handler-complete and
scenario-verified; runtime pools cannot draw excluded content. Proceed to F1 by
expanding the verified profile through Tier 6, then run the 100,000-lobby gate.

## F1. Verified full-tier lobby — COMPLETE

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

Progress:

- Existing dedicated scenarios verified six active Tier-5, two Tier-6, and
  five Tier-7 cards. The first strict full-tier vertical slice contains 65
  Tier 1--6 shop minions, 5 Tier-7 discovery minions, 4 generated tokens, and
  12 unique pool/generated spells.
  Profile SHA-256:
  `02e570f278ba1accbeb284cc0cb493398b1cad1715a9df6d9a6006366e8a7e87`.
- A 1,000-lobby max-tier-6 smoke passed conservation, pairing, complete
  placement, and termination checks at 28.3 games/s with 21.26 average rounds.

Result: 100,000/100,000 lobbies passed at 29.1 games/s with 21.38 average
rounds and seat win shares from 12.281% to 12.698%. The environment contract,
content profile, effective runtime pool, and lifecycle result are frozen in
`benchmarks/hsbg_8p_fulltier_v1.json`. See `docs/f1_fulltier_lobby.md`.

## F2. Curated hero and armor system — COMPLETE

Introduce hero identity, armor, passive/active hero powers, targets, cooldowns,
and once-per-game state. Start with 8--16 heroes chosen to cover distinct
mechanic families; do not attempt the full live roster in one step.

Gate:

- each hero has deterministic scenario tests and observation/action contracts;
- private hero state cannot leak through public observations;
- seat-swapped mirror tests are symmetric when heroes are exchanged;
- a full hero matchup matrix has no unexplained dominant or broken policy.

Result: eight research-reference heroes cover passive, economy, cooldown,
once-per-game, board-target, and store-target mechanics. Behavior-v7 adds
observation/action schema v2 (2,984×35) while preserving older contracts. A
4,000-lobby rotating-seat matrix passed the declared balance tolerances: mean
placement spread 0.909, win-rate spread 3.525 points, and extreme pairwise
score 60.525% / 39.475%. See `docs/f2_hero_system.md` and
`benchmarks/hsbg_8p_heroes_v1.json`.

## F3. External trace conformance — NEXT, DATA-DEPENDENT

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
