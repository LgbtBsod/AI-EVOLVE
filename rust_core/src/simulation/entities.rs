// Entities module stub - to be implemented
use serde::{Serialize, Deserialize};

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Entity {
    pub id: u32,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Position {
    pub x: i32,
    pub y: i32,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Health {
    pub current: f32,
    pub max: f32,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct AI;

pub trait Component {}
