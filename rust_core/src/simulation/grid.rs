// Grid module stub - to be implemented
pub struct Grid {
    pub width: u32,
    pub height: u32,
}

impl Grid {
    pub fn new(width: u32, height: u32) -> Self {
        Self { width, height }
    }
}

#[derive(Clone, Default)]
pub struct Tile;
