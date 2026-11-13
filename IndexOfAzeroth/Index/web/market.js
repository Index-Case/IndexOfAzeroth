// The Index of Azeroth. Copyright 2026 Index Case <indexofazeroth@pm.me>. PolyForm Strict 1.0.0, see LICENSE.md.
"use strict";

const AH_LINES = ["A goblin auctioneer licks his pencil", "A gnome broker is reading the bids", "The auctioneer is counting coin",
  "A goblin is weighing the Linen Cloth", "A dwarf is haggling over the buyouts", "A goblin clerk is pricing every stack",
  "The auctioneer is checking his ledger", "A goblin reads the bids by candlelight", "A gnome is sorting the stacks by price",
  "A goblin is tallying what sold this week"];
const AH_TYPE_MS = 45;
const AH_HOLD_MS = 1100;
const AH_WAIT_MS = 80;
const MARKET_ICON = "inv_misc_coin_02";
const GLASS = "inv_professions_inscription_scribesmagnifyingglass_gold";
const SCAN_TODO = "auction:scan";
const MARKET_TICK_MS = 1000;

const market = {
  brief: null,
  seen: null,
  version: null,
  character: null,
  prices: {},
  asked: new Set(),
  looked: new Set(),
  iconsIn: new Set(),
  tick: 0,
  finder: { text: "", full: false, ask: 0, busy: false, failed: false, found: [], more: false, wait: 0,
            hunt: { line: -1, last: -1, shown: 0, held: false, timer: 0, lines: AH_LINES } },
  view: "search",
  up: { ask: 0, busy: false, failed: false, known: true, slots: [], rows: [], open: new Set() },
};
const UP_LINES = Object.values(wordsOf("page.items.up.wait"));
const UP_ICON = "inv_chest_cloth_17";
const marketNow = () => Date.now() / 1000;


function loadMarket() {
  const asked = getJson("/api/auction/status", { key: "auction-status", share: true });
  return asked ? asked.then(takeStatus, () => null) : null;
}
function takeStatus(st) {
  const was = market.brief;
  market.brief = st;
  if (was?.house !== st.house || was?.version !== st.version) {
    market.prices = {};
    market.asked.clear();
  }
  briefChanged(was);
  return st;
}
function takeSnapshot(snap) {
  const brief = snap.auction ? JSON.stringify(snap.auction) : null;
  const v = snap.versions?.auction ?? null, who = snap.character ?? null;
  if (brief !== market.seen || v !== market.version || who !== market.character) {
    Object.assign(market, { seen: brief, version: v, character: who });
    loadMarket();
  }
}
function briefChanged(was) {
  if (scanWhy(was) && !scanWhy(market.brief) && market.brief?.lastScanComplete) {
    showToast("The auction house scan is complete, so the Scan the auction house to-do is ticked off");
  }
  emit("auction", market.brief, was);
  if (!$("market-menu")?.hidden) paintScan();
}

const houseName = (key) => (key ? key.split("|").filter(Boolean).join(", ") : "");

function scanWhy(b) {
  if (!b || b.running) return "";
  if (b.lastScanComplete === false) return "the last scan was incomplete";
  if (!b.lastScan) return "your auction house has no scan yet";
  return b.stale ? "the last scan is over a day old" : "";
}

function scanTodo() {
  const why = scanWhy(market.brief);
  const b = market.brief;
  return ["Auction house", why ? [{ id: `${SCAN_TODO}:${b.lastScanId ?? "none"}`, text: "Scan the auction house",
    detail: `${why}. Open the auction house in game and press Scan on the tab named The Index of Azeroth`, once: true }] : []];
}

function ahNotice(b = market.brief) {
  if (!b) return "";
  if (b.lastScanComplete === false) return "Last scan incomplete";
  if (!b.lastScan) return "No scan yet";
  return b.stale ? "Last scan over a day old" : "";
}


function scanHtml(b = market.brief, t = marketNow()) {
  if (!b) return html`<div class="market-scan muted">The page is asking the Index about your auction house</div>`;
  const where = houseName(b.house);
  const lines = [];
  if (b.running) {
    lines.push(html`<span class="market-live">Scanning now${b.total ? `: ${num(b.read || 0)} of ${num(b.total)} read` : ""}</span>`);
  } else if (!b.lastScan) {
    lines.push(html`<span>Your auction house has not been scanned yet. Open the auction house in game and press Scan on the tab named The Index of Azeroth</span>`);
  } else {
    lines.push(html`<span>Scanned ${ago(b.lastScan, t)}</span>`);
  }
  if (!b.running && b.lastScanComplete === false) {
    lines.push(html`<span class="market-warn">Last scan incomplete<small>${b.lastComplete ? `the last complete scan was ${ago(b.lastComplete, t)}`
      : "there is no complete scan yet"}</small></span>`);
  }
  if (!b.running && b.lastScan && b.stale) lines.push(html`<span class="market-warn">The last scan is over a day old, so scan the auction house again</span>`);
  lines.push(nextHtml(b, t));
  return html`<div class="market-scan"><img src="/icon/${MARKET_ICON}.jpg" alt=""><div><b>${where || "Your auction house"}</b>${lines}</div></div>`;
}
function nextHtml(b, t) {
  if (b.noAnswer) return html`<span class="market-warn">The auction house didn't answer the last scan, though 15 minutes had passed</span>`;
  const left = (b.nextScanAt || 0) - t;
  return left > 0 ? html`<span class="market-next">Next scan allowed in <b>${hms(left)}</b></span>` : "";
}
function paintScan() {
  const box = $("market-scan");
  if (box) setHtml(box, scanHtml());
}
function tickScan() {
  clearInterval(market.tick);
  market.tick = setInterval(() => {
    const open = !$("market-menu").hidden, left = (market.brief?.nextScanAt || 0) - marketNow();
    paintScan();
    if (!open || left <= 0) clearInterval(market.tick);
  }, MARKET_TICK_MS);
}


function wantPrice(id, done) {
  if (id in market.prices || market.asked.has(id) || !market.brief?.lastScan) return market.prices[id];
  const asked = getJson(`/api/auction/prices?ids=${id}`, { key: `auction-price:${id}`, quiet: true });
  if (!asked) return undefined;
  market.asked.add(id);
  asked.then((j) => {
    market.asked.delete(id);
    if (j.house !== market.brief?.house) return;
    const p = j.items?.[id];
    market.prices[id] = p && (p.listed || p.sales) ? p : null;
    done?.();
  }, () => market.asked.delete(id));
  return undefined;
}

const inCoins = (n) => raw(money(n));
function ahLineHtml(id, t = marketNow()) {
  const p = market.prices[id], b = market.brief;
  if (!b?.lastScan || p === undefined) return "";
  const note = ahNotice(b);
  const tail = note ? html`<small class="tip-ah-note">${note}</small>` : "";
  if (!p?.value) {
    const bid = p?.listed?.lowestBid;
    return html`<div class="tip-ah"><span>Auction house</span> ${bid ? html`bid only, from ${inCoins(bid)}` : html`<span class="muted">none listed</span>`}${tail}</div>`;
  }
  const from = p.from === "sales" ? "what sold lately" : `listed${p.scanned ? ` ${ago(p.scanned, t)}` : ""}`;
  return html`<div class="tip-ah"><span>Auction house</span> ${inCoins(p.value)} each <small>${from}</small>${tail}</div>`;
}

function ahBlockHtml(id, t = marketNow()) {
  const p = market.prices[id], b = market.brief;
  if (!b?.lastScan || p === undefined) return "";
  const note = ahNotice(b);
  const head = html`<div class="tip-ah-head">Auction house<small>${houseName(b.house)}${note ? html`, <span class="tip-ah-note">${note}</span>` : ""}</small></div>`;
  const l = p?.listed;
  if (!l && !p?.sales) return html`<div class="tip-ah-block">${head}<div class="muted">Nobody has listed or sold this item since the scans began</div></div>`;
  const parts = [];
  if (l?.top) {
    const all = [...new Set([...l.top, ...l.bottom])].sort((x, y) => y - x);
    const low = all.slice(-Math.min(3, all.length)), high = all.slice(0, all.length - low.length);
    const row = (v, i, list) => {
      const label = list === high && i === 0 ? "Highest price" : list === low && i === list.length - 1 ? "Lowest price" : "";
      return html`<div class="ah-price">${label ? html`<span>${label}</span>` : ""}${inCoins(v)}</div>`;
    };
    parts.push(html`<div class="ah-count">${num(l.quantity)} listed in ${num(l.auctions)} auction${l.auctions === 1 ? "" : "s"}${p.scanned ? `, ${ago(p.scanned, t)}` : ""}</div>`);
    if (high.length) parts.push(html`<div class="ah-high">${high.map(row)}</div><div class="ah-fade"></div>`);
    parts.push(html`<div class="ah-avg"><span>Average price</span>${inCoins(l.average)}</div>`, html`<div class="ah-low">${low.map(row)}</div>`);
  } else if (l) {
    parts.push(html`<div class="ah-count">${num(l.auctions)} auction${l.auctions === 1 ? "" : "s"} for bids only${l.lowestBid ? html`, from ${inCoins(l.lowestBid)}` : ""}</div>`);
  } else {
    parts.push(html`<div class="ah-count muted">None listed now</div>`);
  }
  parts.push(soldHtml(p.sales, t));
  return html`<div class="tip-ah-block">${head}${parts}</div>`;
}
function soldHtml(s, t) {
  if (!s) return html`<div class="ah-sold muted">No sales seen yet</div>`;
  const recent = s.recentSold ? html`${num(s.recentSold)} sold in the last 14 days, mostly at ${inCoins(s.recentMedian)}` : html`None sold lately`;
  const newest = (s.newest || []).slice(0, 3).map((n) => html`<div class="ah-sale">${inCoins(n.unit)}${n.count > 1 ? ` x${n.count}` : ""}<small>${ago(n.at, t)}</small></div>`);
  return html`<div class="ah-sold"><div>${recent}</div>${newest}</div>`;
}

function ahTipHtml(id, full, again) {
  wantPrice(id, again);
  return String(full ? ahBlockHtml(id) : ahLineHtml(id));
}


const marketFinderHtml = () => html`<div class="npc-find"><div class="npc-box"><form class="npc-form" id="market-form">${raw(searchBox("market-find",
  "Find an item by name", market.finder.text))}</form><button type="button" class="key small up-key" id="market-up" title="${word("page.items.up.hover")}"
  style="--icon:url(/icon/${UP_ICON}.jpg)">${word("page.items.up.key")}</button></div><div class="npc-hunt" aria-live="polite"><img
  class="npc-glass" id="market-glass" src="/icon/${GLASS}.jpg" alt="" title="This is the full search. It also finds names that are a letter or two off" hidden><span
  class="npc-line" id="market-line"></span></div></div>`;

function marketHuntText() {
  const f = market.finder, h = f.hunt;
  if (h.line >= 0) return h.lines[h.line].slice(0, h.shown);
  if (market.view === "upgrades") return market.up.failed ? word("page.items.up.failed") : "";
  if (!f.text.trim() || f.busy) return "";
  if (f.failed) return "The ledger is shut. The search didn't go through";
  const n = f.found.length, further = f.more ? ". Press Enter to search further" : "";
  return n ? `${num(n)} found${further}` : `No item goes by that name${further}`;
}
function marketPaintHunt() {
  const line = $("market-line");
  line.textContent = marketHuntText();
  line.classList.toggle("typing", market.finder.hunt.line >= 0);
  $("market-glass").hidden = market.view !== "search" || !market.finder.full || !market.finder.text.trim();
}
const marketNextLine = (not, n = AH_LINES.length) => { const k = Math.floor(Math.random() * (n - 1)); return k >= not && not >= 0 ? k + 1 : k; };
const marketHuntBusy = () => (market.view === "upgrades" ? market.up.busy : market.finder.busy);
function marketHuntStart(lines = AH_LINES) {
  const h = market.finder.hunt;
  if (h.line >= 0 && h.lines === lines) return;
  if (h.lines !== lines) Object.assign(h, { lines, last: -1 });
  clearTimeout(h.timer);
  h.line = h.last = marketNextLine(h.last, lines.length);
  h.shown = 0;
  h.held = false;
  h.timer = setTimeout(marketHuntTick, AH_TYPE_MS);
}
function marketHuntStop() {
  clearTimeout(market.finder.hunt.timer);
  market.finder.hunt.line = -1;
}
function marketHuntTick() {
  const h = market.finder.hunt;
  if (h.shown < h.lines[h.line].length) {
    h.shown++;
    h.timer = setTimeout(marketHuntTick, AH_TYPE_MS);
  } else if (!h.held) {
    h.held = true;
    h.timer = setTimeout(marketHuntTick, AH_HOLD_MS);
  } else if (marketHuntBusy()) {
    h.line = h.last = marketNextLine(h.line, h.lines.length);
    h.shown = 0;
    h.held = false;
    h.timer = setTimeout(marketHuntTick, AH_TYPE_MS);
  } else {
    h.line = -1;
  }
  marketPaintHunt();
}

function marketTyped(text) {
  const f = market.finder;
  f.text = text;
  showSearch();
  clearTimeout(f.wait);
  f.full = false;
  if (!text.trim()) {
    f.ask++;
    Object.assign(f, { busy: false, failed: false, found: [], more: false });
    marketHuntStop();
  } else {
    f.busy = true;
    marketHuntStart();
    f.wait = setTimeout(() => askMarket(false), AH_WAIT_MS);
  }
  renderMarketFound();
  marketPaintHunt();
}
function marketEntered() {
  clearTimeout(market.finder.wait);
  if (market.finder.text.trim()) askMarket(true);
}
function askMarket(full) {
  const f = market.finder, mine = ++f.ask;
  Object.assign(f, { full, busy: true, failed: false });
  marketHuntStart();
  marketPaintHunt();
  const q = new URLSearchParams({ q: f.text.trim() });
  if (full) q.set("full", "1");
  return getJson(`/api/market/search?${q}`, { key: null }).then((j) => {
    if (mine !== f.ask) return;
    Object.assign(f, { busy: false, found: j.items, more: j.more });
    renderMarketFound();
    marketPaintHunt();
  }, (e) => {
    if (mine !== f.ask) return;
    Object.assign(f, { busy: false, failed: true });
    marketPaintHunt();
    askFailed("No search", e);
  });
}

function findLine(e) {
  const a = e.ah;
  if (!a) return market.brief?.lastScan ? "none in the auction house" : "";
  const listed = a.auctions ? `${num(a.quantity)} listed` : "none listed now";
  return a.sold ? `${listed}, ${num(a.sold)} sold` : listed;
}
function findRow(e, i, line = findLine(e)) {
  const src = e.iconStored ? `${e.icon}.jpg` : market.iconsIn.has(e.item) ? `${e.icon}.jpg?in=1` : "inv_misc_questionmark.jpg";
  const price = e.ah?.value ? html`${inCoins(e.ah.value)}<small>${e.ah.from === "sales" ? "sold lately" : "listed"}</small>` : "";
  return html`<div class="market-row" data-find="${i}"><span class="market-item" data-tip="${e.item}" data-tip-ah="full"><img class="market-ic q${e.q}"
    src="/icon/${src}" alt=""><span class="market-name q${e.q}">${e.name}<small>${line}</small></span><span class="market-price">${price}</span></span><span
    class="market-keys">${ITEM_KEYS.map((k) => itemKeyHtml(e, i, k))}</span></div>`;
}


const UP_TAG = { clear: "up", weak: "gold", debatable: "debatable" };
function upTime(w) {
  if (w.abroad) return word("page.items.up.time.far");
  return w.away == null ? "" : wordCount("page.items.up.time", Math.max(1, Math.round(w.away)));
}
const UP_WAYS = {
  quest: (w) => (w.before ? wordCount("page.items.up.way.chain", w.before, { quest: w.quest }) : word("page.items.up.way.quest", { quest: w.quest })),
  vendor: (w) => word("page.items.up.way.vendor", { vendor: w.vendor }),
  auction: () => word("page.items.up.way.auction"),
  drop: (w) => word("page.items.up.way.drop", { mob: w.mob, kills: num(w.kills) }),
  once: (w) => wordCount("page.items.up.way.once", w.respawn, { mob: w.mob, kills: num(w.kills) }),
  craft: (w) => {
    const what = { what: w.skill ? `${w.profession} ${w.skill}` : w.profession };
    return w.takeUp ? word("page.items.up.way.craft.new", what) : word("page.items.up.way.craft", what);
  },
  gather: (w) => word("page.items.up.way.gather", { node: w.node }),
};
const upWhere = (w) => (w.zone ? word("page.items.up.where", { zone: w.zone }) : "");
const upWay = (w) => [UP_WAYS[w.kind](w), upWhere(w), upTime(w)].filter(Boolean).join(", ");
function upLine(e) {
  const from = e.from ? html`<span class="up-from">${word("page.items.up.from", { level: e.from })}</span>` : "";
  return html`<span class="j-tag ${UP_TAG[e.kind] || "gold"}">${e.tag}</span> ${upWay(e.way)}${from}`;
}
const upSlotName = (slot) => (GEAR_SLOTS.find(([s]) => s === slot) || [slot, ""])[1];
function upgradesHtml() {
  const u = market.up;
  const head = html`<div class="up-head"><button type="button" class="qz-back" id="market-up-back">${word("page.items.up.back")}</button><b>${word("page.items.up.key")}</b>${raw(helpButton("upgrades"))}</div>`;
  if (u.busy || u.failed) return head;
  if (!u.known) return html`${head}<div class="up-empty">${word("page.items.up.unknown")}</div>`;
  if (!u.slots.length) return html`${head}<div class="up-empty">${word("page.items.up.empty")}<small>${word("page.items.up.empty.quip")}</small></div>`;
  return html`${head}${u.slots.map((s) => {
    const open = u.open.has(s.slot), more = s.items.length > 1;
    const rows = (open ? s.items : s.items.slice(0, 1)).map((e) => findRow(e, u.rows.indexOf(e), upLine(e)));
    const name = html`<span>${upSlotName(s.slot)}</span><small>${num(s.items.length)}</small>`;
    const head = more ? html`<button type="button" class="up-slot-head fold-plus" data-up-slot="${s.slot}" aria-expanded="${String(open)}">${name}</button>`
      : html`<div class="up-slot-head">${name}</div>`;
    return html`<div class="up-slot${open ? " open" : ""}">${head}${rows}</div>`;
  })}`;
}
function askUpgrades() {
  const u = market.up, mine = ++u.ask;
  market.view = "upgrades";
  Object.assign(u, { busy: true, failed: false });
  marketHuntStart(UP_LINES);
  renderMarketFound();
  marketPaintHunt();
  const asked = getJson("/api/nextupgrades", { key: null });
  if (!asked) {
    u.busy = false;
    return null;
  }
  return asked.then((j) => {
    if (mine !== u.ask) return;
    Object.assign(u, { busy: false, known: j.known !== false, slots: j.slots || [], open: new Set() });
    u.rows = u.slots.flatMap((s) => s.items);
    renderMarketFound();
    marketPaintHunt();
  }, (e) => {
    if (mine !== u.ask) return;
    Object.assign(u, { busy: false, failed: true });
    renderMarketFound();
    marketPaintHunt();
    askFailed("No upgrades", e);
  });
}
function showSearch() {
  if (market.view === "search") return;
  market.view = "search";
  Object.assign(market.up, { busy: false });
  market.up.ask++;
  if (market.finder.hunt.lines === UP_LINES) marketHuntStop();
  renderMarketFound();
  marketPaintHunt();
}
const shownFinds = () => (market.view === "upgrades" ? market.up.rows : market.finder.found);
function marketClicked(e) {
  if (itemKeyClicked(e)) return true;
  const b = e.target.closest?.("#market-up, #market-up-back, button[data-up-slot]");
  if (!b) return false;
  if (b.id === "market-up") askUpgrades();
  else if (b.id === "market-up-back") showSearch();
  else {
    const slot = +b.dataset.upSlot, open = market.up.open;
    if (open.has(slot)) open.delete(slot); else open.add(slot);
    renderMarketFound();
  }
  return true;
}


const KEYS_OFF = "hide";
const ITEM_KEYS = [{ key: "grind", does: farmForIt }, { key: "quest", does: questForIt }, { key: "craft", does: craftIt }, { key: "buy", does: buyItem }];
const keyHas = (spec, keys) => keys?.[spec.key] || (spec.key === "buy" ? keys?.auction : null);
function keyKind(spec, keys) {
  if (spec.key === "grind" && keys?.grind === "gather") return "gather";
  return spec.key === "buy" && !keys?.buy && keys?.auction ? "auction" : spec.key;
}
const KEY_WORDS = {
  grind: { label: () => word("page.items.key.grind"), hover: (f) => word("page.items.grind", f), none: (f) => word("page.items.grind.none", f),
           pick: (f) => word("page.craft.pick.grind", f) },
  gather: { label: () => word("page.items.key.gather"), hover: (f) => word("page.items.gather", f), none: (f) => word("page.items.grind.none", f),
            pick: (f) => word("page.craft.pick.gather", f) },
  quest: { label: () => word("page.items.key.quest"), hover: (f) => word("page.items.quest", f), none: (f) => word("page.items.quest.none", f),
           pick: (f) => word("page.craft.pick.quest", f) },
  craft: { label: () => word("page.items.key.craft"), hover: (f) => word("page.items.craft", f), none: (f) => word("page.items.craft.none", f),
           pick: (f) => word("page.craft.pick.craft", f) },
  buy: { label: () => word("page.items.key.buy"), hover: (f) => word("page.items.buy", f), none: (f) => word("page.items.buy.none", f),
         pick: (f) => word("page.craft.pick.buy", f) },
  auction: { label: () => word("page.items.key.buy"), hover: (f) => word("page.items.buy.auction", f), none: (f) => word("page.items.buy.none", f),
             pick: (f) => word("page.craft.pick.auction", f) },
};
const OFF_KEYS = { hide: () => "", grey: (says, fill) => html`<button type="button" class="mob-go" disabled title="${says.none(fill)}">${says.label()}</button>` };
function itemKeyHtml(e, i, spec, how = {}) {
  const have = keyHas(spec, e.keys), says = KEY_WORDS[keyKind(spec, e.keys)];
  const fill = { name: e.name, quest: e.keys?.quest, vendor: e.keys?.buy, auctioneer: e.keys?.auction };
  const pressed = how.on === spec.key ? ' aria-pressed="true"' : "";
  const key = have ? html`<button type="button" class="mob-go" data-item-key="${i}:${spec.key}"${raw(pressed)} title="${says[how.hover || "hover"](fill)}">${says.label()}</button>`
    : OFF_KEYS[KEYS_OFF](says, fill);
  return html`<span class="mk-${spec.key}">${key}</span>`;
}
function itemKeyClicked(e) {
  const b = e.target.closest?.("button[data-item-key]");
  if (!b || b.disabled) return false;
  const [i, key] = b.dataset.itemKey.split(":");
  const find = shownFinds()[+i], spec = ITEM_KEYS.find((k) => k.key === key);
  if (find && spec?.does) spec.does(find);
  return true;
}
function farmForIt(find) {
  if (!app.state) return null;
  market.toggle(false);
  const item = { id: find.item, name: find.name };
  if (find.keys.grind === "grind") return searchCamp(false, [], false, null, item);
  const s = app.state, n = app.status?.nums || {}, me = playerWorld(true);
  const q = new URLSearchParams({ item: item.id, level: s.level || 1, faction: app.status?.strs?.faction || "",
                                  mining: n.miningSkill || 0, herbalism: n.herbalismSkill || 0 });
  if (me) { q.set("i", me.inst); q.set("n", me.n); q.set("w", me.w); }
  return getJson(`/api/gatherspot?${q}`, { key: null })?.then((spot) => {
    if (!spot?.names?.length) return showToast(`The Index found no place where you can gather ${item.name}`);
    if (app.tracks.loop) stopTrack("loop", true);
    searchGather(spot.kind, spot.names, [spot.map]);
  }, (e) => askFailed("No gathering loop", e));
}
function questForIt(find) {
  market.toggle(false);
  startEpic({ key: `item:${find.item}`, name: find.name });
}
function startCraftEpic(item, name) {
  const label = word("page.craft.label", { item: name });
  const mine = craftEpicOf(item);
  if (mine) return startEpic({ key: mine, name, label });
  const way = (w) => ({ label: LEVEL_WAYS[w].label(), tip: LEVEL_WAYS[w].tip(), on: () => startEpic({ key: `craft:${item}:${w}`, name, label }) });
  const [cheap, ...rest] = Object.keys(LEVEL_WAYS).map(way);
  return ask({ title: word("page.craft.way.title", { item: name }), text: word("page.craft.way.ask", { item: name }),
               yes: cheap.label, yesTip: cheap.tip, onYes: cheap.on, also: rest, no: word("page.craft.way.no") });
}
function craftEpicOf(item) {
  const its = (key) => key === `craft:${item}` || (key || "").startsWith(`craft:${item}:`);
  const kept = app.plan && its(app.plan.key) && planIsMine(app.plan) ? app.plan.key : null;
  return [app.tracks.epic?.key, kept, ...myProfs().map((p) => p.key)].find(its) || null;
}
function craftIt(find) {
  market.toggle(false);
  startCraftEpic(find.item, find.name);
}
function buyItem(find) {
  market.toggle(false);
  if (find.keys.buy) guideNearest({ cats: ["vendor"], more: { goods: find.item }, what: find.keys.buy });
  else guideNearest({ cats: ["auction"], what: find.keys.auction });
}
function renderMarketFound() {
  const up = market.view === "upgrades";
  setHtml($("market-found"), up ? upgradesHtml() : html`${market.finder.found.map((e, i) => findRow(e, i))}`);
  shownFinds().filter((e) => !e.iconStored).forEach((e) => lookUp(e.item));
}

function lookUp(id) {
  if (market.looked.has(id)) return null;
  const asked = getJson(`/api/market/item/${id}`, { key: `market-item:${id}`, quiet: true });
  if (!asked) return null;
  market.looked.add(id);
  return asked.then((j) => {
    if (j.tooltip === "stored") tipAgain(id);
    if (j.icon) {
      market.iconsIn.add(id);
      renderMarketFound();
    }
  }, () => market.looked.delete(id));
}


function openMarket() {
  const list = $("market-list");
  if (!list.firstChild) list.innerHTML = String(html`<div id="market-scan"></div>${marketFinderHtml()}<div class="mob-scroll"><div id="market-found"></div></div>`);
  paintScan();
  renderMarketFound();
  marketPaintHunt();
  tickScan();
  loadMarket();
  setTimeout(() => $("market-find")?.focus(), 0);
}
function startMarket() {
  const menu = $("market-menu");
  market.toggle = dropdown($("btn-market"), menu, "k", openMarket, { el: $("market-bar"), title: word("page.items.title"), help: "market" });
  menu.addEventListener("input", (e) => { if (e.target.id === "market-find") marketTyped(e.target.value); });
  menu.addEventListener("click", marketClicked);
  menu.addEventListener("submit", (e) => {
    if (e.target.id !== "market-form") return;
    e.preventDefault();
    marketEntered();
  });
  menu.addEventListener("mouseover", (e) => {
    const item = e.target.closest?.(".market-item");
    if (item) lookUp(+item.dataset.tip);
  });
  on("snapshot", takeSnapshot);
  on("todoLists", scanTodo);
  loadMarket();
}

if (typeof module === "object") {
  module.exports = { AH_LINES, AH_TYPE_MS, AH_HOLD_MS, AH_WAIT_MS, MARKET_ICON, SCAN_TODO, MARKET_TICK_MS, market, loadMarket, takeStatus,
                     takeSnapshot, briefChanged, houseName, scanWhy, scanTodo, ahNotice, scanHtml, nextHtml, paintScan, tickScan,
                     wantPrice, ahLineHtml, ahBlockHtml, soldHtml, ahTipHtml, marketFinderHtml, marketHuntText, marketPaintHunt, marketNextLine, marketHuntStart,
                     marketHuntStop, marketHuntTick, marketTyped, marketEntered, askMarket, findLine, findRow, KEYS_OFF, ITEM_KEYS, keyKind, KEY_WORDS, OFF_KEYS,
                     itemKeyHtml, itemKeyClicked, farmForIt, questForIt, startCraftEpic, craftIt, buyItem, renderMarketFound, lookUp, openMarket, startMarket,
                     UP_LINES, UP_ICON, UP_TAG, UP_WAYS, upTime, upWay, upLine, upSlotName, upgradesHtml, askUpgrades, showSearch,
                     shownFinds, marketClicked, keyHas, marketHuntBusy };
}
