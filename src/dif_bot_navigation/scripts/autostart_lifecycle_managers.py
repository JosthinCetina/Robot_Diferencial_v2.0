#!/usr/bin/env python3
"""Start Nav2 lifecycle managers after DDS service discovery has settled."""

import time

import rclpy
from nav2_msgs.srv import ManageLifecycleNodes
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

    def _start_manager(self, service_name, client):
        request = ManageLifecycleNodes.Request()
        request.command = ManageLifecycleNodes.Request.STARTUP
        future = client.call_async(request)
        deadline = time.monotonic() + TRANSITION_TIMEOUT_SEC

        while rclpy.ok() and not future.done() and time.monotonic() < deadline:
            rclpy.spin_once(self, timeout_sec=0.1)

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
            f'Gestor de ciclo de vida activo: {service_name}'
        )

    def start_all(self):
        self._wait_for_manager_services()

        # Nav2's lifecycle manager creates its internal service clients during
        # startup. Give Fast DDS time to match those endpoints before STARTUP;
        # otherwise a fast first transition can complete without its reply
        # reaching the manager client.
        self.get_logger().info(
            f'Esperando {DISCOVERY_SETTLE_SEC:.0f}s para estabilizar DDS '
            'antes de activar los nodos.'
        )
        time.sleep(DISCOVERY_SETTLE_SEC)

        # Localization must be active before the navigation costmaps/servers.
        for service_name in MANAGERS:
            self._start_manager(service_name, self._clients[service_name])

        self.get_logger().info(
            'Localización y servidores Nav2 completaron STARTUP.'
        )


def main(args=None):
    rclpy.init(args=args)
    node = LifecycleStartup()
    exit_code = 0
    try:
        node.start_all()
    except Exception as exc:
        node.get_logger().error(f'Falló el arranque de Nav2: {exc}')
        exit_code = 1
    finally:
        for client in node._clients.values():
            node.destroy_client(client)
        node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()
    return exit_code


if __name__ == '__main__':
    raise SystemExit(main())
