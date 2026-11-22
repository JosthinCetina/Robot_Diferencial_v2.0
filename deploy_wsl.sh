#!/usr/bin/env bash
# Clone/update the official repository in WSL, build the Jazzy image and deploy it.
# The existing development checkout and named Docker volume are deliberately preserved.
set -Eeuo pipefail

REPO_URL="https://github.com/JosthinCetina/Robot_Diferencial_v2.0.git"
BRANCH="main"
IMAGE="dif-bot-os:jazzy"
CONTAINER="dif-bot-os-jazzy"
VOLUME="difbot_jazzy_ws"
DEPLOY_ROOT="${DIFBOT_DEPLOY_ROOT:-$HOME/difbot_deployment}"
PROJECT_DIR="$DEPLOY_ROOT/Robot_Diferencial_v2.0"
ROS_DOMAIN_ID_VALUE="${ROS_DOMAIN_ID:-42}"

info() { printf '\033[0;32m[DIF_BOT DEPLOY]\033[0m %s\n' "$*"; }
warn() { printf '\033[1;33m[AVISO]\033[0m %s\n' "$*" >&2; }
fail() { printf '\033[0;31m[ERROR]\033[0m %s\n' "$*" >&2; exit 1; }

is_wsl=false
if [[ -n "${WSL_DISTRO_NAME:-}" ]] || grep -qiE 'microsoft|wsl' /proc/sys/kernel/osrelease 2>/dev/null; then
  is_wsl=true
fi
[[ "$is_wsl" == "true" ]] || warn "No se detectó WSL. El script continuará si Docker tiene acceso a la GUI."

command -v git >/dev/null 2>&1 || fail "Falta Git en WSL. Instálalo con: sudo apt update && sudo apt install -y git"
command -v docker >/dev/null 2>&1 || fail "No se encontró Docker CLI. Activa la integración WSL de Docker Desktop."
docker info >/dev/null 2>&1 || fail "Docker no está disponible. Abre Docker Desktop y habilita la integración con esta distribución WSL."
command -v curl >/dev/null 2>&1 || fail "Falta curl."

mkdir -p "$DEPLOY_ROOT"

# Download the complete repository into a dedicated deployment checkout.
# This does not overwrite the user's existing ~/github/Robot_Diferencial_v2.0 checkout.
if [[ -d "$PROJECT_DIR/.git" ]]; then
  info "Actualizando checkout de despliegue: $PROJECT_DIR"
  cd "$PROJECT_DIR"

  REMOTE="$(git remote get-url origin 2>/dev/null || true)"
  case "$REMOTE" in
    "$REPO_URL"|https://github.com/JosthinCetina/Robot_Diferencial_v2.0|git@github.com:JosthinCetina/Robot_Diferencial_v2.0.git)
      ;;
    *)
      fail "La carpeta de despliegue apunta a un repositorio inesperado: $REMOTE"
      ;;
  esac

  [[ "$(git branch --show-current)" == "$BRANCH" ]] || fail "El checkout de despliegue debe estar en la rama $BRANCH."
  [[ -z "$(git status --porcelain)" ]] || fail "El checkout de despliegue contiene cambios locales. No se sobrescribirán; revisa $PROJECT_DIR."
  git fetch origin "$BRANCH"
  git pull --ff-only origin "$BRANCH"
elif [[ -e "$PROJECT_DIR" ]]; then
  fail "Existe $PROJECT_DIR, pero no es un checkout Git. Muévelo o define DIFBOT_DEPLOY_ROOT."
else
  info "Descargando el repositorio completo de GitHub..."
  git clone --branch "$BRANCH" "$REPO_URL" "$PROJECT_DIR"
  cd "$PROJECT_DIR"
fi

cd "$PROJECT_DIR"
[[ -f Dockerfile && -x START_DIF_BOT.sh && -x STOP_DIF_BOT.sh ]] || fail "El checkout descargado está incompleto."

info "Commit descargado:"
git log -1 --oneline

info "Construyendo imagen Docker $IMAGE desde el checkout WSL..."
docker build -t "$IMAGE" "$PROJECT_DIR"

# Reuse the existing named volume as a preserved backup; this deployment uses a
# bind mount of the WSL checkout so the complete project remains visible/editable in WSL.
if docker volume inspect "$VOLUME" >/dev/null 2>&1; then
  info "Se conserva el volumen existente $VOLUME (no se elimina ni se formatea)."
else
  info "No existe el volumen histórico $VOLUME; el despliegue nuevo usará el checkout WSL."
fi

# Stop only the old container with this project's reserved name.
# Its named volume is not removed.
if docker container inspect "$CONTAINER" >/dev/null 2>&1; then
  RUNNING="$(docker inspect -f '{{.State.Running}}' "$CONTAINER")"
  if [[ "$RUNNING" == "true" ]]; then
    warn "Deteniendo la instancia anterior de $CONTAINER..."
    docker exec "$CONTAINER" bash -lc 'cd /ros2_ws && ./STOP_DIF_BOT.sh' || warn "No fue posible ejecutar STOP en la instancia anterior; Docker la detendrá."
    docker stop --time 25 "$CONTAINER" >/dev/null || true
  fi
  docker rm "$CONTAINER" >/dev/null 2>&1 || true
fi

ARGS=(
  run -d
  --name "$CONTAINER"
  --restart unless-stopped
  --network host
  -e "ROS_DOMAIN_ID=$ROS_DOMAIN_ID_VALUE"
  -e "DISPLAY=${DISPLAY:-:0}"
  -e "WAYLAND_DISPLAY=${WAYLAND_DISPLAY:-wayland-0}"
  -e "XDG_RUNTIME_DIR=${XDG_RUNTIME_DIR:-/mnt/wslg/runtime-dir}"
  -e QT_X11_NO_MITSHM=1
  -v "$PROJECT_DIR:/ros2_ws"
  -w /ros2_ws
)
if [[ -d /mnt/wslg ]]; then
  ARGS+=( -v /mnt/wslg:/mnt/wslg )
fi
if [[ -d /tmp/.X11-unix ]]; then
  ARGS+=( -v /tmp/.X11-unix:/tmp/.X11-unix:rw )
fi
if [[ -d /dev/dri ]]; then
  ARGS+=( --device /dev/dri:/dev/dri )
fi

info "Creando contenedor con el proyecto montado desde WSL..."
docker "${ARGS[@]}" "$IMAGE" bash -lc 'while true; do sleep 3600; done'

info "Instalando dependencias ROS, compilando workspace y construyendo frontend..."
docker exec "$CONTAINER" bash -lc '
  set -eo pipefail
  cd /ros2_ws
  source /opt/ros/jazzy/setup.bash
  rosdep update
  rosdep install --from-paths src --ignore-src -r -y --rosdistro jazzy
  MAKEFLAGS="-j1" colcon build --symlink-install --executor sequential --event-handlers console_direct+
  source /ros2_ws/install/setup.bash
  cd /ros2_ws/web
  npm ci
  npm run build
'

info "Iniciando DIF_BOT OS (Gazebo, rosbridge, interfaz web, EKF y Nav2)..."
docker exec "$CONTAINER" bash -lc 'cd /ros2_ws && ./START_DIF_BOT.sh'

wait_for_port() {
  local port="$1"
  for _ in {1..30}; do
    if docker exec "$CONTAINER" bash -lc "timeout 1 bash -c '</dev/tcp/127.0.0.1/$port'" >/dev/null 2>&1; then
      return 0
    fi
    sleep 1
  done
  return 1
}

if ! wait_for_port 9090; then
  warn "Rosbridge no abrió el puerto 9090. Se conservan el contenedor y los logs para revisión."
  docker exec "$CONTAINER" bash -lc 'tail -n 80 /ros2_ws/logs/base.log 2>/dev/null || true'
  fail "Despliegue incompleto: no está disponible ws://localhost:9090."
fi

if ! wait_for_port 3000; then
  warn "La interfaz web no abrió el puerto 3000. Se conservan el contenedor y los logs."
  docker exec "$CONTAINER" bash -lc 'tail -n 80 /ros2_ws/logs/web.log 2>/dev/null || true'
  fail "Despliegue incompleto: no está disponible http://localhost:3000."
fi

echo
echo "=========================================================="
echo "              DIF_BOT OS - DESPLIEGUE COMPLETADO"
echo "=========================================================="
echo "Repositorio WSL : $PROJECT_DIR"
echo "Commit           : $(git rev-parse --short HEAD)"
echo "Contenedor       : $CONTAINER"
echo "Imagen           : $IMAGE"
echo "ROS_DOMAIN_ID    : $ROS_DOMAIN_ID_VALUE"
echo "Interfaz         : http://localhost:3000"
echo "Rosbridge        : ws://localhost:9090"
echo
echo "Logs dentro del contenedor:"
echo "  /ros2_ws/logs/base.log"
echo "  /ros2_ws/logs/navigation.log"
echo "  /ros2_ws/logs/web.log"
echo
echo "Para detener los nodos: docker exec $CONTAINER bash -lc 'cd /ros2_ws && ./STOP_DIF_BOT.sh'"
echo "Para detener el contenedor: docker stop $CONTAINER"
echo "El volumen $VOLUME (si existía) no fue eliminado."
