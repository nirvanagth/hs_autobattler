"""Headless lifecycle and card-conservation stress test for LobbyGame."""

from __future__ import annotations

import argparse
import json
import sys
import time
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from hearthstone.engine.configs import CARD_DB
from hearthstone.engine.entities import Unit
from hearthstone.engine.lobby import LobbyGame
from hearthstone.env.smart_bot import smart_bot_turn


def add_unit(counter: Counter[str], unit: Unit) -> None:
    if CARD_DB[unit.card_id].get("is_token", False):
        return
    counter[unit.card_id] += unit.pool_copies
    counter.update(unit.absorbed_pool_copies)


def card_inventory(lobby: LobbyGame) -> Counter[str]:
    counter: Counter[str] = Counter()
    for cards in lobby.pool.tiers.values():
        counter.update(cards)
    for player in lobby.players:
        for unit in player.board:
            add_unit(counter, unit)
        for hand_card in player.hand:
            if hand_card.unit:
                add_unit(counter, hand_card.unit)
        for store_item in player.store:
            if store_item.unit:
                add_unit(counter, store_item.unit)
        for option in player.discovery.options:
            if option.unit:
                add_unit(counter, option.unit)
    return counter


def verify_pairings(lobby: LobbyGame) -> None:
    seen: set[int] = set()
    for pairing in lobby.last_pairings:
        if pairing.player_id in seen:
            raise AssertionError(f"player paired twice: {pairing.player_id}")
        seen.add(pairing.player_id)
        if not pairing.is_ghost and pairing.opponent_id is not None:
            if pairing.opponent_id in seen:
                raise AssertionError(f"player paired twice: {pairing.opponent_id}")
            seen.add(pairing.opponent_id)


def run_game(
    seed: int,
    max_rounds: int,
    *,
    behavior_version: int = 5,
    content_profile: dict | None = None,
) -> tuple[int, int]:
    lobby = LobbyGame(
        seed=seed,
        max_tier=3,
        behavior_version=behavior_version,
        content_profile=content_profile,
    )
    initial_inventory = card_inventory(lobby)
    rounds = 0
    while not lobby.game_over and rounds < max_rounds:
        active_at_round_start = sorted(lobby.active_player_ids)
        for player_id in active_at_round_start:
            smart_bot_turn(lobby, player_id)
        verify_pairings(lobby)
        current_inventory = card_inventory(lobby)
        if current_inventory != initial_inventory:
            difference = current_inventory - initial_inventory
            missing = initial_inventory - current_inventory
            raise AssertionError(
                f"card conservation failed seed={seed} round={rounds + 1}: "
                f"extra={dict(difference)}, missing={dict(missing)}"
            )
        rounds += 1

    if not lobby.game_over:
        raise AssertionError(f"lobby seed={seed} exceeded {max_rounds} rounds")
    if sorted(lobby.placements.values()) != list(range(1, lobby.num_players + 1)):
        raise AssertionError(f"invalid placements seed={seed}: {lobby.placements}")
    if lobby.winner_id is None or lobby.placements[lobby.winner_id] != 1:
        raise AssertionError(f"invalid winner seed={seed}: {lobby.winner_id}")
    return rounds, lobby.winner_id


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--games", type=int, default=1000)
    parser.add_argument("--seed", type=int, default=100_000)
    parser.add_argument("--max-rounds", type=int, default=200)
    parser.add_argument("--log-every", type=int, default=100)
    parser.add_argument("--behavior-version", type=int, default=5)
    parser.add_argument("--content-profile")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    t0 = time.time()
    total_rounds = 0
    winners: Counter[int] = Counter()
    content_profile = (
        json.loads(Path(args.content_profile).read_text())
        if args.content_profile
        else None
    )
    for index in range(args.games):
        rounds, winner = run_game(
            args.seed + index,
            args.max_rounds,
            behavior_version=args.behavior_version,
            content_profile=content_profile,
        )
        total_rounds += rounds
        winners[winner] += 1
        completed = index + 1
        if completed % args.log_every == 0 or completed == args.games:
            elapsed = time.time() - t0
            print(
                f"[stress] {completed:,}/{args.games:,} games "
                f"games/s={completed / elapsed:.1f} "
                f"avg_rounds={total_rounds / completed:.2f}",
                flush=True,
            )
    print(f"[done] winners={dict(sorted(winners.items()))}")


if __name__ == "__main__":
    main()
