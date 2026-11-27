// The Index of Azeroth. Copyright 2026 Index Case <indexofazeroth@pm.me>. PolyForm Strict 1.0.0, see LICENSE.md.
"use strict";

const CTH_REFRESH_MS = 30000;
const CTH_COUNT_MS = 3000;
const CTH_TABS = [["scans", "inv_misc_spyglass_03"], ["market", "inv_misc_coin_02"], ["item", "inv_misc_bag_08"], ["buy", "inv_misc_coin_01"],
  ["sell", "inv_misc_coin_03"], ["auctions", "inv_scroll_03"], ["record", "inv_misc_note_01"], ["goods", "inv_box_01"],
  ["craft", "trade_blacksmithing"], ["odds", "spell_holy_sealofwisdom"]];
const CTH_BUILT = ["scans", "market", "item", "buy", "sell", "craft", "auctions", "record", "goods", "odds"];
const CTH_SCAN_VIEWS = ["diagram", "chart", "table"];
const CTH_LANE = 20, CTH_LANE_GAP = 4, CTH_TICK_SHORT = 9;
const CTH_STRIP = 14;
const CTH_LINE = 70;
const CTH_RISK_LEAST = 0.2, CTH_RISK_MOST = 2, CTH_RISK_STEP = 0.2;
const cthRisk = (v) => {
  const n = Number(v);
  if (v == null || String(v).trim() === "" || !Number.isFinite(n)) return 1;
  const r = Math.round(n / CTH_RISK_STEP) * CTH_RISK_STEP;
  return Math.min(CTH_RISK_MOST, Math.max(CTH_RISK_LEAST, Math.round(r * 100) / 100));
};
const cth = { open: false, data: null, failed: false, house: null, tab: "scans", range: ckRangeOf(), picked: null,
  show: ckStored("budget") === "all" ? "all" : "here", vendor: ckStored("vendor") === "1", risk: cthRisk(ckStored("risk")),
  timer: 0, again: 0, scroll: 0, recalc: false };
const cthShow = () => `show=${cth.show}`;
const CTH_W = wordsOf("page.counting.window"), CTS_W = wordsOf("page.counting.scans");
const cthW = (key, fill) => fillWords(CTH_W[key], fill) ?? "";
const ctsW = (key, fill) => fillWords(CTS_W[key], fill) ?? "";
const cthIcon = (name) => `<img class="mt-ico" src="/icon/${esc(name)}.jpg" alt="">`;
const cthNow = () => Date.now() / 1000;

function cthFeesLines(f) {
  const pct = (share) => Math.round(share * 1000) / 10;
  const lines = [cthW(`fees.cut.${f.from.cut === "game" ? "game" : f.kind}`, { n: pct(f.cut) }),
    cthW(`fees.deposit.${f.from.deposit === "game" ? "game" : f.kind}`, { n: pct(f.deposit.share) })];
  if (!f.read) lines.push(cthW("fees.guide"));
  return lines;
}


function cthView(d = cth.data) {
  if (cth.picked) return cth.picked;
  const scans = d?.scans || [];
  return ckRangeView(cth.range, scans.length ? { from: scans[0].t, to: scans[scans.length - 1].t } : null, d?.now ?? cthNow());
}
function cthScans(d = cth.data, view = cthView(d)) {
  const all = (d?.scans || []).map((s, i, list) => ({ ...s, gap: i ? s.t - list[i - 1].t : null }));
  return { all, shown: all.filter((s) => s.t >= view.from && s.t <= view.to) };
}
const cthBy = (s) => s.by || ctsW("lane.none");
function cthCard(s, now) {
  const lines = [ctsW("tick", { when: pvWhen(s.t) }), ctsW("tick.by", { name: cthBy(s) }), ctsW(s.whole ? "tick.whole" : "tick.partial"),
    ctsW("tick.auctions", { auctions: num(s.auctions) })];
  return ckCard({ value: lines.join("\n"), t: s.t }, now);
}


function cthHouseHtml(d) {
  const label = `<span class="cth-label">${esc(cthW("house"))}</span>`;
  if (d.houses.length < 2) return `<span class="cth-field" title="${esc(cthW("house.tip"))}">${label}<b>${esc(d.name || "")}</b></span>`;
  const options = d.houses.map((h) => `<option value="${esc(h.house)}"${h.house === d.house ? " selected" : ""}>${esc(h.name)}</option>`).join("");
  const missing = d.houses.some((h) => h.house === d.house) ? "" : `<option value="${esc(d.house || "")}" selected>${esc(d.name || "")}</option>`;
  return `<label class="cth-field" title="${esc(cthW("house.tip"))}">${label}<select class="cth-house" id="cth-house">${missing}${options}</select></label>`;
}

function cthShowHtml(d) {
  const b = d.budget;
  const amount = (v) => (v == null ? `<span class="muted" title="${esc(cthW("show.none.tip"))}">${esc(cthW("show.none"))}</span>` : ckGold(v));
  const key = (k, v) => `<button type="button" class="key small cth-budget" data-cth-show="${k}" aria-pressed="${cth.show === k}"
    title="${esc(cthW(`show.${k}.tip`))}">${esc(cthW(`show.${k}`))} <span class="cth-gold">${amount(v)}</span></button>`;
  const reach = b.reach !== b.all ? `<small class="cth-reach" title="${esc(cthW("show.reach.tip"))}">${fillWords(esc(CTH_W["show.reach"]), { coins: ckGold(b.reach) })}</small>` : "";
  const unknown = b.unknown ? `<small class="muted">${esc(wordCount("page.counting.window.show.unknown", b.unknown))}</small>` : "";
  const nobody = cth.show === "here" && !d.playing ? `<small class="muted">${esc(cthW("show.nobody"))}</small>` : "";
  return `<span class="cth-field"><span class="cth-label">${esc(cthW("show"))}</span>${key("here", b.here)}${key("all", b.all)}${reach}${unknown}${nobody}</span>`;
}

function cthScansLine(all, shown, now) {
  if (!all.length) return "";
  const newest = all[all.length - 1];
  const first = newest.by ? cthW("newest", { ago: ago(newest.t, now), name: newest.by }) : cthW("newest.unknown", { ago: ago(newest.t, now) });
  const gaps = shown.slice(1).map((s) => s.gap);
  const parts = [esc(first), shown.length ? esc(wordCount("page.counting.window.in-range", shown.length)) : esc(cthW("none-in-range")),
    gaps.length ? esc(cthW("gap", { span: roughSpan(Math.max(...gaps)) })) : ""];
  return `<p class="cth-line">${parts.filter(Boolean).join(" ")}</p>`;
}

const cthWorking = (d) => !!(d.summarising || cth.recalc || ((cth.tab === "buy" || cth.tab === "sell") && ctp.data?.summarising));

function cthRestsOn(w, key, t, now) {
  if (!t) return "";
  const scans = cth.data?.scans || [], newest = scans.length ? scans[scans.length - 1].t : null;
  const fill = { ago: ckAgeText(now - t) };
  const at = scans.find((s) => s.t === t), short = at?.arrived ? `. ${cthW("arrived", { n: at.arrived })}` : "";
  if (newest == null || t >= newest) return w(key, fill) + short;
  const line = (w(`${key}.older`, fill) || w(key, fill)) + short;
  return cth.data && cthWorking(cth.data) ? cthW("newer", { line, ago: ckAgeText(now - newest) }) : line;
}

function cthRecalcHtml(d) {
  const busy = cthWorking(d);
  return `<button type="button" class="key small cth-recalc" data-cth-recalc="1"${busy ? " disabled" : ""}
    title="${esc(cthW(busy ? "recalc.busy.tip" : "recalc.tip"))}">${cthIcon("inv_misc_pocketwatch_01")}${esc(cthW("recalc"))}</button>`;
}

function cthHeaderHtml(d, all, shown) {
  const now = d.now;
  const list = ctpListKeyHtml();
  const working = cthWorking(d) ? `<p class="cth-line muted">${esc(cthW("working"))}</p>` : "";
  return `<div class="cth-head"><div class="cth-row">${cthHouseHtml(d)}<span class="cth-field"><span class="cth-label">${esc(cthW("range"))}</span>${
    ckRangeHtml(cth.range, !!cth.picked)}</span></div>
    <div class="cth-row">${cthShowHtml(d)}${list}${cthRecalcHtml(d)}</div>${cthScansLine(all, shown, now)}${working}</div>`;
}

function cthAsks(state, asked, force = false, kept = "") {
  const stamp = cth.data?.stamp ?? null, fresh = asked !== state.asked;
  if (!force && !fresh && kept === state.kept && stamp === state.stamp) return false;
  if (fresh) state.data = null;
  state.asked = asked;
  state.kept = kept;
  state.stamp = stamp;
  return fresh ? "new" : "again";
}

const cthAnswered = (state, asked, kept = "") => asked === state.asked && kept === state.kept;

function cthTabsHtml() {
  return `<div class="cth-tabs" role="tablist">${CTH_TABS.map(([k, icon]) => `<button type="button" class="key small cth-tab" role="tab" data-cth-tab="${k}"
    aria-pressed="${cth.tab === k}" title="${esc(cthW(`tab.${k}.tip`))}">${cthIcon(icon)}${esc(cthW(`tab.${k}`))}</button>`).join("")}</div>`;
}


function cthTimelineSvg(all, shown, view, w, now) {
  const names = [...new Set(all.map(cthBy))], series = ckSeriesOf(names), drawn = new Set();
  const top = TC_TOP, lanesH = names.length * (CTH_LANE + CTH_LANE_GAP);
  const x = (t) => chartX(t, view, w).toFixed(1);
  const laneY = (i) => top + i * (CTH_LANE + CTH_LANE_GAP);
  const grounds = names.map((name, i) => `<rect class="cth-lane" x="0" y="${laneY(i)}" width="${w}" height="${CTH_LANE}"/>`).join("");
  const lanes = names.map((name, i) => {
    const y = laneY(i);
    const mine = shown.filter((s) => cthBy(s) === name);
    for (const s of mine) drawn.add(s.whole ? "tick" : "tick-short");
    const ticks = mine.map((s) => `<g class="cth-tick ck-s${series[name]}" title="${esc(cthCard(s, now))}">
      <rect class="cth-tick-hit" x="${(+x(s.t) - 3).toFixed(1)}" y="${y}" width="7" height="${CTH_LANE}"/><line x1="${x(s.t)}" x2="${x(s.t)}"
      y1="${y + (s.whole ? 1 : CTH_TICK_SHORT)}" y2="${y + CTH_LANE - 1}"/></g>`).join("");
    return `<text class="tc-lane-name" x="-6" y="${y + CTH_LANE / 2 + 3.5}">${esc(name)}</text>${ticks}`;
  }).join("");
  const hatch = grounds + ckHatchSvg(ckEmpty(all.map((s) => s.t), view), view, w, top, lanesH, "cth-lanes", drawn);
  const stripTop = top + lanesH + 4, days = cthDays(view, shown), most = Math.max(1, ...days.map((d) => d.n));
  const cells = days.map((d) => {
    const a = Math.max(0, chartX(d.from, view, w)), b = Math.min(w, chartX(d.to, view, w));
    if (b > a) drawn.add(d.n ? "heat-level" : "hatch");
    const tip = d.n ? wordCount("page.counting.scans.coverage.cell", d.n, { day: d.label }) : ctsW("coverage.cell.none", { day: d.label });
    const fill = d.n ? ` fill-opacity="${(0.25 + 0.75 * d.n / most).toFixed(2)}"` : ` style="fill: url(#ck-hatch-cth-lanes)"`;
    return b > a ? `<rect class="cth-cell${d.n ? "" : " none"}" x="${a.toFixed(1)}" y="${stripTop}" width="${Math.max(1, b - a - 1).toFixed(1)}" height="${CTH_STRIP}"${fill} title="${esc(tip)}"/>` : "";
  }).join("");
  const scaleTop = stripTop + CTH_STRIP + 2, height = scaleTop + TC_SCALE;
  return `<svg class="tc cth-timeline" width="${w}" height="${height}" viewBox="0 0 ${w} ${height}">${hatch}${lanes}
    <text class="tc-lane-name" x="-6" y="${stripTop + CTH_STRIP / 2 + 3.5}">${esc(ctsW("coverage"))}</text>${cells}${tcScale(timeScale(view.from, view.to, w), x, scaleTop)}</svg>${
    ckLegendHtml([{ look: "tick", name: ctsW("tick.whole"), tip: ctsW("whole.tip") }, { look: "tick-short", name: ctsW("tick.partial"), tip: ctsW("partial.tip") },
      { look: "heat-level", name: ctsW("coverage") }, ckNoScanLegend()], drawn)}`;
}

function cthDays(view, shown) {
  const out = [], d = new Date(view.from * 1000);
  d.setHours(0, 0, 0, 0);
  while (d.getTime() / 1000 < view.to) {
    const from = d.getTime() / 1000;
    d.setDate(d.getDate() + 1);
    const to = d.getTime() / 1000, mine = shown.filter((s) => s.t >= from && s.t < to), by = {};
    for (const s of mine) by[cthBy(s)] = (by[cthBy(s)] || 0) + 1;
    out.push({ from, to, n: mine.length, by, label: new Date(from * 1000).toLocaleDateString([], { day: "numeric", month: "short" }) });
  }
  return out;
}

function cthChartSvg(all, shown, view, w, now) {
  const names = [...new Set(all.map(cthBy))], series = ckSeriesOf(names), days = cthDays(view, shown);
  const bins = days.filter((d) => d.n).map((d) => ({ from: d.from, to: d.to, parts: names.filter((n) => d.by[n]).map((n) => ({
    series: series[n], v: d.by[n], name: n, title: wordCount("page.counting.scans.chart.day", d.by[n], { day: d.label, name: n }) })) }));
  const scale = timeScale(view.from, view.to, w), empty = ckEmpty(all.map((s) => s.t), view);
  const bars = ckBarsSvg({ id: "cth-days", width: w, high: 110, view, scale, bins, values: { ...valueTicks(Math.max(1, ...days.map((d) => d.n)), 4, true), label: num },
    hatch: empty, legend: [...ckSeriesLegend(series), ckNoScanLegend()] });
  const newest = all.length ? all[all.length - 1].t : now, drawn = new Set(shown.length ? ["line", "dot"] : []);
  const line = timeChartSvg({ id: "cth-auctions", width: w, view, plot: CTH_LINE, scale,
    values: { ...valueTicks(Math.max(1, ...shown.map((s) => s.auctions))), label: (v) => (v >= 1000 ? `${num(v / 1000)}k` : num(v)) },
    dots: shown.map((s) => ({ t: s.t, v: s.auctions, title: cthCard(s, now) })), line: ckBroken(shown.map((s) => ({ t: s.t, v: s.auctions }))),
    under: ckHatchSvg(empty, view, w, TC_TOP, CTH_LINE, "cth-auctions", drawn), fade: ckFade(now - newest) });
  return `${bars}<h4 class="cth-sub">${esc(ctsW("chart.auctions"))}</h4>${line}${ckLegendHtml([{ look: "line", name: ctsW("chart.auctions") },
    { look: "dot", name: ckW("legend.scan") }, ckNoScanLegend()], drawn)}`;
}

function cthScanColumns(now) {
  const by = (s) => {
    if (!s.by) return `<span class="muted" title="${esc(ctsW("by.none.tip"))}">${esc(ctsW("by.none"))}</span>`;
    const told = s.from === "record" ? ` <small class="cth-told" title="${esc(ctsW("by.record.tip"))}">${esc(ctsW("by.record"))}</small>` : "";
    return `${esc(s.by)}${told}`;
  };
  const items = (s) => {
    if (s.items != null) return num(s.items);
    const k = s.counted ? "not-read" : "counting";
    return `<span class="muted" title="${esc(ctsW(`${k}.tip`))}">${esc(ctsW(k))}</span>`;
  };
  const kind = (s) => `<span title="${esc(ctsW(s.whole ? "whole.tip" : "partial.tip"))}">${esc(ctsW(s.whole ? "whole" : "partial"))}</span>`;
  const gap = (s) => (s.gap == null ? `<span class="muted" title="${esc(ctsW("first.tip"))}">${esc(ctsW("first"))}</span>` : esc(roughSpan(s.gap)));
  return [
    { key: "when", label: ctsW("when"), value: (s) => s.t, cell: (s) => `${cthIcon(CTH_TABS[0][1])}${esc(pvWhen(s.t))}${ckAgeTag(s.t, now)}` },
    { key: "by", label: ctsW("by"), value: (s) => s.by?.toLowerCase() ?? null, cell: by },
    { key: "kind", label: ctsW("kind"), value: (s) => (s.whole ? 1 : 0), cell: kind },
    { key: "auctions", label: ctsW("auctions"), num: true, value: (s) => s.auctions, cell: (s) => num(s.auctions) },
    { key: "items", label: ctsW("items"), tip: ctsW("items.tip"), num: true, value: (s) => s.items, cell: items },
    { key: "read", label: ctsW("read"), num: true, value: (s) => s.seconds ?? null, cell: (s) => (s.seconds == null ? "" : esc(duration(s.seconds))) },
    { key: "gap", label: ctsW("gap"), tip: ctsW("gap.tip"), num: true, value: (s) => s.gap, cell: gap },
  ];
}

function cthScansHtml(all, shown) {
  const view = ckViewOf("cth-scans", CTH_SCAN_VIEWS);
  let body;
  if (!all.length) body = `<p class="cth-empty">${esc(cthW("empty"))}</p><p class="muted cth-flavour">${esc(cthW("empty.flavour"))}</p>`;
  else if (view === "table") body = ckTable({ id: "cth-scans", columns: cthScanColumns(cth.data.now), rows: shown, sort: { key: "when", down: true } });
  else body = `<div class="cth-box"><div class="ck-drag cth-plot" id="cth-plot" data-view="${view}"><div class="ck-pick" hidden></div></div></div>`;
  return ckPanelHtml({ id: "cth-scans", icon: CTH_TABS[0][1], title: ctsW("title"), views: all.length ? CTH_SCAN_VIEWS : [], view, body });
}

function cthDraw() {
  const host = $("cth-plot");
  if (!host || !cth.data) return;
  const view = cthView(), { all, shown } = cthScans(cth.data, view), w = Math.max(200, Math.floor(host.clientWidth));
  host.dataset.from = view.from;
  host.dataset.to = view.to;
  const svg = host.dataset.view === "chart" ? cthChartSvg(all, shown, view, w, cth.data.now) : cthTimelineSvg(all, shown, view, w, cth.data.now);
  setHtml(host, `${svg}<div class="ck-pick" hidden></div>`);
}


function renderCounting() {
  if (!cth.open) return;
  const d = cth.data;
  const was = $("counting").querySelector(".cth-scroll");
  cth.scroll = was?.scrollTop || 0;
  const rows = was ? ckRowsRead(was) : null;
  let body;
  if (!d) body = `<p class="muted">${esc(cth.failed ? cthW("failed") : cthW("loading"))}</p>`;
  else {
    const { all, shown } = cthScans(d);
    const panel = !CTH_BUILT.includes(cth.tab) ? `<p class="muted cth-not-built">${esc(cthW("not-built", { panel: cthW(`tab.${cth.tab}`) }))}</p>`
      : cth.tab === "item" ? ctiPanelHtml() : cth.tab === "market" ? ctmPanelHtml() : cth.tab === "craft" ? ccrPanelHtml()
      : cth.tab === "auctions" ? cyaPanelHtml() : cth.tab === "goods" ? cgoPanelHtml() : cth.tab === "odds" ? ctoPanelHtml()
      : cth.tab === "record" ? crtPanelHtml()
      : cth.tab === "buy" || cth.tab === "sell" ? ctpPanelHtml(cth.tab) : cthScansHtml(all, shown);
    body = `${cthHeaderHtml(d, all, shown)}${cthTabsHtml()}<div class="cth-scroll">${panel}</div>`;
  }
  setHtml($("counting"), `<div class="j-bar"><span class="j-bar-keys"><button class="key small" data-back="1" title="${esc(cthW("back.tip"))}">${esc(cthW("back"))}</button></span>
    <span class="j-bar-title">${esc(cthW("title"))}</span><span class="j-bar-end">${helpButton("counting")}<button class="key small square x-mark" data-close="1"
    title="${esc(cthW("close.tip"))}">&times;</button></span></div><div class="j-body cth-body">${body}</div>`);
  const scroller = $("counting").querySelector(".cth-scroll");
  if (scroller) scroller.scrollTop = cth.scroll;
  cthDraw();
  if (cth.tab === "item") ctiDraw();
  if (cth.tab === "market") ctmDraw();
  if (cth.tab === "craft") ccrDraw();
  if (cth.tab === "auctions" || cth.tab === "goods") cgDraw();
  if (cth.tab === "odds") ctoDraw();
  if (cth.tab === "record") crtDraw();
  if (cth.tab === "buy" || cth.tab === "sell") ctpDraw();
  if (scroller) ckRowsPlay(scroller, rows);
}

function takeCounting(d) {
  cth.data = d;
  cth.failed = false;
  cth.recalc = false;
  clearTimeout(cth.again);
  if ((d.counting || d.summarising) && cth.open) cth.again = setTimeout(loadCounting, CTH_COUNT_MS);
  renderCounting();
}

function loadCounting() {
  const url = `/api/counting${cth.house ? `?house=${encodeURIComponent(cth.house)}` : ""}`;
  getJson(url, { key: "/api/counting", force: true })?.then(takeCounting, () => { cth.failed = true; renderCounting(); });
}

function recalculate() {
  if (!cth.data || cthWorking(cth.data)) return;
  cth.recalc = true;
  ctpRecalc();
  renderCounting();
  postJson("/api/counting/recalculate", { house: cth.data.house || null }, { key: "/api/counting" })
    ?.then(takeCounting, () => { cth.recalc = false; renderCounting(); });
}

function openCounting() {
  cth.open = true;
  emit("window", "counting");
  $("counting").hidden = false;
  renderCounting();
  loadCounting();
  clearInterval(cth.timer);
  cth.timer = setInterval(loadCounting, CTH_REFRESH_MS);
}

function closeCounting() {
  cth.open = false;
  clearInterval(cth.timer);
  clearTimeout(cth.again);
  $("counting").hidden = true;
}

$("counting").addEventListener("click", (e) => {
  const b = e.target.closest("button");
  if (b?.dataset.close) return closeCounting();
  if (b?.dataset.back) {
    closeCounting();
    return market.toggle(true);
  }
  const range = ckRangeClick(e);
  if (range) {
    cth.range = range;
    cth.picked = null;
    return renderCounting();
  }
  if (ckSwitchClick(e) || ckSortClick(e)) return renderCounting();
  if (b?.dataset.cthRecalc) return recalculate();
  if (ctiClick(e) || ctmClick(e) || ccrClick(e) || cgClick(e) || crtClick(e) || ctpClick(e)) return;
  if (b?.dataset.cthTab) {
    cth.tab = b.dataset.cthTab;
    return renderCounting();
  }
  if (b?.dataset.cthShow) {
    cth.show = b.dataset.cthShow;
    ckStore("budget", cth.show);
    renderCounting();
  }
});
$("counting").addEventListener("change", (e) => {
  if (e.target.dataset.cthRisk) {
    cth.risk = cthRisk(e.target.value);
    ckStore("risk", String(cth.risk));
    ctpLoad(true);
    return renderCounting();
  }
  if (e.target.dataset.cthVendor) {
    cth.vendor = e.target.checked;
    ckStore("vendor", cth.vendor ? "1" : "0");
    ctpLoad(true);
    return renderCounting();
  }
  if (e.target.id !== "cth-house") return;
  cth.house = e.target.value;
  cth.data = null;
  renderCounting();
  loadCounting();
});
$("counting").addEventListener("input", (e) => {
  const slider = e.target.closest?.("[data-cth-risk]");
  const out = slider?.closest(".ctp-risk")?.querySelector("output");
  if (out) out.textContent = `${cthRisk(slider.value)}\u00d7`;
});
ckDragRange($("counting"), (v) => { cth.picked = v; renderCounting(); });
addEventListener("resize", () => {
  if (!cth.open) return;
  cthDraw();
  if (cth.tab === "item") ctiDraw();
  if (cth.tab === "market") ctmDraw();
  if (cth.tab === "craft") ccrDraw();
  if (cth.tab === "auctions" || cth.tab === "goods") cgDraw();
  if (cth.tab === "odds") ctoDraw();
  if (cth.tab === "record") crtDraw();
  if (cth.tab === "buy" || cth.tab === "sell") ctpDraw();
});
on("counting", openCounting);
on("auction", () => { if (cth.open) loadCounting(); });
on("snapshot", (snap) => {
  const v = snap?.versions?.ledger ?? null;
  if (v === cth.ledger) return;
  cth.ledger = v;
  if (cth.open) loadCounting();
});
closable(LAYER.journal, () => cth.open, closeCounting);
on("window", (w) => { if (w !== "counting" && cth.open) closeCounting(); });
