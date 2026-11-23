#!/usr/bin/env bash
# Runtime diagnostic for the complete DIF_BOT command, odometry and Nav2 chains.
set -uo pipefail
WORKSPACE=/ros2_ws
PID_DIR=/tmp/dif_bot_os
export ROS_DOMAIN_ID="${ROS_DOMAIN_ID:-42}"
export RCUTILS_COLORIZED_OUTPUT=0
set +u
source /opt/ros/jazzy/setup.bash
source "$WORKSPACE/install/setup.bash"
set -u

PASS=0
FAIL=0
NODES="$(timeout 10 ros2 node list 2>/dev/null || true)"
TOPICS="$(timeout 8 ros2 topic list 2>/dev/null || true)"
SERVICES="$(timeout 8 ros2 service list 2>/dev/null || true)"
ACTIONS="$(timeout 8 ros2 action list 2>/dev/null || true)"

ok(){ echo "[OK] $*"; PASS=$((PASS+1)); }
bad(){ echo "[FALLO] $*"; FAIL=$((FAIL+1)); }
has_line(){ grep -Fxq "$1" <<<"$2"; }

check_process(){
  local id="$1" expected="$2" pidfile="$PID_DIR/$1.pid" pgidfile="$PID_DIR/$1.pgid" pid pgid actual cmd
  if [[ ! -s "$pidfile" || ! -s "$pgidfile" ]]; then bad "Proceso $id: sin PID/PGID"; return; fi
  pid="$(cat "$pidfile")"; pgid="$(cat "$pgidfile")"
  if [[ ! "$pid" =~ ^[0-9]+$ || ! "$pgid" =~ ^[0-9]+$ ]] || ! kill -0 "$pid" 2>/dev/null; then
    bad "Proceso $id: PID no activo"; return
  fi
  actual="$(ps -o pgid= -p "$pid" 2>/dev/null | tr -d ' ')"
  cmd="$(ps -p "$pid" -o args= 2>/dev/null || true)"
  if [[ "$actual" == "$pgid" && "$cmd" == *"$expected"* ]]; then ok "Proceso supervisor $id activo"
  else bad "Proceso supervisor $id incoherente"; fi
}

capture(){
  local label="$1"; shift
  echo
  echo "----- $label -----"
  timeout 8 "$@" 2>&1 || echo "[INFO] Consulta terminada sin resultado o excedió 8 s."
}

echo
echo "============================================================"
echo "       DIF_BOT OS — DIAGNÓSTICO DE CADENAS EN EJECUCIÓN"
echo "============================================================"
echo "Fecha UTC: $(date -u +%Y-%m-%dT%H:%M:%SZ)"
echo "ROS_DISTRO=${ROS_DISTRO:-N/D} | ROS_DOMAIN_ID=$ROS_DOMAIN_ID | RMW_IMPLEMENTATION=${RMW_IMPLEMENTATION:-N/D}"
echo

for entry in "base|ros2 launch dif_bot_bringup main.launch.py" \
             "nav|ros2 launch dif_bot_navigation navigation.launch.py" \
             "web|npm run dev"; do
  IFS='|' read -r id expected <<<"$entry"
  check_process "$id" "$expected"
done

echo
echo "----- NODOS ROS 2 -----"
printf '%s\n' "$NODES"
for node in /robot_state_publisher /twist_mux /cmd_vel_stamper /odometry_relay \
            /rosbridge_websocket /web_relay_node /robot_pose_node /goal_bridge_node; do
  if has_line "$node" "$NODES"; then ok "Nodo $node"; else bad "Nodo ausente $node"; fi
done
for node in /ekf_filter_node /map_server /amcl /controller_server /planner_server \
            /behavior_server /bt_navigator /autonomous_mission_server; do
  if has_line "$node" "$NODES"; then ok "Nodo navegación $node"; else bad "Nodo navegación ausente $node"; fi
done

echo
echo "----- TÓPICOS CLAVE -----"
printf '%s\n' "$TOPICS"
for topic in /cmd_vel_web /cmd_vel /diff_drive_controller/cmd_vel \
             /cmd_vel_nav /odom_raw /odom_filtered /scan /imu/data /clock \
             /dif_bot/web/robot_pose /dif_bot/web/nav_status /amcl_pose /map; do
  if has_line "$topic" "$TOPICS"; then ok "Tópico $topic"; else bad "Tópico ausente $topic"; fi
done

echo
echo "----- CADENA DE MANDO: PUBLICADORES / SUSCRIPTORES -----"
for topic in /cmd_vel_web /cmd_vel /diff_drive_controller/cmd_vel /cmd_vel_nav; do
  capture "ros2 topic info -v $topic" ros2 topic info -v "$topic"
done

echo
echo "----- CONTROLADORES ros2_control -----"
capture "ros2 control list_controllers" ros2 control list_controllers
capture "ros2 control list_hardware_components" ros2 control list_hardware_components

echo
echo "----- ACCIÓN, SERVICIOS Y LIFECYCLE -----"
echo "Acciones:"
printf '%s\n' "$ACTIONS"
if has_line /navigate_to_pose "$ACTIONS"; then ok "Acción /navigate_to_pose disponible"; else bad "Acción /navigate_to_pose ausente"; fi
for service in /start_autonomous_mission /dif_bot/stop /amcl/get_state \
               /map_server/get_state /controller_server/get_state \
               /planner_server/get_state /behavior_server/get_state \
               /bt_navigator/get_state; do
  if has_line "$service" "$SERVICES"; then ok "Servicio $service"; else bad "Servicio ausente $service"; fi
done
for node in map_server amcl controller_server planner_server behavior_server bt_navigator; do
  capture "Lifecycle $node" ros2 lifecycle get "/$node"
done

echo
echo "----- MUESTRAS DE SENSORES, ODOMETRÍA Y LOCALIZACIÓN -----"
for topic in /odom_raw /odom_filtered /amcl_pose /dif_bot/web/robot_pose /scan; do
  capture "Primer mensaje de $topic" ros2 topic echo "$topic" --once
done

echo
echo "----- PARÁMETROS REALES DE NAV2 -----"
if has_line /controller_server "$NODES"; then
  for parameter in progress_checker.plugin progress_checker.required_movement_radius \
                   progress_checker.required_movement_angle progress_checker.movement_time_allowance \
                   goal_checker.xy_goal_tolerance goal_checker.yaw_goal_tolerance \
                   FollowPath.max_vel_theta FollowPath.acc_lim_theta \
                   FollowPath.decel_lim_theta FollowPath.vtheta_samples; do
    value="$(timeout 4 ros2 param get /controller_server "$parameter" 2>&1 || true)"
    printf '[NAV2 PARAM] %s = %s\n' "$parameter" "$value"
  done
else
  bad "No se pueden consultar parámetros: /controller_server ausente."
fi

echo
echo "----- CONECTIVIDAD LOCAL -----"
if timeout 2 bash -c '</dev/tcp/127.0.0.1/9090' >/dev/null 2>&1; then ok "TCP rosbridge 9090"; else bad "TCP rosbridge 9090"; fi
if curl -fsS --max-time 3 http://127.0.0.1:3000/ >/dev/null 2>&1; then ok "HTTP web 3000"; else bad "HTTP web 3000"; fi

echo
# Runtime files: /ros2_ws/logs/base.log, /ros2_ws/logs/navigation.log, /ros2_ws/logs/web.log.
# Include progress/oscillation diagnostics as well as controller and lifecycle faults.
echo "----- LOGS RECIENTES -----"
for name in base navigation web; do
  file="$WORKSPACE/logs/$name.log"
  echo
  echo "### $file"
  if [[ -s "$file" ]]; then
    grep -Ei 'error|fatal|exception|abort|failed|not active|lifecycle|bond|timeout|transform|costmap|progress|oscillat|controller|cmd_vel|serial|disconnect' "$file" | tail -n 100 || tail -n 60 "$file"
    echo "--- últimas 35 líneas completas ---"
    tail -n 35 "$file"
  else
    echo "[FALLO] Log inexistente o vacío."
  fi
done

echo
echo "============================================================"
echo "RESULTADO DIAGNÓSTICO: Correctas=$PASS | Fallidas=$FAIL"
if (( FAIL == 0 )); then
  echo "ESTADO: CADENAS ROS DETECTADAS. Aún requiere prueba de movimiento y navegación."
  exit 0
else
  echo "ESTADO: HAY COMPONENTES O CADENAS SIN VERIFICAR. No declarar funcionalidad."
  exit 2
fi
