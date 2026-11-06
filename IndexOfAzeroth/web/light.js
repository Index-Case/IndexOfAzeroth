// The Index of Azeroth. Copyright 2026 Index Case <indexofazeroth@pm.me>. PolyForm Strict 1.0.0, see LICENSE.md.
"use strict";

const SUN = { RISE: 5.5, NOON: 12, SET: 21 };
const GAME_SUN = { bearing: 315,
  polar: [[0, 125], [0.2437, 92], [0.2722, 94], [0.3174, 100], [0.4042, 142], [0.5, 166], [0.5674, 170], [0.7792, 94], [0.875, 92], [1, 125]] };
const SUN_HIGH = Math.max(...GAME_SUN.polar.map(([, p]) => p)) - 90, SUN_LOW = Math.min(...GAME_SUN.polar.map(([, p]) => p)) - 90;
const SHADOW_FULL_AT = 8;
const SUN_SHADOW = { far: 0.3, stretch: 1.5, least: 0.6 };
const LAMP_FULL_AT = 12;

const SKY_DISC = 0.53, EDGE_SIGMA = 0.268;
const penumbra = (along) => Math.max(0, along) * Math.tan(SKY_DISC * Math.PI / 180);
const lanternPenumbra = (size, toCaster, toGround) => (toCaster > 0 ? size * Math.max(0, toGround) / toCaster : 0);
const edgeSigma = (width, perYard) => (perYard > 0 ? width * perYard * EDGE_SIGMA : 0);

const ARROW_SHADOW = { height: 2.4, most: 8, yards: 2, alpha: 0.55 };
const SHADOW_DROP = 20;
const SHEET_BLUR = 18;
const POINTER_SHADOW = { height: 60, mostShare: 0.22, alpha: 0.375, groundAlpha: 0.495, groundScale: 49 / 84, zoomedJump: 0.2, low: 8, yards: 33 };

function pointerAt(depth) {
  const d = Math.min(1, Math.max(0, depth || 0));
  return { height: POINTER_SHADOW.height * Math.pow(POINTER_SHADOW.low / POINTER_SHADOW.height, d),
    scale: Math.pow(POINTER_SHADOW.groundScale, d), alpha: POINTER_SHADOW.alpha + (POINTER_SHADOW.groundAlpha - POINTER_SHADOW.alpha) * d };
}

const POINTER_GROUND = { ...pointerAt(1), height: 0 };

const pointerYards = (height) => POINTER_SHADOW.yards * height / POINTER_SHADOW.height;

function pointerAbove(height) {
  const h = Math.max(0, height), top = POINTER_SHADOW.height, low = POINTER_SHADOW.low;
  const depth = h >= top ? 0 : h <= low ? 1 : Math.log(h / top) / Math.log(low / top);
  return { ...pointerAt(depth), height: h };
}

function onSheet(sheet, [x, y]) {
  const dx = x - sheet.at[0], dy = y - sheet.at[1], [u, v] = [sheet.u, sheet.v];
  const a = (dx * u[0] + dy * u[1]) / (u[0] * u[0] + u[1] * u[1]), b = (dx * v[0] + dy * v[1]) / (v[0] * v[0] + v[1] * v[1]);
  return a >= 0 && a <= 1 && b >= 0 && b <= 1;
}
const SHEET_SNAP = 40;

function pointerDepth(zoom, least, most, wide) {
  if (wide || !(zoom > least)) return 0;
  const jump = Math.log(1 - POINTER_SHADOW.zoomedJump) / Math.log(POINTER_SHADOW.low / POINTER_SHADOW.height);
  return jump + (1 - jump) * Math.min(1, Math.log(zoom / least) / Math.log(most / least));
}
const LAMP = { lift: 1, glow: "lamp-glow", glowAlpha: 0.25, soft: 8, tilt: 9, stops: 12, size: 2.5, rise: 0.85,
  ref: { share: 0.15, mapPx: 1016, perYard: 11.5, full: 0.45 } };

const lanternHeight = (depth) => pointerYards(pointerAt(depth).height);
const LAMP_CONE = (() => {
  const { share, mapPx, perYard, full } = LAMP.ref, low = lanternHeight(1), tan = LAMP.size * share * mapPx / perYard / low;
  const I = Math.pow(low * low + (full * tan * low) ** 2, 1.5) / low;
  return { low, tan, half: Math.atan(tan) * 180 / Math.PI, I, heart: I / (low * low) };
})();
const poolRadius = (h) => h * LAMP_CONE.tan;
const lanternBright = (h, r) => (h > 0 ? LAMP_CONE.I * h / Math.pow(h * h + r * r, 1.5) : 0);
function coneRim(h, dx, dy, tilt = [0, 0]) {
  const len = Math.hypot(dx, dy, h);
  if (!(len > 0)) return 1;
  const c = (dx * tilt[0] + dy * tilt[1] + h * Math.sqrt(Math.max(0, 1 - tilt[0] ** 2 - tilt[1] ** 2))) / len;
  const lo = Math.cos(LAMP_CONE.half * LIGHT_RAD), hi = Math.cos((LAMP_CONE.half - LAMP.soft) * LIGHT_RAD);
  return lightEase((c - lo) / (hi - lo));
}
const LAMP_EASE = 3;
const lanternLight = (h, dx, dy, tilt) => (1 - Math.exp(-LAMP_EASE * lanternBright(h, Math.hypot(dx, dy)))) * coneRim(h, dx, dy, tilt);
const lanternGlow = (h, dx, dy, tilt) => Math.min(1, lanternBright(h, Math.hypot(dx, dy)) / LAMP_CONE.heart) * coneRim(h, dx, dy, tilt);
function lanternTilt(off, chain) {
  const out = Math.hypot(...off);
  if (!(out > 0) || !(chain > 0)) return [0, 0];
  const k = Math.sin(LAMP.tilt * LIGHT_RAD) * Math.min(1, out / chain) / out;
  return [off[0] * k, off[1] * k];
}
function lanternPool(foot, h, perYard, tilt = [0, 0]) {
  const s = Math.hypot(...tilt), u = s > 0 ? [tilt[0] / s, tilt[1] / s] : [1, 0], lean = Math.asin(Math.min(1, s)) / LIGHT_RAD;
  const near = h * Math.tan((lean - LAMP_CONE.half) * LIGHT_RAD), far = h * Math.tan(Math.min(89, lean + LAMP_CONE.half) * LIGHT_RAD);
  const mid = (near + far) / 2, rho = (far - near) / 2, light = [], glow = [];
  for (let i = 0; i < LAMP.stops; i++) {
    const k = i / (LAMP.stops - 1), dx = mid * u[0] - k * rho * u[1], dy = mid * u[1] + k * rho * u[0];
    light.push(lanternLight(h, dx, dy, tilt));
    glow.push(lanternGlow(h, dx, dy, tilt));
  }
  return { at: [foot[0] + mid * u[0] * perYard, foot[1] + mid * u[1] * perYard], radius: rho * perYard, light, glow };
}
const lanternClimb = (perYard) => LAMP_CONE.low * Math.max(1, LAMP.ref.perYard / perYard) ** LAMP.rise;
const poolStops = (pool, colour) => pool.light.map((v, i) => `${colour(v, pool.glow[i])} ${+(100 * i / (LAMP.stops - 1)).toFixed(1)}%`).join(", ");
const poolCircle = (pool) => `circle ${Math.max(1, Math.round(pool.radius))}px at ${Math.round(pool.at[0])}px ${Math.round(pool.at[1])}px`;

const GAUNTLET_SHADOW_SWITCH = { on: false };
const GAUNTLET_SHADOW = { open: pointerYards(POINTER_SHADOW.low), held: 0.5 };

const LANTERN_SHADOW = { alpha: 0.5, size: 1, least: ARROW_SHADOW.height };

function lanternQuad(sheet, at, height, raised) {
  const over = lanternOver(height, raised), k = (raised + over) / over;
  return sheetCorners(sheet).map((p) => [0, 1].map((i) => at[i] + k * (p[i] - at[i])));
}
const lanternOver = (height, raised) => Math.max(height - raised, LANTERN_SHADOW.least);
const lanternEdge = (height, raised, perYard) => edgeSigma(lanternPenumbra(LANTERN_SHADOW.size, lanternOver(height, raised), raised), perYard);
const sheetCorners = ({ at, u, v }) => [[0, 0], [1, 0], [1, 1], [0, 1]].map(([a, b]) => [0, 1].map((i) => at[i] + a * u[i] + b * v[i]));

function lanternReaches(sheet, quad, at, reach) {
  const { at: c, u, v } = sheet, w = Math.hypot(...u), h = Math.hypot(...v);
  const local = ([x, y]) => [((x - c[0]) * u[0] + (y - c[1]) * u[1]) / w, ((x - c[0]) * v[0] + (y - c[1]) * v[1]) / h];
  const [p, a, b] = [local(at), local(quad[0]), local(quad[2])];
  const [x0, x1, y0, y1] = [Math.min(a[0], b[0]), Math.max(a[0], b[0]), Math.min(a[1], b[1]), Math.max(a[1], b[1])];
  const parts = [[x0, Math.min(x1, 0), y0, y1], [Math.max(x0, w), x1, y0, y1], [x0, x1, y0, Math.min(y1, 0)], [x0, x1, Math.max(y0, h), y1]];
  return parts.some(([l, r, t, d]) => l < r && t < d && Math.hypot(Math.max(l - p[0], 0, p[0] - r), Math.max(t - p[1], 0, p[1] - d)) < reach);
}

const GAUNTLET = { size: [49, 45], topAt: 45, margin: 3, shadeWidth: 84,
  open: { file: "open", hot: [1, 2], keyword: "default" }, held: { file: "closed", hot: [26, 23], keyword: "grabbing" } };

function gauntletLight(caster, rot, was = null) {
  const { light } = caster, [across] = turned(...light.dir, rot), up = Math.max(0, light.elevation) * LIGHT_RAD;
  const off = Math.atan2(Math.abs(across) * Math.cos(up), Math.sin(up)) / LIGHT_RAD;
  const line = !was ? GAUNTLET.topAt : GAUNTLET.topAt + (was.side === "top" ? GAUNTLET.margin : -GAUNTLET.margin);
  return { sky: caster.moon ? "moon" : "sun", side: off <= line ? "top" : across > 0 ? "east" : "west" };
}

const gauntletPicture = (kind, look) => `art/guntlet_${GAUNTLET[kind].file}_${look}.png`;
const gauntletCursor = (kind, look) => `url("${gauntletPicture(kind, look)}") ${GAUNTLET[kind].hot.join(" ")}, ${GAUNTLET[kind].keyword}`;
pointerPicture({ w: GAUNTLET.size[0], h: GAUNTLET.size[1], hx: GAUNTLET.open.hot[0], hy: GAUNTLET.open.hot[1] });

const GAUNTLET_FADE = { look: 1000, grip: 200, step: 60 };

const gauntletMix = (kind, look) => ({ [`${kind} ${look}`]: 1 });
function blendMix(from, to, t) {
  const out = {};
  for (const key of new Set([...Object.keys(from), ...Object.keys(to)])) {
    const w = +(((from[key] || 0) * (1 - t)) + ((to[key] || 0) * t)).toFixed(3);
    if (w > 0) out[key] = w;
  }
  return out;
}
const mixKey = (mix) => Object.keys(mix).sort().map((key) => `${key} ${mix[key]}`).join(", ");

function mixBox(mix) {
  const [w, h] = GAUNTLET.size, keys = Object.keys(mix).sort();
  const hots = keys.map((key) => GAUNTLET[key.split(" ")[0]].hot);
  const left = Math.max(...hots.map(([x]) => x)), up = Math.max(...hots.map(([, y]) => y));
  const at = keys.map((key, i) => [key, left - hots[i][0], up - hots[i][1]]);
  return { size: [Math.max(...at.map(([, x]) => x)) + w, Math.max(...at.map(([, , y]) => y)) + h], hot: [left, up], at };
}

function mixCursor(mix, kind, blend, scale = 1) {
  const keys = Object.keys(mix);
  if (keys.length === 1 && scale === 1) { const [k, look] = keys[0].split(" "); return gauntletCursor(k, look); }
  const made = blend(mix, scale);
  return made && `url("${made.url}") ${made.hot.join(" ")}, ${GAUNTLET[kind].keyword}`;
}

const GAUNTLET_GROW = { most: 0.08, ms: 150, step: 0.01 };

const gauntletGrowth = (share) => (share == null ? 1 : 1 + GAUNTLET_GROW.most * (2 * lightClamp(share) - 1));

function gauntletBlend(doc, most = 600) {
  const pictures = {}, made = new Map();
  for (const kind of ["open", "held"]) {
    for (const look of ["sun_east", "sun_top", "sun_west", "moon_east", "moon_top", "moon_west"]) {
      const img = doc.createElement("img");
      img.src = gauntletPicture(kind, look);
      pictures[`${kind} ${look}`] = img;
    }
  }
  return (mix, scale = 1) => {
    const key = `${mixKey(mix)} ${scale}`;
    if (made.has(key)) return made.get(key);
    if (!Object.keys(mix).every((k) => pictures[k].complete && pictures[k].naturalWidth)) return null;
    const box = mixBox(mix), canvas = doc.createElement("canvas");
    [canvas.width, canvas.height] = box.size.map((v) => Math.ceil(v * scale));
    const g = canvas.getContext("2d");
    g.globalCompositeOperation = "lighter";
    g.imageSmoothingQuality = "high";
    for (const [k, x, y] of box.at) { g.globalAlpha = mix[k]; g.drawImage(pictures[k], x * scale, y * scale, GAUNTLET.size[0] * scale, GAUNTLET.size[1] * scale); }
    if (made.size >= most) made.clear();
    const frame = { url: canvas.toDataURL("image/png"), hot: box.hot.map((v) => Math.round(v * scale)) };
    made.set(key, frame);
    return frame;
  };
}

const TINT_CLEAR = { b: 1, c: 1, s: 1, rgb: "white", a: 0 };
const TINT_NIGHT = { b: 1, c: 1, s: 1, rgb: "light-night", a: 0.16 };
const TINTS = [
  [0, TINT_NIGHT],
  [SUN.RISE - 1.5, TINT_NIGHT],
  [SUN.RISE - 0.5, { b: 1, c: 1, s: 1, rgb: "light-dawn", a: 0.08 }],
  [SUN.RISE + 1, { b: 1.05, c: 1.06, s: 1.05, rgb: "white", a: 0 }],
  [10, { b: 1.02, c: 1.02, s: 1.02, rgb: "white", a: 0 }],
  [11, TINT_CLEAR],
  [13, TINT_CLEAR],
  [15.5, { b: 1, c: 1, s: 1.03, rgb: "light-afternoon", a: 0.05 }],
  [SUN.SET - 1, { b: 1, c: 1, s: 1.04, rgb: "light-sunset", a: 0.07 }],
  [SUN.SET + 0.5, { b: 1, c: 1, s: 1, rgb: "light-dusk", a: 0.08 }],
  [SUN.SET + 1.5, TINT_NIGHT],
  [24, TINT_NIGHT],
];
const NIGHT_TINTS = ["light-night", "light-dawn", "light-dusk"];
const TINTS_DAY = TINTS.map(([h, t]) => [h, NIGHT_TINTS.includes(t.rgb) ? TINT_CLEAR : t]);

const lightNeutral = (rgb) => { const y = Math.round(0.2126 * rgb[0] + 0.7152 * rgb[1] + 0.0722 * rgb[2]); return [y, y, y]; };

const LIGHT_RAD = Math.PI / 180;
const lightClamp = (v) => Math.min(1, Math.max(0, v));
const lightEase = (v) => { const t = lightClamp(v); return t * t * (3 - 2 * t); };
const dayHour = (hour) => ((hour % 24) + 24) % 24;

function skyAt(hour) {
  const h = dayHour(hour);
  if (h >= SUN.RISE && h <= SUN.SET) {
    const up = h <= SUN.NOON ? (h - SUN.RISE) / (SUN.NOON - SUN.RISE) : (SUN.SET - h) / (SUN.SET - SUN.NOON);
    return { hour: h, elevation: 90 * up };
  }
  const night = SUN.RISE + 24 - SUN.SET, since = dayHour(h - SUN.SET);
  return { hour: h, elevation: -90 * Math.min(since, night - since) / (night / 2) };
}

function sunAt(hour) {
  const h = dayHour(hour), d = h / 24, keys = GAME_SUN.polar, k = keys.findIndex(([at]) => at > d);
  const [d0, p0] = keys[k - 1], [d1, p1] = keys[k], b = GAME_SUN.bearing * LIGHT_RAD;
  return { hour: h, elevation: p0 + (p1 - p0) * (d - d0) / (d1 - d0) - 90, bearing: GAME_SUN.bearing, dir: [Math.sin(b), -Math.cos(b)] };
}

const moonAt = (hour) => ({ ...sunAt(hour), moon: true });

const sunUp = (elevation) => lightClamp((elevation - SUN_LOW) / (SUN_HIGH - SUN_LOW));

function castShadow(light, height, most) {
  if (light.elevation <= 0) return { x: 0, y: 0, length: 0, strength: 0, stretch: 1 };
  const length = Math.min(most, height / Math.tan(light.elevation * LIGHT_RAD)), [x, y] = light.dir.map((v) => -v * length);
  if (light.moon) return { x, y, length, strength: lightClamp(4 * length / most), stretch: 1 };
  const far = most > 0 ? length / most : 0, day = SUN_SHADOW.least + (1 - SUN_SHADOW.least) * sunUp(light.elevation);
  return { x, y, length, strength: day * (1 - SUN_SHADOW.far * far), stretch: 1 + SUN_SHADOW.stretch * (1 - Math.sin(light.elevation * LIGHT_RAD)) };
}

function shadowEdge(light, yards, height, most, perYard) {
  if (light.elevation <= 0 || !(yards > 0) || !(height > 0)) return 0;
  const along = yards * Math.hypot(1, castShadow(light, height, most).length / height);
  return edgeSigma(penumbra(along), perYard);
}

const shadowAt = (hour, height, most) => castShadow(sunAt(hour), height, most);

function turned(x, y, rot) {
  const c = Math.cos(rot), n = Math.sin(rot);
  return [x * c - y * n, x * n + y * c];
}

function lampAt(hour, night = true) {
  return night !== false ? lightClamp(-skyAt(hour).elevation / LAMP_FULL_AT) : 0;
}

const MOON = { shadow: 0.5, rise: 15, shade: 0.8 };

function moonlightAt(hour, night = true) {
  return night !== false ? lightEase(-skyAt(hour).elevation / MOON.rise) : 0;
}

function casterAt(hour, night = true) {
  if (night === false) return { light: sunAt(hour), share: 1, moon: false };
  const sky = skyAt(hour).elevation;
  if (sky > 0) return { light: sunAt(hour), share: lightEase(sky / SHADOW_FULL_AT), moon: false };
  return { light: moonAt(hour), share: MOON.shadow * lampAt(hour), moon: true };
}

const moonShade = () => lightNeutral(tintRgb("light-moon")).map((v) => Math.round(v * (1 - MOON.shade)));

const SUN_COLOURS = [
  [SUN.RISE - 1, "light-dawn-rose"], [SUN.RISE + 0.5, "light-dawn-rose"], [SUN.RISE + 2, "light-sun-east"], [SUN.NOON, "light-sun-noon"],
  [SUN.NOON + 3, "light-sun-noon"], [SUN.SET - 0.5, "light-sunset-pink"],
];
function sunHueAt(hour) {
  const h = dayHour(hour);
  const k = SUN_COLOURS.findIndex(([at]) => at >= h);
  if (k < 0) return tintRgb(SUN_COLOURS[SUN_COLOURS.length - 1][1]);
  if (k === 0) return tintRgb(SUN_COLOURS[0][1]);
  const [h0, from] = SUN_COLOURS[k - 1], [h1, to] = SUN_COLOURS[k], t = (h - h0) / (h1 - h0);
  const [c0, c1] = [tintRgb(from), tintRgb(to)];
  return c0.map((v, i) => Math.round(v + (c1[i] - v) * t));
}
const NIGHTLESS_TURN = 1;
function sunColourAt(hour, night = true) {
  const h = dayHour(hour);
  if (night !== false || (h >= SUN.RISE && h <= SUN.SET)) return lightNeutral(sunHueAt(h));
  const since = dayHour(h - SUN.SET), till = dayHour(SUN.RISE - h), noon = lightNeutral(tintRgb("light-sun-noon"));
  const edge = lightNeutral(sunHueAt(since < till ? SUN.SET : SUN.RISE)), t = lightEase(Math.min(since, till) / NIGHTLESS_TURN);
  return edge.map((v, i) => Math.round(v + (noon[i] - v) * t));
}

const VIGNETTE = { a: 0.6, reach: 0.9, power: 5, dark: 18, at: [0, 0.04, 0.08, 0.15, 0.25, 1 / 3, 0.45, 0.6, 0.75, 0.9] };

const nightAt = (hour, night = true) => (night !== false ? lightEase(-skyAt(hour).elevation / VIGNETTE.dark) : 0);

function vignetteOf(night) {
  if (VIGNETTE.a * night < 0.002) return "none";
  const rgb = lightNeutral(tintRgb("light-vignette"));
  const stops = VIGNETTE.at.map((x) => `${lightRgba(rgb, VIGNETTE.a * night * Math.pow(1 - x / VIGNETTE.reach, VIGNETTE.power))} ${+(100 - 100 * x).toFixed(1)}%`);
  return `radial-gradient(ellipse closest-side at 50% 50%, ${stops.reverse().join(", ")})`;
}

function vignetteMaskOf(lamp = 0, pool = null) {
  if (!pool || lamp <= 0) return "none";
  return `radial-gradient(${poolCircle(pool)}, ${poolStops(pool, (v) => tint("black", +(1 - LAMP.lift * lamp * v).toFixed(3)))})`;
}

function tintAt(hour, night = true) {
  const h = dayHour(hour), table = night !== false ? TINTS : TINTS_DAY;
  let k = 1;
  while (table[k][0] < h) k++;
  const [h0, from] = table[k - 1], [h1, to] = table[k];
  const t = (h - h0) / (h1 - h0), mix = (p, q) => p + (q - p) * t;
  const a = mix(from.a, to.a);
  const [c0, c1] = [lightNeutral(tintRgb(from.rgb)), lightNeutral(tintRgb(to.rgb))];
  const rgb = [0, 1, 2].map((i) => Math.round(a ? mix(c0[i] * from.a, c1[i] * to.a) / a : 255));
  return { b: mix(from.b, to.b), c: mix(from.c, to.c), s: mix(from.s, to.s), rgb, a };
}

function filterOf(t) {
  const same = (v) => Math.abs(v - 1) < 0.002;
  if (same(t.b) && same(t.c) && same(t.s)) return "";
  return `brightness(${t.b.toFixed(3)}) contrast(${t.c.toFixed(3)}) saturate(${t.s.toFixed(3)})`;
}

function skyOf(hour, night = true, under = 0) {
  const k = 1 - lightClamp(under), t = tintAt(hour, night), toward = (v) => 1 + (v - 1) * k;
  return { tint: { b: toward(t.b), c: toward(t.c), s: toward(t.s), rgb: t.rgb, a: t.a * k },
    night: nightAt(hour, night) * k, lamp: lampAt(hour, night) * k };
}

const lightRgba = (rgb, a) => `rgba(${rgb[0]}, ${rgb[1]}, ${rgb[2]}, ${+a.toFixed(3)})`;

function overlayOf(t, lamp = 0, pool = null) {
  if (t.a < 0.002) return "none";
  if (!pool || lamp <= 0) return lightRgba(t.rgb, t.a);
  return `${lampGlowOf(lamp, pool)}, radial-gradient(${poolCircle(pool)}, ${poolStops(pool, (v) => lightRgba(t.rgb, t.a * (1 - LAMP.lift * lamp * v)))})`;
}

function lampGlowOf(lamp = 0, pool = null) {
  if (!pool || lamp <= 0) return "none";
  const glow = tintRgb(LAMP.glow);
  return `radial-gradient(${poolCircle(pool)}, ${poolStops(pool, (v, g) => lightRgba(glow, LAMP.glowAlpha * lamp * g))})`;
}


const lightHexRgb = (hex) => [1, 3, 5].map((i) => parseInt(hex.slice(i, i + 2), 16));
const lightMix = (hex, to, share) => {
  const c = lightHexRgb(hex);
  return `#${c.map((v, i) => Math.round(v + (to[i] - v) * share).toString(16).padStart(2, "0")).join("")}`;
};

function arrowLook(classColor, gold) {
  if (!classColor) return { lit: gold.lit, mid: gold.gold, shade: gold.shade, edge: null, rim: gold.rim };
  return { lit: lightMix(classColor, [255, 255, 255], 0.4), mid: classColor, shade: lightMix(classColor, [0, 0, 0], 0.28),
    edge: gold.gold, rim: gold.rim };
}

function paintArrow(g, x, y, angle, look, shadow, dpr) {
  g.save();
  g.translate(x, y);
  g.rotate(angle);
  arrowPath(g);
  g.lineJoin = "round";
  if (shadow) {
    g.shadowColor = shadow.color; g.shadowBlur = shadow.blur * dpr;
    g.shadowOffsetX = shadow.x * dpr; g.shadowOffsetY = shadow.y * dpr;
    g.fillStyle = look.rim; g.fill();
    g.shadowColor = tint("black", 0); g.shadowBlur = 0; g.shadowOffsetX = 0; g.shadowOffsetY = 0;
  }
  g.lineWidth = look.edge ? 4 : 3; g.strokeStyle = look.rim; g.stroke();
  if (look.edge) { g.lineWidth = 2; g.strokeStyle = look.edge; g.stroke(); }
  const fill = g.createLinearGradient(0, -15, 0, 11);
  fill.addColorStop(0, look.lit); fill.addColorStop(0.45, look.mid); fill.addColorStop(1, look.shade);
  g.fillStyle = fill; g.fill();
  g.restore();
}

function arrowPath(g) {
  g.beginPath();
  ARROW_SHAPE.forEach(([px, py], k) => (k ? g.lineTo(px, py) : g.moveTo(px, py)));
  g.closePath();
}

const ARROW_GLOW = { blur: 3, width: 2, alpha: 0.9 };
const GLOW_AWAY = 1000;
function paintArrowGlow(g, x, y, angle, color, dpr) {
  g.save();
  g.translate(x, y);
  g.rotate(angle);
  arrowPath(g);
  g.clip();
  g.rotate(-angle);
  g.translate(-GLOW_AWAY, 0);
  g.rotate(angle);
  arrowPath(g);
  g.lineJoin = "round"; g.lineWidth = ARROW_GLOW.width; g.strokeStyle = color;
  g.shadowColor = color; g.shadowBlur = ARROW_GLOW.blur * dpr;
  g.shadowOffsetX = GLOW_AWAY * dpr; g.shadowOffsetY = 0;
  g.globalAlpha *= ARROW_GLOW.alpha;
  g.stroke();
  g.restore();
}

const ARROW_LIGHT = { most: 0.2, settle: 0.6, close: 0.001 };

const arrowLightGoal = (night, shade) => lightClamp(Math.max(0.5 * lightClamp(night || 0), lightClamp(shade || 0)));

const arrowLightSettled = (level, goal) => Math.abs(level - goal) < ARROW_LIGHT.close;

function arrowLightStep(state, goal, dt) {
  const omega = 2 / ARROW_LIGHT.settle, x = omega * dt, decay = 1 / (1 + x + 0.48 * x * x + 0.235 * x * x * x);
  const from = state.level, change = from - goal, push = (state.speed + omega * change) * dt;
  state.speed = (state.speed - omega * push) * decay;
  let level = goal + (change + push) * decay;
  if ((goal > from) === (level > goal) && level !== goal) { level = goal; state.speed = 0; }
  if (arrowLightSettled(level, goal)) { level = goal; state.speed = 0; }
  state.level = lightClamp(level);
  return state.level;
}

function arrowLit(look, level) {
  const k = 1 + ARROW_LIGHT.most * lightClamp(level || 0);
  if (k === 1) return look;
  const up = (hex) => (/^#[0-9a-f]{6}$/i.test(hex || "") ? `#${lightHexRgb(hex).map((v) => Math.min(255, Math.round(v * k)).toString(16).padStart(2, "0")).join("")}` : hex);
  return { ...look, lit: up(look.lit), mid: up(look.mid), shade: up(look.shade), edge: up(look.edge) };
}


const ARROW_SHAPE = [[0, -15], [10, 11], [0, 5], [-10, 11]];
const FIRE_GLOW = {
  radius: 22, alpha: 0.32, step: 50,
  points: [
    { at: [0, -3], reach: [1.2, 1.5], speeds: [1.7, 2.3, 5.1], phase: 0 },
    { at: [-4, 5], reach: [1, 1], speeds: [2.1, 1.6, 6.3], phase: 2.1 },
    { at: [4, 5], reach: [1, 1], speeds: [1.4, 2.7, 4.7], phase: 4.2 },
  ],
};

function inArrow(x, y, shape = ARROW_SHAPE) {
  let inside = false;
  for (let i = 0, j = shape.length - 1; i < shape.length; j = i++) {
    const [xi, yi] = shape[i], [xj, yj] = shape[j];
    if ((yi > y) !== (yj > y) && x < ((xj - xi) * (y - yi)) / (yj - yi) + xi) inside = !inside;
  }
  return inside;
}

function firePoints(t, spread = 1) {
  const s = t / 1000;
  return FIRE_GLOW.points.map(({ at, reach, speeds: [sx, sy, sa], phase }) => ({
    x: spread * (at[0] + reach[0] * Math.sin(s * sx + phase)),
    y: spread * (at[1] + reach[1] * Math.sin(s * sy + phase * 1.3)),
    strength: 0.6 + 0.25 * Math.sin(s * sa + phase) + 0.15 * Math.sin(s * sa * 2.7 + phase * 0.7),
  }));
}

function paintFire(g, x, y, angle, t, glow, spread = 1, radius = FIRE_GLOW.radius) {
  g.save();
  g.translate(x, y);
  g.rotate(angle);
  for (const p of firePoints(t, spread)) {
    const fill = g.createRadialGradient(p.x, p.y, 0, p.x, p.y, radius);
    fill.addColorStop(0, glow(FIRE_GLOW.alpha * p.strength));
    fill.addColorStop(1, glow(0));
    g.fillStyle = fill;
    g.fillRect(p.x - radius, p.y - radius, radius * 2, radius * 2);
  }
  g.restore();
}


const LANTERN = { period: 0.9, damping: 0.2, follow: 0.35, chainShare: 0.4, smoothing: 0.04, longest: 0.05 };

const lanternAtRest = () => ({ off: [0, 0], vel: [0, 0], pivotVel: [0, 0] });

function lanternStep(s, moved, dt, chain) {
  const step = Math.min(LANTERN.longest, dt), w = (2 * Math.PI) / LANTERN.period;
  const keep = Math.exp(-step / LANTERN.smoothing);
  const pivotVel = moved.map((m, i) => m / dt + (s.pivotVel[i] - m / dt) * keep);
  for (const i of [0, 1]) {
    s.vel[i] += (-w * w * s.off[i] - 2 * LANTERN.damping * w * s.vel[i]) * step - LANTERN.follow * (pivotVel[i] - s.pivotVel[i]);
    s.off[i] += s.vel[i] * step;
  }
  s.pivotVel = pivotVel;
  const out = Math.hypot(...s.off);
  if (out > chain) {
    const r = s.off.map((v) => v / out), along = s.vel[0] * r[0] + s.vel[1] * r[1];
    s.off = r.map((v) => v * chain);
    if (along > 0) s.vel = s.vel.map((v, i) => v - along * r[i]);
  }
  return Math.hypot(...s.off) < 0.3 && Math.hypot(...s.vel) < 3 && Math.hypot(...s.pivotVel) < 3;
}


const YOU_BOX = 80;

const clockMinutes = (clock, now) => (clock.minutes + (now - clock.at) / 60000) % 1440;

class MapLight {
  constructor({ layer, night, shade, canvas, you, cast = null, root = null, now = () => Date.now(), frame = (fn) => askFrame(fn), blend = null,
    swung = () => {} }) {
    Object.assign(this, { layer, night, shade, canvas, you, cast, root, now, frame, blend, swung });
    this.youOver = new OverLight(you);
    this.dpr = 1;
    this.castBox = null;
    this.cursors = { open: null, held: null };
    this.showing = null;
    this.fading = null;
    this.clock = null;
    this.rot = 0;
    this.at = null;
    this.depth = 0;
    this.perYard = 0;
    this.grabbed = false;
    this.size = [0, 0];
    this.shown = { filter: null, overlay: null, night: null, mask: null, shade: null, outline: null, cursor: null, cast: "" };
    this.lantern = lanternAtRest();
    this.swinging = null;
    this.gauntlet = null;
    this.sheetList = [];
    this.sheetHeight = 0;
    this.paper = { t: 0, to: 0, time: 0, sheet: null, asked: false, fresh: true };
    this.own = false;
    this.ground = false;
    Object.assign(this, { growTo: 1, growSize: 1, grown: 1, growing: null });
    this.nightOn = true;
    this.under = 0;
    this.lightGauntlet();
  }

  underground(share) {
    share = lightClamp(+share || 0);
    if (share === this.under) return;
    this.under = share;
    this.paint();
  }

  sky() {
    return skyOf(this.hour(), this.nightOn, this.under);
  }

  nightShown(on) {
    on = !!on;
    if (on === this.nightOn) return;
    this.nightOn = on;
    if (!on) { this.lantern = lanternAtRest(); this.swinging = null; }
    this.paint();
  }

  lamp() {
    return this.sky().lamp;
  }

  ownLight(by, under = null) {
    this.growWith(by ? under : null);
    const own = by === true || by === "render", ground = own || by === "minimap";
    if (own === this.own && ground === this.ground) return;
    this.ground = ground;
    if (own !== this.own) { this.own = own; this.paint(); } else this.placeShade();
  }

  gauntletShade() {
    if (!GAUNTLET_SHADOW_SWITCH.on) return null;
    const most = POINTER_SHADOW.mostShare * Math.min(...this.size), ground = this.grabbed ? POINTER_GROUND : pointerAt(this.depth);
    if (!this.at || !this.shown.cursor || this.paper.t > 0 || this.shadeStrength(this.caster(), ground.height, most) < 0.01) return null;
    const kind = this.grabbed ? "held" : "open";
    return { picture: gauntletPicture(kind, this.shown.cursor), hot: GAUNTLET[kind].hot, size: GAUNTLET.size, at: this.at,
      yards: GAUNTLET_SHADOW[kind] };
  }

  lightGauntlet() {
    this.gauntlet = this.minutes() != null ? gauntletLight(casterAt(this.hour(), this.nightOn), this.rot, this.gauntlet) : { sky: "sun", side: "top" };
    const look = `${this.gauntlet.sky}_${this.gauntlet.side}`;
    if (look === this.shown.cursor) return;
    this.shown.cursor = look;
    this.showGauntlet();
  }

  showGauntlet() {
    if (!this.root) return;
    const look = this.shown.cursor, kind = this.grabbed ? "held" : "open", other = this.grabbed ? "open" : "held";
    const to = gauntletMix(kind, look), aim = this.fading ? this.fading.to : this.showing;
    if (!aim || !this.blend) {
      this.showing = to;
      for (const k of ["open", "held"]) this.setCursor(k, this.cursorOf(k, gauntletMix(k, look)));
      return;
    }
    this.setCursor(other, this.cursorOf(other, gauntletMix(other, look)));
    const ms = Object.keys(aim)[0].startsWith(`${kind} `) ? GAUNTLET_FADE.look : GAUNTLET_FADE.grip;
    const fade = { prop: kind, from: this.showing, to, start: this.now(), ms, steps: Math.max(2, Math.round(ms / GAUNTLET_FADE.step)), step: -1 };
    this.fading = fade;
    this.fadeStep(fade);
  }

  fadeStep(fade) {
    if (fade !== this.fading) return;
    const step = Math.min(fade.steps, Math.floor(((this.now() - fade.start) / fade.ms) * fade.steps));
    if (step !== fade.step) {
      fade.step = step;
      const mix = step === fade.steps ? fade.to : blendMix(fade.from, fade.to, step / fade.steps);
      const cursor = mixCursor(mix, fade.prop, this.blend, this.grown);
      if (!cursor) fade.step = fade.steps;
      this.showing = cursor ? mix : fade.to;
      this.setCursor(fade.prop, cursor || this.cursorOf(fade.prop, fade.to));
    }
    if (fade.step < fade.steps) this.frame(() => this.fadeStep(fade));
    else this.fading = null;
  }

  cursorOf(kind, mix) {
    return (this.blend && this.grown !== 1 && mixCursor(mix, kind, this.blend, this.grown)) || mixCursor(mix, kind, this.blend);
  }

  growWith(share) {
    const to = gauntletGrowth(share);
    if (to === this.growTo) return;
    this.growTo = to;
    if (!this.growing) { this.growing = { t: this.now() }; this.frame(() => this.growStep()); }
  }

  growStep() {
    const t = this.now(), k = 1 - Math.exp(-(t - this.growing.t) / GAUNTLET_GROW.ms);
    this.growing.t = t;
    this.growSize += (this.growTo - this.growSize) * k;
    if (Math.abs(this.growTo - this.growSize) < GAUNTLET_GROW.step / 2) this.growSize = this.growTo;
    const grown = +(Math.round(this.growSize / GAUNTLET_GROW.step) * GAUNTLET_GROW.step).toFixed(2);
    if (grown !== this.grown) {
      this.grown = grown;
      const look = this.shown.cursor, fadingKind = this.fading?.prop;
      for (const kind of ["open", "held"]) if (look && kind !== fadingKind) this.setCursor(kind, this.cursorOf(kind, gauntletMix(kind, look)));
    }
    if (this.growSize === this.growTo) this.growing = null;
    else this.frame(() => this.growStep());
  }

  setCursor(kind, value) {
    if (this.cursors[kind] === value) return;
    this.cursors[kind] = value;
    if (kind === "open") this.root.style.setProperty("--cursor-open", value);
    else this.root.style.setProperty("--cursor-held", value);
  }

  report(minutes) {
    if (typeof minutes !== "number" || !Number.isFinite(minutes)) return;
    if (this.clock && Math.floor(clockMinutes(this.clock, this.now())) === minutes) return;
    this.clock = { minutes, at: this.now() };
  }

  minutes() {
    return this.clock ? clockMinutes(this.clock, this.now()) : null;
  }

  minuteIn() {
    const m = this.minutes();
    return m == null ? Infinity : (Math.floor(m) + 1 - m) * 60000;
  }

  hour() {
    const m = this.minutes();
    return m == null ? SUN.NOON : m / 60;
  }

  arrowShadow() {
    const by = this.caster(), { height, most, yards } = ARROW_SHADOW, s = castShadow(by.light, height, most);
    if (s.strength * by.share < 0.01) return null;
    const alpha = +(ARROW_SHADOW.alpha * s.strength * by.share).toFixed(3);
    const [x, y] = turned(s.x, s.y, this.rot), blur = +(2 * shadowEdge(by.light, yards, height, most, this.perYard)).toFixed(2);
    return { x, y, blur, color: by.moon ? lightRgba(moonShade(), alpha) : tint("black", alpha) };
  }

  sheetShadow(depth) {
    const most = POINTER_SHADOW.mostShare * Math.min(...this.size), height = pointerAt(depth).height;
    const by = this.caster(), s = castShadow(by.light, height, most);
    const [x, y] = turned(s.x, s.y, this.rot), strength = this.shadeStrength(by, height, most);
    const blur = most > 0 ? SHEET_BLUR : 0;
    return { x: +x.toFixed(2), y: +(y + SHADOW_DROP).toFixed(2), strength: strength >= 0.01 ? +strength.toFixed(3) : 0,
      rgb: by.moon ? moonShade() : [0, 0, 0], blur: +blur.toFixed(2) };
  }

  sheets(list, depth) {
    this.sheetList = list;
    this.sheetHeight = pointerAt(depth).height;
    this.placeShade();
    this.castLantern();
  }

  resize(w, h, dpr = 1) {
    this.size = [w, h];
    this.dpr = dpr;
    if (this.cast) {
      Object.assign(this.cast, { width: Math.round(w * dpr), height: Math.round(h * dpr) });
      Object.assign(this.cast.style, { width: `${w}px`, height: `${h}px` });
      this.castBox = null;
      this.shown.cast = "";
      this.cast.hidden = true;
    }
    this.paint();
  }

  turn(rot) {
    if (rot === this.rot) return;
    this.rot = rot;
    this.lightGauntlet();
    this.paintOverlay();
    this.placeShade();
  }

  lower(depth, perYard = 0) {
    if (depth === this.depth && perYard === this.perYard) return;
    this.depth = depth;
    this.perYard = perYard;
    this.placeShade();
    if (this.lamp() > 0) this.paintOverlay();
  }

  grab(on) {
    if (!!on === this.grabbed) return;
    this.grabbed = !!on;
    this.showGauntlet();
    this.placeShade();
  }

  pointer(x, y) {
    const was = this.at;
    this.at = x == null ? null : [x, y];
    this.placeShade();
    if (this.lamp() <= 0) return;
    if (this.at && !this.swinging) {
      this.swinging = { at: was || this.at, t: this.now() };
      this.frame(() => this.swing());
    }
    if (!this.at) this.paintOverlay();
  }

  swing() {
    const t = this.now(), dt = (t - this.swinging.t) / 1000, from = this.swinging.at;
    let rest = !this.at || this.lamp() <= 0;
    if (!rest && dt > 0) {
      rest = lanternStep(this.lantern, [this.at[0] - from[0], this.at[1] - from[1]], dt, LANTERN.chainShare * this.reach());
      this.swinging = { at: this.at, t };
    }
    if (rest) { this.lantern = lanternAtRest(); this.swinging = null; } else this.frame(() => this.swing());
    this.paintOverlay();
    this.swung();
  }

  reach() {
    return poolRadius(lanternHeight(this.depth)) * this.yardPx();
  }

  yardPx() {
    return this.perYard > 0 ? this.perYard : LAMP.ref.perYard * Math.min(...this.size) / LAMP.ref.mapPx;
  }

  lanternNow() {
    const lamp = this.lamp(), perYard = this.yardPx();
    if (!this.at || lamp <= 0 || !(perYard > 0)) return null;
    const off = this.lantern.off, foot = [this.at[0] + off[0], this.at[1] + off[1]];
    const tilt = lanternTilt(off, LANTERN.chainShare * this.reach());
    const h = lanternClimb(perYard);
    return { foot, h, perYard, tilt, lamp, pool: lanternPool(foot, h, perYard, tilt) };
  }

  paint() {
    const [w, h] = this.size;
    this.clear = { l: 0, r: w, t: 0, b: h };
    const f = this.own ? "" : filterOf(this.sky().tint);
    if (f !== this.shown.filter) this.canvas.style.filter = this.shown.filter = f;
    this.lightGauntlet();
    this.paintOverlay();
    this.placeShade();
  }

  paintOverlay() {
    const sky = this.sky(), lantern = this.lanternNow(), lamp = lantern ? lantern.lamp : 0, pool = lantern && lantern.pool;
    const tinted = this.own ? lampGlowOf(lamp, pool) : overlayOf(sky.tint, lamp, pool);
    const bg = tinted;
    if (bg !== this.shown.overlay) this.layer.style.background = this.shown.overlay = bg;
    const night = this.own ? "none" : vignetteOf(sky.night), mask = night === "none" ? "none" : vignetteMaskOf(lamp, pool);
    if (night !== this.shown.night) this.night.style.background = this.shown.night = night;
    if (mask !== this.shown.mask) this.night.style.maskImage = this.shown.mask = mask;
    this.castLantern();
  }

  castLantern() {
    const el = this.cast;
    if (!el) return;
    const lantern = this.lanternNow(), lamp = lantern ? lantern.lamp : 0, at = lantern && lantern.foot, pool = lantern && lantern.pool;
    const reach = pool ? pool.radius : 0;
    const height = pointerAt(this.depth).height, casts = [];
    for (const sheet of at ? this.sheetList : []) {
      const raised = this.sheetHeight * sheet.fade, quad = lanternQuad(sheet, at, height, raised), alpha = +(LANTERN_SHADOW.alpha * lamp * sheet.fade).toFixed(3);
      const blur = +lanternEdge(height, raised, this.perYard).toFixed(2);
      if (alpha >= 0.01 && lanternReaches(sheet, quad, pool.at, reach)) casts.push({ sheet, quad, alpha, blur });
    }
    const r = (p) => p.map((v) => Math.round(v * 2) / 2);
    const key = casts.length ? JSON.stringify([r(at), r(pool.at), Math.round(reach), casts.map((c) => [c.alpha, c.blur, c.quad.map(r), [c.sheet.at, c.sheet.u, c.sheet.v].map(r)])]) : "";
    if (key === this.shown.cast) return;
    this.shown.cast = key;
    const g = el.getContext("2d");
    g.setTransform(this.dpr, 0, 0, this.dpr, 0, 0);
    if (this.castBox) g.clearRect(...this.castBox);
    this.castBox = null;
    el.hidden = !casts.length;
    if (!casts.length) return;
    const pad = 3 * Math.max(...casts.map((c) => c.blur)) + 2, [cx, cy] = pool.at;
    const box = [cx - reach - pad, cy - reach - pad, 2 * (reach + pad), 2 * (reach + pad)];
    const rgb = moonShade(), path = (quad) => { g.beginPath(); quad.forEach(([x, y], i) => (i ? g.lineTo(x, y) : g.moveTo(x, y))); g.closePath(); };
    g.save();
    g.beginPath(); g.rect(...box); g.clip();
    for (const { quad, alpha, blur } of casts) {
      g.filter = `blur(${blur}px)`;
      const fill = g.createRadialGradient(cx, cy, 0, cx, cy, reach);
      pool.light.forEach((v, i) => fill.addColorStop(+(i / (LAMP.stops - 1)).toFixed(4), lightRgba(rgb, alpha * v)));
      g.fillStyle = fill;
      path(quad); g.fill();
    }
    g.filter = "none";
    g.globalCompositeOperation = "destination-out";
    g.fillStyle = tint("black");
    for (const sheet of this.sheetList) { path(sheetCorners(sheet)); g.fill(); }
    g.restore();
    this.castBox = box;
  }

  placeShade() {
    const most = POINTER_SHADOW.mostShare * Math.min(...this.size), ground = this.grabbed ? POINTER_GROUND : pointerAt(this.depth);
    const by = this.caster();
    const strength = this.shadeStrength(by, ground.height, most);
    let on = GAUNTLET_SHADOW_SWITCH.on && !!this.at && strength >= 0.01, look = "";
    if (on) {
      const drop = this.grabbed ? SHADOW_DROP / 3 : SHADOW_DROP;
      const spot = (height) => {
        const s = castShadow(by.light, height, most), [x, y] = turned(s.x, s.y, this.rot);
        return [this.at[0] + x, this.at[1] + y + drop];
      };
      const edge = (height) => shadowEdge(by.light, pointerYards(height), height, most, this.perYard);
      let [x, y] = spot(ground.height), { alpha, scale } = ground, sigma = edge(ground.height);
      const k = this.easePaper(this.grabbed ? null : this.sheetUnder(ground.height, [x, y], spot));
      if (k > 0) {
        const above = this.overSheet(this.paper.sheet, ground.height), [px, py] = spot(above.height), mix = (a, b) => a + (b - a) * k;
        [x, y, alpha, scale, sigma] = [mix(x, px), mix(y, py), mix(alpha, above.alpha), mix(scale, above.scale), mix(sigma, edge(above.height))];
      }
      const stretch = +castShadow(by.light, ground.height, most).stretch.toFixed(2), [lx, ly] = turned(...by.light.dir, this.rot);
      const way = +Math.atan2(-ly, -lx).toFixed(3);
      look = `${Math.round(x)} ${Math.round(y)} ${+(alpha * strength).toFixed(2)} ${+scale.toFixed(3)} ${by.moon ? "moon" : "sun"} ${stretch} ${way} ${+(sigma / scale).toFixed(2)}`;
      this.outline();
      if (this.ground && !(k > 0)) [on, look] = [false, "ground"];
    } else Object.assign(this.paper, { t: 0, to: 0, sheet: null, fresh: true });
    if (look === this.shown.shade) return;
    this.shown.shade = look;
    this.shade.hidden = !on;
    if (!on) return;
    const [x, y, alpha, scale, caster, stretch, way, blur] = look.split(" ");
    const long = ` scale(${+(scale * stretch).toFixed(3)}, ${scale})`;
    const size = stretch === "1" ? (scale === "1" ? "" : ` scale(${scale})`) : ` rotate(${way}rad)${long} rotate(${-way}rad)`;
    this.shade.style.transform = `translate(${x}px, ${y}px)${size}`;
    this.shade.style.opacity = alpha;
    this.shade.style.filter = `blur(${blur}px)`;
    this.shade.style.color = caster === "moon" ? lightRgba(moonShade(), 1) : "";
  }

  caster() {
    const by = casterAt(this.hour(), this.nightOn);
    return { ...by, share: this.minutes() != null ? by.share * (1 - this.under) : 0 };
  }

  shadeStrength(by, height, most) {
    if (!(most > 0)) return 0;
    return castShadow(by.light, by.moon ? POINTER_SHADOW.height : height, most).strength * by.share;
  }

  overSheet(sheet, height) {
    return pointerAbove(height - this.sheetHeight * sheet.fade);
  }

  sheetUnder(height, ground, spot) {
    for (const sheet of this.sheetList) {
      if (onSheet(sheet, ground) || onSheet(sheet, spot(this.overSheet(sheet, height).height))) return sheet;
    }
    return null;
  }

  easePaper(sheet) {
    const p = this.paper, now = this.now(), to = sheet ? 1 : 0;
    if (p.t !== p.to) p.t = p.t < p.to ? Math.min(p.to, p.t + (now - p.time) / SHEET_SNAP) : Math.max(p.to, p.t - (now - p.time) / SHEET_SNAP);
    Object.assign(p, { to, time: now });
    if (sheet) p.sheet = sheet;
    if (p.fresh) Object.assign(p, { t: to, fresh: false });
    if (p.t === 0 && !sheet) p.sheet = null;
    if (p.t !== p.to && !p.asked) {
      p.asked = true;
      this.frame(() => { p.asked = false; this.placeShade(); });
    }
    return lightEase(p.t);
  }

  outline() {
    const kind = this.grabbed ? "held" : "open", look = `${kind} ${this.shown.cursor}`;
    if (look === this.shown.outline) return;
    this.shown.outline = look;
    const k = GAUNTLET.shadeWidth / GAUNTLET.size[0], [w, h] = GAUNTLET.size.map((v) => +(v * k).toFixed(1));
    const [x, y] = GAUNTLET[kind].hot.map((v) => +(v * k).toFixed(1));
    Object.assign(this.shade.style, { width: `${w}px`, height: `${h}px`, left: `${-x}px`, top: `${-y}px`, transformOrigin: `${x}px ${y}px`,
      maskImage: `url("${gauntletPicture(kind, this.shown.cursor)}")` });
  }

  showYou(x, y, key, paint, dpr = 1) {
    this.youArgs = [x, y, key, paint, dpr];
    const fire = this.fire ? ` fire ${Math.floor(this.now() / FIRE_GLOW.step)}` : "";
    this.youOver.show(x, y, key + fire, paint, dpr);
  }

  campfire(on) {
    on = !!on;
    if (on === !!this.fire) return;
    this.fire = on;
    if (this.youArgs) this.showYou(...this.youArgs);
    if (on) {
      const loop = (this.fireLoop = (this.fireLoop || 0) + 1);
      const tick = () => {
        if (!this.fire || loop !== this.fireLoop) return;
        if (this.youArgs && !this.youOver.el.hidden) this.showYou(...this.youArgs);
        this.frame(tick);
      };
      this.frame(tick);
    }
  }

  hideYou() {
    this.youOver.hide();
  }
}

class OverLight {
  constructor(el) {
    Object.assign(this, { el, look: null, at: null });
  }

  show(x, y, key, paint, dpr = 1) {
    const el = this.el, [ix, iy] = [Math.floor(x), Math.floor(y)], [fx, fy] = [+(x - ix).toFixed(1), +(y - iy).toFixed(1)];
    const look = `${key} ${fx} ${fy} ${dpr}`;
    if (look !== this.look) {
      this.look = look;
      const size = Math.round(YOU_BOX * dpr);
      if (el.width !== size) { el.width = size; el.height = size; }
      const g = el.getContext("2d");
      g.setTransform(dpr, 0, 0, dpr, 0, 0);
      g.clearRect(0, 0, YOU_BOX, YOU_BOX);
      paint(g, YOU_BOX / 2 + fx, YOU_BOX / 2 + fy);
    }
    const move = `translate(${ix - YOU_BOX / 2}px, ${iy - YOU_BOX / 2}px)`;
    if (move !== this.at) el.style.transform = this.at = move;
    if (el.hidden) el.hidden = false;
  }

  hide() {
    if (this.el && !this.el.hidden) this.el.hidden = true;
  }
}

if (typeof module === "object") {
  module.exports = { ARROW_SHAPE, FIRE_GLOW, inArrow, firePoints, paintFire, SUN, TINTS, ARROW_SHADOW, POINTER_SHADOW, LAMP, LANTERN, MOON, VIGNETTE, YOU_BOX, GAUNTLET, gauntletLight,
    gauntletPicture, gauntletCursor, GAUNTLET_FADE, GAUNTLET_GROW, gauntletGrowth, gauntletMix, blendMix, mixKey, mixBox, mixCursor, gauntletBlend, dayHour, sunAt, moonAt, castShadow, SUN_SHADOW, skyAt, GAME_SUN, SUN_LOW, SUN_HIGH, sunUp,
    shadowAt, casterAt, moonlightAt, sunHueAt, nightAt, vignetteOf, vignetteMaskOf, pointerAt, pointerDepth,
    turned, lampAt, tintAt, skyOf, lightNeutral, TINTS_DAY, GAUNTLET_SHADOW, sunColourAt, filterOf, overlayOf, lampGlowOf, arrowLook, paintArrow, arrowPath, ARROW_GLOW, GLOW_AWAY, paintArrowGlow, ARROW_LIGHT, arrowLightGoal, arrowLightSettled, arrowLightStep, arrowLit, lanternAtRest, lanternStep, pointerAbove, onSheet, SHEET_SNAP,
    LANTERN_SHADOW, lanternQuad, lanternReaches, sheetCorners, MapLight, OverLight, lightEase, SHADOW_FULL_AT, moonShade,
    SKY_DISC, EDGE_SIGMA, penumbra, lanternPenumbra, edgeSigma, shadowEdge, lanternEdge, pointerYards,
    LAMP_CONE, LAMP_EASE, GAUNTLET_SHADOW_SWITCH, lanternClimb, lanternHeight, poolRadius, lanternBright, coneRim, lanternLight, lanternGlow, lanternTilt, lanternPool };
}
