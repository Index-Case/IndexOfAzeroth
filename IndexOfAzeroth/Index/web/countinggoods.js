// The Index of Azeroth. Copyright 2026 Index Case <indexofazeroth@pm.me>. PolyForm Strict 1.0.0, see LICENSE.md.
"use strict";

const CYA_W = wordsOf("page.counting.auctions"), CGO_W = wordsOf("page.counting.goods");
const cyaW = (key, fill) => fillWords(CYA_W[key], fill) ?? "";
const cgoW = (key, fill) => fillWords(CGO_W[key], fill) ?? "";
const CYA_VIEWS = ["chart", "diagram", "table"], CGO_VIEWS = ["chart", "diagram", "table"];
const CYA_ICON = "inv_scroll_03", CGO_ICON = "inv_box_01";
const CYA_STEPS_MOST = 25;
const CYA_SMALL = 90;
const CYA_SMALL_MOST = 12;
const CGO_TREE = 420;
const CGO_TABLE_MOST = 400;
const CGO_PLACES = ["bags", "bank", "mail", "auctions", "warband"];
const cya = { data: null, asked: null, failed: false, item: null };
const cgo = { data: null, asked: null, failed: false, path: [] };


function cgLoad(state, url, force) {
  if (!cth.data) return;
  const asked = `house=${encodeURIComponent(cth.data.house || "")}`, kept = cthShow();
  const asks = cthAsks(state, asked, force, kept);
  if (!asks) return;
  if (asks === "new" && state.path) state.path = [];
  getJson(`${url}?${asked}&${kept}`, { key: url, force: true })?.then((d) => {
    if (!cthAnswered(state, asked, kept)) return;
    state.data = d;
    state.failed = false;
    renderCounting();
  }, () => { state.failed = true; renderCounting(); });
}

const cyaItemHtml = (r) => ckItemHtml({ ...r, key: r.key ?? r.item }, { open: `data-ctm-item="${esc(String(r.key ?? r.item))}"` });
const cgMuted = (text, tip) => `<span class="muted" title="${esc(tip)}">${esc(text)}</span>`;


function cyaNotesHtml(d) {
  const lines = d.characters.map((c) => cyaW("read", { name: c.name, ago: ago(c.at, d.now) }));
  if (d.characters.length && !d.auctions.length) lines.push(cyaW("read.none"));
  lines.push(cyaW(d.style === "commodity" ? "style.commodity" : d.style === "stack" ? "style.stack" : "style.none"));
  if (d.auctions.some((r) => r.scan != null && r.seen > r.scan)) lines.push(cyaW("scan.old"));
  const unknown = d.auctions.some((r) => r.under > 0 && r.deposit == null);
  return `<div class="ctm-notes">${lines.map((t) => `<p>${esc(t)}</p>`).join("")}${unknown ? `<p class="muted">${esc(cyaW("deposit"))}</p>` : ""}</div>`;
}

function cyaLeft(r, now) {
  if (r.sold) return "";
  if (r.ends != null && r.ends <= now) return cgMuted(cyaW("cell.ended"), cyaW("cell.ended.tip"));
  const band = r.band != null && CYA_W[`band.${r.band}`] ? cyaW(`band.${r.band}`) : "";
  const hours = r.ends != null ? cyaW("cell.hours", { n: Math.max(1, Math.round((r.ends - now) / 3600)) }) : "";
  return esc([band, hours].filter(Boolean).join(", "));
}

function cyaColumns(d) {
  const now = d.now, gold = (v) => ckGold(Math.round(v));
  const waiting = (r) => {
    if (r.sold) return cgMuted(cyaW("cell.sold"), cyaW("cell.sold.tip"));
    if (r.unit == null) return r.bid ? cgMuted(cyaW("cell.bid"), cyaW("cell.bid.tip")) : cgMuted(cyaW("cell.unpriced"), cyaW("cell.unpriced.tip"));
    if (r.scan == null) return cgMuted(cyaW("cell.unscanned"), cyaW("cell.unscanned.tip"));
    return null;
  };
  const other = (r) => waiting(r) ?? (r.other == null ? cgMuted(cyaW("cell.none"), cyaW("cell.none.tip")) : `${gold(r.other)}${ckAgeTag(r.scan, now)}`);
  const under = (r) => {
    if (waiting(r) != null || r.other == null) return "";
    return r.under > 0 ? `<span class="cya-under">${gold(r.under)}</span>` : cgMuted(cyaW("cell.no"), cyaW("cell.no.tip"));
  };
  const ahead = d.style === "commodity" ? "col.ahead.below" : "col.ahead.at";
  return [
    { key: "item", label: cyaW("col.item"), value: (r) => (r.name || String(r.item)).toLowerCase(), cell: cyaItemHtml },
    { key: "who", label: cyaW("col.who"), value: (r) => r.who?.toLowerCase() ?? null, cell: (r) => esc(r.who || "") },
    { key: "units", label: cyaW("col.units"), num: true, value: (r) => r.units, cell: (r) => num(r.units) },
    { key: "price", label: cyaW("col.price"), tip: cyaW("col.price.tip"), num: true, value: (r) => r.unit,
      cell: (r) => (r.unit == null ? waiting(r) || "" : `${gold(r.unit)}${ckAgeTag(r.at, now)}`) },
    { key: "other", label: cyaW("col.other"), tip: cyaW("col.other.tip"), num: true, value: (r) => r.other, cell: other },
    { key: "under", label: cyaW("col.under"), tip: cyaW("col.under.tip"), num: true, value: (r) => (r.sold ? null : r.under), cell: under },
    { key: "ahead", label: cyaW(ahead), tip: cyaW("col.ahead.tip"), num: true, value: (r) => r.ahead, cell: (r) => (r.ahead == null ? "" : num(r.ahead)) },
    { key: "match", label: cyaW("col.match"), tip: cyaW("col.match.tip"), num: true, value: (r) => r.match,
      cell: (r) => (r.match == null || !(r.under > 0) ? "" : r.deposit == null ? gold(r.match)
        : `<span title="${esc(cyaW("match.deposit.tip", { deposit: moneyText(r.deposit) }))}">${gold(r.match)}</span>`) },
    ckRepostsColumn((r) => r),
    { key: "left", label: cyaW("col.left"), tip: cyaW("col.left.tip"), value: (r) => r.ends, cell: (r) => cyaLeft(r, now) },
  ];
}

function cyaItems(d) {
  const seen = new Map();
  for (const r of d.auctions) if (!seen.has(r.key)) seen.set(r.key, r);
  return [...seen.values()];
}

function cyaLadderSvg(d, w) {
  const steps = d.ladders[cya.item] || [];
  const shown = steps.filter((s, i) => i < CYA_STEPS_MOST || s[3]);
  return ckHBarsSvg({ id: "cya-ladder", width: w, label: (v) => num(v), legend: [{ look: "tone-gain2", name: cyaW("legend.yours") },
    { look: "tone-flat", name: cyaW("legend.others") }], rows: shown.map(([unit, units, n, yours]) => ({
    name: yours ? cyaW("diagram.yours", { coins: moneyText(Math.round(unit)), units: num(yours) }) : moneyText(Math.round(unit)),
    v: units + yours, tone: yours ? "gain2" : "flat",
    title: [units ? wordCount("page.counting.auctions.diagram.step", n, { coins: moneyText(Math.round(unit)), units: num(units) }) : "",
      yours ? cyaW("diagram.step.yours", { units: num(yours) }) : ""].filter(Boolean).join("\n") })) });
}

function cyaDiagramHtml(d) {
  const items = cyaItems(d);
  if (!items.some((r) => r.key === cya.item)) cya.item = items.length ? items[0].key : null;
  const picks = items.map((r) => `<button type="button" class="key small" data-cya-item="${esc(r.key)}" data-tip="${esc(r.key)}" aria-pressed="${r.key === cya.item}">${
    esc(r.name || String(r.item))}</button>`).join("");
  const steps = (d.ladders[cya.item] || []).length;
  const more = steps > CYA_STEPS_MOST ? `<p class="muted cti-note">${esc(cyaW("diagram.more", { n: CYA_STEPS_MOST }))}</p>` : "";
  return `<div class="cya-picks"><span class="cth-label">${esc(cyaW("diagram.pick"))}</span>${picks}</div><div class="cg-plot" data-cg-plot="ladder"></div>${more}
    <p class="ck-legend">${esc(cyaW("diagram.key"))}</p>`;
}

function cyaSmallSvg(r, d, w) {
  const pts = r.history;
  const from = Math.min(r.seen, pts[0][0]), to = Math.max(d.now, pts[pts.length - 1][0]);
  const most = Math.max(1, ...pts.map((p) => p[1]));
  return ckPlotSvg({ id: `cya-small-${r.id}`, width: w, high: CYA_SMALL, x: { from, to, ticks: timeScale(from, to, w).ticks },
    y: { ...ckAxis(0, most, 3), label: num }, lines: [{ points: pts.map(([t, v]) => ({ x: t, v })) }],
    dots: pts.map(([t, v]) => ({ x: t, v, title: cyaW("chart.point", { when: pvWhen(t), n: num(v) }) })) });
}

function cyaChartHtml(d) {
  const up = d.auctions.filter((r) => r.history.length).slice(0, CYA_SMALL_MOST);
  if (!up.length) return `<p class="muted">${esc(cyaW("chart.none"))}</p>`;
  return `<h4 class="cth-sub">${esc(cyaW("chart.title"))}</h4><div class="cya-smalls">${up.map((r) => `<div class="cya-small"><h5 data-tip="${esc(r.key)}">${
    esc(cyaW("chart.title.one", { name: r.name || String(r.item), units: num(r.units), coins: moneyText(Math.round(r.unit)) }))} <small class="muted">${esc(r.who || "")}</small></h5>
    <div class="cg-plot" data-cg-plot="small" data-cya-id="${r.id}"></div></div>`).join("")}</div>${
    ckLegendHtml([{ look: "line", name: cyaW("legend.ahead") }, { look: "dot", name: ckW("legend.scan") }], new Set(["line", "dot"]))}<p class="ck-legend">${esc(cyaW("chart.from"))}</p>`;
}

function cyaPanelHtml() {
  cgLoad(cya, "/api/counting/auctions");
  const d = cya.data;
  let body, views = [], view = null, latest = "";
  if (!d) body = `<p class="muted">${esc(cya.failed ? cthW("failed") : cyaW("loading"))}</p>`;
  else if (!d.characters.length) {
    body = `<p class="cth-empty">${esc(cyaW("none"))}</p><p class="muted">${esc(cyaW("none.how"))}</p><p class="muted cth-flavour">${esc(cyaW("none.flavour"))}</p>`;
  } else {
    views = d.auctions.length ? CYA_VIEWS : [];
    view = ckViewOf("cya-auctions", CYA_VIEWS);
    latest = cthRestsOn(cyaW, "latest", d.listed, d.now);
    let shown = "";
    if (d.auctions.length) {
      shown = view === "table" ? `<div class="ctm-table">${ckTable({ id: "cya-auctions", columns: cyaColumns(d), rows: d.auctions, key: (r) => r.id, sort: { key: "under", down: true } })}</div>`
        : view === "diagram" ? cyaDiagramHtml(d) : cyaChartHtml(d);
    }
    body = `${cyaNotesHtml(d)}${shown}`;
  }
  return ckPanelHtml({ id: "cya-auctions", icon: CYA_ICON, title: cyaW("title"), latest, views, view, body });
}


const cgoPlaceWord = (where) => cgoW(`where.${where}`);
const cgoList = (parts) => (parts.length < 2 ? parts.join("") : `${parts.slice(0, -1).join(", ")} ${cgoW("where.and")} ${parts[parts.length - 1]}`);

function cgoPlacesText(at, counted = false) {
  const places = CGO_PLACES.filter((w) => at[w]);
  if (places.length === 1 && !counted) return cgoPlaceWord(places[0]);
  return cgoList(places.map((w) => cgoW("where.count", { n: num(at[w]), where: cgoPlaceWord(w) })));
}

function cgoSeenTip(list, now) {
  return list.filter(([, where, at]) => at && (where === "bank" || where === "mail"))
    .map(([who, where, at]) => cgoW(`where.seen.${where}`, { who, ago: ago(at, now) })).join("\n");
}

function cgoPlaceHtml(text, tip) {
  return tip ? `<span title="${esc(tip)}">${esc(text)}</span>` : esc(text);
}


const cgoWho = (r) => r.who ?? cgoW("warband");
const cgoClass = (d, cls) => d.classes[cls] || cgoW("other");
function cgoReadAt(d, who, where) {
  const c = d.characters.find((x) => x.who === who);
  return c?.places?.[where] ?? null;
}

function cgoUnder(d) {
  const [who, cls] = cgo.path;
  return d.rows.filter((r) => (who == null || cgoWho(r) === who) && (cls == null || r.cls === cls));
}

function cgoChildren(d) {
  const rows = cgoUnder(d).filter((r) => r.total), [who, cls] = cgo.path;
  const by = who == null ? (r) => ["w", cgoWho(r), cgoWho(r)] : cls == null ? (r) => ["c", r.cls, cgoClass(d, r.cls)]
    : (r) => ["i", r.key, r.name || r.key];
  const out = new Map();
  for (const r of rows) {
    const [kind, key, name] = by(r), k = `${kind}:${key}`;
    const t = out.get(k) || { key: k, name, v: 0, units: 0, other: 0, row: kind === "i" ? r : null };
    t.v += r.total;
    t.units += r.units;
    if (r.from !== "market") t.other += r.total;
    out.set(k, t);
  }
  return [...out.values()].map((t) => ({ ...t, dim: t.other > t.v / 2,
    title: [t.name, cgoW("tile.worth", { coins: moneyText(Math.round(t.v)) }), t.row ? cgoW("tile.units", { units: num(t.units) }) : ""].filter(Boolean).join("\n") }));
}

function cgoCrumbsHtml(d) {
  const [who, cls] = cgo.path, steps = [cgoW("crumb.all")];
  if (who != null) steps.push(who);
  if (cls != null) steps.push(cgoClass(d, cls));
  return `<nav class="ctm-crumbs">${steps.map((name, i) => (i === steps.length - 1 ? `<b>${esc(name)}</b>`
    : `<button type="button" class="key small" data-cgo-up="${i}" title="${esc(cgoW("crumb.tip", { name }))}">${esc(name)}</button>`)).join(`<span class="ctm-sep">›</span>`)}
    <small class="muted">${esc(cgoW("drill.tip"))}</small></nav>`;
}

function cgoTreeSvg(d, w) {
  return ckTreemapSvg({ id: "cgo-tree", width: w, high: CGO_TREE, legend: [{ look: "tone-flat", name: cgoW("legend.market") },
    { look: "dim-flat", name: cgoW("legend.other") }], tiles: cgoChildren(d).map((t) => ({ v: t.v, name: t.name,
    word: ctmGoldText(t.v), tone: "flat", dim: t.dim, key: t.key, title: t.title })) });
}

function cgoBars(d) {
  const rows = d.rows.filter((r) => r.total), byWho = new Map();
  for (const r of rows) {
    const m = byWho.get(cgoWho(r)) || new Map();
    m.set(r.cls, (m.get(r.cls) || 0) + r.total);
    byWho.set(cgoWho(r), m);
  }
  const order = [...new Set(rows.map((r) => r.cls))].sort((a, b) => cgoClass(d, a).localeCompare(cgoClass(d, b)));
  const series = ckSeriesOf(order.map((c) => cgoClass(d, c)));
  const bars = [...byWho].map(([who, m]) => ({ name: who, key: `w:${who}`, total: [...m.values()].reduce((s, v) => s + v, 0),
    parts: order.filter((c) => m.get(c)).map((c) => ({ series: series[cgoClass(d, c)], v: m.get(c), name: cgoClass(d, c),
      title: `${who}\n${cgoClass(d, c)}\n${cgoW("tile.worth", { coins: moneyText(Math.round(m.get(c))) })}` })) }));
  return { series, bars: bars.sort((a, b) => b.total - a.total) };
}


const cgoTooFew = (r) => !r.bound && String(r.key).includes(":") && r.from !== "market";

function cgoBoundValue(r) {
  if (r.unit == null) {
    const unknown = r.from === "unknown";
    return cgMuted(cgoW(unknown ? "cell.unknown" : "cell.none"), cgoW(unknown ? "cell.bound.unknown.tip" : "cell.bound.none.tip"));
  }
  return `${ckGold(Math.round(r.unit))} <small class="muted" title="${esc(cgoW("cell.bound.tip"))}">${esc(cgoW("cell.bound"))}</small>`;
}

function cgoUnboundPlaces(list) {
  const parts = list.map(([who, where]) => cgoW(`unbound.${where}`, { who }));
  return parts.length < 2 ? parts.join("") : `${parts.slice(0, -1).join(", ")} ${cgoW("unbound.and")} ${parts[parts.length - 1]}`;
}

function cgoColumns(d) {
  const now = d.now;
  const value = (r) => {
    if (r.bound) return cgoBoundValue(r);
    if (r.unit == null && cgoTooFew(r)) return cgMuted(cgoW("cell.few"), cgoW(r.from === "unknown" ? "cell.few.unknown.tip" : "cell.few.tip"));
    if (r.unit == null) return r.from === "unknown" ? cgMuted(cgoW("cell.unknown"), cgoW("cell.unknown.tip")) : cgMuted(cgoW("cell.none"), cgoW("cell.none.tip"));
    const tip = r.from !== "vendor" ? null : cgoTooFew(r) ? "cell.vendor.few.tip" : "cell.vendor.tip";
    return `${ckGold(Math.round(r.unit))}${tip ? ` <small class="muted" title="${esc(cgoW(tip))}">${esc(cgoW("cell.vendor"))}</small>` : ""}`;
  };
  const where = (r) => {
    const at = cgoReadAt(d, r.who, r.where);
    return `${cgoPlaceHtml(cgoPlaceWord(r.where), cgoSeenTip([[r.who, r.where, at]], now))}${at ? ckAgeTag(at, now) : ""}`;
  };
  return [
    { key: "item", label: cgoW("col.item"), value: (r) => (r.name || r.key).toLowerCase(), cell: (r) => cyaItemHtml({ ...r, item: r.key }) },
    { key: "who", label: cgoW("col.who"), value: (r) => cgoWho(r).toLowerCase(), cell: (r) => esc(cgoWho(r)) },
    { key: "where", label: cgoW("col.where"), tip: cgoW("col.where.tip"), value: (r) => CGO_PLACES.indexOf(r.where), cell: where },
    { key: "units", label: cgoW("col.units"), num: true, value: (r) => r.units, cell: (r) => num(r.units) },
    { key: "unit", label: cgoW("col.unit"), tip: cgoW("col.unit.tip"), num: true, value: (r) => r.unit, cell: value },
    { key: "total", label: cgoW("col.total"), num: true, value: (r) => r.total, cell: (r) => (r.total == null ? "" : ckGold(r.total, true)) },
    { key: "age", label: cgoW("col.age"), tip: cgoW("col.age.tip"), value: (r) => r.seen, cell: (r) => (r.seen ? ckAgeTag(r.seen, now) : "") },
    { key: "confidence", label: cgoW("col.confidence"), tip: cgoW("col.confidence.tip"), value: (r) => r.steps,
      cell: (r) => (r.steps != null ? ckConfidence({ steps: r.steps, scans: r.scans, newest: r.seen }, now) : "") },
  ];
}

function cgoNotesHtml(d) {
  const worth = d.rows.reduce((s, r) => s + (r.total || 0), 0);
  const atVendor = (bound) => d.rows.filter((r) => r.from === "vendor" && !!r.bound === bound).reduce((s, r) => s + r.total, 0);
  const vendor = atVendor(false), bound = atVendor(true);
  const kinds = (unknown) => new Set(d.rows.filter((r) => r.unit == null && (r.from === "unknown") === unknown).map((r) => r.key)).size;
  const unpriced = kinds(false), unknown = kinds(true), few = new Set(d.rows.filter(cgoTooFew).map((r) => r.key)).size;
  const lines = [`<p><b>${fillWords(esc(CGO_W.worth), { coins: ckGold(worth) })}</b> ${esc(cgoW("worth.note"))}</p>`];
  if (vendor) lines.push(`<p>${fillWords(esc(CGO_W.vendor), { coins: ckGold(vendor) })}</p>`);
  if (bound) lines.push(`<p>${fillWords(esc(CGO_W.bound), { coins: ckGold(bound) })}</p>`);
  if ((d.unbound || []).length) lines.push(`<p class="muted">${esc(cgoW("unbound", { places: cgoUnboundPlaces(d.unbound) }))}</p>`);
  if (few) lines.push(`<p>${esc(wordCount("page.counting.goods.few", few))}</p>`);
  if (unpriced) lines.push(`<p class="muted">${esc(wordCount("page.counting.goods.unpriced", unpriced))}</p>`);
  if (unknown) lines.push(`<p class="muted">${esc(wordCount("page.counting.goods.unknown", unknown))}</p>`);
  if (d.elsewhere) lines.push(`<p class="muted">${esc(wordCount("page.counting.goods.elsewhere", d.elsewhere))}</p>`);
  return `<div class="ctm-notes">${lines.join("")}</div>`;
}

function cgoPanelHtml() {
  cgLoad(cgo, "/api/counting/goods");
  const d = cgo.data;
  let body, views = [], view = null, latest = "";
  if (!d) body = `<p class="muted">${esc(cgo.failed ? cthW("failed") : cgoW("loading"))}</p>`;
  else if (!d.rows.length) {
    body = `<p class="cth-empty">${esc(cgoW("none"))}</p><p class="muted">${esc(cgoW("none.how"))}</p><p class="muted cth-flavour">${esc(cgoW("none.flavour"))}</p>`;
  } else {
    views = CGO_VIEWS;
    view = ckViewOf("cgo-goods", CGO_VIEWS);
    latest = cthRestsOn(cgoW, "latest", d.priced, d.now);
    let shown;
    if (view === "table") {
      const rows = [...d.rows].sort((a, b) => (b.total || 0) - (a.total || 0)).slice(0, CGO_TABLE_MOST);
      shown = `<div class="ctm-table">${ckTable({ id: "cgo-goods", columns: cgoColumns(d), rows, key: (r) => `${r.who}|${r.where}|${r.key}|${r.bound ? 1 : 0}`, sort: { key: "total", down: true } })}</div>`;
    } else if (view === "diagram") {
      shown = `${cgoCrumbsHtml(d)}<div class="cg-plot" data-cg-plot="tree"></div><p class="ck-legend">${esc(cgoW("diagram.key"))}</p>`;
    } else {
      shown = `<h4 class="cth-sub">${esc(cgoW("chart.key"))}</h4><div class="cg-plot" data-cg-plot="bars"></div>`;
    }
    body = `${cgoNotesHtml(d)}${shown}`;
  }
  return ckPanelHtml({ id: "cgo-goods", icon: CGO_ICON, title: cgoW("title"), latest, views, view, body });
}


function cgDraw() {
  for (const host of $("counting").querySelectorAll("[data-cg-plot]")) {
    const w = Math.max(240, Math.floor(host.clientWidth)), what = host.dataset.cgPlot;
    let svg = "";
    if (what === "ladder" && cya.data) svg = cyaLadderSvg(cya.data, w);
    else if (what === "small" && cya.data) {
      const r = cya.data.auctions.find((x) => String(x.id) === host.dataset.cyaId);
      svg = r ? cyaSmallSvg(r, cya.data, w) : "";
    } else if (what === "tree" && cgo.data) svg = cgoTreeSvg(cgo.data, w);
    else if (what === "bars" && cgo.data) {
      const { series, bars } = cgoBars(cgo.data);
      svg = ckStackHBarsSvg({ id: "cgo-bars", width: w, label: ctmGoldText, rows: bars, legend: ckSeriesLegend(series) });
    }
    setHtml(host, svg);
  }
}

function cgClick(e) {
  const pick = e.target.closest?.("button[data-cya-item]"), up = e.target.closest?.("button[data-cgo-up]");
  const tile = e.target.closest?.("[data-ck-tile]");
  if (pick) {
    cya.item = pick.dataset.cyaItem;
    renderCounting();
    return true;
  }
  if (up) {
    cgo.path = cgo.path.slice(0, +up.dataset.cgoUp);
    renderCounting();
    return true;
  }
  if (!tile || cth.tab !== "goods") return false;
  const key = tile.dataset.ckTile, kind = key.slice(0, 1), rest = key.slice(2);
  if (kind === "i") ctmOpenItem(rest);
  else {
    cgo.path = kind === "w" ? [rest] : [cgo.path[0], rest];
    if (kind === "w") ckStore("view.cgo-goods", "diagram");
    renderCounting();
  }
  return true;
}
