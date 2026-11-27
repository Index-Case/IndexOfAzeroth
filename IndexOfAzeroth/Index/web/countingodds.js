// The Index of Azeroth. Copyright 2026 Index Case <indexofazeroth@pm.me>. PolyForm Strict 1.0.0, see LICENSE.md.
"use strict";

const CTO_W = wordsOf("page.counting.odds");
const ctoW = (key, fill) => fillWords(CTO_W[key], fill) ?? "";
const CTO_VIEWS = ["chart", "diagram", "table"];
const CTO_ICON = "spell_holy_sealofwisdom";
const CTO_SETS = ["all", "high", "medium", "low"];
const CTO_PLOT = 260;
const cto = { data: null, asked: null, failed: false };

const ctoPct = (v) => `${Math.round(v * 100)}%`;
const ctoPct1 = (v) => `${(v * 100).toFixed(1)}%`;

function ctoLoad() {
  if (!cth.data) return;
  const asked = `house=${encodeURIComponent(cth.data.house || "")}`;
  if (!cthAsks(cto, asked, !cto.data)) return;
  getJson(`/api/counting/odds?${asked}`, { key: "/api/counting/odds", force: true })?.then((d) => {
    if (asked !== cto.asked) return;
    cto.data = d;
    cto.failed = false;
    renderCounting();
  }, () => { cto.failed = true; renderCounting(); });
}

function ctoRows(d) {
  const out = [];
  for (const figure of ["price", "sales"]) {
    const f = d[figure];
    if (!f) continue;
    for (const set of CTO_SETS) {
      const part = set === "all" ? f : f.words?.[set];
      if (!part?.shown?.n) continue;
      const e = part.error || {};
      const error = e.median == null ? "" : figure === "price" ? ctoW("cell.error.price", { error: ctoPct(e.median) })
        : ctoW("cell.error.sales", { error: ctmUnits(e.median) });
      out.push({ figure, set, score: part.shown, error, key: `${figure}.${set}` });
    }
  }
  return out;
}

function ctoVerdict(s) {
  const b = s.bins.find((x) => x.counts);
  if (s.holds == null || !b) return "thin";
  return s.holds ? "holds" : b.o < b.p ? "fails" : "over";
}

const ctoTip = (r) => {
  const b = r.score.bins[0];
  return ctoW("chart.row", { figure: ctoW(`figure.${r.figure}`), set: ctoW(`set.${r.set}`), share: ctoPct(r.score.came), n: num(r.score.n),
    low: ctoPct(b.lo), high: ctoPct(b.hi) });
};

function ctoRangesSvg(d, w, figure) {
  const legend = [{ look: "tone-loss", name: ctoW("legend.fails"), tip: ctoW("verdict.fails.tip") }, { look: "tone-flat", name: ctoW("legend.rest") },
    { look: "whisker", name: ctoW("legend.share") }];
  return ckHBarsSvg({ id: `cto-${figure}`, width: w, label: ctoPct, legend, rows: ctoRows(d).filter((r) => r.figure === figure).map((r) => ({ name: ctoW(`set.${r.set}`), v: r.score.came,
    lo: r.score.bins[0].lo, hi: r.score.bins[0].hi, tone: ctoVerdict(r.score) === "fails" ? "loss" : "flat", title: ctoTip(r) })) });
}

function ctoReliabilitySvg(rec, w, id = "cto-record") {
  const ticks = ckAcross(0, 1, ctoPct, 5);
  return ckPlotSvg({ id, width: w, high: CTO_PLOT, x: { from: 0, to: 1, ticks }, y: { bottom: 0, top: 1, ticks: [0, 0.25, 0.5, 0.75, 1], label: ctoPct },
    lines: [{ points: [{ x: 0, v: 0 }, { x: 1, v: 1 }], kind: "soft" }],
    bars: rec.bins.map((b) => ({ x0: b.p - 0.004, x1: b.p + 0.004, v0: b.lo, v1: b.hi, series: 1, title: ctoBinTip(b) })),
    dots: rec.bins.map((b) => ({ x: b.p, v: b.o, hollow: !b.counts, title: ctoBinTip(b) })),
    legend: [{ look: "line-soft", name: ctoW("legend.diagonal") }, { look: "dot", name: ctoW("legend.group") }, { look: "hollow", name: ctoW("legend.few") },
      { look: "s1", name: ctoW("legend.share") }] });
}
const ctoBinTip = (b) => ctoW("record.bin", { low: ctoPct(b.low), high: ctoPct(b.high), n: num(b.n), share: ctoPct(b.o), lo: ctoPct(b.lo), hi: ctoPct(b.hi) });

function ctoRecordHtml(d, table) {
  const rec = d.record;
  const head = `<h4 class="cth-sub">${esc(ctoW("record"))}</h4>`;
  if (rec.n < rec.needs) {
    return `${head}<p>${esc(ctoW("record.thin", { n: num(rec.n), needs: num(rec.needs) }))}</p><p class="muted">${esc(ctoW("record.how"))}</p>
      <p class="muted cth-flavour">${esc(ctoW("record.thin.flavour"))}</p>`;
  }
  if (table) {
    return `${head}${ckTable({ id: "cto-record", rows: rec.bins, columns: [
      { key: "bin", label: ctoW("col.bin"), value: (b) => b.low, cell: (b) => esc(`${ctoPct(b.low)} to ${ctoPct(b.high)}`) },
      { key: "n", label: ctoW("col.n"), num: true, value: (b) => b.n, cell: (b) => num(b.n) },
      { key: "came", label: ctoW("col.came"), num: true, value: (b) => b.o, cell: (b) => esc(ctoPct(b.o)) },
      { key: "interval", label: ctoW("col.interval"), value: (b) => b.lo, cell: (b) => esc(`${ctoPct(b.lo)} to ${ctoPct(b.hi)}`) },
    ], sort: { key: "bin", down: false } })}`;
  }
  return `${head}<div class="tc-box ck-ends"><div class="ctm-plot" data-cto-plot="record"></div></div><p class="ck-legend">${esc(ctoW("record.key"))}</p>`;
}

const CTO_PICK_WAYS = ["before", "after", "shown"];
const CTO_PICK_SETS = ["sells", "one"].flatMap((t) => CTO_PICK_WAYS.map((w) => `${t}.${w}`));
const ctoPickVerdict = (s) => (s.holds == null ? "thin" : s.holds ? "holds" : s.came < s.predicted ? "low" : "high");
const ctoEdgeW = (key, pk) => {
  const edge = pk?.sells?.seen?.edge;
  return edge == null ? ctoW(`${key}.any`) : ctoW(key, { edge: roughSpan(edge * 3600) });
};
function ctoPicksHtml(d, table) {
  const pk = d.picks;
  const title = `<h4 class="cth-sub" title="${esc(ctoEdgeW("picks.tip", pk))}">${esc(ctoW("picks"))}</h4>`;
  if (!pk?.sells?.before?.n) return pk?.sells?.apart ? `${title}<p class="muted">${esc(ctpApartLine(pk.sells.apart))}</p>` : "";
  const bands = (t) => pk[t]?.use || { corrected: 0, capped: 0, of: 0 };
  const use = ctoW("picks.use", { sells: num(bands("sells").corrected), sellsof: num(bands("sells").of), sellscapped: num(bands("sells").capped || 0),
    one: num(bands("one").corrected), oneof: num(bands("one").of), onecapped: num(bands("one").capped || 0) });
  const levels = (pk.sells.above || []).map((l) => {
    const span = l.high == null ? ctoW("picks.range.top", { low: l.low }) : ctoW("picks.range", { low: l.low, high: l.high });
    const n = l.before?.n || 0;
    return `<p class="muted">${esc(l.steps?.length ? ctoW("picks.level", { span, n: num(n), came: ctoPct(l.before.came) })
      : ctoW("picks.level.thin", { span, n: num(n) }))}</p>`;
  }).join("");
  const fl = pk.flips;
  const flips = fl?.n ? `<p class="muted">${esc(ctoW("picks.flips", { n: num(fl.n), gained: num(fl.gained), lost: num(fl.lost),
    net: `${fl.net < 0 ? "-" : ""}${moneyText(Math.abs(fl.net))}` }))}</p>` : "";
  const head = `${title}<p class="muted">${esc(use)}</p>${levels}${flips}`;
  if (!table) {
    return `${head}${CTO_PICK_WAYS.filter((w) => pk.sells[w]?.n).map((w) => `<h4 class="cth-sub">${esc(ctoW(`picks.set.sells.${w}`))}</h4>
      <div class="tc-box ck-ends"><div class="ctm-plot" data-cto-plot="picks.${w}"></div></div>`).join("")}<p class="ck-legend">${esc(ctoW("picks.key"))}</p>`;
  }
  const rows = CTO_PICK_SETS.map((set) => ({ set, ...(pk[set.split(".")[0]]?.[set.split(".")[1]] || {}) })).filter((r) => r.n);
  return `${head}${ckTable({ id: "cto-picks", rows, sort: { key: "set", down: false }, columns: [
    { key: "set", label: ctoW("col.set"), value: (r) => CTO_PICK_SETS.indexOf(r.set), cell: (r) => esc(ctoW(`picks.set.${r.set}`)) },
    { key: "n", label: ctoW("col.n"), tip: ctoEdgeW("picks.n.tip", pk), num: true, value: (r) => r.n, cell: (r) => num(r.n) },
    { key: "predicted", label: ctoW("col.predicted"), num: true, value: (r) => r.predicted, cell: (r) => esc(ctoPct(r.predicted)) },
    { key: "came", label: ctoW("col.came"), num: true, value: (r) => r.came, cell: (r) => esc(ctoPct(r.came)) },
    { key: "verdict", label: ctoW("col.verdict"), value: (r) => ctoPickVerdict(r), cell: (r) => {
      const v = ctoPickVerdict(r);
      return `<span class="cto-verdict ${v === "low" ? "fails" : v}" title="${esc(ctoW(`picks.verdict.${v}.tip`))}">${esc(ctoW(`picks.verdict.${v}`))}</span>`;
    } },
  ] })}`;
}

function ctoTableHtml(d) {
  const ranges = ckTable({ id: "cto-ranges", rows: ctoRows(d), sort: { key: "figure", down: false }, columns: [
    { key: "figure", label: ctoW("col.figure"), value: (r) => (r.figure === "price" ? 0 : 10) + CTO_SETS.indexOf(r.set), cell: (r) => esc(ctoW(`figure.${r.figure}`)) },
    { key: "set", label: ctoW("col.set"), value: (r) => CTO_SETS.indexOf(r.set), cell: (r) => esc(ctoW(`set.${r.set}`)) },
    { key: "n", label: ctoW("col.n"), tip: ctoW("col.n.tip"), num: true, value: (r) => r.score.n, cell: (r) => num(r.score.n) },
    { key: "held", label: ctoW("col.held"), tip: ctoW("col.held.tip"), num: true, value: (r) => r.score.came, cell: (r) => esc(ctoPct(r.score.came)) },
    { key: "interval", label: ctoW("col.interval"), value: (r) => r.score.bins[0].lo, cell: (r) => esc(`${ctoPct1(r.score.bins[0].lo)} to ${ctoPct1(r.score.bins[0].hi)}`) },
    { key: "verdict", label: ctoW("col.verdict"), value: (r) => ctoVerdict(r.score), cell: (r) => {
      const v = ctoVerdict(r.score);
      return `<span class="cto-verdict ${v}" title="${esc(ctoW(`verdict.${v}.tip`))}">${esc(ctoW(`verdict.${v}`))}</span>`;
    } },
    { key: "error", label: ctoW("col.error"), tip: ctoW("col.error.tip"), value: (r) => r.error, cell: (r) => esc(r.error) },
  ] });
  const states = Object.entries(d.states || {}).map(([key, s]) => ({ ...s, state: key.split(" ")[0], how: key.split(" ")[1] || "" }));
  const order = ["spiking", "rising", "stable", "falling", "crashing"], hows = ["", "sure", "uncertain"];
  const stateName = (s) => (s.how === "sure" ? ctoW("state.sure", { state: ctmState(s.state) }) : ctmState(s.state, s.how === "uncertain"));
  const st = states.length ? `<h4 class="cth-sub" title="${esc(ctoW("states.tip"))}">${esc(ctoW("states"))}</h4>${ckTable({ id: "cto-states", rows: states,
    sort: { key: "state", down: false }, columns: [
      { key: "state", label: ctoW("col.state"), value: (s) => order.indexOf(s.state) * hows.length + hows.indexOf(s.how),
        cell: (s) => `<span class="ctm-state ck-tone-${ckToneOf(s.state)}">${esc(stateName(s))}</span>` },
      { key: "n", label: ctoW("col.n"), num: true, value: (s) => s.n, cell: (s) => num(s.n) },
      { key: "same", label: ctoW("col.same"), num: true, value: (s) => s.same, cell: (s) => esc(ctoPct(s.same)) },
      { key: "side", label: ctoW("col.side"), num: true, value: (s) => s.side, cell: (s) => esc(ctoPct(s.side)) },
    ] })}` : "";
  return `<div class="ctm-table">${ranges}</div>${st}<div class="ctm-table">${ctoPicksHtml(d, true)}</div><div class="ctm-table">${ctoRecordHtml(d, true)}</div>`;
}

function ctoPanelHtml() {
  ctoLoad();
  const d = cto.data;
  let body, views = [], latest = "", view = null;
  if (!d) body = `<p class="muted">${esc(cto.failed ? cthW("failed") : ctoW("loading"))}</p>`;
  else if (!d.made) {
    const busy = d.summarising ? `<p class="muted cti-note">${esc(ctoW("summarising"))}</p>` : "";
    body = `${busy}<p class="cth-empty">${esc(ctoW("none"))}</p><p class="muted cth-flavour">${esc(ctoW("none.flavour"))}</p>`;
  } else {
    views = CTO_VIEWS;
    view = ckViewOf("cto-odds", CTO_VIEWS);
    const ds = d.density || {};
    latest = cthRestsOn(ctoW, "latest", ds.last, d.now);
    const head = `<div class="ctm-notes"><p>${esc(ctoW("intro"))}</p><p class="muted">${esc(ctoW("density", { scans: num(ds.scans || 0), days: num(ds.days || 0),
      gap: roughSpan((ds.gap || 0) * 3600), longest: roughSpan((ds.longest || 0) * 3600) }))}</p></div>`;
    const shown = view === "table" ? ctoTableHtml(d) : view === "diagram" ? `${ctoPicksHtml(d, false)}${ctoRecordHtml(d, false)}`
      : `<h4 class="cth-sub">${esc(ctoW("chart.ranges"))}</h4>${["price", "sales"].filter((f) => d[f]).map((f) =>
        `<h4 class="cth-sub">${esc(ctoW(`figure.${f}`))}</h4><div class="ctm-plot" data-cto-plot="${f}"></div>`).join("")}<p class="ck-legend">${esc(ctoW("chart.ranges.key"))}</p>`;
    body = `${head}${shown}<p class="muted cti-note">${esc(ctoW("measured"))}</p>`;
  }
  return ckPanelHtml({ id: "cto-odds", icon: CTO_ICON, title: ctoW("title"), latest, views, view, body });
}

function ctoDraw() {
  const d = cto.data;
  if (!d?.made) return;
  for (const host of $("counting").querySelectorAll("[data-cto-plot]")) {
    const w = Math.max(240, Math.floor(host.clientWidth));
    const what = host.dataset.ctoPlot;
    setHtml(host, what === "record" ? ctoReliabilitySvg(d.record, w)
      : what.startsWith("picks.") ? ctoReliabilitySvg(d.picks.sells[what.slice(6)], w, `cto-${what.replace(".", "-")}`)
      : ctoRangesSvg(d, w, what));
  }
}
