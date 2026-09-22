# F3 external trace conformance

Date: 2026-09-21
Status: real-data import partial; more games required

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
   `benchmarks/powerlog_trace_schema_v1.json`.
3. Top-level action transition reconstruction with before/after entity state.
4. Simulator state normalization for heroes, armor, board, hand, and shop.
5. Field-level comparison with missing/extra entity, card ID, and individual
   tag mismatch categories.
6. Nested recruit-action extraction for buy, sell, roll, freeze, upgrade,
   card play, hero power, and special actions.
7. Aggregate transition reports with exact-transition and field-agreement
   rates plus bounded mismatch examples.

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

## Real import progress

Six local Power.log files (about 244 MB raw) were found and imported without
storing their paths. They contain 30 CREATE_GAME sessions, of which 10 have
Battlegrounds CardIDs. BG-only sanitized output contains:

- 367,040 events;
- 2,677 top-level transitions;
- 3,137 recognized nested recruit actions;
- 751 unique live CardIDs.

Recognized actions are 1,085 rolls, 590 card plays, 492 buys, 363 upgrades,
320 sells, 211 freezes, 48 hero powers, and 28 special actions. The aggregate
privacy-safe evidence file is `benchmarks/hsbg_trace_import_partial_v2.json`
(SHA-256 `37b3a7da97026a5d795004e4966344e8aa01545a4de5f8a179d3b46bd224dd5f`).
Trace schema v2 SHA-256 is
`202819c66a7e113a9f6e002f1dd57fc89d416f6177cae9d7ffd9238d9b620cda`.

Public HearthstoneJSON data (source SHA-256
`079c41a102d386a289bcf2676815799967a8aa0aaeb6b0a5958c76bdd4a20ac3`)
was used for conservative aliases: exact normalized English name, matching tier
for minions, non-golden BG entity, and a unique candidate. This resolved 239 of
257 internal content IDs. No fuzzy match is accepted.

External coverage remains the larger blocker. Of 227 ordinary live minion IDs
observed in these logs, only 111 map to the simulator (48.9%). Of 116 observed
spell IDs, only 10 map (8.6%). The tracked alias and coverage artifacts are:

- `benchmarks/live_card_aliases_v1.json`, SHA-256
  `3edae9f46438e2a7e459a687b73e09179940ca9ab4483e0b188d1db88507190e`;
- `benchmarks/hsbg_live_alias_coverage_partial_v1.json`, SHA-256
  `30f0ab2de6cb3d1193935bb841947bbf57178ae4e479f852dbc6614beb052db6`.

This means 99.5% conformance can currently be measured only on an explicitly
overlapping content subset. Whole-live-patch conformance requires substantially
more card/spell coverage and must not be inferred from simulator self-play.

## Remaining gate

- import at least 10,000 real recruit transitions across multiple games
  (currently 3,137; 6,863 remaining);
- establish live CardID aliases for the frozen content profile;
- replay supported actions into behavior-v7 simulator snapshots;
- reach at least 99.5% agreement on deterministic fields;
- categorize every mismatch and either fix it or exclude it in a versioned
  benchmark contract.

Simulator self-play cannot substitute for this evidence.
