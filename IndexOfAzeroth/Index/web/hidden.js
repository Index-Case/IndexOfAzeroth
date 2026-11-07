// The Index of Azeroth. Copyright 2026 Index Case <indexofazeroth@pm.me>. PolyForm Strict 1.0.0, see LICENSE.md.
"use strict";

const HIDDEN_LINES = [
  "You've gone where the maps don't. A gnome is pretending this was the plan all along.",
  "Somewhere under the city, the tram is rattling along. The Index is betting on which end you come out of.",
  "The map has lost you. The dwarves say that's normal down here, and they'd know.",
  "You're in the deep tunnels now. A goblin is selling guesses at five copper each.",
  "The cartographers of Stormwind never drew this bit. They said it was too damp.",
  "Off the edge of the map and still moving. The Index is following the rattle of the rails.",
  "A secret way under the ground, by the look of it. The Index won't tell anyone.",
  "Your dot has gone underground. A gnome engineer insists it's perfectly safe and is holding his breath.",
  "Wherever you are, it's dark and it smells of oil. The Index is guessing, and guessing with confidence.",
  "You've slipped into one of Azeroth's hidden places. The Index is drawing a line and hoping.",
];
const HIDDEN_DOOR_NEAR = 40;
const HIDDEN_LAST_FRESH = 15000;
const HIDDEN_DOT_GAP = 26;
const HIDDEN_WRITE_MS = 2800;
const HIDDEN_LINE_KEY = "cc.hiddenLine";

const hiddenGuess = {
  places: null,
  last: null,
  now: null,
  lineShown: -1,
};

on("start", () => fetchUntil("/api/hidden", (j) => { hiddenGuess.places = j?.places || {}; }));

function hiddenDoorAt(last, here) {
  for (const [id, place] of Object.entries(hiddenGuess.places || {})) {
    if (here != null && here !== +id) continue;
    for (const d of place.doors || []) {
      if (d[0] === last.inst && Math.hypot(d[1] - last.n, d[2] - last.w) <= HIDDEN_DOOR_NEAR) return { id: +id, place, door: d };
    }
  }
  return null;
}
function hiddenFarDoor(place, door) {
  let far = null, most = -1;
  for (const d of place.doors || []) {
    const yd = d[0] === door[0] ? Math.hypot(d[1] - door[1], d[2] - door[2]) : -1;
    if (yd > most) { far = d; most = yd; }
  }
  return far;
}
function hiddenNextLine() {
  let last = hiddenGuess.lineShown;
  try {
    const kept = localStorage.getItem(HIDDEN_LINE_KEY);
    if (kept != null && Number.isInteger(+kept)) last = +kept;
  } catch (e) {   }
  const next = (last + 1 + HIDDEN_LINES.length) % HIDDEN_LINES.length;
  hiddenGuess.lineShown = next;
  try { localStorage.setItem(HIDDEN_LINE_KEY, String(next)); } catch (e) {   }
  return next;
}

function updateHiddenGuess() {
  const s = app.state, g = hiddenGuess;
  if (!s || lastSeenOnly() || inDungeon(s) || s.flags?.taxi || s.flags?.ghost) return endHiddenGuess();
  const me = playerWorld();
  if (me) {
    g.last = { inst: me.inst, n: me.n, w: me.w, at: Date.now() };
    return endHiddenGuess();
  }
  if (g.now || !g.last || !g.places || Date.now() - g.last.at > HIDDEN_LAST_FRESH) return;
  const here = s.instance?.id ?? null, found = hiddenDoorAt(g.last, here);
  if (!found) return;
  g.now = { id: found.id, place: found.place, from: found.door, to: hiddenFarDoor(found.place, found.door), at: g.last.at,
            seconds: found.place.seconds || 0, line: HIDDEN_LINES[hiddenNextLine()], inst: found.door[0], shown: Date.now() };
  hiddenView(g.now);
  redraw();
}
function endHiddenGuess() {
  if (!hiddenGuess.now) return;
  hiddenGuess.now = null;
  app.hiddenMap = null;
  if (app.view.continent === "hidden") leaveContinent();
  redraw();
}
const HIDDEN_FILL = 0.4;
function hiddenView(g) {
  const cont = continentMap(g.inst), v = app.view;
  app.hiddenMap = cont;
  if (cont == null || v.continent || v.world || !enterContinent("hidden", cont)) return;
  const ends = [g.from, g.to || g.from].map((d) => worldToFrac(cont, { inst: g.inst, n: d[1], w: d[2] })).filter(Boolean);
  if (!ends.length) return;
  const size = imgSize(mapImage(cont)), cv = app.clearShown || clearView();
  const xs = ends.map((f) => f[0]), ys = ends.map((f) => f[1]);
  const bw = Math.max(Math.max(...xs) - Math.min(...xs), 1e-3) * size.w, bh = Math.max(Math.max(...ys) - Math.min(...ys), 1e-3) * size.h;
  const zoom = Math.min((cv.r - cv.l) * HIDDEN_FILL / bw, (cv.b - cv.t) * HIDDEN_FILL / bh) / Math.min(W / size.w, H / size.h);
  if (!Number.isFinite(zoom)) return;
  v.zoom = Math.min(MAX_ZOOM, Math.max(MIN_ZOOM, zoom));
  centreInClear([(Math.min(...xs) + Math.max(...xs)) / 2, (Math.min(...ys) + Math.max(...ys)) / 2], size, cv);
}
on("update", updateHiddenGuess);
on("animate", () => !!hiddenGuess.now && Date.now() - hiddenGuess.now.shown < HIDDEN_WRITE_MS);

function hiddenShare(now = hiddenGuess.now, at = Date.now()) {
  if (!now?.seconds) return 0;
  return Math.max(0, Math.min(1, (at - now.at) / 1000 / now.seconds));
}

function drawHiddenGuess(size, scale) {
  const g = hiddenGuess.now;
  if (!g || app.dungeon) return;
  const a = worldOnScreen(g.inst, g.from[1], g.from[2], size, scale);
  const b = g.to && worldOnScreen(g.inst, g.to[1], g.to[2], size, scale);
  if (a) {
    const span = b ? Math.hypot(b[0] - a[0], b[1] - a[1]) : 0;
    const dots = Math.max(1, Math.round(span / HIDDEN_DOT_GAP)), share = hiddenShare(g), at = Math.round(share * dots);
    for (let k = 0; k <= dots; k++) {
      const t = k / dots, x = b ? a[0] + (b[0] - a[0]) * t : a[0], y = b ? a[1] + (b[1] - a[1]) * t : a[1];
      ctx.beginPath();
      ctx.arc(x, y, k === at ? 7 : 4, 0, Math.PI * 2);
      ctx.fillStyle = tint("ivory", k === at ? 1 : k < at ? 0.75 : 0.3);
      ctx.fill();
      if (k === at) { ctx.lineWidth = 2; ctx.strokeStyle = tint("black"); ctx.stroke(); }
      if (!b) break;
    }
    if (g.seconds && at < dots) redrawIn(((at + 0.5) / dots - share) * g.seconds * 1000);
  }
  drawHiddenLine(g);
}
const HIDDEN_FONT_PX = 34;
const HIDDEN_LINE_AT = 0.12;
function drawHiddenLine(g) {
  const cv = app.clearShown || { l: 0, r: W, t: 0, b: H };
  const most = Math.min(900, (cv.r - cv.l) * 0.8);
  ctx.save();
  ctx.font = `${HIDDEN_FONT_PX}px Metamorphous, serif`;
  ctx.textAlign = "center"; ctx.textBaseline = "middle";
  const rows = [];
  for (const word of g.line.split(" ")) {
    const row = rows.length ? `${rows[rows.length - 1]} ${word}` : word;
    if (rows.length && ctx.measureText(row).width <= most) rows[rows.length - 1] = row;
    else rows.push(word);
  }
  const x = (cv.l + cv.r) / 2, top = cv.t + (cv.b - cv.t) * HIDDEN_LINE_AT, step = HIDDEN_FONT_PX * 1.3;
  const share = Math.min(1, (Date.now() - g.shown) / HIDDEN_WRITE_MS), wide = Math.max(...rows.map((r) => ctx.measureText(r).width));
  ctx.beginPath();
  ctx.rect(x - wide / 2 - 20, top - step, (wide + 40) * share, step * (rows.length + 1));
  ctx.clip();
  ctx.shadowColor = tint("black"); ctx.shadowBlur = 9;
  ctx.fillStyle = tint("forever-cream");
  rows.forEach((r, k) => ctx.fillText(r, x, top + k * step));
  ctx.restore();
}
