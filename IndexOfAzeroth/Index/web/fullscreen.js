// The Index of Azeroth. Copyright 2026 Index Case <indexofazeroth@pm.me>. PolyForm Strict 1.0.0, see LICENSE.md.
"use strict";

const FULL_SLACK = 1;
const FULL_QUERY = "(display-mode: fullscreen)";

function fullScreen(win, doc) {
  if (doc.fullscreenElement) return "page";
  if (win.matchMedia(FULL_QUERY).matches) return "window";
  const s = win.screen;
  const fills = Math.abs(win.innerHeight - s.height) <= FULL_SLACK && Math.abs(win.innerWidth - s.width) <= FULL_SLACK;
  return fills ? "window" : "";
}

function watchFullScreen(win, doc, note) {
  const check = () => {
    const how = fullScreen(win, doc);
    note.classList.toggle("out", !!how);
    note.classList.toggle("leaves", how === "page");
    note.setAttribute("aria-hidden", how ? "false" : "true");
    note.tabIndex = how === "page" ? 0 : -1;
    note.title = how === "page" ? word("page.fullscreen.leave") : "";
    doc.body.classList.toggle("full-screen", !!how);
  };
  win.addEventListener("resize", check);
  doc.addEventListener("fullscreenchange", check);
  win.matchMedia(FULL_QUERY).addEventListener("change", check);
  note.addEventListener("click", () => {
    if (doc.fullscreenElement) doc.exitFullscreen().catch(() => {});
  });
  check();
  return check;
}

if (typeof module === "object") module.exports = { FULL_SLACK, FULL_QUERY, fullScreen, watchFullScreen };
