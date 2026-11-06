// The Index of Azeroth. Copyright 2026 Index Case <indexofazeroth@pm.me>. PolyForm Strict 1.0.0, see LICENSE.md.
"use strict";

const HUNT_LINES = ["A dwarf is reading the bounty board", "SI:7 is asking around for a name", "A hunter is casting Track Humanoids",
  "A guard is pinning up a Wanted poster", "A Ravenholdt informant wants paying", "A tracker is following prints in the mud",
  "A hunter is placing Hunter's Mark", "The guards are asking who passed by", "The innkeeper will gossip for an ale",
  "Your pet has gone ahead on the scent"];
const HUNT_TYPE_MS = 45;
const HUNT_HOLD_MS = 1100;
const FIND_WAIT_MS = 80;
const GLASS_ICON = "inv_professions_inscription_scribesmagnifyingglass_gold";
const NPCS_ICON = "inv_bountyhunting";

const finder = { text: "", full: false, ask: null, busy: false, failed: false, found: [], done: null, wait: 0,
  hunt: { line: -1, last: -1, shown: 0, held: false, timer: 0 }, again: false };
const npcFindKept = keptOr("cc.npcFind", {});
if (typeof npcFindKept.text === "string" && npcFindKept.text.trim()) {
  Object.assign(finder, { text: npcFindKept.text, full: npcFindKept.full === true, again: true });
}
const keepNpcFind = () => keepIn("cc.npcFind", { text: finder.text, full: finder.full });


const finderHtml = () => html`<div class="npc-find"><div class="npc-box"><form class="npc-form" id="npc-form">${raw(searchBox("npc-find",
  "Find an NPC or mob by name", finder.text))}</form></div><div class="npc-hunt" aria-live="polite"><img
  class="npc-glass" id="npc-glass" src="/icon/${GLASS_ICON}.jpg" alt="" title="This is the full search. It allows more letters off and also searches the titles and zones"
  hidden><span class="npc-line" id="npc-line"></span></div></div>`;

function huntText() {
  const h = finder.hunt;
  if (h.line >= 0) return HUNT_LINES[h.line].slice(0, h.shown);
  if (!finder.text.trim() || finder.busy) return "";
  if (finder.failed) return "The trail went cold. The search didn't go through";
  const n = finder.found.length, further = finder.done?.more ? ". Press Enter to search further" : "";
  return n ? `${num(n)} found, with the nearest at the top${further}` : `No one goes by that name${further}`;
}
function paintHunt() {
  const line = $("npc-line");
  line.textContent = huntText();
  line.classList.toggle("typing", finder.hunt.line >= 0);
  $("npc-glass").hidden = !finder.full || !finder.text.trim();
}


function nextLine(not) {
  const k = Math.floor(Math.random() * (HUNT_LINES.length - 1));
  return k >= not && not >= 0 ? k + 1 : k;
}
function huntStart() {
  const h = finder.hunt;
  if (h.line >= 0) return;
  h.line = h.last = nextLine(h.last);
  h.shown = 0;
  h.held = false;
  h.timer = setTimeout(huntTick, HUNT_TYPE_MS);
}
function huntStop() {
  clearTimeout(finder.hunt.timer);
  finder.hunt.line = -1;
}
function huntTick() {
  const h = finder.hunt;
  if (h.shown < HUNT_LINES[h.line].length) {
    h.shown++;
    h.timer = setTimeout(huntTick, HUNT_TYPE_MS);
  } else if (!h.held) {
    h.held = true;
    h.timer = setTimeout(huntTick, HUNT_HOLD_MS);
  } else if (finder.busy) {
    h.line = h.last = nextLine(h.line);
    h.shown = 0;
    h.held = false;
    h.timer = setTimeout(huntTick, HUNT_TYPE_MS);
  } else {
    h.line = -1;
  }
  paintHunt();
}


function findTyped(text) {
  finder.text = text;
  clearTimeout(finder.wait);
  finder.full = false;
  finder.again = false;
  keepNpcFind();
  if (!text.trim()) {
    finder.ask?.abort();
    Object.assign(finder, { ask: null, busy: false, failed: false, found: [], done: null });
    huntStop();
  } else {
    finder.busy = true;
    huntStart();
    finder.wait = setTimeout(() => askNpcs(false), FIND_WAIT_MS);
  }
  renderFound();
  paintHunt();
}
function findEntered() {
  clearTimeout(finder.wait);
  if (finder.text.trim()) askNpcs(true);
}
function askNpcs(full) {
  finder.ask?.abort();
  const ctl = new AbortController(), q = new URLSearchParams({ q: finder.text.trim() });
  Object.assign(finder, { ask: ctl, full, busy: true, failed: false, found: [], done: null, again: false });
  keepNpcFind();
  if (full) q.set("full", "1");
  const me = playerWorld(true);
  if (me) { q.set("inst", me.inst); q.set("n", me.n.toFixed(1)); q.set("w", me.w.toFixed(1)); }
  if (app.status?.strs?.faction) q.set("faction", app.status.strs.faction);
  huntStart();
  renderFound();
  paintHunt();
  const mine = () => finder.ask === ctl;
  return askLines(`/api/npcs?${q}`, (part) => {
    if (!mine()) return;
    if (part.done) finder.done = part; else finder.found.push(...part.found);
    renderFound();
  }, { signal: ctl.signal }).then(() => {
    if (!mine()) return;
    Object.assign(finder, { ask: null, busy: false });
    paintHunt();
  }, (e) => {
    if (!mine()) return;
    Object.assign(finder, { ask: null, busy: false, failed: true });
    paintHunt();
    askFailed("No search", e);
  });
}


function detailHtml(n) {
  if (n.sub) return html`&lt;${n.sub}&gt;`;
  if (!n.levels && n.kind !== "mob") return "";
  return html`${mobLevelHtml(n.levels, { id: n.id, name: n.name, where: "npcs" })}${n.rank ? `, ${n.rank}` : ""}`;
}
function zonesTitle(n) {
  if (n.dungeon) return `${n.name} is inside ${n.zone}. Guide me leads to the entrance of ${n.zone}`;
  if (!n.zone) return `We have no information yet on where ${n.name} stands`;
  return n.zones.length ? `${n.name} is also in ${andList(n.zones)}` : "";
}
function npcRow(n, i) {
  const off = n.at || n.dungeon ? null : raw(" disabled");
  if (off) noteGap("npc-place", n.id, "npcs", n.name);
  const to = n.dungeon ? `the entrance of ${n.zone}` : n.kind === "mob" ? `the nearest spawn of ${n.name}` : n.name;
  const nowhere = `We have no information yet on where ${n.name} stands`;
  return html`<div class="npc-row" data-npc="${i}"><span class="mob-name">${n.name}<small>${detailHtml(n)}</small></span>
    <span class="npc-zone" title="${zonesTitle(n)}">${n.zone || "Unknown"}<small>${n.yards != null ? `${num(n.yards)} yd` : ""}</small></span>
    <button class="mob-go" data-npc-go="${i}"${off} title="${off ? nowhere : `This starts the Navigation Guide to ${to} and copies the line for the in-game arrow`}">Guide me</button>
    <button class="mob-go" data-npc-target="${i}" title="This puts the Target key for ${n.name} in the game. The key shows beside the add-on button after the next /reload, and its line is copied too">Target</button>
    <button class="mob-go" data-npc-both="${i}"${off} title="${off ? nowhere : `This does both. It starts the Navigation Guide to ${to} and puts the Target key for ${n.name} beside the add-on button`}">Both</button></div>`;
}
const foundHtml = () => html`${finder.found.map(npcRow)}`;
const renderFound = () => setHtml($("npc-found"), foundHtml());

function npcsClicked(e) {
  const b = e.target.closest("button[data-npc-go], button[data-npc-target], button[data-npc-both]");
  const n = b && !b.disabled && finder.found[+(b.dataset.npcGo ?? b.dataset.npcTarget ?? b.dataset.npcBoth)];
  if (!n) return !!b;
  heatNpc(n);
  if (b.dataset.npcTarget != null) targetNpc(n);
  else if (b.dataset.npcGo != null) guideToNpc(n);
  else bothNpc(n);
  return true;
}

function guideToNpc(n, opts = {}) {
  toggleMobMenu(false);
  if (n.at) {
    const sub = n.sub || (n.kind === "mob" ? [mobLevelText(n.levels), n.zone].filter(Boolean).join(", ") : n.zone);
    return guideTo({ todoId: null, name: n.name, sub, cat: n.kind === "mob" ? "mob" : "npc", icon: NPCS_ICON,
                     zone: n.zone, instance: n.at.inst, wx: n.at.n, wy: n.at.w, wz: n.at.z ?? undefined }, opts);
  }
  guideToDungeon(n.dungeon, n.zone, opts);
}
const targetLine = (n) => `/ioa target ${n.kind === "mob" ? "!" : "@"}${n.name}`;
function targetNpc(n) {
  const line = targetLine(n);
  leaveForLogin(line, "target", n.name);
  copyText(line, `The Target key for ${n.name} shows beside the add-on button after your next /reload. Its line is copied for a paste too`, false,
           { kind: "Target key", from: "reload-panel", reason: "target", reload: true });
}
function bothNpc(n) {
  leaveForLogin(targetLine(n), "target", n.name);
  guideToNpc(n, { lead: `The guide to ${n.name} is copied. The Target key for ${n.name} shows after your next /reload` });
}


const npcHeat = { spots: {} };
function npcHeatNames() {
  const g = shownGuide();
  return [...new Set([g && !g.none && !g.fromGame ? g.name : "", targetKeyName()])].filter((name) => name && npcHeat.spots[name]);
}
function heatNpc(n) {
  const live = new Set(npcHeatNames());
  for (const name of Object.keys(npcHeat.spots)) if (!live.has(name) && name !== n.name) delete npcHeat.spots[name];
  if (!n.heat || npcHeat.spots[n.name]) return;
  const mine = npcHeat.spots[n.name] = { kind: n.kind, spots: null };
  getJson(`/api/npcspots?${new URLSearchParams({ name: n.name })}`)?.then((d) => {
    if (npcHeat.spots[n.name] !== mine) return;
    mine.spots = d.spots;
    redraw();
  }, () => { if (npcHeat.spots[n.name] === mine) delete npcHeat.spots[n.name]; });
}
function npcHeatLook(name) {
  return npcHeat.spots[name].kind === "mob" ? { color: tint("kill-crimson"), hot: tint("bone-white") }
    : { color: tint("gold"), hot: tint("glint") };
}
function drawNpcHeat(s, size, scale) {
  if (app.dungeon) return;
  for (const name of npcHeatNames()) {
    const pts = (npcHeat.spots[name].spots || []).map(([inst, n, w]) => screenIn(inst, size, scale)([n, w])).filter(Boolean);
    if (!pts.length) continue;
    const look = npcHeatLook(name);
    noteOverlay(name, look.color, look.hot);
    drawLit(name, look.color, () => renderHeat(pts.map(([x, y]) => [x, y, 1]), heatRadius(s.map, size, scale), heatRamp(look.color, look.hot)));
  }
}


function startFinder(menu) {
  menu.addEventListener("input", (e) => { if (e.target.id === "npc-find") findTyped(e.target.value); });
  menu.addEventListener("submit", (e) => {
    if (e.target.id !== "npc-form") return;
    e.preventDefault();
    findEntered();
  });
}
function focusFinder() {
  if (finder.again) askNpcs(finder.full);
  setTimeout(() => $("npc-find")?.focus(), 0);
}

if (typeof module === "object") {
  module.exports = { HUNT_LINES, HUNT_TYPE_MS, HUNT_HOLD_MS, FIND_WAIT_MS, GLASS_ICON, NPCS_ICON, finder, finderHtml, huntText, paintHunt, nextLine,
                     huntStart, huntStop, huntTick, findTyped, findEntered, askNpcs, detailHtml, zonesTitle, npcRow, foundHtml,
                     renderFound, npcsClicked, guideToNpc, targetLine, targetNpc, bothNpc, npcHeat, npcHeatNames, heatNpc, npcHeatLook,
                     drawNpcHeat, startFinder, focusFinder };
}
