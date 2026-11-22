#!/usr/bin/env bash

set -eo pipefail

# Workspace
cd /ros2_ws

echo "=========================================="
echo "  DIF_BOT OS - CONSTRUCCION ROS 2 JAZZY"
echo "=========================================="

# ROS 2 setup no es compatible con Bash nounset (-u).
# Por eso se mantiene desactivado durante los source.

echo "[1/5] Cargando ROS 2 Jazzy..."
set +u
source /opt/ros/jazzy/setup.bash
set -u

# Verificar distribución
if [[ "${ROS_DISTRO:-}" != "jazzy" ]]; then
    echo "ERROR: La distribución ROS no es Jazzy."
    exit 1
fi

echo "ROS_DISTRO=${ROS_DISTRO}"

# Actualizar rosdep
echo "[2/5] Actualizando rosdep..."
rosdep update

# Resolver dependencias
echo "[3/5] Instalando dependencias..."
rosdep install \
    --from-paths src \
    --ignore-src \
    -r -y \
    --rosdistro jazzy

# Compilar workspace
echo "[4/5] Compilando paquetes..."
MAKEFLAGS="-j1" colcon build \
    --symlink-install \
    --executor sequential

# Cargar workspace compilado
echo "[5/5] Cargando workspace..."
set +u
source /ros2_ws/install/setup.bash
set -u

echo "=========================================="
echo "  COMPILACION FINALIZADA"
echo "=========================================="

echo "Paquetes dif_bot disponibles:"
ros2 pkg list | grep '^dif_bot' || true
