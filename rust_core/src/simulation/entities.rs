// Entities module - L3 Simulation core
//! ECS-style components and entities

use serde::{Serialize, Deserialize};

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Entity {
    pub id: u32,
    pub kind: EntityKind,
    pub position: Position,
    pub health: Option<Health>,
    pub ai: Option<AI>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub enum EntityKind {
    Player,
    Enemy,
    Item,
    Trap,
    Obstacle,
}

#[derive(Debug, Clone, Default, Serialize, Deserialize)]
pub struct Position {
    pub x: i32,
    pub y: i32,
}

#[derive(Debug, Clone, Default, Serialize, Deserialize)]
pub struct Health {
    pub current: f32,
    pub max: f32,
}

#[derive(Debug, Clone, Default, Serialize, Deserialize)]
pub struct AI {
    pub policy_hash: String,
    pub state: AIState,
}

#[derive(Debug, Clone, Default, Serialize, Deserialize)]
pub enum AIState {
    #[default]
    Idle,
    Patrolling,
    Chasing,
    Attacking,
    Fleeing,
}

pub trait Component {}
impl Component for Position {}
impl Component for Health {}
impl Component for AI {}
