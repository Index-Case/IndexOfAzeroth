// The Index of Azeroth. Copyright 2026 Index Case <indexofazeroth@pm.me>. PolyForm Strict 1.0.0, see LICENSE.md.
"use strict";

const ms = { data: null, asked: null, failed: false, spell: null, sort: "dmg" };
const MS_WORDS = wordsOf("page.meter.spells");
const msW = (key, fill) => fillWords(MS_WORDS[key], fill) ?? "";
const MS_SPARK_W = 84, MS_SPARK_H = 18;
const MS_ICONS = { spells: "inv_misc_book_11", procs: "spell_nature_lightning" };
const msPct = (v) => (v == null ? msW("none.value") : msW("pct", { pct: v.toFixed(1) }));
const msNum = (v) => (v == null ? msW("none.value") : num(v));
const msOne = (v) => (v == null ? msW("none.value") : v.toFixed(1));

const msStamp = (d) => `${d.char}|${d.building}|${d.fights.length}|${d.fights.length ? d.fights[d.fights.length - 1].t : ""}`;

function loadMeterSpells() {
  const stamp = msStamp(mt.data);
  if (stamp === ms.asked) return;
  ms.asked = stamp;
  getJson(meterSpellsUrl(mt.data.char), { key: "/api/meter/spells", force: true })?.then((j) => {
    if (ms.asked !== stamp) return;
    ms.data = meterSpellsAnswer(j);
    ms.failed = false;
    drawMeterGraph();
  }, () => {
    if (ms.asked !== stamp) return;
    ms.failed = true;
    ms.asked = null;
    drawMeterSpells();
  });
}

const msData = () => (ms.data && ms.data.char === mt.data.char ? ms.data : null);
const msAt = (f) => mg.scale.toPos(f.t);

function meterSpellsHtml(d) {
  const building = d.building ? `<p class="mt-building">${esc(wordCount("page.meter.spells.building", d.building))}</p>` : "";
  const picked = mtPicked();
  if (!picked.fights.length) return `${building}${mtChoiceHtml()}${mtNoneHtml()}`;
  return `${building}${mtChoiceHtml()}${meterGraphHtml(picked)}<div class="mt-scroll msp-body" id="msp-body"></div>`;
}

function msPicked(d) {
  const ts = new Set(mtPicked().fights.map((f) => f.t));
  return d.fights.filter((f) => ts.has(f.t));
}


function msSides(r) {
  if (r.withDps != null) {
    return `<span title="${esc(msW("dps.tip", { with: num(r.withDps), without: num(r.withoutDps) }))}">${esc(msW("dps.value", { with: num(r.withDps), without: num(r.withoutDps) }))}</span>`;
  }
  const parts = [r.need.with && wordCount("page.meter.spells.dps.need.with", r.need.with), r.need.without && wordCount("page.meter.spells.dps.need.without", r.need.without)];
  return `<span class="msp-none" title="${esc(msW("dps.need", { list: rpAndList(parts.filter(Boolean)) }))}">${esc(msW("none.value"))}</span>`;
}

const msSpark = (series, v, tip) => tcSpark(mgAlong(series, mg.view, msAt).map((p) => ({ t: msAt(p), v: v(p) })), mg.view, MS_SPARK_W, MS_SPARK_H, tip);

const MS_HEADS = [["spell"], ["damage", "dmg"], ["share"], ["casts", "casts"], ["perfight", "perFight"], ["hits", "hits"], ["crit", "crit"], ["avg", "avg"],
  ["percast", "perCast"], ["dps", "dps"], ["graph"]];

function msTableHtml(shown, all) {
  const heads = MS_HEADS.map(([k, sort], n) => {
    const label = esc(msW(`head.${k}`));
    const inner = sort ? `<button class="msp-sort" data-ms-sort="${sort}" aria-pressed="${ms.sort === sort}" title="${esc(msW(`head.${k}.tip`))}">${label}</button>`
      : `<span title="${esc(msW(`head.${k}.tip`))}">${label}</span>`;
    return `<th${n && n < MS_HEADS.length - 1 ? ' class="num"' : ""}>${inner}</th>`;
  }).join("");
  const rows = spellSorted(spellTable(shown), ms.sort).map((r) => `<tr class="msp-row" data-ms-spell="${esc(r.key)}" title="${esc(msW("row.tip"))}">
    <td>${mtIcon(mtSpellIcon(r))}<span class="mt-spell">${esc(mtSpellName(r))}</span></td><td class="num">${num(r.dmg)}</td><td class="num">${msPct(r.share)}</td>
    <td class="num">${msNum(r.casts)}</td><td class="num">${msOne(r.perFight)}</td><td class="num">${num(r.hits)}</td><td class="num">${msPct(r.crit)}</td>
    <td class="num">${msNum(r.avg)}</td><td class="num">${msOne(r.perCast)}</td><td class="num">${msSides(r)}</td><td class="msp-spark">${msSpark(spellSeries(all, r.key), (p) => p.share, msW("graph.share.tip"))}</td></tr>`).join("");
  return `<h3 class="msp-heading">${mtIcon(MS_ICONS.spells)}${esc(msW("spells.title"))}</h3>
    <table class="mt-table msp-table"><thead><tr>${heads}</tr></thead><tbody>${rows}</tbody></table>`;
}

function msProcsHtml(shown, all) {
  const procs = procTable(shown);
  const head = `<h3 class="msp-heading">${mtIcon(MS_ICONS.procs)}${esc(msW("procs.title"))}</h3>`;
  if (!procs.length) return `${head}<p class="muted mt-empty">${esc(msW("procs.none"))}</p>`;
  const heads = ["aura", "perfight", "uptime", "damage", "graph"].map((k, n) => `<th${n && n < 4 ? ' class="num"' : ""} title="${esc(msW(`procs.${k}.tip`))}">${esc(msW(`procs.${k}`))}</th>`).join("");
  const rows = procs.map((p) => `<tr><td>${mtIcon(mtSpellIcon(p))}<span class="mt-spell">${esc(p.name || mtW("fight.unknown"))}</span></td>
    <td class="num">${p.perFight.toFixed(1)}</td><td class="num">${msPct(p.uptime)}</td>
    <td class="num">${p.dmg == null ? `<span class="msp-none" title="${esc(msW("procs.damage.none"))}">${esc(msW("none.value"))}</span>` : num(p.dmg)}</td>
    <td class="msp-spark">${msSpark(procSeries(all, p.key), (x) => x.uptime, msW("graph.uptime.tip"))}</td></tr>`).join("");
  return `${head}<table class="mt-table msp-table"><thead><tr>${heads}</tr></thead><tbody>${rows}</tbody></table>`;
}


function msOpened(shown) {
  return spellTable(shown).find((r) => r.key === ms.spell) || null;
}

function msSpellHtml(shown, all) {
  const r = msOpened(shown), whom = all.flatMap((f) => f.spells).find((s) => s.key === ms.spell);
  const name = whom ? mtSpellName(whom) : "";
  const head = whom ? `<h3 class="msp-heading">${mtIcon(mtSpellIcon(whom))}${esc(name)}</h3>` : "";
  if (!r) return `${head}<p class="muted mt-empty">${esc(msW("spell.unused"))}</p>`;
  const tiles = [["damage", num(r.dmg)], ["casts", msNum(r.casts)], ["perfight", msOne(r.perFight)], ["crit", msPct(r.crit)], ["avg", msNum(r.avg)]]
    .map(([k, v]) => pvTile(msW(`head.${k}`), v)).join("");
  const auras = spellAuras(shown, ms.spell);
  const split = `<h3 class="msp-heading">${mtIcon(MS_ICONS.procs)}${esc(msW("split.title", { name }))}</h3>`;
  if (!auras.length) return `${head}<div class="msp-tiles">${tiles}</div>${split}<p class="muted mt-empty">${esc(msW("split.none"))}</p>`;
  const cells = (x) => `<td class="num">${num(x.hits)}</td><td class="num">${msNum(x.avg)}</td><td class="num">${msPct(x.crit)}</td><td class="num">${num(x.dmg)}</td>`;
  const sub = ["hits", "avg", "crit", "damage"].map((k) => `<th class="num">${esc(msW(`head.${k}`))}</th>`).join("");
  const rows = auras.map((a) => `<tr><td title="${esc(wordCount("page.meter.spells.split.fights", a.fights))}">${mtIcon(mtSpellIcon(a))}<span class="mt-spell">${
    esc(a.name || mtW("fight.unknown"))}</span></td>${cells(a.under)}${cells(a.without)}</tr>`).join("");
  return `${head}<div class="msp-tiles">${tiles}</div>${split}<table class="mt-table msp-table msp-split"><thead>
    <tr><th rowspan="2">${esc(msW("split.aura"))}</th><th colspan="4" class="msp-group" title="${esc(msW("split.under.tip"))}">${esc(msW("split.under"))}</th>
    <th colspan="4" class="msp-group" title="${esc(msW("split.without.tip"))}">${esc(msW("split.without"))}</th></tr><tr>${sub}${sub}</tr></thead><tbody>${rows}</tbody></table>`;
}

function meterSpellPlot() {
  const d = mt.view === "spells" && ms.spell ? msData() : null;
  if (!d) return null;
  const series = spellSeries(spellFights(msPicked(d)).kept, ms.spell), whom = d.fights.flatMap((f) => f.spells || []).find((s) => s.key === ms.spell);
  const name = whom ? mtSpellName(whom) : "";
  const chart = (id, of, smooth) => (v, at) => {
    const shown = inStretch(series, v, at);
    return { id: `spell-${id}`, caption: msW(`graph.${id}`, { name }), values: valueTicks(Math.max(0, ...shown.map((p) => Math.max(p[of], p[smooth]))), undefined, true),
      dots: shown.map((p) => ({ t: at(p), v: p[of], data: { "mg-fight": p.t },
        title: msW("dot.tip", { when: pvWhen(p.t), dmg: num(p.dmg), casts: num(p.casts) }) })),
      line: mgAlong(series, v, at).map((p) => ({ t: at(p), v: p[smooth] })) };
  };
  const charts = [series.some((p) => p.dmg) && chart("damage", "dmg", "smoothDmg"), series.some((p) => p.casts) && chart("casts", "casts", "smoothCasts")].filter(Boolean);
  return { title: () => msW("graph.title", { name }), charts: (v, at) => (charts.length ? charts : [chart("damage", "dmg", "smoothDmg")]).map((c) => c(v, at)) };
}


function drawMeterSpells() {
  const box = $("msp-body");
  if (!box || !mt.open || mt.fight || mt.view !== "spells") return;
  const d = msData();
  if (!d) return setHtml(box, `<p class="muted">${esc(ms.failed ? msW("failed") : msW("loading"))}</p>`);
  const picked = msPicked(d), { kept, unrecorded } = spellFights(inStretch(picked, mg.view, msAt)), all = spellFights(picked).kept;
  const lost = unrecorded ? `<p class="mg-note msp-unrecorded">${esc(wordCount("page.meter.spells.unrecorded", unrecorded))}</p>` : "";
  if (!kept.length) return setHtml(box, `${lost}<p class="muted mt-empty">${esc(msW("none"))}</p>`);
  setHtml(box, lost + (ms.spell ? msSpellHtml(kept, all) : msTableHtml(kept, all) + msProcsHtml(kept, all)));
  askMeterIcons([...kept.flatMap((f) => f.spells), ...kept.flatMap((f) => f.auras)]);
}

function meterBackTo() {
  if (mt.view !== "spells") return mtW("fight.back.tip");
  const whom = ms.spell && msData()?.fights.flatMap((f) => f.spells || []).find((s) => s.key === ms.spell);
  return whom ? msW("back.spell.tip", { name: mtSpellName(whom) }) : msW("back.tip");
}
function meterBackFrom() {
  if (mt.view !== "spells") return null;
  return ms.spell ? msW("back.tip") : mtW("fight.back.tip");
}

function meterSpellsBack() {
  if (ms.spell) ms.spell = null;
  else mt.view = "list";
  renderMeter();
}

function toggleMeterSpells(open) {
  mt.view = open ? "spells" : "list";
  ms.spell = null;
  renderMeter();
}

function openMeterSpell(key) {
  ms.spell = key;
  renderMeter();
  $("meter").querySelector(".msp-body")?.scrollTo?.(0, 0);
}

$("meter").addEventListener("click", (e) => {
  const b = e.target.closest?.("button[data-mg-view], button[data-ms-sort]");
  if (b?.dataset.mgView) { toggleMeterSpells(b.getAttribute("aria-pressed") !== "true"); return; }
  if (b) { ms.sort = b.dataset.msSort; drawMeterSpells(); return; }
  const row = e.target.closest?.("tr[data-ms-spell]");
  if (row) openMeterSpell(row.dataset.msSpell);
});
on("meterdrawn", () => {
  if (mt.view !== "spells") return;
  loadMeterSpells();
  drawMeterSpells();
});
on("window", (w) => { if (w === "meter") ms.spell = null; });
