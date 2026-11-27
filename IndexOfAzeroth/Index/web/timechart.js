// The Index of Azeroth. Copyright 2026 Index Case <indexofazeroth@pm.me>. PolyForm Strict 1.0.0, see LICENSE.md.
"use strict";

const TC_SCALES = typeof module === "object" ? require("./replaytime.js") : { ticksFor, daysTicksFor };
const TC_STEPS = [1, 2, 2.5, 5];
const TC_CLOCK_MOST = 1.5 * 86400;

const chartX = (t, view, px) => (t - view.from) / Math.max(1e-6, view.to - view.from) * px;
const chartY = (v, top, h) => h - Math.min(1, Math.max(0, v / Math.max(1e-9, top))) * h;

function valueTicks(most, count = 4, whole = false) {
  if (!(most > 0)) return { top: 1, ticks: [0, 1] };
  const raw = most / count, mag = Math.pow(10, Math.floor(Math.log10(raw)));
  const fits = (s) => s >= raw - 1e-9 && (!whole || (s >= 1 && Math.abs(s - Math.round(s)) < 1e-9));
  const step = [...TC_STEPS, 10].map((s) => s * mag).find(fits) ?? Math.max(1, 10 * mag);
  const steps = Math.ceil(most / step - 1e-9), ticks = [];
  for (let k = 0; k <= steps; k++) ticks.push(Math.round(k * step * 1e6) / 1e6);
  return { top: ticks[ticks.length - 1], ticks };
}

function median(values) {
  const sorted = [...values].sort((a, b) => a - b), m = sorted.length >> 1;
  return sorted.length % 2 ? sorted[m] : (sorted[m - 1] + sorted[m]) / 2;
}

function rollingMedian(values, half) {
  return values.map((_, i) => median(values.slice(Math.max(0, i - half), i + half + 1)));
}

function laneRuns(items) {
  const runs = [];
  let run = null;
  for (const it of items) {
    if (it.key == null) run = null;
    else if (run && run.key === it.key) { run.to = Math.max(run.to, it.end); run.n++; }
    else runs.push(run = { from: it.t, to: it.end, key: it.key, value: it.value, n: 1 });
  }
  return runs;
}

function timeScale(from, to, px) {
  return to - from <= TC_CLOCK_MOST ? TC_SCALES.ticksFor(from, to, px) : TC_SCALES.daysTicksFor(from, to, px);
}

const TRUE_TIME = { kind: "time", toPos: (t) => t, fromPos: (p) => p, sessions: [], breaks: [] };
function sessionScale(spans, gap, room) {
  const sessions = [];
  for (const s of spans) {
    const last = sessions[sessions.length - 1], key = s.key ?? null;
    if (last && s.t - last.to <= gap && last.key === key) { last.to = Math.max(last.to, s.end); last.n++; }
    else sessions.push({ from: s.t, to: s.end, n: 1, key });
  }
  let at = 0;
  for (const s of sessions) { s.at = at; at += s.to - s.from + room; }
  const before = (list, key, v) => { let i = -1; while (i + 1 < list.length && list[i + 1][key] <= v) i++; return i; };
  const toPos = (t) => {
    const s = sessions[before(sessions, "from", t)];
    if (!s) return -room / 2;
    return t <= s.to ? s.at + t - s.from : s.at + s.to - s.from + room / 2;
  };
  const fromPos = (p) => {
    const s = sessions[Math.max(0, before(sessions, "at", p))];
    return s ? s.from + Math.max(0, Math.min(s.to - s.from, p - s.at)) : p;
  };
  const breaks = sessions.slice(1).map((s) => ({ from: s.at - room, to: s.at }));
  return { kind: "session", toPos, fromPos, sessions, breaks };
}

const inStretch = (items, view, at = (x) => x.t) => items.filter((x) => at(x) >= view.from && at(x) <= view.to);

function chartPath(points, view, px, top, h) {
  const pieces = [[]];
  for (const p of points) {
    if (p.v == null) pieces.push([]);
    else pieces[pieces.length - 1].push(`${chartX(p.t, view, px).toFixed(1)},${chartY(p.v, top, h).toFixed(1)}`);
  }
  return pieces.filter((piece) => piece.length > 1).map((piece) => `M${piece.join("L")}`).join("");
}

if (typeof module === "object") {
  module.exports = { TC_CLOCK_MOST, chartX, chartY, valueTicks, median, rollingMedian, laneRuns, timeScale, TRUE_TIME, sessionScale, inStretch,
    chartPath };
}
