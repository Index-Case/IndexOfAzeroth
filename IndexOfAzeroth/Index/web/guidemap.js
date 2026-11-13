// The Index of Azeroth. Copyright 2026 Index Case <indexofazeroth@pm.me>. PolyForm Strict 1.0.0, see LICENSE.md.
"use strict";


const LATER_LEG = tint("gold");
const CUT_OFF_COLOR = tint("zero", 0.85);
const ARROW_EVERY = 36;

const DANGER_GLOW = tint("danger-glow", 0.3), DANGER_SHADOW = tint("danger-red", 0.9);
const dangerDrawn = [];
const DANGER_HOVER = 8;
function drawDanger(way, screen) {
  const spans = way?.danger;
  if (!spans?.length) return;
  ctx.save();
  ctx.setLineDash([]); ctx.lineCap = "round"; ctx.lineJoin = "round";
  ctx.shadowColor = DANGER_SHADOW; ctx.shadowBlur = 12;
  ctx.lineWidth = 10; ctx.strokeStyle = DANGER_GLOW;
  spans.forEach((span, k) => {
    const pts = span.map(screen).filter(Boolean);
    if (pts.length < 2) return;
    strokePath(pts);
    dangerDrawn.push({ pts, notes: way.dangerNotes?.[k] || [] });
  });
  ctx.restore();
}
function dangerTipAt(mx, my) {
  const onIt = (d) => d.pts.some((a, i) => i > 0 && segDist([mx, my], d.pts[i - 1], a) <= DANGER_HOVER);
  const hit = dangerDrawn.filter(onIt);
  if (!hit.length) return null;
  const notes = [...new Set(hit.flatMap((d) => d.notes))];
  return notes.length
    ? `<b>${word("page.guidemap.careful")}</b>${notes.map((n) => `<small>${esc(n)}</small>`).join("<br>")}`
    : `<b>${word("page.guidemap.danger")}</b><small>${word("page.guidemap.danger.reach")}</small>`;
}

function strokeDots(pts, color = LATER_LEG, here = null) {
  const line = heightLine(pts, here);
  ctx.setLineDash([0.01, 9]); ctx.lineCap = "round";
  strokeEdge(line, DOT_WIDTH, tint("black", 0.7));
  strokeRuns(line, color, DOT_WIDTH);
  ctx.setLineDash([]); ctx.lineCap = "butt";
}

const HEIGHT_WIDTH = { level: 0.5, fall: 12, rise: 12, thin: 0.6, thick: 1.4 };
const WAY_WIDTH = { line: 2.5, edge: 2.5 };
const DOT_WIDTH = { line: 4, edge: 3 };
const WIDTH_STEP = 0.05;
function heightWidth(z, here) {
  if (z == null || here == null) return 1;
  const d = z - here, k = HEIGHT_WIDTH;
  if (Math.abs(d) <= k.level) return 1;
  const far = Math.min(1, (Math.abs(d) - k.level) / (d < 0 ? k.fall : k.rise));
  return 1 + far * ((d < 0 ? k.thin : k.thick) - 1);
}
function heightLine(line, here) {
  if (here == null || !line.some((q) => q.z != null)) return line;
  const share = (q) => heightWidth(q.z, here), out = [];
  line.forEach((q, i) => {
    const p = line[i - 1], w = share(q);
    if (p && !q.climb && !q.drop && p.z != null && q.z != null) {
      const n = Math.ceil(Math.abs(w - share(p)) / WIDTH_STEP);
      for (let k = 1; k < n; k++) {
        const t = k / n;
        const m = Object.assign([p[0] + (q[0] - p[0]) * t, p[1] + (q[1] - p[1]) * t], { under: q.under, z: p.z + (q.z - p.z) * t });
        m.w = share(m);
        out.push(m);
      }
    }
    out.push(Object.assign(q, { w }));
  });
  return out;
}
const stretchShare = (line, i) => Math.round((((line[i - 1].w ?? 1) + (line[i].w ?? 1)) / 2) / WIDTH_STEP) * WIDTH_STEP;
function eachRun(line, key, draw) {
  let run = [line[0]], at = 0, runAt = 0, was = null, first = 1;
  const flush = () => { if (run.length > 1) draw(run, runAt, first); };
  for (let i = 1; i < line.length; i++) {
    const len = Math.hypot(line[i][0] - line[i - 1][0], line[i][1] - line[i - 1][1]);
    if (line[i].climb || line[i].drop) { flush(); at += len; run = [line[i]]; runAt = at; continue; }
    const k = key(i);
    if (run.length > 1 && k !== was) { flush(); run = [line[i - 1]]; runAt = at; }
    if (run.length === 1) first = i;
    was = k; run.push(line[i]); at += len;
  }
  flush();
}
function strokeEdge(line, width, style) {
  ctx.strokeStyle = style;
  eachRun(line, (i) => stretchShare(line, i), (run, at, i) => {
    ctx.lineDashOffset = -at; ctx.lineWidth = width.line * stretchShare(line, i) + width.edge; strokePath(run);
  });
  ctx.lineDashOffset = 0;
}

const DIRECTION_EVERY = 144;
const COVERED = tint("covered");
function strokeWay(pts, color, dash = [10, 6], here = null) {
  const line = heightLine(pts, here);
  ctx.setLineDash(dash);
  strokeEdge(line, WAY_WIDTH, tint("black", 0.55));
  strokeRuns(line, color, WAY_WIDTH);
  ctx.setLineDash([]);
}
function strokeRuns(line, color, width) {
  eachRun(line, (i) => `${!!line[i].under} ${stretchShare(line, i)}`, (run, at, i) => {
    ctx.lineDashOffset = -at;
    ctx.strokeStyle = line[i].under ? COVERED : color;
    ctx.lineWidth = width.line * stretchShare(line, i);
    strokePath(run);
  });
  ctx.lineDashOffset = 0;
  for (let i = 1; i < line.length; i++) {
    if (line[i].climb || line[i].drop) drawTricky(line[i - 1], line[i], line[i].climb ? "climb" : "drop", color, stretchShare(line, i));
  }
}
function greyPoints(path, pts) {
  const grey = new Set((path?.covered || []).map((i) => path.points[i]));
  if (grey.size && app.state?.minimap?.indoors) for (const p of pts || path.points) if (!grey.delete(p)) break;
  return grey;
}
function screenWay(path, pts, screen, ahead = pts) {
  const grey = greyPoints(path, ahead);
  const marks = (k) => new Set((path?.[k] || []).map((i) => path.points[i]));
  const climbs = marks("climbs"), drops = marks("drops");
  const out = [];
  for (const p of pts) {
    const q = screen(p);
    if (q) { q.under = grey.has(p); q.climb = climbs.has(p); q.drop = drops.has(p); out.push(q); }
  }
  return out;
}

const ZIGZAG = { step: 7, width: 3.5 };
const DROP_DASH = [3, 4];
const CHEVRON = 6;
const trickyDrawn = [];
const TRICKY_WORDS = wordsOf("page.guidemap.tricky");
function zigzag(a, b) {
  const len = Math.hypot(b[0] - a[0], b[1] - a[1]);
  if (!len) return [a, b];
  const ux = (b[0] - a[0]) / len, uy = (b[1] - a[1]) / len, out = [a];
  for (let d = ZIGZAG.step, k = 1; d < len; d += ZIGZAG.step, k++) {
    const side = k % 2 ? ZIGZAG.width : -ZIGZAG.width;
    out.push([a[0] + ux * d - uy * side, a[1] + uy * d + ux * side]);
  }
  out.push(b);
  return out;
}
function drawTricky(a, b, kind, color, share = 1) {
  ctx.save();
  ctx.lineCap = "round"; ctx.lineJoin = "round";
  const pass = (pts, dash) => {
    ctx.setLineDash(dash);
    ctx.lineWidth = WAY_WIDTH.line * share + WAY_WIDTH.edge; ctx.strokeStyle = tint("black", 0.55); strokePath(pts);
    ctx.lineWidth = WAY_WIDTH.line * share; ctx.strokeStyle = b.under ? COVERED : color; strokePath(pts);
  };
  if (kind === "climb") pass(zigzag(a, b), []);
  else {
    pass([a, b], DROP_DASH);
    const [x, y] = a;
    pass([[x - CHEVRON, y - CHEVRON / 2], [x, y + CHEVRON / 2], [x + CHEVRON, y - CHEVRON / 2]], []);
  }
  ctx.restore();
  trickyDrawn.push({ a, b, kind });
}
const easyDrawn = [];
function drawEasyWay(from, easy, color, screen, name) {
  const rest = remainingPath({ ...easy, from: easy.from || from });
  const line = [from, ...screenWay(easy, rest, screen)];
  if (line.length < 2) return;
  drawWay(line, color);
  easyDrawn.push({ pts: line, name });
}
function easyTipAt(mx, my) {
  const hit = easyDrawn.find((d) => d.pts.some((a, i) => i > 0 && segDist([mx, my], d.pts[i - 1], a) <= DANGER_HOVER));
  return hit ? `<b>${esc(easyName(hit.name))}</b>` : null;
}
const easyName = (name) => word("page.guidemap.easy", { name });
function trickyTipAt(mx, my) {
  const hit = trickyDrawn.find((t) => segDist([mx, my], t.a, t.b) <= DANGER_HOVER);
  return hit ? `<b>${esc(TRICKY_WORDS[hit.kind])}</b>` : null;
}
const endsCovered = (path, pts) => !!path?.points?.length && greyPoints(path, pts).has(path.points[path.points.length - 1]);

function drawArrowheads(pts, color, every = ARROW_EVERY) {
  let carry = every / 2;
  for (let i = 1; i < pts.length; i++) {
    const [ax, ay] = pts[i - 1], [bx, by] = pts[i], len = Math.hypot(bx - ax, by - ay);
    if (!len) continue;
    const a = Math.atan2(by - ay, bx - ax);
    for (let d = carry; d <= len; d += every) {
      const x = ax + (bx - ax) * d / len, y = ay + (by - ay) * d / len;
      if (x < -20 || y < -20 || x > W + 20 || y > H + 20) continue;
      ctx.beginPath();
      ctx.moveTo(x + 8 * Math.cos(a + 2.5), y + 8 * Math.sin(a + 2.5));
      ctx.lineTo(x, y);
      ctx.lineTo(x + 8 * Math.cos(a - 2.5), y + 8 * Math.sin(a - 2.5));
      ctx.lineCap = "round"; ctx.lineJoin = "round";
      ctx.lineWidth = 5.5; ctx.strokeStyle = tint("black", 0.65); ctx.stroke();
      ctx.lineWidth = 3; ctx.strokeStyle = pts[i].under ? COVERED : color; ctx.stroke();
    }
    carry = ((carry - len) % every + every) % every;
  }
  ctx.lineCap = "butt"; ctx.lineJoin = "miter";
}
function drawLaterLegs(size, scale, color = LATER_LEG) {
  const g = shownGuide(), r = app.route;
  if (g && r?.key?.startsWith(`${pathKey(g)}|`)) drawRouteLegs(r, size, scale, color);
}
function drawRouteLegs(r, size, scale, color, from = null) {
  const me = playerWorld();
  if (!r?.legs.length) return;
  r.legs.forEach((leg, k) => {
    const prev = r.legs[k - 1], screen = screenIn(leg.map, size, scale);
    if (leg.kind === "walk") {
      const start = k === 0 ? from : prev?.at;
      if (!start) return;
      const lp = app.ways.get(legPathKey(leg, start, r.mode ?? app.pathMode));
      if (!lp) return;
      const pts = [screen(start), ...screenWay(lp, walkable(lp).points, screen, [])].filter(Boolean);
      if (pts.length < 2) return;
      drawWay(pts, color, { way: lp, screen, dots: true });
      const last = walkable(lp).points.at(-1), end = screen(leg.to);
      if (!wayThere(lp) && end && last && Math.hypot(last[0] - leg.to[0], last[1] - leg.to[1]) > 3) drawCutOff(pts[pts.length - 1], end);
    } else if (leg.kind === "ride") {
      const board = k === 0 ? from || (me && me.inst === leg.map ? [me.n, me.w] : null) : prev?.kind === "walk" && prev.map === leg.map ? prev.to : null;
      if (leg.vehicle === "flight" && leg.via?.length > 1) {
        let via = leg.via;
        if (k === 0 && me && !from) {
          let near = 0;
          via.forEach((p, i) => { if (Math.hypot(p[0] - me.n, p[1] - me.w) < Math.hypot(via[near][0] - me.n, via[near][1] - me.w)) near = i; });
          via = [[me.n, me.w], ...via.slice(near + 1)];
        }
        const pts = via.map(screen).filter(Boolean);
        if (pts.length > 1) drawArrowheads(pts, color);
        return;
      }
      const pts = board && [board, leg.at].map(screen);
      if (!pts || !pts[0] || !pts[1]) return;
      if (leg.vehicle === "flight") { drawArrowheads(pts, color); return; }
      drawWay(pts, color, { dots: true });
    }
  });
}

function drawStops(size, scale, color = LATER_LEG) {
  const g = app.guide;
  if (!g?.stops?.length) return;
  const screen = screenIn(g.instance, size, scale);
  for (const [a, b] of stopPairs(g)) {
    const r = stopRoute(g, a, b);
    if (r) { drawRouteLegs(r, size, scale, color, a); continue; }
    const sp = app.ways.get(wayKey(g.instance, a, b));
    const pts = [screen(a), ...(sp ? screenWay(sp, walkable(sp).points, screen, []) : [screen(b)])].filter(Boolean);
    if (pts.length < 2) continue;
    drawWay(pts, color, { way: sp, screen, dots: true });
    const end = sp?.partial && screen(b);
    if (end) drawCutOff(pts[pts.length - 1], end);
  }
  const pairs = stopPairs(g);
  g.stops.forEach((st, k) => {
    const at = k === g.stops.length - 1 ? null : screen([st.wx, st.wy]);
    if (!at) return;
    drawStopMark(at[0], at[1], k + 2, stopUnder(g, ...pairs[k]) ? COVERED : color);
    noteMark(at[0], at[1], { name: st.name || word("page.guidemap.stop", { n: k + 2 }),
      sub: word("page.guidemap.stop.of", { n: k + 2, total: g.stops.length + 1 }), cat: "guidestop" });
  });
}

function drawStopMark(x, y, n, color) {
  drawRingMarker(x, y, { r: 9, fill: tint("black", 0.75), ring: color, text: n });
}

function finalStep(g) {
  if (!g) return null;
  if (g.stops?.length) return g.stops[g.stops.length - 1];
  return { wx: g.wx, wy: g.wy };
}

function drawDestination(x, y, g, under = false, color = tint("gold")) {
  drawRingMarker(x, y, { r: 17, fill: tint("black"), ring: under ? COVERED : color, width: 3,
    icon: iconImage(g.icon || (g.cat === "gameguide" ? "inv_misc_map_01" : poiIcon(g.cat))) });
  const n = g.stops?.length;
  noteMark(x, y, n ? { name: g.stops[n - 1].name || word("page.guidemap.stop", { n: n + 1 }),
    sub: word("page.guidemap.stop.last", { n: n + 1, total: n + 1 }), cat: "guideend" }
    : { name: g.name, sub: g.sub || "", cat: "guideend" });
}
function guideNowTip(whole, leg) {
  if (leg?.leg) return { name: leg.name, sub: word("page.guidemap.on-the-way", { name: whole.name }), cat: "guidenow" };
  return { name: whole.stopName || whole.name, cat: "guidenow",
    sub: whole.stops?.length ? word("page.guidemap.stop.of", { n: 1, total: whole.stops.length + 1 }) : whole.sub || "" };
}
function routeEndsUnder(r, from) {
  const k = r.legs.length - 1, leg = r.legs[k], start = k ? r.legs[k - 1].at : from;
  return leg.kind === "walk" && !!start && endsCovered(app.ways.get(legPathKey(leg, start, r.mode ?? app.pathMode)), []);
}
function stopUnder(g, a, b) {
  const r = stopRoute(g, a, b);
  return r ? routeEndsUnder(r, a) : endsCovered(app.ways.get(wayKey(g.instance, a, b)), []);
}
function destinationUnder(g, path, rest) {
  const pairs = stopPairs(g);
  if (pairs.length) return stopUnder(g, ...pairs[pairs.length - 1]);
  const r = app.route?.key?.startsWith(`${pathKey(g)}|`) && app.route.legs.length > 1 ? app.route : null;
  return r ? routeEndsUnder(r, null) : endsCovered(path, rest);
}

function drawWayFrom(from, to, path, color, screen) {
  const reach = reachOf(path), walked = reach?.cutOff ? null : path;
  const rest = walked ? remainingPath(walkable(walked)) : null;
  const line = [from];
  if (rest) line.push(...screenWay(walked, rest, screen));
  if (line.length < 2 && !reach) line.push(to);
  if (line.length > 1) drawWay(line, color, { way: walked, screen });
  if (!reach) return rest;
  const end = line[line.length - 1];
  drawCutOff(end, to);
  if (line.length > 1) {
    ctx.lineWidth = 2.5; ctx.strokeStyle = CUT_OFF_COLOR;
    ctx.beginPath(); ctx.moveTo(end[0] - 5, end[1] - 5); ctx.lineTo(end[0] + 5, end[1] + 5);
    ctx.moveTo(end[0] + 5, end[1] - 5); ctx.lineTo(end[0] - 5, end[1] + 5); ctx.stroke();
  }
  return rest;
}

function drawGuide(s, size, scale) {
  const color = tint(guideToken());
  drawLaterLegs(size, scale, color);
  drawStops(size, scale, color);
  const whole = shownGuide(), fin = finalStep(whole), inst = app.maps[s.map]?.instance;
  const finAt = fin && worldOnScreen(whole.instance ?? inst, fin.wx, fin.wy, size, scale);
  const [fx, fy] = finAt || [NaN, NaN];
  const finOn = !Number.isNaN(fx) && fx >= 0 && fy >= 0 && fx <= W && fy <= H;
  const g = legOf(whole), onScreen = screenIn(inst, size, scale);
  const to = guideOnMap() && onScreen([g.wx, g.wy]), from = youOnScreen(size, scale);
  if (!to || !from) { if (finOn) drawDestination(fx, fy, whole, destinationUnder(whole, null, null), color); return; }
  const [tx, ty] = to, [px, py] = from, path = pathFor(g);
  if (path?.easy) drawEasyWay([px, py], path.easy, color, onScreen, g.name);
  const rest = drawWayFrom([px, py], [tx, ty], path, color, onScreen);
  const atEnd = !Number.isNaN(fx) && Math.hypot(fx - tx, fy - ty) < 3;
  if (offView(tx, ty)) drawEdgeHint(tx, ty, g.name, color);
  else if (!atEnd) {
    drawRingMarker(tx, ty, { r: 7, fill: tint("black"), ring: endsCovered(path, rest) ? COVERED : color, width: 3 });
    noteMark(tx, ty, guideNowTip(whole, g));
  }
  if (finOn) drawDestination(fx, fy, whole, destinationUnder(whole, path, rest), color);
}
