// The Index of Azeroth. Copyright 2026 Index Case <indexofazeroth@pm.me>. PolyForm Strict 1.0.0, see LICENSE.md.
"use strict";

const CK_DAY = 86400, CK_WEEK = 7 * 86400;
const CK_GAP_MOST = 2 * CK_DAY;
const CK_GAP_TIMES = 3;
const CK_FADES = [[CK_DAY, 1], [CK_WEEK, 0.6], [Infinity, 0.3]];
const CK_OLD = CK_DAY;
const CK_RANGES = [["24h", CK_DAY], ["7d", CK_WEEK], ["30d", 30 * CK_DAY], ["90d", 90 * CK_DAY], ["all", 0]];
const CK_VIEWS = ["chart", "diagram", "table"];
const CK_STEPS = 5;
const CK_SERIES = 6;
const CK_LOOKS = 2 * CK_SERIES;
const CK_STORE = "wcc.ck.";
const CK_HATCH = 6;
const CK_LABEL_LEAST = 12;
const CK_BAR_CHAR = 7;
const CK_CAL_CELL = 20;
const CK_CAL_ROOM = 2;
const CK_SANKEY_LABEL = 150;
const CK_SANKEY_NODE = 12;
const CK_SANKEY_GAP = 8;
const CK_SANKEY_ROW = 26;
const CK_SANKEY_CHAR = 7;
const CK_CLOCK = `<svg class="ck-clock" viewBox="0 0 12 12" width="10" height="10" aria-hidden="true"><circle cx="6" cy="6" r="5"/><path d="M6 3v3.2l2.2 1.4"/></svg>`;
const CK_W = wordsOf("page.counting.kit");
const ckW = (key, fill) => fillWords(CK_W[key], fill) ?? "";


function ckStored(key) {
  try { return localStorage.getItem(CK_STORE + key); } catch { return null; }
}
function ckStore(key, value) {
  try { localStorage.setItem(CK_STORE + key, value); } catch {   }
}


function ckBroken(points) {
  const gaps = ckGaps(points.map((p) => p.t)), out = [];
  for (const p of points) {
    if (gaps.length && out.length && p.t >= gaps[0].to) out.push({ t: (gaps.shift().from + p.t) / 2, v: null });
    out.push(p);
  }
  return out;
}

function ckGapMost(times) {
  const real = times.slice(1).map((t, i) => t - times[i]).filter((s) => s > 0);
  return real.length ? Math.min(CK_GAP_MOST, CK_GAP_TIMES * median(real)) : CK_GAP_MOST;
}

function ckGaps(times) {
  const most = ckGapMost(times), out = [];
  times.slice(1).forEach((t, i) => { if (t - times[i] > most) out.push({ from: times[i], to: t }); });
  return out;
}

function ckEmpty(times, view) {
  const inside = times.filter((t) => t >= view.from && t <= view.to);
  if (!inside.length) return [{ from: view.from, to: view.to }];
  const most = ckGapMost(times), first = inside[0], last = inside[inside.length - 1];
  const out = ckGaps(times).map((g) => ({ from: Math.max(view.from, g.from), to: Math.min(view.to, g.to) })).filter((g) => g.to > g.from);
  if (first - view.from > most && !times.some((t) => t < view.from)) out.unshift({ from: view.from, to: first });
  if (view.to - last > most && !times.some((t) => t > view.to)) out.push({ from: last, to: view.to });
  return out;
}

function ckHatchSvg(spans, view, w, top, high, id, drawn = null) {
  const boxes = spans.map((s) => {
    const a = Math.max(0, chartX(s.from, view, w)), b = Math.min(w, chartX(s.to, view, w));
    if (b > a) drawn?.add("hatch");
    return b > a ? `<rect class="ck-hatch" x="${a.toFixed(1)}" y="${top}" width="${(b - a).toFixed(1)}" height="${high}" fill="url(#ck-hatch-${id})"/>` : "";
  }).join("");
  return `<defs><pattern id="ck-hatch-${id}" patternUnits="userSpaceOnUse" width="${CK_HATCH}" height="${CK_HATCH}" patternTransform="rotate(45)">
    <line class="ck-hatch-line" x1="0" y1="0" x2="0" y2="${CK_HATCH}"/></pattern></defs>${boxes}`;
}

const ckFade = (age) => CK_FADES.find(([below]) => age < below)[1];


function ckAgeText(s) {
  if (s < 3600) return ckW("age.min", { n: Math.max(1, Math.round(s / 60)) });
  if (s < 2 * CK_DAY) return ckW("age.h", { n: Math.round(s / 3600) });
  return ckW("age.d", { n: Math.round(s / CK_DAY) });
}
function ckAgeTag(t, now = Date.now() / 1000) {
  const old = now - t > CK_OLD;
  return `<span class="ck-age${old ? " old" : ""}" title="${esc(ckW("age.tip", { ago: ago(t, now) }))}">${old ? CK_CLOCK : ""}${esc(ckAgeText(now - t))}</span>`;
}

function ckGold(copper, tight = false) {
  const g = Math.abs(copper) / 10000, sign = copper < 0 ? "&minus;" : "";
  if (!tight || g < 1) return `${sign}${money(Math.abs(copper))}`;
  return `${sign}${coinPicture(g >= 1000 ? `${(g / 1000).toFixed(1)}k` : num(g), "g")}`;
}

function ckRepostsHtml(r) {
  if (!r || (!r.reposts && !r.lost)) return "";
  const tip = [r.reposts ? wordCount("page.counting.kit.reposts.tip", r.reposts, { n: num(r.reposts) }) : "",
    r.lost ? ckW("reposts.lost.tip", { lost: moneyText(r.lost) }) : "", r.reposts >= 2 ? ckW("reposts.many.tip") : ""].filter(Boolean).join(" ");
  return `<span title="${esc(tip)}">${num(r.reposts || 0)} <small class="muted">${ckGold(r.lost || 0)}</small></span>`;
}
const ckRepostsColumn = (of) => ({ key: "reposts", label: ckW("col.reposts"), tip: ckW("col.reposts.tip"), num: true,
  value: (r) => (of(r) || {}).lost || 0, cell: (r) => ckRepostsHtml(of(r)) });

const ckConfidenceWord = (steps) => ckW(steps >= 4 ? "confidence.high" : steps >= 2 ? "confidence.medium" : "confidence.low");
function ckConfidence(c, now = Date.now() / 1000) {
  const lines = [c.scans != null && ckW("confidence.scans", { n: num(c.scans) }), c.newest != null && ckW("confidence.newest", { ago: ago(c.newest, now) }),
    c.gap != null && ckW("confidence.gap", { span: roughSpan(c.gap) }), c.sales != null && ckW("confidence.sales", { n: num(c.sales) })].filter(Boolean);
  const steps = Math.max(0, Math.min(CK_STEPS, Math.round(c.steps)));
  const bar = Array.from({ length: CK_STEPS }, (_, i) => `<i${i < steps ? ' class="on"' : ""}></i>`).join("");
  return `<span class="ck-conf"${lines.length ? ` title="${esc(lines.join("\n"))}"` : ""}><span class="ck-conf-bar" aria-hidden="true">${bar}</span>${esc(ckConfidenceWord(steps))}</span>`;
}

function ckCard(c, now = Date.now() / 1000) {
  return [c.value, c.t != null && ckW("card.age", { span: ckAgeText(now - c.t) }), c.count != null && ckW("card.count", { n: num(c.count) }),
    c.steps != null && ckW("card.confidence", { word: ckConfidenceWord(c.steps) })].filter(Boolean).join("\n");
}


function ckViewOf(panel, views) {
  const kept = ckStored(`view.${panel}`);
  return views.includes(kept) ? kept : views[0];
}
function ckSwitchHtml(panel, views, shown) {
  return `<span class="ck-switch" role="group">${CK_VIEWS.filter((v) => views.includes(v)).map((v) => `<button type="button" class="key small"
    data-ck-panel="${esc(panel)}" data-ck-view="${v}" aria-pressed="${v === shown}" title="${esc(ckW(`view.${v}.tip`))}">${esc(ckW(`view.${v}`))}</button>`).join("")}</span>`;
}
function ckSwitchClick(e) {
  const b = e.target.closest?.("button[data-ck-view]");
  if (!b) return null;
  ckStore(`view.${b.dataset.ckPanel}`, b.dataset.ckView);
  return { panel: b.dataset.ckPanel, view: b.dataset.ckView };
}

function ckRangeOf() {
  const kept = ckStored("range");
  return CK_RANGES.some(([k]) => k === kept) ? kept : "30d";
}
function ckRangeHtml(range, picked = false) {
  const keys = CK_RANGES.map(([k]) => `<button type="button" class="key small" data-ck-range="${k}" aria-pressed="${!picked && k === range}"
    title="${esc(ckW("range.tip"))}">${esc(ckW(`range.${k}`))}</button>`).join("");
  const pick = picked ? `<span class="ck-picked" title="${esc(ckW("range.picked.tip"))}">${esc(ckW("range.picked"))}</span>` : "";
  return `<span class="ck-range" role="group">${keys}${pick}</span>`;
}
function ckRangeClick(e) {
  const b = e.target.closest?.("button[data-ck-range]");
  if (!b) return null;
  ckStore("range", b.dataset.ckRange);
  return b.dataset.ckRange;
}
function ckRangeView(range, whole, now = Date.now() / 1000) {
  const secs = (CK_RANGES.find(([k]) => k === range) || CK_RANGES[1])[1];
  if (!secs && whole) return { from: Math.min(whole.from, now), to: Math.max(whole.to, now) };
  return { from: now - (secs || 30 * CK_DAY), to: now };
}

function ckDragRange(host, picked) {
  let on = null;
  const view = () => ({ from: +on.dataset.from, to: +on.dataset.to });
  const axis = zoomAxis({ axis: () => on, box: () => on.querySelector(".ck-pick"), view, whole: () => (on ? view() : null),
    show: () => {}, picked, click: () => {} });
  host.addEventListener("pointerdown", (e) => {
    on = e.button === 0 ? e.target.closest?.(".ck-drag") : null;
    if (on) axis.down(e);
  });
  addEventListener("pointermove", (e) => { if (on) axis.move(e); });
  addEventListener("pointerup", (e) => { if (on) axis.up(e); });
}


function ckSeriesOf(keys) {
  const out = {};
  for (const k of keys) if (!(k in out)) out[k] = (Object.keys(out).length % CK_LOOKS) + 1;
  return out;
}
const ckStriped = (n) => typeof n === "number" && n > CK_SERIES;


function ckFit(s, px, char = TC_LABEL_CHAR) {
  const room = Math.max(1, Math.floor(px / char));
  return s.length > room ? [`${s.slice(0, Math.max(1, room - 1))}…`, ` title="${esc(s)}"`] : [s, ""];
}
const ckWhole = (name, px) => !!name && !ckFit(name, px - 6, CK_BAR_CHAR)[1];


function ckLookHtml(look) {
  const bare = look.replace(/^(up|down)-/, ""), flag = bare.match(/^mark-(.+)$/), tone = bare.match(/^(tone|dim)-(.+)$/);
  if (flag) return `<i class="ck-look ck-look-mark">${esc(flag[1])}</i>`;
  if (tone) return `<i class="ck-look ck-look-tone ck-tone-${esc(tone[2])}${tone[1] === "dim" ? " ck-look-dim" : ""}"></i>`;
  if (/^s\d+$|^stotal$/.test(bare)) return `<i class="ck-look ck-look-fill ck-${bare}${ckStriped(+bare.slice(1)) ? " ck-look-striped" : ""}"></i>`;
  return `<i class="ck-look ck-look-${esc(bare)}"></i>`;
}

function ckLegendHtml(legend, drawn) {
  if (!legend) return "";
  const rows = [{ group: null, items: [] }];
  for (const e of legend) {
    if (e.group != null) rows.push({ group: e.group, items: [] });
    else if (e.name && drawn.has(e.look)) rows[rows.length - 1].items.push(e);
  }
  return rows.filter((r) => r.items.length).map((r) => `<div class="ck-key">${r.group ? `<span class="ck-key-group">${esc(r.group)}</span>` : ""}${
    r.items.map((e) => `<span class="ck-key-item"${e.tip ? ` title="${esc(e.tip)}"` : ""}>${ckLookHtml(e.look)}${esc(e.name)}</span>`).join("")}</div>`).join("");
}

const ckSeriesLegend = (series) => Object.entries(series).map(([name, n]) => ({ look: `s${n}`, name }));
const ckNoScanLegend = () => ({ look: "hatch", name: ckW("legend.noscan"), tip: ckW("legend.noscan.tip") });

function ckBarsSvg(c) {
  const { width: w, high: h, view, values } = c, top = TC_TOP, foot = top + h, drawn = new Set();
  const x = (t) => chartX(t, view, w).toFixed(1), y = (v) => (top + chartY(v, values.top, h)).toFixed(1);
  const bars = c.bins.map((b) => {
    const a = Math.max(0, chartX(b.from, view, w)), z = Math.min(w, chartX(b.to, view, w)), span = Math.max(1, z - a - 1);
    if (z <= a) return "";
    let base = 0;
    return b.parts.map((p) => {
      const y0 = top + chartY(base, values.top, h), y1 = top + chartY(base + p.v, values.top, h), high = y0 - y1;
      base += p.v;
      drawn.add(`s${p.series}`);
      const label = high >= CK_LABEL_LEAST && ckWhole(p.name, span)
        ? `<text class="ck-bar-label" x="${(a + 3).toFixed(1)}" y="${(y0 - 3).toFixed(1)}">${esc(p.name)}</text>` : "";
      return ckPartSvg(p, a, y1, span, high, c.id, label);
    }).join("");
  }).join("");
  const height = foot + 2 + TC_SCALE, hatch = c.hatch ? ckHatchSvg(c.hatch, view, w, top, h, c.id, drawn) : "";
  return `<svg class="tc ck-bars" width="${w}" height="${height}" viewBox="0 0 ${w} ${height}">
    <defs><clipPath id="ck-clip-${c.id}"><rect x="0" y="${top}" width="${w}" height="${h}"/></clipPath>${ckFillDefs(c.id)}</defs>
    <rect class="tc-plot" x="0" y="${top}" width="${w}" height="${h}"/>${tcGrid(values, y, w)}
    <g clip-path="url(#ck-clip-${c.id})">${hatch}${bars}</g>${tcScale(c.scale, x, foot + 2)}</svg>${ckLegendHtml(c.legend, drawn)}`;
}

function ckAxis(lo, hi, count = 4) {
  if (!(hi > lo)) [lo, hi] = [lo - Math.max(1, Math.abs(lo) * 0.1), hi + Math.max(1, Math.abs(hi) * 0.1)];
  const raw = (hi - lo) / count, mag = Math.pow(10, Math.floor(Math.log10(raw)));
  const step = [...TC_STEPS, 10].map((s) => s * mag).find((s) => s >= raw - 1e-9);
  const bottom = lo >= 0 ? Math.max(0, Math.floor(lo / step + 1e-9) * step) : Math.floor(lo / step + 1e-9) * step;
  const ticks = [];
  for (let v = bottom; v < hi + step - 1e-9; v += step) ticks.push(Math.round(v * 1e6) / 1e6);
  return { bottom: ticks[0], top: ticks[ticks.length - 1], ticks };
}

function ckPlotSvg(c) {
  const { width: w, high: h, x: ax, y: ay } = c, top = TC_TOP, foot = top + h, drawn = new Set();
  const x = (v) => chartX(v, ax, w).toFixed(1);
  const y = (v) => (top + h - Math.min(1, Math.max(0, (v - ay.bottom) / Math.max(1e-9, ay.top - ay.bottom))) * h).toFixed(1);
  const opacity = (f) => (f == null ? "" : ` opacity="${f}"`);
  const seen = (look, markup) => { if (markup) drawn.add(look); return markup; };
  const bars = (c.bars || []).map((b) => {
    const a = Math.max(0, chartX(b.x0, ax, w)), z = Math.min(w, chartX(b.x1, ax, w)), y0 = +y(b.v0), y1 = +y(b.v1);
    return seen(`s${b.series || 1}`, z > a ? ckPartSvg({ series: b.series || 1, title: b.title }, a, Math.min(y0, y1), Math.max(1, z - a), Math.max(1, Math.abs(y0 - y1)), c.id) : "");
  }).join("");
  const runs = (points, ok) => points.reduce((all, p) => {
    if (!ok(p)) all.push([]);
    else all[all.length - 1].push(p);
    return all;
  }, [[]]).filter((r) => r.length);
  const bands = (c.bands || []).map((b) => runs(b.points, (p) => p.lo != null).map((r) => {
    const d = `M${r.map((p) => `${x(p.x)},${y(p.hi)}`).join("L")}L${[...r].reverse().map((p) => `${x(p.x)},${y(p.lo)}`).join("L")}Z`;
    return seen("band", `<path class="ck-band" d="${d}"${opacity(b.fade)}${b.title ? ` title="${esc(b.title)}"` : ""}/>`);
  }).join("")).join("");
  const rules = (c.rules || []).map((r) => seen("rule", `<g class="ck-rule" title="${esc(r.title || "")}"><line x1="0" x2="${w}" y1="${y(r.v)}" y2="${y(r.v)}"/>${
    r.label ? `<text x="${w - 3}" y="${(+y(r.v) - 3).toFixed(1)}">${esc(r.label)}</text>` : ""}</g>`)).join("");
  const cuts = (c.cuts || []).map((r) => seen("cut", `<g class="ck-cut" title="${esc(r.title || "")}"><line x1="${x(r.x)}" x2="${x(r.x)}" y1="${top}" y2="${foot}"/>${
    r.label ? `<text x="${(+x(r.x) + 3).toFixed(1)}" y="${top + 11}">${esc(r.label)}</text>` : ""}</g>`)).join("");
  const lines = (c.lines || []).map((l) => runs(l.points, (p) => p.v != null).map((r) => {
    const d = r.map((p, i) => (i ? `${l.step ? `L${x(p.x)},${y(r[i - 1].v)}` : ""}L${x(p.x)},${y(p.v)}` : `M${x(p.x)},${y(p.v)}`)).join("");
    return seen(l.kind ? `line-${l.kind}` : "line", `<path class="ck-line${l.kind ? ` ${l.kind}` : ""}" d="${d}"${opacity(l.fade)}/>`);
  }).join("")).join("");
  const dots = (c.dots || []).map((d) => seen(d.hollow ? "hollow" : "dot",
    `<circle class="ck-dot${d.hollow ? " hollow" : ""}" cx="${x(d.x)}" cy="${y(d.v)}" r="${TC_DOT}" title="${esc(d.title || "")}"${opacity(d.fade)}/>`)).join("");
  const marks = (c.marks || []).map((m) => seen(`mark-${m.label}`, `<g class="ck-mark" title="${esc(m.title || "")}"><line x1="${x(m.x)}" x2="${x(m.x)}" y1="${top}" y2="${foot}"/>
    <rect x="${(+x(m.x) - 7).toFixed(1)}" y="${top}" width="14" height="13"/><text x="${x(m.x)}" y="${top + 10}">${esc(m.label)}</text></g>`)).join("");
  const height = foot + 2 + TC_SCALE, hatch = c.hatch ? ckHatchSvg(c.hatch, ax, w, top, h, c.id, drawn) : "";
  return `<svg class="tc ck-plot" width="${w}" height="${height}" viewBox="0 0 ${w} ${height}">
    <defs><clipPath id="ck-clip-${c.id}"><rect x="0" y="${top}" width="${w}" height="${h}"/></clipPath>${ckFillDefs(c.id)}</defs>
    <rect class="tc-plot" x="0" y="${top}" width="${w}" height="${h}"/>${tcGrid({ ...ay, ticks: ay.ticks }, y, w)}
    <g clip-path="url(#ck-clip-${c.id})">${hatch}${bars}${bands}${rules}${cuts}${lines}${dots}${marks}</g>${tcScale({ ticks: ax.ticks }, x, foot + 2)}</svg>${
    ckLegendHtml(c.legend, drawn)}`;
}

function ckAcross(from, to, label, count = 6) {
  const a = ckAxis(from, to, count);
  return a.ticks.filter((v) => v >= from - 1e-9 && v <= to + 1e-9).map((v) => ({ t: v, label: label(v), major: true }));
}

const ckTipKey = (key) => (String(key ?? "").endsWith(":pooled") ? baseItem(key) : String(key ?? ""));
function ckItemHtml(it, o = {}) {
  const tip = ckTipKey(it.key), q = it.q != null ? [`q${it.q}`] : [], tag = o.open ? "button" : "span";
  const icon = o.icon === false ? "" : `<img class="${["mt-ico", ...q].join(" ")}" src="/icon/${esc(it.icon || "inv_misc_questionmark")}.jpg" alt="">`;
  return `<${tag}${o.open ? ` type="button" ${o.open}` : ""} class="${["ck-item", ...q, ...(o.cls || [])].join(" ")}"${tip ? ` data-tip="${esc(tip)}"` : ""}>${
    icon}${esc(it.name || it.key || "")}</${tag}>`;
}

const ckSorts = {};
function ckTable(t) {
  const sort = ckSorts[t.id] || t.sort || { key: t.columns[0].key, down: true };
  const col = t.columns.find((c) => c.key === sort.key) || t.columns[0];
  const rows = [...t.rows].sort((a, b) => {
    const va = col.value(a), vb = col.value(b);
    if (va == null || vb == null) return (va == null) - (vb == null);
    return (va < vb ? -1 : va > vb ? 1 : 0) * (sort.down ? -1 : 1);
  });
  const heads = t.columns.map((c) => `<th${c.num ? ' class="num"' : ""}${c.tip ? ` title="${esc(c.tip)}"` : ""}><button type="button" class="ck-sort${
    c.key === col.key ? (sort.down ? " down" : " up") : ""}" data-ck-sort="${esc(t.id)}" data-ck-key="${esc(c.key)}" title="${esc(ckW("sort.tip"))}">${esc(c.label)}</button></th>`).join("");
  const body = rows.map((r) => `<tr${t.key ? ` data-ck-row="${esc(String(t.key(r)))}"` : ""}${t.row ? ` ${t.row(r)}` : ""}>${
    t.columns.map((c) => `<td${c.num ? ' class="num"' : ""}>${c.cell(r)}</td>`).join("")}</tr>`).join("");
  const keyed = t.key ? ` data-ck-table="${esc(t.id)}" data-ck-order="${esc(`${col.key} ${sort.down ? "down" : "up"}`)}"` : "";
  return `<table class="mt-table ck-table"${keyed}><thead><tr>${heads}</tr></thead><tbody>${body}</tbody></table>`;
}


const CK_MOVE_MS = 330;
const CK_FLASH_MS = 500;
let ckRowsPlaying = [];

function ckRowsState(view) {
  const v = view.getBoundingClientRect(), out = { top: v.top, bottom: v.bottom, tables: {} };
  for (const table of view.querySelectorAll("table[data-ck-table]")) {
    const box = table.getBoundingClientRect(), rows = {};
    for (const tr of table.querySelectorAll("tr[data-ck-row]")) {
      const r = tr.getBoundingClientRect(), cells = [...tr.cells], on = r.bottom > v.top && r.top < v.bottom;
      rows[tr.dataset.ckRow] = { el: tr, top: r.top, bottom: r.bottom, left: r.left, width: r.width, cells: cells.map((td) => td.textContent),
        widths: on ? cells.map((td) => td.getBoundingClientRect().width) : null };
    }
    out.tables[table.dataset.ckTable] = { order: table.dataset.ckOrder, el: table, top: box.top, left: box.left, offTop: table.offsetTop,
      offLeft: table.offsetLeft, rows };
  }
  return out;
}

function ckRowsRead(view) {
  for (const a of ckRowsPlaying) a.finish();
  ckRowsPlaying = [];
  return ckRowsState(view);
}

function ckRowsPlan(was, now, still) {
  const plan = { moves: [], flashes: [], gone: [], fresh: [] };
  if (still || !was) return plan;
  const on = (r, v) => r.bottom > v.top && r.top < v.bottom;
  for (const [id, t] of Object.entries(now.tables)) {
    const before = was.tables[id];
    if (!before || before.order !== t.order) continue;
    for (const [key, r] of Object.entries(t.rows)) {
      const o = before.rows[key];
      if (!o) {
        if (on(r, now)) plan.fresh.push([id, key]);
        continue;
      }
      if (!on(r, now) && !on(o, was)) continue;
      const dy = o.top - r.top;
      if (Math.abs(dy) >= 1) plan.moves.push([id, key, dy]);
      const changed = r.cells.flatMap((c, i) => (c !== o.cells[i] ? [i] : []));
      if (changed.length) plan.flashes.push([id, key, changed]);
    }
    for (const [key, o] of Object.entries(before.rows)) if (!(key in t.rows) && on(o, was)) plan.gone.push([id, key]);
  }
  return plan;
}

function ckRowsPlay(view, was) {
  const now = ckRowsState(view), plan = ckRowsPlan(was, now, lessMotion());
  const row = (id, key) => now.tables[id].rows[key].el;
  for (const [id, key, dy] of plan.moves) {
    const tr = row(id, key), slide = tr.animate([{ transform: `translateY(${dy}px)` }, { transform: "none" }], { duration: CK_MOVE_MS, easing: "ease-out" });
    tr.classList.add("ck-moving");
    slide.onfinish = () => tr.classList.remove("ck-moving");
    ckRowsPlaying.push(slide);
  }
  for (const [id, key, cells] of plan.flashes) for (const i of cells) row(id, key).cells[i]?.classList.add("ck-flash");
  for (const [id, key] of plan.fresh) {
    ckRowsPlaying.push(row(id, key).animate([{ opacity: 0 }, { opacity: 1 }], { duration: CK_FLASH_MS, delay: CK_MOVE_MS, fill: "backwards", easing: "ease-out" }));
  }
  for (const [id, key] of plan.gone) ckRowsPlaying.push(ckRowGhost(now.tables[id], was.tables[id].rows[key]));
}

function ckRowGhost(t, o) {
  const g = document.createElement("table"), body = document.createElement("tbody");
  g.className = `${t.el.className} ck-ghost`;
  [...o.el.cells].forEach((td, i) => { td.style.width = `${o.widths[i]}px`; });
  body.append(o.el);
  g.append(body);
  Object.assign(g.style, { left: `${t.offLeft + o.left - t.left}px`, top: `${t.offTop + o.top - t.top}px`, width: `${o.width}px` });
  t.el.after(g);
  const fade = g.animate([{ opacity: 1 }, { opacity: 0 }], { duration: CK_FLASH_MS, easing: "ease-in" });
  fade.onfinish = () => g.remove();
  return { finish: () => g.remove() };
}
function ckSortClick(e) {
  const b = e.target.closest?.("button[data-ck-sort]");
  if (!b) return false;
  const id = b.dataset.ckSort, key = b.dataset.ckKey, was = ckSorts[id];
  ckSorts[id] = { key, down: was?.key === key ? !was.down : true };
  return true;
}


function ckBothWays(up, down) {
  const step = valueTicks(Math.max(up, down, 1), 3).ticks[1];
  const top = Math.max(step, Math.ceil(up / step - 1e-9) * step), foot = Math.ceil(down / step - 1e-9) * step;
  const ticks = [];
  for (let v = -foot; v <= top + 1e-9; v += step) ticks.push(Math.round(v));
  return { up: top, down: foot, step, ticks };
}

const ckFillDefs = (id) => `<pattern id="ck-fill-${id}" patternUnits="userSpaceOnUse" width="${CK_HATCH}" height="${CK_HATCH}" patternTransform="rotate(45)">
  <line class="ck-fill-line" x1="0" y1="0" x2="0" y2="${CK_HATCH}"/></pattern>`;
const ckPartSvg = (p, x, y, w, h, id, inner = "") => {
  const box = `x="${x.toFixed(1)}" y="${y.toFixed(1)}" width="${w.toFixed(1)}" height="${Math.max(0, h).toFixed(1)}"`;
  const stripes = p.unknown || ckStriped(p.series) ? `<rect class="ck-fill-over" ${box} style="fill:url(#ck-fill-${id});fill-opacity:1"/>` : "";
  return `<g class="ck-bar ${p.unknown ? "ck-unknown" : `ck-s${p.series}`}" title="${esc(p.title || "")}"><rect ${box}/>${stripes}${inner}</g>`;
};

function ckSignedBarsSvg(c) {
  const { width: w, high: h, view } = c, top = TC_TOP, foot = top + h, drawn = new Set();
  const sum = (parts) => parts.reduce((s, p) => s + p.v, 0);
  const axis = ckBothWays(Math.max(0, ...c.bins.map((b) => sum(b.up))), Math.max(0, ...c.bins.map((b) => sum(b.down))));
  const y = (v) => top + (axis.up - v) / Math.max(1, axis.up + axis.down) * h;
  const grid = tcGrid({ ticks: axis.ticks, label: c.label }, (v) => y(v).toFixed(1), w);
  const look = (side, p) => drawn.add(`${side}-${p.unknown ? "unknown" : `s${p.series}`}`);
  const bars = c.bins.map((b) => {
    const a = Math.max(0, chartX(b.from, view, w)), z = Math.min(w, chartX(b.to, view, w)), span = Math.max(1, z - a - 1);
    if (z <= a) return "";
    let up = 0, down = 0;
    b.up.forEach((p) => look("up", p));
    b.down.forEach((p) => look("down", p));
    return b.up.map((p) => ckPartSvg(p, a, y(up += p.v), span, y(up - p.v) - y(up), c.id)).join("")
      + b.down.map((p) => ckPartSvg(p, a, y(-down), span, y(-(down += p.v)) - y(-(down - p.v)), c.id)).join("");
  }).join("");
  const pieces = [[]];
  for (const p of c.line) {
    if (p.v == null) pieces.push([]);
    else pieces[pieces.length - 1].push(`${chartX(p.t, view, w).toFixed(1)},${y(p.v).toFixed(1)}`);
  }
  const line = pieces.filter((p) => p.length > 1).map((p) => `M${p.join("L")}`).join("");
  if (line) drawn.add("net");
  const height = foot + 2 + TC_SCALE, hatch = c.hatch ? ckHatchSvg(c.hatch, view, w, top, h, c.id, drawn) : "";
  return `<svg class="tc ck-bars" width="${w}" height="${height}" viewBox="0 0 ${w} ${height}">
    <defs><clipPath id="ck-clip-${c.id}"><rect x="0" y="${top}" width="${w}" height="${h}"/></clipPath>${ckFillDefs(c.id)}</defs>
    <rect class="tc-plot" x="0" y="${top}" width="${w}" height="${h}"/>${grid}
    <g clip-path="url(#ck-clip-${c.id})">${hatch}${bars}<line class="ck-zero" x1="0" x2="${w}" y1="${y(0).toFixed(1)}" y2="${y(0).toFixed(1)}"/>${
  line ? `<path class="ck-net" d="${line}"/>` : ""}</g>${tcScale(c.scale, (t) => chartX(t, view, w).toFixed(1), foot + 2)}</svg>${ckLegendHtml(c.legend, drawn)}`;
}

function ckWaterfallSvg(c) {
  const { width: w, high: h } = c, top = TC_TOP + 14, foot = top + h, n = Math.max(1, c.steps.length);
  let run = 0;
  const laid = c.steps.map((s) => {
    const from = s.total ? 0 : run, to = s.total ? s.v : run + s.v;
    run = to;
    return { ...s, lo: Math.min(from, to), hi: Math.max(from, to) };
  });
  const values = { ...valueTicks(Math.max(1, ...laid.map((s) => s.hi)), 4), label: c.label };
  const y = (v) => top + chartY(v, values.top, h);
  const slot = w / n, bar = Math.max(4, slot * 0.6);
  const bars = laid.map((s, i) => {
    const x = i * slot + (slot - bar) / 2, mid = (i + 0.5) * slot;
    const shown = s.total ? c.label(s.v) : `${s.v < 0 ? "−" : "+"}${c.label(Math.abs(s.v))}`, [name, whole] = ckFit(s.name, slot - 6);
    return `${ckPartSvg({ ...s, series: s.total ? "total" : s.series }, x, y(s.hi), bar, y(s.lo) - y(s.hi), c.id)}
      <text class="ck-wf-value" x="${mid.toFixed(1)}" y="${(y(s.hi) - 4).toFixed(1)}">${esc(shown)}</text>
      <text class="ck-wf-name" x="${mid.toFixed(1)}" y="${foot + 14}"${whole}>${esc(name)}</text>`;
  }).join("");
  const height = foot + 22;
  return `<svg class="tc ck-bars ck-wf" width="${w}" height="${height}" viewBox="0 0 ${w} ${height}"><defs>${ckFillDefs(c.id)}</defs>
    <rect class="tc-plot" x="0" y="${top}" width="${w}" height="${h}"/>${tcGrid(values, (v) => y(v).toFixed(1), w)}${bars}</svg>`;
}

function ckSankeySvg(c) {
  const room = CK_SANKEY_LABEL, node = CK_SANKEY_NODE, gap = CK_SANKEY_GAP, top = 4, h = c.high - 2 * top;
  const total = Math.max(1, c.left.reduce((s, x) => s + x.v, 0), c.right.reduce((s, x) => s + x.v, 0));
  const roomOf = (nodes, k) => nodes.reduce((s, n) => s + Math.max(n.v * k, CK_SANKEY_ROW), 0) + gap * Math.max(0, nodes.length - 1);
  let k = h / total;
  for (let i = 0; i < 4; i++) k *= Math.min(1, h / Math.max(1, roomOf(c.left, k), roomOf(c.right, k)));
  const x0 = room, xm = (c.width - node) / 2, x1 = c.width - room - node;
  const mid = { y: top + (h - total * k) / 2, h: total * k };
  const side = (nodes, x, toMiddle) => {
    let y = top, into = mid.y;
    return nodes.map((n) => {
      const hh = Math.max(1, n.v * k), at = y, m = into, line = at + Math.max(hh, CK_SANKEY_ROW) / 2;
      y += Math.max(hh, CK_SANKEY_ROW) + gap;
      into += n.v * k;
      const ax = toMiddle ? x + node : xm + node, bx = toMiddle ? xm : x, cx = (ax + bx) / 2;
      const [ya, yb] = toMiddle ? [at, m] : [m, at];
      const band = `M${ax},${ya.toFixed(1)}C${cx},${ya.toFixed(1)} ${cx},${yb.toFixed(1)} ${bx},${yb.toFixed(1)}L${bx},${(yb + hh).toFixed(1)}C${cx},${(yb + hh).toFixed(1)} ${cx},${(ya + hh).toFixed(1)} ${ax},${(ya + hh).toFixed(1)}Z`;
      const tx = toMiddle ? x - 6 : x + node + 6, anchor = toMiddle ? "end" : "start", [name, whole] = ckFit(n.name, room - 10, CK_SANKEY_CHAR);
      return `<g class="ck-flow ${n.unknown ? "ck-unknown" : `ck-s${n.series}`}" title="${esc(n.title || "")}"><path d="${band}"/>${
        n.unknown ? `<path class="ck-flow-hatch" d="${band}" style="fill:url(#ck-fill-${c.id})"/>` : ""}${ckPartSvg(n, x, at, node, hh, c.id)}
        <text class="ck-flow-name" x="${tx}" y="${(line - 1).toFixed(1)}" text-anchor="${anchor}"${whole}>${esc(name)}</text>
        <text class="ck-flow-value" x="${tx}" y="${(line + 11).toFixed(1)}" text-anchor="${anchor}">${esc(c.label(n.v))}</text></g>`;
    }).join("");
  };
  const middle = `<g class="ck-bar ck-stotal"><rect x="${xm}" y="${mid.y.toFixed(1)}" width="${node}" height="${mid.h.toFixed(1)}"/></g>
    <text class="ck-flow-name" x="${xm + node / 2}" y="${Math.max(10, mid.y - 4).toFixed(1)}" text-anchor="middle">${esc(c.middle)}</text>`;
  return `<svg class="ck-sankey" width="${c.width}" height="${c.high}" viewBox="0 0 ${c.width} ${c.high}"><defs>${ckFillDefs(c.id)}</defs>${
    side(c.left, x0, true)}${side(c.right, x1, false)}${middle}</svg>`;
}

function ckDiverging(v, most) {
  const share = Math.round(25 + 75 * Math.min(1, Math.abs(v) / Math.max(1, most)));
  return v ? `background:color-mix(in srgb, var(${v > 0 ? "--ck-gain" : "--ck-loss"}) ${share}%, var(--groove))` : "";
}

function ckCalendarHtml(days, cell, legend = null) {
  if (!days.length) return "";
  const got = days.map(cell), most = Math.max(1, ...got.filter((c) => !c.empty).map((c) => Math.abs(c.v || 0))), drawn = new Set();
  for (const c of got) {
    if (c.empty) drawn.add("hatch");
    else if (c.v) drawn.add(c.v > 0 ? "heat-gain" : "heat-loss");
  }
  const date = (s) => new Date(`${s}T12:00:00`), first = date(days[0].day);
  const lead = (first.getDay() + 6) % 7, cols = Math.ceil((lead + days.length) / 7);
  const cells = [], months = [];
  const starts = days.map((d, i) => [i, date(d.day)]).filter(([i, when]) => when.getDate() === 1 || i === 0)
    .map(([i, when]) => ({ col: Math.floor((lead + i) / 7), when }));
  starts.forEach((s, k) => {
    if (k === 0 && starts[1] && starts[1].col - s.col < CK_CAL_ROOM) return;
    months.push(`<span class="ck-cal-month" style="grid-column:${s.col + 2} / span ${CK_CAL_ROOM};grid-row:1">${esc(s.when.toLocaleDateString(undefined, { month: "short" }))}</span>`);
  });
  days.forEach((d, i) => {
    const at = lead + i, col = Math.floor(at / 7), c = got[i], style = c.empty ? "" : ckDiverging(c.v || 0, most);
    cells.push(`<span class="ck-cal-day${c.empty ? " ck-hatched" : ""}" style="grid-column:${col + 2};grid-row:${(at % 7) + 2};${style}" title="${esc(c.title)}"></span>`);
  });
  const names = [1, 3, 5].map((k) => `<span class="ck-cal-name" style="grid-row:${k + 1}">${esc(new Date(2026, 10, 9 + k - 1).toLocaleDateString(undefined, { weekday: "short" }))}</span>`);
  return `<div class="ck-cal" style="grid-template-columns:auto repeat(${cols}, ${CK_CAL_CELL}px)">${months.join("")}${names.join("")}${cells.join("")}</div>${
    ckLegendHtml(legend, drawn)}`;
}

function ckPanelHtml(p) {
  return `<section class="ck-panel" data-ck-panel-of="${esc(p.id)}"><div class="ck-panel-head"><img class="mt-ico" src="/icon/${esc(p.icon)}.jpg" alt="">
    <h3 class="ck-panel-title">${esc(p.title)}${p.latest ? ` <small>${esc(p.latest)}</small>` : ""}</h3>${p.extra || ""}${p.views.length > 1 ? ckSwitchHtml(p.id, p.views, p.view) : ""}</div>
    <div class="ck-panel-body">${p.body}</div></section>`;
}


const CK_TONES = { spiking: "gain2", rising: "gain", stable: "flat", falling: "loss", crashing: "loss2" };
const ckToneOf = (state) => CK_TONES[state] || "none";
const CK_TILE_TEXT = [44, 30];
const CK_HBAR = 20, CK_HBAR_LABEL = 190;

function ckSquarify(items, x, y, w, h) {
  const total = items.reduce((s, i) => s + i.v, 0);
  if (!(total > 0)) return [];
  const scale = (w * h) / total, out = [];
  let rest = items.filter((i) => i.v > 0).map((i) => ({ ...i, a: i.v * scale })), box = { x, y, w, h };
  const worst = (row, side) => {
    const s = row.reduce((t, r) => t + r.a, 0), most = Math.max(...row.map((r) => r.a)), least = Math.min(...row.map((r) => r.a));
    return Math.max((side * side * most) / (s * s), (s * s) / (side * side * least));
  };
  while (rest.length) {
    const side = Math.min(box.w, box.h), row = [rest[0]];
    let i = 1;
    while (i < rest.length && worst([...row, rest[i]], side) <= worst(row, side)) row.push(rest[i++]);
    rest = rest.slice(i);
    const s = row.reduce((t, r) => t + r.a, 0), across = box.w >= box.h;
    const thick = across ? s / box.h : s / box.w;
    let at = across ? box.y : box.x;
    for (const r of row) {
      const len = r.a / thick;
      out.push(across ? { ...r, x: box.x, y: at, w: thick, h: len } : { ...r, x: at, y: box.y, w: len, h: thick });
      at += len;
    }
    box = across ? { x: box.x + thick, y: box.y, w: box.w - thick, h: box.h } : { x: box.x, y: box.y + thick, w: box.w, h: box.h - thick };
  }
  return out;
}

function ckTreemapSvg(c) {
  const laid = ckSquarify([...c.tiles].sort((a, b) => b.v - a.v), 0, 0, c.width, c.high), drawn = new Set();
  const tiles = laid.map((t) => {
    drawn.add(`${t.dim ? "dim" : "tone"}-${t.tone}`);
    const fits = t.w >= CK_TILE_TEXT[0] && t.h >= CK_TILE_TEXT[1], cut = (s) => ckFit(s, t.w - 8)[0];
    const text = fits ? `<text class="ck-tile-name"${t.tip != null ? ` data-tip="${esc(t.tip)}"` : ""} x="${(t.x + 4).toFixed(1)}" y="${(t.y + 14).toFixed(1)}">${esc(cut(t.name))}</text>${
      t.word ? `<text class="ck-tile-word" x="${(t.x + 4).toFixed(1)}" y="${(t.y + 27).toFixed(1)}">${esc(cut(t.word))}</text>` : ""}` : "";
    return `<g class="ck-tile ck-tone-${t.tone}"${t.key != null ? ` data-ck-tile="${esc(t.key)}"` : ""} title="${esc(t.title || "")}">
      <rect x="${t.x.toFixed(1)}" y="${t.y.toFixed(1)}" width="${Math.max(0.5, t.w - 1).toFixed(1)}" height="${Math.max(0.5, t.h - 1).toFixed(1)}"/>${
      t.dim ? `<rect class="ck-hatch" x="${t.x.toFixed(1)}" y="${t.y.toFixed(1)}" width="${Math.max(0.5, t.w - 1).toFixed(1)}" height="${Math.max(0.5, t.h - 1).toFixed(1)}" fill="url(#ck-hatch-${c.id})"/>` : ""}${text}</g>`;
  }).join("");
  return `<svg class="ck-treemap" width="${c.width}" height="${c.high}" viewBox="0 0 ${c.width} ${c.high}">${ckHatchSvg([], { from: 0, to: 1 }, 1, 0, 0, c.id)}${tiles}</svg>${
    ckLegendHtml(c.legend, drawn)}`;
}

function ckHBarsSvg(c) {
  const plot = Math.max(60, c.width - CK_HBAR_LABEL - 70), most = Math.max(1e-9, ...c.rows.map((r) => Math.max(Math.abs(r.v), Math.abs(r.lo ?? 0), Math.abs(r.hi ?? 0))));
  const zero = CK_HBAR_LABEL + (c.two ? plot / 2 : 0), unit = (c.two ? plot / 2 : plot) / most, drawn = new Set();
  const rows = c.rows.map((r, i) => {
    const y = i * CK_HBAR, x0 = Math.min(zero, zero + r.v * unit), x1 = Math.max(zero, zero + r.v * unit);
    drawn.add(`tone-${r.tone || "flat"}`);
    if (r.lo != null && r.hi != null) drawn.add("whisker");
    const whisker = r.lo != null && r.hi != null ? `<line class="ck-whisker" x1="${(zero + r.lo * unit).toFixed(1)}" x2="${(zero + r.hi * unit).toFixed(1)}"
      y1="${y + CK_HBAR / 2}" y2="${y + CK_HBAR / 2}"/>` : "";
    const end = r.v < 0 ? Math.min(x0, r.lo != null ? zero + r.lo * unit : x0) - 4 : Math.max(x1, r.hi != null ? zero + r.hi * unit : x1) + 4;
    const name = ckFit(r.name, CK_HBAR_LABEL - 10);
    return `<g class="ck-hbar ck-tone-${r.tone || "flat"}"${r.key != null ? ` data-ck-tile="${esc(r.key)}"` : ""} title="${esc(r.title || "")}">
      <text class="ck-hbar-name"${r.tip != null ? ` data-tip="${esc(r.tip)}"` : name[1]} x="${CK_HBAR_LABEL - 6}" y="${y + 14}">${esc(name[0])}</text>
      <rect x="${x0.toFixed(1)}" y="${y + 3}" width="${Math.max(1, x1 - x0).toFixed(1)}" height="${CK_HBAR - 6}"/>${whisker}
      <text class="ck-hbar-value${r.v < 0 ? " left" : ""}" x="${end.toFixed(1)}" y="${y + 14}">${esc(c.label(r.v))}</text></g>`;
  }).join("");
  const high = c.rows.length * CK_HBAR;
  return `<svg class="ck-hbars" width="${c.width}" height="${high}" viewBox="0 0 ${c.width} ${high}"><line class="ck-zero" x1="${zero}" x2="${zero}" y1="0" y2="${high}"/>${rows}</svg>${
    ckLegendHtml(c.legend, drawn)}`;
}

function ckStackHBarsSvg(c) {
  const plot = Math.max(60, c.width - CK_HBAR_LABEL - 70), drawn = new Set();
  const totals = c.rows.map((r) => r.parts.reduce((s, p) => s + p.v, 0)), unit = plot / Math.max(1e-9, ...totals);
  const rows = c.rows.map((r, i) => {
    const y = i * CK_HBAR;
    let x = CK_HBAR_LABEL;
    const parts = r.parts.map((p) => {
      const w = p.v * unit, at = x;
      x += w;
      drawn.add(`s${p.series}`);
      const label = ckWhole(p.name, w) ? `<text class="ck-bar-label" x="${(at + 3).toFixed(1)}" y="${y + 14}">${esc(p.name)}</text>` : "";
      return ckPartSvg(p, at, y + 3, Math.max(1, w), CK_HBAR - 6, c.id, label);
    }).join("");
    const [name, whole] = ckFit(r.name, CK_HBAR_LABEL - 10);
    return `<g class="ck-stack"${r.key != null ? ` data-ck-tile="${esc(r.key)}"` : ""}><text class="ck-hbar-name" x="${CK_HBAR_LABEL - 6}" y="${y + 14}"${whole}>${
      esc(name)}</text>${parts}<text class="ck-hbar-value" x="${(x + 4).toFixed(1)}" y="${y + 14}">${esc(c.label(totals[i]))}</text></g>`;
  }).join("");
  const high = c.rows.length * CK_HBAR;
  return `<svg class="ck-hbars" width="${c.width}" height="${high}" viewBox="0 0 ${c.width} ${high}"><defs>${ckFillDefs(c.id)}</defs><line class="ck-zero" x1="${CK_HBAR_LABEL}" x2="${CK_HBAR_LABEL}" y1="0" y2="${high}"/>${rows}</svg>${
    ckLegendHtml(c.legend, drawn)}`;
}

function ckHeatSvg(c) {
  const left = 40, top = 14, cw = (c.width - left) / 24, ch = Math.max(16, Math.min(22, cw)), drawn = new Set();
  const values = c.cells.flat().map((x) => x.v).filter((v) => v != null);
  const lo = Math.min(...values), hi = Math.max(...values);
  const heads = Array.from({ length: 24 }, (_, h) => (h % 3 ? "" : `<text class="ck-heat-hour" x="${(left + h * cw + 2).toFixed(1)}" y="10">${String(h).padStart(2, "0")}</text>`)).join("");
  const rows = c.cells.map((row, d) => `<text class="ck-heat-day" x="${left - 5}" y="${(top + d * ch + ch / 2 + 4).toFixed(1)}">${esc(c.days[d])}</text>${row.map((x, h) => {
    const at = `x="${(left + h * cw).toFixed(1)}" y="${(top + d * ch).toFixed(1)}" width="${Math.max(1, cw - 1).toFixed(1)}" height="${ch - 1}"`;
    let fill = ` fill="url(#ck-hatch-${c.id})"`, cls = "none";
    if (x.v != null) {
      if (c.two) {
        const reach = Math.max(1e-9, Math.abs(hi - 1), Math.abs(1 - lo));
        cls = x.v >= 1 ? "gain" : "loss";
        fill = ` fill-opacity="${(0.15 + 0.85 * Math.abs(x.v - 1) / reach).toFixed(2)}"`;
      } else {
        cls = "level";
        fill = ` fill-opacity="${(0.15 + 0.85 * (hi > lo ? (x.v - lo) / (hi - lo) : 1)).toFixed(2)}"`;
      }
    }
    const count = x.n && cw >= 14 ? `<text class="ck-heat-n" x="${(left + h * cw + cw / 2).toFixed(1)}" y="${(top + d * ch + ch / 2 + 3.5).toFixed(1)}">${x.n}</text>` : "";
    drawn.add(cls === "none" ? "hatch" : `heat-${cls}`);
    return `<g class="ck-heat-cell ${cls}" title="${esc(x.title || "")}"><rect ${at}${fill}/>${count}</g>`;
  }).join("")}`).join("");
  const high = top + 7 * ch;
  return `<svg class="ck-heat" width="${c.width}" height="${high}" viewBox="0 0 ${c.width} ${high}">${ckHatchSvg([], { from: 0, to: 1 }, 1, 0, 0, c.id)}${heads}${rows}</svg>${
    ckLegendHtml(c.legend, drawn)}`;
}
