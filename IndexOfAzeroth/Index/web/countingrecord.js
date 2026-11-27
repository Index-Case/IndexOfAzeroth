// The Index of Azeroth. Copyright 2026 Index Case <indexofazeroth@pm.me>. PolyForm Strict 1.0.0, see LICENSE.md.
"use strict";

const CRT_W = wordsOf("page.counting.record");
const crtW = (key, fill) => fillWords(CRT_W[key], fill) ?? "";
const CRT_VIEWS = ["chart", "diagram", "table"];
const CRT_ICON = "inv_misc_note_01";
const CRT_BARS = 150, CRT_GOLD = 70;
const CRT_TOOK = [3600, 2 * 3600, 6 * 3600, 12 * 3600, 86400, 2 * 86400];
const CRT_SURE = ["guess", "known", "invoice", "certain"];
const CRT_PARTS = [["sold", 1, "chart.sold"], ["known", 2, "chart.sold.known"], ["guess", 0, "chart.sold.guess"],
  ["expired", 5, "chart.expired"], ["cancelled", 6, "chart.cancelled"]];
const crt = { data: null, asked: null, stamp: null, failed: false, more: false };

const crtChance = (p) => (p >= 0.05 ? crtW("chance", { n: Math.round(p * 10) }) : crtW("chance.low"));
const crtWhen = (t) => (t ? pvWhen(t) : "");
const crtKey = (r) => r.itemKey ?? r.item ?? null;
function crtItem(d, r) {
  const info = d.infos?.[String(r.item)] || {};
  return ckItemHtml({ key: crtKey(r), name: r.name || info.n || (r.item ? String(r.item) : ""), q: info.q, icon: info.icon });
}

function crtLoad(force = false) {
  const url = `/api/counting/record?house=${encodeURIComponent(cth.house || "")}`, kept = cthShow();
  if (!cthAsks(crt, url, force || !(crt.data || crt.failed), kept)) return;
  getJson(`${url}&${kept}`, { key: "/api/counting/record", force: true })?.then((d) => {
    if (!cthAnswered(crt, url, kept)) return;
    crt.data = d;
    crt.failed = false;
    if (cth.open && cth.tab === "record") renderCounting();
  }, () => { crt.failed = true; if (cth.open && cth.tab === "record") renderCounting(); });
}

function crtShown(d) {
  const v = cthView(cth.data);
  const at = (r) => [r.start, r.soldAt, r.takenAt, r.ended].filter((t) => t != null);
  return d.auctions.filter((r) => at(r).some((t) => t >= v.from && t <= v.to));
}
function crtPart(r) {
  if (r.outcome === "sold" || r.outcome === "partly") return r.sure === "certain" ? "sold" : r.sure === "guess" ? "guess" : "known";
  if (r.outcome === "expired" || r.outcome === "removed") return "expired";
  return r.outcome === "cancelled" ? "cancelled" : null;
}
const crtEndOf = (r) => r.soldAt ?? r.takenAt ?? r.ended ?? r.invoice?.seen ?? null;


function crtLinesHtml(d, shown) {
  const count = (o) => shown.filter((r) => o.includes(r.outcome)).length;
  const sold = shown.filter((r) => r.outcome === "sold" || r.outcome === "partly");
  const by = (s) => sold.filter((r) => r.sure === s).length;
  const top = [crtW("summary", { sold: num(sold.length), expired: num(count(["expired", "removed"])), cancelled: num(count(["cancelled"])),
    open: num(count(["open"])) })];
  if (count(["ended"])) top.push(wordCount("page.counting.record.summary.ended", count(["ended"])));
  const lines = [];
  if (sold.length) {
    const parts = CRT_SURE.slice().reverse().filter((s) => by(s)).map((s) => wordCount(`page.counting.record.sure.n.${s}`, by(s)));
    const said = parts.length > 1 ? `${parts.slice(0, -1).join(", ")} ${crtW("and")} ${parts[parts.length - 1]}` : parts[0];
    lines.push(crtW("sure.line", { parts: said }));
  }
  const th = d.theta?.item;
  if (sold.some((r) => r.sure === "guess") || d.notices.some((n) => n.sure === "guess")) {
    lines.push(th?.n ? wordCount("page.counting.record.theta", th.n, { chance: crtChance(th.cheapest2) }) : crtW("theta.none"));
  }
  const cut = d.rules?.cut, dep = d.rules?.deposit;
  lines.push(cut ? wordCount("page.counting.record.cut", cut.n, { pct: `${(cut.share * 100).toFixed(1)}%` }) : crtW("cut.none"));
  const last = dep ? Object.entries(dep).sort((a, b) => b[1].seen - a[1].seen)[0] : null;
  if (last) {
    const [dur, x] = last, span = d.rules.durations?.[dur], name = d.infos?.[String(x.item)]?.n || "";
    lines.push(span ? crtW("deposit", { span: roughSpan(span), coins: moneyText(x.deposit), units: num(x.units), name })
      : crtW("deposit.any", { coins: moneyText(x.deposit), units: num(x.units), name }));
  } else lines.push(crtW("deposit.none"));
  const para = (l) => `<p class="muted">${esc(l)}</p>`;
  return `<div class="crt-lines">${top.map(para).join("")}<div class="fold plus-fold crt-more${crt.more ? " open" : ""}"><button class="fold-plus"
    data-crt-more="1" aria-expanded="${crt.more}">${esc(crtW("more"))}</button><div class="fold-more">${lines.map(para).join("")}</div></div></div>`;
}

function crtClick(e) {
  if (!e.target.closest?.("button[data-crt-more]")) return false;
  crt.more = !crt.more;
  renderCounting();
  return true;
}


function crtDays(view) {
  const out = [], d = new Date(view.from * 1000);
  d.setHours(0, 0, 0, 0);
  while (d.getTime() / 1000 < view.to) {
    const from = d.getTime() / 1000;
    d.setDate(d.getDate() + 1);
    out.push({ from, to: d.getTime() / 1000, label: new Date(from * 1000).toLocaleDateString([], { day: "numeric", month: "short" }) });
  }
  return out;
}

function crtChartSvg(d, shown, w) {
  const view = cthView(cth.data), days = crtDays(view), scale = timeScale(view.from, view.to, w);
  const bins = days.map((day) => {
    const mine = shown.filter((r) => { const t = crtEndOf(r); return t != null && t >= day.from && t < day.to; });
    const up = CRT_PARTS.map(([part, series, key]) => {
      const n = mine.filter((r) => crtPart(r) === part).length;
      return n ? { series, unknown: part === "guess", v: n, title: crtW("chart.bar", { when: day.label, n: num(n), what: crtW(key) }) } : null;
    }).filter(Boolean);
    return { from: day.from, to: day.to, up, down: [] };
  });
  const legend = CRT_PARTS.map(([part, series, key]) => ({ look: part === "guess" ? "up-unknown" : `up-s${series}`, name: crtW(key) }));
  const bars = ckSignedBarsSvg({ id: "crt-days", width: w, high: CRT_BARS, view, scale, bins, line: [], label: num, legend });
  const gold = days.map((day) => {
    const v = shown.filter((r) => r.taken != null && r.takenAt >= day.from && r.takenAt < day.to).reduce((s, r) => s + r.taken, 0);
    return { from: day.from, to: day.to, parts: v ? [{ series: 1, v, title: crtW("chart.gold.bar", { when: day.label, money: moneyText(v) }) }] : [] };
  });
  const most = Math.max(0, ...gold.map((b) => b.parts[0]?.v || 0));
  const goldSvg = most ? ckBarsSvg({ id: "crt-gold", width: w, high: CRT_GOLD, view, scale, bins: gold,
    values: { ...valueTicks(most, 3), label: goldText }, legend: [{ look: "s1", name: crtW("chart.gold.key") }] })
    : `<p class="muted">${esc(crtW("chart.gold.none"))}</p>`;
  return `${bars}<h4 class="cth-sub">${esc(crtW("chart.gold"))}</h4>${goldSvg}`;
}


function crtFlowSvg(d, shown, w) {
  const names = [...new Set(shown.map((r) => r.char))], series = ckSeriesOf(names);
  const who = (k) => d.characters.find((c) => c.key === k)?.name || k;
  const left = names.map((k) => ({ name: who(k), series: series[k], v: shown.filter((r) => r.char === k).length,
    title: `${who(k)}: ${num(shown.filter((r) => r.char === k).length)}` }));
  const outcome = (part, label, extra = {}) => {
    const v = shown.filter((r) => (["open", "ended"].includes(part) ? r.outcome === part : crtPart(r) === part)).length;
    return v ? { name: label, v, title: `${label}: ${num(v)}`, ...extra } : null;
  };
  const taken = shown.filter((r) => r.taken != null).reduce((s, r) => s + r.taken, 0);
  const sold = outcome("sold", crtW("chart.sold"), { series: 1 });
  if (sold && taken) sold.title = wordCount("page.counting.record.diagram.sold", sold.v, { money: moneyText(taken) });
  const right = [sold, outcome("known", crtW("chart.sold.known"), { series: 2 }),
    outcome("guess", crtW("chart.sold.guess"), { unknown: true }), outcome("expired", crtW("chart.expired"), { series: 5 }),
    outcome("cancelled", crtW("chart.cancelled"), { series: 6 }), outcome("ended", crtW("outcome.ended"), { series: 4 }),
    outcome("open", crtW("outcome.open"), { series: 3 })].filter(Boolean);
  const high = Math.max(160, 46 * Math.max(left.length, right.length));
  return ckSankeySvg({ id: "crt-flow", width: w, high, left, right, middle: crtW("diagram.middle"), label: num });
}

function crtTookHtml(d, shown, w) {
  const known = shown.filter((r) => r.took != null && r.sure !== "guess").map((r) => r.took).sort((a, b) => a - b);
  if (!known.length) return `<p class="muted">${esc(crtW("diagram.took.none"))}</p>`;
  const median = known.length % 2 ? known[(known.length - 1) / 2] : (known[known.length / 2 - 1] + known[known.length / 2]) / 2;
  const rows = CRT_TOOK.map((edge, i) => {
    const lo = i ? CRT_TOOK[i - 1] : -1, n = known.filter((t) => t > lo && t <= edge).length;
    return { name: crtW("diagram.took.bin", { span: roughSpan(edge) }), v: n, tone: "gain", title: wordCount("page.counting.record.diagram.took.bar", n) };
  });
  const over = known.filter((t) => t > CRT_TOOK[CRT_TOOK.length - 1]).length;
  rows.push({ name: crtW("diagram.took.bin.more", { span: roughSpan(CRT_TOOK[CRT_TOOK.length - 1]) }), v: over, tone: "gain",
    title: wordCount("page.counting.record.diagram.took.bar", over) });
  return `<p class="muted">${esc(wordCount("page.counting.record.diagram.took.median", known.length, { span: playedText(median) }))}</p>${
    ckHBarsSvg({ id: "crt-took", width: w, label: num, rows, legend: [{ look: "tone-gain", name: crtW("diagram.took.key") }] })}`;
}


function crtGuessTip(d, r) {
  const n = d.notices.find((x) => x.auction === r.key && x.sure === "guess");
  if (!n) return crtW("sure.guess.tip");
  const rows = Object.fromEntries(d.auctions.map((a) => [a.key, a]));
  const lines = [crtW("guess.row", { chance: crtChance(n.chance || 0), name: n.name || "", when: crtWhen(n.t) }), crtW("guess.candidates"),
    ...n.candidates.map((c) => { const a = rows[c.key] || {};
      return crtW("guess.candidate", { units: num(a.units || 0), coins: moneyText(a.buyout || 0), when: crtWhen(a.start), chance: crtChance(c.chance) }); })];
  if (n.none > 0) lines.push(crtW("guess.none", { chance: crtChance(n.none) }));
  return lines.join("\n");
}

function crtColumns(d) {
  const now = d.now, chars = new Set(d.auctions.map((r) => r.char));
  const who = (k) => d.characters.find((c) => c.key === k)?.name || "";
  const outcome = (r) => `<span${r.outcome === "ended" ? ` title="${esc(crtW("outcome.ended.tip"))}"` : ""}>${esc(crtW(`outcome.${r.outcome}`))}</span>`;
  const sure = (r) => {
    if (!r.sure && r.chanceSold) {
      return `<span class="crt-sure crt-guess" title="${esc(crtW("sure.open.tip"))}">${esc(crtW("sure.open", { chance: crtChance(r.chanceSold) }))}</span>`;
    }
    if (!r.sure) return "";
    const word = r.sure === "guess" ? `${crtW("sure.guess")} ${crtChance(r.chance ?? 0)}` : crtW(`sure.${r.sure}`);
    const tip = r.sure === "guess" ? crtGuessTip(d, r) : crtW(`sure.${r.sure}.tip`);
    return `<span class="crt-sure crt-${esc(r.sure)}" title="${esc(tip)}">${esc(word)}</span>`;
  };
  const gold = (r) => (r.taken != null ? ckGold(r.taken) : r.invoice?.money != null ? `<span class="muted">${ckGold(r.invoice.money)}</span>` : "");
  const fee = (r) => (["expired", "cancelled"].includes(r.outcome) ? r.deposit || 0 : 0) + (r.invoice?.cut || 0);
  const fees = (r) => (fee(r) ? ckGold(fee(r)) : "");
  const posted = (r) => `${esc(crtWhen(r.start))}${ckAgeTag(r.start, now)}${r.posted == null ? ` <small class="muted" title="${esc(crtW("col.posted.seen.tip"))}">*</small>` : ""}`;
  return [
    { key: "posted", label: crtW("col.posted"), value: (r) => r.start, cell: posted },
    ...(chars.size > 1 ? [{ key: "char", label: crtW("col.char"), value: (r) => who(r.char), cell: (r) => esc(who(r.char)) }] : []),
    { key: "item", label: crtW("col.item"), value: (r) => (r.name || "").toLowerCase(), cell: (r) => crtItem(d, r) },
    { key: "units", label: crtW("col.units"), num: true, value: (r) => r.units, cell: (r) => num(r.units || 0) },
    { key: "price", label: crtW("col.price"), tip: crtW("col.price.tip"), num: true, value: (r) => r.buyout, cell: (r) => (r.buyout ? ckGold(r.buyout) : "") },
    { key: "outcome", label: crtW("col.outcome"), value: (r) => r.outcome, cell: outcome },
    { key: "sure", label: crtW("col.sure"), tip: crtW("col.sure.tip"), value: (r) => CRT_SURE.indexOf(r.sure), cell: sure },
    { key: "gold", label: crtW("col.gold"), tip: crtW("col.gold.tip"), num: true, value: (r) => r.taken ?? r.invoice?.money ?? null, cell: gold },
    { key: "fees", label: crtW("col.fees"), tip: crtW("col.fees.tip"), num: true, value: fee, cell: fees },
    { key: "took", label: crtW("col.took"), tip: crtW("col.took.tip"), num: true, value: (r) => r.took ?? null,
      cell: (r) => (r.took != null ? `<span${r.sure === "guess" ? ' class="muted"' : ""}>${esc(playedText(r.took))}</span>` : "") },
  ];
}

function crtItemsHtml(d) {
  const rate = (s) => (s.saleRate == null ? "" : `${Math.round(s.saleRate * 100)}%`);
  const took = (s) => (s.took == null ? "" : esc(wordCount("page.counting.record.items.took.n", s.tookN, { span: playedText(s.took) })));
  return `<h4 class="cth-sub">${esc(crtW("items.title"))}</h4>${ckTable({ id: "crt-items", rows: d.items, sort: { key: "sold", down: true }, columns: [
    { key: "item", label: crtW("col.item"), value: (s) => (s.name || "").toLowerCase(), cell: (s) => crtItem(d, s) },
    { key: "sold", label: crtW("items.sold"), num: true, value: (s) => s.sold, cell: (s) => num(s.sold) },
    { key: "expired", label: crtW("items.expired"), num: true, value: (s) => s.expired, cell: (s) => num(s.expired) },
    { key: "cancelled", label: crtW("items.cancelled"), num: true, value: (s) => s.cancelled, cell: (s) => num(s.cancelled) },
    { key: "rate", label: crtW("items.rate"), tip: crtW("items.rate.tip"), num: true, value: (s) => s.saleRate, cell: rate },
    { key: "since", label: crtW("items.since"), num: true, value: (s) => s.expiriesSince, cell: (s) => num(s.expiriesSince) },
    { key: "took", label: crtW("items.took"), tip: crtW("items.took.tip"), num: true, value: (s) => s.took, cell: took }] })}`;
}

function crtSalesHtml(d) {
  if (!d.sales.length) return "";
  return `<h4 class="cth-sub">${esc(crtW("sales.title"))}</h4><p class="muted">${esc(crtW("sales.note"))}</p>${ckTable({ id: "crt-sales", rows: d.sales,
    sort: { key: "when", down: true }, columns: [
      { key: "when", label: crtW("sales.when"), value: (s) => s.t, cell: (s) => `${esc(crtWhen(s.t))}${ckAgeTag(s.t, d.now)}` },
      { key: "item", label: crtW("col.item"), value: (s) => (s.name || "").toLowerCase(), cell: (s) => crtItem(d, s) },
      { key: "units", label: crtW("col.units"), num: true, value: (s) => s.units, cell: (s) => (s.units ? num(s.units) : "") },
      { key: "price", label: crtW("col.price"), num: true, value: (s) => s.buyout, cell: (s) => (s.buyout ? ckGold(s.buyout) : "") },
      { key: "sure", label: crtW("col.sure"), value: (s) => CRT_SURE.indexOf(s.sure), cell: (s) => `<span title="${esc(crtW(`sure.${s.sure}.tip`))}">${
        esc(s.pending ? crtW("sales.pending") : crtW(`sure.${s.sure}`))}</span>` },
      { key: "gold", label: crtW("col.gold"), num: true, value: (s) => s.money, cell: (s) => (s.money == null ? ""
        : s.sure === "certain" ? ckGold(s.money) : `<span class="muted">${ckGold(s.money)}</span>`) }] })}`;
}

function crtBidsHtml(d) {
  const bids = d.bids.filter((b) => b.how === "bid");
  if (!bids.length) return "";
  return `<h4 class="cth-sub">${esc(crtW("bids.title"))}</h4>${ckTable({ id: "crt-bids", rows: bids, sort: { key: "when", down: true }, columns: [
    { key: "when", label: crtW("col.posted"), value: (b) => b.t, cell: (b) => esc(crtWhen(b.t)) },
    { key: "item", label: crtW("col.item"), value: (b) => b.item, cell: (b) => crtItem(d, b) },
    { key: "paid", label: crtW("bids.paid"), num: true, value: (b) => b.paid, cell: (b) => ckGold(b.paid) },
    { key: "outcome", label: crtW("col.outcome"), value: (b) => b.outcome, cell: (b) => esc(crtW(`bids.${b.outcome}`)) },
    { key: "refund", label: crtW("bids.refund"), num: true, value: (b) => b.refund ?? null, cell: (b) => (b.refund ? ckGold(b.refund) : "") }] })}`;
}


function crtPanelHtml() {
  crtLoad();
  const d = crt.data;
  let body, views = [], view = null;
  if (!d) body = `<p class="muted">${esc(crt.failed ? cthW("failed") : crtW("loading"))}</p>`;
  else if (!d.made) body = `<p class="cth-empty">${esc(crtW("none"))}</p><p class="muted cth-flavour">${esc(crtW("none.flavour"))}</p>${crtLinesHtml(d, [])}`;
  else {
    views = CRT_VIEWS;
    view = ckViewOf("crt-record", CRT_VIEWS);
    const shown = crtShown(d);
    const inner = view === "table" ? `<div class="ctm-table">${ckTable({ id: "crt-record", columns: crtColumns(d), rows: shown, sort: { key: "posted", down: true } })}</div>${
      crtItemsHtml(d)}${crtSalesHtml(d)}${crtBidsHtml(d)}`
      : view === "chart" ? `<h4 class="cth-sub">${esc(crtW("chart.title"))}</h4><div class="tc-box"><div class="crt-plot" data-crt-plot="chart"></div></div>`
        : `<h4 class="cth-sub">${esc(crtW("diagram.flow"))}</h4><div class="crt-plot" data-crt-plot="flow"></div><h4 class="cth-sub">${
          esc(crtW("diagram.took"))}</h4><div class="crt-plot" data-crt-plot="took"></div>`;
    body = `${crtLinesHtml(d, shown)}${inner}`;
  }
  return ckPanelHtml({ id: "crt-record", icon: CRT_ICON, title: crtW("title"), views, view, body });
}

function crtDraw() {
  const d = crt.data;
  if (!d?.made) return;
  const shown = crtShown(d);
  for (const host of $("counting").querySelectorAll(".crt-plot")) {
    const w = Math.max(240, Math.floor(host.clientWidth)), what = host.dataset.crtPlot;
    const draw = { chart: () => crtChartSvg(d, shown, w), flow: () => crtFlowSvg(d, shown, w), took: () => crtTookHtml(d, shown, w) }[what];
    if (draw) setHtml(host, draw());
  }
}
