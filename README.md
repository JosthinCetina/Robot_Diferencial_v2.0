# dif_bot OS v2.0 — ROS 2 Jazzy + Gazebo Harmonic

Proyecto de robot diferencial simulado: control `ros2_control`, modo nativo Gazebo, EKF, Nav2, misiones secuenciales y panel web. El entorno se separa en una imagen y un volumen Docker dedicados a este proyecto.

## Arquitectura

- **ROS 2 Jazzy / Ubuntu 24.04 / Gazebo Harmonic**.
- Gazebo Sim y `ros_gz_bridge`: sensores `/scan`, `/imu/data`, `/camera/image`.
- **Modo control principal** (`use_ros2_control:=true`): URDF `<ros2_control>`, `gz_ros2_control/GazeboSimSystem`, `controller_manager`, `joint_state_broadcaster` y `diff_drive_controller`.
- **Modo comparativo** (`use_ros2_control:=false`): plugin `gz-sim-diff-drive-system` nativo de Gazebo Sim, sin `ros2_control`.
- Ambos modos normalizan el mando en `/cmd_vel` y odometría bruta en `/odom_raw`. El EKF publica `/odom_filtered` y la única TF `odom -> base_footprint`.
- `twist_mux` arbitra teclado/web/control de pose/Nav2 con prioridad y timeout.
- Nav2 Jazzy (AMCL, NavFn, DWB, behavior server), SLAM Toolbox y una misión Python con waypoints secuenciales.
- React/Vite/roslibjs vía rosbridge WebSocket `9090`; UI en `3000`.

## 1. Crear el repositorio GitHub nuevo

Extrae el ZIP, abre WSL2 en la carpeta `dif_bot_os_jazzy` y autentica GitHub CLI una sola vez:

```bash
sudo apt update && sudo apt install -y gh git
gh auth login
```

Crea el repositorio automáticamente, genera el commit y publica `main` con un único comando:

```bash
./scripts/publish_github.sh public
```

El script crea `dif_bot_os_jazzy` en la cuenta autenticada. Para mantenerlo privado, usa `./scripts/publish_github.sh private`; para ese modo, sigue el flujo de clonación privada más abajo. No incluyas tokens en URLs ni dentro del repositorio. Revisa los campos `maintainer` de los seis `package.xml` y reemplaza el correo genérico antes de presentar o publicar el proyecto formalmente.

También puedes crear un repositorio vacío desde <https://github.com/new> y usar Git manualmente, si prefieres no instalar GitHub CLI.

## 2. Descargarlo y ejecutarlo en el Docker dedicado

Para un repositorio público, desde la carpeta local que contiene `docker-clone-run.sh`, ejecuta:

```bash
./docker-clone-run.sh https://github.com/<USUARIO>/dif_bot_os_jazzy.git main
```

El script construye la imagen `dif-bot-os:jazzy` usando el `Dockerfile` del repositorio remoto, crea el volumen persistente `difbot_jazzy_ws`, clona el repositorio dentro de `/ros2_ws` y abre el contenedor `dif-bot-os-jazzy`. Al salir del contenedor, el volumen conserva el repositorio; al volver a ejecutar el script, actualiza `main` con `git pull --ff-only`.

**Para un repositorio privado:** autentica y clona primero en WSL2 con Git Credential Manager. Luego entra en la carpeta clonada y ejecuta `./docker-build.sh` seguido de `./docker-run.sh`. En este modo Docker monta el repositorio local en `/ros2_ws`, sin guardar credenciales dentro de la imagen ni exponer el token en una URL.

El script configura el acceso gráfico de WSLg y `/dev/dri` cuando están disponibles. También usa `ROS_DOMAIN_ID=42` por defecto para aislar el tráfico DDS de otros proyectos ROS; puedes sobrescribirlo definiendo `ROS_DOMAIN_ID` antes de ejecutar el script. La GUI depende de que Docker Desktop/WSL2 tenga acceso gráfico funcional; la compilación y las pruebas sin GUI pueden realizarse igualmente.

## 3. Instalar dependencias del workspace y compilar

Dentro del contenedor:

```bash
cd /ros2_ws
source /opt/ros/jazzy/setup.bash
rosdep update
rosdep install --from-paths src --ignore-src -r -y --rosdistro jazzy
MAKEFLAGS="-j1" colcon build --symlink-install --executor sequential --event-handlers console_direct+
source install/setup.bash
```

## 4. Levantar el sistema

Modo recomendado con `ros2_control`:

```bash
ros2 launch dif_bot_bringup main.launch.py use_sim_time:=true use_ros2_control:=true launch_navigation:=true
```

Modo nativo para comparar:

```bash
ros2 launch dif_bot_bringup main.launch.py use_sim_time:=true use_ros2_control:=false launch_navigation:=true
```

Ejecuta un solo modo a la vez. Para levantar solo el robot/sensores/control, sin Nav2, añade `launch_navigation:=false`.

En otro terminal del mismo contenedor:

```bash
source /opt/ros/jazzy/setup.bash
source /ros2_ws/install/setup.bash
cd /ros2_ws/web
npm ci
npm run dev -- --host 0.0.0.0
```

Abre `http://localhost:3000`. La UI requiere rosbridge en `ws://localhost:9090`. Para actualizar/crear un mapa desde SLAM, arranca `main.launch.py launch_navigation:=false` y luego ejecuta en terminales separadas `ros2 launch dif_bot_navigation ekf.launch.py use_sim_time:=true` y `ros2 launch dif_bot_navigation slam.launch.py use_sim_time:=true`; no ejecutes AMCL y SLAM simultáneamente.

## 5. Configurar mapa y waypoints

El mapa heredado tiene 197×197 celdas a 0.05 m/resolución (extensión aproximada de 9.85×9.85 m) y el mundo Gazebo tiene un recinto de dimensiones interiores cercanas a 9.8×9.8 m: sus escalas son compatibles como punto de partida, pero eso no demuestra que el contorno de obstáculos esté alineado píxel a píxel. Antes de usar Nav2, compara `/map` con el mundo en RViz2 y verifica la pose AMCL inicial (0,0,0). Si las paredes no coinciden, vuelve a mapear con SLAM Toolbox y reemplaza ambos archivos de mapa. Los puntos de `config/waypoints.yaml` son ejemplos: confirma que cada coordenada cae en una celda libre y que Nav2 puede alcanzarla.

## 6. Pruebas de aceptación

Sigue, en orden, `docs/TEST_PLAN_JAZZY.md`. No declares lista la integración hasta verificar controladores activos, sensores, TF, EKF, movimiento/parada, SLAM/AMCL, navegación individual, misión, WebSocket y comparación de ambos modos. Las pruebas estáticas son:

```bash
python3 -m pytest -q tests
bash -n docker-build.sh docker-run.sh docker-clone-run.sh scripts/*.sh
```

## 7. Alcance y límites

- Se integró el framework `ros2_control` específicamente para simulación con `gz_ros2_control`; para hardware físico se necesita implementar un `hardware_interface` compatible con los motores, encoders y drivers reales.
- El modo `false` es control diferencial nativo de Gazebo Sim, no una segunda forma de `ros2_control`.
- El botón STOP de la interfaz llama a `/dif_bot/stop`, solicita cancelar todos los objetivos `NavigateToPose` y publica velocidades cero en las entradas de mando manual/web; es un paro lógico que depende de ROS, el mux, el controlador y la comunicación. No es un dispositivo E-stop físico ni una función de seguridad certificada. Para hardware real debe instalarse un paro de emergencia cableado e independiente.
- El código y configuraciones han pasado verificaciones estáticas descritas en el informe de entrega. El workflow `.github/workflows/static-validation.yml` repite las pruebas Python/configuración y sintaxis shell en cada push y pull request a `main`. Este entorno de generación no tiene Docker, ROS 2 ni Gazebo instalados; por eso no se declara probado el arranque, el control físico-simulado ni Nav2 hasta ejecutar el plan de integración dentro de tu contenedor.

## Referencias técnicas oficiales

- [ROS 2 Control — Jazzy](https://control.ros.org/jazzy/doc/getting_started/getting_started.html) y [gz_ros2_control — Jazzy](https://control.ros.org/jazzy/doc/gz_ros2_control/doc/index.html).
- [diff_drive_controller — Jazzy](https://control.ros.org/jazzy/doc/ros2_controllers/diff_drive_controller/doc/userdoc.html).
- [Nav2 Behavior Server — Jazzy](https://docs.nav2.org/jazzy/configuration_and_development/configuration_guide/core_servers/configuring_behavior_server/).
- [Gazebo Sim 8 — DiffDrive](https://gazebosim.org/api/sim/8/classgz_1_1sim_1_1systems_1_1DiffDrive.html) y [ros_gz_bridge](https://github.com/gazebosim/ros_gz/blob/ros2/ros_gz_bridge/README.md).
