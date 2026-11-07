// The Index of Azeroth. Copyright 2026 Index Case <indexofazeroth@pm.me>. PolyForm Strict 1.0.0, see LICENSE.md.
"use strict";

const dungeon = { list: [], byKey: {}, byInstance: {}, detail: {}, level: 0, floorPick: {}, wingPick: {}, stars: null, killsSeen: null };
app.dungeon = null;
app.run = null; app.group = null; app.quests = null; app.cap = []; app.gameGuide = null;

const DPOI = [
  ["d:bosses", "Bosses", "achievement_boss_edwinvancleef", "numbered in the order they're met"],
  ["d:rares", "Rare spawns", "inv_misc_head_dragon_01", "the NPCs menu's rares in this dungeon"],
  ["d:myquests", "Your quests", "inv_misc_note_01", "targets of quests in the quest log"],
  ["d:allquests", "All quests", "inv_misc_note_02", "every quest target in this dungeon"],
];
const ROLE_LETTER = { tank: "T", healer: "H", damage: "D" };
const POWER_COLOR = { 0: tint("quality-rare"), 1: tint("power-rage"), 2: tint("class-druid"), 3: tint("class-rogue") };

function loadDungeons(level) {
  getJson(`/api/dungeons?level=${level || 0}`, { key: "dungeons" })?.then((list) => {
    dungeon.level = level;
    dungeon.list = list;
    dungeon.byKey = Object.fromEntries(list.map((d) => [d.key, d]));
    dungeon.byInstance = {};
    for (const d of list) if (d.index) (dungeon.byInstance[d.instance] ||= []).push(d);
    renderJournal();
  }, () => renderJournal());
}

const DETAIL_LISTS = ["quests", "bosses", "trash", "floors", "chain", "entrances"];
function normalDetail(d) {
  const out = { ...d };
  for (const k of DETAIL_LISTS) if (!Array.isArray(out[k])) out[k] = [];
  return out;
}
function dungeonDetail(key) {
  if (dungeon.detail[key]) return dungeon.detail[key];
  getJson(`/api/dungeon/${key}`)?.then((d) => {
    dungeon.detail[key] = normalDetail(d);
    detailShown();
  }, () => detailShown());
  return null;
}
function detailShown() {
  renderJournal();
  if (!app.dungeon) return;
  if (!mobMenu.hidden) buildMobMenu();
  if (!poiMenu.hidden) buildPoiMenu();
}
const detailAgain = (key) => () => {
  dungeonDetail(key);
  detailShown();
};


const MAX_STARS = 40;

function toggleWish(id) {
  const stars = dungeon.stars || [];
  if (!stars.includes(id) && stars.length >= MAX_STARS) {
    showToast(`A character's star list holds ${MAX_STARS} items. Unstar an item first`);
    return;
  }
  postJson("/api/wish", { toggle: id }).then((ids) => { dungeon.stars = ids; renderJournal(); renderRun(); },
    (e) => askFailed("The star wasn't saved", e));
}

const isWished = (id) => !!dungeon.stars?.includes(id);

function starredLoot(b, det) {
  const ids = (b?.loot || []).filter((id) => isWished(id) && det.items[id]);
  if (!ids.length) return "";
  const names = ids.map((id) => `<span class="q${esc(det.items[id].q)}" data-tip="${id}">${esc(det.items[id].n)}</span>`);
  return `Starred loot ${esc(b.name)} can drop: ${names.join(", ")}`;
}

function starredDown(b, det) {
  const names = (b?.loot || []).filter(isWished).map((id) => det.items[id]?.n).filter(Boolean);
  return names.length ? `${b.name} is down. Starred loot it can drop: ${names.join(", ")}` : "";
}

function starsToLoad() {
  const game = app.run?.wish, page = dungeon.stars;
  if (!game || !page || (game.length === page.length && game.every((id) => page.includes(id)))) return "";
  return "Your starred loot changed since the game loaded it";
}

function runKills(key, r = app.run) {
  if (!r) return [];
  return key === r.key ? r.kills : r.also?.[key] || [];
}

function noteStars(snap) {
  const stars = snap.stars ?? null;
  if (!sameData(stars, dungeon.stars)) {
    dungeon.stars = stars;
    renderRun(); renderReload(); renderJournal();
  }
  const run = snap.run?.inside ? snap.run : null, seen = dungeon.killsSeen;
  const down = run ? [run.key, ...Object.keys(run.also || {})].flatMap((k) => runKills(k, run).map((i) => `${k}:${i}`)) : [];
  dungeon.killsSeen = run && { key: run.key, kills: down };
  if (!run || seen?.key !== run.key) return;
  const said = down.filter((k) => !seen.kills.includes(k)).map((k) => {
    const [key, i] = k.split(":"), det = dungeon.detail[key];
    return det ? starredDown(det.bosses[i - 1], det) : "";
  }).filter(Boolean);
  if (said.length) showToast(said.join(". "));
}
on("snapshot", noteStars);

const itemIcon = (it) => (it.icon ? `/fileicon/${esc(it.icon)}.jpg` : `/icon/${esc(it.iconName || "inv_misc_questionmark")}.jpg`);


function wingFor(instance, subzone) {
  const wings = dungeon.byInstance[instance] || [];
  if (wings.length < 2) return wings[0] || null;
  for (const w of wings) {
    const det = dungeonDetail(w.key);
    if (det && ((det.subAreas || []).includes(subzone) || det.bosses.some((b) => b.sub === subzone))) return w;
  }
  const at = `d${app.state?.realMap ?? app.state?.map}`;
  const on = wings.filter((w) => (dungeonDetail(w.key)?.floors || []).includes(at));
  if (on.length === 1) return on[0];
  if (app.run?.key && wings.some((w) => w.key === app.run.key)) return dungeon.byKey[app.run.key];
  if (app.dungeon && wings.some((w) => w.key === app.dungeon.key)) return dungeon.byKey[app.dungeon.key];
  return wings[0];
}

function wingHere(instance, subzone) {
  const wings = dungeon.byInstance[instance] || [];
  const inside = app.dungeon?.instance === instance;
  if (!inside) delete dungeon.wingPick[instance];
  const held = dungeon.wingPick[instance] ?? (inside ? app.dungeon.key : app.run?.inside ? app.run.key : null);
  return wings.find((w) => w.key === held) || wingFor(instance, subzone);
}

const inDungeon = (s = app.state) => !!app.dungeon || ["party", "raid"].includes(s?.instance?.kind);

const inBox = (b, p) => b[0] <= p[0] && p[0] <= b[3] && b[1] <= p[1] && p[1] <= b[4] && (p[2] == null || (b[2] <= p[2] && p[2] <= b[5]));

function floorAt(floors, p) {
  let best = null, bestArea = Infinity;
  for (const id of floors) {
    const f = app.maps[id];
    if (!f) continue;
    const w = f.world;
    const boxes = f.boxes?.length ? f.boxes : [[w.bottom, w.right, -1e6, w.top, w.left, 1e6]];
    for (const b of boxes) {
      const area = (b[3] - b[0]) * (b[4] - b[1]);
      if (inBox(b, p) && area < bestArea) { best = id; bestArea = area; }
    }
  }
  return best;
}

function applyDungeon() {
  const s = app.state, inst = s?.instance;
  const d = inst?.id && dungeon.list.length ? wingHere(inst.id, s.subzone) : null;
  if (!d || !d.floors?.length || !d.floors.every((id) => app.maps[id])) {
    if (app.dungeon) leaveDungeonMode();
    return;
  }
  dungeonDetail(d.key);
  const fresh = !app.dungeon || app.dungeon.key !== d.key;
  if (fresh) delete dungeon.floorPick[d.key];
  const pick = dungeon.floorPick[d.key];
  const floor = d.floors.find((id) => String(id) === pick) ?? d.floors[0];
  s.realMap = s.map;
  s.map = floor;
  s.pos = null;
  s.zone = d.name;
  app.dungeon = { key: d.key, floor, instance: inst.id };
  if (fresh && app.guide?.dungeonKey === d.key) endGuide(`Arrived at ${app.guide.name}`);
  if (fresh) {
    app.view.continent = null; app.view.world = false; app.view.zoom = 1; app.view.follow = true;
    app.trail = [];
    turnOnDungeonPois();
  }
  renderFloorKeys(d);
}

function leaveDungeonMode() {
  app.dungeon = null;
  app.view.zoom = Math.max(1, app.view.zoneZoom || 2.5);
  renderFloorKeys(null);
}

function turnOnDungeonPois() {
  try {
    if (localStorage.getItem("cc.dpoiSet")) return;
    localStorage.setItem("cc.dpoiSet", "1");
  } catch (e) {   }
  poi.on.add("d:bosses"); poi.on.add("d:myquests");
  savePoi();
}


function renderFloorKeys(d) {
  const box = $("floorkeys");
  const wings = d ? dungeon.byInstance[d.instance] || [] : [];
  if (!d || (d.floors.length < 2 && wings.length < 2)) {
    setHtml(box, "");
    box.hidden = true;
    return;
  }
  const wingKeys = wings.length < 2 ? "" : wings.map((w) => `<button class="key small floor" data-wing="${esc(w.key)}" aria-pressed="${w.key === d.key}"
    title="${esc(w.name)}">${esc(w.name)}</button>`).join("");
  const keys = d.floors.length < 2 ? "" : d.floors.map((id) => `<button class="key small floor" data-floor="${id}" aria-pressed="${app.dungeon?.floor === id}"
    title="${esc(app.maps[id]?.name || id)}">${esc(app.maps[id]?.name || id)}</button>`).join("");
  setHtml(box, wingKeys + keys);
  box.hidden = false;
}

function pickFloor(id) {
  if (!id || !app.dungeon) return;
  dungeon.floorPick[app.dungeon.key] = id;
  applyDungeon();
}
function pickWing(key) {
  const inst = app.dungeon?.instance;
  if (!(dungeon.byInstance[inst] || []).some((w) => w.key === key)) return;
  dungeon.wingPick[inst] = key;
  applyDungeon();
}
$("floorkeys").addEventListener("click", (e) => { const b = e.target.closest("button[data-floor], button[data-wing]"); return b?.dataset.wing ? pickWing(b.dataset.wing) : pickFloor(b?.dataset.floor); });


function dungeonPoiCounts(d) {
  if (!d) return {};
  const logIds = new Set((app.quests?.log || []).map((q) => q.id)), aimed = d.quests.filter((q) => q.spots?.length);
  return { "d:bosses": d.bosses.filter((b) => !b.rare).length, "d:rares": d.bosses.filter((b) => b.rare).length,
    "d:myquests": aimed.filter((q) => logIds.has(q.id)).length, "d:allquests": aimed.length };
}

function buildDungeonMenu(menu) {
  const d = dungeonDetail(app.dungeon.key), n = dungeonPoiCounts(d);
  const asked = d ? "" : `<p class="menu-note">${askNote(`/api/dungeon/${app.dungeon.key}`, { what: "the dungeon's bosses and quests",
    again: detailAgain(app.dungeon.key) })}</p>`;
  menu.innerHTML = `<div class="poi-all"><button data-all="1">All</button><button data-all="0">None</button></div>`
    + `<div class="layer-group">${esc(d?.name || "Dungeon")}</div>${asked}` + DPOI.map(([key, label, icon, note]) =>
    `<label><input type="checkbox" value="${key}"${poi.on.has(key) ? " checked" : ""}>
      <img src="/icon/${icon}.jpg" alt=""> ${label}${key in n ? ` (${n[key]})` : ""}${note ? `<small>${note}</small>` : ""}</label>`).join("") +
    `<p class="menu-note">Outside the dungeon, this menu shows the town list again.</p>`;
}


function floorMinimap(info) {
  return info?.high ? { src: pictureSrc(`/dungeonmap/${info.instance}.png`, info.high.v), world: info.high.world } : null;
}

function floorPicture(info) {
  return info?.baked ? { src: pictureSrc(`/dungeonbake/${info.instance}.jpg`, info.baked.v), world: info.baked.world }
    : floorMinimap(info);
}

function onFloor(floorId, pos, floors, frame = app.maps[floorId]?.world) {
  if (!frame || !pos) return null;
  if (floors && floors.length > 1 && floorAt(floors, pos) !== floorId) return null;
  const [x, y] = toFrac(frame, pos[0], pos[1]);
  return x >= 0 && x <= 1 && y >= 0 && y <= 1 ? [x, y] : null;
}

function drawBossMarker(x, y, n, state, rare) {
  const fill = state === "down" ? tint("iron") : state === "next" ? tint("boss-next") : tint("boss-pin");
  const ring = state === "down" ? tint("pewter") : state === "next" ? tint("gold") : tint("bronze-light");
  const text = state === "down" ? "✓" : n, color = state === "down" ? tint("spent") : tint("ivory"), font = `13px ${MARK_FONT}`;
  if (!rare) return drawRingMarker(x, y, { r: 12, edge: 2, fill, ring, text, font, color });
  ctx.save();
  ctx.translate(x, y); ctx.rotate(Math.PI / 4);
  ctx.beginPath(); ctx.rect(-9, -9, 18, 18); ctx.fillStyle = tint("black"); ctx.fill();
  ctx.beginPath(); ctx.rect(-7, -7, 14, 14); ctx.fillStyle = fill; ctx.fill();
  ctx.lineWidth = 2; ctx.strokeStyle = ring; ctx.stroke();
  ctx.restore();
  ctx.fillStyle = color; ctx.font = font; ctx.textAlign = "center"; ctx.textBaseline = "middle";
  ctx.fillText(String(text), x, y + 1);
}

function drawDungeon(s, size, scale) {
  if (!app.dungeon) return;
  const d = dungeon.detail[app.dungeon.key];
  if (!d) return;
  const floor = app.dungeon.floor;
  const logIds = new Set((app.quests?.log || []).map((q) => q.id));
  const quests = d.quests.filter((q) => q.spots?.length && (poi.on.has("d:allquests") || (poi.on.has("d:myquests") && logIds.has(q.id))));
  const radius = Math.max(8, heatRadius(floor, size, scale) * 0.5);
  quests.forEach((q, i) => {
    const pts = q.spots.map((p) => onFloor(floor, p, d.floors)).filter(Boolean).map(([x, y]) => [...toScreen(x, y, size, scale), 1]);
    if (pts.length) {
      const color = OBJECTIVE_COLORS[i % OBJECTIVE_COLORS.length], hot = OBJECTIVE_HOT[i % OBJECTIVE_HOT.length];
      noteOverlay(q.name, color, hot);
      drawLit(q.name, color, () => renderHeat(pts, radius, heatRamp(color, hot)), [q.id]);
    }
  });
  const kills = new Set(runKills(d.key));
  const next = d.bosses.findIndex((b, i) => !b.rare && !kills.has(i + 1));
  d.bosses.forEach((b, i) => {
    if (b.rare ? !poi.on.has("d:rares") : !poi.on.has("d:bosses")) return;
    const at = onFloor(floor, b.pos, d.floors);
    if (!at) return;
    const [x, y] = toScreen(at[0], at[1], size, scale);
    const state = kills.has(i + 1) ? "down" : i === next ? "next" : "";
    drawBossMarker(x, y, i + 1, state, b.rare);
    const loot = b.loot.filter(isWished).map((id) => d.items[id]?.n).filter(Boolean);
    poi.drawn.push({ x, y, p: { name: b.name, cat: "boss", dungeonKey: d.key, bossIndex: i, levels: b.levels ?? null,
      sub: [b.rare ? "Rare spawn" : `Boss ${i + 1}`, state === "down" ? "down" : state === "next" ? "next up" : "", b.sub || "",
        loot.length ? `starred: ${loot.join(", ")}` : ""].filter(Boolean).join(", ") } });
  });
}
POI_LABEL.boss = "Click to open this boss in the journal";


function renderRun() {
  const r = app.run, box = $("runbox");
  const d = r?.inside && dungeon.byKey[r.key];
  let html = "";
  if (d) {
    const det = dungeonDetail(d.key);
    const wings = [d, ...(dungeon.byInstance?.[d.instance] || []).filter((w) => w.key !== d.key && runKills(w.key).length)];
    let down = 0, all = 0, next = null;
    for (const w of wings) {
      const x = w === d ? det : dungeonDetail(w.key), kills = runKills(w.key);
      if (!x) { down += kills.length; continue; }
      x.bosses.forEach((b, i) => {
        if (b.rare) return;
        all += 1;
        if (kills.includes(i + 1)) down += 1;
        else next ||= { b, x };
      });
    }
    const perHour = r.seconds > 120 ? Math.round(r.xp / r.seconds * 3600) : 0;
    const loot = (r.loot || []).map((id) => det?.items[id]).filter(Boolean)
      .map((it, n) => `<img src="${itemIcon(it)}" alt="${esc(it.n)}" data-tip="${r.loot[n]}" class="q${it.q}">`).join("");
    const starred = next ? starredLoot(next.b, next.x) : "";
    html = `<div class="run-head"><span class="with-help"><span class="next-label">${esc(d.name)}</span>${helpButton("run")}</span><span class="run-time">${hms(r.seconds)}</span></div>
      <div class="run-bosses">${down} of ${all || "?"} bosses${next ? `, next <b>${esc(next.b.name)}</b> <small>${mobLevelHtml(next.b.levels)}</small>` : down ? ", all down" : ""}</div>
      ${starred ? `<div class="run-starred">${starred}</div>` : ""}
      <div class="run-facts"><span>XP ${num(r.xp)}${perHour ? ` <small>(${num(perHour)} an hour)</small>` : ""}</span>
        <span>${money(r.money)}</span><span>${r.deaths} ${r.deaths === 1 ? "death" : "deaths"}</span></div>
      ${loot ? `<div class="run-loot">${loot}</div>` : ""}`;
  }
  box.hidden = !html;
  setHtml(box, html);
}

function partySection(help = "") {
  const members = app.group?.members || [];
  if (!members.length) return "";
  const rows = members.map((m) => {
    const color = CLASS_COLORS[m.className] || tint("class-other");
    const flags = [m.dead ? "Dead" : m.ghost ? "Ghost" : "", m.offline ? "Offline" : "", m.far && !m.offline ? "Far" : ""].filter(Boolean).join(", ");
    const hp = m.health ?? 100, power = m.power;
    return `<div class="party-row${m.dead || m.ghost || m.offline ? " out" : ""}">
      <span class="party-role" title="${esc(m.role || "no role")}">${ROLE_LETTER[m.role] || ""}</span>
      <span class="party-name" style="color:${color}">${esc(m.name)}${m.leader ? " <small>lead</small>" : ""}</span>
      <span class="party-level">${m.level}</span>
      <span class="party-bars"><span class="party-hp" style="width:${m.health == null ? 100 : hp}%;background:${hp < 35 ? tint("hp-red") : tint("hp-green")}"></span>
        ${power == null ? "" : `<span class="party-pw" style="width:${power}%;background:${POWER_COLOR[m.powerType] || tint("quality-rare")}"></span>`}</span>
      ${flags ? `<small class="party-flag">${flags}</small>` : ""}</div>`;
  }).join("");
  return `<div class="st-head">${stIcon(SECTION_ICONS.Party, "st-hic")}Party${help}</div>${rows}`;
}

function dungeonWarnings() {
  const n = (app.cap || []).length;
  if (n < 4) return [];
  const oldest = Math.max(...app.cap);
  const wait = Math.max(1, 60 - oldest);
  return [{ key: "instanceCap", level: n >= 5 ? "out" : "low",
    text: n >= 5 ? "Instance cap reached" : `${n} of 5 instances this hour`,
    detail: n >= 5 ? `The next one frees up in ${wait} min` : `One more new instance, then wait. The oldest frees up in ${wait} min` }];
}


on("start", function startDungeons() {
  setInterval(() => {
    const level = app.state?.level || 0;
    if (level && level !== dungeon.level) loadDungeons(level);
  }, 2000);
  loadDungeons(0);
});
