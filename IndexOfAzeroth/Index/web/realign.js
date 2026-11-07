// The Index of Azeroth. Copyright 2026 Index Case <indexofazeroth@pm.me>. PolyForm Strict 1.0.0, see LICENSE.md.
"use strict";

const REALIGN_ICON = `<svg viewBox="0 0 16 16" aria-hidden="true"><path d="M3 7.6A5 5 0 1 0 6.7 3.2" fill="none" stroke="currentColor" stroke-width="2.6" stroke-linecap="round"/><path d="M6.3 0.5L7.7 5.7L3.8 4Z" fill="currentColor"/></svg>`;
const REALIGN_TURNING = `<span class="realign-glow">${REALIGN_ICON}</span><span>${REALIGN_ICON}</span>`;
const REALIGN_WORDS = [
  "The Kirin Tor are re-aligning the ley lines",
  "The cartographers of Stormwind are redrawing their charts",
  "A dwarf is holding the old maps up to the new ones and squinting",
  "The surveyors are pacing the roads again and grumbling about it",
  "The scribes are copying out the new pages by hand",
  "A gnome engineer is recalibrating the gears with a large wrench",
  "The Explorers' League is checking its notes against the new dig",
  "Two loremasters are comparing the old tomes with the new. They have agreed on nothing yet",
  "A Kirin Tor apprentice is tuning the arcane compass. A rat nearby is now purple",
  "The keepers of Uldaman are putting their vaults in order"];
const REALIGN_HOLD_MS = 2000, REALIGN_WORD_MS = 4000;
let realignAt = 0, realignTimer = 0, realignSaid = "";

function realignLines(r) {
  const build = r.build ? `build ${r.build}` : "the new build", lines = [];
  if (r.rebuilding) lines.push(`The Index is rebuilding its data for ${build}${r.step ? ` (${r.step})` : ""}`);
  if (r.readIn) lines.push(r.readIn);
  const kinds = Object.entries(r.what || {}).map(([kind, places]) => `the ${kind}${places.length ? ` (${andList(places)})` : ""}`);
  if (kinds.length) lines.push(`The Index is checking the data it kept from before ${build}: ${andList(kinds)}`);
  return lines;
}

function realignHtml(now = Date.now()) {
  const r = app.realign;
  if (!r) return "";
  const word = REALIGN_WORDS[Math.floor(now / REALIGN_WORD_MS) % REALIGN_WORDS.length];
  const current = r.readIn && !Object.keys(r.what || {}).length;
  return `<h2 class="realign-head"><span class="realign-spin">${REALIGN_TURNING}</span>Re-aligning</h2>
    <div class="replan-working"><span>${esc(word)}</span><i></i><i></i><i></i></div>
    <ul class="realign-what">${realignLines(r).map((line) => `<li>${esc(line)}</li>`).join("")}</ul>${current ? ""
    : `\n    <p class="muted">Until the re-aligning is done, what the page shows may not be up to date.</p>`}`;
}

function noteRealign(r, now = Date.now()) {
  clearTimeout(realignTimer);
  if (r) {
    app.realign = r;
    realignAt = now;
  } else if (app.realign && now - realignAt < REALIGN_HOLD_MS) {
    realignTimer = setTimeout(() => { noteRealign(null); renderDrawer(); }, REALIGN_HOLD_MS - (now - realignAt));
  } else {
    app.realign = null;
  }
  paintRealign();
}

function paintRealign() {
  const key = document.getElementById("key-realign");
  key.hidden = !app.realign;
  const said = app.realign ? ["Re-aligning", ...realignLines(app.realign)].join("\n") : "";
  if (said === realignSaid) return;
  realignSaid = said;
  if (!key.innerHTML) key.innerHTML = REALIGN_TURNING;
  key.title = said;
}

if (typeof module === "object") {
  module.exports = { REALIGN_ICON, REALIGN_TURNING, REALIGN_WORDS, REALIGN_HOLD_MS, REALIGN_WORD_MS, realignLines, realignHtml, noteRealign, paintRealign };
}
