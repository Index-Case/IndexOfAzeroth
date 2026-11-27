// The Index of Azeroth. Copyright 2026 Index Case <indexofazeroth@pm.me>. PolyForm Strict 1.0.0, see LICENSE.md.
"use strict";

const TC_TOP = 6, TC_PLOT = 150, TC_ICON = 16, TC_SCALE = 18, TC_LANE = 14, TC_LANE_GAP = 3, TC_DOT = 3;
const TC_LABEL_CHAR = 6;

const tcAttrs = (data = {}) => Object.entries(data).map(([k, v]) => ` data-${k}="${esc(String(v))}"`).join("");

function tcRun(r, i, y, high, cls, view, w) {
  const a = Math.max(0, chartX(r.from, view, w)), b = Math.min(w, chartX(r.to, view, w)), span = Math.max(1, b - a);
  if (b < 0 || a > w) return "";
  const label = r.label && span > r.label.length * TC_LABEL_CHAR + 6 ? `<text class="tc-lane-label" x="${(a + 4).toFixed(1)}" y="${y + high - 3}">${esc(r.label)}</text>` : "";
  return `<g class="${cls}${i % 2 ? " odd" : ""}" title="${esc(r.title)}"><rect x="${a.toFixed(1)}" y="${y}" width="${span.toFixed(1)}" height="${high}"/>${label}</g>`;
}

const tcGrid = (values, y, w) => values.ticks.map((v) => `<line class="tc-grid" x1="0" x2="${w}" y1="${y(v)}" y2="${y(v)}"/>
    <text class="tc-value" x="-6" y="${y(v)}" dy="3.5">${esc(values.label(v))}</text>`).join("");
const tcScale = (scale, x, top) => scale.ticks.map((k) => `<line class="tc-tick${k.major ? " major" : ""}" x1="${x(k.t)}" x2="${x(k.t)}" y1="${top}" y2="${top + (k.major ? 5 : 3)}"/>${
    k.label ? `<text class="tc-time" x="${x(k.t)}" y="${top + 15}">${esc(k.label)}</text>` : ""}`).join("");

function timeChartSvg(c) {
  const { width: w, view, values } = c, top = values.top, h = c.plot ?? TC_PLOT, foot = TC_TOP + h;
  const marksGiven = c.marks || [], fade = c.fade == null ? "" : ` opacity="${c.fade}"`;
  const x = (t) => chartX(t, view, w).toFixed(1), y = (v) => (TC_TOP + chartY(v, top, h)).toFixed(1);
  const grid = tcGrid(values, y, w);
  const markLines = marksGiven.map((m) => `<line class="tc-mark-line tc-ring-${m.ring}" x1="${x(m.t)}" x2="${x(m.t)}" y1="${TC_TOP}" y2="${foot}"/>`).join("");
  const line = chartPath(c.line, view, w, top, h), ghost = c.ghost ? chartPath(c.ghost.line, view, w, c.ghost.top, h) : "";
  const rule = c.rule == null ? "" : `<line class="tc-rule" x1="0" x2="${w}" y1="${y(c.rule)}" y2="${y(c.rule)}"/>`;
  const dots = c.dots.map((d) => `<circle class="tc-dot${d.v == null ? " hollow" : ""}" cx="${x(d.t)}" cy="${d.v == null ? foot - TC_DOT - 1 : y(d.v)}" r="${TC_DOT}" title="${esc(d.title)}"${tcAttrs(d.data)}/>`).join("");
  const marks = marksGiven.map((m) => `<g class="tc-mark tc-ring-${m.ring}" title="${esc(m.title)}" transform="translate(${x(m.t)},${foot + 2})">
    <rect x="${-TC_ICON / 2 - 1}" y="-1" width="${TC_ICON + 2}" height="${TC_ICON + 2}"/><image href="/icon/${esc(m.icon)}.jpg" x="${-TC_ICON / 2}" y="0" width="${TC_ICON}" height="${TC_ICON}"/></g>`).join("");
  const scaleTop = foot + (c.marks ? TC_ICON + 4 : 2);
  const scale = tcScale(c.scale, x, scaleTop);
  const sessions = (c.sessions || []).map((s, i) => tcRun(s, i, scaleTop + 1, TC_SCALE - 3, "tc-session", view, w)).join("");
  let laneTop = scaleTop + TC_SCALE;
  const lanes = (c.lanes || []).map((lane) => {
    const at = laneTop;
    laneTop += TC_LANE + TC_LANE_GAP;
    return `<text class="tc-lane-name" x="-6" y="${at + TC_LANE - 3}">${esc(lane.name)}</text>${lane.runs.map((r, i) => tcRun(r, i, at, TC_LANE, "tc-run", view, w)).join("")}`;
  }).join("");
  const height = c.bare ? foot + 2 : laneTop + 2;
  const breaks = (c.breaks || []).filter((b) => chartX(b.to, view, w) >= 0 && chartX(b.from, view, w) <= w).map((b) => {
    const a = Math.max(0, chartX(b.from, view, w)), z = Math.min(w, chartX(b.to, view, w));
    const mid = Math.min(w, Math.max(0, chartX((b.from + b.to) / 2, view, w)));
    return `<rect class="tc-break" x="${a.toFixed(1)}" y="${TC_TOP}" width="${Math.max(1, z - a).toFixed(1)}" height="${height - TC_TOP}"/>
      <line class="tc-break-line" x1="${mid.toFixed(1)}" x2="${mid.toFixed(1)}" y1="${TC_TOP}" y2="${height}"/>`;
  }).join("");
  return `<svg class="tc" width="${w}" height="${height}" viewBox="0 0 ${w} ${height}">
    <defs><clipPath id="tc-clip-${c.id}"><rect x="0" y="${TC_TOP}" width="${w}" height="${h}"/></clipPath></defs>
    <rect class="tc-plot" x="0" y="${TC_TOP}" width="${w}" height="${h}"/>${grid}
    <g clip-path="url(#tc-clip-${c.id})">${c.under || ""}${markLines}${rule}<g${fade}>${ghost ? `<path class="tc-line ghost" transform="translate(0 ${TC_TOP})" d="${ghost}"/>` : ""}${line ? `<path class="tc-line" transform="translate(0 ${TC_TOP})" d="${line}"/>` : ""}${dots}</g></g>${
  c.bare ? "" : `${marks}${scale}${sessions}${lanes}`}${breaks}</svg>`;
}

function tcSpark(points, view, w, h, title) {
  const top = Math.max(0, ...points.map((p) => p.v)), last = points[points.length - 1];
  const dot = last ? `<circle class="tc-spark-dot" cx="${chartX(last.t, view, w).toFixed(1)}" cy="${chartY(last.v, top, h).toFixed(1)}" r="1.5"/>` : "";
  return `<svg class="tc-spark" width="${w}" height="${h}" viewBox="0 0 ${w} ${h}" title="${esc(title)}"><path d="${chartPath(points, view, w, top, h)}"/>${dot}</svg>`;
}
