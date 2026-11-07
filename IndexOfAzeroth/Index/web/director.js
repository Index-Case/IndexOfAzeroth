// The Index of Azeroth. Copyright 2026 Index Case <indexofazeroth@pm.me>. PolyForm Strict 1.0.0, see LICENSE.md.
"use strict";

const director = { shut: null, adopted: null };

function directorWord(d = app.director, link = app.link) {
  return link?.gameRunning === false ? null : d || null;
}

function directorAllows(kind, needed = false, d = directorWord()) {
  if (!d) return true;
  const out = d.slide && d.slide.kind !== "levelup";
  if (kind === "levelup") return !d.fighting;
  if (kind === "reload") return needed ? !d.fighting : !d.working && !d.fighting && !out;
  return true;
}

function directorSlide(d = directorWord()) {
  const s = d?.slide;
  if (!s || s.kind === "levelup" || !s.text) return null;
  if (director.shut && director.shut.kind === s.kind && director.shut.text === s.text) return null;
  return s;
}

function slideHtml(s) {
  const words = s.text.split("\n").map((p) => `<p>${esc(p)}</p>`).join("");
  const cq = s.kind === "classquest";
  const tip = DirectorRules.line("buttons", cq ? "class_tip" : s.kind === "nextzone" ? "zone_tip" : "replan_tip");
  const label = DirectorRules.line("buttons", cq ? "start" : "replan");
  const replan = s.replan ? `<button class="panel-btn replan-btn" data-director="replan" title="${esc(tip)}">${esc(label)}</button>` : "";
  return `<button class="key small square x-mark" data-director="close" title="${esc(DirectorRules.line("buttons", cq ? "class_close_tip" : "close_tip"))}">&times;</button>
    <div class="director-words">${words}</div>${replan ? `<div class="director-keys">${replan}</div>` : ""}`;
}

function renderDirector(d = directorWord()) {
  const el = $("director-slide");
  if (!el) return;
  const s = directorSlide(d);
  if (!s) { el.hidden = true; el.dataset.key = ""; return; }
  const key = `${s.kind}|${s.text}`;
  if (el.dataset.key !== key) {
    el.dataset.key = key;
    el.dataset.kind = s.kind;
    setHtml(el, slideHtml(s));
    el.classList.remove("out");
  }
  el.hidden = false;
  const panel = $("track-epic");
  const from = panel && !panel.hidden ? panel : document.querySelector(".sidestack");
  const at = slidePlace(from.getBoundingClientRect(), el.offsetWidth || 300, el.offsetHeight);
  el.style.top = `${Math.round(at.y)}px`;
  el.style.left = `${Math.round(at.x)}px`;
  el.dataset.from = at.from;
  askFrame(() => el.classList.add("out"));
}

function directorClicked(e) {
  const b = e.target.closest("button[data-director]");
  const s = directorSlide();
  if (!b || !s) return;
  director.shut = { kind: s.kind, text: s.text };
  if (b.dataset.director === "replan") {
    if (s.kind === "nextzone" && s.quests?.length) {
      startEpic({ key: `log:${[...s.quests].sort((a, z) => a - z).join(".")}`, name: "Your quests", label: "the quests that lead on to the next zone" });
    } else if (s.kind === "classquest" && s.chain) {
      startEpic({ key: `class:${s.chain}`, name: "Your class quest", label: "the class quest epic" });
    } else replanGuide("epic");
  }
  renderDirector();
}

function adoptAsked(p = app.plan, t = app.tracks?.epic) {
  if (p?.asked !== "game" || !p.key || !planIsMine(p) || director.adopted === p.version) return false;
  director.adopted = p.version;
  if (t?.key === p.key) return false;
  app.tracks.epic = newEpic(p.key, p.anchor || null, p.mode, !!p.close);
  saveTrack("epic");
  refreshEpic(true);
  showToast(`You asked in game for ${p.name || "a new plan"}, so the page shows that epic too`);
  return true;
}

function directorLeftHtml(d = directorWord()) {
  return d?.left ? `<div class="guide-line plan-left">${esc(d.left)}</div>` : "";
}

function startDirector() {
  on("snapshot", () => { renderDirector(); adoptAsked(); });
  $("director-slide")?.addEventListener("click", directorClicked);
}

if (typeof module === "object") {
  module.exports = { director, directorWord, directorAllows, directorSlide, slideHtml, renderDirector,
                     directorClicked, adoptAsked, directorLeftHtml, startDirector };
}
