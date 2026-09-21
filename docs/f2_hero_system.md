# F2 curated hero and armor system

Date: 2026-09-21
Status: complete

## Scope

Eight versioned research-reference heroes exercise the engine mechanisms needed
before importing patch-specific live heroes:

- passive armor;
- one free refresh each turn;
- gold after Tavern upgrade;
- no-target self-damage/economy power;
- delayed economy with cooldown;
- once-per-game friendly golden target;
- repeatable friendly-board buff target;
- cooldown-based friendly-shop buff target.

These names and numbers are a research balance set, not claims about a current
live Battlegrounds patch.

## Contracts and invariants

- Armor absorbs damage before health in combat and effect damage.
- Active powers enforce cost, one use per turn, cooldown, once-per-game state,
  and target zone.
- Behavior-v7 is required for heroes; behavior-v5/v6 reject hero assignment.
- Observation schema v2 exposes own/opponent hero identity, armor, cooldown,
  uses, and availability without exposing private zones.
- Action schema v2 adds action 34 and reuses entity slots for board/store target
  selection. Legacy environments remain 2,958×34; hero environments are
  2,984×35.
- Hero definitions and roster each have independent SHA-256 contracts.

## Balance process

Two preliminary rotating-seat rounds exposed and corrected broken extremes.
The final 4,000-lobby matrix used every hero in every seat exactly 500 times.

Final ranges:

- mean placement: 3.995--4.904;
- Top-4 rate: 43.70%--58.93%;
- win rate: 11.03%--14.55%;
- most extreme pairwise score: 60.525% / 39.475%;
- seat win rate: 12.23%--12.88%.

The preregistered tolerances were at most 1.0 placement spread, 5 win-rate
points, and 11 pairwise-score points from 50%. All passed. No hero is promoted
as “best”; the roster is accepted as a mechanism-validation population.

Exact contracts and matrix hashes are frozen in
`benchmarks/hsbg_8p_heroes_v1.json`. Raw per-game and pairwise results remain in
the gitignored `artifacts/hero_f2/matrix_4000_final.json`.
