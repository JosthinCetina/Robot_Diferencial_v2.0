import os
from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument, ExecuteProcess, TimerAction
from launch.conditions import IfCondition, UnlessCondition
from launch.substitutions import Command, LaunchConfiguration
from launch_ros.actions import Node
from launch_ros.parameter_descriptions import ParameterValue
from ament_index_python.packages import get_package_share_directory


def generate_launch_description():
    description_share = get_package_share_directory('dif_bot_description')
    gazebo_share = get_package_share_directory('dif_bot_gazebo')
    world = os.path.join(gazebo_share, 'worlds', 'my_world.sdf')
    xacro_file = os.path.join(description_share, 'urdf', 'dif_bot_description.urdf.xacro')

    use_sim_time = LaunchConfiguration('use_sim_time')
    use_ros2_control = LaunchConfiguration('use_ros2_control')
    robot_description = ParameterValue(
        Command(['xacro ', xacro_file, ' use_ros2_control:=', use_ros2_control]), value_type=str)

    gz = ExecuteProcess(cmd=['gz', 'sim', '-r', '-v', '3', world], output='screen')
    rsp = Node(package='robot_state_publisher', executable='robot_state_publisher',
               parameters=[{'robot_description': robot_description, 'use_sim_time': use_sim_time}],
               output='screen')
    create = Node(package='ros_gz_sim', executable='create',
                  arguments=['-name', 'dif_bot', '-topic', 'robot_description', '-x', '0', '-y', '0', '-z', '0.0'],
                  output='screen')

    sensor_bridge = Node(package='ros_gz_bridge', executable='parameter_bridge',
        arguments=[
            '/clock@rosgraph_msgs/msg/Clock[gz.msgs.Clock',
            '/scan@sensor_msgs/msg/LaserScan[gz.msgs.LaserScan',
            '/imu/data@sensor_msgs/msg/Imu[gz.msgs.IMU',
            '/camera/image@sensor_msgs/msg/Image[gz.msgs.Image',
        ], output='screen', parameters=[{'use_sim_time': use_sim_time}])

    jsb_spawner = Node(package='controller_manager', executable='spawner',
        arguments=['joint_state_broadcaster', '--controller-manager', '/controller_manager'], output='screen')
    diff_spawner = Node(package='controller_manager', executable='spawner',
        arguments=['diff_drive_controller', '--controller-manager', '/controller_manager'], output='screen')

    native_bridge = Node(package='ros_gz_bridge', executable='parameter_bridge',
        arguments=[
            '/cmd_vel@geometry_msgs/msg/Twist]gz.msgs.Twist',
            '/odom_raw@nav_msgs/msg/Odometry[gz.msgs.Odometry',
        ], output='screen', parameters=[{'use_sim_time': use_sim_time}],
        condition=UnlessCondition(use_ros2_control))

    return LaunchDescription([
        DeclareLaunchArgument('use_sim_time', default_value='true'),
        DeclareLaunchArgument('use_ros2_control', default_value='true',
            description='true: gz_ros2_control + diff_drive_controller; false: Gazebo Sim DiffDrive system'),
        gz, rsp,
        TimerAction(period=6.0, actions=[create, sensor_bridge]),
        TimerAction(period=7.0, actions=[jsb_spawner, diff_spawner], condition=IfCondition(use_ros2_control)),
        native_bridge,
    ])
