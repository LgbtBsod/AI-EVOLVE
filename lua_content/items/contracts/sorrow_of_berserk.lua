-- Sorrow of Berserk - Complete Effect Contract
-- Lua Configuration for Rust Training Room Engine

local UUID = require("uuid")  -- Assuming uuid library available

-- Generate unique ID for this item instance
local ITEM_ID = UUID.generate()

return {
    id = ITEM_ID,
    name = "Sorrow of Berserk",
    item_type = "necklace",
    rarity = "legendary",
    
    -- Base Stats
    base_stats = {
        max_hp_percent = 2000,      -- +2000% HP
        defense_percent = -80,      -- -80% DEF
        vampirism_percent = 20,     -- +20% Vamp
        attack_speed_percent = 50,  -- +50% AS
    },
    
    -- Effect Contracts (managed by Effect Manager)
    effects = {
        {
            id = UUID.generate() .. "_lost_my_self",
            name = "Lost My Self",
            effect_type = "triggered_buff",
            
            -- CAS Trigger Conditions
            trigger_conditions = {
                {
                    condition_type = "hp_percent_lt",
                    parameter = "",
                    threshold = 40.0,
                    operator = "lt"
                }
            },
            
            -- Stat Modifiers (active when triggered)
            stats_modifiers = {
                strength_percent = 20,
                stamina_percent = 10,
                crit_rate_percent = 5,
                crit_damage_percent = 10,
                attack_speed_percent = 5,
            },
            
            duration = nil,  -- Permanent while condition met
            cooldown = nil,
            max_stacks = nil,
            
            -- No cost for this buff
            cost = nil,
            
            -- Special flags
            is_cost_must_be_below_zero = false,
            grants_iframe = false,
            iframe_duration = nil,
            
            -- Scaling: doubles every 10% HP missing below 40%
            scaling_per_missing_percent = {
                threshold_percent = 40.0,
                step_percent = 10.0,
                multiplier_per_step = 2.0,
                max_multiplier = 512.0,  -- Cap at 512x (9 steps: 40%→1%)
            },
        },
        
        {
            id = UUID.generate() .. "_blood_cost",
            name = "Blood Cost",
            effect_type = "passive_attack_modifier",
            
            -- Always active (no trigger conditions)
            trigger_conditions = {},
            
            -- No direct stat modifiers
            stats_modifiers = {},
            
            duration = nil,
            cooldown = nil,
            max_stacks = nil,
            
            -- Cost Configuration
            cost = {
                hp_percent = 0.5,     -- Base: 0.5% max HP per attack
                hp_flat = nil,
                mana_percent = nil,
                mana_flat = nil,
                stamina_percent = nil,
                can_kill = false,     -- FALSE: Cannot kill, stops at 1 HP
            },
            
            -- Special flags
            is_cost_must_be_below_zero = false,
            grants_iframe = false,
            iframe_duration = nil,
            
            -- Escalation: +0.5% cost / +1.5% dmg per 10% missing HP
            scaling_per_missing_percent = {
                threshold_percent = 40.0,
                step_percent = 10.0,
                multiplier_per_step = 1.5,  -- Damage scales 1.5x per step
                max_multiplier = 4.0,       -- Max 4x (2.0% cost → 6.0% dmg)
            },
            
            -- Custom damage calculation callback (handled in Rust/Python)
            damage_override = {
                type = "max_hp_percent",
                base_value = 1.5,     -- 1.5% max HP damage
                scales_with_missing = true,
            },
        },
        
        {
            id = UUID.generate() .. "_safety_net",
            name = "Safety Net (Last Will)",
            effect_type = "reactive_shield",
            
            -- Trigger: when blood_cost > current_hp
            trigger_conditions = {
                {
                    condition_type = "cost_exceeds_hp",
                    parameter = "_blood_cost",
                    threshold = 0.0,
                    operator = "gt"
                }
            },
            
            stats_modifiers = {},
            
            duration = 5.0,   -- 5 seconds iframe
            cooldown = 30.0,  -- 30 seconds before can trigger again
            max_stacks = 1,
            
            cost = nil,
            
            -- Special flags
            is_cost_must_be_below_zero = false,
            grants_iframe = true,
            iframe_duration = 5.0,
            
            -- Sets HP to 1 on trigger
            on_trigger = {
                set_hp_to = 1,
                multiply_buffs_by_missing = 2.0,  -- Double buffs per missing 10%
            },
            
            -- Kill refresh extension
            on_kill_during_iframe = {
                extend_duration = 5.0,
            },
        },
        
        {
            id = UUID.generate() .. "_low_hp_sustain",
            name = "Low HP Sustain",
            effect_type = "passive_buff",
            
            -- Trigger: HP < 40%
            trigger_conditions = {
                {
                    condition_type = "hp_percent_lt",
                    parameter = "",
                    threshold = 40.0,
                    operator = "lt"
                }
            },
            
            stats_modifiers = {
                hp_regen_flat = 20,
                vampirism_percent = 5,
                crit_rate_percent = 5,
                crit_damage_percent = 10,
                attack_speed_percent = 10,
            },
            
            duration = nil,
            cooldown = nil,
            max_stacks = nil,
            
            cost = nil,
            is_cost_must_be_below_zero = false,
            grants_iframe = false,
            iframe_duration = nil,
            scaling_per_missing_percent = nil,
        },
    },
    
    -- Metadata for UI/Builder
    metadata = {
        description = "A cursed necklace that trades life for power. Below 40% HP, gain massive bonuses but consume life with each attack. When life runs out, Last Will protects you briefly.",
        flavor_text = "\"In sorrow, we find our true strength... or our end.\"",
        icon_path = "items/legendary/sorrow_of_berserk.png",
        required_level = 1,
        tradeable = false,
        droppable = false,
    },
}
