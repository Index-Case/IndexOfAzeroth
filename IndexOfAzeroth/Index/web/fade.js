// The Index of Azeroth. Copyright 2026 Index Case <indexofazeroth@pm.me>. PolyForm Strict 1.0.0, see LICENSE.md.
"use strict";

const FADE_OVER = 250, FADE_SWITCH = 100;

class Fades {
  constructor(still = () => false) {
    this.all = new Map();
    this.still = still;
  }

  want(key, to, ms, { from = 0, now = false, data } = {}) {
    let f = this.all.get(key);
    if (!f) this.all.set(key, f = { key, at: from, to, ms, data });
    f.to = to;
    f.ms = ms;
    if (data !== undefined) f.data = data;
    if (f.at !== to && (now || this.still())) f.at = to;
    if (f.at === 0 && to === 0) this.all.delete(key);
    return f;
  }

  show(prefix, shown, ms) {
    for (const key of [...this.all.keys()]) if (key.startsWith(prefix) && !shown.has(key)) this.want(key, 0, ms);
    for (const [key, how] of shown) this.want(key, how.to ?? 1, ms, how);
  }

  step(dt) {
    const still = this.moving() && this.still();
    let moving = false;
    for (const [key, f] of this.all) {
      const by = still ? 1 : dt / f.ms;
      f.at = f.at < f.to ? Math.min(f.to, f.at + by) : Math.max(f.to, f.at - by);
      if (f.at === 0 && f.to === 0) this.all.delete(key);
      else moving ||= f.at !== f.to;
    }
    return moving;
  }

  get(key) {
    return this.all.get(key)?.at ?? 0;
  }

  moving() {
    for (const f of this.all.values()) if (f.at !== f.to) return true;
    return false;
  }

  list(prefix) {
    return [...this.all.values()].filter((f) => f.key.startsWith(prefix));
  }

  drop(key) {
    this.all.delete(key);
  }
}

if (typeof module === "object") module.exports = { FADE_OVER, FADE_SWITCH, Fades };
