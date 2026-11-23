import os

from ament_index_python.packages import get_package_share_directory
from launch import LaunchDescription
from launch.conditions import IfCondition, UnlessCondition
from launch.actions import (
    DeclareLaunchArgument,
    IncludeLaunchDescription,
    LogInfo,
    RegisterEventHandler,
)
from launch.event_handlers import OnProcessExit
from launch.launch_description_sources import PythonLaunchDescriptionSource
from launch.substitutions import Command, LaunchConfiguration
from launch_ros.actions import Node
from launch_ros.parameter_descriptions import ParameterValue


def generate_launch_description():
    description_share = get_package_share_directory('dif_bot_description')
    gazebo_share = get_package_share_directory('dif_bot_gazebo')
    ros_gz_share = get_package_share_directory('ros_gz_sim')

    world_file = os.path.join(gazebo_share, 'worlds', 'my_world.sdf')
    xacro_file = os.path.join(
        description_share, 'urdf', 'dif_bot_description.urdf.xacro'
    )
    gz_launch_file = os.path.join(
        ros_gz_share, 'launch', 'gz_sim.launch.py'
    )

    use_sim_time = LaunchConfiguration('use_sim_time')
    use_ros2_control = LaunchConfiguration('use_ros2_control')
    world_name = LaunchConfiguration('world_name')

    # Expand Xacro once as a launch substitution and provide the exact same
    # description to robot_state_publisher and ros_gz_sim/create.
    robot_description = ParameterValue(
        Command([
            'xacro ',
            xacro_file,
            ' use_ros2_control:=',
            use_ros2_control,
        ]),
        value_type=str,
    )

    # Use the official ros_gz_sim launch action. It sets Gazebo resource and
    # system-plugin search paths from installed ROS packages.
    gazebo = IncludeLaunchDescription(
        PythonLaunchDescriptionSource(gz_launch_file),
        launch_arguments={
            'gz_args': ['-r -v 3 ', world_file],
            'on_exit_shutdown': 'true',
        }.items(),
    )

    robot_state_publisher = Node(
        package='robot_state_publisher',
        executable='robot_state_publisher',
        name='robot_state_publisher',
        parameters=[{
            'robot_description': robot_description,
            'use_sim_time': use_sim_time,
        }],
        output='screen',
    )

    # Pass the URDF as a ROS parameter rather than relying on discovery and
    # transient-local delivery of /robot_description. Explicit world name also
    # avoids the /gazebo/worlds discovery request in ros_gz_sim/create.
    spawn_robot = Node(
        package='ros_gz_sim',
        executable='create',
        arguments=[
            '-world', world_name,
            '-param', 'robot_description',
            '-name', 'dif_bot',
            '-x', '0.0',
            '-y', '0.0',
            '-z', '0.0',
        ],
        parameters=[{'robot_description': robot_description}],
        output='screen',
    )

    sensor_bridge = Node(
        package='ros_gz_bridge',
        executable='parameter_bridge',
        name='sensor_bridge',
        arguments=[
            '/clock@rosgraph_msgs/msg/Clock[gz.msgs.Clock',
            '/scan@sensor_msgs/msg/LaserScan[gz.msgs.LaserScan',
            '/imu/data@sensor_msgs/msg/Imu[gz.msgs.IMU',
            '/camera/image@sensor_msgs/msg/Image[gz.msgs.Image',
        ],
        parameters=[{'use_sim_time': use_sim_time}],
        output='screen',
    )

    jsb_spawner = Node(
        package='controller_manager',
        executable='spawner',
        arguments=[
            'joint_state_broadcaster',
            '--controller-manager',
            '/controller_manager',
            '--controller-manager-timeout',
            '60',
            '--switch-timeout',
            '30',
            '--service-call-timeout',
            '35',
        ],
        output='screen',
        condition=IfCondition(use_ros2_control),
    )

    diff_spawner = Node(
        package='controller_manager',
        executable='spawner',
        arguments=[
            'diff_drive_controller',
            '--controller-manager',
            '/controller_manager',
            '--controller-manager-timeout',
            '60',
            '--switch-timeout',
            '30',
            '--service-call-timeout',
            '35',
        ],
        output='screen',
        condition=IfCondition(use_ros2_control),
    )

    # In ros2_control mode, controller_manager is created by the Gazebo model
    # plugin. Start the spawners only after create has returned successfully.
    start_controllers_after_spawn = RegisterEventHandler(
        OnProcessExit(
            target_action=spawn_robot,
            on_exit=[
                LogInfo(
                    msg=(
                        '[DIF_BOT] El proceso de inserción del robot terminó; '
                        'se inicia joint_state_broadcaster.'
                    )
                ),
                jsb_spawner,
            ],
        )
    )

    start_diff_drive_after_broadcaster = RegisterEventHandler(
        OnProcessExit(
            target_action=jsb_spawner,
            on_exit=[
                LogInfo(
                    msg='[DIF_BOT] Se inicia diff_drive_controller.'
                ),
                diff_spawner,
            ],
        )
    )

    native_bridge = Node(
        package='ros_gz_bridge',
        executable='parameter_bridge',
        name='native_diff_drive_bridge',
        arguments=[
            '/cmd_vel@geometry_msgs/msg/Twist]gz.msgs.Twist',
            '/odom_raw@nav_msgs/msg/Odometry[gz.msgs.Odometry',
        ],
        parameters=[{'use_sim_time': use_sim_time}],
        output='screen',
        condition=UnlessCondition(use_ros2_control),
    )

    return LaunchDescription([
        DeclareLaunchArgument(
            'use_sim_time',
            default_value='true',
        ),
        DeclareLaunchArgument(
            'use_ros2_control',
            default_value='true',
            description=(
                'true: gz_ros2_control + diff_drive_controller; '
                'false: Gazebo Sim DiffDrive system'
            ),
        ),
        DeclareLaunchArgument(
            'world_name',
            default_value='dif_bot_world',
            description='Nombre exacto del mundo declarado en my_world.sdf.',
        ),

        # Register handlers before the processes they observe.
        start_controllers_after_spawn,
        start_diff_drive_after_broadcaster,

        gazebo,
        robot_state_publisher,
        sensor_bridge,
        spawn_robot,
        native_bridge,
    ])
