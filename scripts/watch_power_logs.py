"""Continuously preserve sanitized Power.log events before client rotation."""

from __future__ import annotations

import argparse
import os
import signal
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from hearthstone.traces.live_capture import (
    SanitizedLiveCapture,
    recover_incomplete_captures,
)


def latest_power_log(log_root: Path) -> Path | None:
    candidates = list(log_root.glob("Hearthstone_*/Power.log"))
    return max(candidates, key=lambda path: path.stat().st_mtime_ns) if candidates else None


def allocate_capture_dir(output_root: Path) -> Path:
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    for suffix in range(1, 10_000):
        candidate = output_root / f"capture_{timestamp}_{suffix:04d}"
        if not candidate.exists():
            return candidate
    raise RuntimeError("unable to allocate capture directory")


def _claim_pid_file(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        try:
            existing_pid = int(path.read_text().strip())
            os.kill(existing_pid, 0)
        except (ValueError, ProcessLookupError):
            pass
        else:
            raise RuntimeError(f"collector already running with pid {existing_pid}")
    path.write_text(f"{os.getpid()}\n")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--log-root", default="/Applications/Hearthstone/Logs")
    parser.add_argument("--out-root", default=str(ROOT / "artifacts/trace_f3/live_capture"))
    parser.add_argument("--pid-file", default=str(ROOT / "artifacts/trace_f3/live_collector.pid"))
    parser.add_argument("--poll-seconds", type=float, default=2.0)
    parser.add_argument("--once", action="store_true")
    args = parser.parse_args()

    log_root = Path(args.log_root)
    output_root = Path(args.out_root)
    pid_file = Path(args.pid_file)
    output_root.mkdir(parents=True, exist_ok=True)
    recovered = recover_incomplete_captures(output_root)
    _claim_pid_file(pid_file)
    should_stop = False

    def request_stop(_signum, _frame) -> None:
        nonlocal should_stop
        should_stop = True

    signal.signal(signal.SIGTERM, request_stop)
    signal.signal(signal.SIGINT, request_stop)
    source: Path | None = None
    capture: SanitizedLiveCapture | None = None
    try:
        if recovered:
            print(f"[collector] recovered={len(recovered)}", flush=True)
        while not should_stop:
            candidate = latest_power_log(log_root)
            if candidate is not None and candidate.stat().st_size == 0:
                candidate = None
            if candidate != source:
                if capture is not None:
                    metadata = capture.finalize()
                    print(
                        f"[collector] finalized events={metadata['events']} "
                        f"actions={metadata['action_transitions']}",
                        flush=True,
                    )
                source = candidate
                capture = (
                    SanitizedLiveCapture(allocate_capture_dir(output_root))
                    if source is not None
                    else None
                )
                if capture is not None:
                    print(f"[collector] started {capture.output_dir.name}", flush=True)
            if source is not None and capture is not None:
                try:
                    capture.read_available(source)
                except (FileNotFoundError, RuntimeError):
                    metadata = capture.finalize()
                    print(
                        f"[collector] rotation events={metadata['events']} "
                        f"actions={metadata['action_transitions']}",
                        flush=True,
                    )
                    source = None
                    capture = None
            if args.once:
                break
            time.sleep(max(0.25, args.poll_seconds))
    finally:
        if capture is not None:
            metadata = capture.finalize()
            print(
                f"[collector] stopped events={metadata['events']} "
                f"actions={metadata['action_transitions']}",
                flush=True,
            )
        if pid_file.exists() and pid_file.read_text().strip() == str(os.getpid()):
            pid_file.unlink()


if __name__ == "__main__":
    main()
