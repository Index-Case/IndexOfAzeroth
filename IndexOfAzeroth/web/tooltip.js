// The Index of Azeroth. Copyright 2026 Index Case <indexofazeroth@pm.me>. PolyForm Strict 1.0.0, see LICENSE.md.
"use strict";

const tipCache = {};
const itemTip = $("itemtip");
const TIP_TAGS = new Set(["TABLE", "TBODY", "TR", "TD", "TH", "B", "SPAN", "BR", "DIV", "SMALL"]);

function cleanTip(html) {
  const doc = new DOMParser().parseFromString(`<div>${html}</div>`, "text/html");
  const walk = (node) => {
    for (const child of [...node.childNodes]) {
      if (child.nodeType === Node.COMMENT_NODE) { child.remove(); continue; }
      if (child.nodeType !== Node.ELEMENT_NODE) continue;
      if (!TIP_TAGS.has(child.tagName)) {
        if (child.tagName === "A") {
          const span = doc.createElement("span");
          span.className = child.className;
          span.textContent = child.textContent;
          child.replaceWith(span);
        } else child.remove();
        continue;
      }
      for (const attr of [...child.attributes]) if (attr.name !== "class") child.removeAttribute(attr.name);
      walk(child);
    }
  };
  const root = doc.body.firstChild;
  walk(root);
  return tipCoins(root.innerHTML);
}
const TIP_MONEY = /<span class="money(gold|silver|copper)">([\d,]+)<\/span>/g;
const tipCoins = (html) => html.replace(TIP_MONEY, (_, coin, n) => coinPicture(n, coin[0]));

const TIP_AGAIN_MS = 60000;
const keptTip = (cache, id) => (cache[id]?.missing && Date.now() - cache[id].at > TIP_AGAIN_MS ? undefined : cache[id]);
const tipAnswer = (t, html) => (t.missing || t.none
  ? { missing: !!t.missing, none: !!t.none, name: t.name, quality: t.quality, at: Date.now() }
  : { html: html(t.tooltip || ""), domain: t.domain });
const tipWord = (t) => (t.none ? "No tooltip is known for this" : "The tooltip isn't stored yet");

function loadTip(id) {
  const kept = keptTip(tipCache, id);
  if (kept !== undefined) return Promise.resolve(kept);
  const asked = getJson(`/api/tooltip/${id}`, { share: true, accept: [404] });
  if (!asked) return Promise.resolve(null);
  return asked.then((t) => (tipCache[id] = tipAnswer(t, cleanTip)), () => null);
}

const spellTips = {};
const DRAWN_LEVEL = /<th>(?:(?!<\/th>)[\s\S])*?Level(?:(?!<\/th>)[\s\S])*?<\/th>/;
function loadSpellTip(id) {
  const kept = keptTip(spellTips, id);
  if (kept !== undefined) return Promise.resolve(kept);
  const asked = getJson(`/api/spelltip/${id}`, { share: true, accept: [404] });
  if (!asked) return Promise.resolve(null);
  return asked.then((t) => (spellTips[id] = tipAnswer(t, (html) => cleanTip(html.replace(DRAWN_LEVEL, "")))), () => null);
}


const statCache = {};
const STATS_EACH = 20;
const statAsks = new Map();
function loadStats(ids) {
  const want = [...new Set(ids.filter(Boolean))], need = want.filter((id) => !(id in statCache)), asks = [];
  for (let i = 0; i < need.length; i += STATS_EACH) {
    const batch = need.slice(i, i + STATS_EACH), asked = getJson(`/api/itemstats?ids=${batch.join(",")}`, { share: true });
    if (!asked) continue;
    const done = asked.then((j) => {
      for (const id of batch) {
        statCache[id] = j[id] || null;
        if (!j[id]) setTimeout(() => { if (statCache[id] === null) delete statCache[id]; }, 60000);
      }
    }, () => batch.forEach((id) => delete statCache[id])).finally(() => batch.forEach((id) => statAsks.delete(id)));
    batch.forEach((id) => { statCache[id] = undefined; statAsks.set(id, done); });
    asks.push(done);
  }
  for (const id of want) if (statAsks.has(id) && !need.includes(id)) asks.push(statAsks.get(id));
  if (need.length && !asks.length) return null;
  return Promise.all(new Set(asks)).then(() => {});
}
const WORN_IN = { Head: [1], Neck: [2], Shoulder: [3], Chest: [5], Robe: [5], Waist: [6], Legs: [7], Feet: [8], Wrist: [9],
  Hands: [10], Finger: [11, 12], Trinket: [13, 14], Back: [15], "Main Hand": [16], "One-Hand": [16], "Two-Hand": [16],
  "Off Hand": [17], "Held In Off-hand": [17], Ranged: [18], Thrown: [18], Relic: [18] };
function wornAgainst(id) {
  const st = statCache[id], slots = st && WORN_IN[st.slot];
  if (!slots || !app.equipped) return [];
  return slots.map((s) => app.equipped[s - 1]).filter((w) => w && w !== id).filter((w, i, a) => a.indexOf(w) === i);
}
function damageAs(st, key) {
  if (!st?.dps || st[key]) return st;
  const { dps, ...rest } = st;
  return { ...rest, [key]: dps };
}
const asRanged = (st) => damageAs(st, "rdps");
const statsOf = (id) => {
  const st = { ...(statCache[id]?.st || {}) };
  return ["Ranged", "Thrown"].includes(statCache[id]?.slot) ? asRanged(st) : st;
};
const LINES = [
  [/\+(\d+) (Strength|Agility|Stamina|Intellect|Spirit)\b/g, (m) => ({ Strength: "str", Agility: "agi", Stamina: "sta", Intellect: "int", Spirit: "spi" })[m[2]]],
  [/\(([\d.]+) damage per second\)/g, (m, st) => ["wdps", "rdps"].find((k) => k in st) || "dps"],
  [/(\d+) Armor\b/g, () => "armor"],
  [/Increases damage and healing done by magical spells and effects by up to (?:<span>)?(\d+)(?:<\/span>)?/g, () => "sp"],
  [/Increases healing done by spells and effects by up to (?:<span>)?(\d+)(?:<\/span>)?/g, () => "heal"],
  [/Improves your chance to hit by (?:<span>)?([\d.]+)(?:<\/span>)?%/g, () => "hit"],
  [/Improves your chance to get a critical strike by (?:<span>)?([\d.]+)(?:<\/span>)?%/g, () => "crit"],
  [/\+(?:<span>)?(\d+)(?:<\/span>)? Attack Power/g, () => "ap"],
  [/Restores (?:<span>)?(\d+)(?:<\/span>)? mana per 5 sec/g, () => "mp5"],
];
function annotate(html, mine, theirs) {
  for (const [pattern, keyOf] of LINES) {
    html = html.replace(pattern, (...args) => {
      const key = keyOf(args, mine), d = +((mine[key] || 0) - (theirs[key] || 0)).toFixed(2);
      if (!key || !d) return args[0];
      return `<span class="tip-delta ${d > 0 ? "up" : "down"}">${args[0]} (${d > 0 ? "+" : ""}${d})</span>`;
    });
  }
  return html;
}
function compareHtml(id, t) {
  const against = wornAgainst(id);
  const mine = statsOf(id);
  const panes = against.map((w) => {
    const wt = tipCache[w];
    return wt?.html ? `<div class="tip-pane"><div class="tip-equipped">Equipped</div>${annotate(wt.html, statsOf(w), mine)}</div>` : "";
  }).join("");
  const theirs = against.length ? statsOf(against[0]) : {};
  return `<div class="tip-compare">${panes}<div class="tip-pane">${annotate(t.html, mine, theirs)}</div></div>`;
}

let tipFor = null, tipEvent = null, comparing = false, tipCtrl = false;
let tipFull = false;
const tipAh = (id) => ahTipHtml(baseItem(id), tipFull, () => { if (tipFor === id) showTip(id, tipEvent); });
function showTip(id, e) {
  const t = tipCache[id];
  if (!t || tipFor !== id) return;
  const against = t.html ? wornAgainst(id) : [];
  const ready = against.length && against.every((w) => tipCache[w]?.html);
  tipCtrl = !!e?.ctrlKey;
  comparing = !!(e?.ctrlKey && ready);
  const note = t.domain === "classic" ? `<div class="tip-note">This is Classic data, because the game's tables don't hold this item</div>` : "";
  const hint = ready && !comparing
    ? `<div class="tip-hint">Hold Ctrl to compare with ${against.map((w) => esc(statCache[w]?.n || "what's worn")).join(" and ")}</div>` : "";
  const bare = () => `${t.name ? `<b class="q${t.quality ?? 1}">${esc(t.name)}</b>` : ""}<div class="tip-note">${tipWord(t)}</div>`;
  itemTip.innerHTML = (!t.html ? bare() : comparing ? compareHtml(id, t) : t.html + note + hint) + tipAh(id);
  itemTip.classList.toggle("comparing", comparing);
  itemTip.hidden = false;
  if (e) placeTip(e);
}

function placeTip(e) {
  const r = itemTip.getBoundingClientRect(), at = tipPlace({ x: e.clientX, y: e.clientY }, r.width, r.height, inWindow(), { gap: 16, margin: 8 });
  itemTip.style.left = `${at.x}px`;
  itemTip.style.top = `${at.y}px`;
}

document.addEventListener("mouseover", (e) => {
  const el = hoverOf(e.target).item;
  if (!el) {
    if (tipFor != null && e.target.closest("[data-tip]")) { tipFor = null; itemTip.hidden = true; }
    return;
  }
  const id = itemKey(el.dataset.tip);
  tipFor = id; tipEvent = e; tipFull = el.dataset.tipAh === "full";
  loadTip(id).then((t) => {
    if (tipFor !== id) return;
    if (!t) { itemTip.hidden = true; return; }
    showTip(id, e);
    if (!t.html) return;
    loadStats([id])?.then(() => {
      const against = wornAgainst(id);
      return loadStats(against)?.then(() => Promise.all(against.map(loadTip)));
    }).then(() => { if (tipFor === id) showTip(id, tipEvent); });
  });
});
function tipAgain(id) {
  delete tipCache[id];
  if (tipFor === id) loadTip(id).then((t) => { if (t && tipFor === id) showTip(id, tipEvent); });
}
for (const type of ["keydown", "keyup"]) {
  document.addEventListener(type, (e) => {
    if (e.key !== "Control" || tipFor == null || itemTip.hidden) return;
    if (!!e.ctrlKey !== tipCtrl) showTip(tipFor, { ...tipEvent, ctrlKey: e.ctrlKey, clientX: tipEvent.clientX, clientY: tipEvent.clientY });
  });
}
document.addEventListener("mousemove", (e) => {
  if (itemTip.hidden) return;
  tipEvent = e;
  if (tipFor != null && !!e.ctrlKey !== tipCtrl) showTip(tipFor, e);
  else placeTip(e);
});
document.addEventListener("mouseout", (e) => {
  const el = e.target.closest("[data-tip]");
  if (el && !el.contains(e.relatedTarget)) { tipFor = null; itemTip.hidden = true; }
});
let hoverName = null;
const hoverPin = document.createElement("div");
hoverPin.className = "itemtip hover-pin";
hoverPin.hidden = true;
document.body.appendChild(hoverPin);
function unpinHover() { hoverPin.hidden = true; delete hoverPin.dataset.name; }
document.addEventListener("click", (e) => {
  if (e.target.closest(".hover-pin")) return;
  const el = e.target.closest("[data-hover]");
  if (!el || hoverPin.dataset.name === el.dataset.hover) return unpinHover();
  const r = itemTip.hidden ? el.getBoundingClientRect() : itemTip.getBoundingClientRect();
  hoverPin.innerHTML = hoverHtml(el.dataset.hover, true);
  hoverPin.dataset.name = el.dataset.hover;
  hoverPin.hidden = false;
  const at = itemTip.hidden ? tipPlace(r, hoverPin.offsetWidth, hoverPin.offsetHeight, inWindow(), { gap: 8, y: "level" }) : { x: r.left, y: r.top };
  hoverPin.style.left = `${Math.round(at.x)}px`;
  hoverPin.style.top = `${Math.round(at.y)}px`;
  itemTip.hidden = true;
  hoverName = null;
});
closable(LAYER.pinned, () => !hoverPin.hidden, () => unpinHover());
document.addEventListener("mouseover", (e) => {
  const el = e.target.closest("[data-hover]");
  if (!el || e.target.closest("[data-tip]")) return;
  if (hoverPin.dataset.name === el.dataset.hover) return;
  const html = hoverHtml(el.dataset.hover);
  if (!html) return;
  tipFor = null;
  hoverName = el.dataset.hover;
  itemTip.innerHTML = html;
  itemTip.classList.remove("comparing");
  itemTip.hidden = false;
  placeTip(e);
});
document.addEventListener("mouseout", (e) => {
  const el = e.target.closest("[data-hover]");
  if (el && !el.contains(e.relatedTarget) && tipFor == null) { itemTip.hidden = true; hoverName = null; }
});
function refreshHover() {
  if (hoverName && !itemTip.hidden) itemTip.innerHTML = hoverHtml(hoverName);
  if (hoverPin.dataset.name) hoverPin.innerHTML = hoverHtml(hoverPin.dataset.name, true);
}
