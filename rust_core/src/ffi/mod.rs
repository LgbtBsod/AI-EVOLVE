// FFI Module (Python ↔ Rust interface)
//! PyO3 bindings for Python integration

use pyo3::prelude::*;
use crate::simulation::SimulationEnv;
use crate::generator::WorldGenerator;
use crate::probe::{ProbeConfig, FrameAnalysis, analyze_frame, compute_ssim};
use crate::semantic_core::{LogCompressor as RustLogCompressor, StateDiffCalculator as RustStateDiffCalculator, EventCorrelator as RustEventCorrelator};
use image::{DynamicImage, ImageFormat};
use std::io::Cursor;

/// Python module for rust_core
#[pymodule]
fn rust_core(_py: Python, m: &PyModule) -> PyResult<()> {
    m.add_class::<PySimulationEnv>()?;
    m.add_class::<PyWorldGenerator>()?;
    m.add_class::<PyProbeAnalyzer>()?;
    m.add_class::<PyLogCompressor>()?;
    m.add_class::<PyStateDiffCalculator>()?;
    m.add_class::<PyEventCorrelator>()?;
    // Aliases for cleaner Python API
    m.add("WorldGenerator", m.getattr("PyWorldGenerator")?)?;
    m.add("SimulationEnv", m.getattr("PySimulationEnv")?)?;
    m.add("ProbeAnalyzer", m.getattr("PyProbeAnalyzer")?)?;
    m.add("LogCompressor", m.getattr("PyLogCompressor")?)?;
    m.add("StateDiffCalculator", m.getattr("PyStateDiffCalculator")?)?;
    m.add("EventCorrelator", m.getattr("PyEventCorrelator")?)?;
    m.add("VERSION", env!("CARGO_PKG_VERSION"))?;
    Ok(())
}

#[pyclass]
struct PySimulationEnv {
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
    
    fn step(&mut self, _actions: Vec<PyObject>) -> PyResult<(Vec<PyObject>, Vec<f32>, Vec<bool>, PyObject)> {
        // Convert Python actions to Rust actions
        // Call inner.step()
        // Convert results back to Python
        Python::with_gil(|py| {
            Ok((vec![], vec![0.0], vec![false], py.None()))
        })
    }
    
    fn step_batch(&mut self, _actions: Vec<Vec<PyObject>>) -> PyResult<(Vec<Vec<PyObject>>, Vec<Vec<f32>>, Vec<Vec<bool>>, Vec<PyObject>)> {
        Python::with_gil(|py| {
            Ok((vec![], vec![], vec![], vec![py.None()]))
        })
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
    
    fn generate(&self, bricks_config: &str) -> PyResult<PyObject> {
        match self.inner.generate(bricks_config) {
            Ok(world) => {
                // Convert World to Python dict
                Python::with_gil(|py| {
                    let dict = pyo3::types::PyDict::new(py);
                    dict.set_item("seed", world.seed)?;
                    dict.set_item("map_id", world.map_id)?;
                    dict.set_item("entity_count", world.entities.len())?;
                    dict.set_item("grid_width", world.grid.width)?;
                    dict.set_item("grid_height", world.grid.height)?;
                    Ok(dict.into())
                })
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
    fn new(config_dict: Option<&pyo3::types::PyDict>) -> PyResult<Self> {
        let mut config = ProbeConfig::default();
        
        if let Some(dict) = config_dict {
            if let Ok(val) = dict.get_item("blank_frame_stddev_threshold") {
                if let Some(v) = val { config.blank_frame_stddev_threshold = v.extract()?; }
            }
            if let Ok(val) = dict.get_item("visual_hash_bits") {
                if let Some(v) = val { config.visual_hash_bits = v.extract()?; }
            }
            if let Ok(val) = dict.get_item("hamming_threshold") {
                if let Some(v) = val { config.hamming_threshold = v.extract()?; }
            }
            if let Ok(val) = dict.get_item("motion_detection_threshold") {
                if let Some(v) = val { config.motion_detection_threshold = v.extract()?; }
            }
            if let Ok(val) = dict.get_item("brightness_anomaly_threshold") {
                if let Some(v) = val { config.brightness_anomaly_threshold = v.extract()?; }
            }
            if let Ok(val) = dict.get_item("ssim_threshold") {
                if let Some(v) = val { config.ssim_threshold = v.extract()?; }
            }
        }
        
        Ok(Self {
            config,
            prev_frame: None,
        })
    }

    /// Analyze a single frame from PNG bytes
    /// Returns dict with perceptual_hash, brightness, motion, is_blank, edge_density, complexity_score
    fn analyze_frame(&mut self, png_bytes: &[u8]) -> PyResult<PyObject> {
        let image = image::load_from_memory(png_bytes)
            .map_err(|e| pyo3::exceptions::PyValueError::new_err(format!("Invalid image: {}", e)))?;
        
        let prev_ref = self.prev_frame.as_ref();
        let analysis = analyze_frame(&image, prev_ref, &self.config);
        
        // Store current frame for next motion comparison
        self.prev_frame = Some(image);
        
        Python::with_gil(|py| {
            let dict = pyo3::types::PyDict::new(py);
            
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
                let bright_dict = pyo3::types::PyDict::new(py);
                bright_dict.set_item("mean", bright.mean)?;
                bright_dict.set_item("stddev", bright.stddev)?;
                bright_dict.set_item("min", bright.min)?;
                bright_dict.set_item("max", bright.max)?;
                dict.set_item("brightness", bright_dict)?;
            }
            
            // Motion stats
            if let Some(motion) = &analysis.motion {
                let motion_dict = pyo3::types::PyDict::new(py);
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
            
            Ok(dict.into())
        })
    }

    /// Compare two frames and return SSIM score
    fn compare_frames(&self, frame1_bytes: &[u8], frame2_bytes: &[u8]) -> PyResult<PyObject> {
        let img1 = image::load_from_memory(frame1_bytes)
            .map_err(|e| pyo3::exceptions::PyValueError::new_err(format!("Invalid image 1: {}", e)))?;
        let img2 = image::load_from_memory(frame2_bytes)
            .map_err(|e| pyo3::exceptions::PyValueError::new_err(format!("Invalid image 2: {}", e)))?;
        
        let ssim_result = compute_ssim(&img1, &img2)
            .ok_or_else(|| pyo3::exceptions::PyValueError::new_err("Frames must have same dimensions"))?;
        
        Python::with_gil(|py| {
            let dict = pyo3::types::PyDict::new(py);
            dict.set_item("ssim_score", ssim_result.score)?;
            dict.set_item("mean_score", ssim_result.mean_score)?;
            dict.set_item("is_similar", ssim_result.mean_score > self.config.ssim_threshold)?;
            Ok(dict.into())
        })
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
            for i in 0..4 {
                let start = i * 16;
                let end = start + 16;
                bits[i] = u64::from_str_radix(&hex[start..end], 16)
                    .map_err(|e| format!("Invalid hex at position {}: {}", i, e))?;
            }
            Ok(bits)
        };
        
        let bits1 = parse_hex(hash1).map_err(|e| pyo3::exceptions::PyValueError::new_err(e))?;
        let bits2 = parse_hex(hash2).map_err(|e| pyo3::exceptions::PyValueError::new_err(e))?;
        
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
    fn calculate_diff(py: Python, old_state: &pyo3::types::PyDict, new_state: &pyo3::types::PyDict) -> PyResult<Py<pyo3::types::PyDict>> {
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
