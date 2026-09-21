"""Verify frozen behavior-v6 full-tier artifacts and run lifecycle smoke."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

from hearthstone.engine.pool import CardPool, SpellPool
from hearthstone.env.lobby_env import BattlegroundsLobbyEnv
from hearthstone.league import file_sha256
from stress_lobby import run_game


def runtime_pool_digest(profile: dict) -> str:
    card_pool = CardPool(
        max_tier=7, included_card_ids=set(profile["included_card_ids"])
    )
    spell_pool = SpellPool(
        included_spell_ids=set(profile["included_spell_ids"])
    )
    payload = {
        "cards": {
            str(tier): sorted(str(getattr(card, "value", card)) for card in cards)
            for tier, cards in card_pool.tiers.items()
        },
        "spells": {
            str(tier): sorted(str(getattr(spell, "value", spell)) for spell in spells)
            for tier, spells in spell_pool.tiers.items()
        },
    }
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(encoded).hexdigest()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--benchmark", default="benchmarks/hsbg_8p_fulltier_v1.json"
    )
    parser.add_argument("--smoke-games", type=int, default=10)
    parser.add_argument("--seed", type=int, default=900000)
    args = parser.parse_args()
    benchmark = json.loads(Path(args.benchmark).read_text())
    content = benchmark["content"]
    for key in ("audit", "scenario_index", "profile"):
        path = ROOT / content[f"{key}_path"]
        if file_sha256(path) != content[f"{key}_sha256"]:
            raise ValueError(f"{key} hash mismatch: {path}")
    profile = json.loads((ROOT / content["profile_path"]).read_text())
    if runtime_pool_digest(profile) != content["runtime_pool_sha256"]:
        raise ValueError("runtime content-pool digest mismatch")
    env = BattlegroundsLobbyEnv(
        max_tier=6,
        behavior_version=6,
        content_profile=profile,
    )
    if env.lobby_environment_contract != benchmark["environment_contract"]:
        raise ValueError("full-tier environment contract mismatch")
    rounds = []
    winners = []
    for offset in range(args.smoke_games):
        game_rounds, winner = run_game(
            args.seed + offset,
            200,
            max_tier=6,
            behavior_version=6,
            content_profile=profile,
        )
        rounds.append(game_rounds)
        winners.append(winner)
    print(
        json.dumps(
            {
                "status": "ok",
                "benchmark": benchmark["benchmark_name"],
                "smoke_games": args.smoke_games,
                "mean_rounds": sum(rounds) / len(rounds),
                "winners": winners,
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
