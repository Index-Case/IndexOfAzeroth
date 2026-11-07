// The Index of Azeroth. Copyright 2026 Index Case <indexofazeroth@pm.me>. PolyForm Strict 1.0.0, see LICENSE.md.
"use strict";

const BLOOD_DIR = "art/blood/";
const BLOOD_BANDS = [
  { name: "100-60", from: 60, yards: 1 },
  { name: "60-30", from: 30, yards: 723 / 359 },
  { name: "30-0", from: -Infinity, yards: 1023 / 359 },
];
const BLOOD_POOL = { name: "pool", yards: 3.4 };
const BLOOD_OUTLINE = { src: "art/corpse_outline.png", yards: 7.6 };
const BLOOD_EACH = 5;
const BLOOD = { EACH: 1, UNIT: 0.30, MAP_SCALE: 1.3, MAP_ALPHA: 0.8, DARKEN: 0.42, MOST: 160, TRAIL_MOST: 600,
                FIGHT_KEEP_MS: 60000, SAVE_MS: 5000, DEAD_KEEP_MS: 30 * 60000, MAP_LEAST: 1 };

const bandOf = (health) => BLOOD_BANDS.findIndex((b) => health >= b.from);

function bloodPicture(health, random = Math.random) {
  const k = Math.min(BLOOD_EACH, 1 + Math.floor(random() * BLOOD_EACH));
  return `${BLOOD_BANDS[bandOf(health)].name}_${k}`;
}

function edgeSpot(aspect, random = Math.random) {
  const w = aspect, h = 1;
  let along = random() * 2 * (w + h), x, y;
  if (along < w) [x, y] = [along, 0];
  else if ((along -= w) < h) [x, y] = [w, along];
  else if ((along -= h) < w) [x, y] = [w - along, h];
  else [x, y] = [0, h - (along - w)];
  return { x: x / w, y: y / h };
}

const round = (v, places) => Math.round(v * 10 ** places) / 10 ** places;

class Blood {
  constructor({ layer, doc, picture, kept = () => null, keep = () => {}, drawn = () => {}, aspect = () => 16 / 9,
                random = Math.random, now = () => Date.now() }) {
    Object.assign(this, { layer, doc, kept, keep, drawn, aspect, random, now });
    Object.assign(this, { phase: undefined, health: null, owed: 0, mended: 0, fought: false, lastAlive: null, screen: [], trail: [],
                          savedAt: 0 });
    this.look = { screen: true, map: true, pool: true, screenShare: 1, mapShare: 1 };
    this.pics = new Map();
    const names = [...BLOOD_BANDS.flatMap((b) => Array.from({ length: BLOOD_EACH }, (_, k) => [`${b.name}_${k + 1}`, b.yards])),
                   [BLOOD_POOL.name, BLOOD_POOL.yards]];
    for (const [name, yards] of names) {
      const img = picture(`${BLOOD_DIR}${name}.png`);
      img.onload = () => this.drawn();
      this.pics.set(name, { img, yards });
    }
    this.outline = picture(BLOOD_OUTLINE.src);
    this.outline.onload = () => this.drawn();
  }

  get bleeding() {
    return this.phase === "fight" && this.fought && this.look.map;
  }

  report(state, { character = null, where = null } = {}) {
    const f = state?.flags || {}, now = this.now(), health = state?.health ?? state?.healthGuess ?? null;
    const phase = f.dead || f.ghost ? "dead" : f.combat ? "fight" : "calm";
    let changed = false;
    if (this.phase === undefined) changed = this.restore(character, phase, now);
    const was = this.phase;
    if (was === "dead" && phase !== "dead") changed = this.clear() || changed;
    else if (phase === "calm") changed = this.over() || changed;
    const fighting = phase === "fight" || (phase === "dead" && was === "fight");
    if (fighting && was != null && health != null && this.health != null && health < this.health) {
      this.bleed(this.health - health, health, where);
      changed = true;
    } else if (phase !== "dead" && health != null && this.health != null && health > this.health) {
      changed = this.heal(health - this.health, health) || changed;
    }
    if (phase === "calm" && health != null && health >= 100 && this.screen.length) {
      this.clearScreen();
      changed = true;
    }
    if (phase === "dead" && was !== "dead") changed = this.died(f.dead ? where : null) || changed;
    if (phase !== "dead" && where) this.lastAlive = where;
    if (health != null) this.health = health;
    changed ||= phase !== was;
    this.phase = phase;
    if (changed || ((phase !== "calm" || this.screen.length) && now - this.savedAt >= BLOOD.SAVE_MS)) this.save(character, now);
  }

  restore(character, phase, now) {
    const k = this.kept();
    const ok = !!k && k.character === character && Array.isArray(k.trail) && Array.isArray(k.screen)
      && (k.phase === "dead" ? phase === "dead" && now - k.at < BLOOD.DEAD_KEEP_MS
        : (k.phase === "fight" || (k.phase === "calm" && phase !== "dead")) && now - k.at < BLOOD.FIGHT_KEEP_MS);
    this.phase = ok ? k.phase : null;
    if (!ok) return false;
    this.health = k.health ?? null;
    this.trail = k.phase === "calm" ? [] : k.trail;
    this.fought = k.phase === "fight" && k.screen.length + k.trail.length > 0;
    for (const s of k.screen) this.show(s);
    return true;
  }

  save(character, now) {
    this.savedAt = now;
    this.keep(this.phase === "calm" && !this.screen.length ? null
      : { character, phase: this.phase, health: this.health, at: now, screen: this.screen, trail: this.trail });
  }

  bleed(lost, health, where) {
    this.fought = true;
    this.mended = 0;
    for (this.owed += lost; this.owed > 0; this.owed -= BLOOD.EACH) {
      const pic = bloodPicture(health, this.random), rot = round(this.random() * 2 * Math.PI, 3);
      const { x, y } = edgeSpot(this.aspect(), this.random);
      this.show({ pic, rot, x: round(x, 4), y: round(y, 4) });
      if (where) this.drop({ pic, rot, ...where });
    }
  }

  heal(gained, health) {
    this.mended += gained;
    let n = health >= 100 ? this.screen.length : Math.round(this.mended), gone = false;
    this.mended -= n;
    for (; n > 0 && this.screen.length; n--) {
      const s = this.screen.pop();
      this.layer.lastElementChild.remove();
      const k = this.trail.findLastIndex((t) => t.pic === s.pic && t.rot === s.rot);
      if (k >= 0) this.trail.splice(k, 1);
      gone = true;
    }
    if (!this.screen.length) this.clearScreen();
    return gone;
  }

  drop({ pic, rot, inst, n, w, floor = null }) {
    this.trail.push({ pic, rot, inst, n: round(n, 2), w: round(w, 2), floor });
    if (this.trail.length > BLOOD.TRAIL_MOST) this.trail.shift();
  }

  died(at) {
    const had = this.screen.length > 0;
    this.clearScreen();
    this.fought = false;
    const spot = at || this.lastAlive;
    if (spot) this.drop({ pic: BLOOD_POOL.name, rot: round(this.random() * 2 * Math.PI, 3), ...spot });
    return had || !!spot;
  }

  show(s) {
    const yards = this.pics.get(s.pic)?.yards;
    if (!yards) return;
    const el = this.doc.createElement("img");
    el.className = "blood-spot";
    el.alt = "";
    el.draggable = false;
    el.src = `${BLOOD_DIR}${s.pic}.png`;
    Object.assign(el.style, { left: `${(s.x * 100).toFixed(2)}%`, top: `${(s.y * 100).toFixed(2)}%`,
      width: `${(BLOOD.UNIT * yards * 100).toFixed(2)}vmin`, transform: `translate(-50%, -50%) rotate(${s.rot}rad)` });
    this.layer.appendChild(el);
    this.screen.push(s);
    if (this.screen.length > BLOOD.MOST) {
      this.screen.shift();
      this.layer.firstElementChild.remove();
    }
    this.layScreen();
  }

  clearScreen() {
    this.screen = [];
    this.mended = 0;
    this.layer.replaceChildren();
    this.layScreen();
  }

  layScreen() {
    this.layer.hidden = !this.look.screen || !this.screen.length;
    this.layer.style.opacity = this.look.screenShare < 1 ? String(this.look.screenShare) : "";
  }

  shown(look) {
    Object.assign(this.look, look);
    this.layScreen();
  }

  over() {
    const had = this.trail.length > 0;
    this.trail = [];
    this.owed = 0;
    this.fought = false;
    return had;
  }

  clear() {
    this.clearScreen();
    return this.over();
  }

  paint(g, { project, turn = 0, map = null, dpr = 1, width = Infinity, height = Infinity }) {
    const { map: trailOn, pool: poolOn, mapShare } = this.look;
    const trail = this.trail.filter((s) => (s.pic === BLOOD_POOL.name ? poolOn : trailOn));
    if (!trail.length) return 0;
    const perYard = new Map();
    const stain = this.stainFor(g), to = stain ? stain.getContext("2d") : g;
    let drawn = 0;
    const bodies = [];
    to.save();
    if (stain) {
      to.setTransform(1, 0, 0, 1, 0, 0);
      to.clearRect(0, 0, stain.width, stain.height);
    } else {
      to.globalAlpha = BLOOD.MAP_ALPHA * mapShare;
    }
    for (const s of trail) {
      const pic = this.pics.get(s.pic), img = pic?.img;
      if (!img?.complete || !img.naturalWidth || (s.floor != null && s.floor !== map)) continue;
      const at = project(s.inst, s.n, s.w);
      if (!at) continue;
      if (!perYard.has(s.inst)) {
        const by = project(s.inst, s.n, s.w - 100);
        perYard.set(s.inst, by ? Math.hypot(by[0] - at[0], by[1] - at[1]) / 100 : 0);
      }
      const wide = pic.yards * BLOOD.MAP_SCALE * perYard.get(s.inst), high = (wide * img.naturalHeight) / img.naturalWidth, reach = Math.hypot(wide, high) / 2;
      if (wide * dpr < BLOOD.MAP_LEAST || at[0] + reach < 0 || at[0] - reach > width || at[1] + reach < 0 || at[1] - reach > height) continue;
      const c = Math.cos(s.rot + turn) * dpr, n = Math.sin(s.rot + turn) * dpr;
      to.setTransform(c, n, -n, c, at[0] * dpr, at[1] * dpr);
      if (stain) {
        to.globalCompositeOperation = "destination-over";
        to.globalAlpha = 1;
        to.drawImage(img, -wide / 2, -high / 2, wide, high);
        to.globalCompositeOperation = "multiply";
        to.globalAlpha = BLOOD.DARKEN;
      }
      to.drawImage(img, -wide / 2, -high / 2, wide, high);
      if (s.pic === BLOOD_POOL.name) bodies.push({ c, n, at, perYard: perYard.get(s.inst) });
      drawn++;
    }
    to.restore();
    if (stain && drawn) {
      g.save();
      g.setTransform(1, 0, 0, 1, 0, 0);
      g.globalAlpha = BLOOD.MAP_ALPHA * mapShare;
      g.drawImage(stain, 0, 0);
      g.restore();
    }
    const body = this.outline;
    if (bodies.length && body?.complete && body.naturalHeight) {
      g.save();
      g.globalAlpha = mapShare;
      for (const { c, n, at, perYard: py } of bodies) {
        const high = BLOOD_OUTLINE.yards * BLOOD.MAP_SCALE * py, wide = (high * body.naturalWidth) / body.naturalHeight;
        g.setTransform(c, n, -n, c, at[0] * dpr, at[1] * dpr);
        g.drawImage(body, -wide / 2, -high / 2, wide, high);
      }
      g.restore();
    }
    return drawn;
  }

  stainFor(g) {
    const c = g.canvas;
    if (!c || typeof this.doc?.createElement !== "function") return null;
    const s = (this.stain ??= this.doc.createElement("canvas"));
    if (typeof s.getContext !== "function") return null;
    if (s.width !== c.width || s.height !== c.height) [s.width, s.height] = [c.width, c.height];
    return s;
  }
}

if (typeof module === "object") {
  module.exports = { BLOOD_DIR, BLOOD_BANDS, BLOOD_POOL, BLOOD_OUTLINE, BLOOD, bandOf, bloodPicture, edgeSpot, Blood };
}
