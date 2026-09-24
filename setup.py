"""Standalone builds of the game with Panda3D's build_apps.

    python setup.py build_apps                       # all platforms below
    python setup.py build_apps -p win_amd64          # just one
    python setup.py bdist_apps                       # + zip/tar archives in dist/

Frozen modules are found by import analysis from main.py; third-party wheels
for each target platform are downloaded from PyPI using requirements.txt, so
one machine can build for all three platforms. rust_core is not bundled: the
game does not import it yet.
"""

from setuptools import setup

VERSION = "0.2.0a0"

setup(
    name="AI-EVOLVE",
    version=VERSION,
    options={
        "build_apps": {
            "gui_apps": {"ai-evolve": "main.py"},
            # Data files the game opens at runtime (checked with an audit hook)
            "include_patterns": ["config/*.json", "lua_content/**/*.lua", "assets/**/*"],
            "plugins": ["pandagl", "p3openal_audio"],
            # Plain PyPI wheels. Panda3D's "+opt" index serves a macOS wheel whose md5 in the index
            # does not match the file ("THESE PACKAGES DO NOT MATCH THE HASHES", 2026-09-24).
            "use_optimized_wheels": False,
            "platforms": ["win_amd64", "manylinux2014_x86_64", "macosx_11_0_arm64"],
            "log_filename": "$USER_APPDATA/AI-EVOLVE/output.log",
            "log_append": False,
            # Imported dynamically, invisible to the import analysis: SQLAlchemy
            # loads its dialect by name from the "sqlite:///..." URL
            "include_modules": {"*": ["sqlalchemy.dialects.sqlite", "sqlalchemy.dialects.sqlite.pysqlite"]},
            # Dead/optional code paths that would drag in heavy packages
            # rust_core is optional at runtime (every user has a Python fallback) and is not
            # bundled; excluding it stops the analysis from treating the rust_core/ folder
            # as a package that needs a wheel.
            "exclude_modules": {"*": ["torch", "flet", "cv2", "skimage", "imagehash", "tkinter", "rust_core"]},
        },
    },
)
