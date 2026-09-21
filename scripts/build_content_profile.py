"""Build a strict verified-content profile from an audit manifest."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from hearthstone.engine.content_audit import build_content_profile


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", required=True)
    parser.add_argument(
        "--verification-index",
        default=str(ROOT / "benchmarks/content_scenarios_v1.json"),
    )
    parser.add_argument("--max-tier", type=int, required=True)
    parser.add_argument("--out", required=True)
    args = parser.parse_args()
    manifest_path = Path(args.manifest)
    verification_path = Path(args.verification_index)
    profile = build_content_profile(
        json.loads(manifest_path.read_text()), max_tier=args.max_tier
    )
    profile["source_manifest_sha256"] = hashlib.sha256(
        manifest_path.read_bytes()
    ).hexdigest()
    profile["verification_index_sha256"] = hashlib.sha256(
        verification_path.read_bytes()
    ).hexdigest()
    encoded = json.dumps(profile, indent=2, sort_keys=True) + "\n"
    output = Path(args.out)
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = output.with_suffix(".tmp")
    temporary.write_text(encoded)
    temporary.replace(output)
    print(
        {
            "cards": len(profile["included_card_ids"]),
            "spells": len(profile["included_spell_ids"]),
            "excluded_cards": len(profile["excluded_cards"]),
            "excluded_spells": len(profile["excluded_spells"]),
        }
    )
    print(f"[sha256] {hashlib.sha256(encoded.encode()).hexdigest()}")


if __name__ == "__main__":
    main()
