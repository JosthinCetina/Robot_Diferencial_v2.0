# Plan de pruebas e integración — dif_bot OS v2.0 (Jazzy)

> **Estado de ejecución actualizado — 22 de noviembre de 2026 (hora Colombia).**
>
> - Despliegue incremental y arranque de base/controladores: validado.
> - Teleoperación web sostenida: validada por prueba funcional del usuario.
> - Objetivo web `[1, 1, DEFAULT]`: `NavigateToPose` terminó `SUCCEEDED`.
> - Objetivo web `[1, 1, 5°]`: `NavigateToPose` terminó `SUCCEEDED`; valida orientación final en la misma posición XY, no un recorrido largo.
> - Los timeouts de acciones internas del BT Navigator se corrigieron de 20 ms a 1000 ms; `default_cancel_timeout` también quedó explícito en 1000 ms.
> - El registro de una ejecución anterior mostró TF con 520 ms de antigüedad y errores intermitentes de frecuencia del EKF; la cadena temporal aún no está aprobada.
> - Misión secuencial, SLAM, convergencia AMCL y comparación entre modos de tracción todavía no tienen evidencia funcional.
>
> No declarar terminada una fase por compilación. Esta sección registra pruebas reportadas; las fases pendientes requieren evidencia de ejecución.

Este documento es la secuencia de aceptación técnica. Marca cada resultado con fecha, modo de control y evidencia (captura, log o bag). No se debe declarar una fase aprobada por el mero hecho de compilar.

## Fase 0 — Entorno aislado y reproducible

Dentro del contenedor:

```bash
printenv ROS_DISTRO                 # debe mostrar jazzy
ros2 doctor --report
which gz && gz sim --versions
which colcon
```

Criterio: ROS_DISTRO es `jazzy`; Gazebo Sim identifica la familia Harmonic/Gazebo Sim 8; no hay overlays de otro ROS distro (`echo $AMENT_PREFIX_PATH`).

## Fase 1 — Dependencias, Xacro y compilación

```bash
cd /ros2_ws
source /opt/ros/jazzy/setup.bash
rosdep install --from-paths src --ignore-src -r -y --rosdistro jazzy
MAKEFLAGS="-j1" colcon build --symlink-install --executor sequential --event-handlers console_direct+
source install/setup.bash
ros2 pkg list | grep -E 'dif_bot|gz_ros2_control|diff_drive_controller|robot_localization|nav2'
```

Criterios: `colcon` termina con 0 errores; aparecen los seis paquetes; xacro genera URDF en cada modo:

```bash
xacro src/dif_bot_description/urdf/dif_bot_description.urdf.xacro use_ros2_control:=true > /tmp/dif_bot_ros2_control.urdf
xacro src/dif_bot_description/urdf/dif_bot_description.urdf.xacro use_ros2_control:=false > /tmp/dif_bot_gz_native.urdf
check_urdf /tmp/dif_bot_ros2_control.urdf
check_urdf /tmp/dif_bot_gz_native.urdf
```

## Fase 2 — Simulación + articulaciones

Terminal A:

```bash
ros2 launch dif_bot_gazebo gazebo.launch.py use_sim_time:=true use_ros2_control:=true
```

Terminal B:

```bash
source /opt/ros/jazzy/setup.bash && source /ros2_ws/install/setup.bash
ros2 control list_controllers
ros2 control list_controller_types
ros2 topic echo /joint_states --once
# El log de create debe contener: Entity creation successful.
grep -F 'Entity creation successful.' /ros2_ws/logs/base.log
```

Criterios para modo ros2_control: el log de `ros_gz_sim/create` confirma `Entity creation successful.`; `joint_state_broadcaster` y `diff_drive_controller` están `active`; `/joint_states` contiene `left_wheel_joint` y `right_wheel_joint`. Gazebo muestra el robot y el mundo. El lanzamiento fija el mundo `dif_bot_world` y no usa una espera temporal fija para insertar el modelo.

Prueba equivalente del modo nativo: detener toda la simulación anterior y arrancar con `use_ros2_control:=false`. No deben aparecer spawners ni controller_manager del robot; sí debe verse Gazebo ejecutando el sistema DiffDrive. Verifica `/odom_raw` y comando `/cmd_vel` como en la fase siguiente.

## Fase 3 — Sensores y puentes ROS-Gazebo

```bash
ros2 topic list | sort
ros2 topic echo /scan --once
ros2 topic echo /imu/data --once
ros2 topic echo /camera/image --once
ros2 topic hz /clock
ros2 topic hz /scan
ros2 topic hz /imu/data
```

Criterios: `/scan` es `sensor_msgs/msg/LaserScan` (aprox. 10 Hz), `/imu/data` es `sensor_msgs/msg/Imu` (aprox. 100 Hz), la cámara publica `sensor_msgs/msg/Image`. Comprueba que `header.frame_id` corresponde a `laser_frame`, `imu_link` y `camera_link_optical` (si el frame de cámara no coincide, corregir el `<gz_frame_id>` de la definición de sensor). `ros_gz_bridge` no debe reportar tipos incompatibles.

## Fase 4 — TF y EKF

Con la simulación en marcha y navegación iniciada:

```bash
ros2 topic echo /odom_raw --once
ros2 topic echo /odom_filtered --once
ros2 run tf2_ros tf2_echo odom base_footprint
ros2 run tf2_tools view_frames
```

Criterios: `/odom_raw` y `/odom_filtered` publican; `odom -> base_footprint` existe y evoluciona; hay exactamente un publicador para esa transformación (EKF). La odometría filtrada no contiene NaN/Inf. `/imu/data` y `/odom_raw` tienen stamps de simulación coherentes con `/clock`.

## Fase 5 — Control de movimiento y paro lógico

Con el robot en zona despejada, probar primero velocidades bajas:

```bash
ros2 topic pub --once /cmd_vel_web geometry_msgs/msg/Twist   "{linear: {x: 0.08}, angular: {z: 0.0}}"
ros2 topic echo /odom_filtered --once
ros2 topic pub --once /cmd_vel_web geometry_msgs/msg/Twist "{}"
```

Después probar giro (`angular.z: 0.2`). Para probar el paro lógico global, inicia una meta Nav2 o una misión y ejecuta `ros2 service call /dif_bot/stop std_srvs/srv/Trigger "{}"`; confirma que el objetivo activo se cancela y el robot se detiene. Comprueba que el robot avanza/gira en el sentido esperado y la odometría responde. Para teleop teclado:

```bash
ros2 run dif_bot_control teleop_keyboard
```

Criterios: prioridad de teleop sobre Nav2, timeout de comandos, publicación de velocidad cero, límites de velocidad y ausencia de movimiento residual. Prueba explícitamente desconexión de web y pérdida de comando: el controlador debe detenerse al vencer el timeout. El botón STOP de la UI es un paro lógico por software; no es un paro de emergencia certificado ni sustituye un E-stop físico cableado.

## Fase 6 — SLAM o mapa estático / AMCL

Para construir/actualizar mapa, no arranques Nav2/AMCL en paralelo. En una primera terminal inicia la simulación y los puentes, pero deja desactivada la navegación:

```bash
ros2 launch dif_bot_bringup main.launch.py use_sim_time:=true launch_navigation:=false
```

Con la base en ejecución y una sola instancia del EKF, inicia SLAM Toolbox. El launch de SLAM inicia EKF por defecto para crear `odom -> base_footprint`:

```bash
# slam.launch.py inicia EKF de forma predeterminada.
ros2 launch dif_bot_navigation slam.launch.py use_sim_time:=true
```

Conducir lentamente y guardar el mapa con `nav2_map_server`/`map_saver_cli` (según la CLI instalada):

```bash
./scripts/save_map.sh generated_map
```

Para navegación sobre el mapa estático, relanzar el sistema con Nav2 y validar `/map`, AMCL y la pose inicial. En RViz2 establece `Initial Pose` si no hay localización válida.

Criterios: mapa consistente con el mundo; AMCL mantiene partículas y pose; TF `map -> odom` existe; no hay saltos de localización ni offsets sistemáticos.

## Fase 7 — Navegación Nav2 a una meta individual

```bash
ros2 action list | grep navigate_to_pose
ros2 lifecycle nodes
ros2 topic echo /cmd_vel_nav
```

Enviar una meta desde RViz2 (Nav2 Goal) o el panel web. Empezar con un objetivo corto y visible, en un área libre. Comprobar `/plan`, `/local_costmap/costmap` y `/global_costmap/costmap`.

Criterios: Nav2 planifica, sigue, evita obstáculos y publica cero velocidad al finalizar; no tiene errores de lifecycle, transformaciones o costmaps.

## Fase 8 — Misión secuencial

Primero editar `config/waypoints.yaml` con 2 o 3 puntos conocidos que estén en celdas libres y alcanzables. Después:

```bash
ros2 service list | grep start_autonomous_mission
ros2 service call /start_autonomous_mission std_srvs/srv/Trigger "{}"
ros2 topic echo /dif_bot/mission/progress
```

Criterios: cada punto se ejecuta en orden; el mensaje avanza; una meta inalcanzable causa estado FALLIDA y no se marca como misión completada; no se aceptan dos misiones simultáneas.

## Fase 9 — Interfaz web / rosbridge

En terminal independiente, para desarrollo usar Vite dev; para probar el despliegue normal, construir y servir el bundle de producción:

```bash
cd /ros2_ws/web
npm ci
npm run build
npm run preview -- --host 0.0.0.0 --port 3000
```

Abrir `http://localhost:3000`. Verificar:
- Estado WebSocket conectado.
- LiDAR y telemetría se actualizan.
- WASD o botones envían comando de velocidad.
- STOP solicita cancelar todos los objetivos `NavigateToPose` y publica velocidades cero en las entradas manual/web del mux (paro lógico; no es E-stop físico).
- Meta individual se envía a Nav2.
- Botón de misión invoca servicio y refleja progreso.

Criterios: no hay errores de consola; no hay errores de rosbridge; si se desconecta rosbridge, la UI se identifica como desconectada y el robot detiene movimiento por timeout.

## Fase 10 — Comparación de modos

Repetir fases 2–8 con `use_ros2_control:=true` y luego `false`, no simultáneamente. Registrar:
- controladores activos y tasa de `/joint_states` en el modo ros2_control;
- topic de odometría bruta y frecuencia en ambos;
- respuesta a comando lineal/angular;
- error de odometría en un desplazamiento y giro de referencia;
- estabilidad de EKF y Nav2;
- CPU/RAM de Docker.

En modo ros2_control, odometría nace en `diff_drive_controller`; modo nativo, nace en Gazebo Sim DiffDrive. En los dos debe normalizarse a `/odom_raw` y el EKF publica `/odom_filtered`.

## Fase 11 — Regresión y evidencia

```bash
python3 -m pytest -q /ros2_ws/tests
colcon test --event-handlers console_direct+
colcon test-result --verbose
ros2 bag record -o /ros2_ws/validation_bag /clock /scan /imu/data /odom_raw /odom_filtered /tf /tf_static /cmd_vel /cmd_vel_nav
```

Evidencia recomendada: video del mundo/robot, terminal de controladores, RViz2 con TF/mapa/costmaps, panel web, logs de la misión y un rosbag de navegación completa.


## Fase 7A — Orientación final y progreso angular

El panel web acepta X e Y y un yaw final opcional en grados. Si el campo yaw queda vacío, conserva la orientación del robot al enviar la meta; no debe imponer yaw=0 por omisión.

Con una meta XY cercana, verificar que:
- `/dif_bot/web/goal_pose` contiene un cuaternión normalizado y un yaw coherente con la selección de la interfaz.
- `controller_server` utiliza `nav2_controller::PoseProgressChecker`.
- `required_movement_angle` registra la rotación en el sitio como progreso.
- Cuando el robot entra en la ventana XY pero tiene error angular, DWB sigue publicando `angular.z` en `/cmd_vel_nav` hasta cumplir `yaw_goal_tolerance`.
- La acción termina `SUCCEEDED`; un `ABORTED` no se reinterpreta como éxito únicamente por estar dentro de XY.

Parámetros de referencia: XY 0,05 m, yaw 0,10 rad, radio de progreso 0,08 m, progreso angular 0,05 rad y allowance 30 s.


## Fase 1A — Teleoperación sostenida desde web

- Mantener pulsada una tecla W/A/S/D o uno de los botones.
- Confirmar publicación de `/cmd_vel_web` a 10 Hz mientras se mantiene el control.
- Soltar la tecla/botón y confirmar que la UI publica Twist cero.
- Cambiar de ventana o perder el foco y confirmar que se detiene el comando sostenido.
- Verificar la cadena `/cmd_vel_web -> twist_mux -> /cmd_vel -> cmd_vel_stamper -> /diff_drive_controller/cmd_vel`.
- El timeout del mux sigue siendo 0,5 s; la UI debe refrescar el comando mientras el control está activo.

## Fase 3A — SLAM con EKF y guardado del mapa

- Iniciar base con `launch_navigation:=false`.
- Ejecutar `ros2 launch dif_bot_navigation slam.launch.py use_sim_time:=true`; EKF se inicia por defecto.
- Explorar lentamente y validar `/scan`, `/map` y TF.
- Guardar usando `./scripts/save_map.sh [nombre]` y comprobar YAML/PGM en `src/dif_bot_navigation/maps/`.
- No ejecutar SLAM y AMCL simultáneamente.

## Fases 4 y 5 — RViz2, AMCL y objetivos manuales

- Con Nav2 activo, ejecutar `ros2 launch dif_bot_navigation rviz.launch.py use_sim_time:=true`.
- Confirmar frame fijo `map`, mapa, RobotModel, TF, LiDAR y nube de partículas AMCL.
- Usar 2D Pose Estimate; comprobar convergencia de AMCL y TF `map -> odom`.
- Usar Nav2 GoalTool para enviar una meta manual; observar plan global/local, costmaps y estado final de la acción.
- Repetir desde una pose inicial incorrecta y observar recuperación de AMCL.

## Rendimiento WSL2

El perfil aligerado conserva IMU 100 Hz y LiDAR 10 Hz; reduce cámara a 320×240/5 Hz, apaga la visualización de rayos LiDAR y usa paso de física 2 ms (500 Hz). Deben validarse movimiento y EKF con esos valores; reducir carga no reemplaza la prueba de estabilidad.
