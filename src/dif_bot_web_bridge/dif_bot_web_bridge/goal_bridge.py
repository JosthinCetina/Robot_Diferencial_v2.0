#!/usr/bin/env python3
import math
import rclpy
from rclpy.node import Node
from rclpy.action import ActionClient
import time
from geometry_msgs.msg import PoseStamped, Twist
from std_msgs.msg import String
from nav2_msgs.action import NavigateToPose
from action_msgs.msg import GoalStatus
from action_msgs.srv import CancelGoal
from std_srvs.srv import Trigger
from rclpy.time import Time


class GoalBridgeNode(Node):
    def __init__(self):
        super().__init__('goal_bridge_node')
        self.nav_client = ActionClient(self, NavigateToPose, 'navigate_to_pose')
        self.sub_goal = self.create_subscription(
            PoseStamped, '/dif_bot/web/goal_pose', self.goal_cb, 10
        )
        self.pub_status = self.create_publisher(
            String, '/dif_bot/web/nav_status', 10
        )

        self.last_robot_pose = None
        self.last_robot_pose_wall = 0.0
        self.xy_goal_tolerance = 0.05
        self.yaw_goal_tolerance = 0.10

        self.pose_sub = self.create_subscription(
            PoseStamped,
            '/dif_bot/web/robot_pose',
            self.robot_pose_cb,
            10,
        )

        self.stop_web_pub = self.create_publisher(Twist, '/cmd_vel_web', 10)
        self.stop_teleop_pub = self.create_publisher(Twist, '/cmd_vel_teleop', 10)
        self.cancel_client = self.create_client(
            CancelGoal, '/navigate_to_pose/_action/cancel_goal'
        )
        self.stop_service = self.create_service(
            Trigger, '/dif_bot/stop', self.stop_cb
        )

    def stop_cb(self, request, response):
        del request
        zero = Twist()
        self.stop_web_pub.publish(zero)
        self.stop_teleop_pub.publish(zero)

        if not self.cancel_client.wait_for_service(timeout_sec=1.0):
            response.success = False
            response.message = (
                'Se publicaron velocidades cero, pero el servicio de cancelación '
                'de NavigateToPose no está disponible. Revise Nav2.'
            )
            return response

        cancel_request = CancelGoal.Request()
        cancel_request.goal_info.goal_id.uuid = [0] * 16
        cancel_request.goal_info.stamp.sec = 0
        cancel_request.goal_info.stamp.nanosec = 0
        future = self.cancel_client.call_async(cancel_request)
        future.add_done_callback(self.stop_cancel_result_cb)
        response.success = True
        response.message = (
            'Paro lógico solicitado: velocidades cero publicadas y solicitud '
            'de cancelación global enviada a NavigateToPose.'
        )
        return response

    def stop_cancel_result_cb(self, future):
        try:
            result = future.result()
            self.get_logger().info(
                f'Cancelación Nav2 procesada; return_code={result.return_code}, '
                f'goals_canceling={len(result.goals_canceling)}'
            )
        except Exception as exc:
            self.get_logger().error(
                f'Falló la solicitud de cancelación Nav2: {exc}'
            )

    def goal_cb(self, msg):
        if not self.nav_client.wait_for_server(timeout_sec=2.0):
            self.publish_status('ERROR: Servidor Nav2 inactivo')
            return

        goal_msg = NavigateToPose.Goal()
        goal_msg.pose = msg
        goal_msg.pose.header.frame_id = 'map'
        goal_msg.pose.header.stamp = Time().to_msg()

        # Replace a zero quaternion with the identity quaternion.
        q = goal_msg.pose.pose.orientation
        norm_sq = q.x * q.x + q.y * q.y + q.z * q.z + q.w * q.w
        if norm_sq < 1e-4:
            q.x = 0.0
            q.y = 0.0
            q.z = 0.0
            q.w = 1.0

        target_goal = goal_msg.pose
        self.publish_status(
            f'PROCESANDO: Evaluando ruta hacia '
            f'X={msg.pose.position.x:.2f}, Y={msg.pose.position.y:.2f}...'
        )

        send_goal_future = self.nav_client.send_goal_async(
            goal_msg, feedback_callback=self.feedback_cb
        )
        # Keep each result paired with its own target if requests overlap.
        send_goal_future.add_done_callback(
            lambda future, goal=target_goal: self.goal_response_cb(future, goal)
        )

    def robot_pose_cb(self, msg):
        self.last_robot_pose = msg
        self.last_robot_pose_wall = time.monotonic()

    @staticmethod
    def quaternion_yaw(q):
        return math.atan2(
            2.0 * (q.w * q.z + q.x * q.y),
            1.0 - 2.0 * (q.y * q.y + q.z * q.z),
        )

    @staticmethod
    def angle_error(a, b):
        return abs((a - b + math.pi) % (2.0 * math.pi) - math.pi)

    def goal_response_cb(self, future, target_goal):
        try:
            goal_handle = future.result()
        except Exception as exc:
            self.publish_status(f'ERROR: No se pudo enviar la meta: {exc}')
            return

        if not goal_handle.accepted:
            self.publish_status(
                'RECHAZADO: Meta inaccesible (obstáculo o fuera del mapa)'
            )
            return

        self.publish_status('EN_RUTA: Ejecutando comandos de velocidad...')
        result_future = goal_handle.get_result_async()
        result_future.add_done_callback(
            lambda result, goal=target_goal: self.result_cb(result, goal)
        )

    def feedback_cb(self, feedback_msg):
        distance = feedback_msg.feedback.distance_remaining
        self.publish_status(
            f'EN_RUTA: Distancia restante {distance:.2f} m'
        )

    def result_cb(self, future, target_goal):
        try:
            wrapped = future.result()
        except Exception as exc:
            self.publish_status(
                f'ERROR: No se pudo obtener el resultado de Nav2: {exc}'
            )
            self.get_logger().error(
                f'No se pudo obtener resultado NavigateToPose: {exc}'
            )
            return

        status = int(wrapped.status)
        nav_result = getattr(wrapped, 'result', None)
        error_code = getattr(nav_result, 'error_code', None)
        error_msg = str(
            getattr(nav_result, 'error_msg', '') or ''
        ).replace('\n', ' ').strip() or 'sin detalle proporcionado por Nav2'
        if len(error_msg) > 220:
            error_msg = error_msg[:217] + '...'

        nav_detail = (
            f'error_code={error_code if error_code is not None else "N/D"}; '
            f'error_msg={error_msg}'
        )

        if status == GoalStatus.STATUS_SUCCEEDED:
            self.publish_status(
                f'EXITO: Meta alcanzada; Nav2 status=SUCCEEDED; {nav_detail}'
            )
            return

        if status == GoalStatus.STATUS_ABORTED:
            pose = self.last_robot_pose
            pose_age = time.monotonic() - self.last_robot_pose_wall
            geometry = None

            if (
                pose is not None
                and pose_age <= 2.0
                and pose.header.frame_id.lstrip('/')
                == target_goal.header.frame_id.lstrip('/')
            ):
                dx = (
                    target_goal.pose.position.x - pose.pose.position.x
                )
                dy = (
                    target_goal.pose.position.y - pose.pose.position.y
                )
                xy_error = math.hypot(dx, dy)
                goal_yaw = self.quaternion_yaw(
                    target_goal.pose.orientation
                )
                current_yaw = self.quaternion_yaw(
                    pose.pose.orientation
                )
                yaw_error = self.angle_error(goal_yaw, current_yaw)
                geometry = (xy_error, yaw_error)

                if (
                    xy_error <= self.xy_goal_tolerance
                    and yaw_error <= self.yaw_goal_tolerance
                ):
                    message = (
                        'EXITO_CON_ADVERTENCIA: objetivo alcanzado y verificado '
                        f'(XY={xy_error:.3f}m <= {self.xy_goal_tolerance:.3f}m; '
                        f'error_yaw={yaw_error:.3f}rad <= '
                        f'{self.yaw_goal_tolerance:.3f}rad). '
                        f'Nav2 reportó status=ABORTED; {nav_detail}'
                    )
                    self.publish_status(message)
                    self.get_logger().warning(message)
                    return

            if geometry is not None:
                message = (
                    'ABORTADO_NAV2: la acción terminó ABORTED; '
                    f'error_XY={geometry[0]:.3f}m '
                    f'(límite {self.xy_goal_tolerance:.3f}m); '
                    f'error_yaw={geometry[1]:.3f}rad '
                    f'(límite {self.yaw_goal_tolerance:.3f}rad). '
                    f'{nav_detail}'
                )
            else:
                message = (
                    'ABORTADO_NAV2: la acción terminó ABORTED y no se pudo '
                    'verificar la pose final en el mismo frame del objetivo '
                    f'(pose_recibida_hace={pose_age:.2f}s). {nav_detail}'
                )

            self.publish_status(message)
            self.get_logger().error(message)
            return

        if status == GoalStatus.STATUS_CANCELED:
            self.publish_status(
                f'CANCELADO: Navegación interrumpida; {nav_detail}'
            )
        else:
            self.publish_status(
                f'FINALIZADO: estado de acción={status}; {nav_detail}'
            )

    def publish_status(self, text):
        msg = String()
        msg.data = text
        self.pub_status.publish(msg)


def main(args=None):
    rclpy.init(args=args)
    node = GoalBridgeNode()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    node.destroy_node()
    rclpy.shutdown()


if __name__ == '__main__':
    main()
