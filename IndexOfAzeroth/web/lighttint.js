// The Index of Azeroth. Copyright 2026 Index Case <indexofazeroth@pm.me>. PolyForm Strict 1.0.0, see LICENSE.md.
"use strict";

const LIGHT_TINT = { from: 0.5, whole: 0.9, most: 2.5, sun: 0.97, ease: 200, close: 1, edge: 60 };

const TINT_DUSK = { from: 18.5, over: 0.5, dark: 0.69, band: 0.02 };

function tintKeyAt(keys, hour) {
  const h = ((hour % 24) + 24) % 24, i = keys.findIndex((k) => k[0] > h);
  const next = keys[i < 0 ? 0 : i], prev = keys[(i <= 0 ? keys.length : i) - 1];
  const span = (next[0] - prev[0] + 24) % 24 || 24, t = ((h - prev[0] + 24) % 24) / span;
  return prev.slice(1).map((v, k) => v + (next[k + 1] - v) * t);
}

function tintZone(spots, centre = null) {
  const counts = new Map();
  for (const s of spots) counts.set(s.zone, (counts.get(s.zone) || 0) + 1);
  let zone = null, most = 0;
  for (const [z, n] of counts) if (n > most) [zone, most] = [z, n];
  if (zone == null) return null;
  const far = (s) => (centre && s.inst === centre.inst ? Math.hypot(s.n - centre.n, s.w - centre.w) : Infinity);
  const spot = centre && centre.zone === zone ? centre : spots.filter((s) => s.zone === zone).reduce((a, s) => (far(s) < far(a) ? s : a));
  return { zone, share: most / spots.length, spot };
}

function tintShare(share) {
  const { from, whole } = LIGHT_TINT, t = Math.min(1, Math.max(0, ((share || 0) - from) / (whole - from)));
  return t * t * (3 - 2 * t);
}

const tintLevel = (share) => Math.min(LIGHT_TINT.most, Math.max(0, share)) / LIGHT_TINT.most * 255;
const tintByte = (share) => Math.round(tintLevel(share));

function tintNoon(inst, sun = LIGHT_TINT.sun) {
  const g = tintKeyAt(inst.lights[0].keys, 12);
  return [0, 1, 2].map((j) => Math.max(((g[3 + j] + sun * g[j]) * (1 - g[10]) + g[7 + j] * g[10]) * g[6], 1));
}

function tintInside(poly, n, w) {
  let hit = false;
  for (let i = 0, j = poly.length - 1; i < poly.length; j = i++) {
    const [x1, y1] = poly[j], [x2, y2] = poly[i];
    if (y1 !== y2 && (y1 > w) !== (y2 > w) && n < x1 + (w - y1) * (x2 - x1) / (y2 - y1)) hit = !hit;
  }
  return hit;
}

function tintDepth(poly, n, w) {
  let near = Infinity;
  for (let i = 0, j = poly.length - 1; i < poly.length; j = i++) {
    const [x1, y1] = poly[j], [x2, y2] = poly[i], dx = x2 - x1, dy = y2 - y1;
    const t = Math.min(1, Math.max(0, ((n - x1) * dx + (w - y1) * dy) / (dx * dx + dy * dy || 1)));
    near = Math.min(near, Math.hypot(n - x1 - t * dx, w - y1 - t * dy));
  }
  return tintInside(poly, n, w) ? near : -near;
}

function tintRamp(d, start, end) {
  const mid = (start + end) / 2, half = Math.max(end - start, LIGHT_TINT.edge) / 2;
  return Math.min(1, Math.max(0, (mid + half - d) / (2 * half)));
}

function tintWeights(inst, n, w, z) {
  const raw = inst.lights.map((l, i) => (!i ? 1 : l.at ? tintRamp(Math.hypot(n - l.at[0], w - l.at[1], z - l.at[2]), l.start, l.end) : 0));
  const out = raw.slice();
  for (let i = raw.length - 1; i > 0; i--) {
    if (!raw[i]) continue;
    for (let k = 0; k < i; k++) out[k] *= 1 - raw[i];
  }
  const zones = inst.zonelights || [];
  for (let i = zones.length - 1; i >= 0; i--) {
    const l = zones[i], height = tintRamp(-Math.min(z - l.zmin, l.zmax - z), 0, 0);
    const share = height > 0 ? Math.min(height, tintRamp(-tintDepth(l.poly, n, w), 0, 0)) : 0;
    if (!(share > 0)) continue;
    for (let k = 0; k < out.length; k++) out[k] *= 1 - share;
    out[l.index] += share;
  }
  return out;
}

function tintMix(inst, weights, hour) {
  const sum = new Array(11).fill(0);
  weights.forEach((wt, i) => {
    if (!(wt > 0)) return;
    const col = tintKeyAt(inst.lights[i].keys, hour);
    for (let j = 0; j < 11; j++) sum[j] += wt * col[j];
  });
  return sum;
}

function tintGrade(blend, grade, day = 1) {
  const t = Math.min(1, Math.max(0, day)), out = blend.slice();
  if (!grade || !(t > 0)) return out;
  const tone = (at, kept) => {
    const c = blend.slice(at, at + 3), grey = 0.2126 * c[0] + 0.7152 * c[1] + 0.0722 * c[2];
    for (let j = 0; j < 3; j++) out[at + j] = c[j] + ((c[j] + (grey - c[j]) * grade.grey) * grade.hue[j] * kept - c[j]) * t;
  };
  tone(0, grade.direct);
  tone(3, grade.ambient);
  tone(7, 1);
  out[10] = blend[10] + (Math.max(blend[10], grade.haze) - blend[10]) * t;
  return out;
}

function tintBlendAt(inst, hour, spot, day = 1) {
  const whole = spot.zone != null && inst.zones?.[spot.zone];
  const blend = whole ? tintMix(inst, tintWeights(inst, ...whole), hour)
    : Number.isFinite(spot.z) ? tintMix(inst, tintWeights(inst, spot.n, spot.w, spot.z), hour) : null;
  const grade = blend && spot.zone != null ? inst.graded?.[spot.zone] : null;
  return grade ? tintGrade(blend, grade, day) : blend;
}

function tintView(blend, noon) {
  const d = new Uint8Array(4), a = new Uint8Array(4), f = new Uint8Array(4);
  for (let j = 0; j < 3; j++) {
    const lut = blend[6] / noon[j];
    d[j] = tintByte(blend[j] * lut);
    a[j] = tintByte(blend[3 + j] * lut);
    f[j] = tintByte(blend[7 + j] * lut);
  }
  d[3] = a[3] = 255;
  f[3] = Math.round(Math.min(1, Math.max(0, blend[10])) * 255);
  return { d, a, f };
}

function tintDark(blend, noon, sun = LIGHT_TINT.sun) {
  const lit = [0, 1, 2].map((j) => ((blend[3 + j] + sun * blend[j]) * (1 - blend[10]) + blend[7 + j] * blend[10]) * blend[6] / noon[j]);
  return 0.2126 * lit[0] + 0.7152 * lit[1] + 0.0722 * lit[2];
}

function tintDusk(blend, noon, hour) {
  const { from, over, dark, band } = TINT_DUSK, h = ((hour % 24) + 24) % 24;
  const ease = (t) => { const v = Math.min(1, Math.max(0, t)); return v * v * (3 - 2 * v); };
  return ease((h - from) / over) * ease((dark + band / 2 - tintDark(blend, noon)) / band);
}

class LightTint {
  constructor() {
    this.instances = {};
    this.view = null;
    this.made = null;
    this.stamps = 0;
    this.easing = false;
  }

  set(data) {
    this.instances = { ...(data?.instances || {}) };
    this.view = null;
    this.made = null;
    this.easing = false;
  }

  at(instance, hour, sun = LIGHT_TINT.sun, spot = null, now = 0, strength = 1, day = 1) {
    const inst = this.instances[instance];
    if (!inst) {
      this.easing = false;
      return null;
    }
    const own = spot ? tintBlendAt(inst, hour, spot, day) : null;
    const goal = [...(own || tintKeyAt(inst.lights[0].keys, hour)), own ? Math.min(1, Math.max(0, strength)) : 0];
    const v = this.view;
    if (!v || v.instance !== instance) {
      this.view = { instance, now, blend: goal.slice() };
    } else {
      const k = 1 - Math.exp(-Math.max(0, now - v.now) / LIGHT_TINT.ease);
      v.blend = v.blend.map((x, j) => x + (goal[j] - x) * k);
      v.now = now;
    }
    const view = this.view, noon = tintNoon(inst, sun);
    const bytes = (b) => { const l = tintView(b, noon); return [...l.d, ...l.a, ...l.f, Math.round(b[11] * 255), Math.round(tintDusk(b, noon, hour) * 255)]; };
    const want = bytes(goal);
    this.easing = bytes(view.blend).some((b, j) => Math.abs(b - want[j]) > LIGHT_TINT.close);
    if (!this.easing) view.blend = goal;
    const shown = bytes(view.blend);
    if (this.made?.instance === instance && this.made.bytes.every((b, j) => b === shown[j])) return this.made;
    const d = Uint8Array.from(shown.slice(0, 4)), a = Uint8Array.from(shown.slice(4, 8)), f = Uint8Array.from(shown.slice(8, 12));
    const k = shown[12] / 255, dusk = shown[13] / 255, share = (l) => [0, 1, 2].map((j) => l[j] / 255 * LIGHT_TINT.most);
    this.made = { instance, stamp: ++this.stamps, bytes: shown, col: 0, row: 0, per: 1, w: 1, h: 1, most: LIGHT_TINT.most,
      d, a, f, k, dusk, area: { d: share(d), a: share(a), f: share(f), h: f[3] / 255, k } };
    return this.made;
  }
}

if (typeof module === "object") {
  module.exports = { LIGHT_TINT, tintKeyAt, tintZone, tintShare, tintLevel, tintByte, tintNoon, tintInside,
    tintDepth, tintRamp, tintWeights, tintMix, tintGrade, tintBlendAt, tintView, TINT_DUSK, tintDark, tintDusk, LightTint };
}
