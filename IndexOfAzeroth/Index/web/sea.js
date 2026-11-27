// The Index of Azeroth. Copyright 2026 Index Case <indexofazeroth@pm.me>. PolyForm Strict 1.0.0, see LICENSE.md.
"use strict";

const SEA = { side: 129, version: 3, header: 8, far: 9, scale: 1, fps: 30, open: 2000, cut: 40, travel: [0.3, 30], force: 3.5, eye: 1.1, eyeShift: [-0.24, -0.12],
  fft: { n: 128, sizes: [251.3, 37.7, 7.13], turns: [0, 1.13, 2.41], offsets: [[0, 0], [0.37, 0.71], [0.83, 0.19]], shortest: [9.4, 1.78, 0.25] },
  g: 9.81 / 0.9144, choppy: 1.15, groundPx: 1024, groundUntil: 1.2 };

function decodeSea(buf) {
  if (!buf || buf.byteLength < SEA.header) return null;
  const v = new DataView(buf), n = v.getUint16(0, true), version = v.getUint16(2, true);
  if (version !== SEA.version || n !== SEA.side || buf.byteLength !== SEA.header + n * n * 8) return null;
  return { n, fours: new Uint16Array(buf.slice(SEA.header)) };
}

const INLAND = { version: 7, layers: 10, swell: { cascade: 1, slow: 0.4, stretch: 1.6, green: 0.7, soft: 0.002, glass: 0.2 }, dry: 0xd640,
  run: 2.5, narrow: 5, bank: 0.35, g: 10.7, reach: 20, rush: 6, cycle: 4, hand: 60, current: 1.1, chop: { most: 0.6, speeds: [1, 8.5] },
  falls: { stand: 12, across: 0.5, still: 0.5, held: 0.97, rise: [1.12, 0.75], crumb: 0.3, eddy: 5, quick: 1.5, fleck: 0.45, flecks: 1.6,
    cell: 10, streak: 0.6, most: 0.4, life: 4, bend: { by: 8, swell: 1.4 }, dash: { cell: 7, long: 0.9, wide: 0.09, turn: 0.25, keep: 0.35, most: 0.5 },
    air: 0.75, reach: [1.2, 0.8], marble: 0.55 },
  mouth: { reach: 45, cell: 24, swirl: 0.8, silt: [0.42, 0.4, 0.28], land: 0.6, up: 10, bank: 14, tint: 0.8,
    day: { hand: 220, silt: 0.35, wave: 1.6, top: 0.3, wide: 8, white: 0.7 },
    bands: { every: 3.5, speed: 5, low: 0.55, hand: 120, around: 12, wide: [36, 39.5] } },
  colour: { bed: [0.24, 0.21, 0.15], wet: 0.65, tint: 0.25, shallow: 16, clear: [0.15, 0.29, 0.21], deep: [8, 40], dark: [0.06, 0.12, 0.13], soft: [12, 24], ring: [0.6, 0.3],
    near: 0.85, opaque: 0.85, edge: 0.8, waterline: 0.5, speeds: [0.8, 5], zone: 0.15 } };

const FOAM = { warp: 0.75, gain: 0.5, sd: 0.0885, edge: 0.45, thin: 0.5, thick: 2, whole: 0.85, floor: 0.3,
  crumb: { size: 1.8, mean: 0.43, sd: 0.1896 } };
const STILL_SD = 0.4557;
const foamSums = (f = FOAM) => [0, 1].map((sq) => Array.from({ length: 10 }, (_, k) => (0.5 * f.gain ** k) ** (sq + 1)).reduce((a, b) => a + b, 0));

const inlandRun = (wide, edge = Infinity, drop = 0, fall = 0, I = INLAND) => {
  const side = Math.min(Math.max(edge / Math.max(wide, 1), 0), 1), bank = I.bank + (1 - I.bank) * side * side * (3 - 2 * side);
  const h = Math.max(fall, 0) * I.reach + Math.abs(drop);
  return ((I.run * I.narrow) / Math.max(wide, I.narrow)) * bank + Math.min(Math.sqrt(2 * I.g * h), I.rush);
};

const inlandChop = (speed, c = INLAND.chop) => c.most * smoothHour(c.speeds[0], c.speeds[1], speed);

const inlandChurn = (speed, F = INLAND.falls) => {
  const top = Math.log2(F.life / F.quick), l = Math.min(Math.max(Math.log2((F.life * Math.max(speed, 0)) / F.eddy), 0), top);
  const i = Math.floor(l), k = l - i;
  return { cycles: [F.life / 2 ** i, F.life / 2 ** (i + 1)], w: [1 - k, k] };
};

function decodeInland(buf) {
  if (!buf || buf.byteLength < SEA.header) return null;
  const v = new DataView(buf), n = v.getUint16(0, true), version = v.getUint16(2, true), L = INLAND.layers;
  if (version !== INLAND.version || n !== SEA.side || buf.byteLength !== SEA.header + n * n * L * 2) return null;
  const all = new Uint16Array(buf.slice(SEA.header)), fours = new Uint16Array(n * n * 4), more = new Uint16Array(n * n * 4);
  const white = new Uint16Array(n * n * 4);
  for (let i = 0; i < n * n; i++) {
    fours.set(all.subarray(i * L, i * L + 4), i * 4);
    more.set(all.subarray(i * L + 4, i * L + 8), i * 4);
    white.set(all.subarray(i * L + 8, i * L + 10), i * 4);
  }
  return { n, fours, more, white };
}

const SEA_STORES = { sea: { url: "/api/seafield", index: "index", files: "files", decode: decodeSea },
  inland: { url: "/api/inlandfield", index: "inlandIndex", files: "inlandFiles", decode: decodeInland } };

function halfToFloat(h) {
  const s = h & 0x8000 ? -1 : 1, e = (h >> 10) & 0x1f, f = h & 0x3ff;
  if (e === 0) return s * f * 2 ** -24;
  if (e === 31) return f ? NaN : s * Infinity;
  return s * (1 + f / 1024) * 2 ** (e - 15);
}

const seaBox = (corners, tileYards) => {
  const cols = corners.map((p) => Math.floor(32 - p.w / tileYards)), rows = corners.map((p) => Math.floor(32 - p.n / tileYards));
  return [Math.max(0, Math.min(...cols)), Math.max(0, Math.min(...rows)), Math.min(63, Math.max(...cols)), Math.min(63, Math.max(...rows))];
};

function seaKind(has, rendered, loaded) {
  if (loaded) return 1;
  if (has) return 0;
  return rendered ? 0 : 2;
}

const beaufortWind = (force) => (0.836 * Math.max(force, 0) ** 1.5) / 0.9144;

function seaBlocked(against, speed, force) {
  const ease = (a, b, x) => { const k = Math.min(1, Math.max(0, (x - a) / (b - a))); return k * k * (3 - 2 * k); };
  const q = Math.max(beaufortWind(force) / 0.877 / 4, 1e-3);
  return ease(0.3, 1, against / q) * (1 - ease(1.3, 2.6, speed / q)) * ease(0.5, 2.5, force);
}

const SEA_WEATHER = { at: [0, 0.05, 0.2, 0.3, 0.5, 0.7, 0.9, 1], mean: [SEA.force, SEA.force, SEA.force, SEA.force, 4.5, 5.5, 7, 10],
  spread: [0, 0.3, 0.8, 2, 3, 2, 1, 0.5], front: 2600, period: 64, small: 0.6, drift: 1400, slant: 0.9, second: 0.55, life: 5 };

function seaTable(at, values, x) {
  if (!(x > at[0])) return values[0];
  for (let i = 1; i < at.length; i++) {
    if (x <= at[i]) return values[i - 1] + ((values[i] - values[i - 1]) * (x - at[i - 1])) / (at[i] - at[i - 1]);
  }
  return values[values.length - 1];
}

const seaWeather = (a, n) => Math.min(12, Math.max(0, seaTable(SEA_WEATHER.at, SEA_WEATHER.mean, a) + seaTable(SEA_WEATHER.at, SEA_WEATHER.spread, a) * n));
const seaForce = (red, green, n) => seaWeather(red, n) * (1 - Math.min(1, Math.max(0, green)));
const seaStorm = (red, fromEye = Infinity, m = MAELSTROM) => {
  const t = Math.min(1, Math.max(0, (fromEye - m.radius) / (m.radius * (m.storm - 1))));
  return Math.max(Math.min(1, Math.max(0, red)), 1 - t * t * (3 - 2 * t));
};

function worldPlace(onWorld) {
  const [oa, od] = onWorld(0, 0), [a1] = onWorld(0, 1), [, d1] = onWorld(1, 0);
  return [a1 - oa, oa, d1 - od, od];
}
const frameAt = ([ka, oa, kd, od], across, down) => ({ n: (down - od) / kd, w: (across - oa) / ka });

function seaFronts(hours, w = SEA_WEATHER) {
  const P = w.front * w.period;
  return [0, 0.5].map((half, k) => {
    const life = hours / w.life + half, cycle = Math.floor(life), share = life - cycle, rand = seeded(1197 + 2 * cycle + k);
    return { weight: 1 - Math.abs(2 * share - 1), along: [w.drift * share * w.life, w.drift * share * w.life * w.second],
      at: [rand() * P, rand() * P, rand() * P * w.small, rand() * P * w.small] };
  });
}

const SEA_WIND = { pattern: [-0.24, -0.97].map((v) => v / Math.hypot(0.24, 0.97)), cell: 1200, blend: 0.35, fetch: [1800, 450, 90] };

function seaCircle([col, row, radius, spin], [kn, kw, on, ow], tileYards) {
  return [((32 - row) * tileYards - on) / kn, ((32 - col) * tileYards - ow) / kw, (radius * tileYards) / Math.sqrt(Math.abs(kn * kw)), spin];
}
function seaWind(p, circles) {
  let n = 0, w = 0;
  for (const [cn, cw, R, spin] of circles) {
    const dn = p.n - cn, dw = p.w - cw, r = Math.hypot(dn, dw);
    if (!(R > 0) || !(r > 0)) continue;
    const speed = (r < R ? r / R : R / r) / r;
    n += spin * dw * speed;
    w -= spin * dn * speed;
  }
  const L = Math.hypot(n, w);
  return L > 1e-9 ? [n / L, w / L] : [...SEA_WIND.pattern];
}
function seaFetch(dist, way, away) {
  const off = way[0] * away[0] + way[1] * away[1];
  if (!(off > 0)) return SEA_WIND.fetch.map(() => 1);
  const X = Math.max(dist, 0) / off;
  return SEA_WIND.fetch.map((f) => Math.min(1, Math.sqrt(X / f)));
}

const SEA_GROW = { down: [3, 2, 1.2], up: [1.2, 0.8, 0.5] };
const inlandSwell = (s = INLAND.swell) => seaWeights(seaForce(0, s.green, 0))[s.cascade];
const seaWeights = (force) => SEA_GROW.down.map((p, c) => {
  const k = Math.max(force, 0) / SEA.force;
  return k ** (k > 1 ? SEA_GROW.up[c] : p);
});

const seaSun = (terrain, cloud, share) => 1 - Math.max(terrain, cloud * share);

const SEA_SKY = { horizon: [0.86, 0.9, 0.94], zenith: [0.36, 0.55, 0.82], k: 24, most: 0.45,
  low: [0.61, 0.25], sparkle: 0.02, fade: [4.1, 15.5], sunward: 0, sunwardPow: 6 };

const MAELSTROM = { at: [500 / 1002, 339 / 668], radius: 4250, rim: 0.53, eye: 0.0116, throat: 0.105, spin: -1, turn: 90, pitch: 20,
  streak: { n: [16, 44, 120, 330], along: [1.3, 2.6, 5, 11], amp: [0.32, 0.32, 0.22, 0.14], life: 30 },
  eyeRgb: [0.01, 0.028, 0.075], lace: 45, renew: 8, handOver: 0.8, unwind: 0.5,
  shear: 1.32, shearCore: 0.053, damp: 2, omega: 0.25, block: 0.45, keep: 0.35, churn: 18, fps: 6, storm: 1.5 };

function swirlShare(r, m = MAELSTROM) {
  const R = m.radius, R1 = m.rim * R, u = Math.min(1, Math.max(0, (r - R1) / (R - R1)));
  return { share: 1 - u * u * (3 - 2 * u), rise: u > 0 && u < 1 ? (-6 * u * (1 - u)) / (R - R1) : 0 };
}
function swirlFlow(r, m = MAELSTROM) {
  const core = m.eye * m.radius, throat = m.throat * m.radius, gamma = (2 * Math.PI * throat * throat) / m.turn;
  const along = (r >= core ? gamma / Math.max(r, 1e-9) : (gamma * r) / (core * core)) * swirlShare(r, m).share;
  return { along, in: along * Math.tan((m.pitch * Math.PI) / 180) };
}
function swirlAt(dn, dw, m = MAELSTROM) {
  const r = Math.hypot(dn, dw), k = Math.tan((m.pitch * Math.PI) / 180), rr = Math.max(r, 1e-6);
  const core = m.eye * m.radius, throat = m.throat * m.radius, gamma = (2 * Math.PI * throat * throat) / m.turn;
  const tau = rr >= core ? (rr * rr) / (2 * k * gamma) : (core * core) / (2 * k * gamma) + (Math.log(rr / core) * core * core) / (k * gamma);
  return { r, psi: Math.atan2(dn, -dw) + (m.spin * Math.log(rr)) / k, tau };
}
function swirlBack(dn, dw, back, m = MAELSTROM) {
  const s = swirlAt(dn, dw, m), k = Math.tan((m.pitch * Math.PI) / 180), core = m.eye * m.radius;
  const gamma = (2 * Math.PI * (m.throat * m.radius) ** 2) / m.turn, rr = Math.max(s.r, core);
  const r = Math.sqrt(rr * rr + 2 * k * gamma * back), th = s.psi - (m.spin * Math.log(r)) / k;
  return { n: r * Math.sin(th), w: -r * Math.cos(th) };
}
function laceThin(m = MAELSTROM) {
  const shear = m.unwind / Math.tan((m.pitch * Math.PI) / 180);
  return Math.sqrt((shear * shear) / 4 + 1) - shear / 2;
}
function swirlDepth(m = MAELSTROM, g = SEA.g) {
  const C = (2 * Math.PI * (m.throat * m.radius) ** 2) / m.turn, core = m.eye * m.radius;
  return (C * C) / (2 * g * core * core);
}
function swirlFunnel(r, m = MAELSTROM) {
  const R = m.radius, x = Math.min(r / R, 1), core = m.eye * R, D = swirlDepth(m);
  const q = r / core, sink = 1 / (1 + q * q), win = (1 - x * x) ** 2, down = D * sink;
  const slope = ((2 * D * q) / core) * sink * sink * win + (down * 4 * x * (1 - x * x)) / R;
  return { h: -down * win, slope };
}
function swirlHeldParts(m = MAELSTROM) {
  const R = m.radius, R1 = m.rim * R, L = R - R1, a = m.shearCore * R;
  const c3 = 2 / L ** 3, c2 = -3 / L ** 2 - (6 * R1) / L ** 3, c1 = (6 * R1) / L ** 2 + (6 * R1 * R1) / L ** 3, c0 = 1 - (3 * R1 * R1) / L ** 2 - (2 * R1 ** 3) / L ** 3;
  const A = c0 / a, B = c1 - a * c2 + a * a * c3 - A, k1 = c3 / 2, k0 = c2 - a * c3;
  const F = (x) => k1 * x * x + k0 * x + A * Math.log(x) + B * Math.log(x + a), G = (x) => Math.log(x / (x + a)) / a;
  return { c: [c0, c1, c2, c3], k1, k0, A, B, a, R, R1, FR: F(R), FR1: F(R1), G1: G(R1) };
}
function swirlHeld(r, m = MAELSTROM, h = swirlHeldParts(m)) {
  const S = m.shear * m.radius, x = Math.max(r, 1);
  if (x >= h.R) return { turn: 0, rise: 0 };
  const F = (y) => h.k1 * y * y + h.k0 * y + h.A * Math.log(y) + h.B * Math.log(y + h.a), G = (y) => Math.log(y / (y + h.a)) / h.a;
  const turn = S * (x >= h.R1 ? h.FR - F(x) : h.FR - h.FR1 + h.G1 - G(x));
  return { turn, rise: (-S * swirlShare(x, m).share) / (x + h.a) };
}
function swirlBend(r, tau = 0, m = MAELSTROM) {
  const R1 = m.radius, core = m.eye * R1, gamma = (2 * Math.PI * (m.throat * R1) ** 2) / m.turn, h = swirlHeldParts(m);
  const omegaAt = (x) => Math.min(gamma / Math.max(x * x, core * core), m.omega) * swirlShare(x, m).share;
  const turnAt = (x) => -m.spin * (swirlHeld(x, m, h).turn + omegaAt(Math.max(x, 1)) * tau);
  const rr = Math.max(r, 1), e = Math.max(0.25, 0.003 * rr), lo = Math.max(rr - e, 0.5), hi = rr + e;
  return { turn: turnAt(rr), shear: (rr * (turnAt(hi) - turnAt(lo))) / (hi - lo), omega: omegaAt(rr) };
}
const swirlEye = (spot, m = MAELSTROM) => frameAt(spot, ...m.at);

function seaPlace(toInst) {
  const o = toInst({ n: 0, w: 0 }), n = toInst({ n: 1, w: 0 }), w = toInst({ n: 0, w: 1 });
  return [n.n - o.n, w.w - o.w, o.n, o.w];
}
const placedAt = ([kn, kw, on, ow], p) => ({ n: kn * p.n + on, w: kw * p.w + ow });
function swirlShown(corners, eye, m = MAELSTROM) {
  const ns = corners.map((c) => c.n), ws = corners.map((c) => c.w);
  const dn = Math.max(Math.min(...ns) - eye.n, 0, eye.n - Math.max(...ns)), dw = Math.max(Math.min(...ws) - eye.w, 0, eye.w - Math.max(...ws));
  return Math.hypot(dn, dw) < m.radius;
}

function seeded(seed) {
  let a = seed >>> 0;
  return () => {
    a = (a + 0x6d2b79f5) >>> 0;
    let t = Math.imul(a ^ (a >>> 15), 1 | a);
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}
const normals = (rand) => {
  const r = Math.sqrt(-2 * Math.log(Math.max(rand(), 1e-12))), a = 2 * Math.PI * rand();
  return [r * Math.cos(a), r * Math.sin(a)];
};

function phillips(kx, kz, U, wind, g = SEA.g) {
  const k2 = kx * kx + kz * kz;
  if (!(k2 > 0) || !(U > 0)) return 0;
  const L = (U * U) / g, along = (kx * wind[0] + kz * wind[1]) / Math.sqrt(k2);
  return (Math.exp(-1 / (k2 * L * L)) / (k2 * k2)) * along * along * (along < 0 ? 0.07 : 1) * Math.exp(-k2 * 0.05 * 0.05);
}

const waveIndex = (i, n) => (i < n / 2 ? i : i - n);

function waveSpectra(force, wind = SEA_WIND.pattern, fft = SEA.fft, g = SEA.g) {
  const U = beaufortWind(force), n = fft.n, raw = [], sums = { var: 0 };
  fft.sizes.forEach((size, c) => {
    const a = fft.turns[c], w = [Math.cos(a) * wind[0] - Math.sin(a) * wind[1], Math.sin(a) * wind[0] + Math.cos(a) * wind[1]];
    const dk = (2 * Math.PI) / size, top = (2 * Math.PI) / fft.shortest[c], low = c > 0 ? (2 * Math.PI) / fft.shortest[c - 1] : 0;
    const p = new Float64Array(n * n);
    let slope = 0, own = 0, length = 0;
    const waves = [];
    for (let y = 0; y < n; y++) {
      for (let x = 0; x < n; x++) {
        const kx = waveIndex(x, n) * dk, kz = waveIndex(y, n) * dk, k = Math.hypot(kx, kz);
        if (!(k > low && k <= top)) continue;
        p[y * n + x] = phillips(kx, kz, U, w, g) * dk * dk;
        sums.var += p[y * n + x];
        own += p[y * n + x];
        slope += k * k * p[y * n + x];
        length += ((2 * Math.PI) / k) * p[y * n + x];
        if (p[y * n + x] > 0) waves.push(kx, kz, k * k * p[y * n + x]);
      }
    }
    const slopeWaves = Float64Array.from(waves);
    for (let i = 2; i < slopeWaves.length; i += 3) slopeWaves[i] /= slope;
    raw.push({ p, slope, own, length: own > 0 ? length / own : 0, slopeWaves });
  });
  const hs = (0.21 * U * U) / g, scale = sums.var > 0 ? (hs / 4) ** 2 / (2 * sums.var) : 0;
  const spectra = raw.map(({ p }, c) => {
    const rand = seeded(1160 + 7919 * c), h0 = new Float32Array(n * n * 2), out = new Float32Array(n * n * 4);
    for (let i = 0; i < n * n; i++) {
      const [a, b] = normals(rand), s = Math.sqrt((p[i] * scale) / 2);
      h0[2 * i] = a * s;
      h0[2 * i + 1] = b * s;
    }
    for (let y = 0; y < n; y++) {
      for (let x = 0; x < n; x++) {
        const i = y * n + x, j = ((n - y) % n) * n + ((n - x) % n);
        out.set([h0[2 * i], h0[2 * i + 1], h0[2 * j], -h0[2 * j + 1]], 4 * i);
      }
    }
    return out;
  });
  return { spectra, slopes: raw.map((r) => 2 * r.slope * scale), heights: raw.map((r) => Math.sqrt(2 * r.own * scale)),
    lengths: raw.map((r) => r.length), slopeWaves: raw.map((r) => r.slopeWaves), hs, rms: hs / 4, U, peak: (0.877 * g) / Math.max(U, 1e-3) };
}

const SEA_HELD_WIDE = [2, 4, 8, 16];
function seaHeld(slopeWaves, px, fft = SEA.fft) {
  return slopeWaves.map((waves, c) => {
    const texel = fft.sizes[c] / fft.n, B = Math.sqrt(Math.max(px * px - texel * texel, 0)), D = Math.max(px, texel);
    const sinc2 = (x) => (Math.abs(x) < 1e-6 ? 1 : (Math.sin(x) / x) ** 2), lin = (x) => 1 - (1 - Math.cos(x)) / 3;
    let held = 0;
    for (let i = 0; i < waves.length; i += 3) {
      const kx = waves[i], kz = waves[i + 1];
      held += waves[i + 2] * sinc2((kx * B) / 2) * sinc2((kz * B) / 2) * lin(kx * D) * lin(kz * D);
    }
    return held;
  });
}

const SEA_SWELL = { height: [0.9, 0.15], period: [7, 0.4], ways: [104, 124], periods: [1, 1.12], share: 0.7 };
const seaSwell = (force) => ({ height: SEA_SWELL.height[0] * Math.min(1, Math.max(force, 0) / SEA.force) ** 2 + SEA_SWELL.height[1] * Math.max(force, 0),
  period: SEA_SWELL.period[0] + SEA_SWELL.period[1] * SEA.force });
function seaSwellPhase(t, tau, shore, period, g = SEA.g, s = SEA_SWELL) {
  const ph = s.ways.map((deg, j) => {
    const T = period * s.periods[j], L = (g * T * T) / (2 * Math.PI), a = (deg * Math.PI) / 180;
    const along = Math.cos(a) * shore.n - Math.sin(a) * shore.w;
    return (2 * Math.PI * (t + tau - (along * T) / L)) / T;
  });
  const d = ph[1] - ph[0], r = s.share;
  return { cycles: (ph[0] + Math.atan2(r * Math.sin(d), 1 + r * Math.cos(d))) / (2 * Math.PI),
    sets: Math.sqrt(1 + r * r + 2 * r * Math.cos(d)) / (1 + r) };
}
const seaSwellAt = (red, green, n) => seaSwell(seaWeather(red, n)).height * (1 - Math.min(1, Math.max(0, green)));

const SEA_CREST = { cell: 60, lip: [0.1, 0.35], broken: [0.45, 0.8], white: 0.6 };
const seaCrestHeight = (r) => (2 / Math.sqrt(Math.PI)) * Math.sqrt(Math.log(1 / Math.min(Math.max(r, 1e-4), 1)));
const seaFormed = (depth, h) => (h > 0 ? Math.exp(-(Math.PI / 4) * ((SEA_CREST.lip[0] * Math.max(depth, 0)) / h) ** 2) : 0);

const SEA_FOLD = { depth: 0.78, ripple: 0.1, soft: 0.1, lace: 0.71, laceSoft: 0.15, laceBy: 5, laced: 0.25 };
const seaWhitecaps = (force) => Math.min(3.84e-6 * (0.836 * Math.max(force, 0) ** 1.5) ** 3.41, 0.6);
const normalDensity = (x) => Math.exp(-0.5 * x * x) / Math.sqrt(2 * Math.PI);
const normalCdf = (x) => {
  const z = Math.abs(x) / Math.SQRT2, t = 1 / (1 + 0.3275911 * z);
  const tail = 0.5 * ((((1.061405429 * t - 1.453152027) * t + 1.421413741) * t - 0.284496736) * t + 0.254829592) * t * Math.exp(-z * z);
  return x < 0 ? tail : 1 - tail;
};
function normalQuantile(p) {
  const q = Math.min(Math.max(p, 1e-6), 1 - 1e-6), x0 = 4.91 * (q ** 0.14 - (1 - q) ** 0.14);
  const x1 = x0 - (normalCdf(x0) - q) / normalDensity(x0);
  return x1 - (normalCdf(x1) - q) / normalDensity(x1);
}
function seaShoal(depth, weights, heights, lengths) {
  const d = Math.max(depth, 0), shoal = lengths.map((L) => Math.max((0.5 * L) / Math.max(d, 0.05), 1) ** 0.25);
  const hs = 4 * Math.hypot(...heights.map((h, c) => h * weights[c] * shoal[c])), limit = SEA_FOLD.depth * d;
  const ripple = Math.min(1, hs / SEA_FOLD.ripple), wet = ripple * ripple * (3 - 2 * ripple);
  return { bottom: shoal.map((s) => s * (hs > 0 ? Math.min(1, limit / hs) : 1)), hs, breaking: hs > 0 ? Math.exp(-2 * (limit / hs) ** 2) * wet : 0 };
}
const seaBreaking = (force, shoaled) => 1 - (1 - seaWhitecaps(force)) * (1 - shoaled);
function seaCapsRule(share, v, vf) {
  const sum = (a) => a.reduce((s, x) => s + x, 0), sx2 = sum(v) + SEA_FOLD.soft ** 2, sf2 = sum(vf) + SEA_FOLD.laceSoft ** 2;
  const cov = sum(v.map((x, c) => Math.sqrt(x * vf[c]))), L = SEA_FOLD.laced;
  const lacedAt = (z) => {
    const under = (-Math.sqrt(sx2) * normalDensity(z)) / Math.max(normalCdf(z), 1e-9);
    return L + (1 - L) * normalCdf((SEA_FOLD.lace - 1 - (cov * under) / sx2) / Math.sqrt(Math.max(sf2 - (cov * cov) / sx2, 1e-6)));
  };
  const all = L + (1 - L) * normalCdf((SEA_FOLD.lace - 1) / Math.sqrt(sf2));
  if (!(share > 0)) return { tau: -Infinity, lacedIn: all };
  const lacedIn = lacedAt(normalQuantile(Math.min(share / all, 0.98)));
  return { tau: 1 + Math.sqrt(sx2) * normalQuantile(Math.min(share / lacedIn, 0.98)), lacedIn };
}
function seaFold(J, Jf, tau, v, vf, held) {
  const lost = (a) => a.reduce((s, x, c) => s + x * (1 - held[c]), 0);
  const vl = lost(v) + SEA_FOLD.soft ** 2, fl = lost(vf) + SEA_FOLD.laceSoft ** 2, cl = lost(v.map((x, c) => Math.sqrt(x * vf[c])));
  const a = (tau - J) / Math.sqrt(vl), caps = normalCdf(a);
  const under = (-Math.sqrt(vl) * normalDensity(a)) / Math.max(caps, 1e-9);
  return { caps, lace: normalCdf((SEA_FOLD.lace - Jf - (cl * under) / vl) / Math.sqrt(Math.max(fl - (cl * cl) / vl, 1e-6))) };
}

const SEA_SPRAY = { cell: 5, steep: 0.35, force: [1.5, 6], life: 1.4, beat: 0.05, count: 10,
  drops: [[0.3, [0.13, 0.2], 0.8, 0.9], [0.3, [0.06, 0.09], 1.1, 0.75], [0.4, [0.025, 0.045], 1.5, 0.5]], grow: 1.5, jet: [1, 2],
  up: [55, 80], spread: 0.7, drift: 0.45 };

function sprayDrop(t, v0, way, tau, windV, g = SEA.g) {
  const k = 1 - Math.exp(-t / tau), fall = g * tau;
  const along = v0[0] * tau * k;
  const up = -fall * t + (v0[1] + fall) * tau * k;
  return { at: [way[0] * along + windV[0] * (t - tau * k), way[1] * along + windV[1] * (t - tau * k)], up };
}

const SEA_LIGHT = { moon: 0.9, moonGlint: 2, tinge: 0.5, axis: 3.5, lostShare: 0.36, merge: [0.77, 4], lowFrom: 0.7, lowMost: 2.5, core: [0.0018, 2], crisp: [2.6, 1.0],
  tips: [0.34, 6, 0.8], tipsOff: [[6.75, 7.667], [18.75, 24]], tipsEase: 8 / 60, moonTips: 2.8,
  moonCrisp: [4.4, 0.8] };
const seaLobeLight = (P, c) => (P <= 1 ? P ** c : 1 + c * Math.log(P));
function seaMerge(px, l = SEA_LIGHT) {
  const x = Math.min(1, Math.max(0, Math.log(px / l.merge[0]) / Math.log(l.merge[1])));
  return x * x * (3 - 2 * x);
}
const SEA_GLASS = { disc: 0.0047 };
const smoothHour = (a, b, x) => { const t = Math.min(1, Math.max(0, (x - a) / (b - a))); return t * t * (3 - 2 * t); };
const tipsByHour = (hour) => SEA_LIGHT.tipsOff.reduce((k, [from, to]) =>
  k * (1 - smoothHour(from - SEA_LIGHT.tipsEase, from, hour) * (1 - smoothHour(to, to + SEA_LIGHT.tipsEase, hour))), 1);
function tipsShare(light, hour) {
  if (light.moon) return SEA_LIGHT.moonTips * light.light;
  const start = SEA_LIGHT.tips[0], low = Math.min(1, Math.max(0, (start - light.sin) / start));
  return low * smoothHour(0, 0.017, light.sin) * tipsByHour(hour) * (light.sun ?? 1);
}
function seaLight(light, there = null, hour = 12) {
  const area = there || AREA_NONE;
  const own = oneLightRgb(1, light, 1, true, 1, oneLightAt(SUN.NOON), area, PLACED_NONE), m = nightMatrix(light.mix || 0);
  const blend = (rgb) => m.map((row) => row.reduce((s, v, k) => s + v * rgb[k], 0));
  const lit = blend(own);
  const hue = area.d.map((c) => 1 + (c - 1) * area.k), top = Math.max(...hue, 1e-3);
  const tinge = hue.map((c) => 1 - SEA_LIGHT.tinge * (1 - c / top));
  const bright = light.moon ? SEA_LIGHT.moon : 1;
  const up = light.moon ? sunAt(dayHour(hour + 12)).elevation * Math.PI / 180 : null;
  const [cos, sin] = up === null ? [light.cos, light.sin] : [Math.cos(up), Math.sin(up)];
  return { toward: [light.dir[0] * cos, light.dir[1] * cos, sin], elevation: light.elevation, lit, glint: tinge.map((c) => c * bright), glintK: light.light * (light.moon ? SEA_LIGHT.moonGlint : 1), night: light.night || 0,
    tips: tipsShare(light, hour), moon: !!light.moon };
}

const SEA_VERTEX = `#version 300 es
in vec2 p;
uniform vec2 size;
out vec2 sp;
void main() {
  sp = vec2((p.x + 1.0) * 0.5 * size.x, (1.0 - (p.y + 1.0) * 0.5) * size.y);
  gl_Position = vec4(p, 0.0, 1.0);
}`;

const SEA_SPECTRUM = `#version 300 es
precision highp float;
uniform sampler2D h0;
uniform float t, L, g;
uniform int n;
out vec4 frag;
vec2 cmul(vec2 a, vec2 b) { return vec2(a.x * b.x - a.y * b.y, a.x * b.y + a.y * b.x); }
void main() {
  ivec2 ij = ivec2(gl_FragCoord.xy);
  vec2 m = vec2(ij);
  m -= vec2(greaterThanEqual(ij, ivec2(n / 2))) * float(n);
  vec2 k = 6.2831853 * m / L;
  float kl = length(k);
  vec4 s = texelFetch(h0, ij, 0);
  float ph = mod(sqrt(g * kl) * t, 6.2831853);
  vec2 e = vec2(cos(ph), sin(ph));
  vec2 h = cmul(s.xy, vec2(e.x, -e.y)) + cmul(s.zw, e);
  vec2 dx = kl > 0.0 ? cmul(vec2(0.0, -k.x / kl), h) : vec2(0.0);
  vec2 dz = kl > 0.0 ? cmul(vec2(0.0, -k.y / kl), h) : vec2(0.0);
  frag = vec4(h + vec2(-dx.y, dx.x), dz);
}`;

const SEA_FFT = `#version 300 es
precision highp float;
uniform sampler2D src;
uniform int n, ns, horizontal;
out vec4 frag;
vec2 cmul(vec2 a, vec2 b) { return vec2(a.x * b.x - a.y * b.y, a.x * b.y + a.y * b.x); }
void main() {
  ivec2 ij = ivec2(gl_FragCoord.xy);
  int j = horizontal == 1 ? ij.x : ij.y;
  int r = j % (2 * ns), k = r % ns, i0 = (j / (2 * ns)) * ns + k, i1 = i0 + n / 2;
  ivec2 a0 = horizontal == 1 ? ivec2(i0, ij.y) : ivec2(ij.x, i0);
  ivec2 a1 = horizontal == 1 ? ivec2(i1, ij.y) : ivec2(ij.x, i1);
  vec4 a = texelFetch(src, a0, 0), b = texelFetch(src, a1, 0);
  float ang = 3.14159265 * float(k) / float(ns);
  vec2 w = vec2(cos(ang), sin(ang));
  vec4 bw = vec4(cmul(b.xy, w), cmul(b.zw, w));
  frag = r < ns ? a + bw : a - bw;
}`;

const SEA_SURFACE = `#version 300 es
precision highp float;
uniform sampler2D src;
uniform int n;
uniform float L;
layout(location = 0) out vec4 shape;
layout(location = 1) out vec4 slope;
vec4 at(ivec2 q) { return texelFetch(src, ivec2((q.x + n) % n, (q.y + n) % n), 0); }
void main() {
  ivec2 ij = ivec2(gl_FragCoord.xy);
  vec4 c = at(ij), xp = at(ij + ivec2(1, 0)), xm = at(ij - ivec2(1, 0)), zp = at(ij + ivec2(0, 1)), zm = at(ij - ivec2(0, 1));
  float d = 2.0 * L / float(n);
  shape = vec4(c.x, c.y, c.z, (zp.y - zm.y) / d);
  slope = vec4((xp.x - xm.x) / d, (zp.x - zm.x) / d, (xp.y - xm.y) / d, (zp.z - zm.z) / d);
}`;

const glslTable = (name, at, values) => `float ${name}(float x) {
  const float A[${at.length}] = float[](${at.map((v) => v.toFixed(4)).join(", ")});
  const float V[${at.length}] = float[](${values.map((v) => v.toFixed(4)).join(", ")});
  if (x <= A[0]) return V[0];
  for (int i = 1; i < ${at.length}; i++) if (x <= A[i]) return mix(V[i - 1], V[i], (x - A[i - 1]) / (A[i] - A[i - 1]));
  return V[${at.length - 1}];
}`;
const glslNum = (v) => (Number.isInteger(v) ? `${v}.0` : `${v}`);

const SEA_FRAGMENT = `#version 300 es
precision highp float;
precision highp int;
uniform sampler2D field;
uniform highp sampler2D tags;
uniform sampler2D shape0, shape1, shape2, slope0, slope1, slope2;
uniform sampler2D ground;
uniform sampler2D cover;
uniform sampler2D mask;
uniform sampler2D inland, lakeShape, lakeSlope;
uniform vec4 cascLake;
uniform vec2 offLake;
uniform ivec2 slots;
uniform int maskOn;
uniform vec4 spotAt;
uniform int parts;
uniform float insts[2];
uniform vec4 places[2], rects[2];
uniform ivec2 blocks[2];
uniform vec3 mael;
uniform int seaOn;
uniform vec4 frontAt[2];
uniform vec3 frontRun[2];
uniform float T, t, ypx, eyeUp, night, choppy, rms, hs, g, gustAt, swellT;
uniform float day;
uniform vec4 casc0, casc1, casc2;
uniform vec3 cascH, cascL;
uniform vec3 held;
uniform vec3 heldWide[${SEA_HELD_WIDE.length}];
uniform vec2 off0, off1, off2;
uniform mat3 world;
uniform vec3 toward, glintL, lit, glintRgb;
uniform vec2 centre, size;
uniform vec4 circles[2];
uniform float glintK;
uniform vec2 crispL, coreL, sunwardL;
uniform float axisL, lostL, lowMostL, mergeL;
uniform vec2 tipsL;
uniform float tipsK;
uniform vec3 skyLowL;
uniform vec2 skyFadeL;
uniform sampler2D sunShade, cloudShade;
uniform int shadeOn, cloudOn;
uniform float cloudShare;
in vec2 sp;
out vec4 frag;
float sunNow = 1.0;
float breakShare = 0.0;
const float SIDE = ${SEA.side}.0, OPEN = ${SEA.open}.0, FAR = ${SEA.far.toFixed(1)}, CUT = ${glslNum(SEA.cut)},
  FORCE = ${glslNum(SEA.force)}, TAU = 6.2831853, GLASS = ${((SEA_GLASS.disc / 2) ** 2).toExponential(4)},
  CORE = ${glslNum(MAELSTROM.eye * MAELSTROM.radius)}, THROAT = ${glslNum(MAELSTROM.throat * MAELSTROM.radius)},
  SPIN = ${glslNum(MAELSTROM.spin)}, PK = ${Math.tan((MAELSTROM.pitch * Math.PI) / 180).toFixed(6)}, STREAK_LIFE = ${glslNum(MAELSTROM.streak.life)},
  DEEP = ${swirlDepth().toFixed(3)}, GAM = ${((2 * Math.PI * (MAELSTROM.throat * MAELSTROM.radius) ** 2) / MAELSTROM.turn).toFixed(3)},
  RAD = ${glslNum(MAELSTROM.radius)}, RIM_R = ${glslNum(MAELSTROM.rim * MAELSTROM.radius)},
  SHEAR = ${glslNum(MAELSTROM.shear * MAELSTROM.radius)}, SHEAR_A = ${glslNum(MAELSTROM.shearCore * MAELSTROM.radius)},
  DAMP = ${glslNum(MAELSTROM.damp)}, OMEGA = ${glslNum(MAELSTROM.omega)}, BLOCK = ${glslNum(MAELSTROM.block)},
  KEEP = ${glslNum(MAELSTROM.keep)}, CHURN_V = ${glslNum(MAELSTROM.churn)},
  FADE_T = ${glslNum(MAELSTROM.handOver)},
  FIELD_SD = ${glslNum(FOAM.sd)},
  LACE = ${glslNum(MAELSTROM.lace)}, RENEW = ${glslNum(MAELSTROM.renew)},
  UNWIND = ${(MAELSTROM.unwind * MAELSTROM.spin / Math.tan((MAELSTROM.pitch * Math.PI) / 180)).toFixed(6)}, THIN = ${laceThin().toFixed(6)};
  const vec4 STREAK_N = vec4(${MAELSTROM.streak.n.map(glslNum).join(", ")}), STREAK_M = vec4(${MAELSTROM.streak.along.map(glslNum).join(", ")}),
    STREAK_A = vec4(${MAELSTROM.streak.amp.map(glslNum).join(", ")}),
    HELD_F = vec4(${((h) => [h.k1, h.k0, h.A, h.B].map((v) => v.toExponential(9)).join(", "))(swirlHeldParts())});
  const vec2 HELD_K = vec2(${((h) => [h.FR, h.FR - h.FR1 + h.G1].map((v) => v.toExponential(9)).join(", "))(swirlHeldParts())});

vec2 spotOf(vec2 p) {
  return vec2(spotAt.x * p.y + spotAt.y, spotAt.z * p.x + spotAt.w);
}
int partAt(vec2 p) {
  if (parts < 2) return 0;
  vec2 uv = spotOf(p);
  vec4 a = rects[0], b = rects[1];
  return length(max(max(b.xy - uv, uv - b.zw), 0.0)) < length(max(max(a.xy - uv, uv - a.zw), 0.0)) ? 1 : 0;
}
vec2 placed(int i, vec2 p) {
  vec4 k = places[i];
  return vec2(k.x * p.x + k.z, k.y * p.y + k.w);
}
float wrapWhole(float i, float n) { return i - n * floor((i + 0.5) / n); }
vec2 wrapWhole(vec2 i, float n) { return i - n * floor((i + 0.5) / n); }
ivec2 slotOf(int i, float col, float row) {
  return ivec2(blocks[i].x + int(wrapWhole(col, float(blocks[i].y))), int(wrapWhole(row, float(slots.y))));
}

struct Tile { ivec2 s; vec2 f; float own; bool inside; vec2 points; };
Tile tileAt(vec2 p) {
  int i = partAt(p);
  vec2 q = placed(i, p);
  float c = 32.0 - q.y / T, r = 32.0 - q.x / T, col = floor(c), row = floor(r);
  ivec2 s = slotOf(i, col, row);
  vec2 f = vec2(c - col, r - row);
  return Tile(s, f, (insts[i] * 64.0 + col) * 64.0 + row + 1.0, col >= 0.0 && row >= 0.0 && col <= 63.0 && row <= 63.0,
              (vec2(s) * SIDE + f * (SIDE - 1.0) + 0.5) / (vec2(slots) * SIDE));
}

vec4 fieldAt(vec2 p, out bool drawn) {
  Tile k = tileAt(p);
  drawn = true;
  if (!k.inside) return vec4(OPEN, 60.0, 2000.0, 0.0);
  vec4 tag = texelFetch(tags, k.s, 0);
  if (tag.y > 1.5 && tag.x == k.own) return vec4(OPEN, 60.0, 2000.0, 0.0);
  drawn = tag.y > 0.5 && tag.x == k.own;
  if (!drawn) return vec4(-OPEN, 0.0, 2000.0, 0.0);
  return textureLod(field, k.points, 0.0);
}
bool inlandAt(vec2 p, out vec4 a, out vec4 b, out vec4 c) {
  Tile k = tileAt(p);
  if (!k.inside || texelFetch(tags, k.s, 0).x != k.own) return false;
  a = textureLod(inland, vec2(k.points.x, k.points.y / 3.0), 0.0);
  b = textureLod(inland, vec2(k.points.x, (1.0 + k.points.y) / 3.0), 0.0);
  c = textureLod(inland, vec2(k.points.x, (2.0 + k.points.y) / 3.0), 0.0);
  return true;
}
bool inlandAt(vec2 p, out vec4 a, out vec4 b) { vec4 c; return inlandAt(p, a, b, c); }
vec4 fieldAt(vec2 p) { bool drawn; return fieldAt(p, drawn); }

float hash(vec2 q) {
  uvec2 u = uvec2(ivec2(q) + 65536);
  uint h = u.x * 1664525u + u.y * 1013904223u;
  h ^= h >> 16; h *= 0x7feb352du; h ^= h >> 15; h *= 0x846ca68bu; h ^= h >> 16;
  return float(h) / 4294967295.0;
}
float noise(vec2 x) {
  vec2 i = floor(x), f = fract(x), u = f * f * (3.0 - 2.0 * f);
  return mix(mix(hash(i), hash(i + vec2(1.0, 0.0)), u.x), mix(hash(i + vec2(0.0, 1.0)), hash(i + vec2(1.0, 1.0)), u.x), u.y);
}
float gnoise(vec2 x) {
  vec2 i = floor(x), f = fract(x), u = f * f * f * (f * (f * 6.0 - 15.0) + 10.0);
  vec4 a = TAU * vec4(hash(i), hash(i + vec2(1.0, 0.0)), hash(i + vec2(0.0, 1.0)), hash(i + vec2(1.0, 1.0)));
  vec4 g = cos(a) * vec4(f.x, f.x - 1.0, f.x, f.x - 1.0) + sin(a) * vec4(f.y, f.y, f.y - 1.0, f.y - 1.0);
  return 1.414 * mix(mix(g.x, g.y, u.x), mix(g.z, g.w, u.x), u.y);
}
float wrapped(vec2 x) {
  const float P = ${glslNum(SEA_WEATHER.period)};
  vec2 i = floor(x), f = fract(x), u = f * f * (3.0 - 2.0 * f);
  vec2 a = wrapWhole(i, P), b = wrapWhole(i + 1.0, P);
  return mix(mix(hash(a), hash(vec2(b.x, a.y)), u.x), mix(hash(vec2(a.x, b.y)), hash(b), u.x), u.y);
}
vec4 over(vec4 a, vec4 b) { return a + b * (1.0 - a.a); }

${glslTable("weatherMean", SEA_WEATHER.at, SEA_WEATHER.mean)}
${glslTable("weatherSpread", SEA_WEATHER.at, SEA_WEATHER.spread)}

vec2 paintAt(vec2 p) {
  return maskOn == 0 ? vec2(0.0) : clamp(textureLod(mask, clamp(spotOf(p), 0.0, 1.0), 0.0).rg, 0.0, 1.0);
}
vec2 windAt(vec2 p);
float forceOf(vec2 paint, vec2 p) {
  float n = 0.0;
  if (paint.r > 0.0) {
    const float F = ${glslNum(SEA_WEATHER.front)}, A = ${glslNum(SEA_WEATHER.slant)};
    vec2 way = windAt(p), way2 = mat2(cos(A), sin(A), -sin(A), cos(A)) * way;
    float got = 0.0, sum = 0.0;
    for (int k = 0; k < 2; k++) {
      vec4 at = frontAt[k];
      vec3 run = frontRun[k];
      float c = 0.65 * wrapped((p - way * run.x + at.xy) / F) + 0.35 * wrapped((p - way2 * run.y + at.zw) / (${glslNum(SEA_WEATHER.small)} * F) + 17.0);
      got += run.z * (c - 0.5);
      sum += run.z * run.z;
    }
    n = clamp(got / sqrt(max(sum, 1e-6)) * 3.2, -1.0, 1.0);
  }
  return clamp(weatherMean(paint.r) + weatherSpread(paint.r) * n, 0.0, 12.0) * (1.0 - paint.g);
}
float forceAt(vec2 p) { return forceOf(paintAt(p), p); }
vec3 weightsAt(float F) {
  float k = max(F, 0.0) / FORCE;
  return pow(vec3(k), k > 1.0 ? vec3(${SEA_GROW.up.map(glslNum).join(", ")}) : vec3(${SEA_GROW.down.map(glslNum).join(", ")}));
}
float swellAt(float F) {
  float f = max(F, 0.0);
  return ${glslNum(SEA_SWELL.height[0])} * pow(min(1.0, f / FORCE), 2.0) + ${glslNum(SEA_SWELL.height[1])} * f;
}
float swellOpen(vec2 paint, vec2 p) {
  return swellAt(forceOf(vec2(paint.r, 0.0), p));
}
float swellHere(vec2 paint, vec2 p) {
  return swellOpen(paint, p) * (1.0 - paint.g);
}
float normalDensity(float x) { return exp(-0.5 * x * x) * 0.39894228; }
float lobeLight(float P, float c) { return P <= 1.0 ? pow(P, c) : 1.0 + c * log(P); }
float normalCdf(float x) {
  float z = abs(x) * 0.70710678, k = 1.0 / (1.0 + 0.3275911 * z);
  float tail = 0.5 * ((((1.061405429 * k - 1.453152027) * k + 1.421413741) * k - 0.284496736) * k + 0.254829592) * k * exp(-z * z);
  return x < 0.0 ? tail : 1.0 - tail;
}
float normalQuantile(float p) {
  float q = clamp(p, 1e-6, 1.0 - 1e-6), x = 4.91 * (pow(q, 0.14) - pow(1.0 - q, 0.14));
  x -= (normalCdf(x) - q) / normalDensity(x);
  return x - (normalCdf(x) - q) / normalDensity(x);
}

vec2 windAt(vec2 p) {
  vec2 v = vec2(0.0);
  for (int i = 0; i < 2; i++) {
    vec4 c = circles[i];
    vec2 d = p - c.xy;
    float r = length(d);
    if (c.z <= 0.0 || r <= 0.0) continue;
    v += c.w * vec2(d.y, -d.x) * (r < c.z ? r / c.z : c.z / r) / r;
  }
  return length(v) > 1e-9 ? normalize(v) : vec2(${SEA_WIND.pattern.map((v) => v.toFixed(6)).join(", ")});
}
vec3 fetchAt(float dist, vec2 way, vec2 away) {
  float off = dot(way, away);
  if (off <= 0.0) return vec3(1.0);
  return min(vec3(1.0), sqrt(max(dist, 0.0) / off / vec3(${SEA_WIND.fetch.map(glslNum).join(", ")})));
}

struct Sea { float h; vec2 d; vec2 grad; mat2 m; };
struct Sea2 { Sea a; Sea b; };
void add(inout Sea2 s, sampler2D shp, sampler2D slp, vec4 c, vec2 off, vec2 p, vec2 w, float fp) {
  mat2 R = mat2(c.y, c.z, -c.z, c.y);
  vec2 u = (R * p) / c.x + off;
  float lod = log2(max(fp * float(textureSize(shp, 0).x) / c.x, 1e-6));
  vec4 a = textureLod(shp, u, lod), b = textureLod(slp, u, lod);
  mat2 Rt = transpose(R);
  float h = a.x;
  vec2 d = Rt * a.yz, grad = Rt * b.xy;
  mat2 m = Rt * mat2(b.z, a.w, a.w, b.w) * R;
  s.a = Sea(s.a.h + w.x * h, s.a.d + w.x * d, s.a.grad + w.x * grad, s.a.m + w.x * m);
  s.b = Sea(s.b.h + w.y * h, s.b.d + w.y * d, s.b.grad + w.y * grad, s.b.m + w.y * m);
}
Sea2 pattern(vec2 p, vec3 wa, vec3 wb, vec2 lake, float fp) {
  Sea z = Sea(0.0, vec2(0.0), vec2(0.0), mat2(0.0));
  Sea2 s = Sea2(z, z);
  add(s, shape0, slope0, casc0, off0, p, vec2(wa.x, wb.x), fp);
  add(s, shape1, slope1, casc1, off1, p, vec2(wa.y, wb.y), fp);
  add(s, shape2, slope2, casc2, off2, p, vec2(wa.z, wb.z), fp);
  if (lake.x > 0.0 || lake.y > 0.0) add(s, lakeShape, lakeSlope, cascLake, offLake, p, lake, fp);
  return s;
}
Sea turnedIn(Sea s, Sea o, float k, mat2 M) {
  mat2 Mt = transpose(M);
  return Sea(s.h + k * o.h, s.d + k * (Mt * o.d), s.grad + k * (Mt * o.grad), s.m + k * (Mt * o.m * M));
}
Sea2 surface(vec2 p, vec3 wa, vec3 wb, vec2 lake, float fp) {
  const float C = ${glslNum(SEA_WIND.cell)}, B = ${glslNum(SEA_WIND.blend / 2)};
  const vec2 P = vec2(${SEA_WIND.pattern.map((v) => v.toFixed(6)).join(", ")});
  vec2 x = p / C - 0.5, c0 = floor(x), b = smoothstep(0.5 - B, 0.5 + B, x - c0);
  int nx = b.x > 0.0 && b.x < 1.0 ? 2 : 1, ny = b.y > 0.0 && b.y < 1.0 ? 2 : 1;
  int i0 = b.x >= 1.0 ? 1 : 0, j0 = b.y >= 1.0 ? 1 : 0;
  Sea z = Sea(0.0, vec2(0.0), vec2(0.0), mat2(0.0));
  Sea2 s = Sea2(z, z);
  float k2 = 0.0;
  for (int n = 0; n < nx * ny; n++) {
    int i = i0 + n % nx, j = j0 + n / nx;
    float k = (i == 0 ? 1.0 - b.x : b.x) * (j == 0 ? 1.0 - b.y : b.y);
    vec2 c = (c0 + vec2(float(i), float(j)) + 0.5) * C, v = windAt(c);
    float co = dot(v, P), si = v.x * P.y - v.y * P.x;
    mat2 M = mat2(co, si, -si, co);
    Sea2 o = pattern(c + M * (p - c), wa, wb, lake, fp);
    s = Sea2(turnedIn(s.a, o.a, k, M), turnedIn(s.b, o.b, k, M));
    k2 += k * k;
  }
  float f = inversesqrt(k2);
  return Sea2(Sea(s.a.h * f, s.a.d * f, s.a.grad * f, s.a.m * f), Sea(s.b.h * f, s.b.d * f, s.b.grad * f, s.b.m * f));
}

vec4 groundAt(vec2 p) {
  Tile k = tileAt(p);
  vec4 tag = texelFetch(tags, k.s, 0);
  if (tag.z < 0.5 || tag.x != k.own) return vec4(0.0);
  return vec4(textureLod(ground, (vec2(k.s) + k.f) / vec2(slots), 0.0).rgb, 1.0);
}
float coverAt(vec2 p, vec4 f) {
  Tile k = tileAt(p);
  vec4 tag = texelFetch(tags, k.s, 0);
  if (tag.w < 0.5 || tag.x != k.own) return f.w;
  return textureLod(cover, (vec2(k.s) + k.f) / vec2(slots), 0.0).a;
}

vec3 swirlAt(vec2 d) {
  float r = length(d), rr = max(r, 1e-3);
  float tau = rr >= CORE ? rr * rr / (2.0 * PK * GAM) : CORE * CORE / (2.0 * PK * GAM) + log(rr / CORE) * CORE * CORE / (PK * GAM);
  return vec3(r, atan(d.x, -d.y) + SPIN * log(rr) / PK, tau);
}
vec2 flowShare(float r) {
  float u = clamp((r - RIM_R) / (RAD - RIM_R), 0.0, 1.0);
  return vec2(1.0 - u * u * (3.0 - 2.0 * u), -6.0 * u * (1.0 - u) * r / (RAD - RIM_R));
}
vec2 swirlBack(vec2 d, float back) {
  vec3 s = swirlAt(d);
  float r = sqrt(max(s.x, CORE) * max(s.x, CORE) + 2.0 * PK * GAM * back), th = s.y - SPIN * log(r) / PK;
  return vec2(r * sin(th), -r * cos(th));
}
float ringNoise(vec2 x, float n) {
  vec2 i = floor(x), f = fract(x), u = f * f * (3.0 - 2.0 * f);
  float a = wrapWhole(i.x, n), b = wrapWhole(i.x + 1.0, n);
  return mix(mix(hash(vec2(a, i.y)), hash(vec2(b, i.y)), u.x), mix(hash(vec2(a, i.y + 1.0)), hash(vec2(b, i.y + 1.0)), u.x), u.y);
}
struct Drift { vec4 at; vec2 w; vec4 ph; };
vec2 unwound(vec2 b, float k) {
  float a = k * UNWIND * log(max(length(b), CORE));
  return mat2(cos(a), sin(a), -sin(a), cos(a)) * b;
}
Drift driftAt(vec2 d) {
  float k0 = t / RENEW, k1 = k0 + 0.5, p0 = fract(k0), p1 = fract(k1), w0 = 1.0 - abs(2.0 * p0 - 1.0), sh = flowShare(length(d)).x * RENEW;
  return Drift(vec4(unwound(swirlBack(d, p0 * sh), 1.0) + 4000.0 * vec2(hash(vec2(floor(k0), 1.0)), hash(vec2(floor(k0), 2.0))),
                    unwound(swirlBack(d, p1 * sh), 1.0) + 4000.0 * vec2(hash(vec2(floor(k1), 1.0)), hash(vec2(floor(k1), 2.0)))),
               vec2(w0, 1.0 - w0), vec4(p0, p1, floor(k0), floor(k1)));
}
float threads(vec2 q, float c) {
  float n = 0.62 * noise(q) + 0.38 * noise(q * 2.13 + 5.3), gather = mix(0.6, 1.4, noise(q * 0.45 + 3.1));
  return smoothstep(c * gather + 0.025, c * gather - 0.025, abs(2.0 * n - 1.0));
}
float laceAt(Drift dr, float cell, float seed, float px, float cover) {
  float sharp = smoothstep(1.5, 4.0, cell * THIN / px);
  if (sharp <= 0.0) return cover;
  float c = 0.32 * cover;
  float f = dr.w.x * threads(dr.at.xy / cell + seed, c) + dr.w.y * threads(dr.at.zw / cell + seed, c);
  return mix(cover, f, sharp);
}
vec3 funnelAt(vec2 d) {
  float R = mael.z, r = length(d), x = min(r / R, 1.0);
  float q = r / CORE, sink = 1.0 / (1.0 + q * q), win = (1.0 - x * x) * (1.0 - x * x), down = DEEP * sink;
  float slope = 2.0 * DEEP * q / CORE * sink * sink * win + down * 4.0 * x * (1.0 - x * x) / R;
  return vec3(-down * win, slope * d / max(r, 1e-3));
}
vec4 bendParts(float r) {
  float rr = max(r, 1.0), held = 0.0;
  vec2 sh = flowShare(rr);
  if (rr < RIM_R) held = SHEAR * (HELD_K.y - log(rr / (rr + SHEAR_A)) / SHEAR_A);
  else if (rr < RAD) held = SHEAR * (HELD_K.x - (HELD_F.x * rr * rr + HELD_F.y * rr + HELD_F.z * log(rr) + HELD_F.w * log(rr + SHEAR_A)));
  float heldRise = -SHEAR * sh.x / (rr + SHEAR_A);
  float spin = GAM / max(rr * rr, CORE * CORE), capped = step(OMEGA, spin), g = min(spin, OMEGA);
  float gRise = rr > CORE ? -2.0 * spin * (1.0 - capped) : 0.0;
  return vec4(held, g * sh.x, heldRise, gRise * sh.x + g * sh.y);
}
struct Bend { vec4 q; vec2 w; vec2 al; vec2 s; vec2 out_; vec2 round; float rho; float on; };
Bend bendAt(vec2 p) {
  vec2 d = p - mael.xy;
  float r = length(d);
  if (mael.z <= 0.0 || r >= RAD) return Bend(vec4(p, p), vec2(1.0, 0.0), vec2(0.0), vec2(0.0), vec2(1.0, 0.0), vec2(0.0, 1.0), 1.0, 0.0);
  float k0 = fract(t / RENEW), k1 = fract(t / RENEW + 0.5);
  float w0 = smoothstep(0.0, FADE_T, k0 * RENEW) * (1.0 - smoothstep(0.5 * RENEW, 0.5 * RENEW + FADE_T, k0 * RENEW));
  vec4 at = bendParts(r);
  vec2 tau = RENEW * vec2(k0, k1), al = -SPIN * (at.x + at.y * tau), s = -SPIN * (at.z + at.w * tau);
  vec2 q0 = mael.xy + mat2(cos(al.x), sin(al.x), -sin(al.x), cos(al.x)) * d;
  vec2 q1 = mael.xy + mat2(cos(al.y), sin(al.y), -sin(al.y), cos(al.y)) * d;
  vec2 o = d / max(r, 1e-3);
  float gap = length(q0 - q1);
  return Bend(vec4(q0, q1), vec2(w0, 1.0 - w0), al, s, o, vec2(-o.y, o.x), exp(-gap * gap / 36.0), 1.0);
}
vec3 heldBy(float wide) {
  const float WIDE[${SEA_HELD_WIDE.length}] = float[](${SEA_HELD_WIDE.map((v) => glslNum(Math.log2(v))).join(", ")});
  float x = log2(max(wide, 1.0)), at = 0.0;
  vec3 lo = held;
  for (int j = 0; j < ${SEA_HELD_WIDE.length}; j++) {
    if (x <= WIDE[j]) return mix(lo, heldWide[j], (x - at) / (WIDE[j] - at));
    lo = heldWide[j];
    at = WIDE[j];
  }
  return vec3(0.0);
}
float bendAmp(float s) { return inversesqrt(1.0 + s * s / (DAMP * DAMP)); }
float bendThin(float s) { return inversesqrt(1.0 + 0.5 * s * s + 0.5 * abs(s) * sqrt(s * s + 4.0)); }
struct Vortex { vec2 d; float x; float eye; vec3 fun; Drift dr; Bend b; };
Vortex vortexAt(vec2 p) {
  vec2 d = p - mael.xy;
  float r = length(d), x = mael.z > 0.0 ? r / mael.z : 2.0;
  Bend b = bendAt(p);
  if (x >= 1.0) return Vortex(d, x, 0.0, vec3(0.0), Drift(vec4(0.0), vec2(1.0, 0.0), vec4(0.0)), b);
  float q = r / CORE, a = atan(d.x, -d.y) - SPIN * OMEGA * t;
  float churn = 0.5 * ringNoise(vec2(a / TAU * 9.0, 2.0 * q), 9.0) + 0.3 * ringNoise(vec2(a / TAU * 23.0 + 5.0, 4.0 * q), 23.0)
    + 0.2 * ringNoise(vec2(a / TAU * 61.0 + 9.0, 9.0 * q), 61.0) - 0.5;
  return Vortex(d, x, smoothstep(0.3, 0.9, 1.0 / (1.0 + q * q) + 0.5 * churn), x < 1.0 ? funnelAt(d) : vec3(0.0), driftAt(d), b);
}
struct Waves { float h; float h0; vec2 grad; vec2 gGrad; float caps; float lace; };
Waves wavesAt(vec2 q, vec3 w, vec3 wf, vec3 wg, bool calmer, float fp, vec3 hd) {
  Sea2 at = surface(q, w, wf, vec2(0.0), fp);
  Sea s0 = at.a, fine = at.b;
  Sea2 moved = surface(q - choppy * s0.d, w, wg, vec2(0.0), fp);
  Sea s = moved.a;
  vec2 gGrad = calmer ? moved.b.grad : s.grad;
  const float SOFT = ${glslNum(SEA_FOLD.soft)}, LS = ${glslNum(SEA_FOLD.laceSoft)}, LT = ${glslNum(SEA_FOLD.lace)}, LACED = ${glslNum(SEA_FOLD.laced)},
    BY = ${glslNum(SEA_FOLD.laceBy)};
  vec3 slopes = vec3(casc0.w, casc1.w, casc2.w), lost = 1.0 - hd;
  vec3 v = slopes * w * w * choppy * choppy, vf = slopes * wf * wf * BY * BY * choppy * choppy, vc = sqrt(v * vf);
  float sx2 = v.x + v.y + v.z + SOFT * SOFT, sf2 = vf.x + vf.y + vf.z + LS * LS, cov = vc.x + vc.y + vc.z;
  float all = LACED + (1.0 - LACED) * normalCdf((LT - 1.0) / sqrt(sf2));
  float z = normalQuantile(min(breakShare / all, 0.98));
  float lacedIn = LACED + (1.0 - LACED) * normalCdf((LT - 1.0 + cov * normalDensity(z) / max(normalCdf(z), 1e-9) / sqrt(sx2))
    / sqrt(max(sf2 - cov * cov / sx2, 1e-6)));
  float tau = breakShare > 0.0 ? 1.0 + sqrt(sx2) * normalQuantile(min(breakShare / lacedIn, 0.98)) : -1e9;
  float vl = dot(v, lost) + SOFT * SOFT, fl = dot(vf, lost) + LS * LS, cl = dot(vc, lost);
  float a = (tau - 1.0 - choppy * (s.m[0][0] + s.m[1][1])) / sqrt(vl), caps = normalCdf(a);
  float under = -sqrt(vl) * normalDensity(a) / max(caps, 1e-9);
  float lace = normalCdf((LT - 1.0 - BY * choppy * (fine.m[0][0] + fine.m[1][1]) - cl * under / vl) / sqrt(max(fl - cl * cl / vl, 1e-6)));
  return Waves(s.h, s0.h, s.grad, gGrad, caps, lace);
}
Waves wavesHere(vec2 p, Vortex vt, vec3 w, vec3 wf, vec3 wg, bool calmer) {
  Bend b = vt.b;
  bool bent = b.on > 0.0;
  float f = bent ? inversesqrt(b.w.x * b.w.x + b.w.y * b.w.y + 2.0 * b.w.x * b.w.y * b.rho) : 1.0;
  Waves o = Waves(0.0, 0.0, vec2(0.0), vec2(0.0), 0.0, 0.0);
  int layers = bent ? 2 : 1;
  for (int i = 0; i < layers; i++) {
    float k = bent ? (i == 0 ? b.w.x : b.w.y) : 1.0;
    if (k <= 0.0) continue;
    float a = i == 0 ? b.al.x : b.al.y, s = bent ? (i == 0 ? b.s.x : b.s.y) : 0.0, amp = bent ? bendAmp(s) : 1.0, wide = bent ? 1.0 / bendThin(s) : 1.0;
    Waves l = wavesAt(bent ? (i == 0 ? b.q.xy : b.q.zw) : p, w, wf, wg, calmer, ypx * wide, bent ? heldBy(wide) : held);
    mat2 G = bent ? transpose(mat2(1.0) + s * outerProduct(b.round, b.out_)) * mat2(cos(a), -sin(a), sin(a), cos(a)) : mat2(1.0);
    float kf = k * f * amp;
    o = Waves(o.h + kf * l.h, o.h0 + kf * l.h0, o.grad + kf * (G * l.grad), o.gGrad + kf * (G * l.gGrad), o.caps + k * l.caps, o.lace + k * l.lace);
  }
  return o;
}
vec2 foamField(vec2 q, float cell, float px) {
  float warp = ${glslNum(FOAM.warp)} * cell * smoothstep(1.2, 3.0, cell * THIN / px);
  if (warp > 0.0) q += warp * vec2(gnoise(q / (2.0 * cell) + 3.7), gnoise(q / (2.0 * cell) + 11.1));
  float f = 0.0, amp = 0.5, c = cell, seen = 0.0;
  for (int k = 0; k < 10; k++) {
    float see = smoothstep(1.2, 3.0, c * THIN / px);
    f += amp * (see > 0.0 ? 0.5 + 0.5 * see * gnoise(q / c + float(k) * 17.3) : 0.5);
    seen += amp * amp * see;
    amp *= ${glslNum(FOAM.gain)};
    c *= 0.5;
    q = mat2(0.6, 0.8, -0.8, 0.6) * q;
  }
  return vec2(f / ${foamSums()[0].toFixed(6)}, seen / ${foamSums()[1].toFixed(6)});
}
float levelOver(float c) {
  float p = clamp(min(c, 1.0 - c), 1e-5, 0.5), r = sqrt(-2.0 * log(p));
  float z = r - (2.515517 + 0.802853 * r + 0.010328 * r * r) / (1.0 + 1.432788 * r + 0.189269 * r * r + 0.001308 * r * r * r);
  return c < 0.5 ? z : -z;
}
float foamOf(vec2 s, float cover) {
  float shape = max(cover, ${glslNum(FOAM.floor)}), level = levelOver(shape), f = s.x / sqrt(max(s.y, 0.05));
  float edge = smoothstep(level - ${glslNum(FOAM.edge)}, level + ${glslNum(FOAM.edge)}, f);
  float thick = mix(${glslNum(FOAM.thin)}, 1.0, smoothstep(level, max(level + ${glslNum(FOAM.thick)}, ${glslNum(FOAM.whole)}), f));
  return mix(cover, edge * thick * cover / shape, sqrt(s.y));
}
vec2 crumbAt(vec2 q, float px) {
  const float C = ${glslNum(FOAM.crumb.size)};
  float see = smoothstep(1.2, 3.0, C / px);
  if (see <= 0.0) return vec2(0.0);
  vec2 g = q / C, i = floor(g);
  float d = 9.0;
  for (int y = -1; y <= 1; y++) {
    for (int x = -1; x <= 1; x++) {
      vec2 c = i + vec2(float(x), float(y));
      d = min(d, length(c + vec2(hash(c + 41.0), hash(c + 67.0)) - g));
    }
  }
  return vec2(see * (${glslNum(FOAM.crumb.mean)} - d) / ${glslNum(FOAM.crumb.sd)}, see);
}
vec2 fieldScore(vec2 field) { return vec2((field.x - 0.5) / FIELD_SD, field.y); }
vec2 streakField(float psi, float r, float px) {
  float k0 = t / STREAK_LIFE, k1 = k0 + 0.5, p0 = fract(k0), p1 = fract(k1), w0 = 1.0 - abs(2.0 * p0 - 1.0), w1 = 1.0 - w0;
  float rr = max(r, CORE), back = 2.0 * PK * GAM * flowShare(rr).x * STREAK_LIFE;
  float y0 = 0.5 * log(rr * rr + back * p0), y1 = 0.5 * log(rr * rr + back * p1);
  float h0 = 31.0 * hash(vec2(floor(k0), 7.0)), h1 = 31.0 * hash(vec2(floor(k1), 7.0));
  float q0 = psi + 1.6 * (ringNoise(vec2(psi / TAU * 3.0, y0 * 0.9 + h0), 3.0) - 0.5) + 0.7 * (ringNoise(vec2(psi / TAU * 7.0 + 3.0, y0 * 1.9 + h0), 7.0) - 0.5);
  float q1 = psi + 1.6 * (ringNoise(vec2(psi / TAU * 3.0, y1 * 0.9 + h1), 3.0) - 0.5) + 0.7 * (ringNoise(vec2(psi / TAU * 7.0 + 3.0, y1 * 1.9 + h1), 7.0) - 0.5);
  float s0 = 0.0, s1 = 0.0, held = 0.0, all = 0.0;
  for (int i = 0; i < 4; i++) {
    float n = STREAK_N[i], a = STREAK_A[i], see = smoothstep(1.2, 3.0, TAU * r * 0.94 / n / px);
    s0 += a * see * (ringNoise(vec2(q0 / TAU * n, y0 * STREAK_M[i] + 97.0 * hash(vec2(floor(k0), float(i)))), n) - 0.5);
    s1 += a * see * (ringNoise(vec2(q1 / TAU * n, y1 * STREAK_M[i] + 97.0 * hash(vec2(floor(k1), float(i)))), n) - 0.5);
    held += a * a * see;
    all += a * a;
  }
  return vec2((w0 * s0 + w1 * s1) / (length(vec2(w0, w1)) * 0.215 * sqrt(all)), held / all);
}
vec2 fieldBlend(vec2 a, vec2 b, vec2 w) {
  return vec2(0.5 + (w.x * (a.x - 0.5) + w.y * (b.x - 0.5)) / length(w), w.x * a.y + w.y * b.y);
}
float whitecaps(float F) {
  return min(3.84e-6 * pow(0.836 * pow(max(F, 0.0), 1.5), 3.41), 0.6);
}
  const float FOAM_LIFE = 2.5;
float breakingAt(Vortex vt) {
  float r = max(length(vt.d), CORE), psi = atan(vt.d.x, -vt.d.y) + SPIN * log(r) / PK, got = 0.0, all = 0.0;
  for (int k = 0; k < 4; k++) {
    float back = float(k * k) * 0.45, rk = sqrt(r * r + 2.0 * PK * GAM * back * flowShare(r).x), left = exp(-back / FOAM_LIFE);
    got += left * smoothstep(0.55, 0.8, ringNoise(vec2(psi * 48.0 / TAU, 14.0 * log(rk) + 0.06 * (t - back)), 48.0));
    all += left;
  }
  return got / all;
}
float currentSpeed(float r) {
  return (r >= CORE ? GAM / r : GAM * r / (CORE * CORE)) * flowShare(r).x;
}
vec2 currentAt(vec2 d) {
  float r = max(length(d), 1e-3);
  vec2 o = d / r;
  return currentSpeed(r) * (-SPIN * vec2(o.y, -o.x) - PK * o);
}
float churnedForce(float speed, float F) {
  return mix(F, max(F, 12.0), min(1.0, speed / CHURN_V));
}
float blockedAt(float against, float speed, float F) {
  float q = max(0.836 * pow(max(F, 0.0), 1.5) / 0.9144 / 0.877 / 4.0, 1e-3);
  return smoothstep(0.3, 1.0, against / q) * (1.0 - smoothstep(1.3, 2.6, speed / q)) * smoothstep(0.5, 2.5, F);
}
float breakingSource(vec2 d, float when, float F, vec2 way) {
  float U = 0.836 * pow(max(F, 0.0), 1.5) / 0.9144;
  vec2 q = (mael.xy + d - way * 0.5 * U / 0.877 * when) / 650.0;
  float groups = smoothstep(0.3, 0.75, 0.6 * noise(q) + 0.4 * noise(mat2(0.6, 0.8, -0.8, 0.6) * q * 2.3 + 5.1));
  vec2 v = currentAt(d);
  float speed = length(v);
  return BLOCK * blockedAt(-dot(v, way), speed, F) * groups + whitecaps(churnedForce(speed, F));
}
float carriedFoam(Vortex vt, float F, vec2 way) {
  float r = max(length(vt.d), CORE), turn = TAU * r * r / GAM, got = 0.0, all = 0.0;
  for (int k = 0; k < 5; k++) {
    float back = float(k * k) / 16.0 * 0.7 * turn, left = exp(-back / (KEEP * turn));
    got += left * breakingSource(swirlBack(vt.d, back), t - back, F, way);
    all += left;
  }
  return max(got / all - whitecaps(F), 0.0);
}
vec4 swirlFoam(vec2 p, float px, Vortex vt, float cover, float rimK, float wallA) {
  vec3 s = swirlAt(vt.d);
  float F = forceAt(p);
  vec2 st = streakField(s.y, s.x, px);
  vec2 coarse = fieldBlend(foamField(vt.dr.at.xy + 400.0, 8.0 * LACE, px), foamField(vt.dr.at.zw + 400.0, 8.0 * LACE, px), vt.dr.w);
  float pieces = smoothstep(0.3, 0.7, coarse.x);
  float c = clamp(cover * carriedFoam(vt, F, windAt(p)) * (0.6 + 0.8 * breakingAt(vt)) * mix(0.3, 1.7, pieces), 0.0, 0.92) * (1.0 - wallA);
  float foam = 0.0;
  if (c > 1e-4) {
    vec2 fs = fieldScore(fieldBlend(foamField(vt.dr.at.xy, LACE, px), foamField(vt.dr.at.zw, LACE, px), vt.dr.w)), fc = fieldScore(coarse);
    float a = mix(0.2, 0.75, 1.0 - smoothstep(0.3, 0.75, vt.x)), g = 0.6 * smoothstep(0.3, 0.8, vt.x), b = sqrt(max(1.0 - a * a - g * g, 0.0));
    vec2 field = vec2(a * st.x + b * fs.x + g * fc.x, a * a * st.y + b * b * fs.y + g * g * fc.y);
    float broken = foamOf(field, c), near = foamOf(field + vec2(0.5, 0.0), c);
    broken *= mix(0.5, 1.0, smoothstep(0.02, 0.2, c));
    float open = 0.0, specks = 0.0, h = 16.0;
    vec2 qa = vt.dr.at.xy, qb = vt.dr.at.zw;
    for (int k = 0; k < 4; k++) {
      float see = smoothstep(1.2, 3.0, h * THIN / px);
      float nb = fieldBlend(vec2(noise(qa / h + 77.0 + float(k)), 1.0), vec2(noise(qb / h + 77.0 + float(k)), 1.0), vt.dr.w).x;
      open = max(open, see * smoothstep(0.62, 0.7, nb));
      specks = max(specks, see * smoothstep(0.72, 0.78, 1.0 - nb));
      h *= 0.45;
      qa = mat2(0.6, 0.8, -0.8, 0.6) * qa;
      qb = mat2(0.6, 0.8, -0.8, 0.6) * qb;
    }
    broken = broken * (1.0 - mix(0.85, 0.4, smoothstep(0.1, 0.6, c)) * open) + (near - broken) * specks * 0.8;
    float laced = smoothstep(1.2, 3.0, 4.0 * THIN / px);
    if (laced > 0.0) {
      float lt = vt.dr.w.x * threads(vt.dr.at.xy / 4.0 + 31.0, 0.2) + vt.dr.w.y * threads(vt.dr.at.zw / 4.0 + 31.0, 0.2);
      broken = max(broken, laced * lt * (foamOf(field + vec2(0.9, 0.0), c) - broken) * 0.9);
    }
    foam = 0.92 * broken;
  }
  float l = (length(vt.d) - 4.0 * CORE) / (1.3 * CORE), lip = exp(-l * l);
  float rim = lip > 0.002 ? lip * laceAt(vt.dr, 0.5 * LACE, 9.0, px, 0.8) : 0.0;
  return vec4(clamp(foam + rim * rimK, 0.0, 0.95), smoothstep(0.0, 0.3, c), st.x, smoothstep(0.42, 0.72, coarse.x));
}
float wallsAt(Vortex vt) {
  float q = length(vt.d) / CORE;
  return smoothstep(0.03, 0.3, 1.0 / (1.0 + q * q));
}
vec4 airOver(vec4 o, float share, float litL);
vec4 swirlLayer(vec2 p, float px, float litL, vec3 foamRgb, Vortex vt, float foam, float air, float aired) {
  if (vt.x >= 1.0) return vec4(0.0);
  float r = length(vt.d), q = r / CORE, sink = 1.0 / (1.0 + q * q);
  vec3 Nf = normalize(vec3(-vt.fun.yz, 1.0));
  float face = clamp(dot(Nf, toward) / max(toward.z, 0.15), 0.0, 1.6);
  vec3 turq = vec3(0.16, 0.6, 0.56), teal = vec3(0.04, 0.2, 0.24), deep = vec3(0.01, 0.05, 0.08);
  float wallA = wallsAt(vt);
  vec4 o = vec4(0.0);
  if (wallA > 0.0) {
    vec3 wallRgb = mix(teal, deep, smoothstep(0.1, 0.75, sink));
    o = vec4(wallRgb * mix(0.3, 1.4, face / 1.6) * mix(0.8, 1.2, laceAt(vt.dr, 0.5 * CORE, 0.0, px, 0.5)) * litL, 1.0) * wallA;
    vec3 V = normalize(vec3(centre - p, eyeUp)), Hv = normalize(glintL + V);
    float ch = max(dot(Nf, Hv), 1e-3), t2 = (1.0 - ch * ch) / (ch * ch), r2 = 0.03;
    float shine = clamp(exp(-t2 / r2) / (3.14159 * r2 * ch * ch * ch * ch) * 0.04 * glintK, 0.0, 0.8) * wallA * sunNow;
    o = over(vec4(glintRgb * shine, shine), o);
  }
  o = airOver(o, air * (1.0 - wallA) * mix(0.15, 0.45, aired), litL);
  o = over(vec4(foamRgb * foam, foam), o);
  return over(vec4(vec3(${MAELSTROM.eyeRgb.map(glslNum).join(", ")}) * (0.5 + 0.5 * litL), 1.0) * vt.eye * (1.0 - 0.8 * foam), o);
}
vec2 steepAt(vec2 p, vec2 inward, float dep) {
  float dOut = fieldAt(p - inward * 10.0).y, dIn = fieldAt(p + inward * 6.0).y;
  return vec2(smoothstep(0.15, 0.8, (dOut - max(dep, 0.0)) / 10.0), smoothstep(0.2, 1.0, (min(dep, 0.0) - dIn) / 6.0));
}

float trainPhase(float tau, vec2 shore, float T, vec2 way) {
  float L = g * T * T / TAU;
  return TAU * (t + tau - dot(way, shore) * T / L) / T;
}
vec2 swellPhase(float tau, vec2 shore) {
${SEA_SWELL.ways.map((deg, j) => `  float ph${j} = trainPhase(tau, shore, swellT * ${glslNum(SEA_SWELL.periods[j])}, vec2(${Math.cos((deg * Math.PI) / 180).toFixed(6)}, ${(-Math.sin((deg * Math.PI) / 180)).toFixed(6)}));`).join("\n")}
  const float R = ${glslNum(SEA_SWELL.share)};
  float d = mod(ph1 - ph0, TAU);
  return vec2((ph0 + atan(R * sin(d), 1.0 + R * cos(d))) / TAU, sqrt(1.0 + R * R + 2.0 * R * cos(d)) / (1.0 + R));
}
float crestHeight(vec2 shore, float k) {
  vec2 x = shore / ${glslNum(SEA_CREST.cell)}, i = floor(x), f = fract(x), w = f * f * (3.0 - 2.0 * f), s = vec2(37.0, 59.0) * k;
  vec4 r = vec4(hash(i + s), hash(i + s + vec2(1.0, 0.0)), hash(i + s + vec2(0.0, 1.0)), hash(i + s + vec2(1.0, 1.0)));
  vec4 h = ${(2 / Math.sqrt(Math.PI)).toFixed(6)} * sqrt(-log(clamp(r, 1e-4, 1.0)));
  return mix(mix(h.x, h.y, w.x), mix(h.z, h.w, w.x), w.y);
}

vec2 sprayAt(vec2 p, float px) {
  float keep = 1.0, keepShadow = 1.0;
  const float C = ${glslNum(SEA_SPRAY.cell)};
  vec2 cell = floor(p / C);
  vec2 sun = toward.xy / max(toward.z, 0.25);
  float day = (1.0 - 0.7 * night) * clamp(glintK, 0.0, 1.0) * sunNow;
  for (int j = -1; j <= 1; j++) {
    for (int i = -1; i <= 1; i++) {
      vec2 c = cell + vec2(float(i), float(j));
      vec2 o = (c + 0.2 + 0.6 * vec2(hash(c), hash(c + vec2(91.0, 7.0)))) * C;
      vec4 fo = fieldAt(o);
      if (abs(fo.x) > C) continue;
      float e = 1.5;
      vec2 gs = vec2(fieldAt(o + vec2(e, 0.0)).x - fieldAt(o - vec2(e, 0.0)).x, fieldAt(o + vec2(0.0, e)).x - fieldAt(o - vec2(0.0, e)).x) / (2.0 * e);
      if (length(gs) < 0.2) continue;
      vec2 inward = -normalize(gs);
      o += inward * fo.x;
      vec4 fw = fieldAt(o);
      vec2 st = steepAt(o, inward, fw.y);
      float steep = max(st.y, 0.7 * st.x);
      if (steep < ${glslNum(SEA_SPRAY.steep)}) continue;
      vec2 paint = paintAt(o);
      float F = forceOf(paint, o);
      float strength = steep * smoothstep(${glslNum(SEA_SPRAY.force[0])}, ${glslNum(SEA_SPRAY.force[1])}, F);
      if (strength <= 0.0) continue;
      vec2 swell = swellPhase(fw.z, o);
      float k = swell.x + 0.3 * hash(c + vec2(3.0, 5.0));
      float wave = floor(k), age = fract(k) * swellT - ${glslNum(SEA_SPRAY.beat)};
      if (age <= 0.0 || age > ${glslNum(SEA_SPRAY.life)}) continue;
      if (hash(c * 3.0 + vec2(wave * 7.0, wave * 13.0)) > min(1.3 * strength * swell.y, 1.0)) continue;
      float jet = mix(${glslNum(SEA_SPRAY.jet[0])}, ${glslNum(SEA_SPRAY.jet[1])}, steep) * swellHere(paint, o) * (0.7 + 0.6 * hash(c + vec2(wave, 29.0)));
      float v = sqrt(2.0 * g * jet);
      vec2 windV = windAt(o) * (0.836 * pow(max(F, 0.0), 1.5) / 0.9144) * ${glslNum(SEA_SPRAY.drift)};
      for (int d = 0; d < ${SEA_SPRAY.count}; d++) {
        vec2 q = c * 3.0 + vec2(float(d) * 13.0 + wave * 5.0, wave * 11.0 + float(d) * 3.0);
        float r1 = hash(q), r2 = hash(q + 41.0), r3 = hash(q + 83.0), r4 = hash(q + 127.0), r5 = hash(q + 211.0);
        float tauD = r1 < ${glslNum(SEA_SPRAY.drops[0][0])} ? mix(${SEA_SPRAY.drops[0][1].map(glslNum).join(", ")}, r2)
          : r1 < ${glslNum(SEA_SPRAY.drops[0][0] + SEA_SPRAY.drops[1][0])} ? mix(${SEA_SPRAY.drops[1][1].map(glslNum).join(", ")}, r2)
          : mix(${SEA_SPRAY.drops[2][1].map(glslNum).join(", ")}, r2);
        bool big = r1 < ${glslNum(SEA_SPRAY.drops[0][0])}, mid = r1 < ${glslNum(SEA_SPRAY.drops[0][0] + SEA_SPRAY.drops[1][0])};
        float rad = (big ? ${glslNum(SEA_SPRAY.drops[0][2])} : mid ? ${glslNum(SEA_SPRAY.drops[1][2])} : ${glslNum(SEA_SPRAY.drops[2][2])})
          * (1.0 + ${glslNum(SEA_SPRAY.grow)} * age);
        float white = big ? ${glslNum(SEA_SPRAY.drops[0][3])} : mid ? ${glslNum(SEA_SPRAY.drops[1][3])} : ${glslNum(SEA_SPRAY.drops[2][3])};
        float up = radians(mix(${glslNum(SEA_SPRAY.up[0])}, ${glslNum(SEA_SPRAY.up[1])}, r4));
        float turn = (r5 - 0.5) * 2.0 * ${glslNum(SEA_SPRAY.spread)};
        vec2 way = mat2(cos(turn), sin(turn), -sin(turn), cos(turn)) * inward;
        float speed = v * mix(0.7, 1.15, r3);
        float kk = 1.0 - exp(-age / tauD), fall = g * tauD;
        float h = -fall * age + (speed * sin(up) + fall) * tauD * kk;
        if (h <= 0.0) continue;
        vec2 at = o + way * speed * cos(up) * tauD * kk + windV * (age - tauD * kk);
        float rr = max(rad, 0.7 * px);
        float d2 = dot(p - at, p - at) / (rr * rr);
        float a = exp(-2.5 * d2) * min(1.0, (rad * rad) / (rr * rr)) * white / (1.0 + ${glslNum(SEA_SPRAY.grow)} * age) * strength
          * smoothstep(0.0, 0.15, h);
        keep *= 1.0 - a;
        vec2 s2 = p - (at - sun * h);
        float sh = exp(-1.5 * dot(s2, s2) / (rr * rr)) * min(1.0, (rad * rad) / (rr * rr)) / (1.0 + ${glslNum(SEA_SPRAY.grow)} * age);
        keepShadow *= 1.0 - 0.22 * sh * strength * day;
      }
    }
  }
  return vec2(1.0 - keep, 1.0 - keepShadow);
}


Waves seaWaves(vec2 p, Vortex vt, float F, vec3 weigh, float depth, out vec3 bottom, out bool calmer) {
  float U = 0.836 * pow(max(F, 0.0), 1.5) / 0.9144;
  vec2 drift = p - windAt(p) * U * 0.35 * gustAt;
  vec2 d1 = mat2(0.8, 0.6, -0.6, 0.8) * drift, d2 = mat2(0.28, -0.96, 0.96, 0.28) * drift;
  float gn = 0.5 * noise(drift / 1100.0) + 0.3 * noise(d1 / 470.0 + 7.0) + 0.2 * noise(d2 / 210.0 + 3.0);
  float gust = mix(0.55, 1.4, smoothstep(0.25, 0.75, gn));
  vec3 shoal = pow(max(0.5 * cascL / max(depth, 0.05), vec3(1.0)), vec3(0.25));
  float shoalHs = 4.0 * length(cascH * weigh * shoal), limit = ${glslNum(SEA_FOLD.depth)} * depth;
  bottom = shoal * (shoalHs > 0.0 ? min(1.0, limit / shoalHs) : 1.0);
  float onBottom = shoalHs > 0.0 ? exp(-2.0 * pow(limit / shoalHs, 2.0)) * smoothstep(0.0, ${glslNum(SEA_FOLD.ripple)}, shoalHs) : 0.0;
  breakShare = 1.0 - (1.0 - whitecaps(F)) * (1.0 - onBottom);
  vec3 w = vec3(sqrt(gust), gust, gust) * bottom * weigh;
  calmer = min(weigh.x, min(weigh.y, weigh.z)) < 1.0;
  return wavesHere(p, vt, w, vec3(0.0, gust, gust) * vec3(1.0, max(weigh.y, 0.25), max(weigh.z, 0.25)),
                      vec3(sqrt(gust), gust, gust) * bottom * max(weigh, vec3(1.0)), calmer);
}

const vec3 turq = vec3(0.15, 0.58, 0.55), teal = vec3(0.07, 0.30, 0.33), deep = vec3(0.02, 0.10, 0.15);
vec4 waterBase(vec2 p, float depth, float dep, float aerated, Vortex vt, float litL, float hid, float wall, vec2 inward, vec2 gd,
               float near, vec4 kind, out float wetness) {
  float inl = kind.x, blue = kind.y, alpha = 0.42;
  float clear = 1.0 - exp(-depth / mix(2.6, ${glslNum(INLAND.colour.waterline)}, inl * (1.0 - blue)));
  vec3 blues = mix(turq, teal, smoothstep(1.5, 8.0, depth)), body = mix(blues, deep, smoothstep(8.0, 40.0, depth));
  vec4 sand = groundAt(p + inward * (mix(clamp(depth / max(length(gd), 0.08), 0.0, 14.0), kind.z, kind.x) + 2.5));
  if (inl > 0.0) {
    vec3 bed = mix((sand.w > 0.5 ? sand.rgb : vec3(${INLAND.colour.bed.map(glslNum).join(", ")})) * ${glslNum(INLAND.colour.wet)},
                   vec3(${INLAND.colour.clear.map(glslNum).join(", ")}), ${glslNum(INLAND.colour.tint)});
    float deep = smoothstep(${INLAND.colour.deep.map(glslNum).join(", ")}, kind.w);
    vec3 calm = mix(mix(bed, vec3(${INLAND.colour.clear.map(glslNum).join(", ")}), 1.0 - exp(-depth / ${glslNum(INLAND.colour.shallow)})),
                    vec3(${INLAND.colour.dark.map(glslNum).join(", ")}), deep);
    vec3 hue = lit / max(litL, 1e-3);
    body = mix(body, mix(calm, blues, blue) * mix(vec3(1.0), hue, ${glslNum(INLAND.colour.zone)}), inl);
    alpha = mix(0.42, mix(${glslNum(INLAND.colour.near)}, ${glslNum(INLAND.colour.opaque)}, deep), inl * (1.0 - blue));
  }
  body *= 1.0 + 0.4 * aerated;
  float edge = mix(4.0, ${glslNum(INLAND.colour.edge)}, inl * (1.0 - blue));
  vec4 o = vec4(body * litL * alpha * (1.0 - 0.65 * hid) * wall, alpha) * smoothstep(0.0, edge, depth);
  if (sand.w > 0.5 && near > 0.0) {
    vec3 under = sand.rgb * mix(vec3(1.0), vec3(0.72, 0.95, 0.92), smoothstep(0.0, 0.8, dep));
    vec3 shallowRgb = mix(under, body, clear);
    float a = smoothstep(-1.2, -0.3, dep) * (1.0 - smoothstep(9.0, 14.0, depth)) * near;
    o = over(vec4(shallowRgb * lit, 1.0) * a, o);
  }
  wetness = smoothstep(0.0, 1.2, dep);
  o = over(vec4(0.0, 0.0, 0.0, 0.6 * night * wetness), o);
  return o;
}
vec4 airOver(vec4 o, float share, float litL) {
  return over(vec4(turq * litL, 1.0) * clamp(share, 0.0, 0.9), o);
}

vec4 skyOver(vec4 o, vec2 p, vec3 N, float height, float wetness, float hid, float litL, out vec3 V) {
  V = normalize(vec3(centre - p, eyeUp));
  float trough = clamp(-height / max(3.0 * rms, 0.05), 0.0, 1.0) * 0.18 * (1.0 - 0.7 * night) * wetness;
  o = over(vec4(0.0, 0.0, 0.0, trough), o);
  float fres = 0.02 + 0.98 * pow(1.0 - clamp(dot(N, V), 0.0, 1.0), 5.0);
  vec3 mirrored = reflect(-V, N);
  float sunward = 1.0 + sunwardL.x * pow(max(dot(normalize(mirrored), glintL), 0.0), sunwardL.y) * (1.0 - night);
  float skyA = clamp((fres - 0.02) * ${glslNum(SEA_SKY.k)} * sunward, 0.0, ${glslNum(SEA_SKY.most)}) * (1.0 - 0.8 * night) * wetness
    * (1.0 - 0.6 * hid);
  float rise = clamp(mirrored.z, 0.0, 1.0);
  vec3 skyRgb = mix(vec3(${SEA_SKY.horizon.map(glslNum).join(", ")}), vec3(${SEA_SKY.zenith.map(glslNum).join(", ")}), sqrt(rise));
  o = over(vec4(min(litL * skyRgb, vec3(1.0)) * skyA, skyA), o);
  return o;
}

vec4 foamGlint(vec4 o, vec3 foamRgb, float foam, Waves s, bool calmer, vec3 weigh, vec3 bottom, vec2 swellSlope, Vortex vt,
               float spread, float glass, vec3 N, vec3 V, float facing, float flatLit, float wetness, float px, float litL) {
  float ride = clamp((max(dot(N, toward), 0.0) + 0.02) / (max(facing, 0.0) + 0.02), 0.55, 1.45);
  o = over(vec4(min(foamRgb * ride, vec3(1.0)) * foam, foam), o);

  vec3 w2 = max(weigh, vec3(1.0));
  w2 *= w2;
  vec2 facets = (calmer ? s.gGrad : s.grad) + swellSlope, tilt = vt.fun.yz;
  vec3 Ng = normalize(vec3(-(facets + tilt), 1.0));
  float bendS = dot(vt.b.w, abs(vt.b.s)), bendSpread = vt.b.on > 0.0 ? (1.0 + 0.5 * bendS * bendS) / (1.0 + bendS * bendS / (DAMP * DAMP)) : 1.0;
  float lost = dot(vec3(casc0.w, casc1.w, casc2.w) * w2 * bottom, 1.0 - heldBy(vt.b.on > 0.0 ? 1.0 / bendThin(bendS) : 1.0)) * bendSpread
    + spread;
  float r2 = 0.0016 + lost * lostL;
  vec3 Hv = normalize(glintL + V);
  float ch = max(dot(Ng, Hv), 1e-3);
  vec2 toLight = normalize(glintL.xy + vec2(1e-4, 0.0)), dS = -(facets * (1.0 - glass) + tilt) - Hv.xy / max(Hv.z, 1e-3);
  float along = dot(dS, toLight), across = dot(dS, vec2(-toLight.y, toLight.x));
  float stretch = axisL * clamp(${glslNum(SEA_LIGHT.lowFrom)} / max(glintL.z, 0.05), 1.0, lowMostL);
  float wA = r2 * stretch, wC = r2 / axisL;
  float lightK = glintK * (1.0 - foam) * wetness * sunNow;
  float peak = 0.05 * (1.0 - glass) / (3.14159 * r2 * ch * ch * ch * ch) * r2 / (0.0016 + lost) * lightK;
  float beck = exp(-(along * along / wA + across * across / wC)) * peak;
  float wCore = coreL.x * pow(GLASS / coreL.x, glass), coreTop = coreL.y * lightK;
  float core = exp(-(along * along + across * across) / wCore) * coreTop;
  float cr = crispL.x, glitter = pow(clamp(beck + core, 0.0, 0.95) / 0.95, cr);
  float eL = lost * (1.0 - lostL) * mergeL, eA = eL * stretch, eC = eL / axisL;
  float a1 = wA / cr, b1 = wC / cr, k1 = wCore / cr;
  float merged = lobeLight(peak / 0.95, cr) * sqrt(a1 / (a1 + eA) * b1 / (b1 + eC)) * exp(-(along * along / (a1 + eA) + across * across / (b1 + eC)))
    + lobeLight(coreTop / 0.95, cr) * sqrt(k1 / (k1 + eA) * k1 / (k1 + eC)) * exp(-(along * along / (k1 + eA) + across * across / (k1 + eC)));
  float glint = clamp(mix(glitter, merged, mergeL) * crispL.y, 0.0, 0.95);
  float faces = max(dot(N, glintL), 0.0) / max(facing, flatLit) - 1.0;
  float tips = pow(clamp(faces * tipsL.x * 0.1, 0.0, 1.0), 2.0) * tipsL.y * tipsK * sunNow * wetness * (1.0 - foam);
  glint = clamp(glint + tips, 0.0, 0.95);
  float low = smoothstep(skyLowL.x, skyLowL.y, clamp(reflect(-V, N).z, 0.0, 1.0));
  float sparkle = low * skyLowL.z * (1.0 - foam) * wetness * (1.0 - night)
    * (1.0 - smoothstep(skyFadeL.x, skyFadeL.y, px));
  o = over(vec4(min(litL * vec3(${SEA_SKY.horizon.map(glslNum).join(", ")}), vec3(1.0)) * sparkle, sparkle), o);
  o = over(vec4(glintRgb * glint, glint), o);
  return o;
}

float closeIn(float px) {
  return 1.0 - smoothstep(0.9, 2.6, px);
}

vec4 inlandOr(vec2 q, vec4 a) {
  vec4 x, y;
  return inlandAt(q, x, y) ? x : a;
}
Waves swellOf(vec2 q, float w, float chop, out vec2 d) {
  Sea s = surface(q, vec3(0.0, 0.0, chop), vec3(0.0), vec2(w, 0.0), ypx).a;
  d = s.d;
  return Waves(s.h, s.h, s.grad, s.grad, 0.0, 0.0);
}
float runAt(vec4 a, vec4 b) {
  float side = smoothstep(0.0, 1.0, a.x / max(b.x, 1.0)), h = max(b.w, 0.0) * ${glslNum(INLAND.reach)} + abs(b.y);
  return ${glslNum(INLAND.run * INLAND.narrow)} / max(b.x, ${glslNum(INLAND.narrow)}) * mix(${glslNum(INLAND.bank)}, 1.0, side)
         + min(sqrt(${glslNum(2 * INLAND.g)} * h), ${glslNum(INLAND.rush)});
}
Waves wavesMix(Waves a, Waves b, vec2 w) {
  float k = inversesqrt(dot(w, w));
  return Waves((a.h * w.x + b.h * w.y) * k, (a.h0 * w.x + b.h0 * w.y) * k, (a.grad * w.x + b.grad * w.y) * k,
               (a.gGrad * w.x + b.gGrad * w.y) * k, a.caps * w.x + b.caps * w.y, a.lace * w.x + b.lace * w.y);
}
struct Run { vec4 at; vec2 w; vec2 age; };
Run runOf(vec2 p, vec2 v, float cycle) {
  float k0 = t / cycle + noise(p / ${glslNum(INLAND.hand)}), k1 = k0 + 0.5, w0 = 1.0 - abs(2.0 * fract(k0) - 1.0);
  vec2 j0 = 997.0 * vec2(hash(vec2(floor(k0), 5.0)), hash(vec2(floor(k0), 6.0)));
  vec2 j1 = 997.0 * vec2(hash(vec2(floor(k1), 7.0)), hash(vec2(floor(k1), 8.0)));
  return Run(vec4(p - v * fract(k0) * cycle + j0, p - v * fract(k1) * cycle + j1), vec2(w0, 1.0 - w0), vec2(fract(k0), fract(k1)));
}
struct Inland { vec4 a; vec4 b; vec4 c; vec2 gd; vec2 inward; vec2 v; Waves s; vec2 d; float murk; };
Inland inlandOf(vec2 p) {
  Inland w = Inland(vec4(-100.0, -100.0, 0.0, 0.0), vec4(0.0), vec4(0.0), vec2(0.0), vec2(0.0), vec2(0.0),
                    Waves(0.0, 0.0, vec2(0.0), vec2(0.0), 0.0, 0.0), vec2(0.0), 0.0);
  vec4 a, b, c;
  if (inlandAt(p, a, b, c)) { w.a = a; w.b = b; w.c = c; }
  return w;
}
Inland inlandSurface(vec2 p, Inland w) {
  const float HEIGHT = ${inlandSwell().toExponential(4)};
  const int C = ${INLAND.swell.cascade};
  vec4 a = w.a, b = w.b;
  float e = 2.0;
  vec4 n4 = inlandOr(p + vec2(e, 0.0), a), s4 = inlandOr(p - vec2(e, 0.0), a), w4 = inlandOr(p + vec2(0.0, e), a), e4 = inlandOr(p - vec2(0.0, e), a);
  vec2 gd = vec2(n4.y - s4.y, w4.y - e4.y) / (2.0 * e), gs = vec2(n4.x - s4.x, w4.x - e4.x) / (2.0 * e);
  vec2 away = length(gs) > 1e-4 ? normalize(gs) : vec2(0.0), inward = length(gs) > 1e-4 ? -away : (length(gd) > 1e-4 ? -normalize(gd) : vec2(0.0));
  float murk = max(a.y, 0.0), weight = 1.0;
  for (int k = 0; k < 16; k++) {
    bool far = k >= 6;
    float ang = far ? 0.6283185 * (float(k - 6) + 0.5) : 1.0471976 * float(k);
    float wk = far ? ${glslNum(INLAND.colour.ring[1])} : ${glslNum(INLAND.colour.ring[0])};
    murk += wk * max(inlandOr(p + (far ? ${glslNum(INLAND.colour.soft[1])} : ${glslNum(INLAND.colour.soft[0])}) * vec2(cos(ang), sin(ang)), a).y, 0.0);
    weight += wk;
  }
  murk /= weight;
  vec2 v = a.zw * runAt(a, b);
  float h = HEIGHT * fetchAt(a.x, windAt(p), away)[C] + ${glslNum(INLAND.current)} * min(length(v) / ${glslNum(INLAND.run)}, 1.0);
  float chop = ${glslNum(INLAND.chop.most)} * smoothstep(${INLAND.chop.speeds.map(glslNum).join(", ")}, length(v));
  Run run = runOf(p, v, ${glslNum(INLAND.cycle)});
  vec2 d0, d1;
  Waves s = wavesMix(swellOf(run.at.xy, h, chop, d0), swellOf(run.at.zw, h, chop, d1), run.w);
  return Inland(a, b, w.c, gd, inward, v, s, (d0 * run.w.x + d1 * run.w.y) * inversesqrt(dot(run.w, run.w)), murk);
}
float standingScore(vec2 q, vec2 flow) {
  const float S = ${glslNum(INLAND.falls.stand)};
  vec2 x = vec2(-flow.y, flow.x) * ${glslNum(INLAND.falls.across)} * S;
  float n = 0.0;
  for (int k = 0; k < 2; k++) {
    vec2 y = q + (k == 0 ? -x : x);
    n += gnoise(y / S) + 0.5 * gnoise(y / (0.45 * S) + 31.0);
  }
  return n / ${glslNum(STILL_SD)};
}
float dashesAt(vec2 q, vec2 u, float px) {
  const float CELL = ${glslNum(INLAND.falls.dash.cell)}, LONG = ${glslNum(INLAND.falls.dash.long)}, WIDE = ${glslNum(INLAND.falls.dash.wide)};
  float see = smoothstep(0.6, 1.6, WIDE * CELL / px);
  if (see <= 0.0) return 0.0;
  vec2 g = q / CELL, i = floor(g);
  float most = 0.0;
  for (int y = -1; y <= 1; y++) {
    for (int x = -1; x <= 1; x++) {
      vec2 c = i + vec2(float(x), float(y));
      float r = hash(c + 83.0);
      if (r < ${glslNum(1 - INLAND.falls.dash.keep)}) continue;
      float a = ${glslNum(INLAND.falls.dash.turn)} * (2.0 * hash(c + 19.0) - 1.0);
      vec2 w = mat2(cos(a), sin(a), -sin(a), cos(a)) * u, d = c + vec2(hash(c + 31.0), hash(c + 57.0)) - g;
      float e = length(vec2(dot(d, w) / LONG, dot(d, vec2(-w.y, w.x)) / WIDE));
      most = max(most, (1.0 - smoothstep(0.35, 1.0, e)) * (0.4 + 0.6 * r));
    }
  }
  return most * see;
}
vec2 whiteIn(Inland w, float meet) {
  return w.a.x < 0.0 ? vec2(0.0) : vec2(w.c.x, max(w.c.y, ${glslNum(INLAND.mouth.day.white)} * meet));
}
vec4 seaOut(vec2 p, Inland w, float sd) {
  float o = smoothstep(-8.0, 8.0, sd) * smoothstep(${INLAND.mouth.bands.wide.map(glslNum).join(", ")}, w.b.x);
  if (o <= 0.0) return vec4(0.0);
  const float AROUND = ${glslNum(INLAND.mouth.bands.around)};
  vec2 way = w.a.zw;
  for (int k = 0; k < 4; k++) {
    vec4 a, b;
    vec2 off = AROUND * vec2(k == 0 ? 1.0 : (k == 1 ? -1.0 : 0.0), k == 2 ? 1.0 : (k == 3 ? -1.0 : 0.0));
    if (inlandAt(p + off, a, b) && a.x >= 0.0) way += a.zw;
  }
  return vec4(o, max(sd, 0.0), way / 5.0);
}
vec2 whiteWater(vec2 p, float px, Inland w, vec2 wc, vec4 offshore) {
  const float CELL = ${glslNum(INLAND.falls.cell)}, EDDY = ${glslNum(INLAND.falls.eddy)}, LIFE = ${glslNum(INLAND.falls.life)};
  const float TOP = ${glslNum(+Math.log2(INLAND.falls.life / INLAND.falls.quick).toFixed(6))};
  const float STILL = ${glslNum(INLAND.falls.still)}, FLECK = ${glslNum(INLAND.falls.fleck)}, FLECKS = ${glslNum(INLAND.falls.flecks)};
  const float EVERY = ${glslNum(INLAND.mouth.bands.every)}, SPEED = ${glslNum(INLAND.mouth.bands.speed)};
  vec4 a = w.a;
  float o = offshore.x;
  float tau = fract(t / EVERY - offshore.y / (SPEED * EVERY) + noise(p / ${glslNum(INLAND.mouth.bands.hand)}));
  float band = mix(1.0, mix(${glslNum(INLAND.mouth.bands.low)}, 1.0, smoothstep(0.0, 0.1, tau) * pow(1.0 - tau, 1.5)), o);
  float white = wc.x * band, carried = wc.y * band, speed = runAt(a, w.b);
  vec2 u = length(a.zw) > 1e-3 ? normalize(a.zw) : vec2(0.0), d = a.zw * ${glslNum(INLAND.falls.streak)} * CELL;
  vec2 q = p - ${glslNum(INLAND.falls.bend.by)} * w.d;
  float l = clamp(log2(LIFE * max(speed, 1e-3) / EDDY), 0.0, TOP), i = floor(l);
  Run r0 = runOf(q, vec2(0.0), LIFE * exp2(-i)), r1 = runOf(q, vec2(0.0), LIFE * exp2(-i - 1.0)), rides = runOf(q, offshore.zw * SPEED, EVERY);
  vec2 f[8];
  for (int k = 0; k < 8; k++) {
    bool fleck = k < 4, moving = k >= 6;
    f[k] = vec2(0.5, 0.0);
    if ((fleck && white < 0.004) || (!fleck && !moving && o >= 1.0) || (moving && o <= 0.0)) continue;
    vec4 at = k < 2 ? r0.at : (k < 4 ? r1.at : rides.at);
    f[k] = fleck ? foamField(k % 2 == 0 ? at.xy : at.zw, FLECKS, px)
                 : foamField(moving ? (k == 6 ? at.xy : at.zw) : q + (k == 4 ? -d : d), CELL, px);
  }
  vec2 shape = fieldScore(fieldBlend(fieldBlend(f[4], f[5], vec2(0.5)), fieldBlend(f[6], f[7], rides.w), vec2(1.0 - o, o)));
  vec2 flecks = fieldScore(fieldBlend(fieldBlend(f[0], f[1], r0.w), fieldBlend(f[2], f[3], r1.w), vec2(1.0 - (l - i), l - i)));
  float st = STILL * (1.0 - o), still = white < 0.004 || o >= 1.0 ? 0.0 : standingScore(q, a.zw);
  float kc = ${glslNum(INLAND.falls.crumb)} * smoothstep(0.2, 0.8, white) * (1.0 - o);
  vec2 crumb = kc > 0.0 ? crumbAt(q, px) : vec2(0.0);
  float k2 = 1.0 + FLECK * FLECK + st * st + kc * kc;
  vec2 sc = vec2(shape.x + FLECK * flecks.x + st * still + kc * crumb.x,
                 shape.y + FLECK * FLECK * flecks.y + st * st + kc * kc * crumb.y) / vec2(sqrt(k2), k2);
  float running = smoothstep(0.2, 0.6, length(a.zw)) * (1.0 - o);
  float dash = carried < 0.004 || running <= 0.0 ? 0.0 : running * dashesAt(q, u, px);
  const vec2 RISE = vec2(${INLAND.falls.rise.map(glslNum).join(", ")});
  float cw = min(RISE.x * pow(white, RISE.y) * (1.0 + ${glslNum(INLAND.falls.bend.swell)} * w.s.h), ${glslNum(INLAND.falls.held)}), ct = ${glslNum(INLAND.falls.most)} * pow(carried, RISE.y);
  float foam = max(max(foamOf(sc, cw), foamOf(shape, ct)), ${glslNum(INLAND.falls.dash.most)} * dash * smoothstep(0.0, 0.5, carried));
  const vec2 REACH = vec2(${INLAND.falls.reach.map(glslNum).join(", ")});
  float churned = max(min(REACH.x * white, 1.0), REACH.y * carried);
  return vec2(foam, ${glslNum(INLAND.falls.air)} * churned * mix(${glslNum(INLAND.falls.marble)}, 1.0, smoothstep(-1.5, 1.5, max(sc.x, shape.x))));
}
vec2 mouthDay(vec2 p) {
  const float TOP = ${glslNum(1 - INLAND.mouth.day.top)};
  vec2 ring = vec2(cos(TAU * day), sin(TAU * day)), at = p / ${glslNum(INLAND.mouth.day.hand)};
  return vec2(smoothstep(0.25, 0.75, noise(at + ring * ${glslNum(INLAND.mouth.day.silt)})),
              smoothstep(TOP - 0.04, TOP + 0.04, noise(at + 37.0 + ring * ${glslNum(INLAND.mouth.day.wave)})));
}
float plumeAt(vec2 p, float sd, float share) {
  const float CELL = ${glslNum(INLAND.mouth.cell)}, SWIRL = ${glslNum(INLAND.mouth.swirl)};
  vec4 a, b;
  if (!inlandAt(p, a, b) || a.x < 0.0 || dot(a.zw, a.zw) < 0.0025 || share <= 0.0) return 0.0;
  Run run = runOf(p, a.zw * runAt(a, b), ${glslNum(INLAND.falls.life)});
  vec2 x0 = run.at.xy / CELL, x1 = run.at.zw / CELL;
  x0 += SWIRL * (vec2(noise(0.5 * x0 + 3.1), noise(0.5 * x0 + 7.7)) - 0.5);
  x1 += SWIRL * (vec2(noise(0.5 * x1 + 3.1), noise(0.5 * x1 + 7.7)) - 0.5);
  float n = noise(x0) * run.w.x + noise(x1) * run.w.y;
  float k = 1.0 - clamp(sd / (${glslNum(INLAND.mouth.reach)} * share), 0.0, 1.0);
  return min(length(a.zw), 1.0) * smoothstep(0.35, 0.65, k * (0.5 + n));
}
vec3 siltAt(vec2 p, Inland w, float sd) {
  vec2 u = length(w.a.zw) > 1e-3 ? normalize(w.a.zw) : vec2(0.0), at = p - u * (max(sd, 0.0) + ${glslNum(INLAND.mouth.up)});
  vec2 side = vec2(-u.y, u.x) * ${glslNum(INLAND.mouth.bank)};
  vec4 g = 0.5 * (groundAt(at + side) + groundAt(at - side));
  vec3 land = g.w > 0.0 ? g.rgb / g.w : vec3(0.0);
  return mix(vec3(${INLAND.mouth.silt.map(glslNum).join(", ")}), land, ${glslNum(INLAND.mouth.land)} * g.w * step(1e-3, length(u)));
}
vec4 inlandWater(vec2 p, float px, float litL, vec3 foamRgb, Vortex vt, Inland w, vec2 falls, vec4 silt) {
  float dep = w.a.y, depth = max(dep, 0.0);
  Waves s = w.s;
  vec3 N = normalize(vec3(-s.grad, 1.0));
  float wetness;
  float blue = max(smoothstep(${INLAND.colour.speeds.map(glslNum).join(", ")}, length(w.v)), min(falls.y / ${glslNum(INLAND.falls.air)}, 1.0));
  vec4 o = airOver(waterBase(p, depth, dep, falls.y, vt, litL, 0.0, 1.0, w.inward, w.gd, closeIn(px), vec4(1.0, blue, max(w.a.x, 0.0), w.murk), wetness), falls.y * wetness, litL);
  o.rgb = mix(o.rgb, silt.rgb * litL * o.a, silt.a);
  vec3 V;
  o = skyOver(o, p, N, s.h, wetness, 0.0, litL, V);
  o = foamGlint(o, foamRgb, falls.x * wetness, s, false, vec3(0.0), vec3(0.0), vec2(0.0), vt,
                ${glslNum(INLAND.swell.soft)}, ${glslNum(INLAND.swell.glass)} * (1.0 - min(length(w.v) / ${glslNum(INLAND.run)}, 1.0)), N, V,
                toward.z, max(toward.z, 0.02), wetness, px, litL);
  return o * (1.0 - smoothstep(0.3, 0.6, coverAt(p, vec4(0.0, 0.0, 0.0, w.b.z))));
}

void main() {
  vec2 p = (world * vec3(sp, 1.0)).xy;
  float px = ypx;
  vec2 uv = sp / size;
  sunNow = 1.0 - max(shadeOn == 1 ? textureLod(sunShade, uv, 0.0).r : 0.0, cloudOn == 1 ? textureLod(cloudShade, uv, 0.0).r * cloudShare : 0.0);
  float litL = dot(lit, vec3(0.299, 0.587, 0.114));
  vec3 foamRgb = vec3(clamp(pow(litL, 0.6) * 0.95, 0.0, 1.0));
  Vortex vt = vortexAt(p);
  float fade = seaOn == 0 ? 0.0 : 1.0 - smoothstep(5.0, FAR, px), bands = 0.0, air = 0.0, aired = 0.0, streaks = 0.0;
  if (vt.x < 1.0) {
    vec4 sf = swirlFoam(p, px, vt, mix(1.6, 1.0, fade), mix(0.95, 0.6, fade), wallsAt(vt) * (1.0 - fade));
    bands = sf.x * (1.0 - vt.eye * vt.eye);
    air = sf.y * (1.0 - vt.eye);
    streaks = sf.z;
    aired = sf.w;
  }
  vec4 swirl = fade < 1.0 ? swirlLayer(p, px, litL, foamRgb, vt, bands, air, aired) * (1.0 - fade) : vec4(0.0);
  if (seaOn == 0) { frag = swirl; return; }
  bool drawn;
  vec4 f = fieldAt(p, drawn);
  bool atSea = drawn && f.x >= -CUT;
  vec2 mouth = atSea ? mouthDay(p) : vec2(0.0);
  float plume = atSea ? plumeAt(p, f.x, mouth.x) : 0.0, offshore = atSea ? smoothstep(-8.0, 8.0, f.x) : 0.0;
  float seaward = atSea ? smoothstep(-30.0, -8.0, f.x) * (1.0 - plume) : 0.0;
  Inland iw = inlandOf(p);
  float wave = mouth.y * min(length(iw.a.zw), 1.0) * smoothstep(-3.0, 1.0, f.x) * (1.0 - smoothstep(0.5, 1.0, f.x / ${glslNum(INLAND.mouth.day.wide)}));
  vec2 wc = whiteIn(iw, wave);
  bool churns = max(wc.x, wc.y) >= 0.004, inlandDrawn = seaward < 1.0 && iw.a.y >= -1.5;
  if (churns || inlandDrawn) iw = inlandSurface(p, iw);
  vec2 falls = churns ? whiteWater(p, px, iw, wc, atSea ? seaOut(p, iw, f.x) : vec4(0.0)) : vec2(0.0);
  vec4 silt = plume > 0.0 ? vec4(siltAt(p, iw, f.x), ${glslNum(INLAND.mouth.tint)} * plume * offshore) : vec4(0.0);
  vec4 inland = inlandDrawn ? inlandWater(p, px, litL, foamRgb, vt, iw, falls, silt) * (1.0 - seaward) : vec4(0.0);
  if (!drawn || f.x < -CUT) { frag = over(swirl, inland * fade); return; }
  float sd = f.x, dep = f.y, depth = max(dep, 0.0), tau = f.z;
  float e = 2.0;
  vec4 fn = fieldAt(p + vec2(e, 0.0)), fs = fieldAt(p - vec2(e, 0.0)), fw = fieldAt(p + vec2(0.0, e)), fe = fieldAt(p - vec2(0.0, e));
  vec2 gt = vec2(fn.z - fs.z, fw.z - fe.z) / (2.0 * e);
  vec2 gd = vec2(fn.y - fs.y, fw.y - fe.y) / (2.0 * e);
  vec2 inward = length(gd) > 1e-4 ? -normalize(gd) : (length(gt) > 1e-4 ? -normalize(gt) : -windAt(p));
  vec2 gs = vec2(fn.x - fs.x, fw.x - fe.x) / (2.0 * e), away = length(gs) > 1e-4 ? normalize(gs) : vec2(0.0);
  vec2 shore = p - away * sd;
  float near = closeIn(px);
  vec2 st = steepAt(p, inward, dep);
  float steepSea = st.x, steepLand = st.y;
  float steep = max(steepLand, 0.7 * steepSea);
  vec2 paint = paintAt(p);
  float F = forceOf(paint, p), glass = paint.g;
  float churned = vt.x < 1.0 ? F + (churnedForce(currentSpeed(length(vt.d)), F) - F) * clamp(1.0 + 0.6 * streaks, 0.2, 2.0) : F;
  vec3 weigh = weightsAt(churned) * fetchAt(sd, windAt(p), away);
  float swellH = swellHere(paint, p), swellO = swellOpen(paint, p);

  vec3 bottom;
  bool calmer;
  Waves s = seaWaves(p, vt, F, weigh, depth, bottom, calmer);

  float period = swellT;
  float lam0 = g * period * period / TAU;
  float feel = 1.0 - smoothstep(0.2 * lam0, 0.5 * lam0, depth);
  vec2 swell = swellPhase(tau, shore);
  float ph = TAU * swell.x + 1.4 * s.h / max(rms, 1e-3);
  float u = fract(ph / TAU);
  float sets = clamp(swell.y + 0.35 * s.h0 / max(2.0 * rms, 1e-3), 0.25, 1.4);
  float shoal = pow(max(lam0 * 0.5, 0.5) / max(depth, 0.35), 0.25) * feel * sets;
  float crest = floor(ph / TAU);
  vec2 own = vec2(crestHeight(shore, crest), crestHeight(shore, crest + 1.0));
  vec2 steepK = own * swellO * shoal / max(depth, 0.05);
  float oneWay = smoothstep(0.3, 0.7, length(gt) * sqrt(g * clamp(depth, ${SEA.travel.map(glslNum).join(", ")})));
  vec2 lipK = smoothstep(${glslNum(SEA_CREST.lip[0])}, ${glslNum(SEA_CREST.lip[1])}, steepK) * oneWay;
  vec2 brokenK = smoothstep(${glslNum(SEA_CREST.broken[0])}, ${glslNum(SEA_CREST.broken[1])}, steepK) * feel * oneWay;
  float broken = mix(brokenK.x, brokenK.y, u);
  float H = min(swellH * shoal * mix(own.x, own.y, u), 0.78 * depth + 0.03);
  float sharp = mix(1.5, 6.0, clamp(H / max(depth, 0.05), 0.0, 1.0));
  float c = 0.5 + 0.5 * cos(ph);
  float k = TAU / max(sqrt(g * max(depth, 0.3)) * period, 1.0);
  float lines = 1.0 - 0.85 * steep;
  vec2 swellSlope = -inward * (-0.5 * H * sharp * pow(c, sharp - 1.0) * 0.5 * sin(ph) * k) * (1.0 - 0.6 * broken) * lines;
  float swellY = H * (pow(c, sharp) - 0.3) * lines;

  vec2 grad = s.grad + swellSlope + vt.fun.yz;
  vec3 N = normalize(vec3(-grad, 1.0));
  float height = s.h + swellY;
  float hid = smoothstep(0.1, 0.8, clamp(-vt.fun.x / DEEP, 0.0, 1.0));
  float facing = dot(normalize(vec3(-vt.fun.yz, 1.0)), toward), flatLit = max(toward.z, 0.02);
  float wall = clamp((max(facing, 0.0) + 0.02) / (max(toward.z, 0.0) + 0.02), 0.0, 1.6);
  wall = wall < 1.0 ? mix(0.3, 1.0, wall) : mix(1.0, 1.6, (wall - 1.0) / 0.6);
  if (vt.x < 1.0) sunNow *= smoothstep(-0.08, clamp(toward.z, -0.07, 0.02), facing);

  float wetness;
  vec4 o = waterBase(p, depth, dep, air * (aired - 0.3), vt, litL, hid, wall, inward, gd, near, vec4(0.0), wetness);
  vec3 V;
  o = skyOver(o, p, N, height, wetness, hid, litL, V);

  float caps = s.caps, lace = s.lace;
  float laced = mix(${glslNum(SEA_FOLD.laced)}, 1.0, lace);
  float line = smoothstep(0.88, 0.99, u) * lipK.y + smoothstep(0.06, 0.0, u) * lipK.x;
  float behind = exp(-u * 4.5) * smoothstep(0.0, 0.02, u) * brokenK.x;
  float white = smoothstep(0.0, ${glslNum(SEA_CREST.white)}, swellH);
  float surf = (1.0 - steepSea) * clamp(line * mix(0.3, 1.0, lace) + behind * laced * 0.8, 0.0, 1.0)
    * smoothstep(-0.1, 0.4, dep) * white;
  float hit = smoothstep(0.85, 1.0, u) + exp(-u * 4.0);
  float crash = mix(0.55, 1.0, max(steepSea, steepLand));
  float spray = crash * (1.0 - smoothstep(0.5, 2.5 + 9.0 * exp(-u * 3.0), sd + 1.0)) * min(1.6 * hit * sets, 1.0) * mix(0.5, 1.0, lace)
    * smoothstep(-0.6 * (0.4 + crash), 0.1, dep) * white;
  float foam = clamp(max(max(caps * laced * smoothstep(-0.1, 0.4, dep), surf), spray) + bands, 0.0, 0.95);
  o = airOver(o, 0.22 * clamp(behind * laced * white + spray, 0.0, 1.0) * wetness, litL);
  o = airOver(o, 0.35 * air * mix(0.4, 1.0, aired), litL);
  o = airOver(o, falls.y * wetness, litL);
  o = foamGlint(o, foamRgb, foam, s, calmer, weigh, bottom, swellSlope, vt, 0.0, glass, N, V, facing, flatLit, wetness, px, litL);
  o = over(vec4(vec3(${MAELSTROM.eyeRgb.map(glslNum).join(", ")}) * (0.5 + 0.5 * litL), 1.0) * vt.eye * (1.0 - 0.8 * bands), o);

  vec2 landed = swellPhase(0.0, shore);
  float sw = fract(landed.x + 1.4 * s.h / max(rms, 1e-3) / TAU);
  float run = sw < 0.3 ? smoothstep(0.0, 0.3, sw) : 1.0 - smoothstep(0.3, 1.0, sw);
  float reach = 0.45 * swellY * clamp(landed.y + 0.35 * s.h0 / max(2.0 * rms, 1e-3), 0.5, 1.2) * run;
  float up = -dep;
  float wet = smoothstep(reach + 0.25, reach - 0.05, up) * smoothstep(0.0, 0.1, up) * near * smoothstep(0.03, 0.2, reach);
  float front = exp(-pow((up - reach) / 0.06, 2.0)) * step(0.0, up) * near * laced * smoothstep(0.02, 0.15, reach);
  vec4 swash = over(vec4(foamRgb * front * 0.6, front * 0.6), vec4(0.0, 0.0, 0.0, wet * 0.14)) * (1.0 - steepLand);
  o = over(o, swash);

  float sprayNear = 1.0 - smoothstep(0.9, 2.2, px);
  if (sprayNear > 0.0 && abs(sd) < 12.0 && steep > 0.2) {
    vec2 sprayed = sprayAt(p, px) * sprayNear;
    o = over(vec4(foamRgb * sprayed.x, sprayed.x), over(vec4(0.0, 0.0, 0.0, sprayed.y), o));
  }

  float covered = coverAt(p, f);
  if (near > 0.0 && covered < 0.5) {
    float ring = 0.0;
    for (int i = 0; i < 4; i++) {
      vec2 dir = vec2(cos(float(i) * 1.5708), sin(float(i) * 1.5708)) * 1.2;
      vec2 q = p + dir;
      ring = max(ring, coverAt(q, fieldAt(q)));
    }
    float lap = smoothstep(0.3, 0.7, ring) * (1.0 - smoothstep(0.2, 0.5, covered)) * near * wetness
      * mix(0.35, 1.0, clamp(hit, 0.0, 1.0)) * mix(0.5, 1.0, lace) * smoothstep(0.0, 0.5, swellH) * 0.7;
    o = over(vec4(foamRgb * lap, lap), o);
  }
  o = over(vec4(foamRgb, 1.0) * falls.x * wetness, o);
  frag = over(swirl, (o * seaward * (1.0 - smoothstep(0.3, 0.6, covered)) + inland) * fade);
}`;

const SEA_GL = { alpha: true, premultipliedAlpha: true, preserveDrawingBuffer: true, antialias: false, depth: false, stencil: false };

function seaPixels(img) {
  if (typeof document === "undefined" || !img) return null;
  const c = document.createElement("canvas");
  Object.assign(c, { width: img.naturalWidth || img.width, height: img.naturalHeight || img.height });
  const g = c.getContext("2d", { willReadFrequently: true, colorSpace: "srgb" });
  g.drawImage(img, 0, 0);
  try { return { width: c.width, height: c.height, data: g.getImageData(0, 0, c.width, c.height).data }; } catch (e) { return null; }
}

class Sea {
  constructor({ canvas, bytes, drawn, context = (c) => c.getContext("webgl2", SEA_GL), now = () => performance.now(), picture = () => null,
    image = () => Promise.resolve(null), address, pixels = seaPixels }) {
    Object.assign(this, { canvas, bytes, drawn, context, now, picture, image, address, pixels });
    this.red = null;
    this.grounds = { kx: 0, ky: 0, ids: [] };
    this.covers = { kx: 0, ky: 0, ids: [] };
    this.gl = undefined;
    this.index = undefined;
    this.mask = null;
    this.files = new Map();
    this.inlandIndex = undefined;
    this.inlandFiles = new Map();
    this.asked = new Set();
    this.images = new Map();
    this.atlas = { kx: 0, ky: 0, ids: [], wet: [], widths: new Map(), firsts: new Map() };
    this.maskShown = null;
    this.spectra = null;
    this.held = null;
    this.fps = SEA.fps;
    this.ms = null;
    this.timed = false;
  }

  ready() {
    if (this.gl === undefined) this.gl = this.start();
    if (this.gl && this.build?.done() === false) this.gl = null;
    return !!this.gl;
  }

  built() {
    if (this.progs) return true;
    const made = this.build.done();
    if (!made) {
      if (made === null && !this.buildWaits) { this.buildWaits = true; this.build.whenDone(() => this.drawn()); }
      return false;
    }
    this.progs = Object.fromEntries(Object.entries(made).map(([name, prog]) => [name, { prog, u: new Map() }]));
    return true;
  }

  start() {
    const gl = this.context(this.canvas);
    if (!gl || !gl.getExtension("EXT_color_buffer_float")) return null;
    this.build = buildPrograms(gl, SEA_VERTEX, { spectrum: SEA_SPECTRUM, fft: SEA_FFT, surface: SEA_SURFACE, sea: SEA_FRAGMENT });
    gl.bindBuffer(gl.ARRAY_BUFFER, gl.createBuffer());
    gl.bufferData(gl.ARRAY_BUFFER, new Float32Array([-1, -1, 3, -1, -1, 3]), gl.STATIC_DRAW);
    gl.enableVertexAttribArray(0);
    gl.vertexAttribPointer(0, 2, gl.FLOAT, false, 0, 0);
    gl.pixelStorei(gl.UNPACK_ALIGNMENT, 1);
    const n = SEA.fft.n, tex = (format, filter, wrap) => {
      const t = gl.createTexture();
      gl.bindTexture(gl.TEXTURE_2D, t);
      gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MIN_FILTER, filter === "mip" ? gl.LINEAR_MIPMAP_LINEAR : filter);
      gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MAG_FILTER, filter === "mip" ? gl.LINEAR : filter);
      for (const k of [gl.TEXTURE_WRAP_S, gl.TEXTURE_WRAP_T]) gl.texParameteri(gl.TEXTURE_2D, k, wrap);
      if (format) gl.texStorage2D(gl.TEXTURE_2D, filter === "mip" ? Math.log2(n) + 1 : 1, format, n, n);
      return t;
    };
    gl.activeTexture(gl.TEXTURE0 + 15);
    this.tex = { field: tex(null, gl.LINEAR, gl.CLAMP_TO_EDGE), tags: tex(null, gl.NEAREST, gl.CLAMP_TO_EDGE),
      ground: tex(null, gl.LINEAR, gl.CLAMP_TO_EDGE), cover: tex(null, gl.LINEAR, gl.CLAMP_TO_EDGE), mask: tex(null, gl.LINEAR, gl.CLAMP_TO_EDGE),
      sunShade: tex(null, gl.LINEAR, gl.CLAMP_TO_EDGE), cloudShade: tex(null, gl.LINEAR, gl.CLAMP_TO_EDGE),
      inland: tex(null, gl.LINEAR, gl.CLAMP_TO_EDGE) };
    this.ping = [tex(gl.RGBA32F, gl.NEAREST, gl.REPEAT), tex(gl.RGBA32F, gl.NEAREST, gl.REPEAT)];
    this.cascades = SEA.fft.sizes.map(() => ({ h0: tex(gl.RGBA32F, gl.NEAREST, gl.REPEAT),
      shape: tex(gl.RGBA16F, "mip", gl.REPEAT), slope: tex(gl.RGBA16F, "mip", gl.REPEAT) }));
    this.lake = { shape: tex(gl.RGBA16F, "mip", gl.REPEAT), slope: tex(gl.RGBA16F, "mip", gl.REPEAT) };
    this.fb = gl.createFramebuffer();
    this.most = gl.getParameter(gl.MAX_TEXTURE_SIZE);
    return gl;
  }

  use(name) {
    const gl = this.gl, p = this.progs[name];
    gl.useProgram(p.prog);
    return (u) => {
      if (!p.u.has(u)) p.u.set(u, gl.getUniformLocation(p.prog, u));
      return p.u.get(u);
    };
  }

  bind(unit, t) {
    const gl = this.gl;
    gl.activeTexture(gl.TEXTURE0 + unit);
    gl.bindTexture(gl.TEXTURE_2D, t);
  }

  target(...textures) {
    const gl = this.gl, n = SEA.fft.n;
    gl.bindFramebuffer(gl.FRAMEBUFFER, this.fb);
    const at = [gl.COLOR_ATTACHMENT0, gl.COLOR_ATTACHMENT1];
    textures.forEach((t, i) => gl.framebufferTexture2D(gl.FRAMEBUFFER, at[i], gl.TEXTURE_2D, t, 0));
    if (textures.length < 2) gl.framebufferTexture2D(gl.FRAMEBUFFER, at[1], gl.TEXTURE_2D, null, 0);
    gl.drawBuffers(at.slice(0, textures.length));
    gl.viewport(0, 0, n, n);
  }

  simulate(t) {
    const gl = this.gl, n = SEA.fft.n, stages = Math.log2(n);
    if (!this.spectra) {
      this.spectra = waveSpectra(SEA.force);
      this.cascades.forEach((c, i) => {
        this.bind(0, c.h0);
        gl.texSubImage2D(gl.TEXTURE_2D, 0, 0, 0, n, n, gl.RGBA, gl.FLOAT, this.spectra.spectra[i]);
      });
    }
    const { cascade, slow, stretch } = INLAND.swell, lake = { ...this.cascades[cascade], ...this.lake };
    [...this.cascades.map((c, i) => [c, SEA.fft.sizes[i], t]), [lake, SEA.fft.sizes[cascade] * stretch, t * slow]].forEach(([c, L, at]) => {
      let u = this.use("spectrum");
      this.bind(0, c.h0);
      gl.uniform1i(u("h0"), 0);
      gl.uniform1f(u("t"), at);
      gl.uniform1f(u("L"), L);
      gl.uniform1f(u("g"), SEA.g);
      gl.uniform1i(u("n"), n);
      this.target(this.ping[0]);
      gl.drawArrays(gl.TRIANGLES, 0, 3);
      u = this.use("fft");
      gl.uniform1i(u("n"), n);
      gl.uniform1i(u("src"), 0);
      let from = 0;
      for (const horizontal of [1, 0]) {
        gl.uniform1i(u("horizontal"), horizontal);
        for (let s = 0; s < stages; s++) {
          this.bind(0, this.ping[from]);
          this.target(this.ping[1 - from]);
          gl.uniform1i(u("ns"), 1 << s);
          gl.drawArrays(gl.TRIANGLES, 0, 3);
          from = 1 - from;
        }
      }
      u = this.use("surface");
      this.bind(0, this.ping[from]);
      gl.uniform1i(u("src"), 0);
      gl.uniform1i(u("n"), n);
      gl.uniform1f(u("L"), L);
      this.target(c.shape, c.slope);
      gl.drawArrays(gl.TRIANGLES, 0, 3);
      for (const tx of [c.shape, c.slope]) {
        this.bind(0, tx);
        gl.generateMipmap(gl.TEXTURE_2D);
      }
    });
    gl.bindFramebuffer(gl.FRAMEBUFFER, null);
  }

  asked1(name, url, read) {
    if (this[name] !== undefined) return this[name];
    this[name] = null;
    Promise.resolve(this.bytes(url)).then((buf) => {
      let got = {};
      try { got = JSON.parse(new TextDecoder().decode(buf)); } catch (e) { got = {}; }
      this[name] = read(got);
      this.drawn();
    });
    return null;
  }

  has(instance, key, store = "sea") {
    const { index, url } = SEA_STORES[store];
    const got = this.asked1(index, url, (read) => new Set(Object.entries(read.instances || {}).flatMap(([i, keys]) => keys.map((k) => `${i}/${k}`))));
    return !!got?.has(`${instance}/${key}`);
  }

  setMask(index) {
    const world = index?.world, url = world?.stamp ? this.address("/api/seamask/world.png", world.stamp) : null;
    if (this.mask && this.mask.url !== url) this.images.delete(this.mask.url);
    this.mask = url ? { ...world, url } : null;
  }

  picked(url) {
    const got = this.images.get(url);
    if (got) return got.img ?? null;
    const held = {};
    this.images.set(url, held);
    Promise.resolve(this.image(url)).then((img) => img, () => null).then((img) => {
      held.img = img || null;
      this.drawn();
    });
    return null;
  }

  want(instance, key, store = "sea") {
    const { url, files, decode } = SEA_STORES[store], id = `${instance}/${key}`, file = `${url}/${id}.bin`, kept = this[files];
    if (kept.has(id) || this.asked.has(file)) return;
    this.asked.add(file);
    Promise.resolve(this.bytes(file)).then((buf) => decode(buf), () => null).then((got) => {
      this.asked.delete(file);
      kept.set(id, got);
      this.drawn();
    });
  }

  slotPicture(which, tex, kx, ky, px, at2, sx, sy, tag, img, format) {
    const gl = this.gl, a = this[which];
    if (a.kx !== kx || a.ky !== ky) {
      this.bind(0, this.tex[tex]);
      gl.texImage2D(gl.TEXTURE_2D, 0, format, kx * px, ky * px, 0, format === gl.RGBA8 ? gl.RGBA : gl.ALPHA, gl.UNSIGNED_BYTE, null);
      this[which] = { kx, ky, ids: new Array(kx * ky).fill(null) };
    }
    if (!img || img.naturalWidth !== px || img.naturalHeight !== px) return false;
    if (this[which].ids[at2] !== tag) {
      this.bind(0, this.tex[tex]);
      gl.texSubImage2D(gl.TEXTURE_2D, 0, sx * px, sy * px, format === gl.RGBA8 ? gl.RGBA : gl.ALPHA, gl.UNSIGNED_BYTE, img);
      this[which].ids[at2] = tag;
    }
    return true;
  }

  placeMask() {
    const img = this.mask ? this.picked(this.mask.url) : null;
    if (img && this.maskShown !== this.mask.url) {
      const gl = this.gl;
      this.bind(0, this.tex.mask);
      gl.pixelStorei(gl.UNPACK_COLORSPACE_CONVERSION_WEBGL, gl.NONE);
      gl.texImage2D(gl.TEXTURE_2D, 0, gl.RG8, gl.RG, gl.UNSIGNED_BYTE, img);
      gl.pixelStorei(gl.UNPACK_COLORSPACE_CONVERSION_WEBGL, gl.BROWSER_DEFAULT_WEBGL);
      this.maskShown = this.mask.url;
    }
    return !!this.mask && this.maskShown !== null;
  }

  layoutSlots(instances, boxes) {
    const a = this.atlas, S = SEA.side, widths = new Map(a.widths);
    instances.forEach((inst, i) => widths.set(inst, Math.max(widths.get(inst) || 0, boxes[i][2] - boxes[i][0] + 1)));
    const ky = Math.max(a.ky, 1, ...boxes.map((b) => b[3] - b[1] + 1));
    if (ky === a.ky && [...widths].every(([inst, w]) => a.widths.get(inst) === w)) return true;
    let kx = 0;
    const firsts = new Map();
    for (const inst of [...widths.keys()].sort((x, y) => x - y)) { firsts.set(inst, kx); kx += widths.get(inst); }
    if (kx * S > this.most || 3 * ky * S > this.most) return false;
    const gl = this.gl;
    this.bind(0, this.tex.field);
    gl.texImage2D(gl.TEXTURE_2D, 0, gl.RGBA16F, kx * S, ky * S, 0, gl.RGBA, gl.HALF_FLOAT, null);
    this.bind(0, this.tex.inland);
    gl.texImage2D(gl.TEXTURE_2D, 0, gl.RGBA16F, kx * S, 3 * ky * S, 0, gl.RGBA, gl.HALF_FLOAT, null);
    Object.assign(a, { kx, ky, ids: new Array(kx * ky).fill(null), wet: new Array(kx * ky).fill(null), widths, firsts });
    return true;
  }

  placeOver(tex, over) {
    if (!over) return false;
    this.sent ||= {};
    if (this.sent[tex] !== over.made) {
      const gl = this.gl;
      this.bind(0, this.tex[tex]);
      gl.pixelStorei(gl.UNPACK_COLORSPACE_CONVERSION_WEBGL, gl.NONE);
      gl.texImage2D(gl.TEXTURE_2D, 0, gl.RGBA, gl.RGBA, gl.UNSIGNED_BYTE, over.canvas);
      gl.pixelStorei(gl.UNPACK_COLORSPACE_CONVERSION_WEBGL, gl.BROWSER_DEFAULT_WEBGL);
      this.sent[tex] = over.made;
    }
    return true;
  }

  paint({ instance, rendered, tileYards, at, width, height, light, t, hours = 0, day = 0.5, shade = null, clouds = null, middle = null,
    onWorld = null, ground = null, circles = [] }) {
    if (!(width > 0) || !(height > 0) || !(tileYards > 0)) return false;
    const frame = viewMatrix(at, width, height), ypx = Math.hypot(frame[0], frame[1]);
    this.ypx = ypx;
    const parts = ground || [{ instance, rendered, place: [1, 1, 0, 0], rect: [0, 0, 1, 1] }];
    const corners = [[0, 0], [width, 0], [0, height], [width, height]].map(([x, y]) => at(x, y));
    const spot = onWorld ? worldPlace(onWorld) : null, eye = spot && swirlEye(spot), swirl = !!eye && swirlShown(corners, eye);
    const open = ypx <= SEA.far;
    if ((!open && !swirl) || !this.ready() || !this.built()) return false;
    this.fps = open ? SEA.fps : MAELSTROM.fps;
    const gl = this.gl, S = SEA.side, most = this.most;
    const boxes = open ? parts.map((g) => seaBox(corners.map((p) => placedAt(g.place, p)), tileYards)) : [];
    if (open && !this.layoutSlots(parts.map((g) => g.instance), boxes)) return false;
    const { kx, ky } = this.atlas;
    const G = SEA.groundPx, close = ypx <= SEA.groundUntil && kx * G <= most && ky * G <= most;
    const tags = new Float32Array(Math.max(1, kx * ky) * 4);
    let any = false;
    boxes.forEach(([c0, r0, c1, r1], i) => {
      const { instance: inst, rendered: drawn, hidden = () => false } = parts[i], first = this.atlas.firsts.get(inst), wide = this.atlas.widths.get(inst);
      for (let r = r0; r <= r1; r++) {
        for (let c = c0; c <= c1; c++) {
          const key = `${c}_${r}`, has = this.has(inst, key);
          if (has) this.want(inst, key);
          const file = has ? this.files.get(`${inst}/${key}`) : null;
          const kind = hidden(key) ? 0 : seaKind(has, drawn(key), !!file), sx = first + (c % wide), sy = r % ky, at2 = sy * kx + sx, tag = tagOf(inst, c, r);
          if (kind === 1 && this.atlas.ids[at2] !== tag) {
            this.bind(0, this.tex.field);
            gl.texSubImage2D(gl.TEXTURE_2D, 0, sx * S, sy * S, S, S, gl.RGBA, gl.HALF_FLOAT, file.fours);
            this.atlas.ids[at2] = tag;
          }
          const wet = !hidden(key) && this.has(inst, key, "inland");
          if (wet) this.want(inst, key, "inland");
          const lake = wet ? this.inlandFiles.get(`${inst}/${key}`) : null, holds = lake ? tag : 0;
          if (this.atlas.wet[at2] !== holds) {
            this.dry ||= new Uint16Array(S * S * 4).fill(INLAND.dry);
            this.bind(0, this.tex.inland);
            gl.texSubImage2D(gl.TEXTURE_2D, 0, sx * S, sy * S, S, S, gl.RGBA, gl.HALF_FLOAT, lake ? lake.fours : this.dry);
            if (lake) {
              gl.texSubImage2D(gl.TEXTURE_2D, 0, sx * S, (ky + sy) * S, S, S, gl.RGBA, gl.HALF_FLOAT, lake.more);
              gl.texSubImage2D(gl.TEXTURE_2D, 0, sx * S, (2 * ky + sy) * S, S, S, gl.RGBA, gl.HALF_FLOAT, lake.white);
            }
            this.atlas.wet[at2] = holds;
          }
          const near = close && (kind === 1 || !!lake);
          const shown = near && this.slotPicture("grounds", "ground", kx, ky, G, at2, sx, sy, tag, this.picture(inst, key), gl.RGBA8);
          const covered = near && this.slotPicture("covers", "cover", kx, ky, G, at2, sx, sy, tag, this.picked(`/rendershape/${inst}/${key}.png`), gl.ALPHA);
          tags.set([tag, kind, shown ? 1 : 0, covered ? 1 : 0], at2 * 4);
          any ||= kind > 0 || !!lake;
        }
      }
    });
    if (!any && !swirl) return false;
    if (open && (!this.tags || this.tags.length !== tags.length || tags.some((v, i) => v !== this.tags[i]))) {
      this.bind(1, this.tex.tags);
      gl.texImage2D(gl.TEXTURE_2D, 0, gl.RGBA32F, kx, ky, 0, gl.RGBA, gl.FLOAT, tags);
      this.tags = tags;
    }
    const masked = !!spot && this.placeMask(), shaded = this.placeOver("sunShade", shade), clouded = this.placeOver("cloudShade", clouds);
    const t0 = this.now();
    this.simulate(t);
    const w = Math.max(1, Math.round(width * SEA.scale)), h = Math.max(1, Math.round(height * SEA.scale));
    if (this.canvas.width !== w || this.canvas.height !== h) Object.assign(this.canvas, { width: w, height: h });
    const m = middle || { x: width / 2, y: height / 2 };
    const mid = at(m.x + SEA.eyeShift[0] * width, m.y + SEA.eyeShift[1] * width), sp = this.spectra, u = this.use("sea");
    gl.viewport(0, 0, w, h);
    gl.clearColor(0, 0, 0, 0);
    gl.clear(gl.COLOR_BUFFER_BIT);
    this.bind(0, this.tex.field);
    this.bind(1, this.tex.tags);
    gl.uniform1i(u("field"), 0);
    gl.uniform1i(u("tags"), 1);
    this.bind(8, this.tex.ground);
    gl.uniform1i(u("ground"), 8);
    this.bind(9, this.tex.cover);
    gl.uniform1i(u("cover"), 9);
    this.bind(13, this.tex.inland);
    gl.uniform1i(u("inland"), 13);
    const lake = INLAND.swell.cascade, turn = SEA.fft.turns[lake];
    this.bind(14, this.lake.shape);
    this.bind(15, this.lake.slope);
    gl.uniform1i(u("lakeShape"), 14);
    gl.uniform1i(u("lakeSlope"), 15);
    const { stretch } = INLAND.swell;
    gl.uniform4f(u("cascLake"), SEA.fft.sizes[lake] * stretch, Math.cos(turn), Math.sin(turn), this.spectra.slopes[lake] / stretch ** 2);
    gl.uniform2f(u("offLake"), ...SEA.fft.offsets[lake]);
    this.bind(10, this.tex.mask);
    gl.uniform1i(u("mask"), 10);
    gl.uniform1i(u("maskOn"), masked ? 1 : 0);
    gl.uniform4f(u("spotAt"), ...(spot || [0, 0, 0, 0]));
    gl.uniform1i(u("parts"), Math.min(parts.length, 2));
    const two = (f, n) => [0, 1].flatMap((i) => (parts[i] ? f(parts[i]) : new Array(n).fill(0)));
    gl.uniform1fv(u("insts"), new Float32Array(two((g) => [g.instance], 1)));
    gl.uniform4fv(u("places"), new Float32Array(two((g) => g.place, 4)));
    gl.uniform4fv(u("rects"), new Float32Array(two((g) => g.rect, 4)));
    gl.uniform2iv(u("blocks"), new Int32Array(two((g) => [this.atlas.firsts.get(g.instance) ?? 0, this.atlas.widths.get(g.instance) || 1], 2)));
    gl.uniform3f(u("mael"), ...(eye ? [eye.n, eye.w, MAELSTROM.radius] : [0, 0, 0]));
    gl.uniform1i(u("seaOn"), open ? 1 : 0);
    const fronts = seaFronts(hours);
    gl.uniform4fv(u("frontAt"), new Float32Array(fronts.flatMap((f) => f.at)));
    gl.uniform3fv(u("frontRun"), new Float32Array(fronts.flatMap((f) => [...f.along, f.weight])));
    this.cascades.forEach((c, i) => {
      this.bind(2 + i, c.shape);
      this.bind(5 + i, c.slope);
      gl.uniform1i(u(`shape${i}`), 2 + i);
      gl.uniform1i(u(`slope${i}`), 5 + i);
      const a = SEA.fft.turns[i];
      gl.uniform4f(u(`casc${i}`), SEA.fft.sizes[i], Math.cos(a), Math.sin(a), sp.slopes[i]);
      gl.uniform2f(u(`off${i}`), ...SEA.fft.offsets[i]);
    });
    gl.uniform3f(u("cascH"), ...sp.heights);
    gl.uniform3f(u("cascL"), ...sp.lengths);
    if (this.held?.px !== ypx) this.held = { px: ypx, shares: seaHeld(sp.slopeWaves, ypx), wide: null };
    gl.uniform3f(u("held"), ...this.held.shares);
    if (swirl && open && !this.held.wide) this.held.wide = SEA_HELD_WIDE.flatMap((k) => seaHeld(sp.slopeWaves, k * ypx));
    gl.uniform3fv(u("heldWide"), new Float32Array(this.held.wide || SEA_HELD_WIDE.flatMap(() => [0, 0, 0])));
    gl.uniform2f(u("size"), width, height);
    gl.uniform2i(u("slots"), Math.max(kx, 1), Math.max(ky, 1));
    gl.uniform1f(u("T"), tileYards);
    gl.uniform1f(u("t"), t);
    gl.uniform1f(u("day"), day);
    gl.uniform1f(u("gustAt"), t);
    gl.uniform1f(u("ypx"), ypx);
    gl.uniform1f(u("eyeUp"), SEA.eye * width * ypx);
    gl.uniform1f(u("night"), light.night);
    gl.uniform1f(u("choppy"), SEA.choppy);
    gl.uniform1f(u("rms"), sp.rms);
    gl.uniform1f(u("hs"), sp.hs);
    gl.uniform1f(u("swellT"), seaSwell(SEA.force).period);
    gl.uniform1f(u("g"), SEA.g);
    gl.uniformMatrix3fv(u("world"), false, new Float32Array(frame));
    gl.uniform3f(u("toward"), ...light.toward);
    gl.uniform3f(u("glintL"), ...light.toward);
    gl.uniform3f(u("lit"), ...light.lit);
    this.bind(11, this.tex.sunShade);
    this.bind(12, this.tex.cloudShade);
    gl.uniform1i(u("sunShade"), 11);
    gl.uniform1i(u("cloudShade"), 12);
    gl.uniform1i(u("shadeOn"), shaded ? 1 : 0);
    gl.uniform1i(u("cloudOn"), clouded ? 1 : 0);
    gl.uniform1f(u("cloudShare"), clouds ? clouds.share : 0);
    gl.uniform3f(u("glintRgb"), ...light.glint);
    const turning = circles.slice(0, 2).map((c) => seaCircle(c.circle, c.place, tileYards));
    gl.uniform4fv(u("circles"), new Float32Array([0, 1].flatMap((i) => turning[i] || [0, 0, 0, 0])));
    gl.uniform2f(u("centre"), mid.n, mid.w);
    gl.uniform1f(u("glintK"), light.glintK);
    gl.uniform2f(u("crispL"), ...(light.moon ? SEA_LIGHT.moonCrisp : SEA_LIGHT.crisp));
    gl.uniform1f(u("mergeL"), seaMerge(ypx));
    gl.uniform2f(u("coreL"), ...SEA_LIGHT.core);
    gl.uniform2f(u("sunwardL"), SEA_SKY.sunward, SEA_SKY.sunwardPow);
    gl.uniform1f(u("axisL"), SEA_LIGHT.axis);
    gl.uniform1f(u("lostL"), SEA_LIGHT.lostShare);
    gl.uniform1f(u("lowMostL"), SEA_LIGHT.lowMost);
    gl.uniform2f(u("tipsL"), SEA_LIGHT.tips[1], SEA_LIGHT.tips[2]);
    gl.uniform1f(u("tipsK"), light.tips);
    gl.uniform3f(u("skyLowL"), SEA_SKY.low[0], SEA_SKY.low[1], SEA_SKY.sparkle);
    gl.uniform2f(u("skyFadeL"), ...SEA_SKY.fade);
    gl.drawArrays(gl.TRIANGLES, 0, 3);
    if (this.timed) {
      gl.readPixels(0, 0, 1, 1, gl.RGBA, gl.UNSIGNED_BYTE, new Uint8Array(4));
      this.ms = +(this.now() - t0).toFixed(2);
    }
    return true;
  }

  maskPixels() {
    const img = this.mask ? this.picked(this.mask.url) : null;
    if (!img) return null;
    if (this.red?.url !== this.mask.url) {
      const px = this.pixels(img);
      this.red = px ? { url: this.mask.url, ...px } : null;
    }
    return this.red;
  }

  stormIn({ at, onWorld, width, height, circles = [], tileYards, grid, from, level }) {
    const frame = viewMatrix(at, width, height), ypx = Math.hypot(frame[0], frame[1]);
    const spot = onWorld ? worldPlace(onWorld) : null, eye = spot && swirlEye(spot), red = spot ? this.maskPixels() : null;
    const value = (p) => {
      if (!spot) return 0;
      let paint = 0;
      if (red) {
        const [across, down] = onWorld(p.n, p.w);
        const x = Math.min(red.width - 1, Math.max(0, Math.floor(across * red.width))), y = Math.min(red.height - 1, Math.max(0, Math.floor(down * red.height)));
        paint = red.data[(y * red.width + x) * 4] / 255;
      }
      return seaStorm(paint, Math.hypot(p.n - eye.n, p.w - eye.w));
    };
    const [gx, gy] = grid, values = [];
    for (let j = 0; j < gy; j++) for (let i = 0; i < gx; i++) values.push(value(at(((i + 0.5) / gx) * width, ((j + 0.5) / gy) * height)));
    const corners = [[0, 0], [width, 0], [0, height], [width, height]].map(([x, y]) => at(x, y));
    const maelstrom = eye && swirlShown(corners, eye) ? { eye, radius: MAELSTROM.radius } : null;
    const turning = circles.slice(0, 2).map((c) => seaCircle(c.circle, c.place, tileYards));
    const wind = seaWind(at(width / 2, height / 2), turning), storm = level(values);
    return { values, level: storm, any: values.some((v) => v >= from), maelstrom, frame, ypx, wind, windYards: beaufortWind(seaWeather(storm, 0)) };
  }

  drawOn(ctx, w, h) {
    ctx.drawImage(this.canvas, 0, 0, w, h);
  }
}

if (typeof module === "object") {
  module.exports = { SEA, SEA_LIGHT, SEA_GLASS, SEA_WEATHER, SEA_GROW, SEA_SPRAY, SEA_SKY, MAELSTROM, swirlShare, swirlHeldParts, swirlHeld, swirlFlow, swirlAt, swirlBack, laceThin, swirlDepth, swirlFunnel, swirlBend, seaBlocked, swirlEye, seaPlace,
    smoothHour,
    placedAt, swirlShown, decodeSea, INLAND, FOAM, foamSums, STILL_SD, inlandRun, inlandChop, inlandChurn, inlandSwell, decodeInland, SEA_STORES, halfToFloat, seaBox, seaKind, seaLight,
    beaufortWind, seaTable, seaWeather, seaForce, seaStorm, seaPixels, worldPlace, frameAt, seaFronts, seaWeights, seaSun, sprayDrop, glslTable, seeded, normals, phillips,
    waveIndex, waveSpectra, SEA_SWELL, seaSwell, seaSwellPhase, SEA_WIND, seaCircle, seaWind, seaFetch, seaSwellAt, SEA_CREST, seaCrestHeight, seaFormed, SEA_FOLD, seaWhitecaps,
    normalDensity, normalCdf, normalQuantile, seaShoal, seaBreaking, seaCapsRule, seaFold, seaHeld, SEA_HELD_WIDE, seaMerge, seaLobeLight, SEA_VERTEX, SEA_SPECTRUM, SEA_FFT, SEA_SURFACE, SEA_FRAGMENT, Sea };
}
