# Informe de validación de entrega — dif_bot OS v2.0 (ROS 2 Jazzy)

Fecha de preparación: 2026-11-17.

## Alcance implementado

- Migración de los paquetes del workspace a ROS 2 Jazzy y simulación Gazebo Harmonic mediante `ros_gz`.
- Modo principal `use_ros2_control:=true`: `gz_ros2_control`, `controller_manager`, `joint_state_broadcaster` y `diff_drive_controller`.
- Modo comparativo `use_ros2_control:=false`: sistema DiffDrive nativo de Gazebo Sim.
- Normalización de entradas: ambos modos entregan odometría bruta en `/odom_raw`; el EKF publica `/odom_filtered` y la TF `odom -> base_footprint`.
- Arbitraje de comandos mediante `twist_mux`; adaptación `Twist` a `TwistStamped` para `diff_drive_controller` en Jazzy.
- Puentes de `/clock`, `/scan`, `/imu/data` y `/camera/image`.
- Nav2, SLAM Toolbox, misión secuencial y panel React/roslibjs con servicio de paro lógico.
- Docker dedicado, scripts de build/run, volumen persistente y publicación en un repositorio GitHub nuevo.

## Verificaciones ejecutadas en el entorno de generación

| Verificación | Resultado |
|---|---|
| Pruebas estáticas del proyecto (`python3 -m pytest -q tests`) | PASS — 13/13 |
| Sintaxis de scripts Bash (`bash -n`) | PASS |
| AST de fuentes Python | PASS — 18 archivos |
| XML, Xacro, SDF y manifiestos `package.xml` | PASS — 10 archivos |
| Archivos YAML | PASS — 7 archivos |
| Tamaños de máscaras EKF / covarianza Q | PASS — 15, 15 y 225 elementos |
| Dependencia `ros-jazzy-ros2-control` sin duplicación | PASS |
| Modos `gz_ros2_control` y DiffDrive nativo presentes | PASS |

## Verificaciones no ejecutadas

El entorno usado para preparar esta entrega no tiene los ejecutables `docker`, `ros2`, `gz`, `xacro` ni `colcon`. Por lo tanto, no se ejecutaron:

- Construcción de la imagen Docker ni instalación real de paquetes apt.
- `rosdep install` y `colcon build` dentro de ROS 2 Jazzy.
- Expansión de Xacro con el ejecutable Xacro ni validación URDF con `check_urdf`.
- Arranque real de Gazebo Harmonic, carga del plugin `gz_ros2_control` o activación de controladores.
- Publicación real de sensores, sincronización de `/clock`, TF o convergencia EKF.
- Movimiento de ruedas en ambos modos, Nav2, SLAM, misiones y servicio STOP.
- Compilación del frontend Vite: la instalación de dependencias (`npm ci`) agotó el tiempo de ejecución disponible y no completó; el directorio parcial de dependencias se excluyó del paquete.

Estas pruebas están detalladas, con comandos y criterios de aceptación, en `TEST_PLAN_JAZZY.md`. No se deben marcar como superadas por inferencia a partir de las pruebas estáticas.

## Notas de seguridad y operación

- El modo `false` no es una alternativa de `ros2_control`: es el plugin diferencial nativo de Gazebo Sim y sirve para comparación.
- Los waypoints entregados son ejemplos. Verificar su ocupación y accesibilidad en el mapa generado antes de iniciar la misión.
- El STOP web es una petición de parada lógica por ROS, no un paro de emergencia físico ni una función de seguridad certificada. Un robot físico necesita E-stop cableado y hardware independiente.
- El `hardware_interface` para motores/encoders físicos no se implementa aquí; esta integración `gz_ros2_control` es para simulación.
- La publicación del repositorio remoto no se ejecutó desde esta sesión. El script `scripts/publish_github.sh` realiza la creación y el push desde WSL2 una vez autenticado con GitHub CLI.
