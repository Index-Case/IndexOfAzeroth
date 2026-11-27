// The Index of Azeroth. Copyright 2026 Index Case <indexofazeroth@pm.me>. PolyForm Strict 1.0.0, see LICENSE.md.
"use strict";

const FIN_REFRESH_MS = 30000;
const FIN_SIDE_MS = 60000;
const FIN_CAUSES = ["grinding", "loot", "share", "quest", "vendor", "repair", "training", "flight", "auction", "auctionbuy",
  "auctionfee", "refund", "mail", "postage", "trade", "between", "atvendor", "unexplained"];
const FIN_SERIES = { in: { grinding: 1, loot: 2, share: 3, quest: 4, vendor: 5, atvendor: 6, auction: 6, refund: 6, mail: 3,
  trade: 3, between: 3 },
out: { repair: 1, training: 2, flight: 4, vendor: 5, atvendor: 6, auctionbuy: 6, auctionfee: 6, postage: 4, mail: 3, trade: 3,
  between: 3 } };
const FIN_SIDES = ["in", "out"];
const FIN_RANK = 10;
const FIN_PEOPLE = 15;
const FIN_WASTE = ["death", "deposit", "resold", "vendor", "marked"];
const FIN_PANELS = [
  { id: "overview", icon: "inv_misc_coin_02", views: ["chart", "diagram", "table"] },
  { id: "flows", icon: "inv_misc_note_02", views: ["chart", "diagram", "table"] },
  { id: "earners", icon: "inv_misc_coin_04", views: ["chart", "diagram", "table"] },
  { id: "gold", icon: "inv_misc_coin_01", views: ["chart", "diagram", "table"] },
  { id: "people", icon: "inv_letter_15", views: ["chart", "diagram", "table"] },
  { id: "unexplained", icon: "inv_misc_questionmark", views: ["chart", "table"] }];
const FIN_SHOWN = 5;
const FIN_PLOT = 170;
const FIN_LABEL_ROOM = 56;
const FIN_SPARK = [120, 22];
const FIN_ICON = "inv_misc_coin_02";
const FIN_W = wordsOf("page.financials.window"), FIN_D = wordsOf("page.financials.drawer");
const finW = (key, fill) => fillWords(FIN_W[key], fill) ?? "";
const finCount = (key, n, fill) => finW(n === 1 && FIN_W[`${key}.one`] != null ? `${key}.one` : key, { ...fill, n: num(n) });
const finD = (key, fill) => fillWords(FIN_D[key], fill) ?? "";

const fin = { open: false, scope: "char", key: null, range: ckRangeOf(), picked: null, data: null, failed: false,
  panel: "overview", timer: 0, side: {} };

const finUrl = (scope, key, range, picked) => `/api/financials?scope=${scope}${key ? `&char=${encodeURIComponent(key)}` : ""}&range=${range}${
  picked ? `&from=${Math.floor(picked.from)}&to=${Math.ceil(picked.to)}` : ""}${scope === "account" ? `&realms=${alts.allRealms ? "all" : "here"}` : ""}`;
const finCause = (c, side) => (side && FIN_W[`cause.${c}.${side}`] ? finW(`cause.${c}.${side}`) : finW(`cause.${c}`));
const finSigned = (copper, tight = false) => `${copper > 0 ? "+" : ""}${ckGold(copper, tight)}`;
const finName = (key) => (key && alts.data?.chars?.[key] ? altName(alts.data.chars[key]) : null);
function finWhen(t, bucket) {
  const d = new Date(t * 1000);
  return bucket === "hour" ? d.toLocaleTimeString(undefined, { hour: "2-digit", minute: "2-digit" })
    : d.toLocaleDateString(undefined, { weekday: bucket === "day" ? "short" : undefined, day: "numeric", month: "short" });
}


function finSide(url, redraw) {
  const kept = fin.side[url];
  if (!kept || Date.now() - kept.at > FIN_SIDE_MS) {
    fin.side[url] = { at: Date.now(), d: kept?.d || null };
    getJson(url, { key: url, force: true })?.then((d) => { fin.side[url] = { at: Date.now(), d }; redraw(); }, () => {});
  }
  return fin.side[url].d;
}

function finSparkHtml(trend, tip) {
  const pts = trend.map((x) => ({ t: new Date(`${x.day}T12:00:00`).getTime() / 1000, v: x.held }));
  const view = { from: pts[0].t, to: pts[pts.length - 1].t };
  while (pts.length && pts[pts.length - 1].v == null) pts.pop();
  return pts.length ? tcSpark(pts, view, FIN_SPARK[0], FIN_SPARK[1], tip) : "";
}

const finFigure = (label, value, tip, cls = "") => `<span class="fin-figure${cls}" title="${esc(tip)}"><small>${esc(label)}</small><b>${value}</b></span>`;

on("playerDrawer", () => {
  const key = app.character;
  if (!key) return "";
  const d = finSide(finUrl("char", key, "7d"), () => { if (app.drawer === "player") renderDrawer(); });
  const head = `<h3>${esc(finD("title"))}</h3>`;
  const open = `<button class="key" data-fin-open="char" style="--icon:url(/icon/${FIN_ICON}.jpg)" title="${esc(finD("open.tip"))}">${esc(finD("open"))}</button>`;
  if (!d) return `${head}<p>${open}</p>`;
  if (!d.trend.some((x) => x.held != null) && !d.income && !d.spending) return `${head}<p class="muted">${esc(finW("empty"))}</p><p>${open}</p>`;
  const named = (x, label, tip, side) => (x ? finFigure(label, `${esc(finCause(x.cause, side))} ${ckGold(x.amount, true)}`, tip) : "");
  return `${head}<div class="fin-part"><div class="fin-figures"><small class="fin-week">${esc(finD("week"))}</small>
      ${finFigure(finW("figure.income"), ckGold(d.income, true), finW("figure.income.tip"))}
      ${finFigure(finW("figure.spending"), ckGold(d.spending, true), finW("figure.spending.tip"))}
      ${finFigure(finW("figure.net"), finSigned(d.net, true), finW("figure.net.tip"))}
      ${finFigure(finW("figure.gold"), ckGold(d.gold, true), finW("figure.gold.tip"))}${finSparkHtml(d.trend, finD("held.tip"))}</div>
    <div class="fin-figures">${named(d.top, finD("top"), finD("top.tip"), "in")}${named(d.drain, finD("drain"), finD("drain.tip"), "out")}${
  d.top || d.drain ? "" : `<span class="muted">${esc(finD("none"))}</span>`}</div><p>${open}</p></div>`;
});

function finAltsRowHtml() {
  const d = finSide(finUrl("account", null, "7d"), () => { if (app.drawer === "alts") renderDrawer(); });
  const open = `<button class="key small" data-fin-open="account" style="--icon:url(/icon/${FIN_ICON}.jpg)" title="${esc(finD("alts.open.tip"))}">${esc(finD("alts.open"))}</button>`;
  const line = d ? `<span>${finD("alts.line", { in: ckGold(d.income, true), out: ckGold(d.spending, true), net: finSigned(d.net, true) })}</span>${finSparkHtml(d.trend, finD("held.tip"))}` : "";
  return `<tr><th>${esc(finD("alts.row"))}</th><td><div class="fin-alts">${line}${open}</div></td></tr>`;
}

$("drawer").addEventListener("click", (e) => {
  const b = e.target.closest("button[data-fin-open]");
  if (b) openFinancials(b.dataset.finOpen);
});


const finView = (d) => ({ from: d.since, to: d.until });
const finRowEnd = (d, i) => (i + 1 < d.rows.length ? d.rows[i + 1].at : d.until);
function finNoReport(d) {
  const out = [];
  d.rows.forEach((r, i) => {
    if (r.seen) return;
    const last = out[out.length - 1];
    if (last && last.to === r.at) last.to = finRowEnd(d, i);
    else out.push({ from: r.at, to: finRowEnd(d, i) });
  });
  return out;
}
const finWidth = () => Math.max(300, ($("financials").querySelector(".fin-scroll")?.clientWidth || 900) - FIN_LABEL_ROOM - 24);
const finDragBox = (d, svg) => `<div class="tc-box ck-drag" data-from="${d.since}" data-to="${d.until}">${svg}<div class="ck-pick" hidden></div></div>`;
const finSwatch = (c, side) => ({ name: finCause(c, side), tip: finW(`cause.${c}.tip`), series: FIN_SERIES[side][c], unknown: c === "unexplained" });
const finCausesOf = (d, side) => FIN_CAUSES.filter((c) => d.causes[side][c]);
const finCauseLegend = () => FIN_SIDES.flatMap((side) => [{ group: finW(`legend.${side}`) }, ...FIN_CAUSES.filter((c) => c === "unexplained" || FIN_SERIES[side][c])
  .map((c) => finSwatch(c, side)).map((s) => ({ look: `${side === "in" ? "up" : "down"}-${s.unknown ? "unknown" : `s${s.series}`}`, name: s.name, tip: s.tip }))]);
const finNoReportLegend = () => ({ look: "hatch", name: finW("overview.noreport"), tip: finW("overview.noreport.tip") });

const finPlain = (copper) => `${copper < 0 ? "−" : ""}${moneyText(Math.abs(copper))}`;
const finAxis = goldText;
const finParts = (r, side, when, only) => FIN_CAUSES.filter((c) => r[side][c] && (!only || c === only)).map((c) => ({ series: FIN_SERIES[side][c],
  unknown: c === "unexplained", v: r[side][c], title: finW(`overview.bar.${side}`, { when, money: finPlain(r[side][c]), name: finCause(c, side) }) }));

function finOverviewChart(d) {
  const w = finWidth(), view = finView(d);
  const bins = d.rows.map((r, i) => {
    const when = finWhen(r.at, d.bucket);
    return { from: r.at, to: finRowEnd(d, i), up: finParts(r, "in", when), down: finParts(r, "out", when) };
  });
  const line = d.rows.map((r, i) => ({ t: (r.at + finRowEnd(d, i)) / 2, v: r.seen ? r.net : null }));
  const svg = ckSignedBarsSvg({ id: "fin-overview", width: w, high: FIN_PLOT, view, scale: timeScale(view.from, view.to, w), bins, line,
    label: finAxis, hatch: finNoReport(d), legend: [{ look: "net", name: finW("overview.net"), tip: finW("overview.net.tip") }, finNoReportLegend(), ...finCauseLegend()] });
  return finDragBox(d, svg);
}

function finCalendar(d) {
  const cell = (x) => (x.seen ? { v: x.net, title: finW("overview.day.tip", { day: x.day, in: finPlain(x.income), out: finPlain(x.spending), net: finPlain(x.net) }) }
    : { empty: true, title: finW("overview.day.none", { day: x.day }) });
  return `<div class="fin-cal">${ckCalendarHtml(d.days, cell, [{ look: "heat-gain", name: finW("overview.income") }, { look: "heat-loss", name: finW("overview.spending") },
    finNoReportLegend()])}</div>`;
}

function finOverviewTable(d) {
  const noreport = `<span class="muted" title="${esc(finW("overview.noreport.tip"))}">${esc(finW("overview.noreport"))}</span>`;
  const col = (key, label, value, cell, tip) => ({ key, label, value, cell, tip, num: key !== "at" });
  return ckTable({ id: "fin-overview", sort: { key: "at", down: true }, rows: d.rows, columns: [
    col("at", finW(`overview.when.${d.bucket}`), (r) => r.at, (r) => esc(finWhen(r.at, d.bucket))),
    col("income", finW("overview.income"), (r) => r.income, (r) => (r.seen ? ckGold(r.income) : "")),
    col("spending", finW("overview.spending"), (r) => r.spending, (r) => (r.seen ? ckGold(r.spending) : "")),
    col("net", finW("overview.net"), (r) => r.net, (r) => (r.seen ? finSigned(r.net) : ""), finW("figure.net.tip")),
    col("held", finW("overview.held"), (r) => r.held, (r) => (r.held == null ? noreport : ckGold(r.held)))] });
}

function finHeldLine(p, d) {
  const seen = new Set(p.seen), pts = [...(p.start != null ? [[d.since, p.start]] : []), ...p.points], out = [];
  let i = 0, v = null;
  const midnight = (t, add = 0) => { const x = new Date(t * 1000); return new Date(x.getFullYear(), x.getMonth(), x.getDate() + add).getTime() / 1000; };
  for (let day = midnight(d.since); day < d.until; day = midnight(day, 1)) {
    const from = Math.max(d.since, day), to = Math.min(d.until, midnight(day, 1));
    if (!seen.has(new Date(day * 1000).toLocaleDateString("sv"))) {
      while (i < pts.length && pts[i][0] < to) v = pts[i++][1];
      out.push({ t: from, v: null });
      continue;
    }
    if (v != null) out.push({ t: from, v });
    while (i < pts.length && pts[i][0] < to) {
      const [t, c] = pts[i++];
      if (v != null) out.push({ t, v });
      v = c;
      out.push({ t, v });
    }
    if (v != null) out.push({ t: to, v });
  }
  return out;
}

function finGoldChart(d) {
  const w = finWidth(), view = finView(d), scale = timeScale(view.from, view.to, w);
  if (d.scope === "char") {
    const p = d.characters[0], line = p ? finHeldLine(p, d) : [];
    const values = { ...valueTicks(Math.max(1, ...line.map((x) => x.v || 0)), 4), label: finAxis };
    const dots = (p?.points || []).length <= 200 ? p.points.map(([t, c]) => ({ t, v: c, title: finW("gold.point", { when: ago(t), name: p.name, money: finPlain(c) }) })) : [];
    const drawn = new Set([...(line.some((x) => x.v != null) ? ["line"] : []), ...(dots.length ? ["dot"] : [])]);
    const under = ckHatchSvg(finNoReport(d), view, w, TC_TOP, FIN_PLOT, "fin-gold", drawn);
    return finDragBox(d, `${timeChartSvg({ id: "fin-gold", width: w, view, values, scale, dots, line, plot: FIN_PLOT, under })}${
      ckLegendHtml([{ look: "line", name: finW("legend.held") }, { look: "dot", name: finW("legend.report") }, finNoReportLegend()], drawn)}`);
  }
  const held = d.characters.filter((p) => d.rows.some((r) => r.parts[p.key])).sort((a, b) => (b.end || 0) - (a.end || 0));
  const shown = held.slice(0, FIN_SHOWN), series = ckSeriesOf(shown.map((p) => p.key)), rest = held.slice(FIN_SHOWN);
  const bins = d.rows.map((r, i) => {
    const when = finWhen(r.at, d.bucket), parts = shown.filter((p) => r.parts[p.key]).map((p) => ({ series: series[p.key], v: r.parts[p.key],
      title: finW("gold.point", { when, name: p.name, money: finPlain(r.parts[p.key]) }) }));
    const others = rest.reduce((s, p) => s + (r.parts[p.key] || 0), 0);
    if (others) parts.push({ series: CK_SERIES, v: others, title: finW("gold.point", { when, name: finW("gold.others"), money: finPlain(others) }) });
    return { from: r.at, to: finRowEnd(d, i), parts };
  });
  const values = { ...valueTicks(Math.max(1, ...d.rows.map((r) => r.held || 0)), 4), label: finAxis };
  const legend = [...shown.map((p) => ({ look: `s${series[p.key]}`, name: p.name })), { look: `s${CK_SERIES}`, name: finW("gold.others") }, finNoReportLegend()];
  return finDragBox(d, ckBarsSvg({ id: "fin-gold", width: w, high: FIN_PLOT, view, values, scale, bins, hatch: finNoReport(d), legend }));
}

function finWaterfall(d) {
  const steps = [{ name: finW("gold.start"), v: d.start, total: true, title: finW("gold.start.tip") }];
  if (d.opened) steps.push({ name: finW("gold.opened"), v: d.opened, series: CK_SERIES, title: finW("gold.opened.tip") });
  for (const side of FIN_SIDES) {
    for (const c of finCausesOf(d, side)) {
      const v = d.causes[side][c];
      steps.push({ ...finSwatch(c, side), v: side === "in" ? v : -v, title: finW(`cause.${c}.tip`) });
    }
  }
  steps.push({ name: finW("gold.end"), v: d.end, total: true, title: finW("gold.end.tip") });
  const w = Math.min(finWidth() + FIN_LABEL_ROOM, 120 * steps.length);
  return `<div class="tc-box">${ckWaterfallSvg({ id: "fin-wf", width: w, high: FIN_PLOT, steps, label: finAxis })}</div>`;
}

function finGoldTable(d) {
  const none = `<span class="muted">${esc(finW("gold.none"))}</span>`;
  const gold = (v) => (v == null ? none : ckGold(v));
  const col = (key, label, value, cell, tip) => ({ key, label, value, cell, tip, num: key !== "name" });
  return ckTable({ id: "fin-gold", sort: { key: "end", down: true }, rows: d.characters, columns: [
    col("name", finW("gold.character"), (p) => p.name, (p) => esc(p.name)),
    col("start", finW("gold.start"), (p) => p.start, (p) => gold(p.start), finW("gold.start.tip")),
    col("end", finW("gold.end"), (p) => p.end, (p) => gold(p.end), finW("gold.end.tip")),
    col("change", finW("gold.change"), (p) => (p.end ?? 0) - (p.start ?? 0), (p) => finSigned((p.end ?? 0) - (p.start ?? 0))),
    col("income", finW("overview.income"), (p) => p.income, (p) => ckGold(p.income)),
    col("spending", finW("overview.spending"), (p) => p.spending, (p) => ckGold(p.spending))] });
}


const finPart = (c, part) => (part ? finW(`part.${c}.${part}`) : "");
function finCauseBars(d, side) {
  const rows = finCausesOf(d, side).map((c) => ({ name: finCause(c, side), v: d.causes[side][c], tone: c === "unexplained" ? "none" : side === "in" ? "gain" : "loss",
    title: finW("flows.bar", { name: finCause(c, side), money: finPlain(d.causes[side][c]) }) })).sort((a, b) => b.v - a.v);
  const legend = [{ look: side === "in" ? "tone-gain" : "tone-loss", name: finW(`legend.${side}`) }, { look: "tone-none", name: finCause("unexplained", side) }];
  return rows.length ? `<h4 class="fin-sub">${esc(finW(`legend.${side}`))}</h4>${ckHBarsSvg({ id: `fin-flows-${side}`, width: finWidth() + FIN_LABEL_ROOM, label: finAxis, rows, legend })}` : "";
}

const finFlowsChart = (d) => `${finCauseBars(d, "in")}${finCauseBars(d, "out")}<h4 class="fin-sub">${esc(finW("flows.waterfall"))}</h4>${finWaterfall(d)}`;

function finSankey(d) {
  const node = (c, side) => ({ ...finSwatch(c, side), v: d.causes[side][c], title: finW("flows.bar", { name: finCause(c, side), money: finPlain(d.causes[side][c]) }) });
  const left = finCausesOf(d, "in").map((c) => node(c, "in")), right = finCausesOf(d, "out").map((c) => node(c, "out"));
  const net = d.income - d.spending;
  if (net > 0) right.push({ name: finW("flows.saved"), v: net, series: "total", title: finW("flows.saved.tip", { money: finPlain(net) }) });
  if (net < 0) left.push({ name: finW("flows.drawn"), v: -net, series: "total", title: finW("flows.drawn.tip", { money: finPlain(-net) }) });
  if (!left.length && !right.length) return `<p class="muted">${esc(finW("flows.none"))}</p>`;
  const high = Math.max(160, 46 * Math.max(left.length, right.length));
  return ckSankeySvg({ id: "fin-sankey", width: finWidth() + FIN_LABEL_ROOM, high, left, right, middle: finW("flows.purse"), label: finAxis });
}

function finFlowsTable(d) {
  const rows = FIN_SIDES.flatMap((side) => finCausesOf(d, side).map((c) => {
    const parts = Object.entries(d.parts[side]?.[c] || {}).filter(([p]) => p).sort((a, b) => b[1].total - a[1].total);
    const was = d.before[side][c] || 0, total = d.causes[side][c];
    return { side, cause: c, total, n: Object.values(d.parts[side]?.[c] || {}).reduce((s, x) => s + x.n, 0), share: total / Math.max(1, side === "in" ? d.income : d.spending),
      change: total - was, parts: parts.map(([p, x]) => finCount("flows.part", x.n, { name: finPart(c, p), money: finPlain(x.total) })) };
  }));
  const col = (key, label, value, cell, tip) => ({ key, label, value, cell, tip, num: !["side", "cause", "parts"].includes(key) });
  return ckTable({ id: "fin-flows", sort: { key: "total", down: true }, rows, columns: [
    col("side", finW("flows.side"), (r) => r.side, (r) => esc(finW(`legend.${r.side}`))),
    col("cause", finW("flows.cause"), (r) => finCause(r.cause, r.side), (r) => esc(finCause(r.cause, r.side))),
    col("parts", finW("flows.parts"), (r) => r.parts.join(" "), (r) => r.parts.map(esc).join("<br>")),
    col("n", finW("flows.count"), (r) => r.n, (r) => num(r.n), finW("flows.count.tip")),
    col("total", finW("flows.total"), (r) => r.total, (r) => ckGold(r.total)),
    col("share", finW("flows.share"), (r) => r.share, (r) => `${Math.round(r.share * 100)}%`, finW("flows.share.tip")),
    col("change", finW("flows.change"), (r) => r.change, (r) => finSigned(r.change), finW("flows.change.tip"))] });
}


function finSourceName(s, side) {
  if (s.kind === "route") return finW("source.route", { from: s.from || finW("source.node"), to: s.to || finW("source.node") });
  return s.name || finCause(s.cause, side);
}
const finNamed = (s, side) => finSourceName(s, side) !== finCause(s.cause, side);
const finSourceLabel = (s, side) => (s.kind === "item" && s.id != null ? `<span class="item-named" data-tip="${esc(s.id)}">${esc(finSourceName(s, side))}</span>`
  : esc(finSourceName(s, side)));
const finSourceTip = (s, side) => `${finCount("source.tip", s.n, { name: finSourceName(s, side), cause: finCause(s.cause, side), money: finPlain(s.total) })}${
  s.at.length ? ` ${finW("source.at", { names: s.at.join(", ") })}` : ""}`;
const finRanked = (d, side) => d.sources[side].filter((s) => s.cause !== "unexplained");

function finRankHtml(d, side) {
  const rows = finRanked(d, side).slice(0, FIN_RANK), most = Math.max(1, ...rows.map((s) => s.total)), view = finView(d);
  const spark = (s) => {
    const by = new Map(s.by);
    return tcSpark(d.rows.map((r, i) => ({ t: (r.at + finRowEnd(d, i)) / 2, v: by.get(i) || 0 })), view, 120, 18, finW("earners.spark"));
  };
  const body = rows.map((s) => `<div class="fin-rank" title="${esc(finSourceTip(s, side))}"><span class="fin-rank-name">${finSourceLabel(s, side)}${
    finWasted(s) ? ` <i class="fin-waste-tag">${esc(finW("waste.tag"))}</i>` : ""}${finNamed(s, side) ? `<small>${esc(finCause(s.cause, side))}</small>` : ""}</span>
    <span class="fin-rank-bar ck-tone-${side === "in" ? "gain" : "loss"}" style="width:${Math.max(2, Math.round((90 * s.total) / most))}px"></span>${spark(s)}<b>${ckGold(s.total, true)}</b></div>`).join("");
  return `<div><h4>${esc(finW(`earners.${side}`))}</h4>${body || `<p class="muted">${esc(finW(`earners.${side}.none`))}</p>`}</div>`;
}

function finWasteHtml(d) {
  const lines = FIN_WASTE.filter((why) => d.waste[why]?.total).map((why) => [why, finCount(`waste.${why}`, d.waste[why].n, { money: finPlain(d.waste[why].total) })]);
  return lines.length ? `<div class="fin-waste">${lines.map(([why, x]) => `<p${FIN_W[`waste.${why}.tip`] ? ` title="${esc(finW(`waste.${why}.tip`))}"` : ""}>${esc(x)}</p>`).join("")}</div>` : "";
}

const finEarnersChart = (d) => `${finWasteHtml(d)}<div class="fin-ranks">${finRankHtml(d, "in")}${finRankHtml(d, "out")}</div>`;

const finWasted = (s) => s.marked === true || (s.marked == null && Object.keys(s.waste || {}).length > 0);
const finPerHour = (d, s) => (d.played >= 60 ? (s.total * 3600) / d.played : null);

function finDrainsMap(d) {
  const tiles = d.sources.out.map((s, i) => ({ v: s.total, name: finSourceName(s, "out"), word: finNamed(s, "out") ? finCause(s.cause, "out") : "", tone: s.cause === "unexplained" ? "none" : "loss",
    dim: s.cause === "unexplained", title: finSourceTip(s, "out"), key: i }));
  if (!tiles.length) return `<p class="muted">${esc(finW("earners.out.none"))}</p>`;
  const legend = [{ look: "tone-loss", name: finW("legend.out") }, { look: "dim-none", name: finCause("unexplained", "out") }];
  return `<h4 class="fin-sub">${esc(finW("earners.map"))}</h4>${ckTreemapSvg({ id: "fin-drains", width: finWidth() + FIN_LABEL_ROOM, high: 320, tiles, legend })}`;
}

function finSourcesTable(d) {
  const rows = FIN_SIDES.flatMap((side) => d.sources[side].map((s) => ({ ...s, side, label: finSourceName(s, side) })));
  const col = (key, label, value, cell, tip) => ({ key, label, value, cell, tip, num: ["n", "total", "hour"].includes(key) });
  const mark = (r) => (r.side !== "out" || r.cause === "unexplained" ? "" : `<button class="key small" data-fin-waste="${esc(r.key)}" data-fin-to="${!finWasted(r)}"
    title="${esc(finW(finWasted(r) ? "waste.unmark.tip" : "waste.mark.tip"))}">${esc(finW(finWasted(r) ? "waste.unmark" : "waste.mark"))}</button>`);
  const why = (r) => [...Object.entries(r.waste || {}).filter(() => r.marked == null).map(([w, [total, n]]) => finCount(`waste.${w}.row`, n, { money: finPlain(total) })),
    ...(r.marked === true ? [finW("waste.marked.row")] : [])].join(" ");
  return `${finWasteHtml(d)}${ckTable({ id: "fin-sources", sort: { key: "total", down: true }, rows, columns: [
    col("label", finW("earners.source"), (r) => r.label, (r) => finSourceLabel(r, r.side)),
    col("cause", finW("flows.cause"), (r) => finCause(r.cause, r.side), (r) => esc(finCause(r.cause, r.side))),
    col("side", finW("flows.side"), (r) => r.side, (r) => esc(finW(`legend.${r.side}`))),
    col("at", finW("earners.at"), (r) => r.at.join(", "), (r) => esc(r.at.join(", "))),
    col("n", finW("flows.count"), (r) => r.n, (r) => num(r.n), finW("flows.count.tip")),
    col("total", finW("flows.total"), (r) => r.total, (r) => ckGold(r.total)),
    col("hour", finW("earners.hour"), (r) => finPerHour(d, r), (r) => (finPerHour(d, r) == null ? "" : ckGold(Math.round(finPerHour(d, r)))), finW("earners.hour.tip")),
    col("waste", finW("waste.column"), (r) => (finWasted(r) ? 1 : 0), (r) => `${esc(why(r))} ${mark(r)}`)] })}`;
}


function finLostChart(d) {
  const w = finWidth(), view = finView(d);
  const bins = d.rows.map((r, i) => {
    const when = finWhen(r.at, d.bucket);
    return { from: r.at, to: finRowEnd(d, i), up: finParts(r, "in", when, "unexplained"), down: finParts(r, "out", when, "unexplained") };
  });
  const svg = ckSignedBarsSvg({ id: "fin-lost", width: w, high: FIN_PLOT, view, scale: timeScale(view.from, view.to, w), bins, line: [],
    label: finAxis, hatch: finNoReport(d), legend: [finNoReportLegend(), ...finCauseLegend()] });
  return `${finDragBox(d, svg)}<p class="muted">${esc(finW("lost.chart.note"))}</p>`;
}

function finLostTable(d) {
  const when = (t) => new Date(t * 1000).toLocaleString(undefined, { day: "numeric", month: "short", hour: "2-digit", minute: "2-digit" });
  const named = (k) => d.characters.find((p) => p.key === k)?.name || "";
  const col = (key, label, value, cell, tip) => ({ key, label, value, cell, tip, num: key === "d" });
  const columns = [col("t", finW("lost.when"), (r) => r.t, (r) => esc(when(r.t))),
    ...(d.scope === "account" ? [col("key", finW("gold.character"), (r) => named(r.key), (r) => esc(named(r.key)))] : []),
    col("d", finW("lost.money"), (r) => r.d, (r) => finSigned(r.d)),
    col("kind", finW("lost.kind"), (r) => r.kind, (r) => esc(finW(`part.unexplained.${r.kind}`))),
    col("place", finW("lost.place"), (r) => r.place?.zone || "", (r) => esc(r.place ? (r.place.sub ? finW("lost.place.sub", r.place) : r.place.zone) : ""), finW("lost.place.tip")),
    col("windows", finW("lost.windows"), (r) => r.windows.join(), (r) => esc(r.windows.map((x) => finW(`window.${x}`)).join(", ")), finW("lost.windows.tip"))];
  const more = d.lostCount > d.lost.length ? `<p class="muted">${esc(finW("lost.more", { n: num(d.lost.length), all: num(d.lostCount) }))}</p>` : "";
  return d.lost.length ? `${more}${ckTable({ id: "fin-lost", sort: { key: "t", down: true }, rows: d.lost, columns })}` : `<p class="muted">${esc(finW("lost.none"))}</p>`;
}


const finPersonName = (p) => (p.own ? `${p.name} (${finW("people.own")})` : p.name);

function finPeopleChart(d) {
  const ranked = d.others.slice(0, FIN_PEOPLE), w = finWidth() + FIN_LABEL_ROOM;
  if (!ranked.length) return `<p class="muted">${esc(finW("people.none"))}</p>`;
  const part = (side) => {
    const rows = ranked.filter((p) => p[side]).sort((a, b) => b[side] - a[side]).map((p) => ({ name: finPersonName(p), v: p[side],
      tone: side === "received" ? "gain" : "loss", title: finCount(`people.${side}.bar`, p.n, { name: p.name, money: finPlain(p[side]) }) }));
    const legend = [{ look: side === "received" ? "tone-gain" : "tone-loss", name: finW(`people.${side}`) }];
    return rows.length ? `<h4 class="fin-sub">${esc(finW(`people.${side}`))}</h4>${ckHBarsSvg({ id: `fin-people-${side}`, width: w, label: finAxis, rows, legend })}` : "";
  };
  return `${part("received")}${part("sent")}${d.others.some((p) => p.own) ? `<p class="muted">${esc(finW("people.own.note"))}</p>` : ""}`;
}

function finPeopleSankey(d) {
  const sent = d.others.filter((p) => p.sent);
  if (!sent.length) return `<p class="muted">${esc(finW("people.none"))}</p>`;
  const named = Object.fromEntries(d.characters.map((c) => [c.key, c.name]));
  const keys = [...new Set(sent.flatMap((p) => Object.keys(p.by).filter((k) => p.by[k].sent)))], series = ckSeriesOf(keys);
  const left = keys.map((k) => {
    const v = sent.reduce((s, p) => s + (p.by[k]?.sent || 0), 0);
    return { name: named[k] || k, v, series: series[k], title: finW("people.from", { name: named[k] || k, money: finPlain(v) }) };
  });
  const top = sent.slice(0, FIN_PEOPLE), rest = sent.slice(FIN_PEOPLE).reduce((s, p) => s + p.sent, 0);
  const right = top.map((p) => ({ name: finPersonName(p), v: p.sent, series: p.own ? "total" : 3,
    title: finCount("people.sent.bar", p.n, { name: p.name, money: finPlain(p.sent) }) }));
  if (rest) right.push({ name: finW("people.others"), v: rest, series: 3, title: finW("people.others.tip", { money: finPlain(rest) }) });
  const high = Math.max(160, 46 * Math.max(left.length, right.length));
  return `<h4 class="fin-sub">${esc(finW("people.diagram"))}</h4>${ckSankeySvg({ id: "fin-people", width: finWidth() + FIN_LABEL_ROOM, high, left, right,
    middle: finW("people.sent"), label: finAxis })}`;
}

function finPeopleTable(d) {
  if (!d.others.length) return `<p class="muted">${esc(finW("people.none"))}</p>`;
  const when = (t) => new Date(t * 1000).toLocaleString(undefined, { day: "numeric", month: "short", hour: "2-digit", minute: "2-digit" });
  const col = (key, label, value, cell, tip) => ({ key, label, value, cell, tip, num: ["sent", "received", "n"].includes(key) });
  return ckTable({ id: "fin-people", sort: { key: "sent", down: true }, rows: d.others, columns: [
    col("name", finW("people.name"), (p) => p.name.toLowerCase(), (p) => `${esc(p.name)}${p.own ? ` <small class="muted" title="${esc(finW("people.own.tip"))}">${
      esc(finW("people.own"))}</small>` : ""}`),
    col("sent", finW("people.sent"), (p) => p.sent, (p) => (p.sent ? ckGold(p.sent) : "")),
    col("received", finW("people.received"), (p) => p.received, (p) => (p.received ? ckGold(p.received) : "")),
    col("n", finW("people.count"), (p) => p.n, (p) => num(p.n), finW("people.count.tip")),
    col("how", finW("people.how"), (p) => p.how.join(), (p) => esc(p.how.map((h) => finW(`people.how.${h}`)).join(", "))),
    col("last", finW("people.last"), (p) => p.last, (p) => esc(when(p.last)))] });
}

const FIN_DRAW = {
  overview: { chart: finOverviewChart, diagram: finCalendar, table: finOverviewTable },
  flows: { chart: finFlowsChart, diagram: finSankey, table: finFlowsTable },
  earners: { chart: finEarnersChart, diagram: finDrainsMap, table: finSourcesTable },
  gold: { chart: finGoldChart, diagram: finWaterfall, table: finGoldTable },
  people: { chart: finPeopleChart, diagram: finPeopleSankey, table: finPeopleTable },
  unexplained: { chart: finLostChart, table: finLostTable },
};

function finPanelHtml(d) {
  const p = FIN_PANELS.find((x) => x.id === fin.panel) || FIN_PANELS[0];
  if (!p.views) return ckPanelHtml({ id: `fin-${p.id}`, icon: p.icon, title: finW(`panel.${p.id}`), views: [], body: `<p class="muted">${esc(finW(`panel.${p.id}.later`))}</p>` });
  const view = ckViewOf(`fin-${p.id}`, p.views);
  return ckPanelHtml({ id: `fin-${p.id}`, icon: p.icon, title: finW(`panel.${p.id}`), views: p.views, view, body: FIN_DRAW[p.id][view](d) });
}


function finHousesHtml(d) {
  const rows = d.houses.map((h) => `<tr><td>${esc(h.realm)}</td><td>${esc(h.faction)}</td><td class="num">${num(h.count)}</td><td class="num">${ckGold(h.money)}</td></tr>`).join("");
  return `<div class="fin-houses"><h4>${esc(finW("houses.title"))}</h4><table class="mt-table"><thead><tr><th>${esc(finW("houses.realm"))}</th><th>${esc(finW("houses.side"))}</th>
    <th class="num">${esc(finW("houses.count"))}</th><th class="num">${esc(finW("houses.gold"))}</th></tr></thead><tbody>${rows}</tbody></table>
    <p class="muted">${esc(finW("houses.note"))}</p><p class="muted">${esc(finW("between.note"))}</p></div>`;
}

function finBodyHtml(d) {
  const share = Math.round(d.unexplainedShare * 100);
  const figures = `<div class="fin-figures fin-head-figures">${finFigure(finW("figure.gold"), ckGold(d.gold), finW("figure.gold.tip"))}
    ${finFigure(finW("figure.income"), ckGold(d.income), finW("figure.income.tip"))}${finFigure(finW("figure.spending"), ckGold(d.spending), finW("figure.spending.tip"))}
    ${finFigure(finW("figure.net"), finSigned(d.net), finW("figure.net.tip"))}${finFigure(finW("figure.unexplained"), `${share}%`, finW("figure.unexplained.tip"), " fin-unexplained")}
    ${finFigure(finW("figure.played"), esc(finW("figure.played.value", { hours: (d.played / 3600).toFixed(1) })), finW("figure.played.tip"))}${
  d.played >= 60 ? finFigure(finW("figure.hour"), ckGold(Math.round((d.income * 3600) / d.played)), finW("figure.hour.tip")) : ""}</div>`;
  const unseen = d.unseen.in + d.unseen.out;
  const day = d.record.from ? new Date(d.record.from * 1000).toLocaleDateString(undefined, { day: "numeric", month: "long" }) : "";
  const said = d.record.state !== "recorded" ? finW(`causes.${d.record.state}`, { day }) : "";
  const notes = `<p class="muted">${esc(said)}${unseen ? ` ${finW("unseen.note", { money: ckGold(unseen) })}` : ""}</p>`;
  const tabs = `<div class="fin-tabs">${FIN_PANELS.map((p) => `<button class="key small" data-fin-panel="${p.id}" aria-pressed="${fin.panel === p.id}">${esc(finW(`panel.${p.id}`))}</button>`).join("")}</div>`;
  if (!d.characters.some((p) => p.points.length || p.start != null)) {
    return `${figures}<p>${esc(finW("empty"))}</p><p class="muted fin-flavour">${esc(finW("empty.flavour"))}</p>${d.scope === "account" ? finHousesHtml(d) : ""}`;
  }
  return `${figures}${notes}${tabs}${finPanelHtml(d)}${d.scope === "account" ? finHousesHtml(d) : ""}`;
}

function renderFinancials(measured = false) {
  if (!fin.open) return;
  const name = finName(fin.key) || (fin.data?.scope === "char" && fin.data.characters[0]?.name) || fin.name || finW("scope.char");
  fin.name = name;
  const scope = `<span class="fin-scope" role="group"><button class="key small" data-fin-scope="char" aria-pressed="${fin.scope === "char"}"
      title="${esc(finW("scope.char.tip", { name }))}"${fin.key ? "" : " disabled"}>${esc(name)}</button><button class="key small" data-fin-scope="account"
      aria-pressed="${fin.scope === "account"}" title="${esc(finW("scope.all.tip"))}">${esc(finW("scope.all"))}</button></span>`;
  const head = `<div class="fin-head">${scope}${ckRangeHtml(fin.range, !!fin.picked)}</div>`;
  const keep = $("financials").querySelector(".fin-scroll")?.scrollTop || 0;
  const body = fin.data ? finBodyHtml(fin.data) : `<p class="muted">${esc(fin.failed ? finW("failed") : finW("loading"))}</p>`;
  setHtml($("financials"), `<div class="j-bar"><span class="j-bar-keys"></span><span class="j-bar-title">${esc(finW("title"))}</span>
    <span class="j-bar-end">${helpButton("financials")}<button class="key small square x-mark" data-close="1" title="${esc(finW("close.tip"))}">&times;</button></span></div>
    <div class="j-body fin-body">${head}<div class="fin-scroll">${body}</div></div>`);
  if (fin.data && !measured && Math.abs(finWidth() - (fin.drawnAt || 0)) > 4) {
    fin.drawnAt = finWidth();
    return renderFinancials(true);
  }
  const box = $("financials").querySelector(".fin-scroll");
  if (box) box.scrollTop = keep;
}

function loadFinancials() {
  const url = finUrl(fin.scope, fin.scope === "char" ? fin.key : null, fin.range, fin.picked);
  fin.asked = url;
  getJson(url, { key: "/api/financials", force: true })?.then((d) => {
    if (fin.asked !== url) return;
    for (const p of d.characters) p.name ||= finW("scope.char");
    const twice = new Set(d.characters.map((p) => p.name).filter((n, i, all) => all.indexOf(n) !== i));
    for (const p of d.characters) if (twice.has(p.name) && p.realm) p.name = finW("gold.realm", { name: p.name, realm: p.realm });
    fin.data = d;
    fin.failed = false;
    renderFinancials();
  }, () => { fin.failed = true; renderFinancials(); });
}

function openFinancials(scope) {
  fin.open = true;
  fin.scope = scope === "account" ? "account" : "char";
  if (fin.key !== app.character) fin.name = null;
  fin.key = app.character;
  fin.data = null;
  emit("window", "financials");
  $("financials").hidden = false;
  renderFinancials();
  loadFinancials();
  clearInterval(fin.timer);
  fin.timer = setInterval(loadFinancials, FIN_REFRESH_MS);
}

function closeFinancials() {
  fin.open = false;
  clearInterval(fin.timer);
  $("financials").hidden = true;
}

$("financials").addEventListener("click", (e) => {
  const b = e.target.closest("button");
  if (b?.dataset.close) return closeFinancials();
  if (b?.dataset.finScope) {
    fin.scope = b.dataset.finScope;
    fin.data = null;
    renderFinancials();
    return loadFinancials();
  }
  if (b?.dataset.finWaste) {
    postJson("/api/financials", { do: "waste", source: b.dataset.finWaste, waste: b.dataset.finTo === "true" })?.then(loadFinancials, () => {});
    return;
  }
  if (b?.dataset.finPanel) {
    fin.panel = b.dataset.finPanel;
    return renderFinancials();
  }
  const range = ckRangeClick(e);
  if (range) {
    fin.range = range;
    fin.picked = null;
    fin.data = null;
    renderFinancials();
    return loadFinancials();
  }
  if (ckSwitchClick(e) || ckSortClick(e)) renderFinancials();
});
ckDragRange($("financials"), (stretch) => {
  fin.picked = stretch;
  fin.data = null;
  renderFinancials();
  loadFinancials();
});
on("snapshot", () => {
  if (!fin.open || !app.character || fin.key === app.character) return;
  fin.key = app.character;
  fin.name = null;
  if (fin.scope === "char") fin.data = null;
  loadFinancials();
  renderFinancials();
});
on("allRealms", () => {
  if (!fin.open || fin.scope !== "account") return;
  fin.data = null;
  renderFinancials();
  loadFinancials();
});
closable(LAYER.journal, () => fin.open, closeFinancials);
on("window", (w) => { if (w !== "financials" && fin.open) closeFinancials(); });
