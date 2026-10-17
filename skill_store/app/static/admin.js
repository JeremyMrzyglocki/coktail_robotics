"use strict";
/* Admin: what customers asked for that the robot could not do, and what Daidai
   Labs should bid for the data to fix it. The model lives in app/bidding.py;
   this page only moves its parameters and draws the result. */
const $ = (s) => document.querySelector(s);
const el = (t, c, txt) => { const n = document.createElement(t);
  if (c) n.className = c; if (txt != null) n.textContent = txt; return n; };
const eur = (n, d = 0) => "€" + Number(n || 0).toLocaleString("en-GB",
  { minimumFractionDigits: d, maximumFractionDigits: d });

// name, label, min, max, step, format, help -- defaults come from the server.
const SLIDERS = [
  ["budget_eur", "Monthly data budget", 500, 30000, 500, (v) => eur(v),
   "All skills together. Bids are scaled down evenly to fit."],
  ["target_roi", "Target ROI", 1, 10, 0.5, (v) => v + "×",
   "Spend at most this fraction of the sales a skill unlocks."],
  ["sales_per_request", "Future sales per request", 1, 50, 1, (v) => v,
   "How many sales one logged request stands for once the skill exists."],
  ["episodes_needed", "Episodes to train a skill", 10, 200, 5, (v) => v,
   "Demonstrations needed from scratch."],
  ["open_data_discount", "Open data saves", 0, 0.8, 0.05, (v) => Math.round(v * 100) + "%",
   "Share of episodes a matching open dataset makes unnecessary."],
  ["half_life_days", "Demand half-life", 1, 180, 1, (v) => v + " days",
   "Older requests count less."],
  ["max_bid_per_episode", "Cap per episode", 5, 200, 5, (v) => eur(v),
   "Never pay more than this for one episode."],
  ["batch_episodes", "Quote per X episodes", 1, 100, 1, (v) => v,
   "The batch size the second bid column is priced for."],
];

let defaults = null;
const params = {};

function query() {
  return new URLSearchParams(Object.entries(params).map(([k, v]) => [k, String(v)]));
}

async function load() {
  const r = await fetch("/api/admin/bids?" + query());
  if (!r.ok) throw new Error(`bids: HTTP ${r.status}`);
  const b = await r.json();
  if (!defaults) {
    defaults = { ...b.params };
    Object.assign(params, defaults);
    drawSliders();
  }
  draw(b);
}

function drawSliders() {
  const wrap = $("#sliders");
  wrap.textContent = "";
  SLIDERS.forEach(([name, label, min, max, step, fmt, help]) => {
    const box = el("div", "slider");
    const lab = el("label");
    lab.htmlFor = "s-" + name;
    lab.appendChild(document.createTextNode(label));
    const val = el("b", null, fmt(params[name]));
    lab.appendChild(val);
    const input = el("input");
    Object.assign(input, { type: "range", id: "s-" + name, min, max, step, value: params[name] });
    input.addEventListener("input", () => {
      params[name] = Number(input.value);
      val.textContent = fmt(params[name]);
      schedule();
    });
    box.append(lab, input, el("small", null, help));
    wrap.appendChild(box);
  });
}

let timer = null;
function schedule() {
  clearTimeout(timer);
  timer = setTimeout(() => load().catch(showError), 120);
}

function kpi(value, label) {
  const k = el("div", "kpi");
  k.append(el("div", "v", value), el("div", "l", label));
  return k;
}

function draw(b) {
  const p = b.params;
  $("#meta").textContent = `${b.total_requests} requests logged`;
  const k = $("#kpis");
  k.textContent = "";
  k.append(
    kpi(`${b.unserved_requests}`, `requests could not run (of ${b.total_requests})`),
    kpi(`${b.skills.length}`, "skills blocking them"),
    kpi(eur(b.value_blocked_eur), "sales blocked so far, demand-weighted"),
    kpi(eur(b.spend_eur), `of ${eur(p.budget_eur)} monthly data budget bid`),
  );

  $("#pacing").innerHTML = "";
  const pace = $("#pacing");
  if (b.pacing < 1) {
    pace.append("Bids want ", el("b", null, eur(b.unpaced_spend_eur)),
      ` — all scaled to ${Math.round(b.pacing * 100)}% to fit the budget`);
  } else {
    pace.append("Budget covers every bid in full");
  }
  $("#batch-head").textContent = `Bid / ${p.batch_episodes} ep.`;

  const rows = $("#rows");
  rows.textContent = "";
  if (!b.skills.length) {
    const tr = el("tr"); const td = el("td", "empty",
      "No unserved demand yet. Requests that hit a gap or an untrained skill appear here.");
    td.colSpan = 9; tr.appendChild(td); rows.appendChild(tr);
    return;
  }
  // Floor it: with everything faded to 0.00, a 0/0 width would fill every bar.
  const topDemand = Math.max(1e-9, ...b.skills.map((s) => s.effective_demand));
  b.skills.forEach((s, i) => {
    const tr = el("tr");
    tr.appendChild(el("td", "rank", String(i + 1)));

    const sk = el("td", "sk");
    const name = el("b", null, s.name);
    name.appendChild(el("span", "kind " + s.kind, s.kind === "gap" ? "GAP" : "UNTRAINED"));
    sk.append(name, el("code", null, s.skill_id));
    if (s.example_prompts.length) {
      const q = el("div", "q", "“" + s.example_prompts[0] + "”");
      q.title = s.example_prompts.join("\n");
      sk.appendChild(q);
    }
    tr.appendChild(sk);

    const dem = el("td", "num dem");
    dem.appendChild(el("b", null, s.effective_demand.toFixed(1)));
    dem.appendChild(el("small", null,
      `${s.requests} req · ${s.distinct_prompts} distinct`));
    const bar = el("div", "dbar"); const fill = el("i");
    fill.style.width = (100 * s.effective_demand / topDemand).toFixed(1) + "%";
    bar.appendChild(fill); dem.appendChild(bar);
    tr.appendChild(dem);

    const val = el("td", "num", eur(s.value_blocked_eur));
    val.appendChild(el("small", null, `${eur(s.projected_value_eur)} projected`));
    tr.appendChild(val);

    tr.appendChild(s.dataset_name
      ? el("td", "ds", s.dataset_name)
      : el("td", "ds none", "none — must be recorded"));

    const eps = el("td", "num", String(s.episodes_needed));
    eps.appendChild(el("small", null, s.dataset_name ? "open data helps" : "from scratch"));
    tr.appendChild(eps);

    tr.appendChild(el("td", "num bid", eur(s.bid_per_episode_eur, 2)));
    tr.appendChild(el("td", "num", eur(s.bid_per_batch_eur, 2)));
    tr.appendChild(el("td", "num", eur(s.spend_eur)));
    rows.appendChild(tr);
  });
}

function showError(e) {
  const rows = $("#rows");
  rows.textContent = "";
  const tr = el("tr"); const td = el("td", "empty", "Could not load bids: " + e.message);
  td.colSpan = 9; tr.appendChild(td); rows.appendChild(tr);
}

$("#reset").addEventListener("click", () => {
  Object.assign(params, defaults);
  drawSliders();
  load().catch(showError);
});

load().catch(showError);
