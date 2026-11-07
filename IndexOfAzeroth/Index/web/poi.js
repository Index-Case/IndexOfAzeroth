// The Index of Azeroth. Copyright 2026 Index Case <indexofazeroth@pm.me>. PolyForm Strict 1.0.0, see LICENSE.md.
"use strict";

const CLASS_ICONS = { 1: "warrior", 2: "paladin", 3: "hunter", 4: "rogue", 5: "priest", 7: "shaman", 8: "mage", 9: "warlock", 11: "druid" };
const POI_GROUPS = [
  ["Travel", [
    ["inn", "Inn", "inv_misc_rune_01", "where a hearthstone is set"],
    ["flight", "Flight master", null, ""],
    ["zeppelin", "Zeppelin master", "inv_misc_spyglass_02", ""],
    ["boat", "Boat dock", "creatureportrait_darkshoreboat", "where boats are boarded"],
  ]],
  ["Instances", [
    ["dungeon", "Dungeon entrance", "achievement_dungeon_classicdungeonmaster", "with its level range"],
    ["raid", "Raid entrance", "achievement_dungeon_classicraider", ""],
    ["battleground", "Battleground entrance", "achievement_bg_winwsg", "for the character's faction"],
  ]],
  ["Services", [
    ["bank", "Bank", "inv_misc_bag_10", ""],
    ["auction", "Auction house", "inv_misc_coin_01", ""],
    ["mailbox", "Mailbox", "inv_letter_15", ""],
    ["repair", "Repair", "inv_hammer_20", "armorers and weaponsmiths"],
    ["stable", "Stable master", "ability_hunter_beasttaming", ""],
    ["guild", "Guild master", "inv_shirt_guildtabard_01", "guild charters and tabards"],
    ["barber", "Barber", "inv_misc_comb_01", ""],
    ["battlemaster", "Battlemaster", null, ""],
    ["spirit", "Spirit healer", "spell_holy_resurrection", "where a ghost comes back to life"],
  ]],
  ["Vendors", [
    ["general", "General goods", "inv_misc_bag_10_green", "the basics"],
    ["food", "Food and drink", "inv_misc_food_19", ""],
    ["ammo", "Ammo", "inv_ammo_arrow_02", "arrows and bullets"],
    ["reagents", "Reagents", "inv_misc_dust_02", ""],
    ["poisons", "Poison supplies", "trade_brewpoison", ""],
    ["trade", "Trade supplies", "inv_misc_thread_01", "thread, dyes, vials, flux"],
    ["recipes", "Recipes", "inv_scroll_03", ""],
    ["bags", "Bags and quivers", "inv_misc_bag_07", ""],
    ["weaponvendor", "Weapons", "inv_axe_09", ""],
    ["armor", "Armor", "inv_chest_chain_05", ""],
  ]],
  ["Trainers", [
    ["class", "Class trainer", null, "for the character's class"],
    ["weapons", "Weapon master", "inv_sword_04", ""],
    ["pettrainer", "Pet trainer", "ability_hunter_beastcall", ""],
    ["riding", "Riding trainer", "ability_mount_ridinghorse", ""],
  ]],
  ["Profession trainers", [
    ["alchemy", "Alchemy", "trade_alchemy"], ["blacksmithing", "Blacksmithing", "trade_blacksmithing"],
    ["cooking", "Cooking", "inv_misc_food_15"], ["enchanting", "Enchanting", "trade_engraving"],
    ["engineering", "Engineering", "trade_engineering"], ["firstaid", "First Aid", "spell_holy_sealofsacrifice"],
    ["fishing", "Fishing", "trade_fishing"], ["herbalism", "Herbalism", "spell_nature_naturetouchgrow"],
    ["leatherworking", "Leatherworking", "inv_misc_armorkit_17"], ["mining", "Mining", "trade_mining"],
    ["skinning", "Skinning", "inv_misc_pelt_wolf_01"], ["tailoring", "Tailoring", "trade_tailoring"],
  ]],
];
const POI_LABEL = Object.fromEntries(POI_GROUPS.flatMap(([, cats]) => cats.map(([k, label]) => [k, label])));
const POI_PROFESSIONS = new Set(POI_GROUPS.find(([g]) => g === "Profession trainers")[1].map(([k]) => k));
const poiWhat = (cat) => `${POI_LABEL[cat].toLowerCase()}${POI_PROFESSIONS.has(cat) ? " trainer" : ""}`;
const kindGuidable = (cat, picked = false) => !!app.state?.pos && (cat !== "class" || !!kindDetail(cat, picked));
function kindGuideKey(cat, picked = false) {
  const can = kindGuidable(cat, picked);
  return html`<button class="mob-go" data-near="${cat}"${can ? "" : raw(" disabled")} title="${can
    ? `This starts the Navigation Guide to the nearest ${poiWhat(cat)} and copies the line for the in-game arrow`
    : "This key waits for the game to send where the character is"}">Guide me</button>`;
}
POI_LABEL.respawn = "Respawn timer. Click the timer to be guided to it";
POI_LABEL.node = "Gathering node. Click the node to be guided to it";
POI_LABEL.portal = "Dungeon portal. Click the portal to be guided to it";
POI_LABEL.guidestop = "A stop on the Navigation Guide's route";
POI_LABEL.guidenow = "Where the Navigation Guide heads now";
POI_LABEL.guideend = "Where the Navigation Guide ends";
POI_LABEL.epicmark = "Where the quest epic leads now";
const PORTAL_ICON = "spell_arcane_portalundercity";
const POI_SIZE = 22;

const poi = { on: new Set(), open: new Set(), data: null, key: "", loading: false, drawn: [], focused: true,
              pick: { class: null, weapons: null }, skills: null };
const kindDetail = (cat, picked = true) => (cat === "class" ? (picked && poi.pick.class) || app.status?.classId || null
  : cat === "weapons" && picked ? poi.pick.weapons : null);
function pickShown(p) {
  const want = kindDetail(p.cat);
  if (p.cat === "class") return p.detail === want;
  return !want || p.detail === want || (Array.isArray(p.detail) && p.detail.includes(want));
}
try { JSON.parse(localStorage.getItem("cc.poi") || "[]").forEach((c) => poi.on.add(c)); } catch (e) {   }
try { JSON.parse(localStorage.getItem("cc.poiOpen") || "[]").forEach((g) => poi.open.add(g)); } catch (e) {   }
try { poi.focused = localStorage.getItem("cc.poiFocused") !== "0"; } catch (e) {   }
const SIDES = ["Horde", "Alliance"];
const NO_SIDES = new Set(["Instances"]);
const SIDED_KINDS = new Set(POI_GROUPS.filter(([g]) => !NO_SIDES.has(g)).flatMap(([, cats]) => cats.map(([k]) => k)));
Object.assign(poi, { sides: new Set(SIDES), sidesFor: "" });
function syncSides() {
  const faction = app.status?.strs?.faction || "";
  if (!faction || faction === poi.sidesFor) return;
  Object.assign(poi, { sides: new Set([faction]), sidesFor: faction });
}
on("update", syncSides);
const kindShown = (cat) => poi.on.has(cat);
const sideShown = (p) => !SIDED_KINDS.has(p.cat) || !p.side || poi.sides.has(p.side);
const poisWanted = () => poi.on.size > 0;

const NEUTRAL_FLIGHT = "inv_misc_map02";
function poiIcon(cat, p = null) {
  const faction = p ? p.side : app.status?.strs?.faction;
  if (cat === "portal") return PORTAL_ICON;
  if (cat === "flight") {
    if (p && !p.side) return NEUTRAL_FLIGHT;
    return faction === "Horde" ? "ability_mount_wyvern_01" : "ability_mount_gryphon_01";
  }
  if (cat === "battlemaster") return faction === "Horde" ? "inv_bannerpvp_01" : "inv_bannerpvp_02";
  if (cat === "class") return `classicon_${CLASS_ICONS[p ? p.detail : kindDetail("class")] || "warrior"}`;
  if (cat === "gameguide") return "inv_misc_map_01";
  if (cat === "corpse") return "spell_holy_resurrection";
  if (cat === "rare" || cat === "pin") return "inv_misc_bone_humanskull_01";
  if (cat === "respawn") return "spell_holy_borrowedtime";
  for (const [, cats] of POI_GROUPS) for (const [k, , icon] of cats) if (k === cat) return icon;
  return "inv_misc_questionmark";
}



const poiMenu = $("poi-menu"), poiButton = $("btn-poi");

function buildPoiMenu() {
  if (app.dungeon) return buildDungeonMenu($("poi-list"));
  const className = app.status?.className, asked = poiAsks();
  if (poi.open.has("more:weapons")) askSkills();
  const note = poisWanted() && app.state?.map && asked.key !== poi.key
    ? html`<p class="menu-note">${askNote(asked.urls, { what: "the places", again: () => { refreshPois(); buildPoiMenu(); } })}</p>` : "";
  const sideBox = (side) => {
    const name = side === "Horde" ? word("page.places.horde") : word("page.places.alliance");
    return html`<label class="poi-side" title="${word("page.places.side.tip", { side: name })}"><input type="checkbox"
      data-side="${side}"${poi.sides.has(side) ? " checked" : ""}><img src="${crestSrc(side.toLowerCase())}" alt="${name}"></label>`;
  };
  $("poi-list").innerHTML = html`<div class="poi-all"><button data-all="1">All</button><button data-all="0">None</button>
    <label class="poi-focus" title="When this box is ticked, the zone in the middle of the map shows its places. When the box is unticked, every zone on the map in view shows the picked places, even zoomed out to a continent or the world"><input type="checkbox" data-focused="1"${poi.focused ? " checked" : ""}> Focused</label>${
    SIDES.map(sideBox)}</div>${note}${
    POI_GROUPS.map(([group, cats]) => {
      const on = cats.filter(([k]) => poi.on.has(k)).length, open = poi.open.has(group);
      const rows = open ? cats.map(([key, label, , note]) => [
        html`<label class="poi-cat"><input type="checkbox" value="${key}"${poi.on.has(key) ? " checked" : ""}>
          <img src="/icon/${poiIcon(key)}.jpg" alt=""> ${label}${pickedName(key, className)}${morePlus(key)}
          ${note && key !== "class" ? html`<small>${note}</small>` : ""}${travelKey(key)}${kindGuideKey(key, true)}</label>`,
        poi.open.has(`more:${key}`) ? pickRows(key) : ""]) : [];
      return html`<div class="poi-group${open ? " open" : ""}">
        <input type="checkbox" data-group="${group}" title="This shows or hides all of ${group}"${on === cats.length ? " checked" : ""}>
        <button class="poi-fold" data-fold="${group}" aria-expanded="${open}">${group}
          <span class="poi-on">${on ? `${on} of ${cats.length}` : ""}</span></button></div>${rows}`;
    })}`;
  poiMenu.querySelectorAll("input[data-group]").forEach((box) => {
    const cats = POI_GROUPS.find(([g]) => g === box.dataset.group)[1];
    const on = cats.filter(([k]) => poi.on.has(k)).length;
    box.indeterminate = on > 0 && on < cats.length;
  });
}

const PICK_KINDS = new Set(["class", "weapons"]);
function pickedName(key, className) {
  const id = kindDetail(key), name = key === "class" ? (poi.pick.class ? CLASS_NAMES[id] : className) : key === "weapons" ? poi.skills?.[id]?.n : "";
  return name ? ` (${name})` : "";
}
const morePlus = (key) => (PICK_KINDS.has(key) ? html`<button class="fold-plus poi-more" data-more="${key}" aria-expanded="${
  String(poi.open.has(`more:${key}`))}" title="${word(`page.places.more.${key}`)}"></button>` : "");
function pickRows(key) {
  const row = (value, img, name, on, note = "") => html`<label class="poi-pick"><input type="radio" name="poi-pick-${key}"
    data-pick="${key}" value="${value}"${on ? " checked" : ""}>${img ? html`<img src="${img}" alt="">` : ""} ${name}${
    note ? html`<small>${note}</small>` : ""}</label>`;
  if (key === "class") {
    const own = app.status?.classId, ids = Object.keys(CLASS_NAMES).map(Number);
    const order = [...ids.filter((id) => id === own), ...ids.filter((id) => id !== own).sort((a, b) => CLASS_NAMES[a].localeCompare(CLASS_NAMES[b]))];
    return order.map((id) => row(id, `/icon/classicon_${CLASS_ICONS[id]}.jpg`, CLASS_NAMES[id], id === kindDetail("class"),
      id === own ? word("page.places.pick.yours") : ""));
  }
  if (!poi.skills) return "";
  const skills = Object.entries(poi.skills).sort(([, a], [, b]) => a.n.localeCompare(b.n));
  return [row("", "", word("page.places.pick.every"), !poi.pick.weapons),
    ...skills.map(([id, s]) => row(id, s.icon ? `/fileicon/${s.icon}.jpg` : "", s.n, +id === poi.pick.weapons))];
}

function askSkills() {
  if (poi.skills) return;
  getJson("/api/weaponskills", { share: true })?.then((s) => { poi.skills = s; if (!poiMenu.hidden) buildPoiMenu(); }, () => {});
}

function syncPoiButton() {
  const n = [...poi.on].filter((k) => k.startsWith("d:") === !!app.dungeon).length;
  $("poi-count").textContent = n ? `(${n})` : "";
  poiButton.setAttribute("aria-pressed", String(n > 0));
}

function savePoi() {
  try { localStorage.setItem("cc.poi", JSON.stringify([...poi.on])); } catch (e) {   }
  syncPoiButton();
  refreshPois();
}

const togglePoiMenu = dropdown(poiButton, poiMenu, "p", () => { buildPoiMenu(); $("poi-tip").hidden = true; },
  { el: $("poi-bar"), title: "Places", help: "poi" });

function poiMenuClicked(e) {
  const routes = e.target.closest("button[data-routes]");
  if (routes) {
    e.preventDefault();
    toggleTravel(routes.dataset.routes);
    return buildPoiMenu();
  }
  const near = e.target.closest("button[data-near]");
  if (near) {
    e.preventDefault();
    return guideToKind(near.dataset.near, {}, kindDetail(near.dataset.near));
  }
  const more = e.target.closest("button[data-more]");
  if (more) {
    e.preventDefault();
    return toggleOpen(`more:${more.dataset.more}`);
  }
  const fold = e.target.closest("button[data-fold]");
  if (fold) return toggleOpen(fold.dataset.fold);
  const all = e.target.closest("button[data-all]");
  if (!all) return;
  const keys = app.dungeon ? DPOI.map(([k]) => k) : POI_GROUPS.flatMap(([, cats]) => cats.map(([k]) => k));
  keys.forEach((k) => poi.on.delete(k));
  if (all.dataset.all === "1") keys.forEach((k) => poi.on.add(k));
  savePoi();
  buildPoiMenu();
}
poiMenu.addEventListener("click", poiMenuClicked);
function toggleOpen(g) {
  if (poi.open.has(g)) poi.open.delete(g); else poi.open.add(g);
  try { localStorage.setItem("cc.poiOpen", JSON.stringify([...poi.open])); } catch (err) {   }
  buildPoiMenu();
}
function poiMenuChanged(e) {
  const box = e.target;
  if (box.dataset.side) {
    if (box.checked) poi.sides.add(box.dataset.side); else poi.sides.delete(box.dataset.side);
    refreshTravel();
    return redraw();
  }
  if (box.dataset.pick) {
    const key = box.dataset.pick, value = box.value ? +box.value : null;
    poi.pick[key] = key === "class" && value === app.status?.classId ? null : value;
    poi.on.add(key);
    savePoi();
    redraw();
    return buildPoiMenu();
  }
  if (box.dataset.focused) {
    poi.focused = box.checked;
    try { localStorage.setItem("cc.poiFocused", poi.focused ? "1" : "0"); } catch (err) {   }
    poi.key = "";
    return refreshPois();
  }
  if (box.dataset.group) {
    const cats = POI_GROUPS.find(([g]) => g === box.dataset.group)[1];
    cats.forEach(([k]) => (box.checked ? poi.on.add(k) : poi.on.delete(k)));
  } else if (box.checked) poi.on.add(box.value); else poi.on.delete(box.value);
  savePoi();
  buildPoiMenu();
}
poiMenu.addEventListener("change", poiMenuChanged);
on("start", syncPoiButton);


function poiMaps() {
  if (poi.focused || app.displayMap == null) return [zoneInView()];
  if (app.displayMap !== WORLD_MAP) return [app.displayMap];
  return Object.entries(app.maps).filter(([, m]) => m.type === 2 && m.parent === WORLD_MAP).map(([id]) => +id);
}

function poiAsks() {
  const maps = poiMaps().filter((m) => m != null), faction = encodeURIComponent(app.status?.strs?.faction || "");
  return { key: `${maps.join(",")}|${faction}`, urls: maps.map((m) => `/api/poi?map=${m}&faction=${faction}`) };
}
function refreshPois() {
  const s = app.state;
  syncPoiButton();
  if (!s?.map || !poisWanted() || app.dungeon) return;
  const { key, urls } = poiAsks();
  if (key === poi.key || poi.loading) return;
  const asks = urls.map((url) => getJson(url, { share: true }));
  if (asks.some((a) => !a)) return;
  poi.loading = true;
  const shown = () => { if (!poiMenu.hidden) buildPoiMenu(); };
  Promise.all(asks).then((sets) => { poi.data = sets; poi.key = key; shown(); }, shown).finally(() => { poi.loading = false; });
}


const POI_GAP = 3;
function poiSpots(size, scale) {
  const want = new Set(poiMaps()), out = [];
  if (!poi.data || !poisWanted()) return out;
  const half = POI_SIZE / 2;
  const caveView = app.indoor && !app.indoorZone;
  for (const d of poi.data) {
    if (!want.has(d.map)) continue;
    for (const p of d.pois) {
      const shown = p.cat === "portal" ? !caveView && (kindShown("dungeon") || kindShown("raid")) : kindShown(p.cat);
      if (!shown || !pickShown(p) || !sideShown(p)) continue;
      const [x, y] = toScreen(p.x, p.y, size, scale, d.map);
      if (x < -half || y < -half || x > W + half || y > H + half) continue;
      out.push({ x, y, p, map: d.map });
    }
  }
  return out;
}

function groupSpots(spots, reach = POI_SIZE + 4 + POI_GAP) {
  const groups = [], cells = new Map(), cell = (x, y) => `${Math.floor(x / reach)},${Math.floor(y / reach)}`;
  for (const s of spots) {
    const cx = Math.floor(s.x / reach), cy = Math.floor(s.y / reach);
    let home = null;
    for (let i = -1; i <= 1 && !home; i++) {
      for (let j = -1; j <= 1 && !home; j++) {
        home = (cells.get(`${cx + i},${cy + j}`) || []).find((g) => Math.abs(g[0].x - s.x) < reach && Math.abs(g[0].y - s.y) < reach);
      }
    }
    if (home) { home.push(s); continue; }
    const g = [s], key = cell(s.x, s.y);
    groups.push(g);
    if (!cells.has(key)) cells.set(key, []);
    cells.get(key).push(g);
  }
  return groups;
}

function groupKinds(places) {
  const n = new Map();
  for (const p of places) n.set(p.cat, (n.get(p.cat) || 0) + 1);
  return [...n].sort((a, b) => b[1] - a[1]);
}

const poiGlow = (p) => (p.cat === "flight" || p.foe ? SIDE_TINTS[p.side] || null : null);

const TOP_KINDS = new Set(["flight", "zeppelin", "boat"]);
function drawPois(s, size, scale) {
  if (app.dungeon) return;
  const spots = poiSpots(size, scale);
  const rest = spots.filter((d) => !TOP_KINDS.has(d.p.cat)), top = spots.filter((d) => TOP_KINDS.has(d.p.cat));
  for (const g of [...groupSpots(rest), ...groupSpots(top)]) {
    const { x, y, map } = g[0];
    if (g.length === 1) {
      drawPoiIcon(x, y, iconImage(poiIcon(g[0].p.cat, g[0].p)), poiGlow(g[0].p));
      poi.drawn.push(g[0]);
      continue;
    }
    const places = g.map((d) => d.p), kinds = groupKinds(places), glows = new Set(places.map(poiGlow));
    drawPoiGroup(x, y, iconImage(poiIcon(kinds[0][0], places.find((q) => q.cat === kinds[0][0]))), places.length, glows.size === 1 ? [...glows][0] : null);
    poi.drawn.push({ x, y, map, p: { cat: "group", name: `${places.length} places`, x: g[0].p.x, y: g[0].p.y, group: places } });
  }
}

function zoomIntoGroup(hit) {
  if (!hit.p.group || app.view.zoom >= MAX_ZOOM) return false;
  setFollow(false);
  zoomBy(2, hit.x, hit.y);
  return true;
}

function drawPoiGroup(x, y, img, count, glow) {
  const half = POI_SIZE / 2;
  ctx.fillStyle = tint("black");
  ctx.fillRect(x - half + 2, y - half - 6, POI_SIZE + 4, POI_SIZE + 4);
  ctx.strokeStyle = tint("bronze");
  ctx.lineWidth = 1;
  ctx.strokeRect(x - half + 2.5, y - half - 5.5, POI_SIZE + 3, POI_SIZE + 3);
  drawPoiIcon(x, y, img, glow);
  const text = String(count);
  ctx.save();
  ctx.font = "bold 11px sans-serif";
  const w = Math.max(14, ctx.measureText(text).width + 6), bx = x + half - w / 2 + 3, by = y + half - 4;
  ctx.fillStyle = tint("black");
  ctx.fillRect(bx - w / 2, by - 7, w, 14);
  ctx.strokeStyle = tint("bronze");
  ctx.strokeRect(bx - w / 2 + 0.5, by - 6.5, w - 1, 13);
  ctx.fillStyle = tint("ivory");
  ctx.textAlign = "center";
  ctx.textBaseline = "middle";
  ctx.fillText(text, bx, by + 0.5);
  ctx.restore();
}

const GLOW_COATS = 3;
function drawPoiIcon(x, y, img, glow = null) {
  const half = POI_SIZE / 2;
  ctx.save();
  ctx.shadowColor = glow ? tint(glow) : tint("poi-glow", 0.65);
  ctx.shadowBlur = glow ? 7 : 6;
  ctx.fillStyle = tint("black");
  for (let coat = glow ? GLOW_COATS : 1; coat > 0; coat--) ctx.fillRect(x - half - 2, y - half - 2, POI_SIZE + 4, POI_SIZE + 4);
  ctx.restore();
  ctx.strokeStyle = tint("bronze");
  ctx.lineWidth = 1;
  ctx.strokeRect(x - half - 1.5, y - half - 1.5, POI_SIZE + 3, POI_SIZE + 3);
  if (img.complete && img.naturalWidth) ctx.drawImage(img, x - half, y - half, POI_SIZE, POI_SIZE);
}

function drawIndoorPortals(s, size, scale) {
  const i = app.indoor, w = app.maps[s.map]?.world;
  if (!i?.portals?.length || app.indoorZone || app.dungeon || !w) return;
  for (const pt of i.portals) {
    const [fx, fy] = toFrac(w, pt.n, pt.w), [gx, gy] = toFrac(w, pt.walk[0], pt.walk[1]);
    const [x, y] = toScreen(fx, fy, size, scale, s.map);
    if (x < -POI_SIZE || y < -POI_SIZE || x > W + POI_SIZE || y > H + POI_SIZE) continue;
    drawPoiIcon(x, y, iconImage(PORTAL_ICON));
    poi.drawn.push({ x, y, map: s.map, p: { cat: "portal", name: `${pt.dungeon} portal`, sub: "The way in ends here. Walk into the portal",
                                            x: fx, y: fy, gx, gy, z: pt.walk[2] } });
  }
}

function noteMark(x, y, p) {
  poi.drawn.push({ x, y, p, tipOnly: true });
}

function spotAt(mx, my, click = false) {
  let best = null, bestD = POI_SIZE;
  for (const d of poi.drawn) {
    const dist = Math.hypot(d.x - mx, d.y - my);
    const over = best && dist < POI_SIZE / 2 && TOP_KINDS.has(d.p.cat);
    if ((dist < bestD || over) && !(click && d.tipOnly)) { best = d; bestD = dist; }
  }
  return best;
}

function spotTip(p, place = "") {
  if (p.rare) return rareTip(p);
  if (p.group) return groupTip(p.group);
  const line = "levels" in p ? html`${mobLevelHtml(p.levels)}${p.sub ? `, ${p.sub}` : ""}` : p.sub;
  const kind = p.label || POI_LABEL[p.cat] || p.cat;
  const foe = p.foe ? html`<br><small>${foeWords(p)}</small>` : "";
  if (place) return html`<b>${place}</b><small>${kind}</small><br><small class="tip-flavour">${p.name}${p.sub ? `, ${p.sub}` : ""}</small>${foe}`;
  return html`<b>${p.name}</b>${line ? html`<small>${line}</small><br>` : ""}${p.cat === "node" ? raw(nodeTip(p)) : ""}<small>${kind}</small>${foe}`;
}

const foeWords = (p) => (p.side ? `This NPC belongs to the ${p.side} and attacks you, so it won't serve you.`
  : "This NPC attacks you, so it won't serve you.");

const GROUP_NAMES = 8;
function groupTip(places) {
  const kinds = groupKinds(places).map(([k, n]) => `${n} ${POI_LABEL[k] || k}`).join(", ");
  const names = places.slice(0, GROUP_NAMES).map((p) => html`<br><small>${p.name}, ${POI_LABEL[p.cat] || p.cat}${p.foe ? ` (${p.side || "hostile"})` : ""}</small>`);
  const more = places.length > GROUP_NAMES ? html`<br><small>and ${places.length - GROUP_NAMES} more</small>` : "";
  return html`<b>${places.length} places here</b><small>${kinds}</small>${names}${more}<br><small class="tip-flavour">Click the group to zoom in on its places.</small>`;
}

const tip = $("poi-tip");
function mapTip(e) {
  const r = canvas.getBoundingClientRect(), mx = e.clientX - r.left, my = e.clientY - r.top;
  const best = spotAt(mx, my);
  const danger = !best ? planLineTipAt(mx, my) || trickyTipAt(mx, my) || easyTipAt(mx, my) || dangerTipAt(mx, my) : null;
  const zone = !best && !danger ? zoneTip() : "";
  if (!best && !danger && !zone) { tip.hidden = true; return; }
  tip.innerHTML = danger || zone || spotTip(best.p, travelPlace(best));
  tip.hidden = false;
  const at = tipPlace({ x: mx, y: my }, tip.offsetWidth, tip.offsetHeight, { left: 0, top: 0, right: W, bottom: H });
  tip.style.left = `${at.x}px`;
  tip.style.top = `${at.y}px`;
}
canvas.addEventListener("pointermove", mapTip);
canvas.addEventListener("pointerleave", () => { tip.hidden = true; });
