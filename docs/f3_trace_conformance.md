# F3 external trace conformance

Date: 2026-09-21
Status: tooling complete; real-data gate pending

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
6. Aggregate transition reports with exact-transition and field-agreement
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

No Power.log was found at the standard macOS Hearthstone log locations during
this phase. The user must provide an existing absolute path or generate a new
log before the external gate can run.

## Remaining gate

- import at least 10,000 real recruit transitions across multiple games;
- establish live CardID aliases for the frozen content profile;
- replay supported actions into behavior-v7 simulator snapshots;
- reach at least 99.5% agreement on deterministic fields;
- categorize every mismatch and either fix it or exclude it in a versioned
  benchmark contract.

Simulator self-play cannot substitute for this evidence.
