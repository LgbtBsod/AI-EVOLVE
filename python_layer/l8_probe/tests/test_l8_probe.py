"""Tests for L8 Probe Analytics Layer"""

import pytest
import sys
from pathlib import Path
from datetime import datetime

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from python_layer.l8_probe.analyzer import ProbeAnalytics, FrameMetrics, AnalysisSession
from python_layer.l8_probe.cluster import FrameClusterer
from python_layer.l8_probe.reporter import IssueDetector, SummaryGenerator, DetectedIssue
from python_layer.l8_probe.config_loader import LuaConfigLoader


class TestFrameMetrics:
    def test_metrics_creation(self):
        metrics = FrameMetrics(frame_id=1, timestamp=100.0)
        assert metrics.frame_id == 1
        assert metrics.is_blank is False
    
    def test_metrics_to_dict(self):
        metrics = FrameMetrics(frame_id=5, timestamp=250.5, perceptual_hash="abc123")
        d = metrics.to_dict()
        assert d['frame_id'] == 5


class TestFrameClusterer:
    def test_hamming_distance(self):
        h1 = "0000000000000000"
        h2 = "ffffffffffffffff"
        assert FrameClusterer.hamming_distance(h1, h2) == 64
    
    def test_clustering(self):
        clusterer = FrameClusterer()
        clusterer.add_frame(1, 100.0, "hash1")
        clusterer.add_frame(2, 101.0, "hash1")
        assert len(clusterer.get_clusters()) == 1


class TestIssueDetector:
    def test_detect_blackout(self):
        detector = IssueDetector()
        detector.analyze_frame(1, 100.0, {'is_blank': True}, {'entities_alive': 3})
        issues = detector.get_issues()
        assert len(issues) >= 1


class TestSummaryGenerator:
    def test_generate(self, tmp_path):
        gen = SummaryGenerator(output_dir=tmp_path)
        path = gen.generate(
            session_summary={'total_frames': 10},
            clustering_summary={'total_clusters': 2},
            issues=[],
            representative_frames=[(1, 1.0)],
        )
        assert path.exists()
        assert "**Status:** OK" in path.read_text()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
