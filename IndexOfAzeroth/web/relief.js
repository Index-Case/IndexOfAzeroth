// The Index of Azeroth. Copyright 2026 Index Case <indexofazeroth@pm.me>. PolyForm Strict 1.0.0, see LICENSE.md.
"use strict";

const HEIGHTS = { header: 16, version: 1, coarseFlag: 1, groundFlag: 2, coarseHeader: 20, most: 257, perTile: 16 };
const KIND = { ground: 0, building: 1, tree: 2, water: 3 };

const RELIEF = { ring: 1, keep: 400, scale: 0.5, cell: 1600 / 3 / 128, fineYards: 600, reach: 4000, farPx: (1600 / 3 / 16) * 0.5 / 2,
  coarseStep: 1600 / 3 / 16, shadow: 0.6, roofJump: 3, floor: 0.35, water: 0.5, bias: 0.25, thinEdge: 0.75 };

function decodeHeights(buf) {
  if (!buf || buf.byteLength < HEIGHTS.header) return null;
  const v = new DataView(buf), n = v.getUint16(0, true), version = v.getUint16(2, true);
  const base = v.getFloat32(4, true), step = v.getFloat32(8, true), flags = v.getUint32(12, true);
  if (version !== HEIGHTS.version || n < 2) return null;
  let out;
  if (flags & HEIGHTS.coarseFlag) {
    const h = (buf.byteLength - HEIGHTS.coarseHeader) / (3 * n);
    if (!(h >= 1) || !Number.isInteger(h)) return null;
    const at = HEIGHTS.coarseHeader;
    out = { coarse: true, n, w: n, h, col: v.getInt16(16, true), row: v.getInt16(18, true), base, step,
      heights: new Uint16Array(buf, at, n * h), kinds: new Uint8Array(buf, at + 2 * n * h, n * h) };
  } else {
    if (n > HEIGHTS.most || buf.byteLength < HEIGHTS.header + 3 * n * n) return null;
    out = { n, base, step, heights: new Uint16Array(buf, HEIGHTS.header, n * n), kinds: new Uint8Array(buf, HEIGHTS.header + 2 * n * n, n * n) };
    const at = HEIGHTS.header + 3 * n * n;
    if (flags & HEIGHTS.groundFlag && buf.byteLength >= at + 2 * n * n) out.layer = new Uint16Array(buf.slice(at, at + 2 * n * n));
  }
  let lo = Infinity, hi = -Infinity;
  for (const value of out.heights) { if (value < lo) lo = value; if (value > hi) hi = value; }
  return Object.assign(out, { low: base + lo * step, top: base + hi * step });
}

const withoutTrees = (file) => groundOf(file, [KIND.tree]);

const groundOnly = (file) => groundOf(file, [KIND.building, KIND.tree]);

function groundOf(file, out) {
  const w = file.w || file.n, h = file.h || file.n, heights = Uint16Array.from(file.heights), kinds = Uint8Array.from(file.kinds);
  const left = new Uint8Array(w * h);
  let edge = [];
  for (let p = 0; p < w * h; p++) if (out.includes(kinds[p])) { left[p] = 1; kinds[p] = KIND.ground; }
  const round = (p) => { const i = p % w, j = (p - i) / w; return [i > 0 && p - 1, i < w - 1 && p + 1, j > 0 && p - w, j < h - 1 && p + w].filter((q) => q !== false); };
  for (let p = 0; p < w * h; p++) if (left[p] && round(p).some((q) => !left[q])) edge.push(p);
  while (edge.length) {
    const lowest = edge.map((p) => Math.min(...round(p).filter((q) => !left[q]).map((q) => heights[q])));
    edge.forEach((p, k) => { heights[p] = lowest[k]; left[p] = 0; });
    const next = new Set();
    for (const p of edge) for (const q of round(p)) if (left[q]) next.add(q);
    edge = [...next];
  }
  if (left.some((v) => v)) heights.fill(heights.reduce((a, b) => Math.min(a, b)));
  let lo = Infinity, hi = -Infinity;
  for (const v of heights) { if (v < lo) lo = v; if (v > hi) hi = v; }
  return { ...file, heights, kinds, bare: undefined, ground: undefined, low: file.base + lo * file.step, top: file.base + hi * file.step };
}

const heightAt = (tile, i, j) => tile.base + tile.heights[j * (tile.w || tile.n) + i] * tile.step;
const kindAt = (tile, i, j) => tile.kinds[j * (tile.w || tile.n) + i];

function coarseHeight(file, n, w) {
  const T = 1600 / 3, clamp = (v, hi) => Math.min(hi, Math.max(0, v));
  const cx = (32 - w / T - file.col) * HEIGHTS.perTile - 0.5, cy = (32 - n / T - file.row) * HEIGHTS.perTile - 0.5;
  const i = Math.floor(cx), j = Math.floor(cy), rx = clamp(cx - i, 1), ry = clamp(cy - j, 1);
  const a = clamp(i, file.w - 1), b = clamp(i + 1, file.w - 1), c = clamp(j, file.h - 1), d = clamp(j + 1, file.h - 1);
  const h = (x, y) => file.heights[y * file.w + x];
  const top = h(a, c) + (h(b, c) - h(a, c)) * rx, bottom = h(a, d) + (h(b, d) - h(a, d)) * rx;
  return file.base + file.step * (top + (bottom - top) * ry);
}

function farTile(coarse, col, row) {
  const P = HEIGHTS.perTile, n = P + 1, x0 = (col - coarse.col) * P, y0 = (row - coarse.row) * P, w = coarse.w;
  if (x0 < 0 || y0 < 0 || x0 >= w || y0 >= coarse.h) return null;
  const heights = new Uint16Array(n * n), kinds = new Uint8Array(n * n), h = coarse.heights;
  const at = (x, y) => Math.min(coarse.h - 1, Math.max(0, y)) * w + Math.min(w - 1, Math.max(0, x));
  let lo = Infinity, hi = -Infinity;
  for (let j = 0; j < n; j++) {
    for (let i = 0; i < n; i++) {
      const x = x0 + i, y = y0 + j;
      const v = Math.round((h[at(x - 1, y - 1)] + h[at(x, y - 1)] + h[at(x - 1, y)] + h[at(x, y)]) / 4);
      heights[j * n + i] = v;
      kinds[j * n + i] = coarse.kinds[at(x, y)];
      if (v < lo) lo = v;
      if (v > hi) hi = v;
    }
  }
  return { n, base: coarse.base, step: coarse.step, heights, kinds, far: true, low: coarse.base + lo * coarse.step, top: coarse.base + hi * coarse.step };
}


function gridAround(tile, x, y) {
  const n = tile.w || tile.n, i = Math.min(Math.floor(x), n - 2), j = Math.min(Math.floor(y), n - 2), rx = x - i, ry = y - j;
  const at = [[i, j], [i + 1, j], [i, j + 1], [i + 1, j + 1]];
  return { h: at.map(([a, b]) => heightAt(tile, a, b)), k: at.map(([a, b]) => kindAt(tile, a, b)),
    w: [(1 - rx) * (1 - ry), rx * (1 - ry), (1 - rx) * ry, rx * ry] };
}

function aboveShare(tile, x, y, level) {
  const g = gridAround(tile, x, y);
  return g.w.reduce((s, v, c) => s + (g.h[c] >= level ? v : 0), 0);
}

const SIDE_SPOTS = [[-0.5, -0.5], [0.5, -0.5], [-0.5, 0.5], [0.5, 0.5]];

function edgeSurface(tile, x, y, jump = RELIEF.roofJump) {
  const g = gridAround(tile, x, y), lo = Math.min(...g.h), hi = Math.max(...g.h);
  let w = g.w;
  if (hi - lo > jump && g.k.some((k) => k === KIND.building || k === KIND.tree)) {
    const mid = (lo + hi) / 2, up = g.h.map((v) => v >= mid);
    const high = SIDE_SPOTS.reduce((s, [dx, dy]) => s + aboveShare(tile, x + dx, y + dy, mid), 0) / 4 >= 0.5;
    w = w.map((v, c) => (up[c] === high ? v + 1e-4 : 0));
  }
  let all = 0, h = 0, best = 0;
  w.forEach((v, c) => { all += v; h += v * g.h[c]; if (v > w[best]) best = c; });
  return { h: h / all, kind: g.k[best] };
}

const lean = (a, b, jump = RELIEF.roofJump) => (Math.abs(a - b) > jump ? (Math.abs(a) < Math.abs(b) ? a : b) : (a + b) / 2);

function reliefNormal(tile, x, y, d, yards, jump = RELIEF.roofJump) {
  const own = edgeSurface(tile, x, y, jump);
  const at = (dx, dy) => { const s = edgeSurface(tile, x + dx, y + dy, jump); return s.kind === own.kind ? s.h : own.h; };
  const gn = lean(at(0, -d) - own.h, own.h - at(0, d), jump) / (d * yards);
  const gw = lean(at(-d, 0) - own.h, own.h - at(d, 0), jump) / (d * yards);
  const len = Math.hypot(gn, gw, 1);
  return [-gn / len, -gw / len, 1 / len];
}

function tilePoint(col, row, n, i, j, tileYards) {
  return { n: (32 - row) * tileYards - (j * tileYards) / (n - 1), w: (32 - col) * tileYards - (i * tileYards) / (n - 1) };
}

function reliefTiles(corners, tileYards, ring, has) {
  const ns = corners.map((p) => p.n), ws = corners.map((p) => p.w);
  const col = (w) => Math.floor(32 - w / tileYards), row = (n) => Math.floor(32 - n / tileYards);
  const [c0, c1] = [Math.max(0, col(Math.max(...ws)) - ring), Math.min(63, col(Math.min(...ws)) + ring)];
  const [r0, r1] = [Math.max(0, row(Math.max(...ns)) - ring), Math.min(63, row(Math.min(...ns)) + ring)];
  const mc = (c0 + c1) / 2, mr = (r0 + r1) / 2, out = [];
  for (let r = r0; r <= r1; r++) for (let c = c0; c <= c1; c++) if (has(`${c}_${r}`)) out.push([c, r]);
  out.sort((a, b) => Math.hypot(a[0] - mc, a[1] - mr) - Math.hypot(b[0] - mc, b[1] - mr));
  return out.map(([c, r]) => `${c}_${r}`);
}

const reliefWanted = (info, detail, rendered = false) => detail === "high" && !!info?.world && rendered && info.type !== 4 && !info.high;

function reliefLight(hour, night = true, sun = 1) {
  const by = casterAt(hour, night), e = by.light.elevation, rad = (e * Math.PI) / 180, [east, south] = by.light.dir;
  const shadow = by.moon ? by.share : by.share * (RELIEF.floor + (1 - RELIEF.floor) * sunUp(e));
  return { dir: [-south, -east], elevation: e, sin: Math.sin(rad), cos: Math.cos(rad), tan: Math.tan(rad),
    shadow: +(shadow * sun).toFixed(4), light: +(by.share * sun).toFixed(4), sun,
    rgb: by.moon ? lightNeutral(tintRgb("light-moon")) : sunColourAt(hour, night), shade: by.moon ? moonShade() : [0, 0, 0], moon: by.moon, lamp: lampAt(hour, night) };
}

const ONE_LIGHT = { darkest: 0.62, most: 1.8, exposure: [0.78, 0.3], night: 0.52, greyMix: 0.55, dodge: 128 };
const ONE_HALF = 1 - ONE_LIGHT.dodge / 255;

function oneLightAt(hour, shown = true, left = 1) {
  const light = reliefLight(hour, shown, left), night = lampAt(hour, shown), sun = sunColourAt(hour, shown), moon = lightNeutral(tintRgb("light-moon"));
  return { ...light, night, exposure: ONE_LIGHT.exposure[0] + ONE_LIGHT.exposure[1] * light.sin, s: ONE_LIGHT.darkest * light.shadow,
    bright: 1 - (1 - ONE_LIGHT.night) * night, mix: ONE_LIGHT.greyMix * night, tint: sun.map((v, i) => (v + (moon[i] - v) * night) / 255) };
}

const TORCH = { steps: 24, size: 1 };

const PLACED = { reach: 10, lift: 0.7, ease: 1.5, steps: 8, clear: 1600 / 3 / 256, leastPx: 2, cells: 96, width: 1024, round: 0.5,
  kinds: { torch: [1, 1, 1, 1, 0, 0, 0, 0], fire: [2.3, 3, 2, 1.4, 8, 0.5, 0.8, 0.08] } };
const placedFar = ([reach, , core, , , , wander, breathe], R = PLACED.reach) => Math.max(R * reach * (1 + breathe) + wander, R * core);
const PLACED_FAR = Math.max(...Object.values(PLACED.kinds).map((k) => placedFar(k) / PLACED.reach));
const PATCH = { cell: 16, pad: 2 };
const WALK_LIT = { px: 0.5, shades: 2, least: 0.05 };
function walkedOn(was, now, yards) {
  if (!was || !now) return !was !== !now;
  if (was.length !== now.length) return true;
  const shade = (l) => Math.round(l[8] * WALK_LIT.shades);
  return now.some((l, i) => Math.hypot(l[0] - was[i][0], l[1] - was[i][1]) >= yards || shade(l) !== shade(was[i]));
}
function placedPatches(lights, kinds, m, w, h, R = PLACED.reach) {
  const S = PATCH.cell, gx = Math.ceil(w / S), gy = Math.ceil(h / S), marked = new Uint8Array(gx * gy);
  const sx = Math.abs(m[0]) + Math.abs(m[3]), sy = Math.abs(m[1]) + Math.abs(m[4]);
  for (const l of lights) {
    const k = PLACED.kinds[kinds[l[6]]] || PLACED.kinds.torch;
    if (!(k[6] + k[7] > 0)) continue;
    const far = placedFar(k, R), x = m[0] * l[0] + m[3] * l[1] + m[6], y = m[1] * l[0] + m[4] * l[1] + m[7];
    const i0 = Math.max(0, Math.floor((x - sx * far - PATCH.pad) / S)), i1 = Math.min(gx - 1, Math.floor((x + sx * far + PATCH.pad) / S));
    const j0 = Math.max(0, Math.floor((y - sy * far - PATCH.pad) / S)), j1 = Math.min(gy - 1, Math.floor((y + sy * far + PATCH.pad) / S));
    if (i0 > i1 || j0 > j1) continue;
    for (let j = j0; j <= j1; j++) marked.fill(1, j * gx + i0, j * gx + i1 + 1);
  }
  const rects = [];
  let open = new Map();
  for (let j = 0; j < gy; j++) {
    const next = new Map();
    for (let i = 0; i < gx; i++) {
      if (!marked[j * gx + i]) continue;
      const i0 = i;
      while (i + 1 < gx && marked[j * gx + i + 1]) i++;
      const run = `${i0} ${i}`, r = open.get(run) || [i0 * S, j * S, Math.min(w, (i + 1) * S), 0];
      if (!open.has(run)) rects.push(r);
      r[3] = Math.min(h, (j + 1) * S);
      next.set(run, r);
    }
    open = next;
  }
  return rects;
}
const patchBox = (patches) => (patches.length ? [Math.min(...patches.map((p) => p[0])), Math.min(...patches.map((p) => p[1])),
  Math.max(...patches.map((p) => p[2])), Math.max(...patches.map((p) => p[3]))] : null);
function clipBox(g, box, paint) {
  if (!box) return paint();
  g.save();
  const m = g.getTransform();
  g.setTransform(1, 0, 0, 1, 0, 0);
  g.beginPath();
  g.rect(box[0], box[1], box[2] - box[0], box[3] - box[1]);
  g.clip();
  g.setTransform(m);
  try { return paint(); } finally { g.restore(); }
}
const CORE = { yards: 0.5, px: 1.2, far: [2.5, 20, 0.2], most: 0.95, white: 0.6, step: 100, flicker: 0.45, rate: [3, 7] };
const coreSteady = (ypx) => ypx >= CORE.far[1];
const coreTime = (step, steady = false) => (steady ? 0 : (step * CORE.step / 1000) % 1000);
const coreRadius = (ypx) => Math.max(CORE.yards, CORE.px * ypx);
const coreBright = (ypx) => {
  const [near, far, least] = CORE.far, k = Math.min(1, Math.max(0, Math.log(ypx / near) / Math.log(far / near)));
  return 1 - (1 - least) * k * k * (3 - 2 * k);
};
const coreRgb = (c = [1, 1, 1]) => {
  const m = Math.max(...c, 1e-3);
  return c.map((v) => +(v / m + (1 - v / m) * CORE.white).toFixed(4));
};
const glFloat = (v) => (Number.isInteger(v) ? `${v}.0` : `${v}`);

const placedOn = (light, day = false, dayK = 1, dusk = 0) => Math.max(light.lamp, Math.max(day ? 1 : 0, dusk) * dayK);

const placedFalloff = (d, reach = PLACED.reach, soft = PLACED.kinds.torch[4]) => {
  const x2 = (d / reach) ** 2;
  return x2 < 1 ? (1 - x2) ** 2 / (1 + soft * x2) : 0;
};

const placedLift = (sum) => PLACED.lift * (1 - Math.exp(-PLACED.ease * sum));

function placedGrid(lights, box, colours = [], reach = PLACED.reach, kinds = [], span = Math.max(box.south, box.east)) {
  if (!lights.length) return null;
  const W = PLACED.width, cell = Math.max(reach, span / PLACED.cells);
  const gx = Math.max(1, Math.ceil(box.east / cell)), gy = Math.max(1, Math.ceil(box.south / cell)), cells = [];
  for (let i = 0; i < gx * gy; i++) cells.push([]);
  const size = (l) => PLACED.kinds[kinds[l[6]]] || PLACED.kinds.torch;
  lights.forEach((l, i) => {
    const [n, w] = l, far = placedFar(size(l), reach);
    const span = (v) => [Math.max(0, Math.floor((v - far) / cell)), Math.floor((v + far) / cell)];
    const [x0, x1] = span(box.w - w), [y0, y1] = span(box.n - n);
    for (let y = y0; y <= Math.min(y1, gy - 1); y++) for (let x = x0; x <= Math.min(x1, gx - 1); x++) cells[y * gx + x].push(i);
  });
  const total = 2 * gx * gy + cells.reduce((s, c) => s + c.length, 0), list = new Uint32Array(Math.ceil(total / W) * W);
  let at = 2 * gx * gy;
  cells.forEach((c, k) => {
    list.set([at, c.length], 2 * k);
    list.set(c, at);
    at += c.length;
  });
  const out = new Float32Array(Math.ceil((4 * lights.length) / W) * W * 4);
  const shared = (l) => {
    const k = size(l), s = l[8] ?? 1;
    return s === 1 ? k : [k[0], k[1] * s, k[2], k[3] * s, ...k.slice(4)];
  };
  lights.forEach((l, i) => out.set([l[0], l[1], l[2], (l[4] || 0) + PLACED.clear, ...(colours[l[3]] || [1, 1, 1]), l[5] ? 1 : 0,
    ...shared(l)], 16 * i));
  return { cell, gx, gy, count: lights.length, lights: out, list };
}

const SHAPE = { size: 1024, least: 256, ring: 1, chunk: 8, keptMB: 1024, reach: 48, step: 0.75, octave: 16, steps: 96,
  disc: 2.5, rim: 0.8, rimYards: 2, away: 0.45, awayYards: 8, jump: 1, tall: 64, full: 127.5, zero: 85, format: 2,
  far: { sides: [128, 64, 32, 16, 8], soft: 1.5, resident: 64 }, blend: 0.5, fade: 250, fetches: 6, still: 400, sendMB: 12,
  frame: 16, reads: 3, bandsMost: 12, atNoise: 1e-6 };
const RANK = { now: 0, ahead: 1e6, still: 2e6 };
const renderShape = (id) => `/rendershape/${id}.png`;
const shapeHeight = (byte, full) => ((byte - SHAPE.zero) * full) / (255 - SHAPE.zero);
const shapesRead = (index) => index?.shapeFormat === SHAPE.format;
const shapeSide = (px) => Math.min(SHAPE.size, Math.max(SHAPE.least, 2 ** Math.round(Math.log2(Math.max(px, 1)))));
const shapeBytes = (p) => Math.max(p.bytes, 4 * SHAPE.least * SHAPE.least);

function shapeBands(tileYards) {
  const out = [], edge = (tileYards * Math.SQRT2) / SHAPE.least;
  for (let s = SHAPE.size; s >= SHAPE.least; s /= 2) {
    out.push({ k: out.length, far: false, side: s, from: s === SHAPE.size ? 0 : out.at(-1).to, to: (tileYards * Math.SQRT2) / s, step: SHAPE.step });
  }
  const sides = [...SHAPE.far.sides].sort((a, b) => b - a), narrow = (s) => tileYards / (SHAPE.far.soft * s);
  let first = 0;
  sides.forEach((s, i) => { if (narrow(s) <= edge) first = i; });
  for (let i = first; i < sides.length; i++) {
    out.push({ k: out.length, far: true, side: sides[i], from: i === first ? edge : narrow(sides[i]),
      to: i + 1 < sides.length ? narrow(sides[i + 1]) : Infinity, step: tileYards / sides[i] });
  }
  return out;
}

function shapeBlend(ypx, tileYards) {
  const bands = shapeBands(tileYards), z = ypx > 0 ? ypx : 0;
  const mids = bands.map((b) => (b.from > 0 && b.to < Infinity ? Math.sqrt(b.from * b.to) : b.from > 0 ? b.from * Math.SQRT2 : b.to / Math.SQRT2));
  let i = 0;
  while (i < bands.length - 2 && z >= mids[i + 1]) i++;
  const across = z > 0 ? Math.min(1, Math.max(0, Math.log(z / mids[i]) / Math.log(mids[i + 1] / mids[i]))) : 0;
  const mix = Math.min(1, Math.max(0, (across - 0.5) / SHAPE.blend + 0.5));
  return { ...shapeRead(bands[i], bands[i + 1], mix), at: i + mix };
}

function shapeWeights(at, held) {
  const n = held.length, k = Math.max(0, Math.min(Math.floor(at), n - 1)), mix = k < n - 1 ? Math.min(Math.max(at - k, 0), 1) : 0;
  const got = new Array(n).fill(0);
  for (const [b, share] of [[k, 1 - mix], [k + 1, mix]]) {
    let rest = share;
    for (let d = 0; d < n && rest > 1e-9; d++) {
      for (const c of d ? [b - d, b + d] : [b]) {
        if (!(held[c] > 0)) continue;
        got[c] += rest * held[c];
        rest -= rest * held[c];
      }
    }
  }
  const out = got.map((w, b) => [b, w]).filter(([, w]) => w > 1e-6);
  if (out.length <= SHAPE.reads) return out;
  const total = out.reduce((s, [, w]) => s + w, 0), kept = [...out].sort((x, y) => y[1] - x[1]).slice(0, SHAPE.reads);
  const sum = kept.reduce((s, [, w]) => s + w, 0);
  return kept.map(([b, w]) => [b, (w * total) / sum]).sort((x, y) => x[0] - y[0]);
}

const shapeWord = (band, share, full2, unders) =>
  ((band & 15) | (Math.round(Math.min(Math.max(share, 0), 1) * 4095) << 4) | ((unders ? 1 : 0) << 16) | ((full2 & 32767) << 17)) >>> 0;

const shapeRead = (fine, coarse, mix) =>
  ({ fine, coarse, mix, far: (fine.far ? 1 - mix : 0) + (coarse.far ? mix : 0), step: fine.step ** (1 - mix) * coarse.step ** mix });

function shapeSteps(at, step, reach) {
  const out = [];
  let t = 0.5 * step;
  for (let i = 0; i < SHAPE.steps; i++) {
    if (i > 0 && i % SHAPE.octave === 0) step *= 2;
    t = (Math.floor((at + t) / step) + 1) * step - at;
    if (t > reach) break;
    out.push(t);
  }
  return out;
}

function shapeCone(dh, t, light) {
  const across = dh * light.cos - t * light.sin, down = Math.max(t * light.cos + dh * light.sin, 1e-3);
  const k = Math.min(1, Math.max(0, 0.5 + across / (down * Math.tan((SHAPE.disc * Math.PI) / 180))));
  return k * k * (3 - 2 * k);
}

const shapeHides = (h0, g, s, t, light) =>
  Math.max(shapeCone(g + s.top - h0, t, light) - (s.under > 0 ? shapeCone(g + s.under - h0, t, light) : 0), 0) * s.a;

function shapeShadowAt(at, h0, standAt, light, step, reach) {
  let hidden = 0;
  for (const t of shapeSteps(at, step, reach)) {
    const s = standAt(t);
    if (s && s.a > 0) hidden = Math.max(hidden, shapeHides(h0, s.g, s, t, light));
    if (hidden >= 1) break;
  }
  return hidden;
}

const shadedFar = (terrain, ground, top, cover) => Math.max(terrain, ground) * (1 - cover) + Math.max(terrain, top) * cover;


function torchV(to, normal, blocked) {
  const len = Math.hypot(...to), l = to.map((v) => v / len);
  const facing = Math.max(0, normal[0] * l[0] + normal[1] * l[1] + normal[2] * l[2]);
  return Math.min(facing * (1 - blocked) / Math.max(l[2], 1e-3), ONE_LIGHT.most);
}

function gauntletHides(spot, h0, light, g, ground, toScreen, alpha) {
  const d = (ground + g.yards - h0) / Math.max(light.tan, 1e-3);
  if (!(d > 0)) return 0;
  const [x, y] = toScreen(spot.n + light.dir[0] * d, spot.w + light.dir[1] * d);
  const u = (x - g.at[0] + g.hot[0]) / g.size[0], v = (y - g.at[1] + g.hot[1]) / g.size[1];
  return u < 0 || v < 0 || u > 1 || v > 1 ? 0 : alpha(u, v);
}

function torchShadow(h0, top, height, bias = RELIEF.bias, steps = TORCH.steps, stop = 0) {
  let hidden = 0;
  for (let i = 1; i < steps; i++) {
    const k = (i / steps) * (1 - stop), ray = h0 + (top - h0) * k, edge = Math.max(0.5 * TORCH.size * k, 0.05);
    const x = Math.min(1, Math.max(0, 0.5 + (height(k) - ray - bias) / (2 * edge)));
    hidden = Math.max(hidden, x * x * (3 - 2 * x));
  }
  return hidden;
}

const oneLightV = (facing, blocked, light) => Math.min(Math.max(facing, 0) * (1 - blocked) / Math.max(light.sin, 1e-3), ONE_LIGHT.most);

const oneShadow = (...shares) => Math.max(0, ...shares);

const oneCloudTake = (lit, dim) => lit.map((c, i) => (c >= 1e-4 ? 1 - dim[i] / c : 0));

function oneLightLevel(v, light, water = false) {
  const s = light.s * (water ? RELIEF.water : 1);
  return light.exposure * (1 - s + s * v) * light.bright;
}

const AREA_NONE = { d: [1, 1, 1], a: [1, 1, 1], f: [1, 1, 1], h: 0, k: 0 };
const PLACED_NONE = { rgb: [1, 1, 1], a: 0 };
function oneLightRgb(v, light, keep = 1, water = false, vT = 1, day = oneLightAt(SUN.NOON), area = AREA_NONE, placed = PLACED_NONE) {
  const wet = water ? RELIEF.water : 1, s = light.s * wet, torch = oneLightLevel(vT, day, water), t = 1 - keep;
  const lum = Math.max(0.2126 * placed.rgb[0] + 0.7152 * placed.rgb[1] + 0.0722 * placed.rgb[2], 1e-3);
  const sun = light.sin * (1 - wet * (1 - v));
  return light.tint.map((c, i) => {
    const hour = c * light.exposure * (1 - s + s * v) * light.bright;
    const own = day.tint[i] * day.exposure * ((area.a[i] + sun * area.d[i]) * (1 - area.h) + area.f[i] * area.h);
    const lit = (hour + (own - hour) * area.k) * keep + day.tint[i] * torch * t;
    return lit + (day.tint[i] * day.exposure * placed.rgb[i] / lum - lit) * placed.a;
  });
}

function nightMatrix(mix) {
  return [0, 1, 2].map((c) => [0, 1, 2].map((k) => (c === k ? 1 - mix : 0) + mix / 3));
}

function oneLightPixel(rgb, v, light, keep = 1, water = false, vT = 1) {
  const by = oneLightRgb(v, light, keep, water, vT), lit = rgb.map((c, i) => c * by[i]);
  const m = nightMatrix(light.mix * keep);
  return m.map((row) => Math.min(1, Math.max(0, row.reduce((sum, w, k) => sum + w * lit[k], 0))));
}

function marchPlan(elevation, relief, cell = RELIEF.cell / 2) {
  const reach = elevation > 0 && relief > 0 ? Math.min(RELIEF.reach, relief / Math.tan((elevation * Math.PI) / 180)) : 0;
  const near = Math.min(reach, RELIEF.fineYards);
  return { reach, fine: { step: cell, count: Math.ceil(near / cell) }, coarse: { step: RELIEF.coarseStep, count: Math.ceil((reach - near) / RELIEF.coarseStep) } };
}

function coneShare(dh, t, light) {
  const across = dh * light.cos - t * light.sin, down = Math.max(t * light.cos + dh * light.sin, 1e-3);
  const k = Math.min(1, Math.max(0, 0.5 + across / penumbra(down)));
  return k * k * (3 - 2 * k);
}

function reliefShadow(h0, height, plan, light, top = Infinity, bias = RELIEF.bias, at = 0) {
  if (!(light.tan > 0)) return 0;
  const tanD = Math.tan(SKY_DISC * Math.PI / 180), reach = (top - h0) / Math.max(light.tan - (0.5 * tanD) / (light.cos * light.cos), 0.5 * light.tan);
  const mod = (a, b) => a - b * Math.floor(a / b);
  let shadowed = 0, t = 0;
  for (const [{ step, count }, less] of [[plan.fine, bias], [plan.coarse, 0]]) {
    t -= mod(at + t, step);
    for (let i = 0; i < count; i++) {
      t += step;
      if (t > reach || shadowed >= 1) return shadowed;
      shadowed = Math.max(shadowed, coneShare(height(t) - h0 - less, t, light));
    }
  }
  return shadowed;
}

function lanternKeep(at, lantern, lamp) {
  if (!(lamp > 0) || !lantern || !(lantern.h > 0) || !(lantern.perYard > 0)) return 1;
  const { foot, h, perYard, tilt } = lantern;
  return 1 - LAMP.lift * lamp * lanternLight(h, (at[0] - foot[0]) / perYard, (at[1] - foot[1]) / perYard, tilt);
}

function viewMatrix(at, width, height) {
  const o = at(0, 0), x = at(width, 0), y = at(0, height);
  return [(x.n - o.n) / width, (x.w - o.w) / width, 0, (y.n - o.n) / height, (y.w - o.w) / height, 0, o.n, o.w, 1];
}

const slotOf = (col, row, kx, ky) => [col % kx, row % ky];
const tagOf = (instance, col, row) => (instance * 64 + col) * 64 + row + 1;


const RELIEF_VERTEX = `#version 300 es
in vec2 p;
uniform vec2 size;
out vec2 sp;
void main() {
  sp = vec2((p.x + 1.0) * 0.5 * size.x, (1.0 - (p.y + 1.0) * 0.5) * size.y);
  gl_Position = vec4(p, 0.0, 1.0);
}`;

const RELIEF_FRAGMENT = `#version 300 es
precision highp float;
precision highp int;
precision highp usampler2D;
uniform usampler2D hf;
uniform usampler2D kf;
uniform highp sampler2D tags;
uniform usampler2D hc;
uniform usampler2D kc;
uniform ivec2 slots;
uniform float inst, T, top, jump, water, bias;
uniform mat3 world;
uniform vec4 cbox;
uniform vec2 cscale, dir;
uniform float sinE, cosE, tanE, tanD;
uniform int fineN, coarseN;
uniform float fineStep, coarseStep;
uniform float shadowA;
uniform vec3 lamp;
uniform float lampOn, lift, lampY, lampI;
uniform vec2 lampTilt, lampCos;
uniform usampler2D gf;
uniform float exposure, sOne, bright, most, halfOne, dayExp, daySOne, torchUp;
uniform vec3 tintOne, dayTint;
uniform vec2 torchW;
uniform sampler2D gauntlet;
uniform int gOn;
uniform vec4 gBox;
uniform vec2 gW;
uniform float gUp, gTexW, ypx;
uniform mat3 screen;
uniform highp sampler2DArray shapes;
uniform highp sampler2DArray unders;
uniform highp usampler2D shapeAt;
uniform int shapeOn, sN;
uniform float sReach, sTop, tanS, rimA, rimY, awayA, awayY, sJump, sBase;
uniform vec2 sBand[${SHAPE.bandsMost}];
uniform float cloudK;
uniform sampler2D tintD;
uniform sampler2D tintA;
uniform sampler2D tintF;
uniform vec4 tintBox;
uniform float tintK, tintMost;
uniform int probeOn;
uniform highp sampler2D torchL;
uniform highp usampler2D torchI;
uniform vec4 torchBox;
uniform ivec2 torchCells;
uniform float torchOn, torchDusk;
uniform int torchPool;
uniform vec3 torchCore;
uniform int coreOn;
uniform vec3 coreTint;
uniform sampler2D thinned;
uniform int thinOn;
uniform vec2 size;
in vec2 sp;
layout(location = 0) out vec4 frag;
layout(location = 1) out vec4 cloudTake;
layout(location = 2) out vec4 shadeOut;
layout(location = 3) out vec4 coreOut;
const int S = ${HEIGHTS.most};

vec3 areaD = vec3(1.0), areaA = vec3(1.0), areaF = vec3(1.0);
float areaH = 0.0;
void areaTint(vec2 w) {
  if (tintK <= 0.0) return;
  vec2 uv = vec2((32.0 - w.y / T - tintBox.x) * tintBox.z, (32.0 - w.x / T - tintBox.y) * tintBox.w);
  vec4 f = texture(tintF, uv);
  areaD = texture(tintD, uv).rgb * tintMost;
  areaA = texture(tintA, uv).rgb * tintMost;
  areaF = f.rgb * tintMost;
  areaH = f.a;
}

bool slot(vec2 w, out ivec2 s, out vec2 f, out vec4 tag) {
  vec2 t = vec2(32.0 - w.y / T, 32.0 - w.x / T);
  ivec2 cr = ivec2(floor(t));
  s = ivec2(0); f = vec2(0.0); tag = vec4(0.0);
  if (cr.x < 0 || cr.y < 0 || cr.x > 63 || cr.y > 63) return false;
  s = ivec2(cr.x % slots.x, cr.y % slots.y);
  tag = texelFetch(tags, s, 0);
  if (tag.x != (inst * 64.0 + float(cr.x)) * 64.0 + float(cr.y) + 1.0) return false;
  f = (t - vec2(cr)) * (tag.y - 1.0);
  return true;
}

bool fine(vec2 w, out float h) {
  ivec2 s; vec2 f; vec4 tag;
  h = 0.0;
  if (!slot(w, s, f, tag)) return false;
  ivec2 i = min(ivec2(floor(f)), ivec2(int(tag.y) - 2));
  vec2 r = f - vec2(i);
  ivec2 o = s * S + i;
  float a = float(texelFetch(hf, o, 0).r), b = float(texelFetch(hf, o + ivec2(1, 0), 0).r);
  float c = float(texelFetch(hf, o + ivec2(0, 1), 0).r), d = float(texelFetch(hf, o + ivec2(1, 1), 0).r);
  h = tag.z + tag.w * mix(mix(a, b, r.x), mix(c, d, r.x), r.y);
  return true;
}

bool around(vec2 w, out vec4 q, out vec4 wt, out ivec2 o, out float cell) {
  ivec2 s; vec2 f; vec4 tag;
  q = vec4(0.0); wt = vec4(0.0); o = ivec2(0); cell = 1.0;
  if (!slot(w, s, f, tag)) return false;
  ivec2 i = min(ivec2(floor(f)), ivec2(int(tag.y) - 2));
  vec2 r = f - vec2(i);
  o = s * S + i;
  q = tag.z + tag.w * vec4(float(texelFetch(hf, o, 0).r), float(texelFetch(hf, o + ivec2(1, 0), 0).r),
    float(texelFetch(hf, o + ivec2(0, 1), 0).r), float(texelFetch(hf, o + ivec2(1, 1), 0).r));
  wt = vec4((1.0 - r.x) * (1.0 - r.y), r.x * (1.0 - r.y), (1.0 - r.x) * r.y, r.x * r.y);
  cell = T / (tag.y - 1.0);
  return true;
}

float above(vec2 w, float level) {
  vec4 q, wt; ivec2 o; float cell;
  if (!around(w, q, wt, o, cell)) return 0.0;
  return dot(wt, step(vec4(level), q));
}

bool surface(vec2 w, out float h, out float k) {
  vec4 q, wt; ivec2 o; float cell;
  h = 0.0; k = 0.0;
  if (!around(w, q, wt, o, cell)) return false;
  vec4 kk = vec4(float(texelFetch(kf, o, 0).r), float(texelFetch(kf, o + ivec2(1, 0), 0).r),
    float(texelFetch(kf, o + ivec2(0, 1), 0).r), float(texelFetch(kf, o + ivec2(1, 1), 0).r));
  float lo = min(min(q.x, q.y), min(q.z, q.w)), hi = max(max(q.x, q.y), max(q.z, q.w));
  if (hi - lo > jump && (any(equal(kk, vec4(1.0))) || any(equal(kk, vec4(2.0))))) {
    float mid = 0.5 * (lo + hi), c = 0.5 * cell;
    vec4 up = step(vec4(mid), q);
    float share = 0.25 * (above(w + vec2(c, c), mid) + above(w + vec2(c, -c), mid) + above(w + vec2(-c, c), mid) + above(w - vec2(c, c), mid));
    wt = (wt + 1e-4) * (share >= 0.5 ? up : 1.0 - up);
  }
  h = dot(wt, q) / dot(wt, vec4(1.0));
  float best = wt.x;
  k = kk.x;
  if (wt.y > best) { best = wt.y; k = kk.y; }
  if (wt.z > best) { best = wt.z; k = kk.z; }
  if (wt.w > best) k = kk.w;
  return true;
}

bool coarseCell(vec2 w, out vec2 c) {
  c = (vec2(32.0 - w.y / T, 32.0 - w.x / T) - cbox.xy) * ${HEIGHTS.perTile}.0;
  return c.x >= 0.0 && c.y >= 0.0 && c.x < cbox.z && c.y < cbox.w;
}

bool openSea(vec2 w, out float h, out float k) {
  vec2 c;
  h = 0.0; k = 0.0;
  if (!coarseCell(w, c)) return false;
  ivec2 i = ivec2(floor(c));
  if (texelFetch(kc, i, 0).r != ${KIND.water}u) return false;
  h = cscale.x + cscale.y * float(texelFetch(hc, i, 0).r);
  k = ${KIND.water}.0;
  return true;
}

float coarse(vec2 w) {
  vec2 c;
  if (!coarseCell(w, c)) return -1e9;
  c -= 0.5;
  ivec2 i = ivec2(floor(c)), top = ivec2(cbox.zw) - 1, a = clamp(i, ivec2(0), top), b = clamp(i + 1, ivec2(0), top);
  vec2 r = c - vec2(i);
  float h00 = float(texelFetch(hc, a, 0).r), h10 = float(texelFetch(hc, ivec2(b.x, a.y), 0).r);
  float h01 = float(texelFetch(hc, ivec2(a.x, b.y), 0).r), h11 = float(texelFetch(hc, b, 0).r);
  return cscale.x + cscale.y * mix(mix(h00, h10, r.x), mix(h01, h11, r.x), r.y);
}

float cone(float dh, float t) {
  float across = dh * cosE - t * sinE, down = max(t * cosE + dh * sinE, 1e-3);
  float k = clamp(0.5 + across / (down * tanD), 0.0, 1.0);
  return k * k * (3.0 - 2.0 * k);
}

bool ground(vec2 w, out float h) {
  ivec2 s; vec2 f; vec4 tag;
  h = 0.0;
  if (!slot(w, s, f, tag)) return false;
  ivec2 i = min(ivec2(floor(f)), ivec2(int(tag.y) - 2));
  vec2 r = f - vec2(i);
  ivec2 o = s * S + i;
  float a = float(texelFetch(gf, o, 0).r), b = float(texelFetch(gf, o + ivec2(1, 0), 0).r);
  float c = float(texelFetch(gf, o + ivec2(0, 1), 0).r), d = float(texelFetch(gf, o + ivec2(1, 1), 0).r);
  h = tag.z + tag.w * mix(mix(a, b, r.x), mix(c, d, r.x), r.y);
  return true;
}

float heightFar(vec2 w) {
  float h;
  return fine(w, h) ? h : coarse(w);
}

struct Stand { vec2 n; float a, top, under, rise, far, step; };

float thinnedAt(vec2 w) {
  if (thinOn == 0) return 0.0;
  vec2 uv = (screen * vec3(w, 1.0)).xy / size;
  if (uv.x < 0.0 || uv.y < 0.0 || uv.x > 1.0 || uv.y > 1.0) return 0.0;
  return step(${glFloat(RELIEF.thinEdge)}, textureLod(thinned, uv, 0.0).a);
}

Stand shapeLevel(vec3 uv, float level, uint full2, bool under) {
  if (full2 == 0u) return Stand(vec2(0.5), 0.0, 0.0, 0.0, 0.0, 0.0, 0.0);
  vec4 p = textureLod(shapes, uv, level);
  float full = 0.5 * float(full2), top = (p.b * 255.0 - ${SHAPE.zero}.0) * full / ${255 - SHAPE.zero}.0;
  return Stand(p.rg, p.a, top, under ? textureLod(unders, uv, level).r * full : 0.0, p.a >= 0.5 ? top : 0.0, 0.0, 0.0);
}

bool shape(vec2 w, out Stand s) {
  ivec2 sl; vec2 f; vec4 tag;
  s = Stand(vec2(0.5), 0.0, 0.0, 0.0, 0.0, 1.0, 1.0);
  if (shapeOn == 0 || !slot(w, sl, f, tag)) return false;
  uvec4 at = texelFetch(shapeAt, sl, 0);
  if (at.a == 0u) return false;
  vec3 uv = vec3(f / (tag.y - 1.0), float(at.a - 1u));
  vec2 n = vec2(0.0);
  float c = 0.0, top = 0.0, under = 0.0, rise = 0.0, far = 0.0, octave = 0.0, all = 0.0;
  for (int i = 0; i < ${SHAPE.reads}; i++) {
    uint word = at[i];
    float share = float((word >> 4u) & 4095u) / 4095.0;
    if (share <= 0.0) continue;
    int band = int(word & 15u);
    Stand x = shapeLevel(uv, float(band) - sBase, word >> 17u, (word & 65536u) != 0u);
    float cx = share * x.a;
    n += x.n * cx;
    c += cx;
    top += x.top * cx;
    under += x.under * cx;
    rise += share * x.rise;
    far += share * sBand[band].x;
    octave += share * sBand[band].y;
    all += share;
  }
  float k = max(c, 1e-6), each = max(all, 1e-6);
  float keep = 1.0 - thinnedAt(w);
  s = Stand(c > 0.0 ? n / k : vec2(0.5), c * keep, top / k * keep, under / k * keep, rise * keep, far / each, exp2(octave / each));
  return true;
}

float bare(vec2 w) {
  vec4 q, wt; ivec2 o; float cell, h;
  if (!around(w, q, wt, o, cell)) return coarse(w);
  uvec4 kk = uvec4(texelFetch(kf, o, 0).r, texelFetch(kf, o + ivec2(1, 0), 0).r, texelFetch(kf, o + ivec2(0, 1), 0).r, texelFetch(kf, o + ivec2(1, 1), 0).r);
  if (any(equal(kk, uvec4(1u)))) { ground(w, h); return h; }
  return dot(wt, q);
}

float coneS(float dh, float t) {
  float across = dh * cosE - t * sinE, down = max(t * cosE + dh * sinE, 1e-3);
  float k = clamp(0.5 + across / (down * tanS), 0.0, 1.0);
  return k * k * (3.0 - 2.0 * k);
}

float coneSpan(float g, float top, float under, float h0, float t) {
  return max(coneS(g + top - h0, t) - (under > 0.0 ? coneS(g + under - h0, t) : 0.0), 0.0);
}

float onLayer(float rise) {
  return max(rise, 0.0);
}

vec2 shapeShadow(vec2 w, float h0, float hT, float step) {
  vec2 hidden = vec2(0.0);
  float at = dot(w, dir), stride = step, t = 0.5 * step, reach = (sTop - min(h0, hT)) / max(tanE, 1e-3), g;
  Stand s;
  for (int i = 0; i < sN; i++) {
    if (i > 0 && i % ${SHAPE.octave} == 0) stride *= 2.0;
    t = (floor((at + t) / stride) + 1.0) * stride - at;
    if (t > reach || min(hidden.x, hidden.y) >= 1.0) break;
    vec2 p = w + dir * t;
    if (!shape(p, s) || s.a <= 0.0) continue;
    ground(p, g);
    float top = onLayer(s.top);
    hidden = max(hidden, vec2(coneSpan(g, top, s.under, h0, t), coneSpan(g, top, s.under, hT, t)) * s.a);
  }
  return hidden;
}

vec2 rimAway(vec2 w, float rise, float step) {
  Stand s;
  float rim = 0.0, away = 0.0, own = onLayer(rise) - sJump, k = max(1.0, step / rimY);
  for (int i = 1; i <= 4; i++) {
    if (shape(w + dir * k * rimY * float(i) / 4.0, s) && s.a > 0.5 && onLayer(s.top) > own) continue;
    rim = float(5 - i) / 4.0;
    break;
  }
  for (int i = 1; i <= 4; i++) {
    if (shape(w + dir * k * awayY * float(i) / 4.0, s) && s.a > 0.5 && onLayer(s.top) > own) away += 0.25;
  }
  return vec2(rim, away);
}

float lantern(vec2 at) {
  if (lampOn <= 0.0 || lamp.z <= 0.0) return 1.0;
  vec2 d = (at - lamp.xy) / lampY;
  float h = lamp.z, r2 = dot(d, d), b = 1.0 - exp(-3.0 * lampI * h / pow(h * h + r2, 1.5));
  float c = (dot(d, lampTilt) + h * sqrt(max(1.0 - dot(lampTilt, lampTilt), 0.0))) / sqrt(h * h + r2);
  float x = clamp((c - lampCos.x) / (lampCos.y - lampCos.x), 0.0, 1.0);
  return 1.0 - lift * lampOn * b * x * x * (3.0 - 2.0 * x);
}

vec4 oneLit(float v, float water, float keep, float vT, vec4 placed) {
  float s = sOne * water, sd = daySOne * water;
  vec3 hour = tintOne * exposure * (1.0 - s + s * v) * bright;
  vec3 own = dayTint * dayExp * mix(areaA + sinE * (1.0 - water * (1.0 - v)) * areaD, areaF, areaH);
  vec3 c = mix(hour, own, tintK) * keep + dayTint * dayExp * (1.0 - sd + sd * vT) * (1.0 - keep);
  c = mix(c, dayTint * dayExp * placed.rgb / max(dot(placed.rgb, vec3(0.2126, 0.7152, 0.0722)), 1e-3), placed.a);
  return vec4(min(c * halfOne, vec3(1.0)), 1.0);
}

float standing(vec2 p) {
  Stand s;
  float g, k;
  if (shape(p, s) && s.far < 1.0 && ground(p, g)) {
    float own = g + s.rise;
    return s.far <= 0.0 ? own : mix(own, surface(p, g, k) ? g : coarse(p), s.far);
  }
  return surface(p, g, k) ? g : coarse(p);
}

float pointLit(vec2 w, float h0, vec3 nrm, vec3 to, int n, float stop) {
  float hidden = 0.0;
  for (int i = 1; i < n; i++) {
    float k = float(i) / float(n) * (1.0 - stop), edge = max(0.5 * ${TORCH.size}.0 * k, 0.05);
    float x = clamp(0.5 + (standing(w + to.xy * k) - h0 - to.z * k - bias) / (2.0 * edge), 0.0, 1.0);
    hidden = max(hidden, x * x * (3.0 - 2.0 * x));
    if (hidden >= 1.0) break;
  }
  vec3 l = normalize(to);
  return min(max(dot(nrm, l), 0.0) * (1.0 - hidden) / max(l.z, 1e-3), most);
}

float torchLit(vec2 w, float h0, vec3 nrm) {
  float hb, kb;
  if (!surface(torchW, hb, kb)) return 1.0;
  return pointLit(w, h0, nrm, vec3(torchW - w, hb + torchUp - h0), ${TORCH.steps}, 0.0);
}

uint torchAt(uint i) {
  return texelFetch(torchI, ivec2(int(i % ${PLACED.width}u), int(i / ${PLACED.width}u)), 0).r;
}

float lightSeed(vec2 p) {
  return fract(sin(dot(p, vec2(12.9898, 78.233))) * 43758.5453);
}

float flicker(float h, float t) {
  float s = t * mix(${glFloat(CORE.rate[0])}, ${glFloat(CORE.rate[1])}, h) + 97.0 * h, n = 0.0;
  for (int o = 0; o < 2; o++) {
    float j = floor(s), u = fract(s);
    u = u * u * (3.0 - 2.0 * u);
    float lo = fract(sin(j * 127.1 + h * 311.7) * 43758.5453), hi = fract(sin((j + 1.0) * 127.1 + h * 311.7) * 43758.5453);
    n += mix(lo, hi, u) * (o == 0 ? 0.7 : 0.3);
    s = s * 2.3 + 41.0;
  }
  return n;
}

float torchBurn(float day) {
  return max(torchOn, max(day, torchDusk) * tintK);
}

vec4 placedLit(vec2 w, float h0, vec3 nrm) {
  if (torchPool == 0) return vec4(0.0);
  ivec2 c = ivec2(floor((torchBox.xy - w) / torchBox.z)).yx;
  if (c.x < 0 || c.y < 0 || c.x >= torchCells.x || c.y >= torchCells.y) return vec4(0.0);
  uint at = uint(c.y * torchCells.x + c.x) * 2u, first = torchAt(at), count = torchAt(at + 1u);
  vec3 rgb = vec3(0.0);
  float sum = 0.0;
  for (uint k = 0u; k < count; k++) {
    uint i = 4u * torchAt(first + k);
    ivec2 t = ivec2(int(i % ${PLACED.width}u), int(i / ${PLACED.width}u));
    vec4 L = texelFetch(torchL, t, 0), K = texelFetch(torchL, t + ivec2(2, 0), 0), S = texelFetch(torchL, t + ivec2(3, 0), 0);
    vec2 p = L.xy;
    float r = torchBox.w * K.x;
    if (S.z + S.w > 0.0) {
      float h = lightSeed(p), now = torchCore.y;
      p += S.z * 2.0 * (vec2(flicker(fract(h + 0.31), now), flicker(fract(h + 0.67), now)) - 0.5);
      r *= 1.0 + S.w * 2.0 * (flicker(fract(h + 0.13), now) - 0.5);
    }
    vec3 to = vec3(p - w, L.z - h0);
    float d = length(to);
    if (d >= r) continue;
    vec4 C = texelFetch(torchL, t + ivec2(1, 0), 0);
    float x2 = d * d / (r * r), f = 1.0 - x2, on = torchBurn(C.a);
    if (on <= 0.0) continue;
    float g = f * f / (1.0 + S.x * x2);
    float a = K.y * on * g * pointLit(w, h0, nrm, to, ${PLACED.steps}, min(L.w / max(d, 1e-3), 1.0));
    sum += a;
    vec3 hue = C.rgb / max(max(C.r, C.g), max(C.b, 1e-3));
    rgb += a * (S.y > 0.0 ? mix(hue, vec3(1.0), S.y * g) : C.rgb);
  }
  return vec4(sum > 0.0 ? rgb / sum : vec3(1.0), ${glFloat(PLACED.lift)} * (1.0 - exp(-${glFloat(PLACED.ease)} * sum)));
}

vec2 coreLit(vec2 w) {
  ivec2 c = ivec2(floor((torchBox.xy - w) / torchBox.z)).yx;
  if (c.x < 0 || c.y < 0 || c.x >= torchCells.x || c.y >= torchCells.y) return vec2(0.0);
  uint at = uint(c.y * torchCells.x + c.x) * 2u, first = torchAt(at), count = torchAt(at + 1u);
  vec2 sum = vec2(0.0);
  float t = torchCore.y;
  for (uint k = 0u; k < count; k++) {
    uint i = 4u * torchAt(first + k);
    ivec2 tx = ivec2(int(i % ${PLACED.width}u), int(i / ${PLACED.width}u));
    vec4 L = texelFetch(torchL, tx, 0), K = texelFetch(torchL, tx + ivec2(2, 0), 0);
    vec2 p = L.xy, d = p - w;
    float d2 = dot(d, d), r2 = torchCore.x * torchCore.x * K.z * K.z;
    if (d2 >= 9.0 * r2 || standing(p) > L.z + L.w) continue;
    float on = torchBurn(texelFetch(torchL, tx + ivec2(1, 0), 0).a), e = exp(-d2 / r2);
    sum.x += torchCore.z * K.w * on * ${glFloat(1 - CORE.flicker / 2)} * e;
    sum.y += torchCore.z * K.w * on * (1.0 - ${glFloat(CORE.flicker)} * flicker(lightSeed(p), t)) * e;
  }
  return min(sum, vec2(${glFloat(CORE.most)}));
}

float gauntletShadow(vec2 w, float h0) {
  if (gOn == 0) return 0.0;
  float hb, kb;
  if (!surface(gW, hb, kb)) hb = h0;
  float d = (hb + gUp - h0) / max(tanE, 1e-3);
  if (d <= 0.0) return 0.0;
  vec2 uv = ((screen * vec3(w + dir * d, 1.0)).xy - gBox.xy) / gBox.zw;
  if (uv.x < 0.0 || uv.y < 0.0 || uv.x > 1.0 || uv.y > 1.0) return 0.0;
  return textureLod(gauntlet, uv, log2(max(d * tanD / ypx * gTexW / gBox.z, 1.0))).a;
}

vec3 cloudTaken(vec4 lit, vec4 dim) {
  return mix(vec3(0.0), 1.0 - dim.rgb / max(lit.rgb, vec3(1e-4)), step(vec3(1e-4), lit.rgb));
}

float shadowFrom(vec2 w, float h0, float hT, float cover, bool built, bool shaped, float step) {
  float shadowed = 0.0;
  float reach = (top - h0) / max(tanE - 0.5 * tanD / (cosE * cosE), 0.5 * tanE), t = -mod(dot(w, dir), fineStep);
  for (int i = 0; i < fineN; i++) {
    t += fineStep;
    if (t > reach || shadowed >= 1.0) break;
    shadowed = max(shadowed, cone((built && t <= sReach ? bare(w + dir * t) : heightFar(w + dir * t)) - h0 - bias, t));
  }
  t -= mod(dot(w, dir) + t, coarseStep);
  for (int i = 0; i < coarseN; i++) {
    t += coarseStep;
    if (t > reach || shadowed >= 1.0) break;
    shadowed = max(shadowed, cone(coarse(w + dir * t) - h0, t));
  }
  if (shaped && shadowed < 1.0) {
    vec2 hs = shapeShadow(w, h0, hT, step);
    shadowed = mix(max(shadowed, hs.x), max(shadowed, hs.y), cover);
  }
  return shadowed;
}

float litBy(float facing, float shadowed, float stands, vec2 ra) {
  float v = min(facing * (1.0 - shadowed) / max(sinE, 1e-3), most);
  if (stands > 0.0) v = mix(v, min(v * (1.0 - awayA * ra.y) + rimA * ra.x * (1.0 - shadowed), most), stands);
  return v;
}

void main() {
  vec2 w = (world * vec3(sp, 1.0)).xy;
  vec2 cores = coreLit(w);
  if (coreOn == 1) {
    frag = vec4(coreTint * cores.y, cores.y);
    return;
  }
  coreOut = vec4(coreTint * cores.y, cores.y);
  areaTint(w);
  float h0, k0, g0;
  cloudTake = vec4(0.0);
  shadeOut = vec4(0.0, 0.0, 0.0, 1.0);
  if (!surface(w, h0, k0) && !openSea(w, h0, k0)) {
    if (probeOn == 1) { frag = vec4(0.0, 0.0, 0.0, 1.0); return; }
    frag = oneLit(1.0, 1.0, lantern(sp), 1.0, vec4(0.0));
    if (cloudK > 0.0) cloudTake = vec4(cloudTaken(frag, oneLit(1.0 - cloudK, 1.0, lantern(sp), 1.0, vec4(0.0))), 1.0);
    return;
  }
  float d = T / 128.0;
  if (ground(w, g0) && k0 == 2.0) h0 = g0;
  Stand sh;
  bool shaped = shape(w, sh);
  float built = shaped ? 1.0 - sh.far : 0.0;
  float rise = sh.top, hC = g0 + sh.rise, hS = g0 + onLayer(sh.rise), hT = g0 + onLayer(rise);
  float shadowed = 0.0;
  bool across = dot(dir, dir) > 0.0;
  if (shadowA > 0.0 && tanE > 0.0 && across) {
    if (built > 0.0) shadowed = shadowFrom(w, hS, hS, 0.0, true, true, sh.step);
    if (built < 1.0) shadowed = mix(shadowFrom(w, h0, hT, shaped ? sh.a : 0.0, false, shaped, sh.step), shadowed, built);
  }
  float hL = mix(h0, hC, built);
  if (built > 0.0) h0 = mix(h0, hS, built);
  if (shadowA > 0.0 && across) shadowed = max(shadowed, gauntletShadow(w, h0));
  shadeOut = vec4(vec3(shadowed), 1.0);
  if (probeOn == 1) { frag = vec4(shadowed, 0.0, 0.0, 1.0); return; }
  float gn, gs, gw, ge;
  if (!ground(w + vec2(d, 0.0), gn)) gn = g0;
  if (!ground(w - vec2(d, 0.0), gs)) gs = g0;
  if (!ground(w + vec2(0.0, d), gw)) gw = g0;
  if (!ground(w - vec2(0.0, d), ge)) ge = g0;
  vec3 gnorm = normalize(vec3(-(gn - gs) / (2.0 * d), -(gw - ge) / (2.0 * d), 1.0));
  float stands = shaped ? sh.a : 0.0;
  if (stands > 0.0) {
    vec2 e = sh.n * 2.0 - 1.0;
    gnorm = normalize(mix(gnorm, vec3(-e.y, -e.x, sqrt(max(1.0 - dot(e, e), 0.01))), stands));
  }
  float facing = max(dot(gnorm, vec3(dir * cosE, sinE)), 0.0);
  vec2 ra = stands > 0.0 ? rimAway(w, rise, sh.step) : vec2(0.0);
  float keep = lantern(sp), wet = k0 == 3.0 && !(shaped && sh.rise > 0.0) ? water : 1.0, vT = keep < 1.0 ? torchLit(w, hL, gnorm) : 1.0;
  vec4 placed = placedLit(w, hL, gnorm);
  frag = oneLit(litBy(facing, shadowed, stands, ra), wet, keep, vT, placed);
  float e = cores.x;
  if (cloudK > 0.0) cloudTake = vec4(cloudTaken(frag, oneLit(litBy(facing, max(shadowed, cloudK), stands, ra), wet, keep, vT, placed)) * (1.0 - e), 1.0);
  frag = vec4(frag.rgb * (1.0 - e), 1.0 - e);
}`;

const PROBE_MS = 100;

const PROGRAM_POLL_MS = 50;
const programsBuilt = new Map();
function buildPrograms(gl, vertex, fragments) {
  const ext = gl.getExtension("KHR_parallel_shader_compile");
  const sources = Object.entries(fragments).map(([name, src]) => ({ name, src, key: `${vertex}\n${src}` }));
  let vs = null, made = null, apart = false, out = null, timer = 0;
  const shader = (type, src) => {
    const s = gl.createShader(type);
    gl.shaderSource(s, src);
    gl.compileShader(s);
    return s;
  };
  const begin = () => {
    apart = !!ext && sources.some(({ key }) => !programsBuilt.has(key));
    vs = shader(gl.VERTEX_SHADER, vertex);
    made = sources.map(({ name, src, key }) => {
      const fs = shader(gl.FRAGMENT_SHADER, src), p = gl.createProgram();
      gl.attachShader(p, vs);
      gl.attachShader(p, fs);
      gl.bindAttribLocation(p, 0, "p");
      gl.linkProgram(p);
      if (!programsBuilt.has(key)) programsBuilt.set(key, { gl, p });
      return { name, key, p, fs };
    });
  };
  const building = (key) => {
    const first = programsBuilt.get(key);
    if (!first || first === true) return false;
    const fx = first.gl.getExtension("KHR_parallel_shader_compile");
    if (fx && !first.gl.getProgramParameter(first.p, fx.COMPLETION_STATUS_KHR)) return true;
    programsBuilt.set(key, true);
    return false;
  };
  const waits = [];
  const build = {
    done() {
      if (out !== null) return out;
      if (!made) {
        if (sources.some(({ key }) => building(key))) return null;
        begin();
      }
      if (apart && made.some(({ p }) => !gl.getProgramParameter(p, ext.COMPLETION_STATUS_KHR))) return null;
      const failed = made.filter(({ p }) => !gl.getProgramParameter(p, gl.LINK_STATUS));
      for (const { name, p, fs } of failed) {
        if (typeof console === "object") console.warn(`${name} program:`, gl.getShaderInfoLog(vs), gl.getShaderInfoLog(fs), gl.getProgramInfoLog(p));
      }
      for (const { key } of made) programsBuilt.set(key, true);
      out = failed.length ? false : Object.fromEntries(made.map(({ name, p }) => [name, p]));
      return out;
    },
    whenDone(fn) {
      waits.push(fn);
      const look = () => {
        timer = 0;
        if (build.done() === null) { timer = setTimeout(look, PROGRAM_POLL_MS); return; }
        for (const f of waits.splice(0)) f();
      };
      if (!timer) timer = setTimeout(look, PROGRAM_POLL_MS);
    },
  };
  return build;
}
const RELIEF_GL = { alpha: true, premultipliedAlpha: true, preserveDrawingBuffer: true, antialias: false, depth: false, stencil: false };
const RELIEF_UNIFORMS = ["size", "hf", "kf", "tags", "hc", "kc", "slots", "inst", "T", "top", "jump", "world", "cbox", "cscale", "dir", "sinE",
  "cosE", "tanE", "fineN", "coarseN", "fineStep", "coarseStep", "shadowA", "lamp", "lampOn", "lift", "lampY", "lampI", "lampTilt", "lampCos", "water", "tanD", "bias",
  "gf", "exposure", "sOne", "bright", "most", "halfOne", "tintOne",
  "dayExp", "daySOne", "dayTint", "torchW", "torchUp",
  "gauntlet", "gOn", "gBox", "gW", "gUp", "gTexW", "ypx", "screen",
  "shapes", "unders", "shapeAt", "shapeOn", "sN", "sReach", "sTop", "tanS", "rimA", "rimY", "awayA", "awayY", "sJump", "sBase", "sBand",
  "cloudK", "tintD", "tintA", "tintF", "tintBox", "tintK", "tintMost", "probeOn",
  "torchL", "torchI", "torchBox", "torchCells", "torchOn", "torchDusk", "torchPool", "torchCore", "coreOn", "coreTint", "thinned", "thinOn"];
const RELIEF_TEXTURES = ["hf", "kf", "tags", "hc", "kc", "gf", "gauntlet", "shapes", "unders", "shapeAt", "tintD", "tintA", "tintF",
  "torchL", "torchI", "thinned"];
const RELIEF_ARRAYS = ["shapes", "unders"];
const RELIEF_SMOOTH = ["shapes", "unders", "tintD", "tintA", "tintF"];
const TINT_NONE = Uint8Array.from([102, 102, 102, 255]);
const HAZE_NONE = Uint8Array.from([102, 102, 102, 0]);

function screenMatrix(m) {
  const [a, c, , b, d, , e, f] = m, det = a * d - b * c;
  const ia = d / det, ib = -b / det, ic = -c / det, id = a / det;
  return [ia, ic, 0, ib, id, 0, -(ia * e + ib * f), -(ic * e + id * f), 1];
}

class Relief {
  constructor({ canvas, bytes, decode, drawn, context = (c) => c.getContext("webgl2", RELIEF_GL), now = () => performance.now(),
    doc = typeof document === "object" ? document : null, clearSea = () => tintArt("sea"), picture = () => new Image(),
    resize = (img, side, row = 0) => (typeof createImageBitmap === "function" ? createImageBitmap(img, 0, row, img.width, img.width,
      { resizeWidth: side, resizeHeight: side, resizeQuality: "medium", premultiplyAlpha: "none", colorSpaceConversion: "none" })
      : Promise.reject(new Error("no resize"))),
    memory = (typeof navigator === "object" && navigator.deviceMemory) || 8 }) {
    Object.assign(this, { canvas, bytes, drawn, context, now, doc, clearSea, picture, resize, decode });
    this.shapeBudget = Math.min(1, memory / 8) * SHAPE.keptMB * 2 ** 20;
    this.pictures = new Map();
    this.shapes = new Map();
    this.shapeAsk = 0;
    this.shapeLayers = null;
    this.shapeSent = [];
    this.shapeLevels = 0;
    this.shapeBase = 0;
    this.shapeStamp = 0;
    this.shapeView = null;
    this.gauntletIn = null;
    this.night = null;
    this.cored = null;
    this.againIn = null;
    this.pools = null;
    this.danced = null;
    this.relit = null;
    this.coresIn = null;
    this.cores = null;
    this.coreFor = null;
    this.coresShown = null;
    this.placedFor = null;
    this.torchGridIn = null;
    this.drew = null;
    this.gl = undefined;
    this.files = new Map();
    this.asked = new Set();
    this.atlas = { kx: 0, ky: 0, ids: [], tags: null, dirty: false };
    this.coarseIn = null;
    this.shown = null;
    this.pointerLit = false;
    this.tintIn = null;
    this.take = null;
    this.took = 0;
    this.takeTarget = null;
    this.shade = null;
    this.shaded = false;
    this.shadeMade = 0;
    this.timed = false;
    this.ms = null;
    this.trees = true;
    this.shadeAt = null;
    this.probed = null;
    this.probeStale = false;
    this.probeAsked = null;
  }

  setTrees(on) {
    on = !!on;
    if (on === this.trees) return;
    this.trees = on;
    this.atlas.ids.fill(null);
    this.coarseIn = null;
    this.shown = null;
  }

  lit(file) {
    if (this.trees || !file) return file;
    if (!file.bare) file.bare = withoutTrees(file);
    return file.bare;
  }

  ready() {
    if (this.gl === undefined) this.gl = this.start();
    if (this.gl && this.build?.done() === false) this.gl = null;
    return !!this.gl;
  }

  built() {
    if (this.u) return true;
    const made = this.build.done(), gl = this.gl;
    if (!made) {
      if (made === null && !this.buildWaits) { this.buildWaits = true; this.build.whenDone(() => this.drawn()); }
      return false;
    }
    gl.useProgram(made.light);
    this.u = Object.fromEntries(RELIEF_UNIFORMS.map((name) => [name, gl.getUniformLocation(made.light, name)]));
    RELIEF_TEXTURES.forEach((name, unit) => gl.uniform1i(this.u[name], unit));
    return true;
  }

  start() {
    const gl = this.context(this.canvas);
    if (!gl || !(gl.getParameter(gl.MAX_TEXTURE_SIZE) >= 3 * HEIGHTS.most)) return null;
    this.build = buildPrograms(gl, RELIEF_VERTEX, { light: RELIEF_FRAGMENT });
    gl.bindBuffer(gl.ARRAY_BUFFER, gl.createBuffer());
    gl.bufferData(gl.ARRAY_BUFFER, new Float32Array([-1, -1, 3, -1, -1, 3]), gl.STATIC_DRAW);
    gl.enableVertexAttribArray(0);
    gl.vertexAttribPointer(0, 2, gl.FLOAT, false, 0, 0);
    gl.pixelStorei(gl.UNPACK_ALIGNMENT, 1);
    this.most = Math.floor(gl.getParameter(gl.MAX_TEXTURE_SIZE) / HEIGHTS.most);
    this.layersMost = gl.getParameter(gl.MAX_ARRAY_TEXTURE_LAYERS) || 256;
    this.tex = {};
    RELIEF_TEXTURES.forEach((name, unit) => {
      gl.activeTexture(gl.TEXTURE0 + unit);
      const t = gl.createTexture(), target = RELIEF_ARRAYS.includes(name) ? gl.TEXTURE_2D_ARRAY : gl.TEXTURE_2D;
      gl.bindTexture(target, t);
      for (const k of [gl.TEXTURE_MIN_FILTER, gl.TEXTURE_MAG_FILTER]) gl.texParameteri(target, k, RELIEF_SMOOTH.includes(name) ? gl.LINEAR : gl.NEAREST);
      for (const k of [gl.TEXTURE_WRAP_S, gl.TEXTURE_WRAP_T]) gl.texParameteri(target, k, gl.CLAMP_TO_EDGE);
      if (target === gl.TEXTURE_2D_ARRAY) gl.texParameteri(target, gl.TEXTURE_MIN_FILTER, gl.LINEAR_MIPMAP_NEAREST);
      this.tex[name] = t;
    });
    gl.activeTexture(gl.TEXTURE0 + RELIEF_TEXTURES.indexOf("gauntlet"));
    gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MIN_FILTER, gl.LINEAR_MIPMAP_LINEAR);
    gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MAG_FILTER, gl.LINEAR);
    this.allocate(gl, 1, 1);
    this.texture(gl, "hc", gl.R16UI, 1, 1, gl.RED_INTEGER, gl.UNSIGNED_SHORT, new Uint16Array(1));
    this.texture(gl, "kc", gl.R8UI, 1, 1, gl.RED_INTEGER, gl.UNSIGNED_BYTE, new Uint8Array(1));
    for (const name of ["tintD", "tintA"]) this.texture(gl, name, gl.RGBA, 1, 1, gl.RGBA, gl.UNSIGNED_BYTE, TINT_NONE);
    this.texture(gl, "tintF", gl.RGBA, 1, 1, gl.RGBA, gl.UNSIGNED_BYTE, HAZE_NONE);
    this.texture(gl, "torchL", gl.RGBA32F, 1, 1, gl.RGBA, gl.FLOAT, new Float32Array(4));
    this.texture(gl, "torchI", gl.R32UI, 1, 1, gl.RED_INTEGER, gl.UNSIGNED_INT, new Uint32Array(1));
    this.texture(gl, "thinned", gl.RGBA, 1, 1, gl.RGBA, gl.UNSIGNED_BYTE, new Uint8Array(4));
    return gl;
  }

  texture(gl, name, format, w, h, type, kind, data) {
    gl.activeTexture(gl.TEXTURE0 + RELIEF_TEXTURES.indexOf(name));
    gl.texImage2D(gl.TEXTURE_2D, 0, format, w, h, 0, type, kind, data);
  }

  allocate(gl, kx, ky) {
    const S = HEIGHTS.most;
    this.texture(gl, "hf", gl.R16UI, kx * S, ky * S, gl.RED_INTEGER, gl.UNSIGNED_SHORT, null);
    this.texture(gl, "kf", gl.R8UI, kx * S, ky * S, gl.RED_INTEGER, gl.UNSIGNED_BYTE, null);
    this.atlas = { kx, ky, ids: new Array(kx * ky).fill(null), held: new Array(kx * ky).fill(null), tags: new Float32Array(kx * ky * 4), dirty: true, grounds: null };
  }

  placeGround(gl, at, sx, sy, file) {
    const S = HEIGHTS.most, a = this.atlas;
    if (!a.grounds) {
      this.texture(gl, "gf", gl.R16UI, a.kx * S, a.ky * S, gl.RED_INTEGER, gl.UNSIGNED_SHORT, null);
      a.grounds = new Array(a.kx * a.ky).fill(null);
    }
    if (a.grounds[at] === file) return;
    if (!file.ground) file.ground = file.layer ? { heights: file.layer } : groundOnly(file);
    gl.activeTexture(gl.TEXTURE0 + RELIEF_TEXTURES.indexOf("gf"));
    gl.texSubImage2D(gl.TEXTURE_2D, 0, sx * S, sy * S, file.n, file.n, gl.RED_INTEGER, gl.UNSIGNED_SHORT, file.ground.heights);
    a.grounds[at] = file;
  }

  want(instance, keys) {
    this.keepMost = Math.max(RELIEF.keep, keys.length + 1);
    for (const name of [...keys, "coarse"]) {
      const id = `${instance}/${name}`;
      if (this.files.has(id)) { const f = this.files.get(id); this.files.delete(id); this.files.set(id, f); continue; }
      if (this.asked.has(id)) continue;
      this.asked.add(id);
      Promise.resolve(this.bytes(`/api/heights/${id}.bin`)).then((buf) => decodeHeights(buf), () => null).then((file) => {
        this.asked.delete(id);
        this.files.set(id, file);
        if (this.files.size > this.keepMost) this.files.delete(this.files.keys().next().value);
        this.drawn();
      });
    }
  }

  place(gl, instance, keys, far = false) {
    const cr = keys.map((k) => k.split("_").map(Number)), span = (i) => (cr.length ? Math.max(...cr.map((p) => p[i])) - Math.min(...cr.map((p) => p[i])) + 1 : 1);
    const [kx, ky] = [Math.max(span(0), this.atlas.kx), Math.max(span(1), this.atlas.ky)];
    if (kx > this.most || ky > this.most) return null;
    if (kx !== this.atlas.kx || ky !== this.atlas.ky) this.allocate(gl, kx, ky);
    const S = HEIGHTS.most, a = this.atlas, inView = [];
    keys.forEach((key, k) => {
      const id = `${instance}/${key}`, [c, r] = cr[k];
      const source = far || !this.files.has(id) ? this.farCut(instance, c, r) : this.files.get(id), file = this.lit(source);
      if (!file) return;
      inView.push(file);
      const [sx, sy] = slotOf(c, r, a.kx, a.ky), at = sy * a.kx + sx, tag = tagOf(instance, c, r);
      this.placeGround(gl, at, sx, sy, source);
      if (a.ids[at] === tag && a.held[at] === file) return;
      gl.activeTexture(gl.TEXTURE0);
      gl.texSubImage2D(gl.TEXTURE_2D, 0, sx * S, sy * S, file.n, file.n, gl.RED_INTEGER, gl.UNSIGNED_SHORT, file.heights);
      gl.activeTexture(gl.TEXTURE1);
      gl.texSubImage2D(gl.TEXTURE_2D, 0, sx * S, sy * S, file.n, file.n, gl.RED_INTEGER, gl.UNSIGNED_BYTE, file.kinds);
      a.ids[at] = tag;
      a.held[at] = file;
      a.tags.set([tag, file.n, file.base, file.step], at * 4);
      a.dirty = true;
    });
    if (a.dirty) this.texture(gl, "tags", gl.RGBA32F, a.kx, a.ky, gl.RGBA, gl.FLOAT, a.tags);
    a.dirty = false;
    return inView;
  }

  farCut(instance, col, row) {
    const coarse = this.files.get(`${instance}/coarse`);
    if (!coarse) return null;
    if (!coarse.cuts) coarse.cuts = new Map();
    const key = `${col}_${row}`;
    if (!coarse.cuts.has(key)) coarse.cuts.set(key, farTile(coarse, col, row));
    return coarse.cuts.get(key);
  }

  ground(instance, n, w) {
    const file = this.files.get(`${instance}/coarse`);
    return file ? coarseHeight(file, n, w) : null;
  }

  coarseMap(gl, instance) {
    const file = this.lit(this.files.get(`${instance}/coarse`));
    if (!file) return { box: [0, 0, 0, 0], scale: [0, 0], top: -Infinity };
    if (this.coarseIn !== file) {
      this.texture(gl, "hc", gl.R16UI, file.w, file.h, gl.RED_INTEGER, gl.UNSIGNED_SHORT, file.heights);
      this.texture(gl, "kc", gl.R8UI, file.w, file.h, gl.RED_INTEGER, gl.UNSIGNED_BYTE, file.kinds);
      this.coarseIn = file;
    }
    return { box: [file.col, file.row, file.w, file.h], scale: [file.base, file.step], top: file.top };
  }

  paint({ instance, has, tileYards, at, width, height, hour, pointer, lantern: lamp = null, night = true, gauntlet = null, cloudShare = 0, tint = null, probe = null, torches = null, travellers = null, shaded = false, sun = 1, thinned = null, held = false }) {
    if (!this.ready() || !this.built() || !(width > 0) || !(height > 0)) return false;
    const corners = [[0, 0], [width, 0], [0, height], [width, height]].map(([x, y]) => at(x, y));
    const keys = reliefTiles(corners, tileYards, RELIEF.ring, has), world = viewMatrix(at, width, height);
    const far = Math.hypot(world[0], world[1]) >= RELIEF.farPx;
    this.want(instance, far || held ? [] : keys);
    const heldBack = !far && held && keys.some((key) => !this.files.has(`${instance}/${key}`));
    const gl = this.gl, files = this.place(gl, instance, keys, far);
    if (!files) return false;
    const light = oneLightAt(hour, night, sun), coarse = this.coarseMap(gl, instance);
    const high = Math.max(coarse.top, ...files.map((f) => f.top)), top = Number.isFinite(high) ? high : 0;
    const low = files.length ? Math.min(...files.map((f) => f.low)) : top;
    const on = light.lamp > 0 && lamp && lamp.h > 0 && lamp.perYard > 0 ? lamp : null;
    const plan = marchPlan(light.elevation, top - low), lantern = on ? [...on.foot, on.h] : [0, 0, 0];
    this.pointerLit = light.lamp > 0 || !!gauntlet;
    const g = gauntlet && this.placeGauntlet(gl, gauntlet.picture) ? gauntlet : null;
    this.night = { mix: light.mix, lamp: light.lamp, pool: on ? on.pool : null };
    const torch = on ? at(...on.foot) : null;
    this.underPointer = pointer ? this.groundShare(instance, at(...pointer), tileYards, files) : null;
    const ypx = Math.hypot(world[0], world[1]);
    const area = tint || null;
    const shapeKeys = reliefTiles(corners, tileYards, SHAPE.ring, has), inRing = new Set(shapeKeys);
    const pastRing = reliefTiles(corners, tileYards, SHAPE.ring + 1, has).filter((key) => !inRing.has(key));
    const middle = [32 - corners.reduce((s, c) => s + c.w, 0) / 4 / tileYards, 32 - corners.reduce((s, c) => s + c.n, 0) / 4 / tileYards];
    const bands = shapeBands(tileYards);
    const read = this.placeShapes(gl, instance, shapeKeys, { bands, at: shapeBlend(ypx, tileYards).at, around: pastRing, middle });
    const shaped = !!read;
    const tallest = Math.max(read && read.close ? SHAPE.tall : 0, ...shapeKeys.map((key) => this.shapeTall(`${instance}/${key}`)));
    const ns = corners.map((c) => c.n), ws = corners.map((c) => c.w), R = PLACED.reach, burn = light.lamp;
    const dusk = area && night !== false ? area.dusk || 0 : 0;
    const core = coreRadius(ypx), pad = Math.max(R, 3 * core);
    const box = { n: Math.max(...ns), w: Math.max(...ws), south: Math.max(...ns) - Math.min(...ns), east: Math.max(...ws) - Math.min(...ws) };
    const walking = travellers && night !== false && light.lamp > 0 ? travellersShown(ypx) : 0;
    const seen = walking * (R / ypx >= PLACED.leastPx ? 1 : coreBright(ypx));
    const walk = seen >= WALK_LIT.least ? { travellers, share: walking, ypx } : null;
    const { placed, grid, box: around, torchCount, reads } = this.placedIn(torches, instance, box, pad, light, area ? area.k : 0, dusk, walk);
    const view = JSON.stringify([instance, keys, files.length, files.filter((f) => f.far).length, world.map((v) => +v.toFixed(5)), width, height, Math.floor(hour * 60),
      this.pointerLit ? [...lantern.map(Math.round), ...(on ? on.tilt.map((v) => +v.toFixed(3)) : [])] : 0,this.coarseIn === this.lit(this.files.get(`${instance}/coarse`)), this.trees,
      ...(night !== false ? [] : ["no night"]), ...(g ? [g.picture, g.yards, ...g.at.map(Math.round)] : []),
      ...(shaped ? [this.shapeStamp, this.shapeBase, tallest, this.atlas.shapeSent.join()] : []), ...(cloudShare > 0 ? ["clouds", cloudShare] : []),
      ...(shaded ? ["shaded"] : []), ...(sun < 1 ? ["sun", +sun.toFixed(3)] : []), ...(thinned ? ["thinned", thinned.stamp] : []),
      ...(area ? [area.instance, area.stamp] : []), ...(torchCount ? [torches.stamp, torchCount] : []), ...(grid ? ["lit", +burn.toFixed(3)] : []),
      ...(walk ? ["walking", +walking.toFixed(3), reads] : [])]);
    const w = Math.max(1, Math.round(width * RELIEF.scale)), h = Math.max(1, Math.round(height * RELIEF.scale));
    if (this.pools?.view !== view) {
      const s = screenMatrix(world), kx = w / width, ky = h / height, toLight = [s[0] * kx, s[1] * ky, 0, s[3] * kx, s[4] * ky, 0, s[6] * kx, s[7] * ky, 1];
      const at = grid && R / ypx >= PLACED.leastPx ? placedPatches(placed, torches?.kinds || [], toLight, w, h, R) : [], b = patchBox(at);
      this.pools = { view, at, box: b && [b[0] / kx, b[1] / ky, b[2] / kx, b[3] / ky] };
    }
    const now = this.now(), step = Math.floor(now / CORE.step);
    this.againIn = (read && read.more) || heldBack ? SHAPE.frame : walk && travellers.lights.length ? CORE.step : null;
    this.coresIn = grid && !coreSteady(ypx) ? CORE.step - (now % CORE.step) : null;
    if (view === this.shown) {
      this.shadeAt = this.probe(gl, probe, view, width, height, held);
      this.flicker();
      return true;
    }
    this.shown = view;
    this.relit = true;
    this.danced = step;
    const t0 = this.now(), u = this.u;
    if (this.canvas.width !== w || this.canvas.height !== h) Object.assign(this.canvas, { width: w, height: h });
    gl.viewport(0, 0, w, h);
    gl.clearColor(0, 0, 0, 0);
    gl.clear(gl.COLOR_BUFFER_BIT);
    gl.uniform2f(u.size, width, height);
    gl.uniform2i(u.slots, this.atlas.kx, this.atlas.ky);
    gl.uniform1f(u.inst, instance);
    gl.uniform1f(u.T, tileYards);
    gl.uniform1f(u.top, top);
    gl.uniform1f(u.jump, RELIEF.roofJump);
    gl.uniformMatrix3fv(u.world, false, new Float32Array(world));
    gl.uniform4f(u.cbox, ...coarse.box);
    gl.uniform2f(u.cscale, ...coarse.scale);
    gl.uniform2f(u.dir, ...light.dir);
    gl.uniform1f(u.sinE, light.sin);
    gl.uniform1f(u.cosE, light.cos);
    gl.uniform1f(u.tanE, light.tan);
    gl.uniform1f(u.tanD, Math.tan(SKY_DISC * Math.PI / 180));
    gl.uniform1f(u.water, RELIEF.water);
    gl.uniform1f(u.bias, RELIEF.bias);
    gl.uniform1i(u.fineN, plan.fine.count);
    gl.uniform1i(u.coarseN, plan.coarse.count);
    gl.uniform1f(u.fineStep, plan.fine.step);
    gl.uniform1f(u.coarseStep, plan.coarse.step);
    gl.uniform1f(u.shadowA, RELIEF.shadow * light.shadow);
    gl.uniform3f(u.lamp, ...lantern);
    gl.uniform1f(u.lampOn, light.lamp);
    gl.uniform1f(u.lift, LAMP.lift);
    gl.uniform1f(u.lampY, on ? on.perYard : 1);
    gl.uniform1f(u.lampI, LAMP_CONE.I);
    gl.uniform2f(u.lampTilt, ...(on ? on.tilt : [0, 0]));
    gl.uniform2f(u.lampCos, Math.cos(LAMP_CONE.half * Math.PI / 180), Math.cos((LAMP_CONE.half - LAMP.soft) * Math.PI / 180));
    gl.uniform1i(u.shapeOn, shaped ? 1 : 0);
    gl.uniformMatrix3fv(u.screen, false, new Float32Array(screenMatrix(world)));
    gl.uniform1i(u.thinOn, thinned ? 1 : 0);
    if (thinned) {
      gl.activeTexture(gl.TEXTURE0 + RELIEF_TEXTURES.indexOf("thinned"));
      gl.texImage2D(gl.TEXTURE_2D, 0, gl.RGBA, gl.RGBA, gl.UNSIGNED_BYTE, thinned.canvas);
    }
    if (shaped) {
      gl.uniform1f(u.sReach, Math.min(SHAPE.reach, SHAPE.tall / Math.max(light.tan, 1e-3)));
      const each = new Float32Array(2 * SHAPE.bandsMost);
      bands.forEach((b, k) => each.set([b.far ? 1 : 0, Math.log2(b.step)], 2 * k));
      gl.uniform2fv(u.sBand, each);
      gl.uniform1f(u.sBase, this.shapeBase);
      gl.uniform1i(u.sN, SHAPE.steps);
      gl.uniform1f(u.sTop, (files.length ? Math.max(...files.map((f) => f.top)) : top) + tallest);
      gl.uniform1f(u.tanS, Math.tan(SHAPE.disc * Math.PI / 180));
      gl.uniform1f(u.rimA, SHAPE.rim);
      gl.uniform1f(u.rimY, SHAPE.rimYards);
      gl.uniform1f(u.awayA, SHAPE.away);
      gl.uniform1f(u.awayY, SHAPE.awayYards);
      gl.uniform1f(u.sJump, SHAPE.jump);
    }
    gl.uniform1i(u.gOn, g ? 1 : 0);
    if (g) {
      const spot = at(...g.at);
      gl.uniform4f(u.gBox, g.at[0] - g.hot[0], g.at[1] - g.hot[1], ...g.size);
      gl.uniform2f(u.gW, spot.n, spot.w);
      gl.uniform1f(u.gUp, g.yards);
      gl.uniform1f(u.gTexW, g.size[0]);
      gl.uniform1f(u.ypx, Math.hypot(world[0], world[1]));
    }
    if (torch) {
      gl.uniform2f(u.torchW, torch.n, torch.w);
      gl.uniform1f(u.torchUp, on.h);
    }
    const day = oneLightAt(SUN.NOON);
    gl.uniform1f(u.dayExp, day.exposure);
    gl.uniform1f(u.daySOne, day.s);
    gl.uniform3f(u.dayTint, ...day.tint);
    gl.uniform1f(u.exposure, light.exposure);
    gl.uniform1f(u.sOne, light.s);
    gl.uniform1f(u.bright, light.bright);
    gl.uniform1f(u.most, ONE_LIGHT.most);
    gl.uniform1f(u.halfOne, ONE_HALF);
    gl.uniform3f(u.tintOne, ...light.tint);
    gl.uniform1f(u.cloudK, cloudShare > 0 ? cloudShare : 0);
    if (area && area !== this.tintIn) {
      this.texture(gl, "tintD", gl.RGBA, area.w, area.h, gl.RGBA, gl.UNSIGNED_BYTE, area.d);
      this.texture(gl, "tintA", gl.RGBA, area.w, area.h, gl.RGBA, gl.UNSIGNED_BYTE, area.a);
      this.texture(gl, "tintF", gl.RGBA, area.w, area.h, gl.RGBA, gl.UNSIGNED_BYTE, area.f);
      this.tintIn = area;
    }
    gl.uniform1f(u.tintK, area ? area.k : 0);
    if (area) {
      gl.uniform4f(u.tintBox, area.col, area.row, area.per / area.w, area.per / area.h);
      gl.uniform1f(u.tintMost, area.most);
    }
    gl.uniform1f(u.torchOn, burn);
    gl.uniform1f(u.torchDusk, dusk);
    gl.uniform2i(u.torchCells, grid ? grid.gx : 0, grid ? grid.gy : 0);
    gl.uniform1i(u.torchPool, R / ypx >= PLACED.leastPx ? 1 : 0);
    this.cored = grid ? coreRgb(torches?.colours?.[0]) : null;
    this.coreFor = grid ? { key: view, core, bright: coreBright(ypx), steady: coreSteady(ypx) } : null;
    if (grid) {
      const W = PLACED.width;
      if (this.torchGridIn !== grid) {
        this.texture(gl, "torchL", gl.RGBA32F, W, grid.lights.length / (4 * W), gl.RGBA, gl.FLOAT, grid.lights);
        this.texture(gl, "torchI", gl.R32UI, W, grid.list.length / W, gl.RED_INTEGER, gl.UNSIGNED_INT, grid.list);
        this.torchGridIn = grid;
      }
      gl.uniform4f(u.torchBox, around.n, around.w, grid.cell, R);
      gl.uniform3f(u.torchCore, core, coreTime(step, coreSteady(ypx)), coreBright(ypx));
      gl.uniform3f(u.coreTint, ...this.cored);
    }
    gl.uniform1i(u.probeOn, 0);
    const cores = !!this.coreFor && !!this.doc;
    if (cloudShare > 0 || shaded || grid) this.drawTaking(gl, w, h, { take: cloudShare > 0, shade: shaded, cores });
    else gl.drawArrays(gl.TRIANGLES, 0, 3);
    this.took = cloudShare > 0 ? cloudShare : 0;
    this.shaded = shaded;
    if (cores) this.coresShown = `${view} ${step}`;
    this.shadeAt = this.probe(gl, probe, view, width, height, held);
    if (this.timed) {
      gl.readPixels(0, 0, 1, 1, gl.RGBA, gl.UNSIGNED_BYTE, new Uint8Array(4));
      this.ms = +(this.now() - t0).toFixed(2);
    }
    return true;
  }

  placedIn(torches, instance, view, pad, light, dayK = 0, dusk = 0, walk = null) {
    const key = torches ? JSON.stringify([torches.stamp, instance, light.lamp > 0, dayK > 0, dusk > 0]) : null, span = Math.max(view.south, view.east);
    const k = this.placedFor, same = (a, b) => Math.abs(a - b) <= 1e-6 * Math.max(Math.abs(a), Math.abs(b));
    const kept = k?.key === key && k.torches === torches && same(k.span, span) && same(k.pad, pad) && view.n <= k.box.n && view.w <= k.box.w
      && view.n - view.south >= k.box.n - k.box.south && view.w - view.east >= k.box.w - k.box.east;
    const m = span * PLACED.round, box = kept ? k.box : { n: view.n + m, w: view.w + m, south: view.south + 2 * m, east: view.east + 2 * m };
    const far = pad * PLACED_FAR, around = { n0: box.n + far, n1: box.n - box.south - far, w0: box.w + far, w1: box.w - box.east - far };
    const walkers = walk ? walk.travellers.within(instance, around).filter((l) => l[8] * WALK_LIT.shades >= 0.5)
      .map((l) => [...l.slice(0, 8), l[8] * walk.share]) : null;
    const walked = walkedOn(k?.walking || null, walkers, walk ? WALK_LIT.px * walk.ypx / RELIEF.scale : 0);
    if (kept && !walked) return k;
    const lit = kept ? k.placed.slice(0, k.torchCount) : torches ? torches.within(instance, around).filter((l) => placedOn(light, l[5], dayK, dusk) > 0) : [];
    const placed = walkers?.length ? lit.concat(walkers) : lit;
    const grid = placedGrid(placed, box, torches ? torches.colours : [], pad, torches ? torches.kinds : [], span);
    const reads = (k?.reads || 0) + (walked ? 1 : 0);
    return (this.placedFor = { key, torches, box, span, pad, placed, grid, torchCount: lit.length, walking: walkers, reads });
  }

  drawTaking(gl, w, h, { take = true, shade = false, cores = false, patches = null } = {}) {
    let t = this.takeTarget;
    const targets = [gl.COLOR_ATTACHMENT0, gl.COLOR_ATTACHMENT1, gl.COLOR_ATTACHMENT2, gl.COLOR_ATTACHMENT3];
    if (!t || t.w !== w || t.h !== h) {
      t = this.takeTarget = t || { fb: gl.createFramebuffer(), tex: targets.map(() => gl.createTexture()), targets, cores: gl.createFramebuffer() };
      gl.activeTexture(gl.TEXTURE0 + RELIEF_TEXTURES.length + 1);
      gl.bindFramebuffer(gl.FRAMEBUFFER, t.fb);
      t.tex.forEach((tex, k) => {
        gl.bindTexture(gl.TEXTURE_2D, tex);
        gl.texImage2D(gl.TEXTURE_2D, 0, gl.RGBA, w, h, 0, gl.RGBA, gl.UNSIGNED_BYTE, null);
        for (const p of [gl.TEXTURE_MIN_FILTER, gl.TEXTURE_MAG_FILTER]) gl.texParameteri(gl.TEXTURE_2D, p, gl.NEAREST);
        gl.framebufferTexture2D(gl.FRAMEBUFFER, targets[k], gl.TEXTURE_2D, tex, 0);
      });
      gl.drawBuffers(targets);
      gl.bindFramebuffer(gl.FRAMEBUFFER, t.cores);
      gl.framebufferTexture2D(gl.FRAMEBUFFER, gl.COLOR_ATTACHMENT0, gl.TEXTURE_2D, t.tex[3], 0);
      Object.assign(t, { w, h });
    }
    gl.bindFramebuffer(gl.FRAMEBUFFER, t.fb);
    if (patches) {
      gl.enable(gl.SCISSOR_TEST);
      for (const [x0, y0, x1, y1] of patches) {
        gl.scissor(x0, h - y1, x1 - x0, y1 - y0);
        gl.drawArrays(gl.TRIANGLES, 0, 3);
      }
      gl.disable(gl.SCISSOR_TEST);
    } else gl.drawArrays(gl.TRIANGLES, 0, 3);
    if (take) this.keepTarget(gl, 1, "take");
    if (shade) {
      this.keepTarget(gl, 2, "shade");
      this.shadeMade++;
    }
    if (cores) this.keepTarget(gl, 3, "cores");
    this.layTarget(gl, 0);
    gl.bindFramebuffer(gl.FRAMEBUFFER, null);
  }

  layTarget(gl, k) {
    const t = this.takeTarget;
    gl.bindFramebuffer(gl.READ_FRAMEBUFFER, t.fb);
    gl.bindFramebuffer(gl.DRAW_FRAMEBUFFER, null);
    gl.readBuffer(t.targets[k]);
    gl.blitFramebuffer(0, 0, t.w, t.h, 0, 0, t.w, t.h, gl.COLOR_BUFFER_BIT, gl.NEAREST);
  }

  keepTarget(gl, k, name) {
    this.layTarget(gl, k);
    const { w, h } = this.takeTarget, c = this[name] ||= this.doc.createElement("canvas");
    if (c.width !== w || c.height !== h) Object.assign(c, { width: w, height: h });
    const g = c.getContext("2d");
    g.globalCompositeOperation = "copy";
    g.drawImage(this.canvas, 0, 0);
    g.globalCompositeOperation = "source-over";
  }

  coresAt(gl, step) {
    const c = this.coreFor, key = `${c.key} ${step}`;
    if (!this.doc || key === this.coresShown) return false;
    this.coresShown = key;
    const t = this.takeTarget, u = this.u;
    gl.bindFramebuffer(gl.FRAMEBUFFER, t.cores);
    gl.viewport(0, 0, t.w, t.h);
    gl.uniform1i(u.coreOn, 1);
    gl.uniform3f(u.torchCore, c.core, coreTime(step, c.steady), c.bright);
    gl.drawArrays(gl.TRIANGLES, 0, 3);
    gl.uniform1i(u.coreOn, 0);
    this.keepTarget(gl, 3, "cores");
    this.layTarget(gl, 0);
    gl.bindFramebuffer(gl.FRAMEBUFFER, null);
    return true;
  }

  flicker() {
    if (!this.coreFor || !this.gl || this.coreFor.steady) {
      this.coresIn = null;
      return false;
    }
    const gl = this.gl, now = this.now(), step = Math.floor(now / CORE.step), pools = this.pools;
    this.coresIn = CORE.step - (now % CORE.step);
    const danced = pools.at.length > 0 && step !== this.danced;
    if (danced) {
      const t = this.takeTarget;
      this.danced = step;
      gl.uniform3f(this.u.torchCore, this.coreFor.core, coreTime(step), this.coreFor.bright);
      this.drawTaking(gl, t.w, t.h, { take: this.took > 0, patches: pools.at });
      if (this.relit !== true) this.relit = pools.box;
    }
    return this.coresAt(gl, step) || danced;
  }

  takeRelit() {
    const relit = this.relit;
    this.relit = null;
    return relit;
  }

  frame(draw) {
    this.drew = null;
    this.underPointer = null;
    this.shadeAt = null;
    draw();
  }

  probe(gl, spot, key, width, height, held = false) {
    this.probeStale = false;
    if (!spot || !(spot[0] >= 0 && spot[0] < width && spot[1] >= 0 && spot[1] < height)) return null;
    const w = this.canvas.width, h = this.canvas.height;
    const x = Math.min(w - 1, Math.floor(spot[0] * RELIEF.scale)), y = Math.min(h - 1, h - 1 - Math.floor(spot[1] * RELIEF.scale));
    this.probeTaken(gl);
    const last = this.probed, now = this.now(), share = last ? last.share : null;
    if (last && last.key === key && last.x === x && last.y === y) return last.share;
    if (held && last) return share;
    if (this.probeAsked || (last && now - last.at < PROBE_MS)) { this.probeStale = true; return share; }
    if (!this.probeTarget) {
      gl.activeTexture(gl.TEXTURE0 + RELIEF_TEXTURES.length);
      const t = gl.createTexture();
      gl.bindTexture(gl.TEXTURE_2D, t);
      gl.texImage2D(gl.TEXTURE_2D, 0, gl.RGBA, 1, 1, 0, gl.RGBA, gl.UNSIGNED_BYTE, null);
      const fb = gl.createFramebuffer();
      gl.bindFramebuffer(gl.FRAMEBUFFER, fb);
      gl.framebufferTexture2D(gl.FRAMEBUFFER, gl.COLOR_ATTACHMENT0, gl.TEXTURE_2D, t, 0);
      this.probeTarget = fb;
      this.probeBuffer = gl.createBuffer();
      gl.bindBuffer(gl.PIXEL_PACK_BUFFER, this.probeBuffer);
      gl.bufferData(gl.PIXEL_PACK_BUFFER, 4, gl.STREAM_READ);
      gl.bindBuffer(gl.PIXEL_PACK_BUFFER, null);
    }
    gl.bindFramebuffer(gl.FRAMEBUFFER, this.probeTarget);
    gl.viewport(-x, -y, w, h);
    gl.uniform1i(this.u.probeOn, 1);
    gl.drawArrays(gl.TRIANGLES, 0, 3);
    gl.bindBuffer(gl.PIXEL_PACK_BUFFER, this.probeBuffer);
    gl.readPixels(0, 0, 1, 1, gl.RGBA, gl.UNSIGNED_BYTE, 0);
    gl.bindBuffer(gl.PIXEL_PACK_BUFFER, null);
    const sync = gl.fenceSync(gl.SYNC_GPU_COMMANDS_COMPLETE, 0);
    gl.flush();
    gl.uniform1i(this.u.probeOn, 0);
    gl.bindFramebuffer(gl.FRAMEBUFFER, null);
    gl.viewport(0, 0, w, h);
    this.probeAsked = { key, x, y, at: now, sync };
    this.probeTaken(gl);
    if (this.probeAsked) this.probeStale = true;
    return this.probed ? this.probed.share : share;
  }

  probeTaken(gl) {
    const asked = this.probeAsked;
    if (!asked || gl.getSyncParameter(asked.sync, gl.SYNC_STATUS) !== gl.SIGNALED) return;
    const px = new Uint8Array(4);
    gl.bindBuffer(gl.PIXEL_PACK_BUFFER, this.probeBuffer);
    gl.getBufferSubData(gl.PIXEL_PACK_BUFFER, 0, px);
    gl.bindBuffer(gl.PIXEL_PACK_BUFFER, null);
    gl.deleteSync(asked.sync);
    this.probeAsked = null;
    this.probed = { key: asked.key, x: asked.x, y: asked.y, at: asked.at, share: px[0] / 255 };
  }

  groundShare(instance, spot, tileYards, files) {
    const c = 32 - spot.w / tileYards, r = 32 - spot.n / tileYards, col = Math.floor(c), row = Math.floor(r);
    const file = this.lit(this.files.get(`${instance}/${col}_${row}`));
    if (!file) return null;
    const h = edgeSurface(file, (c - col) * (file.n - 1), (r - row) * (file.n - 1)).h;
    const lo = Math.min(...files.map((f) => f.low)), hi = Math.max(...files.map((f) => f.top));
    return hi - lo > 1 ? Math.min(1, Math.max(0, (h - lo) / (hi - lo))) : 0.5;
  }

  shapeUrl(id, band = null) { return band && band.far ? null : renderShape(id); }

  shapeTall(id) { return 0; }

  shapeFull(id) { return null; }

  shapePicture(id, url = renderShape(id), rank = RANK.now) {
    let s = this.shapes.get(url);
    if (s) this.shapes.delete(url);
    else s = { img: null, ok: false, gone: false, sides: {}, bytes: 0, rank, asked: this.shapeAsk, fetch: null };
    s.rank = s.asked === this.shapeAsk ? Math.min(s.rank, rank) : rank;
    s.asked = this.shapeAsk;
    this.shapes.set(url, s);
    return s;
  }

  fetchShapes() {
    let busy = 0;
    const waiting = [];
    for (const [url, s] of this.shapes) {
      if (s.ok || s.gone) continue;
      if (s.asked < this.shapeAsk - 1) {
        if (s.fetch) s.fetch.stop.abort();
        s.fetch = null;
        this.shapes.delete(url);
      } else if (s.fetch && s.fetch.priority === "low" && s.rank < RANK.ahead) {
        s.fetch.stop.abort();
        s.fetch = null;
        waiting.push([url, s]);
      } else if (s.fetch) busy++;
      else waiting.push([url, s]);
    }
    waiting.sort((x, y) => x[1].rank - y[1].rank);
    for (const [url, s] of waiting.slice(0, Math.max(0, SHAPE.fetches - busy))) {
      const fetch = { stop: new AbortController(), priority: s.rank < RANK.ahead ? "high" : "low" };
      s.fetch = fetch;
      this.decode(url, fetch.priority, fetch.stop.signal).then((img) => {
        if (s.fetch !== fetch) return;
        s.fetch = null;
        if (img) Object.assign(s, { img, ok: true, bytes: 4 * img.width * img.height });
        else s.gone = true;
        if (s.rank < RANK.ahead) this.drawn();
        this.fetchShapes();
      });
    }
  }

  keepShapes(held) {
    let bytes = 0;
    for (const p of this.shapes.values()) bytes += shapeBytes(p);
    for (const [url, p] of this.shapes) {
      if (bytes <= this.shapeBudget) break;
      if (held.has(url) || p.asked >= this.shapeAsk - 1) continue;
      if (p.fetch) p.fetch.stop.abort();
      p.fetch = null;
      bytes -= shapeBytes(p);
      this.shapes.delete(url);
    }
  }

  shapeAtSide(s, side) {
    const w = s.img.width, n = w && s.img.height >= 2 * w ? 2 : 1;
    if (!w || w === side) return Array.from({ length: n }, (_, k) => ({ src: s.img, row: k * w }));
    if (side in s.sides) return s.sides[side];
    s.sides[side] = null;
    Promise.all(Array.from({ length: n }, (_, k) => this.resize(s.img, side, k * w)))
      .then((copies) => { s.sides[side] = copies.map((src) => ({ src, row: 0 })); s.bytes += 4 * side * side * n; this.drawn(); },
        () => { delete s.sides[side]; });
    return null;
  }

  sendSlice(gl, name, layer, level, side, slice, format) {
    gl.activeTexture(gl.TEXTURE0 + RELIEF_TEXTURES.indexOf(name));
    gl.pixelStorei(gl.UNPACK_COLORSPACE_CONVERSION_WEBGL, gl.NONE);
    if (slice.row) gl.pixelStorei(gl.UNPACK_SKIP_ROWS, slice.row);
    gl.texSubImage3D(gl.TEXTURE_2D_ARRAY, level, 0, 0, layer, side, side, 1, format, gl.UNSIGNED_BYTE, slice.src);
    if (slice.row) gl.pixelStorei(gl.UNPACK_SKIP_ROWS, 0);
  }

  shapeSlices(id, url, side, rank) {
    if (!url) return [];
    const s = this.shapePicture(id, url, rank);
    return s.gone ? [] : s.ok ? this.shapeAtSide(s, side) : null;
  }

  putShape(gl, layer, band, side, id, url, slices, at) {
    if (slices[0]) this.sendSlice(gl, "shapes", layer, band - this.shapeBase, side, slices[0], gl.RGBA);
    if (slices[1]) this.sendSlice(gl, "unders", layer, band - this.shapeBase, side, slices[1], gl.RED);
    this.shapeSent[layer][band] = { url, full2: slices.length ? 2 * ((url !== renderShape(id) && this.shapeFull(id)) || SHAPE.full) : 0,
      unders: slices.length > 1 ? 1 : 0, at };
    this.shapeStamp++;
  }

  shapeStore(gl, layers, base, bands, keep) {
    const was = this.shapeLayers || [], sent = this.shapeSent, n = bands.length, from = this.shapeBase;
    const old = { shapes: this.tex.shapes, unders: this.tex.unders };
    for (const [name, format] of [["shapes", gl.RGBA8], ["unders", gl.R8]]) {
      gl.activeTexture(gl.TEXTURE0 + RELIEF_TEXTURES.indexOf(name));
      const t = gl.createTexture();
      gl.bindTexture(gl.TEXTURE_2D_ARRAY, t);
      gl.texParameteri(gl.TEXTURE_2D_ARRAY, gl.TEXTURE_MIN_FILTER, gl.LINEAR_MIPMAP_NEAREST);
      gl.texParameteri(gl.TEXTURE_2D_ARRAY, gl.TEXTURE_MAG_FILTER, gl.LINEAR);
      for (const k of [gl.TEXTURE_WRAP_S, gl.TEXTURE_WRAP_T]) gl.texParameteri(gl.TEXTURE_2D_ARRAY, k, gl.CLAMP_TO_EDGE);
      gl.texStorage3D(gl.TEXTURE_2D_ARRAY, n - base, format, bands[base].side, bands[base].side, layers);
      this.tex[name] = t;
    }
    Object.assign(this, { shapeLayers: new Array(layers).fill(null), shapeSent: Array.from({ length: layers }, () => new Array(n).fill(null)),
      shapeLevels: n, shapeBase: base });
    this.shapeStamp++;
    const copies = [];
    keep.slice(0, layers).forEach((id, layer) => {
      this.shapeLayers[layer] = id;
      const i = was.indexOf(id), held = i < 0 ? null : sent[i];
      if (!held || held.length !== n) return;
      held.forEach((s, b) => {
        if (!s || b < base || b < from) return;
        this.shapeSent[layer][b] = s;
        if (s.full2 > 0) copies.push([i, layer, b, s.unders]);
      });
    });
    if (copies.length) {
      this.copyFrom ||= gl.createFramebuffer();
      gl.bindFramebuffer(gl.READ_FRAMEBUFFER, this.copyFrom);
      for (const name of ["shapes", "unders"]) {
        gl.activeTexture(gl.TEXTURE0 + RELIEF_TEXTURES.indexOf(name));
        for (const [i, layer, b, unders] of copies) {
          if (name === "unders" && !unders) continue;
          gl.framebufferTextureLayer(gl.READ_FRAMEBUFFER, gl.COLOR_ATTACHMENT0, old[name], b - from, i);
          gl.copyTexSubImage3D(gl.TEXTURE_2D_ARRAY, b - base, 0, 0, layer, 0, 0, bands[b].side, bands[b].side);
        }
      }
      gl.framebufferTextureLayer(gl.READ_FRAMEBUFFER, gl.COLOR_ATTACHMENT0, null, 0, 0);
      gl.bindFramebuffer(gl.READ_FRAMEBUFFER, null);
    }
    for (const t of Object.values(old)) gl.deleteTexture(t);
  }

  placeShapes(gl, instance, keys, { bands, at, around = [], middle = [32, 32] }) {
    const a = this.atlas, n = bands.length, now = this.now();
    this.shapeAsk++;
    const v = this.shapeView, joined = `${keys.join()} ${middle.map((x) => Math.round(16 * x)).join()}`, rezoomed = !v || Math.abs(at - v.at) > SHAPE.atNoise;
    if (rezoomed || v.keys !== joined) this.shapeView = { at: rezoomed ? at : v.at, keys: joined, since: now, way: v && rezoomed ? Math.sign(at - v.at) : v ? v.way : 0 };
    const still = now - this.shapeView.since >= SHAPE.still, way = still ? 0 : this.shapeView.way;
    const k = Math.max(0, Math.min(Math.floor(at), n - 1)), found = bands.findIndex((b) => b.far && b.side === SHAPE.far.resident);
    const resident = found < 0 ? n - 1 : Math.max(found, k), zoomed = at > k && k + 1 < n ? [k, k + 1] : [k];
    const ahead = way < 0 ? k - 1 : way > 0 ? zoomed.at(-1) + 1 : -1;
    const levels = [...new Set([...zoomed, resident, ...(ahead >= 0 && ahead < n ? [ahead] : [])])];
    const away = (key) => { const [c, r] = key.split("_").map(Number); return Math.hypot(c + 0.5 - middle[0], r + 0.5 - middle[1]); };
    const rank = (b, d, from) => from + (b === resident ? 0 : 4e5) + Math.round(d * 64) * 16 + (15 - b);
    const ids = keys.slice(0, this.layersMost).map((key) => `${instance}/${key}`), wants = [], wanted = [];
    ids.forEach((id, i) => {
      const d = away(keys[i]), mine = levels.map((b) => ({ id, b, url: this.shapeUrl(id, bands[b]), rank: rank(b, d, zoomed.includes(b) || b === resident ? RANK.now : RANK.ahead) }));
      if (!mine.some((w) => w.url)) return;
      wanted.push(id);
      for (const w of mine) if (w.url) this.shapePicture(id, w.url, w.rank);
      wants.push(...mine);
    });
    if (still) {
      const ask = (id, key, b) => { const url = this.shapeUrl(id, bands[b]); if (url) this.shapePicture(id, url, rank(b, away(key), RANK.still)); };
      const next = [k - 1, zoomed.at(-1) + 1].filter((b) => b >= 0 && b < n);
      ids.forEach((id, i) => { for (const b of next) ask(id, keys[i], b); });
      for (const key of around) for (const b of new Set([...zoomed, resident])) ask(`${instance}/${key}`, key, b);
      for (const [id, file] of this.files) {
        const [inst, key] = id.split("/");
        if (file && inst === String(instance) && key !== "coarse") ask(id, key, resident);
      }
    }
    const layerOf = new Map((this.shapeLayers || []).map((id, i) => [id, i]).filter(([id]) => id));
    const held = (layer) => Array.from({ length: n }, (_, b) => {
      const s = this.shapeSent[layer]?.[b];
      return s ? Math.min(1, Math.max(0, (now - s.at) / SHAPE.fade)) : 0;
    });
    let base = Math.min(...levels);
    for (const id of wanted) {
      const layer = layerOf.get(id), reads = layer == null ? [] : shapeWeights(at, held(layer));
      if (reads.length) base = Math.min(base, reads[0][0]);
    }
    const layers = Math.min(this.layersMost, SHAPE.chunk * Math.ceil(wanted.length / SHAPE.chunk));
    if (wanted.length && (!this.shapeLayers || this.shapeLevels !== n || this.shapeLayers.length < layers || base < this.shapeBase
      || (base > this.shapeBase && still))) {
      const had = this.shapeLayers ? this.shapeLayers.length : 0;
      this.shapeStore(gl, had < 2 * layers ? Math.max(layers, had) : layers, base, bands,
        [...wanted.filter((id) => layerOf.has(id)), ...wanted.filter((id) => !layerOf.has(id))]);
    }
    const slots = new Map(), mine = new Set(wanted);
    layerOf.clear();
    (this.shapeLayers || []).forEach((id, i) => { if (id) layerOf.set(id, i); });
    for (const id of wanted) {
      const [c, r] = id.split("/")[1].split("_").map(Number), [sx, sy] = slotOf(c, r, a.kx, a.ky), slotAt = sy * a.kx + sx;
      if (a.ids[slotAt] !== tagOf(instance, c, r)) continue;
      slots.set(id, slotAt);
      if (layerOf.has(id)) continue;
      const layer = this.shapeLayers.findIndex((had) => !had || !mine.has(had));
      layerOf.delete(this.shapeLayers[layer]);
      this.shapeLayers[layer] = id;
      this.shapeSent[layer] = new Array(n).fill(null);
      layerOf.set(id, layer);
    }
    let sending = 0, more = false;
    for (const w of wants.filter((x) => slots.has(x.id) && x.b >= this.shapeBase).sort((x, y) => x.rank - y.rank)) {
      const layer = layerOf.get(w.id), had = this.shapeSent[layer], side = bands[w.b].side;
      if (had[w.b] && had[w.b].url === w.url) continue;
      const slices = this.shapeSlices(w.id, w.url, side, w.rank);
      if (!slices) continue;
      const bytes = slices.length ? 4 * side * side + (slices.length > 1 ? side * side : 0) : 0;
      if (sending && sending + bytes > SHAPE.sendMB * 2 ** 20) { more = true; continue; }
      sending += bytes;
      const from = !had[w.b] && had.some((s, b) => s && b !== w.b && s.full2 > 0);
      this.putShape(gl, layer, w.b, side, w.id, w.url, slices, from ? now : -Infinity);
    }
    const words = new Uint32Array(4 * a.kx * a.ky);
    let close = false;
    for (const [id, slotAt] of slots) {
      const layer = layerOf.get(id), shares = held(layer), reads = shapeWeights(at, shares);
      if (!reads.length || !this.shapeSent[layer].some((s) => s && s.full2 > 0)) continue;
      reads.forEach(([b, share], i) => {
        const s = this.shapeSent[layer][b];
        words[4 * slotAt + i] = shapeWord(b, share, s.full2, s.unders);
        if (!bands[b].far && s.full2 > 0) close = true;
      });
      words[4 * slotAt + 3] = layer + 1;
      if (shares.some((h) => h > 0 && h < 1)) more = true;
    }
    if (!a.shapeSent || a.shapeSent.length !== words.length || a.shapeSent.some((x, i) => x !== words[i])) {
      a.shapeSent = words;
      a.shapeAt = Array.from({ length: a.kx * a.ky }, (_, i) => words[4 * i + 3]);
      this.texture(gl, "shapeAt", gl.RGBA32UI, a.kx, a.ky, gl.RGBA_INTEGER, gl.UNSIGNED_INT, words);
    }
    this.fetchShapes();
    this.keepShapes(new Set(this.shapeSent.flatMap((list) => list.filter((s) => s && s.url).map((s) => s.url))));
    return a.shapeAt.some((x) => x > 0) ? { close, more } : null;
  }

  placeGauntlet(gl, url) {
    let p = this.pictures.get(url);
    if (!p) {
      p = { img: this.picture(), ok: false };
      p.img.onload = () => { p.ok = true; this.drawn(); };
      p.img.src = url;
      this.pictures.set(url, p);
    }
    if (!p.ok) return false;
    if (this.gauntletIn !== url) {
      gl.activeTexture(gl.TEXTURE0 + RELIEF_TEXTURES.indexOf("gauntlet"));
      gl.texImage2D(gl.TEXTURE_2D, 0, gl.RGBA, gl.RGBA, gl.UNSIGNED_BYTE, p.img);
      gl.generateMipmap(gl.TEXTURE_2D);
      this.gauntletIn = url;
    }
    return true;
  }

  drawOn(ctx, w, h, cut = null, beside = [], box = null) {
    this.drew = "render";
    const t0 = this.now(), light = beside.length ? this.withBeside("canvas", beside, w) : this.canvas;
    const clear = this.clearSea(), g = clear ? this.copyOf(ctx, "work", "none", box) : ctx, [gw, gh] = clear ? [g.canvas.width, g.canvas.height] : [w, h];
    clipBox(g, box, () => {
      const op = g.globalCompositeOperation, fill = g.fillStyle;
      g.globalCompositeOperation = "multiply";
      g.drawImage(cut ? this.onGrey(cut(light)) : light, 0, 0, gw, gh);
      g.globalCompositeOperation = "color-dodge";
      g.fillStyle = `rgb(${ONE_LIGHT.dodge}, ${ONE_LIGHT.dodge}, ${ONE_LIGHT.dodge})`;
      g.fillRect(0, 0, gw, gh);
      g.globalCompositeOperation = op;
      g.fillStyle = fill;
      if (clear) {
        g.globalCompositeOperation = "destination-in";
        g.drawImage(ctx.canvas, 0, 0);
        g.globalCompositeOperation = "source-over";
      }
    });
    if (clear) clipBox(ctx, box, () => ctx.drawImage(g.canvas, 0, 0, w, h));
    this.nightOn(ctx, w, h, box);
    if (this.timed) this.drawMs = +(this.now() - t0).toFixed(2);
  }

  coresOn(ctx, w, h, beside = []) {
    this.parted(ctx, 1, beside.length ? (g, k) => { g.rect(-1e6, -1e6, 2e6, 2e6); beside.forEach((b) => b.part(g, k)); } : null, () => this.coresLaid(ctx, w, h));
    for (const b of beside) this.parted(ctx, 1, b.part, () => b.light.coresLaid(ctx, w, h));
  }

  coresLaid(ctx, w, h) {
    if (!this.cored || !this.cores) return;
    const op = ctx.globalCompositeOperation;
    ctx.globalCompositeOperation = "lighter";
    ctx.drawImage(this.cores, 0, 0, w, h);
    ctx.globalCompositeOperation = op;
  }

  parted(g, k, part, paint) {
    if (!part) return paint();
    g.save();
    g.beginPath();
    part(g, k);
    g.clip("evenodd");
    try { paint(); } finally { g.restore(); }
  }

  withBeside(name, beside, w) {
    const own = this[name];
    if (!own || !beside.some((b) => b.light[name])) return own || null;
    this.spare ||= {};
    const c = this.spare[`beside ${name}`] ||= this.doc.createElement("canvas");
    if (c.width !== own.width || c.height !== own.height) Object.assign(c, { width: own.width, height: own.height });
    const g = c.getContext("2d");
    g.globalCompositeOperation = "copy";
    g.drawImage(own, 0, 0);
    g.globalCompositeOperation = "source-over";
    for (const b of beside) {
      if (b.light[name]) this.parted(g, c.width / w, b.part, () => g.drawImage(b.light[name], 0, 0, c.width, c.height));
    }
    return c;
  }

  onGrey(light) {
    this.spare ||= {};
    const c = this.spare.cut ||= this.doc.createElement("canvas");
    if (c.width !== light.width || c.height !== light.height) Object.assign(c, { width: light.width, height: light.height });
    const g = c.getContext("2d");
    g.globalCompositeOperation = "source-over";
    g.fillStyle = `rgb(${ONE_LIGHT.dodge}, ${ONE_LIGHT.dodge}, ${ONE_LIGHT.dodge})`;
    g.fillRect(0, 0, c.width, c.height);
    g.drawImage(light, 0, 0, c.width, c.height);
    return c;
  }

  nightOn(ctx, w, h, box = null) {
    const n = this.night, id = n && n.mix > 0 ? this.nightFilter(n.mix) : null;
    if (!id) return;
    const g = this.copyOf(ctx, "night", `url(#${id})`, box), pool = n.pool, k = g.canvas.width / w;
    if (pool && pool.radius > 0) {
      const [x, y] = pool.at, lift = g.createRadialGradient(x * k, y * k, 0, x * k, y * k, pool.radius * k);
      pool.light.forEach((v, i) => lift.addColorStop(+(i / (LAMP.stops - 1)).toFixed(4), tint("black", +(LAMP.lift * n.lamp * v).toFixed(3))));
      clipBox(g, box, () => {
        g.globalCompositeOperation = "destination-out";
        g.fillStyle = lift;
        g.fillRect(0, 0, g.canvas.width, g.canvas.height);
        g.globalCompositeOperation = "source-over";
      });
    }
    clipBox(ctx, box, () => ctx.drawImage(g.canvas, 0, 0, w, h));
  }

  copyOf(ctx, name, filter = "none", box = null) {
    this.spare ||= {};
    const src = ctx.canvas, c = this.spare[name] ||= this.doc.createElement("canvas");
    if (c.width !== src.width || c.height !== src.height) Object.assign(c, { width: src.width, height: src.height });
    const g = c.getContext("2d");
    clipBox(g, box, () => {
      g.globalCompositeOperation = "copy";
      g.filter = filter;
      g.drawImage(src, 0, 0);
      g.filter = "none";
      g.globalCompositeOperation = "source-over";
    });
    return g;
  }

  nightFilter(mix) {
    const m = nightMatrix(Math.round(mix * 100) / 100);
    return this.colourFilter(`relief-night-${Math.round(mix * 100)}`, [...m.map((row) => [...row.map((v) => +v.toFixed(5)), 0, 0]).flat(), 0, 0, 0, 1, 0]);
  }

  colourFilter(id, values) {
    if (!this.doc?.createElementNS) return null;
    if (this.doc.getElementById(id)) return id;
    const ns = "http://www.w3.org/2000/svg", make = (tag, attrs) => {
      const el = this.doc.createElementNS(ns, tag);
      for (const [k, v] of Object.entries(attrs)) el.setAttribute(k, v);
      return el;
    };
    if (!this.svg) {
      this.svg = make("svg", { width: "0", height: "0", style: "position: absolute", "aria-hidden": "true" });
      this.doc.body.append(this.svg);
    }
    const filter = make("filter", { id, "color-interpolation-filters": "sRGB" });
    filter.append(make("feColorMatrix", { type: "matrix", values: values.join(" ") }));
    this.svg.append(filter);
    return id;
  }
}

if (typeof module === "object") {
  module.exports = { HEIGHTS, KIND, RELIEF, farTile,ONE_LIGHT, ONE_HALF, oneLightAt, oneLightV, oneShadow, oneCloudTake, oneLightLevel, oneLightRgb, AREA_NONE, nightMatrix, oneLightPixel, groundOnly, groundOf, RELIEF_TEXTURES,
    RELIEF_SMOOTH, RELIEF_ARRAYS,
    TORCH, torchV, torchShadow, screenMatrix, gauntletHides, SHAPE, RANK, renderShape, shapeHeight, shapesRead, shapeSide, shapeBands, shapeBlend, shapeRead, shapeWeights, shapeWord, shapeSteps, shapeCone, shapeHides, shapeShadowAt, shadedFar, PLACED, PLACED_FAR, PLACED_NONE, glFloat, placedOn, placedFalloff, PATCH, WALK_LIT, walkedOn, placedPatches, patchBox, clipBox,
    placedLift, placedGrid, CORE, coreRadius, coreBright, coreSteady, coreRgb,
    decodeHeights, withoutTrees, heightAt, kindAt, coarseHeight, gridAround, edgeSurface, aboveShare, lean, reliefNormal, tilePoint, reliefTiles, reliefWanted, reliefLight, marchPlan, coneShare, reliefShadow,
    lanternKeep, viewMatrix, slotOf, tagOf, RELIEF_VERTEX, RELIEF_FRAGMENT, RELIEF_GL, RELIEF_UNIFORMS, PROBE_MS, PROGRAM_POLL_MS, programsBuilt, buildPrograms, Relief };
}
