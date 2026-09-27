"""Shared solid-box mesh builder.

Replaces the old per-caller "cube" made of 6 flat CardMaker quads positioned
and rotated to approximate a box (with hardcoded per-face brightness
multipliers faking shading). This builds one real triangle-mesh unit box
(GeomVertexData + GeomTriangles) with correct outward face normals so
Panda3D's normal-based lighting can shade it for real, then every caller
instances that single Geom via setScale/setPos/setColor instead of
regenerating vertex data per call.
"""

from panda3d.core import (
    Geom,
    GeomNode,
    GeomTriangles,
    GeomVertexData,
    GeomVertexFormat,
    GeomVertexWriter,
    NodePath,
)

class _BoxMeshCache:
    """Holds the single shared unit-box Geom once built (avoids `global`)."""

    node: GeomNode | None = None

# 6 faces, each defined by its outward normal and the 4 corners of a unit
# cube (-0.5..0.5 per axis) wound counter-clockwise when viewed from outside.
_FACES = (
    ((0, 1, 0), ((-0.5, 0.5, -0.5), (0.5, 0.5, -0.5), (0.5, 0.5, 0.5), (-0.5, 0.5, 0.5))),   # front (+y)
    ((0, -1, 0), ((0.5, -0.5, -0.5), (-0.5, -0.5, -0.5), (-0.5, -0.5, 0.5), (0.5, -0.5, 0.5))),  # back (-y)
    ((-1, 0, 0), ((-0.5, -0.5, -0.5), (-0.5, 0.5, -0.5), (-0.5, 0.5, 0.5), (-0.5, -0.5, 0.5))),  # left (-x)
    ((1, 0, 0), ((0.5, 0.5, -0.5), (0.5, -0.5, -0.5), (0.5, -0.5, 0.5), (0.5, 0.5, 0.5))),   # right (+x)
    ((0, 0, 1), ((-0.5, 0.5, 0.5), (0.5, 0.5, 0.5), (0.5, -0.5, 0.5), (-0.5, -0.5, 0.5))),   # top (+z)
    ((0, 0, -1), ((-0.5, -0.5, -0.5), (0.5, -0.5, -0.5), (0.5, 0.5, -0.5), (-0.5, 0.5, -0.5))),  # bottom (-z)
)


def _build_unit_box_geom_node() -> GeomNode:
    fmt = GeomVertexFormat.getV3n3c4()
    vdata = GeomVertexData("solid_box", fmt, Geom.UHStatic)
    vdata.setNumRows(24)

    vertex = GeomVertexWriter(vdata, "vertex")
    normal = GeomVertexWriter(vdata, "normal")
    color = GeomVertexWriter(vdata, "color")

    tris = GeomTriangles(Geom.UHStatic)
    for face_index, (n, corners) in enumerate(_FACES):
        base = face_index * 4
        for corner in corners:
            vertex.addData3(*corner)
            normal.addData3(*n)
            color.addData4(1, 1, 1, 1)
        # Reversed order (base, base+2, base+1 / base, base+3, base+2): the
        # corners above are listed CCW as seen from *outside* the box, but
        # Panda3D's default back-face cull keeps clockwise-wound triangles;
        # winding them the other way was culling every face from outside.
        tris.addVertices(base, base + 2, base + 1)
        tris.addVertices(base, base + 3, base + 2)

    geom = Geom(vdata)
    geom.addPrimitive(tris)
    node = GeomNode("unit_box")
    node.addGeom(geom)
    return node


def _unit_box_geom_node() -> GeomNode:
    if _BoxMeshCache.node is None:
        _BoxMeshCache.node = _build_unit_box_geom_node()
    return _BoxMeshCache.node


def make_solid_box(parent, name, position, size, color) -> NodePath:
    """Instance the shared unit-box mesh, sized/positioned/colored per call.

    `position` = (x, y, z); `size` = (width, height, depth) where
    width/depth span x/y and height spans z (matches the old CardMaker
    cube convention used by character.py/enemy.py/main_game_scene.py).
    """
    x, y, z = position
    width, height, depth = size
    box = parent.attachNewNode(name)
    # The unit-box GeomNode is one shared singleton instanced everywhere (by
    # design, see module docstring): a PandaNode's transform/color lives on
    # the node itself, not per parent-arc, so setScale/setColor MUST go on
    # `box` (a fresh, non-shared node created above) and never on the child
    # that directly wraps the shared geometry -- setting them there would
    # overwrite every other instance's size/color game-wide.
    box.attachNewNode(_unit_box_geom_node())
    box.setScale(width, depth, height)
    box.setColor(*color)
    box.setPos(x, y, z)
    return box
