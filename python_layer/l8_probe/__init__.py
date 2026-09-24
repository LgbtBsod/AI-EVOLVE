"""L8 - Dev Probe Analytics Layer

High-performance visual analytics for game testing and debugging.
Orchestrates Rust analytics engine with Lua configuration.

Components:
- analyzer: Rust-backed frame analysis (perceptual hash, SSIM, motion)
- config_loader: Lua configuration management
- cluster: Frame clustering for deduplication
- reporter: Summary generation with issue detection
"""

from python_layer.l8_probe.analyzer import ProbeAnalytics
from python_layer.l8_probe.config_loader import LuaConfigLoader
from python_layer.l8_probe.cluster import FrameClusterer
from python_layer.l8_probe.reporter import IssueDetector, SummaryGenerator

__all__ = [
    'ProbeAnalytics',
    'LuaConfigLoader',
    'FrameClusterer',
    'IssueDetector',
    'SummaryGenerator',
]
