#!/usr/bin/env python3

import os
import re
import subprocess
import threading
import time

import rclpy
from rclpy.node import Node
from std_msgs.msg import String

from explain import CONFIRM_QUESTION, CHILD_SENTENCE, INTERACTION_PHRASE
import materials_db
import semantic_map


VOCAB_OBJECTS = sorted([
    # --- original vocabulary (COCO classes present in the training data) ---
    "apple", "bed", "bench", "book", "bottle", "bowl", "chair", "clock",
    "couch", "cup", "dining table", "handbag", "kite", "laptop", "microwave",
    "oven", "potted plant", "refrigerator", "sink", "sports ball", "suitcase",
    "teddy bear", "toilet", "tv", "umbrella", "vase",
    # --- added COCO classes (kept in sync with INDOOR_CLASSES below) ---
    # small manipulable objects, good as "object to move"
    "knife", "scissors", "fork", "spoon", "remote", "keyboard", "mouse",
    "cell phone", "wine glass", "banana", "orange", "sandwich", "hair drier",
    "toothbrush",
    # a few convenient spoken aliases (normalised to a COCO/vocab name)
    "table", "television", "phone", "hair dryer", "fridge",
], key=len, reverse=True)  # longest first: "dining table" before "table"


OBJECT_ALIASES = {
    "television": "tv",
    "phone":      "cell phone",
    "hair dryer": "hair drier",   # COCO spelling is "hair drier"
    "fridge":     "refrigerator",
    "table":      "dining table",
}

ROOM_ALIASES = {  # spoken form -> canonical context name (longest first)
    # the house has 4 navigable rooms (see nav_client.WORLD_WAYPOINTS); the
    # tv/dining areas are part of the open-plan living room / kitchen zones
    "television room": "living_room",
    "utility room":    "utility_room",
    "child's room":    "childs_room",
    "childs room":     "childs_room",
    "kids room":       "childs_room",
    "living room":     "living_room",
    "dining room":     "kitchen",
    "home office":     "home_office",
    "tv room":         "living_room",
    "staircase":       "staircase",
    "bathroom":        "bathroom",
    "corridor":        "corridor",
    "playroom":        "playroom",
    "bedroom":         "bedroom",
    "hallway":         "corridor",
    "kitchen":         "kitchen",
    "office":          "home_office",
    "closet":          "closet",
    "stairs":          "staircase",
    "lobby":           "lobby",
}

MATERIALS = ["ceramic", "fabric", "foliage", "food", "glass", "leather",
             "metal", "mirror", "paper", "plastic", "wood"]

# ordered: most specific keyword first
INTERACTION_KEYWORDS = [
    ("on top of", "placed_on_top"),
    ("on top",    "placed_on_top"),
    ("next to",   "placed_near"),
    ("close to",  "placed_near"),
    ("beside",    "placed_near"),
    ("near",      "placed_near"),
    ("inside",    "placed_inside"),
    ("into",      "placed_inside"),
    ("onto",      "placed_on_top"),
    ("in",        "placed_inside"),
    ("on",        "placed_on_top"),
]

VERBS = ("put", "place", "move", "leave", "set", "drop", "bring", "take")
ARTICLES = ("the", "a", "an", "my", "your", "his", "her", "this", "that", "some")

DEFAULT_ROOM = "living_room"
RECORD_SECONDS = 5
SAMPLE_RATE = 16000
ADULT_AGE = 18

# Vision scan
CAMERA_TOPIC = "/head_front_camera/rgb/image_raw"
SCAN_COMMANDS = ("scan", "look", "look around", "what do you see", "what can you see")

YOLO_WEIGHTS = os.environ.get("TIAGO_YOLO_MODEL", "yolov8n.pt")
CONF_REPORT = 0.15        # detections reported to the user
CONF_LOG = 0.05           # low-confidence candidates: logged + drawn, never reported
YOLO_IMGSZ = 1280
SCAN_DEBUG_DIR = "scan_debug"   # annotated frames (cwd is exchange/, run_voice.sh cds here)
SCAN_FRAMES = 3                 # frames per head pose
HEAD_TILTS = (0.0, -0.55)       # head_2_joint sweep: straight ahead, then table height
HEAD_TOPIC = "/head_controller/joint_trajectory"
HEAD_MOVE_TIME = 1.5            # s, head trajectory duration
MAX_FRAME_MISSES = 2            # consecutive grab failures before giving up a scan

NUMBER_WORDS = {
    "one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6,
    "seven": 7, "eight": 8, "nine": 9, "ten": 10, "eleven": 11, "twelve": 12,
    "thirteen": 13, "fourteen": 14, "fifteen": 15, "sixteen": 16,
    "seventeen": 17, "eighteen": 18, "nineteen": 19, "twenty": 20,
    "thirty": 30, "forty": 40, "fifty": 50, "sixty": 60, "seventy": 70,
    "eighty": 80, "ninety": 90,
}


_stt_model = None

def load_stt():
    global _stt_model
    if _stt_model is None:
        print("Loading speech recognition model (first time only)...")
        from faster_whisper import WhisperModel
        _stt_model = WhisperModel("base.en", device="cpu", compute_type="int8")
    return _stt_model

def record_audio(seconds=RECORD_SECONDS, fs=SAMPLE_RATE):
    try:
        import numpy as np
        import sounddevice as sd
        try:
            rec_fs = fs
            sd.check_input_settings(samplerate=rec_fs)
        except Exception:
            # device does not accept 16 kHz: record at its native rate, resample below
            rec_fs = int(sd.query_devices(kind="input")["default_samplerate"])
        print(f"🎤 Recording for {seconds} seconds — speak now...")
        audio = sd.rec(int(seconds * rec_fs), samplerate=rec_fs, channels=1, dtype="float32")
        sd.wait()
        print("   ...done.")
        audio = np.squeeze(audio)
        if rec_fs != fs:  # linear resample to the 16 kHz whisper expects
            n_out = int(len(audio) * fs / rec_fs)
            audio = np.interp(np.linspace(0, len(audio) - 1, n_out),
                              np.arange(len(audio)), audio).astype("float32")
        return audio
    except Exception as e:
        print(f"Microphone error: {e}")
        print("(Is the container started with the updated start_tiago script? You can still type the sentence.)")
        return None

def transcribe(audio, hint=None):
    """hint: optional vocabulary sentence passed as whisper's initial_prompt to bias
    recognition (crucial for one-word answers like material names)."""
    model = load_stt()
    segments, _ = model.transcribe(audio, language="en", beam_size=1, vad_filter=True,
                                   initial_prompt=hint)
    text = " ".join(seg.text for seg in segments).strip()
    if len(text) < 3:  # silence / whisper hallucination guard
        return None
    return text

def normalize(text):
    text = text.lower()
    text = re.sub(r"[^a-z' ]", " ", text)
    return re.sub(r"\s+", " ", text).strip()

def find_room(text):
    """Return (room, text_without_room, found). Takes the LAST room mention."""
    for alias, room in ROOM_ALIASES.items():
        pattern = r"(?:\b(?:in|at|inside|to)\s+)?(?:\b(?:the|my|a|an)\s+)?\b" + re.escape(alias) + r"\b"
        matches = list(re.finditer(pattern, text))
        if matches:
            m = matches[-1]
            return room, (text[:m.start()] + " " + text[m.end():]).strip(), True
    return DEFAULT_ROOM, text, False

def strip_articles(words):
    return [w for w in words if w not in ARTICLES]

def extract_material(words):
    """Return (material, remaining_words). Supports 'made of M' or a material adjective."""
    joined = " ".join(words)
    m = re.search(r"\bmade of (\w+)\b", joined)
    if m and m.group(1) in MATERIALS:
        joined = joined.replace(m.group(0), " ")
        return m.group(1), joined.split()
    for w in words:
        if w in MATERIALS:
            return w, [x for x in words if x != w]
    return "unknown", words

def extract_object(words):
    words = strip_articles(words)
    material, words = extract_material(words)
    joined = " ".join(words).strip()
    if not joined:
        return None, material
    for obj in VOCAB_OBJECTS:  # known objects, longest first
        if re.search(r"\b" + re.escape(obj) + r"\b", joined):
            return OBJECT_ALIASES.get(obj, obj), material
    return joined, material  # out-of-vocabulary: keep as-is (heuristic fallback handles it)

def find_interaction_split(tokens, start):
    """Find the first interaction keyword after `start` with at least one
    non-article token before it. Returns (interaction, kw_start, kw_end)."""
    for j in range(start + 1, len(tokens)):
        has_object_before = any(t not in ARTICLES for t in tokens[start + 1:j])
        if not has_object_before:
            continue
        for phrase, interaction in INTERACTION_KEYWORDS:
            kw = phrase.split()
            if tokens[j:j + len(kw)] == kw:
                return interaction, j, j + len(kw)
    return None, None, None

def parse_command(text):
    """Returns (params_dict, error_message). params is None on failure."""
    text = normalize(text)
    room, text, room_found = find_room(text)
    tokens = text.split()

    verb_idx = next((i for i, t in enumerate(tokens) if t in VERBS), None)
    if verb_idx is None:
        return None, f"I did not hear an action verb ({'/'.join(VERBS[:4])}...)."

    interaction, kw_start, kw_end = find_interaction_split(tokens, verb_idx)
    if interaction is None:
        return None, "I did not hear where to place the object (in / on / near ...)."

    obj_a, mat_a = extract_object(tokens[verb_idx + 1:kw_start])
    obj_b, mat_b = extract_object(tokens[kw_end:])
    if not obj_a:
        return None, "I did not catch which object to move."
    if not obj_b:
        return None, "I did not catch the destination object."

    return {
        "obj_a": obj_a, "mat_a": mat_a,
        "obj_b": obj_b, "mat_b": mat_b,
        "interaction": interaction,
        "room": room, "room_found": room_found,
    }, None


_yolo_model = None

def load_yolo():
    global _yolo_model
    if _yolo_model is None:
        print(f"Loading object recognition model ({YOLO_WEIGHTS}, first time only)...")
        from ultralytics import YOLO
        _yolo_model = YOLO(YOLO_WEIGHTS)  # kept next to this script (run_voice.sh cds here)
    return _yolo_model

def image_msg_to_bgr(msg):
    import numpy as np
    arr = np.frombuffer(bytes(msg.data), dtype=np.uint8).reshape(msg.height, msg.width, -1)
    if msg.encoding.lower() in ("rgb8", "rgba8"):
        arr = arr[..., 2::-1]  # to BGR
    return arr[..., :3].copy()

INDOOR_CLASSES = {
    "person", "chair", "couch", "potted plant", "bed", "dining table", "toilet",
    "tv", "laptop", "mouse", "remote", "keyboard", "cell phone", "microwave",
    "oven", "toaster", "sink", "refrigerator", "book", "clock", "vase",
    "scissors", "teddy bear", "hair drier", "toothbrush", "bottle", "wine glass",
    "cup", "fork", "knife", "spoon", "bowl", "banana", "apple", "sandwich",
    "orange", "umbrella", "handbag", "suitcase", "bench", "sports ball", "kite",
}


SCAN_LABEL_ALIASES = {
    "bottle":     {"bottle", "cup", "vase"},   # the coke can misreads as cup/vase
    "cup":        {"cup", "bottle"},
    "coke":       {"bottle", "cup", "vase"},
    "cocacola":   {"bottle", "cup", "vase"},
    "coca cola":  {"bottle", "cup", "vase"},
    "pringles":   {"bottle", "cup", "vase"},   # no COCO class: nearest shapes
    "television": {"tv"},
    "bathtub":    None,
}

def scan_labels_for(target):
    """Acceptable YOLO labels for a mission target, or None when the target
    has no plausible COCO class (visual check impossible)."""
    if target in SCAN_LABEL_ALIASES:
        return SCAN_LABEL_ALIASES[target]
    return {target} if target in INDOOR_CLASSES else None

def detect_frame(node, tag="scan", debug=True, timeout=20.0):
    """Grab one camera frame and return the INDOOR_CLASSES objects YOLO sees,
    or None when no frame is available (simulation not running).
    With debug=True each call logs the raw detections (including the
    filtered-out ones) and saves an annotated frame under SCAN_DEBUG_DIR;
    the continuous autoscan passes debug=False to avoid flooding."""
    msg = node.grab_camera_frame(timeout)
    if msg is None:
        return None
    img = image_msg_to_bgr(msg)
    model = load_yolo()
    results = model.predict(img, conf=CONF_LOG, imgsz=YOLO_IMGSZ, verbose=False)
    seen, raw = [], []
    for r in results:
        for c, conf in zip(r.boxes.cls.tolist(), r.boxes.conf.tolist()):
            name = model.names[int(c)]
            if name not in INDOOR_CLASSES:
                raw.append(f"{name} {conf:.2f}(filtered)")
            elif conf < CONF_REPORT:
                raw.append(f"{name} {conf:.2f}(<conf)")
            else:
                raw.append(f"{name} {conf:.2f}")
                if name not in seen:
                    seen.append(name)
    if not debug:
        return seen
    print("   [yolo] " + (", ".join(raw) if raw
                          else f"nothing at all (conf>={CONF_LOG})"))
    try:  # annotated frame: misses are exactly what we need to look at
        import cv2
        os.makedirs(SCAN_DEBUG_DIR, exist_ok=True)
        fname = f"{time.strftime('%H%M%S')}_{tag}.png"
        cv2.imwrite(os.path.join(SCAN_DEBUG_DIR, fname), results[0].plot())
    except Exception as e:
        print(f"   (could not save debug frame: {e})")
    return seen

def aim_head(node, pan=0.0, tilt=0.0, duration=HEAD_MOVE_TIME):

    from trajectory_msgs.msg import JointTrajectory, JointTrajectoryPoint
    if node._head_warned and node._head_pub.get_subscription_count() == 0:
        return False  # already known to be missing: skip the wait
    deadline = time.monotonic() + 2.0
    while node._head_pub.get_subscription_count() == 0:
        if time.monotonic() > deadline:
            if not node._head_warned:
                print("(head controller not available — scanning with the head as-is)")
                node._head_warned = True
            return False
        time.sleep(0.1)
    traj = JointTrajectory()
    traj.joint_names = ["head_1_joint", "head_2_joint"]
    point = JointTrajectoryPoint()
    point.positions = [float(pan), float(tilt)]
    point.time_from_start.sec = int(duration)
    point.time_from_start.nanosec = int((duration % 1.0) * 1e9)
    traj.points.append(point)
    node._head_pub.publish(traj)
    time.sleep(duration + 0.5)  # let the head settle before grabbing frames
    return True

def reset_head(node):
    aim_head(node, 0.0, 0.0)

# ---------------------------------------------------------------------------
AUTOSCAN_PERIOD = 1.5   

_autoscan_enabled = threading.Event()
_autoscan_holds = 0
_autoscan_lock = threading.Lock()

def autoscan_hold():
    global _autoscan_holds
    with _autoscan_lock:
        _autoscan_holds += 1

def autoscan_release():
    global _autoscan_holds
    with _autoscan_lock:
        _autoscan_holds = max(0, _autoscan_holds - 1)

def _autoscan_paused():
    with _autoscan_lock:
        return _autoscan_holds > 0

def autoscan_loop(node):
    """Body of the autoscan daemon thread. Head is left where it is (no tilt
    sweep: nodding every 1.5 s would be unusable); the manual 'scan' command
    still does the full multi-tilt scan."""
    last = None
    warned_camera = False
    while rclpy.ok():
        try:
            if not _autoscan_enabled.is_set() or _autoscan_paused():
                time.sleep(0.2)
                last = None  # re-announce after a pause: the scene may have changed
                continue
            start = time.monotonic()
            seen = detect_frame(node, tag="auto", debug=False, timeout=5.0)
            if not _autoscan_enabled.is_set() or _autoscan_paused():
                continue  # a scan/mission started meanwhile: drop this stale frame
            if seen is None:
                if not warned_camera:
                    print("\n👁 (autoscan: camera not available — retrying quietly)")
                    warned_camera = True
                time.sleep(5.0)
                continue
            warned_camera = False
            cur = sorted(seen)
            if cur != last:
                if cur:
                    print("\n👁 autoscan: I can see " + ", ".join(cur))
                elif last:  # something was visible before, now nothing is
                    print("\n👁 autoscan: I no longer recognize any object")
                last = cur
            time.sleep(max(0.0, AUTOSCAN_PERIOD - (time.monotonic() - start)))
        except Exception as e:  # never let the autoscan thread die
            print(f"\n👁 (autoscan error, continuing: {e})")
            time.sleep(2.0)

def start_autoscan(node):
    _autoscan_enabled.set()
    threading.Thread(target=autoscan_loop, args=(node,), daemon=True).start()

def run_scan(node):
    """Multi-frame scan: a few frames per head tilt (straight ahead, then down
    toward table height), accumulating every object seen."""
    print("👀 Looking through the camera...")
    seen, got_any_frame, camera_down = [], False, False
    autoscan_hold()
    try:
        for tilt in HEAD_TILTS:
            aim_head(node, 0.0, tilt)
            for i in range(SCAN_FRAMES):
                frame_seen = detect_frame(node, tag=f"scan_t{tilt:+.2f}_{i}")
                if frame_seen is None:
                    camera_down = True  # no point retrying other tilts either
                    break
                got_any_frame = True
                seen += [s for s in frame_seen if s not in seen]
                time.sleep(0.3)
            if camera_down:
                break
    finally:
        reset_head(node)
        autoscan_release()
    if not got_any_frame:
        return "I cannot see anything: my camera is not available. Is the simulation running?"
    if not seen:
        return "I looked, but I do not recognize any object in front of me."
    if len(seen) == 1:
        return f"I can see a {seen[0]}."
    return "I can see " + ", ".join(f"a {n}" for n in seen[:-1]) + f" and a {seen[-1]}."

def scan_for_object(node, target, approach=None, frames=3, sweep=(0.0, 0.35, -0.35)):
    """Robust scan: several frames per head tilt per orientation, small yaw
    sweep between batches (re-sent as Nav2 goals so we never fight the
    controller on /cmd_vel). Returns True as soon as a label acceptable for
    `target` (see SCAN_LABEL_ALIASES) appears in any frame.
    `approach` is the (x, y, yaw) world pose the robot is standing at."""
    labels = scan_labels_for(target)
    if labels is None:
        print(f"(I have no way to visually recognize a {target} — skipping the camera check)")
        return False
    print(f"👀 Scanning for the {target}...")
    tag = target.replace(' ', '_')
    misses = 0
    autoscan_hold()
    try:
        for offset in sweep:
            if offset != 0.0:
                if approach is None:
                    break  # cannot rotate without a reference pose
                import nav_client
                ax, ay, ayaw = approach
                if nav_client.navigate_to_pose(node, ax, ay, ayaw + offset,
                                               timeout=30.0) != 'succeeded':
                    continue
            for tilt in HEAD_TILTS:
                aim_head(node, 0.0, tilt)
                for i in range(frames):
                    seen = detect_frame(node, tag=f"{tag}_y{offset:+.2f}_t{tilt:+.2f}_{i}")
                    if seen is None:
                        misses += 1
                        if misses >= MAX_FRAME_MISSES:
                            print("(camera keeps failing — giving up the visual check)")
                            return False
                        continue
                    misses = 0
                    if any(s in labels for s in seen):
                        return True
                    time.sleep(0.3)
    finally:
        reset_head(node)
        autoscan_release()
    return False

def speak(text):
    try:
        subprocess.run(["espeak-ng", "-v", "en-us", "-s", "150", text],
                       check=False, stderr=subprocess.DEVNULL)
    except FileNotFoundError:
        pass  # espeak-ng not installed: text-only mode


class CameraNode(Node):
    """Camera stream on a DEDICATED node with its own spin thread. Nothing
    else lives on this node, so mission/nav/detector callbacks can never
    starve or wedge the frame flow — the autoscan survives anything."""
    def __init__(self):
        super().__init__('voice_camera')
        from sensor_msgs.msg import Image
        from rclpy.qos import qos_profile_sensor_data
        self._msg = None
        self._event = threading.Event()
        self.create_subscription(Image, CAMERA_TOPIC, self._cb,
                                 qos_profile_sensor_data)

    def _cb(self, msg):
        self._msg = msg
        self._event.set()

    def grab(self, timeout=20.0):
        """Wait for the NEXT frame (None on timeout)."""
        self._event.clear()
        if self._event.wait(timeout):
            return self._msg
        return None

class VoiceInterfaceNode(Node):
    def __init__(self):
        super().__init__('voice_interface')
        self.scene_pub = self.create_publisher(String, '/tiago/scene_graph_perception', 10)
        self.response_sub = self.create_subscription(
            String, '/tiago/anomaly_response', self._response_cb, 10)
        self._response_event = threading.Event()
        self._last_response = None
        self.camera = None 
        from trajectory_msgs.msg import JointTrajectory
        self._head_pub = self.create_publisher(JointTrajectory, HEAD_TOPIC, 10)
        self._head_warned = False
        try:  
            from rclpy.action import ActionClient
            from nav2_msgs.action import NavigateToPose
            self._nav_client = ActionClient(self, NavigateToPose, '/navigate_to_pose')
        except ImportError:
            pass

    def _response_cb(self, msg):
        self._last_response = msg.data
        self._response_event.set()

    def wait_for_detector(self):
        printed = False
        while rclpy.ok() and self.scene_pub.get_subscription_count() == 0:
            if not printed:
                print("Waiting for the anomaly detector (run_detector.sh)...")
                printed = True
            time.sleep(1.0)

    def ask_detector(self, payload, timeout=20.0):
        self._response_event.clear()
        self._last_response = None
        self.scene_pub.publish(String(data=payload))
        if self._response_event.wait(timeout):
            return self._last_response
        return None

    def grab_camera_frame(self, timeout=20.0):  # generous: software rendering is slow
        if self.camera is None:
            return None
        return self.camera.grab(timeout)

def get_user_input(prompt, hint=None):
    """One user turn: typed text, or push-to-talk when the line is empty.
    Returns the text, None to re-prompt (mic error / silence), '' on EOF.
    hint biases the speech recognition toward an expected vocabulary."""
    try:
        text = input(prompt).strip()
    except EOFError:
        return ""
    if text:
        return text
    audio = record_audio()
    if audio is None:
        return None
    text = transcribe(audio, hint=hint)
    if not text:
        print("I heard nothing intelligible, please try again.")
        return None
    print(f'Heard: "{text}"')
    return text

YES_PATTERN = re.compile(r"\b(yes|yeah|yep|sure|ok|okay|confirm|proceed|go ahead)\b")

def parse_age(text):
    m = re.search(r"\d{1,3}", text)
    if m:
        return int(m.group())
    total, found = 0, False
    for w in normalize(text).split():
        if w in NUMBER_WORDS:
            total += NUMBER_WORDS[w]
            found = True
    return total if found else None

def ask_age():
    """Ask the user's age at startup. Returns the age, or None if not understood."""
    speak("Hello! Before we start, how old are you?")
    for _ in range(3):
        answer = get_user_input("TIAGo: How old are you? (number, Enter = speak): ")
        if answer == "":
            return None  # EOF
        if answer:
            age = parse_age(answer)
            if age and 0 < age < 120:
                return age
        print("Sorry, I did not catch a number.")
    return None

DONT_KNOW_PATTERN = re.compile(r"\b(?:don'?t know|do not know|no idea|not sure|unknown)\b")

# Frequent speech-to-text mishearings and plurals of one-word material answers
# (whisper base.en has no context to disambiguate a single spoken word).
MATERIAL_ALIASES = {
    "would": "wood", "word": "wood", "woods": "wood",
    "papers": "paper", "pepper": "paper",
    "glasses": "glass", "class": "glass",
    "metals": "metal", "medal": "metal", "mental": "metal",
    "plastics": "plastic",
    "fabrics": "fabric",
    "ceramics": "ceramic",
    "leathers": "leather",
    "mirrors": "mirror",
    "foods": "food",
}

# Spoken to whisper as initial_prompt so material words are favored transcriptions
MATERIAL_HINT = ("The material is one of: " + ", ".join(MATERIALS) +
                 ". Or answer: I don't know.")

def parse_material_answer(text):
    """Return a material from MATERIALS, 'unknown' for an explicit "I don't know",
    or None when the answer matches neither."""
    import difflib
    text = normalize(text)
    if DONT_KNOW_PATTERN.search(text):
        return "unknown"
    words = text.split()
    for w in words:
        if w in MATERIALS:
            return w
        if w in MATERIAL_ALIASES:
            return MATERIAL_ALIASES[w]
    for w in words:  # last resort: close mishearings ("papel" -> paper)
        close = difflib.get_close_matches(w, MATERIALS, n=1, cutoff=0.8)
        if close:
            return close[0]
    return None

def ask_material(obj_name):
    """Ask the user what obj_name is made of. Returns a material from MATERIALS,
    or 'unknown' when the user does not know (after at most one re-ask)."""
    question = f"What is the {obj_name} made of?"
    print(f"\n🤖 TIAGo: {question}")
    speak(question)
    attempts = 2  # initial ask + one re-ask
    while attempts > 0:
        answer = get_user_input(f"You ({', '.join(MATERIALS)} or 'I don't know', Enter = speak): ",
                                hint=MATERIAL_HINT)
        if answer == "":
            return "unknown"  # EOF: treat as don't know
        if answer is None:
            continue  # mic error / silence: re-prompt without consuming an attempt
        material = parse_material_answer(answer)
        if material is not None:
            return material
        attempts -= 1
        if attempts > 0:
            correction = (f"Sorry, I only know these materials: {', '.join(MATERIALS)}. "
                          f"What is the {obj_name} made of?")
            print(f"🤖 TIAGo: {correction}")
            speak(correction)
    fallback = "Alright, I will treat the material as unknown."
    print(f"🤖 TIAGo: {fallback}")
    speak(fallback)
    return "unknown"

SAFE_PREFIX = "Yes, I can do that"  # start of explain.py's 'safe' sentence

NAV_HINT = ("(Navigation stack not running — launch 'ros2 launch simulation "
            "nav.launch.py' instead of sim.launch.py to see the robot move.)\n")

def say(sentence):
    print(f"🤖 TIAGo: {sentence}\n")
    speak(sentence)

def confirm(prompt="You (yes/no, Enter = speak): "):
    answer = get_user_input(prompt)
    return bool(answer and YES_PATTERN.search(answer.lower()))

def run_mission(node, params):
    """Execute an approved action end-to-end (verdict safe, or warning confirmed
    by an adult): drive to object A, visually confirm it, drive to object B in
    the destination room, confirm it, then declare the action feasible.
    Needs 'ros2 launch simulation nav.launch.py'; degrades gracefully otherwise.
    If a scan cannot find the expected object, the robot reports it, stops,
    and asks the human whether to proceed anyway."""
    try:
        import nav_client
    except ImportError as e:
        print(f"(navigation support unavailable: {e})")
        return
    room = params["room"]
    room_spoken = room.replace('_', ' ')
    if room not in nav_client.WORLD_WAYPOINTS:
        say(f"I do not know how to reach the {room_spoken}, so I will stay here.")
        return
    obj_a, obj_b = params["obj_a"], params["obj_b"]

    # ── leg A: fetch (and visually confirm) the object to move ──
    loc_a = semantic_map.locate(obj_a)
    if loc_a is None:
        say(f"I do not know where the {obj_a} is. "
            f"Should I go to the {room_spoken} anyway?")
        if not confirm():
            say("Okay, I am stopping the task.")
            return
    elif loc_a[0] == room:
        say(f"The {obj_a} is already in the {room_spoken}, so I will look "
            f"for it there.")
        loc_a = None  # single leg: both objects checked in the target room
    else:
        room_a, ax, ay, ayaw = loc_a
        say(f"The {obj_a} is in the {room_a.replace('_', ' ')}. "
            f"I will go get it first.")
        result = nav_client.navigate_to_pose(node, ax, ay, ayaw)
        if result == 'unavailable':
            print(NAV_HINT)
            return
        if result == 'failed':
            say(f"I am sorry, I could not reach the {obj_a}. I am stopping the task.")
            return
        if scan_for_object(node, obj_a, (ax, ay, ayaw)):
            say(f"I can see the {obj_a}. I am taking it with me.")
        else:
            say(f"I looked, but I cannot find the {obj_a}. Should I proceed anyway?")
            if not confirm():
                say("Okay, I am stopping the task.")
                return

    # ── leg B: reach the destination object in the target room ──
    loc_b = semantic_map.locate(obj_b)
    if loc_b is not None and loc_b[0] == room:
        bx, by, byaw = loc_b[1:]
    else:
        bx, by, byaw = nav_client.WORLD_WAYPOINTS[room]
    say(f"I am going to the {room_spoken} now.")
    result = nav_client.navigate_to_pose(node, bx, by, byaw)
    if result == 'unavailable':
        print(NAV_HINT)
        return
    if result == 'failed':
        say(f"I am sorry, I could not reach the {room_spoken}. I am stopping the task.")
        return
    if not scan_for_object(node, obj_b, (bx, by, byaw)):
        say(f"I have reached the {room_spoken}, but I cannot find the {obj_b}. "
            f"Should I proceed anyway?")
        if not confirm():
            say("Okay, I am stopping the task.")
            return
        say(f"Understood. I will place the {obj_a} where the {obj_b} should be. "
            f"Task complete.")
        return
    phrase = INTERACTION_PHRASE.get(params["interaction"],
                                    params["interaction"].replace('_', ' '))
    say(f"I have reached the {room_spoken} and I can see the {obj_b}. "
        f"I will now place the {obj_a} {phrase} the {obj_b}. Task complete.")

def interactive_loop(node):
    print("\n" + "=" * 62)
    print(" TIAGo voice interface")
    print("  - type a sentence and press Enter, OR")
    print(f"  - press Enter on an empty line to record {RECORD_SECONDS}s of speech")
    print("  - example: put the hair dryer in the bathtub in the bathroom")
    print("  - say 'scan' to have TIAGo look through its camera")
    print(f"  - autoscan runs every {AUTOSCAN_PERIOD}s and announces changes"
          " (type 'autoscan off'/'autoscan on')")
    print("  - type 'quit' to exit")
    print("=" * 62)
    node.wait_for_detector()
    print("Anomaly detector connected. Ready!\n")

    # ── user profile: minors get warnings turned into firm denials ──
    age = ask_age()
    child_mode = age is None or age < ADULT_AGE
    if age is None:
        print("(I could not understand the age — child mode enabled for safety)")
        greeting = "I did not catch your age, so I will be extra careful with risky actions."
    elif child_mode:
        greeting = f"Thank you! Since you are {age}, I will refuse any risky action."
    else:
        greeting = f"Thank you! You are {age}, so I will ask for your confirmation on risky actions."
    print(f"\n🤖 TIAGo: {greeting}\n")
    speak(greeting)

    start_autoscan(node) 

    while rclpy.ok():
        text = get_user_input("You (Enter = speak): ")
        if text is None:
            continue
        if text == "":
            break

        if text.lower() in ("quit", "exit", "q"):
            break

        if normalize(text) in ("autoscan on", "autoscan off"):
            if normalize(text).endswith("on"):
                _autoscan_enabled.set()
                print("(autoscan resumed)\n")
            else:
                _autoscan_enabled.clear()
                print("(autoscan stopped — type 'autoscan on' to resume)\n")
            continue

        if normalize(text) in SCAN_COMMANDS or normalize(text).startswith("scan"):
            sentence = run_scan(node)
            print(f"\n🤖 TIAGo: {sentence}\n")
            speak(sentence)
            continue

        params, error = parse_command(text)
        if params is None:
            print(f"Sorry, I could not understand. {error}")
            print("Try: 'put the <object> in/on/near the <object> in the <room>'")
            continue

        if not params["room_found"]:
            room_note = (f"You did not mention a room, so I will assume the "
                         f"{DEFAULT_ROOM.replace('_', ' ')}.")
            print(f"\n🤖 TIAGo: {room_note}")
            speak(room_note)
            
        for obj_key, mat_key in (("obj_a", "mat_a"), ("obj_b", "mat_b")):
            if params[mat_key] == "unknown":
                looked_up = materials_db.get(params[obj_key])
                if looked_up is not None:
                    params[mat_key] = looked_up
                    print(f"({params[obj_key]} is {looked_up}, from the material table)")
                else:
                    params[mat_key] = ask_material(params[obj_key])

        print(f"Parsed: {params['interaction']}({params['obj_a']} [{params['mat_a']}] -> "
              f"{params['obj_b']} [{params['mat_b']}]) in {params['room']}")

        payload = (f"{params['obj_a']}, {params['mat_a']}, {params['obj_b']}, "
                   f"{params['mat_b']}, {params['interaction']}, {params['room']}")
        response = node.ask_detector(payload)
        if response is None:
            print("No answer from the detector — is run_detector.sh still running?")
            continue

        if CONFIRM_QUESTION in response and child_mode:
            response = CHILD_SENTENCE

        print(f"\n🤖 TIAGo: {response}\n")
        speak(response)


        if response.startswith(SAFE_PREFIX):
            run_mission(node, params)

        if CONFIRM_QUESTION in response:
            answer = get_user_input("You (yes/no, Enter = speak): ")
            if answer and YES_PATTERN.search(answer.lower()):
                reply = "Understood. I will proceed, but please supervise me."
                print(f"\n🤖 TIAGo: {reply}\n")
                speak(reply)
                run_mission(node, params)
            else:
                reply = "Okay, I will not do it."
                print(f"\n🤖 TIAGo: {reply}\n")
                speak(reply)

def main(args=None):
    rclpy.init(args=args)
    node = VoiceInterfaceNode()
    camera = CameraNode()
    node.camera = camera
    # separate executors: a stall on the voice node can never stop the camera
    spin_thread = threading.Thread(target=rclpy.spin, args=(node,), daemon=True)
    camera_thread = threading.Thread(target=rclpy.spin, args=(camera,), daemon=True)
    spin_thread.start()
    camera_thread.start()
    try:
        interactive_loop(node)
    except KeyboardInterrupt:
        pass
    finally:
        rclpy.try_shutdown()          # stops the spin threads cleanly
        spin_thread.join(timeout=2.0)
        camera_thread.join(timeout=2.0)

if __name__ == '__main__':
    main()
