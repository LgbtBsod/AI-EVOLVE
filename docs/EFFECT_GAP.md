# Coverage corpus: 60 iconic abilities vs SPEC (EFFECT_SYSTEM_DESIGN) and canon (42 kinds)

Canon 42 = OP_HANDLERS in src/effects/ops.py. Aliases to canon: teleport/dash/pull/push/swap -> `move`; status/debuff -> `apply_effect`/`buff`; restore/consume -> `heal`/`drain`; create_minion -> `summon`; use_learned -> `use_learned_technique`; cancel/nullify_technique -> `cancel_technique`/`nullify`. Column 'canon?' counts an ability yes only if its whole intent, not a weakened version, fits.

| # | character | source | ability | SPEC kinds | SPEC lacks (proposed name) | canon 42? |
|---|---|---|---|---|---|---|
| 1 | Gojo | JJK | Infinity | aura,block,immune,untargetable | - | yes |
| 2 | Gojo | JJK | Hollow Purple | fusion_strike,deal | - | no |
| 3 | Gojo | JJK | Domain Unlimited Void | reality_marble,zone,status,rule_override | sure_hit flag on rule (`zone.sure_hit`) | no |
| 4 | Sukuna | JJK | Malevolent Shrine | zone,deal,aura | - | no |
| 5 | Mahoraga | JJK | Adaptation wheel | adapt,rotate_wheel,display_wheel | - | yes |
| 6 | Toji | JJK | Heavenly Restriction | binding_vow,mod,remove_restriction | - | yes |
| 7 | Naruto | Naruto | Shadow Clone | summon,create_minion | memory return on dispel (`on_dispel` trigger + `inherit_memory`) | no |
| 8 | Naruto | Naruto | Rasengan | deal,dash | - | yes |
| 9 | Naruto | Naruto | Kurama mode | transform,timed_power_up,mod | - | no |
| 10 | Sasuke | Naruto | Sharingan copy | copy_technique,perceive | - | no |
| 11 | Itachi | Naruto | Tsukuyomi | enter_dream,hypnosis,time_as_space | subjective time dilation (`subjective_time` mult) | no |
| 12 | Kakashi | Naruto | Kamui phase | teleport,untargetable,dodge | - | yes |
| 13 | Madara | Naruto | Infinite Tsukuyomi | apply_status_to_world,hypnosis,enter_dream | - | no |
| 14 | Ichigo | Bleach | Getsuga Tenshou | deal | - | yes |
| 15 | Aizen | Bleach | Kyoka Suigetsu | hypnosis,perceive,reveal | false-percept layer (`false_percept`) | no |
| 16 | Law | One Piece | Room / Shambles | zone,swap,teleport,space_manipulation | zone op on arbitrary objects inside (`zone.on_inside`) | no |
| 17 | Luffy | One Piece | Gear 5 | transform,stance,mod,timed_power_up | - | no |
| 18 | Luffy | One Piece | Rubber body | resist,immune | - | yes |
| 19 | Akainu | One Piece | Magma fist | deal,status | - | yes |
| 20 | Doflamingo | One Piece | Parasite strings | command,possess,dominance | persistent multi-target control channel (`control_link`) | no |
| 21 | Gon | HxH | Jajanken + vow | binding_vow,deal,mod,consume | - | yes |
| 22 | Kurapika | HxH | Chain Jail | binding_vow,nullify,status | - | yes |
| 23 | Hisoka | HxH | Bungee Gum | pull,status,mark | - | yes |
| 24 | Netero | HxH | Guanyin Zero | deal,dash,summon | - | yes |
| 25 | Dio | JoJo | The World time stop | global_time_scale,status,delay | per-entity exemption from time scale (`time_scale.exempt`) | no |
| 26 | Goku | Dragon Ball | Kamehameha | deal,consume | - | yes |
| 27 | Goku | Dragon Ball | Instant Transmission | teleport,mark | - | yes |
| 28 | Goku | Dragon Ball | Super Saiyan | transform,mod | - | yes |
| 29 | Beerus | Dragon Ball | Hakai | erase | - | no |
| 30 | Saber | Fate | Excalibur | deal,consume | - | yes |
| 31 | Gilgamesh | Fate | Gate of Babylon | create_minion,summon,deal | - | yes |
| 32 | Archer | Fate | Unlimited Blade Works | reality_marble,copy,zone | - | no |
| 33 | Medea | Fate | Rule Breaker | cancel_technique,sever | - | yes |
| 34 | Lancer | Fate | Gae Bolg | reverse_causality,precognition | fate lock: hit resolved before cast (`fate_lock`) | no |
| 35 | Heracles | Fate | God Hand | on_lethal,status,counter_delta | - | no |
| 36 | Iron Man | Marvel | Repulsor + arc reactor | deal,consume,dash | - | yes |
| 37 | Dr Strange | Marvel | Dormammu time loop | time_loop,snapshot,state_rewind | - | no |
| 38 | Thanos | Marvel | Snap | erase,rule | random-half sample filter (`filter.sample`) | no |
| 39 | Spider-Man | Marvel | Spider sense | precognition,dodge,reveal | - | no |
| 40 | Scarlet Witch | Marvel | Reality warp | rule_override,create_ex_nihilo,transform | - | no |
| 41 | Magneto | Marvel | Magnetism | pull,push,polarity_control,telekinetic_weapon | - | no |
| 42 | Wolverine | Marvel | Regeneration | heal | - | yes |
| 43 | Flash | DC | Speed Force | mod,dash | local `time_scale` stat | no |
| 44 | Harry Potter | HP | Expelliarmus | cancel_technique,confiscate,push | - | no |
| 45 | Harry Potter | HP | Patronus | summon,immune | - | yes |
| 46 | Voldemort | HP | Horcruxes | on_lethal,snapshot,restore_state | respawn at anchor object (`respawn_at`) | no |
| 47 | Snape | HP | Sectumsempra | deal,status | - | yes |
| 48 | Gandalf | LOTR | You shall not pass | block,zone,push | - | yes |
| 49 | Sauron | LOTR | One Ring dominion | dominance,command,possess | - | no |
| 50 | Paul Atreides | Dune | Prescience | precognition,perceive | - | no |
| 51 | Bene Gesserit | Dune | The Voice | command,hypnosis | - | no |
| 52 | Shai-Hulud | Dune | Worm summon | summon | - | yes |
| 53 | Chosen Undead | Dark Souls | Estus flask | heal,consume | - | yes |
| 54 | Light Yagami | Death Note | Write a name | write,kill,delay,wish | cause-of-death string on kill (`kill.cause`) | no |
| 55 | Ryuk | Death Note | Shinigami eyes | reveal,perceive | - | no |
| 56 | Geralt | Witcher | Igni | deal,status | - | yes |
| 57 | Geralt | Witcher | Quen | absorb_damage,block | - | yes |
| 58 | Geralt | Witcher | Axii | hypnosis,command,set_faction | - | yes |
| 59 | Aang | Avatar | Avatar State | transform,mod,on_lethal,timed_power_up | - | no |
| 60 | Katara | Avatar | Bloodbending | blood_manipulation,possess,command | - | no |

## Frequency of kinds (orders the implementation, most-used first)

| rank | kind | abilities | canon op |
|---|---|---|---|
| 1 | deal | 13 | deal |
| 2 | status | 8 | apply_effect |
| 3 | mod | 7 | mod |
| 4 | command | 5 | no |
| 5 | consume | 5 | drain |
| 6 | hypnosis | 5 | no |
| 7 | summon | 5 | summon |
| 8 | transform | 5 | no |
| 9 | zone | 5 | no |
| 10 | dash | 4 | move |
| 11 | perceive | 4 | no |
| 12 | binding_vow | 3 | binding_vow |
| 13 | block | 3 | block |
| 14 | immune | 3 | immune |
| 15 | on_lethal | 3 | no |
| 16 | possess | 3 | no |
| 17 | precognition | 3 | no |
| 18 | push | 3 | move |
| 19 | reveal | 3 | - |
| 20 | teleport | 3 | move |
| 21 | timed_power_up | 3 | no |
| 22 | aura | 2 | no |
| 23 | cancel_technique | 2 | cancel_technique |
| 24 | create_minion | 2 | summon |
| 25 | delay | 2 | no |
| 26 | dodge | 2 | no |
| 27 | dominance | 2 | no |
| 28 | enter_dream | 2 | no |
| 29 | erase | 2 | kill (weaker) |
| 30 | heal | 2 | heal |

Reading: `deal`, `status`, `mod`, `summon`, `consume`, `dash`, `block`, `immune` are already canon. The gap starts at rank 6-14: `transform`, `hypnosis`, `command`, `perceive`, `timed_power_up`, `zone`, `teleport`-as-own-kind, `possess`, `precognition`, `on_lethal`. Build order: transform/stance (5), zone+aura (7), hypnosis/command/possess (control family, 5+5+3), perceive/reveal/precognition (perception family, 10 combined), on_lethal/delay (trigger family).

## Percentages (60 abilities, honest)

| basis | count | % |
|---|---|---|
| fully expressible with canon 42 today | 28 | 46.7% |
| fully expressible with the full SPEC as written | 48 | 80.0% |
| SPEC + proposed additions from column 'SPEC lacks' (12 names) | 55 | 91.7% |

Canon 28 counts abilities whose whole intent fits; Super Saiyan/Kurama-style `transform` is counted yes only where a plain `buff` carries the fantasy (Super Saiyan yes, Kurama/Gear 5 no: form change, new moves, drawback). SPEC 48 = 60 minus the 12 rows with a named lack. 55 = the 12 lacks fixed, minus 5 that still need semantics, not names.

## Abilities that break the model (even with additions)

- Gae Bolg (34): effect resolved before cast means causality is a rewrite of already-simulated ticks; needs a two-pass resolve, conflicts with a forward-only deterministic timeline.
- Scarlet Witch reality warp (40): `create_ex_nihilo` + `rule_override` has no bound; any validation rule that limits it turns it into a preset list.
- Dr Strange loop (37): `time_loop` needs whole-game snapshot/rewind; possible for the sim, but the player/hero memory carry-over is a second state stream (persist across rewind).
- Dio time stop (25) and Flash (43): per-entity time scale needs the tick loop to honour a per-unit clock; `src/core/timeline.py` is unwired.
- Death Note (54) and Thanos snap (38): need named-target lookup and a random sample over world entities at the same seed; deterministic only with a seeded RNG stream per op.

## Risks / limits of this corpus

- 60 rows are hand-tagged by one author; the kind counts are a ranking signal, not a measurement. Rows repeat the same fantasy (deal-family 13 of 60), so long-tail kinds are undercounted.
- Spec kinds vs canon names differ (`status` vs `apply_effect`, `consume` vs `drain`, `dash/teleport/pull/push` vs `move`): alias, do not add handlers.
- Marvel/Fate rows use meta-layer kinds (`reality_marble`, `rule_override`, `time_loop`) that the spec lists in RULES/STATE layers; these mix layers with the EFFECT layer and are the costliest 12% of the corpus.


# Effect gap: parts 1-2 (Effect/Op fields, layers, kinds)

Legend: canon = src/effects/schema.py (Effect 309-353, Op 252-306, OP_KINDS :30), ops.py OP_HANDLERS :896 (42 kinds). Sizes S/M/L. Line numbers of ops.py = def op_X.

## 1. Effect fields (spec 1.1)

| item | canon status | proposed canon form | depends on | size | unlocks |
|---|---|---|---|---|---|
| id, tags, ops | yes schema.py:310-313 | as is | - | - | all |
| layer | no | Effect.layer str (default "effect"), enum in lua_content/kinds.lua; manager dispatches by layer | F0 layers | S | rules/state/world abilities |
| version | no | Effect.version int, migration hook in from_json | - | S | save compat |
| trigger | yes :311 (passive/condition/event/applied) | as is | - | - | all |
| duration, cooldown | yes :314-315 | as is | - | - | all |
| cost | no | Effect.cost {stat, value} = implicit drain op on activation; reuse op_drain + fail | drain | S | mana/HP/ammo casts, Contessa, Gojo |
| stacks | partial :316 (dict, rules thin) | StackRule {max, on_max, decay}; reuse Op.max_stacks | - | M | Mahoraga wheel, Sukuna stacks |
| charges | no | Effect.charges {max, regen, per} sharing cooldown code | cooldown | S | limited-use ults, Kunai |
| priority | partial (active_cc priority only) | Effect.priority int, sort in manager | - | S | rule overrides, domain clash |
| exclusive_group | no | Effect.exclusive_group; on apply purge same-group (op_purge) | purge | S | stances, domains, forms |
| conflict_with | no | Effect.conflict_with[] checked at apply | exclusive_group | S | incompatible transformations |
| on_enter / on_exit | partial: trigger applied / event only | Effect.on_enter, on_exit Op[]; run in manager at activate/expire | manager | M | transformations, domain open/close |
| faction, autonomous, ai_profile | partial: set_faction/set_aggro ops :785-817 | ALIAS Effect.faction -> on_enter set_faction; ai_profile = Effect field feeding enemy_ai | set_faction | M | Sukuna fingers, shikigami, minions |
| counter_display | partial: rotate/display/halt_wheel :825-888 | Effect field that emits display_wheel on_enter | wheel ops | S | Mahoraga wheel UI |
| tiered_progression | partial: escalate/deescalate :849-858 | Effect field = list of threshold -> escalate | threshold | M | power-ups, Saitama-like tiers |
| adaptive_response | partial: adapt/unadapt :670-715 | Effect field sugar over op_adapt | adapt | S | Mahoraga, Borg |
| persistent_memory | partial: learn, register_phenomenon :649,750 | Effect field = memory_key namespace saved with profile | state layer | M | Death Note, learning |
| amplify, threshold, meta | canon-only :321-325 | keep; document as extensions | - | - | Lost My Self |

## 2. Op fields (spec 1.2)

| item | canon status | proposed canon form | depends on | size | unlocks |
|---|---|---|---|---|---|
| kind, target, stat, op, value, scale | yes :253-258 | as is | - | - | all |
| when, fail | yes :259-260 (fail documented for drain only) | generalize fail to any op with when/resource fail | - | S | conditional casts |
| duration, cooldown, extend, buff_id, flags | yes :261-265 | as is | - | - | buffs |
| max_stacks, permanent | no | Op.max_stacks int; Op.permanent bool (= duration nil + flag "permanent") | buff | S | stacking marks, permanent steals |
| effect_id | partial: apply_effect reads o dict | add typed field; ALIAS status_id/ability_id -> effect_id when namespaced | registry | S | statuses, combos |
| status_id, ability_id, item_id | no | Op.status_id -> lua_content/statuses; ability_id -> abilities.lua; item_id -> items | statuses.py | M | apply status, cast ability, grant item |
| memory_key | no | Op.memory_key for learn/steal/copy stores | persistent_memory | S | Rogue copy, Sharingan |
| filter, source_filter | no | Op.filter (target predicate), source_filter (event source) using Condition strings | Condition | M | reactive parries, "only magic" |
| ops (nested) | no | Op.ops list run by op_conditional/delay/zone | recursion guard | M | delay, zone tick, Kamehameha charge |
| zone, summon, tick | no (op_summon :453 minimal) | ZoneDef/SummonDef/TickDef dicts in Op; tick reuses scheduler Tick :237-240 | zones | L | domains, barriers, auras, turrets |
| signature, counter_delta, tier_advance, threshold (Op) | no | Op.signature = tag for adapt; counter_delta = ALIAS of escalate/rotate_wheel value; tier_advance = ALIAS escalate | wheel ops | S | Mahoraga, ranks |
| ai_profile, faction (Op) | partial | passes to set_faction op | - | S | allies, tamed |
| layer_meta | no | Op.layer_meta dict, ignored by non-owner layers | layers | S | layer-specific extras |

## 3. Layers (spec 2.1)

| item | canon status | proposed canon form | depends on | size | unlocks |
|---|---|---|---|---|---|
| effect | yes (manager/ops) | default | - | - | combat |
| rules | partial: lua_content/effect_rules.lua | Effect.layer="rules"; rule_override ops write into effect_rules table | F0 | M | Jojo/Zawarudo rules, Geass |
| state | partial: learn/register_phenomenon | memory/snapshots via src/core registry (unwired) | core wiring | L | time loop, save-scum |
| world | no | global host Effect target "world" | timeline | L | apocalypse, weather |
| meta, narrative | no | sandbox events only (no file IO), see risks | - | L | fourth-wall, Doki Doki |
| ontological, conceptual | no | data-only tier stat + concept flag | - | L | Anti-Spiral, One Above All |
| social | no | contract via binding_vow :617 + reputation stat | binding_vow | M | contracts, Kira |
| entity | no | slots as Lua data | - | M | decks, chips, Persona |
| temporal | no | timeline.py (unwired) | timeline | L | loops, Steins;Gate |

## 4. Kinds present in canon and spec (yes)

deal, heal, drain, set, mod, buff, kill, summon, purge, mark, detonate, block, resist, immune, nullify, untargetable, sever, adapt, unadapt, reset_adaptation, learn, observe_phenomenon, register_phenomenon, set_faction, set_aggro, set_targeting, retarget, clear_aggro, escalate, deescalate, rotate_wheel, display_wheel, halt_wheel, absorb_damage, cancel_technique: yes (ops.py handlers, see :378-888).

## 5. Aliases (kind in spec = canon op, only the name differs)

| spec kind | canon op | note |
|---|---|---|
| remove_effect | remove_buff :438 | same |
| oath_binding | binding_vow :617 | rename |
| use_learned | use_learned_technique :761 | rename |
| nullify_technique | cancel_technique :596 | variant |
| learn_technique, copy_technique, technique_absorb | learn :649 | flag steal/copy |
| status, debuff, timed_power_up | apply_effect :443 / buff :412 | negative value, status_id |
| consume, restore, fuel_consume | drain :393 / heal :387 | stat=resource |
| sever_magic_circuits | sever :630 | stat=magic |
| tier_advance, progressive_state, counter_delta | escalate :849 / rotate_wheel :825 | |
| create_minion | summon :453 | |
| pull, push, dash, teleport, swap | move :457 | mode field |
| erase | kill :449 | flag erase (no corpse/loot) |
| conditional | Op.when + fail | not a kind |
| rule, rule_override (effect layer) | Op layer rules | one op |
| narrator, narrative_agent | one kind | dedupe in spec |
| dodge, reflect, counter | block :604 / absorb_damage :611 | flag reflect |
| awaken, remove_restriction | mod / nullify | |
| trigger_true_form, extend | canon-only | keep |

## 6. Missing kinds by family (implementation order)

| # | family | kinds (missing in canon) | depends on | size | unlocks |
|---|---|---|---|---|---|
| 1 | stance/transform | transform, stance, core_swap, transform_elemental, self_transfigure, awaken | on_enter/on_exit, exclusive_group | M | Super Saiyan, Gears, Bankai |
| 2 | conditionals/time | delay, on_lethal, conditional, gamble, gacha | Op.ops | M | Cheat Death, Kazuma luck |
| 3 | reactive combat | counter, reflect, dodge, redirect_harm, sympathetic_damage, precision_strike, create_weak_point | filter | M | Aikido, voodoo, Sukuna cleave |
| 4 | movement | teleport, dash, pull, push, swap | move | S | Flash, Kurama, Gravity |
| 5 | steal/copy/learn | steal, steal_stat, absorb, copy, copy_last_cast, inherit_all, transfer_stat, technique_absorb, confiscate | learn, memory_key | M | Rogue, Meruem, Sharingan |
| 6 | statuses | status_transform, status_mod, debuff, hypnosis, tame, command, temptation | statuses.py | M | Geass, Shaman |
| 7 | vision/perception | reveal, grant_vision, perceive, precognition, advisor | can_see | S | Byakugan, Mirai |
| 8 | zones/auras | zone, aura, zone_mod, reality_marble, block_physics | ZoneDef | L | Domain Expansion, Barrier |
| 9 | summons/possession | possess, body_swap, soul_transmutation, soul_merge, fusion_strike | summon | L | Fusion, Ghost Rider |
| 10 | stat limits | unbounded, mass_resurrect, wish | stat registry | M | Lord Ainz, Dragon Balls |
| 11 | state/time | snapshot, restore_state, load_state, state_rewind, time_loop, time_direction, retroactive_erase, time_erase, global_time_scale, causality_control, reverse_causality, pan_temporal_control, time_as_space, nonlinear_time_perception, enter_dream, memory_block, hack_consciousness | core/timeline | L | Subaru, Okabe, Dio |
| 12 | world | apply_status_to_world, thresholds, world_reset, universe_reset, global_event | world layer | L | Thanos, Madoka |
| 13 | read/write/naming | read, write, rename, rule_entity, concept_*, embody_concept, domain_control, change_tier, create_ex_nihilo | conceptual | L | Death Note, Aizen |
| 14 | social/entity | contract, contract_manipulation, dominance, reputation, diplomacy, narrative_warfare, slot_system, reagent_slot, identity_source, blood_manipulation, telekinetic_weapon, space_manipulation, polarity_control | binding_vow | M | Fate contracts, Persona |
| 15 | meta/narrative/visual | play_anim, play_sound, file_*, save_corruption, game_transform, close_game, author_contact, see_panels, panel_jump, off_panel_win, rule_authority, narrator, narrative_hook, fourth_wall, goal_seek | sandbox events | L | Monika, Deadpool |

Order: 4 -> 1 -> 2 -> 3 -> 6 -> 5 -> 7 -> 10 -> 8 -> 9 -> 14 -> 11 -> 12 -> 13 -> 15. Families 1-7 reuse existing ops (about 60 percent alias/variants).

## Risks / conflicts with canon

- Naming: spec `status`/`remove_effect`/`oath_binding`/`use_learned` vs canon `apply_effect`/`remove_buff`/`binding_vow`/`use_learned_technique`; keep canon names, accept spec names as loader aliases.
- Spec refs are wrong: spec says kinds at "3.x", target at "4.1", stat "5.1"; real sections are 2.2, 3.1, 3.2. Fix the spec.
- Spec `narrator` and `narrative_agent` duplicate; `rule` and `rule_override` too.
- Semantics: spec Op.ops for zone/delay/fail vs canon fail only for drain; recursion needs depth cap.
- Determinism: gacha/gamble need a seeded RNG stream from host, never random.
- Layer mixing: meta layer (file_delete, close_game, save_corruption) must stay sandbox events, never real IO.
- Effect.threshold in canon (hp_cross) differs in meaning from spec Op.threshold (Threshold ext, 4.5); use different names.
- src/core/{registry,timeline}.py are unwired; state/temporal/world layers depend on wiring, big blast radius.


# Effect gap: parts 7, 8, 10 (registries, runtime modules, principles)

Line numbers are from grep/outline reads; nothing was run.

## A. Runtime modules (SPEC part 8, 23 rows)

| item | canon status | proposed canon form | depends on | size | unlocks |
|---|---|---|---|---|---|
| EffectManager | yes, `manager.py:414` (`cast :661`, `emit :715`, `update :483`) | keep. Shrink it to a facade over the modules below | EventBus, Timeline | M | all |
| OpExecutor | yes, `ops.apply_op :931`, `OP_HANDLERS`, `OpHost :257`. Two hosts (manager, `EffectRuntime` runtime.py:499) | ALIAS OpExecutor = `ops.apply_op`. Later a Rust dispatcher over numeric kind ids | numeric ids | L | all |
| ConditionEvaluator | yes, `runtime.compile_pred/eval_pred :236,244` (AST whitelist), `ops._threshold_ok :315` | ALIAS ConditionEvaluator = `runtime.eval_pred` | none | S | conditional abilities |
| SelectorResolver | partial, `manager._targets :777`. `ally/allies` resolve to the caster only, `area` includes the caster (APP_SPECIFICS 3.1) | extract `selectors.py` with a table by selector id. Reuse `_in_arc :1185`. Add real ally/faction selectors via FactionManager | FactionManager | M | AoE heals, "all enemies", chains |
| ValueEvaluator | yes, `ops.resolve_value/compute_amount :137,150` | ALIAS = `ops.resolve_value` | none | S | value-source abilities |
| ScaleEvaluator | partial, `schema.Scale :201` plus mod-math inside ops | ALIAS = `Scale` plus `apply_mod_math :198`. Move the scale logic into one function | none | S | stacking scalers |
| ModifierStack | partial, layered mods in `EffectRuntime` and `EntityState` (`manager.py:174`), `StatCache :158`. Fields are mutated live, base = `field - applied` (APP_SPECIFICS 3.1) | new `modstack.py`: per-entity dict of stat id to a list of (source id, op, value, order). Add one recompute function that replaces the `Unit._eff` push. Rust twin: a batch fold over columns | numeric stat ids, Timeline (undo) | L | buffs, debuffs, "steal stats", copy abilities |
| DamagePipeline | yes, `damage.py` (`resolve_hit :251`, `roll_hit :282`, Rust twin, `cc_adjust :403`) | keep. This is the model for the other modules (pure kernel + Python twin) | none | S | all damage |
| EventBus | partial, `manager.emit :715` (owner-only, depth cap 6, `MAX_EVENT_DEPTH :75`, 11 event kinds). Separate `src/core/event_system.py` (blinker, shared globals) and `AsyncEventBus` (dead) | `bus.py`: numeric event ids, subscribers by (event, entity or global), deterministic order = registration order. `emit` stays the alias. Add `combat_start/combat_end/on_shield_break`, which are declared but never emitted (`schema.py:113-117`) | numeric ids | M | reactions to others' events, counters, "on ally death" |
| Timeline | no in canon. `src/core/timeline.py` (418 lines: `Event`, `commit`, `rewind :248`, `fork :332`, `link_causal :152`) is unwired and used only by `tests/core/` | wire it as the recorder for the manager: every `emit`/`_damage` becomes `commit(Event)` with an int id and a tick. Keep `commit/query/rewind/fork`. Drop `attach_event_system` (unless the blinker bus is removed) | int tick clock (virtual clock in `probe_runtime`), EventBus | L | time rewind/loop, replay, prediction, "undo damage", causality |
| SnapshotManager | partial, `timeline.StateSnapshot :83` and `capture_snapshot :208` (unwired) | provider protocol `capture(entity_ids) -> dict` in Timeline; the manager implements it | Timeline, ModifierStack | M | rewind, save-state, revive at a past HP |
| ZoneManager | no. Zones and auras exist only in the spec (ZoneDef 5.1) | new `zones.py`; a zone = an entity-less effect with a tick and a shape. Reuse `op_summon`, `Periodic :235` and `_every :915` for the tick | EventBus, SelectorResolver | M | domains, fire fields, auras, barriers |
| SummonManager | partial, `op_summon :453` and `manager._summon :1017` | extract `summons.py`: a summon gets its own `EntityState` and a faction | FactionManager | M | familiars, clones, shikigami |
| FactionManager | partial, `core/adaptation.py:248` (`relation`, `is_hostile`, `override`). Companions register in faction `hero` (`main_game_scene.py:471`) but `ally` resolves to the caster | keep the class, feed SelectorResolver | none | S | allies, charm, betrayal |
| AggroManager | partial, `core/adaptation.py:306` (`add_threat`, `select`, `retarget`), ops `op_set_aggro :792`, `op_retarget :810`, `op_clear_aggro :817` | keep | FactionManager | S | taunt, provoke |
| AdaptationManager | yes, `core/adaptation.py:420` (`on_damage`), ops `op_adapt :670`, `op_unadapt :704`, `op_reset_adaptation :715` | keep. Live-content use is unverified (APP_SPECIFICS 3.1) | none | S | adaptive enemies |
| PhenomenonRegistry | yes, `core/adaptation.py:62`, `op_register_phenomenon :750` | keep. Merge into the Registry with namespace `phenomena` | Registry | S | signatures |
| SignatureHasher | yes, `core/adaptation.py:31`, `ops._formula_signature :354` | keep | none | S | signatures |
| EscalationManager | yes, `core/adaptation.py:374`, ops `op_escalate :849`, `op_deescalate :858`, `op_trigger_true_form :868` | keep | none | S | tiers, true forms |
| WheelRenderer | partial, only the ops `op_display_wheel :880`, `op_halt_wheel :888`. No renderer | a view over the `AdaptationState` dict; needs a UI hook. Stays outside the core (layer 8) | UI | S | visual counters |
| LearnedTechniqueManager | partial, `op_learn :649`, `op_use_learned_technique :761`. State is inside the adapt dict | ALIAS = ops. Extract the state class only if the tables grow | none | S | steal/copy techniques |
| MemoryManager | no, PersistentMemory (4.10) has no canon | `memory` dict on the entity, persisted with the save. Needs a schema | Registry, save format | M | remembering, grudges |
| TrueFormManager | partial, `EscalationManager.trigger_true_form :402`, `op_trigger_true_form :868` | ALIAS = EscalationManager | none | S | transformations |

## B. Registries and API (SPEC part 7)

| item | canon status | proposed canon form | depends on | size | unlocks |
|---|---|---|---|---|---|
| Namespaces, 40 listed | partial. `lua_content/registry.lua` lists 19 (`namespaces :16-35`, layers/flags/triggers/selectors/scales as data). `core/registry.py` has 12 domains (`CORE_DOMAINS :123`). The two drift (layer priorities social/entity swapped, `damage_types` differ, `registry.py:189-208`) | Lua is the source, Python is generated. `Registry.declare_namespace` reads the `namespaces` table from `registry.lua` | none | M | any new kind |
| Missing namespaces (no data anywhere) | no: `narratives, contracts, oaths, recipes, achievements, meta_ops, rules, ontologies, aggro_modes, targeting_modes, wheel_segments, adaptation_types` | add on demand. `aggro_modes` and `targeting_modes` are needed first: `AggroManager.register_mode :317` and `op_set_targeting :801` already take them | none | S each | per-character features |
| `register/get/has/all` | yes in `core/registry.py` (`Registry.register :57`, `get :87`, `has :97`, `names :100`, `items :103`). String-keyed. Wired nowhere | keep the API names. `all(namespace, filter)` = `items()` plus a filter | none | S | all |
| `find_by_tag`, `update`, `deprecate`, `on_change`, `export` | no | `find_by_tag`: a tag index built at `freeze`. `deprecate`: an alias map old to new (also gives the ALIAS mechanism for op names). `update` and `on_change`: dev/hot-reload only, must be off in a run | freeze | M | modding, hot reload |
| `freeze/unfreeze` | partial, `Registry.freeze :77` (`unfreeze` missing) | keep freeze only (no unfreeze in a run: determinism) | none | S | determinism |
| Load path for the actual game | partial, canon loads Lua ad hoc: `load_abilities :13`, `load_statuses :19`, `runtime.rules :77`, `damage.config :359`. `schema.OP_KINDS :30` and `registry_stats :175` are hardcoded/derived in Python | a single loader fills the registry from the Lua namespaces; the four functions above become `registry.get(ns, id)` | Registry wiring | M | SSOT |
| Numeric ids | no. Strings everywhere; only Timeline events have int ids | `registry.register` returns an int id (an index in registration order, stable because of the load order in `registry.lua:124`). Tables `id_of(ns, name)`, `name_of(ns, id)` | Registry | M | Rust hot path, fast dispatch |

## C. Principles (SPEC part 10), audit against canon

| item | canon status | proposed canon form | depends on | size | unlocks |
|---|---|---|---|---|---|
| 1 Effect = trigger + ops | yes, `schema.py:111,309` | none | none | S | |
| 2 One Op = one shape | yes, `schema.Op :252`. 42 kinds (`OP_KINDS :30`) | none | none | S | |
| 3 Character adds a kind, not Op fields | partial. Fields like `thr`, `custom`, `extend` sit on Op (`ops.py:301-331`) | count precedents (rule 4) before adding new fields; move `adapt/mahoraga` payload into a registry entry | none | S | |
| 4 A new field needs 3+ precedents | not checkable, no tool | one test that lists fields by the number of kinds using them | none | S | |
| 5 Everything is registered | VIOLATED. `OP_KINDS` hardcoded `schema.py:30`, buff-id string prefixes (`untargetable:`, `block:`, `nullified`) `schema.py:91`, `ops.py:552`, `manager.py:777`. `STAT_MAP manager.py:55`. Events are a hardcoded list `schema.py:113-117`. 4 DamageType enums in `src/core` | derive kinds, events and stats from the registry; make prefixes flags | Registry wiring | M | |
| 6 Everything serialisable | partial. Effects are data plus predicate strings (yes). `Tracked` dict, `EntityState` and the cooldown book are not persisted; `Timeline.to_json :359` is unwired | `to_state/from_state` on `EntityState` (also needed for Timeline snapshots) | Timeline | M | |
| 7 Timeline = foundation | VIOLATED. Not present in canon at all (`core/timeline.py` unwired). `manager.emit` drops events deeper than 6 silently (`:75`, `:681`) with no record | see D and build order | none | L | |
| 8 Layers do not mix | VIOLATED. One host mixes Effect + State + Rules: `manager` pushes stats into entity fields (`push_stats :305`), the game base is `field - applied`, `rules()` falls back to defaults on any Lua error (`runtime.py:76-88`). `core/adaptation.py` sits in `core` (domain code, APP_SPECIFICS 3.3) | the effect layer emits deltas, the state layer applies them. Move `adaptation.py` out of `core` | ModifierStack | L | |
| 9 Numeric ids on the hot path | VIOLATED. Strings for stats, kinds, events, buffs, marks. `_ctx :760` builds a dict per event. Stat cache bypassed for any entity with a passive effect (`manager.py:340`) | see B "Numeric ids" | Registry | L | |
| 10 Extend by enums, not structure | partial. `OP_HANDLERS` is a table (yes). `apply_op` skips an unknown kind silently (`ops.py:928-930`) | unknown kind = fail on load (a check), and stay silent at runtime | Registry | S | |

## D. Foundation: what is needed first

- **Ids first.** Both Timeline and the bus need stable ids. A Registry with numeric ids (B) precedes everything. It is cheap: it changes no behaviour.
- **Timeline second** (principle 7). Wire `core/timeline.py`. A Python `Event` becomes a struct (tick, kind id, source id, target id, amount). `emit` and `_damage` commit into it. Undo and snapshots come after.
- **Relation to the Rust core.** Planned: event bus, timeline, modifier stack, batch calls once per frame. The model exists: `damage.py` (a pure kernel with a Python twin, shared ABI, `available_backends :235`). Same here:
  - Timeline = an append-only column buffer (`Vec<Event>` of i32/f32 columns). Python `Timeline` is the parity oracle.
  - ModifierStack = a batch fold over (entity, stat, op, value) columns once per frame, replacing the per-entity `push_stats`.
  - EventBus in Rust holds queues and dispatches; handlers (ops) stay in Python until an op interpreter exists (`EFFECT_SCHEMA.md:167` is only a plan).
  - The dice stay drawn in Python (APP_SPECIFICS 3.1: Python draws the dice) for parity and seeds.
- **Recommended build order**
  1. Registry wiring: one loader from `registry.lua`, generate `core/registry.py` tables from it, numeric ids, a drift check.
  2. Events as data: register all 11 emitted events plus the 3 dead ones; a bus with numeric ids and the same order and depth cap. Golden parity (`qa.py golden`).
  3. Timeline commit from `emit/_damage` (observer only, no state change). Replay test: the same seed gives the same log.
  4. ModifierStack (Python) replacing the field-delta push. Golden parity, then the stat cache works for heroes too.
  5. Snapshot provider, rewind and fork on top.
  6. Selector extraction, then Zone, Summon, Memory managers.
  7. Rust: Timeline columns, ModifierStack fold, EventBus. Python twins remain as oracles (`AI_EVOLVE_*=python`).

## Risks / conflicts with canon

- Naming: `EffectManager` exists 3 times (`manager.py:414`, `condition_action_system.py:324`, `cas_effect_system.py:325`); 4 DamageType enums. Spec names collide, so use the aliases in A.
- Semantics: `emit` is owner-only with depth 6. The spec bus is global (any entity's events). Change it behind a flag, otherwise every golden run moves.
- Determinism: `emit` order = registration order (dice order, `manager.py:734-772`). Numeric ids and a new bus must keep it byte for byte; `timeline.py` ids and `blinker` ids (ms resolution, collide, `event_system.py:175`) must not be mixed in.
- Layer mixing: `core/adaptation.py` (domain code in `core`), and `core/registry.py` has no Lua loader while `registry.lua` describes a bridge that does not exist (`ARCHITECTURE.md`).
- Two hosts (manager and `EffectRuntime`) run the same ops with 8 known divergent items; each new module has to be implemented on both, or specs stop proving game numbers.
- Time: `timeline.py` is tick-based, the manager uses float seconds and `dt`. A tick clock conversion is needed (virtual clock in `probe_runtime`); `cas_engine_v2` already broke it with `time.time()`.
- Registry `update/on_change/unfreeze` conflict with principle 6 and determinism in a live run; keep them for tools only.
- Numeric ids must be stable across saves and Lua edits: index by registration order breaks when a content row is added. Persist names in saves, ids only in memory.


**Status 2026-09-27 (slice F1)**: with exact aliases 41.7% (25/60, was 28.3%). Newly expressible: #8 Rasengan, #9 Kurama mode, #17 Gear 5, #23 Bungee Gum, #24 Guanyin Zero, #27 Instant Transmission, #28 Super Saiyan, #36 Repulsor (movement aliases carry `params`; `stance`/`transform`/`timed_power_up` are handlers; content: `lua_content/corpus_abilities.lua`). Still blocked from the slice list: #12 (dodge), #16 (zone), #43 (time_scale), #59 (on_lethal).
**Status 2026-09-27 (slice F2)**: with exact aliases 48.3% (29/60, was 41.7%). Newly expressible: #49 One Ring dominion, #51 The Voice, #58 Axii, #60 Bloodbending (kinds hypnosis/command/possess/dominance/temptation/tame in `src/effects/control.py`; aliases blood_manipulation, enter_dream). Control rows are in `lua_content/corpus_abilities.lua` (`family = "control"`). Still blocked: #11 (time_as_space), #13 (apply_status_to_world), #15 (perceive/reveal), #20 (control_link).

**Status 2026-09-26** (`qa.py coverage`, computed): hand tags 46.7% (28/60, matches the table); canon op names literally 13.3% (8/60); with exact aliases 28.3% (17/60); spec 80.0%. `dash/teleport/pull/push` are expressible as `move` + `mode` but are not pure renames, so they are not counted.
