import numpy as np
import os
import glob


SCENE_FILES = glob.glob('./dataset/**/*.npz', recursive=True)

print(f"Found {len(SCENE_FILES)} file .npz")
for f in SCENE_FILES:
    print(f" - {f}")

global_keys = set()
global_affordances = set()
global_attributes = set()

print("Global set extraction\n")

for file_path in SCENE_FILES:
    if os.path.exists(file_path):
        print(f"Analyzing: {os.path.basename(file_path)}...")
        data = np.load(file_path, allow_pickle=True)
        scene_graph = data['output'].item()
        objects_dict = scene_graph.get('object', {})
        
        for obj_id, obj_info in objects_dict.items():
            global_keys.update(obj_info.keys())
            
            affs = obj_info.get('action_affordance', [])
            if isinstance(affs, list):
                global_affordances.update([a.strip().lower() for a in affs if a is not None])
                
            attrs = obj_info.get('attributes', [])
            if isinstance(attrs, list):
                global_attributes.update([a.strip().lower() for a in attrs if a is not None])
    else:
        print(f" File not found: {file_path}")

print("\n Results:")

print(f"Total node KEYS ({len(global_keys)} found):")
print(global_keys)

print(f"\n Unique AFFORDANCES ({len(global_affordances)} found):")
print(global_affordances)

print(f"\nUnique ATTRIBUTES ({len(global_attributes)} trovati):")
print(global_attributes)


MATERIAL_PROPERTIES = {
    'metal': (5000.0, 2.0),     
    'oven': (3000.0, 1.5),      
    'ceramic': (2200.0, 1.5),  
    'glass': (2500.0, 1.0),    
    'mirror': (2500.0, 1.0),   
    'wood': (600.0, 1.5),      
    'plastic': (1000.0, 0.8),  
    'leather': (900.0, 0.5),  
    'food': (1000.0, 0.1),    
    'fabric': (200.0, 0.1),    
    'paper': (100.0, 0.05),    
    'foliage': (150.0, 0.01),  
    'other': (1000.0, 0.5),     
    'unknown': (1000.0, 0.5)    
}

def estimate_mass_and_capacity(material_str, volume):
    primary_material = material_str.split(',')[0].strip().lower()
    
    density, load_factor = MATERIAL_PROPERTIES.get(primary_material, MATERIAL_PROPERTIES['unknown'])
    
    mass = volume * density
    max_load_capacity = mass * load_factor
    
    return mass, max_load_capacity

import pandas as pd
import random
from itertools import combinations, product

random.seed(42)

def extract_physical_properties(obj_info):
    obj_class = obj_info.get('class_', 'unknown').strip().lower()
    raw_materials = obj_info.get('material')
    if isinstance(raw_materials, list):
        valid_materials = [m for m in raw_materials if m is not None]
        material_str = ", ".join(valid_materials) if valid_materials else "unknown"
    elif isinstance(raw_materials, str):
        material_str = raw_materials
    else:
        material_str = "unknown"
        
    volume = obj_info.get('volume', 0.0) or 0.0
    affordances = obj_info.get('action_affordance', []) or []
        
    return obj_class, material_str, float(volume), affordances


def determine_valid_interactions(obj_a, obj_b):

    valid_interactions = ['placed_near'] 
    
    size_a = obj_a.get('size', [0, 0, 0])
    size_b = obj_b.get('size', [0, 0, 0])
    max_dim_a = max(size_a) if (size_a is not None and len(size_a) > 0) else 0.0
    max_dim_b = max(size_b) if (size_b is not None and len(size_b) > 0) else float('inf')
    
    vol_a = obj_a.get('volume', 0.0)
    vol_b = obj_b.get('volume', 0.0)

    if max_dim_a < max_dim_b:
        valid_interactions.append('placed_inside')

    is_not_too_bulky = vol_a < (vol_b * 2.5)
    if is_not_too_bulky:
        valid_interactions.append('placed_on_top')
            
    return valid_interactions

def build_raw_dataset_for_scene(npz_file_path, max_anomalies=1500):
    print(f" Estrazione dati dal file: {npz_file_path} ---")
    data = np.load(npz_file_path, allow_pickle=True)
    scene_graph = data['output'].item()
    objects_dict = scene_graph.get('object', {})
    rooms_dict = scene_graph.get('room', {})
    
    room_to_objects = {}
    for obj_id, obj_info in objects_dict.items():
        room_id = obj_info.get('parent_room')
        if room_id is None: continue
            
        room_category = rooms_dict.get(room_id, {}).get('scene_category', f'room_{room_id}').strip().lower()
        obj_class, material, volume, affordances = extract_physical_properties(obj_info)
        size = obj_info.get('size', [0, 0, 0]) 
        
        if room_category not in room_to_objects:
            room_to_objects[room_category] = []
            
        obj_identifier = (obj_class, material, volume, tuple(sorted(affordances)))
        is_duplicate = any(
            existing_obj.get('identifier') == obj_identifier 
            for existing_obj in room_to_objects[room_category]
        )
        
        if not is_duplicate:
            room_to_objects[room_category].append({
                'class': obj_class, 'material': material, 
                'volume': volume, 'size': size, 'affordances': affordances, 'room': room_category,
                'identifier': obj_identifier
            })

    dataset_rows = []

    for room, obj_list in room_to_objects.items():
        for obj_a, obj_b in combinations(obj_list, 2):
            valid_interactions = determine_valid_interactions(obj_a, obj_b)
            for interaction in valid_interactions:
                dataset_rows.append({
                    "Object_A": obj_a['class'], "Material_A": obj_a['material'], "Volume_A": obj_a['volume'], "Affordances_A": obj_a['affordances'],
                    "Interaction": interaction,
                    "Object_B": obj_b['class'], "Material_B": obj_b['material'], "Volume_B": obj_b['volume'], "Affordances_B": obj_b['affordances'],
                    "Context": room, "Type": "Intra"
                })

    cross_room_pairs = []
    categories = list(room_to_objects.keys())
    for i in range(len(categories)):
        for j in range(len(categories)):
            if i == j: continue
            for obj_a, obj_b in product(room_to_objects[categories[i]], room_to_objects[categories[j]]):
                valid_interactions = determine_valid_interactions(obj_a, obj_b)
                for interaction in valid_interactions:
                    cross_room_pairs.append({
                        "Object_A": obj_a['class'], "Material_A": obj_a['material'], "Volume_A": obj_a['volume'], "Affordances_A": obj_a['affordances'],
                        "Interaction": interaction,
                        "Object_B": obj_b['class'], "Material_B": obj_b['material'], "Volume_B": obj_b['volume'], "Affordances_B": obj_b['affordances'],
                        "Context": categories[j], "Type": "Cross"
                    })
                
    if len(cross_room_pairs) > max_anomalies:
        cross_room_pairs = random.sample(cross_room_pairs, max_anomalies)
        
    dataset_rows.extend(cross_room_pairs)
    df_scene = pd.DataFrame(dataset_rows)
    return df_scene
    

SCENE_FILES = glob.glob('./dataset/**/*.npz', recursive=True)

print(f"Found {len(SCENE_FILES)} file .npz:")
for f in SCENE_FILES:
    print(f" - {f}")

all_dfs = []
for file_path in SCENE_FILES:
    if os.path.exists(file_path):
        df_scene = build_raw_dataset_for_scene(file_path, max_anomalies=1500)
        all_dfs.append(df_scene)
    else:
        print(f"File not found -> {file_path}")

if all_dfs:
    df_raw = pd.concat(all_dfs, ignore_index=True)
    
    df_raw['Affordances_A'] = df_raw['Affordances_A'].apply(tuple)
    df_raw['Affordances_B'] = df_raw['Affordances_B'].apply(tuple)
    
    df_raw = df_raw.drop_duplicates().sample(frac=1, random_state=42).reset_index(drop=True)
    print(f"\n Global Dataset ready: {len(df_raw)} total interactions")
else:
    print(" No data loaded. Check Path in Scene Files.")
    df_raw = pd.DataFrame()

print(df_raw.head())

import pandas as pd
import numpy as np

def get_danger_profile(obj_class, material, volume, affordances):
    
    if affordances is None: affordances = []
    if material is None: material = "unknown"
    if obj_class is None: obj_class = "unknown"
        
    aff_str = " ".join(affordances).lower()
    mat_lower = material.lower()
    obj_class = obj_class.lower()
    
    elec_kws = ['tv', 'lamp', 'computer', 'microwave', 'oven', 'toaster', 'fridge', 'speaker', 'vacuum', 'plug', 'turn on']
    is_electrical = 1.0 if any(k in obj_class or k in aff_str for k in elec_kws) else 0.0
    
    flam_kws = ['paper', 'wood', 'fabric', 'foliage', 'leather', 'clothing', 'newspaper', 'book', 'towel']
    is_flammable = 1.0 if any(k in mat_lower or k in obj_class for k in flam_kws) else 0.0
    
    sharp_kws = ['knife', 'scissors', 'fork', 'cut', 'peel', 'glass']
    is_sharp = 1.0 if any(k in obj_class or k in aff_str or k in mat_lower for k in sharp_kws) else 0.0
    
    toxic_kws = ['bleach', 'soap', 'cleaner', 'detergent', 'medicine', 'chemical', 'wash']
    is_toxic = 1.0 if any(k in obj_class or k in aff_str for k in toxic_kws) else 0.0
    
    is_water_sensitive = 1.0 if (is_electrical == 1.0 or 'paper' in mat_lower) else 0.0
    
    try:
        mass, _ = estimate_mass_and_capacity(material, volume)
        is_heavy = 1.0 if mass > 2.0 else 0.0
    except Exception:
        is_heavy = 0.0
    
    food_kws = ['food', 'eat', 'drink', 'apple', 'snack', 'prepare']
    is_food = 1.0 if any(k in mat_lower or k in obj_class or k in aff_str for k in food_kws) else 0.0
    
    heat_kws = ['stove', 'oven', 'toaster', 'heater', 'microwave', 'radiator', 'cook']
    is_heat_source = 1.0 if any(k in obj_class or k in aff_str for k in heat_kws) else 0.0
    
    fragile_kws = ['glass', 'ceramic', 'mirror', 'monitor', 'screen', 'plate', 'cup']
    is_fragile = 1.0 if any(k in mat_lower or k in obj_class for k in fragile_kws) else 0.0
    
    return [is_electrical, is_flammable, is_sharp, is_toxic, is_water_sensitive, is_heavy, is_food, is_heat_source, is_fragile]

df_raw['Danger_Profile_A'] = df_raw.apply(
    lambda r: get_danger_profile(r['Object_A'], r['Material_A'], r['Volume_A'], r['Affordances_A']), axis=1
)
df_raw['Danger_Profile_B'] = df_raw.apply(
    lambda r: get_danger_profile(r['Object_B'], r['Material_B'], r['Volume_B'], r['Affordances_B']), axis=1
)

print(df_raw[['Object_A', 'Danger_Profile_A', 'Object_B', 'Danger_Profile_B']].head(10))

import torch

print(" Edge Targets building")

def create_edge_target(danger_a, danger_b, interaction):

    interaction_map = {
        'placed_on_top': [1.0, 0.0, 0.0],
        'placed_inside': [0.0, 1.0, 0.0],
        'placed_near':   [0.0, 0.0, 1.0]
    }
    
    target_vector = interaction_map.get(interaction, [0.0, 0.0, 0.0])
    return target_vector

df_raw['Edge_Target'] = df_raw.apply(
    lambda r: create_edge_target(r['Danger_Profile_A'], r['Danger_Profile_B'], r['Interaction']),
    axis=1
)

print(" Generated edge target.")

print(df_raw[['Object_A', 'Interaction', 'Object_B', 'Edge_Target']].head())

import json
import time
import os
import anthropic
import glob

# Percorso aggiornato per la cache locale
WORKING_CACHE_FILE = "./dataset/claude_labels_cache.json"

def load_cache():
    cache = {}
    
    # Percorso aggiornato per cercare i JSON scaricati
    possible_files = glob.glob("./dataset/**/*.json", recursive=True)
    
    for f in possible_files:
        if "claude" in f.lower() and "cache" in f.lower():
            try:
                with open(f, 'r') as file:
                    uploaded_data = json.load(file)
                    cache.update(uploaded_data) 
                    print(f" Found and merged cache {f}: {len(uploaded_data)} elements.")
            except Exception as e:
                print(f"Error loading cache ({f}): {e}")
                
    if not cache:
        print(" No cache file found in ./dataset/")
        
    if os.path.exists(WORKING_CACHE_FILE):
        try:
            with open(WORKING_CACHE_FILE, 'r') as f:
                working_data = json.load(f)
                cache.update(working_data)
                print(f" Found and merged cache: {len(working_data)} elements.")
        except Exception as e:
            print(f" Error loading cache: {e}")
            
    print(f" Total elements in cache: {len(cache)}")
    return cache

def save_cache(cache_data):
    with open(WORKING_CACHE_FILE, 'w') as f:
        json.dump(cache_data, f, indent=4)

# API key from environment: only needed when labeling objects missing from the JSON caches
MY_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")
client = anthropic.Anthropic(api_key=MY_API_KEY)
MODEL_ID = "claude-opus-4-5"

SYSTEM_PROMPT = """You are the supervision and safety module of a smart domestic robot.
Your task is to evaluate whether placing two objects together in a given room context
constitutes a SAFE/NORMAL SITUATION (0) or a SEVERE ANOMALY/DANGER (1).

CRITERIA FOR 1 (SEVERE ANOMALY / UNSAFE):
Assign 1 only if the specific combination of objects causes:
[A] CRITICAL DANGER: Electronics + Water proximity. Heat sources near flammables.
[B] CATASTROPHIC DAMAGE: Extremely heavy objects placed ON TOP OF fragile items.
[C] EXTREME CONTAMINATION: Non-food/dirty items INSIDE kitchen appliances.
[D] SHARP/TOXIC HAZARD: Dangerous objects (knives, chemicals) accessible in child/pet spaces.

CRITERIA FOR 0 (SAFE / NORMAL):
Assign 0 if the action is physically safe, EVEN IF it is weird, messy, or contextually unusual.
Being in an unexpected room does NOT make something dangerous by itself.

IMPORTANT: Base your judgment on the PHYSICAL DANGER of the combination, not on whether
it seems contextually appropriate. A knife in a bathroom is unusual but not inherently dangerous.

Respond EXCLUSIVELY with a JSON containing the array of labels (0 or 1). No other text."""

def call_with_retry(pairs_list, max_attempts=5):
    prompt = (
        f"Analyze these object interactions:\n"
        + "\n".join([f"{i+1}. {p}" for i, p in enumerate(pairs_list)])
        + "\nRespond ONLY with JSON: {\"labels\": [0, 1, ...]}"
    )
    for attempt in range(max_attempts):
        try:
            response = client.messages.create(
                model=MODEL_ID, max_tokens=1024, system=SYSTEM_PROMPT,
                messages=[{"role": "user", "content": prompt}]
            )
            raw = response.content[0].text.strip()
            if "```json" in raw:
                raw = raw.split("```json")[1].split("```")[0].strip()
            elif "```" in raw:
                raw = raw.split("```")[1].split("```")[0].strip()
            return json.loads(raw).get('labels', [])
        except Exception as e:
            print(f" Error API (attempt {attempt+1}/{max_attempts}): {e}")
            time.sleep(15 * (attempt + 1))
    return [0] * len(pairs_list)

def label_dataframe_optimized(df):
    if df.empty:
        print(" Input dataframe is empty.")
        return df
    df_copy = df.copy()
    cache = load_cache()
    df_copy['Prompt_Text'] = df_copy.apply(
        lambda r: (
            f"In a '{r['Context']}' setting: "
            f"take '{r['Object_A']}' (material: {r['Material_A']}) "
            f"and do '{r['Interaction']}' with "
            f"'{r['Object_B']}' (material: {r['Material_B']})"
        ), axis=1
    )
    all_prompts = df_copy['Prompt_Text'].unique().tolist()
    missing_prompts = [p for p in all_prompts if p not in cache]
    print(f"\n Labeling Stats:")
    print(f" - Total unique interactions: {len(all_prompts)}")
    print(f" - Found in cache: {len(all_prompts) - len(missing_prompts)}")
    print(f" - To process with API: {len(missing_prompts)}")
    if missing_prompts:
        print("\n API calls for missing interactions")
        batch_size = 30
        for i in range(0, len(missing_prompts), batch_size):
            batch = missing_prompts[i:i + batch_size]
            labels = call_with_retry(batch)
            if len(labels) != len(batch):
                print(f" Mismatch: received {len(labels)} labels for a batch of {len(batch)}. Fill with 0")
                labels = [0] * len(batch)
            for prompt, label in zip(batch, labels):
                cache[prompt] = label
            save_cache(cache)
            print(f" Processed {min(i + batch_size, len(missing_prompts))}/{len(missing_prompts)} new prompts.")
            time.sleep(2)
    else:
        print(" All anomalies in cache. No API calls executed")
        save_cache(cache)
    df_copy['Anomaly_Label'] = df_copy['Prompt_Text'].map(cache)
    return df_copy.drop(columns=['Prompt_Text', 'Type'])

df_labeled = label_dataframe_optimized(df_raw)

df_intra = df_labeled[~df_labeled['Context'].str.contains('_to_')].copy()
df_cross  = df_labeled[ df_labeled['Context'].str.contains('_to_')].copy()

import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
import seaborn as sns
import warnings
warnings.filterwarnings('ignore')

SAFE_COLOR   = "#2ecc71"
DANGER_COLOR = "#e74c3c"
ACCENT_COLOR = "#3498db"
BG_COLOR     = "#1a1a2e"
PANEL_COLOR  = "#16213e"
TEXT_COLOR   = "#ecf0f1"
GRID_COLOR   = "#2c3e50"

plt.rcParams.update({
    "figure.facecolor": BG_COLOR, "axes.facecolor": PANEL_COLOR,
    "axes.edgecolor": GRID_COLOR, "axes.labelcolor": TEXT_COLOR,
    "xtick.color": TEXT_COLOR,    "ytick.color": TEXT_COLOR,
    "text.color": TEXT_COLOR,     "grid.color": GRID_COLOR,
    "grid.alpha": 0.4,            "font.family": "DejaVu Sans",
    "axes.titlepad": 12,
})

fig, axes = plt.subplots(1, 3, figsize=(18, 5))
fig.suptitle("Dataset Overview", fontsize=15, fontweight='bold', y=1.02)

counts = df_labeled['Anomaly_Label'].value_counts().sort_index()
axes[0].pie(
    counts, labels=['Safe (0)', 'Danger (1)'],
    colors=[SAFE_COLOR, DANGER_COLOR], autopct='%1.1f%%', startangle=140,
    wedgeprops=dict(edgecolor=BG_COLOR, linewidth=2),
    textprops={'color': TEXT_COLOR, 'fontsize': 12}
)
axes[0].set_title("Label distribution", fontsize=13, fontweight='bold')

int_counts = df_labeled['Interaction'].value_counts()
bars = axes[1].bar(int_counts.index, int_counts.values,
                   color=[ACCENT_COLOR, '#9b59b6', '#e67e22'],
                   edgecolor=BG_COLOR, linewidth=1.5, width=0.6)
axes[1].set_title("Type of interaction", fontsize=13, fontweight='bold')
axes[1].set_ylabel("N° Samples"); axes[1].grid(axis='y', alpha=0.4)
axes[1].set_xticklabels(int_counts.index, rotation=20, ha='right')
for bar in bars:
    axes[1].text(bar.get_x() + bar.get_width()/2, bar.get_height() + 5,
                 f'{int(bar.get_height())}', ha='center', va='bottom', fontsize=10)

ctx_counts = df_intra['Context'].value_counts().sort_values()
hbars = axes[2].barh(ctx_counts.index, ctx_counts.values,
                     color=ACCENT_COLOR, edgecolor=BG_COLOR, linewidth=1.2, height=0.65)
axes[2].set_title("Samples for Room\n(intra-room)", fontsize=13, fontweight='bold')
axes[2].set_xlabel("N° Samples"); axes[2].grid(axis='x', alpha=0.4)
for bar in hbars:
    axes[2].text(bar.get_width() + 2, bar.get_y() + bar.get_height()/2,
                 f'{int(bar.get_width())}', va='center', fontsize=9)

plt.tight_layout()
plt.savefig('viz1_dataset_overview.png', dpi=150, bbox_inches='tight', facecolor=BG_COLOR)
# plt.show()

print(f"Total samples: {len(df_labeled)} | Safe: {counts[0]} | Danger: {counts[1]}")
if len(df_labeled) > 0:
    print(f"Anomaly rate: {counts.get(1, 0)/len(df_labeled)*100:.1f}%")

fig, axes = plt.subplots(1, 2, figsize=(16, 5))
fig.suptitle("Anomalies analysis for context and material", fontsize=15, fontweight='bold', y=1.02)

ctx_label = df_intra.groupby(['Context', 'Anomaly_Label']).size().unstack(fill_value=0)
ctx_label.columns = ['Safe', 'Danger'] if len(ctx_label.columns) == 2 else ctx_label.columns
ctx_label = ctx_label.sort_values('Danger', ascending=True) if 'Danger' in ctx_label.columns else ctx_label
ctx_label.plot(kind='barh', stacked=True, color=[SAFE_COLOR, DANGER_COLOR][:len(ctx_label.columns)],
               edgecolor=BG_COLOR, linewidth=1.2, ax=axes[0], legend=True, width=0.65)
axes[0].set_title("Safe vs Danger for room\n(intra-room)", fontsize=13, fontweight='bold')
axes[0].set_xlabel("N° Interactions")
axes[0].legend(facecolor=PANEL_COLOR, edgecolor=GRID_COLOR); axes[0].grid(axis='x', alpha=0.4)

df_simple_mat = df_intra[~df_intra['Material_A'].str.contains(',')].copy()
pivot = df_simple_mat.groupby(['Material_A', 'Anomaly_Label']).size().unstack(fill_value=0)
pivot.columns = ['Safe', 'Danger'] if len(pivot.columns) == 2 else pivot.columns
heat_data = pivot[['Safe', 'Danger']].T if 'Danger' in pivot.columns else pivot.T
sns.heatmap(heat_data, ax=axes[1], cmap='RdYlGn_r', annot=True, fmt='g',
            linewidths=0.5, linecolor=BG_COLOR, cbar_kws={'label': 'Count'})
axes[1].set_title("Counting for material (Object A)\n", fontsize=13, fontweight='bold')
axes[1].set_xticklabels(axes[1].get_xticklabels(), rotation=35, ha='right')

plt.tight_layout()
plt.savefig('viz2_anomaly_context.png', dpi=150, bbox_inches='tight', facecolor=BG_COLOR)
# plt.show() 

if 'Danger' in ctx_label.columns:
    print("Room with most anomalies:", ctx_label['Danger'].idxmax(),
          f"({int(ctx_label['Danger'].max())} danger)")

if not df_labeled.empty and 'Anomaly_Label' in df_labeled.columns:
    print(f"\n Total critical anomalies: {df_labeled['Anomaly_Label'].sum()} su {len(df_labeled)}")
    print(f"Distribution:\n{df_labeled['Anomaly_Label'].value_counts()}")


import torch
import numpy as np
import pandas as pd
from sentence_transformers import SentenceTransformer
from torch_geometric.data import Data
from sklearn.model_selection import train_test_split
import random
 
random.seed(42)
embedder = SentenceTransformer('all-MiniLM-L6-v2')
 
df_labeled['Node_A_str'] = df_labeled['Object_A'] + " made of " + df_labeled['Material_A']
df_labeled['Node_B_str'] = df_labeled['Object_B'] + " made of " + df_labeled['Material_B']
df_labeled['Edge_str']   = df_labeled['Interaction']
 
df_safe   = df_labeled[df_labeled['Anomaly_Label'] == 0].copy()
df_danger = df_labeled[df_labeled['Anomaly_Label'] == 1].copy()
 
df_safe_train, df_safe_temp = train_test_split(df_safe, test_size=0.4, random_state=42)
df_safe_val,   df_safe_test = train_test_split(df_safe_temp, test_size=0.5, random_state=42)
df_danger_val, df_danger_test = train_test_split(df_danger, test_size=0.5, random_state=42)
 
print(f"Safe  → Train: {len(df_safe_train)} | Val: {len(df_safe_val)} | Test: {len(df_safe_test)}")
print(f"Danger→ Val:   {len(df_danger_val)} | Test: {len(df_danger_test)}")
 
room_graphs_train    = {}
room_node_maps_train = {}
 
print("\nBuilding graphs (train)")
for room_name, group in df_safe_train.groupby('Context'):
    

    node_data = {}
    for _, row in group.iterrows():
        na = str(row['Node_A_str'])
        nb = str(row['Node_B_str'])
        if na not in node_data: node_data[na] = row['Danger_Profile_A']
        if nb not in node_data: node_data[nb] = row['Danger_Profile_B']
            
    unique_nodes = list(node_data.keys())
    node_to_id   = {node: i for i, node in enumerate(unique_nodes)}
 
    text_embeddings = embedder.encode(unique_nodes, convert_to_tensor=True).cpu()
    danger_embeddings = torch.tensor([node_data[n] for n in unique_nodes], dtype=torch.float32)
    node_embeddings = torch.cat([text_embeddings, danger_embeddings], dim=1)
    
    edge_targets_list = group['Edge_Target'].tolist()
    edge_embeddings = torch.tensor(edge_targets_list, dtype=torch.float32)

    src = group['Node_A_str'].map(node_to_id).values
    dst = group['Node_B_str'].map(node_to_id).values
    edge_index = torch.tensor(np.vstack((src, dst)), dtype=torch.long)
 
    room_graphs_train[room_name]    = Data(x=node_embeddings, edge_index=edge_index, y_edge_attr=edge_embeddings)
    room_node_maps_train[room_name] = node_to_id
 
print(f"Created {len(room_graphs_train)} graphs. Dimension feature node: {node_embeddings.shape[1]}")

import networkx as nx
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches

INTERACTION_COLORS = {
    'placed_on_top': '#f39c12',
    'placed_inside': '#9b59b6',
    'placed_near':   '#3498db',
}
INTERACTION_STYLES = {
    'placed_on_top': 'solid',
    'placed_inside': 'dashed',
    'placed_near':   'dotted',
}

rooms_to_show = list(room_graphs_train.keys())[:3]

fig, axes = plt.subplots(1, len(rooms_to_show), figsize=(20, 7))
fig.suptitle(
    "3D Scene Graphs  Visualization graphs for room\n"
    "(nodes = objects, edges = physical interactions)",
    fontsize=14, fontweight='bold', y=1.02
)

for ax, room_name in zip(axes, rooms_to_show):
    graph_data   = room_graphs_train[room_name]
    node_map     = room_node_maps_train[room_name]  
    id_to_name   = {v: k for k, v in node_map.items()}
    edge_index   = graph_data.edge_index.cpu().numpy()

    room_df = df_safe_train[df_safe_train['Context'] == room_name]

    G = nx.DiGraph()
    n_nodes = graph_data.x.size(0)
    G.add_nodes_from(range(n_nodes))

    edge_interactions = {}
    for _, row in room_df.iterrows():
        id_a = node_map.get(row['Node_A_str'])
        id_b = node_map.get(row['Node_B_str'])
        if id_a is not None and id_b is not None:
            G.add_edge(id_a, id_b)
            edge_interactions[(id_a, id_b)] = row['Interaction']

    pos = nx.spring_layout(G, seed=42, k=2.2)

    nx.draw_networkx_nodes(G, pos, ax=ax,
                           node_color=ACCENT_COLOR, node_size=1400,
                           edgecolors='white', linewidths=1.5, alpha=0.92)

    labels = {i: id_to_name.get(i, str(i)).split(' made of ')[0].replace('_', '\n')
              for i in range(n_nodes)}
    nx.draw_networkx_labels(G, pos, ax=ax, labels=labels,
                            font_size=7, font_color=TEXT_COLOR, font_weight='bold')

    for interaction_type, color in INTERACTION_COLORS.items():
        style       = INTERACTION_STYLES[interaction_type]
        edge_subset = [(s, d) for (s, d), t in edge_interactions.items()
                       if t == interaction_type]
        if edge_subset:
            nx.draw_networkx_edges(G, pos, edgelist=edge_subset, ax=ax,
                                   edge_color=color, style=style,
                                   arrows=True, arrowsize=18, width=2,
                                   connectionstyle='arc3,rad=0.1', alpha=0.85)

    ax.set_facecolor(PANEL_COLOR)
    ax.set_title(
        f"🏠 {room_name.replace('_', ' ').title()}\n"
        f"{n_nodes} nodi  |  {G.number_of_edges()} archi",
        fontsize=12, fontweight='bold'
    )
    ax.axis('off')

legend_elements = [
    mpatches.Patch(color=ACCENT_COLOR, label='Object (Node)'),
    plt.Line2D([0],[0], color='#f39c12', lw=2, ls='solid',  label='placed_on_top'),
    plt.Line2D([0],[0], color='#9b59b6', lw=2, ls='dashed', label='placed_inside'),
    plt.Line2D([0],[0], color='#3498db', lw=2, ls='dotted', label='placed_near'),
]
fig.legend(handles=legend_elements, loc='lower center', ncol=4,
           facecolor=PANEL_COLOR, edgecolor=GRID_COLOR,
           fontsize=9, bbox_to_anchor=(0.5, -0.08))

plt.tight_layout()
plt.savefig('viz_graph_scene.png', dpi=150, bbox_inches='tight', facecolor=BG_COLOR)
# plt.show() 

print(f"Graphs visualized: {rooms_to_show}")

import torch.nn as nn
import torch.nn.functional as F
from torch_geometric.nn import SAGEConv
 
class RelationalGAE(nn.Module):
    def __init__(self, node_in_dim, hidden_dim, edge_out_dim, dropout=0.2):
        super().__init__()
        self.conv1 = SAGEConv(node_in_dim, hidden_dim)
        self.ln1   = nn.LayerNorm(hidden_dim)
        self.conv2 = SAGEConv(hidden_dim, hidden_dim)
        self.ln2   = nn.LayerNorm(hidden_dim)
        self.conv3 = SAGEConv(hidden_dim, hidden_dim)
        self.ln3   = nn.LayerNorm(hidden_dim)
 
        self.decoder = nn.Sequential(
            nn.Linear(hidden_dim * 2, hidden_dim * 2), nn.ReLU(), nn.Dropout(dropout),
            nn.Linear(hidden_dim * 2, hidden_dim),     nn.ReLU(), nn.Dropout(dropout),
            nn.Linear(hidden_dim, edge_out_dim)
        )
 
    def encode(self, x, edge_index):
        x = self.ln1(self.conv1(x, edge_index).relu())
        x = self.ln2(self.conv2(x, edge_index).relu())
        x = self.ln3(self.conv3(x, edge_index).relu())
        return x
 
    def decode(self, z, edge_index):
        return self.decoder(torch.cat([z[edge_index[0]], z[edge_index[1]]], dim=-1))
 
device       = torch.device('cuda' if torch.cuda.is_available() else 'cpu')
sample_graph = room_graphs_train[list(room_graphs_train.keys())[0]]

NODE_IN_DIM  = sample_graph.x.size(1) 
HIDDEN_DIM   = 128
EDGE_OUT_DIM = sample_graph.y_edge_attr.size(1) 
 
model = RelationalGAE(NODE_IN_DIM, HIDDEN_DIM, EDGE_OUT_DIM, dropout=0.2).to(device)
optimizer = torch.optim.Adam(model.parameters(), lr=0.001, weight_decay=1e-4)
scheduler = torch.optim.lr_scheduler.ReduceLROnPlateau(
    optimizer, mode='min', factor=0.5, patience=20, min_lr=1e-5
)


criterion = nn.MSELoss()
 
print(f"Model inizialized with MSE Loss on {device} (Input: {NODE_IN_DIM}, Output: {EDGE_OUT_DIM})")

import time
import numpy as np

def get_node_emb(obj_str, danger_profile, device_target):
    text_emb = embedder.encode(obj_str, convert_to_tensor=True).cpu()
    danger_emb = torch.tensor(danger_profile, dtype=torch.float32)
    full_emb = torch.cat([text_emb, danger_emb], dim=0).unsqueeze(0)
    return full_emb.to(device_target)

def get_inductive_score(row):
    context = row['Context']
    if context not in room_graphs_train: return None
        
    base_graph = room_graphs_train[context]
    local_map  = room_node_maps_train[context].copy()
    
    x_aug = base_graph.x.clone().to(device)
    edge_index_aug = base_graph.edge_index.clone().to(device)
    
    K = 3  
    node_a_str = f"{row['Object_A']} made of {row['Material_A']}"
    node_b_str = f"{row['Object_B']} made of {row['Material_B']}"
    
    nodes_to_add = [
        (node_a_str, row['Danger_Profile_A']), 
        (node_b_str, row['Danger_Profile_B'])
    ]
    
    for n_str, d_prof in nodes_to_add:
        if n_str not in local_map:
            raw_emb = get_node_emb(n_str, d_prof, device)
            
            sims = F.cosine_similarity(raw_emb, x_aug, dim=-1)
            topk = torch.topk(sims, min(K, x_aug.size(0))).indices
            
            new_id = x_aug.size(0)
            x_aug = torch.cat([x_aug, raw_emb], dim=0)
            local_map[n_str] = new_id
            
            for neighbor_id in topk:
                anchor_edge = torch.tensor([[new_id], [neighbor_id.item()]], dtype=torch.long, device=device)
                edge_index_aug = torch.cat([edge_index_aug, anchor_edge], dim=1)
    
    id_a = local_map[node_a_str]
    id_b = local_map[node_b_str]
    
    new_edge = torch.tensor([[id_a], [id_b]], dtype=torch.long, device=device)
    edge_index_aug = torch.cat([edge_index_aug, new_edge], dim=1)
    
    z_aug = model.encode(x_aug, edge_index_aug)
    pred_emb = model.decode(z_aug, new_edge)
    
    actual_emb = torch.tensor(row['Edge_Target'], dtype=torch.float32, device=device).unsqueeze(0)
    
    score = F.mse_loss(pred_emb, actual_emb).item()
    return score

def compute_val_loss_inductive():
    model.eval()
    total, count = 0.0, 0
    with torch.no_grad():
        for _, row in df_safe_val.iterrows():
            score = get_inductive_score(row)
            if score is not None:
                total += score
                count += 1
    return total / count if count > 0 else 0.0

def compute_anomaly_scores(df_subset):
    y_true, y_scores = [], []
    model.eval()
    with torch.no_grad():
        for row in df_subset:
            score = get_inductive_score(row)
            if score is not None:
                y_true.append(row['Anomaly_Label'])
                y_scores.append(score)
    return np.array(y_true), np.array(y_scores)

from sklearn.metrics import roc_auc_score, f1_score, classification_report
 
def train_rgae():
    model.train()
    total, count = 0.0, 0
    for data in room_graphs_train.values():
        if data.edge_index.size(1) == 0:
            continue
        data = data.to(device)
        optimizer.zero_grad()
        z    = model.encode(data.x, data.edge_index)
        pred = model.decode(z, data.edge_index)
        loss = criterion(pred, data.y_edge_attr)
        loss.backward()
        optimizer.step()
        total += loss.item()
        count += 1
    return total / count if count > 0 else 0.0
 
# ── Checkpoint: skip training if a saved model exists (delete the file to force retrain) ──
CKPT_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'rgae_checkpoint.pt')
_ckpt = None
if os.path.exists(CKPT_PATH):
    try:
        _tmp = torch.load(CKPT_PATH, map_location=device)
        if _tmp.get('node_in_dim') == NODE_IN_DIM and _tmp.get('edge_out_dim') == EDGE_OUT_DIM:
            _ckpt = _tmp
        else:
            print(f"[checkpoint] dim mismatch (got {_tmp.get('node_in_dim')}, expected {NODE_IN_DIM}) -> retraining")
    except Exception as e:
        print(f"[checkpoint] load failed ({e}) -> retraining")

if _ckpt is not None:
    model.load_state_dict(_ckpt['model_state_dict'])
    model.eval()
    print(f"[checkpoint] Loaded trained model from {CKPT_PATH} -- skipping training")
else:
    best_val_loss    = float('inf')
    patience_count   = 0
    PATIENCE         = 30
    best_model_state = None
    epochs           = 300
 
    print(f"Training with MSE (max {epochs} epochs)")
    t_start = time.time()

    train_loss_history, val_loss_history, lr_history = [], [], []

    for epoch in range(1, epochs + 1):
        t_ep       = time.time()
        train_loss = train_rgae()
        val_loss   = compute_val_loss_inductive()
        scheduler.step(val_loss)
 
        if epoch % 10 == 0:
            print(f"Epoch {epoch:03d} | Train Dist: {train_loss:.5f} | Val Dist: {val_loss:.5f} "
                  f"| LR: {optimizer.param_groups[0]['lr']:.6f} | {time.time()-t_ep:.1f}s/ep")

        train_loss_history.append(train_loss)
        val_loss_history.append(val_loss)
        lr_history.append(optimizer.param_groups[0]['lr'])
 
        if val_loss < best_val_loss - 1e-6:
            best_val_loss    = val_loss
            patience_count   = 0
            best_model_state = {k: v.clone() for k, v in model.state_dict().items()}
        else:
            patience_count += 1
            if patience_count >= PATIENCE:
                print(f"\n Early stopping at epoch {epoch}")
                break
 
    if best_model_state:
        model.load_state_dict(best_model_state)

    best_ep = int(np.argmin(val_loss_history)) + 1
    epoch_range = list(range(1, len(train_loss_history) + 1))
 
    fig, axes = plt.subplots(1, 2, figsize=(16, 5))
    fig.suptitle("Training plot for RelationalGAE", fontsize=15, fontweight='bold', y=1.02)
 
    axes[0].plot(epoch_range, train_loss_history, color=ACCENT_COLOR, linewidth=2, label='Train Loss')
    axes[0].plot(epoch_range, val_loss_history, color='#f39c12', linewidth=2, label='Val Loss')
    axes[0].axvline(best_ep, color=SAFE_COLOR, linestyle='--', alpha=0.8, label=f'Best epoch ({best_ep})')
    axes[0].fill_between(epoch_range, train_loss_history, val_loss_history, alpha=0.08, color='white')
    axes[0].set_title("MSE Edge Reconstruction Loss", fontsize=13, fontweight='bold')
    axes[0].set_xlabel("Epoch"); axes[0].set_ylabel("Loss")
    axes[0].legend(facecolor=PANEL_COLOR, edgecolor=GRID_COLOR); axes[0].grid(alpha=0.4)
 
    axes[1].plot(epoch_range, lr_history, color=DANGER_COLOR, linewidth=2)
    axes[1].set_title("Learning Rate Schedule", fontsize=13, fontweight='bold')
    axes[1].set_xlabel("Epoch"); axes[1].set_ylabel("Learning Rate")
    axes[1].set_yscale('log'); axes[1].grid(alpha=0.4)
 
    plt.tight_layout()
    plt.savefig('viz3_training_curve.png', dpi=150, bbox_inches='tight', facecolor=BG_COLOR)
    # plt.show() 

    print(f"Best val loss: {min(val_loss_history):.5f} at epoch {best_ep}")
    print(f"Total epochs: {len(epoch_range)} | Final LR : {lr_history[-1]:.6f}")

from sklearn.metrics import roc_curve, roc_auc_score, f1_score, classification_report, confusion_matrix, precision_recall_curve, auc
import matplotlib.pyplot as plt
import seaborn as sns

if _ckpt is not None:
    global_threshold = float(_ckpt['global_threshold'])
    print(f"\n[checkpoint] Loaded Global Threshold: {global_threshold:.4f}")
else:
    n_val = min(len(df_danger_val), len(df_safe_val))
    raw_val_rows = (df_danger_val.sample(n=n_val, random_state=42).to_dict('records') +
                    df_safe_val.sample(n=n_val, random_state=42).to_dict('records'))
 
    val_rows = [row for row in raw_val_rows if row['Context'] in room_graphs_train]
    y_val_true, y_val_scores = compute_anomaly_scores(val_rows)

    def find_optimal_balanced_threshold(y_t, y_s):
        if len(np.unique(y_t)) < 2: 
            return float(np.percentile(y_s, 90))
        fpr, tpr, thresholds = roc_curve(y_t, y_s)
        optimal_idx = np.argmax(tpr - fpr)
        return float(thresholds[optimal_idx])

    global_threshold = find_optimal_balanced_threshold(y_val_true, y_val_scores)
    print(f"\n Optimized Global Threshold (Youden's J): {global_threshold:.4f}")
    torch.save({
        'model_state_dict': model.state_dict(),
        'global_threshold': float(global_threshold),
        'node_in_dim': NODE_IN_DIM,
        'edge_out_dim': EDGE_OUT_DIM,
        'n_labeled_rows': len(df_labeled),
    }, CKPT_PATH)
    print(f"[checkpoint] Saved model + threshold to {CKPT_PATH}")

context_thresholds = {ctx: global_threshold for ctx in list(room_graphs_train.keys())}

if _ckpt is None:  # skipped on checkpoint load (needs test-set scoring)
    n_test = min(len(df_danger_test), len(df_safe_test))
    raw_test_rows = (df_danger_test.sample(n=n_test, random_state=99).to_dict('records') +
                     df_safe_test.sample(n=n_test, random_state=99).to_dict('records'))
    test_rows = [row for row in raw_test_rows if row['Context'] in room_graphs_train]
    y_test_true, y_test_scores = compute_anomaly_scores(test_rows)
 
    y_pred = (y_test_scores > global_threshold).astype(int)
 
    print(f"\n Final Metrics:")
    print(f" Global AUC  : {roc_auc_score(y_test_true, y_test_scores):.4f}")
    print(f" Global F1   : {f1_score(y_test_true, y_pred):.4f}")
    print(classification_report(y_test_true, y_pred, target_names=['Safe (0)', 'Danger (1)']))

    from sklearn.metrics import roc_curve, confusion_matrix, precision_recall_curve, auc
 
    fpr, tpr, _  = roc_curve(y_test_true, y_test_scores)
    roc_auc_val  = auc(fpr, tpr)
    prec, rec, _ = precision_recall_curve(y_test_true, y_test_scores)
    pr_auc_val   = auc(rec, prec)
    cm           = confusion_matrix(y_test_true, y_pred)
 
    fig, axes = plt.subplots(2, 2, figsize=(14, 11))
    fig.suptitle("Final metrics – Anomaly Detection RGAE", fontsize=15, fontweight='bold', y=1.01)
 
    axes[0,0].plot(fpr, tpr, color=ACCENT_COLOR, linewidth=2.5, label=f'ROC (AUC = {roc_auc_val:.3f})')
    axes[0,0].plot([0,1],[0,1], color=GRID_COLOR, linestyle='--', linewidth=1.5, label='Random')
    axes[0,0].fill_between(fpr, tpr, alpha=0.1, color=ACCENT_COLOR)
    axes[0,0].set_title("ROC Curve", fontsize=13, fontweight='bold')
    axes[0,0].set_xlabel("False Positive Rate"); axes[0,0].set_ylabel("True Positive Rate")
    axes[0,0].legend(facecolor=PANEL_COLOR); axes[0,0].grid(alpha=0.4)
 
    axes[0,1].plot(rec, prec, color='#f39c12', linewidth=2.5, label=f'PR (AUC = {pr_auc_val:.3f})')
    axes[0,1].fill_between(rec, prec, alpha=0.1, color='#f39c12')
    axes[0,1].set_title("Precision-Recall Curve", fontsize=13, fontweight='bold')
    axes[0,1].set_xlabel("Recall"); axes[0,1].set_ylabel("Precision")
    axes[0,1].legend(facecolor=PANEL_COLOR); axes[0,1].grid(alpha=0.4)
 
    sns.heatmap(cm, annot=True, fmt='d', ax=axes[1,0],
                cmap='RdYlGn_r', linewidths=2, linecolor=BG_COLOR, cbar=False,
                xticklabels=['Pred Safe','Pred Danger'],
                yticklabels=['True Safe','True Danger'],
                annot_kws={'size': 14, 'fontweight': 'bold'})
    axes[1,0].set_title("Confusion Matrix", fontsize=13, fontweight='bold')
 
    safe_mask   = y_test_true == 0
    danger_mask = y_test_true == 1
    global_thr  = global_threshold  
    axes[1,1].hist(y_test_scores[safe_mask],   bins=40, alpha=0.7,
                   color=SAFE_COLOR,   label='Safe (0)',   edgecolor='none')
    axes[1,1].hist(y_test_scores[danger_mask], bins=40, alpha=0.7,
                   color=DANGER_COLOR, label='Danger (1)', edgecolor='none')
    axes[1,1].axvline(global_thr, color='white', linestyle='--', linewidth=2,
                      label=f'Global threshold ({global_thr:.3f})')
    axes[1,1].set_title("Anomaly Score distribution", fontsize=13, fontweight='bold')
    axes[1,1].set_xlabel("MSE Anomaly Score"); axes[1,1].set_ylabel("Frequency")
    axes[1,1].legend(facecolor=PANEL_COLOR); axes[1,1].grid(alpha=0.4)
 
    plt.tight_layout()
    plt.savefig('viz4_final_metrics.png', dpi=150, bbox_inches='tight', facecolor=BG_COLOR)
    # plt.show() 

    print(f"ROC-AUC: {roc_auc_val:.4f} | PR-AUC: {pr_auc_val:.4f}")
    print(f"TN={cm[0,0]} | FP={cm[0,1]} | FN={cm[1,0]} | TP={cm[1,1]}")

def get_profile_from_db(obj_name, material):
    match_a = df_labeled[(df_labeled['Object_A'] == obj_name) & (df_labeled['Material_A'] == material)]
    if not match_a.empty: return match_a.iloc[0]['Danger_Profile_A']
    
    match_b = df_labeled[(df_labeled['Object_B'] == obj_name) & (df_labeled['Material_B'] == material)]
    if not match_b.empty: return match_b.iloc[0]['Danger_Profile_B']
    
    return get_danger_profile(obj_name, material, 0.01, [])

inference_log = []

@torch.no_grad()
def check_action_rgae(obj_new, material_new, obj_dest, material_dest, interaction, context):
    model.eval()
    if context not in room_graphs_train:
        print(f" Unknown context: '{context}'")
        return 'danger'
        
    danger_a = get_profile_from_db(obj_new, material_new)
    danger_b = get_profile_from_db(obj_dest, material_dest)
    
    mock_row = {
        'Object_A': obj_new, 'Material_A': material_new, 'Danger_Profile_A': danger_a,
        'Object_B': obj_dest, 'Material_B': material_dest, 'Danger_Profile_B': danger_b,
        'Interaction': interaction, 'Context': context
    }
    
    mock_row['Edge_Target'] = create_edge_target(danger_a, danger_b, interaction)
    score = get_inductive_score(mock_row)
    
    threshold = global_threshold
    warning_margin = threshold * 0.20  
    safe_threshold = threshold - warning_margin
    
    print(f"\n[TIAGo in '{context}'] → {interaction.upper()} {obj_new} con {obj_dest}")
    print(f"   MSE Score: {score:.4f}  |  Danger threshold: {threshold:.4f} (Warning if > {safe_threshold:.4f})")
    
    if score <= safe_threshold:
        is_safe = True
        status = 'safe'
        status_color = "✅"
        print(f"   {status_color} Safe action: Robot executes it.")
    elif score <= threshold:
        is_safe = False # Mettiamo False prudenzialmente finché l'umano non approva
        status = 'warning'
        status_color = "⚠️"
        print(f"   {status_color}The action is atypical. The robot requires human authorization.")
    else:
        is_safe = False
        status = 'danger'
        status_color = "❌"
        print(f"   {status_color} CRITICAL ALARM: Action automatically blocked for safety.")
        
    log_label = f"{obj_new}\n{interaction}\n{obj_dest}"
    inference_log.append({
        'label': log_label,
        'context': context, 'score': score,
        'threshold': threshold, 'safe': is_safe,
    })

    return status

print("\n TEST safe actions")
check_action_rgae("book",    "paper",   "desk",            "wood",    "placed_on_top", "home_office")
check_action_rgae("apple",   "food",    "fridge",          "metal",   "placed_inside", "kitchen")
check_action_rgae("soap",    "plastic", "sink",            "ceramic", "placed_near",   "bathroom")
check_action_rgae("clothes", "fabric",  "washing_machine", "metal",   "placed_inside", "bathroom")
check_action_rgae("cup",     "ceramic", "dining_table",    "wood",    "placed_on_top", "dining_room")

print("\n TEST dangerous actions")
check_action_rgae("hair_dryer", "plastic", "bathtub",      "ceramic", "placed_inside", "bathroom")
check_action_rgae("newspaper",  "paper",   "stove",        "metal",   "placed_on_top", "kitchen")
check_action_rgae("television", "metal",   "mirror",       "glass",   "placed_on_top", "living_room")
check_action_rgae("shoes",      "leather", "oven",         "metal",   "placed_inside", "kitchen")
check_action_rgae("bleach",     "plastic", "refrigerator", "metal",   "placed_inside", "kitchen")
check_action_rgae("knife",      "metal",   "play_mat",     "fabric",  "placed_on_top", "playroom")

print("\n EDGE CASES HRI")
check_action_rgae("towel", "fabric", "oven", "metal", "placed_inside", "kitchen")
check_action_rgae("dumbbells", "metal", "glass_table", "glass", "placed_on_top", "living_room")
check_action_rgae("toilet_paper", "paper", "refrigerator", "metal", "placed_inside", "kitchen")
check_action_rgae("toaster", "metal", "sink", "ceramic", "placed_near", "kitchen")
check_action_rgae("scissors", "metal", "bed", "fabric", "placed_on_top", "bedroom")

labels   = [f"{r['label']}\n({r['context']})" for r in inference_log]
scores   = [r['score']     for r in inference_log]
threshs  = [r['threshold'] for r in inference_log]
is_safe  = [r['safe']      for r in inference_log]

bar_cols = []
warning_threshold = global_threshold * 0.80  

for r in inference_log:
    score = r['score']
    if score <= warning_threshold:
        bar_cols.append(SAFE_COLOR)   
    elif score <= global_threshold:
        bar_cols.append("#f1c40f")    
    else:
        bar_cols.append(DANGER_COLOR)  

fig, ax = plt.subplots(figsize=(16, 7))
fig.patch.set_facecolor(BG_COLOR)
ax.set_facecolor(PANEL_COLOR)

x    = np.arange(len(labels))
bars = ax.bar(x, scores, color=bar_cols, edgecolor=BG_COLOR, linewidth=1.5, width=0.55, zorder=3)
for i, t in enumerate(threshs):
    ax.hlines(t, i - 0.3, i + 0.3, colors='white', linewidths=2.5, zorder=4)
    ax.hlines(t - (t * 0.2), i - 0.3, i + 0.3, colors='#f1c40f', linestyle='--', linewidth=1.5, zorder=4)

for i, (b, s) in enumerate(zip(bars, scores)):
    ax.text(b.get_x() + b.get_width()/2, b.get_height() + 0.008,
            f'{s:.3f}', ha='center', va='bottom', fontsize=9,
            fontweight='bold', color=TEXT_COLOR)

ax.set_xticks(x)
ax.set_xticklabels(labels, fontsize=8.5, rotation=20, ha='right')
ax.set_ylabel("MSE Anomaly Score", fontsize=12)
ax.set_title("TIAGo Inference – Anomaly Score vs Threshols for action",
             fontsize=14, fontweight='bold')
ax.grid(axis='y', alpha=0.4, zorder=0)
ax.set_ylim(0, max(scores) * 1.2)

safe_p   = mpatches.Patch(color=SAFE_COLOR,   label='✅ Azione SICURA')
danger_p = mpatches.Patch(color=DANGER_COLOR, label='❌ ALLARME')
thresh_l = plt.Line2D([0],[0], color='white', linewidth=2.5, label='— Soglia per contesto')
ax.legend(handles=[safe_p, danger_p, thresh_l],
          facecolor=PANEL_COLOR, loc='upper left', fontsize=10)

plt.tight_layout()
plt.savefig('viz5_inference_dashboard.png', dpi=150, bbox_inches='tight', facecolor=BG_COLOR)
# plt.show() ì

n_safe   = sum(is_safe)
n_danger = len(is_safe) - n_safe
print(f"\n Inference Results: {n_safe} SAFE ✅  |  {n_danger} DANGER ❌")

import matplotlib.pyplot as plt
import seaborn as sns
import numpy as np
import pandas as pd
from sklearn.manifold import TSNE
import warnings
warnings.filterwarnings('ignore')

if _ckpt is None:  # skipped on checkpoint load (needs test-set scoring)
    print("Extra Analytics")

    warning_threshold = global_threshold * 0.80

    safe_count = np.sum(y_test_scores <= warning_threshold)
    warning_count = np.sum((y_test_scores > warning_threshold) & (y_test_scores <= global_threshold))
    danger_count = np.sum(y_test_scores > global_threshold)

    feature_names = ['Elettrico', 'Infiammabile', 'Tagliente', 'Tossico', 'Acqua-Sens', 'Pesante', 'Cibo', 'Calore', 'Fragile']
    data_rows = []

    for row, score in zip(test_rows, y_test_scores):
        combined_danger = np.array(row['Danger_Profile_A']) + np.array(row['Danger_Profile_B'])
        combined_danger = np.clip(combined_danger, 0, 1) # Manteniamo formato binario 0/1
    
        row_dict = {feat: val for feat, val in zip(feature_names, combined_danger)}
        row_dict['Anomaly_Score'] = score
        data_rows.append(row_dict)
    
    df_explain = pd.DataFrame(data_rows)


    fig, axes = plt.subplots(1, 3, figsize=(22, 6))
    fig.suptitle("Analysis: HRI Autonomy, Explainability and Latent space", fontsize=16, fontweight='bold', color=TEXT_COLOR, y=1.05)
    fig.patch.set_facecolor(BG_COLOR)

    labels_pie = ['Autonomous (Safe)', 'Human-in-the-Loop\n(Warning)', 'Block (Danger)']
    sizes = [safe_count, warning_count, danger_count]
    colors_pie = [SAFE_COLOR, '#f1c40f', DANGER_COLOR]

    axes[0].set_facecolor(PANEL_COLOR)
    axes[0].pie(sizes, labels=labels_pie, colors=colors_pie, autopct='%1.1f%%', startangle=140,
                wedgeprops=dict(edgecolor=BG_COLOR, linewidth=2),
                textprops={'color': TEXT_COLOR, 'fontsize': 11, 'fontweight': 'bold'})
    axes[0].set_title("Robot Autonomy Rate\n(Distribution on the Test Set)", fontsize=14, color=TEXT_COLOR, fontweight='bold')


    corr_matrix = df_explain.corr()
    score_corr = corr_matrix[['Anomaly_Score']].drop('Anomaly_Score').sort_values(by='Anomaly_Score', ascending=False)

    sns.heatmap(score_corr, annot=True, cmap='RdYlGn_r', fmt=".2f", ax=axes[1],
                linewidths=1.5, linecolor=BG_COLOR, cbar_kws={'label': 'Pearson Correlation'},
                annot_kws={'size': 11, 'fontweight': 'bold'})
    axes[1].set_title("Explainability: What physical traits trigger the GAE alarm?", fontsize=14, color=TEXT_COLOR, fontweight='bold')
    axes[1].set_ylabel("")
    axes[1].tick_params(colors=TEXT_COLOR)

    axes[2].set_facecolor(PANEL_COLOR)
    X_phys = df_explain[feature_names].values
    X_phys_noisy = X_phys + np.random.normal(0, 0.01, X_phys.shape)

    tsne = TSNE(n_components=2, random_state=42, perplexity=30)
    X_tsne = tsne.fit_transform(X_phys_noisy)

    scatter = axes[2].scatter(X_tsne[:, 0], X_tsne[:, 1], c=df_explain['Anomaly_Score'], 
                              cmap='inferno', alpha=0.8, edgecolors='w', linewidth=0.5, s=60)
    cbar = plt.colorbar(scatter, ax=axes[2])
    cbar.set_label('MSE Anomaly Score', color=TEXT_COLOR)
    cbar.ax.yaxis.set_tick_params(color=TEXT_COLOR)
    plt.setp(plt.getp(cbar.ax.axes, 'yticklabels'), color=TEXT_COLOR)

    axes[2].set_title("t-SNE: Physical Clustering \n(", fontsize=14, color=TEXT_COLOR, fontweight='bold')
    axes[2].grid(alpha=0.3, color=GRID_COLOR)
    axes[2].tick_params(colors=TEXT_COLOR)

    plt.tight_layout()
    plt.savefig('viz6_extra_analytics.png', dpi=150, bbox_inches='tight', facecolor=BG_COLOR)
    # plt.show() 

    print(" Plots saved as 'viz6_extra_analytics.png'!")
