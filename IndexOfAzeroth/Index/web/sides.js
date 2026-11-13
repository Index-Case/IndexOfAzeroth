// The Index of Azeroth. Copyright 2026 Index Case <indexofazeroth@pm.me>. PolyForm Strict 1.0.0, see LICENSE.md.
"use strict";

const SIDE_MOST = 2;
const SIDE_AGAIN_MS = 5000;
const sides = { folded: new Set(keptOr("cc.sideFolds", [])), pending: {}, sig: "", loaded: {}, asked: {}, quips: {}, quipTimer: 0 };

const myProfs = () => (app.plan?.profs || []).filter((p) => planIsMine({ ...p, playing: app.plan.playing }));
const sideRunning = (key) => myProfs().find((p) => p.key === key && !p.closed) || null;
const keptSide = (key) => myProfs().find((p) => p.key === key && p.closed) || null;
function sideFull(key) {
  const running = myProfs().filter((p) => !p.closed);
  if (running.length < SIDE_MOST || running.some((p) => p.key === key)) return null;
  return running.map(epicTitle);
}
const capWords = (s) => `${s[0].toUpperCase()}${s.slice(1)}`;

function startSide(d, label) {
  const me = playerWorld();
  const body = { key: d.key, anchor: me ? [me.inst, me.n, me.w] : null, mode: epicWay(app.tracks.epic?.way), close: preferClose(),
                 side: true, click: Date.now() };
  sides.pending[d.key] = { body, label, name: d.name, at: Date.now(), sent: false };
  sendSide(body, label);
  renderSides();
}
function sendSide(body, label) {
  const still = () => sides.pending[body.key]?.body === body;
  postJson("/api/shared/epic", body).then((r) => {
    if (!still()) return;
    if (r?.full) {
      delete sides.pending[body.key];
      return showToast(word("page.craft.side.full", { epic: label, first: r.full[0], second: r.full[1] }));
    }
    if (!r?.started) return setTimeout(() => { if (still()) sendSide(body, label); }, SHARED_AGAIN_MS);
    sides.pending[body.key] = { ...sides.pending[body.key], sent: true, at: Date.now() };
    showToast(word("page.craft.side.started", { epic: capWords(label) }));
    setTimeout(refreshShared, 1500);
  }, (e) => {
    if (still()) delete sides.pending[body.key];
    askFailed(word("page.craft.side.failed"), e);
  });
}
function settleSides() {
  for (const [key, p] of Object.entries(sides.pending)) {
    const got = myProfs().find((s) => s.key === key);
    if (got && (got.written || 0) * 1000 >= p.body.click) {
      delete sides.pending[key];
      showToast(word("page.craft.side.ready", { epic: p.label }));
    } else if (p.sent && app.plan?.working !== key && Date.now() - p.at > SIDE_AGAIN_MS) {
      p.sent = false;
      sendSide(p.body, p.label);
    }
  }
}

function closeSide(p) {
  delete sides.pending[p.key];
  postJson("/api/shared/stop", { key: p.key }).then(() => {
    setTimeout(refreshShared, 500);
    showToast(word("page.craft.side.closing", { epic: capWords(epicTitle(p)) }));
  }, (e) => askFailed(word("page.craft.side.failed"), e));
}
function reopenSide(p) {
  postJson("/api/shared/open", { key: p.key }).then((r) => {
    setTimeout(refreshShared, 500);
    if (r?.full) showToast(word("page.craft.side.full", { epic: epicTitle(p), first: r.full[0], second: r.full[1] }));
    if (r?.opened) showToast(word("page.craft.side.reopened", { epic: capWords(epicTitle(p)) }));
  }, (e) => askFailed(word("page.craft.side.failed"), e));
}

function sideReplanKey(p) {
  const kind = `side:${p.key}`;
  REPLANS[kind] ||= {
    title: () => word("page.craft.side.replan.tip", { epic: epicTitle(sideTrack(p.key) || p) }),
    start(done) {
      const t = sideRunning(p.key) && sideTrack(p.key);
      if (t) startEpic({ key: t.key, name: t.name, label: t.label, replan: true });
      done();
    },
  };
  return replanKey(kind);
}

const sideHeading = (p) => (isCraft(p.key) ? p.name : p.prof) || epicTitle(p);
const sidePlanning = (key) => !!sides.pending[key] || app.plan?.working === key;

function sideQuip(key) {
  const q = (sides.quips[key] ||= { shown: new Set(), last: null, found: [] });
  if (q.last == null) nextSideQuip(q, key);
  return q.last;
}
function nextSideQuip(q, key) {
  const g = app.plan?.progress;
  for (const f of g?.key === key ? g.finds || [] : []) if (!q.found.some((x) => quipKey(x) === quipKey(f))) q.found.push(f);
  q.last = quipNext(quipRecipeLines({ found: q.found }), q.shown, q.last);
}
function streamSideQuips() {
  sides.quipTimer = 0;
  for (const [key, q] of Object.entries(sides.quips)) nextSideQuip(q, key);
  renderSides();
}

function sideHtml(p) {
  const title = epicTitle(p), said = { epic: title }, folded = sides.folded.has(p.key);
  const icon = p.prof ? `<img class="prof-icon" src="/icon/${esc(profIcon(p.prof))}.jpg" alt="">` : "";
  const tip = folded ? word("page.craft.side.open.tip", said) : word("page.craft.side.fold.tip", said);
  const fold = `<button data-side-fold="${esc(p.key)}" aria-expanded="${!folded}" title="${esc(tip)}">${folded ? "+" : "−"}</button>`;
  const end = `<button data-side-close="${esc(p.key)}" title="${esc(word("page.craft.side.close.tip", said))}">${esc(word("page.craft.side.close"))}</button>`;
  const head = panelHead(sideHeading(p), "sides", `${fold}${sideReplanKey(p)}${end}`, { track: true, mark: icon });
  if (folded) return head;
  if (sidePlanning(p.key)) return `${head}<div class="side-quip">${esc(sideQuip(p.key))}</div>`;
  const live = sideLive(p), plan = live ? sidePlan(p, live) : p, newer = newerSide(p);
  const reload = live ? "" : `<div class="guide-line">${esc(word("page.craft.side.reload", said))}</div>`;
  const minor = newer?.rating === "minor" ? newerPlanHtml(newer) : "";
  const steps = plan ? sideStepsHtml(plan.steps || [], live?.states || [], live?.cur) : "";
  return `${head}${reload}${minor}${steps}${materialsHtml(sideTrack(p.key))}`;
}
const sideLive = (p) => (app.sidesLive?.sides || []).find((s) => s.key === p.key && s.running) || null;
function newerSide(p) {
  const live = sideLive(p);
  if (!live || app.plan?.working === p.key || sides.pending[p.key]) return null;
  return newerOf(p, p.written, live.version, app.plan?.sideAdvice?.[p.key]);
}
function sidePlan(p, live) {
  const v = live.version;
  if (v === p.written) return p;
  if (sides.loaded[v]) return sides.loaded[v];
  const asked = !sides.asked[v] && getJson(`/api/shared?version=${v}`, { key: `side plan ${v}`, quiet: true });
  if (asked) {
    sides.asked[v] = true;
    asked.then((sh) => { if (sh?.version === v && sh.epic) { sides.loaded[v] = sh.epic; renderSides(); } },
      () => { delete sides.asked[v]; });
  }
  return null;
}
function sideStepsHtml(steps, states = [], cur = null) {
  const lead = cur != null ? cur - 1 : steps.findIndex((_, k) => (states[k] || "todo") === "todo"), plan = { steps, states };
  return `<ul class="track-next plan-steps side-steps">${steps.map((x, k) => stepRow(x, states[k], null, k === lead, plan, k + 1)).join("")}</ul>`;
}

function sideTrack(key) {
  const p = (app.shared?.profs || []).find((x) => x.key === key);
  return p ? { key, name: p.name, label: epicTitle(p), data: p } : null;
}
const sideOfPanel = (el) => { const key = el?.closest?.("[data-side-key]")?.dataset.sideKey; return key ? sideTrack(key) : null; };

function sidePanels() {
  const mine = (app.shared?.profs || []).filter((p) => !p.closed && planIsMine({ ...p, playing: app.shared.playing }));
  const fresh = Object.entries(sides.pending).filter(([key]) => !mine.some((p) => p.key === key))
    .map(([key, s]) => ({ key, name: s.name }));
  return [...mine, ...fresh];
}

function renderSides() {
  const mine = sidePanels();
  const runs = new Set((app.sidesLive?.sides || []).map((s) => s.version));
  for (const v of Object.keys(sides.loaded)) if (!runs.has(+v)) delete sides.loaded[v];
  for (const key of Object.keys(sides.quips)) if (!sidePlanning(key)) delete sides.quips[key];
  for (let i = 0; i < SIDE_MOST; i++) {
    const box = $(`track-side-${i}`), p = mine[i];
    if (!box) continue;
    box.hidden = !p;
    if (!p) { setHtml(box, ""); continue; }
    box.dataset.sideKey = p.key;
    setHtml(box, `<div class="track-body">${sideHtml(p)}</div>`);
  }
  const streaming = Object.keys(sides.quips).length > 0;
  if (streaming && !sides.quipTimer) sides.quipTimer = setTimeout(streamSideQuips, QuipLines.ms);
  if (!streaming && sides.quipTimer) {
    clearTimeout(sides.quipTimer);
    sides.quipTimer = 0;
  }
}

function sideClicked(e) {
  const b = e.target.closest?.("button[data-side-fold], button[data-side-close]");
  if (!b) return false;
  if (b.dataset.sideFold) {
    const key = b.dataset.sideFold;
    if (sides.folded.has(key)) sides.folded.delete(key); else sides.folded.add(key);
    keepIn("cc.sideFolds", [...sides.folded]);
  } else {
    const p = sidePanels().find((x) => x.key === b.dataset.sideClose);
    if (p) closeSide(p);
  }
  renderSides();
  return true;
}
document.addEventListener("click", sideClicked);

on("update", function sidesUpdate() {
  const sig = JSON.stringify(myProfs().map((p) => [p.key, p.written, !!p.closed]));
  if (sig !== sides.sig) {
    sides.sig = sig;
    refreshShared();
  }
  settleSides();
  renderSides();
});
