"""
Test L6 Curriculum & L7 Render Components

Tests for:
- L6: CurriculumManager (difficulty progression, stages)
- L7: Renderer (isometric camera, UI overlays)
"""

import pytest
import numpy as np
from unittest.mock import Mock, MagicMock, patch
import json

# Import L6 and L7 components
import sys
sys.path.insert(0, '/workspace/python_layer')

from l6_curriculum.curriculum_manager import CurriculumManager, CurriculumStage
from l7_render.renderer import Renderer, IsometricCamera, SceneEditor


# ==================== L6 CURRICULUM TESTS ====================

class TestCurriculumStage:
    """Test curriculum stage definition."""
    
    def test_stage_creation(self):
        """Test creating a curriculum stage."""
        stage = CurriculumStage(
            stage_id=1,
            name="Combat Basics",
            difficulty=0.3,
            objectives=["defeat_enemy"],
            constraints={"enemy_count": 1}
        )
        
        assert stage.stage_id == 1
        assert stage.name == "Combat Basics"
        assert stage.difficulty == 0.3
        assert "defeat_enemy" in stage.objectives
        assert stage.constraints["enemy_count"] == 1
    
    def test_stage_validation(self):
        """Test stage validation."""
        stage = CurriculumStage(
            stage_id=1,
            name="Test Stage",
            difficulty=0.5,
            objectives=["survive"],
            constraints={}
        )
        
        # Valid stage
        assert stage.is_valid() is True
        
        # Invalid difficulty
        invalid_stage = CurriculumStage(
            stage_id=2,
            name="Invalid Stage",
            difficulty=1.5,  # > 1.0
            objectives=[],
            constraints={}
        )
        assert invalid_stage.is_valid() is False


class TestCurriculumManager:
    """Test curriculum management."""
    
    def test_manager_initialization(self):
        """Test curriculum manager initialization."""
        manager = CurriculumManager()
        
        assert manager is not None
        assert hasattr(manager, 'stages')
        assert len(manager.stages) > 0  # Should have default stages
    
    def test_get_current_stage(self):
        """Test getting current stage."""
        manager = CurriculumManager()
        
        # Initially at first stage
        current = manager.get_current_stage()
        assert current is not None
        assert current.stage_id == manager.current_stage_id
    
    def test_advance_stage(self):
        """Test advancing to next stage."""
        manager = CurriculumManager()
        
        initial_stage = manager.get_current_stage()
        initial_id = initial_stage.stage_id
        
        # Advance
        success = manager.advance_stage()
        
        assert success is True
        new_stage = manager.get_current_stage()
        assert new_stage.stage_id > initial_id
    
    def test_check_stage_completion(self):
        """Test checking if stage is complete."""
        manager = CurriculumManager()
        
        # Get current stage requirements
        current_stage = manager.get_current_stage()
        
        # Simulate progress
        progress = {
            'enemies_defeated': 10,
            'damage_taken': 5,
            'time_survived': 60
        }
        
        # Check completion
        is_complete = manager.check_stage_completion(progress)
        
        # Should return boolean
        assert isinstance(is_complete, bool)
    
    def test_get_difficulty_scaling(self):
        """Test difficulty scaling calculation."""
        manager = CurriculumManager()
        
        # Get scaling for current stage
        scaling = manager.get_difficulty_scaling()
        
        assert scaling is not None
        assert isinstance(scaling, dict)
        assert 'enemy_health_multiplier' in scaling or 'damage_multiplier' in scaling
    
    def test_adaptive_curriculum(self):
        """Test adaptive curriculum adjustment."""
        manager = CurriculumManager()
        
        # Simulate player performance
        performance_history = [
            {'success': True, 'time': 30},
            {'success': True, 'time': 25},
            {'success': True, 'time': 20},
        ]
        
        # Adjust curriculum based on performance
        adjustment = manager.adapt_to_player_performance(performance_history)
        
        # Should provide adjustment recommendation
        assert adjustment is not None
    
    def test_get_training_hints(self):
        """Test getting training hints for player."""
        manager = CurriculumManager()
        
        current_stage = manager.get_current_stage()
        hints = manager.get_training_hints(current_stage)
        
        # Should provide hints
        assert hints is not None
        assert isinstance(hints, list)
    
    def test_analyze_player_weaknesses(self):
        """Test analyzing player weaknesses."""
        manager = CurriculumManager()
        
        # Simulate gameplay data
        gameplay_data = {
            'deaths_by_enemy': 5,
            'deaths_by_trap': 0,
            'average_combat_time': 45,
            'success_rate': 0.6
        }
        
        weaknesses = manager.analyze_player_weaknesses(gameplay_data)
        
        # Should identify weaknesses
        assert weaknesses is not None
        assert isinstance(weaknesses, dict)


# ==================== L7 RENDER TESTS ====================

class TestIsometricCamera:
    """Test isometric camera functionality."""
    
    def test_camera_creation(self):
        """Test isometric camera creation."""
        camera = IsometricCamera()
        
        assert camera is not None
        assert hasattr(camera, 'position')
        assert hasattr(camera, 'rotation')
    
    def test_camera_movement(self):
        """Test camera movement."""
        camera = IsometricCamera()
        
        initial_pos = camera.position.copy()
        
        # Move camera
        camera.move(dx=1.0, dy=0.0, dz=0.0)
        
        # Position should change
        assert camera.position[0] != initial_pos[0]
    
    def test_camera_zoom(self):
        """Test camera zoom."""
        camera = IsometricCamera()
        
        initial_zoom = camera.zoom_level
        
        # Zoom in
        camera.zoom(1.5)
        
        # Zoom level should increase
        assert camera.zoom_level > initial_zoom
    
    def test_camera_rotation(self):
        """Test camera rotation."""
        camera = IsometricCamera()
        
        initial_rotation = camera.rotation.copy()
        
        # Rotate camera
        camera.rotate(angle=45.0)
        
        # Rotation should change
        assert camera.rotation != initial_rotation
    
    def test_screen_to_world(self):
        """Test screen to world coordinate conversion."""
        camera = IsometricCamera()
        
        # Screen coordinates
        screen_x, screen_y = 100, 200
        
        # Convert to world
        world_pos = camera.screen_to_world(screen_x, screen_y)
        
        assert world_pos is not None
        assert len(world_pos) == 3  # x, y, z
    
    def test_world_to_screen(self):
        """Test world to screen coordinate conversion."""
        camera = IsometricCamera()
        
        # World coordinates
        world_x, world_y, world_z = 10.0, 20.0, 0.0
        
        # Convert to screen
        screen_pos = camera.world_to_screen(world_x, world_y, world_z)
        
        assert screen_pos is not None
        assert len(screen_pos) == 2  # x, y


class TestSceneEditor:
    """Test scene editor functionality."""
    
    def test_editor_creation(self):
        """Test scene editor creation."""
        editor = SceneEditor()
        
        assert editor is not None
        assert hasattr(editor, 'objects')
    
    def test_add_object(self):
        """Test adding object to scene."""
        editor = SceneEditor()
        
        obj_data = {
            'type': 'enemy',
            'position': [10, 20, 0],
            'properties': {'health': 100}
        }
        
        obj_id = editor.add_object(obj_data)
        
        assert obj_id is not None
        assert obj_id in editor.objects
    
    def test_remove_object(self):
        """Test removing object from scene."""
        editor = SceneEditor()
        
        # Add then remove
        obj_data = {'type': 'prop', 'position': [0, 0, 0]}
        obj_id = editor.add_object(obj_data)
        
        success = editor.remove_object(obj_id)
        
        assert success is True
        assert obj_id not in editor.objects
    
    def test_modify_object(self):
        """Test modifying object properties."""
        editor = SceneEditor()
        
        # Add object
        obj_data = {'type': 'character', 'position': [5, 5, 0]}
        obj_id = editor.add_object(obj_data)
        
        # Modify
        modifications = {'position': [10, 10, 0]}
        success = editor.modify_object(obj_id, modifications)
        
        assert success is True
        assert editor.objects[obj_id]['position'] == [10, 10, 0]
    
    def test_get_objects_in_range(self):
        """Test getting objects within range."""
        editor = SceneEditor()
        
        # Add multiple objects
        for i in range(5):
            editor.add_object({
                'type': 'test',
                'position': [i * 10, 0, 0]
            })
        
        # Query range
        center = [20, 0, 0]
        radius = 15
        
        objects_in_range = editor.get_objects_in_range(center, radius)
        
        # Should find nearby objects
        assert len(objects_in_range) >= 1


class TestRenderer:
    """Test main renderer functionality."""
    
    @pytest.fixture
    def mock_render_context(self):
        """Create mock render context."""
        mock_ctx = Mock()
        mock_ctx.render.return_value = None
        mock_ctx.update.return_value = None
        return mock_ctx
    
    def test_renderer_initialization(self, mock_render_context):
        """Test renderer initialization."""
        with patch('l7_render.renderer.Renderer._init_render_context', return_value=mock_render_context):
            renderer = Renderer()
            
            assert renderer is not None
            assert hasattr(renderer, 'camera')
            assert hasattr(renderer, 'scene_editor')
    
    def test_render_frame(self, mock_render_context):
        """Test rendering a frame."""
        with patch('l7_render.renderer.Renderer._init_render_context', return_value=mock_render_context):
            renderer = Renderer()
            
            # Render should not raise exception
            try:
                renderer.render_frame()
            except Exception as e:
                pytest.fail(f"Render frame raised unexpected exception: {e}")
    
    def test_update_scene(self, mock_render_context):
        """Test updating scene."""
        with patch('l7_render.renderer.Renderer._init_render_context', return_value=mock_render_context):
            renderer = Renderer()
            
            # Update with game state
            game_state = {
                'entities': [],
                'effects': [],
                'ui_elements': []
            }
            
            try:
                renderer.update_scene(game_state)
            except Exception as e:
                pytest.fail(f"Update scene raised unexpected exception: {e}")
    
    def test_render_ui_overlay(self, mock_render_context):
        """Test rendering UI overlay."""
        with patch('l7_render.renderer.Renderer._init_render_context', return_value=mock_render_context):
            renderer = Renderer()
            
            ui_elements = [
                {'type': 'health_bar', 'value': 0.8},
                {'type': 'minimap', 'position': [100, 100]},
            ]
            
            try:
                renderer.render_ui_overlay(ui_elements)
            except Exception as e:
                pytest.fail(f"Render UI overlay raised unexpected exception: {e}")
    
    def test_screenshot(self, mock_render_context):
        """Test taking screenshot."""
        with patch('l7_render.renderer.Renderer._init_render_context', return_value=mock_render_context):
            renderer = Renderer()
            
            # Screenshot should return image data
            try:
                screenshot = renderer.take_screenshot()
                # Could be None if no actual render context
                assert screenshot is None or isinstance(screenshot, np.ndarray)
            except Exception as e:
                pytest.fail(f"Screenshot raised unexpected exception: {e}")


class TestTrainerUI:
    """Test trainer UI overlays."""
    
    def test_training_metrics_display(self):
        """Test displaying training metrics."""
        # Simulate metrics
        metrics = {
            'episode': 100,
            'reward': 250.5,
            'loss': 0.45,
            'learning_rate': 0.001
        }
        
        # Format for display
        display_text = f"Episode: {metrics['episode']} | Reward: {metrics['reward']:.1f}"
        
        assert "Episode: 100" in display_text
        assert "Reward: 250.5" in display_text
    
    def test_auto_balancer_ui(self):
        """Test auto-balancer UI."""
        # Simulate balance state
        balance_state = {
            'player_advantage': 0.1,
            'recommended_adjustment': 'increase_enemy_health',
            'confidence': 0.85
        }
        
        # Generate UI suggestion
        suggestion = f"Recommendation: {balance_state['recommended_adjustment']} (confidence: {balance_state['confidence']:.0%})"
        
        assert "increase_enemy_health" in suggestion
        assert "85%" in suggestion


# ==================== INTEGRATION TESTS ====================

class TestL6L7Integration:
    """Integration tests for L6 and L7."""
    
    def test_curriculum_with_visualization(self):
        """Test curriculum progression with visual feedback."""
        manager = CurriculumManager()
        
        # Get current stage
        stage = manager.get_current_stage()
        
        # Create visual representation hint
        visual_hint = {
            'stage_name': stage.name,
            'difficulty_color': 'green' if stage.difficulty < 0.3 else 'yellow' if stage.difficulty < 0.7 else 'red',
            'objectives': stage.objectives
        }
        
        assert visual_hint['stage_name'] == stage.name
        assert visual_hint['difficulty_color'] in ['green', 'yellow', 'red']
    
    def test_renderer_with_curriculum_data(self):
        """Test renderer displaying curriculum information."""
        manager = CurriculumManager()
        camera = IsometricCamera()
        
        # Get curriculum info
        current_stage = manager.get_current_stage()
        
        # Position camera to show stage area
        camera.position = [0, 0, 10]  # Overview position
        
        # Verify camera can view stage area
        screen_pos = camera.world_to_screen(0, 0, 0)
        assert screen_pos is not None


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
