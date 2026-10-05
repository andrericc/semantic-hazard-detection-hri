"""Semantic map: where each known object stands in house.world.

The robot is assumed to know the home layout in advance (standard HRI
assumption): each entry maps a canonical object name (post OBJECT_ALIASES,
same spelling as the YOLO/COCO class) to the room it belongs to and to an
approach pose for the base, chosen so that the object falls inside the head
camera's field of view once the goal is reached.

Poses are in GAZEBO WORLD coordinates (like nav_client.WORLD_WAYPOINTS);
nav_client.navigate_to_pose applies the world->map transform.

Kept separate from nav_client so tools like detect_test.py can import the
table without pulling in the Nav2 action-client machinery.
"""

# object -> (room, approach_x, approach_y, approach_yaw)  [world frame]
OBJECT_LOCATIONS = {
    # living room (south zone)
    "bottle":       ("living_room",  7.4, -0.9,  0.00),  # coke can on demo_table
    "laptop":       ("living_room",  7.3, -1.1,  0.00),  # on demo_table
    "tv":           ("living_room", 10.2,  1.3,  0.00),  # on demo_tv_table
    "couch":        ("living_room", 11.5, -1.6, -1.57),  # demo_sofa
    "chair":        ("living_room", 10.1, -2.5,  1.57),  # demo_chair
    "book":         ("living_room",  5.5, -2.2, -1.57),  # bookshelf_south
    # bedroom (north-west room)
    "bed":          ("bedroom",      6.5,  4.6,  1.57),
    "teddy bear":   ("bedroom",      6.5,  4.9,  1.57),  # on the bed
    # kitchen (north-east room)
    "oven":         ("kitchen",     11.9,  4.0,  0.10),
    "refrigerator": ("kitchen",     13.9,  3.0,  0.00),
    "dining table": ("kitchen",     11.5,  4.7,  0.50),  # kitchen_table_ne
    "cup":          ("kitchen",     11.4,  5.2,  0.00),  # mug on kitchen_table
    # bathroom (south-east nook)
    "toilet":       ("bathroom",    13.9, -2.5,  0.00),
    "sink":         ("bathroom",    14.0, -0.9,  0.00),  # on bathroom_counter
}


def locate(obj):
    """Return (room, x, y, yaw) for a known object, or None."""
    return OBJECT_LOCATIONS.get((obj or "").strip().lower())
