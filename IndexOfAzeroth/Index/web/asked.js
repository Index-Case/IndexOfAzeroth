// The Index of Azeroth. Copyright 2026 Index Case <indexofazeroth@pm.me>. PolyForm Strict 1.0.0, see LICENSE.md.
"use strict";

const ASK_LINES = Object.values(wordsOf("page.ask.wait"));
const ASK_LINE_MS = 4000;

function askWhy(e) {
  if (e?.status === 0) return word("page.ask.why.away");
  return e?.status ? word("page.ask.why.error", { status: e.status }) : word("page.ask.why.unread");
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
  return html`<span class="ask-failed">${raw(word("page.ask.note.failed", { what: esc(what), why: esc(why || askWhy(failed.error)) }))} <button class="src-link" data-ask-again="${id}">${word("page.ask.note.again")}</button></span>`;
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
