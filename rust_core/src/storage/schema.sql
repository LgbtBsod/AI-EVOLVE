-- Database schema for saves
CREATE TABLE IF NOT EXISTS meta (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    seed INTEGER NOT NULL,
    generator_version TEXT NOT NULL,
    bricks_hash TEXT,
    created_at TEXT NOT NULL,
    playtime INTEGER DEFAULT 0,
    current_map INTEGER DEFAULT 1
);

CREATE TABLE IF NOT EXISTS entities (
    id INTEGER PRIMARY KEY,
    kind TEXT NOT NULL,
    rarity TEXT,
    tier INTEGER,
    tags_json TEXT,
    stats_json TEXT,
    seed_offset INTEGER
);

CREATE TABLE IF NOT EXISTS world_state (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    entity_id INTEGER,
    map_id INTEGER,
    state TEXT,
    position TEXT,
    snapshot BLOB,
    timestamp TEXT
);

CREATE TABLE IF NOT EXISTS maps (
    id INTEGER PRIMARY KEY,
    biome TEXT,
    difficulty INTEGER,
    layout_seed INTEGER,
    cleared INTEGER DEFAULT 0,
    visited INTEGER DEFAULT 0
);

CREATE TABLE IF NOT EXISTS agent_progress (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id TEXT,
    map_id INTEGER,
    reward REAL,
    deaths INTEGER,
    time_seconds REAL,
    learned_skills_json TEXT,
    policy_hash TEXT
);

CREATE TABLE IF NOT EXISTS enemies_progress (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id TEXT,
    enemy_type TEXT,
    policy_hash TEXT,
    win_rate REAL
);
