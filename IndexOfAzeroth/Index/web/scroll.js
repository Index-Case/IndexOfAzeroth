// The Index of Azeroth. Copyright 2026 Index Case <indexofazeroth@pm.me>. PolyForm Strict 1.0.0, see LICENSE.md.
"use strict";


const SCROLL_ART = ["art/scroll.png", "art/scroll_moving1.png", "art/scroll_moving2.png", "art/scroll_moving3.png"];
const SCROLL_SHAPE = {
  rollers: { left: 0.1625, top: 0.057, right: 0.8285, bottom: 0.9485 },
  landing: { y: 0.215, left: 0.33, right: 0.67 },
  page: { left: 0.27, top: 0.25, right: 0.73, bottom: 0.79 },
  caption: { top: 0.855, bottom: 0.905 },
};
const SCROLL_COVER = 0.95;
const SCROLL_GAP = 16;
const SCROLL_LINES = 20;
const SCROLL_LINE = 1.45;

function scrollPlace(W, H, view = { l: 0, r: W, t: 0, b: H }) {
  const R = SCROLL_SHAPE.rollers;
  const free = Math.max(0, view.r - view.l - 2 * SCROLL_GAP), tall = Math.max(0, view.b - view.t);
  const size = Math.max(0, Math.min(SCROLL_COVER * tall / (R.bottom - R.top), free / (R.right - R.left)));
  const x = (view.l + view.r) / 2 - size * (R.left + R.right) / 2, y = (view.t + view.b) / 2 - size * (R.top + R.bottom) / 2;
  const box = (b) => ({ left: x + b.left * size, top: y + b.top * size, right: x + b.right * size, bottom: y + b.bottom * size });
  const L = SCROLL_SHAPE.landing, page = box(SCROLL_SHAPE.page), font = (page.bottom - page.top) / (SCROLL_LINES * SCROLL_LINE);
  return { x, y, size, rollers: box(R), page, font, lines: size > 0 ? SCROLL_LINES : 0,
           landing: { x: x + size * (L.left + L.right) / 2, y: y + L.y * size, half: size * (L.right - L.left) / 2 } };
}

function scrollFrame(showing, random) {
  const others = [1, 2, 3].filter((k) => k !== showing);
  return others[Math.min(others.length - 1, Math.floor(random() * others.length))];
}
const SCROLL_SWITCH = [35, 70];
const SCROLL_SHAKE = { x: 1.6, y: 1.1, turn: 0.18 };
function scrollShake(random) {
  const way = (most) => +((random() * 2 - 1) * most).toFixed(2);
  return `translate(${way(SCROLL_SHAKE.x)}px, ${way(SCROLL_SHAKE.y)}px) rotate(${way(SCROLL_SHAKE.turn)}deg)`;
}


const HOSE = { lift: 0.045, out: 0.08, over: 0.3, drop: 0.12, appear: 0.04, margin: 0.18, round: 0.22, points: 64 };

function arrowPlace(p, r) {
  const beside = Math.max(r.left - p.x, p.x - r.right, 0), up = r.top - p.y, down = p.y - r.bottom;
  if (!beside && up <= 0 && down <= 0) return "under";
  if (up > 0 && up >= beside) return "above";
  if (down > 0 && down >= beside) return "below";
  return p.x < r.left ? "left" : "right";
}

function pullIn(p, to, W, H, margin) {
  const lo = [-margin, -margin], hi = [W + margin, H + margin];
  let k = 1;
  ["x", "y"].forEach((a, i) => {
    const d = p[a] - to[a];
    if (p[a] < lo[i]) k = Math.min(k, (lo[i] - to[a]) / d);
    if (p[a] > hi[i]) k = Math.min(k, (hi[i] - to[a]) / d);
  });
  return { x: to.x + (p.x - to.x) * k, y: to.y + (p.y - to.y) * k };
}

function hoseCurve(controls, n) {
  const out = [];
  for (let k = 0; k <= n; k++) {
    const t = k / n;
    let p = controls;
    while (p.length > 1) p = p.slice(1).map((q, i) => [p[i][0] + (q[0] - p[i][0]) * t, p[i][1] + (q[1] - p[i][1]) * t]);
    out.push(p[0]);
  }
  return out;
}

function hoseControls(from, at, W, H) {
  const r = at.rollers, e = [at.landing.x, at.landing.y], w = r.right - r.left;
  const place = from ? arrowPlace(from, r) : "under";
  if (place === "under") return { place, controls: [[e[0], e[1] - HOSE.appear * H], e] };
  const p = pullIn(from, at.landing, W, H, HOSE.margin * H), s = [p.x, p.y], top = r.top - HOSE.lift * H;
  if (place === "above") return { place, controls: [s, [s[0], s[1] + (e[1] - s[1]) / 2], [e[0], e[1] - HOSE.drop * H], e] };
  const side = place === "left" || (place === "below" && s[0] < e[0]) ? -1 : 1, down = [e[0] + side * HOSE.over * w, top];
  if (place === "below") {
    const round = side < 0 ? r.left - HOSE.round * w : r.right + HOSE.round * w;
    return { place, controls: [s, [round, s[1]], [round, (r.top + r.bottom) / 2], [round, top], down, e] };
  }
  const outX = side < 0 ? r.left - HOSE.out * w : r.right + HOSE.out * w;
  const lean = (side < 0 ? s[0] < outX : s[0] > outX) ? (s[0] + outX) / 2 : outX;
  return { place, controls: [s, [lean, Math.min(s[1], top)], down, e] };
}

function hosePath(from, at, W, H) {
  const { place, controls } = hoseControls(from, at, W, H);
  return { place, line: hoseCurve(controls, HOSE.points) };
}

function hoseLengths(line) {
  const out = [0];
  for (let k = 1; k < line.length; k++) out.push(out[k - 1] + Math.hypot(line[k][0] - line[k - 1][0], line[k][1] - line[k - 1][1]));
  return out;
}

function hoseAt(line, lengths, u) {
  const total = lengths[lengths.length - 1], want = Math.min(1, Math.max(0, u)) * total;
  let lo = 0, hi = lengths.length - 1;
  while (hi - lo > 1) {
    const mid = (lo + hi) >> 1;
    if (lengths[mid] <= want) lo = mid; else hi = mid;
  }
  const a = line[lo], b = line[hi], span = lengths[hi] - lengths[lo], t = span > 0 ? (want - lengths[lo]) / span : 0;
  const len = Math.hypot(b[0] - a[0], b[1] - a[1]) || 1;
  return { x: a[0] + (b[0] - a[0]) * t, y: a[1] + (b[1] - a[1]) * t, dx: (b[0] - a[0]) / len, dy: (b[1] - a[1]) / len };
}

const STREAM_RATE = [60, 260], STREAM_FULL = 600, STREAM_SPEED = 820, STREAM_TIME = [0.45, 1.7];
const STREAM_MOST = 420, STREAM_WAITING = 1500;
const STREAM_FOLLOW = 18;
const STREAM_FONT = 16, STREAM_BLUR = 2.6;
const streamRate = (waiting) => STREAM_RATE[0] + (STREAM_RATE[1] - STREAM_RATE[0]) * Math.min(1, waiting / STREAM_FULL);
const streamTime = (length) => Math.min(STREAM_TIME[1], Math.max(STREAM_TIME[0], length / STREAM_SPEED));
const streamAlpha = (u, length) => Math.min(1, u * length / 60, (1 - u) / 0.12);
const STREAM_COLOURS = ["quality-poor", "white", "quality-uncommon", "quality-rare", "quality-epic", "quality-legendary"];
const streamColour = (q) => STREAM_COLOURS[q] || "forever-cream";


function scrollLine(a) {
  const name = esc(a.name || word("page.auction-scroll.item", { id: a.item })), stack = a.count > 1 ? `${num(a.count)} ` : "";
  const price = a.unit > 0 ? (a.count > 1 ? word("page.auction-scroll.each", { price: money(a.unit) }) : money(a.unit))
    : a.bid > 0 ? word("page.auction-scroll.bid", { price: money(a.bid) }) : "";
  return `<div class="ah-line"><span class="ah-name">${stack}${name}</span><span class="ah-price">${price}</span></div>`;
}
function scrollCaption(b) {
  if (b.waiting) return word("page.auction-scroll.caption.waiting");
  if (b.state === "asking") return word("page.auction-scroll.caption.asking");
  return b.total ? word("page.auction-scroll.caption.count", { n: num(b.received || 0), total: num(b.total) })
    : word("page.auction-scroll.caption.scanning");
}
function scrollEnded(b) {
  const n = num(b.received || 0);
  if (b.state === "done" && b.complete) return word("page.auction-scroll.ended.done", { n });
  if (b.state === "failed") return word("page.auction-scroll.ended.failed");
  if (b.state === "interrupted") return word("page.auction-scroll.ended.cut", { n });
  return word("page.auction-scroll.ended.stopped", { n });
}

const SCROLL_LEAVE_MS = 600;
const SCROLL_KEPT = 120;
const TAPE_RATE = 70, TAPE_NEXT = 240;
const FEED_MOST = 500;


class ScanScroll {
  constructor(parts) {
    Object.assign(this, { now: () => performance.now(), random: Math.random, still: () => false, toast: () => {},
      frame: (fn) => askFrame(fn), unframe: (id) => dropFrame(id) }, parts);
    this.on = false;
    this.leaving = false;
    this.held = false;
    this.brief = null;
    this.at = scrollPlace(0, 0);
    this.W = 0; this.H = 0; this.dpr = 1;
    this.showing = -1;
    this.switchAt = 0;
    this.seq = 0;
    this.waiting = [];
    this.waitingChars = 0;
    this.recent = [];
    this.flying = [];
    this.owed = 0;
    this.line = null;
    this.sprites = new Map();
    this.tapeNext = [];
    this.tapeLines = [];
    this.tapeAt = 0;
    this.loopId = 0; this.last = 0; this.leaveTimer = 0;
    this.cost = { frames: 0, ms: 0, most: 0 };
    this.grip.addEventListener("pointerdown", (e) => this.grab(e));
    for (const type of ["pointerup", "pointercancel", "lostpointercapture"]) this.grip.addEventListener(type, () => this.letGo());
  }

  resize(W, H, dpr = 1, view = undefined) {
    Object.assign(this, { W, H, dpr, at: scrollPlace(W, H, view) });
    const a = this.at, s = this.box.style;
    Object.assign(s, { left: `${a.x}px`, top: `${a.y}px`, width: `${a.size}px`, height: `${a.size}px` });
    this.page.style.fontSize = this.tape.style.fontSize = `${a.font.toFixed(1)}px`;
    this.caption.style.fontSize = `${(a.font * 1.05).toFixed(1)}px`;
    this.stream.width = Math.round(W * dpr);
    this.stream.height = Math.round(H * dpr);
    this.line = null;
    if (this.held) this.writePage();
  }

  report(b) {
    const running = !!b?.running;
    if (b) this.brief = b;
    if (running && !this.on) this.start(b);
    else if (!running && this.on) this.end(b);
    if (!running) return;
    this.caption.textContent = scrollCaption(b);
    if (b.feed > this.seq) this.askFeed();
  }

  start(b) {
    this.on = true;
    this.leaving = false;
    this.held = false;
    clearTimeout(this.leaveTimer);
    this.seq = Math.max(0, (b.feed || 0) - (b.received || 0));
    this.waiting = []; this.waitingChars = 0; this.recent = []; this.flying = []; this.owed = 0; this.line = null;
    this.tapeNext = []; this.tapeLines = []; this.tapeAt = 0; this.landed = false;
    this.roll.innerHTML = "";
    this.frames.forEach((img, k) => { if (!img.src) img.src = SCROLL_ART[k]; });
    this.page.hidden = true;
    this.box.classList.remove("leaving", "held");
    this.stream.classList.remove("leaving");
    this.box.hidden = false;
    this.stream.hidden = false;
    this.switchAt = 0;
    this.loop();
  }

  end(b) {
    this.on = false;
    this.leaving = true;
    this.held = false;
    this.page.hidden = true;
    this.waiting = []; this.waitingChars = 0;
    this.box.classList.remove("held");
    this.box.classList.add("leaving");
    this.stream.classList.add("leaving");
    this.toast(scrollEnded(b || this.brief || {}));
    clearTimeout(this.leaveTimer);
    this.leaveTimer = setTimeout(() => this.gone(), SCROLL_LEAVE_MS);
  }

  gone() {
    this.leaving = false;
    this.box.hidden = true;
    this.stream.hidden = true;
    this.flying = [];
    this.unframe(this.loopId);
    this.loopId = 0;
  }

  askFeed() {
    const asked = this.ask(`/api/auction/feed?since=${this.seq}&most=${FEED_MOST}`);
    asked?.then((answer) => this.take(answer), () => {});
  }

  take(answer) {
    if (!this.on) return;
    const items = (answer?.items || []).filter((a) => a.seq > this.seq);
    this.seq = Math.max(this.seq, answer?.seq || 0, ...items.map((a) => a.seq));
    for (const a of items) {
      const text = a.name || word("page.auction-scroll.item", { id: a.item });
      this.waiting.push({ text, q: a.q });
      this.waitingChars += text.length;
    }
    while (this.waitingChars > STREAM_WAITING) this.waitingChars -= this.waiting.shift().text.length;
    this.tapeNext.push(...items);
    if (this.tapeNext.length > TAPE_NEXT) this.tapeNext.splice(0, this.tapeNext.length - TAPE_NEXT);
    this.recent.push(...items);
    if (this.recent.length > SCROLL_KEPT) this.recent.splice(0, this.recent.length - SCROLL_KEPT);
  }

  grab(e) {
    if (!this.on || e.button > 0 || e.target?.closest?.(".help-q")) return;
    this.held = true;
    try { this.grip.setPointerCapture?.(e.pointerId); } catch (err) {   }
    e.preventDefault?.();
    this.box.classList.add("held");
    this.show(0);
    this.box.style.transform = "none";
    this.writePage();
    this.page.hidden = false;
  }

  letGo() {
    if (!this.held) return;
    this.held = false;
    this.box.classList.remove("held");
    this.page.hidden = true;
    this.switchAt = 0;
  }

  writePage() {
    const n = this.at.lines, shown = n ? this.recent.slice(-n) : [];
    this.page.innerHTML = shown.length ? shown.map(scrollLine).join("") : `<div class="ah-line ah-none">${esc(word("page.auction-scroll.none"))}</div>`;
  }

  show(k) {
    if (k === this.showing) return;
    this.frames.forEach((img, i) => { img.hidden = i !== k; });
    this.showing = k;
  }

  loop() {
    if (this.loopId) return;
    const tick = (t) => {
      this.loopId = 0;
      if (this.tick(t)) this.loopId = this.frame(tick);
    };
    this.loopId = this.frame(tick);
  }

  tick(t) {
    const began = this.now();
    const dt = this.last && t > this.last ? Math.min(0.1, (t - this.last) / 1000) : 1 / 60;
    this.last = t;
    const scrolling = this.on && !this.held && !this.brief?.waiting && this.landed;
    if (!scrolling) {
      this.show(0);
      if (!this.held) this.box.style.transform = "none";
    } else if (t >= this.switchAt) {
      this.show(scrollFrame(this.showing, this.random));
      this.box.style.transform = this.still() ? "none" : scrollShake(this.random);
      this.switchAt = t + SCROLL_SWITCH[0] + this.random() * (SCROLL_SWITCH[1] - SCROLL_SWITCH[0]);
    }
    if (this.tape.hidden === scrolling) this.tape.hidden = !scrolling;
    if (scrolling) this.rollOn(dt);
    this.flow(dt);
    const spent = this.now() - began;
    this.cost.frames++;
    this.cost.ms += spent;
    this.cost.most = Math.max(this.cost.most, spent);
    return this.on || this.leaving;
  }

  rollOn(dt) {
    const lineH = this.at.font * SCROLL_LINE;
    if (!(lineH > 0)) return;
    this.tapeAt += TAPE_RATE * lineH * dt;
    let added = false;
    while (this.tapeAt >= lineH) {
      this.tapeAt -= lineH;
      const a = this.tapeNext.shift() || this.recent[Math.floor(this.random() * this.recent.length)];
      this.tapeLines.unshift(a ? scrollLine(a) : `<div class="ah-line"></div>`);
      added = true;
    }
    if (added) {
      this.tapeLines.length = Math.min(this.tapeLines.length, this.at.lines + 4);
      this.roll.innerHTML = this.tapeLines.join("");
    }
    this.roll.style.transform = `translateY(${(this.tapeAt - lineH).toFixed(1)}px)`;
  }

  hose(dt) {
    const want = hosePath(this.you(), this.at, this.W, this.H).line;
    if (!this.line) return (this.line = want);
    const k = 1 - Math.exp(-dt * STREAM_FOLLOW);
    this.line = want.map((p, i) => [this.line[i][0] + (p[0] - this.line[i][0]) * k, this.line[i][1] + (p[1] - this.line[i][1]) * k]);
    return this.line;
  }

  flow(dt) {
    const line = this.hose(dt), lengths = hoseLengths(line), length = lengths[lengths.length - 1];
    this.owed = this.waiting.length ? this.owed + streamRate(this.waitingChars) * dt : 0;
    while (this.owed >= 1 && this.waiting.length && this.flying.length < STREAM_MOST) {
      this.owed -= 1;
      const name = this.waiting[0], ch = name.text[0];
      name.text = name.text.slice(1);
      this.waitingChars--;
      if (!name.text) this.waiting.shift();
      if (ch.trim()) {
        this.flying.push({ ch, q: name.q, u: 0, pace: 0.85 + this.random() * 0.3, sway: (this.random() * 2 - 1) * 9,
                           phase: this.random() * 6.28, land: this.random() * 2 - 1 });
      }
    }
    const g = this.stream.getContext("2d");
    g.setTransform(this.dpr, 0, 0, this.dpr, 0, 0);
    g.clearRect(0, 0, this.W, this.H);
    const time = streamTime(length), half = this.at.landing.half;
    this.flying = this.flying.filter((c) => {
      c.u += dt * c.pace / time;
      if (c.u < 1) return true;
      this.landed = true;
      return false;
    });
    for (const c of this.flying) {
      const p = hoseAt(line, lengths, c.u), bend = c.sway * Math.sin(c.phase + c.u * 9) * Math.sin(Math.PI * c.u);
      const x = p.x - p.dy * bend + c.land * half * c.u ** 3, y = p.y + p.dx * bend;
      const img = this.sprite(c.ch, c.q), k = 0.65 + 0.45 * c.u;
      g.globalAlpha = Math.max(0, streamAlpha(c.u, length));
      g.drawImage(img, x - img.width * k / (2 * this.dpr), y - img.height * k / (2 * this.dpr), img.width * k / this.dpr, img.height * k / this.dpr);
    }
    g.globalAlpha = 1;
  }

  sprite(ch, q) {
    const key = `${q}|${ch}`;
    if (this.sprites.has(key)) return this.sprites.get(key);
    const c = this.canvas(), side = Math.ceil(STREAM_FONT * 2 * this.dpr), mid = side / 2;
    c.width = c.height = side;
    const g = c.getContext("2d");
    g.font = `${Math.round(STREAM_FONT * this.dpr)}px Metamorphous, Georgia, serif`;
    g.textAlign = "center";
    g.textBaseline = "middle";
    g.filter = `blur(${(STREAM_BLUR * this.dpr).toFixed(1)}px)`;
    g.fillStyle = tint("black", 0.55);
    g.fillText(ch, mid, mid + this.dpr);
    g.fillStyle = tint(streamColour(q));
    g.fillText(ch, mid, mid);
    this.sprites.set(key, c);
    return c;
  }
}

if (typeof module === "object") {
  module.exports = { SCROLL_ART, SCROLL_SHAPE, SCROLL_COVER, SCROLL_GAP, SCROLL_LINES, SCROLL_LINE, scrollPlace, scrollFrame,
    SCROLL_SWITCH, SCROLL_SHAKE, scrollShake, HOSE, arrowPlace, pullIn, hoseCurve, hoseControls, hosePath, hoseLengths, hoseAt, STREAM_RATE, STREAM_FULL,
    STREAM_SPEED, STREAM_TIME, STREAM_MOST, STREAM_WAITING, STREAM_FOLLOW, STREAM_FONT, STREAM_BLUR, streamRate, streamTime, streamAlpha,
    STREAM_COLOURS, streamColour, scrollLine, scrollCaption, scrollEnded, SCROLL_LEAVE_MS, SCROLL_KEPT, TAPE_RATE, TAPE_NEXT, FEED_MOST, ScanScroll };
}
