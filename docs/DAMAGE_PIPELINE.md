# Damage pipeline: one hit, one place

Every point of HP the game takes off in combat goes through `EffectManager._damage` -> **one pure kernel**:

| what | where |
|---|---|
| formulas (kernel) | `rust_core/src/combat/mod.rs` (`resolve_hit`, batch `resolve_hits`); `cargo test combat` |
| Python twin = the semantics, and the fallback without rust_core | `src/effects/damage.py` (`resolve_hit_py`); `AI_EVOLVE_DAMAGE=python` forces it |
| numbers a designer tunes: damage types, constants | `lua_content/damage.lua` |
| stats + bounds (SSOT of stat definitions) | `lua_content/effect_rules.lua` (`defaults`, `bounds`, per-type `families`) |
| the live caller: params in, dice out, `HitInfo` filled | `EffectManager._hit_params` / `_damage` (`src/effects/manager.py`) |
| tests / bench | `tests/test_damage_pipeline.py` (Rust == twin bit for bit) / `tools/bench_damage.py` |

The kernel is pure: `resolve_hit(params, rolls, consts) -> Outcome`. The RNG stays in Python: `roll_hit` draws the dice one by one, **exactly the ones a stage asks for**
(`Outcome.need`), so seeds and traces are reproducible. Neutral stats (nothing but armor and crit) = today's numbers and today's two draws.

## Stages (the stage table; order = evaluation order)

| # | stage | rule | roll (drawn only when...) |
|---|---|---|---|
| 1 | accuracy vs evasion | hit % = clamp(`hit.base` + accuracy - evasion, `hit.min`, `hit.max`); roll >= hit % is a miss (`hit=0`) | accuracy: hit % < 100 |
| 2 | dodge | dodged iff roll < `dodge` (0..1, the entity's `dodge_chance`) | dodge: the hit is avoidable (always, as before) |
| 3 | block (chance) | blocked iff `block_chance` > 0 and roll < `block_chance` % | block: `block_chance` > 0 |
| 4 | crit | crit iff roll < `crit_chance` (0..1) | crit: not `no_crit` / periodic (always, as before) |
| 5 | base x type x variance x crit | `amount` x (1 + `damage_<type>`/100) x (1 + `variance` x (2 roll - 1)) x `crit_mult` = `damage_before` | variance: `constants.variance` > 0 and avoidable |
| 6 | armor + penetration | eff = armor > 0 ? max(0, armor (1 - `penetration_pct`/100) - `penetration_flat`) : armor (negative armor is not penetrated, it adds damage as before); `subtractive`: max(`min_damage`, dmg - eff), `percent`: dmg k / (k + eff) -> `armor_reduced`, `armor_ignored` | - |
| 7 | resistance | raw `resist_<type>` >= `resist.immune_at`: immune, final 0 (no floor); else eff = clamp(raw > 0 ? max(0, raw - `resist_pen`) : raw, `resist.min`, `resist.max`), dmg x (1 - eff/100) -> `resisted` | - |
| 8 | block (reduction) | if blocked: dmg x (1 - clamp(`block.reduction` + `block_reduction`, 0, 100)/100) -> `blocked_amount` | - |
| 9 | final modifiers | dmg x max(0, 1 + `damage_taken`/100) x (`broken` ? `broken` const : 1); floor `min_damage` (not for true damage, not for immunity) -> `final` | - |

Then, outside the kernel (manager): invulnerability (`iframe` buff -> `HitInfo.invulnerable`), HP cap, lifesteal, events (`attack_hit`, `crit`, `dodge`, `take_damage`, `kill`, `die`).

**Flags** (hit flag names -> kernel bits, `damage.flag_bits`): `true_damage` = no armor stage and no floor (resistance still applies: poison is resisted); `true_damage` / `unavoidable` / `periodic` = cannot miss, dodge or be blocked (no accuracy, dodge, block or variance roll); `no_crit` / `periodic` = no crit roll; target stat `broken` > 0 = broken.

**Roll order** (fixed, one `rng.random()` each): accuracy, dodge, block, crit, variance. A miss or a dodge stops the hit: the later rolls are never drawn (a dodged hit draws no crit roll, as before). Neutral hit: dodge, crit.

**Outcome** = `{need, hit, dodged, blocked, crit, damage_before, armor_ignored, armor_reduced, resisted, blocked_amount, final}` -> `HitInfo` (`missed`, `blocked`, `hit_type`, `damage_before`, `armor_reduced`, `resisted`, `blocked_amount`, `armor_ignored`; `landed` = not dodged, not missed) -> combat events (`combat.jsonl`: `type`, `armor`, `resisted`, `missed`, `blocked` + `guarded`, `pierced`; `dodged` = did not land) -> `agent_play` metrics `misses blocks resisted armored pierced` (RESULT line) and the `dev_probe` combat totals.

## Stats (defaults 0 = neutral; bounds in `effect_rules.lua`)

`defense` (armor), `crit_chance`, `crit_dmg`, `dodge` are the old stats. New: `accuracy`, `evasion`, `penetration_pct`, `penetration_flat`, `resist_pen` (attacker); `block_chance`, `block_reduction`, `damage_taken`, `broken` (target);
per damage type (list in `damage.lua`): `resist_<type>` (target, %), `damage_<type>` (attacker, % bonus). Items, perks and effects change them like any stat (`stats = { resist_fire = 20 }`, `mod ... stat = "resist_fire"`);
an enemy kind gets them from `stats` in `lua_content/bestiary.lua` (`golem_shard`); a unit's baseline per type = `resist` / `mod` of that type in `damage.lua`.

A hit's damage type = the first tag of its ability/effect that names a type in `damage.lua` (`tags = { "spell", "fire" }`), else `physical`; a DoT keeps its type.

## Tuning and checking

`lua_content/damage.lua` (constants, types) -> `AI_EVOLVE_DAMAGE_LUA=path` swaps the file. `python tools/agent_play.py "spawn enemy golem_shard x3; until kills>=3 or dead max 60"` (scenario `golem_guard`),
`python tools/bench_damage.py`, `python tools/qa.py check --name damage,play:golem_guard`.

### Measured single-hit cost
2026-09-26, Windows, i5-11600KF, `python tools/bench_damage.py --hits 200000 --repeat 5` (neutral mix): Python twin 2.81 us/hit, Rust single-call 1.47 us/hit (x1.9 faster), Rust batch 0.21 us/hit.
Rich mix: twin 2.64 us, Rust single 1.49 us. So the Rust path is NOT slower per single hit (kernel call only; extra FFI calls around it in `damage.py:251-289` are not in this number).
