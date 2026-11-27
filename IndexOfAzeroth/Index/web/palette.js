// The Index of Azeroth. Copyright 2026 Index Case <indexofazeroth@pm.me>. PolyForm Strict 1.0.0, see LICENSE.md.
"use strict";

let tintRoot = null;
const tintRead = new Map();
let tintPictures = null;

function tintRgb(name) {
  if (!tintRead.has(name)) {
    tintRoot ||= getComputedStyle(document.documentElement);
    const hex = /^#([0-9a-f]{6})$/i.exec(tintRoot.getPropertyValue(`--${name}`).trim());
    if (!hex) console.error(`The Index of Azeroth: --${name} isn't a colour on style.css's :root`);
    tintRead.set(name, hex ? [0, 2, 4].map((i) => parseInt(hex[1].slice(i, i + 2), 16)) : [0, 0, 0]);
  }
  return [...tintRead.get(name)];
}

function tint(name, alpha = 1) {
  const [r, g, b] = tintRgb(name);
  if (alpha === 1) return `#${[r, g, b].map((c) => c.toString(16).padStart(2, "0")).join("")}`;
  return `rgba(${r}, ${g}, ${b}, ${alpha})`;
}

function tintArt(name) {
  tintPictures ||= new Set(String(document.documentElement.getAttribute("data-art") ?? "").split(" ").filter(Boolean));
  return tintPictures.has(name);
}

const GUIDE_LOOKS = { gold: "gold", corpse: "bone-white", npc: "kill-crimson" };
const LOOP_LOOKS = { grind: "kill-crimson", xp: "kill-crimson", farm: "kill-crimson", gather: "gather-purple", skin: "skin-teal",
                     mining: "mining-blue", herbalism: "herbalism-leaf", fishing: "fishing-salmon", treasure: "treasure-gold" };
const EPIC_LOOK = "forever-blue";

if (typeof module === "object") {
  module.exports = { tintRgb, tint, tintArt, GUIDE_LOOKS, LOOP_LOOKS, EPIC_LOOK };
}
