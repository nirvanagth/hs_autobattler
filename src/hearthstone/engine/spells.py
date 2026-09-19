from __future__ import annotations

from typing import Dict, List, Set

from .enums import EffectIDs, MechanicType, SpellIDs, Tags
from .event_system import EffectContext, EntityRef, Event, EventType, TriggerDef, Zone


# ---------------------------------------------------------------------------
# Legacy hand-rolled handlers (kept for backward compat; still used by the
# old hardcoded registry entries that are now superseded by build_spell_registry,
# but they are NOT removed so existing import paths don't break).
# ---------------------------------------------------------------------------

def _spell_coin(ctx: EffectContext, event: Event, trigger_uid: int) -> None:
    if not event.source_pos:
        return
    ctx.gain_gold(event.source_pos.side, 1)


def _spell_banana(ctx: EffectContext, event: Event, trigger_uid: int) -> None:
    if not event.target:
        return
    ctx.buff_perm(EntityRef(event.target.uid), 2, 2)


def _spell_bloodgem(ctx: EffectContext, event: Event, trigger_uid: int) -> None:
    if not event.target or not event.source_pos:
        return
    player = ctx.players_by_uid.get(event.source_pos.side)
    if not player:
        return
    atk, hp = player.mechanics.get_stat(MechanicType.BLOOD_GEM)
    ctx.buff_perm(EntityRef(event.target.uid), atk, hp)


def _spell_arrow(ctx: EffectContext, event: Event, trigger_uid: int) -> None:
    if not event.target:
        return
    ctx.buff_perm(EntityRef(event.target.uid), 4, 0)


def _spell_fortify(ctx: EffectContext, event: Event, trigger_uid: int) -> None:
    if not event.target:
        return
    ctx.buff_perm(EntityRef(event.target.uid), 0, 3)
    unit = ctx.resolve_unit(EntityRef(event.target.uid))
    if unit:
        unit.tags.add(Tags.TAUNT)


def _spell_apple(ctx: EffectContext, event: Event, trigger_uid: int) -> None:
    if not event.source_pos:
        return
    side = event.source_pos.side

    for _, unit in ctx.iter_store_units(side):
        ctx.buff_perm(EntityRef(unit.uid), 1, 2)


def _spell_surf_spellcraft(ctx: EffectContext, event: Event, trigger_uid: int) -> None:
    if not event.target:
        return
    ctx.attach_effect_turn(EntityRef(event.target.uid), EffectIDs.CRAB_DEATHRATTLE, 1)


# ---------------------------------------------------------------------------
# Factory functions — one per effect code.
# Each factory receives spell_id so it can close over SPELL_DB params.
# ---------------------------------------------------------------------------

def _make_gain_gold_handler(spell_id: str):
    """Spell effect: GAIN_GOLD — gives player gold equal to params['gold']."""
    from .configs import SPELL_DB
    params = SPELL_DB[spell_id].get("params", {})
    gold_amount = params.get("gold", 1)

    def _handler(ctx: EffectContext, event: Event, trigger_uid: int) -> None:
        if not event.source_pos:
            return
        ctx.gain_gold(event.source_pos.side, gold_amount)

    return _handler


def _make_buff_minion_handler(spell_id: str):
    """Spell effect: BUFF_MINION — buffs targeted board unit with atk/hp/tags from params."""
    from .configs import SPELL_DB
    params = SPELL_DB[spell_id].get("params", {})

    # Blood Gem is special: its atk/hp come from player mechanic state, not fixed params.
    # We detect it by the absence of fixed atk/hp (both 0 and no 'tags' means dynamic).
    # Actually the simplest check: if spell_id is BLOOD_GEM, delegate to dynamic path.
    is_blood_gem = (spell_id == SpellIDs.BLOOD_GEM)

    fixed_atk: int = params.get("atk", 0)
    fixed_hp: int = params.get("hp", 0)
    extra_tags: set = params.get("tags", set())

    def _handler(ctx: EffectContext, event: Event, trigger_uid: int) -> None:
        if not event.target:
            return
        ref = EntityRef(event.target.uid)
        if is_blood_gem:
            if not event.source_pos:
                return
            player = ctx.players_by_uid.get(event.source_pos.side)
            if not player:
                return
            atk, hp = player.mechanics.get_stat(MechanicType.BLOOD_GEM)
            ctx.buff_perm(ref, atk, hp)
        else:
            if not event.source_pos:
                return
            b_atk, b_hp = _tavern_spell_power_bonus(ctx, event.source_pos.side)
            ctx.buff_perm(ref, fixed_atk + b_atk, fixed_hp + b_hp)
            if extra_tags:
                unit = ctx.resolve_unit(ref)
                if unit:
                    unit.tags |= extra_tags
                    unit.recalc_stats()

    return _handler


def _make_buff_board_handler(spell_id: str):
    """Spell effect: BUFF_BOARD — buffs ALL friendly board units with atk/hp from params."""
    from .configs import SPELL_DB
    params = SPELL_DB[spell_id].get("params", {})
    atk: int = params.get("atk", 0)
    hp: int = params.get("hp", 0)
    extra_tags: set = params.get("tags", set())

    def _handler(ctx: EffectContext, event: Event, trigger_uid: int) -> None:
        if not event.source_pos:
            return
        side = event.source_pos.side
        b_atk, b_hp = _tavern_spell_power_bonus(ctx, side)
        for _, unit in ctx.iter_board_units(side):
            ctx.buff_perm(EntityRef(unit.uid), atk + b_atk, hp + b_hp)
            if extra_tags:
                unit.tags |= extra_tags
                unit.recalc_stats()

    return _handler


def _make_buff_board_type_handler(spell_id: str):
    """Spell effect: BUFF_BOARD_TYPE — buffs friendly board units of a given type."""
    from .configs import SPELL_DB
    from .enums import UnitType
    params = SPELL_DB[spell_id].get("params", {})
    atk: int = params.get("atk", 0)
    hp: int = params.get("hp", 0)
    type_filter = params.get("type", None)
    extra_tags: set = params.get("tags", set())

    def _handler(ctx: EffectContext, event: Event, trigger_uid: int) -> None:
        if not event.source_pos:
            return
        side = event.source_pos.side
        b_atk, b_hp = _tavern_spell_power_bonus(ctx, side)
        for _, unit in ctx.iter_board_units(side):
            if type_filter is not None and type_filter not in unit.types:
                continue
            ctx.buff_perm(EntityRef(unit.uid), atk + b_atk, hp + b_hp)
            if extra_tags:
                unit.tags |= extra_tags
                unit.recalc_stats()

    return _handler


def _make_discover_handler(spell_id: str):
    """Spell effect: DISCOVER — sets player.pending_discovery_request for deferred resolution."""
    from .configs import SPELL_DB
    from .entities import DiscoveryRequest
    params = SPELL_DB[spell_id].get("params", {})
    tier: int = params.get("tier", 1)
    exact_tier: bool = params.get("exact_tier", False)

    def _handler(ctx: EffectContext, event: Event, trigger_uid: int) -> None:
        if not event.source_pos:
            return
        player = ctx.players_by_uid.get(event.source_pos.side)
        if not player:
            return
        player.pending_discovery_request = DiscoveryRequest(
            tier=tier,
            exact_tier=exact_tier,
            source=f"Spell:{spell_id}",
        )

    return _handler


def _make_discover_tier_up_handler(spell_id: str):
    """Spell effect: DISCOVER_TIER_UP — discover using dynamic tier stored in spell.params.

    This is used by TRIPLET_REWARD whose tier is set dynamically at cast time.
    However, TRIPLET_REWARD is handled directly in TavernManager._cast_spell,
    so this factory covers any future DISCOVER_TIER_UP spells with static tier.
    """
    from .configs import SPELL_DB
    from .entities import DiscoveryRequest
    params = SPELL_DB[spell_id].get("params", {})
    tier: int = params.get("tier", 1)
    exact_tier: bool = params.get("exact_tier", True)

    def _handler(ctx: EffectContext, event: Event, trigger_uid: int) -> None:
        if not event.source_pos:
            return
        player = ctx.players_by_uid.get(event.source_pos.side)
        if not player:
            return
        player.pending_discovery_request = DiscoveryRequest(
            tier=tier,
            exact_tier=exact_tier,
            source=f"Spell:{spell_id}",
        )

    return _handler


def _make_get_random_unit_handler(spell_id: str):
    """Spell effect: GET_RANDOM_UNIT — draws a random unit from pool into hand."""
    from .configs import SPELL_DB
    params = SPELL_DB[spell_id].get("params", {})
    tier: int = params.get("tier", 1)
    count: int = params.get("count", 1)

    def _handler(ctx: EffectContext, event: Event, trigger_uid: int) -> None:
        if not event.source_pos:
            return
        side = event.source_pos.side
        ctx.draw_from_pool(side, tier, count)

    return _handler


def _make_free_refresh_handler(spell_id: str):
    """Spell effect: FREE_REFRESH — grants player one free tavern refresh."""
    from .configs import SPELL_DB
    params = SPELL_DB[spell_id].get("params", {})
    count: int = params.get("count", 1)

    def _handler(ctx: EffectContext, event: Event, trigger_uid: int) -> None:
        if not event.source_pos:
            return
        player = ctx.players_by_uid.get(event.source_pos.side)
        if not player:
            return
        player.free_refreshes += count

    return _handler


def _make_buff_tavern_handler(spell_id: str):
    """Spell effect: BUFF_TAVERN — buffs all units currently in the shop."""
    from .configs import SPELL_DB
    params = SPELL_DB[spell_id].get("params", {})
    atk: int = params.get("atk", 0)
    hp: int = params.get("hp", 0)
    extra_tags: set = params.get("tags", set())

    def _handler(ctx: EffectContext, event: Event, trigger_uid: int) -> None:
        if not event.source_pos:
            return
        side = event.source_pos.side
        b_atk, b_hp = _tavern_spell_power_bonus(ctx, side)
        for _, unit in ctx.iter_store_units(side):
            ctx.buff_perm(EntityRef(unit.uid), atk + b_atk, hp + b_hp)
            if extra_tags:
                unit.tags |= extra_tags
                unit.recalc_stats()

    return _handler


def _make_attach_effect_handler(spell_id: str):
    """Spell effect: ATTACH_EFFECT — attaches an effect to the targeted unit (turn-scoped)."""
    from .configs import SPELL_DB
    params = SPELL_DB[spell_id].get("params", {})
    effect_id: str = params.get("effect_id", "")
    count: int = params.get("count", 1)

    def _handler(ctx: EffectContext, event: Event, trigger_uid: int) -> None:
        if not event.target or not effect_id:
            return
        ctx.attach_effect_turn(EntityRef(event.target.uid), effect_id, count)

    return _handler


def _make_attach_crab_dr_handler(spell_id: str):
    """Spell effect: ATTACH_CRAB_DR — legacy alias kept for SURF_SPELLCRAFT."""
    return _make_attach_effect_handler(spell_id)


def _tavern_spell_power_bonus(ctx: EffectContext, side: int) -> tuple:
    """(atk, hp) bonus from TAVERN_SPELL_POWER for ordinary buff spells.

    Blood Gem is explicitly excluded (handled in its own branch).
    """
    player = ctx.players_by_uid.get(side)
    if not player:
        return (0, 0)
    return player.mechanics.get_stat(MechanicType.TAVERN_SPELL_POWER)


# ---------------------------------------------------------------------------
# B2 expansion factories (2026-09).
# ---------------------------------------------------------------------------

def _make_buff_minion_turn_handler(spell_id: str):
    """Spell effect: BUFF_MINION_TURN — turn-scoped buff on targeted board unit."""
    from .configs import SPELL_DB
    params = SPELL_DB[spell_id].get("params", {})
    atk: int = params.get("atk", 0)
    hp: int = params.get("hp", 0)

    def _handler(ctx: EffectContext, event: Event, trigger_uid: int) -> None:
        if not event.target or not event.source_pos:
            return
        b_atk, b_hp = _tavern_spell_power_bonus(ctx, event.source_pos.side)
        ctx.buff_turn(EntityRef(event.target.uid), atk + b_atk, hp + b_hp)

    return _handler


def _make_buff_minion_turn_scaling_handler(spell_id: str):
    """Spell effect: BUFF_MINION_TURN_SCALING — turn buff scaling with a counter.

    total = base + (scaling_value // per_n) * step.
    """
    from .configs import SPELL_DB
    params = SPELL_DB[spell_id].get("params", {})
    base_atk: int = params.get("base_atk", 0)
    base_hp: int = params.get("base_hp", 0)
    scaling_key: str = params.get("scaling_key", "")
    per_n: int = params.get("per_n", 1) or 1
    step_atk: int = params.get("step_atk", 0)
    step_hp: int = params.get("step_hp", 0)

    def _handler(ctx: EffectContext, event: Event, trigger_uid: int) -> None:
        if not event.target or not event.source_pos:
            return
        side = event.source_pos.side
        player = ctx.players_by_uid.get(side)
        steps = 0
        if player and scaling_key:
            steps = player.mechanics.get_scaling(scaling_key) // per_n
        b_atk, b_hp = _tavern_spell_power_bonus(ctx, side)
        ctx.buff_turn(
            EntityRef(event.target.uid),
            base_atk + steps * step_atk + b_atk,
            base_hp + steps * step_hp + b_hp,
        )

    return _handler


def _make_buff_minion_turn_tags_handler(spell_id: str):
    """Spell effect: BUFF_MINION_TURN_TAGS — turn buff plus keywords."""
    from .configs import SPELL_DB
    params = SPELL_DB[spell_id].get("params", {})
    atk: int = params.get("atk", 0)
    hp: int = params.get("hp", 0)
    extra_tags: set = params.get("tags", set())

    def _handler(ctx: EffectContext, event: Event, trigger_uid: int) -> None:
        if not event.target or not event.source_pos:
            return
        ref = EntityRef(event.target.uid)
        b_atk, b_hp = _tavern_spell_power_bonus(ctx, event.source_pos.side)
        ctx.buff_turn(ref, atk + b_atk, hp + b_hp)
        if extra_tags:
            unit = ctx.resolve_unit(ref)
            if unit:
                unit.tags |= extra_tags
                unit.recalc_stats()

    return _handler


def _make_buff_minion_cond_tags_handler(spell_id: str):
    """Spell effect: BUFF_MINION_COND_TAGS — buff always; keywords only if
    the target has cond_type."""
    from .configs import SPELL_DB
    from .enums import UnitType
    params = SPELL_DB[spell_id].get("params", {})
    atk: int = params.get("atk", 0)
    hp: int = params.get("hp", 0)
    cond_type: UnitType = params.get("cond_type")
    extra_tags: set = params.get("tags", set())

    def _handler(ctx: EffectContext, event: Event, trigger_uid: int) -> None:
        if not event.target or not event.source_pos:
            return
        ref = EntityRef(event.target.uid)
        b_atk, b_hp = _tavern_spell_power_bonus(ctx, event.source_pos.side)
        ctx.buff_perm(ref, atk + b_atk, hp + b_hp)
        if extra_tags and cond_type is not None:
            unit = ctx.resolve_unit(ref)
            if unit and cond_type in unit.types:
                unit.tags |= extra_tags
                unit.recalc_stats()

    return _handler


def _make_buff_minion_tags_handler(spell_id: str):
    """Spell effect: BUFF_MINION_TAGS — grant keywords to targeted board unit."""
    from .configs import SPELL_DB
    params = SPELL_DB[spell_id].get("params", {})
    extra_tags: set = params.get("tags", set())

    def _handler(ctx: EffectContext, event: Event, trigger_uid: int) -> None:
        if not event.target or not extra_tags:
            return
        unit = ctx.resolve_unit(EntityRef(event.target.uid))
        if unit:
            unit.tags |= extra_tags
            unit.recalc_stats()

    return _handler


_STAT_SPELL_EFFECTS = frozenset({
    "BUFF_MINION",
    "BUFF_BOARD",
    "BUFF_TAVERN",
    "BUFF_BOARD_TYPE",
    "BUFF_ALL_FRIENDLY",
    "BUFF_ALL_BY_TYPE",
})


def _make_get_random_stat_spell_handler(spell_id: str):
    """Spell effect: GET_RANDOM_STAT_SPELL — add a random stat-buff tavern
    spell to hand (excludes temporary spellcrafts)."""
    import random
    from .configs import SPELL_DB

    candidates = [
        sid for sid, data in SPELL_DB.items()
        if data.get("effect") in _STAT_SPELL_EFFECTS
        and not data.get("is_temporary", False)
    ]

    def _handler(ctx: EffectContext, event: Event, trigger_uid: int) -> None:
        if not event.source_pos or not candidates:
            return
        chosen = random.choice(candidates)
        ctx.add_spell_to_hand(event.source_pos.side, chosen)

    return _handler


def _make_get_random_unit_tier_by_turn_handler(spell_id: str):
    """Spell effect: GET_RANDOM_UNIT_TIER_BY_TURN — get a random unit of
    unit_type with tier = min(turn_number, max_tier)."""
    from .configs import SPELL_DB
    from .entities import HandCard, Unit
    from .enums import UnitType
    params = SPELL_DB[spell_id].get("params", {})
    unit_type: UnitType = params.get("unit_type")
    base_tier: int = params.get("base_tier", 1)
    per_turn: int = params.get("per_turn", 1)
    max_tier: int = params.get("max_tier", 6)

    def _handler(ctx: EffectContext, event: Event, trigger_uid: int) -> None:
        if not event.source_pos:
            return
        side = event.source_pos.side
        player = ctx.players_by_uid.get(side)
        if not player or not ctx.card_pool:
            return
        turn = max(1, getattr(player, "turn_number", 1))
        tier = max(base_tier, min(base_tier + (turn - 1) * per_turn, max_tier))

        def _pred(d) -> bool:
            return unit_type is not None and unit_type in d.get("type", [])

        drawn = ctx.card_pool.draw_discovery_cards(
            1, tier, exact_tier=True, predicate=_pred
        )
        if not drawn:
            return
        if len(player.hand) >= 10:
            ctx.card_pool.return_cards(drawn)
            return
        uid = ctx._uid_provider()
        unit = Unit.create_from_db(drawn[0], uid, side)
        player.hand.append(HandCard(uid=uid, unit=unit))

    return _handler


def _make_copy_random_other_tavern_minion_handler(spell_id: str):
    """Spell effect: COPY_RANDOM_OTHER_TAVERN_MINION — add a copy of a random
    shop minion to hand."""
    import random

    def _handler(ctx: EffectContext, event: Event, trigger_uid: int) -> None:
        if not event.source_pos:
            return
        side = event.source_pos.side
        store_units = [u for _, u in ctx.iter_store_units(side)]
        if not store_units:
            return
        chosen = random.choice(store_units)
        ctx.add_unit_to_hand(side, chosen.card_id)

    return _handler


def _make_tavern_spell_bonus_global_handler(spell_id: str):
    """Spell effect: TAVERN_SPELL_BONUS_GLOBAL — increase TAVERN_SPELL_POWER."""
    from .configs import SPELL_DB
    params = SPELL_DB[spell_id].get("params", {})
    atk: int = params.get("atk", 0)
    hp: int = params.get("hp", 0)

    def _handler(ctx: EffectContext, event: Event, trigger_uid: int) -> None:
        if not event.source_pos:
            return
        player = ctx.players_by_uid.get(event.source_pos.side)
        if not player:
            return
        player.mechanics.modify_stat(MechanicType.TAVERN_SPELL_POWER, atk, hp)

    return _handler


def _make_buff_minion_and_board_type_handler(spell_id: str):
    """Spell effect: BUFF_MINION_AND_BOARD_TYPE — buff the target, then all
    other friendly board minions of unit_type."""
    from .configs import SPELL_DB
    from .enums import UnitType
    params = SPELL_DB[spell_id].get("params", {})
    atk: int = params.get("atk", 0)
    hp: int = params.get("hp", 0)
    unit_type: UnitType = params.get("unit_type")

    def _handler(ctx: EffectContext, event: Event, trigger_uid: int) -> None:
        if not event.target or not event.source_pos:
            return
        side = event.source_pos.side
        b_atk, b_hp = _tavern_spell_power_bonus(ctx, side)
        total_atk, total_hp = atk + b_atk, hp + b_hp
        target_uid = event.target.uid
        ctx.buff_perm(EntityRef(target_uid), total_atk, total_hp)
        if unit_type is None:
            return
        for _, unit in ctx.iter_board_units(side):
            if unit.uid == target_uid:
                continue
            if unit_type in unit.types:
                ctx.buff_perm(EntityRef(unit.uid), total_atk, total_hp)

    return _handler


def _make_transform_to_random_same_type_handler(spell_id: str):
    """Spell effect: TRANSFORM_TO_RANDOM_SAME_TYPE — replace the target with
    a random same-tier minion sharing one of its types. Buffs are not kept."""
    from .auras import recalculate_board_auras
    from .entities import Unit

    def _handler(ctx: EffectContext, event: Event, trigger_uid: int) -> None:
        if not event.target or not event.source_pos:
            return
        side = event.source_pos.side
        player = ctx.players_by_uid.get(side)
        if not player or not ctx.card_pool:
            return
        pos = ctx.resolve_pos(event.target)
        if not pos or pos.zone != Zone.BOARD:
            return
        slot = pos.slot
        if slot < 0 or slot >= len(player.board):
            return
        old_unit = player.board[slot]
        if old_unit.uid != event.target.uid:
            return
        types = list(old_unit.types)
        tier = old_unit.tier
        was_golden = old_unit.is_golden

        def _pred(d) -> bool:
            if int(d.get("tier", 0)) != tier:
                return False
            dtypes = d.get("type", [])
            return any(t in dtypes for t in types)

        drawn = ctx.card_pool.draw_discovery_cards(
            1, tier, exact_tier=True, predicate=_pred
        )
        if not drawn:
            return
        player.board.pop(slot)
        ctx.card_pool.return_cards([old_unit.card_id])
        new_unit = Unit.create_from_db(
            drawn[0], ctx._uid_provider(), side, was_golden
        )
        player.board.insert(slot, new_unit)
        ctx._reindex_side(side)
        recalculate_board_auras(player.board)

    return _handler


# ---------------------------------------------------------------------------
# Effect code -> factory mapping
# ---------------------------------------------------------------------------

#: Maps SPELL_DB "effect" codes to their factory functions.
EFFECT_FACTORIES = {
    "GAIN_GOLD": _make_gain_gold_handler,
    "BUFF_MINION": _make_buff_minion_handler,
    "BUFF_BOARD": _make_buff_board_handler,
    "BUFF_BOARD_TYPE": _make_buff_board_type_handler,
    "DISCOVER": _make_discover_handler,
    "DISCOVER_TIER_UP": _make_discover_tier_up_handler,
    "GET_RANDOM_UNIT": _make_get_random_unit_handler,
    "FREE_REFRESH": _make_free_refresh_handler,
    "BUFF_TAVERN": _make_buff_tavern_handler,
    "ATTACH_EFFECT": _make_attach_effect_handler,
    "ATTACH_CRAB_DR": _make_attach_crab_dr_handler,
    "BUFF_ALL_FRIENDLY": _make_buff_board_handler,       # alias: buff all board
    "BUFF_ALL_BY_TYPE": _make_buff_board_type_handler,   # alias: buff board by type
    # --- B2 expansion effect codes (2026-09) ---
    "BUFF_MINION_TURN": _make_buff_minion_turn_handler,
    "BUFF_MINION_TURN_SCALING": _make_buff_minion_turn_scaling_handler,
    "BUFF_MINION_TURN_TAGS": _make_buff_minion_turn_tags_handler,
    "BUFF_MINION_COND_TAGS": _make_buff_minion_cond_tags_handler,
    "BUFF_MINION_TAGS": _make_buff_minion_tags_handler,
    "GET_RANDOM_STAT_SPELL": _make_get_random_stat_spell_handler,
    "GET_RANDOM_UNIT_TIER_BY_TURN": _make_get_random_unit_tier_by_turn_handler,
    "COPY_RANDOM_OTHER_TAVERN_MINION": _make_copy_random_other_tavern_minion_handler,
    "TAVERN_SPELL_BONUS_GLOBAL": _make_tavern_spell_bonus_global_handler,
    "BUFF_MINION_AND_BOARD_TYPE": _make_buff_minion_and_board_type_handler,
    "TRANSFORM_TO_RANDOM_SAME_TYPE": _make_transform_to_random_same_type_handler,
}

#: Effect codes whose spells require a board target.
_TARGET_REQUIRED_EFFECTS: Set[str] = {
    "BUFF_MINION",
    "ATTACH_EFFECT",
    "ATTACH_CRAB_DR",
    # --- B2 ---
    "TRANSFORM_TO_RANDOM_SAME_TYPE",
    "BUFF_MINION_AND_BOARD_TYPE",
    "BUFF_MINION_TURN",
    "BUFF_MINION_TURN_SCALING",
    "BUFF_MINION_TURN_TAGS",
    "BUFF_MINION_COND_TAGS",
    "BUFF_MINION_TAGS",
}


def build_spell_registry():
    """Auto-build SPELL_TRIGGER_REGISTRY and SPELLS_REQUIRE_TARGET from SPELL_DB.

    Returns:
        (registry, require_target) where registry maps spell_id -> List[TriggerDef]
        and require_target is a set of spell_ids that need a board target.
    """
    from .configs import SPELL_DB

    registry: Dict[str, List[TriggerDef]] = {}
    require_target: Set[str] = set()

    for spell_id, data in SPELL_DB.items():
        effect_code = data.get("effect", "")
        factory = EFFECT_FACTORIES.get(effect_code)
        if factory is None:
            continue  # unknown effect; leave unregistered (cast will fail gracefully)

        handler = factory(spell_id)
        registry[spell_id] = [
            TriggerDef(
                event_type=EventType.SPELL_CAST,
                condition=lambda ctx, e, uid: True,
                effect=handler,
                name=f"Spell: {data['name']}",
            )
        ]

        if effect_code in _TARGET_REQUIRED_EFFECTS:
            require_target.add(spell_id)

    return registry, require_target


# ---------------------------------------------------------------------------
# Module-level registries — auto-generated from SPELL_DB.
# These are the authoritative references imported by tavern.py.
# ---------------------------------------------------------------------------

SPELL_TRIGGER_REGISTRY, SPELLS_REQUIRE_TARGET = build_spell_registry()
