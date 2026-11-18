#!/usr/bin/env python3
"""Convert geometry_msgs/Twist to TwistStamped for ros2_control Jazzy."""
import rclpy
from rclpy.node import Node
from geometry_msgs.msg import Twist, TwistStamped

class CmdVelStamper(Node):
    def __init__(self):
        super().__init__('cmd_vel_stamper')
        self.declare_parameter('input_topic', '/cmd_vel')
        self.declare_parameter('output_topic', '/diff_drive_controller/cmd_vel')
        input_topic = self.get_parameter('input_topic').value
        output_topic = self.get_parameter('output_topic').value
        self.publisher = self.create_publisher(TwistStamped, output_topic, 10)
        self.subscription = self.create_subscription(Twist, input_topic, self.callback, 10)
        self.get_logger().info(f'{input_topic} (Twist) -> {output_topic} (TwistStamped)')

    def callback(self, message):
        stamped = TwistStamped()
        stamped.header.stamp = self.get_clock().now().to_msg()
        stamped.header.frame_id = 'base_footprint'
        stamped.twist = message
        self.publisher.publish(stamped)

def main(args=None):
    rclpy.init(args=args)
    node = CmdVelStamper()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()

if __name__ == '__main__':
    main()
