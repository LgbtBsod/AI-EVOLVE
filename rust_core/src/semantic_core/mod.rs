//! Semantic Core for Dev Probe
//! Compresses logs, states, and events into token-efficient summaries.
//! Implements SRP: Only responsible for data compression and semantic extraction.

use std::collections::{HashMap, HashSet};
use pyo3::prelude::*;
use pyo3::types::{PyDict, PyList};

/// Compresses repetitive log lines into patterns.
/// Example: "Player took 5 dmg" x 100 -> "Player took damage 100 times (avg 5)"
#[pyclass]
pub struct LogCompressor {
    pattern_counts: HashMap<String, u32>,
    numeric_accumulators: HashMap<String, Vec<f64>>,
}

#[pymethods]
impl LogCompressor {
    #[new]
    fn new() -> Self {
        Self {
            pattern_counts: HashMap::new(),
            numeric_accumulators: HashMap::new(),
        }
    }

    /// Ingest a log line and update patterns.
    fn ingest(&mut self, line: &str) {
        // Simple heuristic: replace numbers with <*> to find patterns
        let pattern = regex_replace_numbers(line);
        *self.pattern_counts.entry(pattern.clone()).or_insert(0) += 1;
        
        // Extract numbers for stats if present
        if let Some(nums) = extract_numbers(line) {
            self.numeric_accumulators
                .entry(pattern)
                .or_insert_with(Vec::new)
                .extend(nums);
        }
    }

    /// Generate compressed summary string.
    fn summarize(&self) -> String {
        let mut summary = String::new();
        let mut sorted_patterns: Vec<_> = self.pattern_counts.iter().collect();
        sorted_patterns.sort_by(|a, b| b.1.cmp(a.1)); // Sort by frequency

        for (pattern, count) in sorted_patterns.iter().take(20) { // Top 20 patterns
            if *count > 1 {
                summary.push_str(&format!("[{}x] {}\n", count, pattern));
                if let Some(nums) = self.numeric_accumulators.get(pattern) {
                    let avg: f64 = nums.iter().sum::<f64>() / nums.len() as f64;
                    summary.push_str(&format!("  -> Avg value: {:.2}\n", avg));
                }
            } else {
                summary.push_str(&format!("{}\n", pattern));
            }
        }
        summary
    }

    /// Reset state for new session.
    fn reset(&mut self) {
        self.pattern_counts.clear();
        self.numeric_accumulators.clear();
    }
}

/// Calculates minimal diff between two game states (JSON-like dicts).
/// Returns only changed fields to save tokens.
#[pyclass]
pub struct StateDiffCalculator;

#[pymethods]
impl StateDiffCalculator {
    #[staticmethod]
    fn calculate_diff(py: Python, old_state: &PyDict, new_state: &PyDict) -> PyResult<Py<PyDict>> {
        let diff = PyDict::new(py);
        
        for (key, new_val) in new_state.iter() {
            if !old_state.contains(key)? {
                diff.set_item(key, new_val)?; // New field
            } else {
                let old_val = old_state.get_item(key)?.unwrap();
                if is_different(old_val, new_val) {
                    diff.set_item(key, new_val)?; // Changed field
                }
            }
        }
        
        // Check for deleted fields
        for (key, _) in old_state.iter() {
            if !new_state.contains(key)? {
                diff.set_item(key, "DELETED")?;
            }
        }

        Ok(diff.into())
    }
}

/// Correlates visual events (from L8) with logical errors.
#[pyclass]
pub struct EventCorrelator {
    time_window_ms: u64,
    events: Vec<(u64, String, String)>, // (timestamp, type, payload)
}

#[pymethods]
impl EventCorrelator {
    #[new]
    fn new(time_window_ms: u64) -> Self {
        Self {
            time_window_ms,
            events: Vec::new(),
        }
    }

    fn add_event(&mut self, timestamp: u64, event_type: &str, payload: &str) {
        self.events.push((timestamp, event_type.to_string(), payload.to_string()));
    }

    /// Find correlations: e.g., "Render Blackout" happened within 100ms of "Panic Error".
    fn find_correlations(&self) -> Vec<String> {
        let mut correlations = Vec::new();
        let mut visited = vec![false; self.events.len()];

        for i in 0..self.events.len() {
            if visited[i] { continue; }
            
            let (t1, type1, _) = &self.events[i];
            
            for j in (i + 1)..self.events.len() {
                let (t2, type2, payload2) = &self.events[j];
                
                if t2 - t1 > self.time_window_ms {
                    break; // Sorted by time assumption or break early
                }

                if is_critical_pair(type1, type2) {
                    correlations.push(format!(
                        "CORRELATION: {} at {}ms linked with {} at {}ms ({})",
                        type1, t1, type2, t2, payload2
                    ));
                    visited[j] = true;
                }
            }
        }
        correlations
    }
    
    fn clear(&mut self) {
        self.events.clear();
    }
}

// Helper functions
fn regex_replace_numbers(input: &str) -> String {
    let mut result = String::new();
    let mut last_was_digit = false;
    
    for c in input.chars() {
        if c.is_ascii_digit() {
            if !last_was_digit {
                result.push('*');
                last_was_digit = true;
            }
        } else {
            result.push(c);
            last_was_digit = false;
        }
    }
    result
}

fn extract_numbers(input: &str) -> Option<Vec<f64>> {
    let mut nums = Vec::new();
    let mut current_num = String::new();
    
    for c in input.chars() {
        if c.is_ascii_digit() || c == '.' {
            current_num.push(c);
        } else if !current_num.is_empty() {
            if let Ok(n) = current_num.parse::<f64>() {
                nums.push(n);
            }
            current_num.clear();
        }
    }
    if !current_num.is_empty() {
        if let Ok(n) = current_num.parse::<f64>() {
            nums.push(n);
        }
    }
    
    if nums.is_empty() { None } else { Some(nums) }
}

fn is_different(old: &PyAny, new: &PyAny) -> bool {
    // Simple equality check via Python
    match old.eq(new) {
        Ok(val) => !val,
        Err(_) => true, // If comparison fails, assume different
    }
}

fn is_critical_pair(type1: &str, type2: &str) -> bool {
    let critical_pairs = [
        ("visual_blackout", "panic_error"),
        ("freeze_detected", "timeout_exception"),
        ("low_fps", "memory_leak_warning"),
        ("texture_missing", "asset_load_error"),
    ];
    critical_pairs.iter().any(|(a, b)| {
        (type1 == *a && type2 == *b) || (type1 == *b && type2 == *a)
    })
}

#[pymodule]
fn semantic_core(_py: Python, m: &PyModule) -> PyResult<()> {
    m.add_class::<LogCompressor>()?;
    m.add_class::<StateDiffCalculator>()?;
    m.add_class::<EventCorrelator>()?;
    Ok(())
}
