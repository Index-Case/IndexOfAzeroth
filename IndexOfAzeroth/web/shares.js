// The Index of Azeroth. Copyright 2026 Index Case <indexofazeroth@pm.me>. PolyForm Strict 1.0.0, see LICENSE.md.
"use strict";

const SHARE_KEYS = ".guide-cmd, .guide-legs";
const SHARE_CARDS = {
  runbox: { rows: ":scope > :not(.run-head)", pins: ":scope > .run-head" },
  "track-epic": { rows: ":scope > .track-body > :not(.guide-head, .guide-name)", pins: ":scope > .track-body > :is(.guide-head, .guide-name)",
                  keys: SHARE_KEYS, usual: 3 },
  "track-loop": { rows: ":scope > .track-body > :not(.guide-head, .guide-name)", pins: ":scope > .track-body > :is(.guide-head, .guide-name)",
                  keys: SHARE_KEYS },
  "track-profs": { rows: ":scope > .track-body > .prof-row", pins: ":scope > .track-body > .guide-head" },
  guide: { rows: ":scope > .guide-body > :not(.guide-head, .guide-name)", pins: ":scope > .guide-body > :is(.guide-head, .guide-name)",
           keys: SHARE_KEYS },
  todo: { rows: ".todo-item", group: ".todo-list", pins: ":scope > .todo-head", usual: 2 },
};
const SHARE_EPS = 0.5;

function shareFill(room, wants) {
  const sum = (f) => wants.reduce((n, w) => n + f(w), 0);
  if (room <= sum((w) => w.min)) return wants.map((w) => w.min);
  if (room >= sum((w) => w.max)) return wants.map((w) => w.max);
  const at = (level) => sum((w) => Math.min(w.max, Math.max(w.min, level)));
  const bends = [...new Set(wants.flatMap((w) => [w.min, w.max]))].sort((a, b) => a - b);
  let low = bends[0];
  for (const b of bends) {
    if (at(b) >= room) break;
    low = b;
  }
  const rising = wants.filter((w) => w.min <= low && w.max > low).length;
  const level = low + (room - at(low)) / rising;
  return wants.map((w) => Math.min(w.max, Math.max(w.min, level)));
}

function sharePlan(room, cards) {
  const sum = (list) => list.reduce((x, y) => x + y, 0), fits = (wants) => sum(wants.map((w) => w.min)) <= room + SHARE_EPS;
  let wants = cards.map((c) => ({ min: c.keep, max: c.whole }));
  if (!fits(wants)) wants = cards.map((c) => (c.list ? { min: c.first, max: c.whole } : { min: c.keep, max: c.keep }));
  if (!fits(wants)) wants = cards.map((c) => (c.list ? { min: c.first, max: c.first } : { min: c.first, max: c.keep }));
  if (!fits(wants)) {
    const least = cards.map((c) => c.first), frees = (i) => least[i] - cards[i].bare;
    for (const lists of [false, true]) {
      for (let need = sum(least) - room; need > SHARE_EPS; need = sum(least) - room) {
        const can = cards.map((c, i) => i).filter((i) => !!cards[i].list === lists && frees(i) > SHARE_EPS);
        if (!can.length) break;
        const enough = can.filter((i) => frees(i) >= need - SHARE_EPS).sort((a, b) => frees(a) - frees(b));
        const i = enough[0] ?? can.sort((a, b) => frees(b) - frees(a))[0];
        least[i] = cards[i].bare;
      }
    }
    const lists = shareFill(room, cards.map((c, i) => ({ min: least[i], max: c.list ? c.first : least[i] })));
    wants = cards.map((c, i) => ({ min: lists[i], max: c.list ? lists[i] : c.keep }));
  }
  return shareFill(room, wants).map((share, i) => {
    const whole = cards[i].whole;
    return share >= whole - SHARE_EPS ? { cap: null, height: whole } : { cap: share, height: share };
  });
}

function measureCard(el, spec) {
  const rect = (x) => x.getBoundingClientRect();
  const rows = spec ? [...el.querySelectorAll(spec.rows)].filter((r) => rect(r).height > 0) : [];
  if (rows.length < 2) return null;
  const groups = rows.map((r) => (spec.group ? r.closest(spec.group) : null));
  const end = Math.max(...rows.map((r, i) => rect(groups[i] || r).bottom)), whole = rect(el).height;
  const last = (k) => rect(groups[k - 1] && groups[k - 1] !== groups[k] ? groups[k - 1] : rows[k - 1]).bottom;
  const upTo = (k) => (k < rows.length ? whole - (end - last(k)) : whole);
  const title = whole - (end - rect(groups[0] || rows[0]).top);
  const own = (k) => !k.closest(".fold-more");
  const keys = spec.keys ? rows.filter((r) => r.matches(spec.keys) || [...r.querySelectorAll(spec.keys)].some(own)) : [];
  const tall = (list) => list.reduce((n, r) => n + rect(r).height, 0), keysTall = tall(keys), list = spec.usual != null;
  const words = rows.find((r) => !keys.includes(r));
  const bare = Math.min(whole, title + keysTall);
  const first = Math.min(whole, keys.includes(rows[0]) ? bare + (words ? rect(words).height : 0) : upTo(1) + keysTall);
  const usual = Math.min(rows.length, spec.usual ?? rows.length), keep = Math.min(whole, upTo(usual) + tall(keys.filter((r) => rows.indexOf(r) >= usual)));
  const pinned = [...el.querySelectorAll(spec.pins), ...keys].sort((a, b) => rect(a).top - rect(b).top);
  return { el, whole, bare, first, keep: list ? Math.max(first, keep) : whole, list, pinned };
}

function capCard(el, cap, pinned = []) {
  const px = cap ? `${cap}px` : "";
  if (el.style.maxHeight !== px) el.style.maxHeight = px;
  if (el.classList.contains("card-capped") !== !!cap) el.classList.toggle("card-capped", !!cap);
  const was = [...el.querySelectorAll(".share-pin")];
  for (const x of was) {
    if (cap && pinned.includes(x)) continue;
    x.classList.toggle("share-pin", false);
    x.style.top = x.style.bottom = "";
  }
  if (!cap) return;
  const pad = getComputedStyle(el), tall = pinned.map((x) => x.getBoundingClientRect().height);
  let above = -parseFloat(pad.paddingTop), below = -parseFloat(pad.paddingBottom) + tall.reduce((n, h) => n + h, 0);
  pinned.forEach((x, i) => {
    below -= tall[i];
    if (!x.classList.contains("share-pin")) x.classList.toggle("share-pin", true);
    if (x.style.top !== `${above}px`) x.style.top = `${above}px`;
    if (x.style.bottom !== `${below}px`) x.style.bottom = `${below}px`;
    above += tall[i];
  });
}

const cardShares = { working: false, held: false, watch: null, sizes: "", above: [] };
const stackSizes = (stack) => [...[...stack.children].map((el) => `${el.offsetHeight}/${el.scrollHeight}`),
  ...cardShares.above.map((el) => el.getBoundingClientRect().bottom)].join(",");
function onlyWords(records, stack) {
  const text = (n) => n.nodeType === 3;
  return records.every((r) => r.type === "characterData" || (r.type === "childList" && [...r.addedNodes, ...r.removedNodes].every(text)))
    && stackSizes(stack) === cardShares.sizes;
}

function shareStack(stack) {
  if (cardShares.working) return;
  if (pressedAt && stack.contains(pressedAt)) { cardShares.held = true; return; }
  cardShares.held = false;
  cardShares.working = true;
  const cards = [...stack.children], scrolled = cards.map((el) => el.scrollTop), style = getComputedStyle(stack);
  const rect = (x) => x.getBoundingClientRect(), gap = parseFloat(style.rowGap) || 0;
  stack.style.height = style.maxHeight;
  stack.classList.add("measuring");
  for (const el of cards) el.style.maxHeight = "";
  const shown = cards.filter((el) => rect(el).height > 0), box = rect(stack);
  let full = box.height;
  for (const a of cardShares.above.map(rect)) {
    if (a.height > 0 && a.left < box.right && a.right > box.left) full = Math.min(full, box.bottom - a.bottom - gap);
  }
  const gaps = gap * Math.max(0, shown.length - 1);
  const sharing = [];
  let room = full - gaps;
  for (const el of cards) {
    const m = shown.includes(el) ? measureCard(el, SHARE_CARDS[el.id]) : null;
    if (m) sharing.push(m);
    else {
      room -= shown.includes(el) ? rect(el).height : 0;
      capCard(el, null);
    }
  }
  const plan = sharePlan(room, sharing);
  sharing.forEach((m, i) => capCard(m.el, plan[i].cap, m.pinned));
  stack.classList.remove("measuring");
  stack.style.height = "";
  cards.forEach((el, i) => { if (el.scrollTop !== scrolled[i]) el.scrollTop = scrolled[i]; });
  cardShares.sizes = stackSizes(stack);
  cardShares.watch?.takeRecords();
  cardShares.working = false;
}

function startShares(stack, above = []) {
  if (!stack) return;
  const again = () => shareStack(stack);
  cardShares.above = above.filter(Boolean);
  cardShares.watch = new MutationObserver((records) => { if (!onlyWords(records, stack)) again(); });
  for (const el of [stack, ...cardShares.above]) {
    cardShares.watch.observe(el, { childList: true, subtree: true, characterData: true, attributes: true, attributeFilter: ["hidden"] });
  }
  addEventListener("resize", again);
  const released = () => { if (cardShares.held) setTimeout(again); };
  addEventListener("pointerup", released, true);
  addEventListener("pointercancel", released, true);
  document.fonts?.ready?.then?.(again);
  again();
}

if (typeof module === "object") {
  module.exports = { SHARE_KEYS, SHARE_CARDS, SHARE_EPS, shareFill, sharePlan, measureCard, capCard, cardShares, stackSizes,
                     onlyWords, shareStack, startShares };
} else startShares(document.querySelector(".sidestack"), [document.getElementById("warnings")]);
