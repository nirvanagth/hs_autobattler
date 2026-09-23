"""Incremental privacy-safe Power.log capture tests."""

import json

from hearthstone.traces.live_capture import (
    SanitizedLiveCapture,
    recover_incomplete_captures,
)


SYNTHETIC_LOG = """CREATE_GAME
FULL_ENTITY - Creating ID=10 CardID=BG_TEST_MINION name=Private_Player
tag=CONTROLLER value=5
tag=ZONE value=HAND
tag=ZONE_POSITION value=1
tag=ATK value=2
tag=HEALTH value=3
BLOCK_START BlockType=PLAY Entity=[id=10 cardId=BG_TEST_MINION]
TAG_CHANGE Entity=10 tag=ZONE value=PLAY
BLOCK_END
""".encode()


def test_live_capture_handles_partial_lines_and_finalizes(tmp_path) -> None:
    directory = tmp_path / "capture_0001"
    capture = SanitizedLiveCapture(directory)
    split = SYNTHETIC_LOG.index(b"Private_Player")
    capture.ingest_bytes(SYNTHETIC_LOG[:split])
    capture.ingest_bytes(SYNTHETIC_LOG[split:])
    metadata = capture.finalize()

    assert metadata["status"] == "finalized"
    assert metadata["battlegrounds_sessions"] == 1
    assert metadata["action_transitions"] == 1
    assert metadata["source_bytes_observed"] == len(SYNTHETIC_LOG)
    encoded = "\n".join(path.read_text() for path in directory.iterdir())
    assert "Private_Player" not in encoded
    assert "/Applications" not in encoded


def test_incomplete_sanitized_capture_is_recoverable(tmp_path) -> None:
    directory = tmp_path / "capture_0002"
    capture = SanitizedLiveCapture(directory)
    capture.ingest_bytes(SYNTHETIC_LOG)

    recovered = recover_incomplete_captures(tmp_path)
    assert recovered == [directory]
    metadata = json.loads((directory / "metadata.json").read_text())
    assert metadata["status"] == "recovered"
    assert metadata["action_transitions"] == 1
