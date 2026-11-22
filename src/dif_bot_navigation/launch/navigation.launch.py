import os

from ament_index_python.packages import get_package_share_directory
from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node
from launch.conditions import IfCondition


def generate_launch_description():
    share = get_package_share_directory('dif_bot_navigation')
    params = LaunchConfiguration('params_file')
    map_file = LaunchConfiguration('map_file')
    rviz_config = LaunchConfiguration('rviz_config')
    launch_rviz = LaunchConfiguration('launch_rviz')
    ekf_yaml = LaunchConfiguration('ekf_params_file')
    waypoints = LaunchConfiguration('waypoints_file')
    use_sim_time = LaunchConfiguration('use_sim_time')
    autostart = LaunchConfiguration('autostart')

    localization_nodes = ['map_server', 'amcl']
    navigation_nodes = [
        'controller_server',
        'planner_server',
        'behavior_server',
        'bt_navigator',
    ]

    lifecycle_manager_parameters = {
        'use_sim_time': use_sim_time,
        'autostart': autostart,
        # WSL2/Gazebo can pause ROS process scheduling under CPU pressure.
        # Extend the bond deadline without hiding normal node exceptions.
        'bond_timeout': 15.0,
    }

    return LaunchDescription([
        DeclareLaunchArgument('use_sim_time', default_value='true'),
        DeclareLaunchArgument('autostart', default_value='true'),
        DeclareLaunchArgument(
            'map_file',
            default_value=os.path.join(share, 'maps', 'my_map.yaml'),
            description='Mapa YAML que usarán Map Server y AMCL.',
        ),
        DeclareLaunchArgument('launch_rviz', default_value='false'),
        DeclareLaunchArgument(
            'rviz_config',
            default_value=os.path.join(share, 'config', 'navigation.rviz'),
        ),
        DeclareLaunchArgument(
            'params_file',
            default_value=os.path.join(share, 'config', 'nav2_params.yaml'),
        ),
        DeclareLaunchArgument(
            'ekf_params_file',
            default_value=os.path.join(share, 'config', 'ekf.yaml'),
        ),
        DeclareLaunchArgument(
            'waypoints_file',
            default_value=os.path.join(share, 'config', 'waypoints.yaml'),
        ),

        Node(
            package='robot_localization',
            executable='ekf_node',
            name='ekf_filter_node',
            output='screen',
            parameters=[ekf_yaml, {'use_sim_time': use_sim_time}],
            remappings=[('odometry/filtered', '/odom_filtered')],
        ),
        Node(
            package='dif_bot_navigation',
            executable='mission_server',
            name='autonomous_mission_server',
            output='screen',
            parameters=[{
                'use_sim_time': use_sim_time,
                'waypoints_file': waypoints,
                'nav2_startup_timeout_sec': 180.0,
                'amcl_pose_timeout_sec': 60.0,
                'action_server_timeout_sec': 30.0,
                'waypoint_timeout_sec': 240.0,
            }],
        ),
        Node(
            package='nav2_map_server',
            executable='map_server',
            name='map_server',
            output='screen',
            parameters=[params, {'use_sim_time': use_sim_time, 'yaml_filename': map_file}],
        ),
        Node(
            package='nav2_amcl',
            executable='amcl',
            name='amcl',
            output='screen',
            parameters=[params],
        ),
        Node(
            package='nav2_controller',
            executable='controller_server',
            name='controller_server',
            output='screen',
            parameters=[params],
            remappings=[('cmd_vel', '/cmd_vel_nav')],
        ),
        Node(
            package='nav2_planner',
            executable='planner_server',
            name='planner_server',
            output='screen',
            parameters=[params],
        ),
        Node(
            package='nav2_behaviors',
            executable='behavior_server',
            name='behavior_server',
            output='screen',
            parameters=[params],
            remappings=[('cmd_vel', '/cmd_vel_nav')],
        ),
        Node(
            package='nav2_bt_navigator',
            executable='bt_navigator',
            name='bt_navigator',
            output='screen',
            parameters=[params],
        ),
        Node(
            package='nav2_lifecycle_manager',
            executable='lifecycle_manager',
            name='lifecycle_manager_localization',
            output='screen',
            parameters=[{
                **lifecycle_manager_parameters,
                'node_names': localization_nodes,
            }],
        ),
        Node(
            package='rviz2',
            executable='rviz2',
            name='nav2_rviz',
            arguments=['-d', rviz_config],
            parameters=[{'use_sim_time': use_sim_time}],
            output='screen',
            condition=IfCondition(launch_rviz),
        ),
        Node(
            package='nav2_lifecycle_manager',
            executable='lifecycle_manager',
            name='lifecycle_manager_navigation',
            output='screen',
            parameters=[{
                **lifecycle_manager_parameters,
                'node_names': navigation_nodes,
            }],
        ),
    ])
