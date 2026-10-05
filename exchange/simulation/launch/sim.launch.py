import os
from ament_index_python.packages import get_package_share_directory
from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument, ExecuteProcess, IncludeLaunchDescription, TimerAction
from launch.launch_description_sources import PythonLaunchDescriptionSource
from launch.substitutions import LaunchConfiguration

# TIAGo always spawns at (0,0), which is outside the house: once the sim is up
# we teleport it into the living room, facing the furniture.
ROBOT_HOME_POSE = "{state: {name: tiago, pose: {position: {x: 6.5, y: -1.0, z: 0.05}}}}"


def generate_launch_description():
    world_name_arg = DeclareLaunchArgument(
        "world_name",
        default_value="house",
        description="Gazebo world name (file in simulation/worlds, without .world)",
    )
    pkg_my_sim = get_package_share_directory("simulation")
    pkg_tiago_gazebo = get_package_share_directory("tiago_gazebo")

    my_models_path = os.path.join(pkg_my_sim, "models")

    # Inject our models path now so pal_gazebo.launch.py picks it up via environ
    existing = os.environ.get("GAZEBO_MODEL_PATH", "")
    os.environ["GAZEBO_MODEL_PATH"] = (
        (existing + ":" + my_models_path) if existing else my_models_path
    )

    tiago_launch = IncludeLaunchDescription(
        PythonLaunchDescriptionSource(
            os.path.join(pkg_tiago_gazebo, "launch", "tiago_gazebo.launch.py")
        ),
        launch_arguments={
            "navigation": "False",
            "is_public_sim": "True",
            "world_name": LaunchConfiguration("world_name"),
            "moveit": "True",
            "rviz": "False",
            "tuck_arm": "True",
        }.items(),
    )

    move_robot_inside = TimerAction(
        period=30.0,
        actions=[
            ExecuteProcess(
                cmd=["ros2", "service", "call", "/gazebo/set_entity_state",
                     "gazebo_msgs/srv/SetEntityState", ROBOT_HOME_POSE],
                output="screen",
            )
        ],
    )

    return LaunchDescription(
        [
            world_name_arg,
            tiago_launch,
            move_robot_inside,
        ]
    )
