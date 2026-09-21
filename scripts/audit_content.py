"""Generate the deterministic F0 executable-content manifest."""

from __future__ import annotations

import argparse
import hashlib
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from hearthstone.engine.content_audit import (
    build_content_manifest,
    content_manifest_json,
    load_verification_index,
)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--tests", default=str(ROOT / "tests"))
    parser.add_argument(
        "--verification-index",
        default=str(ROOT / "benchmarks/content_scenarios_v1.json"),
    )
    parser.add_argument("--out", required=True)
    parser.add_argument("--behavior-version", type=int, default=5)
    args = parser.parse_args()
    test_root = Path(args.tests)
    verified = load_verification_index(
        Path(args.verification_index), test_root=test_root
    )
    manifest = build_content_manifest(
        test_root=test_root,
        verified_scenarios=verified,
        behavior_version=args.behavior_version,
    )
    encoded = content_manifest_json(manifest)
    output = Path(args.out)
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = output.with_suffix(".tmp")
    temporary.write_text(encoded)
    temporary.replace(output)
    print(manifest["summary"])
    print(f"[sha256] {hashlib.sha256(encoded.encode()).hexdigest()}")


if __name__ == "__main__":
    main()
