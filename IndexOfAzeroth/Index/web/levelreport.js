// The Index of Azeroth. Copyright 2026 Index Case <indexofazeroth@pm.me>. PolyForm Strict 1.0.0, see LICENSE.md.
"use strict";


const REPORT_MISSING = {
  played: Object.values(wordsOf("page.level-report.missing.played")),
  gold: Object.values(wordsOf("page.level-report.missing.gold")),
  goldHour: Object.values(wordsOf("page.level-report.missing.gold-hour")),
  pace: Object.values(wordsOf("page.level-report.missing.pace")),
  kills: Object.values(wordsOf("page.level-report.missing.kills")),
  spell: Object.values(wordsOf("page.level-report.missing.spell")),
  stats: Object.values(wordsOf("page.level-report.missing.stats")),
  when: Object.values(wordsOf("page.level-report.missing.when")),
};
const reportMissingLine = (what, random = Math.random) => {
  const pool = REPORT_MISSING[what] || [];
  return pool[Math.min(pool.length - 1, Math.floor(random() * pool.length))] || "";
};


const LEVEL_ART = { big: "art/level_scroll.png", small: "art/level_scroll_small.png" };
const LEVEL_SHAPE = {
  rollers: { left: 0.135, top: 0.093, right: 0.83, bottom: 0.949 },
  page: { top: 0.205, bottom: 0.8 },
  seal: { x: 0.2027, y: 0.3761, w: 0.093, h: 0.103, turn: -6 },
};
const LEVEL_EDGES = [[0.225, 0.2070, 0.7850], [0.273, 0.2130, 0.7790], [0.321, 0.2180, 0.7760], [0.369, 0.2265, 0.7735],
  [0.417, 0.2260, 0.7725], [0.465, 0.2280, 0.7690], [0.513, 0.2265, 0.7685], [0.560, 0.2235, 0.7740], [0.608, 0.2185, 0.7760],
  [0.656, 0.2190, 0.7800], [0.704, 0.2170, 0.7820], [0.752, 0.2115, 0.7865], [0.800, 0.2095, 0.7920]];
const LEVEL_BUFFER = 0.065;

function levelEdge(y) {
  const E = LEVEL_EDGES;
  if (y <= E[0][0]) return { left: E[0][1], right: E[0][2] };
  for (let k = 1; k < E.length; k++) {
    if (y <= E[k][0]) {
      const t = (y - E[k - 1][0]) / (E[k][0] - E[k - 1][0]);
      return { left: E[k - 1][1] + t * (E[k][1] - E[k - 1][1]), right: E[k - 1][2] + t * (E[k][2] - E[k - 1][2]) };
    }
  }
  return { left: E[E.length - 1][1], right: E[E.length - 1][2] };
}
const LEVEL_TEXT = { left: Math.min(...LEVEL_EDGES.map((e) => e[1])) + LEVEL_BUFFER,
                     right: Math.max(...LEVEL_EDGES.map((e) => e[2])) - LEVEL_BUFFER };
function levelInset(y0, y1) {
  const ys = [y0, y1, ...LEVEL_EDGES.map((e) => e[0]).filter((y) => y > y0 && y < y1)];
  const edges = ys.map(levelEdge);
  return { left: Math.max(...edges.map((e) => e.left)) + LEVEL_BUFFER - LEVEL_TEXT.left,
           right: LEVEL_TEXT.right - (Math.min(...edges.map((e) => e.right)) - LEVEL_BUFFER) };
}
const LEVEL_FONT = 0.0165;

function levelPlace(W, H, view = { l: 0, r: W, t: 0, b: H }) {
  const R = LEVEL_SHAPE.rollers;
  const free = Math.max(0, view.r - view.l - 2 * SCROLL_GAP), tall = Math.max(0, view.b - view.t);
  const size = Math.max(0, Math.min(SCROLL_COVER * tall / (R.bottom - R.top), free / (R.right - R.left)));
  return { x: (view.l + view.r) / 2 - size * (R.left + R.right) / 2, y: (view.t + view.b) / 2 - size * (R.top + R.bottom) / 2,
           size, font: size * LEVEL_FONT };
}

function sealSvg(level) {
  const s = LEVEL_SHAPE.seal, text = String(level ?? "");
  const size = (text.length > 1 ? 0.66 : 0.86) * s.h * 1000;
  const squash = (s.w / s.h).toFixed(3);
  const glyph = (extra) => `<text x="0" y="0" text-anchor="middle" dominant-baseline="central" font-size="${size.toFixed(1)}" ${extra}>${esc(text)}</text>`;
  return `<svg class="lr-seal" viewBox="0 0 1000 1000" aria-hidden="true">
    <defs><linearGradient id="lr-gold" x1="0" y1="1" x2="1" y2="0">
      <stop offset="0" stop-color="var(--seal-gold-light)"/><stop offset="0.45" stop-color="var(--seal-gold)"/>
      <stop offset="1" stop-color="var(--seal-gold-deep)"/></linearGradient>
      <filter id="lr-soft" x="-20%" y="-20%" width="140%" height="140%"><feGaussianBlur stdDeviation="0.7"/></filter></defs>
    <g transform="translate(${(s.x * 1000).toFixed(1)} ${(s.y * 1000).toFixed(1)}) rotate(${s.turn}) scale(${squash} 1)" class="lr-seal-num">
      ${glyph('class="lr-seal-shade" transform="translate(2.4 -2.4)" filter="url(#lr-soft)"')}
      ${glyph('class="lr-seal-lit" transform="translate(-1.7 1.7)" filter="url(#lr-soft)"')}
      ${glyph('class="lr-seal-face" fill="url(#lr-gold)"')}
    </g></svg>`;
}


const lrLink = (go, words, data = {}) => `<button class="lr-link" data-lr="${go}"${Object.entries(data).map(([k, v]) =>
  ` data-${k}="${esc(v)}"`).join("")}>${esc(words)}</button>`;
const LR_STATS = ["str", "agi", "sta", "int", "spi"];
const lrStatWord = (k) => wordsOf("page.stats.long")[k];
const andWords = (list) => (list.length < 2 ? list.join("")
  : word("page.level-report.and", { list: list.slice(0, -1).join(", "), last: list[list.length - 1] }));
const LR_QUEST_ZONES = 5, LR_QUEST_NAMES = 4;

function zoneMapNamed(name) {
  if (!name) return null;
  const hit = Object.entries(app.maps || {}).find(([, m]) => m.name === name);
  return hit ? +hit[0] : null;
}
const zoneLink = (name, map) => (map != null && app.maps?.[map] ? lrLink("zone", name || app.maps[map].name, { map }) : esc(name || ""));

const REPORT_MISSING_TITLE = {
  played: (level) => word("page.level-report.missing-title.played", { level }),
  gold: (level) => word("page.level-report.missing-title.gold", { level }),
  goldHour: () => word("page.level-report.missing-title.gold-hour"),
  pace: () => word("page.level-report.missing-title.pace"),
  kills: (level) => word("page.level-report.missing-title.kills", { level }),
  spell: (level) => word("page.level-report.missing-title.spell", { level }),
  stats: () => word("page.level-report.missing-title.stats"),
};
const quipLine = (quips, what, random, level) =>
  (quips.push({ title: REPORT_MISSING_TITLE[what]?.(level) || "", line: reportMissingLine(what, random) }), "");

function fightLines(r) {
  const level = r.from, out = [];
  if (r.deaths != null) {
    out.push(`<li>${r.deaths === 0 ? word("page.level-report.died.none", { level })
      : wordCount("page.level-report.died", r.deaths, { n: num(r.deaths), level })}</li>`);
  }
  if (r.dealt != null) out.push(`<li>${word("page.level-report.dealt", { n: num(r.dealt), level })}</li>`);
  if (r.taken != null) out.push(`<li>${word("page.level-report.taken", { n: num(r.taken), level })}</li>`);
  if (r.fighting > 0) out.push(`<li>${word("page.level-report.fighting", { time: esc(clock(r.fighting)), level })}</li>`);
  return out.join("");
}

function numbersLines(r, random, quips = []) {
  const level = r.from, out = [];
  const miss = (what) => quipLine(quips, what, random, level);
  const hours = r.played > 0 ? r.played / 3600 : null;
  out.push(r.played > 0 ? `<li>${word("page.level-report.played", { time: esc(clock(r.played)), level })}</li>` : miss("played"));
  if (r.gold == null) out.push(miss("gold"));
  else if (r.gold > 0) out.push(`<li>${word("page.level-report.gold.made", { money: money(r.gold), level })}</li>`);
  else if (r.gold < 0) out.push(`<li>${word("page.level-report.gold.lost", { money: money(-r.gold), level })}</li>`);
  else out.push(`<li>${word("page.level-report.gold.same", { level })}</li>`);
  out.push(r.gold > 0 && hours ? `<li>${word("page.level-report.gold.hour", { money: money(Math.round(r.gold / hours)), level })}</li>`
    : r.gold != null && r.gold <= 0 ? "" : miss("goldHour"));
  out.push(r.xpLevel && hours ? `<li>${word("page.level-report.pace", { n: num(r.xpLevel / hours), level })}</li>` : miss("pace"));
  if (r.counting && r.kills == null && !r.spell) {
    out.push(`<li>${word("page.level-report.counting", { level })}</li>`);
    return out.join("");
  }
  out.push(r.kills != null ? `<li>${wordCount("page.level-report.kills", r.kills, { n: num(r.kills), level })}</li>` : miss("kills"));
  out.push(fightLines(r));
  out.push(r.spell ? `<li>${word("page.level-report.favourite", { spell: lrLink("spell", r.spell.name, { level: r.spell.level || level }), level })}</li>`
    : miss("spell"));
  return out.join("");
}

function statsLines(r, random, quips = []) {
  const s = r.stats || {}, out = [];
  const went = (stat, was, now, by) => (was != null && now != null && was !== now
    ? `<li>${word("page.level-report.stat.from", { stat, was: num(was), now: num(now) })}</li>`
    : by ? `<li>${word("page.level-report.stat.by", { stat, n: num(by) })}</li>` : "");
  out.push(went(word("page.level-report.stat.health"), s.wasHealth, s.nowHealth, s.health),
    went(word("page.level-report.stat.mana"), null, null, s.mana));
  const gains = LR_STATS.filter((k) => s[k] != null);
  for (const k of gains) if (s[k] > 0) out.push(k === "spi" ? went(lrStatWord("spi"), s.wasSpirit, s.nowSpirit, s.spi) : went(lrStatWord(k), null, null, s[k]));
  if (!gains.length && s.wasSpirit != null && s.nowSpirit != null) out.push(went(lrStatWord("spi"), s.wasSpirit, s.nowSpirit));
  if (s.talents > 0) out.push(`<li>${wordCount("page.level-report.talent-points", s.talents, { n: num(s.talents) })}</li>`);
  if (!gains.length && !out.some(Boolean)) quipLine(quips, "stats", random, r.level);
  return out.join("");
}

function gatedLine(e) {
  const at = { level: e.level };
  if (e.kind === "talent" && e.spent) {
    return `<li>${word("page.level-report.tier", { link: lrLink("road", word("page.level-report.tier.link"), at), spent: e.spent })}</li>`;
  }
  if (e.kind === "talent") return `<li>${word("page.level-report.points", { link: lrLink("road", word("page.level-report.points.link"), at) })}</li>`;
  if (e.kind === "milestone") {
    return `<li>${word("page.level-report.milestone", { link: lrLink("road", word("page.level-report.milestone.link"), at) })}</li>`;
  }
  const name = lrLink("road", e.name, at);
  if (!e.at) return `<li>${word("page.level-report.learn", { name })}</li>`;
  const teacher = wordsOf("page.level-report.teacher")[e.kind === "riding" || e.kind === "weapon" ? e.kind : "class"];
  return `<li>${word("page.level-report.learn.from", { name, teacher: lrLink("near", teacher, { cat: e.at }) })}</li>`;
}

function skillLines(r) {
  const u = r.unlocks;
  if (!u) return "";
  const out = [];
  const spells = (u.spells || []).filter((s) => !s.pet), pets = (u.spells || []).filter((s) => s.pet);
  const spellAt = (s) => `${lrLink("spell", s.name, { level: s.level })}${s.rank ? ` (${esc(s.rank)})` : ""}`;
  for (const s of spells) out.push(`<li>${word("page.level-report.spell.class", { spell: spellAt(s) })}</li>`);
  if (spells.length) {
    const cost = spells.every((s) => s.cost != null) ? spells.reduce((sum, s) => sum + s.cost, 0) : null;
    const link = lrLink("near", word("page.level-report.teaches.link"), { cat: "class" });
    out.push(`<li>${cost ? wordCount("page.level-report.teaches.cost", spells.length,
      { link, money: spells.length > 1 ? word("page.price.total", { money: money(cost) }) : money(cost) })
      : wordCount("page.level-report.teaches", spells.length, { link })}</li>`);
  }
  for (const s of pets) {
    out.push(`<li>${word("page.level-report.spell.pet", { spell: spellAt(s),
      link: lrLink("near", word("page.level-report.spell.pet.link"), { cat: "pettrainer" }) })}</li>`);
  }
  for (const e of u.gated || []) out.push(gatedLine(e));
  for (const t of u.talents || []) {
    const fill = { icon: `<img class="lr-icon" src="/fileicon/${esc(t.icon)}.jpg" alt="">`, talent: lrLink("road", t.name, { level: t.level }),
                   rank: t.rank, ranks: t.ranks };
    out.push(`<li>${t.ranks > 1 ? word("page.level-report.talent.rank", fill) : word("page.level-report.talent", fill)}</li>`);
  }
  return out.join("");
}

function unlockLines(r, skills = "") {
  const u = r.unlocks;
  if (!u) return `<li class="lr-missing">${word("page.level-report.scribes", { level: r.level })}</li>`;
  const out = [];
  for (const d of u.dungeons || []) {
    const dungeon = lrLink("dungeon", d.name, { key: d.key });
    out.push(`<li>${d.why === "door" ? word("page.level-report.dungeon.door", { dungeon }) : word("page.level-report.at-level", { name: dungeon })}</li>`);
  }
  for (const z of u.zones || []) {
    if (app.maps?.[z.map]) out.push(`<li>${word("page.level-report.at-level", { name: zoneLink(app.maps[z.map].name, z.map) })}</li>`);
  }
  for (const g of u.gear || []) {
    const item = `<button class="lr-link" data-lr="gear" data-tip="${esc(g.id)}">${esc(g.name || word("page.level-report.gear.item", { id: g.id }))}</button>`;
    out.push(`<li>${word("page.level-report.gear", { item })}</li>`);
  }
  out.push(...questLines(u.quests || []));
  if (!out.length && !skills) out.push(`<li>${word("page.level-report.nothing", { level: r.level })}</li>`);
  if ((u.dungeons || []).length || (u.gear || []).length) {
    out.push(`<li>${word("page.level-report.upgrades", { link: lrLink("gear", word("page.level-report.upgrades.link")) })}</li>`);
  }
  return out.join("");
}

function questLines(quests) {
  const byZone = new Map();
  for (const q of quests) {
    const z = q.zone || "";
    if (!byZone.has(z)) byZone.set(z, []);
    byZone.get(z).push(q);
  }
  const here = app.state?.zone;
  const zones = [...byZone.entries()].sort((a, b) => !a[0] - !b[0] || (b[0] === here) - (a[0] === here) || b[1].length - a[1].length
    || a[0].localeCompare(b[0]));
  const out = zones.slice(0, LR_QUEST_ZONES).map(([zone, list]) => {
    const named = list.slice(0, LR_QUEST_NAMES).map((q) => (q.x != null && app.maps?.[q.map]
      ? lrLink("quest", q.name, { map: q.map, x: q.x, y: q.y, giver: q.giver || q.name }) : esc(q.name)));
    const more = list.length - LR_QUEST_NAMES;
    if (more > 0) named.push(wordCount("page.level-report.quests.more", more, { n: num(more) }));
    if (!zone) return `<li>${word("page.level-report.quests.loose", { quests: andWords(named) })}</li>`;
    return `<li>${wordCount("page.level-report.quests.zone", list.length,
      { n: num(list.length), zone: zoneLink(zone, list[0].map ?? zoneMapNamed(zone)), quests: andWords(named) })}</li>`;
  });
  const rest = zones.slice(LR_QUEST_ZONES).reduce((n, [, list]) => n + list.length, 0);
  if (rest) out.push(`<li>${wordCount("page.level-report.quests.rest", rest, { n: num(rest) })}</li>`);
  return out;
}

const REACHED = wordsOf("page.level-report.reached");
const reachedLine = (text, level, where, on) => text.split("{where}").map((part) => fillWords(esc(part), { level, on })).join(where);

function reportHtml(r, who = "", random = Math.random) {
  const at = r.at ? new Date(r.at * 1000) : r.atDay ? new Date(r.atDay * 1000) : null;
  const day = at ? at.toLocaleDateString("en-GB", { day: "numeric", month: "short", year: "numeric" }) : "";
  const when = r.at ? word("page.level-report.when", { day, time: at.toLocaleTimeString("en-GB", { hour: "2-digit", minute: "2-digit" }) }) : day;
  const where = r.zone ? ` ${word("page.level-report.where", { zone: zoneLink(r.zone, zoneMapNamed(r.zone)) })}` : "";
  const reached = when
    ? reachedLine(REACHED.day, r.level, where, `<span class="lr-when">${esc(word("page.level-report.on", { when }))}</span>`)
    : reachedLine(reportMissingLine("when", random), r.level, where);
  const quips = [];
  const section = (title, lines) => (lines ? `<h3>${title}</h3><ul>${lines}</ul>` : "");
  const stats = statsLines(r, random, quips), skills = skillLines(r), numbers = numbersLines(r, random, quips);
  return `<h2 class="lr-title">${word("page.level-report.title", { level: r.level })}</h2>
    <p class="lr-who">${esc(who)}${who ? ". " : ""}${reached}</p>
    ${section(word("page.level-report.section.stats"), stats)}
    ${section(word("page.level-report.section.skills"), skills)}
    <h3>${word("page.level-report.section.new", { level: r.level })}</h3><ul>${unlockLines(r, skills)}</ul>
    ${section(word("page.level-report.section.time", { level: r.from }), numbers)}
    ${quips.length ? `<ul class="lr-quips">${quips.map((q) => `<li class="lr-missing">${q.title ? `<b class="lr-quip-title">${esc(q.title)}:</b> ` : ""}“${esc(q.line)}”</li>`).join("")}</ul>` : ""}`;
}


const POLAROID = { x: 0.69, y: 0.655, w: 0.165, tilt: 5, tiltLeast: 1.5, shift: 0.012, gap: 0.014 };
const POLAROID_CARD = { art: null, aspect: 1.2, window: [0.06, 0.05, 0.94, 0.78], strip: [0.78, 1] };
const polaroidFrame = { ...POLAROID_CARD };
function polaroidArt(m) {
  if (!m || !Array.isArray(m.window) || m.window.length !== 4 || !Array.isArray(m.strip) || !Array.isArray(m.size)) return false;
  Object.assign(polaroidFrame, { art: "art/polaroid.png", aspect: m.size[1] / m.size[0], window: m.window, strip: m.strip });
  return true;
}
getJson("art/polaroid.json", { key: null, quiet: true }).then((m) => {
  if (polaroidArt(m) && lr.open != null) showReport(lr.open);
}, () => {});

function polaroidHash(s) {
  let h = 2166136261;
  for (let k = 0; k < s.length; k++) h = Math.imul(h ^ s.charCodeAt(k), 16777619) >>> 0;
  h = Math.imul(h ^ (h >>> 16), 0x85ebca6b) >>> 0;
  h = Math.imul(h ^ (h >>> 13), 0xc2b2ae35) >>> 0;
  return (h ^ (h >>> 16)) >>> 0;
}
function polaroidPose(char, level) {
  const h = polaroidHash(`${char || ""}|${level}`);
  const u = (k) => ((h >>> (k * 8)) & 255) / 255;
  const way = u(3) < 0.5 ? -1 : 1;
  return { tilt: way * (POLAROID.tiltLeast + u(0) * (POLAROID.tilt - POLAROID.tiltLeast)),
           dx: (u(1) * 2 - 1) * POLAROID.shift, dy: (u(2) * 2 - 1) * POLAROID.shift };
}
function polaroidBox(pose, aspect = polaroidFrame.aspect) {
  const w = POLAROID.w, h = w * aspect, cx = POLAROID.x + pose.dx, cy = POLAROID.y + pose.dy;
  const a = Math.abs(pose.tilt) * Math.PI / 180, bw = w * Math.cos(a) + h * Math.sin(a), bh = w * Math.sin(a) + h * Math.cos(a);
  return { left: cx - w / 2, top: cy - h / 2, w, h, tilt: pose.tilt,
           bounds: { left: cx - bw / 2, top: cy - bh / 2, right: cx + bw / 2, bottom: cy + bh / 2 } };
}
const polaroidOn = () => options.get("polaroid");
const polaroidShown = (r) => !!(r?.shot && r.shot.id && polaroidOn());

function polaroidHtml(r, char) {
  if (!polaroidShown(r)) return "";
  const f = polaroidFrame, b = polaroidBox(polaroidPose(char, r.level), f.aspect), pct = (v) => `${(v * 100).toFixed(2)}%`;
  const at = r.shot.at || r.at;
  const day = at ? new Date(at * 1000).toLocaleDateString("en-GB", { day: "numeric", month: "short", year: "numeric" }) : "";
  const [wl, wt, wr, wb] = f.window, [st, sb] = f.strip;
  const lines = [r.zone, day].filter(Boolean).map((t) => `<span>${esc(t)}</span>`).join("");
  return `<button class="lr-polaroid${f.art ? "" : " card"}" data-lr-photo="${esc(r.shot.id)}" title="${word("page.level-report.photo.open")}"
      style="left:${pct(b.left)};top:${pct(b.top)};width:${pct(b.w)};height:${pct(b.h)};transform:rotate(${b.tilt.toFixed(2)}deg)">
    <img class="lr-pol-photo" src="/levelshot/${esc(r.shot.id)}.jpg" alt="${word("page.level-report.photo.alt", { level: r.level })}" draggable="false"
      style="left:${pct(wl)};top:${pct(wt)};width:${pct(wr - wl)};height:${pct(wb - wt)}">
    ${f.art ? `<img class="lr-pol-frame" src="${f.art}" alt="" draggable="false">` : ""}
    <span class="lr-pol-caption" style="left:4%;right:4%;top:${pct(st)};height:${pct(sb - st)}">${lines}</span></button>`;
}

function openPhoto(id) {
  const box = $("lr-photo");
  box.innerHTML = `<img src="/levelshot/${esc(id)}-big.jpg" alt="${word("page.level-report.photo.big.alt")}" draggable="false">`;
  box.hidden = false;
}
const closePhoto = () => { $("lr-photo").hidden = true; };
const photoOpen = () => !$("lr-photo").hidden;
closable(LAYER.reader + 0.5, photoOpen, closePhoto);
$("lr-photo").addEventListener("click", closePhoto);

function polaroidChanged() {
  if (lr.open != null) showReport(lr.open);
}
options.hooks.polaroid = { changed: polaroidChanged };


const lr = { char: null, reports: [], version: null, playing: null, open: null, at: null, asking: false };

function reportWho(r) {
  const c = alts.data?.chars?.[lr.char];
  const name = c ? altName(c) : "";
  const cls = r.className || c?.className || "";
  return [name, cls].filter(Boolean).join(", ");
}

function askReports() {
  if (lr.asking) return;
  const asked = getJson("/api/levelreports", { key: "level reports", quiet: true });
  if (!asked) return;
  lr.asking = true;
  asked.then((d) => {
    lr.asking = false;
    const moved = d.char !== lr.char;
    lr.char = d.char;
    lr.reports = d.reports || [];
    if (moved || lr.at == null || lr.at >= lr.reports.length) lr.at = lr.reports.length - 1;
    if (lr.open != null) showReport(lr.open);
    popNewest();
    if (app.drawer === "player") renderDrawer();
  }, () => { lr.asking = false; });
}
on("snapshot", (snap) => {
  const v = snap.versions?.levels;
  if (v !== lr.version || app.character !== lr.playing) {
    lr.version = v;
    lr.playing = app.character;
    askReports();
  }
  popNewest();
});

function popNewest() {
  if (!options.get("levelreport") || lr.open != null || app.state?.flags?.combat || !lr.char || lr.char !== app.character) return;
  if (!directorAllows("levelup")) return;
  const fresh = lr.reports.filter((r) => !r.seen);
  if (!fresh.length) return;
  showReport(fresh[fresh.length - 1].level);
  awayStart();
}

const LR_AWAY_WAIT_MS = 5000;
const LR_AWAY_COUNT = 10;
const LR_AWAY_TICK_MS = 1000;
const lrAway = { timer: 0, n: null, flying: false };

const onIndex = () => !document.hidden && document.hasFocus?.() !== false;

function awayStart() {
  awayStop();
  if (!onIndex()) lrAway.timer = setTimeout(awayTick, LR_AWAY_WAIT_MS);
}
function awayTick() {
  lrAway.n = lrAway.n == null ? LR_AWAY_COUNT : lrAway.n - 1;
  if (lrAway.n <= 0) return flyReport();
  const line = $("lr-countdown");
  line.textContent = word("page.level-report.countdown", { n: lrAway.n });
  line.classList.add("on");
  lrAway.timer = setTimeout(awayTick, LR_AWAY_TICK_MS);
}
function awayStop() {
  clearTimeout(lrAway.timer);
  Object.assign(lrAway, { timer: 0, n: null, flying: false });
  $("lr-countdown").classList.remove("on");
}
function awaySeen() {
  if (!lrAway.flying) awayStop();
}
addEventListener("focus", awaySeen);
document.addEventListener("visibilitychange", () => { if (onIndex()) awaySeen(); });

function flyReport() {
  const at = lr.reports.findIndex((r) => r.level === lr.open);
  if (at >= 0) lr.at = at;
  const drawer = app.drawer === "player";
  if (drawer) renderDrawer();
  $("lr-countdown").classList.remove("on");
  lrAway.flying = true;
  flyInto($("lr-scroll"), drawer ? $("drawer").querySelector(".lr-small-scroll") : $("btn-player"));
  lrAway.timer = setTimeout(closeReport, FLY_INTO_MS);
}

function placeReport() {
  const box = $("lr-scroll");
  if (!box || box.hidden) return;
  const cv = clearView(true), at = levelPlace(W, H, cv);
  Object.assign(box.style, { left: `${at.x}px`, top: `${at.y}px`, width: `${at.size}px`, height: `${at.size}px`, fontSize: `${at.font.toFixed(1)}px` });
  const x = box.querySelector(".lr-close"), map = $("map").getBoundingClientRect();
  const over = x ? cv.t + SCROLL_GAP - (x.getBoundingClientRect().top - map.top) : 0;
  if (over > 0) box.style.top = `${at.y + over}px`;
  shapeReport();
}
const lrWatch = new ResizeObserver(placeReport);
for (const el of [$("map"), $("alert")]) lrWatch.observe(el);

const LR_BLOCKS = "h2, p, h3, li";
function polaroidInset(y0, y1, bounds) {
  if (!bounds || y1 < bounds.top - POLAROID.gap || y0 > bounds.bottom + POLAROID.gap) return 0;
  return Math.max(0, LEVEL_TEXT.right - (bounds.left - POLAROID.gap));
}
function shapeReport() {
  const box = $("lr-scroll"), page = $("lr-page"), side = +box.offsetWidth || 0;
  if (box.hidden || !side) return;
  const top = LEVEL_SHAPE.page.top;
  const r = lr.reports.find((x) => x.level === lr.open);
  const pol = polaroidShown(r) ? polaroidBox(polaroidPose(lr.char, r.level)).bounds : null;
  for (const el of page.querySelectorAll(LR_BLOCKS)) {
    const y = el.offsetTop - page.scrollTop, y0 = top + y / side, y1 = top + (y + el.offsetHeight) / side;
    const inset = levelInset(y0, y1);
    inset.right = Math.max(inset.right, polaroidInset(y0, y1, pol));
    const left = `${(inset.left * side).toFixed(1)}px`, right = `${(inset.right * side).toFixed(1)}px`;
    if (el.style.marginLeft !== left) el.style.marginLeft = left;
    if (el.style.marginRight !== right) el.style.marginRight = right;
  }
}
let lrShaping = 0;
$("lr-page").addEventListener("scroll", () => {
  if (!lrShaping) lrShaping = askFrame(() => { lrShaping = 0; shapeReport(); });
}, { passive: true });
document.fonts?.addEventListener?.("loadingdone", shapeReport);
Object.assign($("lr-page").style, { left: `${(LEVEL_TEXT.left * 100).toFixed(2)}%`, width: `${((LEVEL_TEXT.right - LEVEL_TEXT.left) * 100).toFixed(2)}%` });

function showReport(level) {
  const r = lr.reports.find((x) => x.level === level);
  if (!r) return;
  lr.open = level;
  const box = $("lr-scroll");
  if (!box.querySelector(".lr-art").src) box.querySelector(".lr-art").src = LEVEL_ART.big;
  box.querySelector(".lr-seal-box").innerHTML = sealSvg(level);
  const page = $("lr-page"), kept = page.scrollTop;
  page.innerHTML = reportHtml(r, reportWho(r));
  $("lr-pol-box").innerHTML = polaroidHtml(r, lr.char);
  box.hidden = false;
  placeReport();
  page.scrollTop = kept;
}

function closeReport() {
  const level = lr.open;
  lr.open = null;
  awayStop();
  const box = $("lr-scroll");
  box.hidden = true;
  box.classList.remove("fly-into");
  Object.assign(box.style, { transform: "", opacity: "" });
  $("lr-page").scrollTop = 0;
  const r = lr.reports.find((x) => x.level === level);
  if (r && !r.seen && lr.char) {
    lr.reports.forEach((x) => { if (x.level <= level) x.seen = true; });
    postJson("/api/levelreports", { do: "seen", char: lr.char, level }, { quiet: true })?.catch(() => {});
  }
  if (app.drawer === "player") renderDrawer();
}
closable(LAYER.reader, () => lr.open != null, closeReport);

function reportClicked(e) {
  if (e.target.closest("button[data-lr-close]")) return closeReport();
  const photo = e.target.closest("button[data-lr-photo]");
  if (photo) return openPhoto(photo.dataset.lrPhoto);
  const b = e.target.closest("button[data-lr]");
  if (!b) return;
  const d = b.dataset;
  if (d.lr === "spell" || d.lr === "road") openTimelineAt(+d.level);
  else if (d.lr === "near") guideToKind(d.cat);
  else if (d.lr === "dungeon") openJournal(d.key);
  else if (d.lr === "zone") showZone(+d.map);
  else if (d.lr === "quest") guideToSpot(+d.map, +d.x, +d.y, d.giver, word("page.level-report.giver"));
  else if (d.lr === "gear") openGear();
  else return;
  closeReport();
}
$("lr-scroll").addEventListener("click", reportClicked);

function levelSmallHtml() {
  const r = lr.reports[lr.at];
  const back = lr.at > 0, on = lr.at < lr.reports.length - 1;
  return `<div class="lr-small${r ? "" : " none"}">
    <div class="lr-small-label">${word("page.level-report.small.label")}</div>
    <div class="lr-small-row">
      <button class="key small square lr-arrow" data-lr-step="-1"${back ? "" : " disabled"} title="${back ? word("page.level-report.small.step", { level: lr.reports[lr.at - 1].level }) : word("page.level-report.small.first")}">&lsaquo;</button>
      <button class="lr-small-scroll" data-lr-open="${r ? r.level : ""}"${r ? "" : " disabled"} title="${r ? word("page.level-report.small.open", { level: r.level }) : word("page.level-report.small.none")}">
        <img src="${LEVEL_ART.small}" alt=""><span class="lr-small-num">${r ? r.level : ""}</span></button>
      <button class="key small square lr-arrow" data-lr-step="1"${on ? "" : " disabled"} title="${on ? word("page.level-report.small.step", { level: lr.reports[lr.at + 1].level }) : word("page.level-report.small.last")}">&rsaquo;</button>
    </div></div>`;
}
on("playerHead", levelSmallHtml);

function levelSmallClicked(e) {
  const step = e.target.closest("button[data-lr-step]"), open = e.target.closest("button[data-lr-open]");
  if (step && !step.disabled) {
    lr.at = Math.max(0, Math.min(lr.reports.length - 1, lr.at + +step.dataset.lrStep));
    renderDrawer();
    if (lr.open != null && lr.reports[lr.at]) { $("lr-page").scrollTop = 0; showReport(lr.reports[lr.at].level); }
  } else if (open && !open.disabled) showReport(+open.dataset.lrOpen);
}
$("drawer").addEventListener("click", levelSmallClicked);
