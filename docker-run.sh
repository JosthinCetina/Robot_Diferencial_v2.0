#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")" && pwd)"
ARGS=(--name dif-bot-os-jazzy --network host -it --rm
  -e ROS_DOMAIN_ID="${ROS_DOMAIN_ID:-42}"
  -e DISPLAY="${DISPLAY:-}"
  -e WAYLAND_DISPLAY="${WAYLAND_DISPLAY:-}"
  -e XDG_RUNTIME_DIR="${XDG_RUNTIME_DIR:-/mnt/wslg/runtime-dir}"
  -e QT_X11_NO_MITSHM=1
  -v "$ROOT:/ros2_ws"
  -v /tmp/.X11-unix:/tmp/.X11-unix:rw)
if [[ -d /mnt/wslg ]]; then ARGS+=( -v /mnt/wslg:/mnt/wslg ); fi
if [[ -d /dev/dri ]]; then ARGS+=( --device /dev/dri:/dev/dri ); fi
docker run "${ARGS[@]}" dif-bot-os:jazzy
