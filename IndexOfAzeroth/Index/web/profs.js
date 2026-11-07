// The Index of Azeroth. Copyright 2026 Index Case <indexofazeroth@pm.me>. PolyForm Strict 1.0.0, see LICENSE.md.
"use strict";

const profs = { data: null, at: 0, version: null };
const PROF_FRESH = 15000;
const profIcon = (name) => SKILL_ICONS[name] || "inv_misc_questionmark";
const PROF_STATES = { learn: "To learn", train: "Rank to train", sleep: "Waiting", raise: "Raising", done: "Done", full: "Full" };

function askProfEpics(force) {
  if (!force && profs.data && profs.version === alts.want && Date.now() - profs.at < PROF_FRESH) return;
  const asked = getJson("/api/profepics", { quiet: true, force: !!force });
  if (!asked) return;
  profs.version = alts.want;
  profs.at = Date.now();
  asked.then((d) => { profs.data = d; profsRedraw(); }, () => {});
}

function profsRedraw() {
  renderProfPanels();
  if (!questMenu.hidden && questsUi.view === "profs") buildQuestMenu();
  if (app.drawer === "player" || app.drawer === "alts") renderDrawer();
}

function profBar(p) {
  if (p.skill == null) return `<small class="muted">Not learnt</small>`;
  const pct = p.cap ? Math.min(100, Math.round(p.skill / p.cap * 100)) : 0;
  return `<span class="prof-bar" title="${esc(`${p.name}: ${p.skill} of ${p.cap}`)}"><span style="width:${pct}%"></span></span><small>${p.skill} / ${p.cap}</small>`;
}

function wallsTip(p) {
  return (p.walls || []).map((w) => `${w.name} ${p.name} to ${w.cap}${w.skill ? `, skill ${w.skill}` : ""}${w.level > 1 ? `, level ${w.level}` : ""}`).join("\n");
}

function levelKey(p) {
  const can = p.offer || ["learn", "train", "raise"].includes(p.state);
  const tip = p.offer ? `This turns on the ${p.offer} layer on the map. ${p.offer === "skinning" ? "Skin here" : "Gather here"} under the zone name then starts a loop for the character's skill`
    : !can ? p.text : p.gathering ? `This makes the ${p.name} plan the epic, with its trainer, its materials and its crafts at any distance. The ${p.name} plan takes the quest epic's place`
      : word("page.profepics.level.tip", { skill: p.name });
  return `<button class="key small" data-prof-level="${p.line}"${can ? "" : " disabled"} title="${esc(tip)}">Level it now</button>`;
}

const LEVEL_WAYS = {
  gather: { label: () => word("page.profepics.gather"), tip: () => word("page.profepics.gather.tip") },
  buy: { label: () => word("page.profepics.buy"), tip: () => word("page.profepics.buy.tip") },
  both: { label: () => word("page.profepics.both"), tip: () => word("page.profepics.both.tip") },
};
const levelAsk = { line: null, way: "both", to: null };
const levelTop = (p) => Math.max(...(p.walls || []).map((w) => w.cap), p.cap || 0, p.target || 0);
function levelAskHtml(p) {
  if (levelAsk.line !== p.line) return "";
  const to = levelAsk.to ?? p.target ?? "";
  const ways = Object.entries(LEVEL_WAYS).map(([way, says]) => `<button class="key small" data-prof-way="${way}"${levelAsk.way === way
    ? ' aria-pressed="true"' : ""} title="${esc(says.tip())}">${esc(says.label())}</button>`).join("");
  return `<div class="prof-ask"><label class="guide-line">${esc(word("page.profepics.level", { skill: p.name }))}
      <input type="number" id="prof-to-${p.line}" min="${(p.skill || 0) + 1}" max="${levelTop(p)}" value="${esc(to)}"></label>
    <div class="guide-cmd">${ways}</div>
    <div class="guide-cmd"><button class="key small" data-prof-go="${p.line}">${esc(word("page.profepics.start", { skill: p.name }))}</button></div></div>`;
}
function levelGo(p) {
  const typed = parseInt(levelAsk.to ?? p.target, 10);
  const to = Math.min(levelTop(p), Math.max((p.skill || 0) + 1, Number.isFinite(typed) ? typed : p.target));
  levelAsk.line = null;
  renderProfPanels();
  startEpic({ key: `prof:${p.line}:${to}:${levelAsk.way}`, name: `${p.name} epic`, label: `the ${p.name} epic` });
}

function profRow(p) {
  const inPlan = p.planned ? ` <small class="muted" title="The ${esc(p.name)} chore is in the plan the game has">In your epic</small>` : "";
  return `<div class="prof-row prof-${esc(p.state)}" title="${esc(wallsTip(p))}">
    <div class="prof-top"><img class="prof-icon" src="/icon/${esc(profIcon(p.name))}.jpg" alt=""><span class="prof-name">${esc(p.name)}</span>${profBar(p)}</div>
    <div class="guide-line">${esc(p.text)}${inPlan}</div>
    <div class="guide-cmd">${levelKey(p)}<button class="key small" data-prof-hide="${esc(p.name)}" title="This takes the ${esc(p.name)} panel off the page. Its chores keep coming, and Unhide in the Player menu brings the panel back">Hide</button><button class="key small" data-prof-stop="${esc(p.name)}" title="This ends the ${esc(p.name)} epic for this character. If you start the ${esc(p.name)} epic again, the Index builds the epic afresh from the game">Stop</button></div>
    ${levelAskHtml(p)}
  </div>`;
}

function renderProfPanels() {
  const box = $("track-profs");
  if (!box) return;
  const shown = (profs.data?.epics || []).filter((p) => !p.hidden);
  box.hidden = !shown.length;
  setHtml(box, shown.length ? `<div class="track-body">${panelHead("Profession epics", "profepics", "", { track: true })}${shown.map(profRow).join("")}</div>` : "");
}

function profsViewHtml() {
  const head = `<div class="qz-head"><button class="qz-back" data-view="log">Back</button><span>Professions</span>${helpButton("profepics")}</div>`;
  const d = profs.data;
  if (!d) {
    return `${head}<p class="menu-note">${askNote("/api/profepics", { what: "your professions", again: () => askProfEpics(true) })}</p>`;
  }
  if (!d.playing) return `${head}<p class="menu-note">The professions show once the game has said who's playing.</p>`;
  const rows = d.list.map((p) => {
    const key = p.on ? `<span class="qp-on">Running${p.hidden ? ", hidden" : ""}</span><button class="key small" data-prof-stop="${esc(p.name)}" title="This ends the ${esc(p.name)} epic for this character">Stop</button>`
      : `<button class="key small" data-prof-start="${esc(p.name)}"${p.can ? "" : " disabled"} title="${esc(p.can
        ? `This starts the ${p.name} epic for this character. The epic shows a step when there's something to do and nothing the rest of the time` : p.why)}">Start</button>`;
    return `<div class="qp-row${p.on ? " on" : ""}${p.can ? "" : " off"}"><img src="/icon/${esc(profIcon(p.name))}.jpg" alt="">
      <span class="qz-name">${esc(p.name)}${p.primary ? "" : ` <small class="muted">secondary</small>`}</span>${profBar(p)}${key}</div>`;
  }).join("");
  return `${head}<div class="qz-list">${rows}</div>`;
}

const profStateTag = (p) => {
  const tag = p.why ? "" : PROF_STATES[p.state];
  return tag ? ` <small>${esc(tag)}</small>` : "";
};

function profEpicsDrawerHtml() {
  askProfEpics(false);
  const list = profs.data?.epics || [];
  if (!list.length) return "";
  const rows = list.map((p) => `<div class="pl-prof"><img src="/icon/${esc(profIcon(p.name))}.jpg" alt="">
    <div><div class="pl-prof-name">${esc(p.name)} epic${profStateTag(p)}</div><div>${esc(p.text)}</div>
    ${p.hidden ? `<button class="key small" data-prof-unhide="${esc(p.name)}" title="This puts the ${esc(p.name)} panel back on the right">Unhide</button>` : ""}</div></div>`);
  return `<h3>Profession epics ${helpButton("profepics")}</h3><div class="pl-profs">${rows.join("")}</div>`;
}

function altProfRow(key) {
  const list = profs.data?.alts?.[key];
  if (!list?.length) return "";
  const rows = list.map((p) => `<div class="alt-prof">${esc(p.name)}${p.skill != null ? ` ${p.skill}/${p.cap}` : ""}: ${esc(p.text)}
    <button class="key small" data-prof-stop="${esc(p.name)}" data-prof-char="${esc(key)}" title="This ends the ${esc(p.name)} epic for this character">Stop</button></div>`);
  return `<tr><th>Profession epics</th><td>${rows.join("")}</td></tr>`;
}

function profClicked(e) {
  const b = e.target.closest?.("button[data-prof-start], button[data-prof-stop], button[data-prof-hide], button[data-prof-unhide], button[data-prof-level], button[data-prof-way], button[data-prof-go]");
  if (!b || b.disabled) return false;
  const epicOf = (line) => (profs.data?.epics || []).find((x) => String(x.line) === String(line));
  if (b.dataset.profLevel) {
    const p = epicOf(b.dataset.profLevel);
    if (p?.offer) showGatherLayer(p.offer);
    else if (p?.gathering) startEpic({ key: `prof:${p.line}`, name: `${p.name} epic`, label: `the ${p.name} epic` });
    else if (p) {
      Object.assign(levelAsk, levelAsk.line === p.line ? { line: null } : { line: p.line, way: "both", to: null });
      renderProfPanels();
    }
    return true;
  }
  if (b.dataset.profWay) {
    levelAsk.way = b.dataset.profWay;
    renderProfPanels();
    return true;
  }
  if (b.dataset.profGo) {
    const p = epicOf(b.dataset.profGo);
    if (p) levelGo(p);
    return true;
  }
  const [what, name] = b.dataset.profStart ? ["start", b.dataset.profStart] : b.dataset.profStop ? ["stop", b.dataset.profStop]
    : b.dataset.profHide ? ["hide", b.dataset.profHide] : ["unhide", b.dataset.profUnhide];
  const body = { do: what, name, ...(b.dataset.profChar ? { char: b.dataset.profChar } : {}) };
  postJson("/api/profepics", body).then(() => askProfEpics(true), (err) => askFailed(`${name}'s epic`, err));
  return true;
}
document.addEventListener("click", profClicked);
document.addEventListener("input", (e) => {
  if (String(e.target?.id || "").startsWith("prof-to-")) levelAsk.to = e.target.value;
});

function laterProfKey(e) {
  const name = e?.prof;
  if (!name) return "";
  const row = profs.data?.list?.find((p) => p.name === name);
  if (row?.on) return ` <small class="muted">${esc(name)} epic running</small>`;
  return ` <button class="key small" data-prof-start="${esc(name)}"${row && !row.can ? " disabled" : ""} title="${esc(row && !row.can ? row.why
    : `This starts the ${name} epic for this character. The epic leads to the skill this wall needs, to the trainer and to the next rank`)}">${esc(name)} epic</button>`;
}

on("laterLine", laterProfKey);
on("playerDrawer", profEpicsDrawerHtml);
on("update", function profsUpdate() {
  askProfEpics(false);
  renderProfPanels();
});
