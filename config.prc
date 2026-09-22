# Panda3D Configuration for Headless Testing
# This file enables offscreen rendering for CI/CD and automated testing

# Use the offscreen graphics pipe (no display required)
load-display pandagl

# Force offscreen rendering mode
pipe-type offscreen

# Enable EGL for headless operation (Linux servers without X11)
egl-device true

# Set a reasonable default resolution for screenshots
win-size 1024 768

# Disable audio for testing (saves resources)
audio-library-name null

# Enable shadow framebuffer for proper rendering
show-frame-rate-meter #f

# Use compatible shader model
gl-shader-profile 3 3

# Disable vertical sync for faster testing
sync-video #f

# Set anonymous console to avoid window management issues
notify-level-pananda warning
