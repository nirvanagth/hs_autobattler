from __future__ import annotations

import random
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Dict, List, Optional

from .enums import CardIDs, EffectIDs, MechanicType, SpellIDs, Tags, UnitType

if TYPE_CHECKING:
    from .event_system import EffectContext, Event


def _event_system():
    """Lazy import to avoid circular import via configs -> entities -> event_system."""
    from . import event_system as _es  # noqa: PLC0415

    return _es


# ---------------------------------------------------------------------------
# Condition helpers (needed by factory functions below)
# ---------------------------------------------------------------------------


def _is_self_play(_ctx: EffectContext, event: Event, trigger_uid: int) -> bool:
    return event.source is not None and event.source.uid == trigger_uid


def _is_self_death(_ctx: EffectContext, event: Event, trigger_uid: int) -> bool:
    return event.source is not None and event.source.uid == trigger_uid


def _is_friendly_death_exclude_self(ctx: EffectContext, event: Event, trigger_uid: int) -> bool:
    es = _event_system()
    if event.event_type != es.EventType.MINION_DIED:
        return False
    dead_pos = event.source_pos or (event.snapshot.pos if event.snapshot else None)
    if not dead_pos:
        return False
    owner_pos = ctx.resolve_pos(es.EntityRef(trigger_uid))
    if not owner_pos:
        return False
    return (dead_pos.side == owner_pos.side) and (
        event.source is not None and event.source.uid != trigger_uid
    )


def _is_friendly_soc(ctx: EffectContext, _event: Event, trigger_uid: int) -> bool:
    """Condition: Start of Combat, and I'm on a board."""
    es = _event_system()
    pos = ctx.resolve_pos(es.EntityRef(trigger_uid))
    return pos is not None


# ---------------------------------------------------------------------------
# EffectDef base + subclasses
# ---------------------------------------------------------------------------


@dataclass
class EffectDef:
    """Base class for declarative effects."""

    pass


@dataclass
class DeathrattleSummon(EffectDef):
    """On death, summon token(s) at the dead unit's position."""

    token_id: str  # CardIDs value (string)
    count: int = 1


@dataclass
class DeathrattleSummonWithTag(EffectDef):
    """On death, summon token(s) and add a tag to each summoned unit."""

    token_id: str
    count: int = 1
    tag: Tags = Tags.IMMEDIATE_ATTACK


@dataclass
class BattlecryGainGold(EffectDef):
    """On self-play, gain gold immediately."""

    amount: int = 1


@dataclass
class BattlecryAddSpell(EffectDef):
    """On self-play, add spell(s) to hand."""

    spell_id: str  # SpellIDs value
    count: int = 1


@dataclass
class BattlecrySummonAtRight(EffectDef):
    """On self-play, summon a unit immediately to the right."""

    token_id: str
    count: int = 1


@dataclass
class BattlecryBuffSelf(EffectDef):
    atk: int = 0
    hp: int = 0


@dataclass
class BattlecrySpellDiscount(EffectDef):
    """On self-play, reduce spell cost by `amount` for the rest of the game."""

    amount: int = 1


@dataclass
class BattlecryModifyMechanic(EffectDef):
    """Modify a global mechanic stat (like Dune Dweller's elemental buff)."""

    mechanic: MechanicType
    atk: int = 0
    hp: int = 0


@dataclass
class ConsumeShopUnit(EffectDef):
    """Consume random shop unit, gain its stats."""

    pass


@dataclass
class BattlecryMakeGolden(EffectDef):
    """Make this minion golden on play."""

    pass


@dataclass
class SellForGold(EffectDef):
    """This minion sells for N gold instead of 1."""

    amount: int = 3


@dataclass
class RallyBuff(EffectDef):
    """Rally: when this unit attacks, buff itself (combat scope)."""

    atk: int = 0
    hp: int = 0
    use_blood_gem: bool = False  # if True, use player's Blood Gem values instead of atk/hp


@dataclass
class StartOfCombatFromHand(EffectDef):
    """SoC: if this is in your hand, summon a copy onto your board."""

    pass


@dataclass
class AvengeEffect(EffectDef):
    """Avenge(N): after N friendly deaths in combat, fire inner effect.
    The inner effect describes WHAT happens — buff self, buff type, buff adjacent, etc."""

    threshold: int
    # What to do when avenge fires:
    buff_atk: int = 0
    buff_hp: int = 0
    buff_scope: str = "combat"  # "combat" or "perm"
    buff_target: str = "self"  # "self", "friendly_type", "adjacent", "random_friendly_type"
    target_type: Optional[UnitType] = None  # for friendly_type / random_friendly_type


@dataclass
class MultiplierDef:
    """Not an EffectDef — metadata on CardDef for cards like Brann/Titus/Drakkari.
    When this unit is on board, matching triggers get extra stacks."""

    event_type_name: str  # EventType name to match (e.g. "MINION_PLAYED")
    self_only: bool = True  # True = only self-play triggers (battlecries), False = all
    extra_stacks: int = 1  # How many extra stacks (1 = double, 2 = triple)


@dataclass
class OnFriendlyPlayType(EffectDef):
    """When any friendly unit of specific type is played, buff self."""

    trigger_type: UnitType
    atk: int = 0
    hp: int = 0
    exclude_self: bool = True


@dataclass
class OnFriendlyPlayTypeDamageHero(EffectDef):
    """When friendly unit of specific type is played (excl. self), damage own hero and buff self."""

    trigger_type: UnitType
    hero_dmg: int = 1
    atk: int = 0
    hp: int = 0
    exclude_self: bool = True


@dataclass
class SellAddSpell(EffectDef):
    """On self-sell, add spell(s) to hand."""

    spell_id: str
    count: int = 1


@dataclass
class SellGetRandomUnit(EffectDef):
    """On self-sell, add a random T{tier} minion to hand."""

    tier: int = 1


@dataclass
class StartOfCombatBuffSelf(EffectDef):
    atk: int = 0
    hp: int = 0


@dataclass
class StartOfCombatBuffSelfByTier(EffectDef):
    """Gain +tier/+tier at start of combat."""

    pass


@dataclass
class OnFriendlyDeathBuff(EffectDef):
    """Gain stats when any friendly minion dies (excluding self), as a combat buff."""

    atk: int = 0
    hp: int = 0


@dataclass
class OnFriendlySummonedTypeBuff(EffectDef):
    """When a friendly unit of specific type is summoned (not played),
    gain +atk/+hp and optionally divine shield."""

    trigger_type: UnitType
    atk: int = 0
    hp: int = 0
    exclude_self: bool = True
    combat_buff: bool = False
    gain_divine_shield: bool = False


@dataclass
class DeathrattleBuffAllFriendlies(EffectDef):
    """On death, give all surviving friendly minions +atk/+hp (combat buff)."""

    atk: int = 0
    hp: int = 0


@dataclass
class DeathrattleRandomEnemyDamage(EffectDef):
    """On death, deal damage to a random enemy minion."""

    damage: int = 4


@dataclass
class CustomEffect(EffectDef):
    """For complex effects that cannot be described declaratively."""

    trigger_defs: list = field(default_factory=list)  # List[TriggerDef]


@dataclass
class EndOfTurnAddSpell(EffectDef):
    """End of turn: add spell(s) to hand."""

    spell_id: str
    count: int = 1


@dataclass
class EndOfTurnBuffAdjacent(EffectDef):
    """End of turn: buff adjacent units."""

    atk: int = 0
    hp: int = 0


@dataclass
class EndOfTurnBuffSelf(EffectDef):
    """End of turn: buff self."""

    atk: int = 0
    hp: int = 0


@dataclass
class EndOfTurnBuffBoard(EffectDef):
    """End of turn: buff all friendly board units."""

    atk: int = 0
    hp: int = 0


@dataclass
class EndOfTurnBuffBoardByType(EffectDef):
    """End of turn: buff all friendly board units of a type."""

    trigger_type: UnitType
    atk: int = 0
    hp: int = 0


@dataclass
class StartOfCombatBuffFriendlyType(EffectDef):
    """SoC: give all friendly units of type +atk/+hp (combat buff)."""

    trigger_type: UnitType
    atk: int = 0
    hp: int = 0


@dataclass
class BattlecryBuffAllByType(EffectDef):
    """BC: give all friendly units of type +atk/+hp (perm buff)."""

    trigger_type: UnitType
    atk: int = 0
    hp: int = 0


@dataclass
class OnFriendlyPlayTypeAddSpell(EffectDef):
    """When friendly of type is played, add spell to hand."""

    trigger_type: UnitType
    spell_id: str
    count: int = 1
    exclude_self: bool = True


@dataclass
class OnSummonedTypeBuffRandomOther(EffectDef):
    """When friendly of type is summoned, buff a random OTHER friendly of that type."""

    trigger_type: UnitType
    atk: int = 0
    hp: int = 0


@dataclass
class SellAddUnit(EffectDef):
    """On sell: add a specific unit to hand."""

    card_id: str


@dataclass
class RallyBuffRandomFriendlyType(EffectDef):
    """Rally: when this attacks, buff a random other friendly of type (combat buff)."""

    trigger_type: UnitType
    atk: int = 0
    hp: int = 0


@dataclass
class SellGetRandomUnitByType(EffectDef):
    """On sell: get a random unit of specific type from pool."""

    unit_type: UnitType


@dataclass
class ConsumeShopUnitForRandomFriendly(EffectDef):
    """BC: a random friendly of type consumes a shop unit for its stats."""

    trigger_type: UnitType


@dataclass
class OnTavernRefreshBuffRightmostShop(EffectDef):
    """After tavern refreshed: buff rightmost shop minion with atk/hp and optionally Reborn."""

    atk: int = 0
    hp: int = 0
    give_reborn: bool = False
    use_blood_gem: bool = False  # if True, apply blood gem count times instead


@dataclass
class SellBuffBoardScaling(EffectDef):
    """On sell: buff all board minions +atk/+hp, and increment scaling counter."""

    scaling_key: str
    atk_per: int = 0
    hp_per: int = 0


@dataclass
class StartOfCombatDamageAndBuffAdjacent(EffectDef):
    """SoC: deal damage to adjacent minions and give them ATK buff."""

    damage: int = 1
    atk: int = 0
    hp: int = 0


@dataclass
class OnHeroDamagedHealAndBuffSelf(EffectDef):
    """After hero takes damage: undo the damage and buff self +hp."""

    hp: int = 1


@dataclass
class EndOfTurnBuffAdjacentPerGolden(EffectDef):
    """EOT: buff adjacent +atk/+hp, repeat for each friendly golden minion."""

    atk: int = 0
    hp: int = 0


@dataclass
class SellDiscover(EffectDef):
    """On sell: discover a minion of base_tier (improves each turn via scaling_key)."""

    base_tier: int = 1
    scaling_key: str = ""


@dataclass
class DeathrattleAddSpell(EffectDef):
    """On death: add spell(s) to hand."""

    spell_id: str = ""
    count: int = 1


@dataclass
class RallyAddSpell(EffectDef):
    """Rally: when this unit attacks, add spell(s) to hand."""

    spell_id: str = ""
    count: int = 1


@dataclass
class EndOfTurnBuffSelfPerGolden(EffectDef):
    """EOT: buff self +atk/+hp for each friendly golden minion."""

    atk_per: int = 0
    hp_per: int = 0


@dataclass
class OnDivineShieldLostAddSpell(EffectDef):
    """After a friendly minion loses Divine Shield, add a spell to hand."""

    spell_id: str = ""
    count: int = 1


@dataclass
class BattlecryBuffAllByTypeIncludeHand(EffectDef):
    """BC: give all OTHER friendly units of type in hand AND board +atk/+hp."""

    trigger_type: UnitType = UnitType.NEUTRAL
    atk: int = 0
    hp: int = 0


@dataclass
class RallyDamageOwnBoard(EffectDef):
    """Rally: when this unit attacks, deal damage to all other friendly minions."""

    damage: int = 1


@dataclass
class DeathrattleModifyMechanic(EffectDef):
    """On death: permanently modify a global mechanic."""

    mechanic: MechanicType = MechanicType.BLOOD_GEM
    atk: int = 0
    hp: int = 0


@dataclass
class StartOfCombatBuffRandomFriendlyTypeAndDS(EffectDef):
    """SoC: give another friendly unit of type +atk/+hp and Divine Shield."""

    trigger_type: UnitType = UnitType.DRAGON
    atk: int = 0
    hp: int = 0


@dataclass
class OnSelfDamagedBuffBoard(EffectDef):
    """When this minion takes damage, buff all other friendly minions."""

    atk: int = 0
    hp: int = 0


@dataclass
class OnFriendlyRebornBuffSelf(EffectDef):
    """After a friendly minion triggers Reborn, buff self permanently."""

    atk: int = 0
    hp: int = 0


@dataclass
class DeathrattleBuffFriendlyTypeGlobal(EffectDef):
    """On death: permanently buff all friendly units of type +atk/+hp (even in hand)."""

    trigger_type: UnitType = UnitType.UNDEAD
    atk: int = 0
    hp: int = 0


@dataclass
class DeathrattleBuffShop(EffectDef):
    """On death: permanently buff all tavern shop minions +atk/+hp this game."""

    atk: int = 0
    hp: int = 0


@dataclass
class DeathrattleBuffHandRandom(EffectDef):
    """On death: give a random minion in hand +atk/+hp."""

    atk: int = 0
    hp: int = 0


@dataclass
class StartOfCombatGainGold(EffectDef):
    """Start of turn (shop phase): gain gold. Used for start-of-turn gold generators."""

    amount: int = 1


@dataclass
class OnFriendlyAttackBuffSelf(EffectDef):
    """When another friendly unit of type attacks, buff that unit permanently."""

    trigger_type: UnitType = UnitType.DRAGON
    atk: int = 0
    hp: int = 0


@dataclass
class OnSpellCastBuffSelf(EffectDef):
    """When a tavern spell is cast (played on a minion), gain +atk/+hp."""

    atk: int = 0
    hp: int = 0


@dataclass
class OnGainGoldBuffSelf(EffectDef):
    """After gaining gold (Tavern Coin), buff self +atk/+hp."""

    atk: int = 0
    hp: int = 0


@dataclass
class DeathrattleDamageAllMinions(EffectDef):
    """On death: deal damage to ALL minions on both sides."""

    damage: int = 3


@dataclass
class StartOfCombatBuffAllFriendlyType(EffectDef):
    """SoC: buff all friendly units of type +atk/+hp permanently."""

    trigger_type: UnitType = UnitType.DRAGON
    atk: int = 0
    hp: int = 0


@dataclass
class StartOfCombatGiveFriendlyTypeReborn(EffectDef):
    """SoC: give a random friendly unit of type Reborn."""

    trigger_type: UnitType = UnitType.UNDEAD


@dataclass
class AvengeAddSpell(EffectDef):
    """Avenge(N): add a spell to hand."""

    threshold: int = 3
    spell_id: str = ""
    count: int = 1


@dataclass
class BattlecryAddRandomUnit(EffectDef):
    """BC: add a random unit of specific type from pool to hand."""

    unit_type: Optional[UnitType] = None
    tier: Optional[int] = None


@dataclass
class BattlecryGainFreeRefreshes(EffectDef):
    """BC: gain N free refreshes immediately."""

    count: int = 2


@dataclass
class OnDivineShieldLostBuffUnit(EffectDef):
    """After a friendly minion loses Divine Shield, give it +atk/+hp permanently."""

    atk: int = 0
    hp: int = 0


@dataclass
class RallyBuffAllOthersByType(EffectDef):
    """Rally: buff all other friendly minions of type with 2 blood gems."""

    trigger_type: UnitType = UnitType.PIRATE
    count: int = 2  # number of blood gems to play


@dataclass
class EndOfTurnAddRandomSpell(EffectDef):
    """End of turn: add a random tavern spell from pool to hand."""

    pass


@dataclass
class OnFriendlyPlayTypeBuffSelfInHand(EffectDef):
    """While in hand, when a friendly unit of type is played, buff self."""

    trigger_type: UnitType = UnitType.MURLOC
    atk: int = 0
    hp: int = 0


@dataclass
class OnFriendlyAttackBuffTriggerSelf(EffectDef):
    """When another friendly unit of type attacks, buff self (the trigger unit) permanently."""

    trigger_type: UnitType = UnitType.DRAGON
    atk: int = 0
    hp: int = 0


@dataclass
class OnSpellCastBuffBoard(EffectDef):
    """When a tavern spell is cast, buff all friendly minions (or of a type)."""

    atk: int = 0
    hp: int = 0
    trigger_type: Optional[UnitType] = None  # None = all friendlies


@dataclass
class DeathrattleSummonTauntToken(EffectDef):
    """On death: summon N tokens and give them Taunt."""

    token_id: str = ""
    count: int = 1


@dataclass
class StartOfCombatBuffSelfByHighestAllyAtk(EffectDef):
    """SoC: set own attack to the highest friendly attack value."""

    pass


@dataclass
class StartOfCombatBuffSelfByHighestBoardAtk(EffectDef):
    """SoC: set own stats to match the highest-attack minion on board."""

    pass


@dataclass
class BattlecryMakeGoldenFriendlyByTier(EffectDef):
    """BC: make a friendly minion from tier <= max_tier golden."""

    max_tier: int = 4


@dataclass
class RallyBuffFriendlyTypeAtk(EffectDef):
    """Rally: give all other friendly units of type +atk permanently."""

    trigger_type: UnitType = UnitType.NAGA
    atk: int = 1


@dataclass
class OnFriendlyBeastDamagedBuffSelf(EffectDef):
    """When another friendly Beast takes damage, buff self +hp permanently."""

    hp: int = 2


@dataclass
class OnFriendlyBeastDamagedBuffOther(EffectDef):
    """When a friendly Beast takes damage, give a different friendly Beast +atk/+hp."""

    atk: int = 0
    hp: int = 0


@dataclass
class AvengeBuffFriendlyTypeGlobal(EffectDef):
    """Avenge(N): give all friendly units of type +atk permanently (even in hand)."""

    threshold: int = 2
    trigger_type: UnitType = UnitType.UNDEAD
    atk: int = 1
    hp: int = 0


@dataclass
class DeathrattleDestroyKiller(EffectDef):
    """On death: destroy the minion that killed this."""

    pass


@dataclass
class SellForGoldConditional(EffectDef):
    """Sells for extra gold if player lost last combat."""

    amount: int = 5


@dataclass
class DeathrattleBuffAllFriendliesGlobal(EffectDef):
    """On death: permanently buff all friendly beasts on board +atk/+hp."""

    trigger_type: UnitType = UnitType.BEAST
    atk: int = 8
    hp: int = 8


@dataclass
class EndOfTurnBuffFriendlyTypeNaga(EffectDef):
    """EoT: give all friendly Naga +atk/+hp (scales with diversity)."""

    atk: int = 2
    hp: int = 1


@dataclass
class OnFriendlyDemonDamageBuff(EffectDef):
    """After a friendly Demon deals damage, buff other friendlies +atk/+hp."""

    atk: int = 2
    hp: int = 1


@dataclass
class EndOfTurnConsumeTavernForDemon(EffectDef):
    """EoT: each friendly Demon consumes a tavern minion for its stats."""

    pass


@dataclass
class StartOfCombatBuffFriendlyTypeScaling(EffectDef):
    """SoC: give all friendlies of type +atk/+hp, scaling with elemental play count."""

    trigger_type: UnitType = UnitType.ELEMENTAL
    atk: int = 3
    hp: int = 2


@dataclass
class EndOfTurnTriggerAdjacentBattlecry(EffectDef):
    """EoT: trigger the battlecry of adjacent minions."""

    pass


@dataclass
class RallyDealDamageEqualToAtk(EffectDef):
    """Rally: deal damage equal to this minion's Attack to a random enemy."""

    pass


@dataclass
class DeathrattleGiveFriendliesScaling(EffectDef):
    """On death: give all friendlies +1/+1 and deal 1 damage to them."""

    buff_atk: int = 1
    buff_hp: int = 1
    self_damage: int = 1


# ---------------------------------------------------------------------------
# B2 expansion EffectDef types (2026-09).
# Effect semantics were assigned from card names where the live card text
# could not be verified; each flagged card should be re-checked against
# the live game before treating numbers as authoritative.
# ---------------------------------------------------------------------------


@dataclass
class BattlecryBuffAllByTypeIncludeHand(EffectDef):
    """BC: give all friendly units of type +atk/+hp (board + hand)."""

    trigger_type: UnitType = UnitType.MECH
    atk: int = 0
    hp: int = 0


@dataclass
class OnSpellCastOnSelfBuffSelf(EffectDef):
    """Whenever you cast a spell (same side), this minion gains +atk/+hp."""

    atk: int = 1
    hp: int = 1


@dataclass
class OnSpellCastScalingBuffSelf(EffectDef):
    """Every `per_n` spells you cast, this minion gains +atk/+hp."""

    per_n: int = 3
    atk: int = 1
    hp: int = 1


@dataclass
class OnSpellCastRecastRandomTavernSpell(EffectDef):
    """Whenever you cast a spell (same side), cast a random Tavern spell
    on a random valid target."""

    pass


@dataclass
class OtherSummonScalingAura(EffectDef):
    """Whenever you summon a minion of trigger_type (not self), give it +atk/+hp."""

    trigger_type: UnitType = UnitType.ELEMENTAL
    atk: int = 1
    hp: int = 1


@dataclass
class StartOfCombatBuffLeftmostTypeWindfury(EffectDef):
    """SoC: the leftmost friendly minion of trigger_type gains +atk/+hp
    (combat buff) and Windfury."""

    trigger_type: UnitType = UnitType.NAGA
    atk: int = 3
    hp: int = 3


@dataclass
class KeepFirstSpellcraftPerTurn(EffectDef):
    """The first Spellcraft you cast each turn also gives its target +atk/+hp."""

    atk: int = 1
    hp: int = 2


@dataclass
class ActivateAbility(EffectDef):
    """Tavern-phase activated ability. Simplified: auto-fires at END_OF_TURN
    if the player can afford the cost (deducted automatically)."""

    cost: int = 0


@dataclass
class ActivateGetRandomUnit(ActivateAbility):
    """Pay cost: add a random unit of unit_type (tier <= tavern tier) to hand."""

    unit_type: Optional[UnitType] = None


@dataclass
class ActivateGainGoldNextTurn(ActivateAbility):
    """Pay cost: gain `gold` Gold at the start of next turn."""

    gold: int = 3


@dataclass
class ActivateCastRandomSpells(ActivateAbility):
    """Pay cost: cast `count` random Tavern spells on random valid targets."""

    count: int = 2


@dataclass
class OnSelfAttackBuffFriendlyTypeGlobal(EffectDef):
    """Whenever this attacks: give all friendly minions of trigger_type
    (board + hand) +atk/+hp."""

    trigger_type: UnitType = UnitType.ELEMENTAL
    atk: int = 2
    hp: int = 2


@dataclass
class BattlecryBuffOtherTypeScaling(EffectDef):
    """BC: give other friendly minions of trigger_type +atk/+hp,
    plus a per-tavern-tier bonus."""

    trigger_type: UnitType = UnitType.ELEMENTAL
    atk: int = 1
    hp: int = 1
    per_tier_atk: int = 1
    per_tier_hp: int = 1


@dataclass
class OnFriendlySellTypeBuffSelf(EffectDef):
    """Whenever you sell another friendly minion of trigger_type, gain +atk/+hp."""

    trigger_type: UnitType = UnitType.NAGA
    atk: int = 2
    hp: int = 1


@dataclass
class BattlecryBuffShop(EffectDef):
    """BC: give all minions currently in your shop +atk/+hp."""

    atk: int = 1
    hp: int = 1


@dataclass
class BattlecryDiscoverMechMagnetize(EffectDef):
    """BC (simplified, no discover UI): add a random Mech
    (tier <= tavern tier) to hand and give it Magnetic."""

    pass


@dataclass
class DeathrattleBuffOneOfEachType(EffectDef):
    """DR: give a random friendly minion of each type +atk/+hp.
    Minions with ALL count for every type (may be picked repeatedly)."""

    atk: int = 2
    hp: int = 2


@dataclass
class RallyCastSpellOnRight(EffectDef):
    """When this attacks: cast a random Tavern spell on the minion to its right."""

    pass


@dataclass
class SpellcraftCastOnSelfAddCopyOncePerTurn(EffectDef):
    """When you cast a Spellcraft on this minion: add a copy of it to hand
    (once per turn)."""

    pass


@dataclass
class EndOfTurnAddRandomUnitFromList(EffectDef):
    """EoT: add a random unit of unit_type (tier <= tavern tier) to hand."""

    unit_type: Optional[UnitType] = None


@dataclass
class BattlecryBuffShopMaxTier(EffectDef):
    """BC: give shop minions with tier <= max_tier +atk/+hp."""

    atk: int = 1
    hp: int = 1
    max_tier: int = 6


@dataclass
class DeathrattleSummonFirstDeadMechs(EffectDef):
    """DR: summon the first `count` friendly Mechs that died this combat
    as fresh copies. Consumed entries are not reused by later triggers."""

    count: int = 2


@dataclass
class DeathrattleAddRandomMagneticUnit(EffectDef):
    """DR: add a random Magnetic unit (tier <= tavern tier) to hand."""

    pass


@dataclass
class OnSpellCastOnSelfCastSpellOnAdjacent(EffectDef):
    """When you cast a Spellcraft on this minion: also cast a copy of it
    on each adjacent friendly minion."""

    pass


@dataclass
class OnSelfAttackModifyMechanic(EffectDef):
    """Whenever this attacks: modify a global mechanic stat."""

    mechanic: MechanicType = MechanicType.ELEMENTAL_BUFF_BONUS
    atk: int = 1
    hp: int = 0


@dataclass
class OnFriendlyPlayTypeBuffBoardType(EffectDef):
    """Whenever you play a minion of play_type: give other friendly board
    minions of buff_type +atk/+hp."""

    play_type: UnitType = UnitType.MURLOC
    buff_type: UnitType = UnitType.MURLOC
    atk: int = 1
    hp: int = 1


@dataclass
class OnMrrgltonPlayedBuffSelf(EffectDef):
    """Whenever you play Mama Mrrglton or Papa Mrrglton (including itself),
    this minion gains +atk/+hp."""

    atk: int = 1
    hp: int = 1


@dataclass
class ImmuneWhileAttacking(EffectDef):
    """This minion is Immune while attacking: gains IMMUNE on attack declared,
    loses it after the attack resolves."""

    pass


@dataclass
class SpendGoldBuffType(EffectDef):
    """Every `gold_per` Gold you spend: give up to `max_targets` other friendly
    minions of trigger_type +atk/+hp. Paid out at end of turn."""

    trigger_type: UnitType = UnitType.PIRATE
    gold_per: int = 5
    atk: int = 4
    hp: int = 5
    max_targets: int = 2


@dataclass
class DeathrattleBuffFriendlyTypeScaling(EffectDef):
    """DR: give friendly minions of trigger_type +atk/+hp
    plus a per-tavern-tier bonus."""

    trigger_type: UnitType = UnitType.DEMON
    atk: int = 2
    hp: int = 2
    per_tier_atk: int = 1
    per_tier_hp: int = 1


@dataclass
class OnFriendlyPlayTypeBuffSelfScaling(EffectDef):
    """Whenever you play another friendly minion of trigger_type,
    gain +atk/+hp."""

    trigger_type: UnitType = UnitType.NAGA
    atk: int = 1
    hp: int = 1


@dataclass
class OnSpellCastOnTypeBuffBoard(EffectDef):
    """Whenever you cast a spell (same side): give all friendly board minions
    of trigger_type +atk/+hp."""

    trigger_type: UnitType = UnitType.NAGA
    atk: int = 1
    hp: int = 1


@dataclass
class BattlecryDeathrattleBuffTavernType(EffectDef):
    """BC and DR: give minions of trigger_type in the Tavern +atk/+hp
    this game (Dancing Barnstormer)."""

    trigger_type: UnitType = UnitType.ELEMENTAL
    atk: int = 8
    hp: int = 8


@dataclass
class OnFriendlyPlayTypeBuffBoardTypeIncludeSelf(EffectDef):
    """Whenever you play a friendly minion of play_type (including self):
    give all friendly board minions of buff_type +atk/+hp
    (Unleashed Mana Surge)."""

    play_type: UnitType = UnitType.ELEMENTAL
    buff_type: UnitType = UnitType.ELEMENTAL
    atk: int = 4
    hp: int = 4


@dataclass
class OnSummonAutomatonBuffAutomatons(EffectDef):
    """Whenever you summon an Ancestral Automaton: give other friendly
    Ancestral Automatons +atk/+hp, and give the summoned one +atk/+hp
    for each other friendly Ancestral Automaton (board + hand)."""

    atk: int = 3
    hp: int = 2


@dataclass
class EndOfTurnAddMrrglton(EffectDef):
    """At the end of your turn, get a Mama Mrrglton or a Papa Mrrglton
    (Cousin Errgl)."""

    pass


@dataclass
class RallyModifyMechanic(EffectDef):
    """Rally: modify a global mechanic stat (Moat Custodian).
    Official: Rally: Your Elementals give an extra +2/+2 this game."""

    mechanic: MechanicType = MechanicType.ELEMENTAL_BUFF_BONUS
    atk: int = 2
    hp: int = 2


@dataclass
class BattlecryBuffOtherType(EffectDef):
    """BC: give other friendly board minions of trigger_type +atk/+hp
    (Mama/Papa Mrrglton). TODO: scaling by Mrrgltons played this game."""

    trigger_type: UnitType = UnitType.MURLOC
    atk: int = 3
    hp: int = 0


@dataclass
class OnTavernSpellCastBuffSelf(EffectDef):
    """Whenever you cast a Tavern spell (not Spellcraft), gain +atk/+hp
    (Abyssal Bruiser: Has +2/+1 for each Tavern spell you've cast)."""

    atk: int = 2
    hp: int = 1


@dataclass
class DeathrattleBuffFriendlyType(EffectDef):
    """DR: give all friendly board minions of trigger_type +atk/+hp
    (Showy Cyclist). TODO: scaling every 3 spells cast."""

    trigger_type: UnitType = UnitType.NAGA
    atk: int = 2
    hp: int = 1


@dataclass
class OnSpellCastOnNagaBuffBoard(EffectDef):
    """Whenever you cast a spell on a Naga, give all friendly board
    minions +atk/+hp (Torrential Ruiner)."""

    atk: int = 2
    hp: int = 3


@dataclass
class OnPlayNagaBuffSelf(EffectDef):
    """After you play a Naga, gain +atk/+hp (Groundbreaker).
    TODO: scaling every 3 spells cast."""

    atk: int = 2
    hp: int = 2


# ---------------------------------------------------------------------------
# CardDef
# ---------------------------------------------------------------------------


@dataclass
class CardDef:
    card_id: str  # e.g. "101" or "t001"
    name: str
    tier: int
    atk: int
    hp: int
    types: list  # list[UnitType]
    tags: set = field(default_factory=set)
    is_token: bool = False
    deathrattle: bool = False  # metadata flag used by obs encoding
    effects: list = field(default_factory=list)  # list[EffectDef]
    multiplier: Optional[MultiplierDef] = None  # Brann/Titus/Drakkari

    @property
    def avenge_threshold(self) -> int:
        """Return avenge threshold if card has AvengeEffect, else 0."""
        for eff in self.effects:
            if isinstance(eff, AvengeEffect):
                return eff.threshold
        return 0


# ---------------------------------------------------------------------------
# ALL_CARDS — single source of truth for every card / token
# ---------------------------------------------------------------------------

ALL_CARDS: List[CardDef] = [
    # -----------------------------------------------------------------------
    # TIER 1 — 21 cards (patch 234747)
    # -----------------------------------------------------------------------
    CardDef(
        CardIDs.ANNOY_O_TRON,
        "Annoy-o-Tron",
        1,
        1,
        2,
        [UnitType.MECH],
        tags={Tags.DIVINE_SHIELD, Tags.TAUNT},
    ),
    CardDef(
        CardIDs.AUREATE_LAUREATE,
        "Aureate Laureate",
        1,
        1,
        1,
        [UnitType.PIRATE],
        tags={Tags.DIVINE_SHIELD},
        effects=[BattlecryMakeGolden()],
    ),
    CardDef(
        CardIDs.CORD_PULLER,
        "Cord Puller",
        1,
        1,
        1,
        [UnitType.MECH],
        tags={Tags.DIVINE_SHIELD},
        deathrattle=True,
        effects=[DeathrattleSummon(token_id=CardIDs.MICROBOT, count=1)],
    ),
    CardDef(
        CardIDs.CRACKLING_CYCLONE,
        "Crackling Cyclone",
        1,
        2,
        1,
        [UnitType.ELEMENTAL],
        tags={Tags.DIVINE_SHIELD, Tags.WINDFURY},
    ),
    CardDef(
        CardIDs.DUNE_DWELLER,
        "Dune Dweller",
        1,
        3,
        2,
        [UnitType.ELEMENTAL],
        effects=[BattlecryModifyMechanic(mechanic=MechanicType.ELEMENTAL_BUFF, atk=1, hp=1)],
    ),
    CardDef(
        CardIDs.FLIGHTY_SCOUT,
        "Flighty Scout",
        1,
        3,
        3,
        [UnitType.MURLOC],
        effects=[StartOfCombatFromHand()],
    ),
    CardDef(
        CardIDs.HARMLESS_BONEHEAD,
        "Harmless Bonehead",
        1,
        1,
        1,
        [UnitType.UNDEAD],
        deathrattle=True,
        effects=[DeathrattleSummon(token_id=CardIDs.SKELETON, count=2)],
    ),
    CardDef(
        CardIDs.MANASABER,
        "Manasaber",
        1,
        4,
        1,
        [UnitType.BEAST],
        deathrattle=True,
        effects=[DeathrattleSummon(token_id=CardIDs.CUBLING, count=2)],
    ),
    CardDef(
        CardIDs.MINTED_CORSAIR,
        "Minted Corsair",
        1,
        1,
        3,
        [UnitType.PIRATE],
        effects=[SellAddSpell(spell_id=SpellIDs.TAVERN_COIN, count=1)],
    ),
    CardDef(
        CardIDs.MISFIT_DRAGONLING,
        "Misfit Dragonling",
        1,
        2,
        1,
        [UnitType.DRAGON],
        # SoC: Gain stats equal to your Tier
        effects=[StartOfCombatBuffSelfByTier()],
    ),
    CardDef(
        CardIDs.OMINOUS_SEER,
        "Ominous Seer",
        1,
        2,
        1,
        [UnitType.DEMON, UnitType.NAGA],
        effects=[BattlecrySpellDiscount(amount=1)],
    ),
    CardDef(
        CardIDs.PICKY_EATER,
        "Picky Eater",
        1,
        1,
        1,
        [UnitType.DEMON],
        effects=[ConsumeShopUnit()],
    ),
    CardDef(
        CardIDs.RAZORFEN_GEOMANCER,
        "Razorfen Geomancer",
        1,
        2,
        1,
        [UnitType.QUILBOAR],
        effects=[BattlecryAddSpell(spell_id=SpellIDs.BLOOD_GEM, count=2)],
    ),
    CardDef(
        CardIDs.RISEN_RIDER,
        "Risen Rider",
        1,
        2,
        1,
        [UnitType.UNDEAD],
        tags={Tags.TAUNT, Tags.REBORN},
    ),
    CardDef(
        CardIDs.RIVER_SKIPPER,
        "River Skipper",
        1,
        1,
        1,
        [UnitType.MURLOC],
        effects=[SellGetRandomUnit(tier=1)],
    ),
    CardDef(
        CardIDs.ROT_HIDE_GNOLL,
        "Rot Hide Gnoll",
        1,
        1,
        4,
        [UnitType.UNDEAD],
        # +1 Atk per friendly death this combat — combat trigger
        effects=[OnFriendlyDeathBuff(atk=1, hp=0)],
    ),
    CardDef(
        CardIDs.SURF_N_SURF,
        "Surf n' Surf",
        1,
        1,
        1,
        [UnitType.NAGA, UnitType.BEAST],
        # Spellcraft: DR summon 3/2 Crab — shop-phase spellcraft
    ),
    CardDef(
        CardIDs.SWAMPSTRIKER,
        "Swampstriker",
        1,
        1,
        5,
        [UnitType.MURLOC],
        tags={Tags.WINDFURY},
        effects=[
            OnFriendlyPlayType(
                trigger_type=UnitType.MURLOC,
                atk=1,
                hp=0,
                exclude_self=True,
            )
        ],
    ),
    CardDef(
        CardIDs.TUSKED_CAMPER,
        "Tusked Camper",
        1,
        2,
        3,
        [UnitType.QUILBOAR],
        effects=[RallyBuff(use_blood_gem=True)],
    ),
    CardDef(
        CardIDs.TWILIGHT_HATCHLING,
        "Twilight Hatchling",
        1,
        1,
        1,
        [UnitType.DRAGON],
        deathrattle=True,
        effects=[
            DeathrattleSummonWithTag(
                token_id=CardIDs.TWILIGHT_WHELP,
                count=1,
                tag=Tags.IMMEDIATE_ATTACK,
            )
        ],
    ),
    CardDef(
        CardIDs.WRATH_WEAVER,
        "Wrath Weaver",
        1,
        1,
        4,
        [UnitType.DEMON],
        effects=[
            OnFriendlyPlayTypeDamageHero(
                trigger_type=UnitType.DEMON,
                hero_dmg=1,
                atk=2,
                hp=1,
                exclude_self=True,
            )
        ],
    ),
    CardDef(
        CardIDs.MOLTEN_ROCK,
        "Molten Rock",
        1,
        3,
        3,
        [UnitType.ELEMENTAL],
        effects=[
            BattlecryBuffOtherTypeScaling(
                trigger_type=UnitType.ELEMENTAL,
                atk=2,
                hp=2,
                per_tier_atk=1,
                per_tier_hp=1,
            )
        ],
    ),
    CardDef(
        CardIDs.FLEEING_FUGITIVE,
        "Fleeing Fugitive",
        1,
        5,
        2,
        [UnitType.NAGA],
        # Official: Whenever you cast a spell on this, gain +1 Health.
        effects=[OnSpellCastOnSelfBuffSelf(atk=0, hp=1)],
    ),
    CardDef(
        CardIDs.MINI_MYRMIDON,
        "Mini-Myrmidon",
        1,
        1,
        4,
        [UnitType.NAGA],
        effects=[
            OnSpellCastOnSelfBuffSelf(atk=1, hp=1),
            SpellcraftCastOnSelfAddCopyOncePerTurn(),
        ],
    ),
    # -----------------------------------------------------------------------
    # TIER 2
    # -----------------------------------------------------------------------
    CardDef(
        CardIDs.FREEDEALING_GAMBLER,
        "Freedealing Gambler",
        2,
        3,
        3,
        [],
        effects=[SellForGold(amount=3)],
    ),
    CardDef(
        CardIDs.SHELL_COLLECTOR,
        "Shell Collector",
        2,
        4,
        3,
        [],
        effects=[BattlecryAddSpell(spell_id=SpellIDs.TAVERN_COIN, count=1)],
    ),
    CardDef(
        CardIDs.SEWER_RAT,
        "Sewer Rat",
        2,
        3,
        2,
        [],
        deathrattle=True,
        effects=[DeathrattleSummon(token_id=CardIDs.TURTLE, count=1)],
    ),
    CardDef(
        CardIDs.MOON_BACON_JAZZER,
        "Moon-Bacon Jazzer",
        2,
        2,
        3,
        [UnitType.QUILBOAR],
        effects=[BattlecryModifyMechanic(mechanic=MechanicType.BLOOD_GEM, atk=0, hp=1)],
    ),
    CardDef(
        CardIDs.MECHAGNOME_INTERPRETER,
        "Mechagnome Interpreter",
        2,
        2,
        3,
        [UnitType.MECH],
        effects=[
            OnFriendlyPlayType(
                trigger_type=UnitType.MECH,
                atk=2,
                hp=1,
                exclude_self=False,
            )
        ],
    ),
    CardDef(
        CardIDs.BRIARBACK_BOOKIE,
        "Briarback Bookie",
        2,
        3,
        3,
        [UnitType.QUILBOAR],
        effects=[EndOfTurnAddSpell(spell_id=SpellIDs.BLOOD_GEM, count=1)],
    ),
    CardDef(
        CardIDs.HUMMING_BIRD,
        "Humming Bird",
        2,
        1,
        4,
        [UnitType.BEAST],
        effects=[StartOfCombatBuffFriendlyType(trigger_type=UnitType.BEAST, atk=1, hp=0)],
    ),
    CardDef(
        CardIDs.NERUBIAN_DEATHSWARMER,
        "Nerubian Deathswarmer",
        2,
        1,
        4,
        [UnitType.UNDEAD],
        effects=[BattlecryBuffAllByType(trigger_type=UnitType.UNDEAD, atk=1, hp=0)],
    ),
    CardDef(
        CardIDs.OOZELING_GLADIATOR,
        "Oozeling Gladiator",
        2,
        2,
        2,
        [],
        effects=[BattlecryAddSpell(spell_id=SpellIDs.SLIMY_SHIELD, count=2)],
    ),
    CardDef(
        CardIDs.PROPHET_OF_THE_BOAR,
        "Prophet of the Boar",
        2,
        2,
        3,
        [],
        tags={Tags.TAUNT},
        effects=[
            OnFriendlyPlayTypeAddSpell(
                trigger_type=UnitType.QUILBOAR,
                spell_id=SpellIDs.BLOOD_GEM,
                count=1,
                exclude_self=True,
            )
        ],
    ),
    CardDef(
        CardIDs.SALTSCALE_HONCHO,
        "Saltscale Honcho",
        2,
        5,
        2,
        [UnitType.MURLOC],
        effects=[OnSummonedTypeBuffRandomOther(trigger_type=UnitType.MURLOC, atk=0, hp=2)],
    ),
    CardDef(
        CardIDs.SELLEMENTAL,
        "Sellemental",
        2,
        3,
        3,
        [UnitType.ELEMENTAL],
        effects=[SellAddUnit(card_id=CardIDs.WATER_DROPLET)],
    ),
    CardDef(
        CardIDs.SLEEPY_SUPPORTER,
        "Sleepy Supporter",
        2,
        3,
        4,
        [UnitType.DRAGON],
        effects=[RallyBuffRandomFriendlyType(trigger_type=UnitType.DRAGON, atk=2, hp=3)],
    ),
    CardDef(
        CardIDs.TAD,
        "Tad",
        2,
        2,
        2,
        [UnitType.MURLOC],
        effects=[SellGetRandomUnitByType(unit_type=UnitType.MURLOC)],
    ),
    CardDef(
        CardIDs.MIND_MUCK,
        "Mind Muck",
        2,
        3,
        2,
        [UnitType.DEMON],
        effects=[ConsumeShopUnitForRandomFriendly(trigger_type=UnitType.DEMON)],
    ),
    CardDef(
        CardIDs.EMBALMING_EXPERT,
        "Embalming Expert",
        2,
        3,
        2,
        [UnitType.UNDEAD],
        effects=[OnTavernRefreshBuffRightmostShop(atk=2, hp=0, give_reborn=True)],
    ),
    CardDef(
        CardIDs.QUILLED_CABBIE,
        "Quilled Cabbie",
        2,
        2,
        5,
        [UnitType.QUILBOAR],
        effects=[
            OnTavernRefreshBuffRightmostShop(atk=0, hp=0, give_reborn=False, use_blood_gem=True)
        ],
    ),
    CardDef(
        CardIDs.GHOSTLY_YMIRJAR,
        "Ghostly Ymirjar",
        2,
        2,
        5,
        [UnitType.UNDEAD],
        effects=[
            AvengeEffect(
                threshold=4,
                buff_atk=0,
                buff_hp=0,
                buff_scope="perm",
                buff_target="free_refresh",
            )
        ],
    ),
    CardDef(
        CardIDs.FIRE_BALLER,
        "Fire Baller",
        2,
        4,
        3,
        [UnitType.ELEMENTAL],
        effects=[SellBuffBoardScaling(scaling_key="baller", atk_per=1, hp_per=0)],
    ),
    CardDef(
        CardIDs.SNOW_BALLER,
        "Snow Baller",
        2,
        3,
        4,
        [UnitType.ELEMENTAL],
        effects=[SellBuffBoardScaling(scaling_key="baller", atk_per=0, hp_per=1)],
    ),
    CardDef(
        CardIDs.IRATE_ROOSTER,
        "Irate Rooster",
        2,
        3,
        4,
        [UnitType.BEAST],
        effects=[StartOfCombatDamageAndBuffAdjacent(damage=1, atk=4, hp=0)],
    ),
    CardDef(
        CardIDs.SOUL_REWINDER,
        "Soul Rewinder",
        2,
        4,
        1,
        [UnitType.DEMON],
        effects=[OnHeroDamagedHealAndBuffSelf(hp=1)],
    ),
    CardDef(
        CardIDs.SURFING_SYLVAR,
        "Surfing Sylvar",
        2,
        1,
        2,
        [UnitType.PIRATE],
        effects=[EndOfTurnBuffAdjacentPerGolden(atk=1, hp=0)],
    ),
    CardDef(
        CardIDs.PATIENT_SCOUT,
        "Patient Scout",
        2,
        1,
        1,
        [],
        effects=[SellDiscover(base_tier=1, scaling_key="patient_scout")],
    ),
    CardDef(
        CardIDs.ANCESTRAL_AUTOMATON,
        "Ancestral Automaton",
        2,
        3,
        4,
        [UnitType.MECH],
        effects=[
            # Official: Has +3/+2 for each other Ancestral Automaton
            # you've summoned this game (wherever this is).
            OnSummonAutomatonBuffAutomatons(atk=3, hp=2)
        ],
    ),
    CardDef(
        CardIDs.METALLIC_HUNTER,
        "Metallic Hunter",
        2,
        4,
        2,
        [UnitType.MECH],
        deathrattle=True,
        # Official: Deathrattle: Get a Pointy Arrow.
        effects=[DeathrattleAddSpell(spell_id=SpellIDs.POINTY_ARROW, count=1)],
    ),
    CardDef(
        CardIDs.THOUSANDTH_PAPER_DRAKE,
        "Thousandth Paper Drake",
        2,
        2,
        3,
        [UnitType.DRAGON],
        effects=[
            OnSelfAttackModifyMechanic(
                mechanic=MechanicType.ELEMENTAL_BUFF_BONUS, atk=1, hp=0
            )
        ],
    ),
    CardDef(
        CardIDs.LAVA_LURKER,
        "Lava Lurker",
        2,
        2,
        5,
        [UnitType.NAGA],
        effects=[OnSpellCastOnSelfBuffSelf(atk=1, hp=1)],
    ),
    CardDef(
        CardIDs.THAUMATURGIST,
        "Thaumaturgist",
        2,
        1,
        2,
        [UnitType.NAGA],
        effects=[
            OnSpellCastOnSelfBuffSelf(atk=1, hp=1),
            OnSpellCastScalingBuffSelf(per_n=3, atk=1, hp=1),
        ],
    ),
    # -----------------------------------------------------------------------
    # TIER 3
    # -----------------------------------------------------------------------
    CardDef(
        CardIDs.BIRD_BUDDY,
        "Bird Buddy",
        3,
        3,
        3,
        [UnitType.BEAST],
        effects=[
            AvengeEffect(
                threshold=1,
                buff_atk=1,
                buff_hp=1,
                buff_scope="combat",
                buff_target="friendly_type",
                target_type=UnitType.BEAST,
            )
        ],
    ),
    CardDef(
        CardIDs.BUDDING_GREENTHUMB,
        "Budding Greenthumb",
        3,
        2,
        4,
        [UnitType.ELEMENTAL],
        effects=[
            AvengeEffect(
                threshold=3,
                buff_atk=2,
                buff_hp=2,
                buff_scope="perm",
                buff_target="adjacent",
            )
        ],
    ),
    CardDef(
        CardIDs.ANNOY_O_MODULE,
        "Annoy-o-Module",
        3,
        2,
        4,
        [UnitType.MECH],
        tags={Tags.DIVINE_SHIELD, Tags.TAUNT, Tags.MAGNETIC},
    ),
    CardDef(
        CardIDs.DEADLY_SPORE,
        "Deadly Spore",
        3,
        1,
        1,
        [],
        tags={Tags.VENOMOUS},
    ),
    CardDef(
        CardIDs.CADAVER_CARETAKER,
        "Cadaver Caretaker",
        3,
        3,
        3,
        [UnitType.UNDEAD],
        deathrattle=True,
        effects=[DeathrattleSummon(token_id=CardIDs.SKELETON, count=3)],
    ),
    CardDef(
        CardIDs.BRINY_BOOTLEGGER,
        "Briny Bootlegger",
        3,
        4,
        2,
        [UnitType.PIRATE],
        deathrattle=True,
        effects=[DeathrattleAddSpell(spell_id=SpellIDs.TAVERN_COIN, count=1)],
    ),
    CardDef(
        CardIDs.HANDLESS_FORSAKEN,
        "Handless Forsaken",
        3,
        2,
        1,
        [UnitType.UNDEAD],
        deathrattle=True,
        effects=[DeathrattleSummonWithTag(token_id=CardIDs.HAND_TOKEN, count=1, tag=Tags.REBORN)],
    ),
    CardDef(
        CardIDs.GREEDY_SNAKETONGUE,
        "Greedy Snaketongue",
        3,
        2,
        4,
        [UnitType.NAGA],
        effects=[RallyAddSpell(spell_id=SpellIDs.TAVERN_COIN, count=1)],
    ),
    CardDef(
        CardIDs.ROADBOAR,
        "Roadboar",
        3,
        3,
        4,
        [UnitType.QUILBOAR],
        effects=[RallyAddSpell(spell_id=SpellIDs.BLOOD_GEM, count=2)],
    ),
    CardDef(
        CardIDs.GOLDGRUBBER,
        "Goldgrubber",
        3,
        3,
        2,
        [UnitType.PIRATE],
        effects=[EndOfTurnBuffSelfPerGolden(atk_per=3, hp_per=2)],
    ),
    CardDef(
        CardIDs.GEMSPLITTER,
        "Gemsplitter",
        3,
        2,
        1,
        [UnitType.QUILBOAR],
        tags={Tags.DIVINE_SHIELD},
        effects=[OnDivineShieldLostAddSpell(spell_id=SpellIDs.BLOOD_GEM, count=1)],
    ),
    CardDef(
        CardIDs.CANOPY_SWINGER,
        "Canopy Swinger",
        3,
        4,
        5,
        [UnitType.MURLOC],
        effects=[BattlecryBuffAllByTypeIncludeHand(trigger_type=UnitType.MURLOC, atk=4, hp=0)],
    ),
    CardDef(
        CardIDs.HOT_SPRINGER,
        "Hot Springer",
        3,
        5,
        4,
        [UnitType.MURLOC],
        effects=[BattlecryBuffAllByTypeIncludeHand(trigger_type=UnitType.MURLOC, atk=0, hp=4)],
    ),
    CardDef(
        CardIDs.RAMPAGER,
        "Rampager",
        3,
        8,
        8,
        [UnitType.BEAST],
        effects=[RallyDamageOwnBoard(damage=1)],
    ),
    CardDef(
        CardIDs.FELEMENTAL,
        "Felemental",
        3,
        3,
        3,
        [UnitType.ELEMENTAL, UnitType.DEMON],
        effects=[
            CustomEffect()  # wired in build_trigger_registry via _make_felemental_bc
        ],
    ),
    CardDef(
        CardIDs.PRICKLY_PIPER,
        "Prickly Piper",
        3,
        5,
        1,
        [UnitType.QUILBOAR],
        deathrattle=True,
        effects=[DeathrattleModifyMechanic(mechanic=MechanicType.BLOOD_GEM, atk=1, hp=0)],
    ),
    CardDef(
        CardIDs.AMBER_GUARDIAN,
        "Amber Guardian",
        3,
        3,
        2,
        [UnitType.DRAGON],
        tags={Tags.TAUNT},
        effects=[
            StartOfCombatBuffRandomFriendlyTypeAndDS(trigger_type=UnitType.DRAGON, atk=2, hp=2)
        ],
    ),
    CardDef(
        CardIDs.HARDY_ORCA,
        "Hardy Orca",
        3,
        1,
        6,
        [UnitType.BEAST],
        tags={Tags.TAUNT},
        effects=[OnSelfDamagedBuffBoard(atk=1, hp=1)],
    ),
    CardDef(
        CardIDs.COLDLIGHT_DIVER,
        "Coldlight Diver",
        3,
        1,
        1,
        [UnitType.MURLOC],
        deathrattle=True,
        effects=[
            BattlecryAddSpell(
                spell_id=SpellIDs.TAVERN_COIN, count=1
            ),  # placeholder for random T1 spell
            DeathrattleAddSpell(spell_id=SpellIDs.TAVERN_COIN, count=1),
        ],
    ),
    CardDef(
        CardIDs.JELLY_BELLY,
        "Jelly Belly",
        3,
        2,
        3,
        [UnitType.UNDEAD],
        effects=[OnFriendlyRebornBuffSelf(atk=2, hp=3)],
    ),
    CardDef(
        CardIDs.ANUBARAK_NERUBIAN_KING,
        "Anub'arak, Nerubian King",
        3,
        3,
        2,
        [UnitType.UNDEAD],
        deathrattle=True,
        effects=[DeathrattleBuffFriendlyTypeGlobal(trigger_type=UnitType.UNDEAD, atk=1, hp=0)],
    ),
    CardDef(
        CardIDs.ARANASI_ALCHEMIST,
        "Aranasi Alchemist",
        3,
        1,
        2,
        [UnitType.DEMON, UnitType.NAGA],
        tags={Tags.TAUNT, Tags.REBORN},
        deathrattle=True,
        effects=[DeathrattleBuffShop(atk=0, hp=1)],
    ),
    CardDef(
        CardIDs.BASSGILL,
        "Bassgill",
        3,
        5,
        2,
        [UnitType.MURLOC],
        deathrattle=True,
        effects=[DeathrattleBuffHandRandom(atk=5, hp=5)],
    ),
    CardDef(
        CardIDs.BRIARBACK_DRUMMER,
        "Briarback Drummer",
        3,
        5,
        2,
        [UnitType.QUILBOAR],
        effects=[BattlecryAddSpell(spell_id=SpellIDs.BLOOD_GEM_BARRAGE, count=1)],
    ),
    CardDef(
        CardIDs.DEFLECT_O_BOT,
        "Deflect-o-Bot",
        3,
        3,
        2,
        [UnitType.MECH],
        tags={Tags.DIVINE_SHIELD},
        effects=[
            OnFriendlySummonedTypeBuff(
                trigger_type=UnitType.MECH,
                atk=2,
                hp=0,
                exclude_self=True,
                combat_buff=True,
                gain_divine_shield=True,
            )
        ],
    ),
    CardDef(
        CardIDs.PEGGY_STURDYBONE,
        "Peggy Sturdybone",
        3,
        2,
        1,
        [UnitType.PIRATE, UnitType.UNDEAD],
        effects=[
            # When a card added to hand, buff another friendly pirate
            # Model as: on friendly PIRATE play, buff another pirate +2/+1
            OnFriendlyPlayType(trigger_type=UnitType.PIRATE, atk=2, hp=1, exclude_self=False)
        ],
    ),
    CardDef(
        CardIDs.PREHISTORIC_TINKERER,
        "Prehistoric Tinkerer",
        3,
        4,
        2,
        [UnitType.MECH],
        tags={Tags.DIVINE_SHIELD},
        effects=[OnTavernRefreshBuffRightmostShop(atk=2, hp=2, give_reborn=False)],
    ),
    CardDef(
        CardIDs.ROARING_RECRUITER,
        "Roaring Recruiter",
        3,
        2,
        8,
        [UnitType.DRAGON],
        effects=[OnFriendlyAttackBuffSelf(trigger_type=UnitType.DRAGON, atk=3, hp=1)],
    ),
    CardDef(
        CardIDs.SCOURFIN,
        "Scourfin",
        3,
        3,
        3,
        [UnitType.MURLOC],
        deathrattle=True,
        effects=[DeathrattleBuffHandRandom(atk=5, hp=5)],
    ),
    CardDef(
        CardIDs.TARDY_TRAVELER,
        "Tardy Traveler",
        3,
        3,
        4,
        [],
        effects=[
            SellAddSpell(spell_id=SpellIDs.TAVERN_COIN, count=1)  # simplified: get a coin
        ],
    ),
    CardDef(
        CardIDs.TECHNICAL_ELEMENT,
        "Technical Element",
        3,
        5,
        6,
        [UnitType.MECH, UnitType.ELEMENTAL],
        tags={Tags.MAGNETIC},
    ),
    CardDef(
        CardIDs.THE_GLAD_IATOR,
        "The Glad-iator",
        3,
        3,
        3,
        [],
        tags={Tags.DIVINE_SHIELD},
        effects=[OnSpellCastBuffSelf(atk=1, hp=0)],
    ),
    CardDef(
        CardIDs.TIMECAPN_HOOKTAIL,
        "Timecap'n Hooktail",
        3,
        1,
        4,
        [UnitType.PIRATE, UnitType.DRAGON],
        effects=[OnSpellCastBuffSelf(atk=1, hp=0)],
    ),
    CardDef(
        CardIDs.UNDERHANDED_DEALER,
        "Underhanded Dealer",
        3,
        3,
        3,
        [UnitType.DEMON],
        effects=[OnGainGoldBuffSelf(atk=1, hp=2)],
    ),
    CardDef(
        CardIDs.WAVELING,
        "Waveling",
        3,
        6,
        1,
        [UnitType.ELEMENTAL],
        effects=[OnTavernRefreshBuffRightmostShop(atk=2, hp=2, give_reborn=False)],
    ),
    CardDef(
        CardIDs.WHEELED_CREWMATE,
        "Wheeled Crewmate",
        3,
        6,
        3,
        [UnitType.MECH],
        deathrattle=True,
        effects=[
            BattlecryModifyMechanic(mechanic=MechanicType.ELEMENTAL_BUFF, atk=0, hp=0)
            # Actually this reduces tavern upgrade cost; model as no-op for now
        ],
    ),
    CardDef(
        CardIDs.WILDFIRE_ELEMENTAL,
        "Wildfire Elemental",
        3,
        6,
        3,
        [UnitType.ELEMENTAL],
        tags={Tags.CLEAVE},
    ),
    CardDef(
        CardIDs.BREAKOUT_MASTERMIND,
        "Breakout Mastermind",
        3,
        5,
        5,
        [UnitType.MURLOC],
        # Official: Activate (2): Get a random Murloc.
        effects=[ActivateGetRandomUnit(unit_type=UnitType.MURLOC, cost=2)],
    ),
    CardDef(
        CardIDs.DUSTBONE_DEVASTATOR,
        "Dustbone Devastator",
        3,
        2,
        6,
        [UnitType.UNDEAD],
        effects=[
            AvengeEffect(
                threshold=3,
                buff_atk=2,
                buff_hp=1,
                buff_scope="perm",
                buff_target="friendly_type",
                target_type=UnitType.UNDEAD,
            )
        ],
    ),
    CardDef(
        CardIDs.MAMA_MRRGLTON,
        "Mama Mrrglton",
        3,
        4,
        2,
        [UnitType.MURLOC],
        # Official: Battlecry: Give your other Murlocs +3 Attack.
        # (Improved by each Mrrglton you played this game! - TODO)
        effects=[
            BattlecryBuffOtherType(
                trigger_type=UnitType.MURLOC, atk=3, hp=0
            ),
        ],
    ),
    CardDef(
        CardIDs.METEORITE_CRASHER,
        "Meteorite Crasher",
        3,
        4,
        4,
        [UnitType.ELEMENTAL],
        # Official: After you sell an Elemental, gain +4/+4.
        effects=[
            OnFriendlySellTypeBuffSelf(
                trigger_type=UnitType.ELEMENTAL, atk=4, hp=4
            )
        ],
    ),
    CardDef(
        CardIDs.PAPA_MRRGLTON,
        "Papa Mrrglton",
        3,
        2,
        4,
        [UnitType.MURLOC],
        # Official: Battlecry: Give your other Murlocs +3 Health.
        # (Improved by each Mrrglton you played this game! - TODO)
        effects=[
            BattlecryBuffOtherType(
                trigger_type=UnitType.MURLOC, atk=0, hp=3
            ),
        ],
    ),
    CardDef(
        CardIDs.PRIVATE_INVESTIGATOR,
        "Private Investigator",
        3,
        5,
        6,
        [UnitType.PIRATE],
        # Official: Activate (1): Gain 2 Gold next turn.
        effects=[ActivateGainGoldNextTurn(gold=2, cost=1)],
    ),
    CardDef(
        CardIDs.SAND_SWIRLER,
        "Sand Swirler",
        3,
        3,
        2,
        [UnitType.ELEMENTAL],
        # Official: Battlecry: Your Elementals give an extra +2 Attack this game.
        effects=[
            BattlecryModifyMechanic(
                mechanic=MechanicType.ELEMENTAL_BUFF_BONUS, atk=2, hp=0
            )
        ],
    ),
    CardDef(
        CardIDs.DEEP_SEA_ANGLER,
        "Deep-Sea Angler",
        3,
        2,
        3,
        [UnitType.NAGA],
        effects=[RallyCastSpellOnRight()],
    ),
    CardDef(
        CardIDs.WAVERIDER,
        "Waverider",
        3,
        2,
        6,
        [UnitType.NAGA],
        effects=[
            StartOfCombatBuffLeftmostTypeWindfury(
                trigger_type=UnitType.NAGA, atk=3, hp=3
            )
        ],
    ),
    # -----------------------------------------------------------------------
    # TIER 4
    # -----------------------------------------------------------------------
    CardDef(
        CardIDs.ACCORD_O_TRON,
        "Accord-o-Tron",
        4,
        5,
        5,
        [UnitType.MECH],
        tags={Tags.MAGNETIC},
        effects=[StartOfCombatGainGold(amount=1)],
    ),
    CardDef(
        CardIDs.BLADE_COLLECTOR,
        "Blade Collector",
        4,
        3,
        2,
        [],
        tags={Tags.CLEAVE},
    ),
    CardDef(
        CardIDs.BONKER,
        "Bonker",
        4,
        2,
        7,
        [UnitType.QUILBOAR],
        effects=[RallyBuffAllOthersByType(trigger_type=UnitType.ALL, count=2)],
    ),
    CardDef(
        CardIDs.DEVOUT_HELLCALLER,
        "Devout Hellcaller",
        4,
        2,
        2,
        [UnitType.DEMON],
        effects=[
            OnFriendlyDeathBuff(atk=1, hp=2)  # simplified: any friendly death
        ],
    ),
    CardDef(
        CardIDs.EN_DJINN_BLAZER,
        "En-Djinn Blazer",
        4,
        4,
        4,
        [UnitType.ELEMENTAL],
        effects=[OnTavernRefreshBuffRightmostShop(atk=2, hp=2, give_reborn=False)],
    ),
    CardDef(
        CardIDs.FRIENDLY_GEIST,
        "Friendly Geist",
        4,
        6,
        3,
        [UnitType.UNDEAD],
        deathrattle=True,
        effects=[DeathrattleModifyMechanic(mechanic=MechanicType.ELEMENTAL_BUFF, atk=1, hp=0)],
    ),
    CardDef(
        CardIDs.GEOMAGUS_ROOGUG,
        "Geomagus Roogug",
        4,
        4,
        6,
        [UnitType.QUILBOAR],
        tags={Tags.DIVINE_SHIELD},
    ),
    CardDef(
        CardIDs.GREASE_BOT,
        "Grease Bot",
        4,
        2,
        4,
        [UnitType.MECH],
        tags={Tags.DIVINE_SHIELD},
        effects=[OnDivineShieldLostBuffUnit(atk=2, hp=2)],
    ),
    CardDef(
        CardIDs.HEROIC_UNDERDOG,
        "Heroic Underdog",
        4,
        1,
        10,
        [],
        tags={Tags.STEALTH},
        effects=[
            RallyBuff(atk=1, hp=0)  # simplified: gain +1 atk when attacks
        ],
    ),
    CardDef(
        CardIDs.HUMON_GOZZ,
        "Humon'gozz",
        4,
        5,
        5,
        [],
        tags={Tags.DIVINE_SHIELD},
        effects=[BattlecryModifyMechanic(mechanic=MechanicType.ELEMENTAL_BUFF, atk=1, hp=2)],
    ),
    CardDef(
        CardIDs.INDUSTRIOUS_DECKHAND,
        "Industrious Deckhand",
        4,
        3,
        5,
        [UnitType.PIRATE],
        effects=[StartOfCombatGainGold(amount=2)],
    ),
    CardDef(
        CardIDs.KING_BAGURGLE,
        "King Bagurgle",
        4,
        3,
        4,
        [UnitType.MURLOC],
        effects=[BattlecryBuffAllByTypeIncludeHand(trigger_type=UnitType.MURLOC, atk=2, hp=3)],
    ),
    CardDef(
        CardIDs.MARQUEE_TICKER,
        "Marquee Ticker",
        4,
        1,
        5,
        [],
        effects=[EndOfTurnAddRandomSpell()],
    ),
    CardDef(
        CardIDs.PRIZED_PROMO_DRAKE,
        "Prized Promo-Drake",
        4,
        1,
        1,
        [UnitType.DRAGON],
        effects=[StartOfCombatBuffAllFriendlyType(trigger_type=UnitType.DRAGON, atk=4, hp=4)],
    ),
    CardDef(
        CardIDs.PROSTHETIC_HAND,
        "Prosthetic Hand",
        4,
        3,
        1,
        [UnitType.MECH, UnitType.UNDEAD],
        tags={Tags.MAGNETIC, Tags.REBORN},
    ),
    CardDef(
        CardIDs.RAZORFEN_FLAPPER,
        "Razorfen Flapper",
        4,
        5,
        3,
        [UnitType.QUILBOAR],
        deathrattle=True,
        effects=[DeathrattleAddSpell(spell_id=SpellIDs.BLOOD_GEM_BARRAGE, count=1)],
    ),
    CardDef(
        CardIDs.REFRESHING_ANOMALY,
        "Refreshing Anomaly",
        4,
        4,
        5,
        [UnitType.ELEMENTAL],
        effects=[BattlecryGainFreeRefreshes(count=2)],
    ),
    CardDef(
        CardIDs.SILENT_ENFORCER,
        "Silent Enforcer",
        4,
        6,
        2,
        [UnitType.DEMON],
        tags={Tags.TAUNT},
        deathrattle=True,
        effects=[DeathrattleDamageAllMinions(damage=2)],
    ),
    CardDef(
        CardIDs.SIN_DOREI_STRAIGHT_SHOT,
        "Sin'dorei Straight Shot",
        4,
        3,
        4,
        [],
        tags={Tags.DIVINE_SHIELD, Tags.WINDFURY},
    ),
    CardDef(
        CardIDs.SLY_RAPTOR,
        "Sly Raptor",
        4,
        1,
        4,
        [UnitType.BEAST],
        deathrattle=True,
        effects=[
            DeathrattleSummon(token_id=CardIDs.SKELETON, count=1)  # simplified: summon 8/8 beast
        ],
    ),
    CardDef(
        CardIDs.SOULSPLITTER,
        "Soulsplitter",
        4,
        4,
        2,
        [UnitType.UNDEAD],
        tags={Tags.REBORN},
        effects=[StartOfCombatGiveFriendlyTypeReborn(trigger_type=UnitType.UNDEAD)],
    ),
    CardDef(
        CardIDs.SPIRIT_DRAKE,
        "Spirit Drake",
        4,
        1,
        8,
        [UnitType.DRAGON],
        effects=[
            AvengeEffect(
                threshold=3,
                buff_atk=0,
                buff_hp=0,
                buff_scope="perm",
                buff_target="add_spell",
                target_type=None,
            )
        ],
    ),
    CardDef(
        CardIDs.TAVERN_TEMPEST,
        "Tavern Tempest",
        4,
        2,
        2,
        [UnitType.ELEMENTAL],
        effects=[BattlecryAddRandomUnit(unit_type=UnitType.ELEMENTAL)],
    ),
    CardDef(
        CardIDs.TUNNEL_BLASTER,
        "Tunnel Blaster",
        4,
        3,
        7,
        [UnitType.UNDEAD],
        tags={Tags.TAUNT},
        deathrattle=True,
        effects=[DeathrattleDamageAllMinions(damage=3)],
    ),
    CardDef(
        CardIDs.WANNABE_GARGOYLE,
        "Wannabe Gargoyle",
        4,
        9,
        1,
        [UnitType.UNDEAD],
        tags={Tags.REBORN},
    ),
    CardDef(
        CardIDs.WITCHWING_NESTMATRON,
        "Witchwing Nestmatron",
        4,
        3,
        5,
        [UnitType.DRAGON],
        effects=[
            AvengeEffect(
                threshold=3,
                buff_atk=0,
                buff_hp=0,
                buff_scope="perm",
                buff_target="add_unit",
                target_type=None,
            )
        ],
    ),
    CardDef(
        CardIDs.TRENCH_FIGHTER,
        "Trench Fighter",
        4,
        6,
        6,
        [UnitType.NAGA],
        effects=[EndOfTurnAddSpell(spell_id=SpellIDs.GEM_CONFISCATION, count=1)],
    ),
    CardDef(
        CardIDs.GUNPOWDER_COURIER,
        "Gunpowder Courier",
        4,
        2,
        6,
        [UnitType.PIRATE],
        effects=[
            OnGainGoldBuffSelf(atk=2, hp=0)  # simplified: gain +2 atk when gaining gold
        ],
    ),
    # --- remaining T4 cards ---
    CardDef(
        CardIDs.BREAM_COUNTER,
        "Bream Counter",
        4,
        4,
        4,
        [UnitType.MURLOC],
        effects=[OnFriendlyPlayTypeBuffSelfInHand(trigger_type=UnitType.MURLOC, atk=4, hp=4)],
    ),
    CardDef(
        CardIDs.DAGGERSPINE_THRASHER,
        "Daggerspine Thrasher",
        4,
        3,
        5,
        [UnitType.NAGA],
        # Whenever you cast a spell, gain Divine Shield, Windfury, or Venomous — complex random; model as OnSpellCastBuffSelf
        effects=[OnSpellCastBuffSelf(atk=1, hp=0)],
    ),
    CardDef(
        CardIDs.MONSTROUS_MACAW,
        "Monstrous Macaw",
        4,
        5,
        4,
        [UnitType.BEAST],
        # Rally: Trigger left-most Deathrattle — complex; model as simple rally buff
        effects=[RallyBuff(atk=1, hp=1)],
    ),
    CardDef(
        CardIDs.PLANKWALKER,
        "Plankwalker",
        4,
        6,
        4,
        [UnitType.NAGA],
        effects=[OnSpellCastBuffBoard(atk=2, hp=1)],
    ),
    CardDef(
        CardIDs.RYLAK_METALHEAD,
        "Rylak Metalhead",
        4,
        5,
        3,
        [UnitType.MECH],
        tags={Tags.TAUNT},
        deathrattle=True,
        # DR: Trigger battlecry of adjacent minion — complex; model as buff
        effects=[DeathrattleBuffAllFriendlies(atk=1, hp=1)],
    ),
    CardDef(
        CardIDs.SUNKEN_ADVOCATE,
        "Sunken Advocate",
        4,
        2,
        7,
        [UnitType.NAGA],
        effects=[RallyBuffFriendlyTypeAtk(trigger_type=UnitType.NAGA, atk=1)],
    ),
    CardDef(
        CardIDs.TORTOLLAN_BLUE_SHELL,
        "Tortollan Blue Shell",
        4,
        3,
        6,
        [],
        effects=[SellForGoldConditional(amount=5)],
    ),
    CardDef(
        CardIDs.TRIGORE_THE_LASHER,
        "Trigore the Lasher",
        4,
        9,
        3,
        [UnitType.BEAST],
        effects=[OnFriendlyBeastDamagedBuffSelf(hp=2)],
    ),
    CardDef(
        CardIDs.FLAMING_ENFORCER,
        "Flaming Enforcer",
        4,
        4,
        5,
        [UnitType.ELEMENTAL],
        effects=[
            # EoT: consume highest-Health tavern minion — model as EndOfTurnBuffSelf
            EndOfTurnBuffSelf(atk=2, hp=2)
        ],
    ),
    CardDef(
        CardIDs.ICHORON_THE_PROTECTOR,
        "Ichoron the Protector",
        4,
        3,
        1,
        [UnitType.ELEMENTAL],
        tags={Tags.DIVINE_SHIELD},
        effects=[
            # Whenever you play an Elemental, give it DS until next turn — model as OnFriendlyPlayType buff
            OnFriendlyPlayType(trigger_type=UnitType.ELEMENTAL, atk=0, hp=1, exclude_self=True)
        ],
    ),
    CardDef(
        CardIDs.PERSISTENT_POET,
        "Persistent Poet",
        4,
        2,
        3,
        [UnitType.DRAGON],
        tags={Tags.DIVINE_SHIELD},
        # Adjacent Dragons keep bonus keywords — aura-like; model as keyword-only
    ),
    CardDef(
        CardIDs.AUTO_ASSEMBLER,
        "Auto Assembler",
        4,
        2,
        2,
        [UnitType.MECH],
        tags={Tags.MAGNETIC},
        effects=[ActivateGetRandomUnit(cost=2, unit_type=UnitType.MECH)],
    ),
    CardDef(
        CardIDs.CAPTAIN_COOKIE,
        "Captain Cookie",
        4,
        5,
        3,
        [UnitType.MURLOC, UnitType.PIRATE],
        effects=[EndOfTurnAddRandomUnitFromList(unit_type=UnitType.MURLOC)],
    ),
    CardDef(
        CardIDs.CLUNKER_JUNKER,
        "Clunker Junker",
        4,
        3,
        4,
        [UnitType.MECH],
        effects=[BattlecryDiscoverMechMagnetize()],
    ),
    CardDef(
        CardIDs.DEEPWATER_CHIEFTAIN,
        "Deepwater Chieftain",
        4,
        3,
        2,
        [UnitType.MURLOC],
        effects=[
            OnFriendlyPlayTypeBuffBoardType(
                play_type=UnitType.MURLOC,
                buff_type=UnitType.MURLOC,
                atk=1,
                hp=1,
            )
        ],
    ),
    CardDef(
        CardIDs.GLOWING_CINDER,
        "Glowing Cinder",
        4,
        4,
        1,
        [UnitType.ELEMENTAL],
        effects=[
            OtherSummonScalingAura(
                trigger_type=UnitType.ELEMENTAL, atk=1, hp=1
            )
        ],
    ),
    CardDef(
        CardIDs.MOTLEY_PHALANX,
        "Motley Phalanx",
        4,
        3,
        3,
        [UnitType.ALL],
        tags={Tags.TAUNT},
        deathrattle=True,
        # Official: DR: Give a friendly minion of each type +3/+3 permanently.
        effects=[DeathrattleBuffOneOfEachType(atk=3, hp=3)],
    ),
    CardDef(
        CardIDs.ABYSSAL_BRUISER,
        "Abyssal Bruiser",
        4,
        2,
        1,
        [UnitType.NAGA],
        tags={Tags.DIVINE_SHIELD},
        # Official: Divine Shield. Has +2/+1 for each Tavern spell
        # you've cast this game.
        effects=[OnTavernSpellCastBuffSelf(atk=2, hp=1)],
    ),
    CardDef(
        CardIDs.CAGEY_CONJURER,
        "Cagey Conjurer",
        4,
        5,
        3,
        [UnitType.NAGA],
        # Official: Activate (1): Cast 2 random Tavern spells
        # (targets this if possible).
        effects=[ActivateCastRandomSpells(count=2, cost=1)],
    ),
    CardDef(
        CardIDs.RIMESCALE_PRIESTESS,
        "Rimescale Priestess",
        4,
        3,
        3,
        [UnitType.NAGA],
        effects=[OnSpellCastOnSelfBuffSelf(atk=1, hp=1)],
    ),
    CardDef(
        CardIDs.SEAFLOOR_RECRUITER,
        "Seafloor Recruiter",
        4,
        3,
        5,
        [UnitType.NAGA],
        effects=[KeepFirstSpellcraftPerTurn(atk=1, hp=2)],
    ),
    CardDef(
        CardIDs.ZESTY_SHAKER,
        "Zesty Shaker",
        4,
        6,
        7,
        [UnitType.NAGA],
        effects=[
            OnFriendlySellTypeBuffSelf(
                trigger_type=UnitType.NAGA, atk=2, hp=1
            )
        ],
    ),
    # -----------------------------------------------------------------------
    # TIER 5
    # -----------------------------------------------------------------------
    CardDef(
        CardIDs.BRANN_BRONZEBEARD,
        "Brann Bronzebeard",
        5,
        2,
        4,
        [],
        multiplier=MultiplierDef(event_type_name="MINION_PLAYED", self_only=True, extra_stacks=1),
    ),
    CardDef(
        CardIDs.TITUS_RIVENDARE,
        "Titus Rivendare",
        5,
        1,
        7,
        [],
        multiplier=MultiplierDef(event_type_name="MINION_DIED", self_only=True, extra_stacks=1),
    ),
    CardDef(
        CardIDs.DRAKKARI_ENCHANTER,
        "Drakkari Enchanter",
        5,
        1,
        5,
        [],
        multiplier=MultiplierDef(event_type_name="END_OF_TURN", self_only=False, extra_stacks=1),
    ),
    CardDef(
        CardIDs.GENTLE_DJINNI,
        "Gentle Djinni",
        5,
        4,
        5,
        [UnitType.ELEMENTAL],
        tags={Tags.TAUNT},
        deathrattle=True,
        effects=[BattlecryAddRandomUnit(unit_type=UnitType.ELEMENTAL)],
    ),
    CardDef(
        CardIDs.INDOMITABLE_MOUNT,
        "Indomitable Mount",
        5,
        3,
        6,
        [UnitType.BEAST],
        deathrattle=True,
        effects=[BattlecryAddRandomUnit(unit_type=UnitType.BEAST, tier=4)],
    ),
    CardDef(
        CardIDs.CHAMPION_OF_THE_PRIMUS,
        "Champion of the Primus",
        5,
        2,
        10,
        [UnitType.UNDEAD],
        effects=[
            AvengeBuffFriendlyTypeGlobal(threshold=2, trigger_type=UnitType.UNDEAD, atk=1, hp=0)
        ],
    ),
    CardDef(
        CardIDs.CORRUPTED_MYRMIDON,
        "Corrupted Myrmidon",
        5,
        3,
        3,
        [UnitType.DEMON],
        effects=[
            StartOfCombatBuffSelf(atk=3, hp=3)  # simplified: doubles own stats
        ],
    ),
    CardDef(
        CardIDs.SILITHID_BURROWER,
        "Silithid Burrower",
        5,
        5,
        4,
        [UnitType.BEAST],
        deathrattle=True,
        effects=[
            DeathrattleBuffFriendlyTypeGlobal(trigger_type=UnitType.BEAST, atk=1, hp=1),
            AvengeEffect(threshold=1, buff_atk=1, buff_hp=1, buff_scope="perm", buff_target="self"),
        ],
    ),
    CardDef(
        CardIDs.GHOUL_OF_THE_FEAST,
        "Ghoul of the Feast",
        5,
        2,
        7,
        [UnitType.UNDEAD],
        effects=[
            AvengeEffect(
                threshold=1,
                buff_atk=2,
                buff_hp=2,
                buff_scope="perm",
                buff_target="friendly_type",
                target_type=None,
            )
        ],
    ),
    CardDef(
        CardIDs.TWILIGHT_WATCHER,
        "Twilight Watcher",
        5,
        3,
        7,
        [UnitType.DRAGON],
        effects=[OnFriendlyAttackBuffTriggerSelf(trigger_type=UnitType.DRAGON, atk=1, hp=3)],
    ),
    CardDef(
        CardIDs.UNFORGIVING_TREANT,
        "Unforgiving Treant",
        5,
        3,
        12,
        [],
        tags={Tags.TAUNT},
        effects=[OnSelfDamagedBuffBoard(atk=2, hp=0)],
    ),
    CardDef(
        CardIDs.NOMI_KITCHEN_NIGHTMARE,
        "Nomi, Kitchen Nightmare",
        5,
        4,
        4,
        [],
        effects=[
            # After you play an Elemental, give Elementals in tavern +2/+2 — model as OnFriendlyPlayType buff shop
            OnFriendlyPlayType(trigger_type=UnitType.ELEMENTAL, atk=2, hp=2, exclude_self=False)
        ],
    ),
    CardDef(
        CardIDs.BILE_SPITTER,
        "Bile Spitter",
        5,
        1,
        10,
        [UnitType.MURLOC],
        tags={Tags.VENOMOUS},
        effects=[
            RallyBuffRandomFriendlyType(trigger_type=UnitType.MURLOC, atk=0, hp=0)
            # Rally: give another Murloc Venomous — simplified as no-buff rally
        ],
    ),
    CardDef(
        CardIDs.RAZORFEN_VINEWEAVER,
        "Razorfen Vineweaver",
        5,
        5,
        5,
        [UnitType.QUILBOAR],
        effects=[
            RallyBuff(use_blood_gem=True)  # plays 3 blood gems on itself
        ],
    ),
    CardDef(
        CardIDs.CARAPACE_RAISER,
        "Carapace Raiser",
        5,
        6,
        3,
        [UnitType.UNDEAD],
        deathrattle=True,
        effects=[DeathrattleAddSpell(spell_id=SpellIDs.HAUNTED_CARAPACE, count=1)],
    ),
    CardDef(
        CardIDs.SHADOWDANCER,
        "Shadowdancer",
        5,
        5,
        4,
        [],
        tags={Tags.TAUNT},
        deathrattle=True,
        effects=[DeathrattleAddSpell(spell_id=SpellIDs.STAFF_OF_ENRICHMENT, count=1)],
    ),
    CardDef(
        CardIDs.FIRESCALE_HOARDER,
        "Firescale Hoarder",
        5,
        5,
        5,
        [UnitType.DRAGON],
        deathrattle=True,
        effects=[
            BattlecryAddSpell(spell_id=SpellIDs.SHINY_RING, count=1),
            DeathrattleAddSpell(spell_id=SpellIDs.SHINY_RING, count=1),
        ],
    ),
    CardDef(
        CardIDs.SPIKED_SAVIOR,
        "Spiked Savior",
        5,
        8,
        2,
        [UnitType.UNDEAD],
        tags={Tags.TAUNT, Tags.REBORN},
        deathrattle=True,
        effects=[DeathrattleGiveFriendliesScaling(buff_atk=1, buff_hp=1, self_damage=1)],
    ),
    CardDef(
        CardIDs.LEEROY_THE_RECKLESS,
        "Leeroy the Reckless",
        5,
        6,
        2,
        [],
        deathrattle=True,
        effects=[DeathrattleDestroyKiller()],
    ),
    CardDef(
        CardIDs.STUNTDRAKE,
        "Stuntdrake",
        5,
        14,
        5,
        [UnitType.DRAGON],
        effects=[
            AvengeEffect(
                threshold=3,
                buff_atk=14,
                buff_hp=5,
                buff_scope="perm",
                buff_target="random_friendly_type",
                target_type=UnitType.DRAGON,
            )
        ],
    ),
    CardDef(
        CardIDs.WINTERGRASP_GHOUL,
        "Wintergrasp Ghoul",
        5,
        5,
        3,
        [UnitType.UNDEAD],
        deathrattle=True,
        effects=[DeathrattleAddSpell(spell_id=SpellIDs.TOMB_TURNING, count=1)],
    ),
    CardDef(
        CardIDs.IRIDESCENT_SKYBLAZER,
        "Iridescent Skyblazer",
        5,
        3,
        7,
        [UnitType.DRAGON],
        effects=[OnFriendlyBeastDamagedBuffOther(atk=1, hp=1)],
    ),
    CardDef(
        CardIDs.NIUZAO,
        "Niuzao",
        5,
        7,
        6,
        [UnitType.BEAST],
        effects=[RallyDealDamageEqualToAtk()],
    ),
    CardDef(
        CardIDs.TWILIGHT_BROODMOTHER,
        "Twilight Broodmother",
        5,
        7,
        4,
        [UnitType.DRAGON],
        deathrattle=True,
        effects=[DeathrattleSummonTauntToken(token_id=CardIDs.TWILIGHT_WHELP, count=2)],
    ),
    CardDef(
        CardIDs.COSTUME_ENTHUSIAST,
        "Costume Enthusiast",
        5,
        4,
        5,
        [],
        tags={Tags.DIVINE_SHIELD},
        effects=[StartOfCombatBuffSelfByHighestAllyAtk()],
    ),
    CardDef(
        CardIDs.ELITE_NAVIGATOR,
        "Elite Navigator",
        5,
        5,
        5,
        [UnitType.PIRATE],
        effects=[BattlecryMakeGoldenFriendlyByTier(max_tier=4)],
    ),
    CardDef(
        CardIDs.COUSIN_ERRGL,
        "Cousin Errgl",
        5,
        5,
        5,
        [UnitType.MURLOC],
        effects=[
            # Official: At the end of your turn, get a Mama Mrrglton
            # or a Papa Mrrglton.
            EndOfTurnAddMrrglton()
        ],
    ),
    CardDef(
        CardIDs.DANCING_BARNSTORMER,
        "Dancing Barnstormer",
        5,
        4,
        4,
        [UnitType.ELEMENTAL],
        deathrattle=True,
        effects=[
            # Official (35.6): Battlecry and Deathrattle: Give Elementals
            # in the Tavern +8/+8 this game.
            BattlecryDeathrattleBuffTavernType(
                trigger_type=UnitType.ELEMENTAL, atk=8, hp=8
            )
        ],
    ),
    CardDef(
        CardIDs.DUAL_WIELD_CORSAIR,
        "Dual-Wield Corsair",
        5,
        4,
        5,
        [UnitType.PIRATE],
        effects=[
            SpendGoldBuffType(
                trigger_type=UnitType.PIRATE,
                gold_per=5,
                atk=4,
                hp=5,
                max_targets=2,
            )
        ],
    ),
    CardDef(
        CardIDs.KANGORS_APPRENTICE,
        "Kangor's Apprentice",
        5,
        3,
        6,
        [],
        deathrattle=True,
        effects=[DeathrattleSummonFirstDeadMechs(count=2)],
    ),
    CardDef(
        CardIDs.SCRAP_SCRAPER,
        "Scrap Scraper",
        5,
        6,
        5,
        [UnitType.MECH],
        deathrattle=True,
        effects=[DeathrattleAddRandomMagneticUnit()],
    ),
    CardDef(
        CardIDs.VIGILANT_BRISTLEMANE,
        "Vigilant Bristlemane",
        5,
        3,
        5,
        [UnitType.QUILBOAR],
        effects=[OnSpellCastRecastRandomTavernSpell()],
    ),
    CardDef(
        CardIDs.VOID_PUP_TRAINER,
        "Void Pup Trainer",
        5,
        7,
        7,
        [UnitType.DEMON],
        deathrattle=True,
        effects=[
            DeathrattleBuffFriendlyTypeScaling(
                trigger_type=UnitType.DEMON,
                atk=2,
                hp=2,
                per_tier_atk=1,
                per_tier_hp=1,
            )
        ],
    ),
    CardDef(
        CardIDs.DARKCREST_STRATEGIST,
        "Darkcrest Strategist",
        5,
        4,
        5,
        [UnitType.NAGA],
        effects=[OnSpellCastOnSelfBuffSelf(atk=1, hp=1)],
    ),
    CardDef(
        CardIDs.GLOWSCALE,
        "Glowscale",
        5,
        4,
        6,
        [UnitType.NAGA],
        tags={Tags.TAUNT},
        effects=[OnSpellCastOnSelfBuffSelf(atk=1, hp=1)],
    ),
    CardDef(
        CardIDs.SHOWY_CYCLIST,
        "Showy Cyclist",
        5,
        4,
        2,
        [UnitType.NAGA],
        deathrattle=True,
        # Official: Deathrattle: Give all your Naga +2/+1.
        # (Improved by every 3 spells you've cast this game! - TODO)
        effects=[
            DeathrattleBuffFriendlyType(
                trigger_type=UnitType.NAGA, atk=2, hp=1
            ),
        ],
    ),
    CardDef(
        CardIDs.TRANQUIL_MEDITATIVE,
        "Tranquil Meditative",
        5,
        3,
        8,
        [UnitType.NAGA],
        effects=[
            OnSpellCastOnSelfBuffSelf(atk=1, hp=1),
            OnSpellCastOnTypeBuffBoard(
                trigger_type=UnitType.NAGA, atk=1, hp=1
            ),
        ],
    ),
    # -----------------------------------------------------------------------
    # TIER 6
    # -----------------------------------------------------------------------
    CardDef(
        CardIDs.GOLDRINN_THE_GREAT_WOLF,
        "Goldrinn, the Great Wolf",
        6,
        8,
        8,
        [UnitType.BEAST],
        deathrattle=True,
        effects=[DeathrattleBuffAllFriendliesGlobal(trigger_type=UnitType.BEAST, atk=8, hp=8)],
    ),
    CardDef(
        CardIDs.CHARLGA,
        "Charlga",
        6,
        3,
        3,
        [UnitType.QUILBOAR],
        effects=[
            EndOfTurnBuffBoardByType(trigger_type=UnitType.ALL, atk=0, hp=0)
            # EoT plays 2 Blood Gems on all other minions — model as EndOfTurnAddSpell x2
        ],
    ),
    CardDef(
        CardIDs.SLITHERSPEAR_LORD_OF_GAINS,
        "Slitherspear, Lord of Gains",
        6,
        4,
        5,
        [UnitType.NAGA],
        effects=[EndOfTurnBuffFriendlyTypeNaga(atk=2, hp=1)],
    ),
    CardDef(
        CardIDs.LORD_OF_THE_RUINS,
        "Lord of the Ruins",
        6,
        5,
        6,
        [UnitType.DEMON],
        effects=[OnFriendlyDemonDamageBuff(atk=2, hp=1)],
    ),
    CardDef(
        CardIDs.FAMISHED_FELBAT,
        "Famished Felbat",
        6,
        9,
        5,
        [UnitType.DEMON],
        effects=[EndOfTurnConsumeTavernForDemon()],
    ),
    CardDef(
        CardIDs.SHIP_MASTER_EUDORA,
        "Ship Master Eudora",
        6,
        10,
        5,
        [UnitType.PIRATE],
        deathrattle=True,
        effects=[DeathrattleBuffAllFriendlies(atk=8, hp=8)],
    ),
    CardDef(
        CardIDs.AVALANCHE_CALLER,
        "Avalanche Caller",
        6,
        6,
        5,
        [UnitType.ELEMENTAL],
        effects=[EndOfTurnAddSpell(spell_id=SpellIDs.MOUNTING_AVALANCHE, count=1)],
    ),
    CardDef(
        CardIDs.ULTRAVIOLET_ASCENDANT,
        "Ultraviolet Ascendant",
        6,
        6,
        3,
        [UnitType.ELEMENTAL],
        effects=[
            StartOfCombatBuffFriendlyTypeScaling(trigger_type=UnitType.ELEMENTAL, atk=3, hp=2)
        ],
    ),
    CardDef(
        CardIDs.IGNITION_SPECIALIST,
        "Ignition Specialist",
        6,
        8,
        8,
        [],
        effects=[
            EndOfTurnAddRandomSpell(),
            EndOfTurnAddRandomSpell(),  # gets 2 random spells
        ],
    ),
    CardDef(
        CardIDs.FAUNA_WHISPERER,
        "Fauna Whisperer",
        6,
        4,
        9,
        [UnitType.BEAST],
        effects=[
            EndOfTurnBuffAdjacent(atk=3, hp=3)  # simplified: Natural Blessing on adjacent
        ],
    ),
    CardDef(
        CardIDs.YOUNG_MURK_EYE,
        "Young Murk-Eye",
        6,
        9,
        6,
        [UnitType.MURLOC],
        effects=[EndOfTurnTriggerAdjacentBattlecry()],
    ),
    CardDef(
        CardIDs.FIRE_FORGED_EVOKER,
        "Fire-forged Evoker",
        6,
        8,
        5,
        [UnitType.DRAGON],
        effects=[StartOfCombatBuffFriendlyType(trigger_type=UnitType.DRAGON, atk=2, hp=1)],
    ),
    CardDef(
        CardIDs.SANGUINE_REFINER,
        "Sanguine Refiner",
        6,
        3,
        10,
        [UnitType.QUILBOAR],
        effects=[
            # Rally: Blood Gems give extra +1/+1 — model as BattlecryModifyMechanic
            RallyBuff(use_blood_gem=True)
        ],
    ),
    CardDef(
        CardIDs.BLOODSNOUT_WARLORD,
        "Bloodsnout Warlord",
        6,
        5,
        5,
        [UnitType.QUILBOAR],
        effects=[
            # Whenever a friendly Rally minion attacks, plays 3 Blood Gems — simplified
            RallyBuffAllOthersByType(trigger_type=UnitType.ALL, count=3)
        ],
    ),
    CardDef(
        CardIDs.DEATHLY_STRIKER,
        "Deathly Striker",
        6,
        8,
        8,
        [UnitType.UNDEAD],
        deathrattle=True,
        effects=[
            AvengeEffect(
                threshold=4,
                buff_atk=0,
                buff_hp=0,
                buff_scope="perm",
                buff_target="add_unit",
                target_type=UnitType.UNDEAD,
            )
        ],
    ),
    CardDef(
        CardIDs.WHIRLING_LASS_O_MATIC,
        "Whirling Lass-o-Matic",
        6,
        6,
        3,
        [],
        tags={Tags.DIVINE_SHIELD, Tags.WINDFURY},
        effects=[
            RallyAddSpell(spell_id=SpellIDs.TRIPLET_REWARD, count=1)  # random tavern spell
        ],
    ),
    CardDef(
        CardIDs.ARCHAEDAS,
        "Archaedas",
        6,
        10,
        10,
        [],
        effects=[BattlecryAddRandomUnit(unit_type=None, tier=5)],
    ),
    CardDef(
        CardIDs.NIGHTMARE_PAR_TEA_GUEST,
        "Nightmare Par-tea Guest",
        6,
        6,
        6,
        [],
        deathrattle=True,
        effects=[
            BattlecryAddSpell(spell_id=SpellIDs.MISPLACED_TEA_SET, count=1),
            DeathrattleAddSpell(spell_id=SpellIDs.MISPLACED_TEA_SET, count=1),
        ],
    ),
    CardDef(
        CardIDs.SUNDERED_MATRIARCH,
        "Sundered Matriarch",
        6,
        7,
        4,
        [UnitType.DRAGON],
        effects=[OnSpellCastBuffBoard(atk=0, hp=2)],
    ),
    CardDef(
        CardIDs.PRIMITIVE_PAINTER,
        "Primitive Painter",
        6,
        3,
        8,
        [UnitType.MURLOC],
        effects=[
            # After playing a card from T3 or below, give Murlocs +1/+2 — simplified
            OnFriendlyPlayType(trigger_type=UnitType.MURLOC, atk=1, hp=2, exclude_self=False)
        ],
    ),
    CardDef(
        CardIDs.MOAT_CUSTODIAN,
        "Moat Custodian",
        6,
        5,
        10,
        [UnitType.ELEMENTAL],
        # Official: Rally: Your Elementals give an extra +2/+2 this game.
        effects=[
            RallyModifyMechanic(
                mechanic=MechanicType.ELEMENTAL_BUFF_BONUS, atk=2, hp=2
            )
        ],
    ),
    CardDef(
        CardIDs.UNLEASHED_MANA_SURGE,
        "Unleashed Mana Surge",
        6,
        6,
        9,
        [UnitType.ELEMENTAL],
        effects=[
            # Official (36.4.2, current): After you play an Elemental,
            # give your Elementals +2/+3.
            OnFriendlyPlayTypeBuffBoardTypeIncludeSelf(
                play_type=UnitType.ELEMENTAL,
                buff_type=UnitType.ELEMENTAL,
                atk=2,
                hp=3,
            )
        ],
    ),
    CardDef(
        CardIDs.WARPWING,
        "Warpwing",
        6,
        12,
        4,
        [UnitType.DRAGON],
        effects=[ImmuneWhileAttacking()],
    ),
    CardDef(
        CardIDs.GROUNDBREAKER,
        "Groundbreaker",
        6,
        6,
        4,
        [UnitType.NAGA],
        # Official: After you play a Naga, gain +2/+2.
        # (Improved by every 3 spells you've cast this game! - TODO)
        effects=[OnPlayNagaBuffSelf(atk=2, hp=2)],
    ),
    CardDef(
        CardIDs.TORRENTIAL_RUINER,
        "Torrential Ruiner",
        6,
        6,
        3,
        [UnitType.NAGA],
        # Official: Whenever you cast a spell on a Naga,
        # give your minions +2/+3.
        effects=[OnSpellCastOnNagaBuffBoard(atk=2, hp=3)],
    ),
    # -----------------------------------------------------------------------
    # TIER 7
    # -----------------------------------------------------------------------
    CardDef(
        CardIDs.SEA_WITCH_ZARJIRA,
        "Sea Witch Zar'jira",
        7,
        4,
        5,
        [UnitType.NAGA],
        effects=[
            OnFriendlyPlayTypeBuffSelfScaling(
                trigger_type=UnitType.NAGA, atk=1, hp=1
            )
        ],
    ),
    CardDef(
        CardIDs.CAPTAIN_SANDERS,
        "Captain Sanders",
        7,
        9,
        9,
        [UnitType.PIRATE],
        effects=[BattlecryMakeGoldenFriendlyByTier(max_tier=6)],
    ),
    CardDef(
        CardIDs.HIGHKEEPER_RA,
        "Highkeeper Ra",
        7,
        6,
        6,
        [],
        effects=[
            BattlecryAddRandomUnit(unit_type=None, tier=6),
            DeathrattleAddSpell(spell_id=SpellIDs.TRIPLET_REWARD, count=1),
        ],
    ),
    CardDef(
        CardIDs.THE_LAST_ONE_STANDING,
        "The Last One Standing",
        7,
        12,
        12,
        [],
        effects=[
            # Rally: give a friendly minion of each type +12/+12 — simplified as big rally buff
            RallyBuff(atk=12, hp=12)
        ],
    ),
    CardDef(
        CardIDs.SANGUINE_CHAMPION,
        "Sanguine Champion",
        7,
        18,
        3,
        [],
        effects=[
            BattlecryModifyMechanic(mechanic=MechanicType.BLOOD_GEM, atk=1, hp=1),
            DeathrattleModifyMechanic(mechanic=MechanicType.BLOOD_GEM, atk=1, hp=1),
        ],
    ),
    CardDef(
        CardIDs.PSYCHUS,
        "Psychus",
        7,
        1,
        1,
        [],
        effects=[StartOfCombatBuffSelfByHighestBoardAtk()],
    ),
    CardDef(
        CardIDs.OBSIDIAN_RAVAGER,
        "Obsidian Ravager",
        7,
        7,
        7,
        [],
        effects=[RallyDealDamageEqualToAtk()],
    ),
    CardDef(
        CardIDs.STITCHED_SALVAGER,
        "Stitched Salvager",
        7,
        16,
        4,
        [UnitType.UNDEAD],
        deathrattle=True,
        effects=[
            # SoC: Destroy left minion, DR: summon exact copy — complex; model as DR buff
            DeathrattleBuffAllFriendlies(atk=4, hp=4)
        ],
    ),
    CardDef(
        CardIDs.FUTUREFIN,
        "Futurefin",
        7,
        7,
        13,
        [UnitType.MURLOC],
        effects=[
            # EoT: give stats to left-most warband minion — model as EoT buff adjacent
            EndOfTurnBuffAdjacent(atk=7, hp=13)
        ],
    ),
    # -----------------------------------------------------------------------
    # TOKENS
    # -----------------------------------------------------------------------
    CardDef(
        CardIDs.MICROBOT,
        "Microbot",
        1,
        1,
        1,
        [UnitType.MECH],
        is_token=True,
    ),
    CardDef(
        CardIDs.SKELETON,
        "Skeleton",
        1,
        1,
        1,
        [UnitType.UNDEAD],
        is_token=True,
    ),
    CardDef(
        CardIDs.CUBLING,
        "Cubling",
        1,
        0,
        1,
        [UnitType.BEAST],
        tags={Tags.TAUNT},
        is_token=True,
    ),
    CardDef(
        CardIDs.TWILIGHT_WHELP,
        "Twilight Whelp",
        1,
        3,
        3,
        [UnitType.DRAGON],
        is_token=True,
    ),
    CardDef(
        CardIDs.CRAB_TOKEN,
        "Crab",
        1,
        3,
        2,
        [UnitType.BEAST],
        is_token=True,
    ),
    CardDef(
        CardIDs.TURTLE,
        "Turtle",
        2,
        2,
        3,
        [],
        tags={Tags.TAUNT},
        is_token=True,
    ),
    CardDef(
        CardIDs.WATER_DROPLET,
        "Water Droplet",
        2,
        3,
        3,
        [UnitType.ELEMENTAL],
        is_token=True,
    ),
    CardDef(
        CardIDs.HAND_TOKEN,
        "Hand",
        1,
        2,
        1,
        [UnitType.UNDEAD],
        is_token=True,
    ),
    CardDef(
        CardIDs.GOLEM_TOKEN,
        "Golem",
        6,
        6,
        6,
        [],
        is_token=True,
    ),
]


# ---------------------------------------------------------------------------
# build_card_db  →  produces the same dict as the original hardcoded CARD_DB
# ---------------------------------------------------------------------------


def build_card_db() -> Dict[str, Any]:
    db: Dict[str, Any] = {}
    for card in ALL_CARDS:
        entry: Dict[str, Any] = {
            "name": card.name,
            "tier": card.tier,
            "atk": card.atk,
            "hp": card.hp,
            "type": card.types,
        }
        if card.tags:
            entry["tags"] = card.tags
        if card.is_token:
            entry["is_token"] = True
        if card.deathrattle:
            entry["deathrattle"] = True
        if card.avenge_threshold > 0:
            entry["avenge_threshold"] = card.avenge_threshold
        db[card.card_id] = entry
    return db


# ---------------------------------------------------------------------------
# Effect factory functions
# ---------------------------------------------------------------------------


def _make_dr_summon(token_id: str, count: int):
    """Deathrattle: summon `count` copies of `token_id` at the dead unit's slot."""

    def _effect(ctx: EffectContext, event: Event, _trigger_uid: int) -> None:
        pos = event.source_pos or (event.snapshot.pos if event.snapshot else None)
        if pos:
            for _ in range(count):
                ctx.summon(pos.side, token_id, pos.slot)

    return _effect


def _make_dr_summon_with_tag(token_id: str, count: int, tag: Tags):
    """Deathrattle: summon `count` copies of `token_id`, each with an extra tag."""

    def _effect(ctx: EffectContext, event: Event, _trigger_uid: int) -> None:
        pos = event.source_pos or (event.snapshot.pos if event.snapshot else None)
        if not pos:
            return
        for _ in range(count):
            ref = ctx.summon(pos.side, token_id, pos.slot)
            if ref:
                unit = ctx.resolve_unit(ref)
                if unit:
                    unit.tags.add(tag)

    return _effect


def _make_battlecry_summon_at_right(token_id: str):
    """Battlecry: summon a token immediately to the right of self."""

    def _effect(ctx: EffectContext, _event: Event, trigger_uid: int) -> None:
        es = _event_system()
        pos = ctx.resolve_pos(es.EntityRef(trigger_uid))
        if not pos:
            return
        ctx.summon(pos.side, token_id, pos.slot + 1)

    return _effect


def _make_battlecry_gain_gold(amount: int):
    """Battlecry: gain gold immediately."""

    def _effect(ctx: EffectContext, _event: Event, trigger_uid: int) -> None:
        es = _event_system()
        pos = ctx.resolve_pos(es.EntityRef(trigger_uid))
        if not pos:
            return
        ctx.gain_gold(pos.side, amount)

    return _effect


def _make_battlecry_add_spell(spell_id: str, count: int):
    """Battlecry: add spell(s) to hand."""

    def _effect(ctx: EffectContext, _event: Event, trigger_uid: int) -> None:
        es = _event_system()
        pos = ctx.resolve_pos(es.EntityRef(trigger_uid))
        if not pos:
            return
        for _ in range(count):
            ctx.add_spell_to_hand(pos.side, spell_id)

    return _effect


def _make_battlecry_spell_discount(amount: int):
    """Battlecry: next tavern spell costs `amount` less."""

    def _effect(ctx: EffectContext, _event: Event, trigger_uid: int) -> None:
        es = _event_system()
        pos = ctx.resolve_pos(es.EntityRef(trigger_uid))
        if not pos:
            return
        player = ctx.players_by_uid.get(pos.side)
        if not player:
            return
        player.spell_discount += amount

    return _effect


def _make_battlecry_modify_mechanic(mechanic: MechanicType, atk: int, hp: int):
    """Battlecry: modify a global mechanic stat (Dune Dweller)."""

    def _effect(ctx: EffectContext, _event: Event, trigger_uid: int) -> None:
        es = _event_system()
        pos = ctx.resolve_pos(es.EntityRef(trigger_uid))
        if not pos:
            return
        player = ctx.players_by_uid.get(pos.side)
        if not player:
            return
        player.mechanics.modify_stat(mechanic, atk, hp)

    return _effect


def _make_battlecry_consume_shop_unit():
    """Battlecry: consume random shop unit, gain its stats."""

    def _effect(ctx: EffectContext, _event: Event, trigger_uid: int) -> None:
        es = _event_system()
        pos = ctx.resolve_pos(es.EntityRef(trigger_uid))
        if not pos:
            return
        result = ctx.consume_random_store_unit(pos.side)
        if result:
            atk, hp = result
            ctx.buff_perm(es.EntityRef(trigger_uid), atk, hp)

    return _effect


def _make_sell_add_spell(spell_id: str, count: int):
    """On sell: add spell(s) to hand."""

    def _effect(ctx: EffectContext, _event: Event, trigger_uid: int) -> None:
        es = _event_system()
        pos = ctx.resolve_pos(es.EntityRef(trigger_uid))
        if not pos:
            return
        for _ in range(count):
            ctx.add_spell_to_hand(pos.side, spell_id)

    return _effect


def _make_battlecry_make_golden():
    """Battlecry: make this minion golden."""

    def _effect(ctx: EffectContext, _event: Event, trigger_uid: int) -> None:
        es = _event_system()
        ctx.make_golden(es.EntityRef(trigger_uid))

    return _effect


def _make_sell_for_gold(amount: int):
    """On sell: gain extra gold (total = amount instead of default 1)."""

    def _effect(ctx: EffectContext, _event: Event, trigger_uid: int) -> None:
        es = _event_system()
        pos = ctx.resolve_pos(es.EntityRef(trigger_uid))
        if not pos:
            return
        # Sell already gives 1 gold from tavern logic.
        # We give (amount - 1) extra to reach the target sell price.
        ctx.gain_gold(pos.side, amount - 1)

    return _effect


def _make_rally_buff(atk: int, hp: int, use_blood_gem: bool):
    """Rally: when this unit attacks, buff itself (combat scope)."""

    def _effect(ctx: EffectContext, _event: Event, trigger_uid: int) -> None:
        es = _event_system()
        if use_blood_gem:
            pos = ctx.resolve_pos(es.EntityRef(trigger_uid))
            if not pos:
                return
            player = ctx.players_by_uid.get(pos.side)
            if not player:
                return
            buff_atk, buff_hp = player.mechanics.get_stat(MechanicType.BLOOD_GEM)
        else:
            buff_atk, buff_hp = atk, hp
        ctx.buff_combat(es.EntityRef(trigger_uid), buff_atk, buff_hp)

    return _effect


def _make_soc_from_hand():
    """Start of Combat: if this unit is in hand, summon a copy onto board."""

    def _effect(ctx: EffectContext, _event: Event, trigger_uid: int) -> None:
        es = _event_system()
        pos = ctx.resolve_pos(es.EntityRef(trigger_uid))
        if not pos or pos.zone != es.Zone.HAND:
            return
        unit = ctx.resolve_unit(es.EntityRef(trigger_uid))
        if not unit:
            return
        player = ctx.players_by_uid.get(pos.side)
        if not player or len(player.board) >= 7:
            return
        ctx.summon(pos.side, unit.card_id, len(player.board), unit.is_golden)

    return _effect


def _make_sell_get_random_unit(tier: int):
    """On sell: draw a random T{tier} unit from the shared pool into hand."""

    def _effect(ctx: EffectContext, _event: Event, trigger_uid: int) -> None:
        es = _event_system()
        pos = ctx.resolve_pos(es.EntityRef(trigger_uid))
        if not pos:
            return
        ctx.draw_from_pool(pos.side, tier=tier, count=1)

    return _effect


def _make_start_of_combat_buff_self_by_tier():
    """Start of Combat: gain +tavern_tier/+tavern_tier (Misfit Dragonling)."""

    def _effect(ctx: EffectContext, _event: Event, trigger_uid: int) -> None:
        es = _event_system()
        unit = ctx.resolve_unit(es.EntityRef(trigger_uid))
        if not unit or not unit.is_alive:
            return
        pos = ctx.resolve_pos(es.EntityRef(trigger_uid))
        if not pos:
            return
        player = ctx.players_by_uid.get(pos.side)
        if not player:
            return
        tier = player.tavern_tier
        ctx.buff_combat(es.EntityRef(trigger_uid), tier, tier)

    return _effect


def _make_on_friendly_death_buff(atk: int, hp: int):
    """On any friendly death (excl. self), gain +atk/+hp as combat buff (Rot Hide Gnoll)."""

    def _effect(ctx: EffectContext, _event: Event, trigger_uid: int) -> None:
        es = _event_system()
        gnoll = ctx.resolve_unit(es.EntityRef(trigger_uid))
        if not gnoll or not gnoll.is_alive:
            return
        ctx.buff_combat(es.EntityRef(trigger_uid), atk, hp)

    return _effect


def _make_on_play_type_buff(trigger_type: UnitType, atk: int, hp: int, exclude_self: bool):
    """On any friendly play of a unit of `trigger_type`, buff self."""

    def _effect(ctx: EffectContext, event: Event, trigger_uid: int) -> None:
        es = _event_system()
        played = ctx.resolve_unit(event.source)
        if not played or trigger_type not in played.types:
            return
        if exclude_self and event.source and event.source.uid == trigger_uid:
            return
        pos = ctx.resolve_pos(es.EntityRef(trigger_uid))
        if not pos:
            return
        ctx.buff_perm(es.EntityRef(trigger_uid), atk, hp)

    return _effect


def _make_on_play_type_damage_hero(
    trigger_type: UnitType, hero_dmg: int, atk: int, hp: int, exclude_self: bool
):
    """Wrath Weaver pattern: on play of demon (not self), damage own hero and buff self."""

    def _effect(ctx: EffectContext, event: Event, trigger_uid: int) -> None:
        es = _event_system()
        played = ctx.resolve_unit(event.source)
        if not played or trigger_type not in played.types:
            return
        if exclude_self and event.source and event.source.uid == trigger_uid:
            return

        weaver = ctx.resolve_unit(es.EntityRef(trigger_uid))
        if not weaver:
            return

        pos = ctx.resolve_pos(es.EntityRef(trigger_uid))
        if not pos:
            return

        ctx.damage_hero(pos.side, hero_dmg)
        ctx.buff_perm(es.EntityRef(weaver.uid), atk, hp)

    return _effect


def _make_dr_buff_all_friendlies(atk: int, hp: int):
    """Deathrattle: buff all friendly minions (combat buff)."""

    def _effect(ctx: EffectContext, event: Event, _trigger_uid: int) -> None:
        es = _event_system()
        pos = event.source_pos or (event.snapshot.pos if event.snapshot else None)
        if not pos:
            return
        player = ctx.players_by_uid.get(pos.side)
        if not player:
            return
        for unit in player.board:
            ctx.buff_combat(es.EntityRef(unit.uid), atk, hp)

    return _effect


def _make_dr_random_enemy_damage(damage: int):
    """Deathrattle: deal `damage` to a random enemy minion."""

    def _effect(ctx: EffectContext, event: Event, trigger_uid: int) -> None:
        es = _event_system()
        source_pos = event.source_pos or (event.snapshot.pos if event.snapshot else None)
        if not source_pos:
            return

        enemy_side = 1 - source_pos.side
        enemy_player = ctx.players_by_uid.get(enemy_side)

        if not enemy_player or not enemy_player.board:
            return

        target = random.choice(enemy_player.board)

        if target.has_divine_shield:
            target.tags.discard(Tags.DIVINE_SHIELD)
            ctx.emit_event(
                es.Event(
                    event_type=es.EventType.DIVINE_SHIELD_LOST,
                    source=es.EntityRef(target.uid),
                    source_pos=es.PosRef(side=enemy_side, zone=es.Zone.BOARD, slot=-1),
                )
            )
        else:
            target.cur_hp -= damage
            ctx.emit_event(
                es.Event(
                    event_type=es.EventType.MINION_DAMAGED,
                    source=es.EntityRef(trigger_uid),
                    target=es.EntityRef(target.uid),
                    value=damage,
                )
            )

    return _effect


def _make_on_friendly_summoned_type_buff(
    trigger_type: UnitType,
    atk: int,
    hp: int,
    exclude_self: bool,
    combat_buff: bool,
    gain_divine_shield: bool,
):
    """Deflect-o-Bot pattern: on friendly mech summoned (not self),
    buff self and optionally grant divine shield."""

    def _effect(ctx: EffectContext, event: Event, trigger_uid: int) -> None:
        es = _event_system()
        summoned_unit = ctx.resolve_unit(event.source)
        if not summoned_unit:
            return
        if trigger_type not in summoned_unit.types:
            return
        if exclude_self and summoned_unit.uid == trigger_uid:
            return
        deflecto = ctx.resolve_unit(es.EntityRef(trigger_uid))
        if not deflecto or not deflecto.is_alive:
            return
        if combat_buff:
            ctx.buff_combat(es.EntityRef(trigger_uid), atk, hp)
        else:
            ctx.buff_perm(es.EntityRef(trigger_uid), atk, hp)
        if gain_divine_shield:
            deflecto.tags.add(Tags.DIVINE_SHIELD)

    return _effect


def _make_deflect_o_bot_condition():
    """Condition: a friendly unit was summoned by someone else on the same side."""

    def _condition(ctx: EffectContext, event: Event, uid: int) -> bool:
        es = _event_system()
        return bool(
            event.source_pos
            and ctx.resolve_pos(es.EntityRef(uid))
            and event.source_pos.side == ctx.resolve_pos(es.EntityRef(uid)).side  # type: ignore
            and event.source
            and event.source.uid != uid
        )

    return _condition


def _make_end_of_turn_add_spell(spell_id: str, count: int):
    """End of turn: add spell(s) to hand (unit must be on board)."""

    def _effect(ctx: EffectContext, _event: Event, trigger_uid: int) -> None:
        es = _event_system()
        pos = ctx.resolve_pos(es.EntityRef(trigger_uid))
        if not pos:
            return
        for _ in range(count):
            ctx.add_spell_to_hand(pos.side, spell_id)

    return _effect


def _make_eot_buff_adjacent(atk: int, hp: int):
    """End of turn: buff adjacent units (perm buff)."""

    def _effect(ctx: EffectContext, _event: Event, trigger_uid: int) -> None:
        es = _event_system()
        pos = ctx.resolve_pos(es.EntityRef(trigger_uid))
        if not pos:
            return
        for _slot, unit in ctx.get_adjacent(pos.side, trigger_uid):
            ctx.buff_perm(es.EntityRef(unit.uid), atk, hp)

    return _effect


def _make_eot_buff_self(atk: int, hp: int):
    """End of turn: buff self (perm buff)."""

    def _effect(ctx: EffectContext, _event: Event, trigger_uid: int) -> None:
        es = _event_system()
        pos = ctx.resolve_pos(es.EntityRef(trigger_uid))
        if not pos:
            return
        ctx.buff_perm(es.EntityRef(trigger_uid), atk, hp)

    return _effect


def _make_eot_buff_board(atk: int, hp: int):
    """End of turn: buff all friendly board units (perm buff)."""

    def _effect(ctx: EffectContext, _event: Event, trigger_uid: int) -> None:
        es = _event_system()
        pos = ctx.resolve_pos(es.EntityRef(trigger_uid))
        if not pos:
            return
        for _slot, unit in ctx.iter_board_units(pos.side):
            ctx.buff_perm(es.EntityRef(unit.uid), atk, hp)

    return _effect


def _make_eot_buff_board_by_type(trigger_type: UnitType, atk: int, hp: int):
    """End of turn: buff all friendly board units of a type (perm buff)."""

    def _effect(ctx: EffectContext, _event: Event, trigger_uid: int) -> None:
        es = _event_system()
        pos = ctx.resolve_pos(es.EntityRef(trigger_uid))
        if not pos:
            return
        for _slot, unit in ctx.iter_board_units(pos.side):
            if trigger_type in unit.types:
                ctx.buff_perm(es.EntityRef(unit.uid), atk, hp)

    return _effect


def _make_soc_buff_friendly_type(trigger_type: UnitType, atk: int, hp: int):
    """SoC: give all friendly units of matching type +atk/+hp as combat buff."""

    def _effect(ctx: EffectContext, _event: Event, trigger_uid: int) -> None:
        es = _event_system()
        pos = ctx.resolve_pos(es.EntityRef(trigger_uid))
        if not pos:
            return
        for _slot, unit in ctx.iter_board_units(pos.side):
            if trigger_type in unit.types:
                ctx.buff_combat(es.EntityRef(unit.uid), atk, hp)

    return _effect


def _make_bc_buff_all_by_type(trigger_type: UnitType, atk: int, hp: int):
    """BC: give all friendly units of matching type +atk/+hp as perm buff."""

    def _effect(ctx: EffectContext, _event: Event, trigger_uid: int) -> None:
        es = _event_system()
        pos = ctx.resolve_pos(es.EntityRef(trigger_uid))
        if not pos:
            return
        for _slot, unit in ctx.iter_board_units(pos.side):
            if trigger_type in unit.types:
                ctx.buff_perm(es.EntityRef(unit.uid), atk, hp)

    return _effect


def _make_on_play_type_add_spell(
    trigger_type: UnitType, spell_id: str, count: int, exclude_self: bool
):
    """On any friendly play of a unit of trigger_type, add spell to hand."""

    def _effect(ctx: EffectContext, event: Event, trigger_uid: int) -> None:
        es = _event_system()
        played = ctx.resolve_unit(event.source)
        if not played or trigger_type not in played.types:
            return
        if exclude_self and event.source and event.source.uid == trigger_uid:
            return
        pos = ctx.resolve_pos(es.EntityRef(trigger_uid))
        if not pos:
            return
        for _ in range(count):
            ctx.add_spell_to_hand(pos.side, spell_id)

    return _effect


def _make_on_summoned_buff_random_other(trigger_type: UnitType, atk: int, hp: int):
    """When friendly of trigger_type is summoned, buff a random OTHER friendly of that type."""

    def _effect(ctx: EffectContext, event: Event, trigger_uid: int) -> None:
        es = _event_system()
        summoned = ctx.resolve_unit(event.source)
        if not summoned or trigger_type not in summoned.types:
            return
        # Determine side of the summoned unit
        source_pos = event.source_pos
        if not source_pos:
            return
        # Collect all other friendly units of matching type on the same board
        candidates = [
            unit
            for _slot, unit in ctx.iter_board_units(source_pos.side)
            if trigger_type in unit.types and unit.uid != summoned.uid
        ]
        if not candidates:
            return
        target = random.choice(candidates)
        ctx.buff_perm(es.EntityRef(target.uid), atk, hp)

    return _effect


def _make_sell_add_unit_v2(card_id: str):
    """On sell: add a specific unit to hand, resolving side via source_pos."""

    def _effect(ctx: EffectContext, event: Event, trigger_uid: int) -> None:
        if event.source_pos:
            side = event.source_pos.side
        else:
            side = next(iter(ctx.players_by_uid), None)
            if side is None:
                return
        ctx.add_unit_to_hand(side, card_id)

    return _effect


def _make_rally_buff_random_type(trigger_type: UnitType, atk: int, hp: int):
    """Rally: when this unit attacks, buff a random OTHER friendly of trigger_type (combat buff)."""

    def _effect(ctx: EffectContext, _event: Event, trigger_uid: int) -> None:
        es = _event_system()
        pos = ctx.resolve_pos(es.EntityRef(trigger_uid))
        if not pos:
            return
        candidates = [
            unit
            for _slot, unit in ctx.iter_board_units(pos.side)
            if trigger_type in unit.types and unit.uid != trigger_uid
        ]
        if not candidates:
            return
        target = random.choice(candidates)
        ctx.buff_combat(es.EntityRef(target.uid), atk, hp)

    return _effect


def _make_sell_get_random_by_type(unit_type: UnitType):
    """On sell: get a random unit of specific type from pool into hand."""

    def _effect(ctx: EffectContext, event: Event, trigger_uid: int) -> None:
        from .configs import CARD_DB

        if event.source_pos:
            side = event.source_pos.side
        else:
            side = next(iter(ctx.players_by_uid), None)
            if side is None:
                return
        if not ctx.card_pool:
            return
        player = ctx.players_by_uid.get(side)
        if not player or len(player.hand) >= 10:
            return
        # Collect all candidates from pool tiers matching the type
        candidates: list[str] = []
        for tier_cards in ctx.card_pool.tiers.values():
            for cid in tier_cards:
                data = CARD_DB.get(cid)
                if data and unit_type in data.get("type", []):
                    candidates.append(cid)
        if not candidates:
            return
        chosen = random.choice(candidates)
        # Remove from pool
        for tier_cards in ctx.card_pool.tiers.values():
            if chosen in tier_cards:
                tier_cards.remove(chosen)
                break
        from .entities import HandCard, Unit

        uid = ctx._uid_provider()
        new_unit = Unit.create_from_db(chosen, uid, side)
        player.hand.append(HandCard(uid=uid, unit=new_unit))

    return _effect


def _make_consume_for_random_friendly(trigger_type: UnitType):
    """BC: consume a random shop unit, give its stats to a random friendly of trigger_type."""

    def _effect(ctx: EffectContext, _event: Event, trigger_uid: int) -> None:
        es = _event_system()
        pos = ctx.resolve_pos(es.EntityRef(trigger_uid))
        if not pos:
            return
        result = ctx.consume_random_store_unit(pos.side)
        if not result:
            return
        gained_atk, gained_hp = result
        candidates = [
            unit for _slot, unit in ctx.iter_board_units(pos.side) if trigger_type in unit.types
        ]
        if not candidates:
            return
        target = random.choice(candidates)
        ctx.buff_perm(es.EntityRef(target.uid), gained_atk, gained_hp)

    return _effect


def _make_on_tavern_refresh_buff_rightmost_shop(
    atk: int, hp: int, give_reborn: bool, use_blood_gem: bool
):
    """After tavern refreshed: buff rightmost shop minion."""

    def _effect(ctx: EffectContext, event: Event, trigger_uid: int) -> None:
        es = _event_system()
        # Identify the player's side from the event or the unit's position
        source_pos = event.source_pos
        if source_pos:
            side = source_pos.side
        else:
            pos = ctx.resolve_pos(es.EntityRef(trigger_uid))
            if not pos:
                return
            side = pos.side
        store_units = ctx.iter_store_units(side)
        if not store_units:
            return
        # rightmost = highest slot index
        _slot, target = store_units[-1]
        if use_blood_gem:
            player = ctx.players_by_uid.get(side)
            if not player:
                return
            from .enums import MechanicType

            buff_atk, buff_hp = player.mechanics.get_stat(MechanicType.BLOOD_GEM)
            ctx.buff_perm(es.EntityRef(target.uid), buff_atk, buff_hp)
            ctx.buff_perm(es.EntityRef(target.uid), buff_atk, buff_hp)  # plays 2 blood gems
        else:
            ctx.buff_perm(es.EntityRef(target.uid), atk, hp)
        if give_reborn:
            target.tags.add(Tags.REBORN)

    return _effect


def _make_on_tavern_refresh_buff_rightmost_shop_condition():
    """Condition: the refreshed player is the one with this unit on board."""

    def _condition(ctx: EffectContext, event: Event, trigger_uid: int) -> bool:
        es = _event_system()
        pos = ctx.resolve_pos(es.EntityRef(trigger_uid))
        if not pos:
            return False
        source_pos = event.source_pos
        if not source_pos:
            return False
        return pos.side == source_pos.side

    return _condition


def _make_sell_buff_board_scaling(scaling_key: str, atk_per: int, hp_per: int):
    """On sell: buff board by (base + scaling * count) and increment counter."""

    def _effect(ctx: EffectContext, event: Event, trigger_uid: int) -> None:
        if event.source_pos:
            side = event.source_pos.side
        else:
            side = next(iter(ctx.players_by_uid), None)
            if side is None:
                return
        player = ctx.players_by_uid.get(side)
        if not player:
            return
        count = player.mechanics.get_scaling(scaling_key)
        buff_atk = atk_per * (count + 1)
        buff_hp = hp_per * (count + 1)
        player.mechanics.increment_scaling(scaling_key)
        es = _event_system()
        for _slot, unit in ctx.iter_board_units(side):
            ctx.buff_perm(es.EntityRef(unit.uid), buff_atk, buff_hp)

    return _effect


def _make_soc_damage_and_buff_adjacent(damage: int, atk: int, hp: int):
    """SoC: deal damage to adjacent units and buff their ATK."""

    def _effect(ctx: EffectContext, _event: Event, trigger_uid: int) -> None:
        es = _event_system()
        pos = ctx.resolve_pos(es.EntityRef(trigger_uid))
        if not pos:
            return
        for _slot, unit in ctx.get_adjacent(pos.side, trigger_uid):
            unit.cur_hp -= damage
            ctx.buff_combat(es.EntityRef(unit.uid), atk, hp)

    return _effect


def _make_on_hero_damaged_heal_and_buff_self(hp: int):
    """After hero takes damage: undo damage, buff self +hp."""

    def _effect(ctx: EffectContext, event: Event, trigger_uid: int) -> None:
        es = _event_system()
        # Determine which side took damage
        source_pos = event.source_pos
        if not source_pos:
            return
        damaged_side = source_pos.side
        # Only fire if the unit is on the same side as the hero that took damage
        unit_pos = ctx.resolve_pos(es.EntityRef(trigger_uid))
        if not unit_pos or unit_pos.side != damaged_side:
            return
        unit = ctx.resolve_unit(es.EntityRef(trigger_uid))
        if not unit or not unit.is_alive:
            return
        # Heal the hero by the damage value
        damage_amount = event.value or 0
        ctx.heal_hero(damaged_side, damage_amount)
        # Buff self
        ctx.buff_perm(es.EntityRef(trigger_uid), 0, hp)

    return _effect


def _make_eot_buff_adjacent_per_golden(atk: int, hp: int):
    """EOT: buff adjacent +atk/+hp, once per friendly golden minion (minimum 1)."""

    def _effect(ctx: EffectContext, _event: Event, trigger_uid: int) -> None:
        es = _event_system()
        pos = ctx.resolve_pos(es.EntityRef(trigger_uid))
        if not pos:
            return
        player = ctx.players_by_uid.get(pos.side)
        if not player:
            return
        # Count golden minions on board
        golden_count = sum(1 for u in player.board if u.is_golden)
        repeats = max(1, golden_count)
        for _slot, unit in ctx.get_adjacent(pos.side, trigger_uid):
            for _ in range(repeats):
                ctx.buff_perm(es.EntityRef(unit.uid), atk, hp)

    return _effect


def _make_sell_discover(base_tier: int, scaling_key: str):
    """On sell: discover a minion of tier (base_tier + scaling_counter)."""

    def _effect(ctx: EffectContext, event: Event, trigger_uid: int) -> None:
        if event.source_pos:
            side = event.source_pos.side
        else:
            side = next(iter(ctx.players_by_uid), None)
            if side is None:
                return
        player = ctx.players_by_uid.get(side)
        if not player or not ctx.card_pool:
            return
        count = player.mechanics.get_scaling(scaling_key) if scaling_key else 0
        player.mechanics.increment_scaling(scaling_key) if scaling_key else None
        discover_tier = min(6, base_tier + count)
        # Set a pending discovery request on the player
        from .entities import DiscoveryRequest

        player.pending_discovery_request = DiscoveryRequest(
            tier=discover_tier,
            exact_tier=False,
            source="Patient Scout",
        )

    return _effect


def _make_dr_add_spell(spell_id: str, count: int):
    """Deathrattle: add spell(s) to hand."""

    def _effect(ctx: EffectContext, event: Event, _trigger_uid: int) -> None:
        es = _event_system()
        pos = event.source_pos or (event.snapshot.pos if event.snapshot else None)
        if not pos:
            return
        for _ in range(count):
            ctx.add_spell_to_hand(pos.side, spell_id)

    return _effect


def _make_rally_add_spell(spell_id: str, count: int):
    """Rally: when this unit attacks, add spell(s) to hand."""

    def _effect(ctx: EffectContext, _event: Event, trigger_uid: int) -> None:
        es = _event_system()
        pos = ctx.resolve_pos(es.EntityRef(trigger_uid))
        if not pos:
            return
        for _ in range(count):
            ctx.add_spell_to_hand(pos.side, spell_id)

    return _effect


def _make_eot_buff_self_per_golden(atk_per: int, hp_per: int):
    """EOT: buff self +atk_per/+hp_per for each friendly golden minion."""

    def _effect(ctx: EffectContext, _event: Event, trigger_uid: int) -> None:
        es = _event_system()
        pos = ctx.resolve_pos(es.EntityRef(trigger_uid))
        if not pos:
            return
        player = ctx.players_by_uid.get(pos.side)
        if not player:
            return
        golden_count = sum(1 for u in player.board if u.is_golden)
        if golden_count == 0:
            return
        ctx.buff_perm(es.EntityRef(trigger_uid), atk_per * golden_count, hp_per * golden_count)

    return _effect


def _make_on_divine_shield_lost_add_spell(spell_id: str, count: int):
    """After a friendly minion loses Divine Shield, add spell to hand."""

    def _effect(ctx: EffectContext, event: Event, trigger_uid: int) -> None:
        es = _event_system()
        # Check that the shield-losing unit is on the same side
        unit_pos = ctx.resolve_pos(es.EntityRef(trigger_uid))
        if not unit_pos:
            return
        source_pos = event.source_pos
        if not source_pos or source_pos.side != unit_pos.side:
            return
        for _ in range(count):
            ctx.add_spell_to_hand(unit_pos.side, spell_id)

    return _effect


def _make_bc_buff_all_by_type_include_hand(trigger_type: UnitType, atk: int, hp: int):
    """BC: give all OTHER friendly units of type in hand AND board +atk/+hp."""

    def _effect(ctx: EffectContext, _event: Event, trigger_uid: int) -> None:
        es = _event_system()
        pos = ctx.resolve_pos(es.EntityRef(trigger_uid))
        if not pos:
            return
        player = ctx.players_by_uid.get(pos.side)
        if not player:
            return
        targets = []
        for _slot, unit in ctx.iter_board_units(pos.side):
            if trigger_type in unit.types and unit.uid != trigger_uid:
                targets.append(unit)
        for hc in player.hand:
            if hc.unit and trigger_type in hc.unit.types and hc.unit.uid != trigger_uid:
                targets.append(hc.unit)
        for unit in targets:
            ctx.buff_perm(es.EntityRef(unit.uid), atk, hp)

    return _effect


def _make_rally_damage_own_board(damage: int):
    """Rally: deal damage to all other friendly minions."""

    def _effect(ctx: EffectContext, _event: Event, trigger_uid: int) -> None:
        es = _event_system()
        pos = ctx.resolve_pos(es.EntityRef(trigger_uid))
        if not pos:
            return
        for _slot, unit in ctx.iter_board_units(pos.side):
            if unit.uid != trigger_uid:
                unit.cur_hp -= damage

    return _effect


def _make_dr_modify_mechanic(mechanic: MechanicType, atk: int, hp: int):
    """Deathrattle: permanently modify a global mechanic stat."""

    def _effect(ctx: EffectContext, event: Event, _trigger_uid: int) -> None:
        pos = event.source_pos or (event.snapshot.pos if event.snapshot else None)
        if not pos:
            return
        player = ctx.players_by_uid.get(pos.side)
        if not player:
            return
        player.mechanics.modify_stat(mechanic, atk, hp)

    return _effect


def _make_soc_buff_random_friendly_type_and_ds(trigger_type: UnitType, atk: int, hp: int):
    """SoC: give another friendly unit of type +atk/+hp and Divine Shield."""

    def _effect(ctx: EffectContext, _event: Event, trigger_uid: int) -> None:
        es = _event_system()
        pos = ctx.resolve_pos(es.EntityRef(trigger_uid))
        if not pos:
            return
        candidates = [
            unit
            for _slot, unit in ctx.iter_board_units(pos.side)
            if trigger_type in unit.types and unit.uid != trigger_uid
        ]
        if not candidates:
            return
        target = random.choice(candidates)
        ctx.buff_combat(es.EntityRef(target.uid), atk, hp)
        target.tags.add(Tags.DIVINE_SHIELD)

    return _effect


def _make_on_self_damaged_buff_board(atk: int, hp: int):
    """When this minion takes damage, buff all other friendly minions."""

    def _effect(ctx: EffectContext, event: Event, trigger_uid: int) -> None:
        es = _event_system()
        # Check target is self
        if not event.target or event.target.uid != trigger_uid:
            return
        unit = ctx.resolve_unit(es.EntityRef(trigger_uid))
        if not unit or not unit.is_alive:
            return
        pos = ctx.resolve_pos(es.EntityRef(trigger_uid))
        if not pos:
            return
        for _slot, other in ctx.iter_board_units(pos.side):
            if other.uid != trigger_uid:
                ctx.buff_perm(es.EntityRef(other.uid), atk, hp)

    return _effect


def _make_felemental_bc():
    """BC: give all tavern minions +2/+1 this game (modifies ELEMENTAL_BUFF mechanic for shop buffing)."""

    def _effect(ctx: EffectContext, _event: Event, trigger_uid: int) -> None:
        es = _event_system()
        pos = ctx.resolve_pos(es.EntityRef(trigger_uid))
        if not pos:
            return
        # Buff all current shop units
        for _slot, unit in ctx.iter_store_units(pos.side):
            ctx.buff_perm(es.EntityRef(unit.uid), 2, 1)
        # Also buff future shop units via mechanic (reuse ELEMENTAL_BUFF for tavern)
        player = ctx.players_by_uid.get(pos.side)
        if player:
            from .enums import MechanicType

            player.mechanics.modify_stat(MechanicType.ELEMENTAL_BUFF, 2, 1)

    return _effect


def _make_on_friendly_reborn_buff_self(atk: int, hp: int):
    """After a friendly minion triggers Reborn, buff self permanently."""

    def _effect(ctx: EffectContext, event: Event, trigger_uid: int) -> None:
        es = _event_system()
        unit_pos = ctx.resolve_pos(es.EntityRef(trigger_uid))
        if not unit_pos:
            return
        # MINION_SUMMONED with meta=1 means it was a Reborn summon
        if event.meta != 1:
            return
        source_pos = event.source_pos
        if not source_pos or source_pos.side != unit_pos.side:
            return
        # Don't buff self if it's this unit that rebore (though possible)
        unit = ctx.resolve_unit(es.EntityRef(trigger_uid))
        if not unit or not unit.is_alive:
            return
        ctx.buff_perm(es.EntityRef(trigger_uid), atk, hp)

    return _effect


def _make_dr_buff_friendly_type_global(trigger_type: UnitType, atk: int, hp: int):
    """Deathrattle: permanently buff all friendly units of type in hand + board."""

    def _effect(ctx: EffectContext, event: Event, _trigger_uid: int) -> None:
        es = _event_system()
        pos = event.source_pos or (event.snapshot.pos if event.snapshot else None)
        if not pos:
            return
        player = ctx.players_by_uid.get(pos.side)
        if not player:
            return
        for unit in player.board:
            if trigger_type in unit.types:
                ctx.buff_perm(es.EntityRef(unit.uid), atk, hp)
        for hc in player.hand:
            if hc.unit and trigger_type in hc.unit.types:
                ctx.buff_perm(es.EntityRef(hc.unit.uid), atk, hp)

    return _effect


def _make_dr_buff_shop(atk: int, hp: int):
    """Deathrattle: permanently buff all shop minions."""

    def _effect(ctx: EffectContext, event: Event, _trigger_uid: int) -> None:
        es = _event_system()
        pos = event.source_pos or (event.snapshot.pos if event.snapshot else None)
        if not pos:
            return
        for _slot, unit in ctx.iter_store_units(pos.side):
            ctx.buff_perm(es.EntityRef(unit.uid), atk, hp)
        # Also persist the buff for future shop minions via ELEMENTAL_BUFF mechanic (hp only)
        player = ctx.players_by_uid.get(pos.side)
        if player:
            player.mechanics.modify_stat(MechanicType.ELEMENTAL_BUFF, atk, hp)

    return _effect


def _make_dr_buff_hand_random(atk: int, hp: int):
    """Deathrattle: give a random minion in hand +atk/+hp."""

    def _effect(ctx: EffectContext, event: Event, _trigger_uid: int) -> None:
        es = _event_system()
        pos = event.source_pos or (event.snapshot.pos if event.snapshot else None)
        if not pos:
            return
        player = ctx.players_by_uid.get(pos.side)
        if not player:
            return
        candidates = [hc.unit for hc in player.hand if hc.unit is not None]
        if not candidates:
            return
        target = random.choice(candidates)
        ctx.buff_perm(es.EntityRef(target.uid), atk, hp)

    return _effect


def _make_on_friendly_attack_buff_attacker(trigger_type: UnitType, atk: int, hp: int):
    """When another friendly unit of type attacks, buff that attacker permanently."""

    def _effect(ctx: EffectContext, event: Event, trigger_uid: int) -> None:
        es = _event_system()
        attacker = ctx.resolve_unit(event.source)
        if not attacker or trigger_type not in attacker.types:
            return
        if attacker.uid == trigger_uid:
            return
        # Check same side
        pos = ctx.resolve_pos(es.EntityRef(trigger_uid))
        if not pos:
            return
        att_pos = ctx.resolve_pos(es.EntityRef(attacker.uid))
        if not att_pos or att_pos.side != pos.side:
            return
        ctx.buff_perm(es.EntityRef(attacker.uid), atk, hp)

    return _effect


def _make_on_friendly_attack_buff_trigger(trigger_type: UnitType, atk: int, hp: int):
    """When another friendly unit of type attacks, buff the TRIGGER unit (self) permanently."""

    def _effect(ctx: EffectContext, event: Event, trigger_uid: int) -> None:
        es = _event_system()
        attacker = ctx.resolve_unit(event.source)
        if not attacker or trigger_type not in attacker.types:
            return
        if attacker.uid == trigger_uid:
            return
        pos = ctx.resolve_pos(es.EntityRef(trigger_uid))
        if not pos:
            return
        att_pos = ctx.resolve_pos(es.EntityRef(attacker.uid))
        if not att_pos or att_pos.side != pos.side:
            return
        ctx.buff_perm(es.EntityRef(trigger_uid), atk, hp)

    return _effect


def _make_on_friendly_play_type_buff_self_in_hand(trigger_type: UnitType, atk: int, hp: int):
    """While in hand, when a friendly unit of type is played, buff self."""

    def _effect(ctx: EffectContext, event: Event, trigger_uid: int) -> None:
        es = _event_system()
        played = ctx.resolve_unit(event.source)
        if not played or trigger_type not in played.types:
            return
        # Find the trigger unit in the player's hand
        for side, player in ctx.players_by_uid.items():
            for hc in player.hand:
                if hc.unit and hc.unit.uid == trigger_uid:
                    # Must be the same side as played unit
                    src_pos = event.source_pos
                    if src_pos and src_pos.side == side:
                        ctx.buff_perm(es.EntityRef(trigger_uid), atk, hp)
                    return

    return _effect


def _make_on_spell_cast_buff_self(atk: int, hp: int):
    """When a tavern spell is played, buff self +atk/+hp."""

    def _effect(ctx: EffectContext, event: Event, trigger_uid: int) -> None:
        es = _event_system()
        pos = ctx.resolve_pos(es.EntityRef(trigger_uid))
        if not pos:
            return
        # SPELL_PLAYED event source_pos.side must match owner
        source_pos = event.source_pos
        if not source_pos or source_pos.side != pos.side:
            return
        unit = ctx.resolve_unit(es.EntityRef(trigger_uid))
        if not unit or not unit.is_alive:
            return
        ctx.buff_perm(es.EntityRef(trigger_uid), atk, hp)

    return _effect


def _make_on_gain_gold_buff_self(atk: int, hp: int):
    """After gaining gold (tavern coin played), buff self +atk/+hp."""

    def _effect(ctx: EffectContext, event: Event, trigger_uid: int) -> None:
        es = _event_system()
        pos = ctx.resolve_pos(es.EntityRef(trigger_uid))
        if not pos:
            return
        source_pos = event.source_pos
        if not source_pos or source_pos.side != pos.side:
            return
        unit = ctx.resolve_unit(es.EntityRef(trigger_uid))
        if not unit or not unit.is_alive:
            return
        ctx.buff_perm(es.EntityRef(trigger_uid), atk, hp)

    return _effect


def _make_dr_damage_all_minions(damage: int):
    """Deathrattle: deal damage to ALL minions on both sides."""

    def _effect(ctx: EffectContext, event: Event, trigger_uid: int) -> None:
        es = _event_system()
        pos = event.source_pos or (event.snapshot.pos if event.snapshot else None)
        if not pos:
            return
        for side in list(ctx.players_by_uid.keys()):
            player = ctx.players_by_uid.get(side)
            if not player:
                continue
            for unit in list(player.board):
                if unit.has_divine_shield:
                    unit.tags.discard(Tags.DIVINE_SHIELD)
                    ctx.emit_event(
                        es.Event(
                            event_type=es.EventType.DIVINE_SHIELD_LOST,
                            source=es.EntityRef(unit.uid),
                            source_pos=es.PosRef(side=side, zone=es.Zone.BOARD, slot=-1),
                        )
                    )
                else:
                    unit.cur_hp -= damage

    return _effect


def _make_soc_buff_all_friendly_type(trigger_type: UnitType, atk: int, hp: int):
    """SoC: permanently buff all friendly units of type +atk/+hp."""

    def _effect(ctx: EffectContext, _event: Event, trigger_uid: int) -> None:
        es = _event_system()
        pos = ctx.resolve_pos(es.EntityRef(trigger_uid))
        if not pos:
            return
        for _slot, unit in ctx.iter_board_units(pos.side):
            if trigger_type in unit.types:
                ctx.buff_perm(es.EntityRef(unit.uid), atk, hp)

    return _effect


def _make_soc_give_friendly_type_reborn(trigger_type: UnitType):
    """SoC: give a random friendly unit of type Reborn."""

    def _effect(ctx: EffectContext, _event: Event, trigger_uid: int) -> None:
        es = _event_system()
        pos = ctx.resolve_pos(es.EntityRef(trigger_uid))
        if not pos:
            return
        candidates = [
            unit
            for _slot, unit in ctx.iter_board_units(pos.side)
            if trigger_type in unit.types
            and unit.uid != trigger_uid
            and Tags.REBORN not in unit.tags
        ]
        if not candidates:
            return
        target = random.choice(candidates)
        target.tags.add(Tags.REBORN)

    return _effect


def _make_bc_add_random_unit(unit_type: Optional[UnitType], tier: Optional[int]):
    """BC: add a random unit of type (or tier) from pool to hand."""

    def _effect(ctx: EffectContext, _event: Event, trigger_uid: int) -> None:
        from .configs import CARD_DB

        es = _event_system()
        pos = ctx.resolve_pos(es.EntityRef(trigger_uid))
        if not pos:
            return
        player = ctx.players_by_uid.get(pos.side)
        if not player or not ctx.card_pool:
            return
        candidates: list[str] = []
        for t, tier_cards in ctx.card_pool.tiers.items():
            if tier is not None and t != tier:
                continue
            for cid in tier_cards:
                data = CARD_DB.get(cid)
                if data and data.get("is_token"):
                    continue
                if unit_type is not None and unit_type not in data.get("type", []):
                    continue
                candidates.append(cid)
        if not candidates:
            return
        chosen = random.choice(candidates)
        for tier_cards in ctx.card_pool.tiers.values():
            if chosen in tier_cards:
                tier_cards.remove(chosen)
                break
        from .entities import Unit, HandCard

        uid = ctx._uid_provider()
        new_unit = Unit.create_from_db(chosen, uid, pos.side)
        player.hand.append(HandCard(uid=uid, unit=new_unit))

    return _effect


def _make_bc_gain_free_refreshes(count: int):
    """BC: gain N free refreshes immediately."""

    def _effect(ctx: EffectContext, _event: Event, trigger_uid: int) -> None:
        es = _event_system()
        pos = ctx.resolve_pos(es.EntityRef(trigger_uid))
        if not pos:
            return
        player = ctx.players_by_uid.get(pos.side)
        if not player:
            return
        player.free_refreshes = getattr(player, "free_refreshes", 0) + count

    return _effect


def _make_on_ds_lost_buff_unit(atk: int, hp: int):
    """After a friendly minion loses Divine Shield, give it +atk/+hp permanently."""

    def _effect(ctx: EffectContext, event: Event, trigger_uid: int) -> None:
        es = _event_system()
        unit_pos = ctx.resolve_pos(es.EntityRef(trigger_uid))
        if not unit_pos:
            return
        source_pos = event.source_pos
        if not source_pos or source_pos.side != unit_pos.side:
            return
        # Buff the unit that lost the shield
        if event.source:
            ctx.buff_perm(event.source, atk, hp)

    return _effect


def _make_rally_buff_all_others_blood_gems(count: int):
    """Rally: play `count` blood gems on every other friendly minion."""

    def _effect(ctx: EffectContext, _event: Event, trigger_uid: int) -> None:
        es = _event_system()
        pos = ctx.resolve_pos(es.EntityRef(trigger_uid))
        if not pos:
            return
        player = ctx.players_by_uid.get(pos.side)
        if not player:
            return
        gem_atk, gem_hp = player.mechanics.get_stat(MechanicType.BLOOD_GEM)
        for _slot, unit in ctx.iter_board_units(pos.side):
            if unit.uid != trigger_uid:
                for _ in range(count):
                    ctx.buff_perm(es.EntityRef(unit.uid), gem_atk, gem_hp)

    return _effect


def _make_eot_add_random_spell():
    """End of turn: add a random tavern spell to hand."""

    def _effect(ctx: EffectContext, _event: Event, trigger_uid: int) -> None:
        from .configs import SPELL_DB

        es = _event_system()
        pos = ctx.resolve_pos(es.EntityRef(trigger_uid))
        if not pos:
            return
        pool_spells = [
            sid
            for sid, data in SPELL_DB.items()
            if data.get("pool", True) and sid != SpellIDs.TRIPLET_REWARD
        ]
        if not pool_spells:
            pool_spells = [SpellIDs.TAVERN_COIN]
        chosen = random.choice(pool_spells)
        ctx.add_spell_to_hand(pos.side, chosen)

    return _effect


def _make_avenge_add_spell(spell_id: str, count: int):
    """Avenge fires: add spell to hand (used for Spirit Drake, etc.)."""

    def _effect(ctx: EffectContext, _event: Event, trigger_uid: int) -> None:
        es = _event_system()
        pos = ctx.resolve_pos(es.EntityRef(trigger_uid))
        if not pos:
            return
        for _ in range(count):
            ctx.add_spell_to_hand(pos.side, spell_id)

    return _effect


def _make_avenge_add_random_unit():
    """Avenge fires: add a random battlecry unit to hand (Witchwing Nestmatron)."""

    def _effect(ctx: EffectContext, _event: Event, trigger_uid: int) -> None:
        from .configs import CARD_DB

        es = _event_system()
        pos = ctx.resolve_pos(es.EntityRef(trigger_uid))
        if not pos:
            return
        player = ctx.players_by_uid.get(pos.side)
        if not player or not ctx.card_pool:
            return
        candidates: list[str] = []
        for tier_cards in ctx.card_pool.tiers.values():
            for cid in tier_cards:
                data = CARD_DB.get(cid)
                if data and not data.get("is_token"):
                    candidates.append(cid)
        if not candidates:
            return
        chosen = random.choice(candidates)
        for tier_cards in ctx.card_pool.tiers.values():
            if chosen in tier_cards:
                tier_cards.remove(chosen)
                break
        from .entities import Unit, HandCard

        uid = ctx._uid_provider()
        new_unit = Unit.create_from_db(chosen, uid, pos.side)
        player.hand.append(HandCard(uid=uid, unit=new_unit))

    return _effect


# ---------------------------------------------------------------------------
# New factory functions for T4-T7 EffectDef types
# ---------------------------------------------------------------------------


def _make_on_spell_cast_buff_board(atk: int, hp: int, trigger_type: Optional[UnitType]):
    """When a spell is cast, buff all friendly minions (or of a type)."""

    def _effect(ctx: EffectContext, event: Event, trigger_uid: int) -> None:
        es = _event_system()
        unit_pos = ctx.resolve_pos(es.EntityRef(trigger_uid))
        if not unit_pos:
            return
        # Only fire for same-side spells
        source_pos = event.source_pos
        if source_pos and source_pos.side != unit_pos.side:
            return
        for _slot, unit in ctx.iter_board_units(unit_pos.side):
            if trigger_type is None or trigger_type in unit.types:
                ctx.buff_perm(es.EntityRef(unit.uid), atk, hp)

    return _effect


def _make_dr_summon_taunt_token(token_id: str, count: int):
    """Deathrattle: summon N tokens and give them Taunt."""

    def _effect(ctx: EffectContext, event: Event, _trigger_uid: int) -> None:
        pos = event.source_pos or (event.snapshot.pos if event.snapshot else None)
        if not pos:
            return
        for _ in range(count):
            ref = ctx.summon(pos.side, token_id, pos.slot)
            if ref:
                unit = ctx.resolve_unit(ref)
                if unit:
                    unit.tags.add(Tags.TAUNT)

    return _effect


def _make_soc_buff_self_by_highest_ally_atk():
    """SoC: set own attack to the highest friendly attack value."""

    def _effect(ctx: EffectContext, _event: Event, trigger_uid: int) -> None:
        es = _event_system()
        pos = ctx.resolve_pos(es.EntityRef(trigger_uid))
        if not pos:
            return
        max_atk = max(
            (
                unit.cur_atk
                for _slot, unit in ctx.iter_board_units(pos.side)
                if unit.uid != trigger_uid
            ),
            default=0,
        )
        if max_atk <= 0:
            return
        unit = ctx.resolve_unit(es.EntityRef(trigger_uid))
        if unit:
            ctx.buff_perm(es.EntityRef(trigger_uid), max_atk, 0)

    return _effect


def _make_soc_buff_self_by_highest_board_atk():
    """SoC: set own stats to match the highest-attack friendly minion."""

    def _effect(ctx: EffectContext, _event: Event, trigger_uid: int) -> None:
        es = _event_system()
        pos = ctx.resolve_pos(es.EntityRef(trigger_uid))
        if not pos:
            return
        best = max(
            (
                (unit.cur_atk, unit.cur_hp)
                for _slot, unit in ctx.iter_board_units(pos.side)
                if unit.uid != trigger_uid
            ),
            default=(0, 0),
        )
        if best[0] <= 0:
            return
        unit = ctx.resolve_unit(es.EntityRef(trigger_uid))
        if unit:
            gain_atk = max(0, best[0] - unit.cur_atk)
            gain_hp = max(0, best[1] - unit.cur_hp)
            ctx.buff_perm(es.EntityRef(trigger_uid), gain_atk, gain_hp)

    return _effect


def _make_bc_make_golden_friendly_by_tier(max_tier: int):
    """BC: make a random non-golden friendly minion from tier <= max_tier golden."""

    def _effect(ctx: EffectContext, _event: Event, trigger_uid: int) -> None:
        from .configs import CARD_DB

        es = _event_system()
        pos = ctx.resolve_pos(es.EntityRef(trigger_uid))
        if not pos:
            return
        candidates = [
            unit
            for _slot, unit in ctx.iter_board_units(pos.side)
            if unit.uid != trigger_uid
            and not unit.is_golden
            and CARD_DB.get(unit.card_id, {}).get("tier", 99) <= max_tier
        ]
        if not candidates:
            return
        target = random.choice(candidates)
        target.is_golden = True
        # Double stats for golden
        ctx.buff_perm(es.EntityRef(target.uid), target.cur_atk, target.cur_hp)

    return _effect


def _make_rally_buff_friendly_type_atk(trigger_type: UnitType, atk: int):
    """Rally: give all other friendly units of type +atk permanently."""

    def _effect(ctx: EffectContext, _event: Event, trigger_uid: int) -> None:
        es = _event_system()
        pos = ctx.resolve_pos(es.EntityRef(trigger_uid))
        if not pos:
            return
        for _slot, unit in ctx.iter_board_units(pos.side):
            if unit.uid != trigger_uid and trigger_type in unit.types:
                ctx.buff_perm(es.EntityRef(unit.uid), atk, 0)

    return _effect


def _make_on_friendly_beast_damaged_buff_self(hp: int):
    """When another friendly Beast takes damage, buff self +hp permanently."""

    def _effect(ctx: EffectContext, event: Event, trigger_uid: int) -> None:
        es = _event_system()
        # Determine who took damage
        if not event.target:
            return
        target = ctx.resolve_unit(event.target)
        if not target or UnitType.BEAST not in target.types:
            return
        if target.uid == trigger_uid:
            return
        unit_pos = ctx.resolve_pos(es.EntityRef(trigger_uid))
        if not unit_pos:
            return
        # Must be friendly
        target_pos = ctx.resolve_pos(event.target)
        if target_pos and target_pos.side != unit_pos.side:
            return
        ctx.buff_perm(es.EntityRef(trigger_uid), 0, hp)

    return _effect


def _make_on_friendly_beast_damaged_buff_other(atk: int, hp: int):
    """When a friendly Beast takes damage, give a different friendly Beast +atk/+hp."""

    def _effect(ctx: EffectContext, event: Event, trigger_uid: int) -> None:
        es = _event_system()
        if not event.target:
            return
        damaged = ctx.resolve_unit(event.target)
        if not damaged or UnitType.BEAST not in damaged.types:
            return
        unit_pos = ctx.resolve_pos(es.EntityRef(trigger_uid))
        if not unit_pos:
            return
        target_pos = ctx.resolve_pos(event.target)
        if target_pos and target_pos.side != unit_pos.side:
            return
        candidates = [
            unit
            for _slot, unit in ctx.iter_board_units(unit_pos.side)
            if unit.uid != damaged.uid and UnitType.BEAST in unit.types
        ]
        if not candidates:
            return
        target = random.choice(candidates)
        ctx.buff_perm(es.EntityRef(target.uid), atk, hp)

    return _effect


def _make_avenge_buff_friendly_type_global(
    threshold: int, trigger_type: UnitType, atk: int, hp: int
):
    """Avenge(N): give all friendly units of type +atk globally."""

    # NOTE: This is registered in AVENGE_REGISTRY and handled by avenge system
    # The avenge system calls this effect when threshold is met
    def _effect(ctx: EffectContext, _event: Event, trigger_uid: int) -> None:
        es = _event_system()
        pos = ctx.resolve_pos(es.EntityRef(trigger_uid))
        if not pos:
            return
        player = ctx.players_by_uid.get(pos.side)
        if not player:
            return
        for unit in player.board:
            if trigger_type in unit.types:
                ctx.buff_perm(es.EntityRef(unit.uid), atk, hp)
        for hc in player.hand:
            if hc.unit and trigger_type in hc.unit.types:
                ctx.buff_perm(es.EntityRef(hc.unit.uid), atk, hp)

    return _effect


def _make_dr_destroy_killer():
    """Deathrattle: destroy the minion that killed this."""

    def _effect(ctx: EffectContext, event: Event, _trigger_uid: int) -> None:
        # event.meta stores killer uid
        killer_uid = event.meta
        if not killer_uid:
            return
        es = _event_system()
        killer = ctx.resolve_unit(es.EntityRef(killer_uid))
        if killer and killer.is_alive:
            killer.cur_hp = 0

    return _effect


def _make_sell_for_gold_conditional(amount: int):
    """Sells for extra gold if player lost last combat."""

    def _effect(ctx: EffectContext, event: Event, trigger_uid: int) -> None:
        if event.source_pos:
            side = event.source_pos.side
        else:
            side = next(iter(ctx.players_by_uid), None)
            if side is None:
                return
        player = ctx.players_by_uid.get(side)
        if not player:
            return
        # Check if lost last combat (simplified: always give extra)
        lost_last = getattr(player, "lost_last_combat", False)
        gold = amount if lost_last else 1
        ctx.gain_gold(side, gold - 1)  # -1 because default sell already gives 1

    return _effect


def _make_dr_buff_all_friendlies_global(trigger_type: UnitType, atk: int, hp: int):
    """On death: permanently buff all surviving friendlies of type (Goldrinn)."""

    def _effect(ctx: EffectContext, event: Event, _trigger_uid: int) -> None:
        es = _event_system()
        pos = event.source_pos or (event.snapshot.pos if event.snapshot else None)
        if not pos:
            return
        for _slot, unit in ctx.iter_board_units(pos.side):
            if trigger_type in unit.types or trigger_type == UnitType.ALL:
                ctx.buff_combat(es.EntityRef(unit.uid), atk, hp)

    return _effect


def _make_eot_buff_friendly_type_naga(atk: int, hp: int):
    """EoT: give all other friendly Naga +atk/+hp."""

    def _effect(ctx: EffectContext, _event: Event, trigger_uid: int) -> None:
        es = _event_system()
        pos = ctx.resolve_pos(es.EntityRef(trigger_uid))
        if not pos:
            return
        for _slot, unit in ctx.iter_board_units(pos.side):
            if unit.uid != trigger_uid and UnitType.NAGA in unit.types:
                ctx.buff_perm(es.EntityRef(unit.uid), atk, hp)

    return _effect


def _make_on_friendly_demon_damage_buff(atk: int, hp: int):
    """After a friendly Demon deals damage, buff other friendlies +atk/+hp."""

    def _effect(ctx: EffectContext, event: Event, trigger_uid: int) -> None:
        es = _event_system()
        unit_pos = ctx.resolve_pos(es.EntityRef(trigger_uid))
        if not unit_pos:
            return
        # Check source is a friendly demon
        if not event.source:
            return
        src = ctx.resolve_unit(event.source)
        if not src or UnitType.DEMON not in src.types:
            return
        src_pos = ctx.resolve_pos(event.source)
        if not src_pos or src_pos.side != unit_pos.side:
            return
        for _slot, unit in ctx.iter_board_units(unit_pos.side):
            if unit.uid != src.uid:
                ctx.buff_perm(es.EntityRef(unit.uid), atk, hp)

    return _effect


def _make_eot_consume_tavern_for_demon():
    """EoT: each friendly Demon consumes a tavern minion for its stats."""

    def _effect(ctx: EffectContext, _event: Event, trigger_uid: int) -> None:
        es = _event_system()
        pos = ctx.resolve_pos(es.EntityRef(trigger_uid))
        if not pos:
            return
        demons = [
            unit for _slot, unit in ctx.iter_board_units(pos.side) if UnitType.DEMON in unit.types
        ]
        for demon in demons:
            result = ctx.consume_random_store_unit(pos.side)
            if result:
                gained_atk, gained_hp = result
                ctx.buff_perm(es.EntityRef(demon.uid), gained_atk, gained_hp)

    return _effect


def _make_soc_buff_friendly_type_scaling(trigger_type: UnitType, atk: int, hp: int):
    """SoC: buff all friendly units of type, scaling with a play counter."""

    def _effect(ctx: EffectContext, _event: Event, trigger_uid: int) -> None:
        es = _event_system()
        pos = ctx.resolve_pos(es.EntityRef(trigger_uid))
        if not pos:
            return
        for _slot, unit in ctx.iter_board_units(pos.side):
            if trigger_type in unit.types and unit.uid != trigger_uid:
                ctx.buff_combat(es.EntityRef(unit.uid), atk, hp)

    return _effect


def _make_eot_trigger_adjacent_battlecry():
    """EoT: trigger the battlecry of adjacent minions."""

    def _effect(ctx: EffectContext, _event: Event, trigger_uid: int) -> None:
        es = _event_system()
        pos = ctx.resolve_pos(es.EntityRef(trigger_uid))
        if not pos:
            return
        for _slot, unit in ctx.get_adjacent(pos.side, trigger_uid):
            # Re-fire MINION_PLAYED for adjacent unit to trigger its battlecry
            ctx.emit_event(
                es.Event(
                    event_type=es.EventType.MINION_PLAYED,
                    source=es.EntityRef(unit.uid),
                    source_pos=es.PosRef(side=pos.side, zone=es.Zone.BOARD, slot=_slot),
                )
            )

    return _effect


def _make_rally_deal_damage_equal_to_atk():
    """Rally: deal damage equal to this minion's Attack to a random enemy."""

    def _effect(ctx: EffectContext, _event: Event, trigger_uid: int) -> None:
        es = _event_system()
        pos = ctx.resolve_pos(es.EntityRef(trigger_uid))
        if not pos:
            return
        attacker = ctx.resolve_unit(es.EntityRef(trigger_uid))
        if not attacker:
            return
        enemy_side = 1 - pos.side
        candidates = [unit for _slot, unit in ctx.iter_board_units(enemy_side) if unit.is_alive]
        if not candidates:
            return
        target = random.choice(candidates)
        target.cur_hp -= attacker.cur_atk

    return _effect


def _make_dr_give_friendlies_scaling(buff_atk: int, buff_hp: int, self_damage: int):
    """DR: give all friendly minions +atk/+hp and deal self_damage to them."""

    def _effect(ctx: EffectContext, event: Event, _trigger_uid: int) -> None:
        es = _event_system()
        pos = event.source_pos or (event.snapshot.pos if event.snapshot else None)
        if not pos:
            return
        for _slot, unit in ctx.iter_board_units(pos.side):
            ctx.buff_perm(es.EntityRef(unit.uid), buff_atk, buff_hp)
            if self_damage > 0:
                unit.cur_hp -= self_damage

    return _effect


# ---------------------------------------------------------------------------
# B2 expansion factory functions (2026-09)
# ---------------------------------------------------------------------------


def _is_spellcraft(spell_id: Optional[str]) -> bool:
    """True if spell_id refers to a Spellcraft (temporary) spell."""
    if not spell_id:
        return False
    try:
        from .configs import SPELL_DB

        data = SPELL_DB.get(SpellIDs(spell_id))
    except (ValueError, KeyError):
        return False
    return bool(data and data.get("is_temporary"))


def _random_tavern_spell_id() -> Optional[str]:
    """Pick a random spell_id from the regular tavern spell pool
    (excludes spellcrafts and the triplet reward)."""
    from .configs import SPELL_DB

    candidates = [
        sid.value
        for sid, data in SPELL_DB.items()
        if data.get("pool", True)
        and not data.get("is_temporary")
        and sid != SpellIDs.TRIPLET_REWARD
    ]
    return random.choice(candidates) if candidates else None


def _cast_tavern_spell_as(
    ctx: EffectContext,
    event: Event,
    trigger_uid: int,
    side: int,
    spell_id: str,
    target_uid: Optional[int],
) -> None:
    """Apply a tavern spell's handler directly with a synthetic SPELL_CAST event.
    The synthetic event is NOT emitted to the queue, so no trigger cascade."""
    from . import spells as _spells

    es = _event_system()
    triggers = _spells.SPELL_TRIGGER_REGISTRY.get(spell_id)
    if not triggers:
        return
    handler = triggers[0].effect
    synthetic = es.Event(
        event_type=es.EventType.SPELL_CAST,
        source=es.EntityRef(trigger_uid),
        source_pos=es.PosRef(side=side, zone=es.Zone.BOARD, slot=0),
        target=es.EntityRef(target_uid) if target_uid is not None else None,
        spell_id=spell_id,
    )
    handler(ctx, synthetic, trigger_uid)


def _draw_filtered_unit_to_hand(
    ctx: EffectContext,
    side: int,
    unit_type: Optional[UnitType] = None,
    require_magnetic: bool = False,
    max_tier: int = 7,
    add_tag: Optional[Tags] = None,
) -> bool:
    """Draw a random pool unit matching the filters into hand.
    Returns True on success."""
    from .configs import CARD_DB
    from .entities import HandCard, Unit

    player = ctx.players_by_uid.get(side)
    if not player or not ctx.card_pool or len(player.hand) >= 10:
        return False
    candidates: List[str] = []
    for tier_cards in ctx.card_pool.tiers.values():
        for cid in tier_cards:
            data = CARD_DB.get(cid)
            if not data:
                continue
            try:
                t = int(data.get("tier", 99))
            except (TypeError, ValueError):
                continue
            if t < 1 or t > max_tier:
                continue
            if unit_type is not None and unit_type not in data.get("type", []):
                continue
            if require_magnetic and Tags.MAGNETIC not in data.get("tags", set()):
                continue
            candidates.append(cid)
    if not candidates:
        return False
    chosen = random.choice(candidates)
    for tier_cards in ctx.card_pool.tiers.values():
        if chosen in tier_cards:
            tier_cards.remove(chosen)
            break
    uid = ctx._uid_provider()
    new_unit = Unit.create_from_db(chosen, uid, side)
    if add_tag is not None:
        new_unit.tags.add(add_tag)
    player.hand.append(HandCard(uid=uid, unit=new_unit))
    return True


def _make_on_spell_cast_on_self_buff_self(atk: int, hp: int):
    """Whenever you cast a spell (same side), buff self +atk/+hp."""

    def _effect(ctx: EffectContext, event: Event, trigger_uid: int) -> None:
        es = _event_system()
        pos = ctx.resolve_pos(es.EntityRef(trigger_uid))
        if not pos:
            return
        if event.source_pos and event.source_pos.side != pos.side:
            return
        unit = ctx.resolve_unit(es.EntityRef(trigger_uid))
        if not unit or not unit.is_alive:
            return
        ctx.buff_perm(es.EntityRef(trigger_uid), atk, hp)

    return _effect


def _make_on_spell_cast_scaling_buff_self(per_n: int, atk: int, hp: int):
    """Every `per_n` spells you cast, buff self +atk/+hp."""

    def _effect(ctx: EffectContext, event: Event, trigger_uid: int) -> None:
        es = _event_system()
        pos = ctx.resolve_pos(es.EntityRef(trigger_uid))
        if not pos:
            return
        if event.source_pos and event.source_pos.side != pos.side:
            return
        player = ctx.players_by_uid.get(pos.side)
        if not player:
            return
        key = f"spellcast_{trigger_uid}"
        player.mechanics.increment_scaling(key)
        if player.mechanics.get_scaling(key) % per_n != 0:
            return
        unit = ctx.resolve_unit(es.EntityRef(trigger_uid))
        if not unit or not unit.is_alive:
            return
        ctx.buff_perm(es.EntityRef(trigger_uid), atk, hp)

    return _effect


def _make_on_spell_cast_recast_random_tavern_spell():
    """Whenever you cast a spell (same side), cast a random Tavern spell
    on a random valid target."""

    def _effect(ctx: EffectContext, event: Event, trigger_uid: int) -> None:
        from . import spells as _spells

        es = _event_system()
        pos = ctx.resolve_pos(es.EntityRef(trigger_uid))
        if not pos:
            return
        if event.source_pos and event.source_pos.side != pos.side:
            return
        spell_id = _random_tavern_spell_id()
        if not spell_id:
            return
        target_uid = None
        if spell_id in _spells.SPELLS_REQUIRE_TARGET:
            candidates = [u for _, u in ctx.iter_board_units(pos.side) if u.is_alive]
            if not candidates:
                return
            target_uid = random.choice(candidates).uid
        _cast_tavern_spell_as(ctx, event, trigger_uid, pos.side, spell_id, target_uid)

    return _effect


def _make_other_summon_scaling_aura(trigger_type: UnitType, atk: int, hp: int):
    """Whenever you summon a minion of trigger_type (not self), give it +atk/+hp."""

    def _effect(ctx: EffectContext, event: Event, trigger_uid: int) -> None:
        es = _event_system()
        summoned = ctx.resolve_unit(event.source)
        if not summoned or trigger_type not in summoned.types:
            return
        if summoned.uid == trigger_uid:
            return
        source_pos = event.source_pos
        unit_pos = ctx.resolve_pos(es.EntityRef(trigger_uid))
        if not source_pos or not unit_pos or source_pos.side != unit_pos.side:
            return
        ctx.buff_perm(es.EntityRef(summoned.uid), atk, hp)

    return _effect


def _make_soc_buff_leftmost_type_windfury(trigger_type: UnitType, atk: int, hp: int):
    """SoC: leftmost friendly minion of trigger_type gains +atk/+hp (combat)
    and Windfury."""

    def _effect(ctx: EffectContext, _event: Event, trigger_uid: int) -> None:
        es = _event_system()
        pos = ctx.resolve_pos(es.EntityRef(trigger_uid))
        if not pos:
            return
        target = None
        for _slot, unit in ctx.iter_board_units(pos.side):
            if trigger_type in unit.types or UnitType.ALL in unit.types:
                target = unit
                break
        if not target:
            return
        ctx.buff_combat(es.EntityRef(target.uid), atk, hp)
        target.tags.add(Tags.WINDFURY)

    return _effect


def _make_keep_first_spellcraft_per_turn(atk: int, hp: int):
    """The first Spellcraft you cast each turn also gives its target +atk/+hp."""

    def _effect(ctx: EffectContext, event: Event, trigger_uid: int) -> None:
        es = _event_system()
        if not _is_spellcraft(event.spell_id):
            return
        pos = ctx.resolve_pos(es.EntityRef(trigger_uid))
        if not pos:
            return
        if event.source_pos and event.source_pos.side != pos.side:
            return
        unit = ctx.resolve_unit(es.EntityRef(trigger_uid))
        if not unit or "first_spellcraft" in unit.turn_flags:
            return
        target = ctx.resolve_unit(event.target) if event.target else None
        if not target:
            return
        unit.turn_flags.add("first_spellcraft")
        ctx.buff_perm(es.EntityRef(target.uid), atk, hp)

    return _effect


def _make_activate_get_random_unit(cost: int, unit_type: Optional[UnitType]):
    """END_OF_TURN: if affordable, pay cost and add a random unit to hand."""

    def _effect(ctx: EffectContext, _event: Event, trigger_uid: int) -> None:
        es = _event_system()
        pos = ctx.resolve_pos(es.EntityRef(trigger_uid))
        if not pos:
            return
        player = ctx.players_by_uid.get(pos.side)
        if not player or player.gold < cost:
            return
        player.gold -= cost
        _draw_filtered_unit_to_hand(
            ctx, pos.side, unit_type=unit_type, max_tier=player.tavern_tier
        )

    return _effect


def _make_activate_gain_gold_next_turn(cost: int, gold: int):
    """END_OF_TURN: if affordable, pay cost to gain `gold` Gold next turn."""

    def _effect(ctx: EffectContext, _event: Event, trigger_uid: int) -> None:
        es = _event_system()
        pos = ctx.resolve_pos(es.EntityRef(trigger_uid))
        if not pos:
            return
        player = ctx.players_by_uid.get(pos.side)
        if not player or player.gold < cost:
            return
        player.gold -= cost
        player.gold_next_turn += gold

    return _effect


def _make_activate_cast_random_spells(cost: int, count: int):
    """END_OF_TURN: if affordable, pay cost and cast `count` random Tavern spells."""

    def _effect(ctx: EffectContext, event: Event, trigger_uid: int) -> None:
        from . import spells as _spells

        es = _event_system()
        pos = ctx.resolve_pos(es.EntityRef(trigger_uid))
        if not pos:
            return
        player = ctx.players_by_uid.get(pos.side)
        if not player or player.gold < cost:
            return
        player.gold -= cost
        for _ in range(count):
            spell_id = _random_tavern_spell_id()
            if not spell_id:
                continue
            target_uid = None
            if spell_id in _spells.SPELLS_REQUIRE_TARGET:
                candidates = [u for _, u in ctx.iter_board_units(pos.side) if u.is_alive]
                if not candidates:
                    continue
                target_uid = random.choice(candidates).uid
            _cast_tavern_spell_as(ctx, event, trigger_uid, pos.side, spell_id, target_uid)

    return _effect


def _make_on_self_attack_buff_friendly_type_global(
    trigger_type: UnitType, atk: int, hp: int
):
    """Whenever this attacks: give all friendly minions of trigger_type
    (board + hand) +atk/+hp."""

    def _effect(ctx: EffectContext, _event: Event, trigger_uid: int) -> None:
        es = _event_system()
        pos = ctx.resolve_pos(es.EntityRef(trigger_uid))
        if not pos:
            return
        player = ctx.players_by_uid.get(pos.side)
        if not player:
            return
        for _slot, unit in ctx.iter_board_units(pos.side):
            if trigger_type in unit.types or trigger_type == UnitType.ALL:
                ctx.buff_perm(es.EntityRef(unit.uid), atk, hp)
        for hc in player.hand:
            if hc.unit and (
                trigger_type in hc.unit.types or trigger_type == UnitType.ALL
            ):
                ctx.buff_perm(es.EntityRef(hc.unit.uid), atk, hp)

    return _effect


def _make_on_self_attack_modify_mechanic(mechanic: MechanicType, atk: int, hp: int):
    """Whenever this attacks: modify a global mechanic stat."""

    def _effect(ctx: EffectContext, _event: Event, trigger_uid: int) -> None:
        es = _event_system()
        pos = ctx.resolve_pos(es.EntityRef(trigger_uid))
        if not pos:
            return
        player = ctx.players_by_uid.get(pos.side)
        if not player:
            return
        player.mechanics.modify_stat(mechanic, atk, hp)

    return _effect


def _make_bc_buff_other_type_scaling(
    trigger_type: UnitType, atk: int, hp: int, per_tier_atk: int, per_tier_hp: int
):
    """BC: give other friendly minions of trigger_type +atk/+hp
    plus a per-tavern-tier bonus."""

    def _effect(ctx: EffectContext, _event: Event, trigger_uid: int) -> None:
        es = _event_system()
        pos = ctx.resolve_pos(es.EntityRef(trigger_uid))
        if not pos:
            return
        player = ctx.players_by_uid.get(pos.side)
        if not player:
            return
        tier = player.tavern_tier
        total_atk = atk + per_tier_atk * tier
        total_hp = hp + per_tier_hp * tier
        for _slot, unit in ctx.iter_board_units(pos.side):
            if unit.uid == trigger_uid:
                continue
            if trigger_type in unit.types or UnitType.ALL in unit.types:
                ctx.buff_perm(es.EntityRef(unit.uid), total_atk, total_hp)

    return _effect


def _make_on_friendly_sell_type_buff_self(trigger_type: UnitType, atk: int, hp: int):
    """Whenever you sell another friendly minion of trigger_type, gain +atk/+hp."""

    def _effect(ctx: EffectContext, event: Event, trigger_uid: int) -> None:
        es = _event_system()
        # MINION_SOLD fires before the unit is popped, so it still resolves.
        sold = ctx.resolve_unit(event.source)
        if not sold or trigger_type not in sold.types:
            return
        if sold.uid == trigger_uid:
            return
        pos = ctx.resolve_pos(es.EntityRef(trigger_uid))
        if not pos:
            return
        if event.source_pos and event.source_pos.side != pos.side:
            return
        unit = ctx.resolve_unit(es.EntityRef(trigger_uid))
        if not unit:
            return
        ctx.buff_perm(es.EntityRef(trigger_uid), atk, hp)

    return _effect


def _make_bc_buff_shop(atk: int, hp: int, max_tier: int = 7):
    """BC: give shop minions (tier <= max_tier) +atk/+hp."""

    def _effect(ctx: EffectContext, _event: Event, trigger_uid: int) -> None:
        from .configs import CARD_DB

        es = _event_system()
        pos = ctx.resolve_pos(es.EntityRef(trigger_uid))
        if not pos:
            return
        for _slot, unit in ctx.iter_store_units(pos.side):
            data = CARD_DB.get(unit.card_id, {})
            try:
                tier = int(data.get("tier", 0))
            except (TypeError, ValueError):
                tier = 0
            if tier > max_tier:
                continue
            ctx.buff_perm(es.EntityRef(unit.uid), atk, hp)

    return _effect


def _make_bc_discover_mech_magnetize():
    """BC (simplified, no discover UI): add a random Mech to hand, give it Magnetic."""

    def _effect(ctx: EffectContext, _event: Event, trigger_uid: int) -> None:
        es = _event_system()
        pos = ctx.resolve_pos(es.EntityRef(trigger_uid))
        if not pos:
            return
        player = ctx.players_by_uid.get(pos.side)
        if not player:
            return
        _draw_filtered_unit_to_hand(
            ctx,
            pos.side,
            unit_type=UnitType.MECH,
            max_tier=player.tavern_tier,
            add_tag=Tags.MAGNETIC,
        )

    return _effect


def _make_dr_buff_one_of_each_type(atk: int, hp: int):
    """DR: give a random friendly minion of each type +atk/+hp.
    ALL minions count for every type."""
    _all_types = [
        UnitType.BEAST,
        UnitType.DRAGON,
        UnitType.DEMON,
        UnitType.MURLOC,
        UnitType.PIRATE,
        UnitType.ELEMENTAL,
        UnitType.MECH,
        UnitType.UNDEAD,
        UnitType.NAGA,
        UnitType.QUILBOAR,
    ]

    def _effect(ctx: EffectContext, event: Event, _trigger_uid: int) -> None:
        es = _event_system()
        pos = event.source_pos or (event.snapshot.pos if event.snapshot else None)
        if not pos:
            return
        for t in _all_types:
            candidates = [
                unit
                for _slot, unit in ctx.iter_board_units(pos.side)
                if (t in unit.types or UnitType.ALL in unit.types) and unit.is_alive
            ]
            if not candidates:
                continue
            target = random.choice(candidates)
            ctx.buff_perm(es.EntityRef(target.uid), atk, hp)

    return _effect


def _make_rally_cast_spell_on_right():
    """When this attacks: cast a random Tavern spell on the minion to its right."""

    def _effect(ctx: EffectContext, event: Event, trigger_uid: int) -> None:
        es = _event_system()
        pos = ctx.resolve_pos(es.EntityRef(trigger_uid))
        if not pos:
            return
        player = ctx.players_by_uid.get(pos.side)
        if not player:
            return
        right_unit = None
        for slot, unit in enumerate(player.board):
            if unit.uid == trigger_uid and slot + 1 < len(player.board):
                right_unit = player.board[slot + 1]
                break
        if not right_unit:
            return
        spell_id = _random_tavern_spell_id()
        if not spell_id:
            return
        _cast_tavern_spell_as(
            ctx, event, trigger_uid, pos.side, spell_id, right_unit.uid
        )

    return _effect


def _make_spellcraft_cast_on_self_add_copy_once_per_turn():
    """When you cast a Spellcraft on this: add a copy to hand (once per turn)."""

    def _effect(ctx: EffectContext, event: Event, trigger_uid: int) -> None:
        es = _event_system()
        if not _is_spellcraft(event.spell_id):
            return
        if not event.target or event.target.uid != trigger_uid:
            return
        pos = ctx.resolve_pos(es.EntityRef(trigger_uid))
        if not pos:
            return
        if event.source_pos and event.source_pos.side != pos.side:
            return
        unit = ctx.resolve_unit(es.EntityRef(trigger_uid))
        if not unit or "spellcraft_copied" in unit.turn_flags:
            return
        unit.turn_flags.add("spellcraft_copied")
        ctx.add_spell_to_hand(pos.side, event.spell_id)

    return _effect


def _make_eot_add_random_unit_from_list(unit_type: Optional[UnitType]):
    """EoT: add a random unit of unit_type (tier <= tavern tier) to hand."""

    def _effect(ctx: EffectContext, _event: Event, trigger_uid: int) -> None:
        es = _event_system()
        pos = ctx.resolve_pos(es.EntityRef(trigger_uid))
        if not pos:
            return
        player = ctx.players_by_uid.get(pos.side)
        if not player:
            return
        _draw_filtered_unit_to_hand(
            ctx, pos.side, unit_type=unit_type, max_tier=player.tavern_tier
        )

    return _effect


def _make_dr_summon_first_dead_mechs(count: int):
    """DR: summon the first `count` friendly Mechs that died this combat
    as fresh copies. Consumed log entries are skipped by later triggers."""

    def _effect(ctx: EffectContext, event: Event, _trigger_uid: int) -> None:
        pos = event.source_pos or (event.snapshot.pos if event.snapshot else None)
        if not pos:
            return
        player = ctx.players_by_uid.get(pos.side)
        if not player:
            return
        picked = []
        for record in player.combat_death_log:
            if len(picked) >= count:
                break
            if record.get("kangor_used"):
                continue
            if UnitType.MECH not in record.get("types", []):
                continue
            record["kangor_used"] = True
            picked.append(record)
        for record in picked:
            ctx.summon(pos.side, record["card_id"], pos.slot)

    return _effect


def _make_dr_add_random_magnetic_unit():
    """DR: add a random Magnetic unit (tier <= tavern tier) to hand."""

    def _effect(ctx: EffectContext, event: Event, _trigger_uid: int) -> None:
        pos = event.source_pos or (event.snapshot.pos if event.snapshot else None)
        if not pos:
            return
        player = ctx.players_by_uid.get(pos.side)
        if not player:
            return
        _draw_filtered_unit_to_hand(
            ctx,
            pos.side,
            require_magnetic=True,
            max_tier=player.tavern_tier,
        )

    return _effect


def _make_on_spellcast_on_self_cast_on_adjacent():
    """When you cast a Spellcraft on this: also cast a copy on adjacent minions."""

    def _effect(ctx: EffectContext, event: Event, trigger_uid: int) -> None:
        es = _event_system()
        if not _is_spellcraft(event.spell_id):
            return
        if not event.target or event.target.uid != trigger_uid:
            return
        pos = ctx.resolve_pos(es.EntityRef(trigger_uid))
        if not pos:
            return
        if event.source_pos and event.source_pos.side != pos.side:
            return
        for _slot, unit in ctx.get_adjacent(pos.side, trigger_uid):
            _cast_tavern_spell_as(
                ctx, event, trigger_uid, pos.side, event.spell_id, unit.uid
            )

    return _effect


def _make_on_mrrglton_played_buff_self(atk: int, hp: int):
    """Whenever you play Mama/Papa Mrrglton (including itself), gain +atk/+hp."""
    _mrrglton_ids = {CardIDs.MAMA_MRRGLTON.value, CardIDs.PAPA_MRRGLTON.value}

    def _effect(ctx: EffectContext, event: Event, trigger_uid: int) -> None:
        es = _event_system()
        played = ctx.resolve_unit(event.source)
        if not played or played.card_id not in _mrrglton_ids:
            return
        pos = ctx.resolve_pos(es.EntityRef(trigger_uid))
        if not pos:
            return
        if event.source_pos and event.source_pos.side != pos.side:
            return
        unit = ctx.resolve_unit(es.EntityRef(trigger_uid))
        if not unit:
            return
        ctx.buff_perm(es.EntityRef(trigger_uid), atk, hp)

    return _effect


def _make_gain_immune():
    """Give the trigger unit IMMUNE."""

    def _effect(ctx: EffectContext, _event: Event, trigger_uid: int) -> None:
        es = _event_system()
        unit = ctx.resolve_unit(es.EntityRef(trigger_uid))
        if unit:
            unit.tags.add(Tags.IMMUNE)

    return _effect


def _make_lose_immune():
    """Remove IMMUNE from the trigger unit."""

    def _effect(ctx: EffectContext, _event: Event, trigger_uid: int) -> None:
        es = _event_system()
        unit = ctx.resolve_unit(es.EntityRef(trigger_uid))
        if unit:
            unit.tags.discard(Tags.IMMUNE)

    return _effect


def _make_spend_gold_buff_type(
    trigger_type: UnitType, gold_per: int, atk: int, hp: int, max_targets: int
):
    """Every `gold_per` Gold spent: give up to `max_targets` other friendly
    minions of trigger_type +atk/+hp. Paid out at end of turn."""

    def _effect(ctx: EffectContext, _event: Event, trigger_uid: int) -> None:
        es = _event_system()
        pos = ctx.resolve_pos(es.EntityRef(trigger_uid))
        if not pos:
            return
        player = ctx.players_by_uid.get(pos.side)
        if not player:
            return
        paid_key = f"dual_wield_paid_{trigger_uid}"
        spent = player.mechanics.get_scaling("gold_spent")
        paid = player.mechanics.get_scaling(paid_key)
        new_thresholds = spent // gold_per - paid // gold_per
        if new_thresholds <= 0:
            return
        player.mechanics.increment_scaling(paid_key, new_thresholds * gold_per)
        for _ in range(new_thresholds):
            candidates = [
                unit
                for _slot, unit in ctx.iter_board_units(pos.side)
                if trigger_type in unit.types
                and unit.uid != trigger_uid
                and unit.is_alive
            ]
            if not candidates:
                break
            for unit in random.sample(candidates, min(max_targets, len(candidates))):
                ctx.buff_perm(es.EntityRef(unit.uid), atk, hp)

    return _effect


def _make_dr_buff_friendly_type_scaling(
    trigger_type: UnitType, atk: int, hp: int, per_tier_atk: int, per_tier_hp: int
):
    """DR: give friendly minions of trigger_type +atk/+hp plus per-tier bonus."""

    def _effect(ctx: EffectContext, event: Event, _trigger_uid: int) -> None:
        es = _event_system()
        pos = event.source_pos or (event.snapshot.pos if event.snapshot else None)
        if not pos:
            return
        player = ctx.players_by_uid.get(pos.side)
        if not player:
            return
        tier = player.tavern_tier
        total_atk = atk + per_tier_atk * tier
        total_hp = hp + per_tier_hp * tier
        for _slot, unit in ctx.iter_board_units(pos.side):
            if trigger_type in unit.types or trigger_type == UnitType.ALL:
                ctx.buff_perm(es.EntityRef(unit.uid), total_atk, total_hp)

    return _effect


def _make_on_friendly_play_type_buff_self_scaling(
    trigger_type: UnitType, atk: int, hp: int
):
    """Whenever you play another friendly minion of trigger_type, gain +atk/+hp."""

    def _effect(ctx: EffectContext, event: Event, trigger_uid: int) -> None:
        es = _event_system()
        played = ctx.resolve_unit(event.source)
        if not played or trigger_type not in played.types:
            return
        if event.source and event.source.uid == trigger_uid:
            return
        pos = ctx.resolve_pos(es.EntityRef(trigger_uid))
        if not pos:
            return
        if event.source_pos and event.source_pos.side != pos.side:
            return
        unit = ctx.resolve_unit(es.EntityRef(trigger_uid))
        if not unit:
            return
        ctx.buff_perm(es.EntityRef(trigger_uid), atk, hp)

    return _effect


def _make_on_spell_cast_on_type_buff_board(trigger_type: UnitType, atk: int, hp: int):
    """Whenever you cast a spell (same side): give all friendly board minions
    of trigger_type +atk/+hp."""

    def _effect(ctx: EffectContext, event: Event, trigger_uid: int) -> None:
        es = _event_system()
        pos = ctx.resolve_pos(es.EntityRef(trigger_uid))
        if not pos:
            return
        if event.source_pos and event.source_pos.side != pos.side:
            return
        for _slot, unit in ctx.iter_board_units(pos.side):
            if trigger_type in unit.types or UnitType.ALL in unit.types:
                ctx.buff_perm(es.EntityRef(unit.uid), atk, hp)

    return _effect


def _make_eot_buff_board_by_type_on_play(
    play_type: UnitType, buff_type: UnitType, atk: int, hp: int
):
    """Whenever you play a minion of play_type (excluding self): give other
    friendly board minions of buff_type +atk/+hp."""

    def _effect(ctx: EffectContext, event: Event, trigger_uid: int) -> None:
        es = _event_system()
        played = ctx.resolve_unit(event.source)
        if not played or play_type not in played.types:
            return
        if event.source and event.source.uid == trigger_uid:
            return
        pos = ctx.resolve_pos(es.EntityRef(trigger_uid))
        if not pos:
            return
        if event.source_pos and event.source_pos.side != pos.side:
            return
        for _slot, unit in ctx.iter_board_units(pos.side):
            if unit.uid == trigger_uid:
                continue
            if buff_type in unit.types or UnitType.ALL in unit.types:
                ctx.buff_perm(es.EntityRef(unit.uid), atk, hp)

    return _effect


def _make_bc_buff_all_by_type_include_hand(trigger_type: UnitType, atk: int, hp: int):
    """BC: give all friendly units of type +atk/+hp (board + hand)."""

    def _effect(ctx: EffectContext, _event: Event, trigger_uid: int) -> None:
        es = _event_system()
        pos = ctx.resolve_pos(es.EntityRef(trigger_uid))
        if not pos:
            return
        player = ctx.players_by_uid.get(pos.side)
        if not player:
            return
        for _slot, unit in ctx.iter_board_units(pos.side):
            if trigger_type in unit.types or UnitType.ALL in unit.types:
                ctx.buff_perm(es.EntityRef(unit.uid), atk, hp)
        for hc in player.hand:
            if hc.unit and (
                trigger_type in hc.unit.types or UnitType.ALL in hc.unit.types
            ):
                ctx.buff_perm(es.EntityRef(hc.unit.uid), atk, hp)

    return _effect


def _make_bc_dr_buff_tavern_type(trigger_type: UnitType, atk: int, hp: int):
    """BC and DR: give minions of trigger_type in the Tavern +atk/+hp
    this game (Dancing Barnstormer)."""

    def _effect(ctx: EffectContext, event: Event, trigger_uid: int) -> None:
        es = _event_system()
        if event.event_type == es.EventType.MINION_PLAYED:
            pos = ctx.resolve_pos(es.EntityRef(trigger_uid))
        else:  # MINION_DIED
            pos = event.source_pos or (event.snapshot.pos if event.snapshot else None)
        if not pos:
            return
        for _slot, unit in ctx.iter_store_units(pos.side):
            if trigger_type in unit.types or trigger_type == UnitType.ALL:
                ctx.buff_perm(es.EntityRef(unit.uid), atk, hp)
        # Persist for future shop units this game (same convention as Felemental)
        player = ctx.players_by_uid.get(pos.side)
        if player:
            player.mechanics.modify_stat(MechanicType.ELEMENTAL_BUFF, atk, hp)

    return _effect


def _make_on_play_type_buff_board_include_self(
    play_type: UnitType, buff_type: UnitType, atk: int, hp: int
):
    """Whenever you play a friendly minion of play_type (including self):
    give all friendly board minions of buff_type +atk/+hp
    (Unleashed Mana Surge)."""

    def _effect(ctx: EffectContext, event: Event, trigger_uid: int) -> None:
        es = _event_system()
        played = ctx.resolve_unit(event.source)
        if not played or play_type not in played.types:
            return
        pos = ctx.resolve_pos(es.EntityRef(trigger_uid))
        if not pos:
            return
        if event.source_pos and event.source_pos.side != pos.side:
            return
        for _slot, unit in ctx.iter_board_units(pos.side):
            if buff_type in unit.types or buff_type == UnitType.ALL:
                ctx.buff_perm(es.EntityRef(unit.uid), atk, hp)

    return _effect


def _make_on_summon_automaton_buff(atk: int, hp: int):
    """Whenever you summon an Ancestral Automaton: give other friendly
    Ancestral Automatons +atk/+hp, and the summoned one +atk/+hp
    for each other friendly Ancestral Automaton (board + hand).
    Only the summoned unit's own trigger fires (avoids double-counting)."""

    def _effect(ctx: EffectContext, event: Event, trigger_uid: int) -> None:
        es = _event_system()
        summoned = ctx.resolve_unit(event.source)
        if not summoned:
            return
        if summoned.card_id != CardIDs.ANCESTRAL_AUTOMATON:
            return
        # Only the summoned unit's own trigger fires
        if summoned.uid != trigger_uid:
            return
        pos = ctx.resolve_pos(es.EntityRef(trigger_uid))
        if not pos:
            return
        if event.source_pos and event.source_pos.side != pos.side:
            return
        # Find other friendly Automatons (board + hand, excluding summoned)
        others = []
        for _slot, unit in ctx.iter_board_units(pos.side):
            if unit.uid == summoned.uid:
                continue
            if unit.card_id == CardIDs.ANCESTRAL_AUTOMATON:
                others.append(unit)
        player = ctx.players_by_uid.get(pos.side)
        if player:
            for hc in player.hand:
                if hc.unit and hc.unit.uid != summoned.uid:
                    if hc.unit.card_id == CardIDs.ANCESTRAL_AUTOMATON:
                        others.append(hc.unit)
        # Buff others +atk/+hp
        for unit in others:
            ctx.buff_perm(es.EntityRef(unit.uid), atk, hp)
        # Buff summoned +atk/+hp per other
        if others:
            ctx.buff_perm(
                es.EntityRef(summoned.uid), atk * len(others), hp * len(others)
            )

    return _effect


def _make_eot_add_mrrglton():
    """At the end of your turn, get a Mama Mrrglton or a Papa Mrrglton
    (Cousin Errgl)."""

    def _effect(ctx: EffectContext, event: Event, trigger_uid: int) -> None:
        es = _event_system()
        pos = ctx.resolve_pos(es.EntityRef(trigger_uid))
        if not pos:
            return
        card_id = random.choice(
            [CardIDs.MAMA_MRRGLTON, CardIDs.PAPA_MRRGLTON]
        )
        ctx.add_unit_to_hand(pos.side, card_id)

    return _effect


def _make_rally_modify_mechanic(mechanic: MechanicType, atk: int, hp: int):
    """Rally: modify a global mechanic stat (Moat Custodian)."""

    def _effect(ctx: EffectContext, event: Event, trigger_uid: int) -> None:
        es = _event_system()
        pos = ctx.resolve_pos(es.EntityRef(trigger_uid))
        if not pos:
            return
        player = ctx.players_by_uid.get(pos.side)
        if player:
            player.mechanics.modify_stat(mechanic, atk, hp)

    return _effect


def _make_bc_buff_other_type(trigger_type: UnitType, atk: int, hp: int):
    """BC: give other friendly board minions of trigger_type +atk/+hp
    (Mama/Papa Mrrglton)."""

    def _effect(ctx: EffectContext, event: Event, trigger_uid: int) -> None:
        es = _event_system()
        pos = ctx.resolve_pos(es.EntityRef(trigger_uid))
        if not pos:
            return
        for _slot, unit in ctx.iter_board_units(pos.side):
            if unit.uid == trigger_uid:
                continue
            if trigger_type in unit.types or UnitType.ALL in unit.types:
                ctx.buff_perm(es.EntityRef(unit.uid), atk, hp)

    return _effect


def _make_on_tavern_spell_cast_buff_self(atk: int, hp: int):
    """Whenever you cast a Tavern spell, gain +atk/+hp
    (Abyssal Bruiser). Simplified: triggers on any SPELL_CAST."""

    def _effect(ctx: EffectContext, event: Event, trigger_uid: int) -> None:
        es = _event_system()
        # TODO: distinguish Tavern spells from Spellcrafts via spell_id
        ctx.buff_perm(es.EntityRef(trigger_uid), atk, hp)

    return _effect


def _make_dr_buff_friendly_type(trigger_type: UnitType, atk: int, hp: int):
    """DR: give all friendly board minions of trigger_type +atk/+hp
    (Showy Cyclist)."""

    def _effect(ctx: EffectContext, event: Event, trigger_uid: int) -> None:
        es = _event_system()
        pos = event.source_pos or (event.snapshot.pos if event.snapshot else None)
        if not pos:
            return
        for _slot, unit in ctx.iter_board_units(pos.side):
            if trigger_type in unit.types or trigger_type == UnitType.ALL:
                ctx.buff_perm(es.EntityRef(unit.uid), atk, hp)

    return _effect


def _make_on_spell_cast_on_naga_buff_board(atk: int, hp: int):
    """Whenever you cast a spell on a Naga, give all friendly board
    minions +atk/+hp (Torrential Ruiner)."""

    def _effect(ctx: EffectContext, event: Event, trigger_uid: int) -> None:
        es = _event_system()
        target = ctx.resolve_unit(event.target) if event.target else None
        if not target or UnitType.NAGA not in target.types:
            return
        pos = ctx.resolve_pos(es.EntityRef(trigger_uid))
        if not pos:
            return
        if event.source_pos and event.source_pos.side != pos.side:
            return
        for _slot, unit in ctx.iter_board_units(pos.side):
            ctx.buff_perm(es.EntityRef(unit.uid), atk, hp)

    return _effect


def _make_on_play_naga_buff_self(atk: int, hp: int):
    """After you play a Naga, gain +atk/+hp (Groundbreaker)."""

    def _effect(ctx: EffectContext, event: Event, trigger_uid: int) -> None:
        es = _event_system()
        played = ctx.resolve_unit(event.source)
        if not played or UnitType.NAGA not in played.types:
            return
        # Only trigger if this Groundbreaker is on board
        pos = ctx.resolve_pos(es.EntityRef(trigger_uid))
        if not pos:
            return
        if event.source_pos and event.source_pos.side != pos.side:
            return
        ctx.buff_perm(es.EntityRef(trigger_uid), atk, hp)

    return _effect


def _is_self_on_board(ctx, event, ref) -> bool:
    """Condition: the trigger unit (ref) is currently on the board
    (not in hand or shop)."""
    es = _event_system()
    pos = ctx.resolve_pos(es.EntityRef(ref))
    if not pos:
        return False
    for _slot, unit in ctx.iter_board_units(pos.side):
        if unit.uid == ref:
            return True
    return False


# ---------------------------------------------------------------------------
# build_trigger_registry  →  produces the same dict as original TRIGGER_REGISTRY
# ---------------------------------------------------------------------------


def build_trigger_registry() -> Dict[str, list]:
    es = _event_system()
    TriggerDef = es.TriggerDef
    EventType = es.EventType

    registry: Dict[str, list] = {}

    for card in ALL_CARDS:
        triggers: list = []

        for eff in card.effects:
            # --- Deathrattle: summon token(s) ---
            if isinstance(eff, DeathrattleSummon):
                triggers.append(
                    TriggerDef(
                        event_type=EventType.MINION_DIED,
                        condition=_is_self_death,
                        effect=_make_dr_summon(eff.token_id, eff.count),
                        name=f"{card.name} Deathrattle",
                    )
                )

            # --- Deathrattle: summon token(s) with extra tag ---
            elif isinstance(eff, DeathrattleSummonWithTag):
                triggers.append(
                    TriggerDef(
                        event_type=EventType.MINION_DIED,
                        condition=_is_self_death,
                        effect=_make_dr_summon_with_tag(eff.token_id, eff.count, eff.tag),
                        name=f"{card.name} Deathrattle",
                    )
                )

            # --- Battlecry: summon unit at right ---
            elif isinstance(eff, BattlecrySummonAtRight):
                triggers.append(
                    TriggerDef(
                        event_type=EventType.MINION_PLAYED,
                        condition=_is_self_play,
                        effect=_make_battlecry_summon_at_right(eff.token_id),
                        name=f"{card.name} Battlecry",
                        priority=10,
                    )
                )

            # --- Battlecry: gain gold ---
            elif isinstance(eff, BattlecryGainGold):
                triggers.append(
                    TriggerDef(
                        event_type=EventType.MINION_PLAYED,
                        condition=_is_self_play,
                        effect=_make_battlecry_gain_gold(eff.amount),
                        name=f"{card.name} Battlecry",
                        priority=10,
                    )
                )

            # --- Battlecry: add spell to hand ---
            elif isinstance(eff, BattlecryAddSpell):
                triggers.append(
                    TriggerDef(
                        event_type=EventType.MINION_PLAYED,
                        condition=_is_self_play,
                        effect=_make_battlecry_add_spell(eff.spell_id, eff.count),
                        name=f"{card.name} Battlecry",
                        priority=10,
                    )
                )

            # --- Battlecry: spell discount ---
            elif isinstance(eff, BattlecrySpellDiscount):
                triggers.append(
                    TriggerDef(
                        event_type=EventType.MINION_PLAYED,
                        condition=_is_self_play,
                        effect=_make_battlecry_spell_discount(eff.amount),
                        name=f"{card.name} Battlecry",
                        priority=10,
                    )
                )

            # --- Battlecry: modify mechanic ---
            elif isinstance(eff, BattlecryModifyMechanic):
                triggers.append(
                    TriggerDef(
                        event_type=EventType.MINION_PLAYED,
                        condition=_is_self_play,
                        effect=_make_battlecry_modify_mechanic(eff.mechanic, eff.atk, eff.hp),
                        name=f"{card.name} Battlecry",
                        priority=10,
                    )
                )

            # --- Battlecry: consume random shop unit ---
            elif isinstance(eff, ConsumeShopUnit):
                triggers.append(
                    TriggerDef(
                        event_type=EventType.MINION_PLAYED,
                        condition=_is_self_play,
                        effect=_make_battlecry_consume_shop_unit(),
                        name=f"{card.name} Battlecry",
                        priority=10,
                    )
                )

            # --- Battlecry: make self golden ---
            elif isinstance(eff, BattlecryMakeGolden):
                triggers.append(
                    TriggerDef(
                        event_type=EventType.MINION_PLAYED,
                        condition=_is_self_play,
                        effect=_make_battlecry_make_golden(),
                        name=f"{card.name} Battlecry",
                        priority=10,
                    )
                )

            # --- Sell: add spell to hand ---
            elif isinstance(eff, SellAddSpell):
                triggers.append(
                    TriggerDef(
                        event_type=EventType.MINION_SOLD,
                        condition=_is_self_play,
                        effect=_make_sell_add_spell(eff.spell_id, eff.count),
                        name=f"{card.name} Sell",
                    )
                )

            # --- Sell: get random unit ---
            elif isinstance(eff, SellGetRandomUnit):
                triggers.append(
                    TriggerDef(
                        event_type=EventType.MINION_SOLD,
                        condition=_is_self_play,
                        effect=_make_sell_get_random_unit(eff.tier),
                        name=f"{card.name} Sell",
                    )
                )

            # --- Sell for gold ---
            elif isinstance(eff, SellForGold):
                triggers.append(
                    TriggerDef(
                        event_type=EventType.MINION_SOLD,
                        condition=_is_self_play,
                        effect=_make_sell_for_gold(eff.amount),
                        name=f"{card.name} Sell",
                    )
                )

            # --- Rally: Blood Gem on self when this attacks ---
            elif isinstance(eff, RallyBuff):
                triggers.append(
                    TriggerDef(
                        event_type=EventType.ATTACK_DECLARED,
                        condition=_is_self_play,  # source.uid == trigger_uid
                        effect=_make_rally_buff(eff.atk, eff.hp, eff.use_blood_gem),
                        name=f"{card.name} Rally",
                    )
                )

            # --- SoC from hand ---
            elif isinstance(eff, StartOfCombatFromHand):
                triggers.append(
                    TriggerDef(
                        event_type=EventType.START_OF_COMBAT,
                        condition=lambda ctx, event, ref: True,
                        effect=_make_soc_from_hand(),
                        name=f"{card.name} SoC",
                    )
                )

            # --- Start of Combat: buff self by tier ---
            elif isinstance(eff, StartOfCombatBuffSelfByTier):
                triggers.append(
                    TriggerDef(
                        event_type=EventType.START_OF_COMBAT,
                        condition=_is_friendly_soc,
                        effect=_make_start_of_combat_buff_self_by_tier(),
                        name=f"{card.name} SoC",
                    )
                )

            elif isinstance(eff, StartOfCombatBuffSelf):
                _soc_a, _soc_h = eff.atk, eff.hp
                def _make_soc_self(a=_soc_a, h=_soc_h):
                    def _fn(ctx, _ev, uid):
                        es = _event_system()
                        ctx.buff_combat(es.EntityRef(uid), a, h)
                    return _fn
                triggers.append(
                    TriggerDef(
                        event_type=EventType.START_OF_COMBAT,
                        condition=_is_friendly_soc,
                        effect=_make_soc_self(),
                        name=f"{card.name} SoC",
                    )
                )

            # --- On friendly death (excl. self): combat buff ---
            elif isinstance(eff, OnFriendlyDeathBuff):
                triggers.append(
                    TriggerDef(
                        event_type=EventType.MINION_DIED,
                        condition=_is_friendly_death_exclude_self,
                        effect=_make_on_friendly_death_buff(eff.atk, eff.hp),
                        name=f"{card.name} Buff",
                    )
                )

            # --- On friendly play of type: damage hero + buff self ---
            elif isinstance(eff, OnFriendlyPlayTypeDamageHero):
                triggers.append(
                    TriggerDef(
                        event_type=EventType.MINION_PLAYED,
                        condition=lambda ctx, event, ref: True,
                        effect=_make_on_play_type_damage_hero(
                            eff.trigger_type, eff.hero_dmg, eff.atk, eff.hp, eff.exclude_self
                        ),
                        name=f"{card.name} Trigger",
                    )
                )

            # --- On friendly play of type: buff self ---
            elif isinstance(eff, OnFriendlyPlayType):
                triggers.append(
                    TriggerDef(
                        event_type=EventType.MINION_PLAYED,
                        condition=lambda ctx, event, ref: True,
                        effect=_make_on_play_type_buff(
                            eff.trigger_type, eff.atk, eff.hp, eff.exclude_self
                        ),
                        name=f"{card.name} Trigger",
                    )
                )

            # --- Deathrattle: buff all friendlies ---
            elif isinstance(eff, DeathrattleBuffAllFriendlies):
                triggers.append(
                    TriggerDef(
                        event_type=EventType.MINION_DIED,
                        condition=lambda ctx, e, uid: bool(e.source and e.source.uid == uid),
                        effect=_make_dr_buff_all_friendlies(eff.atk, eff.hp),
                        name=f"{card.name} DR",
                    )
                )

            # --- Deathrattle: deal damage to random enemy ---
            elif isinstance(eff, DeathrattleRandomEnemyDamage):
                triggers.append(
                    TriggerDef(
                        event_type=EventType.MINION_DIED,
                        condition=lambda ctx, e, uid: bool(e.source and e.source.uid == uid),
                        effect=_make_dr_random_enemy_damage(eff.damage),
                        name=f"{card.name} DR",
                    )
                )

            # --- On friendly summoned of type: buff self + divine shield ---
            elif isinstance(eff, OnFriendlySummonedTypeBuff):
                triggers.append(
                    TriggerDef(
                        event_type=EventType.MINION_SUMMONED,
                        condition=_make_deflect_o_bot_condition(),
                        effect=_make_on_friendly_summoned_type_buff(
                            eff.trigger_type,
                            eff.atk,
                            eff.hp,
                            eff.exclude_self,
                            eff.combat_buff,
                            eff.gain_divine_shield,
                        ),
                        name=f"{card.name} Trigger",
                    )
                )

            # --- End of turn: add spell to hand ---
            elif isinstance(eff, EndOfTurnAddSpell):
                triggers.append(
                    TriggerDef(
                        event_type=EventType.END_OF_TURN,
                        condition=_is_friendly_soc,  # unit must be on board
                        effect=_make_end_of_turn_add_spell(eff.spell_id, eff.count),
                        name=f"{card.name} End of Turn",
                    )
                )

            # --- End of turn: buff adjacent units ---
            elif isinstance(eff, EndOfTurnBuffAdjacent):
                triggers.append(
                    TriggerDef(
                        event_type=EventType.END_OF_TURN,
                        condition=_is_friendly_soc,
                        effect=_make_eot_buff_adjacent(eff.atk, eff.hp),
                        name=f"{card.name} End of Turn",
                    )
                )

            # --- End of turn: buff self ---
            elif isinstance(eff, EndOfTurnBuffSelf):
                triggers.append(
                    TriggerDef(
                        event_type=EventType.END_OF_TURN,
                        condition=_is_friendly_soc,
                        effect=_make_eot_buff_self(eff.atk, eff.hp),
                        name=f"{card.name} End of Turn",
                    )
                )

            # --- End of turn: buff all board units ---
            elif isinstance(eff, EndOfTurnBuffBoard):
                triggers.append(
                    TriggerDef(
                        event_type=EventType.END_OF_TURN,
                        condition=_is_friendly_soc,
                        effect=_make_eot_buff_board(eff.atk, eff.hp),
                        name=f"{card.name} End of Turn",
                    )
                )

            # --- End of turn: buff all board units of type ---
            elif isinstance(eff, EndOfTurnBuffBoardByType):
                triggers.append(
                    TriggerDef(
                        event_type=EventType.END_OF_TURN,
                        condition=_is_friendly_soc,
                        effect=_make_eot_buff_board_by_type(eff.trigger_type, eff.atk, eff.hp),
                        name=f"{card.name} End of Turn",
                    )
                )

            # --- SoC: buff all friendly of type (combat) ---
            elif isinstance(eff, StartOfCombatBuffFriendlyType):
                triggers.append(
                    TriggerDef(
                        event_type=EventType.START_OF_COMBAT,
                        condition=_is_friendly_soc,
                        effect=_make_soc_buff_friendly_type(eff.trigger_type, eff.atk, eff.hp),
                        name=f"{card.name} SoC",
                    )
                )

            # --- BC: buff all friendly of type (perm) ---
            elif isinstance(eff, BattlecryBuffAllByType):
                triggers.append(
                    TriggerDef(
                        event_type=EventType.MINION_PLAYED,
                        condition=_is_self_play,
                        effect=_make_bc_buff_all_by_type(eff.trigger_type, eff.atk, eff.hp),
                        name=f"{card.name} Battlecry",
                        priority=10,
                    )
                )

            # --- On friendly play of type: add spell to hand ---
            elif isinstance(eff, OnFriendlyPlayTypeAddSpell):
                triggers.append(
                    TriggerDef(
                        event_type=EventType.MINION_PLAYED,
                        condition=lambda ctx, event, ref: True,
                        effect=_make_on_play_type_add_spell(
                            eff.trigger_type, eff.spell_id, eff.count, eff.exclude_self
                        ),
                        name=f"{card.name} Trigger",
                    )
                )

            # --- On friendly summoned of type: buff random other ---
            elif isinstance(eff, OnSummonedTypeBuffRandomOther):
                triggers.append(
                    TriggerDef(
                        event_type=EventType.MINION_SUMMONED,
                        condition=lambda ctx, event, ref: True,
                        effect=_make_on_summoned_buff_random_other(
                            eff.trigger_type, eff.atk, eff.hp
                        ),
                        name=f"{card.name} Trigger",
                    )
                )

            # --- Sell: add unit to hand ---
            elif isinstance(eff, SellAddUnit):
                triggers.append(
                    TriggerDef(
                        event_type=EventType.MINION_SOLD,
                        condition=_is_self_play,
                        effect=_make_sell_add_unit_v2(eff.card_id),
                        name=f"{card.name} Sell",
                    )
                )

            # --- Rally: buff random other friendly of type (combat) ---
            elif isinstance(eff, RallyBuffRandomFriendlyType):
                triggers.append(
                    TriggerDef(
                        event_type=EventType.ATTACK_DECLARED,
                        condition=_is_self_play,
                        effect=_make_rally_buff_random_type(eff.trigger_type, eff.atk, eff.hp),
                        name=f"{card.name} Rally",
                    )
                )

            # --- Sell: get random unit of type from pool ---
            elif isinstance(eff, SellGetRandomUnitByType):
                triggers.append(
                    TriggerDef(
                        event_type=EventType.MINION_SOLD,
                        condition=_is_self_play,
                        effect=_make_sell_get_random_by_type(eff.unit_type),
                        name=f"{card.name} Sell",
                    )
                )

            # --- BC: consume shop unit, give stats to random friendly of type ---
            elif isinstance(eff, ConsumeShopUnitForRandomFriendly):
                triggers.append(
                    TriggerDef(
                        event_type=EventType.MINION_PLAYED,
                        condition=_is_self_play,
                        effect=_make_consume_for_random_friendly(eff.trigger_type),
                        name=f"{card.name} Battlecry",
                        priority=10,
                    )
                )

            # --- After tavern refreshed: buff rightmost shop minion ---
            elif isinstance(eff, OnTavernRefreshBuffRightmostShop):
                triggers.append(
                    TriggerDef(
                        event_type=EventType.TAVERN_REFRESHED,
                        condition=_make_on_tavern_refresh_buff_rightmost_shop_condition(),
                        effect=_make_on_tavern_refresh_buff_rightmost_shop(
                            eff.atk, eff.hp, eff.give_reborn, eff.use_blood_gem
                        ),
                        name=f"{card.name} Tavern Refresh",
                    )
                )

            # --- Sell: buff board scaling ---
            elif isinstance(eff, SellBuffBoardScaling):
                triggers.append(
                    TriggerDef(
                        event_type=EventType.MINION_SOLD,
                        condition=_is_self_play,
                        effect=_make_sell_buff_board_scaling(
                            eff.scaling_key, eff.atk_per, eff.hp_per
                        ),
                        name=f"{card.name} Sell",
                    )
                )

            # --- SoC: damage and buff adjacent ---
            elif isinstance(eff, StartOfCombatDamageAndBuffAdjacent):
                triggers.append(
                    TriggerDef(
                        event_type=EventType.START_OF_COMBAT,
                        condition=_is_friendly_soc,
                        effect=_make_soc_damage_and_buff_adjacent(eff.damage, eff.atk, eff.hp),
                        name=f"{card.name} SoC",
                    )
                )

            # --- On hero damaged: heal and buff self ---
            elif isinstance(eff, OnHeroDamagedHealAndBuffSelf):
                triggers.append(
                    TriggerDef(
                        event_type=EventType.HERO_DAMAGED,
                        condition=lambda ctx, event, ref: True,
                        effect=_make_on_hero_damaged_heal_and_buff_self(eff.hp),
                        name=f"{card.name} Trigger",
                    )
                )

            # --- EOT: buff adjacent per golden ---
            elif isinstance(eff, EndOfTurnBuffAdjacentPerGolden):
                triggers.append(
                    TriggerDef(
                        event_type=EventType.END_OF_TURN,
                        condition=_is_friendly_soc,
                        effect=_make_eot_buff_adjacent_per_golden(eff.atk, eff.hp),
                        name=f"{card.name} End of Turn",
                    )
                )

            # --- Sell: discover ---
            elif isinstance(eff, SellDiscover):
                triggers.append(
                    TriggerDef(
                        event_type=EventType.MINION_SOLD,
                        condition=_is_self_play,
                        effect=_make_sell_discover(eff.base_tier, eff.scaling_key),
                        name=f"{card.name} Sell",
                    )
                )

            # --- Deathrattle: add spell to hand ---
            elif isinstance(eff, DeathrattleAddSpell):
                triggers.append(
                    TriggerDef(
                        event_type=EventType.MINION_DIED,
                        condition=_is_self_death,
                        effect=_make_dr_add_spell(eff.spell_id, eff.count),
                        name=f"{card.name} Deathrattle",
                    )
                )

            # --- Rally: add spell to hand ---
            elif isinstance(eff, RallyAddSpell):
                triggers.append(
                    TriggerDef(
                        event_type=EventType.ATTACK_DECLARED,
                        condition=_is_self_play,
                        effect=_make_rally_add_spell(eff.spell_id, eff.count),
                        name=f"{card.name} Rally",
                    )
                )

            # --- EOT: buff self per golden ---
            elif isinstance(eff, EndOfTurnBuffSelfPerGolden):
                triggers.append(
                    TriggerDef(
                        event_type=EventType.END_OF_TURN,
                        condition=_is_friendly_soc,
                        effect=_make_eot_buff_self_per_golden(eff.atk_per, eff.hp_per),
                        name=f"{card.name} End of Turn",
                    )
                )

            # --- On Divine Shield lost: add spell ---
            elif isinstance(eff, OnDivineShieldLostAddSpell):
                triggers.append(
                    TriggerDef(
                        event_type=EventType.DIVINE_SHIELD_LOST,
                        condition=lambda ctx, event, ref: True,
                        effect=_make_on_divine_shield_lost_add_spell(eff.spell_id, eff.count),
                        name=f"{card.name} Trigger",
                    )
                )

            # --- BC: buff all of type in hand and board ---
            elif isinstance(eff, BattlecryBuffAllByTypeIncludeHand):
                triggers.append(
                    TriggerDef(
                        event_type=EventType.MINION_PLAYED,
                        condition=_is_self_play,
                        effect=_make_bc_buff_all_by_type_include_hand(
                            eff.trigger_type, eff.atk, eff.hp
                        ),
                        name=f"{card.name} Battlecry",
                        priority=10,
                    )
                )

            # --- Rally: damage own board ---
            elif isinstance(eff, RallyDamageOwnBoard):
                triggers.append(
                    TriggerDef(
                        event_type=EventType.ATTACK_DECLARED,
                        condition=_is_self_play,
                        effect=_make_rally_damage_own_board(eff.damage),
                        name=f"{card.name} Rally",
                    )
                )

            # --- Deathrattle: modify mechanic ---
            elif isinstance(eff, DeathrattleModifyMechanic):
                triggers.append(
                    TriggerDef(
                        event_type=EventType.MINION_DIED,
                        condition=_is_self_death,
                        effect=_make_dr_modify_mechanic(eff.mechanic, eff.atk, eff.hp),
                        name=f"{card.name} Deathrattle",
                    )
                )

            # --- SoC: buff random friendly of type + divine shield ---
            elif isinstance(eff, StartOfCombatBuffRandomFriendlyTypeAndDS):
                triggers.append(
                    TriggerDef(
                        event_type=EventType.START_OF_COMBAT,
                        condition=_is_friendly_soc,
                        effect=_make_soc_buff_random_friendly_type_and_ds(
                            eff.trigger_type, eff.atk, eff.hp
                        ),
                        name=f"{card.name} SoC",
                    )
                )

            # --- On self damaged: buff board ---
            elif isinstance(eff, OnSelfDamagedBuffBoard):
                triggers.append(
                    TriggerDef(
                        event_type=EventType.MINION_DAMAGED,
                        condition=lambda ctx, event, ref: (
                            event.target is not None and event.target.uid == ref
                        ),
                        effect=_make_on_self_damaged_buff_board(eff.atk, eff.hp),
                        name=f"{card.name} Trigger",
                    )
                )

            # --- On friendly reborn: buff self ---
            elif isinstance(eff, OnFriendlyRebornBuffSelf):
                triggers.append(
                    TriggerDef(
                        event_type=EventType.MINION_SUMMONED,
                        condition=lambda ctx, event, ref: True,
                        effect=_make_on_friendly_reborn_buff_self(eff.atk, eff.hp),
                        name=f"{card.name} Trigger",
                    )
                )

            # --- Deathrattle: buff all friendly of type globally (hand+board) ---
            elif isinstance(eff, DeathrattleBuffFriendlyTypeGlobal):
                triggers.append(
                    TriggerDef(
                        event_type=EventType.MINION_DIED,
                        condition=_is_self_death,
                        effect=_make_dr_buff_friendly_type_global(
                            eff.trigger_type, eff.atk, eff.hp
                        ),
                        name=f"{card.name} Deathrattle",
                    )
                )

            # --- Deathrattle: buff shop minions ---
            elif isinstance(eff, DeathrattleBuffShop):
                triggers.append(
                    TriggerDef(
                        event_type=EventType.MINION_DIED,
                        condition=_is_self_death,
                        effect=_make_dr_buff_shop(eff.atk, eff.hp),
                        name=f"{card.name} Deathrattle",
                    )
                )

            # --- Deathrattle: buff random hand minion ---
            elif isinstance(eff, DeathrattleBuffHandRandom):
                triggers.append(
                    TriggerDef(
                        event_type=EventType.MINION_DIED,
                        condition=_is_self_death,
                        effect=_make_dr_buff_hand_random(eff.atk, eff.hp),
                        name=f"{card.name} Deathrattle",
                    )
                )

            # --- On friendly attack: buff the attacker (Roaring Recruiter) ---
            elif isinstance(eff, OnFriendlyAttackBuffSelf):
                triggers.append(
                    TriggerDef(
                        event_type=EventType.ATTACK_DECLARED,
                        condition=lambda ctx, event, ref: True,
                        effect=_make_on_friendly_attack_buff_attacker(
                            eff.trigger_type, eff.atk, eff.hp
                        ),
                        name=f"{card.name} Trigger",
                    )
                )

            # --- On friendly attack: buff self/trigger unit (Twilight Watcher) ---
            elif isinstance(eff, OnFriendlyAttackBuffTriggerSelf):
                triggers.append(
                    TriggerDef(
                        event_type=EventType.ATTACK_DECLARED,
                        condition=lambda ctx, event, ref: True,
                        effect=_make_on_friendly_attack_buff_trigger(
                            eff.trigger_type, eff.atk, eff.hp
                        ),
                        name=f"{card.name} Trigger",
                    )
                )

            # --- While in hand, on friendly play of type: buff self (Bream Counter) ---
            elif isinstance(eff, OnFriendlyPlayTypeBuffSelfInHand):
                triggers.append(
                    TriggerDef(
                        event_type=EventType.MINION_PLAYED,
                        condition=lambda ctx, event, ref: True,
                        effect=_make_on_friendly_play_type_buff_self_in_hand(
                            eff.trigger_type, eff.atk, eff.hp
                        ),
                        name=f"{card.name} Trigger",
                    )
                )

            # --- On spell cast: buff self (Glad-iator, Timecap'n Hooktail) ---
            elif isinstance(eff, OnSpellCastBuffSelf):
                triggers.append(
                    TriggerDef(
                        event_type=EventType.SPELL_CAST,
                        condition=lambda ctx, event, ref: True,
                        effect=_make_on_spell_cast_buff_self(eff.atk, eff.hp),
                        name=f"{card.name} Trigger",
                    )
                )

            # --- On gain gold (spell cast with GAIN_GOLD): buff self ---
            elif isinstance(eff, OnGainGoldBuffSelf):
                triggers.append(
                    TriggerDef(
                        event_type=EventType.SPELL_CAST,
                        condition=lambda ctx, event, ref: True,
                        effect=_make_on_gain_gold_buff_self(eff.atk, eff.hp),
                        name=f"{card.name} Trigger",
                    )
                )

            # --- Deathrattle: damage all minions (Tunnel Blaster, Silent Enforcer) ---
            elif isinstance(eff, DeathrattleDamageAllMinions):
                triggers.append(
                    TriggerDef(
                        event_type=EventType.MINION_DIED,
                        condition=_is_self_death,
                        effect=_make_dr_damage_all_minions(eff.damage),
                        name=f"{card.name} Deathrattle",
                    )
                )

            # --- SoC: permanently buff all friendly of type (Prized Promo-Drake) ---
            elif isinstance(eff, StartOfCombatBuffAllFriendlyType):
                triggers.append(
                    TriggerDef(
                        event_type=EventType.START_OF_COMBAT,
                        condition=_is_friendly_soc,
                        effect=_make_soc_buff_all_friendly_type(eff.trigger_type, eff.atk, eff.hp),
                        name=f"{card.name} SoC",
                    )
                )

            # --- SoC: give random friendly of type Reborn (Soulsplitter) ---
            elif isinstance(eff, StartOfCombatGiveFriendlyTypeReborn):
                triggers.append(
                    TriggerDef(
                        event_type=EventType.START_OF_COMBAT,
                        condition=_is_friendly_soc,
                        effect=_make_soc_give_friendly_type_reborn(eff.trigger_type),
                        name=f"{card.name} SoC",
                    )
                )

            # --- BC: add random unit of type to hand (Tavern Tempest) ---
            elif isinstance(eff, BattlecryAddRandomUnit):
                triggers.append(
                    TriggerDef(
                        event_type=EventType.MINION_PLAYED,
                        condition=_is_self_play,
                        effect=_make_bc_add_random_unit(eff.unit_type, eff.tier),
                        name=f"{card.name} Battlecry",
                        priority=10,
                    )
                )

            # --- BC: gain free refreshes (Refreshing Anomaly) ---
            elif isinstance(eff, BattlecryGainFreeRefreshes):
                triggers.append(
                    TriggerDef(
                        event_type=EventType.MINION_PLAYED,
                        condition=_is_self_play,
                        effect=_make_bc_gain_free_refreshes(eff.count),
                        name=f"{card.name} Battlecry",
                        priority=10,
                    )
                )

            # --- On DS lost: buff the unit that lost it (Grease Bot) ---
            elif isinstance(eff, OnDivineShieldLostBuffUnit):
                triggers.append(
                    TriggerDef(
                        event_type=EventType.DIVINE_SHIELD_LOST,
                        condition=lambda ctx, event, ref: True,
                        effect=_make_on_ds_lost_buff_unit(eff.atk, eff.hp),
                        name=f"{card.name} Trigger",
                    )
                )

            # --- Rally: play blood gems on all other friendlies (Bonker) ---
            elif isinstance(eff, RallyBuffAllOthersByType):
                triggers.append(
                    TriggerDef(
                        event_type=EventType.ATTACK_DECLARED,
                        condition=_is_self_play,
                        effect=_make_rally_buff_all_others_blood_gems(eff.count),
                        name=f"{card.name} Rally",
                    )
                )

            # --- EOT: add random spell to hand (Marquee Ticker) ---
            elif isinstance(eff, EndOfTurnAddRandomSpell):
                triggers.append(
                    TriggerDef(
                        event_type=EventType.END_OF_TURN,
                        condition=_is_friendly_soc,
                        effect=_make_eot_add_random_spell(),
                        name=f"{card.name} End of Turn",
                    )
                )

            # --- StartOfCombatGainGold: handled as EOT gold (Accord-o-Tron, Industrious Deckhand) ---
            elif isinstance(eff, StartOfCombatGainGold):
                triggers.append(
                    TriggerDef(
                        event_type=EventType.END_OF_TURN,
                        condition=_is_friendly_soc,
                        effect=_make_battlecry_gain_gold(eff.amount),
                        name=f"{card.name} End of Turn",
                    )
                )

            # --- AvengeEffect: extended targets (add_spell, add_unit) ---
            elif isinstance(eff, AvengeEffect) and eff.buff_target in ("add_spell", "add_unit"):
                # These are handled in the avenge system via AVENGE_REGISTRY
                # but we also need to register them so they fire.
                # The avenge system in combat.py reads AVENGE_REGISTRY for threshold.
                pass  # handled by avenge system reading AvengeEffect from registry

            # --- AvengeBuffFriendlyTypeGlobal ---
            elif isinstance(eff, AvengeBuffFriendlyTypeGlobal):
                pass  # handled by avenge system; effect fired via avenge_registry

            # --- OnSpellCastBuffBoard (Plankwalker, Sundered Matriarch) ---
            elif isinstance(eff, OnSpellCastBuffBoard):
                triggers.append(
                    TriggerDef(
                        event_type=EventType.SPELL_CAST,
                        condition=lambda ctx, event, ref: True,
                        effect=_make_on_spell_cast_buff_board(eff.atk, eff.hp, eff.trigger_type),
                        name=f"{card.name} Trigger",
                    )
                )

            # --- DeathrattleSummonTauntToken (Twilight Broodmother) ---
            elif isinstance(eff, DeathrattleSummonTauntToken):
                triggers.append(
                    TriggerDef(
                        event_type=EventType.MINION_DIED,
                        condition=_is_self_death,
                        effect=_make_dr_summon_taunt_token(eff.token_id, eff.count),
                        name=f"{card.name} Deathrattle",
                    )
                )

            # --- StartOfCombatBuffSelfByHighestAllyAtk (Costume Enthusiast) ---
            elif isinstance(eff, StartOfCombatBuffSelfByHighestAllyAtk):
                triggers.append(
                    TriggerDef(
                        event_type=EventType.START_OF_COMBAT,
                        condition=_is_friendly_soc,
                        effect=_make_soc_buff_self_by_highest_ally_atk(),
                        name=f"{card.name} SoC",
                    )
                )

            # --- StartOfCombatBuffSelfByHighestBoardAtk (Psychus) ---
            elif isinstance(eff, StartOfCombatBuffSelfByHighestBoardAtk):
                triggers.append(
                    TriggerDef(
                        event_type=EventType.START_OF_COMBAT,
                        condition=_is_friendly_soc,
                        effect=_make_soc_buff_self_by_highest_board_atk(),
                        name=f"{card.name} SoC",
                    )
                )

            # --- BattlecryMakeGoldenFriendlyByTier (Elite Navigator, Captain Sanders) ---
            elif isinstance(eff, BattlecryMakeGoldenFriendlyByTier):
                triggers.append(
                    TriggerDef(
                        event_type=EventType.MINION_PLAYED,
                        condition=_is_self_play,
                        effect=_make_bc_make_golden_friendly_by_tier(eff.max_tier),
                        name=f"{card.name} Battlecry",
                        priority=10,
                    )
                )

            # --- RallyBuffFriendlyTypeAtk (Sunken Advocate) ---
            elif isinstance(eff, RallyBuffFriendlyTypeAtk):
                triggers.append(
                    TriggerDef(
                        event_type=EventType.ATTACK_DECLARED,
                        condition=_is_self_play,
                        effect=_make_rally_buff_friendly_type_atk(eff.trigger_type, eff.atk),
                        name=f"{card.name} Rally",
                    )
                )

            # --- OnFriendlyBeastDamagedBuffSelf (Trigore the Lasher) ---
            elif isinstance(eff, OnFriendlyBeastDamagedBuffSelf):
                triggers.append(
                    TriggerDef(
                        event_type=EventType.MINION_DAMAGED,
                        condition=lambda ctx, event, ref: True,
                        effect=_make_on_friendly_beast_damaged_buff_self(eff.hp),
                        name=f"{card.name} Trigger",
                    )
                )

            # --- OnFriendlyBeastDamagedBuffOther (Iridescent Skyblazer) ---
            elif isinstance(eff, OnFriendlyBeastDamagedBuffOther):
                triggers.append(
                    TriggerDef(
                        event_type=EventType.MINION_DAMAGED,
                        condition=lambda ctx, event, ref: True,
                        effect=_make_on_friendly_beast_damaged_buff_other(eff.atk, eff.hp),
                        name=f"{card.name} Trigger",
                    )
                )

            # --- DeathrattleDestroyKiller (Leeroy the Reckless) ---
            elif isinstance(eff, DeathrattleDestroyKiller):
                triggers.append(
                    TriggerDef(
                        event_type=EventType.MINION_DIED,
                        condition=_is_self_death,
                        effect=_make_dr_destroy_killer(),
                        name=f"{card.name} Deathrattle",
                    )
                )

            # --- SellForGoldConditional (Tortollan Blue Shell) ---
            elif isinstance(eff, SellForGoldConditional):
                triggers.append(
                    TriggerDef(
                        event_type=EventType.MINION_SOLD,
                        condition=_is_self_play,
                        effect=_make_sell_for_gold_conditional(eff.amount),
                        name=f"{card.name} Sell",
                    )
                )

            # --- DeathrattleBuffAllFriendliesGlobal (Goldrinn) ---
            elif isinstance(eff, DeathrattleBuffAllFriendliesGlobal):
                triggers.append(
                    TriggerDef(
                        event_type=EventType.MINION_DIED,
                        condition=_is_self_death,
                        effect=_make_dr_buff_all_friendlies_global(
                            eff.trigger_type, eff.atk, eff.hp
                        ),
                        name=f"{card.name} Deathrattle",
                    )
                )

            # --- EndOfTurnBuffFriendlyTypeNaga (Slitherspear) ---
            elif isinstance(eff, EndOfTurnBuffFriendlyTypeNaga):
                triggers.append(
                    TriggerDef(
                        event_type=EventType.END_OF_TURN,
                        condition=_is_friendly_soc,
                        effect=_make_eot_buff_friendly_type_naga(eff.atk, eff.hp),
                        name=f"{card.name} End of Turn",
                    )
                )

            # --- OnFriendlyDemonDamageBuff (Lord of the Ruins) ---
            elif isinstance(eff, OnFriendlyDemonDamageBuff):
                triggers.append(
                    TriggerDef(
                        event_type=EventType.DAMAGE_DEALT,
                        condition=lambda ctx, event, ref: True,
                        effect=_make_on_friendly_demon_damage_buff(eff.atk, eff.hp),
                        name=f"{card.name} Trigger",
                    )
                )

            # --- EndOfTurnConsumeTavernForDemon (Famished Felbat) ---
            elif isinstance(eff, EndOfTurnConsumeTavernForDemon):
                triggers.append(
                    TriggerDef(
                        event_type=EventType.END_OF_TURN,
                        condition=_is_friendly_soc,
                        effect=_make_eot_consume_tavern_for_demon(),
                        name=f"{card.name} End of Turn",
                    )
                )

            # --- StartOfCombatBuffFriendlyTypeScaling (Ultraviolet Ascendant) ---
            elif isinstance(eff, StartOfCombatBuffFriendlyTypeScaling):
                triggers.append(
                    TriggerDef(
                        event_type=EventType.START_OF_COMBAT,
                        condition=_is_friendly_soc,
                        effect=_make_soc_buff_friendly_type_scaling(
                            eff.trigger_type, eff.atk, eff.hp
                        ),
                        name=f"{card.name} SoC",
                    )
                )

            # --- EndOfTurnTriggerAdjacentBattlecry (Young Murk-Eye) ---
            elif isinstance(eff, EndOfTurnTriggerAdjacentBattlecry):
                triggers.append(
                    TriggerDef(
                        event_type=EventType.END_OF_TURN,
                        condition=_is_friendly_soc,
                        effect=_make_eot_trigger_adjacent_battlecry(),
                        name=f"{card.name} End of Turn",
                    )
                )

            # --- RallyDealDamageEqualToAtk (Niuzao, Obsidian Ravager) ---
            elif isinstance(eff, RallyDealDamageEqualToAtk):
                triggers.append(
                    TriggerDef(
                        event_type=EventType.ATTACK_DECLARED,
                        condition=_is_self_play,
                        effect=_make_rally_deal_damage_equal_to_atk(),
                        name=f"{card.name} Rally",
                    )
                )

            # --- DeathrattleGiveFriendliesScaling (Spiked Savior) ---
            elif isinstance(eff, DeathrattleGiveFriendliesScaling):
                triggers.append(
                    TriggerDef(
                        event_type=EventType.MINION_DIED,
                        condition=_is_self_death,
                        effect=_make_dr_give_friendlies_scaling(
                            eff.buff_atk, eff.buff_hp, eff.self_damage
                        ),
                        name=f"{card.name} Deathrattle",
                    )
                )

            # --- B2: BattlecryBuffAllByTypeIncludeHand (Ancestral Automaton) ---
            elif isinstance(eff, BattlecryBuffAllByTypeIncludeHand):
                triggers.append(
                    TriggerDef(
                        event_type=EventType.MINION_PLAYED,
                        condition=_is_self_play,
                        effect=_make_bc_buff_all_by_type_include_hand(
                            eff.trigger_type, eff.atk, eff.hp
                        ),
                        name=f"{card.name} Battlecry",
                    )
                )

            # --- B2: OnSpellCastOnSelfBuffSelf (Fleeing Fugitive, Lava Lurker,
            # Mini-Myrmidon, Thaumaturgist, Abyssal Bruiser, Cagey Conjurer,
            # Rimescale Priestess, Darkcrest Strategist, Glowscale,
            # Tranquil Meditative) ---
            elif isinstance(eff, OnSpellCastOnSelfBuffSelf):
                triggers.append(
                    TriggerDef(
                        event_type=EventType.SPELL_CAST,
                        condition=_is_self_on_board,
                        effect=_make_on_spell_cast_on_self_buff_self(eff.atk, eff.hp),
                        name=f"{card.name} OnSpellCast",
                    )
                )

            # --- B2: OnSpellCastScalingBuffSelf (Thaumaturgist, Groundbreaker,
            # Showy Cyclist) ---
            elif isinstance(eff, OnSpellCastScalingBuffSelf):
                triggers.append(
                    TriggerDef(
                        event_type=EventType.SPELL_CAST,
                        condition=_is_self_on_board,
                        effect=_make_on_spell_cast_scaling_buff_self(
                            eff.per_n, eff.atk, eff.hp
                        ),
                        name=f"{card.name} OnSpellCastScaling",
                    )
                )

            # --- B2: OnSpellCastRecastRandomTavernSpell (Vigilant Bristlemane) ---
            elif isinstance(eff, OnSpellCastRecastRandomTavernSpell):
                triggers.append(
                    TriggerDef(
                        event_type=EventType.SPELL_CAST,
                        condition=_is_self_on_board,
                        effect=_make_on_spell_cast_recast_random_tavern_spell(),
                        name=f"{card.name} OnSpellCastRecast",
                    )
                )

            # --- B2: OtherSummonScalingAura (Glowing Cinder) ---
            elif isinstance(eff, OtherSummonScalingAura):
                triggers.append(
                    TriggerDef(
                        event_type=EventType.MINION_SUMMONED,
                        condition=_is_self_on_board,
                        effect=_make_other_summon_scaling_aura(
                            eff.trigger_type, eff.atk, eff.hp
                        ),
                        name=f"{card.name} SummonAura",
                    )
                )

            # --- B2: StartOfCombatBuffLeftmostTypeWindfury (Waverider) ---
            elif isinstance(eff, StartOfCombatBuffLeftmostTypeWindfury):
                triggers.append(
                    TriggerDef(
                        event_type=EventType.START_OF_COMBAT,
                        condition=_is_self_on_board,
                        effect=_make_soc_buff_leftmost_type_windfury(
                            eff.trigger_type, eff.atk, eff.hp
                        ),
                        name=f"{card.name} SoCLeftmostWindfury",
                    )
                )

            # --- B2: KeepFirstSpellcraftPerTurn (Seafloor Recruiter) ---
            elif isinstance(eff, KeepFirstSpellcraftPerTurn):
                triggers.append(
                    TriggerDef(
                        event_type=EventType.SPELL_CAST,
                        condition=_is_self_on_board,
                        effect=_make_keep_first_spellcraft_per_turn(eff.atk, eff.hp),
                        name=f"{card.name} KeepSpellcraft",
                    )
                )

            # --- B2: ActivateGetRandomUnit (Auto Assembler) ---
            elif isinstance(eff, ActivateGetRandomUnit):
                triggers.append(
                    TriggerDef(
                        event_type=EventType.END_OF_TURN,
                        condition=_is_self_on_board,
                        effect=_make_activate_get_random_unit(eff.cost, eff.unit_type),
                        name=f"{card.name} Activate",
                    )
                )

            # --- B2: ActivateGainGoldNextTurn (Moat Custodian) ---
            elif isinstance(eff, ActivateGainGoldNextTurn):
                triggers.append(
                    TriggerDef(
                        event_type=EventType.END_OF_TURN,
                        condition=_is_self_on_board,
                        effect=_make_activate_gain_gold_next_turn(eff.cost, eff.gold),
                        name=f"{card.name} Activate",
                    )
                )

            # --- B2: ActivateCastRandomSpells (Unleashed Mana Surge) ---
            elif isinstance(eff, ActivateCastRandomSpells):
                triggers.append(
                    TriggerDef(
                        event_type=EventType.END_OF_TURN,
                        condition=_is_self_on_board,
                        effect=_make_activate_cast_random_spells(eff.cost, eff.count),
                        name=f"{card.name} Activate",
                    )
                )

            # --- B2: OnSelfAttackBuffFriendlyTypeGlobal (Dancing Barnstormer) ---
            elif isinstance(eff, OnSelfAttackBuffFriendlyTypeGlobal):
                triggers.append(
                    TriggerDef(
                        event_type=EventType.ATTACK_DECLARED,
                        condition=_is_self_play,
                        effect=_make_on_self_attack_buff_friendly_type_global(
                            eff.trigger_type, eff.atk, eff.hp
                        ),
                        name=f"{card.name} AttackAura",
                    )
                )

            # --- B2: BattlecryBuffOtherTypeScaling (Meteorite Crasher) ---
            elif isinstance(eff, BattlecryBuffOtherTypeScaling):
                triggers.append(
                    TriggerDef(
                        event_type=EventType.MINION_PLAYED,
                        condition=_is_self_play,
                        effect=_make_bc_buff_other_type_scaling(
                            eff.trigger_type,
                            eff.atk,
                            eff.hp,
                            eff.per_tier_atk,
                            eff.per_tier_hp,
                        ),
                        name=f"{card.name} Battlecry",
                    )
                )

            # --- B2: OnFriendlySellTypeBuffSelf (Sand Swirler, Zesty Shaker) ---
            elif isinstance(eff, OnFriendlySellTypeBuffSelf):
                triggers.append(
                    TriggerDef(
                        event_type=EventType.MINION_SOLD,
                        condition=_is_self_on_board,
                        effect=_make_on_friendly_sell_type_buff_self(
                            eff.trigger_type, eff.atk, eff.hp
                        ),
                        name=f"{card.name} SellTrigger",
                    )
                )

            # --- B2: BattlecryBuffShop (Breakout Mastermind, Private Investigator,
            # Papa Mrrglton) ---
            elif isinstance(eff, BattlecryBuffShop):
                triggers.append(
                    TriggerDef(
                        event_type=EventType.MINION_PLAYED,
                        condition=_is_self_play,
                        effect=_make_bc_buff_shop(eff.atk, eff.hp),
                        name=f"{card.name} Battlecry",
                    )
                )

            # --- B2: BattlecryDiscoverMechMagnetize (Clunker Junker) ---
            elif isinstance(eff, BattlecryDiscoverMechMagnetize):
                triggers.append(
                    TriggerDef(
                        event_type=EventType.MINION_PLAYED,
                        condition=_is_self_play,
                        effect=_make_bc_discover_mech_magnetize(),
                        name=f"{card.name} Battlecry",
                    )
                )

            # --- B2: DeathrattleBuffOneOfEachType (Motley Phalanx) ---
            elif isinstance(eff, DeathrattleBuffOneOfEachType):
                triggers.append(
                    TriggerDef(
                        event_type=EventType.MINION_DIED,
                        condition=_is_self_death,
                        effect=_make_dr_buff_one_of_each_type(eff.atk, eff.hp),
                        name=f"{card.name} Deathrattle",
                    )
                )

            # --- B2: RallyCastSpellOnRight (Deep-Sea Angler) ---
            elif isinstance(eff, RallyCastSpellOnRight):
                triggers.append(
                    TriggerDef(
                        event_type=EventType.ATTACK_DECLARED,
                        condition=_is_self_play,
                        effect=_make_rally_cast_spell_on_right(),
                        name=f"{card.name} Rally",
                    )
                )

            # --- B2: SpellcraftCastOnSelfAddCopyOncePerTurn (Showy Cyclist) ---
            elif isinstance(eff, SpellcraftCastOnSelfAddCopyOncePerTurn):
                triggers.append(
                    TriggerDef(
                        event_type=EventType.SPELL_CAST,
                        condition=_is_self_on_board,
                        effect=_make_spellcraft_cast_on_self_add_copy_once_per_turn(),
                        name=f"{card.name} SpellcraftCopy",
                    )
                )

            # --- B2: EndOfTurnAddRandomUnitFromList (Captain Cookie) ---
            elif isinstance(eff, EndOfTurnAddRandomUnitFromList):
                triggers.append(
                    TriggerDef(
                        event_type=EventType.END_OF_TURN,
                        condition=_is_self_on_board,
                        effect=_make_eot_add_random_unit_from_list(eff.unit_type),
                        name=f"{card.name} EoT",
                    )
                )

            # --- B2: BattlecryBuffShopMaxTier (Mama Mrrglton) ---
            elif isinstance(eff, BattlecryBuffShopMaxTier):
                triggers.append(
                    TriggerDef(
                        event_type=EventType.MINION_PLAYED,
                        condition=_is_self_play,
                        effect=_make_bc_buff_shop(eff.atk, eff.hp, eff.max_tier),
                        name=f"{card.name} Battlecry",
                    )
                )

            # --- B2: DeathrattleSummonFirstDeadMechs (Kangor's Apprentice) ---
            elif isinstance(eff, DeathrattleSummonFirstDeadMechs):
                triggers.append(
                    TriggerDef(
                        event_type=EventType.MINION_DIED,
                        condition=_is_self_death,
                        effect=_make_dr_summon_first_dead_mechs(eff.count),
                        name=f"{card.name} Deathrattle",
                    )
                )

            # --- B2: DeathrattleAddRandomMagneticUnit (Scrap Scraper) ---
            elif isinstance(eff, DeathrattleAddRandomMagneticUnit):
                triggers.append(
                    TriggerDef(
                        event_type=EventType.MINION_DIED,
                        condition=_is_self_death,
                        effect=_make_dr_add_random_magnetic_unit(),
                        name=f"{card.name} Deathrattle",
                    )
                )

            # --- B2: OnSpellCastOnSelfCastSpellOnAdjacent (Torrential Ruiner) ---
            elif isinstance(eff, OnSpellCastOnSelfCastSpellOnAdjacent):
                triggers.append(
                    TriggerDef(
                        event_type=EventType.SPELL_CAST,
                        condition=_is_self_on_board,
                        effect=_make_on_spellcast_on_self_cast_on_adjacent(),
                        name=f"{card.name} SpellcraftSplash",
                    )
                )

            # --- B2: OnSelfAttackModifyMechanic (Thousandth Paper Drake) ---
            elif isinstance(eff, OnSelfAttackModifyMechanic):
                triggers.append(
                    TriggerDef(
                        event_type=EventType.ATTACK_DECLARED,
                        condition=_is_self_play,
                        effect=_make_on_self_attack_modify_mechanic(
                            eff.mechanic, eff.atk, eff.hp
                        ),
                        name=f"{card.name} AttackBuff",
                    )
                )

            # --- B2: OnFriendlyPlayTypeBuffBoardType (Deepwater Chieftain) ---
            elif isinstance(eff, OnFriendlyPlayTypeBuffBoardType):
                triggers.append(
                    TriggerDef(
                        event_type=EventType.MINION_PLAYED,
                        condition=_is_self_on_board,
                        effect=_make_eot_buff_board_by_type_on_play(
                            eff.play_type, eff.buff_type, eff.atk, eff.hp
                        ),
                        name=f"{card.name} PlayBuff",
                    )
                )

            # --- B2: OnMrrgltonPlayedBuffSelf (Mama Mrrglton, Papa Mrrglton) ---
            elif isinstance(eff, OnMrrgltonPlayedBuffSelf):
                triggers.append(
                    TriggerDef(
                        event_type=EventType.MINION_PLAYED,
                        condition=_is_self_on_board,
                        effect=_make_on_mrrglton_played_buff_self(eff.atk, eff.hp),
                        name=f"{card.name} MrrgltonBuff",
                    )
                )

            # --- B2: ImmuneWhileAttacking (Warpwing) ---
            elif isinstance(eff, ImmuneWhileAttacking):
                triggers.append(
                    TriggerDef(
                        event_type=EventType.ATTACK_DECLARED,
                        condition=_is_self_play,
                        effect=_make_gain_immune(),
                        name=f"{card.name} ImmuneOn",
                    )
                )
                triggers.append(
                    TriggerDef(
                        event_type=EventType.AFTER_ATTACK,
                        condition=_is_self_play,
                        effect=_make_lose_immune(),
                        name=f"{card.name} ImmuneOff",
                    )
                )

            # --- B2: SpendGoldBuffType (Dual-Wield Corsair) ---
            elif isinstance(eff, SpendGoldBuffType):
                triggers.append(
                    TriggerDef(
                        event_type=EventType.END_OF_TURN,
                        condition=_is_self_on_board,
                        effect=_make_spend_gold_buff_type(
                            eff.trigger_type,
                            eff.gold_per,
                            eff.atk,
                            eff.hp,
                            eff.max_targets,
                        ),
                        name=f"{card.name} SpendGold",
                    )
                )

            # --- B2: DeathrattleBuffFriendlyTypeScaling (Void Pup Trainer) ---
            elif isinstance(eff, DeathrattleBuffFriendlyTypeScaling):
                triggers.append(
                    TriggerDef(
                        event_type=EventType.MINION_DIED,
                        condition=_is_self_death,
                        effect=_make_dr_buff_friendly_type_scaling(
                            eff.trigger_type,
                            eff.atk,
                            eff.hp,
                            eff.per_tier_atk,
                            eff.per_tier_hp,
                        ),
                        name=f"{card.name} Deathrattle",
                    )
                )

            # --- B2: OnFriendlyPlayTypeBuffSelfScaling (Cousin Errgl,
            # Sea Witch Zar'jira) ---
            elif isinstance(eff, OnFriendlyPlayTypeBuffSelfScaling):
                triggers.append(
                    TriggerDef(
                        event_type=EventType.MINION_PLAYED,
                        condition=_is_self_on_board,
                        effect=_make_on_friendly_play_type_buff_self_scaling(
                            eff.trigger_type, eff.atk, eff.hp
                        ),
                        name=f"{card.name} PlayBuff",
                    )
                )

            # --- B2: OnSpellCastOnTypeBuffBoard (Tranquil Meditative) ---
            elif isinstance(eff, OnSpellCastOnTypeBuffBoard):
                triggers.append(
                    TriggerDef(
                        event_type=EventType.SPELL_CAST,
                        condition=_is_self_on_board,
                        effect=_make_on_spell_cast_on_type_buff_board(
                            eff.trigger_type, eff.atk, eff.hp
                        ),
                        name=f"{card.name} OnSpellCast",
                    )
                )

            # --- B2: BattlecryDeathrattleBuffTavernType (Dancing Barnstormer) ---
            elif isinstance(eff, BattlecryDeathrattleBuffTavernType):
                triggers.append(
                    TriggerDef(
                        event_type=EventType.MINION_PLAYED,
                        condition=_is_self_play,
                        effect=_make_bc_dr_buff_tavern_type(
                            eff.trigger_type, eff.atk, eff.hp
                        ),
                        name=f"{card.name} Battlecry",
                        priority=10,
                    )
                )
                triggers.append(
                    TriggerDef(
                        event_type=EventType.MINION_DIED,
                        condition=_is_self_death,
                        effect=_make_bc_dr_buff_tavern_type(
                            eff.trigger_type, eff.atk, eff.hp
                        ),
                        name=f"{card.name} Deathrattle",
                    )
                )

            # --- B2: OnFriendlyPlayTypeBuffBoardTypeIncludeSelf
            # (Unleashed Mana Surge) ---
            elif isinstance(eff, OnFriendlyPlayTypeBuffBoardTypeIncludeSelf):
                triggers.append(
                    TriggerDef(
                        event_type=EventType.MINION_PLAYED,
                        condition=_is_self_on_board,
                        effect=_make_on_play_type_buff_board_include_self(
                            eff.play_type, eff.buff_type, eff.atk, eff.hp
                        ),
                        name=f"{card.name} PlayBuff",
                    )
                )

            # --- B2: OnSummonAutomatonBuffAutomatons (Ancestral Automaton) ---
            elif isinstance(eff, OnSummonAutomatonBuffAutomatons):
                triggers.append(
                    TriggerDef(
                        event_type=EventType.MINION_SUMMONED,
                        condition=_is_friendly_soc,
                        effect=_make_on_summon_automaton_buff(eff.atk, eff.hp),
                        name=f"{card.name} OnSummon",
                    )
                )

            # --- B2: EndOfTurnAddMrrglton (Cousin Errgl) ---
            elif isinstance(eff, EndOfTurnAddMrrglton):
                triggers.append(
                    TriggerDef(
                        event_type=EventType.END_OF_TURN,
                        condition=_is_friendly_soc,
                        effect=_make_eot_add_mrrglton(),
                        name=f"{card.name} End of Turn",
                    )
                )

            # --- B2: RallyModifyMechanic (Moat Custodian) ---
            elif isinstance(eff, RallyModifyMechanic):
                triggers.append(
                    TriggerDef(
                        event_type=EventType.ATTACK_DECLARED,
                        condition=_is_self_play,
                        effect=_make_rally_modify_mechanic(
                            eff.mechanic, eff.atk, eff.hp
                        ),
                        name=f"{card.name} Rally",
                    )
                )

            # --- B2: BattlecryBuffOtherType (Mama/Papa Mrrglton) ---
            elif isinstance(eff, BattlecryBuffOtherType):
                triggers.append(
                    TriggerDef(
                        event_type=EventType.MINION_PLAYED,
                        condition=_is_self_play,
                        effect=_make_bc_buff_other_type(
                            eff.trigger_type, eff.atk, eff.hp
                        ),
                        name=f"{card.name} Battlecry",
                        priority=10,
                    )
                )

            # --- B2: OnTavernSpellCastBuffSelf (Abyssal Bruiser) ---
            elif isinstance(eff, OnTavernSpellCastBuffSelf):
                triggers.append(
                    TriggerDef(
                        event_type=EventType.SPELL_CAST,
                        condition=_is_self_on_board,
                        effect=_make_on_tavern_spell_cast_buff_self(eff.atk, eff.hp),
                        name=f"{card.name} Trigger",
                    )
                )

            # --- B2: DeathrattleBuffFriendlyType (Showy Cyclist) ---
            elif isinstance(eff, DeathrattleBuffFriendlyType):
                triggers.append(
                    TriggerDef(
                        event_type=EventType.MINION_DIED,
                        condition=_is_self_death,
                        effect=_make_dr_buff_friendly_type(
                            eff.trigger_type, eff.atk, eff.hp
                        ),
                        name=f"{card.name} Deathrattle",
                    )
                )

            # --- B2: OnSpellCastOnNagaBuffBoard (Torrential Ruiner) ---
            elif isinstance(eff, OnSpellCastOnNagaBuffBoard):
                triggers.append(
                    TriggerDef(
                        event_type=EventType.SPELL_CAST,
                        condition=_is_self_on_board,
                        effect=_make_on_spell_cast_on_naga_buff_board(eff.atk, eff.hp),
                        name=f"{card.name} Trigger",
                    )
                )

            # --- B2: OnPlayNagaBuffSelf (Groundbreaker) ---
            elif isinstance(eff, OnPlayNagaBuffSelf):
                triggers.append(
                    TriggerDef(
                        event_type=EventType.MINION_PLAYED,
                        condition=_is_self_on_board,
                        effect=_make_on_play_naga_buff_self(eff.atk, eff.hp),
                        name=f"{card.name} Trigger",
                    )
                )

            # --- Pass-through for custom / hand-crafted triggers ---
            elif isinstance(eff, CustomEffect):
                # Felemental: BC gives +2/+1 to all current shop minions, and future ones via mechanic
                if card.card_id == CardIDs.FELEMENTAL:
                    triggers.append(
                        TriggerDef(
                            event_type=EventType.MINION_PLAYED,
                            condition=_is_self_play,
                            effect=_make_felemental_bc(),
                            name="Felemental Battlecry",
                            priority=10,
                        )
                    )
                else:
                    triggers.extend(eff.trigger_defs)

        if triggers:
            registry[card.card_id] = triggers

    # --- Crab Deathrattle (attached dynamically via Surf Spellcraft spell) ---
    def _summon_crab_token(ctx: EffectContext, event: Event, _trigger_uid: int) -> None:
        pos = event.source_pos or (event.snapshot.pos if event.snapshot else None)
        if pos:
            ctx.summon(pos.side, CardIDs.CRAB_TOKEN, pos.slot)

    registry[EffectIDs.CRAB_DEATHRATTLE] = [
        TriggerDef(
            event_type=EventType.MINION_DIED,
            condition=lambda ctx, event, trigger_uid: (
                event.source is not None and event.source.uid == trigger_uid
            ),
            effect=_summon_crab_token,
            name="Attached Crab Deathrattle",
        )
    ]

    return registry


# =====================================================================
# Module-level registries (importable by combat.py, game.py, tavern.py)
# Lazy-initialized to avoid circular import:
#   card_def → event_system → auras → entities → configs → card_def
# =====================================================================

_TRIGGER_REGISTRY = None
GOLDEN_TRIGGER_REGISTRY: dict = {}


def _get_trigger_registry():
    global _TRIGGER_REGISTRY
    if _TRIGGER_REGISTRY is None:
        _TRIGGER_REGISTRY = build_trigger_registry()
    return _TRIGGER_REGISTRY


class _LazyTriggerRegistry:
    """Dict-like proxy that builds TRIGGER_REGISTRY on first access."""

    def __getattr__(self, name):
        return getattr(_get_trigger_registry(), name)

    def __getitem__(self, key):
        return _get_trigger_registry()[key]

    def __contains__(self, key):
        return key in _get_trigger_registry()

    def __iter__(self):
        return iter(_get_trigger_registry())

    def __len__(self):
        return len(_get_trigger_registry())

    def keys(self):
        return _get_trigger_registry().keys()

    def values(self):
        return _get_trigger_registry().values()

    def items(self):
        return _get_trigger_registry().items()

    def get(self, key, default=None):
        return _get_trigger_registry().get(key, default)


TRIGGER_REGISTRY = _LazyTriggerRegistry()


# ---------------------------------------------------------------------------
# AVENGE_REGISTRY — card_id → AvengeEffect for all cards with Avenge mechanic
# ---------------------------------------------------------------------------


def build_avenge_registry() -> Dict[str, AvengeEffect]:
    """Map card_id → AvengeEffect for cards with Avenge mechanic.
    Also maps AvengeBuffFriendlyTypeGlobal to a synthetic AvengeEffect."""
    registry: Dict[str, AvengeEffect] = {}
    for card in ALL_CARDS:
        for eff in card.effects:
            if isinstance(eff, AvengeEffect):
                registry[card.card_id] = eff
                break
            elif isinstance(eff, AvengeBuffFriendlyTypeGlobal):
                # Map to AvengeEffect with friendly_type scope covering board
                registry[card.card_id] = AvengeEffect(
                    threshold=eff.threshold,
                    buff_atk=eff.atk,
                    buff_hp=eff.hp,
                    buff_scope="perm",
                    buff_target="friendly_type",
                    target_type=eff.trigger_type,
                )
                break
    return registry


AVENGE_REGISTRY: Dict[str, AvengeEffect] = build_avenge_registry()
