// rust_core/src/qa/mod.rs
//! L8c: QA kernels for tools/qa.py.
//!
//! - `reach`: graph reachability over a CSR adjacency (import graph of the
//!   repo: liveness of modules, which tests a change affects);
//! - `describe`: distribution summary + bootstrap CI of the mean for Monte
//!   Carlo sweeps (splitmix64 PRNG so the Python twin is bit-identical);
//! - `fnv1a64_lines`: per-line fingerprints of a state trajectory (golden
//!   scenarios: find the first diverging sample without storing the file).
//!
//! Pure functions over slices; Python twins live in tools/probe_kernels.py.

/// Nodes reachable from `roots` following edges node -> targets[offsets[node]..offsets[node+1]].
/// Returns one flag per node (1 = reachable). Out-of-range ids are ignored.
pub fn reach(offsets: &[u64], targets: &[u64], roots: &[u64]) -> Vec<u8> {
    let n = offsets.len().saturating_sub(1);
    let mut seen = vec![0u8; n];
    let mut stack: Vec<usize> = roots.iter().map(|&r| r as usize).filter(|&r| r < n).collect();
    while let Some(node) = stack.pop() {
        if seen[node] != 0 {
            continue;
        }
        seen[node] = 1;
        let (a, b) = (offsets[node] as usize, offsets[node + 1] as usize);
        for &t in &targets[a.min(targets.len())..b.min(targets.len())] {
            let t = t as usize;
            if t < n && seen[t] == 0 {
                stack.push(t);
            }
        }
    }
    seen
}

/// splitmix64 - tiny, well-mixed, trivially portable PRNG.
pub struct SplitMix64(pub u64);

impl SplitMix64 {
    pub fn next_u64(&mut self) -> u64 {
        self.0 = self.0.wrapping_add(0x9E37_79B9_7F4A_7C15);
        let mut z = self.0;
        z = (z ^ (z >> 30)).wrapping_mul(0xBF58_476D_1CE4_E5B9);
        z = (z ^ (z >> 27)).wrapping_mul(0x94D0_49BB_1331_11EB);
        z ^ (z >> 31)
    }
}

/// Linear-interpolated percentile of a SORTED slice (numpy's default method).
pub fn percentile_sorted(sorted: &[f64], q: f64) -> f64 {
    if sorted.is_empty() {
        return f64::NAN;
    }
    let pos = q * (sorted.len() - 1) as f64;
    let lo = pos.floor() as usize;
    let hi = (lo + 1).min(sorted.len() - 1);
    sorted[lo] + (sorted[hi] - sorted[lo]) * (pos - lo as f64)
}

#[derive(Debug, Clone, PartialEq)]
pub struct Describe {
    pub n: usize,
    pub mean: f64,
    pub sd: f64,
    pub min: f64,
    pub p5: f64,
    pub p50: f64,
    pub p95: f64,
    pub max: f64,
    pub ci_lo: f64,
    pub ci_hi: f64,
}

/// Summary statistics + 95% bootstrap confidence interval of the mean.
/// NaNs are dropped. sd is the sample standard deviation (n-1).
pub fn describe(values: &[f64], resamples: usize, seed: u64) -> Describe {
    let mut v: Vec<f64> = values.iter().copied().filter(|x| !x.is_nan()).collect();
    let n = v.len();
    if n == 0 {
        return Describe { n: 0, mean: f64::NAN, sd: f64::NAN, min: f64::NAN, p5: f64::NAN, p50: f64::NAN,
                          p95: f64::NAN, max: f64::NAN, ci_lo: f64::NAN, ci_hi: f64::NAN };
    }
    let mean = v.iter().sum::<f64>() / n as f64;
    let sd = if n > 1 { (v.iter().map(|x| (x - mean) * (x - mean)).sum::<f64>() / (n - 1) as f64).sqrt() } else { 0.0 };
    let mut rng = SplitMix64(seed);
    let mut means: Vec<f64> = (0..resamples)
        .map(|_| {
            let mut s = 0.0;
            for _ in 0..n {
                s += v[(rng.next_u64() % n as u64) as usize];
            }
            s / n as f64
        })
        .collect();
    v.sort_by(|a, b| a.partial_cmp(b).unwrap());
    means.sort_by(|a, b| a.partial_cmp(b).unwrap());
    let (ci_lo, ci_hi) = if means.is_empty() { (mean, mean) } else {
        (percentile_sorted(&means, 0.025), percentile_sorted(&means, 0.975))
    };
    Describe {
        n, mean, sd, min: v[0], p5: percentile_sorted(&v, 0.05), p50: percentile_sorted(&v, 0.5),
        p95: percentile_sorted(&v, 0.95), max: v[n - 1], ci_lo, ci_hi,
    }
}

/// FNV-1a 64 of every line: data[offsets[i]..offsets[i+1]].
pub fn fnv1a64_lines(data: &[u8], offsets: &[u64]) -> Vec<u64> {
    offsets
        .windows(2)
        .map(|w| {
            let (a, b) = ((w[0] as usize).min(data.len()), (w[1] as usize).min(data.len()));
            data[a..b.max(a)].iter().fold(0xcbf2_9ce4_8422_2325u64, |h, &byte| {
                (h ^ byte as u64).wrapping_mul(0x0000_0100_0000_01B3)
            })
        })
        .collect()
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn reach_follows_edges_only_forward() {
        // 0 -> 1 -> 2, 3 isolated
        let offsets = [0, 1, 2, 2, 2];
        let targets = [1, 2];
        assert_eq!(reach(&offsets, &targets, &[0]), vec![1, 1, 1, 0]);
        assert_eq!(reach(&offsets, &targets, &[1]), vec![0, 1, 1, 0]);
        assert_eq!(reach(&offsets, &targets, &[]), vec![0, 0, 0, 0]);
    }

    #[test]
    fn describe_basic_and_deterministic() {
        let d = describe(&[1.0, 2.0, 3.0, 4.0, f64::NAN], 500, 42);
        assert_eq!(d.n, 4);
        assert_eq!(d.mean, 2.5);
        assert_eq!(d.p50, 2.5);
        assert!(d.ci_lo >= 1.0 && d.ci_hi <= 4.0 && d.ci_lo <= d.mean && d.mean <= d.ci_hi);
        assert_eq!(d, describe(&[1.0, 2.0, 3.0, 4.0], 500, 42));
        assert_eq!(SplitMix64(0).next_u64(), 0xE220_A839_7B1D_CDAF);
    }

    #[test]
    fn fnv_known_values() {
        let data = b"ab";
        assert_eq!(fnv1a64_lines(data, &[0, 0, 1, 2]), vec![0xcbf29ce484222325, 0xaf63dc4c8601ec8c, 0xaf63df4c8601f1a5]);
    }
}
