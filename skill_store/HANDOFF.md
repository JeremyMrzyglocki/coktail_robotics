# Handoff — Robot Skill Store

Everything needed to pick this up cold. Written 2026-10-17 at the end of the first
build session. Nothing is committed to git yet (`git init` done, zero commits).

---

## 1. What this is

A working prototype of **Daidai Labs' product**: you type a process in plain
language, an LLM compiles it into a sequence of purchasable robot skills with
prices and measured success rates, a world model verifies the sequence is
physically coherent, you assign hands and the scheduler parallelises it, and the
plan is queued to a robot runner that executes it and writes the success rates
back into the storefront.

Built for a 30-hour hackathon run by Daidai Labs, with two **Spirit AI Moz1**
robots, VR teleoperation, GPUs, and human demonstration datasets available.

**Location:** `/Users/jeremymrzyglocki/Github_projects/robot-skill-store`
**Runs with:** `uvicorn app.api:app --port 8000` + `python runner/runner.py --mock`

---

## 2. The hackathon brief, and what it rewards

Daidai's challenge: *"make robot skills easier to create, reuse and deploy."*
Suggested directions: skill training with minimal data, data efficiency, a skill
factory, one-shot learning, skill transfer, skill composition, easy deployment.

Their stated judging bar, quoted almost verbatim:

> "Show us a working demo, measure your success rate or resource efficiency, and
> explain what you've learned. A simple skill with a 90% success rate and minimal
> training data could be more impressive than a complex demo that only works once."

Two starting tasks were suggested: **surface wiping using Eidon data**, and
**pick and place using EgoDex data**.

So the rubric is: measurement + reusability, not robot theatrics. Everything in
this repo is pointed at that.

---

## 3. Market research — who else exists

Daidai's public site sells both halves: egocentric data collection *and* a skill
catalog ("Pick a skill. Add it to your robot") listing Unitree G1, quadrupeds and
AgiBot as compatible. They are roughly a month old.

**Direct analogues (egocentric data → skills)**
- **Roborecs** — first-person multimodal human-demo data, LeRobot-compatible, EU capture. Nearly Daidai's data business verbatim.
- **Human Archive** — pays gig workers in India to wear camera caps; 1,000+ headsets.
- **Build AI** — open-sourced *Egocentric-10K*: 10,000 h, 2,153 factory workers, 16.4 TB, Apache-2.0. **This commoditises paid egocentric data** and is the biggest threat to a data-collection moat.
- **Agile Robots "Robot Academy"** — Munich, worker video → training data, no teleop.
- **Nature Will** — Natura-1, pretrained on 1M+ hours egocentric.

**Skill stores (what Daidai wants to be)**
- **Unitree Robot App Store** — beta since late 2025, ~1,200 developers, 237 apps, on the G1. The OEM shipping a store for the exact hardware Daidai lists.
- **OpenMind** — robot app store on the OM1 OS, early 2026, cross-platform; partners reportedly include UBtech, **AgiBot**, Deep Robotics, Fourier, Booster, Dobot, LimX.
- **Hugging Face LeRobot + Hub** — the free one. Standard dataset format, pretrained policies (ACT, π₀, SmolVLA), teleop→record→train→deploy in a few CLI commands.
- **RobotAppStore** (2011, Nao/Roomba era) — Grishin-backed, now out of business. The cautionary tale.

**Could make a skill store unnecessary**
- **Physical Intelligence (π)** — ~$600M at $5.6B, reportedly raising ~$1B at $11B+. Wants to be the software layer robot makers call like an API. Open-sourced π₀.
- **Skild AI** — ~$1.4B at $14B+ (SoftBank, NVIDIA's NVentures, Bezos Expeditions). One "omni-bodied brain" across quadrupeds, humanoids, arms.

**The no-code precedent that already works (industrial)**
- **Micropsi Industries (MIRAI)** — Berlin, $30M Series B. Train skills by human demonstration with a wrist camera, no programming. Went hardware-agnostic from UR/FANUC to KUKA and, via voraus robotik, broadly to 6-axis arms. Closest working version of "a skill that installs on any arm".
- **Wandelbots** — Dresden, €26M+. TracePen demonstration → compiles to vendor-specific robot code.
- **Intrinsic (Alphabet)** — developer platform, ready-made universal grasping skills.

**Vertically integrated consumer**
- **Sunday Robotics** — $165M Series B at $1.15B (March 2026, Coatue-led). Memo home robot trained via a patented **Skill Capture Glove**, ~10M episodes from 500+ homes, explicitly avoiding teleoperation.

### The strategic conclusion this project is built on

Daidai is squeezed three ways: OEM stores own the hardware, open hubs give away
weights and data, and foundation-model labs want skills to be prompts. The one
thing none of them provide is **certification and per-unit deployment** — a skill
with a published, measured success rate that provably installs and self-verifies
on *your* specific robot, with its camera in its slightly wrong place.

That is what this repo builds. Say it out loud in the pitch.

---

## 4. Quickstart

```bash
cd /Users/jeremymrzyglocki/Github_projects/robot-skill-store
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
set -a && . ./.env && set +a
.venv/bin/uvicorn app.api:app --reload --port 8000
```

Second terminal:

```bash
set -a && . ./.env && set +a
.venv/bin/python runner/runner.py --mock --speed 6
```

Then open <http://127.0.0.1:8000>, or drive it from the terminal:

```bash
.venv/bin/python cli.py run "making a pina colada"
```

### Credentials

- The key you supplied is in **`API.txt`** and it is an **OpenAI** key (`sk-proj-…`), not Anthropic. It is gitignored, and `.env` (mode 600) was generated from it.
- `app/llm.py` is **provider-agnostic**: OpenAI or Anthropic, whichever key is present, or force with `LLM_PROVIDER`.
- Model is **`gpt-4.1-mini`**. Measured on "mix me a piña colada": `gpt-4o-mini` 23 s and still invalid, `gpt-4.1-nano` 15 s invalid, `gpt-4.1-mini` **4.3 s valid**. Do not "upgrade" to 4o-mini thinking it is better; it is not, for this task.
- The two-stage compiler (§9c) can give stage 1 its own model with `COMPILER_ACT_MODEL`. `gpt-4.1` there beat `gpt-4.1-mini` on `tools/compile_eval.py` (24/26 vs 22/26 valid, same or lower latency); binding stays on `COMPILER_MODEL`.
- `ROBOT_SHARED_SECRET` authenticates the two robot endpoints. They queue **physical arm motions** — do not leave them open.

---

## 5. Architecture

```
browser / CLI  ──▶  FastAPI + SQLite  ◀── polls ──  runner.py  ──▶  Moz1
                    (laptop:8000)                   (same laptop)    (CAT6)
```

The runner only makes **outbound** requests, so nothing has to reach into the
laptop: no tunnel, no port forward, works behind a captive portal or hotspot. The
120 Hz control loop stays in the runner, never across the network.

| File | What it does |
|---|---|
| `app/api.py` (550) | FastAPI. 16 endpoints, listed below. |
| `app/compiler.py` | Two stages: **act it out** (request → objects, phases of hand movements, goal; no catalog in view), then **bind** (movements → catalog skills or gaps, each gap with an open dataset). Enum-constrains skill IDs. Runs the **repair loop** on the binder. |
| `app/llm.py` (119) | OpenAI/Anthropic structured-output call behind one interface. |
| `app/validator.py` | STRIPS-lite world model: per-hand predicates, validation (incl. `acts_on` object-kind check, gaps simulated in place), two-hand episodes, dependency graph, `balance_hands` search. **The brain.** |
| `app/catalog.py` (228) | Catalog reads, success rates, Wilson intervals, availability tiers, gap report, benchmark query. |
| `app/models.py` | Pydantic wire types. |
| `app/db.py`, `app/schema.sql` | SQLite: `skills`, `plans`, `runs`, `requests`, `compile_cache`. |
| `app/static/{index.html,style.css,app.js}` (1,653) | Zero-build storefront. Daidai orange/black. |
| `runner/runner.py` (233) | Polls for jobs, executes **waves** with per-hand concurrency, reports every attempt. Stdlib only. |
| `runner/executor.py` (105) | `SkillExecutor` protocol + `MockExecutor` (thread-safe, seeded). |
| `runner/moz1.py` (218) | Real Moz1 executor. **Two methods deliberately unimplemented** — see §9. |
| `runner/probe_robot.py` | Run this in your first 10 minutes of robot access. |
| `cli.py` (190) | Terminal control: `skills`, `compile`, `install`, `run`, `gaps`. |
| `tools/make_catalog.py` (327) | The whole 57-skill catalog as one editable table. |
| `tools/run_eval.py` (239) | The skill evaluation harness (does a skill work?). |
| `tools/compile_eval.py` | The compiler evaluation (does an unfamiliar request become a valid plan?). 8 novel + 5 demo prompts → `reports/compile_eval_*.md`. |
| `tools/fetch_media.py` (236) | Dataset cover images from the HF Hub. |

**Endpoints:** `GET /`, `/api/skills`, `/api/skills/{id}`, `/api/datasets`,
`/api/gaps`, `/api/benchmark`, `/api/plans/{id}`, `/api/plans/{id}/status`,
`/api/jobs/next`†, `POST /api/compile`, `/api/validate`, `/api/autobalance`,
`/api/install`, `/api/compose`, `/api/runs`†, `/api/plans/complete`†
(† = requires `Authorization: Bearer $ROBOT_SHARED_SECRET`).

---

## 6. The eight design decisions that matter

Do not undo these without understanding why they exist.

**1. The plan is a program, not a shopping list.** One JSON artefact renders as the
cart (price, vendor, rating) and as the DAG the robot executes. That is what makes
the install button real rather than a mockup.

**2. Ratings are measured, never typed.** `app/catalog.py` computes success rates
from the `runs` table, which the robot writes. A skill nobody has run shows *no
data*. There is no code path that lets a human enter a rating.

**3. The model proposes, the validator decides.** `skill_id` is enum-constrained to
the live catalog, then `app/validator.py` replays the plan through a STRIPS-lite
world model. `/api/install` refuses an invalid plan with 409. This is also why a
weak, cheap model is usable.

**4. The repair loop is what makes a cheap model work.** One-shot output from a
small model is rarely installable. The validator's complaints go *back* to the
model, which is far better at fixing a named error than avoiding it (`_repair` in
`app/compiler.py`, 2 rounds by default). Only the binding stage is retried; the
motion script from stage 1 is not in question.

**5. Gaps are the product.** Anything the catalog cannot do goes in `missing[]`,
never invented into `steps[]`, positioned inline via `insert_after` (exact by
construction: the binder returns one sequence and gaps sit where they occur), and
every request is logged. Each gap names the open dataset (matched on
`data/datasets.json` → `covers`) that could train it. `/api/gaps` ranks unmet demand — Daidai's data-collection
roadmap, generated from customers instead of guesswork. **Lead the pitch with the
storefront, close it with the Demand page.**

**6. Hand predicates are scoped per hand.** `hand_empty@left`, `bottle_grasped@right`.
Two sub-chains on different hands share no predicate and no hand edge, so the
scheduler puts them in the same time slot. This is where the parallelism comes
from — **not from the LLM**. It is correct by construction rather than by asking a
model nicely. Shared world facts still serialize (`resource` edges): two pours into
one glass cannot overlap, because there is one glass.

**7. Previews are schematics, not photographs.** Skill thumbnails are SVG generated
from each skill's own manifest (category glyph + availability bar). Earlier these
were real dataset frames, but 30 of 41 were a hash-picked frame from *someone
else's* dataset — a store card implying "this is what the skill looks like" when it
was not. Nothing in the seed catalog has been recorded yet, so no photo can
honestly depict these skills. Real frames remain on **dataset** cards, where they
genuinely are representative. If you record real Moz1 episodes, swap in real frames
with exact provenance — `tools/fetch_media.py --skills` still does this.

**8. Rates are intervals, not point estimates.** 18/20 is not "90%", it is
90% [70%, 97%]. Wilson score, because it stays sensible at 0% and 100%. The
Benchmark page draws each interval to scale so a wide bar visibly means a weak
claim.

---

## 7. Measured results so far

All from the **mock executor** — honest numbers for the system, not yet for the robot.

| What | Result |
|---|---|
| Compiler model choice | `gpt-4.1-mini` 4.3 s valid · `gpt-4o-mini` 23 s invalid · `gpt-4.1-nano` 15 s invalid |
| Compile eval, 13 prompts × 2 (`tools/compile_eval.py`, stage 1 on gpt-4.1) | valid **25/26** (96% [81–99%]) · hands empty 25/26 · 0 wrong-object grasps · 56/56 gaps with an open dataset · median ~7 s — `reports/compile_eval_20261017T134904.md` (before hand labels: 24/26, `…133529.md`) |
| Two-handed request ("make me a jam sandwich") | valid in **15/20** compiles with hand labels, 0/6 without |
| Auto-balance, piña colada | 12 → **8** time slots, widest branch 2 → 3, 8 evaluations, ~1 ms |
| Auto-balance, 40-step chain | 31 → 17 slots, 512 evaluations, 119 ms (exhaustive) |
| Auto-balance, 80-step chain | 61 → 35 slots, 77 evaluations, 38 ms (hill-climb) |
| Parallel execution (mock) | **15.3 s** vs **25.4 s** `--serial` — 39% faster, matching the predicted depth drop |
| Skill eval, 13 skills × 20 trials | overall 248/260 = 95.4% [92–97%] |

Report: `reports/eval_20261017T111252.md`. Regenerate any time with
`python tools/run_eval.py --all-trained --trials 20`.

---

## 8. Spirit AI Moz1 — everything established

From `docs.spirit-ai.com`, verified by reading the docs. **This is the most
expensive knowledge in this file to re-derive.**

```
SDK           mozrobot, classes MOZ1Robot / MOZ1RobotConfig
transport     ROS 2 Humble (DDS), ROS_DOMAIN_ID=33
network       laptop static IP on 172.16.0.x, robot at 172.16.0.20, CAT6
              (teleop page says 172.16.1.20 — the docs contradict themselves, ask)
control       120 Hz loop, SI units (radians, metres, seconds)
cameras       3× RealSense @ 30 Hz — head, left wrist, right wrist (3 USB 3.0 ports)
host          Ubuntu 22.04, Python 3.10+
structure     dualarm | wholebody_without_base | wholebody
```

```python
robot.connect()
robot.enable_external_following_mode()   # MANDATORY before any send_action
obs = robot.capture_observation()        # joints, cartesian, gripper, images
robot.send_action(action_dict)           # steady 120 Hz
robot.reset_robot_positions(...)         # ASYNC — returns on send, not on arrival
```

**Traps:** `enable_external_following_mode()` is mandatory and easy to miss;
`reset_robot_positions` needs a 3–5 s settle.

**π0.5 path exists and is documented** (`docs.spirit-ai.com/open-resources/pi.html`):
openpi, `pi05_moz` train config, dataset at
`~/.cache/huggingface/lerobot/spirit-ai/pickplace` (LeRobot cache layout). Deployment
is already client/server:

```bash
uv run scripts/serve_policy.py --default-prompt='…' \
  policy:checkpoint --policy.config=pi05_moz --policy.dir=/path/to/checkpoint
python3 examples/moz1_real/main.py --host … --port …
```

**A skill is therefore a `(checkpoint, prompt)` pair**, and π0.5 is
language-conditioned — several catalog skills can share one fine-tuned checkpoint
and differ only by prompt. That is the difference between 1 trained skill and 4 in
a 30-hour window. The catalog already models this (`checkpoint` + `prompt` fields).

**Known time sinks:**
- `mozrobot` must be installed **outside** the openpi `uv` env (Spirit's docs warn mixing breaks dependencies). Use their `examples/moz1_real/compose.yml` Docker path. This is why `runner/` is stdlib-only.
- First inference runs `torch.compile` and can time out. `Moz1Executor.load()` fires a warm-up for this reason.
- Check the laptop can reach the robot on wired `172.16.0.x` **and** the internet on wifi at the same time. Verify at hour 2, not hour 28.

**Ask the organizers on day one** (all hard blockers, gated behind Spirit support):
1. The openpi fork + `pi05_base` checkpoint + `pickplace` dataset (key + TOS Browser).
2. The `mozrobot` wheel (`0.1.0`, or `mozrobot-0.1.2.zip` for Docker).
3. RealSense serial numbers, in order: head, left wrist, right wrist.
4. Which robot IP is correct.
5. Whether Capture-X is set up (teleop alone needs only MovaXHelper; recording needs Capture-X).

**Teleop:** Quest headset + controllers, MovaXHelper, port 40030, Capture-X for
recording. The collection UI has explicit **Failed (D)** and **Complete (E)** keys —
use Failed aggressively; clean demos matter more than many demos when fine-tuning
on a few dozen episodes.

---

## 9. What is NOT done

**The robot executor is a stub in exactly two places.** `runner/moz1.py`
`_to_policy_obs()` and `_to_action()` both raise `NotConfigured` with a clear
message. The SDK docs do not publish observation keys or the action schema, so
rather than guess:

```bash
python runner/probe_robot.py --structure dualarm --no-camera
```

prints the real keys. Map them into those two methods. Everything else in the
runner is written and tested against the mock.

**`Moz1Executor.supports_parallel = False`, deliberately.** One `send_action`
carries the whole body and each π0.5 checkpoint drives both arms, so running two
skills at once needs a merge layer taking the left-arm block from one policy and
the right-arm block from the other at 120 Hz. Real, but not something to improvise
during a demo. Until it exists the runner executes waves in order and prints why.
**Say it that way on stage: the parallel schedule is a plan, the 39% is a mock
measurement.**

Also missing:
- No real robot data. Every number is from the mock.
- **Nothing is committed to git.** 11 changed files.
- The chalk-coverage success detector (top-down camera + pixel diff for % area cleared) — designed but not built. This is the cheapest way to get an objective, automatic metric.
- The teleop gap-fill loop: request → gap → teleoperate it live → publish → re-compile. The strongest demo moment available and still unbuilt.
- `app/validator.py` `hands_required()` reads an optional `hands` field that nothing sets; two-handed skills (`handover`, `polish_glass`) are inferred, not declared.

**Open question you raised and I have not addressed** (draft note at `t.txt`,
unsent): *why does `locate_object` sit on its own branch in the flowchart?* It is a
real modelling wrinkle — `locate_object` declares no preconditions, so it lands in
layer 0 and looks detached. Arguably it should depend on the step that creates the
need for it, or be folded into the grasp. Worth fixing; it is the first thing a
judge will point at. `t.txt` also says you think I misunderstood something — that
conversation did not happen, so it is still open.

---

## 9b. Second session (same day) — what changed

- **`locate_object` no longer floats on its own branch.** `object_located` is now
  hand-scoped (locating is an arm motion, consumed by that arm's grasp), and
  `locate_object` needs an empty hand. Hand episodes are computed by simulating
  what each hand carries, so locate → grasp → … → release is one episode.
- **Move, then act.** `move_to_station` ("Move To Location") needs `holding` and adds
  `positioned`; `pour_into` and `release_object` need `positioned`. Every grasp adds
  `holding`. New skills: `grasp_object` (fruit, lids — no more bananas as bottles)
  and `run_blender`. `glass_filled` was renamed `vessel_filled`; mixing re-asserts
  it so pouring out waits for the mix.
- **Space constraint:** two arms cannot be over the same target at once (a
  `resource` edge named "space over the …"); broad surfaces (table, counter…) are
  exempt (`SHARED_PLACES` in `app/validator.py`).
- **Compiler:** composites are hidden from it; repair messages name the skills
  that establish an unmet fact; a plan ending with something still in hand is a
  `loose_end` issue (non-blocking, but triggers a repair round). gpt-4.1-mini is
  still noisy on long recipes — same prompt can give a clean or a sloppy plan.
- **UI:** the FLOW tab is gone; the LIST has a git-log-style graph (one lane per
  hand; hover a row or a state chip to trace it). FLOWCHART cards have L/R
  toggles that slide the layout, hover tracing, and ▶ PLAY SCHEDULE. Default demo
  is now **"mix me a smoothie"**.
- **Footage:** `python tools/fetch_clips.py` cuts dataset preview clips into
  `app/static/clips/` (gitignored) + `data/clip_sources.json`; skill and dataset
  popups play them. LeRobot sets are AV1 and stream from the Hub (Chrome yes,
  Safari only on M3+) until an ffmpeg with libdav1d converts them.
- Startup now re-seeds the catalog every time (composites kept), so editing
  `tools/make_catalog.py` + restart is enough.

## 9c. Two-stage compiler — what changed and why

The single masterprompt planned *from* the catalog, so whatever the catalog could
not do was dropped or squashed into one task-sized gap ("draw_image_with_brush",
"perform_magic_moves"), and a bottle grasp on a paint bucket passed because the
predicates lined up. The fix is structural, not a list of special cases:

- **Stage 1, act it out** (`act_out`): no catalog in view. Objects, each classified
  into a kind from `data/object_kinds.json`; phases named by outcome, each broken
  into physical movements (movement verbs only — an outcome verb names a phase);
  and the goal. `COMPILER_ACT_MODEL` can give it a stronger model.
- **Stage 2, bind**: movements → catalog skills, or `GAP` items with a primitive
  name (`press_to_surface`, not the task), declared conditions, and an open
  dataset. Skill items and gap items are two schema shapes, which keeps output —
  and latency — down on long plans.
- **Object kinds are data.** Skills declare `acts_on` in `tools/make_catalog.py`
  (`OBJECT_KINDS`, `ACTS_ON`); the validator compares that with the kind stage 1
  gave the target (`wrong_object`, blocking). Nothing in code knows what a bucket is.
- **Gaps are simulated** with their declared effects, and take part in hand
  assignment, so a tool held through a run of gaps is still in hand afterwards.
- **Two hands.** Hand episodes now track both hands: a step that needs an empty
  hand while one is busy starts an overlapping episode on the other hand. This
  alone took the eval from 20/26 to 25/26 valid.
- **Hand labels.** Stage 1 says which hand does each movement, the binder copies
  it onto every step and gap (`Step.planned_hand`, `MissingSkill.hand`), and the
  validator puts a labelled step in the open episode on that hand. That is what
  lets one hand hold the jar while the other dips the knife in — facts alone
  cannot say which hand reaches. Labels yield to facts when they contradict them
  (locate on the right, grasp on the left), to a person's L/R override in the UI,
  and are absent for steps a person inserts. The UI sends them back on every
  re-check. Repair complaints now say what a busy hand still holds and since
  which step.
- **Duplicate gaps** (same pre/postconditions as a catalog skill) go back to the
  binder as a repair complaint.
- **Datasets.** Only open-access datasets are offered (`catalog.open_datasets()`),
  and each has a factual `covers` line describing its footage.
- **Cache.** `COMPILER_VERSION` is part of the cache key: bump it on any compiler
  change, and **re-warm the demo prompts** — old entries no longer match.

Known limits, from the eval:
- **Two-handed plans** now validate most of the time (jam sandwich 15/20). The
  rest are plans where a hand picks up something new while still holding the
  last thing; the repair hint names it, but two rounds do not always fix it and a
  third round did not help (5/6 either way, up to 40 s).
- Dataset matches lean heavily on EPIC-Kitchens, including for motions it does not
  really show (shuffling cards). Coverage is complete; precision is unmeasured.
- On gpt-4.1-mini, stage 1 still sometimes writes an outcome as a movement
  ("operate blender") or skips a trained skill (`wipe_surface`).

## 9c. Install gate, runner refusal, skill aliases (same day, later)

Tested 14 fresh prompts: 7 feasible, 5 "valid" but wrong, 2 failed. Fixes:

- **Install gate.** `PlanResponse.installable` / `install_blockers`: a plan with
  gaps or any step without a checkpoint is not queueable; `/api/install` returns
  409 "not runnable: 2 gaps (…)" and the button reads "Not runnable: …".
  `valid` still only means the preconditions chain.
- **Runner refuses untrained steps.** `run_job` checks every step has a
  checkpoint before any motion; otherwise it completes the plan as failed with
  nothing run and nothing logged -- the mock can no longer write a rating for a
  skill that was never performed (it had: run_blender 100% from one mock run).
- **Skill aliases** (`ALIASES` in tools/make_catalog.py, `aliases` in the manifest,
  `aka` in the binder's catalog block). "drag the cloth over the table" now
  binds to wipe_surface instead of a gap; COMPILER_VERSION is 4 so old cached
  plans recompile.
- **Gap dedupe.** `catalog.covering_skill(gap, catalog)` matches a proposed gap
  to a skill by alias words (single generic verbs never match alone). The repair
  loop sends matches back to the binder; `/api/gaps` adds `covered_by`
  (trained = binder miss, untrained = data order) and the Demand page shows a
  badge. 15 of 38 logged gaps were covered -- the #1 item, operate_blender ×41,
  was run_blender all along.

## 9d. Contents ledger: pours go from the held vessel into the target

The smoothie plan ended with grasp_glass(glass) → move_to_station(blender) →
pour_into(glass): the glass tipped into the blender. The predicate model cannot
see it -- `holding` + `positioned` hold either way round -- so the validator now
keeps a ledger: which object each hand holds (set by grasps), and what each
object contains (bottles start full, glasses and shakers empty; pours and
releases move contents). Skills declare `flow` in the manifest (`FLOW` in
tools/make_catalog.py): pours are `held->target`, release/place_in_bin are
`object->target`. `wrong_flow` is blocking and fires on: pouring into the thing
being held, pouring from an empty glass/shaker, pouring onto the table. The
binder prompt states the direction; COMPILER_VERSION is 5.

## 9e. Generated props and the repair model

- **Props on demand.** The ANIMATION tab had builders for bottles, glasses,
  fruit, cloth, a blender; anything else was a grey cube. `app/props.py` now
  asks the model to design an unknown object once as a list of primitives
  (box/cylinder/sphere/cone/torus, metres, grey shades, how a hand holds it),
  bounds every number, caches it in the `props` table and serves it from
  `/api/props?names=a,b`. The browser assembles the primitives
  (`PROPS.generated` in scene-kit.js); no generated code is ever executed.
  Three objects took 2.6 s and a few hundred tokens; the second plan naming them
  is instant. To redo one, delete its row from `props`.
- **REPAIR_MODEL.** The first bind stays on COMPILER_MODEL (gpt-4.1-mini); repair
  rounds go to REPAIR_MODEL (gpt-4.1 in .env) because that is where the small
  model fails on 25-step plans. A wrong_flow earns one extra repair round.

## 9f. Footage for every dataset

133 of 138 datasets have a local 6 s clip in `app/static/clips/` (36 MB,
gitignored -- ship the folder when deploying). `tools/fetch_clips.py` now: uses
Homebrew's ffmpeg (`ffmpeg_bin()` in fetch_media.py; Anaconda's shadows it on
PATH and cannot decode AV1), pulls Build AI's gated sets out of their tar shards
with HF_TOKEN from .env, saves progress after every dataset, and skips what is
already local (`--only <id>` redoes one). Skill popups show the first of their
datasets that has footage and caption it by name. Still without footage: EgoDex,
Ego-Exo4D, EPIC-KITCHENS (off the Hub), Spirit pickplace, droid-scooping subset.

## 10. Gotchas that cost time

- **Browser caching.** Asset URLs are stamped with mtime and the HTML is sent `no-store`, but some browsers still hold the document. If an edit does not appear, add `?r=1` to the URL. Changing only the `#fragment` does **not** reload.
- **LeRobot v3 videos are AV1.** The stock macOS ffmpeg cannot decode them. `brew install ffmpeg` gets one with libdav1d. Image-column datasets (`lerobot/aloha_sim_insertion_human_image`) sidestep this entirely.
- **`meta/tasks.parquet` needs pyarrow ≥ 21.** Older pyarrow fails with "Repetition level histogram size mismatch".
- Structured-output strict mode forbids free-form objects, which is why step `params` travel as a `{name, value}` list and are flattened server-side.

---

## 11. Verified dataset identifiers

Tested and reachable:

| Dataset | Repo | Access | Note |
|---|---|---|---|
| Egocentric-10K subset | `Voxel51/Egocentric_10K_subset` | open | **Start here.** H.264, ffmpeg reads it straight off the URL. |
| Egocentric-10K | `builddotai/Egocentric-10K` | gated-auto | 10,000 h, 16.4 TB, Apache-2.0. Stream, never download. |
| Egocentric-100K | `builddotai/Egocentric-100K` | gated-auto | 10× the above. |
| SO-101 Pick & Place | `lerobot/svla_so101_pickplace` | open | 50 episodes, 11,939 frames, 30 fps. AV1 video. |
| ALOHA Insertion (image) | `lerobot/aloha_sim_insertion_human_image` | open | Frames as images — Hub viewer serves thumbnails directly. |
| DROID | `lerobot/droid_1.0.1` | open | Large multi-scene Franka. |
| EgoDex | github.com/apple/ml-egodex | GitHub only | 829 h, 2 TB, 338k episodes, 194 tasks, Vision Pro hand poses. **Not on the Hub.** |
| Spirit pickplace | `spirit-ai/pickplace` | private | Nothing public under `spirit-ai`. From support only. |

Set `HF_TOKEN` after accepting terms once to reach the gated Build AI sets.
Full registry with licences in `data/datasets.json`, surfaced on the Data page.

---

## 12. Suggested next steps, in order

1. **Commit.** Nothing is in git yet.
2. **Fix the `locate_object` branching wrinkle** — first thing a judge will question.
3. **Build the chalk-coverage success detector.** Dust the table with chalk or coloured beads, top-down camera, pixel diff → % area cleared. Objective, automatic, resettable in 5 s, and it makes a 20-trial eval fast and credible. Use dry granular media rather than liquid: visually identical at 3 m, tolerant of centimetres of error, no spills.
4. **Get robot access and run `probe_robot.py`.** Map the two methods. Everything downstream is already written.
5. **Record 40–60 teleop demos, fine-tune one checkpoint, and use prompts to get several skills from it.**
6. **Rerun `tools/run_eval.py --robot --trials 20`** — the same report regenerates from real trials, and the storefront ratings become real.
7. **Build the teleop gap-fill loop** if time allows. Judge types a request → one skill is missing → teleoperate it live in VR → publish → re-compile → it runs. That is the whole flywheel in three minutes.

## 13. The demo script that sells this

1. A **judge** types the request — hand them the keyboard.
2. The chain appears: skills with prices, measured rates, availability tiers, and the gaps named in place.
3. Click **AUTO-BALANCE HANDS** — 12 → 8 time slots in front of them.
4. Switch to **FLOWCHART** — the 3D assembly, parallel branches visible.
5. **Install & run** — the runner executes, ratings tick up live.
6. **Benchmark** page — measured rates with intervals, and the honest line about how many trials you would need for ±5pp.
7. **Demand** page — the ranked collection queue, generated from customer requests. *"This is your data-collection roadmap, and it wrote itself."*
