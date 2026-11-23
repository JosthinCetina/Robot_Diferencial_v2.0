from pathlib import Path
import ast
import math
import xml.etree.ElementTree as ET

import yaml

ROOT = Path(__file__).resolve().parents[1]


def _load_pgm_p5(path):
    data = path.read_bytes()
    marker = b'\n255\n'
    marker_index = data.find(marker)
    assert data.startswith(b'P5\n'), f'{path} debe ser un PGM binario P5.'
    assert marker_index >= 0, f'No se encontró el encabezado PGM de {path}.'

    header_end = marker_index + len(marker)
    header = data[:header_end].split()
    assert len(header) >= 4
    width, height, max_value = map(int, header[1:4])
    assert max_value == 255, 'El validador espera PGM de 8 bits.'
    pixels = data[header_end:]
    assert len(pixels) == width * height
    return width, height, pixels


def test_python_sources_parse():
    for path in ROOT.glob('src/**/*.py'):
        ast.parse(path.read_text(encoding='utf-8'), filename=str(path))


def test_package_manifests_are_valid_and_unique():
    names = []
    for path in ROOT.glob('src/*/package.xml'):
        root = ET.parse(path).getroot()
        names.append(root.findtext('name'))
        assert root.findtext('version') == '2.0.0'
        if root.findtext('name') == 'dif_bot_navigation':
            deps = {node.text for node in root.findall('exec_depend')}
            assert 'action_msgs' in deps
    assert len(names) == 6
    assert len(names) == len(set(names))


def test_all_yaml_configs_parse():
    for path in ROOT.glob('src/**/*.yaml'):
        with path.open(encoding='utf-8') as stream:
            yaml.safe_load(stream)


def test_both_drive_modes_are_present():
    xacro = (
        ROOT / 'src/dif_bot_description/urdf/dif_bot_description.urdf.xacro'
    ).read_text()
    assert 'gz_ros2_control/GazeboSimSystem' in xacro
    assert 'gz-sim-diff-drive-system' in xacro
    assert 'use_ros2_control' in xacro
    assert 'libgazebo_ros_diff_drive.so' not in xacro


def test_ekf_input_is_normalized_and_imu_fuses_gyro_z():
    ekf = yaml.safe_load(
        (ROOT / 'src/dif_bot_navigation/config/ekf.yaml').read_text()
    )
    params = ekf['ekf_filter_node']['ros__parameters']
    assert params['odom0'] == '/odom_raw'
    assert params['imu0'] == '/imu/data'
    assert params['publish_tf'] is True
    assert len(params['process_noise_covariance']) == 225

    # The simulator's orientation covariance was observed as all zeros.
    # Fuse the measured gyro Z rather than treating yaw as an absolute fix.
    imu_config = params['imu0_config']
    assert len(imu_config) == 15
    assert imu_config[5] is False
    assert imu_config[11] is True

    relay = (
        ROOT / 'src/dif_bot_control/dif_bot_control/odometry_relay.py'
    ).read_text()
    assert '/diff_drive_controller/odom' in relay
    assert '/odom_raw' in relay


def test_nav2_jazzy_behavior_topics_and_stamped_mode():
    nav = yaml.safe_load(
        (ROOT / 'src/dif_bot_navigation/config/nav2_params.yaml').read_text()
    )
    behavior = nav['behavior_server']['ros__parameters']
    assert 'local_costmap_topic' in behavior
    assert 'global_costmap_topic' in behavior
    assert 'local_footprint_topic' in behavior
    assert 'global_footprint_topic' in behavior
    assert behavior['enable_stamped_cmd_vel'] is False
    assert nav['controller_server']['ros__parameters']['odom_topic'] == '/odom_filtered'


def test_nav2_bt_action_ack_and_cancel_timeouts_are_wsl_tolerant():
    nav = yaml.safe_load(
        (ROOT / 'src/dif_bot_navigation/config/nav2_params.yaml').read_text()
    )
    bt = nav['bt_navigator']['ros__parameters']
    # Nav2 Jazzy expresses these BT action timeouts in milliseconds.
    # Twenty milliseconds caused false failures under WSL2 scheduling delays.
    assert bt['default_server_timeout'] >= 1000
    assert bt['default_cancel_timeout'] >= 1000
    assert bt['wait_for_service_timeout'] >= 1000


def test_nav2_lifecycle_has_extended_bond_timeout():
    launch = (
        ROOT / 'src/dif_bot_navigation/launch/navigation.launch.py'
    ).read_text()
    assert "'bond_timeout': 15.0" in launch
    assert 'lifecycle_manager_localization' in launch
    assert 'lifecycle_manager_navigation' in launch


def test_gazebo_sim_sensors_are_bridged():
    sensors = (
        ROOT / 'src/dif_bot_description/urdf/sensors.xacro'
    ).read_text()
    assert 'type="gpu_lidar"' in sensors
    assert '<gz_frame_id>laser_frame</gz_frame_id>' in sensors
    assert '<gz_frame_id>imu_link</gz_frame_id>' in sensors
    launch = (
        ROOT / 'src/dif_bot_gazebo/launch/gazebo.launch.py'
    ).read_text()
    assert 'ros_gz_bridge' in launch
    assert 'gz.msgs.LaserScan' in launch
    assert '/clock@rosgraph_msgs/msg/Clock[gz.msgs.Clock' in launch
    assert "'/cmd_vel@geometry_msgs/msg/Twist]gz.msgs.Twist'" in launch
    assert "'/odom_raw@nav_msgs/msg/Odometry[gz.msgs.Odometry'" in launch
    xacro = (
        ROOT / 'src/dif_bot_description/urdf/dif_bot_description.urdf.xacro'
    ).read_text()
    assert '<topic>/cmd_vel</topic>' in xacro
    assert '<odom_topic>/odom_raw</odom_topic>' in xacro


def test_default_waypoints_fall_in_free_cells_of_committed_map():
    maps_dir = ROOT / 'src/dif_bot_navigation/maps'
    map_yaml = yaml.safe_load((maps_dir / 'my_map.yaml').read_text())
    width, height, pixels = _load_pgm_p5(maps_dir / map_yaml['image'])
    resolution = float(map_yaml['resolution'])
    origin_x, origin_y, _ = map_yaml['origin']
    free_threshold = float(map_yaml['free_thresh'])
    occupied_threshold = float(map_yaml['occupied_thresh'])
    negate = int(map_yaml.get('negate', 0))

    waypoints = yaml.safe_load(
        (ROOT / 'src/dif_bot_navigation/config/waypoints.yaml').read_text()
    )['mission']['waypoints']

    assert width == 197 and height == 197
    assert resolution == 0.05
    assert len(waypoints) >= 3

    for point in [{'name': 'Pose inicial', 'x': 0.0, 'y': 0.0}, *waypoints]:
        mx = math.floor((float(point['x']) - origin_x) / resolution)
        my = math.floor((float(point['y']) - origin_y) / resolution)
        assert 0 <= mx < width and 0 <= my < height, (
            f"{point['name']} queda fuera del mapa."
        )

        # PGM rows are stored from top to bottom; map coordinates grow upwards.
        pgm_row = height - 1 - my
        pixel = pixels[pgm_row * width + mx]
        occupied_probability = (
            pixel / 255.0 if negate else (255 - pixel) / 255.0
        )
        assert occupied_probability < free_threshold, (
            f"{point['name']} no está en una celda libre "
            f"(pixel={pixel}, P(ocupado)={occupied_probability:.3f})."
        )
        assert occupied_probability <= occupied_threshold


def test_mission_server_has_bounded_waits_and_validation():
    mission = (
        ROOT / 'src/dif_bot_navigation/scripts/mission_server.py'
    ).read_text()
    assert 'from lifecycle_msgs.srv import GetState' in mission
    assert 'nav2_startup_timeout_sec' in mission
    assert 'amcl_pose_timeout_sec' in mission
    assert 'action_server_timeout_sec' in mission
    assert 'waypoint_timeout_sec' in mission
    assert 'time.monotonic()' in mission
    assert 'cancel_goal_async()' in mission
    assert 'math.isfinite' in mission


def test_mission_ui_and_service_are_connected():
    app = (ROOT / 'web/src/App.jsx').read_text()
    server = (
        ROOT / 'src/dif_bot_navigation/scripts/mission_server.py'
    ).read_text()
    assert '/start_autonomous_mission' in app
    assert 'std_srvs/Trigger' in app
    assert '/dif_bot/mission/progress' in app
    assert '/dif_bot/mission/progress' in server


def test_urdf_xacro_and_sdf_are_well_formed_xml():
    for relative in [
        'src/dif_bot_description/urdf/dif_bot_description.urdf.xacro',
        'src/dif_bot_description/urdf/sensors.xacro',
        'src/dif_bot_gazebo/worlds/my_world.sdf',
    ]:
        ET.parse(ROOT / relative)


def test_control_adapters_use_consistent_jazzy_topics():
    stamper = (
        ROOT / 'src/dif_bot_control/dif_bot_control/cmd_vel_stamper.py'
    ).read_text()
    relay = (
        ROOT / 'src/dif_bot_control/dif_bot_control/odometry_relay.py'
    ).read_text()
    pose = (
        ROOT / 'src/dif_bot_control/dif_bot_control/pose_controller.py'
    ).read_text()
    hardware = (
        ROOT / 'src/dif_bot_control/dif_bot_control/hardware_validation.py'
    ).read_text()
    assert '/cmd_vel' in stamper
    assert '/diff_drive_controller/cmd_vel' in stamper
    assert '/diff_drive_controller/odom' in relay
    assert '/odom_raw' in relay
    assert "'/odom_filtered'" in pose
    assert (
        "'/odom_filtered'" in hardware
        or "'/odom_filtered'" in hardware.replace('"', "'")
    )


def test_web_stop_is_documented_as_logical_not_safety_estop():
    app = (ROOT / 'web/src/App.jsx').read_text()
    readme = (ROOT / 'README.md').read_text()
    plan = (ROOT / 'docs/TEST_PLAN_JAZZY.md').read_text()
    assert 'No sustituye un E-stop físico' in app
    assert "name: '/dif_bot/stop'" in app
    assert 'No es un dispositivo E-stop físico' in readme
    assert 'sustituye un E-stop físico' in plan
    bridge = (
        ROOT / 'src/dif_bot_web_bridge/dif_bot_web_bridge/goal_bridge.py'
    ).read_text()
    assert '/dif_bot/stop' in bridge
    assert 'CancelGoal.Request()' in bridge
    assert '/navigate_to_pose/_action/cancel_goal' in bridge
    stop_fn = app.split('const forceStopRobot = () => {', 1)[1].split('};', 1)[0]
    assert 'connected' not in stop_fn


def test_github_publish_and_docker_clone_workflows_exist():
    publish = (ROOT / 'scripts/publish_github.sh').read_text()
    clone = (ROOT / 'docker-clone-run.sh').read_text()
    assert 'Robot_Diferencial_v2.0' in publish
    assert 'gh repo create' not in publish
    assert 'git push origin main' in publish
    assert r'\${' not in publish
    assert 'git clone --branch' in clone
    assert 'ROS_DOMAIN_ID' in clone
    assert 'ROS_DOMAIN_ID' in (ROOT / 'docker-run.sh').read_text()


def test_wsl_deployer_is_incremental_and_avoids_expensive_runtime_scans():
    deploy = (ROOT / 'deploy_wsl.sh').read_text()
    assert 'Robot_Diferencial_v2.0.git' in deploy
    assert 'git clone --branch' in deploy
    assert 'git pull --ff-only' in deploy
    assert 'docker build -t' in deploy
    assert 'colcon build' in deploy
    assert 'npm ci' in deploy and 'package-lock.json' in deploy
    assert 'START_DIF_BOT.sh' in deploy
    assert 'for id in base nav web' in deploy
    assert 'docker volume rm' not in deploy
    assert 'rosdep update' not in deploy
    assert 'ros2 action list' not in deploy
    assert 'DIAGNOSTIC_DIF_BOT.sh' not in deploy
    assert 'DIAG_CAPTURE' not in deploy


def test_startup_requires_rosbridge_and_production_frontend_before_nav2():
    start = (ROOT / 'START_DIF_BOT.sh').read_text()
    assert 'wait_for_robot_spawn 90' in start
    assert 'wait_for_ros2_controllers 150' in start
    assert 'run preview' in start
    assert 'wait_port 3000 45' in start
    assert 'wait_port 9090 20' in start
    assert 'No se inicia Nav2: la interfaz de teleoperación no está disponible.' in start


def test_ci_workflow_covers_static_checks_and_jazzy_build():
    workflow = (
        ROOT / '.github/workflows/static-validation.yml'
    ).read_text()
    assert 'python3 -m pytest -q tests' in workflow
    assert 'action-ros-ci@v0.4' in workflow
    assert 'target-ros2-distro: jazzy' in workflow


def test_docker_image_has_jazzy_control_stack_without_duplicate_apt_packages():
    dockerfile = (ROOT / 'Dockerfile').read_text()
    assert dockerfile.count('ros-jazzy-gz-ros2-control') == 1
    assert sum(
        line.strip().rstrip('\\').strip() == 'ros-jazzy-ros2-control'
        for line in dockerfile.splitlines()
    ) == 1
    assert dockerfile.count('ros-jazzy-ros2-controllers') == 1
    assert 'FROM ros:jazzy-ros-base' in dockerfile


def test_gazebo_spawn_uses_explicit_world_and_robot_description_parameter():
    launch = (
        ROOT / 'src/dif_bot_gazebo/launch/gazebo.launch.py'
    ).read_text()
    world = ET.parse(
        ROOT / 'src/dif_bot_gazebo/worlds/my_world.sdf'
    ).getroot().find('world')
    assert world is not None
    assert world.attrib['name'] == 'dif_bot_world'
    assert "'world_name'," in launch
    assert "default_value='dif_bot_world'" in launch
    assert "'-world', world_name" in launch
    assert "'-param', 'robot_description'" in launch
    assert "parameters=[{'robot_description': robot_description}]" in launch
    assert 'TimerAction' not in launch
    assert 'gz_sim.launch.py' in launch
    assert 'on_exit_shutdown' in launch
    assert 'target_action=spawn_robot' in launch
    assert launch.count('condition=IfCondition(use_ros2_control)') == 2
    assert "name='spawn_dif_bot'" not in launch


def test_start_script_fails_loudly_when_robot_did_not_spawn():
    start = (ROOT / 'START_DIF_BOT.sh').read_text()
    assert 'wait_for_robot_spawn 90' in start
    assert 'Entity creation successful.' in start
    assert 'wait_for_ros2_controllers 150' in start
    assert 'Configured and activated joint_state_broadcaster' in start
    assert 'Configured and activated diff_drive_controller' in start
    assert 'output="$(timeout 4 ros2 control list_controllers' not in start


def test_nav2_progress_checker_tracks_rotation_at_xy_goal():
    nav = yaml.safe_load(
        (ROOT / 'src/dif_bot_navigation/config/nav2_params.yaml').read_text()
    )
    controller = nav['controller_server']['ros__parameters']
    progress = controller['progress_checker']
    goal = controller['goal_checker']
    assert progress['plugin'] == 'nav2_controller::PoseProgressChecker'
    assert progress['required_movement_radius'] == 0.08
    assert progress['required_movement_angle'] == 0.05
    assert progress['movement_time_allowance'] >= 20.0
    assert goal['stateful'] is True
    assert goal['xy_goal_tolerance'] == 0.05
    assert goal['yaw_goal_tolerance'] == 0.10


def test_xy_only_web_goal_preserves_current_yaw_and_allows_explicit_yaw():
    app = (ROOT / 'web/src/App.jsx').read_text()
    assert "yawDeg: ''" in app
    assert 'currentPose.yawRad' in app
    assert "currentPose.frameId !== 'map'" in app
    assert 'Math.sin(halfYaw)' in app
    assert 'Math.cos(halfYaw)' in app
    assert 'Yaw final (grados; vacío = conservar orientación)' in app
    assert 'orientation: { w: 1.0 }' not in app


def test_web_pose_and_goal_bridge_preserve_simulation_time_stamps():
    launch = (ROOT / 'src/dif_bot_bringup/launch/main.launch.py').read_text()
    pose_node = launch.split("robot_pose = Node", 1)[1].split(
        "goal_bridge = Node", 1
    )[0]
    goal_node = launch.split("goal_bridge = Node", 1)[1].split(
        "\n\n    nav", 1
    )[0]
    assert "parameters=[{'use_sim_time': use_sim_time}]" in pose_node
    assert "parameters=[{'use_sim_time': use_sim_time}]" in goal_node

    pose_source = (
        ROOT / 'src/dif_bot_web_bridge/dif_bot_web_bridge/robot_pose.py'
    ).read_text()
    bridge = (
        ROOT / 'src/dif_bot_web_bridge/dif_bot_web_bridge/goal_bridge.py'
    ).read_text()
    assert 'pose_msg.header.stamp = t.header.stamp' in pose_source
    assert 'goal_msg.pose.header.stamp = self.get_clock().now().to_msg()' in bridge
    assert 'Time.from_msg(' in bridge
    assert 'pose_age_ros <= 2.0' in bridge

def test_goal_bridge_validates_map_frame_and_normalizes_quaternion():
    bridge = (
        ROOT / 'src/dif_bot_web_bridge/dif_bot_web_bridge/goal_bridge.py'
    ).read_text()
    assert "if frame_id != 'map'" in bridge
    assert 'all(math.isfinite(value) for value in coordinates)' in bridge
    assert 'norm = math.sqrt(' in bridge
    assert 'q.z /= norm' in bridge
    assert 'orientación final no se alcanzó' in bridge


def test_navigation_diagnostic_reports_progress_checker_and_nav2_errors():
    diag = (ROOT / 'DIAGNOSTIC_DIF_BOT.sh').read_text()
    assert 'progress_checker.required_movement_angle' in diag
    assert 'goal_checker.yaw_goal_tolerance' in diag
    assert 'navigation.log' in diag
    assert 'oscillat' in diag.lower()
    assert "[NAV2 PARAM] %s = %s" in diag and 'printf' in diag


def test_runtime_diagnostic_checks_command_chain_localization_and_logs():
    diagnostic = (ROOT / 'DIAGNOSTIC_DIF_BOT.sh').read_text()
    for token in (
        '/cmd_vel_web', '/cmd_vel', '/diff_drive_controller/cmd_vel',
        '/cmd_vel_nav', 'ros2 topic info -v', 'ros2 control list_controllers',
        '/amcl_pose', '/odom_filtered', 'ros2 lifecycle get',
        'navigation.log', 'base.log', 'web.log'
    ):
        assert token in diagnostic


def test_deployer_does_not_run_heavy_runtime_diagnostics_automatically():
    deploy = (ROOT / 'deploy_wsl.sh').read_text()
    assert 'ros2 action list' not in deploy
    assert 'DIAGNOSTIC_DIF_BOT.sh' not in deploy
    assert 'rosdep update' not in deploy
    assert 'LOCK_MARKER' in deploy
    assert 'SERVICIOS INICIADOS' in deploy



def test_slam_launch_includes_ekf_for_required_odom_tf():
    launch = (ROOT / 'src/dif_bot_navigation/launch/slam.launch.py').read_text()
    assert "package='robot_localization'" in launch
    assert "name='ekf_filter_node'" in launch
    assert "default_value='true'" in launch
    assert "package='slam_toolbox'" in launch
    assert "remappings=[('odometry/filtered', '/odom_filtered')]" in launch


def test_nav2_map_server_uses_package_share_map_and_optional_rviz():
    launch = (ROOT / 'src/dif_bot_navigation/launch/navigation.launch.py').read_text()
    params = yaml.safe_load(
        (ROOT / 'src/dif_bot_navigation/config/nav2_params.yaml').read_text()
    )
    assert "default_value=os.path.join(share, 'maps', 'my_map.yaml')" in launch
    assert "'yaml_filename': map_file" in launch
    assert "default_value='false'" in launch
    assert "package='rviz2'" in launch
    assert "name='nav2_rviz'" in launch
    assert 'yaml_filename' not in params['map_server']['ros__parameters']


def test_rviz_profile_supports_amcl_and_manual_nav2_goals():
    rviz = yaml.safe_load(
        (ROOT / 'src/dif_bot_navigation/config/navigation.rviz').read_text()
    )
    manager = rviz['Visualization Manager']
    classes = {entry.get('Class') for entry in manager['Displays']}
    tools = {entry['Class'] for entry in manager['Tools']}
    panels = {entry['Class'] for entry in rviz['Panels']}
    assert manager['Global Options']['Fixed Frame'] == 'map'
    assert 'rviz_default_plugins/Map' in classes
    assert 'rviz_default_plugins/LaserScan' in classes
    assert 'nav2_rviz_plugins/ParticleCloud' in classes
    assert 'nav2_rviz_plugins/GoalTool' in tools
    assert 'rviz_default_plugins/SetInitialPose' in tools
    assert 'nav2_rviz_plugins/Navigation 2' in panels


def test_map_saver_script_writes_yaml_and_pgm_inside_package_maps():
    script = (ROOT / 'scripts/save_map.sh').read_text()
    assert 'src/dif_bot_navigation/maps' in script
    assert 'map_saver_cli' in script
    assert 'PREFIX.yaml' in script
    assert 'PREFIX.pgm' in script
    assert 'MAP_NAME' in script


def test_simulation_defaults_reduce_wsl_load_without_removing_sensors():
    world = ET.parse(
        (ROOT / 'src/dif_bot_gazebo/worlds/my_world.sdf')
    ).getroot()
    physics = world.find('.//physics')
    assert float(physics.findtext('max_step_size')) == 0.002
    sensors = (ROOT / 'src/dif_bot_description/urdf/sensors.xacro').read_text()
    assert '<update_rate>100</update_rate>' in sensors
    assert '<update_rate>10</update_rate>' in sensors
    assert '<update_rate>5</update_rate>' in sensors
    assert '<width>320</width><height>240</height>' in sensors
    assert '<visualize>false</visualize>' in sensors


def test_wsl_deployer_avoids_local_expansion_inside_remote_shell():
    deploy = (ROOT / 'deploy_wsl.sh').read_text()
    marker = 'info "Instalando dependencias ROS, compilando workspace y construyendo frontend..."'
    remote = deploy[deploy.index(marker):].split("bash -lc '", 1)[1].split("\n'", 1)[0]
    assert "'" not in remote
    assert "awk '{print $1}'" not in deploy
    assert 'DIFBOT_SKIP_IMAGE_BUILD' in deploy
    assert 'LOCK_HASH="${LOCK_HASH%% *}"' in deploy

def test_gazebo_controller_spawners_allow_slow_simulation_startup():
    launch = (
        ROOT / 'src/dif_bot_gazebo/launch/gazebo.launch.py'
    ).read_text()
    assert launch.count("'--switch-timeout'") == 2
    assert launch.count("'30'") >= 2
    assert launch.count("'--service-call-timeout'") == 2
    assert launch.count("'35'") >= 2


def test_startup_waits_for_actual_controller_spawner_success_without_ros_cli_polling():
    start = (ROOT / 'START_DIF_BOT.sh').read_text()
    wait_block = start.split('wait_for_ros2_controllers(){', 1)[1].split(
        'wait_for_ros2_controllers 150', 1
    )[0]
    assert 'Configured and activated joint_state_broadcaster' in wait_block
    assert 'Configured and activated diff_drive_controller' in wait_block
    assert 'output="$(timeout 4 ros2 control list_controllers' not in wait_block
    assert 'local limit="${1:-150}"' in wait_block
