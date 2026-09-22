"""Compare behavior-v7 replay results with normalized live post-states."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from hearthstone.traces.replay import sha256_file
from hearthstone.traces.replay_conformance import compare_replay_results


def read_jsonl(path: Path):
    with path.open() as handle:
        for line in handle:
            if line.strip():
                yield json.loads(line)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--replay-results", required=True)
    parser.add_argument("--contract", required=True)
    parser.add_argument("--out", required=True)
    args = parser.parse_args()

    replay_path = Path(args.replay_results)
    contract_path = Path(args.contract)
    contract = json.loads(contract_path.read_text())
    comparison = compare_replay_results(read_jsonl(replay_path), contract)
    observed_agreement = comparison["deterministic"]["field_agreement_rate"]
    report = {
        "schema_version": 1,
        "replay_results_sha256": sha256_file(replay_path),
        "contract_sha256": sha256_file(contract_path),
        "comparison": comparison,
        "conformance_gate": {
            "target_field_agreement_rate": 0.995,
            "observed_field_agreement_rate": observed_agreement,
            "status": "passed" if observed_agreement >= 0.995 else "failed",
        },
        "excluded_fields": contract["state_contract"]["excluded_exact_fields"],
        "privacy": {
            "source_paths_stored": False,
            "raw_lines_stored": False,
            "entity_names_stored": False,
        },
    }
    output = Path(args.out)
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = output.with_suffix(".tmp")
    temporary.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    temporary.replace(output)
    print(json.dumps(report, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
