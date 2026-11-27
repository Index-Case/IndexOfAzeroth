// The Index of Azeroth. Copyright 2026 Index Case <indexofazeroth@pm.me>. PolyForm Strict 1.0.0, see LICENSE.md.
"use strict";
const MARK_SIZE = 20;
const PLAN_MARK_GAP = 1.3;
const PLAN_DOT = 2.4;
const PLAN_DOT_GLOW = 9;
const PLAN_DOT_POP = 480;
const PLAN_DOT_ALPHA = 0.6;
const PLAN_LINK = 1.4;
const PLAN_EDGE = 1;
const PLAN_EDGE_ALPHA = 0.45;
const PLAN_LINK_ALPHA = 0.7;
const PLAN_CHAIN_ALPHA = 0.6;
const PLAN_CHAIN_DASH = [5, 4];
const PLAN_LINK_GROW = 300;
const PLAN_THREAD = 1.3;
const PLAN_THREAD_ALPHA = 0.6;
const ORDER_TICKS = 1800;
const ORDER_TICK = [16, 70];
const BADGE_POP = 220;
const PLAN_BLOOM = 520;
const PLAN_GLINT = 760;
const STAGE_PAUSE = 380;
const PLAN_MAP_FADE = 1400;
const PLAN_DOT_PULSE = 900;
const PLAN_RING = 0.85;
const PLAN_RING_W = 2.2;
const PLAN_RING_GLIDE = 140;
const PLAN_RING_BEAT = 900;
const PLAN_MOVED_GLOW = 900;
const PLAN_DROP = 1.6;
const LINE_TINT = { kill: "kill-crimson", collect: "plan-collect", use: "use-yellow", talk: "plan-talk", handin: "forever-blue" };
const PLAN_CHAIN_TINT = "plan-chain";
const PLAN_THREAD_TINT = "bronze-lit";
const OBJECTIVE_LINE = { kill: "kill", loot: "collect", grab: "collect", buy: "collect", pickpocket: "collect", use: "use",
  heal: "use", talk: "talk", escort: "talk", event: "talk", explore: "talk" };
function lineKind(a, b) {
  if (b.k === "T") return a.k === "P" ? "talk" : "handin";
  if (b.k === "D") return "kill";
  return OBJECTIVE_LINE[b.ic] || "kill";
}
const QUEST_LINE = { P: 0, O: 1, D: 1, T: 2 };
const freshPlanMap = (key) => ({ key, quests: new Map(), dots: [], marks: new Map(), icons: new Set(), lines: new Map(),
  order: [], popsEnd: 0, ticksEnd: 0, ring: null, into: 0, flying: false, fade: 0, over: false, closing: false });
const planMap = freshPlanMap(null);
const stepSeen = (s) => `${s.k}|${s.ic || ""}|${s.what || ""}|${s.q ?? ""}|${s.i}|${s.at?.[0]}|${s.at?.[1]}`;

const clamp01 = (v) => Math.min(1, Math.max(0, v));
const easeOutCubic = (u) => 1 - (1 - u) ** 3;
const easeOutBack = (u) => 1 + 2.4 * (u - 1) ** 3 + 1.4 * (u - 1) ** 2;
const planAlong = (now, t, ms) => (lessMotion() ? (now >= t ? 1 : 0) : clamp01((now - t) / ms));

function planMapFor(key) {
  if (planMap.key === key) return;
  Object.assign(planMap, freshPlanMap(key));
  syncPlanLegend();
}

function planMapPop(fresh, now) {
  if (!fresh.length) return;
  const waiting = [...planMap.dots, ...planMap.marks.values()].filter((x) => x.t > now && x.t !== Infinity).sort((a, b) => a.t - b.t);
  const all = [...waiting, ...fresh], gap = lessMotion() ? 0 : spreadGap(all.length);
  all.forEach((x, k) => { x.t = now + k * gap; });
  planMap.popsEnd = Math.max(planMap.popsEnd, now + (all.length - 1) * gap + (lessMotion() ? 0 : STEP_POP));
  redraw();
}

function planMapQuests(quests, now) {
  if (planMap.over || planMap.closing) return;
  const lit = [], picked = new Set(quests.map((q) => q.id));
  for (const q of quests) {
    let rec = planMap.quests.get(q.id);
    if (!rec) {
      rec = {};
      planMap.quests.set(q.id, rec);
      const w = q.at ? fracToWorld(q.at[0], q.at[1] / 100, q.at[2] / 100) : null;
      if (w) lit.push({ w, t: Infinity, q: q.id });
    }
    Object.assign(rec, { name: q.name || rec.name || "", pre: q.pre || [], crumb: !!q.crumb });
  }
  for (const d of planMap.dots) {
    if (picked.has(d.q)) d.gone = 0;
    else d.gone ||= now;
  }
  planMap.dots.push(...lit);
  planMapPop(lit, now);
}

function planMapPlaced(steps, now) {
  planMapAdd(steps.map((s) => [stepSeen(s), s]), now);
}

function planMapAdd(steps, now) {
  if (planMap.over || planMap.closing) return;
  const fresh = [], icons = planMap.icons.size;
  for (const [key, s] of steps) {
    if (planMap.marks.has(key)) continue;
    const m = { s, t: Infinity, n: 0, was: 0, nt: 0 };
    planMap.marks.set(key, m);
    planMap.icons.add(stepIconName(s));
    fresh.push(m);
    if (s.q == null) continue;
    const line = planMap.lines.get(s.q) || [];
    line.push(m);
    line.sort((a, b) => (QUEST_LINE[a.s.k] ?? 1) - (QUEST_LINE[b.s.k] ?? 1));
    planMap.lines.set(s.q, line);
  }
  if (planMap.icons.size !== icons) syncPlanLegend();
  planMapPop(fresh, now);
}

const shownNumber = (m, now) => (now >= m.nt ? m.n : m.was);

function planMapOrder(steps, now) {
  if (planMap.over || planMap.closing) return;
  const times = new Map(), keys = steps.map((s) => {
    const key = stepSeen(s), n = (times.get(key) || 0) + 1;
    times.set(key, n);
    return n > 1 ? `${key}#${n}` : key;
  });
  planMapAdd(keys.map((key, i) => [key, steps[i]]), now);
  const old = planMap.order;
  let f = 0;
  while (f < keys.length && keys[f] === old[f]) f++;
  if (f === keys.length && keys.length === old.length) return;
  const still = lessMotion(), T0 = still ? now : Math.max(now, planMap.popsEnd + STAGE_PAUSE);
  const tick = Math.min(ORDER_TICK[1], Math.max(ORDER_TICK[0], ORDER_TICKS / Math.max(1, keys.length - f)));
  const held = new Set(keys), quests = new Set(steps.map((s) => s.q).filter((q) => q != null));
  for (const [key, m] of planMap.marks) {
    if (held.has(key)) m.gone = 0;
    else if (!m.gone) Object.assign(m, { was: shownNumber(m, now), n: 0, nt: T0, gone: T0 });
  }
  for (const d of planMap.dots) if (d.q != null) d.gone = quests.has(d.q) ? 0 : d.gone || T0;
  keys.forEach((key, i) => {
    if (i < f) return;
    const m = planMap.marks.get(key), was = shownNumber(m, now);
    Object.assign(m, { was, n: i + 1, nt: still ? now : T0 + (i - f) * tick, moved: !!was && was !== i + 1 });
  });
  planMap.order = keys;
  planMap.ticksEnd = still ? now : T0 + Math.max(0, keys.length - f - 1) * tick + BADGE_POP;
  redraw();
}

function planMapInto(now) {
  if (planMap.into || planMap.over || planMap.closing) return;
  planMap.into = lessMotion() ? now : Math.max(now, planMap.popsEnd, planMap.ticksEnd) + STAGE_PAUSE;
  redraw();
}

function planMapHoldsLegs() {
  return planMap.marks.size > 0 && !planMap.fade && !planMap.over && !planMap.closing && !lessMotion();
}

function planMapDone(now) {
  if (!planMap.key || planMap.closing) return;
  Object.assign(planMap, { closing: true, flying: true, fade: planMap.fade || now });
  if (planMap.over || lessMotion() || (!planMap.marks.size && !planMap.dots.length)) Object.assign(planMap, freshPlanMap(null));
  syncPlanLegend();
  redraw();
}

const orderedMarks = () => planMap.order.map((key) => planMap.marks.get(key)).filter(Boolean);

const goneLeft = (x, now) => (x.gone && now >= x.gone ? (lessMotion() ? 0 : clamp01(1 - (now - x.gone) / PLAN_MAP_FADE)) : 1);

function planMapRing(step, now) {
  const key = step ? stepSeen(step) : null, was = planMap.ring;
  if ((was?.key ?? null) === key) return;
  planMap.ring = key ? { key, from: was?.key ?? null, t: now } : null;
  redraw();
}

function planMapForget(now) {
  for (const [key, m] of planMap.marks) {
    if (!m.gone || goneLeft(m, now) > 0) continue;
    planMap.marks.delete(key);
    const line = planMap.lines.get(m.s.q);
    if (line) line.splice(line.indexOf(m), 1);
  }
  planMap.dots = planMap.dots.filter((d) => !d.gone || goneLeft(d, now) > 0);
}

function animatePlanMap(now) {
  if (!planMap.key) return false;
  if (planMap.into && now >= planMap.into && !planMap.flying) planMap.flying = true;
  if (planMap.flying && !planMap.closing && !planMap.fade) {
    if (lessMotion()) planMap.fade = now - PLAN_MAP_FADE;
    else {
      const due = orderedMarks().filter((m) => !m.sent && now >= m.t + STEP_POP);
      for (const m of due) m.sent = true;
      if (due.length) flyPlaced(due.map((m) => m.s));
      if (!stepFlights.waiting.length && orderedMarks().every((m) => m.sent)) planMap.fade = now;
    }
    if (planMap.fade) {
      syncPlanLegend();
      followPlanWork();
    }
  }
  if (planMap.fade && now - planMap.fade >= PLAN_MAP_FADE) {
    if (planMap.closing) Object.assign(planMap, freshPlanMap(null));
    else planMap.over = true;
    syncPlanLegend();
    return false;
  }
  planMapForget(now);
  if (planMap.over || lessMotion()) return false;
  const shown = planMap.marks.size > 0 || planMap.dots.length > 0;
  const going = [...planMap.marks.values(), ...planMap.dots].some((x) => x.gone);
  const glowing = [...planMap.marks.values()].some((m) => m.moved && now < m.nt + PLAN_MOVED_GLOW);
  return (shown && now < Math.max(planMap.popsEnd, planMap.ticksEnd) + Math.max(PLAN_GLINT, PLAN_DOT_PULSE)) || going || glowing
    || (!!planMap.ring && !planMap.flying) || !!planMap.into || !!planMap.fade;
}
on("animate", animatePlanMap);

function drawPlanMap(size, scale) {
  const now = performance.now();
  planLinesDrawn.length = 0;
  if (!options.get("planmap")) return;
  placePlanStage(size, scale);
  if (planMap.key && !planMap.over) {
    const left = planMap.fade ? clamp01(1 - (now - planMap.fade) / PLAN_MAP_FADE) : 1;
    const at = planMapSpots(now, size, scale);
    if (left > 0) {
      drawPlanDots(now, size, scale, left);
      drawPlanThread(now, at, left);
      drawPlanLines(now, at, left);
    }
    drawPlanWaysNow(size, scale);
    drawPlanMarks(now, at, left);
    if (!planMap.flying) drawPlanRing(now, at);
    return;
  }
  drawPlanWaysNow(size, scale);
}
on("livedraw", drawPlanMap);

function planMapSpots(now, size, scale) {
  const at = new Map(), together = new Map();
  for (const m of planMap.marks.values()) {
    if (m.t > now) continue;
    const p = worldOnScreen(m.s.i, m.s.at[0], m.s.at[1], size, scale);
    if (!p) continue;
    at.set(m, p);
    const place = `${m.s.i}|${m.s.at[0]}|${m.s.at[1]}`;
    together.set(place, [...(together.get(place) || []), m]);
  }
  for (const group of together.values()) {
    const cols = Math.ceil(Math.sqrt(group.length)), rows = Math.ceil(group.length / cols), step = MARK_SIZE * PLAN_MARK_GAP;
    group.forEach((m, k) => {
      const row = Math.floor(k / cols), inRow = row === rows - 1 ? group.length - row * cols : cols;
      const dx = (k % cols - (inRow - 1) / 2) * step, dy = (row - (rows - 1) / 2) * step, p = at.get(m);
      m.s.fan = [dx, dy];
      at.set(m, [p[0] + dx, p[1] + dy]);
    });
  }
  return at;
}

function drawPlanDots(now, size, scale, left) {
  ctx.save();
  for (const d of planMap.dots) {
    if (d.t > now) continue;
    const p = worldOnScreen(d.w.inst, d.w.n, d.w.w, size, scale);
    if (!p) continue;
    const u = planAlong(now, d.t, PLAN_DOT_POP), a = PLAN_DOT_ALPHA * easeOutCubic(u) * left * goneLeft(d, now);
    if (a <= 0) continue;
    const pulse = planAlong(now, d.t, PLAN_DOT_PULSE);
    if (pulse > 0 && pulse < 1) {
      ctx.lineWidth = 1.5; ctx.strokeStyle = tint("gold-pale", 0.7 * (1 - pulse) * left);
      ctx.beginPath(); ctx.arc(p[0], p[1], PLAN_DOT_GLOW * (0.4 + 1.4 * easeOutCubic(pulse)), 0, Math.PI * 2); ctx.stroke();
    }
    const glow = ctx.createRadialGradient(p[0], p[1], 0, p[0], p[1], PLAN_DOT_GLOW);
    glow.addColorStop(0, tint("poi-glow", 0.45 * a));
    glow.addColorStop(1, tint("poi-glow", 0));
    ctx.fillStyle = glow;
    ctx.beginPath(); ctx.arc(p[0], p[1], PLAN_DOT_GLOW, 0, Math.PI * 2); ctx.fill();
    ctx.beginPath(); ctx.arc(p[0], p[1], PLAN_DOT * Math.max(0, easeOutBack(u)), 0, Math.PI * 2);
    ctx.fillStyle = tint("gold-pale", a); ctx.fill();
    ctx.lineWidth = 1; ctx.strokeStyle = tint("bronze-ink", 0.8 * a); ctx.stroke();
  }
  ctx.restore();
}

function planLine(a, b, u, colour, width, alpha, { dash = null, edge = "black" } = {}) {
  const dx = b[0] - a[0], dy = b[1] - a[1], len = Math.hypot(dx, dy), trim = MARK_SIZE * 0.55;
  if (len <= 2 * trim || u <= 0) return null;
  const ux = dx / len, uy = dy / len, from = [a[0] + ux * trim, a[1] + uy * trim];
  const to = [from[0] + ux * (len - 2 * trim) * u, from[1] + uy * (len - 2 * trim) * u];
  ctx.setLineDash(dash || []);
  for (const [w, c] of [[width + 2 * PLAN_EDGE, tint(edge, PLAN_EDGE_ALPHA * alpha)], [width, tint(colour, alpha)]]) {
    ctx.lineWidth = w; ctx.strokeStyle = c;
    ctx.beginPath(); ctx.moveTo(...from); ctx.lineTo(...to); ctx.stroke();
  }
  return [from, to];
}

function drawPlanThread(now, at, left) {
  const marks = orderedMarks();
  ctx.save(); ctx.lineCap = "round";
  for (let i = 1; i < marks.length; i++) {
    const a = at.get(marks[i - 1]), b = at.get(marks[i]), m = marks[i];
    if (!a || !b || now < m.nt || !m.n) continue;
    planLine(a, b, easeOutCubic(planAlong(now, m.nt, BADGE_POP)), PLAN_THREAD_TINT, PLAN_THREAD, PLAN_THREAD_ALPHA * left,
      { edge: "bronze-ink" });
  }
  ctx.restore();
}

const planLinesDrawn = [];
function drawPlanLines(now, at, left) {
  ctx.save(); ctx.lineCap = "round";
  for (const [q, line] of planMap.lines) {
    for (let i = 1; i < line.length; i++) {
      const a = at.get(line[i - 1]), b = at.get(line[i]);
      if (!a || !b) continue;
      const kind = lineKind(line[i - 1].s, line[i].s);
      const u = planAlong(now, Math.max(line[i - 1].t, line[i].t) + STEP_POP * 0.4, PLAN_LINK_GROW);
      const fading = Math.min(goneLeft(line[i - 1], now), goneLeft(line[i], now));
      if (fading <= 0) continue;
      const drawn = planLine(a, b, easeOutCubic(u), LINE_TINT[kind], PLAN_LINK, PLAN_LINK_ALPHA * left * fading);
      if (drawn) planLinesDrawn.push({ a: drawn[0], b: drawn[1], q, kind });
    }
  }
  for (const [q, rec] of planMap.quests) {
    const to = planMap.lines.get(q)?.[0];
    for (const p of rec.pre || []) {
      const from = planMap.lines.get(p)?.at(-1);
      if (!from || !to || !at.get(from) || !at.get(to)) continue;
      const u = planAlong(now, Math.max(from.t, to.t) + STEP_POP * 0.4, PLAN_LINK_GROW);
      const drawn = planLine(at.get(from), at.get(to), easeOutCubic(u), PLAN_CHAIN_TINT, PLAN_LINK,
        PLAN_CHAIN_ALPHA * left * Math.min(goneLeft(from, now), goneLeft(to, now)), { dash: PLAN_CHAIN_DASH });
      if (drawn) planLinesDrawn.push({ a: drawn[0], b: drawn[1], q, kind: "chain", after: p });
    }
  }
  ctx.restore();
}

const PLAN_HOVER = 5;
const PLAN_WORDS = { head: wordsOf("page.planning.head"), line: wordsOf("page.planning.line"), mark: wordsOf("page.planning.mark") };
function planLineTipAt(mx, my) {
  let hit = null, best = PLAN_HOVER;
  for (const d of planLinesDrawn) {
    const dist = segDist([mx, my], d.a, d.b);
    if (dist <= best) { hit = d; best = dist; }
  }
  if (!hit) return null;
  const name = planMap.quests.get(hit.q)?.name;
  const kind = (hit.kind === "chain" && word("page.planning.tip.chain", { after: planMap.quests.get(hit.after)?.name }))
    || PLAN_WORDS.line[hit.kind];
  return name ? html`<b>${name}</b><small>${kind}</small>` : html`<b>${kind}</b>`;
}

const planMarkOrder = () => [...new Set([PLAN_ICON.P, ...Object.values(PLAN_OBJECTIVE), PLAN_ICON.D, PLAN_ICON.T,
  ...Object.values(PLAN_ERRAND)])];
function planLegendHtml(icons) {
  const line = (colour, words, dashed = false) =>
    html`<span class="pl-item"><i class="pl-line${dashed ? " dashed" : ""}" style="--c:var(--${colour})"></i>${words}</span>`;
  const lines = [...Object.entries(LINE_TINT).map(([kind, colour]) => line(colour, PLAN_WORDS.line[kind])),
    line(PLAN_CHAIN_TINT, PLAN_WORDS.line.chain, true), line(PLAN_THREAD_TINT, PLAN_WORDS.line.order)];
  const marks = planMarkOrder().filter((name) => icons.has(name))
    .map((name) => html`<span class="pl-item"><img src="/ui/${name}.png" alt="">${PLAN_WORDS.mark[name]}</span>`);
  const row = (head, items) => html`<div class="pl-row"><span class="pl-head">${head}</span><span class="pl-items">${items}</span></div>`;
  return html`${row(PLAN_WORDS.head.lines, lines)}${marks.length ? row(PLAN_WORDS.head.marks, marks) : ""}`.markup;
}
let planLegendSaid = null;
function syncPlanLegend() {
  const box = $("plan-legend"), shown = !!planMap.key && !planMap.fade && !planMap.over && options.get("planmap");
  const said = shown ? [...planMap.icons].join() : null;
  if (said === planLegendSaid) return;
  planLegendSaid = said;
  box.hidden = !shown;
  document.body.classList.toggle("plan-legend-open", shown);
  if (!shown) return;
  box.innerHTML = planLegendHtml(planMap.icons);
  placePlanLegend();
}
function placePlanLegend() {
  const box = $("plan-legend");
  if (box.hidden) return;
  const far = `${footFar(document.querySelector(".mapkeys")?.getBoundingClientRect(),
    document.querySelector(".sidestack")?.getBoundingClientRect(), box.getBoundingClientRect(), innerWidth, columnSide())}px`;
  if (box.style.getPropertyValue("--pl-far") !== far) box.style.setProperty("--pl-far", far);
  document.body.style.setProperty("--plan-legend-h", `${box.offsetHeight}px`);
}
const planLegendWatch = new ResizeObserver(placePlanLegend);
for (const el of [$("plan-legend"), document.querySelector(".mapkeys"), document.querySelector(".sidestack")]) if (el) planLegendWatch.observe(el);
on("column", placePlanLegend);

function drawPlanMarks(now, at, left) {
  for (const [m, spot] of at) {
    if (m.s.lifted && now >= m.s.lifted) continue;
    const alpha = ((m.n && !planMap.closing) || !planMap.fade ? 1 : left) * goneLeft(m, now);
    if (alpha <= 0) continue;
    const u = planAlong(now, m.t, STEP_POP), size = MARK_SIZE * Math.max(0, easeOutBack(u));
    const p = m.s.k === "S" ? [spot[0], spot[1] - (1 - easeOutCubic(u)) * MARK_SIZE * PLAN_DROP] : spot;
    const moved = m.moved && now >= m.nt ? planAlong(now, m.nt, PLAN_MOVED_GLOW) : 1;
    if (moved < 1) {
      const r = MARK_SIZE * (0.7 + 0.5 * moved), glow = ctx.createRadialGradient(p[0], p[1], 0, p[0], p[1], r);
      glow.addColorStop(0, tintBetween("bronze-lit", "gold-bright", 1 - moved));
      glow.addColorStop(1, tint("gold-bright", 0));
      ctx.save();
      ctx.globalAlpha = 0.65 * (1 - moved) * alpha;
      ctx.fillStyle = glow;
      ctx.beginPath(); ctx.arc(p[0], p[1], r, 0, Math.PI * 2); ctx.fill();
      ctx.restore();
    }
    const bloom = planAlong(now, m.t, PLAN_BLOOM);
    if (bloom < 1) {
      const r = MARK_SIZE * (0.5 + 0.7 * bloom), glow = ctx.createRadialGradient(p[0], p[1], 0, p[0], p[1], r);
      glow.addColorStop(0, tint("glint", 0.5 * (1 - bloom) * alpha));
      glow.addColorStop(1, tint("glint", 0));
      ctx.fillStyle = glow;
      ctx.beginPath(); ctx.arc(p[0], p[1], r, 0, Math.PI * 2); ctx.fill();
    }
    const img = uiImage(stepIconName(m.s));
    if (img.complete && img.naturalWidth && size > 0) {
      ctx.save();
      ctx.globalAlpha = alpha * Math.min(1, u * 3);
      ctx.shadowColor = tint("black", 0.85); ctx.shadowBlur = 3; ctx.shadowOffsetY = 1;
      ctx.drawImage(img, p[0] - size / 2, p[1] - size / 2, size, size);
      ctx.restore();
    }
    if (planMap.quests.get(m.s.q)?.crumb) drawPlanGlint(p, planAlong(now, m.t, PLAN_GLINT), alpha);
    drawPlanBadge(m, p, now, alpha);
  }
}

function drawPlanRing(now, at) {
  const ring = planMap.ring, to = ring && planMap.marks.get(ring.key), q = to && at.get(to);
  if (!q || goneLeft(to, now) < 1) return;
  const from = ring.from && planMap.marks.get(ring.from), f = from && at.get(from), u = easeOutCubic(planAlong(now, ring.t, PLAN_RING_GLIDE));
  const p = f ? [f[0] + (q[0] - f[0]) * u, f[1] + (q[1] - f[1]) * u] : q;
  const beat = lessMotion() ? 1 : 0.5 - 0.5 * Math.cos(2 * Math.PI * (now % PLAN_RING_BEAT) / PLAN_RING_BEAT);
  ctx.save();
  for (const [w, c] of [[PLAN_RING_W + 2 * PLAN_EDGE, tint("bronze-ink", 0.8)], [PLAN_RING_W, tintBetween("bronze-lit", "gold-bright", beat)]]) {
    ctx.lineWidth = w; ctx.strokeStyle = c;
    ctx.beginPath(); ctx.arc(p[0], p[1], MARK_SIZE * PLAN_RING, 0, Math.PI * 2); ctx.stroke();
  }
  ctx.restore();
}

function drawPlanGlint(p, g, alpha) {
  if (g <= 0 || g >= 1) return;
  const s = MARK_SIZE * 0.75 * Math.sin(Math.PI * g), x = p[0] - MARK_SIZE * 0.32, y = p[1] - MARK_SIZE * 0.32;
  ctx.save();
  ctx.strokeStyle = tint("glint", 0.55 * (1 - g) * alpha); ctx.lineWidth = 1.25;
  ctx.beginPath(); ctx.arc(p[0], p[1], MARK_SIZE * (0.55 + 0.6 * g), 0, Math.PI * 2); ctx.stroke();
  ctx.translate(x, y); ctx.rotate(g * Math.PI / 3);
  ctx.fillStyle = tint("glint", 0.95 * alpha);
  ctx.shadowColor = tint("gold-bright", 0.9 * alpha); ctx.shadowBlur = 6;
  ctx.beginPath();
  for (let k = 0; k < 8; k++) {
    const r = k % 2 ? s * 0.16 : s, t = k * Math.PI / 4;
    ctx.lineTo(Math.cos(t) * r, Math.sin(t) * r);
  }
  ctx.closePath(); ctx.fill();
  ctx.restore();
}

function drawPlanBadge(m, p, now, alpha) {
  const n = shownNumber(m, now);
  if (!n) return;
  const b = now >= m.nt ? planAlong(now, m.nt, BADGE_POP) : 1, flash = 1 - b;
  const k = m.was ? 1 + 0.22 * Math.sin(Math.PI * b) : Math.max(0, easeOutBack(b));
  if (k <= 0) return;
  const r = n >= 100 ? 9 : n >= 10 ? 8 : 7, x = p[0] + MARK_SIZE * 0.48, y = p[1] - MARK_SIZE * 0.48;
  ctx.save();
  ctx.globalAlpha = alpha;
  ctx.translate(x, y); ctx.scale(k, k);
  drawRingMarker(0, 0, { r, edge: 1, width: 1.25, fill: tint("bronze-ink", 0.92), ring: tintBetween("seal-gold", "gold-bright", flash),
    text: n, font: `${n >= 100 ? 8.5 : 10}px ${MARK_FONT}`, color: tintBetween("gold-pale", "white-hot", flash), dy: 0.5 });
  ctx.restore();
}

if (typeof module === "object") {
  module.exports = { MARK_SIZE, PLAN_MARK_GAP, PLAN_DOT, PLAN_DOT_GLOW, PLAN_DOT_POP, PLAN_DOT_ALPHA, PLAN_LINK, PLAN_EDGE,
    PLAN_EDGE_ALPHA, PLAN_LINK_ALPHA, PLAN_CHAIN_ALPHA, PLAN_CHAIN_DASH, PLAN_LINK_GROW, PLAN_THREAD, PLAN_THREAD_ALPHA, ORDER_TICKS,
    ORDER_TICK, BADGE_POP, PLAN_BLOOM, PLAN_GLINT, STAGE_PAUSE, PLAN_MAP_FADE, PLAN_DOT_PULSE, PLAN_RING, PLAN_RING_W, PLAN_RING_GLIDE,
    PLAN_RING_BEAT, PLAN_MOVED_GLOW, PLAN_DROP, LINE_TINT, PLAN_CHAIN_TINT, PLAN_THREAD_TINT, OBJECTIVE_LINE, lineKind, QUEST_LINE,
    freshPlanMap, planMap, stepSeen, clamp01, easeOutCubic, easeOutBack, planAlong, planMapFor, planMapPop, planMapQuests,
    planMapPlaced, planMapAdd, shownNumber, planMapOrder, planMapInto, planMapHoldsLegs, planMapDone, orderedMarks, goneLeft,
    planMapRing, planMapForget, animatePlanMap, drawPlanMap, planMapSpots, drawPlanDots, planLine, drawPlanThread, planLinesDrawn,
    drawPlanLines, PLAN_HOVER, PLAN_WORDS, planLineTipAt, planMarkOrder, planLegendHtml, syncPlanLegend, placePlanLegend,
    planLegendWatch, drawPlanMarks, drawPlanRing, drawPlanGlint, drawPlanBadge };
}
