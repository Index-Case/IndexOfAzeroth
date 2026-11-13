// The Index of Azeroth. Copyright 2026 Index Case <indexofazeroth@pm.me>. PolyForm Strict 1.0.0, see LICENSE.md.
"use strict";


const QUIP_MS = QuipLines.ms;
const QUIP_RESUME = QuipLines.resume;
const COMPOSE_WAITING = Object.values(wordsOf("page.compose.ready"));
const QUILL = { w: 230, h: 140, yaw: 25, pitch: 28 };
const compose = { since: 0, mode: null, view: null, loading: false, raf: 0, stream: 0, held: false, shown: new Set(), last: null,
  nowLast: false, t: null, found: [], el: null };
function producing(t) {
  if (!t || t.kind !== "epic" || t.waiting) return false;
  if (!t.startedAt) return false;
  if (!t.data) return !askState("epic")?.error;
  return !planWritten(t) && !planAskFailed() && !planBroke(t);
}
function planWritten(t) {
  if (t.kind !== "epic") return true;
  const p = app.plan;
  return !!p && p.key === t.key && p.start != null && p.start > (t.planBefore ?? 0);
}
function planBroke(t) {
  const b = app.plan?.broke;
  return t.kind === "epic" && !!b && b.key === t.key && b.at > (t.brokeBefore ?? 0);
}
function awaitingLoad(t) {
  const p = app.plan;
  return !!t && t.kind === "epic" && !!p && p.key === t.key && planIsMine(p) && !!p.fresh && !!p.start && loadedVersion() < p.start;
}
const composeMode = (t) => (producing(t) ? "making" : awaitingLoad(t) ? "waiting" : null);
function showCompose(box, mode, t = null) {
  let c = box.querySelector(":scope > .compose");
  if (!c) {
    c = document.createElement("div");
    c.className = "compose";
    c.hidden = true;
    c.innerHTML = `<div class="compose-show" aria-hidden="true"><div class="compose-pics"><div class="compose-slide"></div>
      <div class="compose-slide"></div></div><div class="compose-burn"></div><div class="compose-names"></div></div>
      <div class="compose-art"></div><div class="compose-line"></div><span class="compose-help">${helpButton("epic")}</span>`;
    holdQuips(c);
    box.prepend(c);
  }
  compose.el = c;
  compose.t = t;
  if (mode) box.dataset.composing = mode;
  else delete box.dataset.composing;
  if (!mode) {
    if (c.hidden && !compose.since) return;
    compose.since = 0;
    compose.mode = null;
    stopQuips();
    c.hidden = true;
    dropFrame(compose.raf);
    showPictures(c.querySelector(".compose-show"), false);
    return;
  }
  if (!compose.since) {
    compose.since = performance.now();
    compose.found = [];
    compose.shown.clear();
    warmPicture();
  }
  if (compose.mode !== mode) {
    compose.mode = mode;
    const line = c.querySelector(".compose-line");
    c.classList.remove("done");
    line.classList.remove("writing", "swoop", "quip");
    line.classList.toggle("waiting", mode === "waiting");
    compose.swoop = mode === "waiting";
    if (compose.swoop) {
      stopQuips();
      compose.text = COMPOSE_WAITING[Math.floor(Math.random() * COMPOSE_WAITING.length)];
      line.textContent = compose.text;
    } else {
      nextQuip(line);
      if (!c.hidden) showQuill(c.querySelector(".compose-art"));
    }
  }
  if (c.hidden) {
    c.hidden = false;
    showQuill(c.querySelector(".compose-art"));
    showPictures(c.querySelector(".compose-show"), true);
  }
  if (compose.swoop) {
    compose.swoop = false;
    swoopLine(c, c.querySelector(".compose-line"), compose.text);
  }
}

function quipFacts(t) {
  const me = alts.data?.chars?.[app.character] || {}, g = app.plan?.progress;
  const said = t && g?.key === t.key ? g : null;
  for (const f of said?.finds || []) if (!compose.found.some((x) => quipKey(x) === quipKey(f))) compose.found.push(f);
  return { stage: quipStage(said), now: said?.now || null,
    me: { race: me.raceName, cls: app.status?.className || me.className, zone: app.state?.zone, found: compose.found } };
}
function nextQuip(line) {
  clearTimeout(compose.stream);
  if (compose.held) return;
  const f = quipFacts(compose.t), now = quipNow(f.now);
  const text = quipNext(quipLines(f.stage, f.me), compose.shown, compose.last, now, compose.nowLast);
  if (text) {
    compose.nowLast = text === now;
    compose.last = text;
    line.textContent = text;
    line.classList.remove("quip");
    void line.offsetWidth;
    line.classList.add("quip");
  }
  compose.stream = setTimeout(() => nextQuip(line), QUIP_MS);
}
function stopQuips() {
  clearTimeout(compose.stream);
  compose.stream = 0;
  compose.held = false;
  compose.last = null;
  compose.nowLast = false;
}

const PLAN_WAYS_ALPHA = 0.45;
const WEIGH_WAYS_ALPHA = 0.9;
const PLAN_WAYS_FADE = 1500;
const LEG_GROW = 300;
const freshPlanWays = (key) => ({ key, list: [], gone: 0, grow: { from: 0, since: 0, until: 0 } });
const planWays = freshPlanWays(null);

function followPlanWork() {
  const t = compose.t, g = app.plan?.progress, now = performance.now();
  if (compose.mode !== "making" || !t) {
    if (planWays.list.length && !planWays.gone) planWays.gone = now;
    if (planWork.key) Object.assign(planWork, freshPlanWork(null));
    stepsLand();
    planMapDone(now);
    showQuestNames();
    return;
  }
  if (planWays.key !== t.key || planWays.gone) Object.assign(planWays, freshPlanWays(t.key));
  if (planWork.key !== t.key) {
    Object.assign(planWork, freshPlanWork(t.key));
    stepsLand();
  }
  planMapFor(t.key);
  const said = g?.key === t.key ? g : null;
  planWork.ways = said?.stage === "ways";
  showQuestNames();
  planMapRing(planWork.ways ? null : said?.at?.step, now);
  if (!said) return;
  if (planWork.ways) planMapInto(now);
  const from = planWays.list.length, placed = planWork.placed, asks = [];
  if (said.found > from && !planMapHoldsLegs()) asks.push(`from=${from}`);
  if (said.picked && said.picked !== planWork.picked) asks.push("quests=1");
  if (said.placed > placed) asks.push(`steps=${Math.max(placed, said.placed - STEP_KEEP)}`);
  if (said.ordered && said.ordered !== planWork.ordered) asks.push("order=1");
  if (!asks.length) return;
  getJson(`/api/shared/progress?${asks.join("&")}`, { key: "/api/shared/progress" })?.then((p) => {
    if (!p || p.key !== planWork.key) return;
    const at = performance.now();
    if (p.ways && p.key === planWays.key && planWays.list.length === from && !planWays.gone) addPlanWays(planWays, p.ways, at);
    if (p.quests) {
      Object.assign(planWork, { picked: p.picked, names: p.quests.filter((q) => q.name).map((q) => q.name) });
      planMapQuests(p.quests, at);
      showQuestNames();
    }
    if (p.steps && planWork.placed === placed) {
      planWork.placed = p.placed;
      planMapPlaced(p.steps, at);
    }
    if (p.order && p.ordered !== planWork.ordered) {
      planWork.ordered = p.ordered;
      planMapOrder(p.order, at);
    }
  }, () => {});
}
on("update", followPlanWork);


function planWaysAt(drawn, now) {
  const n = drawn.list.length, { from, since, until } = drawn.grow;
  return now >= until ? n : from + (n - from) * (now - since) / (until - since);
}

function addPlanWays(drawn, ways, now) {
  if (!ways.length) return;
  const from = planWaysAt(drawn, now), still = matchMedia("(prefers-reduced-motion: reduce)").matches;
  drawn.list.push(...ways);
  drawn.grow = { from, since: now, until: now + (still ? 0 : LEG_GROW) };
  redraw();
}

function planWaysDrawn(drawn, now) {
  const at = planWaysAt(drawn, now), whole = Math.floor(at);
  return whole + (1 - (1 - (at - whole)) ** 3);
}

function animatePlanWays(now) {
  if (!planWays.gone) return now < planWays.grow.until;
  if (now - planWays.gone < PLAN_WAYS_FADE) return true;
  Object.assign(planWays, freshPlanWays(null));
  return false;
}
on("animate", animatePlanWays);

function drawPlanWaysNow(size, scale) {
  if (!planWays.list.length) return;
  const now = performance.now(), left = planWays.gone ? Math.max(0, 1 - (now - planWays.gone) / PLAN_WAYS_FADE) : 1;
  if (left > 0) drawPlanWays(planWays.list, size, scale, PLAN_WAYS_ALPHA * left, planWaysDrawn(planWays, now));
}


const STEP_POP = 320;
const STEP_FLY = 820;
const STEP_KEEP = 200;
const STEP_SPREAD = 2000;
const STEP_GAP = [35, 180];
const STEP_LIFT = 0.16;
const STEP_CORNER = 24;
const STEP_FLY_SIZE = 26;
const QUEST_NAME_MS = 900;
const freshPlanWork = (key) => ({ key, picked: 0, names: [], placed: 0, ordered: 0, ways: false });
const spreadGap = (n) => Math.min(STEP_GAP[1], Math.max(STEP_GAP[0], STEP_SPREAD / n));
const planWork = freshPlanWork(null);
const stepFlights = { waiting: [], gap: STEP_GAP[1], timer: 0, layer: null };

function showQuestNames() {
  const box = compose.el?.querySelector(".compose-names");
  if (!box) return;
  const names = planWork.key && !planWork.ways ? planWork.names : [];
  box.classList.toggle("on", names.length > 0);
  if (!names.length || box.dataset.names === String(planWork.picked)) return;
  box.dataset.names = String(planWork.picked);
  let roll = box.querySelector(".compose-names-roll");
  if (!roll) {
    roll = document.createElement("div");
    roll.className = "compose-names-roll";
    box.append(roll);
  }
  const lines = names.map((n) => `<div>${esc(n)}</div>`).join("");
  roll.style.setProperty("--names-roll", `${names.length * QUEST_NAME_MS}ms`);
  roll.innerHTML = lines + lines;
}

function flyPlaced(steps) {
  if (lessMotion() || !steps.length || !options.get("planmap")) return;
  const w = stepFlights.waiting;
  w.push(...steps);
  stepFlights.gap = spreadGap(w.length);
  if (!stepFlights.timer) stepTakeOff();
}
function stepTakeOff() {
  stepFlights.timer = 0;
  while (stepFlights.waiting.length) {
    const s = stepFlights.waiting.shift();
    s.lifted = performance.now();
    if (launchStep(s)) break;
  }
  if (stepFlights.waiting.length) stepFlights.timer = setTimeout(stepTakeOff, stepFlights.gap);
}
function stepsLand() {
  clearTimeout(stepFlights.timer);
  Object.assign(stepFlights, { waiting: [], timer: 0 });
}
function launchStep(s) {
  const map = $("map"), art = compose.el?.querySelector(".compose-art");
  if (!map || !art || !art.isConnected) return false;
  const m = map.getBoundingClientRect(), a = art.getBoundingClientRect();
  if (!a.width) return false;
  const spot = worldOnScreen(s.i, s.at[0], s.at[1], app.curSize, scaleFor(app.curSize));
  const [dx, dy] = s.fan || [0, 0];
  const corner = a.left + a.right < m.left + m.right ? m.left + STEP_CORNER : m.right - STEP_CORNER;
  const from = spot ? [Math.min(m.right, Math.max(m.left, m.left + spot[0] + dx)), Math.min(m.bottom, Math.max(m.top, m.top + spot[1] + dy))]
    : [corner, m.top + STEP_CORNER];
  const to = [a.left + a.width / 2, a.top + a.height / 2];
  if (!stepFlights.layer?.isConnected) {
    stepFlights.layer = document.createElement("div");
    stepFlights.layer.className = "plan-flights";
    document.body.append(stepFlights.layer);
  }
  const icon = document.createElement("img");
  icon.className = "plan-fly";
  icon.src = `/ui/${stepIconName(s)}.png`;
  icon.alt = "";
  stepFlights.layer.append(icon);
  icon.animate(stepFlightFrames(from, to, window.innerHeight), { duration: STEP_FLY, easing: "linear" }).onfinish = () => icon.remove();
  return true;
}
function stepFlightFrames(from, to, H) {
  const top = Math.min(from[1], to[1]) - STEP_LIFT * H;
  const line = hoseCurve([from, [from[0], top], [to[0], top], to], 48), lengths = hoseLengths(line);
  const at = ([x, y], k) => `translate(${x.toFixed(1)}px, ${y.toFixed(1)}px) scale(${k.toFixed(3)})`;
  const k0 = MARK_SIZE / STEP_FLY_SIZE, N = 18, frames = [];
  for (let k = 0; k <= N; k++) {
    const u = k / N, eased = u < 0.5 ? 2 * u * u : 1 - (-2 * u + 2) ** 2 / 2, p = hoseAt(line, lengths, eased);
    const size = (k0 + (0.65 - k0) * eased) * (1 + 0.3 * Math.sin(Math.PI * u));
    frames.push({ offset: u, transform: at([p.x, p.y], size), opacity: Math.min(1, (1 - u) / 0.2) });
  }
  return frames;
}

function holdQuips(c) {
  const line = () => c.querySelector(".compose-line");
  c.addEventListener("pointerdown", () => {
    if (compose.mode !== "making") return;
    compose.held = true;
    clearTimeout(compose.stream);
    c.classList.add("held");
  });
  const free = () => {
    if (!compose.held) return;
    compose.held = false;
    c.classList.remove("held");
    if (compose.mode === "making") compose.stream = setTimeout(() => nextQuip(line()), QUIP_RESUME);
  };
  for (const ev of ["pointerup", "pointercancel", "pointerleave"]) c.addEventListener(ev, free);
}

function swoopLine(c, line, text) {
  const box = c.getBoundingClientRect(), at = line.getBoundingClientRect();
  line.style.setProperty("--rise", `${Math.round(box.top + box.height / 2 - (at.top + at.height / 2))}px`);
  line.replaceChildren(...swoopParts(text));
  line.classList.add("swoop");
  c.classList.add("done");
  compose.swoopAt = performance.now();
}
function swoopParts(text) {
  let k = 0;
  const letter = (ch) => {
    const s = document.createElement("span");
    s.className = "ch";
    s.textContent = ch;
    s.style.setProperty("--i", k);
    s.style.setProperty("--dx", (k % 2 ? 1 : -1) * (10 + ((k * 7) % 16)));
    s.style.setProperty("--rot", ((k % 3) - 1) * 16);
    k++;
    return s;
  };
  const out = [];
  text.split(" ").forEach((w, n) => {
    if (n) { out.push(document.createTextNode(" ")); k++; }
    if (!w) return;
    const word = document.createElement("span");
    word.className = "word";
    word.append(...[...w].map(letter));
    out.push(word);
  });
  return out;
}
const SWOOP_FADE = 1500;

const SHOW_EACH = 6500, SHOW_FADE = 1400;
const SHOW_ZOOM = [1.7, 2.6];
const SHOW_SHARP = 1.8;
const pictureShow = { timer: 0, run: 0, last: null, first: null, front: 0 };
const nextPicture = () => (pickPicture(pictureShow.last));
function warmPicture() {
  pictureShow.first = nextPicture();
  new Image().src = pictureShow.first;
}
function showPictures(stage, on) {
  clearTimeout(pictureShow.timer);
  const run = ++pictureShow.run;
  if (!on) {
    for (const s of stage.querySelectorAll(".compose-slide")) { s.classList.remove("on"); s.replaceChildren(); }
    return;
  }
  const next = () => {
    const src = pictureShow.first || nextPicture(), img = new Image();
    pictureShow.first = null;
    img.onload = () => {
      if (run !== pictureShow.run || !stage.isConnected) return;
      pictureShow.last = src;
      placeSlide(stage, img);
      pictureShow.timer = setTimeout(next, SHOW_EACH);
    };
    img.onerror = () => { if (run === pictureShow.run) pictureShow.timer = setTimeout(next, 1500); };
    img.src = src;
  };
  next();
}
function placeSlide(stage, img) {
  const slides = stage.querySelectorAll(".compose-slide"), w = stage.clientWidth, h = stage.clientHeight;
  if (slides.length < 2 || !w || !h || !img.naturalWidth) return;
  pictureShow.front ^= 1;
  const into = slides[pictureShow.front], out = slides[pictureShow.front ^ 1];
  const cover = Math.max(w / img.naturalWidth, h / img.naturalHeight);
  const sharp = SHOW_SHARP / (cover * (window.devicePixelRatio || 1));
  const still = matchMedia("(prefers-reduced-motion: reduce)").matches;
  const z0 = Math.max(1.3, Math.min(SHOW_ZOOM[0] + Math.random() * (SHOW_ZOOM[1] - SHOW_ZOOM[0]), sharp));
  const z1 = still ? z0 : z0 * (Math.random() < 0.5 ? 1.12 : 1 / 1.12);
  const f0 = [0.2 + Math.random() * 0.6, 0.25 + Math.random() * 0.5];
  const f1 = still ? f0 : [f0[0] + (Math.random() - 0.5) * 0.12, f0[1] + (Math.random() - 0.5) * 0.1];
  const iw = img.naturalWidth * cover, ih = img.naturalHeight * cover;
  const at = (z, f) => {
    const x = Math.min(0, Math.max(w - iw * z, w / 2 - f[0] * iw * z)), y = Math.min(0, Math.max(h - ih * z, h / 2 - f[1] * ih * z));
    return `translate(${x.toFixed(1)}px, ${y.toFixed(1)}px) scale(${z.toFixed(3)})`;
  };
  img.className = "compose-pic";
  img.alt = "";
  img.style.width = `${iw}px`;
  img.style.height = `${ih}px`;
  img.style.transform = at(z0, f0);
  into.replaceChildren(img);
  void img.offsetWidth;
  img.style.transition = `transform ${SHOW_EACH + SHOW_FADE * 2}ms linear`;
  img.style.transform = at(z1, f1);
  into.classList.add("on");
  out.classList.remove("on");
}
function showQuill(holder) {
  if (compose.view) {
    if (compose.view.canvas.parentNode !== holder) holder.replaceChildren(compose.view.canvas);
    return runQuill();
  }
  if (compose.loading) return;
  const picture = () => { holder.innerHTML = `<img src="models/quill.png" alt="">`; };
  const asked = loadModel("quill");
  if (!asked) return picture();
  compose.loading = true;
  asked.then((m) => {
    compose.view = new ModelView(m, { yaw: QUILL.yaw, pitch: QUILL.pitch });
    holder.replaceChildren(compose.view.canvas);
    runQuill();
  }).catch(picture).finally(() => { compose.loading = false; });
}
function runQuill() {
  dropFrame(compose.raf);
  const v = compose.view;
  const frame = (t) => {
    const box = v.canvas.closest(".compose");
    if (!v.canvas.isConnected || box?.hidden || (box?.classList.contains("done") && performance.now() - compose.swoopAt > SWOOP_FADE)) return;
    v.size(QUILL.w, QUILL.h);
    v.draw(t);
    compose.raf = askFrame(frame);
  };
  compose.raf = askFrame(frame);
}
