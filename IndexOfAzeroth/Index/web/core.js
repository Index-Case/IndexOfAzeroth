// The Index of Azeroth. Copyright 2026 Index Case <indexofazeroth@pm.me>. PolyForm Strict 1.0.0, see LICENSE.md.
"use strict";


const stepFailed = new Set();
function step(name, fn) {
  try { return fn(); } catch (e) {
    const key = `${name}: ${e?.message || e}`;
    if (!stepFailed.has(key)) { stepFailed.add(key); console.error(`The Index of Azeroth, ${name}:`, e); }
    return undefined;
  }
}


const listeners = new Map();
function on(name, fn) {
  if (!listeners.has(name)) listeners.set(name, []);
  listeners.get(name).push(fn);
}
function emit(name, ...args) {
  return (listeners.get(name) || []).map((fn) => step(`${name} ${fn.name || "(a part)"}`, () => fn(...args)));
}
const answered = (what, quiet) => { if (!quiet) emit("answer", what); };


const UNFOCUSED_FPS = 30, UNFOCUSED_EARLY_MS = 1000 / 120;
const pageFrames = { asked: new Map(), running: new Map(), seq: 0, raf: 0, wait: 0, last: 0 };
function askFrame(fn) {
  const f = pageFrames;
  f.asked.set(++f.seq, fn);
  if (!f.raf && !f.wait) {
    const wait = document.hasFocus?.() === false ? f.last + 1000 / UNFOCUSED_FPS - UNFOCUSED_EARLY_MS - performance.now() : 0;
    if (wait > 1) f.wait = setTimeout(() => { f.wait = 0; f.raf = requestAnimationFrame(runFrame); }, wait);
    else f.raf = requestAnimationFrame(runFrame);
  }
  return f.seq;
}
function dropFrame(id) {
  const f = pageFrames;
  f.asked.delete(id);
  f.running.delete(id);
  if (f.asked.size) return;
  clearTimeout(f.wait);
  cancelAnimationFrame(f.raf);
  f.wait = f.raf = 0;
}
function runFrame(now) {
  const f = pageFrames;
  f.raf = 0;
  f.last = now;
  f.running = f.asked;
  f.asked = new Map();
  for (const fn of f.running.values()) step(`frame ${fn.name || "(a part)"}`, () => fn(now));
  f.running = new Map();
}


const ASK_WAIT_FIRST = 2000, ASK_WAIT_MOST = 60000;
const asks = new Map();

class AskError extends Error {
  constructor(url, status) {
    super(status ? `${url} answered ${status}` : `${url} had no answer`);
    this.name = "AskError";
    this.url = url;
    this.status = status;
  }
}

function askFor(key, work, { force = false, share = false, quiet = false } = {}) {
  let a = asks.get(key);
  if (a?.out && force) {
    const queued = a;
    queued.nextAsk = { work, how: { force, share, quiet } };
    queued.next ||= queued.out.catch(() => {}).then(() => {
      const { work: last, how } = queued.nextAsk;
      queued.next = queued.nextAsk = null;
      return askFor(key, last, how);
    });
    return queued.next;
  }
  if (a?.out) return share ? a.out : null;
  if (a && !force && Date.now() < a.until) return null;
  if (!a) asks.set(key, a = { out: null, fails: 0, until: 0 });
  const done = a;
  a.out = new Promise((resolve) => resolve(work())).then((v) => {
    asks.delete(key);
    answered(key, quiet);
    return v;
  }, (e) => {
    done.out = null;
    done.error = e;
    done.until = Date.now() + (e?.waiting ? ASK_WAIT_FIRST : Math.min(ASK_WAIT_MOST, ASK_WAIT_FIRST * 2 ** done.fails++));
    throw e;
  });
  return a.out;
}

const askWait = (key) => Math.max(0, (asks.get(key)?.until || 0) - Date.now());
function askState(key) {
  const a = asks.get(key);
  return a ? { out: !!a.out, error: a.out ? null : a.error } : null;
}
function askNow(key) {
  const a = asks.get(key);
  if (a) a.until = 0;
}

function getJson(url, { key = url, init, accept = [], ...how } = {}) {
  const work = () => fetch(url, init).catch(() => { throw new AskError(url, 0); }).then((r) => {
    if (!r.ok && !accept.includes(r.status)) throw new AskError(url, r.status);
    return r.json();
  });
  return key == null ? work().then((v) => { answered(url, how.quiet); return v; }) : askFor(key, work, how);
}

const getBytes = (url) => fetch(url).then((r) => (r.ok ? r.arrayBuffer() : null), () => null);

const getPicture = (url, priority, signal) => fetch(url, { priority, signal })
  .then((r) => (r.ok ? r.blob() : null))
  .then((blob) => blob && createImageBitmap(blob, { premultiplyAlpha: "none", colorSpaceConversion: "none" }))
  .catch(() => null);

const pictureSrc = (path, stamp) => (stamp == null || stamp === "" ? path : `${path}?v=${encodeURIComponent(stamp)}`);

const postJson = (url, body, opts = {}) => getJson(url, { key: null, ...opts,
  init: { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) } });

const gapsTold = new Set();
function noteGap(kind, id, where, name) {
  const key = `${kind}|${id}|${where}`;
  if (id == null || id === "" || gapsTold.has(key)) return;
  gapsTold.add(key);
  postJson("/api/gap", { kind, id, where, name }, { quiet: true })?.catch(() => {});
}

function askLines(url, part, { signal } = {}) {
  return fetch(url, { signal }).catch((e) => { throw e?.name === "AbortError" ? e : new AskError(url, 0); }).then(async (r) => {
    if (!r.ok) throw new AskError(url, r.status);
    const reader = r.body.getReader(), decoder = new TextDecoder();
    let kept = "";
    for (;;) {
      const { value, done } = await reader.read();
      kept += done ? decoder.decode() : decoder.decode(value, { stream: true });
      const lines = kept.split("\n");
      kept = done ? "" : lines.pop();
      for (const line of lines) if (line.trim()) part(JSON.parse(line));
      if (done) return;
    }
  });
}

const untilWaiting = new Set();
function fetchUntil(url, use) {
  const asked = getJson(url, { share: true });
  const again = () => {
    const w = { url, use };
    w.timer = setTimeout(() => { untilWaiting.delete(w); fetchUntil(url, use); }, askWait(url));
    untilWaiting.add(w);
  };
  if (!asked) return again();
  asked.then(use, again);
}

const PICTURE_AGAIN_MS = 10000;
const picturesWaiting = new Map();
function ourAddress(src) {
  try {
    return new URL(src, location.href).origin === location.origin;
  } catch (e) {
    return false;
  }
}
function pictureFailed(e) {
  const img = e.target;
  if (img?.tagName !== "IMG" || !img.src || picturesWaiting.has(img) || !ourAddress(img.src)) return;
  picturesWaiting.set(img, setTimeout(() => pictureAgain(img), PICTURE_AGAIN_MS));
}
function pictureAgain(img) {
  clearTimeout(picturesWaiting.get(img));
  picturesWaiting.delete(img);
  if (img.isConnected) img.src = img.src;
}
if (typeof document === "object" && typeof document.addEventListener === "function") {
  document.addEventListener("error", pictureFailed, true);
}

function linkBack() {
  for (const a of asks.values()) a.until = 0;
  for (const w of [...untilWaiting]) {
    clearTimeout(w.timer);
    untilWaiting.delete(w);
    fetchUntil(w.url, w.use);
  }
  for (const img of [...picturesWaiting.keys()]) pictureAgain(img);
}

function sameData(a, b, skip = null) {
  if (a === b) return true;
  if (typeof a !== "object" || typeof b !== "object" || !a || !b || Array.isArray(a) !== Array.isArray(b)) return false;
  if (Array.isArray(a)) return a.length === b.length && a.every((x, i) => sameData(x, b[i]));
  const keys = Object.keys(a).filter((k) => !skip?.has(k));
  if (keys.length !== Object.keys(b).filter((k) => !skip?.has(k)).length) return false;
  return keys.every((k) => Object.hasOwn(b, k) && sameData(a[k], b[k]));
}


const panelHtml = new WeakMap(), heldHtml = new Map();
let pressedAt = null;
const pressed = (e) => { pressedAt = e.target; };
const released = () => {
  pressedAt = null;
  setTimeout(() => { for (const [el, html] of [...heldHtml]) { heldHtml.delete(el); setHtml(el, html); } });
};
const moved = (e) => { if (pressedAt && !e.buttons) released(); };
if (typeof addEventListener === "function") {
  addEventListener("pointerdown", pressed, true);
  addEventListener("pointerup", released, true);
  addEventListener("pointercancel", released, true);
  addEventListener("pointermove", moved, true);
}
let sight = null;
function watchSight(el, on) {
  sight ||= new IntersectionObserver((seen) => { for (const e of seen) e.target.classList.toggle("out-of-sight", !e.isIntersecting); });
  for (const one of el.querySelectorAll(".seen-only")) (on ? sight.observe(one) : sight.unobserve(one));
}
function setHtml(el, markup) {
  const html = String(markup);
  if (pressedAt && el.contains(pressedAt)) { heldHtml.set(el, html); return false; }
  heldHtml.delete(el);
  if (panelHtml.get(el) === html) return false;
  panelHtml.set(el, html);
  const a = document.activeElement, keep = a?.id && el.contains(a) ? [a.id, a.selectionStart, a.selectionEnd] : null;
  watchSight(el, false);
  el.innerHTML = html;
  watchSight(el, true);
  const box = keep && document.getElementById(keep[0]);
  if (box) { box.focus(); try { box.setSelectionRange(keep[1], keep[2]); } catch (e) {   } }
  return true;
}

const TOAST_MS = 3500;
let toastTimer = 0;
function showToast(text) {
  const t = document.getElementById("toast");
  t.textContent = text;
  t.hidden = false;
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => { t.hidden = true; }, TOAST_MS);
}
function askFailed(what, e) {
  showToast(`${what}, because ${e?.status === 404 ? "the Index is older than the page and has no answer for this ask yet. Restart the Index and try again"
    : e?.status ? `the Index answered with error ${e.status}` : "the Index isn't answering. Check that the Index is running"}`);
}


let tipPointer = null;
function pointerPicture(box) { tipPointer = box; }

function tipPlace(at, w, h, within, { gap = 14, margin = 4, x = "beside", y } = {}) {
  const point = at.left == null, p = point ? tipPointer : null;
  const a = !point ? at : p ? { left: at.x - p.hx, right: at.x - p.hx + p.w, top: at.y - p.hy, bottom: at.y - p.hy + p.h }
    : { left: at.x, right: at.x, top: at.y, bottom: at.y };
  y = y ?? (p ? "level" : "below");
  const inside = (v, lo, hi, size) => Math.max(lo + margin, Math.min(v, hi - margin - size));
  const left = x === "centre" ? (a.left + a.right - w) / 2
    : x === "middle" ? (a.left + a.right < within.left + within.right ? a.right + gap : a.left - gap - w)
    : a.right + gap + w <= within.right - margin ? a.right + gap : a.left - gap - w;
  const top = y === "level" ? a.top
    : y === "above" ? (a.top - gap - h >= within.top + margin ? a.top - gap - h : a.bottom + gap)
    : a.bottom + gap + h <= within.bottom - margin ? a.bottom + gap : a.top - gap - h;
  return { x: inside(left, within.left, within.right, w), y: inside(top, within.top, within.bottom, h) };
}

const inWindow = () => ({ left: 0, top: 0, right: innerWidth, bottom: innerHeight });

const SLIDE_GAP = 10;
function slidePlace(panel, w, h, within = inWindow()) {
  const at = tipPlace(panel, w, h, within, { gap: SLIDE_GAP, x: "middle", y: "level" });
  return { ...at, from: at.x < panel.left ? "right" : "left" };
}

const FLY_INTO_MS = 600;
function flyInto(el, to) {
  const b = el.getBoundingClientRect(), r = to && !to.hidden ? to.getBoundingClientRect() : null;
  let dx = 0, dy = 0, scale = 0.1;
  if (r && r.width > 0 && b.width > 0) {
    dx = r.left + r.width / 2 - (b.left + b.width / 2);
    dy = r.top + r.height / 2 - (b.top + b.height / 2);
    scale = Math.max(0.1, Math.min(1, r.width / b.width, r.height / b.height));
  }
  el.classList.add("fly-into");
  void el.offsetWidth;
  el.style.transform = `translate(${Math.round(dx)}px, ${Math.round(dy)}px) scale(${scale.toFixed(3)})`;
  el.style.opacity = "0";
}


class RecentMap {
  constructor(most) {
    this.most = most;
    this.map = new Map();
  }
  has(key) { return this.map.has(key); }
  get(key) {
    if (!this.map.has(key)) return undefined;
    const value = this.map.get(key);
    this.map.delete(key);
    this.map.set(key, value);
    return value;
  }
  set(key, value) {
    this.map.delete(key);
    this.map.set(key, value);
    if (this.map.size > this.most) this.map.delete(this.map.keys().next().value);
    return this;
  }
  delete(key) { return this.map.delete(key); }
  keys() { return [...this.map.keys()]; }
  get size() { return this.map.size; }
}


function keptOr(key, fallback) {
  let v;
  try { v = JSON.parse(localStorage.getItem(key)); } catch (e) { return fallback; }
  if (v == null) return fallback;
  if (fallback == null) return v;
  return Array.isArray(v) === Array.isArray(fallback) && typeof v === typeof fallback ? v : fallback;
}
function keepIn(key, value) {
  try { localStorage.setItem(key, JSON.stringify(value)); } catch (e) {   }
}

const CHAR_STORES = ["epic", "loop", "epicDismissed", "questPick", "skillStart"];
const charStore = (name, key) => `cc.${name}.${key || "?"}`;
function moveCharStores(was, key) {
  if (!key) return;
  for (const old of was || []) {
    if (!old || old === key) continue;
    for (const name of CHAR_STORES) {
      try {
        const kept = localStorage.getItem(charStore(name, old));
        if (kept == null) continue;
        if (localStorage.getItem(charStore(name, key)) == null) localStorage.setItem(charStore(name, key), kept);
        localStorage.removeItem(charStore(name, old));
      } catch (e) {   }
    }
  }
}

if (typeof module === "object") {
  module.exports = { step, on, emit, UNFOCUSED_FPS, UNFOCUSED_EARLY_MS, askFrame, dropFrame, ASK_WAIT_FIRST, ASK_WAIT_MOST, AskError, askFor, askWait, askState, askNow, getJson, postJson, noteGap, askLines,
                     getBytes, getPicture, pictureSrc, fetchUntil, PICTURE_AGAIN_MS, pictureFailed, linkBack, sameData, pressed, released, moved, setHtml, TOAST_MS, showToast, askFailed, tipPlace, inWindow, SLIDE_GAP, slidePlace, FLY_INTO_MS, flyInto, RecentMap,
                     keptOr, keepIn, CHAR_STORES, charStore, moveCharStores };
}
