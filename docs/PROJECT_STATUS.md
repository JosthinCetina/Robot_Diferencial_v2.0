# Estado del proyecto — DIF_BOT OS v2.0

**Corte:** 22 de noviembre de 2026 (America/Bogota)  
**Rama:** `main`  
**Stack:** ROS 2 Jazzy · Gazebo Harmonic · `ros2_control` · robot_localization · Nav2 · React/Vite

## Evidencia funcional reportada

| Subsistema / prueba | Resultado | Alcance de la evidencia |
|---|---|---|
| Despliegue WSL2/Docker | Validado | Base Gazebo, controladores, rosbridge y frontend arrancan; una primera espera HTTP agotó 20 s, el segundo despliegue funcionó. |
| Teleoperación web | Validada | El usuario confirmó movimiento y control desde la interfaz. |
| NAV-01: meta `[1, 1, DEFAULT]` | SUCCEEDED | Nav2 terminó la acción `NavigateToPose` correctamente. |
| NAV-02: meta `[1, 1, 5°]` | SUCCEEDED | Confirma orientación final en la misma posición XY; no es una prueba de desplazamiento largo. |
| Timeouts BT Navigator | Corregidos en configuración | `default_server_timeout` y `default_cancel_timeout` pasan a 1000 ms (Jazzy los interpreta en milisegundos). |

## Correcciones de sincronización publicadas

Los nodos web que publican/consumen poses trabajan ahora con `use_sim_time`:
- `robot_pose` conserva `t.header.stamp`, la marca temporal real de la transformación TF, en lugar de reemplazarla por la hora de publicación.
- `goal_bridge` fecha la meta con su reloj ROS y verifica la antigüedad tanto por tiempo de recepción monotónico como por la marca temporal TF.
- Se añadió una prueba estática para evitar que se pierda esta coherencia temporal.
- La espera HTTP del frontend durante el arranque se amplió de 20 a 45 s tras un primer arranque donde Vite Preview tardó en abrir el puerto 3000.

## Incidencias conocidas que aún requieren validación

1. **TF:** un registro anterior mostró `Transform data too old` al transformar de `odom` a `map`; desfase observado 0.520 s frente a 0.500 s configurados. La corrección del puente web no sustituye la verificación de la cadena AMCL → `map → odom` → EKF → `odom → base_footprint`.
2. **EKF:** con `frequency: 30.0 Hz`, se registraron ciclos de 34–94 ms. No bajar la frecuencia sin medir primero la tasa efectiva de /odom_filtered, el ritmo de /clock y la antigüedad de TF.
3. **Robustez Nav2:** dos objetivos tuvieron SUCCEEDED, pero falta un recorrido de traslación largo, una serie de metas consecutivas y comprobar que los abortos TF no vuelven a aparecer.
4. **Misión secuencial:** `mission_server.py` y tres waypoints de ejemplo están implementados; todavía no se ha validado una misión completa en ejecución.
5. **SLAM/AMCL:** existen launches y un mapa versionado de 197×197 celdas a 0.05 m; falta validar correspondencia mapa-mundo, convergencia AMCL y TF global.
6. **Comparación de tracción:** falta repetir las pruebas con DiffDrive nativo de Gazebo (`use_ros2_control:=false`) y compararlo con `ros2_control`.

## Próxima secuencia de integración

1. Desplegar el commit actual y comprobar que interfaz web y navegación arrancan.
2. Ejecutar una misión con los tres waypoints de `config/waypoints.yaml`; confirmar progreso, orden, SUCCEEDED por waypoint y resultado final.
3. Revisar con esos registros la frescura de TF, los timestamps de `/scan`, `/odom_raw`, `/odom_filtered`, /clock y la salida del EKF. Ajustar la frecuencia solo con esa evidencia.
4. Ejecutar SLAM de forma exclusiva: detener Nav2/AMCL, mantener una sola instancia de EKF, explorar y guardar un mapa nuevo; luego reiniciar con mapa estático y validar AMCL en RViz.
5. Completar pruebas repetidas de navegación, recuperaciones, paro/cancelación, y comparación de los dos modos de tracción.

## Reglas para declarar una fase completada

- Compilar o pasar CI no prueba movimiento ni navegación.
- SLAM y AMCL no deben ejecutarse al mismo tiempo como localizadores competidores.
- Teleoperación y navegación autónoma no deben controlar el robot simultáneamente durante pruebas de aceptación.
- Las tolerancias de llegada no se relajan para ocultar errores de TF o localización.
- Toda aceptación funcional debe apoyarse en resultado de acción, progreso, logs y, para localización, marcas temporales coherentes.
