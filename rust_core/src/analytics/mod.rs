// rust_core/src/analytics/mod.rs
//! L8b: Run analytics kernels for the agent dev tools.
//!
//! Python (tools/probe_kernels.py) orchestrates: it flattens state samples
//! and combat events into column arrays, calls these kernels and turns the
//! numbers into hypotheses/forecasts. Everything here is a pure function
//! over slices - no Python types, no game knowledge - and has a byte-for-byte
//! equivalent Python fallback (parity is checked in tests/test_agent_tools.py),
//! so the tools work without a built rust_core.

/// Least-squares line fit: (slope, intercept). None for <2 points or all-equal x.
pub fn linear_fit(xs: &[f64], ys: &[f64]) -> Option<(f64, f64)> {
    let n = xs.len().min(ys.len());
    if n < 2 {
        return None;
    }
    let nf = n as f64;
    let mx = xs[..n].iter().sum::<f64>() / nf;
    let my = ys[..n].iter().sum::<f64>() / nf;
    let mut sxx = 0.0;
    let mut sxy = 0.0;
    for i in 0..n {
        let dx = xs[i] - mx;
        sxx += dx * dx;
        sxy += dx * (ys[i] - my);
    }
    if sxx == 0.0 {
        return None;
    }
    let slope = sxy / sxx;
    Some((slope, my - slope * mx))
}

const SPARK_CHARS: [char; 8] = ['▁', '▂', '▃', '▄', '▅', '▆', '▇', '█'];

/// Unicode sparkline, downsampled to `width` buckets by taking each bucket's
/// MINIMUM (a short HP dip must stay visible after downsampling).
pub fn sparkline(values: &[f64], width: usize) -> String {
    let vals: Vec<f64> = values.iter().copied().filter(|v| !v.is_nan()).collect();
    if vals.is_empty() || width == 0 {
        return String::new();
    }
    let vals = if vals.len() > width {
        let step = vals.len() as f64 / width as f64;
        (0..width)
            .map(|i| {
                let start = (i as f64 * step) as usize;
                let end = ((((i + 1) as f64) * step) as usize).max(start + 1);
                vals[start..end].iter().copied().fold(f64::INFINITY, f64::min)
            })
            .collect()
    } else {
        vals
    };
    let lo = vals.iter().copied().fold(f64::INFINITY, f64::min);
    let hi = vals.iter().copied().fold(f64::NEG_INFINITY, f64::max);
    if hi - lo < 1e-9 {
        let c = if hi > 0.0 { SPARK_CHARS[7] } else { SPARK_CHARS[0] };
        return std::iter::repeat_n(c, vals.len()).collect();
    }
    vals.iter()
        .map(|v| SPARK_CHARS[(((v - lo) / (hi - lo)) * 7.0 + 0.5).floor() as usize])
        .collect()
}

/// Distance from the player to the nearest enemy for every sample.
/// Enemies of sample i are ex/ey[offsets[i]..offsets[i+1]]; NaN = no enemies.
pub fn nearest_distances(px: &[f64], py: &[f64], offsets: &[usize], ex: &[f64], ey: &[f64]) -> Vec<f64> {
    (0..px.len())
        .map(|i| {
            let (a, b) = (offsets[i], offsets[i + 1]);
            (a..b)
                .map(|j| (ex[j] - px[i]).hypot(ey[j] - py[i]))
                .fold(f64::NAN, |acc, d| if acc.is_nan() || d < acc { d } else { acc })
        })
        .collect()
}

/// First stretch where the (alive) hero stays under `frac` of max HP for at
/// least `min_seconds`: (from_t, to_t, hp_at_to_t). Death resets the stretch.
pub fn pinned_interval(
    ts: &[f64], hp: &[f64], max_hp: &[f64], alive: &[bool], frac: f64, min_seconds: f64,
) -> Option<(f64, f64, f64)> {
    let mut low_since: Option<f64> = None;
    for i in 0..ts.len() {
        if !alive[i] || hp[i] <= 0.0 {
            low_since = None;
            continue;
        }
        let mhp = if max_hp[i] > 0.0 { max_hp[i] } else { 1.0 };
        if hp[i] / mhp < frac {
            let since = *low_since.get_or_insert(ts[i]);
            if ts[i] - since >= min_seconds {
                return Some((since, ts[i], hp[i]));
            }
        } else {
            low_since = None;
        }
    }
    None
}

/// First window of ~`window_s` seconds in which the alive hero moved less than
/// `min_dist` and no timestamp from `busy_ts` (sorted combat event times)
/// fell inside it: (from_t, to_t).
pub fn stuck_interval(
    ts: &[f64], xs: &[f64], ys: &[f64], alive: &[bool], window_s: f64, min_dist: f64, busy_ts: &[f64],
) -> Option<(f64, f64)> {
    let mut start = 0usize;
    let mut count = 0usize;
    for i in 0..ts.len() {
        if !alive[i] {
            count = 0;
            continue;
        }
        if count == 0 {
            start = i;
        }
        count += 1;
        while ts[i] - ts[start] > window_s {
            start += 1;
            count -= 1;
        }
        if count >= 3 && ts[i] - ts[start] >= window_s * 0.9 {
            let span = (start..=i)
                .map(|j| (xs[j] - xs[start]).hypot(ys[j] - ys[start]))
                .fold(0.0, f64::max);
            let (t0, t1) = (ts[start], ts[i]);
            let first_busy = busy_ts.partition_point(|&t| t < t0);
            let busy = first_busy < busy_ts.len() && busy_ts[first_busy] <= t1;
            if span < min_dist && !busy {
                return Some((t0, t1));
            }
        }
    }
    None
}

fn is_hex_id(token: &str) -> bool {
    token.chars().any(|c| c.is_ascii_digit())
        && (token.chars().all(|c| c.is_ascii_hexdigit()) || token.starts_with("0x"))
}

/// Log line -> template: "HH:MM:SS " prefix dropped, every ASCII-alphanumeric
/// run that is a number or a hex-ish id becomes "#".
pub fn log_template(line: &str) -> String {
    let body = strip_time_prefix(line);
    let mut out = String::with_capacity(body.len());
    let mut token = String::new();
    let flush = |token: &mut String, out: &mut String| {
        if !token.is_empty() {
            out.push_str(if is_hex_id(token) { "#" } else { token });
            token.clear();
        }
    };
    for c in body.chars() {
        if c.is_ascii_alphanumeric() {
            token.push(c);
        } else {
            flush(&mut token, &mut out);
            out.push(c);
        }
    }
    flush(&mut token, &mut out);
    out
}

pub fn strip_time_prefix(line: &str) -> &str {
    let b = line.as_bytes();
    let digit = |i: usize| b.get(i).is_some_and(|c| c.is_ascii_digit());
    if b.len() >= 9 && digit(0) && digit(1) && b[2] == b':' && digit(3) && digit(4) && b[5] == b':'
        && digit(6) && digit(7) && b[8] == b' '
    {
        &line[9..]
    } else {
        line
    }
}

/// Collapse repeated log messages: [(count, first original body)], most
/// frequent first, ties in first-seen order; at most `limit` entries.
pub fn log_digest(lines: &[String], limit: usize) -> (Vec<(usize, String)>, usize) {
    let mut order: Vec<(String, usize, String)> = Vec::new();
    let mut index: std::collections::HashMap<String, usize> = std::collections::HashMap::new();
    for line in lines {
        let first_line = line.trim().lines().next().unwrap_or("");
        let key = log_template(first_line);
        match index.get(&key) {
            Some(&i) => order[i].1 += 1,
            None => {
                index.insert(key.clone(), order.len());
                order.push((key, 1, strip_time_prefix(first_line).to_string()));
            }
        }
    }
    let distinct = order.len();
    order.sort_by(|a, b| b.1.cmp(&a.1));
    (order.into_iter().take(limit).map(|(_, n, body)| (n, body)).collect(), distinct)
}

/// Hero columns of one run, struct-of-arrays (one row per state sample).
/// Enemies of sample i are ex/ey[offsets[i]..offsets[i+1]] (living only).
pub struct HeroColumns<'a> {
    pub ts: &'a [f64],
    pub hp: &'a [f64],
    pub max_hp: &'a [f64],
    pub x: &'a [f64],
    pub y: &'a [f64],
    pub alive: &'a [u8],
    pub offsets: &'a [u64],
    pub ex: &'a [f64],
    pub ey: &'a [f64],
}

pub struct HeroScanParams {
    pub low_hp_fraction: f64,
    pub pinned_seconds: f64,
    pub stuck_seconds: f64,
    pub stuck_distance: f64,
    pub spark_width: usize,
}

/// Everything probe_analysis.hypotheses() needs from the hero table,
/// computed in one pass-per-kernel and returned as one structure.
#[derive(Debug, Default, PartialEq)]
pub struct HeroScan {
    pub pinned: Option<(f64, f64, f64)>,
    pub stuck: Option<(f64, f64)>,
    pub death_t: Option<f64>,
    pub invalid_count: usize,
    /// (t, hp, max_hp) of the first sample with NaN or out-of-range HP
    pub invalid_first: Option<(f64, f64, f64)>,
    pub min_nearest: Option<f64>,
    pub hp_sparkline: String,
}

pub fn scan_hero(c: &HeroColumns, p: &HeroScanParams, busy_ts: &[f64]) -> HeroScan {
    let n = c.ts.len();
    let alive: Vec<bool> = c.alive[..n].iter().map(|&a| a != 0).collect();
    let mut scan = HeroScan::default();
    for i in 0..n {
        let (hp, mhp) = (c.hp[i], c.max_hp[i]);
        let bad = hp.is_nan() || c.x[i].is_nan() || c.y[i].is_nan()
            || (alive[i] && (hp > mhp + 0.01 || hp < -0.01));
        if bad {
            scan.invalid_count += 1;
            scan.invalid_first.get_or_insert((c.ts[i], hp, mhp));
        }
        if scan.death_t.is_none() && (!alive[i] || hp <= 0.0) {
            scan.death_t = Some(c.ts[i]);
        }
    }
    let offsets: Vec<usize> = c.offsets.iter().map(|&o| o as usize).collect();
    scan.min_nearest = nearest_distances(c.x, c.y, &offsets, c.ex, c.ey)
        .into_iter()
        .filter(|d| !d.is_nan())
        .fold(None, |acc: Option<f64>, d| Some(acc.map_or(d, |a| a.min(d))));
    scan.pinned = pinned_interval(c.ts, c.hp, c.max_hp, &alive, p.low_hp_fraction, p.pinned_seconds);
    scan.stuck = stuck_interval(c.ts, c.x, c.y, &alive, p.stuck_seconds, p.stuck_distance, busy_ts);
    scan.hp_sparkline = sparkline(c.hp, p.spark_width);
    scan
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn fit_recovers_line() {
        let (s, b) = linear_fit(&[0.0, 1.0, 2.0, 3.0], &[1.0, 3.0, 5.0, 7.0]).unwrap();
        assert!((s - 2.0).abs() < 1e-12 && (b - 1.0).abs() < 1e-12);
        assert!(linear_fit(&[1.0, 1.0], &[0.0, 5.0]).is_none());
    }

    #[test]
    fn sparkline_keeps_dips() {
        assert_eq!(sparkline(&[0.0, 7.0], 24), "▁█");
        let mut v = vec![10.0; 100];
        v[50] = 0.0;
        assert!(sparkline(&v, 10).contains('▁'));
        assert_eq!(sparkline(&[5.0, 5.0], 24), "██");
    }

    #[test]
    fn nearest_handles_empty_samples() {
        let d = nearest_distances(&[0.0, 0.0], &[0.0, 0.0], &[0, 0, 2], &[3.0, 1.0], &[4.0, 0.0]);
        assert!(d[0].is_nan());
        assert_eq!(d[1], 1.0);
    }

    #[test]
    fn pinned_and_stuck() {
        let ts: Vec<f64> = (0..10).map(|i| i as f64).collect();
        let hp = vec![100.0, 10.0, 10.0, 10.0, 10.0, 10.0, 10.0, 10.0, 10.0, 10.0];
        let alive = vec![true; 10];
        assert_eq!(pinned_interval(&ts, &hp, &[100.0; 10], &alive, 0.2, 5.0), Some((1.0, 6.0, 10.0)));
        let still = vec![1.0; 10];
        assert_eq!(stuck_interval(&ts, &still, &still, &alive, 4.0, 0.5, &[]), Some((0.0, 4.0)));
        assert_eq!(stuck_interval(&ts, &still, &still, &alive, 4.0, 0.5, &[2.0]), Some((3.0, 7.0)));
    }

    #[test]
    fn scan_hero_one_call() {
        let ts = [0.0, 1.0, 2.0];
        let cols = HeroColumns {
            ts: &ts, hp: &[100.0, 50.0, 0.0], max_hp: &[100.0; 3], x: &[0.0; 3], y: &[0.0; 3],
            alive: &[1, 1, 0], offsets: &[0, 1, 1, 2], ex: &[3.0, 1.0], ey: &[4.0, 0.0],
        };
        let p = HeroScanParams { low_hp_fraction: 0.2, pinned_seconds: 5.0, stuck_seconds: 8.0,
                                 stuck_distance: 0.5, spark_width: 24 };
        let scan = scan_hero(&cols, &p, &[]);
        assert_eq!(scan.death_t, Some(2.0));
        assert_eq!(scan.min_nearest, Some(1.0));
        assert_eq!(scan.invalid_count, 0);
        assert_eq!(scan.hp_sparkline, "█▅▁");
    }

    #[test]
    fn log_digest_groups_by_template() {
        let lines: Vec<String> = ["12:00:01 WARNING x: hp 5 of enemy_1a2b3c4d", "12:00:02 WARNING x: hp 7 of enemy_ffff0000", "ERROR boom"]
            .iter().map(|s| s.to_string()).collect();
        let (digest, distinct) = log_digest(&lines, 10);
        assert_eq!(distinct, 2);
        assert_eq!(digest[0], (2, "WARNING x: hp 5 of enemy_1a2b3c4d".to_string()));
        assert_eq!(log_template("t=12.5 id=0x1f"), "t=#.# id=#");
    }
}
