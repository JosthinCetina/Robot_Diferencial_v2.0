#!/usr/bin/env python3
"""Normalize diff_drive_controller odometry to /odom_raw for robot_localization."""
import rclpy
from rclpy.node import Node
from nav_msgs.msg import Odometry

class OdometryRelay(Node):
    def __init__(self):
        super().__init__('odometry_relay')
        self.declare_parameter('input_topic', '/diff_drive_controller/odom')
        self.declare_parameter('output_topic', '/odom_raw')
        source = self.get_parameter('input_topic').value
        target = self.get_parameter('output_topic').value
        self.publisher = self.create_publisher(Odometry, target, 20)
        self.subscription = self.create_subscription(Odometry, source, self.callback, 20)
        self.get_logger().info(f'Odometry relay: {source} -> {target}')

    def callback(self, message: Odometry):
        self.publisher.publish(message)

def main(args=None):
    rclpy.init(args=args)
    node = OdometryRelay()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()

if __name__ == '__main__':
    main()
