// The Index of Azeroth. Copyright 2026 Index Case <indexofazeroth@pm.me>. PolyForm Strict 1.0.0, see LICENSE.md.
"use strict";


const epicWay = (way) => (way === "safe" || way === "fight" ? way : "any");
const newEpic = (key, anchor, way = "any", close = false, name = "Quest epic") => ({ kind: "epic", key, anchor, way: epicWay(way),
  close, data: null, step: null, name, stops: [], at: 0, lap: 1 });
function epicTitle(t) {
  const kind = (t?.key || "").split(":")[0], name = (t?.name || "").replace(/(\s+(quests?|epic|crafting))+$/i, "");
  const cls = CLASS_ICONS[player.data?.class];
  if (kind === "zone") return `${name ? `${name} ` : ""}Zone epic`;
  if (kind === "log") return `${app.who?.name ? `${app.who.name} ` : ""}Quest epic`;
  if (kind === "class") return `${cls ? cls[0].toUpperCase() + cls.slice(1) : "Class"} Quest epic`;
  if (kind === "prof") return `${name ? `${name} ` : ""}Profession epic`;
  if (kind === "camp") return "Camping epic";
  if (kind === "craft") return word("page.craft.title", { item: name });
  return `${name ? `${name} ` : ""}Quest epic`;
}
const isCraft = (key) => (key || "").startsWith("craft:");
function preferClose() {
  try { return localStorage.getItem("cc.preferClose") === "1"; } catch (e) { return false; }
}

function startEpic(d) {
  const run = app.tracks.epic, label = d.label || `the ${d.name} quest epic`;
  if (run && run.key !== d.key) {
    const aside = isCraft(d.key) && !isCraft(run.key);
    return ask({ title: "One epic at a time",
                 text: aside ? word("page.craft.ask", { running: run.name, item: d.name }) : `${run.name} is running. Stop ${run.name} and start ${label}?`,
                 yes: aside ? word("page.craft.ask.yes") : "Start the new epic", no: "Keep the current epic", onYes: () => beginEpic(d, label) });
  }
  beginEpic(d, label);
}

const asideEpic = () => (isCraft(app.plan?.key) && app.plan?.aside && planIsMine({ ...app.plan.aside, playing: app.plan.playing })
  ? app.plan.aside : null);
function backKey() {
  const a = asideEpic(), name = a && epicTitle(a);
  return a ? `<button data-epic-back title="${esc(word("page.craft.back.tip", { epic: name }))}">${esc(word("page.craft.back", { epic: name }))}</button>` : "";
}
function backEpic() {
  const a = asideEpic();
  if (!a) return;
  postJson("/api/shared/back", {}).then((r) => {
    if (!r?.back) return refreshShared();
    app.stoppedHere = null;
    app.tracks.epic = newEpic(a.key, a.anchor || null, a.mode, !!a.close, a.name);
    saveTrack("epic");
    refreshEpic(true);
    setTimeout(refreshShared, 500);
    showToast(word("page.craft.back.done", { epic: epicTitle(a) }));
  }, (e) => askFailed(word("page.craft.back.failed"), e));
}

const PICK_KEY = { vendor: "buy", auction: "buy", grind: "grind", gather: "grind", quest: "quest", craft: "craft" };
function materialsHtml(t) {
  const rows = t?.data?.materials, crafts = craftsHtml(t);
  if (!rows?.length) return crafts;
  return `${crafts}<div class="plan-materials"><span class="plan-next-label">${esc(word("page.craft.materials"))}</span>${rows.map(materialRowHtml).join("")}</div>`;
}
function craftsHtml(t) {
  const rows = t?.data?.route;
  if (!rows?.length) return "";
  const line = (r) => `<div class="guide-line">${esc(word("page.craft.route.row", { from: r.from, to: r.to, count: num(r.crafts),
    item: r.item, colour: r.colour }))}</div>`;
  return `<div class="plan-next"><span class="plan-next-label">${esc(word("page.craft.route"))}</span><div>${rows.map(line).join("")}</div></div>`;
}
const MATERIAL_WAY = { vendor: (f) => word("page.craft.row.vendor", f), grind: (f) => word("page.craft.row.grind", f),
  gather: (f) => word("page.craft.row.gather", f), quest: (f) => word("page.craft.row.quest", f), craft: (f) => word("page.craft.row.craft", f) };
function materialWay(r) {
  const fill = { item: r.name, count: num(r.short), vendor: r.vendor, zone: r.zone, quest: r.quest };
  if (r.pick === "auction") return esc(word("page.craft.row.auction", { ...fill, coins: "\u0001" })).replace("\u0001", money(r.cost));
  return esc((MATERIAL_WAY[r.pick] || ((f) => word("page.craft.row.none", f)))(fill));
}
function materialRowHtml(r, i) {
  const need = r.kind === "pattern" ? word("page.craft.row.pattern", { item: r.name })
    : word("page.craft.row.need", { count: num(r.need), item: r.name, have: num(r.have) });
  return `<div class="plan-material" style="--depth:${Math.max(0, r.depth - 1)}"><div class="pm-item"><img class="market-ic q${r.q}"
    src="/icon/${r.iconStored ? r.icon : "inv_misc_questionmark"}.jpg" alt=""><span class="market-name q${r.q}">${esc(r.name)}</span></div>
    <div class="guide-line">${esc(need)}</div><div class="guide-line muted">${materialWay(r)}</div>
    <span class="market-keys">${ITEM_KEYS.map((k) => itemKeyHtml(r, i, k, { hover: "pick", on: PICK_KEY[r.pick] })).join("")}</span></div>`;
}
function pickMaterial(t, i, key) {
  const r = t?.data?.materials?.[i];
  if (!r) return null;
  const way = key === "buy" ? (r.vendor ? "vendor" : "auction") : key === "grind" ? r.keys.grind : key;
  if (PICK_KEY[r.pick] === key && (key !== "grind" || r.pick === way)) return null;
  return postJson("/api/shared/pick", { key: t.key, item: r.item, way }).then((got) => {
    if (!got?.set) return showToast(word("page.craft.pick.failed"));
    startEpic({ key: t.key, name: t.name, replan: true });
  }, (e) => askFailed(word("page.craft.pick.failed"), e));
}
function beginEpic(d, label) {
  const kept = !d.replan && keptEpic(d.key);
  if (kept) return reopenEpic(kept);
  const run = app.tracks.epic, me = playerWorld();
  app.tracks.epic = newEpic(d.key, me ? [me.inst, me.n, me.w] : null, run?.way, preferClose(), d.name);
  app.tracks.epic.planReady = true;
  app.tracks.epic.startedAt = Date.now();
  app.tracks.epic.planBefore = app.plan?.version ?? null;
  app.tracks.epic.brokeBefore = app.plan?.broke?.at ?? null;
  if (d.keepParked?.length) app.tracks.epic.keepParked = d.keepParked;
  app.stoppedHere = null;
  saveTrack("epic");
  refreshEpic(true);
  showToast(d.replan ? `The Index planned ${d.name} afresh from where you are${d.keepParked?.length ? " and kept its parked quests parked" : ""
  }. The Index is writing the plan for the game now`
    : `${label[0].toUpperCase()}${label.slice(1)} started. The Index is writing the plan for the game now`);
}

let epicSig = "", epicAgain = false;
function refreshEpic(force) {
  const t = app.tracks.epic;
  if (!t) return;
  const sig = JSON.stringify([t.key, app.character, app.quests?.log, app.quests?.done, app.state?.level]);
  const changed = !!force || sig !== epicSig;
  if (!changed && !epicAgain) return;
  const q = new URLSearchParams({ key: t.key });
  if (t.anchor) { q.set("inst", t.anchor[0]); q.set("n", t.anchor[1].toFixed(1)); q.set("w", t.anchor[2].toFixed(1)); }
  if (t.close) q.set("close", "1");
  if (t.keepParked) q.set("parked", t.keepParked.join("."));
  const asked = askFor("epic", () => getJson(`/api/epic?${q}`, { key: null, accept: [409] }).then((data) => {
    if (data.waiting) throw Object.assign(new Error("waiting for the game"), { waiting: data.waiting });
    return data;
  }), { force: changed });
  if (!asked) return;
  epicSig = sig;
  epicAgain = false;
  asked.then((data) => {
    if (app.tracks.epic !== t) return;
    t.waiting = null;
    setEpicData(t, data);
  }, (e) => {
    epicAgain = true;
    if (app.tracks.epic !== t) return;
    t.waiting = e.waiting || null;
    renderTracks();
  });
}

const stepPlace = (s) => JSON.stringify([s?.inst, s?.at, s?.loop, s?.ways]);
const epicAllDone = (d) => !!d && !d.steps?.length && !!d.quests?.length && d.quests.every((q) => q.state === "done");
function setEpicData(t, data) {
  const cur = gameStep(t, data) || data.steps[0] || null, was = t.step || t.heldStep;
  t.data = data;
  t.name = data.name;
  askShared(t);
  const same = was && cur && was.kind === cur.kind && was.quest === cur.quest && was.text === cur.text;
  const back = same && !t.step;
  const fuller = same && !back && (!!cur.spawns?.length !== !!was.spawns?.length || !!cur.loop?.length !== !!was.loop?.length
    || stepPlace(cur) !== stepPlace(was));
  t.heldStep = !cur && !epicAllDone(data) ? was : null;
  if (same && !back && !fuller) t.step = cur;
  if (!same || back || fuller) {
    t.step = cur;
    t.stops = cur?.loop?.length ? cur.loop.map((p) => (p[2] != null ? [p[0], p[1], p[2]] : [p[0], p[1]])) : cur?.at ? [cur.at] : [];
    t.loop = !!cur?.loop?.length;
    t.inst = cur?.inst ?? null;
    t.at = 0; t.lap = 1; t.path = null; t.asked = null; t.route = null; t.routeAsked = null; t.routePending = false;
    if (was && cur && !back && !fuller && !writtenPlan(t)) showToast(`Quest epic: ${cur.text}`);
    if (was && !cur && epicAllDone(data)) showToast(`${data.name} is all done`);
  }
  renderTracks();
}

app.shared = null;
let sharedAsked = "";
let sharedToast = false;
const SHARED_AGAIN_MS = 3000;
const sharedCode = (s) => s.k === "S" ? `S${s.what}:${s.npc}` : `${s.k}${s.ids.join(".")}`;
const planIsMine = (p) => !!p?.key && charSame(p.char, p.playing);
app.plan = null;
app.loadedPlan = null;
app.epicLive = null;
const loadedVersion = () => app.status?.nums?.sharedVersion || 0;
function loadedPlan() {
  const v = loadedVersion();
  if (!v) return null;
  if (app.shared?.version === v) return app.shared;
  if (app.loadedPlan?.version === v) return app.loadedPlan;
  const asked = app.loadedAsked !== v && getJson(`/api/shared?version=${v}`);
  if (asked) {
    app.loadedAsked = v;
    asked.then((sh) => { if (sh?.version === v) { app.loadedPlan = sh; renderTracks(); } }, () => { app.loadedAsked = 0; });
  }
  return null;
}
const planSteps = () => loadedPlan()?.epic?.steps || null;
function gameGuide() {
  const lp = loadedPlan(), live = app.epicLive, nums = app.status?.nums || {}, v = loadedVersion();
  if (!lp?.epic || !charSame(lp.epic.char, app.plan?.playing)) return null;
  if (live?.running && live.version === v) return live;
  if (live && !live.running && live.stopped) return null;
  return nums.epicStep != null ? { running: true, version: v, cur: nums.epicStep, done: nums.epicDone } : null;
}
function planInGame(t) {
  if (!t || t.kind !== "epic") return null;
  if (gameGuide() && loadedPlan().epic.key === t.key) return "running";
  const p = app.plan;
  if (p?.key !== t.key || !planIsMine(p)) return null;
  return loadedVersion() !== p.version ? "ready" : "loaded";
}
function writtenPlan(t) {
  const sh = app.shared;
  return composeMode(t) === "waiting" && sh?.version === app.plan.version && sh.epic?.key === t.key && sh.epic.steps?.length ? sh : null;
}
const STEP_WORDS = { noun: "step", first: "the first step" };
const writtenKey = (w) => `plan ${w.version}`;
function planLeg(plan, k) {
  const s = plan.steps[k];
  return { inst: s.inst, walks: s.lg || [] };
}
const planStepSpans = (plan) => plan.steps.map((s, k) => ({ inst: s.inst, name: s.text, id: k, outOnly: true,
  pts: [...(s.lg?.length ? planLeg(plan, k).walks.flat() : [s.at]), ...(s.loop || [])].filter(Boolean).map((p) => [p[0], p[1]]) }));
const pickedStep = (t, w = writtenPlan(t)) => legIndex(planStepSpans(w.epic), "epic", writtenKey(w));
function lookedLeg(t) {
  const w = t?.kind === "epic" && writtenPlan(t);
  return w ? planLeg(w.epic, pickedStep(t, w)) : null;
}
function shownPlan(t) {
  const w = writtenPlan(t);
  if (w) return { p: w.epic, g: null, inspect: true };
  return planInGame(t) === "running" && planSteps() ? { p: loadedPlan().epic, g: gameGuide(), inspect: false } : null;
}
const stoppedHereOnly = () => !!app.plan?.key && !!app.plan.closed && (app.epicLive?.running || app.status?.nums?.epicStep != null);
const closedEpic = () => (!app.tracks.epic && !dismissedClose(app.plan) ? keptEpic(app.plan?.key) : null);
const keptEpic = (key) => (!!key && app.plan?.key === key && app.plan.closed && planIsMine(app.plan) ? app.plan : null);
function closedEpicHtml(p) {
  const name = p.name || "The quest epic";
  const dismiss = p.closed.game ? `<button data-epic-dismiss title="${esc(word("page.epic.closed.dismiss.tip"))}">${esc(word("page.epic.closed.dismiss"))}</button>` : "";
  return panelHead(p.name || "Quest epic", trackStyle("epic", p).help, `${backKey()}<button data-epic-reopen title="This opens the epic again where you were, with its plan and progress">Reopen</button>${dismiss}`,
    { track: true, glide: true }) + `<div class="guide-line muted">${esc(name)} is closed. Its plan and your progress are kept.</div>`;
}
function reopenEpic(p = closedEpic()) {
  if (!p) return;
  const closedInGame = !!p.closed.game;
  postJson("/api/shared/open", { key: p.key }).then((r) => {
    if (!r?.opened) return refreshShared();
    app.stoppedHere = null;
    app.tracks.epic = newEpic(p.key, p.anchor || null, p.mode, !!p.close);
    saveTrack("epic");
    refreshEpic(true);
    setTimeout(refreshShared, 500);
    showToast(`${p.name || "The quest epic"} is open again where you were${closedInGame ? ". To pick it up in game, type /ioa guide start or /reload" : ""}`);
  }, (e) => askFailed("The epic is still closed", e));
}
function reopenedHere(t) {
  const p = app.plan, live = app.epicLive;
  return !!t && p?.key === t.key && !p.closed && !!p.opened?.game && planIsMine(p) && !live?.running ? p : null;
}
const newerPlan = (t) => {
  const p = app.plan;
  if (producing(t)) return null;
  if (p?.key !== t?.key || !planIsMine(p) || p.version === loadedVersion()) return null;
  if (p.fresh && p.start && loadedVersion() < p.start) return { ...p, rating: "start" };
  const lv = loadedVersion(), a = p.advice?.loaded === lv && p.advice?.version === p.version ? p.advice : null;
  if (a) return { ...p, rating: a.rating, reasons: a.reasons };
  return p.rating === "minor" || p.against === lv ? p : { ...p, rating: "minor", reasons: [] };
};
function newerPlanHtml(p) {
  if (p.rating !== "minor") return "";
  const why = planReasons(p.reasons || []);
  return `<div class="guide-line plan-minor">A new plan is ready${why ? `. ${esc(why)}` : ""}. Any /reload loads the new plan</div>`;
}
const startedHereSince = (t, at) => !!t?.startedAt && t.startedAt > (at || 0) * 1000;
function syncEpicWithGame() {
  const g = gameGuide(), t = app.tracks.epic, live = app.epicLive, lp = g && loadedPlan().epic;
  const sh = app.stoppedHere;
  if (sh && (sh.version !== loadedVersion() || (app.plan?.opened?.at || 0) * 1000 > (sh.at || 0))) app.stoppedHere = null;
  if (lp && (!t || t.key !== lp.key) && app.plan?.key === lp.key && !app.plan.closed && app.stoppedHere?.key !== lp.key
      && !startedHereSince(t, lp.written)) {
    app.tracks.epic = newEpic(lp.key, lp.anchor || null, app.plan.mode ?? lp.mode, !!lp.close);
    saveTrack("epic");
    refreshEpic(true);
    return showToast(`The guide for ${lp.name || "the quest epic"} runs in game, so the page shows the epic too`);
  }
  const closed = t && app.plan?.key === t.key ? app.plan.closed : null;
  if (closed && !startedHereSince(t, closed.at)) {
    stopTrack("epic", true);
    if (closed.by === "game") showToast(`You closed ${t.name || "the quest epic"} in game, so the page closed the epic too. Its plan and your progress are kept, and Reopen picks it up again`);
    return;
  }
  const p = app.plan;
  if (t && p?.playing && !planInGame(t) && p.working !== t.key && !startedHereSince(t, p.written)) {
    app.tracks.epic = null;
    return saveTrack("epic");
  }
  followLead(t, g);
}
function followLead(t, g = gameGuide()) {
  const w = writtenPlan(t);
  const at = w ? `${writtenKey(w)}:${pickedStep(t, w)}` : g && `${g.cur}:${g.handIn || ""}:${stopsOut(g.cur).join(",")}`;
  if (!t?.data || !at || at === t.gameCur) return false;
  t.gameCur = at;
  setEpicData(t, t.data);
  return true;
}
const PLAN_KIND = { P: "pickup", O: "objective", T: "turnin", D: "dungeon", S: "errand" };
const PLAN_VERB = { P: "Pick up", O: "Objective", T: "Turn in", D: "The dungeon", S: "Errand" };
const PLAN_ICON = { P: "pickup", T: "turnin", O: "objective", D: "dungeon" };
const PLAN_OBJECTIVE = { kill: "objective", loot: "loot", grab: "grab", use: "use", talk: "talk", heal: "heal", event: "event",
                         explore: "explore", escort: "escort", buy: "vendor", pickpocket: "pickpocket" };
const PLAN_ERRAND = { train: ["train", "Train"], repair: ["bank", "Repair"], sell: ["bank", "Sell"], restock: ["vendor", "Buy"],
                      bind: ["inn", "Set your hearth"], flightpath: ["flight", "Flight path"],
                      learn: ["train", "Learn"], supplies: ["vendor", "Buy"], craft: ["train", "Craft"], camp: ["camp", "Make camp"],
                      wall: ["warning", "Later"] };
const planIcon = (name, words = "") => `<img class="ui-icon" src="/ui/${name}.png" alt="${esc(words)}">`;
function stepItemIcon(s) {
  if (s.k !== "O" || !s.it || (s.ic !== "grab" && s.ic !== "loot")) return null;
  const icon = app.itemInfo?.[s.it]?.icon;
  if (!icon) wantItemInfo([s.it], () => renderTracks());
  return icon ? `<img class="ui-icon" src="/icon/${esc(icon)}.jpg" alt="">` : null;
}
const stepIconName = (s) => s.k === "S" ? PLAN_ERRAND[s.what]?.[0] || "vendor"
  : (s.k === "O" && PLAN_OBJECTIVE[s.ic]) || PLAN_ICON[s.k] || "objective";
const stepIcon = (s) => stepItemIcon(s) || planIcon(stepIconName(s));
function planVerb(s) {
  if (s.k === "S") return PLAN_ERRAND[s.what]?.[1] || "Errand";
  const first = s.k === "O" && /^(Kill|Collect|Use|Talk to) /.exec(s.text || "");
  return first ? first[1] : PLAN_VERB[s.k];
}
const nextWords = (s) => s.k === "D" ? s.name || "The dungeon" : s.k === "S" || s.k === "O" ? s.text : `${PLAN_VERB[s.k]} ${s.name || s.text}`;
const OBJECTIVES_MOST = 4;
const logObjectives = (id) => (app.questlog?.entries || []).find((e) => e.id === id)?.objectives || [];
function shownObjectives(s) {
  if (!s || s.k === "P") return [];
  return (s.ids || []).flatMap((id) => logObjectives(id).map((o, k) => ({ id, k, o }))).slice(0, OBJECTIVES_MOST);
}
function stepObjective(x, objs) {
  if (!x.target || x.get || !objs?.length) return -1;
  const want = x.target.toLowerCase(), has = (ob) => (ob.text || "").includes(x.target);
  const exact = objs.findIndex((ob) => has(ob) && objThing(ob.text).toLowerCase() === want);
  return exact >= 0 ? exact : objs.findIndex(has);
}
function rowKeys(steps, id, k, o) {
  const t = steps.find((x) => x.k === "O" && x.ids?.[0] === id && x.mobs?.length && stepObjective(x, logObjectives(id)) === k);
  return t ? t.mobs : [objThing(o.text)];
}
const mobColours = { kept: {} };
function rowColours(s, steps, along) {
  const keys = [], at = [];
  const add = (id, k, o) => { keys.push(rowKeys(steps, id, k, o)); at.push(`${id}:${k}`); };
  for (const { id, k, o } of shownObjectives(s)) add(id, k, o);
  for (const x of along) {
    const a = alongObjective(x);
    if (a) add(a.id, a.k, a.o);
  }
  const got = DirectorRules.colours(keys, mobColours.kept);
  mobColours.kept = got.kept;
  return Object.fromEntries(at.map((w, n) => [w, DirectorRules.table.badges.mobs[got.rows[n] - 1]]));
}
function objThing(text) {
  const t = String(text ?? "").replace(/\d+\s*\/\s*\d+/g, "").replace(/^\s*:\s*/, "").replace(/\s*:\s*$/, "")
    .replace(/\s+slain\s*$/, "").trim();
  return t || String(text ?? "");
}
function objCounts(o) {
  const m = /(\d+)\s*\/\s*(\d+)/.exec(o.text || "");
  return { done: o.done ?? (m ? +m[1] : 0), need: o.need ?? (m ? +m[2] : 0) };
}
const objLeft = (o, c) => (o.finished ? "" : c.need - c.done > 0 ? `${c.need - c.done} left` : "wanted");
const objTitle = (o, c) => (c.need >= 1 ? `${Math.min(c.done, c.need)}/${c.need} ${objThing(o.text)}`
  : objThing(o.text));
function objectivesHtml(s, colours, levels = false) {
  const shown = shownObjectives(s);
  return shown.map(({ id, k: n, o }) => {
    const c = objCounts(o), p = o.finished ? 100 : c.need > 0 ? Math.round(Math.min(c.done, c.need) / c.need * 100) : 0;
    const title = objTitle(o, c), left = objLeft(o, c);
    const k = levels && s.lv ? (s.mobs || []).findIndex((x) => (o.text || "").includes(x)) : -1;
    const lv = k >= 0 ? ` <small>${mobLevelHtml(stepMobLevels(s, k))}</small>` : "";
    return `<div class="guide-line plan-obj${o.finished ? " done" : ""}" style="--p:${p}%;--c:${o.finished ? "var(--card-green)" : colours[`${id}:${n}`]}"><span class="obj-title">${
      itemNamed(title, o.item, o.itemName)}${lv}</span>${left ? `<span class="obj-left">${left}</span>` : ""}</div>`;
  }).join("") + bagSlotsHtml(s, shown.map((r) => r.o));
}
function bagSlotsHtml(s, objectives) {
  const free = app.status?.nums?.bagFree;
  if (s?.k !== "O" || typeof free !== "number") return "";
  const want = DirectorRules.slots((objectives || []).map((o) => {
    const c = objCounts(o);
    return { item: o.type === "item", have: c.done, need: c.need, finished: !!o.finished };
  }), free);
  if (!want) return "";
  const title = DirectorRules.line("heads", want === 1 ? "bag_slot" : "bag_slots", { n: want });
  return `<div class="guide-line plan-obj bag-short" style="--p:${Math.round(free / want * 100)}%;--c:var(--error)"><span class="obj-title">${
    esc(title)}</span><span class="obj-left">${want - free} left</span></div>`;
}
const stepMobLevels = (s, k) => (s.lv?.[k]?.length ? s.lv[k] : null);
function nextChainsHtml(p) {
  const nx = p?.key?.startsWith("log:") ? p.next || [] : [];
  return nx.length ? `<div class="guide-line">The next quests in these chains: ${esc(nx.map((q) => q.name).join(", "))}</div>
    <button class="key small" data-epic-next="${nx.map((q) => q.id).join(".")}">Start these quests as an epic</button>` : "";
}
function handInStep(p, steps, g, cur) {
  const id = g?.handIn, at = cur ? steps?.[cur - 1] : null;
  if (!id || ((at?.k === "T" || at?.k === "P") && at.ids?.[0] === id)) return null;
  const you = playerWorld(true);
  const gap = (e) => you && e.i === you.inst ? Math.hypot(e.at[0] - you.n, e.at[1] - you.w) : Infinity;
  const e = (p?.ends || []).filter((x) => x.q === id && x.at).sort((a, b) => gap(a) - gap(b))[0];
  const name = (app.questlog?.entries || []).find((x) => x.id === id)?.title || `quest ${id}`;
  return { k: "T", ids: [id], name, npc: e?.npc, inst: e?.i, at: e?.at, extra: true,
           text: `Turn in ${name}${e?.npc ? ` to ${e.npc}` : ""}` };
}
const stepQuest = (x) => x?.name || x?.text || "";
function leadLine(g, steps, at, s) {
  const r = g?.reason;
  if (!r) {
    if (!s || !g?.handIn) return "";
    const key = s.k === "P" ? (s.npc ? "pickup" : "pickup_here") : (s.npc ? "handin" : "handin_here");
    return DirectorRules.quiet(key) ? "" : DirectorRules.say(key, { won: stepQuest(s), wonNpc: s.npc }) || "";
  }
  if (DirectorRules.quiet(r.key)) return "";
  const k = r.other ? (at || []).indexOf(r.other) : -1;
  const other = k >= 0 ? steps[k] : r.otherQuest ? handInStep(loadedPlan().epic, steps, { handIn: r.otherQuest }, 0) : null;
  return DirectorRules.say(r.key, { won: stepQuest(s), wonNpc: s?.npc, lost: stepQuest(other), lostNpc: other?.npc, n: r.n,
                                    thing: s?.target, things: s?.things, place: placeName(s), nearer: placeName(other) })
    || "";
}
function placeName(x) {
  const names = loadedPlan()?.epic?.places;
  return x?.pl && Array.isArray(names) ? names[x.pl - 1] : undefined;
}
function gameStep(t, data) {
  const w = writtenPlan(t);
  if (w) {
    const ps = w.epic.steps[pickedStep(t, w)];
    return planPlace(pageStep(data, ps) || planEntryStep(ps), ps, [], null, w.epic.steps);
  }
  const g = gameGuide(), steps = planSteps();
  const mine = steps && loadedPlan().epic.key === t.key;
  const x = mine ? handInStep(loadedPlan().epic, steps, g, g?.cur) : null;
  if (x) return { kind: "turnin", quest: x.ids[0], questName: x.name, text: x.text, inst: x.inst, at: x.at };
  const ps = g?.cur && mine ? steps[g.cur - 1] : null;
  if (!ps) return null;
  return planPlace(pageStep(data, ps) || planEntryStep(ps), ps, stopsOut(g.cur), g.cur);
}
const planEntryStep = (ps) => ({ kind: PLAN_KIND[ps.k], quest: ps.ids?.[0], quests: ps.k === "D" ? ps.ids : undefined,
  questName: ps.name, text: ps.text, inst: ps.inst, at: ps.at, zone: ps.zone });
function stopsOut(p) {
  const d = app.loopStops;
  return d && d.version === loadedVersion() ? d.steps?.[String(p)] || [] : [];
}
function loopLeft(loop, out) {
  const gone = new Set(out || []);
  if (!loop?.length || !gone.size) return loop;
  const left = loop.filter((_, k) => !gone.has(k + 1));
  return left.length ? left : loop.slice(0, 1);
}
function planPlace(step, ps, out, p, steps = planSteps()) {
  if (!ps?.at || !planHasWays(steps)) return step;
  const flat = (pts) => JSON.stringify((pts || []).map((q) => [q[0], q[1]]));
  const loop = ps.loop?.length ? loopLeft(flat(ps.loop) === flat(step.loop) ? step.loop : ps.loop, out) : null;
  return { ...step, inst: ps.inst, at: ps.at, loop, ways: entryWays(ps), planStep: p, ground: ps.ground || null };
}
const entryWays = (x) => ({ way: x.way || null, alt: x.alt || null, ez: x.ez || null,
  hw: x.hearth?.w?.length ? [x.hearth.at, ...x.hearth.w] : null });
function gameWay(ways, p) {
  if (!ways) return null;
  const n = app.status?.nums || {}, said = p != null && n.epicStep === p ? DirectorRules.table.guide.ways[n.epicWay - 1] : null;
  return (said && ways[said]) || ways.way || ways.alt || null;
}
const planHasWays = (steps = planSteps()) => (steps || []).some((s) => s.way || s.loop || s.walk);
function pageStep(data, ps) {
  const code = sharedCode(ps), mine = (data?.steps || []).filter((s) => epicCode(s) === code);
  return mine.find((s) => s.text === ps.text) || (ps.target && mine.find((s) => s.target === ps.target)) || mine[0] || null;
}
function partyLine() {
  const grp = app.group, members = grp?.members || [];
  if (grp?.of == null || !members.length) return "";
  const chips = members.map((m) => `<b style="color:${CLASS_COLORS[m.className] || tint("class-other")}">${esc(m.name)}</b> ${m.on ?? 0}/${grp.of}`);
  const away = members.filter((m) => m.away).map((m) => m.name);
  return `<div class="guide-line">Party: ${chips.join(" | ")}</div>${
    away.length ? `<div class="guide-line plan-door">You're at the door, waiting for ${esc(away.join(", "))}</div>` : ""}`;
}

function grindPoint(steps, states = [], cur = 0, level = app.state?.level || 0, live = null) {
  let at = -1, before = 0;
  for (let k = 0; k < steps.length && at < 0; k++) {
    const st = states[k] || "todo";
    if (st !== "done" && st !== "skipped" && steps[k].grind > level) at = k;
    else if (st === "todo" || st === "wait") before++;
  }
  const plan = { steps, states, live };
  const wall = cur || !states.length ? -1 : states.findIndex((st, k) => st === "wait" && !(steps[k]?.k === "P" && waitsOn(steps[k], plan)));
  const w = steps[wall], first = !(at >= 0 && at <= wall);
  if ((w?.min || 0) > level && first) return { level: w.min, before: 0, at: wall };
  const skill = w && first ? skillShort(w) : null;
  if (skill) return { skill, before: 0, at: wall };
  return at >= 0 && DirectorRules.said("reckoned", before, live?.play) ? { level: steps[at].grind, before, at } : null;
}
const WALL = wordsOf("both.wall");
function grindWords(steps, states, cur, live = null) {
  const g = grindPoint(steps || [], states, cur, undefined, live);
  if (!g) return "";
  const step = steps[g.at], then = step.text ? ` (then ${step.text})` : "";
  if (g.skill) return `${fillWords(WALL.skill, g.skill) || ""}${then}`;
  const when = g.before === 0 ? "now, the next quests open there" : `after the next ${g.before} step${g.before === 1 ? "" : "s"}`;
  return `Grind to level ${g.level} ${when}${then}`;
}
const grindLine = (words) => (words ? `<div class="guide-line plan-grind">${esc(words)}</div>` : "");

window.HOVERS = window.HOVERS || {};
let missingNow = [];
const errandNotesLine = (notes, hidden) => ((notes?.length || hidden?.length) ? foldHtml("epic:notes", "Left out of the plan", [
  ...(notes || []).map((n) => `<div class="guide-line muted">Not planned yet: ${esc(n)}</div>`),
  ...(hidden || []).map((n) => `<div class="guide-line plan-hidden">Hidden by you: ${esc(n)}</div>`)]) : "");
const LATER_OFFERS = {
  level: [["grind", "Grind here", "Finds the best camp for the character's level in the area in view and a loop round the camp"],
          ["zones", "Zone epic", "Shows every zone with quests for the character. Click a zone to plan all of its quests as one epic"]],
  ...Object.fromEntries(["mining", "herbalism", "fishing", "skinning"].map((l) => [l, [[l, "Show on the map",
    `Shows the ${l} layer on the map. The ${l === "skinning" ? "Skin here" : "Gather here"} key under the zone name starts a loop for the character's skill`]]])),
};
function laterHtml(list) {
  if (!list?.length) return "";
  const rows = list.map((e) => `<div class="guide-line">${esc(e.text)}${(LATER_OFFERS[e.offer] || []).map(([what, words, tip]) =>
    ` <button class="key small" data-epic-offer="${what}" title="${esc(tip)}">${words}</button>`).join("")}${emit("laterLine", e).join("")}</div>`);
  return foldHtml("epic:later", "Later", rows);
}
const foldsOpen = new Set(keptOr("cc.folds", []));
const LIST_TIP = "Expands or collapses this list";
const foldHtml = (key, label, rows) => plusFoldHtml(key, "guide-line plan-list", "", `${label}: ${rows.length}`, rows.join(""), LIST_TIP);
function toggleFold(key, box) {
  const open = !foldsOpen.has(key);
  if (open) foldsOpen.add(key); else foldsOpen.delete(key);
  keepIn("cc.folds", [...foldsOpen].filter((k) => !k.startsWith("row:")));
  const fold = box?.closest(".fold"), btn = fold?.querySelector("[data-fold-key]");
  if (!fold) return open;
  fold.classList.toggle("open", open);
  btn.setAttribute("aria-expanded", String(open));
  return open;
}
function laterOffer(what) {
  if (what === "grind") return startGrindLoop();
  if (what === "zones") {
    questsUi.view = "zones";
    keepQuestsView();
    return toggleQuestMenu(true);
  }
  showGatherLayer(what);
}
function plusFoldHtml(key, cls, restAttrs, label, rest, tip = "Expands or collapses the rest of this note") {
  const open = foldsOpen.has(key);
  return `<div class="${cls} fold plus-fold${open ? " open" : ""}" data-fold="${key}"><button class="fold-plus" data-fold-key="${key}" aria-expanded="${
    open}" title="${tip}">${label}</button><div class="fold-more"${restAttrs}>${rest}</div></div>`;
}
function missingLine(list) {
  missingNow = list || [];
  const n = missingNow.length, way = missingNow.filter((x) => x.onWay).length;
  if (!n) return "";
  const names = missingNow.map((x) => `<li>${esc(x.name)}${x.onWay ? ' <span class="epic-missing-way">(on your way)</span>' : ""}</li>`).join("");
  return plusFoldHtml("epic:missing", "guide-line epic-missing", "",
    `<span class="data-missing">No data yet</span> Forever added ${n} quest${n === 1 ? "" : "s"}`,
    `We have no information yet on what opens ${n === 1 ? "the quest" : "these quests"}. ${way ? `The epic picks up ${way} of them on the way if a giver offers ${way === 1 ? "it" : "them"}. ` : ""}The epic leaves ${
      way ? "the rest" : n === 1 ? "that quest" : "those quests"} out, and takes a quest for you when a giver you talk to offers it.<ul class="epic-missing-list">${names}</ul>`);
}

const parkedIds = (live) => new Set(live?.parked || []);
function needsFirst(ps, plan) {
  if (ps.k !== "P") return [];
  const parked = parkedIds(plan.live);
  const handedIn = (id) => {
    const k = plan.steps.findIndex((s) => s.k === "T" && s.ids?.[0] === id);
    return k < 0 ? null : !parked.has(id) && plan.states[k] === "done";
  };
  const open = (ps.any || []).some((p) => handedIn(p) === true);
  return [...(ps.pre || []), ...(open ? [] : ps.any || [])].filter((p) => handedIn(p) === false);
}
function waitsOn(ps, plan) {
  const needs = needsFirst(ps, plan), parked = parkedIds(plan.live);
  const id = needs.find((p) => parked.has(p)) ?? needs[0];
  if (id == null) return null;
  const t = plan.steps.find((s) => s.k === "T" && s.ids?.[0] === id);
  return { id, name: t.name || t.text || STEP_WHY["quest-before"], parked: parked.has(id) };
}
const STEP_WHY = wordsOf("both.step-why");
const whySaid = (key, fill) => ({ key, text: fillWords(STEP_WHY[key], fill) || "" });
const afterWords = (w) => whySaid(w.parked ? "after.parked" : "after", { quest: w.name });
function holdsBack(id, plan) {
  const held = new Set([id]);
  for (let more = true; more;) {
    more = false;
    plan.steps.forEach((s, k) => {
      if (s.k !== "P" || plan.states[k] === "done" || held.has(s.ids?.[0])) return;
      if (needsFirst(s, plan).some((p) => held.has(p))) { held.add(s.ids[0]); more = true; }
    });
  }
  return plan.steps.filter((s) => s.k === "P" && s.ids?.[0] !== id && held.has(s.ids?.[0])).map((s) => s.name || s.text);
}
function parkedQuests(plan) {
  const parked = parkedIds(plan.live), seen = new Set(), out = [];
  for (const s of plan.steps) {
    const id = s.ids?.[0];
    if (s.k === "D" || s.k === "S" || !parked.has(id) || seen.has(id)) continue;
    seen.add(id);
    out.push({ id, name: s.name || s.text, holds: holdsBack(id, plan) });
  }
  return out;
}
function parkedHtml(plan) {
  const parkedNow = parkedQuests(plan);
  if (!parkedNow.length) return "";
  const older = (app.status?.nums?.lineFormat || 0) < UNPARK_FORMAT;
  const title = older ? "The addon in game reads this line after its next /reload. Until then, click the quest's row in the card's Steps list to put the quest back"
    : "Copies the line that puts this quest back in the guide in game. The quest goes back in at once, fitted in from the character's spot";
  const keys = parkedNow.map((q) => `<button class="key small" data-epic-unpark="${q.id}" data-name="${esc(q.name)}"${
    older ? " disabled" : ""} title="${title}">Unpark ${esc(q.name)}</button>`).join("");
  const held = parkedNow.filter((q) => q.holds.length)
    .map((q) => `<div class="guide-line plan-held-back">The parked quest ${esc(q.name)} holds back ${esc(andList(q.holds))}</div>`).join("");
  return plusFoldHtml("epic:parked", "guide-line plan-list plan-parked", "", `Parked: ${parkedNow.length}`, `${held}<div class="guide-cmd">${keys}</div>`, LIST_TIP);
}

const SKIP_FOR_GOOD = new Set(["train", "bind", "flightpath"]);
const CHORE_CODES = { train: 1, sell: 4, repair: 5, restock: 6 };
const putBackLine = (line) => `/ioa guide putback ${line}`;
const putBackOf = (x, k, at) => (x.own ? (CHORE_CODES[x.what] ? `chore ${CHORE_CODES[x.what]} ${x.npcId || 0}` : "")
  : at[k] ? `step ${at[k]}` : "");
const bgSkill = (steps, id) => steps.find((t) => t.ids?.[0] === id && t.sk?.[2])?.sk[2] || "skill";
function putAwayRows(plan, at) {
  const { steps, states } = plan, out = [], gone = (k) => ["done", "skipped"].includes(states[k]);
  const head = (key, fill = {}) => out.push({ head: DirectorRules.line("heads", key, fill) });
  const byHead = new Map();
  steps.forEach((x, k) => {
    if (!plan.putOff.has(x) || gone(k)) return;
    const text = DirectorRules.back("heads", "drawer_later", putOffWhere(x));
    if (!byHead.has(text)) byHead.set(text, []);
    byHead.get(text).push({ text: x.text, back: { kind: "later", steps: [x], spot: x, thing: x.text, line: putBackOf(x, k, at) } });
  });
  for (const [text, rows] of byHead) out.push({ head: text }, ...rows);
  const bg = app.director?.background || [], bgIds = new Set(bg.map((b) => b.quest));
  const questSteps = (id) => steps.filter((t, j) => t.k !== "D" && t.k !== "S" && t.ids?.[0] === id && states[j] === "parked");
  const parked = parkedQuests(plan).filter((q) => !bgIds.has(q.id));
  if (parked.length) head("drawer_parked");
  for (const q of parked) out.push({ text: q.name, back: { kind: "parked", steps: questSteps(q.id), thing: q.name, line: `quest ${q.id}` } });
  if (bg.length) head("drawer_background");
  for (const b of bg) {
    const name = steps.find((t) => t.ids?.[0] === b.quest && t.k !== "S")?.name || `quest ${b.quest}`;
    out.push({ text: DirectorRules.line("heads", "drawer_row_background", { quest: name, skill: bgSkill(steps, b.quest), have: b.have, need: b.need }),
               back: { kind: "background", steps: questSteps(b.quest), thing: name, line: `quest ${b.quest}` } });
  }
  const inLog = (id) => (app.quests?.log || []).some((q) => q.id === id);
  const short = (plan.skillShort || []).map((q) => ({ ...q, have: yourSkills().find((s) => s.name === q.skill)?.rank || 0 }))
    .filter((q) => !bgIds.has(q.id) && inLog(q.id) && q.have < (q.need || 1));
  if (short.length) head("drawer_short");
  for (const q of short) {
    out.push({ text: DirectorRules.line("heads", "drawer_row_background", { quest: q.name, skill: q.skill || "skill", have: q.have, need: q.need }) });
  }
  const skipped = (good) => steps.map((x, k) => [x, k]).filter(([x, k]) => x.k === "S" && states[k] === "skipped" && SKIP_FOR_GOOD.has(x.what) === good)
    .map(([x, k]) => ({ text: x.text, back: { kind: "skipped", steps: [x], thing: x.text, line: putBackOf(x, k, at) } }));
  for (const [good, key] of [[true, "drawer_skipped"], [false, "drawer_skipped_level"]]) {
    const rows = skipped(good);
    if (rows.length) { head(key); out.push(...rows); }
  }
  return out;
}
function putOffWhere(x, spot = x) {
  const at = spot?.at ? spot : x;
  return { town: DirectorRules.town(app.shared?.towns, at?.inst, at?.at?.[0], at?.at?.[1]), npc: at?.npc || x?.npc || null,
           place: placeName(x) || placeName(at) || null };
}
function putBackHow(b, plan, me = playerWorld()) {
  const { steps, states } = plan, moving = new Set(b.steps), run = stretchRun(steps, states);
  const spot = b.spot || b.steps.find((x) => x.at);
  const yards = (x) => (x?.at && spot?.at && x.inst === spot.inst ? Math.hypot(x.at[0] - spot.at[0], x.at[1] - spot.at[1]) : Infinity);
  const npc = spot?.npc || null;
  if (me && spot?.at && spot.inst === me.inst && Math.hypot(spot.at[0] - me.n, spot.at[1] - me.w) <= DirectorRules.reach("back", run)) {
    return { how: "here", npc };
  }
  const leads = (x) => x.k !== "S" || (x.trip != null && !plan.putOff.has(x));
  const n = steps.findIndex((x, k) => states[k] === "todo" && !moving.has(x) && leads(x));
  const move = n >= 0 && b.steps.some((x) => steps.indexOf(x) < n);
  const visit = move ? steps.find((t, k) => k > n && !moving.has(t) && t.k !== "S" && ["todo", "wait"].includes(states[k])
    && yards(t) <= DirectorRules.reach("walked_away", run)) : null;
  return { how: b.kind === "later" || move ? "visit" : "place",
           where: { ...putOffWhere(b.steps[0] || spot, spot), npc: npc || visit?.npc || null } };
}
const PUTBACK_ARROW = `<svg class="putback-arrow" viewBox="0 0 10 10" aria-hidden="true"><path d="M5 1 9.5 6H6.5v3h-3V6H.5z"/></svg>`;
function putAwayHtml(plan, at) {
  const rows = putAwayRows(plan, at);
  if (!rows.length) return "";
  const older = (app.status?.nums?.lineFormat || 0) < PUTBACK_FORMAT, me = playerWorld();
  const html = rows.map((r) => {
    if (r.head) return `<div class="guide-line putaway-head">${esc(r.head)}</div>`;
    if (!r.back) return `<div class="guide-line putaway-row"><span>${esc(r.text)}</span></div>`;
    const w = putBackHow(r.back, plan, me), off = older || !r.back.line;
    const tip = older ? "The addon in game reads this key's line after its next /reload"
      : DirectorRules.back("buttons", `putback_${w.how}_tip`, w.where, { thing: r.back.thing });
    return `<div class="guide-line putaway-row"><button class="key small putback" data-epic-putback="${esc(r.back.line)}" data-name="${
      esc(r.back.thing)}" data-how="${w.how}"${off ? " disabled" : ""} title="${esc(tip)}">${PUTBACK_ARROW}</button><span>${esc(r.text)}</span></div>`;
  }).join("");
  return plusFoldHtml("epic:putaway", "guide-line plan-list", "", `Put away: ${rows.filter((r) => !r.head).length}`,
    `<div class="plan-putaway">${html}</div>`, LIST_TIP);
}

const timerFull = {};
function timersHtml(steps) {
  const limits = {}, mine = new Set();
  for (const s of steps || []) for (const id of s.ids || []) { mine.add(id); if (s.limit) limits[id] = s.limit; }
  const now = Date.now() / 1000;
  return (app.questlog?.entries || []).filter((e) => e.ends && !e.failed)
    .map((e) => ({ e, left: Math.max(0, e.ends - now) }))
    .sort((a, b) => (mine.has(b.e.id) - mine.has(a.e.id)) || a.left - b.left)
    .map(({ e, left }) => {
      const full = timerFull[e.id] = Math.max(timerFull[e.id] || 0, left, limits[e.id] || 0);
      return `<div class="guide-line plan-timer${left < full / 5 ? " late" : ""}" style="--p:${full ? Math.round(left / full * 100) : 0}%">${
        esc(e.title)}: ${questClock(left)}</div>`;
    }).join("");
}

function levelInText(steps, cur, states, pace, play) {
  const s = app.state;
  if (!s?.xpMax || !cur || s.xpMax <= s.xp || (app.maxLevel != null && s.level >= app.maxLevel)) return "";
  let xp = 0, sec = 0, before = 0;
  for (let k = cur - 1; k < steps.length; k++) {
    if (!["todo", "wait"].includes(states[k] || "todo")) continue;
    xp += steps[k].xp || 0; sec += steps[k].sec || 0;
    if (steps[k].xp && xp >= s.xpMax - s.xp) {
      if (!DirectorRules.said("reckoned", before, play)) return "";
      const m = Math.round(sec * (pace || 1) / 60);
      return `Level ${s.level + 1} in ${m < 1 ? "under a minute" : m < 60 ? `about ${m} min` : `about ${Math.floor(m / 60)} h ${m % 60} min`}`;
    }
    before++;
  }
  return "";
}

const planNext = (steps, states) => steps.findIndex((x, k) => x.k !== "S" && states[k] === "todo") + 1;
function stretchRun(steps, states) {
  const lengths = [], from = Math.max(1, planNext(steps, states)), most = DirectorRules.table.run.steps + 1;
  let prev = null, n = 0;
  for (let k = from - 1; k < steps.length && n < most; k++) {
    const x = steps[k];
    if (x.own) continue;
    n++;
    if (!x.at) continue;
    if (prev && prev.inst === x.inst) lengths.push(Math.hypot(x.at[0] - prev.at[0], x.at[1] - prev.at[1]));
    prev = x;
  }
  return DirectorRules.run(lengths);
}
function alongYards(x, me) {
  if (!me || !x.at || x.inst !== me.inst) return Infinity;
  const p = [me.n, me.w], ring = x.loop || x.walk;
  let d = Math.hypot(x.at[0] - p[0], x.at[1] - p[1]);
  if (ring?.length > 1) [...ring, ring[0]].forEach((b, k, r) => { if (k) d = Math.min(d, segDist(p, r[k - 1], b)); });
  return d;
}
function alongSteps(steps, from, states, me = playerWorld(), at = steps.map((_, k) => k + 1)) {
  const key = (x) => `${x.ids?.[0] ?? ""}\n${x.target || x.text}`, shown = steps[from - 1], out = [];
  if (!shown?.at || !me || shown.inst !== me.inst) return out;
  const seen = new Set(), leg = new Set(shown.al || []);
  steps.forEach((x, k) => {
    if (k === from - 1 || x.k !== "O" || states[k] !== "todo" || seen.has(key(x)) || !x.at || x.inst !== me.inst) return;
    if (DirectorRules.onCard(shown.k, shown.ids, x.k, x.ids?.[0])) return;
    if (leg.has(at[k]) || DirectorRules.spawnedNear(x.sp, me.n, me.w)) {
      seen.add(key(x));
      out.push({ x, d: alongYards(x, me), k });
    }
  });
  return out.sort((a, b) => a.d - b.d || a.k - b.k).map((c) => c.x);
}
function alongHtml(steps, from, states, at) {
  const rows = alongSteps(steps, from, states, playerWorld(), at)
    .map((x) => {
      const left = alongObjective(x)?.o;
      return `<div class="guide-line plan-along">${stepIcon(x)} ${
        left ? itemNamed(left.text, left.item, left.itemName) : esc(x.text)}</div>`;
    });
  return rows.length ? plusFoldHtml("epic:along", "guide-line plan-list plan-along", "", `Along the way: ${rows.length}`,
    `<div class="plan-along-list">${rows.join("")}</div>`, LIST_TIP) : "";
}

function parkedWait(ps, live, plan = null) {
  const id = ps.ids?.[0];
  if (ps.k === "P") {
    if (live?.notOffered?.includes(id)) return null;
    const w = plan && waitsOn(ps, plan);
    return w ? afterWords(w) : (ps.min || 0) > (app.state?.level || 0) ? whySaid("level", { level: ps.min }) : null;
  }
  if ((app.questlog?.entries || []).some((e) => e.id === id && e.failed)) return null;
  const held = (app.quests?.log || []).find((q) => q.id === id);
  if (!held) return whySaid("pickup");
  if ((ps.min || 0) > (app.state?.level || 0)) return whySaid("level", { level: ps.min });
  const skill = skillShort(ps);
  if (skill) return whySaid("skill", skill);
  return ps.k === "T" && !held.complete ? whySaid("objectives") : null;
}
function skillShort(ps) {
  const id = ps.ids?.[0];
  if (!(ps.k === "T" || (ps.k === "O" && !ps.get)) || !(app.quests?.log || []).some((q) => q.id === id)) return null;
  const objs = logObjectives(id), own = ps.k === "O" ? stepObjective(ps, objs) : -1;
  for (const o of own >= 0 ? [objs[own]] : objs) {
    const text = (o.text || "").toLowerCase();
    const sk = !o.finished && yourSkills().find((s) => s.name && text.includes(`${s.name.toLowerCase()} skill`));
    const need = sk && rankAsked(text, sk.name);
    if (need && sk.rank < need) return { skill: sk.name, rank: need };
  }
  return null;
}
const yourSkills = () => [...(app.professions || []), ...(app.state?.skills || [])];
function rankAsked(text, name) {
  const lower = (text || "").toLowerCase(), at = name ? lower.indexOf(`${name.toLowerCase()} skill`) : -1;
  const m = at >= 0 && /^\D*(\d+)/.exec(lower.slice(at + name.length + 6));
  return m ? +m[1] : null;
}
function canBackground(ps, plan) {
  const id = ps.ids?.[0], [, rank, name] = ps.sk || [];
  if (!id || !name || ps.k === "D" || ps.k === "S") return false;
  if ((app.director?.background || []).some((b) => b.quest === id) || parkedIds(plan?.live).has(id)) return false;
  if ((app.quests?.log || []).some((q) => q.id === id && q.complete)) return false;
  const asked = logObjectives(id).map((o) => rankAsked(o.text, name)).find(Boolean);
  return (yourSkills().find((s) => s.name === name)?.rank || 0) < (asked || rank || 1);
}
const backgroundLine = (id) => `/ioa guide background ${id}`;
function backgroundKey(x, st, plan) {
  if ((st !== "todo" && st !== "wait") || !canBackground(x, plan)) return "";
  const older = (app.status?.nums?.lineFormat || 0) < BACKGROUND_FORMAT;
  const tip = older ? "The addon in game reads this key's line after its next /reload" : DirectorRules.line("buttons", "background_copy_tip");
  return `<div class="guide-cmd"><button class="key small" data-epic-background="${x.ids[0]}" data-name="${esc(x.name || x.text)}"${
    older ? " disabled" : ""} title="${esc(tip)}">${esc(DirectorRules.line("buttons", "background"))}</button></div>`;
}
const GROUP_TAG = ` <span class="plan-group">(group quest)</span>`;
const parkLine = (id) => `/ioa guide park ${id}`;
function groupHtml(s, state) {
  if (app.group?.members?.length || state === "parked") return `<div class="guide-line plan-group">Group quest</div>`;
  if ((app.status?.nums?.lineFormat || 0) < PARK_FORMAT) {
    return `<div class="guide-line plan-group">This is a group quest. Park it on the card if you're on your own</div>`;
  }
  return `<div class="guide-line plan-group">This is a group quest. Park it if you're on your own</div>
    <button class="key small" data-epic-park="${s.ids[0]}" data-name="${esc(s.name || s.text)}"
      title="Copies the line that parks this quest in game, as Park on the card does. The guide comes back to the quest once the rest is done">Park it</button>`;
}
function takesFrom(s, t) {
  if (s.k !== "S" || t.k !== "S" || !s.takes || typeof s.takes !== "object" || !t.need || typeof t.need !== "object") return false;
  const got = { items: new Set((t.need.items || []).filter((row) => row?.length).map((row) => String(row[0]))),
                recipes: new Set((t.need.recipes || []).map(String)),
                skills: new Set((t.need.skills || []).filter((row) => row?.[1] === 1).map((row) => String(row[0]))) };
  return Object.entries(got).some(([kind, have]) => (s.takes[kind] || []).some((v) => have.has(String(v))));
}
function stepWhy(ps, state, live, plan = null) {
  if (state === "parked") {
    const wait = parkedWait(ps, live, plan);
    return wait?.text ? whySaid("parked.waiting", { why: wait.text }) : whySaid("parked");
  }
  if (state === "skipped") return whySaid("skipped");
  if (state === "blocked") {
    return ps.k !== "P" ? whySaid("failed") : ps.npc ? whySaid("not-offered", { npc: ps.npc }) : whySaid("not-offered.giver");
  }
  if (plan?.putOff?.has(ps)) return { key: null, text: DirectorRules.back("words", "put_off", putOffWhere(ps)) || "" };
  if (state !== "wait") return null;
  if (ps.k === "P") {
    const w = plan && waitsOn(ps, plan);
    return w ? afterWords(w) : ps.min ? whySaid("level", { level: ps.min }) : null;
  }
  if (ps.k === "D") return whySaid("run");
  if (ps.k === "S") {
    const from = plan?.steps?.find((t, k) => t !== ps && ["todo", "wait"].includes(plan.states[k]) && takesFrom(ps, t));
    if (from) return whySaid("takes", { step: from.text });
    const pay = ps.need?.pay;
    if (ps.min && !(pay && (app.state?.level || 0) >= ps.min)) return whySaid("level", { level: ps.min });
    return pay ? whySaid("money", { money: moneyText(pay) }) : null;
  }
  const held = (app.quests?.log || []).some((q) => q.id === ps.ids[0]);
  if (held && (ps.min || 0) > (app.state?.level || 0)) return whySaid("level", { level: ps.min });
  const skill = skillShort(ps);
  if (skill) return whySaid("skill", skill);
  return ps.k === "T" && held ? whySaid("objectives") : whySaid("pickup");
}
function whyLine(s, state, cur, live, plan = null) {
  const why = cur && state === "parked" ? DirectorRules.line("words", "back") : stepWhy(s, state, live, plan)?.text;
  if (!why) return "";
  const line = state === "wait" ? whySaid("waiting", { why }).text
    : state === "blocked" ? whySaid("blocked", { why }).text : why[0].toUpperCase() + why.slice(1);
  return `<div class="guide-line plan-why ${state}">${esc(line)}</div>`;
}
const onHold = (x, st) => st === "blocked" || st === "parked" || (st === "wait" && (x.min || 0) > (app.state?.level || 0));
function stepTag(x, st) {
  if (st === "blocked") return "Blocked";
  if (st === "parked") return "Parked";
  if (st === "skipped") return "Skipped";
  return onHold(x, st) ? `Level ${x.min}` : "";
}
const ORDER_WAITS = new Set(["pickup", "objectives", "run"]);
function stepDetail(x, st, why, plan = null) {
  const said = why?.text && st !== "skipped" && !(st === "wait" && ORDER_WAITS.has(why.key)) ? why.text : "";
  return [said && `<span class="plan-step-why">${esc(said[0].toUpperCase() + said.slice(1))}</span>`,
    x.mv && `<span class="plan-step-why">${esc(x.mv)}</span>`, blurbUnder(x), plan?.live && !plan.inspect && backgroundKey(x, st, plan)]
    .filter(Boolean).join("");
}
const unparkLine = (id) => `/ioa guide unpark ${id}`;
const blurbUnder = (x) => (x.k === "P" && x.bl ? `<span class="plan-blurb">${esc(x.bl)}</span>` : "");
const STEP_TICK = `<span class="step-mark tick" aria-label="Done">✓</span>`;
const STEP_ARROW = `<span class="step-mark here" aria-hidden="true">▶</span>`;
const UNPARK_TIP = "This quest is parked and still to do. A click copies the line that puts the quest back in game, as a click on its row on the card does. The quest goes back in at once, fitted in from the character's spot";
const PICK_TIP = "Shows this step of the plan on the map and in this panel";
function stepRow(x, state, live, lit, plan = null, k = 0) {
  const st = state || "todo", detail = stepDetail(x, st, stepWhy(x, state, live, plan), plan);
  const key = `row:${x.k}:${x.ids?.[0] ?? ""}:${x.text}`, open = !!detail && foldsOpen.has(key);
  const cls = `st-${st}${onHold(x, st) ? " hold" : ""}${lit ? " cur" : ""}${detail ? ` fold${open ? " open" : ""}` : ""}`;
  const mark = lit ? STEP_ARROW : st === "done" ? STEP_TICK : `<span class="step-mark"></span>`;
  const tag = lit && !plan?.inspect ? `<span class="step-tag here">You are here</span>` : stepTag(x, st) ? `<span class="step-tag">${stepTag(x, st)}</span>` : "";
  const more = detail ? `<button class="fold-plus step-more" data-fold-key="${esc(key)}" aria-expanded="${open}" title="Expands or collapses more about this step"></button>` : "";
  const text = `${esc(x.text)}${x.grp ? GROUP_TAG : ""}`, unpark = st === "parked" && (app.status?.nums?.lineFormat || 0) >= UNPARK_FORMAT;
  const words = plan?.inspect ? `<button class="step-words" data-epic-pick="${k - 1}" title="${PICK_TIP}">${text}</button>`
    : unpark ? `<button class="step-words" data-epic-unpark="${x.ids[0]}" data-name="${esc(x.name || x.text)}" title="${UNPARK_TIP}">${text}</button>`
    : `<span class="step-words">${text}</span>`;
  const tip = st === "parked" && !unpark ? ` title="This quest is parked and still to do. Click its row in the card's Steps list to put the quest back"` : "";
  return `<li class="${cls}"${detail ? ` data-fold="${esc(key)}"` : ""}${tip}><div class="step-line">${mark}${stepIcon(x)}${words}${classQuestTag(x)}${tag}${more}</div>${
    detail ? `<div class="fold-more">${detail}</div>` : ""}</li>`;
}
const STEPS_WORDS = {
  all: "All steps",
  allTip: "Shows every step of the epic in order",
  held: "Steps on hold",
  heldTip: "Shows only the steps on hold: the ones blocked, parked or waiting for a level",
  foldTip: "Collapses this list of steps",
  none: "No step is on hold now",
};
const STEPS_LISTS = ["", "all", "held"];
let stepsShown = STEPS_LISTS.includes(keptOr("cc.epicSteps", "")) ? keptOr("cc.epicSteps", "") : "";
function showSteps(which) {
  stepsShown = which === stepsShown || !STEPS_LISTS.includes(which) ? "" : which;
  keepIn("cc.epicSteps", stepsShown);
  renderTracks();
}
function stepsHtml(steps, states, cur, shown, live, plan = { steps, states, live }) {
  const rows = steps.map((x, k) => [x, states[k], k + 1]), held = rows.filter(([x, st]) => onHold(x, st));
  const now = stepsShown === "held" && !held.length ? "" : stepsShown;
  const listed = (now === "all" ? rows : now === "held" ? held : []).map(([x, st, k]) => stepRow(x, st, live, k === cur, plan, k)).join("");
  const key = (which, label, tip, off = false) => `<button class="key small plan-steps-key" data-epic-steps="${which}" aria-pressed="${
    now === which}"${off ? " disabled" : ""} title="${off ? STEPS_WORDS.none : now === which ? STEPS_WORDS.foldTip : tip}">${label}</button>`;
  return `<div class="guide-cmd plan-steps-cmd">${key("all", STEPS_WORDS.all, STEPS_WORDS.allTip)}${
    key("held", STEPS_WORDS.held, STEPS_WORDS.heldTip, !held.length)}</div>
    ${listed ? `<ol class="track-next ${now === "all" ? "plan-steps" : "plan-held"}">${listed}</ol>` : ""}`;
}
function setStepsHtml(body, html) {
  const was = body.querySelector(".plan-steps")?.scrollTop;
  if (!setHtml(body, html)) return;
  const list = body.querySelector(".plan-steps"), cur = list?.querySelector("li.cur");
  if (list && was != null) list.scrollTop = was;
  else if (cur) list.scrollTop = Math.max(0, cur.offsetTop - 2 * cur.offsetHeight);
}
function planProgress(steps, states, cur, live, g, before = 0) {
  const done = before + (live ? states.filter((x) => x === "done").length : (g?.done ?? 0));
  const all = before + steps.length - states.filter((x) => x === "skipped").length;
  const d = steps.findIndex((x) => x.k === "D") + 1;
  const stage = !cur ? null : !d || cur < d ? "prep" : cur > d ? "turnin" : app.state?.flags?.instance ? "inside" : "travel";
  const share = (from, to) => {
    const ks = states.map((x, i) => [x, i + 1]).filter(([x, i]) => i >= from && i <= to && x !== "skipped");
    return ks.length ? ks.filter(([x]) => x === "done").length / ks.length : 0;
  };
  const fills = { prep: d ? share(1, d - 1) : share(1, steps.length), travel: stage === "inside" || stage === "turnin" ? 1 : 0,
                  inside: d && states[d - 1] === "done" ? 1 : 0, turnin: d ? share(d + 1, steps.length) : 0 };
  return { done, all, d, stage, fills };
}
function runOrder(steps, states, cur, moves = [], chores = []) {
  const placed = new Map(), front = new Map(), at = [];
  for (const m of moves || []) if (m.step > 0 && m.step <= steps.length) placed.set(m.step, m);
  if (!placed.size) return ownChores({ steps, states, cur, at: steps.map((_, k) => k + 1) }, chores);
  for (const m of placed.values()) {
    const key = m.before && m.before <= steps.length && !placed.has(m.before) ? m.before : 0;
    front.set(key, [...(front.get(key) || []), m.step]);
  }
  steps.forEach((_, k) => { if (!placed.has(k + 1)) at.push(...(front.get(k + 1) || []), k + 1); });
  at.push(...(front.get(0) || []));
  return ownChores({ steps: at.map((n) => steps[n - 1]), states: at.map((n) => placed.get(n)?.state ?? states[n - 1]),
                     cur: cur ? at.indexOf(cur) + 1 : 0, at }, chores);
}
function ownChores(run, chores) {
  if (!chores?.length) return run;
  const steps = [...run.steps], states = [...run.states], at = [...run.at];
  let lead = run.cur ? steps[run.cur - 1] : null;
  for (const c of chores) {
    if (!c.step) continue;
    const k = c.before ? at.indexOf(c.before) : -1;
    const i = k < 0 ? steps.length : k;
    const step = c.putOff || c.npc ? { ...c.step, ...(c.putOff ? { putOff: true } : {}), ...(c.npc ? { npcId: c.npc } : {}) } : c.step;
    steps.splice(i, 0, step);
    states.splice(i, 0, c.state || "todo");
    at.splice(i, 0, 0);
    if (c.lead) lead = step;
  }
  return { steps, states, at, cur: lead ? steps.indexOf(lead) + 1 : 0 };
}
const shownStep = (states, cur) => cur || states.findIndex((x) => x === "wait" || x === "blocked") + 1
  || states.findIndex((x) => x === "parked") + 1;
const USE_ARROWS = {
  1: { line: "M84 34Q45-6 6 30", head: "M13.7 28L6 30 8.5 22.4" },
  2: { line: "M6 30Q45-6 84 34", head: "M81.8 26.3L84 34 76.4 31.6" },
};
const HEARTH = { item: 6948, cast: 20, detour: 1.25, run: 7, far: 600 };
function hearthSaves(s, me) {
  const h = s.hearth, at = (a, b) => Math.hypot(a[0] - b[0], a[1] - b[1]) * HEARTH.detour / HEARTH.run;
  const inn = h.i === s.inst ? at(h.at, s.at) : HEARTH.far;
  const you = me && me.inst === s.inst ? at([me.n, me.w], s.at) : HEARTH.far;
  return Math.min(you, HEARTH.far) - Math.min(inn, HEARTH.far) - HEARTH.cast;
}
function classIconHtml() {
  const cls = CLASS_ICONS[app.status?.classId];
  return cls ? `<img class="ui-icon class-icon" src="/icon/classicon_${cls}.jpg" alt="">` : "";
}
function classQuestTag(x) {
  if (!x?.cq) return "";
  const col = CLASS_COLORS[app.status?.className];
  return `<span class="step-tag class-quest"${col ? ` style="color:${esc(col)}"` : ""}>${classIconHtml()}${esc(DirectorRules.line("heads", "class_quest"))}</span>`;
}
function tripHtml(s, leading) {
  const out = [];
  const cq = s?.cq ? `<div class="guide-line plan-trip plan-class">${classIconHtml()} ${esc(DirectorRules.line("heads", "class_quest"))}</div>` : "";
  if (s?.why) out.push(s.why);
  if (leading && s?.hearth && app.status?.nums?.epicItem === HEARTH.item) {
    const n = Math.max(1, Math.round(hearthSaves(s, playerWorld()) / 60));
    out.push(DirectorRules.say(n === 1 ? "hearth_one" : "hearth", { town: s.hearth.t, n }));
  }
  return cq + out.filter(Boolean).map((line) => `<div class="guide-line plan-trip">${esc(line)}</div>`).join("");
}
function useItemHtml() {
  const n = app.status?.nums || {}, id = n.epicItem;
  if (!id) return "";
  wantItemInfo([id], () => renderTracks());
  const it = app.itemInfo?.[id], use = USE_ARROWS[n.epicUse] ? n.epicUse : 0;
  const a = USE_ARROWS[use];
  const arrow = a ? `<svg class="use-arrow seen-only" viewBox="0 0 90 40" aria-hidden="true"><path id="use-words" d="${USE_ARROWS[2].line}" fill="none"/>`
    + `<path class="use-line" pathLength="100" d="${a.line}"/><path class="use-head" d="${a.head}"/><text dy="-5">`
    + `<textPath href="#use-words" startOffset="50%" text-anchor="middle">Use this</textPath></text></svg>` : "";
  return `<span class="plan-useitem${use === 2 ? " lit" : ""}" data-tip="${esc(id)}">${arrow}<img src="/icon/${
    esc(it?.icon || "inv_misc_questionmark")}.jpg" alt="${esc(it?.n || "")}"></span>`;
}
const QT_ICON = "inv_misc_note_01";
const epicTexts = {}, epicTextsAsked = new Set();
let epicTextOpen = null;
const textQuest = (s) => (["P", "O", "T"].includes(s?.k) ? s.ids?.[0] ?? null : null);
function epicText(id) {
  if (id == null) return null;
  if (!(id in epicTexts) && !epicTextsAsked.has(id)) {
    const asked = getJson(`/api/questtext?ids=${id}`);
    if (asked) {
      epicTextsAsked.add(id);
      asked.then((d) => { epicTexts[id] = d?.[id] || null; renderTracks(); }, () => epicTextsAsked.delete(id));
    }
  }
  return epicTexts[id];
}
function questTextIcon(s) {
  const id = textQuest(s), t = epicText(id);
  if (!t || !(t.todo || t.text)) return "";
  const open = epicTextOpen?.id === id;
  return `<button class="plan-qt" data-epic-text="${id}" data-name="${esc(s.name || s.text)}" aria-expanded="${open}" title="Quest text. ${
    open ? "Click to close the quest's text" : "Click to read the quest's full text"}"><img src="/icon/${QT_ICON}.jpg" alt="Quest text"></button>`;
}
function toggleEpicText(id, name) {
  epicTextOpen = epicTextOpen?.id === id || id == null ? null : { id, name };
  renderTracks();
}
function drawQuestText() {
  const panel = $("track-epic"), o = epicTextOpen, t = o && epicTexts[o.id];
  let box = $("epic-qt");
  if (!o || !t || !panel || panel.hidden) {
    if (box) box.hidden = true;
    return;
  }
  if (!box) {
    box = document.createElement("div");
    box.id = "epic-qt";
    box.className = "epic-qt";
    box.addEventListener("pointerdown", (e) => { if (e.button === 0 && e.target.closest("[data-epic-text-close]")) toggleEpicText(null); });
    document.body.appendChild(box);
  }
  const rows = t.game ? (questEntry(o.id)?.objectives || []).map((x) => x.text).filter(Boolean) : [];
  const html = `<div class="epic-qt-head"><span class="epic-qt-title">${esc(o.name)}${t.game ? "" : ` <span class="epic-qt-not">(not picked up yet)</span>`}</span>
    <button class="epic-qt-x" data-epic-text-close title="Closes the quest's text">x</button></div>
    <div class="epic-qt-body${t.game ? "" : " dimmed"}">${t.todo ? `<div class="epic-qt-label">Quest objectives</div><p>${esc(t.todo)}</p>` : ""}${
      rows.length ? `<p>${rows.map(esc).join("<br>")}</p>` : ""}${t.text ? `<div class="epic-qt-label">Description</div><p>${esc(t.text)}</p>` : ""}
    <p class="epic-qt-src">${t.game ? "The game's text from your quest log." : "This quest isn't in your log. The text comes from the Index's quest data."}</p></div>`;
  if (box.dataset.html !== html) { box.innerHTML = html; box.dataset.html = html; }
  box.hidden = false;
  const at = slidePlace(panel.getBoundingClientRect(), box.offsetWidth, box.offsetHeight);
  box.style.top = `${Math.round(at.y)}px`;
  box.style.left = `${Math.round(at.x)}px`;
}
document.addEventListener?.("keydown", (e) => { if (e.key === "Escape" && epicTextOpen) toggleEpicText(null); });
function stepMoreHtml(s, state, cur, live, plan, said, ahead = false) {
  const rest = [s.bl ? `<div class="guide-line plan-blurb">${esc(s.bl)}</div>` : "",
    said ? `<div class="guide-line plan-why todo">${esc(said)}</div>` : ahead ? "" : whyLine(s, state, cur, live, plan)].join("");
  return rest ? plusFoldHtml("epic:step-more", "guide-line plan-step-more", "", "Details", rest) : "";
}
function stepShownTag(s, state, lit) {
  if (lit && state !== "parked" && state !== "blocked") return "";
  const tag = stepTag(s, state) || (state === "wait" ? "Waiting" : "");
  return tag ? ` <span class="step-tag ${state}${onHold(s, state) ? " hold" : ""}">${tag}</span>` : "";
}
function epicPlanHtml(t, head, where, way = "", src = shownPlan(t), legRow = "") {
  const { p, g, inspect } = src, live = g?.states ? g : null;
  const { steps, states, cur, at } = runOrder(p.steps, live?.states || [], g?.cur || 0, live?.moves, live?.chores);
  const plan = { steps, states, live, inspect, skillShort: p.skillShort,
                 putOff: new Set(steps.filter((x, k) => x.k === "S" && (x.putOff || (live?.putOff || []).includes(at[k])))) };
  const newer = newerPlan(t);
  const { done, all, d, stage, fills } = planProgress(steps, states, cur, live, g, inspect ? 0 : app.status?.nums?.epicBefore || 0);
  const stages = [["prep", "Prep"], ["travel", "Travel"], ["inside", "Inside"], ["turnin", "Turn in"]].map(([k, name]) =>
    `<span class="${k === stage ? "on" : ""}" style="--p:${Math.round((fills[k] || 0) * 100)}%">${name}</span>`).join("");
  const i = inspect ? pickedStep(t) + 1 : shownStep(states, cur);
  const extra = handInStep(p, steps, g, cur);
  const handing = g?.handIn && (extra || steps[cur - 1]?.ids?.[0] === g.handIn);
  const back = handing && !extra ? states.findIndex((x) => x === "todo") : -1;
  const s = extra || (i ? steps[i - 1] : null), state = extra ? "todo" : s ? states[i - 1] : null;
  const said = s && (extra || (cur && i === cur)) ? leadLine(g, steps, at, s) : "";
  if (epicTextOpen && textQuest(s) !== epicTextOpen.id) epicTextOpen = null;
  let who = !s ? "" : s.k === "P" || s.k === "T" ? esc(s.npc || "") : s.k === "D" ? `${s.ids.length} quest${s.ids.length === 1 ? "" : "s"} inside`
    : (s.mobs || []).map((n, k) => esc(n) + (s.lv ? ` ${mobLevelHtml(stepMobLevels(s, k))}` : "")).join(", ") || esc(s.target || "");
  const along = s ? alongSteps(steps, i, states, playerWorld(), at) : [], colours = rowColours(s, steps, along);
  let objs = objectivesHtml(s, colours);
  const named = s?.k === "O" && (s.mobs?.length ? s.mobs : [s.target]).filter(Boolean);
  if (named?.length && objs && named.every((n) => objs.includes(esc(n)))) [who, objs] = ["", objectivesHtml(s, colours, true)];
  const have = app.status?.nums?.money;
  const cost = s?.k === "S" && s.cost ? `costs ${money(s.cost)}${have != null
    ? `, <span class="${have < s.cost ? "have-short" : "have-enough"}">you have ${money(have)}</span>` : ""}` : "";
  const run = app.run, same = run?.inside && (run.key === p.key
    || (dungeon.byKey[p.key]?.instance != null && dungeon.byKey[p.key].instance === dungeon.byKey[run.key]?.instance));
  const det = same ? dungeonDetail(p.key) : null;
  let bosses = "", bossWhere = "";
  if (s?.k === "D" && s.bosses && det) {
    const index = Object.fromEntries(det.bosses.map((b, n) => [b.name, n + 1])), kills = runKills(p.key);
    let found = false, down = 0;
    bosses = s.bosses.map((b) => {
      const isDown = kills.includes(index[b.n]), now = !isDown && !found;
      found ||= !isDown; down += isDown ? 1 : 0;
      const lv = index[b.n] ? ` <small>${mobLevelHtml(det.bosses[index[b.n] - 1].levels)}</small>` : "";
      return `<li class="${isDown ? "down" : now ? "now" : ""}">${esc(b.n)}${lv}${b.q ? `<span>${esc(b.q.join(", "))}</span>` : ""}</li>`;
    }).join("");
    bossWhere = `Inside, ${down} of ${s.bosses.length} bosses down`;
  }
  const next = [], nextLine = (st) => `<div class="guide-line">${stepIcon(st)} ${esc(nextWords(st))}${st.grp ? GROUP_TAG : ""}</div>`;
  const alongNow = new Set(along);
  const onCard = (st) => alongNow.has(st) || Boolean(s && DirectorRules.onCard(s.k, s.ids, st.k, st.ids?.[0]));
  const thenAt = g?.then && (extra || (cur && i === cur)) ? at.indexOf(g.then) : -1;
  if (thenAt >= 0 && (extra || thenAt !== i - 1) && !onCard(steps[thenAt])) next.push(nextLine(steps[thenAt]));
  for (let k = extra ? Math.max(0, i - 1) : back >= 0 && back < i - 1 ? back : i; k < steps.length && next.length < 2; k++) {
    if (k === thenAt || (!extra && k === i - 1) || (states.length && !["todo", "wait"].includes(states[k])) || onCard(steps[k])) continue;
    next.push(nextLine(steps[k]));
  }
  const level = levelInText(steps, cur, states, live?.pace, live?.play);
  const over = !s && done >= all;
  return `${head}<div class="guide-name">${esc(p.name || t.name)}</div>${epicWorking(t)}
    <div class="guide-line plan-count">${done} of ${all} steps done</div>
    ${level ? `<div class="guide-line muted">${level}</div>` : ""}
    ${live?.cardHidden ? `<div class="guide-line muted">The epic's card is hidden in game. Click the add-on button or the blue arrow, or type /ioa guide, to show the card again</div>` : ""}
    ${newer ? newerPlanHtml(newer) : ""}
    ${inspect ? "" : directorLeftHtml()}
    ${waysLine(t)}${unbuiltLine(t)}
    ${d ? `<div class="plan-stages">${stages}</div>` : ""}
    ${legRow}
    ${s ? `<div class="plan-verb">${cur && i === cur ? useItemHtml() : ""}${stepIcon(s)} ${esc(planVerb(s))}${extra ? "" : stepShownTag(s, state, cur && i === cur)}</div>
      <div class="guide-line plan-step-name">${questTextIcon(s)}<b>${esc(s.name || s.text)}</b></div>
      ${s.grp ? groupHtml(s, states[i - 1]) : ""}
      <div class="guide-line">${[who, esc([bossWhere || (cur && s.at ? where : ""), bossWhere ? "" : s.zone].filter(Boolean).join(" | ")), cost]
        .filter(Boolean).join(" | ")}</div>
      ${cur && s.at && !bossWhere ? way : ""}
      ${s.mv ? `<div class="guide-line plan-moves">${esc(s.mv)}</div>` : ""}
      ${(s.careful || "").split("; ").filter(Boolean).map((m) => `<div class="guide-line plan-careful">${
        planIcon("warning", "Careful")} ${esc(m)}</div>`).join("")}
      ${bosses ? `<ol class="plan-bosses">${bosses}</ol>` : ""}
      ${tripHtml(s, !!cur && i === cur)}
      ${objs}
      ${stepMoreHtml(s, state, cur, live, plan, said, Boolean(handing))}`
      : done >= all ? `<div class="guide-line"><b>All done</b></div>${nextChainsHtml(p)}`
      : `<div class="guide-line muted">The epic has nothing for you to do right now</div>`}
    ${timersHtml(steps)}
    ${s ? alongHtml(steps, i, states, at) : ""}
    ${inspect ? "" : partyLine()}
    ${next.length ? `<div class="plan-next"><span class="plan-next-label">Next</span><div>${next.join("")}</div></div>` : ""}
    ${over ? "" : `${grindLine(grindWords(steps, states, cur, live))}
    ${missingLine(p.missing)}
    ${errandNotesLine(p.notes, p.hidden)}`}
    ${laterHtml(p.later)}
    ${materialsHtml(t)}
    ${live ? parkedHtml(plan) : ""}
    ${live ? putAwayHtml(plan, at) : ""}
    ${live || inspect ? stepsHtml(steps, states, inspect ? i : cur, i, live, plan) : ""}`;
}
function refreshShared() {
  const asked = getJson("/api/shared");
  if (!asked) {
    if (!askWait("/api/shared")) setTimeout(refreshShared, 500);
    return;
  }
  asked.then((sh) => {
    const was = app.shared?.version;
    app.shared = sh;
    if (app.tracks?.epic?.data) askShared(app.tracks.epic);
    if (sh.working) return setTimeout(refreshShared, 2000);
    if (sh.version && was !== sh.version && sharedToast && sh.epic) {
      sharedToast = false;
      showToast(`The plan for ${sh.epic.name || "the quest epic"} is ready for the addon. Type /reload in game to load the epic's guide`);
    }
  }, () => setTimeout(refreshShared, askWait("/api/shared")));
}
function askShared(t) {
  const steps = (t.data?.steps || []).filter((s) => s.at && epicCode(s)), sh = app.shared;
  if (!t.startedAt || t.planAsked || planWritten(t) || !sh || !steps.length) return;
  const sig = `${t.key}|${t.startedAt || ""}|${steps.map((s) => epicCode(s)).join(";")}`;
  if (sharedAsked === sig) return;
  const mode = trackMode(t);
  const asked = postJson("/api/shared/epic", { key: t.key, anchor: t.anchor, mode, close: !!t.close, parked: t.keepParked || [],
    click: t.startedAt, again: !!t.startSent }, { key: "shared epic" });
  if (!asked) return;
  t.startSent = true;
  sharedAsked = sig;
  asked.then((r) => {
    if (!r?.started) {
      if (sharedAsked === sig) sharedAsked = "";
      setTimeout(() => { if (app.tracks.epic === t) askShared(t); }, SHARED_AGAIN_MS);
      return;
    }
    t.planAsked = true; sharedToast = true; setTimeout(refreshShared, 1500);
    if (trackMode(t) !== mode) askEpicMode(t, true);
  }, () => {
    if (sharedAsked === sig) sharedAsked = "";
    renderTracks();
  });
}
const planAsks = () => (app.shared ? ["shared epic"] : ["shared epic", "/api/shared"]);
const planAskFailed = () => planAsks().some((k) => askState(k)?.error);
function planNote(t) {
  const broke = planBroke(t);
  if (!t.startedAt || planWritten(t) || !(broke || planAskFailed())) return "";
  return `<div class="guide-line">${askNote(planAsks(), { what: "the epic's plan written for the game",
    why: broke ? "the Index ran into an error while writing it" : null,
    again: () => {
      if (broke) { t.brokeBefore = app.plan.broke.at; t.planAsked = false; sharedAsked = ""; }
      refreshShared(); askShared(t); renderTracks();
    } })}</div>`;
}

const WAY_WORDS = { safe: "the safest route, to roads and well clear of mobs", fight: "the grinding route, through the mobs worth fighting",
  any: "the quickest route round the mobs" };
function askEpicMode(t, quiet = false) {
  const mode = trackMode(t), way = `Quest epic: ${WAY_WORDS[mode]}`, say = (words) => quiet || showToast(words);
  const none = `${way}. The epic has no plan in game yet. A Re-plan writes one that way`;
  if (t.startedAt && !t.planAsked) return say(`${way}. The Index is writing the epic's plan for the game that way`);
  if (!t.planAsked && !(app.plan?.key === t.key && planIsMine(app.plan))) return say(none);
  postJson("/api/shared/mode", { key: t.key, mode }).then(({ asked }) => {
    const lp = loadedPlan()?.epic;
    say(!asked ? none : lp?.key === t.key && (lp.mode || "any") === mode ? `${way}, as the epic's plan in game has it`
      : `${way}. The blue arrow in game takes the new route after a /reload, once the reload prompt asks for one`);
  }, (e) => quiet || askFailed("The epic's plan in game keeps its old route", e));
}
function makingLine(t) {
  const p = app.plan, g = p?.progress;
  if (!g || g.key !== t.key || !g.of) return "";
  const none = g.unbuilt ? `. ${num(g.unbuilt)} step${g.unbuilt === 1 ? " has" : "s have"} no walking path yet, because the map data there is still being built` : "";
  const at = Math.min(g.done + 1, g.of);
  return `<div class="guide-line muted plan-making">The Index is working out the epic's legs, at step ${num(at)} of ${num(g.of)}${none}</div>${planBarHtml(g.key, at, g.done, g.of)}`;
}

const PLAN_BAR = { digit: 7, pad: 5, gap: 4, room: 6, width: 330, ease: 600 };
const planBar = { key: null, from: 0, to: 0, w: PLAN_BAR.width, timer: 0 };
function planBarPlaces(at, done, of, w = planBar.w) {
  const fill = Math.min(1, Math.max(0, done / of)), edge = fill * w;
  const atW = num(at).length * PLAN_BAR.digit, ofW = num(of).length * PLAN_BAR.digit;
  if (done >= of) return { fill: 1, place: "behind", total: false };
  const behind = edge - PLAN_BAR.gap - atW >= PLAN_BAR.pad;
  const right = behind ? edge - PLAN_BAR.gap : edge + PLAN_BAR.gap + atW;
  return { fill, place: behind ? "behind" : "ahead", total: right <= w - PLAN_BAR.pad - ofW - PLAN_BAR.room };
}
function planBarHtml(key, at, done, of) {
  const p = planBarPlaces(at, done, of), pct = (f) => `${(f * 100).toFixed(2)}%`;
  if (planBar.key !== key) Object.assign(planBar, { key, from: 0, to: 0 });
  if (p.fill !== planBar.to) {
    planBar.from = planBar.to;
    planBar.to = p.fill;
    clearTimeout(planBar.timer);
    planBar.timer = setTimeout(() => { planBar.from = planBar.to; }, PLAN_BAR.ease + 100);
  }
  return `<div class="plan-bar" role="progressbar" aria-label="Steps worked out" aria-valuemin="0" aria-valuemax="${of}" aria-valuenow="${Math.min(done, of)}" style="--fill: ${
    pct(planBar.from)}" data-fill="${pct(p.fill)}"><div class="plan-bar-fill"></div><span class="plan-bar-of${p.total ? "" : " gone"}">${num(of)}</span><span class="plan-bar-at ${
    p.place}">${num(at)}</span></div>`;
}
function growPlanBar(box) {
  const bar = box.querySelector(".plan-bar[data-fill]");
  if (!bar) return;
  if (bar.clientWidth) planBar.w = bar.clientWidth;
  const to = bar.dataset.fill;
  if (bar.style.getPropertyValue("--fill").trim() === to) return;
  void bar.offsetWidth;
  bar.style.setProperty("--fill", to);
}
const epicWorking = (t) => (producing(t) && makingLine(t)) || workingHtml("epic");
function unbuiltLine(t) {
  const p = app.plan, n = p?.unbuilt;
  if (!n || p.key !== t.key || !planIsMine(p) || app.navfill?.state === "done") return "";
  const pct = app.navfill?.pct;
  const built = pct != null ? ` (${Math.min(99.9, Math.floor(pct * 10) / 10)}% of the world is mapped so far)` : "";
  return `<div class="guide-line muted plan-unbuilt">The walking path to ${n === 1 ? "1 step" : `${num(n)} steps`} isn't worked out yet, because the map data for ${
    n === 1 ? "that spot" : "those spots"} is still being built${built}. Until then the arrow points straight at ${n === 1 ? "that step" : "those steps"}.</div>`;
}
function waysLine(t) {
  const p = app.plan;
  if (p?.key !== t.key || !planIsMine(p) || (p.mode || "any") === trackMode(t)) return "";
  return `<div class="guide-line muted">${p.working ? "The Index is writing the epic's plan for the game again with this route"
    : `The epic's plan for the game still goes ${WAY_WORDS[p.mode || "any"]}`}</div>`;
}
function sharedStepIndex(t) {
  const sh = app.shared, loaded = app.status?.nums?.sharedVersion;
  if (t.kind !== "epic" || !t.step || !sh?.version || !loaded || loaded !== sh.version || sh.epic?.key !== t.key) return -1;
  return sh.epic.steps.findIndex((s) => sharedCode(s) === epicCode(t.step) && s.text === t.step.text);
}
on("start", refreshShared);

const EPIC_QUEUE_WAYS = 6;
const stepWayMode = (t, step) => withWant(trackMode(t), step?.mobs);
function stepWayPairs(t) {
  const steps = (t.data?.steps || []).slice(0, EPIC_QUEUE_WAYS + 1), out = [];
  for (let k = 1; k < steps.length; k++) {
    const a = steps[k - 1], b = steps[k];
    const apart = a.at && b.at ? Math.hypot(a.at[0] - b.at[0], a.at[1] - b.at[1]) : 0;
    if (!a.at || !b.at || a.inst !== b.inst || apart < 8 || apart >= ROUTE_NEAR) continue;
    out.push({ inst: b.inst, a: a.at, b: b.at, key: epicKey(b), mode: stepWayMode(t, b) });
  }
  return out;
}
function fetchStepWays(t) {
  for (const p of stepWayPairs(t)) askWay(p.inst, p.a, p.b, p.mode);
}

const EPIC_TARGET = { color: tint("objective-sky"), hot: tint("objective-sky-hot") };
function drawEpicTargets(t, s, size, scale) {
  const st = t.step;
  if (st?.walker && st.patrols?.length) return drawTalkWalk(st, s, size, scale);
  if (st?.kind !== "objective" || !st.spawns?.length) return;
  const screen = screenIn(st.inst, size, scale);
  if (!st.spawns.some((p) => screen(p))) return;
  const label = st.who?.length && !st.who.includes(st.target) ? `${st.target}: ${st.who.join(", ")}` : st.target;
  noteOverlay(label, EPIC_TARGET.color, EPIC_TARGET.hot);
  drawLit(label, EPIC_TARGET.color, () => {
    const pts = st.spawns.map(screen).filter(Boolean);
    renderHeat(pts.map(([x, y]) => [x, y, 1]), heatRadius(s.map, size, scale), heatRamp(EPIC_TARGET.color, EPIC_TARGET.hot));
    if (st.alone) for (const route of st.patrols || []) drawPatrol(route.map(screen).filter(Boolean), EPIC_TARGET.color);
    if (pts.length === 1) drawRingMarker(pts[0][0], pts[0][1], { r: 4, fill: EPIC_TARGET.color, ring: tint("black"), width: 1.5 });
  }, [st.quest]);
}

function drawTalkWalk(st, s, size, scale) {
  const screen = screenIn(st.inst, size, scale);
  const pts = st.patrols[0].map(screen).filter(Boolean);
  if (!pts.length) return;
  const label = `${st.npc || st.target || "The NPC"} walks the marked route`;
  noteOverlay(label, EPIC_TARGET.color, EPIC_TARGET.hot);
  drawLit(label, EPIC_TARGET.color, () => {
    if (st.walker === "off") renderHeat(pts.map(([x, y]) => [x, y, 1]), heatRadius(s.map, size, scale), heatRamp(EPIC_TARGET.color, EPIC_TARGET.hot));
    drawPatrol(pts, EPIC_TARGET.color);
  }, [st.quest]);
}

const ALONG_TARGETS = [{ color: tint("objective-mint"), hot: tint("objective-mint-hot") },
  { color: tint("objective-lemon"), hot: tint("white") }];
function alongTargets(t) {
  const g = gameGuide();
  if (!g?.states || loadedPlan().epic.key !== t.key || !t.data?.steps) return [];
  const { steps, states, cur, at } = runOrder(planSteps(), g.states, g.cur || 0, g.moves, g.chores);
  const i = shownStep(states, cur);
  if (!i) return [];
  const out = [];
  for (const x of alongSteps(steps, i, states, playerWorld(), at)) {
    const step = pageStep(t.data, x);
    const label = alongLabel(x);
    if (step?.spawns?.length && label) out.push({ step, label, quests: x.ids || [] });
  }
  return out;
}
function alongObjective(x) {
  if (x.get) return null;
  const id = x.ids?.[0], own = x.k === "O" ? stepObjective(x, logObjectives(id)) : -1;
  if (own >= 0) {
    const o = logObjectives(id)[own];
    return o.finished ? null : { o, id, k: own };
  }
  return shownObjectives(x).find((r) => !r.o.finished && typeof r.o.text === "string") || null;
}
function alongLabel(x) {
  const log = app.questlog?.entries || [];
  if (!(x.ids || []).some((id) => log.some((e) => e.id === id))) return `${x.text}, along the way`;
  const o = alongObjective(x)?.o;
  if (!o) {
    const left = stepObjective(x, logObjectives(x.ids[0])) < 0 && shownObjectives(x).some((r) => !r.o.finished);
    return left ? `${x.text}, along the way` : "";
  }
  const m = /^(.*?):\s*(\d+\s*\/\s*\d+)$/.exec(o.text || "");
  return `${m ? `${m[2].replace(/\s/g, "")} ${m[1]}` : o.text || x.text}, along the way`;
}
function drawAlongTargets(t, s, size, scale) {
  alongTargets(t).forEach(({ step, label, quests }, n) => {
    const screen = screenIn(step.inst, size, scale);
    if (!step.spawns.some((p) => screen(p))) return;
    const { color, hot } = ALONG_TARGETS[n % ALONG_TARGETS.length];
    noteOverlay(label, color, hot);
    drawLit(label, color, () => {
      const pts = step.spawns.map(screen).filter(Boolean);
      renderHeat(pts.map(([x, y]) => [x, y, 1]), heatRadius(s.map, size, scale), heatRamp(color, hot));
      if (step.alone) for (const route of step.patrols || []) drawPatrol(route.map(screen).filter(Boolean), color);
    }, quests);
  });
}

REPLANS.epic = {
  title: () => "Plans the epic afresh from the character's spot and what the game says now, the same as stopping the epic and starting it again. Then type /reload in game",
  question() {
    const parked = replanParked(app.tracks.epic);
    if (!parked.length) return null;
    return { title: "Unpark parked quests?", text: `Re-planning ${app.tracks.epic.name || "the quest epic"}. ${
      parked.length === 1 ? "This quest is" : "These quests are"} parked:`, list: parked.map((q) => q.name),
      more: "Yes plans the parked quests back in from where you are. No keeps them parked, planned last and still to do",
      yes: "Unpark them", no: "Keep them parked" };
  },
  start(done, { answer } = {}) {
    const t = app.tracks.epic;
    if (t) startEpic({ key: t.key, name: t.name, replan: true, keepParked: answer === false ? replanParked(t).map((q) => q.id) : null });
    done();
  },
};
function replanParked(t) {
  const g = gameGuide(), lp = loadedPlan()?.epic;
  if (!t || !g?.states || lp?.key !== t.key) return [];
  const { steps, states } = runOrder(planSteps(), g.states, g.cur || 0, g.moves, g.chores);
  return parkedQuests({ steps, states, live: g });
}


function drawPlanWays(steps, size, scale, alpha = 1, upTo = steps.length, colour = "forever-blue") {
  const whole = Math.floor(upTo), shown = steps.slice(0, Math.ceil(upTo)), strength = (s) => alpha * (s.a ?? 1);
  let tip = null, tipAlpha = alpha;
  ctx.save();
  ctx.lineWidth = 2; ctx.setLineDash([7, 5]);
  shown.forEach((s, k) => {
    let pts = (s.way || []).map(([n, w]) => worldOnScreen(s.i, n, w, size, scale)).filter(Boolean);
    if (pts.length < 2) return;
    if (k === whole) {
      const cum = lengths(pts);
      pts = stretch(pts, cum, 0, (upTo - whole) * cum[cum.length - 1]);
      tip = pts[pts.length - 1];
      tipAlpha = strength(s);
    }
    ctx.strokeStyle = tint(colour, 0.75 * strength(s));
    ctx.beginPath();
    pts.forEach(([x, y], j) => (j ? ctx.lineTo(x, y) : ctx.moveTo(x, y)));
    ctx.stroke();
  });
  ctx.setLineDash([]);
  for (const s of steps.slice(0, whole)) {
    const p = worldOnScreen(s.i, s.at[0], s.at[1], size, scale);
    if (!p) continue;
    ctx.beginPath(); ctx.arc(p[0], p[1], 4, 0, Math.PI * 2);
    ctx.fillStyle = tint(colour, 0.9 * strength(s)); ctx.fill();
    ctx.lineWidth = 1; ctx.strokeStyle = tint("black", strength(s)); ctx.stroke();
  }
  if (tip) {
    ctx.beginPath(); ctx.arc(tip[0], tip[1], 5, 0, Math.PI * 2);
    ctx.fillStyle = tint(colour, tipAlpha); ctx.fill();
    ctx.beginPath(); ctx.arc(tip[0], tip[1], 2, 0, Math.PI * 2);
    ctx.fillStyle = tint("white", Math.min(1, 2 * tipAlpha)); ctx.fill();
  }
  ctx.restore();
}
