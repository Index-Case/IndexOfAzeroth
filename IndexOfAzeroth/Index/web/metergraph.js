// The Index of Azeroth. Copyright 2026 Index Case <indexofazeroth@pm.me>. PolyForm Strict 1.0.0, see LICENSE.md.
"use strict";

const MG_ICONS = { level: "spell_holy_surgeoflight", weapon: "inv_sword_04", gear: "inv_chest_chain_05", spell: "inv_misc_book_11",
  talent: "ability_marksmanship" };
const MG_RINGS = { level: "gold", weapon: "crimson", gear: "bronze", spell: "jade", talent: "blue" };
const MG_WIDTH = 800;
const mg = { way: "session", view: null, follow: "recent", data: null, char: null, series: [], scale: TRUE_TIME, whole: null, recent: null,
  lanes: null, bases: {}, norm: false };
const mgW = (key, fill) => mtW(`graph.${key}`, fill);
const mgSame = (a, b) => !!a && !!b && Math.abs(a.from - b.from) < 1 && Math.abs(a.to - b.to) < 1;

function takeMeterGraph(d) {
  if (mg.data === d && mg.scale.kind === mg.way) return;
  if (d.char !== mg.char) mg.follow = "recent";
  const was = mg.scale, view = mg.view;
  mg.data = d;
  mg.char = d.char;
  mg.bases = meterBaselines(d.fights);
  mg.series = meterSeries(d.fights, mg.bases);
  mg.scale = meterScale(mg.series, mg.way);
  mg.whole = meterWhole(mg.series, d.events, mg.scale);
  mg.recent = meterRecent(mg.series, mg.whole, mg.scale);
  mg.lanes = meterLanes(mg.series);
  if (mg.follow) { mg.view = mg[mg.follow]; return; }
  const at = (p) => mg.scale.toPos(was.fromPos(p)), from = at(view.from);
  mg.view = zoomAbout({ from, to: at(view.to) }, from, 1, mg.whole, METER_ZOOM_LEAST);
}

function meterGraphHtml(d) {
  if (!d.fights.length) return "";
  return `<div class="mg"><div class="mg-keys" id="mg-keys"></div>
    <div class="mg-plot tc-box" id="mg-plot"><div id="mg-draw"></div><div class="mg-pick" id="mg-pick" hidden></div></div>
    <p class="mg-note" id="mg-note" hidden>${esc(mgW("undated"))}</p><p class="mg-note" id="mg-norm-note" hidden></p></div>`;
}

const mgItem = (id) => app.itemInfo[id]?.n || null;

function mgMarkWords(m) {
  const when = { when: pvWhen(m.at) };
  const rank = (r) => mgW("mark.talent.rank", { name: r.name, was: r.was, now: r.now });
  const line = m.key === "talent.ranks" ? mgW("mark.talent.ranks", { list: rpAndList(m.ranks.map(rank)), ...when })
    : m.n == null ? mgW(`mark.${m.key}`, { ...m.fill, ...when }) : wordCount(`page.meter.graph.mark.${m.key}`, m.n, when);
  const g = mg.norm && m.gain;
  const said = g ? `${line} ${mgW("mark.level.gain", { prev: g.from, before: num(g.was), level: g.level, after: num(g.now) })}` : line;
  return m.more ? `${said} ${wordCount("page.meter.graph.mark.more", m.more)}` : said;
}

const mgKindFights = () => mtW(`kind.${mt.choice.kind}.fights`);

function mgDotWords(f) {
  const fill = { name: mtFightName(f), when: pvWhen(f.t), dps: num(f.dps), level: f.lvl, least: METER_BASE_LEAST,
    fights: mgKindFights() };
  if (!mg.norm) return mgW("dot.tip", fill);
  if (f.pct != null) return mgW("norm.dot.tip", { ...fill, pct: num(f.pct), median: num(f.base) });
  return mgW(f.lvl == null ? "norm.dot.unlevelled" : "norm.dot.few", fill);
}

function mgPlot(shown, along, at) {
  const raw = valueTicks(Math.max(0, ...shown.map((f) => Math.max(f.dps, f.smooth))));
  const dots = (v) => shown.map((f) => ({ t: at(f), v: v(f), data: { "mg-fight": f.t }, title: mgDotWords(f) }));
  const line = (v) => along.map((f) => ({ t: at(f), v: v(f) }));
  if (!mg.norm) return { values: { ...raw, label: num }, dots: dots((f) => f.dps), line: line((f) => f.smooth) };
  const pcts = shown.flatMap((f) => [f.pct, f.pctSmooth]).filter((p) => p != null);
  return { values: { ...valueTicks(Math.max(100, ...pcts)), label: (p) => mgW("norm.value", { pct: num(p) }) }, rule: 100,
    dots: dots((f) => f.pct), line: line((f) => f.pctSmooth), ghost: { line: line((f) => f.smooth), top: raw.top } };
}

function mgNormNote(shown) {
  if (!mg.norm) return "";
  const un = meterUnbased(shown), fill = { least: METER_BASE_LEAST, fights: mgKindFights() };
  return [un.few && wordCount("page.meter.graph.norm.few", un.few, fill),
    un.unlevelled && wordCount("page.meter.graph.norm.unlevelled", un.unlevelled, fill)].filter(Boolean).join(" ");
}

function mgLane(name, runs, label, tip) {
  const at = mg.scale.toPos;
  return { name: mgW(`lane.${name}`), runs: runs.map((r) => ({ from: at(r.from), to: at(r.to), label: label(r.value),
    title: mgW(`lane.${name}.tip`, { from: pvWhen(r.from), to: pvWhen(r.to), n: r.n, ...tip(r.value) }) })) };
}

function mgLanes() {
  const named = (ids) => rpAndList(ids.filter(Boolean).map((id) => mgItem(id) || mgW("lane.item.unknown")));
  const all = [mgLane("level", mg.lanes.level, String, (v) => ({ level: v })),
    mgLane("weapons", mg.lanes.weapons, (v) => mgItem(v.find(Boolean)) || "", (v) => ({ items: named(v) || mgW("lane.weapons.none") })),
    mgLane("gear", mg.lanes.gear, () => "", () => ({})),
    mgLane("talents", mg.lanes.talents, (v) => v.join("/"), (v) => ({ points: v.join("/") }))];
  return all.filter((lane) => lane.runs.length);
}

function askMeterItems(marks) {
  const ids = [...mg.lanes.weapons.flatMap((r) => r.value), ...marks.flatMap((e) => (e.kind === "gear" ? e.slots.map((s) => s.now) : []))];
  wantItemInfo(ids.filter((id) => id && !app.itemInfo[id]), drawMeterGraph);
}

function mgAlong(series, v, at) {
  const first = series.findIndex((f) => at(f) >= v.from), last = series.findLastIndex((f) => at(f) <= v.to);
  return series.slice(Math.max(0, (first < 0 ? series.length : first) - 1), last + 2);
}

const MG_DPS = {
  title: () => mgW("title"),
  charts: (v, at) => [{ id: "meter", ...mgPlot(inStretch(mg.series, v, at), mgAlong(mg.series, v, at), at) }],
};

function drawMeterGraph() {
  const d = mt.open && !mt.fight && mt.data ? mtPicked() : null;
  if (!d?.fights.length) return;
  takeMeterGraph(d);
  const v = mg.view, width = +$("mg-plot").getBoundingClientRect().width || MG_WIDTH, sc = mg.scale, at = (f) => sc.toPos(f.t);
  const marks = mt.data.events.map((e) => {
    const m = meterMark(e, mgItem);
    return m && { ...m, t: at(e), at: e.t, gain: e.kind === "level" ? meterLevelGain(e, mg.bases) : null };
  }).filter(Boolean);
  const kept = marksShown(marks, v.from, v.to, width, ICON_GAP, (m) => METER_MARK_RANKS[m.kind]);
  const plot = meterSpellPlot() || MG_DPS, charts = plot.charts(v, at), shown = inStretch(mg.series, v, at);
  const common = {
    width, view: v,
    scale: sc.kind === "time" ? timeScale(v.from, v.to, width) : { ticks: [] },
    sessions: sc.sessions.map((s) => ({ from: s.at, to: s.at + s.to - s.from, label: s.key || pvWhen(s.from),
      title: mgW(s.key ? "band.dungeon.tip" : "band.tip", { from: pvWhen(s.from), to: pvWhen(s.to), n: s.n, dungeon: s.key }) })),
    breaks: sc.breaks,
    marks: kept.map((m) => ({ t: m.t, icon: MG_ICONS[m.kind], ring: MG_RINGS[m.kind], title: mgMarkWords(m) })),
    lanes: mgLanes(),
  };
  $("mg-draw").innerHTML = charts.map((c, i) => `${c.caption ? `<p class="mg-cap">${esc(c.caption)}</p>` : ""}${
    timeChartSvg({ ...common, ...c, values: { label: num, ...c.values }, bare: i < charts.length - 1 })}`).join("");
  const one = mgSame(mg.recent, mg.whole);
  const key = (attr, k, on, off = false) => `<button class="key small" ${attr}="${k}" aria-pressed="${on}" title="${
    esc(mgW(`${k}.tip`, { days: METER_RECENT_DAYS, n: METER_RECENT_FIGHTS }))}"${off ? " disabled" : ""}>${esc(mgW(k))}</button>`;
  const dps = plot === MG_DPS;
  $("mg-keys").innerHTML = `<span class="mg-title">${esc(plot.title())}</span>${key("data-mg", "recent", !one && mgSame(v, mg.recent), one)}${
    key("data-mg", "whole", !one && mgSame(v, mg.whole), one)}${key("data-mg-way", "session", mg.way === "session")}${key("data-mg-way", "time", mg.way === "time")}${
    key("data-mg-norm", "norm", dps && mg.norm, !dps)}${key("data-mg-view", "spells", mt.view === "spells")}`;
  $("mg-note").hidden = !meterUndated(shown);
  const norm = dps ? mgNormNote(shown) : "";
  $("mg-norm-note").innerHTML = esc(norm);
  $("mg-norm-note").hidden = !norm;
  askMeterItems(mt.data.events);
  emit("meterdrawn");
}

function showMeterStretch(view, follow = mgSame(view, mg.whole) ? "whole" : null) {
  mg.view = view;
  mg.follow = follow;
  drawMeterGraph();
}

const meterAxis = zoomAxis({
  axis: () => $("mg-plot"),
  box: () => $("mg-pick"),
  view: () => mg.view,
  whole: () => (mt.open && !mt.fight ? mg.whole : null),
  show: showMeterStretch,
  least: METER_ZOOM_LEAST,
  pickLeast: METER_PICK_LEAST,
  click: (t, e) => {
    const dot = e.target?.closest?.("[data-mg-fight]");
    const fight = dot && mt.data.fights.find((f) => String(f.t) === dot.dataset.mgFight);
    if (fight) openMeterFight(fight);
  },
});

{
  const box = $("meter"), onPlot = (e) => !!e.target.closest?.("#mg-plot");
  box.addEventListener("pointerdown", (e) => { if (onPlot(e)) meterAxis.down(e); });
  box.addEventListener("wheel", (e) => { if (onPlot(e)) meterAxis.wheel(e); }, { passive: false });
  box.addEventListener("dblclick", (e) => { if (onPlot(e)) meterAxis.whole(); });
  box.addEventListener("click", (e) => {
    if (e.target.closest?.("button[data-mg-norm]")) { mg.norm = !mg.norm; drawMeterGraph(); return; }
    const b = e.target.closest?.("button[data-mg], button[data-mg-way]");
    if (!b || b.getAttribute?.("aria-pressed") === "true") return;
    const k = b.dataset.mg, way = b.dataset.mgWay;
    if (k) showMeterStretch(mg[k], k);
    if (way) { mg.way = way; drawMeterGraph(); }
  });
  addEventListener("pointermove", (e) => meterAxis.move(e));
  addEventListener("pointerup", (e) => meterAxis.up(e));
  on("window", (w) => { if (w === "meter") Object.assign(mg, { follow: "recent", data: null }); });
}
