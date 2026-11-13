// The Index of Azeroth. Copyright 2026 Index Case <indexofazeroth@pm.me>. PolyForm Strict 1.0.0, see LICENSE.md.
"use strict";

const LAYER_HEAT = {
  xp: { base: tint("kill-crimson"), hot: tint("bone-white"), title: word("page.layers.name.xp"), gain: 3 },
  gold: { base: tint("gold-layer"), hot: tint("glint"), title: word("page.layers.name.gold"),
          bands: [tint("gold-band-1"), tint("gold-band-2"), tint("gold-band-3"), tint("gold-band-4"), tint("gold-band-5"),
                  tint("gold-band-6"), tint("gold-band-7")] },
  skinning: { base: tint("skin-teal"), hot: tint("skin-teal-hot"), title: word("page.layers.name.skinning") },
};
const LAYER_DOTS = {
  mining: { color: tint(LOOP_LOOKS.mining), hot: tint("mining-hot"), title: word("page.layers.name.mining"), icon: "trade_mining" },
  herbalism: { color: tint(LOOP_LOOKS.herbalism), hot: tint("herbalism-hot"), title: word("page.layers.name.herbalism"), icon: "spell_nature_naturetouchgrow" },
  fishing: { color: tint(LOOP_LOOKS.fishing), hot: tint("fishing-hot"), title: word("page.layers.name.fishing"), icon: "trade_fishing" },
  treasure: { color: tint(LOOP_LOOKS.treasure), hot: tint("glint"), title: word("page.layers.name.treasure"), icon: "inv_misc_ornatebox" },
};
const GATHER_SKILL = { mining: "miningSkill", herbalism: "herbalismSkill", fishing: "fishingSkill" };
const NODE_ICON = 14;
const TOP_ZONES = 6;
const ZONE_VALUE = { xp: "xp", gold: "gold", skinning: "skin" };

const layers = { on: new Set(), off: new Set(), only: {}, open: new Set(), data: null, key: "" };
try { layers.goldAll = localStorage.getItem("cc.goldAll") === "1"; } catch (e) { layers.goldAll = false; }
const goldAll = () => layers.goldAll && layers.on.has("gold");
try { layers.ahPrices = localStorage.getItem("cc.ahPrices") === "1"; } catch (e) { layers.ahPrices = false; }
const goldAh = () => (layers.ahPrices && layers.on.has("gold") ? 1 : 0);
try { layers.daredevil = localStorage.getItem("cc.daredevil") === "1"; } catch (e) { layers.daredevil = false; }
try { layers.gatherAll = localStorage.getItem("cc.gatherAll") === "1"; } catch (e) { layers.gatherAll = false; }
try { layers.aoe = localStorage.getItem("cc.aoe") === "1"; } catch (e) { layers.aoe = false; }
const AOE_SPECS = { 8: { tree: 3, from: 22, name: word("page.layers.aoe.mage") }, 2: { tree: 2, from: 40, name: word("page.layers.aoe.paladin") } };
const AOE_MOST = { 8: 6, 2: 4 };
const aoeSpec = () => { const a = AOE_SPECS[app.status?.classId]; return !!a && spec() === a.tree && (app.state?.level || 0) >= a.from; };
const aoeMost = () => AOE_MOST[app.status?.classId] || 3;
const WARN = `<svg viewBox="0 0 16 16" width="13" height="13" aria-hidden="true"><path d="M8 1.5L15 14H1z" fill="${tint("caution")}" stroke="${tint("black")}" stroke-width="1"/><path d="M8 6v4" stroke="${tint("black")}" stroke-width="1.8"/><circle cx="8" cy="12" r="1" fill="${tint("black")}"/></svg>`;
const layerTitle = (layer, style) => layer === "gold" && goldAll() ? word("page.layers.name.gold-all") : style.title;

try {
  JSON.parse(localStorage.getItem("cc.layers") || "[]").forEach((l) => layers.on.add(l));
  JSON.parse(localStorage.getItem("cc.layerTypesOff") || "[]").forEach((t) => layers.off.add(t));
  for (const [layer, names] of Object.entries(JSON.parse(localStorage.getItem("cc.layerTypesOnly") || "{}"))) layers.only[layer] = new Set(names);
  JSON.parse(localStorage.getItem("cc.layersOpen") || "[]").forEach((g) => layers.open.add(g));
} catch (e) {   }

function saveLayers() {
  try {
    localStorage.setItem("cc.layers", JSON.stringify([...layers.on]));
    localStorage.setItem("cc.layerTypesOff", JSON.stringify([...layers.off]));
    localStorage.setItem("cc.layerTypesOnly", JSON.stringify(Object.fromEntries(Object.entries(layers.only).map(([l, s]) => [l, [...s]]))));
    localStorage.setItem("cc.layersOpen", JSON.stringify([...layers.open]));
    localStorage.setItem("cc.goldAll", layers.goldAll ? "1" : "0");
    localStorage.setItem("cc.daredevil", layers.daredevil ? "1" : "0");
    localStorage.setItem("cc.gatherAll", layers.gatherAll ? "1" : "0");
    localStorage.setItem("cc.aoe", layers.aoe ? "1" : "0");
    localStorage.setItem("cc.ahPrices", layers.ahPrices ? "1" : "0");
  } catch (e) {   }
}


const menu = $("layer-menu"), menuButton = $("btn-layers");

const LAYER_ROWS = wordsOf("page.layers.row");
const GATHER_NOTES = wordsOf("page.layers.note");
const typeKey = (layer, name) => `${layer}:${name}`;
const typeShown = (layer, name) => (layers.only[layer] ? layers.only[layer].has(name) : !layers.off.has(typeKey(layer, name)));

layers.leatherKinds = null;
layers.leatherZones = {};
const leatherZonesUrl = (inst) => `/api/leatherzones?instance=${inst}&faction=${encodeURIComponent(app.status?.strs?.faction || "")}`;
function refreshLeathers() {
  if (!layers.on.has("skinning") && menu.hidden) return;
  if (!layers.leatherKinds) {
    getJson("/api/leatherkinds")?.then((k) => { layers.leatherKinds = k; layers.key = ""; layers.zonesFor = {}; refreshLayers(); zonesIn(); }, zonesIn);
  }
  if (!zoomedOut()) return;
  for (const url of viewInstances().map(leatherZonesUrl)) {
    if (!layers.leatherZones[url]) getJson(url)?.then((z) => { layers.leatherZones[url] = z; zonesIn(); }, zonesIn);
  }
}
function leatherFilter() {
  if (!layers.only.skinning && ![...layers.off].some((t) => t.startsWith("skinning:"))) return [];
  return Object.entries(layers.leatherKinds || {}).filter(([name]) => typeShown("skinning", name)).map(([name, k]) => ({ name, id: k.id }));
}
const leatherIds = (list = leatherFilter()) => list.map((l) => l.id).join(",");
const LEATHERS_NAMED = 3;
const leatherWords = (list) => (list.length && list.length <= LEATHERS_NAMED ? andList(list.map((l) => l.name)) : "");
function leatherTypes() {
  if (!zoomedOut()) return (layers.data?.leathers || []).map((t) => ({ ...t, can: layers.gatherAll || t.can }));
  const kinds = layers.leatherKinds || {}, zones = new Set(searchArea().zones), count = new Map(), skill = skinFor();
  for (const url of viewInstances().map(leatherZonesUrl)) {
    for (const z of layers.leatherZones[url] || []) {
      if (!zones.has(z.map)) continue;
      for (const [name, [n, need]] of Object.entries(z.leathers)) {
        const had = count.get(name);
        count.set(name, had ? [had[0] + n, Math.min(had[1], need)] : [n, need]);
      }
    }
  }
  return [...count].map(([name, [n, need]]) => ({ name, id: kinds[name]?.id, icon: kinds[name]?.icon, skill: need, count: n, can: skill >= need }));
}
function areaTypes(layer) {
  if (layer === "skinning") return leatherTypes();
  if (!zoomedOut()) return (layers.data?.dots?.[layer]?.types || []).map((t) => ({ ...t, can: layers.gatherAll || t.can }));
  const kinds = layers.nodeKinds?.[layer] || {}, skill = app.status?.nums?.[GATHER_SKILL[layer]] || 0;
  const zones = new Set(searchArea().zones), count = new Map();
  for (const inst of viewInstances()) {
    for (const z of layers.nodeZones[inst] || []) {
      if (!zones.has(z.map)) continue;
      for (const [name, n] of Object.entries(z.spots?.[layer] || {})) count.set(name, (count.get(name) || 0) + n);
    }
  }
  return [...count].map(([name, n]) => {
    const k = kinds[name] || {};
    return { name, icon: k.icon, skill: k.skill || 0, count: n, can: layers.gatherAll || !k.skill || skill >= k.skill };
  });
}

function typesNote(none, layer) {
  const out = zoomedOut(), insts = viewInstances(), skin = layer === "skinning";
  const zoned = skin ? ["/api/leatherkinds", ...insts.map(leatherZonesUrl)] : ["/api/nodekinds", ...insts.map((i) => `/api/nodezones?instance=${i}`)];
  const zonesIn = skin ? !!layers.leatherKinds && insts.every((i) => layers.leatherZones[leatherZonesUrl(i)])
    : !!layers.nodeKinds && insts.every((i) => layers.nodeZones[i]);
  return askNote(out ? zoned : "layers", {
    have: out ? zonesIn : !!layers.data, none,
    what: out ? word("page.layers.ask.area") : word("page.layers.ask.map"), again: layersAgain });
}
function layersAgain() {
  refreshLayers();
  updateLayers();
  zonesIn();
}

function buildLayerMenu() {
  const plain = (key) => `<label><input type="checkbox" value="${key}"${layers.on.has(key) ? " checked" : ""}> ${LAYER_HEAT[key].title} <small>${LAYER_ROWS[key]}</small></label>`;
  const group = (layer, title, whole) => {
    const types = areaTypes(layer).slice().sort((a, b) => (b.can - a.can) || a.skill - b.skill || a.name.localeCompare(b.name));
    const open = layers.open.has(layer), on = layers.on.has(layer);
    const shown = on ? types.filter((t) => typeShown(layer, t.name)).length : 0;
    const rows = open ? types.map((t) => `<label class="poi-cat layer-type${t.can ? "" : " dim"}">
        <input type="checkbox" data-type="${esc(typeKey(layer, t.name))}"${on && typeShown(layer, t.name) ? " checked" : ""}>
        <img src="/icon/${esc(t.icon || "inv_misc_questionmark")}.jpg" alt=""> ${esc(t.name)}
        <small>${num(t.count)}${t.can || !t.skill ? "" : `, ${word("page.layers.needs", { skill: t.skill })}`}</small></label>`).join("")
      || `<p class="menu-note">${typesNote(zoomedOut() ? word("page.layers.none.area") : word("page.layers.none.map"), layer)}</p>` : "";
    return `<div class="poi-group${open ? " open" : ""}">
        <input type="checkbox" data-layer="${layer}" title="${whole}"${on ? " checked" : ""}>
        <button class="poi-fold" data-fold="${layer}" aria-expanded="${open}">${title}
        <span class="poi-on">${on && types.length ? word("page.layers.shown", { n: shown, of: types.length })
          : types.length ? word("page.layers.here", { n: types.length }) : GATHER_NOTES[layer]}</span></button></div>${rows}`;
  };
  const whole = wordsOf("page.layers.whole");
  const groups = Object.entries(LAYER_DOTS).map(([layer, style]) => group(layer, style.title, whole[layer])).join("");
  const skinning = group("skinning", LAYER_HEAT.skinning.title, whole.skinning);
  const all = `<label class="layer-sub daredevil"><input type="checkbox" data-gold-all="1"${layers.goldAll ? " checked" : ""}> ${SKULL} ${word("page.layers.all")}
    <small>${word("page.layers.all.gold")}</small></label>`;
  const gatherAll = `<label class="layer-sub daredevil"><input type="checkbox" data-gather-all="1"${layers.gatherAll ? " checked" : ""}> ${SKULL} ${word("page.layers.all")}
    <small>${word("page.layers.all.gather")}</small></label>`;
  $("layer-list").innerHTML = `<div class="poi-all"><button data-layers-all="1">${word("page.layers.menu.all")}</button><button data-layers-all="0">${word("page.layers.menu.none")}</button></div>
    <div class="layer-group">${word("page.layers.group.grinding")}</div>${plain("xp")}${plain("gold")}${all}
    <div class="layer-group">${word("page.layers.group.gathering")}</div>${gatherAll}${skinning}${groups}${emit("layerMenu").join("")}`;
  menu.querySelectorAll("input[data-layer]").forEach((box) => {
    const layer = box.dataset.layer, types = areaTypes(layer);
    const off = types.filter((t) => !typeShown(layer, t.name)).length;
    box.indeterminate = layers.on.has(layer) && off > 0 && off < types.length;
  });
}

function syncMenu() {
  if (!menu.hidden) buildLayerMenu();
  $("layer-count").textContent = layers.on.size ? `(${layers.on.size})` : "";
  menuButton.setAttribute("aria-pressed", String(layers.on.size > 0));
}

const toggleMenu = dropdown(menuButton, menu, "l", () => { buildLayerMenu(); refreshLayers(); refreshNodeZones(); refreshLeathers(); },
  { el: $("layer-bar"), title: word("page.layers.title"), help: "layers" });

function layersChanged() {
  saveLayers();
  syncMenu();
  layers.key = "";
  refreshLayers();
  renderLegend();
}

menu.addEventListener("click", (e) => {
  const every = e.target.closest("button[data-layers-all]");
  if (every) return setAllLayers(every.dataset.layersAll === "1");
  const fold = e.target.closest("button[data-fold]");
  if (!fold) return;
  const g = fold.dataset.fold;
  if (layers.open.has(g)) layers.open.delete(g); else layers.open.add(g);
  saveLayers();
  buildLayerMenu();
});
menu.addEventListener("change", layerMenuChange);
function layerMenuChange(e) {
  const box = e.target;
  if (box.dataset.goldAll) {
    layers.goldAll = box.checked;
    if (box.checked) layers.on.add("gold");
  } else if (box.dataset.gatherAll) {
    layers.gatherAll = box.checked;
  } else if (box.dataset.type) {
    const [layer] = box.dataset.type.split(":"), name = box.dataset.type.slice(layer.length + 1);
    if (box.checked) {
      layers.off.delete(box.dataset.type);
      if (!layers.on.has(layer)) {
        layers.on.add(layer);
        layers.only[layer] = new Set([name]);
      } else layers.only[layer]?.add(name);
    } else if (layers.only[layer]) {
      layers.only[layer].delete(name);
      if (!layers.only[layer].size) { delete layers.only[layer]; layers.on.delete(layer); }
    } else {
      layers.off.add(box.dataset.type);
      if (areaTypes(layer).every((t) => !typeShown(layer, t.name))) layers.on.delete(layer);
    }
  } else {
    const layer = box.dataset.layer || box.value;
    if (box.checked) wholeLayerOn(layer);
    else layers.on.delete(layer);
  }
  layersChanged();
}
function setAllLayers(on) {
  const keys = [...Object.keys(LAYER_HEAT), ...Object.keys(LAYER_DOTS)];
  if (on) keys.forEach((k) => wholeLayerOn(k));
  else { keys.forEach((k) => layers.on.delete(k)); for (const k of Object.keys(layers.only)) delete layers.only[k]; }
  menu.querySelectorAll?.("input[data-own]").forEach((b) => {
    if (b.checked !== on) { b.checked = on; b.dispatchEvent(new Event("change", { bubbles: true })); }
  });
  layersChanged();
}
function wholeLayerOn(layer) {
  layers.on.add(layer);
  delete layers.only[layer];
  for (const t of [...layers.off]) if (t.startsWith(`${layer}:`)) layers.off.delete(t);
}
function showGatherLayer(layer) {
  wholeLayerOn(layer);
  layersChanged();
  showToast(word("page.layers.on-map", { layer: LAYER_DOTS[layer]?.title || LAYER_HEAT[layer]?.title || layer,
    key: layer === "skinning" ? word("page.layers.key.skin") : word("page.layers.key.gather") }));
}
on("start", function startLayers() { syncMenu(); renderLegend(); });


const layersMap = () => shownMap(zoneInView());
function refreshLayers() {
  const s = app.state, st = app.status;
  if (!s || !s.map || (!layers.on.size && menu.hidden)) return;
  const n = st?.nums || {}, any = layers.gatherAll ? 300 : null;
  const params = new URLSearchParams({
    map: layersMap(), level: s.level || 1, faction: st?.strs?.faction || "",
    mining: any ?? (n.miningSkill || 0), herbalism: any ?? (n.herbalismSkill || 0), skinning: any ?? (n.skinningSkill || 0),
    fishing: any ?? (n.fishingSkill || 0), all: goldAll() ? 1 : 0, ah: goldAh(),
    skinned: n.skinningSkill || 0,
  });
  const leathers = leatherIds();
  if (leathers) params.set("leathers", leathers);
  const key = params.toString();
  if (key === layers.key) return;
  getJson(`/api/layers?${key}`, { key: "layers" })?.then((data) => {
    layers.data = data;
    layers.key = key;
    renderLegend();
    if (!menu.hidden) buildLayerMenu();
  }, zonesIn);
}


function drawNode(x, y, icon, color, can) {
  const h = NODE_ICON / 2, img = iconImage(icon || "inv_misc_questionmark");
  ctx.fillStyle = tint("black");
  ctx.fillRect(x - h - 2, y - h - 2, NODE_ICON + 4, NODE_ICON + 4);
  ctx.fillStyle = can ? color : tint("node-locked");
  ctx.fillRect(x - h - 1, y - h - 1, NODE_ICON + 2, NODE_ICON + 2);
  if (img.complete && img.naturalWidth) {
    const m = Math.round(img.naturalWidth * 0.07), n = img.naturalWidth - 2 * m;
    ctx.drawImage(img, m, m, n, n, x - h, y - h, NODE_ICON, NODE_ICON);
  }
  else { ctx.fillStyle = tint("ash"); ctx.fillRect(x - h, y - h, NODE_ICON, NODE_ICON); }
}

const CARD_STEP = 3;
function nodeStacks(dots, hidden) {
  const key = hidden.join();
  if (dots.stacks?.key === key) return dots.stacks.list;
  const at = new Map();
  for (const [x, y, t, chance = 1, up = 1] of dots.points) {
    if (hidden[t]) continue;
    const spot = at.get(`${x},${y}`);
    if (!spot) at.set(`${x},${y}`, { x, y, types: [t], chance: { [t]: chance }, up });
    else if (!spot.types.includes(t)) { spot.types.push(t); spot.chance[t] = chance; }
  }
  const rank = (t) => dots.types[t].can ? 1e4 + (dots.types[t].skill || 0) : -(dots.types[t].skill || 0);
  const list = [...at.values()];
  for (const spot of list) spot.types.sort((a, b) => rank(a) - rank(b));
  dots.stacks = { key, list };
  return list;
}
const oddsPct = (v) => `${Math.round(v * 100)}%`;
function nodeTip(p) {
  const stack = p.stack ? `<span class="tip-stack"><small>${word("page.layers.node.stack")}</small>${p.stack.map((s) =>
    `<span><img src="/icon/${esc(s.icon || "inv_misc_questionmark")}.jpg" alt="">${esc(s.name)} <b class="tip-odds">${oddsPct(s.chance)}</b>${s.needs ? ` <i>${esc(s.needs)}</i>` : ""}</span>`).join("")}</span>` : "";
  const up = p.up != null && p.up < 1 ? `<small>${word("page.layers.node.up", { pct: oddsPct(p.up) })}</small><br>` : "";
  return stack + up;
}


layers.zones = {};
layers.zonesFor = {};
layers.nodeZones = {};
const zoomedOut = () => app.view.world || (!!app.view.continent && app.detail.current === "low");
function viewInstances() {
  if (app.view.world) return [0, 1];
  const m = app.maps[app.displayMap];
  return m?.instance != null ? [m.instance] : [];
}
function zonesIn() {
  renderLegend();
  if (!menu.hidden) buildLayerMenu();
}
function refreshNodeZones() {
  if (!zoomedOut() || (!Object.keys(LAYER_DOTS).some((l) => layers.on.has(l)) && menu.hidden)) return;
  if (!layers.nodeKinds) getJson("/api/nodekinds")?.then((k) => { layers.nodeKinds = k; zonesIn(); }, zonesIn);
  for (const inst of viewInstances()) {
    if (!layers.nodeZones[inst]) getJson(`/api/nodezones?instance=${inst}`)?.then((z) => { layers.nodeZones[inst] = z; zonesIn(); }, zonesIn);
  }
}
const zoneNodeCount = (z, layer) => Object.entries(z.nodes?.[layer] || {}).reduce((sum, [name, n]) => sum + (typeShown(layer, name) ? n : 0), 0);

const TIP_KINDS = 3;
function zoneTip(id = app.hoverZone) {
  const m = app.maps[id];
  if (!m || !layers.on.size || !zoomedOut()) return "";
  const score = layers.zones[m.instance]?.find((z) => z.map === id), nodes = layers.nodeZones[m.instance]?.find((z) => z.map === id);
  const shown = (n, text) => (n > 0 ? text : `<span class="zero-text">${text}</span>`);
  const line = (swatch, title, text, more = "") => `<span class="tip-layer"><i style="background:${swatch}"></i><span>${esc(title)}: ${text}</span></span>${more}`;
  const lines = [];
  for (const [layer, style] of Object.entries(LAYER_HEAT)) {
    if (!layers.on.has(layer) || !layers.zones[m.instance]) continue;
    const n = score?.[ZONE_VALUE[layer]] || 0, up = score?.skinUp || 0;
    const beasts = shown(n, word("page.layers.tip.skin", { n: num(n) }));
    const text = layer === "xp" ? shown(n, word("page.layers.tip.xp", { n: num(n) })) : layer === "gold" ? shown(n, word("page.layers.tip.gold", { money: money(n) }))
      : layers.gatherAll ? word("page.layers.tip.skin.any", { text: beasts })
      : n ? `${beasts}, ${shown(up, word("page.layers.tip.raise", { n: num(up) }))}` : beasts;
    lines.push(line(`linear-gradient(135deg, ${style.base} 45%, ${style.hot})`, layerTitle(layer, style), text));
  }
  for (const [layer, style] of Object.entries(LAYER_DOTS)) {
    if (!layers.on.has(layer) || !layers.nodeZones[m.instance]) continue;
    const kinds = Object.entries(nodes?.spots?.[layer] || {}).filter(([name]) => typeShown(layer, name)).sort((a, b) => b[1] - a[1] || a[0].localeCompare(b[0]));
    const total = kinds.reduce((sum, [, n]) => sum + n, 0), up = nodes ? zoneNodeCount(nodes, layer) : 0;
    const list = kinds.slice(0, TIP_KINDS).map(([name, n]) => `${esc(name)} ${num(n)}`).join(", ");
    const named = kinds.length > TIP_KINDS ? word("page.layers.tip.kinds.more", { list, n: kinds.length - TIP_KINDS }) : list;
    lines.push(line(style.color, style.title, shown(total, word("page.layers.tip.nodes", { n: num(total) }))
      + (total ? `, ${word("page.layers.tip.up", { n: num(Math.max(1, Math.round(up))) })}` : ""),
      named ? `<small class="tip-kinds">${named}</small>` : ""));
  }
  if (!lines.length) return "";
  const range = m.levels ? ` <small style="color:${zoneThreat(m.levels)}">${zoneRangeText(m.levels)}</small>` : "";
  return `<b>${esc(m.name)}${range}</b>${lines.join("")}`;
}

const skinFor = () => (layers.gatherAll ? 300 : app.status?.nums?.skinningSkill || 0);
function refreshZoneScores() {
  const s = app.state;
  if (!s || !zoomedOut() || !Object.keys(LAYER_HEAT).some((l) => layers.on.has(l))) return;
  const mine = app.status?.nums?.skinningSkill || 0;
  const leathers = leatherIds(), only = leathers ? `&leathers=${leathers}` : "";
  const faction = app.status?.strs?.faction || "", want = `${s.level || 1}|${faction}|${goldAll() ? 1 : 0}|${skinFor()}|${goldAh()}|${mine}|${leathers}`;
  for (const inst of viewInstances()) {
    if (layers.zonesFor[inst] === want) continue;
    getJson(`/api/layerzones?instance=${inst}&level=${s.level || 1}&faction=${encodeURIComponent(faction)}&all=${goldAll() ? 1 : 0}&skin=${skinFor()}&ah=${goldAh()}&skinning=${mine}${only}`,
      { key: `layerzones:${inst}` })?.then((z) => { layers.zones[inst] = z; layers.zonesFor[inst] = want; renderLegend(); }, renderLegend);
  }
}
function zoneGlows(size, scale, book = layers.zones) {
  const out = [];
  for (const inst of viewInstances()) {
    for (const z of book[inst] || []) {
      const c = worldToFrac(app.displayMap, { inst, n: z.n, w: z.w });
      const e = worldToFrac(app.displayMap, { inst, n: z.n, w: z.w - z.rw * ZONE_FILL });
      const s = worldToFrac(app.displayMap, { inst, n: z.n - z.rn * ZONE_FILL, w: z.w });
      if (!c || !e || !s) continue;
      const [x, y] = toScreen(c[0], c[1], size, scale, app.displayMap), [ex, ey] = toScreen(e[0], e[1], size, scale, app.displayMap);
      const [sx, sy] = toScreen(s[0], s[1], size, scale, app.displayMap);
      const r = Math.max(6, Math.hypot(ex - x, ey - y)), r2 = Math.max(6, Math.hypot(sx - x, sy - y));
      out.push({ z, x, y, r: Math.max(r, r2), rx: r, ry: r2 });
    }
  }
  return out;
}
const layerRamp = (style) => style.bands ? bandRamp(style.bands) : heatRamp(style.base, style.hot);

function countedLit(have) {
  const seen = have.filter(([g]) => g.x >= 0 && g.y >= 0 && g.x <= W && g.y <= H).map(([, c]) => c);
  const among = seen.length ? seen : have.map(([, c]) => c), lo = Math.min(...among), hi = Math.max(...among);
  return have.map(([g, c]) => ({ g, v: hi > lo ? Math.min(1, Math.max(GATHER_GLOW_LEAST, GATHER_GLOW_LEAST + (1 - GATHER_GLOW_LEAST) * (c - lo) / (hi - lo))) : 1 }));
}

const ZONE_SHARED = [1, 1, 0.85, 0.75, 0.68];
const ZONE_GAIN = 1;
const ZONE_FILL = 0.75;
const ZONE_OPACITY = 0.78;
const GATHER_GLOW_LEAST = 0.1;
function drawZoneLayers(size, scale) {
  const on = (g) => g.x > -g.r && g.y > -g.r && g.x < W + g.r && g.y < H + g.r;
  const glows = [];
  const scores = zoneGlows(size, scale).filter(on);
  const piles = [];
  for (const layer of ["xp", "gold"]) {
    if (!layers.on.has(layer)) continue;
    if (layer === "gold" && coin.sprite) {
      const style = LAYER_HEAT.gold;
      piles.push({ title: layerTitle(layer, style), base: style.base, hot: style.hot, bands: style.bands, zones: coinPiles(scores) });
      continue;
    }
    const style = LAYER_HEAT[layer], top = Math.max(1, ...scores.map((g) => g.z[layer]));
    const lit = scores.filter((g) => g.z[layer] > 0).map((g) => ({ g, v: Math.max(0.12, g.z[layer] / top) }));
    if (lit.length) glows.push({ title: layerTitle(layer, style), base: style.base, hot: style.hot, bands: style.bands, ramp: boostRamp(layerRamp(style), ZONE_GAIN), lit });
  }
  if (layers.on.has("skinning")) {
    const style = LAYER_HEAT.skinning, lit = countedLit(scores.map((g) => [g, g.z.skin || 0]).filter(([, c]) => c > 0));
    if (lit.length) glows.push({ title: style.title, base: style.base, hot: style.hot, ramp: boostRamp(layerRamp(style), ZONE_GAIN), lit, shaped: true });
  }
  const counted = zoneGlows(size, scale, layers.nodeZones).filter(on);
  for (const [layer, style] of Object.entries(LAYER_DOTS)) {
    if (!layers.on.has(layer)) continue;
    const lit = countedLit(counted.map((g) => [g, zoneNodeCount(g.z, layer)]).filter(([, c]) => c > 0));
    if (lit.length) glows.push({ title: style.title, base: style.color, hot: style.hot, ramp: boostRamp(heatRamp(style.color, style.hot), ZONE_GAIN), lit, shaped: true });
  }
  for (const p of piles) {
    noteOverlay(p.title, p.base, p.hot, "", p.bands);
    if (!overlayOff(p.title)) layers.piles = p.zones;
  }
  const strength = ZONE_SHARED[Math.min(glows.length, ZONE_SHARED.length - 1)];
  const continent = app.maps[app.displayMap]?.type === 2;
  for (const g of glows) {
    noteOverlay(g.title, g.base, g.hot, "", g.bands);
    drawLayerGlow(g.title, g.base, () => {
      ctx.save();
      ctx.globalAlpha *= strength * ZONE_OPACITY;
      const rest = continent && g.shaped ? drawZoneShapes(g, size, scale) : g.lit;
      if (rest.length) renderHeat(rest.map(({ g: z, v }) => [z.x, z.y, v, z.rx, z.ry]), 20, g.ramp, zoneSprite());
      ctx.restore();
    });
  }
  drawLitZone(size, scale);
}

const COINS_PER_RANK = 3, COINS_A_STACK = 8, COIN_PX = 20, COIN_RISE = 3, COIN_TILT = 62;
const coin = { sprite: null, loading: false, canDraw: true };
function coinSprite() {
  if (coin.sprite || coin.loading || !coin.canDraw) return coin.sprite;
  const asked = loadModel("coin");
  if (!asked) return null;
  coin.loading = true;
  asked.then((m) => {
    try {
      const view = new ModelView(m, { yaw: 20, pitch: COIN_TILT });
      view.size(COIN_PX * 3, COIN_PX * 3);
      view.draw(0);
      const c = document.createElement("canvas");
      c.width = view.canvas.width; c.height = view.canvas.height;
      c.getContext("2d").drawImage(view.canvas, 0, 0);
      coin.sprite = c;
    } catch (e) {
      coin.canDraw = false;
    }
  }, () => {}).finally(() => { coin.loading = false; });
  return null;
}
function coinPiles(scores) {
  const seen = scores.filter((g) => g.z.gold > 0 && g.x >= 0 && g.y >= 0 && g.x <= W && g.y <= H)
    .sort((a, b) => a.z.gold - b.z.gold);
  return seen.map((g, i) => ({ x: g.x, y: g.y, coins: (i + 1) * COINS_PER_RANK, seed: g.z.map }));
}
layers.piles = null;
function drawPilesOnTop() {
  if (layers.piles && coin.sprite) drawCoinPiles(layers.piles);
  layers.piles = null;
}
function drawCoinPiles(zones) {
  const img = coin.sprite, w = COIN_PX, h = COIN_PX * img.height / img.width;
  const wobble = (a, b, c) => ((Math.imul(a * 73856093 ^ b * 19349663 ^ c * 83492791, 2654435761) >>> 0) % 5 - 2) / 2;
  for (const z of zones) {
    const stacks = Math.ceil(z.coins / COINS_A_STACK), spots = [];
    for (let k = 0; k < stacks; k++) {
      const turn = k * 2.39996, far = k ? w * 0.45 * Math.sqrt(k) : 0;
      spots.push({ x: z.x + Math.cos(turn) * far, y: z.y + Math.sin(turn) * far * 0.55, k });
    }
    spots.sort((a, b) => a.y - b.y);
    for (const sp of spots) {
      const n = Math.floor(z.coins / stacks) + (sp.k < z.coins % stacks ? 1 : 0);
      for (let i = 0; i < n; i++) {
        ctx.drawImage(img, sp.x - w / 2 + wobble(z.seed, sp.k, i), sp.y - h / 2 - i * COIN_RISE, w, h);
      }
    }
  }
}

const SHAPE_STEPS = 16;
const SHAPE_LIGHTEN = 0.35, SHAPE_FAINT = 0.35, SHAPE_FULL = 0.9;
function drawZoneShapes(glow, size, scale) {
  const v = app.view, spots = new Map(continentZones(app.displayMap, size).map((z) => [z.id, z])), rest = [];
  const base = hex(glow.base), hot = hex(glow.hot || glow.base), outer = ctx.globalAlpha;
  inMapSpace(size, scale, () => {
    for (const item of glow.lit) {
      const z = spots.get(item.g.z.map), d = Math.round(item.v * (SHAPE_STEPS - 1)) / (SHAPE_STEPS - 1);
      const rgb = tonedRgb(base.map((c, k) => Math.round(c + (hot[k] - c) * SHAPE_LIGHTEN * d)));
      const shape = z && zoneShape(z.id, rgb);
      if (!shape) { rest.push(item); continue; }
      paintGlow((g) => g.drawImage(shape, z.x0 * size.w, z.y0 * size.h, z.w * size.w, z.h * size.h),
        { alpha: outer * (SHAPE_FAINT + (SHAPE_FULL - SHAPE_FAINT) * d) });
    }
  });
  return rest;
}

function updateLayers() {
  const mode = zoomedOut() ? "zones" : "spots";
  if (layers.mode !== mode) { layers.mode = mode; renderLegend(); }
  refreshLeathers();
  if (mode !== "zones") return;
  refreshZoneScores();
  refreshNodeZones();
  if (layers.on.has("gold")) coinSprite();
}
on("update", updateLayers);

function drawLayerGlow(title, base, paint) {
  drawLit(title, base, () => {
    ctx.save();
    ctx.globalAlpha *= app.hotspotShare ?? 1;
    try { paint(); } finally { ctx.restore(); }
  });
}

function drawLayers(s, size, scale) {
  if (zoomedOut()) return drawZoneLayers(size, scale);
  const d = layers.data;
  if (!d || d.map !== layersMap() || !layers.on.size) return;
  const radius = heatRadius(d.map, size, scale);
  for (const [layer, style] of Object.entries(LAYER_HEAT)) {
    if (!layers.on.has(layer) || !d.heat[layer]?.length) continue;
    let pts = d.heat[layer].map(([x, y, w]) => [...toScreen(x, y, size, scale, d.map), w]);
    if ((d.heatRaw || []).includes(layer)) {
      const seen = pts.filter(([x, y]) => x > -radius && y > -radius && x < W + radius && y < H + radius);
      const top = Math.max(1, ...seen.map((p) => p[2]));
      pts = pts.map(([x, y, v]) => [x, y, v / top]);
    }
    pts = pts.map(([x, y, w]) => [x, y, Math.max(0.15, w)]);
    noteOverlay(layerTitle(layer, style), style.base, style.hot, "", style.bands);
    const ramp = style.gain ? boostRamp(layerRamp(style), style.gain) : layerRamp(style);
    drawLayerGlow(layerTitle(layer, style), style.base, () => renderHeat(pts, radius, ramp));
  }
  drawLitMob(d, size, scale);
  for (const [layer, style] of Object.entries(LAYER_DOTS)) {
    const dots = d.dots[layer];
    if (!layers.on.has(layer) || !dots?.points.length) continue;
    const hidden = dots.types.map((t) => !typeShown(layer, t.name));
    if (hidden.every(Boolean)) continue;
    noteOverlay(style.title, style.color, style.color, "dots");
    const needs = (type) => type.can || !type.skill ? "" : word("page.layers.needs", { skill: type.skill });
    drawLit(style.title, style.color, () => {
      const stacks = nodeStacks(dots, hidden);
      for (const pass of [false, true]) {
        for (const { x, y, types, chance, up } of stacks) {
          const top = dots.types[types[types.length - 1]];
          if (top.can !== pass) continue;
          const [sx, sy] = toScreen(x, y, size, scale, d.map), reach = (types.length - 1) * CARD_STEP;
          if (sx < -10 || sy < -10 - reach || sx > W + 10 + reach || sy > H + 10) continue;
          types.forEach((t, i) => {
            const step = (types.length - 1 - i) * CARD_STEP;
            drawNode(sx + step, sy - step, dots.types[t].icon, style.color, dots.types[t].can);
          });
          const p = { name: top.name, cat: "node", icon: top.icon, x, y, up, sub: `${style.title}${needs(top) ? `, ${needs(top)}` : ""}` };
          if (types.length > 1) {
            p.stack = types.map((t) => ({ name: dots.types[t].name, icon: dots.types[t].icon, needs: needs(dots.types[t]), chance: chance[t] })).reverse();
          }
          poi.drawn.push({ x: sx, y: sy, map: d.map, p });
        }
      }
    });
  }
}

const LIT_RING = 7;
function drawLitMob(d, size, scale) {
  if (!layers.lit?.startsWith("mob:")) return;
  const [, layer, ...name] = layers.lit.split(":");
  const mob = d.top?.[layer]?.find((e) => e.name === name.join(":"));
  if (!mob?.points) return;
  ctx.beginPath();
  for (const [x, y] of mob.points) {
    const [sx, sy] = toScreen(x, y, size, scale, d.map);
    if (sx < -LIT_RING || sy < -LIT_RING || sx > W + LIT_RING || sy > H + LIT_RING) continue;
    ctx.moveTo(sx + LIT_RING, sy);
    ctx.arc(sx, sy, LIT_RING, 0, Math.PI * 2);
  }
  ctx.lineWidth = 4; ctx.strokeStyle = tint("black"); ctx.stroke();
  ctx.lineWidth = 2; ctx.strokeStyle = LAYER_HEAT[layer].hot; ctx.stroke();
}
function drawLitZone(size, scale) {
  if (app.litZone == null || zoneLabelsOn()) return;
  const g = [...zoneGlows(size, scale), ...zoneGlows(size, scale, layers.nodeZones)].find((q) => q.z.map === app.litZone);
  if (!g) return;
  ctx.beginPath();
  ctx.ellipse(g.x, g.y, g.rx, g.ry, 0, 0, Math.PI * 2);
  ctx.lineWidth = 4; ctx.strokeStyle = tint("black"); ctx.stroke();
  ctx.lineWidth = 2; ctx.strokeStyle = ZONE_NAME; ctx.stroke();
  serifFont ||= getComputedStyle(document.documentElement).getPropertyValue("--serif").trim() || "Georgia, serif";
  ctx.font = `18px ${serifFont}`;
  ctx.textAlign = "center"; ctx.textBaseline = "middle"; ctx.lineJoin = "round";
  ctx.lineWidth = 4; ctx.strokeStyle = tint("black", 0.85); ctx.strokeText(g.z.name, g.x, g.y);
  ctx.fillStyle = ZONE_NAME; ctx.fillText(g.z.name, g.x, g.y);
  ctx.lineJoin = "miter";
}


function ahBox() {
  const note = ahNotice();
  return `<label class="lg-ah" title="${word("page.layers.ah.tip")}"><input type="checkbox" data-ah-prices="1"${layers.ahPrices ? " checked" : ""}><img src="/icon/inv_misc_coin_02.jpg" alt=""> ${word("page.layers.ah")}</label>${note ? `<span class="lg-ah-note">${esc(note)}</span>` : ""}`;
}

function renderLegend() {
  const d = layers.data, box = $("legend");
  if (!layers.on.size) { box.hidden = true; litAt(null); return; }
  const panes = [];
  let parts = [];
  const pane = () => { if (parts.length) panes.push(`<div class="lg-pane">${parts.join("")}</div>`); parts = []; };
  const head = (title, swatch) => `<div class="lg-head"><span class="lg-swatch" style="background:${swatch}"></span>${title}</div>`;
  const rowHtml = (a, b, dim, attrs = "") => `<div class="lg-row${dim ? " dim" : ""}"${attrs}><span>${a}</span><span>${b}</span></div>`;
  const rowsLit = new Set();
  const zoneRow = (z, value) => {
    const levels = app.maps[z.map]?.levels;
    const range = levels ? ` <small style="color:${zoneThreat(levels)}">${zoneRangeText(levels)}</small>` : "";
    rowsLit.add(`zone:${z.map}`);
    return rowHtml(`${esc(z.name)}${range}`, value, false,
      ` data-lit="zone:${z.map}" role="button" tabindex="0" title="${word("page.layers.lit.zone", { zone: esc(z.name) })}"`);
  };
  const forLeather = leatherWords(leatherFilter());
  const notAoe = layers.aoe && !aoeSpec()
    ? `<span class="lg-warn" title="${word("page.layers.aoe.warn", { n: aoeMost(), list: word("page.layers.and", {
      list: word("page.layers.aoe.spec", { name: AOE_SPECS[8].name, level: AOE_SPECS[8].from }),
      last: word("page.layers.aoe.spec", { name: AOE_SPECS[2].name, level: AOE_SPECS[2].from }) }) })}">${WARN}</span>` : "";
  const skinTip = layers.gatherAll ? word("page.layers.key.skin.tip.all") : word("page.layers.key.skin.tip");
  const hunt = (layer) => app.dungeon ? "" : layer === "xp"
    ? `<div class="lg-grind with-help"><button data-grind title="${word("page.layers.key.grind.tip")}">${SWORDS} ${word("page.layers.key.grind")}</button>${helpButton("loop")}
        <label class="lg-aoe" title="${word("page.layers.aoe.tip")}"><input type="checkbox" data-aoe="1"${layers.aoe ? " checked" : ""}><img src="/icon/spell_nature_wispsplode.jpg" alt=""> ${word("page.layers.aoe")}</label>${notAoe}</div>`
    : layer === "gold" ? `<div class="lg-grind with-help"><button data-farm title="${word("page.layers.key.farm.tip")}">${SWORDS} ${word("page.layers.key.farm")}</button>${helpButton("loop")}
        ${ahBox()}</div>`
    : layer === "skinning" && (app.status?.nums?.skinningSkill || layers.gatherAll) ? `<div class="lg-grind with-help"><button data-skin title="${forLeather
      ? word("page.layers.key.skin.leathers", { tip: skinTip, leathers: esc(forLeather) }) : skinTip}"><img class="lg-btn-icon" src="/icon/inv_misc_pelt_wolf_01.jpg" alt=""> ${word("page.layers.key.skin")}</button>${helpButton("loop")}</div>` : "";
  for (const [layer, style] of Object.entries(LAYER_HEAT)) {
    if (!layers.on.has(layer)) continue;
    pane();
    parts.push(head(layer === "skinning" && forLeather ? word("page.layers.skin-for", { layer: style.title, leathers: esc(forLeather) }) : style.title, `linear-gradient(135deg, ${style.base} 45%, ${style.hot})`));
    const noSkinning = layer === "skinning" && !skinFor();
    if (zoomedOut()) {
      const insts = viewInstances(), key = ZONE_VALUE[layer];
      const zones = insts.flatMap((i) => layers.zones[i] || []).filter((z) => z[key] > 0).sort((a, b) => b[key] - a[key]).slice(0, TOP_ZONES);
      if (!zones.length) {
        parts.push(`<div class="lg-note">${askNote(insts.map((i) => `layerzones:${i}`), { have: insts.every((i) => layers.zones[i]),
          none: noSkinning ? word("page.layers.no-skinning") : word("page.layers.nothing.area"), what: word("page.layers.ask.zones"), again: layersAgain })}</div>`);
      }
      for (const z of zones) {
        parts.push(zoneRow(z, layer === "xp" ? word("page.layers.value.xp", { n: num(z.xp) }) : layer === "gold" ? word("page.layers.value.gold", { money: money(z.gold) })
          : word("page.layers.value.spawns", { n: num(z.skin) })));
      }
      parts.push(hunt(layer));
      continue;
    }
    const top = d?.top?.[layer] || [];
    if (!top.length) {
      parts.push(`<div class="lg-note">${askNote("layers", { have: !!d, none: noSkinning ? word("page.layers.no-skinning") : word("page.layers.nothing.map"),
        what: word("page.layers.ask.map"), again: layersAgain })}</div>`);
    }
    for (const e of top) {
      const value = layer === "xp" ? word("page.layers.value.kill", { n: num(e.perKill) }) : layer === "gold" ? word("page.layers.value.gold", { money: money(e.perHour) })
        : word("page.layers.value.spawns", { n: e.spawns });
      rowsLit.add(`mob:${layer}:${e.name}`);
      parts.push(rowHtml(`${esc(e.name)} <small>${esc(e.levels)}</small>`, value, false,
        ` data-lit="${esc(`mob:${layer}:${e.name}`)}" tabindex="0" title="${word("page.layers.lit.mob", { name: esc(e.name) })}"`));
    }
    const measured = layer === "xp" && d?.xpMeasured;
    if (measured?.share) {
      parts.push(`<div class="lg-note">${word("page.layers.measured.share", { n: num(measured.kills), pct: Math.round(measured.share * 100) })}</div>`);
    } else if (measured) parts.push(`<div class="lg-note">${word("page.layers.measured", { n: measured.kills })}</div>`);
    const pace = (layer === "xp" || layer === "gold") && d?.pace;
    if (pace?.measured) parts.push(`<div class="lg-note">${word("page.layers.pace.measured", { s: pace.seconds, n: num(pace.kills) })}</div>`);
    else if (pace) parts.push(`<div class="lg-note">${word("page.layers.pace", { s: pace.seconds })}</div>`);
    if (d) parts.push(hunt(layer));
  }
  for (const [layer, style] of Object.entries(LAYER_DOTS)) {
    if (!layers.on.has(layer)) continue;
    pane();
    parts.push(head(style.title, style.color));
    const out = zoomedOut(), have = out ? layers.nodeZones[viewInstances()[0]] : d;
    const types = areaTypes(layer).filter((t) => typeShown(layer, t.name)).sort((a, b) => (b.can - a.can) || a.skill - b.skill);
    if (!types.length) parts.push(`<div class="lg-note">${typesNote(out ? word("page.layers.legend.none.area") : word("page.layers.legend.none.map"))}</div>`);
    for (const t of types) {
      const loopBtn = have && !app.dungeon ? `<button class="lg-loop" data-gather="${esc(layer)}" data-type="${esc(t.name)}" title="${word("page.layers.key.loop.tip", { name: esc(t.name) })}">${word("page.layers.key.loop")}</button>` : "";
      const icon = `<span class="lg-node" style="--node:${t.can ? style.color : "var(--node-locked)"}"><img src="/icon/${esc(t.icon || "inv_misc_questionmark")}.jpg" alt=""></span>`;
      parts.push(rowHtml(icon + esc(t.name) + loopBtn + (t.can || !t.skill ? "" : ` <small>${word("page.layers.needs", { skill: t.skill })}</small>`), num(t.count), !t.can));
    }
    if (types.length && have && !app.dungeon) {
      const all = `<button data-gather="${esc(layer)}" title="${word("page.layers.key.gather.tip")}">${word("page.layers.key.gather")}</button>`;
      parts.push(`<div class="lg-grind with-help">${all}${helpButton("loop")}
        <label class="lg-daredevil" title="${word("page.layers.daredevil.tip")}"><input type="checkbox" data-daredevil="1"${layers.daredevil ? " checked" : ""}> ${SKULL} ${word("page.layers.daredevil")}</label></div>`);
    }
  }
  pane();
  const html = panes.join("");
  box.hidden = false;
  setHtml(box, html);
  fitLegend();
  if (layers.lit && !rowsLit.has(layers.lit)) litAt(null);
}
const LEGEND_FOOT = 64;
const LEGEND_LEAST = 120;
function fitLegend() {
  const box = $("legend");
  if (box.hidden) return;
  box.style.maxHeight = `${Math.max(LEGEND_LEAST, innerHeight - box.getBoundingClientRect().top - LEGEND_FOOT)}px`;
}
addEventListener("resize", fitLegend);
on("column", fitLegend);

layers.lit = null;
function litAt(what) {
  if (what === layers.lit) return;
  layers.lit = what;
  app.litZone = what?.startsWith("zone:") ? +what.slice(5) : null;
  redraw();
}
const litRow = (e) => e.target.closest?.(".lg-row[data-lit]")?.dataset.lit ?? null;
$("legend").addEventListener("pointerover", (e) => litAt(litRow(e)));
$("legend").addEventListener("pointerleave", () => litAt(null));
$("legend").addEventListener("focusin", (e) => litAt(litRow(e)));
$("legend").addEventListener("focusout", () => litAt(null));
function intoLitZone(e) {
  const what = litRow(e);
  if (!what?.startsWith("zone:")) return false;
  litAt(null);
  showZone(+what.slice(5));
  return true;
}
function zoneRowKey(e) {
  if ((e.key !== "Enter" && e.key !== " ") || !intoLitZone(e)) return false;
  e.preventDefault();
  return true;
}

$("legend").addEventListener("change", (e) => {
  if (e.target.dataset?.daredevil) layers.daredevil = e.target.checked;
  else if (e.target.dataset?.aoe) layers.aoe = e.target.checked;
  else if (e.target.dataset?.ahPrices) return ahPricesTicked(e.target.checked);
  else return;
  saveLayers();
  renderLegend();
});
function ahPricesTicked(on) {
  layers.ahPrices = on;
  ahPricesMoved();
  saveLayers();
  renderLegend();
}
function ahPricesMoved() {
  layers.key = "";
  layers.zonesFor = {};
  refreshLayers();
  refreshZoneScores();
}
function ahScanMoved(b, was) {
  if (layers.ahPrices && (b?.version !== was?.version || b?.house !== was?.house)) ahPricesMoved();
  if (layers.on.has("gold")) renderLegend();
}
on("auction", ahScanMoved);
$("legend").addEventListener("click", (e) => {
  if (e.target.closest("button[data-grind]")) startGrindLoop();
  else if (e.target.closest("button[data-farm]")) startGrindLoop(true);
  else if (e.target.closest("button[data-skin]")) startGrindLoop(false, true);
  else if (!intoLitZone(e)) {
    const b = e.target.closest("button[data-gather]");
    if (b) startGatherLoop(b.dataset.gather, b.dataset.type);
  }
});
const loopFailed = (e) => askFailed(word("page.layers.loop.failed"), e);

function upText(n) {
  if (n == null) return word("page.layers.up.none");
  const v = n >= 10 ? Math.round(n) : Math.round(n * 10) / 10;
  return wordCount("page.layers.up", v);
}
function lapText(c) {
  if (!c?.lap || !c?.respawn) return "";
  const time = (s) => s < 90 ? `${Math.round(s)} s` : `${Math.round(s / 60)} min`;
  const fill = { lap: time(c.lap), respawn: time(c.respawn) };
  return `, ${c.lap >= c.respawn ? word("page.layers.lap.back", fill) : word("page.layers.lap.short", fill)}`;
}

function startGrindLoop(gold, skin) {
  if (!app.state) return;
  const area = searchArea(), go = () => searchCamp(gold, area.zones, skin);
  if (area.ask) return askSearch("hunt", area, go);
  go();
}
app.scout = null;
const SCOUT_LINES = Object.values(wordsOf("page.layers.scout.line"));
function scoutWords(s) {
  if (s.item) return word("page.layers.scout.item", { item: s.item.name });
  const what = { grind: word("page.layers.scout.grind"), farm: word("page.layers.scout.farm"), skin: word("page.layers.scout.skin") }[s.what];
  return s.zones.length > 1 ? word("page.layers.scout.zones", { what, n: s.zones.length }) : word("page.layers.scout.zone", { what, zone: mapName(s.zones[0]) });
}
function scoutHtml() {
  return `${panelHead(word("page.layers.scout.title"), "loop", `<button data-scout-stop title="${word("page.layers.scout.stop.tip")}">${word("page.layers.scout.stop")}</button>`, { track: true })}
    <div class="guide-name">${esc(scoutWords(app.scout))}</div>${runeLine(app.scout.line)}`;
}
function stopScout(quiet = false) {
  const s = app.scout;
  if (!s) return;
  app.scout = null;
  renderTracks();
  const stopped = word("page.layers.scout.stopped");
  if (!quiet) showToast(s.was && app.tracks.loop === s.was ? word("page.layers.runs-on", { text: stopped, loop: s.was.name }) : stopped);
  s.done?.();
}
document.querySelector(".sidestack")?.addEventListener("click", (e) => {
  if (e.target.closest("button[data-scout-stop]")) stopScout();
});

function searchCamp(gold, zones, skin, again, item = again?.was?.item) {
  if (item) [gold, skin] = [false, false];
  const s = app.state, me = playerWorld(), many = zones.length > 1;
  const all = gold ? goldAll() : !!skin && layers.gatherAll;
  const what = skin ? "skin" : gold ? "farm" : "grind";
  const q = new URLSearchParams(item ? { item: item.id } : { maps: zones.join(",") });
  q.set("level", s.level || 1);
  q.set("faction", app.status?.strs?.faction || "");
  if (me) { q.set("n", me.n.toFixed(1)); q.set("w", me.w.toFixed(1)); q.set("i", me.inst); }
  if (item) q.set("skinning", app.status?.nums?.skinningSkill || 0);
  if (gold) {
    q.set("gold", "1");
    q.set("skinning", app.status?.nums?.skinningSkill || 0);
  }
  if (gold && layers.ahPrices) q.set("ah", "1");
  if (all) q.set("all", "1");
  const leathers = skin ? (again ? again.was.leathers || [] : leatherFilter()) : [];
  if (skin) q.set("skin", app.status?.nums?.skinningSkill || 1);
  else if (!gold && !item && layers.aoe) q.set("aoe", aoeMost());
  if (leathers.length) q.set("leathers", leatherIds(leathers));
  if (prospecting()) stopProspecting(true);
  stopScout(true);
  const scout = app.scout = { what, zones, item, line: SCOUT_LINES[Math.floor(Math.random() * SCOUT_LINES.length)], was: again?.was,
    done: again?.done };
  renderTracks();
  const heeded = () => {
    if (app.scout !== scout) return false;
    app.scout = null;
    renderTracks();
    return true;
  };
  return getJson(`/api/grindloop?${q}`, { key: null }).then((c) => {
    if (!heeded()) return;
    if (again && app.tracks.loop !== again.was) return again.done();
    if (!c?.stops?.length) {
      const none = { what: skin ? word("page.layers.found.skin") : gold ? word("page.layers.found.farm") : word("page.layers.found.grind"),
        where: again ? word("page.layers.found.again") : many ? word("page.layers.found.area") : word("page.layers.found.zone") };
      const text = item ? word("page.layers.found.none.item", { item: item.name })
        : all ? word("page.layers.found.none", none) : word("page.layers.found.none.level", none);
      showToast(again ? word("page.layers.runs-on", { text, loop: again.was.name }) : text);
      return again?.done();
    }
    if (item) return itemLoop(c, item, again);
    const words = leatherWords(leathers);
    const cut = c.whole === false ? `, ${word("page.layers.sub.cut")}` : "";
    const from = words ? word("page.layers.loop.from", { what: words, name: c.name }) : c.name;
    const at = many && c.map ? word("page.layers.loop.in", { name: from, zone: mapName(c.map) }) : from;
    const name = skin ? word("page.layers.loop.skin", { name: at }) : gold ? word("page.layers.loop.farm", { name: at }) : word("page.layers.loop.grind", { name: at });
    const camp = { levels: c.levels, spawns: c.spawns }, atLevel = all ? ` ${word("page.layers.sub.at-level")}` : "";
    const [lead, after] = wordsOf("page.layers.sub").gold.split("{money}");
    const sub = skin ? word("page.layers.sub.count", { ...camp, n: num(c.skins),
      what: leathers.length ? words || word("page.layers.sub.leather") : word("page.layers.sub.skins") }) + atLevel + lapText(c) + cut
      : gold ? [fillWords(lead, camp), { money: c.gold },
        `${after}${layers.ahPrices ? ` ${word("page.layers.sub.ah")}` : ""}${atLevel}${lapText(c)}${cut}`]
      : word("page.layers.sub.xp", { ...camp, n: num(c.xp) }) + (c.pack ? `, ${word("page.layers.sub.pack", { n: c.pack })}` : "")
        + (c.perHour ? ` ${word("page.layers.sub.per-hour", { n: num(c.perHour) })}` : "") + lapText(c) + cut;
    if (again && sameLoop(again.was, what, name, c.stops, c.ids)) keepLoop(again.was, sub, c.spots);
    else {
      startLoopTrack(what, name, sub, c.stops, c.inst ?? app.maps[c.map ?? zones[0]]?.instance,
        { zone: c.map, zones, ...(c.mobs && { mobs: c.mobs }), ...(c.ids && { ids: c.ids }), ...(c.spots && { spots: c.spots }),
          ...(leathers.length && { leathers }) }, !!again);
    }
    again?.done();
  }, (e) => { if (heeded()) throw e; }).catch((e) => { loopFailed(e); again?.done(); });
}
function itemLoop(c, item, again) {
  const what = c.kind === "skin" ? "skin" : "grind";
  const cut = c.whole === false ? `, ${word("page.layers.sub.cut")}` : "";
  const from = word("page.layers.loop.from", { what: item.name, name: c.name });
  const name = what === "skin" ? word("page.layers.loop.skin", { name: from }) : word("page.layers.loop.grind", { name: from });
  const sub = word("page.layers.sub.count", { levels: c.levels, spawns: c.spawns, n: num(c.items), what: item.name }) + lapText(c) + cut;
  if (again && sameLoop(again.was, what, name, c.stops, c.ids)) keepLoop(again.was, sub, c.spots);
  else {
    startLoopTrack(what, name, sub, c.stops, c.inst ?? app.maps[c.map]?.instance,
      { zone: c.map, zones: [c.map], item, ...(c.mobs && { mobs: c.mobs }), ...(c.ids && { ids: c.ids }), ...(c.spots && { spots: c.spots }) }, !!again);
  }
  again?.done();
}

function startGatherLoop(layer, type) {
  if (!app.state) return;
  const area = searchArea(), go = () => {
    if (app.tracks.loop) stopTrack("loop", true);
    searchGather(layer, type ? [type] : null, area.zones);
  };
  if (area.ask) return askSearch("gather", area, go);
  go();
}
function gatherHereKinds(shown) {
  const can = shown.filter((t) => t.can);
  return (can.length ? can : shown).map((t) => t.name);
}
function searchGather(layer, kinds, zones, again) {
  const s = app.state, me = playerWorld(), map = zones[0];
  const types = again?.types?.length ? again.types : kinds?.length ? kinds : gatherHereKinds(areaTypes(layer).filter((t) => typeShown(layer, t.name)));
  if (!types.length) {
    showToast(word("page.layers.gather.none", { layer: LAYER_DOTS[layer]?.title || layer }));
    return again?.done();
  }
  const q = new URLSearchParams({ maps: zones.join(","), layer, types: types.join("|") });
  const skill = app.status?.nums?.[GATHER_SKILL[layer]];
  if (skill != null && !layers.gatherAll) q.set("skill", skill);
  const daredevil = !!layers.daredevil;
  if (daredevil) q.set("daredevil", "1");
  q.set("level", s.level || 1); q.set("faction", app.status?.strs?.faction || "");
  if (me) { q.set("n", me.n.toFixed(1)); q.set("w", me.w.toFixed(1)); }
  const kindsNamed = types.join(", ") || layer;
  startProspecting(q, { name: zones.length > 1 ? word("page.layers.prospecting", { kinds: kindsNamed })
                          : word("page.layers.prospecting.zone", { kinds: kindsNamed, zone: mapName(map) }),
                        map, many: zones.length > 1, inst: app.maps[map]?.instance, layer, types, daredevil,
                        mode: loopMode({ what: "gather", layer, types, daredevil }),
                        searched: zones, all: again ? !!again.all : !kinds?.length, was: again?.was, done: again?.done });
}

function gatherKinds(layer, zones, then) {
  const insts = [...new Set(zones.map((z) => app.maps[z]?.instance).filter((i) => i != null))];
  const asks = [];
  if (!layers.nodeKinds) asks.push(getJson("/api/nodekinds", { share: true })?.then((k) => { layers.nodeKinds = k; }));
  for (const inst of insts.filter((i) => !layers.nodeZones[i])) {
    asks.push(getJson(`/api/nodezones?instance=${inst}`, { share: true })?.then((z) => { layers.nodeZones[inst] = z; }));
  }
  if (asks.some((a) => !a)) return then(null);
  Promise.all(asks).then(() => {
    const want = new Set(zones), kinds = layers.nodeKinds?.[layer] || {}, skill = app.status?.nums?.[GATHER_SKILL[layer]] || 0;
    const there = new Set(insts.flatMap((i) => layers.nodeZones[i] || []).filter((z) => want.has(z.map))
      .flatMap((z) => Object.keys(z.spots?.[layer] || {})));
    then(gatherHereKinds([...there].filter((name) => typeShown(layer, name))
      .map((name) => ({ name, can: layers.gatherAll || !kinds[name]?.skill || skill >= kinds[name].skill }))));
  }).catch(() => then(null));
}
