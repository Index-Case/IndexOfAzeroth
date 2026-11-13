// The Index of Azeroth. Copyright 2026 Index Case <indexofazeroth@pm.me>. PolyForm Strict 1.0.0, see LICENSE.md.
"use strict";

const TRACK_STYLE = {
  epic: { color: tint(EPIC_LOOK), verb: "e", label: "Quest epic", help: "epic" },
  craft: { color: tint(EPIC_LOOK), verb: "e", label: "Crafting epic", help: "craft" },
  loop: { color: tint("kill-crimson"), verb: "g", label: "Loop", help: "loop" },
};
const LOOP_ON = 25;
const LOOP_AHEAD = 30;
const LOOP_PATH_FROM = 60;
const EPIC_GLYPH = { pickup: "!", turnin: "?", objective: "✕", dungeon: "▼", errand: "◆" };
app.tracks = { epic: null, loop: null };
const LOOP_LABEL = { grind: "Grinding", farm: "Gold farming", gather: "Gathering", skin: "Skinning" };
const trackLabel = (kind, t) => kind === "loop" ? LOOP_LABEL[t?.what] || "Loop" : TRACK_STYLE[kind].label;
const loopKind = (t) => (LOOP_LABEL[t?.what] ? `${LOOP_LABEL[t.what].toLowerCase()} loop` : "loop");
const loopLook = (t) => t?.what === "gather" ? (LAYER_DOTS[t.layer] ? t.layer : "gather")
  : t?.what === "farm" ? "farm" : t?.what === "skin" ? "skin" : "xp";
const LOOP_VERB_KIND = { grind: "grind", xp: "grind", farm: "grind", gather: "gather", mining: "gather", herbalism: "gather",
                         fishing: "gather", treasure: "gather", skin: "skin" };
function shownLoopLook(t) {
  const own = loopLook(t), g = app.gameLoop, p = app.pendingGuides?.loop;
  if (!g?.look || g.kind !== LOOP_VERB_KIND[own]) return own;
  const mine = p && p.page === pageId() && p.check != null && app.gameChecks?.loop != null;
  const runs = mine ? app.gameChecks.loop === p.check : sameGuideName(g.name, t.name);
  return runs ? g.look : own;
}
const LOOP_VERB = { grind: "g", gather: "h", skin: "k" }, LOOP_STYLES = {};
function trackStyle(kind, t) {
  if (kind === "epic" && isCraft(t?.key)) return TRACK_STYLE.craft;
  if (kind !== "loop") return TRACK_STYLE[kind];
  const look = shownLoopLook(t), of = LOOP_VERB_KIND[look];
  return (LOOP_STYLES[look] ||= { color: tint(LOOP_LOOKS[look]), verb: LOOP_VERB[of], help: "loop", look,
                                  label: of === "gather" ? "Gathering" : of === "skin" ? "Skinning" : "Loop" });
}
const loopIcon = (t) => t.what === "gather"
  ? (layers.data?.dots?.[t.layer]?.types || []).find((x) => t.types?.includes(x.name))?.icon || LAYER_DOTS[t.layer]?.icon
  : t.what === "farm" ? "inv_misc_coin_01" : t.what === "skin" ? "inv_misc_pelt_wolf_01" : "inv_sword_04";


const trackStore = (kind) => charStore(kind, app.character);
function saveTrack(kind) {
  const t = app.tracks[kind];
  try {
    if (!t) localStorage.removeItem(trackStore(kind));
    else if (kind === "epic") localStorage.setItem(trackStore(kind), JSON.stringify({ key: t.key, anchor: t.anchor, way: t.way, close: !!t.close, name: t.name,
                                                                                         questLevels: t.questLevels }));
    else localStorage.setItem(trackStore(kind), JSON.stringify({ what: t.what, name: t.name, sub: t.sub, inst: t.inst, stops: t.stops, at: t.at, lap: t.lap,
                                                                layer: t.layer, types: t.types, glass: t.glass, zone: t.zone, daredevil: t.daredevil,
                                                                zones: t.zones, all: t.all, mobs: t.mobs, ids: t.ids, spots: t.spots }));
  } catch (e) {   }
}

const dismissedClose = (p) => !!p?.closed && app.dismissed?.key === p.key && app.dismissed.at === p.closed.at;
function dismissClosedEpic() {
  const p = closedEpic();
  if (!p?.closed.game) return;
  app.dismissed = { key: p.key, at: p.closed.at };
  keepIn(trackStore("epicDismissed"), app.dismissed);
  renderTracks();
  renderTodo();
}
function dismissedEpicNotices() {
  const p = app.tracks.epic ? null : keptEpic(app.plan?.key);
  if (!p || !dismissedClose(p)) return [];
  return [{ id: `epic:${p.key}`, icon: QUESTS_ICON, text: p.name || "Quest epic", why: word("page.epic.closed.why"), again: () => reopenEpic(p) }];
}
NOTICE_SOURCES.push(dismissedEpicNotices);

let tracksFor = null;
function loadTracks() {
  if (tracksFor === app.character) return;
  tracksFor = app.character;
  app.tracks = { epic: null, loop: null };
  app.dismissed = keptOr(trackStore("epicDismissed"), null);
  try {
    const e = JSON.parse(localStorage.getItem(trackStore("epic")) || "null");
    if (e?.key) { app.tracks.epic = newEpic(e.key, e.anchor, e.way ?? (e.safe ? "safe" : "any"), !!e.close, e.name, e.questLevels); refreshEpic(true); }
    const g = JSON.parse(localStorage.getItem(trackStore("loop")) || "null");
    if (g?.stops?.length) app.tracks.loop = { kind: "loop", ...g, loop: true };
  } catch (e) {   }
  renderTracks();
}

function leaveCharacter() {
  stopGuide();
  stopScout(true);
  stopProspecting(true);
  dropAsk();
}

function stopTrack(kind, quiet) {
  const t = app.tracks[kind];
  app.tracks[kind] = null;
  if (kind === "loop") glassStop();
  const pending = app.pendingGuides?.loop;
  if (kind === "loop" && t) leaveForLogin(null, "loop");
  const there = kind === "loop" && endGuideThere(t);
  if (kind === "loop" && t && !quiet) {
    app.endedHere.loop = { name: t.name || trackLabel(kind, t), verb: trackStyle(kind, t).verb,
                           check: pending && pending.page === pageId() ? pending.check : null };
  }
  const epic = kind === "epic" && !!t;
  if (epic) {
    app.stoppedHere = { key: t.key, version: loadedVersion(), at: Date.now() };
    postJson("/api/shared/stop", { key: t.key }).then(() => setTimeout(refreshShared, 500),
      (e) => askFailed("The epic is still open in the game's table", e));
  }
  saveTrack(kind);
  renderTracks();
  if (t && !quiet) showToast(epic ? `${t.name} closed. Its plan and your progress are kept, and Reopen picks it up again. To close the epic in game, close its card or the blue arrow, or do a /reload`
    : `${t.name || trackLabel(kind, t)} stopped${there ? " with the guide to it" : ""}. To stop the loop in game, type /ioa ${trackStyle(kind, t).verb} off`
      + (there ? " and /ioa go off" : ""));
  return there;
}


const GUIDED_NEAR = 30;
const guidedTo = (t) => {
  const g = app.guide;
  return !!g && !g.fromGame && g.instance === t.inst && !!t.stops?.some((p) => Math.hypot(p[0] - g.wx, p[1] - g.wy) < GUIDED_NEAR);
};
function guideToLoop(t) {
  const p = t?.stops?.[t.at] || t?.stops?.[0];
  if (!p) return;
  const words = loopKind(t);
  guideTo({ todoId: null, name: t.name, sub: words[0].toUpperCase() + words.slice(1), cat: "node", icon: loopIcon(t), instance: t.inst,
            wx: p[0], wy: p[1], wz: p[2] ?? undefined, forLoop: true });
  t.copyWhenReady = true;
}
function endGuideThere(t) {
  if (!t || !app.guide?.forLoop || !guidedTo(t)) return false;
  endGuide(null, { stillInGame: true });
  return true;
}

function startLoopTrack(what, name, sub, stops, inst, more = {}, replanned = false) {
  const old = app.tracks.loop;
  app.tracks.loop = { kind: "loop", what, name, sub, inst, stops, loop: true, at: 0, lap: 1, copyWhenReady: true, planReady: true, ...more };
  if (replanned) app.tracks.loop.copyLead = `${replannedWords(name)}, copied for the in-game ${arrowColor(app.tracks.loop)} arrow`;
  delete app.endedHere?.loop;
  const there = !!old && !replanned && endGuideThere(old);
  saveTrack("loop");
  renderTracks();
  if (old && !replanned) showToast(`${name} takes the place of ${old.name}, because only one loop runs at a time${there ? `. The guide to ${old.name} is over too` : ""}`);
}


const FIGHT_LOOPS = ["grind", "farm", "skin"];
const fights = (t) => FIGHT_LOOPS.includes(t?.what);
app.loopWay = (() => {
  try {
    const m = localStorage.getItem("cc.loopWay");
    return ["safe", "fight", "any"].includes(m) ? m : null;
  } catch (e) { return null; }
})();
function trackMode(t) {
  if (t.kind === "epic") return t.way === "safe" || t.way === "fight" ? t.way : "any";
  const pick = app.loopWay ?? (fights(t) ? "fight" : "any");
  return pick === "fight" && !fights(t) ? "any" : pick;
}
const withWant = (mode, ids) => (ids?.length ? `${mode === "any" ? "" : `${mode}+`}want:${ids.join(".")}` : mode);
const campWant = (t) => (t.kind === "epic" ? t.step?.mobs : fights(t) ? t.ids : null) || [];
const trackWayMode = (t) => withWant(trackMode(t), campWant(t));

const LOOP_HOP_STRAIGHT = 12;
const LOOP_NEAR = 20;
const walkedWay = (way) => way && (!way.partial || (way.gap ?? Infinity) <= LOOP_NEAR);
const loopMode = (t) => t.kind === "epic" ? withWant("any", t.step?.mobs)
  : fights(t) ? (t.ids?.length ? withWant("any", t.ids) : "fight")
  : t.what === "gather" && t.layer ? `gather:${t.layer}:${(t.types || []).join("|")}${t.daredevil ? ":dd" : ""}` : "any";
function fetchLoopWays(t) {
  const n = t.stops.length;
  for (let k = 0; k < n; k++) {
    const a = t.stops[k], b = t.stops[(k + 1) % n];
    if (Math.hypot(a[0] - b[0], a[1] - b[1]) >= LOOP_HOP_STRAIGHT) askWay(t.inst, a, b, loopMode(t), t.kind === "loop" && "loop");
  }
}
function loopCircuit(t, from = 0) {
  const n = t.stops.length, pts = [], stops = new Set();
  for (let k = 0; k < n; k++) {
    const a = t.stops[(from + k) % n], b = t.stops[(from + k + 1) % n], stop = [a[0], a[1]];
    pts.push(stop);
    stops.add(stop);
    const way = app.ways.get(wayKey(t.inst, a, b, loopMode(t)));
    if (walkedWay(way)) for (const p of way.points.slice(0, -1)) pts.push([p[0], p[1]]);
  }
  return { pts, stops };
}
function nearestOn(route, me) {
  let best = Infinity;
  for (let i = 0; i < route.length; i++) best = Math.min(best, segDist([me.n, me.w], route[Math.max(0, i - 1)], route[i]));
  return best;
}
function dropLoopBend(circuit) {
  const pts = circuit.pts, drop = leastBend(pts, { from: 0, to: pts.length - 1, ring: true, kept: (i) => circuit.stops.has(pts[i]) });
  if (drop < 0) return false;
  pts.splice(drop, 1);
  return true;
}


function loopHops(t) {
  const n = t.stops.length, hops = [];
  for (let k = 0; k < n; k++) {
    const a = t.stops[k], b = t.stops[(k + 1) % n], pts = [[a[0], a[1]]];
    const way = app.ways.get(wayKey(t.inst, a, b, loopMode(t)));
    if (walkedWay(way)) for (const p of way.points.slice(0, -1)) pts.push([p[0], p[1]]);
    pts.push([b[0], b[1]]);
    hops.push(pts);
  }
  return hops;
}
function loopNearest(t, me) {
  const hops = loopHops(t), k = hops.length;
  let best = null, round = 0;
  hops.forEach((pts, h) => {
    for (let i = 1; i < pts.length; i++) {
      const a = pts[i - 1], b = pts[i], dx = b[0] - a[0], dy = b[1] - a[1], len2 = dx * dx + dy * dy, len = Math.sqrt(len2);
      const u = len2 ? Math.max(0, Math.min(1, ((me.n - a[0]) * dx + (me.w - a[1]) * dy) / len2)) : 0;
      const n = a[0] + dx * u, w = a[1] + dy * u, d = Math.hypot(n - me.n, w - me.w);
      if (!best || d < best.d) best = { n, w, d, seg: (h + 1) % k, at: round + len * u, hop: h, i };
      round += len;
    }
  });
  return best && { ...best, round };
}

function loopAhead(t, p, ahead) {
  const hops = loopHops(t), bends = hops.reduce((sum, pts) => sum + pts.length, 0);
  let n = p.n, w = p.w, h = p.hop ?? 0, i = p.i ?? 1;
  for (let step = 0; step < bends * 2; step++) {
    const to = hops[h][i], d = Math.hypot(to[0] - n, to[1] - w);
    if (d >= ahead) return [n + (to[0] - n) * ahead / d, w + (to[1] - w) * ahead / d];
    ahead -= d; n = to[0]; w = to[1];
    if (++i >= hops[h].length) { h = (h + 1) % hops.length; i = 1; }
  }
  return [n, w];
}

function trackTarget(t) {
  const r = trackRoute(t), leg = r?.legs[0];
  if (leg && leg.kind !== "walk") return null;
  const me = playerWorld();
  if (leg && me && leg.map === me.inst && r.legs.length > 1) return { inst: leg.map, n: leg.to[0], w: leg.to[1], z: leg.to[2], leg };
  if (!r && routeAwaited(t, me)) return null;
  return trackGoal(t);
}
function routeAwaited(t, me) {
  if (!me || !t?.stops?.length || t.inst == null) return false;
  const dest = t.stops[0];
  if (t.inst === me.inst && Math.hypot(dest[0] - me.n, dest[1] - me.w) < ROUTE_NEAR) return false;
  return t.routePending || !t.route || t.route.key !== `${t.inst}|${Math.round(dest[0])}|${Math.round(dest[1])}|${me.inst}`;
}

function trackRoute(t) {
  const far = farTrack(t);
  if (far === null) return null;
  if (!far) return t.route?.legs.some((l) => l.kind !== "walk") ? t.route : null;
  const r = t.route?.key === far.key ? t.route : null;
  return r?.legs.some((l) => l.kind !== "walk") ? r : null;
}
function farTrack(t) {
  if (!(t?.kind === "epic" || t?.loop) || !t.stops?.length || t.inst == null) return null;
  const me = playerWorld();
  if (!me) return false;
  const dest = { inst: t.inst, n: t.stops[0][0], w: t.stops[0][1], z: t.stops[0][2] };
  if (dest.inst === me.inst && Math.hypot(dest.n - me.n, dest.w - me.w) < ROUTE_NEAR) return null;
  return { dest, me, key: `${dest.inst}|${Math.round(dest.n)}|${Math.round(dest.w)}|${me.inst}` };
}
function shownTrackRoute(t) {
  const far = farTrack(t);
  return trackRoute(t) || (far && t.route?.key === far.key ? t.route : null);
}
function trackLegSpans(t) {
  const w = writtenPlan(t);
  if (w) return planStepSpans(w.epic);
  const far = farTrack(t), r = trackRoute(t);
  if (!far || !r?.legs.length) return [];
  const me = far.me, walking = r.legs[0].kind === "walk" && r.legs[0].map === me.inst;
  const spans = routeLegSpans({ ...r, mode: r.mode ?? trackWayMode(t) },
    { from: walking ? [me.n, me.w] : null, path: walking ? t.path : null });
  const stops = t.stops.map((p) => [p[0], p[1]]), last = spans[spans.length - 1];
  if (last?.inst === t.inst) last.pts.push(...stops);
  else spans.push({ inst: t.inst, pts: stops, name: t.name || trackLabel(t.kind, t) });
  return spans;
}
function trackLegKey(t) {
  const w = writtenPlan(t);
  return w ? writtenKey(w) : t.route?.key;
}
function followTrackRoute(t) {
  if (!(t?.kind === "epic" || t?.loop) || !t.stops?.length || t.inst == null) return;
  const me = playerWorld();
  if (me && t.copiedInst != null && me.inst !== t.copiedInst && continentMapOf(me.inst)) t.copyWhenReady = true;
  const far = farTrack(t);
  if (!far) return;
  const r = t.route?.key === far.key ? t.route : null;
  if (r) advanceRoute(r, far.me);
  const leg = r?.legs[0], riding = leg && leg.kind !== "walk";
  const stale = riding ? Date.now() - r.boarded > ((leg.minutes || 1) * 2 + 3) * 60000
    : r && Math.hypot(far.me.n - r.from[0], far.me.w - r.from[1]) > ROUTE_REPLAN;
  if (!r || stale) askTrackRoute(t, far.dest, far.me, far.key);
}

function askTrackRoute(t, dest, me, key) {
  const ask = `${key}|${Math.round(me.n / 50)}|${Math.round(me.w / 50)}`;
  if (t.routeAsked === ask) return;
  const q = new URLSearchParams({ si: me.inst, sn: me.n.toFixed(1), sw: me.w.toFixed(1), gi: dest.inst, gn: dest.n.toFixed(1),
    gw: dest.w.toFixed(1), name: t.step?.text || t.name, side: app.status?.strs?.faction || "" });
  if (t.kind !== "epic" && app.status?.nums?.hearth === 0 && app.status?.strs?.bind) q.set("hearth", app.status.strs.bind);
  const asked = weighRoute(q, [me.inst, me.n, me.w], () => getJson(`/api/route?${q}`, { key: `${t.kind} route ${key}` }));
  if (!asked) return;
  t.routeAsked = ask;
  t.routePending = !t.route;
  busy(asked.then((plan) => {
    if (t.routeAsked !== ask || app.tracks[t.kind] !== t) return;
    const before = t.route?.legs.map((l) => l.name).join("|");
    t.route = { key, from: [me.n, me.w], boarded: Date.now(), legs: goalHeight(plan?.legs || [], dest.z), minutes: plan?.minutes,
      against: plan?.against, noFlights: !!plan?.noFlights, mode: trackWayMode(t) };
    t.routePending = false;
    fetchLegPaths(t.route, t.kind);
    if (t.route.legs.map((l) => l.name).join("|") !== before) { t.path = null; t.asked = null; }
    renderTracks();
  }, () => { if (t.routeAsked === ask) t.routeAsked = null; }), t.kind);
}

function trackGoal(t) {
  if (t?.loop && t.stops.length > 1) {
    const me = playerWorld();
    if (me && me.inst === t.inst) {
      const p = loopNearest(t, me);
      if (p.d > LOOP_ON) return { inst: t.inst, n: p.n, w: p.w, near: p };
      const [n, w] = loopAhead(t, p, LOOP_AHEAD);
      return { inst: t.inst, n, w, near: p };
    }
  }
  const p = t?.stops?.[t.at];
  return p ? { inst: t.inst, n: p[0], w: p[1], z: p[2] } : null;
}

function trackReached(t) {
  const me = playerWorld();
  if (!t.loop || t.stops.length < 2 || !me || me.inst !== t.inst) return;
  const p = loopNearest(t, me);
  if (p.d > LOOP_ON) return;
  const lapped = t.round != null && t.round > p.round * 0.75 && p.at < p.round * 0.25;
  t.round = p.at;
  if (!lapped && p.seg === t.at) return;
  if (lapped) t.lap = (t.lap || 1) + 1;
  t.at = p.seg;
  if (t.kind === "loop") saveTrack("loop");
  renderTracks();
}

const COLOUR_NAMES = wordsOf("both.colours");
const arrowColor = (t) => COLOUR_NAMES[t.kind === "epic" ? EPIC_LOOK : LOOP_LOOKS[loopLook(t)]];
const COPY_WAIT_MS = 6000;
function trackWaysPending(t) {
  const r = trackRoute(t), cont = r && continentMapOf(r.legs[0]?.map)?.id;
  for (let k = 1; r && k < r.legs.length; k++) {
    const leg = r.legs[k], prev = r.legs[k - 1];
    if (leg.kind === "walk" && prev.at && continentMapOf(leg.map)?.id === cont
        && !app.ways.get(legPathKey(leg, prev.at, r.mode ?? trackWayMode(t)))) return true;
  }
  if (t.loop && t.kind !== "epic") {
    for (let k = 0; k < t.stops.length; k++) {
      const a = t.stops[k], b = t.stops[(k + 1) % t.stops.length];
      if (Math.hypot(a[0] - b[0], a[1] - b[1]) >= LOOP_HOP_STRAIGHT && !app.ways.get(wayKey(t.inst, a, b, loopMode(t)))) return true;
    }
  }
  return false;
}

function epicPlanReady(t) {
  if (!t?.planReady || !planWritten(t)) return;
  t.planReady = false;
  if (planInGame(t) !== "running") showPlanReady({ ...trackReady(t), copied: null });
}

function copyTrackWhenReady(t) {
  if (t.kind === "epic" || !t.copyWhenReady || t.routePending) return;
  if (planInGame(t) === "running") { t.copyWhenReady = false; return; }
  if (guidedTo(t)) return;
  if (trackWaysPending(t) && Date.now() - (t.copyWaitFrom ??= Date.now()) < COPY_WAIT_MS) { t.copyPending = true; return; }
  t.copyPending = false; t.copyWaitFrom = null;
  t.copyWhenReady = false;
  const reach = reachOf(t.path);
  if (reach) { t.copyLead = null; return showToast(reachToast(reach)); }
  const cmd = trackCommand(t);
  if (cmd) trackCopied(t, cmd, t.copyLead || `Copied for the in-game ${arrowColor(t)} arrow`, t.planReady ? trackReady(t) : null);
  t.copyLead = null;
}
const trackReady = (t) => ({ kind: trackReadyKind(t), from: `track-${t.kind}`, reason: t.kind === "epic" ? "epic" : "loop",
  inGame: t.kind === "epic" ? () => app.tracks.epic === t && ["running", "loaded"].includes(planInGame(t)) : null });
function copyTrack(t, heldAt = Date.now()) {
  if (t.kind === "epic") return;
  if (busyFor(t.kind) || ((t.routePending || trackWaysPending(t)) && Date.now() - heldAt < COPY_WAIT_MS)) {
    if (t.copyHeld !== heldAt) { t.copyHeld = heldAt; renderTracks(); }
    return;
  }
  t.copyHeld = null;
  const cmd = trackCommand(t);
  const reach = reachOf(t.path);
  if (cmd) trackCopied(t, cmd, `Copied for the in-game ${arrowColor(t)} arrow${reach ? `, though the route ends ${num(reach.gap)} yd short` : ""}`);
  else showToast(reach?.cutOff ? reachToast(reach) : "Nothing to copy yet. This step has no place on the map, or it is inside a dungeon");
  renderTracks();
}
function trackCopied(t, cmd, lead, plan = null) {
  copyText(cmd, lead, true, plan);
  t.copiedPacked = t.lastPacked;
  t.copiedInst = playerWorld()?.inst;
  t.copyWhenReady = t.copyPending = t.planReady = false;
  t.copyWaitFrom = t.copyHeld = t.copyLead = null;
}

function trackWayKey(t, g) {
  const grid = g.near ? 25 : 1;
  return `${g.inst}|${Math.round(g.n / grid)}|${Math.round(g.w / grid)}|${app.state?.flags?.ghost ? "ghost" : "alive"}|${trackWayMode(t)}`
    + `|${app.state?.level || 1}`;
}

function updateTrackPath(t) {
  const g = trackTarget(t), me = playerWorld();
  if (!g || !me || g.inst !== me.inst || app.dungeon) {
    t.path = null;
    if (!g && me && !app.dungeon && trackRoute(t)) copyTrackWhenReady(t);
    return;
  }
  const planned = t.kind === "epic" ? planWayPath(t, me, g) : undefined;
  if (planned !== undefined) {
    if (!planned) { t.path = null; t.asked = null; }
    else if (t.path?.key !== planned.key) { t.path = planned; t.asked = null; renderTracks(); }
    return copyTrackWhenReady(t);
  }
  if (g.near && g.near.d <= LOOP_PATH_FROM) {
    t.path = null; t.asked = null;
    return copyTrackWhenReady(t);
  }
  const escort = t.kind === "epic" && t.step?.inst === me.inst ? t.step?.escort : null;
  if (escort?.length > 1) {
    const key = `escort|${t.step.quest}|${escort.length}`;
    if (t.path?.key !== key) {
      t.path = { points: escort.slice(1).map((p) => [p[0], p[1], p[2]]), key, from: escort[0].slice(0, 2), escort: true };
      t.asked = null;
      renderTracks();
    }
    return copyTrackWhenReady(t);
  }
  const key = trackWayKey(t, g);
  if (t.path?.key === key && offPath(t.path) < 30 && !roundabout(t.path, [g.n, g.w]) && !shortStale(t.path)
      && askedAsNow(t.path)) return;
  if (t.asked === key && Date.now() - t.askedAt < 4000) return;
  const q = new URLSearchParams({ inst: me.inst, fn: me.n.toFixed(1), fw: me.w.toFixed(1), tn: g.n.toFixed(1), tw: g.w.toFixed(1) });
  if (g.z != null) q.set("tz", g.z.toFixed(1));
  const indoors = youIndoors();
  if (indoors != null) q.set("indoors", indoors ? "1" : "0");
  modeParams(q, app.state?.flags?.ghost ? "ghost" : trackWayMode(t));
  const asked = getJson(`/api/path?${q}`, { key: `${t.kind} path ${key}` });
  if (!asked) return;
  t.asked = key; t.askedAt = Date.now();
  busy(asked.then((p) => {
    if (!p || t.asked !== key) return;
    t.path = { ...p, key, from: [me.n, me.w], at: Date.now(), askedIndoors: indoors };
    copyTrackWhenReady(t);
    renderTracks();
  }, () => {}), t.kind);
}

const GAME_ON_LOOP = 25;
function planWayPath(t, me, g) {
  const s = t.step;
  if (!s?.at || s.escort || g.leg || s.inst !== me.inst) return undefined;
  const bends = gameWay(s.ways, s.planStep);
  if (!bends?.length) return undefined;
  if (g.near && g.near.d <= GAME_ON_LOOP) return null;
  const pts = [...bends, s.at].map((p) => (p[2] != null ? [p[0], p[1], p[2]] : [p[0], p[1]]));
  return { points: pts.slice(1), from: pts[0].slice(0, 2), key: `plan|${t.inst}|${JSON.stringify(pts)}`, plan: true };
}
function stepWay(t) {
  const s = t.step, bends = gameWay(s.ways, s.planStep);
  const way = bends?.length ? bends : t.path ? walkable(t.path).points : [];
  return [...way, s.at].map((p) => [p[0], p[1], p[2] ?? null]);
}

function trackRise(t, g, me) {
  if (!me || !g || g.near || g.leg || g.inst !== me.inst) return null;
  const s = t.kind === "epic" ? t.step : null;
  if (s?.at?.[2] != null && s.inst === me.inst) {
    if (t.heightAt?.step !== s) t.heightAt = { step: s };
    const here = stepHeight(stepWay(t), s.ground, [me.n, me.w], t.heightAt);
    if (here != null) return riseWords(s.at[2] - here, Math.hypot(s.at[0] - me.n, s.at[1] - me.w));
  }
  if (!t.path) return null;
  const pts = walkable(t.path).points.map((p) => [p[0], p[1], p[2]]), end = pts[pts.length - 1];
  if (!reachOf(t.path) && (!end || Math.hypot(end[0] - g.n, end[1] - g.w) > 5)) pts.push([g.n, g.w, g.z]);
  return heightWords(pts, t.kind === "epic" ? t.stops?.[0]?.[2] : null, [me.n, me.w], Math.hypot(g.n - me.n, g.w - me.w),
    t.path.rising ??= {});
}

function trackAlong(t) {
  const g = trackTarget(t), me = playerWorld();
  if (!g || !me || g.inst !== me.inst) return null;
  if (!t.path) return Math.hypot(g.n - me.n, g.w - me.w);
  let along = 0, prev = [me.n, me.w];
  for (const p of remainingPath(t.path)) { along += Math.hypot(p[0] - prev[0], p[1] - prev[1]); prev = p; }
  return along;
}

function tracksOut() {
  if (app.dungeon) return [];
  return Object.keys(TRACK_STYLE).map((kind) => [kind, app.tracks[kind]])
    .filter(([kind, t]) => t && t.inst != null && !(kind === "loop" && prospecting()));
}
function updateTracks() {
  epicPlanReady(app.tracks.epic);
  if (!app.dungeon && app.tracks.epic?.data) fetchStepWays(app.tracks.epic);
  for (const [, t] of tracksOut()) {
    if (!lookedLeg(t)) {
      followTrackRoute(t);
      trackReached(t);
      updateTrackPath(t);
    }
    if (t.loop && t.stops.length > 1) fetchLoopWays(t);
    if (t.copyPending) copyTrackWhenReady(t);
    if (t.copyHeld) copyTrack(t, t.copyHeld);
  }
}
on("update", updateTracks);
function drawTracks(s, size, scale) {
  for (const [kind, t] of tracksOut()) {
    drawWaiting(ghostWaits(), () => {
      if (kind === "epic") { drawEpicTargets(t, s, size, scale); drawAlongTargets(t, s, size, scale); }
      else drawLoopTargets(t, s, size, scale);
      drawTrack(t, trackStyle(kind, t), s, size, scale);
    });
  }
  if (!app.dungeon) drawProspects(s, size, scale);
}

const LOOP_TARGET = { color: tint("kill-crimson"), hot: tint("bone-white") };
const KILL_LOOPS = ["grind", "farm"];
function drawLoopTargets(t, s, size, scale) {
  if (!KILL_LOOPS.includes(t.what) || !t.spots?.length) return;
  const pts = [], screen = screenIn(t.inst, size, scale);
  for (const p of t.spots) {
    const at = screen(p);
    if (at) pts.push([at[0], at[1], p[2] ?? 1]);
  }
  if (!pts.length) return;
  const label = t.mobs?.length ? andList(t.mobs) : t.name;
  noteOverlay(label, LOOP_TARGET.color, LOOP_TARGET.hot);
  drawLit(label, LOOP_TARGET.color, () => renderHeat(pts, heatRadius(s.map, size, scale), heatRamp(LOOP_TARGET.color, LOOP_TARGET.hot)));
}

function drawTrack(t, style, s, size, scale) {
  const inst = app.maps[s.map]?.instance, r = trackRoute(t);
  const screen = screenIn(t.inst, size, scale);
  if (t.loop && t.stops.length > 1) {
    const { line, stopsUnder } = loopLine(t, screen);
    if (line.length > 2) {
      t.stops.forEach((a, k) => {
        const way = app.ways.get(wayKey(t.inst, a, t.stops[(k + 1) % t.stops.length], loopMode(t)));
        if (walkedWay(way)) drawDanger(way, screen);
      });
      drawLoopRound(line, style.color);
    }
    t.stops.forEach((p, k) => {
      const at = screen(p);
      if (!at) return;
      drawStopMark(at[0], at[1], k + 1, stopsUnder[k] ? COVERED : style.color);
      noteMark(at[0], at[1], loopStopTip(t, k));
    });
  }
  const leg = lookedLeg(t);
  if (leg) {
    const legScreen = screenIn(leg.inst, size, scale);
    for (const walk of leg.walks) {
      const line = walk.map(legScreen).filter(Boolean);
      if (line.length > 1) drawWay(line, style.color, { screen: legScreen });
    }
    return drawTrackMark(t, style, t.step?.at ? screen(t.step.at) : null);
  }
  if (t.inst !== inst && !r) return;
  if (t.kind === "loop" && guidedTo(t)) {
    const at = screen(t.stops[t.at]);
    if (at && at[0] >= 0 && at[1] >= 0 && at[0] <= W && at[1] <= H) drawTrackMark(t, style, at);
    return;
  }
  if (r) drawRouteLegs(r, size, scale, style.color);
  const g = trackTarget(t), goal = r ? trackGoal(t) : g, way = g && screenIn(g.inst, size, scale);
  const tp = g && g.inst === inst && way([g.n, g.w]);
  const mark = goal && goal.inst === inst ? screenIn(goal.inst, size, scale)([goal.n, goal.w]) : null;
  const you = youOnScreen(size, scale);
  if (!tp || !you) return drawTrackMark(t, style, mark);
  const rest = drawWayFrom(you, tp, t.path, style.color, way);
  drawTrackMark(t, endsCovered(t.path, rest) && !r ? { ...style, color: COVERED } : style, r ? mark : tp);
}

function loopLine(t, screen) {
  const n = t.stops.length, ring = [];
  const ends = [];
  const me = playerWorld(), near = me?.inst === t.inst ? loopNearest(t, me) : null;
  let here = -1;
  t.stops.forEach((a, k) => {
    const b = t.stops[(k + 1) % n], way = app.ways.get(wayKey(t.inst, a, b, loopMode(t))), walked = walkedWay(way);
    if (near?.hop === k && near.d <= LOOP_ON && app.state?.minimap?.indoors) here = ring.length + (walked ? near.i - 1 : 0);
    const covered = new Set(walked ? way.covered || [] : []);
    for (const [i, p] of (walked ? way.points : [b]).entries()) ring.push([p, covered.has(i), !walked && !!way]);
    ends.push(ring.length - 1);
  });
  if (here >= 0) {
    const on = (j) => ring[((j % ring.length) + ring.length) % ring.length];
    for (let j = here; on(j)[1] && j < here + ring.length; j++) on(j)[1] = false;
    for (let j = here - 1; on(j)[1] && j > here - 1 - ring.length; j--) on(j)[1] = false;
  }
  const line = [[t.stops[0], false], ...ring].map(([p, under, cut]) => {
    const q = screen(p);
    if (q) { q.under = under; q.cut = !!cut; }
    return q;
  }).filter(Boolean);
  return { line, stopsUnder: t.stops.map((_, k) => ring[ends[(k + n - 1) % n]][1]) };
}

function drawLoopRound(line, color) {
  let run = [line[0]];
  const flush = () => { if (run.length > 1) drawWay(run, color, { dots: true }); };
  for (let i = 1; i < line.length; i++) {
    if (!line[i].cut) { run.push(line[i]); continue; }
    flush();
    drawCutOff(line[i - 1], line[i]);
    run = [line[i]];
  }
  flush();
}
function loopCutOff(t) {
  const n = t.stops.length;
  return cutOffStopsHtml(t.stops.map((a, k) => [(k + 1) % n + 1, app.ways.get(wayKey(t.inst, a, t.stops[(k + 1) % n], loopMode(t)))])
    .filter(([, way]) => way && !walkedWay(way)).sort((x, y) => x[0] - y[0]));
}

function drawTrackMark(t, style, at) {
  if (!at) return;
  const [tx, ty] = at;
  if (offView(tx, ty)) return drawEdgeHint(tx, ty, t.kind === "epic" ? t.step?.text || t.name : t.name, style.color);
  drawRingMarker(tx, ty, { r: 10, fill: tint("black", 0.85), ring: style.color, width: 3, color: style.color, dy: 0.5,
    text: t.kind === "epic" ? EPIC_GLYPH[t.step?.kind] || "" : t.at + 1, font: `12px ${MARK_FONT}` });
  noteMark(tx, ty, trackMarkTip(t));
}
function loopStopTip(t, k) {
  const of = `Stop ${k + 1} of ${t.stops.length}`;
  return t.kind === "epic" ? { name: t.step?.text || t.name, sub: `${of} round the camp`, cat: "loopstop", label: "The quest epic's camp" }
    : { name: t.name, sub: of, cat: "loopstop", label: `A stop on the ${loopKind(t)}` };
}
function trackMarkTip(t) {
  if (t.kind === "epic") return { name: t.step?.text || t.name, sub: t.step?.zone || "", cat: "epicmark" };
  return { name: t.name, sub: `Heading for stop ${t.at + 1} of ${t.stops.length}, lap ${t.lap || 1}`, cat: "loopmark",
           label: `Where the ${loopKind(t)} heads now` };
}


function wayKeysHtml(kind, t, guided = false) {
  const mode = trackMode(t);
  const key = (way, cls, icon, name, title, off = false) => `<button data-track-way="${way}" data-track="${kind}"
    class="${cls}${mode === way ? " on" : ""}" aria-pressed="${mode === way}"${off || guided ? " disabled" : ""}
    title="${guided ? word("page.ways.guided") : title}">${icon} ${name}</button>`;
  if (kind === "epic") {
    const inGame = word("page.ways.epic.in-game");
    return key("safe", "safe-btn", HEART, word("page.ways.safest"), `${word("page.ways.safest.tip")} ${inGame}`)
      + key("fight", "fight-btn", SWORDS, word("page.ways.grinding"), `${word("page.ways.grinding.tip")} ${inGame}`);
  }
  return key("safe", "safe-btn", HEART, word("page.ways.safest"), word("page.ways.loop.safest.tip"))
    + key("fight", "fight-btn", SWORDS, word("page.ways.grinding"),
      fights(t) ? word("page.ways.loop.grinding.tip") : word("page.ways.loop.gathering"), !fights(t));
}
const loopWaysHtml = (t, guided) => `<div class="guide-cmd track-ways"><span class="muted">The route there</span>${wayKeysHtml("loop", t, guided)}</div>`;
const epicWaysHtml = (t) => `<div class="guide-cmd track-ways"><span class="muted">The epic's route</span>${wayKeysHtml("epic", t)}</div>`;

function trackLegRow(kind, t) {
  const me = playerWorld();
  if (kind === "loop" && me && t.inst != null && (me.inst !== t.inst || !!trackRoute(t)) && guidedTo(t)) return "";
  const spans = trackLegSpans(t);
  return spans.length > 1 ? legKeys(spans, kind, trackStyle(kind, t).color, trackLegKey(t), writtenPlan(t) ? STEP_WORDS : LEG_WORDS) : "";
}
function trackHtml(kind, t) {
  const legRow = trackLegRow(kind, t), html = trackPanelHtml(kind, t, legRow);
  const fit = fitButton(kind, trackStyle(kind, t).color, t.name || trackLabel(kind, t));
  return legRow && html.includes(legRow) ? html.replace(fit, "") : html;
}
function trackPanelHtml(kind, t, legRow) {
  const style = trackStyle(kind, t), s = app.state, g = trackTarget(t), me = playerWorld(), r = trackRoute(t);
  const along = trackAlong(t), mobs = wayMobsWords(t.path);
  let where = "";
  if (r && !g) where = rideNow(r.legs[0]);
  else if (g && me && g.inst !== me.inst) where = "on another continent";
  else if (g?.near) where = g.near.d > LOOP_ON ? `${distanceWords(along ?? g.near.d)} to the loop${mobs}` : "on the loop";
  else if (along != null) {
    where = `${distanceWords(along)}${g.leg ? ` to ${g.leg.name}` : ""}`;
    const rise = trackRise(t, g, me);
    if (rise) where += `, ${rise}`;
    if (atSpot(along, rise)) where = "You're there";
    else {
      if (s?.facing != null && s.pos && app.maps[s.map]?.world) {
        const f = worldOnMap(g.n, g.w), yd = mapYards(s.map);
        if (f && yd) where += `, ${turnText(wrap(Math.atan2(-(f[0] - s.pos.x) * yd.w, -(f[1] - s.pos.y) * yd.h) - s.facing))}`;
      }
      where += mobs;
    }
  }
  const calc = calculating(kind), notes = calc ? "" : wayNotesHtml(t.path), routeNotes = routeNotesHtml(shownTrackRoute(t), calc);
  const legsLine = r ? `<div class="guide-route">${routeWords(r.legs)}</div>` : "";
  const label = kind === "epic" ? epicTitle(t) : trackLabel(kind, t);
  const guided = kind === "loop" && !!me && t.inst != null && (me.inst !== t.inst || !!r) && guidedTo(t);
  const making = kind === "epic" && !!composeMode(t), shown = kind === "epic" ? shownPlan(t) : null;
  const wait = calc || !!t.copyHeld;
  const head = panelHead(label, style.help, `${kind === "epic" ? "" : `<button data-track-copy="${kind}"${wait ? " disabled" : ""} title="This copies the command for the in-game ${arrowColor({ ...t, kind })} arrow, to paste into the game's chat box">${wait ? "Wait" : "Copy"}</button>`}
    ${fitButton(kind, style.color, t.name || label)}
    ${replanKey(kind)}${kind === "epic" ? backKey() : ""}
    <button data-track-stop="${kind}" title="${kind === "loop" ? `Stop this ${loopKind(t)}">Stop` : `Close this ${trackLabel(kind, t).toLowerCase()}">Close`}</button>`,
    { track: true, glide: kind === "epic", mark: kind === "loop" ? lookMarkHtml(style.look) : "" }) + (kind === "epic" ? epicWaysHtml(t) : "");
  if (making && !shown?.inspect) return head + epicWorking(t) + (producing(t) ? "" : unbuiltLine(t));
  if (kind === "loop") {
    const away = !!me && t.inst != null && (me.inst !== t.inst || !!r), none = !!t.route && !t.route.legs.length;
    const way = !away ? routeNotes : guided ? `<div class="guide-line muted">The guide is taking you there</div>`
      : none ? `<div class="guide-line muted">The Index has no route there from here</div>${routeNotes}`
      : `${legsLine}${routeNotes}${legRow}
        <div class="guide-cmd"><button data-track-guide title="This starts the Navigation Guide to this loop. The guide shows the route there by flight, boat or airship on the map, in its panel and for the in-game arrow">Guide me</button></div>`;
    return `${head}<div class="guide-name">${esc(t.name)}</div>${workingHtml("loop")}<div class="guide-line">${lineHtml(t.sub || "")}</div>
      ${guided ? "" : `<div class="guide-line">Stop ${t.at + 1} of ${t.stops.length}, lap ${t.lap || 1}. The loop goes round until you stop it${where ? ` | ${esc(where)}` : ""}</div>
        ${notes}${loopCutOff(t)}`}
      ${loopWaysHtml(t, guided)}${way}`;
  }
  const wayHtml = `${notes}${legsLine}${routeNotes}${shown?.inspect ? "" : legRow}${t.step?.loop ? loopCutOff(t) : ""}`;
  if (shown) return epicPlanHtml(t, head, where, wayHtml, shown, shown.inspect ? legRow : "");
  const d = t.data;
  if (!d && t.waiting) return `${head}<div class="guide-line plan-why wait">Waiting for the game: ${esc(t.waiting)}</div>`;
  if (!d) return `${head}<div class="guide-line">${askNote("epic", { what: "the epic's steps", again: () => { refreshEpic(); renderTracks(); } })}</div>`;
  const plan = planInGame(t), nums = app.status?.nums || {};
  const planLine = planNote(t) || (app.shared?.working ? `<div class="guide-line muted">The Index is writing the epic's plan for the addon...</div>`
    : `${plan === "running" ? `<div class="guide-line plan-loaded">The epic's guide runs in game${nums.epicStep ? `, at step ${nums.epicStep}` : ", but the guide has nothing to do right now"}</div>`
      : plan === "loaded" ? `<div class="guide-line plan-ready">The epic's plan is in game, but its guide isn't running. Type /ioa guide start</div>`
      : plan === "ready" && newerPlan(t) ? newerPlanHtml(newerPlan(t)) : ""}${waysLine(t)}${unbuiltLine(t)}`);
  const quests = d.quests || [], done = quests.filter((q) => q.state === "done").length;
  const next = d.steps.slice(1, 4).map((x) => `<li>${esc(x.text)}${x.group ? GROUP_TAG : ""}</li>`).join("");
  const later = laterLine((d.later || []).filter((x) => !x.missing));
  const step = t.step;
  return `${head}<div class="guide-name">${esc(d.name)}</div>${epicWorking(t)}${planLine}
    ${step ? `<div class="guide-line"><b>${esc(step.text)}</b></div>
      ${step.group ? `<div class="guide-line plan-group">Group quest</div>` : ""}
      ${step.moves ? `<div class="guide-line plan-moves">${esc(step.moves)}</div>` : ""}
      <div class="guide-line">${esc([step.zone, step.loop ? `stop ${t.at + 1} of ${t.stops.length} round the camp` : "",
        step.patrols?.length && !step.loop?.length && !step.moves ?`${step.who?.join(", ") || "the mob"} walks the dotted way` : "",
        step.at ? where : "the step has no place on the map, so do it where it is"].filter(Boolean).join(" | "))}</div>
      ${step.at ? wayHtml : ""}`
      : epicAllDone(d) ? `<div class="guide-line"><b>All done</b></div>${nextChainsHtml({ key: t.key, next: d.next })}`
      : `<div class="guide-line muted">The epic has nothing for you to do right now</div>`}
    <div class="guide-line muted">${d.steps.length} step${d.steps.length === 1 ? "" : "s"} left${quests.length ? `, ${done} of ${quests.length} quests turned in` : ""}</div>
    ${next ? `<ol class="track-next">${next}</ol>` : ""}
    ${grindLine(grindWords(d.steps))}
    ${missingLine((d.later || []).filter((x) => x.missing))}
    ${errandNotesLine((d.errandNotes || []).filter((n) => !n.hidden).map((n) => n.text),
    (d.errandNotes || []).filter((n) => n.hidden).map((n) => n.text))}
    ${later}${laterHtml((d.campLater || []).map((e) => ({ text: e.text, offer: e.wall?.offer })))}${materialsHtml(t)}`;
}

const LATER_NAMED = 3;
const LATER_HIGH = /^the quest opens at level (\d+)(?:, and this plan takes you to level (\d+))?$/;
const LATER_NEVER = /(^the quest|, and .+) (is for (the other faction|another class|another race)|needs a profession you don't have|opens at level \d+, above the game's level cap of \d+)$/;
function laterLine(all) {
  const later = all.filter((x) => !LATER_NEVER.test(x.why || ""));
  if (!later.length) return "";
  const high = [], other = [];
  for (const x of later) {
    const m = LATER_HIGH.exec(x.why || "");
    if (m) high.push({ name: x.name, at: +m[1], top: m[2] ? +m[2] : null }); else other.push({ name: x.name, why: x.why || "" });
  }
  high.sort((a, b) => a.at - b.at);
  const named = (names) => {
    const all = [...new Set(names)], shown = all.slice(0, LATER_NAMED);
    return andList(all.length > shown.length ? [...shown, `${all.length - shown.length} more`] : shown);
  };
  const parts = [];
  if (high.length) {
    const top = high.every((x) => x.top !== null) ? high[0].top : null, n = `${high.length} quest${high.length === 1 ? "" : "s"}`;
    parts.push(`${top !== null ? `${n} opening above level ${top}, where this plan takes you, from level ${high[0].at}`
      : `${n} opening from level ${high[0].at}`}: ${named(high.map((x) => x.name))}`);
  }
  if (other.length) parts.push(named(other.map((x) => `${x.name} (${x.why})`)));
  const lines = [...high.map((x) => `${x.name}: at level ${x.at}`), ...other.map((x) => `${x.name}: ${x.why}`)];
  const counts = new Map();
  for (const l of lines) counts.set(l, (counts.get(l) || 0) + 1);
  const hover = [...counts].map(([l, n]) => (n > 1 ? `${l} (${n} quests)` : l)).join("\n");
  return `<div class="guide-line muted plan-later" title="${esc(hover)}">Not yet: ${esc(parts.join(". "))}</div>`;
}

function trackBody(box) {
  let body = box.querySelector(":scope > .track-body");
  if (!body) {
    box.innerHTML = `<canvas class="prospect-glass" hidden></canvas><div class="track-body"></div>`;
    body = box.querySelector(":scope > .track-body");
  }
  return body;
}

function renderTracks() {
  for (const kind of Object.keys(TRACK_STYLE)) {
    const box = $(`track-${kind}`), t = app.tracks[kind];
    if (!box) continue;
    const looking = kind === "loop" && prospecting(), scouting = kind === "loop" && !looking && !!app.scout;
    const closed = kind === "epic" && !t ? closedEpic() : null;
    const html = looking ? prospectHtml() : scouting ? scoutHtml() : t ? trackHtml(kind, t) : closed ? closedEpicHtml(closed) : "";
    (kind === "epic" ? setStepsHtml : setHtml)(kind === "loop" || kind === "epic" ? trackBody(box) : box, html);
    if (kind === "epic") showCompose(box, composeMode(t), t);
    if (kind === "epic") glideLabels(box);
    if (kind === "epic") growPlanBar(box);
    if (kind === "loop") {
      const look = looking ? loopLook({ what: "gather", layer: app.prospect.layer })
        : scouting ? (app.scout.what === "skin" ? "skin" : "xp") : t ? trackStyle(kind, t).look : "";
      if (box.dataset.look !== look) box.dataset.look = look;
    }
    box.hidden = !t && !looking && !scouting && !closed;
    box.classList.toggle("waits", !!t && ghostWaits());
    if (kind === "loop" && !looking) {
      if (!scouting && t?.what === "gather" && t.glass) glassEnsure(t.glass);
      else if (glass.phase !== "off") glassStop();
    }
  }
  drawQuestText();
  frameNow();
  const chip = $("epic-mode"), e = app.tracks.epic;
  if (chip) { chip.hidden = !e; chip.textContent = e ? e.name : ""; }
}

REPLANS.loop = {
  title: () => "This plans the loop afresh from the character's spot, with the level, skills and settings now, over the same area, the same as stopping the loop and starting it again. Then /reload in game or paste its line",
  start: replanLoop,
};
function loopZones(t) {
  if (t.zones?.length) return t.zones;
  const z = t.zone ?? (t.stops?.length ? zoneNamed({ inst: t.inst, n: t.stops[0][0], w: t.stops[0][1] }) : null);
  return z != null ? [z] : [];
}
function replanLoop(done) {
  const t = app.tracks.loop;
  if (!t || !app.state) return done();
  const zones = loopZones(t);
  if (!zones.length || (t.what === "gather" && !t.layer)) {
    showToast(`Where ${t.name} was searched for isn't known, so start the loop again from its layer`);
    return done();
  }
  showToast(`${t.name}: planning afresh from where you are`);
  if (t.what !== "gather") return searchCamp(t.what === "farm", zones, t.what === "skin", { was: t, done });
  const go = (types) => searchGather(t.layer, null, zones, { types, all: t.all, was: t, done });
  if (!t.all) return go(t.types || []);
  gatherKinds(t.layer, zones, (kinds) => go(kinds?.length ? kinds : t.types || []));
}
function sameLoop(t, what, name, stops, ids) {
  if (!t || t.what !== what || t.name !== name || t.stops.length !== stops.length) return false;
  if (fights(t) && String(t.ids || []) !== String(ids || [])) return false;
  const spot = (p) => `${Math.round(p[0])},${Math.round(p[1])}`, have = new Set(t.stops.map(spot));
  return stops.every((p) => have.has(spot(p)));
}
function keepLoop(t, sub, spots) {
  t.sub = sub;
  if (spots) t.spots = spots;
  saveTrack("loop");
  renderTracks();
  showToast(`${replannedWords(t.name)}, round the same stops. Nothing new for the game`);
}

function trackPanelClicked(e) {
  const stop = e.target.closest("button[data-track-stop]"), copy = e.target.closest("button[data-track-copy]");
  if (stop) return stopTrack(stop.dataset.trackStop);
  if (e.target.closest("button[data-epic-reopen]")) return reopenEpic();
  if (e.target.closest("button[data-epic-dismiss]")) return dismissClosedEpic();
  if (e.target.closest("button[data-epic-back]")) return backEpic();
  const material = e.target.closest(".plan-materials button[data-item-key]");
  if (material) {
    const [i, key] = material.dataset.itemKey.split(":");
    return pickMaterial(sideOfPanel(material) || app.tracks.epic, +i, key);
  }
  const picked = (t) => (t.kind === "epic" && followLead(t)) || renderTracks();
  for (const kind of ["epic", "loop"]) {
    const t = app.tracks[kind];
    if (t && stepLegs(e, kind, trackLegSpans(t), trackLegKey(t))) return picked(t);
  }
  const pick = e.target.closest("button[data-epic-pick]"), epic = app.tracks.epic;
  if (pick && epic) {
    pickLeg("epic", trackLegSpans(epic), trackLegKey(epic), +pick.dataset.epicPick);
    return picked(epic);
  }
  if (e.target.closest("button[data-track-guide]")) return guideToLoop(app.tracks.loop);
  const nextUp = e.target.closest("button[data-epic-next]");
  if (nextUp) return startEpic({ key: `log:${nextUp.dataset.epicNext}`, name: "your quests", label: "a quest epic of what follows your ticked quests" });
  const park = e.target.closest("button[data-epic-park]");
  if (park) return copyText(parkLine(park.dataset.epicPark), `Copied the line that parks ${park.dataset.name}`, false);
  const text = e.target.closest("button[data-epic-text]");
  if (text) return toggleEpicText(+text.dataset.epicText, text.dataset.name);
  const steps = e.target.closest("button[data-epic-steps]");
  if (steps) return showSteps(steps.dataset.epicSteps);
  const fold = e.target.closest("button[data-fold-key]");
  if (fold) return toggleFold(fold.dataset.foldKey, fold);
  const offer = e.target.closest("button[data-epic-offer]");
  if (offer) return laterOffer(offer.dataset.epicOffer);
  const unpark = e.target.closest("button[data-epic-unpark]");
  if (unpark) {
    return copyText(unparkLine(unpark.dataset.epicUnpark),
      `Copied the line that puts ${unpark.dataset.name} back in the guide, fitted in from where you are`, false);
  }
  const aside = e.target.closest("button[data-epic-background]");
  if (aside) {
    return copyText(backgroundLine(aside.dataset.epicBackground),
      `Copied the line that sets ${aside.dataset.name} aside until the skill is up`, false);
  }
  const putback = e.target.closest("button[data-epic-putback]");
  if (putback) return copyText(putBackLine(putback.dataset.epicPutback), `Copied the line that puts ${putback.dataset.name} back in your plan`, false);
  const way = e.target.closest("button[data-track-way]");
  if (way && app.tracks[way.dataset.track]) return pressWayKey(app.tracks[way.dataset.track], way.dataset.trackWay);
  if (copy && app.tracks[copy.dataset.trackCopy]) copyTrack(app.tracks[copy.dataset.trackCopy]);
}
function pressWayKey(t, mode) {
  if (t.kind === "epic") {
    t.way = trackMode(t) === mode ? "any" : mode;
    saveTrack("epic");
  } else {
    app.loopWay = trackMode(t) === mode ? "any" : mode;
    try { localStorage.setItem("cc.loopWay", app.loopWay); } catch (e) {   }
  }
  t.path = null; t.asked = null; t.copyWhenReady = t.kind === "loop";
  if (t.route) { t.route.mode = trackWayMode(t); fetchLegPaths(t.route, t.kind); }
  renderTracks();
  if (t.kind === "epic") askEpicMode(t);
}
document.querySelector(".sidestack")?.addEventListener("click", trackPanelClicked);
