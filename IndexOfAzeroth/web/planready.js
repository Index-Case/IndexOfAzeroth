// The Index of Azeroth. Copyright 2026 Index Case <indexofazeroth@pm.me>. PolyForm Strict 1.0.0, see LICENSE.md.
"use strict";

const PLAN_READY_MS = 4000;

let readyBox = null;

const EPIC_KINDS = [["zone:", "Zone epic"], ["camp:", "Camping"], ["class:", "Class quest epic"], ["", "Quest epic"]];
const EPIC_READY = EPIC_KINDS.map(([, kind]) => kind);
function planReadyWords(kind, copied, reload = true) {
  if (EPIC_READY.includes(kind)) return [`${kind} planning complete.`, null, "Press Reload on the add-on button to load the plan."];
  const paste = copied === true ? "The plan is in your clipboard, so paste it into your chat in game."
    : copied === false ? "The browser wouldn't let the page copy the plan, so the plan isn't in your clipboard. Press Copy, then paste the plan into your chat in game."
      : "Press Copy, then paste the plan into your chat in game.";
  return [`${kind} planning complete.`, paste, ...(reload ? ["Or press Reload on the add-on button to load the plan."] : [])];
}

function trackReadyKind(t) {
  if (t.kind === "epic") {
    const key = String(t.key);
    return EPIC_KINDS.find(([start]) => key.startsWith(start))[1];
  }
  const words = loopKind(t);
  return words[0].toUpperCase() + words.slice(1);
}

function dropReadyBox() {
  if (!readyBox) return;
  clearTimeout(readyBox.timer);
  readyBox.el.remove();
  readyBox = null;
}

function showPlanReady(plan) {
  dropReadyBox();
  const el = document.createElement("div");
  el.className = "ready-box";
  el.setAttribute("role", "status");
  const [lead, paste, or] = planReadyWords(plan.kind, plan.copied, plan.reload !== false);
  el.innerHTML = `<div class="ready-box-top"><div class="ready-box-lead"></div><button class="key small square x-mark ready-box-x"
    title="Close" aria-label="Close">&times;</button></div>
    ${paste ? `<p class="ready-box-paste${plan.copied === true ? "" : " ready-box-refused"}"></p>` : ""}${or ? `<p class="ready-box-or"><img class="ready-box-where"
    src="img/reload-where.png" alt="The add-on button in game, with its little reload arrow clicked"><span></span></p>` : ""}
    <div class="gp-foot">${plan.copied === true || !paste ? "" : `<button class="key small ready-box-copy">Copy</button>`}<button
    class="key small ready-box-ok">OK</button></div>`;
  el.querySelector(".ready-box-lead").textContent = lead;
  if (paste) el.querySelector(".ready-box-paste").textContent = paste;
  if (or) el.querySelector(".ready-box-or span").textContent = or;
  el.addEventListener("click", (e) => {
    const copy = !!e.target.closest(".ready-box-copy");
    const text = readyBox?.text;
    dropReadyBox();
    if (copy) copyText(text, "Copied", false);
  });
  document.body.appendChild(el);
  readyBox = { el, kind: plan.kind, from: plan.from, reason: plan.reason || null, inGame: plan.inGame || null,
               had: !!plan.inGame?.(), seen: false, text: plan.text };
  readyBox.timer = setTimeout(flyReadyBox, PLAN_READY_MS);
  return readyBox;
}

function flyReadyBox() {
  const box = readyBox;
  if (!box) return;
  flyInto(box.el, box.from ? document.getElementById(box.from) : null);
  box.timer = setTimeout(dropReadyBox, FLY_INTO_MS);
}

function planReadyCheck(reasons) {
  const box = readyBox;
  if (!box) return;
  const waiting = !!box.reason && reasons.some((r) => r.kind === box.reason);
  if (waiting) box.seen = true;
  if ((box.seen && !waiting) || (box.inGame && !box.had && box.inGame())) dropReadyBox();
}

const planReadyShown = () => readyBox;

if (typeof module === "object") {
  module.exports = { PLAN_READY_MS, planReadyWords, trackReadyKind, showPlanReady, flyReadyBox, planReadyCheck,
                     dropReadyBox, planReadyShown };
}
