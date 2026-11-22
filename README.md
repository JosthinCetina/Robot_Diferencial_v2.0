# dif_bot OS v2.0 — ROS 2 Jazzy + Gazebo Harmonic

Proyecto de robot diferencial simulado con control dual, fusión sensorial, SLAM, AMCL, Nav2, misiones secuenciales y panel web. El entorno se separa en una imagen Docker y un volumen persistente dedicados al proyecto.

Repositorio de desarrollo: **[JosthinCetina/Robot_Diferencial_v2.0](https://github.com/JosthinCetina/Robot_Diferencial_v2.0)**.

## Arquitectura

- ROS 2 Jazzy / Ubuntu 24.04 / Gazebo Harmonic.
- Gazebo Sim y \`ros_gz_bridge\`: sensores \`/scan\`, \`/imu/data\`, \`/camera/image\`.
- Modo principal (\`use_ros2_control:=true\`): URDF \`<ros2_control>\`, \`gz_ros2_control/GazeboSimSystem\`, \`controller_manager\`, \`joint_state_broadcaster\` y \`diff_drive_controller\`.
- Modo comparativo (\`use_ros2_control:=false\`): plugin DiffDrive nativo de Gazebo Sim, sin \`ros2_control\`.
- Ambos modos normalizan la odometría bruta en \`/odom_raw\`; el EKF publica \`/odom_filtered\` y la única TF \`odom -> base_footprint\`.
- \`twist_mux\` arbitra teclado/web/control de pose/Nav2 con prioridades y timeout.
- Nav2: AMCL, NavFn, DWB y Behavior Server; SLAM Toolbox para generar mapas.
- Misión Python mediante \`nav2_simple_commander\`, servicio \`/start_autonomous_mission\` y waypoints YAML.
- React/Vite/roslibjs vía rosbridge WebSocket \`9090\`; interfaz web en \`3000\`.

## 1. Actualizar el repositorio existente

Este proyecto ya está asociado a \`JosthinCetina/Robot_Diferencial_v2.0\`. **No se debe crear un repositorio nuevo** para publicar sus actualizaciones.

En la raíz del repositorio, después de revisar los cambios locales:

\`\`\`bash
./scripts/publish_github.sh --dry-run
./scripts/publish_github.sh
\`\`\`

El script valida el remoto y la rama \`main\`, comprueba que el historial local incluya el último commit remoto, respeta \`.gitignore\`, valida el diff y publica en el repositorio existente. Nunca crea otro repositorio ni sobrescribe el historial remoto.

No incluyas tokens, claves, archivos \`.env\`, bolsas ROS ni logs en Git. \`.gitignore\` excluye artefactos de ejecución y diagnósticos locales.

## 2. Descargarlo y ejecutarlo en Docker

Para clonar el repositorio público en WSL2 desde una carpeta que contenga \`docker-clone-run.sh\`:

\`\`\`bash
./docker-clone-run.sh https://github.com/JosthinCetina/Robot_Diferencial_v2.0.git main
\`\`\`

El script construye la imagen \`dif-bot-os:jazzy\`, crea el volumen persistente \`difbot_jazzy_ws\`, clona el repositorio dentro de \`/ros2_ws\` y abre el contenedor \`dif-bot-os-jazzy\`. El volumen conserva el workspace al cerrar el contenedor. Al volver a ejecutar el script, se actualiza \`main\` mediante \`git pull --ff-only\`.

Para un checkout local existente, usa \`docker-build.sh\` y \`docker-run.sh\`. No borres el volumen persistente si quieres conservar el workspace.

El entorno usa \`ROS_DOMAIN_ID=42\` por defecto para aislar el tráfico DDS. La interfaz gráfica de Gazebo depende de que Docker Desktop/WSL2 tenga acceso gráfico funcional; para depurar el comportamiento de ROS, RViz y Nav2 se debe priorizar un entorno con carga de CPU controlada.

## 3. Instalar dependencias y compilar

Dentro del contenedor:

\`\`\`bash
cd /ros2_ws
source /opt/ros/jazzy/setup.bash
rosdep update
rosdep install --from-paths src --ignore-src -r -y --rosdistro jazzy
MAKEFLAGS="-j1" colcon build --symlink-install --executor sequential --event-handlers console_direct+
source install/setup.bash
\`\`\`

Los seis paquetes propios son \`dif_bot_bringup\`, \`dif_bot_control\`, \`dif_bot_description\`, \`dif_bot_gazebo\`, \`dif_bot_navigation\` y \`dif_bot_web_bridge\`.

## 4. Levantar el sistema

Modo recomendado con \`ros2_control\`:

\`\`\`bash
./START_DIF_BOT.sh
\`\`\`

Este script inicia por separado la base Gazebo/ROS, la interfaz web y el proceso de navegación. Los logs quedan separados en \`/ros2_ws/logs/base.log\`, \`navigation.log\` y \`web.log\`.

Abre \`http://localhost:3000\`; rosbridge usa \`ws://localhost:9090\`. Para detener todos los procesos gestionados:

\`\`\`bash
./STOP_DIF_BOT.sh
\`\`\`

Para comparar el modo nativo, detén el sistema y arranca la base con \`use_ros2_control:=false\`; no ejecutes ambos controladores al mismo tiempo. El lanzamiento directo de referencia es:

\`\`\`bash
ros2 launch dif_bot_bringup main.launch.py use_sim_time:=true use_ros2_control:=false launch_navigation:=false
\`\`\`

## 5. Mapa, SLAM y waypoints

SLAM Toolbox se lanza por separado y no debe ejecutarse simultáneamente con AMCL:

\`\`\`bash
ros2 launch dif_bot_bringup main.launch.py use_sim_time:=true launch_navigation:=false
ros2 launch dif_bot_navigation ekf.launch.py use_sim_time:=true
ros2 launch dif_bot_navigation slam.launch.py use_sim_time:=true
\`\`\`

Después de explorar el mundo con velocidades reducidas, guarda el mapa en \`src/dif_bot_navigation/maps/\` y actualiza \`my_map.yaml\` para apuntar al mapa generado.

El mapa versionado actualmente tiene 197 × 197 celdas a 0,05 m/resolución y origen aproximado \`[-4.93, -4.94, 0]\`. Las pruebas estáticas comprueban que la pose inicial (0,0) y los tres waypoints incluidos en \`config/waypoints.yaml\` caen en celdas libres de ese archivo. Esta comprobación **no sustituye** la alineación visual del mapa con el mundo Gazebo en RViz2 ni demuestra que las rutas sean transitables.

Los waypoints son puntos de ejemplo que deben volver a comprobarse cada vez que se sustituya el mapa.

## 6. Validación automática y pruebas funcionales

Cada push a \`main\` y cada pull request ejecuta:

- Pruebas estáticas de Python, XML/Xacro/SDF, YAML, conexión entre tópicos y servicio de misión.
- Comprobación de ocupación de las celdas correspondientes a la pose inicial y waypoints.
- Sintaxis de scripts Bash.
- Build y pruebas de los seis paquetes ROS 2 sobre Jazzy mediante \`colcon\`.

La automatización de GitHub valida código, dependencias y compilación; **no ejecuta Gazebo, no comprueba movimiento físico-simulado y no certifica la convergencia de AMCL ni el éxito de una misión**. Para eso se debe ejecutar el plan de integración de \`docs/TEST_PLAN_JAZZY.md\` dentro del contenedor.

Comprobaciones manuales locales:

\`\`\`bash
python3 -m pytest -q tests
bash -n START_DIF_BOT.sh STOP_DIF_BOT.sh DIAGNOSTIC_DIF_BOT.sh scripts/*.sh
\`\`\`

## 7. Seguridad y límites del sistema

- \`gz_ros2_control\` está integrado para simulación. Un robot físico requiere un \`hardware_interface\` compatible con sus motores, encoders y drivers.
- El modo \`false\` es DiffDrive nativo de Gazebo Sim, no una segunda implementación de \`ros2_control\`.
- El botón STOP llama a \`/dif_bot/stop\`, solicita cancelar los objetivos \`NavigateToPose\` y publica velocidades cero en las entradas manuales/web del mux. **No es un dispositivo E-stop físico ni una función de seguridad certificada.** En hardware real debe existir un paro de emergencia cableado e independiente.
- Las configuraciones de covarianza del EKF deben ajustarse usando mensajes y datos registrados; una prueba estática no demuestra precisión estadística.
- El ciclo de vida Nav2 usa un margen de heartbeat de 15 s para tolerar pausas de planificación en WSL2. Esto no corrige falta de CPU ni errores de los servidores.

## Referencias técnicas

- [ROS 2 Control — Jazzy](https://control.ros.org/jazzy/doc/getting_started/getting_started.html) y [gz_ros2_control — Jazzy](https://control.ros.org/jazzy/doc/gz_ros2_control/doc/index.html).
- [diff_drive_controller — Jazzy](https://control.ros.org/jazzy/doc/ros2_controllers/diff_drive_controller/doc/userdoc.html).
- [Nav2 Simple Commander — Jazzy](https://github.com/ros-navigation/navigation2/tree/jazzy/nav2_simple_commander).
- [Nav2 Behavior Server — Jazzy](https://docs.nav2.org/jazzy/configuration_and_development/configuration_guide/core_servers/configuring_behavior_server/).
- [Gazebo Sim DiffDrive — Gazebo Sim 8](https://gazebosim.org/api/sim/8/classgz_1_1sim_1_1systems_1_1DiffDrive.html).
