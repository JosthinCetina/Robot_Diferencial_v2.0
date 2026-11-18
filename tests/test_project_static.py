from pathlib import Path
import ast
import xml.etree.ElementTree as ET
import yaml

ROOT = Path(__file__).resolve().parents[1]

def test_python_sources_parse():
    for path in ROOT.glob('src/**/*.py'):
        ast.parse(path.read_text(encoding='utf-8'), filename=str(path))

def test_package_manifests_are_valid_and_unique():
    names = []
    for path in ROOT.glob('src/*/package.xml'):
        root = ET.parse(path).getroot()
        names.append(root.findtext('name'))
        assert root.findtext('version') == '2.0.0'
    assert len(names) == 6
    assert len(names) == len(set(names))

def test_all_yaml_configs_parse():
    for path in ROOT.glob('src/**/*.yaml'):
        with path.open(encoding='utf-8') as stream:
            yaml.safe_load(stream)

def test_both_drive_modes_are_present():
    xacro = (ROOT / 'src/dif_bot_description/urdf/dif_bot_description.urdf.xacro').read_text()
    assert 'gz_ros2_control/GazeboSimSystem' in xacro
    assert 'gz-sim-diff-drive-system' in xacro
    assert 'use_ros2_control' in xacro
    assert 'libgazebo_ros_diff_drive.so' not in xacro

def test_ekf_input_is_normalized_for_both_modes():
    ekf = yaml.safe_load((ROOT / 'src/dif_bot_navigation/config/ekf.yaml').read_text())
    params = ekf['ekf_filter_node']['ros__parameters']
    assert params['odom0'] == '/odom_raw'
    assert params['imu0'] == '/imu/data'
    assert params['publish_tf'] is True
    assert len(params['process_noise_covariance']) == 225
    relay = (ROOT / 'src/dif_bot_control/dif_bot_control/odometry_relay.py').read_text()
    assert '/diff_drive_controller/odom' in relay and '/odom_raw' in relay

def test_nav2_jazzy_behavior_topics_and_stamped_mode():
    nav = yaml.safe_load((ROOT / 'src/dif_bot_navigation/config/nav2_params.yaml').read_text())
    behavior = nav['behavior_server']['ros__parameters']
    assert 'local_costmap_topic' in behavior
    assert 'global_costmap_topic' in behavior
    assert 'local_footprint_topic' in behavior
    assert 'global_footprint_topic' in behavior
    assert behavior['enable_stamped_cmd_vel'] is False
    assert nav['controller_server']['ros__parameters']['odom_topic'] == '/odom_filtered'

def test_gazebo_sim_sensors_are_bridged():
    sensors = (ROOT / 'src/dif_bot_description/urdf/sensors.xacro').read_text()
    assert 'type="gpu_lidar"' in sensors
    assert '<gz_frame_id>laser_frame</gz_frame_id>' in sensors
    assert '<gz_frame_id>imu_link</gz_frame_id>' in sensors
    launch = (ROOT / 'src/dif_bot_gazebo/launch/gazebo.launch.py').read_text()
    assert 'ros_gz_bridge' in launch and 'gz.msgs.LaserScan' in launch
    assert '/clock@rosgraph_msgs/msg/Clock[gz.msgs.Clock' in launch
    assert "'/cmd_vel@geometry_msgs/msg/Twist]gz.msgs.Twist'" in launch
    assert "'/odom_raw@nav_msgs/msg/Odometry[gz.msgs.Odometry'" in launch
    xacro = (ROOT / 'src/dif_bot_description/urdf/dif_bot_description.urdf.xacro').read_text()
    assert '<topic>/cmd_vel</topic>' in xacro
    assert '<odom_topic>/odom_raw</odom_topic>' in xacro

def test_mission_ui_and_service_are_connected():
    app = (ROOT / 'web/src/App.jsx').read_text()
    server = (ROOT / 'src/dif_bot_navigation/scripts/mission_server.py').read_text()
    assert '/start_autonomous_mission' in app and 'std_srvs/Trigger' in app
    assert '/dif_bot/mission/progress' in app and '/dif_bot/mission/progress' in server


def test_urdf_xacro_and_sdf_are_well_formed_xml():
    for relative in [
        'src/dif_bot_description/urdf/dif_bot_description.urdf.xacro',
        'src/dif_bot_description/urdf/sensors.xacro',
        'src/dif_bot_gazebo/worlds/my_world.sdf',
    ]:
        ET.parse(ROOT / relative)

def test_control_adapters_use_consistent_jazzy_topics():
    stamper = (ROOT / 'src/dif_bot_control/dif_bot_control/cmd_vel_stamper.py').read_text()
    relay = (ROOT / 'src/dif_bot_control/dif_bot_control/odometry_relay.py').read_text()
    pose = (ROOT / 'src/dif_bot_control/dif_bot_control/pose_controller.py').read_text()
    hardware = (ROOT / 'src/dif_bot_control/dif_bot_control/hardware_validation.py').read_text()
    assert '/cmd_vel' in stamper and '/diff_drive_controller/cmd_vel' in stamper
    assert '/diff_drive_controller/odom' in relay and '/odom_raw' in relay
    assert "'/odom_filtered'" in pose
    assert "'/odom_filtered'" in hardware or "'/odom_filtered'" in hardware.replace('"', "'")

def test_web_stop_is_documented_as_logical_not_safety_estop():
    app = (ROOT / 'web/src/App.jsx').read_text()
    readme = (ROOT / 'README.md').read_text()
    plan = (ROOT / 'docs/TEST_PLAN_JAZZY.md').read_text()
    assert 'No sustituye un E-stop físico' in app
    assert "name: '/dif_bot/stop'" in app or "name: '/dif_bot/stop'" in app.replace('\n', '')
    assert 'No es un dispositivo E-stop físico' in readme
    assert 'no es E-stop físico' in plan
    bridge = (ROOT / 'src/dif_bot_web_bridge/dif_bot_web_bridge/goal_bridge.py').read_text()
    assert '/dif_bot/stop' in bridge and 'CancelGoal.Request()' in bridge
    assert '/navigate_to_pose/_action/cancel_goal' in bridge
    stop_fn = app.split('const forceStopRobot = () => {', 1)[1].split('};', 1)[0]
    assert 'connected' not in stop_fn  # avoids stale connected=false captured by the mount effect

def test_github_publish_and_docker_clone_workflows_exist():
    publish = ROOT / 'scripts/publish_github.sh'
    clone = ROOT / 'docker-clone-run.sh'
    assert publish.exists() and clone.exists()
    assert 'gh repo create' in publish.read_text()
    assert 'git clone --branch' in clone.read_text()
    assert 'ROS_DOMAIN_ID' in clone.read_text()
    assert 'ROS_DOMAIN_ID' in (ROOT / 'docker-run.sh').read_text()


def test_docker_image_has_jazzy_control_stack_without_duplicate_apt_packages():
    dockerfile = (ROOT / 'Dockerfile').read_text()
    assert dockerfile.count('ros-jazzy-gz-ros2-control') == 1
    assert sum(line.strip().rstrip('\\').strip() == 'ros-jazzy-ros2-control' for line in dockerfile.splitlines()) == 1
    assert dockerfile.count('ros-jazzy-ros2-controllers') == 1
    assert 'FROM ros:jazzy-ros-base' in dockerfile
