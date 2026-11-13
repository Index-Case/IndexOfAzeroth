// The Index of Azeroth. Copyright 2026 Index Case <indexofazeroth@pm.me>. PolyForm Strict 1.0.0, see LICENSE.md.
"use strict";

const PVP_REFRESH_MS = 30000;
const PVP_ICONS = { skull: "inv_misc_bone_humanskull_01", group: "inv_misc_groupneedmore", kb: "achievement_bg_killingblow_most",
  melee: "ability_meleedamage", revenge: "ability_warrior_revenge", ambush: "ability_rogue_ambush", duel: "ability_dualwield",
  one: "ability_warrior_challange", notice: "inv_misc_note_01" };
const pv = { open: false, data: null, failed: false, search: "", timer: 0, fight: null, shown: null, fightFailed: false,
  scroll: 0, ...keptOr("cc.pvp", {}) };
pv.filter = PVP_FILTERS.includes(pv.filter) ? pv.filter : "all";
pv.by = PVP_GROUPINGS.includes(pv.by) ? pv.by : "class";
pv.bgs = pv.bgs === true;
pv.autos = pv.autos !== false;

const keepPvp = () => keepIn("cc.pvp", { filter: pv.filter, by: pv.by, bgs: pv.bgs, autos: pv.autos });
const PV_WORDS = { window: wordsOf("page.pvp.window"), stats: wordsOf("page.pvp.stats"), filters: wordsOf("page.pvp.filters"),
  table: wordsOf("page.pvp.table"), notice: wordsOf("page.pvp.notice"), fight: wordsOf("page.pvp.fight") };
const pvW = (key, fill) => { const dot = key.indexOf("."); return fillWords(PV_WORDS[key.slice(0, dot)]?.[key.slice(dot + 1)], fill) ?? ""; };
const pvCount = (key, n) => pvW(n === 1 && pvW(`${key}.one`) ? `${key}.one` : key, { n });
const pvSide = () => (app.status?.strs?.faction === "Horde" ? "horde" : "alliance");
const pvIcon = (name, tip = "", more = "") => (name ? `<img class="pv-ico${more ? ` ${more}` : ""}" src="/icon/${esc(name)}.jpg" alt=""${tip ? ` title="${esc(tip)}"` : ""}>` : "");
const pvFileIcon = (fid, tip = "") => (fid ? `<img class="pv-ico" src="/fileicon/${+fid}.jpg" alt=""${tip ? ` title="${esc(tip)}"` : ""}>` : "");
const pvClassIcon = (cls, tip = "") => (CLASS_ICONS[cls] ? pvIcon(`classicon_${CLASS_ICONS[cls]}`, tip) : "");
const pvName = (name, clsName) => `<span class="pv-name"${CLASS_COLORS[clsName] ? ` style="color:${esc(CLASS_COLORS[clsName])}"` : ""}>${esc(name || "")}</span>`;
const pvZone = (r) => r.bg?.name || r.zone || app.maps?.[r.map]?.name || "";
const pvWhen = (t) => { const d = new Date(t * 1000);
  return `${d.toLocaleDateString("en-GB", { day: "numeric", month: "short" })} ${d.toLocaleTimeString("en-GB", { hour: "2-digit", minute: "2-digit" })}`; };
const pvWL = (rec) => `<span class="pv-w">${esc(pvW("stats.won.short", { n: rec.wins }))}</span> <span class="pv-l">${esc(pvW("stats.lost.short", { n: rec.losses }))}</span>`;


function pvLevel(o) {
  if (o?.level) return `<span class="pv-lvl">${o.level}</span>`;
  if (o?.least) return `<span class="pv-lvl pv-floor" title="${esc(pvW("table.level.floor.tip", { level: o.least }))}">${esc(pvW("table.level.floor", { level: o.least }))}</span>`;
  return `<span class="pv-lvl pv-floor" title="${esc(pvW("table.level.none.tip"))}">${esc(pvW("table.level.none"))}</span>`;
}

const pvSideCount = (n, tip) => `<span class="pv-count" title="${esc(tip)}">${pvIcon(PVP_ICONS.group)}${n}</span>`;
const pvSkull = (side) => pvIcon(PVP_ICONS.skull, pvW(`table.skull.${side}.tip`), "pv-skull");

function pvYouCell(r) {
  return `${r.you?.level ? `<span class="pv-lvl">${r.you.level}</span>` : pvLevel(null)}${r.attackers > 1 ? pvSideCount(r.attackers,pvW("table.count.you.tip", { theirs: r.attackers })) : ""}${r.skull === "you" ? pvSkull("you") : ""}`;
}

function pvResultCell(r) {
  const key = r.duel ? `duel.${r.outcome}` : r.outcome;
  const look = r.duel ? "duel" : { won: "won", lost: "lost", guards: "guards" }[r.outcome] || "away";
  const tip = r.duel ? pvW("table.duel.tip") : pvW(`table.${r.outcome}.tip`);
  const count = r.one ? `<span class="pv-one" title="${esc(pvW("table.one.tip"))}">${esc(pvW("table.one"))}</span>`
    : `<span class="pv-heads">${esc(pvW("table.count", { ours: r.ours, theirs: r.theirs }))}</span>`;
  return `<span class="pv-out ${look}" title="${esc(tip)}">${esc(pvW(`table.${key}`))}</span>${count}${r.duel ? pvIcon(PVP_ICONS.duel, tip) : ""}${r.revenge ? pvIcon(PVP_ICONS.revenge, pvW(`table.revenge.${r.revenge}.tip`)) : ""}${r.onMob ? pvIcon(PVP_ICONS.ambush, pvW("table.mob.tip")) : ""}`;
}

function pvOpponentCell(r) {
  const o = r.opp;
  if (!o) return "";
  const who = [o.title, o.name, o.guild ? `<${o.guild}>` : ""].filter(Boolean).join(" ");
  return `${pvClassIcon(o.cls, o.clsName || "")}${o.race?.icon ? pvIcon(o.race.icon, o.race.name) : ""}<span title="${esc(who)}">${pvName(o.name, o.clsName)}</span>${pvLevel(o)}${r.ours > 1 ? pvSideCount(r.ours,pvW("table.count.them.tip", { ours: r.ours })) : ""}${r.skull === "them" ? pvSkull("them") : ""}`;
}

function pvKillCell(r) {
  const k = r.kb;
  if (!k) return "";
  const who = k.by === "you" ? `<span class="pv-name">${esc(pvW("table.kb.you"))}</span>`
    : k.by === "npc" ? `<span class="pv-name" title="${esc(k.name || "")}">${esc(pvW("table.kb.guards"))}</span>`
      : k.by ? pvName(k.name, k.clsName)
        : `<span class="pv-name">${esc(pvW("table.kb.fall"))}</span>`;
  const spell = k.swing ? pvIcon(PVP_ICONS.melee, pvW("table.kb.melee")) : pvIcon(pv.data?.icons?.[k.spell], k.spell || "");
  return `${spell}${who}`;
}

function pvWhereCell(r) {
  if (r.bg) return `${pvFileIcon(r.bg.icon, pvW("table.bg.tip", { zone: r.bg.name }))}<span class="pv-bg">${esc(r.bg.name)}</span>`;
  return esc(pvZone(r));
}

const pvHonourCell = (r) => (r.honour ? `${pvIcon(`pvpcurrency-honor-${pvSide()}`)}${esc(pvW("table.honour.value", { n: r.honour }))}` : "");

function pvRow(r) {
  return `<tr class="pv-row ${r.one ? "one" : ""}" data-fight="${esc(r.id)}" title="${esc(pvW("fight.open.tip"))}"><td class="pv-when">${esc(pvWhen(r.t))}</td><td class="pv-you">${pvYouCell(r)}</td>
    <td class="pv-result">${pvResultCell(r)}</td><td class="pv-opp">${pvOpponentCell(r)}</td><td class="pv-kb">${pvKillCell(r)}</td>
    <td class="pv-time">${esc(pvW("table.seconds", { n: Math.round(r.secs) }))}</td><td class="pv-where">${pvWhereCell(r)}</td>
    <td class="pv-honour">${pvHonourCell(r)}</td></tr>`;
}

function pvSearchText(r) {
  const o = r.opp || {};
  return [...r.foes.map((f) => f.name), o.clsName, o.race?.name, o.level || o.least, o.guild, pvZone(r),
    pvW(`table.${r.duel ? `duel.${r.outcome}` : r.outcome}`)].filter((x) => x != null).join(" ");
}


const pvTile = (label, value, sub = "", tip = "", icon = "") => `<div class="pv-tile"${tip ? ` title="${esc(tip)}"` : ""}>
  <span class="pv-tile-n">${icon}${value}</span><span class="pv-tile-label">${esc(label)}</span>${sub ? `<span class="pv-tile-sub">${sub}</span>` : ""}</div>`;

const pvNote = (label, body) => `<div class="pv-note"><span class="pv-note-label">${esc(label)}</span><span class="pv-note-body">${body}</span></div>`;

function pvPlayerStat(label, most, line) {
  return pvNote(label, most ? `${pvClassIcon(most.opp.cls, most.opp.clsName || "")}${pvName(most.opp.name, most.opp.clsName)}<small>${esc(pvCount(line, most.n))}</small>`
    : `<small>${esc(pvW("stats.nobody"))}</small>`);
}

function pvSpellStat(label, s) {
  return pvNote(label, s ? `${pvIcon(pv.data?.icons?.[s.spell], s.spell)}<span class="pv-name">${esc(s.spell)}</span><small>${esc(pvW("stats.spell.line", { n: num(s.n) }))}</small>`
    : `<small>${esc(pvW("stats.nobody"))}</small>`);
}

function pvChip(g) {
  const name = [g.clsName, g.race?.name].filter(Boolean).join(" ");
  return `<span class="pv-chip" title="${esc(pvW("stats.chip.tip", { name, wins: g.wins, losses: g.losses }))}">${g.cls ? pvClassIcon(g.cls) : ""}${g.race?.icon ? pvIcon(g.race.icon) : g.race ? `<span class="pv-chip-word">${esc(g.race.name)}</span>` : ""}${pvWL(g)}</span>`;
}

const pvGroup = (label, parts, nameOf, tip = "") => (parts.length ? `<div class="pv-more-group"${tip ? ` title="${esc(tip)}"` : ""}><span class="pv-more-label">${esc(label)}</span>${parts.map((g) =>
  `<span class="pv-more-part" title="${esc(pvW("stats.group.tip", { name: nameOf(g), wins: g.wins, losses: g.losses }))}">${esc(nameOf(g))} ${pvWL(g)}</span>`).join("")}</div>` : "");

function pvSchoolName(bits) {
  const names = PVP_SCHOOLS.filter((b) => bits & b).map((b) => pvW(`stats.school.${b}`));
  return names.length ? andList(names) : String(bits);
}

function pvStatsHtml(rows) {
  const s = pvpStats(rows, pvZone);
  const rate = s.rate == null ? `<span class="pv-dim">${esc(pvW("stats.rate.none"))}</span>` : esc(pvW("stats.rate.value", { rate: s.rate }));
  const tiles = [pvTile(pvW("stats.wins"), `<span class="pv-w">${s.record.wins}</span>`), pvTile(pvW("stats.losses"), `<span class="pv-l">${s.record.losses}</span>`),
    pvTile(pvW("stats.rate"), rate), pvTile(pvW("stats.one"), pvWL(s.one), "", "", pvIcon(PVP_ICONS.one)),
    pvTile(pvW("stats.kbs"), s.kbs, "", "", pvIcon(PVP_ICONS.kb)), pvTile(pvW("stats.assists"), s.assists, "", pvW("stats.assists.tip")),
    pvTile(pvW("stats.honour"), num(s.honour), esc(pvW("stats.honour.today", { n: num(s.today) })), "", pvIcon(`pvpcurrency-honor-${pvSide()}`)),
    pvTile(pvW("stats.streak"), s.streak, esc(pvW("stats.streak.best", { n: s.best })), pvW("stats.streak.tip"))].join("");
  const notes = [pvPlayerStat(pvW("stats.nemesis"), s.nemesis, "stats.nemesis.line"),
    pvPlayerStat(pvW("stats.favourite"), s.favourite, "stats.favourite.line"),
    pvSpellStat(pvW("stats.most"), s.most), pvSpellStat(pvW("stats.least"), s.least)].join("");
  const switches = PVP_GROUPINGS.map((by) => `<button class="key small" data-by="${by}" aria-pressed="${pv.by === by}">${esc(pvW(`stats.by.${by}`))}</button>`).join("");
  const chips = s.matchups[pv.by].map(pvChip).join("");
  const more = [
    pvGroup(pvW("stats.outnumbered"), s.outnumbered, (g) => (g.key >= 3 ? pvW("stats.outnumbered.more") : pvW("stats.outnumbered.n", { n: g.key }))),
    s.ganks ? `<div class="pv-more-group" title="${esc(pvW("stats.ganks.tip"))}"><span class="pv-more-label">${esc(pvW("stats.ganks"))}</span>${pvIcon(PVP_ICONS.skull)}<span class="pv-l">${s.ganks}</span></div>` : "",
    pvGroup(pvW("stats.gap"), s.gap, (g) => pvW(`stats.gap.${g.key}`)),
    pvGroup(pvW("stats.zones"), s.zones, (g) => g.key),
    pvGroup(pvW("stats.hours"), s.hours, (g) => pvW(`stats.hours.${g.key}`)),
    s.school.length ? `<div class="pv-more-group"><span class="pv-more-label">${esc(pvW("stats.school"))}</span>${s.school.map((x) =>
      `<span class="pv-more-part">${esc(pvSchoolName(x.school))} <b>${num(x.n)}</b></span>`).join("")}</div>` : "",
    s.ttk != null ? `<div class="pv-more-group" title="${esc(pvW("stats.ttk.tip"))}"><span class="pv-more-label">${esc(pvW("stats.ttk"))}</span><b>${esc(pvW("stats.seconds", { n: s.ttk }))}</b></div>` : "",
  ].join("");
  return `<div class="pv-tiles">${tiles}</div><div class="pv-notes">${notes}</div>
    <div class="pv-matchups"><span class="pv-switch">${switches}</span><span class="pv-chips">${chips}</span></div>
    ${more ? `<div class="pv-more">${more}</div>` : ""}`;
}


function pvNoticeHtml() {
  const off = pv.data?.off || [];
  if (!off.length) return "";
  const at = (t) => new Date(t * 1000).toLocaleTimeString("en-GB", { hour: "2-digit", minute: "2-digit" });
  const tip = [...off.map(([a, b]) => pvW("notice.stretch", { day: new Date(a * 1000).toLocaleDateString("en-GB", { day: "numeric", month: "short" }), from: at(a), to: at(b) })),
    pvW("notice.how")].join("\n");
  return `<p class="pv-notice" title="${esc(tip)}">${pvIcon(PVP_ICONS.notice)}${esc(pvCount("notice.off", off.length))}</p>`;
}

function pvFiltersHtml() {
  const keys = PVP_FILTERS.map((f) => `<button class="key small" data-filter="${f}" aria-pressed="${pv.filter === f}">${esc(pvW(`filters.${f}`))}</button>`).join("");
  return `<div class="pv-filters"><span class="pv-keys">${keys}</span>${searchBox("pv-search", pvW("filters.search"), pv.search)}
    <label class="pv-check" title="${esc(pvW("filters.bgs.tip"))}"><input type="checkbox" id="pv-bgs"${pv.bgs ? " checked" : ""}>${esc(pvW("filters.bgs"))}</label></div>`;
}

function pvTableHtml(rows) {
  const heads = ["when", "you", "result", "opponent", "kb", "time", "where", "honour"].map((k) => `<th class="pv-h-${k}">${esc(pvW(`table.${k}`))}</th>`).join("");
  const body = rows.length ? rows.map(pvRow).join("") : `<tr><td colspan="8" class="pv-none">${esc(pvW("filters.nothing"))}</td></tr>`;
  return `<table class="pv-table"><thead><tr>${heads}</tr></thead><tbody>${body}</tbody></table>`;
}

function renderPvp() {
  if (!pv.open) return;
  const fights = pv.data?.fights || [];
  const opened = pv.fight != null;
  let body;
  if (opened) body = pfBodyHtml();
  else if (!pv.data) body = `<p class="muted">${esc(pv.failed ? pvW("window.failed") : pvW("window.loading"))}</p>`;
  else if (!fights.length) body = `<p class="muted pv-empty">${esc(pvW("window.empty"))}</p>`;
  else {
    const counted = pvpCounted(fights, pv.bgs);
    const shown = pvpShown(fights, { filter: pv.filter, search: pv.search, bgs: pv.bgs }, pvSearchText, matchesSearch);
    body = `${pvNoticeHtml()}<div class="pv-stats">${pvStatsHtml(counted)}</div>${pvFiltersHtml()}<div class="pv-scroll">${pvTableHtml(shown)}</div>`;
  }
  const back = opened ? `<button class="key small" data-back="1" title="${esc(pvW("fight.back.tip"))}">${esc(pvW("fight.back"))}</button>` : "";
  setHtml($("pvp"), `<div class="j-bar"><span class="j-bar-keys">${back}</span><span class="j-bar-title">${esc(pvW("window.title"))}</span>
    <span class="j-bar-end">${helpButton("pvp")}<button class="key small square x-mark" data-close="1" title="${esc(pvW("window.close.tip"))}">&times;</button></span></div>
    <div class="j-body pv-body${opened ? " pf-body" : ""}">${body}</div>`);
}

function loadPvp() {
  getJson("/api/pvp", { force: true })?.then((j) => { pv.data = j; pv.failed = false; renderPvp(); },
    () => { pv.failed = true; renderPvp(); });
}

function openPvp() {
  pv.open = true;
  emit("window", "pvp");
  $("pvp").hidden = false;
  $("btn-pvp").setAttribute("aria-pressed", "true");
  renderPvp();
  loadPvp();
  clearInterval(pv.timer);
  pv.timer = setInterval(loadPvp, PVP_REFRESH_MS);
}

function closePvp() {
  pv.open = false;
  clearInterval(pv.timer);
  $("pvp").hidden = true;
  $("btn-pvp").setAttribute("aria-pressed", "false");
}

const togglePvp = () => (pv.open ? closePvp() : openPvp());

$("pvp").addEventListener("click", (e) => {
  const b = e.target.closest("button");
  if (!b) return;
  if (b.dataset.close) return closePvp();
  if (b.dataset.filter) { pv.filter = b.dataset.filter; keepPvp(); return renderPvp(); }
  if (b.dataset.by) { pv.by = b.dataset.by; keepPvp(); return renderPvp(); }
});
$("pvp").addEventListener("input", (e) => {
  if (e.target.id === "pv-search") { pv.search = e.target.value; renderPvp(); }
});
$("pvp").addEventListener("change", (e) => {
  if (e.target.id === "pv-bgs") { pv.bgs = e.target.checked; keepPvp(); renderPvp(); }
});

(function pvpKey() {
  const key = $("btn-pvp");
  key.title = pvW("window.key.tip");
  key.querySelector(".key-word").textContent = pvW("window.key");
  let side = null;
  const icon = () => {
    if (pvSide() === side) return;
    side = pvSide();
    key.style.setProperty("--icon", `url(/icon/${side === "horde" ? "inv_bannerpvp_01" : "inv_bannerpvp_02"}.jpg)`);
  };
  icon();
  on("snapshot", icon);
})();
$("btn-pvp").addEventListener("click", togglePvp);
hotkey(["b"], togglePvp);
closable(LAYER.journal, () => pv.open, closePvp);
on("window", (w) => { if (w !== "pvp" && pv.open) closePvp(); });
