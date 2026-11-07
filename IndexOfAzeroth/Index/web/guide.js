// The Index of Azeroth. Copyright 2026 Index Case <indexofazeroth@pm.me>. PolyForm Strict 1.0.0, see LICENSE.md.
"use strict";

const GUIDE_CATS = {
  "restock:ammo": ["ammo"], "restock:petFood": ["food"], "restock:water": ["food"], "restock:food": ["food"],
  "restock:poisons": ["poisons"], "restock:mhPoison": ["poisons"], "restock:ohPoison": ["poisons"],
  "character:repair": ["repair"],
  "restock:camp": ["general"],
  ...Object.fromEntries(REAGENTS.map((r) => [`restock:${r.key}`, r.cats || ["reagents"]])),
};
const GUIDE_ITEMS = Object.fromEntries(REAGENTS.map((r) => [`restock:${r.key}`, r.buys || [r.item]]));

app.guide = null;
const GAME_SOURCES = { journal: "Picked in the in-game journal", typed: "From /ioa go in game", corpse: "Corpse run",
  pin: "Map pin in game" };

function pinnedRare(g) {
  if (!mobs?.data || mobs.map !== g.map) return null;
  let best = null, bestD = 0.025;
  for (const r of mobs.data.rares) {
    for (const [x, y] of [r.at, ...r.spots]) {
      const d = Math.hypot(x - g.x / 100, y - g.y / 100);
      if (d < bestD) { best = r; bestD = d; }
    }
  }
  return best;
}

function pagesOwnInGame(g) {
  const mine = app.guide, p = app.pendingGuides?.go;
  if (g.source !== "typed" || !mine || mine.none) return false;
  const sameLine = !!p && p.page === pageId() && p.check != null && app.gameChecks?.go === p.check;
  return sameLine || sameGuideName(g.name, mine.name);
}
function shownGuide() {
  const g = app.gameGuide, w = g && app.maps[g.map]?.world;
  if (g && w && !pagesOwnInGame(g)) {
    const rare = g.source === "pin" ? pinnedRare(g) : null;
    const toDungeon = g.source === "corpse" && g.name.startsWith("Back to ");
    const at = toWorld(w, g.x / 100, g.y / 100);
    return { fromGame: true, name: g.name || rare?.name || "Map pin",
      sub: toDungeon ? "Corpse run back to the entrance" : GAME_SOURCES[g.source] || "",
      cat: toDungeon ? "dungeon" : g.source === "corpse" ? "corpse" : g.source === "pin" ? "pin" : "gameguide",
      instance: app.maps[g.map].instance, zone: app.maps[g.map].name, wx: at.n, wy: at.w };
  }
  return app.guide;
}
function guideToken() {
  return GUIDE_LOOKS[guideLook()];
}
function guideLook() {
  const g = app.gameGuide, shown = shownGuide();
  const runs = !!g && !!shown && (!!shown.fromGame || pagesOwnInGame(g));
  return !runs ? "gold" : g.source === "corpse" ? "corpse" : g.look === "npc" && !crimsonHolds(g) ? "gold"
    : GUIDE_LOOKS[g.look] ? g.look : "gold";
}
function crimsonHolds(g) {
  return !!g.checks?.target && !(pagesOwnInGame(g) && goalMark(app.guide) === "@");
}
const LOOK_MARKS = { farm: { src: "/ui/gold.png", tip: "This is a gold farming loop. The mark is the game's gold coin, as on the loop's beacon in game" },
                     npc: { src: "/icon/ability_hunter_snipershot.jpg", tip: "This guide leads to an NPC the Target key holds. The mark is Hunter's Mark, as on the guide's beacon in game" },
                     xp: { words: "XP", tip: "This is an XP grind loop. The mark is XP in gold, as on the loop's beacon in game" } };
function lookMarkHtml(look) {
  const m = LOOK_MARKS[look];
  if (!m) return "";
  return m.words ? `<span class="look-mark" data-look-mark="${look}" title="${esc(m.tip)}">${m.words}</span>`
    : `<img class="look-mark" data-look-mark="${look}" src="${m.src}" alt="" title="${esc(m.tip)}">`;
}


function zoneAt(wx, wy, instance) {
  const id = zoneNamed({ n: wx, w: wy, inst: instance }), w = id != null && app.maps[id]?.world;
  if (!w) return null;
  const [x, y] = toFrac(w, wx, wy);
  return { id, x: x * 100, y: y * 100 };
}

const WAYS_KEPT = 400;
app.ways = new RecentMap(WAYS_KEPT);
const wayKey = (inst, a, b, mode = app.pathMode) => `${inst}|${Math.round(a[0])}|${Math.round(a[1])}|${Math.round(b[0])}|${Math.round(b[1])}|${mode}`
  + `|${app.state?.level || 1}`;
const given = (p) => { if (!p) throw new Error("none given"); return p; };
function askWay(inst, a, b, mode = app.pathMode, shown = false) {
  const key = wayKey(inst, a, b, mode);
  if (app.ways.has(key)) return;
  const q = new URLSearchParams({ inst, fn: a[0].toFixed(1), fw: a[1].toFixed(1), tn: b[0].toFixed(1), tw: b[1].toFixed(1), bg: 1 });
  if (a[2] != null) q.set("fz", a[2].toFixed(1));
  if (b[2] != null) q.set("tz", b[2].toFixed(1));
  modeParams(q, mode);
  const asked = askFor(`way ${key}`, () => getJson(`/api/path?${q}`, { key: null }).then(given));
  if (!asked) return;
  app.ways.set(key, null);
  const settled = asked.then((p) => { app.ways.set(key, p); }, () => { app.ways.delete(key); });
  if (shown) busy(settled, shown === true ? "guide" : shown);
}

const legPathKey = (leg, from, mode = app.pathMode) => wayKey(leg.map, from, leg.to, mode);
function fetchLegPaths(r = app.route, shown = true) {
  if (!r) return;
  const mode = r.mode ?? app.pathMode;
  r.legs.forEach((leg, k) => {
    const from = k > 0 && r.legs[k - 1].at;
    if (leg.kind === "walk" && from && continentMapOf(leg.map)) askWay(leg.map, from, leg.to, mode, shown);
  });
}

const LEG_NEAR = 40;
const wayShort = (way) => !!way?.partial && (way.gap ?? Infinity) > LEG_NEAR;
const NO_WAY_ON_FOOT = "(no route on foot found)";
function routeShortHtml(r) {
  return (r?.legs || []).map((leg, k) => {
    const from = k > 0 && r.legs[k - 1].at;
    const way = leg.kind === "walk" && from ? app.ways.get(legPathKey(leg, from, r.mode ?? app.pathMode)) : null;
    return wayShort(way) ? `<div class="guide-blocked">There's no route on foot to ${esc(leg.name)}. The route ends ${num(way.gap)} yd short</div>` : "";
  }).join("");
}

function stopPairs(g) {
  if (!g?.stops?.length) return [];
  const all = [[g.wx, g.wy], ...g.stops.map((s) => [s.wx, s.wy])];
  return all.slice(1).map((b, k) => [all[k], b]);
}
function stopRoute(g, a, b) {
  const r = app.ways.get(wayKey(g.instance, a, b, "route"));
  return r?.legs.length ? r : null;
}
function askStopRoute(g, a, b, name) {
  const key = wayKey(g.instance, a, b, "route");
  if (app.ways.has(key)) return;
  const q = new URLSearchParams({ si: g.instance, sn: a[0].toFixed(1), sw: a[1].toFixed(1), gi: g.instance, gn: b[0].toFixed(1),
    gw: b[1].toFixed(1), name, side: app.status?.strs?.faction || "" });
  const asked = weighRoute(q, [g.instance, ...a], () => askFor(`stop route ${key}`, () => getJson(`/api/route?${q}`, { key: null }).then(given)));
  if (!asked) return;
  app.ways.set(key, null);
  busy(asked.then((plan) => {
    app.ways.set(key, { legs: plan.legs || [], minutes: plan.minutes });
    fetchStopPaths();
  }, () => { app.ways.delete(key); }));
}
function fetchStopPaths() {
  const g = app.guide;
  stopPairs(g).forEach(([a, b], k) => {
    if (Math.hypot(a[0] - b[0], a[1] - b[1]) >= ROUTE_NEAR) {
      askStopRoute(g, a, b, g.stops[k].name || `Stop ${k + 2}`);
      const r = app.ways.get(wayKey(g.instance, a, b, "route"));
      if (!r) return;
      if (r.legs.length) {
        r.legs.forEach((leg, i) => {
          const from = i ? r.legs[i - 1].at : a;
          if (leg.kind === "walk" && from && continentMapOf(leg.map)) askWay(leg.map, from, leg.to, app.pathMode, true);
        });
        return;
      }
    }
    askWay(g.instance, a, b, app.pathMode, true);
  });
}
const stopRoutesLine = (g) => stopPairs(g).map(([a, b], k) => [k + 2, stopRoute(g, a, b)]).filter(([, r]) => r)
  .map(([n, r]) => `<div class="guide-line muted">Stop ${n}: ${routeWords(r.legs)}</div>`).join("");
function stopsCutOff(g) {
  return cutOffStopsHtml(stopPairs(g).map(([a, b], k) => [k + 2, app.ways.get(wayKey(g.instance, a, b))]).filter(([, sp]) => sp?.partial));
}
function cutOffStopsHtml(cut) {
  if (!cut.length) return "";
  const gap = cut.length === 1 && cut[0][1].gap != null ? `. The route ends ${num(cut[0][1].gap)} yd from the stop`
    : `. The route ends short of ${cut.length > 1 ? "those stops" : "the stop"}`;
  return `<div class="guide-blocked">You can't reach ${cut.length > 1 ? "stops" : "stop"} ${andList(cut.map(([n]) => String(n)))} on foot${gap}</div>`;
}
function nextStop(g) {
  const [next, ...rest] = g.stops;
  app.guide = { ...g, wx: next.wx, wy: next.wy, wz: undefined, stopName: next.name, stops: rest };
  pathAsked = null;
  renderGuide();
}
function arrival(g, leg, d, rise = null, held = false) {
  if (!g || g.fromGame || leg?.leg || !atSpot(d, rise, held)) return null;
  return g.stops?.length ? "stop" : "end";
}
function guideRise(g, leg, d) {
  const path = !g?.fromGame && !leg?.leg && pathFor(leg), me = playerWorld();
  if (!path || !me) return null;
  return heightWords(walkable(path).points, leg.wz, [me.n, me.w], d, path.rising ??= {});
}
const RISE_ARROW = { "Above you": "M5 1.5L9 8.5H1z", "Below you": "M5 8.5L9 1.5H1z" };
const riseHtml = (rise) => (rise ? ` <span class="guide-rise"><svg viewBox="0 0 10 10" width="9" height="9" aria-hidden="true"><path d="${
  RISE_ARROW[rise]}" fill="currentColor"/></svg> ${rise}</span>` : "");
let arriving = null;
function guideArrived() {
  const g = app.guide, s = app.state;
  if (!g || g.none || g !== shownGuide() || arriving === g) return;
  const at = guideOnMap(), yd = mapYards(s?.map);
  if (!at || !s?.pos || !yd) return;
  const leg = legOf(g), d = Math.hypot((at[0] - s.pos.x) * yd.w, (at[1] - s.pos.y) * yd.h);
  const kind = arrival(g, leg, d, guideRise(g, leg, d), endHeld(pathFor(leg)));
  if (!kind) return;
  arriving = g;
  setTimeout(() => {
    if (app.guide !== g) return;
    if (kind === "stop") nextStop(g);
    else endGuide(`Arrived at ${g.name}`);
    requestUpdate();
  }, kind === "stop" ? 300 : 2500);
}
function updateGuide() {
  updatePath();
  guideArrived();
}
on("update", updateGuide);


app.path = null;
let pathAsked = null, pathAskedAt = 0;

const BUSY_AFTER = 350;
const busyOf = {};
const busyState = (kind) => (busyOf[kind] ??= { count: 0, timer: 0, shown: false, idle: [] });
function busy(promise, kind = "guide") {
  const b = busyState(kind);
  b.count++;
  if (!b.timer && !b.shown) b.timer = setTimeout(() => { b.timer = 0; showBusy(kind); }, BUSY_AFTER);
  return promise.finally(() => {
    b.count--;
    if (!b.count) { clearTimeout(b.timer); b.timer = 0; }
    showBusy(kind);
    if (!b.count) b.idle.splice(0).forEach((fn) => fn());
  });
}
const busyFor = (kind) => !!busyOf[kind]?.count;
const calculating = (kind) => !!busyOf[kind]?.shown;
function whenIdle(fn, kind = "guide") { if (busyFor(kind)) busyState(kind).idle.push(fn); else fn(); }
function showBusy(kind) {
  const b = busyState(kind), on = b.count > 0 && !b.timer;
  if (on === b.shown) return;
  b.shown = on;
  if (kind !== "guide") return renderTracks();
  $("guide").classList.toggle("busy", on);
  window.seeker?.run(on);
  renderGuide();
}

function playerWorld(flying = false) {
  const s = app.state, m = s && app.maps[s.map], w = m?.world;
  if (!s?.pos || !w || (s.flags?.taxi && !flying)) return null;
  return { inst: m.instance, ...toWorld(w, s.pos.x, s.pos.y) };
}
function heightHere() {
  const me = playerWorld();
  if (!me) return null;
  for (const path of [app.path, app.tracks?.epic?.path, app.tracks?.loop?.path]) {
    if (!path?.points?.length) continue;
    const way = walkable(path);
    const h = heightAlong(way.points, me.n, me.w, path.heightHere ??= {}) ?? remainingPath(way)[0]?.[2];
    if (h != null) return h;
  }
  return null;
}

app.pathMode = (() => {
  try {
    const m = localStorage.getItem("cc.pathMode") || "any";
    return ["safe", "fight"].includes(m) ? m : "any";
  } catch (e) { return "any"; }
})();
function modeParams(q, mode = app.pathMode) {
  if (mode === "ghost") { q.set("ghost", "1"); return; }
  q.set("level", app.state?.level || 1); q.set("faction", app.status?.strs?.faction || "");
  const cut = mode.indexOf("want:"), way = cut < 0 ? mode : mode.slice(0, Math.max(0, cut - 1));
  if (cut >= 0) q.set("want", mode.slice(cut + 5).replace(/\./g, ","));
  if (way.startsWith("gather:")) {
    const [, layer, types, dd] = way.split(":");
    q.set("mode", "gather"); q.set("layer", layer); q.set("types", types);
    if (dd === "dd") q.set("daredevil", "1");
  } else if (way && way !== "any") q.set("mode", way);
}
const LEG_BACK = `<svg viewBox="0 0 10 10" width="9" height="9" aria-hidden="true"><path d="M7.5 1L2 5l5.5 4z" fill="currentColor"/></svg>`;
const LEG_ON = `<svg viewBox="0 0 10 10" width="9" height="9" aria-hidden="true"><path d="M2.5 1L8 5 2.5 9z" fill="currentColor"/></svg>`;
const legPicked = {};
const legId = (x) => x.id ?? x.name;
const LEG_WORDS = { noun: "leg", first: "the current leg" };
function routeLegSpans(r, first) {
  const out = [];
  (r?.legs || []).forEach((leg, k) => {
    const prev = r.legs[k - 1];
    if (leg.kind === "walk") {
      const from = k === 0 ? first.from : prev?.at;
      const lp = k === 0 ? first.path : from && app.ways.get(legPathKey(leg, from, r.mode ?? app.pathMode));
      const pts = [from, ...(lp?.points || []), leg.to].filter(Boolean).map((p) => [p[0], p[1]]);
      if (pts.length > 1) out.push({ inst: leg.map, pts, name: `walk to ${leg.name}` });
    } else if (leg.kind === "ride" && leg.vehicle === "flight" && leg.via?.length > 1) {
      out.push({ inst: leg.map, pts: leg.via.map((p) => [p[0], p[1]]), name: leg.name });
    }
  });
  return out;
}
function guideLegSpans(g) {
  const me = playerWorld(), r = app.route;
  if (!g || g.none || !me || !r?.legs.length || r.key !== `${pathKey(g)}|${me.inst}`) return [];
  const walking = r.legs[0].kind === "walk" && r.legs[0].map === me.inst;
  return routeLegSpans(r, { from: walking ? [me.n, me.w] : null, path: walking ? pathFor(legOf(g)) : null });
}
const legIndex = (spans, kind = "guide", routeKey = app.route?.key) => {
  const p = legPicked[kind];
  return Math.max(0, p && p.key === routeKey ? spans.findIndex((x) => legId(x) === p.id) : 0);
};
function legKeys(spans, kind = "guide", color = tint(guideToken()), routeKey = app.route?.key, words = LEG_WORDS) {
  const i = legIndex(spans, kind, routeKey), n = spans.length;
  const step = (d, svg, word) => { const to = spans[i + d];
    return `<button class="leg-btn" data-leg="${d}" data-legs-of="${kind}"${to ? ` title="${word} ${words.noun} ${i + d + 1} of ${n}: ${esc(to.name)}"` : " disabled"}>${svg}</button>`; };
  return `<div class="guide-legs" style="--leg:${color}">${step(-1, LEG_BACK, "Back to")}${fitButton(`${kind}-leg`, color, spans[0].name,
    `Show ${words.first} (1 of ${n}) on the map: ${spans[0].name}`)}${step(1, LEG_ON, "On to")}</div>`;
}
function stepLegs(e, kind, spans, routeKey) {
  const step = e.target.closest(`button[data-leg][data-legs-of="${kind}"]`);
  if (!step && !e.target.closest(`button[data-fit-route="${kind}-leg"]`)) return false;
  pickLeg(kind, spans, routeKey, step ? legIndex(spans, kind, routeKey) + +step.dataset.leg : 0);
  return true;
}
function pickLeg(kind, spans, routeKey, i) {
  if (!spans.length) return;
  const leg = spans[Math.max(0, Math.min(spans.length - 1, i))];
  legPicked[kind] = { key: routeKey, id: legId(leg) };
  fitRoute(leg);
}

const SWORDS = `<svg viewBox="0 0 16 16" width="11" height="11" aria-hidden="true"><path d="M2.5 2.5L10.6 10.6M9 12.2L12.2 9M11.3 11.3L13.6 13.6M13.5 2.5L5.4 10.6M3.8 9L7 12.2M4.7 11.3L2.4 13.6"/></svg>`;
const HEART = `<svg viewBox="0 0 16 16" width="11" height="11" aria-hidden="true"><path d="M8 14s-5.6-3.4-5.6-7.3C2.4 4.6 3.9 3 5.8 3c1.1 0 1.8.6 2.2 1.3C8.4 3.6 9.1 3 10.2 3c1.9 0 3.4 1.6 3.4 3.7C13.6 10.6 8 14 8 14z"/></svg>`;
const SKULL = `<svg class="skull" viewBox="0 0 16 16" width="12" height="12" aria-hidden="true"><path fill="currentColor" fill-rule="evenodd" d="M8 1C4.4 1 2 3.5 2 6.7c0 1.9.9 3.4 2.3 4.3V14h2v-1.6h1.1V14h1.2v-1.6h1.1V14h2v-3c1.4-.9 2.3-2.4 2.3-4.3C14 3.5 11.6 1 8 1zM5.6 5.4a1.6 1.6 0 1 0 0 3.2 1.6 1.6 0 0 0 0-3.2zm4.8 0a1.6 1.6 0 1 0 0 3.2 1.6 1.6 0 0 0 0-3.2zM8 8.8l-.9 1.5h1.8z"/></svg>`;

const pathKey = (g) => g && !g.none ? `${g.instance}|${Math.round(g.wx)}|${Math.round(g.wy)}|${app.state?.flags?.ghost ? "ghost" : "alive"}|${app.pathMode}`
  + `|${app.state?.level || 1}` : null;
const wayMode = () => (app.state?.flags?.ghost ? "ghost" : app.pathMode);
function pathFor(g) { return g && app.path && app.path.key === pathKey(g) ? app.path : null; }


app.route = null;
let routeAsked = null;
const ROUTE_NEAR = 800;
const ROUTE_REPLAN = 250;
const ROUTE_TOOK_OFF = 120;

const routeHere = (g, me) => (app.route?.key === `${pathKey(g)}|${me.inst}` ? app.route : null);
function legOf(g) {
  if (!g || g.none) return g;
  const me = playerWorld();
  if (g.instance == null || !me) return g;
  const here = g.instance === me.inst;
  if (here && Math.hypot(g.wx - me.n, g.wy - me.w) < ROUTE_NEAR) return g;
  const r = routeHere(g, me), leg = r?.legs[0];
  if (!leg || (app.state?.flags?.taxi && leg.kind === "walk")) return here ? g : null;
  if (leg.kind !== "walk" || leg.map !== me.inst) return null;
  return { ...g, name: leg.name, wx: leg.to[0], wy: leg.to[1], wz: leg.to[2], instance: me.inst, leg: true };
}
function followRoute(g) {
  const me = playerWorld(true);
  if (!g || g.none || g.instance == null || !me) return;
  const r = routeHere(g, me);
  if (r) advanceRoute(r, me);
  if (g.instance === me.inst && Math.hypot(g.wx - me.n, g.wy - me.w) < ROUTE_NEAR) return;
  const leg = r?.legs[0];
  if (app.state?.flags?.taxi && (!leg || leg.kind === "walk")) return;
  const riding = leg && leg.kind !== "walk";
  const stale = riding ? Date.now() - r.boarded > ((leg.minutes || 1) * 2 + 3) * 60000
    : r && Math.hypot(me.n - r.from[0], me.w - r.from[1]) > ROUTE_REPLAN;
  if (!r || stale) askRoute(g, me, `${pathKey(g)}|${me.inst}`);
}

function askRoute(g, me, key) {
  const ask = `${key}|${Math.round(me.n / 50)}|${Math.round(me.w / 50)}`;
  if (routeAsked === ask) return;
  const q = new URLSearchParams({ si: me.inst, sn: me.n.toFixed(1), sw: me.w.toFixed(1), gi: g.instance, gn: g.wx.toFixed(1),
    gw: g.wy.toFixed(1), name: g.name, side: app.status?.strs?.faction || "" });
  const ghost = !!app.state?.flags?.ghost;
  if (ghost) q.set("ghost", "1");
  else if (app.status?.nums?.hearth === 0 && app.status?.strs?.bind) q.set("hearth", app.status.strs.bind);
  const asked = weighRoute(q, [me.inst, me.n, me.w], () => getJson(`/api/route?${q}`, { key: `guide route ${key}` }));
  if (!asked) return;
  routeAsked = ask;
  busy(asked.then((plan) => {
    if (routeAsked !== ask) return;
    app.route = { key, from: [me.n, me.w], boarded: Date.now(), legs: goalHeight(plan?.legs || [], g.wz), noFlights: !!plan?.noFlights,
      minutes: plan?.minutes, against: plan?.against, ...(ghost ? { mode: "ghost" } : {}) };
    renderGuide();
    updatePath();
  }, () => { if (routeAsked === ask) routeAsked = null; }));
}
const routeNote = (g) => askNote(`guide route ${pathKey(g)}|${playerWorld(true)?.inst}`, { what: "the route there",
  again: () => { updatePath(); renderGuide(); } });

function advanceRoute(r, me) {
  const [leg, next] = r.legs;
  if (!leg) return;
  const near = leg.to && Math.hypot(leg.to[0] - me.n, leg.to[1] - me.w), { board: boardAt, landed } = DirectorRules.table.guide;
  const board = next?.vehicle === "flight" ? !!app.state?.flags?.taxi && near < ROUTE_TOOK_OFF : near <= boardAt;
  if (leg.kind === "walk" && next && next.kind !== "walk" && leg.map === me.inst && board) {
    r.legs = r.legs.slice(1);
    r.boarded = Date.now();
    r.boardAt = leg.to;
  } else if (leg.kind !== "walk" && leg.map === me.inst && (Math.hypot(leg.at[0] - me.n, leg.at[1] - me.w) <= landed
             || (leg.vehicle === "flight" && !app.state?.flags?.taxi))) {
    r.legs = r.legs.slice(1);
    r.from = [me.n, me.w];
    r.boardAt = null;
  }
}

const routeWords = (legs) => legs.map((l) => l.kind === "ride" ? `${esc(l.name)} (${Math.max(1, Math.round(l.minutes))} min)`
  : l.kind !== "walk" ? esc(l.name) : `walk to ${esc(l.name)}`).join(" → ");
function rideNow(leg) {
  const me = playerWorld(true), at = leg?.at;
  const left = me && at && leg.map === me.inst ? `, ${num(Math.hypot(at[0] - me.n, at[1] - me.w))} yd left` : "";
  return `${leg?.name || "on the way"} now${left}`;
}
function routeLine() {
  const legs = app.route?.key?.startsWith(`${pathKey(shownGuide())}|`) && app.route.legs;
  return legs?.length ? routeWords(legs) : "";
}
const routeAgainst = (r) => r?.against
  ? `About ${r.minutes} min ${r.legs.length ? "by this route" : "on foot"}${r.against.hearth ? ", keeping your Hearthstone" : ""}. ${esc(r.against.what)}: ${r.against.minutes} min` : "";
function tripLine(g) {
  const r = app.route;
  if (!r?.key?.startsWith(`${pathKey(g)}|`) || !r.legs?.length || !(r.minutes > 0)) return "";
  return `<div class="guide-line trip-time">The whole trip takes about ${Math.max(1, Math.round(r.minutes))} min</div>`;
}

const CUT_OFF_SHARE = 0.8;
function reachOf(path) {
  if (!path?.partial) return null;
  const me = playerWorld(), goal = path.points[path.points.length - 1];
  const straight = me ? Math.hypot(goal[0] - me.n, goal[1] - me.w) : 0;
  const gap = path.gap ?? straight;
  return { gap, cutOff: !straight || gap > straight * CUT_OFF_SHARE, city: path.enemyGoal };
}
const walkable = (path) => path.partial ? { ...path, points: path.points.slice(0, -1) } : path;
const TALK_REACH = 5;
const wayThere = (path) => !path?.partial && !(path?.near > TALK_REACH);


const capitalWords = (c) => c?.side ? `the ${c.side}'s capital` : "the other side's capital";
function reachWords(path) {
  if (path?.enemyGoal) return `The route on foot stops outside ${path.enemyGoal.name} because the spot is inside ${capitalWords(path.enemyGoal)}`;
  const reach = reachOf(path);
  if (reach) return reach.cutOff ? "There's no route on foot from here. The spot looks cut off, like a mountain top, an island or a place behind cliffs"
    : `The route on foot gets within ${num(reach.gap)} yd and no further`;
  return path && !wayThere(path) ? `The route couldn't be planned that far. It stops ${num(path.near)} yd short of the spot` : "";
}
const reachToast = (reach) => reach.city ? `The spot is inside ${reach.city.name}, ${capitalWords(reach.city)}, so ${
  reach.cutOff ? "the page copied nothing" : "Copy takes you to the edge of the city"}`
  : reach.cutOff ? "There's no route on foot from here, so the page copied nothing"
  : `The route gets within ${num(reach.gap)} yd and no further. Copy takes you that far`;
function wayMobsWords(path) {
  if (path?.fight != null) {
    return (path.fight ? `, ${path.fight} mob${path.fight > 1 ? "s" : ""} to fight` : ", nothing to fight on the way")
      + (path.mobs ? `, ${path.mobs} too strong` : "");
  }
  return path?.mobs != null ? (path.mobs ? `, past ${path.mobs} mob${path.mobs > 1 ? "s" : ""}` : ", clear of mobs") : "";
}
function wayNotesHtml(path) {
  const blocked = reachWords(path), over = path?.overZones || [], cities = path?.enemyCities || [];
  return `${blocked ? `<div class="guide-blocked">${esc(blocked)}</div>` : ""}${over.length ? `<div class="guide-blocked">The route goes through ${
    esc(andList(over.map((z) => z.levels ? `${z.name} (${zoneRangeText(z.levels)})` : z.name)))}, far above your level, and there's no route round on foot</div>` : ""}${
    cities.length ? `<div class="guide-blocked">The route goes through ${esc(andList(cities.map((c) => c.name)))}, ${
      cities.length > 1 ? "the other side's capitals" : esc(capitalWords(cities[0]))}, and there's no route round on foot</div>` : ""}`;
}
const routeNotesHtml = (r, calc = false) => !r ? "" : `${calc ? "" : routeShortHtml(r)}${r.against
  ? `<div class="guide-line muted">${routeAgainst(r)}</div>` : ""}${r.noFlights
  ? `<div class="guide-line muted">Guides fly once you've opened a flight master's map on this character</div>` : ""}`;

function heldIndoors(path) {
  if (youIndoors() !== false || !path?.indoor?.length) return new Set();
  return new Set(path.indoor.map((i) => path.points[i]));
}
const endHeld = (path) => !!path?.points?.length && heldIndoors(path).has(path.points[path.points.length - 1]);

function remainingPath(path) {
  const me = playerWorld(), pts = path.points;
  if (!me || pts.length < 2) return pts;
  const held = heldIndoors(path);
  let best = 0, bestD = Infinity, prev = path.from;
  for (let i = 0; i < pts.length; i++) {
    if (held.has(pts[i])) { prev = pts[i]; continue; }
    const d = segDist([me.n, me.w], prev, pts[i]);
    if (d < bestD) { bestD = d; best = i; }
    prev = pts[i];
  }
  return pts.slice(best);
}

function segDist(p, a, b) {
  const dx = b[0] - a[0], dy = b[1] - a[1], len = dx * dx + dy * dy;
  const t = len ? Math.max(0, Math.min(1, ((p[0] - a[0]) * dx + (p[1] - a[1]) * dy) / len)) : 0;
  return Math.hypot(p[0] - a[0] - t * dx, p[1] - a[1] - t * dy);
}

function offPath(path) {
  const me = playerWorld();
  if (!me) return 0;
  let prev = path.from, best = Infinity;
  const held = heldIndoors(path);
  for (const p of path.points) { if (!held.has(p)) best = Math.min(best, segDist([me.n, me.w], prev, p)); prev = p; }
  return best;
}

const WAY_FRESH_MOVED = 80, WAY_FRESH_LONGER = 1.15;
function roundabout(path, goal) {
  const me = playerWorld();
  if (!me || !path?.from || !path.points?.length) return false;
  if (Math.hypot(me.n - path.from[0], me.w - path.from[1]) < WAY_FRESH_MOVED) return false;
  const straight = Math.hypot(goal[0] - me.n, goal[1] - me.w);
  if (straight < 40) return false;
  return leftOf(walkable(path)) > straight * WAY_FRESH_LONGER;
}
function leftOf(path) {
  const me = playerWorld();
  let left = 0, prev = me ? [me.n, me.w] : null;
  for (const p of remainingPath(path)) { if (prev) left += Math.hypot(p[0] - prev[0], p[1] - prev[1]); prev = p; }
  return left;
}

const askedAsNow = (path) => (path?.askedIndoors ?? null) === youIndoors();

const WAY_SHORT_AGAIN = 20000;
const shortStale = (path) => !!path?.partial && Date.now() - (path.at ?? 0) > WAY_SHORT_AGAIN;

function updatePath() {
  followRoute(shownGuide());
  fetchLegPaths();
  fetchStopPaths();
  const g = legOf(shownGuide()), me = playerWorld(), key = pathKey(g);
  if (!key || !me || g.instance != null && g.instance !== me.inst) { if (!key) app.path = null; return; }
  const have = pathFor(g);
  takeWay(have);
  const near = have?.easy && offPath(easyOf(have)) < offPath(have) ? easyOf(have) : have;
  if (have && offPath(near) < 30 && !roundabout(near, [g.wx, g.wy]) && !shortStale(have) && askedAsNow(have)) return;
  if (pathAsked === key && Date.now() - pathAskedAt < 4000) return;
  const q = new URLSearchParams({ inst: me.inst, fn: me.n.toFixed(1), fw: me.w.toFixed(1), tn: g.wx.toFixed(1), tw: g.wy.toFixed(1) });
  if (g.wz != null) q.set("tz", g.wz.toFixed(1));
  const indoors = youIndoors();
  if (indoors != null) q.set("indoors", indoors ? "1" : "0");
  modeParams(q, wayMode());
  q.set("easy", "1");
  const asked = getJson(`/api/path?${q}`, { key: `guide path ${key}` });
  if (!asked) return;
  pathAsked = key; pathAskedAt = Date.now();
  busy(asked.then((p) => {
    if (p && pathKey(legOf(shownGuide())) === key) app.path = wayPicked({ ...p, key, from: [me.n, me.w], at: Date.now(), askedIndoors: indoors });
  }, () => {}));
}

const easyOf = (path) => (path?.easy ? { ...path.easy, from: path.from } : null);
function takeWay(path) {
  const easy = easyOf(path);
  if (!easy || !playerWorld()) return;
  const kept = DirectorRules.ways(offPath(path), offPath(easy), leftOf(path), leftOf(easy), [path.length, easy.length]);
  if (kept === "easy") {
    app.path = { key: path.key, from: path.from, at: path.at, askedIndoors: path.askedIndoors, points: easy.points,
                 length: easy.length, covered: easy.covered, indoor: easy.indoor, partial: false };
  } else if (kept === "quick") {
    const kept = { ...path };
    delete kept.easy;
    app.path = kept;
  }
}

function easyWayKey(path, calc) {
  const off = calc ? " disabled" : "";
  if (path?.easy) return `<div class="guide-cmd"><button data-easy-way${off}>Take the easy way</button></div>`;
  if (path?.quick) return `<div class="guide-cmd"><button data-quick-way${off}>Take the quick way</button></div>`;
  return "";
}
let easyPicked = null;
function easyTaken(path) {
  const quick = { ...path };
  delete quick.easy;
  return { key: path.key, from: path.from, at: path.at, askedIndoors: path.askedIndoors, points: path.easy.points,
           length: path.easy.length, covered: path.easy.covered, indoor: path.easy.indoor, partial: false, quick };
}
const wayPicked = (path) => (path?.easy && easyPicked && easyPicked === path.key ? easyTaken(path) : path);
function pickWay(easy) {
  const g = shownGuide(), path = pathFor(legOf(g));
  if (!g || !path) return;
  if (easy && path.easy) {
    app.path = easyTaken(path);
    easyPicked = path.key;
  } else if (!easy && path.quick) {
    app.path = { ...path.quick, easy: { points: path.points, length: path.length, covered: path.covered, indoor: path.indoor } };
    easyPicked = null;
  } else return;
  renderGuide();
  const cmd = goCommand(g);
  if (cmd) copyText(cmd, "Copied", !g.fromGame);
}

function setPathMode(mode) {
  app.pathMode = app.pathMode === mode ? "any" : mode;
  try { localStorage.setItem("cc.pathMode", app.pathMode); } catch (e) {   }
  pathAsked = null;
  renderGuide();
  const g = app.guide;
  updatePath();
  whenIdle(() => { if (g && app.guide === g && !g.fromGame) { const cmd = goCommand(g); if (cmd) copyText(cmd, "Copied", true, GUIDE_READY); } renderGuide(); });
}

const GUIDE_READY = { kind: "Navigation Guide", from: "guide", reason: "guide" };
function guideTo(g, { lead, then, copy: toClipboard = true } = {}) {
  g.instance ??= app.maps[app.state?.realMap ?? app.state?.map]?.instance;
  const z = zoneAt(g.wx, g.wy, g.instance);
  if (!g.zone && z) g.zone = app.maps[z.id]?.name || "";
  if (g.wz == null && goalMark(g) === "@") {
    const learnt = learntHeight(g);
    if (learnt != null) { g.wz = learnt; g.wzLearnt = true; }
  }
  app.guide = g;
  delete app.endedHere?.go;
  renderGuide();
  const copy = () => {
    if (app.guide !== g) return then?.();
    const reach = reachOf(pathFor(legOf(g)));
    if (reach) {
      showToast(reachToast(reach));
      return then?.();
    }
    const cmd = goCommand(g);
    if (cmd && toClipboard) copyText(cmd, lead, true, GUIDE_READY);
    else if (cmd) { leaveForLogin(cmd); showToast(lead); showPlanReady({ ...GUIDE_READY, text: cmd, copied: null }); }
    then?.();
  };
  pathAsked = null;
  updatePath();
  whenIdle(copy);
}

function guideCats(todoId) {
  if (app.status?.classId === 8 && (todoId === "restock:water" || todoId === "restock:food")) return null;
  return GUIDE_CATS[todoId] || (todoId?.startsWith("auction:") ? ["auction"] : null);
}

function startGuide(todoId, opts = {}) {
  const cats = guideCats(todoId), more = {};
  if (!cats) return opts.then?.();
  if (GUIDE_ITEMS[todoId]) more.items = GUIDE_ITEMS[todoId].join("|");
  const line = app.status && generatedLists(app.status).flatMap(([, items]) => items).find((i) => i.id === todoId);
  if (line?.to) return guideTo({ ...line.to, todoId }, opts);
  if (line?.goods?.length) more.goods = line.goods.join(",");
  const kind = todoId === "restock:ammo" && { 2: "arrow", 3: "bullet" }[app.status?.nums?.ammoKind];
  if (kind) more.ammo = kind;
  guideNearest({ cats, more, todoId, again: (o) => startGuide(todoId, o) }, opts);
}

function guideToKind(cat, opts = {}, detail = kindDetail(cat, false)) {
  const more = detail ? { detail } : {};
  guideNearest({ cats: [cat], more, what: poiWhat(cat), again: (o) => guideToKind(cat, o, detail) }, opts);
}

function guideNearest(ask, opts = {}) {
  const s = app.state, todoId = ask.todoId ?? null;
  if (!s?.pos) return opts.then?.();
  const q = new URLSearchParams({ map: s.map, x: s.pos.x, y: s.pos.y, faction: app.status?.strs?.faction || "", cats: ask.cats.join(","), ...ask.more });
  getJson(`/api/nearest?${q}`, { key: null }).then((best) => {
    const dungeonKey = best && (best.cat === "dungeon" || best.cat === "raid") ? dungeonForEntrance(best.name)?.key : undefined;
    if (best) guideTo({ ...best, todoId, ...(dungeonKey ? { dungeonKey } : {}), again: ask.again }, opts);
    else { app.guide = { todoId, none: true, what: ask.what }; renderGuide(); opts.then?.(); }
  }, (e) => { askFailed("The page couldn't start the guide", e); opts.then?.(); });
}

function stopGuide() {
  if (app.guide) leaveForLogin(null);
  app.guide = null;
  app.path = null;
  app.route = null;
  routeAsked = null;
  renderGuide();
}

app.endedHere = {};
function endGuide(words, { stillInGame = false } = {}) {
  const g = app.guide, p = app.pendingGuides?.go;
  if (g && !g.none && stillInGame) app.endedHere.go = { name: g.name, check: p && p.page === pageId() ? p.check : null };
  stopGuide();
  if (words) showToast(words);
}
function stopHere() {
  const g = app.guide;
  endGuide(g && !g.none ? `${g.name} stopped. To stop the guide in game, type /ioa go off` : null, { stillInGame: true });
}


const REPLANS = {};
app.replanning = {};
const REPLAN_LINES = [
  "A dwarf scout is redrawing the route from where you stand",
  "A gnome is planning your route again on a fresh sheet of paper",
  "The gryphon master is looking over the routes once more",
  "A goblin surveyor is measuring the route from here and charging you again",
  "A night elf tracker is reading fresh tracks from where you stand",
  "A Tauren pathfinder is asking the land for a new road",
  "An orc scout is planning a new road from here. He prefers roads that go through things",
  "A quartermaster is plotting your route again and sighing about it",
  "Brann Bronzebeard is planning a new route from here. He has already lost the first one",
  "The Explorers' League is checking its charts again. One of them found a dig site on the way"];
const replannedWords = (name) => `The Index planned ${name} afresh from where you are`;
function replanKey(kind) {
  const r = REPLANS[kind];
  if (!r) return "";
  const working = !!app.replanning[kind];
  return `<button class="replan-btn" data-replan="${kind}"${working ? " disabled" : ""} title="${esc(r.title())}">${working ? "Re-planning" : "Re-plan"}</button>`;
}
const runeLine = (words) => `<div class="replan-working" role="status"><span>${esc(words)}</span><i></i><i></i><i></i></div>`;
function replanWorking(kind) {
  const line = app.replanning[kind];
  return line ? runeLine(line) : "";
}
const CALCULATING = `<div class="calculating seen-only" role="status"><span>Calculating</span><i></i><i></i><i></i></div>`;
const workingHtml = (kind) => replanWorking(kind) || (calculating(kind) ? CALCULATING : "");
function replanGuide(kind, opts = {}) {
  const r = REPLANS[kind];
  if (!r || app.replanning[kind]) return;
  const q = r.question?.();
  if (q) {
    ask(q).then((answer) => { if (answer !== null) replanNow(kind, { ...opts, answer }); });
    return;
  }
  replanNow(kind, opts);
}
function replanNow(kind, opts) {
  const r = REPLANS[kind];
  if (app.replanning[kind]) return;
  app.replanning[kind] = REPLAN_LINES[Math.floor(Math.random() * REPLAN_LINES.length)];
  showReplans();
  let over = false;
  r.start(() => {
    if (over) return;
    over = true;
    delete app.replanning[kind];
    showReplans();
  }, opts);
}
function showReplans() {
  renderGuide();
  renderTracks();
}
document.querySelector(".sidestack")?.addEventListener("click", (e) => {
  const b = e.target.closest("button[data-replan]");
  if (b && !b.disabled) replanGuide(b.dataset.replan);
});

REPLANS.guide = {
  title: () => shownGuide()?.fromGame ? "Works out the guide's route afresh from the character's spot and copies the line for the in-game arrow, as Copy path does"
    : "Plans the guide afresh from the character's spot, the same as stopping the guide and starting it again. The Index works out the route, the flights and the boats again. For a restock the Index also finds the nearest vendor. Then type /reload in game or paste the guide's line",
  start: replanGold,
};
function forgetGuideWays(g) {
  const forgetWalks = (r, from) => (r?.legs || []).forEach((leg, k) => {
    const at = k ? r.legs[k - 1].at : from;
    if (leg.kind === "walk" && at) app.ways.delete(legPathKey(leg, at, r.mode ?? app.pathMode));
  });
  forgetWalks(app.route, null);
  for (const [a, b] of stopPairs(g)) {
    forgetWalks(app.ways.get(wayKey(g.instance, a, b, "route")), a);
    app.ways.delete(wayKey(g.instance, a, b, "route"));
    app.ways.delete(wayKey(g.instance, a, b));
  }
  app.path = null; pathAsked = null;
  app.route = null; routeAsked = null;
}
function replanGold(done, { auto = false } = {}) {
  const g = shownGuide();
  if (!g || g.none) return done();
  forgetGuideWays(g);
  showToast(auto ? `${g.name} is complete. The Index is planning the route to the quest's turn-in` : `The Index is planning ${g.name} afresh from where you are`);
  const lead = auto ? `The guide for ${g.name} now leads to its turn-in, and the Index left the guide for your next /reload. You can also press Copy on the guide's panel and paste the line`
    : `${replannedWords(g.name)} and copied the line for the in-game arrow`;
  const opts = { lead, then: done, ...(auto ? { auto, copy: false } : {}) };
  if (!g.fromGame) return g.again ? g.again(opts) : guideTo({ ...g }, opts);
  updatePath();
  whenIdle(() => {
    const now = shownGuide(), cmd = now?.fromGame && now.name === g.name ? goCommand(now) : null;
    if (cmd) copyText(cmd, lead, false, GUIDE_READY);
    else if (now?.fromGame) showToast(`${replannedWords(g.name)}. There's nothing to copy for the in-game arrow from here`);
    done();
  });
}

function worldOnMap(n, wv) {
  const s = app.state, w = s && app.maps[s.map]?.world;
  return w ? toFrac(w, n, wv) : null;
}

function guideOnMap() {
  const g = legOf(shownGuide()), s = app.state, w = s && app.maps[s.map]?.world;
  if (!g || g.none || !w) return null;
  if (g.instance != null && app.maps[s.map].instance !== g.instance) return null;
  return toFrac(w, g.wx, g.wy);
}


function panelHead(label, help, keys, { track = false, keysClass = "", mark = "", glide = false } = {}) {
  const name = glide ? `<span class="glide"><span>${esc(label)}</span></span>` : esc(label);
  return `<div class="guide-head"><span class="with-help"><span class="next-label${track ? " track-label" : ""}">${name}</span>${mark}${helpButton(help)}</span>
    <span class="guide-btns${keysClass ? ` ${keysClass}` : ""}">${keys}</span></div>`;
}

function glideLabels(root) {
  for (const g of root?.querySelectorAll?.(".glide") || []) {
    const over = Math.max(0, Math.ceil(g.scrollWidth - g.clientWidth));
    g.style.setProperty("--slide", String(over));
    g.classList.toggle("slides", over > 0);
  }
}

function renderGuide() {
  const box = $("guide"), body = $("guide-body"), g = shownGuide(), s = app.state;
  let html = "";
  if (g && g.none) {
    html = `${panelHead("Guide", "guide", "<button data-stop>Close</button>")}
      <div class="guide-line">The data has no ${esc(g.what || "vendor for that")} on this continent.</div>`;
  } else if (g) {
    const leg = legOf(g), at = guideOnMap(), yd = mapYards(s?.map), path = pathFor(leg);
    let where = `${esc(g.zone)}`, dist = "", turn = "", rise = null;
    if (at && s?.pos && yd) {
      const dx = (at[0] - s.pos.x) * yd.w, dy = (at[1] - s.pos.y) * yd.h, d = Math.hypot(dx, dy);
      const me = playerWorld(), rest = path && me ? remainingPath(path) : null;
      let along = d, next = at;
      if (rest?.length) {
        along = 0;
        let prev = [me.n, me.w];
        for (const p of rest) { along += Math.hypot(p[0] - prev[0], p[1] - prev[1]); prev = p; }
        const bend = rest.find((p) => Math.hypot(p[0] - me.n, p[1] - me.w) > 10) || rest[rest.length - 1];
        next = worldOnMap(bend[0], bend[1]) || at;
      }
      dist = `${distanceWords(along)}${path ? (reachOf(path) ? "" : ", walking") : ""}${wayMobsWords(path)}`;
      rise = guideRise(g, leg, d);
      const held = endHeld(path);
      if (atSpot(d, rise, held)) turn = leg?.leg ? `At ${leg.name}` : "You're there";
      if (!arrival(g, leg, d, rise, held) && s.facing != null) {
        const tx = (next[0] - s.pos.x) * yd.w, ty = (next[1] - s.pos.y) * yd.h;
        turn = turnText(wrap(Math.atan2(-tx, -ty) - s.facing));
      }
    }
    const spans = guideLegSpans(g), legRow = spans.length > 1 ? legKeys(spans) : "";
    const fit = legRow ? "" : fitButton("guide", tint(guideToken()), g.name || "the guide"), cmd = goCommand(g);
    const copyPath = g.fromGame && path && path.points.length > 1 && cmd, replan = replanKey("guide");
    const ghost = !!s?.flags?.ghost, calc = calculating("guide");
    html = `${panelHead(g.fromGame ? "Guided in game" : "Guiding to", "guide", `${ghost ? "" : `<button data-safe class="safe-btn${app.pathMode === "safe" ? " on" : ""}" aria-pressed="${app.pathMode === "safe"}"
          title="${word("page.ways.safest.tip")}">${HEART} ${word("page.ways.safest")}</button>
        <button data-fight class="fight-btn${app.pathMode === "fight" ? " on" : ""}" aria-pressed="${app.pathMode === "fight"}"
          title="${word("page.ways.grinding.tip")}">${SWORDS} ${word("page.ways.grinding")}</button>`}
        ${g.fromGame ? "" : "<button data-stop>Stop</button>"}`, { mark: lookMarkHtml(guideLook()) })}
      <div class="guide-name"><img src="/icon/${g.icon || poiIcon(g.cat)}.jpg" alt=""> ${esc(g.name)}</div>
      <div class="guide-line">${esc(g.sub || "")}${g.sub && where ? ", " : ""}${where}</div>
      ${g.stops?.length ? `<div class="guide-line">Then ${g.stops.length} more stop${g.stops.length > 1 ? "s" : ""}</div>${stopRoutesLine(g)}` : ""}
      ${stopsCutOff(g)}
      ${workingHtml("guide")}
      ${calc ? "" : wayNotesHtml(path)}
      ${easyWayKey(path, calc)}
      ${tripLine(g)}
      <div class="guide-line">${leg?.leg ? `To ${esc(leg.name)}: ` : ""}<b>${dist}</b> <span class="next-turn">${turn}</span>${riseHtml(rise)}</div>
      ${routeLine() && leg !== g ? `<div class="guide-route">${routeLine()}</div>` : !leg ? `<div class="guide-line muted">${app.route && !app.route.legs.length ? "The Index has no route to that map from here"
        : app.route?.legs[0] && app.route.legs[0].kind !== "walk" ? esc(rideNow(app.route.legs[0])) : routeNote(g)}</div>` : ""}
      ${app.route?.key?.startsWith(`${pathKey(g)}|`) ? routeNotesHtml(app.route, calc) : ""}
      ${legRow}
      ${g.fromGame ? `<div class="guide-stop"><b>To stop:</b> click the x on the arrow in game, or type /ioa go off</div>
        ${copyPath ? `<div class="guide-cmd"><button data-copy-path${calc ? " disabled" : ""}>${calc ? "Calculating" : "Copy path"}</button><span class="muted"> gives the in-game arrow the bends</span>${fit}${replan}</div>` : ""}`
        : cmd ? `<div class="guide-cmd${calc ? " waiting" : ""}"><code>${esc(cmd)}</code><button data-copy${calc ? " disabled" : ""}>${calc ? "Wait" : "Copy"}</button>${fit}${replan}</div>` : ""}
      ${cmd && (!g.fromGame || copyPath) ? "" : `<div class="guide-cmd">${fit}${replan}</div>`}`;
  }
  box.hidden = !html;
  box.classList.toggle("ghostly", !!s?.flags?.ghost);
  box.classList.toggle("waits", ghostWaits() && !!g && !isCorpseRun(g));
  setHtml(body, html);
}

$("guide").addEventListener("click", (e) => {
  if (stepLegs(e, "guide", guideLegSpans(shownGuide()), app.route?.key)) return renderGuide();
  if (e.target.closest("button[data-stop]")) stopHere();
  else if (e.target.closest("button[data-safe]")) setPathMode("safe");
  else if (e.target.closest("button[data-fight]")) setPathMode("fight");
  else if (busyFor("guide")) return;
  else if (e.target.closest("button[data-easy-way]")) pickWay(true);
  else if (e.target.closest("button[data-quick-way]")) pickWay(false);
  else if (e.target.closest("button[data-copy]") && app.guide) copyText(goCommand(app.guide));
  else if (e.target.closest("button[data-copy-path]")) { const g = shownGuide(); if (g) copyText(goCommand(g), "Copied", false); }
});

const spotGuideSub = (p) => ("levels" in p ? [mobLevelText(p.levels), p.sub].filter(Boolean).join(", ") : p.sub);

const spotMap = (hit) => app.state && app.maps[hit?.map ?? app.state.map];
const spotPlace = (hit) => (hit.p.group ? hit.p.group[0] : hit.p);

canvas.addEventListener("click", (e) => {
  if (app.justDragged) return;
  const r = canvas.getBoundingClientRect(), mx = e.clientX - r.left, my = e.clientY - r.top;
  const hit = e.ctrlKey ? null : spotAt(mx, my, true), was = pickTravel(null);
  if (e.ctrlKey) return guideToPoint(mx, my);
  if (!hit && zoomIntoCapital(mx, my)) return;
  if (!hit && zoomIntoZone(mx, my)) return;
  if (!hit && openContinentAt(mx, my)) return;
  if (!hit || !spotMap(hit)?.world) return;
  if (zoomIntoGroup(hit)) return;
  const p = spotPlace(hit);
  if (p.cat === "boss") { jr.boss = p.bossIndex; return openJournal(p.dungeonKey, "bosses"); }
  if ((p.cat === "dungeon" || p.cat === "raid")) {
    const d = dungeonForEntrance(p.name);
    if (d) return openJournal(d.key);
  }
  if (p.cat in TRAVEL_KINDS) return was && sameTravelPick(was, hit) ? undefined : pickTravel(hit);
  guideToMapSpot(hit);
});

function guideToMapSpot(hit) {
  const m = spotMap(hit), w = m?.world, p = spotPlace(hit);
  if (!w) return;
  if (p.foe) return showToast(foeWords(p));
  const at = toWorld(w, p.gx ?? p.x, p.gy ?? p.y);
  guideTo({ todoId: null, name: p.name, sub: spotGuideSub(p), cat: p.cat, icon: p.icon, zone: "", wz: p.z ?? undefined, instance: m.instance,
            wx: at.n, wy: at.w });
}

function guideToPoint(mx, my) {
  if (app.dungeon) return;
  const size = app.curSize, mapId = app.displayMap ?? app.state?.map, m = app.maps[mapId], w = m?.world;
  if (!size || !w) return showToast("This map has no position to guide to");
  const f = toMap(mx, my, size, scaleFor(size)), at = toWorld(w, f.x, f.y), wx = at.n, wy = at.w;
  const z = zoneAt(wx, wy, m.instance);
  if (!z) return showToast("That spot isn't in a zone on the map");
  const name = spotName(app.maps[z.id].name, z.x, z.y);
  const g = app.guide;
  if (g?.spots && g.instance === m.instance) {
    app.guide = { ...g, stops: [...(g.stops || []), { wx, wy, name }] };
    showToast(`Stop ${app.guide.stops.length + 1} added. The Stop key clears all the stops`);
    renderGuide();
    const now = app.guide;
    updatePath();
    whenIdle(() => { if (app.guide === now) { const cmd = goCommand(now); if (cmd) copyText(cmd, "Copied", true, GUIDE_READY); } });
    return;
  }
  spotGuide({ name, zone: app.maps[z.id].name, inst: m.instance, wx, wy });
}
const spotName = (zone, x, y) => `${zone} ${x.toFixed(1)}, ${y.toFixed(1)}`;
function spotGuide(s) {
  guideTo({ todoId: null, name: s.name, sub: s.sub || "a spot you picked", cat: "gameguide", zone: s.zone, instance: s.inst, wx: s.wx, wy: s.wy,
            spots: true });
}

const heightsKept = { version: -1, list: [] };
const HEIGHT_REACH = 15;
function refreshHeights(snap) {
  const v = snap?.versions?.heights;
  if (v == null || v === heightsKept.version) return;
  getJson("/api/heights")?.then((d) => { heightsKept.list = d.heights || []; heightsKept.version = v; }, () => {});
}
function learntHeight(g) {
  let best = null, near = HEIGHT_REACH;
  for (const h of heightsKept.list) {
    const d = h.inst === g.instance && h.name === g.name ? Math.hypot(h.at[0] - g.wx, h.at[1] - g.wy) : Infinity;
    if (d <= near) { best = h.z; near = d; }
  }
  return best;
}

function goalHeight(legs, z) {
  const end = legs[legs.length - 1];
  if (z != null && end?.kind === "walk" && end.to && end.to[2] == null) end.to = [end.to[0], end.to[1], z];
  return legs;
}
