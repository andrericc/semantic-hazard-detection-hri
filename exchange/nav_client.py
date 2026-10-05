"""Nav2 client: drive TIAGo to a room after an approved action.

Requires the navigation stack (ros2 launch simulation nav.launch.py). The voice
node's mission (run_mission) calls navigate_to_pose() with poses from
semantic_map.OBJECT_LOCATIONS / WORLD_WAYPOINTS after an 'allow' verdict or a
confirmed warning; when the /navigate_to_pose action server is not up, it
returns 'unavailable' and the demo continues without moving the robot.

Waypoints are written in GAZEBO WORLD coordinates (read them off the Gazebo GUI
or simulation/worlds/house.world) and converted to the map frame below.

The world->map transform derives from nav.launch.py: the robot spawns at world
(0, 0, yaw 0) and its published initial pose in the map is (9.151, -6.340,
yaw 2.204). If the map or the spawn pose ever changes, recalibrate: with nav
running and the robot standing at a known world pose (X, Y), run
    ros2 run tf2_ros tf2_echo map base_footprint
and adjust MAP_TX / MAP_TY / MAP_TYAW until world_to_map(X, Y, 0) matches tf.
"""
import math
import time

MAP_TX, MAP_TY, MAP_TYAW = 9.151, -6.340, 2.204

# room -> (x, y, yaw) in the Gazebo world frame, standing ~1.5 m from the furniture.
# The four semantic rooms of house.world (see the room map comment in the world file).
WORLD_WAYPOINTS = {
    'living_room': (7.5,  -1.0,  0.0),    # facing demo_table (9.0, -1.0)
    'bedroom':     (6.5,   4.5,  1.57),   # NW room, facing the bed (6.5, 6.7)
    'kitchen':     (11.5,  4.5,  0.59),   # NE room, facing kitchen_table_ne (13, 5.5)
    'bathroom':    (13.8, -2.3,  0.0),    # SE nook, facing toilet/sink on the east wall
}

NAV_TIMEOUT = 240.0  # s; the base is slow and may have to cross the whole house


def world_to_map(x, y, yaw):
    c, s = math.cos(MAP_TYAW), math.sin(MAP_TYAW)
    return (MAP_TX + c * x - s * y,
            MAP_TY + s * x + c * y,
            yaw + MAP_TYAW)


def _wait(future, timeout):
    """Wait on an rclpy future; the caller's node is spun by a background thread."""
    deadline = time.monotonic() + timeout
    while not future.done():
        if time.monotonic() > deadline:
            return False
        time.sleep(0.1)
    return True


def go_to_room(node, room):
    """Send a NavigateToPose goal for `room`.
    Returns 'no_waypoint' | 'unavailable' | 'succeeded' | 'failed'."""
    if room not in WORLD_WAYPOINTS:
        return 'no_waypoint'
    return navigate_to_pose(node, *WORLD_WAYPOINTS[room])


def navigate_to_pose(node, wx, wy, wyaw, timeout=NAV_TIMEOUT):
    """Send a NavigateToPose goal for a pose in GAZEBO WORLD coordinates.
    Returns 'unavailable' | 'succeeded' | 'failed'."""
    from rclpy.action import ActionClient
    from nav2_msgs.action import NavigateToPose

    client = getattr(node, '_nav_client', None)
    if client is None:
        client = ActionClient(node, NavigateToPose, '/navigate_to_pose')
        node._nav_client = client
    if not client.wait_for_server(timeout_sec=2.0):
        return 'unavailable'

    x, y, yaw = world_to_map(wx, wy, wyaw)
    goal = NavigateToPose.Goal()
    goal.pose.header.frame_id = 'map'
    goal.pose.pose.position.x = x
    goal.pose.pose.position.y = y
    goal.pose.pose.orientation.z = math.sin(yaw / 2.0)
    goal.pose.pose.orientation.w = math.cos(yaw / 2.0)

    send_future = client.send_goal_async(goal)
    if not _wait(send_future, 10.0):
        return 'failed'
    goal_handle = send_future.result()
    if goal_handle is None or not goal_handle.accepted:
        return 'failed'

    result_future = goal_handle.get_result_async()
    if not _wait(result_future, timeout):
        goal_handle.cancel_goal_async()
        return 'failed'

    from action_msgs.msg import GoalStatus
    status = result_future.result().status
    return 'succeeded' if status == GoalStatus.STATUS_SUCCEEDED else 'failed'
