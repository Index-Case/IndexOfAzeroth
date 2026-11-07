// The Index of Azeroth. Copyright 2026 Index Case <indexofazeroth@pm.me>. PolyForm Strict 1.0.0, see LICENSE.md.
"use strict";

const FRESH_SETTLE = 1500;

class Fresh {
  constructor({ reload, editing = () => false, later = (fn, ms) => setTimeout(fn, ms), cancel = (id) => clearTimeout(id),
    settle = FRESH_SETTLE }) {
    Object.assign(this, { reload, editing, settle });
    this.later = (fn, ms) => later(fn, ms);
    this.cancel = (id) => cancel(id);
    this.timer = 0;
    this.held = false;
  }

  heard(stamp, loaded) {
    if (!stamp || !loaded || stamp === loaded) {
      if (this.timer) this.cancel(this.timer);
      this.timer = 0;
      this.waitingFor = null;
      return false;
    }
    if (this.timer && this.waitingFor === stamp) return true;
    if (this.timer) this.cancel(this.timer);
    this.waitingFor = stamp;
    this.timer = this.later(() => this.due(), this.settle);
    return true;
  }

  due() {
    this.timer = 0;
    this.held = this.editing();
    if (!this.held) this.reload();
  }

  idle() {
    if (this.held) this.later(() => this.due(), 0);
  }
}

function typingIn(el) {
  if (!el) return false;
  const tag = String(el.tagName || "").toLowerCase();
  if (tag === "textarea" || tag === "select") return true;
  if (tag === "input") return !/^(checkbox|radio|button|submit|range|color|file)$/i.test(el.type || "text");
  return !!el.isContentEditable;
}

if (typeof module === "object") module.exports = { FRESH_SETTLE, Fresh, typingIn };
