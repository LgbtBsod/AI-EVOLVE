// Simulation Module (L3)
//! Core simulation: grid, entities, tick, collisions, pathfinding

pub mod grid;
pub mod entities;
pub mod tick;
pub mod pathfinding;
pub mod batch;

pub use grid::Grid;
pub use entities::{Entity, Component, Position, Health, AI};
pub use tick::TickSystem;
pub use pathfinding::{AStar, FlowField};
pub use batch::BatchStepper;

use serde::{Serialize, Deserialize};

/// World state snapshot for rendering and ML
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct World {
    pub seed: u64,
    pub map_id: u32,
    pub entities: Vec<Entity>,
    pub grid: Grid,
}

/// Environment for Gym wrapper
pub struct SimulationEnv {
    world: World,
    state: State,
}

struct State {
    step_count: u64,
    done: bool,
}

impl SimulationEnv {
    pub fn new(seed: u64) -> Self {
        // World will be loaded from generator or database
        Self {
            world: World {
                seed,
                map_id: 0,
                entities: Vec::new(),
                grid: Grid::new(32, 32),
            },
            state: State {
                step_count: 0,
                done: false,
            },
        }
    }
    
    pub fn load_world(&mut self, world: World) {
        self.world = world;
    }
    
    /// Step the simulation (releases GIL when called from Python)
    pub fn step(&mut self, actions: Vec<Action>) -> StepResult {
        self.state.step_count += 1;
        
        // Apply actions
        // Tick simulation
        // Check done conditions
        
        StepResult {
            observations: Vec::new(),
            rewards: vec![0.0],
            dones: vec![self.state.done],
            info: Info {
                step: self.state.step_count,
            },
        }
    }
    
    /// Batch step for ML training (releases GIL)
    pub fn step_batch(&mut self, actions: Vec<Vec<Action>>) -> BatchStepResult {
        pyo3::Python::with_gil(|py| {
            py.allow_threads(|| {
                // Parallel batch processing
                self.step_multiple(actions)
            })
        })
    }
    
    fn step_multiple(&mut self, actions: Vec<Vec<Action>>) -> BatchStepResult {
        // Implement parallel batch stepping
        BatchStepResult {
            observations: Vec::new(),
            rewards: Vec::new(),
            dones: Vec::new(),
            infos: Vec::new(),
        }
    }
    
    /// Create snapshot for saving
    pub fn snapshot(&self) -> WorldSnapshot {
        WorldSnapshot {
            world: self.world.clone(),
            state: self.state.clone(),
        }
    }
}

#[derive(Debug, Clone)]
pub struct Action {
    pub entity_id: u32,
    pub action_type: ActionType,
}

#[derive(Debug, Clone)]
pub enum ActionType {
    Move { x: i32, y: i32 },
    Attack { target_id: u32 },
    UseSkill { skill_id: u32, target_x: i32, target_y: i32 },
    UseItem { item_id: u32 },
    Wait,
}

#[derive(Debug)]
pub struct StepResult {
    pub observations: Vec<Observation>,
    pub rewards: Vec<f32>,
    pub dones: Vec<bool>,
    pub info: Info,
}

#[derive(Debug)]
pub struct BatchStepResult {
    pub observations: Vec<Vec<Observation>>,
    pub rewards: Vec<Vec<f32>>,
    pub dones: Vec<Vec<bool>>,
    pub infos: Vec<Info>,
}

#[derive(Debug, Clone)]
pub struct Observation {
    pub visual: Vec<u8>,  // 64x64 grayscale
    pub vector: Vec<f32>, // HP, position, inventory, etc.
}

#[derive(Debug, Clone)]
pub struct Info {
    pub step: u64,
}

#[derive(Clone)]
pub struct WorldSnapshot {
    pub world: World,
    pub state: State,
}
