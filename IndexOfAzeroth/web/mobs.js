// The Index of Azeroth. Copyright 2026 Index Case <indexofazeroth@pm.me>. PolyForm Strict 1.0.0, see LICENSE.md.
"use strict";

const RARE_COLORS = [tint("rare-red"), tint("rare-silver"), tint("rare-teal"), tint("rare-indigo"), tint("rare-lime"), tint("rare-pink"),
  tint("rare-copper"), tint("rare-lilac"), tint("rare-steel"), tint("rare-olive"), tint("rare-orange"), tint("rare-aqua")];
const RARE_HOT = [tint("rare-red-hot"), tint("white"), tint("rare-teal-hot"), tint("rare-indigo-hot"), tint("rare-lime-hot"),
  tint("rare-pink-hot"), tint("rare-copper-hot"), tint("rare-lilac-hot"), tint("rare-steel-hot"), tint("rare-olive-hot"),
  tint("rare-orange-hot"), tint("rare-aqua-hot")];

const mobs = { data: null, map: null, on: [], open: new Set(), hover: null };
try { mobs.on = JSON.parse(localStorage.getItem("cc.rares") || "[]"); } catch (e) {   }
keptOr("cc.mobsOpen", ["Rares"]).forEach((g) => mobs.open.add(g));

const mobMenu = $("mob-menu"), mobButton = $("btn-mobs");

function rareStyle(id) {
  const i = mobs.on.indexOf(id);
  if (i < 0) return null;
  return { color: RARE_COLORS[i % RARE_COLORS.length], hot: RARE_HOT[i % RARE_HOT.length], rings: Math.floor(i / RARE_COLORS.length) % 2 === 1 };
}

function saveRares() {
  try { localStorage.setItem("cc.rares", JSON.stringify(mobs.on)); } catch (e) {   }
  syncMobButton();
}

function syncMobButton() {
  let n;
  if (app.dungeon) n = poi.on.has("d:rares") ? dungeonRares().length : 0;
  else {
    const here = new Set((mobs.data?.rares || []).map((r) => r.id));
    n = mobs.on.filter((id) => here.has(id)).length;
  }
  $("mob-count").textContent = n ? `(${n})` : "";
  mobButton.setAttribute("aria-pressed", String(n > 0));
}
const dungeonRares = () => (dungeon.detail[app.dungeon?.key]?.bosses || []).filter((b) => b.rare);


const raresMap = () => shownMap(zoneInView(app.state?.realMap ?? app.state?.map));
function refreshMobs() {
  syncMobButton();
  const map = app.dungeon ? null : raresMap();
  if (!map || map === mobs.map) return;
  getJson(`/api/rares?map=${map}`, { key: "rares" })?.then((d) => {
    mobs.data = d;
    mobs.map = map;
    syncMobButton();
    if (!mobMenu.hidden) buildMobMenu();
  }, () => { if (!mobMenu.hidden) buildMobMenu(); });
}

const lootIcons = (r, d, max = 30) => r.loot.slice(0, max).filter((id) => d.items[id])
  .map((id) => html`<img src="/icon/${d.items[id].icon}.jpg" alt="" class="q${d.items[id].q}" data-tip="${id}">`);
function lootLine(r, d, max) {
  const icons = lootIcons(r, d, max);
  return html`<div class="mob-drops">${icons.length ? icons : html`<span class="muted">No drops recorded</span>`}</div>`;
}
const rareLine = (r) => [mobLevelText(r.levels), r.kind].filter(Boolean).join(", ");
const rareMob = (r) => ({ id: r.id, name: r.name, where: "rares" });
const rareHead = (r) => html`<b>${r.name}</b><small>${mobLevelHtml(r.levels, rareMob(r))}${r.kind ? `, ${r.kind}` : ""}</small>`;


function layOutMobMenu() {
  $("mob-list").innerHTML = html`${finderHtml()}<div class="mob-scroll"><div id="npc-found"></div><div id="mob-rest"></div></div>
    <div class="mob-loot" id="mob-loot" hidden></div>`;
}

function buildMobMenu() {
  if (app.dungeon) return buildDungeonMobs();
  const d = mobs.map === raresMap() ? mobs.data : null;
  const rares = d?.rares || [];
  const open = mobs.open.has("Rares");
  const shown = rares.filter((r) => mobs.on.includes(r.id)).length;
  const rows = open ? rares.map((r) => {
    const st = rareStyle(r.id);
    const sw = st ? html`<span class="mob-swatch${st.rings ? " rings" : ""}" style="--c:${st.color}"></span>` : html`<span class="mob-swatch off"></span>`;
    return html`<label class="mob-row" data-rare="${r.id}"><input type="checkbox" value="${r.id}"${st ? " checked" : ""}>${sw}
      <span class="mob-num">${st ? mobs.on.indexOf(r.id) + 1 : ""}</span>
      <span class="mob-name">${r.name}<small>${mobLevelHtml(r.levels, rareMob(r))}${r.loot.length ? `, ${r.loot.length} drops` : ""}</small></span>
      <button class="mob-go" data-go="${r.id}" title="This starts the Navigation Guide to ${r.name} and copies the line for the in-game arrow">Guide me</button></label>`;
  }) : [];
  const rest = $("mob-rest");
  rest.innerHTML = html`<div class="poi-all"><button data-all="1">All</button><button data-all="0">None</button></div>
    <div class="poi-group${open ? " open" : ""}">
      <input type="checkbox" data-group="Rares" title="This shows or hides all of this zone's rares"${rares.length && shown === rares.length ? " checked" : ""}>
      <button class="poi-fold" data-fold="Rares" aria-expanded="${open}">Rares
      <span class="poi-on">${shown ? `${shown} of ${rares.length}` : rares.length ? `${rares.length} here` : ""}</span></button></div>
    ${rows.length ? rows : open ? html`<p class="menu-note">${askNote("rares", { have: !!d, none: "No rares are known in this zone.",
      what: "the zone's rares", again: () => { refreshMobs(); buildMobMenu(); } })}</p>` : ""}
    <p class="menu-note">Hover over a rare to see its drops.</p>
    ${respawnMenu()}`;
  const group = rest.querySelector("input[data-group]");
  if (group) group.indeterminate = shown > 0 && shown < rares.length;
}

function buildDungeonMobs() {
  const d = dungeon.detail[app.dungeon.key], rares = dungeonRares();
  const rows = rares.map((b) => html`<div class="mob-row"><span class="mob-name">${b.name}<small>${mobLevelHtml(b.levels)}${b.sub ? `, ${b.sub}` : ""}</small></span></div>`);
  $("mob-rest").innerHTML = html`<div class="layer-group">${d?.name || "Dungeon"}</div>
    ${rares.length ? html`<label class="mob-row"><input type="checkbox" data-drares="1"${poi.on.has("d:rares") ? " checked" : ""}>
      <span class="mob-name">Show the dungeon's rares on the map<small>${rares.length}</small></span></label>${rows}`
      : html`<p class="menu-note">${askNote(`/api/dungeon/${app.dungeon.key}`, { have: !!d, none: "No rares are known in this dungeon.",
        what: "the dungeon's rares", again: detailAgain(app.dungeon.key) })}</p>`}
    <p class="menu-note">This box is the same switch as Rare spawns under Places. Outside the dungeon, this menu shows the zone's rares again.</p>
    ${respawnMenu()}`;
}

function setAllRares(on) {
  const here = (mobs.data?.rares || []).map((r) => r.id);
  mobs.on = mobs.on.filter((id) => !here.includes(id));
  if (on) mobs.on.push(...here);
  saveRares();
  buildMobMenu();
}

const toggleMobMenu = dropdown(mobButton, mobMenu, "m", () => { buildMobMenu(); $("poi-tip").hidden = true; focusFinder(); },
  { el: $("mob-bar"), title: "NPCs, Monsters and Rares", help: "mobs" });

mobMenu.addEventListener("click", (e) => {
  if (npcsClicked(e)) return;
  const go = e.target.closest("button[data-go]");
  if (go) {
    e.preventDefault();
    const r = mobs.data?.rares.find((x) => x.id === +go.dataset.go);
    if (r) guideToRare(r);
    return;
  }
  const fold = e.target.closest("button[data-fold]");
  if (fold) {
    const name = fold.dataset.fold;
    if (mobs.open.has(name)) mobs.open.delete(name); else mobs.open.add(name);
    try { localStorage.setItem("cc.mobsOpen", JSON.stringify([...mobs.open])); } catch (err) {   }
    return buildMobMenu();
  }
  const all = e.target.closest("button[data-all]");
  if (all) setAllRares(all.dataset.all === "1");
});
function mobMenuChanged(e) {
  if (e.target.dataset.group) return setAllRares(e.target.checked);
  if (e.target.dataset.drares) {
    if (e.target.checked) poi.on.add("d:rares"); else poi.on.delete("d:rares");
    savePoi();
    syncMobButton();
    return buildMobMenu();
  }
  const id = +e.target.value;
  if (!id) return;
  mobs.on = mobs.on.filter((x) => x !== id);
  if (e.target.checked) mobs.on.push(id);
  saveRares();
  buildMobMenu();
}
mobMenu.addEventListener("change", mobMenuChanged);
function showRareLoot(e) {
  const row = e.target.closest(".mob-row");
  const panel = $("mob-loot");
  if (!row || !panel || row.dataset.rare === mobs.hover) return;
  mobs.hover = row.dataset.rare;
  const r = mobs.data?.rares.find((x) => x.id === +row.dataset.rare);
  if (!r) return;
  panel.innerHTML = html`${rareHead(r)}${lootLine(r, mobs.data)}`;
  panel.hidden = false;
  placeRareLoot(panel, row);
}
mobMenu.addEventListener("mouseover", showRareLoot);
function placeRareLoot(panel, row) {
  const menu = mobMenu.getBoundingClientRect(), r = row.getBoundingClientRect();
  const at = tipPlace({ left: menu.left, right: menu.right, top: r.top, bottom: r.bottom }, panel.offsetWidth, panel.offsetHeight,
    inWindow(), { gap: 0, x: "middle", y: "level" });
  panel.style.left = `${Math.round(at.x - menu.left - mobMenu.clientLeft)}px`;
  panel.style.top = `${Math.round(at.y - menu.top - mobMenu.clientTop)}px`;
}
mobMenu.addEventListener("mouseleave", () => { mobs.hover = null; const p = $("mob-loot"); if (p) p.hidden = true; });


function guideToRare(r) {
  const s = app.state, w = app.maps[mobs.map]?.world;
  if (!w) return;
  const at = toWorld(w, r.at[0], r.at[1]);
  guideTo({ todoId: null, name: r.name, sub: rareLine(r), cat: "rare", zone: app.maps[mobs.map].name, instance: app.maps[mobs.map].instance,
    wx: at.n, wy: at.w });
}

function drawRareMarker(x, y, n, st) {
  drawRingMarker(x, y, { r: 10, edge: 2, fill: tint("rare-mark"), ring: st.color, width: 2.5, text: n, font: `12px ${MARK_FONT}` });
}

const WALK_HEAT = 0.15;
function walkHeat(pts, radius) {
  const out = [], step = Math.max(2, radius / 2);
  pts.forEach(([x, y], i) => {
    if (i === 0) return out.push([x, y, WALK_HEAT]);
    const [px, py] = pts[i - 1], n = Math.max(1, Math.round(Math.hypot(x - px, y - py) / step));
    for (let k = 1; k <= n; k++) out.push([px + (x - px) * k / n, py + (y - py) * k / n, WALK_HEAT]);
  });
  return out;
}

function drawMobs(s, size, scale) {
  const d = mobs.data;
  if (!d || app.dungeon || !app.state || raresMap() !== mobs.map) return;
  const shown = d.rares.filter((r) => mobs.on.includes(r.id));
  if (!shown.length) return;
  const radius = Math.max(8, heatRadius(mobs.map, size, scale) * 0.7);
  for (const r of shown) {
    const st = rareStyle(r.id);
    const walks = (r.walks || []).map((w) => w.map(([x, y]) => toScreen(x, y, size, scale, mobs.map)));
    const pts = r.spots.map(([x, y]) => [...toScreen(x, y, size, scale, mobs.map), 1]);
    noteOverlay(r.name, st.color, st.hot, st.rings ? "rings" : "");
    drawLit(r.name, st.color, () => {
      if (st.rings) {
        for (const [x, y] of pts) {
          ctx.beginPath(); ctx.arc(x, y, Math.max(6, radius * 0.45), 0, Math.PI * 2);
          ctx.lineWidth = 4; ctx.strokeStyle = tint("black", 0.6); ctx.stroke();
          ctx.lineWidth = 2.5; ctx.strokeStyle = st.color; ctx.stroke();
        }
      } else {
        renderHeat([...pts, ...walks.flatMap((w) => walkHeat(w, radius))], radius, heatRamp(st.color, st.hot));
      }
      for (const w of walks) drawPatrol(w, st.color);
    });
  }
  for (const r of shown) {
    const st = rareStyle(r.id);
    const [x, y] = toScreen(r.at[0], r.at[1], size, scale, mobs.map);
    drawLit(r.name, st.color, () => drawRareMarker(x, y, mobs.on.indexOf(r.id) + 1, st));
    if (overlayOff(r.name)) continue;
    poi.drawn.push({ x, y, map: mobs.map, p: { name: r.name, sub: rareLine(r), cat: "rare", x: r.at[0], y: r.at[1], rare: r } });
  }
}

function rareTip(p) {
  const r = p.rare;
  return html`${rareHead(r)}${lootLine(r, mobs.data, 24)}<small>Click the marker to start the guide to ${r.name} and copy the line for the in-game arrow</small>`;
}

on("start", function startMobs() {
  layOutMobMenu();
  startFinder(mobMenu);
  setInterval(refreshMobs, 1000);
  syncMobButton();
});
on("start", () => startMarket());
