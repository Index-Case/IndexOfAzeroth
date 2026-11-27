// The Index of Azeroth. Copyright 2026 Index Case <indexofazeroth@pm.me>. PolyForm Strict 1.0.0, see LICENSE.md.
"use strict";

app.addons = null;
app.gameInfo = null;
app.loaded = null;
const noticeHidden = {};

function applyAddons(snap) {
  app.addons = snap.addons || null;
  app.gameInfo = snap.game || null;
  app.loaded = snap.loaded || null;
  renderAddonNotice();
}

const bare = (v) => String(v || "").replace(/^v/i, "");

function addonAction(a) {
  const live = app.link?.ok && app.addons?.running ? app.loaded?.[a.folder] : null;
  if (a.status === "error") return `${a.label}: ${a.message}`;
  if (live) {
    const name = a.label;
    if (live.state === "missing" && a.installed) return word("page.addons.act.installed", { name });
    if (live.state === "disabled") return word("page.addons.act.off", { name });
    if (live.state === "notLoaded") {
      return live.reason ? word("page.addons.act.not-loaded.why", { name, reason: live.reason.toLowerCase().replace(/_/g, " ") })
        : word("page.addons.act.not-loaded", { name });
    }
    if (live.state === "loaded" && a.installed && !a.linked && bare(live.version) !== bare(a.installed)) {
      return word("page.addons.act.reload", { name, version: a.installed, running: live.version });
    }
    return null;
  }
  if (a.restart) {
    return a.status === "updated" ? word("page.addons.act.restart.updated", { name: a.label })
      : word("page.addons.act.restart.installed", { name: a.label });
  }
  return null;
}

function renderAddonNotice() {
  const box = $("addon-notice");
  const lines = (app.addons?.list || []).map(addonAction).filter((t) => t && !noticeHidden[t]);
  const html = lines.map((t) => `<div class="an-line"><span>${esc(t)}</span><button class="x-mark" data-hide="${esc(t)}" aria-label="${esc(word("page.addons.hide"))}">×</button></div>`).join("");
  setHtml(box, html);
  box.hidden = !html;
}

$("addon-notice").addEventListener("click", (e) => {
  const b = e.target.closest("button[data-hide]");
  if (!b) return;
  noticeHidden[b.dataset.hide] = true;
  renderAddonNotice();
});


const ADDON_STATES = { ok: "", ...wordsOf("page.addons.state") };

function addonsTable() {
  const list = app.addons?.list;
  if (!list) return "";
  const rows = list.map((a) => {
    const live = app.link?.ok && app.addons.running ? app.loaded?.[a.folder] : null;
    const inGame = !live ? "" : live.state === "loaded" ? esc(live.version || word("page.addons.game.loaded"))
      : live.state === "missing" ? esc(word("page.addons.game.not-yet"))
      : esc(live.state === "disabled" ? word("page.addons.game.off") : live.reason || word("page.addons.game.not-loaded"));
    const note = [ADDON_STATES[a.status] ?? a.status, a.message].filter(Boolean).join(". ");
    const fresh = freshRow(a.changed);
    const name = sourceName(a.label, a.url);
    return `<tr class="${fresh}"><td>${name}</td><td class="num">${esc(a.installed || word("page.addons.disk.none"))}</td><td class="num">${inGame}</td>
      <td>${a.status === "error" || a.error ? `<span class="zero-text">${esc(a.error || a.message || "")}</span>` : esc(note)}</td></tr>`;
  }).join("");
  const where = app.gameInfo?.folder ? `<p class="muted">${esc(word("page.addons.folder", { folder: app.gameInfo.folder }))}</p>` : "";
  return `${where}<table class="list addons"><tr><th>${esc(word("page.addons.head.addon"))}</th>`
    + `<th class="num">${esc(word("page.addons.head.disk"))}</th><th class="num">${esc(word("page.addons.head.game"))}</th>`
    + `<th>${esc(word("page.addons.head.status"))}</th></tr>${rows}</table>`;
}
