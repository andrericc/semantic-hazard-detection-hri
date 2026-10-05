
MATERIALS_DB = {
    # food
    "apple":         "food",
    "banana":        "food",
    "orange":        "food",
    "sandwich":      "food",
    # paper
    "book":          "paper",
    # plastic
    "bottle":        "plastic",
    "clock":         "plastic",
    "hair drier":    "plastic",
    "keyboard":      "plastic",
    "mouse":         "plastic",
    "remote":        "plastic",
    "cell phone":    "plastic",
    "toothbrush":    "plastic",
    # metal
    "knife":         "metal",
    "fork":          "metal",
    "spoon":         "metal",
    "scissors":      "metal",
    "laptop":        "metal",
    "microwave":     "metal",
    "oven":          "metal",
    "toaster":       "metal",
    "refrigerator":  "metal",
    # ceramic
    "bowl":          "ceramic",
    "cup":           "ceramic",
    "sink":          "ceramic",
    "toilet":        "ceramic",
    # glass
    "tv":            "glass",
    "vase":          "glass",
    "wine glass":    "glass",
    # wood
    "chair":         "wood",
    "dining table":  "wood",
    "bench":         "wood",
    # fabric
    "bed":           "wood",
    "couch":         "fabric",
    "teddy bear":    "fabric",
    "handbag":       "leather",
    "suitcase":      "fabric",
    # foliage
    "potted plant":  "foliage",
}


def get(object_name):
    """Return the material for object_name, or None if it is not in the table.
    Matching is case-insensitive and tolerant of surrounding whitespace."""
    if object_name is None:
        return None
    return MATERIALS_DB.get(object_name.strip().lower())
