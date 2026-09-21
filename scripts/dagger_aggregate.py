"""Aggregate a base BC dataset with complete DAgger episodes."""

from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np


ROW_FIELDS = ("obs", "masks", "actions", "rewards", "returns", "episode_ids")


def select_complete_episodes(
    episode_ids: np.ndarray,
    target_rows: int,
    seed: int,
) -> np.ndarray:
    """Select shuffled whole episodes until at least target_rows are covered."""
    unique, counts = np.unique(episode_ids, return_counts=True)
    rng = np.random.default_rng(seed)
    order = rng.permutation(len(unique))
    selected: list[int] = []
    rows = 0
    for index in order:
        selected.append(int(unique[index]))
        rows += int(counts[index])
        if rows >= target_rows:
            break
    return np.isin(episode_ids, np.asarray(selected, dtype=episode_ids.dtype))


def scalar_string(data: np.lib.npyio.NpzFile, key: str) -> str | None:
    return str(data[key].item()) if key in data else None


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base", required=True)
    parser.add_argument("--dagger", required=True)
    parser.add_argument("--out", required=True)
    parser.add_argument("--dagger-fraction", type=float, default=0.3)
    parser.add_argument("--disagreement-weight", type=float, default=5.0)
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()
    if not 0.0 < args.dagger_fraction < 1.0:
        parser.error("--dagger-fraction must be in (0, 1)")
    if args.disagreement_weight < 1.0:
        parser.error("--disagreement-weight must be at least 1")

    base = np.load(args.base)
    dagger = np.load(args.dagger)
    for field in ROW_FIELDS:
        if field not in base or field not in dagger:
            raise ValueError(f"both datasets must contain {field!r}")

    for key in ("card_vocab_hash", "card_vocab_scheme", "environment_contract"):
        if key not in base and key not in dagger:
            continue
        if scalar_string(base, key) != scalar_string(dagger, key):
            raise ValueError(
                f"dataset {key} mismatch: base={scalar_string(base, key)!r}, "
                f"dagger={scalar_string(dagger, key)!r}"
            )

    base_rows = len(base["actions"])
    desired_dagger_rows = round(
        base_rows * args.dagger_fraction / (1.0 - args.dagger_fraction)
    )
    available_dagger_rows = len(dagger["actions"])
    if available_dagger_rows > desired_dagger_rows:
        dagger_keep = select_complete_episodes(
            dagger["episode_ids"], desired_dagger_rows, args.seed
        )
    else:
        dagger_keep = np.ones(available_dagger_rows, dtype=bool)

    selected_dagger_rows = int(dagger_keep.sum())
    episode_offset = int(base["episode_ids"].max()) + 1
    dagger_episode_ids = dagger["episode_ids"][dagger_keep].astype(np.int64)
    selected_episode_ids, normalized_ids = np.unique(
        dagger_episode_ids, return_inverse=True
    )
    combined_episode_ids = np.concatenate(
        [
            base["episode_ids"].astype(np.int64),
            normalized_ids.astype(np.int64) + episode_offset,
        ]
    ).astype(np.int32)

    combined = {
        "obs": np.concatenate([base["obs"], dagger["obs"][dagger_keep]]),
        "masks": np.concatenate([base["masks"], dagger["masks"][dagger_keep]]),
        "actions": np.concatenate([base["actions"], dagger["actions"][dagger_keep]]),
        "rewards": np.concatenate([base["rewards"], dagger["rewards"][dagger_keep]]),
        "returns": np.concatenate([base["returns"], dagger["returns"][dagger_keep]]),
        "episode_ids": combined_episode_ids,
        "source_is_dagger": np.concatenate(
            [
                np.zeros(base_rows, dtype=np.bool_),
                np.ones(selected_dagger_rows, dtype=np.bool_),
            ]
        ),
        "sample_weights": np.concatenate(
            [
                np.ones(base_rows, dtype=np.float32),
                np.where(
                    dagger["disagreements"][dagger_keep],
                    args.disagreement_weight,
                    1.0,
                ).astype(np.float32),
            ]
        ),
        "gamma": base["gamma"],
        "card_vocab_hash": base["card_vocab_hash"],
        "card_vocab_scheme": base["card_vocab_scheme"],
        "card_vocabulary": base["card_vocabulary"],
        "teacher_weights_sha256": dagger["teacher_weights_sha256"],
        "dagger_policy_checkpoint_sha256": dagger["policy_checkpoint_sha256"],
        "dagger_beta": dagger["dagger_beta"],
    }
    if "environment_contract" in base:
        combined["environment_contract"] = base["environment_contract"]

    base_board_powers = base["board_powers"] if "board_powers" in base else np.array([])
    dagger_board_powers = (
        dagger["board_powers"][selected_episode_ids]
        if "board_powers" in dagger else np.array([])
    )
    combined["board_powers"] = np.concatenate([base_board_powers, dagger_board_powers])

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(out_path, **combined)

    total = base_rows + selected_dagger_rows
    print(f"[base] {base_rows:,} rows")
    print(f"[dagger] {selected_dagger_rows:,}/{available_dagger_rows:,} rows")
    print(f"[combined] {total:,} rows; dagger_fraction={selected_dagger_rows / total:.3f}")
    print(f"[weights] disagreement_weight={args.disagreement_weight:g}")
    print(f"[saved] {out_path} ({out_path.stat().st_size / 1e6:.1f} MB)")


if __name__ == "__main__":
    main()
