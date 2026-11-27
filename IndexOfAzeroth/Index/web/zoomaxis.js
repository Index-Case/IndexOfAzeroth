// The Index of Azeroth. Copyright 2026 Index Case <indexofazeroth@pm.me>. PolyForm Strict 1.0.0, see LICENSE.md.
"use strict";

const ZOOM_WHEEL = 1.0015;
const ZOOM_MOVED = 4;

function zoomAxis(o) {
  const least = o.least ?? ZOOM_LEAST, pickLeast = o.pickLeast ?? PICK_LEAST, picked = o.picked || o.show;
  let pick = null;
  const timeAt = (e) => {
    const r = o.axis().getBoundingClientRect(), v = o.view();
    return v.from + Math.min(1, Math.max(0, (e.clientX - r.left) / Math.max(1, r.width))) * (v.to - v.from);
  };
  const zoomed = () => {
    const w = o.whole(), v = o.view();
    return !!w && (v.from > w.from + 1e-6 || v.to < w.to - 1e-6);
  };
  return {
    timeAt,
    zoomed,
    wheel(e) {
      const w = o.whole();
      if (!w) return false;
      e.preventDefault?.();
      o.show(zoomAbout(o.view(), timeAt(e), Math.pow(ZOOM_WHEEL, e.deltaY || 0), w, least));
      return true;
    },
    down(e) {
      if (!o.whole()) return;
      pick = { a: timeAt(e), x: e.clientX, pan: zoomed() && !e.shiftKey, view: o.view() };
    },
    move(e) {
      if (!pick) return false;
      if (pick.pan) {
        const v = pick.view, w = o.whole(), width = Math.max(1, o.axis().getBoundingClientRect().width);
        o.show(panBy(v, -(e.clientX - pick.x) / width * (v.to - v.from), w));
        return true;
      }
      const v = o.view(), b = timeAt(e), box = o.box(), span = Math.max(1, v.to - v.from);
      const lo = Math.min(pick.a, b), hi = Math.max(pick.a, b);
      box.hidden = Math.abs(e.clientX - pick.x) < ZOOM_MOVED;
      box.style.left = `${(lo - v.from) / span * 100}%`;
      box.style.width = `${(hi - lo) / span * 100}%`;
      return true;
    },
    up(e) {
      if (!pick) return false;
      const { a, x, pan } = pick, b = timeAt(e), moved = Math.abs(e.clientX - x) >= ZOOM_MOVED, v = o.view();
      pick = null;
      o.box().hidden = true;
      if (pan && moved) return true;
      if (moved && Math.abs(b - a) >= Math.min(pickLeast, (v.to - v.from) / 100)) picked({ from: Math.min(a, b), to: Math.max(a, b) });
      else o.click(b, e);
      return true;
    },
    whole() {
      const w = o.whole();
      if (w) o.show(w);
    },
  };
}
