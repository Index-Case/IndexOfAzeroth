// The Index of Azeroth. Copyright 2026 Index Case <indexofazeroth@pm.me>. PolyForm Strict 1.0.0, see LICENSE.md.
"use strict";

const CTM_W = wordsOf("page.counting.market"), CSA_W = wordsOf("page.counting.sales");
const ctmW = (key, fill) => fillWords(CTM_W[key], fill) ?? "";
const csaW = (key, fill) => fillWords(CSA_W[key], fill) ?? "";
const CTM_VIEWS = ["diagram", "chart", "table"];
const CTM_TREE = 440;
const CTM_BARS_MOST = 25;
const CTM_MOVERS = 8;
const CTM_TABLE_MOST = 300;
const CTM_AGAIN_MS = 3000;
const CTM_ICON = "inv_misc_coin_02";
const ctm = { data: null, asked: null, failed: false, path: [], again: 0, profit: false };

const ctmUnits = (n) => (n >= 10 ? num(n) : n >= 1 ? n.toFixed(1) : n.toFixed(2));
const ctmChange = (c) => `${c >= 0 ? "+" : "−"}${Math.round(Math.abs(c) * 100)}%`;
const ctmState = (s, uncertain) => (!s ? "" : uncertain ? ctiW("state.uncertain", { state: ctiW(`state.${s}`) }) : ctiW(`state.${s}`));
function ctmHeldTip(d, s, ranged) {
  const got = d.holds?.[ranged ? `${s} sure` : s];
  return got ? ctiW("state.held.tip", { state: ctiW(`state.${s}`), n: Math.round(got.same * 100) }) : ctiW("state.held.none", { state: ctiW(`state.${s}`) });
}
const ctmGoldText = (copper) => moneyText(copper >= 10000 ? Math.round(copper / 10000) * 10000 : Math.round(copper));


function ctmLoad(force = false) {
  if (!cth.data) return;
  const asked = `house=${encodeURIComponent(cth.data.house || "")}`;
  const asks = cthAsks(ctm, asked, force);
  if (!asks) return;
  if (asks === "new") ctm.path = [];
  getJson(`/api/counting/market?${asked}`, { key: "/api/counting/market", force: true })?.then((d) => {
    if (asked !== ctm.asked) return;
    ctm.data = ctmRows(d);
    ctm.failed = false;
    clearTimeout(ctm.again);
    if (d.summarising && cth.open) ctm.again = setTimeout(() => ctmLoad(true), CTM_AGAIN_MS);
    renderCounting();
  }, () => { ctm.failed = true; renderCounting(); });
}

function ctmRows(d) {
  d.rows = d.items.map((a) => {
    const r = Object.fromEntries(d.columns.map((c, i) => [c, a[i]]));
    r.gold = r.day != null && r.price ? r.day * r.price : 0;
    r.goldDay = r.profit != null && r.dayCraft != null ? r.profit * r.dayCraft : null;
    r.cls = (r.sub || "").split(".")[0];
    return r;
  });
  return d;
}


function ctmName(d, key) {
  return (key.includes(".") ? d.subs[key] : d.classes[key]) || ctmW("other");
}

function ctmUnder(d) {
  const [cls, sub] = ctm.path;
  return d.rows.filter((r) => (cls == null || r.cls === cls) && (sub == null || r.sub === sub));
}

function ctmChildren(d) {
  const rows = ctmUnder(d), [cls, sub] = ctm.path;
  if (sub != null) return rows.map((r) => ({ key: `i:${r.item}`, name: r.name || r.item, gold: r.gold, state: r.state,
    uncertain: r.uncertain, change: r.change, row: r }));
  const by = cls == null ? (r) => r.cls : (r) => r.sub, counts = new Map();
  for (const r of rows) counts.set(by(r), (counts.get(by(r)) || 0) + 1);
  return [...counts].map(([k, n]) => {
    const g = d.groups[k] || {};
    return { key: `${cls == null ? "c" : "s"}:${k}`, name: ctmName(d, k), gold: g.gold || 0, state: g.state, uncertain: g.uncertain,
      change: g.change, items: n };
  });
}

function ctmTip(c) {
  const lines = [c.name, c.gold ? ctmW("tile.gold", { coins: moneyText(Math.round(c.gold)) }) : ctmW("tile.gold.none"),
    c.state ? ctmW("tile.state", { state: ctmState(c.state, c.uncertain), change: ctmChange(c.change) }) : ctmW("tile.state.none")];
  if (c.state && ctm.data) lines.push(ctmHeldTip(ctm.data, c.state, !!c.row));
  if (c.items != null) lines.push(wordCount("page.counting.market.tile.items", c.items));
  if (c.row) {
    const r = c.row;
    if (r.price) lines.push(ctmW("tile.price", { coins: moneyText(Math.round(r.price)) }));
    if (r.day != null) lines.push(ctmW("tile.sold", { n: ctmUnits(r.day), low: ctmUnits(r.dayLow), high: ctmUnits(r.dayHigh) }));
    lines.push(ctmW("tile.open"));
  }
  return lines.join("\n");
}


function ctmRulesHtml(d) {
  const r = d.rules || {}, n = 3;
  const style = r.style === "commodity" ? ctmW("rules.commodity") : r.style === "stack" ? ctmW("rules.stack", { n }) : ctmW("rules.style.none");
  const bids = r.bids === true ? ctmW("rules.bids") : r.bids === false ? ctmW("rules.no-bids", { n }) : ctmW("rules.bids.none");
  const longest = r.longest ? ctmW("rules.longest", { span: roughSpan(r.longest) }) : ctmW("rules.longest.none");
  const dep = r.deposit ? Object.values(r.deposit).sort((a, b) => b.seen - a.seen)[0] : null;
  const paid = dep ? [crtW("rules.deposit.read", { coins: moneyText(dep.deposit), units: num(dep.units), name: dep.name || "" })] : [];
  const items = [style, bids, longest, ...(d.fees ? cthFeesLines(d.fees) : []), ...paid];
  return `<div class="ctm-rules"><h4 class="cth-sub">${esc(ctmW("rules"))}</h4><ul>${items.map((t) => `<li>${esc(t)}</li>`).join("")}</ul></div>`;
}

function ctmNotesHtml(d) {
  const pairs = d.pairs ? ctmW("pairs", { n: d.pairs, short: d.short }) : ctmW("pairs.none");
  return `<div class="ctm-notes"><p>${esc(ctmW("estimate"))}</p><p>${esc(ctmW("fast"))}</p><p class="muted">${esc(pairs)}</p></div>`;
}

function ctmProfitHtml() {
  return `<button type="button" class="key small" data-ctm-profit aria-pressed="${ctm.profit}" title="${esc(ctmW("profit.order.tip"))}">${esc(ctmW("profit.order"))}</button>`;
}

function ctmCrumbsHtml(d) {
  const [cls, sub] = ctm.path, steps = [["", ctmW("crumb.all")]];
  if (cls != null) steps.push([cls, ctmName(d, cls)]);
  if (sub != null) steps.push([sub, ctmName(d, sub)]);
  return `<nav class="ctm-crumbs">${steps.map(([k, name], i) => (i === steps.length - 1 ? `<b>${esc(name)}</b>`
    : `<button type="button" class="key small" data-ctm-up="${i}" title="${esc(ctmW("crumb.tip", { name }))}">${esc(name)}</button>`)).join(`<span class="ctm-sep">›</span>`)}
    <small class="muted">${esc(ctmW("drill.tip"))}</small></nav>`;
}


const ctmStateLegend = () => [...Object.keys(CK_TONES).map((s) => ({ look: `tone-${ckToneOf(s)}`, name: ctmState(s), tip: ctiW("state.tip") })),
  ...["tone-none", "dim-none"].map((look) => ({ look, name: ctiW("state.none") }))];

function ctmTreeSvg(d, w) {
  const kids = ctmChildren(d).filter((c) => c.gold > 0);
  return ckTreemapSvg({ id: "ctm-tree", width: w, high: CTM_TREE, legend: ctmStateLegend(), tiles: kids.map((c) => ({ v: c.gold, name: c.name,
    word: c.state ? `${ctmState(c.state, c.uncertain)} ${ctmChange(c.change)}` : "", tone: ckToneOf(c.state), dim: !c.state, key: c.key, title: ctmTip(c), tip: c.row?.item })) });
}

function ctmSizeSvg(d, w) {
  const kids = ctmChildren(d).filter((c) => c.gold > 0).sort((a, b) => b.gold - a.gold).slice(0, CTM_BARS_MOST);
  return ckHBarsSvg({ id: "ctm-size", width: w, label: ctmGoldText, legend: ctmStateLegend(), rows: kids.map((c) => ({ name: c.name, v: c.gold,
    tone: ckToneOf(c.state), key: c.key, title: ctmTip(c), tip: c.row?.item })) });
}

const ctmMoved = (d) => ctmUnder(d).filter((r) => r.change != null && r.change !== 0 && r.price && r.steps >= 2);

function ctmMoversSvg(d, w) {
  const moved = ctmMoved(d).sort((a, b) => b.change - a.change);
  const rows = [...moved.filter((r) => r.change > 0).slice(0, CTM_MOVERS), ...moved.filter((r) => r.change < 0).slice(-CTM_MOVERS)];
  return ckHBarsSvg({ id: "ctm-movers", width: w, two: true, label: ctmChange, legend: ctmStateLegend(), rows: rows.map((r) => ({ name: r.name || r.item, v: r.change,
    tone: ckToneOf(r.state), key: `i:${r.item}`, tip: r.item,
    title: ctmW("chart.movers.row", { name: r.name || r.item, change: ctmChange(r.change), coins: moneyText(Math.round(r.price / (1 + r.change))) }) })) });
}

function ctmGoldDayTip(r) {
  const carries = r.dayCraft >= 1 ? ctmW("cell.goldday.rate") : ctmW("cell.goldday.profit");
  return [ctmW("cell.goldday.top", { coins: moneyText(Math.round(r.goldDay)) }),
    ctmW("cell.goldday.work", { profit: moneyText(Math.round(r.profit)), n: ctmUnits(r.dayCraft) }),
    ctmW("cell.goldday.rare"), carries].join("\n");
}

function ctmColumns(now, crafts = true, rate = true) {
  const pooled = (r) => String(r.item).endsWith(":pooled");
  const flags = (r) => [pooled(r) && ["pooled", "flag.pooled"], r.vendor && ["vendor", "flag.vendor"], r.bait && ["bait", "flag.bait"],
    r.reset && ["reset", "flag.reset"]].filter(Boolean)
    .map(([k, w]) => ` <span class="ctm-flag ${k}" title="${esc(ctmW(`${w}.tip`))}">${esc(ctmW(w))}</span>`).join("");
  const name = (r) => `${ckItemHtml({ ...r, key: r.item }, { open: `data-ctm-item="${esc(r.item)}"` })}${flags(r)}`;
  const thin = `<span class="muted" title="${esc(ctmW("cell.thin.tip"))}">${esc(ctmW("cell.thin"))}</span>`;
  const sold = (r) => {
    if (r.day == null) return `<span class="muted" title="${esc(ctmW("cell.sold.none.tip"))}">${esc(ctmW("cell.sold.none"))}</span>`;
    const range = `<small class="cti-range ctm-under">${esc(ctmUnits(r.dayLow))} to ${esc(ctmUnits(r.dayHigh))}</small>`;
    const prior = r.from === "prior" ? ` <small class="muted" title="${esc(ctmW("cell.sold.prior.tip"))}">${esc(ctmW("cell.sold.prior"))}</small>` : "";
    const reset = r.resetUnits ? ` title="${esc(ctmW("cell.sold.reset", { units: num(r.resetUnits) }))}"` : "";
    return `<span${reset}>${esc(ctmUnits(r.day))}</span> ${range}${prior}`;
  };
  const supply = (r) => {
    if (r.day == null || !r.listed) return "";
    if (!r.wall) return `<span class="muted">${esc(ctmW("cell.supply.none"))}</span>`;
    const days = r.wall / Math.max(r.day, 1e-9);
    return days > 365 ? esc(ctmW("cell.supply.long")) : esc(ctmUnits(days));
  };
  const craft = crafts ? [
    { key: "profit", label: ctmW("col.profit"), tip: ctmW("col.profit.tip"), num: true, value: (r) => r.profit,
      cell: (r) => (r.profit == null ? "" : ckGold(r.profit)) },
    { key: "margin", label: ctmW("col.margin"), tip: ctmW("col.margin.tip"), num: true, value: (r) => r.margin,
      cell: (r) => (r.margin == null ? "" : esc(ctmChange(r.margin))) },
    ...(rate ? [{ key: "goldDay", label: ctmW("col.goldday"), tip: ctmW("col.goldday.tip"), num: true,
      value: (r) => r.goldDay,
      cell: (r) => (r.profit == null ? "" : r.goldDay == null
        ? `<span class="muted" title="${esc(ctmW("cell.goldday.none.tip"))}">${esc(ctmW("cell.goldday.none"))}</span>`
        : `<span title="${esc(ctmGoldDayTip(r))}">${ckGold(Math.round(r.goldDay))}</span>`) }] : []),
  ] : [];
  return [
    { key: "item", label: ctmW("col.item"), value: (r) => (r.name || r.item).toLowerCase(), cell: name },
    { key: "state", label: ctmW("col.state"), value: (r) => r.change, cell: (r) => (r.state ? `<span class="ctm-state ck-tone-${ckToneOf(r.state)}"
      title="${esc(ctmHeldTip(ctm.data, r.state, true))}">${esc(ctmState(r.state, r.uncertain))}</span>` : "") },
    { key: "price", label: ctmW("col.price"), num: true, value: (r) => r.price, cell: (r) => (r.price ? ckGold(Math.round(r.price)) : thin) },
    ...craft,
    { key: "change", label: ctmW("col.change"), tip: ctmW("col.change.tip"), num: true, value: (r) => r.change, cell: (r) => (r.change == null ? "" : esc(ctmChange(r.change))) },
    { key: "listed", label: ctmW("col.listed"), tip: ctmW("col.listed.tip"), num: true, value: (r) => r.listed,
      cell: (r) => (r.listed ? `<span title="${esc(ctmW("cell.listed.tip", { n: ctmUnits(r.average) }))}">${num(r.listed)}</span>`
        : `<span class="muted" title="${esc(ctmW("cell.unlisted.tip"))}">${esc(ctmW("cell.unlisted"))}</span>`) },
    { key: "sold", label: ctmW("col.sold"), tip: ctmW("col.sold.tip"), num: true, value: (r) => r.day, cell: sold },
    { key: "supply", label: ctmW("col.supply"), tip: ctmW("col.supply.tip"), num: true, value: (r) => (r.day && r.wall ? r.wall / r.day : null), cell: supply },
    { key: "auctions", label: ctmW("col.auctions"), num: true, value: (r) => r.auctions, cell: (r) => (r.auctions ? num(r.auctions) : "") },
    { key: "cheapest", label: ctmW("col.cheapest"), num: true, value: (r) => r.cheapest, cell: (r) => (r.cheapest != null ? ckGold(Math.round(r.cheapest)) : "") },
    { key: "age", label: ctmW("col.age"), value: (r) => r.seen, cell: (r) => (r.seen ? ckAgeTag(r.seen, now) : "") },
    { key: "confidence", label: ctmW("col.confidence"), tip: ctmW("col.confidence.tip"), value: (r) => r.steps,
      cell: (r) => (r.steps != null ? ckConfidence({ steps: r.steps, scans: r.scans, newest: r.seen }, now) : "") },
  ];
}

function ctmPanelHtml() {
  ctmLoad();
  const d = ctm.data;
  const busy = d?.summarising ? `<p class="muted cti-note">${esc(ctmW("summarising"))}</p>` : "";
  let body, views = [], latest = "";
  if (!d) body = `<p class="muted">${esc(ctm.failed ? cthW("failed") : ctmW("loading"))}</p>`;
  else if (!d.made) body = `${busy}<p class="cth-empty">${esc(ctmW("none"))}</p><p class="muted cth-flavour">${esc(ctmW("none.flavour"))}</p>`;
  else {
    views = CTM_VIEWS;
    latest = cthRestsOn(ctmW, "latest", d.newest, d.now);
    const view = ckViewOf("ctm-market", CTM_VIEWS), under = ctmUnder(d);
    const thin = under.filter((r) => !r.price).length;
    const priced = under.some((r) => r.gold > 0);
    const hasProfit = !!d.columns?.includes("profit"), hasRate = !!d.columns?.includes("dayCraft");
    const byProfit = hasProfit && hasRate && ctm.profit;
    let shown;
    if (view === "table") {
      const rows = (byProfit
        ? [...under].sort((a, b) => (b.goldDay ?? -Infinity) - (a.goldDay ?? -Infinity) || b.gold - a.gold)
        : [...under].sort((a, b) => b.gold - a.gold || (b.listed || 0) - (a.listed || 0))).slice(0, CTM_TABLE_MOST);
      const more = under.length > rows.length ? `<p class="muted cti-note">${esc(ctmW(byProfit ? "table.more.profit" : "table.more", { n: num(rows.length) }))}</p>` : "";
      const left = byProfit && d.crafts?.left ? `<p class="muted cti-note">${esc(wordCount("page.counting.market.profit.left", d.crafts.left))}</p>` : "";
      const leftRate = byProfit && d.crafts?.leftSales ? `<p class="muted cti-note">${esc(wordCount("page.counting.market.profit.left.sales", d.crafts.leftSales))}</p>` : "";
      shown = `${more}<div class="ctm-table">${ckTable({ id: "ctm-market", columns: ctmColumns(d.now, hasProfit, hasRate), rows, key: (r) => r.item, sort: { key: "sold", down: true } })}</div>${left}${leftRate}`;
    } else if (!priced) shown = `<p class="muted">${esc(ctmW("empty"))}</p>`;
    else if (view === "chart") {
      const many = ctmChildren(d).filter((c) => c.gold > 0).length > CTM_BARS_MOST ? `<p class="muted cti-note">${esc(ctmW("chart.size.more", { n: CTM_BARS_MOST }))}</p>` : "";
      const moved = ctmMoved(d).length > 0;
      shown = `<h4 class="cth-sub">${esc(ctmW("chart.size"))}</h4><div class="ctm-plot" data-ctm-plot="size"></div>${many}
        <h4 class="cth-sub">${esc(ctmW("chart.movers"))}</h4>${moved ? '<div class="ctm-plot" data-ctm-plot="movers"></div>' : `<p class="muted">${esc(ctmW("chart.movers.none"))}</p>`}`;
    } else {
      shown = `<div class="ctm-plot" data-ctm-plot="tree"></div><p class="ck-legend">${esc(ctmW("diagram.key"))}</p>${
        thin ? `<p class="muted cti-note">${esc(wordCount("page.counting.market.thin", thin))}</p>` : ""}`;
    }
    body = `${busy}${ctmRulesHtml(d)}${ctmCrumbsHtml(d)}${shown}${ctmNotesHtml(d)}`;
    return ckPanelHtml({ id: "ctm-market", icon: CTM_ICON, title: ctmW("title"), latest, views, view, body, extra: hasProfit && hasRate ? ctmProfitHtml() : "" });
  }
  return ckPanelHtml({ id: "ctm-market", icon: CTM_ICON, title: ctmW("title"), latest, views, view: null, body });
}

function ctmDraw() {
  const d = ctm.data;
  if (!d?.made) return;
  for (const host of $("counting").querySelectorAll(".ctm-plot")) {
    const w = Math.max(240, Math.floor(host.clientWidth)), what = host.dataset.ctmPlot;
    const draw = { tree: () => ctmTreeSvg(d, w), size: () => ctmSizeSvg(d, w), movers: () => ctmMoversSvg(d, w) }[what];
    if (draw) setHtml(host, draw());
  }
}

function ctmOpenItem(item) {
  cth.tab = "item";
  ctiOpen(item);
}

function ctmClick(e) {
  const profit = e.target.closest?.("button[data-ctm-profit]");
  if (profit) {
    ctm.profit = !ctm.profit;
    ckSorts["ctm-market"] = ctm.profit ? { key: "goldDay", down: true } : { key: "sold", down: true };
    if (ctm.profit) ckStore("view.ctm-market", "table");
    renderCounting();
    return true;
  }
  const tile = e.target.closest?.("[data-ck-tile]"), up = e.target.closest?.("button[data-ctm-up]"), item = e.target.closest?.("button[data-ctm-item]");
  if (item) {
    ctmOpenItem(item.dataset.ctmItem);
    return true;
  }
  if (up) {
    ctm.path = ctm.path.slice(0, +up.dataset.ctmUp);
    renderCounting();
    return true;
  }
  if (!tile?.closest(".ctm-plot")) return false;
  const [kind, key] = [tile.dataset.ckTile.slice(0, 1), tile.dataset.ckTile.slice(2)];
  if (kind === "i") ctmOpenItem(key);
  else {
    ctm.path = kind === "c" ? [key] : [ctm.path[0], key];
    renderCounting();
  }
  return true;
}


function csaFactHtml(d) {
  const f = d.sales?.figure;
  if (!f) return `<span class="muted" title="${esc(csaW("fact.none.tip"))}">${esc(csaW("fact.none"))}</span>`;
  const prior = f.from === "prior" ? ` <small class="muted" title="${esc(csaW("fact.prior.tip"))}">${esc(csaW("fact.prior"))}</small>` : "";
  return `${esc(csaW("fact", { n: ctmUnits(f.day), low: ctmUnits(f.low), high: ctmUnits(f.high) }))} ${ckConfidence({ steps: f.steps, scans: f.pairs }, d.now)}${prior}`;
}

const csaAge = (d) => cthRestsOn(csaW, "age", d.sales?.newest, d.now);

const CSA_DAYS = Array.from({ length: 7 }, (_, i) => new Date(2024, 0, 1 + i).toLocaleDateString([], { weekday: "short" }));

function csaColumns(now) {
  const units = (v) => (v == null ? "" : esc(ctmUnits(v)));
  return [
    { key: "when", label: csaW("col.when"), value: (r) => r.t, cell: (r) => `${esc(pvWhen(r.t))}${ckAgeTag(r.t, now)}${r.reset
      ? ` <span class="ctm-flag reset" title="${esc(csaW("reset.tip"))}">${esc(csaW("reset"))}</span>` : ""}` },
    { key: "gap", label: csaW("col.gap"), tip: csaW("col.gap.tip"), num: true, value: (r) => r.hours, cell: (r) => esc(roughSpan(r.hours * 3600)) },
    { key: "gone", label: csaW("col.gone"), tip: csaW("col.gone.tip"), num: true, value: (r) => r.units, cell: (r) => num(r.units) },
    { key: "share", label: csaW("col.share"), tip: csaW("col.share.tip"), num: true, value: (r) => r.share, cell: (r) => (r.share == null ? "" : `${Math.round(r.share * 100)}%`) },
    { key: "sold", label: csaW("col.sold"), num: true, value: (r) => r.sold, cell: (r) => units(r.sold) },
    { key: "expired", label: csaW("col.expired"), tip: csaW("col.expired.tip"), num: true, value: (r) => r.expired, cell: (r) => units(r.expired) },
    { key: "cancelled", label: csaW("col.cancelled"), tip: csaW("col.cancelled.tip"), num: true, value: (r) => r.cancelled, cell: (r) => units(r.cancelled) },
  ];
}

const csaNotesHtml = () => `<div class="ctm-notes"><p>${esc(csaW("estimate"))}</p><p>${esc(csaW("fast"))}</p><p class="muted">${esc(csaW("limits"))}</p></div>`;

function csaTileBody(d, view) {
  const s = d.sales;
  if (!s || !s.pairs.length) return `<p class="muted">${esc(csaW("none"))}</p>${csaNotesHtml()}`;
  if (view === "table") return `${ckTable({ id: "csa-pairs", columns: csaColumns(d.now), rows: s.pairs, sort: { key: "when", down: true } })}${csaNotesHtml()}`;
  if (view === "diagram") {
    return `<div class="csa-week"><h4 class="cth-sub">${esc(csaW("heat.sold"))}</h4>${ctiPlot("sales-sold", false)}<p class="ck-legend">${esc(csaW("heat.sold.key"))}</p>
      <h4 class="cth-sub">${esc(csaW("heat.price"))}</h4>${ctiPlot("sales-price", false)}<p class="ck-legend">${esc(csaW("heat.price.key"))}</p>
      <p class="muted cti-note">${esc(csaW("heat.few"))}</p></div>${csaNotesHtml()}`;
  }
  return `${ctiPlot("sales-chart", true)}${csaNotesHtml()}`;
}

function csaChartSvg(d, view, w) {
  const days = d.sales.days.filter((x) => x.t >= view.from - CK_DAY && x.t <= view.to + CK_DAY), half = CK_DAY * 0.38;
  const thin = days.filter((x) => x.pairs <= 1).map((x) => ({ from: x.t - CK_DAY / 2, to: x.t + CK_DAY / 2 }));
  const empty = ckEmpty(d.sales.pairs.map((p) => p.t), view);
  const card = (x) => wordCount("page.counting.sales.chart.day", x.pairs, { day: x.day, n: ctmUnits(x.sold), low: ctmUnits(x.low), high: ctmUnits(x.high) });
  return ckPlotSvg({ id: "csa-chart", width: w, high: CTI_PLOT, x: { ...view, ticks: timeScale(view.from, view.to, w).ticks },
    y: { ...ckAxis(0, Math.max(1, ...days.map((x) => x.high))), label: (v) => ctmUnits(v) },
    hatch: [...empty, ...thin], legend: [{ look: "s2", name: csaW("legend.sold"), tip: csaW("legend.sold.tip") }, { look: "line", name: ckW("legend.range"), tip: csaW("legend.range.tip") },
      { look: "dot", name: csaW("legend.pairs") }, { look: "hollow", name: csaW("legend.pair") }, { look: "hatch", name: csaW("legend.thin") }],
    bars: days.map((x) => ({ x0: x.t - half, x1: x.t + half, v0: 0, v1: x.sold, series: 2, title: card(x) })),
    lines: days.map((x) => ({ points: [{ x: x.t, v: x.low }, { x: x.t, v: x.high }] })),
    dots: days.map((x) => ({ x: x.t, v: x.sold, hollow: x.pairs <= 1, title: card(x) })) });
}

function csaHeatSvg(d, what, w) {
  const hour = (h) => `${String(h).padStart(2, "0")}:00`;
  const cells = d.sales.heat[what].map((row, day) => row.map(([v, n], h) => {
    const at = { day: CSA_DAYS[day], hour: hour(h) };
    const title = v == null ? csaW("heat.cell.thin", { ...at, n })
      : what === "sold" ? csaW("heat.cell.sold", { ...at, n: ctmUnits(v), pairs: n }) : csaW("heat.cell.price", { ...at, share: `${Math.round(v * 100)}%`, scans: n });
    return { v, n, title };
  }));
  const legend = what === "price" ? [{ look: "heat-gain", name: csaW("legend.heat.above") }, { look: "heat-loss", name: csaW("legend.heat.below") },
    { look: "hatch", name: csaW("legend.heat.thin.price") }]
    : [{ look: "heat-level", name: csaW("legend.heat.sold"), tip: csaW("legend.heat.sold.tip") }, { look: "hatch", name: csaW("legend.heat.thin.sold") }];
  return ckHeatSvg({ id: `csa-${what}`, width: w, days: CSA_DAYS, cells, two: what === "price", legend });
}

function csaDraw(d, what, view, w) {
  if (!d.sales?.pairs.length) return "";
  return { "sales-chart": () => csaChartSvg(d, view, w), "sales-sold": () => csaHeatSvg(d, "sold", w),
    "sales-price": () => csaHeatSvg(d, "price", w) }[what]?.() ?? "";
}
