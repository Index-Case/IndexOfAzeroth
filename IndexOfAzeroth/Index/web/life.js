// The Index of Azeroth. Copyright 2026 Index Case <indexofazeroth@pm.me>. PolyForm Strict 1.0.0, see LICENSE.md.
"use strict";

const lessMotion = () => matchMedia("(prefers-reduced-motion: reduce)").matches;

const WORDS = {
  combat: { src: "art/in_combat.png", label: "In combat" },
  dead: { src: "art/corpserun.png", label: "Corpse run" },
};
for (const w of Object.values(WORDS)) (w.img = new Image()).src = w.src;
function wordHtml({ src, label, img }) {
  const wide = img.naturalWidth || 3, high = img.naturalHeight || 1;
  const across = 0.08 / (wide / high);
  return `<svg class="life-smear" width="0" height="0" aria-hidden="true">
  <filter id="lw-word" x="-80%" y="-40%" width="260%" height="180%" primitiveUnits="objectBoundingBox" color-interpolation-filters="sRGB">
    <feComponentTransfer in="SourceAlpha" result="solid"><feFuncA type="linear" slope="4" intercept="-1.6"/></feComponentTransfer>
    <feComposite in="SourceGraphic" in2="solid" operator="in" result="letters"/>
    <feGaussianBlur in="solid" stdDeviation="${across.toFixed(4)} 0.08" result="soft"/>
    <feColorMatrix in="soft" values="0 0 0 0 0  0 0 0 0 0  0 0 0 0 0  0 0 0 0.7 0" result="glow"/>
    <feMerge result="word"><feMergeNode in="glow"/><feMergeNode in="letters"/></feMerge>
    <feGaussianBlur class="lw-smear" in="word" stdDeviation="0 0"/>
  </filter>
</svg><img class="life-word" src="${src}" alt="${label}" width="${wide}" height="${high}" style="filter:url(#lw-word)">`;
}

const LIFE = {
  combat: { model: "duel-flag", yaw: 30, pitch: 8, word: WORDS.combat, h: 340, fall: 460, fallMs: 300, squash: 0.84,
            bounce: 9, tilt: -7, shake: 8, dust: 200 },
  dead: { model: "gravestone", yaw: 22, pitch: 8, word: WORDS.dead, h: 230, fall: 480, fallMs: 330, squash: 0.8,
          bounce: 11, tilt: -5, shake: 10, dust: 250, spins: 3, rock: 12 },
};
const LIFE_IMPACT_MS = 220;
const LIFE_HOLD_MS = 1000;
const LIFE_FLY_MS = 950;
const life = { want: undefined, flyer: null, raf: 0, smear: 0, markRaf: 0, dismissed: null };
const MAP_LEFT = 334;
const MAP_REF = { w: 1572, h: 873 };
function mapScale() {
  const map = $("map").getBoundingClientRect();
  return Math.min(map.height / MAP_REF.h, (map.width - MAP_LEFT) / MAP_REF.w);
}

const lifeArt = {};
for (const [kind, k] of Object.entries(LIFE)) {
  const art = lifeArt[kind] = { view: null, picture: new Image() };
  art.picture.src = `${MODEL_DIR}${k.model}.png`;
  loadModel(k.model)?.then((model) => {
    art.view = new ModelView(model, k);
    if (life.want === kind && !life.flyer) landLife(kind);
  }).catch((e) => console.warn(`${k.model} shown as its picture: ${e.message}`));
}
const artAspect = (kind) => {
  const a = lifeArt[kind];
  return a.view ? a.view.aspect : a.picture.naturalWidth / a.picture.naturalHeight || 0.6;
};
function artFor(kind) {
  const a = lifeArt[kind];
  if (a.view) return a.view.canvas;
  const img = a.picture.cloneNode();
  img.alt = "";
  return img;
}
function sizeArt(kind, art, width, height) {
  const view = lifeArt[kind].view;
  if (view?.canvas === art) {
    view.size(width, height);
    view.draw(performance.now());
  } else {
    art.style.width = `${width}px`;
    art.style.height = `${height}px`;
  }
}

let artCopies = 0;
function fresh(svg) {
  const n = ++artCopies;
  return svg.replace(/id="([^"]+)"/g, `id="$1-${n}"`).replace(/url\(#([^)]+)\)/g, `url(#$1-${n})`);
}

const easeInOut = (t) => (t < 0.5 ? 4 * t * t * t : 1 - (-2 * t + 2) ** 3 / 2);
const cubic = (a, b, c, d, t) => (1 - t) ** 3 * a + 3 * (1 - t) ** 2 * t * b + 3 * (1 - t) * t * t * c + t ** 3 * d;
const QUARTER = 0.5523;

function updateLife(state) {
  const f = state?.flags || {};
  const want = f.dead || f.ghost ? "dead" : f.combat ? "combat" : null, first = life.want === undefined;
  if (want !== life.want) {
    life.want = want;
    cancelLifeFlight();
    if (!want) clearLife(true);
    else if (first || document.hidden || lessMotion() || !options.get("duelflag")) landLife(want);
    else flyLife(want);
  } else fitMark();
  idleAlarm(want === "combat" ? state : null, first);
}

function lifeShown() {
  if (!options.get("idlewarning")) calmAlarm();
  if (!life.want) return;
  cancelLifeFlight();
  stopSmear();
  landLife(life.want);
}
for (const id of ["combatwords", "idlewarning", "edgeglow", "duelflag"]) options.hooks[id] = { changed: lifeShown };

const MARK_GAP = 14;
function markFor(kind, art) {
  const mark = $("life-mark");
  mark.replaceChildren(art);
  mark.className = `life-mark ${kind}`;
  mark.dataset.fit = "";
  mark.hidden = false;
  fitMark(kind);
  return mark;
}
function fitMark(kind = life.want) {
  const mark = $("life-mark"), art = mark.firstElementChild;
  if (mark.hidden || !art || !LIFE[kind]) return;
  const coords = document.querySelector(".coords-line"), words = document.createRange();
  words.selectNodeContents($("subzone"));
  const key = [$("zone").textContent, $("subzone").textContent, $("coords").textContent.length, $("btn-locate").hidden,
               $("expedition").hidden, kind].join("|");
  if (mark.dataset.fit === key) return;
  mark.dataset.fit = key;
  const zone = $("zone").getBoundingClientRect(), box = mark.getBoundingClientRect();
  const height = Math.round(coords.getBoundingClientRect().bottom - zone.top), width = Math.round(height * artAspect(kind));
  const reach = Math.max(words.getBoundingClientRect().right,
                         ...[...coords.children].filter((c) => !c.hidden).map((c) => c.getBoundingClientRect().right));
  const shift = Math.max(0, Math.round(reach + MARK_GAP - box.left));
  sizeArt(kind, art, width, height);
  art.style.left = `${shift}px`;
  art.style.top = `${Math.round(zone.top - box.top)}px`;
  mark.style.width = `${shift + width}px`;
}

function landLife(kind) {
  const banner = $("life-banner"), k = LIFE[kind];
  stopMarkLoop();
  if (!options.get("duelflag")) $("life-mark").hidden = true;
  else {
    markFor(kind, artFor(kind));
    if (!lessMotion()) life.markRaf = askFrame(markLoop);
  }
  $("zone").classList.toggle("in-combat", kind === "combat");
  $("zone").classList.toggle("is-dead", kind === "dead");
  banner.innerHTML = fresh(wordHtml(k.word));
  banner.className = `life-banner ${kind}`;
  wordOrGlow(kind);
}

const LIFE_WINDOWS = ["journal", "reader", "timeline", "drawer", "video"];
function wordBox() {
  const banner = $("life-banner");
  if (!banner.hidden) return banner.getBoundingClientRect();
  banner.style.visibility = "hidden";
  banner.hidden = false;
  const box = banner.getBoundingClientRect();
  banner.hidden = true;
  banner.style.visibility = "";
  return box;
}
function wordCovered() {
  const open = LIFE_WINDOWS.map((id) => $(id)).filter((w) => w && !w.hidden);
  if (!open.length) return false;
  const word = wordBox();
  return open.some((w) => {
    const r = w.getBoundingClientRect();
    return r.left < word.right && r.right > word.left && r.top < word.bottom && r.bottom > word.top;
  });
}
function wordOrGlow(kind = life.want) {
  const glow = !!kind && (!options.get("combatwords") || life.dismissed === kind || (kind === "combat" && alarm.burst) || wordCovered());
  const edge = glow && options.get("edgeglow");
  document.body.classList.toggle("edge-combat", edge && kind === "combat");
  document.body.classList.toggle("edge-dead", edge && kind === "dead");
  if (!kind) return;
  if ($("life-banner").hidden !== glow) $("life-banner").hidden = glow;
  document.body.classList.toggle("life-on", !glow);
}
$("life-banner").addEventListener("click", (e) => {
  const kind = life.want;
  if (!kind || life.smear || !e.target.closest(".life-word")) return;
  life.dismissed = kind;
  if (!smearAway($("life-banner"), true, () => wordOrGlow(kind))) wordOrGlow(kind);
});
const lookAgain = () => { if (life.want && !life.smear && !life.flyer) wordOrGlow(); };
const windowWatch = new MutationObserver(lookAgain);
for (const id of LIFE_WINDOWS) if ($(id)) windowWatch.observe($(id), { attributes: true, attributeFilter: ["hidden"] });
addEventListener("resize", lookAgain);

const ALARM = { START: 10, FULL: 50, BURST: 50, BPM: [66, 150], THUMP: [0.03, 0.1], SHAKE: 0.02, EASE: 0.3 };
const grown = (lost) => Math.min(1, Math.max(0, (lost - ALARM.START) / (ALARM.FULL - ALARM.START)));
const alarm = { lost: 0, burst: false, raf: 0, last: 0, level: 0, phase: 0 };

const thump = (p, at) => {
  const off = ((((p - at) % 1) + 1.5) % 1) - 0.5;
  return Math.exp(-((off / 0.07) ** 2));
};
const heartbeat = (p) => Math.min(1, thump(p, 0) + 0.6 * thump(p, 0.24));

function idleAlarm(state, first = false) {
  const lost = state?.idleLost || 0, health = state?.health ?? state?.healthGuess ?? null;
  if (lost < ALARM.START || !options.get("idlewarning")) return calmAlarm();
  alarm.lost = lost;
  if (!alarm.burst && health !== null && health <= ALARM.BURST) burstWord(first);
  if (lessMotion()) return drawAlarm(0, true);
  if (!alarm.raf) {
    alarm.last = performance.now();
    alarm.raf = askFrame(alarmLoop);
  }
}

function burstWord(first) {
  alarm.burst = true;
  if (!first) burstSound();
  const banner = $("life-banner");
  if (life.flyer || life.smear || banner.hidden) return;
  if (first || !smearAway(banner, true, () => wordOrGlow())) wordOrGlow();
}

const BURST_SOUND = ["audio/idle_burst.ogg", "audio/idle_burst.mp3", "audio/idle_burst.wav"];
let burstClip = null;
function burstSound() {
  const ctx = sound.ctx;
  if (!ctx) return;
  burstClip ??= (async () => {
    for (const url of BURST_SOUND) {
      const bytes = await getBytes(url);
      try {
        if (bytes) return await ctx.decodeAudioData(bytes);
      } catch (e) {   }
    }
    return null;
  })();
  burstClip.then((clip) => {
    if (!clip) return;
    if (ctx.state === "suspended") ctx.resume();
    const src = ctx.createBufferSource();
    src.buffer = clip;
    src.connect(ctx.destination);
    src.start();
  });
}

function calmAlarm() {
  if (!alarm.lost) return;
  dropFrame(alarm.raf);
  const burst = alarm.burst, banner = $("life-banner"), word = banner.querySelector(".life-word");
  Object.assign(alarm, { lost: 0, burst: false, raf: 0, level: 0 });
  if (word && !life.smear) word.style.transform = "";
  banner.style.setProperty("--halo", "0");
  Object.assign($("edge-alarm").style, { willChange: "auto", opacity: "0" });
  if (!burst || life.want !== "combat") return;
  stopSmear();
  banner.innerHTML = fresh(wordHtml(LIFE.combat.word));
  if (!life.flyer) wordOrGlow("combat");
}

function alarmLoop(now) {
  alarm.raf = 0;
  if (!alarm.lost) return;
  const dt = Math.min(0.1, Math.max(0, (now - alarm.last) / 1000)), [lo, hi] = ALARM.BPM;
  alarm.last = now;
  alarm.level += (grown(alarm.lost) - alarm.level) * Math.min(1, dt / ALARM.EASE);
  alarm.phase = (alarm.phase + (dt * (lo + (hi - lo) * (alarm.burst ? 1 : alarm.level))) / 60) % 1;
  drawAlarm(now / 1000);
  alarm.raf = askFrame(alarmLoop);
}

function drawAlarm(t, still = false) {
  const k = still ? grown(alarm.lost) : alarm.level, beat = still ? 0.6 : heartbeat(alarm.phase);
  const banner = $("life-banner"), word = banner.querySelector(".life-word");
  const onWord = !!word && !banner.hidden && !life.smear && !life.flyer;
  if (onWord) {
    const [lo, hi] = ALARM.THUMP, reach = still ? 0 : ALARM.SHAKE * word.offsetHeight * k ** 0.8;
    const x = reach * (0.6 * Math.sin(t * 44) + 0.4 * Math.sin(t * 59.7 + 1.3)), y = 0.4 * reach * Math.sin(t * 69.1 + 0.7);
    const swell = still ? 1 : 1 + (lo + (hi - lo) * k) * beat, turn = 0.35 * reach * Math.sin(t * 37.7 + 2.1);
    word.style.transform = `translate(${x.toFixed(2)}px, ${y.toFixed(2)}px) rotate(${turn.toFixed(2)}deg) scale(${swell.toFixed(4)})`;
  }
  banner.style.setProperty("--halo", onWord ? ((0.3 + 0.7 * k) * (0.3 + 0.7 * beat)).toFixed(3) : "0");
  banner.style.setProperty("--halo-size", (0.92 + 0.1 * k + 0.12 * beat).toFixed(3));
  const edge = onWord || life.flyer || !options.get("edgeglow") ? 0 : alarm.burst ? 0.7 + 0.3 * beat : (0.1 + 0.45 * k) * (0.35 + 0.65 * beat);
  Object.assign($("edge-alarm").style, { willChange: "opacity", opacity: edge.toFixed(3) });
}

function markLoop() {
  const view = lifeArt[life.want]?.view;
  if (!view?.moving || !view.canvas.isConnected || $("life-mark").hidden) {
    life.markRaf = 0;
    return;
  }
  view.draw(performance.now());
  life.markRaf = askFrame(markLoop);
}
function stopMarkLoop() {
  dropFrame(life.markRaf);
  life.markRaf = 0;
}

function clearLife(smear = false) {
  $("life-mark").hidden = true;
  stopMarkLoop();
  $("zone").classList.remove("in-combat", "is-dead");
  life.dismissed = null;
  wordOrGlow(null);
  const banner = $("life-banner");
  stopSmear();
  if (smear && !banner.hidden && smearAway(banner)) return;
  banner.hidden = true;
  document.body.classList.remove("life-on");
}

const SMEAR_MS = 520;
function smearAway(banner, every = false, then = null) {
  const word = banner.querySelector(".life-word"), blur = banner.querySelector(".lw-smear");
  if (!word || !blur || document.hidden || lessMotion()) return false;
  const start = performance.now(), reach = (0.28 * word.offsetHeight) / (word.offsetWidth || 1);
  const step = (now) => {
    const u = Math.min(1, (now - start) / SMEAR_MS), e = u * u;
    word.style.transform = every ? `scale(${1 + e * 1.1})` : `scaleX(${1 + e * 1.1})`;
    blur.setAttribute("stdDeviation", `${(e * reach).toFixed(4)} ${every ? (e * 0.28).toFixed(4) : 0}`);
    word.style.opacity = String(1 - u ** 1.4);
    if (u < 1) life.smear = askFrame(step);
    else {
      life.smear = 0;
      banner.hidden = true;
      document.body.classList.remove("life-on");
      then?.();
    }
  };
  life.smear = askFrame(step);
  return true;
}
function stopSmear() {
  dropFrame(life.smear);
  life.smear = 0;
}

function lifeImpact(k, [x, y]) {
  const stage = $("map").parentElement, frames = [], steps = 12;
  for (let i = 0; i <= steps; i++) {
    const f = i === steps ? 0 : k.shake * (1 - i / steps) ** 2 * (i % 2 ? -1 : 1);
    frames.push({ transform: `translate(${f * (0.6 + Math.random() * 0.4)}px, ${f * (Math.random() - 0.3)}px)` });
  }
  if (options.get("mapshake")) stage.animate(frames, { duration: 420, easing: "linear" });
  const dust = document.createElement("div");
  dust.className = "life-dust";
  dust.style.left = `${x}px`;
  dust.style.top = `${y}px`;
  dust.style.width = `${k.dust}px`;
  dust.style.height = `${Math.round(k.dust * 0.27)}px`;
  document.body.appendChild(dust);
  dust.animate([{ transform: "translate(-50%, -50%) scale(0.35)", opacity: 0.75 }, { transform: "translate(-50%, -50%) scale(1.7)", opacity: 0 }],
               { duration: 560, easing: "cubic-bezier(.2, .7, .3, 1)" }).onfinish = () => dust.remove();
}

function cancelLifeFlight() {
  dropFrame(life.raf);
  life.flyer?.remove();
  life.flyer = null;
  for (const a of Object.values(lifeArt)) a.view?.unspin();
}

function lifeGround(h) {
  const stage = $("map").getBoundingClientRect(), css = getComputedStyle(document.documentElement);
  const x = parseFloat(css.getPropertyValue("--clear-x")), y = parseFloat(css.getPropertyValue("--clear-y"));
  return [stage.left + (Number.isFinite(x) ? x : (MAP_LEFT + stage.width) / 2),
          stage.top + (Number.isFinite(y) ? y : stage.height / 2) + h / 2];
}

function flyLife(kind) {
  const set = LIFE[kind], s = mapScale();
  const k = { ...set, h: set.h * s, fall: set.fall * s, bounce: set.bounce * s, shake: set.shake * s, dust: set.dust * s };
  let w = Math.round(k.h * artAspect(kind));
  clearLife();
  const holder = markFor(kind, document.createElement("span")).firstElementChild;
  const end = holder.getBoundingClientRect();
  const foot = [end.left + end.width / 2, end.bottom];
  const scale = end.height / k.h;
  let ground = lifeGround(k.h);
  const flyer = document.createElement("div");
  flyer.className = `life-flyer ${kind}`;
  flyer.style.width = `${w}px`;
  flyer.style.height = `${k.h}px`;
  const art = artFor(kind), view = lifeArt[kind].view?.canvas === art ? lifeArt[kind].view : null;
  sizeArt(kind, art, w, k.h);
  flyer.appendChild(art);
  document.body.appendChild(flyer);
  life.flyer = flyer;
  const place = (x, y, s, rot = 0, sy = 1, alpha = 1) => {
    flyer.style.transform = `translate(${x - w / 2}px, ${y - k.h}px) rotate(${rot}deg) scale(${s * (1 + (1 - sy) * 0.5)}, ${s * sy})`;
    flyer.style.opacity = alpha;
  };
  const start = performance.now(), landAt = k.fallMs, flyAt = landAt + LIFE_IMPACT_MS + LIFE_HOLD_MS, doneAt = flyAt + LIFE_FLY_MS;
  let hit = false;
  const frame = (now) => {
    const t = now - start;
    if (t < flyAt) ground = lifeGround(k.h);
    if (t < landAt) {
      const u = t / landAt;
      place(ground[0], ground[1] - k.fall * (1 - u ** 3), 1, k.tilt * (1 - u), 1, Math.min(1, u * 4));
    } else if (t < landAt + LIFE_IMPACT_MS) {
      if (!hit) { hit = true; lifeImpact(k, ground); }
      const u = (t - landAt) / LIFE_IMPACT_MS;
      const squash = 1 - (1 - k.squash) * Math.max(0, 1 - u * 2.4);
      const rebound = k.bounce * Math.sin(Math.min(1, u * 1.7) * Math.PI) * (1 - u);
      place(ground[0], ground[1] - rebound, 1, 0, squash);
    } else if (t < flyAt) {
      place(ground[0], ground[1], 1);
    } else if (t < doneAt) {
      const raw = (t - flyAt) / LIFE_FLY_MS, u = easeInOut(raw);
      const back = [ground[0] - QUARTER * (ground[0] - foot[0]), ground[1]], rise = [foot[0], foot[1] + QUARTER * (ground[1] - foot[1])];
      let rock = 0;
      if (k.spins) {
        if (view) {
          view.spin(k.yaw + 360 * k.spins * (1 - (1 - raw) ** 3));
          const spun = Math.round(k.h * view.aspect);
          if (spun !== w) { w = spun; flyer.style.width = `${w}px`; view.size(w, k.h); }
        }
        rock = k.rock * Math.sin(raw * Math.PI * 5) * (1 - raw);
      }
      place(cubic(ground[0], back[0], rise[0], foot[0], u), cubic(ground[1], back[1], rise[1], foot[1], u), 1 + (scale - 1) * u, rock);
    } else {
      cancelLifeFlight();
      return landLife(kind);
    }
    view?.draw(now);
    life.raf = askFrame(frame);
  };
  life.raf = askFrame(frame);
}
