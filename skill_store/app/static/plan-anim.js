"use strict";
/* ------------------------------------------------------------------ *
 * ANIMATION: the compiled plan played by two grey robot arms.
 * The plan becomes a scene-kit recipe by a fixed table, with no model call:
 * each step maps to one motion by its skill, hand and target, and every
 * step in the same graph layer starts at the same moment, so whatever the
 * scheduler runs in parallel is seen running in parallel. A gap (a skill that
 * does not exist yet) gets its own slot and plays as a pause.
 * Loaded after app.js; uses its globals (plan, viewMode, $, el).
 * ------------------------------------------------------------------ */

// Catalog skill -> scene-kit motion. Anything else plays as a placeholder.
const ANIM_KIND = {
  locate_object: "locate",
  grasp_object: "grasp", grasp_bottle: "grasp", grasp_bottle_lite: "grasp",
  grasp_glass: "grasp", grasp_cloth: "grasp", grasp_scoop: "grasp", grasp_shaker: "grasp",
  move_to_station: "move",
  place_on_coaster: "place", place_in_bin: "place", return_to_shelf: "place",
  place_in_fridge: "place", load_tray: "place", stack_glasses: "place", set_place: "place",
  pour_into: "pour", measure_pour: "pour", top_up: "pour", scoop_pour: "pour",
  release_object: "release",
  stir: "stir",
  shake_shaker: "shake", swirl_glass: "shake",
  run_blender: "blend",
  fold_towel: "fold",
  wipe_surface: "wipe", wipe_spill: "wipe", wipe_window: "wipe", wipe_handle: "wipe",
  sweep_crumbs: "wipe",
};
// A missing skill plays the motion its name implies, washed out, so the rest of
// the chain still makes sense. No match: a plain pause.
const GAP_KIND = [[/pour/, "pour"], [/blend/, "blend"], [/stir|mix/, "stir"],
  [/wipe|drag_over|scrub|clean|sweep/, "wipe"], [/shake/, "shake"], [/fold/, "fold"],
  [/place|put|stack|insert|load|set_down|drop/, "place"], [/grasp|pick|grab/, "grasp"],
  [/release|let_go/, "release"]];
// Seconds per motion; a time slot lasts as long as its slowest step.
const ANIM_DUR = { locate: 1.0, grasp: 1.1, move: 1.4, place: 2.2, pour: 2.6, release: 1.0,
                   stir: 3.0, shake: 2.4, blend: 3.2, wipe: 3.2, fold: 2.2, unknown: 1.2, gap: 1.6 };
const ANIM_LEAD = 0.6;
const THREE_URL = "https://cdnjs.cloudflare.com/ajax/libs/three.js/r128/three.min.js";
const KIT_URL = "/static/scene-kit.js";

function planToRecipe(p) {
  const steps = (p && p.steps) || [];
  const graph = (p && p.graph) || [];
  const layerOf = new Map(graph.map((n) => [n.index, n.layer]));
  const slotOf = (i) => (layerOf.has(i) ? layerOf.get(i) : i);

  // A locate with no target is looking for whatever that hand grabs next.
  const targetOf = (i) => {
    const t = steps[i].params && steps[i].params.target;
    if (t || ANIM_KIND[steps[i].skill_id] !== "locate") return t || "";
    const next = steps.slice(i + 1).find((x) => x.hand === steps[i].hand && x.params && x.params.target);
    return next ? next.params.target : "";
  };
  const items = steps.map((s, i) => {
    const kind = ANIM_KIND[s.skill_id] || "unknown";
    return {
      key: slotOf(i),
      action: {
        kind, step: i, dur: ANIM_DUR[kind],
        hand: s.hands_required === 0 ? null : (s.hand || "right"),
        target: targetOf(i),
        label: s.name || s.skill_id,
      },
    };
  });
  // A gap waits for the step it follows; two gaps after one step take turns.
  (p && p.missing || []).forEach((m, g) => {
    const after = m.insert_after == null ? -1 : m.insert_after;
    const hit = GAP_KIND.find(([re]) => re.test(m.proposed_id || ""));
    const kind = hit ? hit[1] : "gap";
    const near = [steps[after], steps[after + 1]].find((x) => x && x.params && x.params.target);
    items.push({
      key: (after < 0 ? -1 : slotOf(after)) + 0.5 + g * 0.001,
      action: { kind, gap: true, step: "gap" + g, dur: ANIM_DUR[kind], hand: m.hand || null,
                target: near ? near.params.target : "", label: m.name || m.proposed_id },
    });
  });

  const keys = [...new Set(items.map((x) => x.key))].sort((a, b) => a - b);
  const slots = [];
  let t = ANIM_LEAD;
  keys.forEach((k) => {
    const inSlot = items.filter((x) => x.key === k);
    const len = Math.max(...inSlot.map((x) => x.action.dur));
    inSlot.forEach((x) => { x.action.t0 = t; });
    slots.push({ t0: t, t1: t + len, n: inSlot.length });
    t += len;
  });
  const actions = items.map((x) => x.action);

  // Time with both arms moving at once, for the stats line.
  let both = 0;
  slots.forEach((sl) => {
    const live = actions.filter((a) => a.t0 === sl.t0);
    const L = live.filter((a) => a.hand === "left").map((a) => a.dur);
    const R = live.filter((a) => a.hand === "right").map((a) => a.dur);
    if (L.length && R.length) both += Math.min(Math.max(...L), Math.max(...R));
  });
  return { actions, slots, end: t, both };
}

/* ---------------- lazy three.js ---------------- */
let kitReady = null;
function loadScript(src) {
  return new Promise((ok, fail) => {
    const s = document.createElement("script");
    s.src = src; s.onload = ok;
    s.onerror = () => fail(new Error("could not load " + src));
    document.head.appendChild(s);
  });
}
function loadKit() {
  if (!kitReady) {
    kitReady = (window.THREE ? Promise.resolve() : loadScript(THREE_URL))
      .then(() => (window.POVScene ? null : loadScript(KIT_URL)));
  }
  return kitReady;
}

/* ---------------- the view ---------------- */
let anim = null;            // { scene, recipe, sig }
let animDragging = false;
const animWas = new Map();  // plan_id -> last length in seconds, to show a re-balance

function disposeAnim() {
  if (anim && anim.scene) anim.scene.dispose();
  anim = null;
  document.querySelectorAll(".row.anim-on").forEach((r) => r.classList.remove("anim-on"));
}

async function renderAnim() {
  const box = $("#anim");
  if (viewMode !== "anim") { disposeAnim(); return; }
  const recipe = planToRecipe(plan);
  const sig = JSON.stringify(recipe.actions);
  if (anim && anim.sig === sig) return;
  disposeAnim();

  const stage = $("#animstage");
  stage.textContent = "";
  $("#animlanes").textContent = "";
  $("#animnow").textContent = "";
  $("#animstats").textContent = "";
  box.classList.toggle("empty-anim", !recipe.actions.length);
  if (!recipe.actions.length) {
    stage.appendChild(el("div", "empty", "Compile a process to see it played."));
    return;
  }
  const mine = { sig, recipe, scene: null };
  anim = mine;
  try { await loadKit(); }
  catch (e) { stage.appendChild(el("div", "empty", "The animation needs three.js: " + e.message)); return; }
  if (anim !== mine) return;          // a newer plan arrived while loading

  const canvas = el("canvas");
  stage.appendChild(canvas);
  drawLanes(recipe);
  drawAnimStats(recipe);
  const scrub = $("#animscrub");
  mine.scene = POVScene.create({
    canvas, style: "plain", fit: "parent", plan: { actions: recipe.actions },
    camera: { pos: [0, 1.0, 1.0], look: [0, 0.08, -0.17], fov: 30 },
    lead: 0, tail: 1.6,
    onError: () => stage.appendChild(el("div", "empty", "This view needs WebGL.")),
    onFrame: (s) => animFrame(mine, s),
  });
  if (!mine.scene) return;
  scrub.max = mine.scene.duration.toFixed(2);
  setAnimPlaying(true);
}

function drawLanes(recipe) {
  const lanes = $("#animlanes");
  const end = recipe.end + 1.6;
  const rows = [["left", "L"], ["right", "R"]];
  if (recipe.actions.some((a) => !a.hand)) rows.push([null, "—"]);
  rows.forEach(([hand, label]) => {
    const lane = el("div", "alane " + (hand || "none"));
    lane.appendChild(el("span", "alane-k", label));
    const track = el("div", "alane-t");
    recipe.actions.filter((a) => a.hand === hand)
      .forEach((a) => {
        const b = el("i", "ablk " + (a.gap ? "gap" : a.kind === "unknown" ? "unk" : ""));
        b.style.left = (a.t0 / end * 100) + "%";
        b.style.width = (a.dur / end * 100) + "%";
        b.dataset.step = String(a.step);
        b.title = `${typeof a.step === "number" ? "Step " + (a.step + 1) : "Missing"}: ` +
                  a.label + (a.target ? " → " + a.target : "");
        track.appendChild(b);
      });
    lane.appendChild(track);
    lanes.appendChild(lane);
  });
  const head = el("div", "aplayhead");
  head.id = "animhead";
  lanes.appendChild(head);
}

function drawAnimStats(recipe) {
  const stats = $("#animstats");
  const n = recipe.actions.filter((a) => !a.gap).length;
  const secs = recipe.end + 1.6;
  const add = (label, value, cls) => {
    const d = el("div");
    d.appendChild(el("b", cls, value));
    d.appendChild(document.createTextNode(" " + label));
    stats.appendChild(d);
  };
  add("steps", String(n));
  add("time slots", String(recipe.slots.length));
  add("seconds", secs.toFixed(1));
  add("of it with both hands moving", Math.round(recipe.both / recipe.end * 100) + "%",
      recipe.both > 0 ? "win" : null);
  const id = plan && plan.plan_id;
  const was = animWas.get(id);
  if (was && Math.abs(was - secs) > 0.05) {
    add(`was ${was.toFixed(1)} s before this hand assignment`, (secs < was ? "−" : "+") +
        Math.abs(was - secs).toFixed(1) + " s", secs < was ? "win" : null);
  }
  animWas.set(id, secs);
}

let animLastKey = "";
function animFrame(mine, s) {
  if (anim !== mine) return;
  if (!animDragging) $("#animscrub").value = s.t.toFixed(2);
  const end = mine.recipe.end + 1.6;
  const head = $("#animhead");
  if (head) head.style.left = `calc(28px + (100% - 28px) * ${s.t / end})`;
  $("#anim").classList.toggle("in-gap", !!s.gap);
  $("#animtime").textContent = `${s.t.toFixed(1)} / ${s.duration.toFixed(1)} s`;

  const key = s.active.join(",");
  if (key === animLastKey) return;
  animLastKey = key;
  const on = new Set(s.active.map(String));
  document.querySelectorAll(".ablk").forEach((b) => {
    const a = mine.recipe.actions.find((x) => String(x.step) === b.dataset.step);
    b.classList.toggle("on", on.has(b.dataset.step));
    b.classList.toggle("done", !!a && a.t0 + a.dur <= s.t && !on.has(b.dataset.step));
  });
  document.querySelectorAll("#seq .row").forEach((r) => {
    const id = r.dataset.gap != null ? "gap" + r.dataset.gap : r.dataset.index;
    r.classList.toggle("anim-on", on.has(id));
  });
  const now = $("#animnow");
  now.textContent = "";
  mine.recipe.actions.filter((a) => on.has(String(a.step))).forEach((a) => {
    const d = el("span", "anow " + (a.gap ? "gap" : a.hand || "none"));
    d.appendChild(el("b", null, a.gap ? "MISSING" : a.hand ? a.hand[0].toUpperCase() : "—"));
    d.appendChild(document.createTextNode(" " + a.label + (a.target ? " → " + a.target : "")));
    now.appendChild(d);
  });
}

function setAnimPlaying(on) {
  if (!anim || !anim.scene) return;
  if (on) anim.scene.play(); else anim.scene.pause();
  const b = $("#animplay");
  b.innerHTML = on ? "&#10074;&#10074;" : "&#9654;";
  b.setAttribute("aria-label", on ? "Pause" : "Play");
}
$("#animplay").addEventListener("click", () => {
  if (anim && anim.scene) setAnimPlaying(!anim.scene.isPlaying());
});
$("#animscrub").addEventListener("pointerdown", () => {
  animDragging = true;
  if (anim && anim.scene) anim.scene.hold(true);
});
window.addEventListener("pointerup", () => {
  if (!animDragging) return;
  animDragging = false;
  if (anim && anim.scene) anim.scene.hold(false);
});
$("#animscrub").addEventListener("input", () => {
  if (anim && anim.scene) anim.scene.seek(parseFloat($("#animscrub").value));
});
// Click a block in the lanes to jump to that step.
$("#animlanes").addEventListener("click", (e) => {
  const b = e.target.closest(".ablk");
  if (!b || !anim || !anim.scene) return;
  const a = anim.recipe.actions.find((x) => String(x.step) === b.dataset.step);
  if (a) anim.scene.seek(a.t0 + 0.01);
});
