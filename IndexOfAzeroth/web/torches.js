// The Index of Azeroth. Copyright 2026 Index Case <indexofazeroth@pm.me>. PolyForm Strict 1.0.0, see LICENSE.md.
"use strict";

const TORCH_TILE = 1600 / 3, TORCH_CORNER = 32 * TORCH_TILE;

class Torches {
  constructor() {
    this.instances = {};
    this.colours = [];
    this.kinds = [];
    this.stamp = 0;
  }

  set(data) {
    this.instances = data?.instances && typeof data.instances === "object" ? data.instances : {};
    this.colours = Array.isArray(data?.colours) ? data.colours : [];
    this.kinds = Array.isArray(data?.kinds) ? data.kinds : [];
    this.stamp++;
  }

  within(instance, { n0, n1, w0, w1 }) {
    const tiles = this.instances[instance], out = [];
    if (!tiles) return out;
    const tile = (v) => Math.floor((TORCH_CORNER - v) / TORCH_TILE);
    for (let col = tile(w0); col <= tile(w1); col++) {
      for (let row = tile(n0); row <= tile(n1); row++) {
        for (const l of tiles[`${col}_${row}`] || []) if (l[0] <= n0 && l[0] >= n1 && l[1] <= w0 && l[1] >= w1) out.push(l);
      }
    }
    return out;
  }
}

if (typeof module === "object") {
  module.exports = { TORCH_TILE, TORCH_CORNER, Torches };
}
