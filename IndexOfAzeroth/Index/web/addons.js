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
    if (live.state === "missing" && a.installed) return `${a.label} is installed. Restart the game to load it`;
    if (live.state === "disabled") return `${a.label} is turned off. Turn it on in the AddOns list at character select`;
    if (live.state === "notLoaded") return `${a.label} didn't load${live.reason ? ` (${live.reason.toLowerCase().replace(/_/g, " ")})` : ""}. Check the AddOns list at character select`;
    if (live.state === "loaded" && a.installed && !a.linked && bare(live.version) !== bare(a.installed)) {
      return `${a.label} ${a.installed} is on disk, but the game is running ${live.version}. Type /reload to load the new version`;
    }
    return null;
  }
  if (a.restart) return `${a.label} was ${a.status === "updated" ? "updated" : "installed"}. Restart the game to load it`;
  return null;
}

function renderAddonNotice() {
  const box = $("addon-notice");
  const lines = (app.addons?.list || []).map(addonAction).filter((t) => t && !noticeHidden[t]);
  const html = lines.map((t) => `<div class="an-line"><span>${esc(t)}</span><button class="x-mark" data-hide="${esc(t)}" aria-label="Hide">×</button></div>`).join("");
  setHtml(box, html);
  box.hidden = !html;
}

$("addon-notice").addEventListener("click", (e) => {
  const b = e.target.closest("button[data-hide]");
  if (!b) return;
  noticeHidden[b.dataset.hide] = true;
  renderAddonNotice();
});


const ADDON_STATES = { ok: "", waiting: "Waiting", installed: "Installed", updated: "Updated", linked: "Linked", error: "Failed",
  nogame: "No game folder", unknown: "Waiting" };

function addonsTable() {
  const list = app.addons?.list;
  if (!list) return "";
  const rows = list.map((a) => {
    const live = app.link?.ok && app.addons.running ? app.loaded?.[a.folder] : null;
    const inGame = !live ? "" : live.state === "loaded" ? esc(live.version || "loaded") : live.state === "missing" ? "not yet" : esc(live.state === "disabled" ? "turned off" : live.reason || "not loaded");
    const note = [ADDON_STATES[a.status] ?? a.status, a.message].filter(Boolean).join(". ");
    const fresh = freshRow(a.changed);
    const name = sourceName(a.label, a.url);
    return `<tr class="${fresh}"><td>${name}</td><td class="num">${esc(a.installed || "none")}</td><td class="num">${inGame}</td>
      <td>${a.status === "error" || a.error ? `<span class="zero-text">${esc(a.error || a.message || "")}</span>` : esc(note)}</td></tr>`;
  }).join("");
  const where = app.gameInfo?.folder ? `<p class="muted">Game folder: ${esc(app.gameInfo.folder)}</p>` : "";
  return `${where}<table class="list addons"><tr><th>Addon</th><th class="num">On disk</th><th class="num">In game</th><th>Status</th></tr>${rows}</table>`;
}
