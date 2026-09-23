# F3 external trace conformance

Date: 2026-09-22
Status: overlap comparison passes on behavior v8; more coverage and games required

## Privacy boundary

Raw Power.log files remain at the user-provided path and are never copied into
the repository. The importer stores only allowlisted structural fields,
numeric entity IDs, safe card IDs, and deterministic tags. It does not store
raw lines, entity/player names, account values, or the source path. Sanitized
outputs inside the repository are restricted to `artifacts/`, which is ignored
by git.

## Implemented pipeline

1. Streaming parser for CREATE_GAME, FULL/SHOW/CHANGE_ENTITY, TAG_CHANGE, and
   nested BLOCK_START/BLOCK_END records.
2. Versioned allowlist and schema in
   `benchmarks/powerlog_trace_schema_v3.json`.
3. Top-level action transition reconstruction with before/after entity state.
4. Simulator state normalization for heroes, armor, board, hand, and shop.
5. Field-level comparison with missing/extra entity, card ID, and individual
   tag mismatch categories.
6. Nested recruit-action extraction for buy, sell, roll, freeze, upgrade,
   card play, hero power, and special actions.
7. Aggregate transition reports with exact-transition and field-agreement
   rates plus bounded mismatch examples.
8. Hash-pinned behavior-v7 overlap contract for the supported live CardID
   subset and explicit per-action replay policy.
9. Conservative replayability selection with categorized exclusion reasons.
10. State hydration and deterministic behavior-v7 execution for selected
    buy, sell, play, roll, and upgrade actions.

Synthetic end-to-end verification parsed 14 lines into 13 sanitized events and
one action transition. The event stream SHA-256 is
`6fd2a803217e059bc346746a3d2eb0ef22dcfcbb74c2cee2713315297a39105a`;
self-conformance was 100% over eight deterministic fields. The fixture contains
fake private-looking values and tests prove they do not appear in output.

## Import command

```bash
PYTHONPATH=src:cpp/build:. .venv/bin/python scripts/import_power_log.py \
  --input /absolute/private/path/Power.log \
  --out-dir artifacts/trace_f3/session_name
```

## Live capture

`scripts/watch_power_logs.py` follows the newest Power.log and writes only
allowlisted, sanitized events under `artifacts/trace_f3/live_capture/`. It never
copies raw lines or stores the source path. On log rotation, truncation,
SIGTERM, or Ctrl-C it reconstructs transitions and finalizes the capture. A
capturing directory can also be recovered after interruption from its sanitized
`events.jsonl` alone.

```bash
.venv/bin/python scripts/watch_power_logs.py \
  --log-root /Applications/Hearthstone/Logs \
  --out-root artifacts/trace_f3/live_capture \
  --pid-file artifacts/trace_f3/live_collector.pid \
  --poll-seconds 2
```

The collector was live-smoked against an actively growing log: it preserved
12,990 sanitized events and finalized 50 correctly classified recruit actions.
Partial-line parsing, log truncation handling, privacy, finalization, and
interrupted-capture recovery have automated tests.

## Real import progress

Eight local Power.log files (about 348 MB raw) were found and imported without
storing their paths. They contain 40 CREATE_GAME sessions, of which 16 have
Battlegrounds CardIDs. BG-only sanitized output contains:

- 527,769 events;
- 4,074 top-level transitions;
- 1,709 recognized recruit actions;
- 946 unique live CardIDs.

Recognized actions are 246 rolls, 798 card plays, 270 buys, 52 upgrades,
231 sells, 12 freezes, 56 hero powers, and 44 special actions. The aggregate
privacy-safe evidence file is `benchmarks/hsbg_trace_import_partial_v5.json`
(SHA-256 `187f83e177dfacb76c3f88885c175ddedb37c6635801f2171250abd172f703d7`).
The source artifacts use trace schema v2; action counts are reclassified by
classifier v3. New imports use trace schema v3 (SHA-256
`17a526aa1fe540869046c3ce1900e5896923b61765a50a82c8136a9f054f2629`).

Classifier v3 corrects an important false-positive in the earlier partial-v4
report. Only `BlockType=PLAY` is a user recruit action. Nested POWER, TRIGGER,
and ATTACK blocks are effects, not additional actions, and `TB_BaconUps_*`
identifies golden minions rather than tavern-upgrade buttons. The earlier 4,319
count is therefore superseded, not comparable to the corrected 1,709 count.

Public HearthstoneJSON data (source SHA-256
`079c41a102d386a289bcf2676815799967a8aa0aaeb6b0a5958c76bdd4a20ac3`)
was used for conservative aliases: exact normalized English name, matching tier
for minions, non-golden BG entity, and a unique candidate. This resolved 239 of
257 internal content IDs. No fuzzy match is accepted.

External coverage remains the larger blocker. Of 276 ordinary live minion IDs
observed in these logs, only 125 map to the simulator (45.3%). Of 129 observed
spell IDs, only 11 map (8.5%). The tracked alias and coverage artifacts are:

- `benchmarks/live_card_aliases_v1.json`, SHA-256
  `3edae9f46438e2a7e459a687b73e09179940ca9ab4483e0b188d1db88507190e`;
- `benchmarks/hsbg_live_alias_coverage_partial_v2.json`, SHA-256
  `67831f8f54d5c7055653335c3eb725358fa8ddde7540d86eac7b5c8cb124736a`.

This means 99.5% conformance can currently be measured only on an explicitly
overlapping content subset. Whole-live-patch conformance requires substantially
more card/spell coverage and must not be inferred from simulator self-play.

## Frozen overlap and replay

`benchmarks/hsbg_trace_overlap_contract_v1.json` freezes behavior v7, the
full-tier content profile, the exact alias registry, 81 supported live aliases,
and the replay policy (SHA-256
`5c1a20072ad421977719343062c428d905e9c60ea2ac4c16714dba5b8410c2da`).
Buy, sell, supported card play, and upgrade are deterministic by default;
transitions touching a contract-listed random effect are downgraded to
invariant-only. Roll is also invariant-only because the live RNG seed is
unavailable. Freeze, live hero powers, and special buttons remain explicitly
excluded until their missing state or semantics are represented.

The conservative selector admitted 55/1,709 transitions (3.22%): 52 upgrades,
1 buy, 1 sell, and 1 card play. All 55 were accepted by the behavior-v7
simulator; 54 are deterministic candidates and the random River Skipper sell is
invariant-only. The low selection rate is primarily caused by unmapped live
cards in the board, hand, or shop. It is evidence about coverage, not a replay
failure.

The privacy-safe aggregate is
`benchmarks/hsbg_trace_replay_selection_v1.json` (SHA-256
`16ec593645be7498934b1fca4db6106b6056ef488f276841afa95d8fde62fe64`).
Two full runs produced identical selection and replay-result hashes.

```bash
.venv/bin/python scripts/replay_trace_actions.py \
  --transitions artifacts/trace_f3/session/action_transitions.jsonl \
  --contract benchmarks/hsbg_trace_overlap_contract_v1.json \
  --profile benchmarks/hsbg_content_profile_v7_fulltier.json \
  --aliases benchmarks/live_card_aliases_v1.json \
  --out-dir artifacts/trace_f3/replay_session

.venv/bin/python scripts/compare_trace_replays.py \
  --replay-results artifacts/trace_f3/replay_session/replay_results.jsonl \
  --contract benchmarks/hsbg_trace_overlap_contract_v1.json \
  --out artifacts/trace_f3/conformance.json
```

## First deterministic comparison

The first post-state pass compared only fields declared by each action's frozen
contract. Gold, hero state, freeze state, unknown enchantments, and random card
identity are not silently scored. All 140 replay precondition fields matched.

Of 54 deterministic candidates, 28 had complete and timely live post-state
evidence. Eighteen transitions matched exactly; 10 mismatched, for 64.29% exact
transition agreement and 89.36% field agreement (84/94). The buy and card-play
transitions matched exactly. All 10 mismatches were `upgrade_cost`: live exposed
11 while the simulator produced 9 or 10. The invariant-only River Skipper sell
passed its board/hand/shop delta and generated-tier checks.

Twenty-three upgrades were excluded because Power.log published the new button
state after the captured action block, and three lacked a complete precondition.
These are categorized trace-boundary limitations, not matches. The report is
`benchmarks/hsbg_trace_conformance_v1.json` (SHA-256
`a15300fcd25d88b2907315bfda26bc4b38c9bed7cf15bc2372ae02243a1f308d`).

## Behavior-v8 correction

The mismatch was corrected in behavior v8 without changing the frozen v7
contract: the base costs shown after upgrading to Tavern Tier 4 and Tier 5 are
now 11 for the next Tier 5 and Tier 6 upgrades, rather than 9 and 10. Lower-tier
costs are unchanged. The generated v8 full-tier profile is
`benchmarks/hsbg_content_profile_v8_fulltier.json` (SHA-256
`3676224966426c47ecbac019d41e1a6f7cc9a0aa6dc8c632ab78698f17db914f`).
Its source audit is `benchmarks/hsbg_content_audit_v8.json` (SHA-256
`1ce596fc1191ad3caae11ff32a416cb8d8ee1a5dda1d732a0092e62931f66b06`).

The same trace inputs and selection policy were replayed under the v2 overlap
contract (SHA-256
`fb0b2ced90214ff223f4c20238e91f0400b3e753161754e46b07d3c54bbb1719`).
All 28 evaluable deterministic transitions then matched exactly, with 94/94
matching fields and 100% field agreement. The invariant-only sell also passed.
The two full runs remained byte-identical. Evidence:

- `benchmarks/hsbg_trace_replay_selection_v2.json`, SHA-256
  `f7b5f38bba342fd82c446ec88bc7d69b5f59b255c3daf9fdcfb2009cf464d143`;
- `benchmarks/hsbg_trace_conformance_v2.json`, SHA-256
  `2efddc96afb7e2e383481f2f8591585fccd77488b6907500fffd3a6ac713a147`.

This passes the 99.5% agreement threshold for the current narrow, evaluable
overlap. It does not complete F3 because the 10,000-action volume gate and broad
live-content coverage gate remain unmet.

A 1,000-lobby behavior-v8 full-tier smoke test completed without invariant or
lifecycle failures at 20.9 games/s and 25.98 average rounds. Every seat and all
eight reference heroes recorded wins.

## Remaining gate

- import at least 10,000 real recruit transitions across multiple games
  (currently 1,709; 8,291 remaining);
- improve trace-boundary capture and supported-content coverage so more than
  28 deterministic transitions are evaluable;
- sustain at least 99.5% agreement as the evaluable set expands;
- categorize every mismatch and either fix it or exclude it in a versioned
  benchmark contract.

Simulator self-play cannot substitute for this evidence.
