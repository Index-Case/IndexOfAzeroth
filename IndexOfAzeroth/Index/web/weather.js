// The Index of Azeroth. Copyright 2026 Index Case <indexofazeroth@pm.me>. PolyForm Strict 1.0.0, see LICENSE.md.
"use strict";

const WEATHER_KINDS = { 1: "rain", 2: "snow", 3: "sandstorm", 4: "other" };

function zoneOfMap(id, maps) {
  let cur = id;
  for (let i = 0; i < 5 && maps[cur]?.type > 3; i++) cur = maps[cur].parent;
  return maps[cur]?.type === 3 ? +cur : null;
}

function weatherHere(status, state, live, maps) {
  const n = status?.nums;
  if (!live || !n || !state?.map) return null;
  const kind = WEATHER_KINDS[n.weatherKind];
  if (!kind || n.weatherStrength == null || n.weatherMap == null) return null;
  const zone = zoneOfMap(n.weatherMap, maps);
  if (zone == null || zone !== zoneOfMap(state.map, maps)) return null;
  return { kind, strength: Math.max(0, Math.min(1, n.weatherStrength / 1000)), zone };
}

const WEATHER_LOOKS = { rain: { rain: true }, other: { rain: false } };
const WEATHER_MASK = { feather: 200, scale: 0.25, cover: 0.6, band: 0.15 };

function weatherCover(share) {
  const { cover, band } = WEATHER_MASK, t = Math.min(1, Math.max(0, (share - cover + band) / (2 * band)));
  return t * t * (3 - 2 * t);
}

function weatherFeather(data) {
  for (let i = 3; i < data.length; i += 4) {
    const t = Math.min(1, (data[i] / 255) * 2);
    data[i] = Math.round(255 * t * t * (3 - 2 * t));
  }
}

class LandWeather {
  constructor({ storm, shape, canvas }) {
    Object.assign(this, { storm, shape, canvas });
    this.maskCanvas = null;
    this.maskKey = null;
    this.tinted = null;
    this.cells = new Map();
    this.job = null;
  }

  cellPicture(g, zone, own) {
    const key = `${g.runs.length}|${g.rows}|${g.cols}|${g.zones.join(",")}|${zone}|${own}`;
    let c = this.cells.get(key);
    if (c) return c;
    c = this.canvas(g.cols, g.rows);
    const x = c.getContext("2d"), img = x.createImageData(g.cols, g.rows), cells = areaGrid(g);
    for (let i = 0; i < cells.length; i++) {
      const z = g.zones[cells[i]];
      if (own ? z === zone : z && z !== zone) img.data.set([255, 255, 255, 255], i * 4);
    }
    x.putImageData(img, 0, 0);
    this.cells.set(key, c);
    return c;
  }

  mask(zone, at) {
    const key = `${zone}|${at.key}`;
    if (key === this.maskKey && this.made) return this.made;
    const m = at.maps[zone];
    if (!m?.world) return null;
    const k = WEATHER_MASK.scale, w = Math.ceil(at.width * k), h = Math.ceil(at.height * k);
    if (!this.shapeCanvas || this.shapeCanvas.width !== w || this.shapeCanvas.height !== h) {
      this.shapeCanvas = this.canvas(w, h);
      this.maskCanvas = this.canvas(w, h);
    }
    const g = this.shapeCanvas.getContext("2d");
    g.setTransform(1, 0, 0, 1, 0, 0);
    g.globalCompositeOperation = "source-over";
    g.clearRect(0, 0, w, h);
    at.place(g, k);
    const spot = (n, w) => worldToFrac(at.display, { inst: m.instance, n, w }, at.maps);
    const box = [Infinity, Infinity, -Infinity, -Infinity];
    const rect = (top, left, bottom, right, grow = true) => {
      const a = spot(top, left), b = spot(bottom, right);
      if (!a || !b) return null;
      const r = [a[0] * at.size.w, a[1] * at.size.h, (b[0] - a[0]) * at.size.w, (b[1] - a[1]) * at.size.h], t = g.getTransform();
      if (!grow) return r;
      for (const [x, y] of [[r[0], r[1]], [r[0] + r[2], r[1]], [r[0], r[1] + r[3]], [r[0] + r[2], r[1] + r[3]]]) {
        const p = t.transformPoint({ x, y });
        box[0] = Math.min(box[0], p.x); box[1] = Math.min(box[1], p.y); box[2] = Math.max(box[2], p.x); box[3] = Math.max(box[3], p.y);
      }
      return r;
    };
    const capitals = Object.values(at.maps).filter((c) => c.areas && c.world && c.instance === m.instance);
    const named = capitals.some((c) => c.areas.zones.includes(zone));
    g.imageSmoothingEnabled = true;
    if (m.highlight) {
      const img = this.shape(zone), r = rect(m.world.top, m.world.left, m.world.bottom, m.world.right);
      if (!img || !r) return null;
      g.drawImage(img, r[0], r[1], r[2], r[2]);
    } else if (!named) {
      const r = rect(m.world.top, m.world.left, m.world.bottom, m.world.right);
      if (r) { g.fillStyle = tint("black"); g.fillRect(...r); }
    }
    for (const c of capitals) {
      const a = c.areas, r = rect(c.world.top, c.world.left, c.world.top - a.rows * a.cell, c.world.left - a.cols * a.cell, a.zones.includes(zone));
      if (!r) continue;
      g.globalCompositeOperation = "destination-out";
      g.drawImage(this.cellPicture(a, zone, false), ...r);
      g.globalCompositeOperation = "source-over";
      g.drawImage(this.cellPicture(a, zone, true), ...r);
    }
    const t = g.getTransform(), across = at.maps[at.display]?.world;
    const band = WEATHER_MASK.feather * Math.hypot(t.a, t.b) * at.size.w / (across ? Math.abs(across.left - across.right) : 1);
    const out = this.maskCanvas.getContext("2d");
    out.setTransform(1, 0, 0, 1, 0, 0);
    out.globalCompositeOperation = "copy";
    out.filter = `blur(${(band / 2).toFixed(1)}px)`;
    out.drawImage(this.shapeCanvas, 0, 0);
    out.filter = "none";
    out.globalCompositeOperation = "source-over";
    const px = out.getImageData(0, 0, w, h);
    weatherFeather(px.data);
    out.putImageData(px, 0, 0);
    g.setTransform(1, 0, 0, 1, 0, 0);
    if (!(box[2] > box[0])) return null;
    const cover = weatherCover(Math.max((box[2] - box[0]) / w, (box[3] - box[1]) / h));
    if (cover > 0) {
      out.globalAlpha = cover;
      out.fillStyle = tint("black");
      out.fillRect(0, 0, w, h);
      out.globalAlpha = 1;
    }
    this.made = { canvas: this.maskCanvas, cover, box: cover > 0 ? [0, 0, at.width, at.height]
      : [Math.max(0, (box[0] - band) / k), Math.max(0, (box[1] - band) / k), Math.min(at.width, (box[2] + band) / k),
        Math.min(at.height, (box[3] + band) / k)].map(Math.round) };
    this.maskKey = key;
    return this.made;
  }

  see(weather, view, gate, tone, mask) {
    const look = weather && WEATHER_LOOKS[weather.kind];
    if (!look || !view || !mask) return this.clear();
    if (weather.fading) gate = 0;
    this.job = { strength: weather.strength, mul: tone ? tone.mul : [1, 1, 1] };
    this.storm.see({ ...view, level: 1, any: true, maelstrom: null, strength: weather.strength, dark: tone ? tone.none : 1,
      gate, lightning: false, rain: look.rain, mask });
  }

  held(weather) {
    const last = this.last, showing = this.storm.zoomIn > 0.002;
    if (weather && (!last || !showing || last.zone === weather.zone)) {
      if (!showing) this.storm.zoomIn = 0;
      this.last = weather;
      return weather;
    }
    if (last && showing) return (this.last = { ...last, fading: true });
    this.last = null;
    return null;
  }

  clear() {
    this.job = null;
    this.storm.see(null);
  }

  draw(ctx, now, dpr) {
    const j = this.job, mask = this.storm.view?.mask;
    if (!j || !mask) return false;
    const m = mask.canvas, [x0, y0, x1, y1] = mask.box, sx = m.width / ctx.canvas.width, sy = m.height / ctx.canvas.height;
    if (!(x1 > x0 && y1 > y0)) return false;
    if (!this.tinted || this.tinted.width !== m.width || this.tinted.height !== m.height) this.tinted = this.canvas(m.width, m.height);
    const t = this.tinted.getContext("2d");
    t.globalCompositeOperation = "copy";
    t.drawImage(m, 0, 0);
    t.globalCompositeOperation = "source-in";
    t.fillStyle = `rgb(${j.mul.map((v) => Math.round(v * 255)).join(", ")})`;
    t.fillRect(0, 0, m.width, m.height);
    ctx.save();
    ctx.setTransform(1, 0, 0, 1, 0, 0);
    ctx.globalAlpha = Math.min(1, j.strength * this.storm.zoomIn);
    ctx.globalCompositeOperation = "multiply";
    ctx.drawImage(this.tinted, x0 * sx, y0 * sy, (x1 - x0) * sx, (y1 - y0) * sy, x0, y0, x1 - x0, y1 - y0);
    ctx.restore();
    this.storm.draw(ctx, now, dpr);
    return true;
  }

  next(now) {
    return this.job ? this.storm.next(now) : null;
  }
}

if (typeof module === "object") module.exports = { WEATHER_KINDS, WEATHER_LOOKS, WEATHER_MASK, weatherFeather, weatherCover, zoneOfMap, weatherHere, LandWeather };
