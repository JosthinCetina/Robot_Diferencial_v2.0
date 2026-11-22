#!/usr/bin/env python3
"""Sequential waypoint mission service for dif_bot OS v2.0."""

import math
import threading
import time

import rclpy
from rclpy.executors import SingleThreadedExecutor
from rclpy.parameter import Parameter
import yaml

from ament_index_python.packages import get_package_share_directory
from geometry_msgs.msg import PoseStamped
from nav2_simple_commander.robot_navigator import BasicNavigator, TaskResult
from rclpy.node import Node
from std_msgs.msg import String
from std_srvs.srv import Trigger

class MissionServer(Node):

    def __init__(self):
        super().__init__('autonomous_mission_server')

        default_file = (
            get_package_share_directory('dif_bot_navigation')
            + '/config/waypoints.yaml'
        )

        self.declare_parameter('waypoints_file', default_file)

        self._lock = threading.Lock()
        self._running = False
        self._worker = None

        self._progress = self.create_publisher(
            String,
            '/dif_bot/mission/progress',
            10
        )

        self._service = self.create_service(
            Trigger,
            '/start_autonomous_mission',
            self.start_callback
        )

        self.get_logger().info(
            'Servicio listo: /start_autonomous_mission'
        )

    def publish_progress(self, text):
        msg = String()
        msg.data = text
        self._progress.publish(msg)
        self.get_logger().info(text)

    def start_callback(self, request, response):
        del request

        with self._lock:
            if self._running:
                response.success = False
                response.message = 'Ya existe una misión en ejecución.'
                return response

            self._running = True

            self._worker = threading.Thread(
                target=self.run_mission,
                daemon=True
            )

            self._worker.start()

        response.success = True
        response.message = (
            'Misión aceptada. Consulte /dif_bot/mission/progress.'
        )

        return response

    def load_waypoints(self):
        path = self.get_parameter(
            'waypoints_file'
        ).get_parameter_value().string_value

        with open(path, 'r', encoding='utf-8') as stream:
            data = yaml.safe_load(stream)

        mission = data.get('mission', {})
        frame = mission.get('frame_id', 'map')
        points = mission.get('waypoints', [])

        if not points:
            raise ValueError(
                'waypoints.yaml no contiene waypoints.'
            )

        return frame, points

    def run_mission(self):
        navigator = None

        try:
            frame, points = self.load_waypoints()

            self.publish_progress(
                f'INICIANDO|0|{len(points)}|Preparando Nav2'
            )

            navigator = BasicNavigator()

            # BasicNavigator recibe la misma configuración de tiempo
            # que utiliza el servidor de misiones.
            navigator.set_parameters([
                Parameter(
                    'use_sim_time',
                    value=self.get_parameter('use_sim_time').value
                )
            ])

            navigator.waitUntilNav2Active()

            for index, point in enumerate(points, start=1):

                pose = PoseStamped()
                pose.header.frame_id = frame
                pose.header.stamp = (
                    navigator.get_clock().now().to_msg()
                )

                pose.pose.position.x = float(point['x'])
                pose.pose.position.y = float(point['y'])

                yaw = math.radians(
                    float(point.get('yaw_deg', 0.0))
                )

                pose.pose.orientation.z = math.sin(yaw / 2.0)
                pose.pose.orientation.w = math.cos(yaw / 2.0)

                name = str(
                    point.get('name', f'Waypoint_{index}')
                )

                self.publish_progress(
                    f'EN_RUTA|{index}|{len(points)}|{name}'
                )

                navigator.goToPose(pose)

                while not navigator.isTaskComplete():

                    feedback = navigator.getFeedback()

                    if (
                        feedback is not None
                        and hasattr(feedback, 'distance_remaining')
                    ):
                        self.publish_progress(
                            f'EN_RUTA|{index}|{len(points)}|'
                            f'{name}|'
                            f'dist={feedback.distance_remaining:.2f}m'
                        )

                    time.sleep(0.25)

                result = navigator.getResult()

                if result != TaskResult.SUCCEEDED:

                    self.publish_progress(
                        f'FALLIDA|{index}|{len(points)}|'
                        f'{name}|resultado={result}'
                    )

                    return

                self.publish_progress(
                    f'COMPLETADO|{index}|{len(points)}|{name}'
                )

            self.publish_progress(
                f'MISION_COMPLETADA|{len(points)}|{len(points)}|'
                'Todos los waypoints alcanzados'
            )

        except Exception as exc:

            self.publish_progress(
                f'ERROR|0|0|{type(exc).__name__}: {exc}'
            )

        finally:

            if navigator is not None:
                try:
                    navigator.destroyNode()
                except Exception:
                    pass

            with self._lock:
                self._running = False

def main(args=None):

    rclpy.init(args=args)

    node = MissionServer()
    executor = SingleThreadedExecutor()
    executor.add_node(node)

    try:
        # El servidor de misiones utiliza un executor propio.
        # BasicNavigator puede utilizar el executor global de rclpy
        # desde el hilo de ejecución de cada misión.
        executor.spin()

    except KeyboardInterrupt:
        pass

    finally:
        executor.shutdown()
        executor.remove_node(node)
        node.destroy_node()

        if rclpy.ok():
            rclpy.shutdown()


if __name__ == '__main__':
    main()
