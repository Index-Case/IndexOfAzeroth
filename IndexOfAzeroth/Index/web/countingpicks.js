// The Index of Azeroth. Copyright 2026 Index Case <indexofazeroth@pm.me>. PolyForm Strict 1.0.0, see LICENSE.md.
"use strict";

const CTP_W = wordsOf("page.counting.picks");
const ctpW = (key, fill) => fillWords(CTP_W[key], fill) ?? "";
const ctpCount = (key, n, fill) => wordCount(`page.counting.picks.${key}`, n, fill);
const CTP_VIEWS = ["table", "chart", "diagram"];
const CTP_ICONS = { buy: "inv_misc_coin_01", sell: "inv_misc_coin_03" };
const CTP_TREE = 360, CTP_PLOT = 220;
const CTP_AGAIN_MS = 3000;
const CTP_STEPS_MS = 250;
const CTP_NO_STEPS = 999999999;
const CTP_ROOM = 8;
const ctp = { data: null, asked: null, again: 0, picked: null, list: ctpListRead(), drawer: false, loading: false, askedAt: -1, answeredAt: -1,
  show: null, lastRun: null, stepping: false, stepTimer: 0, raf: 0, note: null, endedRun: null, copyPart: 0 };


function ctpListRead() {
  try { return JSON.parse(ckStored("list") || "[]") || []; } catch (e) { return []; }
}
function ctpListKeep() { ckStore("list", JSON.stringify(ctp.list)); }

function ctpEntry(kind, p, d) {
  const buy = kind === "buy", vendor = !buy && p.way === "vendor";
  const price = buy ? Math.round(p.upTo) : vendor ? Math.round(p.vendorGold / Math.max(1, p.units)) : Math.round(p.listAt);
  const hours = buy ? Math.round((p.hold?.[0] ?? d?.hold?.[0] ?? 0) * (p.hold?.[1] ?? d?.hold?.[1] ?? 1))
    : vendor ? null : Math.round(p.hold?.[0] ?? d?.hold?.[0] ?? 0);
  return { kind: buy ? "buy" : vendor ? "vendor" : "post", item: p.item, name: p.name || p.item,
    units: buy ? p.units : vendor ? p.units : p.post, price, floor: buy ? price : vendor ? null : p.floor ?? null,
    hours, char: buy ? (d?.playing || "") : Object.keys(p.on || {})[0] || "", house: cth.data?.house || "",
    expected: buy ? p.expected : vendor ? p.vendorGold : p.gold, added: Math.round(Date.now() / 1000) };
}

const ctpTradeDuration = (hours) => ((hours || 24) <= 12 ? 1 : (hours || 24) <= 24 ? 2 : 3);
function ctpTradePicks() {
  return ctp.list.map((e) => ({ act: e.kind, item: e.item, units: e.units, price: e.price,
    ...(e.kind === "buy" ? { price: e.floor ?? e.price, floor: e.floor ?? e.price, hours: e.hours } : {}),
    ...(e.kind === "post" ? { duration: ctpTradeDuration(e.hours), floor: e.floor } : {}) }));
}

function ctpCopyLine(part = 0) {
  const picks = ctpTradePicks(), scanned = ctp.data?.newest ?? null, check = tradeCheck(scanned);
  const count = tradeLines(picks, check).lines.length;
  copyTradeLine(picks, count ? part % count : 0, scanned);
  ctp.copyPart = count ? (part + 1) % count : 0;
}

function ctpAddKey(side, p, i) {
  const kind = side === "buy" ? "buy" : p.way === "vendor" ? "vendor" : "post";
  const on = ctp.list.some((e) => e.kind === kind && e.item === p.item);
  return `<button type="button" class="key small square" data-ctp-add="${side}" data-ctp-i="${i}" aria-pressed="${on}"
    title="${esc(ctpW(on ? "add.on.tip" : "add.tip"))}">${on ? "&#10003;" : "+"}</button>`;
}

function ctpListHtml() {
  if (!ctp.drawer) return "";
  const groups = {};
  for (const [i, e] of ctp.list.entries()) (groups[e.char || ctpW("list.nobody")] ||= []).push([i, e]);
  const spent = ctp.list.filter((e) => e.kind === "buy").reduce((s, e) => s + e.units * e.price, 0);
  const expected = ctp.list.reduce((s, e) => s + (e.expected || 0), 0);
  const line = ([i, e]) => `<li>${fillWords(esc(CTP_W[`list.${e.kind}`] ?? ""), { units: num(e.units), name: esc(e.name),
    price: ckGold(e.price || 0), hours: num(e.hours || 0) })}
      <button type="button" class="key small" data-ctp-drop="${i}" title="${esc(ctpW("list.drop.tip"))}">${esc(ctpW("list.drop"))}</button></li>`;
  const body = ctp.list.length ? Object.entries(groups).map(([who, rows]) => `<h4 class="cth-sub">${esc(who)}</h4><ul class="ctp-list">${rows.map(line).join("")}</ul>`).join("")
    : `<p class="muted">${esc(ctpW("list.empty"))}</p>`;
  const sums = ctp.list.length ? `<p>${fillWords(esc(CTP_W["list.sums"]), { spent: ckGold(spent), expected: ckGold(expected) })}</p>` : "";
  return `<aside class="ctp-drawer"><div class="ctp-drawer-head"><b>${esc(ctpW("list.title"))}</b><span class="ctp-drawer-keys">
    <button type="button" class="key small" data-ctp-copy="1" title="${esc(ctpW("list.copy.tip"))}">${esc(ctpW("list.copy"))}</button>
    <button type="button" class="key small square x-mark" data-ctp-close="1" title="${esc(ctpW("list.close.tip"))}">&times;</button></span></div>${sums}${body}
    <p class="muted cti-note">${esc(ctpW("list.note"))}</p></aside>`;
}


function ctpLoad(force = false) {
  if (!cth.data) return;
  const asked = `house=${encodeURIComponent(cth.data.house || "")}`, kept = `${cthShow()}&vendor=${cth.vendor ? 1 : 0}&risk=${cth.risk}`;
  if (!cthAsks(ctp, asked, force, kept)) return;
  clearTimeout(ctp.again);
  const again = () => {
    if (cthAnswered(ctp, asked, kept)) ctp.again = setTimeout(() => { if (cth.open) ctpLoad(true); else ctp.asked = null; }, CTP_AGAIN_MS);
  };
  const at = performance.now();
  const got = getJson(`/api/counting/picks?${asked}&${kept}`, { key: "/api/counting/picks", force: true });
  if (!got) return;
  ctp.loading = true;
  got.then((d) => {
    ctp.loading = false;
    if (!cthAnswered(ctp, asked, kept)) return;
    if (!d.made && ctp.data?.made) d = { ...ctp.data, summarising: true };
    Object.assign(ctp, { data: d, askedAt: at, answeredAt: performance.now() });
    if (!d.made || d.summarising) again();
    renderCounting();
  }, () => {
    ctp.loading = false;
    again();
  });
}


function ctpPictured(side) {
  if (ctp.show && (ctp.show.asked !== ctp.asked || ctp.show.side !== side)) ctp.show = null;
  const last = ctp.lastRun?.asked === ctp.asked && ctp.lastRun.show === cth.show ? ctp.lastRun : null;
  if (!ctp.show && ctp.data && (cth.recalc || (!ctp.data.made && cthWorking(cth.data)))) {
    ctp.note = null;
    ctp.show = { asked: ctp.asked, side, before: last ? (last.done ? last.id : null) : undefined, run: null, from: CTP_NO_STEPS, since: performance.now(), recalc: cth.recalc,
      pic: null, el: null, w: 0, high: 0, skipped: false };
  }
  const s = ctp.show;
  if (s?.recalc && !cth.recalc) Object.assign(s, { recalc: false, since: performance.now() });
  return !!s;
}

const ctpShown = () => cth.open && (cth.tab === "buy" || cth.tab === "sell");

function ctpRecalc() {
  ctp.show = null;
  ctp.note = null;
}

function ctpEnd() {
  ctp.endedRun = ctp.show.run ?? ctp.lastRun?.id ?? null;
  ctp.show = null;
  renderCounting();
}

const ctpAnswerIn = (s) => !!ctp.data && (s.doneAt ? ctp.askedAt >= s.doneAt : !ctp.data.summarising && !cth.recalc && ctp.askedAt >= s.since);

function ctpPicturePlace(s, slot) {
  if (!s.el) {
    s.el = document.createElement("div");
    s.el.className = "ctp-picture";
    s.el.addEventListener("click", ctpSkip);
    const box = slot.closest(".cth-scroll");
    s.w = Math.max(480, Math.floor(slot.clientWidth));
    s.high = box ? Math.floor(box.getBoundingClientRect().bottom - slot.getBoundingClientRect().top) - CTP_ROOM : 0;
    ctpPictureNew(s);
  }
  slot.replaceWith(s.el);
  if (!ctp.raf) ctp.raf = askFrame(ctpFrame);
  if (!ctp.stepping && !ctp.stepTimer) ctpSteps();
}
function ctpPictureNew(s) {
  s.pic = cpxNew(s.side, s.w, {}, lessMotion(), s.high);
  cpxFrame(s.pic, s.el);
}

function ctpFrame() {
  ctp.raf = 0;
  const s = ctp.show;
  if (!s?.pic || !s.el.isConnected) return;
  const now = performance.now();
  cpxDraw(s.pic, now);
  if (s.skipped || cpxOver(s.pic, now)) {
    if (ctpAnswerIn(s)) return ctpEnd();
    if (!ctp.loading && now - ctp.askedAt > CTP_STEPS_MS) ctpLoad(true);
  }
  ctp.raf = askFrame(ctpFrame);
}

function ctpSkip() {
  if (ctp.show?.pic?.done) ctp.show.skipped = true;
}

function ctpSteps() {
  ctp.stepTimer = 0;
  const s = ctp.show, asked = ctp.asked, show = cth.show;
  if (ctp.stepping || !ctpShown() || !asked || (s && !s.pic)) return;
  const sent = { run: s?.run ?? null, at: performance.now() };
  const got = getJson(`/api/counting/picks/steps?${asked}&${cthShow()}&from=${s?.run != null ? s.from : CTP_NO_STEPS}`, { key: "/api/counting/picks/steps", force: true });
  if (!got) return;
  ctp.stepping = true;
  const next = () => {
    ctp.stepping = false;
    const now = ctp.show;
    if (ctpShown() && (now ? now.pic && !now.pic.done : !!ctp.data?.summarising)) ctp.stepTimer = setTimeout(ctpSteps, Math.max(0, CTP_STEPS_MS - (performance.now() - sent.at)));
  };
  got.then((d) => {
    if (asked === ctp.asked && show === cth.show) {
      const first = ctp.lastRun?.asked !== asked;
      ctp.lastRun = { asked, show, id: d.run, done: !!d.done, fresh: d.fresh ?? null, listed: d.listed || 0 };
      if (s && s === ctp.show) ctpFollow(s, d, sent);
      else if (!ctp.show && first) renderCounting();
    }
    next();
  }, next);
}

function ctpFollow(s, d, sent) {
  if (s.before === undefined && d.run != null) s.before = d.done ? d.run : null;
  if (d.run != null && d.run !== s.before) {
    if (d.run !== sent.run) {
      if (s.run != null) ctpPictureNew(s);
      Object.assign(s, { run: d.run, from: 0 });
      return;
    }
    cpxFeed(s.pic, d, performance.now());
    s.from = d.seq;
    if (d.done && !s.doneAt) {
      s.doneAt = performance.now();
      if (!ctp.loading) ctpLoad(true);
    }
    return;
  }
  if (ctpAnswerIn(s) && ctp.askedAt < sent.at) {
    ctp.note = ctp.asked;
    ctpEnd();
  } else if (!ctp.loading && ctp.askedAt < s.since) ctpLoad(true);
}


const ctpOdds = (p) => (p == null ? "" : ctpW("odds", { n: Math.min(9, Math.max(0, Math.floor(p * 10))) }));
const ctpOddsTip = (p) => (p == null ? "" : ctpW("odds.tip", { n: Math.round(p * 100) }));

function ctpHeadHtml(d) {
  const hold = ctpW(d.fees.from.deposit === "game" ? "hold.game" : "hold.guide", { listings: d.hold[1], span: roughSpan(d.hold[0] * 3600) });
  const pop = d.population ? ctpW(`population.${d.population.state}`, { n: Math.round(d.population.trend * 100), low: Math.round(d.population.low * 100),
    high: Math.round(d.population.high * 100) }) : ctpW("population.none");
  const opening = d.openings?.[0];
  const more = [...cthFeesLines(d.fees), hold, pop, ctpW("effects.patch"), ctpW("effects.state"), ctpW("effects.launch"), ctpW("effects.week"),
    opening ? ctpW(`effects.opening.${opening.kind}`, { day: new Date(opening.opens).toLocaleDateString([], { day: "numeric", month: "short" }) }) : ctpW("effects.events")];
  const apart = d.scansApart ? `<p>${esc(ctpApartLine(d.scansApart))}</p>` : "";
  return `<div class="ctp-head"><p>${esc(ctpW(d.fees.read ? "fees.read" : "fees.guide"))}</p>${apart}<details class="ctp-effects"><summary>${esc(ctpW("effects"))}</summary>
    <ul>${more.map((t) => `<li>${esc(t)}</li>`).join("")}</ul></details></div>`;
}
const ctpApartLine = (a) => ctpW("checks.apart", { gap: roughSpan(a.apart * 3600), edge: roughSpan(a.edge * 3600), span: roughSpan(a.span * 3600) });

function ctpRests(p, d) {
  const r = p.rests || {};
  const t = p.tested;
  const lines = [r.scans != null ? ctpW("rests.scans", { n: num(r.scans) }) : "", r.pairs != null ? ctpW("rests.pairs", { n: num(r.pairs) }) : "",
    r.newest ? ctpW("rests.newest", { ago: ago(r.newest, d.now) }) : "",
    p.evidence ? ctpW("rests.evidence", { seen: num(p.evidence.seen), at: num(p.evidence.at) }) : "",
    p.model && p.sells != null && Math.round(p.model.sells * 100) !== Math.round(p.sells * 100)
      ? ctpW("rests.model", { model: Math.round(p.model.sells * 100), shown: Math.round(p.sells * 100) }) : "",
    t ? ctpW("rests.tested", { came: Math.round(t.came * 100), predicted: Math.round(t.predicted * 100), n: num(t.n) }) : "",
    p.kellyLow != null ? ctpW("rests.kellylow", { n: Math.round(p.kellyLow * 100) }) : "",
    ...(p.lowered || []).map((w) => ctpW(`lowered.${w}`))];
  if (p.way === "vendor" && !r.scans) lines.push(ctpW("rests.vendor"));
  return lines.filter(Boolean).join("\n");
}
function ctpQuality(p, d) {
  const bar = Array.from({ length: CK_STEPS }, (_, i) => `<i${i < p.steps ? ' class="on"' : ""}></i>`).join("");
  return `<span class="ck-conf" title="${esc(ctpRests(p, d))}"><span class="ck-conf-bar" aria-hidden="true">${bar}</span>${esc(ckConfidenceWord(p.steps))}</span>`;
}
function ctpWeak(p, side) {
  if (!p.weak?.length) return "";
  const lines = [...p.weak.map((w) => ctpW(`weak.${side}.${w}`)), ...(p.worst < 0 ? [ctpW("weak.worst", { coins: moneyText(-p.worst) })] : [])];
  return `<span class="ctp-weak" title="${esc(lines.join("\n"))}">${esc(ctpW("weak"))}</span>`;
}
const ctpItem = (p, marks) => `<span class="ctp-item">${ckItemHtml({ ...p, key: p.item })}${marks ? `<span class="ctp-marks">${marks}</span>` : ""}</span>`;


function ctpBuyColumns(d) {
  const add = (p, i) => ctpAddKey("buy", p, i);
  const gain = (p) => `<span class="${p.expected >= 0 ? "ctp-gain" : "ctp-loss"}" title="${esc(ctpW("expected.tip", { low: moneyText(p.p10), high: moneyText(p.p90), median: moneyText(p.median) }))}">${
    p.expected >= 0 ? "+" : "&minus;"}${ckGold(Math.abs(p.expected))}</span>`;
  const loseTip = (p) => [ctpW("lose.tip", { n: Math.round(p.lose * 100) }), p.vendor === null ? ctpW("lose.vendor.unknown") : ""].filter(Boolean).join("\n");
  const lose = (p) => (p.worst < 0 ? `<span class="ctp-loss" title="${esc(loseTip(p))}">&minus;${ckGold(-p.worst)}</span>`
    : `<span class="muted" title="${esc(ctpW("lose.none.tip"))}">${esc(ctpW("lose.none"))}</span>`);
  const plan = (p) => (p.plan === "vendor" ? `<span title="${esc(ctpW("plan.vendor.tip"))}">${esc(ctpW("plan.vendor"))} ${ckGold(p.sellAt)}</span>`
    : ckGold(p.sellAt));
  const funded = (p) => (p.funded ? "" : `<span class="muted" title="${esc(ctpW(`unfunded.${p.unfunded}.tip`))}">${esc(ctpW("unfunded"))}</span>`);
  const kind = (p) => `<span class="ctp-kind" title="${esc(ctpW(`kind.${p.kind}.tip`))}">${esc(ctpW(`kind.${p.kind}`))}</span>`;
  return [
    { key: "item", label: ctpW("col.item"), value: (p) => (p.name || p.item).toLowerCase(), cell: (p) => ctpItem(p, `${kind(p)}${ctpWeak(p, "buy")}${funded(p)}`) },
    { key: "buy", label: ctpW("col.buy"), tip: ctpW("col.buy.tip"), num: true, value: (p) => p.units, cell: (p) => `<span title="${esc(ctpCount("buy.tip", p.auctions, { n: num(p.auctions), there: Math.round(p.there * 100) }))}">${num(p.units)}</span>` },
    { key: "upTo", label: ctpW("col.upto"), tip: ctpW("col.upto.tip"), num: true, value: (p) => p.upTo, cell: (p) => ckGold(p.upTo) },
    { key: "sellAt", label: ctpW("col.sellat"), tip: ctpW("col.sellat.tip"), num: true, value: (p) => p.sellAt, cell: plan },
    { key: "sells", label: ctpW("col.sells"), tip: ctpW("col.sells.tip"), num: true, value: (p) => p.sells, cell: (p) => (p.sells == null ? "" : `<span title="${esc(ctpOddsTip(p.sells))}">${esc(ctpOdds(p.sells))}</span>`) },
    { key: "gain", label: ctpW("col.gain"), tip: ctpW("col.gain.tip"), num: true, value: (p) => p.gain, cell: (p) => `<span title="${esc(ctpOddsTip(p.gain))}">${esc(ctpOdds(p.gain))}</span>` },
    { key: "expected", label: ctpW("col.expected"), tip: ctpW("col.expected.tip"), num: true, value: (p) => p.expected, cell: gain },
    { key: "lose", label: ctpW("col.lose"), tip: ctpW("col.lose.tip"), num: true, value: (p) => p.worst, cell: lose },
    { key: "quality", label: ctpW("col.quality"), tip: ctpW("col.quality.tip"), num: true, value: (p) => p.steps, cell: (p) => ctpQuality(p, d) },
    { key: "add", label: "", value: () => null, cell: (p) => add(p, d.buy.picks.indexOf(p)) },
  ];
}

function ctpBuyHtml(d) {
  const b = d.buy, used = d.budget.used;
  const who = d.budget.which === "here" ? ctpW("budget.here") : ctpW("budget.all", { coins: moneyText(d.budget.all || 0) });
  const fundedAny = b.picks.some((p) => p.funded) || !b.picks.length;
  const head = `<p class="ctp-budget">${fillWords(esc(CTP_W[fundedAny ? "budget.line" : "budget.none"]), { who: esc(who), budget: ckGold(used || 0), reserve: Math.round(d.budget.reserve * 100),
    spent: ckGold(b.spent), expected: ckGold(b.expected) })}</p>
    <label class="ctp-vendor" title="${esc(ctpW("vendor.tip"))}"><input type="checkbox" data-cth-vendor="1"${cth.vendor ? " checked" : ""}> ${esc(ctpW("vendor"))}</label>
    <label class="ctp-risk" title="${esc(ctpW("risk.tip"))}">${esc(ctpW("risk"))}
      <input type="range" min="${CTH_RISK_LEAST}" max="${CTH_RISK_MOST}" step="${CTH_RISK_STEP}" value="${cth.risk}" data-cth-risk="1"><output>${cth.risk}&times;</output></label>`;
  const view = ckViewOf("ctp-buy", CTP_VIEWS);
  const noneFunded = b.picks.length && !b.picks.some((p) => p.funded) ? `<p class="cti-note">${esc(ctpW("buy.none.funded"))}</p>` : "";
  const vendorHidden = !cth.vendor && b.hidden ? `<p class="cti-note">${esc(wordCount("page.counting.picks.buy.vendor.hidden", b.hidden))}</p>` : "";
  let body;
  if (!b.picks.length) body = `<p class="cth-empty">${esc(ctpW("buy.none"))}</p><p class="muted cth-flavour">${esc(ctpW("buy.none.flavour"))}</p>`;
  else if (view === "table") body = `<div class="ctm-table">${ckTable({ id: "ctp-buy", columns: ctpBuyColumns(d), rows: b.picks, key: (p) => p.item, sort: { key: "expected", down: true } })}</div>`;
  else if (view === "chart") body = `${ctpAxesPlot("buyodds")}<p class="ck-legend">${esc(ctpW("buy.chart.key"))}</p>`;
  else {
    const picked = b.picks.find((p) => p.item === ctp.picked) || b.picks[0];
    body = `<h4 class="cth-sub">${esc(ctpW("buy.tree"))}</h4><div class="ctp-plot" data-ctp-plot="buytree"></div>
      <h4 class="cth-sub">${esc(ctpW("buy.curve", { name: picked.name || picked.item }))}</h4>${ctpAxesPlot("curve")}
      <p class="ck-legend">${esc(ctpW("buy.curve.key"))}</p>`;
  }
  return ckPanelHtml({ id: "ctp-buy", icon: CTP_ICONS.buy, title: ctpW("buy.title"), latest: cthRestsOn(ctpW, "latest", d.newest, d.now),
    views: CTP_VIEWS, view, body: `${ctpHeadHtml(d)}${head}${vendorHidden}${noneFunded}${body}<p class="muted cti-note">${esc(ctpW("buy.note"))}</p>` });
}


function ctpPaid(p) {
  if (p.paid == null) return "";
  const net = p.gold - p.paid;
  const tip = p.paidUnits < p.units ? ctpW("paid.part.tip", { cost: moneyText(p.paid), n: num(p.paidUnits), units: num(p.units) })
    : ctpCount(net >= 0 ? "paid.more.tip" : "paid.less.tip", p.units, { cost: moneyText(p.paid), units: num(p.units), gold: moneyText(Math.abs(net)) });
  return `<span title="${esc(tip)}">${ckGold(p.paid)}</span>`;
}

function ctpSellColumns(d) {
  const reposted = (p) => (d.reposted || {})[p.item];
  const add = (p, i) => ctpAddKey("sell", p, i);
  const places = (p) => ((d.places || {})[p.bound ? "bound" : "held"] || {})[p.item] || {};
  const seen = (d.places || {}).seen || {};
  const held = (p) => Object.entries(places(p)).map(([who, at]) => ({ who, at }));
  const tip = (p) => cgoSeenTip(held(p).flatMap(({ who, at }) => Object.keys(at).map((w) => [who, w, seen[who]?.[w]])), d.now);
  const on = (p) => Object.entries(p.on || {}).map(([who, n]) => {
    const at = places(p)[who];
    return !at || at.warband ? `${esc(who)} ${num(n)}` : esc(cgoW("where.who", { who, places: cgoPlacesText(at, true) }));
  }).join("<br>");
  const where = (p) => {
    const sum = {};
    for (const { at } of held(p)) for (const [w, n] of Object.entries(at)) sum[w] = (sum[w] || 0) + n;
    return Object.keys(sum).length ? cgoPlaceHtml(cgoPlacesText(sum), tip(p)) : "";
  };
  const way = (p) => (p.bound ? `<span title="${esc(ctpW("way.bound.tip"))}">${esc(ctpW("way.vendor"))} <small class="muted">${esc(ctpW("way.bound"))}</small></span>`
    : p.way === "vendor"
      ? `<span title="${esc(ctpW(p.wayWhy === "noprice" ? "way.vendor.noprice.tip" : "way.vendor.tip"))}">${esc(ctpW("way.vendor"))}</span>`
      : `<span title="${esc(ctpW(`way.${p.way}.tip`))}">${esc(ctpW(`way.${p.way}`))}</span>`);
  return [
    { key: "item", label: ctpW("col.item"), value: (p) => (p.name || p.item).toLowerCase(), cell: (p) => ctpItem(p, ctpWeak(p, "sell")) },
    { key: "on", label: ctpW("col.on"), value: (p) => Object.keys(p.on || {})[0] || "", cell: on },
    { key: "where", label: cgoW("col.where"), tip: cgoW("col.where.tip"), value: (p) => CGO_PLACES.findIndex((w) => held(p).some(({ at }) => at[w])), cell: where },
    { key: "post", label: ctpW("col.post"), tip: ctpW("col.post.tip"), num: true, value: (p) => p.post, cell: (p) => (p.way === "vendor" ? "" : `${num(p.post)} / ${num(p.units)}`) },
    { key: "listAt", label: ctpW("col.listat"), tip: ctpW("col.listat.tip"), num: true, value: (p) => p.listAt,
      cell: (p) => (p.listAt == null ? "" : `${ckGold(p.listAt)}${p.lastScan ? ` <small class="muted" title="${esc(ctpW("listat.last.tip"))}">${esc(ctpW("listat.last"))}</small>` : ""}`) },
    { key: "one", label: ctpW("col.one"), tip: ctpW("col.one.tip"), num: true, value: (p) => p.sellsOne, cell: (p) => esc(ctpOdds(p.sellsOne)) },
    { key: "sells", label: ctpW("col.sells"), tip: ctpW("col.sells.tip"), num: true, value: (p) => p.sells, cell: (p) => esc(ctpOdds(p.sells)) },
    { key: "beats", label: ctpW("col.beats"), tip: ctpW("col.beats.tip"), num: true, value: (p) => p.beats,
      cell: (p) => (p.vendor === null ? `<span class="muted" title="${esc(ctpW("beats.unknown.tip"))}">${esc(ctpW("beats.unknown"))}</span>` : esc(ctpOdds(p.beats))) },
    { key: "gold", label: ctpW("col.gold"), tip: ctpW("col.gold.tip"), num: true, value: (p) => p.gold,
      cell: (p) => `<span title="${esc(p.vendor === null ? ctpW("gold.tip.unknown", { low: moneyText(p.p10), high: moneyText(p.p90) })
        : ctpW("gold.tip", { low: moneyText(p.p10), high: moneyText(p.p90), vendor: moneyText(p.vendorGold) }))}">${ckGold(p.gold)}</span>` },
    { key: "paid", label: ctpW("col.paid"), tip: ctpW("col.paid.tip"), num: true, value: (p) => p.paid, cell: ctpPaid },
    ckRepostsColumn(reposted),
    { key: "way", label: ctpW("col.way"), value: (p) => p.way, cell: way },
    { key: "quality", label: ctpW("col.quality"), tip: ctpW("col.quality.tip"), num: true, value: (p) => p.steps, cell: (p) => ctpQuality(p, d) },
    { key: "add", label: "", value: () => null, cell: (p) => add(p, d.sell.indexOf(p)) },
  ];
}

function ctpSellHtml(d) {
  const view = ckViewOf("ctp-sell", CTP_VIEWS);
  let body;
  if (!d.sell.length) body = `<p class="cth-empty">${esc(ctpW("sell.none"))}</p><p class="muted cth-flavour">${esc(ctpW("sell.none.flavour"))}</p>`;
  else if (view === "table") body = `<div class="ctm-table">${ckTable({ id: "ctp-sell", columns: ctpSellColumns(d), rows: d.sell, key: (p) => p.item, sort: { key: "gold", down: true } })}</div>`;
  else if (view === "chart") body = `${ctpAxesPlot("sellodds")}<p class="ck-legend">${esc(ctpW("sell.chart.key"))}</p>`;
  else body = `<div class="ctp-plot" data-ctp-plot="selltree"></div><p class="ck-legend">${esc(ctpW("sell.tree.key"))}</p>`;
  return ckPanelHtml({ id: "ctp-sell", icon: CTP_ICONS.sell, title: ctpW("sell.title"), latest: cthRestsOn(ctpW, "latest", d.newest, d.now),
    views: CTP_VIEWS, view, body: `${ctpHeadHtml(d)}${body}<p class="muted cti-note">${esc(ctpW("sell.note"))}</p>` });
}


function ctpPanelHtml(which) {
  ctpLoad();
  const d = ctp.data;
  let body;
  if (!d) body = `<p class="muted">${esc(ctpW("loading"))}</p>`;
  else if (ctpPictured(which)) {
    body = ckPanelHtml({ id: `ctp-${which}`, icon: CTP_ICONS[which], title: ctpW(`${which}.title`), views: [], body: '<div class="ctp-picture-slot"></div>' });
  } else if (!d.made) body = `<p class="cth-empty">${esc(ctpW(d.summarising ? "summarising" : "none"))}</p><p class="muted cth-flavour">${esc(ctpW("none.flavour"))}</p>`;
  else if (d.summarising && ctp.lastRun?.asked !== ctp.asked) body = `<p class="muted">${esc(ctpW("summarising"))}</p>`;
  else body = which === "buy" ? ctpBuyHtml(d) : ctpSellHtml(d);
  const note = ctp.note && ctp.note === ctp.asked && !ctp.show ? `<p class="cth-line muted">${esc(cpxW("nothing"))}</p>` : "";
  return `${note}${body}${ctpListHtml()}`;
}


const ctpAxesPlot = (what) => `<div class="tc-box ck-ends"><div class="ctp-plot" data-ctp-plot="${what}"></div></div>`;

function ctpOddsSvg(picks, chance, gold, w, id) {
  const ys = picks.map(gold), lo = Math.min(0, ...ys), hi = Math.max(1, ...ys);
  return ckPlotSvg({ id, width: w, high: CTP_PLOT, x: { from: 0, to: 1, ticks: ckAcross(0, 1, (v) => ctpOdds(v), 5) },
    y: { ...ckAxis(lo, hi), label: goldText },
    rules: [{ v: 0, label: "", title: ctpW("legend.zero") }],
    dots: picks.filter((p) => chance(p) != null).map((p) => ({ x: chance(p), v: gold(p), hollow: p.steps < 2,
      title: `${p.name || p.item}\n${ctpW("dot", { gold: moneyText(Math.round(gold(p))), odds: ctpOdds(chance(p)), word: ckConfidenceWord(p.steps) })}` })),
    legend: [{ look: "dot", name: ctpW("legend.trusted") }, { look: "hollow", name: ctpW("legend.low") }, { look: "rule", name: ctpW("legend.zero") }] });
}

function ctpTreeSvg(groups, w, id, legend) {
  return ckTreemapSvg({ id, width: w, high: CTP_TREE, legend, tiles: groups.filter((g) => g.v > 0).map((g) => ({ v: g.v, name: g.name, word: moneyText(Math.round(g.v)),
    tone: g.tone || "flat", title: `${g.name}\n${moneyText(Math.round(g.v))}` })) });
}

function ctpDraw() {
  const slot = $("counting").querySelector(".ctp-picture-slot");
  if (slot && ctp.show) ctpPicturePlace(ctp.show, slot);
  else if (ctp.asked && (ctp.lastRun?.asked !== ctp.asked || ctp.lastRun.show !== cth.show || ctp.data?.summarising) && !ctp.stepping && !ctp.stepTimer) ctpSteps();
  const d = ctp.data;
  if (!d?.made || ctp.show) return;
  for (const host of $("counting").querySelectorAll(".ctp-plot")) {
    const w = Math.max(240, Math.floor(host.clientWidth)), what = host.dataset.ctpPlot;
    const funded = d.buy.picks.filter((p) => p.funded);
    const draw = {
      buyodds: () => ctpOddsSvg(d.buy.picks, (p) => p.gain, (p) => p.expected, w, "ctp-buyodds"),
      sellodds: () => ctpOddsSvg(d.sell.filter((p) => p.way === "house" && p.vendor !== null), (p) => p.sells, (p) => p.gain, w, "ctp-sellodds"),
      buytree: () => (funded.length ? ctpTreeSvg(funded.map((p) => ({ v: p.cost, name: p.name || p.item, tone: p.expected > 0 ? "gain" : "loss" })), w, "ctp-buytree",
        [{ look: "tone-gain", name: ctpW("legend.gain") }, { look: "tone-loss", name: ctpW("legend.loss") }])
        : `<p class="muted">${esc(ctpW("buy.tree.none"))}</p>`),
      selltree: () => ctpTreeSvg(Object.entries(d.sell.reduce((by, p) => {
        for (const [who, n] of Object.entries(p.on || {})) by[who] = (by[who] || 0) + p.gold * n / Math.max(1, p.units);
        return by;
      }, {})).map(([name, v]) => ({ v, name })), w, "ctp-selltree", [{ look: "tone-flat", name: ctpW("legend.character") }]),
      curve: () => {
        const p = d.buy.picks.find((x) => x.item === ctp.picked) || d.buy.picks[0];
        const xs = p.curve.map((c) => c[0]), ys = p.curve.map((c) => c[1]);
        return ckPlotSvg({ id: "ctp-curve", width: w, high: CTP_PLOT, x: { from: 0, to: Math.max(...xs), ticks: ckAcross(0, Math.max(...xs), num, 6) },
          y: { ...ckAxis(Math.min(0, ...ys), Math.max(1, ...ys)), label: goldText },
          lines: [{ points: p.curve.map((c) => ({ x: c[0], v: c[1] })) }], cuts: [{ x: p.units, label: ctpW("curve.chosen"), title: ctpCount("curve.chosen.tip", p.units, { n: num(p.units) }) }],
          dots: p.curve.map((c) => ({ x: c[0], v: c[1], title: ctpCount("curve.dot", c[0], { n: num(c[0]), gold: moneyText(c[1]), cost: moneyText(c[2]) }) })),
          legend: [{ look: "line", name: ctpW("legend.curve") }, { look: "dot", name: ctpW("legend.step") }, { look: "cut", name: ctpW("legend.chosen") }] });
      },
    }[what];
    if (draw) setHtml(host, draw());
  }
}

function ctpClick(e) {
  const b = e.target.closest?.("button");
  if (!b) return false;
  if (b.dataset.ctpOpen || b.dataset.ctpClose) {
    ctp.drawer = !!b.dataset.ctpOpen && !ctp.drawer;
    renderCounting();
    return true;
  }
  if (b.dataset.ctpCopy) {
    ctpCopyLine(ctp.copyPart);
    return true;
  }
  if (!ctp.data) return false;
  if (b.dataset.ctpAdd) {
    const side = b.dataset.ctpAdd, list = side === "buy" ? ctp.data.buy.picks : ctp.data.sell, p = list[+b.dataset.ctpI];
    if (p) {
      const entry = ctpEntry(side, p, ctp.data), at = ctp.list.findIndex((x) => x.kind === entry.kind && x.item === entry.item);
      if (at >= 0) ctp.list.splice(at, 1);
      else {
        ctp.list.push(entry);
        ctp.picked = p.item;
      }
      ctp.copyPart = 0;
      ctpListKeep();
      renderCounting();
    }
    return true;
  }
  if (b.dataset.ctpDrop) {
    ctp.list.splice(+b.dataset.ctpDrop, 1);
    ctp.copyPart = 0;
    ctpListKeep();
    renderCounting();
    return true;
  }
  return false;
}

function ctpListKeyHtml() {
  return `<span class="cth-field cth-list">${esc(ctpW("list.title"))}<button type="button" class="key small" data-ctp-open="1" aria-pressed="${ctp.drawer}"
    title="${esc(ctpW("list.open.tip"))}">${esc(wordCount("page.counting.picks.list.count", ctp.list.length))}</button></span>`;
}
