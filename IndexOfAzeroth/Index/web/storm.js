// The Index of Azeroth. Copyright 2026 Index Case <indexofazeroth@pm.me>. PolyForm Strict 1.0.0, see LICENSE.md.
"use strict";

const STORM = { from: 0.8, share: 0.5, grid: [12, 7], dark: 0.6, cloudDark: 0.55, zoom: [12, 18], settle: 1000, far: [6, 14], ease: 1500, fps: 15,
  corner: { turn: [0.35, 0.8], cross: 1500, sway: 0.008, period: [9, 16], reach: 0.2 },
  drift: { gap: [4, 12], clear: 0.4, fadeIn: 0.2, fadeOut: 0.35, least: 3, size: [0.8, 1.1] },
  roam: { count: 8, gap: [0.4, 1.6], fade: 1500, life: [18, 36], size: [0.45, 0.8] },
  swirl: { cell: 1400, keep: 0.4, alpha: 0.35, size: [1.3, 2], turn: 120, edge: 0.25, fps: 8 },
  flash: { chunk: 8, quiet: 1.05, short: [0.2, 0.45], long: [0.9, 3.2], burst: 0.35, most: 3, length: 0.2, peak: 0.06, elevation: 68,
    glint: 1.5, fps: 30, apart: Math.PI / 3, side: { soft: 6, bulk: 8, even: 0.5, more: 0.5 } },
  rain: { most: 0.6, cell: 120, per: 54, life: 1.2, deep: 2.5, near: 0.08, trail: 0.06, wander: 0.04,
    longest: 0.3, least: 4, shift: 0.25, gust: 30, rings: [0.45, 0.8], blur: [1, 2, 3.2], fade: [1, 0.55, 0.3] },
  haze: { most: 0.12, side: 32, cell: 40, drift: 1 },
  shade: { most: 0.06, steps: 2 } };
const STORM_SCREEN = [3840, 2160];
const STORM_CORNERS = ["top_left", "top_right", "bottom_left", "bottom_right"];

const stormEase = (a, b, x) => { const t = Math.min(1, Math.max(0, (x - a) / (b - a))); return t * t * (3 - 2 * t); };
const stormRand = (...keys) => seeded(keys.reduce((h, k) => {
  let x = Math.imul(h ^ (k | 0), 0x85ebca6b);
  x = Math.imul(x ^ (x >>> 13), 0xc2b2ae35);
  return (x ^ (x >>> 16)) >>> 0;
}, 1245));

function stormLevel(values) {
  if (!values.length) return 0;
  const sorted = [...values].sort((a, b) => b - a);
  return sorted[Math.floor(values.length * STORM.share)];
}
const stormOn = (level) => level >= STORM.from;
const stormDepth = (level) => stormEase(STORM.from, 1, level);
const stormDark = (level, night, flash = 0) => STORM.dark * stormDepth(level) * (1 - Math.min(1, Math.max(0, night))) * (1 - flash);
const stormSun = (level, moon = false) => (moon ? 1 : 1 - stormDepth(level));
const stormCloudLight = (level, night, keep = 1, inn = 1) =>
  keep * (1 - STORM.cloudDark * stormDepth(level) * inn * (1 - Math.min(1, Math.max(0, night))));
const stormLightning = (level) => level >= 1 - 1e-6;
function stormSettle(from, goal, dt, still, ms = STORM.settle) {
  const step = still ? 1 : dt / ms;
  return goal > from ? Math.min(goal, from + step) : Math.max(goal, from - step);
}
const stormZoomIn = (zoom) => stormEase(STORM.zoom[0], STORM.zoom[1], zoom);
const stormFar = (ypx) => stormEase(STORM.far[0], STORM.far[1], ypx);

function stormFlashes(k, f = STORM.flash) {
  const rand = stormRand(k), out = [], end = f.chunk - f.quiet;
  const pick = ([a, b]) => a + (b - a) * rand();
  let t = pick(f.long) * rand();
  while (t < end) {
    out.push(t);
    let gap = pick(rand() < f.burst ? f.short : f.long);
    const back = out[out.length - f.most];
    if (out.length >= f.most && t + gap - back <= 1) gap = back + 1.001 - t;
    t += gap;
  }
  return out;
}
function stormFlashShape(s, f = STORM.flash) {
  if (!(s >= 0) || s >= f.length) return 0;
  return s < f.peak ? 1 : ((f.length - s) / (f.length - f.peak)) ** 2;
}
function stormFlashAt(t, f = STORM.flash) {
  const k = Math.floor(t / f.chunk);
  for (const c of [k, k - 1]) {
    const starts = stormFlashes(c, f);
    for (let i = starts.length - 1; i >= 0; i--) {
      const light = stormFlashShape(t - (c * f.chunk + starts[i]), f);
      if (light > 0) return { k: light, id: c * 64 + i };
    }
  }
  return { k: 0, id: null };
}
function stormFlashNext(t, f = STORM.flash) {
  for (let c = Math.floor(t / f.chunk); ; c++) {
    const next = stormFlashes(c, f).map((s) => c * f.chunk + s).find((s) => s > t);
    if (next !== undefined) return next;
  }
}
function stormToward(id, up = STORM.flash.elevation, f = STORM.flash) {
  const c = Math.floor(id / 64), e = (up * Math.PI) / 180;
  let a = stormRand(c, 7)() * 2 * Math.PI;
  for (let i = 1; i <= id - c * 64; i++) a += f.apart + stormRand(c, i, 7)() * (2 * Math.PI - 2 * f.apart);
  return [-Math.sin(a) * Math.cos(e), -Math.cos(a) * Math.cos(e), Math.sin(e)];
}
function stormSeaLight(light, flash) {
  if (!flash || !(flash.k > 0)) return light;
  const toward = stormToward(flash.id);
  return { ...light, toward, glintK: light.glintK * (1 - flash.k) + STORM.flash.glint * flash.k };
}

function stormSoften(a, W, H, r) {
  const pass = (src, along) => {
    const out = new Float32Array(src.length), n = along ? W : H, lines = along ? H : W;
    for (let line = 0; line < lines; line++) {
      const at = (k) => (along ? line * W + Math.min(n - 1, Math.max(0, k)) : Math.min(n - 1, Math.max(0, k)) * W + line);
      let sum = 0;
      for (let k = -r; k <= r; k++) sum += src[at(k)];
      for (let k = 0; k < n; k++) {
        out[at(k)] = sum / (2 * r + 1);
        sum += src[at(k + r + 1)] - src[at(k - r)];
      }
    }
    return out;
  };
  return pass(pass(a, true), false);
}
function stormNormals(px, { soft, bulk } = STORM.flash.side) {
  const { width: W, height: H, data } = px, n = W * H;
  const a = new Float32Array(n);
  for (let i = 0; i < n; i++) a[i] = data[i * 4] / 255;
  const h = soft > 0 ? stormSoften(stormSoften(a, W, H, soft), W, H, soft) : a;
  const sx = new Float32Array(n), sy = new Float32Array(n);
  for (let y = 0; y < H; y++) {
    for (let x = 0; x < W; x++) {
      const i = y * W + x, l = h[i - (x > 0 ? 1 : 0)], r = h[i + (x < W - 1 ? 1 : 0)], u = h[i - (y > 0 ? W : 0)], d = h[i + (y < H - 1 ? W : 0)];
      const gx = -((r - l) / 2) * bulk, gy = -((d - u) / 2) * bulk, len = Math.hypot(gx, gy, 1);
      sx[i] = gx / len;
      sy[i] = gy / len;
    }
  }
  return { width: W, height: H, a, sx, sy };
}
function stormSideLight({ width, height, a, sx, sy }, way, { even, more } = STORM.flash.side) {
  const out = new Uint8ClampedArray(width * height * 4);
  for (let i = 0; i < width * height; i++) {
    const toward = Math.max(0, sx[i] * way[0] + sy[i] * way[1]);
    out[i * 4] = out[i * 4 + 1] = out[i * 4 + 2] = 255;
    out[i * 4 + 3] = 255 * Math.min(1, even + more * Math.min(1, 2 * toward)) * a[i];
  }
  return out;
}
function stormCloudWay(id, turn = 0) {
  const [n, w] = stormToward(id), L = Math.hypot(n, w), x = -w / L, y = -n / L, c = Math.cos(turn), s = Math.sin(turn);
  return [x * c + y * s, -x * s + y * c];
}

function stormCornerRect(box, corner, W, H, reach = STORM.corner.reach) {
  const [S0, S1] = STORM_SCREEN, s = Math.max(W / S0, H / S1), left = corner.endsWith("left"), top = corner.startsWith("top");
  const [x0, y0, x1, y1] = [box[0] * S0, box[1] * S1, box[2] * S0, box[3] * S1];
  const x = left ? x0 * s : W - (S0 - x0) * s, y = top ? y0 * s : H - (S1 - y0) * s, w = (x1 - x0) * s, h = (y1 - y0) * s;
  const k = Math.min(1, (reach * W) / (left ? x + w : W - x), (reach * H) / (top ? y + h : H - y));
  return [left ? x * k : W - (W - x) * k, top ? y * k : H - (H - y) * k, w * k, h * k];
}
function stormLayerLight(light) {
  return light < 1 - 0.002 ? tint("black", +(1 - light).toFixed(3)) : null;
}
function stormShade(...keys) {
  const h = STORM.shade;
  return +((h.most * (Math.round(stormRand(...keys, 73)() * 2 * h.steps) - h.steps)) / h.steps).toFixed(4);
}
const stormCanvas = (w, h) => Object.assign(document.createElement("canvas"), { width: w, height: h });

function stormSway(corner, t, W, c = STORM.corner) {
  const k = STORM_CORNERS.indexOf(corner), rand = stormRand(k, 23), reach = c.sway * W;
  const way = (out) => {
    const period = c.period[0] + (c.period[1] - c.period[0]) * rand(), start = rand() * 2 * Math.PI;
    return out * reach * (1 + Math.sin((2 * Math.PI * t) / period + start));
  };
  return [way(corner.endsWith("left") ? -1 : 1), way(corner.startsWith("top") ? -1 : 1)];
}

function stormClear(v) {
  const c = v.clear || { l: 0, r: v.width, t: 0, b: v.height };
  return [c.l, c.t, c.r - c.l, c.b - c.t];
}
function stormSize(box, W, H) {
  const [S0, S1] = STORM_SCREEN, s = Math.max(W / S0, H / S1);
  return [(box[2] - box[0]) * S0 * s, (box[3] - box[1]) * S1 * s];
}

function stormUpwind(way, W, H) {
  const at = { top_left: [-W / 2, -H / 2], top_right: [W / 2, -H / 2], bottom_left: [-W / 2, H / 2], bottom_right: [W / 2, H / 2] };
  return STORM_CORNERS.reduce((best, c) => (at[c][0] * way[0] + at[c][1] * way[1] < at[best][0] * way[0] + at[best][1] * way[1] ? c : best));
}
function stormDriftWay(corner, way, W, H) {
  const from = [corner.endsWith("left") ? 0 : W, corner.startsWith("top") ? 0 : H], R = STORM.drift.clear * Math.hypot(W, H) / 2;
  const dx = from[0] - W / 2, dy = from[1] - H / 2, b = dx * way[0] + dy * way[1], c = dx * dx + dy * dy - R * R, disc = b * b - c;
  const along = disc >= 0 ? -b - Math.sqrt(disc) : -b;
  return { from, way, length: Math.max(along, 0) };
}
const stormDriftAlpha = (p, d = STORM.drift) => (p < 0 || p >= 1 ? 0 : Math.min(1, p / d.fadeIn, (1 - p) / d.fadeOut));

function stormCell(ci, cj, p = STORM.swirl) {
  const rand = stormRand(ci, cj, 5);
  if (rand() >= p.keep) return null;
  return { n: (ci + rand()) * p.cell, w: (cj + rand()) * p.cell, which: rand(), turn: rand() * 2 * Math.PI, size: p.size[0] + (p.size[1] - p.size[0]) * rand() };
}
function stormSwirlAngle(t, r, radius, spin = MAELSTROM.spin) {
  const half = radius / 2, k = half / Math.max(r, radius / 8);
  return spin * ((2 * Math.PI * t) / STORM.swirl.turn) * k;
}

function stormRainPoint(W, H, wind, windYards = 0, r = STORM.rain) {
  const shift = r.shift * Math.hypot(W / 2, H / 2) * Math.min(1, windYards / r.gust);
  return [W / 2 + wind[0] * shift, H / 2 + wind[1] * shift];
}
function stormRainCell(ypx, r = STORM.rain) {
  return 2 ** (Math.round(2 * Math.log2(r.cell * ypx)) / 2);
}
function stormRainSpots(frame, W, H, ypx, t, r = STORM.rain) {
  const f = frame, C = stormRainCell(ypx, r), R = Math.hypot(W / 2, H / 2), out = [];
  const corners = [[0, 0], [W, 0], [0, H], [W, H]].map(([x, y]) => [f[6] + f[0] * x + f[3] * y, f[7] + f[1] * x + f[4] * y]);
  const ns = corners.map((c) => c[0]), ws = corners.map((c) => c[1]);
  for (let ci = Math.floor(Math.min(...ns) / C); ci <= Math.floor(Math.max(...ns) / C); ci++) {
    for (let cj = Math.floor(Math.min(...ws) / C); cj <= Math.floor(Math.max(...ws) / C); cj++) {
      for (let k = 0; k < r.per; k++) {
        const phase = stormRand(ci, cj, k, 61)(), when = t / r.life + phase, life = Math.floor(when);
        const rand = stormRand(ci, cj, k, life, 67), q = stormOnScreen(f, { n: (ci + rand()) * C, w: (cj + rand()) * C });
        if (q[0] < 0 || q[1] < 0 || q[0] > W || q[1] > H) continue;
        const turn = rand() * 2 * Math.PI, off = rand() * r.wander * R;
        out.push({ q, share: when - life, aim: [Math.cos(turn) * off, Math.sin(turn) * off] });
      }
    }
  }
  return out;
}
function stormDrop(q, share, at, R, gust = 0, aim = [0, 0], r = STORM.rain) {
  const cx = at[0] + aim[0], cy = at[1] + aim[1], sx = (q[0] - cx) * r.deep, sy = (q[1] - cy) * r.deep;
  const far = Math.hypot(sx, sy) + 1e-9, z = r.near + (r.deep - r.near) * share, x0 = cx + sx / z, y0 = cy + sy / z;
  const len = Math.min(r.longest * R, Math.max(r.least * gust, far * (1 / (z - r.trail) - 1 / z)));
  return { x0, y0, x1: x0 + (sx / far) * len, y1: y0 + (sy / far) * len, strength: Math.min(1, share * 20, (1 - share) * 10) * (1 - 0.4 * share) };
}
function stormHaze(h = STORM.haze) {
  const S = h.side, rand = stormRand(37), v = Array.from({ length: S * S }, () => rand()), rgb = tintRgb("light-haze");
  let cur = v;
  for (let pass = 0; pass < 3; pass++) {
    cur = cur.map((_, i) => {
      const x = i % S, y = Math.floor(i / S);
      let sum = 0;
      for (const [dx, dy] of [[0, 0], [1, 0], [-1, 0], [0, 1], [0, -1]]) sum += cur[((y + dy + S) % S) * S + ((x + dx + S) % S)];
      return sum / 5;
    });
  }
  const lo = Math.min(...cur), hi = Math.max(...cur), out = new Uint8ClampedArray(S * S * 4);
  cur.forEach((c, i) => {
    out.set(rgb, i * 4);
    out[i * 4 + 3] = (255 * (c - lo)) / Math.max(hi - lo, 1e-9);
  });
  return out;
}

function stormOnScreen(frame, p) {
  const [a, b, , c, d, , n0, w0] = frame, det = a * d - b * c, dn = p.n - n0, dw = p.w - w0;
  return [(d * dn - c * dw) / det, (a * dw - b * dn) / det];
}
function stormScreenWay(frame, way) {
  const [x0, y0] = stormOnScreen(frame, { n: 0, w: 0 }), [x1, y1] = stormOnScreen(frame, { n: way[0], w: way[1] });
  const L = Math.hypot(x1 - x0, y1 - y0);
  return [(x1 - x0) / L, (y1 - y0) / L];
}

class Storm {
  constructor({ picture, index, drawn = () => {}, pieces = () => [], rgb = [8, 14, 24], canvas = stormCanvas, pixels = seaPixels }) {
    Object.assign(this, { picture, index, drawn, pieces, rgb, canvas, pixels });
    this.layer = null;
    this.turned = new Map();
    this.list = undefined;
    this.pics = new Map();
    this.heights = new Map();
    this.lit = { id: null, sides: new Map() };
    this.hazeTile = null;
    this.hazeSheet = null;
    this.view = null;
    this.shown = 0;
    this.zoomIn = 0;
    this.level = 0;
    this.drawnAt = null;
    this.moved = -Infinity;
    this.corners = null;
    this.drift = null;
    this.driftNext = 0;
    this.roam = [];
    this.roamNext = 0;
    this.sides = [];
  }

  named(kind) {
    return this.list ? Object.keys(this.list).filter((n) => n.startsWith(`storm_${kind}_corner_`)).sort() : [];
  }

  pic(name, shade = 0) {
    if (!this.list?.[name]) return null;
    let p = this.pics.get(name);
    if (!p) {
      const img = this.picture(pictureSrc(`/art/storm/${name}.webp`, this.list[name].v));
      p = { img, ok: false, shades: new Map() };
      img.onload = () => { p.ok = true; this.drawn(); };
      this.pics.set(name, p);
      this.normals(name);
    }
    if (!p.ok || !shade) return p.ok ? p.img : null;
    let c = p.shades.get(shade);
    if (!c) {
      c = this.canvas(p.img.naturalWidth, p.img.naturalHeight);
      const g = c.getContext("2d");
      g.filter = `brightness(${1 + shade})`;
      g.drawImage(p.img, 0, 0);
      Object.assign(c, { of: p.img, src: `${p.img.src}#${shade}` });
      p.shades.set(shade, c);
    }
    return c;
  }

  normals(name) {
    const v = this.list?.[name]?.height;
    if (!v) return null;
    let h = this.heights.get(name);
    if (!h) {
      const img = this.picture(pictureSrc(`/art/storm/${name}.height.png`, v));
      h = { img, ok: false, normals: null };
      img.onload = () => { h.ok = true; };
      this.heights.set(name, h);
    }
    if (h.ok && !h.normals) {
      const px = this.pixels(h.img);
      h.normals = px ? stormNormals(px) : false;
    }
    return h.normals || null;
  }

  sideLight(name, turn, id) {
    if (this.lit.id !== id) this.lit = { id, sides: new Map() };
    const key = `${name}|${turn.toFixed(4)}`;
    if (!this.lit.sides.has(key)) {
      const nm = this.normals(name);
      if (!nm) return null;
      const c = this.canvas(nm.width, nm.height), g = c.getContext("2d"), img = g.createImageData(nm.width, nm.height);
      img.data.set(stormSideLight(nm, stormCloudWay(id, turn)));
      g.putImageData(img, 0, 0);
      this.lit.sides.set(key, c);
    }
    return this.lit.sides.get(key);
  }

  see(view) {
    this.view = view;
    if (!view) return;
    if ((view.any || view.maelstrom) && this.list === undefined) {
      this.list = null;
      Promise.resolve(this.index()).then((got) => { this.list = got?.pictures || {}; this.drawn(); }, () => { this.list = {}; });
    }
    const mid = { n: view.frame[6] + (view.frame[0] * view.width + view.frame[3] * view.height) / 2, w: view.frame[7] + (view.frame[1] * view.width + view.frame[4] * view.height) / 2 };
    if (this.mid) {
      const px = Math.hypot(mid.n - this.mid.n, mid.w - this.mid.w) / view.ypx;
      if (px > 0.5) {
        this.moved = view.now;
        if (this.corners) for (const c of this.corners) c.pan -= px / view.width;
      }
    }
    this.mid = mid;
  }

  sun() {
    const v = this.view;
    return v ? 1 - (1 - stormSun(this.level, v.moon)) * this.zoomIn : 1;
  }

  flash(now) {
    const v = this.view;
    return v && !v.still && stormLightning(this.level) && this.zoomIn > 0 ? stormFlashAt(now / 1000) : { k: 0, id: null };
  }

  next(now) {
    const v = this.view;
    if (!v || v.still) return null;
    const due = [];
    const showing = (stormOn(v.level) || stormOn(this.level) || this.shown > 0) && (this.zoomIn > 0 || stormZoomIn(v.zoom) > 0);
    const settling = Math.abs(stormZoomIn(v.zoom) - this.zoomIn) > 1e-3 || Math.abs(v.level - this.level) > 1e-3;
    if (showing && settling) due.push(now + 1000 / STORM.fps);
    if (stormLightning(this.level) && this.zoomIn > 0) {
      due.push(this.flash(now).k > 0 ? now + 1000 / STORM.flash.fps : stormFlashNext(now / 1000) * 1000);
    }
    if (showing && this.list) due.push(now + 1000 / STORM.fps);
    if (v.maelstrom && stormFar(v.ypx) > 0 && this.list) due.push(now + 1000 / STORM.swirl.fps);
    return due.length ? Math.min(...due) : null;
  }

  draw(ctx, now, dpr) {
    const v = this.view;
    if (!v) return false;
    const dt = this.drawnAt == null ? 0 : Math.min(1000, Math.max(0, now - this.drawnAt));
    this.drawnAt = now;
    this.zoomIn = stormSettle(this.zoomIn, stormZoomIn(v.zoom), dt, v.still);
    this.level = stormSettle(this.level, v.level, dt, v.still);
    const level = this.level, zoomIn = this.zoomIn;
    const goal = stormOn(level) ? 1 : 0, step = v.still ? 1 : dt / STORM.ease;
    this.shown = goal > this.shown ? Math.min(goal, this.shown + step) : Math.max(goal, this.shown - step);
    if (this.shown === 0) Object.assign(this, { corners: null, drift: null, roam: [] });
    const flash = this.flash(now), on = stormOn(level);
    const dark = on ? stormDark(level, v.night, flash.k) * zoomIn : 0;
    const near = zoomIn * this.shown, far = v.maelstrom ? stormFar(v.ypx) : 0;
    const weather = v.still || !on ? 0 : stormDepth(level) * near;
    if (dark < 0.002 && near < 0.002 && far <= 0 && weather < 0.002) return false;
    ctx.save();
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    if (dark >= 0.002) {
      ctx.fillStyle = `rgba(${this.rgb.join(", ")}, ${dark.toFixed(3)})`;
      ctx.fillRect(0, 0, v.width, v.height);
    }
    if (weather >= 0.002) {
      this.drawHaze(ctx, v, weather * STORM.haze.most, now);
      this.drawRain(ctx, v, weather * STORM.rain.most, now);
    }
    const lit = stormLayerLight(stormCloudLight(on ? level : 0, v.night, v.keep, zoomIn));
    const L = lit ? this.layerFor(ctx.canvas.width, ctx.canvas.height) : null, g = L ? L.getContext("2d") : ctx;
    if (L) {
      g.setTransform(1, 0, 0, 1, 0, 0);
      g.globalCompositeOperation = "source-over";
      g.globalAlpha = 1;
      g.clearRect(0, 0, L.width, L.height);
      g.setTransform(dpr, 0, 0, dpr, 0, 0);
    }
    this.sides = [];
    if (far > 0) this.drawSwirl(g, v, far, now);
    if (near >= 0.002) {
      this.drawRoam(g, v, near, now, dt);
      if (!v.still) this.drawDrift(g, v, near, now);
      this.drawCorners(g, v, near, now);
    }
    if (L) {
      g.setTransform(1, 0, 0, 1, 0, 0);
      g.globalAlpha = 1;
      g.globalCompositeOperation = "source-atop";
      g.fillStyle = lit;
      g.fillRect(0, 0, L.width, L.height);
      g.globalCompositeOperation = "source-over";
      g.setTransform(dpr, 0, 0, dpr, 0, 0);
    }
    if (flash.k > 0) {
      for (const s of this.sides) {
        const side = this.sideLight(s.name, s.turn, flash.id);
        if (side) this.layAt(g, side, s.at, s.size, s.turn, s.alpha * flash.k);
      }
    }
    if (L) {
      ctx.setTransform(1, 0, 0, 1, 0, 0);
      ctx.globalAlpha = 1;
      ctx.drawImage(L, 0, 0);
    }
    ctx.restore();
    return true;
  }

  layerFor(w, h) {
    if (!this.layer || this.layer.width !== w || this.layer.height !== h) this.layer = this.canvas(w, h);
    return this.layer;
  }

  drawHaze(ctx, v, strength, now) {
    const h = STORM.haze;
    if (!this.hazeTile) {
      this.hazeTile = this.canvas(h.side, h.side);
      const g = this.hazeTile.getContext("2d"), img = g.createImageData(h.side, h.side);
      img.data.set(stormHaze());
      g.putImageData(img, 0, 0);
    }
    const cw = Math.ceil(v.width / h.cell) + 2, ch = Math.ceil(v.height / h.cell) + 2;
    if (!this.hazeSheet || this.hazeSheet.width !== cw || this.hazeSheet.height !== ch) this.hazeSheet = this.canvas(cw, ch);
    const g = this.hazeSheet.getContext("2d"), way = stormScreenWay(v.frame, v.wind);
    const go = (h.drift * Math.max(STORM.drift.least, v.windYards / v.ypx) * now) / 1000 / h.cell;
    const pattern = g.createPattern(this.hazeTile, "repeat");
    pattern.setTransform({ a: 1, b: 0, c: 0, d: 1, e: (way[0] * go) % h.side, f: (way[1] * go) % h.side });
    g.clearRect(0, 0, cw, ch);
    g.fillStyle = pattern;
    g.fillRect(0, 0, cw, ch);
    ctx.imageSmoothingEnabled = true;
    ctx.globalAlpha = strength;
    ctx.drawImage(this.hazeSheet, -h.cell, -h.cell, cw * h.cell, ch * h.cell);
    ctx.globalAlpha = 1;
  }

  drawRain(ctx, v, strength, now) {
    const r = STORM.rain, at = stormRainPoint(v.width, v.height, stormScreenWay(v.frame, v.wind), v.windYards);
    const R = Math.hypot(v.width / 2, v.height / 2), bands = r.blur.map(() => [[], [], []]), gust = Math.min(1, v.windYards / r.gust);
    for (const spot of stormRainSpots(v.frame, v.width, v.height, v.ypx, now / 1000)) {
      const d = stormDrop(spot.q, spot.share, at, R, gust, spot.aim);
      if (d.x0 < 0 || d.y0 < 0 || d.x0 > v.width || d.y0 > v.height) continue;
      const far = Math.hypot(d.x0 - at[0], d.y0 - at[1]) / R, ring = far < r.rings[0] ? 0 : far < r.rings[1] ? 1 : 2;
      bands[ring][Math.min(2, Math.floor(d.strength * 3))].push(d);
    }
    ctx.lineCap = "round";
    ctx.strokeStyle = tint("light-rain");
    bands.forEach((ring, j) => ring.forEach((band, k) => {
      ctx.globalAlpha = (strength * r.fade[j] * (k + 1)) / 3;
      ctx.lineWidth = r.blur[j];
      ctx.beginPath();
      for (const d of band) {
        ctx.moveTo(d.x0, d.y0);
        ctx.lineTo(d.x1, d.y1);
      }
      ctx.stroke();
    }));
    ctx.globalAlpha = 1;
  }

  turnedPicture(img, turn, w, h) {
    const key = `${img.src || ""}|${turn.toFixed(4)}|${Math.round(w)}|${Math.round(h)}`;
    let c = this.turned.get(key);
    if (!c) {
      const side = Math.ceil(Math.hypot(w, h));
      c = this.canvas(side, side);
      const g = c.getContext("2d");
      g.translate(side / 2, side / 2);
      g.rotate(turn);
      g.drawImage(img, -w / 2, -h / 2, w, h);
      if (this.turned.size >= STORM.roam.count + 4) this.turned.delete(this.turned.keys().next().value);
      this.turned.set(key, c);
    }
    return c;
  }

  drawCorners(ctx, v, alpha, now) {
    const rand = stormRand(Math.floor(now));
    const span = () => STORM.corner.turn[0] + (STORM.corner.turn[1] - STORM.corner.turn[0]) * rand();
    if (!this.corners) {
      this.corners = STORM_CORNERS.map((c, i) => {
        const names = this.named(c);
        return names.length ? { corner: c, names, shades: names.map((n, k) => stormShade(i, k)), now: names[i % names.length], was: null, at: -Infinity, pan: span() } : null;
      }).filter(Boolean);
      if (!this.corners.length) { this.corners = null; return; }
    }
    for (const c of this.corners) {
      if (c.pan <= 0 && now - c.at >= STORM.corner.cross) {
        const others = c.names.filter((n) => n !== c.now);
        if (others.length) Object.assign(c, { was: c.now, now: others[Math.floor(rand() * others.length)], at: now });
        c.pan = span();
      }
      const e = stormEase(0, 1, (now - c.at) / STORM.corner.cross);
      for (const [name, share] of [[c.was, 1 - e], [c.now, e < 1 ? e : 1]]) {
        const img = name && share > 0 ? this.pic(name, c.shades[c.names.indexOf(name)]) : null;
        if (!img) continue;
        const [x, y, w, h] = stormCornerRect(this.list[name].box, c.corner, v.width, v.height);
        const [dx, dy] = stormSway(c.corner, v.still ? 0 : now / 1000, v.width);
        ctx.globalAlpha = alpha * share;
        ctx.drawImage(img, x + dx, y + dy, w, h);
        this.sides.push({ name, turn: 0, at: [x + dx + w / 2, y + dy + h / 2], size: [w, h], alpha: alpha * share });
      }
    }
  }

  drawDrift(ctx, v, alpha, now) {
    const d = STORM.drift, names = this.named("random");
    if (!names.length) return;
    const [l, t, W, H] = stormClear(v), speed = Math.max(d.least, v.windYards / v.ypx);
    if (!this.drift && now >= this.driftNext) {
      const rand = stormRand(Math.floor(now), 11), way = stormScreenWay(v.frame, v.wind), corner = stormUpwind(way, W, H), path = stormDriftWay(corner, way, W, H);
      this.drift = { ...path, from: [l + path.from[0], t + path.from[1]], name: names[Math.floor(rand() * names.length)], turn: rand() * 2 * Math.PI,
        size: d.size[0] + (d.size[1] - d.size[0]) * rand(), start: now, speed, shade: stormShade(Math.floor(now), 23) };
    }
    const c = this.drift;
    if (!c) return;
    const along = c.speed * (now - c.start) / 1000, p = along / Math.max(c.length, 1e-9);
    if (p >= 1) {
      this.drift = null;
      this.driftNext = now + 1000 * (d.gap[0] + (d.gap[1] - d.gap[0]) * stormRand(Math.floor(now), 13)());
      return;
    }
    const [w, h] = stormSize(this.list[c.name].box, W, H).map((s) => s * c.size), at = [c.from[0] + c.way[0] * along, c.from[1] + c.way[1] * along];
    const strength = alpha * stormDriftAlpha(p);
    this.layTurned(ctx, this.pic(c.name, c.shade), at, [w, h], c.turn, strength);
    this.sides.push({ name: c.name, turn: c.turn, at, size: [w, h], alpha: strength });
  }

  drawRoam(ctx, v, alpha, now, dt) {
    const R = STORM.roam, names = this.named("random");
    if (!names.length) return;
    const [l, t, cw, ch] = stormClear(v), W = v.width, H = v.height;
    if (this.roam.length < R.count && now >= this.roamNext) {
      const rand = stormRand(Math.floor(now), 17), x = l + cw * rand(), y = t + ch * rand(), f = v.frame;
      const life = 1000 * (R.life[0] + (R.life[1] - R.life[0]) * rand());
      this.roam.push({ n: f[6] + f[0] * x + f[3] * y, w: f[7] + f[1] * x + f[4] * y, name: names[Math.floor(rand() * names.length)],
        turn: rand() * 2 * Math.PI, size: R.size[0] + (R.size[1] - R.size[0]) * rand(), ypx: v.ypx, at: now, end: now + life, shade: stormShade(Math.floor(now), 19) });
      this.roamNext = now + 1000 * (R.gap[0] + (R.gap[1] - R.gap[0]) * rand());
    }
    const resting = !v.still && now - this.moved > 250;
    this.roam = this.roam.filter((c) => {
      if (resting) {
        c.n += v.wind[0] * v.windYards * dt / 1000;
        c.w += v.wind[1] * v.windYards * dt / 1000;
      }
      const [w, h] = stormSize(this.list[c.name].box, W, H).map((k) => k * c.size * c.ypx / v.ypx), [x, y] = stormOnScreen(v.frame, c);
      if (now >= c.end || x < -w || x > W + w || y < -h || y > H + h) return false;
      const strength = alpha * Math.min(1, (now - c.at) / R.fade, (c.end - now) / R.fade);
      this.layTurned(ctx, this.pic(c.name, c.shade), [x, y], [w, h], c.turn, strength);
      this.sides.push({ name: c.name, turn: c.turn, at: [x, y], size: [w, h], alpha: strength });
      return true;
    });
  }

  drawSwirl(ctx, v, alpha, now) {
    const mine = this.named("random");
    if (!mine.length) return;
    const f = v.frame, m = v.maelstrom, S = STORM.swirl, own = this.pieces(), all = mine.length + own.length;
    for (let ci = Math.floor((m.eye.n - m.radius) / S.cell); ci * S.cell < m.eye.n + m.radius; ci++) {
      for (let cj = Math.floor((m.eye.w - m.radius) / S.cell); cj * S.cell < m.eye.w + m.radius; cj++) {
        const cell = stormCell(ci, cj);
        if (!cell) continue;
        const dn = cell.n - m.eye.n, dw = cell.w - m.eye.w, r = Math.hypot(dn, dw);
        if (r >= m.radius) continue;
        const a = stormSwirlAngle(now / 1000, r, m.radius), cos = Math.cos(a), sin = Math.sin(a), k = Math.floor(cell.which * all);
        const img = k < mine.length ? this.pic(mine[k], stormShade(ci, cj)) : own[k - mine.length];
        if (!img) continue;
        const side = (S.cell * cell.size) / v.ypx, s = side / Math.max(img.naturalWidth, img.naturalHeight, 1);
        this.layAt(ctx, img, stormOnScreen(f, { n: m.eye.n + dn * cos - dw * sin, w: m.eye.w + dn * sin + dw * cos }),
          [img.naturalWidth * s, img.naturalHeight * s], cell.turn + a, alpha * S.alpha * (1 - stormEase(1 - S.edge, 1, r / m.radius)));
      }
    }
  }

  layTurned(ctx, img, [x, y], [w, h], turn, alpha) {
    if (!img || !(alpha > 0.002)) return;
    const c = this.turnedPicture(img, turn, w, h);
    ctx.globalAlpha = alpha;
    ctx.drawImage(c, x - c.width / 2, y - c.height / 2);
  }

  layAt(ctx, img, [x, y], [w, h], turn, alpha) {
    if (!img || !(alpha > 0.002)) return;
    const was = ctx.getTransform();
    ctx.globalAlpha = alpha;
    ctx.translate(x, y);
    ctx.rotate(turn);
    ctx.drawImage(img, -w / 2, -h / 2, w, h);
    ctx.setTransform(was);
  }
}

if (typeof module === "object") {
  module.exports = { STORM, STORM_SCREEN, STORM_CORNERS, stormLevel, stormOn, stormDepth, stormDark, stormSun, stormCloudLight, stormLightning,
    stormSettle, stormZoomIn, stormFar, stormDrop, stormRainPoint, stormRainSpots, stormRainCell, stormShade, stormFlashes, stormFlashShape, stormFlashAt, stormFlashNext, stormToward, stormSeaLight, stormSoften, stormNormals, stormSideLight,
    stormCloudWay, stormCornerRect, stormLayerLight, stormCanvas, stormSway, stormClear, stormSize, stormUpwind, stormDriftWay, stormDriftAlpha,
    stormCell, stormSwirlAngle, stormHaze, stormOnScreen, stormScreenWay, Storm };
}
