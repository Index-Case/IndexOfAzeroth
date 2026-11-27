// The Index of Azeroth. Copyright 2026 Index Case <indexofazeroth@pm.me>. PolyForm Strict 1.0.0, see LICENSE.md.
"use strict";

const CPX_W = wordsOf("page.counting.picture");
const cpxW = (key, fill) => fillWords(CPX_W[key], fill) ?? "";
const CPX_HIGH = 392;
const CPX_GROW = 2, CPX_LEAST = 720;
const CPX_PAD = 12;
const CPX_ICON = 30;
const CPX_SMALL = 24;
const CPX_CELL = [42, 50];
const CPX_SHELF_ROWS = 3;
const CPX_ASIDE = [4, 2];
const CPX_HEAP = 7;
const CPX_TRIP = { lift: 240, hold: 200, drop: 320 };
const CPX_GAP = [90, 260];
const CPX_SPREAD = 1500;
const CPX_KEEP = { good: 6, bad: 4, aside: 2, house: 6, vendor: 4, none: 2 };
const CPX_ACT_GAP = [110, 260];
const CPX_ACT_SPREAD = 2200;
const CPX_SLIDE = 240;
const CPX_COINS = 200;
const CPX_SETTLE = 900;
const CPX_ROW = 30;
const CPX_HEAD = 22;
const CPX_ARC = 22;
const CPX_ROWS_IN = 300;
const CPX_HOLD = 600;

const cpxGap = (n, spread, gap) => Math.min(gap[1], Math.max(gap[0], spread / Math.max(1, n)));
const cpxEase = (f) => (f < 0.5 ? 4 * f * f * f : 1 - Math.pow(-2 * f + 2, 3) / 2);
const cpxKind = (e) => (e.e === "sell" ? e.way || "none" : e.e);
const cpxPiles = () => Object.fromEntries(["good", "bad", "aside", "house", "vendor", "none"].map((k) => [k, { slots: [], next: 0 }]));

function cpxNew(side, w, items = {}, still = false, high = CPX_HIGH) {
  const k = Math.max(1, Math.min(CPX_GROW, high / CPX_HIGH, w / CPX_LEAST));
  w /= k;
  return {
    side, w, h: CPX_HIGH, k, lay: cpxLayout(side, w), items, still, next: [], got: { good: 0, bad: 0, aside: 0, house: 0, vendor: 0, none: 0 },
    started: false, done: false,
    waiting: [], acts: [], nextAt: 0, actAt: 0, phase: "weigh",
    counts: { left: 0, weigh: 0, good: 0, bad: 0, aside: 0, held: 0, house: 0, vendor: 0, none: 0, weighed: 0, of: 0 }, way: {},
    gold: {}, actors: new Map(), shelves: cpxPiles(), list: [], rest: [], spent: 0, spend: 0, rows: null, settledAt: 0,
    timers: [],
  };
}

function cpxLayout(side, w) {
  const p = CPX_PAD, top = 44, foot = 236;
  const lay = { listed: { x: p + 56, y: top + 46 }, scales: { x: p + 186, y: top + 46 }, foot };
  lay.aside = { x: p + 186 - ((CPX_ASIDE[0] - 1) * 30) / 2, y: top + 128, cols: CPX_ASIDE[0], rows: CPX_ASIDE[1], cell: 30 };
  const from = p + 290, half = (w - p - from - 24) / 2;
  const cols = Math.max(2, Math.floor(half / CPX_CELL[0]));
  const shelf = (x) => ({ x: x + CPX_CELL[0] / 2, y: top + CPX_ICON / 2 + 2, cols, rows: CPX_SHELF_ROWS, cell: CPX_CELL[0], down: CPX_CELL[1], w: half });
  lay[side === "sell" ? "house" : "good"] = shelf(from);
  lay[side === "sell" ? "vendor" : "bad"] = shelf(from + half + 24);
  lay.none = lay.aside;
  lay.bar = { x: p, y: foot + 24, w: w - 2 * p };
  lay.list = { x: p + CPX_CELL[0] / 2 - 4, y: foot + 66 };
  lay.labels = {
    listed: { x: p, y: 8 }, scales: { x: p + 146, y: 8 }, aside: { x: p + 136, y: top + 96 },
    left: { x: from, y: 8 }, right: { x: from + half + 24, y: 8 }, budget: { x: p, y: foot }, rest: { x: p, y: foot + 100 },
  };
  return lay;
}

function cpxSlot(at, k) {
  if (k >= at.cols * at.rows) return null;
  return { x: at.x + (k % at.cols) * at.cell, y: at.y + Math.floor(k / at.cols) * (at.down || at.cell) };
}


function cpxFeed(pic, got, now) {
  Object.assign(pic.items, got.items);
  Object.assign(pic, { next: got.next || [], started: true, done: !!got.done });
  pic.counts.of = got.listed;
  if (got.held && !pic.heldOf) pic.counts.held = pic.heldOf = got.held;
  if (got.held && pic.side === "sell") pic.phase = pic.phase === "settled" ? "settled" : "held";
  for (const e of got.steps) {
    if (e.e === "good" || e.e === "bad" || e.e === "aside") {
      pic.got[e.e]++;
      if (e.e !== "aside") pic.gold[e.i] = e.gold;
      pic.waiting.push(e);
    } else if (e.e === "sell") {
      pic.gold[e.i] = e.gold;
      pic.way[e.i] = cpxKind(e);
      pic.got[pic.way[e.i]]++;
      if (pic.side === "sell") pic.waiting.push(e);
    } else if (e.e === "held") {
      if (pic.side === "sell") pic.phase = "held";
    } else if (e.e !== "list") pic.acts.push(e);
  }
  for (const k of Object.keys(pic.got)) {
    const held = k === "house" || k === "vendor" || k === "none";
    const unseen = (got.counts[held ? `sell.${k}` : k] || 0) - pic.got[k];
    if (unseen > 0) {
      pic.got[k] += unseen;
      pic.counts[k] += unseen;
      if (held) pic.counts.held -= unseen;
      else Object.assign(pic.counts, { weighed: pic.counts.weighed + unseen, left: pic.counts.left + unseen });
    }
  }
  if (!pic.nextAt) pic.nextAt = now;
}

function cpxOver(pic, now) {
  if (pic.phase === "settled") return pic.still || now >= cpxRowsFrom(pic) + CPX_ROWS_IN + CPX_HOLD;
  return pic.done && !pic.waiting.length && !pic.acts.length && !pic.timers.length;
}

function cpxStep(pic, now) {
  const due = pic.timers.filter((d) => d.at <= now);
  pic.timers = pic.timers.filter((d) => d.at > now);
  for (const d of due) d.run();
  cpxCatchUp(pic);
  if (pic.nextAt < now - CPX_GAP[1]) pic.nextAt = now;
  while (pic.waiting.length && now >= pic.nextAt) {
    cpxWeigh(pic, pic.waiting.shift(), pic.nextAt);
    pic.nextAt += pic.still ? 0 : cpxGap(pic.waiting.length + 1, CPX_SPREAD, CPX_GAP);
  }
  if (pic.waiting.length) return;
  if (pic.actAt < now - CPX_ACT_GAP[1]) pic.actAt = now;
  while (pic.acts.length && now >= pic.actAt) {
    const e = pic.acts.shift();
    const shown = pic.side === "sell" ? cpxSellAct(pic, e, pic.actAt) : cpxBuyAct(pic, e, pic.actAt);
    if (shown && !pic.still) pic.actAt += cpxGap(pic.acts.length + 1, CPX_ACT_SPREAD, CPX_ACT_GAP);
  }
}

function cpxCatchUp(pic) {
  const kept = {}, keep = new Set();
  for (const e of pic.waiting) {
    const kind = cpxKind(e);
    if (pic.side === "sell" && e.e !== "sell") continue;
    if ((kept[kind] || 0) < CPX_KEEP[kind]) {
      kept[kind] = (kept[kind] || 0) + 1;
      keep.add(e);
    }
  }
  pic.waiting = pic.waiting.filter((e) => {
    if (keep.has(e)) return true;
    cpxTaken(pic, e);
    if (e.e !== "sell") pic.counts.weighed++;
    pic.counts[cpxKind(e)]++;
    return false;
  });
}

function cpxTaken(pic, e) {
  if (e.e === "sell") pic.counts.held--;
  else pic.counts.left++;
}

function cpxHeap(pic) {
  if (pic.side === "sell" && pic.phase === "weigh") return [];
  const c = pic.counts, most = Math.min(CPX_HEAP, pic.side === "sell" ? c.held : c.of - c.left), out = [];
  const next = pic.side === "buy" && pic.phase !== "weigh" ? [] : pic.next;
  for (const k of [...pic.waiting.map((e) => e.i), ...next]) {
    if (out.length >= most) break;
    if (!out.includes(k) && !pic.actors.has(k)) out.push(k);
  }
  return out.reverse();
}


function cpxActor(pic, key, at, t, size = CPX_ICON) {
  let a = pic.actors.get(key);
  if (!a) {
    a = { key, from: { x: at.x, y: at.y, s: size }, legs: [], coins: null, fade: { o: 1, t, d: pic.still ? 0 : 120 } };
    pic.actors.set(key, a);
  }
  return a;
}

function cpxGo(pic, a, to, t, d, arc = 0) {
  a.legs.push({ to: { s: CPX_ICON, ...to }, t, d: pic.still ? 0 : d, arc });
  a.legs.sort((p, q) => p.t - q.t);
}

function cpxPos(from, leg, now) {
  const f = leg.d ? cpxEase(Math.max(0, Math.min(1, (now - leg.t) / leg.d))) : now >= leg.t ? 1 : 0;
  const lift = leg.arc * Math.sin(Math.PI * f);
  return { x: from.x + (leg.to.x - from.x) * f, y: from.y + (leg.to.y - from.y) * f - lift, s: from.s + (leg.to.s - from.s) * f };
}

function cpxAt(a, now) {
  while (a.legs.length > 1 && a.legs[1].t <= now) {
    a.from = cpxPos(a.from, a.legs[0], a.legs[1].t);
    a.legs.shift();
  }
  const leg = a.legs[0];
  return leg && leg.t <= now ? cpxPos(a.from, leg, now) : a.from;
}

function cpxCoins(a, gold, t, off = null) {
  a.coins = { gold, t, off };
}

function cpxLater(pic, at, run) {
  if (pic.still) run();
  else pic.timers.push({ at, run });
}

function cpxSink(pic, a, t) {
  a.fade = { o: 0, t, d: pic.still ? 0 : CPX_SLIDE };
  cpxLater(pic, t + CPX_SLIDE, () => { if (a.fade.o === 0) pic.actors.delete(a.key); });
}

function cpxWeigh(pic, e, t) {
  const lay = pic.lay;
  cpxTaken(pic, e);
  pic.counts.weigh++;
  const a = cpxActor(pic, e.i, lay.listed, t);
  const pile = cpxKind(e);
  let off = t;
  if (e.kept) {
    cpxCoins(a, e.gold, t);
  } else {
    const on = t + CPX_TRIP.lift;
    off = on + CPX_TRIP.hold;
    cpxGo(pic, a, { ...lay.scales, s: CPX_ICON + 8 }, t, CPX_TRIP.lift, CPX_ARC);
    if (e.gold != null) cpxCoins(a, e.gold, on);
  }
  cpxLater(pic, off + CPX_TRIP.drop, () => {
    pic.counts.weigh--;
    pic.counts.weighed += pic.side === "buy" ? 1 : 0;
    pic.counts[pile]++;
  });
  cpxShelve(pic, a, pile, off, CPX_TRIP.drop);
}

function cpxShelve(pic, a, pile, t, d) {
  const low = pile === "aside" || pile === "none";
  const shelf = pic.shelves[pile], at = pic.lay[pile], small = low ? CPX_SMALL : CPX_ICON;
  cpxUnshelve(pic, a.key);
  let k = shelf.slots.indexOf(null);
  if (k < 0) k = shelf.slots.length < at.cols * at.rows ? shelf.slots.length : shelf.next++ % shelf.slots.length;
  const was = pic.actors.get(shelf.slots[k]);
  if (was) cpxSink(pic, was, t + d - CPX_SLIDE / 2);
  shelf.slots[k] = a.key;
  cpxGo(pic, a, { ...cpxSlot(at, k), s: small }, t, d, low ? 6 : CPX_ARC);
}
function cpxUnshelve(pic, key) {
  for (const s of Object.values(pic.shelves)) {
    const k = s.slots.indexOf(key);
    if (k >= 0) s.slots[k] = null;
  }
}


function cpxListSlot(pic, n, rest = false) {
  const lay = pic.lay, many = pic.list.length + pic.rest.length;
  const cell = Math.min(CPX_CELL[0], (pic.w - 2 * CPX_PAD - 40) / Math.max(1, many + 1));
  return { x: lay.list.x + (n + (rest ? pic.list.length : 0)) * cell + (rest ? 30 : 0), y: lay.list.y, s: Math.min(CPX_ICON, cell - 6) };
}

function cpxFetch(pic, key, t) {
  if (pic.actors.has(key)) {
    cpxUnshelve(pic, key);
    return pic.actors.get(key);
  }
  const g = pic.gold[key], pile = pic.lay[pic.side === "sell" ? pic.way[key] || "house" : g > 0 ? "good" : "bad"];
  const a = cpxActor(pic, key, { x: pile.x + pile.w / 2 - pile.cell / 2, y: pile.y + pile.down * (pile.rows - 0.5) }, t);
  if (g !== undefined) cpxCoins(a, g, t);
  return a;
}

function cpxBuyAct(pic, e, t) {
  const d = CPX_TRIP.drop;
  if (e.e === "fill") {
    Object.assign(pic, { phase: "fill", spend: e.spend });
    return false;
  }
  if (pic.phase === "weigh" && (e.e === "fund" || e.e === "out" || e.e === "pick" || e.e === "drop")) pic.phase = "fill";
  if (e.e === "fund") {
    const a = cpxFetch(pic, e.i, t), fresh = !pic.list.includes(e.i);
    if (fresh) pic.list.push(e.i);
    pic.spent = e.spent;
    Object.assign(a, { units: e.units, cost: (a.cost || 0) + e.more, moved: t });
    cpxGo(pic, a, cpxListSlot(pic, pic.list.indexOf(e.i)), t, d, fresh ? CPX_ARC : 10);
    cpxRelist(pic, t);
    return true;
  }
  if ((e.e === "pick" || e.e === "out") && e.gold != null) pic.gold[e.i] = e.gold;
  if (e.e === "pick") {
    const a = pic.actors.get(e.i);
    if (a) cpxCoins(a, e.gold, t);
    return false;
  }
  if (e.e === "drop") {
    const a = pic.actors.get(e.i);
    pic.list = pic.list.filter((k) => k !== e.i);
    if (a) {
      pic.spent -= a.cost || 0;
      if (a.coins) a.coins.off = t;
      a.moved = t;
      cpxShelve(pic, a, "aside", t + CPX_COINS, d);
    }
    cpxRelist(pic, t);
    return true;
  }
  if (e.e === "out") {
    const a = cpxFetch(pic, e.i, t);
    pic.rest.push(e.i);
    Object.assign(a, { why: e.why, moved: t });
    cpxCoins(a, e.gold, Math.min(a.coins?.t ?? t, t), t + d);
    cpxGo(pic, a, cpxListSlot(pic, pic.rest.length - 1, true), t, d, CPX_ARC);
    cpxRelist(pic, t);
    return true;
  }
  if (e.e === "settle") {
    cpxSettle(pic, e, t);
    return true;
  }
  return false;
}

function cpxRelist(pic, t) {
  const slide = (k, n, rest) => {
    const a = pic.actors.get(k);
    if (a && a.moved !== t) cpxGo(pic, a, cpxListSlot(pic, n, rest), t, CPX_SLIDE);
  };
  pic.list.forEach((k, n) => slide(k, n, false));
  pic.rest.forEach((k, n) => slide(k, n, true));
}

function cpxSettle(pic, e, t) {
  Object.assign(pic, { phase: "settled", settledAt: t, shelves: cpxPiles() });
  pic.rows = [...e.order].sort((a, b) => (pic.gold[b] ?? 0) - (pic.gold[a] ?? 0))
    .map((key, n) => ({ key, n, funded: pic.side === "sell" || pic.list.includes(key) }));
  const kept = new Set(e.order);
  for (const a of pic.actors.values()) if (!kept.has(a.key)) cpxSink(pic, a, t);
  for (const r of pic.rows) {
    const a = cpxFetch(pic, r.key, t);
    if (cpxRowTop(r.n + 1) > pic.h) cpxSink(pic, a, t);
    else cpxGo(pic, a, { x: CPX_PAD + CPX_SMALL / 2 + 2, y: cpxRowTop(r.n) + CPX_ROW / 2, s: CPX_SMALL }, t + Math.min(r.n, 12) * 30, CPX_SETTLE);
  }
}
const cpxRowTop = (n) => CPX_PAD + CPX_HEAD + n * CPX_ROW;
const cpxRowsFrom = (pic) => pic.settledAt + 12 * 30 + CPX_SETTLE * 0.8;


function cpxSellAct(pic, e, t) {
  if (e.e !== "sold") return false;
  cpxSettle(pic, e, t);
  return true;
}


function cpxFrame(pic, host) {
  const L = pic.lay.labels, buy = pic.side === "buy";
  const label = (k, at, cls = "") => `<div class="cpx-label ${cls}" data-cpx="${k}" style="left:${at.x}px;top:${at.y}px"></div>`;
  host.style.height = `${Math.ceil(pic.h * pic.k)}px`;
  host.innerHTML = `<div class="cpx" style="width:${pic.w}px;height:${pic.h}px;transform:scale(${pic.k})">
    <div class="cpx-heap" style="left:${pic.lay.listed.x}px;top:${pic.lay.listed.y}px"></div>
    <div class="cpx-scales" style="left:${pic.lay.scales.x}px;top:${pic.lay.scales.y}px"></div>
    ${label("listed", L.listed)}${label("scales", L.scales)}${label(buy ? "aside" : "none", L.aside)}
    ${label("left", L.left, buy ? "cpx-gain" : "")}${label("right", L.right, buy ? "cpx-loss" : "")}
    ${label("budget", L.budget)}${buy ? `<div class="cpx-bar" style="left:${pic.lay.bar.x}px;top:${pic.lay.bar.y}px;width:${pic.lay.bar.w}px"><i></i></div>${label("rest", L.rest)}` : ""}
    <div class="cpx-rows"></div><div class="cpx-actors"></div></div>`;
  pic.host = host;
  pic.els = new Map();
}

function cpxText(pic, k, html) {
  const el = pic.host.querySelector(`[data-cpx="${k}"]`);
  if (el && el.dataset.was !== html) {
    el.dataset.was = html;
    el.innerHTML = html;
  }
}

function cpxMoney(copper) {
  const v = Math.abs(copper), sign = copper < 0 ? "&minus;" : copper > 0 ? "+" : "";
  if (v >= 10000) return `${sign}${ckGold(v, true)}`;
  return `${sign}${coinPicture(v >= 100 ? Math.round(v / 100) : Math.round(v), v >= 100 ? "s" : "c")}`;
}

const cpxIcon = (pic, key) => pic.items[key]?.icon || "inv_misc_questionmark";

function cpxDraw(pic, now) {
  cpxStep(pic, now);
  const c = pic.counts, n = (v) => (pic.started ? `<b>${esc(num(Math.max(0, v)))}</b>` : "");
  const settled = pic.phase === "settled";
  const piles = settled ? Math.max(0, 1 - (now - pic.settledAt) / 400) : 1;
  const frame = pic.host.querySelector(".cpx");
  frame.style.setProperty("--cpx-piles", piles.toFixed(2));
  if (pic.side === "buy") {
    cpxText(pic, "listed", `${esc(cpxW("listed"))} ${n(c.of - c.left)}`);
    cpxText(pic, "scales", esc(cpxW(pic.phase === "weigh" ? "weighing" : "weighed")));
    cpxText(pic, "aside", `${esc(cpxW("aside"))} ${n(c.aside)}`);
    cpxText(pic, "left", `${esc(cpxW("good"))} ${n(c.good)}`);
    cpxText(pic, "right", `${esc(cpxW("bad"))} ${n(c.bad)}`);
    cpxText(pic, "budget", !pic.started ? esc(cpxW("market.wait")) : pic.phase === "weigh" ? esc(cpxW("budget.wait"))
      : fillWords(esc(CPX_W.budget), { spent: ckGold(pic.spent), spend: ckGold(pic.spend) }));
    const rest = pic.host.querySelector('[data-cpx="rest"]');
    rest.style.left = `${cpxListSlot(pic, 0, true).x - 15}px`;
    cpxText(pic, "rest", pic.rest.length ? esc(cpxW("rest")) : "");
    frame.querySelector(".cpx-bar i").style.width = `${pic.spend ? Math.min(100, (100 * pic.spent) / pic.spend) : 0}%`;
  } else {
    const weigh = pic.phase === "weigh";
    cpxText(pic, "listed", `${esc(cpxW("held"))} ${weigh ? "" : n(c.held)}`);
    cpxText(pic, "scales", weigh ? "" : esc(cpxW(c.held > 0 || c.weigh ? "weighing" : "weighed")));
    cpxText(pic, "none", `${esc(cpxW("none"))} ${n(c.none)}`);
    cpxText(pic, "left", `${esc(cpxW("house"))} ${n(c.house)}`);
    cpxText(pic, "right", `${esc(cpxW("vendor"))} ${n(c.vendor)}`);
    cpxText(pic, "budget", !pic.started ? esc(cpxW("market.wait")) : weigh ? esc(cpxW("market", { n: num(c.weighed), of: num(c.of) })) : "");
  }
  cpxDrawHeap(pic);
  cpxDrawRows(pic, now);
  const layer = frame.querySelector(".cpx-actors"), seen = new Set();
  for (const a of pic.actors.values()) {
    const at = cpxAt(a, now), f = a.fade;
    const o = !f.d ? (now >= f.t ? f.o : 1 - f.o) : Math.max(0, Math.min(1, (now - f.t) / f.d)) * (f.o ? 1 : -1) + (f.o ? 0 : 1);
    let el = pic.els.get(a.key);
    if (!el) {
      el = document.createElement("div");
      el.className = "cpx-it";
      el.innerHTML = `<img src="/icon/${esc(cpxIcon(pic, a.key))}.jpg" alt="" data-tip="${esc(ckTipKey(a.key))}"><span class="cpx-coins"></span>`;
      layer.append(el);
      pic.els.set(a.key, el);
    }
    seen.add(a.key);
    const look = `translate(${(at.x - at.s / 2).toFixed(1)}px, ${(at.y - at.s / 2).toFixed(1)}px)|${at.s.toFixed(1)}px|${o.toFixed(2)}`;
    if (el.dataset.was !== look) {
      el.dataset.was = look;
      const [move, size, shown] = look.split("|");
      el.style.transform = move;
      el.style.width = el.style.height = size;
      el.style.opacity = shown;
      el.classList.toggle("rest", pic.rest.includes(a.key));
    }
    cpxDrawCoins(el.lastChild, a.coins, now, settled);
  }
  for (const [k, el] of pic.els) {
    if (!seen.has(k)) {
      el.remove();
      pic.els.delete(k);
    }
  }
}

function cpxDrawCoins(el, coins, now, settled) {
  if (!coins || now < coins.t || settled) {
    if (el.dataset.look !== "0") el.style.opacity = el.dataset.look = "0";
    return;
  }
  const html = cpxMoney(coins.gold);
  if (el.dataset.was !== html) {
    el.dataset.was = html;
    el.innerHTML = html;
    el.className = `cpx-coins${coins.gold > 0 ? " cpx-gain" : coins.gold < 0 ? " cpx-loss" : ""}`;
  }
  const on = Math.min(1, (now - coins.t) / CPX_COINS);
  const gone = coins.off === null || now < coins.off ? 0 : Math.min(1, (now - coins.off) / (CPX_COINS * 1.5));
  const look = `${(on * (1 - gone)).toFixed(2)}|translate(-50%, ${(16 * gone).toFixed(1)}px) scale(${(0.5 + 0.5 * on).toFixed(2)})`;
  if (el.dataset.look === look) return;
  el.dataset.look = look;
  [el.style.opacity, el.style.transform] = look.split("|");
}

function cpxDrawHeap(pic) {
  const heap = pic.host.querySelector(".cpx-heap");
  const next = cpxHeap(pic);
  const html = next.map((key, k) => `<img src="/icon/${esc(cpxIcon(pic, key))}.jpg" alt="" data-tip="${esc(ckTipKey(key))}" style="--k:${next.length - 1 - k}">`).join("");
  if (heap.dataset.was !== html) {
    heap.dataset.was = html;
    heap.innerHTML = html;
  }
}

function cpxDrawRows(pic, now) {
  const box = pic.host.querySelector(".cpx-rows"), sell = pic.side === "sell";
  if (!pic.rows) return;
  if (!box.childElementCount) {
    const fits = pic.rows.filter((r) => cpxRowTop(r.n + 1) <= pic.h);
    const heads = sell ? ["row.item", "row.way", "row.gold"] : ["row.item", "row.buy", "row.expected"];
    box.innerHTML = `<div class="cpx-row cpx-row-head" style="top:${CPX_PAD}px">${heads.map((k) => `<span>${esc(cpxW(k))}</span>`).join("")}</div>`
      + fits.map((r) => {
        const a = pic.actors.get(r.key), it = pic.items[r.key] || {};
        const gold = pic.gold[r.key] ?? 0;
        const middle = sell ? esc(cpxW(pic.way[r.key])) : r.funded && a?.units ? esc(num(a.units)) : "";
        return `<div class="cpx-row${r.funded ? "" : " rest"}" style="top:${cpxRowTop(r.n)}px">
          <span>${ckItemHtml({ key: r.key, name: it.n, q: it.q, icon: it.icon }, { icon: false })}${r.funded ? "" : ` <i>${esc(cpxW("row.out"))}</i>`}</span><span>${middle}</span>
          <span class="${gold > 0 ? "cpx-gain" : gold < 0 ? "cpx-loss" : ""}">${gold < 0 ? "&minus;" : gold > 0 ? "+" : ""}${ckGold(Math.abs(gold))}</span></div>`;
      }).join("");
  }
  const shown = pic.still ? 1 : Math.max(0, Math.min(1, (now - cpxRowsFrom(pic)) / CPX_ROWS_IN));
  box.style.opacity = shown === 1 ? "1" : shown.toFixed(2);
  box.classList.toggle("cpx-shown", shown === 1);
}
