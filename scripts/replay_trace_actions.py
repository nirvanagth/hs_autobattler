"""Select and replay overlap-supported sanitized trace actions."""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from hearthstone.traces.replay import (
    replay_transition,
    select_replayable_transition,
    sha256_file,
    summarize_replay_decisions,
    validate_overlap_contract,
)
from hearthstone.traces.powerlog import classify_battlegrounds_action


def read_jsonl(path: Path):
    with path.open() as handle:
        for line in handle:
            if line.strip():
                yield json.loads(line)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--transitions", action="append", required=True)
    parser.add_argument("--contract", required=True)
    parser.add_argument("--profile", required=True)
    parser.add_argument("--aliases", required=True)
    parser.add_argument("--out-dir", required=True)
    args = parser.parse_args()

    contract_path = Path(args.contract)
    profile_path = Path(args.profile)
    aliases_path = Path(args.aliases)
    contract = json.loads(contract_path.read_text())
    profile = json.loads(profile_path.read_text())
    validate_overlap_contract(contract, profile_path, aliases_path)

    output = Path(args.out_dir)
    output.mkdir(parents=True, exist_ok=False)
    selections_path = output / "selections.jsonl"
    results_path = output / "replay_results.jsonl"
    all_decisions = []
    accepted_counts: Counter[str] = Counter()
    accepted_action_counts: Counter[str] = Counter()
    input_evidence = []
    with selections_path.open("w") as selections, results_path.open("w") as results:
        for input_index, raw_path in enumerate(args.transitions, start=1):
            path = Path(raw_path)
            input_evidence.append({"input_index": input_index, "sha256": sha256_file(path)})
            for transition in read_jsonl(path):
                action_type = classify_battlegrounds_action(
                    transition.get("source_card_id"), transition.get("block_type")
                )
                if action_type is None:
                    continue
                transition["action_type"] = action_type
                decision = select_replayable_transition(transition, contract)
                all_decisions.append(decision)
                selection = {
                    "input_index": input_index,
                    "transition_index": transition["transition_index"],
                    "session_index": transition["session_index"],
                    **decision.to_dict(),
                }
                selections.write(json.dumps(selection, sort_keys=True) + "\n")
                if not decision.eligible:
                    continue
                seed = (
                    input_index * 1_000_000
                    + int(transition["session_index"]) * 10_000
                    + int(transition["transition_index"])
                )
                replay = replay_transition(transition, decision, contract, profile, seed=seed)
                replay["input_index"] = input_index
                replay["seed"] = seed
                results.write(json.dumps(replay, sort_keys=True) + "\n")
                accepted_counts["accepted" if replay["accepted"] else "rejected"] += 1
                if replay["accepted"]:
                    accepted_action_counts[decision.action_type] += 1

    report = {
        "schema_version": 1,
        "contract_sha256": sha256_file(contract_path),
        "inputs": input_evidence,
        "selection": summarize_replay_decisions(all_decisions),
        "replay": {
            "accepted": accepted_counts["accepted"],
            "rejected": accepted_counts["rejected"],
            "accepted_action_counts": dict(sorted(accepted_action_counts.items())),
        },
        "outputs": {
            "selections_sha256": sha256_file(selections_path),
            "replay_results_sha256": sha256_file(results_path),
        },
        "privacy": {
            "source_paths_stored": False,
            "raw_lines_stored": False,
            "entity_names_stored": False,
        },
    }
    report_path = output / "report.json"
    temporary = report_path.with_suffix(".tmp")
    temporary.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    temporary.replace(report_path)
    print(json.dumps(report, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
