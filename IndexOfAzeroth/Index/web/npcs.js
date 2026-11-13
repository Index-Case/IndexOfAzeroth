// The Index of Azeroth. Copyright 2026 Index Case <indexofazeroth@pm.me>. PolyForm Strict 1.0.0, see LICENSE.md.
"use strict";

const HUNT_LINES = Object.values(wordsOf("page.npcs.hunt"));
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
  word("page.npcs.box"), finder.text))}</form></div><div class="npc-hunt" aria-live="polite"><img
  class="npc-glass" id="npc-glass" src="/icon/${GLASS_ICON}.jpg" alt="" title="${word("page.npcs.full.tip")}"
  hidden><span class="npc-line" id="npc-line"></span></div></div>`;

function huntText() {
  const h = finder.hunt;
  if (h.line >= 0) return HUNT_LINES[h.line].slice(0, h.shown);
  if (!finder.text.trim() || finder.busy) return "";
  if (finder.failed) return word("page.npcs.failed");
  const n = finder.found.length, more = !!finder.done?.more;
  if (n) return more ? word("page.npcs.found.more", { n: num(n) }) : word("page.npcs.found", { n: num(n) });
  return more ? word("page.npcs.none.more") : word("page.npcs.none");
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
    askFailed(word("page.npcs.search.failed"), e);
  });
}


function detailHtml(n) {
  if (n.sub) return html`&lt;${n.sub}&gt;`;
  if (!n.levels && n.kind !== "mob") return "";
  return html`${mobLevelHtml(n.levels, { id: n.id, name: n.name, where: "npcs" })}${n.rank ? `, ${n.rank}` : ""}`;
}
function zonesTitle(n) {
  if (n.dungeon) return word("page.npcs.inside", { name: n.name, zone: n.zone });
  if (!n.zone) return word("page.npcs.nowhere", { name: n.name });
  return n.zones.length ? word("page.npcs.also", { name: n.name, zones: andList(n.zones) }) : "";
}
function npcRow(n, i) {
  const off = n.at || n.dungeon ? null : raw(" disabled");
  if (off) noteGap("npc-place", n.id, "npcs", n.name);
  const to = n.dungeon ? word("page.npcs.to.entrance", { zone: n.zone }) : n.kind === "mob" ? word("page.npcs.to.spawn", { name: n.name }) : n.name;
  const nowhere = word("page.npcs.nowhere", { name: n.name });
  const show = off ? "" : html` title="${word("page.search.show", { name: n.name })}"`;
  return html`<div class="npc-row" data-npc="${i}"${show}><span class="mob-name">${n.name}<small>${detailHtml(n)}</small></span>
    <span class="npc-zone" title="${zonesTitle(n)}">${n.zone || word("page.npcs.zone.unknown")}<small>${n.yards != null ? `${num(n.yards)} yd` : ""}</small></span>
    <button class="mob-go" data-npc-go="${i}"${off} title="${off ? nowhere : word("page.npcs.go.tip", { to })}">${word("page.npcs.go")}</button>
    <button class="mob-go" data-npc-target="${i}" title="${word("page.npcs.target.tip", { name: n.name })}">${word("page.npcs.target")}</button>
    <button class="mob-go" data-npc-both="${i}"${off} title="${off ? nowhere : word("page.npcs.both.tip", { to, name: n.name })}">${word("page.npcs.both")}</button></div>`;
}
const foundHtml = () => html`${finder.found.map(npcRow)}`;
const renderFound = () => setHtml($("npc-found"), foundHtml());

function npcPlace(n) {
  if (n.at) return { at: n.at };
  const d = n.dungeon && dungeon.byKey[n.dungeon];
  return d ? doorFind(d) : null;
}
function npcsClicked(e) {
  const b = e.target.closest("button[data-npc-go], button[data-npc-target], button[data-npc-both]");
  const row = !b && e.target.closest("[data-npc]");
  if (row) {
    const p = finder.found[+row.dataset.npc] && npcPlace(finder.found[+row.dataset.npc]);
    if (p) {
      toggleMobMenu(false);
      showPlace(p);
    }
    return true;
  }
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
  copyText(line, word("page.npcs.target.copied", { name: n.name }), false,
           { kind: word("page.npcs.target.kind"), from: "reload-panel", reason: "target", reload: true });
}
function bothNpc(n) {
  leaveForLogin(targetLine(n), "target", n.name);
  guideToNpc(n, { lead: word("page.npcs.both.copied", { name: n.name }) });
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
