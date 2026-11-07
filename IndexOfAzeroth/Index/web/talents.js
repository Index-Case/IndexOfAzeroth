// The Index of Azeroth. Copyright 2026 Index Case <indexofazeroth@pm.me>. PolyForm Strict 1.0.0, see LICENSE.md.
"use strict";

const talents = { open: false, menu: false, timer: 0, picking: false };
const TW_CELL = 66, TW_ROW = 104;
const TW_ICON = 40;

hotkey(["n"], () => (talents.open ? closeTalents() : openTalents()));
closable(LAYER.reader, () => talents.open, () => closeTalents());

function openTalents() {
  talents.open = true;
  askPlayer(true);
  renderTalents();
  clearInterval(talents.timer);
  talents.timer = setInterval(() => askPlayer(false), PLAYER_FRESH);
}
function closeTalents() {
  talents.open = talents.menu = false;
  clearInterval(talents.timer);
  $("talents").hidden = true;
}
on("playerShown", () => { if (talents.open) renderTalents(); });

const rankLine = (level, rank, ranks) => `<span class="tw-lvl${level == null ? " taken" : ""}">${level == null ? "taken" : `lvl ${level}`}</span> ${rank}/${ranks}`;

function talentCell(t, plan) {
  const levels = plan?.levels?.[String(t.node)] || null, have = plan?.ranks?.[String(t.node)] || 0;
  const shown = levels ? levels.length : have;
  const lines = (levels || []).map((lv, i) => `<div>${rankLine(lv, i + 1, t.ranks)}</div>`).join("");
  return `<div class="tw-cell${levels ? " lit" : ""}${have ? " have" : ""}" style="grid-row:${t.row + 1};grid-column:${t.col + 1}" data-hover="talent:${t.node}">
    <span class="tw-icon"><img src="/fileicon/${esc(t.icon)}.jpg" alt=""><span class="tw-rank">${shown}/${t.ranks}</span></span>
    ${lines ? `<div class="tw-levels">${lines}</div>` : ""}</div>`;
}

function treeArrows(tree) {
  const at = Object.fromEntries(tree.talents.map((t) => [t.node, t]));
  const cx = (t) => t.col * TW_CELL + TW_CELL / 2, top = (t) => t.row * TW_ROW, mid = (t) => top(t) + TW_ICON / 2;
  const paths = [];
  for (const t of tree.talents) {
    for (const n of t.needs || []) {
      const s = at[n];
      if (!s) continue;
      if (s.col === t.col) paths.push(`M${cx(s)} ${top(s) + TW_ICON} V${top(t) - 3}`);
      else if (s.row === t.row) paths.push(`M${cx(s) + Math.sign(t.col - s.col) * TW_ICON / 2} ${mid(s)} H${cx(t) - Math.sign(t.col - s.col) * (TW_ICON / 2 + 3)}`);
      else paths.push(`M${cx(s) + Math.sign(t.col - s.col) * TW_ICON / 2} ${mid(s)} H${cx(t)} V${top(t) - 3}`);
    }
  }
  const rows = Math.max(0, ...tree.talents.map((t) => t.row)) + 1;
  return `<svg class="tw-arrows" width="${4 * TW_CELL}" height="${rows * TW_ROW}" aria-hidden="true">
    <defs><marker id="tw-head" viewBox="0 0 8 8" refX="6" refY="4" markerWidth="6" markerHeight="6" orient="auto"><path d="M0 0L8 4L0 8z"/></marker></defs>
    ${paths.map((d) => `<path d="${d}" marker-end="url(#tw-head)"/>`).join("")}</svg>`;
}

function treeHtml(tree, i, plan) {
  const points = tree.talents.reduce((sum, t) => sum + (plan?.levels?.[String(t.node)]?.length || 0), 0);
  const rows = Math.max(0, ...tree.talents.map((t) => t.row)) + 1;
  return `<section class="tw-tree${plan?.build?.tree === i + 1 ? " main" : ""}">
    <h3 class="tw-name">${esc(tree.name)}<small>${points} points</small></h3>
    <div class="tw-grid" style="grid-template-rows:repeat(${rows},${TW_ROW}px)">${treeArrows(tree)}${tree.talents.map((t) => talentCell(t, plan)).join("")}</div></section>`;
}

function buildMenu(plan) {
  if (!plan) return "";
  const list = talents.menu ? `<div class="tw-menu" role="menu">${(plan.builds || []).map((b) => `<button class="tw-build${b.key === plan.build.key ? " on" : ""}" role="menuitem" data-tw-build="${esc(b.key)}">${esc(b.name)}${b.note ? `<small>${esc(b.note)}</small>` : ""}</button>`).join("")}</div>` : "";
  return `<div class="tw-pick"><button class="key small" data-tw="menu" aria-haspopup="true" aria-expanded="${talents.menu}" title="Pick the build the talent planner follows">Build: ${esc(plan.build.name)} &#9662;</button>${
    plan.picked ? `<button class="key small" data-tw="reset" title="Let your pick go: the build for the tree you spend the most in comes back">Reset</button>` : ""}${list}</div>`;
}

function renderTalents() {
  const d = player.data, box = $("talents"), plan = d?.talentPlan;
  const bar = `<div class="rd-bar"><span class="rd-keys">${buildMenu(plan)}</span>
    <span class="rd-title">Talents<small>${d ? `${esc(playerName())}, ${esc(d.name)}. ` : ""}Your build's talents are lit, each with the level its ranks are taken at</small></span>
    <span class="rd-keys"><button class="key small square x-mark" data-tw="close" title="Close (Escape)">&times;</button></span></div>`;
  const body = !d ? `<p class="muted">${spellsNote("The talent trees come from the game's own tables once the game has said who's playing.")}</p>`
    : !(d.trees || []).length ? `<p class="muted">The game's tables have no talent trees for ${esc(d.name)}.</p>`
    : `${plan && !plan.known ? `<p class="muted tw-note">Your talents reach the Index with the addon's next /reload.</p>` : ""}
      <div class="tw-trees">${d.trees.map((t, i) => treeHtml(t, i, plan)).join("")}</div>`;
  setHtml(box, `${bar}<div class="rd-scroll tw-scroll">${body}</div>`);
  box.hidden = false;
}

function talentHoverHtml(name) {
  const node = name.slice("talent:".length), d = player.data;
  const t = (d?.trees || []).flatMap((tr) => tr.talents).find((x) => String(x.node) === node);
  if (!t) return "";
  const tip = keptTip(spellTips, t.id);
  if (tip === undefined && !player.tipAsking.has(t.id)) {
    player.tipAsking.add(t.id);
    loadSpellTip(t.id).then((got) => { player.tipAsking.delete(t.id); if (got) refreshHover(); });
  }
  const levels = d.talentPlan?.levels?.[node] || [];
  const ranks = levels.map((lv, i) => `<div class="sp-line">${rankLine(lv, i + 1, t.ranks)}</div>`).join("");
  return `<div class="sp-tip">${tip?.html || `<b class="q">${esc(t.name)}</b>`}${ranks ? `<div class="sp-line sp-first">Your build</div>${ranks}` : ""}</div>`;
}
HOVERS["talent:"] = (pinned, name) => talentHoverHtml(name);

function talentsClicked(e) {
  const pick = e.target.closest("button[data-tw-build]"), key = e.target.closest("button[data-tw]")?.dataset.tw;
  if (key === "close") return closeTalents();
  if (key === "menu") { talents.menu = !talents.menu; return renderTalents(); }
  if (key === "reset" || pick) {
    talents.menu = false;
    postJson("/api/talentbuild", { build: pick ? pick.dataset.twBuild : null })
      .then(() => askPlayer(true), (err) => askFailed("your talent build", err));
    renderTalents();
  }
}
$("talents").addEventListener("click", talentsClicked);
