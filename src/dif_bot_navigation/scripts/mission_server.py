#!/usr/bin/env python3
"""Bounded sequential waypoint mission server for dif_bot OS v2.0."""

import math
import os
import threading
import time

import rclpy
import yaml
from ament_index_python.packages import get_package_share_directory
from action_msgs.msg import GoalStatus
from geometry_msgs.msg import PoseStamped
from lifecycle_msgs.srv import GetState
from nav2_simple_commander.robot_navigator import BasicNavigator, TaskResult
from rclpy.executors import SingleThreadedExecutor
from rclpy.node import Node
from rclpy.parameter import Parameter
from std_msgs.msg import String
from std_srvs.srv import Trigger


class MissionServer(Node):
    """Accepts one mission at a time and reports bounded, explicit outcomes."""

    NAV2_LIFECYCLE_NODES = (
        'map_server',
        'amcl',
        'planner_server',
        'controller_server',
        'behavior_server',
        'bt_navigator',
    )

    def __init__(self):
        super().__init__('autonomous_mission_server')

        default_file = os.path.join(
            get_package_share_directory('dif_bot_navigation'),
            'config',
            'waypoints.yaml',
        )
        self.declare_parameter('waypoints_file', default_file)
        self.declare_parameter('nav2_startup_timeout_sec', 180.0)
        self.declare_parameter('amcl_pose_timeout_sec', 60.0)
        self.declare_parameter('action_server_timeout_sec', 30.0)
        self.declare_parameter('waypoint_timeout_sec', 240.0)

        self._lock = threading.Lock()
        self._running = False
        self._worker = None
        self._shutdown_event = threading.Event()

        self._progress = self.create_publisher(
            String, '/dif_bot/mission/progress', 10
        )
        self._service = self.create_service(
            Trigger, '/start_autonomous_mission', self.start_callback
        )

        self.get_logger().info(
            'Servicio listo: /start_autonomous_mission '
            '(esperas Nav2 y AMCL con timeout)'
        )

    def publish_progress(self, text):
        message = String()
        message.data = text
        self._progress.publish(message)
        self.get_logger().info(text)

    def _positive_parameter(self, name):
        value = float(self.get_parameter(name).value)
        if not math.isfinite(value) or value <= 0.0:
            raise ValueError(f'El parámetro {name} debe ser positivo y finito.')
        return value

    @staticmethod
    def _finite_number(value, field, waypoint_name):
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise ValueError(
                f'{waypoint_name}: el campo {field} debe ser numérico.'
            )
        number = float(value)
        if not math.isfinite(number):
            raise ValueError(
                f'{waypoint_name}: el campo {field} debe ser finito.'
            )
        return number

    def load_waypoints(self):
        path = self.get_parameter('waypoints_file').value
        if not path or not os.path.isfile(path):
            raise FileNotFoundError(f'No existe el archivo de waypoints: {path}')

        with open(path, 'r', encoding='utf-8') as stream:
            data = yaml.safe_load(stream)

        if not isinstance(data, dict) or not isinstance(data.get('mission'), dict):
            raise ValueError('El YAML debe contener una sección mission.')

        mission = data['mission']
        frame = mission.get('frame_id', 'map')
        if not isinstance(frame, str) or not frame.strip():
            raise ValueError('mission.frame_id debe ser un frame no vacío.')

        points = mission.get('waypoints')
        if not isinstance(points, list) or not points:
            raise ValueError('mission.waypoints debe contener al menos un punto.')

        validated = []
        for index, point in enumerate(points, start=1):
            if not isinstance(point, dict):
                raise ValueError(f'Waypoint_{index}: cada punto debe ser un objeto YAML.')

            name = str(point.get('name', f'Waypoint_{index}')).strip()
            if not name:
                name = f'Waypoint_{index}'

            validated.append({
                'name': name,
                'x': self._finite_number(point.get('x'), 'x', name),
                'y': self._finite_number(point.get('y'), 'y', name),
                'yaw_deg': self._finite_number(
                    point.get('yaw_deg', 0.0), 'yaw_deg', name
                ),
            })

        return frame, validated

    def _wait_for_nav2_and_localization(self, navigator):
        """Wait for all required lifecycle nodes and AMCL pose, with deadlines."""
        startup_timeout = self._positive_parameter('nav2_startup_timeout_sec')
        amcl_timeout = self._positive_parameter('amcl_pose_timeout_sec')
        action_timeout = self._positive_parameter('action_server_timeout_sec')

        startup_deadline = time.monotonic() + startup_timeout
        state_clients = {
            name: navigator.create_client(GetState, f'/{name}/get_state')
            for name in self.NAV2_LIFECYCLE_NODES
        }
        active_nodes = set()

        while time.monotonic() < startup_deadline:
            if self._shutdown_event.is_set() or not rclpy.ok():
                raise RuntimeError('El servidor recibió una solicitud de apagado.')

            active_nodes.clear()
            for name, client in state_clients.items():
                if not client.wait_for_service(timeout_sec=0.15):
                    continue

                future = client.call_async(GetState.Request())
                remaining = max(0.05, startup_deadline - time.monotonic())
                rclpy.spin_until_future_complete(
                    navigator, future, timeout_sec=min(1.0, remaining)
                )

                if not future.done() or future.result() is None:
                    continue

                if future.result().current_state.label == 'active':
                    active_nodes.add(name)

            if len(active_nodes) == len(self.NAV2_LIFECYCLE_NODES):
                break
            time.sleep(0.25)
        else:
            missing = sorted(set(self.NAV2_LIFECYCLE_NODES) - active_nodes)
            raise TimeoutError(
                f'Nav2 no quedó activo en {startup_timeout:.0f}s. '
                f'Nodos aún no activos: {", ".join(missing) or "estado no confirmado"}.'
            )

        # BasicNavigator marks this flag when it receives /amcl_pose.
        # Unlike waitUntilNav2Active(), this loop has a wall-clock deadline.
        pose_deadline = time.monotonic() + amcl_timeout
        while rclpy.ok() and not navigator.initial_pose_received:
            if self._shutdown_event.is_set():
                raise RuntimeError('La misión fue interrumpida durante la localización.')
            remaining = pose_deadline - time.monotonic()
            if remaining <= 0.0:
                raise TimeoutError(
                    f'AMCL no publicó /amcl_pose en {amcl_timeout:.0f}s. '
                    'Compruebe /map, /scan, TF y la pose inicial.'
                )
            rclpy.spin_once(navigator, timeout_sec=min(0.25, remaining))

        if not rclpy.ok():
            raise RuntimeError('ROS 2 se cerró mientras se esperaba la pose AMCL.')

        if not navigator.nav_to_pose_client.wait_for_server(
            timeout_sec=action_timeout
        ):
            raise TimeoutError(
                f'El action server navigate_to_pose no estuvo disponible '
                f'en {action_timeout:.0f}s.'
            )

        self.get_logger().info('Nav2 y AMCL están listos para ejecutar la misión.')

    @staticmethod
    def _cancel_current_goal(navigator):
        """Request cancellation without allowing shutdown to block indefinitely."""
        goal_handle = getattr(navigator, 'goal_handle', None)
        if goal_handle is None:
            return
        try:
            future = goal_handle.cancel_goal_async()
            rclpy.spin_until_future_complete(
                navigator, future, timeout_sec=5.0
            )
        except Exception:
            pass

    def start_callback(self, request, response):
        del request

        with self._lock:
            if self._shutdown_event.is_set():
                response.success = False
                response.message = 'El servidor de misiones se está apagando.'
                return response
            if self._running:
                response.success = False
                response.message = 'Ya existe una misión en ejecución.'
                return response

            self._running = True
            self._worker = threading.Thread(
                target=self.run_mission,
                name='dif_bot_mission_worker',
                daemon=True,
            )
            try:
                self._worker.start()
            except Exception as exc:
                self._running = False
                response.success = False
                response.message = f'No se pudo iniciar el hilo de misión: {exc}'
                return response

        response.success = True
        response.message = (
            'Misión aceptada. El servidor validará Nav2 y AMCL antes de moverse; '
            'consulte /dif_bot/mission/progress.'
        )
        return response

    def run_mission(self):
        navigator = None
        current_index = 0
        total = 0

        try:
            frame, points = self.load_waypoints()
            total = len(points)
            waypoint_timeout = self._positive_parameter('waypoint_timeout_sec')

            self.publish_progress(f'INICIANDO|0|{total}|Validando Nav2, AMCL y waypoints')

            navigator = BasicNavigator()
            sim_time = bool(self.get_parameter('use_sim_time').value)
            result = navigator.set_parameters([
                Parameter('use_sim_time', value=sim_time)
            ])
            if result and not result[0].successful:
                raise RuntimeError(
                    f'No se pudo configurar use_sim_time en BasicNavigator: '
                    f'{result[0].reason}'
                )

            self._wait_for_nav2_and_localization(navigator)

            for current_index, point in enumerate(points, start=1):
                if self._shutdown_event.is_set() or not rclpy.ok():
                    raise RuntimeError('Misión interrumpida por cierre del sistema.')

                if not navigator.nav_to_pose_client.wait_for_server(
                    timeout_sec=self._positive_parameter('action_server_timeout_sec')
                ):
                    raise TimeoutError(
                        'navigate_to_pose dejó de estar disponible antes del '
                        f'waypoint {current_index}.'
                    )

                pose = PoseStamped()
                pose.header.frame_id = frame
                pose.header.stamp = navigator.get_clock().now().to_msg()
                pose.pose.position.x = point['x']
                pose.pose.position.y = point['y']

                yaw = math.radians(point['yaw_deg'])
                pose.pose.orientation.z = math.sin(yaw / 2.0)
                pose.pose.orientation.w = math.cos(yaw / 2.0)

                name = point['name']
                self.publish_progress(
                    f'EN_RUTA|{current_index}|{total}|{name}'
                )

                accepted = navigator.goToPose(pose)
                if not accepted:
                    self.publish_progress(
                        f'FALLIDA|{current_index}|{total}|{name}|Meta rechazada por Nav2'
                    )
                    return

                waypoint_deadline = time.monotonic() + waypoint_timeout
                last_feedback_time = 0.0

                while rclpy.ok() and not navigator.isTaskComplete():
                    if self._shutdown_event.is_set():
                        self._cancel_current_goal(navigator)
                        raise RuntimeError('Misión interrumpida por apagado del servidor.')

                    if time.monotonic() >= waypoint_deadline:
                        self._cancel_current_goal(navigator)
                        self.publish_progress(
                            f'FALLIDA|{current_index}|{total}|{name}|'
                            f'Timeout de navegación ({waypoint_timeout:.0f}s)'
                        )
                        return

                    now = time.monotonic()
                    feedback = navigator.getFeedback()
                    if (
                        feedback is not None
                        and hasattr(feedback, 'distance_remaining')
                        and now - last_feedback_time >= 1.0
                    ):
                        self.publish_progress(
                            f'EN_RUTA|{current_index}|{total}|{name}|'
                            f'dist={feedback.distance_remaining:.2f}m'
                        )
                        last_feedback_time = now

                    time.sleep(0.05)

                if not rclpy.ok():
                    raise RuntimeError('ROS 2 se cerró durante la navegación.')

                task_result = navigator.getResult()
                if task_result != TaskResult.SUCCEEDED:
                    detail = (
                        'cancelada' if task_result == TaskResult.CANCELED
                        else f'fallida (resultado={task_result})'
                    )
                    self.publish_progress(
                        f'FALLIDA|{current_index}|{total}|{name}|Meta {detail}'
                    )
                    return

                self.publish_progress(
                    f'COMPLETADO|{current_index}|{total}|{name}'
                )

            self.publish_progress(
                f'MISION_COMPLETADA|{total}|{total}|Todos los waypoints alcanzados'
            )

        except Exception as exc:
            if rclpy.ok() and not self._shutdown_event.is_set():
                detail = f'{type(exc).__name__}: {exc}'.replace('|', '/')
                self.publish_progress(
                    f'ERROR|{current_index}|{total}|{detail}'
                )
                self.get_logger().error(detail)
        finally:
            if navigator is not None:
                try:
                    navigator.destroyNode()
                except Exception:
                    pass

            with self._lock:
                self._running = False
                self._worker = None

    def request_shutdown(self):
        self._shutdown_event.set()


def main(args=None):
    rclpy.init(args=args)
    node = MissionServer()
    executor = SingleThreadedExecutor()
    executor.add_node(node)

    try:
        executor.spin()
    except KeyboardInterrupt:
        pass
    finally:
        node.request_shutdown()
        worker = node._worker
        if worker is not None and worker.is_alive():
            worker.join(timeout=10.0)

        executor.shutdown()
        executor.remove_node(node)
        node.destroy_node()

        if rclpy.ok():
            rclpy.shutdown()


if __name__ == '__main__':
    main()
