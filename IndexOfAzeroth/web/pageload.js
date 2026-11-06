// The Index of Azeroth. Copyright 2026 Index Case <indexofazeroth@pm.me>. PolyForm Strict 1.0.0, see LICENSE.md.
"use strict";

const LOAD_TRIES = 3;
const LOAD_WAIT = 1000;
const LOAD_KEY = "pageLoadTries";

class PageLoad {
  constructor({ store, reload, probe, later, show }) {
    Object.assign(this, { store, reload, probe, show });
    this.later = (fn, ms) => later(fn, ms);
    this.failures = [];
    this.tries = Number(this.kept()) || 0;
  }

  kept() {
    try { return this.store?.getItem(LOAD_KEY); } catch { return null; }
  }

  keep(tries) {
    try {
      if (tries) this.store?.setItem(LOAD_KEY, String(tries));
      else this.store?.removeItem(LOAD_KEY);
    } catch {   }
  }

  failed(url, kind, why) {
    if (this.failures.some((f) => f.url === url)) return;
    this.failures.push({ url, kind, why });
    const again = this.tries < LOAD_TRIES;
    this.show(this.failures, again);
    if (again && this.failures.length === 1) this.ask(this.failures[0]);
  }

  ask(file) {
    this.later(() => this.probe(file.url, file.kind, () => { this.keep(this.tries + 1); this.reload(); }, () => this.ask(file)),
      LOAD_WAIT);
  }

  loaded() {
    if (!this.failures.length) this.keep(0);
  }

  restart() {
    this.keep(0);
    this.reload();
  }
}

function loadName(url) {
  try { return decodeURIComponent(new URL(url).pathname).replace(/^\//, "") || url; } catch { return url; }
}

function loadLines(failures, again) {
  const [first] = failures, rest = failures.length - 1;
  const lines = [first.why ? `The page didn't load whole: ${loadName(first.url)} stopped with an error (${first.why}).`
    : `The page didn't load whole: ${loadName(first.url)} didn't arrive.`];
  if (rest) lines.push(`${rest} ${rest === 1 ? "file" : "files"} after it failed too.`);
  lines.push(again ? `The page loads again as soon as ${loadName(first.url)} arrives.`
    : `The page loaded incomplete ${LOAD_TRIES + 1} times in a row and has stopped trying.`);
  return lines;
}

function watchPageLoad(win, doc) {
  let box = null;
  const place = () => {
    box = doc.createElement("div");
    box.className = "page-load";
    box.setAttribute("role", "alert");
    if (doc.body) doc.body.prepend(box);
    else doc.addEventListener("DOMContentLoaded", () => doc.body.prepend(box), { once: true });
  };
  let store = null, asked = 0;
  try { store = win.sessionStorage; } catch {   }
  const load = new PageLoad({
    store,
    reload: () => win.location.reload(),
    later: (fn, ms) => win.setTimeout(fn, ms),
    probe: (url, kind, answered, failed) => {
      const link = doc.createElement("link");
      Object.assign(link, { rel: "preload", as: kind, href: `${url}${url.includes("?") ? "&" : "?"}arrives=${++asked}` });
      link.onload = () => { link.remove(); answered(); };
      link.onerror = () => { link.remove(); failed(); };
      doc.head.append(link);
    },
    show: (failures, again) => {
      if (!box) place();
      box.replaceChildren(...loadLines(failures, again).map((line) => Object.assign(doc.createElement("p"), { textContent: line })));
      if (!again) {
        const key = Object.assign(doc.createElement("button"), { type: "button", textContent: "Reload" });
        key.addEventListener("click", () => load.restart());
        box.append(key);
      }
    },
  });
  win.addEventListener("error", (e) => {
    const el = e.target;
    if (el?.tagName === "SCRIPT") load.failed(el.src, "script", "");
    else if (el?.tagName === "LINK" && el.rel === "stylesheet") load.failed(el.href, "style", "");
    else if (doc.currentScript?.src) load.failed(doc.currentScript.src, "script", e.message || String(e.error));
  }, true);
  win.addEventListener("load", () => load.loaded());
  return load;
}

if (typeof window === "object") watchPageLoad(window, document);

if (typeof module === "object") module.exports = { LOAD_TRIES, LOAD_WAIT, LOAD_KEY, PageLoad, loadName, loadLines, watchPageLoad };
