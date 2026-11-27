// The Index of Azeroth. Copyright 2026 Index Case <indexofazeroth@pm.me>. PolyForm Strict 1.0.0, see LICENSE.md.
"use strict";

const MT_TIME = typeof module === "object" ? { ...require("./timechart.js"), ...require("./replaytime.js") } : { median, rollingMedian, laneRuns, rpAndList, TRUE_TIME, sessionScale };

const METER_RECENT_DAYS = 7;
const METER_RECENT_FIGHTS = 200;
const METER_SMOOTH_HALF = 4;
const METER_ZOOM_LEAST = 900;
const METER_PICK_LEAST = 60;
const METER_SHOWN_LEAST = 3600;
const METER_MARGIN = 0.03;
const METER_SESSION_GAP = 1200;
const METER_BREAK = 600;
const METER_MARK_RANKS = { level: 5, weapon: 4, talent: 3, gear: 2, spell: 1 };
const METER_BASE_LEAST = 8;

function meterBaselines(fights) {
  const by = {}, bases = {};
  for (const f of fights) if (f.lvl != null) (by[f.lvl] ||= []).push(f.dps);
  for (const [lvl, dps] of Object.entries(by)) {
    const base = dps.length >= METER_BASE_LEAST ? MT_TIME.median(dps) : 0;
    if (base > 0) bases[lvl] = base;
  }
  return bases;
}

function meterSeries(fights, bases = meterBaselines(fights)) {
  const sorted = [...fights].sort((a, b) => a.t - b.t);
  const smooth = MT_TIME.rollingMedian(sorted.map((f) => f.dps), METER_SMOOTH_HALF);
  const series = sorted.map((f, i) => {
    const base = bases[f.lvl] ?? null;
    return { ...f, smooth: smooth[i], base, pct: base ? (f.dps / base) * 100 : null, pctSmooth: null };
  });
  for (let i = 0; i < series.length; i++) {
    let end = i;
    while (end < series.length && series[end].pct != null) end++;
    MT_TIME.rollingMedian(series.slice(i, end).map((f) => f.pct), METER_SMOOTH_HALF).forEach((v, k) => { series[i + k].pctSmooth = v; });
    i = end;
  }
  return series;
}

function meterLevelGain(e, bases) {
  const was = bases[e.from], now = bases[e.level];
  return was && now ? { from: e.from, was, level: e.level, now } : null;
}

function meterUnbased(series) {
  const missing = series.filter((f) => f.pct == null);
  return { few: missing.filter((f) => f.lvl != null).length, unlevelled: missing.filter((f) => f.lvl == null).length };
}

function meterRoom(from, to) {
  const mid = (from + to) / 2, half = Math.max(METER_SHOWN_LEAST, to - from) / 2, room = half * 2 * METER_MARGIN;
  return { from: mid - half - room, to: mid + half + room };
}

function meterScale(series, way) {
  if (way === "time") return MT_TIME.TRUE_TIME;
  return MT_TIME.sessionScale(series.map((f) => ({ t: f.t, end: f.t + f.len, key: f.dg ?? null })), METER_SESSION_GAP, METER_BREAK);
}

function meterWhole(series, events, scale) {
  if (!series.length) return null;
  const last = series[series.length - 1], at = events.map((e) => scale.toPos(e.t));
  return meterRoom(Math.min(scale.toPos(series[0].t), ...at), Math.max(scale.toPos(last.t + last.len), ...at));
}

function meterRecent(series, whole, scale) {
  const last = series[series.length - 1], end = last.t + last.len;
  const nth = series[Math.max(0, series.length - METER_RECENT_FIGHTS)].t;
  const got = meterRoom(scale.toPos(Math.max(end - METER_RECENT_DAYS * 86400, nth)), scale.toPos(end));
  return { from: Math.max(whole.from, got.from), to: Math.min(whole.to, got.to) };
}

function meterLanes(series) {
  const lane = (of) => MT_TIME.laneRuns(series.map((f) => {
    const value = of(f);
    return { t: f.t, end: f.t + f.len, key: value == null ? null : JSON.stringify(value), value };
  }));
  return { level: lane((f) => f.lvl), weapons: lane((f) => f.weapons), gear: lane((f) => f.gear), talents: lane((f) => f.talents) };
}

const meterUndated = (fights) => fights.some((f) => !f.gear && !f.talents);

function meterMark(e, named) {
  if (e.kind === "level") return { kind: "level", key: "level", fill: { level: e.level } };
  if (e.kind === "gear") {
    const kind = e.weapon ? "weapon" : "gear", put = e.slots.filter((s) => s.now).map((s) => named(s.now));
    if (put.length && put.every(Boolean)) return { kind, key: kind, fill: { items: MT_TIME.rpAndList(put) } };
    return { kind, key: `${kind}.count`, n: e.slots.length, fill: {} };
  }
  if (e.kind === "spell") {
    const learned = e.learned.length, lost = e.lost.length;
    if (learned && lost) return { kind: "spell", key: "spell.both", fill: { learned, lost } };
    return learned ? { kind: "spell", key: "spell.learned", n: learned, fill: {} } : { kind: "spell", key: "spell.lost", n: lost, fill: {} };
  }
  if (e.kind !== "talent") return null;
  if (e.points) {
    const now = e.points.join("/");
    return e.was ? { kind: "talent", key: "talent", fill: { now, was: e.was.join("/") } } : { kind: "talent", key: "talent.set", fill: { now } };
  }
  const ranks = Object.entries(e.ranks).map(([name, [was, now]]) => ({ name, was, now }));
  return { kind: "talent", key: "talent.ranks", ranks, fill: {} };
}

if (typeof module === "object") {
  module.exports = { METER_RECENT_DAYS, METER_RECENT_FIGHTS, METER_SMOOTH_HALF, METER_ZOOM_LEAST, METER_PICK_LEAST, METER_SHOWN_LEAST,
    METER_MARGIN, METER_MARK_RANKS, METER_SESSION_GAP, METER_BREAK, METER_BASE_LEAST, meterBaselines, meterSeries, meterLevelGain, meterUnbased, meterScale, meterWhole, meterRecent, meterLanes, meterUndated, meterMark };
}
