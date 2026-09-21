"""Rotating-seat hero placement and pairwise matchup benchmark."""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

from hearthstone.engine.heroes import HERO_IDS, hero_registry_sha256
from hearthstone.engine.lobby import LobbyGame
from hearthstone.env.smart_bot import smart_bot_turn
from hearthstone.league import file_sha256
from stress_lobby import card_inventory, verify_pairings


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--games", type=int, default=4000)
    parser.add_argument("--seed", type=int, default=840000)
    parser.add_argument("--profile", required=True)
    parser.add_argument("--out", required=True)
    args = parser.parse_args()
    profile_path = Path(args.profile)
    profile = json.loads(profile_path.read_text())
    placements: dict[str, list[int]] = defaultdict(list)
    seats: dict[str, Counter[int]] = defaultdict(Counter)
    pairwise: dict[str, dict[str, Counter[str]]] = defaultdict(
        lambda: defaultdict(Counter)
    )
    raw_games = []
    for episode in range(args.games):
        shift = episode % len(HERO_IDS)
        heroes = list(HERO_IDS[shift:] + HERO_IDS[:shift])
        lobby = LobbyGame(
            max_tier=6,
            behavior_version=7,
            content_profile=profile,
            hero_ids=heroes,
            seed=args.seed + episode,
        )
        initial_inventory = card_inventory(lobby)
        while not lobby.game_over:
            for player_id in sorted(lobby.active_player_ids):
                smart_bot_turn(lobby, player_id)
            verify_pairings(lobby)
            if card_inventory(lobby) != initial_inventory:
                raise AssertionError(f"card conservation failed: {args.seed + episode}")
        hero_placements = {
            heroes[seat]: lobby.placements[seat] for seat in range(lobby.num_players)
        }
        for seat, hero_id in enumerate(heroes):
            placements[hero_id].append(lobby.placements[seat])
            seats[hero_id][seat] += 1
        for first in HERO_IDS:
            for second in HERO_IDS:
                if first == second:
                    continue
                key = "wins" if hero_placements[first] < hero_placements[second] else "losses"
                pairwise[first][second][key] += 1
        raw_games.append(
            {
                "seed": args.seed + episode,
                "heroes": heroes,
                "placements": [lobby.placements[seat] for seat in range(8)],
            }
        )
    summary = {}
    for hero_id in HERO_IDS:
        values = placements[hero_id]
        summary[hero_id] = {
            "games": len(values),
            "mean_placement": sum(values) / len(values),
            "top4_rate": sum(value <= 4 for value in values) / len(values),
            "win_rate": sum(value == 1 for value in values) / len(values),
            "seat_counts": dict(sorted(seats[hero_id].items())),
        }
    matrix = {
        first: {
            second: {
                "games": counts["wins"] + counts["losses"],
                "wins": counts["wins"],
                "losses": counts["losses"],
                "score_rate": counts["wins"] / (counts["wins"] + counts["losses"]),
            }
            for second, counts in sorted(opponents.items())
        }
        for first, opponents in sorted(pairwise.items())
    }
    report = {
        "schema_version": 1,
        "games": args.games,
        "seed_base": args.seed,
        "profile": str(profile_path),
        "profile_sha256": file_sha256(profile_path),
        "hero_registry_sha256": hero_registry_sha256(),
        "heroes": summary,
        "pairwise": matrix,
        "raw_games": raw_games,
    }
    output = Path(args.out)
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = output.with_suffix(".tmp")
    temporary.write_text(json.dumps(report, indent=2, sort_keys=True))
    temporary.replace(output)
    print(json.dumps(summary, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
