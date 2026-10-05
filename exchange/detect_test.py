#!/usr/bin/env python3
"""Empirical YOLO detectability test for the objects in house.world.

For every target object the robot is TELEPORTED (via /gazebo/set_entity_state,
same pattern as sim.launch.py) to poses at increasing distances along the
approach direction, a batch of camera frames is grabbed and run through the
same YOLOv8n + INDOOR_CLASSES filter the voice node uses. The per-class hit
table tells which models are reliably detectable and at which distance, and
feeds back into semantic_map.OBJECT_LOCATIONS and house.world.

Run INSIDE the tiago_sim container with ONLY the plain simulation up
(sim.launch.py, NOT nav.launch.py: teleports would corrupt AMCL):
    cd /root/exchange/exchange && python3 detect_test.py [target ...]

Acceptance rule (from the project plan):
    >= 4/8 frames  -> model + pose OK
    1-3/8 frames   -> try a different distance or a head tilt
    0/8 everywhere -> replace the model or demote the object to
                      conversational-only (no visual verification)

Annotated frames are saved under ./detect_test_out/ for visual debugging.
"""
import math
import os
import sys
import threading
import time

import rclpy
from rclpy.node import Node
from rclpy.qos import qos_profile_sensor_data
from sensor_msgs.msg import Image
from gazebo_msgs.srv import SetEntityState

from voice_node import (image_msg_to_bgr, load_yolo, INDOOR_CLASSES, CAMERA_TOPIC,
                        CONF_REPORT, YOLO_IMGSZ)

# target COCO class -> (object world x, object world y, approach_dir)
# approach_dir = yaw the robot faces (pointing AT the object); the robot is
# placed at object - distance * (cos, sin)(approach_dir). Directions keep the
# robot clear of walls and other furniture (see house.world room map).
TARGETS = {
    "bottle":       (8.90, -0.80, 0.00),   # coke can on demo_table (z 0.82)
    "laptop":       (8.65, -1.10, 0.00),   # GSO laptop on demo_table
    "tv":           (11.50, 1.30, 0.00),   # on demo_tv_table
    "couch":        (11.50, -3.00, -1.57), # demo_sofa, approach from north
    "chair":        (10.10, -1.00, 1.57),  # demo_chair, approach from south
    "book":         (5.50, -3.50, -1.57),  # bookshelf, approach from north
    "bed":          (6.50, 6.70, 1.57),    # AWS bed, approach from south
    "teddy bear":   (6.50, 6.00, 1.57),    # GSO teddy on the bed
    "oven":         (13.50, 4.20, 0.10),   # custom PBR oven
    "refrigerator": (15.40, 3.00, 0.00),   # AWS fridge, approach from west
    "dining table": (13.00, 5.50, 0.30),   # kitchen_table_ne
    "cup":          (12.85, 5.20, 0.00),   # GSO mug on kitchen_table (z 0.66)
    "toilet":       (15.50, -2.50, 0.00),  # Fuel toilet, approach from west
    "sink":         (15.55, -0.90, 0.00),  # Fuel sink on bathroom_counter
}

DISTANCES = (1.5, 2.0, 3.0)   # m from the object
FRAMES = 8
FRAME_GAP = 0.4               # s between grabbed frames
SETTLE = 3.0                  # s after a teleport (software rendering is slow)
OUT_DIR = "detect_test_out"


class DetectTestNode(Node):
    def __init__(self):
        super().__init__('detect_test')
        self._teleport = self.create_client(SetEntityState, '/gazebo/set_entity_state')

    def teleport(self, x, y, yaw):
        if not self._teleport.wait_for_service(timeout_sec=5.0):
            raise RuntimeError("/gazebo/set_entity_state not available - "
                               "is sim.launch.py running?")
        req = SetEntityState.Request()
        req.state.name = 'tiago'
        req.state.pose.position.x = float(x)
        req.state.pose.position.y = float(y)
        req.state.pose.position.z = 0.05
        req.state.pose.orientation.z = math.sin(yaw / 2.0)
        req.state.pose.orientation.w = math.cos(yaw / 2.0)
        future = self._teleport.call_async(req)
        deadline = time.monotonic() + 10.0
        while not future.done():
            if time.monotonic() > deadline:
                raise RuntimeError("teleport service call timed out")
            time.sleep(0.05)
        return future.result().success

    def grab_frame(self, timeout=20.0):
        event = threading.Event()
        holder = {}

        def cb(msg):
            holder['msg'] = msg
            event.set()

        sub = self.create_subscription(Image, CAMERA_TOPIC, cb, qos_profile_sensor_data)
        got = event.wait(timeout)
        self.destroy_subscription(sub)
        return holder.get('msg') if got else None


def test_pose(node, model, target, dist, ox, oy, direction):
    rx = ox - dist * math.cos(direction)
    ry = oy - dist * math.sin(direction)
    if not node.teleport(rx, ry, direction):
        print(f"    teleport to ({rx:.2f},{ry:.2f}) FAILED")
        return 0, {}
    time.sleep(SETTLE)

    hits = 0
    best_conf = 0.0
    others = {}
    annotated = None
    for i in range(FRAMES):
        msg = node.grab_frame()
        if msg is None:
            print("    no camera frame (is the simulation rendering?)")
            break
        img = image_msg_to_bgr(msg)
        results = model.predict(img, conf=CONF_REPORT, imgsz=YOLO_IMGSZ, verbose=False)
        found = False
        for r in results:
            for c, conf in zip(r.boxes.cls.tolist(), r.boxes.conf.tolist()):
                name = model.names[int(c)]
                if name not in INDOOR_CLASSES:
                    continue
                if name == target:
                    found = True
                    best_conf = max(best_conf, conf)
                else:
                    others[name] = max(others.get(name, 0.0), conf)
        if found:
            hits += 1
            if annotated is None:
                annotated = results[0].plot()
        time.sleep(FRAME_GAP)

    if annotated is not None:
        import cv2
        safe = target.replace(' ', '_')
        cv2.imwrite(os.path.join(OUT_DIR, f"{safe}_{dist:.1f}m.png"), annotated)
    return hits, {"best_conf": best_conf, "others": others}


def main():
    wanted = [a.lower() for a in sys.argv[1:]] or list(TARGETS)
    unknown = [w for w in wanted if w not in TARGETS]
    if unknown:
        print(f"unknown target(s): {unknown}; known: {sorted(TARGETS)}")
        return

    os.makedirs(OUT_DIR, exist_ok=True)
    rclpy.init()
    node = DetectTestNode()
    spin = threading.Thread(target=rclpy.spin, args=(node,), daemon=True)
    spin.start()
    model = load_yolo()

    verdicts = {}
    for target in wanted:
        ox, oy, direction = TARGETS[target]
        print(f"\n=== {target} at ({ox},{oy}) ===")
        best = (0, None)
        for dist in DISTANCES:
            hits, info = test_pose(node, model, target, dist, ox, oy, direction)
            extra = ""
            if info.get("others"):
                top = sorted(info["others"].items(), key=lambda kv: -kv[1])[:4]
                extra = "   also: " + ", ".join(f"{n} {c:.2f}" for n, c in top)
            print(f"  {dist:.1f} m: {hits}/{FRAMES} frames"
                  f" (best conf {info.get('best_conf', 0):.2f}){extra}")
            if hits > best[0]:
                best = (hits, dist)
        if best[0] >= 4:
            verdicts[target] = f"OK at {best[1]:.1f} m ({best[0]}/{FRAMES})"
        elif best[0] > 0:
            verdicts[target] = f"WEAK, best {best[0]}/{FRAMES} at {best[1]:.1f} m"
        else:
            verdicts[target] = "NOT DETECTED - replace model or demote object"

    print("\n" + "=" * 50)
    print("Summary (acceptance: >=4/8 frames):")
    for target, verdict in verdicts.items():
        print(f"  {target:14s} {verdict}")
    print(f"Annotated frames in ./{OUT_DIR}/")

    node.destroy_node()
    rclpy.shutdown()


if __name__ == "__main__":
    main()
