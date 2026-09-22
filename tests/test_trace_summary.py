"""Sanitized import-summary privacy contract test."""

import json
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent


def test_summary_never_stores_import_paths(tmp_path) -> None:
    import_dir = tmp_path / "private_player_name"
    import_dir.mkdir()
    (import_dir / "metadata.json").write_text(
        json.dumps(
            {
                "source_sha256": "a" * 64,
                "event_stream_sha256": "b" * 64,
                "sessions": 1,
                "battlegrounds_sessions": 1,
                "events": 1,
                "transitions": 1,
                "action_transitions": 1,
            }
        )
    )
    (import_dir / "events.jsonl").write_text(json.dumps({"card_id": "BG_TEST"}) + "\n")
    (import_dir / "action_transitions.jsonl").write_text(
        json.dumps(
            {
                "action_type": "BUY",
                "source_card_id": "TB_BaconShop_DragBuy",
                "block_type": "PLAY",
            }
        )
        + "\n"
    )
    output = tmp_path / "summary.json"
    subprocess.run(
        [
            sys.executable,
            str(ROOT / "scripts/summarize_trace_imports.py"),
            "--import-dir",
            str(import_dir),
            "--out",
            str(output),
        ],
        check=True,
        cwd=ROOT,
    )
    encoded = output.read_text()
    assert "private_player_name" not in encoded
    assert json.loads(encoded)["gate"]["remaining_action_transitions"] == 9999
