#!/usr/bin/env python3
"""Generate data/seed_skills.json from the compact table below.

Edit SKILLS, re-run, restart the API. Columns:
  id, name, category, status, price_eur, vendor, preconditions, adds, deletes, description

status: 'trained' = real checkpoint, executable on hardware
        'beta'    = checkpoint exists, success rate not yet established
        'catalog' = listed but not trained -- requesting it creates demand signal
"""
import json
from pathlib import Path

DAIDAI, SPIRIT, COMMUNITY, ROBORECS = "Daidai Labs", "Spirit AI", "OpenGrasp (community)", "Roborecs"

# Checkpoints: a "skill" is a (checkpoint, prompt) pair. Several skills share one
# fine-tuned pi0.5 checkpoint and differ only by the language prompt.
BARTENDER_CKPT = "checkpoints/pi05_moz_bartender/30000"
WIPE_CKPT = "checkpoints/pi05_moz_wipe/30000"

# Everything a hand can be carrying. Letting go clears all of it.
RELEASES = ["bottle_grasped", "glass_grasped", "shaker_grasped", "scoop_grasped",
            "cloth_grasped", "object_grasped", "holding", "positioned"]

# id, name, category, status, price, vendor, pre, adds, deletes, desc, prompt, ckpt
SKILLS = [
    # --- perception -------------------------------------------------------
    # locate_object is a policy rollout that moves an arm, and the pose it finds is
    # consumed by that arm's grasp, so object_located is per hand (validator.py).
    ("locate_object", "Locate Object", "perception", "trained", 4.0, DAIDAI,
     ["hand_empty"], ["object_located"], [],
     "Sweep the wrist camera over the work surface to find a named object and its "
     "pose, with the arm that will grasp it.",
     "find the {target} on the table", BARTENDER_CKPT),
    ("detect_fill_level", "Detect Fill Level", "perception", "beta", 6.0, DAIDAI,
     [], ["fill_known"], [],
     "Estimate how full a transparent vessel is, from the wrist camera.", None, None),
    ("verify_surface_clean", "Verify Surface Clean", "perception", "trained", 5.0, DAIDAI,
     [], ["surface_verified"], [],
     "Score a surface for residue from the head camera. Used as a success detector.",
     None, None),
    ("read_label", "Read Label", "perception", "catalog", 7.0, ROBORECS,
     [], ["label_read"], [], "Read a printed bottle or package label.", None, None),
    ("detect_spill", "Detect Spill", "perception", "catalog", 5.0, DAIDAI,
     [], ["spill_located"], [], "Spot liquid or granular spill on a surface.", None, None),

    # --- grasping ---------------------------------------------------------
    ("grasp_bottle", "Grasp Bottle", "manipulation", "trained", 12.0, DAIDAI,
     ["object_located", "hand_empty"], ["bottle_grasped", "holding"],
     ["hand_empty", "object_located"],
     "Close the gripper around an upright bottle and secure it.",
     "pick up the {target} bottle", BARTENDER_CKPT),
    ("grasp_bottle_lite", "Grasp Bottle (Lite)", "manipulation", "beta", 3.0, COMMUNITY,
     ["object_located", "hand_empty"], ["bottle_grasped", "holding"],
     ["hand_empty", "object_located"],
     "Budget bottle grasp. Same interface, lower success rate, no wrist-camera servoing.",
     "pick up the {target} bottle", BARTENDER_CKPT),
    ("grasp_glass", "Grasp Glass", "manipulation", "trained", 12.0, DAIDAI,
     ["object_located", "hand_empty"], ["glass_grasped", "holding"],
     ["hand_empty", "object_located"],
     "Grasp a stemless glass without tipping it.",
     "pick up the glass", BARTENDER_CKPT),
    ("grasp_scoop", "Grasp Scoop", "manipulation", "catalog", 9.0, DAIDAI,
     ["object_located", "hand_empty"], ["scoop_grasped", "holding"],
     ["hand_empty", "object_located"],
     "Pick up a measuring scoop by the handle.", None, None),
    ("grasp_shaker", "Grasp Shaker", "manipulation", "catalog", 14.0, DAIDAI,
     ["object_located", "hand_empty"], ["shaker_grasped", "holding"],
     ["hand_empty", "object_located"],
     "Grasp a cocktail shaker around its body.", None, None),
    ("grasp_object", "Grasp Object", "manipulation", "beta", 10.0, DAIDAI,
     ["object_located", "hand_empty"], ["object_grasped", "holding"],
     ["hand_empty", "object_located"],
     "Pick up a rigid, hand-sized loose item by its body or handle -- fruit, a lid, "
     "a utensil, a brush, a bucket, a box.",
     "pick up the {target}", BARTENDER_CKPT),
    ("grasp_cloth", "Grasp Cloth", "manipulation", "trained", 10.0, DAIDAI,
     ["object_located", "hand_empty"], ["cloth_grasped", "holding"],
     ["hand_empty", "object_located"],
     "Pick up a folded cloth or sponge from a flat surface.",
     "pick up the cloth", WIPE_CKPT),
    ("release_object", "Release Object", "manipulation", "trained", 2.0, DAIDAI,
     ["holding", "positioned"], ["hand_empty"], RELEASES,
     "Open the gripper wherever the held object was moved to, and retract. Over a "
     "vessel this drops the object in; over the table it sets it down.",
     "let go of the object", BARTENDER_CKPT),
    ("handover", "Bimanual Handover", "manipulation", "catalog", 24.0, SPIRIT,
     ["bottle_grasped"], ["handover_done"], [],
     "Pass a held object from one arm to the other. Requires dual-arm structure.", None, None),
    ("twist_cap", "Twist Cap", "manipulation", "catalog", 18.0, DAIDAI,
     ["bottle_grasped"], ["cap_removed"], [],
     "Unscrew and remove a bottle cap while the bottle is held.", None, None),
    ("press_dispenser", "Press Dispenser", "manipulation", "catalog", 8.0, COMMUNITY,
     ["hand_empty"], ["dispensed"], [], "Press down on a pump dispenser.", None, None),
    ("open_drawer", "Open Drawer", "manipulation", "catalog", 16.0, SPIRIT,
     ["hand_empty"], ["drawer_open"], [], "Hook a drawer handle and pull it open.", None, None),
    ("close_drawer", "Close Drawer", "manipulation", "catalog", 14.0, SPIRIT,
     ["drawer_open"], [], ["drawer_open"], "Push a drawer closed.", None, None),

    # --- transport --------------------------------------------------------
    # A held object goes somewhere before it is let go or poured: move, then act.
    ("move_to_station", "Move To Location", "transport", "trained", 6.0, DAIDAI,
     ["holding"], ["positioned"], [],
     "Carry the held object to a named place and hold it there -- over a vessel, "
     "above a glass, back onto the table.",
     "move it over the {target}", BARTENDER_CKPT),
    ("place_on_coaster", "Place On Coaster", "transport", "trained", 10.0, DAIDAI,
     ["glass_grasped"], ["hand_empty", "glass_placed"], RELEASES,
     "Set a held glass down on the coaster, upright and centred.",
     "put the glass down on the coaster", BARTENDER_CKPT),
    ("place_in_bin", "Place In Bin", "transport", "beta", 8.0, DAIDAI,
     ["holding"], ["hand_empty", "in_bin"], RELEASES,
     "Drop a held object into a bin.", "put it in the bin", BARTENDER_CKPT),
    ("return_to_shelf", "Return To Shelf", "transport", "catalog", 11.0, DAIDAI,
     ["bottle_grasped"], ["hand_empty", "on_shelf"], RELEASES,
     "Return a bottle to its slot on the shelf.", None, None),
    ("load_tray", "Load Tray", "transport", "catalog", 15.0, ROBORECS,
     [], ["on_tray"], [], "Place an object onto a serving tray.", None, None),

    # --- pouring ----------------------------------------------------------
    ("pour_into", "Pour Into", "pouring", "trained", 20.0, DAIDAI,
     ["holding", "positioned", "glass_placed"], ["vessel_filled"], ["positioned"],
     "Tilt the held bottle or vessel, already moved over the target, pour a target "
     "amount and come back upright.",
     "pour from the bottle into the glass", BARTENDER_CKPT),
    ("measure_pour", "Measured Pour", "pouring", "catalog", 26.0, DAIDAI,
     ["holding", "positioned", "glass_placed"], ["vessel_filled", "measured"],
     ["positioned"],
     "Pour a specified volume using closed-loop fill-level feedback.", None, None),
    ("scoop_pour", "Scoop And Pour", "pouring", "catalog", 17.0, DAIDAI,
     ["scoop_grasped", "positioned"], ["vessel_filled"], ["positioned"],
     "Empty a filled scoop into the vessel it was moved over.", None, None),
    ("top_up", "Top Up", "pouring", "catalog", 12.0, COMMUNITY,
     ["holding", "positioned", "fill_known"], ["vessel_filled"], [],
     "Add liquid until a target fill level is reached.", None, None),

    # --- mixing -----------------------------------------------------------
    ("stir", "Stir", "mixing", "trained", 14.0, DAIDAI,
     ["vessel_filled", "hand_empty"], ["contents_mixed", "vessel_filled"], [],
     "Insert a stirrer and run a circular stirring motion in the glass.",
     "stir the drink in the glass", BARTENDER_CKPT),
    ("shake_shaker", "Shake Shaker", "mixing", "catalog", 22.0, DAIDAI,
     ["shaker_grasped", "shaker_closed", "vessel_filled"],
     ["contents_mixed", "vessel_filled"], [],
     "Agitate a sealed shaker vertically for a set duration.", None, None),
    ("swirl_glass", "Swirl Glass", "mixing", "catalog", 9.0, COMMUNITY,
     ["glass_grasped"], ["contents_mixed"], [],
     "Rotate a held glass to mix contents without a stirrer.", None, None),
    # Mixing rewrites what is in the vessel, so it re-asserts vessel_filled: that
    # makes the next pour out of it wait for the mix (a resource edge).
    ("run_blender", "Run Blender", "mixing", "catalog", 16.0, DAIDAI,
     ["hand_empty", "vessel_filled"], ["contents_mixed", "vessel_filled"], [],
     "Press and hold a countertop blender's start button until the contents are "
     "smooth.", None, None),
    ("seal_shaker", "Seal Shaker", "mixing", "catalog", 13.0, DAIDAI,
     ["shaker_grasped"], ["shaker_closed"], [], "Press the lid onto a shaker.", None, None),

    # --- wiping / cleaning ------------------------------------------------
    ("wipe_surface", "Wipe Surface", "cleaning", "trained", 16.0, DAIDAI,
     ["cloth_grasped"], ["surface_clean"], [],
     "Run overlapping wiping strokes across a bounded flat area.",
     "wipe the table clean", WIPE_CKPT),
    ("wipe_spill", "Wipe Spill", "cleaning", "beta", 18.0, DAIDAI,
     ["cloth_grasped", "spill_located"], ["surface_clean"], [],
     "Wipe a localised spill, working inward from the edges.",
     "wipe up the spill", WIPE_CKPT),
    ("polish_glass", "Polish Glass", "cleaning", "catalog", 19.0, ROBORECS,
     ["cloth_grasped", "glass_grasped"], ["glass_polished"], [],
     "Rotate a glass against a cloth to remove streaks. Bimanual.", None, None),
    ("rinse_vessel", "Rinse Vessel", "cleaning", "catalog", 21.0, DAIDAI,
     ["glass_grasped"], ["glass_rinsed"], [], "Hold a vessel under a tap and rinse.", None, None),
    ("clear_table", "Clear Table", "cleaning", "catalog", 25.0, ROBORECS,
     [], ["table_clear"], [], "Move every loose object on the table into a bin or tray.",
     None, None),
    ("stack_glasses", "Stack Glasses", "cleaning", "catalog", 20.0, COMMUNITY,
     ["glass_grasped"], ["stacked"], [], "Nest a glass into a stack.", None, None),

    # --- finishing / serving ---------------------------------------------
    ("garnish", "Garnish", "finishing", "catalog", 23.0, DAIDAI,
     ["vessel_filled", "hand_empty"], ["garnish_added"], [],
     "Place a fruit slice or similar garnish on the glass rim.", None, None),
    ("add_straw", "Add Straw", "finishing", "catalog", 11.0, COMMUNITY,
     ["vessel_filled", "hand_empty"], ["straw_added"], [],
     "Drop a straw into a filled glass.", None, None),
    ("add_umbrella", "Add Umbrella", "finishing", "catalog", 10.0, COMMUNITY,
     ["vessel_filled", "hand_empty"], ["umbrella_added"], [],
     "Place a cocktail umbrella in a filled glass.", None, None),
    ("serve_to_guest", "Serve To Guest", "finishing", "catalog", 28.0, SPIRIT,
     ["vessel_filled", "contents_mixed"], ["served"], [],
     "Present the finished drink to a person and wait for them to take it.", None, None),
    ("slide_coaster", "Slide Coaster", "finishing", "catalog", 7.0, DAIDAI,
     ["hand_empty"], ["coaster_ready"], [], "Slide a coaster into position.", None, None),

    # --- household breadth (catalog only) --------------------------------
    ("fold_towel", "Fold Towel", "household", "catalog", 24.0, ROBORECS,
     ["cloth_grasped"], ["folded"], [], "Fold a rectangular towel in halves.", None, None),
    ("sort_cutlery", "Sort Cutlery", "household", "catalog", 27.0, ROBORECS,
     ["hand_empty"], ["sorted"], [], "Sort mixed cutlery into compartments.", None, None),
    ("load_dishwasher", "Load Dishwasher", "household", "catalog", 32.0, ROBORECS,
     ["hand_empty"], ["loaded"], [], "Place crockery into a dishwasher rack.", None, None),
    ("water_plant", "Water Plant", "household", "catalog", 15.0, COMMUNITY,
     ["bottle_grasped"], ["watered"], [], "Pour a measured amount into a plant pot.", None, None),
    ("wipe_window", "Wipe Window", "household", "catalog", 26.0, DAIDAI,
     ["cloth_grasped"], ["window_clean"], [], "Wipe a vertical glass surface.", None, None),
    ("pick_up_floor", "Pick Up From Floor", "household", "catalog", 29.0, SPIRIT,
     ["hand_empty"], ["object_grasped", "holding"], ["hand_empty"],
     "Pick an object off the floor. Requires torso or mobile base.", None, None),
    ("open_fridge", "Open Fridge", "household", "catalog", 30.0, SPIRIT,
     ["hand_empty"], ["fridge_open"], [], "Pull a fridge door open by the handle.", None, None),
    ("place_in_fridge", "Place In Fridge", "household", "catalog", 22.0, SPIRIT,
     ["fridge_open", "bottle_grasped"], ["hand_empty"], RELEASES,
     "Put a held item onto a fridge shelf.", None, None),
    ("sweep_crumbs", "Sweep Crumbs", "household", "catalog", 17.0, DAIDAI,
     ["hand_empty"], ["surface_clean"], [], "Brush crumbs from a surface into a dustpan.",
     None, None),
    ("align_chair", "Align Chair", "household", "catalog", 18.0, SPIRIT,
     ["hand_empty"], ["chair_aligned"], [], "Push a chair flush to the table edge.", None, None),
    ("hang_cloth", "Hang Cloth", "household", "catalog", 13.0, COMMUNITY,
     ["cloth_grasped"], ["hand_empty", "hung"], RELEASES,
     "Drape a cloth over a rail.", None, None),
    ("close_fridge", "Close Fridge", "household", "catalog", 12.0, SPIRIT,
     ["fridge_open"], [], ["fridge_open"], "Push the fridge door shut.", None, None),
    ("wipe_handle", "Wipe Handle", "household", "catalog", 14.0, DAIDAI,
     ["cloth_grasped"], ["handle_clean"], [], "Wipe a cylindrical handle or rail.", None, None),
    ("pour_cereal", "Pour Cereal", "household", "catalog", 19.0, COMMUNITY,
     ["bottle_grasped"], ["bowl_filled"], [], "Pour granular food into a bowl.", None, None),
    ("set_place", "Set A Place", "household", "catalog", 25.0, ROBORECS,
     ["hand_empty"], ["place_set"], [], "Lay out a plate, cutlery and glass for one person.",
     None, None),
    ("collect_bottles", "Collect Bottles", "household", "catalog", 21.0, DAIDAI,
     ["hand_empty"], ["bottles_collected"], [], "Gather loose bottles into a crate.", None, None),
]


# ---------------------------------------------------------------------------
# Provenance: which dataset a skill was trained from, or would be trained from.
# A catalog-only skill still names its candidate source -- that is what turns the
# gap report into a work order ("collect N episodes from this dataset").
# ---------------------------------------------------------------------------
DATASET_BY_CATEGORY = {
    "perception":   "egocentric-10k-subset",
    "manipulation": "svla_so101_pickplace",
    "transport":    "svla_so101_pickplace",
    "pouring":      "egodex",
    "mixing":       "egodex",
    "cleaning":     "egocentric-10k-subset",
    "finishing":    "egodex",
    "household":    "egocentric-10k",
}

# Skills with no candidate dataset at all -- nobody has recorded anything close.
# These are the ones the gap report should push to the top of the collection queue.
NO_DATASET = {
    "handover", "polish_glass", "rinse_vessel", "stack_glasses", "seal_shaker",
    "shake_shaker", "load_dishwasher", "sort_cutlery", "set_place", "align_chair",
    "open_fridge", "close_fridge", "place_in_fridge", "press_dispenser",
    "serve_to_guest", "read_label", "run_blender",
}

# ---------------------------------------------------------------------------
# What a skill can be used on. The compiler classifies every object in a request
# into one of these kinds (it never sees a skill while doing so), and the
# validator rejects a step whose target is a kind the skill does not list -- a
# bottle grasp closing on a bucket. A skill with no entry here takes any target.
# A new kind is a new line in OBJECT_KINDS plus the skills that handle it.
# ---------------------------------------------------------------------------
OBJECT_KINDS = {
    "bottle": "a rigid bottle, carton or jug of liquid, held upright by its body",
    "glass": "a drinking glass, cup, mug or tumbler",
    "shaker": "a cocktail shaker",
    "scoop": "a measuring scoop with a handle",
    "cloth": "something soft and deformable: a cloth, towel, rag, napkin or sponge",
    "item": "any other rigid, hand-sized loose thing: fruit, a lid, a utensil, a "
            "brush, a tool, a bucket, a box, a toy",
    "fixed": "something that is not picked up: the table, a wall, a shelf, a sink, "
             "an appliance, a bin, a plant pot in soil",
    "substance": "a material inside something else, not grasped on its own: paint, "
                 "water, sand, crumbs, a spill",
}

ACTS_ON = {
    "grasp_bottle": ["bottle"], "grasp_bottle_lite": ["bottle"],
    "grasp_glass": ["glass"], "grasp_shaker": ["shaker"], "grasp_scoop": ["scoop"],
    "grasp_cloth": ["cloth"], "grasp_object": ["item"],
    "pick_up_floor": ["bottle", "glass", "cloth", "item"],
}

# Skills that move contents between objects. "held->target": what the hand holds
# empties into the target (a pour); "object->target": the held object itself
# ends up inside the target (fruit dropped into a blender). The validator keeps
# a contents ledger from these, so pouring from an empty glass, or pouring into
# the thing being held, is caught as wrong_flow.
FLOW = {
    "pour_into": "held->target", "measure_pour": "held->target", "top_up": "held->target",
    "scoop_pour": "held->target",
    "release_object": "object->target", "place_in_bin": "object->target",
}

# Episodes actually collected, for skills with a checkpoint. Edit as you record.
EPISODES = {
    "locate_object": 40, "grasp_bottle": 52, "grasp_glass": 44, "grasp_cloth": 38,
    "release_object": 52, "move_to_station": 36, "place_on_coaster": 47,
    "pour_into": 61, "stir": 43, "wipe_surface": 58, "verify_surface_clean": 30,
    "grasp_bottle_lite": 18, "wipe_spill": 22, "place_in_bin": 19,
    "detect_fill_level": 16,
}

# Action title: the phrase a person would say to the robot. Written out for the
# skills that have a policy prompt (the prompt keeps its {target} placeholder for
# runtime substitution); derived from the description for the rest.
TITLES = {
    "locate_object": "find the object on the table",
    "grasp_bottle": "pick up the bottle",
    "grasp_bottle_lite": "pick up the bottle",
    "grasp_glass": "pick up the glass",
    "grasp_cloth": "pick up the cloth",
    "release_object": "let go of it there",
    "grasp_object": "pick up the object",
    "move_to_station": "carry it over to the target",
    "place_on_coaster": "put the glass down on the coaster",
    "place_in_bin": "put it in the bin",
    "pour_into": "pour it into the target",
    "stir": "stir the drink in the glass",
    "wipe_surface": "wipe the table clean",
    "wipe_spill": "wipe up the spill",
    "verify_surface_clean": "check whether the surface is clean",
    "detect_fill_level": "check how full the glass is",
}


def action_title(sid: str, name: str, prompt: str | None, desc: str) -> str:
    if sid in TITLES:
        return TITLES[sid]
    first = desc.split(".")[0].strip()
    return first[0].lower() + first[1:] if first else name.lower()


EMBODIMENT = {
    "structure": "dualarm",
    "gripper": "parallel",
    "cameras": ["head", "left_wrist", "right_wrist"],
    "control_hz": 120,
}

# Skills needing more than two arms' worth of reach get the whole-body structure.
WHOLEBODY = {"pick_up_floor", "open_fridge", "place_in_fridge", "close_fridge",
             "align_chair", "serve_to_guest", "clear_table", "set_place"}


# Other ways people describe each motion. The binder sees these next to the
# description, so "drag the cloth along the table" lands on wipe_surface instead
# of becoming a gap; the Demand page uses them to spot gaps the catalog covers.
ALIASES = {
    "locate_object": ["look for", "find", "search for", "spot"],
    "grasp_bottle": ["pick up the bottle", "take the bottle", "grab the bottle", "lift the bottle",
                     "grasp the bottle", "grasp the can", "grasp the carton"],
    "grasp_bottle_lite": ["pick up the bottle"],
    "grasp_glass": ["pick up the glass", "take the glass", "grab the cup", "lift the glass",
                    "grasp the glass", "grasp the cup", "grasp the mug"],
    "grasp_object": ["pick up", "take", "grab", "lift", "hold"],
    "grasp_cloth": ["pick up the cloth", "take the towel", "grab the sponge", "grab the rag",
                    "grasp the cloth", "grasp the towel"],
    "grasp_scoop": ["pick up the scoop", "take the spoon"],
    "grasp_shaker": ["pick up the shaker", "take the shaker"],
    "release_object": ["let go", "set down", "put down", "drop it in", "place", "leave it", "release"],
    "move_to_station": ["carry", "bring", "move it over", "hold it above", "take it to", "transport"],
    "pour_into": ["pour", "tilt into", "tip into", "empty into", "fill from", "decant"],
    "measure_pour": ["pour a measure", "measured pour", "pour exactly"],
    "scoop_pour": ["scoop into", "spoon into", "ladle into", "add a scoop"],
    "top_up": ["top up", "fill to the line"],
    "stir": ["stir", "mix with a spoon", "swirl the spoon", "agitate", "whisk"],
    "swirl_glass": ["swirl", "swish"],
    "shake_shaker": ["shake", "shake it up"],
    "seal_shaker": ["close the shaker", "cap the shaker", "put the lid on", "seal"],
    "run_blender": ["blend", "turn on the blender", "operate the blender", "press the blender button",
                    "start the blender", "run the mixer", "switch on", "press start"],
    "wipe_surface": ["wipe", "drag the cloth over", "rub the surface", "scrub", "wipe down",
                     "clean the table", "sweep the cloth across", "polish the surface"],
    "wipe_spill": ["wipe up the spill", "mop up", "dab the spill"],
    "wipe_window": ["wipe the window", "clean the glass pane"],
    "wipe_handle": ["wipe the handle", "clean the rail"],
    "verify_surface_clean": ["check it is clean", "inspect the surface"],
    "detect_fill_level": ["check how full", "see the level"],
    "polish_glass": ["polish", "buff the glass", "dry the glass"],
    "rinse_vessel": ["rinse", "wash out", "hold under the tap"],
    "twist_cap": ["unscrew", "twist open", "open the bottle", "remove the cap", "uncap"],
    "press_dispenser": ["press the pump", "push the dispenser", "press down"],
    "open_drawer": ["open the drawer", "pull the drawer"],
    "close_drawer": ["close the drawer", "push the drawer shut"],
    "open_fridge": ["open the fridge", "open the refrigerator", "pull the fridge door"],
    "close_fridge": ["close the fridge", "shut the fridge door"],
    "place_in_fridge": ["put in the fridge", "store in the fridge"],
    "place_on_coaster": ["put the glass on the coaster", "set the glass down"],
    "place_in_bin": ["throw away", "bin it", "drop in the bin", "discard", "put in the trash"],
    "return_to_shelf": ["put the bottle back", "return to the shelf", "put it back on the shelf"],
    "load_tray": ["put on the tray", "load the tray"],
    "garnish": ["add a garnish", "put a slice on the rim", "decorate the drink", "add the cherry"],
    "add_straw": ["add a straw", "put a straw in"],
    "add_umbrella": ["add an umbrella", "put a parasol in"],
    "serve_to_guest": ["serve", "hand to the guest", "give it to the person", "hand me", "pass me",
                       "present the drink", "slide it across"],
    "handover": ["hand over", "pass to the other hand", "switch hands", "transfer between hands"],
    "slide_coaster": ["slide the coaster", "position the coaster"],
    "fold_towel": ["fold", "fold the cloth", "fold the laundry", "fold in half"],
    "hang_cloth": ["hang the cloth", "drape over the rail", "hang up"],
    "sort_cutlery": ["sort the cutlery", "sort the forks and knives"],
    "load_dishwasher": ["load the dishwasher", "put the dishes in the dishwasher"],
    "water_plant": ["water the plant", "pour onto the soil"],
    "pick_up_floor": ["pick up from the floor", "lift off the floor", "reach down"],
    "sweep_crumbs": ["sweep", "brush the crumbs", "sweep into the dustpan"],
    "align_chair": ["push the chair in", "straighten the chair"],
    "pour_cereal": ["pour cereal", "pour into the bowl", "fill the bowl"],
    "set_place": ["set the table", "lay a place setting"],
    "collect_bottles": ["collect the bottles", "gather the bottles", "pick up the empties"],
    "clear_table": ["clear the table", "clear away", "tidy the table"],
    "stack_glasses": ["stack", "nest the glasses", "pile the cups"],
}


def build() -> list[dict]:
    out = []
    for (sid, name, cat, status, price, vendor, pre, adds, dels, desc,
         prompt, ckpt) in SKILLS:
        emb = dict(EMBODIMENT)
        if sid in WHOLEBODY:
            emb["structure"] = "wholebody_without_base"
        ds_id = None if sid in NO_DATASET else DATASET_BY_CATEGORY.get(cat)
        n_eps = EPISODES.get(sid, 0)
        out.append({
            "id": sid,
            "name": name,
            "title": action_title(sid, name, prompt, desc),
            "thumbnail": f"thumbs/{sid}.jpg",
            "dataset": {
                "id": ds_id,
                "episodes": n_eps,
                "status": "trained_on" if (ckpt and n_eps) else "candidate",
            },
            "category": cat,
            "status": status,
            "price_eur": price,
            "vendor": vendor,
            "description": desc,
            "preconditions": pre,
            "postconditions": adds,
            "deletes": dels,
            "embodiment": emb,
            "acts_on": ACTS_ON.get(sid, []),
            "aliases": ALIASES.get(sid, []),
            "flow": FLOW.get(sid),
            "checkpoint": ckpt,
            "prompt": prompt,
            "est_duration_s": 6.0 if cat == "perception" else 12.0,
        })
    return out


if __name__ == "__main__":
    skills = build()
    ids = [s["id"] for s in skills]
    assert len(ids) == len(set(ids)), "duplicate skill id"
    unknown = set(ALIASES) - set(ids)
    assert not unknown, f"aliases for unknown skills: {sorted(unknown)}"
    dest = Path(__file__).resolve().parent.parent / "data" / "seed_skills.json"
    dest.write_text(json.dumps(skills, indent=2) + "\n")
    unknown = {k for kinds in ACTS_ON.values() for k in kinds} - set(OBJECT_KINDS)
    assert not unknown, f"ACTS_ON names undeclared kinds: {unknown}"
    (dest.parent / "object_kinds.json").write_text(json.dumps(OBJECT_KINDS, indent=2) + "\n")
    trained = sum(1 for s in skills if s["status"] == "trained")
    beta = sum(1 for s in skills if s["status"] == "beta")
    print(f"{len(skills)} skills -> {dest}")
    print(f"  trained={trained}  beta={beta}  catalog={len(skills)-trained-beta}")
    with_eps = sum(1 for s in skills if s["dataset"]["episodes"])
    print(f"  with collected episodes: {with_eps}  "
          f"(total {sum(s['dataset']['episodes'] for s in skills)} episodes)")
