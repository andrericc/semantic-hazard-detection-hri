
import re

ELECTRICAL, FLAMMABLE, SHARP, TOXIC, WATER_SENSITIVE, HEAVY, FOOD, HEAT_SOURCE, FRAGILE = range(9)


ELECTRICAL_KW = {'hair dryer', 'hair_dryer', 'dryer', 'tv', 'television', 'lamp',
                 'computer', 'laptop', 'phone', 'tablet', 'charger', 'radio',
                 'microwave', 'oven', 'toaster', 'fridge', 'refrigerator',
                 'speaker', 'vacuum', 'kettle', 'iron', 'fan', 'heater',
                 'console', 'monitor', 'clock'}
HEAT_SOURCE_KW = {'stove', 'oven', 'toaster', 'heater', 'microwave', 'radiator',
                  'fireplace', 'candle', 'grill', 'iron', 'kettle'}
SHARP_KW = {'knife', 'scissors', 'fork', 'razor', 'blade', 'saw', 'needle', 'axe'}
TOXIC_KW = {'bleach', 'detergent', 'cleaner', 'soap', 'medicine', 'pills',
            'chemical', 'paint', 'glue', 'pesticide'}
HEAVY_KW = {'dumbbells', 'dumbbell', 'television', 'tv', 'microwave', 'oven',
            'suitcase', 'couch', 'refrigerator', 'fridge', 'washing machine',
            'washing_machine', 'toolbox', 'safe'}
FLAMMABLE_MAT = {'paper', 'wood', 'fabric', 'foliage', 'leather'}
FRAGILE_MAT = {'glass', 'ceramic', 'mirror'}
WATER_CONTAINERS = {'bathtub', 'bath', 'sink', 'toilet', 'washing_machine',
                    'washing machine', 'pool', 'aquarium', 'bucket'}
WATER_CONTEXTS = {'bathroom', 'utility_room'}
CHILD_CONTEXTS = {'childs_room', 'playroom'}
CHILD_SOFT_SPOTS = {'bed', 'couch', 'play_mat', 'play mat', 'teddy bear', 'crib'}
FOOD_STORAGE = {'refrigerator', 'fridge', 'oven', 'microwave',
                'dining table', 'dining_table', 'pantry'}

INTERACTION_PHRASE = {
    'placed_on_top': 'on top of',
    'placed_inside': 'inside',
    'placed_near':   'near',
}

CONFIRM_QUESTION = "Do you confirm that I should proceed?"

CHILD_SENTENCE = "No, I cannot do that. It is not safe. Please ask an adult for help."


def _phrase(interaction):
    return INTERACTION_PHRASE.get(interaction, interaction.replace('_', ' '))


def _norm(name):
    return (name or '').lower().replace('_', ' ').strip()


def _matches(name, kw_set):
    """True if any keyword appears in the object name as whole word(s)
    (word-boundary match, so 'fan' does NOT match 'infant')."""
    n = _norm(name)
    for kw in kw_set:
        if re.search(r"\b" + re.escape(_norm(kw)) + r"\b", n):
            return True
    return False


def augment_profile(obj_name, material, prof):
    """OR the model's danger profile with the richer lexical flags."""
    p = list(prof) if prof is not None else [0.0] * 9
    mat = _norm(material)
    if _matches(obj_name, ELECTRICAL_KW):
        p[ELECTRICAL] = 1.0
        p[WATER_SENSITIVE] = 1.0
    if _matches(obj_name, HEAT_SOURCE_KW):
        p[HEAT_SOURCE] = 1.0
    if _matches(obj_name, SHARP_KW):
        p[SHARP] = 1.0
    if _matches(obj_name, TOXIC_KW):
        p[TOXIC] = 1.0
    if _matches(obj_name, HEAVY_KW):
        p[HEAVY] = 1.0
    if mat in FLAMMABLE_MAT:
        p[FLAMMABLE] = 1.0
    if mat in FRAGILE_MAT:
        p[FRAGILE] = 1.0
    return p


def _is_water_related(obj_class, context):
    return _matches(obj_class, WATER_CONTAINERS) or context in WATER_CONTEXTS


def explain_refusal(obj_a, mat_a, prof_a, obj_b, mat_b, prof_b, interaction, context):

    a = augment_profile(obj_a, mat_a, prof_a)
    b = augment_profile(obj_b, mat_b, prof_b)
    na, nb = _norm(obj_a), _norm(obj_b)
    inside_or_near = interaction in ('placed_inside', 'placed_near')
    room = context.replace('_', ' ')

    # 1. electrical / water-sensitive object + water -> electrocution / damage
    if (a[ELECTRICAL] or a[WATER_SENSITIVE]) and _is_water_related(nb, context) and inside_or_near:
        if a[ELECTRICAL]:
            return 'electric_water', (
                f"the {na} is an electrical device, and the {nb} may contain water. "
                f"Together they create a serious risk of electric shock")
        return 'water_damage', (
            f"the {na} could be damaged by the water in the {nb}")

    # 2. flammable object + heat source -> fire
    if a[FLAMMABLE] and (b[HEAT_SOURCE] or _matches(nb, HEAT_SOURCE_KW)):
        return 'fire', (
            f"the {na} can catch fire, and the {nb} gets hot. "
            f"This could start a fire in the {room}")

    # 3. heavy object on fragile support -> breakage
    if a[HEAVY] and (b[FRAGILE] or _matches(nb, {'glass table', 'glass shelf'})) \
            and interaction == 'placed_on_top':
        return 'breakage', (
            f"the {na} is too heavy for the {nb}, which is fragile and could shatter")

    # 4. sharp object in child areas or on soft resting surfaces -> injury
    if a[SHARP] and (context in CHILD_CONTEXTS or _matches(nb, CHILD_SOFT_SPOTS)):
        return 'injury', (
            f"the {na} is sharp, and leaving it {_phrase(interaction)} the {nb} "
            f"means someone could get hurt")

    # 5. toxic substance near food or food storage -> contamination
    if a[TOXIC] and (b[FOOD] or _matches(nb, FOOD_STORAGE)):
        return 'contamination', (
            f"the {na} contains chemicals that could contaminate food "
            f"if kept {_phrase(interaction)} the {nb}")

    # 6. food in non-food appliances / places
    if a[FOOD] and b[ELECTRICAL] and not _matches(nb, FOOD_STORAGE):
        return 'food_misplacement', (
            f"the {nb} is not a safe place to keep food")

    # 7. fragile object onto a heat source
    if a[FRAGILE] and (b[HEAT_SOURCE] or _matches(nb, HEAT_SOURCE_KW)):
        return 'fragile_heat', (
            f"the {na} is fragile and the {nb} gets hot, so it could crack")

    # fallback: the network flagged it but no rule matches
    return 'atypical', (
        f"a {na} is not normally placed {_phrase(interaction)} a {nb} "
        f"in the {room}, so I cannot be sure it is safe")


def sentence_for_unknown_room(context):
    room = _norm(context)
    return (f"I do not know the room called {room}, "
            f"so I cannot evaluate whether this action is safe.")


def sentence_for_status(status, obj_a, mat_a, prof_a, obj_b, mat_b, prof_b,
                        interaction, context, child_mode=False):
    if status == 'safe':
        return "Yes, I can do that. The action looks safe."

    reason_key, reason = explain_refusal(
        obj_a, mat_a, prof_a, obj_b, mat_b, prof_b, interaction, context)

    if child_mode:
        return CHILD_SENTENCE

    if status == 'warning':
        if reason_key == 'atypical':
            return (f"I am not sure this is safe: {reason}. "
                    f"{CONFIRM_QUESTION}")
        return (f"I have a concern: {reason}. "
                f"{CONFIRM_QUESTION}")

    return f"No, I will not do that: {reason}."
