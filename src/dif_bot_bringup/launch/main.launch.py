import os
from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument, IncludeLaunchDescription, TimerAction
from launch.conditions import IfCondition
from launch.launch_description_sources import PythonLaunchDescriptionSource
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node
from ament_index_python.packages import get_package_share_directory


def generate_launch_description():
    gazebo_share = get_package_share_directory('dif_bot_gazebo')
    control_share = get_package_share_directory('dif_bot_control')
    nav_share = get_package_share_directory('dif_bot_navigation')
    use_sim_time = LaunchConfiguration('use_sim_time')
    use_ros2_control = LaunchConfiguration('use_ros2_control')
    launch_navigation = LaunchConfiguration('launch_navigation')

    sim = IncludeLaunchDescription(
        PythonLaunchDescriptionSource(os.path.join(gazebo_share, 'launch', 'gazebo.launch.py')),
        launch_arguments={'use_sim_time': use_sim_time, 'use_ros2_control': use_ros2_control}.items())

    mux = Node(package='twist_mux', executable='twist_mux', name='twist_mux',
        parameters=[os.path.join(control_share, 'config', 'twist_mux.yaml'), {'use_sim_time': use_sim_time}],
        remappings=[('cmd_vel_out', '/cmd_vel')], output='screen')

    stamper = Node(package='dif_bot_control', executable='cmd_vel_stamper',
        condition=IfCondition(use_ros2_control), parameters=[{'use_sim_time': use_sim_time}], output='screen')
    odometry_relay = Node(package='dif_bot_control', executable='odometry_relay',
        condition=IfCondition(use_ros2_control), output='screen')

    rosbridge = Node(package='rosbridge_server', executable='rosbridge_websocket',
        name='rosbridge_websocket', parameters=[{'port': 9090}], output='screen')
    relay = Node(package='dif_bot_web_bridge', executable='relay', name='web_relay_node', output='screen')
    robot_pose = Node(package='dif_bot_web_bridge', executable='robot_pose', name='robot_pose_node',
        parameters=[{'use_sim_time': use_sim_time}], output='screen')
    goal_bridge = Node(package='dif_bot_web_bridge', executable='goal_bridge', name='goal_bridge_node',
        parameters=[{'use_sim_time': use_sim_time}], output='screen')

    nav = IncludeLaunchDescription(
        PythonLaunchDescriptionSource(os.path.join(nav_share, 'launch', 'navigation.launch.py')),
        launch_arguments={'use_sim_time': use_sim_time}.items(), condition=IfCondition(launch_navigation))

    return LaunchDescription([
        DeclareLaunchArgument('use_sim_time', default_value='true'),
        DeclareLaunchArgument('use_ros2_control', default_value='true'),
        DeclareLaunchArgument('launch_navigation', default_value='true'),
        sim,
        TimerAction(period=8.0, actions=[mux, stamper, odometry_relay, rosbridge, relay, robot_pose, goal_bridge]),
        TimerAction(period=10.0, actions=[nav]),
    ])
