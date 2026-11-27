// The Index of Azeroth. Copyright 2026 Index Case <indexofazeroth@pm.me>. PolyForm Strict 1.0.0, see LICENSE.md.
"use strict";

const recipes = {
  open: new Set(keptOr("cc.recipesOpen", [])),
  ups: {},
  finds: {},
  typing: null,
  timer: 0,
};
const RECIPES_WAIT_MS = 250;

function askRecipeUps(line) {
  const had = recipes.ups[line];
  if (had && (had.busy || (had.version === alts.version && Date.now() - had.at < PLAYER_FRESH))) return;
  const asked = getJson(`/api/profupgrades?line=${line}`, { key: `recipeups:${line}`, quiet: true });
  if (!asked) return;
  const mine = recipes.ups[line] = { at: Date.now(), version: alts.version, busy: true, answer: had?.answer || null };
  asked.then((j) => { Object.assign(mine, { busy: false, answer: j }); recipesRedraw(); },
    () => { Object.assign(mine, { busy: false, failed: true }); recipesRedraw(); });
}
function recipesRedraw() {
  if (app.drawer === "player") renderDrawer();
}

function recipesTyped(line, text) {
  const f = recipes.finds[line] ||= {};
  f.text = text;
  clearTimeout(recipes.timer);
  if (!text.trim()) {
    Object.assign(f, { busy: false, answer: null });
    recipesRedraw();
    return;
  }
  recipes.timer = setTimeout(() => {
    const asked = getJson(`/api/profupgrades?${new URLSearchParams({ line, q: text.trim() })}`, { key: `recipefind:${line}`, quiet: true });
    if (!asked) return;
    f.busy = true;
    asked.then((j) => { if (f.text === text) Object.assign(f, { busy: false, failed: false, answer: j }); recipesRedraw(); },
      () => { if (f.text === text) Object.assign(f, { busy: false, failed: true }); recipesRedraw(); });
  }, RECIPES_WAIT_MS);
}

function learnWords(r, skill) {
  const l = r.learn;
  if (l.how === "known") return word("page.recipes.learn.known");
  if (l.how === "trainer") return l.npc ? word("page.recipes.learn.trainer", { npc: l.npc }) : word("page.recipes.learn.trainer.far", { skill });
  return l.npc ? word("page.recipes.learn.vendor", { npc: l.npc, pattern: l.patternName })
    : word("page.recipes.learn.vendor.far", { pattern: l.patternName });
}

function recipeLine(r, skill) {
  const tag = r.tag ? html`<span class="j-tag ${UP_TAG[r.kind]}">${r.tag}</span> ` : "";
  const needs = r.short ? html` <span class="up-from">${word("both.craft.skill", { skill, need: r.skill, have: r.yours ?? 0 })}</span>` : "";
  const from = r.from ? html` <span class="up-from">${word("page.recipes.from", { level: r.from })}</span>` : "";
  return html`${tag}${learnWords(r, skill)}${needs}${from}`;
}

function recipeRow(r, i, list, p) {
  const src = r.iconStored ? `${r.icon}.jpg` : "inv_misc_questionmark.jpg";
  const at = `${p.line}:${list}:${i}`;
  const guide = r.learn.npc ? html`<button type="button" class="mob-go" data-rcp-learn="${at}" data-rcp-cat="${p.cat}"
    title="${word("page.recipes.guide.learn", { npc: r.learn.npc, name: r.name })}">${word("page.recipes.guide")}</button>` : "";
  const craft = r.short ? html`<button type="button" class="mob-go" data-rcp-craft="${at}" title="${word("page.recipes.level.hover", { name: r.name, skill: p.name, need: r.skill })}">${word("page.recipes.level", { need: r.skill })}</button>`
    : html`<button type="button" class="mob-go" data-rcp-craft="${at}" title="${word("page.items.craft", { name: r.name })}">${word("page.items.key.craft")}</button>`;
  return html`<div class="market-row"><span class="market-item" data-tip="${r.item}"><img class="market-ic q${r.q}" src="/icon/${src}" alt=""><span
    class="market-name q${r.q}">${r.name}<small>${recipeLine(r, p.name)}</small></span></span><span class="market-keys">${guide}${craft}</span></div>`;
}

function recipeKeys(p) {
  if (!p.gear || p.line == null) return "";
  const open = recipes.open.has(p.line);
  return html`<button type="button" class="camp-fold rcp-fold" data-rcp-fold="${p.line}" aria-expanded="${String(open)}"
    title="${open ? word("page.recipes.collapse", { skill: p.name }) : word("page.recipes.expand", { skill: p.name })}"></button><button type="button" class="mob-go"
    data-rcp-guide="${esc(p.cat)}" title="${word("page.recipes.guide.trainer", { skill: p.name })}">${word("page.recipes.guide")}</button>`;
}

function recipesHtml(p) {
  if (!p.gear || p.line == null || !recipes.open.has(p.line)) return "";
  askRecipeUps(p.line);
  const f = recipes.finds[p.line], u = recipes.ups[p.line];
  const box = html`<div class="rcp-find">${raw(searchBox(`rcp-find-${p.line}`, word("page.recipes.find", { skill: p.name }), f?.text || ""))}</div>`;
  let body;
  if (f?.text?.trim()) {
    const rows = f.answer?.finds || [];
    body = f.failed ? html`<div class="up-empty">${word("page.recipes.failed")}</div>`
      : rows.length ? rows.map((r, i) => recipeRow(r, i, "finds", p)) : f.busy ? "" : html`<div class="up-empty">${word("page.recipes.none", { skill: p.name })}</div>`;
  } else {
    const a = u?.answer;
    body = !a ? (u?.failed ? html`<div class="up-empty">${word("page.recipes.failed")}</div>` : "")
      : !a.known ? html`<div class="up-empty">${word("page.recipes.unknown")}</div>`
        : a.upgrades.length ? a.upgrades.map((r, i) => recipeRow(r, i, "upgrades", p))
          : html`<div class="up-empty">${word("page.recipes.empty")}<small>${word("page.recipes.quip")}</small></div>`;
  }
  if (recipes.typing === p.line) queueMicrotask(() => giveFocus(p.line));
  return html`<div class="rcp-list"><h4>${word("page.recipes.heading")} ${raw(helpButton("recipes"))}</h4>${box}${body}</div>`;
}

function giveFocus(line) {
  const box = $(`rcp-find-${line}`);
  if (!box || document.activeElement === box) return;
  box.focus();
  box.setSelectionRange(box.value.length, box.value.length);
}

function recipeOf(at) {
  const [line, list, i] = at.split(":");
  const rows = list === "finds" ? recipes.finds[line]?.answer?.finds : recipes.ups[line]?.answer?.upgrades;
  return rows?.[+i];
}

function recipesClicked(e) {
  const b = e.target.closest?.("button[data-rcp-fold], button[data-rcp-guide], button[data-rcp-learn], button[data-rcp-craft]");
  if (!b) return false;
  const d = b.dataset;
  if (d.rcpFold) {
    const line = +d.rcpFold;
    if (recipes.open.has(line)) recipes.open.delete(line); else recipes.open.add(line);
    keepIn("cc.recipesOpen", [...recipes.open]);
    renderDrawer();
  } else if (d.rcpGuide) guideToKind(d.rcpGuide);
  else {
    const r = recipeOf(d.rcpLearn || d.rcpCraft);
    if (!r) return true;
    if (d.rcpCraft) startCraftEpic(r.item, r.name);
    else if (r.learn.how === "trainer") guideNearest({ cats: [d.rcpCat], more: { npcs: r.learn.npcs.join(",") }, what: r.learn.npc });
    else guideNearest({ cats: ["vendor"], more: { goods: r.learn.pattern }, what: r.learn.npc });
  }
  return true;
}
$("drawer").addEventListener("click", recipesClicked);
$("drawer").addEventListener("input", (e) => {
  const id = e.target.id || "";
  if (!id.startsWith("rcp-find-")) return;
  const line = +id.slice("rcp-find-".length);
  recipes.typing = line;
  recipesTyped(line, e.target.value);
});
$("drawer").addEventListener("focusout", (e) => { if ((e.target.id || "").startsWith("rcp-find-") && e.target.isConnected) recipes.typing = null; });

if (typeof module === "object") {
  module.exports = { recipes, RECIPES_WAIT_MS, askRecipeUps, recipesRedraw, recipesTyped, learnWords, recipeLine, recipeRow, recipeKeys,
                     recipesHtml, giveFocus, recipeOf, recipesClicked };
}
