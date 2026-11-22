#!/usr/bin/env bash
set -Eeuo pipefail

WORKSPACE=/ros2_ws
PID_DIR=/tmp/dif_bot_os
LOG_DIR="$WORKSPACE/logs"
export ROS_DOMAIN_ID="${ROS_DOMAIN_ID:-42}"
mkdir -p "$PID_DIR" "$LOG_DIR"

info(){ printf '\033[0;32m[DIF_BOT]\033[0m %s\n' "$*"; }
warn(){ printf '\033[1;33m[AVISO]\033[0m %s\n' "$*"; }
fail(){ printf '\033[0;31m[ERROR]\033[0m %s\n' "$*" >&2; exit 1; }

group_alive(){
  local pgid="$1"
  [[ "$pgid" =~ ^[0-9]+$ ]] || return 1
  ps -eo pgid=,stat= | awk -v g="$pgid" '$1 == g && $2 !~ /^Z/ { found=1 } END { exit(found ? 0 : 1) }'
}

managed_alive(){
  local id="$1" pidfile="$PID_DIR/$1.pid" pgidfile="$PID_DIR/$1.pgid" pid pgid actual
  [[ -s "$pidfile" && -s "$pgidfile" ]] || return 1
  pid="$(cat "$pidfile")"; pgid="$(cat "$pgidfile")"
  [[ "$pid" =~ ^[0-9]+$ && "$pgid" =~ ^[0-9]+$ ]] || return 1
  kill -0 "$pid" 2>/dev/null || return 1
  actual="$(ps -o pgid= -p "$pid" 2>/dev/null | tr -d ' ')"
  [[ "$actual" == "$pgid" ]] && group_alive "$pgid"
}

start_managed(){
  local id="$1" logfile="$2" pidfile="$PID_DIR/$1.pid" pgidfile="$PID_DIR/$1.pgid" supervisorfile="$PID_DIR/$1.supervisor"
  shift 2
  rm -f "$pidfile" "$pgidfile" "$supervisorfile"

  # The child records its OWN PID and process-group ID before exec. Do not
  # save $! from setsid: setsid may fork when the caller is already a group leader.
  setsid --wait bash -c '
    pidfile="$1"; pgidfile="$2"; shift 2
    printf "%s\n" "$$" > "$pidfile"
    ps -o pgid= -p "$$" | tr -d " " > "$pgidfile"
    exec "$@"
  ' _ "$pidfile" "$pgidfile" "$@" > "$logfile" 2>&1 < /dev/null &
  echo "$!" > "$supervisorfile"

  for _ in {1..30}; do
    if [[ -s "$pidfile" && -s "$pgidfile" ]]; then
      local pid
      pid="$(cat "$pidfile")"
      if kill -0 "$pid" 2>/dev/null; then
        info "$id iniciado (PID=$pid, PGID=$(cat "$pgidfile")). Log: $logfile"
        return 0
      fi
    fi
    sleep 0.2
  done

  warn "No se pudo confirmar el proceso $id. Últimas líneas de $logfile:"
  tail -n 50 "$logfile" 2>/dev/null || true
  return 1
}

port_open(){ timeout 1 bash -c "</dev/tcp/127.0.0.1/$1" >/dev/null 2>&1; }

wait_port(){
  local port="$1" limit="$2" label="$3"
  for ((s=1; s<=limit; s++)); do
    if port_open "$port"; then info "$label disponible en puerto $port."; return 0; fi
    if (( s % 5 == 0 )); then info "Esperando $label: ${s}/${limit} s"; fi
    sleep 1
  done
  warn "$label no abrió el puerto $port en ${limit} s. Se conserva el despliegue y sus logs."
  return 1
}

# Serializa solo la operación de arranque.
command -v flock >/dev/null 2>&1 || fail "No está disponible flock."
exec 9>"$PID_DIR/start.lock"
flock -n 9 || fail "Ya hay otro proceso START_DIF_BOT.sh ejecutándose."

set +u
source /opt/ros/jazzy/setup.bash
source "$WORKSPACE/install/setup.bash"
set -u
[[ "${ROS_DISTRO:-}" == jazzy ]] || fail "ROS_DISTRO no es jazzy."

for cmd in ros2 npm curl setsid timeout ps; do command -v "$cmd" >/dev/null 2>&1 || fail "Falta el comando $cmd."; done
[[ -x "$WORKSPACE/web/node_modules/.bin/vite" ]] || fail "Faltan dependencias web. Ejecuta npm ci una sola vez en /ros2_ws/web."

# Detecta procesos administrados anteriores; no borra un PID si aún tiene procesos vivos.
for id in base nav web; do
  if managed_alive "$id"; then fail "$id ya está activo. Ejecuta ./STOP_DIF_BOT.sh antes de iniciar otra instancia."; fi
  pgidfile="$PID_DIR/$id.pgid"
  if [[ -s "$pgidfile" ]] && group_alive "$(cat "$pgidfile")"; then
    fail "Quedó vivo el grupo $id (PGID $(cat "$pgidfile")). Ejecuta ./STOP_DIF_BOT.sh para recuperarlo."
  fi
  rm -f "$PID_DIR/$id.pid" "$PID_DIR/$id.pgid" "$PID_DIR/$id.supervisor"
done

port_open 9090 && fail "El puerto 9090 ya está ocupado. Ejecuta ./STOP_DIF_BOT.sh para limpiar instancias anteriores."
port_open 3000 && fail "El puerto 3000 ya está ocupado. Ejecuta ./STOP_DIF_BOT.sh para limpiar instancias anteriores."

info "ROS 2 Jazzy | ROS_DOMAIN_ID=$ROS_DOMAIN_ID"
info "Arrancando la simulación BASE sin Nav2 (Nav2 tendrá su propio proceso y log)..."
start_managed base "$LOG_DIR/base.log" ros2 launch dif_bot_bringup main.launch.py \
  use_sim_time:=true use_ros2_control:=true launch_navigation:=false

# La base crea rosbridge y los nodos web después de 8 s en main.launch.py.
# La navegación no se usa como condición para abrir la interfaz.
wait_port 9090 15 "Rosbridge" || true
if ! managed_alive base; then
  warn "La base ROS 2/Gazebo terminó durante el arranque. Registro reciente:"
  tail -n 100 "$LOG_DIR/base.log" || true
  fail "No se puede continuar: el proceso principal de la base ya no está activo."
fi

# Levanta primero la web, sin esperar a que Nav2 esté listo.
info "Arrancando la interfaz web..."
start_managed web "$LOG_DIR/web.log" npm --prefix "$WORKSPACE/web" run dev -- --host 0.0.0.0
wait_port 3000 20 "Interfaz web HTTP" || true
if ! managed_alive web; then
  warn "Vite terminó durante el arranque. Registro reciente:"
  tail -n 100 "$LOG_DIR/web.log" || true
  fail "La interfaz web terminó inesperadamente."
fi

# Nav2 se levanta por separado y no bloquea la base ni la web.
info "Arrancando EKF, localización, Nav2 y Mission Server en proceso independiente..."
start_managed nav "$LOG_DIR/navigation.log" ros2 launch dif_bot_navigation navigation.launch.py use_sim_time:=true

sleep 2

for id in base nav web; do
  if ! managed_alive "$id"; then
    warn "El proceso $id terminó durante el arranque. Últimas líneas del log:"
    case "$id" in
      base) tail -n 70 "$LOG_DIR/base.log" || true ;;
      nav) tail -n 70 "$LOG_DIR/navigation.log" || true ;;
      web) tail -n 70 "$LOG_DIR/web.log" || true ;;
    esac
  fi
done

echo
echo "=================================================="
echo "       DIF_BOT OS - SERVICIOS LANZADOS"
echo "=================================================="
echo "Base ROS 2/Gazebo : PID $(cat "$PID_DIR/base.pid" 2>/dev/null || echo N/A)"
echo "Nav2/EKF          : PID $(cat "$PID_DIR/nav.pid" 2>/dev/null || echo N/A)"
echo "Web               : PID $(cat "$PID_DIR/web.pid" 2>/dev/null || echo N/A)"
echo "Interfaz          : http://localhost:3000"
echo "Rosbridge         : ws://localhost:9090"
echo
echo "Logs separados:"
echo "  $LOG_DIR/base.log"
echo "  $LOG_DIR/navigation.log"
echo "  $LOG_DIR/web.log"
echo
echo "La navegación se valida aparte; un fallo de Nav2 ya no bloquea ni derriba la base o la web."
echo "Para detener el sistema completo: ./STOP_DIF_BOT.sh"
echo "Para comprobar componentes: ./DIAGNOSTIC_DIF_BOT.sh"
