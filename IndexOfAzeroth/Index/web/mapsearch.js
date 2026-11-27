// The Index of Azeroth. Copyright 2026 Index Case <indexofazeroth@pm.me>. PolyForm Strict 1.0.0, see LICENSE.md.
"use strict";

const SEARCH_MOST = 30;
const FIND_ICONS = { zone: "inv_misc_map_01", continent: "inv_misc_map_01", place: "ability_townwatch", spot: "ability_hunter_pathfinding" };
const SMALL_WORDS = new Set(["a", "an", "and", "at", "for", "in", "of", "on", "the", "to"]);

const mapSearch = { text: "", open: false, found: [], built: null };


const fold = (s) => String(s).toLowerCase().replace(/['\u2019]/g, "").replace(/\s+/g, " ").trim();
const zoneMap = (m) => !!m?.world && ((m.type === 3 && !!m.parent && !m.tilesOnly) || m.type === 2);

function knownWords(names) {
  const known = new Map();
  for (const name of names) {
    for (const w of String(name).split(/\s+/)) if (/^[A-Z]/.test(w) && !known.has(w.toLowerCase())) known.set(w.toLowerCase(), w);
  }
  return known;
}
function nameCase(text, known) {
  return String(text).split(/\s+/).filter(Boolean).map((w, k) => {
    const low = w.toLowerCase();
    if (k && SMALL_WORDS.has(low)) return low;
    return known.get(low) ?? low.charAt(0).toUpperCase() + low.slice(1);
  }).join(" ");
}

function doorFind(d, maps = app.maps) {
  const e = yourSide(d.entrances).find((x) => maps[x.map]?.world);
  if (!e) return null;
  const m = maps[e.map];
  return { name: d.name, kind: d.kind, zone: m.name, key: d.key, at: { inst: m.instance, ...toWorld(m.world, e.x / 100, e.y / 100) } };
}

function searchPlaces() {
  const maps = app.maps, places = app.detailView?.places || {}, dungeons = dungeon.list || [], stops = travel.data?.flight?.stops || [];
  const from = [maps, places, dungeons, stops], b = mapSearch.built;
  if (b && b.from.every((v, k) => v === from[k])) return b.finds;
  const finds = [], mapName = (id) => maps[id]?.name || "";
  const zoneOf = (at) => mapName(zoneNamed(at));
  for (const [id, m] of Object.entries(maps)) {
    if (!zoneMap(m)) continue;
    const w = m.world;
    finds.push({ name: m.name, kind: m.type === 2 ? "continent" : "zone", zone: m.type === 2 ? "" : mapName(continentOf(+id, maps)), map: +id,
                 at: { inst: m.instance, n: (w.top + w.bottom) / 2, w: (w.left + w.right) / 2 } });
  }
  const doors = new Set();
  for (const d of dungeons) {
    const p = doorFind(d, maps);
    if (!p) continue;
    finds.push(p);
    doors.add(`${fold(d.name)}|${p.zone}`);
  }
  for (const s of stops) {
    const at = { inst: s.inst, n: s.n, w: s.w };
    finds.push({ name: s.name, kind: "flight", zone: zoneOf(at), side: s.side ?? null, at });
  }
  const known = knownWords(finds.map((f) => f.name));
  for (const [id, lettering] of Object.entries(places)) {
    if (!maps[id]?.world) continue;
    for (const place of lettering.names || []) {
      const box = placeBox(place), at = fracToWorld(+id, (box[0] + box[2]) / 2, (box[1] + box[3]) / 2);
      const name = nameCase(place.lines.map((l) => l.text).join(" "), known), zone = mapName(id);
      if (at && !doors.has(`${fold(name)}|${zone}`)) finds.push({ name, kind: "place", zone, at });
    }
  }
  mapSearch.built = { from, finds };
  return finds;
}

function ranked(finds, typed, me) {
  const q = fold(typed);
  if (!q) return [];
  const far = (p) => (me && p.at?.inst === me.inst ? Math.hypot(p.at.n - me.n, p.at.w - me.w) : Infinity);
  const scored = [];
  for (const p of finds) {
    const name = fold(p.name), lot = name.startsWith(q) ? 0 : name.includes(q) ? 1 : -1;
    if (lot >= 0) scored.push({ p, lot, far: far(p) });
  }
  scored.sort((a, b) => a.lot - b.lot || (a.far === b.far ? 0 : a.far < b.far ? -1 : 1) || a.p.name.localeCompare(b.p.name));
  return scored.map((s) => s.p);
}


const WAY_LINE = /^\s*(?:\/way\s+)?(?:#(\d+)\s+)?(.*?)\s*(\d{1,3}(?:\.\d+)?)(?:\s*,\s*|\s+)(\d{1,3}(?:\.\d+)?)(?:\s+(.*?))?\s*$/i;
function zoneNamedAs(text, maps = app.maps) {
  const q = fold(text);
  const hit = Object.entries(maps).find(([, m]) => zoneMap(m) && fold(m.name) === q);
  return hit ? +hit[0] : null;
}
function parseSpot(text, shown) {
  const m = WAY_LINE.exec(text);
  if (!m) return null;
  const [, id, zone, x, y, note = ""] = m;
  const map = id ? +id : zone ? zoneNamedAs(zone) : shown;
  if (map == null || !zoneMap(app.maps[map]) || +x > 100 || +y > 100) return null;
  return { map, x: +x, y: +y, note };
}
function spotFind(spot) {
  const m = app.maps[spot.map], at = fracToWorld(spot.map, spot.x / 100, spot.y / 100);
  return { name: spotName(m.name, spot.x, spot.y), kind: "spot", zone: m.name, note: spot.note, map: spot.map, at };
}
function findsFor(text) {
  const spot = parseSpot(text, zoneInView());
  if (spot) return [spotFind(spot)];
  return ranked(searchPlaces(), text, playerWorld(true)).slice(0, SEARCH_MOST);
}


const findIcon = (p) => FIND_ICONS[p.kind] || poiIcon(p.kind, p);
function findUnder(p) {
  const kind = wordsOf("page.search.kind")[p.kind];
  if (p.kind === "spot") return p.note || kind;
  return p.zone ? word("page.search.under", { kind, zone: p.zone }) : kind;
}
const DOORS = new Set(["dungeon", "raid", "battleground"]);
function searchRow(p, i) {
  const fill = { name: p.name };
  const go = DOORS.has(p.kind) ? word("page.search.guide.entrance", fill) : word("page.search.guide", fill);
  return html`<div class="ms-row" data-find="${i}" title="${word("page.search.show", fill)}"><img class="ms-icon" src="/icon/${findIcon(p)}.jpg" alt=""><span class="ms-name">${p.name}<small>${findUnder(p)}</small></span><button type="button" class="mob-go" data-find-go="${i}" title="${go}">${word("page.search.guide.key")}</button></div>`;
}
const searchFoundHtml = () => (mapSearch.found.length ? html`${mapSearch.found.map(searchRow)}` : html`<p class="ms-none">${word("page.search.none")}</p>`);
const LIST_GAP_PX = 3;
function placeList(list) {
  const r = $("map-find").getBoundingClientRect(), right = columnSide() === "right";
  list.style.left = right ? "auto" : `${Math.round(r.left)}px`;
  list.style.right = right ? `${Math.round(document.documentElement.clientWidth - r.right)}px` : "auto";
  list.style.top = `${Math.round(r.bottom + LIST_GAP_PX)}px`;
}
function renderSearch() {
  const list = $("map-found"), shown = list.matches(":popover-open");
  $("map-search").classList.toggle("open", mapSearch.open);
  setHtml(list, mapSearch.open ? searchFoundHtml() : "");
  if (mapSearch.open) {
    placeList(list);
    if (!shown) list.showPopover();
  } else if (shown) list.hidePopover();
}

function searchTyped(text) {
  mapSearch.text = text;
  mapSearch.found = text.trim() ? findsFor(text) : [];
  mapSearch.open = !!text.trim();
  renderSearch();
}
function closeSearch() {
  mapSearch.open = false;
  renderSearch();
}


function showPlace(p) {
  if (p.kind === "zone") return showZone(p.map);
  if (p.kind === "continent") {
    setFollow(false);
    enterContinent("zoom", p.map);
    [app.view.cx, app.view.cy] = [0.5, 0.5];
    return viewMoved();
  }
  const id = app.maps[p.map]?.type === 3 ? p.map : zoneNamed(p.at);
  const zone = id == null ? null : shownMap(id), f = zone != null && worldToFrac(zone, p.at);
  if (!f) return;
  showSpot(id, zone, f);
}
function guidePlace(p) {
  const { inst, n, w } = p.at;
  if (p.kind === "spot") return spotGuide({ name: p.name, zone: p.zone, inst, wx: n, wy: w, sub: p.note || undefined });
  if (DOORS.has(p.kind)) return guideToDungeon(p.key, p.name);
  const sub = p.kind === "flight" ? word("page.search.kind.flight") : p.zone;
  guideTo({ todoId: null, name: p.name, sub, cat: p.kind === "flight" ? "flight" : "gameguide", zone: p.map != null ? p.name : p.zone,
            instance: inst, wx: n, wy: w });
}
function searchClicked(e) {
  const b = e.target.closest("[data-find-go]"), row = !b && e.target.closest("[data-find]");
  const p = mapSearch.found[+(b ? b.dataset.findGo : row?.dataset.find)];
  if (!p) return false;
  if (b) guidePlace(p); else showPlace(p);
  closeSearch();
  return true;
}


function startSearch(form) {
  const box = $("map-find");
  form.addEventListener("input", () => searchTyped(box.value));
  form.addEventListener("submit", (e) => {
    e.preventDefault();
    const p = mapSearch.found[0];
    if (!p) return;
    showPlace(p);
    closeSearch();
  });
  form.addEventListener("click", (e) => searchClicked(e));
  box.addEventListener("focus", () => { if (!mapSearch.open && box.value.trim()) searchTyped(box.value); });
  document.addEventListener("pointerdown", (e) => { if (mapSearch.open && !form.contains(e.target)) closeSearch(); }, true);
  closable(LAYER.menu, () => mapSearch.open, closeSearch);
}
on("start", () => startSearch($("map-search")));

if (typeof module === "object") {
  module.exports = { SEARCH_MOST, FIND_ICONS, SMALL_WORDS, mapSearch, fold, zoneMap, knownWords, nameCase, searchPlaces, ranked, WAY_LINE,
                     doorFind, zoneNamedAs, parseSpot, spotFind, findsFor, findIcon, findUnder, searchRow, searchFoundHtml, LIST_GAP_PX, placeList, renderSearch, searchTyped,
                     closeSearch, showPlace, guidePlace, searchClicked, startSearch };
}
