// The Index of Azeroth. Copyright 2026 Index Case <indexofazeroth@pm.me>. PolyForm Strict 1.0.0, see LICENSE.md.
"use strict";

const BELOW = {
  distance: { map: 1415, zoom: 1.94 },
  at: [0.48, 0.3],
  pan: 0.25,
  grow: 0.05,
  blur: { px: 2, rise: 0.45 },
  res: 0.25,
  margin: 160,
  haze: 0.16,
  rim: { yards: 100, most: 220, alpha: 0.6, thin: 0.4, res: 0.25 },
  height: 24000,
  longest: 7000,
  shadow: 0.55,
  void: [9, 36],
  mask: 512,
  shape: 16,
  clouds: {
    between: [{ band: "medium", at: [-2300, 1500], yards: 2600, depth: 0.35, alpha: 0.8 },
              { band: "light", at: [2600, -1300], yards: 2200, depth: 0.2, alpha: 0.7 }],
    rim: [{ band: "light", at: [0.62, 0.95], yards: 900, alpha: 0.85 }, { band: "light", at: [0.31, 0.6], yards: 700, alpha: 0.7 }],
  },
};

function voidMatrix([lo, hi] = BELOW.void) {
  const s = +(255 / (hi - lo)).toFixed(5);
  return [0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, -s, -s, -s, 0, +(hi / (hi - lo)).toFixed(5)];
}
function voidAlpha([r, g, b], [lo, hi] = BELOW.void) {
  return Math.min(1, Math.max(0, (hi - r - g - b) / (hi - lo)));
}

function belowFrame({ zoom, mid, base }) {
  const z = Math.max(1, zoom), k = base * z ** BELOW.grow;
  return { k, base, zoom: z, mid, blur: BELOW.blur.px * z ** BELOW.blur.rise, pan: [mid[0] * k * BELOW.pan, mid[1] * k * BELOW.pan] };
}

function shadowShift(ground) {
  if (!ground || !(ground.tan > 0) || !(ground.strength > 0)) return null;
  const far = Math.min(BELOW.longest, BELOW.height / ground.tan);
  return { x: -ground.dir[0] * far, y: -ground.dir[1] * far, strength: +(ground.strength * BELOW.shadow).toFixed(4) };
}

function rimThin(zoom) {
  return Math.max(1, zoom) ** -BELOW.rim.thin;
}

function betweenAt(cloud, f, near) {
  const d = cloud.depth, perYard = f.k * near ** d, share = BELOW.pan + (1 - BELOW.pan) * d;
  return { x: (f.mid[0] * share + cloud.at[0]) * perYard, y: (f.mid[1] * share + cloud.at[1]) * perYard, size: cloud.yards * perYard };
}

const rgbOf = (c, a = 1) => `rgba(${c.map((v) => Math.round(Math.min(255, Math.max(0, v)))).join(", ")}, ${a})`;

class Below {
  constructor({ el, canvas, doc = null, now = () => performance.now() }) {
    Object.assign(this, { el, canvas, doc, now });
    this.key = null;
    this.kept = {};
    this.masks = new WeakMap();
    this.cost = { paint: 0, rim: 0, paints: 0, layers: 0 };
  }

  voidMask(img, parts = []) {
    const shaped = parts.filter((p) => p.img).length, kept = this.masks.get(img);
    if (kept && kept.shaped === shaped) return kept.canvas;
    const n = Math.min(BELOW.mask, img.naturalWidth || img.width || BELOW.mask);
    const c = kept ? kept.canvas : this.canvas(n, n), g = c.getContext("2d");
    g.setTransform(1, 0, 0, 1, 0, 0);
    g.globalCompositeOperation = "copy";
    g.filter = this.voidFilter();
    g.drawImage(img, 0, 0, n, n);
    g.filter = "none";
    g.globalCompositeOperation = "destination-out";
    for (const p of parts) if (p.img) g.drawImage(p.img, p.at[0] * n, p.at[1] * n, p.at[2] * n, p.at[3] * n);
    g.globalCompositeOperation = "source-over";
    this.masks.set(img, { canvas: c, shaped });
    return c;
  }

  voidFilter() {
    if (!this.doc?.createElementNS) return "none";
    const id = "below-void";
    if (!this.doc.getElementById(id)) {
      const ns = "http://www.w3.org/2000/svg", svg = this.doc.createElementNS(ns, "svg"), filter = this.doc.createElementNS(ns, "filter");
      const m = this.doc.createElementNS(ns, "feColorMatrix");
      svg.setAttribute("width", "0");
      svg.setAttribute("height", "0");
      svg.setAttribute("style", "position: absolute");
      svg.setAttribute("aria-hidden", "true");
      filter.setAttribute("id", id);
      filter.setAttribute("color-interpolation-filters", "sRGB");
      m.setAttribute("type", "matrix");
      m.setAttribute("values", voidMatrix().join(" "));
      filter.append(m);
      svg.append(filter);
      this.doc.body.append(svg);
    }
    return `url(#${id})`;
  }

  sized(name, w, h) {
    const c = this.kept[name] ||= this.canvas(w, h);
    if (c.width !== w || c.height !== h) Object.assign(c, { width: w, height: h });
    const g = c.getContext("2d");
    g.setTransform(1, 0, 0, 1, 0, 0);
    Object.assign(g, { globalAlpha: 1, globalCompositeOperation: "source-over", filter: "none" });
    g.clearRect(0, 0, w, h);
    return g;
  }

  hide() {
    this.el.hidden = true;
    this.key = null;
  }

  silhouette(blocks, w, h, ink) {
    const key = `${w}x${h}:${blocks.length}:${blocks.map((b) => (b.parts || []).filter((p) => p.img).length).join(",")}`;
    if (this.kept.shape && this.shapeKey === key) return this.kept.shape;
    const g = this.sized("shape", w, h);
    for (const b of blocks) {
      g.globalCompositeOperation = "source-over";
      g.drawImage(b.img, ...b.at);
      g.globalCompositeOperation = "destination-out";
      g.drawImage(this.voidMask(b.img, b.parts), ...b.at);
    }
    g.globalCompositeOperation = "source-in";
    g.fillStyle = ink;
    g.fillRect(0, 0, w, h);
    this.shapeKey = key;
    return this.kept.shape;
  }

  layer(v, at) {
    const k = v.frame.base, reach = Math.hypot(v.W, v.H) / 2 + BELOW.margin, side = 2 * reach;
    const key = JSON.stringify([v.W, v.H, k, v.sea, at, v.perFrac, v.world.length, v.key ?? null]);
    if (this.layerAt && this.layerKey === key) return this.layerAt;
    const r = BELOW.res, n = Math.max(1, Math.round(side * r)), g = this.sized("layer", n, n);
    g.fillStyle = rgbOf(v.sea);
    g.fillRect(0, 0, n, n);
    g.setTransform(r, 0, 0, r, n / 2, n / 2);
    const [kx, ky] = [k * v.perFrac[0], k * v.perFrac[1]];
    for (const b of v.world) {
      const x0 = (b.from[0] - at[0]) * kx, y0 = (b.from[1] - at[1]) * ky;
      g.drawImage(b.img, x0, y0, (b.to[0] - at[0]) * kx - x0, (b.to[1] - at[1]) * ky - y0);
    }
    if (v.over) v.over(g, [kx, ky], at, reach);
    this.layerKey = key;
    this.layerAt = { side: n / r, k };
    this.cost.layers++;
    return this.layerAt;
  }

  paint(v) {
    this.el.hidden = false;
    const f = v.frame, at = v.at || BELOW.at;
    const key = JSON.stringify([v.W, v.H, v.rot, f, v.px, v.sea, v.light, at, v.world.length, v.shadow && [v.shadow.box, v.shadow.shift],
      v.clouds.length, v.key ?? null]);
    if (key === this.key) return false;
    this.key = key;
    const t0 = this.now(), r = BELOW.res, w = Math.max(1, Math.round(v.W * r)), h = Math.max(1, Math.round(v.H * r));
    const pad = Math.ceil(3 * f.blur * r), layer = this.layer(v, at), g = this.sized("world", w + 2 * pad, h + 2 * pad);
    g.setTransform(r, 0, 0, r, pad, pad);
    g.translate(v.W / 2, v.H / 2);
    g.rotate(v.rot);
    g.translate(...f.pan);
    const grown = layer.side * f.k / layer.k;
    g.drawImage(this.kept.layer, -grown / 2, -grown / 2, grown, grown);
    const s = v.shadow;
    if (s?.shift) {
      g.globalAlpha = s.shift.strength;
      const [x0, y0, x1, y1] = s.box.map((q, i) => (q + (i % 2 ? s.shift.y : s.shift.x)) * f.k);
      g.drawImage(s.img, x0, y0, x1 - x0, y1 - y0);
      g.globalAlpha = 1;
    }
    g.setTransform(1, 0, 0, 1, 0, 0);
    g.globalCompositeOperation = "multiply";
    g.fillStyle = rgbOf(v.light.k.map((q) => q * 255));
    g.fillRect(0, 0, w + 2 * pad, h + 2 * pad);
    if (this.el.width !== w || this.el.height !== h) Object.assign(this.el, { width: w, height: h });
    const o = this.el.getContext("2d");
    o.setTransform(1, 0, 0, 1, 0, 0);
    o.globalAlpha = 1;
    o.globalCompositeOperation = "copy";
    o.filter = `blur(${+(f.blur * r).toFixed(2)}px)${v.light.night === "none" ? "" : ` ${v.light.night}`}`;
    o.drawImage(this.kept.world, -pad, -pad);
    o.globalCompositeOperation = "source-over";
    o.filter = "none";
    o.fillStyle = rgbOf(v.light.haze, BELOW.haze);
    o.fillRect(0, 0, w, h);
    o.setTransform(r, 0, 0, r, 0, 0);
    o.translate(v.W / 2, v.H / 2);
    o.rotate(v.rot);
    for (const { img, cloud } of v.clouds) {
      const p = betweenAt(cloud, f, v.px / f.zoom / f.base);
      o.filter = `blur(${+(f.blur * r * (1 - cloud.depth)).toFixed(2)}px) brightness(${v.light.share})`;
      o.globalAlpha = cloud.alpha;
      o.drawImage(img, p.x - p.size / 2, p.y - p.size / 2, p.size, p.size);
    }
    o.filter = "none";
    o.globalAlpha = 1;
    this.cost.paint = +(this.now() - t0).toFixed(2);
    this.cost.paints++;
    return true;
  }

  rim(ground, W, H, colour, px) {
    const t0 = this.now(), r = BELOW.rim.res, w = Math.max(1, Math.round(W * r)), h = Math.max(1, Math.round(H * r));
    const blur = Math.min(BELOW.rim.most, BELOW.rim.yards * px) * r, pad = Math.ceil(3 * blur);
    const m = this.sized("mask", w, h);
    m.drawImage(ground, 0, 0, w, h);
    const mask = this.kept.mask, p = this.sized("spread", w + 2 * pad, h + 2 * pad);
    p.drawImage(mask, pad, pad);
    for (const [sx, sy, sw, sh, dx, dy, dw, dh] of [[0, 0, w, 1, pad, 0, w, pad], [0, h - 1, w, 1, pad, h + pad, w, pad],
      [0, 0, 1, h, 0, pad, pad, h], [w - 1, 0, 1, h, w + pad, pad, pad, h], [0, 0, 1, 1, 0, 0, pad, pad],
      [w - 1, 0, 1, 1, w + pad, 0, pad, pad], [0, h - 1, 1, 1, 0, h + pad, pad, pad], [w - 1, h - 1, 1, 1, w + pad, h + pad, pad, pad]]) {
      p.drawImage(mask, sx, sy, sw, sh, dx, dy, dw, dh);
    }
    const b = this.sized("soft", w, h);
    b.filter = `blur(${+blur.toFixed(2)}px)`;
    b.drawImage(this.kept.spread, -pad, -pad);
    b.filter = "none";
    const band = this.sized("band", w, h);
    band.drawImage(mask, 0, 0);
    band.globalCompositeOperation = "destination-out";
    band.drawImage(this.kept.soft, 0, 0);
    b.globalCompositeOperation = "destination-out";
    b.drawImage(mask, 0, 0);
    band.globalCompositeOperation = "lighter";
    band.drawImage(this.kept.soft, 0, 0);
    band.drawImage(this.kept.band, 0, 0);
    band.globalCompositeOperation = "source-in";
    band.fillStyle = rgbOf(colour);
    band.fillRect(0, 0, w, h);
    this.cost.rim = +(this.now() - t0).toFixed(2);
    return this.kept.band;
  }

  lay(ctx, W, H, rim, clouds = [], share = 1, zoom = 1) {
    const thin = rimThin(zoom);
    ctx.globalAlpha = BELOW.rim.alpha * thin;
    ctx.drawImage(rim, 0, 0, W, H);
    if (share < 1) ctx.filter = `brightness(${share})`;
    for (const c of clouds) {
      ctx.globalAlpha = c.alpha * thin;
      ctx.drawImage(c.img, c.x - c.size / 2, c.y - c.size / 2, c.size, c.size);
    }
    ctx.filter = "none";
    ctx.globalAlpha = 1;
  }
}

if (typeof module === "object") module.exports = { BELOW, voidMatrix, voidAlpha, belowFrame, shadowShift, rimThin, betweenAt, Below };
