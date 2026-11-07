// The Index of Azeroth. Copyright 2026 Index Case <indexofazeroth@pm.me>. PolyForm Strict 1.0.0, see LICENSE.md.
"use strict";

const MODEL_DIR = "models/";
const MODEL_LIGHT = [-0.45, 0.55, 0.7];
const MODEL_AMBIENT = 0.62, MODEL_DIFFUSE = 0.55;
const ALPHA_KEY = 1, ALPHA_BLEND = 2;
const UNLIT = 0x1, NO_DEPTH_WRITE = 0x10;

function loadModel(name) {
  return askFor(`model:${name}`, async () => {
    const data = await getJson(`${MODEL_DIR}${name}.json`, { key: null });
    const images = {};
    await Promise.all([...new Set(data.batches.map((b) => b.texture))].map((file) => new Promise((done, fail) => {
      const img = new Image();
      img.onload = () => done(images[file] = img);
      img.onerror = () => fail(new Error(`${file} didn't load`));
      img.src = MODEL_DIR + file;
    })));
    return { name, data, images };
  });
}

function sampleTrack(track, t, fallback) {
  if (!track) return fallback;
  const { times, values, loop } = track, n = times.length;
  if (n === 1 || !loop) return values[0];
  const at = t % loop;
  if (at <= times[0]) return values[0];
  if (at >= times[n - 1]) return values[n - 1];
  let lo = 0, hi = n - 1;
  while (hi - lo > 1) { const mid = (lo + hi) >> 1; if (times[mid] <= at) lo = mid; else hi = mid; }
  const a = values[lo];
  if (!track.linear) return a;
  const b = values[hi], f = (at - times[lo]) / (times[hi] - times[lo]);
  if (a.length === 4) {
    const s = a[0] * b[0] + a[1] * b[1] + a[2] * b[2] + a[3] * b[3] < 0 ? -1 : 1;
    const q = a.map((v, i) => v + (s * b[i] - v) * f), len = Math.hypot(...q) || 1;
    return q.map((v) => v / len);
  }
  return a.map((v, i) => v + (b[i] - v) * f);
}

function poseBones(bones, t) {
  const out = new Array(bones.length);
  bones.forEach((bone, i) => {
    const [tx, ty, tz] = sampleTrack(bone.t, t, [0, 0, 0]);
    const [x, y, z, w] = sampleTrack(bone.r, t, [0, 0, 0, 1]);
    const [sx, sy, sz] = sampleTrack(bone.s, t, [1, 1, 1]);
    const r = [1 - 2 * (y * y + z * z), 2 * (x * y + z * w), 2 * (x * z - y * w),
               2 * (x * y - z * w), 1 - 2 * (x * x + z * z), 2 * (y * z + x * w),
               2 * (x * z + y * w), 2 * (y * z - x * w), 1 - 2 * (x * x + y * y)];
    const m = [r[0] * sx, r[1] * sx, r[2] * sx, r[3] * sy, r[4] * sy, r[5] * sy, r[6] * sz, r[7] * sz, r[8] * sz];
    const [px, py, pz] = bone.pivot;
    const local = [...m, px + tx - (m[0] * px + m[3] * py + m[6] * pz), py + ty - (m[1] * px + m[4] * py + m[7] * pz),
                   pz + tz - (m[2] * px + m[5] * py + m[8] * pz)];
    const p = bone.parent >= 0 ? out[bone.parent] : null;
    out[i] = p ? [
      p[0] * local[0] + p[3] * local[1] + p[6] * local[2], p[1] * local[0] + p[4] * local[1] + p[7] * local[2], p[2] * local[0] + p[5] * local[1] + p[8] * local[2],
      p[0] * local[3] + p[3] * local[4] + p[6] * local[5], p[1] * local[3] + p[4] * local[4] + p[7] * local[5], p[2] * local[3] + p[5] * local[4] + p[8] * local[5],
      p[0] * local[6] + p[3] * local[7] + p[6] * local[8], p[1] * local[6] + p[4] * local[7] + p[7] * local[8], p[2] * local[6] + p[5] * local[7] + p[8] * local[8],
      p[0] * local[9] + p[3] * local[10] + p[6] * local[11] + p[9], p[1] * local[9] + p[4] * local[10] + p[7] * local[11] + p[10],
      p[2] * local[9] + p[5] * local[10] + p[8] * local[11] + p[11]] : local;
  });
  return out;
}

function skin(d, mats, pos, nrm) {
  const P = d.positions, N = d.normals, B = d.boneIndices, W = d.boneWeights;
  for (let v = 0, n = P.length / 3; v < n; v++) {
    const x = P[3 * v], y = P[3 * v + 1], z = P[3 * v + 2], nx = N[3 * v], ny = N[3 * v + 1], nz = N[3 * v + 2];
    let ox = 0, oy = 0, oz = 0, qx = 0, qy = 0, qz = 0, total = 0;
    for (let k = 0; k < 4; k++) {
      const w = W[4 * v + k];
      if (!w) continue;
      const m = mats[B[4 * v + k]], f = w / 255;
      total += f;
      ox += f * (m[0] * x + m[3] * y + m[6] * z + m[9]);
      oy += f * (m[1] * x + m[4] * y + m[7] * z + m[10]);
      oz += f * (m[2] * x + m[5] * y + m[8] * z + m[11]);
      qx += f * (m[0] * nx + m[3] * ny + m[6] * nz);
      qy += f * (m[1] * nx + m[4] * ny + m[7] * nz);
      qz += f * (m[2] * nx + m[5] * ny + m[8] * nz);
    }
    if (!total) { ox = x; oy = y; oz = z; qx = nx; qy = ny; qz = nz; }
    pos[3 * v] = ox; pos[3 * v + 1] = oy; pos[3 * v + 2] = oz;
    nrm[3 * v] = qx; nrm[3 * v + 1] = qy; nrm[3 * v + 2] = qz;
  }
}

function viewTurn(yaw, pitch) {
  const a = (yaw * Math.PI) / 180, b = (pitch * Math.PI) / 180, ca = Math.cos(a), sa = Math.sin(a), cb = Math.cos(b), sb = Math.sin(b);
  const base = [[0, 1, 0], [0, 0, 1], [1, 0, 0]];
  const yawM = [[ca, 0, sa], [0, 1, 0], [-sa, 0, ca]];
  const pitchM = [[1, 0, 0], [0, cb, -sb], [0, sb, cb]];
  const mul = (A, B) => A.map((row) => [0, 1, 2].map((j) => row[0] * B[0][j] + row[1] * B[1][j] + row[2] * B[2][j]));
  return mul(pitchM, mul(yawM, base));
}

const MODEL_VS = `#version 300 es
in vec3 aPos; in vec3 aNrm; in vec2 aUv;
uniform mat3 uTurn; uniform vec4 uFrame; uniform vec2 uDepth;
out vec3 vNrm; out vec2 vUv;
void main() {
  vec3 p = uTurn * aPos;
  vNrm = uTurn * aNrm; vUv = aUv;
  gl_Position = vec4((p.x - uFrame.x) / uFrame.z * 2.0 - 1.0, (p.y - uFrame.y) / uFrame.w * 2.0 - 1.0,
                     (uDepth.x - p.z) / uDepth.y * 2.0 - 1.0, 1.0);
}`;
const MODEL_FS = `#version 300 es
precision mediump float;
in vec3 vNrm; in vec2 vUv;
uniform sampler2D uTex; uniform vec3 uLight; uniform float uAlpha, uKey; uniform bool uLit, uBlend;
out vec4 color;
void main() {
  vec4 c = texture(uTex, vUv);
  if (c.a < uKey) discard;
  vec3 n = normalize(vNrm) * (gl_FrontFacing ? 1.0 : -1.0);
  float light = uLit ? ${MODEL_AMBIENT.toFixed(2)} + ${MODEL_DIFFUSE.toFixed(2)} * max(dot(n, uLight), 0.0) : 1.0;
  vec3 rgb = uBlend ? c.rgb : c.rgb / max(c.a, 0.004);
  vec3 lit = min(rgb * light, vec3(uBlend ? c.a : 1.0));
  color = vec4(lit * uAlpha, (uBlend ? c.a : 1.0) * uAlpha);
}`;

class ModelView {
  constructor(model, { yaw = 0, pitch = 0 } = {}) {
    this.model = model;
    this.yaw = yaw; this.pitch = pitch;
    this.turn = viewTurn(yaw, pitch);
    this.canvas = document.createElement("canvas");
    this.canvas.className = "model-view";
    const gl = this.canvas.getContext("webgl2", { alpha: true, premultipliedAlpha: true, antialias: true });
    if (!gl) throw new Error("no WebGL2");
    this.gl = gl;
    const d = model.data, count = d.positions.length / 3;
    this.pos = new Float32Array(count * 3);
    this.nrm = new Float32Array(count * 3);
    this.frameBox = this.measure();
    this.aspect = this.frameBox.w / this.frameBox.h;
    this.moving = d.bones.some((b) => [b.t, b.r, b.s].some((tr) => tr && tr.times.length > 1));
    const shader = (type, src) => {
      const s = gl.createShader(type);
      gl.shaderSource(s, src);
      gl.compileShader(s);
      if (!gl.getShaderParameter(s, gl.COMPILE_STATUS)) throw new Error(gl.getShaderInfoLog(s));
      return s;
    };
    const prog = gl.createProgram();
    gl.attachShader(prog, shader(gl.VERTEX_SHADER, MODEL_VS));
    gl.attachShader(prog, shader(gl.FRAGMENT_SHADER, MODEL_FS));
    gl.linkProgram(prog);
    if (!gl.getProgramParameter(prog, gl.LINK_STATUS)) throw new Error(gl.getProgramInfoLog(prog));
    this.prog = prog;
    this.u = Object.fromEntries(["uTurn", "uFrame", "uDepth", "uTex", "uLight", "uAlpha", "uKey", "uLit", "uBlend"]
      .map((n) => [n, gl.getUniformLocation(prog, n)]));
    const buffer = (data, loc, size) => {
      const b = gl.createBuffer();
      gl.bindBuffer(gl.ARRAY_BUFFER, b);
      gl.bufferData(gl.ARRAY_BUFFER, data, data === this.pos || data === this.nrm ? gl.DYNAMIC_DRAW : gl.STATIC_DRAW);
      gl.enableVertexAttribArray(loc);
      gl.vertexAttribPointer(loc, size, gl.FLOAT, false, 0, 0);
      return b;
    };
    this.vao = gl.createVertexArray();
    gl.bindVertexArray(this.vao);
    this.posBuf = buffer(this.pos, gl.getAttribLocation(prog, "aPos"), 3);
    this.nrmBuf = buffer(this.nrm, gl.getAttribLocation(prog, "aNrm"), 3);
    buffer(new Float32Array(d.uvs), gl.getAttribLocation(prog, "aUv"), 2);
    const ib = gl.createBuffer();
    gl.bindBuffer(gl.ELEMENT_ARRAY_BUFFER, ib);
    gl.bufferData(gl.ELEMENT_ARRAY_BUFFER, new Uint16Array(d.indices), gl.STATIC_DRAW);
    gl.bindVertexArray(null);
    this.textures = {};
    for (const b of d.batches) {
      if (this.textures[b.texture]) continue;
      const t = gl.createTexture();
      gl.bindTexture(gl.TEXTURE_2D, t);
      gl.pixelStorei(gl.UNPACK_PREMULTIPLY_ALPHA_WEBGL, true);
      gl.texImage2D(gl.TEXTURE_2D, 0, gl.RGBA, gl.RGBA, gl.UNSIGNED_BYTE, model.images[b.texture]);
      gl.generateMipmap(gl.TEXTURE_2D);
      gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MIN_FILTER, gl.LINEAR_MIPMAP_LINEAR);
      gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_WRAP_S, b.wrap & 1 ? gl.REPEAT : gl.CLAMP_TO_EDGE);
      gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_WRAP_T, b.wrap & 2 ? gl.REPEAT : gl.CLAMP_TO_EDGE);
      this.textures[b.texture] = t;
    }
  }

  measure() {
    const d = this.model.data, T = this.turn;
    const loops = d.bones.flatMap((b) => [b.t, b.r, b.s]).filter(Boolean).map((tr) => tr.loop || 0);
    const span = Math.min(10000, Math.max(0, ...loops)), steps = span ? 64 : 1;
    let side = 0, low = Infinity, high = -Infinity, near = -Infinity, far = Infinity;
    for (let i = 0; i < steps; i++) {
      skin(d, poseBones(d.bones, (span * i) / steps), this.pos, this.nrm);
      for (let v = 0; v < this.pos.length; v += 3) {
        const x = this.pos[v], y = this.pos[v + 1], z = this.pos[v + 2];
        const vx = T[0][0] * x + T[0][1] * y + T[0][2] * z, vy = T[1][0] * x + T[1][1] * y + T[1][2] * z;
        const vz = T[2][0] * x + T[2][1] * y + T[2][2] * z;
        side = Math.max(side, Math.abs(vx));
        low = Math.min(low, vy); high = Math.max(high, vy);
        near = Math.max(near, vz); far = Math.min(far, vz);
      }
    }
    const pad = (high - low) * 0.02;
    return { x: -side - pad, y: low - pad, w: 2 * (side + pad), h: high - low + 2 * pad, near: near + 1, depth: near - far + 2 };
  }

  spin(yaw) {
    this.stood ??= { turn: this.turn, frameBox: this.frameBox, aspect: this.aspect };
    this.frameBox = this.spinFrame();
    this.aspect = this.frameBox.w / this.frameBox.h;
    this.turn = viewTurn(yaw, this.pitch);
  }
  unspin() {
    if (!this.stood) return;
    ({ turn: this.turn, frameBox: this.frameBox, aspect: this.aspect } = this.stood);
    this.stood = null;
  }
  spinFrame() {
    if (!this.spinBox) {
      const keep = this.turn, boxes = [];
      for (let k = 0; k < 16; k++) {
        this.turn = viewTurn(this.yaw + k * 22.5, this.pitch);
        boxes.push(this.measure());
      }
      this.turn = keep;
      const side = Math.max(...boxes.map((b) => -b.x)), low = Math.min(...boxes.map((b) => b.y));
      const high = Math.max(...boxes.map((b) => b.y + b.h)), near = Math.max(...boxes.map((b) => b.near));
      const far = Math.min(...boxes.map((b) => b.near - b.depth));
      this.spinBox = { x: -side, y: low, w: 2 * side, h: high - low, near, depth: near - far };
    }
    return this.spinBox;
  }

  size(width, height) {
    const r = window.devicePixelRatio || 1, w = Math.max(1, Math.round(width * r)), h = Math.max(1, Math.round(height * r));
    this.canvas.style.width = `${width}px`;
    this.canvas.style.height = `${height}px`;
    if (this.canvas.width !== w || this.canvas.height !== h) {
      this.canvas.width = w;
      this.canvas.height = h;
    }
  }

  draw(t) {
    const gl = this.gl, d = this.model.data, u = this.u, f = this.frameBox, T = this.turn;
    skin(d, poseBones(d.bones, t), this.pos, this.nrm);
    gl.viewport(0, 0, this.canvas.width, this.canvas.height);
    gl.clearColor(0, 0, 0, 0);
    gl.clear(gl.COLOR_BUFFER_BIT | gl.DEPTH_BUFFER_BIT);
    gl.useProgram(this.prog);
    gl.bindVertexArray(this.vao);
    gl.bindBuffer(gl.ARRAY_BUFFER, this.posBuf);
    gl.bufferSubData(gl.ARRAY_BUFFER, 0, this.pos);
    gl.bindBuffer(gl.ARRAY_BUFFER, this.nrmBuf);
    gl.bufferSubData(gl.ARRAY_BUFFER, 0, this.nrm);
    gl.uniformMatrix3fv(u.uTurn, false, [T[0][0], T[1][0], T[2][0], T[0][1], T[1][1], T[2][1], T[0][2], T[1][2], T[2][2]]);
    gl.uniform4f(u.uFrame, f.x, f.y, f.w, f.h);
    gl.uniform2f(u.uDepth, f.near, f.depth);
    const len = Math.hypot(...MODEL_LIGHT);
    gl.uniform3f(u.uLight, ...MODEL_LIGHT.map((v) => v / len));
    gl.uniform1i(u.uTex, 0);
    gl.activeTexture(gl.TEXTURE0);
    gl.enable(gl.DEPTH_TEST);
    gl.disable(gl.CULL_FACE);
    for (const b of d.batches) {
      const blended = b.blend >= ALPHA_BLEND;
      gl.bindTexture(gl.TEXTURE_2D, this.textures[b.texture]);
      gl.uniform1f(u.uAlpha, b.alpha);
      gl.uniform1f(u.uKey, b.blend === ALPHA_KEY ? 0.878 : blended ? 0.004 : -1);
      gl.uniform1i(u.uLit, b.flags & UNLIT ? 0 : 1);
      gl.uniform1i(u.uBlend, blended ? 1 : 0);
      if (blended) {
        gl.enable(gl.BLEND);
        gl.blendFunc(gl.ONE, gl.ONE_MINUS_SRC_ALPHA);
      } else {
        gl.disable(gl.BLEND);
      }
      gl.depthMask(!(blended && b.flags & NO_DEPTH_WRITE));
      gl.drawElements(gl.TRIANGLES, b.count, gl.UNSIGNED_SHORT, b.start * 2);
    }
    gl.depthMask(true);
    gl.bindVertexArray(null);
  }
}
