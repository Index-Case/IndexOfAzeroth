// The Index of Azeroth. Copyright 2026 Index Case <indexofazeroth@pm.me>. PolyForm Strict 1.0.0, see LICENSE.md.
"use strict";


const REPORT_MISSING = {
  played: [
    "A dwarf of the Explorers' League started counting your hours at this level, then found a dig site and forgot.",
    "The bronze dragons keep the hours of every level, and they aren't telling anyone how long this one took.",
    "Two Tauren elders argued over how long this level took you. They agreed that it was a while.",
    "The goblin who sells hourglasses in Booty Bay wants a deposit before he says how long you spent here.",
    "Brann Bronzebeard wrote down how long you spent at this level, and then he lost the notebook.",
    "A night elf sentinel kept time for this level, but she counts in moons and she is still waiting for one.",
  ],
  gold: [
    "A Venture Company accountant took your ledger for this level and has not come back.",
    "The bankers of Ironforge were closed for a holiday that nobody else has heard of.",
    "The goblins of Gadgetzan counted your gold for this level and kept the total as their fee.",
    "A Defias bookkeeper had your gold count for this level. Nobody has seen him since the Deadmines.",
    "A kobold was put in charge of your gold count. He only wanted the candle.",
    "The Steamwheedle Cartel will tell you what you made at this level, for a small consideration.",
  ],
  goldHour: [
    "The goblins of the Gadgetzan auction house tried to count your gold per hour and are still arguing about the decimal.",
    "A gnome in Tinker Town is building a machine to work out your gold per hour. He has been building it for some time.",
    "The apothecaries of the Undercity were asked for your gold per hour. They sent back a vial, which helped nobody.",
    "A Booty Bay pirate offered to work out your gold per hour, but he only counts in doubloons.",
    "An ogre in Dire Maul was given your gold per hour to count. He got as far as two.",
    "The dwarves of the Ironforge mint weighed your gold, but nobody gave them the hours to weigh it against.",
  ],
  pace: [
    "A gnome engineer was timing your level with a stopwatch. The stopwatch exploded.",
    "The night elves measured your pace in centuries and found this level too short to write down.",
    "A Darkspear troll watched you level and says you were quick. He gave no number.",
    "The Kirin Tor have a spell for your levelling speed, and the apprentice who knew it is a sheep this week.",
    "A goblin bookmaker took bets on how fast you would level and left town before paying out.",
    "A kodo herder from Mulgore timed your level against his slowest kodo. The kodo has not finished yet.",
  ],
  kills: [
    "The Argent Dawn sent a clerk to count your kills at this level. He is still counting the boars.",
    "A murloc kept the count of your kills at this level. Nobody can read what he wrote.",
    "The Scourge claim some of your kills as their own and are disputing the count.",
    "A Forsaken apothecary says your kills will be counted once they stop getting back up.",
    "The spirit healers keep a list of everyone you sent their way, and they don't share it.",
    "A Kodo herder offered to tally your kills, but he only counts in kodos.",
  ],
  spell: [
    "The Kirin Tor asked all over Dalaran about your favourite spell. Nobody would say.",
    "A gnome counted every spell you cast at this level and then turned himself into a sheep by mistake.",
    "Your class trainer has a guess at your favourite spell and keeps it to themselves.",
    "The Shen'dralar keep a book of everyone's favourite spells, and the page with yours is missing.",
    "A murloc watched every spell you cast at this level and liked all of them the same.",
    "The shamans of the Earthen Ring asked the elementals about your favourite spell and got four different answers.",
  ],
  stats: [
    "A dwarf of Ironforge measured your new strength with a hammer and wrote nothing down.",
    "The druids of the Cenarion Circle say you grew this level, but they measure growth in tree rings.",
    "A goblin offered to weigh your new stats on his scales, for a fee that he hasn't named yet.",
    "The scribes of Stormwind write down a level's new stats when you next log out or reload, and not a moment before.",
    "An Orgrimmar grunt sized you up after this level and said you look about the same.",
    "The gnomes built a machine to read your new stats. The machine is in Gnomeregan, which is a problem.",
  ],
  when: [
    "You reached level {level}{where} at some point in the last few days. The goblin keeping the calendar was paid by the hour and saw no reason to rush.",
    "You reached level {level}{where}, sometime. A gnome had a clock on it, and the clock is now a small fire.",
    "You reached level {level}{where} while nobody was looking. The bronze dragons know when, and they're not saying.",
    "You reached level {level}{where} on a day the scribes of Stormwind took off. They have written it down as 'recently'.",
    "You reached level {level}{where}. A Tauren elder says it was a few moons ago. A night elf says it was a moment ago. Both are sure.",
    "You reached level {level}{where} at an hour the Undercity's clocks don't keep, since nobody there needs to know when lunch is.",
  ],
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
const LR_STAT_WORDS = { str: "Strength", agi: "Agility", sta: "Stamina", int: "Intellect", spi: "Spirit" };
const andWords = (list) => (list.length < 2 ? list.join("") : `${list.slice(0, -1).join(", ")} and ${list[list.length - 1]}`);
const plural = (n, one, many) => `${num(n)} ${n === 1 ? one : many}`;
const LR_QUEST_ZONES = 5, LR_QUEST_NAMES = 4;

function zoneMapNamed(name) {
  if (!name) return null;
  const hit = Object.entries(app.maps || {}).find(([, m]) => m.name === name);
  return hit ? +hit[0] : null;
}
const zoneLink = (name, map) => (map != null && app.maps?.[map] ? lrLink("zone", name || app.maps[map].name, { map }) : esc(name || ""));

const REPORT_MISSING_TITLE = {
  played: (lv) => `Time spent at level ${lv}`, gold: (lv) => `Gold made at level ${lv}`, goldHour: () => "Gold an hour",
  pace: () => "Experience an hour", kills: (lv) => `Kills at level ${lv}`, spell: (lv) => `Favourite spell at level ${lv}`,
  stats: () => "Your new stats",
};
const quipLine = (quips, what, random, level) =>
  (quips.push({ title: REPORT_MISSING_TITLE[what]?.(level) || "", line: reportMissingLine(what, random) }), "");

function fightLines(r) {
  const before = r.from, out = [];
  if (r.deaths != null) {
    out.push(r.deaths === 0 ? `<li>You didn't die once at level ${before}.</li>`
      : `<li>You died ${r.deaths === 1 ? "once" : `${num(r.deaths)} times`} at level ${before}.</li>`);
  }
  if (r.dealt != null) out.push(`<li>You dealt ${num(r.dealt)} damage at level ${before}.</li>`);
  if (r.taken != null) out.push(`<li>You took ${num(r.taken)} damage at level ${before}.</li>`);
  if (r.fighting > 0) out.push(`<li>You spent ${esc(clock(r.fighting))} in fights at level ${before}.</li>`);
  return out.join("");
}

function numbersLines(r, random, quips = []) {
  const before = r.from, out = [];
  const miss = (what) => quipLine(quips, what, random, before);
  const hours = r.played > 0 ? r.played / 3600 : null;
  out.push(r.played > 0 ? `<li>You spent ${esc(clock(r.played))} at level ${before}.</li>` : miss("played"));
  if (r.gold == null) out.push(miss("gold"));
  else if (r.gold > 0) out.push(`<li>You made ${money(r.gold)} at level ${before}.</li>`);
  else if (r.gold < 0) out.push(`<li>You spent ${money(-r.gold)} more than you made at level ${before}.</li>`);
  else out.push(`<li>Your gold stayed the same at level ${before}.</li>`);
  out.push(r.gold > 0 && hours ? `<li>You made ${money(Math.round(r.gold / hours))} an hour at level ${before}.</li>` : r.gold != null && r.gold <= 0 ? "" : miss("goldHour"));
  out.push(r.xpLevel && hours ? `<li>You earned ${num(r.xpLevel / hours)} experience an hour at level ${before}.</li>` : miss("pace"));
  if (r.counting && r.kills == null && !r.spell) {
    out.push(`<li>Your kills and favourite spell at level ${before} are still being counted.</li>`);
    return out.join("");
  }
  out.push(r.kills != null ? `<li>You killed ${plural(r.kills, "enemy", "enemies")} at level ${before}.</li>` : miss("kills"));
  out.push(fightLines(r));
  out.push(r.spell ? `<li>Your favourite spell at level ${before} was ${lrLink("spell", r.spell.name, { level: r.spell.level || before })}.</li>` : miss("spell"));
  return out.join("");
}

function statsLines(r, random, quips = []) {
  const s = r.stats || {}, out = [];
  const went = (word, was, now, by) => (was != null && now != null && was !== now ? `<li>Your ${word} went up from ${num(was)} to ${num(now)}.</li>`
    : by ? `<li>Your ${word} went up by ${num(by)}.</li>` : "");
  out.push(went("health", s.wasHealth, s.nowHealth, s.health), went("mana", null, null, s.mana));
  const gains = Object.keys(LR_STAT_WORDS).filter((k) => s[k] != null);
  for (const k of gains) if (s[k] > 0) out.push(k === "spi" ? went("Spirit", s.wasSpirit, s.nowSpirit, s.spi) : `<li>Your ${LR_STAT_WORDS[k]} went up by ${num(s[k])}.</li>`);
  if (!gains.length && s.wasSpirit != null && s.nowSpirit != null) out.push(went("Spirit", s.wasSpirit, s.nowSpirit));
  if (s.talents > 0) out.push(`<li>You have ${plural(s.talents, "new talent point", "new talent points")}.</li>`);
  if (!gains.length && !out.some(Boolean)) quipLine(quips, "stats", random, r.level);
  return out.join("");
}

function gatedLine(e) {
  const at = { level: e.level };
  if (e.kind === "talent" && e.spent) return `<li>You can now pick ${lrLink("road", "talents", at)} that ask for ${e.spent} points spent.</li>`;
  if (e.kind === "talent") return `<li>You can now spend ${lrLink("road", "talent points", at)}.</li>`;
  if (e.kind === "milestone") return `<li>This level gives you a ${lrLink("road", "milestone talent point", at)}.</li>`;
  const teacher = e.at ? ` from ${lrLink("near", e.kind === "riding" ? "a riding trainer" : e.kind === "weapon" ? "a weapon master" : "your trainer", { cat: e.at })}` : "";
  return `<li>You can now learn ${lrLink("road", e.name, at)}${teacher}.</li>`;
}

function skillLines(r) {
  const u = r.unlocks;
  if (!u) return "";
  const out = [];
  const spells = (u.spells || []).filter((s) => !s.pet), pets = (u.spells || []).filter((s) => s.pet);
  for (const s of spells) out.push(`<li>${lrLink("spell", s.name, { level: s.level })}${s.rank ? ` (${esc(s.rank)})` : ""} is at your class trainer now.</li>`);
  if (spells.length) {
    const cost = spells.every((s) => s.cost != null) ? spells.reduce((sum, s) => sum + s.cost, 0) : null;
    out.push(`<li>Your ${lrLink("near", "class trainer", { cat: "class" })} teaches ${spells.length === 1 ? "this spell" : "these spells"}${cost ? ` for ${spells.length > 1 ? word("page.price.total", { money: money(cost) }) : money(cost)}` : ""}.</li>`);
  }
  for (const s of pets) out.push(`<li>${lrLink("spell", s.name, { level: s.level })}${s.rank ? ` (${esc(s.rank)})` : ""} is at a ${lrLink("near", "pet trainer", { cat: "pettrainer" })} now.</li>`);
  for (const e of u.gated || []) out.push(gatedLine(e));
  for (const t of u.talents || []) {
    out.push(`<li>Take <img class="lr-icon" src="/fileicon/${esc(t.icon)}.jpg" alt="">${lrLink("road", t.name, { level: t.level })}${
      t.ranks > 1 ? ` (rank ${t.rank} of ${t.ranks})` : ""} with this point.</li>`);
  }
  return out.join("");
}

function unlockLines(r, skills = "") {
  const u = r.unlocks;
  if (!u) return `<li class="lr-missing">The scribes are still writing down what level ${r.level} opened for you.</li>`;
  const out = [];
  for (const d of u.dungeons || []) {
    out.push(d.why === "door" ? `<li>${lrLink("dungeon", d.name, { key: d.key })} lets you in now.</li>` : `<li>${lrLink("dungeon", d.name, { key: d.key })} is at your level now.</li>`);
  }
  for (const z of u.zones || []) if (app.maps?.[z.map]) out.push(`<li>${zoneLink(app.maps[z.map].name, z.map)} is at your level now.</li>`);
  for (const g of u.gear || []) {
    out.push(`<li>You can now wear ${`<button class="lr-link" data-lr="gear" data-tip="${esc(g.id)}">${esc(g.name || `Item ${g.id}`)}</button>`}, which is in your bags.</li>`);
  }
  out.push(...questLines(u.quests || []));
  if (!out.length && !skills) out.push(`<li>Level ${r.level} opens nothing new for you.</li>`);
  if ((u.dungeons || []).length || (u.gear || []).length) out.push(`<li>Your ${lrLink("gear", "Next upgrades")} show the dungeon gear for your new level.</li>`);
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
    if (list.length > LR_QUEST_NAMES) named.push(`${plural(list.length - LR_QUEST_NAMES, "more quest", "more quests")}`);
    if (!zone) return `<li>You can also take ${andWords(named)}.</li>`;
    return `<li>${zoneLink(zone, list[0].map ?? zoneMapNamed(zone))} has ${plural(list.length, "new quest", "new quests")} for you: ${andWords(named)}.</li>`;
  });
  const rest = zones.slice(LR_QUEST_ZONES).reduce((n, [, list]) => n + list.length, 0);
  if (rest) out.push(`<li>Other zones have ${plural(rest, "more new quest", "more new quests")} for you.</li>`);
  return out;
}

function reportHtml(r, who = "", random = Math.random) {
  const at = r.at ? new Date(r.at * 1000) : r.atDay ? new Date(r.atDay * 1000) : null;
  const day = at ? at.toLocaleDateString("en-GB", { day: "numeric", month: "short", year: "numeric" }) : "";
  const when = r.at ? `${day} at ${at.toLocaleTimeString("en-GB", { hour: "2-digit", minute: "2-digit" })}` : day;
  const where = r.zone ? ` in ${zoneLink(r.zone, zoneMapNamed(r.zone))}` : "";
  const reached = when ? `You reached level ${r.level}${where} <span class="lr-when">on ${esc(when)}</span>.`
    : reportMissingLine("when", random).split("{where}").map((part) => esc(part.replace("{level}", r.level))).join(where);
  const quips = [];
  const section = (title, lines) => (lines ? `<h3>${title}</h3><ul>${lines}</ul>` : "");
  const stats = statsLines(r, random, quips), skills = skillLines(r), numbers = numbersLines(r, random, quips);
  return `<h2 class="lr-title">Congratulations on level ${r.level}</h2>
    <p class="lr-who">${esc(who)}${who ? ". " : ""}${reached}</p>
    ${section("Your new stats", stats)}
    ${section("New skills and talents", skills)}
    <h3>New at level ${r.level}</h3><ul>${unlockLines(r, skills)}</ul>
    ${section(`Your time at level ${r.from}`, numbers)}
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
  return `<button class="lr-polaroid${f.art ? "" : " card"}" data-lr-photo="${esc(r.shot.id)}" title="This opens the picture large"
      style="left:${pct(b.left)};top:${pct(b.top)};width:${pct(b.w)};height:${pct(b.h)};transform:rotate(${b.tilt.toFixed(2)}deg)">
    <img class="lr-pol-photo" src="/levelshot/${esc(r.shot.id)}.jpg" alt="Where you were at level ${r.level}" draggable="false"
      style="left:${pct(wl)};top:${pct(wt)};width:${pct(wr - wl)};height:${pct(wb - wt)}">
    ${f.art ? `<img class="lr-pol-frame" src="${f.art}" alt="" draggable="false">` : ""}
    <span class="lr-pol-caption" style="left:4%;right:4%;top:${pct(st)};height:${pct(sb - st)}">${lines}</span></button>`;
}

function openPhoto(id) {
  const box = $("lr-photo");
  box.innerHTML = `<img src="/levelshot/${esc(id)}-big.jpg" alt="Where you were when you levelled up" draggable="false">`;
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
  if (lr.open != null || app.state?.flags?.combat || !lr.char || lr.char !== app.character) return;
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
  else if (d.lr === "quest") guideToSpot(+d.map, +d.x, +d.y, d.giver, "a quest giver");
  else if (d.lr === "gear") openGear();
  else return;
  closeReport();
}
$("lr-scroll").addEventListener("click", reportClicked);

function levelSmallHtml() {
  const r = lr.reports[lr.at];
  const back = lr.at > 0, on = lr.at < lr.reports.length - 1;
  return `<div class="lr-small${r ? "" : " none"}">
    <div class="lr-small-label">Level report</div>
    <div class="lr-small-row">
      <button class="key small square lr-arrow" data-lr-step="-1"${back ? "" : " disabled"} title="${back ? `The level ${lr.reports[lr.at - 1].level} report` : "There is no earlier level report"}">&lsaquo;</button>
      <button class="lr-small-scroll" data-lr-open="${r ? r.level : ""}"${r ? "" : " disabled"} title="${r ? `This opens the level ${r.level} report` : "The first level report comes with the next level up"}">
        <img src="${LEVEL_ART.small}" alt=""><span class="lr-small-num">${r ? r.level : ""}</span></button>
      <button class="key small square lr-arrow" data-lr-step="1"${on ? "" : " disabled"} title="${on ? `The level ${lr.reports[lr.at + 1].level} report` : "There is no later level report"}">&rsaquo;</button>
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
