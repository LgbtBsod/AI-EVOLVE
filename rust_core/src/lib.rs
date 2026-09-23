//! Rust Core Layer for AI Evolve
//! 
//! # Layers
//! - L3: Simulation (grid, entities, tick, pathfinding)
//! - L2: World Generation (procedural, deterministic, seeded)
//! - L1: Storage (SQLite, snapshots, saves)
//! - L8: Probe Analytics (visual analysis, frame hashing, motion detection)
//! - L9: Semantic Core (log compression, state diffs, event correlation)
//! 
//! # Principles
//! - Deterministic: Same seed = same world on all OS
//! - GIL-free: Batch operations release GIL
//! - ECS: Component arrays, not OOP objects
//! - No Python knowledge: Doesn't know about PyTorch, Panda3D

pub mod simulation;
pub mod generator;
pub mod storage;
pub mod ffi;
pub mod probe;
pub mod semantic_core;

pub use simulation::{SimulationEnv, World, Entity};
pub use generator::WorldGenerator;
pub use storage::Database;
pub use probe::{ProbeConfig, FrameAnalysis, PerceptualHash};
pub use semantic_core::{LogCompressor, StateDiffCalculator, EventCorrelator};

/// Library version
pub const VERSION: &str = env!("CARGO_PKG_VERSION");
