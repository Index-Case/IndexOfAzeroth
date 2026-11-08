// The Index of Azeroth. Copyright 2026 Index Case <indexofazeroth@pm.me>. PolyForm Strict 1.0.0, see LICENSE.md.
"use strict";

const jr = { open: false, key: null, tab: "bosses", boss: 0, quest: 0, side: null, kind: "dungeon", floor: 0, html: "", runs: null,
  history: [],
  scroll: [0, 0], place: null, saved: "", reopen: false };
const HISTORY_MAX = 30;

function pushView() {
  jr.history.push({ key: jr.key, tab: jr.tab, boss: jr.boss, kind: jr.kind, floor: jr.floor });
  if (jr.history.length > HISTORY_MAX) jr.history.shift();
}
function goBack() {
  const v = jr.history.pop();
  if (!v) return;
  Object.assign(jr, v);
  if (jr.tab === "run") loadRuns();
  renderJournal();
}
const journalKept = keptOr("cc.journal", {});
journalBack(journalKept);
function journalBack(k) {
  const view = (x) => x && typeof x === "object" && (x.key === null || typeof x.key === "string");
  const num = (x) => (Number.isInteger(x) && x >= 0 ? x : 0);
  if (typeof k.tab === "string" && k.tab) jr.tab = k.tab;
  if (typeof k.kind === "string" && k.kind) jr.kind = k.kind;
  if (!view(k)) return;
  Object.assign(jr, { key: k.key, boss: num(k.boss), quest: num(k.quest), side: typeof k.side === "string" ? k.side : null,
    floor: num(k.floor), history: (Array.isArray(k.history) ? k.history : []).filter(view).slice(-HISTORY_MAX)
      .map((h) => ({ key: h.key, tab: typeof h.tab === "string" ? h.tab : "bosses", boss: num(h.boss), kind: typeof h.kind === "string" ? h.kind : "dungeon", floor: num(h.floor) })) });
  const sc = Array.isArray(k.scroll) ? k.scroll.map(num) : [];
  jr.scroll = [sc[0] || 0, sc[1] || 0];
  jr.place = jr.scroll[0] || jr.scroll[1] ? { to: jr.scroll.slice() } : null;
  jr.reopen = k.open === true;
}

const QUALITY = [tint("quality-poor"), tint("white"), tint("quality-uncommon"), tint("quality-rare"), tint("quality-epic"),
  tint("quality-legendary")];
const CLASS_BIT = (classId) => 1 << ((classId || 1) - 1);
const ARMOR_OK = {
  1: { 1: 1, 2: 1, 3: 1, 4: 40, 6: 1 }, 2: { 1: 1, 2: 1, 3: 1, 4: 40, 6: 1, 7: 1 }, 3: { 1: 1, 2: 1, 3: 40 }, 4: { 1: 1, 2: 1 },
  5: { 1: 1 }, 7: { 1: 1, 2: 1, 3: 40, 6: 1, 9: 1 }, 8: { 1: 1 }, 9: { 1: 1 }, 11: { 1: 1, 2: 1, 8: 1 },
};
const WEAPON_OK = {
  1: [0, 1, 2, 3, 4, 5, 6, 7, 8, 10, 13, 15, 16, 18], 2: [0, 1, 4, 5, 6, 7, 8], 3: [0, 1, 2, 3, 6, 7, 8, 10, 13, 15, 16, 18],
  4: [0, 2, 3, 4, 7, 13, 15, 16, 18], 5: [4, 10, 15, 19], 7: [0, 1, 4, 5, 10, 13, 15], 8: [7, 10, 15, 19], 9: [7, 10, 15, 19],
  11: [4, 5, 10, 13, 15],
};
const WEAPON_SKILL = { 0: "Axes", 1: "Two-Handed Axes", 2: "Bows", 3: "Guns", 4: "Maces", 5: "Two-Handed Maces", 6: "Polearms",
  7: "Swords", 8: "Two-Handed Swords", 10: "Staves", 13: "Fist Weapons", 15: "Daggers", 16: "Thrown", 18: "Crossbows", 19: "Wands" };
const ARMOR_SKILL = { 1: "Cloth", 2: "Leather", 3: "Mail", 4: "Plate Mail", 6: "Shield" };
const ARMOR_NAME = { 1: "cloth", 2: "leather", 3: "mail", 4: "plate" };
const ARMOR_TOP = { 1: [3, 4], 2: [3, 4], 3: [2, 3], 7: [2, 3], 4: [2], 11: [2], 5: [1], 8: [1], 9: [1] };
const BODY_ARMOR = new Set([1, 3, 5, 20, 6, 7, 8, 9, 10]);
const SLOTS_FOR = { 1: [1], 2: [2], 3: [3], 5: [5], 20: [5], 6: [6], 7: [7], 8: [8], 9: [9], 10: [10], 11: [11, 12], 12: [13, 14],
  16: [15], 13: [16, 17], 17: [16], 21: [16], 22: [17], 14: [17], 23: [17], 15: [18], 26: [18], 25: [18], 28: [18] };

function usability(it) {
  return usabilityFor(it, app.status?.classId, app.state?.level || 1, app.status?.nums || {});
}
function usabilityFor(it, cls, level = 1, n = {}) {
  if (!cls || !it) return { use: "yes" };
  if (it.classes && !(it.classes & CLASS_BIT(cls))) return { use: "never" };
  if (it.cls === 4 && it.sub) {
    const need = ARMOR_OK[cls]?.[it.sub], skill = ARMOR_SKILL[it.sub];
    if (!need) return { use: "never" };
    if (!skill) return { use: "yes" };
    const known = n.armorKinds & 2 ? n.armorKinds : null;
    if (known != null ? known & (1 << it.sub) : level >= need) {
      const best = bestArmorFor(cls, level, n);
      return best && BODY_ARMOR.has(it.inv) && it.sub < best ? { use: "yes", lower: best } : { use: "yes" };
    }
    return level < need ? { use: "later", skill, level: need } : { use: "train", skill };
  }
  if (it.cls === 2 && WEAPON_SKILL[it.sub]) {
    if (!(WEAPON_OK[cls] || []).includes(it.sub)) return { use: "never" };
    const known = n.weaponKinds || null;
    return known == null || known & (1 << it.sub) ? { use: "yes" } : { use: "train", skill: WEAPON_SKILL[it.sub] };
  }
  return { use: "yes" };
}
const canUse = (it) => usability(it).use !== "never";

function bestArmorFor(cls, level = 1, n = {}) {
  const top = ARMOR_TOP[cls];
  if (!top) return null;
  const known = n.armorKinds & 2 ? n.armorKinds : null;
  return top[1] && (known != null ? known & (1 << top[1]) : level >= 40) ? top[1] : top[0];
}

function upgradeKind(u, up, cmp) {
  if (!up) return "";
  if (u.use === "train") return "train";
  if (u.lower) return "lower";
  return cmp?.kind || "item-level";
}
const UPGRADE_COLOUR = { train: "gold", lower: "grey", clear: "up", weak: "gold", debatable: "debatable", "item-level": "gold" };

function upgradeTag(it, u, up, cmp) {
  const kind = upgradeKind(u, up, cmp);
  if (!kind) return "";
  const [text, tip] = kind === "train"
    ? [esc(word("both.upgrades.train", { skill: u.skill })), word("both.upgrades.train.tip", { skill: u.skill,
      teacher: it.cls === 2 ? word("both.upgrades.train.weapon") : word("both.upgrades.train.armour") })]
    : kind === "lower" ? [word("both.upgrades.lower"), word("both.upgrades.lower.tip", { kind: ARMOR_NAME[it.sub], wear: ARMOR_NAME[u.lower] })]
    : kind === "item-level" ? [word("both.upgrades.item-level"), word("both.upgrades.item-level.tip")]
    : [{ clear: word("both.upgrades.clear"), weak: word("both.upgrades.weak"), debatable: word("both.upgrades.debatable") }[kind], compareWords(cmp)];
  return `<span class="j-tag ${UPGRADE_COLOUR[kind]}" title="${esc(tip)}">${text}</span>`;
}

function rowCompare(id, it) {
  loadGear();
  const st = it.st || gear.data?.items?.[id]?.st || statCache[id]?.st, r = replaced(it.inv);
  return st && r.known ? compareGear({ st: inSlot(st, r.slot) }, r.against) : null;
}

function isUpgrade(it) {
  const gear = app.run?.gear;
  const slots = it && SLOTS_FOR[it.inv];
  if (!gear || !slots || !it.il || !gear.some((v) => v > 0)) return false;
  return it.il > Math.min(...slots.map((s) => gear[s - 1] || 0));
}

function fit(d) {
  const lvl = app.state?.level || 0, [min, lo, hi] = d.levels || [0, 0, 0];
  if (d.notOpen) return ["", ""];
  if (!lvl || !d.levels) return ["", ""];
  if (lvl < Math.max(min, d.openFrom || 0)) return [word("page.journal.dungeon.fit.low"), "red"];
  if (lvl < lo) return [word("page.journal.dungeon.fit.stretch"), "yellow"];
  if (lvl <= hi) return [word("page.journal.dungeon.fit.right"), "green"];
  if (lvl <= hi + 5) return [word("page.journal.dungeon.fit.easy"), "grey"];
  return [word("page.journal.dungeon.fit.gray"), "grey"];
}

const levelsText = (d) => (!d.levels ? "" : d.levels[1] !== d.levels[2] ? word("page.journal.dungeon.levels.range", { lo: d.levels[1], hi: d.levels[2] })
  : word("page.journal.dungeon.levels.from", { level: d.levels[0] || "?" }));
function levelsNote(d) {
  const notes = d.gameLevel ? [word("page.journal.dungeon.levels.game", { level: d.gameLevel })] : [];
  if (d.openLevels) notes.push(word("page.journal.dungeon.levels.notes", { lo: d.openLevels[0], hi: d.openLevels[1] }));
  else if (d.openFrom) notes.push(word("page.journal.dungeon.levels.notes-from", { level: d.openFrom }));
  for (const [lo, hi] of d.levelsElsewhere || []) notes.push(word("page.journal.dungeon.levels.maybe", { lo, hi }));
  return notes.join(", ");
}
function dayAhead(day) {
  const at = day ? new Date(`${day}T00:00:00`) : null;
  return at && at > new Date() ? at.toLocaleDateString("en-GB", { day: "numeric", month: "short" }) : "";
}
function whenText(d) {
  if (d.notOpen) return word("page.journal.dungeon.when.not-open");
  const day = dayAhead(d.opens);
  if (day) return word("page.journal.dungeon.when.opens", { day });
  if (d.later) return word("page.journal.dungeon.when.later");
  return d.coming ? word("page.journal.dungeon.when.coming") : "";
}
const playersText = (d) => (!d.players ? "" : d.kind === "battleground" ? word("page.journal.dungeon.players.battleground", { n: d.players })
  : word("page.journal.dungeon.players", { n: d.players }));
const faction = () => app.status?.strs?.faction || "Alliance";
function questFits(q, side = faction()) {
  if (q.side !== "Both" && q.side !== side) return false;
  return !(q.classes && side === faction() && app.status?.classId && !(q.classes & CLASS_BIT(app.status.classId)));
}

function saveJournal() {
  const kept = { tab: jr.tab, kind: jr.kind, open: jr.open, key: jr.key, boss: jr.boss, quest: jr.quest, side: jr.side, floor: jr.floor,
    history: jr.history, scroll: jr.scroll };
  const text = JSON.stringify(kept);
  if (text !== jr.saved) keepIn("cc.journal", kept);
  jr.saved = text;
}
function journalScrolled(e) {
  const list = e.target.matches?.(".j-list") ? 1 : e.target.matches?.(".j-detail, .j-single") ? 0 : -1;
  if (list < 0 || jr.place) return;
  jr.scroll[list] = Math.round(e.target.scrollTop);
  saveJournal();
}
function placeJournal(box) {
  const p = jr.place, els = [box.querySelector(".j-detail, .j-single"), box.querySelector(".j-list")];
  if (!p || !els[0]) return;
  const there = els.map((el, i) => {
    if (!el) return !p.to[i];
    el.scrollTop = p.to[i];
    return Math.abs(el.scrollTop - p.to[i]) < 1;
  });
  if (there.every(Boolean)) { jr.place = null; jr.scroll = p.to.slice(); }
}
const journalTouched = () => { if (jr.place) { jr.scroll = jr.place.to.slice(); jr.place = null; } };


function openJournal(key, tab) {
  if (!jr.open) jr.history = [];
  showJournal(key, tab);
}
function showJournal(key, tab) {
  jr.open = true;
  if (key !== undefined && key !== jr.key) { jr.key = key; jr.boss = 0; jr.quest = 0; jr.floor = 0; jr.place = null; }
  if (tab) jr.tab = tab;
  $("journal").hidden = false;
  $("btn-journal").setAttribute("aria-pressed", "true");
  if (jr.tab === "run") loadRuns();
  renderJournal();
}

function closeJournal() {
  jr.open = false;
  $("journal").hidden = true;
  $("btn-journal").setAttribute("aria-pressed", "false");
  saveJournal();
}

function toggleJournal() {
  if (jr.open) return closeJournal();
  openJournal(app.dungeon?.key ?? jr.key);
}

function loadRuns() {
  getJson("/api/runs")?.then((j) => { jr.runs = j; renderJournal(); }, () => renderJournal());
}

function dungeonForEntrance(name) {
  const n = (name || "").toLowerCase().replace(/^the /, "");
  return dungeon.list.find((d) => d.name.toLowerCase().replace(/^the /, "") === n)
    || dungeon.list.find((d) => d.name.toLowerCase().replace(/^the /, "").split(":")[0] === n)
    || dungeon.list.find((d) => d.name.toLowerCase().replace(/^(the |lower |upper )/, "").startsWith(n));
}


function itemRowHtml({ id, icon, q, name, line = "", more = "", after = "", cls = "" }) {
  const color = QUALITY[q] || tint("white");
  return `<div class="j-item${cls ? ` ${cls}` : ""}" data-tip="${esc(id)}"><img src="${icon}" alt="" class="q${esc(q)}">
    <div class="j-item-text"><b style="color:${color}">${esc(name)}</b><small>${line}</small>${more}</div>${after}</div>`;
}

function starButton(id) {
  const on = isWished(id), who = dungeon.stars !== null;
  const title = !who ? word("page.journal.items.star.off") : on ? word("page.journal.items.star.on") : word("page.journal.items.star.tip");
  return `<button class="j-star${on ? " on" : ""}" data-star="${id}"${who ? "" : " disabled"} title="${title}">${on ? "★" : "☆"}</button>`;
}

function itemRow(id, d) {
  const it = d.items[id];
  if (!it) return "";
  const u = usability(it), usable = u.use !== "never", cmp = usable ? rowCompare(id, it) : null;
  const up = (u.use === "yes" || u.use === "train") && (cmp ? !!cmp.kind : isUpgrade(it));
  const line = [it.slot, it.kind && it.kind !== it.slot ? it.kind : ""].filter(Boolean).join(", ");
  const star = starButton(id);
  return itemRowHtml({ id, icon: itemIcon(it), q: it.q, name: it.n, cls: usable ? "" : "unusable",
    line: [esc(line), it.rl > 1 ? word("page.journal.items.requires", { level: it.rl }) : "",
      usable ? "" : word("page.journal.items.never"),
      u.use === "later" ? esc(word("page.journal.items.later", { skill: u.skill, level: u.level }))
        : u.use === "train" ? esc(word("page.journal.items.train", { skill: u.skill })) : ""].filter(Boolean).join(", "),
    after: upgradeTag(it, u, up, cmp) + star });
}

function questState(q, d) {
  const log = (app.quests?.log || []).find((l) => l.id === q.id);
  if (log) return log.complete ? [word("page.journal.quests.state.ready"), "green"] : [word("page.journal.quests.state.have"), "cyan"];
  const idx = d.quests.indexOf(q);
  if ((app.quests?.done?.[d.index] || []).includes(idx)) return [word("page.journal.quests.state.done"), "grey"];
  if ((q.req || 0) > (app.state?.level || 99)) return [word("page.journal.quests.state.low"), "red"];
  return ["", ""];
}

function place(p) {
  if (!p) return "";
  if (p.inside) {
    return word("page.journal.quests.place.inside", { name: p.name, dungeon: p.dungeon || word("page.journal.quests.place.the-dungeon") });
  }
  if (p.item) return word("page.journal.quests.place.item", { name: p.name });
  return p.zone ? word("page.journal.quests.place.zone", { name: p.name, zone: p.zone }) : p.name;
}

function placeKey(p, which, idx, title) {
  return p?.map ? `<button class="key small" data-go-${which}="${idx}" title="${esc(title)}">${word("page.journal.quests.guide")}</button>` : "";
}

function guideToPlace(p, sub) {
  if (p?.map) guideToSpot(p.map, p.x, p.y, p.name, sub);
}


const KIND_TABS = [["dungeon", word("page.journal.browse.dungeons")], ["raid", word("page.journal.browse.raids")],
  ["battleground", word("page.journal.browse.battlegrounds")]];
const kindKey = ([k, label]) => `<button class="key small" data-kind="${k}" aria-pressed="${jr.kind === k}">${label}</button>`;

function sourcesHtml() {
  const cols = KIND_TABS.length, col = KIND_TABS.findIndex(([k]) => k === jr.kind);
  const line = GEAR_KINDS.includes(jr.kind)
    ? `<svg viewBox="0 0 ${cols * 2} 2" preserveAspectRatio="none" aria-hidden="true"><path d="M${col * 2 + 1} 0V1H${cols}V2" vector-effect="non-scaling-stroke"/></svg>`
    : "";
  return `<div class="j-sources" style="--cols:${cols}">
      ${KIND_TABS.map(kindKey).join("")}
      <span class="j-flow"${line ? ` data-from="${jr.kind}"` : ""}>${line}</span>
      <button class="key small g-open" data-gear="1" title="${word("page.journal.browse.upgrades.tip")}">${word("page.journal.browse.upgrades")}</button></div>`;
}

const cardSrc = (d) => pictureSrc(`/card/${d.key}.jpg`, d.cardPicture);

function homeHtml() {
  const cards = dungeon.list.filter((d) => d.kind === jr.kind).map((d) => {
    const [fitText, fitClass] = fit(d);
    const quests = d.quests.filter((q) => questFits(q)).length;
    const stars = d.loot.filter(isWished).length;
    const when = whenText(d), size = playersText(d), note = levelsNote(d);
    const count = [quests ? wordCount("page.journal.browse.quests", quests) : "", size].filter(Boolean).join(", ");
    return `<button class="j-card${d.coming || d.notOpen ? " coming" : ""}" data-open="${d.key}"${d.card ? ` style="background-image:url('${cardSrc(d)}')"` : ""}>
      <span class="j-card-name">${esc(d.name)}</span>${when ? `<span class="j-card-when">${esc(when)}</span>` : ""}
      <span class="j-card-count">${esc(count)}${stars ? ` <b>${word("page.journal.browse.starred", { n: stars })}</b>` : ""}</span>
      <span class="j-card-foot"><span${note ? ` title="${esc(levelsText(d))}: ${esc(note)}"` : ""}>${[levelsText(d), d.coming ? d.zone : ""].filter(Boolean).map(esc).join(", ")}${d.xpRun ? ` <small>${word("page.journal.dungeon.xp", { xp: num(d.xpRun) })}</small>` : ""}</span>
        <span class="fit ${fitClass}">${fitText}</span></span>
    </button>`;
  }).join("");
  const [, title] = KIND_TABS.find(([k]) => k === jr.kind) || KIND_TABS[0];
  const pick = { dungeon: word("page.journal.browse.pick.dungeon"), raid: word("page.journal.browse.pick.raid"),
    battleground: word("page.journal.browse.pick.battleground") };
  const none = { dungeon: word("page.journal.browse.none.dungeon"), raid: word("page.journal.browse.none.raid"),
    battleground: word("page.journal.browse.none.battleground") };
  return `<div class="j-top"><div><h2>${word("page.journal.browse.title", { kind: title })}</h2>
      <p class="muted">${pick[jr.kind] || pick.dungeon}</p></div>
    ${sourcesHtml()}</div>
    <div class="j-cards">${cards || `<p class="muted">${askNote("dungeons", { have: dungeon.list.length > 0, none: none[jr.kind] || none.dungeon,
      what: word("page.journal.browse.asked"), again: () => { loadDungeons(app.state?.level || 0); renderJournal(); } })}</p>`}</div>`;
}

function bossesHtml(d) {
  const kills = new Set(runKills(d.key));
  const list = d.bosses.map((b, i) => ({ b, i }));
  if (d.trash?.length) {
    list.push({ b: { name: word("page.journal.bosses.trash"), loot: d.trash, note: word("page.journal.bosses.trash.note") }, i: -1 });
  }
  if (jr.pick && (jr.pick.boss || jr.pick.trash)) {
    const n = jr.pick.trash ? list.length - 1 : list.findIndex(({ b }) => b.name === jr.pick.boss);
    if (n >= 0) jr.boss = n;
    jr.pick = null;
  }
  jr.boss = Math.min(jr.boss, list.length - 1);
  const bossMob = (b) => ({ id: b.npc, name: b.name, where: "dungeons" });
  const under = (b, i) => [i >= 0 ? mobLevelHtml(b.levels, bossMob(b)) : "", b.rare ? word("page.journal.bosses.rare") : esc(b.sub || "")].filter(Boolean).join(", ");
  const rows = list.map(({ b, i }, n) => `<button class="j-row${n === jr.boss ? " on" : ""}" data-boss="${n}">
      <span class="j-num">${i >= 0 ? i + 1 : ""}</span><span class="j-row-text">${esc(b.name)}<small>${under(b, i)}</small></span>
      ${kills.has(i + 1) ? `<span class="j-tag green">${word("page.journal.bosses.down")}</span>` : ""}${b.loot.some(isWished) ? `<span class="j-tag gold">★</span>` : ""}</button>`).join("");
  const { b, i } = list[jr.boss] || {};
  if (!b) return `<p class="muted">${word("page.journal.bosses.none")}</p>`;
  const facts = [i >= 0 ? mobLevelHtml(b.levels, bossMob(b)) : "", b.rare ? word("page.journal.bosses.rare-spawn") : "", esc(b.sub || "")].filter(Boolean);
  const detail = `<h3 class="j-title">${esc(b.name)}</h3>
    ${facts.length ? `<p class="muted">${facts.join(", ")}</p>` : ""}
    ${b.note ? `<p>${esc(b.note)}</p>` : ""}
    <div class="j-label">${word("page.journal.bosses.loot")} <span>${wordCount("page.journal.bosses.loot.count", b.loot.length)}</span></div>
    ${b.loot.map((id) => itemRow(id, d)).join("") || `<p class="muted">${word("page.journal.bosses.loot.none")}</p>`}`;
  return `<div class="j-split"><div class="j-list"><div class="j-label">${word("page.journal.bosses.title")} <span>${d.bosses.length}</span></div>${rows}</div>
    <div class="j-detail">${detail}</div></div>`;
}

function questsHtml(d) {
  jr.side ||= faction();
  if (jr.pick?.quest) {
    const q = d.quests.find((x) => x.name === jr.pick.quest);
    if (q && !questFits(q, jr.side)) jr.side = q.side === "Both" ? faction() : q.side;
  }
  const list = d.quests.filter((q) => questFits(q, jr.side));
  if (jr.pick?.quest) {
    const n = list.findIndex((q) => q.name === jr.pick.quest);
    if (n >= 0) jr.quest = n;
    jr.pick = null;
  }
  jr.quest = Math.min(jr.quest, Math.max(0, list.length - 1));
  const rows = list.map((q, n) => {
    const [tag, cls] = questState(q, d);
    return `<button class="j-row${n === jr.quest ? " on" : ""}${tag === "DONE" ? " done" : ""}" data-quest="${n}">
      <span class="j-bang">!</span><span class="j-row-text">${esc(q.name)}<small>${word("page.journal.quests.available", { req: q.req || 1 })}</small></span>
      ${tag ? `<span class="j-tag ${cls}">${tag}</span>` : ""}</button>`;
  }).join("");
  const q = list[jr.quest];
  let detail = `<p class="muted">${esc(word("page.journal.quests.none", { side: jr.side, dungeon: d.name }))}</p>`;
  if (q) {
    const start = (q.start || [])[0], end = (q.end || [])[0];
    const rw = q.rewards || {};
    const party = (app.group?.key === d.key ? app.group.members : []);
    const idx = d.quests.indexOf(q);
    const on = party.filter((m) => m.quests.includes(idx)).map((m) => m.name), off = party.filter((m) => !m.quests.includes(idx)).map((m) => m.name);
    const extras = [rw.xp ? word("page.journal.quests.xp", { xp: num(rw.xp) }) : "", rw.money ? money(rw.money) : "",
      ...(rw.rep || []).map(([f, v]) => `${esc(f)} ${v > 0 ? "+" : ""}${v}`), !rw.xp && rw.summary ? esc(rw.summary) : ""].filter(Boolean);
    const unknown = word("page.journal.quests.unknown");
    detail = `<h3 class="j-title">${esc(q.name)}</h3>
      <p class="muted">${esc(q.side !== "Both" ? word("page.journal.quests.levels.side", { level: q.level, req: q.req || 1, side: q.side })
        : word("page.journal.quests.levels", { level: q.level, req: q.req || 1 }))}</p>
      ${q.objective ? `<div class="j-label">${word("page.journal.quests.objective")}</div><p>${esc(q.objective)}</p>` : ""}
      <div class="j-label">${word("page.journal.quests.starts")}</div><p>${esc(q.pickup || place(start) || unknown)}</p>
      ${placeKey(start, "start", idx, word("page.journal.quests.guide.start.tip"))}
      <div class="j-label">${word("page.journal.quests.turn-in")}</div><p>${esc(q.turnin || place(end) || unknown)}</p>
      ${placeKey(end, "end", idx, word("page.journal.quests.guide.end.tip"))}
      ${q.note ? `<div class="j-label">${word("page.journal.quests.notes")}</div><p>${esc(q.note)}</p>` : ""}
      ${party.length ? `<div class="j-label">${word("page.journal.quests.party")}</div><p>${on.length ? esc(word("page.journal.quests.party.have", { names: on.join(", ") }))
        : word("page.journal.quests.party.nobody")}${off.length ? `<br><span class="muted">${esc(word("page.journal.quests.party.without", { names: off.join(", ") }))}</span>` : ""}</p>` : ""}
      ${rw.choice?.length ? `<div class="j-label">${word("page.journal.quests.choose")}</div>${rw.choice.map((id) => itemRow(id, d)).join("")}` : ""}
      ${rw.items?.length ? `<div class="j-label">${word("page.journal.quests.also")}</div>${rw.items.map((id) => itemRow(id, d)).join("")}` : ""}
      ${extras.length ? `<p class="j-extras">${extras.join("&nbsp;&nbsp; ")}</p>` : ""}`;
  }
  const sides = ["Alliance", "Horde"].map((s) => `<button class="j-side${jr.side === s ? " on" : ""}" data-side="${s}" title="${word("page.journal.quests.side.tip", { side: s })}">
    <img src="/icon/${s === "Alliance" ? "inv_bannerpvp_02" : "inv_bannerpvp_01"}.jpg" alt="${s}"></button>`).join("");
  const running = app.tracks?.epic?.key === d.key;
  const level = app.state?.level || 0, from = d.epicFrom?.[app.status?.strs?.faction || jr.side];
  const early = !running && from && level && level < from;
  const epic = list.length ? `<div class="j-epic"><button class="key small" data-epic="1"${early ? " disabled" : ""} title="${word("page.journal.quests.epic.tip")}">${
    early ? word("page.journal.quests.epic.early", { from }) : running ? word("page.journal.quests.epic.restart") : word("page.journal.quests.epic.start")}</button>
    <small>${early ? word("page.journal.quests.epic.early.note", { from, level })
      : running ? word("page.journal.quests.epic.running.note") : word("page.journal.quests.epic.start.note")}</small></div>` : "";
  return `${epic}<div class="j-split"><div class="j-list"><div class="j-label">${word("page.journal.quests.title")} <span>${list.length}</span><span class="j-sides">${sides}</span></div>${rows}</div>
    <div class="j-detail">${detail}</div></div>`;
}

function runHtmlFor(d) {
  const r = app.run?.key === d.key || runKills(d.key).length ? app.run : null;
  const W = (key, fill) => word(key, fill);
  let now = `<p class="muted">${esc(word("page.journal.run.none", { dungeon: d.name }))}</p>`;
  if (r) {
    const kills = runKills(d.key);
    const bosses = d.bosses.map((b, i) => `<div class="j-run-boss${kills.includes(i + 1) ? " down" : ""}">${kills.includes(i + 1) ? word("page.journal.run.down") : "&ndash;"} <span>${esc(b.name)}</span> <small>${mobLevelHtml(b.levels)}</small></div>`).join("");
    now = `<h3 class="j-title">${r.inside ? word("page.journal.run.inside") : r.open ? word("page.journal.run.paused") : word("page.journal.run.last")}</h3>
      <table class="facts"><tr><th>${word("page.journal.run.time")}</th><td>${hms(r.seconds)}</td></tr>
        <tr><th>${word("page.journal.run.bosses")}</th><td>${word("page.journal.run.bosses.count", { kills: kills.length, total: d.bosses.length })}</td></tr>
        <tr><th>${word("page.journal.run.deaths")}</th><td>${r.deaths}</td></tr>
        <tr><th>${word("page.journal.run.xp")}</th><td>${num(r.xp)}</td></tr><tr><th>${word("page.journal.run.gold")}</th><td>${money(r.money)}</td></tr></table>
      <div class="j-label">${word("page.journal.run.bosses")}</div>${bosses}
      ${r.loot.length ? `<div class="j-label">${word("page.journal.run.loot")}</div>${r.loot.map((id) => itemRow(id, d)).join("")}` : ""}`;
  }
  const past = (jr.runs?.runs || []).filter((x) => x.key === d.key).slice(0, 8).map((x) =>
    `<tr><td>${new Date(x.ended * 1000).toLocaleString([], { month: "short", day: "numeric", hour: "2-digit", minute: "2-digit" })}</td>
     <td class="num">${hms(x.seconds)}</td><td class="num">${x.kills}/${x.bosses}</td><td class="num">${num(x.xp)}</td><td class="num">${x.deaths}</td></tr>`).join("");
  const cap = app.cap || [];
  return `<div class="j-single">${now}
    <div class="j-label">${word("page.journal.run.cap")} <span>${word("page.journal.run.cap.count", { n: cap.length })}</span></div>
    <p class="${cap.length >= 4 ? "warn-text" : "muted"}">${cap.length ? word("page.journal.run.cap.frees", { min: Math.max(1, 60 - Math.max(...cap)) }) : word("page.journal.run.cap.none")}</p>
    ${past ? `<div class="j-label">${word("page.journal.run.earlier")}</div><table class="list"><tr><th>${word("page.journal.run.earlier.ended")}</th><th class="num">${word("page.journal.run.time")}</th><th class="num">${
      word("page.journal.run.bosses")}</th><th class="num">${word("page.journal.run.earlier.xp")}</th><th class="num">${word("page.journal.run.deaths")}</th></tr>${past}</table>`
      : jr.runs ? "" : `<div class="j-label">${word("page.journal.run.earlier")}</div><p class="muted">${askNote("/api/runs", { what: word("page.journal.run.asked"),
        again: () => { loadRuns(); renderJournal(); } })}</p>`}</div>`;
}

function mapHtml(d) {
  const floors = d.floors.map((id) => d.floorInfo[id]).filter(Boolean);
  if (!floors.length) return `<p class="muted">${esc(word("page.journal.map.none", { dungeon: d.name }))}</p>`;
  jr.floor = Math.min(jr.floor, floors.length - 1);
  const f = floors[jr.floor], id = d.floors[jr.floor];
  const tabs = floors.length > 1 ? `<div class="j-tabs">${floors.map((x, i) => `<button class="key small" data-floor-tab="${i}" aria-pressed="${i === jr.floor}">${esc(x.name)}</button>`).join("")}</div>` : "";
  const mini = f.tilesOnly ? floorPicture(f) : null;
  if (f.tilesOnly && !mini) return `<div class="j-single">${tabs}<p class="muted">${esc(word("page.journal.map.floor-none", { floor: f.name }))}</p></div>`;
  const pins = d.bosses.map((b, i) => {
    const at = b.pos && onFloor(id, b.pos, d.floors, mini?.world);
    return at ? `<button class="j-pin${b.rare ? " rare" : ""}" style="left:${at[0] * 100}%;top:${at[1] * 100}%" data-pin-boss="${i}"
      aria-label="${esc(b.name)}"><span>${i + 1}</span></button>` : "";
  }).join("");
  const src = mini ? mini.src : worldMapSrc(id);
  return `<div class="j-single j-floor">${tabs}<div class="j-floor-pic"><div class="j-map"><img src="${esc(src)}" alt="${esc(f.name)}">${pins}<div class="poi-tip j-pin-tip" hidden></div></div></div></div>`;
}

function wayInHtml(d) {
  const e = d.entrances?.[0];
  const pin = e?.walked ? word("page.journal.dungeon.pin.walked") : e?.described ? word("page.journal.dungeon.pin.described") : "";
  const way = d.wayIn ? esc(word("page.journal.dungeon.way-in", { way: d.wayIn })) : "";
  return way || pin ? `<p class="muted">${[way, pin].filter(Boolean).join(" ")}</p>` : "";
}

function clearXpText(d) {
  const xp = dungeon.byKey[d.key]?.xpRun;
  if (xp == null) return ` | <span class="muted">${word("page.journal.dungeon.xp.unknown")}</span>`;
  return xp > 0 ? ` | ${word("page.journal.dungeon.xp", { xp: num(xp) })}` : ` | <span class="muted">${word("page.journal.dungeon.xp.none")}</span>`;
}

function dungeonHtml(d) {
  const [fitText, fitClass] = fit(d);
  const note = levelsNote(d), when = whenText(d), size = playersText(d);
  const tabs = [["bosses", word("page.journal.dungeon.tab.bosses")], ["quests", word("page.journal.dungeon.tab.quests")],
    ["run", word("page.journal.dungeon.tab.run")], ["map", word("page.journal.dungeon.tab.map")]].map(([k, label]) =>
    `<button class="key small" data-tab="${k}" aria-pressed="${jr.tab === k}">${label}</button>`).join("");
  const body = jr.tab === "quests" ? questsHtml(d) : jr.tab === "run" ? runHtmlFor(d) : jr.tab === "map" ? mapHtml(d) : bossesHtml(d);
  const inThis = app.dungeon?.key === d.key ? " disabled" : "";
  return `<div class="j-head" style="background-image:linear-gradient(90deg, ${tint("page", 0.95)} 30%, ${tint("page", 0.55)}), url('${cardSrc(d)}')">
      <div><h2>${esc(d.name)}</h2>
        <p>${levelsText(d)}${note ? ` (${esc(note)})` : ""}${d.location ? ` | ${esc(d.location)}` : d.zone && d.zone !== d.name ? ` | ${esc(d.zone)}` : ""}${size ? ` | ${esc(size)}` : ""}
          ${fitText ? ` | <span class="fit ${fitClass}">${fitText}</span>` : ""}${when ? ` | <b class="j-when">${esc(when)}</b>` : ""}${clearXpText(d)}</p>
        ${d.description ? `<p class="muted">${esc(d.description)}</p>` : ""}${wayInHtml(d)}</div>
      <div class="j-head-keys"><div class="j-tabs">${tabs}</div>
        ${d.entrances?.length ? (d.portals?.length
          ? `<button class="key small" data-go-entrance="1"${inThis} title="${word("page.journal.dungeon.to-portal.tip")}">${word("page.journal.dungeon.to-portal")}</button>`
          : `<button class="key small" data-go-entrance="1"${inThis} title="${word("page.journal.dungeon.to-entrance.tip")}">${word("page.journal.dungeon.to-entrance")}</button>`) : ""}</div>
    </div>${body}`;
}

function comingHtml(d) {
  const [fitText, fitClass] = fit(d), note = levelsNote(d), when = whenText(d);
  const facts = [levelsText(d) && `${esc(levelsText(d))}${note ? ` (${esc(note)})` : ""}`, esc(d.zone || ""), esc(playersText(d)),
    fitText && `<span class="fit ${fitClass}">${fitText}</span>`].filter(Boolean);
  return `<div class="j-head"><div><h2>${esc(d.name)}</h2><p>${facts.join(" | ")}</p>
      ${d.where ? `<p class="muted">${esc(d.where)}</p>` : ""}</div></div>
    <div class="j-single"><p>${esc(when && when !== word("page.journal.dungeon.when.coming")
      ? word("page.journal.dungeon.coming.when", { when, coming: word("page.journal.dungeon.coming") }) : word("page.journal.dungeon.coming"))}</p></div>`;
}

const yourSide = (list) => (list || []).filter((e) => !e.side || e.side === faction());

function battlegroundHtml(d) {
  const [fitText, fitClass] = fit(d), lvl = app.state?.level || 0;
  const doors = yourSide(d.entrances), masters = yourSide(d.battlemasters);
  const brackets = (d.brackets || []).map(([lo, hi]) => {
    const text = lo === hi ? `${lo}` : `${lo}-${hi}`;
    return lvl >= lo && lvl <= hi ? `<b>${text}</b>` : text;
  }).join(", ");
  const rows = masters.map((m, i) => `<div class="j-row"><span class="j-row-text">${esc(m.name)}<small>${esc(app.maps[m.map]?.name || "")}</small></span>
      <button class="key small" data-go-master="${i}" title="${word("page.journal.battleground.master.tip")}">${word("page.journal.quests.guide")}</button></div>`).join("");
  return `<div class="j-head"><div><h2>${esc(d.name)}</h2>
      <p>${[levelsText(d), playersText(d)].filter(Boolean).map(esc).join(" | ")}${fitText ? ` | <span class="fit ${fitClass}">${fitText}</span>` : ""}</p></div>
      <div class="j-head-keys">${doors.length ? `<button class="key small" data-go-entrance="1" title="${word("page.journal.battleground.to-entrance.tip")}">${word("page.journal.dungeon.to-entrance")}</button>` : ""}</div></div>
    <div class="j-single">${brackets ? `<div class="j-label">${word("page.journal.battleground.brackets")}</div><p>${brackets}</p>` : ""}
      <div class="j-label">${word("page.journal.battleground.masters")} <span>${masters.length}</span></div>
      ${doors.length || masters.length ? rows || `<p class="muted">${word("page.journal.battleground.none.side")}</p>`
    : `<p class="muted">${word("page.journal.battleground.none")}</p>`}</div>`;
}

function renderJournal() {
  if (!jr.open) return;
  saveJournal();
  const box = $("journal");
  let html;
  if (!jr.key) html = homeHtml();
  else if (jr.key === "@gear") html = gearHtml();
  else {
    const d = dungeonDetail(jr.key);
    html = !d ? `<p class="muted">${askNote(`/api/dungeon/${jr.key}`, { what: dungeon.byKey[jr.key]?.name || word("page.journal.dungeon.asked"), again: detailAgain(jr.key) })}</p>`
      : d.coming ? comingHtml(d) : d.kind === "battleground" ? battlegroundHtml(d) : dungeonHtml(d);
  }
  html = `<div class="j-bar"><span class="j-bar-keys"><button class="key small" data-back="1"${jr.history.length ? "" : " hidden"} title="${word("page.journal.window.back.tip")}">${word("page.journal.window.back")}</button>
    <button class="key small" data-home="1"${jr.key ? "" : " hidden"}>${word("page.journal.window.home")}</button></span>
    <span class="j-bar-title">${word("page.journal.window.title")}</span><span class="j-bar-end">${helpButton("journal")}<button class="key small square x-mark" data-close="1" title="${word("page.journal.window.close.tip")}">&times;</button></span></div>
    <div class="j-body">${html}</div>`;
  const scroller = box.querySelector(".j-detail, .j-single"), scroll = scroller?.scrollTop || 0;
  const listScroll = box.querySelector(".j-list")?.scrollTop || 0;
  if (!setHtml(box, html)) return;
  const again = box.querySelector(".j-detail, .j-single");
  if (again) again.scrollTop = scroll;
  const list = box.querySelector(".j-list");
  if (list) list.scrollTop = listScroll;
  placeJournal(box);
}


function guideToSpot(mapId, x, y, name, sub, dungeonKey, opts = {}) {
  const w = app.maps[mapId]?.world;
  if (!w) { showToast(word("page.journal.guide.no-map")); return opts.then?.(); }
  const at = toWorld(w, x / 100, y / 100);
  guideTo({ todoId: null, name, sub, cat: "dungeon", zone: app.maps[mapId].name, instance: app.maps[mapId].instance, dungeonKey,
    wx: at.n, wy: at.w, again: opts.again }, opts);
}

function journalClicked(e) {
  const b = e.target.closest("button");
  if (!b) return;
  const d = jr.key && dungeonDetail(jr.key);
  if (b.dataset.close) return closeJournal();
  if (b.dataset.back) return goBack();
  if (b.dataset.home) { pushView(); jr.key = null; return renderJournal(); }
  if (b.dataset.kind) { jr.kind = b.dataset.kind; saveJournal(); return renderJournal(); }
  if (b.dataset.open) { pushView(); jr.tab = "bosses"; return openJournal(b.dataset.open); }
  if (b.dataset.pinBoss) { pushView(); jr.tab = "bosses"; jr.boss = +b.dataset.pinBoss; saveJournal(); return renderJournal(); }
  if (b.dataset.tab) { jr.tab = b.dataset.tab; saveJournal(); if (jr.tab === "run") loadRuns(); return renderJournal(); }
  if (b.dataset.boss) { jr.boss = +b.dataset.boss; return renderJournal(); }
  if (b.dataset.quest) { jr.quest = +b.dataset.quest; return renderJournal(); }
  if (b.dataset.side) { jr.side = b.dataset.side; jr.quest = 0; return renderJournal(); }
  if (b.dataset.floorTab) { jr.floor = +b.dataset.floorTab; return renderJournal(); }
  if (b.dataset.star) return toggleWish(+b.dataset.star);
  if (b.dataset.goStart && d) {
    const q = d.quests[+b.dataset.goStart];
    if (q) guideToPlace(q.start?.[0], word("page.journal.quests.guide.start", { quest: q.name }));
    return;
  }
  if (b.dataset.goEnd && d) {
    const q = d.quests[+b.dataset.goEnd];
    if (q) guideToPlace(q.end?.[0], word("page.journal.quests.guide.end", { quest: q.name }));
    return;
  }
  if (b.dataset.goEntrance && d && !b.disabled) guideToEntrance(d);
  if (b.dataset.goMaster && d) {
    const m = yourSide(d.battlemasters)[+b.dataset.goMaster];
    if (m) guideToSpot(m.map, m.x, m.y, m.name, word("page.journal.battleground.master.guide", { name: d.name }));
  }
  if (b.dataset.epic && !b.disabled && d) { startEpic(d); renderJournal(); }
}
$("journal").addEventListener("click", journalClicked);

const PORTAL_FROM_ENTRANCE = 1000;
function guideToEntrance(d, opts = {}) {
  const s = app.state, inst = app.maps[s?.realMap || s?.map]?.instance;
  const doors = yourSide(d.entrances).filter((e2) => app.maps[e2.map]?.instance === inst);
  const here = s?.pos && app.maps[s.map]?.world;
  const world = (e2) => {
    const at = toWorld(app.maps[e2.map].world, e2.x / 100, e2.y / 100);
    return [at.n, at.w];
  };
  const dist = (e2) => {
    if (!here) return 0;
    const me = toWorld(here, s.pos.x, s.pos.y), [wx, wy] = world(e2);
    return Math.hypot(wx - me.n, wy - me.w);
  };
  const best = doors.sort((a, c) => dist(a) - dist(c))[0];
  if (!best) { showToast(word("page.journal.guide.far", { dungeon: d.name })); return opts.then?.(); }
  const [ex, ey] = world(best), far = (p) => Math.hypot(p.n - ex, p.w - ey);
  const portal = (d.portals || []).filter((p) => p.inst === inst && far(p) <= PORTAL_FROM_ENTRANCE).sort((a, c) => far(a) - far(c))[0];
  const again = (o) => guideToEntrance(d, o);
  if (!portal) {
    return guideToSpot(best.map, best.x, best.y, word("page.journal.guide.entrance", { dungeon: d.name }), word("page.journal.guide.entrance.sub"),
      d.key, { ...opts, again });
  }
  guideTo({ todoId: null, name: word("page.journal.guide.portal", { dungeon: d.name }),
            sub: portal.underground ? word("page.journal.guide.portal.sub.underground") : word("page.journal.guide.portal.sub"), cat: "dungeon",
            zone: app.maps[best.map].name, instance: inst, dungeonKey: d.key, wx: portal.walk[0], wy: portal.walk[1], wz: portal.walk[2],
            again }, opts);
}

function guideToDungeon(key, name, opts = {}) {
  if (dungeon.detail[key]) return guideToEntrance(dungeon.detail[key], opts);
  getJson(`/api/dungeon/${key}`, { share: true })?.then((d) => {
    dungeon.detail[key] ??= normalDetail(d);
    guideToEntrance(dungeon.detail[key], opts);
  }, (e) => askFailed(word("page.journal.guide.failed", { dungeon: name }), e));
}

const pinTipHtml = (b) => `<b>${esc(b.name)}</b><small>${[mobLevelHtml(b.levels), ...[b.sub, b.rare ? word("page.journal.bosses.rare.small") : ""].filter(Boolean).map(esc)].join(", ")}</small><br><small>${word("page.journal.bosses.pin.click")}</small>`;

$("journal").addEventListener("mouseover", (e) => {
  const pin = e.target.closest(".j-pin"), map = pin?.closest(".j-map"), tip = map?.querySelector(".j-pin-tip");
  if (!tip) return;
  const d = jr.key && dungeonDetail(jr.key), b = d?.bosses[+pin.dataset.pinBoss];
  if (!b) return;
  tip.innerHTML = pinTipHtml(b);
  tip.hidden = false;
  const m = map.getBoundingClientRect(), p = pin.getBoundingClientRect();
  const at = tipPlace({ left: p.left - m.left, right: p.right - m.left, top: p.top - m.top - 4, bottom: p.bottom - m.top },
    tip.offsetWidth, tip.offsetHeight, { left: 0, top: 0, right: m.width, bottom: m.height }, { gap: 6, y: "level" });
  tip.style.left = `${at.x}px`;
  tip.style.top = `${at.y}px`;
});
$("journal").addEventListener("mouseout", (e) => {
  const pin = e.target.closest(".j-pin");
  if (pin && !pin.contains(e.relatedTarget)) pin.closest(".j-map")?.querySelector(".j-pin-tip")?.setAttribute("hidden", "");
});

$("journal").addEventListener("scroll", journalScrolled, true);
for (const type of ["wheel", "pointerdown", "keydown"]) $("journal").addEventListener(type, journalTouched, { capture: true, passive: true });
$("btn-journal").addEventListener("click", () => toggleJournal());
hotkey(["j"], () => toggleJournal());
closable(LAYER.journal, () => jr.open, () => closeJournal());

on("start", () => setInterval(() => { if (jr.open) renderJournal(); }, 1000));
on("start", () => { if (jr.reopen) showJournal(); });
