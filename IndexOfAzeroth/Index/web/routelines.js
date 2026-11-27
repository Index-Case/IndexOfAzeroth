// The Index of Azeroth. Copyright 2026 Index Case <indexofazeroth@pm.me>. PolyForm Strict 1.0.0, see LICENSE.md.
"use strict";

const ROUTE_BOW = 0.18;
const ROUTE_STEPS = 48;
const MAELSTROM_SHARE = 0.3;
const SETTLE_BAND = 60;
const SETTLE_LIFT = 24;

function bowed(a, b, up, bow = ROUTE_BOW) {
  const east = [-up[1], up[0]];
  const reach = Math.abs((b[0] - a[0]) * east[0] + (b[1] - a[1]) * east[1]);
  return [(a[0] + b[0]) / 2 + up[0] * reach * bow, (a[1] + b[1]) / 2 + up[1] * reach * bow];
}

function curve(a, c, b, steps = ROUTE_STEPS) {
  const out = [];
  for (let i = 0; i <= steps; i++) {
    const t = i / steps, u = 1 - t;
    out.push([u * u * a[0] + 2 * u * t * c[0] + t * t * b[0], u * u * a[1] + 2 * u * t * c[1] + t * t * b[1]]);
  }
  return out;
}

function closestOnCurve(pts, x, y) {
  let near = pts[0], least = Infinity;
  for (const p of pts) {
    const d = Math.hypot(p[0] - x, p[1] - y);
    if (d < least) { least = d; near = p; }
  }
  return [near, least];
}

function steered(a, c, b, away = []) {
  let at = c;
  for (const o of away) {
    if (Math.hypot(a[0] - o.x, a[1] - o.y) < o.r || Math.hypot(b[0] - o.x, b[1] - o.y) < o.r) continue;
    for (let round = 0; round < 12; round++) {
      const [near, least] = closestOnCurve(curve(a, at, b, 24), o.x, o.y);
      if (least >= o.r) break;
      let dx = near[0] - o.x, dy = near[1] - o.y;
      if (Math.hypot(dx, dy) < 1e-6) [dx, dy] = [a[1] - b[1], b[0] - a[0]];
      const len = Math.hypot(dx, dy), push = (o.r - least) * 2.2 + 1;
      at = [at[0] + (dx / len) * push, at[1] + (dy / len) * push];
    }
  }
  return at;
}

function lengths(pts) {
  const out = [0];
  for (let i = 1; i < pts.length; i++) out.push(out[i - 1] + Math.hypot(pts[i][0] - pts[i - 1][0], pts[i][1] - pts[i - 1][1]));
  return out;
}

function pointAt(pts, cum, s) {
  let i = 1;
  while (i < pts.length - 1 && cum[i] < s) i++;
  const p = pts[i - 1], q = pts[i], step = cum[i] - cum[i - 1], t = step ? Math.min(1, Math.max(0, (s - cum[i - 1]) / step)) : 0;
  return { x: p[0] + (q[0] - p[0]) * t, y: p[1] + (q[1] - p[1]) * t, angle: Math.atan2(q[1] - p[1], q[0] - p[0]) };
}

function stretch(pts, cum, s0, s1) {
  const a = pointAt(pts, cum, s0), b = pointAt(pts, cum, s1), out = [[a.x, a.y]];
  pts.forEach((p, i) => { if (cum[i] > s0 && cum[i] < s1) out.push(p); });
  out.push([b.x, b.y]);
  return out;
}

function seenRun(pts, cum, box) {
  let best = null, from = null;
  const inside = (p) => p[0] >= box.left && p[0] <= box.right && p[1] >= box.top && p[1] <= box.bottom;
  pts.forEach((p, i) => {
    if (inside(p) && from == null) from = i;
    if (from != null && (!inside(p) || i === pts.length - 1)) {
      const to = inside(p) ? i : i - 1;
      if (!best || cum[to] - cum[from] > best[1] - best[0]) best = [cum[from], cum[to]];
      from = null;
    }
  });
  return best;
}

function along(pts, cum, from, dir, text, widths) {
  const total = widths.reduce((t, w) => t + w, 0);
  const span = dir > 0 ? [from, from + total] : [from - total, from];
  const backward = Math.cos(pointAt(pts, cum, (span[0] + span[1]) / 2).angle) < 0;
  const letters = [];
  let s = backward ? span[1] : span[0];
  [...text].forEach((ch, i) => {
    const mid = s + (backward ? -widths[i] / 2 : widths[i] / 2), p = pointAt(pts, cum, mid);
    letters.push({ ch, x: p.x, y: p.y, angle: backward ? p.angle + Math.PI : p.angle });
    s += backward ? -widths[i] : widths[i];
  });
  return { letters, span };
}

function settled(p, box, band = SETTLE_BAND) {
  const inset = Math.min(p[0] - box.left, box.right - p[0], p[1] - box.top, box.bottom - p[1]);
  if (inset <= 0) return 0;
  return band > 0 ? Math.min(1, inset / band) : 1;
}

function level(x, y, text, widths) {
  let s = x - widths.reduce((t, w) => t + w, 0) / 2;
  return [...text].map((ch, i) => {
    const at = { ch, x: s + widths[i] / 2, y, angle: 0 };
    s += widths[i];
    return at;
  });
}

const LEVEL_ROWS = 3;
function placeLevel(taken, spot, w, h, lift = SETTLE_LIFT) {
  const box = (dy) => ({ left: spot[0] - w / 2, right: spot[0] + w / 2, top: spot[1] + dy - h / 2, bottom: spot[1] + dy + h / 2 });
  for (let row = 0; row < LEVEL_ROWS; row++) {
    for (const dy of [-lift - row * (h + 2), lift + row * (h + 2)]) {
      const b = box(dy);
      if (taken.some((o) => b.left < o.right && o.left < b.right && b.top < o.bottom && o.top < b.bottom)) continue;
      taken.push(b);
      return dy;
    }
  }
  taken.push(box(-lift));
  return -lift;
}

function insideSpot(spot, box, w, h, margin = 12) {
  return [Math.min(box.right - margin - w / 2, Math.max(box.left + margin + w / 2, spot[0])),
          Math.min(box.bottom - margin - h / 2, Math.max(box.top + margin + h / 2, spot[1]))];
}

const EDGE_ROWS = 4;
function edgePlace(taken, spot, box, w, h, margin = 12) {
  const [x, y] = insideSpot(spot, box, w, h, margin);
  const rows = [0];
  for (let k = 1; k <= EDGE_ROWS; k++) rows.push(-k * (h + 2), k * (h + 2));
  for (const dy of rows) {
    const b = { left: x - w / 2, right: x + w / 2, top: y + dy - h / 2, bottom: y + dy + h / 2 };
    const inside = b.left >= box.left && b.right <= box.right && b.top >= box.top && b.bottom <= box.bottom;
    if (!inside || taken.some((o) => b.left < o.right && o.left < b.right && b.top < o.bottom && o.top < b.bottom)) continue;
    taken.push(b);
    return [x, y + dy];
  }
  return null;
}

function between(from, to, t) {
  return from.map((a, i) => {
    const b = to[i], turn = Math.atan2(Math.sin(b.angle - a.angle), Math.cos(b.angle - a.angle));
    return { ch: a.ch, x: a.x + (b.x - a.x) * t, y: a.y + (b.y - a.y) * t, angle: a.angle + turn * t };
  });
}

function routeMarks(pts, box, names, measure, gap = 7, settle = null, h = 18, taken = []) {
  const cum = lengths(pts), seen = seenRun(pts, cum, box);
  if (!seen) return null;
  const mid = (seen[0] + seen[1]) / 2, diamond = pointAt(pts, cum, mid);
  const out = { diamond, names: [], gaps: [] };
  let onLine = 0;
  names.forEach((name, k) => {
    if (!name) return;
    const widths = [...name].map(measure), dir = k ? 1 : -1, set = along(pts, cum, mid + dir * gap * 1.5, dir, name, widths);
    const fits = set.span[0] >= seen[0] && set.span[1] <= seen[1];
    const s = settle?.end === k ? settle : null;
    if (!s && !fits) return;
    if (s) {
      const spot = pts[k ? pts.length - 1 : 0], w = widths.reduce((t, x) => t + x, 0);
      const from = fits ? set.letters : level(...(edgePlace(taken, spot, box, w, h) || insideSpot(spot, box, w, h)), name, widths);
      const letters = s.t > 0 ? between(from, level(spot[0], spot[1] + s.lift, name, widths), s.t) : from;
      out.names.push({ letters, white: s.t, alpha: 1 });
      if (!fits) return;
    } else out.names.push({ letters: set.letters, white: 0, alpha: 1 });
    const keep = s ? 1 - s.t : 1, half = ((set.span[1] - set.span[0]) / 2 + 3) * keep, c = (set.span[0] + set.span[1]) / 2;
    if (keep > 0) out.gaps.push([c - half, c + half]);
    onLine = Math.max(onLine, keep);
  });
  diamond.alpha = onLine;
  if (onLine > 0) out.gaps.unshift([mid - gap * onLine, mid + gap * onLine]);
  return out;
}

function edgeMarks(pts, box, names, measure, h = 18, taken = [], keep = null) {
  const out = { diamond: { x: 0, y: 0, angle: 0, alpha: 0 }, names: [], gaps: [] };
  names.forEach((name, k) => {
    if (!name || !pts.length) return;
    const widths = [...name].map(measure), w = widths.reduce((t, x) => t + x, 0), end = pts[k ? pts.length - 1 : 0];
    const at = edgePlace(taken, end, box, w, h) || (k === keep ? insideSpot(end, box, w, h) : null);
    if (at) out.names.push({ letters: level(at[0], at[1], name, widths), white: 0, alpha: 1 });
  });
  return out.names.length ? out : null;
}

function piecesOutside(pts, gaps) {
  const cum = lengths(pts), end = cum[cum.length - 1], out = [];
  let s = 0;
  for (const [g0, g1] of [...gaps].sort((p, q) => p[0] - q[0])) {
    if (g0 > s) out.push(stretch(pts, cum, s, Math.min(g0, end)));
    s = Math.max(s, g1);
  }
  if (s < end) out.push(stretch(pts, cum, s, end));
  return out;
}

function offLine(pts, x, y) {
  let least = Infinity;
  for (let i = 1; i < pts.length; i++) {
    const [ax, ay] = pts[i - 1], [bx, by] = pts[i], dx = bx - ax, dy = by - ay;
    const t = Math.max(0, Math.min(1, ((x - ax) * dx + (y - ay) * dy) / (dx * dx + dy * dy || 1)));
    least = Math.min(least, Math.hypot(x - ax - t * dx, y - ay - t * dy));
  }
  return least;
}

function maelstromOn(map) {
  const r = map?.regions;
  if (r?.length !== 2) return null;
  const [w, e] = [...r].sort((p, q) => p.ui[0] - q.ui[0]).map((g) => g.ui);
  const sea = e[0] - w[2];
  if (sea <= 0) return null;
  return { x: (w[2] + e[0]) / 2, y: (Math.max(w[1], e[1]) + Math.min(w[3], e[3])) / 2, r: sea * MAELSTROM_SHARE };
}

if (typeof module === "object") {
  module.exports = { ROUTE_BOW, ROUTE_STEPS, SETTLE_BAND, SETTLE_LIFT, bowed, curve, closestOnCurve, steered, lengths, pointAt,
                     stretch, seenRun, along, settled, level, placeLevel, insideSpot, edgePlace, between, routeMarks, edgeMarks,
                     piecesOutside, offLine, maelstromOn };
}
