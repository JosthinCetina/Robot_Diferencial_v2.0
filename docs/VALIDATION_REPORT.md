# Estado técnico del proyecto — DIF_BOT OS v2.0

**Corte de revisión:** 22 de noviembre de 2026  
**Repositorio:** \`JosthinCetina/Robot_Diferencial_v2.0\`  
**Rama:** \`main\`  
**Commit base auditado:** \`cd7f751\`; este documento se actualiza junto con el commit de los ajustes técnicos descritos aquí.

Este documento registra el estado de implementación y funcionamiento conocido de los seis componentes técnicos definidos en \`rbtc_proyecto_final_v1.pdf\`. No evalúa video, informe académico ni otros requisitos de entrega.

## Resumen ejecutivo

La arquitectura de software está integrada en seis paquetes ROS 2 y utiliza ROS 2 Jazzy, Gazebo Harmonic, robot_localization, SLAM Toolbox y Nav2. El repositorio contiene ambos modos de control, sensores simulados, adaptadores de tópicos, EKF, mapa, AMCL, planner, controller, behaviors, misión secuencial y panel web.

**La implementación en código no equivale a aceptación funcional.** No se debe marcar una práctica como superada hasta comprobarla en ejecución en el contenedor del proyecto.

## Matriz de cumplimiento técnico

| Componente | Implementación en el repositorio | Funcionamiento conocido | Trabajo necesario para aceptación |
|---|---|---|---|
| 1. Control diferencial y odometría | Modo Gazebo DiffDrive y modo \`gz_ros2_control\`; adaptadores a \`/cmd_vel\` y \`/odom_raw\`. | **Parcial.** En una sesión anterior se observaron activos los controladores de \`ros2_control\`. La comparación equivalente del modo nativo no está documentada como prueba aprobada. | Ejecutar ambos modos por separado, medir respuesta lineal/angular, frecuencia y error de odometría. |
| 2. Fusión EKF | \`ekf.yaml\` integra \`/odom_raw\` y \`/imu/data\`; publica \`/odom_filtered\` y TF \`odom -> base_footprint\`. | **Pendiente de revalidación.** En sesiones anteriores hubo lecturas intermitentes de \`/odom_raw\` y covarianzas anormalmente grandes en \`/odom_filtered\`. Se ajustó la selección de IMU para no fusionar yaw absoluto con covarianza de orientación observada en cero. | Confirmar datos de entrada, covarianzas, ausencia de NaN/Inf y evolución coherente de TF con el robot en movimiento. |
| 3. Mapeo SLAM | SLAM Toolbox, parámetros asíncronos, lanzamiento y mapa PGM/YAML versionado. | **Parcial.** El mapa existente tiene dimensiones/resolución conocidas. El README lo identifica como heredado; no hay evidencia de que sea una reconstrucción SLAM reciente alineada con el mundo actual. | Ejecutar exploración lenta, guardar mapa nuevo y comparar obstáculos con Gazebo en RViz2. |
| 4. Localización AMCL | AMCL, Map Server, parámetros de partículas, frame map/odom/base y pose inicial configurada. | **Pendiente de convergencia.** En sesiones previas Map Server y AMCL llegaron a estar activos, pero no se confirmó una pose AMCL estable. | Confirmar \`/amcl_pose\`, nube de partículas y TF \`map -> odom\`; probar pose inicial incorrecta y ruido de LiDAR. |
| 5. Navegación Nav2 | NavFn, DWB, costmaps global/local, BT Navigator y cuatro comportamientos de recuperación. | **Parcial e inestable.** Se consiguió una meta con error XY cercano a 0,04 m después de ajustar DWB. También se observaron pérdidas de heartbeat de planner/behavior bajo presión elevada de CPU en WSL2. | Mantener servidores lifecycle activos, validar costmaps, evitar obstáculos, completar varias metas y registrar recuperaciones. |
| 6. Misiones autónomas | Servidor Python con BasicNavigator, servicio Trigger, YAML de waypoints y tópico de progreso. | **Implementación presente; ejecución integral no demostrada.** El YAML incluye tres puntos. Se añade validación estática de que esos puntos caen en celdas libres y límites temporales para evitar esperas indefinidas. | Ejecutar los tres puntos en orden, confirmar progreso y resultado, y comprobar rechazo de metas fallidas y bloqueo de misiones simultáneas. |

## Evidencia que ya existe

- El URDF/Xacro contiene ambos sistemas de control.
- El modo \`ros2_control\` dispone de configuración para \`joint_state_broadcaster\` y \`diff_drive_controller\`.
- Los sensores simulados y puentes incluyen LiDAR, IMU, cámara y reloj de simulación.
- El EKF está configurado en dos dimensiones y publica la transformación odométrica.
- SLAM Toolbox tiene un lanzamiento independiente para no ejecutarse simultáneamente con AMCL.
- Nav2 integra Map Server, AMCL, NavFn, DWB, costmaps y Behavior Server.
- La misión utiliza \`nav2_simple_commander\`, \`/start_autonomous_mission\` y \`config/waypoints.yaml\`.
- El panel web tiene conexión con rosbridge, telemetría, objetivos, paro lógico y progreso de misión.
- Los tres waypoints actuales y la pose inicial (0,0) fueron comprobados contra los píxeles del mapa versionado: corresponden a celdas libres (valor PGM 254). La prueba se incorpora a la suite estática.

## Ajustes técnicos incorporados en esta actualización

1. El servidor de misiones dejó de usar \`BasicNavigator.waitUntilNav2Active()\` como espera ilimitada. Consulta los estados de los seis nodos lifecycle requeridos, espera \`/amcl_pose\` con timeout, valida el servidor de acción y aplica un tiempo máximo por waypoint. Los resultados se publican como \`FALLIDA\` o \`ERROR\`, sin dejar la interfaz permanentemente ocupada.
2. Se valida el contenido numérico del YAML de misión para rechazar coordenadas no finitas, tipos incorrectos y listas vacías.
3. La misión publica feedback de distancia como máximo una vez por segundo, evitando inundar el registro y la interfaz.
4. Nav2 usa un \`bond_timeout\` de 15 s en ambos administradores lifecycle para tolerar pausas de planificación por presión de CPU. Este margen no sustituye la resolución de una saturación real.
5. El EKF fusiona la velocidad angular Z de la IMU, pero no la orientación yaw absoluta observada con covarianza cero; la orientación se obtiene a partir de la integración de tasas del giróscopo y la odometría de ruedas.
6. El puente web conserva la meta correspondiente a cada solicitud de acción, evitando comparar un resultado antiguo con una meta nueva.
7. Se añadió CI para pruebas estáticas y compilación de los seis paquetes ROS 2 Jazzy.
8. Se añadió \`.gitignore\` para evitar publicar logs, diagnósticos, backups, bolsas ROS, dependencias web y archivos de entorno.
9. El script de actualización GitHub se adaptó al repositorio existente y dejó de crear por defecto un repositorio nuevo.

## Qué significa la validación automática

El workflow \`.github/workflows/static-validation.yml\` comprueba análisis estático, YAML, XML/Xacro/SDF, waypoints en celdas libres, sintaxis Bash y build/test de paquetes con ROS 2 Jazzy.

Un resultado verde del workflow demuestra que los checks automatizados pasaron; **no demuestra** que Gazebo se haya ejecutado, que el robot se mueva, que AMCL converja, que Nav2 mantenga sus lifecycle bonds bajo carga ni que la misión llegue a los tres objetivos.

## Criterio para declarar el proyecto funcionalmente terminado

La matriz solo se puede marcar completamente en verde después de completar las pruebas del plan \`docs/TEST_PLAN_JAZZY.md\` en el contenedor real, con evidencia de ejecución y sin fallos pendientes. Hasta entonces, los estados parciales y pendientes de la matriz se mantienen deliberadamente para no confundir implementación con funcionamiento comprobado.

## Límites

- \`gz_ros2_control\` está configurado para simulación. No existe todavía un \`hardware_interface\` para motores/encoders de un robot físico.
- El modo nativo Gazebo DiffDrive es una alternativa de simulación, no un segundo hardware interface de \`ros2_control\`.
- El STOP web es un paro lógico de software. No es un dispositivo E-stop físico ni una función de seguridad certificada.
- Los waypoints se validan contra celdas libres del mapa versionado, pero la accesibilidad de la ruta y la alineación global del mapa deben verificarse en Gazebo/RViz2.
