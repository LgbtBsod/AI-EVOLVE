// FFI Module (Python ↔ Rust interface)
//! PyO3 bindings for Python integration

use pyo3::prelude::*;
use pyo3::types::PyDict;
use pyo3::buffer::{Element, PyUntypedBuffer};
use crate::simulation::SimulationEnv;
use crate::generator::WorldGenerator;
use crate::probe::{ProbeConfig, analyze_frame, compute_ssim};
use crate::semantic_core::{LogCompressor as RustLogCompressor, StateDiffCalculator as RustStateDiffCalculator, EventCorrelator as RustEventCorrelator};
use crate::analytics;
use crate::qa;
use crate::lua_content;
use crate::tactics;
use crate::combat;
use crate::simulation::pathfinding::{self as pathing, Algorithm, CostGrid};
use image::DynamicImage;

/// Python module for rust_core
#[pymodule]
fn rust_core(m: &Bound<'_, PyModule>) -> PyResult<()> {
    m.add_class::<PySimulationEnv>()?;
    m.add_class::<PyWorldGenerator>()?;
    m.add_class::<PyProbeAnalyzer>()?;
    m.add_class::<PyLogCompressor>()?;
    m.add_class::<PyStateDiffCalculator>()?;
    m.add_class::<PyEventCorrelator>()?;
    m.add_class::<PyRunAnalytics>()?;
    m.add_class::<PyQaKernels>()?;
    m.add_class::<PyLuaContent>()?;
    m.add_class::<PyTacticsBandit>()?;
    m.add_class::<PyFlowField>()?;
    m.add_function(wrap_pyfunction!(py_find_path, m)?)?;
    m.add_function(wrap_pyfunction!(py_flow_field, m)?)?;
    m.add_function(wrap_pyfunction!(py_resolve_hit, m)?)?;
    m.add_function(wrap_pyfunction!(py_resolve_hits, m)?)?;
    // Aliases for cleaner Python API
    m.add("WorldGenerator", m.getattr("PyWorldGenerator")?)?;
    m.add("SimulationEnv", m.getattr("PySimulationEnv")?)?;
    m.add("ProbeAnalyzer", m.getattr("PyProbeAnalyzer")?)?;
    m.add("LogCompressor", m.getattr("PyLogCompressor")?)?;
    m.add("StateDiffCalculator", m.getattr("PyStateDiffCalculator")?)?;
    m.add("EventCorrelator", m.getattr("PyEventCorrelator")?)?;
    m.add("RunAnalytics", m.getattr("PyRunAnalytics")?)?;
    m.add("QaKernels", m.getattr("PyQaKernels")?)?;
    m.add("LuaContent", m.getattr("PyLuaContent")?)?;
    m.add("TacticsBandit", m.getattr("PyTacticsBandit")?)?;
    m.add("FlowField", m.getattr("PyFlowField")?)?;
    m.add("VERSION", env!("CARGO_PKG_VERSION"))?;
    Ok(())
}

#[pyclass]
struct PySimulationEnv {
    // Not wired yet: step()/step_batch() below are stubs that do not call into it.
    #[allow(dead_code)]
    inner: SimulationEnv,
}

#[pymethods]
impl PySimulationEnv {
    #[new]
    fn new(seed: u64) -> Self {
        Self {
            inner: SimulationEnv::new(seed),
        }
    }

    #[allow(clippy::type_complexity)]
    fn step(&mut self, py: Python<'_>, _actions: Vec<Py<PyAny>>) -> PyResult<(Vec<Py<PyAny>>, Vec<f32>, Vec<bool>, Py<PyAny>)> {
        // Convert Python actions to Rust actions
        // Call inner.step()
        // Convert results back to Python
        Ok((vec![], vec![0.0], vec![false], py.None()))
    }

    #[allow(clippy::type_complexity)]
    fn step_batch(&mut self, py: Python<'_>, _actions: Vec<Vec<Py<PyAny>>>) -> PyResult<(Vec<Vec<Py<PyAny>>>, Vec<Vec<f32>>, Vec<Vec<bool>>, Vec<Py<PyAny>>)> {
        Ok((vec![], vec![], vec![], vec![py.None()]))
    }
}

#[pyclass]
struct PyWorldGenerator {
    inner: WorldGenerator,
}

#[pymethods]
impl PyWorldGenerator {
    #[new]
    fn new(seed: u64, version: &str) -> Self {
        Self {
            inner: WorldGenerator::new(seed, version),
        }
    }

    fn generate(&self, py: Python<'_>, bricks_config: &str) -> PyResult<Py<PyAny>> {
        match self.inner.generate(bricks_config) {
            Ok(world) => {
                // Convert World to Python dict
                let dict = PyDict::new(py);
                dict.set_item("seed", world.seed)?;
                dict.set_item("map_id", world.map_id)?;
                dict.set_item("entity_count", world.entities.len())?;
                dict.set_item("grid_width", world.grid.width)?;
                dict.set_item("grid_height", world.grid.height)?;
                Ok(dict.into_any().unbind())
            }
            Err(e) => Err(pyo3::exceptions::PyRuntimeError::new_err(e)),
        }
    }
}

/// Python wrapper for probe analytics
#[pyclass]
struct PyProbeAnalyzer {
    config: ProbeConfig,
    prev_frame: Option<DynamicImage>,
}

#[pymethods]
impl PyProbeAnalyzer {
    #[new]
    #[pyo3(signature = (config_dict=None))]
    fn new(config_dict: Option<&Bound<'_, PyDict>>) -> PyResult<Self> {
        let mut config = ProbeConfig::default();

        if let Some(dict) = config_dict {
            if let Ok(Some(v)) = dict.get_item("blank_frame_stddev_threshold") {
                config.blank_frame_stddev_threshold = v.extract()?;
            }
            if let Ok(Some(v)) = dict.get_item("visual_hash_bits") {
                config.visual_hash_bits = v.extract()?;
            }
            if let Ok(Some(v)) = dict.get_item("hamming_threshold") {
                config.hamming_threshold = v.extract()?;
            }
            if let Ok(Some(v)) = dict.get_item("motion_detection_threshold") {
                config.motion_detection_threshold = v.extract()?;
            }
            if let Ok(Some(v)) = dict.get_item("brightness_anomaly_threshold") {
                config.brightness_anomaly_threshold = v.extract()?;
            }
            if let Ok(Some(v)) = dict.get_item("ssim_threshold") {
                config.ssim_threshold = v.extract()?;
            }
        }

        Ok(Self {
            config,
            prev_frame: None,
        })
    }

    /// Analyze a single frame from PNG bytes
    /// Returns dict with perceptual_hash, brightness, motion, is_blank, edge_density, complexity_score
    fn analyze_frame(&mut self, py: Python<'_>, png_bytes: &[u8]) -> PyResult<Py<PyAny>> {
        let image = image::load_from_memory(png_bytes)
            .map_err(|e| pyo3::exceptions::PyValueError::new_err(format!("Invalid image: {}", e)))?;

        let prev_ref = self.prev_frame.as_ref();
        let analysis = analyze_frame(&image, prev_ref, &self.config);

        // Store current frame for next motion comparison
        self.prev_frame = Some(image);

        let dict = PyDict::new(py);

        // Perceptual hash as hex string
        if let Some(hash) = &analysis.perceptual_hash {
            let hex = format!("{:016x}{:016x}{:016x}{:016x}",
                hash.bits[0], hash.bits[1], hash.bits[2], hash.bits[3]);
            dict.set_item("perceptual_hash", hex)?;
        } else {
            dict.set_item("perceptual_hash", py.None())?;
        }

        // Brightness stats
        if let Some(bright) = &analysis.brightness {
            let bright_dict = PyDict::new(py);
            bright_dict.set_item("mean", bright.mean)?;
            bright_dict.set_item("stddev", bright.stddev)?;
            bright_dict.set_item("min", bright.min)?;
            bright_dict.set_item("max", bright.max)?;
            dict.set_item("brightness", bright_dict)?;
        }

        // Motion stats
        if let Some(motion) = &analysis.motion {
            let motion_dict = PyDict::new(py);
            motion_dict.set_item("mean_magnitude", motion.mean_magnitude)?;
            motion_dict.set_item("max_magnitude", motion.max_magnitude)?;
            motion_dict.set_item("std_magnitude", motion.std_magnitude)?;
            motion_dict.set_item("high_motion_pixels", motion.high_motion_pixels)?;
            motion_dict.set_item("motion_ratio", motion.motion_ratio)?;
            dict.set_item("motion", motion_dict)?;
        }

        dict.set_item("is_blank", analysis.is_blank)?;
        dict.set_item("edge_density", analysis.edge_density)?;
        dict.set_item("complexity_score", analysis.complexity_score)?;

        Ok(dict.into_any().unbind())
    }

    /// Compare two frames and return SSIM score
    fn compare_frames(&self, py: Python<'_>, frame1_bytes: &[u8], frame2_bytes: &[u8]) -> PyResult<Py<PyAny>> {
        let img1 = image::load_from_memory(frame1_bytes)
            .map_err(|e| pyo3::exceptions::PyValueError::new_err(format!("Invalid image 1: {}", e)))?;
        let img2 = image::load_from_memory(frame2_bytes)
            .map_err(|e| pyo3::exceptions::PyValueError::new_err(format!("Invalid image 2: {}", e)))?;

        let ssim_result = compute_ssim(&img1, &img2)
            .ok_or_else(|| pyo3::exceptions::PyValueError::new_err("Frames must have same dimensions"))?;

        let dict = PyDict::new(py);
        dict.set_item("ssim_score", ssim_result.score)?;
        dict.set_item("mean_score", ssim_result.mean_score)?;
        dict.set_item("is_similar", ssim_result.mean_score > self.config.ssim_threshold)?;
        Ok(dict.into_any().unbind())
    }

    /// Compute hamming distance between two perceptual hashes
    #[staticmethod]
    fn hamming_distance(hash1: &str, hash2: &str) -> PyResult<u32> {
        if hash1.len() != 64 || hash2.len() != 64 {
            return Err(pyo3::exceptions::PyValueError::new_err(
                "Hashes must be 64 hex characters (256 bits)"
            ));
        }

        let parse_hex = |hex: &str| -> Result<[u64; 4], String> {
            let mut bits = [0u64; 4];
            for (i, word) in bits.iter_mut().enumerate() {
                let start = i * 16;
                let end = start + 16;
                *word = u64::from_str_radix(&hex[start..end], 16)
                    .map_err(|e| format!("Invalid hex at position {}: {}", i, e))?;
            }
            Ok(bits)
        };

        let bits1 = parse_hex(hash1).map_err(pyo3::exceptions::PyValueError::new_err)?;
        let bits2 = parse_hex(hash2).map_err(pyo3::exceptions::PyValueError::new_err)?;

        let mut distance = 0u32;
        for i in 0..4 {
            distance += (bits1[i] ^ bits2[i]).count_ones();
        }

        Ok(distance)
    }

    /// Reset previous frame (for when you want to restart motion comparison)
    fn reset(&mut self) {
        self.prev_frame = None;
    }
}

// ============================================================================
// Semantic Core FFI Wrappers
// ============================================================================

#[pyclass]
struct PyLogCompressor {
    inner: RustLogCompressor,
}

#[pymethods]
impl PyLogCompressor {
    #[new]
    fn new() -> Self {
        Self {
            inner: RustLogCompressor::new(),
        }
    }

    fn ingest(&mut self, line: &str) {
        self.inner.ingest(line);
    }

    fn summarize(&self) -> String {
        self.inner.summarize()
    }

    fn reset(&mut self) {
        self.inner.reset();
    }
}

#[pyclass]
struct PyStateDiffCalculator;

#[pymethods]
impl PyStateDiffCalculator {
    #[staticmethod]
    fn calculate_diff(py: Python<'_>, old_state: &Bound<'_, PyDict>, new_state: &Bound<'_, PyDict>) -> PyResult<Py<PyDict>> {
        RustStateDiffCalculator::calculate_diff(py, old_state, new_state)
    }
}

#[pyclass]
struct PyEventCorrelator {
    inner: RustEventCorrelator,
}

#[pymethods]
impl PyEventCorrelator {
    #[new]
    #[pyo3(signature = (time_window_ms=100))]
    fn new(time_window_ms: u64) -> Self {
        Self {
            inner: RustEventCorrelator::new(time_window_ms),
        }
    }

    fn add_event(&mut self, timestamp: u64, event_type: &str, payload: &str) {
        self.inner.add_event(timestamp, event_type, payload);
    }

    fn find_correlations(&self) -> Vec<String> {
        self.inner.find_correlations()
    }

    fn clear(&mut self) {
        self.inner.clear();
    }
}

// ============================================================================
// Run analytics FFI (agent dev tools: tools/probe_kernels.py)
// ============================================================================

/// Stateless number-crunching kernels for tools/probe_analysis.py.
///
/// Data crosses the layer as columnar binary buffers (Python `array('d')`,
/// `array('B')`, `array('Q')`, numpy arrays, memoryviews - anything with the
/// buffer protocol): one memcpy per column instead of converting every float
/// object. `scan_hero` takes a whole struct-of-arrays table object and
/// returns one dict, so a full hero analysis is a single FFI crossing.
/// Every method releases the GIL while computing.
#[pyclass]
struct PyRunAnalytics;

/// Buffer-protocol object -> Vec<T> with one memcpy. Empty buffers are
/// special-cased: CPython may hand out an unaligned pointer for an empty
/// array('d'), which a typed buffer view rejects.
fn buf<T: Element + Copy>(py: Python<'_>, obj: &Bound<'_, PyAny>) -> PyResult<Vec<T>> {
    let untyped = PyUntypedBuffer::get(obj)?;
    if untyped.item_count() == 0 {
        return Ok(Vec::new());
    }
    untyped.into_typed::<T>()?.to_vec(py)
}

fn column<T: Element + Copy>(py: Python<'_>, table: &Bound<'_, PyAny>, name: &str) -> PyResult<Vec<T>> {
    buf(py, &table.getattr(name)?)
}

fn same_len(n: usize, others: &[usize]) -> PyResult<()> {
    if others.iter().any(|&l| l != n) {
        return Err(pyo3::exceptions::PyValueError::new_err("columns must have equal length"));
    }
    Ok(())
}

fn param(params: &Bound<'_, PyDict>, name: &str, default: f64) -> PyResult<f64> {
    match params.get_item(name)? {
        Some(v) => v.extract(),
        None => Ok(default),
    }
}

#[pymethods]
impl PyRunAnalytics {
    #[staticmethod]
    fn linear_fit(py: Python<'_>, xs: &Bound<'_, PyAny>, ys: &Bound<'_, PyAny>) -> PyResult<Option<(f64, f64)>> {
        let (xs, ys) = (buf::<f64>(py, xs)?, buf::<f64>(py, ys)?);
        Ok(py.detach(|| analytics::linear_fit(&xs, &ys)))
    }

    #[staticmethod]
    #[pyo3(signature = (values, width=24))]
    fn sparkline(py: Python<'_>, values: &Bound<'_, PyAny>, width: usize) -> PyResult<String> {
        let values = buf::<f64>(py, values)?;
        Ok(py.detach(|| analytics::sparkline(&values, width)))
    }

    #[staticmethod]
    fn nearest_distances(
        py: Python<'_>, px: &Bound<'_, PyAny>, py_: &Bound<'_, PyAny>, offsets: &Bound<'_, PyAny>, ex: &Bound<'_, PyAny>, ey: &Bound<'_, PyAny>,
    ) -> PyResult<Vec<f64>> {
        let (px, py_, ex, ey) = (buf::<f64>(py, px)?, buf::<f64>(py, py_)?, buf::<f64>(py, ex)?, buf::<f64>(py, ey)?);
        let offsets: Vec<usize> = buf::<u64>(py, offsets)?.into_iter().map(|o| o as usize).collect();
        if offsets.len() != px.len() + 1 || py_.len() != px.len() || ex.len() != ey.len()
            || offsets.last().copied().unwrap_or(0) > ex.len()
        {
            return Err(pyo3::exceptions::PyValueError::new_err("inconsistent column lengths"));
        }
        Ok(py.detach(|| analytics::nearest_distances(&px, &py_, &offsets, &ex, &ey)))
    }

    #[staticmethod]
    fn pinned_interval(
        py: Python<'_>, ts: &Bound<'_, PyAny>, hp: &Bound<'_, PyAny>, max_hp: &Bound<'_, PyAny>, alive: &Bound<'_, PyAny>,
        frac: f64, min_seconds: f64,
    ) -> PyResult<Option<(f64, f64, f64)>> {
        let (ts, hp, max_hp) = (buf::<f64>(py, ts)?, buf::<f64>(py, hp)?, buf::<f64>(py, max_hp)?);
        let alive: Vec<bool> = buf::<u8>(py, alive)?.into_iter().map(|a| a != 0).collect();
        same_len(ts.len(), &[hp.len(), max_hp.len(), alive.len()])?;
        Ok(py.detach(|| analytics::pinned_interval(&ts, &hp, &max_hp, &alive, frac, min_seconds)))
    }

    #[staticmethod]
    #[allow(clippy::too_many_arguments)]
    fn stuck_interval(
        py: Python<'_>, ts: &Bound<'_, PyAny>, xs: &Bound<'_, PyAny>, ys: &Bound<'_, PyAny>, alive: &Bound<'_, PyAny>,
        window_s: f64, min_dist: f64, busy_ts: &Bound<'_, PyAny>,
    ) -> PyResult<Option<(f64, f64)>> {
        let (ts, xs, ys, busy) = (buf::<f64>(py, ts)?, buf::<f64>(py, xs)?, buf::<f64>(py, ys)?, buf::<f64>(py, busy_ts)?);
        let alive: Vec<bool> = buf::<u8>(py, alive)?.into_iter().map(|a| a != 0).collect();
        same_len(ts.len(), &[xs.len(), ys.len(), alive.len()])?;
        Ok(py.detach(|| analytics::stuck_interval(&ts, &xs, &ys, &alive, window_s, min_dist, &busy)))
    }

    /// table: object with buffer attributes ts, hp, max_hp, x, y (f64), alive (u8),
    /// offsets (u64), ex, ey (f64) - see tools/probe_kernels.py:HeroTable.
    /// params: dict with low_hp_fraction, pinned_seconds, stuck_seconds, stuck_distance, spark_width.
    #[staticmethod]
    fn scan_hero(
        py: Python<'_>, table: &Bound<'_, PyAny>, params: &Bound<'_, PyDict>, busy_ts: &Bound<'_, PyAny>,
    ) -> PyResult<Py<PyDict>> {
        let (ts, hp, max_hp): (Vec<f64>, Vec<f64>, Vec<f64>) =
            (column(py, table, "ts")?, column(py, table, "hp")?, column(py, table, "max_hp")?);
        let (x, y): (Vec<f64>, Vec<f64>) = (column(py, table, "x")?, column(py, table, "y")?);
        let alive: Vec<u8> = column(py, table, "alive")?;
        let offsets: Vec<u64> = column(py, table, "offsets")?;
        let (ex, ey): (Vec<f64>, Vec<f64>) = (column(py, table, "ex")?, column(py, table, "ey")?);
        let n = ts.len();
        if [hp.len(), max_hp.len(), x.len(), y.len(), alive.len()].iter().any(|&l| l != n)
            || offsets.len() != n + 1 || ex.len() != ey.len()
            || offsets.last().copied().unwrap_or(0) as usize > ex.len()
        {
            return Err(pyo3::exceptions::PyValueError::new_err("inconsistent HeroTable column lengths"));
        }
        let p = analytics::HeroScanParams {
            low_hp_fraction: param(params, "low_hp_fraction", 0.2)?,
            pinned_seconds: param(params, "pinned_seconds", 5.0)?,
            stuck_seconds: param(params, "stuck_seconds", 8.0)?,
            stuck_distance: param(params, "stuck_distance", 0.5)?,
            spark_width: param(params, "spark_width", 24.0)? as usize,
        };
        let busy = buf::<f64>(py, busy_ts)?;
        let scan = py.detach(|| {
            let cols = analytics::HeroColumns {
                ts: &ts, hp: &hp, max_hp: &max_hp, x: &x, y: &y, alive: &alive, offsets: &offsets, ex: &ex, ey: &ey,
            };
            analytics::scan_hero(&cols, &p, &busy)
        });
        let d = PyDict::new(py);
        d.set_item("pinned", scan.pinned)?;
        d.set_item("stuck", scan.stuck)?;
        d.set_item("death_t", scan.death_t)?;
        d.set_item("invalid_count", scan.invalid_count)?;
        d.set_item("invalid_first", scan.invalid_first)?;
        d.set_item("min_nearest", scan.min_nearest)?;
        d.set_item("hp_sparkline", scan.hp_sparkline)?;
        Ok(d.unbind())
    }

    #[staticmethod]
    fn log_template(line: &str) -> String {
        analytics::log_template(line)
    }

    /// -> ([(count, first_body)], distinct_templates)
    #[staticmethod]
    #[pyo3(signature = (lines, limit=10))]
    fn log_digest(py: Python<'_>, lines: Vec<String>, limit: usize) -> (Vec<(usize, String)>, usize) {
        py.detach(|| analytics::log_digest(&lines, limit))
    }
}

// ============================================================================
// QA kernels FFI (tools/qa.py via tools/probe_kernels.py)
// ============================================================================

/// Graph reachability (CSR buffers), bootstrap statistics, line fingerprints.
#[pyclass]
struct PyQaKernels;

#[pymethods]
impl PyQaKernels {
    /// offsets/targets: CSR adjacency as array('Q'); roots: array('Q') -> list of 0/1 flags.
    #[staticmethod]
    fn reach(py: Python<'_>, offsets: &Bound<'_, PyAny>, targets: &Bound<'_, PyAny>, roots: &Bound<'_, PyAny>) -> PyResult<Vec<u8>> {
        let (offsets, targets, roots) = (buf::<u64>(py, offsets)?, buf::<u64>(py, targets)?, buf::<u64>(py, roots)?);
        if offsets.windows(2).any(|w| w[0] > w[1]) || offsets.last().copied().unwrap_or(0) as usize > targets.len() {
            return Err(pyo3::exceptions::PyValueError::new_err("offsets must be non-decreasing and within targets"));
        }
        Ok(py.detach(|| qa::reach(&offsets, &targets, &roots)))
    }

    /// values: array('d') -> dict(n, mean, sd, min, p5, p50, p95, max, ci_lo, ci_hi)
    #[staticmethod]
    #[pyo3(signature = (values, resamples=2000, seed=0))]
    fn describe(py: Python<'_>, values: &Bound<'_, PyAny>, resamples: usize, seed: u64) -> PyResult<Py<PyDict>> {
        let values = buf::<f64>(py, values)?;
        let d = py.detach(|| qa::describe(&values, resamples, seed));
        let out = PyDict::new(py);
        out.set_item("n", d.n)?;
        for (k, v) in [("mean", d.mean), ("sd", d.sd), ("min", d.min), ("p5", d.p5), ("p50", d.p50),
                       ("p95", d.p95), ("max", d.max), ("ci_lo", d.ci_lo), ("ci_hi", d.ci_hi)] {
            out.set_item(k, v)?;
        }
        Ok(out.unbind())
    }

    /// data: bytes-like, offsets: array('Q') line boundaries -> list of u64 FNV-1a hashes.
    #[staticmethod]
    fn fnv1a64_lines(py: Python<'_>, data: &Bound<'_, PyAny>, offsets: &Bound<'_, PyAny>) -> PyResult<Vec<u64>> {
        let (data, offsets) = (buf::<u8>(py, data)?, buf::<u64>(py, offsets)?);
        Ok(py.detach(|| qa::fnv1a64_lines(&data, &offsets)))
    }
}

// ============================================================================
// Lua content FFI (tools/lua_bridge.py)
// ============================================================================

/// Sandboxed Lua 5.5 -> one JSON string (json.loads on the Python side).
#[pyclass]
struct PyLuaContent;

fn lua_limits(memory_mb: usize, max_instructions: u64) -> lua_content::Limits {
    lua_content::Limits { memory_bytes: memory_mb << 20, instructions: max_instructions }
}

#[pymethods]
impl PyLuaContent {
    /// Lua helpers shared with the lupa fallback (export.lua).
    #[classattr]
    const EXPORT_LUA: &'static str = lua_content::EXPORT_LUA;

    /// Execute `source` and return its data as JSON. `globals`: names of global
    /// tables to return instead of the chunk's return value (settings files).
    #[staticmethod]
    #[pyo3(signature = (source, chunk_name="content", globals=None, memory_mb=1024, max_instructions=2_000_000_000))]
    fn load_json(py: Python<'_>, source: &str, chunk_name: &str, globals: Option<Vec<String>>,
                 memory_mb: usize, max_instructions: u64) -> PyResult<String> {
        let globals = globals.unwrap_or_default();
        let limits = lua_limits(memory_mb, max_instructions);
        py.detach(|| lua_content::export_json(source, chunk_name, &globals, limits))
            .map_err(pyo3::exceptions::PyValueError::new_err)
    }

    /// Evaluate every pred() condition of `source` on each context of `ctxs_json`
    /// (JSON array) -> JSON array of {condition source: result}.
    #[staticmethod]
    #[pyo3(signature = (source, ctxs_json, chunk_name="content", memory_mb=1024, max_instructions=2_000_000_000))]
    fn eval_preds_json(py: Python<'_>, source: &str, ctxs_json: &str, chunk_name: &str,
                       memory_mb: usize, max_instructions: u64) -> PyResult<String> {
        let limits = lua_limits(memory_mb, max_instructions);
        py.detach(|| lua_content::eval_preds_json(source, chunk_name, ctxs_json, limits))
            .map_err(pyo3::exceptions::PyValueError::new_err)
    }
}

// ============================================================================
// Tactics memory FFI (src/gameplay/tactics.py)
// ============================================================================

/// Discounted UCB1 bandit: contexts (enemy archetypes) x arms (tactics).
#[pyclass]
struct PyTacticsBandit {
    inner: tactics::Bandit,
}

#[pymethods]
impl PyTacticsBandit {
    #[new]
    #[pyo3(signature = (contexts, arms, c=0.6, decay=0.97))]
    fn new(contexts: usize, arms: usize, c: f64, decay: f64) -> PyResult<Self> {
        if arms == 0 || contexts == 0 {
            return Err(pyo3::exceptions::PyValueError::new_err("contexts and arms must be > 0"));
        }
        Ok(Self { inner: tactics::Bandit::new(contexts, arms, c, decay) })
    }

    #[pyo3(signature = (ctx, allowed=None))]
    fn select(&self, ctx: usize, allowed: Option<Vec<bool>>) -> PyResult<usize> {
        self.check(ctx, 0)?;
        Ok(self.inner.select(ctx, &allowed.unwrap_or_default()))
    }

    fn update(&mut self, ctx: usize, arm: usize, reward: f64) -> PyResult<()> {
        self.check(ctx, arm)?;
        self.inner.update(ctx, arm, reward);
        Ok(())
    }

    fn means(&self, ctx: usize) -> PyResult<Vec<f64>> {
        self.check(ctx, 0)?;
        Ok(self.inner.means(ctx))
    }

    /// (counts, sums) - to save the memory between sessions.
    fn state(&self) -> (Vec<f64>, Vec<f64>) {
        (self.inner.counts.clone(), self.inner.sums.clone())
    }

    fn load_state(&mut self, counts: Vec<f64>, sums: Vec<f64>) -> PyResult<()> {
        if counts.len() != self.inner.counts.len() || sums.len() != self.inner.sums.len() {
            return Err(pyo3::exceptions::PyValueError::new_err("state shape does not match"));
        }
        self.inner.counts = counts;
        self.inner.sums = sums;
        Ok(())
    }
}

impl PyTacticsBandit {
    fn check(&self, ctx: usize, arm: usize) -> PyResult<()> {
        if ctx >= self.inner.contexts() || arm >= self.inner.arms {
            return Err(pyo3::exceptions::PyIndexError::new_err("context or arm out of range"));
        }
        Ok(())
    }
}

// ============================================================================
// Grid pathfinding FFI (src/gameplay/pathfinding.py)
// ============================================================================

/// Coordinates from Python ints: anything outside i32 is "off the grid".
fn py_cell(p: (i64, i64)) -> (i32, i32) {
    (i32::try_from(p.0).unwrap_or(-1), i32::try_from(p.1).unwrap_or(-1))
}

/// Optimal path [(x, y), ...] over a row-major cost grid (0 = wall, 1..255 = cost of entering).
/// `algorithm`: "auto" | "astar" | "jps" (ValueError for jps on a non-uniform grid).
#[pyfunction]
#[pyo3(name = "find_path", signature = (width, height, costs, start, goal, algorithm="auto"))]
fn py_find_path(
    py: Python<'_>,
    width: usize,
    height: usize,
    costs: &[u8],
    start: (i64, i64),
    goal: (i64, i64),
    algorithm: &str,
) -> PyResult<Vec<(i32, i32)>> {
    let algorithm = Algorithm::parse(algorithm).map_err(pyo3::exceptions::PyValueError::new_err)?;
    let grid = CostGrid::new(width, height, costs).map_err(pyo3::exceptions::PyValueError::new_err)?;
    let (start, goal) = (py_cell(start), py_cell(goal));
    py.detach(|| pathing::find_path(&grid, start, goal, algorithm))
        .map_err(pyo3::exceptions::PyValueError::new_err)
}

/// Dijkstra flow field toward `target`: `.distance(x, y)`, `.direction(x, y)`, `.directions()`.
#[pyfunction]
#[pyo3(name = "flow_field")]
fn py_flow_field(py: Python<'_>, width: usize, height: usize, costs: &[u8], target: (i64, i64)) -> PyResult<PyFlowField> {
    let grid = CostGrid::new(width, height, costs).map_err(pyo3::exceptions::PyValueError::new_err)?;
    let target = py_cell(target);
    let inner = py.detach(|| pathing::FlowField::compute(&grid, target));
    Ok(PyFlowField { inner })
}

#[pyclass]
struct PyFlowField {
    inner: pathing::FlowField,
}

#[pymethods]
impl PyFlowField {
    #[getter]
    fn width(&self) -> i32 {
        self.inner.width()
    }

    #[getter]
    fn height(&self) -> i32 {
        self.inner.height()
    }

    #[getter]
    fn target(&self) -> (i32, i32) {
        self.inner.target()
    }

    /// Cost of the cheapest path from (x, y) to the target; None if unreachable/blocked/outside.
    fn distance(&self, x: i64, y: i64) -> Option<f64> {
        let (x, y) = py_cell((x, y));
        self.inner.distance(x, y)
    }

    /// The step (dx, dy) toward the target; None at the target or when there is no path.
    fn direction(&self, x: i64, y: i64) -> Option<(i32, i32)> {
        let (x, y) = py_cell((x, y));
        self.inner.direction(x, y)
    }

    /// Distances by rows, inf = no path.
    fn distances(&self) -> Vec<f64> {
        self.inner.distances().to_vec()
    }

    /// Flat [dx0, dy0, dx1, dy1, ...] by rows; (0, 0) = no step.
    fn directions(&self, py: Python<'_>) -> Vec<i32> {
        py.detach(|| self.inner.directions())
    }
}

// ============================================================================
// Damage pipeline FFI (src/effects/damage.py)
// ============================================================================

/// One hit through the damage kernel (rust_core/src/combat). `params` = 16 numbers in the order of
/// `damage.PARAMS`, `rolls` = 5 numbers (NaN = not drawn yet), `consts` = 11 numbers of damage.lua.
/// Returns (need, hit, dodged, blocked, crit, damage_before, armor_ignored, armor_reduced, resisted,
/// blocked_amount, final); need != 0 = "draw roll need-1 and call again".
#[pyfunction]
#[pyo3(name = "resolve_hit")]
fn py_resolve_hit(
    params: Vec<f64>,
    rolls: Vec<f64>,
    consts: Vec<f64>,
) -> PyResult<(i64, i64, i64, i64, i64, f64, f64, f64, f64, f64, f64)> {
    let bad = pyo3::exceptions::PyValueError::new_err;
    let p = combat::Params::from_slice(&params).map_err(bad)?;
    let c = combat::Consts::from_slice(&consts).map_err(bad)?;
    let r: [f64; combat::N_ROLLS] = rolls
        .try_into()
        .map_err(|v: Vec<f64>| bad(format!("rolls: expected {} numbers, got {}", combat::N_ROLLS, v.len())))?;
    let o = combat::resolve_hit(&p, &c, &r);
    Ok((
        o.need, o.hit as i64, o.dodged as i64, o.blocked as i64, o.crit as i64, o.damage_before, o.armor_ignored,
        o.armor_reduced, o.resisted, o.blocked_amount, o.finalv,
    ))
}

/// Many hits from column buffers (buffer protocol, f64): 16 parameter columns, 5 roll columns, the 11
/// constants. Returns 11 `bytes` (native-endian f64 columns, `array('d').frombytes`) in the order of
/// `damage.OUT_FIELDS`.
#[pyfunction]
#[pyo3(name = "resolve_hits")]
fn py_resolve_hits<'py>(
    py: Python<'py>,
    params: Vec<Bound<'py, PyAny>>,
    rolls: Vec<Bound<'py, PyAny>>,
    consts: Vec<f64>,
) -> PyResult<Vec<Bound<'py, pyo3::types::PyBytes>>> {
    let bad = pyo3::exceptions::PyValueError::new_err;
    let c = combat::Consts::from_slice(&consts).map_err(bad)?;
    let params = params.iter().map(|col| buf::<f64>(py, col)).collect::<PyResult<Vec<_>>>()?;
    let rolls = rolls.iter().map(|col| buf::<f64>(py, col)).collect::<PyResult<Vec<_>>>()?;
    let pc: Vec<&[f64]> = params.iter().map(|v| v.as_slice()).collect();
    let rc: Vec<&[f64]> = rolls.iter().map(|v| v.as_slice()).collect();
    let cols = py.detach(|| combat::resolve_hits(&pc, &rc, &c)).map_err(bad)?;
    Ok(cols
        .iter()
        .map(|col| {
            let bytes: Vec<u8> = col.iter().flat_map(|v| v.to_ne_bytes()).collect();
            pyo3::types::PyBytes::new(py, &bytes)
        })
        .collect())
}
