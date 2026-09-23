// FFI Module (Python ↔ Rust interface)
//! PyO3 bindings for Python integration

use pyo3::prelude::*;
use crate::simulation::SimulationEnv;
use crate::generator::WorldGenerator;

/// Python module for rust_core
#[pymodule]
fn rust_core(_py: Python, m: &PyModule) -> PyResult<()> {
    m.add_class::<PySimulationEnv>()?;
    m.add_class::<PyWorldGenerator>()?;
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
    
    fn step(&mut self, actions: Vec<PyObject>) -> PyResult<(Vec<PyObject>, Vec<f32>, Vec<bool>, PyObject)> {
        // Convert Python actions to Rust actions
        // Call inner.step()
        // Convert results back to Python
        Python::with_gil(|py| {
            Ok((vec![], vec![0.0], vec![false], py.None()))
        })
    }
    
    fn step_batch(&mut self, actions: Vec<Vec<PyObject>>) -> PyResult<(Vec<Vec<PyObject>>, Vec<Vec<f32>>, Vec<Vec<bool>>, Vec<PyObject>)> {
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
            Ok(_world) => {
                // Convert World to Python object
                Python::with_gil(|py| Ok(py.None()))
            }
            Err(e) => Err(pyo3::exceptions::PyRuntimeError::new_err(e)),
        }
    }
}
