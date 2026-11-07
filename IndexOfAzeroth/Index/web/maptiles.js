// The Index of Azeroth. Copyright 2026 Index Case <indexofazeroth@pm.me>. PolyForm Strict 1.0.0, see LICENSE.md.
"use strict";

const MAPTILES_MAX = 400;
const MAPTILES_MID_MAX = 800;
const MAPTILES_FULL_PX = 300;
const MAPTILES_FAR_COUNT = 300;
const MAPTILES_SKIRT = 0.5;
const MAPTILES_SAMPLE = 32;
const MAPTILES_SEA_NEAR = 24;
const MAPTILES_SEAS = 64;
const MAPTILES_SEA = [38, 57, 61];
const MAPTILES_SMOOTH = 0.02;
const MAPTILES_SIDES = [[0, -1], [1, 0], [0, 1], [-1, 0]];
const MAPTILES_CORNERS = [[-1, -1], [1, -1], [1, 1], [-1, 1]];

class MapTiles {
  constructor({ picture, drawn, max = MAPTILES_MAX, midMax = MAPTILES_MID_MAX, ink, address }) {
    Object.assign(this, { picture, drawn, max, midMax, ink, address });
    this.render = { version: null, instances: {} };
    this.rendered = new Map();
    this.boxes = new Map();
    this.mid = { version: null, keys: new Map() };
    this.floors = { version: null, instances: {} };
    this.images = new Map();
    this.seas = [];
  }

  setFloors(tiles) {
    this.floors = tiles?.instances ? tiles : { version: null, instances: {} };
    this.forget("floor");
  }

  setRender(index) {
    this.render = index?.instances ? index : { version: null, instances: {} };
    this.rendered = new Map(Object.entries(this.render.instances).map(([inst, keys]) => [String(inst), new Set(keys || [])]));
    this.boxes = new Map();
    this.forget("render");
  }

  setMid(version, lists) {
    this.mid = { version: version ?? null, keys: new Map(Object.entries(lists || {}).map(([inst, keys]) => [String(inst), new Set(keys || [])])) };
    this.forget("mid");
  }

  hasRender(instance, key) { return !!this.rendered.get(String(instance))?.has(key); }
  renders(instance) { return !!this.rendered.get(String(instance))?.size; }
  renderBox(instance) {
    const keys = this.rendered.get(String(instance));
    if (!keys?.size) return null;
    if (!this.boxes.has(String(instance))) {
      const cr = [...keys].map((k) => k.split("_").map(Number)), cs = cr.map((p) => p[0]), rs = cr.map((p) => p[1]);
      this.boxes.set(String(instance), [Math.min(...cs), Math.min(...rs), Math.max(...cs), Math.max(...rs)]);
    }
    return this.boxes.get(String(instance));
  }
  hasMid(instance, key) { return !!this.mid.keys.get(String(instance))?.has(key); }

  level(px, count, farPx = 0) {
    if (count > MAPTILES_FAR_COUNT || (farPx > 0 && px <= farPx)) return "far";
    return px > MAPTILES_FULL_PX ? "full" : "mid";
  }
  hasFloor(instance, key) { return !!this.floors.instances?.[instance]?.[key]; }

  has(instance) {
    return !!this.rendered.get(String(instance))?.size || Object.keys(this.floors.instances?.[instance] || {}).length > 0;
  }

  image(instance, key, level = "full") {
    const kind = this.hasRender(instance, key) ? "render" : this.hasFloor(instance, key) ? "floor" : null;
    if (!kind) return null;
    const want = level === "mid" && kind === "render" && this.hasMid(instance, key) ? "mid" : kind;
    const entry = this.load(want, instance, key);
    if (entry.ok) return entry;
    const other = kind === "render" && this.images.get(`${want === "mid" ? "render" : "mid"}/${instance}/${key}`);
    return other?.ok ? other : null;
  }

  noteSea(img, src, canvas) {
    this.seas.push(this.edgeColour(img, src, canvas));
    if (this.seas.length > MAPTILES_SEAS) this.seas.shift();
  }

  edgeColour(img, src, canvas) {
    const cv = canvas(MAPTILES_SAMPLE, 1), g = cv.getContext("2d", { willReadFrequently: true });
    g.drawImage(img, ...src, 0, 0, MAPTILES_SAMPLE, 1);
    const px = g.getImageData(0, 0, MAPTILES_SAMPLE, 1).data, sum = [0, 0, 0];
    for (let i = 0; i < px.length; i += 4) for (let q = 0; q < 3; q++) sum[q] += px[i + q] / MAPTILES_SAMPLE;
    return sum.map(Math.round);
  }

  seaEdge(img, src, canvas) {
    const e = this.edgeColour(img, src, canvas), s = this.sea();
    return Math.hypot(e[0] - s[0], e[1] - s[1], e[2] - s[2]) <= MAPTILES_SEA_NEAR;
  }

  sea() {
    const seen = this.seas;
    if (!seen.length) return MAPTILES_SEA;
    return [0, 1, 2].map((q) => seen.map((s) => s[q]).sort((a, b) => a - b)[Math.floor(seen.length / 2)]);
  }

  exists(instance, key) { return this.hasRender(instance, key) || this.hasFloor(instance, key); }

  skirts(instance, key, entry, canvas) {
    const [c, r] = key.split("_").map(Number), gone = (dc, dr) => !this.exists(instance, `${c + dc}_${r + dr}`);
    const open = MAPTILES_SIDES.map(([dc, dr]) => gone(dc, dr));
    const corners = MAPTILES_CORNERS.map(([dc, dr]) => gone(dc, 0) && gone(0, dr) && gone(dc, dr));
    const sides = [...open, ...corners].map(Number).join("");
    if (entry.skirts?.sides === sides) return entry.skirts.list;
    const img = entry.img, n = img.naturalWidth || 512, d = MAPTILES_SKIRT, px = Math.round(n * d), list = [];
    const ease = (g, ramp) => {
      ramp.addColorStop(0, this.ink(1));
      ramp.addColorStop(0.45, this.ink(0.45));
      ramp.addColorStop(1, this.ink(0));
      g.globalCompositeOperation = "destination-in";
      g.fillStyle = ramp;
      g.fillRect(0, 0, n, n);
      g.globalCompositeOperation = "source-over";
    };
    const strips = [
      [[0, 0, n, 1], [n, px], [0, px, 0, 0], [0, -d, 1, d]],
      [[n - 1, 0, 1, n], [px, n], [0, 0, px, 0], [1, 0, d, 1]],
      [[0, n - 1, n, 1], [n, px], [0, 0, 0, px], [0, 1, 1, d]],
      [[0, 0, 1, n], [px, n], [px, 0, 0, 0], [-d, 0, d, 1]],
    ];
    open.forEach((o, i) => {
      if (!o) return;
      const [src, [w, h], ramp, at] = strips[i];
      if (entry.kind !== "floor" && !this.seaEdge(img, src, canvas)) return;
      const cv = canvas(w, h), g = cv.getContext("2d");
      g.drawImage(img, ...src, 0, 0, w, h);
      g.filter = `blur(${Math.round(n * MAPTILES_SMOOTH)}px)`;
      g.drawImage(img, ...src, 0, 0, w, h);
      g.filter = "none";
      ease(g, g.createLinearGradient(...ramp));
      list.push({ canvas: cv, at });
      if (entry.kind !== "floor") this.noteSea(img, src, canvas);
    });
    corners.forEach((o, i) => {
      if (!o) return;
      const [dc, dr] = MAPTILES_CORNERS[i];
      if (entry.kind !== "floor" && !this.seaEdge(img, [dc > 0 ? n - 2 : 0, dr > 0 ? n - 2 : 0, 2, 2], canvas)) return;
      const cv = canvas(px, px), g = cv.getContext("2d");
      const cx = dc > 0 ? 0 : px, cy = dr > 0 ? 0 : px;
      g.drawImage(img, dc > 0 ? n - 2 : 0, dr > 0 ? n - 2 : 0, 2, 2, 0, 0, px, px);
      ease(g, g.createRadialGradient(cx, cy, 0, cx, cy, px));
      list.push({ canvas: cv, at: [dc > 0 ? 1 : -d, dr > 0 ? 1 : -d, d, d] });
    });
    entry.skirts = { sides, list };
    return list;
  }

  load(kind, instance, key) {
    const id = `${kind}/${instance}/${key}`;
    let entry = this.images.get(id);
    if (entry) {
      this.images.delete(id);
      this.images.set(id, entry);
      return entry;
    }
    const img = this.picture(), list = kind === "render" ? this.render : kind === "mid" ? this.mid : this.floors;
    entry = { img, ok: false, kind };
    img.onload = () => { entry.ok = true; this.drawn(); };
    img.src = kind === "mid" ? this.address(`/detailview/render/${instance}/mid/${key}.webp`, list.version)
      : kind === "render" ? this.address(`/rendertile/${instance}/${key}.jpg`, list.version)
      : this.address(`/tile/${instance}/${key}.jpg`, list.instances[instance]?.[key]);
    this.images.set(id, entry);
    const mid = kind === "mid", cap = mid ? this.midMax : this.max;
    let count = 0;
    for (const e of this.images.values()) if ((e.kind === "mid") === mid) count++;
    if (count > cap) {
      for (const [k, e] of this.images) if ((e.kind === "mid") === mid) { this.images.delete(k); break; }
    }
    return entry;
  }

  forget(kind) {
    for (const id of [...this.images.keys()]) if (id.startsWith(`${kind}/`)) this.images.delete(id);
  }
}

if (typeof module === "object") {
  module.exports = { MapTiles, MAPTILES_MAX, MAPTILES_MID_MAX, MAPTILES_FULL_PX, MAPTILES_FAR_COUNT, MAPTILES_SEA, MAPTILES_SKIRT, MAPTILES_SMOOTH };
}
