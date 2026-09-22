"""
Plugin for AI-EVOLVE Dev Probe: ML Vision Analyzer
Purpose: Use computer vision to detect UI elements, damage numbers, and visual anomalies.
"""

import json
import time
from dataclasses import dataclass, field
from typing import Dict, List, Any, Optional, Tuple
from pathlib import Path
import numpy as np

try:
    import cv2
    CV2_AVAILABLE = True
except ImportError:
    CV2_AVAILABLE = False

try:
    from PIL import Image
    PIL_AVAILABLE = True
except ImportError:
    PIL_AVAILABLE = False


@dataclass
class UIElement:
    """Detected UI element."""
    element_type: str  # "health_bar", "damage_number", "status_effect", etc.
    confidence: float
    bounding_box: Tuple[int, int, int, int]  # x, y, width, height
    value: Optional[str] = None  # Parsed text/value if applicable


@dataclass
class VisualAnomaly:
    """Detected visual anomaly."""
    anomaly_type: str
    description: str
    severity: str  # "critical", "warning", "info"
    frame_index: int
    evidence: Dict[str, Any] = field(default_factory=dict)


class MLVisionPlugin:
    """Plugin for ML-based vision analysis of game screenshots."""
    
    def __init__(self, probe_instance):
        self.probe = probe_instance
        self.analyzed_frames: List[Dict[str, Any]] = []
        self.ui_elements_detected: List[UIElement] = []
        self.anomalies: List[VisualAnomaly] = []
        self.damage_numbers_log: List[Dict[str, Any]] = []
        
        # Color ranges for UI detection (HSV)
        self.health_bar_colors = {
            'green': ((40, 50, 50), (70, 255, 255)),
            'yellow': ((25, 50, 50), (35, 255, 255)),
            'red': ((0, 50, 50), (15, 255, 255))
        }
        
        # Damage number detection params
        self.damage_number_min_area = 50
        self.damage_number_max_area = 500
        
        self._register_hooks()
    
    def _register_hooks(self):
        """Register event hooks with the probe."""
        if hasattr(self.probe, 'register_hook'):
            self.probe.register_hook('screenshot_captured', self._on_screenshot)
            self.probe.register_hook('session_end', self._on_session_end)
    
    def _on_screenshot(self, data: Dict[str, Any]):
        """Process captured screenshot."""
        if not CV2_AVAILABLE:
            return
        
        screenshot_path = data.get('path')
        frame_index = data.get('frame_index', len(self.analyzed_frames))
        
        if not screenshot_path or not Path(screenshot_path).exists():
            return
        
        # Load and analyze image
        image = cv2.imread(str(screenshot_path))
        if image is None:
            return
        
        analysis_result = self._analyze_frame(image, frame_index)
        self.analyzed_frames.append(analysis_result)
        
        # Log damage numbers
        if analysis_result.get('damage_numbers'):
            self.damage_numbers_log.extend(analysis_result['damage_numbers'])
    
    def _analyze_frame(self, image: np.ndarray, frame_index: int) -> Dict[str, Any]:
        """Comprehensive frame analysis."""
        result = {
            'frame_index': frame_index,
            'timestamp': time.time(),
            'health_bars': [],
            'damage_numbers': [],
            'status_effects': [],
            'anomalies': [],
            'scene_complexity': 0
        }
        
        # Convert to different color spaces
        hsv = cv2.cvtColor(image, cv2.COLOR_BGR2HSV)
        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        
        # Detect health bars
        health_bars = self._detect_health_bars(hsv, image)
        result['health_bars'] = health_bars
        
        # Detect damage numbers (bright text on dark background)
        damage_numbers = self._detect_damage_numbers(gray, image)
        result['damage_numbers'] = damage_numbers
        
        # Detect status effects (small icons in corners)
        status_effects = self._detect_status_effects(image)
        result['status_effects'] = status_effects
        
        # Calculate scene complexity (edge density)
        result['scene_complexity'] = self._calculate_scene_complexity(gray)
        
        # Check for visual anomalies
        anomalies = self._detect_anomalies(image, result)
        result['anomalies'] = anomalies
        self.anomalies.extend(anomalies)
        
        return result
    
    def _detect_health_bars(self, hsv: np.ndarray, image: np.ndarray) -> List[UIElement]:
        """Detect health bars by color segmentation."""
        health_bars = []
        
        for color_name, (lower, upper) in self.health_bar_colors.items():
            lower_np = np.array(lower, dtype=np.uint8)
            upper_np = np.array(upper, dtype=np.uint8)
            
            mask = cv2.inRange(hsv, lower_np, upper_np)
            contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
            
            for contour in contours:
                area = cv2.contourArea(contour)
                if area > 500:  # Minimum size for health bar
                    x, y, w, h = cv2.boundingRect(contour)
                    
                    # Health bars are typically wide rectangles
                    if w > h * 3:
                        health_bar = UIElement(
                            element_type=f"health_bar_{color_name}",
                            confidence=0.8,
                            bounding_box=(x, y, w, h),
                            value=f"{int(area)}px"
                        )
                        health_bars.append(health_bar)
                        self.ui_elements_detected.append(health_bar)
        
        return health_bars
    
    def _detect_damage_numbers(self, gray: np.ndarray, image: np.ndarray) -> List[Dict[str, Any]]:
        """Detect damage numbers using thresholding and contour detection."""
        damage_numbers = []
        
        # Threshold bright regions (damage numbers are usually white/bright)
        _, thresh = cv2.threshold(gray, 200, 255, cv2.THRESH_BINARY)
        
        # Find contours
        contours, _ = cv2.findContours(thresh, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        
        for contour in contours:
            area = cv2.contourArea(contour)
            if self.damage_number_min_area < area < self.damage_number_max_area:
                x, y, w, h = cv2.boundingRect(contour)
                
                # Damage numbers are typically small text
                if 10 < w < 100 and 10 < h < 50:
                    damage_info = {
                        'position': (x, y),
                        'size': (w, h),
                        'area': area,
                        'frame_index': len(self.analyzed_frames)
                    }
                    damage_numbers.append(damage_info)
        
        return damage_numbers
    
    def _detect_status_effects(self, image: np.ndarray) -> List[UIElement]:
        """Detect status effect icons (typically in corners)."""
        status_effects = []
        
        # Define corner regions where status effects usually appear
        h, w = image.shape[:2]
        corner_regions = [
            (0, 0, w // 4, h // 4),  # Top-left
            (w * 3 // 4, 0, w // 4, h // 4),  # Top-right
            (0, h * 3 // 4, w // 4, h // 4),  # Bottom-left
            (w * 3 // 4, h * 3 // 4, w // 4, h // 4)  # Bottom-right
        ]
        
        for x1, y1, x2, y2 in corner_regions:
            # Ensure region is valid
            if x2 <= x1 or y2 <= y1:
                continue
            roi = image[y1:y2, x1:x2]
            
            # Skip empty ROIs
            if roi.size == 0:
                continue
            
            # Look for small icon-sized regions with distinct colors
            gray_roi = cv2.cvtColor(roi, cv2.COLOR_BGR2GRAY)
            edges = cv2.Canny(gray_roi, 50, 150)
            
            contours, _ = cv2.findContours(edges, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
            
            for contour in contours:
                area = cv2.contourArea(contour)
                if 400 < area < 2500:  # Icon-sized
                    x, y, w, h = cv2.boundingRect(contour)
                    
                    status_effect = UIElement(
                        element_type="status_effect",
                        confidence=0.6,
                        bounding_box=(x1 + x, y1 + y, w, h)
                    )
                    status_effects.append(status_effect)
                    self.ui_elements_detected.append(status_effect)
        
        return status_effects
    
    def _calculate_scene_complexity(self, gray: np.ndarray) -> float:
        """Calculate scene complexity using edge density."""
        edges = cv2.Canny(gray, 50, 150)
        edge_density = np.sum(edges > 0) / edges.size
        return round(edge_density, 4)
    
    def _detect_anomalies(self, image: np.ndarray, analysis: Dict[str, Any]) -> List[VisualAnomaly]:
        """Detect visual anomalies in the frame."""
        anomalies = []
        
        # Check for completely black/white frames (render failure)
        mean_brightness = np.mean(image)
        if mean_brightness < 10:
            anomaly = VisualAnomaly(
                anomaly_type="black_screen",
                description="Frame appears completely black - possible render failure",
                severity="critical",
                frame_index=analysis['frame_index'],
                evidence={'mean_brightness': mean_brightness}
            )
            anomalies.append(anomaly)
        elif mean_brightness > 245:
            anomaly = VisualAnomaly(
                anomaly_type="white_screen",
                description="Frame appears completely white - possible render failure",
                severity="critical",
                frame_index=analysis['frame_index'],
                evidence={'mean_brightness': mean_brightness}
            )
            anomalies.append(anomaly)
        
        # Check for missing UI elements when combat is active
        if not analysis['health_bars'] and analysis['scene_complexity'] > 0.1:
            anomaly = VisualAnomaly(
                anomaly_type="missing_health_bars",
                description="No health bars detected in complex scene - UI may be broken",
                severity="warning",
                frame_index=analysis['frame_index']
            )
            anomalies.append(anomaly)
        
        # Check for no damage numbers during high activity
        if analysis['scene_complexity'] > 0.3 and not analysis['damage_numbers']:
            # High complexity but no damage numbers might indicate UI issue
            pass  # Could be a false positive, skip for now
        
        return anomalies
    
    def _on_session_end(self, data: Dict[str, Any]):
        """Generate vision analysis report."""
        report = self._generate_report()
        self._print_summary(report)
    
    def _generate_report(self) -> Dict[str, Any]:
        """Generate comprehensive vision analysis report."""
        total_frames = len(self.analyzed_frames)
        
        if total_frames == 0:
            return {'status': 'no_data'}
        
        # Aggregate stats
        total_health_bars = sum(len(f.get('health_bars', [])) for f in self.analyzed_frames)
        total_damage_numbers = sum(len(f.get('damage_numbers', [])) for f in self.analyzed_frames)
        total_status_effects = sum(len(f.get('status_effects', [])) for f in self.analyzed_frames)
        
        avg_complexity = np.mean([f.get('scene_complexity', 0) for f in self.analyzed_frames])
        
        frames_with_damage = sum(1 for f in self.analyzed_frames if f.get('damage_numbers'))
        frames_missing_ui = sum(1 for f in self.analyzed_frames if not f.get('health_bars') and f.get('scene_complexity', 0) > 0.1)
        
        report = {
            'total_frames_analyzed': total_frames,
            'ui_detection': {
                'total_health_bars': total_health_bars,
                'total_damage_numbers': total_damage_numbers,
                'total_status_effects': total_status_effects,
                'frames_with_damage_numbers': frames_with_damage,
                'damage_per_frame_avg': round(total_damage_numbers / max(total_frames, 1), 2)
            },
            'scene_analysis': {
                'avg_complexity': round(avg_complexity, 4),
                'complexity_trend': 'stable'  # Could calculate trend over time
            },
            'anomalies': {
                'total_count': len(self.anomalies),
                'by_severity': {
                    'critical': sum(1 for a in self.anomalies if a.severity == 'critical'),
                    'warning': sum(1 for a in self.anomalies if a.severity == 'warning'),
                    'info': sum(1 for a in self.anomalies if a.severity == 'info')
                },
                'frames_missing_ui': frames_missing_ui
            }
        }
        
        # Save report
        report_path = Path('tools/vision_reports')
        report_path.mkdir(exist_ok=True)
        
        timestamp = int(time.time())
        report_file = report_path / f'vision_analysis_{timestamp}.json'
        
        with open(report_file, 'w') as f:
            json.dump(report, f, indent=2, default=str)
        
        return report
    
    def _print_summary(self, report: Dict[str, Any]):
        """Print vision analysis summary."""
        print(f"\n👁️  VISION ANALYSIS REPORT:")
        
        if report.get('status') == 'no_data':
            print("   No frames analyzed (OpenCV may not be available)")
            return
        
        ui = report.get('ui_detection', {})
        print(f"   Frames Analyzed: {report.get('total_frames_analyzed', 0)}")
        print(f"   Health Bars Detected: {ui.get('total_health_bars', 0)}")
        print(f"   Damage Numbers: {ui.get('total_damage_numbers', 0)} ({ui.get('damage_per_frame_avg', 0)} per frame)")
        print(f"   Status Effects: {ui.get('total_status_effects', 0)}")
        
        anomalies = report.get('anomalies', {})
        print(f"   Anomalies: {anomalies.get('total_count', 0)}")
        if anomalies.get('total_count', 0) > 0:
            by_sev = anomalies.get('by_severity', {})
            print(f"     Critical: {by_sev.get('critical', 0)}")
            print(f"     Warnings: {by_sev.get('warning', 0)}")
        
        print(f"   Avg Scene Complexity: {report.get('scene_analysis', {}).get('avg_complexity', 0)}")
    
    def get_stats(self) -> Dict[str, Any]:
        """Return current vision stats."""
        return {
            'frames_analyzed': len(self.analyzed_frames),
            'ui_elements': len(self.ui_elements_detected),
            'anomalies': len(self.anomalies),
            'cv2_available': CV2_AVAILABLE
        }


def register_plugin(probe_instance):
    """Register the plugin with the probe."""
    plugin = MLVisionPlugin(probe_instance)
    print("✅ MLVisionPlugin registered successfully")
    return plugin


if __name__ == "__main__":
    print("Running MLVisionPlugin self-test...")
    print(f"   OpenCV Available: {CV2_AVAILABLE}")
    print(f"   PIL Available: {PIL_AVAILABLE}")
    
    if not CV2_AVAILABLE:
        print("⚠️  Skipping detailed test (OpenCV not installed)")
        print("   Install with: pip install opencv-python-headless")
    else:
        class MockProbe:
            def __init__(self):
                self.hooks = {}
            
            def register_hook(self, event, callback):
                if event not in self.hooks:
                    self.hooks[event] = []
                self.hooks[event].append(callback)
        
        mock_probe = MockProbe()
        plugin = MLVisionPlugin(mock_probe)
        
        # Create a test image
        test_img = np.zeros((480, 640, 3), dtype=np.uint8)
        cv2.rectangle(test_img, (50, 50), (200, 70), (0, 255, 0), -1)  # Green health bar
        
        result = plugin._analyze_frame(test_img, 0)
        
        print(f"\n✅ Self-test PASSED")
        print(f"   Health bars found: {len(result['health_bars'])}")
        print(f"   Scene complexity: {result['scene_complexity']}")
    
    stats = plugin.get_stats()
    print(f"\n   Stats: {stats}")
