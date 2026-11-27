// The Index of Azeroth. Copyright 2026 Index Case <indexofazeroth@pm.me>. PolyForm Strict 1.0.0, see LICENSE.md.
"use strict";

const QMARK_KEPT = { take: "cc.questMarksTake", hand: "cc.questMarksHand", done: "cc.questMarksDone" };const qmarkWas = keptOr("cc.questMarks", false) === true;
const qmarks = { take: keptOr(QMARK_KEPT.take, qmarkWas) === true, hand: keptOr(QMARK_KEPT.hand, qmarkWas) === true,
                 done: keptOr(QMARK_KEPT.done, false) === true,
                 data: null, key: "", loading: false, pictures: new Map() };
const qmarkSwitch = (m) => ((m.k === "done" ? m.m === "!" : m.k === "take") ? "take" : "hand");
const qmarksOn = () => qmarks.take || qmarks.hand;
const QMARK_SIZE = 18;
const QMARK_EDGE = 0.75;
const QMARK_PICTURE = { take: "pickup", ready: "turnin", open: "incomplete" };
const QMARK_ORDER = ["done", "open", "take", "ready"];
const QMARK_LOOK = { plain: { fill: null, edge: "black" }, done: { fill: "quest-done", edge: "quest-done-edge" } };

function questMarkSwitches() {
  const box = (which, label) => html`<label class="ql-close"><input type="checkbox" data-qmarks="${which}"${
    qmarks[which] ? raw(" checked") : ""}> ${label}</label>`;
  return html`<div class="ql-marks">${box("take", word("page.questmarks.switch.take"))}${
    box("hand", word("page.questmarks.switch.hand"))}
    <label class="ql-close${qmarksOn() ? "" : " off"}"><input type="checkbox" data-qmarks="done"${qmarks.done ? raw(" checked") : ""}${
    qmarksOn() ? "" : raw(" disabled")}> ${word("page.questmarks.switch.done")}</label></div>`;
}

function questMarksSwitched(box) {
  const which = box.dataset?.qmarks;
  if (!QMARK_KEPT[which]) return false;
  qmarks[which] = box.checked;
  keepIn(QMARK_KEPT[which], box.checked);
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
  if (!qmarksOn() || !app.state?.map || app.dungeon) return;
  const { key, urls } = questMarkAsks();
  if (key === qmarks.key || qmarks.loading) return;
  const asks = urls.map((url) => getJson(url));
  if (asks.some((a) => !a)) return;
  qmarks.loading = true;
  Promise.all(asks).then((sets) => { qmarks.data = sets; qmarks.key = key; redraw(); }, () => {})
    .finally(() => { qmarks.loading = false; });
}

function outlinedMark(name, look) {
  const key = `${name}|${look.fill || ""}|${look.edge}`;
  if (qmarks.pictures.has(key)) return qmarks.pictures.get(key);
  const img = uiImage(name);
  if (!img.complete || !img.naturalWidth) return null;
  const r = Math.ceil(window.devicePixelRatio || 1), s = QMARK_SIZE * r, edge = QMARK_EDGE * r, pad = Math.ceil(edge) + r;
  const layer = (tone) => {
    const c = document.createElement("canvas");
    c.width = c.height = s;
    const g = c.getContext("2d");
    g.drawImage(img, 0, 0, s, s);
    if (tone) {
      g.globalCompositeOperation = "source-in";
      g.fillStyle = tint(tone);
      g.fillRect(0, 0, s, s);
    }
    return c;
  };
  const glyph = layer(look.fill), ink = layer(look.edge);
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
  if (!qmarksOn() || !qmarks.data || app.dungeon) return;
  const want = new Set(poiMaps()), shown = [];
  for (const d of qmarks.data) {
    if (!want.has(d.map)) continue;
    for (const m of d.marks) {
      if (!qmarks[qmarkSwitch(m)] || (m.k === "done" && !qmarks.done)) continue;
      const [x, y] = toScreen(m.x, m.y, size, scale, d.map);
      if (x < -QMARK_SIZE || y < -QMARK_SIZE || x > W + QMARK_SIZE || y > H + QMARK_SIZE) continue;
      shown.push({ x, y, m, map: d.map });
    }
  }
  shown.sort((a, b) => QMARK_ORDER.indexOf(a.m.k) - QMARK_ORDER.indexOf(b.m.k));
  for (const { x, y, m, map } of shown) {
    const done = m.k === "done";
    const pic = outlinedMark(done ? (m.m === "!" ? "pickup" : "turnin") : QMARK_PICTURE[m.k], QMARK_LOOK[done ? "done" : "plain"]);
    if (pic) ctx.drawImage(pic.canvas, x - pic.size / 2, y - pic.size / 2, pic.size, pic.size);
    poi.drawn.push({ x, y, map, p: questMarkSpot(m) });
  }
}
