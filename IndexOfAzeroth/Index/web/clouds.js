// The Index of Azeroth. Copyright 2026 Index Case <indexofazeroth@pm.me>. PolyForm Strict 1.0.0, see LICENSE.md.
"use strict";

const CLOUDS_SMALLEST = 16;

const MOTION = { fade: 10000, stepPx: 0.5, least: 100, most: 1000 };

const CLOUD_SHADOW = { base: 300, top: 360, longest: 4000, moon: 0.3, step: 1,
  unlit: { elevation: 45, dir: [-Math.SQRT1_2, -Math.SQRT1_2], strength: 0.4 }, probe: { side: 32, steps: 16 } };

const KEPT = { area: 3, part: 5, side: 8192, around: [0.5, 0.25, 0.1], moving: [0] };
KEPT.still = [null, ...KEPT.around];

function cloudShade(by, dark, tileYards) {
  const { dir, tan, strength, moon } = groundLight(by, dark);
  if (!(tan > 0)) return { dx: 0, dy: 0, tx: 0, ty: 0, yards: 0, topYards: 0, strength: 0, moon };
  const far = (h) => Math.min(CLOUD_SHADOW.longest, h / tan);
  const yards = far(CLOUD_SHADOW.base), topYards = far(CLOUD_SHADOW.top);
  const [ex, sy] = dir.map((v) => -v / tileYards);
  return { dx: ex * yards, dy: sy * yards, tx: ex * topYards, ty: sy * topYards, yards, topYards, strength, moon };
}

function shadowReach([c0, c1, r0, r1], { dx, dy, tx, ty }) {
  return [c0 - Math.max(0, dx, tx), c1 - Math.min(0, dx, tx), r0 - Math.max(0, dy, ty), r1 - Math.min(0, dy, ty)];
}

function groundLight(by, dark) {
  const light = by ? by.light : CLOUD_SHADOW.unlit, e = light.elevation, moon = !!by?.moon;
  if (!(e > 0)) return { dir: [0, 0], tan: 0, strength: 0, moon };
  const s = !by ? CLOUD_SHADOW.unlit.strength : dark * (moon ? CLOUD_SHADOW.moon : 1);
  return { dir: light.dir, tan: Math.tan((e * Math.PI) / 180), strength: +s.toFixed(4), moon };
}

function motionOf([, col, row, , track], areas) {
  const kind = Array.isArray(track) ? track[0] : null, given = Array.isArray(track) ? Number(track[track.length - 1]) : 0;
  const speed = kind === "swirl" ? Math.abs(given) : given;
  if (!(speed > 0 && speed < Infinity)) return null;
  let legs, loop = false, phase = 0, fast = speed;
  if (kind === "roll" || kind === "swirl") {
    const area = areas[track[1]];
    if (!area) return null;
    if (kind === "roll") {
      const [, , lo, hi] = track, [, , , ax, ay] = area, at = (s) => [col + ax * (lo + s), row + ay * (lo + s)];
      legs = [{ at, length: hi - lo, speed, box: spotsBox([at(0), at(hi - lo)]) }];
      phase = -lo / speed;
    } else {
      const [, , a0, a1] = track, [, mc, mr] = area, dx = col - mc, dy = row - mr, r = Math.hypot(dx, dy), way = Math.sign(given);
      const round = (deg) => { const a = deg * Math.PI / 180, c = Math.cos(a), s = Math.sin(a); return [mc + dx * c - dy * s, mr + dx * s + dy * c]; };
      const from = way > 0 ? a0 : a1;
      loop = a1 - a0 >= 360;
      legs = [{ at: loop ? (s) => round(way * s) : (s) => round(from + way * s), length: loop ? 360 : a1 - a0, speed, box: [mc - r, mc + r, mr - r, mr + r] }];
      phase = loop ? 0 : -way * from / speed;
      fast = speed * Math.PI / 180 * r;
    }
  } else if (kind === "drift" || kind === "spiral") {
    legs = [track[1], track[2]].map((way) => alongWay(way, speed));
    if (!legs.every(Boolean)) return null;
  } else return null;
  if (!(legs.reduce((n, l) => n + l.length, 0) > 0)) return null;
  const fade = MOTION.fade / 60000;
  return { legs, loop, phase, fast, period: legs.reduce((n, l) => n + l.length / l.speed + fade, 0) };
}

function alongWay(way, speed) {
  if (!Array.isArray(way) || !way.length) return null;
  const pts = way.map(([c, r]) => [Number(c), Number(r)]), last = pts.length - 1;
  const sums = pts.map((p, k) => (k ? Math.hypot(p[0] - pts[k - 1][0], p[1] - pts[k - 1][1]) : 0));
  for (let k = 1; k <= last; k++) sums[k] += sums[k - 1];
  const at = (s) => {
    let k = 0;
    while (k < last && sums[k + 1] < s) k++;
    const a = pts[k], n = Math.min(k + 1, last), gap = sums[n] - sums[k];
    const u = gap > 0 ? Math.min(1, Math.max(0, (s - sums[k]) / gap)) : 0;
    return [a[0] + (pts[n][0] - a[0]) * u, a[1] + (pts[n][1] - a[1]) * u];
  };
  return { at, length: sums[sums.length - 1], speed, box: spotsBox(pts) };
}

function spotsBox(pts) {
  const cs = pts.map((p) => p[0]), rs = pts.map((p) => p[1]);
  return [Math.min(...cs), Math.max(...cs), Math.min(...rs), Math.max(...rs)];
}

function copiesAt(motion, col, row, t) {
  if (!motion || t == null) return [[col, row, 1]];
  const { legs } = motion;
  if (motion.loop) return [[...legs[0].at(cycle(legs[0].speed * t, 360)), 1]];
  const fade = MOTION.fade / 60000;
  let f = cycle(t + motion.phase, motion.period);
  for (let j = 0; ; j++) {
    const leg = legs[j], go = leg.length / leg.speed;
    if (f < go) return [[...leg.at(leg.speed * f), 1]];
    f -= go;
    if (f < fade || j === legs.length - 1) {
      const u = Math.min(1, f / fade), out = [[...leg.at(leg.length), 1 - u], [...legs[(j + 1) % legs.length].at(0), u]];
      return out.filter((c) => c[2] > 0);
    }
    f -= fade;
  }
}
const cycle = (v, n) => { const r = v % n; return r < 0 ? r + n : r; };
const meets = (boxes, c0, c1, r0, r1) => boxes.some(([a0, a1, b0, b1]) => a1 >= c0 && a0 <= c1 + 1 && b1 >= r0 && b0 <= r1 + 1);

class Clouds {
  constructor({ picture, canvas, drawn, now = () => Date.now(), settled = () => true, address }) {
    Object.assign(this, { picture, canvas, drawn, now, settled, address });
    this.set(null);
  }

  set(index) {
    const changed = !this.index || this.index.version !== index?.version;
    this.ready = !!index;
    this.index = index && Array.isArray(index.pieces) ? index : { version: null, pieceTiles: 1, pieces: [], instances: {} };
    this.side = Number(this.index.pieceTiles) || 1;
    this.reaches = this.index.pieces.map((p) => (Number(p?.reach) || 0) * this.side);
    if (changed || !this.pics) this.pics = new Map();
    this.lists = new Map();
    this.covers = new Map();
    this.readyTiles = new Set();
    this.answers = {};
    for (const [inst, list] of Object.entries(this.index.instances || {})) {
      const areas = this.index.areas?.[inst] || [];
      const placed = (list || []).map((p, k) => {
        const reach = this.reachOf(p[0]), motion = motionOf(p, areas);
        const boxes = (motion ? motion.legs.map((l) => l.box) : [[p[1], p[1], p[2], p[2]]])
          .map(([c0, c1, r0, r1]) => [c0 - reach, c1 + reach, r0 - reach, r1 + reach]);
        for (const [c0, c1, r0, r1] of boxes) {
          for (let r = Math.floor(r0); r <= Math.floor(r1); r++) {
            for (let c = Math.floor(c0); c <= Math.floor(c1); c++) {
              const id = `${inst}/${c}_${r}`;
              if (!this.covers.has(id)) this.covers.set(id, new Set());
              this.covers.get(id).add(p[0]);
            }
          }
        }
        this.load(p[0]);
        return { p, k, reach, motion, boxes };
      });
      placed.sort((a, b) => Math.floor(a.p[2]) - Math.floor(b.p[2]) || Math.floor(a.p[1]) - Math.floor(b.p[1]) || a.k - b.k);
      this.lists.set(String(inst), placed);
    }
    this.reach = Math.max(0, ...this.reaches);
  }

  tileReady(instance, key) {
    if (!this.ready) return false;
    const id = `${instance}/${key}`;
    if (this.readyTiles.has(id)) return true;
    const pieces = this.covers.get(id);
    if (pieces) for (const i of pieces) if (!this.pics.get(i)?.ok) return false;
    this.readyTiles.add(id);
    return true;
  }

  areaReady(instance, [c0, c1, r0, r1]) {
    if (!this.ready) return false;
    for (let r = r0; r <= r1; r++) for (let c = c0; c <= c1; c++) if (!this.tileReady(instance, `${c}_${r}`)) return false;
    return true;
  }

  reachOf(i) {
    return this.reaches[i] || 0;
  }

  has(instance) {
    return (this.lists.get(String(instance))?.length || 0) > 0;
  }

  within(instance, c0, c1, r0, r1, t = null) {
    const out = [];
    for (const { p, reach, motion } of this.crossing(instance, [c0, c1, r0, r1]).list) {
      for (const [col, row, strength] of copiesAt(motion, p[1], p[2], t)) {
        if (meets([[col - reach, col + reach, row - reach, row + reach]], c0, c1, r0, r1)) out.push([p[0], col, row, p[3], strength]);
      }
    }
    return out;
  }

  over(instance, col, row, t = null) {
    return this.answer("over", [instance, col, row, t],
      () => this.within(instance, col, col, row, row, t).some((p) => Math.hypot(p[1] - col, p[2] - row) <= this.reachOf(p[0])));
  }

  answer(name, key, make) {
    const id = JSON.stringify(key), kept = (this.answers ||= {})[name];
    if (kept?.id === id) return kept.value;
    const value = make();
    this.answers[name] = { id, value };
    return value;
  }

  time(instance, box, tilePx) {
    const fast = this.crossing(instance, box).fast;
    if (!(fast > 0 && tilePx > 0)) return { t: null, next: null };
    const step = Math.min(MOTION.most, Math.max(MOTION.least, MOTION.stepPx / (fast / 60000 * tilePx)));
    const at = Math.floor(this.now() / step) * step;
    return { t: at / 60000, next: at + step };
  }

  crossing(instance, [c0, c1, r0, r1]) {
    const all = this.lists.get(String(instance)), key = `${instance} ${c0} ${c1} ${r0} ${r1}`;
    if (!all) return { list: [], fast: 0 };
    const kept = (this.crossKept ||= new Map()).get(key);
    if (kept?.all === all) return kept;
    const list = all.filter(({ boxes }) => meets(boxes, c0, c1, r0, r1));
    const fast = list.reduce((most, { motion }) => (motion ? Math.max(most, motion.fast) : most), 0);
    if (this.crossKept.size >= 64) this.crossKept.clear();
    const found = { all, list, fast };
    this.crossKept.set(key, found);
    return found;
  }

  shadowAt(instance, col, row, t, shade) {
    const { dx, dy, tx, ty } = shade;
    return this.answer("shadowAt", [instance, col, row, t, dx, dy, tx, ty], () => this.shadowFound(instance, col, row, t, shade));
  }

  shadowFound(instance, col, row, t, shade) {
    const { dx, dy, tx, ty } = shade, s = this.side, n = CLOUD_SHADOW.probe.side;
    const steps = Math.max(1, Math.ceil(Math.hypot(tx - dx, ty - dy) * CLOUD_SHADOW.probe.steps));
    const pieces = this.within(instance, ...shadowReach([col, col, row, row], shade), t)
      .map(([i, pc, pr, turn, strength]) => ({ alpha: this.alphaOf(i), pc, pr, strength, c: Math.cos(turn * Math.PI / 180), sn: Math.sin(turn * Math.PI / 180) }))
      .filter((p) => p.alpha);
    let most = 0;
    for (let k = 0; k <= steps; k++) {
      const ox = dx + (tx - dx) * k / steps, oy = dy + (ty - dy) * k / steps;
      let left = 1;
      for (const { alpha, pc, pr, strength, c, sn } of pieces) {
        const qx = col - pc - ox, qy = row - pr - oy, u = (qx * c + qy * sn) / s + 0.5, v = (qy * c - qx * sn) / s + 0.5;
        if (u >= 0 && u < 1 && v >= 0 && v < 1) left *= 1 - alpha[Math.floor(v * n) * n + Math.floor(u * n)] / 255 * strength;
      }
      most = Math.max(most, 1 - left);
    }
    return most;
  }

  alphaOf(i) {
    const pic = this.load(i);
    if (!pic?.ok) return null;
    if (pic.alpha === undefined) {
      const n = CLOUD_SHADOW.probe.side, g = this.canvas(n, n).getContext("2d", { willReadFrequently: true });
      g.drawImage(pic.img, 0, 0, n, n);
      const px = g.getImageData?.(0, 0, n, n)?.data;
      pic.alpha = px ? Uint8Array.from({ length: n * n }, (_, k) => px[k * 4 + 3]) : null;
    }
    return pic.alpha;
  }

  pictureFor(i, px) {
    const pic = this.load(i);
    if (!pic?.ok) return null;
    if (!pic.sizes) pic.sizes = this.shrink(pic.img);
    let best = pic.img;
    for (const c of pic.sizes) if (c.width >= px) best = c;
    return best;
  }

  load(i) {
    const name = this.index.pieces[i]?.name;
    if (!name) return null;
    let pic = this.pics.get(i);
    if (!pic) {
      const img = this.picture();
      pic = { img, ok: false, sizes: null };
      img.onload = () => { pic.ok = true; this.answers = {}; this.drawn(); };
      img.src = this.address(`/clouds/${encodeURIComponent(name)}.png`, this.index.version);
      this.pics.set(i, pic);
    }
    return pic;
  }

  shrink(img) {
    const out = [];
    let from = img, w = img.naturalWidth || img.width, h = img.naturalHeight || img.height;
    while (w / 2 >= CLOUDS_SMALLEST && h / 2 >= CLOUDS_SMALLEST) {
      w = Math.round(w / 2); h = Math.round(h / 2);
      const c = this.canvas(w, h), g = c.getContext("2d");
      g.imageSmoothingQuality = "high";
      g.drawImage(from, 0, 0, w, h);
      out.push(c);
      from = c;
    }
    return out;
  }

  paint(ctx, instance, [c0, c1, r0, r1], at, tile, devicePx, t = null) {
    let drawn = 0;
    const s = this.side, alpha = ctx.globalAlpha;
    for (const [i, col, row, turn, strength] of this.within(instance, c0, c1, r0, r1, t)) {
      const pic = this.pictureFor(i, s * Math.max(tile[0], tile[1]) * devicePx);
      if (!pic) continue;
      fadeTo(ctx, alpha * strength);
      placeCloud(ctx, pic, at(col, row), tile, turn, s, s);
      drawn++;
    }
    fadeTo(ctx, alpha);
    return drawn;
  }

  shadowFor(i, px) {
    const base = this.pictureFor(i, px);
    if (!base) return null;
    const pic = this.pics.get(i);
    if (!pic.shadows) pic.shadows = new Map();
    let mask = pic.shadows.get(base);
    if (!mask) {
      const w = base.naturalWidth || base.width, h = base.naturalHeight || base.height;
      mask = this.canvas(w, h);
      const g = mask.getContext("2d");
      g.drawImage(base, 0, 0, w, h);
      g.globalCompositeOperation = "source-in";
      g.fillStyle = "white";
      g.fillRect(0, 0, w, h);
      g.globalCompositeOperation = "destination-over";
      g.fillStyle = "black";
      g.fillRect(0, 0, w, h);
      pic.shadows.set(base, mask);
    }
    return mask;
  }

  paintShadows(g, instance, box, at, tile, devicePx, shade, t = null, off = null) {
    let drawn = 0;
    const s = this.side, alpha = g.globalAlpha;
    g.globalCompositeOperation = "screen";
    for (const [i, col, row, turn, strength] of this.within(instance, ...shadowReach(box, shade), t)) {
      const r = this.reachOf(i);
      if (off && meets([[col - r, col + r, row - r, row + r]], ...off)) continue;
      const mask = this.shadowFor(i, s * Math.max(tile[0], tile[1]) * devicePx);
      if (!mask) continue;
      fadeTo(g, alpha * strength);
      placeCloud(g, mask, at(col + shade.dx, row + shade.dy), tile, turn, s, s);
      drawn++;
    }
    fadeTo(g, alpha);
    g.globalCompositeOperation = "source-over";
    return drawn;
  }

  shadowPass(ctx, layer, jobs, devicePx, shade, take, alpha = 1, { picture = null, kept = false, keep = null, mask = null } = {}) {
    const strength = (take.light ? 1 : shade.strength) * alpha;
    if (!(strength >= 0.005)) return 0;
    const g = layer.getContext("2d"), [w, h] = [layer.width, layer.height], kx = w / ctx.canvas.width, ky = h / ctx.canvas.height;
    const c = ctx.getTransform(), m = { a: c.a * kx, b: c.b * ky, c: c.c * kx, d: c.d * ky, e: c.e * kx, f: c.f * ky };
    const laid = mask ? this.maskLaid(layer, mask) : null;
    const drawn = laid ?? (picture ? this.shadowMaskOf(layer, m, [kx, ky], picture, jobs[0], shade, devicePx * kx)
      : (kept ? this.shadowMaskKept(layer, m, jobs, devicePx * kx, shade) : null) ?? this.shadowMask(layer, m, jobs, devicePx * kx, shade));
    if (!drawn) return 0;
    if (keep && laid == null) {
      if (keep.width !== w || keep.height !== h) Object.assign(keep, { width: w, height: h });
      const k = keep.getContext("2d");
      k.globalCompositeOperation = "copy";
      k.drawImage(layer, 0, 0);
      k.globalCompositeOperation = "source-over";
    }
    g.globalCompositeOperation = "multiply";
    if (take.light) g.drawImage(take.light, 0, 0, w, h);
    g.fillStyle = `rgb(${(take.light ? [0, 0, 0] : take.rgb).map((v) => Math.round(strength * (255 - v))).join(", ")})`;
    g.fillRect(0, 0, w, h);
    g.globalCompositeOperation = "difference";
    g.fillStyle = "white";
    g.fillRect(0, 0, w, h);
    g.globalCompositeOperation = "destination-in";
    g.drawImage(ctx.canvas, 0, 0, w, h);
    g.globalCompositeOperation = "source-over";
    ctx.save();
    ctx.setTransform(1, 0, 0, 1, 0, 0);
    ctx.globalCompositeOperation = "multiply";
    ctx.drawImage(layer, 0, 0, ctx.canvas.width, ctx.canvas.height);
    ctx.restore();
    return drawn;
  }

  maskLaid(layer, { canvas, drawn }) {
    if (canvas.width !== layer.width || canvas.height !== layer.height) return null;
    const g = layer.getContext("2d");
    g.setTransform(1, 0, 0, 1, 0, 0);
    g.globalCompositeOperation = "copy";
    g.drawImage(canvas, 0, 0);
    g.globalCompositeOperation = "source-over";
    return drawn;
  }

  shadowMask(layer, m, jobs, devicePx, shade) {
    const g = layer.getContext("2d");
    g.setTransform(1, 0, 0, 1, 0, 0);
    g.fillStyle = "black";
    g.fillRect(0, 0, layer.width, layer.height);
    g.setTransform(m);
    let drawn = 0;
    for (const j of jobs) drawn += this.paintShadows(g, j.instance, j.box, j.at, j.tile, devicePx, shade, j.t);
    g.setTransform(1, 0, 0, 1, 0, 0);
    if (!drawn) return 0;
    const { at } = jobs[0], [a, b] = at(0, 0), [c, d] = at(shade.tx - shade.dx, shade.ty - shade.dy);
    const [vx, vy] = [c - a, d - b];
    this.sweep(g, [m.a * vx + m.c * vy, m.b * vx + m.d * vy]);
    return drawn;
  }

  shadowMaskOf(layer, m, [kx, ky], k, job, shade, devicePx) {
    const { at } = job, g = layer.getContext("2d");
    g.setTransform(1, 0, 0, 1, 0, 0);
    g.clearRect(0, 0, layer.width, layer.height);
    const way = (dc, dr) => { const [a, b] = at(0, 0), [c, d] = at(dc, dr), [vx, vy] = [c - a, d - b]; return [m.a * vx + m.c * vy, m.b * vx + m.d * vy]; };
    if (k.drawn) {
      const [a, b, c, d, e, f] = k.at, [ox, oy] = way(shade.dx, shade.dy);
      g.setTransform(a * kx, b * ky, c * kx, d * ky, e * kx + ox, f * ky + oy);
      g.drawImage(k.canvas, 0, 0);
      g.setTransform(1, 0, 0, 1, 0, 0);
    }
    g.globalCompositeOperation = "source-in";
    g.fillStyle = "white";
    g.fillRect(0, 0, layer.width, layer.height);
    g.globalCompositeOperation = "destination-over";
    g.fillStyle = "black";
    g.fillRect(0, 0, layer.width, layer.height);
    g.globalCompositeOperation = "source-over";
    let off = 0;
    if (k.region) {
      g.setTransform(m);
      off = this.paintShadows(g, job.instance, job.box, at, job.tile, devicePx, shade, job.t, k.region[0]);
      g.setTransform(1, 0, 0, 1, 0, 0);
    }
    if (k.drawn + off) this.sweep(g, way(shade.tx - shade.dx, shade.ty - shade.dy));
    return k.drawn + off;
  }

  shadowMaskKept(layer, m, jobs, devicePx, shade) {
    const reach = this.reach + Math.max(Math.abs(shade.tx - shade.dx), Math.abs(shade.ty - shade.dy));
    const sig = [shade.dx, shade.dy, shade.tx, shade.ty].map((v) => +v.toFixed(2));
    const k = this.keep("shadow", layer, m, jobs, sig, reach, (g, full, lin) => {
      g.save();
      g.setTransform(1, 0, 0, 1, 0, 0);
      g.fillStyle = "black";
      g.fillRect(0, 0, g.canvas.width, g.canvas.height);
      g.restore();
      let drawn = 0;
      for (const j of full) drawn += this.paintShadows(g, j.instance, j.box, j.at, j.tile, devicePx, shade);
      if (drawn) {
        const { at } = full[0], [a, b] = at(0, 0), [c, d] = at(shade.tx - shade.dx, shade.ty - shade.dy), [vx, vy] = [c - a, d - b];
        g.setTransform(1, 0, 0, 1, 0, 0);
        this.sweep(g, [lin[0] * vx + lin[2] * vy, lin[1] * vx + lin[3] * vy]);
      }
      return drawn;
    });
    if (!k) return null;
    const g = layer.getContext("2d");
    g.setTransform(1, 0, 0, 1, 0, 0);
    g.globalCompositeOperation = "source-over";
    g.fillStyle = "black";
    g.fillRect(0, 0, layer.width, layer.height);
    if (k.drawn) {
      g.setTransform(...k.at);
      g.drawImage(k.canvas, 0, 0);
      g.setTransform(1, 0, 0, 1, 0, 0);
    }
    return k.drawn;
  }

  keptPicture(ctx, jobs, devicePx) {
    const times = jobs.map((j) => j.t ?? null);
    return this.keep("clouds", ctx.canvas, ctx.getTransform(), jobs, times, this.reach, (g, full) => {
      let drawn = 0;
      for (const j of full) drawn += this.paint(g, j.instance, j.box, j.at, j.tile, devicePx, j.t);
      return drawn;
    }, ...(times.some((t) => t != null) ? [KEPT.moving, KEPT.still] : [KEPT.still]));
  }

  lay(ctx, k) {
    ctx.save();
    ctx.setTransform(...k.at);
    if (k.drawn) ctx.drawImage(k.canvas, 0, 0);
    ctx.restore();
    return k.drawn;
  }

  paintKept(ctx, jobs, devicePx) {
    const k = this.keptPicture(ctx, jobs, devicePx);
    return k ? this.lay(ctx, k) : null;
  }

  keep(name, screen, m, jobs, sig, pad, draw, regions = KEPT.still, moving = regions) {
    if (!jobs.length) return null;
    const lin = [m.a, m.b, m.c, m.d], scaleKey = JSON.stringify(lin.map((v) => +v.toFixed(6)));
    const frameKey = JSON.stringify([...lin, m.e, m.f].map((v) => +v.toFixed(3)));
    let ok = 0;
    for (const p of this.pics.values()) if (p.ok) ok++;
    const what = JSON.stringify([name, jobs.map((j) => j.instance), this.index.version]), base = JSON.stringify([what, sig, ok]);
    const kept = (this.kept ||= new Map());
    if (!kept.has(name)) kept.set(name, {});
    const k = kept.get(name), settled = this.settled(), resting = k.frame === frameKey;
    k.frame = frameKey;
    const inside = () => !k.region || jobs.every((j, i) => k.region[i] && Math.max(0, j.box[0]) >= k.region[i][0]
      && Math.min(63, j.box[1]) <= k.region[i][1] && Math.max(0, j.box[2]) >= k.region[i][2] && Math.min(63, j.box[3]) <= k.region[i][3]);
    const covers = () => !!k.canvas && k.what === what && k.big !== scaleKey && inside();
    if (!(covers() && k.base === base && k.scaleKey === scaleKey) && (settled || !covers()) && k.big !== scaleKey) {
      const part = (share) => jobs.map((j) => {
        const [c0, c1, r0, r1] = j.box, mc = Math.ceil((c1 - c0 + 1) * share), mr = Math.ceil((r1 - r0 + 1) * share);
        return [Math.max(0, c0 - mc), Math.min(63, c1 + mc), Math.max(0, r0 - mr), Math.min(63, r1 + mr)];
      });
      let made = null;
      for (const share of resting ? regions : moving) {
        const boxes = share == null ? null : part(share);
        const region = boxes?.some((b) => b.join() !== "0,63,0,63") ? boxes : null;
        made = this.frame(lin, jobs.map((j, i) => ({ ...j, box: region ? region[i] : [0, 63, 0, 63] })), pad, screen, share == null ? KEPT.area : KEPT.part);
        if (made) { made.region = region; break; }
      }
      if (!made) {
        k.big = scaleKey;
        return null;
      }
      const { full, bx, by, w, h, region } = made;
      const canvas = k.canvas || this.canvas(1, 1), g = canvas.getContext("2d");
      if (canvas.width === w && canvas.height === h) {
        Object.assign(g, { globalAlpha: 1, globalCompositeOperation: "source-over" });
        g.setTransform(1, 0, 0, 1, 0, 0);
        g.clearRect(0, 0, w, h);
      } else Object.assign(canvas, { width: w, height: h });
      const fe = m.e - Math.floor(m.e), ff = m.f - Math.floor(m.f);
      g.setTransform(lin[0], lin[1], lin[2], lin[3], fe - bx, ff - by);
      const drawn = draw(g, full, lin);
      g.setTransform(1, 0, 0, 1, 0, 0);
      g.globalCompositeOperation = "source-over";
      Object.assign(k, { what, base, scaleKey, lin, canvas, bx: bx - fe, by: by - ff, drawn, region, big: null });
      this.builds = (this.builds || 0) + 1;
    }
    if (!covers()) return null;
    if (k.scaleKey === scaleKey) return { canvas: k.canvas, at: [1, 0, 0, 1, m.e + k.bx, m.f + k.by], drawn: k.drawn, region: k.region };
    const [a, b, c, d] = k.lin, det = a * d - b * c;
    const ia = d / det, ib = -b / det, ic = -c / det, id = a / det;
    const t = [lin[0] * ia + lin[2] * ib, lin[1] * ia + lin[3] * ib, lin[0] * ic + lin[2] * id, lin[1] * ic + lin[3] * id];
    return { canvas: k.canvas, at: [...t, t[0] * k.bx + t[2] * k.by + m.e, t[1] * k.bx + t[3] * k.by + m.f], drawn: k.drawn, region: k.region };
  }

  frame(lin, full, pad, screen, area) {
    let x0 = Infinity, y0 = Infinity, x1 = -Infinity, y1 = -Infinity;
    for (const j of full) {
      const [c0, c1, r0, r1] = j.box;
      for (const [c, r] of [[c0 - pad, r0 - pad], [c1 + 1 + pad, r0 - pad], [c0 - pad, r1 + 1 + pad], [c1 + 1 + pad, r1 + 1 + pad]]) {
        const [fx, fy] = j.at(c, r), dx = lin[0] * fx + lin[2] * fy, dy = lin[1] * fx + lin[3] * fy;
        x0 = Math.min(x0, dx); x1 = Math.max(x1, dx); y0 = Math.min(y0, dy); y1 = Math.max(y1, dy);
      }
    }
    const bx = Math.floor(x0), by = Math.floor(y0), w = Math.ceil(x1) - bx, h = Math.ceil(y1) - by;
    if (!(w > 0 && h > 0) || w * h > area * screen.width * screen.height || Math.max(w, h) > KEPT.side) return null;
    return { full, bx, by, w, h };
  }

  sweep(g, [x, y]) {
    const length = Math.hypot(x, y);
    if (!(length >= CLOUD_SHADOW.step / 2)) return 0;
    const passes = Math.ceil(Math.log2(Math.max(2, length / CLOUD_SHADOW.step))), unit = 1 / 2 ** passes;
    const spare = this.spare ||= this.canvas(1, 1), w = g.canvas.width, h = g.canvas.height;
    if (spare.width !== w || spare.height !== h) Object.assign(spare, { width: w, height: h });
    const k = spare.getContext("2d");
    for (let p = 0; p < passes; p++) {
      const by = unit * 2 ** p;
      k.globalCompositeOperation = "copy";
      k.drawImage(g.canvas, 0, 0);
      g.globalCompositeOperation = "lighten";
      g.drawImage(spare, x * by, y * by);
    }
    g.globalCompositeOperation = "source-over";
    return passes;
  }
}

function fadeTo(ctx, alpha) {
  if (ctx.globalAlpha !== alpha) ctx.globalAlpha = alpha;
}

function placeCloud(ctx, img, [x, y], tile, turn, w, h) {
  ctx.save();
  ctx.translate(x, y);
  ctx.scale(tile[0], tile[1]);
  ctx.rotate(turn * Math.PI / 180);
  ctx.drawImage(img, -w / 2, -h / 2, w, h);
  ctx.restore();
}

if (typeof module === "object") {
  module.exports = { Clouds, CLOUDS_SMALLEST, CLOUD_SHADOW, KEPT, MOTION, cloudShade, shadowReach, groundLight, copiesAt };
}
