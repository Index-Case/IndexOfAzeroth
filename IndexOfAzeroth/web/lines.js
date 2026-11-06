// The Index of Azeroth. Copyright 2026 Index Case <indexofazeroth@pm.me>. PolyForm Strict 1.0.0, see LICENSE.md.
"use strict";

const CHAT_MAX = 255;
const B64 = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-_";

function packPoint(fx, fy) {
  const q = (f) => Math.max(0, Math.min(32767, Math.round(f * 32767)));
  let v = q(fx) * 32768 + q(fy), s = "";
  for (let i = 0; i < 5; i++) { s = B64[v % 64] + s; v = Math.floor(v / 64); }
  return s;
}

const WAY_STEP = 2;
function wayCodes(pts, near, far) {
  let cn = 0, cw = 0, first = true;
  for (const p of pts) {
    if (!first) {
      const dn = Math.round((p[0] - cn) / WAY_STEP), dw = Math.round((p[1] - cw) / WAY_STEP);
      if (dn >= -32 && dn <= 30 && dw >= -32 && dw <= 31) {
        near(dn, dw);
        cn += dn * WAY_STEP; cw += dw * WAY_STEP;
        continue;
      }
    }
    far(p, first);
    cn = p[0]; cw = p[1]; first = false;
  }
}
function packWay(cont, pts) {
  let out = "^";
  wayCodes(pts, (dn, dw) => { out += B64[dn + 32] + B64[dw + 32]; }, (p, first) => { out += (first ? "" : "_") + packPoint(...onMap(cont, p)); });
  return out;
}
function packedLength(pts) {
  let n = 1;
  wayCodes(pts, () => { n += 2; }, (p, first) => { n += first ? 5 : 6; });
  return n;
}

const RISE_REACH = 60, RISE_LEAST = 4;
function riseFrom(pts, top, all = false) {
  const end = pts[pts.length - 1];
  top ??= end?.[2];
  if (top == null || !end) return null;
  let from = -1, any = false;
  for (let i = 0; i < pts.length; i++) {
    if (from < 0 && Math.hypot(pts[i][0] - end[0], pts[i][1] - end[1]) <= RISE_REACH) from = i;
    if (from >= 0 && Math.abs(pts[i][2] == null ? 0 : top - pts[i][2]) >= RISE_LEAST) any = true;
  }
  return any || all ? { from, top } : null;
}
const UNDER_MARK = "*", HEIGHT_MARK = ":";
function heightLetters(z) {
  let v = Math.max(0, Math.min(262143, Math.round((z + 4096) * 8))), s = "";
  for (let i = 0; i < 3; i++) { s = B64[v % 64] + s; v = Math.floor(v / 64); }
  return s;
}
const RISE_STEP = 2;
const riseValue = (z, top) => Math.max(0, Math.min(63, Math.round((z == null ? 0 : top - z) / RISE_STEP) + 32));
const COVER_MARK = ".", RUN_MOST = 63;
function coverRuns(pts) {
  const runs = [];
  let inside = false, n = 0;
  const close = () => {
    while (n > RUN_MOST) { runs.push(RUN_MOST, 0); n -= RUN_MOST; }
    runs.push(n);
  };
  for (const p of pts) {
    if (!!p[3] !== inside) { close(); inside = !inside; n = 0; }
    n++;
  }
  if (inside) close();
  return runs.length ? COVER_MARK + runs.map((v) => B64[v]).join("") : "";
}
function riseToken(pts, top, { under = false, height = null, cover = false } = {}) {
  const said = height != null, r = riseFrom(pts, said ? height : top, said);
  const mark = (under ? UNDER_MARK : "") + (said ? HEIGHT_MARK + heightLetters(height) : "");
  const runs = cover ? coverRuns(pts) : "";
  if (!r) return (mark || runs) && `!${mark}${runs}`;
  return "!" + mark + pts.slice(r.from).map((p) => B64[riseValue(p[2], r.top)]).join("") + runs;
}
const riseLength = (pts, top, { under = false, height = null, cover = false } = {}) => {
  const said = height != null, r = riseFrom(pts, said ? height : top, said);
  const mark = (under ? UNDER_MARK.length : 0) + (said ? HEIGHT_MARK.length + 3 : 0) + (cover ? coverRuns(pts).length : 0);
  return r ? 1 + mark + pts.length - r.from : mark && 1 + mark;
};
const coverToken = (pts) => { const runs = coverRuns(pts); return runs && `!${runs}`; };


const RISE_SHOW = 40, ON_WAY = 12, WAY_BACK = 20, WAY_AHEAD = 45;
function wayRises(pts, top) {
  const r = riseFrom(pts, top);
  if (!r) return null;
  return pts.map((p, i) => [p[0], p[1], i >= r.from ? (riseValue(p[2], r.top) - 32) * RISE_STEP : null]);
}
function onStretch(a, b, px, py) {
  const dn = b[0] - a[0], dw = b[1] - a[1], len2 = dn * dn + dw * dw;
  const t = len2 > 0 ? Math.max(0, Math.min(1, ((px - a[0]) * dn + (py - a[1]) * dw) / len2)) : 0;
  return { t, d: Math.hypot(a[0] + dn * t - px, a[1] + dw * t - py), len2 };
}
function heightAlong(pts, px, py, state) {
  if (pts.length < 2) return null;
  const along = [0];
  for (let i = 1; i < pts.length; i++) {
    const a = pts[i - 1], b = pts[i], rise = a[2] != null && b[2] != null ? b[2] - a[2] : 0;
    along[i] = along[i - 1] + Math.hypot(b[0] - a[0], b[1] - a[1], rise);
  }
  const was = state.along ?? 0;
  const best = (lo, hi) => {
    let hit = null;
    for (let i = 0; i < pts.length - 1; i++) {
      if (along[i + 1] < lo || along[i] > hi) continue;
      const a = pts[i], b = pts[i + 1], { t, d } = onStretch(a, b, px, py);
      const at = along[i] + t * (along[i + 1] - along[i]), score = d + Math.abs(at - was) * 0.1;
      if (d <= ON_WAY && (!hit || score < hit.score)) {
        hit = { score, at, h: a[2] != null && b[2] != null ? a[2] + t * (b[2] - a[2]) : a[2] ?? b[2] };
      }
    }
    return hit;
  };
  const hit = best(was - WAY_BACK, was + WAY_AHEAD) || best(-Infinity, Infinity);
  if (!hit) return null;
  state.along = hit.at;
  return hit.h;
}
function riseHere(pts, leg, px, py) {
  const a = pts[leg - 1], b = pts[leg];
  if (b?.[2] == null) return null;
  if (a?.[2] == null) return b[2];
  const { t, len2 } = onStretch(a, b, px, py);
  return a[2] + (b[2] - a[2]) * (len2 > 0 ? t : 1);
}
function riseWords(rise, yards) {
  if (rise == null || yards > RISE_SHOW || Math.abs(rise) < RISE_LEAST) return null;
  return rise > 0 ? "Above you" : "Below you";
}
function heightWords(pts, top, [px, py], yards, state) {
  if (yards > RISE_SHOW) return null;
  const way = wayRises(pts, top);
  if (!way) return null;
  return riseWords(heightAlong(way, px, py, state) ?? riseHere(way, stretchOf(way, [px, py]), px, py), yards);
}

const stepHeight = (pts, ground, [px, py], state) => heightAlong(pts, px, py, state) ?? groundHeight(ground, px, py);
function groundHeight(g, px, py) {
  if (!g || !Array.isArray(g.h) || !g.c || !g.s) return null;
  const rows = Math.floor(g.h.length / g.c), fi = (g.n - px) / g.s, fj = (g.w - py) / g.s;
  const i0 = Math.floor(fi), j0 = Math.floor(fj);
  if (i0 < 0 || j0 < 0 || i0 + 1 >= rows || j0 + 1 >= g.c) return null;
  const at = (i, j) => { const v = g.h[i * g.c + j]; return typeof v === "number" ? v : null; };
  const a = at(i0, j0), b = at(i0, j0 + 1), c = at(i0 + 1, j0), d = at(i0 + 1, j0 + 1);
  if (a == null || b == null || c == null || d == null) return a ?? b ?? c ?? d;
  const u = fi - i0, v = fj - j0;
  return a * (1 - u) * (1 - v) + b * (1 - u) * v + c * u * (1 - v) + d * u * v;
}

const RIDE_CODES = { boat: "B", zeppelin: "Z", airship: "A", tram: "T", flight: "F" };
function rideWords(leg) {
  if (leg.kind === "door" || leg.kind === "teleport") return { code: "D", text: leg.name };
  if (leg.kind === "hearth") return { code: "H", text: leg.name.replace(/^Hearthstone to /, "") };
  return { code: RIDE_CODES[leg.vehicle] || "B", text: leg.name.replace(/^.*? to /, "") };
}

function leastBend(pts, { from = 1, to = pts.length - 2, kept = null, ring = false, before = null } = {}) {
  const n = pts.length;
  let drop = -1, least = Infinity;
  for (let i = from; i <= to; i++) {
    if (kept?.(i)) continue;
    const a = ring ? pts[(i - 1 + n) % n] : pts[i - 1] || before || pts[i], b = pts[i], c = ring ? pts[(i + 1) % n] : pts[i + 1];
    const area = Math.abs((b[0] - a[0]) * (c[1] - a[1]) - (c[0] - a[0]) * (b[1] - a[1]));
    if (area < least) { least = area; drop = i; }
  }
  return drop;
}

function trimToFit(pts, fits, bends = {}) {
  while (!fits()) {
    const drop = leastBend(pts, bends);
    if (drop < 0) return false;
    pts.splice(drop, 1);
  }
  return true;
}


const CAREFUL_MOST = 2;
const CAREFUL_BENDS = 12;
const ELITE_WORDS = /\((?:level [^ )]+ )?(?:rare )?elite[,)]/;

function stretchYards(p, a, b) {
  const dn = b[0] - a[0], dw = b[1] - a[1], len = dn * dn + dw * dw;
  const u = len ? Math.max(0, Math.min(1, ((p[0] - a[0]) * dn + (p[1] - a[1]) * dw) / len)) : 0;
  return Math.hypot(p[0] - a[0] - u * dn, p[1] - a[1] - u * dw);
}
function stretchOf(pts, p) {
  let best = 0, least = Infinity;
  for (let i = 1; i < pts.length; i++) {
    const d = stretchYards(p, pts[i - 1], pts[i]);
    if (d < least) { least = d; best = i; }
  }
  return best;
}
function wayNotes(way, from = 0) {
  const out = [];
  (way?.danger || []).forEach((span, k) => {
    if (from > 0 && stretchOf(way.points || [], span[span.length - 1]) < from) return;
    out.push(...(way.dangerNotes?.[k] || []));
  });
  return out;
}
function carefulPick(notes) {
  const once = [...new Set(notes)], elite = once.filter((n) => ELITE_WORDS.test(n));
  return [...elite, ...once.filter((n) => !elite.includes(n))].slice(0, CAREFUL_MOST);
}
function carefulForms(notes) {
  const forms = notes.map((_, k) => notes.slice(0, notes.length - k));
  const first = notes[0] || "", cut = first.indexOf("): ");
  if (cut >= 0) forms.push([first.slice(0, cut + 1)]);
  forms.push([]);
  return forms;
}
const carefulText = (notes) => notes.map((n) => n.replace(/;/g, ",").replace(/[~=|\x00-\x1f\x7f]/g, "").trim().replace(/\s+/g, "_"))
  .filter(Boolean).join(";");
function carefulToken(notes, lead = " ?") {
  const text = carefulText(notes);
  return text ? lead + text : "";
}
const carefulLength = (notes) => carefulToken(notes).length;

if (typeof module === "object") {
  module.exports = { CHAT_MAX, B64, packPoint, WAY_STEP, wayCodes, packWay, packedLength, RISE_REACH, RISE_LEAST, riseFrom,
                     UNDER_MARK, HEIGHT_MARK, heightLetters, RISE_STEP, riseValue, COVER_MARK, RUN_MOST, coverRuns, coverToken,
                     riseToken, riseLength, RISE_SHOW, ON_WAY,
                     WAY_BACK, WAY_AHEAD, wayRises, onStretch, heightAlong, riseHere, riseWords, heightWords, stepHeight, groundHeight, RIDE_CODES,
                     rideWords, leastBend, trimToFit,
                     CAREFUL_MOST, CAREFUL_BENDS, ELITE_WORDS, stretchYards, stretchOf, wayNotes, carefulPick, carefulForms,
                     carefulText, carefulToken, carefulLength };
}
