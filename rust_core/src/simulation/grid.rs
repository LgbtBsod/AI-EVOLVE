// Grid module - L3 Simulation core
//! 2D grid with tiles for pathfinding and collision

use serde::{Serialize, Deserialize};

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Grid {
    pub width: u32,
    pub height: u32,
    pub tiles: Vec<Tile>,
}

impl Grid {
    pub fn new(width: u32, height: u32) -> Self {
        let size = (width * height) as usize;
        Self {
            width,
            height,
            tiles: vec![Tile::default(); size],
        }
    }
    
    pub fn get_tile(&self, x: i32, y: i32) -> Option<&Tile> {
        if x < 0 || y < 0 || x >= self.width as i32 || y >= self.height as i32 {
            return None;
        }
        let idx = (y * self.width as i32 + x) as usize;
        self.tiles.get(idx)
    }
    
    pub fn get_tile_mut(&mut self, x: i32, y: i32) -> Option<&mut Tile> {
        if x < 0 || y < 0 || x >= self.width as i32 || y >= self.height as i32 {
            return None;
        }
        let idx = (y * self.width as i32 + x) as usize;
        self.tiles.get_mut(idx)
    }
}

#[derive(Debug, Clone, Default, Serialize, Deserialize)]
pub struct Tile {
    pub walkable: bool,
    pub visible: bool,
    pub entity_ids: Vec<u32>,
}
