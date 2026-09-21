"""Export the deterministic reference-hero registry."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from hearthstone.engine.heroes import hero_registry_payload, hero_registry_sha256


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", required=True)
    args = parser.parse_args()
    encoded = json.dumps(hero_registry_payload(), indent=2, sort_keys=True) + "\n"
    output = Path(args.out)
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = output.with_suffix(".tmp")
    temporary.write_text(encoded)
    temporary.replace(output)
    print(f"[canonical_sha256] {hero_registry_sha256()}")
    print(f"[file_sha256] {hashlib.sha256(encoded.encode()).hexdigest()}")


if __name__ == "__main__":
    main()
