-- Semantic Core Compression Rules
-- Defines thresholds and patterns for log/state compression

return {
    -- Log compression settings
    log_compression = {
        -- Minimum occurrences to group as pattern
        min_pattern_count = 3,
        
        -- Maximum patterns to keep in summary
        max_patterns = 50,
        
        -- Patterns to always preserve (never compress)
        critical_patterns = {
            "CRITICAL",
            "FATAL",
            "EXCEPTION",
            "PANIC",
            "ASSERTION_FAILED"
        },
        
        -- Patterns to ignore completely
        ignored_patterns = {
            "DEBUG:",
            "[VERBOSE]",
            "Tick completed"
        }
    },
    
    -- State diff settings
    state_diff = {
        -- Fields to always include in diff (even if unchanged)
        always_include = {
            "hp",
            "mana",
            "status"
        },
        
        -- Fields to never include (too verbose)
        exclude = {
            "frame_number",
            "timestamp",
            "internal_id"
        },
        
        -- Array fields: only report length changes
        array_length_only = {
            "particles",
            "effects",
            "enemies_in_view"
        }
    },
    
    -- Event correlation settings
    event_correlation = {
        -- Time window for correlation (ms)
        default_window_ms = 100,
        
        -- Critical pairs (visual + logical)
        critical_pairs = {
            {"visual_blackout", "panic_error"},
            {"freeze_detected", "timeout_exception"},
            {"ssim_drop", "render_exception"},
            {"texture_missing", "asset_load_error"}
        },
        
        -- Warning pairs
        warning_pairs = {
            {"low_fps", "memory_leak_warning"},
            {"high_latency", "network_timeout"},
            {"stutter_detected", "gc_pause"}
        }
    },
    
    -- Token budget settings (for LLM context)
    token_budget = {
        -- Max tokens for log summary
        max_log_tokens = 500,
        
        -- Max tokens for state diff
        max_state_tokens = 200,
        
        -- Max tokens for event correlations
        max_event_tokens = 300,
        
        -- Total budget per analysis frame
        total_budget = 1000
    }
}
