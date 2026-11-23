#!/usr/bin/env python3
"""Start Nav2 lifecycle managers after DDS service discovery has settled."""

import time

import rclpy
from nav2_msgs.srv import ManageLifecycleNodes
from rclpy.executors import SingleThreadedExecutor
from rclpy.node import Node


MANAGERS = (
    '/lifecycle_manager_localization/manage_nodes',
    '/lifecycle_manager_navigation/manage_nodes',
)
SERVICE_DISCOVERY_TIMEOUT_SEC = 60.0
DISCOVERY_SETTLE_SEC = 3.0
TRANSITION_TIMEOUT_SEC = 180.0


class LifecycleStartup(Node):
    """Wait for lifecycle-manager services, then start localization and Nav2."""

    def __init__(self):
        super().__init__('nav2_lifecycle_startup')
        self._clients = {
            service_name: self.create_client(ManageLifecycleNodes, service_name)
            for service_name in MANAGERS
        }

    def _wait_for_manager_services(self):
        deadline = time.monotonic() + SERVICE_DISCOVERY_TIMEOUT_SEC
        for service_name, client in self._clients.items():
            while rclpy.ok() and time.monotonic() < deadline:
                if client.wait_for_service(timeout_sec=0.5):
                    self.get_logger().info(
                        f'Servicio de ciclo de vida disponible: {service_name}'
                    )
                    break
            else:
                raise TimeoutError(
                    f'No apareció el servicio de ciclo de vida {service_name} '
                    f'en {SERVICE_DISCOVERY_TIMEOUT_SEC:.0f}s.'
                )

    def _start_manager(self, service_name, client, executor):
        request = ManageLifecycleNodes.Request()
        request.command = ManageLifecycleNodes.Request.STARTUP
        self.get_logger().info(f'Enviando STARTUP a {service_name}.')
        future = client.call_async(request)
        deadline = time.monotonic() + TRANSITION_TIMEOUT_SEC

        # Process one executor event at a time while waiting for the service
        # response. In the deployed ROS 2 Jazzy environment,
        # spin_until_future_complete raised an internal _executor_event error
        # and terminated this coordinator after localization STARTUP.
        while (
            rclpy.ok()
            and not future.done()
            and time.monotonic() < deadline
        ):
            executor.spin_once(timeout_sec=0.1)

        if not future.done():
            client.remove_pending_request(future)
            raise TimeoutError(
                f'{service_name} no respondió STARTUP en '
                f'{TRANSITION_TIMEOUT_SEC:.0f}s.'
            )

        response = future.result()
        if response is None or not response.success:
            raise RuntimeError(
                f'El gestor {service_name} no pudo activar sus nodos.'
            )

        self.get_logger().info(
            f'Gestor de ciclo de vida activo: {service_name} '
            '(STARTUP respondió success=true).'
        )

    def start_all(self, executor):
        self._wait_for_manager_services()
        self.get_logger().info(
            f'Esperando {DISCOVERY_SETTLE_SEC:.0f}s para estabilizar DDS '
            'antes de activar los nodos.'
        )
        time.sleep(DISCOVERY_SETTLE_SEC)

        # Localization must be active before navigation costmaps and servers.
        for service_name in MANAGERS:
            self._start_manager(
                service_name, self._clients[service_name], executor
            )

        self.get_logger().info(
            'Localización y servidores Nav2 completaron STARTUP.'
        )


def main(args=None):
    rclpy.init(args=args)
    node = LifecycleStartup()
    executor = SingleThreadedExecutor()
    executor.add_node(node)
    exit_code = 0
    try:
        node.start_all(executor)
    except Exception as exc:
        node.get_logger().error(f'Falló el arranque de Nav2: {exc}')
        exit_code = 1
    finally:
        # destroy_node() already destroys its clients. Destroying them
        # explicitly first corrupts Node's internal client list and raises
        # KeyError during node cleanup.
        executor.remove_node(node)
        executor.shutdown()
        node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()
    return exit_code


if __name__ == '__main__':
    raise SystemExit(main())
