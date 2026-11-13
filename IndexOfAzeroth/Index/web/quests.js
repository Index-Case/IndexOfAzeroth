// The Index of Azeroth. Copyright 2026 Index Case <indexofazeroth@pm.me>. PolyForm Strict 1.0.0, see LICENSE.md.
"use strict";

const questMenu = $("quest-menu"), questList = $("quest-list"), questButton = $("btn-quests");
const questsUi = { view: "log", zones: null, zonesAt: 0, zonesFor: "", picked: new Set(), pickedFor: null, logAt: undefined,
  find: "",
  texts: {}, textsAsked: new Set(), textsAt: 0, textsFor: null, textOpen: null };
const ZONES_FRESH = 60000;
const questsKept = keptOr("cc.questsView", {});
if (questsKept.view === "zones") questsUi.view = "zones";
if (typeof questsKept.find === "string") questsUi.find = questsKept.find;
const keepQuestsView = () => keepIn("cc.questsView", { view: questsUi.view, find: questsUi.find });

const pickKey = () => charStore("questPick", app.character);
function loadPicks() {
  if (questsUi.pickedFor === pickKey()) return;
  questsUi.pickedFor = pickKey();
  try { questsUi.picked = new Set(JSON.parse(localStorage.getItem(pickKey()) || "[]")); } catch (e) { questsUi.picked = new Set(); }
}
function savePicks() {
  try { localStorage.setItem(pickKey(), JSON.stringify([...questsUi.picked])); } catch (e) {   }
}

function questTier(level, me) {
  const d = level - me;
  if (d >= 5) return "red";
  if (d >= 3) return "orange";
  if (d >= -2) return "yellow";
  return level > grayLevel(me) ? "green" : "gray";
}
const QUEST_TINT = { red: "game-red", orange: "quest-orange", yellow: "quest-yellow", green: "quest-green", gray: "quality-poor" };
function questColor(level, me = app.state?.level) {
  if (!me || !level) return "var(--gold)";
  return tint(QUEST_TINT[questTier(level, me)]);
}

function mobLevelHtml(levels, mob) {
  if (!levels) return html`<span class="mob-level muted">${mobLevelText(levels, mob)}</span>`;
  const top = levels[1] ?? levels[0];
  return html`<span class="mob-level" style="color:${questColor(top === "??" ? Infinity : top)}">${mobLevelText(levels)}</span>`;
}

function questLog() {
  const q = app.questlog;
  return q && (!q.char || !app.character || q.char === app.character) ? q.entries : null;
}

function logHtml(log) {
  if (!log) return `<p class="menu-note">${word("page.quests.log.none")}</p>`;
  if (!log.some((e) => e.id)) return `<p class="menu-note">${word("page.quests.log.empty")}</p>`;
  return log.map((e) => {
    if (e.header != null) {
      return `<div class="ql-head">${esc(e.header)}${e.folded ? `<small>${word("page.quests.log.folded")}</small>` : ""}</div>`;
    }
    return questRow(e);
  }).join("");
}

const lineNamed = (line) => itemNamed(line.text, line.item, line.itemName);

function questRow(e) {
  const state = e.failed ? `<li class="failed">${word("page.quests.failed")}</li>` : e.complete ? `<li class="ready">${word("page.quests.ready")}</li>` : "";
  const objs = state || e.objectives.map((o) => `<li class="${o.finished ? "done" : ""}">${lineNamed(o)}</li>`).join("")
    || (e.text ? `<li>${lineNamed(e)}</li>` : "");
  const at = questSpot(e), box = `ql-pick-${e.id}`;
  const go = at ? (at.turnin ? word("page.quests.go.turnin") : word("page.quests.go.objectives")) : NO_QUEST_MARK;
  const open = questsUi.textOpen === e.id;
  return `<div class="ql-quest${open ? " open" : ""}" data-quest="${e.id}"><label class="ql-pick" for="${box}" data-hover="quest:${e.id}"><span class="ql-mark ${e.complete ? "ready" : e.failed ? "failed" : "open"}" aria-hidden="true">${e.complete ? "?" : "…"}</span>
      <span class="ql-body"><span class="ql-title" data-quest-text="${e.id}" role="button" aria-expanded="${open}" title="${open ? word("page.quests.text.hide") : word("page.quests.text.show")}" style="color:${questColor(e.level)}">[${e.level}${e.group ? "+" : ""}] ${esc(e.title)}</span>
      ${questsUi.texts[e.id]?.blurb ? `<span class="ql-blurb">${esc(questsUi.texts[e.id].blurb)}</span>` : ""}
      ${objs ? `<ul class="ql-obj">${objs}</ul>` : ""}</span></label>
    <button class="key small ql-go" data-quest-go="${e.id}"${at ? "" : " disabled"} title="${go}">${word("page.quests.go")}</button>
    <input type="checkbox" id="${box}" value="${e.id}"${questsUi.picked.has(e.id) ? " checked" : ""} title="${word("page.quests.pick.tip")}">${open ? questTextHtml(e.id) : ""}</div>`;
}


const TEXTS_FRESH = 60000;

function askQuestTexts(force) {
  const who = app.character || "";
  if (questsUi.textsFor !== who) {
    questsUi.texts = {};
    questsUi.textsAsked = new Set();
    questsUi.textsFor = who;
  }
  if (force && Date.now() - questsUi.textsAt >= TEXTS_FRESH) questsUi.textsAsked = new Set();
  const ids = (questLog() || []).filter((e) => e.id && !questsUi.textsAsked.has(e.id)).map((e) => e.id);
  if (!ids.length) return;
  const asked = getJson(`/api/questtext?ids=${ids.join(",")}`);
  if (!asked) return;
  for (const id of ids) questsUi.textsAsked.add(id);
  questsUi.textsAt = Date.now();
  asked.then((d) => {
    if (questsUi.textsFor !== who) return;
    for (const id of ids) questsUi.texts[id] = d?.[id] || null;
    if (!questMenu.hidden && questsUi.view === "log") buildQuestMenu();
  }, () => {
    for (const id of ids) questsUi.textsAsked.delete(id);
    if (!questMenu.hidden && questsUi.view === "log") buildQuestMenu();
  });
}

function questTextHtml(id) {
  if (!(id in questsUi.texts)) {
    return `<div class="ql-text"><p class="ql-src">${questsUi.textsAsked.has(id) ? word("page.quests.text.asking") : word("page.quests.text.failed")}</p></div>`;
  }
  const t = questsUi.texts[id];
  if (!t?.todo && !t?.text) return `<div class="ql-text"><p class="ql-src">${word("page.quests.text.none")}</p></div>`;
  return `<div class="ql-text">${t.todo ? `<p class="ql-todo">${esc(t.todo)}</p>` : ""}${t.text ? `<p class="ql-words">${esc(t.text)}</p>` : ""}
    <p class="ql-src">${t.game ? word("page.quests.text.game") : word("page.quests.text.ours")}</p></div>`;
}

function toggleQuestText(id) {
  questsUi.textOpen = questsUi.textOpen === id ? null : id;
  askQuestTexts();
  buildQuestMenu();
}


const QUESTS_ICON = "inv_scroll_08";
const NO_QUEST_MARK = word("page.quests.no-mark");

const questEntry = (id) => questLog()?.find((x) => x.id === id) || null;

function questSpot(e) {
  const p = e?.poi || e?.poiLearnt, at = p && fracToWorld(p.map, p.x, p.y);
  return at ? { ...at, turnin: !!e.complete, learnt: !e.poi } : null;
}

window.HOVERS = window.HOVERS || {};
const QUEST_TIP = [questTipSummary, questTipState, questTipWhere];
HOVERS["quest:"] = (pinned, name) => questTipHtml(+name.slice(6));
function questTipHtml(id) {
  const e = questEntry(id);
  return e ? `<div class="hv ql-tip">${QUEST_TIP.map((part) => part(e)).join("")}</div>` : "";
}
function questTipSummary(e) {
  const s = questsUi.texts[e.id]?.summary;
  return s ? `<div class="hv-row ql-sum">${esc(s)}</div>` : "";
}
function questTipState(e) {
  if (e.failed) return `<div class="hv-head">${word("page.quests.failed")}</div>`;
  if (e.complete) return `<div class="hv-head">${word("page.quests.ready")}</div>`;
  const objs = e.objectives.map((o) => `<div class="hv-row${o.finished ? " done" : ""}">${lineNamed(o)}</div>`).join("")
    || (e.text ? `<div class="hv-row">${lineNamed(e)}</div>` : `<div class="hv-note">${word("page.quests.tip.no-objectives")}</div>`);
  return `<div class="hv-head">${word("page.quests.tip.objectives")}</div>${objs}`;
}
function questTipWhere(e) {
  const at = questSpot(e), z = at && zoneAt(at.n, at.w, at.inst), zone = z && app.maps[z.id]?.name;
  if (!at) return `<div class="hv-foot">${NO_QUEST_MARK}</div>`;
  const where = zone ? (at.learnt ? word("page.quests.tip.zone.learnt", { zone }) : word("page.quests.tip.zone", { zone }))
    : at.learnt ? word("page.quests.tip.map.learnt") : word("page.quests.tip.map");
  return `<div class="hv-foot">${esc(where)}</div>`;
}

let questHover = null;
function hoverQuest(id) {
  if (id === questHover) return;
  questHover = id;
  redraw();
}
function questMenuHovered(e) {
  const row = e.target.closest?.(".ql-quest");
  hoverQuest(row ? +row.dataset.quest : null);
}
function questMenuLeft() { hoverQuest(null); }
questMenu.addEventListener("mouseover", questMenuHovered);
questMenu.addEventListener("mouseleave", questMenuLeft);
const QUEST_RING = 14;
function drawQuestRing(size, scale) {
  const e = questMenu.hidden || questHover == null ? null : questEntry(questHover), at = questSpot(e);
  const p = at && worldOnScreen(at.inst, at.n, at.w, size, scale);
  if (!p) return;
  const color = tint(e.complete ? "mark-gold" : e.failed ? "mark-failed" : "mark-open");
  if (offView(p[0], p[1])) { drawEdgeHint(p[0], p[1], "", color); return; }
  drawRingMarker(p[0], p[1], { r: QUEST_RING, edge: 2, fill: tint("black", 0.7), ring: color, width: 3, color, dy: 0.5,
    text: EPIC_GLYPH[at.turnin ? "turnin" : "objective"], font: `13px ${MARK_FONT}` });
}
function guideToQuest(id, opts = {}) {
  const e = questEntry(id), at = questSpot(e);
  if (!at) {
    showToast(e ? word("page.quests.no-mark.toast", { quest: e.title }) : word("page.quests.gone"));
    return opts.then?.();
  }
  if (!opts.auto) {
    hoverQuest(null);
    toggleQuestMenu(false);
  }
  guideTo({ todoId: null, name: e.title, sub: at.turnin ? word("page.quests.guide.turnin") : word("page.quests.guide.objectives"), cat: "gameguide", icon: QUESTS_ICON,
            zone: "", instance: at.inst, wx: at.n, wy: at.w, questId: id, turnin: at.turnin, again: (o) => guideToQuest(id, o) }, opts);
}

const TURNIN_MOVED = 10;
function followQuestGuide() {
  const g = app.guide;
  if (!g || g.questId == null || g !== shownGuide() || app.replanning.guide) return;
  const e = questEntry(g.questId), at = e?.complete ? questSpot(e) : null;
  if (!at || (g.turnin && at.inst === g.instance && Math.hypot(at.n - g.wx, at.w - g.wy) < TURNIN_MOVED)) return;
  replanGuide("guide", { auto: true });
}

function zoneFar(id, me) {
  const m = app.maps[id], w = m?.world;
  if (!w || !me) return Infinity;
  if (m.instance !== me.inst) return 1e7;
  return Math.hypot((w.top + w.bottom) / 2 - me.n, (w.left + w.right) / 2 - me.w);
}

const ZONE_COLOURS = ["gray", "green", "yellow", "orange", "red"];
const ZONE_COLOUR_WORDS = wordsOf("page.zoneepic.colours");
const zoneColours = new Set(keptOr("cc.zoneColours", ZONE_COLOURS));
function zoneLevels(me = app.state?.level) {
  if (!me || ZONE_COLOURS.every((c) => zoneColours.has(c))) return null;
  const ranges = [];
  for (let level = 1; ; level++) {
    const tier = questTier(level, me), last = ranges[ranges.length - 1];
    if (zoneColours.has(tier)) {
      if (last && last[1] === level - 1) last[1] = level;
      else ranges.push([level, level]);
    }
    if (tier === "red") {
      if (zoneColours.has(tier)) ranges[ranges.length - 1][1] = null;
      return ranges;
    }
  }
}
const zoneColoursNone = () => !zoneColours.size;
function zoneColoursHtml() {
  const colour = (c) => `<label class="ql-close" title="${esc(word("page.zoneepic.colour.tip"))}"><input type="checkbox"
    data-zone-colour="${c}"${zoneColours.has(c) ? " checked" : ""}> <span style="color:${tint(QUEST_TINT[c])}">${
    esc(ZONE_COLOUR_WORDS[c])}</span></label>`;
  return `<div class="qz-colours">${ZONE_COLOURS.map(colour).join("")}${helpButton("zones")}</div>${
    zoneColoursNone() ? `<p class="menu-note">${esc(word("page.zoneepic.none"))}</p>` : ""}`;
}
function zoneColourSwitched(box) {
  const which = box.dataset?.zoneColour;
  if (!which) return false;
  if (box.checked) zoneColours.add(which);
  else zoneColours.delete(which);
  keepIn("cc.zoneColours", [...zoneColours]);
  buildQuestMenu();
  return true;
}

function zonesHtml() {
  const list = questsUi.zones;
  const head = `<div class="qz-head"><button class="qz-back" data-view="log">${word("page.quests.zones.back")}</button><span>${
    word("page.quests.zone-epic")}</span></div>${zoneColoursHtml()}`;
  if (!list) {
    return `${head}<p class="menu-note">${askNote("/api/quests", { what: word("page.quests.zones.what"),
      again: () => { refreshQuestZones(true); buildQuestMenu(); } })}</p>`;
  }
  const me = playerWorld() || (app.state && app.maps[app.state.map]?.world ? { inst: app.maps[app.state.map].instance,
    n: (app.maps[app.state.map].world.top + app.maps[app.state.map].world.bottom) / 2,
    w: (app.maps[app.state.map].world.left + app.maps[app.state.map].world.right) / 2 } : null);
  const running = app.tracks?.epic?.key;
  const hereMark = (z) => (app.state && z.id === app.state.map ? `<span class="step-tag here qz-here">${word("page.quests.zones.here")}</span>` : "");
  const rows = list.filter((z) => matchesSearch(z.name, questsUi.find))
    .map((z) => ({ ...z, levels: app.maps[z.id]?.levels || null, far: zoneFar(z.id, me) }))
    .sort((a, b) => (!a.levels - !b.levels) || (a.levels?.[0] ?? 0) - (b.levels?.[0] ?? 0)
      || (a.levels?.[1] ?? 0) - (b.levels?.[1] ?? 0) || a.far - b.far || a.name.localeCompare(b.name))
    .map((z) => `<button class="qz-row${running === `zone:${z.id}` ? " on" : ""}" data-zone="${z.id}"${zoneColoursNone() ? " disabled" : ""}
        title="${zoneColoursNone() ? esc(word("page.zoneepic.none")) : zoneLevels() ? esc(word("page.zoneepic.row.tip", { zone: z.name }))
          : esc(word("page.quests.zones.tip", { zone: z.name }))}">
      <span class="qz-name">${esc(z.name)}</span>${z.levels ? `<span class="qz-range" style="color:${zoneThreat(z.levels)}">${esc(zoneRangeText(z.levels))}</span>` : ""}
      <span class="qz-count">${z.done ? word("page.quests.zones.done", { done: z.done, total: z.quests }) : wordCount("page.quests.zones.quests", z.quests)}${
        z.missing ? ` <span class="data-missing" title="${esc(wordCount("page.quests.zones.missing.tip", z.missing, { zone: z.name }))}">${
          word("page.quests.zones.missing", { n: z.missing })}</span>` : ""}${hereMark(z)}</span></button>`).join("");
  return `${head}<div class="qz-find">${searchBox("zone-find", word("page.quests.zones.find"), questsUi.find)}</div>
    <div class="qz-list">${rows || (list.length ? nothingMatches() : `<p class="menu-note">${word("page.quests.zones.none")}</p>`)}</div>`;
}

const CAMP_KEY = "camp:epic";
function campKey() {
  const opens = questsUi.campOpens, level = app.state?.level || 1;
  const shut = opens === null ? word("page.quests.camp.no-data") : opens > level ? word("page.quests.camp.opens", { level: opens }) : "";
  const on = app.tracks?.epic?.key === CAMP_KEY;
  return `<button class="ql-epickey${on ? " on" : ""}" data-camp-epic${shut ? " disabled" : ""} title="${esc(shut ||
    word("page.quests.camp.tip"))}"><img src="/icon/spell_fire_fire.jpg" alt="">${word("page.quests.camp")}</button>`;
}

function classChainNow(chains = questsUi.classChains, level = app.state?.level || 1) {
  return (chains || []).find((c) => c.lv <= level) || null;
}
function classKey() {
  const chains = questsUi.classChains || [], now = classChainNow(chains), next = chains[0];
  const cls = CLASS_ICONS[app.status?.classId];
  const on = now && app.tracks?.epic?.key === `class:${now.c}`;
  const shut = now ? "" : next ? word("page.quests.class.next", { level: next.lv }) : word("page.quests.class.none");
  const tip = !now ? shut : now.u ? word("page.quests.class.tip.teaches", { name: now.n, spells: now.u })
    : word("page.quests.class.tip", { name: now.n });
  return `<button class="ql-epickey${on ? " on" : ""}" data-class-epic="${now ? now.c : ""}"${shut ? " disabled" : ""} title="${esc(tip)}"><img src="/icon/${
    cls ? `classicon_${cls}` : "inv_misc_book_11"}.jpg" alt="">${word("page.quests.class")}</button>`;
}

function buildQuestMenu() {
  loadPicks();
  const log = questLog();
  const inLog = new Set((log || []).filter((e) => e.id).map((e) => e.id));
  const picked = [...questsUi.picked].filter((id) => inLog.has(id));
  const scroller = questMenu.querySelector(".ql-scroll, .qz-list");
  const scrolled = scroller?.scrollTop || 0;
  const written = setHtml(questList, questsUi.view === "zones" ? zonesHtml() : questsUi.view === "profs" ? profsViewHtml() : `
    <div class="ql-top"><button class="ql-epickey" data-view="zones" title="${word("page.quests.zone-epic.tip")}"><img src="/icon/inv_misc_map_01.jpg" alt="">${word("page.quests.zone-epic")}</button>
      <button class="ql-epickey" data-log-epic${picked.length ? "" : " disabled"}
        title="${picked.length ? word("page.quests.log-epic.tip") : word("page.quests.log-epic.none")}"><span class="ql-mark" aria-hidden="true">!</span>${word("page.quests.log-epic")}${picked.length ? ` (${picked.length})` : ""}</button>
      ${campKey()}
      ${classKey()}${helpButton("classquest")}
      <button class="ql-epickey" data-view="profs" title="${word("page.quests.profs.tip")}"><img src="/icon/trade_blacksmithing.jpg" alt="">${word("page.quests.profs")}</button>
      <label class="ql-close" title="${word("page.quests.close.tip")}"><input type="checkbox" data-prefer-close${preferClose() ? " checked" : ""}> ${word("page.quests.close")}</label></div>
    ${questMarkSwitches()}
    <div class="ql-scroll">${logHtml(log)}</div>`);
  const again = questMenu.querySelector(".ql-scroll, .qz-list");
  if (written && again && scroller?.className === again.className) again.scrollTop = scrolled;
}

function refreshQuestZones(force) {
  const who = app.character || "";
  if (!force && questsUi.zones && questsUi.zonesFor === who && Date.now() - questsUi.zonesAt < ZONES_FRESH) return;
  askFor("/api/quests", () => getJson("/api/quests", { key: null, accept: [409] }).then((d) => {
    if (d.waiting) throw Object.assign(new Error("waiting for the game"), { waiting: d.waiting });
    return d;
  }))?.then((d) => {
    questsUi.zones = d.zones || [];
    questsUi.campOpens = d.campOpens ?? null;
    questsUi.classChains = d.classChains || [];
    questsUi.zonesAt = Date.now();
    questsUi.zonesFor = who;
    if (!questMenu.hidden) buildQuestMenu();
  }, (e) => {
    if (e?.waiting) questsUi.zones = null;
    if (!questMenu.hidden && questsUi.view === "zones") buildQuestMenu();
  });
}

const toggleQuestMenu = dropdown(questButton, questMenu, "q", () => { hoverQuest(null); refreshQuestZones(); askQuestTexts(true); buildQuestMenu(); },
  { el: $("quest-bar"), title: word("page.quests.title"), help: "quests" });

function applyQuestLog() {
  if (!questsUi.zones && !questMenu.hidden && questsUi.view === "zones") refreshQuestZones();
  const at = app.questlog?.at ?? null;
  if (at === questsUi.logAt) return;
  questsUi.logAt = at;
  if (!questMenu.hidden && questsUi.view === "log") {
    askQuestTexts();
    buildQuestMenu();
  }
  followQuestGuide();
}

function questMenuClicked(e) {
  const title = e.target.closest("[data-quest-text]");
  if (title) {
    e.preventDefault?.();
    return toggleQuestText(+title.dataset.questText);
  }
  const go = e.target.closest("button[data-quest-go]");
  if (go) return go.disabled ? undefined : guideToQuest(+go.dataset.questGo);
  const view = e.target.closest("button[data-view]");
  if (view) {
    questsUi.view = view.dataset.view;
    keepQuestsView();
    if (questsUi.view === "zones") refreshQuestZones();
    if (questsUi.view === "profs") askProfEpics(true);
    return buildQuestMenu();
  }
  if (e.target.closest("button[data-find-all]")) return zoneSearched("");
  const zone = e.target.closest("button[data-zone]");
  if (zone) {
    if (zone.disabled) return;
    const z = questsUi.zones?.find((x) => x.id === +zone.dataset.zone);
    toggleQuestMenu(false);
    return startEpic({ key: `zone:${zone.dataset.zone}`, name: z?.name || word("page.quests.zones.zone"), questLevels: zoneLevels() });
  }
  const camp = e.target.closest("button[data-camp-epic]");
  if (camp) {
    if (camp.disabled) return;
    toggleQuestMenu(false);
    return startEpic({ key: CAMP_KEY, name: word("page.quests.camp"), label: word("page.quests.camp.label") });
  }
  const cq = e.target.closest("button[data-class-epic]");
  if (cq) {
    const c = (questsUi.classChains || []).find((x) => String(x.c) === cq.dataset.classEpic);
    if (cq.disabled || !c) return;
    toggleQuestMenu(false);
    return startEpic({ key: `class:${c.c}`, name: c.n, label: word("page.quests.class.label", { name: c.n }) });
  }
  const epic = e.target.closest("button[data-log-epic]");
  if (epic && !epic.disabled) {
    const inLog = new Set((questLog() || []).filter((x) => x.id).map((x) => x.id));
    const ids = [...questsUi.picked].filter((id) => inLog.has(id)).sort((a, b) => a - b);
    if (!ids.length) return;
    toggleQuestMenu(false);
    startEpic({ key: `log:${ids.join(".")}`, name: word("page.quests.log-epic.name"), label: word("page.quests.log-epic.label") });
  }
}
questMenu.addEventListener("click", questMenuClicked);
function questMenuChanged(e) {
  if (e.target.type !== "checkbox" || questMarksSwitched(e.target) || zoneColourSwitched(e.target)) return;
  if (e.target.matches("[data-prefer-close]")) {
    try { localStorage.setItem("cc.preferClose", e.target.checked ? "1" : "0"); } catch (err) {   }
    return;
  }
  const id = +e.target.value;
  if (!id) return;
  if (e.target.checked) questsUi.picked.add(id); else questsUi.picked.delete(id);
  savePicks();
  buildQuestMenu();
}
questMenu.addEventListener("change", questMenuChanged);
function zoneSearched(query) {
  questsUi.find = query;
  keepQuestsView();
  buildQuestMenu();
  const list = questMenu.querySelector(".qz-list");
  if (list) list.scrollTop = 0;
}
questMenu.addEventListener("input", (e) => { if (e.target.id === "zone-find") zoneSearched(e.target.value); });
