// The Index of Azeroth. Copyright 2026 Index Case <indexofazeroth@pm.me>. PolyForm Strict 1.0.0, see LICENSE.md.
"use strict";

const SEA_GIANTS = {
  giants: {
    cthulu: { at: [779 / 1002, 61 / 668], map: 1415 },
    turtle: { at: [365 / 1002, 104 / 668], map: 1414 },
    seaserpent: { at: [102 / 1002, 183 / 668], map: 1414 },
  },
  length: 360, offset: 450, zoom: [4.1, 4.7],
  depth: { size: [1.08, 0.92], opacity: [0.4, 0.22] },
  shade: 0.45, patch: 24, resample: 20000,
};

function giantLook(shapes, rand, g = SEA_GIANTS) {
  const shape = Math.min(shapes - 1, Math.floor(rand() * shapes)), facing = rand() * 2 * Math.PI;
  const r = g.offset * Math.sqrt(rand()), way = rand() * 2 * Math.PI, depth = rand();
  const by = ([shallow, deep]) => shallow + (deep - shallow) * depth;
  return { shape, facing, dn: r * Math.sin(way), dw: r * Math.cos(way), depth, size: by(g.depth.size), opacity: by(g.depth.opacity) };
}

const giantFade = (zoom, g = SEA_GIANTS) => (zoom < g.zoom[0] ? 0 : smoothHour(g.zoom[0], g.zoom[1], zoom));

const giantZoom = (mapYards, fitPx, ypx) => mapYards / (fitPx * ypx);

const giantOnScreen = (s, n, w) => ({ x: s[0] * n + s[3] * w + s[6], y: s[1] * n + s[4] * w + s[7] });

function giantSeaColour(rgba) {
  const ch = [[], [], []];
  for (let i = 0; i + 3 < rgba.length; i += 4) {
    if (rgba[i + 3] === 0) continue;
    for (let c = 0; c < 3; c++) ch[c].push(rgba[i + c]);
  }
  if (!ch[0].length) return null;
  return ch.map((v) => v.sort((a, b) => a - b)[v.length >> 1]);
}

const giantTint = (sea, g = SEA_GIANTS) => `rgb(${sea.map((v) => Math.round(v * g.shade)).join(", ")})`;

class SeaGiants {
  constructor({ image, address, drawn, canvas = () => document.createElement("canvas"), now = () => performance.now(), rand = Math.random }) {
    Object.assign(this, { image, address, drawn, canvas, now, rand });
    this.index = {};
    this.images = new Map();
    this.looks = {};
  }

  setIndex(index) {
    const next = index && typeof index === "object" ? index : {};
    for (const name of Object.keys(this.looks)) {
      if (JSON.stringify(next[name]) !== JSON.stringify(this.index[name])) delete this.looks[name];
    }
    this.index = next;
  }

  away() {
    this.looks = {};
  }

  picture(shape) {
    const url = this.address(`art/seagiants/${shape.image}`, shape.v), got = this.images.get(url);
    if (got) return got.img ?? null;
    const held = {};
    this.images.set(url, held);
    Promise.resolve(this.image(url)).then((img) => img, () => null).then((img) => {
      held.img = img || null;
      this.drawn();
    });
    return null;
  }

  coloured(ctx, look, img, size, p) {
    const g = SEA_GIANTS, now = this.now();
    if (!look.tint || now - look.read >= g.resample) {
      const t = ctx.getTransform(), cw = ctx.canvas.width, chh = ctx.canvas.height, half = g.patch / 2;
      const x = Math.min(Math.max(t.a * p.x + t.c * p.y + t.e, half), cw - half), y = Math.min(Math.max(t.b * p.x + t.d * p.y + t.f, half), chh - half);
      const sea = giantSeaColour(ctx.getImageData(Math.round(x - half), Math.round(y - half), g.patch, g.patch).data);
      look.read = now;
      if (sea && giantTint(sea) !== look.tint) {
        look.tint = giantTint(sea);
        const cv = (look.shaped ||= this.canvas()), c = cv.getContext("2d");
        Object.assign(cv, { width: size[0], height: size[1] });
        c.globalCompositeOperation = "source-over";
        c.fillStyle = look.tint;
        c.fillRect(0, 0, size[0], size[1]);
        c.globalCompositeOperation = "destination-in";
        c.drawImage(img, 0, 0);
      }
    }
    return look.shaped || null;
  }

  drawOn(ctx, { at, onWorld, width, height, fitPx, mapYards }) {
    if (!onWorld || !(width > 0) || !(height > 0) || !(fitPx > 0)) { this.away(); return 0; }
    const g = SEA_GIANTS, view = viewMatrix(at, width, height), frame = screenMatrix(view), ypx = Math.hypot(view[0], view[1]);
    const spot = worldPlace(onWorld), reach = (g.offset + (g.length * Math.max(...g.depth.size)) / 2) / ypx;
    let drew = 0;
    for (const [name, giant] of Object.entries(g.giants)) {
      const shapes = this.index[name], eye = frameAt(spot, ...giant.at), c = giantOnScreen(frame, eye.n, eye.w);
      const near = c.x > -reach && c.x < width + reach && c.y > -reach && c.y < height + reach;
      const fade = giantFade(giantZoom(mapYards(giant.map), fitPx, ypx));
      if (!shapes?.length || !near || !(fade > 0)) { delete this.looks[name]; continue; }
      const look = (this.looks[name] ||= giantLook(shapes.length, this.rand));
      const shape = shapes[look.shape], img = this.picture(shape);
      if (!img) continue;
      const p = giantOnScreen(frame, eye.n + look.dn, eye.w + look.dw), north = giantOnScreen(frame, eye.n + look.dn + 1, eye.w + look.dw);
      const k = (g.length * look.size) / ypx / (shape.body || Math.max(...shape.size)), turn = Math.atan2(north.y - p.y, north.x - p.x) + Math.PI / 2 + look.facing;
      if (!giantOnView(shape.size, p, k, width, height)) continue;
      const shaped = this.coloured(ctx, look, img, shape.size, p);
      if (!shaped) continue;
      giantLaid(ctx, shaped, shape.size, p, k, turn, look.opacity * fade);
      drew++;
    }
    return drew;
  }
}

function giantOnView(size, p, k, width, height) {
  const half = (Math.hypot(...size) * k) / 2;
  return !(p.x + half <= 0 || p.y + half <= 0 || p.x - half >= width || p.y - half >= height);
}

function giantLaid(ctx, picture, size, p, k, turn, opacity) {
  ctx.save();
  ctx.globalCompositeOperation = "soft-light";
  ctx.globalAlpha *= opacity;
  ctx.translate(p.x, p.y);
  ctx.rotate(turn);
  ctx.drawImage(picture, (-size[0] * k) / 2, (-size[1] * k) / 2, size[0] * k, size[1] * k);
  ctx.restore();
}

if (typeof module === "object") {
  module.exports = { SEA_GIANTS, giantLook, giantFade, giantZoom, giantOnScreen, giantSeaColour, giantTint, SeaGiants };
}
