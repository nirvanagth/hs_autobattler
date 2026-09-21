"""Run shared-pool eight-player matches sampled from a policy league."""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

import numpy as np
import torch

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

from evaluate_checkpoints import resolve_device
from hearthstone.league import PolicyEntry, PolicyLeague, file_sha256
from hearthstone.lobby_arena import LobbyArena
from lobby_league_runtime import NeuralPolicy, SearchPolicy, load_policies


def evaluate(
    league: PolicyLeague,
    candidate_id: str,
    *,
    episodes: int,
    seed_base: int,
    device: torch.device,
    schedule: dict[str, object] | None = None,
    search: bool = False,
    policy_prior_weight: float = 0.05,
) -> tuple[list[dict[str, object]], dict[str, Counter], dict[str, object]]:
    policies = load_policies(league, device)
    if candidate_id not in policies:
        raise ValueError(f"candidate is not a runnable lobby policy: {candidate_id}")
    if search:
        entry = league.entries[candidate_id]
        if entry.kind != "neural_lobby_pointer":
            raise ValueError("depth-one search requires a neural lobby candidate")
        policies[candidate_id] = SearchPolicy(
            Path(entry.artifact_path),
            device,
            policy_prior_weight=policy_prior_weight,
        )
    arena = LobbyArena(max_tier=3, seed=seed_base)
    records: list[dict[str, object]] = []
    outcomes: dict[str, Counter] = defaultdict(Counter)

    scheduled_games = schedule["games"] if schedule is not None else None
    for episode in range(episodes):
        scheduled = scheduled_games[episode] if scheduled_games is not None else None
        seed = int(scheduled["seed"]) if scheduled is not None else seed_base + episode
        arena.reset(seed=seed)
        for policy in policies.values():
            policy.begin_episode()
        candidate_seat = (
            int(scheduled["candidate_seat"])
            if scheduled is not None
            else episode % arena.game.num_players
        )
        opponents = (
            list(scheduled["opponents"])
            if scheduled is not None
            else league.sample_opponents(
                candidate_id, arena.game.num_players - 1, seed=seed
            )
        )
        lineup: list[str] = []
        opponent_iter = iter(opponents)
        for seat in range(arena.game.num_players):
            lineup.append(candidate_id if seat == candidate_seat else next(opponent_iter))
        missing = sorted(set(lineup) - set(policies))
        if missing:
            raise ValueError(f"sampled policies are not runnable in the lobby: {missing}")

        while not arena.game.game_over:
            for seat in sorted(arena.game.active_player_ids):
                policies[lineup[seat]].play_turn(arena, seat)

        candidate_placement = arena.game.placements[candidate_seat]
        for seat, opponent_id in enumerate(lineup):
            if seat == candidate_seat:
                continue
            opponent_placement = arena.game.placements[seat]
            key = "wins" if candidate_placement < opponent_placement else "losses"
            outcomes[opponent_id][key] += 1
        records.append(
            {
                "seed": seed,
                "candidate_seat": candidate_seat,
                "candidate_placement": candidate_placement,
                "lineup": lineup,
                "placements": [arena.game.placements[seat] for seat in range(8)],
                "rounds": arena.game.turn_count,
            }
        )
        print(
            f"[league] {episode + 1}/{episodes} seed={seed} "
            f"candidate_place={candidate_placement}",
            flush=True,
        )
    candidate_policy = policies[candidate_id]
    diagnostics: dict[str, object] = {"search": search}
    if isinstance(candidate_policy, NeuralPolicy):
        diagnostics.update(
            {
                "decisions": candidate_policy.decisions,
                "inference_seconds": candidate_policy.elapsed_seconds,
                "milliseconds_per_decision": (
                    1000.0 * candidate_policy.elapsed_seconds / candidate_policy.decisions
                    if candidate_policy.decisions
                    else 0.0
                ),
            }
        )
    if isinstance(candidate_policy, SearchPolicy):
        diagnostics.update(
            {
                "expanded_actions": candidate_policy.expanded_actions,
                "mean_expanded_actions": (
                    candidate_policy.expanded_actions / candidate_policy.decisions
                    if candidate_policy.decisions
                    else 0.0
                ),
            }
        )
    return records, outcomes, diagnostics


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--league", required=True)
    parser.add_argument("--candidate", required=True)
    parser.add_argument("--candidate-checkpoint")
    parser.add_argument("--episodes", type=int, default=200)
    parser.add_argument("--seed-base", type=int, default=210_000)
    parser.add_argument("--device", choices=("auto", "cpu", "mps"), default="cpu")
    parser.add_argument("--out", required=True)
    parser.add_argument("--schedule")
    parser.add_argument("--record", action="store_true")
    parser.add_argument("--search", action="store_true")
    parser.add_argument("--policy-prior-weight", type=float, default=0.05)
    args = parser.parse_args()
    league_path = Path(args.league).resolve()
    league = PolicyLeague.load(league_path)
    base_league_sha256 = file_sha256(league_path)
    if args.candidate_checkpoint:
        checkpoint_path = Path(args.candidate_checkpoint).resolve()
        checkpoint = torch.load(checkpoint_path, map_location="cpu")
        league.add_policy(
            PolicyEntry(
                policy_id=args.candidate,
                kind="neural_lobby_pointer",
                artifact_path=str(checkpoint_path),
                artifact_sha256=file_sha256(checkpoint_path),
                environment_contract=checkpoint["lobby_environment_contract"],
                metadata={"temporary_evaluation_entry": True},
            )
        )
    schedule_path = Path(args.schedule).resolve() if args.schedule else None
    schedule = json.loads(schedule_path.read_text()) if schedule_path else None
    if schedule is not None and schedule["league_sha256"] != base_league_sha256:
        raise ValueError("schedule was generated from a different league manifest")
    episodes = len(schedule["games"]) if schedule is not None else args.episodes
    records, outcomes, diagnostics = evaluate(
        league,
        args.candidate,
        episodes=episodes,
        seed_base=args.seed_base,
        device=resolve_device(args.device),
        schedule=schedule,
        search=args.search,
        policy_prior_weight=args.policy_prior_weight,
    )
    if args.record:
        for opponent_id, counts in outcomes.items():
            league.record_series(
                args.candidate,
                opponent_id,
                wins=counts["wins"],
                losses=counts["losses"],
            )
        league.save(league_path)
    placements = [int(row["candidate_placement"]) for row in records]
    report = {
        "schema_version": 1,
        "candidate_id": args.candidate,
        "episodes": episodes,
        "seed_base": args.seed_base,
        "schedule": str(schedule_path) if schedule_path else None,
        "schedule_sha256": file_sha256(schedule_path) if schedule_path else None,
        "mean_placement": float(np.mean(placements)),
        "top4_rate": float(np.mean(np.asarray(placements) <= 4)),
        "win_rate": float(np.mean(np.asarray(placements) == 1)),
        "opponent_outcomes": {key: dict(value) for key, value in outcomes.items()},
        "inference": diagnostics,
        "games": records,
    }
    output = Path(args.out)
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = output.with_suffix(".tmp")
    temporary.write_text(json.dumps(report, indent=2, sort_keys=True))
    temporary.replace(output)
    print(f"[saved] {output}")


if __name__ == "__main__":
    main()
