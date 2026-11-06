// The Index of Azeroth. Copyright 2026 Index Case <indexofazeroth@pm.me>. PolyForm Strict 1.0.0, see LICENSE.md.
"use strict";

const HELP_ICON = `<svg viewBox="-16 -16 32 32" aria-hidden="true">
  <g class="hq-points"><path class="hq-lit" d="M0-16L-5.2-9.5H0Z"/><path class="hq-shade" d="M0-16L5.2-9.5H0Z"/>
    <path class="hq-shade" d="M0 16L-5.2 9.5H0Z"/><path class="hq-dark" d="M0 16L5.2 9.5H0Z"/>
    <path class="hq-lit" d="M10.47-10.47L6.78-9.9L8.34-8.34Z"/><path class="hq-shade" d="M10.47-10.47L9.9-6.78L8.34-8.34Z"/>
    <path class="hq-lit" d="M-10.47-10.47L-6.78-9.9L-8.34-8.34Z"/><path class="hq-shade" d="M-10.47-10.47L-9.9-6.78L-8.34-8.34Z"/>
    <path class="hq-shade" d="M10.47 10.47L9.9 6.78L8.34 8.34Z"/><path class="hq-dark" d="M10.47 10.47L6.78 9.9L8.34 8.34Z"/>
    <path class="hq-lit" d="M-10.47 10.47L-9.9 6.78L-8.34 8.34Z"/><path class="hq-dark" d="M-10.47 10.47L-6.78 9.9L-8.34 8.34Z"/></g>
  <circle class="hq-ring" r="12.4"/><circle class="hq-runes" r="11"/><circle class="hq-plate" r="9.4"/>
  <text class="hq-mark" y="6.3" text-anchor="middle">?</text></svg>`;
const HQ_GLYPH = "M8.7 9.3C8.7 7 10.3 5.7 12.2 5.7C14.2 5.7 15.6 7 15.6 8.8C15.6 10.4 14.5 11.2 13.4 11.9C12.6 12.4 12.2 13 12.2 14.1V14.6";
const HELP_ICON_SMALL = `<svg viewBox="-16 -16 32 32" aria-hidden="true">
  <circle class="hq-ring" r="15.3"/><circle class="hq-plate" r="12.6"/>
  <g transform="translate(0 0.5) scale(1.3) translate(-12.2 -12.5)"><path class="hq-edge" d="${HQ_GLYPH}"/>
    <circle class="hq-dot-edge" cx="12.2" cy="17.9" r="2.1"/><path class="hq-glyph" d="${HQ_GLYPH}"/><circle class="hq-dot" cx="12.2" cy="17.9" r="1.45"/></g></svg>`;
const HELP_DEFS = `<svg width="0" height="0" style="position:absolute" aria-hidden="true"><defs>
  <linearGradient id="hq-ring" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="${tint("bronze-lit")}"/><stop offset="0.5" stop-color="${tint("medal-ring")}"/><stop offset="1" stop-color="${tint("medal-dark")}"/></linearGradient>
  <radialGradient id="hq-plate" cx="42%" cy="34%" r="75%"><stop offset="0" stop-color="${tint("medal-plate-lit")}"/><stop offset="0.55" stop-color="${tint("medal-plate")}"/><stop offset="1" stop-color="${tint("medal-plate-deep")}"/></radialGradient>
  <linearGradient id="hq-cream" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="${tint("white")}"/><stop offset="0.65" stop-color="${tint("medal-cream")}"/><stop offset="1" stop-color="${tint("medal-cream-shade")}"/></linearGradient>
</defs></svg>`;

const HELP_SYMBOLS = { up: "▲", down: "▼", about: "≈", play: "▶", back: "⏪", fast: "⏩", prev: "⏮", next: "⏭" };

function helpBody(lines) {
  let html = "", list = false;
  for (const [key, text] of lines) {
    const tag = !key.includes(".") ? "h4" : /\.li\d+$/.test(key) ? "li" : "p";
    if ((tag === "li") !== list) { html += list ? "</ul>" : "<ul>"; list = !list; }
    html += `<${tag}>${fillWords(text, HELP_SYMBOLS)}</${tag}>`;
  }
  return list ? `${html}</ul>` : html;
}

const HELP = (() => {
  const topics = {};
  for (const [key, text] of Object.entries(wordsOf("page.help"))) {
    const dot = key.indexOf(".");
    (topics[key.slice(0, dot)] ||= []).push([key.slice(dot + 1), text]);
  }
  return Object.fromEntries(Object.entries(topics).map(([key, lines]) => [key,
    [Object.fromEntries(lines).title, helpBody(lines.filter(([k]) => k !== "title"))]]));
})();

function helpButton(key, big) {
  if (!HELP[key]) return "";
  const title = HELP[key][0];
  return `<button class="help-q${big ? " big" : ""}" data-help="${key}" title="${esc(word("page.help-button.tip", { title }))}" aria-label="${esc(word("page.help-button.label", { title }))}">${big ? HELP_ICON : HELP_ICON_SMALL}</button>`;
}

(() => {
  const pop = document.createElement("div");
  pop.className = "help-pop";
  pop.hidden = true;
  pop.setAttribute("role", "dialog");
  document.body.append(pop);
  document.body.insertAdjacentHTML("afterbegin", HELP_DEFS);
  let from = null;
  const close = () => { pop.hidden = true; from = null; };
  function open(btn, key) {
    const [title, body] = HELP[key] || [word("page.help-button.none.title"), `<p>${word("page.help-button.none.body")}</p>`];
    pop.innerHTML = `<div class="help-head"><span>${esc(title)}</span><button class="help-close x-mark" aria-label="${esc(word("page.help-button.close"))}">&times;</button></div>${body}`;
    pop.hidden = false;
    from = btn;
    const r = btn.getBoundingClientRect(), w = pop.offsetWidth, h = pop.offsetHeight;
    let x = r.right - w, y = r.bottom + 8;
    if (x < 8) x = Math.min(r.left, window.innerWidth - w - 8);
    if (y + h > window.innerHeight - 8) y = Math.max(8, r.top - h - 8);
    pop.style.left = `${Math.max(8, x)}px`;
    pop.style.top = `${y}px`;
  }
  document.addEventListener("click", (e) => {
    const btn = e.target.closest(".help-q");
    if (btn) {
      e.stopPropagation();
      if (from === btn && !pop.hidden) return close();
      return open(btn, btn.dataset.help);
    }
    if (e.target.closest(".help-pop")) {
      e.stopPropagation();
      if (e.target.closest(".help-close")) close();
      return;
    }
    close();
  }, true);
  closable(LAYER.help, () => !pop.hidden, () => close());
  document.querySelectorAll(".help-q:empty").forEach((b) => { b.innerHTML = b.classList.contains("big") ? HELP_ICON : HELP_ICON_SMALL; });
})();
