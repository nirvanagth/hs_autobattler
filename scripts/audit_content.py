"""Generate the deterministic F0 executable-content manifest."""

from __future__ import annotations

import argparse
import hashlib
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from hearthstone.engine.content_audit import build_content_manifest, content_manifest_json


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--tests", default=str(ROOT / "tests"))
    parser.add_argument("--out", required=True)
    args = parser.parse_args()
    manifest = build_content_manifest(test_root=Path(args.tests))
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
