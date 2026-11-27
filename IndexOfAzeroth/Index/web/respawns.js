// The Index of Azeroth. Copyright 2026 Index Case <indexofazeroth@pm.me>. PolyForm Strict 1.0.0, see LICENSE.md.
"use strict";

const rs = { timers: [], version: -1, want: null, skew: 0, show: true };
try { rs.show = localStorage.getItem("cc.respawns") !== "0"; } catch (e) {   }

const nowSec = () => Date.now() / 1000 + rs.skew;

function refreshRespawns(snap) {
  const v = rs.want = snap ? snap.versions?.respawns : rs.want;
  if (v == null || v === rs.version) return;
  getJson("/api/respawns")?.then((d) => {
    rs.timers = d.timers;
    rs.skew = d.now - Date.now() / 1000;
    rs.version = v;
    if (!mobMenu.hidden) buildMobMenu();
  }, () => { if (!mobMenu.hidden) buildMobMenu(); });
}

function timeLeft(t, now = nowSec()) {
  return { left: t.died + t.min - now, windowLeft: t.died + t.max - now };
}

function leftText(t) {
  const { left, windowLeft } = timeLeft(t);
  if (left > 0) return (t.guess || t.est ? "~" : "") + hms(left);
  if (windowLeft > 0) return word("page.respawns.any.most", { left: hms(windowLeft) });
  return word("page.respawns.back");
}

function timerOnMap(t, mapId = app.displayMap) {
  const at = worldToFrac(mapId, { inst: t.map, n: t.x, w: t.y });
  if (!at) return null;
  const [x, y] = at;
  return x < -0.05 || x > 1.05 || y < -0.05 || y > 1.05 ? null : at;
}
function timerSpot(t) {
  const home = continentMapOf(t.map);
  if (!home) return null;
  const [x, y] = toFrac(home.w, t.x, t.y);
  return { map: home.id, x, y };
}


function respawnMenu() {
  const open = mobs.open.has("Respawns");
  const now = nowSec();
  const list = [...rs.timers].sort((a, b) => (a.died + a.min) - (b.died + b.min));
  const running = list.filter((t) => t.died + t.min > now).length;
  const rows = open ? list.map((t) => {
    const back = t.died + t.min <= now, zone = t.zone || zoneNameAt(t);
    return html`<div class="rs-row${back ? " back" : ""}" data-timer="${t.id}">
      <span class="rs-left" data-left="${t.id}">${leftText(t)}</span>
      <span class="mob-name">${t.name}<small>${mobLevelHtml(t.levels)}${zone ? `, ${zone}` : ""}${t.rare ? `, ${word("page.respawns.tag.rare")}` : ""}${
        t.guess ? `, ${word("page.respawns.tag.guess")}` : t.measured ? `, ${word("page.respawns.tag.measured")}` : t.est ? `, ${word("page.respawns.tag.est")}` : ""}</small></span>
      <button class="mob-go" data-rs-go="${t.id}" title="${word("page.respawns.go.tip", { name: t.name })}">${word("page.respawns.go")}</button>
      <button class="rs-x x-mark" data-rs-forget="${t.id}" title="${word("page.respawns.forget.tip")}">×</button></div>`;
  }) : [];
  return html`<div class="poi-group${open ? " open" : ""}">
      <input type="checkbox" data-rs-show title="${word("page.respawns.show.tip")}"${rs.show ? " checked" : ""}>
      <button class="poi-fold" data-fold="Respawns" aria-expanded="${open}">${word("page.respawns.title")}
      <span class="poi-on">${list.length ? word("page.respawns.running", { n: running }) : ""}</span></button></div>
    ${rows.length ? rows : open ? html`<p class="menu-note">${askNote("/api/respawns", { have: rs.version !== -1,
      none: word("page.respawns.none"), what: word("page.respawns.what"), again: () => { refreshRespawns(); buildMobMenu(); } })}</p>` : ""}`;
}

function zoneNameAt(t) {
  const g = zoneAt(t.x, t.y, t.map);
  return g ? app.maps[g.id]?.name : "";
}

setInterval(() => {
  if (mobMenu.hidden) return;
  mobMenu.querySelectorAll("[data-left]").forEach((el) => {
    const t = rs.timers.find((x) => x.id === el.dataset.left);
    if (t) {
      el.textContent = leftText(t);
      el.parentElement.classList.toggle("back", t.died + t.min <= nowSec());
    }
  });
}, 1000);

const guideToTimer = (t) => guideTo({ todoId: null, name: t.name, sub: word("page.respawns.guide", { level: mobLevelText(t.levels) }), cat: "respawn", zone: "",
  instance: t.map, wx: t.x, wy: t.y });

mobMenu.addEventListener("click", (e) => {
  const go = e.target.closest("button[data-rs-go]"), forget = e.target.closest("button[data-rs-forget]");
  if (go) {
    const t = rs.timers.find((x) => x.id === go.dataset.rsGo);
    if (t) guideToTimer(t);
  } else if (forget) {
    rs.timers = rs.timers.filter((x) => x.id !== forget.dataset.rsForget);
    postJson("/api/respawns", { forget: forget.dataset.rsForget }).catch((err) => askFailed(word("page.respawns.forget.failed"), err));
    buildMobMenu();
  }
});
mobMenu.addEventListener("change", (e) => {
  if (!("rsShow" in e.target.dataset)) return;
  rs.show = e.target.checked;
  try { localStorage.setItem("cc.respawns", rs.show ? "1" : "0"); } catch (err) {   }
});


function drawCountdown(x, y, done, color, label, labelColor, dashed = false) {
  ctx.beginPath(); ctx.arc(x, y, 9, 0, Math.PI * 2);
  ctx.fillStyle = tint("black", 0.75); ctx.fill();
  ctx.lineWidth = 3;
  ctx.setLineDash(dashed ? [3, 3] : []);
  ctx.strokeStyle = tint("white", 0.18);
  ctx.beginPath(); ctx.arc(x, y, 9, 0, Math.PI * 2); ctx.stroke();
  ctx.strokeStyle = color;
  ctx.beginPath(); ctx.arc(x, y, 9, -Math.PI / 2, -Math.PI / 2 + done * Math.PI * 2); ctx.stroke();
  ctx.setLineDash([]);
  ctx.font = "600 11px 'Open Sans', sans-serif";
  ctx.textAlign = "center"; ctx.textBaseline = "top";
  ctx.lineWidth = 3; ctx.strokeStyle = tint("black"); ctx.strokeText(label, x, y + 12);
  ctx.fillStyle = labelColor; ctx.fillText(label, x, y + 12);
}

function drawRespawns(s, size, scale) {
  if (!rs.show || !rs.timers.length || !app.state || app.displayMap == null) return;
  const mapId = app.displayMap, now = nowSec();
  for (const t of rs.timers) {
    const at = timerOnMap(t, mapId);
    if (!at) continue;
    const [x, y] = toScreen(at[0], at[1], size, scale, mapId);
    if (x < -20 || y < -20 || x > W + 20 || y > H + 20) continue;
    const left = t.died + t.min - now, back = left <= 0;
    const done = back ? 1 : Math.min(1, Math.max(0, (now - t.died) / t.min));
    const color = back ? tint("back-green") : t.rare ? tint("gold") : tint("cyan");
    const label = back ? (t.died + t.max > now ? word("page.respawns.any") : word("page.respawns.back")) : hms(left);
    drawCountdown(x, y, done, color, label, back ? tint("back-green") : tint("ivory"), t.guess);
    redrawIn(1000 * (!back ? Math.min(left, hmsTurns(left)) : t.died + t.max > now ? t.died + t.max - now : Infinity));
    const how = t.back ? `, ${word("page.respawns.seen", { span: hms(t.min) })}` : t.measured ? `, ${word("page.respawns.measured")}` : "";
    const spot = timerSpot(t) ?? { map: mapId, x: at[0], y: at[1] };
    const when = back ? word("page.respawns.back") : t.guess || t.est ? word("page.respawns.in.about", { left: hms(left) })
      : word("page.respawns.in", { left: hms(left) });
    poi.drawn.push({ x, y, map: spot.map, p: { name: t.name, levels: t.levels ?? null,
      sub: `${when}${t.max > t.min ? `, ${word("page.respawns.window", { span: hms(t.max - t.min) })}` : ""}${how}`,
      cat: "respawn", x: spot.x, y: spot.y, respawn: t } });
  }
}
