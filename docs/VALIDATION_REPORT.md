# Estado técnico del proyecto — DIF_BOT OS v2.0

**Corte de revisión:** 22 de noviembre de 2026  
**Repositorio:** \`JosthinCetina/Robot_Diferencial_v2.0\`  
**Rama:** \`main\`  
**Commit base auditado:** `4e0b436`; revisión posterior al despliegue del 22 de noviembre que presentó caída de HTTP 3000, teleoperación no disponible y espera prolongada de Nav2.

Este documento registra el estado de implementación y funcionamiento conocido de los seis componentes técnicos definidos en \`rbtc_proyecto_final_v1.pdf\`. No evalúa video, informe académico ni otros requisitos de entrega.

## Resumen ejecutivo

La arquitectura de software está integrada en seis paquetes ROS 2 y utiliza ROS 2 Jazzy, Gazebo Harmonic, robot_localization, SLAM Toolbox y Nav2. El repositorio contiene ambos modos de control, sensores simulados, adaptadores de tópicos, EKF, mapa, AMCL, planner, controller, behaviors, misión secuencial y panel web.

**La implementación en código no equivale a aceptación funcional.** No se debe marcar una práctica como superada hasta comprobarla en ejecución en el contenedor del proyecto.

## Matriz de cumplimiento técnico

| Componente | Implementación en el repositorio | Funcionamiento conocido | Trabajo necesario para aceptación |
|---|---|---|---|
| 1. Control diferencial y odometría | Plugin DiffDrive de Gazebo y `gz_ros2_control`, adaptadores `/cmd_vel` y `/odom_raw`. | **Parcial.** El último despliegue confirmó robot y controladores activos, pero HTTP 3000 no abrió y la teleoperación web no estuvo disponible. La UI ya se corrige para publicar Twist a 10 Hz mientras se mantiene pulsado y Twist cero al soltar; falta revalidación en ejecución. | Validar ambos modos por separado, recepción Twist/TwistStamped y cambio de `/odom_raw`; medir estabilidad/latencia y comparar fuentes de odometría. |
| 2. Fusión EKF | `ekf.yaml` fusiona `/odom_raw` y `/imu/data`; publica `/odom_filtered` y TF `odom -> base_footprint`. | **Implementado; validación runtime pendiente.** EKF está integrado en Nav2 y en `slam.launch.py` por defecto para crear la TF odométrica que requiere SLAM Toolbox. | Confirmar entradas, covarianzas, ausencia NaN/Inf, evolución TF y efecto de deshabilitar IMU. |
| 3. Mapeo SLAM | SLAM Toolbox asíncrono, parámetros 0,05 m, frames `map/odom/base_footprint`, mapa PGM/YAML y script `save_map.sh`. | **Implementación integrada; mapa actual no certificado como reconstrucción reciente.** SLAM incluye EKF por defecto y se agrega guardado reproducible YAML/PGM bajo `maps/`. | Explorar el mundo actual, guardar mapa nuevo, comprobar resolución/alineación en RViz y evaluar errores a distintas velocidades. |
| 4. Localización AMCL | Map Server, AMCL, partículas, pose inicial, frames map/odom/base y parámetros de ruido. | **Implementado; convergencia no demostrada.** Map Server recibe un mapa configurable del package share y se incorpora perfil RViz con nube de partículas y estimación inicial. | Observar convergencia en RViz, publicar pose inicial incorrecta y evaluar ruido LiDAR. |
| 5. Navegación Nav2 | NavFn, DWB, progress/goal checkers, costmaps, Behavior Server, BT Navigator y GoalTool RViz. | **No funcional en la última evidencia.** El usuario reportó abortos inmediatos y HTTP 3000 estuvo caído en el último despliegue. Se integra perfil RViz y configuración de mapa; yaw opcional/PoseProgressChecker ya están en código. Falta validación runtime. | Ejecutar metas UI/RViz, verificar lifecycle/AMCL, planes global/local, seguimiento angular y varios objetivos consecutivos sin abortos. |
| 6. Misiones autónomas | Servidor Python con BasicNavigator, servicio Trigger, YAML de waypoints, timeout y feedback. | **Implementación presente; misión integral no demostrada.** Los tres waypoints están configurados y validados estáticamente contra el mapa; el último run no confirmó navegación estable. | Ejecutar la secuencia real de tres waypoints, confirmar progreso/resultados y rechazo de metas fallidas y misiones simultáneas. |

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

El workflow `.github/workflows/static-validation.yml` comprueba análisis estático, YAML, XML/Xacro/SDF, waypoints en celdas libres, sintaxis Bash, compilación del frontend y build/test de paquetes con ROS 2 Jazzy.

Un resultado verde del workflow demuestra que los checks automatizados pasaron; **no demuestra** que Gazebo se haya ejecutado, que el robot se mueva, que AMCL converja, que Nav2 mantenga sus lifecycle bonds bajo carga ni que la misión llegue a los tres objetivos.

## Criterio para declarar el proyecto funcionalmente terminado

La matriz solo se puede marcar completamente en verde después de completar las pruebas del plan \`docs/TEST_PLAN_JAZZY.md\` en el contenedor real, con evidencia de ejecución y sin fallos pendientes. Hasta entonces, los estados parciales y pendientes de la matriz se mantienen deliberadamente para no confundir implementación con funcionamiento comprobado.

## Límites

- \`gz_ros2_control\` está configurado para simulación. No existe todavía un \`hardware_interface\` para motores/encoders de un robot físico.
- El modo nativo Gazebo DiffDrive es una alternativa de simulación, no un segundo hardware interface de \`ros2_control\`.
- El STOP web es un paro lógico de software. No es un dispositivo E-stop físico ni una función de seguridad certificada.
- Los waypoints se validan contra celdas libres del mapa versionado, pero la accesibilidad de la ruta y la alineación global del mapa deben verificarse en Gazebo/RViz2.


## Evidencia del último despliegue WSL2 (commit 208201f)

El texto de consola compartido el 22 de noviembre confirma:

- `ros_gz_sim/create` publicó `Entity creation successful.`.
- `joint_state_broadcaster` y `diff_drive_controller` quedaron activos.
- `colcon build` terminó con 6 paquetes completados.
- La compilación Vite terminó correctamente; el frontend se abrió en puerto 3000 y rosbridge en 9090.
- `START_DIF_BOT.sh` inició los procesos base, web y navegación.
- El usuario confirmó posteriormente que la teleoperación funciona.

El texto de despliegue no incluye `logs/navigation.log`; por tanto no demuestra que AMCL, todos los nodos lifecycle o una navegación autónoma completa hayan quedado estables. También reporta una advertencia rosdep no resuelta para la clave `ament_python` en dos paquetes (el build continuó y terminó) y dos vulnerabilidades npm (una moderada y una alta).

## Diagnóstico del aborto XY/yaw

El puente reportó `error_XY=0.046m`, `error_yaw=0.663rad`, con tolerancias de 0,050 m y 0,100 rad. El robot estaba dentro de la ventana XY, pero fuera de la tolerancia angular; Nav2 no debía declarar la pose completa como alcanzada.

La UI solo solicitaba X/Y, pero generaba un cuaternión identidad (`yaw=0`). Esto forzaba una orientación final no solicitada. Se modifica para conservar el yaw actual cuando no se proporciona y permitir un yaw explícito en grados.

Además, `SimpleProgressChecker` solo considera desplazamiento XY. La llegada a la ventana XY puede requerir rotación en el sitio, que no reinicia su temporizador de progreso. Se reemplaza por `nav2_controller::PoseProgressChecker`, que considera desplazamiento y diferencia angular. La corrección está fundada en el código upstream de Nav2 Jazzy, pero no se marcará como funcional hasta repetir la navegación en Gazebo y revisar `navigation.log`.


## Incidente de regresión — despliegue posterior a 9bff4ef

En la prueba reportada por el usuario, la teleoperación no produjo movimiento y los objetivos de navegación abortaron inmediatamente. El registro confirma que la compilación de los seis paquetes y del frontend finalizó, Gazebo insertó `dif_bot` y los controladores `joint_state_broadcaster` y `diff_drive_controller` quedaron `active`. Esto no demuestra que `twist_mux` publicara comandos, que el controlador recibiera `TwistStamped`, ni que AMCL/Nav2 quedaran activos y publicaran una pose/localización utilizable.

El diagnóstico automático de ese despliegue falló antes de ejecutar el script: la redirección intentó escribir `logs/post_deploy_diagnostic.log` en un directorio del bind mount sin permisos para el usuario WSL y devolvió `Permission denied`. Por tanto, no se obtuvo estado runtime ni extractos de `navigation.log`. El resultado debe clasificarse como **regresión funcional sin causa raíz confirmada**, no como fallo específico de DWB o del EKF.

El desplegador se modifica para capturar en un archivo temporal propiedad del usuario, imprimirlo completo y adjuntar también las últimas líneas crudas de `base.log`, `navigation.log` y `web.log`. El diagnóstico revisa las cadenas de mando, el estado de controladores, nodos, tópicos, acción, lifecycle, muestras de odometría y AMCL, parámetros de DWB y errores de logs.


## Incidente de despliegue del 22 de noviembre (commit 602a429)

El registro confirma que `colcon build` finalizó con seis paquetes, Vite construyó el frontend, Gazebo insertó el robot y los controladores aparecieron activos. Sin embargo, HTTP 3000 no abrió después de 20 segundos; `START_DIF_BOT.sh` continuó hasta iniciar Nav2. La interfaz no estaba disponible para teleoperar.

El despliegue entró después en una espera de `/navigate_to_pose` y realizaba consultas repetidas `ros2 action list`, seguidas por un barrido de nodos, topics, lifecycle y `topic echo --once`. Repetir ese procedimiento bajo carga de Gazebo/WSL2 explica el tiempo prolongado y la degradación. Esas operaciones se retiraron del camino normal de despliegue. La validación funcional se ejecuta siguiendo el plan de prácticas, no durante cada reconstrucción.

La UI publica ahora Twist sostenido a 10 Hz mientras se mantiene un control y publica cero al soltar o perder foco. El inicio usa `vite preview`, requiere que rosbridge y HTTP estén disponibles y no lanza Nav2 si la web falla.

## Integración de prácticas 3, 4 y 5

`slam.launch.py` inicia EKF por defecto para proveer `odom -> base_footprint`. `navigation.launch.py` carga el mapa mediante un parámetro configurable cuya ruta predeterminada está en el package share. Se agrega `rviz.launch.py` y un perfil que muestra mapa, RobotModel, TF, LiDAR, partículas AMCL, planes y Nav2 GoalTool. RViz es bajo demanda para reducir carga.

`scripts/save_map.sh` usa Map Saver y guarda YAML/PGM bajo `src/dif_bot_navigation/maps/`. Se reduce el paso de física a 2 ms (500 Hz), se desactiva visualización de rayos LiDAR y se reduce la cámara a 320×240/5 Hz; el IMU sigue a 100 Hz y el LiDAR a 10 Hz. La configuración necesita validación de movimiento y EKF en ejecución.

**Aceptación:** ninguna práctica se marca funcional solo por compilar. Teleoperación, EKF, SLAM, convergencia AMCL, navegación desde RViz y misión secuencial siguen pendientes de evidencia runtime.
