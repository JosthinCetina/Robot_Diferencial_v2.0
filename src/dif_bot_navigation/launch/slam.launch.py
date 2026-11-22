import os

from ament_index_python.packages import get_package_share_directory
from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument
from launch.conditions import IfCondition
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node


def generate_launch_description():
    share = get_package_share_directory('dif_bot_navigation')
    params_file = LaunchConfiguration('params_file')
    ekf_params_file = LaunchConfiguration('ekf_params_file')
    use_sim_time = LaunchConfiguration('use_sim_time')
    launch_ekf = LaunchConfiguration('launch_ekf')

    # SLAM Toolbox needs odom -> base_footprint. With ros2_control,
    # diff_drive_controller publishes /odom_raw and EKF supplies that TF.
    ekf = Node(
        package='robot_localization',
        executable='ekf_node',
        name='ekf_filter_node',
        output='screen',
        parameters=[ekf_params_file, {'use_sim_time': use_sim_time}],
        remappings=[('odometry/filtered', '/odom_filtered')],
        condition=IfCondition(launch_ekf),
    )

    slam = Node(
        package='slam_toolbox',
        executable='async_slam_toolbox_node',
        name='slam_toolbox',
        output='screen',
        parameters=[params_file, {'use_sim_time': use_sim_time}],
    )

    return LaunchDescription([
        DeclareLaunchArgument('use_sim_time', default_value='true'),
        DeclareLaunchArgument('launch_ekf', default_value='true'),
        DeclareLaunchArgument(
            'params_file',
            default_value=os.path.join(share, 'config', 'mapper_params_online_async.yaml'),
        ),
        DeclareLaunchArgument(
            'ekf_params_file',
            default_value=os.path.join(share, 'config', 'ekf.yaml'),
        ),
        ekf,
        slam,
    ])
