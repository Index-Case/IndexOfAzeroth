// The Index of Azeroth. Copyright 2026 Index Case <indexofazeroth@pm.me>. PolyForm Strict 1.0.0, see LICENSE.md.
"use strict";

const METER_REFRESH_MS = 30000;
const METER_ICONS = { meter: "ability_dualwield", fight: "ability_meleedamage", auto: "ability_meleedamage", unknown: "inv_misc_questionmark",
  dungeon: "inv_misc_book_09", boss: "achievement_boss_edwinvancleef",
  spells: "inv_misc_book_11" };
const mt = { open: false, data: null, failed: false, timer: 0, fight: null, shown: null, fightFailed: false, icons: {}, scroll: 0,
  for: null, view: "list", choice: { ...METER_CHOICE }, picked: null };
const MT_WORDS = wordsOf("page.meter");
const mtW = (key, fill) => fillWords(MT_WORDS[key], fill) ?? "";
const mtIcon = (name) => `<img class="mt-ico" src="/icon/${esc(name)}.jpg" alt="">`;


function mtPicked() {
  const c = mt.choice, key = `${c.kind}|${c.place}`;
  if (mt.picked?.from !== mt.data || mt.picked.key !== key) mt.picked = { from: mt.data, key, d: meterChosen(mt.data, c) };
  return mt.picked.d;
}

function mtChoiceHtml() {
  const key = (attr, k, on) => `<button class="key small" ${attr}="${k}" aria-pressed="${on}" title="${esc(mtW(`kind.${k}.tip`))}">${esc(mtW(`kind.${k}`))}</button>`;
  return `<div class="mt-choice">${METER_KINDS.map((k) => key("data-mt-kind", k, mt.choice.kind === k)).join("")}<span class="mt-choice-gap"></span>${
    METER_PLACES.map((k) => key("data-mt-place", k, mt.choice.place === k)).join("")}</div>`;
}

const mtNoneHtml = () => `<p class="muted mt-empty">${esc(mtW("kind.none"))}</p>`;


const mtOthers = (f) => (f.multi ? f.ne - 1 : 0);
function mtFightName(f) {
  const name = f.name || mtW("list.target.unknown"), others = mtOthers(f);
  return others > 0 ? mtW("kind.target.more", { name, n: others }) : name;
}
function mtTarget(f) {
  const others = mtOthers(f), name = esc(mtFightName(f));
  const shown = others > 0 ? `<span title="${esc(wordCount("page.meter.kind.target.more.tip", others))}">${name}</span>` : name;
  const mark = (k, tip) => `<img class="mt-ico mt-mark" src="/icon/${METER_ICONS[k]}.jpg" alt="" title="${esc(mtW(tip, { dungeon: f.dg }))}">`;
  return `${shown}${f.dg ? mark("dungeon", "kind.dungeon.mark.tip") : ""}${f.boss ? mark("boss", "kind.boss.mark.tip") : ""}`;
}

const MT_COLUMNS = ["when", "target", "duration", "dps", "damage", "taken"];
const MT_PULL_COLUMNS = ["enemies", "ttk", "main"];
const mtColumns = () => (mt.choice.kind === "single" ? MT_COLUMNS : [...MT_COLUMNS, ...MT_PULL_COLUMNS]);
const mtNone = () => `<span class="msp-none">${esc(mtW("list.none.value"))}</span>`;

function mtRow(f) {
  const pull = mt.choice.kind === "single" ? "" : `<td class="num">${num(f.ne)}</td><td class="num">${f.ttk == null ? mtNone() : esc(duration(f.ttk))}</td>
    <td class="num">${f.main == null ? mtNone() : esc(mtW("list.main.value", { pct: f.main }))}</td>`;
  return `<tr class="mt-row" data-fight="${f.t}" title="${esc(mtW("list.open.tip"))}"><td class="mt-when">${mtIcon(METER_ICONS.fight)}${esc(pvWhen(f.t))}</td>
    <td class="mt-target">${mtTarget(f)}</td><td class="num">${esc(duration(f.len))}</td>
    <td class="num mt-dps">${num(f.dps)}</td><td class="num">${num(f.dmg)}</td><td class="num">${num(f.taken)}</td>${pull}</tr>`;
}

function mtListHtml(d) {
  const building = d.building ? `<p class="mt-building">${esc(wordCount("page.meter.window.building", d.building))}</p>` : "";
  if (!d.fights.length) return building || `<p class="muted mt-empty">${esc(mtW("window.empty"))}</p>`;
  const picked = mtPicked();
  if (!picked.fights.length) return `${building}${mtChoiceHtml()}${mtNoneHtml()}`;
  const heads = mtColumns().map((k, n) => `<th${n > 1 ? ' class="num"' : ""}${MT_PULL_COLUMNS.includes(k) ? ` title="${esc(mtW(`list.${k}.tip`))}"` : ""}>${
    esc(mtW(`list.${k}`))}</th>`).join("");
  const { rows, more } = meterShown(picked);
  return `${building}${mtChoiceHtml()}${meterGraphHtml(picked)}<div class="mt-scroll"><table class="mt-table"><thead><tr>${heads}</tr></thead><tbody>${rows.map(mtRow).join("")}</tbody></table>${
    more ? `<p class="mt-more">${esc(wordCount("page.meter.list.more", more))}</p>` : ""}</div>`;
}


function mtSpellName(s) {
  const own = s.id == null ? mtW("fight.auto") : s.name || mtW("fight.unknown");
  return s.by ? `${own} (${s.by})` : own;
}
const mtSpellIcon = (s) => (s.id == null ? METER_ICONS.auto : (s.name && mt.icons[s.name]) || METER_ICONS.unknown);

function mtSpellRow(s, pull) {
  const per = meterPerCast(s);
  return `<tr><td>${mtIcon(mtSpellIcon(s))}<span class="mt-spell">${esc(mtSpellName(s))}</span></td><td class="num">${num(s.dmg)}</td>
    <td class="num">${esc(mtW("fight.share.value", { share: s.share.toFixed(1) }))}</td><td class="num">${num(s.hits)}</td>
    <td class="num">${num(s.crits)}</td><td class="num">${num(s.misses)}</td>${pull ? `<td class="num">${per == null ? mtNone() : per.toFixed(1)}</td>` : ""}</tr>`;
}

function mtEnemyRow(e) {
  const mark = e.kind ? `<span class="mt-kind mt-kind-${e.kind}">${esc(mtW(`fight.kind.${e.kind}`))}</span>` : "";
  return `<tr><td>${mtIcon(e.kind === "boss" ? METER_ICONS.boss : METER_ICONS.fight)}<span class="mt-spell">${esc(e.name || mtW("list.target.unknown"))}</span>${mark}</td>
    <td class="num">${num(e.dmg)}</td><td class="num">${esc(mtW("fight.share.value", { share: e.share.toFixed(1) }))}</td>
    <td class="num">${e.died == null ? `<span class="msp-none" title="${esc(mtW("fight.died.none.tip"))}">${esc(mtW("list.none.value"))}</span>`
    : esc(mtW("fight.died.value", { secs: e.died.toFixed(1) }))}</td></tr>`;
}

function mtFightHtml(f) {
  const tiles = [["dps", num(f.dps)], ["damage", num(f.dmg)], ["duration", esc(duration(f.len))], ["taken", num(f.taken)]]
    .map(([k, v]) => pvTile(mtW(`list.${k}`), v)).join("");
  const head = `<h2 class="mt-heading">${esc(mtW("fight.heading", { name: mtFightName(f), when: pvWhen(f.t) }))}</h2><div class="mt-tiles">${tiles}</div>`;
  const o = mt.shown;
  if (!o) return `${head}<p class="muted">${esc(mt.fightFailed ? mtW("fight.failed") : mtW("fight.loading"))}</p>`;
  if (!o.spells.length) return `${head}<p class="muted mt-empty">${esc(mtW("fight.none"))}</p>`;
  const th = (k, n) => `<th${n ? ' class="num"' : ""}${mtW(`fight.${k}.tip`) ? ` title="${esc(mtW(`fight.${k}.tip`))}"` : ""}>${esc(mtW(`fight.${k}`))}</th>`;
  const foes = o.multi ? `<h3 class="msp-heading">${mtIcon(METER_ICONS.fight)}${esc(mtW("fight.enemies.title"))}</h3><table class="mt-table"><thead><tr>${
    ["enemy", "damage", "share", "died"].map(th).join("")}</tr></thead><tbody>${meterEnemies(o).map(mtEnemyRow).join("")}</tbody></table>` : "";
  const heads = ["spell", "damage", "share", "hits", "crits", "misses", ...(o.multi ? ["percast"] : [])].map(th).join("");
  return `${head}<div class="mt-scroll">${foes}<h3 class="msp-heading">${mtIcon(METER_ICONS.spells)}${esc(mtW("fight.spells.title"))}</h3><table class="mt-table"><thead><tr>${heads}</tr></thead><tbody>${
    meterSpells(o).map((s) => mtSpellRow(s, o.multi)).join("")}</tbody></table></div>`;
}

function askMeterIcons(spells) {
  const need = [...new Set(spells.map((s) => s.name).filter((n) => n && !(n in mt.icons)))];
  if (!need.length) return;
  getJson(`/api/spellicons?names=${encodeURIComponent(need.join("|"))}`, { key: "meter-spellicons", force: true })?.then((j) => {
    for (const n of need) mt.icons[n] = j[n] || null;
    renderMeter();
  }, () => {});
}

function openMeterFight(row) {
  mt.scroll = $("meter").querySelector(".mt-scroll")?.scrollTop || 0;
  mt.fight = row;
  mt.shown = null;
  mt.fightFailed = false;
  renderMeter();
  getJson(meterFightUrl(mt.data.char, row.t), { force: true })?.then((j) => {
    if (mt.fight !== row) return;
    mt.shown = meterFightAnswer(j);
    renderMeter();
    askMeterIcons(mt.shown.spells);
  }, () => { if (mt.fight === row) { mt.fightFailed = true; renderMeter(); } });
}

function meterBack() {
  if (mt.fight == null) return meterSpellsBack();
  mt.fight = null;
  mt.shown = null;
  renderMeter();
  const list = $("meter").querySelector(".mt-scroll");
  if (list) list.scrollTop = mt.scroll;
}


function renderMeter() {
  if (!mt.open) return;
  const opened = mt.fight != null;
  let body;
  if (opened) body = mtFightHtml(mt.fight);
  else if (!mt.data) body = `<p class="muted">${esc(mt.failed ? mtW("window.failed") : mtW("window.loading"))}</p>`;
  else body = mt.view === "spells" ? meterSpellsHtml(mt.data) : mtListHtml(mt.data);
  const tip = opened ? meterBackTo() : meterBackFrom();
  const back = tip ? `<button class="key small" data-back="1" title="${esc(tip)}">${esc(mtW("fight.back"))}</button>` : "";
  setHtml($("meter"), `<div class="j-bar"><span class="j-bar-keys">${back}</span><span class="j-bar-title">${esc(mtW("window.title"))}</span>
    <span class="j-bar-end">${helpButton("meter")}<button class="key small square x-mark" data-close="1" title="${esc(mtW("window.close.tip"))}">&times;</button></span></div>
    <div class="j-body mt-body">${body}</div>`);
  drawMeterGraph();
}

function askMeter() {
  if (!app.character) return null;
  return getJson(meterUrl(app.character), { key: "/api/meter", force: true })?.then(meterAnswer);
}

function loadMeter() {
  mt.for = app.character;
  askMeter()?.then((d) => { mt.data = d; mt.failed = false; renderMeter(); }, () => { mt.failed = true; renderMeter(); });
}

function openMeter() {
  mt.open = true;
  mt.view = "list";
  emit("window", "meter");
  $("meter").hidden = false;
  renderMeter();
  loadMeter();
  clearInterval(mt.timer);
  mt.timer = setInterval(loadMeter, METER_REFRESH_MS);
}

function closeMeter() {
  mt.open = false;
  clearInterval(mt.timer);
  $("meter").hidden = true;
}

$("meter").addEventListener("click", (e) => {
  const b = e.target.closest("button");
  if (b?.dataset.close) return closeMeter();
  if (b?.dataset.back) return meterBack();
  if (b?.dataset.mtKind || b?.dataset.mtPlace) {
    mt.choice = { ...mt.choice, ...(b.dataset.mtKind ? { kind: b.dataset.mtKind } : { place: b.dataset.mtPlace }) };
    return renderMeter();
  }
  const row = !b && e.target.closest("tr.mt-row");
  const fight = row && mt.data?.fights.find((f) => String(f.t) === row.dataset.fight);
  if (fight) openMeterFight(fight);
});
on("snapshot", () => {
  if (!mt.open || !app.character || mt.for === app.character) return;
  Object.assign(mt, { data: null, failed: false, fight: null, shown: null, view: "list" });
  loadMeter();
  renderMeter();
});
closable(LAYER.journal, () => mt.open, closeMeter);
on("window", (w) => { if (w !== "meter" && mt.open) closeMeter(); });
