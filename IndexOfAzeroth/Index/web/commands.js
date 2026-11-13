// The Index of Azeroth. Copyright 2026 Index Case <indexofazeroth@pm.me>. PolyForm Strict 1.0.0, see LICENSE.md.
"use strict";


const PLACE_CATS = new Set(["dungeon", "raid", "battleground", "mailbox", "portal", "gameguide", "pin", "corpse", "node", "boat", "questobject"]);
const MOB_CATS = new Set(["rare", "boss", "respawn", "mob"]);
const goalMark = (g) => !g || g.fromGame || g.stops?.length ? ""
  : MOB_CATS.has(g.cat) ? "!" : (g.cat && !PLACE_CATS.has(g.cat)) || g.todoId ? "@" : "";

const fitted = new Map();
function fittedLine(key, make) {
  if (fitted.has(key)) return fitted.get(key);
  const line = make();
  fitted.set(key, line);
  if (fitted.size > 8) fitted.delete(fitted.keys().next().value);
  return line;
}
const pointsKey = (pts) => pts.map((p) => `${p[0]},${p[1]},${p[2] ?? ""}${p[3] ? ",i" : ""}`).join(";");
const covers = () => (app.status?.nums?.lineFormat || 0) >= COVER_FORMAT;
function linePoints(way, pts) {
  const inside = covers() ? new Set((way?.indoor || []).map((i) => way.points[i])) : new Set();
  return pts.map((p) => [p[0], p[1], p[2], inside.has(p) ? 1 : 0]);
}
const endsUnder = (way) => !!way && !way.partial && !!way.points?.length && (way.covered || []).includes(way.points.length - 1);
const learnsHeight = (g) => goalMark(g) === "@" && (g.wz == null || !!g.wzLearnt)
  && (app.status?.nums?.lineFormat || 0) >= HEIGHT_FORMAT;

let goCut = null;
function goCommand(guide) {
  goCut = null;
  if (!guide?.stops?.length || app.dungeon) return targetCommand(guide);
  const many = stopsCommand(guide), of = guide.stops.length + 1;
  if (many) {
    if (many.kept < of) goCut = { line: many.line, said: stopsCutWords(many.kept, of) };
    return many.line;
  }
  const line = targetCommand(guide);
  if (line && !goCut) goCut = { line, said: stopsCutWords(1, of) };
  return line;
}

function targetCommand(guide) {
  const route = routeCommand(guide);
  if (route) return route;
  if (app.dungeon) return null;
  const g = legOf(guide);
  if (!g) return null;
  const line = walkCommand(g, guide);
  if (line && g.leg && app.route?.legs.length > 1) goCut = { line, said: routeCutWords(g.name) };
  return line;
}

function walkCommand(g, guide) {
  const path = pathFor(g), cont = path && continentMapOf(g.instance ?? app.maps[app.state?.map]?.instance);
  if (path && cont && path.points.length > 1) {
    const reach = reachOf(path);
    if (reach?.cutOff) return null;
    const pts = linePoints(path, remainingPath(walkable(path)));
    if (!pts.length) return null;
    const notes = carefulPick(wayNotes(path, walkable(path).points.length - pts.length));
    const name = reach ? word("page.commands.close-to", { name: g.name }) : `${goalMark(g)}${g.name}`;
    const top = g.wz;
    const under = endsUnder(path), height = g === guide && learnsHeight(g) ? top ?? pts[pts.length - 1][2] ?? null : null;
    const head = `/ioa go ${cont.id} `;
    const marks = { under, height, cover: covers() };
    const line = fittedLine(`go|${head}|${Object.values(cont.w)}|${top}|${under}|${height}|${name}|${pointsKey(pts)}|${notes.join(";")}`, () => {
      const forms = carefulForms(notes);
      const length = (way, form) => head.length + packedLength(way) + riseLength(way, top, marks) + carefulLength(form) + 1 + name.length;
      let said = 0;
      if (notes.length) {
        const floor = pts.slice();
        trimToFit(floor, () => floor.length <= CAREFUL_BENDS || length(floor, forms[0]) <= CHAT_MAX);
        while (said < forms.length - 1 && length(floor, forms[said]) > CHAT_MAX) said++;
      }
      return trimToFit(pts, () => length(pts, forms[said]) <= CHAT_MAX)
        ? `${head}${packWay(cont, pts)}${riseToken(pts, top, marks)}${carefulToken(forms[said])} ${name}` : null;
    });
    if (line) return line;
  }
  if (reachOf(path)) return null;
  const c = continentMapOf(g.instance ?? app.maps[app.state?.map]?.instance);
  if (c) {
    const [x, y] = onMap(c, [g.wx, g.wy]);
    return `/ioa go ${c.id} ${(x * 100).toFixed(2)},${(y * 100).toFixed(2)} ${goalMark(g)}${g.name}`;
  }
  const z = zoneAt(g.wx, g.wy, g.instance ?? app.maps[app.state?.map]?.instance);
  return z ? `/ioa go ${z.id} ${z.x.toFixed(1)} ${z.y.toFixed(1)} ${goalMark(g)}${g.name}` : null;
}

function goalAt(inst, wx, wy) {
  const gc = continentMapOf(inst), gz = !gc && zoneAt(wx, wy, inst);
  return gc ? `${gc.id}.${packPoint(...onMap(gc, [wx, wy]))}` : gz ? `${gz.id}.${packPoint(gz.x / 100, gz.y / 100)}` : "0.AAAAA";
}

const NO_WAY_YET = word("page.commands.no-way");
function legParts(g, legs, from, mode, ends) {
  const last = legs.length - 1;
  const inWords = (leg, k, why) => (k < last ? { text: `w${leg.name}${why ? ` ${why}` : ""}` } : ends.stop ? { stop: ends.stop, why }
    : { text: why ? `w${ends.name} ${why}` : "w" });
  return legs.map((leg, k) => {
    if (leg.kind !== "walk") {
      const { code, text } = rideWords(leg);
      return { text: code + text + (leg.npc ? `@${leg.npc}` : "") };
    }
    const cont = continentMapOf(leg.map), at = k ? legs[k - 1].at || leg.to : from;
    if (!cont) return inWords(leg, k, "");
    const way = at ? app.ways.get(legPathKey(leg, at, mode)) : pathFor(legOf(g));
    if (wayShort(way)) return inWords(leg, k, NO_WAY_ON_FOOT);
    if (!way?.points?.length) return inWords(leg, k, NO_WAY_YET);
    const ahead = at ? way.points : remainingPath(way);
    const pts = linePoints(way, at ? [at, ...ahead] : ahead);
    const height = k === last && learnsHeight(g) ? ends.top ?? pts[pts.length - 1][2] ?? null : null;
    return { cont, pts, fixed: at ? 1 : 0, rise: k === last ? { top: ends.top, under: endsUnder(way), height, cover: covers() } : null,
      notes: wayNotes(way, way.points.length - ahead.length) };
  });
}
const stopName = (s, n) => `stop ${s} of ${n}`;
function partText(l, n) {
  if (l.pts) return `W${l.cont.id}${packWay(l.cont, l.pts)}${l.rise ? riseToken(l.pts, l.rise.top, l.rise) : coverToken(l.pts)}`;
  return l.stop ? `w${stopName(l.stop, n)}${l.why ? ` ${l.why}` : ""}` : l.text;
}
const partLength = (l, n) => (l.pts ? 1 + String(l.cont.id).length + packedLength(l.pts)
  + (l.rise ? riseLength(l.pts, l.rise.top, l.rise) : coverToken(l.pts).length) : partText(l, n).length);
const partKey = (l) => (l.pts ? `${l.cont.id}:${Object.values(l.cont.w)}:${l.fixed}:${l.rise ? `${l.rise.top}:${l.rise.under}:${l.rise.height}` : ""}:${pointsKey(l.pts)}:${l.notes.join(";")}`
  : l.stop ? `${l.stop}:${l.why}` : l.text);

function routeCommand(g) {
  const r = app.route;
  if (!g || !r?.key?.startsWith(`${pathKey(g)}|`) || !r.legs.some((l) => l.kind !== "walk")) return null;
  const legs = legParts(g, r.legs, null, r.mode ?? app.pathMode, { name: g.name, top: g.wz });
  const head = `/ioa r ${goalAt(g.instance, g.wx, g.wy)}`, tail = `=${goalMark(g)}${g.name}`;
  const shorter = (k) => {
    for (let j = k - 1; j > 1; j--) if (r.legs[j - 1].kind !== "walk" && r.legs.slice(0, j - 1).some((l) => l.kind === "walk")) return j;
    return 0;
  };
  const fit = fittedLine(`r|${head}|${tail}|${legs.map(partKey).join("~")}`, () => {
    let k = legs.length;
    const held = () => legs.slice(0, k);
    const notes = () => carefulPick(held().flatMap((l) => l.notes || []));
    const length = (form) => held().reduce((n, l) => n + 1 + partLength(l), head.length + tail.length) + carefulLength(form);
    for (;;) {
      while (length(notes()) > CHAT_MAX && dropHarmless(held())) {   }
      const j = length(notes()) > CHAT_MAX && shorter(k);
      if (!j) break;
      k = j;
    }
    const forms = carefulForms(notes());
    let said = 0;
    while (said < forms.length - 1 && length(forms[said]) > CHAT_MAX) said++;
    if (length(forms[said]) > CHAT_MAX) return null;
    const upTo = k < legs.length ? r.legs.slice(0, k).filter((l) => l.kind === "walk").at(-1).name : null;
    return { line: `${head}~${held().map((l) => partText(l)).join("~")}${carefulToken(forms[said], "~?")}${tail}`, upTo };
  });
  if (fit?.upTo) goCut = { line: fit.line, said: routeCutWords(fit.upTo) };
  return fit ? fit.line : null;
}

function stopsCommand(g) {
  const r = app.route?.key?.startsWith(`${pathKey(g)}|`) ? app.route : null;
  const own = r?.legs.length ? r.legs : [{ kind: "walk", map: g.instance, to: [g.wx, g.wy, g.wz], name: g.name }];
  const segment = (legs, from, mode, stop) => legParts(g, legs, from, mode, { stop, top: stop === 1 ? g.wz : null });
  const segs = [segment(own, null, r?.mode ?? app.pathMode, 1)], goals = [goalAt(g.instance, g.wx, g.wy)];
  stopPairs(g).forEach(([a, b], k) => {
    const sr = stopRoute(g, a, b);
    segs.push(segment(sr ? sr.legs : [{ kind: "walk", map: g.instance, to: b, name: g.stops[k].name }], a, app.pathMode, k + 2));
    goals.push(goalAt(g.instance, b[0], b[1]));
  });
  const tail = `=${goalMark(g)}${g.name}`;
  const key = `s|${goals}|${tail}|${segs.map((s) => s.map(partKey).join("~")).join("^")}`;
  return fittedLine(key, () => {
    let n = segs.length;
    const parts = () => segs.slice(0, n).flat();
    const notes = () => carefulPick(parts().flatMap((l) => l.notes || []));
    const length = (form) => parts().reduce((len, l) => len + 1 + partLength(l, n), `/ioa r ${goals[n - 1]}`.length + tail.length)
      + carefulLength(form);
    for (;;) {
      while (length(notes()) > CHAT_MAX && dropHarmless(parts())) {   }
      if (n === 2 || length(notes()) <= CHAT_MAX) break;
      n--;
    }
    const forms = carefulForms(notes());
    let said = 0;
    while (said < forms.length - 1 && length(forms[said]) > CHAT_MAX) said++;
    if (length(forms[said]) > CHAT_MAX) return null;
    return { line: `/ioa r ${goals[n - 1]}~${parts().map((l) => partText(l, n)).join("~")}${carefulToken(forms[said], "~?")}${tail}`, kept: n };
  });
}
const BEND_SHIFT = 4;
function dropHarmless(parts) {
  let best = null;
  for (const l of parts) {
    for (let i = 1; l.pts && i < l.pts.length - 1; i++) {
      const shift = bendShift(l.pts[i - 1], l.pts[i], l.pts[i + 1]);
      if (shift <= BEND_SHIFT && (!best || shift < best.shift)) best = { l, at: i, shift };
    }
  }
  if (best) best.l.pts.splice(best.at, 1);
  return !!best;
}
function bendShift(a, b, c) {
  if (a[2] == null || b[2] == null || c[2] == null) return stretchYards(b, a, c);
  const d = [c[0] - a[0], c[1] - a[1], c[2] - a[2]], len = d[0] ** 2 + d[1] ** 2 + d[2] ** 2;
  const u = len ? Math.max(0, Math.min(1, ((b[0] - a[0]) * d[0] + (b[1] - a[1]) * d[1] + (b[2] - a[2]) * d[2]) / len)) : 0;
  return Math.hypot(b[0] - a[0] - u * d[0], b[1] - a[1] - u * d[1], b[2] - a[2] - u * d[2]);
}
const stopsCutWords = (kept, of) => (kept > 1 ? word("page.commands.cut.stops", { kept, of }) : word("page.commands.cut.stop", { of }));
const routeCutWords = (upTo) => word("page.commands.cut.route", { upto: upTo });


const PASTE_HOW = word("page.commands.paste");
const LINE_FORMAT = 19;
const BACKGROUND_FORMAT = 19;
const PUTBACK_FORMAT = 18;
const COVER_FORMAT = 17;
const HEIGHT_FORMAT = 13;
const PARK_FORMAT = 8;
const UNPARK_FORMAT = 10;
function copyText(text, lead = word("page.commands.copied"), leave = true, plan = null) {
  if (!text) return showToast(word("page.commands.nothing"));
  if (leave) leaveForLogin(text);
  const older = lineTooNew(), cut = goCut?.line === text ? ` ${goCut.said}.` : "";
  const ready = (copied) => plan && showPlanReady({ reload: leave, ...plan, text, copied });
  const done = () => {
    showToast(`${lead}.${cut} ${older ? word("page.commands.older") : PASTE_HOW}${
      shownGuide()?.fromGame ? `. ${word("page.commands.game-guide")}` : ""}`);
    ready(true);
  };
  const refused = () => ready(false);
  if (navigator.clipboard?.writeText) {
    navigator.clipboard.writeText(text).then(done, () => fallbackCopy(text, done, refused));
  } else fallbackCopy(text, done, refused);
}

function fallbackCopy(text, done, refused = () => {}) {
  const box = document.createElement("textarea");
  box.value = text;
  document.body.appendChild(box);
  box.select();
  let ok;
  try { ok = document.execCommand("copy") !== false; } catch (e) { ok = false; }
  if (ok) done();
  else { showToast(word("page.commands.refused")); refused(); }
  box.remove();
}

function leaveForLogin(line, kind = "go", title = null) {
  if (line && !/^\/ioa (go|r|g|h|k|target) /.test(line)) return;
  const loop = !!line && /^\/ioa (g|h|k) /.test(line);
  const body = line ? { line, guide: (title ?? (loop ? app.tracks?.loop?.name : app.guide?.name)) || "", page: pageId() } : { clear: true, kind };
  if (loop && app.tracks?.loop?.what) body.what = app.tracks.loop.what;
  postJson("/api/pending", body).catch(() => {});
}

let pageIdWas = null;
function pageId() {
  try {
    let id = sessionStorage.getItem("cc.pageId");
    if (!id) { id = Math.random().toString(36).slice(2, 12); sessionStorage.setItem("cc.pageId", id); }
    return id;
  } catch (e) { return pageIdWas ||= Math.random().toString(36).slice(2, 12); }
}


const LOOP_TOKENS = { xp: "x", farm: "g", mining: "m", herbalism: "h", fishing: "f", treasure: "t" };
const loopToken = (t) => (t.kind === "loop" && LOOP_TOKENS[loopLook(t)] ? ` &${LOOP_TOKENS[loopLook(t)]}` : "");

function trackCommand(t) {
  const r = trackRoute(t), me = playerWorld();
  const at = r?.boardAt || (me && [me.n, me.w]);
  const g = trackTarget(t) || (r && me ? { inst: me.inst, n: at[0], w: at[1] } : null);
  const cont = g && continentMapOf(g.inst);
  if (!g || !cont || app.dungeon) return null;
  const pct = (p) => onMap(cont, p).map((f) => (f * 100).toFixed(2)).join(",");
  const style = trackStyle(t.kind, t);
  let name = t.kind === "epic" ? t.step?.text || t.name : t.name;
  const takes = t.kind === "epic" ? epicTakes(t) : "";
  let lead = t.path ? remainingPath(walkable(t.path)).map((p) => [p[0], p[1], p[2]]) : [];
  const reach = reachOf(t.path);
  if (reach?.cutOff || (reach && !lead.length)) return null;
  const seen = t.kind === "loop" ? [wayNotes(t.path, t.path ? walkable(t.path).points.length - lead.length : 0)] : null;
  if (!reach && (!lead.length || Math.hypot(lead[lead.length - 1][0] - g.n, lead[lead.length - 1][1] - g.w) > 5)) lead.push([g.n, g.w, g.z]);
  const circuit = t.loop && t.kind !== "epic" ? loopCircuit(t, t.at) : null;
  const walks = t.kind === "epic" && (t.step?.kind === "objective" || t.step?.walker) && t.step.inst === g.inst && t.step.patrols?.length && !t.step.loop?.length
    ? t.step.patrols.reduce((a, b) => !me || nearestOn(a, me) <= nearestOn(b, me) ? a : b) : null;
  const loop = circuit ? circuit.pts : walks ? walks.map((p) => [p[0], p[1]]) : [];
  const around = () => loop.length ? ` @ ${packed(loop)}` : "";
  let head = "", queue = [], keys = [];
  if (t.kind === "epic" && epicCode(t.step)) {
    head = `=${epicToken(t.step)} `;
    keys = [epicKey(t.step)];
    const steps = t.data?.steps || [];
    for (let k = 1; k < steps.length; k++) {
      const st = steps[k], prev = steps[k - 1];
      if (!st.at || st.inst !== g.inst || !epicCode(st)) break;
      const way = prev.at && app.ways.get(wayKey(st.inst, prev.at, st.at, stepWayMode(t, st)));
      const bends = way && !way.partial ? walkable(way).points.slice(0, -1).map((p) => [p[0], p[1]]) : [];
      queue.push({ token: `${epicToken(st)}@${packPoint(...onMap(cont, st.at))}`, key: epicKey(st), bends });
    }
  }
  const rides = [];
  let ride = null;
  const rideToken = (x) => ({ token: `>${x.code}${lineWord(x.text)}${x.npc ? `@${lineWord(x.npc)}` : ""}` });
  for (let k = r && r.legs[0].kind !== "walk" ? 0 : 1; r && k < r.legs.length; k++) {
    const leg = r.legs[k], prev = r.legs[k - 1];
    if (leg.kind !== "walk") {
      const { code, text } = rideWords(leg);
      if (!ride || (ride.code === "D" && code !== "D")) ride = { code, text, npc: leg.npc };
      else if (code !== "D") ride.text = text;
      continue;
    }
    if (!prev?.at || continentMapOf(leg.map)?.id !== cont.id) continue;
    const lp = app.ways.get(legPathKey(leg, prev.at, r.mode ?? trackWayMode(t)));
    if (wayShort(lp)) break;
    const pts = [[prev.at[0], prev.at[1], prev.at[2]]];
    seen?.push(wayNotes(lp));
    for (const p of lp ? walkable(lp).points : []) pts.push([p[0], p[1], p[2]]);
    if (Math.hypot(pts.at(-1)[0] - leg.to[0], pts.at(-1)[1] - leg.to[1]) > 5) pts.push([leg.to[0], leg.to[1], leg.to[2]]);
    if (ride) rides.push(rideToken(ride));
    ride = null;
    rides.push({ pts });
  }
  if (ride) rides.push(rideToken(ride));
  const packed = (pts) => packWay(cont, pts);
  const dropBend = (pts, keep) => {
    if (pts.length <= keep) return false;
    const drop = leastBend(pts);
    if (drop < 0) pts.shift(); else pts.splice(drop, 1);
    return true;
  };
  const endWalk = rides.length ? rides[rides.length - 1].pts : lead, goalZ = t.kind === "epic" ? t.stops?.[0]?.[2] : null;
  const walk = (pts) => packed(pts) + (pts === endWalk ? riseToken(pts, goalZ) : "");
  const rideText = () => rides.map((x) => ` ${x.token ?? walk(x.pts)}`).join("");
  const shared = sharedStepIndex(t);
  if (shared >= 0) {
    const short = () => `/ioa ${style.verb} ${cont.id} ${walk(lead)}${rideText()}${around()} #${app.shared.version}:${shared + 1}${takes}`;
    while (short().length > CHAT_MAX && dropBend(lead, 2)) {   }
    t.lastPacked = app.shared.epic.steps.slice(shared).map((s) => `${sharedCode(s)}|${s.text}`);
    return short().length <= CHAT_MAX ? short() : null;
  }
  const tail = () => queue.length ? ` ${queue.map((q) => q.token + (q.bends?.length ? ` ${packed(q.bends)}` : "")).join(" ")}` : "";
  const mobs = t.kind === "loop" && t.what !== "gather" ? [...(t.mobs || [])] : [];
  const mobText = () => mobs.length ? ` !${mobs.map(lineWord).join(";")}` : "";
  for (let k = 0; seen && circuit && k < t.stops.length; k++) {
    const n = t.stops.length, a = t.stops[(t.at + k) % n], b = t.stops[(t.at + k + 1) % n];
    seen.push(wayNotes(app.ways.get(wayKey(t.inst, a, b, loopMode(t)))));
  }
  const forms = carefulForms(seen ? carefulPick(seen.flat()) : []);
  let said = 0;
  const careText = () => carefulToken(forms[said]);
  const named = () => (reach ? word("page.commands.close-to", { name }) : name);
  const kindText = loopToken(t);
  const line = () => loop.length && t.kind !== "epic" ? `/ioa ${style.verb} ${cont.id}${kindText} ${walk(lead)}${rideText()}${around()}${mobText()}${careText()} ${named()}`
    : lead.length > 1 || head || rides.length || loop.length ? `/ioa ${style.verb} ${cont.id}${kindText} ${head}${walk(lead)}${rideText()}${around()}${tail()}${takes}${mobText()} ${named()}`
    : `/ioa ${style.verb} ${cont.id}${kindText} ${pct(lead[0]).replace(",", " ")} ${named()}`;
  const dropWay = (q) => {
    while (line().length > CHAT_MAX && q.bends.length && (q.bends.length > 1 ? dropBend(q.bends, 1) : q.bends.pop())) {   }
  };
  while (line().length > CHAT_MAX && queue.length > 6) queue.pop();
  for (let k = queue.length - 1; k >= 1 && line().length > CHAT_MAX; k--) dropWay(queue[k]);
  if (line().length > CHAT_MAX) name = name.replace(/ (to|from) [^,]+$/, "");
  if (forms.length > 2 && line().length > CHAT_MAX) {
    const was = lead.slice();
    while (line().length > CHAT_MAX && dropBend(lead, 12)) {   }
    while (line().length > CHAT_MAX && said < forms.length - 2) said++;
    lead.splice(0, lead.length, ...was);
  }
  while (line().length > CHAT_MAX && dropBend(lead, 12)) {   }
  while (line().length > CHAT_MAX && circuit && dropLoopBend(circuit)) {   }
  if (queue.length) dropWay(queue[0]);
  for (const x of rides) {
    while (line().length > CHAT_MAX && x.pts && dropBend(x.pts, 2)) {   }
  }
  while (line().length > CHAT_MAX && queue.length) queue.pop();
  while (line().length > CHAT_MAX && mobs.length > 1) mobs.pop();
  while (line().length > CHAT_MAX && said < forms.length - 1) said++;
  while (line().length > CHAT_MAX && dropBend(lead, 1)) {   }
  t.lastPacked = [...keys, ...queue.map((q) => q.key)];
  return line().length <= CHAT_MAX ? line() : null;
}

const EPIC_CODE = { pickup: "P", objective: "O", turnin: "T", dungeon: "D", errand: "S" };
function epicTakes(t) {
  const ids = [...new Set((t.data?.steps || []).filter((s) => s.kind === "pickup" && s.quest).map((s) => Number(s.quest)))];
  return ids.length ? ` +${ids.map((id) => id.toString(36)).join(".")}` : "";
}
const epicCode = (st) => st?.kind === "errand" ? `S${st.what}:${st.npc}`
  : st && EPIC_CODE[st.kind] && (st.kind === "dungeon" ? st.quests?.length : st.quest)
  ? `${EPIC_CODE[st.kind]}${(st.kind === "dungeon" ? st.quests : [st.quest]).join(".")}` : null;
const epicKey = (st) => `${epicCode(st)}|${st.text}`;
const lineWord = (s) => String(s ?? "").trim().replace(/\s+/g, "_");
const epicToken = (st) => st?.kind === "errand" ? `S${st.what}:${lineWord(st.npc)}` : epicCode(st);
