"""Verify frozen behavior-v7 hero contracts and run rotating-seat smoke."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

from hearthstone.engine.heroes import HERO_IDS, hero_registry_payload
from hearthstone.env.lobby_env import BattlegroundsLobbyEnv
from hearthstone.league import file_sha256
from stress_lobby import run_game


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--benchmark", default="benchmarks/hsbg_8p_heroes_v1.json")
    parser.add_argument("--smoke-games", type=int, default=8)
    parser.add_argument("--seed", type=int, default=910000)
    args = parser.parse_args()
    benchmark = json.loads(Path(args.benchmark).read_text())
    artifacts = benchmark["artifacts"]
    registry_path = ROOT / artifacts["hero_registry_path"]
    profile_path = ROOT / artifacts["content_profile_path"]
    if file_sha256(registry_path) != artifacts["hero_registry_file_sha256"]:
        raise ValueError("hero registry file hash mismatch")
    if json.loads(registry_path.read_text()) != hero_registry_payload():
        raise ValueError("hero registry runtime mismatch")
    if file_sha256(profile_path) != artifacts["content_profile_file_sha256"]:
        raise ValueError("hero content profile hash mismatch")
    profile = json.loads(profile_path.read_text())
    env = BattlegroundsLobbyEnv(
        max_tier=6,
        behavior_version=7,
        content_profile=profile,
        hero_ids=list(HERO_IDS),
    )
    if env.lobby_environment_contract != benchmark["environment_contract"]:
        raise ValueError("hero environment contract mismatch")
    winners = []
    for episode in range(args.smoke_games):
        shift = episode % len(HERO_IDS)
        heroes = list(HERO_IDS[shift:] + HERO_IDS[:shift])
        _, winner = run_game(
            args.seed + episode,
            200,
            max_tier=6,
            behavior_version=7,
            content_profile=profile,
            hero_ids=heroes,
        )
        winners.append({"seat": winner, "hero": heroes[winner]})
    print(
        json.dumps(
            {
                "status": "ok",
                "benchmark": benchmark["benchmark_name"],
                "smoke_games": args.smoke_games,
                "winners": winners,
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
