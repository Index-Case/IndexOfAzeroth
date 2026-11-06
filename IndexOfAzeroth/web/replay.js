// The Index of Azeroth. Copyright 2026 Index Case <indexofazeroth@pm.me>. PolyForm Strict 1.0.0, see LICENSE.md.
"use strict";

const replay = {
  on: false, days: [], day: null, char: null, data: null, line: null, t: 0, from: 0, to: 0,
  playing: false, dir: 1, speed: 1, pauses: new Set(), effects: [], bubbles: [], icons: {}, me: null,
  className: null, lastFrame: 0, pick: null, asked: 0, onward: false, fade: false,
};

function replayShown() { return !!options.get("replay"); }

const RP_FOLLOW_ICON = document.querySelector("#btn-follow svg")?.outerHTML || "";
const followingReplay = () => app.view.follow && app.view.target === "replay";

function replaySuiteHtml() {
  const pauses = REPLAY_PAUSES.map((p) => `<label class="rp-pause"><input type="checkbox" data-rp-pause="${p.id}"${replay.pauses.has(p.id) ? " checked" : ""}> ${p.name}</label>`).join("");
  return `<div class="rp-row">
    <span class="layer-pick"><button class="key small rp-day" id="rp-day" aria-haspopup="true" aria-expanded="false"
      title="Pick the day to play back">${replay.day ? esc(dayName(replay.day)) : "No day recorded yet"}</button>
      <div class="layer-menu rp-days" id="rp-days" role="menu" hidden></div></span>
    <button class="key small square" data-rp="back" title="Step back one recorded event (while paused)">⏮</button>
    <button class="key small square" data-rp="rewind" title="Play the day backwards">⏪</button>
    <button class="key small square" data-rp="play" id="rp-play" title="Play or pause the day">${replay.playing ? "⏸" : "▶"}</button>
    <button class="key small square" data-rp="forward" title="Fast forward: play at the next speed up">⏩</button>
    <button class="key small square" data-rp="next" title="Step forward one recorded event (while paused)">⏭</button>
    <span class="rp-speeds"><button class="key small square" data-rp="slower" title="Slower">&minus;</button>
      <span class="rp-speed-now" id="rp-speed" title="How many times faster than it was played">${replay.speed}x</span>
      <button class="key small square" data-rp="faster" title="Faster">+</button></span>
    <span class="layer-pick"><button class="key small" id="rp-pause-key" aria-haspopup="true" aria-expanded="false"
      title="Pick what the replay pauses on when it reaches it">Pause on</button>
      <div class="layer-menu rp-pauses" id="rp-pauses" role="menu" hidden>${pauses}</div></span>
    <button class="key small rp-toggle" data-rp="onward" aria-pressed="${replay.onward}"
      title="At the end of a day the replay plays on into the next one, or into the day before when playing backwards">Next day</button>
    <button class="key small rp-toggle" data-rp="fade" aria-pressed="${replay.fade}"
      title="The walked path fades from faint at its start to full strength at the arrow">Path fade</button>
    <button class="key small" id="rp-follow" data-rp="follow" aria-pressed="${followingReplay()}"
      title="Keep the map centred on the replayed character">${RP_FOLLOW_ICON}Follow</button>
    <span class="rp-clock" id="rp-clock">${replay.data ? clockOf(replay.t) : ""}</span>
    ${helpButton("replay")}
    <button class="key small square x-mark" data-rp="close" title="Closes the replay and switches Replay off in Options">&times;</button>
  </div>
  <div class="rp-time${replayHeld() ? " held" : ""}" id="rp-time">
    <div class="rp-edge rp-edge-start" id="rp-edge-start" data-rp-edge="-1" hidden></div>
    <div class="rp-edge rp-edge-end" id="rp-edge-end" data-rp-edge="1" hidden></div>
    <div class="rp-marks" id="rp-marks"></div><div class="rp-band" id="rp-band"></div><div class="rp-scale" id="rp-scale"
      title="The mouse wheel over the timeline zooms in and out around the pointer. Dragging across the whole day zooms into that stretch. Zoomed in, dragging moves along the day and Shift with a drag zooms into a stretch. A double-click shows the whole day again"></div>
    <div class="rp-pick" id="rp-pick" hidden></div><div class="rp-head" id="rp-head"></div>
  </div>`;
}

function replayTimeWidth() { return $("rp-time")?.getBoundingClientRect?.().width || 1000; }

function renderReplayTime() {
  const marksBox = $("rp-marks"), head = $("rp-head");
  if (!marksBox || !replay.line) return;
  const span = Math.max(1e-6, replay.to - replay.from), px = replayTimeWidth();
  const at = (t) => `${((t - replay.from) / span * 100).toFixed(3)}%`;
  marksBox.innerHTML = marksShown(replay.line.marks, replay.from, replay.to, px).map((m) => {
    const d = RP_EVENTS[m.kind];
    return `<span class="rp-mark rp-ring-${d.ring}" style="left:${at(m.t)}" data-rp-at="${m.t}" title="${esc(markWords(m))}"><img src="/icon/${d.icon}.jpg" alt=""></span>`;
  }).join("");
  const band = $("rp-band");
  if (band && !band.title && !band.dataset?.title) band.title = bandWords(rpBandAt(replay.line.band, replay.t));
  if (band) band.innerHTML = bandShown(replay.line.band, replay.from, replay.to, px).map((s) =>
    `<i class="rp-band-${s.kind}" style="left:${at(s.t)};width:${((s.to - s.t) / span * 100).toFixed(3)}%"></i>`).join("");
  const scale = $("rp-scale");
  if (scale) scale.innerHTML = ticksFor(replay.from, replay.to, px).ticks.map((k) =>
    `<i class="rp-tick${k.major ? " major" : ""}" style="left:${at(k.t)}">${k.label ? `<b>${k.label}</b>` : ""}</i>`).join("");
  head.style.left = at(replay.t);
  for (const [id, dir, words] of [["rp-edge-start", -1, "Go back to"], ["rp-edge-end", 1, "Go on to"]]) {
    const edge = $(id), day = dayBeside(dir);
    if (!edge) continue;
    edge.hidden = !day;
    edge.title = day ? `${words} ${dayName(day)}` : "";
  }
}

function renderReplayClock() {
  const put = (el, text) => { if (el && el.textContent !== text) el.textContent = text; };
  put($("rp-clock"), replay.data ? clockOf(replay.t) : "");
  put($("rp-play"), replay.playing ? "⏸" : "▶");
  put($("rp-speed"), `${replay.speed}x`);
  const head = $("rp-head"), left = `${((replay.t - replay.from) / Math.max(1, replay.to - replay.from) * 100).toFixed(3)}%`;
  if (head && replay.line && head.style.left !== left) head.style.left = left;
}

function renderReplay() {
  const box = $("replay");
  box.hidden = !replay.on;
  document.body.classList.toggle("replay-open", replay.on);
  if (!replay.on) return;
  box.innerHTML = replaySuiteHtml();
  renderReplayTime();
  placeReplay();
}

function placeReplay() {
  const box = $("replay");
  if (box.hidden) return;
  const right = footRight(document.querySelector(".mapkeys")?.getBoundingClientRect?.(),
    document.querySelector(".sidestack")?.getBoundingClientRect?.(), box.getBoundingClientRect?.(), innerWidth);
  const was = box.style.getPropertyValue("--rp-right"), now = `${right}px`;
  if (was !== now) box.style.setProperty("--rp-right", now);
  document.body.style.setProperty("--replay-h", `${box.offsetHeight || 64}px`);
}

function syncReplay() {
  if (replayShown() && !replay.on) openReplay();
  else if (!replayShown() && replay.on) closeReplay();
}

async function loadReplayDays() {
  const ask = ++replay.asked;
  const got = await getJson("/api/replay/days", { force: true }).catch(() => null);
  if (ask !== replay.asked || !got) return;
  replay.char = got.char;
  replay.days = (got.days || []).map((d) => d.day).reverse();
  if (!replay.day && replay.days.length) await loadReplayDay(replay.days[0]);
  else renderReplay();
}

async function loadReplayDay(day) {
  const ask = ++replay.asked;
  const q = new URLSearchParams({ day, ...(replay.char ? { char: replay.char } : {}) });
  const got = await getJson(`/api/replay/day?${q}`, { force: true }).catch(() => null);
  if (ask !== replay.asked || !got) return;
  replay.day = day;
  replay.data = got;
  replay.me = got.me;
  replay.icons = got.icons || {};
  replay.className = got.className || null;
  replay.line = replayTimeline(got.events, got.me);
  replay.from = replay.line.from ?? 0;
  replay.to = replay.line.to ?? 0;
  replay.t = replay.from;
  replay.playing = false;
  clearReplayEffects();
  placeReplayYou();
  renderReplay();
  redraw();
}

function openReplay() {
  replay.on = true;
  setFollow(true, "replay");
  renderReplay();
  loadReplayDays();
}

function closeReplay() {
  Object.assign(replay, { on: false, playing: false });
  placeReplayYou();
  if (app.view.target === "replay") setFollow(app.view.follow);
  clearReplayEffects();
  renderReplay();
  requestUpdate();
}

function clearReplayEffects() { replay.effects = []; replay.bubbles = []; }

function placeReplayYou() {
  const at = replay.line ? trackAt(replay.line.track, replay.t) : null;
  app.replayYou = replay.on && at ? at : null;
  checkIndoors();
}

function seekReplay(t) {
  replay.t = Math.min(replay.to, Math.max(replay.from, t));
  clearReplayEffects();
  placeReplayYou();
  renderReplayClock();
  redraw();
}

function replayFrame(now) {
  if (!replay.on) return false;
  placeReplay();
  if (!replay.line) return false;
  const wall = performance.now(), held = replayHeld();
  if (replay.playing && !held) {
    const dt = replay.lastFrame ? Math.min(0.25, (wall - replay.lastFrame) / 1000) : 0;
    const was = replay.t;
    let next = was + dt * replay.speed * replay.dir;
    const stop = pauseAt(replay.line.marks, was, next, replay.pauses);
    if (stop != null) { next = stop; replay.playing = false; }
    if (replay.dir > 0 ? next >= replay.to : next <= replay.from) {
      next = Math.min(replay.to, Math.max(replay.from, next)); replay.playing = false;
      if (replay.onward && dayBeside(replay.dir)) rollDay(replay.dir, true);
    }
    replay.t = next;
    if (replay.dir > 0) playReplayEvents(was, next, wall);
    placeReplayYou();
    renderReplayClock();
  }
  const moving = replay.playing && !held;
  replay.lastFrame = moving ? wall : 0;
  replay.effects = replay.effects.filter((f) => wall - f.born < f.life);
  replay.bubbles = replay.bubbles.filter((f) => wall - f.born < f.life);
  return moving || replay.effects.length > 0 || replay.bubbles.length > 0;
}

function dayBeside(dir) {
  if (!replay.line || (dir > 0 ? replay.to < replay.line.to : replay.from > replay.line.from)) return null;
  const i = replay.days.indexOf(replay.day);
  return i < 0 ? null : replay.days[dir > 0 ? i - 1 : i + 1] || null;
}

async function rollDay(dir, play) {
  const day = dayBeside(dir);
  if (!day) return false;
  await loadReplayDay(day);
  if (replay.day !== day || !replay.line) return false;
  if (dir < 0) replay.t = replay.to;
  replay.playing = play;
  placeReplayYou();
  renderReplay();
  redraw();
  return true;
}

function playReplayEvents(a, b, wall) {
  const fx = replay.line.fx;
  for (let i = lastAt(fx, a) + 1; i < fx.length && fx[i].t <= b; i++) {
    for (const f of effectsOf(fx[i], replay.me, replay.icons)) {
      if (f.kind === "bubble") {
        replay.bubbles.push({ ...f, born: wall, life: BUBBLE_MS });
        if (replay.bubbles.length > BUBBLES_MOST) replay.bubbles.shift();
      } else if (replay.effects.length < EFFECTS_MOST) {
        replay.effects.push({ ...f, born: wall, life: f.kind === "card" ? FLY_MS : SCT_MS, seed: replay.effects.length });
      }
    }
  }
}


const replayLook = () => arrowLook(CLASS_COLORS[replay.className] || classColor(),
  { lit: tint("arrow-lit"), gold: tint("gold"), shade: tint("arrow-shade"), rim: tint("black") });

function unitOnScreen(guid, size, scale) {
  const u = replay.line?.units.get(guid), at = u && unitAt(u, replay.t);
  return at ? worldOnScreen(at.at[0], at.at[1], at.at[2], size, scale) : null;
}

const replayOver = new OverLight($("map-replay-you"));
function drawReplay(size, scale) {
  if (!replay.on || !replay.line) return replayOver.hide();
  drawReplayTrack(size, scale);
  drawReplayUnits(size, scale);
  const you = app.replayYou, me = you && !you.hidden ? toScreen(you.x, you.y, size, scale, you.map) : null;
  if (!me || !Number.isFinite(me[0])) return replayOver.hide();
  const angle = -(you.f ?? 0) + app.view.rot, look = replayLook(), shadow = mapLight.arrowShadow();
  const glow = CLASS_COLORS[replay.className] || classColor() || tint("gold");
  replayOver.show(me[0], me[1], JSON.stringify([+angle.toFixed(3), look, shadow, glow]), (g, px, py) => {
    paintArrow(g, px, py, angle, look, shadow, dpr);
    paintArrowGlow(g, px, py, angle, glow, dpr);
  }, dpr);
  drawReplayEffects(me, you, size, scale);
}

function drawReplayTrack(size, scale) {
  const track = replay.line.track, look = replayLook();
  const runs = (from, to) => {
    const out = [];
    let run = null;
    for (let i = Math.max(0, lastAt(track, from)); i < track.length && track[i].t <= to; i++) {
      const p = track[i];
      if (p.gone) { run = null; continue; }
      const q = toScreen(p.x, p.y, size, scale, p.m);
      if (!Number.isFinite(q[0])) { run = null; continue; }
      if (run && Math.hypot(q[0] - run.at(-1)[0], q[1] - run.at(-1)[1]) < 2) continue;
      if (!run) out.push(run = []);
      run.push(q);
    }
    return out;
  };
  const stroke = (lines) => {
    ctx.beginPath();
    for (const pts of lines) pts.forEach((q, k) => (k ? ctx.lineTo(q[0], q[1]) : ctx.moveTo(q[0], q[1])));
    ctx.stroke();
  };
  ctx.save();
  ctx.lineJoin = "round"; ctx.lineCap = "round";
  ctx.strokeStyle = tint("ivory", 0.22); ctx.lineWidth = 2;
  stroke(runs(replay.t, replay.to));
  ctx.strokeStyle = look.mid; ctx.lineWidth = 3;
  const walked = runs(replay.from, replay.t);
  if (replay.fade) {
    ctx.lineCap = "butt";
    for (const piece of fadePieces(walked)) { ctx.globalAlpha = piece.alpha; stroke([piece.pts]); }
  } else stroke(walked);
  ctx.restore();
}

function drawReplayUnits(size, scale) {
  ctx.save();
  for (const u of replay.line.units.values()) {
    const at = unitAt(u, replay.t);
    const p = at && worldOnScreen(at.at[0], at.at[1], at.at[2], size, scale);
    if (!p) continue;
    const color = isMine(u.flags) ? "leaf-green" : u.flags & RP_HOSTILE || !(u.flags & RP_PLAYER) ? "kill-crimson" : "cyan";
    ctx.globalAlpha = Math.max(0, Math.min(1, at.alpha));
    ctx.beginPath(); ctx.arc(p[0], p[1], 5.5, 0, Math.PI * 2);
    ctx.fillStyle = tint(color); ctx.fill();
    ctx.lineWidth = 1.5; ctx.strokeStyle = tint("black"); ctx.stroke();
    if (u.name && at.alpha > 0.5) {
      ctx.font = `600 11px ${MARK_FONT}`; ctx.textAlign = "center";
      ctx.lineWidth = 3; ctx.strokeStyle = tint("black", 0.85); ctx.strokeText(u.name, p[0], p[1] - 10);
      ctx.fillStyle = tint("ivory"); ctx.fillText(u.name, p[0], p[1] - 10);
    }
  }
  ctx.restore();
}

function effectSpot(where, me, you, seed, size, scale) {
  const ahead = (d) => [me[0] + Math.sin((you.f ?? 0) - app.view.rot) * -d, me[1] - Math.cos((you.f ?? 0) - app.view.rot) * d];
  if (where === "me") return me;
  if (where === "ahead") return ahead(70);
  if (where === "above") return [me[0], me[1] - 90];
  if (where === "below") return [me[0], me[1] + 90];
  const p = where && where !== "around" ? unitOnScreen(where, size, scale) : null;
  if (p) return p;
  const a = (seed * 2.399) % (Math.PI * 2);
  return [me[0] + Math.cos(a) * 80, me[1] + Math.sin(a) * 80];
}

function drawReplayEffects(me, you, size, scale) {
  const wall = performance.now();
  ctx.save();
  for (const f of replay.effects) {
    const k = Math.min(1, (wall - f.born) / f.life);
    if (f.kind === "card") {
      const a = effectSpot(f.from, me, you, f.seed, size, scale), b = effectSpot(f.to, me, you, f.seed, size, scale);
      const e = 1 - Math.pow(1 - k, 3), x = a[0] + (b[0] - a[0]) * e, y = a[1] + (b[1] - a[1]) * e;
      const img = iconImage(f.icon), s = 22;
      ctx.globalAlpha = k > 0.85 ? (1 - k) / 0.15 : 1;
      ctx.translate(x, y); ctx.rotate((1 - e) * 0.6);
      ctx.fillStyle = tint("black"); ctx.fillRect(-s / 2 - 2, -s / 2 - 2, s + 4, s + 4);
      if (img.complete && img.naturalWidth) ctx.drawImage(img, -s / 2, -s / 2, s, s);
      ctx.strokeStyle = tint("gold"); ctx.lineWidth = 1.5; ctx.strokeRect(-s / 2 - 1, -s / 2 - 1, s + 2, s + 2);
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    } else {
      const p = effectSpot(f.at, me, you, f.seed, size, scale);
      const color = SCT_TINTS[f.look] || "white";
      ctx.globalAlpha = 1 - k * k;
      ctx.font = `700 ${f.crit ? 18 : 14}px ${MARK_FONT}`; ctx.textAlign = "center";
      const x = p[0] + ((f.seed % 3) - 1) * 12, y = p[1] - 18 - k * 34;
      ctx.lineWidth = 3; ctx.strokeStyle = tint("black", 0.9); ctx.strokeText(f.text, x, y);
      ctx.fillStyle = tint(color); ctx.fillText(f.text, x, y);
    }
  }
  ctx.globalAlpha = 1;
  let y = me[1] - 58;
  for (const b of [...replay.bubbles].reverse()) {
    const k = (wall - b.born) / b.life;
    ctx.globalAlpha = k > 0.85 ? (1 - k) / 0.15 : 1;
    ctx.font = `13px ${MARK_FONT}`;
    const text = b.text.length > 90 ? `${b.text.slice(0, 89)}…` : b.text, w = ctx.measureText(text).width + 16, h = 22;
    const x = me[0] - w / 2;
    y -= h + 6;
    ctx.fillStyle = tint("backdrop", 0.88); ctx.fillRect(x, y, w, h);
    ctx.strokeStyle = tint(b.at ? "gold" : b.ch === "whisper" || b.ch === "to" ? "class-paladin" : "bronze-dark");
    ctx.lineWidth = b.at ? 2 : 1; ctx.strokeRect(x, y, w, h);
    ctx.textAlign = "center"; ctx.fillStyle = tint(b.ch === "whisper" || b.ch === "to" ? "class-paladin" : "ivory");
    ctx.fillText(text, me[0], y + 15);
  }
  ctx.restore();
}


function replayClick(e) {
  const t = e.target.closest?.("[data-rp], [data-rp-day], [data-rp-at], [data-rp-edge]");
  if (e.target.closest?.("#rp-day")) return toggleReplayMenu("rp-days", "rp-day", daysMenuHtml);
  if (e.target.closest?.("#rp-pause-key")) return toggleReplayMenu("rp-pauses", "rp-pause-key");
  if (!t) return;
  if (t.dataset.rpDay) { $("rp-days").hidden = true; return loadReplayDay(t.dataset.rpDay); }
  if (t.dataset.rpEdge) return rollDay(+t.dataset.rpEdge, false);
  if (t.dataset.rpAt) return seekReplay(+t.dataset.rpAt);
  const what = t.dataset.rp;
  if (what === "faster" || what === "slower") {
    replay.speed = what === "faster" ? fasterThan(replay.speed) : slowerThan(replay.speed);
    return renderReplayClock();
  }
  if (what === "close") return options.set("replay", false);
  if (what === "onward") {
    replay.onward = !replay.onward;
    keepIn("cc.replayOnward", replay.onward);
    return t.setAttribute("aria-pressed", String(replay.onward));
  }
  if (what === "follow") return setFollow(!followingReplay(), "replay");
  if (what === "fade") {
    replay.fade = !replay.fade;
    keepIn("cc.replayFade", replay.fade);
    t.setAttribute("aria-pressed", String(replay.fade));
    return redraw();
  }
  if (!replay.line) return;
  if (what === "play") {
    if (!replay.playing && replay.t >= replay.to) replay.t = replay.from;
    replay.dir = 1; replay.playing = !replay.playing;
  } else if (what === "rewind") { replay.dir = -1; replay.playing = true; }
  else if (what === "forward") { replay.dir = 1; replay.speed = fasterThan(replay.speed); replay.playing = true; }
  else if (what === "back" || what === "next") {
    replay.playing = false;
    seekReplay(stepFrom(replay.line.steps, replay.t, what === "next" ? 1 : -1));
    const ev = replay.line.fx[lastAt(replay.line.fx, replay.t)];
    if (ev && ev.t === replay.t && what === "next") playReplayEvents(replay.t - 1e-6, replay.t, performance.now());
  }
  renderReplayClock();
  redraw();
}

function daysMenuHtml() {
  return replay.days.length ? replay.days.map((d) => `<button class="layer-item" data-rp-day="${d}" role="menuitem"
    aria-pressed="${d === replay.day}">${esc(dayName(d))}</button>`).join("") : `<p class="rp-none">The Index hasn't recorded a day of yours yet.</p>`;
}

function toggleReplayMenu(menuId, keyId, html) {
  const menu = $(menuId), key = $(keyId);
  if (html) menu.innerHTML = html();
  menu.hidden = !menu.hidden;
  key.setAttribute("aria-expanded", String(!menu.hidden));
}

function replayChange(e) {
  const id = e.target.dataset?.rpPause;
  if (!id) return;
  if (e.target.checked) replay.pauses.add(id); else replay.pauses.delete(id);
  keepIn("cc.replayPauses", [...replay.pauses]);
}

function timeAt(e) {
  const r = $("rp-time").getBoundingClientRect();
  return replay.from + Math.min(1, Math.max(0, (e.clientX - r.left) / Math.max(1, r.width))) * (replay.to - replay.from);
}
const replayZoomed = () => !!replay.line && (replay.from > replay.line.from + 1e-6 || replay.to < replay.line.to - 1e-6);
function showReplayStretch(view) {
  replay.from = view.from; replay.to = view.to;
  renderReplayTime();
  if (replay.t < replay.from || replay.t > replay.to) seekReplay(replay.t);
  else renderReplayClock();
}
function replayWheel(e) {
  if (!replay.line || !e.target.closest?.("#rp-time")) return;
  e.preventDefault?.();
  const whole = { from: replay.line.from, to: replay.line.to };
  const band = e.target.closest?.("#rp-band");
  showReplayStretch(zoomAbout({ from: replay.from, to: replay.to }, timeAt(e), Math.pow(1.0015, e.deltaY || 0), whole));
  nameReplayBand(e, band);
}
function nameReplayBand(e, band = e.target?.closest?.("#rp-band")) {
  if (band && replay.line) band.title = bandWords(rpBandAt(replay.line.band, timeAt(e)));
}
const replayHeld = () => !!replay.pick?.head;
function holdReplayHead(held) { $("rp-time")?.classList.toggle("held", held); }
function replayPointerDown(e) {
  if (!replay.line || !e.target.closest?.("#rp-time") || e.target.closest?.("[data-rp-at], [data-rp-edge]")) return;
  if (e.target.closest?.("#rp-head")) {
    replay.pick = { head: true, shift: 0, x: e.clientX, rolling: false };
    return holdReplayHead(true);
  }
  replay.pick = { a: timeAt(e), x: e.clientX, pan: replayZoomed() && !e.shiftKey, view: { from: replay.from, to: replay.to } };
}
function dragReplayHead(clientX) {
  const pick = replay.pick;
  pick.x = clientX;
  if (pick.rolling) return;
  const r = $("rp-time").getBoundingClientRect(), x = clientX + pick.shift;
  const dir = x < r.left ? -1 : x > r.left + r.width ? 1 : 0;
  if (dir && replay.onward && dayBeside(dir)) {
    pick.rolling = true;
    return rollDay(dir, replay.playing).then((rolled) => {
      pick.rolling = false;
      if (rolled) pick.shift += -dir * r.width;
      if (replay.pick === pick) dragReplayHead(pick.x);
    });
  }
  seekReplay(timeAt({ clientX: x }));
}
function replayPointerMove(e) {
  if (!replay.pick) return nameReplayBand(e);
  if (replay.pick.head) return dragReplayHead(e.clientX);
  if (replay.pick.pan) {
    const v = replay.pick.view, dt = -(e.clientX - replay.pick.x) / replayTimeWidth() * (v.to - v.from);
    return showReplayStretch(panBy(v, dt, { from: replay.line.from, to: replay.line.to }));
  }
  const b = timeAt(e), box = $("rp-pick"), span = Math.max(1, replay.to - replay.from);
  const lo = Math.min(replay.pick.a, b), hi = Math.max(replay.pick.a, b);
  box.hidden = Math.abs(e.clientX - replay.pick.x) < 4;
  box.style.left = `${(lo - replay.from) / span * 100}%`;
  box.style.width = `${(hi - lo) / span * 100}%`;
}
function replayPointerUp(e) {
  if (!replay.pick) return;
  if (replay.pick.head) {
    replay.pick = null;
    holdReplayHead(false);
    return redraw();
  }
  const a = replay.pick.a, b = timeAt(e), moved = Math.abs(e.clientX - replay.pick.x) >= 4, pan = replay.pick.pan;
  replay.pick = null;
  $("rp-pick").hidden = true;
  if (pan && moved) return;
  if (moved && Math.abs(b - a) >= Math.min(PICK_LEAST, (replay.to - replay.from) / 100)) {
    replay.from = Math.min(a, b); replay.to = Math.max(a, b);
    seekReplay(replay.from);
    renderReplayTime();
  } else seekReplay(b);
}
function replayWhole() {
  if (!replay.line) return;
  replay.from = replay.line.from; replay.to = replay.line.to;
  renderReplayTime();
  renderReplayClock();
}

{
  replay.pauses = new Set(keptOr("cc.replayPauses", []));
  replay.onward = keptOr("cc.replayOnward", false) === true;
  replay.fade = keptOr("cc.replayFade", false) === true;
  $("replay").addEventListener("click", replayClick);
  $("replay").addEventListener("change", replayChange);
  $("replay").addEventListener("pointerdown", replayPointerDown);
  $("replay").addEventListener("wheel", replayWheel, { passive: false });
  $("replay").addEventListener("dblclick", (e) => { if (e.target.closest?.("#rp-time")) replayWhole(); });
  addEventListener("pointermove", replayPointerMove);
  addEventListener("pointerup", replayPointerUp);
  options.hooks.replay = { changed: () => syncReplay() };
  on("animate", replayFrame);
  on("mapdraw", drawReplay);
  on("follow", () => $("rp-follow")?.setAttribute("aria-pressed", String(followingReplay())));
  syncReplay();
}

