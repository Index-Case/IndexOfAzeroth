// The Index of Azeroth. Copyright 2026 Index Case <indexofazeroth@pm.me>. PolyForm Strict 1.0.0, see LICENSE.md.
"use strict";

const player = { data: null, at: 0, cls: null, open: false, timer: 0, profs: null, profsAt: 0, profsVersion: null,
  for: null,
  chips: {}, tipAsking: new Set(),
  find: "",
  kind: "all",
  back: null,
  goto: null };
const PLAYER_FRESH = 15000;
const PLAYER_MAX = 60;
const pastCap = (level) => Number(level) > (player.data?.maxLevel || Infinity);
const pastCapWords = () => `This level is past the game's level cap of ${player.data.maxLevel}, so you can't reach it yet`;
const SPELL_WORDS = {
  known: "Known", learn: "At your trainer now", later: "You need to reach this level first", talent: "This is a talent's rank, which comes with the talent",
  unknown: "It isn't known yet whether you have this spell or skill. Your spellbook reaches the page with the addon's next /reload",
  elsewhere: "No class trainer teaches this spell. A book, a quest or a portal trainer teaches it",
};
function petSourceHtml(s) {
  const line = (text) => `<div class="sp-line">${esc(text)}</div>`;
  if (s.pet !== "trainer") return line("The page hasn't read yet where this skill is learnt");
  const near = player.data?.petTrainer;
  return line(near ? `A pet trainer teaches this skill. The nearest pet trainer is ${near.name}${near.zone ? ` in ${near.zone}` : ""}` : "A pet trainer teaches this skill")
    + (s.petDisputed ? line("We are not sure yet whether pet trainers teach this skill") : "")
    + (s.petCost != null ? `<div class="sp-line">${money(s.petCost)} at the pet trainer</div>` : "");
}
const PET_WORDS = { known: "Known", learn: "At a pet trainer now", later: "You need to reach this level first", unknown: SPELL_WORDS.unknown };
const petWord = (s) => (s.pet === "trainer" || s.state !== "learn" ? PET_WORDS[s.state] : "Open to you at your level");

const SPELL_TIP_AGAIN_MS = 2000;
function spellHoverHtml(name) {
  const [, id, level] = name.split(":"), s = player.chips[`${id}:${level}`];
  if (!s) return "";
  const tip = s.id ? keptTip(spellTips, s.id) : null;
  if (tip === undefined && !player.tipAsking.has(s.id)) {
    player.tipAsking.add(s.id);
    loadSpellTip(s.id).then((t) => {
      player.tipAsking.delete(s.id);
      if (t) refreshHover();
      else if (spellTips[s.id] === undefined) setTimeout(refreshHover, SPELL_TIP_AGAIN_MS);
    });
  }
  const head = tip?.html || `<b class="q">${esc(s.name)}</b>${s.rank ? ` <span class="q0">${esc(s.rank)}</span>` : ""}`;
  const word = tip && !tip.html ? `<div class="sp-line">${tipWord(tip)}</div>` : "";
  const cost = s.pet ? petSourceHtml(s) : s.state === "elsewhere" || s.cost == null ? ""
    : `<div class="sp-line">${money(s.cost)} at the trainer${s.game ? ", which is the game's price" : ""}</div>`;
  const at = [s.line, `Level ${level}`].filter(Boolean).join(", ");
  const said = pastCap(level) ? pastCapWords() : s.pet ? petWord(s) : SPELL_WORDS[s.state];
  return `<div class="sp-tip">${head}${word}<div class="sp-line sp-first">${esc(at)}</div>${
    said ? `<div class="sp-line">${esc(said)}</div>` : ""}${cost}</div>`;
}
window.HOVERS = window.HOVERS || {};
HOVERS["spell:"] = (pinned, name) => spellHoverHtml(name);

DRAWER_TITLES.player = "Player";

function playerKey() {
  const key = $("btn-player"), cls = app.status?.classId;
  if (!key || !cls || cls === player.cls || !CLASS_ICONS[cls]) return;
  player.cls = cls;
  key.style.setProperty("--icon", `url(/icon/classicon_${CLASS_ICONS[cls]}.jpg)`);
}

function askPlayer(force) {
  if (!app.status?.classId || (!force && player.data && Date.now() - player.at < PLAYER_FRESH)) return;
  const who = app.character;
  getJson("/api/classspells")?.then((d) => {
    if (who !== app.character) return askPlayer(true);
    player.data = d;
    player.at = Date.now();
    playerShown();
  }, playerShown);
}
function playerShown() {
  if (app.drawer === "player") renderDrawer();
  if (player.open) renderTimeline(false);
  emit("playerShown");
}
const spellsNote = (waiting) => (app.status?.classId ? askNote("/api/classspells", { what: "your class's spells",
  again: () => { askPlayer(true); playerShown(); } }) : waiting);

function askProfessions() {
  if (player.profsVersion === alts.version && Date.now() - player.profsAt < PLAYER_FRESH) return;
  const asked = getJson("/api/professions");
  if (!asked) return;
  const who = app.character;
  player.profsVersion = alts.version;
  player.profsAt = Date.now();
  asked.then((d) => {
    if (who !== app.character) return;
    player.profs = d.professions || [];
    if (app.drawer === "player") renderDrawer();
  }, () => { if (app.drawer === "player") renderDrawer(); });
}

const NO_RECIPES = new Set(["Skinning", "Herbalism", "Fishing", "Lockpicking"]);

function professionsHtml(list) {
  if (list === null) {
    return `<h3>Professions</h3><p class="muted">${askNote("/api/professions", { what: "your professions",
      again: () => { player.profsAt = 0; askProfessions(); renderDrawer(); } })}</p>`;
  }
  if (!list?.length) return "";
  const rows = list.map((p) => {
    const asks = [p.next?.skill ? `skill ${p.next.skill}` : "", p.next?.level ? `level ${p.next.level}` : ""].filter(Boolean).join(" and ");
    const next = p.next ? `<div title="${esc(`This comes from the last ${p.name} trainer you saw, ${ago(p.trainerAt)}`)}">Next rank${
      p.next.rank ? `: ${esc(p.next.rank)}` : ""}${asks ? ` at ${asks}` : ""}${p.next.cost ? ` for ${money(p.next.cost)}` : ""}</div>`
      : p.trainerAt ? `<div class="muted">The last ${esc(p.name)} trainer you saw had no higher rank</div>` : "";
    return `<div class="pl-prof"><img src="/icon/${esc(SKILL_ICONS[p.name] || "inv_misc_questionmark")}.jpg" alt="">
      <div><div class="pl-prof-name">${esc(p.name)}${p.max ? ` <small>${p.rank ?? 0} / ${p.max}</small>` : ""}</div>
      ${p.recipes == null || NO_RECIPES.has(p.name) ? "" : `<div>${num(p.recipes)} recipe${p.recipes === 1 ? "" : "s"} known, as your profession window showed them ${ago(p.at)}</div>`}${next}</div></div>`;
  });
  const unread = list.some((p) => (p.recipes == null && !NO_RECIPES.has(p.name)) || !p.trainerAt);
  return `<h3>Professions</h3><div class="pl-profs">${rows.join("")}</div>${unread ? `<p class="muted">Open a profession's window or
    its trainer in game once, and the page fills in its recipes and next rank here.</p>` : ""}`;
}

function spellChip(s, level) {
  const key = `${String(s.id ?? s.name).replace(/:/g, "")}:${level}`;
  player.chips[key] = s;
  return `<span class="tl-spell ${esc(s.state || "later")}${s.pet ? " beast" : ""}" data-hover="spell:${esc(key)}"><img src="/fileicon/${s.icon}.jpg" alt="">${esc(s.name)}${
    s.rank ? `<small>${esc(s.rank.replace("Rank ", "R"))}</small>` : ""}</span>`;
}
const shownSpells = (v) => (v?.spells || []).filter((s) => s.state !== "race");

const GATED_WORDS = { known: "Known", learn: "Yours to learn now", later: "You need to reach this level first", unknown: SPELL_WORDS.unknown };
const GATED_TEACHER = { riding: "a riding trainer", weapon: "a weapon master" };
function gatedChip(e, level) {
  const key = `${e.kind}-${String(e.id ?? e.name).replace(/[:\s]/g, "")}:${level}`;
  player.chips[`gated:${key}`] = { ...e, level };
  const cls = CLASS_ICONS[player.data?.class];
  const icon = e.icon ? `/fileicon/${e.icon}.jpg` : `/icon/${cls ? `classicon_${cls}` : "inv_misc_book_11"}.jpg`;
  return `<span class="tl-spell gated ${esc(e.state || "later")}" data-hover="gated:${esc(key)}"><img src="${icon}" alt="">${esc(e.name)}${
    e.kind === "plan" && e.ranks > 1 ? `<small>${e.rank}/${e.ranks}</small>` : ""}</span>`;
}
const talentSteps = (d) => (d.talentPlan?.steps || []).map((s) => ({ kind: "plan", id: s.node, name: s.name, icon: s.icon,
  rank: s.rank, ranks: s.ranks, level: s.level, state: s.level <= (d.level || 1) ? "learn" : "later" }));
const gatedAt = (d, lv) => [...(d.gated?.[String(lv)] || []), ...talentSteps(d).filter((s) => s.level === lv)];
function gatedHoverHtml(name) {
  const e = player.chips[`gated:${name.slice("gated:".length)}`];
  if (!e) return "";
  const line = (text) => `<div class="sp-line">${esc(text)}</div>`;
  const parts = [`<b class="q">${esc(e.name)}</b>`, `<div class="sp-line sp-first">${e.level === "?" ? "Level not known" : `Level ${e.level}`}</div>`];
  if (e.level === "?") parts.push(line(`We have no information yet on the level ${e.name} opens at`));
  else if (pastCap(e.level)) parts.push(line(pastCapWords()));
  else if (e.kind === "plan") parts.push(line(e.state === "learn" ? "You can take this talent now" : GATED_WORDS.later));
  else if (GATED_WORDS[e.state]) parts.push(line(e.kind === "talent" || e.kind === "milestone" ? (e.state === "known" ? "Reached" : GATED_WORDS.later) : GATED_WORDS[e.state]));
  if (e.kind === "plan") parts.push(line(`Rank ${e.rank} of ${e.ranks}`), line(`Your build, ${player.data?.talentPlan?.build?.name || ""}, takes this talent at this level`));
  else if (e.kind === "talent") parts.push(line(e.spent ? `This is the first level with ${e.spent} talent points, so talents that ask for ${e.spent} points spent can open from this level` : `Talent points: ${e.text}`));
  else if (e.kind === "milestone") parts.push(line(`The game says: ${e.text}`), line(`This level gives a point for Forever's milestone talents${e.of ? `, up to ${e.of} in all` : ""}`));
  else if (e.text) parts.push(line(e.text));
  if (e.at || GATED_TEACHER[e.kind]) {
    const near = player.data?.nearest?.[e.at], who = GATED_TEACHER[e.kind] || `a ${e.name.split(" ").slice(1).join(" ")} trainer`;
    parts.push(line(`${who[0].toUpperCase()}${who.slice(1)} teaches ${e.name}${near ? `. The nearest is ${near.name}${near.zone ? ` in ${near.zone}` : ""}` : ""}`));
  }
  if (e.skill) parts.push(line(`${e.name} lets your skill go up to ${e.skill}`));
  if (e.classic && !e.game) parts.push(line("This level is Classic's, because Forever's own data gives none"));
  if (e.cost != null) parts.push(`<div class="sp-line">${money(e.cost)} at the trainer${e.game ? ", which is the game's price" : e.forever ? "" : ", which is Classic's price"}</div>`);
  return `<div class="sp-tip">${parts.join("")}</div>`;
}
HOVERS["gated:"] = (pinned, name) => gatedHoverHtml(name);
function nextTalentHtml(d) {
  const p = d.talentPlan, nt = p?.next;
  if (!nt) return "";
  const [step] = talentSteps({ ...d, talentPlan: { steps: [nt] } });
  return `<h3>Next talent</h3><div class="tl-spells">${gatedChip(step, nt.level)}</div>
    <p class="muted">${nt.level <= (d.level || 1) ? "You can take it now" : `At level ${nt.level}`}, from your build ${esc(p.build.name)}.${
      p.known ? "" : " Your talents reach the Index with the addon's next /reload."}</p>`;
}

const playerName = () => {
  const c = alts.data?.chars?.[alts.data.current];
  return c ? altName(c) : "You";
};

DRAWERS.player = function () {
  playerKey();
  askPlayer(false);
  askProfessions();
  const d = player.data;
  if (!d) {
    return `${emit("playerHead").join("")}<p class="muted">${spellsNote("This shows the class's spells level by level, from the game's own tables. The spells show once the game has said who's playing.")}</p>
      ${emit("playerDrawer").join("")}`;
  }
  const levels = Object.entries(d.levels);
  const now = levels.flatMap(([lv, v]) => shownSpells(v).filter((s) => s.state === "learn" && !s.pet).map((s) => [lv, s]));
  const next = levels.find(([lv, v]) => Number(lv) > (d.level || 1) && shownSpells(v).length);
  const nowCost = now.every(([, s]) => s.cost != null) ? now.reduce((sum, [, s]) => sum + s.cost, 0)
    : [...new Set(now.map(([lv]) => lv))].reduce((sum, lv) => sum + (d.levels[lv].cost || 0), 0);
  return `<div class="pl-top"><div><div class="pl-head">${CLASS_ICONS[d.class] ? `<img class="pl-icon" src="/icon/classicon_${CLASS_ICONS[d.class]}.jpg" alt="">` : ""}
      <div><div class="pl-name">${esc(playerName())}</div><div class="pl-sub">Level ${d.level || "?"} ${esc(d.name)}</div></div></div></div>
    ${emit("playerHead").join("")}</div>
    <p class="pl-keys"><button class="key" data-player="timeline" style="--icon:url(/icon/inv_misc_book_11.jpg)" title="This shows every level to 60, what each level opens and what it costs">Your road to 60</button>
      <button class="key" data-player="talents" style="--icon:url(/icon/ability_marksmanship.jpg)" title="The talent planner shows your class's talent trees with your build's talents lit and the level each one is taken at (N)">Talents</button></p>
    ${d.known ? "" : `<p class="muted">Your spellbook reaches the page with the addon's next /reload. Until then, no spell is lit as known.</p>`}
    ${now.length ? `<h3>At your trainer now</h3><div class="tl-spells">${now.map(([lv, s]) => spellChip(s, lv)).join("")}</div>
      <p class="muted pl-train">${word("page.price.total", { money: money(nowCost) })} ${kindGuideKey("class")}</p>` : d.known ? `<p>You have nothing to learn at your trainer now.</p>` : ""}
    ${next ? `<h3>Next, at level ${next[0]}</h3><div class="tl-spells">${shownSpells(next[1]).map((s) => spellChip(s, next[0])).join("")}</div>
      <p class="muted">${money(next[1].cost || 0)}</p>` : ""}
    ${nextTalentHtml(d)}
    ${professionsHtml(player.profs)}${emit("playerDrawer").join("")}`;
};


const ROAD_KINDS = [
  { kind: "all", name: "All", find: "Find a spell" },
  { kind: "class", name: "Class spells", find: "Find a class spell" },
  { kind: "pet", name: "Pet skills", find: "Find a pet skill" },
  { kind: "talent", name: "Talents", find: "Find a talent" },
  { kind: "profession", name: "Professions", find: "Find a profession skill" },
  { kind: "weapon", name: "Weapon skills", find: "Find a weapon skill" },
  { kind: "riding", name: "Riding", find: "Find a riding skill" },
  { kind: "spec", name: "Specializations", find: "Find a specialization" },
];
const roadKind = (k) => ROAD_KINDS.find((r) => r.kind === k);
const spellKind = (sp) => (sp.pet ? "pet" : "class");
const gatedKind = (e) => (e.kind === "milestone" || e.kind === "plan" ? "talent" : e.kind);
function roadChips(d) {
  const out = [];
  for (const v of Object.values(d.levels)) for (const sp of shownSpells(v)) out.push([spellKind(sp), sp, "spell"]);
  for (const list of [...Object.values(d.gated || {}), d.gatedUnknown || [], talentSteps(d)]) for (const e of list) out.push([gatedKind(e), e, "gated"]);
  return out;
}
function kindIcon(kind, chips, d) {
  const cls = CLASS_ICONS[d.class], classIcon = `/icon/${cls ? `classicon_${cls}` : "inv_misc_book_11"}.jpg`;
  if (kind === "all") return "/icon/inv_misc_book_11.jpg";
  if (kind === "class" || kind === "talent") return classIcon;
  const first = chips.find(([k, c]) => k === kind && c.icon);
  return first ? `/fileicon/${first[1].icon}.jpg` : classIcon;
}
function shownKind(d) {
  return player.kind !== "all" && roadChips(d).some(([k]) => k === player.kind) ? player.kind : "all";
}
function kindKeys(d, shown) {
  const chips = roadChips(d), held = new Set(chips.map(([k]) => k));
  return `<div class="tl-kinds">${ROAD_KINDS.map((r) => {
    const has = r.kind === "all" || held.has(r.kind);
    return `<button class="key small" data-tl-kind="${r.kind}" aria-pressed="${shown === r.kind}" style="--icon:url(${kindIcon(r.kind, chips, d)})"${
      has ? "" : " disabled"} title="${esc(r.kind === "all" ? "Show everything on the road" : has ? `Show only the ${r.name.toLowerCase()} on the road`
        : `Your road has no ${r.name.toLowerCase()}`)}">${esc(r.name)}</button>`;
  }).join("")}</div>`;
}

const timelineKept = keptOr("cc.timeline", {});
if (typeof timelineKept.find === "string") player.find = timelineKept.find;
if (roadKind(timelineKept.kind)) player.kind = timelineKept.kind;
if (timelineKept.open === true && Number.isFinite(timelineKept.scroll) && timelineKept.scroll > 0) player.back = timelineKept.scroll;
function keepTimeline() {
  const sc = $("timeline").querySelector(".tl-scroll");
  const scroll = player.back ?? (sc && player.open ? Math.round(sc.scrollTop) : 0);
  keepIn("cc.timeline", { open: player.open, kind: player.kind, find: player.find, scroll });
}
on("start", () => { if (timelineKept.open === true) openTimeline(); });
on("snapshot", () => {
  if (player.for !== app.character) {
    const had = !!player.data;
    Object.assign(player, { for: app.character, data: null, at: 0, profs: null, profsAt: 0, profsVersion: null });
    if (had || player.open) askPlayer(true);
    playerShown();
  } else if (player.open && !player.data) askPlayer(false);
});

function openTimeline() {
  player.open = true;
  askPlayer(true);
  renderTimeline(true);
  clearInterval(player.timer);
  player.timer = setInterval(() => askPlayer(false), PLAYER_FRESH);
  keepTimeline();
}
function closeTimeline() {
  player.open = false;
  player.back = null;
  clearInterval(player.timer);
  $("timeline").hidden = true;
  keepTimeline();
}

function renderTimeline(toYou) {
  const d = player.data, box = $("timeline");
  const bar = `<div class="rd-bar"><span class="rd-keys"></span>
    <span class="rd-title">Your road to 60<small>${d ? `${esc(playerName())}, ${esc(d.name)}. ` : ""}The class trainer's spells${
      d && Object.values(d.levels).some((v) => v.spells.some((s) => s.pet)) ? " and the pet's skills" : ""} by the level they're learnt at, and what else each level opens</small></span>
    <span class="rd-keys">${helpButton("timeline")}<button class="key small square x-mark" data-tl="close" title="Close (Escape)">&times;</button></span></div>`;
  if (!d) {
    setHtml(box, `${bar}<div class="rd-scroll"><p class="muted">${spellsNote("The class's spells come from the game's own tables once the game has said who's playing.")}</p></div>`);
    box.hidden = false;
    return;
  }
  const you = d.level || 1, s = app.state, part = s?.xpMax ? Math.min(1, (s.xp || 0) / s.xpMax) : 0;
  const kind = shownKind(d), of = (k) => kind === "all" || k === kind;
  const searching = !!player.find.trim() || kind !== "all", rows = [];
  let capSaid = false;
  for (let lv = 1; lv <= Math.max(PLAYER_MAX, d.maxLevel || 0); lv++) {
    const v = d.levels[String(lv)], spells = shownSpells(v).filter((sp) => of(spellKind(sp)) && matchesSearch(`${sp.name} ${sp.rank || ""}`, player.find));
    const more = gatedAt(d, lv).filter((e) => of(gatedKind(e)) && matchesSearch(e.name, player.find));
    if (searching && !spells.length && !more.length) continue;
    const cost = searching ? spells.reduce((sum, sp) => sum + (sp.cost || 0), 0) : spells.length && v.cost;
    const fill = lv < you ? 1 : lv === you ? part : 0;
    const beyond = pastCap(lv);
    if (beyond && !capSaid) {
      capSaid = true;
      rows.push(`<div class="tl-cap" id="tl-cap">The game's level cap is ${d.maxLevel}, so you can't reach the levels past it yet</div>`);
    }
    rows.push(`<div class="tl-row${spells.length || more.length ? "" : " quiet"}${lv <= you ? " past" : ""}${lv === you ? " now" : ""}${beyond ? " beyond" : ""}" id="tl-${lv}" style="--fill:${(fill * 100).toFixed(1)}%">
      <span class="tl-mark"${beyond ? ` title="${esc(pastCapWords())}"` : ""}>${lv}</span>
      <div class="tl-spells">${spells.map((sp) => spellChip(sp, lv)).join("")}${more.map((e) => gatedChip(e, lv)).join("")}</div>
      <span class="tl-cost">${cost ? money(cost) : ""}</span></div>`);
  }
  const unknown = (d.gatedUnknown || []).filter((e) => of(gatedKind(e)) && matchesSearch(e.name, player.find));
  if (unknown.length) {
    rows.push(`<div class="tl-row tl-unknown" id="tl-unknown"><span class="tl-mark">?</span>
      <div class="tl-spells">${unknown.map((e) => gatedChip({ ...e, state: "later" }, "?")).join("")}</div><span class="tl-cost"></span></div>`);
  }
  const scroller = box.querySelector(".tl-scroll"), kept = player.back ?? (scroller && !toYou && player.goto == null ? scroller.scrollTop : null);
  setHtml(box, `${bar}<div class="tl-find">${kindKeys(d, kind)}${searchBox("tl-find", roadKind(kind).find, player.find)}</div>
    <div class="rd-scroll tl-scroll">${rows.length ? `<div class="tl-list">${rows.join("")}</div>` : nothingMatches()}</div>`);
  box.hidden = false;
  player.back = null;
  const sc = box.querySelector(".tl-scroll");
  if (kept != null) sc.scrollTop = kept;
  else {
    const row = $(`tl-${player.goto ?? you}`);
    if (row) sc.scrollTop = row.offsetTop - sc.offsetTop - sc.clientHeight / 2 + row.offsetHeight / 2;
  }
  player.goto = null;
}
function openTimelineAt(level) {
  player.goto = level;
  player.kind = "all";
  player.find = "";
  openTimeline();
}

function playerDrawerClicked(e) {
  if (e.target.closest("button[data-player='timeline']")) openTimeline();
  if (e.target.closest("button[data-player='talents']")) openTalents();
  const near = e.target.closest("button[data-near]");
  if (near) guideToKind(near.dataset.near);
}
$("drawer").addEventListener("click", playerDrawerClicked);
function timelineClicked(e) {
  const key = e.target.closest("button[data-tl-kind]");
  if (e.target.closest("button[data-tl='close']")) closeTimeline();
  else if (key) timelineFiltered(key.dataset.tlKind);
  else if (e.target.closest("button[data-find-all]")) {
    player.kind = "all";
    timelineSearched("");
  }
}
$("timeline").addEventListener("click", timelineClicked);
function timelineSearched(query) {
  player.find = query;
  player.back = null;
  renderTimeline(true);
  keepTimeline();
}
function timelineFiltered(kind) {
  if (!roadKind(kind)) return;
  player.kind = kind;
  timelineSearched(player.find);
}
$("timeline").addEventListener("input", (e) => { if (e.target.id === "tl-find") timelineSearched(e.target.value); });
$("timeline").addEventListener("scroll", (e) => { if (e.target.matches?.(".tl-scroll")) keepTimeline(); }, true);
closable(LAYER.reader, () => !$("timeline").hidden, () => closeTimeline());
