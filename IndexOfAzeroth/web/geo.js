// The Index of Azeroth. Copyright 2026 Index Case <indexofazeroth@pm.me>. PolyForm Strict 1.0.0, see LICENSE.md.
"use strict";

const toFrac = (b, n, w) => [(b.left - w) / (b.left - b.right), (b.top - n) / (b.top - b.bottom)];
function placeIn(b, n, w, x0 = 0, y0 = 0, x1 = 1, y1 = 1) {
  const [u, v] = toFrac(b, n, w);
  return [x0 + u * (x1 - x0), y0 + v * (y1 - y0)];
}
const toWorld = (b, fx, fy) => ({ n: b.top - fy * (b.top - b.bottom), w: b.left - fx * (b.left - b.right) });
const onMap = (cont, [n, w]) => toFrac(cont.w, n, w);

function mapYards(id, maps = app.maps) {
  const w = maps[id]?.world;
  return w ? { w: Math.abs(w.left - w.right), h: Math.abs(w.top - w.bottom) } : null;
}
function yardsBetween(mapId, a, b, maps = app.maps) {
  const yd = mapYards(mapId, maps);
  return yd ? Math.hypot((b.x - a.x) * yd.w, (b.y - a.y) * yd.h) : null;
}

function continentOf(id, maps = app.maps) {
  let cur = id;
  for (let i = 0; i < 5 && maps[cur] && maps[cur].type > 2; i++) cur = maps[cur].parent;
  return maps[cur]?.type === 2 && maps[cur].instance === maps[id]?.instance ? cur : null;
}
function continentMap(inst, maps = app.maps) {
  for (const [id, m] of Object.entries(maps)) if (m.type === 2 && m.instance === inst && m.world) return +id;
  return null;
}
function continentMapOf(instance, maps = app.maps) {
  let id = continentMap(instance, maps);
  if (id == null) {
    let most = 0;
    for (const [k, m] of Object.entries(maps)) {
      const w = m.world;
      if (m.type !== 3 || m.instance !== instance || !w || !m.parent || m.tilesOnly) continue;
      const size = Math.abs((w.left - w.right) * (w.top - w.bottom));
      if (size > most) { most = size; id = +k; }
    }
  }
  return id == null ? null : { id, w: maps[id].world };
}

function regionOf(inst, maps = app.maps) {
  for (const [id, m] of Object.entries(maps)) {
    const r = m.regions?.find((x) => x.instance === inst);
    if (r) return { ...r, map: +id };
  }
  return null;
}
function fromWorldMap(inst, u, v, maps = app.maps) {
  const r = regionOf(inst, maps);
  if (!r) return null;
  const [x0, y0, x1, y1] = r.ui;
  return { inst, ...toWorld(r.world, (u - x0) / (x1 - x0), (v - y0) / (y1 - y0)) };
}
function acrossTo(inst, p, maps = app.maps) {
  if (p.inst === inst) return p;
  const a = regionOf(p.inst, maps), b = regionOf(inst, maps);
  if (!a || !b || a.map !== b.map) return null;
  return fromWorldMap(inst, ...placeIn(a.world, p.n, p.w, ...a.ui), maps);
}
function worldYards(world, maps = app.maps) {
  const rs = maps[world]?.regions || [];
  if (!rs.length) return null;
  const mean = (f) => rs.reduce((s, r) => s + f(r), 0) / rs.length;
  return { w: mean((r) => Math.abs(r.world.left - r.world.right) / (r.ui[2] - r.ui[0])),
           h: mean((r) => Math.abs(r.world.top - r.world.bottom) / (r.ui[3] - r.ui[1])) };
}
const worldAt = (yd, u, v) => ({ n: (0.5 - v) * yd.h, w: (0.5 - u) * yd.w });
const worldSpot = (yd, n, w) => [0.5 - w / yd.w, 0.5 - n / yd.h];

function convertFrac(from, to, fx, fy, maps = app.maps, across = false) {
  if (from === to) return [fx, fy];
  const src = maps[from], dst = maps[to], a = src?.world;
  if (!a || !dst) return [NaN, NaN];
  const p = toWorld(a, fx, fy);
  if (dst.world) return worldToFrac(to, { inst: src.instance, ...p }, maps, across) || [NaN, NaN];
  const region = dst.regions?.find((r) => r.instance === src.instance);
  return region ? placeIn(region.world, p.n, p.w, ...region.ui) : [NaN, NaN];
}
function fracToWorld(mapId, fx, fy, maps = app.maps, across = false) {
  const m = maps[mapId];
  if (!m) return null;
  if (m.world) {
    const p = { inst: m.instance, ...toWorld(m.world, fx, fy) }, r = across && regionOf(m.instance, maps);
    return r ? fracToWorld(r.map, ...placeIn(r.world, p.n, p.w, ...r.ui), maps) : p;
  }
  let best = null, bestD = Infinity;
  for (const r of m.regions || []) {
    const [x0, y0, x1, y1] = r.ui;
    const d = Math.hypot(Math.max(x0 - fx, 0, fx - x1), Math.max(y0 - fy, 0, fy - y1));
    if (d < bestD) { bestD = d; best = { inst: r.instance, ...toWorld(r.world, (fx - x0) / (x1 - x0), (fy - y0) / (y1 - y0)) }; }
  }
  return best;
}
function worldToFrac(mapId, p, maps = app.maps, across = false) {
  const m = maps[mapId];
  if (!m || !p) return null;
  if (m.world) {
    const q = m.instance === p.inst ? p : across ? acrossTo(m.instance, p, maps) : null;
    return q ? placeIn(m.world, q.n, q.w) : null;
  }
  const r = m.regions?.find((x) => x.instance === p.inst);
  return r ? placeIn(r.world, p.n, p.w, ...r.ui) : null;
}
function mapOn(from, to, maps = app.maps, across = false) {
  const a = maps[from], b = maps[to];
  if (!a || !b) return null;
  if (a.world && b.world) {
    const c0 = worldToFrac(to, { inst: a.instance, n: a.world.top, w: a.world.left }, maps, across);
    const c1 = worldToFrac(to, { inst: a.instance, n: a.world.bottom, w: a.world.right }, maps, across);
    return c0 && c1 ? [...c0, ...c1] : null;
  }
  if (a.world) {
    const r = b.regions?.find((x) => x.instance === a.instance);
    return r ? [...placeIn(r.world, a.world.top, a.world.left, ...r.ui), ...placeIn(r.world, a.world.bottom, a.world.right, ...r.ui)] : null;
  }
  const r = b.world && a.regions?.find((x) => x.instance === b.instance);
  if (!r) return null;
  const [x0, y0, x1, y1] = r.ui;
  const corner = (fx, fy) => { const p = toWorld(r.world, (fx - x0) / (x1 - x0), (fy - y0) / (y1 - y0)); return toFrac(b.world, p.n, p.w); };
  return [...corner(0, 0), ...corner(1, 1)];
}

const ZONE_EDGE = 0.1;
function zoneHolding(p, maps = app.maps, mine = app.state?.map) {
  let best = null, bestKey = null;
  for (const [id, m] of Object.entries(maps)) {
    const w = m.world;
    if (m.type !== 3 || !w || m.instance !== p.inst || m.tilesOnly || (!m.parent && +id !== mine)) continue;
    const [fx, fy] = toFrac(w, p.n, p.w);
    if (fx < 0 || fx > 1 || fy < 0 || fy > 1) continue;
    const key = [Math.min(fx, 1 - fx, fy, 1 - fy) < ZONE_EDGE ? 1 : 0, Math.abs((w.left - w.right) * (w.top - w.bottom))];
    if (!bestKey || key[0] < bestKey[0] || key[0] === bestKey[0] && key[1] < bestKey[1]) { best = +id; bestKey = key; }
  }
  return best;
}

const areaCells = new WeakMap();
function areaZone(m, p) {
  const g = m?.areas, w = m?.world;
  if (!g || !w || m.instance !== p.inst) return null;
  const r = Math.floor((w.top - p.n) / g.cell), c = Math.floor((w.left - p.w) / g.cell);
  if (!(r >= 0 && r < g.rows && c >= 0 && c < g.cols)) return null;
  let cells = areaCells.get(g);
  if (!cells) {
    cells = new Uint8Array(g.rows * g.cols);
    for (let i = 0, at = 0; i + 1 < g.runs.length; at += g.runs[i + 1], i += 2) cells.fill(g.runs[i], at, at + g.runs[i + 1]);
    areaCells.set(g, cells);
  }
  return g.zones[cells[r * g.cols + c]] || null;
}
function zoneOfArea(p, maps = app.maps) {
  let other = null;
  for (const [id, m] of Object.entries(maps)) {
    const z = m.areas ? areaZone(m, p) : null;
    if (z === +id) return z;
    other ??= z;
  }
  return other;
}

function cityZone(id, maps = app.maps) {
  const c = maps[id], b = c?.world;
  if (c?.type !== 3 || c.highlight || !b) return null;
  let best = null, most = 0, smallest = Infinity;
  for (const [k, m] of Object.entries(maps)) {
    const w = m.world;
    if (m.type !== 3 || !m.highlight || !w || m.instance !== c.instance) continue;
    const across = Math.min(b.left, w.left) - Math.max(b.right, w.right), down = Math.min(b.top, w.top) - Math.max(b.bottom, w.bottom);
    const held = Math.max(0, across) * Math.max(0, down), size = Math.abs((w.left - w.right) * (w.top - w.bottom));
    if (held > most || (held && held === most && size < smallest)) { best = +k; most = held; smallest = size; }
  }
  return best;
}

if (typeof module === "object") {
  module.exports = { toFrac, placeIn, toWorld, onMap, mapYards, yardsBetween, continentOf, continentMap, continentMapOf, regionOf,
                     fromWorldMap, acrossTo, worldYards, worldAt, worldSpot, convertFrac, fracToWorld, worldToFrac, mapOn, ZONE_EDGE, zoneHolding,
                     areaZone, zoneOfArea, cityZone };
}
