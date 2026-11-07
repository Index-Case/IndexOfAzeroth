// The Index of Azeroth. Copyright 2026 Index Case <indexofazeroth@pm.me>. PolyForm Strict 1.0.0, see LICENSE.md.
"use strict";
const TRAVELLERS = { chance: 0.2, busy: 0.4, routes: [["Brill", "Undercity", "Sepulcher"], ["Ironforge", "Kharanos", "Thelsamar"],
  ["Stormwind City", "Goldshire", "Lakeshire"], ["Orgrimmar", "Razor Hill", "Crossroads"], ["Auberdine", "Astranaar"],
  ["Shadowglen", "Darnassus"]], town: 300, jump: 500, jumpCost: 4, per: 1000, hour: 3600, group: [1, 3], most: 5, speed: 1.53, near: 100, lift: 1.5, clear: 0.5, fade: 4,
  step: 10, lost: 7200, ypx: 0.635, fadeTo: 1.25, sample: 5 };

const travellersShown = (ypx) => {
  const k = Math.min(1, Math.max(0, Math.log(TRAVELLERS.ypx / ypx) / Math.log(TRAVELLERS.fadeTo)));
  return 1 - k * k * (3 - 2 * k);
};

function travelWays(n, rnd) {
  const ways = Array.from({ length: n }, () => (rnd() < 0.5 ? 1 : -1));
  if (n === 2) ways[1] = -ways[0];
  if (n >= 3 && ways.every((w) => w === ways[0])) ways[Math.floor(rnd() * n) % n] *= -1;
  return ways;
}

const travelSpots = (n, length) => Array.from({ length: n }, (_, i) => (length * (i + 0.5)) / n);

const nameKey = (name) => String(name).toUpperCase().replace(/^THE /, "").replace(/[^A-Z ]/g, "").trim();

const boxFar = ([, top, bottom, left, right], n, w) => Math.hypot(n > top ? n - top : n < bottom ? bottom - n : 0, w > left ? w - left : w < right ? right - w : 0);

function routeBetween(d, a, b) {
  const near = (box) => {
    const far = d.stretches.map((s) => Math.min(...s.n.map((n, i) => boxFar(box, n, s.w[i]))));
    const reach = box[1] === box[2] && box[3] === box[4] ? TRAVELLERS.town : 0;
    const close = far.map((f, k) => (f <= reach ? k : -1)).filter((k) => k >= 0);
    return close.length || !far.length ? close : [far.indexOf(Math.min(...far))];
  };
  const from = near(a), to = near(b);
  if (!from.length || !to.length) return null;
  const shared = from.find((k) => to.includes(k));
  if (shared !== undefined) return [shared];
  const dist = new Map(), via = new Map(), done = new Set(), first = new Map(), last = new Map();
  for (const k of from) for (const node of [d.stretches[k].a, d.stretches[k].b]) {
    dist.set(node, 0);
    first.set(node, k);
  }
  for (const k of to) for (const node of [d.stretches[k].a, d.stretches[k].b]) last.set(node, k);
  let end = null;
  while (end === null) {
    let node = null;
    for (const [k, v] of dist) if (!done.has(k) && (node === null || v < dist.get(node))) node = k;
    if (node === null) return null;
    if (last.has(node)) {
      end = node;
      break;
    }
    done.add(node);
    const reach = (next, len, k) => {
      if (!done.has(next) && !(dist.get(next) <= len)) {
        dist.set(next, len);
        via.set(next, [k, node]);
      }
    };
    for (const [k] of d.nodes[node] || []) {
      const s = d.stretches[k];
      reach(s.a === node ? s.b : s.a, dist.get(node) + s.length, k);
    }
    const [n0, w0] = d.at[node];
    d.at.forEach((p, next) => {
      const far = p ? Math.hypot(p[0] - n0, p[1] - w0) : Infinity;
      if (next !== node && far <= TRAVELLERS.jump) reach(next, dist.get(node) + far * TRAVELLERS.jumpCost, -1);
    });
  }
  const way = [last.get(end)];
  let node = end;
  while (via.has(node)) {
    const [k, back] = via.get(node);
    if (k >= 0) way.push(k);
    node = back;
  }
  return [...new Set([...way, first.get(node)])];
}

class RoadStretch {
  constructor(zone, a, b, flat) {
    this.zone = zone;
    this.a = a;
    this.b = b;
    this.n = [];
    this.w = [];
    this.h = [];
    for (let i = 0; i + 2 < flat.length; i += 3) {
      this.n.push(flat[i]);
      this.w.push(flat[i + 1]);
      this.h.push(flat[i + 2]);
    }
    this.at = [0];
    for (let i = 1; i < this.n.length; i++) this.at.push(this.at[i - 1] + Math.hypot(this.n[i] - this.n[i - 1], this.w[i] - this.w[i - 1]));
    this.length = this.at[this.at.length - 1] || 0;
    this.nearAt = null;
  }

  spot(d) {
    const at = this.at;
    if (!(this.length > 0)) return [this.n[0], this.w[0], this.h[0]];
    let lo = 0, hi = at.length - 1;
    const x = Math.min(this.length, Math.max(0, d));
    while (hi - lo > 1) {
      const mid = (lo + hi) >> 1;
      if (at[mid] <= x) lo = mid;
      else hi = mid;
    }
    const k = at[hi] > at[lo] ? (x - at[lo]) / (at[hi] - at[lo]) : 0;
    return [this.n[lo] + (this.n[hi] - this.n[lo]) * k, this.w[lo] + (this.w[hi] - this.w[lo]) * k, this.h[lo] + (this.h[hi] - this.h[lo]) * k];
  }
}

class Travellers {
  constructor(random = Math.random) {
    this.random = random;
    this.instances = {};
    this.places = [];
    this.lights = [];
    this.time = 0;
    this.night = false;
    this.rolls = null;
    this.named = [];
    this.routed = [];
  }

  set(data) {
    const got = data?.instances && typeof data.instances === "object" ? data.instances : {};
    this.instances = {};
    for (const [inst, d] of Object.entries(got)) {
      if (!Array.isArray(d?.stretches) || !Array.isArray(d?.nodes)) continue;
      const stretches = d.stretches.filter((s) => Array.isArray(s) && Array.isArray(s[3]) && s[3].length >= 6).map(([z, a, b, flat]) => new RoadStretch(z, a, b, flat));
      const nodes = d.nodes.map(() => []);
      stretches.forEach((s, k) => {
        nodes[s.a]?.push([k, 0]);
        nodes[s.b]?.push([k, 1]);
      });
      const at = nodes.map(() => null);
      stretches.forEach((s) => {
        at[s.a] = [s.n[0], s.w[0]];
        at[s.b] = [s.n[s.n.length - 1], s.w[s.w.length - 1]];
      });
      this.instances[inst] = { nodes, stretches, at };
    }
    this.markRoutes(this.named);
    this.restart();
  }

  setPlaces(places, names = []) {
    const boxed = (places || []).map((p, i) => [p.length === 3 ? [p[0], p[1], p[1], p[2], p[2]] : p, names[i]]);
    const kept = boxed.filter(([p]) => p.length === 5 && p.every(Number.isFinite));
    this.places = kept.map(([p]) => p);
    for (const d of Object.values(this.instances)) for (const s of d.stretches) s.nearAt = null;
    this.named = kept.filter(([, name]) => name).map(([p, name]) => [nameKey(name), p]);
    this.markRoutes(this.named);
  }

  markRoutes(named) {
    for (const d of Object.values(this.instances)) for (const s of d.stretches) s.busy = false;
    const at = new Map(named);
    this.routed = TRAVELLERS.routes.map((towns) => ({ towns, legs: towns.slice(1).map((to, i) => {
      const a = at.get(nameKey(towns[i])), b = at.get(nameKey(to));
      if (!a || !b || a[0] !== b[0] || !this.instances[a[0]]) return null;
      const way = routeBetween(this.instances[a[0]], a, b);
      way?.forEach((k) => { this.instances[a[0]].stretches[k].busy = true; });
      return way ? way.length : null;
    }) }));
  }

  restart() {
    this.lights = [];
    this.rolls = null;
    this.night = false;
  }

  placeFar(inst, n, w) {
    let best = Infinity;
    for (const [i, top, bottom, left, right] of this.places) {
      if (i !== +inst) continue;
      const dn = n > top ? n - top : n < bottom ? bottom - n : 0, dw = w > left ? w - left : w < right ? right - w : 0;
      best = Math.min(best, Math.hypot(dn, dw));
    }
    return best;
  }

  near(inst, s) {
    if (s.nearAt) return s.nearAt;
    const out = [], step = TRAVELLERS.sample, n = Math.max(1, Math.ceil(s.length / step));
    let from = null;
    for (let i = 0; i <= n; i++) {
      const d = (s.length * i) / n, [north, west] = s.spot(d), close = this.placeFar(inst, north, west) <= TRAVELLERS.near;
      if (close && from == null) from = d;
      if (!close && from != null) {
        out.push([from, d]);
        from = null;
      }
    }
    if (from != null) out.push([from, s.length]);
    return (s.nearAt = out);
  }

  inside(inst, s, d) {
    return this.near(inst, s).some(([a, b]) => d >= a && d <= b);
  }

  advance(seconds, night) {
    if (!night) {
      this.restart();
      return;
    }
    if (!this.night || seconds > TRAVELLERS.lost) {
      this.restart();
      this.night = true;
      this.startRolls();
      seconds = 0;
    }
    for (let left = Math.max(0, seconds); left > 0;) {
      const dt = Math.min(TRAVELLERS.step, left);
      left -= dt;
      this.time += dt;
      this.walk(dt);
      this.roll();
    }
  }

  startRolls() {
    this.rolls = {};
    for (const [inst, d] of Object.entries(this.instances)) {
      this.rolls[inst] = d.stretches.map(() => this.time + this.random() * TRAVELLERS.hour);
      d.stretches.forEach((s, k) => this.rollOn(inst, k));
    }
  }

  roll() {
    for (const [inst, due] of Object.entries(this.rolls || {})) {
      for (let k = 0; k < due.length; k++) {
        while (due[k] <= this.time) {
          due[k] += TRAVELLERS.hour;
          this.rollOn(inst, k);
        }
      }
    }
  }

  rollOn(inst, k) {
    const s = this.instances[inst]?.stretches[k];
    if (!s || this.random() >= Math.min(1, ((s.busy ? TRAVELLERS.busy : TRAVELLERS.chance) * s.length) / TRAVELLERS.per)) return;
    const [least, most] = TRAVELLERS.group, n = least + Math.min(most - least, Math.floor(this.random() * (most - least + 1)));
    this.setOut(inst, k, n);
  }

  setOut(inst, k, n) {
    const s = this.instances[inst]?.stretches[k];
    if (!s) return;
    const ways = travelWays(n, this.random);
    travelSpots(n, s.length).forEach((d, i) => {
      this.makeRoom(inst, k);
      this.lights.push({ inst, s: k, d, way: ways[i], born: this.time, share: 0, leaving: false, inside: this.inside(inst, s, d) });
    });
  }

  makeRoom(inst, k) {
    const on = this.lights.filter((l) => l.inst === inst && l.s === k && !l.leaving).sort((a, b) => a.born - b.born);
    for (let i = 0; i <= on.length - TRAVELLERS.most; i++) on[i].leaving = true;
  }

  walk(dt) {
    const fade = dt / TRAVELLERS.fade;
    for (const l of this.lights) {
      l.share = Math.min(1, Math.max(0, l.share + (l.leaving ? -fade : fade)));
      if (l.leaving) continue;
      const d = this.instances[l.inst];
      let s = d.stretches[l.s], go = TRAVELLERS.speed * dt;
      for (let turns = 0; go > 0 && turns < 8; turns++) {
        const to = l.way > 0 ? s.length - l.d : l.d;
        if (go <= to) {
          l.d += l.way * go;
          go = 0;
          break;
        }
        go -= to;
        const node = l.way > 0 ? s.b : s.a, on = (d.nodes[node] || []).filter(([k]) => k !== l.s);
        if (!on.length) {
          l.d = l.way > 0 ? s.length : 0;
          l.leaving = true;
          break;
        }
        const [k, end] = on[Math.floor(this.random() * on.length) % on.length];
        this.makeRoom(l.inst, k);
        l.s = k;
        s = d.stretches[k];
        l.way = end === 0 ? 1 : -1;
        l.d = end === 0 ? 0 : s.length;
      }
      const inside = this.inside(l.inst, s, l.d);
      if (inside && !l.inside) l.leaving = true;
      l.inside = inside;
    }
    this.lights = this.lights.filter((l) => !(l.leaving && l.share <= 0));
  }

  within(instance, { n0, n1, w0, w1 }) {
    const d = this.instances[instance], out = [];
    if (!d) return out;
    for (const l of this.lights) {
      if (l.inst !== String(instance) || !(l.share > 0)) continue;
      const [n, w, h] = d.stretches[l.s].spot(l.d);
      if (n <= n0 && n >= n1 && w <= w0 && w >= w1) out.push([n, w, h + TRAVELLERS.lift, 0, TRAVELLERS.clear, 0, -1, 0, l.share]);
    }
    return out;
  }
}

if (typeof module === "object") {
  module.exports = { TRAVELLERS, travellersShown, travelWays, travelSpots, nameKey, boxFar, routeBetween, RoadStretch, Travellers };
}
