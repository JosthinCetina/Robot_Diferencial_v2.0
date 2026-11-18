#!/usr/bin/env bash
set -euo pipefail
cd /ros2_ws
source /opt/ros/jazzy/setup.bash
rosdep update
rosdep install --from-paths src --ignore-src -r -y --rosdistro jazzy
MAKEFLAGS="-j1" colcon build --symlink-install --executor sequential
source install/setup.bash
