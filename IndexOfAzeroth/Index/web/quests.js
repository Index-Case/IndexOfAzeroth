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

function questColor(level, me = app.state?.level) {
  if (!me || !level) return "var(--gold)";
  const d = level - me;
  if (d >= 5) return tint("game-red");
  if (d >= 3) return tint("quest-orange");
  if (d >= -2) return tint("quest-yellow");
  return level > grayLevel(me) ? tint("quest-green") : tint("quality-poor");
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
  if (!log) return `<p class="menu-note">Your quest log shows here once the game sends it. Do a /reload in game after the addon updates.</p>`;
  if (!log.some((e) => e.id)) return `<p class="menu-note">Your quest log is empty.</p>`;
  return log.map((e) => {
    if (e.header != null) {
      return `<div class="ql-head">${esc(e.header)}${e.folded ? `<small>this header is collapsed in game, so its quests aren't listed</small>` : ""}</div>`;
    }
    return questRow(e);
  }).join("");
}

const lineNamed = (line) => itemNamed(line.text, line.item, line.itemName);

function questRow(e) {
  const state = e.failed ? `<li class="failed">Failed</li>` : e.complete ? `<li class="ready">Ready for turn-in</li>` : "";
  const objs = state || e.objectives.map((o) => `<li class="${o.finished ? "done" : ""}">${lineNamed(o)}</li>`).join("")
    || (e.text ? `<li>${lineNamed(e)}</li>` : "");
  const at = questSpot(e), box = `ql-pick-${e.id}`;
  const go = at ? `This starts the Navigation Guide to the quest's ${at.turnin ? "turn-in" : "objectives"} and copies the line for the in-game arrow` : NO_QUEST_MARK;
  const open = questsUi.textOpen === e.id;
  return `<div class="ql-quest${open ? " open" : ""}" data-quest="${e.id}"><label class="ql-pick" for="${box}" data-hover="quest:${e.id}"><span class="ql-mark ${e.complete ? "ready" : e.failed ? "failed" : "open"}" aria-hidden="true">${e.complete ? "?" : "…"}</span>
      <span class="ql-body"><span class="ql-title" data-quest-text="${e.id}" role="button" aria-expanded="${open}" title="${open ? "Hide the quest's text" : "Show the quest's text"}" style="color:${questColor(e.level)}">[${e.level}${e.group ? "+" : ""}] ${esc(e.title)}</span>
      ${questsUi.texts[e.id]?.blurb ? `<span class="ql-blurb">${esc(questsUi.texts[e.id].blurb)}</span>` : ""}
      ${objs ? `<ul class="ql-obj">${objs}</ul>` : ""}</span></label>
    <button class="key small ql-go" data-quest-go="${e.id}"${at ? "" : " disabled"} title="${go}">Guide me</button>
    <input type="checkbox" id="${box}" value="${e.id}"${questsUi.picked.has(e.id) ? " checked" : ""} title="Tick this box to put the quest in the quest epic">${open ? questTextHtml(e.id) : ""}</div>`;
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
    return `<div class="ql-text"><p class="ql-src">${questsUi.textsAsked.has(id) ? "The page is asking the Index for the quest's text" : "The quest's text didn't come, because the Index didn't answer"}</p></div>`;
  }
  const t = questsUi.texts[id];
  if (!t?.todo && !t?.text) return `<div class="ql-text"><p class="ql-src">Our quest data has no text for this quest yet</p></div>`;
  return `<div class="ql-text">${t.todo ? `<p class="ql-todo">${esc(t.todo)}</p>` : ""}${t.text ? `<p class="ql-words">${esc(t.text)}</p>` : ""}
    <p class="ql-src">${t.game ? "This is the quest's text from your game" : "This is the quest's text from our quest data. The game's own text shows after a /reload"}</p></div>`;
}

function toggleQuestText(id) {
  questsUi.textOpen = questsUi.textOpen === id ? null : id;
  askQuestTexts();
  buildQuestMenu();
}


const QUESTS_ICON = "inv_scroll_08";
const NO_QUEST_MARK = "The game hasn't marked this quest on its map yet";

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
  if (e.failed) return `<div class="hv-head">Failed</div>`;
  if (e.complete) return `<div class="hv-head">Ready for turn-in</div>`;
  const objs = e.objectives.map((o) => `<div class="hv-row${o.finished ? " done" : ""}">${lineNamed(o)}</div>`).join("")
    || (e.text ? `<div class="hv-row">${lineNamed(e)}</div>` : `<div class="hv-note">The game lists no objectives</div>`);
  return `<div class="hv-head">Objectives</div>${objs}`;
}
function questTipWhere(e) {
  const at = questSpot(e), z = at && zoneAt(at.n, at.w, at.inst), zone = z && app.maps[z.id]?.name;
  if (!at) return `<div class="hv-foot">${NO_QUEST_MARK}</div>`;
  return `<div class="hv-foot">${zone ? `In ${esc(zone)}` : "On the map"}${at.learnt ? ", where the game last marked the quest" : ""}</div>`;
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
    showToast(e ? `The game hasn't marked ${e.title} on its map yet` : "That quest isn't in your quest log now");
    return opts.then?.();
  }
  if (!opts.auto) {
    hoverQuest(null);
    toggleQuestMenu(false);
  }
  guideTo({ todoId: null, name: e.title, sub: at.turnin ? "its turn-in" : "its objectives", cat: "gameguide", icon: QUESTS_ICON,
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

function zonesHtml() {
  const list = questsUi.zones;
  const head = `<div class="qz-head"><button class="qz-back" data-view="log">Back</button><span>Zone epic</span></div>`;
  if (!list) {
    return `${head}<p class="menu-note">${askNote("/api/quests", { what: "the zones with quests for you",
      again: () => { refreshQuestZones(true); buildQuestMenu(); } })}</p>`;
  }
  const me = playerWorld() || (app.state && app.maps[app.state.map]?.world ? { inst: app.maps[app.state.map].instance,
    n: (app.maps[app.state.map].world.top + app.maps[app.state.map].world.bottom) / 2,
    w: (app.maps[app.state.map].world.left + app.maps[app.state.map].world.right) / 2 } : null);
  const running = app.tracks?.epic?.key;
  const hereMark = (z) => (app.state && z.id === app.state.map ? `<span class="step-tag here qz-here">You are here</span>` : "");
  const rows = list.filter((z) => matchesSearch(z.name, questsUi.find))
    .map((z) => ({ ...z, levels: app.maps[z.id]?.levels || null, far: zoneFar(z.id, me) }))
    .sort((a, b) => (!a.levels - !b.levels) || (a.levels?.[0] ?? 0) - (b.levels?.[0] ?? 0)
      || (a.levels?.[1] ?? 0) - (b.levels?.[1] ?? 0) || a.far - b.far || a.name.localeCompare(b.name))
    .map((z) => `<button class="qz-row${running === `zone:${z.id}` ? " on" : ""}" data-zone="${z.id}"
        title="This plans every quest of ${esc(z.name)} as one epic, with the order, the route and the legs">
      <span class="qz-name">${esc(z.name)}</span>${z.levels ? `<span class="qz-range" style="color:${zoneThreat(z.levels)}">${esc(zoneRangeText(z.levels))}</span>` : ""}
      <span class="qz-count">${z.done ? `${z.done} of ${z.quests} done` : `${z.quests} quest${z.quests === 1 ? "" : "s"}`}${
        z.missing ? ` <span class="data-missing" title="Forever added ${z.missing} quest${z.missing === 1 ? "" : "s"} to ${esc(z.name)} with no information on them yet. The zone epic leaves ${z.missing === 1 ? "that quest" : "those quests"} out. When a quest giver offers one in game, the addon takes it">${z.missing} no data yet</span>` : ""}${hereMark(z)}</span></button>`).join("");
  return `${head}<div class="qz-find">${searchBox("zone-find", "Find a zone", questsUi.find)}</div>
    <div class="qz-list">${rows || (list.length ? nothingMatches() : `<p class="menu-note">No zone has quests for you.</p>`)}</div>`;
}

const CAMP_KEY = "camp:epic";
function campKey() {
  const opens = questsUi.campOpens, level = app.state?.level || 1;
  const shut = opens === null ? "The data has no camping quests yet" : opens > level ? `Camping opens at level ${opens}` : "";
  const on = app.tracks?.epic?.key === CAMP_KEY;
  return `<button class="ql-epickey${on ? " on" : ""}" data-camp-epic${shut ? " disabled" : ""} title="${esc(shut ||
    "This plans camping as one epic, with the camping quests at the nearest camper, Cooking, the professions' camp features and a first camp, as far as the character's level and skills allow")}"><img src="/icon/spell_fire_fire.jpg" alt="">Camping epic</button>`;
}

function classChainNow(chains = questsUi.classChains, level = app.state?.level || 1) {
  return (chains || []).find((c) => c.lv <= level) || null;
}
function classKey() {
  const chains = questsUi.classChains || [], now = classChainNow(chains), next = chains[0];
  const cls = CLASS_ICONS[app.status?.classId];
  const on = now && app.tracks?.epic?.key === `class:${now.c}`;
  const shut = now ? "" : next ? `Your next class quest opens at level ${next.lv}` : "No class quest is open for you now";
  const tip = now ? `This plans the class quest ${now.n} as one epic, every step of it in order${now.u ? `. ${now.n} teaches ${now.u}` : ""}` : shut;
  return `<button class="ql-epickey${on ? " on" : ""}" data-class-epic="${now ? now.c : ""}"${shut ? " disabled" : ""} title="${esc(tip)}"><img src="/icon/${
    cls ? `classicon_${cls}` : "inv_misc_book_11"}.jpg" alt="">Class quest</button>`;
}

function buildQuestMenu() {
  loadPicks();
  const log = questLog();
  const inLog = new Set((log || []).filter((e) => e.id).map((e) => e.id));
  const picked = [...questsUi.picked].filter((id) => inLog.has(id));
  const scroller = questMenu.querySelector(".ql-scroll, .qz-list");
  const scrolled = scroller?.scrollTop || 0;
  const written = setHtml(questList, questsUi.view === "zones" ? zonesHtml() : questsUi.view === "profs" ? profsViewHtml() : `
    <div class="ql-top"><button class="ql-epickey" data-view="zones" title="This lists every zone with quests for the character. A click on a zone plans all of its quests as one epic"><img src="/icon/inv_misc_map_01.jpg" alt="">Zone epic</button>
      <button class="ql-epickey" data-log-epic${picked.length ? "" : " disabled"}
        title="${picked.length ? "This plans the ticked quests as one epic. The quests that follow them are offered once the epic is done" : "Tick the quests to plan first"}"><span class="ql-mark" aria-hidden="true">!</span>Quest epic${picked.length ? ` (${picked.length})` : ""}</button>
      ${campKey()}
      ${classKey()}${helpButton("classquest")}
      <button class="ql-epickey" data-view="profs" title="This lists every profession with its epic. Start a profession's epic and it leads the way when there's something to do, from the trainer to the next rank"><img src="/icon/trade_blacksmithing.jpg" alt="">Professions</button>
      <label class="ql-close" title="A dense camp further off can be the better camp, with more of what a quest needs in one spot. When this box is ticked, the epics started from now plan each objective's camp near its quest's giver instead, for less walking"><input type="checkbox" data-prefer-close${preferClose() ? " checked" : ""}> Prefer close</label></div>
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
  { el: $("quest-bar"), title: "Quests and Professions", help: "quests" });

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
    const z = questsUi.zones?.find((x) => x.id === +zone.dataset.zone);
    toggleQuestMenu(false);
    return startEpic({ key: `zone:${zone.dataset.zone}`, name: z?.name || "the zone" });
  }
  const camp = e.target.closest("button[data-camp-epic]");
  if (camp) {
    if (camp.disabled) return;
    toggleQuestMenu(false);
    return startEpic({ key: CAMP_KEY, name: "Camping epic", label: "the camping epic" });
  }
  const cq = e.target.closest("button[data-class-epic]");
  if (cq) {
    const c = (questsUi.classChains || []).find((x) => String(x.c) === cq.dataset.classEpic);
    if (cq.disabled || !c) return;
    toggleQuestMenu(false);
    return startEpic({ key: `class:${c.c}`, name: c.n, label: `the ${c.n} class quest epic` });
  }
  const epic = e.target.closest("button[data-log-epic]");
  if (epic && !epic.disabled) {
    const inLog = new Set((questLog() || []).filter((x) => x.id).map((x) => x.id));
    const ids = [...questsUi.picked].filter((id) => inLog.has(id)).sort((a, b) => a - b);
    if (!ids.length) return;
    toggleQuestMenu(false);
    startEpic({ key: `log:${ids.join(".")}`, name: "your quests", label: "a quest epic of your ticked quests" });
  }
}
questMenu.addEventListener("click", questMenuClicked);
function questMenuChanged(e) {
  if (e.target.type !== "checkbox" || questMarksSwitched(e.target)) return;
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
