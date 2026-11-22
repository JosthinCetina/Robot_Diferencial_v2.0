#!/usr/bin/env bash
set -Eeuo pipefail

WORKSPACE="${WORKSPACE:-/ros2_ws}"
MAP_DIR="$WORKSPACE/src/dif_bot_navigation/maps"
MAP_NAME="${1:-my_map}"

if [[ ! "$MAP_NAME" =~ ^[A-Za-z0-9_-]+$ ]]; then
  echo "Nombre de mapa inválido. Usa letras, números, guion o guion bajo." >&2
  exit 2
fi

source /opt/ros/jazzy/setup.bash
source "$WORKSPACE/install/setup.bash"
mkdir -p "$MAP_DIR"

PREFIX="$MAP_DIR/$MAP_NAME"
echo "[SLAM] Guardando /map en $PREFIX.yaml y $PREFIX.pgm ..."
ros2 run nav2_map_server map_saver_cli -f "$PREFIX" --ros-args -p use_sim_time:=true

[[ -s "$PREFIX.yaml" && -s "$PREFIX.pgm" ]] || {
  echo "[ERROR] Map Saver no generó ambos archivos." >&2
  exit 1
}

echo "[OK] Mapa guardado:"
echo "  YAML: $PREFIX.yaml"
echo "  PGM : $PREFIX.pgm"
