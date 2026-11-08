// The Index of Azeroth. Copyright 2026 Index Case <indexofazeroth@pm.me>. PolyForm Strict 1.0.0, see LICENSE.md.
"use strict";

const SIDE_MOST = 2;
const SIDE_AGAIN_MS = 5000;
const sides = { folded: new Set(keptOr("cc.sideFolds", [])), data: {}, pending: {}, sig: "" };

const myProfs = () => (app.plan?.profs || []).filter((p) => planIsMine({ ...p, playing: app.plan.playing }));
const sideRunning = (key) => myProfs().find((p) => p.key === key && !p.closed) || null;
const keyLine = (key) => { const m = /^prof:(\d+)/.exec(key || ""); return m ? +m[1] : null; };
function sideFull(key) {
  const mine = myProfs(), line = keyLine(key);
  if (mine.length < SIDE_MOST || mine.some((p) => p.closed) || line == null || mine.some((p) => p.line === line)) return null;
  return mine.map(epicTitle);
}
const capWords = (s) => `${s[0].toUpperCase()}${s.slice(1)}`;

function startSide(d, label) {
  const kept = myProfs().find((p) => p.key === d.key && p.closed);
  if (kept && !d.replan) return reopenSide(kept);
  const me = playerWorld();
  const body = { key: d.key, anchor: me ? [me.inst, me.n, me.w] : null, mode: epicWay(app.tracks.epic?.way), close: preferClose(),
                 side: true, click: Date.now() };
  sides.pending[d.key] = { body, label, at: Date.now(), sent: false };
  sendSide(body, label);
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

function closeSide(key) {
  postJson("/api/shared/stop", { key }).then(() => setTimeout(refreshShared, 500), (e) => askFailed(word("page.craft.side.failed"), e));
}
function reopenSide(p) {
  postJson("/api/shared/open", { key: p.key }).then((r) => {
    setTimeout(refreshShared, 500);
    if (r?.opened) showToast(word("page.craft.side.reopened", { epic: capWords(epicTitle(p)) }));
  }, (e) => askFailed(word("page.craft.side.failed"), e));
}

const sideHeading = (p) => (isCraft(p.key) ? p.name : p.prof) || epicTitle(p);
function sideHtml(p) {
  const title = epicTitle(p), said = { epic: title }, folded = sides.folded.has(p.key);
  const icon = p.prof ? `<img class="prof-icon" src="/icon/${esc(profIcon(p.prof))}.jpg" alt="">` : "";
  const tip = folded ? word("page.craft.side.open.tip", said) : word("page.craft.side.fold.tip", said);
  const fold = `<button data-side-fold="${esc(p.key)}" aria-expanded="${!folded}" title="${esc(tip)}">${folded ? "+" : "−"}</button>`;
  const end = p.closed ? `<button data-side-reopen="${esc(p.key)}" title="${esc(word("page.craft.side.reopen.tip", said))}">${esc(word("page.craft.side.reopen"))}</button>`
    : `<button data-side-close="${esc(p.key)}" title="${esc(word("page.craft.side.close.tip", said))}">Close</button>`;
  const head = panelHead(sideHeading(p), "sides", `${fold}${end}`, { track: true, mark: icon });
  if (folded) return head;
  if (p.closed) return `${head}<div class="guide-line muted">${esc(word("page.craft.side.closed", { epic: capWords(title) }))}</div>`;
  if (app.plan?.working === p.key || sides.pending[p.key]) {
    return `${head}<div class="guide-line">${esc(word("page.craft.side.writing", said))}</div>`;
  }
  const live = sideLive(p);
  const reload = live ? "" : `<div class="guide-line">${esc(word("page.craft.side.reload", said))}</div>`;
  return `${head}${reload}${sideStepsHtml(p.steps || [], live?.states || [], live?.cur)}${materialsHtml(sideTrack(p.key))}`;
}
const sideLive = (p) => (app.sidesLive?.sides || []).find((s) => s.version === p.written && s.running) || null;
function sideStepsHtml(steps, states = [], cur = null) {
  const lead = cur != null ? cur - 1 : steps.findIndex((_, k) => (states[k] || "todo") === "todo"), plan = { steps, states };
  return `<ul class="track-next plan-steps side-steps">${steps.map((x, k) => stepRow(x, states[k], null, k === lead, plan, k + 1)).join("")}</ul>`;
}

function sideTrack(key) {
  const p = (app.shared?.profs || []).find((x) => x.key === key);
  return p ? { key, name: p.name, label: epicTitle(p), data: sides.data[key]?.data || null } : null;
}
const sideOfPanel = (el) => { const key = el?.closest?.("[data-side-key]")?.dataset.sideKey; return key ? sideTrack(key) : null; };

function askSideData(p) {
  const had = sides.data[p.key];
  if (had && had.written === p.written) return;
  const q = new URLSearchParams({ key: p.key });
  if (p.anchor) { q.set("inst", p.anchor[0]); q.set("n", (+p.anchor[1]).toFixed(1)); q.set("w", (+p.anchor[2]).toFixed(1)); }
  sides.data[p.key] = { written: p.written, data: had?.data || null };
  getJson(`/api/epic?${q}`, { key: `side epic data ${p.key}`, quiet: true })?.then((d) => {
    if (sides.data[p.key]?.written === p.written) { sides.data[p.key].data = d; renderSides(); }
  }, () => {});
}

function renderSides() {
  const mine = (app.shared?.profs || []).filter((p) => planIsMine({ ...p, playing: app.shared.playing }));
  for (let i = 0; i < SIDE_MOST; i++) {
    const box = $(`track-side-${i}`), p = mine[i];
    if (!box) continue;
    box.hidden = !p;
    if (!p) { setHtml(box, ""); continue; }
    if (!p.closed) askSideData(p);
    box.dataset.sideKey = p.key;
    setHtml(box, `<div class="track-body">${sideHtml(p)}</div>`);
  }
}

function sideClicked(e) {
  const b = e.target.closest?.("button[data-side-fold], button[data-side-close], button[data-side-reopen]");
  if (!b) return false;
  if (b.dataset.sideFold) {
    const key = b.dataset.sideFold;
    if (sides.folded.has(key)) sides.folded.delete(key); else sides.folded.add(key);
    keepIn("cc.sideFolds", [...sides.folded]);
  } else if (b.dataset.sideClose) {
    closeSide(b.dataset.sideClose);
  } else {
    const p = myProfs().find((x) => x.key === b.dataset.sideReopen);
    if (p) reopenSide(p);
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
