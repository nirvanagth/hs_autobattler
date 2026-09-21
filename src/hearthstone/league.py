"""Immutable policy registry, ratings, and PFSP opponent sampling."""

from __future__ import annotations

import hashlib
import json
import math
import random
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any


LEAGUE_SCHEMA_VERSION = 1


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


@dataclass(frozen=True)
class PolicyEntry:
    policy_id: str
    kind: str
    artifact_path: str
    artifact_sha256: str
    environment_contract: dict[str, Any] | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class MatchupStats:
    games: int = 0
    score: float = 0.0
    wins: int = 0
    losses: int = 0
    draws: int = 0

    @property
    def score_rate(self) -> float:
        return self.score / self.games if self.games else 0.5


@dataclass(frozen=True)
class PromotionDecision:
    eligible: bool
    candidate_id: str
    incumbent_id: str
    holdout_ids: tuple[str, ...]
    min_games: int
    min_opponents: int
    min_mean_improvement: float
    max_regression: float
    mean_improvement: float | None
    worst_improvement: float | None
    comparisons: tuple[dict[str, Any], ...]
    reasons: tuple[str, ...]

    def metadata(self) -> dict[str, Any]:
        return asdict(self)


class PolicyLeague:
    def __init__(self, *, initial_rating: float = 1000.0, k_factor: float = 24.0):
        self.initial_rating = initial_rating
        self.k_factor = k_factor
        self.entries: dict[str, PolicyEntry] = {}
        self.ratings: dict[str, float] = {}
        self.matchups: dict[str, dict[str, MatchupStats]] = {}
        self.main_policy_id: str | None = None
        self.promotion_history: list[dict[str, Any]] = []

    def add_policy(self, entry: PolicyEntry, *, verify_artifact: bool = True) -> None:
        if entry.policy_id in self.entries:
            if self.entries[entry.policy_id] != entry:
                raise ValueError(f"policy id is immutable: {entry.policy_id}")
            return
        if verify_artifact:
            path = Path(entry.artifact_path)
            if not path.is_file():
                raise FileNotFoundError(path)
            actual = file_sha256(path)
            if actual != entry.artifact_sha256:
                raise ValueError(
                    f"artifact hash mismatch for {entry.policy_id}: "
                    f"expected={entry.artifact_sha256}, actual={actual}"
                )
        self.entries[entry.policy_id] = entry
        self.ratings[entry.policy_id] = self.initial_rating
        self.matchups[entry.policy_id] = {}

    def _stats(self, first: str, second: str) -> MatchupStats:
        if first not in self.entries or second not in self.entries:
            raise KeyError(f"unknown policy matchup: {first}, {second}")
        return self.matchups[first].setdefault(second, MatchupStats())

    def policies_are_compatible(self, first: str, second: str) -> bool:
        """Return whether two entries can act in the same environment.

        Heuristics are treated as environment adapters. Neural policies must
        have identical contracts; legacy neural policies with no contract are
        compatible only with other legacy neural policies.
        """
        if first not in self.entries or second not in self.entries:
            raise KeyError(f"unknown policies: {first}, {second}")
        first_entry = self.entries[first]
        second_entry = self.entries[second]
        if first_entry.kind.startswith("heuristic") or second_entry.kind.startswith(
            "heuristic"
        ):
            return True
        return first_entry.environment_contract == second_entry.environment_contract

    @staticmethod
    def _update_stats(stats: MatchupStats, *, wins: int, losses: int, draws: int) -> None:
        stats.games += wins + losses + draws
        stats.score += wins + 0.5 * draws
        stats.wins += wins
        stats.losses += losses
        stats.draws += draws

    def record_result(self, first: str, second: str, score: float) -> None:
        if score not in {0.0, 0.5, 1.0}:
            raise ValueError("score must be 0, 0.5, or 1 from first policy's perspective")
        if score == 1.0:
            self.record_series(first, second, wins=1, losses=0)
        elif score == 0.0:
            self.record_series(first, second, wins=0, losses=1)
        else:
            self.record_series(first, second, wins=0, losses=0, draws=1)

    def record_series(
        self, first: str, second: str, *, wins: int, losses: int, draws: int = 0
    ) -> None:
        if min(wins, losses, draws) < 0:
            raise ValueError("series counts must be non-negative")
        games = wins + losses + draws
        if games == 0:
            raise ValueError("series must contain at least one game")
        if not self.policies_are_compatible(first, second):
            raise ValueError(f"incompatible policy contracts: {first}, {second}")

        self._update_stats(
            self._stats(first, second), wins=wins, losses=losses, draws=draws
        )
        self._update_stats(
            self._stats(second, first), wins=losses, losses=wins, draws=draws
        )

        # Imported aggregate results have no meaningful game order. Updating
        # once from their score rate avoids the large wins-first/losses-second
        # bias of replaying an arbitrarily ordered series. sqrt(N) gives larger
        # studies more influence without making a single batch dominate.
        first_rating = self.ratings[first]
        second_rating = self.ratings[second]
        expected = 1.0 / (1.0 + 10.0 ** ((second_rating - first_rating) / 400.0))
        actual = (wins + 0.5 * draws) / games
        delta = self.k_factor * math.sqrt(games) * (actual - expected)
        self.ratings[first] += delta
        self.ratings[second] -= delta

    def sample_opponents(
        self,
        learner_id: str,
        count: int,
        *,
        seed: int,
        exponent: float = 2.0,
        include_learner: bool = False,
    ) -> list[str]:
        if learner_id not in self.entries:
            raise KeyError(learner_id)
        candidates = sorted(
            policy_id
            for policy_id in self.entries
            if (include_learner or policy_id != learner_id)
            and self.policies_are_compatible(learner_id, policy_id)
        )
        if not candidates:
            raise ValueError("league has no compatible opponent policies")
        weights = []
        for opponent in candidates:
            win_rate = self._stats(learner_id, opponent).score_rate
            weights.append(max(0.05, 1.0 - win_rate) ** exponent)
        rng = random.Random(seed)
        return rng.choices(candidates, weights=weights, k=count)

    def bootstrap_main(self, policy_id: str, evidence: dict[str, Any]) -> None:
        if policy_id not in self.entries:
            raise KeyError(policy_id)
        if self.main_policy_id is not None or self.promotion_history:
            raise ValueError("main policy has already been bootstrapped")
        self._set_main(policy_id, {"bootstrap": True, **evidence})

    def evaluate_promotion(
        self,
        candidate_id: str,
        holdout_ids: list[str] | tuple[str, ...],
        *,
        min_games: int = 200,
        min_opponents: int = 3,
        min_mean_improvement: float = 0.0,
        max_regression: float = 0.02,
    ) -> PromotionDecision:
        if candidate_id not in self.entries:
            raise KeyError(candidate_id)
        if self.main_policy_id is None:
            raise ValueError("bootstrap a main policy before evaluating promotion")
        if candidate_id == self.main_policy_id:
            raise ValueError(f"policy is already main: {candidate_id}")
        if min_games <= 0 or min_opponents <= 0:
            raise ValueError("promotion minimums must be positive")
        if max_regression < 0:
            raise ValueError("max_regression must be non-negative")

        incumbent_id = self.main_policy_id
        unique_holdouts = tuple(dict.fromkeys(holdout_ids))
        reasons: list[str] = []
        comparisons: list[dict[str, Any]] = []
        if len(unique_holdouts) < min_opponents:
            reasons.append(
                f"need at least {min_opponents} independent holdouts; got {len(unique_holdouts)}"
            )
        for opponent_id in unique_holdouts:
            if opponent_id in {candidate_id, incumbent_id}:
                reasons.append(f"holdout cannot be candidate or incumbent: {opponent_id}")
                continue
            if opponent_id not in self.entries:
                reasons.append(f"unknown holdout: {opponent_id}")
                continue
            if not self.policies_are_compatible(candidate_id, opponent_id):
                reasons.append(f"candidate contract incompatible with {opponent_id}")
                continue
            if not self.policies_are_compatible(incumbent_id, opponent_id):
                reasons.append(f"incumbent contract incompatible with {opponent_id}")
                continue
            candidate = self.matchups[candidate_id].get(opponent_id, MatchupStats())
            incumbent = self.matchups[incumbent_id].get(opponent_id, MatchupStats())
            comparison = {
                "opponent_id": opponent_id,
                "candidate_games": candidate.games,
                "incumbent_games": incumbent.games,
                "candidate_score_rate": candidate.score_rate,
                "incumbent_score_rate": incumbent.score_rate,
                "improvement": candidate.score_rate - incumbent.score_rate,
            }
            comparisons.append(comparison)
            if candidate.games < min_games or incumbent.games < min_games:
                reasons.append(
                    f"{opponent_id} needs {min_games} games for both policies; "
                    f"got candidate={candidate.games}, incumbent={incumbent.games}"
                )

        improvements = [row["improvement"] for row in comparisons]
        mean_improvement = (
            float(sum(improvements) / len(improvements)) if improvements else None
        )
        worst_improvement = min(improvements) if improvements else None
        if mean_improvement is None or mean_improvement <= min_mean_improvement:
            reasons.append(
                f"mean improvement must exceed {min_mean_improvement:.4f}; "
                f"got {mean_improvement}"
            )
        if worst_improvement is None or worst_improvement < -max_regression:
            reasons.append(
                f"worst holdout regression must be >= {-max_regression:.4f}; "
                f"got {worst_improvement}"
            )
        return PromotionDecision(
            eligible=not reasons,
            candidate_id=candidate_id,
            incumbent_id=incumbent_id,
            holdout_ids=unique_holdouts,
            min_games=min_games,
            min_opponents=min_opponents,
            min_mean_improvement=min_mean_improvement,
            max_regression=max_regression,
            mean_improvement=mean_improvement,
            worst_improvement=worst_improvement,
            comparisons=tuple(comparisons),
            reasons=tuple(reasons),
        )

    def promote(
        self,
        policy_id: str,
        holdout_ids: list[str] | tuple[str, ...],
        evidence: dict[str, Any],
        **gate_kwargs: Any,
    ) -> PromotionDecision:
        decision = self.evaluate_promotion(policy_id, holdout_ids, **gate_kwargs)
        if not decision.eligible:
            raise ValueError("promotion gate failed: " + "; ".join(decision.reasons))
        self._set_main(
            policy_id,
            {"bootstrap": False, "gate": decision.metadata(), **evidence},
        )
        return decision

    def _set_main(self, policy_id: str, evidence: dict[str, Any]) -> None:
        self.main_policy_id = policy_id
        self.promotion_history.append(
            {
                "sequence": len(self.promotion_history) + 1,
                "policy_id": policy_id,
                "evidence": evidence,
            }
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": LEAGUE_SCHEMA_VERSION,
            "initial_rating": self.initial_rating,
            "k_factor": self.k_factor,
            "entries": {key: asdict(value) for key, value in self.entries.items()},
            "ratings": self.ratings,
            "matchups": {
                first: {second: asdict(stats) for second, stats in opponents.items()}
                for first, opponents in self.matchups.items()
            },
            "main_policy_id": self.main_policy_id,
            "promotion_history": self.promotion_history,
        }

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> PolicyLeague:
        if payload.get("schema_version") != LEAGUE_SCHEMA_VERSION:
            raise ValueError("unsupported league schema")
        league = cls(
            initial_rating=float(payload["initial_rating"]),
            k_factor=float(payload["k_factor"]),
        )
        league.entries = {
            key: PolicyEntry(**entry) for key, entry in payload["entries"].items()
        }
        league.ratings = {key: float(value) for key, value in payload["ratings"].items()}
        league.matchups = {
            first: {
                second: MatchupStats(**stats) for second, stats in opponents.items()
            }
            for first, opponents in payload["matchups"].items()
        }
        league.main_policy_id = payload.get("main_policy_id")
        league.promotion_history = list(payload.get("promotion_history", []))
        return league

    def save(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_suffix(".tmp")
        temporary.write_text(json.dumps(self.to_dict(), indent=2, sort_keys=True))
        temporary.replace(path)

    @classmethod
    def load(cls, path: Path, *, verify_artifacts: bool = True) -> PolicyLeague:
        league = cls.from_dict(json.loads(path.read_text()))
        if verify_artifacts:
            for entry in league.entries.values():
                actual = file_sha256(Path(entry.artifact_path))
                if actual != entry.artifact_sha256:
                    raise ValueError(f"artifact hash mismatch for {entry.policy_id}")
        return league
