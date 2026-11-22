#!/usr/bin/env bash

set -eo pipefail

cd /ros2_ws

echo "=========================================="
echo "  DIF_BOT OS - INICIO DEL SISTEMA"
echo "=========================================="

echo "[1/2] Cargando ROS 2 Jazzy..."
set +u
source /opt/ros/jazzy/setup.bash
source /ros2_ws/install/setup.bash
set -u

if [[ "${ROS_DISTRO:-}" != "jazzy" ]]; then
    echo "ERROR: ROS 2 Jazzy no está correctamente cargado."
    exit 1
fi

echo "ROS_DISTRO=${ROS_DISTRO}"

echo "[2/2] Iniciando DIF_BOT OS..."

exec ros2 launch dif_bot_bringup main.launch.py \
    use_sim_time:=true \
    use_ros2_control:="${USE_ROS2_CONTROL:-true}" \
    launch_navigation:=true
