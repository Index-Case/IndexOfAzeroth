// The Index of Azeroth. Copyright 2026 Index Case <indexofazeroth@pm.me>. PolyForm Strict 1.0.0, see LICENSE.md.
"use strict";

const REALIGN_ICON = `<svg viewBox="0 0 16 16" aria-hidden="true"><path d="M3 7.6A5 5 0 1 0 6.7 3.2" fill="none" stroke="currentColor" stroke-width="2.6" stroke-linecap="round"/><path d="M6.3 0.5L7.7 5.7L3.8 4Z" fill="currentColor"/></svg>`;
const REALIGN_TURNING = `<span class="realign-glow">${REALIGN_ICON}</span><span>${REALIGN_ICON}</span>`;
const REALIGN_WORDS = Object.values(wordsOf("page.realign.wait"));
const REALIGN_HOLD_MS = 2000, REALIGN_WORD_MS = 4000;
let realignAt = 0, realignTimer = 0, realignSaid = "";

function realignLines(r) {
  const build = r.build ? word("page.realign.build", { build: r.build }) : word("page.realign.build.new"), lines = [];
  if (r.rebuilding) {
    lines.push(r.step ? word("page.realign.rebuilding.step", { build, step: r.step }) : word("page.realign.rebuilding", { build }));
  }
  if (r.readIn) lines.push(r.readIn);
  const kinds = Object.entries(r.what || {}).map(([kind, places]) => (places.length
    ? word("page.realign.kind.places", { kind, places: andList(places) }) : word("page.realign.kind", { kind })));
  if (kinds.length) lines.push(word("page.realign.checking", { build, kinds: andList(kinds) }));
  return lines;
}

function realignHtml(now = Date.now()) {
  const r = app.realign;
  if (!r) return "";
  const flavour = REALIGN_WORDS[Math.floor(now / REALIGN_WORD_MS) % REALIGN_WORDS.length];
  const current = r.readIn && !Object.keys(r.what || {}).length;
  return `<h2 class="realign-head"><span class="realign-spin">${REALIGN_TURNING}</span>${esc(word("page.realign.title"))}</h2>
    <div class="replan-working"><span>${esc(flavour)}</span><i></i><i></i><i></i></div>
    <ul class="realign-what">${realignLines(r).map((line) => `<li>${esc(line)}</li>`).join("")}</ul>${current ? ""
    : `\n    <p class="muted">${esc(word("page.realign.not-current"))}</p>`}`;
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
  const said = app.realign ? [word("page.realign.title"), ...realignLines(app.realign)].join("\n") : "";
  if (said === realignSaid) return;
  realignSaid = said;
  if (!key.innerHTML) key.innerHTML = REALIGN_TURNING;
  key.title = said;
}

if (typeof module === "object") {
  module.exports = { REALIGN_ICON, REALIGN_TURNING, REALIGN_WORDS, REALIGN_HOLD_MS, REALIGN_WORD_MS, realignLines, realignHtml, noteRealign, paintRealign };
}
