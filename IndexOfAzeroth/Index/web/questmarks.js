// The Index of Azeroth. Copyright 2026 Index Case <indexofazeroth@pm.me>. PolyForm Strict 1.0.0, see LICENSE.md.
"use strict";

const qmarks = { on: keptOr("cc.questMarks", false) === true, done: keptOr("cc.questMarksDone", false) === true,
                 data: null, key: "", loading: false, pictures: new Map() };
const QMARK_SIZE = 18;
const QMARK_EDGE = 1.5;
const QMARK_PICTURE = { take: "pickup", ready: "turnin", open: "incomplete" };
const QMARK_ORDER = ["done", "open", "take", "ready"];
const QMARK_DONE_FADE = 0.85;

function questMarkSwitches() {
  return html`<div class="ql-marks"><label class="ql-close"><input type="checkbox" data-qmarks="on"${qmarks.on ? raw(" checked") : ""}>
    ${word("page.questmarks.switch.show")}</label>
    <label class="ql-close${qmarks.on ? "" : " off"}"><input type="checkbox" data-qmarks="done"${qmarks.done ? raw(" checked") : ""}${
    qmarks.on ? "" : raw(" disabled")}> ${word("page.questmarks.switch.done")}</label></div>`;
}

function questMarksSwitched(box) {
  const which = box.dataset?.qmarks;
  if (!which) return false;
  qmarks[which] = box.checked;
  keepIn(which === "on" ? "cc.questMarks" : "cc.questMarksDone", box.checked);
  refreshQuestMarks();
  buildQuestMenu();
  redraw();
  return true;
}

function questMarkAsks() {
  const maps = poiMaps().filter((m) => m != null);
  const who = [app.character || "", app.status?.strs?.faction || "", app.state?.level || 0, app.questlog?.at ?? ""].join("|");
  return { key: `${maps.join(",")}|${who}`, urls: maps.map((m) => `/api/questmarks?map=${m}`) };
}
function refreshQuestMarks() {
  if (!qmarks.on || !app.state?.map || app.dungeon) return;
  const { key, urls } = questMarkAsks();
  if (key === qmarks.key || qmarks.loading) return;
  const asks = urls.map((url) => getJson(url));
  if (asks.some((a) => !a)) return;
  qmarks.loading = true;
  Promise.all(asks).then((sets) => { qmarks.data = sets; qmarks.key = key; redraw(); }, () => {})
    .finally(() => { qmarks.loading = false; });
}

function outlinedMark(name, tone = null) {
  const key = `${name}|${tone || ""}`;
  if (qmarks.pictures.has(key)) return qmarks.pictures.get(key);
  const img = uiImage(name);
  if (!img.complete || !img.naturalWidth) return null;
  const r = Math.ceil(window.devicePixelRatio || 1), s = QMARK_SIZE * r, edge = QMARK_EDGE * r, pad = Math.ceil(edge) + r;
  const layer = (draw) => {
    const c = document.createElement("canvas");
    c.width = c.height = s;
    draw(c.getContext("2d"));
    return c;
  };
  const glyph = layer((g) => {
    g.drawImage(img, 0, 0, s, s);
    if (!tone) return;
    g.globalCompositeOperation = "color";
    g.fillStyle = tint(tone);
    g.fillRect(0, 0, s, s);
    g.globalCompositeOperation = "destination-in";
    g.drawImage(img, 0, 0, s, s);
  });
  const ink = layer((g) => {
    g.drawImage(img, 0, 0, s, s);
    g.globalCompositeOperation = "source-in";
    g.fillStyle = tint("black");
    g.fillRect(0, 0, s, s);
  });
  const out = document.createElement("canvas");
  out.width = out.height = s + pad * 2;
  const g = out.getContext("2d");
  for (let a = 0; a < 16; a++) g.drawImage(ink, pad + Math.cos(a * Math.PI / 8) * edge, pad + Math.sin(a * Math.PI / 8) * edge);
  g.drawImage(glyph, pad, pad);
  const mark = { canvas: out, size: out.width / r };
  qmarks.pictures.set(key, mark);
  return mark;
}

function questMarkSpot(m) {
  const quests = m.q.map((q) => q.n).join(", ") + (m.more ? ` ${word("page.questmarks.more", { n: m.more })}` : "");
  return { cat: m.o ? "questobject" : "quest", name: m.n, sub: quests, icon: QUESTS_ICON, x: m.x, y: m.y, z: m.z ?? undefined,
           label: `${wordsOf("page.questmarks.kind")[m.k]}. ${word("page.questmarks.click", { name: m.n })}` };
}

function drawQuestMarks(size, scale) {
  if (!qmarks.on || !qmarks.data || app.dungeon) return;
  const want = new Set(poiMaps()), shown = [];
  for (const d of qmarks.data) {
    if (!want.has(d.map)) continue;
    for (const m of d.marks) {
      if (m.k === "done" && !qmarks.done) continue;
      const [x, y] = toScreen(m.x, m.y, size, scale, d.map);
      if (x < -QMARK_SIZE || y < -QMARK_SIZE || x > W + QMARK_SIZE || y > H + QMARK_SIZE) continue;
      shown.push({ x, y, m, map: d.map });
    }
  }
  shown.sort((a, b) => QMARK_ORDER.indexOf(a.m.k) - QMARK_ORDER.indexOf(b.m.k));
  for (const { x, y, m, map } of shown) {
    const done = m.k === "done";
    const pic = outlinedMark(done ? (m.m === "!" ? "pickup" : "turnin") : QMARK_PICTURE[m.k], done ? "quest-done" : null);
    if (pic) {
      ctx.save();
      if (done) ctx.globalAlpha = QMARK_DONE_FADE;
      ctx.drawImage(pic.canvas, x - pic.size / 2, y - pic.size / 2, pic.size, pic.size);
      ctx.restore();
    }
    poi.drawn.push({ x, y, map, p: questMarkSpot(m) });
  }
}
