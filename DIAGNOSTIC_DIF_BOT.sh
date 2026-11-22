#!/usr/bin/env bash
set -uo pipefail
WORKSPACE=/ros2_ws
PID_DIR=/tmp/dif_bot_os
export ROS_DOMAIN_ID="${ROS_DOMAIN_ID:-42}"
set +u
source /opt/ros/jazzy/setup.bash
source "$WORKSPACE/install/setup.bash"
set -u

PASS=0; FAIL=0; CORE_FAIL=0; NAV_FAIL=0; WEB_FAIL=0
ok(){ echo "[OK] $*"; PASS=$((PASS+1)); }
bad(){ echo "[FALLO] $*"; FAIL=$((FAIL+1)); }
check_pid(){
  local id="$1" expected="$2" pidfile="$PID_DIR/$1.pid" pgidfile="$PID_DIR/$1.pgid" pid pgid actual cmd
  [[ -s "$pidfile" && -s "$pgidfile" ]] || return 1
  pid="$(cat "$pidfile")"; pgid="$(cat "$pgidfile")"
  [[ "$pid" =~ ^[0-9]+$ && "$pgid" =~ ^[0-9]+$ ]] || return 1
  kill -0 "$pid" 2>/dev/null || return 1
  actual="$(ps -o pgid= -p "$pid" 2>/dev/null | tr -d ' ')"
  [[ "$actual" == "$pgid" ]] || return 1
  cmd="$(ps -p "$pid" -o args= 2>/dev/null || true)"
  [[ "$cmd" == *"$expected"* ]]
}
check_node(){ grep -Fxq "$1" <<< "$NODES"; }
check_topic(){ grep -Fxq "$1" <<< "$TOPICS"; }
check_service(){ grep -Fxq "$1" <<< "$SERVICES"; }
check_action(){ grep -Fxq "$1" <<< "$ACTIONS"; }

check_group(){
  local group="$1" desc="$2" category="$3"
  if check_pid "$group" "$desc"; then
    ok "Proceso $group"
  else
    bad "Proceso $group"
    case "$category" in
      CORE) CORE_FAIL=$((CORE_FAIL+1)) ;;
      NAV) NAV_FAIL=$((NAV_FAIL+1)) ;;
      WEB) WEB_FAIL=$((WEB_FAIL+1)) ;;
    esac
  fi
}

echo
echo "=================================================="
echo "        DIF_BOT OS - DIAGNÓSTICO RÁPIDO"
echo "=================================================="
echo "ROS_DOMAIN_ID=$ROS_DOMAIN_ID"

check_group base 'ros2 launch dif_bot_bringup main.launch.py' CORE
check_group nav 'ros2 launch dif_bot_navigation navigation.launch.py' NAV
check_group web 'npm run dev' WEB

# Una única consulta al grafo. No se repite durante minutos ni arranca bucles de espera.
NODES="$(timeout 8 ros2 node list 2>/dev/null || true)"
TOPICS="$(timeout 6 ros2 topic list 2>/dev/null || true)"
SERVICES="$(timeout 6 ros2 service list 2>/dev/null || true)"
ACTIONS="$(timeout 6 ros2 action list 2>/dev/null || true)"

for node in /robot_state_publisher /twist_mux /rosbridge_websocket /web_relay_node /robot_pose_node /goal_bridge_node; do
  if check_node "$node"; then ok "Nodo base $node"; else bad "Nodo base $node"; CORE_FAIL=$((CORE_FAIL+1)); fi
done

for node in /ekf_filter_node /autonomous_mission_server /map_server /amcl /controller_server /planner_server /behavior_server /bt_navigator; do
  if check_node "$node"; then ok "Nodo navegación $node"; else bad "Nodo navegación $node"; NAV_FAIL=$((NAV_FAIL+1)); fi
done

for topic in /clock /tf /scan /imu/data /cmd_vel /odom_raw /odom_filtered; do
  if check_topic "$topic"; then ok "Tópico $topic"; else bad "Tópico $topic"; CORE_FAIL=$((CORE_FAIL+1)); fi
done

if check_service /start_autonomous_mission; then ok 'Servicio /start_autonomous_mission'; else bad 'Servicio /start_autonomous_mission'; NAV_FAIL=$((NAV_FAIL+1)); fi
if check_service /dif_bot/stop; then ok 'Servicio /dif_bot/stop'; else bad 'Servicio /dif_bot/stop'; CORE_FAIL=$((CORE_FAIL+1)); fi
if check_action /navigate_to_pose; then ok 'Acción /navigate_to_pose'; else bad 'Acción /navigate_to_pose'; NAV_FAIL=$((NAV_FAIL+1)); fi

if timeout 2 bash -c '</dev/tcp/127.0.0.1/9090' >/dev/null 2>&1; then ok 'Rosbridge TCP 9090'; else bad 'Rosbridge TCP 9090'; CORE_FAIL=$((CORE_FAIL+1)); fi
if curl -fsS --max-time 3 http://127.0.0.1:3000/ >/dev/null 2>&1; then ok 'Web HTTP 3000'; else bad 'Web HTTP 3000'; WEB_FAIL=$((WEB_FAIL+1)); fi

echo
echo "Correctas=$PASS | Fallidas=$FAIL"
if (( CORE_FAIL == 0 && WEB_FAIL == 0 && NAV_FAIL == 0 )); then
  echo 'ESTADO: BASE + WEB + NAVEGACIÓN: NODOS Y SERVICIOS DETECTADOS.'
  echo 'Nota: esto no sustituye una prueba física de movimiento ni de misión completa.'
  exit 0
elif (( CORE_FAIL == 0 && WEB_FAIL == 0 )); then
  echo 'ESTADO: BASE Y WEB DISPONIBLES; NAVEGACIÓN PENDIENTE.'
  echo 'Consulta /ros2_ws/logs/navigation.log; la interfaz permanece levantada.'
  exit 2
else
  echo 'ESTADO: HAY FALLOS EN LA BASE O EN LA INTERFAZ.'
  echo 'Logs: /ros2_ws/logs/base.log, navigation.log, web.log'
  exit 1
fi
