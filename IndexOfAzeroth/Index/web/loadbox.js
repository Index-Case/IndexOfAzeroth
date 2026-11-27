// The Index of Azeroth. Copyright 2026 Index Case <indexofazeroth@pm.me>. PolyForm Strict 1.0.0, see LICENSE.md.
"use strict";

const LOADBOX_FADE = 1500;

class LoadBox {
  constructor(doc, say, later = (fn, ms) => setTimeout(fn, ms)) {
    const make = (tag, cls, parent) => {
      const el = doc.createElement(tag);
      el.className = cls;
      parent?.append(el);
      return el;
    };
    this.later = later;
    this.box = make("div", "loadbox");
    this.box.setAttribute("role", "status");
    const sheet = make("div", "loadbox-window", this.box);
    const word = make("div", "loadbox-word calculating", sheet);
    make("span", "", word).textContent = say("page.launcher.loading");
    for (let i = 0; i < 3; i++) make("i", "", word);
    const progress = make("div", "loadbox-progress", sheet);
    this.bar = make("div", "loadbox-bar", progress);
    this.fill = make("div", "loadbox-fill", this.bar);
    this.line = make("div", "loadbox-line", progress);
    this.quill = make("div", "loadbox-quill", progress);
    this.more = make("div", "loadbox-more", progress);
    this.show({});
    doc.body.prepend(this.box);
  }

  show({ line = "", share = null } = {}) {
    this.line.textContent = line;
    this.bar.hidden = share == null;
    this.fill.style.width = `${Math.round(100 * Math.min(1, Math.max(0, share || 0)))}%`;
  }

  leave() {
    if (this.gone) return;
    this.gone = true;
    this.box.classList.add("leaving");
    this.later(() => this.box.remove(), LOADBOX_FADE);
  }
}

function changeRows(doc, text) {
  return (text || "").split("\n").map((line) => line.trim()).filter(Boolean).map((line) => {
    const [kind, said] = line.startsWith("### ") ? ["loadbox-change-topic", line.slice(4)]
      : line.startsWith("- ") ? ["loadbox-change-item", line.slice(2)] : ["loadbox-change-line", line];
    const row = doc.createElement("div");
    row.className = kind;
    said.split("**").forEach((part, n) => {
      if (!part) return;
      const piece = doc.createElement(n % 2 ? "strong" : "span");
      piece.textContent = part;
      row.append(piece);
    });
    return row;
  });
}

const loadBox = typeof document === "object" ? new LoadBox(document, word) : null;

if (typeof module === "object") module.exports = { LOADBOX_FADE, LoadBox, changeRows };
