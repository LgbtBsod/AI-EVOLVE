// Storage Module (L1)
//! SQLite database for saves and snapshots

use rusqlite::{Connection, Result};
use std::path::Path;

pub struct Database {
    conn: Connection,
}

impl Database {
    pub fn create(path: &str) -> Result<Self> {
        let conn = Connection::open(path)?;
        
        // Create schema
        conn.execute_batch(include_str!("schema.sql"))?;
        
        Ok(Self { conn })
    }
    
    pub fn save_meta(&self, seed: u64, version: &str) -> Result<()> {
        self.conn.execute(
            "INSERT INTO meta (seed, generator_version, created_at) VALUES (?1, ?2, datetime('now'))",
            [seed, version],
        )?;
        Ok(())
    }
    
    pub fn save_snapshot(&self, snapshot: &[u8]) -> Result<()> {
        self.conn.execute(
            "INSERT INTO world_state (snapshot, timestamp) VALUES (?1, datetime('now'))",
            [snapshot],
        )?;
        Ok(())
    }
}
