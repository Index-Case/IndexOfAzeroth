// The Index of Azeroth. Copyright 2026 Index Case <indexofazeroth@pm.me>. PolyForm Strict 1.0.0, see LICENSE.md.
"use strict";

const CONTOUR = { ladder: [2, 5, 10, 20, 50, 100, 200, 500, 1000], perPx: 10, grow: 0.75, fifth: 5, width: 1, indexWidth: 1.6, alpha: 0.85, indexAlpha: 1,
  least: 4, cellPx: 2, push: 1.6, blur: 1.5, rings: 3 };

function contourTaps(rings = CONTOUR.rings) {
  const out = [[0, 0, 1]];
  for (let k = 1; k <= rings; k++) {
    const d = k / rings, n = 6 * k, w = +Math.exp(-2 * d * d).toFixed(5);
    for (let i = 0; i < n; i++) {
      const a = (2 * Math.PI * (i + (k % 2) / 2)) / n;
      out.push([+(d * Math.cos(a)).toFixed(5), +(d * Math.sin(a)).toFixed(5), w]);
    }
  }
  return out;
}
const CONTOUR_TAPS = contourTaps();

const contourGap = (ypx) => CONTOUR.ladder.find((g) => g >= CONTOUR.perPx * ypx ** CONTOUR.grow) ?? CONTOUR.ladder.at(-1);

function contourStride(n, tileYards, ypx) {
  let s = 1;
  while (2 * s <= n - 1 && (2 * s * tileYards) / (n - 1) <= CONTOUR.cellPx * ypx) s *= 2;
  return s;
}

function contourPoints(heights, kinds, n, base, step, stride) {
  const m = (n - 1) / stride + 1, out = new Float32Array(2 * m * m);
  for (let j = 0; j < m; j++) {
    for (let i = 0; i < m; i++) {
      const p = j * stride * n + i * stride;
      out.set([base + step * heights[p], kinds[p] === KIND.water ? 1 : 0], 2 * (j * m + i));
    }
  }
  return out;
}

function contourMatrix(push = CONTOUR.push) {
  const k = +push.toFixed(4), c = +((1 + push) / 2).toFixed(4);
  return [-k, 0, 0, 0, c, 0, -k, 0, 0, c, 0, 0, -k, 0, c, 0, 0, 0, 1, 0];
}

const CONTOUR_FRAGMENT = `#version 300 es
precision highp float;
precision highp int;
uniform highp sampler2D hg;
uniform highp sampler2D tags;
uniform ivec2 slots;
uniform int side;
uniform float inst, T, gap, least, blur;
uniform mat3 world;
uniform vec4 look;
in vec2 sp;
out vec4 frag;

bool ground(vec2 w, out vec2 h) {
  vec2 t = vec2(32.0 - w.y / T, 32.0 - w.x / T);
  ivec2 cr = ivec2(floor(t));
  h = vec2(0.0);
  if (cr.x < 0 || cr.y < 0 || cr.x > 63 || cr.y > 63) return false;
  ivec2 s = ivec2(cr.x % slots.x, cr.y % slots.y);
  vec4 tag = texelFetch(tags, s, 0);
  if (tag.x != (inst * 64.0 + float(cr.x)) * 64.0 + float(cr.y) + 1.0) return false;
  vec2 f = (t - vec2(cr)) * (tag.y - 1.0);
  ivec2 i = min(ivec2(floor(f)), ivec2(int(tag.y) - 2));
  vec2 r = f - vec2(i);
  ivec2 o = s * side + i;
  vec2 a = texelFetch(hg, o, 0).rg, b = texelFetch(hg, o + ivec2(1, 0), 0).rg;
  vec2 c = texelFetch(hg, o + ivec2(0, 1), 0).rg, d = texelFetch(hg, o + ivec2(1, 1), 0).rg;
  h = mix(mix(a, b, r.x), mix(c, d, r.x), r.y);
  return true;
}

float smoothed(vec2 w, float own) {
  const vec3 TAPS[${CONTOUR_TAPS.length}] = vec3[${CONTOUR_TAPS.length}](${CONTOUR_TAPS.map((t) => `vec3(${t.map(glFloat).join(", ")})`).join(", ")});
  float sum = 0.0, all = 0.0;
  vec2 h;
  for (int i = 0; i < ${CONTOUR_TAPS.length}; i++) {
    float hit = ground(w + blur * TAPS[i].xy, h) ? TAPS[i].z : 0.0;
    sum += hit * h.x;
    all += hit;
  }
  return all > 0.0 ? sum / all : own;
}

void main() {
  vec2 h, w = (world * vec3(sp, 1.0)).xy;
  bool on = ground(w, h);
  float f = smoothed(w, h.x) / gap, g = length(vec2(dFdx(f), dFdy(f)));
  float k = floor(f + 0.5), apart = 1.0 / max(g, 1e-6);
  bool index = mod(k, ${glFloat(CONTOUR.fifth)}) == 0.0;
  float wide = index ? look.y : look.x;
  float a = clamp(0.5 * wide + 0.5 - abs(f - k) * apart, 0.0, 1.0);
  a *= smoothstep(0.5 * least, least, index ? ${glFloat(CONTOUR.fifth)} * apart : apart) * (index ? look.w : look.z) * (1.0 - h.y);
  frag = on && g > 1e-5 ? vec4(a) : vec4(0.0);
}`;

const CONTOUR_UNIFORMS = ["size", "hg", "tags", "slots", "side", "inst", "T", "gap", "least", "blur", "world", "look"];
const CONTOUR_TEXTURES = ["hg", "tags"];

class Contours {
  constructor({ light, canvas, drawn, context = (c) => c.getContext("webgl2", RELIEF_GL) }) {
    Object.assign(this, { light, canvas, drawn, context });
    this.gl = undefined;
    this.atlas = null;
    this.shown = null;
    this.made = new WeakMap();
    this.ids = new WeakMap();
    this.fileCount = 0;
  }

  ready() {
    if (this.gl === undefined) this.gl = this.start();
    if (this.gl && this.build.done() === false) this.gl = null;
    return !!this.gl;
  }

  start() {
    const gl = this.context(this.canvas);
    if (!gl) return null;
    this.build = buildPrograms(gl, RELIEF_VERTEX, { contours: CONTOUR_FRAGMENT });
    gl.bindBuffer(gl.ARRAY_BUFFER, gl.createBuffer());
    gl.bufferData(gl.ARRAY_BUFFER, new Float32Array([-1, -1, 3, -1, -1, 3]), gl.STATIC_DRAW);
    gl.enableVertexAttribArray(0);
    gl.vertexAttribPointer(0, 2, gl.FLOAT, false, 0, 0);
    gl.pixelStorei(gl.UNPACK_ALIGNMENT, 1);
    this.most = gl.getParameter(gl.MAX_TEXTURE_SIZE);
    this.tex = {};
    CONTOUR_TEXTURES.forEach((name, unit) => {
      gl.activeTexture(gl.TEXTURE0 + unit);
      const t = gl.createTexture();
      gl.bindTexture(gl.TEXTURE_2D, t);
      for (const k of [gl.TEXTURE_MIN_FILTER, gl.TEXTURE_MAG_FILTER]) gl.texParameteri(gl.TEXTURE_2D, k, gl.NEAREST);
      for (const k of [gl.TEXTURE_WRAP_S, gl.TEXTURE_WRAP_T]) gl.texParameteri(gl.TEXTURE_2D, k, gl.CLAMP_TO_EDGE);
      this.tex[name] = t;
    });
    return gl;
  }

  built() {
    if (this.u) return true;
    const made = this.build.done(), gl = this.gl;
    if (!made) {
      if (made === null && !this.waits) { this.waits = true; this.build.whenDone(() => this.drawn()); }
      return false;
    }
    gl.useProgram(made.contours);
    this.u = Object.fromEntries(CONTOUR_UNIFORMS.map((name) => [name, gl.getUniformLocation(made.contours, name)]));
    CONTOUR_TEXTURES.forEach((name, unit) => gl.uniform1i(this.u[name], unit));
    return true;
  }

  points(file, stride) {
    const heights = groundLayer(file).heights;
    if (!this.made.has(heights)) this.made.set(heights, {});
    const kept = this.made.get(heights);
    return (kept[stride] ||= contourPoints(heights, file.kinds, file.n, file.base, file.step, stride));
  }

  idOf(file) {
    if (!this.ids.has(file)) this.ids.set(file, this.fileCount++);
    return this.ids.get(file);
  }

  place(gl, instance, tiles) {
    const span = (k) => Math.max(...tiles.map((t) => t[k])) - Math.min(...tiles.map((t) => t[k])) + 1;
    const side = Math.max(...tiles.map((t) => t.m)), a0 = this.atlas;
    const kx = Math.max(span("c"), a0 && a0.side === side ? a0.kx : 0), ky = Math.max(span("r"), a0 && a0.side === side ? a0.ky : 0);
    if (kx * side > this.most || ky * side > this.most) return false;
    if (!a0 || a0.side !== side || a0.kx !== kx || a0.ky !== ky) {
      gl.activeTexture(gl.TEXTURE0);
      gl.texImage2D(gl.TEXTURE_2D, 0, gl.RG32F, kx * side, ky * side, 0, gl.RG, gl.FLOAT, null);
      this.atlas = { kx, ky, side, held: new Array(kx * ky).fill(null), tags: new Float32Array(4 * kx * ky) };
    }
    const a = this.atlas;
    let changed = a !== a0;
    for (const t of tiles) {
      const [sx, sy] = slotOf(t.c, t.r, a.kx, a.ky), at = sy * a.kx + sx, points = this.points(t.file, t.stride);
      if (a.held[at] === points) continue;
      gl.activeTexture(gl.TEXTURE0);
      gl.texSubImage2D(gl.TEXTURE_2D, 0, sx * side, sy * side, t.m, t.m, gl.RG, gl.FLOAT, points);
      a.held[at] = points;
      a.tags.set([tagOf(instance, t.c, t.r), t.m, 0, 0], 4 * at);
      changed = true;
    }
    if (changed) {
      gl.activeTexture(gl.TEXTURE1);
      gl.texImage2D(gl.TEXTURE_2D, 0, gl.RGBA32F, a.kx, a.ky, 0, gl.RGBA, gl.FLOAT, a.tags);
    }
    return true;
  }

  paint({ instance, has, tileYards, at, width, height, dpr = 1 }) {
    if (!this.ready() || !this.built() || !(width > 0) || !(height > 0)) return false;
    const gl = this.gl, world = viewMatrix(at, width, height), ypx = Math.hypot(world[0], world[1]), far = ypx >= RELIEF.farPx;
    const corners = [[0, 0], [width, 0], [0, height], [width, height]].map(([x, y]) => at(x, y));
    const tiles = reliefTiles(corners, tileYards, 0, has).map((key) => {
      const [c, r] = key.split("_").map(Number), file = this.light.tileFile(instance, c, r, far);
      const stride = file && contourStride(file.n, tileYards, ypx);
      return file && { c, r, file, stride, m: (file.n - 1) / stride + 1 };
    }).filter(Boolean);
    const w = Math.max(1, Math.round(width * dpr)), h = Math.max(1, Math.round(height * dpr)), gap = contourGap(ypx);
    const view = JSON.stringify([instance, world.map((v) => +v.toFixed(5)), w, h, gap, tiles.map((t) => [t.c, t.r, t.stride, this.idOf(t.file)])]);
    if (view === this.shown) return true;
    if (tiles.length && !this.place(gl, instance, tiles)) return false;
    this.shown = view;
    if (this.canvas.width !== w || this.canvas.height !== h) Object.assign(this.canvas, { width: w, height: h });
    gl.viewport(0, 0, w, h);
    gl.clearColor(0, 0, 0, 0);
    gl.clear(gl.COLOR_BUFFER_BIT);
    if (!tiles.length) return true;
    const u = this.u, k = w / width;
    gl.uniform2f(u.size, width, height);
    gl.uniform2i(u.slots, this.atlas.kx, this.atlas.ky);
    gl.uniform1i(u.side, this.atlas.side);
    gl.uniform1f(u.inst, instance);
    gl.uniform1f(u.T, tileYards);
    gl.uniform1f(u.gap, gap);
    gl.uniform1f(u.blur, CONTOUR.blur * gap);
    gl.uniform1f(u.least, CONTOUR.least * k);
    gl.uniformMatrix3fv(u.world, false, new Float32Array(world));
    gl.uniform4f(u.look, CONTOUR.width * k, CONTOUR.indexWidth * k, CONTOUR.alpha, CONTOUR.indexAlpha);
    gl.drawArrays(gl.TRIANGLES, 0, 3);
    return true;
  }

  drawOn(ctx, w, h, beside = [], box = null) {
    const own = beside.length ? (g, k) => { g.rect(-1e6, -1e6, 2e6, 2e6); beside.forEach((b) => b.part(g, k)); } : null;
    this.light.parted(ctx, 1, own, () => this.lay(ctx, w, h, box));
    for (const b of beside) this.light.parted(ctx, 1, b.part, () => b.lines.lay(ctx, w, h, box));
  }

  lay(ctx, w, h, box) {
    const id = this.light.colourFilter(`contours-${Math.round(CONTOUR.push * 100)}`, contourMatrix());
    if (!id) return;
    const g = this.light.copyOf(ctx, "contours", `url(#${id})`, box);
    clipBox(g, box, () => {
      g.globalCompositeOperation = "destination-in";
      g.drawImage(this.canvas, 0, 0, g.canvas.width, g.canvas.height);
      g.globalCompositeOperation = "source-over";
    });
    clipBox(ctx, box, () => ctx.drawImage(g.canvas, 0, 0, w, h));
  }
}

if (typeof module === "object") {
  module.exports = { CONTOUR, contourGap, contourStride, contourPoints, contourMatrix, contourTaps, CONTOUR_TAPS, CONTOUR_FRAGMENT, CONTOUR_UNIFORMS, CONTOUR_TEXTURES, Contours };
}
