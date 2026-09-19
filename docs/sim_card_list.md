# hs_autobattler 模拟器随从卡全枚举（sim side）

> 来源：`src/hearthstone/engine/card_def.py`（`ALL_CARDS` 单一来源）+ `configs.py`（`ROTATED_OUT`/`TIER_COPIES`）+ `enums.py`（`CardIDs`）。生成日期：2026-09-18。
> `中文名` 列：模拟器源码中无中文名，统一记为 —。`is_token=是` 的为衍生物 token（不可收集，仅由效果召唤，仍保留在 CARD_DB 中）。
> `种族` 列记为 — 的卡在源码中 `types=[]`（空列表，即无种族标签，视为中立）。

## 统计
- 随从卡总数：**184**（可收集 175 + 衍生物 token 9）
- 按星级分组（可收集 / token）：
  - T1：可收集 21，token 6
  - T2：可收集 24，token 2
  - T3：可收集 37，token 0
  - T4：可收集 39，token 0
  - T5：可收集 26，token 0
  - T6：可收集 20，token 1
  - T7：可收集 8，token 0
- `ROTATED_OUT`（configs.py）：`{CardIDs.MONSTROUS_MACAW}` — 巨型金刚鹦鹉 Monstrous Macaw（T4 野兽），补丁 36.6.1 移出轮换；保留在 CARD_DB 仅作兼容，永不进商店/发现池。
- `TIER_COPIES`（每星卡池份数）：T1=16, T2=15, T3=13, T4=11, T5=9, T6=7, T7=3。CardPool 默认 `max_tier=7`：7 星卡在池中（每种 3 份）仅供 6 本三连发现，商店最高 6 本。

## 事件 / 触发器关键词（card_def.py 中出现的全部 EventType）
共 13 种：
- `ATTACK_DECLARED`（攻击时）：出现 9 次
- `DAMAGE_DEALT`（造成伤害）：出现 1 次
- `DIVINE_SHIELD_LOST`（失去圣盾）：出现 4 次
- `END_OF_TURN`（回合结束）：出现 12 次
- `HERO_DAMAGED`（英雄受伤）：出现 1 次
- `MINION_DAMAGED`（受伤）：出现 4 次
- `MINION_DIED`（死亡）：出现 17 次
- `MINION_PLAYED`（打出）：出现 19 次
- `MINION_SOLD`（出售）：出现 8 次
- `MINION_SUMMONED`（被召唤）：出现 3 次
- `SPELL_CAST`（施法）：出现 3 次
- `START_OF_COMBAT`（战斗开始）：出现 11 次
- `TAVERN_REFRESHED`（酒馆刷新）：出现 1 次

另有元数据标记：`deathrattle=True`（亡语 obs 编码标记）、`avenge_threshold`（复仇阈值，来自 `AvengeEffect`，由独立 `AVENGE_REGISTRY` 处理，不走事件触发器）。

## 自定义 Python 逻辑的卡（非纯声明式 EffectDef）
- `FELEMENTAL`（Felemental）：`CustomEffect()`，在 `build_trigger_registry` 中按 card_id 特判，用手写闭包 `_make_felemental_bc()` 实现（战吼：当前商店随从 +2/+1，后续商店随从通过 ELEMENTAL_BUFF 机制加成）。事件：`MINION_PLAYED`。
- `BRANN_BRONZEBEARD`（Brann Bronzebeard）：`MultiplierDef(event_type=MINION_PLAYED, self_only=True, x2)` — 战吼触发双倍。
- `TITUS_RIVENDARE`（Titus Rivendare）：`MultiplierDef(event_type=MINION_DIED, self_only=True, x2)` — 亡语触发双倍。
- `DRAKKARI_ENCHANTER`（Drakkari Enchanter）：`MultiplierDef(event_type=END_OF_TURN, self_only=False, x2)` — 回合结束触发双倍（全场）。
- 其余 180 张卡（含 9 token）的全部效果均由声明式 `EffectDef` 子类描述，触发器由 `build_trigger_registry()` 按 `isinstance` 分支统一装配（手写 `_make_*` 工厂闭包属引擎通用装配代码，非按卡手写逻辑）。

## 全卡表

| CardID枚举名 | 英文名 | 中文名 | 星级 | 种族 | 攻击/生命 | 效果摘要 | 实现方式 |
|---|---|---|---|---|---|---|---|
| ANNOY_O_TRON | Annoy-o-Tron | — | 1 | Mech | 1/2 | 白板（圣盾、嘲讽） | 无触发器 | is_token=否
| AUREATE_LAUREATE | Aureate Laureate | — | 1 | Pirate | 1/1 | BattlecryMakeGolden（圣盾） | BattlecryMakeGolden@MINION_PLAYED（打出） | is_token=否
| CORD_PULLER | Cord Puller | — | 1 | Mech | 1/1 | DeathrattleSummon(token_id=MICROBOT, count=1)（圣盾） | DeathrattleSummon@MINION_DIED（死亡） | is_token=否
| CRACKLING_CYCLONE | Crackling Cyclone | — | 1 | Elemental | 2/1 | 白板（圣盾、风怒） | 无触发器 | is_token=否
| DUNE_DWELLER | Dune Dweller | — | 1 | Elemental | 3/2 | BattlecryModifyMechanic(mechanic=ELEMENTAL_BUFF, atk=1, hp=1) | BattlecryModifyMechanic@MINION_PLAYED（打出） | is_token=否
| FLIGHTY_SCOUT | Flighty Scout | — | 1 | Murloc | 3/3 | StartOfCombatFromHand | StartOfCombatFromHand@START_OF_COMBAT（战斗开始） | is_token=否
| HARMLESS_BONEHEAD | Harmless Bonehead | — | 1 | Undead | 1/1 | DeathrattleSummon(token_id=SKELETON, count=2) | DeathrattleSummon@MINION_DIED（死亡） | is_token=否
| MANASABER | Manasaber | — | 1 | Beast | 4/1 | DeathrattleSummon(token_id=CUBLING, count=2) | DeathrattleSummon@MINION_DIED（死亡） | is_token=否
| MINTED_CORSAIR | Minted Corsair | — | 1 | Pirate | 1/3 | SellAddSpell(spell_id=TAVERN_COIN, count=1) | SellAddSpell@MINION_SOLD（出售） | is_token=否
| MISFIT_DRAGONLING | Misfit Dragonling | — | 1 | Dragon | 2/1 | StartOfCombatBuffSelfByTier | StartOfCombatBuffSelfByTier@START_OF_COMBAT（战斗开始） | is_token=否
| OMINOUS_SEER | Ominous Seer | — | 1 | Demon+Naga | 2/1 | BattlecrySpellDiscount(amount=1) | BattlecrySpellDiscount@MINION_PLAYED（打出） | is_token=否
| PICKY_EATER | Picky Eater | — | 1 | Demon | 1/1 | ConsumeShopUnit | ConsumeShopUnit@MINION_PLAYED（打出） | is_token=否
| RAZORFEN_GEOMANCER | Razorfen Geomancer | — | 1 | Quilboar | 2/3 | BattlecryAddSpell(spell_id=BLOOD_GEM, count=2) | BattlecryAddSpell@MINION_PLAYED（打出） | is_token=否
| RISEN_RIDER | Risen Rider | — | 1 | Undead | 2/1 | 白板（复生、嘲讽） | 无触发器 | is_token=否
| RIVER_SKIPPER | River Skipper | — | 1 | Murloc | 1/1 | SellGetRandomUnit(tier=1) | SellGetRandomUnit@MINION_SOLD（出售） | is_token=否
| ROT_HIDE_GNOLL | Rot Hide Gnoll | — | 1 | Undead | 1/4 | OnFriendlyDeathBuff(atk=1, hp=0) | OnFriendlyDeathBuff@MINION_DIED（死亡） | is_token=否
| SURF_N_SURF | Surf n' Surf | — | 1 | Naga+Beast | 1/1 | 白板 | 无触发器 | is_token=否
| SWAMPSTRIKER | Swampstriker | — | 1 | Murloc | 1/5 | OnFriendlyPlayType(trigger_type=MURLOC, atk=1, hp=0, exclude_self=True)（风怒） | OnFriendlyPlayType@MINION_PLAYED（打出） | is_token=否
| TUSKED_CAMPER | Tusked Camper | — | 1 | Quilboar | 2/3 | RallyBuff(atk=0, hp=0, use_blood_gem=True) | RallyBuff@ATTACK_DECLARED（攻击时） | is_token=否
| TWILIGHT_HATCHLING | Twilight Hatchling | — | 1 | Dragon | 1/1 | DeathrattleSummonWithTag(token_id=TWILIGHT_WHELP, count=1, tag=IMMEDIATE_ATTACK) | DeathrattleSummonWithTag@MINION_DIED（死亡） | is_token=否
| WRATH_WEAVER | Wrath Weaver | — | 1 | Demon | 1/4 | OnFriendlyPlayTypeDamageHero(trigger_type=DEMON, hero_dmg=1, atk=2, hp=1, exclude_self=True) | OnFriendlyPlayTypeDamageHero@MINION_PLAYED（打出） | is_token=否
| FREEDEALING_GAMBLER | Freedealing Gambler | — | 2 | — | 3/3 | SellForGold(amount=3) | SellForGold@MINION_SOLD（出售） | is_token=否
| SHELL_COLLECTOR | Shell Collector | — | 2 | — | 4/3 | BattlecryAddSpell(spell_id=TAVERN_COIN, count=1) | BattlecryAddSpell@MINION_PLAYED（打出） | is_token=否
| SEWER_RAT | Sewer Rat | — | 2 | — | 3/2 | DeathrattleSummon(token_id=TURTLE, count=1) | DeathrattleSummon@MINION_DIED（死亡） | is_token=否
| MOON_BACON_JAZZER | Moon-Bacon Jazzer | — | 2 | Quilboar | 2/3 | BattlecryModifyMechanic(mechanic=BLOOD_GEM, atk=0, hp=1) | BattlecryModifyMechanic@MINION_PLAYED（打出） | is_token=否
| MECHAGNOME_INTERPRETER | Mechagnome Interpreter | — | 2 | Mech | 2/3 | OnFriendlyPlayType(trigger_type=MECH, atk=2, hp=1, exclude_self=False) | OnFriendlyPlayType@MINION_PLAYED（打出） | is_token=否
| BRIARBACK_BOOKIE | Briarback Bookie | — | 2 | Quilboar | 3/3 | EndOfTurnAddSpell(spell_id=BLOOD_GEM, count=1) | EndOfTurnAddSpell@END_OF_TURN（回合结束） | is_token=否
| HUMMING_BIRD | Humming Bird | — | 2 | Beast | 1/4 | StartOfCombatBuffFriendlyType(trigger_type=BEAST, atk=1, hp=0) | StartOfCombatBuffFriendlyType@START_OF_COMBAT（战斗开始） | is_token=否
| NERUBIAN_DEATHSWARMER | Nerubian Deathswarmer | — | 2 | Undead | 1/4 | BattlecryBuffAllByType(trigger_type=UNDEAD, atk=1, hp=0) | BattlecryBuffAllByType@MINION_PLAYED（打出） | is_token=否
| OOZELING_GLADIATOR | Oozeling Gladiator | — | 2 | — | 2/2 | BattlecryAddSpell(spell_id=SLIMY_SHIELD, count=2) | BattlecryAddSpell@MINION_PLAYED（打出） | is_token=否
| PROPHET_OF_THE_BOAR | Prophet of the Boar | — | 2 | — | 2/3 | OnFriendlyPlayTypeAddSpell(trigger_type=QUILBOAR, spell_id=BLOOD_GEM, count=1, exclude_self=True)（嘲讽） | OnFriendlyPlayTypeAddSpell@MINION_PLAYED（打出） | is_token=否
| SALTSCALE_HONCHO | Saltscale Honcho | — | 2 | Murloc | 5/2 | OnSummonedTypeBuffRandomOther(trigger_type=MURLOC, atk=0, hp=2) | OnSummonedTypeBuffRandomOther@MINION_SUMMONED（被召唤） | is_token=否
| SELLEMENTAL | Sellemental | — | 2 | Elemental | 3/3 | SellAddUnit(card_id=WATER_DROPLET) | SellAddUnit@MINION_SOLD（出售） | is_token=否
| SLEEPY_SUPPORTER | Sleepy Supporter | — | 2 | Dragon | 3/4 | RallyBuffRandomFriendlyType(trigger_type=DRAGON, atk=2, hp=3) | RallyBuffRandomFriendlyType@ATTACK_DECLARED（攻击时） | is_token=否
| TAD | Tad | — | 2 | Murloc | 2/2 | SellGetRandomUnitByType(unit_type=MURLOC) | SellGetRandomUnitByType@MINION_SOLD（出售） | is_token=否
| MIND_MUCK | Mind Muck | — | 2 | Demon | 3/2 | ConsumeShopUnitForRandomFriendly(trigger_type=DEMON) | ConsumeShopUnitForRandomFriendly@MINION_PLAYED（打出） | is_token=否
| EMBALMING_EXPERT | Embalming Expert | — | 2 | Undead | 3/2 | OnTavernRefreshBuffRightmostShop(atk=2, hp=0, give_reborn=True, use_blood_gem=False) | OnTavernRefreshBuffRightmostShop@TAVERN_REFRESHED（酒馆刷新） | is_token=否
| QUILLED_CABBIE | Quilled Cabbie | — | 2 | Quilboar | 2/5 | OnTavernRefreshBuffRightmostShop(atk=0, hp=0, give_reborn=False, use_blood_gem=True) | OnTavernRefreshBuffRightmostShop@TAVERN_REFRESHED（酒馆刷新） | is_token=否
| GHOSTLY_YMIRJAR | Ghostly Ymirjar | — | 2 | Undead | 2/5 | AvengeEffect(threshold=4, buff_atk=0, buff_hp=0, buff_scope=perm, buff_target=free_refresh, target_type=None) | AvengeEffect（复仇注册表AVENGE_REGISTRY，无事件触发器） | is_token=否
| FIRE_BALLER | Fire Baller | — | 2 | Elemental | 4/3 | SellBuffBoardScaling(scaling_key=baller, atk_per=1, hp_per=0) | SellBuffBoardScaling@MINION_SOLD（出售） | is_token=否
| SNOW_BALLER | Snow Baller | — | 2 | Elemental | 3/4 | SellBuffBoardScaling(scaling_key=baller, atk_per=0, hp_per=1) | SellBuffBoardScaling@MINION_SOLD（出售） | is_token=否
| IRATE_ROOSTER | Irate Rooster | — | 2 | Beast | 3/4 | StartOfCombatDamageAndBuffAdjacent(damage=1, atk=4, hp=0) | StartOfCombatDamageAndBuffAdjacent@START_OF_COMBAT（战斗开始） | is_token=否
| SOUL_REWINDER | Soul Rewinder | — | 2 | Demon | 4/1 | OnHeroDamagedHealAndBuffSelf(hp=1) | OnHeroDamagedHealAndBuffSelf@HERO_DAMAGED（英雄受伤） | is_token=否
| SURFING_SYLVAR | Surfing Sylvar | — | 2 | Pirate | 1/2 | EndOfTurnBuffAdjacentPerGolden(atk=1, hp=0) | EndOfTurnBuffAdjacentPerGolden@END_OF_TURN（回合结束） | is_token=否
| PATIENT_SCOUT | Patient Scout | — | 2 | — | 1/1 | SellDiscover(base_tier=1, scaling_key=patient_scout) | SellDiscover@MINION_SOLD（出售） | is_token=否
| BIRD_BUDDY | Bird Buddy | — | 3 | Beast | 3/3 | AvengeEffect(threshold=1, buff_atk=1, buff_hp=1, buff_scope=combat, buff_target=friendly_type, target_type=BEAST) | AvengeEffect（复仇注册表AVENGE_REGISTRY，无事件触发器） | is_token=否
| BUDDING_GREENTHUMB | Budding Greenthumb | — | 3 | Elemental | 2/4 | AvengeEffect(threshold=3, buff_atk=2, buff_hp=2, buff_scope=perm, buff_target=adjacent, target_type=None) | AvengeEffect（复仇注册表AVENGE_REGISTRY，无事件触发器） | is_token=否
| ANNOY_O_MODULE | Annoy-o-Module | — | 3 | Mech | 2/4 | 白板（圣盾、磁力、嘲讽） | 无触发器 | is_token=否
| DEADLY_SPORE | Deadly Spore | — | 3 | — | 1/1 | 白板（烈毒） | 无触发器 | is_token=否
| CADAVER_CARETAKER | Cadaver Caretaker | — | 3 | Undead | 3/3 | DeathrattleSummon(token_id=SKELETON, count=3) | DeathrattleSummon@MINION_DIED（死亡） | is_token=否
| BRINY_BOOTLEGGER | Briny Bootlegger | — | 3 | Pirate | 4/2 | DeathrattleAddSpell(spell_id=TAVERN_COIN, count=1) | DeathrattleAddSpell@MINION_DIED（死亡） | is_token=否
| HANDLESS_FORSAKEN | Handless Forsaken | — | 3 | Undead | 2/1 | DeathrattleSummonWithTag(token_id=HAND_TOKEN, count=1, tag=REBORN) | DeathrattleSummonWithTag@MINION_DIED（死亡） | is_token=否
| GREEDY_SNAKETONGUE | Greedy Snaketongue | — | 3 | Naga | 2/4 | RallyAddSpell(spell_id=TAVERN_COIN, count=1) | RallyAddSpell@ATTACK_DECLARED（攻击时） | is_token=否
| ROADBOAR | Roadboar | — | 3 | Quilboar | 3/4 | RallyAddSpell(spell_id=BLOOD_GEM, count=2) | RallyAddSpell@ATTACK_DECLARED（攻击时） | is_token=否
| GOLDGRUBBER | Goldgrubber | — | 3 | Pirate | 3/2 | EndOfTurnBuffSelfPerGolden(atk_per=3, hp_per=2) | EndOfTurnBuffSelfPerGolden@END_OF_TURN（回合结束） | is_token=否
| GEMSPLITTER | Gemsplitter | — | 3 | Quilboar | 2/1 | OnDivineShieldLostAddSpell(spell_id=BLOOD_GEM, count=1)（圣盾） | OnDivineShieldLostAddSpell@DIVINE_SHIELD_LOST（失去圣盾） | is_token=否
| CANOPY_SWINGER | Canopy Swinger | — | 3 | Murloc | 4/5 | BattlecryBuffAllByTypeIncludeHand(trigger_type=MURLOC, atk=4, hp=0) | BattlecryBuffAllByTypeIncludeHand@MINION_PLAYED（打出） | is_token=否
| HOT_SPRINGER | Hot Springer | — | 3 | Murloc | 5/4 | BattlecryBuffAllByTypeIncludeHand(trigger_type=MURLOC, atk=0, hp=4) | BattlecryBuffAllByTypeIncludeHand@MINION_PLAYED（打出） | is_token=否
| RAMPAGER | Rampager | — | 3 | Beast | 8/8 | RallyDamageOwnBoard(damage=1) | RallyDamageOwnBoard@ATTACK_DECLARED（攻击时） | is_token=否
| FELEMENTAL | Felemental | — | 3 | Elemental+Demon | 3/3 | 自定义效果（战吼：商店随从+2/+1，见上文说明） | CustomEffect→自定义Python闭包@MINION_PLAYED（打出） | is_token=否
| PRICKLY_PIPER | Prickly Piper | — | 3 | Quilboar | 5/1 | DeathrattleModifyMechanic(mechanic=BLOOD_GEM, atk=1, hp=0) | DeathrattleModifyMechanic@MINION_DIED（死亡） | is_token=否
| AMBER_GUARDIAN | Amber Guardian | — | 3 | Dragon | 3/2 | StartOfCombatBuffRandomFriendlyTypeAndDS(trigger_type=DRAGON, atk=2, hp=2)（嘲讽） | StartOfCombatBuffRandomFriendlyTypeAndDS@START_OF_COMBAT（战斗开始） | is_token=否
| HARDY_ORCA | Hardy Orca | — | 3 | Beast | 1/6 | OnSelfDamagedBuffBoard(atk=1, hp=1)（嘲讽） | OnSelfDamagedBuffBoard@MINION_DAMAGED（受伤） | is_token=否
| COLDLIGHT_DIVER | Coldlight Diver | — | 3 | Murloc | 1/1 | BattlecryAddSpell(spell_id=TAVERN_COIN, count=1)；DeathrattleAddSpell(spell_id=TAVERN_COIN, count=1) | BattlecryAddSpell@MINION_PLAYED（打出）；DeathrattleAddSpell@MINION_DIED（死亡） | is_token=否
| JELLY_BELLY | Jelly Belly | — | 3 | Undead | 2/3 | OnFriendlyRebornBuffSelf(atk=2, hp=3) | OnFriendlyRebornBuffSelf@MINION_SUMMONED（被召唤） | is_token=否
| ANUBARAK_NERUBIAN_KING | Anub'arak, Nerubian King | — | 3 | Undead | 3/2 | DeathrattleBuffFriendlyTypeGlobal(trigger_type=UNDEAD, atk=1, hp=1) | DeathrattleBuffFriendlyTypeGlobal@MINION_DIED（死亡） | is_token=否
| ARANASI_ALCHEMIST | Aranasi Alchemist | — | 3 | Demon+Naga | 1/2 | DeathrattleBuffShop(atk=0, hp=1)（复生、嘲讽） | DeathrattleBuffShop@MINION_DIED（死亡） | is_token=否
| BASSGILL | Bassgill | — | 3 | Murloc | 5/2 | DeathrattleBuffHandRandom(atk=5, hp=5) | DeathrattleBuffHandRandom@MINION_DIED（死亡） | is_token=否
| BRIARBACK_DRUMMER | Briarback Drummer | — | 3 | Quilboar | 5/2 | BattlecryAddSpell(spell_id=BLOOD_GEM_BARRAGE, count=1) | BattlecryAddSpell@MINION_PLAYED（打出） | is_token=否
| DEFLECT_O_BOT | Deflect-o-Bot | — | 3 | Mech | 3/2 | OnFriendlySummonedTypeBuff(trigger_type=MECH, atk=2, hp=0, exclude_self=True, combat_buff=True, gain_divine_shield=True)（圣盾） | OnFriendlySummonedTypeBuff@MINION_SUMMONED（被召唤） | is_token=否
| PEGGY_STURDYBONE | Peggy Sturdybone | — | 3 | Pirate+Undead | 2/1 | OnFriendlyPlayType(trigger_type=PIRATE, atk=2, hp=1, exclude_self=False) | OnFriendlyPlayType@MINION_PLAYED（打出） | is_token=否
| PREHISTORIC_TINKERER | Prehistoric Tinkerer | — | 3 | Mech | 4/2 | OnTavernRefreshBuffRightmostShop(atk=2, hp=2, give_reborn=False, use_blood_gem=False)（圣盾） | OnTavernRefreshBuffRightmostShop@TAVERN_REFRESHED（酒馆刷新） | is_token=否
| ROARING_RECRUITER | Roaring Recruiter | — | 3 | Dragon | 2/8 | OnFriendlyAttackBuffSelf(trigger_type=DRAGON, atk=3, hp=1) | OnFriendlyAttackBuffSelf@ATTACK_DECLARED（攻击时） | is_token=否
| SCOURFIN | Scourfin | — | 3 | Murloc | 3/3 | DeathrattleBuffHandRandom(atk=5, hp=5) | DeathrattleBuffHandRandom@MINION_DIED（死亡） | is_token=否
| TARDY_TRAVELER | Tardy Traveler | — | 3 | — | 3/4 | SellAddSpell(spell_id=TAVERN_COIN, count=1) | SellAddSpell@MINION_SOLD（出售） | is_token=否
| TECHNICAL_ELEMENT | Technical Element | — | 3 | Mech+Elemental | 5/6 | 白板（磁力） | 无触发器 | is_token=否
| THE_GLAD_IATOR | The Glad-iator | — | 3 | — | 3/3 | OnSpellCastBuffSelf(atk=1, hp=0)（圣盾） | OnSpellCastBuffSelf@SPELL_CAST（施法） | is_token=否
| TIMECAPN_HOOKTAIL | Timecap'n Hooktail | — | 3 | Pirate+Dragon | 1/4 | OnSpellCastBuffSelf(atk=1, hp=0) | OnSpellCastBuffSelf@SPELL_CAST（施法） | is_token=否
| UNDERHANDED_DEALER | Underhanded Dealer | — | 3 | Demon | 3/3 | OnGainGoldBuffSelf(atk=1, hp=2) | OnGainGoldBuffSelf@SPELL_CAST（施法） | is_token=否
| WAVELING | Waveling | — | 3 | Elemental | 6/1 | OnTavernRefreshBuffRightmostShop(atk=2, hp=2, give_reborn=False, use_blood_gem=False) | OnTavernRefreshBuffRightmostShop@TAVERN_REFRESHED（酒馆刷新） | is_token=否
| WHEELED_CREWMATE | Wheeled Crewmate | — | 3 | Mech | 6/3 | BattlecryModifyMechanic(mechanic=ELEMENTAL_BUFF, atk=0, hp=0) | BattlecryModifyMechanic@MINION_PLAYED（打出） | is_token=否
| WILDFIRE_ELEMENTAL | Wildfire Elemental | — | 3 | Elemental | 6/3 | 白板（顺劈） | 无触发器 | is_token=否
| ACCORD_O_TRON | Accord-o-Tron | — | 4 | Mech | 5/5 | StartOfCombatGainGold(amount=1)（磁力） | StartOfCombatGainGold@END_OF_TURN（回合结束） | is_token=否
| BLADE_COLLECTOR | Blade Collector | — | 4 | — | 3/2 | 白板（顺劈） | 无触发器 | is_token=否
| BONKER | Bonker | — | 4 | Quilboar | 2/7 | RallyBuffAllOthersByType(trigger_type=ALL, count=2) | RallyBuffAllOthersByType@ATTACK_DECLARED（攻击时） | is_token=否
| DEVOUT_HELLCALLER | Devout Hellcaller | — | 4 | Demon | 2/2 | OnFriendlyDeathBuff(atk=1, hp=2) | OnFriendlyDeathBuff@MINION_DIED（死亡） | is_token=否
| EN_DJINN_BLAZER | En-Djinn Blazer | — | 4 | Elemental | 4/4 | OnTavernRefreshBuffRightmostShop(atk=2, hp=2, give_reborn=False, use_blood_gem=False) | OnTavernRefreshBuffRightmostShop@TAVERN_REFRESHED（酒馆刷新） | is_token=否
| FRIENDLY_GEIST | Friendly Geist | — | 4 | Undead | 6/3 | DeathrattleModifyMechanic(mechanic=ELEMENTAL_BUFF, atk=1, hp=0) | DeathrattleModifyMechanic@MINION_DIED（死亡） | is_token=否
| GEOMAGUS_ROOGUG | Geomagus Roogug | — | 4 | Quilboar | 4/6 | 白板（圣盾） | 无触发器 | is_token=否
| GREASE_BOT | Grease Bot | — | 4 | Mech | 2/4 | OnDivineShieldLostBuffUnit(atk=2, hp=2)（圣盾） | OnDivineShieldLostBuffUnit@DIVINE_SHIELD_LOST（失去圣盾） | is_token=否
| HEROIC_UNDERDOG | Heroic Underdog | — | 4 | — | 1/10 | RallyBuff(atk=1, hp=0, use_blood_gem=False)（潜行） | RallyBuff@ATTACK_DECLARED（攻击时） | is_token=否
| HUMON_GOZZ | Humon'gozz | — | 4 | — | 5/5 | BattlecryModifyMechanic(mechanic=ELEMENTAL_BUFF, atk=1, hp=2)（圣盾） | BattlecryModifyMechanic@MINION_PLAYED（打出） | is_token=否
| INDUSTRIOUS_DECKHAND | Industrious Deckhand | — | 4 | Pirate | 3/5 | StartOfCombatGainGold(amount=2) | StartOfCombatGainGold@END_OF_TURN（回合结束） | is_token=否
| KING_BAGURGLE | King Bagurgle | — | 4 | Murloc | 3/4 | BattlecryBuffAllByTypeIncludeHand(trigger_type=MURLOC, atk=2, hp=3) | BattlecryBuffAllByTypeIncludeHand@MINION_PLAYED（打出） | is_token=否
| MARQUEE_TICKER | Marquee Ticker | — | 4 | — | 1/5 | EndOfTurnAddRandomSpell | EndOfTurnAddRandomSpell@END_OF_TURN（回合结束） | is_token=否
| PRIZED_PROMO_DRAKE | Prized Promo-Drake | — | 4 | Dragon | 1/1 | StartOfCombatBuffAllFriendlyType(trigger_type=DRAGON, atk=4, hp=4) | StartOfCombatBuffAllFriendlyType@START_OF_COMBAT（战斗开始） | is_token=否
| PROSTHETIC_HAND | Prosthetic Hand | — | 4 | Mech+Undead | 3/1 | 白板（磁力、复生） | 无触发器 | is_token=否
| RAZORFEN_FLAPPER | Razorfen Flapper | — | 4 | Quilboar | 5/3 | DeathrattleAddSpell(spell_id=BLOOD_GEM_BARRAGE, count=1) | DeathrattleAddSpell@MINION_DIED（死亡） | is_token=否
| REFRESHING_ANOMALY | Refreshing Anomaly | — | 4 | Elemental | 4/5 | BattlecryGainFreeRefreshes(count=2) | BattlecryGainFreeRefreshes@MINION_PLAYED（打出） | is_token=否
| SILENT_ENFORCER | Silent Enforcer | — | 4 | Demon | 6/2 | DeathrattleDamageAllMinions(damage=2)（嘲讽） | DeathrattleDamageAllMinions@MINION_DIED（死亡） | is_token=否
| SIN_DOREI_STRAIGHT_SHOT | Sin'dorei Straight Shot | — | 4 | — | 3/4 | 白板（圣盾、风怒） | 无触发器 | is_token=否
| SLY_RAPTOR | Sly Raptor | — | 4 | Beast | 1/4 | DeathrattleSummon(token_id=SKELETON, count=1) | DeathrattleSummon@MINION_DIED（死亡） | is_token=否
| SOULSPLITTER | Soulsplitter | — | 4 | Undead | 4/2 | StartOfCombatGiveFriendlyTypeReborn(trigger_type=UNDEAD)（复生） | StartOfCombatGiveFriendlyTypeReborn@START_OF_COMBAT（战斗开始） | is_token=否
| SPIRIT_DRAKE | Spirit Drake | — | 4 | Dragon | 1/8 | AvengeEffect(threshold=3, buff_atk=0, buff_hp=0, buff_scope=perm, buff_target=add_spell, target_type=None) | AvengeEffect（复仇注册表AVENGE_REGISTRY，无事件触发器） | is_token=否
| TAVERN_TEMPEST | Tavern Tempest | — | 4 | Elemental | 2/2 | BattlecryAddRandomUnit(unit_type=ELEMENTAL, tier=None) | BattlecryAddRandomUnit@MINION_PLAYED（打出） | is_token=否
| TUNNEL_BLASTER | Tunnel Blaster | — | 4 | Undead | 3/7 | DeathrattleDamageAllMinions(damage=3)（嘲讽） | DeathrattleDamageAllMinions@MINION_DIED（死亡） | is_token=否
| WANNABE_GARGOYLE | Wannabe Gargoyle | — | 4 | Undead | 9/1 | 白板（复生） | 无触发器 | is_token=否
| WITCHWING_NESTMATRON | Witchwing Nestmatron | — | 4 | Dragon | 3/5 | AvengeEffect(threshold=3, buff_atk=0, buff_hp=0, buff_scope=perm, buff_target=add_unit, target_type=None) | AvengeEffect（复仇注册表AVENGE_REGISTRY，无事件触发器） | is_token=否
| TRENCH_FIGHTER | Trench Fighter | — | 4 | Naga | 6/6 | EndOfTurnAddSpell(spell_id=GEM_CONFISCATION, count=1) | EndOfTurnAddSpell@END_OF_TURN（回合结束） | is_token=否
| GUNPOWDER_COURIER | Gunpowder Courier | — | 4 | Pirate | 2/6 | OnGainGoldBuffSelf(atk=2, hp=0) | OnGainGoldBuffSelf@SPELL_CAST（施法） | is_token=否
| BREAM_COUNTER | Bream Counter | — | 4 | Murloc | 4/4 | OnFriendlyPlayTypeBuffSelfInHand(trigger_type=MURLOC, atk=4, hp=4) | OnFriendlyPlayTypeBuffSelfInHand@MINION_PLAYED（打出） | is_token=否
| DAGGERSPINE_THRASHER | Daggerspine Thrasher | — | 4 | Naga | 3/5 | OnSpellCastBuffSelf(atk=1, hp=0) | OnSpellCastBuffSelf@SPELL_CAST（施法） | is_token=否
| MONSTROUS_MACAW | Monstrous Macaw | — | 4 | Beast | 5/4 | RallyBuff(atk=1, hp=1, use_blood_gem=False) | RallyBuff@ATTACK_DECLARED（攻击时） | is_token=否
| PLANKWALKER | Plankwalker | — | 4 | Naga | 6/4 | OnSpellCastBuffBoard(atk=2, hp=1, trigger_type=None) | OnSpellCastBuffBoard@SPELL_CAST（施法） | is_token=否
| RYLAK_METALHEAD | Rylak Metalhead | — | 4 | Mech | 5/3 | DeathrattleBuffAllFriendlies(atk=1, hp=1)（嘲讽） | DeathrattleBuffAllFriendlies@MINION_DIED（死亡） | is_token=否
| SUNKEN_ADVOCATE | Sunken Advocate | — | 4 | Naga | 2/7 | RallyBuffFriendlyTypeAtk(trigger_type=NAGA, atk=1) | RallyBuffFriendlyTypeAtk@ATTACK_DECLARED（攻击时） | is_token=否
| TORTOLLAN_BLUE_SHELL | Tortollan Blue Shell | — | 4 | — | 3/6 | SellForGoldConditional(amount=5) | SellForGoldConditional@MINION_SOLD（出售） | is_token=否
| TRIGORE_THE_LASHER | Trigore the Lasher | — | 4 | Beast | 9/3 | OnFriendlyBeastDamagedBuffSelf(hp=2) | OnFriendlyBeastDamagedBuffSelf@MINION_DAMAGED（受伤） | is_token=否
| FLAMING_ENFORCER | Flaming Enforcer | — | 4 | Elemental | 4/5 | EndOfTurnBuffSelf(atk=2, hp=2) | EndOfTurnBuffSelf@END_OF_TURN（回合结束） | is_token=否
| ICHORON_THE_PROTECTOR | Ichoron the Protector | — | 4 | Elemental | 3/1 | OnFriendlyPlayType(trigger_type=ELEMENTAL, atk=0, hp=1, exclude_self=True)（圣盾） | OnFriendlyPlayType@MINION_PLAYED（打出） | is_token=否
| PERSISTENT_POET | Persistent Poet | — | 4 | Dragon | 2/3 | 白板（圣盾） | 无触发器 | is_token=否
| BRANN_BRONZEBEARD | Brann Bronzebeard | — | 5 | — | 2/4 | 光环：MINION_PLAYED 触发 x2（仅自身） | MultiplierDef（自定义Python逻辑） | is_token=否
| TITUS_RIVENDARE | Titus Rivendare | — | 5 | — | 1/7 | 光环：MINION_DIED 触发 x2（仅自身） | MultiplierDef（自定义Python逻辑） | is_token=否
| DRAKKARI_ENCHANTER | Drakkari Enchanter | — | 5 | — | 1/5 | 光环：END_OF_TURN 触发 x2（全场） | MultiplierDef（自定义Python逻辑） | is_token=否
| GENTLE_DJINNI | Gentle Djinni | — | 5 | Elemental | 4/5 | BattlecryAddRandomUnit(unit_type=ELEMENTAL, tier=None)（嘲讽） | BattlecryAddRandomUnit@MINION_PLAYED（打出） | is_token=否
| INDOMITABLE_MOUNT | Indomitable Mount | — | 5 | Beast | 3/6 | BattlecryAddRandomUnit(unit_type=BEAST, tier=4) | BattlecryAddRandomUnit@MINION_PLAYED（打出） | is_token=否
| CHAMPION_OF_THE_PRIMUS | Champion of the Primus | — | 5 | Undead | 2/10 | AvengeBuffFriendlyTypeGlobal(threshold=2, trigger_type=UNDEAD, atk=1, hp=0) | AvengeBuffFriendlyTypeGlobal（复仇注册表AVENGE_REGISTRY，无事件触发器） | is_token=否
| CORRUPTED_MYRMIDON | Corrupted Myrmidon | — | 5 | Demon | 3/3 | StartOfCombatBuffSelf(atk=3, hp=3) | StartOfCombatBuffSelf@START_OF_COMBAT（战斗开始） | is_token=否
| SILITHID_BURROWER | Silithid Burrower | — | 5 | Beast | 5/4 | DeathrattleBuffFriendlyTypeGlobal(trigger_type=BEAST, atk=1, hp=1)；AvengeEffect(threshold=1, buff_atk=1, buff_hp=1, buff_scope=perm, buff_target=self, target_type=None) | DeathrattleBuffFriendlyTypeGlobal@MINION_DIED（死亡）；AvengeEffect（复仇注册表AVENGE_REGISTRY，无事件触发器） | is_token=否
| GHOUL_OF_THE_FEAST | Ghoul of the Feast | — | 5 | Undead | 2/7 | AvengeEffect(threshold=1, buff_atk=2, buff_hp=2, buff_scope=perm, buff_target=friendly_type, target_type=None) | AvengeEffect（复仇注册表AVENGE_REGISTRY，无事件触发器） | is_token=否
| TWILIGHT_WATCHER | Twilight Watcher | — | 5 | Dragon | 3/7 | OnFriendlyAttackBuffTriggerSelf(trigger_type=DRAGON, atk=1, hp=3) | OnFriendlyAttackBuffTriggerSelf@ATTACK_DECLARED（攻击时） | is_token=否
| UNFORGIVING_TREANT | Unforgiving Treant | — | 5 | — | 3/12 | OnSelfDamagedBuffBoard(atk=2, hp=0)（嘲讽） | OnSelfDamagedBuffBoard@MINION_DAMAGED（受伤） | is_token=否
| NOMI_KITCHEN_NIGHTMARE | Nomi, Kitchen Nightmare | — | 5 | — | 4/4 | OnFriendlyPlayType(trigger_type=ELEMENTAL, atk=2, hp=2, exclude_self=False) | OnFriendlyPlayType@MINION_PLAYED（打出） | is_token=否
| BILE_SPITTER | Bile Spitter | — | 5 | Murloc | 1/10 | RallyBuffRandomFriendlyType(trigger_type=MURLOC, atk=0, hp=0)（烈毒） | RallyBuffRandomFriendlyType@ATTACK_DECLARED（攻击时） | is_token=否
| RAZORFEN_VINEWEAVER | Razorfen Vineweaver | — | 5 | Quilboar | 2/1 | RallyBuff(atk=0, hp=0, use_blood_gem=True) | RallyBuff@ATTACK_DECLARED（攻击时） | is_token=否
| CARAPACE_RAISER | Carapace Raiser | — | 5 | Undead | 6/3 | DeathrattleAddSpell(spell_id=HAUNTED_CARAPACE, count=1) | DeathrattleAddSpell@MINION_DIED（死亡） | is_token=否
| SHADOWDANCER | Shadowdancer | — | 5 | — | 5/4 | DeathrattleAddSpell(spell_id=STAFF_OF_ENRICHMENT, count=1)（嘲讽） | DeathrattleAddSpell@MINION_DIED（死亡） | is_token=否
| FIRESCALE_HOARDER | Firescale Hoarder | — | 5 | Dragon | 5/5 | BattlecryAddSpell(spell_id=SHINY_RING, count=1)；DeathrattleAddSpell(spell_id=SHINY_RING, count=1) | BattlecryAddSpell@MINION_PLAYED（打出）；DeathrattleAddSpell@MINION_DIED（死亡） | is_token=否
| SPIKED_SAVIOR | Spiked Savior | — | 5 | Undead | 8/2 | DeathrattleGiveFriendliesScaling(buff_atk=1, buff_hp=1, self_damage=1)（复生、嘲讽） | DeathrattleGiveFriendliesScaling@MINION_DIED（死亡） | is_token=否
| LEEROY_THE_RECKLESS | Leeroy the Reckless | — | 5 | — | 6/2 | DeathrattleDestroyKiller | DeathrattleDestroyKiller@MINION_DIED（死亡） | is_token=否
| STUNTDRAKE | Stuntdrake | — | 5 | Dragon | 14/5 | AvengeEffect(threshold=3, buff_atk=14, buff_hp=5, buff_scope=perm, buff_target=random_friendly_type, target_type=DRAGON) | AvengeEffect（复仇注册表AVENGE_REGISTRY，无事件触发器） | is_token=否
| WINTERGRASP_GHOUL | Wintergrasp Ghoul | — | 5 | Undead | 5/3 | DeathrattleAddSpell(spell_id=TOMB_TURNING, count=1) | DeathrattleAddSpell@MINION_DIED（死亡） | is_token=否
| IRIDESCENT_SKYBLAZER | Iridescent Skyblazer | — | 5 | Dragon | 3/7 | OnFriendlyBeastDamagedBuffOther(atk=1, hp=1) | OnFriendlyBeastDamagedBuffOther@MINION_DAMAGED（受伤） | is_token=否
| NIUZAO | Niuzao | — | 5 | Beast | 7/6 | RallyDealDamageEqualToAtk | RallyDealDamageEqualToAtk@ATTACK_DECLARED（攻击时） | is_token=否
| TWILIGHT_BROODMOTHER | Twilight Broodmother | — | 5 | Dragon | 7/4 | DeathrattleSummonTauntToken(token_id=TWILIGHT_WHELP, count=2) | DeathrattleSummonTauntToken@MINION_DIED（死亡） | is_token=否
| COSTUME_ENTHUSIAST | Costume Enthusiast | — | 5 | — | 4/5 | StartOfCombatBuffSelfByHighestAllyAtk（圣盾） | StartOfCombatBuffSelfByHighestAllyAtk@START_OF_COMBAT（战斗开始） | is_token=否
| ELITE_NAVIGATOR | Elite Navigator | — | 5 | Pirate | 5/5 | BattlecryMakeGoldenFriendlyByTier(max_tier=4) | BattlecryMakeGoldenFriendlyByTier@MINION_PLAYED（打出） | is_token=否
| GOLDRINN_THE_GREAT_WOLF | Goldrinn, the Great Wolf | — | 6 | Beast | 8/8 | DeathrattleBuffAllFriendliesGlobal(trigger_type=BEAST, atk=8, hp=8) | DeathrattleBuffAllFriendliesGlobal@MINION_DIED（死亡） | is_token=否
| CHARLGA | Charlga | — | 6 | Quilboar | 3/3 | EndOfTurnBuffBoardByType(trigger_type=ALL, atk=0, hp=0) | EndOfTurnBuffBoardByType@END_OF_TURN（回合结束） | is_token=否
| SLITHERSPEAR_LORD_OF_GAINS | Slitherspear, Lord of Gains | — | 6 | Naga | 4/5 | EndOfTurnBuffFriendlyTypeNaga(atk=2, hp=1) | EndOfTurnBuffFriendlyTypeNaga@END_OF_TURN（回合结束） | is_token=否
| LORD_OF_THE_RUINS | Lord of the Ruins | — | 6 | Demon | 5/6 | OnFriendlyDemonDamageBuff(atk=2, hp=1) | OnFriendlyDemonDamageBuff@DAMAGE_DEALT（造成伤害） | is_token=否
| FAMISHED_FELBAT | Famished Felbat | — | 6 | Demon | 9/5 | EndOfTurnConsumeTavernForDemon | EndOfTurnConsumeTavernForDemon@END_OF_TURN（回合结束） | is_token=否
| SHIP_MASTER_EUDORA | Ship Master Eudora | — | 6 | Pirate | 10/5 | DeathrattleBuffAllFriendlies(atk=8, hp=8) | DeathrattleBuffAllFriendlies@MINION_DIED（死亡） | is_token=否
| AVALANCHE_CALLER | Avalanche Caller | — | 6 | Elemental | 6/5 | EndOfTurnAddSpell(spell_id=MOUNTING_AVALANCHE, count=1) | EndOfTurnAddSpell@END_OF_TURN（回合结束） | is_token=否
| ULTRAVIOLET_ASCENDANT | Ultraviolet Ascendant | — | 6 | Elemental | 6/3 | StartOfCombatBuffFriendlyTypeScaling(trigger_type=ELEMENTAL, atk=3, hp=2) | StartOfCombatBuffFriendlyTypeScaling@START_OF_COMBAT（战斗开始） | is_token=否
| IGNITION_SPECIALIST | Ignition Specialist | — | 6 | — | 8/8 | EndOfTurnAddRandomSpell；EndOfTurnAddRandomSpell | EndOfTurnAddRandomSpell@END_OF_TURN（回合结束）；EndOfTurnAddRandomSpell@END_OF_TURN（回合结束） | is_token=否
| FAUNA_WHISPERER | Fauna Whisperer | — | 6 | Beast | 4/9 | EndOfTurnBuffAdjacent(atk=3, hp=3) | EndOfTurnBuffAdjacent@END_OF_TURN（回合结束） | is_token=否
| YOUNG_MURK_EYE | Young Murk-Eye | — | 6 | Murloc | 9/6 | EndOfTurnTriggerAdjacentBattlecry | EndOfTurnTriggerAdjacentBattlecry@END_OF_TURN（回合结束） | is_token=否
| FIRE_FORGED_EVOKER | Fire-forged Evoker | — | 6 | Dragon | 8/5 | StartOfCombatBuffFriendlyType(trigger_type=DRAGON, atk=2, hp=1) | StartOfCombatBuffFriendlyType@START_OF_COMBAT（战斗开始） | is_token=否
| SANGUINE_REFINER | Sanguine Refiner | — | 6 | Quilboar | 3/10 | RallyBuff(atk=0, hp=0, use_blood_gem=True) | RallyBuff@ATTACK_DECLARED（攻击时） | is_token=否
| BLOODSNOUT_WARLORD | Bloodsnout Warlord | — | 6 | Quilboar | 5/5 | RallyBuffAllOthersByType(trigger_type=ALL, count=3) | RallyBuffAllOthersByType@ATTACK_DECLARED（攻击时） | is_token=否
| DEATHLY_STRIKER | Deathly Striker | — | 6 | Undead | 8/8 | AvengeEffect(threshold=4, buff_atk=0, buff_hp=0, buff_scope=perm, buff_target=add_unit, target_type=UNDEAD) | AvengeEffect（复仇注册表AVENGE_REGISTRY，无事件触发器） | is_token=否
| WHIRLING_LASS_O_MATIC | Whirling Lass-o-Matic | — | 6 | — | 6/3 | RallyAddSpell(spell_id=TRIPLET_REWARD, count=1)（圣盾、风怒） | RallyAddSpell@ATTACK_DECLARED（攻击时） | is_token=否
| ARCHAEDAS | Archaedas | — | 6 | — | 10/10 | BattlecryAddRandomUnit(unit_type=None, tier=5) | BattlecryAddRandomUnit@MINION_PLAYED（打出） | is_token=否
| NIGHTMARE_PAR_TEA_GUEST | Nightmare Par-tea Guest | — | 6 | — | 6/6 | BattlecryAddSpell(spell_id=MISPLACED_TEA_SET, count=1)；DeathrattleAddSpell(spell_id=MISPLACED_TEA_SET, count=1) | BattlecryAddSpell@MINION_PLAYED（打出）；DeathrattleAddSpell@MINION_DIED（死亡） | is_token=否
| SUNDERED_MATRIARCH | Sundered Matriarch | — | 6 | Dragon | 7/4 | OnSpellCastBuffBoard(atk=0, hp=2, trigger_type=None) | OnSpellCastBuffBoard@SPELL_CAST（施法） | is_token=否
| PRIMITIVE_PAINTER | Primitive Painter | — | 6 | Murloc | 3/8 | OnFriendlyPlayType(trigger_type=MURLOC, atk=1, hp=2, exclude_self=False) | OnFriendlyPlayType@MINION_PLAYED（打出） | is_token=否
| CAPTAIN_SANDERS | Captain Sanders | — | 7 | Pirate | 9/9 | BattlecryMakeGoldenFriendlyByTier(max_tier=6) | BattlecryMakeGoldenFriendlyByTier@MINION_PLAYED（打出） | is_token=否
| HIGHKEEPER_RA | Highkeeper Ra | — | 7 | — | 6/6 | BattlecryAddRandomUnit(unit_type=None, tier=6)；DeathrattleAddSpell(spell_id=TRIPLET_REWARD, count=1) | BattlecryAddRandomUnit@MINION_PLAYED（打出）；DeathrattleAddSpell@MINION_DIED（死亡） | is_token=否
| THE_LAST_ONE_STANDING | The Last One Standing | — | 7 | — | 12/12 | RallyBuff(atk=12, hp=12, use_blood_gem=False) | RallyBuff@ATTACK_DECLARED（攻击时） | is_token=否
| SANGUINE_CHAMPION | Sanguine Champion | — | 7 | — | 18/3 | BattlecryModifyMechanic(mechanic=BLOOD_GEM, atk=1, hp=1)；DeathrattleModifyMechanic(mechanic=BLOOD_GEM, atk=1, hp=1) | BattlecryModifyMechanic@MINION_PLAYED（打出）；DeathrattleModifyMechanic@MINION_DIED（死亡） | is_token=否
| PSYCHUS | Psychus | — | 7 | — | 1/1 | StartOfCombatBuffSelfByHighestBoardAtk | StartOfCombatBuffSelfByHighestBoardAtk@START_OF_COMBAT（战斗开始） | is_token=否
| OBSIDIAN_RAVAGER | Obsidian Ravager | — | 7 | — | 7/7 | RallyDealDamageEqualToAtk | RallyDealDamageEqualToAtk@ATTACK_DECLARED（攻击时） | is_token=否
| STITCHED_SALVAGER | Stitched Salvager | — | 7 | Undead | 16/4 | DeathrattleBuffAllFriendlies(atk=4, hp=4) | DeathrattleBuffAllFriendlies@MINION_DIED（死亡） | is_token=否
| FUTUREFIN | Futurefin | — | 7 | Murloc | 7/13 | EndOfTurnBuffAdjacent(atk=7, hp=13) | EndOfTurnBuffAdjacent@END_OF_TURN（回合结束） | is_token=否
| MICROBOT | Microbot | — | 1 | Mech | 1/1 | 白板 | 无触发器 | is_token=是
| SKELETON | Skeleton | — | 1 | Undead | 1/1 | 白板 | 无触发器 | is_token=是
| CUBLING | Cubling | — | 1 | Beast | 0/1 | 白板（嘲讽） | 无触发器 | is_token=是
| TWILIGHT_WHELP | Twilight Whelp | — | 1 | Dragon | 3/3 | 白板 | 无触发器 | is_token=是
| CRAB_TOKEN | Crab | — | 1 | Beast | 3/2 | 白板 | 无触发器 | is_token=是
| TURTLE | Turtle | — | 2 | — | 2/3 | 白板（嘲讽） | 无触发器 | is_token=是
| WATER_DROPLET | Water Droplet | — | 2 | Elemental | 3/3 | 白板 | 无触发器 | is_token=是
| HAND_TOKEN | Hand | — | 1 | Undead | 2/1 | 白板 | 无触发器 | is_token=是
| GOLEM_TOKEN | Golem | — | 6 | — | 6/6 | 白板 | 无触发器 | is_token=是

注：`实现方式` 列格式为 `EffectDef类名@事件名`；事件中文见上表；`复仇` 走独立注册表。token 行末尾标注 `is_token=是`。
