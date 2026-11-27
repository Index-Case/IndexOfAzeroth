// The Index of Azeroth. Copyright 2026 Index Case <indexofazeroth@pm.me>. PolyForm Strict 1.0.0, see LICENSE.md.
"use strict";

const CCR_W = wordsOf("page.counting.craft");
const ccrW = (key, fill) => fillWords(CCR_W[key], fill) ?? "";
const CCR_VIEWS = ["chart", "diagram", "table"];
const CCR_PANEL = "ccr-craft";
const CCR_ICON = "trade_blacksmithing";
const CCR_BARS_MOST = 30;
const CCR_TABLE_MOST = 300;
const CCR_NODE = 260;
const CCR_LINK = 56;
const CCR_LINE = 15;
const ccr = { data: null, asked: null, failed: false, every: false, picked: null };

const ccrMoney = (c) => `${c < 0 ? "−" : ""}${moneyText(Math.abs(Math.round(c)))}`;
const ccrShort = (c, up) => ccrMoney(Math.abs(c) >= 10000 ? Math[up ? "ceil" : "floor"](c / 10000) * 10000 : c);
function ccrFigure(f, r) {
  if (!f) return ccrMissing(r);
  return `${ckGold(f.mid, true)}<small class="cti-range ctm-under">${esc(ccrW("cell.range", { low: ccrShort(f.low, false), high: ccrShort(f.high, true) }))}</small>`;
}
function ccrMissing(r) {
  const why = r.missing.map((m) => {
    if (m === "product") return ccrW("cell.missing.product");
    const g = r.reagents.find((x) => x.item === m);
    return ccrW(g?.way == null ? "cell.missing.way" : "cell.missing.sell", { item: g?.name || m });
  });
  return `<span class="muted" title="${esc(why.join("\n"))}">${esc(ccrW("cell.missing"))}</span>`;
}


function ccrLoad(force = false) {
  if (!cth.data) return;
  const asked = `house=${encodeURIComponent(cth.data.house || "")}${ccr.every ? "&all=1" : ""}`, kept = cthShow();
  if (!cthAsks(ccr, asked, force, kept)) return;
  getJson(`/api/counting/craft?${asked}&${kept}`, { key: "/api/counting/craft", force: true })?.then((d) => {
    if (!cthAnswered(ccr, asked, kept)) return;
    ccr.data = d;
    ccr.failed = false;
    renderCounting();
  }, () => { ccr.failed = true; renderCounting(); });
}

function ccrPicked(d) {
  const rows = d.recipes;
  return rows.find((r) => r.spell === ccr.picked) || [...rows].sort((a, b) => (b.versus?.mid ?? -Infinity) - (a.versus?.mid ?? -Infinity))[0];
}


function ccrBarsSvg(d, w) {
  const rows = d.recipes.filter((r) => r.versus).sort((a, b) => b.versus.mid - a.versus.mid);
  const shown = rows.length > CCR_BARS_MOST ? [...rows.slice(0, CCR_BARS_MOST / 2), ...rows.slice(-CCR_BARS_MOST / 2)] : rows;
  const legend = [{ look: "tone-gain", name: ccrW("legend.gain") }, { look: "tone-loss", name: ccrW("legend.loss") }, { look: "whisker", name: ckW("legend.range") }];
  return ckHBarsSvg({ id: "ccr-bars", width: w, two: true, label: ccrMoney, legend, rows: shown.map((r) => ({ name: r.name, v: r.versus.mid,
    lo: r.versus.low, hi: r.versus.high, tone: r.versus.mid >= 0 ? "gain" : "loss", key: `r:${r.spell}`, tip: r.item,
    title: ccrW("chart.row", { name: r.name, coins: ccrMoney(r.versus.mid), low: ccrMoney(r.versus.low), high: ccrMoney(r.versus.high) }) })) });
}

function ccrTreeSvg(r, w) {
  const node = Math.min(CCR_NODE, Math.floor(w * 0.35)), x = node + CCR_LINK, room = Math.floor((w - x - 8) / TC_LABEL_CHAR);
  const cut = (s) => (s.length > room ? `${s.slice(0, Math.max(1, room - 1))}…` : s);
  const lines = r.reagents.map((g) => {
    const way = g.way === "vendor" ? ccrW("diagram.vendor", { each: ccrMoney(g.unit) })
      : g.way === "auction" ? ccrW("diagram.auction", { each: ccrMoney(g.unit), low: ccrMoney(g.low), high: ccrMoney(g.high) }) : ccrW("diagram.no-way");
    return [`${num(g.count)} × ${g.name}`, way, g.sell === "vendor" ? ccrW("diagram.sell.vendor", { each: ccrMoney(g.sellUnit) }) : null].filter(Boolean);
  });
  const tools = r.tools.map((t) => [ccrW("diagram.tool", { item: t.name })]);
  let y = 6;
  const tops = [...lines, ...tools].map((text) => {
    const top = y;
    y += text.length * CCR_LINE + 10;
    return top;
  });
  const high = Math.max(y, 80), mid = Math.round(high / 2), box = 54;
  const text = (t, at, top, sub, tool = false, tip = null) => `<text class="ccr-text${sub ? " sub" : ""}${tool ? " tool" : ""}" x="${at}" y="${top}"${
    tip ? ` data-tip="${tip}"` : ""}>${esc(t)}</text>`;
  const items = [...r.reagents.map((g) => g.item), ...r.tools.map((t) => t.item)];
  const right = [...lines, ...tools].map((t, i) => t.map((s, k) => text(cut(s), x, tops[i] + 12 + k * CCR_LINE, k > 0, i >= lines.length, k ? null : items[i])).join("")).join("");
  const links = lines.map((_, i) => `<path class="ccr-link" d="M${node} ${mid}C${node + CCR_LINK / 2} ${mid} ${x - CCR_LINK / 2} ${tops[i] + 8} ${x - 4} ${tops[i] + 8}"/>`).join("");
  const fit = Math.floor((node - 16) / TC_LABEL_CHAR), clip = (s) => (s.length > fit ? `${s.slice(0, Math.max(1, fit - 1))}…` : s);
  const value = r.value ? ccrW("diagram.value", { coins: ccrMoney(r.value.mid) }) : ccrW("cell.missing.product");
  const left = [r.itemName || r.name, ccrW("diagram.makes", { count: num(r.makes) }), value]
    .map((t, k) => text(clip(t), 10, mid - box / 2 + 17 + k * CCR_LINE, k > 0, false, k ? null : r.item)).join("");
  return `<svg class="ccr-tree" width="${w}" height="${high}" viewBox="0 0 ${w} ${high}"><rect class="ccr-node" x="0.5" y="${mid - box / 2}" width="${node}" height="${box}"/>${
    links}${left}${right}</svg>`;
}

function ccrColumns(d) {
  const now = d.now, before = !d.fees;
  const name = (r) => `${ckItemHtml({ ...r, key: r.item }, { open: `data-ccr-recipe="${r.spell}"` })}${
    r.makes > 1 ? ` <small class="muted">${esc(ccrW("cell.makes", { count: num(r.makes) }))}</small>` : ""}`;
  const who = (r) => `<small class="cti-range ctm-under"${r.who.length ? "" : ` title="${esc(ccrW("col.who.none.tip"))}"`}>${
    esc(r.who.length ? ccrW("cell.who", { names: r.who.join(", ") }) : ccrW("col.who.none"))}</small>`;
  const sold = (r) => {
    const p = r.product;
    if (p?.day == null) return `<span class="muted">${esc(ccrW("cell.sold.none"))}</span>`;
    return `${esc(ctmUnits(p.day))}<small class="cti-range ctm-under">${esc(ccrW("cell.range", { low: ctmUnits(p.dayLow), high: ctmUnits(p.dayHigh) }))}</small>`;
  };
  const by = (k) => (r) => r[k]?.mid ?? null;
  const rec = (r) => {
    const v = r.versus;
    if (!v) return ccrMissing(r);
    const craft = v.mid >= 0, m = ccrMoney;
    const lines = craft ? [ccrW("rec.craft.tip", { coins: m(v.mid), low: m(v.low), high: m(v.high) }), v.low < 0 && ccrW("rec.craft.loss", { coins: m(-v.low) })]
      : [ccrW("rec.sell.tip", { coins: m(-v.mid), low: m(-v.high), high: m(-v.low) }), v.high > 0 && ccrW("rec.sell.loss", { coins: m(v.high) })];
    return `<span title="${esc(lines.filter(Boolean).join("\n"))}">${esc(ccrW(craft ? "rec.craft" : "rec.sell"))}</span>`;
  };
  return [
    { key: "recipe", label: ccrW("col.recipe"), value: (r) => r.name.toLowerCase(), cell: (r) => `${name(r)}${who(r)}` },
    { key: "cost", label: ccrW("col.cost"), tip: ccrW("col.cost.tip"), num: true, value: by("cost"), cell: (r) => ccrFigure(r.cost, r) },
    { key: "value", label: ccrW("col.value"), tip: ccrW("col.value.tip"), num: true, value: by("value"), cell: (r) => ccrFigure(r.value, r) },
    { key: "profit", label: ccrW(before ? "col.profit.before" : "col.profit"), tip: ccrW("col.profit.tip"), num: true, value: by("margin"), cell: (r) => ccrFigure(r.margin, r) },
    { key: "reagents", label: ccrW("col.reagents"), tip: ccrW("col.reagents.tip"), num: true, value: by("reagentsValue"), cell: (r) => ccrFigure(r.reagentsValue, r) },
    { key: "gain", label: ccrW("col.gain"), tip: ccrW("col.gain.tip"), num: true, value: by("versus"), cell: (r) => ccrFigure(r.versus, r) },
    { key: "rec", label: ccrW("col.rec"), tip: ccrW("col.rec.tip"), value: (r) => (r.versus ? (r.versus.mid >= 0 ? 1 : 0) : null), cell: rec },
    { key: "sold", label: ccrW("col.sold"), tip: ccrW("col.sold.tip"), num: true, value: (r) => r.product?.day ?? null, cell: sold },
    { key: "confidence", label: ccrW("col.confidence"), tip: ccrW("col.confidence.tip"), value: (r) => r.steps,
      cell: (r) => (r.steps != null ? `${ckConfidence({ steps: r.steps, scans: r.scans, newest: r.seen }, now)}${r.seen ? `<span class="ctm-under">${ckAgeTag(r.seen, now)}</span>` : ""}` : "") },
  ];
}


function ccrKeysHtml() {
  const key = (every, k) => `<button type="button" class="key small" data-ccr-every="${every ? 1 : 0}" aria-pressed="${ccr.every === every}"
    title="${esc(ccrW(`${k}.tip`))}">${esc(ccrW(k))}</button>`;
  return `<div class="cth-row ccr-keys">${key(false, "known")}${key(true, "all")}</div>`;
}

function ccrNotesHtml(d) {
  const fees = d.fees ? ccrW("fees.after", { cut: `${Math.round(d.fees.cut * 1000) / 10}%` }) : ccrW("fees.before");
  return `<div class="ctm-notes"><p>${esc(fees)}</p><p>${esc(ccrW("odds"))}</p><p class="muted">${esc(ccrW("ranges"))}</p><p class="muted">${esc(ccrW("prices"))}</p></div>`;
}

function ccrPanelHtml() {
  ccrLoad();
  const d = ccr.data;
  let body, views = [], latest = "", view = null;
  if (!d) body = `<p class="muted">${esc(ccr.failed ? cthW("failed") : ccrW("loading"))}</p>`;
  else if (!d.made) body = `<p class="cth-empty">${esc(ccrW("none"))}</p><p class="muted cth-flavour">${esc(ccrW("none.flavour"))}</p>`;
  else if (!d.recipes.length) {
    body = `${ccrKeysHtml()}<p class="cth-empty">${esc(ccrW(d.every ? "empty.all" : "empty.known"))}</p>${
      d.every ? "" : `<p class="muted cth-flavour">${esc(ccrW("empty.known.flavour"))}</p>`}`;
  } else {
    views = CCR_VIEWS;
    view = ckViewOf(CCR_PANEL, CCR_VIEWS);
    latest = cthRestsOn(ccrW, "latest", d.newest, d.now);
    let shown;
    if (view === "table") {
      const rows = [...d.recipes].sort((a, b) => Math.abs(b.versus?.mid ?? 0) - Math.abs(a.versus?.mid ?? 0)).slice(0, CCR_TABLE_MOST);
      const more = d.recipes.length > rows.length ? `<p class="muted cti-note">${esc(ccrW("table.more", { n: num(rows.length) }))}</p>` : "";
      shown = `${more}<div class="ctm-table">${ckTable({ id: "ccr-table", columns: ccrColumns(d), rows, key: (r) => r.spell, sort: { key: "gain", down: true } })}</div>`;
    }
    else if (view === "diagram") {
      const r = ccrPicked(d);
      shown = `<h4 class="cth-sub">${esc(ccrW("diagram", { name: r.name }))}</h4><div class="ctm-plot" data-ccr-plot="tree"></div><p class="ck-legend">${esc(ccrW("diagram.pick"))}</p>`;
    } else {
      const n = d.recipes.filter((r) => r.versus).length;
      shown = !n ? `<p class="muted">${esc(ccrW("chart.none"))}</p>` : `<h4 class="cth-sub">${esc(ccrW("chart"))}</h4><div class="ctm-plot" data-ccr-plot="bars"></div>
        <p class="ck-legend">${esc(ccrW("chart.key"))}</p>${n > CCR_BARS_MOST ? `<p class="muted cti-note">${esc(ccrW("chart.more", { n: CCR_BARS_MOST }))}</p>` : ""}`;
    }
    body = `${ccrKeysHtml()}${shown}${ccrNotesHtml(d)}`;
  }
  return ckPanelHtml({ id: CCR_PANEL, icon: CCR_ICON, title: ccrW("title"), latest, views, view, body });
}

function ccrDraw() {
  const d = ccr.data;
  if (!d?.recipes?.length) return;
  for (const host of $("counting").querySelectorAll("[data-ccr-plot]")) {
    const w = Math.max(320, Math.floor(host.clientWidth));
    setHtml(host, host.dataset.ccrPlot === "bars" ? ccrBarsSvg(d, w) : ccrTreeSvg(ccrPicked(d), w));
  }
}

function ccrOpen(spell) {
  ccr.picked = spell;
  ckStore(`view.${CCR_PANEL}`, "diagram");
  renderCounting();
}

function ccrClick(e) {
  const every = e.target.closest?.("button[data-ccr-every]"), recipe = e.target.closest?.("button[data-ccr-recipe]");
  const bar = e.target.closest?.("[data-ck-tile]");
  if (every) {
    ccr.every = every.dataset.ccrEvery === "1";
    ccrLoad();
    renderCounting();
    return true;
  }
  if (recipe) {
    ccrOpen(+recipe.dataset.ccrRecipe);
    return true;
  }
  if (bar?.closest("[data-ccr-plot]")) {
    ccrOpen(+bar.dataset.ckTile.slice(2));
    return true;
  }
  return false;
}
