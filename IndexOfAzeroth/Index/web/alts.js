// The Index of Azeroth. Copyright 2026 Index Case <indexofazeroth@pm.me>. PolyForm Strict 1.0.0, see LICENSE.md.
"use strict";

const alts = { data: null, version: -1, want: null, skew: 0,
  open: new Set(), query: "",
  removing: null, typed: "",
  onMap: false };
try { JSON.parse(localStorage.getItem("cc.altsOpen") || "[]").forEach((id) => alts.open.add(id)); } catch (e) {   }
try { alts.query = localStorage.getItem("cc.altsFind") || ""; } catch (e) {   }
try { alts.onMap = localStorage.getItem("cc.altsOnMap") === "1"; } catch (e) {   }
function saveAlts() {
  try {
    localStorage.setItem("cc.altsOpen", JSON.stringify([...alts.open]));
    localStorage.setItem("cc.altsFind", alts.query);
    localStorage.setItem("cc.altsOnMap", alts.onMap ? "1" : "0");
  } catch (e) {   }
}

const playingAlt = (key, d = alts.data) => !!app.link?.ok && key === d?.current;

function altsSeen(shown) {
  const d = alts.data;
  if (!alts.onMap || !d) return [];
  return Object.entries(d.chars || {}).filter(([key, c]) => c.seen?.pos && !playingAlt(key, d) && key !== shown?.character)
    .map(([, c]) => c.seen);
}

const LOCATE_ICON = $("btn-follow").querySelector(".locate-ic").outerHTML;
function locateKey(key, c, playing) {
  const name = esc(altName(c) || "this character");
  const known = playing || c.seen?.map != null;
  const tip = playing ? `Shows ${name} on the map` : known ? `Shows on the map where ${name} was last seen`
    : `The Index doesn't know yet where ${name} was last seen`;
  return `<button class="key small square alt-locate" data-locate="${esc(key)}" title="${tip}"${known ? "" : " disabled"}>${LOCATE_ICON}</button>`;
}

function refreshAlts(snap) {
  const v = alts.want = snap ? snap.versions?.characters : alts.want;
  if (v == null || v === alts.version) return;
  getJson("/api/characters")?.then((d) => {
    alts.data = d;
    alts.skew = d.now - Date.now() / 1000;
    alts.version = v;
    loadItemInfo(d);
    if (app.drawer === "alts") renderDrawer();
    if (alts.onMap) redraw();
  }, () => { if (app.drawer === "alts") renderDrawer(); });
}


function restedNow(c, d, playing) {
  const cap = (c.xpMax || 0) * d.cap;
  if (playing || !c.xpMax) return { rested: c.rested || 0, cap, fullIn: null };
  const now = Date.now() / 1000 + alts.skew;
  const perHour = c.xpMax * (c.resting ? d.rate : d.awayRate) * d.factor;
  const rested = Math.min(cap, (c.rested || 0) + perHour * Math.max(0, now - c.lastSeen) / 3600);
  return { rested, cap, fullIn: rested >= cap || !perHour ? 0 : (cap - rested) / perHour };
}

function playingRealm(d, live) {
  return live && d.current ? d.chars[d.current]?.realm || null : null;
}

function altName(c) {
  const d = alts.data || {};
  return charLabel(c, [...Object.values(d.chars || {}), ...Object.values(d.removed || {})]);
}

function altsMoved(was, key) {
  let moved = false;
  for (const old of was || []) {
    for (const id of [...alts.open]) {
      if (!old || old === key || !id.startsWith(`${old}|`)) continue;
      alts.open.delete(id);
      alts.open.add(key + id.slice(old.length));
      moved = true;
    }
  }
  if (moved) saveAlts();
}

function otherRealm(c, here) {
  return !!here && !!c.realm && c.realm !== here;
}

function realmTag(c, away, hereName) {
  if (!c.realm) return `<small class="muted alt-realm">realm not known yet</small>`;
  const tip = away ? ` title="${esc(`This character is on another realm. You're playing on ${hereName}`)}"` : "";
  return `<small class="muted alt-realm"${tip}>${esc(c.realmName)}</small>`;
}

DRAWER_TITLES.alts = "Alts";
DRAWERS.alts = function () {
  const d = alts.data;
  const list = Object.entries(d?.chars || {});
  if (!list.length) {
    return `<p class="muted">${askNote("/api/characters", { have: !!d, what: "the characters", again: () => { refreshAlts(); renderDrawer(); },
      none: "Every character played while the Index runs shows up here, with gold, bags, professions and rested experience that keeps building while they're logged out." })}</p>`;
  }
  const live = app.link?.ok;
  list.sort(([ka, a], [kb, b]) => (kb === d.current) - (ka === d.current) || (b.level || 0) - (a.level || 0) || (b.lastSeen || 0) - (a.lastSeen || 0));
  const totalGold = list.reduce((sum, [, c]) => sum + (c.money || 0), 0);
  const playedOf = ([key, c]) => (live && key === d.current ? app.status?.nums?.playedSeconds : null) ?? c.played;
  const counted = list.filter((e) => playedOf(e) != null), gone = Object.values(d.removed || {}).filter((r) => r.played);
  const totalPlayed = counted.reduce((sum, e) => sum + playedOf(e), 0) + gone.reduce((sum, r) => sum + r.played, 0);
  const goneNote = gone.length ? `<span class="alt-asterisk" title="${esc(`The total includes ${gone.length === 1 ? "a character" : `${gone.length} characters`
    } you took off the board: ${gone.map((r) => altName(r)).join(", ")}`)}">*</span>` : "";
  const uncounted = list.length - counted.length;
  const here = playingRealm(d, live);
  const playedRow = counted.length || gone.length ? `<tr><th>Played on all</th><td>${playedText(totalPlayed)}${goneNote}${
    uncounted ? ` <small class="muted">(${uncounted === 1 ? "1 character isn't counted yet. Log in on that character once"
      : `${uncounted} characters aren't counted yet. Log in on each of them once`})</small>` : ""}</td></tr>` : "";
  const cards = list.map(([key, saved]) => {
    const playing = playingAlt(key, d);
    const c = playing ? withLive(saved) : saved;
    const color = CLASS_COLORS[c.className] || "var(--ivory)";
    const maxed = (c.level || 0) >= (c.maxLevel || d.maxLevel) || !c.xpMax;
    const r = restedNow(c, d, playing);
    const xpPct = maxed ? 100 : Math.round((c.xp || 0) / c.xpMax * 1000) / 10;
    const restPct = maxed ? 0 : Math.min(100 - xpPct, Math.round(r.rested / c.xpMax * 1000) / 10);
    const restLine = maxed ? "" : `<tr><th>Rested</th><td>${Math.round(r.rested / c.xpMax * 100)}% of a level${
      r.rested >= r.cap * 0.999 ? ", full" : playing ? (c.resting ? ", building" : "") : r.fullIn ? `, full in ${restDuration(r.fullIn)}` : ""}${
      !playing && !c.resting ? ` <small class="muted">(logged out outside an inn, so rested builds at a quarter of the rate)</small>` : ""}</td></tr>`;
    const profs = (c.professions || []).map((p) => `${esc(p.name)} ${p.rank}/${p.max}`).join(", ");
    const where = [c.subzone, c.zone].filter(Boolean).filter((v, i, a) => a.indexOf(v) === i).join(", ");
    const gearOpen = alts.open.has(`${key}|Gear`);
    const restOpen = alts.open.has(`${key}|Card`);
    const away = otherRealm(c, here);
    return `<div class="alt-card${playing ? " playing" : ""}${away ? " other-realm" : ""}">
      <div class="alt-head">${locateKey(key, c, playing)}<span class="alt-name" style="color:${color}">${charMarks(c)}${esc(altName(c))}</span>
        <button class="key small alt-char" data-show="${esc(key)}|Gear" aria-pressed="${gearOpen}" style="--icon:url(/icon/${GEAR_ICON}.jpg)"
          title="Shows what ${esc(altName(c) || "this character")} wears, laid out like the game's character panel">Gear</button>
        <span class="alt-level">${c.level ? `Level ${c.level}` : ""} ${esc(raceClass(c))} ${realmTag(c, away, d.chars[d.current]?.realmName)}</span></div>
      ${gearOpen ? paperDoll(c, playing, key) : ""}
      ${maxed ? "" : `<div class="bigbar alt-bar"><div class="rest" style="left:${xpPct}%;width:${restPct}%"></div>
        <div class="fill" style="width:${xpPct}%">${heatEdgeHtml((c.xp || 0) / c.xpMax, 0, HEAT_XP)}</div></div>`}
      <div class="alt-rest fold plus-fold${restOpen ? " open" : ""}"><button class="fold-plus" data-show="${esc(key)}|Card"
        aria-expanded="${restOpen}" title="Expands or collapses the rest of this card"></button><div class="fold-more">
      <table class="facts">
        ${playing ? playingRows(c, d) : restLine}
        ${c.talentPoints ? `<tr><th>Talents</th><td class="zero-text">${c.talentPoints} unspent</td></tr>` : ""}
        <tr><th>Gold</th><td>${money(c.money || 0)}</td></tr>
        ${c.played != null ? `<tr><th>Played</th><td>${playedText(c.played)}${c.levelPlayed != null ? `, ${playedText(c.levelPlayed)} at this level` : ""}</td></tr>` : ""}
        ${c.bags ? containerRow(key, "Bags", c.bags, playing, `${c.bagFree ?? c.bags.free} of ${c.bagSlots ?? c.bags.slots} free`)
          : c.bagSlots ? `<tr><th>Bags</th><td>${c.bagFree} of ${c.bagSlots} free</td></tr>` : ""}
        ${c.bank ? containerRow(key, "Bank", c.bank, false) : `<tr><th>Bank</th><td class="muted">Open the bank once on ${esc(altName(c) || "this character")} to see the bank here</td></tr>`}
        ${c.durability != null ? `<tr><th>Durability</th><td>${c.durability}% lowest</td></tr>` : ""}
        ${c.bind ? `<tr><th>Hearth</th><td>${esc(c.bind)}</td></tr>` : ""}
        ${profs ? `<tr><th>Professions</th><td>${profs}</td></tr>` : ""}
        ${playing ? "" : altProfRow(key)}
        ${legacyCardRow(key, c, d.legacyBoard)}
        <tr><th>${playing ? "Playing" : "Last seen"}</th><td>${playing ? esc(where) : `${ago(c.lastSeen)}${where ? `, ${esc(where)}` : ""}`}</td></tr>
      </table>${removeRow(key, c)}</div></div></div>`;
  }).join("");
  const rate = d.samples ? `The Index measured the rested rate on Forever at ${Math.round(d.factor * 100)}% of Classic's rate, from ${d.samples} login${d.samples > 1 ? "s" : ""}.`
    : "The Index uses Classic's rested rate. A character gains 5% of a level per 8 hours in an inn or city and a quarter of that anywhere else, up to 150%. Each login checks the rate against the game.";
  return `<div class="alt-find"><div class="alt-find-row">${searchBox("alt-find", "Find an item on any character", alts.query)}
    <label class="alt-onmap"><input type="checkbox" data-alts-map="1"${alts.onMap ? " checked" : ""}> Show on map</label></div>${findResults(d)}</div>
    <table class="facts"><tr><th>Characters</th><td>${list.length}</td></tr><tr><th>Gold on all</th><td>${money(totalGold)}</td></tr>
      ${playedRow}
      ${legacyRow(d.legacyBoard)}
      ${d.warband ? containerRow("account", "Warband bank", d.warband, false) : ""}</table>
    ${cards}
    <p class="muted">${rate} Numbers are from each character's last session.</p>`;
};


function legacyRow(b) {
  if (!b) return "";
  const open = alts.open.has("account|Legacy");
  const parts = [`${b.earned} earned`];
  if (b.granted) parts.push(`${b.granted} granted`);
  const has = b.max != null ? `, ${b.max} on the account` : "";
  const cap = b.cap != null ? `. Each character can spend up to ${b.cap}` : "";
  const total = b.total ? ` <small class="muted">(the challenges give ${b.total} points in all)</small>` : "";
  const list = open ? `<div class="legacy-done">${b.done.length ? b.done.map((x) => `<div>${esc(x.text)}: ${x.amount} ${x.amount === 1 ? "point" : "points"}${
    x.by ? `, ${esc(x.by)}` : ""}</div>`).join("") : `<p class="muted">You haven't done any challenge yet</p>`}</div>` : "";
  return `<tr><th><span class="with-help">Legacy points${helpButton("legacy")}</span></th><td>${parts.join(", ")}${has}${cap}${total}
    <button class="alt-show" data-show="account|Legacy">${open ? "Hide" : "Show"}</button>${list}</td></tr>`;
}

function legacyCardRow(key, c, b) {
  if (!b) return "";
  const earned = b.byChar?.[key] || 0, mine = c.legacy;
  const own = mine && (mine.spent != null || mine.unspent != null)
    ? `. ${mine.spent ?? "?"} spent, ${mine.unspent ?? "?"} left to spend` : "";
  if (!earned && !own) return "";
  return `<tr><th>Legacy</th><td>${earned} earned${own}</td></tr>`;
}


function containerIds(d) {
  const ids = new Set();
  const add = (snap) => {
    Object.keys(snap?.items || {}).forEach((id) => ids.add(id));
    (snap?.each || []).forEach((b) => b.id && ids.add(String(b.id)));
  };
  Object.values(d?.chars || {}).forEach((c) => { add(c.bags); add(c.bank); (c.equipped?.items || []).forEach((id) => id && ids.add(String(id))); });
  (app.equipped || []).forEach((id) => id && ids.add(String(baseItem(id))));
  add(d?.warband);
  return [...ids];
}


function removeRow(key, c) {
  if (alts.removing !== key) {
    return `<div class="alt-remove"><button class="alt-remove-ask" data-remove="${esc(key)}">Remove from the board</button></div>`;
  }
  const name = esc(altName(c) || "this character");
  return `<div class="alt-remove confirm"><p>Type <b>FORGET</b> to take ${name} off the board. The Index keeps the character's record,
      and the record comes back whole when you log in on ${name} again.</p>
    <input id="alt-forget" autocomplete="off" spellcheck="false" value="${esc(alts.typed)}" aria-label="Type FORGET to confirm">
    <button class="key small" data-remove-go="${esc(key)}"${alts.typed === "FORGET" ? "" : " disabled"}>Remove</button>
    <button class="key small" data-remove-cancel>Cancel</button></div>`;
}

$("drawer").addEventListener("input", (e) => {
  if (e.target.id !== "alt-forget") return;
  alts.typed = e.target.value;
  const go = document.querySelector("#drawer [data-remove-go]");
  if (go) go.disabled = alts.typed !== "FORGET";
});


const DOLL_LEFT = [[1, "head"], [2, "neck"], [3, "shoulder"], [15, "chest"], [5, "chest"], [4, "shirt"], [9, "wrists"]];
const DOLL_RIGHT = [[10, "hands"], [6, "waist"], [7, "legs"], [8, "feet"], [11, "finger"], [12, "finger"], [13, "trinket"], [14, "trinket"]];
const DOLL_WEAPONS = [[16, "mainhand"], [17, "offhand"], [18, "ranged"]];

function charIcon(c) {
  return c.className ? `classicon_${c.className.toLowerCase().replace(/\s+/g, "")}` : "inv_shirt_16";
}

const GEAR_ICON = "inv_shirt_16";

function charMarks(c, big) {
  const side = (c.faction || "").toLowerCase(), size = big ? "large/" : "";
  const crest = side === "alliance" || side === "horde"
    ? `<img class="char-crest" src="/detailview/crests/${side}.png" alt="${esc(c.faction)}" title="${esc(c.faction)}">` : "";
  const cls = c.className ? `<img class="char-class" src="/icon/${size}${esc(charIcon(c))}.jpg" alt="${esc(c.className)}" title="${esc(c.className)}">` : "";
  return crest || cls ? `<span class="char-marks${big ? " big" : ""}">${crest}${cls}</span>` : "";
}

function raceClass(c) {
  return [c.raceName, c.className].filter(Boolean).join(" ");
}

function dollSlot([slot, empty], items, comparing) {
  const id = items?.[slot - 1], mark = comparing ? compareMark(slot, id) : "";
  if (!id) return `<span class="bank-item doll-empty"><img src="/icon/inventoryslot_${empty}.jpg" alt="">${mark}</span>`;
  return altItemIcon(String(id), 0, mark);
}

function paperDoll(c, playing, key) {
  const saved = c.equipped;
  const items = playing && app.equipped ? app.equipped : saved?.keys || saved?.items;
  if (!items) {
    return `<p class="muted doll-note">Log in on ${esc(altName(c) || "this character")} once with the addon running to see what ${esc(altName(c) || "the character")} wears here.</p>`;
  }
  const worn = items.filter(Boolean).length;
  const cur = alts.data?.chars?.[alts.data.current], me = (cur && altName(cur)) || "you";
  const canCompare = !playing && !!app.equipped, comparing = canCompare && alts.open.has(`${key}|Compare`);
  if (comparing) { wantDollStats(items); loadStatWeights(); }
  const col = (slots) => `<div class="doll-col">${slots.map((s) => dollSlot(s, items, comparing)).join("")}</div>`;
  return `<div class="doll">${col(DOLL_LEFT)}
      <div class="doll-mid">${charMarks(c, true)}
        ${raceClass(c) ? `<span class="doll-who" style="color:${CLASS_COLORS[c.className] || "var(--ivory)"}">${esc(raceClass(c))}</span>` : ""}
        <span>${worn} of 18 slots</span><small class="muted">${playing ? "wearing now" : `as of ${ago(saved.at)}`}</small>
        ${canCompare ? `<button class="key small doll-compare" data-show="${esc(key)}|Compare" aria-pressed="${comparing}"
          title="Marks each piece by what the piece would do for ${esc(me)} against what ${esc(me)} wears in that slot, using the stat weights of ${esc(me)}'s spec">Compare with ${esc(me)}</button>` : ""}</div>
      ${col(DOLL_RIGHT)}
      <div class="doll-weapons">${DOLL_WEAPONS.map((s) => dollSlot(s, items, comparing)).join("")}</div></div>`;
}

function compareMark(slot, altId) {
  const mine = app.equipped?.[slot - 1];
  if (!altId && !mine) return "";
  if (altId && String(altId) === String(mine)) return `<i class="doll-cmp same" title="You wear this same piece">=</i>`;
  const theirs = altId && statCache[altId] ? { ...statCache[altId], st: inSlot(statCache[altId].st, slot) } : null, yours = wornIn(slot);
  if ((altId && !theirs) || yours === undefined) return "";
  const up = compareGear(theirs, yours), down = compareGear(yours, theirs);
  if (!up || !down) return "";
  if (up.kind) return `<i class="doll-cmp up ${up.kind}" title="${esc(compareWords(up))}">▲</i>`;
  if (down.kind) {
    const better = down.gains.slice(0, 4).map(([k, d]) => statWords(k, d, true)).join(", ");
    return `<i class="doll-cmp down" title="${esc(`Your piece is better for ${down.who}${better ? `: ${better}` : ""}`)}">▼</i>`;
  }
  return `<i class="doll-cmp even" title="This piece and yours are about the same for you">≈</i>`;
}

alts.statsAsked = new Set();
function wantDollStats(items) {
  const ids = items.filter((id) => id && !statCache[id] && !alts.statsAsked.has(String(id))).map(String);
  if (!ids.length) return;
  const asked = loadStats(ids);
  if (!asked) return;
  ids.forEach((id) => alts.statsAsked.add(id));
  asked.then(() => {
    ids.filter((id) => !statCache[id]).forEach((id) => alts.statsAsked.delete(id));
    if (app.drawer === "alts" && ids.some((id) => statCache[id])) renderDrawer();
  });
}

function loadItemInfo(d) {
  wantItemInfo(containerIds(d), () => { if (app.drawer === "alts") { renderDrawer(); } });
}

function altItemIcon(id, count, extra = "") {
  const info = app.itemInfo[baseItem(id)];
  return `<span class="bank-item q${info?.q ?? 1}" data-tip="${esc(id)}"><img src="/icon/${esc(info?.icon || "inv_misc_questionmark")}.jpg" alt="">${
    count > 1 ? `<b>${count > 999 ? `${Math.floor(count / 1000)}k` : count}</b>` : ""}${extra}</span>`;
}

function heldItems(snap) {
  const out = { ...(snap?.items || {}) };
  for (const [key, n] of Object.entries(snap?.sfx || {})) {
    const id = String(baseItem(key));
    out[key] = n;
    out[id] = (out[id] || 0) - n;
    if (out[id] <= 0) delete out[id];
  }
  return out;
}

function itemGrid(items) {
  const info = (id) => app.itemInfo[baseItem(id)];
  const list = Object.entries(items || {}).sort(([a], [b]) => (info(b)?.q ?? 0) - (info(a)?.q ?? 0)
    || (info(a)?.n || "").localeCompare(info(b)?.n || ""));
  return list.length ? `<div class="bank-grid">${list.map(([id, n]) => altItemIcon(id, n)).join("")}</div>` : `<p class="muted">Empty</p>`;
}

function containerRow(key, label, snap, live, fullness) {
  const kinds = Object.keys(snap.items || {}).length, id = `${key}|${label}`, open = alts.open.has(id);
  const text = `${fullness || `${snap.free} of ${snap.slots} free`}, ${kinds} kind${kinds === 1 ? "" : "s"} of item${live ? "" : `, read ${ago(snap.at)}`}`;
  return `<tr><th>${esc(label)}</th><td>${text} <button class="alt-show" data-show="${esc(id)}">${open ? "Hide" : "Show"}</button>
    ${open ? itemGrid(heldItems(snap)) : ""}</td></tr>`;
}

function findResults(d) {
  const q = alts.query.trim();
  if (q.length < 2) return "";
  const found = {};
  const add = (who, where, snap) => {
    for (const [id, n] of Object.entries(snap?.items || {})) {
      if (!matchesSearch(app.itemInfo[id]?.n, q)) continue;
      (found[id] ||= []).push({ who, where, n });
    }
  };
  Object.values(d.chars || {}).forEach((c) => { add(altName(c), "bags", c.bags); add(altName(c), "bank", c.bank); });
  add("Warband bank", "", d.warband);
  const rows = Object.entries(found).sort(([a], [b]) => app.itemInfo[a].n.localeCompare(app.itemInfo[b].n)).slice(0, 30).map(([id, holders]) => {
    const info = app.itemInfo[id], total = holders.reduce((sum, h) => sum + h.n, 0);
    return `<div class="find-row">${altItemIcon(id, 0)}<span class="find-text"><span class="find-name q${info.q}" data-tip="${esc(id)}">${esc(info.n)}</span>
      <small>${num(total)} in all: ${holders.map((h) => `${esc(h.who)} ${num(h.n)}${h.where ? ` in ${h.where}` : ""}`).join(", ")}</small></span></div>`;
  }).join("");
  return `<div class="find-results">${rows || `<p class="muted">No item by that name is in any bags or bank the board has seen.</p>`}</div>`;
}

function altsSearched(e) {
  if (e.target.id !== "alt-find") return;
  alts.query = e.target.value;
  saveAlts();
  renderDrawer();
}
$("drawer").addEventListener("input", altsSearched);

function withLive(c) {
  const s = app.state, n = app.status?.nums || {};
  if (!s) return c;
  return { ...c, level: s.level, xp: s.xp, xpMax: s.xpMax, rested: s.rested, resting: !!s.flags?.resting, zone: s.zone, subzone: s.subzone,
    money: n.money ?? c.money, bagFree: n.bagFree ?? c.bagFree, bagSlots: n.bagSlots ?? c.bagSlots,
    durability: n.durability ?? c.durability, talentPoints: n.talentPoints ?? c.talentPoints,
    played: n.playedSeconds ?? c.played, levelPlayed: n.levelSeconds ?? c.levelPlayed, maxLevel: app.maxLevel || c.maxLevel };
}

function playingRows(c, d) {
  if ((c.level || 0) >= (c.maxLevel || d.maxLevel) || !c.xpMax) return "";
  const left = c.xpMax - c.xp, cap = c.xpMax * d.cap;
  const covers = left > 0 ? Math.min(100, Math.round(c.rested / left * 100)) : 0;
  const perHour = c.xpMax * (c.resting ? d.rate : d.awayRate) * d.factor;
  const full = c.rested >= cap * 0.999;
  const logout = full ? "Rested is full, so logging out here gains nothing more"
    : `Rested is full in ${restDuration((cap - c.rested) / perHour)}${c.resting ? "" : `. Out here rested builds at a quarter of the rate${
      c.bind ? `. Hearth to ${esc(c.bind)} for the full rate` : ". An inn or a city gives the full rate"}`}`;
  return `<tr><th>Experience</th><td>${num(c.xp)} / ${num(c.xpMax)} (${Math.round(c.xp / c.xpMax * 100)}%), ${num(left)} to level ${c.level + 1}</td></tr>
    <tr><th>Rested</th><td>${c.rested ? `${num(c.rested)}, ${Math.round(c.rested / c.xpMax * 100)}% of a level, covers ${covers}% of the experience left in this level` : "None"}</td></tr>
    <tr><th>Resting</th><td>${c.resting ? "Yes, rested experience is building" : "No"}</td></tr>
    <tr><th>Log out here</th><td>${logout}</td></tr>`;
}

function altsClicked(e) {
  const locate = e.target.closest("button[data-locate]");
  if (locate) {
    const key = locate.dataset.locate, c = alts.data?.chars?.[key];
    return playingAlt(key) ? centreOnMe() : showSeen(c?.seen);
  }
  const show = e.target.closest("button[data-show]");
  if (show) {
    const id = show.dataset.show;
    if (alts.open.has(id)) alts.open.delete(id); else alts.open.add(id);
    saveAlts();
    return renderDrawer();
  }
  const ask = e.target.closest("button[data-remove]");
  if (ask) {
    alts.removing = ask.dataset.remove;
    alts.typed = "";
    renderDrawer();
    return $("alt-forget")?.focus();
  }
  if (e.target.closest("button[data-remove-cancel]")) {
    alts.removing = null;
    return renderDrawer();
  }
  const go = e.target.closest("button[data-remove-go]");
  if (!go || alts.typed !== "FORGET" || !alts.data) return;
  const key = go.dataset.removeGo;
  alts.removing = null;
  postJson("/api/characters", { forget: key, confirm: "FORGET" }).then(() => { delete alts.data.chars[key]; renderDrawer(); },
    (e) => { askFailed("The character is still on the board", e); renderDrawer(); });
}
$("drawer").addEventListener("click", altsClicked);

function altsMapSwitched(e) {
  if (!e.target.dataset?.altsMap) return;
  alts.onMap = e.target.checked;
  saveAlts();
  redraw();
}
$("drawer").addEventListener("change", altsMapSwitched);

on("start", () => setInterval(() => { if (app.drawer === "alts" && document.activeElement?.id !== "alt-find") { renderDrawer(); } }, 60000));
