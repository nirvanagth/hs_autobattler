"""Build the frozen behavior-v7/live-CardID overlap contract."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from hearthstone.traces.replay import build_overlap_contract, sha256_file


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--profile", required=True)
    parser.add_argument("--aliases", required=True)
    parser.add_argument("--out", required=True)
    args = parser.parse_args()

    profile_path = Path(args.profile)
    aliases_path = Path(args.aliases)
    contract = build_overlap_contract(
        json.loads(profile_path.read_text()),
        json.loads(aliases_path.read_text()),
        profile_sha256=sha256_file(profile_path),
        aliases_sha256=sha256_file(aliases_path),
    )
    output = Path(args.out)
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = output.with_suffix(".tmp")
    temporary.write_text(json.dumps(contract, indent=2, sort_keys=True) + "\n")
    temporary.replace(output)
    print(
        json.dumps(
            {
                "behavior_version": contract["behavior_version"],
                "supported_live_aliases": len(contract["alias_registry"]["supported_live_aliases"]),
            },
            indent=2,
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
