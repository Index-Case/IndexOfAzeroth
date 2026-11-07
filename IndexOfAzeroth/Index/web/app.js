// The Index of Azeroth. Copyright 2026 Index Case <indexofazeroth@pm.me>. PolyForm Strict 1.0.0, see LICENSE.md.
"use strict";

const $ = (id) => document.getElementById(id);
const DEFAULT_IMG = { w: 1024, h: 683 };
const ALERT_DELAY_MS = 1500;
const SERVER_SILENT_MS = 8000;
const RUN_SPEED = 7;
const MIN_ZOOM = 1, MAX_ZOOM = 40;
const HIGH_AT_PX_PER_YARD = 0.32, LOW_AT_PX_PER_YARD = 0.26;
const DRAWN_BELOW_ZOOM = 1.4, TILES_FROM_ZOOM = 1.6;
const OBJECTIVE_COLORS = [tint("objective-magenta"), tint("objective-violet"), tint("objective-mint"), tint("objective-rose"),
  tint("objective-lemon"), tint("objective-sky")];
const OBJECTIVE_HOT = [tint("objective-magenta-hot"), tint("objective-violet-hot"), tint("objective-mint-hot"), tint("grind-amber"),
  tint("white"), tint("objective-sky-hot")];
const SPAWN_RADIUS_YARDS = 40;

const app = {
  maps: {}, images: {},
  tiles: { instances: {} },
  detail: { current: "low", drawn: "low", city: {}, cityOn: false }, mapKinds: "both",
  state: null, status: null, bars: null, link: null, lastEvent: 0, badSince: null,
  view: { cx: 0.5, cy: 0.5, zoom: 2.5, follow: true, target: "you", headingUp: false, rot: 0, continent: null, world: false,
          zoneZoom: 2.5, contMap: null, zone: null },
  displayMap: null, curSize: null,
  band: { pull: 0, last: 0 },
  disp: null, dispMap: null,
  replayYou: null,
  trail: [], lastTrail: 0,
  drawer: null,
  noteHidden: {},
};

const wrap = (a) => Math.atan2(Math.sin(a), Math.cos(a));
const coords = (x, y) => `${(x * 100).toFixed(1)}, ${(y * 100).toFixed(1)}`;


const titleTip = document.createElement("div");
titleTip.className = "title-tip";
titleTip.hidden = true;
titleTip.setAttribute("role", "tooltip");
document.body.appendChild(titleTip);
let titleFor = null;
function titleOf(el) {
  if (el.hasAttribute("title")) {
    const text = el.getAttribute("title");
    el.removeAttribute("title");
    el.dataset.title = text;
    if (!el.getAttribute("aria-label") && !el.textContent.trim()) el.setAttribute("aria-label", text);
  }
  return el.dataset.title || "";
}
function placeTitleTip(e) {
  const at = tipPlace({ x: e.clientX, y: e.clientY }, titleTip.offsetWidth, titleTip.offsetHeight, inWindow());
  titleTip.style.left = `${at.x}px`;
  titleTip.style.top = `${at.y}px`;
}
function hideTitleTip() { titleTip.hidden = true; titleFor = null; }
function hoverOf(target) {
  const titled = target?.closest?.("[title], [data-title]"), item = target?.closest?.("[data-tip]");
  if (titled && item && titled !== item && item.contains(titled)) return { title: titled, item: null };
  return { title: item ? null : titled, item };
}
addEventListener("mouseover", (e) => {
  const any = e.target.closest?.("[title]");
  if (any) titleOf(any);
  const el = hoverOf(e.target).title;
  const text = el ? titleOf(el) : "";
  if (!text) return hideTitleTip();
  titleFor = el;
  if (titleTip.textContent !== text) titleTip.textContent = text;
  titleTip.hidden = false;
  placeTitleTip(e);
}, true);
addEventListener("mousemove", (e) => {
  if (!titleFor) return;
  if (titleFor.hasAttribute("title")) titleTip.textContent = titleOf(titleFor);
  placeTitleTip(e);
}, true);
addEventListener("mouseout", (e) => { if (titleFor && !titleFor.contains(e.relatedTarget)) hideTitleTip(); }, true);
new MutationObserver((changes) => {
  for (const c of changes) {
    if (!c.target.hasAttribute("title")) continue;
    const text = titleOf(c.target);
    if (c.target === titleFor && titleTip.textContent !== text) titleTip.textContent = text;
  }
}).observe(document.body, { attributes: true, attributeFilter: ["title"], subtree: true });
addEventListener("pointerdown", hideTitleTip, true);


const HOTKEYS = new Map();
function hotkey(keys, fn) {
  for (const k of keys) {
    if (HOTKEYS.has(k.toLowerCase())) throw new Error(`the ${k} key is taken twice`);
    HOTKEYS.set(k.toLowerCase(), fn);
  }
}
const LAYER = { help: 50, pinned: 49, question: 8, reader: 7, menu: 6, options: 5.5, video: 5, journal: 4, traffic: 3.5, drawer: 3 };
const CLOSABLES = [];
function closable(layer, isOpen, close) {
  CLOSABLES.push({ layer, isOpen, close });
  CLOSABLES.sort((a, b) => b.layer - a.layer);
}
function keyed(e) {
  if (e.key === "Escape") {
    const top = CLOSABLES.find((c) => c.isOpen());
    if (top) { e.stopImmediatePropagation(); e.preventDefault(); top.close(e); }
    return;
  }
  if (!e.altKey && e.target?.closest?.(".ol-item") && legendKey(e)) return;
  if (e.ctrlKey || e.metaKey || e.altKey || e.target?.closest?.("input, textarea, select, [contenteditable]")) return;
  if (e.target?.closest?.(".lg-row[data-lit]") && zoneRowKey(e)) return;
  const hotkey = HOTKEYS.get(e.key.toLowerCase());
  if (hotkey) { mapTouched(); hotkey(e); }
}
document.addEventListener("keydown", keyed, true);

function panelBar(bar, title, help, key) {
  bar.innerHTML = `<span class="j-bar-keys"></span><span class="j-bar-title">${esc(title)}</span><span class="j-bar-end">${helpButton(help)}`
    + `<button class="key small square x-mark" data-bar-close="1" title="Close (${key ? `${esc(key)} or ` : ""}Escape)">&times;</button></span>`;
}

const dropdowns = [];
function dropdown(button, menu, key, opening, bar) {
  const toggle = (open = menu.hidden) => {
    if (open) for (const other of dropdowns) if (other !== toggle) other(false);
    menu.hidden = !open;
    button.setAttribute("aria-expanded", String(open));
    if (open) opening();
  };
  dropdowns.push(toggle);
  panelBar(bar.el, bar.title, bar.help, key.toUpperCase());
  let own = null;
  button.addEventListener("click", (e) => { own = e; toggle(); });
  menu.addEventListener("click", (e) => {
    own = e;
    if (e.target.closest?.("[data-bar-close]")) toggle(false);
  });
  document.addEventListener("click", (e) => { if (e !== own) toggle(false); });
  hotkey([key], () => toggle());
  closable(LAYER.menu, () => !menu.hidden, () => toggle(false));
  return toggle;
}

let askShown = null;
function ask(q) {
  const box = $("ask-box");
  if (askShown) askShown.settle(null);
  let settle;
  const answer = new Promise((done) => { settle = done; });
  askShown = { ...q, settle };
  const list = (q.list || []).length ? `<ul class="ask-list">${q.list.map((x) => `<li>${esc(x)}</li>`).join("")}</ul>` : "";
  box.innerHTML = `<div class="gp-title">${esc(q.title)}</div><p>${esc(q.text)}</p>${list}${q.more ? `<p class="ask-more">${esc(q.more)}</p>` : ""}
    <div class="gp-foot"><button class="key small" data-ask="no">${esc(q.no || "No")}</button>
      <button class="key small" data-ask="yes">${esc(q.yes || "Yes")}</button></div>`;
  box.hidden = false;
  box.querySelector('button[data-ask="yes"]')?.focus();
  return answer;
}
function dropAsk() {
  takeAsk()?.settle(null);
}
function answerAsk(yes) {
  const q = takeAsk();
  if (!q) return;
  q.settle(yes);
  (yes ? q.onYes : q.onNo)?.();
}
function takeAsk() {
  const q = askShown;
  if (q) {
    askShown = null;
    $("ask-box").hidden = true;
  }
  return q;
}
function askClicked(e) {
  const b = e.target.closest("button[data-ask]");
  if (b) answerAsk(b.dataset.ask === "yes");
}
$("ask-box").addEventListener("click", askClicked);
closable(LAYER.question, () => !!askShown, () => answerAsk(false));

function mapName(id) {
  return app.maps[id]?.name || (id ? `map ${id}` : "unknown map");
}

function mapImage(id) {
  const info = app.maps[id];
  if (!info || info.type < 1 || info.tilesOnly) return null;
  let entry = app.images[id];
  if (entry?.failed) {
    const again = entry.failedAt + PICTURE_AGAIN_MS - Date.now();
    if (again <= 0) entry = app.images[id] = null;
    else redrawIn(again);
  }
  if (!entry) {
    const img = new Image();
    entry = app.images[id] = { img, ok: false, failed: false };
    img.onload = () => { entry.ok = true; redraw(); };
    img.onerror = () => {
      if (info.area && !img.src.includes("/map/")) img.src = `/map/${info.area}.jpg`;
      else { entry.failed = true; entry.failedAt = Date.now(); redraw(); }
    };
    img.src = worldMapSrc(id);
  }
  entry.hiSrc = info.paperup ? pictureSrc(`/paperup/${id}.jpg`, info.paperup) : null;
  return entry;
}
const PAPERUP_AT = 1, PAPERUP_ASK_AT = 0.6;
function paperUp(src) {
  const img = new Image(), hi = { img, src, ok: false };
  const done = () => { hi.ok = true; redraw(); };
  img.onload = () => (img.decode ? img.decode().then(done, done) : done());
  img.src = src;
  return hi;
}
function paperOf(entry, perPx) {
  if (!entry.hiSrc || !(perPx >= PAPERUP_ASK_AT)) return entry.img;
  if (entry.hi && entry.hi.src !== entry.hiSrc) entry.hi = null;
  entry.hi ||= paperUp(entry.hiSrc);
  return entry.hi.ok && perPx >= PAPERUP_AT ? entry.hi.img : entry.img;
}
const perPicturePx = (entry, wide, scale) => (scale * dpr * wide) / (entry.img.naturalWidth || wide);

const WORLD_MAP = 947;

function worldRound(map = app.displayMap) {
  const m = app.maps[map];
  return app.mapKinds === "detailed" && !app.dungeon && !!m?.world && (m.type === 2 || m.type === 3) && !!regionOf(m.instance, app.maps);
}

function viewMap() {
  const v = app.view, s = app.state;
  if (!s) return null;
  if (v.world && app.maps[WORLD_MAP]) return WORLD_MAP;
  const mine = ownMap();
  if (v.continent) return v.contMap || continentOf(mine) || app.hiddenMap || mine;
  return shownMap(v.zone || mine);
}
function ownMap() {
  const me = followed(), map = me?.map ?? app.state?.map;
  if (!me || app.maps[map]?.type !== 2) return map;
  const p = fracToWorld(map, me.x, me.y), zone = p ? zoneNamed(p, false) : null;
  return zone != null && app.maps[zone]?.type === 3 ? zone : map;
}
function followed() {
  const r = app.replayYou, s = app.state;
  if (app.view.target === "replay" && r) return { x: r.x, y: r.y, facing: r.f ?? 0, map: r.map };
  return app.disp && s ? { x: app.disp.x, y: app.disp.y, facing: app.disp.facing, map: app.dispMap ?? s.map } : null;
}
const followingYou = () => app.view.follow && app.view.target === "you";
const shownMap = (id) => cityZone(id) ?? id;

function zoneInView(own = followed()?.map ?? app.state?.map) {
  const v = app.view;
  if (!app.state || app.dungeon || followingYou() || app.displayMap == null) return own;
  const spot = fracToWorld(app.displayMap, v.cx, v.cy, app.maps, worldRound());
  return (spot && zoneNamed(spot)) || own;
}
function zoneNamed(spot, boxless = true) {
  const known = zoneOfArea(spot);
  if (known != null) return known;
  const box = zoneHolding(spot), m = app.maps[box];
  if (m?.areas) return zoneOfShape(spot) ?? cityZone(box);
  if (box != null && !m?.highlight) return box;
  return zoneOfShape(spot) ?? (boxless ? box : null);
}

const ZONE_FILLS = 0.25;
function searchArea() {
  const own = zoneInView(), info = app.maps[app.displayMap];
  if (!app.state || app.dungeon || !app.curSize || !info) return { scope: "zone", zones: [own], ask: false };
  const size = app.curSize, scale = scaleFor(size);
  if (app.view.world) {
    const zones = worldZones();
    return { scope: "world", zones, ask: zones.length > 1 };
  }
  if (info.type === 2 && zoneLabelsOn()) {
    const { all, labels } = zoneLabels(size, scale, { cont: app.displayMap, own: size, zone: shownZone() });
    if (!all) {
      const zones = continentZones(app.displayMap, size).map((z) => z.id);
      return { scope: "continent", zones, name: info.name, ask: zones.length > 1 };
    }
    const cv = clearView(), zones = labels.filter((l) => l.x >= cv.l && l.x <= cv.r && l.y >= cv.t && l.y <= cv.b).map((l) => l.id);
    if (zones.length) return { scope: "zones", zones, ask: zones.length > 1 };
  }
  return { scope: "zone", zones: zonesFilling(own, size, scale), ask: false };
}

function worldZones() {
  const out = [];
  for (const [id, m] of Object.entries(app.maps)) {
    if (m.type !== 3 || !m.world || m.tilesOnly) continue;
    const up = app.maps[m.parent];
    if (m.parent === WORLD_MAP || (up?.type === 2 && up.parent === WORLD_MAP)) out.push(+id);
  }
  return out;
}

const VIEW_ZONES = { cols: 16, rows: 10 };
function viewZones(size, scale) {
  const cv = clearView(), counts = new Map(), spots = [], { cols, rows } = VIEW_ZONES;
  for (let i = 0; i < cols; i++) {
    for (let j = 0; j < rows; j++) {
      const m = toMap(cv.l + (i + 0.5) * (cv.r - cv.l) / cols, cv.t + (j + 0.5) * (cv.b - cv.t) / rows, size, scale);
      const p = fracToWorld(app.displayMap, m.x, m.y, app.maps, worldRound()), z = p && zoneNamed(p, false);
      if (z == null) continue;
      spots.push({ zone: z, inst: p.inst, n: p.n, w: p.w });
      counts.set(z, (counts.get(z) || 0) + 1);
    }
  }
  return { counts, land: spots.length, spots };
}

function zonesFilling(own, size, scale) {
  const { counts, land } = viewZones(size, scale);
  return [own, ...[...counts].filter(([z, n]) => z !== own && n >= land * ZONE_FILLS).map(([z]) => z)];
}

function zoneOfShape(p) {
  const cont = continentMap(p.inst), f = cont != null && worldToFrac(cont, p);
  return f ? zoneUnder(f[0], f[1], imgSize(mapImage(cont)), cont) : zoneHolding(p);
}

const worldMapSrc = (id) => pictureSrc(`/worldmap/${id}.jpg`, app.maps[id]?.picture);

const markImages = new Map();
function markImage(src) {
  let img = markImages.get(src);
  if (!img) {
    img = new Image();
    img.onload = redraw;
    img.src = src;
    markImages.set(src, img);
  }
  return img;
}
function iconImage(name) {
  return markImage(`/icon/${name}.jpg`);
}
function uiImage(name) {
  return markImage(`/ui/${name}.png`);
}

const mapTiles = new MapTiles({ picture: () => new Image(), drawn: () => redraw(), ink: (a) => tint("black", a), address: pictureSrc });
const newCanvas = (w, h) => Object.assign(document.createElement("canvas"), { width: w, height: h });
const clouds = new Clouds({ canvas: newCanvas, picture: () => new Image(), drawn: () => redraw(), settled: () => viewSettled(), address: pictureSrc });


const pageFresh = new Fresh({ reload: () => location.reload(), editing: () => typingIn(document.activeElement) });
document.addEventListener("focusout", () => pageFresh.idle());
$("btn-reload").addEventListener("click", () => pageFresh.reload());

const HIDDEN_APPLY_MS = 1000;
const stream = { events: null, fails: 0, timer: 0 };
function connect() {
  let waiting = null, waitTimer = 0;
  const applyWaiting = () => { waitTimer = 0; const d = waiting; waiting = null; if (d) apply(JSON.parse(d)); };
  const open = () => {
    stream.timer = 0;
    const events = stream.events = new EventSource("/events");
    events.onopen = () => {
      stream.fails = 0;
      linkBack();
    };
    events.onmessage = (e) => {
      app.lastEvent = Date.now();
      if (!document.hidden) return apply(JSON.parse(e.data));
      waiting = e.data;
      if (!waitTimer) waitTimer = setTimeout(applyWaiting, HIDDEN_APPLY_MS);
    };
    events.onerror = () => {
      if (events.readyState !== EventSource.CLOSED || stream.timer) return;
      events.close();
      stream.timer = setTimeout(open, Math.min(ASK_WAIT_MOST, ASK_WAIT_FIRST * 2 ** stream.fails++));
    };
  };
  open();
  document.addEventListener("visibilitychange", () => {
    if (!document.hidden && waiting) { clearTimeout(waitTimer); applyWaiting(); }
  });
}

const SNAP_CLOCKS = new Set(["link", "time"]);
let lastSnap = null;
function apply(snap) {
  const changed = !sameData(snap, lastSnap, SNAP_CLOCKS);
  lastSnap = snap;
  app.link = snap.link;
  if (snap.updates) {
    app.updates = snap.updates;
    app.webLoaded ??= snap.updates.web;
    app.indexLoaded ??= snap.updates.index?.version;
    if (!snap.updates.index) step("page reload", () => pageFresh.heard(snap.updates.web, app.webLoaded));
  }
  if (snap.character && snap.character !== app.character) {
    if (app.character && !(snap.was || []).includes(app.character)) step("leave character", () => leaveCharacter());
    step("character keys", () => { moveCharStores(snap.was, snap.character); altsMoved(snap.was, snap.character); });
    app.character = snap.character;
  }
  app.who = snap.who || null;
  app.maxLevel = snap.maxLevel || null;
  app.options = snap.options || {};
  if (app.character) step("load tracks", () => loadTracks());
  if (snap.state && !snap.lastSeen) {
    const s = { ...snap.state }, waited = lastSeenOnly();
    if (app.state?.map !== s.map) { app.trail = []; }
    app.state = s;
    if (waited) step("last seen", () => endLastSeen());
    step("life", () => updateLife(s));
  } else step("last seen", () => takeLastSeen(snap.lastSeen));
  if (snap.status) {
    app.status = snap.status;
    step("player key", () => playerKey());
  }
  app.professions = snap.professions || [];
  app.legacyPoints = snap.legacyPoints || null;
  if (snap.bars) app.bars = snap.bars;
  app.run = snap.run || null;
  app.equipped = snap.equipped?.keys || snap.equipped?.items || null;
  step("rolls", () => applyRolls(snap));
  app.group = snap.group || null;
  app.queue = snap.queue || null;
  step("queue", () => applyQueue());
  app.quests = snap.quests || null;
  app.questlog = snap.questlog || null;
  step("quest log", () => applyQuestLog());
  app.epicLive = snap.epic || null;
  app.director = snap.director || null;
  app.loopStops = snap.loopStops || null;
  step("quest click", () => takeQuestClick(snap.questClick));
  if (snap.plan !== undefined) {
    const was = app.plan?.version;
    app.plan = snap.plan;
    if (app.plan?.version && app.plan.version !== was && app.plan.version !== app.shared?.version) step("shared", () => refreshShared());
  }
  app.cap = snap.cap || [];
  app.gameGuide = snap.guide?.source ? snap.guide : null;
  app.gameLoop = snap.guide?.loop || null;
  app.gameChecks = snap.guide?.checks || null;
  app.gameDeclined = snap.guide?.declined || null;
  app.pendingGuides = snap.pending || {};
  step("left guides", () => forgetLeftGuides());
  step("closed in game", () => noteGameClosed(snap.guide?.closed));
  step("reload prompt", () => renderReload());
  step("data status", () => noteDataStatus(snap.data));
  step("realign", () => noteRealign(snap.realign));
  app.fires = snap.fires || [];
  app.crates = snap.crates || [];
  app.grades = snap.grades || {};
  mapLight.campfire(arrowGlow(snap));
  app.navfill = snap.navfill || null;
  step("addons", () => applyAddons(snap));
  step("respawns", () => refreshRespawns(snap));
  step("alts", () => refreshAlts(snap));
  step("heights", () => refreshHeights(snap));
  step("dungeon", () => applyDungeon());
  if (app.state) step("indoors", () => checkIndoors());
  if (app.state && !app.state.seen) step("blood", () => blood.report(app.state, { character: app.character, where: bloodSpot() }));
  update();
  step("run", () => renderRun());
  step("hud", () => updateHud());
  step("xp", () => updateXp());
  step("status", () => renderStatus());
  step("drawer", () => renderDrawer());
  step("heat", () => heatWatch());
  step("alert", () => checkAlert());
  step("layers", () => refreshLayers());
  step("pois", () => refreshPois());
  step("epic sync", () => syncEpicWithGame());
  step("epic", () => refreshEpic());
  step("tracks", () => renderTracks());
  if (changed) redraw();
  emit("snapshot", snap);
}


app.dataStatus = null;
function noteDataStatus(d) {
  const before = app.dataStatus;
  app.dataStatus = d || null;
  if (!d || !before) return;
  if (d.state === "rebuilding" && d.readAt && d.readAt !== before.readAt) loadMapData();
  if (d.state !== "rebuilt" || before.at === d.at) return;
  loadMapData();
  dungeon.detail = {};
  dungeon.level = null;
  loadDungeons(app.state?.level || 0);
  loadStatWeights(true);
  showToast(d.art ? `${d.message}. The map shows it now.` : `${d.message}. Type /reload in game to load the new data into the journal.`);
}

function loadMapData() {
  fetchUntil(`/api/maps?v=${Date.now()}`, (j) => {
    app.maps = j.maps;
    app.images = {};
    updateHud();
    placeTravellers();
  });
  fetchUntil("/api/tiles", (j) => { app.tiles = j; mapTiles.setFloors(j); });
  fetchUntil("/api/rendertiles", (j) => { mapTiles.setRender(j); redraw(); });
  trees.reload();
  fetchUntil("/api/clouds", (j) => { clouds.set(j); redraw(); });
  fetchUntil("/api/seamask", (j) => { sea.setMask(j); redraw(); });
  loadUnderground();
  loadSeaGiants();
  fetchUntil("/api/lighttint", (j) => { lightTint.set(j); redraw(); });
  fetchUntil("/api/torches", (j) => { torches.set(j); redraw(); });
  fetchUntil("/api/roadways", (j) => { travellers.set(j); placeTravellers(); redraw(); });
  fetchUntil("/api/detailview", (j) => {
    app.detailView = j; detailPics.clear(); mapTiles.setMid(j.version, j.mid?.render);
    preloadFarTiles();
    placeTravellers();
    redraw();
  });
}

const DATA_STATES = { waiting: "Waiting", rebuilding: "Rebuilding", rebuilt: "Rebuilt", filled: "Filled ahead", failed: "Rebuild failed", error: "Check failed" };

const FRAME_WORDS = { position: "Position", status: "Status", bars: "Action bars",
  entrances: "Entrances", run: "Dungeon run", guide: "Arrow's guide", group: "Party", quests: "Quest list", loaded: "Loaded plan",
  kills: "Kills", character: "Character", taxi: "Flight paths", equipped: "Gear", container: "Bags and banks",
  rolls: "Loot rolls", gathers: "Gathering", epic: "Quest epic", completed: "Turned-in quests", questlog: "Quest log",
  queue: "Group finder", reloading: "Reloading" };
const linkSecs = (s) => (s == null ? "" : s < 10 ? `${s.toFixed(1)} s` : `${Math.round(s)} s`);


const HINTS = [
  [/window not found/, "window"],
  [/minimized/, "minimized"],
  [/strip isn't visible/, "hidden"],
  [/colors changed: Brightness/, "brightness"],
  [/colors changed: Contrast/, "contrast"],
  [/colors changed: Gamma/, "gamma"],
  [/colors changed/, "colors"],
  [/checksum/, "checksum"],
  [/version/, "version"],
  [/cut off/, "cut-off"],
  [/Index/, "index"],
];

const indexSilent = () => !app.lastEvent || Date.now() - app.lastEvent > SERVER_SILENT_MS;
function addonAwaited() {
  const a = app.updates?.index?.addon;
  if (a === "waiting") return word("page.launcher.addon-waiting");
  return a === "new" && !app.character ? word("page.launcher.addon-new") : null;
}
function linkProblem() {
  if (indexSilent()) return app.lastEvent ? "The Index isn't answering" : "Connecting to the Index";
  if (app.link && !app.link.ok) return app.link.message;
  return null;
}
function reloadingNow(now = Date.now()) {
  const r = app.link?.reloading;
  return !!r && now < r.until * 1000 && !indexSilent();
}
const RELOADING_TITLE = "The game interface is reloading";
const RELOADING_TEXT = "The pixel strip comes back when the game has finished loading.";

const lineTooNew = () => !!app.status?.nums && (app.status.nums.lineFormat || 0) < LINE_FORMAT;
const sameGuideName = (a, b) => {
  const x = String(a || "").trim().toLowerCase(), y = String(b || "").trim().toLowerCase();
  return !!x && !!y && (x === y || x.startsWith(y) || y.startsWith(x));
};

const PENDING_FRESH_MS = 12 * 3600 * 1000;
const pendingLeft = (g) => (g.at || 0) * 1000 + PENDING_FRESH_MS - Date.now();
const pendingWaits = (g, slot) => !!g && (!g.name || !app.who || charSame(g, app.who)) && pendingLeft(g) > 0
  && !(g.check != null && app.gameDeclined?.[slot] === g.check);
function gameRunsLine(slot, line, name = line.title) {
  if (app.gameChecks && line.check != null) return app.gameChecks[slot] === line.check;
  if (slot === "go") return !!app.gameGuide && sameGuideName(app.gameGuide.name, name);
  if (slot === "loop") return !!app.gameLoop && (line.kind == null || app.gameLoop.kind === line.kind) && sameGuideName(app.gameLoop.name, name);
  return false;
}
function targetKeyName() {
  const t = app.pendingGuides?.target;
  if (!t) return "";
  if (gameRunsLine("target", t)) return t.title || "";
  if (!pendingWaits(t, "target")) return "";
  redrawIn(pendingLeft(t));
  return t.title || "";
}
const LOOP_WORDS = { grind: "grind", farm: "farm", gather: "gathering", skin: "skinning", mining: "mining", herbalism: "herbalism",
                     fishing: "fishing", treasure: "treasure" };
function reloadReasons() {
  const u = app.updates || {}, out = [];
  if (u.addon === "restart") out.push({ kind: "addon", restart: true, text: "The Index's addon has a new file list, and the game reads a new file list only when it starts" });
  else if (u.addon === "reload") out.push({ kind: "addon", text: "The Index's addon changed since the game loaded it" });
  else if (lineTooNew()) out.push({ kind: "addon", text: "The addon in game is older than the page" });
  const newer = newerPlan(app.tracks?.epic);
  if (newer && newer.rating !== "minor") {
    const why = planReasons(newer.reasons || []);
    const said = newer.rating === "needed" ? "needs a new plan" : newer.rating === "worth" ? "has a new plan that is worth a reload" : "has its plan ready";
    out.push({ kind: "epic", needed: newer.rating === "needed", text: `${newer.name || "The quest epic"} ${said}${why ? `. ${why}` : ""}` });
  }
  const reopened = !newer && reopenedHere(app.tracks?.epic);
  if (reopened) out.push({ kind: "epic", text: `${reopened.name || "The quest epic"} is open again on the page, and the guide in game picks it up where you were` });
  const p = app.pendingGuides || {}, waiting = pendingWaits;
  if (waiting(p.go, "go") && !gameRunsLine("go", p.go)) {
    out.push({ kind: "guide", paste: true, text: `The Navigation Guide${p.go.title ? ` to ${p.go.title}` : ""} is waiting for the game` });
  }
  if (waiting(p.loop, "loop") && !gameRunsLine("loop", p.loop)) {
    const look = p.loop.look || p.loop.kind, word = LOOP_WORDS[p.loop.kind === "gather" ? look : p.loop.what] || LOOP_WORDS[p.loop.kind] || "grind";
    out.push({ kind: "loop", look, paste: true, text: `The ${word} loop${p.loop.title ? ` ${p.loop.title}` : ""} is waiting for the game` });
  }
  if (waiting(p.target, "target") && !gameRunsLine("target", p.target)) {
    out.push({ kind: "target", paste: true, text: `The Target key for ${p.target.title || "an NPC"} is waiting for the game` });
  }
  const loud = loudInGame().map((w) => warningText(w, app.status.nums)[0]);
  if (loud.length) {
    out.push({ kind: "warn", text: `${loud.length > 1 ? "Warnings you moved to To do still sound" : "A warning you moved to To do still sounds"} in game (${andList(loud)})` });
  }
  const hushed = quietInGame().map((w) => warningText(w, app.status.nums)[0]);
  if (hushed.length) {
    out.push({ kind: "warn", text: `${hushed.length > 1 ? "Warnings you put back on the band are" : "A warning you put back on the band is"} still quiet in game (${andList(hushed)})` });
  }
  const stars = starsToLoad();
  if (stars) out.push({ kind: "stars", text: stars });
  return out;
}

function renderReload() {
  const box = $("reload-panel");
  if (!box) return;
  const all = reloadReasons();
  planReadyCheck(all);
  const rs = all.filter((r) => r.kind !== "epic" || directorAllows("reload", r.needed));
  box.hidden = !rs.length;
  if (!rs.length) { setHtml(box, ""); return; }
  const restart = rs.some((r) => r.restart), needed = restart || rs.some((r) => r.needed);
  const flags = app.state?.flags || {};
  const when = flags.combat ? " once you're out of combat" : flags.taxi ? " now, while you fly" : "";
  const pasted = rs.filter((r) => r.paste), paste = pasted.length === rs.length;
  const lead = restart ? "Restart the game" : `Reload the interface (/reload)${paste ? ` or paste ${pasted.length > 1 ? "the lines" : "the line"}` : ""}${when}`;
  const panels = pasted.filter((r) => r.kind !== "target").length, targets = pasted.length - panels;
  const panel = pasted.find((r) => r.kind !== "target")?.kind === "loop" ? "the loop's panel" : "the guide's panel";
  const copy = !targets ? (panels > 1 ? "Press Copy on each panel, paste each line" : `Press Copy on ${panel}, paste the line`)
    : !panels ? "Press Target in the NPCs menu to copy the line, then paste the line"
    : "Copy a guide's line with Copy on its panel and the Target key's line with Target in the NPCs menu. Paste each line";
  const how = paste ? `<p class="reload-paste">Pasting is faster and needs no reload. ${copy} into the game's chat window and press Enter.</p>` : "";
  const where = "img/reload-where.png";
  setHtml(box, `<div class="plan-reload plan-${needed ? "needed" : "worth"}"><span class="plan-reload-where" style="--where:url(${where})"><span class="plan-reload-halo"></span><img src="${where}"
    alt="The add-on button in game with its little reload arrow clicked"></span>
    <div><div class="reload-top"><div class="plan-reload-lead">${esc(lead)}</div>${helpButton("reload")}</div>
    <ul class="reload-why">${rs.map((r) => `<li class="why-${r.kind}"${r.look ? ` data-look="${r.look}"` : ""}>${esc(r.text + (r.paste && !paste ? " (you can also paste its line)" : ""))}</li>`).join("")}</ul>${how}</div></div>`);
}

function forgetLeftGuides() {
  const p = app.pendingGuides || {}, mine = (g) => g && (!g.page || g.page === pageId());
  const hasGold = !!(app.guide && !app.guide.none && !app.guide.fromGame), hasLoop = !!app.tracks?.loop;
  app.pendingForgot = app.pendingForgot || {};
  for (const [slot, has] of [["go", hasGold], ["loop", hasLoop]]) {
    const g = p[slot];
    if (mine(g) && !has && !gameRunsLine(slot, g) && app.pendingForgot[slot] !== g.at) {
      app.pendingForgot[slot] = g.at;
      leaveForLogin(null, slot);
    }
  }
}

let closedSeen;
function noteGameClosed(c) {
  if (!c) return;
  if (closedSeen === undefined || c.n === closedSeen) { closedSeen = c.n; return; }
  closedSeen = c.n;
  if (c.kind === "gold" && app.guide && !app.guide.fromGame && sameGuideName(app.guide.name, c.name)) {
    const name = app.guide.name;
    stopGuide();
    showToast(`You closed the Navigation Guide to ${name} in game, so the page stopped the guide too`);
  } else if (c.kind === "loop" && app.tracks?.loop && sameGuideName(app.tracks.loop.name, c.name)) {
    const name = app.tracks.loop.name;
    const there = stopTrack("loop", true);
    showToast(`You closed ${name} in game, so the page stopped the loop${there ? " and the guide to it" : ""} too`);
  } else if (c.kind === "epic" && pastedFrom(app.tracks?.epic, c.name)) {
    const name = app.tracks.epic.name;
    stopTrack("epic", true);
    showToast(`${name} closed in game, so the page stopped it too`);
  }
}
function pastedFrom(t, codes) {
  if (!t) return false;
  const mine = new Set([...(t.data?.steps || []).map(epicCode), ...(t.copiedPacked || []).map((k) => k.split("|")[0])]);
  return String(codes || "").split(",").some((code) => !!code && mine.has(code));
}

function endedInGame() {
  const e = app.endedHere || {}, out = [];
  const go = !!e.go && gameRunsLine("go", e.go, e.go.name);
  if (e.go && !go) delete e.go;
  if (go) out.push(`The Navigation Guide to ${e.go.name} has ended on the page but still runs in game. To end the guide there, close its arrow, type /ioa go off or /reload`);
  const loop = !!e.loop && gameRunsLine("loop", e.loop, e.loop.name);
  if (e.loop && !loop) delete e.loop;
  if (loop) out.push(`${e.loop.name} has ended on the page but still runs in game. To end the loop there, close its arrow, type /ioa ${e.loop.verb} off or /reload`);
  return out;
}

function indexAsks() {
  const ix = app.updates?.index;
  if (!ix) return null;
  if (app.indexLoaded && ix.version !== app.indexLoaded) return "updated";
  return ix.news?.step === "offer" && app.indexAnswered !== ix.news.version ? "offer" : null;
}

function indexUpdateHtml() {
  const n = app.updates?.index?.news;
  if (!n || (n.step === "offer" && indexAsks() !== "offer")) return "";
  if (n.step === "offer") {
    return `<section class="index-update"><p>${esc(word("page.update.offer", { version: n.version, size: n.size }))}</p>`
      + `${n.changes ? `<p class="muted">${esc(n.changes)}</p>` : ""}<div class="index-update-keys">`
      + `<button class="key small" data-index-update="update">${esc(word("page.launcher.update"))}</button>`
      + `<button class="key small" data-index-update="later">${esc(word("page.launcher.later"))}</button></div></section>`;
  }
  const line = n.step === "downloading" ? n.line : word("page.launcher.wait-game");
  return `<section class="index-update"><p>${esc(line)}</p></section>`;
}

function answerUpdate(choice) {
  app.indexAnswered = app.updates?.index?.news?.version;
  renderDrawer();
  postJson("/api/update", { choice }, { quiet: true })?.catch(() => { app.indexAnswered = null; renderDrawer(); });
}

function updateReasons() {
  const u = app.updates || {}, out = [];
  if (indexAsks() === "updated") out.push(word("page.update.updated"));
  else if (u.web && app.webLoaded && u.web !== app.webLoaded) out.push("The page has an update. Press Ctrl+F5 to load the update");
  for (const r of reloadReasons()) {
    out.push(`${r.text}. ${r.restart ? "Restart the game" : r.paste ? "Type /reload in game or paste the line into the game's chat" : "Type /reload in game"}`);
  }
  if (stoppedHereOnly()) {
    out.push("The quest epic is closed on the page but its guide still runs in game. To close the guide there, close its card or the blue arrow, or type /reload");
  }
  out.push(...endedInGame());
  for (const a of app.addons?.list || []) { const t = addonAction(a); if (t) out.push(t); }
  return out;
}

const PAGE_VERSION = String(document.querySelector?.('meta[name="page-version"]')?.getAttribute?.("content") || "");
function pageVersion() {
  const at = app.webLoaded && new Date(app.webLoaded * 1000), two = (n) => String(n).padStart(2, "0");
  const built = PAGE_VERSION || (at ? `${at.getDate()} ${at.toLocaleString("en-GB", { month: "short" })} ${two(at.getHours())}:${two(at.getMinutes())}` : "");
  const stale = !!(app.updates?.web && app.webLoaded && app.updates.web !== app.webLoaded);
  return { text: built ? `Page ${built}${stale ? ". Ctrl+F5 loads the newer page" : ""}` : "", stale };
}

function checkAlert() {
  const problem = linkProblem(), reload = reloadingNow();
  const signal = $("signal");
  signal.classList.toggle("ok", !problem && !reload);
  signal.classList.toggle("bad", !!problem && !reload && !!app.badSince);
  signal.classList.toggle("info", reload);
  $("signal-text").textContent = reload ? "Reloading" : problem ? "No signal" : `Live ${app.link?.rate ?? 0}/s`;
  const version = pageVersion();
  $("signal-version").textContent = version.text;
  $("signal-version").classList.toggle("stale", version.stale);
  const waiting = updateReasons(), news = $("signal-news");
  news.hidden = !waiting.length;
  const asks = !!indexAsks();
  document.querySelectorAll('.key[data-drawer="link"]').forEach((k) => k.classList.toggle("update-blink", asks));
  signal.title = waiting.length ? `Waiting to be loaded:\n${waiting.join("\n")}` : "Shows whether the page can read the pixel strip";

  if (!problem && !reload) {
    app.badSince = null;
    $("alert").hidden = true;
    document.body.classList.remove("alerting");
    return;
  }
  if (reload) {
    app.badSince = null;
    $("alert").classList.add("info");
    $("alert-title").textContent = RELOADING_TITLE;
    $("alert-text").textContent = RELOADING_TEXT;
    $("alert-hint").textContent = "";
  } else {
    app.badSince ??= Date.now();
    if (Date.now() - app.badSince < ALERT_DELAY_MS) {
      $("alert").hidden = true;
      document.body.classList.remove("alerting");
      return;
    }
    const serverDown = /Index/.test(problem), addon = !serverDown && addonAwaited();
    $("alert").classList.remove("info");
    $("alert-title").textContent = serverDown ? "The Index is offline" : "The pixel strip can't be read";
    $("alert-text").textContent = addon || problem.charAt(0).toUpperCase() + problem.slice(1);
    $("alert-hint").textContent = addon ? "" : wordsOf("page.alert")[(HINTS.find(([re]) => re.test(problem)) || [null, "default"])[1]];
  }
  $("alert").hidden = false;
  document.body.style.setProperty("--alert-h", `${$("alert").offsetHeight}px`);
  document.body.classList.add("alerting");
}


function turnText(rel) {
  const deg = Math.round(Math.abs(rel) * 180 / Math.PI);
  if (deg <= 12) return "Straight ahead";
  if (deg >= 165) return "Behind you";
  return `Turn ${rel > 0 ? "left" : "right"} ${deg}°`;
}

const atSpot = (d, rise = null, held = false) => !rise && !held && d <= DirectorRules.table.guide.arrive;
function distanceWords(yd) {
  const s = app.state, speed = s?.speed > 0.5 ? s.speed : RUN_SPEED;
  return atSpot(yd) ? `${num(yd)} yd` : `${num(yd)} yd, ${duration(yd / speed)}`;
}

function updateViewZone() {
  const v = app.view, s = app.state, box = $("view-zone");
  const id = s && !v.world && !v.continent && !app.dungeon ? zoneInView() : null;
  let name = id && id !== s.map ? app.maps[id]?.name : "";
  const place = s && !v.world && !app.dungeon && !followingYou() ? placeInView() : null;
  if (place && place.cont !== continentOf(s.map) && (v.continent || place.sea)) name = place.name;
  if (box.textContent !== (name || "")) box.textContent = name || "";
  box.hidden = !name;
}
function placeInView() {
  const map = app.displayMap, mid = worldRound(map) ? fracToWorld(map, app.view.cx, app.view.cy, app.maps, true) : null;
  const r = mid && regionOf(mid.inst, app.maps);
  if (!r) return null;
  const [across, down] = placeIn(r.world, mid.n, mid.w, ...r.ui), yd = worldYards(r.map, app.maps);
  const here = worldAt(yd, across, down), eye = swirlEye(worldPlace((n, w) => worldSpot(yd, n, w))), sea = zoneNamed(mid, false) == null;
  if (Math.hypot(here.n - eye.n, here.w - eye.w) < MAELSTROM.radius) return { name: word("page.map.maelstrom"), cont: null, sea };
  const cont = continentMap(mid.inst);
  if (cont != null && across >= r.ui[0] && across <= r.ui[2] && down >= r.ui[1] && down <= r.ui[3]) return { name: mapName(cont), cont, sea };
  return { name: word("page.map.sea"), cont: null, sea };
}

const WAITING_ZONE = $("zone").textContent;
function updateHud() {
  const s = app.state;
  if (!s) return;
  const zone = s.zone || (s.seen && nobodySeen(s.seen) ? WAITING_ZONE : mapName(s.map));
  $("zone").textContent = zone;
  const levels = app.maps[s.map]?.levels, range = $("zone-levels");
  range.hidden = !levels || !!app.dungeon;
  if (levels) {
    range.textContent = zoneRangeText(levels);
    range.style.color = zoneThreat(levels);
  }
  $("subzone").textContent = s.subzone && s.subzone !== zone ? s.subzone : "";
  updateViewZone();
  const tags = [];
  if (s.flags.combat) tags.push("In combat");
  if (s.flags.resting) tags.push("Resting");
  if (s.flags.ghost) tags.push("Ghost");
  if (insideAt(liveIndoors(s))) tags.push("Underground or indoors");
  const inside = inDungeon(s);
  const where = inside ? "" : s.pos ? coords(s.pos.x, s.pos.y) : lastSeenOnly() ? lastSeenText(s.seen) : "No coordinates here";
  $("coords").textContent = [where, tags.join(", ")].filter(Boolean).join("   ");

  const note = $("mapnote");
  const info = app.maps[s.map];
  if (inside || lastSeenOnly()) {
    note.textContent = "";
  } else if (!s.pos) {
    note.textContent = "The game hides your position in some indoor areas, and you're in one of those areas.";
  } else if (!info || (!info.world && !info.regions)) {
    note.textContent = `No map data for ${mapName(s.map)}. Showing your position on a blank grid.`;
  } else if (app.images[s.map]?.failed) {
    note.textContent = `The map picture for ${info.name} isn't stored yet.`;
  } else {
    note.textContent = "";
  }
  const text = note.textContent;
  note.hidden = !text || !!app.noteHidden[text];
}

app.itemInfo = {};
const itemInfoAsked = new Set();
const itemInfoWaiting = new Map();
let itemInfoOut = 0;
function itemInfoDone() {
  itemInfoOut--;
  const waiting = [...itemInfoWaiting.values()];
  itemInfoWaiting.clear();
  waiting.forEach(([ids, then]) => wantItemInfo(ids, then));
}
function wantItemInfo(ids, then) {
  const need = [...new Set(ids.filter(Boolean).map(String).filter((id) => !itemInfoAsked.has(id)))];
  const batch = need.slice(0, 200), asked = batch.length && getJson(`/api/iteminfo?ids=${batch.join(",")}`, { key: "iteminfo" });
  if (!asked) {
    if (batch.length && itemInfoOut) itemInfoWaiting.set(need.join(","), [need, then]);
    return;
  }
  itemInfoOut++;
  batch.forEach((id) => itemInfoAsked.add(id));
  asked.then((j) => { Object.assign(app.itemInfo, j); then?.(); itemInfoDone(); if (need.length > batch.length) wantItemInfo(need.slice(batch.length), then); },
    () => { batch.forEach((id) => itemInfoAsked.delete(id)); itemInfoDone(); });
}
function updateXp() {
  const s = app.state;
  if (!s) return;
  const capped = app.maxLevel != null && s.level >= app.maxLevel;
  const max = capped ? 0 : s.xpMax;
  const fill = max ? Math.min(1, s.xp / max) : 1;
  const rest = max ? Math.min(1, (s.xp + s.rested) / max) : 0;
  $("xp-fill").style.width = `${fill * 100}%`;
  $("xp-rested").style.width = `${rest * 100}%`;
  $("xp-text").textContent = max
    ? `Level ${s.level}   ${num(s.xp)} / ${num(max)} (${pct(s.xp, max)}%)` + (s.rested ? `   Rested ${num(s.rested)} (${pct(s.rested, max)}%)` : "")
    : `Level ${s.level}${capped ? ", the game's level cap" : ""}`;
  const stage = max ? heatStage(fill) : "", edge = $("xp-edge"), tail = $("xp-tail");
  if (edge.dataset.stage !== stage) {
    edge.dataset.stage = stage;
    edge.className = `heat-edge${stage ? ` heat-${stage}` : ""}`;
    edge.hidden = tail.hidden = !stage;
  }
  if (stage) {
    tail.style.cssText = heatTailStyle(heatT(fill), HEAT_XP);
    edge.style.cssText = heatEdgeStyle(heatT(fill), HEAT_XP);
  }
  const age = heatLevelled(`xp:${heatWho()}`, s.level || 0), burst = $("xp-burst");
  burst.hidden = age == null;
  if (age != null) burst.style.animationDelay = `-${Math.round(age)}ms`;
}


const DRAWERS = {
  link() {
    const l = app.link || {};
    const problem = linkProblem();
    const waiting = updateReasons();
    const kinds = Object.entries(l.kinds || {}).sort((a, b) => (b[1].most ?? 99) - (a[1].most ?? 99))
      .map(([k, s]) => `<tr><td>${esc(FRAME_WORDS[k] || k)}</td><td class="num">${s.n}</td><td class="num">${linkSecs(s.every)}</td>
        <td class="num">${linkSecs(s.most)}</td><td class="num">${linkSecs(s.age)}</td></tr>`).join("");
    return `${indexUpdateHtml()}${realignHtml()}${waiting.length ? `<h2>Waiting to be loaded</h2><ul class="waiting">${waiting.map((t) => `<li>${esc(t)}</li>`).join("")}</ul>` : ""}
      <h2>Pixel strip</h2>
      <table class="facts">
        <tr><th>Status</th><td>${esc(problem || l.message || "")}</td></tr>
        <tr><th>Reads per second</th><td>${l.rate ?? 0}</td></tr>
        <tr><th>Frames per second</th><td>${l.fps ?? 0}</td></tr>
        <tr><th>Frames lost, last minute</th><td>${l.lost ?? 0}${l.lost ? ` (${l.lostPct}%)` : ""}</td></tr>
        <tr><th>Old frames read again, dropped</th><td>${l.stale ?? 0}</td></tr>
        <tr><th>Reader stalls, last minute</th><td>${l.stalls ? `${l.stalls}, the longest ${l.stallMost} ms` : "none"}</td></tr>
        <tr><th>Failed reads, last 2 s</th><td>${l.errors ?? 0}</td></tr>
        <tr><th>Block size</th><td>${l.block ? `${l.block} px` : "not seen yet"}</td></tr>
      </table>
      ${kinds ? `<h3>Each kind of frame, last minute</h3>
      <table class="list"><tr><th>Frame</th><th class="num">Came</th><th class="num">Every</th><th class="num">Longest gap</th><th class="num">Last</th></tr>${kinds}</table>
      <p class="muted">A lost frame is one the game drew and the Index never read. A stall is the Index staying busy for longer than a frame shows. Both are lag. Every and Longest gap say how long each kind of frame waits for its turn on the strip.</p>` : ""}
      <h3>How it works</h3>
      <p>The Index's addon draws a row of colored blocks in the top left corner of the game window. The Index copies that corner of the screen about 15 times a second and decodes position, facing, experience and the guide's waypoints from the colors.</p>
      <h3>In game</h3>
      <table class="facts">
        <tr><th><code>/ioa test</code></th><td>Draws a fixed pattern. This page says "test pattern OK" when every value arrives intact.</td></tr>
        <tr><th><code>/ioa strip on</code></th><td>Resumes live data, or turns the strip back on.</td></tr>
        <tr><th><code>/ioa size 6</code></th><td>Makes the blocks bigger. The size goes from 2 to 8 pixels.</td></tr>
        <tr><th><code>/ioa debug</code></th><td>Prints what the addon is sending.</td></tr>
      </table>
      <h3>Data</h3>
      <table class="facts">
        <tr><th>Built for</th><td>${esc(app.tiles?.version || "unknown")}</td></tr>
        ${app.dataStatus?.state ? `<tr><th>${DATA_STATES[app.dataStatus.state] || app.dataStatus.state}</th><td>${esc(app.dataStatus.step || app.dataStatus.message || "")}</td></tr>` : ""}
      </table>
      ${emit("statusData").join("")}
      <h3>Addons</h3>
      <p class="muted">The Index keeps the Index's addon installed and current. AtlasLoot can be kept or removed, because the journal no longer needs AtlasLoot in the game. When the Index's addon is missing, the Index installs it at once. Updates wait until the game is closed. The Index keeps the copies it replaced in the game folder's WCC\\old.</p>
      ${addonsTable()}
      ${emit("statusAddons").join("")}
      <h3>Credits</h3>
      <ul class="credits">
        <li><b>RestedXP Guides</b> (the RestedXP team): the dangerous mobs and their notes, which show on the red glow of a route and on the epic's card. Their data is licensed under <a href="https://creativecommons.org/licenses/by-nc-sa/4.0/" target="_blank" rel="noopener">CC BY-NC-SA 4.0</a>. Our copy is under the same licence, credited here and never sold. Their licence text is in data/dangerous-LICENSE.txt. No other RestedXP data has been used.</li>
        <li><b>ForeverDB</b>: Some of the quest givers, quest chains and vendor and trainer prices come from <a href="https://foreverdb.net" target="_blank" rel="noopener">ForeverDB.net</a>, which collects what its players see in WoW Forever. ForeverDB is not affiliated with Blizzard Entertainment.</li>
        <li>World of Warcraft and its art © Blizzard Entertainment, Inc.</li>
      </ul>
      <p>If you'd like to tip, the Index has a Ko-fi page: <a href="https://ko-fi.com/indexcase" target="_blank" rel="noopener">ko-fi.com/indexcase</a></p>`;
  },
};

const DRAWER_TITLES = { route: "Route", link: "Status", alts: "Alts" };

app.pack = { state: "idle" };
const packBusy = () => app.pack.state === "exporting" || app.pack.state === "importing";
app.packPath = "";
function packPanel() {
  const off = packBusy() ? " disabled" : "";
  return `<div class="opt-row wide"><div class="opt-words"><div class="opt-name">${esc(word("page.options.import-export.export"))}</div>`
    + `<div class="opt-text">${esc(word("page.options.import-export.export.text"))}</div></div>`
    + `<div class="opt-line"><button class="key small" id="btn-pack-export"${off}>${esc(word("page.options.import-export.export.key"))}</button>`
    + `<span class="opt-state">${esc(packText())}</span></div></div>`
    + `<div class="opt-row wide"><div class="opt-words"><div class="opt-name">${esc(word("page.options.import-export.import"))}</div>`
    + `<div class="opt-text">${esc(word("page.options.import-export.import.text"))}</div></div>`
    + `<div class="opt-line"><input id="pack-path" type="text" placeholder="${esc(word("page.options.import-export.import.box"))}" value="${esc(app.packPath)}">`
    + `<button class="key small" id="btn-pack-import"${off}>${esc(word("page.options.import-export.import.key"))}</button></div></div>`;
}
function keepPackPath(e) {
  if (e.target.id === "pack-path") app.packPath = e.target.value;
}
function packText() {
  const p = app.pack, pct = p.total ? ` ${Math.round(p.done / p.total * 100)}%` : "";
  return p.state === "exporting" ? `${word("page.options.import-export.exporting")}${pct}`
    : p.state === "importing" ? `${word("page.options.import-export.importing")}${pct}`
    : p.state === "exported" ? word("page.options.import-export.exported", { size: (p.total / 2 ** 30).toFixed(1), path: p.path })
    : p.state === "imported" ? wordCount("page.options.import-export.imported", p.files, { kept: p.kept })
    : p.state === "failed" ? word("page.options.import-export.failed", { message: p.message }) : "";
}
function packClick(e) {
  if (e.target.id === "btn-pack-export") startPack({ do: "export" });
  else if (e.target.id === "btn-pack-import") startPack({ do: "import", path: app.packPath.trim() });
}
let packTimer = 0;
function followPack() {
  clearTimeout(packTimer);
  const asked = getJson("/api/pack", { quiet: true }), next = (ms) => { packTimer = setTimeout(followPack, ms); };
  if (!asked) {
    if (askWait("/api/pack")) next(askWait("/api/pack"));
    return;
  }
  asked.then((p) => {
    app.pack = p;
    options.refresh();
    if (packBusy()) next(1000);
  }, () => { if (packBusy()) next(askWait("/api/pack")); });
}
function startPack(body) {
  postJson("/api/pack", body).then((j) => {
    if (!j.started) showToast(j.message || word("page.options.import-export.busy"));
    else app.pack = { state: body.do === "import" ? "importing" : "exporting" };
    followPack();
  }, (e) => askFailed(body.do === "import" ? word("page.options.import-export.import.failed") : word("page.options.import-export.export.failed"), e));
}

function renderDrawer() {
  if (app.drawer && setHtml($("drawer-body"), emit("drawer", app.drawer).join("") + DRAWERS[app.drawer]())) placeDrawer();
}

function openDrawer(name) {
  keepDrawerPlace();
  app.drawer = app.drawer === name ? null : name;
  $("drawer").hidden = !app.drawer;
  document.body.classList.toggle("drawer-open", !!app.drawer);
  document.querySelectorAll(".key[data-drawer]").forEach((k) => k.setAttribute("aria-pressed", String(k.dataset.drawer === app.drawer)));
  if (app.drawer) {
    drawerBar(app.drawer);
    drawerOpened(app.drawer);
  }
  renderDrawer();
  if (app.drawer) backToPlace();
  keepIn("cc.drawer", app.drawer);
}

const drawerPlace = { at: {}, back: null };
try { Object.assign(drawerPlace.at, JSON.parse(localStorage.getItem("cc.drawerScroll") || "{}")); } catch (e) {   }
function keepDrawerPlace() {
  const name = app.drawer, back = drawerPlace.back, top = $("drawer-body").scrollTop;
  if (!name) return;
  drawerPlace.at[name] = back?.name === name && top === back.top ? back.to : Math.round(top);
  try { localStorage.setItem("cc.drawerScroll", JSON.stringify(drawerPlace.at)); } catch (e) {   }
}
function backToPlace() {
  drawerPlace.back = { name: app.drawer, to: +drawerPlace.at[app.drawer] || 0, top: $("drawer-body").scrollTop };
  placeDrawer();
}
function placeDrawer() {
  const back = drawerPlace.back, body = $("drawer-body");
  if (!back || back.name !== app.drawer || body.scrollTop !== back.top) { drawerPlace.back = null; return; }
  body.scrollTop = back.to;
  back.top = body.scrollTop;
  if (Math.abs(back.top - back.to) < 1) drawerPlace.back = null;
}
$("drawer-body").addEventListener("scroll", keepDrawerPlace);

function drawerBar(name) {
  const key = document.querySelector(`.key[data-drawer="${name}"] .hotkey`)?.textContent;
  panelBar($("drawer-bar"), DRAWER_TITLES[name] || "", name, key);
}


const canvas = $("map");
const needle = $("needle");
const ctx = canvas.getContext("2d");
let W = 0, H = 0, dpr = 1;

const mapLight = new MapLight({ layer: $("map-light"), night: $("map-night"), shade: $("map-shade"), canvas, you: $("map-you"),
  cast: lanternCanvas($("map-shade")), root: document.documentElement, blend: gauntletBlend(document),
  swung: () => { if (relief.pointerLit) redraw(); } });
function lanternCanvas(under) {
  const el = document.createElement("canvas");
  el.hidden = true;
  el.setAttribute("aria-hidden", "true");
  Object.assign(el.style, { position: "absolute", left: "0", top: "0", pointerEvents: "none" });
  under.before(el);
  return el;
}
on("snapshot", (snap) => mapLight.report(snap.status?.nums?.serverMinutes));
on("update", () => mapLight.paint());
canvas.addEventListener("pointermove", (e) => mapLight.pointer(e.offsetX, e.offsetY));
canvas.addEventListener("pointerleave", () => mapLight.pointer(null));

function newLight() {
  return Object.assign(new Relief({ canvas: document.createElement("canvas"), bytes: getBytes, decode: getPicture, drawn: () => redraw(),
    clearSea: () => tintArt("sea") || belowShown() }), {
    shapeUrl: (id, band = null) => (app.treesOn && shapesRead(trees.index) && trees.shapeUrl(id, band))
      || (band && band.far || !shapesRead(mapTiles.render) ? null : renderShape(id)),
    shapeTall: (id) => (app.treesOn ? trees.tallest(id) : 0),
    shapeFull: (id) => trees.full(id) });
}
let relief = newLight();
const lights = new Map();
function lightOf(inst) {
  if (!lights.has(inst)) lights.set(inst, lights.size ? newLight() : relief);
  return lights.get(inst);
}
const lightTint = new LightTint();
const torches = new Torches();
const travellers = new Travellers();
let travellersAt = null;
function walkTravellers() {
  const now = performance.now(), seconds = travellersAt == null ? 0 : (now - travellersAt) / 1000;
  travellersAt = now;
  travellers.advance(seconds, oneLightAt(mapLight.hour(), app.nightOn !== false).lamp > 0);
}
function placeTravellers() {
  if (!app.maps || !app.detailView) return;
  const out = [], names = [];
  for (const [id, lettering] of Object.entries(app.detailView.places || {})) {
    for (const place of lettering.names || []) {
      const b = placeBox(place), spot = fracToWorld(+id, (b[0] + b[2]) / 2, (b[1] + b[3]) / 2);
      if (spot) {
        out.push([spot.inst, spot.n, spot.w]);
        names.push(place.lines.map((l) => l.text).join(" "));
      }
    }
  }
  for (const id of Object.keys(app.detailView.capitals || {})) {
    const m = app.maps[id], w = m?.world;
    if (w) {
      out.push([m.instance, w.top, w.bottom, w.left, w.right]);
      names.push(m.name);
    }
  }
  travellers.setPlaces(out, names);
}
const setRelief = (on) => options.set("lighting", on);

const trees = new Trees({ address: pictureSrc,
  json: (url) => Promise.resolve(getJson(url, { share: true })).catch(() => null),
  image: (url) => { const img = new Image(), entry = { img, ok: false, gone: false }; img.onload = () => { entry.ok = true; redraw(); };
    img.onerror = () => { entry.gone = true; }; img.src = url; return entry; },
  canvas: (w, h) => Object.assign(document.createElement("canvas"), { width: w, height: h }), drawn: () => redraw(),
  ink: (a) => tint("black", a), indexed: () => options.refresh() });
const treeLayer = document.createElement("canvas");
const thinLayer = document.createElement("canvas");
let thinned = null;
let treesLaid = 0;
function drawTrees(size, scale, alpha) {
  treesLaid = 0;
  thinned = null;
  const info = app.maps[app.displayMap];
  const underground = undergroundShown(app.displayMap, size);
  alpha *= 1 - underground.inside;
  if (!(alpha > 0) || !app.treesOn || !reliefWanted(info, app.detail.drawn, mapTiles.renders(info?.instance))) return 0;
  trees.start();
  if (!trees.ready()) return 0;
  if (treeLayer.width !== canvas.width || treeLayer.height !== canvas.height) Object.assign(treeLayer, { width: canvas.width, height: canvas.height });
  const g = treeLayer.getContext("2d");
  const w = info.world, corners = [[0, 0], [W, 0], [0, H], [W, H]].map(([x, y]) => toMap(x, y, size, scale)).map((p) => toWorld(w, p.x, p.y));
  const frame = { instance: info.instance, corners, tileYards: app.tiles.tileYards,
    at: (n, wv) => { const [fx, fy] = toFrac(w, n, wv); return [fx * size.w, fy * size.h]; },
    k: [size.w / Math.abs(w.left - w.right), size.h / Math.abs(w.top - w.bottom)] };
  const thin = { ...frame, roofsOf: (instance, key) => trees.roofs(instance, key) };
  const seen = app.disp && !app.replayYou ? toScreen(app.disp.x, app.disp.y, size, scale) : null, spot = seen?.every(Number.isFinite) ? seen : null;
  const lay = (out) => {
    g.setTransform(1, 0, 0, 1, 0, 0);
    g.clearRect(0, 0, treeLayer.width, treeLayer.height);
    g.setTransform(ctx.getTransform());
    g.save();
    g.beginPath();
    g.rect(-20 * size.w, -20 * size.h, 41 * size.w, 41 * size.h);
    citySheets(app.displayMap, size).filter((c) => c.fade > 0).forEach((c) => g.rect(...c.at));
    g.clip("evenodd");
    const drawn = trees.paint(g, frame, out);
    if (drawn) cutBelow(g, underground.below);
    g.restore();
    if (!drawn) return 0;
    if (app.treesThin) trees.thin(g, { ...thin, you: spot && spot.map((v) => v * dpr), dpr });
    ctx.save();
    ctx.setTransform(1, 0, 0, 1, 0, 0);
    ctx.globalAlpha = alpha;
    ctx.drawImage(treeLayer, 0, 0);
    ctx.restore();
    return drawn;
  };
  const under = lay(false), standing = lay(true);
  if (standing) treesLaid = alpha;
  if (app.treesThin && under + standing) {
    const k = RELIEF.scale, m = ctx.getTransform(), w = Math.max(1, Math.round(W * k)), h = Math.max(1, Math.round(H * k));
    if (thinLayer.width !== w || thinLayer.height !== h) Object.assign(thinLayer, { width: w, height: h });
    const t = thinLayer.getContext("2d"), f = k / dpr;
    t.setTransform(m.a * f, m.b * f, m.c * f, m.d * f, m.e * f, m.f * f);
    thinned = { canvas: thinLayer, stamp: trees.heights(t, { ...thin, you: spot && spot.map((v) => v * k), dpr: k }) };
  }
  return under + standing;
}

function keyLines(bar) {
  for (const tick of bar.querySelectorAll(".key-tick")) {
    const words = [...tick.querySelectorAll(".key-tick-run > span")].map((s) => s.textContent);
    tick.insertAdjacentHTML("beforeend", `<span class="key-fixed" aria-hidden="true">${esc(andList(words, "&"))}</span>`);
  }
}
function keyNames(bar, fixed) {
  bar.classList.toggle("names-fixed", fixed);
  if (!fixed) return;
  const ticks = [...bar.querySelectorAll(".key-tick")];
  bar.style.setProperty("--key-name-w", `${Math.max(0, ...ticks.map((t) => t.querySelector(".key-tick-run").offsetWidth))}px`);
  for (const t of ticks) {
    const line = t.querySelector(".key-fixed");
    line.style.setProperty("--slide", String(Math.max(0, line.scrollWidth - line.clientWidth)));
  }
}
keyLines($("top-keys"));

function fitBar(bar, keys) {
  bar.classList.remove("two-rows");
  bar.classList.toggle("two-rows", keys.scrollWidth > keys.clientWidth);
}
{
  const bar = document.querySelector("header.bar"), keys = $("top-keys");
  const fit = new ResizeObserver(() => fitBar(bar, keys));
  for (const el of [document.documentElement, bar.querySelector(".brand-name"), ...keys.children,
                    ...bar.querySelectorAll(".end-keys > .key, #signal, #btn-reload, #btn-options")]) fit.observe(el);
}

const options = new OptionsWindow({ box: $("options"), key: $("btn-options"), kept: keptOr, keep: keepIn, esc, put: setHtml,
  send: (changes) => postJson("/api/settings", { set: changes }, { quiet: true })?.catch(() => {}),
  help: (key) => helpButton(key),
  hooks: { lighting: { can: () => relief.ready(), changed: (on) => { app.reliefOn = on; redraw(); } },
    keynames: { changed: (look) => keyNames($("top-keys"), look === "fixed") },
    mapkinds: { changed: (kinds) => { app.mapKinds = kinds; preloadFarTiles(); requestUpdate(); } },
    night: { changed: (on) => { app.nightOn = on; mapLight.nightShown?.(on); redraw(); } },
    zoneglow: { changed: (on) => { app.zoneGlowOn = on; redraw(); } },
    continentnames: { changed: (on) => { app.continentNamesOn = on; redraw(); } },
    zonenames: { changed: (on) => { app.zoneNamesOn = on; redraw(); } },
    citybanners: { changed: (on) => { app.cityBannersOn = on; redraw(); } },
    placenames: { changed: (on) => { app.placeNamesOn = on; redraw(); } },
    trees: { changed: (on) => { app.treesOn = on; redraw(); } },
    treesThin: { changed: (on) => { app.treesThin = on; redraw(); } },
    canopy: { choices: () => { trees.start(); return trees.canopyZones().map((id) => ({ value: id, name: app.maps[id]?.name ?? String(id) }))
      .sort((a, b) => a.name.localeCompare(b.name)); }, changed: (off) => trees.canopy(off) },
    importexport: { panel: packPanel, click: packClick, input: keepPackPath } } });
$("btn-options").addEventListener("click", () => options.toggle());
$("options").addEventListener("click", (e) => options.click(e));
$("options").addEventListener("input", (e) => options.input(e));
closable(LAYER.options, () => options.isOpen, () => options.close());
const reliefPointer = () => { if (relief.pointerLit) redraw(); };
canvas.addEventListener("pointermove", reliefPointer);
canvas.addEventListener("pointerleave", reliefPointer);
function lightCentre(info, middle) {
  const me = followed(), mine = me && app.maps[me.map];
  if (app.view.follow && mine?.world && mine.instance === info.instance) return toWorld(mine.world, me.x, me.y);
  return middle;
}

const LIGHT_ZONE = { every: 150 };
let lightZone = { key: null, at: -Infinity, zone: null };
function areaLight(info, size, scale, centre) {
  if (!lightTint.instances[info.instance]) return null;
  const now = performance.now(), cv = clearView(), v = app.view;
  const key = [app.displayMap, app.mapKinds, zoneShapesRead, W, H, cv.l, cv.r, cv.t, cv.b, size.w, size.h, scale, v.cx, v.cy, v.rot, centre.n, centre.w].join();
  if (key !== lightZone.key && now - lightZone.at >= LIGHT_ZONE.every) {
    const lies = new Map(), ground = (z) => {
      if (!lies.has(z)) lies.set(z, cityZone(z) ?? z);
      return lies.get(z);
    };
    const middle = { inst: info.instance, ...centre }, at = zoneNamed(middle, false);
    const spots = viewZones(size, scale).spots.map((s) => ({ ...s, zone: ground(s.zone) }));
    lightZone = { key, at: now, zone: tintZone(spots, { ...middle, zone: at == null ? null : ground(at) }) };
  } else if (key !== lightZone.key) redraw();
  const zone = lightZone.zone, inst = zone ? zone.spot.inst : info.instance;
  const spot = zone && { ...zone.spot, zone: zone.zone, z: lightOf(inst).ground(inst, zone.spot.n, zone.spot.w) };
  const hour = mapLight.hour();
  return lightTint.at(inst, hour, oneLightAt(SUN.NOON).sin, spot, now, tintShare(zone?.share), 1 - lampAt(hour, app.nightOn !== false));
}
let litBeside = [];
let relights = [], layLight = null, layCores = null;
function paintKept(light, look) {
  const due = () => {
    if (light.againIn != null) groundTicks.light = Math.min(groundTicks.light ?? Infinity, performance.now() + light.againIn);
    if (light.coresIn != null) groundTicks.cores = Math.min(groundTicks.cores ?? Infinity, performance.now() + light.coresIn);
  };
  const kept = {
    light,
    paint: () => { const lit = light.paint(look); due(); return lit; },
    flicker: () => { light.flicker(); due(); },
  };
  const lit = kept.paint();
  light.takeRelit();
  if (lit) relights.push(kept);
  return lit;
}
const handMoves = () => !!drag?.moved || viewSettling() > 0;
function relitOn(lights) {
  const each = lights.map((l) => l.takeRelit()).filter(Boolean);
  if (each.includes(true)) return true;
  const box = patchBox(each);
  return box ? [Math.floor(box[0] * dpr), Math.floor(box[1] * dpr), Math.ceil(box[2] * dpr), Math.ceil(box[3] * dpr)] : false;
}
function drawRelief(size, scale, alpha, frames = []) {
  cloudsLit = false;
  seaJob = null;
  storm.see(null);
  litBeside = [];
  relights = [];
  layLight = layCores = null;
  const info = app.maps[app.displayMap];
  const under = undergroundShown(app.displayMap, size);
  alpha *= 1 - under.inside;
  if (!(alpha > 0) || !app.reliefOn || !reliefWanted(info, app.detail.drawn, mapTiles.renders(info?.instance))) return;
  const at = (x, y) => { const p = toMap(x, y, size, scale); return toWorld(info.world, p.x, p.y); };
  const tint = areaLight(info, size, scale, lightCentre(info, at(W / 2, H / 2)));
  if (lightTint.easing) redraw();
  const view = seaFrame(frames, size, scale), hour = mapLight.hour(), night = app.nightOn !== false, sky = oneLightAt(hour, night);
  storm.see({ ...sea.stormIn({ ...view, width: W, height: H, tileYards: app.tiles.tileYards, grid: STORM.grid, from: STORM.from, level: stormLevel }),
    width: W, height: H, zoom: app.view.zoom, clear: app.clearShown || clearView(), night: sky.night, moon: !!sky.moon, keep: cloudShare(hour, night), still: lessMotion(), now: performance.now() });
  seaJob = { frames, size, scale, view, area: tint ? tint.area : null, light: oneLightAt(hour, night, storm.sun()), hour, alpha, shaded: seaTicks.on, lit: false };
  if (info.world && !clouds.areaReady(info.instance, screenTiles(info, size, scale))) return;
  const takes = cloudsTakeShare(info);
  walkTravellers();
  const lit = paintKept(relief, { instance: info.instance, has: (key) => mapTiles.hasRender(info.instance, key) && clouds.tileReady(info.instance, key), tileYards: app.tiles.tileYards, at,
    width: W, height: H, hour: mapLight.hour(), pointer: mapLight.at, lantern: mapLight.lanternNow(), night: app.nightOn !== false,
    gauntlet: mapLight.gauntletShade(), cloudShare: takes, tint, probe: app.disp ? toScreen(app.disp.x, app.disp.y, size, scale) : null, torches, travellers,
    shaded: seaTicks.on, sun: storm.sun(), thinned, held: handMoves() });
  if (!lit) return;
  seaJob.lit = true;
  cloudsLit = takes > 0;
  litBeside = frames.map((f) => lightBeside(f, size, scale, tint)).filter(Boolean);
  const sheets = citySheets(app.displayMap, size).filter((c) => c.fade > 0), drawn = under.below.filter((c) => c.art);
  const laid = (paint) => (box = null) => {
    ctx.save();
    ctx.beginPath();
    ctx.rect(-20 * size.w, -20 * size.h, 41 * size.w, 41 * size.h);
    sheets.forEach((c) => ctx.rect(...c.at));
    under.below.filter((c) => !c.art).forEach((c) => ctx.rect(...c.at));
    ctx.clip("evenodd");
    const frame = ctx.getTransform();
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    ctx.globalAlpha = alpha;
    paint(frame, box);
    ctx.restore();
  };
  layLight = laid((frame, box) => relief.drawOn(ctx, W, H, drawn.length ? (light) => cutDrawings(light, drawn, frame) : null, litBeside, box));
  layCores = laid(() => relief.coresOn(ctx, W, H, litBeside));
}
function lightBeside(f, size, scale, tint) {
  const inst = f.info.instance, light = lightOf(inst);
  if (!clouds.areaReady(inst, screenTiles(f.info, f.size, f.scale, f.toMap))) return null;
  const at = (x, y) => { const p = f.toMap(x, y); return toWorld(f.info.world, p.x, p.y); };
  const yours = app.disp && app.maps[app.dispMap]?.instance === inst;
  const lit = paintKept(light, { instance: inst, has: (key) => mapTiles.hasRender(inst, key) && clouds.tileReady(inst, key), tileYards: app.tiles.tileYards, at,
    width: W, height: H, hour: mapLight.hour(), pointer: mapLight.at, lantern: mapLight.lanternNow(), night: app.nightOn !== false,
    gauntlet: mapLight.gauntletShade(), cloudShare: cloudsTakeShare(f.info), tint, probe: yours ? toScreen(app.disp.x, app.disp.y, size, scale) : null,
    torches, travellers, shaded: seaTicks.on, sun: storm.sun(), held: handMoves() });
  if (!lit) return null;
  const [x0, y0, x1, y1] = f.ground, corners = [[x0, y0], [x1, y0], [x1, y1], [x0, y1]].map(([fx, fy]) => toScreen(fx, fy, size, scale, app.displayMap));
  return { light, inst, part: (g, k) => {
    corners.forEach(([sx, sy], i) => (i ? g.lineTo(sx * k, sy * k) : g.moveTo(sx * k, sy * k)));
    g.closePath();
  } };
}
const sea = new Sea({ canvas: document.createElement("canvas"), bytes: getBytes, drawn: () => redraw(),
  picture: (instance, key) => { const e = mapTiles.load("render", instance, key); return e.ok ? e.img : null; },
  image: (url) => new Promise((done) => { const img = new Image(); img.onload = () => done(img); img.onerror = () => done(null); img.src = url; }), address: pictureSrc });
let seaJob = null;
const storm = new Storm({ picture: (url) => { const img = new Image(); img.src = url; return img; },
  index: () => getJson("/art/storm/index.json"), drawn: () => redraw(), rgb: tintRgb("light-storm"),
  pieces: () => [...(clouds.pics?.values() || [])].filter((p) => p.ok).map((p) => p.img) });
const seaClock = () => (performance.now() / 1000) % 3600;
function seaFrame(frames, size, scale) {
  const info = app.maps[app.displayMap], r = regionOf(info.instance, app.maps), yards = r && worldYards(r.map, app.maps);
  const own = (x, y) => { const p = toMap(x, y, size, scale); return { inst: info.instance, ...toWorld(info.world, p.x, p.y) }; };
  const part = (inst) => ({ instance: inst, rendered: (key) => mapTiles.hasRender(inst, key), hidden: (key) => !clouds.tileReady(inst, key) });
  const circles = clouds.index?.circles || {};
  if (!yards) {
    const mine = circles[info.instance];
    return { at: own, onWorld: null, ground: [{ ...part(info.instance), place: [1, 1, 0, 0], rect: [0, 0, 1, 1] }],
      circles: mine ? [{ circle: mine, place: [1, 1, 0, 0] }] : [] };
  }
  const at = (x, y) => worldAt(yards, ...worldToFrac(r.map, own(x, y))), onWorld = (n, w) => worldSpot(yards, n, w);
  const place = (inst) => seaPlace((p) => fromWorldMap(inst, ...onWorld(p.n, p.w)));
  const placed = (inst) => ({ ...part(inst), place: place(inst), rect: regionOf(inst, app.maps).ui });
  const turning = Object.keys(circles).map(Number).filter((inst) => regionOf(inst, app.maps)).map((inst) => ({ circle: circles[inst], place: place(inst) }));
  return { at, onWorld, ground: [placed(info.instance), ...frames.map((f) => placed(f.info.instance))], circles: turning };
}
const seaGiants = new SeaGiants({ drawn: () => redraw(), address: pictureSrc,
  image: (url) => new Promise((done) => { const img = new Image(); img.onload = () => done(img); img.onerror = () => done(null); img.src = url; }) });
function loadSeaGiants() {
  return getJson("art/seagiants/index.json", { key: null })?.then((index) => { seaGiants.setIndex(index); redraw(); }).catch(() => {});
}
function drawSea(size) {
  const job = seaJob;
  if (!job) { seaGiants.away(); return false; }
  const cv = app.clearShown || clearView();
  const view = job.view;
  const shade = job.lit && job.shaded && relief.shaded ? relief.withBeside("shade", litBeside, W) : null;
  const shown = sea.paint({ tileYards: app.tiles.tileYards, at: view.at, onWorld: view.onWorld, ground: view.ground, circles: view.circles, width: W, height: H,
    light: stormSeaLight(seaLight(job.light, job.area, job.hour), storm.flash(performance.now())), t: lessMotion() ? 0 : seaClock(), hours: Date.now() / 3.6e6, day: job.hour / 24,
    middle: { x: (cv.l + cv.r) / 2, y: (cv.t + cv.b) / 2 },
    shade: shade ? { canvas: shade, made: [relief, ...litBeside.map((b) => b.light)].reduce((s, l) => s + l.shadeMade, 0) } : null,
    clouds: cloudMask.on ? { canvas: cloudMask.canvas, share: cloudMask.share, made: cloudMask.made } : null });
  if (!shown) { seaGiants.away(); return false; }
  if (job.lit && !job.shaded) redraw();
  seaTicks.last = performance.now();
  ctx.save();
  cutCitySheets(size);
  ctx.globalAlpha = job.alpha;
  if (belowShown()) ctx.globalCompositeOperation = "source-atop";
  if (treesLaid > 0) {
    ctx.setTransform(1, 0, 0, 1, 0, 0);
    ctx.drawImage(waterUnderTrees(), 0, 0);
  } else {
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    sea.drawOn(ctx, W, H);
  }
  ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
  seaGiants.drawOn(ctx, { at: view.at, onWorld: view.onWorld, width: W, height: H, fitPx: (job.size.w * job.scale) / app.view.zoom,
    mapYards: (map) => { const b = app.maps[map]?.world; return b ? b.left - b.right : 0; } });
  ctx.restore();
  return true;
}
const seaUnder = document.createElement("canvas");
function waterUnderTrees() {
  if (seaUnder.width !== canvas.width || seaUnder.height !== canvas.height) Object.assign(seaUnder, { width: canvas.width, height: canvas.height });
  const g = seaUnder.getContext("2d");
  g.setTransform(1, 0, 0, 1, 0, 0);
  g.globalAlpha = 1;
  g.globalCompositeOperation = "copy";
  sea.drawOn(g, seaUnder.width, seaUnder.height);
  g.globalCompositeOperation = "destination-out";
  g.globalAlpha = treesLaid;
  g.drawImage(treeLayer, 0, 0);
  g.globalCompositeOperation = "source-over";
  g.globalAlpha = 1;
  return seaUnder;
}
const seaTicks = { on: false, last: 0 };
const groundTicks = { timer: 0, frame: 0, clouds: null, light: null, cores: null, fire: null };
function groundDue() {
  const now = performance.now(), due = [];
  if (groundTicks.clouds != null) due.push(now + groundTicks.clouds - clouds.now());
  if (seaTicks.on && !lessMotion()) due.push(seaTicks.last + 1000 / sea.fps);
  const stormDue = storm.next(now);
  if (stormDue != null) due.push(stormDue);
  if (groundTicks.light != null) due.push(groundTicks.light);
  if (groundTicks.cores != null) due.push(groundTicks.cores);
  if (groundTicks.fire != null) due.push(groundTicks.fire);
  return Math.min(Infinity, ...due);
}
function askGroundTick() {
  clearTimeout(groundTicks.timer);
  dropFrame(groundTicks.frame);
  groundTicks.timer = groundTicks.frame = 0;
  if (document.hidden) return;
  const wait = groundDue() - performance.now();
  if (wait === Infinity) return;
  if (wait > 2) groundTicks.timer = setTimeout(() => { groundTicks.timer = 0; groundTicks.frame = askFrame(groundTick); }, wait - 2);
  else groundTicks.frame = askFrame(groundTick);
}
function groundTick() {
  groundTicks.frame = 0;
  if (frameAsked || document.hidden || !glowLayer.whole) return;
  const at = performance.now();
  if (groundTicks.light != null && at >= groundTicks.light) {
    groundTicks.light = null;
    walkTravellers();
    if (!relights.every((kept) => kept.paint())) { redraw(); return; }
  }
  if (groundTicks.cores != null && at >= groundTicks.cores) {
    groundTicks.cores = null;
    relights.forEach((kept) => kept.flicker());
  }
  const relit = relitOn(relights.map((kept) => kept.light));
  groundTicks.clouds = null;
  cloudHold.moving = false;
  step("ground", () => groundUnder(relit));
  askGroundTick();
  if (youLightOwed()) redraw();
}
const drawingsCut = document.createElement("canvas");
function cutDrawings(light, drawn, frame) {
  if (drawingsCut.width !== light.width || drawingsCut.height !== light.height) Object.assign(drawingsCut, { width: light.width, height: light.height });
  const g = drawingsCut.getContext("2d"), k = light.width / canvas.width;
  g.setTransform(1, 0, 0, 1, 0, 0);
  g.globalCompositeOperation = "copy";
  g.drawImage(light, 0, 0);
  g.globalCompositeOperation = "source-over";
  g.setTransform(frame.a * k, frame.b * k, frame.c * k, frame.d * k, frame.e * k, frame.f * k);
  cutBelow(g, drawn);
  g.setTransform(1, 0, 0, 1, 0, 0);
  return drawingsCut;
}

const scanScroll = new ScanScroll({ box: $("ah-scroll"), grip: $("ah-grip"), page: $("ah-page"), tape: $("ah-tape"),
  roll: $("ah-roll"), caption: $("ah-caption"),
  stream: $("ah-stream"), frames: [...document.querySelectorAll("#ah-scroll .ah-frame")], you: () => app.youOnScreen,
  ask: (url) => getJson(url, { key: "auction feed", quiet: true }), canvas: () => document.createElement("canvas"),
  still: () => lessMotion(), toast: showToast });
on("snapshot", (snap) => scanScroll.report(snap.auction));

const blood = new Blood({ layer: $("blood"), doc: document, picture: (src) => Object.assign(new Image(), { src }),
  kept: () => keptOr("cc.blood", null), keep: (v) => keepIn("cc.blood", v), drawn: () => redraw(),
  aspect: () => innerWidth / Math.max(1, innerHeight) });
function bloodSpot() {
  const p = !inDungeon() && playerWorld();
  return p ? { ...p, floor: null } : null;
}

function resize() {
  const r = canvas.getBoundingClientRect();
  dpr = window.devicePixelRatio || 1;
  W = r.width; H = r.height;
  canvas.width = Math.round(W * dpr);
  canvas.height = Math.round(H * dpr);
  mapLight.resize(W, H, dpr);
  scanScroll.resize(W, H, dpr, clearView(false));
}
new ResizeObserver(() => { resize(); redraw(); }).observe(canvas);

function imgSize(entry) {
  return entry?.ok ? { w: entry.img.naturalWidth, h: entry.img.naturalHeight } : DEFAULT_IMG;
}

const BAND_GIVE = 0.25, BAND_POP = 0.45, BAND_WAIT_MS = 320;
function bandScale() {
  if (app.mapKinds === "detailed") return 1;
  return 1 - BAND_GIVE * (1 - Math.exp(-app.band.pull * 4));
}

function scaleFor(size) {
  return Math.min(W / size.w, H / size.h) * app.view.zoom * (app.view.world ? 1 : bandScale());
}

function toScreen(fx, fy, size, s, from = app.state?.map) {
  const v = app.view;
  if (app.displayMap != null && from != null && app.displayMap !== from) [fx, fy] = convertFrac(from, app.displayMap, fx, fy, app.maps, worldRound());
  const px = (fx - v.cx) * size.w * s, py = (fy - v.cy) * size.h * s;
  const c = Math.cos(v.rot), n = Math.sin(v.rot);
  return [W / 2 + px * c - py * n, H / 2 + px * n + py * c];
}

function toMap(sx, sy, size, s) {
  const v = app.view;
  const dx = sx - W / 2, dy = sy - H / 2;
  const c = Math.cos(v.rot), n = Math.sin(v.rot);
  return { x: v.cx + (dx * c + dy * n) / (size.w * s), y: v.cy + (-dx * n + dy * c) / (size.h * s) };
}

const GLIDE_LEFT = 1e-6, GLIDE_TURN = 1e-4;
function smooth(dt) {
  const s = app.state;
  if (!s?.pos) { app.disp = null; return false; }
  const k = 1 - Math.exp(-dt * 10);
  const facing = s.facing ?? app.disp?.facing ?? 0;
  const jumped = app.disp && Math.hypot(s.pos.x - app.disp.x, s.pos.y - app.disp.y) > 0.05;
  if (!app.disp || app.dispMap !== s.map || jumped) {
    app.disp = { x: s.pos.x, y: s.pos.y, facing };
    app.dispMap = s.map;
  } else {
    app.disp.x += (s.pos.x - app.disp.x) * k;
    app.disp.y += (s.pos.y - app.disp.y) * k;
    app.disp.facing += wrap(facing - app.disp.facing) * k;
  }
  const gliding = Math.hypot(s.pos.x - app.disp.x, s.pos.y - app.disp.y) > GLIDE_LEFT || Math.abs(wrap(facing - app.disp.facing)) > GLIDE_TURN;
  if (!gliding) Object.assign(app.disp, { x: s.pos.x, y: s.pos.y, facing });
  const now = performance.now();
  const last = app.trail[app.trail.length - 1];
  if (!blood.bleeding && now - app.lastTrail > 500 && (!last || Math.hypot(last.x - app.disp.x, last.y - app.disp.y) > 0.0015)) {
    app.trail.push({ x: app.disp.x, y: app.disp.y });
    if (app.trail.length > 400) app.trail.shift();
    app.lastTrail = now;
  }
  return gliding;
}

function drawGrid(size, s) {
  ctx.strokeStyle = tint("slate", 0.55);
  ctx.lineWidth = 1 / s;
  for (let i = 0; i <= 10; i++) {
    ctx.beginPath(); ctx.moveTo((i / 10) * size.w, 0); ctx.lineTo((i / 10) * size.w, size.h); ctx.stroke();
    ctx.beginPath(); ctx.moveTo(0, (i / 10) * size.h); ctx.lineTo(size.w, (i / 10) * size.h); ctx.stroke();
  }
}

const classColor = () => CLASS_COLORS[app.status?.className];
const youLook = () => arrowLit(arrowLook(classColor(), { lit: tint("arrow-lit"), gold: tint("gold"), shade: tint("arrow-shade"), rim: tint("black") }),
  youLight.level);

const youLight = { level: 0, speed: 0, at: 0 };
const youLightGoal = () => arrowLightGoal(mapLight.lamp(), shadeAtYou());
const youLightOwed = () => !arrowLightSettled(youLight.level, youLightGoal()) || relief.probeStale || litBeside.some((b) => b.light.probeStale);
on("animate", (now) => {
  const dt = youLight.at && now > youLight.at ? Math.min(0.1, (now - youLight.at) / 1000) : 1 / 60;
  youLight.at = now;
  arrowLightStep(youLight, youLightGoal(), dt);
  return youLightOwed();
});
const YOU_GHOST = 0.45;
function drawPlayer(x, y, angle, ghost = false) {
  const look = youLook(), shadow = mapLight.arrowShadow(), grounded = !!app.youGrounded;
  mapLight.showYou(x, y, JSON.stringify([+angle.toFixed(3), look, shadow, grounded, ghost]), (g, px, py) => {
    if (mapLight.fire && !ghost) paintFire(g, px, py, angle, mapLight.now(), (a) => tint("campfire", a));
    if (ghost) g.globalAlpha = YOU_GHOST;
    if (!grounded) paintArrow(g, px, py, angle, look, shadow, dpr);
    paintArrowGlow(g, px, py, angle, classColor() || tint("gold"), dpr);
    g.globalAlpha = 1;
  }, dpr);
}

function drawYouOnGround(size, scale, terrain) {
  app.youGrounded = false;
  const shown = app.maps[app.displayMap];
  if (!app.disp || app.replayYou || !(terrain > 0) || !reliefWanted(shown, app.detail.drawn, mapTiles.renders(shown?.instance))) return false;
  const [x, y] = toScreen(app.disp.x, app.disp.y, size, scale);
  ctx.save();
  ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
  paintArrow(ctx, x, y, -app.disp.facing + app.view.rot, youLook(), mapLight.arrowShadow(), dpr);
  ctx.restore();
  app.youGrounded = true;
  return true;
}

function arrowGlow(snap, now = Date.now() / 1000) {
  return !!snap?.campfire && !liveFires(snap.fires, now).length;
}


const FIRE_SPREAD = 0.3, FIRE_RADIUS = 12;
let firePointer = null;
function liveFires(fires, now = Date.now() / 1000) {
  return (fires || []).filter((f) => f.ends > now);
}
function fireTip(f, now) {
  const mins = Math.max(1, Math.ceil((f.ends - now) / 60));
  return { name: f.name || "Your campfire", sub: `goes out in ${mins} minute${mins === 1 ? "" : "s"}`, cat: "campfire",
           label: "Your campfire burns where you stood when you placed it", x: f.x, y: f.y };
}
function drawFires(s, size, scale, now = Date.now() / 1000) {
  if (app.dungeon) return;
  for (const f of liveFires(app.fires, now)) {
    const [x, y] = toScreen(f.x, f.y, size, scale, f.map);
    if (x < -FIRE_RADIUS * 2 || y < -FIRE_RADIUS * 2 || x > W + FIRE_RADIUS * 2 || y > H + FIRE_RADIUS * 2) continue;
    redrawIn((f.ends - now) * 1000);
    glowLayer.fires.push({ x, y });
    if (firePointer && Math.hypot(firePointer.x - x, firePointer.y - y) < POI_SIZE / 2) {
      const left = f.ends - now;
      drawCountdown(x, y, 1 - left / (f.ends - f.at), tint("campfire"), hms(left), tint("ivory"));
      redrawIn(1000 * hmsTurns(left));
    }
    noteMark(x, y, fireTip(f, now));
  }
}
function layFires(fires) {
  groundTicks.fire = null;
  if (!fires.length) return;
  const now = mapLight.now();
  groundTicks.fire = performance.now() + FIRE_GLOW.step - (now % FIRE_GLOW.step);
  ctx.save();
  ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
  for (const { x, y } of fires) paintFire(ctx, x, y, 0, now, (a) => tint("campfire", a), FIRE_SPREAD, FIRE_RADIUS);
  ctx.restore();
}
function fireMouse(e) {
  if (e.type === "pointerleave") { firePointer = null; return; }
  const r = canvas.getBoundingClientRect();
  firePointer = { x: e.clientX - r.left, y: e.clientY - r.top };
  if (liveFires(app.fires).length) redraw();
}
canvas.addEventListener("pointermove", fireMouse);
canvas.addEventListener("pointerleave", fireMouse);

const ghostWaits = () => !!app.state?.flags?.ghost;
const isCorpseRun = (g) => !!g?.fromGame && app.gameGuide?.source === "corpse";
const GHOST_GREY = "grayscale(1) opacity(0.6)";
function drawWaiting(waits, f) {
  if (!waits) return f();
  ctx.save(); ctx.filter = GHOST_GREY;
  try { f(); } finally { ctx.restore(); }
}
function offView(x, y) {
  const cv = clearView();
  return x < cv.l || y < cv.t || x > cv.r || y > cv.b;
}
function drawEdgeHint(tx, ty, label, color = tint("cyan")) {
  const inset = 34, cv = clearView();
  const cx = (cv.l + cv.r) / 2, cy = (cv.t + cv.b) / 2;
  const dx = tx - cx, dy = ty - cy;
  const t = Math.min(((cv.r - cv.l) / 2 - inset) / Math.abs(dx || 1e-6), ((cv.b - cv.t) / 2 - inset) / Math.abs(dy || 1e-6));
  const x = cx + dx * t, y = cy + dy * t;
  const a = Math.atan2(dy, dx);
  ctx.save();
  ctx.translate(x, y); ctx.rotate(a);
  ctx.beginPath(); ctx.moveTo(14, 0); ctx.lineTo(-8, -11); ctx.lineTo(-3, 0); ctx.lineTo(-8, 11); ctx.closePath();
  ctx.lineWidth = 3; ctx.strokeStyle = tint("black"); ctx.stroke();
  ctx.fillStyle = color; ctx.fill();
  ctx.restore();
  ctx.font = "600 13px 'Open Sans', Arial, sans-serif";
  ctx.textAlign = "center"; ctx.textBaseline = "middle";
  const ly = y + (y > cy ? -22 : 22);
  ctx.lineWidth = 4; ctx.strokeStyle = tint("black"); ctx.strokeText(label, x, ly);
  ctx.fillStyle = tint("ivory"); ctx.fillText(label, x, ly);
  return [x, y];
}

function sheetDepth(size, scale) {
  const w = app.maps[app.displayMap]?.world, f = mapFades.list("over:city:").find((c) => c.data.seen);
  if (!w || !f) return 1;
  const px = scale * size.w / Math.abs(w.left - w.right), at = Math.max(HIGH_AT_PX_PER_YARD, TILES_FROM_ZOOM * cityFit(f.data.id));
  return pointerDepth(app.view.zoom * at / px, MIN_ZOOM, MAX_ZOOM, false);
}
function yardPx(mapId, size, scale) {
  const w = app.maps[mapId]?.world;
  return w ? scale * size.w / Math.abs(w.left - w.right) : 0;
}
const detailBy = (was, pxPerYard, zoom) => (pxPerYard > HIGH_AT_PX_PER_YARD && zoom >= TILES_FROM_ZOOM ? "high"
  : pxPerYard < LOW_AT_PX_PER_YARD || zoom < DRAWN_BELOW_ZOOM ? "low" : was);

function chooseDetail(mapId, size, scale) {
  const d = app.detail;
  const w = app.maps[mapId]?.world;
  const hasTiles = w && mapTiles.has(app.maps[mapId].instance);
  let next = d.current;
  const info = app.maps[mapId];
  if (app.view.drawnHeld && app.view.continent) next = "low";
  else if (info?.type === 4 && info.tilesOnly) next = "high";
  else if (info?.type === 4 && !info.high) next = "low";
  else if (!hasTiles && !info?.high) next = "low";
  else if (!w) next = "low";
  else next = detailBy(d.current, scale * size.w / Math.abs(w.left - w.right), app.view.zoom);
  d.current = next;
  const both = hasTiles && !app.view.world && info.type !== 4 && !info.tilesOnly && !info.high;
  d.drawn = !both || app.mapKinds === "both" ? next : app.mapKinds === "paper" ? "low" : "high";
}
function cityStep(id, was, pxPerYard) {
  if (!app.detail.cityOn) return undefined;
  if (app.mapKinds === "paper") return "low";
  if (app.mapKinds === "detailed") return "high";
  if (app.detail.current !== "high") return "low";
  return detailBy(was, pxPerYard, pxPerYard / cityFit(id));
}

const stitched = new Map();
const MAX_STITCHED = 6;
function stitchedEntry(src, keep = false) {
  let entry = stitched.get(src);
  if (entry) stitched.delete(src);
  else {
    const img = new Image();
    entry = { img, ok: false, keep: false };
    const done = () => { entry.ok = true; redraw(); };
    img.onload = () => (img.decode ? img.decode().then(done, done) : done());
    img.src = src;
  }
  entry.keep ||= keep;
  stitched.set(src, entry);
  for (const [key, old] of stitched) {
    if (stitched.size <= MAX_STITCHED) break;
    if (!old.keep) stitched.delete(key);
  }
  return entry;
}
function drawStitched(src, bounds, info, size, backdrop, { area = null, alpha = 1, scale = 0 } = {}) {
  const w = info.world, entry = stitchedEntry(src);
  if (!entry.ok || !w || !alpha) return;
  ctx.globalAlpha = alpha;
  if (!backdrop) {
  } else if (area) {
    const box = boundsRect(w, area, size);
    if (scale) shadowRect(box, scale);
    ctx.fillStyle = backdrop;
    ctx.fillRect(...box);
  } else {
    ctx.fillStyle = backdrop;
    ctx.fillRect(0, 0, size.w, size.h);
  }
  const at = boundsRect(w, bounds, size);
  if (scale) drawShadow(entry.img, at, scale);
  ctx.drawImage(entry.img, ...at);
  ctx.globalAlpha = 1;
}

const MAP_SHADOW = { alpha: 0.7, strength: 1, color: tint("black", 0.7), full: tint("black", 0.7), blur: 18, x: 6, y: 8 };
function castMapShadow({ x, y, strength, rgb, blur }) {
  Object.assign(MAP_SHADOW, { x, y, strength, blur, color: lightRgba(rgb, MAP_SHADOW.alpha * strength), full: lightRgba(rgb, MAP_SHADOW.alpha) });
}
const SHADOW_STEP = 1.25, SHADOW_CELL = 3, MAX_SHADOW_SIDE = 1024, MAX_SHADOWS = 4;
const mapShadows = new Map();
function mapShadow(img, perPx) {
  const step = Math.round(Math.log(perPx) / Math.log(SHADOW_STEP)), soft = +(MAP_SHADOW.blur / perPx).toPrecision(2);
  const kept = mapShadows.get(img);
  if (kept?.step === step && kept.color === MAP_SHADOW.full && kept.soft === soft) return kept;
  const iw = img.naturalWidth, ih = img.naturalHeight, onScreen = SHADOW_STEP ** step;
  const k = Math.min(onScreen / SHADOW_CELL, MAX_SHADOW_SIDE / Math.max(iw, ih));
  const blur = soft * k, pad = Math.ceil(blur * 1.5) + 2;
  const canvas = document.createElement("canvas");
  canvas.width = Math.ceil(iw * k) + 2 * pad;
  canvas.height = Math.ceil(ih * k) + 2 * pad;
  const g = canvas.getContext("2d");
  g.filter = `blur(${blur / 2}px)`;
  g.drawImage(img, pad, pad, iw * k, ih * k);
  g.filter = "none";
  g.globalCompositeOperation = "source-in";
  g.fillStyle = MAP_SHADOW.full;
  g.fillRect(0, 0, canvas.width, canvas.height);
  const made = { step, color: MAP_SHADOW.full, soft, canvas, k, pad };
  mapShadows.delete(img);
  mapShadows.set(img, made);
  if (mapShadows.size > MAX_SHADOWS) mapShadows.delete(mapShadows.keys().next().value);
  return made;
}
function drawShadow(img, at, scale) {
  const iw = img.naturalWidth, ih = img.naturalHeight;
  if (!iw || !ih || !MAP_SHADOW.strength) return;
  const ux = at[2] / iw, uy = at[3] / ih, s = mapShadow(img, scale * (ux + uy) / 2);
  const c = Math.cos(app.view.rot), n = Math.sin(app.view.rot);
  const ox = (MAP_SHADOW.x * c + MAP_SHADOW.y * n) / scale, oy = (MAP_SHADOW.y * c - MAP_SHADOW.x * n) / scale;
  const quality = ctx.imageSmoothingQuality, alpha = ctx.globalAlpha;
  ctx.imageSmoothingQuality = "low";
  ctx.globalAlpha = alpha * MAP_SHADOW.strength;
  ctx.drawImage(s.canvas, at[0] - s.pad / s.k * ux + ox, at[1] - s.pad / s.k * uy + oy, s.canvas.width / s.k * ux,
    s.canvas.height / s.k * uy);
  ctx.imageSmoothingQuality = quality;
  ctx.globalAlpha = alpha;
}
function shadowRect(at, scale, clip = true) {
  if (!MAP_SHADOW.strength) return;
  const reach = (MAP_SHADOW.blur * 1.5 + Math.hypot(MAP_SHADOW.x, MAP_SHADOW.y)) / scale;
  ctx.save();
  if (clip) {
    ctx.beginPath();
    ctx.rect(at[0] - reach, at[1] - reach, at[2] + 2 * reach, at[3] + 2 * reach);
    ctx.rect(...at);
    ctx.clip("evenodd");
  }
  ctx.shadowColor = MAP_SHADOW.color;
  ctx.shadowBlur = MAP_SHADOW.blur * dpr;
  ctx.shadowOffsetX = MAP_SHADOW.x * dpr;
  ctx.shadowOffsetY = MAP_SHADOW.y * dpr;
  ctx.fillStyle = tint("black");
  ctx.fillRect(...at);
  ctx.restore();
}
function boundsRect(w, b, size) {
  const [x0, y0] = toFrac(w, b.top, b.left), [x1, y1] = toFrac(w, b.bottom, b.right);
  return [x0 * size.w, y0 * size.h, x1 * size.w - x0 * size.w, y1 * size.h - y0 * size.h];
}

function drawDungeonHigh(info, size) {
  const mini = floorMinimap(info);
  drawStitched(mini.src, mini.world, info, size, info.tilesOnly ? null : tint("backdrop"));
}

app.indoor = null;
app.indoorZone = false;
let indoorAsked = null, indoorFrom = null;
let cityIn = null, cityFrom = null;
const INDOOR_FILL = 0.8;
const INDOOR_CLOSEST = 100;
const OPEN_CITIES = new Set([1453, 1454]);
function indoorsOf(s = app.state) {
  const r = app.replayYou;
  if (r) {
    const w = !r.hidden && fracToWorld(r.map, r.x, r.y);
    return w ? { map: r.map, inst: w.inst, here: [w.n, w.w], indoors: !!(r.fl & RP_INDOORS_BIT), sub: r.sub } : null;
  }
  return liveIndoors(s);
}
function liveIndoors(s) {
  return s && { map: s.map, inst: s.instance?.id, here: s.instance?.world, indoors: !!s.minimap?.indoors, sub: s.subzone };
}
function insideAt(at) { return !!at?.indoors && !OPEN_CITIES.has(at.map); }
function checkIndoors(s = app.state) {
  const at = indoorsOf(s), here = at?.here;
  if (app.dungeon || !insideAt(at) || !here) { leaveIndoors(); indoorAsked = null; return; }
  if (indoorAsked && indoorAsked.inst === at.inst && Math.hypot(here[0] - indoorAsked.x, here[1] - indoorAsked.y) < 40) return;
  const asking = getJson(`/api/indoor?inst=${at.inst}&x=${here[0]}&y=${here[1]}`, { key: "indoor" });
  if (!asking) return;
  const asked = indoorAsked = { inst: at.inst, x: here[0], y: here[1] };
  asking.then((found) => {
    if (indoorAsked !== asked) return;
    if (!found) return leaveIndoors();
    const first = !app.indoor;
    app.indoor = { ...found, inst: at.inst };
    if (first && !app.indoorZone) zoomIndoors(app.indoor);
    renderLevelKeys();
  }, () => { if (indoorAsked === asked) indoorAsked = null; });
  renderLevelKeys();
}

const ZONE_NAME = tint("ivory");
const ZONE_LABEL_CUT = 0.3;
const ZONE_GLOW_CUT = 0.08;
const ZONE_GLOW_SPREAD = 8;
const zoneShines = {};
let zoneShapesRead = 0;
function zoneGlow(id) {
  const m = app.maps[id];
  if (!m?.highlight) return null;
  const src = pictureSrc(`/highlight/${m.highlight}.png`, m.highlightPicture);
  let g = zoneShines[id];
  if (g?.src !== src) {
    g = zoneShines[id] = { src, img: new Image(), mask: null };
    g.img.onload = () => {
      try {
        const c = document.createElement("canvas");
        c.width = c.height = 128;
        const x = c.getContext("2d");
        x.drawImage(g.img, 0, 0, 128, 128);
        const d = x.getImageData(0, 0, 128, 128).data, mask = new Uint8Array(128 * 128);
        let max = 0;
        for (let i = 0; i < mask.length; i++) max = Math.max(max, mask[i] = Math.max(d[i * 4], d[i * 4 + 1], d[i * 4 + 2]));
        let sx = 0, sy = 0, sw = 0;
        for (let i = 0; i < mask.length; i++) {
          const b = mask[i];
          if (b > max * ZONE_LABEL_CUT) { sx += (i % 128) * b; sy += Math.floor(i / 128) * b; sw += b; }
        }
        g.hit = spreadGlow(mask, ZONE_GLOW_SPREAD, max || 1);
        Object.assign(g, { rgb: d, max: max || 1 });
        if (sw) { g.cx = (sx / sw + 0.5) / 128; g.cy = (sy / sw + 0.5) / 128; }
      } catch (e) { g.hit = null; }
      zoneShapesRead++;
      redraw();
    };
    g.img.src = src;
  }
  return g;
}
const SHAPE_GAIN = 1.6, SHAPES_KEPT = 240;
const zoneShapes = new Map();
function zoneShape(id, rgb) {
  const g = zoneGlow(id);
  if (!g?.img.complete || !g.img.naturalWidth) return null;
  const key = `${g.src}|${rgb.join(",")}`;
  let c = zoneShapes.get(key);
  if (c) return c;
  const w = g.img.naturalWidth, h = g.img.naturalHeight;
  c = document.createElement("canvas");
  c.width = w; c.height = h;
  const x = c.getContext("2d", { willReadFrequently: true });
  x.drawImage(g.img, 0, 0);
  try {
    const d = x.getImageData(0, 0, w, h), p = d.data;
    let max = 1;
    for (let i = 0; i < p.length; i += 4) max = Math.max(max, p[i], p[i + 1], p[i + 2]);
    for (let i = 0; i < p.length; i += 4) {
      const b = Math.max(p[i], p[i + 1], p[i + 2]) / max;
      [p[i], p[i + 1], p[i + 2]] = rgb;
      p[i + 3] = 255 * Math.min(1, b * SHAPE_GAIN);
    }
    x.putImageData(d, 0, 0);
  } catch (e) {
    return null;
  }
  zoneShapes.set(key, c);
  if (zoneShapes.size > SHAPES_KEPT) zoneShapes.delete(zoneShapes.keys().next().value);
  return c;
}

function spreadGlow(mask, r, max) {
  const across = new Float32Array(128 * 128), out = new Float32Array(128 * 128);
  for (let y = 0; y < 128; y++) {
    for (let x = 0; x < 128; x++) {
      let m = 0;
      for (let k = Math.max(0, x - r); k <= Math.min(127, x + r); k++) m = Math.max(m, mask[y * 128 + k]);
      across[y * 128 + x] = m;
    }
  }
  for (let x = 0; x < 128; x++) {
    for (let y = 0; y < 128; y++) {
      let m = 0;
      for (let k = Math.max(0, y - r); k <= Math.min(127, y + r); k++) m = Math.max(m, across[k * 128 + x]);
      out[y * 128 + x] = m / max;
    }
  }
  return out;
}

function continentZones(cont, size) {
  const out = [];
  for (const [id, m] of Object.entries(app.maps)) {
    if (m.parent !== cont || m.type !== 3 || !m.highlight || !m.world) continue;
    const a = worldToFrac(cont, { inst: m.instance, n: m.world.top, w: m.world.left });
    const b = worldToFrac(cont, { inst: m.instance, n: m.world.bottom, w: m.world.right });
    if (!a || !b) continue;
    const w = b[0] - a[0];
    out.push({ id: +id, x0: a[0], y0: a[1], w, h: w * size.w / size.h, boxH: b[1] - a[1] });
  }
  return out;
}
function zoneLabelsOn() {
  const info = app.maps[app.displayMap];
  return !!info && info.type === 2 && (app.detail.current === "low" || app.detail.drawn === "low") && !app.dungeon && !app.view.world;
}
function zoneUnder(fx, fy, size, cont = app.displayMap) {
  let best = null, bestB = ZONE_GLOW_CUT;
  for (const z of continentZones(cont, size)) {
    const u = (fx - z.x0) / z.w, v = (fy - z.y0) / z.h;
    if (u < 0 || v < 0 || u >= 1 || fy - z.y0 >= z.boxH) continue;
    const g = zoneGlow(z.id);
    const b = g?.hit ? g.hit[Math.floor(v * 128) * 128 + Math.floor(u * 128)] : 0;
    if (b > bestB) { bestB = b; best = z.id; }
  }
  return best;
}
app.hoverZone = null;
app.litZone = null;
const shownZone = () => app.hoverZone ?? app.litZone;
function hoverZoneAt(e) {
  const size = app.curSize;
  let id = null;
  if (size && zoneLabelsOn() && !drag?.moved) {
    const r = canvas.getBoundingClientRect(), m = toMap(e.clientX - r.left, e.clientY - r.top, size, scaleFor(size));
    id = zoneUnder(m.x, m.y, size);
  }
  if (id !== app.hoverZone) { app.hoverZone = id; redraw(); }
}
canvas.addEventListener("pointermove", hoverZoneAt);
canvas.addEventListener("pointerleave", () => { if (app.hoverZone != null) { app.hoverZone = null; redraw(); } });
function zoomIntoZone(mx, my) {
  const size = app.curSize;
  if (!size || !zoneLabelsOn()) return false;
  const at = toMap(mx, my, size, scaleFor(size));
  const id = zoneUnder(at.x, at.y, size), spot = id != null && fracToWorld(app.displayMap, at.x, at.y);
  const f = spot && worldToFrac(id, spot), zw = app.maps[id]?.world;
  if (!f || !zw) return false;
  setFollow(false);
  leaveContinent(MIN_ZOOM, id);
  app.view.zoom = detailZoom(id);
  [app.view.cx, app.view.cy] = f;
  viewMoved();
  return true;
}
function detailZoom(id) {
  return Math.min(MAX_ZOOM, Math.max(MIN_ZOOM, HIGH_AT_PX_PER_YARD * 1.15 / widestPerYard(id)));
}
function widestPerYard(id, inst = app.maps[id]?.instance) {
  const m = app.maps[id], r = m?.world ? { ui: [0, 0, 1, 1], world: m.world } : m?.regions?.find((x) => x.instance === inst);
  if (!r) return 0;
  const size = imgSize(mapImage(id));
  return Math.min(W / size.w, H / size.h) * bandScale() * (r.ui[2] - r.ui[0]) * size.w / Math.abs(r.world.left - r.world.right);
}
function zoomKeepingScale(from, zoom, to, inst = app.maps[to]?.instance) {
  const was = widestPerYard(from, inst), now = widestPerYard(to, inst);
  return Math.min(MAX_ZOOM, Math.max(MIN_ZOOM, was > 0 && now > 0 ? zoom * was / now : MIN_ZOOM));
}
function zoomIntoCapital(mx, my) {
  const size = app.curSize;
  if (!size) return false;
  const hit = capitalNames(size, scaleFor(size)).find((c) => Math.abs(mx - c.x) <= c.w / 2 && Math.abs(my - c.y) <= c.h / 2);
  const city = hit && app.maps[hit.id], b = city?.world;
  const zone = b && [cityZone(hit.id), hit.id].find((m) => app.maps[m]?.world);
  const f = zone != null && worldToFrac(zone, { inst: city.instance, n: (b.top + b.bottom) / 2, w: (b.left + b.right) / 2 });
  if (!f) return false;
  const cv = clearView(false);
  setFollow(false);
  leaveContinent(MIN_ZOOM, zone);
  app.view.zoom = Math.min(MAX_ZOOM, Math.max(TILES_FROM_ZOOM * 1.15, detailZoom(zone), fitZoom(zone, b, cv)));
  centreInClear(f, imgSize(mapImage(zone)), cv);
  if (CITIES[hit.id]) askCityPic(hit.id);
  viewMoved();
  return true;
}
const fitZoom = (id, b, cv) => Math.min((cv.r - cv.l) / Math.abs(b.left - b.right), (cv.b - cv.t) / Math.abs(b.top - b.bottom)) / widestPerYard(id);

const ZONE_GLOW_PEAK = 64, ZONE_GLOW_EDGE = 0.1, ZONE_NIGHT_DIM = 0.6;
function zoneOwnership(self, others) {
  const own = new Float32Array(128 * 128);
  for (let j = 0; j < 128; j++) {
    const fy = self.y0 + ((j + 0.5) / 128) * self.h;
    if (fy - self.y0 >= self.boxH) continue;
    for (let i = 0; i < 128; i++) {
      const fx = self.x0 + ((i + 0.5) / 128) * self.w, mine = self.hit[j * 128 + i];
      let best = 0;
      for (const q of others) {
        const u = (fx - q.x0) / q.w, v = (fy - q.y0) / q.h;
        if (u < 0 || v < 0 || u >= 1 || v >= 1 || fy - q.y0 >= q.boxH) continue;
        best = Math.max(best, q.hit[Math.floor(v * 128) * 128 + Math.floor(u * 128)]);
      }
      own[j * 128 + i] = Math.min(1, Math.max(0, (mine - best) / ZONE_GLOW_EDGE));
    }
  }
  return own;
}
function zoneGlowPixels(rgb, max, own) {
  const out = new Uint8ClampedArray(128 * 128 * 4), k = ZONE_GLOW_PEAK / max;
  for (let i = 0; i < own.length; i++) {
    for (let c = 0; c < 3; c++) out[i * 4 + c] = rgb[i * 4 + c] * k * own[i];
    out[i * 4 + 3] = 255;
  }
  return out;
}
const zoneLitKept = new Map();
function zoneLit(cont, size, id) {
  const zones = continentZones(cont, size), self = zones.find((q) => q.id === id), g = self && zoneGlow(id);
  const key = `${cont} ${id} ${(size.w / size.h).toFixed(4)}`;
  if (zoneLitKept.has(key)) return zoneLitKept.get(key);
  if (!g) return null;
  const near = zones.filter((q) => q.id !== id && q.x0 < self.x0 + self.w && q.x0 + q.w > self.x0 && q.y0 < self.y0 + self.h && q.y0 + q.h > self.y0);
  const glows = near.map((q) => ({ ...q, hit: zoneGlow(q.id)?.hit }));
  if (!g.hit || !g.rgb || glows.some((q) => !q.hit)) return null;
  const c = document.createElement("canvas");
  c.width = c.height = 128;
  const x = c.getContext("2d"), img = x.getImageData(0, 0, 128, 128);
  img.data.set(zoneGlowPixels(g.rgb, g.max, zoneOwnership({ ...self, hit: g.hit }, glows)));
  x.putImageData(img, 0, 0);
  zoneLitKept.set(key, c);
  return c;
}
const zoneGlowShare = (hour, night) => 1 - ZONE_NIGHT_DIM * lampAt(hour, night);

function wantZones() {
  const on = zoneLabelsOn() ? [[`zones:${app.displayMap}`, { data: { map: app.displayMap, zone: shownZone() } }]] : [];
  mapFades.show("zones:", new Map(on), FADE_OVER);
}
function zoneSets(size) {
  const out = [];
  for (const f of mapFades.list("zones:")) {
    const at = f.data.map === app.displayMap ? [0, 0, 1, 1] : mapOn(f.data.map, app.displayMap);
    if (at) out.push({ cont: f.data.map, at, own: { w: (at[2] - at[0]) * size.w, h: (at[3] - at[1]) * size.h }, zone: f.data.zone, strength: f.at });
  }
  return out;
}
function drawZoneGlow(size) {
  if (app.zoneGlowOn === false) return;
  for (const set of zoneSets(size)) {
    const z = set.zone != null && continentZones(set.cont, set.own).find((q) => q.id === set.zone);
    if (!z) continue;
    ctx.save();
    ctx.translate(set.at[0] * size.w, set.at[1] * size.h);
    paintZoneGlow(set.cont, set.own, z, set.strength);
    ctx.restore();
  }
}
function paintZoneGlow(cont, size, z, strength) {
  const lit = zoneLit(cont, size, z.id);
  if (!lit) return;
  paintGlow((g) => {
    for (let k = 0; k < 2; k++) g.drawImage(lit, z.x0 * size.w, z.y0 * size.h, z.w * size.w, z.h * size.h);
  }, { alpha: ctx.globalAlpha * strength * zoneGlowShare(mapLight.hour(), app.nightOn !== false), light: true });
}
let serifFont = null;
function zoneLabels(size, scale, { cont, own, zone }) {
  const w = app.maps[cont].world, pic = imgSize(mapImage(cont));
  const yards = w && Math.abs(w.left - w.right);
  const widest = Math.min(W / pic.w, H / pic.h) * pic.w / yards, now = scale * own.w / yards;
  const all = !!yards && now >= Math.sqrt(widest * HIGH_AT_PX_PER_YARD), labels = [];
  for (const z of continentZones(cont, own)) {
    if (!all && z.id !== zone) continue;
    const g = zoneGlow(z.id);
    if (g?.cx == null) continue;
    const [x, y] = toScreen(z.x0 + g.cx * z.w, z.y0 + g.cy * z.h, size, scale, cont);
    if (x < -100 || y < -30 || x > W + 100 || y > H + 30) continue;
    labels.push({ id: z.id, x, y });
  }
  return { all, labels };
}

function drawZoneNames(size, scale) {
  if (app.zoneNamesOn === false) return;
  const sets = zoneSets(size);
  if (!sets.length) return;
  serifFont ||= getComputedStyle(document.documentElement).getPropertyValue("--serif").trim() || "Georgia, serif";
  ctx.textAlign = "center"; ctx.textBaseline = "middle"; ctx.lineJoin = "round";
  for (const set of sets) {
    ctx.globalAlpha = set.strength;
    if (!set.strength) continue;
    for (const { id, x, y } of zoneLabels(size, scale, set).labels) {
      const name = app.maps[id].name, big = id === set.zone;
      ctx.font = `${big ? 22 : 18}px ${serifFont}`;
      ctx.lineWidth = 4; ctx.strokeStyle = tint("black", 0.85); ctx.strokeText(name, x, y);
      ctx.fillStyle = ZONE_NAME; ctx.fillText(name, x, y);
      const levels = app.maps[id].levels;
      if (!levels) continue;
      const text = zoneRangeText(levels), ly = y + (big ? 20 : 17);
      ctx.font = `${big ? 16 : 14}px ${serifFont}`;
      ctx.lineWidth = 3.5; ctx.strokeText(text, x, ly);
      ctx.fillStyle = zoneThreat(levels); ctx.fillText(text, x, ly);
    }
  }
  ctx.globalAlpha = 1;
  ctx.lineJoin = "miter";
}

const ZONE_OVER = 3;
const THREAT = { grey: tint("quality-poor"), green: tint("quest-green"), yellow: tint("quest-yellow"), red: tint("threat-red") };
function grayLevel(level) {
  if (level <= 5) return 0;
  if (level <= 39) return level - 5 - Math.floor(level / 10);
  if (level <= 59) return level - 1 - Math.floor(level / 5);
  return level - 9;
}
function zoneThreat([lo, hi], level = app.state?.level) {
  if (!level) return ZONE_NAME;
  if (hi <= grayLevel(level)) return THREAT.grey;
  if (lo >= level + ZONE_OVER) return THREAT.red;
  return hi < level - 2 ? THREAT.green : THREAT.yellow;
}
const zoneRangeText = ([lo, hi]) => lo === hi ? `${lo}` : `${lo}-${hi}`;

const CITY_HOLD = 1.15;
const cityReach = (pxPerYard, zoom) => Math.min(pxPerYard / LOW_AT_PX_PER_YARD, zoom / DRAWN_BELOW_ZOOM);
function chooseCities(mapId, size, scale) {
  const info = app.maps[mapId], w = info?.world, d = app.detail, steps = {};
  const pxPerYard = w ? scale * size.w / Math.abs(w.left - w.right) : 0;
  const reach = w && !app.view.world ? cityReach(pxPerYard, app.view.zoom) : 0;
  d.cityOn = reach >= 1 || (!!d.cityOn && reach >= 1 / CITY_HOLD);
  if (d.cityOn) {
    for (const id of citiesOn(info.instance)) {
      if (cityInView(id, mapId, size, scale)) steps[id] = cityStep(id, d.city[id] || "low", pxPerYard);
    }
  }
  d.city = steps;
}
const citiesOn = (inst) => Object.keys(app.maps).filter((id) => app.maps[id].instance === inst && cityZone(id) != null)
  .map(Number);
function cityInView(id, mapId, size, scale) {
  const b = app.maps[id].world, w = app.maps[mapId].world;
  const corners = [[b.top, b.left], [b.top, b.right], [b.bottom, b.left], [b.bottom, b.right]]
    .map(([n, x]) => toScreen(...toFrac(w, n, x), size, scale, mapId));
  const xs = corners.map((c) => c[0]), ys = corners.map((c) => c[1]);
  return Math.max(...xs) >= 0 && Math.min(...xs) <= W && Math.max(...ys) >= 0 && Math.min(...ys) <= H;
}
function cityFit(id) {
  const size = imgSize(mapImage(id)), yd = mapYards(id);
  return Math.min(W / size.w, H / size.h) * size.w / yd.w;
}

const UNDERGROUND = {};
function loadUnderground() {
  return getJson("art/underground/index.json", { key: null })?.then((drawn) => { Object.assign(UNDERGROUND, drawn || {}); redraw(); })
    .catch(() => {});
}
on("start", loadUnderground);
on("start", () => startDirector());
const CITIES = {
  1455: { name: "Ironforge", above: "Dun Morogh", at: [0, -4821.8, -1155.4, 502.2], auto: true },
  1458: { name: "Undercity", above: "Tirisfal Glades", at: [0, 1568.6, 268.0, -43.1], auto: true },
  1454: { name: "Orgrimmar", above: "Durotar", at: [1, 1677.6, -4315.7, 61.2], auto: false },
};
function youIndoors() {
  const s = app.state;
  if (CITIES[s?.map]?.auto) return true;
  return s?.minimap?.indoors ?? null;
}
app.cityPics = {};
app.cityChoice = {};
let cityShown = null;
function cityBelow(id) {
  const choice = app.cityChoice[id];
  return choice ? choice === "below" : CITIES[id].auto;
}
function citiesBelowShown() {
  if (app.dungeon || app.indoor || app.view.world || app.detail.drawn !== "high") return [];
  return Object.keys(app.detail.city).map(Number).filter((id) => CITIES[id] && app.detail.city[id] === "high");
}
function showCity() {
  const here = zoneInView(), all = citiesBelowShown();
  const id = all.includes(here) ? here : all[0] ?? null;
  if (id === cityShown) return;
  if (cityShown != null) delete app.cityChoice[cityShown];
  cityShown = id;
  renderLevelKeys();
  requestUpdate();
}
function askCity() {
  for (const id of new Set([cityShown, ...citiesAhead()])) askCityPic(id);
}
on("update", askCity);
function citiesAhead() {
  const info = app.maps[app.displayMap], size = app.curSize;
  if (![2, 3].includes(info?.type) || !info.world || !size || app.view.world || app.dungeon) return [];
  const scale = scaleFor(size);
  return citiesOn(info.instance).filter((id) => CITIES[id]?.auto && cityInView(id, app.displayMap, size, scale));
}
function askCityPic(id) {
  if (id == null || app.cityPics[id] || !cityBelow(id)) return;
  const [inst, x, y, z] = CITIES[id].at;
  askFor(`city:${id}`, () => getJson(`/api/indoor?inst=${inst}&x=${x}&y=${y}&z=${z}`, { key: null }).then((found) => {
    if (!found) throw new Error(`no picture of ${CITIES[id].name} yet`);
    app.cityPics[id] = found;
    stitchedEntry(`/indoor/${found.image}`, true);
  }))?.catch(() => {});
}
function toggleCity(id) {
  if (!CITIES[id]) return;
  app.cityChoice[id] = cityBelow(id) ? "above" : "below";
  renderLevelKeys();
}

function renderLevelKeys() {
  const box = $("levelkeys"), at = indoorsOf();
  const html = app.indoor && !app.dungeon ? [
    `<button class="key small floor" data-level="inside" aria-pressed="${!app.indoorZone}" title="The map of the cave or building the character is in (C)">${app.indoorZone ? "" : '<span class="hotkey">C</span>'}${esc(at?.sub || "Inside")}</button>`,
    `<button class="key small floor" data-level="zone" aria-pressed="${app.indoorZone}" title="The zone map, for picking a spot outside (C)">${app.indoorZone ? '<span class="hotkey">C</span>' : ""}${esc(mapName(at?.map))}</button>`,
  ].join("") : cityShown != null ? cityKey(cityShown) : "";
  setHtml(box, html);
  box.hidden = !html;
}

function cityKey(id) {
  const c = CITIES[id], below = cityBelow(id);
  return `<button class="key small floor" data-city="${id}" title="${below ? `The ground above ${c.name}` : `${c.name} itself, as the game's minimap shows the city inside`} (C)"><span class="hotkey">C</span>${esc(below ? c.above : c.name)}</button>`;
}

function setIndoorZone(on) {
  if (!app.indoor || on === app.indoorZone) return;
  app.indoorZone = on;
  const v = app.view;
  if (on) {
    if (indoorFrom != null && v.follow && !v.continent && !v.world) v.zoom = indoorFrom;
    indoorFrom = null;
  } else zoomIndoors(app.indoor);
  renderLevelKeys();
}

$("levelkeys").addEventListener("click", (e) => {
  const b = e.target.closest("button[data-level]"), c = e.target.closest("button[data-city]");
  if (b) setIndoorZone(b.dataset.level === "zone");
  else if (c) toggleCity(+c.dataset.city);
});

function zoomIndoors(i) {
  const was = zoomToFit(i.world);
  if (was != null) indoorFrom = was;
}
function zoomToFit(b, least = 0) {
  const v = app.view, map = mapYards(shownMap(followed()?.map ?? app.state?.map));
  if (!v.follow || v.continent || v.world || !map || !b) return null;
  const size = app.curSize || DEFAULT_IMG, fit = Math.min(W / size.w, H / size.h);
  const bw = Math.abs(b.left - b.right), bh = Math.abs(b.top - b.bottom);
  const pxPerYard = Math.min(INDOOR_FILL * Math.min(W / bw, H / bh), Math.min(W, H) / INDOOR_CLOSEST);
  const zoom = Math.min(MAX_ZOOM, Math.max(least, pxPerYard * map.w / size.w / fit));
  if (!(zoom > v.zoom)) return null;
  const was = v.zoom;
  v.zoom = zoom;
  return was;
}

function leaveIndoors() {
  const v = app.view;
  if (indoorFrom != null && v.follow && !v.continent && !v.world) v.zoom = indoorFrom;
  app.indoor = null;
  app.indoorZone = false;
  indoorFrom = null;
  renderLevelKeys();
}

const OVER_BACKDROP = tint("backdrop", 0.86);
function wantOverMaps(mapId, size, scale) {
  const info = app.maps[mapId], w = info?.world, shown = new Map();
  if (w) {
    const pxPerYard = scale * size.w / Math.abs(w.left - w.right);
    for (const id of citiesOn(info.instance)) {
      const seen = cityInView(id, mapId, size, scale);
      const step = seen ? app.detail.city[id] : cityStep(id, "low", pxPerYard);
      shown.set(`over:city:${id}`, { to: step === "low" ? 1 : 0, now: !seen, data: { id, seen } });
    }
    const i = app.indoor;
    if (i && !app.indoorZone && info.instance === i.inst && !app.view.world) {
      shown.set(`over:indoor:${i.image}`, { data: { image: i.image, world: i.world, inst: i.inst } });
    }
    for (const id of citiesBelowShown()) {
      const art = cityBelow(id) && UNDERGROUND[id], pic = cityBelow(id) && app.cityPics[id];
      const src = art ? pictureSrc(`art/underground/${art.image}`, art.v) : pic && `/indoor/${pic.image}`;
      if (!src || !stitchedEntry(src, true).ok) continue;
      const a = app.maps[id].world, b = art ? art.world : pic.world;
      const area = { left: Math.max(a.left, b.left), right: Math.min(a.right, b.right), top: Math.max(a.top, b.top), bottom: Math.min(a.bottom, b.bottom) };
      const image = art ? art.image : pic.image;
      shown.set(`over:below:${image}`, { data: { image, src, art: !!art, world: b, area, inst: app.maps[id].instance } });
    }
  }
  mapFades.show("over:", shown, FADE_OVER);
}
function citySheets(mapId, size, scale = 0) {
  const info = app.maps[mapId], w = info?.world, out = [];
  if (!w) return out;
  for (const f of mapFades.list("over:city:")) {
    const city = app.maps[f.data.id], entry = f.data.seen && city?.instance === info.instance ? mapImage(f.data.id) : null;
    if (!entry?.ok || !f.at) continue;
    const at = boundsRect(w, city.world, size);
    out.push({ at, img: paperOf(entry, perPicturePx(entry, at[2], scale)), fade: f.at });
  }
  return out;
}
function rectOnScreen([x, y, w, h], size, scale) {
  const corner = (px, py) => toScreen(px / size.w, py / size.h, size, scale, app.displayMap);
  const at = corner(x, y), right = corner(x + w, y), down = corner(x, y + h);
  return { at, u: [right[0] - at[0], right[1] - at[1]], v: [down[0] - at[0], down[1] - at[1]] };
}
function undergroundShown(mapId, size) {
  const info = app.maps[mapId], w = info?.world, out = { inside: app.dungeon ? 1 : 0, below: [] };
  if (!w || app.dungeon) return out;
  for (const f of mapFades.list("over:indoor:")) if (f.data.inst === info.instance) out.inside = Math.max(out.inside, f.at || 0);
  for (const f of mapFades.list("over:below:")) {
    if (!(f.data.inst === info.instance && f.at > 0)) continue;
    if (f.data.art) out.below.push({ at: boundsRect(w, f.data.world, size), fade: f.at, art: stitchedEntry(f.data.src).img });
    else out.below.push({ at: boundsRect(w, f.data.area || f.data.world, size), fade: f.at });
  }
  return out;
}
function cutBelow(g, below) {
  g.save();
  g.globalCompositeOperation = "destination-out";
  for (const c of below) {
    g.globalAlpha = c.fade;
    if (c.art) g.drawImage(c.art, ...c.at);
    else g.fillRect(...c.at);
  }
  g.restore();
}
function drawOverMaps(mapId, size, scale) {
  const info = app.maps[mapId], w = info?.world;
  if (!w) return;
  for (const { at, img, fade } of citySheets(mapId, size, scale)) {
    ctx.globalAlpha = fade;
    shadowRect(at, scale, fade < 1);
    ctx.drawImage(img, ...at);
  }
  ctx.globalAlpha = 1;
  for (const f of [...mapFades.list("over:indoor:"), ...mapFades.list("over:below:")]) {
    const d = f.data;
    if (d.inst !== info.instance) continue;
    if (d.art) drawStitched(d.src, d.world, info, size, null, { alpha: f.at });
    else drawStitched(`/indoor/${d.image}`, d.world, info, size, OVER_BACKDROP, { area: d.area, alpha: f.at });
  }
}

function detailedOnly() {
  return app.mapKinds === "detailed" && app.displayMap !== WORLD_MAP && !app.dungeon;
}
function worldRender() {
  return app.mapKinds === "detailed" && app.displayMap === WORLD_MAP && !app.dungeon;
}
function seaFill() {
  return `rgb(${mapTiles.sea().join(", ")})`;
}
function drawWorldRender(size, scale) {
  const n = app.detailView.chunk || 8, T = app.tiles?.tileYards, seam = 0.75 / scale;
  const sea = worldSea();
  if (sea.ok) ctx.drawImage(sea.img, 0, 0, size.w, size.h);
  for (const r of T && clouds.ready ? app.maps[WORLD_MAP]?.regions || [] : []) {
    for (const key of app.detailView.overviews?.render?.[r.instance] || []) {
      const entry = detailPic(`render/${r.instance}/${key}.webp`);
      if (!entry.ok) continue;
      const [cx, cy] = key.split("_").map(Number);
      if (!clouds.areaReady(r.instance, [cx * n, cx * n + n - 1, cy * n, cy * n + n - 1])) continue;
      const [fx0, fy0] = placeIn(r.world, (32 - cy * n) * T, (32 - cx * n) * T, ...r.ui);
      const [fx1, fy1] = placeIn(r.world, (32 - cy * n - n) * T, (32 - cx * n - n) * T, ...r.ui);
      ctx.drawImage(entry.img, fx0 * size.w, fy0 * size.h, (fx1 - fx0) * size.w + seam, (fy1 - fy0) * size.h + seam);
    }
  }
}
const WORLD_SEA = "art/world/sea_world_paper.png";
let worldArt = null;
function worldSea() {
  if (!worldArt) {
    const img = new Image();
    worldArt = { img, ok: false };
    img.onload = () => { worldArt.ok = true; redraw(); };
    img.src = WORLD_SEA;
  }
  return worldArt;
}
const below = new Below({ el: $("map-below"), canvas: newCanvas, doc: document });
function floats(inst) {
  return !!app.maps && mapTiles.renders(inst) && !regionOf(inst, app.maps);
}
function belowShown() {
  const m = app.maps?.[app.displayMap];
  return !app.dungeon && !!m?.world && !m.high && floats(m.instance) && mapFades.get("terrain") > 0;
}
function belowLight() {
  const hour = mapLight.hour(), night = app.nightOn !== false, one = oneLightAt(hour, night), round = (q) => +q.toFixed(3);
  const blend = one.mix > 0 && mapLight.own ? relief.nightFilter(one.mix) : null;
  return { k: oneLightRgb(1, one).map((q) => round(Math.min(1, q))), night: blend ? `url(#${blend})` : "none",
           haze: one.tint.map((q) => Math.round(255 * Math.min(1, q * one.bright))), share: round(cloudShare(hour, night)) };
}
function cloudPiece(band, px) {
  const i = clouds.index.pieces.findIndex((p) => p.band === band);
  return i < 0 ? null : clouds.pictureFor(i, px);
}
function islandShape(info) {
  const box = mapTiles.renderBox(info.instance), n = app.detailView.chunk || 8, T = app.tiles.tileYards, px = BELOW.shape;
  if (!box) return null;
  const [c0, r0, c1, r1] = box, blocks = [];
  for (const key of app.detailView.overviews?.render?.[info.instance] || []) {
    const entry = detailPic(`render/${info.instance}/${key}.webp`);
    if (!entry.ok) continue;
    const [cx, cy] = key.split("_").map(Number);
    blocks.push({ img: entry.img, parts: voidParts(info.instance, cx * n, cy * n, n), at: [(cx * n - c0) * px, (cy * n - r0) * px, n * px, n * px] });
  }
  if (!blocks.length) return null;
  const mid = toWorld(info.world, 0.5, 0.5);
  return { img: below.silhouette(blocks, (c1 - c0 + 1) * px, (r1 - r0 + 1) * px, tint("black")),
           box: [mid.w - (32 - c0) * T, mid.n - (32 - r0) * T, mid.w - (31 - c1) * T, mid.n - (31 - r1) * T] };
}
function paintBelow(size, scale) {
  const far = app.maps?.[BELOW.distance.map], region = far && regionOf(far.instance, app.maps);
  if (!belowShown() || !region || !app.tiles) return below.hide();
  const info = app.maps[app.displayMap], v = app.view, T = app.tiles.tileYards, w = info.world, n = app.detailView.chunk || 8;
  const mid = [(0.5 - v.cx) * Math.abs(w.left - w.right), (0.5 - v.cy) * Math.abs(w.top - w.bottom)];
  const farSize = imgSize(mapImage(BELOW.distance.map));
  const frame = belowFrame({ zoom: v.zoom, mid, base: yardPx(BELOW.distance.map, farSize, Math.min(W / farSize.w, H / farSize.h) * BELOW.distance.zoom) });
  const perFrac = [Math.abs(region.world.left - region.world.right) / (region.ui[2] - region.ui[0]),
                   Math.abs(region.world.top - region.world.bottom) / (region.ui[3] - region.ui[1])];
  const world = [], regions = clouds.ready ? app.maps[WORLD_MAP]?.regions || [] : [];
  for (const r of regions) {
    for (const key of app.detailView.overviews?.render?.[r.instance] || []) {
      const [cx, cy] = key.split("_").map(Number);
      if (!clouds.areaReady(r.instance, [cx * n, cx * n + n - 1, cy * n, cy * n + n - 1])) continue;
      const entry = detailPic(`render/${r.instance}/${key}.webp`);
      if (entry.ok) world.push({ img: entry.img, from: placeIn(r.world, (32 - cy * n) * T, (32 - cx * n) * T, ...r.ui),
                                 to: placeIn(r.world, (32 - cy * n - n) * T, (32 - cx * n - n) * T, ...r.ui) });
    }
  }
  const shape = islandShape(info), shift = shadowShift(groundLight(...lightNow())), px = yardPx(app.displayMap, size, scale);
  const between = BELOW.clouds.between.map((cloud) => ({ cloud, img: cloudPiece(cloud.band, cloud.yards * px) })).filter((c) => c.img);
  const over = (g, [kx, ky], at, reach) => {
    const view = [[-1, -1], [1, -1], [-1, 1], [1, 1]].map(([sx, sy]) => [at[0] + (sx * reach) / kx, at[1] + (sy * reach) / ky]);
    for (const r of regions) {
      if (!clouds.has(r.instance)) continue;
      const on = (col, row) => { const [fx, fy] = placeIn(r.world, (32 - row) * T, (32 - col) * T, ...r.ui); return [(fx - at[0]) * kx, (fy - at[1]) * ky]; };
      const tiles = view.map(([x, y]) => toWorld(r.world, (x - r.ui[0]) / (r.ui[2] - r.ui[0]), (y - r.ui[1]) / (r.ui[3] - r.ui[1])));
      const cols = tiles.map((p) => 32 - p.w / T), rows = tiles.map((p) => 32 - p.n / T);
      const box = [Math.max(0, Math.floor(Math.min(...cols))), Math.min(63, Math.floor(Math.max(...cols))),
                   Math.max(0, Math.floor(Math.min(...rows))), Math.min(63, Math.floor(Math.max(...rows)))];
      if (box[0] > box[1] || box[2] > box[3]) continue;
      const [a0, b0] = on(0, 0), [a1, b1] = on(1, 1);
      clouds.paint(g, r.instance, box, on, [a1 - a0, b1 - b0], BELOW.res * dpr);
    }
  };
  below.paint({ W, H, rot: v.rot, frame, px, sea: mapTiles.sea(), world, perFrac, over, light: belowLight(),
    shadow: shape && shift ? { ...shape, shift } : null, clouds: between, key: [shape ? 1 : 0, [...clouds.pics.values()].filter((p) => p.ok).length] });
}
let belowRim = null;
function makeBelowRim(size, scale) {
  belowRim = belowShown() ? below.rim(glowLayer.ground, W, H, belowLight().haze, yardPx(app.displayMap, size, scale)) : null;
}
function drawBelowRim(size, scale) {
  if (!belowRim) return;
  const px = yardPx(app.displayMap, size, scale), light = belowLight();
  const list = BELOW.clouds.rim.map((c) => {
    const img = cloudPiece(c.band, c.yards * px * dpr), [x, y] = toScreen(c.at[0], c.at[1], size, scale, app.displayMap);
    return img && { img, x, y, size: c.yards * px, alpha: c.alpha };
  }).filter(Boolean);
  ctx.save();
  ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
  below.lay(ctx, W, H, belowRim, list, light.share, app.view.zoom);
  ctx.restore();
}
function worldFrames(size, scale) {
  const shown = app.maps[app.displayMap], T = app.tiles?.tileYards, out = [];
  if (!worldRound() || !T) return out;
  for (const r of app.maps[WORLD_MAP]?.regions || []) {
    const map = continentMap(r.instance), box = mapTiles.renderBox(r.instance);
    if (map == null || r.instance === shown.instance || !box) continue;
    const on = (c, row) => worldToFrac(app.displayMap, { inst: r.instance, n: (32 - row) * T, w: (32 - c) * T }, app.maps, true);
    const a = on(box[0], box[1]), b = on(box[2] + 1, box[3] + 1), at = mapOn(map, app.displayMap, app.maps, true);
    if (!a || !b || !at || !(boxShown([...a, ...b], size, scale) > 0)) continue;
    const cs = imgSize(mapImage(map)), kx = (at[2] - at[0]) * size.w / cs.w, ky = (at[3] - at[1]) * size.h / cs.h;
    const toMapIn = (x, y) => { const p = toMap(x, y, size, scale); return { x: (p.x - at[0]) / (at[2] - at[0]), y: (p.y - at[1]) / (at[3] - at[1]) }; };
    out.push({ map, info: app.maps[map], size: cs, scale: scale * kx, at, kx, ky, toMap: toMapIn, ground: [...a, ...b] });
  }
  return out;
}
function inFrame(f, size, paint) {
  ctx.save();
  ctx.translate(f.at[0] * size.w, f.at[1] * size.h);
  ctx.scale(f.kx, f.ky);
  try { paint(); } finally { ctx.restore(); }
}
function regionsBox() {
  const rs = app.maps[WORLD_MAP]?.regions || [];
  if (!rs.length) return [0, 0, 1, 1];
  return [0, 1, 2, 3].map((i) => (i < 2 ? Math.min : Math.max)(...rs.map((r) => r.ui[i])));
}
function openContinentAt(mx, my) {
  const size = app.curSize;
  if (!size || !worldRender()) return false;
  const at = toMap(mx, my, size, scaleFor(size));
  const r = (app.maps[WORLD_MAP]?.regions || []).find((q) => at.x >= q.ui[0] && at.x <= q.ui[2] && at.y >= q.ui[1] && at.y <= q.ui[3]);
  const cont = r && continentMap(r.instance);
  if (cont == null) return false;
  setFollow(false);
  enterContinent("zoom", cont);
  [app.view.cx, app.view.cy] = [0.5, 0.5];
  viewMoved();
  return true;
}
function screenTiles(info, size, scale, onMap = (x, y) => toMap(x, y, size, scale)) {
  const T = app.tiles.tileYards, w = info.world;
  const corners = [[0, 0], [W, 0], [0, H], [W, H]].map(([x, y]) => onMap(x, y)).map((p) => toWorld(w, p.x, p.y));
  const wys = corners.map((p) => p.w), wxs = corners.map((p) => p.n);
  return [Math.floor(32 - Math.max(...wys) / T), Math.floor(32 - Math.min(...wys) / T),
          Math.floor(32 - Math.max(...wxs) / T), Math.floor(32 - Math.min(...wxs) / T)];
}
function cloudsOn(info) {
  return !!info?.world && !info.high && !app.dungeon && !!app.tiles && clouds.has(info.instance);
}
function detailClouds(size, scale, alpha, frames = []) {
  const info = app.maps[app.displayMap];
  if (worldRender() || !(alpha > 0) || !cloudsOn(info)) return null;
  const views = [[info, detailCloudView(info, size, scale)], ...frames.filter((f) => cloudsOn(f.info)).map((f) => [f.info, detailCloudView(f.info, size, scale, f)])];
  let when = { t: null, next: null };
  for (const [of, view] of views) if ((when = cloudsNow(of, view, scale)).t != null) break;
  groundTicks.clouds = when.next;
  const jobs = views.map(([, view]) => ({ ...view, t: when.t }));
  return { jobs, pic: clouds.keptPicture(ctx, jobs, scale * dpr) };
}
const CLOUD_NIGHT = 0.7;
const cloudShare = (hour, night) => 1 - CLOUD_NIGHT * nightAt(hour, night);
function drawClouds(size, scale, alpha, sky) {
  if (!sky) return 0;
  ctx.save();
  cutCitySheets(size);
  ctx.globalAlpha = alpha;
  const k = cloudShare(mapLight.hour(), app.nightOn !== false);
  if (k < 1) ctx.filter = `brightness(${k.toFixed(3)})`;
  const drawn = sky.pic ? clouds.lay(ctx, sky.pic)
    : sky.jobs.reduce((n, { instance, box, at, tile, t }) => n + clouds.paint(ctx, instance, box, at, tile, scale * dpr, t), 0);
  ctx.restore();
  return drawn;
}
function cloudsMove(info) {
  return cloudsOn(info) && !lessMotion();
}
function cloudsNow(info, view, scale) {
  if (!cloudsMove(info)) return { t: null, next: null };
  const tilePx = Math.max(Math.abs(view.tile[0]), Math.abs(view.tile[1])) * scale * dpr;
  return heldTime(clouds.time(view.instance, shadowReach(view.box, cloudShadeNow()), tilePx));
}
const cloudHold = { frame: null, moving: false, t: null, at: 0 };
function heldTime(when) {
  const now = clouds.now();
  if (when.t == null) return when;
  if (cloudHold.t != null && cloudHold.moving && (drag?.moved || now - cloudHold.at < MOTION.most)) return { t: cloudHold.t, next: when.next };
  Object.assign(cloudHold, { t: when.t, at: now });
  return when;
}
function noteViewMoved() {
  const v = app.view, frame = JSON.stringify([app.displayMap, v.cx, v.cy, v.zoom, v.rot, W, H, dpr]);
  cloudHold.moving = frame !== cloudHold.frame;
  cloudHold.frame = frame;
  const scale = JSON.stringify([app.displayMap, app.curSize ? scaleFor(app.curSize) : null, v.rot, W, H, dpr]);
  if (scale !== viewScale.key) {
    if (viewSettling() <= 0) viewScale.move++;
    Object.assign(viewScale, { key: scale, at: performance.now() });
  }
}
const VIEW_SETTLE_MS = 200;
const viewScale = { key: null, at: -Infinity, move: 0 };
const viewSettling = () => viewScale.at + VIEW_SETTLE_MS - performance.now();
function viewSettled() {
  const left = viewSettling();
  if (left > 0) redrawIn(left);
  return left <= 0;
}
document.addEventListener("visibilitychange", () => (document.hidden ? askGroundTick() : redraw()));
matchMedia("(prefers-reduced-motion: reduce)").addEventListener?.("change", () => redraw());
function cutCitySheets(size) {
  ctx.beginPath();
  ctx.rect(-20 * size.w, -20 * size.h, 41 * size.w, 41 * size.h);
  citySheets(app.displayMap, size).filter((c) => c.fade > 0).forEach((c) => ctx.rect(...c.at));
  ctx.clip("evenodd");
}
function detailCloudView(info, size, scale, frame = null) {
  const T = app.tiles.tileYards, w = info.world, [ax, ay, bx, by] = frame ? frame.at : [0, 0, 1, 1];
  const at = (col, row) => { const [fx, fy] = toFrac(w, (32 - row) * T, (32 - col) * T); return [(ax + fx * (bx - ax)) * size.w, (ay + fy * (by - ay)) * size.h]; };
  const [x0, y0] = at(0, 0), [x1, y1] = at(1, 1);
  return { instance: info.instance, box: frame ? screenTiles(info, frame.size, frame.scale, frame.toMap) : screenTiles(info, size, scale), at, tile: [x1 - x0, y1 - y0] };
}
function drawWorldClouds(size, scale) {
  const views = worldCloudViews(size, scale), kept = clouds.paintKept(ctx, views, scale * dpr);
  if (kept != null) return kept;
  let drawn = 0;
  for (const { instance, box, at, tile } of views) drawn += clouds.paint(ctx, instance, box, at, tile, scale * dpr);
  return drawn;
}
function worldCloudViews(size, scale) {
  if (!worldRender() || !app.tiles) return [];
  const T = app.tiles.tileYards, view = [[0, 0], [W, 0], [0, H], [W, H]].map(([x, y]) => toMap(x, y, size, scale));
  const out = [];
  for (const r of app.maps[WORLD_MAP]?.regions || []) {
    if (!clouds.has(r.instance)) continue;
    const [x0, y0, x1, y1] = r.ui;
    const at = (col, row) => { const [fx, fy] = placeIn(r.world, (32 - row) * T, (32 - col) * T, ...r.ui); return [fx * size.w, fy * size.h]; };
    const tiles = view.map((p) => toWorld(r.world, (p.x - x0) / (x1 - x0), (p.y - y0) / (y1 - y0)));
    const cols = tiles.map((p) => 32 - p.w / T), rows = tiles.map((p) => 32 - p.n / T);
    const box = [Math.max(0, Math.floor(Math.min(...cols))), Math.min(63, Math.floor(Math.max(...cols))),
                 Math.max(0, Math.floor(Math.min(...rows))), Math.min(63, Math.floor(Math.max(...rows)))];
    if (box[0] > box[1] || box[2] > box[3]) continue;
    const [a0, b0] = at(0, 0), [a1, b1] = at(1, 1);
    out.push({ instance: r.instance, box, at, tile: [a1 - a0, b1 - b0] });
  }
  return out;
}
const cloudLayer = newCanvas(1, 1);
const cloudMask = { canvas: newCanvas(1, 1), share: 0, on: false, made: 0, drawn: 0 };
function drawCloudShadows(size, scale, alpha, sky, again = false) {
  const wasOn = cloudMask.on;
  cloudMask.on = false;
  const world = worldRender();
  const jobs = world ? worldCloudViews(size, scale) : sky ? sky.jobs : [];
  if (!jobs.length) return 0;
  const under = world ? { inside: 0, below: [] } : undergroundShown(app.displayMap, size);
  const strength = world ? 1 : alpha * (1 - under.inside);
  if (!(strength > 0)) return 0;
  const shade = cloudShadeNow(), lit = !world && cloudsLit, own = lit ? relief.take : canvas;
  if (cloudLayer.width !== own.width || cloudLayer.height !== own.height) Object.assign(cloudLayer, { width: own.width, height: own.height });
  const m = cloudMask.canvas, kept = again && wasOn && m.width === cloudLayer.width && m.height === cloudLayer.height ? { canvas: m, drawn: cloudMask.drawn } : null;
  ctx.save();
  cutCitySheets(size);
  if (under.below.length) {
    ctx.beginPath();
    ctx.rect(-20 * size.w, -20 * size.h, 41 * size.w, 41 * size.h);
    under.below.forEach((c) => ctx.rect(...c.at));
    ctx.clip("evenodd");
  }
  const take = lit ? { light: relief.withBeside("take", litBeside, W) } : { rgb: shade.moon ? moonShade() : [0, 0, 0] };
  const drawn = clouds.shadowPass(ctx, cloudLayer, jobs, scale * dpr, shade, take, strength,
    world ? { kept: true } : { picture: sky.pic, keep: lit ? cloudMask.canvas : null, mask: lit ? kept : null });
  ctx.restore();
  if (drawn && lit) Object.assign(cloudMask, { share: relief.took * strength, on: true, made: cloudMask.made + (kept ? 0 : 1), drawn });
  return drawn;
}
let cloudsLit = false;
function cloudsTakeShare(info) {
  if (worldRender() || !cloudsOn(info)) return 0;
  const [by, dark] = lightNow(), shade = cloudShade(by, dark, app.tiles.tileYards);
  return shade.strength > 0 && dark > 0 ? (shade.moon ? CLOUD_SHADOW.moon : 1) : 0;
}
function shadeAtYou() {
  const p = app.disp && fracToWorld(app.state?.map, app.disp.x, app.disp.y), info = app.maps[app.displayMap];
  const light = litBeside.find((b) => b.inst === p?.inst)?.light || relief, ground = light.shadeAt;
  if (ground == null || !cloudsLit || !p) return ground;
  const T = app.tiles.tileYards, mine = app.maps[continentMap(p.inst)] || info;
  if (light === relief && p.inst !== info.instance) return ground;
  const t = cloudsMove(mine) ? cloudHold.t : null;
  return Math.max(ground, light.took * clouds.shadowAt(p.inst, 32 - p.w / T, 32 - p.n / T, t, cloudShadeNow()));
}
function cloudShadeNow() {
  return cloudShade(...lightNow(), app.tiles.tileYards);
}
function lightNow() {
  if (!app.reliefOn) return [null, 0];
  const night = app.nightOn !== false, hour = mapLight.hour();
  return [casterAt(hour, night), ONE_LIGHT.darkest * reliefLight(hour, night, storm.sun()).shadow];
}
function cloudsOverYou() {
  const info = app.maps[app.displayMap], world = worldRender();
  if (!app.disp || (!world && !cloudsOn(info)) || !app.tiles) return false;
  const p = fracToWorld(app.state?.map, app.disp.x, app.disp.y), T = app.tiles.tileYards;
  const inst = world ? p?.inst : info.instance;
  const t = world ? null : cloudsNow(info, detailCloudView(info, app.curSize, scaleFor(app.curSize)), scaleFor(app.curSize)).t;
  return !!p && p.inst === inst && clouds.has(inst) && clouds.over(inst, 32 - p.w / T, 32 - p.n / T, t);
}
function drawTiles(mapId, size, scale, frame = null) {
  const info = app.maps[mapId];
  if (info.high && !info.tilesOnly) return drawDungeonHigh(info, size);
  if (!mapTiles.has(info.instance)) return;
  if (!clouds.ready) return;
  const T = app.tiles.tileYards, w = info.world;
  const floating = floats(info.instance);
  const [c0, c1, r0, r1] = frame ? screenTiles(info, size, scale, frame.toMap) : screenTiles(info, size, scale);
  const tilePx = (app.tiles.tileYards * size.w / Math.abs(info.world.left - info.world.right)) * scale * dpr;
  const farPx = app.detailView.overviews?.render?.[info.instance]?.length ? app.detailView.tilePx || 0 : 0;
  const level = mapTiles.level(tilePx, (c1 - c0 + 1) * (r1 - r0 + 1), farPx);
  if (level === "far") return drawFarTiles(info, size, [c0, c1, r0, r1], scale, floating);
  const seam = 0.75 / scale;
  const skirts = [], sea = seaFill();
  for (let r = Math.max(0, r0 - 1); r <= Math.min(63, r1 + 1); r++) {
    for (let c = Math.max(0, c0 - 1); c <= Math.min(63, c1 + 1); c++) {
      const key = `${c}_${r}`;
      if (!clouds.tileReady(info.instance, key)) continue;
      const has = mapTiles.exists(info.instance, key), entry = mapTiles.image(info.instance, key, level), open = !frame && !has && !floating;
      const stand = entry || !has ? null : farPiece(info, c, r);
      if (!entry && !open && !stand) continue;
      const [fx0, fy0] = toFrac(w, (32 - r) * T, (32 - c) * T), [fx1, fy1] = toFrac(w, (31 - r) * T, (31 - c) * T);
      const x0 = fx0 * size.w, y0 = fy0 * size.h, tw = fx1 * size.w - x0, th = fy1 * size.h - y0;
      if (open) { ctx.fillStyle = sea; ctx.fillRect(x0, y0, tw + seam, th + seam); }
      const parts = floating ? voidParts(info.instance, c, r, 1) : null;
      if (entry) drawGround(entry.img, parts, x0, y0, tw + seam, th + seam);
      else if (stand) drawGround(stand.img, floating ? voidParts(info.instance, c - (c % stand.n), r - (r % stand.n), stand.n) : null, ...stand.src, x0, y0, tw + seam, th + seam);
      if (entry && !floating) for (const s of mapTiles.skirts(info.instance, key, entry, newCanvas)) skirts.push([s.canvas, x0 + s.at[0] * tw, y0 + s.at[1] * th, s.at[2] * tw, s.at[3] * th]);
    }
  }
  for (const s of skirts) ctx.drawImage(...s);
  if (info.high) drawDungeonHigh(info, size);
}

app.detailView = { version: null, chunk: 8, overviews: {}, names: {} };
const detailPics = new Map();
const detailSrc = (path) => pictureSrc(`/detailview/${path}`, app.detailView.version);
function detailPic(path, ahead = false) {
  const src = detailSrc(path);
  let entry = detailPics.get(src);
  if (!entry) {
    const img = new Image();
    entry = { img, ok: false, looked: false };
    img.onload = () => { entry.ok = true; if (entry.looked) redraw(); };
    img.src = src;
    detailPics.set(src, entry);
  }
  if (!ahead) entry.looked = true;
  return entry;
}
function preloadFarTiles() {
  if (app.mapKinds !== "detailed") return;
  for (const [inst, keys] of Object.entries(app.detailView.overviews?.render || {})) {
    for (const key of keys) detailPic(`render/${inst}/${key}.webp`, true);
  }
}
function farPiece(info, c, r) {
  const n = app.detailView.chunk || 8;
  const entry = detailPics.get(detailSrc(`render/${info.instance}/${Math.floor(c / n)}_${Math.floor(r / n)}.webp`));
  if (entry) entry.looked = true;
  if (!entry?.ok) return null;
  const iw = entry.img.naturalWidth / n, ih = entry.img.naturalHeight / n;
  return { img: entry.img, n, src: [(c % n) * iw, (r % n) * ih, iw, ih] };
}
function drawGround(img, parts, ...at) {
  ctx.drawImage(img, ...at);
  if (!parts) return;
  const mask = below.voidMask(img, parts), k = mask.width / (img.naturalWidth || img.width || mask.width), was = ctx.globalCompositeOperation;
  const [sx, sy, sw, sh] = at.length === 8 ? at.slice(0, 4).map((v) => v * k) : [0, 0, mask.width, mask.height];
  const [dx, dy, dw, dh] = at.slice(-4);
  const t = ctx.getTransform(), e = 1 / (Math.hypot(t.a, t.b) || 1);
  ctx.globalCompositeOperation = "destination-out";
  ctx.drawImage(mask, sx, sy, sw, sh, dx - e, dy - e, dw + 2 * e, dh + 2 * e);
  ctx.globalCompositeOperation = was;
}
const shapePics = new Map();
function voidParts(inst, c, r, n) {
  const out = [];
  for (let dr = 0; dr < n; dr++) {
    for (let dc = 0; dc < n; dc++) {
      const key = `${c + dc}_${r + dr}`;
      if (!mapTiles.hasRender(inst, key)) continue;
      const id = `${inst}/${key}`;
      let pic = shapePics.get(id);
      if (!pic) {
        pic = { img: new Image(), ok: false };
        pic.img.onload = () => { pic.ok = true; redraw(); };
        pic.img.src = renderShape(id);
        shapePics.set(id, pic);
      }
      out.push({ img: pic.ok ? pic.img : null, at: [dc / n, dr / n, 1 / n, 1 / n] });
    }
  }
  return out;
}
function drawFarTiles(info, size, [c0, c1, r0, r1], scale, floating = false) {
  const all = app.detailView.overviews || {}, n = app.detailView.chunk || 8, T = app.tiles.tileYards, w = info.world;
  const list = "render", seam = 0.75 / scale;
  for (const key of all[list]?.[info.instance] || []) {
    const [cx, cy] = key.split("_").map(Number);
    if (cx < Math.floor(c0 / n) || cx > Math.floor(c1 / n) || cy < Math.floor(r0 / n) || cy > Math.floor(r1 / n)) continue;
    if (!clouds.areaReady(info.instance, [cx * n, cx * n + n - 1, cy * n, cy * n + n - 1])) continue;
    const entry = detailPic(`${list}/${info.instance}/${key}.webp`);
    if (!entry.ok) continue;
    const [fx0, fy0] = toFrac(w, (32 - cy * n) * T, (32 - cx * n) * T), [fx1, fy1] = toFrac(w, (32 - cy * n - n) * T, (32 - cx * n - n) * T);
    drawGround(entry.img, floating ? voidParts(info.instance, cx * n, cy * n, n) : null,
      fx0 * size.w, fy0 * size.h, (fx1 - fx0) * size.w + seam, (fy1 - fy0) * size.h + seam);
  }
}
const NAME_FROM = 0.5, NAME_FULL = 0.8;
const CONTINENT_GLOW_PX = 14;
const NAME_GLOW_GONE = 0.4, NAME_INK_FULL = 0.5;
let metamorphous = null;
function metamorphousReady() {
  if (metamorphous) return true;
  if (!metamorphousReady.asked && document.fonts?.load) {
    metamorphousReady.asked = true;
    Promise.resolve(document.fonts.load("100px Metamorphous")).then(() => {
      const c = document.createElement("canvas").getContext("2d");
      c.font = "100px Metamorphous";
      const tall = (ch) => c.measureText(ch).actualBoundingBoxAscent / 100;
      metamorphous = { cap: tall("E") || 0.75 };
      redraw();
    }, () => {});
  }
  return false;
}
function landShown(cont, size, scale, onMap = undefined) {
  let x0 = Infinity, y0 = Infinity, x1 = -Infinity, y1 = -Infinity;
  for (const z of continentZones(cont, size)) {
    x0 = Math.min(x0, z.x0); y0 = Math.min(y0, z.y0); x1 = Math.max(x1, z.x0 + z.w); y1 = Math.max(y1, z.y0 + z.boxH);
  }
  return boxShown([x0, y0, x1, y1], size, scale, onMap);
}
function boxShown([x0, y0, x1, y1], size, scale, onMap = (x, y) => toMap(x, y, size, scale)) {
  if (!(x1 > x0 && y1 > y0)) return 1;
  const corners = [[0, 0], [W, 0], [0, H], [W, H]].map(([x, y]) => onMap(x, y));
  const vx0 = Math.min(...corners.map((p) => p.x)), vx1 = Math.max(...corners.map((p) => p.x));
  const vy0 = Math.min(...corners.map((p) => p.y)), vy1 = Math.max(...corners.map((p) => p.y));
  const iw = Math.max(0, Math.min(x1, vx1) - Math.max(x0, vx0)), ih = Math.max(0, Math.min(y1, vy1) - Math.max(y0, vy0));
  return (iw * ih) / ((x1 - x0) * (y1 - y0));
}
const nameBy = (share) => Math.min(1, Math.max(0, (share - NAME_FROM) / (NAME_FULL - NAME_FROM)));
function continentNames(size, scale, terrain, frames = []) {
  if (app.continentNamesOn === false) return [];
  const id = app.displayMap, names = app.detailView.names || {};
  if (worldRender()) {
    const out = [];
    for (const r of app.maps[WORLD_MAP]?.regions || []) {
      const cont = continentMap(r.instance), at = cont != null && names[cont] ? mapOn(cont, WORLD_MAP) : null;
      const alpha = at ? nameBy(boxShown(r.ui, size, scale)) : 0;
      if (alpha > 0) out.push({ name: names[cont], alpha, at, cont });
    }
    return out;
  }
  if (!(terrain > 0) || app.maps[id]?.type !== 2) return [];
  const own = names[id] ? [{ name: names[id], alpha: terrain * nameBy(landShown(id, size, scale)), at: null }] : [];
  const round = frames.filter((f) => names[f.map]).map((f) => ({ name: names[f.map], alpha: terrain * nameBy(landShown(f.map, f.size, f.scale, f.toMap)), at: f.at, cont: f.map }));
  return [...own, ...round].filter((n) => n.alpha > 0);
}
function nameShown(size, scale, terrain, frames = []) {
  return Math.max(0, ...continentNames(size, scale, terrain, frames).map((n) => n.alpha));
}
function nameLetters(line, size) {
  const cap = line.cap * size.h / metamorphous.cap, small = line.small * size.h / metamorphous.cap;
  const letters = [...line.text].map((ch, k) => ({ ch: ch.toUpperCase(),
    px: (k === 0 || line.text[k - 1] === " ") && ch === ch.toUpperCase() ? cap : small }));
  for (const l of letters) {
    ctx.font = `${l.px}px Metamorphous`;
    l.m = ctx.measureText(l.ch);
  }
  const lead = letters[0].m.actualBoundingBoxLeft || 0, last = letters[letters.length - 1].m;
  let ink = lead + (last.actualBoundingBoxRight ?? last.width);
  for (let k = 0; k < letters.length - 1; k++) ink += letters[k].m.width;
  const gap = letters.length > 1 ? ((line.x1 - line.x0) * size.w - ink) / (letters.length - 1) : 0;
  let x = line.x0 * size.w + lead;
  for (const l of letters) {
    l.x = x;
    x += l.m.width + gap;
  }
  return letters;
}
function drawContinentName(size, scale, terrain, frames = []) {
  const shown = continentNames(size, scale, terrain, frames);
  if (!shown.length || !metamorphousReady()) return;
  for (const { name, alpha, at, cont } of shown) {
    if (!at) { letterName(name, alpha, size, scale); continue; }
    const cs = imgSize(mapImage(cont)), kx = (at[2] - at[0]) * size.w / cs.w, ky = (at[3] - at[1]) * size.h / cs.h;
    ctx.save();
    ctx.translate(at[0] * size.w, at[1] * size.h);
    ctx.scale(kx, ky);
    letterName(name, alpha, cs, scale * kx);
    ctx.restore();
  }
}
function letterName(name, alpha, size, scale, glowPx = CONTINENT_GLOW_PX, bold = null) {
  ctx.save();
  ctx.textBaseline = "alphabetic";
  ctx.textAlign = "left";
  for (const line of name.lines) inkLetters(nameLetters(line, size), line.base * size.h, name, alpha, 1 / scale, glowPx, bold);
  ctx.restore();
}
function inkLetters(letters, y, name, alpha, off, glowPx, bold = null) {
  const glow = Math.max(0, (alpha - NAME_GLOW_GONE) / (1 - NAME_GLOW_GONE)), lettersAlpha = Math.min(1, alpha / NAME_INK_FULL);
  const moving = bold ? nameSprite(letters, y, name, off, glowPx, bold) : null;
  if (moving) return layNameSprite(moving, glow, lettersAlpha, bold);
  ctx.save();
  ctx.globalAlpha = glow;
  if (bold?.blend) ctx.globalCompositeOperation = bold.blend;
  const sprite = bold && glow > 0 ? glowSprite(letters, y, glowPx, bold) : null;
  if (sprite) {
    ctx.setTransform(1, 0, 0, 1, 0, 0);
    for (let pass = 0; pass < bold.glows; pass++) ctx.drawImage(sprite.canvas, sprite.x, sprite.y);
  } else {
    ctx.shadowColor = tint("continent-glow", bold?.glowShadow ?? 0.9);
    ctx.shadowBlur = glowPx;
    ctx.fillStyle = tint("continent-glow", bold?.glowFill ?? 0.55);
    for (let pass = 0; pass < (bold?.glows || 2); pass++) {
      for (const l of letters) {
        ctx.font = `${l.px}px Metamorphous`;
        ctx.fillText(l.ch, l.x, y);
      }
    }
  }
  ctx.restore();
  ctx.save();
  ctx.globalAlpha = lettersAlpha;
  strokeLetters(ctx, letters, y, name, off, bold);
  ctx.restore();
}
function strokeLetters(g, letters, y, name, off, bold) {
  const ink = `rgb(${name.ink.join(",")})`, bevel = `rgb(${name.bevel.join(",")})`;
  g.lineJoin = "round";
  for (const l of letters) {
    g.font = `${l.px}px Metamorphous`;
    if (bold) {
      g.lineWidth = bold.outlinePx * off;
      g.strokeStyle = bold.outline;
      g.strokeText(l.ch, l.x, y);
    }
    g.fillStyle = bevel;
    g.fillText(l.ch, l.x + off, y + off);
    if (bold) {
      g.lineWidth = bold.edgePx * off;
      g.strokeStyle = ink;
      g.strokeText(l.ch, l.x, y);
    }
    g.fillStyle = ink;
    g.fillText(l.ch, l.x, y);
  }
}
const NAME_SPRITES = { most: 400 };
const nameSprites = new Map();
function nameSprite(letters, y, name, off, glowPx, bold) {
  if (viewSettled()) return null;
  const key = JSON.stringify([letters.map((l) => [l.ch, l.px, l.x]), y, glowPx, name.ink, name.bevel]);
  let s = nameSprites.get(key);
  nameSprites.delete(key);
  if (s?.move !== viewScale.move) {
    const m = ctx.getTransform(), glow = glowSprite(letters, y, glowPx, bold);
    const canvas = newCanvas(glow.canvas.width, glow.canvas.height), g = canvas.getContext("2d");
    g.setTransform(m.a, m.b, m.c, m.d, m.e - glow.x, m.f - glow.y);
    g.textBaseline = "alphabetic";
    g.textAlign = "left";
    strokeLetters(g, letters, y, name, off, bold);
    s = { glow: glow.canvas, letters: canvas, lin: [m.a, m.b, m.c, m.d], bx: glow.x - m.e, by: glow.y - m.f, move: viewScale.move };
  }
  nameSprites.set(key, s);
  if (nameSprites.size > NAME_SPRITES.most) nameSprites.delete(nameSprites.keys().next().value);
  return s;
}
function layNameSprite(s, glow, lettersAlpha, bold) {
  const m = ctx.getTransform(), [a, b, c, d] = s.lin, det = a * d - b * c;
  const ia = d / det, ib = -b / det, ic = -c / det, id = a / det;
  const t = [m.a * ia + m.c * ib, m.b * ia + m.d * ib, m.a * ic + m.c * id, m.b * ic + m.d * id];
  ctx.save();
  ctx.setTransform(...t, t[0] * s.bx + t[2] * s.by + m.e, t[1] * s.bx + t[3] * s.by + m.f);
  if (glow > 0) {
    ctx.globalAlpha = glow;
    if (bold.blend) ctx.globalCompositeOperation = bold.blend;
    for (let pass = 0; pass < bold.glows; pass++) ctx.drawImage(s.glow, 0, 0);
    ctx.globalCompositeOperation = "source-over";
  }
  ctx.globalAlpha = lettersAlpha;
  ctx.drawImage(s.letters, 0, 0);
  ctx.restore();
}
const GLOW_SPRITES = { most: 400, pad: 1.5, spare: 2 };
const glowSprites = new Map();
function glowSprite(letters, y, glowPx, bold) {
  const m = ctx.getTransform(), lin = [m.a, m.b, m.c, m.d];
  const key = JSON.stringify([letters.map((l) => [l.ch, l.px, l.x]), y, glowPx, bold.glowShadow, bold.glowFill, lin]);
  let s = glowSprites.get(key);
  if (s) {
    glowSprites.delete(key);
    glowSprites.set(key, s);
  } else {
    let x0 = Infinity, y0 = Infinity, x1 = -Infinity, y1 = -Infinity;
    for (const l of letters) {
      const left = l.x - (l.m?.actualBoundingBoxLeft ?? 0), right = l.x + (l.m?.actualBoundingBoxRight ?? l.px);
      const top = y - (l.m?.actualBoundingBoxAscent ?? l.px), bottom = y + (l.m?.actualBoundingBoxDescent ?? l.px / 4);
      for (const [px, py] of [[left, top], [right, top], [left, bottom], [right, bottom]]) {
        const dx = m.a * px + m.c * py, dy = m.b * px + m.d * py;
        x0 = Math.min(x0, dx); x1 = Math.max(x1, dx); y0 = Math.min(y0, dy); y1 = Math.max(y1, dy);
      }
    }
    const pad = Math.ceil(GLOW_SPRITES.pad * glowPx) + GLOW_SPRITES.spare, bx = Math.floor(x0) - pad, by = Math.floor(y0) - pad;
    const canvas = newCanvas(Math.max(1, Math.ceil(x1) + pad - bx), Math.max(1, Math.ceil(y1) + pad - by)), g = canvas.getContext("2d");
    g.setTransform(m.a, m.b, m.c, m.d, -bx, -by);
    g.textBaseline = "alphabetic";
    g.textAlign = "left";
    g.shadowColor = tint("continent-glow", bold.glowShadow ?? 0.9);
    g.shadowBlur = glowPx;
    g.fillStyle = tint("continent-glow", bold.glowFill ?? 0.55);
    for (const l of letters) {
      g.font = `${l.px}px Metamorphous`;
      g.fillText(l.ch, l.x, y);
    }
    s = { canvas, bx, by };
    glowSprites.set(key, s);
    if (glowSprites.size > GLOW_SPRITES.most) glowSprites.delete(glowSprites.keys().next().value);
  }
  return { canvas: s.canvas, x: m.e + s.bx, y: m.f + s.by };
}

const PLACE_GLOW_PX = 22;
const PLACE_BOLD = { glows: 6, blend: "hard-light", glowShadow: 1, glowFill: 0.85, outlinePx: 3,
  outline: tint("place-outline", 0.85), edgePx: 1.4 };
const PLACE_INK = 0.6;
const PLACE_SIZE = 1.12;
const PLACE_TRACK = 0.14;
const PLACE_GROW = 1.3;
const PLACE_MOST_LIKE = ["BLOODHOOF VILLAGE", "GOLDSHIRE"];
function placeYards(zone, place) {
  const w = app.maps[zone]?.world;
  return w ? Math.max(...place.lines.map((l) => l.cap)) * Math.abs(w.top - w.bottom) : 0;
}
let placeMostFor = null, placeMostYards = 0;
function placeMost() {
  if (placeMostFor === app.detailView) return placeMostYards;
  const got = [];
  for (const [id, lettering] of Object.entries(app.detailView?.places || {}))
    for (const place of lettering.names || [])
      if (PLACE_MOST_LIKE.includes(place.lines.map((l) => l.text).join(" ").toUpperCase())) got.push(placeYards(+id, place));
  placeMostFor = app.detailView;
  placeMostYards = got.length ? got.reduce((s, v) => s + v, 0) / got.length : 0;
  return placeMostYards;
}
function placeFit(zone, place) {
  const most = placeMost(), yards = placeYards(zone, place);
  return most > 0 && yards > most ? most / yards : 1;
}
function paperZoneShown(size, scale) {
  const info = app.maps[app.displayMap];
  if (!detailedOnly() || info?.type !== 3 || !info.world) return 0;
  const by = (t) => Math.min(1, Math.max(0, t));
  const px = yardPx(app.displayMap, size, scale), zoom = app.view.zoom;
  return Math.max(by((HIGH_AT_PX_PER_YARD - px) / (HIGH_AT_PX_PER_YARD - LOW_AT_PX_PER_YARD)),
                  by((TILES_FROM_ZOOM - zoom) / (TILES_FROM_ZOOM - DRAWN_BELOW_ZOOM)));
}
function placesShown() {
  const info = app.maps[app.displayMap];
  return app.placeNamesOn !== false && detailedOnly() && info?.type === 3 && !!info.world ? 1 : 0;
}
function placeShrink(size, scale) {
  const w = app.maps[app.displayMap]?.world;
  if (!w || !(scale > 0)) return 1;
  const atHigh = HIGH_AT_PX_PER_YARD * Math.abs(w.left - w.right) / size.w, atTiles = scale / app.view.zoom * TILES_FROM_ZOOM;
  return PLACE_SIZE * Math.min(1, PLACE_GROW * Math.max(atHigh, atTiles) / scale);
}
function placesOverClouds(size, scale) {
  return placeShrink(size, scale) < PLACE_SIZE - 1e-9;
}
function placeBox(place) {
  const ls = place.lines;
  return [Math.min(...ls.map((l) => l.x0)), Math.min(...ls.map((l) => l.base - l.cap)), Math.max(...ls.map((l) => l.x1)), Math.max(...ls.map((l) => l.base))];
}
function inCapital(p) {
  return Object.keys(app.detailView.capitals || {}).some((id) => {
    const w = app.maps[id]?.world;
    return !!w && app.maps[id].instance === p.inst && p.n <= w.top && p.n >= w.bottom && p.w <= w.left && p.w >= w.right;
  });
}
function placeNames(size, scale) {
  const alpha = placesShown(), info = app.maps[app.displayMap], out = [];
  if (!(alpha > 0)) return out;
  const k = placeShrink(size, scale);
  const cityZoom = !(paperZoneShown(size, scale) > 0);
  for (const [id, lettering] of Object.entries(app.detailView.places || {})) {
    const capital = !!app.detailView.capitals?.[id];
    const at = app.maps[id]?.instance === info.instance && (!capital || cityZoom) && mapOn(+id, app.displayMap);
    if (!at) continue;
    for (const place of lettering.names || []) {
      const b = placeBox(place), spot = fracToWorld(+id, (b[0] + b[2]) / 2, (b[1] + b[3]) / 2);
      if (!spot || (!capital && inCapital(spot))) continue;
      const kx = at[2] - at[0], ky = at[3] - at[1], kp = capital ? 1 : k * placeFit(+id, place);
      const mx = at[0] + (b[0] + b[2]) / 2 * kx, my = at[1] + (b[1] + b[3]) / 2 * ky;
      const hw = (b[2] - b[0]) / 2 * kx * kp, hh = (b[3] - b[1]) / 2 * ky * kp;
      const box = [mx - hw, my - hh, mx + hw, my + hh];
      if (boxShown(box, size, scale) <= 0) continue;
      const ink = lettering.ink.map((v) => Math.round(v * PLACE_INK));
      const lines = place.lines.map((l) => {
        const c = (l.x0 + l.x1) / 2, half = (l.x1 - l.x0) / 2 * (1 + PLACE_TRACK);
        return { ...l, x0: c - half, x1: c + half };
      });
      out.push({ zone: +id, at, box, k: kp, alpha, mid: [mx, my], name: { lines, ink, bevel: lettering.bevel } });
    }
  }
  return onceEach(out, size);
}
function onceEach(places, size) {
  const cv = clearView(), cx = (cv.l + cv.r) / 2, cy = (cv.t + cv.b) / 2, kept = new Map();
  const far = (p) => Math.hypot(p.mid[0] * size.w - cx, p.mid[1] * size.h - cy);
  for (const p of places) {
    const text = p.name.lines.map((l) => l.text.toUpperCase()).join(" ");
    if (!kept.has(text) || far(p) < far(kept.get(text))) kept.set(text, p);
  }
  return places.filter((p) => kept.get(p.name.lines.map((l) => l.text.toUpperCase()).join(" ")) === p);
}
function drawPlaceNames(size, scale, shown = placeNames(size, scale)) {
  if (!shown.length || !metamorphousReady()) return;
  for (const { at, name, alpha, k, mid } of shown) {
    const kx = at[2] - at[0], ky = at[3] - at[1];
    ctx.save();
    ctx.translate(mid[0] * size.w, mid[1] * size.h);
    ctx.scale(k, k);
    ctx.translate(-mid[0] * size.w, -mid[1] * size.h);
    ctx.translate(at[0] * size.w, at[1] * size.h);
    ctx.scale(kx, ky);
    letterName(name, alpha, size, scale * kx * k, PLACE_GLOW_PX, PLACE_BOLD);
    ctx.restore();
  }
}

const SMALL_CAPS = 0.83;
const BANNER_MOST_PX = 110;
const BANNER_LEAST_PX = 34;
const BANNER_OVER_PLACE = 1.25;
const BANNER = "art/world/banner.png";
const BANNER_TEXT = { left: 0.29, right: 0.72, ends: 0.374, mid: 0.315, cap: 0.26 };
const BANNER_WIDE = 0.55;
const CREST_SHARE = 1.7;
const CREST_LIFT = 0.32;
const CREST_ASIDE = 0.18, CREST_TILT = 0.14;
const capitalArt = {};
function capitalPicture(key, srcs) {
  let entry = capitalArt[key];
  if (!entry) {
    const img = new Image();
    entry = capitalArt[key] = { img, ok: false, at: 0 };
    img.onload = () => { entry.ok = true; redraw(); };
    img.onerror = () => { if (++entry.at < srcs.length) img.src = srcs[entry.at]; };
    img.src = srcs[0];
  }
  return entry;
}
const bannerArt = () => capitalPicture("banner", [BANNER]);
const crestSrc = (faction) => detailSrc(`crests/${faction}.png`);
const crestArt = (faction) => capitalPicture(`crest:${faction}`, [`art/world/crest_${faction}.png`, crestSrc(faction)]);
function capitalNames(size, scale) {
  if (app.cityBannersOn === false || !(detailedOnly() || worldRender()) || !metamorphousReady()) return [];
  const zoneMap = app.maps[app.displayMap]?.type === 3, alpha = zoneMap ? paperZoneShown(size, scale) : 1;
  if (!(alpha > 0)) return [];
  const out = [], aspect = 1389 / 340, t = BANNER_TEXT, yards = bannerYards();
  for (const [id, c] of Object.entries(app.detailView.capitals || {})) {
    const on = c.box && mapOn(c.zone, app.displayMap, app.maps, worldRound());
    let x, y;
    if (on) {
      const kx = on[2] - on[0], ky = on[3] - on[1], b = c.box;
      [x, y] = toScreen(on[0] + kx * (b[0] + b[2]) / 2, on[1] + ky * (b[1] + b[3]) / 2, size, scale, app.displayMap);
    } else {
      const f = worldToFrac(app.displayMap, { inst: c.inst, n: c.n, w: c.w }, app.maps, worldRound());
      if (!f || !(f[0] >= -1 && f[0] <= 2)) continue;
      [x, y] = toScreen(f[0], f[1], size, scale, app.displayMap);
    }
    const least = Math.min(...bannerLetters(c.name, 0, 0, aspect * 100, 100).map((l) => l.px)) * metamorphous.cap / 100;
    const tall = Math.max(yards / BANNER_WIDE / aspect, least > 0 ? placeMost() * PLACE_SIZE * BANNER_OVER_PLACE / least : 0);
    const most = Math.max(BANNER_MOST_PX, tall * bannerFadeYardPx(c.zone));
    let h = Math.max(BANNER_LEAST_PX, Math.min(most, tall * capitalYardPx(c, +id, size, scale)));
    if (!(h > 0)) continue;
    const top = y - h * (t.ends + t.mid) / 2, left = x - h * aspect / 2, letters = bannerLetters(c.name, left, top, h * aspect, h);
    const w = h * aspect;
    if (x + w < 0 || x - w > W || y + h < 0 || y - h > H) continue;
    out.push({ id: +id, faction: c.faction, x, y: top + h / 2, w, h, alpha, letters });
  }
  return out;
}
let bannerYardsFor = null, bannerYardsAre = 0;
function bannerFadeYardPx(zone) {
  const w = app.maps[zone]?.world, img = imgSize(mapImage(zone));
  if (!w || !(W > 0 && H > 0)) return 0;
  return Math.max(LOW_AT_PX_PER_YARD, DRAWN_BELOW_ZOOM * Math.min(W / img.w, H / img.h) * img.w / Math.abs(w.left - w.right));
}
function bannerYards() {
  if (bannerYardsFor === app.detailView) return bannerYardsAre;
  const got = [];
  for (const c of Object.values(app.detailView?.capitals || {})) {
    const w = c.box && app.maps[c.zone]?.world;
    if (w) got.push((c.box[2] - c.box[0]) * Math.abs(w.left - w.right));
  }
  bannerYardsFor = app.detailView;
  bannerYardsAre = got.length ? (Math.min(...got) + Math.max(...got)) / 2 : 0;
  return bannerYardsAre;
}
function capitalYardPx(c, id, size, scale) {
  for (const m of [c.zone, id]) {
    const on = m && mapOn(m, app.displayMap, app.maps, worldRound()), w = app.maps[m]?.world;
    if (on && w) return (on[2] - on[0]) * size.w * scale / Math.abs(w.left - w.right);
  }
  return 0;
}
function bannerLetters(name, left, top, w, h) {
  const t = BANNER_TEXT, text = name.toUpperCase();
  const at = (fx, fy) => [left + fx * w, top + fy * h];
  const a = at(t.left, t.ends), b = at(t.right, t.ends), c = at((t.left + t.right) / 2, 2 * t.mid - t.ends);
  const pts = curve(a, c, b), cum = lengths(pts), room = cum[cum.length - 1];
  let cap = t.cap * h / metamorphous.cap;
  const sized = (k) => [...text].map((ch, i) => ({ ch, px: (i === 0 || text[i - 1] === " " ? 1 : SMALL_CAPS) * cap * k }));
  const widths = (ls) => ls.map((l) => { ctx.font = `${l.px}px Metamorphous`; return ctx.measureText(l.ch).width; });
  let letters = sized(1), ws = widths(letters), total = ws.reduce((s, v) => s + v, 0);
  if (total > room * 0.96) {
    const k = room * 0.96 / total;
    letters = sized(k);
    ws = widths(letters);
    total = ws.reduce((s, v) => s + v, 0);
  }
  let s = (room - total) / 2;
  letters.forEach((l, i) => {
    const p = pointAt(pts, cum, s + ws[i] / 2);
    Object.assign(l, { x: p.x, y: p.y, angle: p.angle, w: ws[i] });
    s += ws[i];
  });
  return letters;
}
function drawCapitalPiece(g, c, banner, dx, dy) {
  const crest = c.faction ? crestArt(c.faction) : null, side = c.h * CREST_SHARE;
  if (crest?.ok) {
    g.save();
    const way = c.faction === "horde" ? -1 : 1;
    g.translate(c.x + dx + way * c.w * CREST_ASIDE, c.y + dy - side * CREST_LIFT);
    g.rotate(way * CREST_TILT);
    g.drawImage(crest.img, -side / 2, -side / 2, side, side);
    g.restore();
  }
  if (banner.ok) g.drawImage(banner.img, c.x + dx - c.w / 2, c.y + dy - c.h / 2, c.w, c.h);
}
const BANNER_RISE_YARDS = 50, BANNER_SHADOW_MOST = 3;
function capitalShadowAt(c, light) {
  const size = app.curSize, cap = app.detailView.capitals?.[c.id];
  const rise = BANNER_RISE_YARDS * (size && cap ? capitalYardPx(cap, c.id, size, scaleFor(size)) : 0);
  const far = Math.min(BANNER_SHADOW_MOST * rise, rise / light.tan);
  return turned(-light.dir[0] * far, -light.dir[1] * far, app.view.rot);
}
const capitalLayer = newCanvas(1, 1);
function drawCapitalShadows(shown) {
  const light = groundLight(...lightNow()), banner = bannerArt();
  if (!(light.strength >= 0.005) || !(light.tan > 0)) return 0;
  if (capitalLayer.width !== canvas.width || capitalLayer.height !== canvas.height) Object.assign(capitalLayer, { width: canvas.width, height: canvas.height });
  const g = capitalLayer.getContext("2d");
  g.setTransform(1, 0, 0, 1, 0, 0);
  g.clearRect(0, 0, capitalLayer.width, capitalLayer.height);
  g.setTransform(dpr, 0, 0, dpr, 0, 0);
  for (const c of shown) {
    g.globalAlpha = c.alpha;
    drawCapitalPiece(g, c, banner, ...capitalShadowAt(c, light));
  }
  g.globalAlpha = 1;
  g.setTransform(1, 0, 0, 1, 0, 0);
  g.globalCompositeOperation = "source-in";
  g.fillStyle = `rgb(${(light.moon ? moonShade() : [0, 0, 0]).join(", ")})`;
  g.fillRect(0, 0, capitalLayer.width, capitalLayer.height);
  g.globalCompositeOperation = "source-over";
  ctx.save();
  ctx.setTransform(1, 0, 0, 1, 0, 0);
  ctx.globalAlpha = light.strength;
  ctx.drawImage(capitalLayer, 0, 0);
  ctx.restore();
  return shown.length;
}
function drawCapitalNames(size, scale, shown = capitalNames(size, scale)) {
  if (!shown.length) return;
  drawCapitalShadows(shown);
  const banner = bannerArt();
  for (const c of shown) {
    const cont = app.detailView.names?.[continentMap(app.detailView.capitals[c.id].inst)];
    const ink = `rgb(${(cont?.ink || [77, 50, 6]).join(",")})`, bevel = `rgb(${(cont?.bevel || [194, 158, 79]).join(",")})`;
    ctx.save();
    ctx.globalAlpha = c.alpha;
    drawCapitalPiece(ctx, c, banner, 0, 0);
    ctx.textBaseline = "middle";
    ctx.textAlign = "center";
    for (const l of c.letters) {
      ctx.save();
      ctx.translate(l.x, l.y);
      ctx.rotate(l.angle);
      ctx.font = `${l.px}px Metamorphous`;
      ctx.fillStyle = bevel;
      ctx.fillText(l.ch, 1, 1);
      ctx.fillStyle = ink;
      ctx.fillText(l.ch, 0, 0);
      ctx.restore();
    }
    ctx.restore();
  }
}
function namesOverYou(size, scale, places, capitals) {
  if (!app.disp || !app.state) return false;
  const [fx, fy] = convertFrac(app.state.map, app.displayMap, app.disp.x, app.disp.y, app.maps, worldRound());
  if (places.some(({ box: [x0, y0, x1, y1] }) => fx >= x0 && fx <= x1 && fy >= y0 && fy <= y1)) return true;
  const [sx, sy] = toScreen(app.disp.x, app.disp.y, size, scale);
  return capitals.some((c) => Math.abs(sx - c.x) <= c.w / 2 && sy >= c.y - c.h * CREST_SHARE * (0.5 + CREST_LIFT) && sy <= c.y + c.h / 2);
}

const HEAT_SCALE = 0.25;
const heat = { canvas: document.createElement("canvas"), sprite: null, ramps: {} };
const HEAT_CPU = { willReadFrequently: true };
heat.ctx = heat.canvas.getContext("2d", HEAT_CPU);

const ZONE_PEAK = 0.6;
function zoneSprite() {
  if (heat.zoneSprite) return heat.zoneSprite;
  const size = 64, c = document.createElement("canvas");
  c.width = c.height = size;
  const g = c.getContext("2d", HEAT_CPU);
  const grad = g.createRadialGradient(size / 2, size / 2, 0, size / 2, size / 2, size / 2);
  for (let i = 0; i <= 10; i++) {
    const r = i / 10, fall = r <= 0.5 ? 1 : (1 - ((r - 0.5) / 0.5) ** 2) ** 2;
    grad.addColorStop(r, tint("white", +(ZONE_PEAK * fall).toFixed(4)));
  }
  g.fillStyle = grad;
  g.fillRect(0, 0, size, size);
  heat.zoneSprite = c;
  return c;
}

function heatSprite() {
  if (heat.sprite) return heat.sprite;
  const size = 64, c = document.createElement("canvas");
  c.width = c.height = size;
  const g = c.getContext("2d", HEAT_CPU);
  const grad = g.createRadialGradient(size / 2, size / 2, 0, size / 2, size / 2, size / 2);
  for (let i = 0; i <= 10; i++) grad.addColorStop(i / 10, tint("white", +(0.2 * (1 - (i / 10) ** 2) ** 2).toFixed(4)));
  g.fillStyle = grad;
  g.fillRect(0, 0, size, size);
  heat.sprite = c;
  return c;
}

const hex = (h) => [1, 3, 5].map((i) => parseInt(h.slice(i, i + 2), 16));

const HEAT_FADE = 0.12;
const HEAT_TOP = 0.65, HEAT_MAX = 235;
const HEAT_FLOOR = 0.18, HEAT_BEND = 1.6;
function heatRamp(base, hot) {
  const key = base + hot;
  if (heat.ramps[key]) return heat.ramps[key];
  const b = hex(base), h = hex(hot);
  const ramp = new Uint8ClampedArray(256 * 4);
  for (let d = 0; d < 256; d++) {
    const f = d / 255;
    const t = Math.min(1, Math.max(0, (f - 0.2) / 0.45));
    for (let c = 0; c < 3; c++) ramp[d * 4 + c] = b[c] + (h[c] - b[c]) * t;
    const fade = Math.min(1, f / HEAT_FADE), climb = HEAT_FLOOR + (1 - HEAT_FLOOR) * Math.min(1, f / HEAT_TOP) ** HEAT_BEND;
    ramp[d * 4 + 3] = HEAT_MAX * climb * fade * fade * (3 - 2 * fade);
  }
  ramp.full = Math.round(HEAT_TOP * 255);
  heat.ramps[key] = ramp;
  return ramp;
}

const BAND_FROM = 0.04;
function bandRamp(bands) {
  const key = bands.join();
  if (heat.ramps[key]) return heat.ramps[key];
  const ramp = new Uint8ClampedArray(256 * 4), n = bands.length, cols = bands.map(hex);
  for (let d = 0; d < 256; d++) {
    const f = d / 255, i = Math.min(n - 1, Math.floor(Math.max(0, f - BAND_FROM) / (1 - BAND_FROM) * n));
    for (let c = 0; c < 3; c++) ramp[d * 4 + c] = cols[i][c];
    ramp[d * 4 + 3] = !d ? 0 : f < BAND_FROM ? 100 * f / BAND_FROM : 110 + 125 * i / Math.max(1, n - 1);
  }
  ramp.full = 255;
  heat.ramps[key] = ramp;
  return ramp;
}

const boosted = new WeakMap();
function boostRamp(ramp, gain) {
  const mine = boosted.get(ramp) || new Map();
  boosted.set(ramp, mine);
  if (mine.has(gain)) return mine.get(gain);
  const out = new Uint8ClampedArray(ramp);
  for (let d = 3; d < out.length; d += 4) out[d] = 255 * (1 - (1 - ramp[d] / 255) ** gain);
  out.full = ramp.full;
  mine.set(gain, out);
  return out;
}

function heatStretch(px, width = 0, part = null, full = 255) {
  let top = 0;
  if (part) {
    const [x0, y0, w, h] = part;
    for (let y = y0; y < y0 + h; y++) for (let p = (y * width + x0) * 4 + 3, end = p + w * 4; p < end; p += 4) if (px[p] > top) top = px[p];
  } else for (let p = 3; p < px.length; p += 4) if (px[p] > top) top = px[p];
  return top ? Math.min(8, Math.max(1, full / top)) : 1;
}

function heatRadius(mapId, size, scale) {
  const yd = mapYards(app.displayMap || mapId);
  return Math.max(8, yd ? SPAWN_RADIUS_YARDS * scale * size.w / yd.w : 16);
}

const HEAT_SHIFT = 4;
heat.kept = new Map();
heat.now = 0;
const HEAT_KEPT_MS = 2000;
const rampIds = new WeakMap();
let rampCount = 0;
function heatSig(pts, radius, ramp) {
  if (!rampIds.has(ramp)) rampIds.set(ramp, ++rampCount);
  const x0 = pts[0]?.[0] ?? 0, y0 = pts[0]?.[1] ?? 0;
  let h = pts.length | 0;
  for (const [x, y, w, own, tall] of pts) {
    h = Math.imul(h ^ Math.round((x - x0) * 8), 16777619);
    h = Math.imul(h ^ Math.round((y - y0) * 8), 16777619);
    h = Math.imul(h ^ (Math.round((w ?? 1) * 256) + (Math.round(own || 0) << 12)), 16777619);
    h = Math.imul(h ^ Math.round(tall || 0), 16777619);
  }
  return `${h}|${Math.round(radius * 8)}|${rampIds.get(ramp)}|${W}|${H}`;
}
function drawHeatImage(image, dx, dy, w = W, h = H) {
  paintGlow((g) => {
    g.setTransform(dpr, 0, 0, dpr, 0, 0);
    g.drawImage(image, dx, dy, w, h);
  }, { boosted: true });
}


const OVERLAY_CEIL = 0.6;
const glowLayer = { canvas: null, ctx: null, ground: null, gctx: null, light: null, lctx: null, marks: null, mctx: null, on: false, used: false,
  lit: false, parts: {}, frame: null, whole: false, groundLit: null, glctx: null, litNow: false, shaded: null, sctx: null, shadedNow: false,
  sky: null, kctx: null, skyDrawn: 0, cloudsAt: null, fires: [] };
function glowBegin(parts = {}) {
  const L = glowLayer, w = canvas.width, h = canvas.height;
  if (!L.canvas) {
    L.canvas = document.createElement("canvas");
    L.ground = document.createElement("canvas");
    L.groundLit = document.createElement("canvas");
    L.shaded = document.createElement("canvas");
    L.sky = document.createElement("canvas");
    L.light = document.createElement("canvas");
    L.marks = document.createElement("canvas");
    L.ctx = L.canvas.getContext("2d");
    L.gctx = L.ground.getContext("2d");
    L.glctx = L.groundLit.getContext("2d");
    L.sctx = L.shaded.getContext("2d");
    L.kctx = L.sky.getContext("2d");
    L.lctx = L.light.getContext("2d");
    L.mctx = L.marks.getContext("2d");
  }
  for (const c of [L.canvas, L.ground, L.groundLit, L.shaded, L.sky, L.light, L.marks]) if (c.width !== w || c.height !== h) { c.width = w; c.height = h; }
  L.parts = parts;
  L.litNow = false;
  L.shadedNow = false;
  L.cloudsAt = null;
  L.fires = [];
  L.frame = { at: ctx.getTransform(), quality: ctx.imageSmoothingQuality };
  L.whole = false;
  L.gctx.setTransform(1, 0, 0, 1, 0, 0);
  L.gctx.globalAlpha = 1;
  L.gctx.globalCompositeOperation = "copy";
  L.gctx.drawImage(canvas, 0, 0);
  L.gctx.globalCompositeOperation = "source-over";
  L.ctx.setTransform(1, 0, 0, 1, 0, 0);
  L.ctx.clearRect(0, 0, w, h);
  L.lctx.setTransform(1, 0, 0, 1, 0, 0);
  L.lctx.clearRect(0, 0, w, h);
  L.lit = false;
  ctx.save();
  ctx.setTransform(1, 0, 0, 1, 0, 0);
  ctx.clearRect(0, 0, w, h);
  ctx.restore();
  L.on = true;
  L.used = false;
}
function glowEnd() {
  const L = glowLayer;
  if (!L.on) return;
  L.on = false;
  L.mctx.setTransform(1, 0, 0, 1, 0, 0);
  L.mctx.globalCompositeOperation = "copy";
  L.mctx.drawImage(canvas, 0, 0);
  L.mctx.globalCompositeOperation = "source-over";
  L.whole = true;
  groundUnder();
}
function cloudsKey(sky) {
  return JSON.stringify([sky ? sky.jobs.map((j) => j.t ?? null) : null, clouds.builds || 0]);
}
function keepCanvas(g) {
  g.setTransform(1, 0, 0, 1, 0, 0);
  g.globalAlpha = 1;
  g.globalCompositeOperation = "copy";
  g.drawImage(canvas, 0, 0);
  g.globalCompositeOperation = "source-over";
}
function groundUnder(relit = false) {
  const L = glowLayer, P = L.parts;
  const framed = (paint) => {
    ctx.save();
    ctx.setTransform(L.frame.at);
    ctx.imageSmoothingQuality = L.frame.quality;
    const out = paint();
    ctx.restore();
    return out;
  };
  const sky = P.sky ? framed(P.sky) : null, at = cloudsKey(sky), fresh = at !== L.cloudsAt;
  L.cloudsAt = at;
  ctx.save();
  ctx.setTransform(1, 0, 0, 1, 0, 0);
  ctx.globalAlpha = 1;
  if (fresh) {
    ctx.clearRect(0, 0, canvas.width, canvas.height);
    L.skyDrawn = P.clouds ? framed(() => P.clouds(sky)) : 0;
    if (L.skyDrawn) keepCanvas(L.kctx);
  }
  ctx.globalCompositeOperation = "copy";
  const box = Array.isArray(relit) ? relit : null;
  if (L.shadedNow && !fresh && !relit) ctx.drawImage(L.shaded, 0, 0);
  else {
    if (P.lay && L.litNow && relit !== true) {
      ctx.drawImage(L.groundLit, 0, 0);
      if (box) {
        clipBox(ctx, box, () => {
          ctx.drawImage(L.ground, 0, 0);
          ctx.globalCompositeOperation = "source-over";
          framed(() => P.lay(box));
        });
        clipBox(L.glctx, box, () => keepCanvas(L.glctx));
      }
    } else {
      ctx.drawImage(L.ground, 0, 0);
      ctx.globalCompositeOperation = "source-over";
      if (P.lay) {
        framed(P.lay);
        keepCanvas(L.glctx);
        L.litNow = true;
      }
    }
    ctx.globalCompositeOperation = "source-over";
    if (box && L.shadedNow && !fresh) {
      if (P.shade) clipBox(ctx, box, () => framed(() => P.shade(sky, true)));
      clipBox(L.sctx, box, () => keepCanvas(L.sctx));
      ctx.globalCompositeOperation = "copy";
      ctx.drawImage(L.shaded, 0, 0);
    } else {
      if (P.shade) framed(() => P.shade(sky, !fresh));
      keepCanvas(L.sctx);
      L.shadedNow = true;
    }
  }
  ctx.globalCompositeOperation = "source-over";
  if (P.cores) framed(P.cores);
  if (P.sea) framed(P.sea);
  if (L.skyDrawn) ctx.drawImage(L.sky, 0, 0);
  if (P.storm) framed(P.storm);
  if (P.over) framed(P.over);
  if (L.used) {
    ctx.globalAlpha = OVERLAY_CEIL;
    ctx.globalCompositeOperation = "hard-light";
    ctx.drawImage(L.canvas, 0, 0);
    ctx.globalAlpha = 1;
  }
  if (L.lit) {
    ctx.globalCompositeOperation = "lighter";
    ctx.drawImage(L.light, 0, 0);
  }
  ctx.globalCompositeOperation = "source-over";
  layFires(L.fires);
  ctx.drawImage(L.marks, 0, 0);
  ctx.restore();
}
function paintGlow(paint, { alpha = ctx.globalAlpha, boosted = false, op = null, light = false } = {}) {
  if (light) return paintLight(paint, alpha);
  const strength = boosted ? alpha : Math.min(1, alpha / OVERLAY_CEIL);
  if (glowLayer.on) {
    const g = glowLayer.ctx;
    g.save();
    g.setTransform(ctx.getTransform());
    g.globalAlpha = strength;
    g.globalCompositeOperation = op || (ctx.globalCompositeOperation === "lighter" ? "lighter" : "source-over");
    g.imageSmoothingEnabled = true;
    g.imageSmoothingQuality = "high";
    g.filter = ctx.filter || "none";
    try { paint(g); } finally { g.restore(); }
    glowLayer.used = true;
    return;
  }
  ctx.save();
  ctx.globalAlpha = strength * OVERLAY_CEIL;
  ctx.globalCompositeOperation = "hard-light";
  ctx.imageSmoothingEnabled = true;
  ctx.imageSmoothingQuality = "high";
  try { paint(ctx); } finally { ctx.restore(); }
}
function paintLight(paint, alpha) {
  const L = glowLayer, g = L.on ? L.lctx : ctx;
  g.save();
  if (L.on) g.setTransform(ctx.getTransform());
  g.globalAlpha = alpha;
  g.globalCompositeOperation = "lighter";
  try { paint(g); } finally { g.restore(); }
  if (L.on) L.lit = true;
}
const ceiled = new WeakMap();
function ceilRamp(ramp) {
  if (ceiled.has(ramp)) return ceiled.get(ramp);
  const out = new Uint8ClampedArray(ramp);
  for (let d = 3; d < out.length; d += 4) out[d] = Math.min(255, Math.round(ramp[d] / OVERLAY_CEIL));
  out.full = ramp.full;
  ceiled.set(ramp, out);
  return out;
}
function forgetHeat() {
  heat.now = performance.now();
  for (const [key, kept] of heat.kept) if (heat.now - kept.used > HEAT_KEPT_MS) heat.kept.delete(key);
}

const HEAT_PAN = 0.5;
function renderHeat(pts, radius, ramp, sprite = heatSprite()) {
  pts = pts.filter((p) => Number.isFinite(p[0]) && Number.isFinite(p[1]));
  if (!pts.length) return;
  ramp = tonedRamp(ramp);
  const x0 = pts[0]?.[0] ?? 0, y0 = pts[0]?.[1] ?? 0, sig = heat.key != null ? heatSig(pts, radius, ramp) : null;
  const panning = !!drag?.moved;
  let kept = sig && heat.kept.get(heat.key);
  const give = !kept ? 0 : kept.padX ? (panning ? Math.min(kept.padX, kept.padY) : -1) : HEAT_SHIFT;
  if (kept && kept.sig === sig && Math.abs(x0 - kept.x0) <= give && Math.abs(y0 - kept.y0) <= give) {
    kept.used = heat.now;
    return drawHeatImage(kept.canvas, x0 - kept.x0 - kept.padX, y0 - kept.y0 - kept.padY, W + 2 * kept.padX, H + 2 * kept.padY);
  }
  if (sig && !kept) {
    const canvas = document.createElement("canvas");
    kept = { canvas, ctx: canvas.getContext("2d", { willReadFrequently: true }) };
    heat.kept.set(heat.key, kept);
  }
  const target = kept || heat;
  const pad = (side) => (kept && panning ? Math.round(side * HEAT_PAN * HEAT_SCALE) / HEAT_SCALE : 0);
  const padX = pad(W), padY = pad(H);
  const hw = Math.max(1, Math.round((W + 2 * padX) * HEAT_SCALE)), hh = Math.max(1, Math.round((H + 2 * padY) * HEAT_SCALE));
  if (target.canvas.width !== hw || target.canvas.height !== hh) { target.canvas.width = hw; target.canvas.height = hh; }
  const hc = target.ctx;
  hc.setTransform(1, 0, 0, 1, 0, 0);
  hc.globalCompositeOperation = "source-over";
  hc.globalAlpha = 1;
  hc.clearRect(0, 0, hw, hh);
  hc.setTransform(HEAT_SCALE, 0, 0, HEAT_SCALE, padX * HEAT_SCALE, padY * HEAT_SCALE);
  hc.globalCompositeOperation = "lighter";
  for (const [x, y, w, own, tall] of pts) {
    const r = own || radius, r2 = tall || r;
    if (x < -r - padX || y < -r2 - padY || x > W + r + padX || y > H + r2 + padY) continue;
    hc.globalAlpha = w ?? 1;
    hc.drawImage(sprite, x - r, y - r2, r * 2, r2 * 2);
  }
  hc.globalAlpha = 1;
  const img = hc.getImageData(0, 0, hw, hh), px = img.data;
  const k = heatStretch(px, hw, [padX * HEAT_SCALE, padY * HEAT_SCALE, Math.round(W * HEAT_SCALE), Math.round(H * HEAT_SCALE)], ramp.full);
  const tone = ceilRamp(ramp);
  for (let p = 0; p < px.length; p += 4) {
    const d = Math.min(255, Math.round(px[p + 3] * k)) * 4;
    px[p] = tone[d]; px[p + 1] = tone[d + 1]; px[p + 2] = tone[d + 2]; px[p + 3] = tone[d + 3];
  }
  hc.putImageData(img, 0, 0);
  if (kept) Object.assign(kept, { sig, x0, y0, padX, padY, used: heat.now });
  drawHeatImage(target.canvas, -padX, -padY, W + 2 * padX, H + 2 * padY);
}


app.overlays = [];
app.lit = null;
const overlayKey = (name, base) => `${name}|${base}`;
app.overlaySet = new Map();
const OFF_FORGET_MS = 1500;
const offName = (name) => name.replace(/^\d+\s*\/\s*\d+\s+/, "");
const overlayOff = (name) => !!app.overlaySet.get(offName(name))?.off;
const overlayLevel = (name) => app.overlaySet.get(offName(name))?.level ?? 1;
function setOverlay(name, change) {
  const set = { off: false, level: 1, ...app.overlaySet.get(name), ...change, gone: null };
  if (!set.off && set.level >= 1) app.overlaySet.delete(name);
  else app.overlaySet.set(name, set);
}
const LEVEL_PULL = 0.5;
const levelTone = (level) => ({ pull: Math.min(1, (1 - level) / LEVEL_PULL), alpha: Math.min(1, level / (1 - LEVEL_PULL)) });
const pullRgb = (rgb, base, pull) => rgb.map((c, k) => Math.round(c + (base[k] - c) * pull));
heat.tone = null;
const PULL_STEPS = 32;
const pulledRamps = new WeakMap();
function tonedRamp(ramp) {
  const tone = heat.tone;
  if (!tone) return ramp;
  const mine = pulledRamps.get(ramp) || new Map(), key = `${tone.base}|${tone.pull}`;
  pulledRamps.set(ramp, mine);
  if (mine.has(key)) return mine.get(key);
  const out = new Uint8ClampedArray(ramp);
  for (let d = 0; d < out.length; d += 4) out.set(pullRgb([ramp[d], ramp[d + 1], ramp[d + 2]], tone.base, tone.pull), d);
  out.full = ramp.full;
  mine.set(key, out);
  return out;
}
const tonedRgb = (rgb) => (heat.tone ? pullRgb(rgb, heat.tone.base, heat.tone.pull) : rgb);
function noteOverlay(name, base, hot, style = "", bands = null) {
  if (!app.overlays.some((o) => o.name === name && o.base === base)) app.overlays.push({ name, base, hot: hot || base, style, bands });
}

const bandSwatch = (bands) => `linear-gradient(90deg, ${bands.map((c, i) => `${c} ${(i * 100 / bands.length).toFixed(1)}% ${((i + 1) * 100 / bands.length).toFixed(1)}%`).join(", ")})`;

const QUEST_FLASH_MS = 1500, QUEST_FLASH_PULSES = 2, CLICK_FRESH_S = 5;
const QUEST_FLASH_STEP = QUEST_FLASH_MS / (2 * QUEST_FLASH_PULSES - 1);
app.questFlash = null;
let clickHeard = null;
function takeQuestClick(click, nowS = Date.now() / 1000) {
  if (!click) return;
  const said = `${click.quest}:${click.n}:${click.at}`;
  if (said === clickHeard) return;
  clickHeard = said;
  if (!(nowS - click.at < CLICK_FRESH_S)) return;
  app.questFlash = { quest: click.quest, at: performance.now() };
  redraw();
}
function questFlashing(quests) {
  const f = app.questFlash;
  if (!f || !quests?.includes(f.quest)) return false;
  const t = performance.now() - f.at;
  if (t >= QUEST_FLASH_MS) return false;
  const step = Math.floor(t / QUEST_FLASH_STEP);
  redrawIn(QUEST_FLASH_STEP * (step + 1) - t);
  return step % 2 === 0;
}

app.litPaint = [];
function drawLit(name, base, paint, quests = null) {
  const flash = questFlashing(quests);
  if (!flash && overlayOff(name)) return;
  const key = overlayKey(name, base), { pull, alpha } = levelTone(flash ? 1 : overlayLevel(name)), step = Math.round(pull * PULL_STEPS);
  const run = () => {
    const was = ctx.globalAlpha;
    heat.key = key;
    heat.tone = step ? { base: hex(base), pull: step / PULL_STEPS } : null;
    ctx.globalAlpha = was * alpha;
    try { paint(); } finally { heat.key = null; heat.tone = null; ctx.globalAlpha = was; }
  };
  if (app.lit === key || flash) app.litPaint.push(run);
  else run();
}

function drawLitLast() {
  const queued = app.litPaint;
  app.litPaint = [];
  if (!queued.length) return;
  const paint = () => queued.forEach((p) => p());
  paint();
  ctx.save();
  ctx.globalCompositeOperation = "lighter";
  ctx.globalAlpha = 0.35;
  paint();
  ctx.restore();
}

function renderOverlayLegend() {
  const box = $("overlay-legend"), now = performance.now(), here = new Set(app.overlays.map((o) => offName(o.name)));
  for (const [name, set] of app.overlaySet) {
    if (here.has(name)) { set.gone = null; continue; }
    set.gone ??= now;
    if (now - set.gone >= OFF_FORGET_MS) app.overlaySet.delete(name);
    else redrawIn(set.gone + OFF_FORGET_MS - now);
  }
  const html = app.overlays.map((o) => {
    const off = overlayOff(o.name);
    return `<div class="ol-item${o.style ? ` ${o.style}` : ""}${o.bands ? " banded" : ""}${off ? " off" : ""}" role="button" tabindex="0" aria-pressed="${!off}"
      data-key="${esc(overlayKey(o.name, o.base))}" data-name="${esc(offName(o.name))}"
      style="--a:${o.base};--b:${o.hot}${o.bands ? `;--bands:${bandSwatch(o.bands)}` : ""}"><span>${esc(o.name)}</span></div>`;
  }).join("");
  const focused = document.activeElement?.closest?.("#overlay-legend .ol-item")?.dataset.key;
  setHtml(box, html);
  const items = [...box.querySelectorAll(".ol-item")];
  for (const el of items) {
    const level = overlayLevel(el.dataset.name), fill = `${+(level * 100).toFixed(1)}%`, pull = `${+(levelTone(level).pull * 100).toFixed(1)}%`;
    if (el.style.getPropertyValue("--fill") !== fill) el.style.setProperty("--fill", fill);
    if (el.style.getPropertyValue("--pull") !== pull) el.style.setProperty("--pull", pull);
  }
  if (focused) items.find((el) => el.dataset.key === focused)?.focus();
  box.hidden = !html;
  const keys = document.querySelector(".mapkeys");
  const room = `${(keys?.offsetWidth || 0) + 32}px`;
  if (box.style.getPropertyValue("--keys-w") !== room) box.style.setProperty("--keys-w", room);
}

function legendTip(item) {
  const tip = $("ol-tip"), span = item.firstElementChild, name = item.dataset.name;
  const click = overlayOff(name) ? "Click to show." : "Click to hide.";
  const ctrl = soloName() === name ? "Ctrl+click to show all again." : "Ctrl+click to show only this one.";
  const full = span.scrollWidth > span.clientWidth ? `<span class="ol-name">${esc(span.textContent)}</span>` : "";
  tip.innerHTML = `${full}<span class="ol-hint">${click} ${ctrl}</span><span class="ol-hint">Drag left or right to fade this one down or up.</span>`;
  tip.hidden = false;
  const r = item.getBoundingClientRect(), stage = $("overlay-legend").parentElement.getBoundingClientRect();
  const at = tipPlace({ left: r.left - stage.left, right: r.right - stage.left, top: r.top - stage.top, bottom: r.bottom - stage.top },
    tip.offsetWidth, tip.offsetHeight, { left: 0, top: 0, right: stage.width, bottom: stage.height }, { x: "centre", y: "above", gap: 8, margin: 8 });
  tip.style.left = `${at.x}px`;
  tip.style.top = `${at.y}px`;
}
$("overlay-legend").addEventListener("mouseover", (e) => {
  const item = e.target.closest(".ol-item");
  if (!item) return;
  if (app.lit !== item.dataset.key) { app.lit = item.dataset.key; redraw(); }
  legendTip(item);
});
$("overlay-legend").addEventListener("mouseleave", () => { app.lit = null; $("ol-tip").hidden = true; redraw(); });
function switchOverlay(name) {
  setOverlay(name, { off: !overlayOff(name) });
  renderOverlayLegend();
}
const legendNames = () => [...new Set(app.overlays.map((o) => offName(o.name)))];
function soloName() {
  const names = legendNames(), on = names.filter((n) => !overlayOff(n));
  return names.length > 1 && on.length === 1 ? on[0] : null;
}
function soloOverlay(name) {
  if (soloName() === name) for (const n of [...app.overlaySet.keys()]) setOverlay(n, { off: false });
  else {
    for (const n of legendNames()) if (n !== name) setOverlay(n, { off: true });
    setOverlay(name, { off: false });
  }
  renderOverlayLegend();
}
function pressOverlay(item, e) {
  const key = item.dataset.key;
  (e.ctrlKey || e.metaKey ? soloOverlay : switchOverlay)(item.dataset.name);
  const now = [...$("overlay-legend").querySelectorAll(".ol-item")].find((el) => el.dataset.key === key);
  if (now) legendTip(now);
}
$("overlay-legend").addEventListener("click", (e) => {
  const item = e.target.closest(".ol-item");
  if (legendDrag?.moved) legendDrag = null;
  else if (item) pressOverlay(item, e);
});
const LEVEL_DRAG_PX = 240, CLICK_SLOP_PX = 4;
let legendDrag = null;
$("overlay-legend").addEventListener("pointerdown", (e) => {
  const item = e.target.closest(".ol-item");
  legendDrag = item && e.button === 0
    ? { name: item.dataset.name, key: item.dataset.key, x: e.clientX, from: overlayLevel(item.dataset.name), moved: false } : null;
});
$("overlay-legend").addEventListener("pointermove", (e) => {
  const d = legendDrag, dx = d?.name ? e.clientX - d.x : 0;
  if (!d?.name || (!d.moved && Math.abs(dx) < CLICK_SLOP_PX)) return;
  if (!d.moved) $("overlay-legend").setPointerCapture?.(e.pointerId);
  d.moved = true;
  setOverlay(d.name, { level: Math.min(1, Math.max(0, d.from + dx / LEVEL_DRAG_PX)) });
  renderOverlayLegend();
  redraw();
  const item = [...$("overlay-legend").querySelectorAll(".ol-item")].find((el) => el.dataset.key === d.key);
  if (item) legendTip(item);
});
for (const type of ["pointerup", "pointercancel"]) {
  $("overlay-legend").addEventListener(type, () => { legendDrag = legendDrag?.moved ? { moved: true } : null; });
}
function legendKey(e) {
  const item = e.target.closest?.(".ol-item");
  if ((e.key !== "Enter" && e.key !== " ") || !item) return false;
  e.preventDefault();
  pressOverlay(item, e);
  return true;
}
$("overlay-legend").addEventListener("focusin", (e) => {
  const item = e.target.closest?.(".ol-item");
  if (!item) return;
  if (app.lit !== item.dataset.key) { app.lit = item.dataset.key; redraw(); }
  legendTip(item);
});
$("overlay-legend").addEventListener("focusout", () => { app.lit = null; $("ol-tip").hidden = true; redraw(); });

function strokePath(pts) {
  ctx.beginPath();
  ctx.moveTo(...pts[0]);
  for (let i = 1; i < pts.length; i++) ctx.lineTo(...pts[i]);
  ctx.stroke();
}

const MARK_FONT = "Marcellus, Georgia, serif";
function drawRingMarker(x, y, { r, fill, ring, width = 2, edge = 0, text = null, font = `11px ${MARK_FONT}`, color = tint("ivory"),
  dy = 1, icon = null }) {
  if (edge) { ctx.beginPath(); ctx.arc(x, y, r + edge, 0, Math.PI * 2); ctx.fillStyle = tint("black"); ctx.fill(); }
  ctx.beginPath(); ctx.arc(x, y, r, 0, Math.PI * 2);
  ctx.fillStyle = fill; ctx.fill();
  ctx.lineWidth = width; ctx.strokeStyle = ring; ctx.stroke();
  if (icon?.complete && icon.naturalWidth) {
    const ir = r - 3;
    ctx.save(); ctx.beginPath(); ctx.arc(x, y, ir, 0, Math.PI * 2); ctx.clip();
    ctx.drawImage(icon, x - ir, y - ir, ir * 2, ir * 2); ctx.restore();
  }
  if (text == null) return;
  ctx.fillStyle = color; ctx.font = font; ctx.textAlign = "center"; ctx.textBaseline = "middle";
  ctx.fillText(String(text), x, y + dy);
}

function drawWay(line, color, { way = null, screen = null, dots = false } = {}) {
  if (way) drawDanger(way, screen);
  const here = heightHere();
  if (dots) strokeDots(line, color, here); else strokeWay(line, color, undefined, here);
  drawArrowheads(line, color, DIRECTION_EVERY);
}
function drawCutOff(from, to) {
  ctx.save();
  ctx.setLineDash([2, 6]); ctx.lineCap = "round";
  ctx.lineWidth = 2; ctx.strokeStyle = CUT_OFF_COLOR; strokePath([from, to]);
  ctx.restore();
}

function drawPatrol(pts, color) {
  if (pts.length < 2) return;
  ctx.setLineDash([0.01, 9]); ctx.lineCap = "round";
  ctx.lineWidth = 6.5; ctx.strokeStyle = tint("black", 0.6); strokePath(pts);
  ctx.lineWidth = 4; ctx.strokeStyle = color; strokePath(pts);
  ctx.setLineDash([]); ctx.lineCap = "butt";
}

let needleAt = null;
function layoutView() {
  const s = app.state, v = app.view;
  if (!s) return;
  if (v.follow) { v.zone = null; v.contMap = null; }
  passOver();
  passInto();
  passAcross();
  app.displayMap = viewMap();
  const lit = app.maps[app.displayMap];
  if (lit?.world && mapTiles.renders(lit.instance)) relief = lightOf(lit.instance);
  const me = followed(), myMap = me ? me.map : s.map;
  if (app.displayMap === myMap && v.backTo == null) { v.continent = app.maps[myMap]?.type === 2 ? v.continent || "zoom" : null; v.world = false; }
  updateToZones();
  const size = imgSize(mapImage(app.displayMap)), scale = scaleFor(size);
  app.curSize = size;
  v.rot = v.headingUp && me ? me.facing : 0;
  if (v.follow && me) {
    const you = convertFrac(myMap, app.displayMap, me.x, me.y);
    if (Number.isNaN(you[0])) [v.cx, v.cy] = [0.5, 0.5];
    else centreInClear(you, size, app.clearShown || clearView());
  }
  holdPan();
  if (v.rot !== needleAt) { needleAt = v.rot; needle.style.transform = `rotate(${v.rot}rad)`; }
  mapLight.turn(v.rot);
  mapLight.lower(pointerDepth(v.zoom, MIN_ZOOM, MAX_ZOOM, v.world || v.continent), yardPx(app.displayMap, size, scale));
  updateLocate(size, scale);
  const detailWas = app.detail.current + app.detail.drawn;
  chooseDetail(app.displayMap, size, scale);
  if (app.detail.current + app.detail.drawn !== detailWas) requestUpdate();
  chooseCities(app.displayMap, size, scale);
  showCity();
  wantMaps(size, scale);
}

const mapFades = new Fades(() => lessMotion());
function wantMaps(size, scale) {
  noteMapSwitch();
  mapFades.want("terrain", app.detail.drawn === "high" ? 1 : 0, FADE_SWITCH);
  wantOverMaps(app.displayMap, size, scale);
  wantZones();
}
let mapShownLast = null;
function noteMapSwitch() {
  const from = mapShownLast, to = app.displayMap;
  mapShownLast = to;
  if (from == null || from === to) return;
  const paper = 1 - mapFades.get("terrain");
  const back = mapFades.get(`was:${to}`), share = paper * (1 - back);
  mapFades.drop(`was:${to}`);
  const a = app.maps[from], b = app.maps[to];
  if (!a?.world || !b?.world || a.instance !== b.instance) mapFades.want("terrain", app.detail.drawn === "high" ? 1 : 0, FADE_SWITCH, { now: true });
  if (mapOn(from, to)) mapFades.want(`was:${from}`, 0, FADE_SWITCH, { from: share, data: { map: from } });
  else for (const f of mapFades.list("was:")) mapFades.drop(f.key);
}
function drawLeaving(size, scale = 0) {
  const going = mapFades.list("was:");
  for (let k = going.length - 1; k >= 0; k--) {
    const f = going[k], entry = app.images[f.data.map], at = mapOn(f.data.map, app.displayMap);
    const rendered = f.data.map === WORLD_MAP && app.mapKinds === "detailed";
    if (!(entry?.ok || rendered) || !at) continue;
    const x = at[0] * size.w, y = at[1] * size.h, w = (at[2] - at[0]) * size.w, h = (at[3] - at[1]) * size.h;
    ctx.globalAlpha = f.at;
    if (rendered) {
      const own = imgSize(mapImage(WORLD_MAP));
      ctx.save();
      ctx.translate(x, y);
      ctx.scale(w / own.w, h / own.h);
      drawWorldRender(own, scale * w / own.w);
      ctx.restore();
    } else ctx.drawImage(paperOf(entry, perPicturePx(entry, w, scale)), x, y, w, h);
  }
  ctx.globalAlpha = 1;
}

function paintSea() {
  if (belowShown()) { ctx.clearRect(0, 0, W, H); return; }
  if (detailedOnly() || worldRender()) { ctx.fillStyle = seaFill(); ctx.fillRect(0, 0, W, H); return; }
  if (tintArt("sea")) ctx.clearRect(0, 0, W, H);
  else { ctx.fillStyle = tint("sea"); ctx.fillRect(0, 0, W, H); }
}

function draw() {
  glowLayer.whole = false;
  groundTicks.clouds = groundTicks.light = groundTicks.cores = groundTicks.fire = null;
  if (!canvas.width || !canvas.height) return;
  noteViewMoved();
  ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
  paintSea();
  const s = app.state;
  app.overlays = [];
  forgetHeat();
  app.youOnScreen = null;
  if (!s) { mapLight.hideYou(); return; }
  redrawIn(mapLight.minuteIn());

  const entry = mapImage(app.displayMap);
  if (app.maps && (!entry || entry.ok || entry.failed || detailedOnly() || worldRender())) loadBox?.leave();
  const v = app.view, size = app.curSize, scale = scaleFor(size);
  const live = !app.replayYou;
  ctx.save();
  ctx.translate(W / 2, H / 2);
  ctx.rotate(v.rot);
  ctx.scale(scale, scale);
  ctx.translate(-v.cx * size.w, -v.cy * size.h);
  if (detailedOnly() || belowShown()) {
  } else if (worldRender()) {
    drawWorldRender(size, scale);
  } else if (entry?.ok) {
    ctx.imageSmoothingQuality = "high";
    ctx.drawImage(paperOf(entry, perPicturePx(entry, size.w, scale)), 0, 0, size.w, size.h);
  } else {
    ctx.fillStyle = tint("map-blank");
    ctx.fillRect(0, 0, size.w, size.h);
    drawGrid(size, scale);
  }
  const terrain = mapFades.get("terrain"), frames = worldFrames(size, scale);
  if (terrain > 0) {
    drawTiles(app.displayMap, size, scale);
    for (const f of frames) inFrame(f, size, () => drawTiles(f.map, f.size, f.scale, f));
  }
  if (terrain > 0 && terrain < 1 && entry?.ok) {
    ctx.globalAlpha = 1 - terrain;
    ctx.drawImage(paperOf(entry, perPicturePx(entry, size.w, scale)), 0, 0, size.w, size.h);
    ctx.globalAlpha = 1;
  }
  drawLeaving(size, scale);
  mapLight.underground(undergroundShown(app.displayMap, size).inside);
  const raised = sheetDepth(size, scale);
  castMapShadow(mapLight.sheetShadow(raised));
  mapLight.sheets(citySheets(app.displayMap, size).map(({ at, fade }) => ({ ...rectOnScreen(at, size, scale), fade })), raised);
  drawOverMaps(app.displayMap, size, scale);
  blood.paint(ctx, { project: (inst, n, w) => worldOnScreen(inst, n, w, size, scale), turn: v.rot, map: app.displayMap, dpr,
                     width: W, height: H });
  const places = placeNames(size, scale), capitals = capitalNames(size, scale);
  const named = nameShown(size, scale, terrain, frames) > 0 || ((terrain > 0 || worldRender()) && cloudsOverYou())
    || namesOverYou(size, scale, places, capitals);
  if (!named) drawLastSeen(s, size, scale);
  if (!named) drawYouOnGround(size, scale, terrain);
  else app.youGrounded = false;
  drawTrees(size, scale, terrain);
  relief.frame(() => drawRelief(size, scale, terrain, frames));
  if (youLightOwed()) redraw();
  const namesOver = placesOverClouds(size, scale);
  glowBegin({
    lay: layLight,
    cores: layCores,
    sky: () => detailClouds(size, scale, terrain, frames),
    shade: (sky, again) => drawCloudShadows(size, scale, terrain, sky, again),
    sea: () => {
      seaTicks.on = drawSea(size);
      if (!namesOver) drawPlaceNames(size, scale, places);
    },
    clouds: (sky) => drawClouds(size, scale, terrain, sky) + drawWorldClouds(size, scale),
    storm: () => storm.draw(ctx, performance.now(), dpr),
    over: () => {
      drawBelowRim(size, scale);
      drawContinentName(size, scale, terrain, frames);
      if (namesOver) drawPlaceNames(size, scale, places);
      if (named) drawLastSeen(s, size, scale);
    },
  });
  paintBelow(size, scale);
  makeBelowRim(size, scale);
  drawZoneGlow(size);
  if (terrain < 1 && !worldRender() && !belowShown()) {
    ctx.globalAlpha = 1 - terrain;
    ctx.lineWidth = 2 / scale; ctx.strokeStyle = tint("black");
    ctx.strokeRect(0, 0, size.w, size.h);
    ctx.globalAlpha = 1;
  }
  ctx.restore();
  drawCapitalNames(size, scale, capitals);

  poi.drawn = [];
  dangerDrawn.length = 0;
  trickyDrawn.length = 0;
  easyDrawn.length = 0;
  drawLayers(s, size, scale);
  drawWaiting(ghostWaits(), () => drawLoopZone(size, scale));
  drawZoneNames(size, scale);
  drawDungeon(s, size, scale);

  if (live) app.trail.forEach((p, i) => {
    const [x, y] = toScreen(p.x, p.y, size, scale);
    ctx.beginPath(); ctx.arc(x, y, 2.2, 0, Math.PI * 2);
    ctx.fillStyle = tint("ivory", 0.15 + 0.55 * (i / app.trail.length));
    ctx.fill();
  });

  drawTravel(size, scale);

  drawPois(s, size, scale);
  drawIndoorPortals(s, size, scale);
  drawMobs(s, size, scale);
  if (live) drawNpcHeat(s, size, scale);
  drawRespawns(s, size, scale);
  drawFires(s, size, scale);
  drawBooks(s, size, scale);
  if (live) {
    drawRouteWeighing(size, scale);
    drawWaiting(ghostWaits() && !isCorpseRun(shownGuide()), () => drawGuide(s, size, scale));
    drawTracks(s, size, scale);
  }
  drawQuestRing(size, scale);

  drawHiddenGuess(size, scale);

  drawLitLast();
  drawPilesOnTop();
  drawLastSeen(s, size, scale, true);
  if (live) emit("livedraw", size, scale);
  emit("mapdraw", size, scale);
  glowEnd();
  mapLight.ownLight(relief.drew, relief.underPointer);
  askGroundTick();
  if (app.disp) {
    const [x, y] = toScreen(app.disp.x, app.disp.y, size, scale);
    app.youOnScreen = { x, y };
    drawPlayer(x, y, -app.disp.facing + v.rot, !live);
  } else mapLight.hideYou();
}


const TICK_MS = 1000;
let frameAsked = 0, tickTimer = 0, updateDue = false, lastFrame = 0;
const DUE_AFTER_MS = 1;
let redrawDue = Infinity, dueTimer = 0;
function redrawIn(ms) {
  if (ms < Infinity) redrawDue = Math.min(redrawDue, performance.now() + Math.max(0, ms));
}
function redraw() {
  if (!frameAsked) frameAsked = askFrame(frame);
}
function requestUpdate() {
  updateDue = true;
  redraw();
}
function update() {
  updateDue = false;
  clearTimeout(tickTimer);
  tickTimer = setTimeout(update, TICK_MS);
  emit("update");
}
function frame(now) {
  frameAsked = 0;
  const gap = now - lastFrame;
  const dt = lastFrame && gap > 0 && gap < 250 ? Math.min(0.1, gap / 1000) : 1 / 60;
  lastFrame = now;
  if (updateDue) update();
  const moving = step("animate", () => animate(dt, now));
  redrawDue = Infinity;
  step("map", () => { layoutView(); draw(); });
  step("legend", renderOverlayLegend);
  if (moving || mapFades.moving()) redraw();
  clearTimeout(dueTimer);
  dueTimer = redrawDue < Infinity ? setTimeout(redraw, redrawDue + DUE_AFTER_MS - performance.now()) : 0;
}
function animate(dt, now) {
  let moving = mapFades.step(dt * 1000);
  if (smooth(dt)) moving = true;
  if (app.band.pull > 0) {
    if (now - app.band.last > BAND_WAIT_MS) {
      app.band.pull *= Math.exp(-dt * 9);
      if (app.band.pull < 0.002) app.band.pull = 0;
    }
    moving = true;
  }
  return emit("animate", now).some(Boolean) || moving;
}
on("answer", requestUpdate);



const lastSeenOnly = () => !!app.state?.seen && !app.state.pos;
let followBefore = null;
const FOLLOW_TITLE = $("btn-follow").title;
function takeLastSeen(seen) {
  if (seen?.map == null) {
    if (app.state) return;
    seen = { ...seen, map: WORLD_MAP };
  }
  const first = !lastSeenOnly();
  app.state = { map: seen.map, pos: null, facing: null, level: seen.level, zone: seen.zone, subzone: seen.subzone, flags: {}, seen };
  if (!first) return;
  const v = app.view;
  followBefore = v.follow;
  v.follow = false;
  if (v.backTo == null) {
    v.zone = null; v.contMap = null; v.continent = null; v.world = false; v.drawnHeld = false;
    [v.cx, v.cy] = seen.pos ? convertFrac(seen.map, shownMap(seen.map), seen.pos.x, seen.pos.y) : [0.5, 0.5];
    if (Number.isNaN(v.cx)) [v.cx, v.cy] = [0.5, 0.5];
  }
  followWaits(true);
}
function endLastSeen() {
  app.view.follow = followBefore ?? true;
  followBefore = null;
  followWaits(false);
}
function followWaits(waits) {
  const b = $("btn-follow");
  b.disabled = waits;
  b.title = waits ? "Follow waits for the game. The strip isn't read, so the map shows where the character was last seen" : FOLLOW_TITLE;
  showFollow();
}
const seenMarks = (s) => [...(s.seen ? [s.seen] : []), ...altsSeen(s.seen)];
function drawLastSeen(s, size, scale, label = false) {
  if (app.dungeon) return;
  for (const seen of seenMarks(s)) {
    if (!seen.pos) continue;
    const [x, y] = toScreen(seen.pos.x, seen.pos.y, size, scale, seen.map);
    if (!(x > -40 && y > -40 && x < W + 40 && y < H + 40)) continue;
    ctx.save();
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    if (!label) paintArrow(ctx, x, y, -(seen.facing || 0) + app.view.rot, seenLook(), null, dpr);
    else drawLastSeenLabel(seen, x, y);
    ctx.restore();
  }
}
function showSeen(seen) {
  const zone = seen?.map != null ? shownMap(seen.map) : null;
  if (zone == null) return;
  const f = seen.pos && convertFrac(seen.map, zone, seen.pos.x, seen.pos.y);
  if (f && Number.isFinite(f[0] + f[1])) showSpot(seen.map, zone, f);
  else showZone(zone);
}
function drawLastSeenLabel(seen, x, y) {
  ctx.font = "600 13px 'Open Sans', Arial, sans-serif";
  ctx.textAlign = "center"; ctx.textBaseline = "middle";
  const label = lastSeenText(seen);
  ctx.lineWidth = 4; ctx.strokeStyle = tint("black"); ctx.strokeText(label, x, y + 26);
  ctx.fillStyle = tint("text"); ctx.fillText(label, x, y + 26);
  redrawIn(agoTurns(seen.at) * 1000);
}
const seenLook = () => ({ lit: tint("text"), mid: tint("text-dim"), shade: tint("iron"), edge: null, rim: tint("black"), seen: true });
const nobodySeen = (seen) => seen.at === undefined;
const lastSeenText = (seen) => nobodySeen(seen) ? "" : `${seen.name ? `${seen.name} ` : ""}last seen ${ago(seen.at)}`.replace(/^l/, "L");

function setFollow(on, target = "you") {
  if (lastSeenOnly() && target === "you") on = false;
  app.view.follow = on;
  if (on) app.view.target = target;
  showFollow();
  updateViewZone();
  keepView();
  redraw();
}
function showFollow() {
  $("btn-follow").setAttribute("aria-pressed", String(followingYou()));
  emit("follow");
}

function keepView() {
  const v = app.view, on = viewMap();
  if (on == null || app.dungeon || v.continent === "taxi" || v.backTo != null) return;
  const before = cityFrom ?? indoorFrom, zoom = v.follow && before != null ? before : v.zoom;
  keepIn("cc.view", { follow: lastSeenOnly() ? followBefore !== false : v.follow, zoom, zoneZoom: v.zoneZoom, world: v.world, continent: v.continent, on, cx: v.cx, cy: v.cy,
                      held: !!v.drawnHeld });
}
const viewKept = keptOr("cc.view", {});
function viewBack(k = viewKept) {
  const v = app.view, zoom = (z) => (Number.isFinite(z) ? Math.min(MAX_ZOOM, Math.max(MIN_ZOOM, z)) : null);
  if (zoom(k.zoom) == null) return;
  v.zoom = zoom(k.zoom);
  v.zoneZoom = zoom(k.zoneZoom) ?? v.zoom;
  v.follow = k.follow !== false;
  v.world = k.world === true;
  v.continent = !v.world && (k.continent === "zoom" || k.continent === "route") ? k.continent : null;
  v.drawnHeld = k.held === true && !!v.continent;
  if (!v.follow && Number.isFinite(k.cx) && Number.isFinite(k.cy) && Number.isInteger(k.on)) {
    [v.cx, v.cy] = [k.cx, k.cy];
    v.backTo = k.on;
  } else v.follow = true;
  showFollow();
}
viewBack();
function settleView() {
  const v = app.view, s = app.state, on = v.backTo;
  if (on == null || !s || !Object.keys(app.maps).length) return;
  v.backTo = null;
  if (app.dungeon || !app.maps[on]) { v.continent = null; v.world = false; return setFollow(true); }
  if (v.continent) v.contMap = on === continentOf(s.map) ? null : on;
  else if (!v.world) v.zone = shownMap(on) === shownMap(s.map) ? null : on;
  viewMoved();
}
on("update", settleView);

const LOCATE_IN = 0.5;
function closeZoom(map, home = shownMap(map), pxPerYard = 0) {
  const high = zoomShowing(home, home === map ? HIGH_AT_PX_PER_YARD : TILES_FROM_ZOOM * cityFit(map)), near = zoomShowing(home, pxPerYard);
  if (high == null || near == null) return null;
  return Math.min(MAX_ZOOM, Math.max(MIN_ZOOM, high * Math.pow(Math.max(1, MAX_ZOOM / high), LOCATE_IN), near));
}
function zoomShowing(home, pxPerYard) {
  const mine = app.maps[home]?.world, size = imgSize(mapImage(home));
  if (!mine || !size?.w) return null;
  const zoom = pxPerYard * Math.abs(mine.left - mine.right) / (size.w * Math.min(W / size.w, H / size.h) * bandScale());
  return Number.isFinite(zoom) ? zoom : null;
}
function centreOnMe(zoomTo = closeZoom) {
  const s = app.state, v = app.view;
  if (!s || !app.disp) return;
  if (v.follow && !followingYou()) setFollow(false);
  const shown = app.maps[app.displayMap]?.world, cur = app.curSize;
  const now = shown && cur ? scaleFor(cur) * cur.w / Math.abs(shown.left - shown.right) : 0;
  v.zone = null; v.contMap = null; v.world = false; v.continent = null;
  const home = shownMap(s.map);
  [v.cx, v.cy] = convertFrac(s.map, home, app.disp.x, app.disp.y);
  v.zoom = zoomTo(s.map, home, now) ?? v.zoom;
  viewMoved();
}
$("btn-locate").addEventListener("click", () => centreOnMe());

let offScreen = null;
function updateLocate(size, scale) {
  let off = false;
  if (!followingYou() && app.disp && app.state?.pos) {
    const [x, y] = toScreen(app.disp.x, app.disp.y, size, scale);
    off = !(x >= 12 && y >= 12 && x <= W - 12 && y <= H - 12);
  }
  const shown = app.maps[app.displayMap]?.world;
  const far = !!app.state?.pos && !app.dungeon && (app.displayMap === WORLD_MAP
    || (!!shown && !!size?.w && scale * size.w / Math.abs(shown.left - shown.right) < HIGH_AT_PX_PER_YARD));
  const show = off || far;
  if (show !== offScreen) { offScreen = show; $("btn-locate").hidden = !show; }
}

const ROUTE_MARGIN = 0.12;
const LOCATE_SVG = document.querySelector("#btn-locate svg")?.outerHTML || "";
const fitButton = (key, color, name, title = `Show all of ${name} on the map`) => `<button class="fit-btn" data-fit-route="${key}"
  style="color:${color}" title="${esc(title)}">${LOCATE_SVG}</button>`;
function routesShown() {
  const out = [], me = playerWorld();
  const g = shownGuide(), leg = g && legOf(g);
  if (leg && !leg.none && me) {
    const pts = [[me.n, me.w]], path = pathFor(leg), fin = finalStep(g);
    if (path?.points) pts.push(...path.points.map((p) => [p[0], p[1]]));
    if (leg.wx != null && (leg.instance == null || leg.instance === me.inst)) pts.push([leg.wx, leg.wy]);
    if (fin?.wx != null && (g.instance == null || g.instance === me.inst)) pts.push([fin.wx, fin.wy]);
    out.push({ key: "guide", color: tint(guideToken()), name: g.name || "the guide", inst: me.inst, pts });
  }
  for (const kind of ["loop", "epic"]) {
    const t = app.tracks?.[kind];
    if (t?.stops?.length) {
      const inst = t.inst ?? me?.inst, mine = me && inst === me.inst;
      const from = mine ? [[me.n, me.w], ...(t.path?.points || []).map((p) => [p[0], p[1]])] : [];
      out.push({ key: kind, color: trackStyle(kind, t).color, name: t.name || trackLabel(kind, t), inst,
                 pts: [...from, ...t.stops.map((p) => [p[0], p[1]])] });
    }
  }
  return out.filter((r) => r.inst != null && r.pts.length);
}
document.addEventListener("click", (e) => {
  const b = e.target.closest("button[data-fit-route]");
  const r = b && routesShown().find((x) => x.key === b.dataset.fitRoute);
  if (r) fitRoute(r);
});

function worldOnScreen(inst, n, w, size, scale) {
  const f = worldToFrac(app.displayMap, { inst, n, w }, app.maps, worldRound());
  return f ? toScreen(f[0], f[1], size, scale, app.displayMap) : null;
}
function screenIn(inst, size, scale) {
  return ([n, w, z]) => {
    const q = worldOnScreen(inst, n, w, size, scale);
    if (q && z != null) q.z = z;
    return q;
  };
}
function youOnScreen(size, scale) {
  const m = app.disp && app.maps[app.dispMap];
  if (!m?.world) return null;
  const p = toWorld(m.world, app.disp.x, app.disp.y);
  return screenIn(m.instance, size, scale)([p.n, p.w]);
}

function inMapSpace(size, scale, paint) {
  const v = app.view;
  ctx.save();
  ctx.translate(W / 2, H / 2);
  ctx.rotate(v.rot);
  ctx.scale(scale, scale);
  ctx.translate(-v.cx * size.w, -v.cy * size.h);
  try { paint(); } finally { ctx.restore(); }
}

function clearView(cards = true) {
  const c = canvas.getBoundingClientRect(), shown = (el) => el && !el.hidden && el.getBoundingClientRect().height > 0;
  const status = $("status"), stack = document.querySelector(".sidestack"), bar = document.querySelector("header.bar");
  const keys = document.querySelector(".mapkeys");
  const tall = (el) => shown(el) && el.getBoundingClientRect().height > H / 2;
  const wide = (el) => shown(el) && el.getBoundingClientRect().width > W / 2;
  let l = 0, r = W, t = 0, b = H;
  if (tall(status)) l = Math.max(l, status.getBoundingClientRect().right - c.left);
  for (const side of cards ? [stack, $("drawer")] : [$("drawer")]) {
    if (tall(side)) r = Math.min(r, side.getBoundingClientRect().left - c.left);
  }
  for (const top of [bar, ...document.querySelectorAll(".alert, .top-banner")]) if (wide(top)) t = Math.max(t, top.getBoundingClientRect().bottom - c.top);
  if (wide(keys)) b = Math.min(b, keys.getBoundingClientRect().top - c.top);
  return r - l > W / 4 && b - t > H / 4 ? { l, r, t, b } : { l: 0, r: W, t: 0, b: H };
}

function placeClearMiddle() {
  const cv = clearView(false), root = document.documentElement.style;
  scanScroll.resize(W, H, dpr, cv);
  root.setProperty("--clear-x", `${Math.round((cv.l + cv.r) / 2)}px`);
  root.setProperty("--clear-y", `${Math.round((cv.t + cv.b) / 2)}px`);
  app.clearShown = clearView();
  redraw();
}
const clearWatch = new ResizeObserver(placeClearMiddle);
for (const el of [canvas, $("status"), $("drawer"), document.querySelector(".sidestack"), document.querySelector("header.bar"),
                  document.querySelector(".mapkeys"), $("alert")]) if (el) clearWatch.observe(el);
new ResizeObserver(() => document.body.style.setProperty("--alert-h", `${$("alert").offsetHeight}px`)).observe($("alert"));

function centreInClear([fx, fy], size, cv = clearView()) {
  const v = app.view, ox = (cv.l + cv.r) / 2 - W / 2, oy = (cv.t + cv.b) / 2 - H / 2;
  [v.cx, v.cy] = [fx, fy];
  if (!(ox || oy) || !Number.isFinite(ox + oy)) return;
  const sc = scaleFor(size), c = Math.cos(-v.rot), n = Math.sin(-v.rot), ux = ox * c - oy * n, uy = ox * n + oy * c;
  const cx = fx - ux / (size.w * sc), cy = fy - uy / (size.h * sc);
  if (Number.isFinite(cx + cy)) [v.cx, v.cy] = [cx, cy];
}
function fitRoute(r) {
  const s = app.state, v = app.view;
  if (!s || !r.pts.length) return;
  const cv = clearView(), vw = cv.r - cv.l, vh = cv.b - cv.t;
  const box = (fs) => [Math.min(...fs.map((f) => f[0])), Math.min(...fs.map((f) => f[1])), Math.max(...fs.map((f) => f[0])), Math.max(...fs.map((f) => f[1]))];
  const zoomFor = (b, size) => {
    const bw = Math.max(b[2] - b[0], 1e-4) * size.w, bh = Math.max(b[3] - b[1], 1e-4) * size.h, d = v.rot ? Math.hypot(bw, bh) : 0;
    return Math.min(vw * (1 - 2 * ROUTE_MARGIN) / (d || bw), vh * (1 - 2 * ROUTE_MARGIN) / (d || bh)) / Math.min(W / size.w, H / size.h);
  };
  const centre = (b, size) => centreInClear([(b[0] + b[2]) / 2, (b[1] + b[3]) / 2], size, cv);
  const clamp = (z) => Math.min(MAX_ZOOM, Math.max(MIN_ZOOM, z));
  const on = (mapId) => r.pts.map(([n, w]) => worldToFrac(mapId, { inst: r.inst, n, w })).filter(Boolean);
  const within = (b) => b && b[0] >= -0.02 && b[1] >= -0.02 && b[2] <= 1.02 && b[3] <= 1.02;
  setFollow(false);
  const out = !!r.outOnly, wide = !!(v.continent || v.world), had = v.zoom;
  const no = (z) => clamp(out ? Math.min(had, z) : z);
  const shown = out ? viewMap() : null, sb = shown != null ? box(on(shown)) : null;
  const ns = r.pts.map((p) => p[0]), ws = r.pts.map((p) => p[1]);
  const holder = zoneHolding({ inst: r.inst, n: (Math.min(...ns) + Math.max(...ns)) / 2, w: (Math.min(...ws) + Math.max(...ws)) / 2 });
  const zone = shownMap(holder), hb = holder != null ? box(on(holder)) : null;
  const zb = zone != null ? box(on(zone)) : null, zoneZoom = zb ? zoomFor(zb, imgSize(mapImage(zone))) : 0;
  const cont = continentMap(r.inst);
  if (within(sb)) {
    const size = imgSize(mapImage(shown));
    v.zoom = no(zoomFor(sb, size));
    centre(sb, size);
  } else if (within(hb) && (zoneZoom >= MIN_ZOOM || !cont) && !(out && wide)) {
    leaveContinent(no(zoneZoom), zone);
    centre(zb, imgSize(mapImage(zone)));
  } else if (cont) {
    enterContinent("route", cont);
    const b = box(on(cont)), size = imgSize(mapImage(cont)), fit = zoomFor(b, size);
    v.zoom = out && wide ? no(fit) : clamp(fit);
    centre(b, size);
  } else return;
  viewMoved();
}

function showMouseCoords(e) {
  const box = $("mouse-coords"), s = app.state, size = app.curSize;
  let text = "";
  if (s && size && !drag?.moved && !app.dungeon && app.displayMap != null) {
    const r = canvas.getBoundingClientRect();
    const m = toMap(e.clientX - r.left, e.clientY - r.top, size, scaleFor(size));
    const spot = fracToWorld(app.displayMap, m.x, m.y, app.maps, worldRound());
    const viewed = $("view-zone").hidden ? null : zoneInView();
    const f = spot && worldToFrac(viewed || s.map, spot);
    if (f && f[0] >= 0 && f[0] <= 1 && f[1] >= 0 && f[1] <= 1) text = coords(f[0], f[1]);
  }
  if (box.textContent !== text) box.textContent = text;
  box.hidden = !text;
}
canvas.addEventListener("pointermove", showMouseCoords);
canvas.addEventListener("pointerleave", () => { $("mouse-coords").hidden = true; });

function setHeadingUp(on) {
  app.view.headingUp = on;
  $("btn-heading").setAttribute("aria-pressed", String(on));
  $("orient-label").textContent = on ? "Heading up" : "North up";
  try { localStorage.setItem("cc.headingUp", on ? "1" : "0"); } catch (e) {   }
}

function zoneFillZoom(zone = app.state?.map) {
  const cont = continentOf(zone), z = widestPerYard(zone), c = cont != null ? widestPerYard(cont) : 0;
  return z > 0 && c > 0 ? z / c : 4;
}

function enterContinent(reason, cont, near = false) {
  const s = app.state, v = app.view, zone = v.zone || s?.map;
  cont = cont ?? continentOf(zone);
  if (!s || !cont) return false;
  if (!v.continent && !v.world) v.zoneZoom = v.zoom;
  v.continent = reason;
  v.contMap = cont === continentOf(s.map) ? null : cont;
  v.world = false;
  v.zone = null;
  v.zoom = MIN_ZOOM;
  app.band.pull = 0;
  const on = near && mapOn(zone, cont);
  if (on) [v.cx, v.cy] = [(on[0] + on[2]) / 2, (on[1] + on[3]) / 2];
  v.drawnHeld = !!on;
  return true;
}

function enterWorld() {
  const v = app.view;
  if (!app.maps[WORLD_MAP]) return false;
  const left = app.maps[viewMap()]?.instance;
  if (!v.continent && !v.world) v.zoneZoom = v.zoom;
  v.world = true;
  v.zone = null;
  v.zoom = MIN_ZOOM;
  app.band.pull = 0;
  const r = app.mapKinds === "detailed" && regionOf(left, app.maps);
  if (r) {
    const size = imgSize(mapImage(WORLD_MAP)), s = scaleFor(size), box = regionsBox();
    const hx = W / 2 / (size.w * s), hy = H / 2 / (size.h * s);
    const fit = (mid, lo, hi, half) => (hi - lo <= 2 * half ? Math.min(lo + half, Math.max(hi - half, mid)) : mid);
    v.cx = fit((r.ui[0] + r.ui[2]) / 2, box[0], box[2], hx);
    v.cy = fit((r.ui[1] + r.ui[3]) / 2, box[1], box[3], hy);
  }
  return true;
}

function unplacedZones() {
  const onWorld = new Set((app.maps[WORLD_MAP]?.regions || []).map((r) => r.instance));
  return Object.entries(app.maps).filter(([id, m]) => m.type === 3 && m.world && !m.tilesOnly && m.parent
    && continentOf(+id) == null && !onWorld.has(m.instance)).map(([id, m]) => ({ id: +id, name: m.name }));
}
function updateToZones() {
  const v = app.view, widest = v.world && app.displayMap === WORLD_MAP && v.zoom <= MIN_ZOOM + 1e-6;
  const shown = app.dungeon || !widest ? [] : unplacedZones().filter((z) => z.id !== app.displayMap);
  const html = shown.map((z) => `<button class="key small" data-to-zone="${z.id}" style="--icon:url(/icon/inv_misc_map02.jpg)"
    title="Open ${esc(z.name)}'s map. No zoomed-out map shows ${esc(z.name)}${z.id === app.state?.map ? ". You're there now" : ""}">To ${esc(z.name)}</button>`).join("");
  setHtml($("to-zones"), html);
  $("to-zones").hidden = !html;
  if (html) keepBelowBanners($("to-zones"));
}
function keepBelowBanners(el) {
  const stage = el.offsetParent?.getBoundingClientRect?.();
  if (!stage) return;
  let low = 0;
  for (const b of document.querySelectorAll(".alert, .top-banner")) {
    const r = b.getBoundingClientRect();
    if (!b.hidden && r.height > 0 && r.top < stage.top + 120) low = Math.max(low, r.bottom - stage.top);
  }
  el.style.top = low ? `${Math.round(low + 8)}px` : "";
}
$("to-zones").addEventListener("click", (e) => {
  const b = e.target.closest("button[data-to-zone]");
  if (b) showZone(+b.dataset.toZone);
});
function showZone(id) {
  if (!app.state || !app.maps[id]) return;
  const mine = app.state.map === id;
  if (!mine) setFollow(false);
  leaveContinent(mine ? undefined : MIN_ZOOM, id);
  [app.view.cx, app.view.cy] = mine && app.disp ? [app.disp.x, app.disp.y] : [0.5, 0.5];
  viewMoved();
}
function showSpot(id, zone, f) {
  setFollow(false);
  leaveContinent(MIN_ZOOM, zone);
  app.view.zoom = closeZoom(id, zone) ?? app.view.zoom;
  centreInClear(f, imgSize(mapImage(zone)), clearView());
  viewMoved();
}

function zoneOpening(spot) {
  const v = app.view;
  if (!v.continent || v.world) return null;
  const zone = shownMap(spot ? zoneHolding(spot) : ownMap());
  return zone != null && app.maps[zone]?.type === 3 && v.zoom >= zoneFillZoom(zone) * (1 - 1e-9) ? zone : null;
}
function passInto() {
  const v = app.view, from = viewMap();
  if (v.continent !== "zoom" || v.world || v.backTo != null || from == null || !(W > 0 && H > 0)) return false;
  const spot = fracToWorld(from, v.cx, v.cy, app.maps, worldRound(from));
  const zone = zoneOpening(spot);
  if (zone == null) return false;
  leaveContinent(zoomKeepingScale(from, v.zoom, zone, spot ? spot.inst : undefined), zone);
  const f = spot && worldToFrac(zone, spot);
  if (f) [v.cx, v.cy] = f;
  return true;
}
function passAcross() {
  const v = app.view, from = viewMap();
  if (app.mapKinds !== "paper" || v.follow || v.continent || v.world || app.dungeon || v.backTo != null) return false;
  if (app.maps[from]?.type !== 3 || !(W > 0 && H > 0)) return false;
  const mid = fracToWorld(from, v.cx, v.cy), to = mid && zoneNear(mid, from);
  if (to == null || to === from) return false;
  leaveContinent(zoomKeepingScale(from, v.zoom, to, mid.inst), to);
  [v.cx, v.cy] = worldToFrac(to, mid);
  return true;
}
const ZONE_NEAR = 0.25;
function zoneNear(p, held) {
  const cont = continentOf(held), size = cont != null && imgSize(mapImage(cont));
  if (!size) return held;
  const far = (z) => {
    const g = zoneGlow(z.id), b = app.maps[z.id].world;
    const mid = g?.cx != null ? fracToWorld(cont, z.x0 + g.cx * z.w, z.y0 + g.cy * z.h) : { n: (b.top + b.bottom) / 2, w: (b.left + b.right) / 2 };
    return Math.hypot(p.n - mid.n, p.w - mid.w) / (ZONE_NEAR * Math.min(Math.abs(b.left - b.right), Math.abs(b.top - b.bottom)));
  };
  const zones = continentZones(cont, size), own = zones.find((z) => z.id === held);
  if (own && far(own) < 1) return held;
  let best = held, least = 1;
  for (const z of zones) {
    const d = z.id === held ? Infinity : far(z);
    if (d < least) { best = z.id; least = d; }
  }
  return best;
}
function zoneDrawnUnder(spot) {
  const v = app.view, from = viewMap(), size = app.curSize;
  if (app.mapKinds !== "both" || !spot || !size || v.continent || v.world || app.dungeon || app.detail.current !== "high") return null;
  const at = app.maps[from]?.type === 3 ? zoneNamed(spot, false) : null, to = at != null ? shownMap(at) : null;
  if (to == null || to === from || app.maps[to]?.type !== 3 || app.maps[to].instance !== spot.inst) return null;
  const px = yardPx(from, size, scaleFor(size)), low = (zoom) => detailBy("high", px, zoom) === "low";
  return low(v.zoom) || low(zoomKeepingScale(from, v.zoom, to, spot.inst)) ? to : null;
}

function leaveContinent(zoom, zone) {
  const v = app.view;
  v.continent = null;
  v.contMap = null;
  v.world = false;
  v.zone = zone && zone !== app.state?.map ? zone : null;
  v.zoom = zoom ?? v.zoneZoom ?? MIN_ZOOM;
}

function worldFillZoom(to, inst = app.maps[to]?.instance) {
  const w = widestPerYard(WORLD_MAP, inst), m = to != null ? widestPerYard(to, inst) : 0;
  return w > 0 && m > 0 ? m / w : 3;
}

let wasTaxi = false;
function followTaxi() {
  const onTaxi = !!app.state?.flags?.taxi;
  let moved = false;
  if (onTaxi && !wasTaxi && !app.view.continent) moved = enterContinent("taxi");
  else if (!onTaxi && app.view.continent === "taxi") { leaveContinent(); moved = true; }
  wasTaxi = onTaxi;
  if (moved) redraw();
}
on("update", followTaxi);

function followCity() {
  const p = !app.dungeon && playerWorld(), z = p ? zoneNamed(p) : null, here = z != null && cityZone(z) != null ? z : null;
  const was = cityIn;
  if (here === was) return;
  if (was != null) leaveCity();
  if (here != null && app.view.continent !== "taxi") {
    cityIn = here;
    cityFrom = zoomToFit(app.maps[here].world, TILES_FROM_ZOOM);
  }
  if (cityIn !== was) redraw();
}
function leaveCity() {
  const v = app.view;
  if (cityFrom != null && v.follow && !v.continent && !v.world) v.zoom = cityFrom;
  cityIn = cityFrom = null;
}
on("update", followCity);

function overscroll(factor, zoom = MIN_ZOOM * factor) {
  if (app.dungeon) return;
  if (app.mapKinds === "detailed") app.band.pull = BAND_POP;
  app.band.pull += 1 - factor;
  app.band.last = performance.now();
  if (app.band.pull < BAND_POP) return;
  const v = app.view, left = viewMap(), inst = app.maps[left]?.instance;
  const out = (!v.continent && enterContinent("zoom", undefined, true)) || enterWorld();
  if (!out) return;
  v.zoom = zoomKeepingScale(left, zoom, viewMap(), inst);
  if (!v.follow) return;
  if (v.world || !v.drawnHeld) layoutView();
  setFollow(false);
}

function zoomBy(factor, sx = null, sy = null) {
  if (sx === null) {
    const cv = clearView();
    [sx, sy] = [(cv.l + cv.r) / 2, (cv.t + cv.b) / 2];
  }
  const v = app.view, from = viewMap(), size = app.curSize || DEFAULT_IMG;
  const at = toMap(sx, sy, size, scaleFor(size));
  const spot = !v.follow && from != null ? fracToWorld(from, at.x, at.y, app.maps, worldRound(from)) : null;
  zoomView(factor, sx, sy, spot);
  if (spot) keepUnder(spot, sx, sy);
  holdPan();
  clearTimeout(zoomRest);
  zoomRest = setTimeout(viewMoved, ZOOM_REST_MS);
}
const ZOOM_REST_MS = 250;
let zoomRest = 0;

function panHeld(map) {
  return panBox(map) != null;
}
function panBox(map) {
  if (app.maps[map]?.type === 2) return worldRound(map) ? mapOn(WORLD_MAP, map) : [0, 0, 1, 1];
  if (map === WORLD_MAP && app.mapKinds === "detailed" && !app.dungeon) return regionsBox();
  return null;
}
function passOver() {
  const v = app.view, from = viewMap(), s = app.state;
  if (!v.continent || v.world || v.follow || !s || !worldRound(from)) return false;
  const spot = fracToWorld(from, v.cx, v.cy, app.maps, true), to = spot && continentMap(spot.inst);
  const at = to != null && to !== from && mapOn(to, from, app.maps, true);
  if (!at) return false;
  const was = imgSize(mapImage(from)), now = imgSize(mapImage(to)), k = (at[2] - at[0]) * was.w / now.w;
  const fit = (size) => Math.min(W / size.w, H / size.h) * bandScale();
  v.zoom = Math.min(MAX_ZOOM, v.zoom * k * fit(was) / fit(now));
  [v.cx, v.cy] = worldToFrac(to, spot);
  v.contMap = to === continentOf(s.map) ? null : to;
  return true;
}
function holdPan() {
  const v = app.view, box = panBox(viewMap());
  if (!box) return;
  v.cx = Math.min(box[2], Math.max(box[0], v.cx));
  v.cy = Math.min(box[3], Math.max(box[1], v.cy));
}

function keepUnder(p, sx, sy) {
  const v = app.view, map = viewMap(), f = worldToFrac(map, p, app.maps, worldRound(map));
  if (!f) return;
  const size = imgSize(mapImage(map)), m = toMap(sx, sy, size, scaleFor(size));
  v.cx += f[0] - m.x;
  v.cy += f[1] - m.y;
}

function zoomView(factor, sx, sy, spot) {
  const v = app.view;
  if (factor > 1) v.drawnHeld = false;
  if (!v.world && factor < 1 && v.zoom * factor < MIN_ZOOM) {
    const out = v.zoom * factor;
    v.zoom = MIN_ZOOM;
    return overscroll(factor, out);
  }
  const size = app.curSize || DEFAULT_IMG;
  const before = toMap(sx, sy, size, scaleFor(size));
  v.zoom = Math.min(MAX_ZOOM, Math.max(Math.min(MIN_ZOOM, v.zoom), v.zoom * factor));
  const inst = spot ? spot.inst : app.maps[app.state?.map]?.instance;
  const reaches = (at) => v.zoom >= at * (1 - 1e-9);
  const cont = v.world && factor > 1 ? (spot ? continentMap(inst) : continentOf(app.state?.map)) : null;
  const to = v.world && factor > 1 ? cont ?? (spot ? zoneHolding(spot) : app.state?.map) : null;
  if (to != null && reaches(worldFillZoom(to, inst))) {
    v.world = false;
    if (cont == null) return leaveContinent(zoomKeepingScale(WORLD_MAP, v.zoom, to, inst), spot && to);
    v.continent = v.continent || "zoom";
    v.contMap = cont === continentOf(app.state?.map) ? null : cont;
    v.zoom = zoomKeepingScale(WORLD_MAP, v.zoom, cont, inst);
    return;
  }
  const zone = factor > 1 ? zoneOpening(spot) : null;
  if (zone != null) return leaveContinent(zoomKeepingScale(viewMap(), v.zoom, zone), zone);
  const under = factor < 1 ? zoneDrawnUnder(spot) : null;
  if (under != null) return leaveContinent(zoomKeepingScale(viewMap(), v.zoom, under, spot.inst), under);
  if (!v.follow) {
    const after = toMap(sx, sy, size, scaleFor(size));
    v.cx += before.x - after.x;
    v.cy += before.y - after.y;
  }
}

let drag = null;
function startDrag(e) {
  drag = { x: e.clientX, y: e.clientY, moved: false };
  app.justDragged = false;
  canvas.setPointerCapture(e.pointerId);
  canvas.classList.add("dragging");
  mapLight.grab(true);
}
canvas.addEventListener("pointerdown", startDrag);
canvas.addEventListener("pointermove", (e) => {
  if (!drag) return;
  const dx = e.clientX - drag.x, dy = e.clientY - drag.y;
  if (!drag.moved && Math.hypot(dx, dy) < 4) return;
  drag.moved = true;
  drag.x = e.clientX; drag.y = e.clientY;
  setFollow(false);
  const size = app.curSize || DEFAULT_IMG;
  const sc = scaleFor(size), c = Math.cos(app.view.rot), n = Math.sin(app.view.rot);
  app.view.cx -= (dx * c + dy * n) / (size.w * sc);
  app.view.cy -= (-dx * n + dy * c) / (size.h * sc);
  holdPan();
  updateViewZone();
  redraw();
});
function endDrag() {
  if (drag?.moved) viewMoved();
  app.justDragged = !!drag?.moved;
  drag = null;
  canvas.classList.remove("dragging");
  mapLight.grab(false);
}
function viewMoved() {
  layoutView();
  refreshPois();
  refreshLayers();
  updateViewZone();
  keepView();
  requestUpdate();
}
canvas.addEventListener("pointerup", endDrag);
canvas.addEventListener("pointercancel", endDrag);
canvas.addEventListener("dblclick", () => setFollow(true));
function wheelZoom(e) {
  e.preventDefault();
  const r = canvas.getBoundingClientRect();
  zoomBy(Math.exp(-e.deltaY * 0.0015), e.clientX - r.left, e.clientY - r.top);
}
canvas.addEventListener("wheel", wheelZoom, { passive: false });

$("btn-follow").addEventListener("click", () => setFollow(!followingYou()));
const FOLLOW_TWICE = 350;
let followPressed = -Infinity;
function followAndLocate() {
  setFollow(true);
  centreOnMe();
}
$("btn-follow").addEventListener("dblclick", followAndLocate);
const STICKY_AFTER = 15000;
const STICKY_TICK = 1000;
const STICKY_YPX = 1.013;
function stickyZoom(map, home, pxPerYard) {
  const zoom = zoomShowing(home, Math.max(pxPerYard, 1 / STICKY_YPX));
  return zoom == null ? null : Math.min(MAX_ZOOM, Math.max(MIN_ZOOM, zoom));
}
const sticky = $("follow-sticky");
sticky.checked = keptOr("cc.sticky", false) === true;
sticky.addEventListener("change", () => { keepIn("cc.sticky", sticky.checked); mapTouched(); });
let movedFor = 0, stickyFrom = null;
function mapTouched() { movedFor = 0; }
for (const ev of ["pointerdown", "wheel"]) canvas.addEventListener(ev, mapTouched, { passive: true });
function stickyCheck() {
  const at = app.disp ? { x: app.disp.x, y: app.disp.y } : null;
  const moving = !!(at && stickyFrom && (at.x !== stickyFrom.x || at.y !== stickyFrom.y));
  stickyFrom = at;
  if (!sticky.checked || app.view.follow || lastSeenOnly() || app.dungeon) { movedFor = 0; return; }
  if (moving) movedFor += STICKY_TICK;
  if (movedFor < STICKY_AFTER) return;
  centreOnMe(stickyZoom);
  setFollow(true);
  mapTouched();
}
setInterval(stickyCheck, STICKY_TICK);
function followKey(now = performance.now()) {
  const twice = now - followPressed < FOLLOW_TWICE;
  followPressed = twice ? -Infinity : now;
  if (twice) followAndLocate();
  else setFollow(!followingYou());
}
const NOTES_KEPT = 30;
const notesKept = keptOr("cc.notesHidden", []).filter((t) => typeof t === "string").slice(-NOTES_KEPT);
notesKept.forEach((t) => { app.noteHidden[t] = true; });
function hideNote() {
  const text = $("mapnote").textContent;
  app.noteHidden[text] = true;
  $("mapnote").hidden = true;
  if (!notesKept.includes(text)) notesKept.push(text);
  keepIn("cc.notesHidden", notesKept.slice(-NOTES_KEPT));
}
$("mapnote").addEventListener("click", hideNote);
$("btn-heading").addEventListener("click", () => setHeadingUp(!app.view.headingUp));
$("btn-zoomin").addEventListener("click", () => zoomBy(1.4));
$("btn-zoomout").addEventListener("click", () => zoomBy(1 / 1.4));
document.querySelectorAll("[data-drawer]").forEach((b) => b.addEventListener("click", () => openDrawer(b.dataset.drawer)));
$("drawer").addEventListener("click", (e) => {
  if (e.target.closest?.("[data-bar-close]")) openDrawer(app.drawer);
  const answer = e.target.closest?.("[data-index-update]");
  if (answer) answerUpdate(answer.dataset.indexUpdate);
});

function userActed(e) {
  emit("acted", e);
  if (e.type === "keydown" && e.key !== "Escape" && e.target?.closest?.("input, textarea, select, [contenteditable]")) return;
  requestUpdate();
}
for (const type of ["click", "dblclick", "change", "wheel", "pointerup", "keydown"]) addEventListener(type, userActed, { capture: true, passive: true });

hotkey(["a"], () => openDrawer("alts"));
hotkey(["y"], () => openDrawer("player"));
hotkey(["f"], () => followKey());
hotkey(["h"], () => setHeadingUp(!app.view.headingUp));
hotkey(["c"], () => { if (app.indoor) setIndoorZone(!app.indoorZone); else if (cityShown != null) toggleCity(cityShown); });
hotkey(["+", "="], () => zoomBy(1.4));
hotkey(["-", "_"], () => zoomBy(1 / 1.4));
closable(LAYER.drawer, () => !!app.drawer, () => openDrawer(app.drawer));


on("start", function startPage() {
  loadBox?.show({ line: word("page.launcher.loading-maps") });
  loadMapData();
  try { setHeadingUp(localStorage.getItem("cc.headingUp") === "1"); } catch (e) { setHeadingUp(false); }
  options.start();
  fetchUntil("/api/settings", (saved) => options.took(saved));
  followPack();
  const drawer = keptOr("cc.drawer", "");
  if (Object.hasOwn(DRAWERS, drawer)) openDrawer(drawer);
  setInterval(checkAlert, 500);
  watchFullScreen(window, document, $("fs-note"));
  resize();
  connect();
  requestUpdate();
  document.fonts?.ready?.then?.(redraw);
  document.fonts?.ready?.then?.(() => keyNames($("top-keys"), options.get("keynames") === "fixed"));
});
const startAll = () => emit("start");
if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", startAll);
else setTimeout(startAll);
