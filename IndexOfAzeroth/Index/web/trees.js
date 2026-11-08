// The Index of Azeroth. Copyright 2026 Index Case <indexofazeroth@pm.me>. PolyForm Strict 1.0.0, see LICENSE.md.
"use strict";

const TREES = { instances: [0, 1], most: 300, far: 0.5, side: 256, perFrame: 4 };
const SHEETS_KEPT = 4 * TREES.most;
const LISTS_KEPT = 2 * TREES.most;

const treeOut = (tree) => tree[5] !== 0;
const canopyOff = (tree, off) => tree[7] === 1 && off.has(tree[6]);

const SEE = { amount: { buildings: 0.97, roads: 0.97, you: 0.8 }, fade: 2, gain: 4, side: 256, kinds: ["buildings", "roads"], looked: 16,
  you: { inner: 18, outer: 34 }, ground: ["roads"] };
const HOLES_KEPT = SEE.kinds.length * TREES.most;
const NO_ROOFS = Object.freeze({ img: null, ok: false, gone: true });

function treeReach(model, px, scale) {
  const [ox, oy, w, h] = model;
  return Math.hypot(Math.max(ox, w - ox), Math.max(oy, h - oy)) * px * scale;
}

function treeTiles(box, tileYards, has) {
  const col = (w) => Math.floor(32 - w / tileYards), row = (n) => Math.floor(32 - n / tileYards);
  const out = [];
  for (let r = Math.max(0, row(box.nHi)); r <= Math.min(63, row(box.nLo)); r++) {
    for (let c = Math.max(0, col(box.wHi)); c <= Math.min(63, col(box.wLo)); c++) if (has(`${c}_${r}`)) out.push(`${c}_${r}`);
  }
  return out;
}

function worldBox(points, pad = 0) {
  const ns = points.map((p) => p.n), ws = points.map((p) => p.w);
  return { nHi: Math.max(...ns) + pad, nLo: Math.min(...ns) - pad, wHi: Math.max(...ws) + pad, wLo: Math.min(...ws) - pad };
}

function treeMatrix(tree, model, px, at, k) {
  const yaw = (tree[3] * Math.PI) / 180, s = tree[4] * px, cos = Math.cos(yaw), sin = Math.sin(yaw);
  const a = k[0] * cos * s, b = -k[1] * sin * s, c = k[0] * sin * s, d = k[1] * cos * s;
  return [a, b, c, d, at[0] - (a * model[0] + c * model[1]), at[1] - (b * model[0] + d * model[1])];
}

function timesMatrix(m, n) {
  return [m[0] * n[0] + m[2] * n[1], m[1] * n[0] + m[3] * n[1], m[0] * n[2] + m[2] * n[3], m[1] * n[2] + m[3] * n[3],
    m[0] * n[4] + m[2] * n[5] + m[4], m[1] * n[4] + m[3] * n[5] + m[5]];
}

function keptMap(map, key, value, most) {
  map.delete(key);
  map.set(key, value);
  if (map.size > most) map.delete(map.keys().next().value);
  return value;
}

const tileCorner = (key, tileYards) => {
  const [col, row] = key.split("_").map(Number);
  return { n: (32 - row) * tileYards, w: (32 - col) * tileYards };
};

function blockStep(keys) {
  let step = 1;
  while (new Set(keys.map((key) => blockOf(key, step))).size > TREES.most) step *= 2;
  return step;
}
const blockOf = (key, step) => key.split("_").map((v) => Math.floor(Number(v) / step)).join("_");
const blockCorner = (block, step, tileYards) => tileCorner(block.split("_").map((v) => Number(v) * step).join("_"), tileYards);
function blockTiles(block, step) {
  const [bcol, brow] = block.split("_").map(Number), keys = [];
  for (let row = brow * step; row < (brow + 1) * step; row++) for (let col = bcol * step; col < (bcol + 1) * step; col++) keys.push(`${col}_${row}`);
  return keys;
}

const holeBlur = (yards, side, tileYards) => (yards * side) / tileYards;

class Trees {
  constructor({ json, image, canvas, drawn, ink, address, indexed = () => {} }) {
    Object.assign(this, { json, image, canvas, drawn, ink, address, indexed });
    this.index = null;
    this.off = new Set();
    this.asked = false;
    this.lists = new Map();
    this.pictures = new Map();
    this.shown = new Map();
    this.holes = new Map();
    this.sheets = new Map();
    this.marks = { lists: null, sheets: null };
    this.margin = 0;
  }

  start() {
    if (this.asked) return;
    this.asked = true;
    this.json(`/api/trees/index.json?v=${Date.now()}`).then((index) => {
      if (!index?.models) { this.asked = false; return; }
      this.index = { ...index, tiles: Object.fromEntries(Object.entries(index.tiles || {}).map(([i, keys]) => [i, new Set(keys)])) };
      this.marks = { lists: index.placed, sheets: this.sheetsMark() };
      this.margin = Math.max(0, ...Object.entries(index.models).map(([fid, m]) => treeReach(m, index.px, index.scales?.[fid] ?? 0)));
      this.indexed();
      this.drawn();
    });
  }

  sheetsMark() { return JSON.stringify([this.index?.placed, this.index?.models, [...this.off].sort((a, b) => a - b)]); }

  canopy(zones) {
    this.off = new Set(zones.map(Number));
    this.marks.sheets = this.sheetsMark();
    this.drawn();
  }

  canopyZones() { return Object.keys(this.index?.canopy || {}).map(Number); }

  reload() {
    if (!this.index) return;
    this.asked = false;
    this.start();
  }

  ready() { return !!this.index; }

  has(instance, key) { return !!this.index?.tiles[instance]?.has(key); }

  list(instance, key) {
    const id = `${instance}/${key}`, mark = this.marks.lists, kept = this.lists.get(id);
    if (kept) keptMap(this.lists, id, kept, LISTS_KEPT);
    if (kept && kept.mark === mark) return kept.trees;
    const entry = { trees: kept ? kept.trees : null, mark, asking: true };
    keptMap(this.lists, id, entry, LISTS_KEPT);
    this.json(`/api/trees/${id}.json`).then((got) => {
      entry.asking = false;
      if (!got) { entry.mark = null; return; }
      entry.trees = got.trees || [];
      this.drawn();
    });
    return entry.trees;
  }

  listNow(instance, key) {
    const trees = this.list(instance, key), kept = this.lists.get(`${instance}/${key}`);
    return kept && !kept.asking ? trees : null;
  }

  shapeUrl(id, band = null) {
    const [instance, key] = id.split("/"), digest = this.index?.shapes?.[instance]?.[key];
    if (!digest) return null;
    if (band && band.far) return this.address(`/api/trees/far/${band.side}/${id}.png`, digest);
    if (band && (this.index.close || []).includes(band.side)) return this.address(`/api/trees/close/${band.side}/${id}.png`, digest);
    return this.address(`/api/trees/shape/${id}.png`, digest);
  }

  tallest(id) {
    const [instance, key] = id.split("/");
    return this.index?.tall?.[instance]?.[key] ?? 0;
  }

  full(id) {
    const [instance, key] = id.split("/");
    return this.index?.full?.[instance]?.[key] ?? null;
  }

  picture(fid, model) {
    const key = `${fid}|${model[4]}`;
    if (!this.pictures.has(key)) this.pictures.set(key, this.image(this.address(`/api/trees/models/${fid}.png`, model[4])));
    return this.pictures.get(key);
  }

  draw(ctx, base, trees, view, at, k, out = null, gone = false) {
    const px = this.index.px, models = this.index.models;
    let count = 0;
    for (const tree of trees) {
      const [fid, n, w, , scale] = tree, model = models[fid];
      if (!model || (out != null && treeOut(tree) !== out) || canopyOff(tree, this.off) !== gone) continue;
      const reach = treeReach(model, px, scale);
      if (view && (n - reach > view.nHi || n + reach < view.nLo || w - reach > view.wHi || w + reach < view.wLo)) continue;
      const pic = this.picture(fid, model);
      if (pic.ok) this.shown.set(fid, { img: pic.img, model });
      const shown = this.shown.get(fid);
      if (!shown) continue;
      ctx.setTransform(...timesMatrix(base, treeMatrix(tree, shown.model, px, at(n, w), k)));
      ctx.drawImage(shown.img, 0, 0);
      count++;
    }
    ctx.setTransform(...base);
    return count;
  }

  picturesIn(trees) {
    const models = this.index.models;
    return trees.every((t) => !models[t[0]] || this.picture(t[0], models[t[0]]).ok);
  }

  sheet(id, nw, across, trees, gone = false) {
    const px = this.index.px, models = this.index.models;
    if (!trees.length) return keptMap(this.sheets, id, { canvas: null, pad: 0, count: 0, mark: this.marks.sheets }, SHEETS_KEPT);
    const pad = Math.ceil(Math.max(0, ...trees.map((t) => (models[t[0]] ? treeReach(models[t[0]], px, t[4]) : 0))));
    const a = TREES.side / across, size = Math.ceil((across + 2 * pad) * a);
    const c = this.canvas(size, size), g = c.getContext("2d");
    const count = this.draw(g, [1, 0, 0, 1, 0, 0], trees, null, (n, w) => [(nw.w + pad - w) * a, (nw.n + pad - n) * a], [a, a], null, gone);
    return keptMap(this.sheets, id, { canvas: c, pad, count, mark: this.marks.sheets }, SHEETS_KEPT);
  }

  paint(ctx, { instance, corners, tileYards, at, k }, out = true, gone = false) {
    if (!this.index || (gone && !this.off.size)) return 0;
    const view = worldBox(corners), keys = treeTiles(worldBox(corners, this.margin), tileYards, (key) => this.has(instance, key));
    const m = ctx.getTransform(), base = [m.a, m.b, m.c, m.d, m.e, m.f];
    const step = blockStep(keys), far = step > 1 || Math.hypot(m.a, m.b) * k[0] < TREES.far;
    let count = 0, made = 0, asked = 0, owed = false;
    if (!far) {
      for (const key of keys) count += this.draw(ctx, base, this.list(instance, key) || [], view, at, k, out, gone) || 0;
      return count;
    }
    for (const block of new Set(keys.map((key) => blockOf(key, step)))) {
      const id = `${instance}/${step}/${block}/${out ? "out" : "under"}${gone ? "/gone" : ""}`, nw = blockCorner(block, step, tileYards), across = step * tileYards;
      let sheet = this.sheets.has(id) ? keptMap(this.sheets, id, this.sheets.get(id), SHEETS_KEPT) : null;
      if (!sheet || sheet.mark !== this.marks.sheets) {
        const members = blockTiles(block, step).filter((key) => this.has(instance, key));
        const room = made < TREES.perFrame && asked + members.length <= TREES.most;
        if (!room) owed = true;
        if (room || (step === 1 && !sheet)) {
          asked += members.length;
          const lists = members.map((key) => this.listNow(instance, key));
          const trees = lists.every(Boolean) ? lists.flat().filter((t) => treeOut(t) === out && canopyOff(t, this.off) === gone) : null;
          if (room && trees && this.picturesIn(trees)) {
            if (trees.length) made++;
            sheet = this.sheet(id, nw, across, trees, gone);
          } else if (!sheet && step === 1) {
            const now = this.list(instance, members[0]);
            if (now) count += this.draw(ctx, base, now, view, at, k, out, gone);
          }
        }
        if (!sheet) continue;
      }
      if (!sheet.canvas) continue;
      const [x, y] = at(nw.n + sheet.pad, nw.w + sheet.pad), side = across + 2 * sheet.pad;
      ctx.drawImage(sheet.canvas, x, y, k[0] * side, k[1] * side);
      count += sheet.count;
    }
    if (owed) this.drawn();
    return count;
  }

  roads(instance, key) {
    const id = `roads ${instance}/${key}`;
    if (!this.pictures.has(id)) this.pictures.set(id, this.image(`/api/trees/roads/${instance}/${key}.png`));
    return this.pictures.get(id);
  }

  roofs(instance, key) {
    const digest = this.index?.shapes?.[instance]?.[key];
    if (!digest) return NO_ROOFS;
    const id = `roof ${instance}/${key} ${digest}`;
    if (!this.pictures.has(id)) this.pictures.set(id, this.image(this.address(`/api/trees/roof/${instance}/${key}.png`, digest)));
    return this.pictures.get(id);
  }

  hole(kind, instance, key, pic, tileYards) {
    const id = `${kind} ${instance}/${key}`;
    if (this.holes.has(id)) return keptMap(this.holes, id, this.holes.get(id), HOLES_KEPT);
    const side = SEE.side, c = this.canvas(side, side), g = c.getContext("2d");
    g.filter = `blur(${holeBlur(SEE.fade, side, tileYards)}px)`;
    g.globalCompositeOperation = "lighter";
    for (let i = 0; i < SEE.gain; i++) g.drawImage(pic.img, 0, 0, side, side);
    return keptMap(this.holes, id, c, HOLES_KEPT);
  }

  thin(ctx, frame) {
    ctx.save();
    ctx.globalCompositeOperation = "destination-out";
    this.seeThrough(ctx, frame, (kind) => SEE.amount[kind]);
    this.roundYou(ctx, frame, SEE.amount.you);
    ctx.restore();
  }

  heights(ctx, frame, thin = true) {
    const ground = (kind) => SEE.ground.includes(kind);
    ctx.save();
    ctx.save();
    ctx.setTransform(1, 0, 0, 1, 0, 0);
    ctx.clearRect(0, 0, ctx.canvas.width, ctx.canvas.height);
    ctx.restore();
    ctx.globalCompositeOperation = "source-over";
    let laid = thin ? this.seeThrough(ctx, frame, (kind) => (ground(kind) ? SEE.amount[kind] : null)) : 0;
    const you = thin ? this.roundYou(ctx, frame, SEE.amount.you) : null;
    const gone = this.layGone(ctx, frame);
    ctx.globalCompositeOperation = "destination-out";
    laid += this.seeThrough(ctx, frame, (kind) => (ground(kind) ? null : 1));
    ctx.restore();
    return JSON.stringify([laid, you && you.map(Math.round), gone, [...this.off].sort((a, b) => a - b)]);
  }

  layGone(ctx, frame) {
    if (!this.off.size) return 0;
    const { width, height } = ctx.canvas, m = ctx.getTransform();
    if (this.goneLayer?.width !== width || this.goneLayer?.height !== height) this.goneLayer = this.canvas(width, height);
    const g = this.goneLayer.getContext("2d");
    g.setTransform(1, 0, 0, 1, 0, 0);
    g.clearRect(0, 0, width, height);
    g.setTransform(m.a, m.b, m.c, m.d, m.e, m.f);
    const count = this.paint(g, frame, true, true) + this.paint(g, frame, false, true);
    if (!count) return 0;
    ctx.save();
    ctx.setTransform(1, 0, 0, 1, 0, 0);
    ctx.globalAlpha = 1;
    ctx.globalCompositeOperation = "lighter";
    ctx.filter = `blur(${SEE.fade * Math.hypot(m.a, m.b) * frame.k[0]}px)`;
    for (let i = 0; i < SEE.gain; i++) ctx.drawImage(this.goneLayer, 0, 0);
    ctx.restore();
    return count;
  }

  seeThrough(ctx, { instance, corners, tileYards, at, k, roofsOf }, each) {
    const keys = this.index ? treeTiles(worldBox(corners), tileYards, (key) => this.has(instance, key)) : [];
    if (!keys.length || blockStep(keys) !== 1) return 0;
    const kinds = SEE.kinds.filter((kind) => each(kind) != null);
    let made = 0, looked = 0, owed = false, laid = 0;
    for (const key of keys) {
      const under = { buildings: () => roofsOf(instance, key), roads: () => this.roads(instance, key) };
      for (const kind of kinds) {
        let hole = this.holes.has(`${kind} ${instance}/${key}`) ? this.hole(kind, instance, key, null, tileYards) : null;
        if (!hole) {
          if (looked >= SEE.looked) { owed = true; continue; }
          const pic = under[kind]();
          if (pic?.gone) continue;
          looked++;
          if (!pic?.ok) continue;
          if (made >= TREES.perFrame) { owed = true; continue; }
          made++;
          hole = this.hole(kind, instance, key, pic, tileYards);
        }
        const nw = tileCorner(key, tileYards), [x, y] = at(nw.n, nw.w);
        ctx.globalAlpha = each(kind);
        ctx.drawImage(hole, x, y, k[0] * tileYards, k[1] * tileYards);
        laid++;
      }
    }
    if (owed) this.drawn();
    return laid;
  }

  roundYou(ctx, { you, dpr = 1 }, a) {
    if (!you || a == null) return null;
    ctx.save();
    ctx.setTransform(1, 0, 0, 1, 0, 0);
    ctx.globalAlpha = a;
    const [x, y] = you, inner = SEE.you.inner * dpr, outer = SEE.you.outer * dpr;
    const fade = ctx.createRadialGradient(x, y, inner, x, y, outer);
    fade.addColorStop(0, this.ink(1));
    fade.addColorStop(1, this.ink(0));
    ctx.fillStyle = fade;
    ctx.fillRect(x - outer, y - outer, 2 * outer, 2 * outer);
    ctx.restore();
    return you;
  }
}

if (typeof module === "object") {
  module.exports = { TREES, SEE, SHEETS_KEPT, LISTS_KEPT, treeOut, canopyOff,treeTiles, worldBox, treeReach, treeMatrix, timesMatrix, keptMap, tileCorner, holeBlur,
    blockStep, blockOf, blockTiles, Trees };
}
