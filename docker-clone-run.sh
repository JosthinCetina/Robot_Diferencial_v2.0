#!/usr/bin/env bash
set -euo pipefail
REPO_URL="${1:?Uso: ./docker-clone-run.sh https://github.com/usuario/dif_bot_os_jazzy.git [rama]}"
BRANCH="${2:-main}"
IMAGE="dif-bot-os:jazzy"
VOLUME="difbot_jazzy_ws"
CONTAINER="dif-bot-os-jazzy"

echo "[1/3] Construyendo imagen Docker desde el Dockerfile del repositorio remoto..."
docker build -t "$IMAGE" "${REPO_URL}#${BRANCH}"

echo "[2/3] Preparando volumen persistente para el workspace..."
docker volume create "$VOLUME" >/dev/null

echo "[3/3] Iniciando contenedor dedicado y clonando el proyecto en /ros2_ws..."
ARGS=(--name "$CONTAINER" --network host -it --rm
  -e ROS_DOMAIN_ID="${ROS_DOMAIN_ID:-42}"
  -v "$VOLUME:/ros2_ws" -e REPO_URL="$REPO_URL" -e REPO_BRANCH="$BRANCH"
  -e DISPLAY="${DISPLAY:-}" -e WAYLAND_DISPLAY="${WAYLAND_DISPLAY:-}"
  -e XDG_RUNTIME_DIR="${XDG_RUNTIME_DIR:-/mnt/wslg/runtime-dir}"
  -e QT_X11_NO_MITSHM=1 -v /tmp/.X11-unix:/tmp/.X11-unix:rw)
if [[ -d /mnt/wslg ]]; then ARGS+=( -v /mnt/wslg:/mnt/wslg ); fi
if [[ -d /dev/dri ]]; then ARGS+=( --device /dev/dri:/dev/dri ); fi

docker run "${ARGS[@]}" "$IMAGE" bash -lc '
  if [[ ! -d /ros2_ws/.git ]]; then
    git clone --branch "$REPO_BRANCH" "$REPO_URL" /ros2_ws
  else
    git -C /ros2_ws pull --ff-only
  fi
  source /opt/ros/jazzy/setup.bash
  cd /ros2_ws
  exec bash
'
