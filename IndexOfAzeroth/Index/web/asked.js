// The Index of Azeroth. Copyright 2026 Index Case <indexofazeroth@pm.me>. PolyForm Strict 1.0.0, see LICENSE.md.
"use strict";

const ASK_LINES = [
  "A dwarf of the Explorers' League went down to the archives for this. The archives are deep",
  "A goblin courier is bringing the ledgers. He is paid by the mile, so he took the long way round",
  "The librarian of Stormwind climbed the ladder for the top shelf and is still climbing",
  "A Forsaken scribe is copying out the pages. He stops now and then to put a finger back on",
  "Three magi of the Kirin Tor are looking for the right tome. They disagree about which tome",
  "A gryphon rider from Aerie Peak is bringing the dispatch. The gryphon has its own views on the route",
  "A kobold was sent down to the record room. He has found a candle and seems happy with that",
  "An orc of Orgrimmar is reading out the list to you. He is on the second letter",
  "The quartermaster of Ironforge is dusting off his books. Most of the dust is a family heirloom",
  "A night elf archivist is fetching the scrolls. She does not believe in hurrying"];
const ASK_LINE_MS = 4000;

function askWhy(e) {
  if (e?.status === 0) return "the Index didn't answer";
  return e?.status ? `the Index answered with error ${e.status}` : "the Index's answer couldn't be read";
}

const askAgains = new Map();

function askNote(keys, { have = false, none = "", what, again, why = null }) {
  if (have) return html`${none}`;
  const list = [].concat(keys), id = list.join("\n");
  const failed = list.map((k) => askState(k)).find((s) => s && !s.out);
  const waits = typeof failed?.error?.waiting === "string" ? failed.error.waiting : "";
  if (waits && !why) {
    return html`<span class="ask-wait" role="status"><span>${waits[0].toUpperCase() + waits.slice(1)}</span><i></i><i></i><i></i></span>`;
  }
  if (!failed && !why) {
    const from = [...id].reduce((n, c) => n + c.charCodeAt(0), 0);
    const line = ASK_LINES[(from + Math.floor(Date.now() / ASK_LINE_MS)) % ASK_LINES.length];
    return html`<span class="ask-wait" role="status"><span>${line}</span><i></i><i></i><i></i></span>`;
  }
  askAgains.set(id, { keys: list, again });
  return html`<span class="ask-failed">The page couldn't get ${what} because ${why || askWhy(failed.error)}. <button class="src-link" data-ask-again="${id}">Ask again</button></span>`;
}

function askAgain(e) {
  const note = askAgains.get(e.target.closest?.("button[data-ask-again]")?.dataset.askAgain);
  if (!note) return;
  note.keys.forEach(askNow);
  note.again();
}
if (typeof addEventListener === "function") addEventListener("click", askAgain, true);

if (typeof module === "object") {
  module.exports = { ASK_LINES, ASK_LINE_MS, askWhy, askNote, askAgain };
}
