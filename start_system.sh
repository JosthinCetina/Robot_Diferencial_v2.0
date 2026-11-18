#!/usr/bin/env bash
set -euo pipefail
cd /ros2_ws
source /opt/ros/jazzy/setup.bash
source /ros2_ws/install/setup.bash
ros2 launch dif_bot_bringup main.launch.py use_sim_time:=true use_ros2_control:=${USE_ROS2_CONTROL:-true} launch_navigation:=true
