#!/usr/bin/env bash
set -Eeuo pipefail
PID_DIR=/tmp/dif_bot_os

info(){ echo "[STOP] $*"; }
group_alive(){
  local pgid="$1"
  [[ "$pgid" =~ ^[0-9]+$ ]] || return 1
  ps -eo pgid=,stat= | awk -v g="$pgid" '$1 == g && $2 !~ /^Z/ { found=1 } END { exit(found ? 0 : 1) }'
}

stop_group(){
  local id="$1" pidfile="$PID_DIR/$1.pid" pgidfile="$PID_DIR/$1.pgid" supervisorfile="$PID_DIR/$1.supervisor" pgid supervisor
  if [[ ! -s "$pgidfile" ]]; then
    info "$id: sin grupo registrado."
    rm -f "$pidfile" "$supervisorfile"
    return 0
  fi
  pgid="$(cat "$pgidfile")"
  if [[ ! "$pgid" =~ ^[0-9]+$ ]] || ! group_alive "$pgid"; then
    info "$id: grupo ya detenido u obsoleto."
  else
    info "Enviando SIGINT al grupo $id (PGID $pgid)..."
    kill -INT -- "-$pgid" 2>/dev/null || true
    for _ in {1..12}; do group_alive "$pgid" || break; sleep 1; done
    if group_alive "$pgid"; then
      info "Enviando SIGTERM a $id..."
      kill -TERM -- "-$pgid" 2>/dev/null || true
      for _ in {1..5}; do group_alive "$pgid" || break; sleep 1; done
    fi
    if group_alive "$pgid"; then
      info "Enviando SIGKILL a $id..."
      kill -KILL -- "-$pgid" 2>/dev/null || true
      sleep 1
    fi
  fi
  supervisor="$(cat "$supervisorfile" 2>/dev/null || true)"
  if [[ "$supervisor" =~ ^[0-9]+$ ]]; then kill -TERM "$supervisor" 2>/dev/null || true; fi
  if ! group_alive "$pgid"; then rm -f "$pidfile" "$pgidfile" "$supervisorfile"; else info "ATENCIÓN: el grupo $id sigue activo; se conserva su registro."; fi
}

echo
echo "=================================================="
echo "          DIF_BOT OS - DETENER SISTEMA"
echo "=================================================="
# Orden: navegación, web y finalmente simulación base.
stop_group nav
stop_group web
stop_group base

# Recupera procesos heredados de versiones anteriores que no tenían PID/PGID fiables.
# Solo busca ejecutables y nodos propios de este proyecto; nunca mata el grupo de esta terminal.
python3 - <<'PY'
import os, signal, time
current_pgid = os.getpgrp()
markers = (
    'ros2 launch dif_bot_bringup main.launch.py',
    'ros2 launch dif_bot_navigation navigation.launch.py',
    'my_world.sdf',
    '/opt/ros/jazzy/lib/ros_gz_sim/create',
    '/opt/ros/jazzy/lib/robot_state_publisher/robot_state_publisher',
    '/opt/ros/jazzy/lib/ros_gz_bridge/parameter_bridge',
    'cmd_vel_stamper',
    'odometry_relay',
    'web_relay_node',
    'robot_pose_node',
    'goal_bridge_node',
    '/opt/ros/jazzy/lib/twist_mux/twist_mux',
    '/opt/ros/jazzy/lib/rosbridge_server/rosbridge_websocket',
    '/opt/ros/jazzy/lib/robot_localization/ekf_node',
    '/opt/ros/jazzy/lib/nav2_map_server/map_server',
    '/opt/ros/jazzy/lib/nav2_amcl/amcl',
    '/opt/ros/jazzy/lib/nav2_controller/controller_server',
    '/opt/ros/jazzy/lib/nav2_planner/planner_server',
    '/opt/ros/jazzy/lib/nav2_behaviors/behavior_server',
    '/opt/ros/jazzy/lib/nav2_bt_navigator/bt_navigator',
    '/opt/ros/jazzy/lib/controller_manager/spawner',
    '/ros2_ws/web/node_modules/.bin/vite',
    'npm run dev -- --host 0.0.0.0',
)
groups, individual = set(), set()
for entry in os.listdir('/proc'):
    if not entry.isdigit():
        continue
    pid = int(entry)
    if pid in (os.getpid(), os.getppid()):
        continue
    try:
        raw = open(f'/proc/{pid}/cmdline', 'rb').read().replace(b'\0', b' ').decode(errors='replace')
        if not raw or not any(m in raw for m in markers):
            continue
        pgid = os.getpgid(pid)
        if pgid > 1 and pgid != current_pgid:
            groups.add(pgid)
        else:
            individual.add(pid)
    except (FileNotFoundError, ProcessLookupError, PermissionError):
        pass
for pgid in sorted(groups):
    try: os.killpg(pgid, signal.SIGINT)
    except ProcessLookupError: pass
for pid in sorted(individual):
    try: os.kill(pid, signal.SIGINT)
    except ProcessLookupError: pass
if groups or individual:
    print(f'[STOP] Recuperación heredada: grupos={sorted(groups)}, procesos={sorted(individual)}')
    time.sleep(3)
    for pgid in groups:
        try: os.killpg(pgid, signal.SIGTERM)
        except ProcessLookupError: pass
    for pid in individual:
        try: os.kill(pid, signal.SIGTERM)
        except ProcessLookupError: pass
    time.sleep(2)
    for pgid in groups:
        try: os.killpg(pgid, signal.SIGKILL)
        except ProcessLookupError: pass
    for pid in individual:
        try: os.kill(pid, signal.SIGKILL)
        except ProcessLookupError: pass
else:
    print('[STOP] No se encontraron procesos heredados del proyecto.')
PY

# Detiene solo el caché de descubrimiento de ROS 2; no es un nodo del robot.
if [[ -f /opt/ros/jazzy/setup.bash ]]; then
  set +u
  source /opt/ros/jazzy/setup.bash
  set -u
  ROS_DOMAIN_ID="${ROS_DOMAIN_ID:-42}" timeout 5 ros2 daemon stop >/dev/null 2>&1 || true
fi

# No se borran a ciegas los registros de grupos que aún sigan vivos.
for id in nav web base; do
  pgidfile="$PID_DIR/$id.pgid"
  if [[ ! -s "$pgidfile" ]] || ! group_alive "$(cat "$pgidfile")"; then
    rm -f "$PID_DIR/$id.pid" "$PID_DIR/$id.pgid" "$PID_DIR/$id.supervisor"
  else
    echo "[AVISO] Se conserva el registro de $id porque su grupo aún sigue activo."
  fi
done

echo "[OK] Solicitud de parada y recuperación finalizada."
