// The Index of Azeroth. Copyright 2026 Index Case <indexofazeroth@pm.me>. PolyForm Strict 1.0.0, see LICENSE.md.
"use strict";

const WEIGH_AFTER = 500;
const WEIGH_POLL = 250;
const WEIGH_SETTLE = 1200;
const WEIGH_TINT = "gold";
const weighing = new Map();
let weighAsks = 0;

function weighRoute(q, from, ask) {
  const n = ++weighAsks;
  q.set("ask", n);
  const asked = ask();
  if (!asked) return asked;
  const w = { from, drawn: freshPlanWays(n), walked: 0, tries: 0, tried: null, won: null, answered: 0, reading: false,
    timer: setTimeout(() => readWeighing(n), WEIGH_AFTER) };
  weighing.set(n, w);
  asked.then(() => weighAnswered(n), () => weighAnswered(n, false));
  return asked;
}

function weighAnswered(n, ok = true) {
  const w = weighing.get(n);
  clearTimeout(w.timer);
  if (!w.drawn.list.length && !w.reading) {
    weighing.delete(n);
    return;
  }
  const settle = () => { w.answered = performance.now(); redraw(); };
  if (!ok) {
    w.won = null;
    settle();
    return;
  }
  readWeighing(n, settle);
}

function readWeighing(n, last = null) {
  const w = weighing.get(n);
  if (!w || (w.answered && !last)) return;
  w.reading = true;
  const from = w.walked, asks = `ask=${n}&walks=${from}${w.tried ? "" : "&tried=1"}`;
  getJson(`/api/route/progress?${asks}`, { key: null }).then((p) => {
    if (p) weighSaid(w, p, performance.now(), from);
  }, () => {}).then(() => {
    if (last) last();
    else w.timer = setTimeout(() => readWeighing(n), WEIGH_POLL);
  });
}

function weighSaid(w, p, now, from) {
  if (p.won != null) w.won = p.won;
  if (p.tries !== w.tries) {
    if (!p.tried) {
      w.tried = null;
      return;
    }
    w.tried = p.tried;
    w.tries = p.tries;
    const rides = p.tried.flatMap((t, c) => t.rides.map((r, k) => rideWay(r, c, k ? null : w.from)).filter(Boolean));
    const straight = p.ends.map((e) => ({ i: e.i, at: e.to, way: [e.from, e.to], c: weighedIn(w, e.w), w: e.w, straight: true }));
    addPlanWays(w.drawn, [...rides, ...straight], now);
  }
  if (!w.tries || w.walked !== from) return;
  const ways = p.walks.map((x) => ({ i: x.i, at: x.way.at(-1), way: x.way, c: weighedIn(w, x.w), w: x.w }))
    .filter((x) => x.way.length > 1);
  for (const s of w.drawn.list) if (s.straight && ways.some((x) => x.w === s.w)) s.replaced = true;
  w.walked = p.walked;
  addPlanWays(w.drawn, ways, now);
}

const weighedIn = (w, n) => w.tried.flatMap((t, c) => (t.walks.includes(n) ? [c] : []));

function rideWay(r, c, from) {
  const start = r.from || (from && from[0] === r.i ? [from[1], from[2]] : null);
  if (r.k !== "ride" || !start) return null;
  return { i: r.i, at: r.at, way: [start, ...(r.via || []), r.at], c: [c] };
}

function weighStrength(w, x, now) {
  if (x.replaced) return 0;
  if (!w.answered) return 1;
  const since = now - w.answered - (w.won != null && x.c.includes(w.won) ? WEIGH_SETTLE : 0);
  return lessMotion() ? (since < 0 ? 1 : 0) : clamp01(1 - since / PLAN_WAYS_FADE);
}

function animateRouteWeighing(now) {
  let more = false;
  for (const [n, w] of weighing) {
    if (w.answered && w.drawn.list.every((x) => weighStrength(w, x, now) === 0)) weighing.delete(n);
    else more = more || !!w.answered || now < w.drawn.grow.until;
  }
  return more;
}
on("animate", animateRouteWeighing);

function drawRouteWeighing(size, scale) {
  const now = performance.now();
  for (const w of weighing.values()) {
    if (!w.drawn.list.length) continue;
    const ways = w.drawn.list.map((x) => ({ ...x, a: weighStrength(w, x, now) }));
    drawPlanWays(ways, size, scale, WEIGH_WAYS_ALPHA, planWaysDrawn(w.drawn, now), WEIGH_TINT);
  }
}

if (typeof module === "object") {
  module.exports = { WEIGH_AFTER, WEIGH_POLL, WEIGH_SETTLE, WEIGH_TINT, weighing, weighRoute, weighAnswered, readWeighing,
    weighSaid, weighedIn, rideWay, weighStrength, animateRouteWeighing, drawRouteWeighing };
}
