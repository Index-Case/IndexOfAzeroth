// The Index of Azeroth. Copyright 2026 Index Case <indexofazeroth@pm.me>. PolyForm Strict 1.0.0, see LICENSE.md.
"use strict";

const HEAT = {
  WARM: 0.07,
  GLOW: 0.06,
  FIRE: 0.01,
  COOL_MS: 10000,
  TAIL_LO: 10,
  TAIL_HI: 40,
  last: {},
  bursts: {},
};

const HEAT_BLUE = tintRgb("heat-blue");
const HEAT_XP = tintRgb("xp-lit");
const heatMix = (a, b, u) => a.map((c, k) => c + (b[k] - c) * u);
function heatStops(base = HEAT_BLUE) {
  return [[0, base], [0.45, heatMix(base, tintRgb("white"), 0.45)], [0.75, heatMix(base, tintRgb("heat-pale"), 0.85)],
    [6 / 7, tintRgb("heat-warm")], [1, tintRgb("glint")]];
}

function heatT(frac) {
  return Math.max(0, Math.min(1, (HEAT.WARM - (1 - frac)) / HEAT.WARM));
}

function heatAt(t, base) {
  const ramp = heatStops(base);
  let i = 1;
  while (i < ramp.length - 1 && t > ramp[i][0]) i++;
  const [t0, c0] = ramp[i - 1], [t1, c1] = ramp[i], u = Math.max(0, Math.min(1, (t - t0) / (t1 - t0)));
  return c0.map((c, k) => Math.round(c + (c1[k] - c) * u)).join(", ");
}

const heatBloom = (t) => Math.max(0, Math.min(1, (t - 1 / 7) / (5 / 7)));

function heatTailStyle(t, base) {
  const along = (p) => Math.round(25 + 75 * (t > 0 ? p / t : 1));
  const stops = [`rgba(${heatAt(0, base)}, 0) 0%`, ...heatStops(base).filter(([p]) => p < t).map(([p]) => `rgb(${heatAt(p, base)}) ${along(p)}%`),
    `rgb(${heatAt(t, base)}) 100%`];
  const width = HEAT.TAIL_LO + (HEAT.TAIL_HI - HEAT.TAIL_LO) * t;
  return `width:${width.toFixed(1)}%;opacity:${(0.3 + 0.7 * t).toFixed(2)};--streak:${heatBloom(t).toFixed(2)};`
    + `background:linear-gradient(to right, ${stops.join(", ")})`;
}

const heatEdgeStyle = (t, base) => `--heat:${heatAt(t, base)};--bloom:${heatBloom(t).toFixed(2)}`;

function heatStage(frac, point = 0) {
  const left = 1 - frac, hair = 1e-9;
  if (!(left > 0) || left > HEAT.WARM + hair) return "";
  return left <= Math.max(HEAT.FIRE, point) + hair ? "fire" : left <= HEAT.GLOW + hair ? "glow" : "warm";
}

function heatEdgeHtml(frac, point = 0, base = HEAT_BLUE) {
  const stage = heatStage(frac, point);
  if (!stage) return "";
  const t = heatT(frac);
  return `<span class="heat-tail" style="${heatTailStyle(t, base)}"></span>`
    + `<span class="heat-edge heat-${stage}" data-stage="${stage}" style="${heatEdgeStyle(t, base)}"></span>`;
}

const heatLayer = { raf: 0, marks: [], sized: null };
const heatPoints = (html) => `<u class="heat-pt">${html}</u>`.repeat(3);
const HEAT_TIP = {
  warm: '<b class="heat-bloom"></b>',
  glow: heatPoints('<b class="heat-ember"></b><b class="heat-bloom"></b>'),
  fire: heatPoints(`<b class="heat-ember"></b><b class="heat-bloom"></b><b class="heat-flame"></b><b class="heat-core"></b><b class="heat-line"></b>${"<i></i>".repeat(6)}`),
};
function heatTips(layer = $("heat-layer")) {
  const marks = [...document.querySelectorAll(".heat-edge")].filter((m) => !m.hidden && m.getClientRects().length);
  while (layer.children.length > marks.length) layer.lastChild.remove();
  marks.forEach((mark, i) => {
    const tip = layer.children[i] || layer.appendChild(document.createElement("span"));
    const stage = mark.dataset.stage;
    if (tip.dataset.stage !== stage) {
      tip.dataset.stage = stage;
      tip.className = `heat-tip heat-${stage}`;
      tip.innerHTML = HEAT_TIP[stage];
    }
    const bar = mark.parentElement.getBoundingClientRect(), x = bar.right, y = bar.top + bar.height / 2;
    const home = mark.closest(HEAT_HOMES), panel = home?.getBoundingClientRect();
    const over = document.elementFromPoint(Math.min(x, innerWidth - 1), y);
    tip.hidden = (!!panel && (y < panel.top || y > panel.bottom)) || (!!over && !!home && !home.contains(over));
    tip.style.cssText = `left:${x}px;top:${y}px;--bh:${bar.height}px;${mark.style.cssText}`;
  });
  return marks.length > 0;
}
const HEAT_HOMES = ".status, .drawer-body, .xpbar";
const HEAT_OVER = ".stage > *";
function heatPlace() {
  if (!heatLayer.raf) heatLayer.raf = askFrame(heatFrame);
}
function heatFrame() {
  heatLayer.raf = 0;
  heatTips();
}
function heatWatch() {
  const marks = [...document.querySelectorAll(".heat-edge")].filter((m) => !m.hidden);
  if (marks.length === heatLayer.marks.length && marks.every((m, i) => m === heatLayer.marks[i])) return;
  heatLayer.marks = marks;
  heatLayer.sized ||= new ResizeObserver(heatPlace);
  heatLayer.sized.disconnect();
  const homes = marks.map((m) => [...(m.closest(HEAT_HOMES)?.children || [])]).flat();
  const watched = new Set([...marks.map((m) => m.parentElement), ...homes, ...(marks.length ? document.querySelectorAll(HEAT_OVER) : [])]);
  for (const el of watched) heatLayer.sized.observe(el);
  heatPlace();
}
function heatMoved(e) {
  if (heatLayer.marks.some((m) => !e.target.contains || e.target.contains(m))) heatPlace();
}
if (typeof addEventListener === "function") {
  addEventListener("scroll", heatMoved, { capture: true, passive: true });
  addEventListener("resize", heatMoved);
}

function heatLevelled(key, level, now = performance.now()) {
  const was = HEAT.last[key];
  HEAT.last[key] = level;
  if (was != null && level > was) HEAT.bursts[key] = now;
  const at = HEAT.bursts[key];
  if (at == null) return null;
  if (now - at >= HEAT.COOL_MS) {
    delete HEAT.bursts[key];
    return null;
  }
  return now - at;
}

function heatWho() {
  return app.character || "";
}

function heatBurstHtml(age) {
  return age == null ? "" : `<span class="heat-burst" style="animation-delay:-${Math.round(age)}ms"></span>`;
}
