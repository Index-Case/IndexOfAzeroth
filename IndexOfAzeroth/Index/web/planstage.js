// The Index of Azeroth. Copyright 2026 Index Case <indexofazeroth@pm.me>. PolyForm Strict 1.0.0, see LICENSE.md.
"use strict";
const STAGE_GAP = 18;
const STAGE_EDGE = 16;
const PLAN_STAGE_WORDS = wordsOf("page.planning.stage");
const freshPlanStage = (key) => ({ key, stage: null, text: "", spots: [], at: null });
const planStage = freshPlanStage(null);

function planStageOf(said) {
  if (!said) return null;
  if (PLAN_STAGE_WORDS[said.stage]) return said.stage;
  return said.of ? "ways" : null;
}

function planStageCount(stage, said) {
  if (stage === "ways") return said.of ? word("page.planning.count.way", { k: Math.min((said.done || 0) + 1, said.of), n: said.of }) : "";
  if (said.rounds) return word("page.planning.count.round", { n: said.rounds.n, of: said.rounds.of });
  if (said.at) return word("page.planning.count.stop", { k: said.at.k, n: said.at.n });
  return "";
}

function planStageLine(stage, count) {
  const name = PLAN_STAGE_WORDS[stage];
  return count ? word("page.planning.line", { stage: name, count }) : name;
}

function syncPlanStage() {
  const box = $("plan-stage");
  if (!box) return;
  const t = compose.t, said = t && compose.mode === "making" && app.plan?.progress?.key === t.key && options.get("planmap") ? app.plan.progress : null;
  const stage = planStageOf(said);
  if (!stage) {
    if (planStage.key && !box.classList.contains("leaving")) box.classList.add("leaving");
    if (!t || compose.mode !== "making") Object.assign(planStage, freshPlanStage(null));
    return;
  }
  if (planStage.key !== t.key) Object.assign(planStage, freshPlanStage(t.key));
  const text = planStageLine(stage, planStageCount(stage, said));
  box.hidden = false;
  box.classList.remove("leaving");
  if (stage !== planStage.stage) {
    planStage.stage = stage;
    box.classList.remove("writing");
    if (!lessMotion()) {
      void box.offsetWidth;
      box.classList.add("writing");
    }
  }
  if (text !== planStage.text) {
    planStage.text = text;
    box.textContent = text;
  }
}
on("update", syncPlanStage);

function planStageSpots() {
  if (planMap.key !== planStage.key || (!planMap.dots.length && !planMap.marks.size)) return planStage.spots;
  planStage.spots = [...planMap.dots.map((d) => [d.w.inst, d.w.n, d.w.w]),
    ...[...planMap.marks.values()].map((m) => [m.s.i, m.s.at[0], m.s.at[1]])];
  return planStage.spots;
}

const STAGE_CLEAR = ".location > *, .sidestack > *, #warnings > *, #status, .mapkeys, #plan-legend, #overlay-legend";

function planStagePlace(points, w, h, width, height, blocks = []) {
  let x = width / 2, y = height / 3;
  if (points.length) {
    const xs = points.map((p) => p[0]), top = Math.min(...points.map((p) => p[1]));
    x = (Math.min(...xs) + Math.max(...xs)) / 2;
    y = top - STAGE_GAP - h / 2;
  }
  const at = [Math.min(Math.max(x - w / 2, STAGE_EDGE), width - w - STAGE_EDGE), Math.min(Math.max(y - h / 2, STAGE_EDGE), height - h - STAGE_EDGE)];
  return planStageClear(at, w, h, width, height, blocks).map(Math.round);
}

function planStageClear(at, w, h, width, height, blocks) {
  const E = STAGE_EDGE, inside = ([x, y]) => x >= E && y >= E && x + w <= width - E && y + h <= height - E;
  const touching = ([x, y]) => blocks.filter((b) => x < b.right + E && x + w > b.left - E && y < b.bottom + E && y + h > b.top - E);
  if (!touching(at).length) return at;
  const round = ([x, y]) => touching([x, y]).flatMap((b) => [[b.right + E, y], [b.left - E - w, y], [x, b.bottom + E], [x, b.top - E - h]]);
  const first = round(at), places = [...first, ...first.filter(inside).flatMap(round)];
  const clear = places.filter((p) => inside(p) && !touching(p).length);
  if (!clear.length) return at;
  const far = (p) => Math.hypot(p[0] - at[0], p[1] - at[1]);
  return clear.reduce((best, p) => (far(p) < far(best) ? p : best));
}

function planStageBlocks(frame) {
  return [...document.querySelectorAll(STAGE_CLEAR)].map((el) => el.getBoundingClientRect())
    .filter((r) => r.width > 0 && r.height > 0)
    .map((r) => ({ left: r.left - frame.left, top: r.top - frame.top, right: r.right - frame.left, bottom: r.bottom - frame.top }));
}

function placePlanStage(size, scale) {
  const box = $("plan-stage");
  if (!box || box.hidden || !planStage.key) return;
  const points = planStageSpots().map(([i, n, w]) => worldOnScreen(i, n, w, size, scale)).filter(Boolean);
  const frame = box.offsetParent?.getBoundingClientRect() || { left: 0, top: 0, width: innerWidth, height: innerHeight };
  const at = planStagePlace(points, box.offsetWidth, box.offsetHeight, frame.width, frame.height, planStageBlocks(frame));
  if (planStage.at && at[0] === planStage.at[0] && at[1] === planStage.at[1]) return;
  planStage.at = at;
  box.style.transform = `translate(${at[0]}px, ${at[1]}px)`;
}

function planStageGone(e) {
  const box = e.currentTarget;
  if (e.propertyName === "opacity" && box.classList.contains("leaving")) {
    box.hidden = true;
    box.classList.remove("leaving", "writing");
    box.textContent = "";
  }
}
$("plan-stage")?.addEventListener("transitionend", planStageGone);

options.hooks.planmap = { changed: () => { syncPlanLegend(); syncPlanStage(); redraw(); } };

if (typeof module === "object") {
  module.exports = { STAGE_GAP, STAGE_EDGE, STAGE_CLEAR, PLAN_STAGE_WORDS, planStage, planStageOf, planStageCount, planStageLine,
    syncPlanStage, planStageSpots, planStagePlace, planStageClear, planStageBlocks, placePlanStage, planStageGone };
}
