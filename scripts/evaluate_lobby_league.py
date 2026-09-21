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
from evaluate_lobby_models import load_model
from hearthstone.env.smart_bot import smart_bot_turn
from hearthstone.league import PolicyLeague
from hearthstone.lobby_arena import LobbyArena


class LoadedPolicy:
    def begin_episode(self) -> None:
        pass

    def play_turn(self, arena: LobbyArena, player_id: int) -> int:
        raise NotImplementedError


class SmartPolicy(LoadedPolicy):
    def play_turn(self, arena: LobbyArena, player_id: int) -> int:
        smart_bot_turn(arena.game, player_id)
        return 1


class NeuralPolicy(LoadedPolicy):
    def __init__(self, checkpoint: Path, device: torch.device) -> None:
        self.model, self.contract = load_model(checkpoint, device)
        self.device = device
        self.hidden: dict[int, torch.Tensor | None] = {}

    def begin_episode(self) -> None:
        self.hidden.clear()

    def play_turn(self, arena: LobbyArena, player_id: int) -> int:
        def select(observation, mask, seat):
            with torch.inference_mode():
                logits, _, hidden = self.model(
                    torch.as_tensor(
                        observation, dtype=torch.float32, device=self.device
                    ).unsqueeze(0),
                    self.hidden.get(seat),
                )
                mask_tensor = torch.as_tensor(
                    mask, dtype=torch.bool, device=self.device
                ).unsqueeze(0)
                action = int(
                    logits.masked_fill(~mask_tensor, -1e8).argmax(dim=-1).item()
                )
            self.hidden[seat] = hidden
            return action

        return arena.play_action_turn(player_id, select)


def load_policies(league: PolicyLeague, device: torch.device) -> dict[str, LoadedPolicy]:
    policies: dict[str, LoadedPolicy] = {}
    for policy_id, entry in league.entries.items():
        if entry.kind == "heuristic_lobby_smart":
            policies[policy_id] = SmartPolicy()
        elif entry.kind == "neural_lobby_pointer":
            policy = NeuralPolicy(Path(entry.artifact_path), device)
            if policy.contract != entry.environment_contract:
                raise ValueError(f"checkpoint contract mismatch for {policy_id}")
            policies[policy_id] = policy
    return policies


def evaluate(
    league: PolicyLeague,
    candidate_id: str,
    *,
    episodes: int,
    seed_base: int,
    device: torch.device,
) -> tuple[list[dict[str, object]], dict[str, Counter]]:
    policies = load_policies(league, device)
    if candidate_id not in policies:
        raise ValueError(f"candidate is not a runnable lobby policy: {candidate_id}")
    arena = LobbyArena(max_tier=3, seed=seed_base)
    records: list[dict[str, object]] = []
    outcomes: dict[str, Counter] = defaultdict(Counter)

    for episode in range(episodes):
        seed = seed_base + episode
        arena.reset(seed=seed)
        for policy in policies.values():
            policy.begin_episode()
        candidate_seat = episode % arena.game.num_players
        opponents = league.sample_opponents(
            candidate_id, arena.game.num_players - 1, seed=seed
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
    return records, outcomes


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--league", required=True)
    parser.add_argument("--candidate", required=True)
    parser.add_argument("--episodes", type=int, default=200)
    parser.add_argument("--seed-base", type=int, default=210_000)
    parser.add_argument("--device", choices=("auto", "cpu", "mps"), default="cpu")
    parser.add_argument("--out", required=True)
    parser.add_argument("--record", action="store_true")
    args = parser.parse_args()
    league_path = Path(args.league)
    league = PolicyLeague.load(league_path)
    records, outcomes = evaluate(
        league,
        args.candidate,
        episodes=args.episodes,
        seed_base=args.seed_base,
        device=resolve_device(args.device),
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
        "episodes": args.episodes,
        "seed_base": args.seed_base,
        "mean_placement": float(np.mean(placements)),
        "top4_rate": float(np.mean(np.asarray(placements) <= 4)),
        "win_rate": float(np.mean(np.asarray(placements) == 1)),
        "opponent_outcomes": {key: dict(value) for key, value in outcomes.items()},
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
