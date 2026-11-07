// The Index of Azeroth. Copyright 2026 Index Case <indexofazeroth@pm.me>. PolyForm Strict 1.0.0, see LICENSE.md.
"use strict";

const TRAVEL_KINDS = { flight: "flight path", zeppelin: "zeppelin and airship", boat: "boat" };
const TRAVEL_TINTS = { flight: "route-flight", zeppelin: "route-zeppelin", boat: "route-boat" };
const SIDE_TINTS = { Alliance: "route-alliance", Horde: "route-horde" };
const SETTLED_TINTS = { "route-alliance": "route-alliance-bright", "route-horde": "route-horde-bright" };
const TRAVEL_MATCH = 80;
const TRAVEL_HOVER_PX = 7;
const ROUTE_FONT_PX = 18;

const travel = { on: new Set(), data: null, key: null, loading: false, hover: null, picked: null, route: null, lit: [], faint: [] };
const travelGo = $("travel-go");
try { JSON.parse(localStorage.getItem("cc.travelRoutes") || "[]").forEach((k) => { if (k in TRAVEL_KINDS) travel.on.add(k); }); } catch (e) {   }

function travelKey(cat) {
  if (!(cat in TRAVEL_KINDS)) return "";
  const lit = travel.on.has(cat);
  return html`<button class="mob-go" data-routes="${cat}" aria-pressed="${lit ? "true" : "false"}" title="${lit
    ? `Hide the ${TRAVEL_KINDS[cat]} routes`
    : `Show every ${TRAVEL_KINDS[cat]} route on the map as faint lines`}">Routes</button>`;
}
function toggleTravel(cat) {
  if (travel.on.has(cat)) travel.on.delete(cat); else travel.on.add(cat);
  try { localStorage.setItem("cc.travelRoutes", JSON.stringify([...travel.on])); } catch (e) {   }
  redraw();
}

function refreshTravel() {
  const ticked = [...poi.sides];
  const faction = ticked.length === 1 ? ticked[0] : ticked.length ? "" : app.status?.strs?.faction || "";
  if (travel.key === faction || travel.loading) return;
  const ask = getJson(`/api/travel?faction=${encodeURIComponent(faction)}`, { share: true });
  if (!ask) return;
  travel.loading = true;
  ask.then((d) => { travel.data = d; travel.key = faction; redraw(); }, () => {}).finally(() => { travel.loading = false; });
}
on("update", refreshTravel);

function stopNear(kind, inst, n, w) {
  let best = null, least = TRAVEL_MATCH;
  (travel.data?.[kind]?.stops || []).forEach((s, i) => {
    const d = s.inst === inst ? Math.hypot(s.n - n, s.w - w) : Infinity;
    if (d < least) { least = d; best = i; }
  });
  return best;
}

function stopOfSpot(d) {
  if (!d || !(d.p.cat in TRAVEL_KINDS) || d.map == null) return null;
  const f = fracToWorld(d.map, d.p.x, d.p.y);
  return f ? stopNear(d.p.cat, f.inst, f.n, f.w) : null;
}

function stopsOfSpot(d) {
  const out = [];
  for (const p of d?.p.group || (d ? [d.p] : [])) {
    const kind = p.cat, stop = stopOfSpot({ ...d, p });
    if (stop != null && !out.some((s) => s.kind === kind && s.stop === stop)) out.push({ kind, stop });
  }
  return out.length ? out : null;
}

function travelPlace(d) {
  if (d?.p.cat === "boat") return "";
  const i = stopOfSpot(d);
  return i == null ? "" : travel.data[d.p.cat].stops[i].name;
}

function litStops() {
  const shown = [...travel.hover || [], ...travel.picked?.stops || []]
    .filter((s, i, all) => all.findIndex((o) => o.kind === s.kind && o.stop === s.stop) === i);
  if (shown.length) return shown;
  const g = app.guide;
  if (!g || !(g.cat in TRAVEL_KINDS) || g.wx == null) return null;
  const i = stopNear(g.cat, g.instance, g.wx, g.wy);
  return i == null ? null : [{ kind: g.cat, stop: i }];
}

function routesAvoid(size, scale) {
  const m = app.displayMap === WORLD_MAP ? maelstromOn(app.maps[WORLD_MAP]) : null;
  if (!m) return [];
  const [x, y] = toScreen(m.x, m.y, size, scale, WORLD_MAP);
  return [{ x, y, r: m.r * size.w * scale }];
}

function strokeLine(pts, color, width) {
  ctx.beginPath();
  pts.forEach(([x, y], i) => (i ? ctx.lineTo(x, y) : ctx.moveTo(x, y)));
  ctx.strokeStyle = color; ctx.lineWidth = width;
  ctx.stroke();
}

const FAINT_EDGE = [0.45, 3], FAINT_INK = [0.8, 1.6];
function drawFaintRoute(pts, ink) {
  strokeLine(pts, tint("black", FAINT_EDGE[0]), FAINT_EDGE[1]);
  strokeLine(pts, tint(ink, FAINT_INK[0]), FAINT_INK[1]);
}

function routeBox() {
  const cv = app.clearShown || clearView();
  return { left: cv.l, top: cv.t, right: cv.r, bottom: cv.b };
}

function drawLitRoute(l, taken) {
  const ink = l.tint, box = routeBox(), hovered = travel.route === l.id, measure = (ch) => ctx.measureText(ch).width;
  const named = hovered || l.ours;
  const marks = named ? routeMarks(l.pts, box, l.names, measure, 7, l.settle, ROUTE_FONT_PX, taken)
    || edgeMarks(l.pts, box, l.names, measure, ROUTE_FONT_PX, taken, l.dest) : null;
  const pieces = marks ? piecesOutside(l.pts, marks.gaps) : [l.pts];
  for (const p of pieces) strokeLine(p, tint("black", 0.6), 4.5);
  for (const p of pieces) strokeLine(p, tint(ink, hovered ? 1 : 0.9), hovered ? 3 : 2.5);
  if (!marks) return;
  const { x, y, angle, alpha } = marks.diamond;
  ctx.save();
  ctx.globalAlpha = alpha;
  ctx.translate(x, y); ctx.rotate(angle + Math.PI / 4);
  ctx.fillStyle = tint(ink); ctx.strokeStyle = tint("black", 0.8); ctx.lineWidth = 1.5;
  ctx.fillRect(-4.5, -4.5, 9, 9); ctx.strokeRect(-4.5, -4.5, 9, 9);
  ctx.restore();
  ctx.textAlign = "center"; ctx.textBaseline = "middle"; ctx.lineWidth = 4;
  ctx.strokeStyle = tint("black", 0.85);
  for (const n of marks.names) {
    ctx.fillStyle = tintBetween(ink, SETTLED_TINTS[ink] || "white", n.white);
    ctx.globalAlpha = n.alpha;
    for (const c of n.letters) {
      ctx.save();
      ctx.translate(c.x, c.y); ctx.rotate(c.angle);
      ctx.strokeText(c.ch, 0, 0); ctx.fillText(c.ch, 0, 0);
      ctx.restore();
    }
  }
  ctx.globalAlpha = 1;
}

function tintBetween(from, to, t) {
  if (!t) return tint(from);
  const p = tintRgb(from), q = tintRgb(to);
  return `rgb(${p.map((c, i) => Math.round(c + (q[i] - c) * t)).join(", ")})`;
}

function settleNames(taken) {
  const box = routeBox();
  const band = window.matchMedia?.("(prefers-reduced-motion: reduce)").matches ? 0 : SETTLE_BAND;
  travel.lit.filter((l) => l.dest != null)
    .map((l) => { const spot = l.pts[l.dest ? l.pts.length - 1 : 0]; return { l, spot, t: settled(spot, box, band) }; })
    .sort((p, q) => q.t - p.t)
    .forEach(({ l, spot, t }) => {
      const lift = t > 0 ? placeLevel(taken, spot, ctx.measureText(l.names[l.dest]).width, ROUTE_FONT_PX) : -SETTLE_LIFT;
      l.settle = { end: l.dest, t, lift };
    });
}

function drawTravel(size, scale) {
  travel.lit = []; travel.faint = [];
  const key = placeTravelGo(size, scale);
  const d = travel.data;
  if (!d || app.dungeon) return;
  const lit = litStops() || [], up = [Math.sin(app.view.rot), -Math.cos(app.view.rot)], away = routesAvoid(size, scale);
  ctx.save();
  ctx.lineCap = "round"; ctx.lineJoin = "round";
  for (const kind of Object.keys(TRAVEL_KINDS)) {
    const net = d[kind], mine = new Set(lit.filter((s) => s.kind === kind).map((s) => s.stop));
    if (!net || (!travel.on.has(kind) && !mine.size)) continue;
    const at = net.stops.map((s) => worldOnScreen(s.inst, s.n, s.w, size, scale));
    net.links.forEach(([i, j, side], li) => {
      const on = mine.has(i) || mine.has(j), a = at[i], b = at[j];
      if (!a || !b || (!on && !travel.on.has(kind))) return;
      const pts = curve(a, steered(a, bowed(a, b, up), b, away), b);
      const own = on && !(mine.has(i) && mine.has(j)) ? (mine.has(i) ? i : j) : null;
      const names = [i === own ? "" : net.stops[i].name, j === own ? "" : net.stops[j].name];
      const ink = (kind === "flight" && SIDE_TINTS[side]) || TRAVEL_TINTS[kind];
      const route = { id: `${kind}:${li}`, kind, tint: ink, pts, ours: on, names, dest: own == null ? null : i === own ? 1 : 0 };
      if (on || route.id === travel.route) travel.lit.push(route);
      else { travel.faint.push(route); drawFaintRoute(pts, ink); }
    });
  }
  serifFont ||= getComputedStyle(document.documentElement).getPropertyValue("--serif").trim() || "Georgia, serif";
  ctx.font = `${ROUTE_FONT_PX}px ${serifFont}`;
  const taken = key ? [key] : [];
  settleNames(taken);
  travel.lit.forEach((l) => drawLitRoute(l, taken));
  ctx.restore();
}

function travelHover(e) {
  const r = canvas.getBoundingClientRect(), mx = e.clientX - r.left, my = e.clientY - r.top;
  const hover = stopsOfSpot(spotAt(mx, my));
  const onIt = (l) => offLine(l.pts, mx, my) < TRAVEL_HOVER_PX;
  const near = hover ? null : travel.lit.find(onIt) || travel.faint.find(onIt);
  const route = near ? near.id : null;
  if (JSON.stringify(hover) !== JSON.stringify(travel.hover) || route !== travel.route) {
    travel.hover = hover; travel.route = route;
    redraw();
  }
}
canvas.addEventListener("pointermove", travelHover);

function pickTravel(hit) {
  const was = travel.picked, p = hit && spotPlace(hit);
  const at = p && fracToWorld(hit.map ?? app.state?.map, p.x, p.y);
  travel.picked = at ? { hit, stops: stopsOfSpot(hit) || [], at } : null;
  if (travel.picked) travelGo.title = `Starts the Navigation Guide to this ${poiWhat(p.cat)}. Paste the line the page copies into the game's chat, as with every guide`;
  if (was || travel.picked) redraw();
  return was;
}

function sameTravelPick(pick, hit) {
  const a = spotPlace(pick.hit), b = spotPlace(hit);
  return (pick.hit.map ?? null) === (hit.map ?? null) && a.cat === b.cat && a.x === b.x && a.y === b.y;
}

function placeTravelGo(size, scale) {
  const pk = travel.picked, box = routeBox();
  const at = pk && !app.dungeon ? worldOnScreen(pk.at.inst, pk.at.n, pk.at.w, size, scale) : null;
  const shown = !!at && at[0] >= box.left && at[0] <= box.right && at[1] >= box.top && at[1] <= box.bottom;
  travelGo.classList.toggle("out", shown);
  travelGo.tabIndex = shown ? 0 : -1;
  if (!shown) return null;
  const left = Math.round(at[0] + POI_SIZE / 2 + 6), top = Math.round(at[1]), h = Number(travelGo.offsetHeight) || 0;
  travelGo.style.left = `${left}px`;
  travelGo.style.top = `${top}px`;
  return { left, right: left + (Number(travelGo.offsetWidth) || 0), top: top - h / 2, bottom: top + h / 2 };
}
travelGo.addEventListener("click", () => { if (travel.picked) guideToMapSpot(travel.picked.hit); });
canvas.addEventListener("pointerleave", () => {
  if (!travel.hover && !travel.route) return;
  travel.hover = null; travel.route = null;
  redraw();
});
