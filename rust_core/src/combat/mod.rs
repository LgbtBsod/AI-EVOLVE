// rust_core/src/combat/mod.rs
//! L12: the damage pipeline kernel (docs/DAMAGE_PIPELINE.md, Python twin src/effects/damage.py).
//!
//! `resolve_hit(params, consts, rolls)` turns "a hit of N points" into an `Outcome`: accuracy vs evasion,
//! dodge, block, crit, damage-type modifier, variance, armor with penetration, resistance, final modifiers.
//! It is PURE: the dice are drawn by the caller (RNG and seeds stay in Python) and passed in. A roll is NaN
//! while it is not drawn; the first stage that needs a NaN roll stops the hit with `need = index + 1`, the
//! caller draws that one roll and asks again, so a hit consumes exactly the rolls its stages read.
//!
//! The arithmetic is written in the SAME order as the Python twin (only + - * / and explicit comparisons,
//! no fused ops, no `f64::max`/`clamp`), so both give the same bits: tests/test_damage_pipeline.py checks it
//! on tens of thousands of random hits. Field order = `Params` / `Consts` / `Outcome::to_row` = the ABI.

pub const N_PARAMS: usize = 16;
pub const N_CONSTS: usize = 11;
pub const N_ROLLS: usize = 5;
pub const N_OUT: usize = 11;

// flag bits of `Params::flags`
pub const F_TRUE: i64 = 1; // true damage: no armor, no min-damage floor (resistance still applies)
pub const F_NO_CRIT: i64 = 2;
pub const F_CERTAIN: i64 = 4; // cannot miss, dodge or be blocked, no variance (periodic, unavoidable, true damage)
pub const F_BROKEN: i64 = 8; // target is broken: x `broken_mult`

// index of a roll
pub const R_ACCURACY: usize = 0;
pub const R_DODGE: usize = 1;
pub const R_BLOCK: usize = 2;
pub const R_CRIT: usize = 3;
pub const R_VARIANCE: usize = 4;

/// One hit. Units: docs/DAMAGE_PIPELINE.md.
#[derive(Clone, Copy, Debug, PartialEq)]
pub struct Params {
    pub amount: f64,
    pub flags: f64,
    pub accuracy: f64,
    pub evasion: f64,
    pub dodge: f64,
    pub block_chance: f64,
    pub block_bonus: f64,
    pub crit_chance: f64,
    pub crit_mult: f64,
    pub type_mod: f64,
    pub resist: f64,
    pub resist_pen: f64,
    pub armor: f64,
    pub pen_pct: f64,
    pub pen_flat: f64,
    pub taken: f64,
}

impl Params {
    pub fn from_slice(s: &[f64]) -> Result<Self, String> {
        if s.len() != N_PARAMS {
            return Err(format!("params: expected {N_PARAMS} numbers, got {}", s.len()));
        }
        Ok(Self {
            amount: s[0], flags: s[1], accuracy: s[2], evasion: s[3], dodge: s[4], block_chance: s[5],
            block_bonus: s[6], crit_chance: s[7], crit_mult: s[8], type_mod: s[9], resist: s[10],
            resist_pen: s[11], armor: s[12], pen_pct: s[13], pen_flat: s[14], taken: s[15],
        })
    }
}

/// The numbers of lua_content/damage.lua -> constants.
#[derive(Clone, Copy, Debug, PartialEq)]
pub struct Consts {
    pub hit_base: f64,
    pub hit_min: f64,
    pub hit_max: f64,
    pub block_reduction: f64,
    pub armor_k: f64, // 0 = subtractive armor, > 0 = percent curve k / (k + armor)
    pub resist_min: f64,
    pub resist_max: f64,
    pub immune_at: f64,
    pub broken_mult: f64,
    pub min_damage: f64,
    pub variance: f64,
}

impl Consts {
    pub fn from_slice(s: &[f64]) -> Result<Self, String> {
        if s.len() != N_CONSTS {
            return Err(format!("consts: expected {N_CONSTS} numbers, got {}", s.len()));
        }
        Ok(Self {
            hit_base: s[0], hit_min: s[1], hit_max: s[2], block_reduction: s[3], armor_k: s[4], resist_min: s[5],
            resist_max: s[6], immune_at: s[7], broken_mult: s[8], min_damage: s[9], variance: s[10],
        })
    }
}

/// Everything a hit did. `need != 0`: the kernel wants roll `need - 1` and computed nothing else.
#[derive(Clone, Copy, Debug, PartialEq, Default)]
pub struct Outcome {
    pub need: i64,
    pub hit: bool,
    pub dodged: bool,
    pub blocked: bool,
    pub crit: bool,
    pub damage_before: f64,
    pub armor_ignored: f64,
    pub armor_reduced: f64,
    pub resisted: f64,
    pub blocked_amount: f64,
    pub finalv: f64,
}

impl Outcome {
    /// The row as N_OUT numbers (flags 0/1): the layout of the batch columns.
    pub fn to_row(&self) -> [f64; N_OUT] {
        let b = |x: bool| if x { 1.0 } else { 0.0 };
        [
            self.need as f64, b(self.hit), b(self.dodged), b(self.blocked), b(self.crit), self.damage_before,
            self.armor_ignored, self.armor_reduced, self.resisted, self.blocked_amount, self.finalv,
        ]
    }
}

const MISS: Outcome = Outcome {
    need: 0, hit: false, dodged: false, blocked: false, crit: false, damage_before: 0.0, armor_ignored: 0.0,
    armor_reduced: 0.0, resisted: 0.0, blocked_amount: 0.0, finalv: 0.0,
};
const DODGED: Outcome = Outcome { hit: true, dodged: true, ..MISS };

/// Err(index) = that roll is not drawn yet.
type Need<T> = Result<T, usize>;

fn roll(rolls: &[f64; N_ROLLS], i: usize) -> Need<f64> {
    let v = rolls[i];
    if v != v {
        return Err(i);
    }
    Ok(v)
}

fn clamp(x: f64, lo: f64, hi: f64) -> f64 {
    if x < lo { lo } else if x > hi { hi } else { x }
}

fn fmax(a: f64, b: f64) -> f64 {
    if a > b { a } else { b }
}

fn stage_hit(p: &Params, c: &Consts, rolls: &[f64; N_ROLLS]) -> Need<bool> {
    let chance = clamp(c.hit_base + p.accuracy - p.evasion, c.hit_min, c.hit_max);
    if chance >= 100.0 {
        return Ok(true);
    }
    Ok(roll(rolls, R_ACCURACY)? < chance / 100.0)
}

fn stage_block(p: &Params, rolls: &[f64; N_ROLLS]) -> Need<bool> {
    if !(p.block_chance > 0.0) {
        return Ok(false);
    }
    Ok(roll(rolls, R_BLOCK)? < p.block_chance / 100.0)
}

fn stage_amount(p: &Params, c: &Consts, rolls: &[f64; N_ROLLS], crit: bool, avoidable: bool) -> Need<f64> {
    let m = 1.0 + p.type_mod / 100.0;
    let mut dmg = p.amount * (if m > 0.0 { m } else { 0.0 });
    if avoidable && c.variance > 0.0 {
        dmg *= 1.0 + c.variance * (2.0 * roll(rolls, R_VARIANCE)? - 1.0);
    }
    Ok(if crit { dmg * p.crit_mult } else { dmg })
}

/// armor x (1 - pen%) - flat, never below 0; armor <= 0 is not penetrated.
fn armor_eff(p: &Params) -> f64 {
    if p.armor <= 0.0 {
        return p.armor;
    }
    fmax(0.0, p.armor * (1.0 - clamp(p.pen_pct, 0.0, 100.0) / 100.0) - fmax(p.pen_flat, 0.0))
}

fn stage_armor(p: &Params, c: &Consts, dmg: f64) -> (f64, f64) {
    let eff = armor_eff(p);
    let after = if c.armor_k > 0.0 {
        dmg * (c.armor_k / (c.armor_k + fmax(eff, -0.5 * c.armor_k)))
    } else {
        dmg - eff
    };
    (fmax(c.min_damage, after), p.armor - eff)
}

/// Damage after the resistance; None = immune (raw resist >= immune_at).
fn stage_resist(p: &Params, c: &Consts, dmg: f64) -> Option<f64> {
    if p.resist >= c.immune_at {
        return None;
    }
    let eff = if p.resist <= 0.0 { p.resist } else { fmax(0.0, p.resist - fmax(p.resist_pen, 0.0)) };
    Some(dmg * (1.0 - clamp(eff, c.resist_min, c.resist_max) / 100.0))
}

fn stage_final(p: &Params, c: &Consts, dmg: f64, flags: i64) -> f64 {
    let mut mult = fmax(1.0 + p.taken / 100.0, 0.0);
    if flags & F_BROKEN != 0 {
        mult *= c.broken_mult;
    }
    let out = dmg * mult;
    if flags & F_TRUE != 0 { out } else { fmax(c.min_damage, out) }
}

/// armor -> resist -> block -> final modifiers. True damage skips the armor stage (and every min-damage floor).
fn mitigate(p: &Params, c: &Consts, flags: i64, before: f64, blocked: bool) -> Outcome {
    let (after_armor, ignored) = if flags & F_TRUE != 0 { (before, 0.0) } else { stage_armor(p, c, before) };
    let base = Outcome { hit: true, blocked, damage_before: before, armor_ignored: ignored,
                         armor_reduced: before - after_armor, ..MISS };
    let Some(after_resist) = stage_resist(p, c, after_armor) else {
        return Outcome { resisted: after_armor, ..base };
    };
    let mut after_block = after_resist;
    if blocked {
        after_block = after_resist * (1.0 - clamp(c.block_reduction + p.block_bonus, 0.0, 100.0) / 100.0);
    }
    Outcome {
        resisted: after_armor - after_resist,
        blocked_amount: after_resist - after_block,
        finalv: stage_final(p, c, after_block, flags),
        ..base
    }
}

fn resolve(p: &Params, c: &Consts, rolls: &[f64; N_ROLLS]) -> Need<Outcome> {
    let flags = p.flags as i64;
    let avoidable = flags & F_CERTAIN == 0;
    if avoidable {
        if !stage_hit(p, c, rolls)? {
            return Ok(MISS);
        }
        if roll(rolls, R_DODGE)? < p.dodge {
            return Ok(DODGED);
        }
    }
    let blocked = avoidable && flags & F_TRUE == 0 && stage_block(p, rolls)?;
    let crit = flags & F_NO_CRIT == 0 && roll(rolls, R_CRIT)? < p.crit_chance;
    let before = stage_amount(p, c, rolls, crit, avoidable)?;
    Ok(Outcome { crit, ..mitigate(p, c, flags, before, blocked) })
}

/// One hit. Rolls are N_ROLLS numbers, NaN = not drawn yet (then `need` says which one to draw).
pub fn resolve_hit(p: &Params, c: &Consts, rolls: &[f64; N_ROLLS]) -> Outcome {
    match resolve(p, c, rolls) {
        Ok(o) => o,
        Err(i) => Outcome { need: i as i64 + 1, ..MISS },
    }
}

/// Many hits from columns: `params[k][i]` = field k of hit i (N_PARAMS columns), `rolls[k][i]` (N_ROLLS
/// columns), result = N_OUT columns in `Outcome::to_row` order.
pub fn resolve_hits(params: &[&[f64]], rolls: &[&[f64]], consts: &Consts) -> Result<Vec<Vec<f64>>, String> {
    if params.len() != N_PARAMS || rolls.len() != N_ROLLS {
        return Err(format!("expected {N_PARAMS} param columns and {N_ROLLS} roll columns, got {} and {}",
                           params.len(), rolls.len()));
    }
    let n = params[0].len();
    if params.iter().chain(rolls.iter()).any(|col| col.len() != n) {
        return Err("columns must have equal length".to_string());
    }
    let mut out: Vec<Vec<f64>> = (0..N_OUT).map(|_| Vec::with_capacity(n)).collect();
    let mut row = [0.0; N_PARAMS];
    let mut r = [0.0; N_ROLLS];
    for i in 0..n {
        for (k, col) in params.iter().enumerate() {
            row[k] = col[i];
        }
        for (k, col) in rolls.iter().enumerate() {
            r[k] = col[i];
        }
        let p = Params::from_slice(&row)?;
        for (col, v) in out.iter_mut().zip(resolve_hit(&p, consts, &r).to_row()) {
            col.push(v);
        }
    }
    Ok(out)
}

#[cfg(test)]
mod tests {
    use super::*;

    const NAN: f64 = f64::NAN;
    const C: Consts = Consts {
        hit_base: 100.0, hit_min: 5.0, hit_max: 100.0, block_reduction: 50.0, armor_k: 0.0, resist_min: -100.0,
        resist_max: 90.0, immune_at: 100.0, broken_mult: 1.15, min_damage: 1.0, variance: 0.0,
    };
    const P: Params = Params {
        amount: 10.0, flags: 0.0, accuracy: 0.0, evasion: 0.0, dodge: 0.0, block_chance: 0.0, block_bonus: 0.0,
        crit_chance: 0.0, crit_mult: 1.5, type_mod: 0.0, resist: 0.0, resist_pen: 0.0, armor: 0.0, pen_pct: 0.0,
        pen_flat: 0.0, taken: 0.0,
    };
    const ROLLS: [f64; 5] = [NAN, 1.0, NAN, 1.0, NAN]; // no dodge, no crit, nothing else drawn

    fn hit(p: Params, rolls: [f64; 5]) -> Outcome {
        resolve_hit(&p, &C, &rolls)
    }

    #[test]
    fn neutral_hit_is_max_one_amount_minus_armor() {
        let o = hit(Params { amount: 20.0, armor: 3.0, ..P }, ROLLS);
        assert_eq!((o.need, o.hit, o.dodged, o.blocked, o.crit), (0, true, false, false, false));
        assert_eq!((o.damage_before, o.armor_reduced, o.finalv), (20.0, 3.0, 17.0));
        assert_eq!(hit(Params { amount: 5.0, armor: 1000.0, ..P }, ROLLS).finalv, 1.0);
        assert_eq!(hit(Params { amount: 10.0, armor: -3.0, ..P }, ROLLS).finalv, 13.0);
    }

    #[test]
    fn true_damage_has_no_armor_and_no_floor_but_is_resisted() {
        let p = Params { amount: 0.4, armor: 1000.0, flags: (F_TRUE | F_CERTAIN | F_NO_CRIT) as f64, ..P };
        let o = hit(p, [NAN; 5]);
        assert_eq!((o.finalv, o.armor_reduced), (0.4, 0.0));
        let r = hit(Params { amount: 100.0, resist: 25.0, ..p }, [NAN; 5]);
        assert_eq!((r.finalv, r.resisted), (75.0, 25.0));
    }

    #[test]
    fn crit_multiplies_before_armor() {
        let p = Params { amount: 10.0, crit_chance: 0.5, crit_mult: 2.0, armor: 5.0, ..P };
        let o = hit(p, [NAN, 1.0, NAN, 0.0, NAN]);
        assert_eq!((o.crit, o.damage_before, o.finalv), (true, 20.0, 15.0));
        assert!(!hit(p, [NAN, 1.0, NAN, 0.5, NAN]).crit);
    }

    #[test]
    fn penetration_floors_at_zero_and_leaves_negative_armor() {
        let p = Params { amount: 20.0, armor: 10.0, ..P };
        assert_eq!(hit(Params { pen_pct: 50.0, ..p }, ROLLS).finalv, 15.0);
        assert_eq!(hit(Params { pen_flat: 4.0, ..p }, ROLLS).finalv, 14.0);
        let o = hit(Params { pen_pct: 50.0, pen_flat: 20.0, ..p }, ROLLS);
        assert_eq!((o.finalv, o.armor_ignored), (20.0, 10.0));
        assert_eq!(hit(Params { armor: -4.0, pen_pct: 100.0, pen_flat: 9.0, ..p }, ROLLS).finalv, 24.0);
    }

    #[test]
    fn percent_armor_curve() {
        let c = Consts { armor_k: 100.0, ..C };
        let o = resolve_hit(&Params { amount: 100.0, armor: 100.0, ..P }, &c, &ROLLS);
        assert_eq!((o.finalv, o.armor_reduced), (50.0, 50.0));
    }

    #[test]
    fn resistance_penetration_clamp_and_immunity() {
        let p = Params { amount: 100.0, ..P };
        assert_eq!(hit(Params { resist: 25.0, ..p }, ROLLS).finalv, 75.0);
        assert_eq!(hit(Params { resist: 50.0, resist_pen: 20.0, ..p }, ROLLS).finalv, 70.0);
        assert_eq!(hit(Params { resist: 50.0, resist_pen: 80.0, ..p }, ROLLS).finalv, 100.0);
        assert!((hit(Params { resist: 99.0, ..p }, ROLLS).finalv - 10.0).abs() < 1e-9); // capped at 90
        assert_eq!(hit(Params { resist: -50.0, ..p }, ROLLS).finalv, 150.0);
        let o = hit(Params { resist: 100.0, resist_pen: 100.0, ..p }, ROLLS);
        assert_eq!((o.finalv, o.resisted), (0.0, 100.0)); // immune: no min damage
    }

    #[test]
    fn block_roll_cuts_damage() {
        let p = Params { amount: 100.0, block_chance: 25.0, ..P };
        let o = hit(p, [NAN, 1.0, 0.1, 1.0, NAN]);
        assert_eq!((o.blocked, o.blocked_amount, o.finalv), (true, 50.0, 50.0));
        assert!((hit(Params { block_bonus: 30.0, ..p }, [NAN, 1.0, 0.1, 1.0, NAN]).finalv - 20.0).abs() < 1e-9);
        assert!(!hit(p, [NAN, 1.0, 0.25, 1.0, NAN]).blocked);
        let t = Params { flags: (F_TRUE | F_CERTAIN) as f64, ..p };
        assert!(!hit(t, [NAN; 5]).blocked);
    }

    #[test]
    fn dodge_and_accuracy_vs_evasion() {
        let o = hit(Params { dodge: 0.2, ..P }, [NAN, 0.1, NAN, 1.0, NAN]);
        assert_eq!((o.hit, o.dodged, o.finalv), (true, true, 0.0));
        assert!(!hit(Params { dodge: 0.2, ..P }, [NAN, 0.2, NAN, 1.0, NAN]).dodged);
        let p = Params { evasion: 30.0, ..P };
        assert!(hit(p, [0.69, 1.0, NAN, 1.0, NAN]).hit);
        assert!(!hit(p, [0.71, 1.0, NAN, 1.0, NAN]).hit);
        assert_eq!(hit(Params { accuracy: 50.0, ..P }, ROLLS).need, 0); // cannot miss: no roll asked
        assert!(hit(Params { evasion: 200.0, ..P }, [0.04, 1.0, NAN, 1.0, NAN]).hit); // floor: hit_min = 5 %
        assert!(!hit(Params { evasion: 200.0, ..P }, [0.06, 1.0, NAN, 1.0, NAN]).hit);
    }

    #[test]
    fn final_modifiers_type_modifier_and_variance() {
        let p = Params { amount: 100.0, ..P };
        assert_eq!(hit(Params { taken: 20.0, ..p }, ROLLS).finalv, 120.0);
        assert!((hit(Params { flags: F_BROKEN as f64, ..p }, ROLLS).finalv - 115.0).abs() < 1e-9);
        assert_eq!(hit(Params { taken: -200.0, ..p }, ROLLS).finalv, 1.0);
        assert_eq!(hit(Params { type_mod: 25.0, ..p }, ROLLS).finalv, 125.0);
        let c = Consts { variance: 0.2, ..C };
        let v = |r: f64| resolve_hit(&p, &c, &[NAN, 1.0, NAN, 1.0, r]).finalv;
        assert!((v(0.5) - 100.0).abs() < 1e-9 && (v(1.0) - 120.0).abs() < 1e-9 && (v(0.0) - 80.0).abs() < 1e-9);
    }

    #[test]
    fn the_kernel_asks_for_rolls_in_stage_order() {
        let p = Params { evasion: 10.0, block_chance: 10.0, ..P };
        let mut rolls = [NAN; 5];
        let mut asked = vec![];
        loop {
            let o = resolve_hit(&p, &C, &rolls);
            if o.need == 0 {
                break;
            }
            asked.push(o.need - 1);
            rolls[(o.need - 1) as usize] = 0.5;
        }
        assert_eq!(asked, vec![0, 1, 2, 3]);
        // a dodged hit never asks for the crit roll
        let d = Params { dodge: 0.9, ..P };
        assert_eq!(resolve_hit(&d, &C, &[NAN, 0.1, NAN, NAN, NAN]).need, 0);
        // a hit that cannot be avoided is asked only for its crit roll
        let u = Params { flags: F_CERTAIN as f64, ..P };
        assert_eq!(resolve_hit(&u, &C, &[NAN; 5]).need, R_CRIT as i64 + 1);
    }

    #[test]
    fn batch_equals_single_calls_and_checks_shape() {
        let n = 40;
        let mut params: Vec<Vec<f64>> = vec![vec![0.0; n]; N_PARAMS];
        let mut rolls: Vec<Vec<f64>> = vec![vec![0.0; n]; N_ROLLS];
        let mut x = 0.123_f64;
        let mut next = || {
            x = (x * 9301.0 + 49297.0) % 233280.0;
            x / 233280.0
        };
        for i in 0..n {
            let row = [next() * 90.0 + 1.0, 0.0, 0.0, next() * 40.0, next() * 0.3, next() * 30.0, 0.0, 0.5, 1.5,
                       0.0, next() * 60.0, 0.0, next() * 20.0, 0.0, 0.0, 0.0];
            for k in 0..N_PARAMS {
                params[k][i] = row[k];
            }
            for k in 0..N_ROLLS {
                rolls[k][i] = next();
            }
        }
        let pc: Vec<&[f64]> = params.iter().map(|c| c.as_slice()).collect();
        let rc: Vec<&[f64]> = rolls.iter().map(|c| c.as_slice()).collect();
        let out = resolve_hits(&pc, &rc, &C).unwrap();
        assert_eq!(out.len(), N_OUT);
        for i in 0..n {
            let mut row = [0.0; N_PARAMS];
            let mut r = [0.0; N_ROLLS];
            (0..N_PARAMS).for_each(|k| row[k] = params[k][i]);
            (0..N_ROLLS).for_each(|k| r[k] = rolls[k][i]);
            let single = resolve_hit(&Params::from_slice(&row).unwrap(), &C, &r).to_row();
            assert!((0..N_OUT).all(|k| out[k][i] == single[k]), "row {i}");
        }
        assert!(resolve_hits(&pc[..3], &rc, &C).is_err());
        assert!(Params::from_slice(&[0.0; 3]).is_err() && Consts::from_slice(&[0.0; 3]).is_err());
    }
}
