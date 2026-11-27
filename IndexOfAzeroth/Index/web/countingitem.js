// The Index of Azeroth. Copyright 2026 Index Case <indexofazeroth@pm.me>. PolyForm Strict 1.0.0, see LICENSE.md.
"use strict";

const CTI_W = wordsOf("page.counting.item");
const ctiW = (key, fill) => fillWords(CTI_W[key], fill) ?? "";
const CTI_VIEWS = { history: ["chart", "diagram", "table"], depth: ["diagram", "chart", "table"], unusual: ["chart", "table"],
  volatility: ["chart", "table"], sales: ["chart", "diagram", "table"] };
const CTI_PLOT = 150;
const CTI_FIND_MS = 250;
const CTI_FIND_MOST = 12;
const CTI_BINS = 12;
const CTI_UNUSUAL_LEAST = 5;
const CTI_DAY_LEAST = 3;
const CTI_SHOWN = 0.95;
const CTI_CHEAP = 0.15, CTI_REACH = 3;
const CTI_AGAIN_MS = 3000;
const CTI_PERCENTILES = [10, 25, 50, 75, 90];
const cti = { item: ckStored("item"), data: null, asked: null, failed: false, find: "", found: null, timer: 0, again: 0 };

const ctiGold = (copper) => ckGold(Math.round(copper));
const ctiText = (copper) => moneyText(Math.round(copper));


function ctiSince() {
  if (cth.range === "all" && !cth.picked) return 0;
  return Math.floor(cthView().from / CK_DAY) * CK_DAY;
}

function ctiLoad(force = false) {
  if (!cti.item || !cth.data) return;
  const asked = `house=${encodeURIComponent(cth.data.house || "")}&item=${encodeURIComponent(cti.item)}&since=${ctiSince()}`;
  if (!cthAsks(cti, asked, force)) return;
  getJson(`/api/counting/item?${asked}`, { key: "/api/counting/item", force: true })?.then((d) => {
    if (asked !== cti.asked) return;
    cti.data = d;
    cti.failed = false;
    clearTimeout(cti.again);
    if (d.summarising && cth.open) cti.again = setTimeout(() => ctiLoad(true), CTI_AGAIN_MS);
    renderCounting();
  }, () => { cti.failed = true; renderCounting(); });
}

function ctiOpen(item) {
  cti.item = String(item);
  ckStore("item", cti.item);
  cti.found = null;
  cti.find = "";
  ctiLoad(true);
  renderCounting();
}

function ctiFind(words) {
  cti.find = words;
  clearTimeout(cti.timer);
  if (words.trim().length < 2) {
    cti.found = null;
    return ctiFoundDraw();
  }
  cti.timer = setTimeout(() => {
    getJson(`/api/market/search?q=${encodeURIComponent(words.trim())}`, { key: null }).then((j) => {
      if (words !== cti.find) return;
      cti.found = (j.items || []).slice(0, CTI_FIND_MOST);
      ctiFoundDraw();
    }, () => {});
  }, CTI_FIND_MS);
}

function ctiFoundHtml() {
  if (!cti.found) return "";
  if (!cti.found.length) return `<p class="muted cti-found-none">${esc(ctiW("find.none"))}</p>`;
  return cti.found.map((f) => ckItemHtml({ ...f, key: f.item }, { open: `data-cti-item="${esc(f.item)}"`, cls: ["key", "small", "cti-find-item"] })).join("");
}
function ctiFoundDraw() {
  const host = $("cti-found");
  if (host) setHtml(host, ctiFoundHtml());
}


const ctiFact = (label, value, tip) => `<span class="cti-fact"${tip ? ` title="${esc(tip)}"` : ""}><span class="cth-label">${esc(label)}</span>${value}</span>`;

function ctiPriceLine(d) {
  const p = d.price, now = d.now;
  if (!p) return `<p class="cti-line">${ctiFact(ctiW("price"), `<span class="muted">${esc(ctiW("price.none"))}</span>`, ctiW("price.tip"))}</p>`;
  const range = fillWords(esc(CTI_W["price.range"]), { low: ctiGold(p.low), high: ctiGold(p.high) });
  const conf = ckConfidence({ steps: p.steps, scans: p.scans, newest: p.newest, gap: p.gap }, now);
  const facts = [esc(wordCount("page.counting.item.price.scans", p.scans)), p.gap ? esc(ctiW("price.gap", { span: roughSpan(p.gap) })) : "",
    esc(cthRestsOn(ctiW, "price.newest", p.newest, now))].filter(Boolean).join(", ");
  const few = p.scans < 3 ? `<p class="muted cti-note">${esc(ctiW("price.few"))}</p>` : "";
  return `<p class="cti-line">${ctiFact(ctiW("price"), `<b class="cti-price">${ctiGold(p.price)}</b> <span class="cti-range">${range}</span>`, ctiW("price.tip"))}
    ${conf}<span class="cti-dim">${facts}</span></p>${few}`;
}

function ctiFactsLine(d) {
  const now = d.now, c = d.cheapest;
  const cheapest = c ? `${ctiGold(c.unit)}${ckAgeTag(c.t, now)}${c.bait ? ` <span class="cti-bait" title="${esc(ctiW("bait.tip"))}">${esc(ctiW("bait"))}</span>` : ""}` : `<span class="muted">${esc(ctiW("depth.none"))}</span>`;
  const sold = csaFactHtml(d);
  const how = d.vendor == null ? "vendor.unknown" : "vendor.none";
  const vendor = !d.item ? "" : ctiFact(ctiW("vendor"), d.vendor ? ctiGold(d.vendor) : `<span class="muted" title="${esc(ctiW(`${how}.tip`))}">${esc(ctiW(how))}</span>`, ctiW("vendor.tip"));
  let state = "";
  if (d.state?.state) {
    const change = `${d.state.change >= 0 ? "+" : "−"}${Math.round(Math.abs(d.state.change) * 100)}%`, name = ctiW(`state.${d.state.state}`);
    const held = d.state.held != null ? ctiW("state.held.tip", { state: name, n: Math.round(d.state.held * 100) }) : ctiW("state.held.none", { state: name });
    const tip = [ctiW("state.change", { change, coins: ctiText(d.state.level) }), d.state.sure === false ? ctiW("state.range.tip") : "", held].filter(Boolean).join("\n");
    state = ctiFact(ctiW("state"), `<span class="cti-state" title="${esc(tip)}">${esc(d.state.uncertain ? ctiW("state.uncertain", { state: name }) : name)} ${
      esc(change)}</span>`, ctiW("state.tip"));
  } else if (d.state) {
    state = ctiFact(ctiW("state"), `<span class="muted" title="${esc(ctiW("state.none.tip", { n: d.state.days }))}">${esc(ctiW("state.none"))}</span>`, ctiW("state.tip"));
  }
  return `<p class="cti-line">${ctiFact(ctiW("cheapest"), cheapest, ctiW("cheapest.tip"))}${ctiFact(ctiW("sold"), sold, csaW("fact.tip"))}${vendor}${state}</p>`;
}


const ctiShown = (d, view) => d.scans.filter((s) => s.t >= view.from && s.t <= view.to);
const ctiFade = (d) => (d.scans.length ? ckFade(d.now - d.scans[d.scans.length - 1].t) : 1);

function ctiBand(d) {
  const times = d.scans.map((s) => s.t), most = ckGapMost(times);
  return d.band.map(([t, , lo, hi]) => {
    const next = times.findIndex((s) => s > t);
    const broken = next > 0 && times[next] - times[next - 1] > most && t > times[next - 1];
    return { x: t, lo: broken ? null : lo, hi };
  });
}

function ctiAxis(values) {
  const lo = Math.min(...values), hi = Math.max(...values);
  return ckAxis(Math.max(0, lo - (hi - lo) * 0.15 - lo * 0.05), hi + (hi - lo) * 0.15 + hi * 0.05);
}

function ctiDotCard(s, now) {
  const lines = [ctiW("history.dot", { coins: ctiText(s.low), when: pvWhen(s.t) })];
  if (s.bait) lines.push(ctiW("history.dot.bait"));
  if (s.level != null) lines.push(ctiW("history.level", { coins: ctiText(s.level), low: ctiText(s.lo), high: ctiText(s.hi) }));
  if (s.by) lines.push(ctsW("tick.by", { name: s.by }));
  return ckCard({ value: lines.join("\n"), t: s.t }, now);
}


function ctiHistorySvg(d, view, w) {
  const shown = ctiShown(d, view), now = d.now;
  const values = [...shown.flatMap((s) => [s.low, s.level, s.price, s.lo, s.hi]), ...(d.support ? [d.support.p10, d.support.p90] : [])].filter((v) => v != null);
  if (!shown.length || !values.length) return `<p class="muted">${esc(ctiW("history.empty"))}</p>`;
  const y = { ...ctiAxis(values), label: ctiText }, fade = ctiFade(d);
  const marks = [...d.changes.map((t) => ({ x: t, label: ctiW("history.mark.change"), title: ctiW("history.mark.change.tip", { when: pvWhen(t) }) })),
    ...d.resets.map((t) => ({ x: t, label: ctiW("history.mark.reset"), title: ctiW("history.mark.reset.tip", { when: pvWhen(t) }) })),
    ...d.breaks.map((t) => ({ x: t, label: ctiW("history.mark.break"), title: ctiW("history.mark.break.tip", { when: pvWhen(t) }) }))]
    .filter((m) => m.x >= view.from && m.x <= view.to);
  const rules = d.support ? [{ v: d.support.p10, label: ctiW("history.floor"), title: ctiW("history.floor.tip", { coins: ctiText(d.support.p10) }) },
    { v: d.support.p90, label: ctiW("history.ceiling"), title: ctiW("history.ceiling.tip", { coins: ctiText(d.support.p90) }) }] : [];
  const level = ckBroken(d.scans.filter((s) => s.level != null).map((s) => ({ t: s.t, v: s.level }))).map((p) => ({ x: p.t, v: p.v }));
  const flag = (k) => ({ look: `mark-${ctiW(`history.mark.${k}`)}`, name: ctiW(`legend.mark.${k}`) });
  return ckPlotSvg({ id: "cti-history", width: w, high: CTI_PLOT, x: { ...view, ticks: timeScale(view.from, view.to, w).ticks }, y,
    hatch: ckEmpty(d.scans.map((s) => s.t), view), bands: [{ points: ctiBand(d), fade }], rules, marks, lines: [{ points: level, fade }],
    dots: shown.filter((s) => s.low != null).map((s) => ({ x: s.t, v: s.low, hollow: s.bait > 0, title: ctiDotCard(s, now), fade })),
    legend: [{ look: "line", name: ctiW("price"), tip: ctiW("legend.price.tip") }, { look: "band", name: ckW("legend.range"), tip: ctiW("legend.range.tip") },
      { look: "dot", name: ctiW("legend.low"), tip: ctiW("legend.low.tip") }, { look: "hollow", name: ctiW("bait"), tip: ctiW("bait.tip") },
      { look: "rule", name: ctiW("legend.rules"), tip: ctiW("legend.rules.tip") }, flag("change"), flag("reset"), flag("break"), ckNoScanLegend()] });
}

function ctiDays(d, view) {
  const by = new Map();
  for (const s of ctiShown(d, view).filter((s) => s.low != null)) {
    const at = new Date(s.t * 1000);
    at.setHours(0, 0, 0, 0);
    const k = at.getTime() / 1000;
    if (!by.has(k)) by.set(k, []);
    by.get(k).push(s);
  }
  return [...by].filter(([, list]) => list.length >= CTI_DAY_LEAST).map(([from, list]) => ({ from, to: from + CK_DAY,
    low: Math.min(...list.map((s) => s.low)), high: Math.max(...list.map((s) => s.low)), last: list[list.length - 1], n: list.length }));
}

function ctiRangeSvg(d, view, w) {
  const days = ctiDays(d, view);
  if (!days.length) return `<p class="muted">${esc(ctiW("range.none"))}</p>`;
  const y = { ...ctiAxis(days.flatMap((x) => [x.low, x.high])), label: ctiText };
  const pad = CK_DAY * 0.25;
  return ckPlotSvg({ id: "cti-range", width: w, high: CTI_PLOT, x: { ...view, ticks: timeScale(view.from, view.to, w).ticks }, y,
    hatch: ckEmpty(d.scans.map((s) => s.t), view),
    bars: days.map((x) => ({ x0: x.from + pad, x1: x.to - pad, v0: x.low, v1: x.high, series: 2,
      title: ctiW("range.day", { when: new Date(x.from * 1000).toLocaleDateString([], { day: "numeric", month: "short" }), low: ctiText(x.low), high: ctiText(x.high), n: x.n }) })),
    dots: days.map((x) => ({ x: x.last.t, v: x.last.low, title: ctiDotCard(x.last, d.now) })),
    legend: [{ look: "s2", name: ctiW("legend.day"), tip: ctiW("legend.day.tip") }, { look: "dot", name: ctiW("legend.last") }, ckNoScanLegend()] });
}

function ctiHistoryColumns(now) {
  const by = (s) => {
    if (!s.by) return `<span class="muted" title="${esc(ctsW("by.none.tip"))}">${esc(ctsW("by.none"))}</span>`;
    return `${esc(s.by)}${s.from === "record" ? ` <small class="cth-told" title="${esc(ctsW("by.record.tip"))}">${esc(ctsW("by.record"))}</small>` : ""}`;
  };
  const price = (s) => {
    if (s.price != null) return ctiGold(s.price);
    const k = s.auctions ? "table.thin" : "table.gone";
    return `<span class="muted" title="${esc(ctiW(`${k}.tip`))}">${esc(ctiW(k))}</span>`;
  };
  const note = (s) => [s.change && ctiW("table.note.change"), s.reset && ctiW("table.note.reset"), s.bait && ctiW("bait")].filter(Boolean).map(esc).join(", ");
  return [
    { key: "when", label: ctsW("when"), value: (s) => s.t, cell: (s) => `${esc(pvWhen(s.t))}${ckAgeTag(s.t, now)}` },
    { key: "by", label: ctsW("by"), value: (s) => s.by?.toLowerCase() ?? null, cell: by },
    { key: "low", label: ctiW("table.low"), num: true, value: (s) => s.low, cell: (s) => (s.low == null ? "" : ctiGold(s.low)) },
    { key: "price", label: ctiW("table.price"), tip: ctiW("table.price.tip"), num: true, value: (s) => s.price, cell: price },
    { key: "level", label: ctiW("table.level"), tip: ctiW("table.level.tip"), num: true, value: (s) => s.level,
      cell: (s) => (s.level == null ? "" : `${ctiGold(s.level)} <small class="cti-dim">${fillWords(esc(CTI_W["price.range"]), { low: ctiGold(s.lo), high: ctiGold(s.hi) })}</small>`) },
    { key: "units", label: ctiW("table.units"), num: true, value: (s) => s.units, cell: (s) => num(s.units) },
    { key: "auctions", label: ctiW("table.auctions"), num: true, value: (s) => s.auctions, cell: (s) => num(s.auctions) },
    { key: "note", label: ctiW("table.note"), value: (s) => (s.change || s.reset || s.bait ? 1 : 0), cell: note },
  ];
}


function ctiLadder(dp) {
  let have = 0;
  const steps = dp.steps.map(([unit, units, n, cost, far]) => ({ unit, units, n, cost, far, times: dp.farHigh, have: (have += units) }));
  const cheap = (steps.find((s) => s.have >= CTI_CHEAP * dp.units) || steps[steps.length - 1]).unit;
  const cut = steps.findIndex((s, i) => s.have >= CTI_SHOWN * dp.units || (steps[i + 1] && steps[i + 1].unit > CTI_REACH * cheap));
  const shown = steps.slice(0, cut < 0 ? steps.length : cut + 1);
  return { steps, shown, beyond: dp.units - shown[shown.length - 1].have };
}

function ctiBudget(dp) {
  const b = cth.data?.budget?.[cth.show];
  if (b == null || !dp) return null;
  let got = null;
  for (const [units, average, marginal] of dp.curve) {
    if (units * average > b) break;
    got = { units, price: marginal, cost: units * average };
  }
  return { budget: b, got, all: got && got.units >= dp.units };
}

function ctiLadderSvg(d, w) {
  const dp = d.depth, { shown } = ctiLadder(dp), reach = ctiBudget(dp);
  const points = [{ x: shown[0].unit, v: 0 }, ...shown.map((s) => ({ x: s.unit, v: s.have }))];
  const last = shown[shown.length - 1].unit, first = shown[0].unit, span = Math.max(last - first, first * 0.1, 1);
  const x = { from: first - span * 0.03, to: last + span * 0.03 };
  const cuts = reach?.got && !reach.all && reach.got.price <= x.to ? [{ x: reach.got.price, label: ctiW("depth.budget"),
    title: ctiW("depth.budget.tip", { coins: ctiText(reach.budget), units: num(reach.got.units), price: ctiText(reach.got.price) }) }] : [];
  return ckPlotSvg({ id: "cti-ladder", width: w, high: CTI_PLOT, x: { ...x, ticks: ckAcross(x.from, x.to, ctiText) },
    y: { ...ckAxis(0, shown[shown.length - 1].have), label: num }, cuts,
    lines: [{ points, step: true }], legend: [{ look: "line", name: ctiW("legend.listed") }, { look: "dot", name: ctiW("legend.step") },
      { look: "cut", name: ctiW("depth.budget"), tip: ctiW("legend.budget.tip") }],
    dots: shown.map((s) => ({ x: s.unit, v: s.have, title: ctiW("depth.step", { units: num(s.units), n: num(s.n), price: ctiText(s.unit), have: num(s.have) }) })) });
}

function ctiCostSvg(d, w) {
  const dp = d.depth, { shown } = ctiLadder(dp), reach = ctiBudget(dp), most = shown[shown.length - 1].have;
  const curve = dp.curve.filter((c) => c[0] <= most * 1.0001);
  const values = curve.flatMap((c) => [c[1], c[2], ...(c.length > 3 ? [c[4]] : [])]);
  const lines = [{ points: curve.map((c) => ({ x: c[0], v: c[1] })) }, { points: curve.map((c) => ({ x: c[0], v: c[2] })), kind: "alt", step: true }];
  if (dp.survive) lines.push({ points: curve.filter((c) => c.length > 3).map((c) => ({ x: c[3], v: c[4] })), kind: "soft" });
  const cuts = reach?.got && !reach.all ? [{ x: reach.got.units, label: ctiW("depth.budget"),
    title: ctiW("depth.budget.tip", { coins: ctiText(reach.budget), units: num(reach.got.units), price: ctiText(reach.got.price) }) }] : [];
  const dots = curve.filter((_, i) => i % Math.max(1, Math.round(curve.length / 40)) === 0).map((c) => ({ x: c[0], v: c[1],
    title: ctiW("depth.point", { units: num(c[0]), coins: ctiText(c[0] * c[1]), price: ctiText(c[1]) }) }));
  return ckPlotSvg({ id: "cti-cost", width: w, high: CTI_PLOT, x: { from: 0, to: most, ticks: ckAcross(0, most, num) },
    y: { ...ctiAxis(values), label: ctiText }, lines, cuts, dots,
    legend: [{ look: "line", name: ctiW("depth.average") }, { look: "line-alt", name: ctiW("depth.marginal") }, { look: "line-soft", name: ctiW("depth.expected") },
      { look: "dot", name: ctiW("legend.cost") }, { look: "cut", name: ctiW("depth.budget"), tip: ctiW("legend.budget.tip") }] });
}

function ctiDepthNotes(d) {
  const dp = d.depth, { beyond } = ctiLadder(dp), reach = ctiBudget(dp), notes = [ctiW("depth.rule")];
  if (dp.survive) notes.push(ctiW("depth.survive", { share: Math.round(dp.survive.share * 100), span: roughSpan(Math.max(60, d.now - dp.t)) }));
  if (reach?.all) notes.push(ctiW("depth.budget.short", { coins: ctiText(reach.budget) }));
  if (beyond > 0) notes.push(ctiW("depth.beyond", { units: num(beyond) }));
  return notes.map((n) => `<p class="muted cti-note">${esc(n)}</p>`).join("");
}

function ctiDepthColumns() {
  return [
    { key: "unit", label: ctiW("depth.table.price"), num: true, value: (s) => s.unit, cell: (s) => `${ctiGold(s.unit)}${
      s.far ? ` <span class="cti-far" title="${esc(ctiW("depth.far.tip", { times: num(s.times) }))}">${esc(ctiW("depth.far"))}</span>` : ""}` },
    { key: "units", label: ctiW("depth.table.units"), num: true, value: (s) => s.units, cell: (s) => num(s.units) },
    { key: "n", label: ctiW("depth.table.auctions"), num: true, value: (s) => s.n, cell: (s) => num(s.n) },
    { key: "have", label: ctiW("depth.table.total"), num: true, value: (s) => s.have, cell: (s) => num(s.have) },
    { key: "cost", label: ctiW("depth.table.cost"), num: true, value: (s) => s.cost, cell: (s) => ctiGold(s.cost) },
  ];
}


function ctiPast(d, view) {
  const past = ctiShown(d, view).map((s) => s.price).filter((v) => v != null).sort((a, b) => a - b);
  const now = d.price?.price;
  if (now == null || !past.length) return { past, now };
  return { past, now, below: Math.round(100 * past.filter((v) => v < now).length / past.length),
    above: Math.round(100 * past.filter((v) => v > now).length / past.length) };
}

function ctiUnusualLine(p) {
  if (p.above == null) return "";
  return `<p class="cti-line"><b>${esc(p.above >= p.below ? ctiW("unusual.line", { n: p.above }) : ctiW("unusual.line.dearer", { n: p.below }))}</b></p>`;
}

function ctiHistogramSvg(d, view, w) {
  const p = ctiPast(d, view), lo = Math.min(...p.past, p.now), hi = Math.max(...p.past, p.now);
  const width = (hi - lo) / CTI_BINS || Math.max(1, lo * 0.05);
  const bins = Array.from({ length: CTI_BINS }, (_, i) => ({ from: lo + i * width, to: lo + (i + 1) * width, n: 0 }));
  for (const v of p.past) bins[Math.min(CTI_BINS - 1, Math.floor((v - lo) / width))].n++;
  const x = { from: lo - width * 0.5, to: lo + width * (CTI_BINS + 0.5) };
  return ckPlotSvg({ id: "cti-unusual", width: w, high: CTI_PLOT, x: { ...x, ticks: ckAcross(x.from, x.to, ctiText) },
    y: { ...valueTicks(Math.max(1, ...bins.map((b) => b.n)), 4, true), bottom: 0, label: num },
    bars: bins.filter((b) => b.n).map((b) => ({ x0: b.from, x1: b.to, v0: 0, v1: b.n, series: 2,
      title: wordCount("page.counting.item.unusual.bin", b.n, { low: ctiText(b.from), high: ctiText(b.to) }) })),
    cuts: [{ x: p.now, label: ctiW("unusual.now"), title: ctiW("unusual.now.tip", { coins: ctiText(p.now) }) }],
    legend: [{ look: "s2", name: ctiW("legend.bin") }, { look: "cut", name: ctiW("legend.now") }] });
}

function ctiUnusualRows(d, view) {
  const p = ctiPast(d, view);
  const rows = CTI_PERCENTILES.map((n) => ({ n, v: p.past[Math.min(p.past.length - 1, Math.max(0, Math.ceil(n / 100 * p.past.length) - 1))] }));
  if (p.now != null) rows.push({ n: 100 - p.above, v: p.now, now: true });
  return rows;
}

function ctiUnusualColumns() {
  return [
    { key: "n", label: ctiW("unusual.percentile"), num: true, value: (r) => r.n,
      cell: (r) => (r.now ? `<b>${esc(ctiW("unusual.now"))}</b> ` : "") + esc(ctiW("unusual.p", { n: r.n })) },
    { key: "v", label: ctiW("unusual.reading"), num: true, value: (r) => r.v, cell: (r) => ctiGold(r.v) },
  ];
}


const ctiMove = (sd) => `${Math.round((Math.exp(sd) - 1) * 100)}%`;
const ctiVolatility = (d, view) => d.volatility.filter(([t]) => t >= view.from && t <= view.to);

function ctiVolatilitySvg(d, view, w) {
  const pts = ctiVolatility(d, view);
  const values = pts.map(([, sd]) => (Math.exp(sd) - 1) * 100);
  return ckPlotSvg({ id: "cti-volatility", width: w, high: CTI_PLOT * 0.7, x: { ...view, ticks: timeScale(view.from, view.to, w).ticks },
    y: { ...ckAxis(0, Math.max(...values)), label: (v) => `${num(v)}%` },
    hatch: ckEmpty(d.scans.map((s) => s.t), view),
    legend: [{ look: "line", name: ctiW("volatility.table.move"), tip: ctiW("volatility.line") }, { look: "dot", name: ckW("legend.scan") }, ckNoScanLegend()],
    lines: [{ points: ckBroken(pts.map(([t, sd]) => ({ t, v: (Math.exp(sd) - 1) * 100 }))).map((p) => ({ x: p.t, v: p.v })), fade: ctiFade(d) }],
    dots: pts.map(([t, sd]) => ({ x: t, v: (Math.exp(sd) - 1) * 100, title: ctiW("volatility.point", { when: pvWhen(t), change: ctiMove(sd) }) })) });
}


function ctiTile(id, title, age, body) {
  const views = CTI_VIEWS[id] || [], view = views.length ? ckViewOf(`cti-${id}`, views) : null;
  return ckPanelHtml({ id: `cti-${id}`, icon: CTI_ICONS[id], title, latest: age, views, view, body: body(view) });
}
const CTI_ICONS = { history: "inv_misc_note_01", depth: "inv_misc_bag_08", sales: "inv_misc_coin_02", unusual: "inv_misc_questionmark",
  volatility: "spell_holy_sealofwisdom" };
const ctiPlot = (what, time) => `<div class="tc-box"><div class="cti-plot${time ? " ck-drag" : ""}" data-cti-plot="${what}">${time ? '<div class="ck-pick" hidden></div>' : ""}</div></div>`;

function ctiBodyHtml(d) {
  const view = cthView(), now = d.now;
  const head = `<h3 class="cti-name">${ckItemHtml({ ...d, key: cti.item })}${d.pooled ? ` <small class="muted">${esc(ctiW("pooled.mark"))}</small>` : ""}</h3>${
    d.pooled ? `<p class="muted cti-note">${esc(ctiW("pooled"))}</p>` : ""}`;
  const busy = d.summarising ? `<p class="muted cti-note">${esc(ctiW("summarising"))}</p>` : "";
  if (!d.seen) return `${head}${busy}<p class="cth-empty">${esc(ctiW("never"))}</p><p class="muted cth-flavour">${esc(ctiW("never.flavour"))}</p>`;
  const newest = d.scans.length ? d.scans[d.scans.length - 1].t : null;
  const age = cthRestsOn(ctiW, "history.age", newest, now);
  const history = ctiTile("history", ctiW("history"), age, (v) => {
    if (v === "table") return ckTable({ id: "cti-history", columns: ctiHistoryColumns(now), rows: ctiShown(d, view), sort: { key: "when", down: true } });
    return ctiPlot(`history-${v}`, true);
  });
  const depth = ctiTile("depth", ctiW("depth"), cthRestsOn(ctiW, "depth.age", d.depth?.t, now), (v) => {
    if (!d.depth) return `<p class="muted">${esc(ctiW("depth.none"))}</p>`;
    const notes = ctiDepthNotes(d);
    if (v === "table") return `${ckTable({ id: "cti-depth", columns: ctiDepthColumns(), rows: ctiLadder(d.depth).steps, sort: { key: "unit", down: false } })}${notes}`;
    return `${ctiPlot(`depth-${v}`, false)}${notes}`;
  });
  const sales = ctiTile("sales", ctiW("sales"), csaAge(d), (v) => csaTileBody(d, v));
  const p = ctiPast(d, view);
  const unusual = ctiTile("unusual", ctiW("unusual"), age, (v) => {
    if (p.now == null || p.past.length < CTI_UNUSUAL_LEAST) return `<p class="muted">${esc(ctiW("unusual.few", { n: p.past.length }))}</p>`;
    if (v === "table") return `${ctiUnusualLine(p)}${ckTable({ id: "cti-unusual", columns: ctiUnusualColumns(), rows: ctiUnusualRows(d, view), sort: { key: "n", down: false } })}`;
    return `${ctiUnusualLine(p)}${ctiPlot("unusual-chart", false)}`;
  });
  const vol = ctiVolatility(d, view);
  const volatility = ctiTile("volatility", ctiW("volatility"), age, (v) => {
    if (!vol.length) return `<p class="muted">${esc(ctiW("volatility.few"))}</p>`;
    if (v === "table") return ckTable({ id: "cti-volatility", rows: vol.map(([t, sd]) => ({ t, sd })), sort: { key: "when", down: true }, columns: [
      { key: "when", label: ctsW("when"), value: (r) => r.t, cell: (r) => `${esc(pvWhen(r.t))}${ckAgeTag(r.t, now)}` },
      { key: "sd", label: ctiW("volatility.table.move"), num: true, value: (r) => r.sd, cell: (r) => esc(ctiMove(r.sd)) }] });
    return ctiPlot("volatility-chart", true);
  });
  return `${head}${busy}${ctiPriceLine(d)}${ctiFactsLine(d)}<div class="cti-tiles">${history}${depth}${sales}${unusual}</div>
    <h4 class="cth-sub">${esc(ctiW("more"))}</h4><div class="cti-tiles">${volatility}<p class="muted cti-later">${esc(ctiW("more.later"))}</p></div>`;
}

function ctiPanelHtml() {
  ctiLoad();
  const find = `<div class="cti-find"><label class="cth-field" title="${esc(ctiW("find.tip"))}"><span class="cth-label">${esc(ctiW("find"))}</span>
    <input type="search" class="cti-find-field" id="cti-find" autocomplete="off" placeholder="${esc(ctiW("find.placeholder"))}" value="${esc(cti.find)}"></label>
    <div class="cti-found" id="cti-found">${ctiFoundHtml()}</div></div>`;
  let body;
  if (!cti.item) body = `<p class="cth-empty">${esc(ctiW("pick"))}</p><p class="muted cth-flavour">${esc(ctiW("pick.flavour"))}</p>`;
  else if (!cti.data) body = `<p class="muted">${esc(cti.failed ? cthW("failed") : cthW("loading"))}</p>`;
  else body = ctiBodyHtml(cti.data);
  return `<section class="ck-panel cti">${find}${body}</section>`;
}

function ctiDraw() {
  const d = cti.data;
  if (!d) return;
  const view = cthView();
  for (const host of $("counting").querySelectorAll(".cti-plot")) {
    const w = Math.max(200, Math.floor(host.clientWidth)), what = host.dataset.ctiPlot;
    const draw = { "history-chart": () => ctiHistorySvg(d, view, w), "history-diagram": () => ctiRangeSvg(d, view, w),
      "depth-diagram": () => ctiLadderSvg(d, w), "depth-chart": () => ctiCostSvg(d, w), "unusual-chart": () => ctiHistogramSvg(d, view, w),
      "volatility-chart": () => ctiVolatilitySvg(d, view, w) }[what] || (what.startsWith("sales-") && (() => csaDraw(d, what, view, w)));
    if (!draw) continue;
    if (host.classList.contains("ck-drag")) {
      host.dataset.from = view.from;
      host.dataset.to = view.to;
    }
    setHtml(host, `${draw()}${host.classList.contains("ck-drag") ? '<div class="ck-pick" hidden></div>' : ""}`);
  }
}

function ctiClick(e) {
  const b = e.target.closest?.("button[data-cti-item]");
  if (!b) return false;
  ctiOpen(b.dataset.ctiItem);
  return true;
}

$("counting").addEventListener("input", (e) => { if (e.target.id === "cti-find") ctiFind(e.target.value); });
