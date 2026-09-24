// rust_core/src/tactics/mod.rs
//! L11: collective tactics memory of enemies (src/gameplay/tactics.py).
//!
//! A discounted UCB1 bandit per context (enemy archetype): which tactic
//! (rush, flank, kite, ambush, pack, hit_and_run) works best against this
//! hero. Every enemy reports the outcome of its engagement; old evidence
//! decays so the memory follows a hero who changes gear or style.
//! Deterministic (ties -> lowest arm), so the Python twin is bit-identical.

#[derive(Clone, Debug)]
pub struct Bandit {
    pub arms: usize,
    pub counts: Vec<f64>, // contexts * arms
    pub sums: Vec<f64>,
    pub c: f64,
    pub decay: f64,
}

impl Bandit {
    pub fn new(contexts: usize, arms: usize, c: f64, decay: f64) -> Self {
        Self { arms, counts: vec![0.0; contexts * arms], sums: vec![0.0; contexts * arms], c, decay }
    }

    fn row(&self, ctx: usize) -> std::ops::Range<usize> {
        ctx * self.arms..(ctx + 1) * self.arms
    }

    pub fn contexts(&self) -> usize {
        if self.arms == 0 { 0 } else { self.counts.len() / self.arms }
    }

    /// Untried arm first (lowest index), otherwise argmax mean + c * sqrt(ln N / n).
    pub fn select(&self, ctx: usize, allowed: &[bool]) -> usize {
        let r = self.row(ctx);
        let counts = &self.counts[r.clone()];
        let sums = &self.sums[r];
        let ok = |a: usize| allowed.get(a).copied().unwrap_or(true);
        if let Some(a) = (0..self.arms).find(|&a| ok(a) && counts[a] < 1e-9) {
            return a;
        }
        let total: f64 = (0..self.arms).filter(|&a| ok(a)).map(|a| counts[a]).sum();
        let ln = total.max(1.0).ln();
        let mut best = usize::MAX;
        let mut best_v = f64::NEG_INFINITY;
        for a in 0..self.arms {
            if !ok(a) {
                continue;
            }
            let v = sums[a] / counts[a] + self.c * (ln / counts[a]).sqrt();
            if v > best_v {
                best_v = v;
                best = a;
            }
        }
        if best == usize::MAX { 0 } else { best }
    }

    /// Decay the context's evidence, then add one observation.
    pub fn update(&mut self, ctx: usize, arm: usize, reward: f64) {
        let r = self.row(ctx);
        for i in r.clone() {
            self.counts[i] *= self.decay;
            self.sums[i] *= self.decay;
        }
        self.counts[r.start + arm] += 1.0;
        self.sums[r.start + arm] += reward;
    }

    pub fn means(&self, ctx: usize) -> Vec<f64> {
        let r = self.row(ctx);
        self.counts[r.clone()].iter().zip(&self.sums[r]).map(|(n, s)| if *n > 1e-9 { s / n } else { 0.0 }).collect()
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn tries_every_arm_then_exploits_the_best() {
        let mut b = Bandit::new(2, 3, 0.5, 1.0);
        let all = [true, true, true];
        let rewards = [0.1, 0.9, 0.3];
        let mut picks = vec![];
        for _ in 0..40 {
            let a = b.select(0, &all);
            picks.push(a);
            b.update(0, a, rewards[a]);
        }
        assert_eq!(&picks[..3], &[0, 1, 2]);
        assert!(picks[20..].iter().filter(|&&a| a == 1).count() >= 15);
        assert_eq!(b.select(1, &all), 0); // other context untouched
    }

    #[test]
    fn allowed_mask_and_decay() {
        let mut b = Bandit::new(1, 3, 0.5, 0.5);
        assert_eq!(b.select(0, &[false, true, true]), 1);
        b.update(0, 1, 1.0);
        b.update(0, 2, 0.0);
        assert!((b.counts[1] - 0.5).abs() < 1e-12); // decayed once by the second update
        assert_eq!(b.means(0)[1], 1.0);
    }
}
