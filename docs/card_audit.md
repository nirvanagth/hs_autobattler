# 酒馆战棋卡池审计报告

**审计日期**：2026-09-18（36.6.1 补丁上线前，现行第 14 赛季 Dark Gifts of Dalaran）
**原则**：只对标当前正式服标准卡池；9 月 22 日补丁前瞻内容（畸变怪种族等）全部排除。

## 数据来源

- **模拟器侧**：`src/hearthstone/engine/card_def.py`（`ALL_CARDS` 单一来源，程序化解析）、`configs.py`、`enums.py`。
  全枚举见 `docs/sim_card_list.md`。模拟器可收集随从 **175 张**（另有衍生物 token 9 张，不计入 diff）。
- **正式服侧**：HearthstoneJSON 最新构建（`api.hearthstonejson.com`，按池标记过滤掉 9/22 未上线卡、双打专属卡）、36.6.1 官方公告（退环境名单）、hearthpwn / outof.games 补丁镜像。
  现行标准卡池 **248 张**（1 星 22 / 2 星 34 / 3 星 43 / 4 星 57 / 5 星 47 / 6 星 33 / 7 星 12）。

## 总览

| 类别 | 含义 | 数量 |
|---|---|---|
| A | 模拟器有、正式服已退环境 → 待加入 `ROTATED_OUT`（鹦鹉已在内，不重复计） | **91** |
| B1 | 正式服有、模拟器缺失 → **补卡清单（建议补）** | **121** |
| B2 | 正式服现行有但 9/22 即将移除/纳迦暂退 → **建议跳过** | **45** |
| C | 两边都有但星级/身材/效果不一致 | **34**（大改 17 / 小改 17）|
| D | 模拟器独有、正式服没有 | **1** |

难度标注：① 纯身材或现有 EffectDef/事件可表达（快）；② 需新增事件或机制（中）；③ 需 Python+C++ 生成器扩展或新系统（慢）。

---

## A 类：待加入 ROTATED_OUT（91 张）

这些卡在模拟器卡池里，但已不在正式服现行标准池中。建议把以下枚举名全部加入 `configs.py` 的 `ROTATED_OUT`（卡定义保留，仅不进池）。

**T1（9）**：`ANNOY_O_TRON`（吵吵机器人）、`DUNE_DWELLER`（沙丘住民 ※9/22 回归，届时记得移出）、`MANASABER`（玛瑙萨伯）、`MINTED_CORSAIR`（铸币海盗）、`MISFIT_DRAGONLING`（错位幼龙）、`PICKY_EATER`（挑食者）、`SURF_N_SURF`（冲浪）、`SWAMPSTRIKER`（沼泽打击者）、`TWILIGHT_HATCHLING`（暮光雏龙）

**T2（11）**：`FREEDEALING_GAMBLER`、`SEWER_RAT`（下水道老鼠）、`MOON_BACON_JAZZER`、`BRIARBACK_BOOKIE`、`PROPHET_OF_THE_BOAR`、`SALTSCALE_HONCHO`、`SLEEPY_SUPPORTER`、`EMBALMING_EXPERT`、`QUILLED_CABBIE`、`GHOSTLY_YMIRJAR`、`IRATE_ROOSTER`

**T3（25）**：`BIRD_BUDDY`、`BUDDING_GREENTHUMB`、`BRINY_BOOTLEGGER`、`GREEDY_SNAKETONGUE`、`GOLDGRUBBER`、`GEMSPLITTER`、`CANOPY_SWINGER`、`HOT_SPRINGER`、`RAMPAGER`、`FELEMENTAL`、`PRICKLY_PIPER`、`HARDY_ORCA`、`COLDLIGHT_DIVER`、`JELLY_BELLY`、`ANUBARAK_NERUBIAN_KING`、`ARANASI_ALCHEMIST`、`BASSGILL`、`PEGGY_STURDYBONE`、`PREHISTORIC_TINKERER`、`SCOURFIN`、`TARDY_TRAVELER`、`TECHNICAL_ELEMENT`、`THE_GLAD_IATOR`、`UNDERHANDED_DEALER`、`WHEELED_CREWMATE`

**T4（17）**：`GREASE_BOT`、`INDUSTRIOUS_DECKHAND`、`KING_BAGURGLE`、`MARQUEE_TICKER`、`PRIZED_PROMO_DRAKE`、`SILENT_ENFORCER`、`SOULSPLITTER`、`SPIRIT_DRAKE`、`TUNNEL_BLASTER`、`WANNABE_GARGOYLE`、`WITCHWING_NESTMATRON`、`DAGGERSPINE_THRASHER`、`PLANKWALKER`、`RYLAK_METALHEAD`、`SUNKEN_ADVOCATE`、`TRIGORE_THE_LASHER`、`ICHORON_THE_PROTECTOR`

**T5（17）**：`GENTLE_DJINNI`、`INDOMITABLE_MOUNT`、`CHAMPION_OF_THE_PRIMUS`、`CORRUPTED_MYRMIDON`、`SILITHID_BURROWER`、`GHOUL_OF_THE_FEAST`、`TWILIGHT_WATCHER`、`UNFORGIVING_TREANT`、`CARAPACE_RAISER`、`SHADOWDANCER`、`SPIKED_SAVIOR`、`STUNTDRAKE`、`WINTERGRASP_GHOUL`、`IRIDESCENT_SKYBLAZER`、`NIUZAO`、`TWILIGHT_BROODMOTHER`、`ELITE_NAVIGATOR`

**T6（12）**：`CHARLGA`、`SLITHERSPEAR_LORD_OF_GAINS`、`LORD_OF_THE_RUINS`、`FAMISHED_FELBAT`、`SHIP_MASTER_EUDORA`、`AVALANCHE_CALLER`、`ULTRAVIOLET_ASCENDANT`、`YOUNG_MURK_EYE`、`BLOODSNOUT_WARLORD`、`WHIRLING_LASS_O_MATIC`、`ARCHAEDAS`、`SUNDERED_MATRIARCH`

> 注意：`DUNE_DWELLER` 在 9/22 补丁回归名单中，补丁上线后需把它从 `ROTATED_OUT` 移出。

---

## B2 类：建议跳过（45 张）

这些卡今天在正式服池中，但 **9 月 22 日补丁即被移除**，或属于 **9/22 暂退的纳迦种族**。现在补等于 4 天后白干，建议跳过，等补丁后再按新池处理。

**9/22 移除（27 张）**：
- T1：Molten Rock（熔融岩石）
- T2：Ancestral Automaton（星元自动机）、Metallic Hunter（钢铁猎人）、Thousandth Paper Drake（千纸幼龙）
- T3：Breakout Mastermind（越狱主谋）、Dustbone Devastator（尘骨毁灭者）、Mama Mrrglton（莫格顿大妈）、Meteorite Crasher（裂地陨星）、Papa Mrrglton（莫格顿老爹）、Private Investigator（私家调查员）、Sand Swirler（沙尘旋流）
- T4：Auto Assembler（自动装配机）、Captain Cookie（"船长"曲奇）、Clunker Junker（废铁残械）、Deepwater Chieftain（深水酋长）、Glowing Cinder（辐光余烬）、Motley Phalanx（混编战团）
- T5：Cousin Errgl（厄戈尔表弟）、Dancing Barnstormer（农场热舞旋风）、Dual-Wield Corsair（双持海盗）、Kangor's Apprentice（坎格尔的学徒）、Scrap Scraper（报废废铁回收机）、Vigilant Bristlemane（警戒的刺鬃野猪人）、Void Pup Trainer（虚空幼犬训练师）
- T6：Moat Custodian（沟渠守护元素）、Unleashed Mana Surge（狂放的法力涌流）、Warpwing（折跃之翼）

**纳迦种族（9/22 暂退，18 张）**：
- T1：Fleeing Fugitive（逃窜的纳迦）、Mini-Myrmidon（迷你侍从）
- T2：Lava Lurker（熔岩潜伏者）、Thaumaturgist（杂耍奇术师）
- T3：Deep-Sea Angler（深海钓客）、Waverider（乘波骑士）
- T4：Abyssal Bruiser（深渊打手）、Cagey Conjurer（机警的咒术师）、Rimescale Priestess（霜鳞女祭司）、Seafloor Recruiter（海床招募者）、Zesty Shaker（热情沙锤手）
- T5：Darkcrest Strategist（暗潮战略专家）、Glowscale（闪鳞纳迦）、Showy Cyclist（显眼的骑手）、Tranquil Meditative（宁静的冥想者）
- T6：Groundbreaker（碎地者）、Torrential Ruiner（涌流毁灭者）
- T7：Sea Witch Zar'jira（海巫扎尔吉拉）

> 模拟器里已有的纳迦卡（如 Ominous Seer、Shell Collector、Trench Fighter 等）可保留定义不动；等 9/22 补丁实装后再决定是否整体处理。

---

## B1 类：补卡清单（121 张，核心产出）

正式服有、模拟器缺失，且 9/22 补丁后仍在池中的卡。按星级排列。

### T1（7 张）

| 英文名 | 中文名 | 种族 | 身材 | 效果摘要 | 难度 |
|---|---|---|---|---|---|
| Buzzing Vermin | 嗡鸣害虫 | 野兽 | 1/1 | 嘲讽，亡语召唤 2/2 甲虫 | ① |
| Flittering Bat | 翩飞蝙蝠 | 野兽 | 1/4 | 进击：召唤 1/1 野兽 | ① |
| Glim Guardian | 微光护卫者 | 龙 | 1/4 | 进击：+2 攻击 | ① |
| Lullabot | 催眠机器人 | 机械 | 2/2 | 磁力，回合结束时 +1 生命 | ① |
| Scarlet Survivor | 血色幸存飞龙 | 龙 | 3/3 | 攻击达到 6 时获得圣盾 | ② |
| Southsea Busker | 南海卖艺者 | 海盗 | 3/1 | 战吼：下回合 +1 铸币 | ② |
| Suspicious Prisonguard | 可疑的监狱守卫 | — | 3/3 | 发动(1)：使另一随从 +3/+3 | ② |

### T2（15 张）

| 英文名 | 中文名 | 种族 | 身材 | 效果摘要 | 难度 |
|---|---|---|---|---|---|
| Bilgewater Breakout | 锈水爆破手 | 海盗 | 3/2 | 战吼：获取上锁宝箱（新法术） | ② |
| Clever Castaway | 机智的船难海盗 | 海盗 | 2/3 | 发动(2)：发现酒馆法术 | ② |
| Crater Miner | 坑谷矿工 | 野猪人 | 2/2 | 抉择：2 鲜血宝石 / 宝石特训 | ② |
| Decoy Conjurer | 迷诱咒术师 | — | 3/4 | 发动(2)：偷取酒馆最高攻随从牌 | ② |
| Electric Synthesizer | 电音合成师 | 龙 | 3/4 | 战吼、战斗开始：其他龙 +1/+1 | ① |
| Eternal Knight | 永恒骑士 | 亡灵 | 4/2 | 本局每死一个友方永恒骑士 +4/+2 | ② |
| Expert Aviator | 飞行专家 | 鱼人 | 3/4 | 进击：召唤手牌最高攻随从（本场战斗） | ② |
| Forest Rover | 森林游虫 | 野兽 | 1/1 | 战吼本局甲虫 +2/+1；亡语召唤 2/2 甲虫 | ② |
| Intrepid Botanist | 新锐植物学家 | — | 3/4 | 抉择：本局酒馆法术 +1 攻 / +1 血 | ② |
| Laboratory Assistant | 实验室助理 | 恶魔 | 3/4 | 战吼：下 3 次刷新各加恶魔饲料 | ② |
| Lurking Lionfish | 深潜狮子鱼 | 野兽 | 3/4 | 发动(2)：鱼饵机制（新系统） | ③ |
| Prodigious Tusker | 惊异长牙猪 | 野猪人 | 2/5 | 另一友方攻击时对其用血宝石 | ① |
| Scarlet Skull | 血色骷髅 | 亡灵 | 2/1 | 复生，亡语使友方亡灵 +1/+2 | ① |
| Tarecgosa | 泰蕾苟萨 | 龙 | 4/4 | 永久保留战斗阶段获得的增益 | ② |
| Very Hungry Winterfinner | 巨饿冬鳍鱼人 | 鱼人 | 2/6 | 嘲讽，受伤时手牌随从 +2/+1 | ② |

### T3（18 张）

| 英文名 | 中文名 | 种族 | 身材 | 效果摘要 | 难度 |
|---|---|---|---|---|---|
| Azsharan Cutlassier | 艾萨拉的刀客 | 海盗 | 6/4 | 战吼：本局酒馆法术 +1 攻 | ② |
| Blue Whelp | 蓝色雏龙 | 龙 | 1/5 | 进击：本局酒馆法术 +1 血 | ② |
| Diremuck Forager | 凶饿的觅食者 | 鱼人 | 4/5 | 战斗开始：召唤手牌最高攻鱼人 | ② |
| Disguised Graverobber | 变装盗墓贼 | — | 4/4 | 战吼：消灭友方亡灵获其原版复制 | ② |
| Fearless Foodie | 无畏的食客 | 野猪人 | 2/4 | 抉择：本局血宝石 +1/+1 / 获 4 血宝石 | ② |
| Fruit Vendor | 水果商贩 | — | 3/6 | 发动(1)：获 2 张香蕉果盘 | ② |
| Gem Rat | 健身搏猪 | 野猪人 | 4/4 | 回合结束：获宝石特训 | ② |
| Hired Mount | 受雇坐骑 | 龙 | 3/5 | 发动(2)：随机多彩幼龙 | ② |
| Locked-up Mutineer | 铐住的哗变者 | 海盗 | 6/3 | 亡语：获上锁宝箱 | ② |
| Malchezaar, Prince of Dance | 舞蹈王子玛克扎尔 | 恶魔 | 4/3 | 每回合 2 次刷新耗血而非铸币 | ② |
| Mummifier | 木乃伊工匠 | 亡灵 | 5/2 | 亡语：使另一亡灵获复生 | ① |
| Rescue Bot | 救援机器人 | 机械 | 2/1 | 嘲讽，亡语获维修作业（新法术） | ② |
| Sly Infiltrator | 狡猾的渗透者 | 野猪人 | 4/5 | 抉择：2 次免费刷新 / 3 血宝石 | ② |
| Sprightly Scarab | 机变甲虫 | 野兽 | 3/1 | 抉择：野兽 +1/+1 复生 / +4 攻风怒 | ② |
| Tasty Lobster | 美味龙虾 | 野兽 | 2/1 | 亡语：随机友方野兽 +2/+1（可成长） | ② |
| Trapped Clapper | 受困的钟舌恶魔 | 恶魔 | 2/2 | 亡语：下 3 次刷新加恶魔饲料 | ② |
| Treasure Parrot | 财宝鹦鹉 | 野兽/海盗 | 5/5 | 造成 35 伤后获点金之触（伤害计数器） | ③ |
| Wolf Pup | 狼宝宝 | 野兽 | 3/6 | 进击：其他随从 +4/+1 | ① |

### T4（30 张）

| 英文名 | 中文名 | 种族 | 身材 | 效果摘要 | 难度 |
|---|---|---|---|---|---|
| Air Baller | 空气投球手 | 元素 | 6/6 | 出售：随从 +2/+2，提升后续投球手 | ① |
| Ashen Corruptor | 灰烬腐蚀者 | 恶魔 | 6/6 | 英雄受伤后回溯，酒馆随从本回合 +2/+2 | ② |
| Banana Slamma | 香蕉猛猿 | 野兽 | 3/6 | 战斗中召唤野兽后其攻击翻倍 | ② |
| Bigwig Bandit | 顶尖大盗 | 海盗 | 4/6 | 进击：随机悬赏令（新法术） | ② |
| Boom-in-a-Box | 砰砰箱 | — | 5/10 | 嘲讽，战斗开始对其他随从 3 伤 | ① |
| Bramble Tunneler | 棘刺挖掘工 | 野猪人 | 3/6 | 进击：随机抉择牌 | ② |
| Bronze Timewalker | 青铜时光行者 | 龙 | 4/5 | 进击：随机多彩幼龙 | ② |
| Cage Gnawer | 啮笼鼠 | 野兽 | 2/7 | 友方野兽攻击时野兽 +2/+1 | ① |
| Dead Bellringer | 丧钟死灵 | 亡灵 | 3/6 | 发动(1)：另一亡灵获复生后消灭获 +4/+4 | ② |
| Drone Duplicator | 复映无人机 | 机械 | 5/2 | 圣盾，发动(1)：下次磁力翻倍 | ② |
| Enchanted Sentinel | 附魔哨卫 | 机械 | 3/5 | 磁力，酒馆法术 +1/+1 | ② |
| Gearfin | 机鳍鱼人 | 机械/鱼人 | 6/5 | 回合结束：获 2 张 1 费酒馆法术 | ② |
| Glambot | 炫彩机器人 | 机械 | 4/4 | 对机械施法时磁力吸附 4/4 卫星 | ② |
| Headhunter Gryphon | 猎头狮鹫 | 野兽 | 3/5 | 进击：随机野兽牌 | ② |
| Hoarding Hyena | 囤食土狼 | 野兽 | 4/6 | 进击：召唤美味龙虾 | ② |
| Imp-lusionist | 鬼影幻术师 | 恶魔 | 4/2 | 亡语：获理性癫狂（新法术） | ② |
| Imposing Percussionist | 奇瑰打击乐手 | 恶魔 | 4/4 | 战吼：发现恶魔，英雄受等星伤害 | ① |
| Kelp Keeper | 海藻护卫 | 鱼人 | 5/5 | 发动(1)：触发友方战吼 | ② |
| Living Prison | 活体监牢 | 元素 | 4/5 | 发动(1)：获本回合下购随从属性值 | ③ |
| Lovesick Balladist | 苦情民谣歌手 | 海盗 | 3/2 | 战吼：海盗 +1 血（花钱成长） | ② |
| Maritime Extortionist | 海上勒索师 | 海盗 | 7/7 | 本局每用一张金色 +7/+7 | ② |
| Maw Caster | 噬渊施法者 | 亡灵 | 4/5 | 战吼：消灭亡灵发现亡灵 | ② |
| Plaguerunner | 疫病行尸 | 亡灵 | 4/2 | 亡语：本局亡灵 +2 攻（战斗外 +4） | ② |
| Runic Arcanist | 符文奥术师 | 龙 | 2/4 | 战斗开始：施放闪亮的戒指 ×2 | ② |
| Sky-hatch Runaway | 天诞逃生飞龙 | 龙 | 4/7 | 发动(1)：触发友方进击 | ② |
| Snare Trapper | 圈套陷阱师 | 野猪人 | 4/4 | 抉择：随机野猪人 / 铸币上限 +1 | ② |
| Snarky Shark | 尖利的鲨鱼 | 野兽 | 4/5 | 出售：刷新+鱼饵（新系统） | ③ |
| Soulkeeping Jailer | 缚魂狱卒 | 恶魔 | 3/5 | 发动(2)：恶魔吞食酒馆随从 | ③ |
| Thorned Trailblazer | 刺棘开拓者 | 野猪人 | 4/5 | 抉择牌可同时有两种效果 | ② |
| Twilight Tidehunter | 暮光猎潮者 | 鱼人 | 4/6 | 对其施法：手牌最左 +8/+8 | ② |

### T5（24 张）

| 英文名 | 中文名 | 种族 | 身材 | 效果摘要 | 难度 |
|---|---|---|---|---|---|
| Air Revenant | 空气亡魂 | 元素 | 3/6 | 花 7 币后施放乘借东风 | ② |
| Barrier Banshee | 障蔽女妖 | 亡灵 | 7/7 | 友方复生后获圣盾 +7/+7 | ① |
| Cataclysmic Harbinger | 灾变先锋 | — | 6/10 | 回合结束：复制上施放法术 | ② |
| Charging Czarina | 蓄能女沙皇 | 机械 | 4/1 | 圣盾，施法时圣盾随从 +4 攻 | ② |
| Deft Deserter | 灵巧的逃亡者 | 恶魔 | 8/8 | 发动(1)：酒馆随从 +8/+8 及关键词 | ② |
| Devilish Distractor | 恶魔干扰者 | 恶魔 | 4/7 | 对其施法：酒馆随从本局 +2/+2 | ② |
| Draconic Warden | 龙族看护员 | 龙 | 7/4 | 战吼、亡语：随机多彩幼龙 | ① |
| Drustfallen Butcher | 德鲁斯特堕落屠夫 | 亡灵 | 2/7 | 复仇(3)：获宰割 | ① |
| Enterprising Escapee | 上进的逃兵 | 海盗 | 6/6 | 花 5 币获上锁宝箱 | ② |
| Felboar | 邪能野猪人 | 恶魔/野猪人 | 2/6 | 施 3 法后吞食酒馆随从 | ② |
| Felfire Conjurer | 邪火咒龙 | 恶魔/龙 | 6/5 | 回合结束：本局酒馆法术 +1/+1 | ② |
| Flourishing Frostling | 缤纷冰灵 | 元素 | 2/1 | 本局每用一张元素 +2/+1 | ② |
| Insatiable Ur'zul | 贪食的乌祖尔 | 恶魔 | 4/6 | 嘲讽，用恶魔牌后吞食酒馆随从 | ② |
| Kalecgos, Arcane Aspect | 奥术守护者卡雷苟斯 | 龙 | 4/12 | 触发战吼后龙 +2/+2 | ② |
| Lurking Leviathan | 深潜巨兽 | 野兽 | 3/9 | 召唤野兽 +3 攻并成长 | ② |
| Primalfin Lookout | 蛮鱼斥候 | 鱼人 | 3/2 | 战吼：有其他鱼人则发现鱼人 | ① |
| Proud Privateer | 骄傲的私掠者 | 海盗 | 8/8 | 悬赏令施放两次 | ② |
| Rodeo Performer | 竞技表演者 | — | 3/4 | 战吼：发现酒馆法术 | ① |
| Sewer Lord | 下水道老鼠头目 | 野兽 | 4/6 | 亡语：召唤下水道老鼠 | ① |
| Shamanic Tidecaller | 萨满招潮者 | 鱼人 | 5/7 | 对鱼人施法：鱼人 +3/+3 | ② |
| Shipwrecked Rascal | 船难海贼 | 海盗 | 5/4 | 战吼、亡语：随机悬赏令 | ② |
| Spark Snapper | 火花破坏机 | 机械 | 5/5 | 用机械牌磁力 2/2 卫星并成长 | ② |
| Tichondrius | 提克迪奥斯 | 恶魔 | 4/4 | 英雄受伤后恶魔 +4/+4 | ① |
| Turquoise Skitterer | 绿松石飞掠虫 | 野兽 | 5/5 | 亡语：本局甲虫 +5/+5 并召唤 | ② |

### T6（22 张）

| 英文名 | 中文名 | 种族 | 身材 | 效果摘要 | 难度 |
|---|---|---|---|---|---|
| Balinda Stonehearth | 巴琳达·斯通赫尔斯 | — | 6/6 | 目标友方法术施放两次 | ② |
| Choral Mrrrglr | 合唱鱼人 | 鱼人 | 6/6 | 战斗开始：获手牌随从属性值之和 | ② |
| Crimson Vindicator | 赤红守备巨龙 | 龙 | 8/9 | 圣盾，进击施放威猛龙息（新法术） | ② |
| Deathstrider | 逐亡陆行鸟 | 野兽 | 10/11 | 友方进击攻击后触发最左亡语 | ③ |
| Elemental of Surprise | 惊喜元素 | 元素 | 8/8 | 圣盾，可与任意元素三连（三连规则改动） | ③ |
| Eredar Escapist | 艾瑞达逃脱大师 | 恶魔 | 6/8 | 英雄受 4 伤后获腐化糕点 | ② |
| Eternal Summoner | 永恒召唤者 | 亡灵 | 8/1 | 复生，亡语召唤永恒骑士 | ① |
| Falling Sky Golem | 坠落的飞天魔像 | 机械 | 4/2 | 圣盾，本局每触发亡语 +4/+2 | ② |
| Forsaken Weaver | 被遗忘者纺织工 | 亡灵 | 3/8 | 施法后亡灵本局 +3 攻 | ② |
| Gatekeeper Amalgam | 守门融合怪 | 全部 | 6/6 | 对其施法：施放乱放的茶具 | ② |
| Hooktusk, Master Marauder | 掠夺大师钩牙 | 海盗 | 4/4 | 发现牌后海盗 +1/+1（金卡成长） | ② |
| Magicfin Mycologist | 魔鳍真菌学家 | 鱼人 | 4/8 | 购法术后获 1/1 鱼人并"教"它法术 | ③ |
| Ravaging Scorpid | 暴虐巨蝎 | 野兽 | 6/7 | 友方攻击后本局甲虫 +5/+5；亡语甲虫 | ② |
| Silent Deliverer | 安静的投递员 | 海盗 | 7/7 | 战吼：随机 4 星金色（无三连奖励） | ② |
| Sky Admiral Rogers | 空军上将罗杰斯 | 海盗 | 4/5 | 花 9 币随机悬赏令 | ② |
| Snazzy Phantom | 时尚魅影 | 亡灵 | 6/8 | 友方复生后最右亡灵获其攻击 | ② |
| Turbo Hogrider | 极速野猪骑士 | 野猪人 | 5/7 | 用抉择后野猪人各用血宝石 | ② |
| Twisted Wrathguard | 扭曲的愤怒卫士 | 恶魔 | 8/8 | 出售后下刷加恶魔饲料 | ② |
| Tyrael | 泰瑞尔 | — | 10/10 | 发动(1)：随从变 50/50 | ② |
| Unbound Tempest | 无羁雷暴 | 元素 | 3/12 | 用 3 元素后获酒馆最高血随从属性 | ② |
| Utility Drone | 多面辅助无人机 | 机械 | 4/5 | 回合结束：每磁力效果 +4/+5 | ② |
| Veteran Brigand | 老牌恶匪 | 野猪人 | 8/8 | 抉择：全场 3 血宝石 / 3 弹幕 | ② |

### T7（5 张）

| 英文名 | 中文名 | 种族 | 身材 | 效果摘要 | 难度 |
|---|---|---|---|---|---|
| Champion of Sargeras | 萨格拉斯的勇士 | 恶魔 | 8/8 | 战吼、亡语：酒馆随从本局 +8/+8 | ① |
| Jailbird Juggernaut | 囚牢恶霸 | 野猪人 | 6/15 | 进击：召唤同属性魔像并率先攻击 | ③ |
| Polarizing Beatboxer | 极性B-Box拳手 | 机械 | 5/10 | 对不同随从磁力时联动磁力自己 | ③ |
| Stalwart Kodo | 坚韧的科多兽 | 野兽 | 16/32 | 战斗中召唤后获最大属性（限 3 次） | ② |
| Stone Age Slab | 石器时代顽石 | 元素 | 10/10 | 购买后 +20/+20 并翻倍（每回合 1 次） | ② |

**B1 难度统计**：① 22 张 / ② 89 张 / ③ 10 张。

---

## C 类：两边都有但不一致（34 张）

### 大改（星级/效果不同，17 张）

| 卡 | 模拟器 | 正式服 | 改动点 |
|---|---|---|---|
| Devout Hellcaller | T4 2/2，友方死亡 +1/+2 | T3 4/4，友方恶魔造成伤害后永久 +2/+2 | 星级、身材、效果全改 |
| Prosthetic Hand | T4 | T3（3/1，磁力复生） | 星级 |
| Accord-o-Tron | T4 5/5 | T3 3/3 | 星级、身材 |
| Trench Fighter | T4 6/6 纳迦 | T3 3/3 野猪人 | 星级、身材、种族 |
| Sly Raptor | T4 1/4，亡语召唤骷髅 | T3 1/3，亡语随机召唤 6/6 野兽 | 星级、身材、效果 |
| Roadboar | T3 3/4 | T2 2/4 | 星级、身材 |
| Nomi, Kitchen Nightmare | T5 4/4，打出元素 +2/+2 | T5 6/6，使用元素后酒馆元素本局 +4/+4 | 身材、效果 |
| Razorfen Vineweaver | T5 2/1 | T5 5/5，进击对自己用 3 张永久血宝石 | 身材、效果 |
| Goldrinn, the Great Wolf | T6 8/8，亡语野兽 +8/+8 | T5 7/7，亡语野兽 +7/+7 直到下回合 | 星级、身材、效果持续时间 |
| Nightmare Par-tea Guest | T6 6/6 | T5 3/3 | 星级、身材 |
| Sanguine Refiner | T6 3/10 | T5 3/8 | 星级、身材 |
| Sanguine Champion | T7 18/3 无种族 | T6 9/4 野猪人 | 星级、身材、种族、效果 |
| Futurefin | T7 7/13，相邻 +7/+13 | T7 7/13，手牌最左获本随从属性值 | 效果重写 |
| Stitched Salvager | T7 16/4，亡语全场 +4/+4 | T7 16/4，战斗开始消灭左边，亡语召唤其复制 | 效果重写 |
| The Last One Standing | T7 12/12 无种族，进击 +12/+12 | T7 15/15 全部种族，进击每类型 +15/+15 | 身材、种族、效果 |
| Fauna Whisperer | T6 4/9，相邻 +3/+3 | T6 4/9，回合结束对相邻施放自然祝福 | 效果 |
| Primitive Painter | T6 3/8，打出鱼人 +1/+2 | T6 3/8，用 3 星以下牌后鱼人 +3/+3 | 效果 |

### 小改（身材/种族微调，17 张）

| 卡 | 模拟器 | 正式服 |
|---|---|---|
| Wrath Weaver | 1/4 | 1/3 |
| Razorfen Geomancer | 2/3 | 2/1 |
| Aureate Laureate | 1/1 | 2/2 |
| Mechagnome Interpreter | 2/3 | 3/1 |
| Soul Rewinder | 4/1 | 4/2 |
| Briarback Drummer | 5/2 | 5/3 |
| Waveling | 6/1 | 5/1 |
| Bream Counter | 4/4 | 6/6 |
| En-Djinn Blazer | 4/4 | 5/5 |
| Razorfen Flapper | 5/3 | 6/2 |
| Fire-forged Evoker | 8/5 | 8/6 |
| Blade Collector | 无种族 | 海盗 |
| Flaming Enforcer | 元素 | 元素/恶魔 |
| Firescale Hoarder | 龙 | 纳迦/龙 |
| Costume Enthusiast | 无种族 | 鱼人 |
| Obsidian Ravager | 无种族 | 龙（另：正式服进击还打相邻） |
| Highkeeper Ra | 战吼+亡语 | 正式服多一个进击 |

---

## D 类：模拟器独有（1 张）

- `PSYCHUS`（T7，1/1，无种族）：正式服现行池（含 7 星 12 张）中没有这张卡。疑似自定义/未来卡。建议：要么从卡池移除（或移到 ROTATED_OUT），要么确认来源后保留。请用户定夺。

---

## 实施建议

1. **先做 A**：91 个枚举名加入 `ROTATED_OUT`，一行改动，零风险。注意 `DUNE_DWELLER` 9/22 回归时要移出。
2. **再做 C 的小改**：17 张纯数值/种族对齐，直接改 `card_def.py` 对应条目。
3. **然后 B1 按难度推进**：① 22 张（现有机制直接表达，最快）；② 89 张是主体——其中"发动""抉择""塑造法术""悬赏令/上锁宝箱"等新机制建议先做通用系统再批量补卡；③ 10 张（鱼饵、磁力联动、三连规则改动等）最后。
4. **C 的大改** 17 张穿插在 B1 之前/之中处理（多为数值+效果重写）。
5. **B2 跳过**，等 9/22 补丁实装后按新卡池（畸变怪等）另做一次审计。
6. **D 的 Psychus** 等用户确认后再动。
7. 每补一批跑 `pytest tests -q`，重点看 `test_pool.py` 的总数断言（总数会变，需同步更新期望）。
