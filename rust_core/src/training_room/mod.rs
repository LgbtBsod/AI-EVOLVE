"""
Rust Core: Training Room Engine
High-performance simulation for item/skill testing
"""

use pyo3::prelude::*;
use serde::{Deserialize, Serialize};
use std::collections::HashMap;
use uuid::Uuid;

/// Effect Contract Definition
/// Universal structure for all item effects
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct EffectContract {
    pub id: String,              // UUID for unique identification
    pub name: String,            // Display name
    pub effect_type: String,     // "buff", "debuff", "passive", "triggered"
    
    // Trigger conditions (CAS subscription)
    pub trigger_conditions: Vec<TriggerCondition>,
    
    // Effect parameters
    pub stats_modifiers: HashMap<String, f64>,  // stat_name -> value
    pub duration: Option<f64>,   // seconds, None = permanent
    pub cooldown: Option<f64>,   // seconds
    pub max_stacks: Option<i32>,
    
    // Cost configuration
    pub cost: Option<EffectCost>,
    
    // Special flags
    pub is_cost_must_be_below_zero: bool,  // If true, cost can kill (HP → 0)
    pub grants_iframe: bool,
    pub iframe_duration: Option<f64>,
    
    // Scaling configuration
    pub scaling_per_missing_percent: Option<ScalingConfig>,
}

/// Cost Configuration
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct EffectCost {
    pub hp_percent: Option<f64>,      // % of max HP
    pub hp_flat: Option<f64>,         // flat HP cost
    pub mana_percent: Option<f64>,
    pub mana_flat: Option<f64>,
    pub stamina_percent: Option<f64>,
    pub can_kill: bool,               // If false, HP stops at 1
}

/// Scaling Configuration (escalation)
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ScalingConfig {
    pub threshold_percent: f64,       // e.g., 40.0 for <40% HP
    pub step_percent: f64,            // e.g., 10.0 for every 10%
    pub multiplier_per_step: f64,     // e.g., 2.0 for doubling
    pub max_multiplier: Option<f64>,
}

/// Trigger Condition (CAS subscribes to these)
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct TriggerCondition {
    pub condition_type: String,       // "hp_percent_lt", "hp_percent_gt", "has_debuff", etc.
    pub parameter: String,            // e.g., "bleed" for has_debuff
    pub threshold: f64,               // e.g., 40.0 for hp_percent_lt
    pub operator: String,             // "lt", "gt", "eq", "gte", "lte"
}

/// CAS Event Result
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct CasEvent {
    pub effect_id: String,
    pub event_type: String,           // "triggered", "expired", "stacked"
    pub timestamp: f64,
    pub context: HashMap<String, f64>, // current HP, stacks, etc.
}

/// Mannequin/Bot Configuration for Rust simulation
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct SimulationEntity {
    pub id: String,
    pub entity_type: String,          // "mannequin", "immortal_bot", "player"
    
    // Base stats
    pub max_hp: f64,
    pub current_hp: f64,
    pub defense: f64,
    pub attack_damage: f64,
    pub attack_speed: f64,
    pub crit_rate: f64,
    pub crit_damage: f64,
    pub vampirism: f64,
    
    // Active effects
    pub active_effects: Vec<EffectContract>,
    
    // Immortality flag (for testing)
    pub is_immortal: bool,
    
    // AI behavior (for bots)
    pub ai_aggression: f64,           // 0.0 = passive, 1.0 = aggressive
}

/// Simulation Result
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct SimulationResult {
    pub duration_seconds: f64,
    pub total_damage_dealt: f64,
    pub total_damage_taken: f64,
    pub dps: f64,
    pub hps: f64,                     // healing per second
    pub kills: i32,
    pub deaths: i32,
    pub iframe_uptime_percent: f64,
    pub effect_triggers: Vec<CasEvent>,
    pub final_hp_percent: f64,
}

/// Main Training Room Engine
#[pyclass]
pub struct TrainingRoomEngine {
    entities: HashMap<String, SimulationEntity>,
    effects_registry: HashMap<String, EffectContract>,
    cas_events: Vec<CasEvent>,
    simulation_time: f64,
}

#[pymethods]
impl TrainingRoomEngine {
    #[new]
    fn new() -> Self {
        TrainingRoomEngine {
            entities: HashMap::new(),
            effects_registry: HashMap::new(),
            cas_events: Vec::new(),
            simulation_time: 0.0,
        }
    }
    
    /// Register an effect contract (from Lua/JSON)
    fn register_effect(&mut self, effect_json: &str) -> PyResult<String> {
        let effect: EffectContract = serde_json::from_str(effect_json)
            .map_err(|e| PyErr::new::<pyo3::exceptions::PyValueError, _>(format!("Invalid effect JSON: {}", e)))?;
        
        let effect_id = effect.id.clone();
        self.effects_registry.insert(effect_id.clone(), effect);
        Ok(effect_id)
    }
    
    /// Create a mannequin/bot entity
    fn create_entity(&mut self, config_json: &str) -> PyResult<String> {
        let entity: SimulationEntity = serde_json::from_str(config_json)
            .map_err(|e| PyErr::new::<pyo3::exceptions::PyValueError, _>(format!("Invalid entity JSON: {}", e)))?;
        
        let entity_id = entity.id.clone();
        self.entities.insert(entity_id.clone(), entity);
        Ok(entity_id)
    }
    
    /// Run simulation for N seconds
    fn simulate(&mut self, duration: f64, tick_rate: f64) -> PyResult<SimulationResult> {
        let mut result = SimulationResult {
            duration_seconds: duration,
            total_damage_dealt: 0.0,
            total_damage_taken: 0.0,
            dps: 0.0,
            hps: 0.0,
            kills: 0,
            deaths: 0,
            iframe_uptime_percent: 0.0,
            effect_triggers: Vec::new(),
            final_hp_percent: 100.0,
        };
        
        let ticks = (duration / tick_rate) as i32;
        let mut iframe_time = 0.0;
        
        for tick in 0..ticks {
            self.simulation_time = tick as f64 * tick_rate;
            
            // Process each entity
            for (_, entity) in &mut self.entities {
                // Check CAS triggers
                for effect in &entity.active_effects {
                    if self.check_cas_trigger(entity, effect) {
                        let event = CasEvent {
                            effect_id: effect.id.clone(),
                            event_type: "triggered".to_string(),
                            timestamp: self.simulation_time,
                            context: HashMap::from([
                                ("current_hp_percent", entity.current_hp / entity.max_hp * 100.0),
                            ]),
                        };
                        self.cas_events.push(event.clone());
                        result.effect_triggers.push(event);
                    }
                }
                
                // Apply costs (HP drain)
                for effect in &entity.active_effects {
                    if let Some(cost) = &effect.cost {
                        if let Some(hp_percent) = cost.hp_percent {
                            let cost_amount = entity.max_hp * (hp_percent / 100.0);
                            if cost.can_kill || entity.is_immortal {
                                entity.current_hp -= cost_amount;
                                if entity.current_hp <= 0.0 && !entity.is_immortal {
                                    entity.current_hp = 0.0;
                                    result.deaths += 1;
                                }
                            } else {
                                // Cannot kill - stop at 1 HP
                                if entity.current_hp > 1.0 {
                                    entity.current_hp = (entity.current_hp - cost_amount).max(1.0);
                                }
                            }
                        }
                    }
                }
                
                // Track iframe uptime
                for effect in &entity.active_effects {
                    if effect.grants_iframe {
                        iframe_time += tick_rate;
                    }
                }
            }
        }
        
        // Calculate final stats
        if let Some(entity) = self.entities.values().next() {
            result.final_hp_percent = entity.current_hp / entity.max_hp * 100.0;
            result.dps = result.total_damage_dealt / duration;
            result.hps = result.total_damage_taken / duration; // Simplified
            result.iframe_uptime_percent = (iframe_time / duration) * 100.0;
        }
        
        Ok(result)
    }
    
    /// Check if CAS trigger conditions are met
    fn check_cas_trigger(&self, entity: &SimulationEntity, effect: &EffectContract) -> bool {
        for condition in &effect.trigger_conditions {
            match condition.condition_type.as_str() {
                "hp_percent_lt" => {
                    let current_percent = entity.current_hp / entity.max_hp * 100.0;
                    if current_percent >= condition.threshold {
                        return false;
                    }
                },
                "hp_percent_gt" => {
                    let current_percent = entity.current_hp / entity.max_hp * 100.0;
                    if current_percent <= condition.threshold {
                        return false;
                    }
                },
                "has_debuff" => {
                    // Check if entity has specific debuff (simplified)
                    // In real implementation, check debuff list
                    return false; // Placeholder
                },
                _ => return false,
            }
        }
        true
    }
    
    /// Get all registered effects
    fn get_effects(&self) -> PyResult<String> {
        serde_json::to_string(&self.effects_registry)
            .map_err(|e| PyErr::new::<pyo3::exceptions::PyValueError, _>(format!("Serialization error: {}", e)))
    }
    
    /// Export simulation result to JSON
    fn export_result(&self, result: &SimulationResult) -> PyResult<String> {
        serde_json::to_string_pretty(result)
            .map_err(|e| PyErr::new::<pyo3::exceptions::PyValueError, _>(format!("Serialization error: {}", e)))
    }
}

/// Python module definition
#[pymodule]
fn training_room(_py: Python, m: &PyModule) -> PyResult<()> {
    m.add_class::<TrainingRoomEngine>()?;
    m.add_class::<EffectContract>()?;
    m.add_class::<SimulationResult>()?;
    Ok(())
}
