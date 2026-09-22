#!/usr/bin/env python3
"""
Renderer Abstraction Layer

Purpose:
- Decouple rendering logic from Panda3D dependency
- Enable headless testing without GUI
- Support future engine migration
- Follow Dependency Inversion Principle (DIP)

Usage:
    # In production
    renderer = Panda3DRenderer()
    
    # In tests
    renderer = HeadlessRenderer()
    
    # Inject into systems
    health_bar = renderer.create_health_bar(width=1.0, height=0.1)
"""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from typing import Any, Protocol

logger = logging.getLogger(__name__)


# ============================================================================
# RENDERER PROTOCOLS (Interfaces)
# ============================================================================


class ICardMaker(Protocol):
    """Protocol for card/rectangle creation."""
    
    def set_frame(self, left: float, right: float, bottom: float, top: float) -> None:
        """Set card dimensions."""
        ...
    
    def set_color(self, r: float, g: float, b: float, a: float = 1.0) -> None:
        """Set card color."""
        ...
    
    def generate(self, name: str) -> Any:
        """Generate the card geometry."""
        ...


class ITextNode(Protocol):
    """Protocol for text rendering."""
    
    def set_text(self, text: str) -> None:
        """Set text content."""
        ...
    
    def set_scale(self, scale: float) -> None:
        """Set text scale."""
        ...
    
    def set_pos(self, x: float, y: float, z: float) -> None:
        """Set text position."""
        ...


class INodePath(Protocol):
    """Protocol for scene graph nodes."""
    
    def attach_new_node(self, node: Any) -> Any:
        """Attach node to scene graph."""
        ...
    
    def remove_node(self) -> None:
        """Remove from scene graph."""
        ...
    
    def hide(self) -> None:
        """Hide the node."""
        ...
    
    def show(self) -> None:
        """Show the node."""
        ...
    
    def set_pos(self, x: float, y: float, z: float) -> None:
        """Set position."""
        ...
    
    def set_scale(self, scale: float) -> None:
        """Set scale."""
        ...


class IRenderer(ABC):
    """
    Abstract base class for renderers.
    
    This is the main interface that all renderer implementations must follow.
    Allows swapping renderer backends without changing game logic.
    """
    
    @property
    @abstractmethod
    def is_headless(self) -> bool:
        """Return True if this is a headless (non-GUI) renderer."""
        ...
    
    @abstractmethod
    def create_card(self, width: float, height: float, name: str = "card") -> Any:
        """Create a rectangular card/quad."""
        ...
    
    @abstractmethod
    def create_colored_card(
        self, 
        width: float, 
        height: float, 
        r: float, 
        g: float, 
        b: float, 
        a: float = 1.0,
        name: str = "colored_card"
    ) -> Any:
        """Create a colored rectangular card."""
        ...
    
    @abstractmethod
    def create_text_node(self, text: str = "", name: str = "text") -> Any:
        """Create a text node."""
        ...
    
    @abstractmethod
    def create_health_bar(
        self, 
        width: float, 
        height: float,
        fill_color: tuple[float, float, float, float] = (0.0, 1.0, 0.0, 1.0),
        border_color: tuple[float, float, float, float] = (1.0, 1.0, 1.0, 1.0),
        name: str = "health_bar"
    ) -> dict[str, Any]:
        """
        Create a health bar UI element.
        
        Returns dict with keys:
        - 'root': NodePath of the root
        - 'fill': NodePath of the fill bar
        - 'border': NodePath of the border
        """
        ...
    
    @abstractmethod
    def set_transparency(self, node: Any, enabled: bool = True) -> None:
        """Enable/disable transparency on a node."""
        ...
    
    @abstractmethod
    def parent_node(self, child: Any, parent: Any) -> None:
        """Parent a node to another node."""
        ...
    
    @abstractmethod
    def destroy_node(self, node: Any) -> None:
        """Destroy/remove a node from the scene."""
        ...


# ============================================================================
# HEADLESS RENDERER (For Testing)
# ============================================================================


class HeadlessRenderer(IRenderer):
    """
    Headless renderer implementation.
    
    Used for:
    - Unit tests without GUI
    - Server-side simulations
    - Performance benchmarks
    
    All methods are no-ops or return mock objects.
    """
    
    def __init__(self) -> None:
        self._is_headless = True
        logger.debug("HeadlessRenderer initialized")
    
    @property
    def is_headless(self) -> bool:
        return self._is_headless
    
    def create_card(self, width: float, height: float, name: str = "card") -> Any:
        """Return mock card object."""
        logger.debug(f"[Headless] Created card '{name}': {width}x{height}")
        return MockNodePath(name)
    
    def create_colored_card(
        self, 
        width: float, 
        height: float, 
        r: float, 
        g: float, 
        b: float, 
        a: float = 1.0,
        name: str = "colored_card"
    ) -> Any:
        """Return mock colored card."""
        logger.debug(f"[Headless] Created colored card '{name}': {width}x{height} RGBA({r},{g},{b},{a})")
        return MockNodePath(name)
    
    def create_text_node(self, text: str = "", name: str = "text") -> Any:
        """Return mock text node."""
        logger.debug(f"[Headless] Created text node '{name}': '{text}'")
        return MockTextNode(name, text)
    
    def create_health_bar(
        self, 
        width: float, 
        height: float,
        fill_color: tuple[float, float, float, float] = (0.0, 1.0, 0.0, 1.0),
        border_color: tuple[float, float, float, float] = (1.0, 1.0, 1.0, 1.0),
        name: str = "health_bar"
    ) -> dict[str, Any]:
        """Return mock health bar."""
        logger.debug(f"[Headless] Created health bar '{name}': {width}x{height}")
        root = MockNodePath(f"{name}_root")
        fill = MockNodePath(f"{name}_fill")
        border = MockNodePath(f"{name}_border")
        return {'root': root, 'fill': fill, 'border': border}
    
    def set_transparency(self, node: Any, enabled: bool = True) -> None:
        """No-op in headless mode."""
        logger.debug(f"[Headless] Set transparency on {node}: {enabled}")
    
    def parent_node(self, child: Any, parent: Any) -> None:
        """No-op in headless mode."""
        logger.debug(f"[Headless] Parented {child} to {parent}")
    
    def destroy_node(self, node: Any) -> None:
        """Mark node as destroyed."""
        logger.debug(f"[Headless] Destroyed {node}")
        if hasattr(node, '_destroy'):
            node._destroy()


# ============================================================================
# PANDA3D RENDERER (Production)
# ============================================================================


class Panda3DRenderer(IRenderer):
    """
    Panda3D engine renderer implementation.
    
    This is the production renderer that uses actual Panda3D APIs.
    All dependencies on panda3d.core are isolated here.
    """
    
    def __init__(self, render_node: Any | None = None) -> None:
        """
        Initialize Panda3D renderer.
        
        Args:
            render_node: The root render node (usually 'render' from Panda3D).
                        If None, will try to import from panda3d.core.
        """
        self._is_headless = False
        self._render = render_node
        
        # Lazy import to allow testing without Panda3D
        try:
            from panda3d.core import CardMaker, TransparencyAttrib, TextNode
            self._CardMaker = CardMaker
            self._TransparencyAttrib = TransparencyAttrib
            self._TextNode = TextNode
            logger.info("Panda3DRenderer initialized with full capabilities")
        except ImportError as e:
            logger.warning(f"Panda3D not available, some features disabled: {e}")
            self._CardMaker = None
            self._TransparencyAttrib = None
            self._TextNode = None
    
    @property
    def is_headless(self) -> bool:
        return self._is_headless
    
    def create_card(self, width: float, height: float, name: str = "card") -> Any:
        """Create a rectangular card using Panda3D CardMaker."""
        if self._CardMaker is None:
            logger.error("CardMaker not available (Panda3D not loaded)")
            return None
        
        card_maker = self._CardMaker(name)
        half_w = width / 2.0
        half_h = height / 2.0
        card_maker.set_frame(-half_w, half_w, -half_h, half_h)
        
        card_np = self._render.attach_new_node(card_maker.generate())
        logger.debug(f"[Panda3D] Created card '{name}': {width}x{height}")
        return card_np
    
    def create_colored_card(
        self, 
        width: float, 
        height: float, 
        r: float, 
        g: float, 
        b: float, 
        a: float = 1.0,
        name: str = "colored_card"
    ) -> Any:
        """Create a colored rectangular card."""
        card_np = self.create_card(width, height, name)
        if card_np and hasattr(card_np.node(), 'setColor'):
            card_np.node().setColor(r, g, b, a)
        logger.debug(f"[Panda3D] Created colored card '{name}': {width}x{height} RGBA({r},{g},{b},{a})")
        return card_np
    
    def create_text_node(self, text: str = "", name: str = "text") -> Any:
        """Create a TextNode."""
        if self._TextNode is None:
            logger.error("TextNode not available (Panda3D not loaded)")
            return None
        
        text_node = self._TextNode(name)
        text_node.setText(text)
        text_np = self._render.attach_new_node(text_node)
        logger.debug(f"[Panda3D] Created text node '{name}': '{text}'")
        return text_np
    
    def create_health_bar(
        self, 
        width: float, 
        height: float,
        fill_color: tuple[float, float, float, float] = (0.0, 1.0, 0.0, 1.0),
        border_color: tuple[float, float, float, float] = (1.0, 1.0, 1.0, 1.0),
        name: str = "health_bar"
    ) -> dict[str, Any]:
        """Create a health bar UI element."""
        if self._CardMaker is None:
            logger.error("CardMaker not available for health bar")
            return {'root': None, 'fill': None, 'border': None}
        
        # Create root node
        root_name = f"{name}_root"
        root = self._render.attach_new_node(root_name)
        
        # Create border
        border_maker = self._CardMaker(f"{name}_border")
        half_w = width / 2.0
        half_h = height / 2.0
        border_maker.set_frame(-half_w, half_w, -half_h, half_h)
        border_np = root.attach_new_node(border_maker.generate())
        border_np.node().setColor(*border_color)
        self.set_transparency(border_np, True)
        
        # Create fill (slightly smaller)
        fill_maker = self._CardMaker(f"{name}_fill")
        inset = 0.02  # Small inset for visual separation
        fill_maker.set_frame(-half_w + inset, half_w - inset, -half_h + inset, half_h - inset)
        fill_np = root.attach_new_node(fill_maker.generate())
        fill_np.node().setColor(*fill_color)
        self.set_transparency(fill_np, True)
        
        logger.debug(f"[Panda3D] Created health bar '{name}': {width}x{height}")
        return {'root': root, 'fill': fill_np, 'border': border_np}
    
    def set_transparency(self, node: Any, enabled: bool = True) -> None:
        """Enable/disable transparency on a Panda3D node."""
        if self._TransparencyAttrib is None:
            return
        
        if enabled:
            node.set_transparency(self._TransparencyAttrib.MAlpha)
        else:
            node.clear_transparency()
    
    def parent_node(self, child: Any, parent: Any) -> None:
        """Reparent a node in Panda3D scene graph."""
        if child and parent and hasattr(child, 'reparent_to'):
            child.reparent_to(parent)
            logger.debug(f"[Panda3D] Reparented {child.get_name()} to {parent.get_name()}")
    
    def destroy_node(self, node: Any) -> None:
        """Remove and destroy a Panda3D node."""
        if node and hasattr(node, 'remove_node'):
            node.remove_node()
            logger.debug(f"[Panda3D] Destroyed {node.get_name() if hasattr(node, 'get_name') else 'node'}")


# ============================================================================
# MOCK OBJECTS FOR HEADLESS MODE
# ============================================================================


class MockNodePath:
    """Mock NodePath for headless testing."""
    
    def __init__(self, name: str = "mock_node") -> None:
        self._name = name
        self._children: list[MockNodePath] = []
        self._destroyed = False
        self._pos = (0.0, 0.0, 0.0)
        self._scale = 1.0
        self._hidden = False
    
    @property
    def name(self) -> str:
        return self._name
    
    def get_name(self) -> str:
        return self._name
    
    def attach_new_node(self, node: Any) -> Any:
        """Mock attach."""
        if isinstance(node, MockNodePath):
            self._children.append(node)
        return node
    
    def reparent_to(self, parent: Any) -> None:
        """Mock reparent."""
        pass
    
    def remove_node(self) -> None:
        """Mock remove."""
        self._destroyed = True
    
    def hide(self) -> None:
        """Mock hide."""
        self._hidden = True
    
    def show(self) -> None:
        """Mock show."""
        self._hidden = False
    
    def set_pos(self, x: float, y: float, z: float) -> None:
        """Mock set position."""
        self._pos = (x, y, z)
    
    def set_scale(self, scale: float) -> None:
        """Mock set scale."""
        self._scale = scale
    
    def node(self) -> Any:
        """Return self for method chaining."""
        return self
    
    def setColor(self, r: float, g: float, b: float, a: float = 1.0) -> None:
        """Mock set color."""
        pass
    
    def set_transparency(self, mode: Any) -> None:
        """Mock set transparency."""
        pass
    
    def __repr__(self) -> str:
        status = "destroyed" if self._destroyed else ("hidden" if self._hidden else "active")
        return f"MockNodePath('{self._name}', {status})"


class MockTextNode:
    """Mock TextNode for headless testing."""
    
    def __init__(self, name: str = "mock_text", text: str = "") -> None:
        self._name = name
        self._text = text
        self._scale = 1.0
        self._pos = (0.0, 0.0, 0.0)
    
    def set_text(self, text: str) -> None:
        """Set text content."""
        self._text = text
    
    def set_scale(self, scale: float) -> None:
        """Set text scale."""
        self._scale = scale
    
    def set_pos(self, x: float, y: float, z: float) -> None:
        """Set text position."""
        self._pos = (x, y, z)
    
    def setText(self, text: str) -> None:
        """Alias for set_text (Panda3D compatibility)."""
        self.set_text(text)
    
    def __repr__(self) -> str:
        return f"MockTextNode('{self._name}', '{self._text}')"


# ============================================================================
# RENDERER FACTORY
# ============================================================================


def create_renderer(headless: bool = False, render_node: Any | None = None) -> IRenderer:
    """
    Factory function to create appropriate renderer.
    
    Args:
        headless: If True, use HeadlessRenderer. Otherwise use Panda3DRenderer.
        render_node: Root render node for Panda3DRenderer.
    
    Returns:
        IRenderer implementation
    """
    if headless:
        return HeadlessRenderer()
    else:
        return Panda3DRenderer(render_node)


# ============================================================================
# GLOBAL RENDERER REGISTRY (Optional Convenience)
# ============================================================================


class RendererRegistry:
    """
    Global registry for renderer instances.
    
    Use this for quick access without dependency injection.
    For testable code, prefer injecting IRenderer via constructor.
    """
    
    _instance: IRenderer | None = None
    
    @classmethod
    def register(cls, renderer: IRenderer) -> None:
        """Register a renderer instance."""
        cls._instance = renderer
        logger.info(f"Renderer registered: {renderer.__class__.__name__}")
    
    @classmethod
    def get(cls) -> IRenderer:
        """Get the registered renderer."""
        if cls._instance is None:
            logger.warning("No renderer registered, creating default HeadlessRenderer")
            cls._instance = HeadlessRenderer()
        return cls._instance
    
    @classmethod
    def reset(cls) -> None:
        """Clear the registered renderer."""
        cls._instance = None
