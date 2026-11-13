// The Index of Azeroth. Copyright 2026 Index Case <indexofazeroth@pm.me>. PolyForm Strict 1.0.0, see LICENSE.md.
"use strict";

const PF_SCHOOLS = { 1: "physical", 2: "holy", 4: "fire", 8: "nature", 16: "frost", 32: "shadow", 64: "arcane" };
const PF_BAR = 90;
const pfW = (key, fill) => pvW(`fight.${key}`, fill);
const pfSecs = (s) => (Math.round(s * 10) / 10).toFixed(1);
const pfDay = (t) => new Date(t * 1000).toLocaleDateString("en-GB", { day: "numeric", month: "short" });
const pfNone = () => `<span class="pf-none" title="${esc(pfW("card.none.tip"))}">${esc(pfW("card.none"))}</span>`;
const pfLabel = (key) => `<span class="pf-label">${esc(pfW(key))}</span>`;

function pfWho(o, g, short) {
  const p = o.people?.[g];
  if (!p) return "";
  const name = short && p.kind === "player" ? String(p.name || "").split(" ")[0] : p.name;
  return `<span class="pf-who"${name !== p.name ? ` title="${esc(p.name)}"` : ""}>${p.cls ? pvClassIcon(p.cls, p.clsName || "") : ""}${pvName(name, p.clsName)}</span>`;
}

const pfSpell = (o, name) => (name ? `${pvIcon(o.icons?.[name], name)}<span class="pf-sp">${esc(name)}</span>`
  : `${pvIcon(PVP_ICONS.melee)}<span class="pf-sp">${esc(pfW("seq.melee"))}</span>`);

function pfHealth(o, g, h, mh) {
  const tip = pfW("seq.health.tip", { name: o.people?.[g]?.name, health: num(h), most: num(mh) });
  return `<span class="pf-hp-box" title="${esc(tip)}"><span class="pf-hp"><i style="width:${Math.round((h / mh) * 100)}%"></i></span><span class="pf-hp-n">${num(h)}</span></span>`;
}


function pfCardHtml(o) {
  const p = o.opp || {}, n = o.numbersOf, none = pfNone();
  const value = (v) => (v == null || v === "" ? none : esc(typeof v === "number" ? num(v) : v));
  const tags = (names, label) => (names.length ? names.map((s) => `<span class="pf-tag">${pvIcon(o.icons?.[s.name || s], s.name || s)}${esc(label ? label(s) : s)}</span>`).join("") : none);
  const fact = (key, body, tip = "") => `<div class="pf-fact"${tip ? ` title="${esc(tip)}"` : ""}>${pfLabel(key)}<span class="pf-val">${body}</span></div>`;
  const numbers = n ? pfW("card.numbers.tip") : "";
  const facts = [fact("card.level", p.guid ? pvLevel(p) : none),
    fact("card.guild", value(p.guild)), fact("card.ilvl", value(n?.lv), numbers), fact("card.health", value(n?.mh), numbers),
    fact("card.ap", value(n?.ap), numbers), fact("card.sp", value(n?.sp), numbers), fact("card.armour", value(n?.ar), numbers),
    !n || n.mp != null ? fact("card.mana", value(n?.mp), numbers) : "",
    fact("card.talents", tags(o.seen?.talents || [], (t) => pfW("card.talent", { name: t.name, tree: t.tree }))),
    fact("card.racials", tags(o.seen?.racials || [])), fact("card.buffs", tags(o.carried || []))].join("");
  const rec = pvpAgainst(pvpCounted(pv.data?.fights || [], pv.bgs), p.guid);
  const met = rec.first == null ? "" : pfDay(rec.first) === pfDay(rec.last) ? pfW("record.met.once", { first: pfDay(rec.first) })
    : pfW("record.met", { first: pfDay(rec.first), last: pfDay(rec.last) });
  const revenge = o.revenge ? pvIcon(PVP_ICONS.revenge, pvW(`table.revenge.${o.revenge}.tip`)) : "";
  const who = [p.title, p.guild ? `<${p.guild}>` : ""].filter(Boolean).join(" ");
  return `<div class="pf-card-head">${pvClassIcon(p.cls, p.clsName || "")}${p.race?.icon ? pvIcon(p.race.icon, p.race.name) : ""}<span class="pf-card-name"${who ? ` title="${esc(who)}"` : ""}>${pvName(p.name, p.clsName)}</span></div>
    <div class="pf-facts">${facts}</div>
    <div class="pf-record">${pfLabel("record")}<span class="pf-val">${pvWL(rec)}${revenge}</span>${met ? `<span class="pf-dim">${esc(met)}</span>` : ""}</div>`;
}


function pfMapHtml(o) {
  const p = o.at && { inst: o.at[0], n: o.at[1], w: o.at[2] };
  const map = (p && (zoneOfShape(p) || zoneHolding(p))) || o.map;
  if (o.bg || !map || !app.maps?.[map]) return "";
  const f = p && worldToFrac(map, p);
  const pin = f && f[0] >= 0 && f[0] <= 1 && f[1] >= 0 && f[1] <= 1
    ? `<span class="pf-pin" style="left:${(f[0] * 100).toFixed(2)}%;top:${(f[1] * 100).toFixed(2)}%"></span>` : "";
  return `<div class="pf-map" title="${esc(pfW("map.tip"))}"><img src="${esc(worldMapSrc(map))}" alt="" draggable="false">${pin}</div>`;
}

function pfLineHtml(o) {
  const fact = (key, body, tip = "") => `<div class="pf-fact"${tip ? ` title="${esc(tip)}"` : ""}>${pfLabel(key)}<span class="pf-val">${body}</span></div>`;
  const facts = [fact("fact.result", pvResultCell(o)), o.kb ? fact("fact.kb", pvKillCell(o)) : "",
    fact("fact.time", esc(pfW("fact.seconds", { n: pfSecs(o.secs) }))),
    o.ttk != null ? fact("fact.ttk", esc(pfW("fact.seconds", { n: pfSecs(o.ttk) })), pfW("fact.ttk.tip")) : "",
    o.struck ? fact("fact.struck", esc(pfW(`fact.struck.${o.struck}`))) : "", o.honour ? fact("fact.honour", pvHonourCell(o)) : "",
    fact("fact.where", pvWhereCell(o)), fact("fact.when", esc(pvWhen(o.t)))].join("");
  const players = (side) => Object.entries(o.people || {}).filter(([, p]) => p.side === side && p.fought)
    .map(([g]) => `<span class="pf-person">${pfWho(o, g)}</span>`).join("");
  return `<div class="pf-band"><div class="pf-band-facts"><div class="pf-line-facts">${facts}</div>
    <div class="pf-sides"><div class="pf-side-list">${pfLabel("num.you")}${players("you")}</div><div class="pf-side-list">${pfLabel("num.them")}${players("them")}</div></div></div>
    ${pfMapHtml(o)}</div>`;
}


const pfAt = (rows, t) => { let got = null; for (const r of rows || []) { if (r[0] > t) break; got = r; } return got && [got[1], got[2]]; };

function pfStripHtml(o) {
  const me = o.health?.[o.me], them = o.health?.[o.opp?.guid];
  if (!me && !them) return "";
  const span = Math.max(o.secs, ...[...(me || []), ...(them || [])].map((r) => r[0]), 0.1);
  const x = (s) => ((s / span) * 1000).toFixed(1), y = (h, mh) => (98 - (h / mh) * 94).toFixed(1);
  const line = (rows, cls, colour) => {
    if (!rows) return "";
    const pts = [];
    rows.forEach(([s, h, mh], i) => { if (i) pts.push(`${x(s)},${y(rows[i - 1][1], rows[i - 1][2])}`); pts.push(`${x(s)},${y(h, mh)}`); });
    const [, h, mh] = rows[rows.length - 1];
    pts.push(`1000,${y(h, mh)}`);
    return `<polyline class="${cls}" points="${pts.join(" ")}"${colour ? ` style="stroke:${esc(colour)}"` : ""}/>`;
  };
  const name = o.opp?.name || "", colour = CLASS_COLORS[o.opp?.clsName] || "";
  const shown = (got) => (got ? `${num(got[0])}/${num(got[1])}` : pfW("strip.unknown"));
  const times = [...new Set([0, ...[...(me || []), ...(them || [])].map((r) => r[0])])].sort((a, b) => a - b);
  const slices = times.map((t, i) => {
    const to = i + 1 < times.length ? times[i + 1] : span;
    const tip = pfW("strip.tip", { time: pfSecs(t), you: shown(pfAt(me, t)), them: shown(pfAt(them, t)), name });
    return `<span style="left:${((t / span) * 100).toFixed(2)}%;width:${(((to - t) / span) * 100).toFixed(2)}%" title="${esc(tip)}"></span>`;
  }).join("");
  const kb = (o.lines || []).find((l) => l.kb);
  const skull = kb ? `<span class="pf-strip-kb" style="left:${((Math.max(0, kb.s) / span) * 100).toFixed(2)}%">${pvIcon(PVP_ICONS.skull, pfW("strip.kb"))}</span>` : "";
  return `<div class="pf-strip-box"><div class="pf-strip-head">${pfLabel("strip")}<span class="pf-key you">${esc(o.people?.[o.me]?.name || "")}</span>${them ? `<span class="pf-key them"${colour ? ` style="color:${esc(colour)}"` : ""}>${esc(name)}</span>` : ""}</div>
    <div class="pf-strip"><svg viewBox="0 0 1000 100" preserveAspectRatio="none">${line(me, "you")}${line(them, "them", colour)}</svg>
    <div class="pf-strip-hover">${slices}</div>${skull}</div>
    <div class="pf-strip-ends"><span>${esc(pfW("strip.start"))}</span><span>${esc(pfW("strip.end", { n: pfSecs(span) }))}</span></div></div>`;
}


function pfUsed(o, used) {
  if (!used.length) return esc(pfW("num.none"));
  return used.map((u) => {
    const kind = pfW(`used.${u.kind}`), cost = u.cost ? moneyText(u.cost) : null;
    const key = cost ? "used.cost.tip" : "used.tip";
    const tip = pfW(u.n === 1 ? `${key}.one` : key, { spell: u.sp, kind, n: u.n, cost });
    return `<span class="pf-used" title="${esc(tip)}">${pvIcon(o.icons?.[u.sp], tip)}${u.n > 1 ? `<small>${u.n}</small>` : ""}</span>`;
  }).join("");
}

function pfSchools(school, most) {
  const parts = Object.entries(school).sort((a, b) => b[1] - a[1]);
  if (!parts.length) return esc(pfW("num.none"));
  const total = parts.reduce((s, [, n]) => s + n, 0);
  const pieces = parts.map(([bits, n]) => {
    const tip = `${PF_SCHOOLS[bits] ? pvW(`stats.school.${bits}`) : bits}: ${num(n)}`;
    return `<i style="flex:${n};background:var(--school-${PF_SCHOOLS[bits] || "physical"})" title="${esc(tip)}"></i>`;
  }).join("");
  return `<span class="pf-bar" style="width:${Math.max(4, Math.round((total / most) * PF_BAR))}px">${pieces}</span>`;
}

function pfNumbersHtml(o) {
  const you = o.numbers.you, them = o.numbers.them;
  const row = (key, a, b, tip = "") => `<div class="pf-num-row"${tip ? ` title="${esc(tip)}"` : ""}><span class="pf-num you">${a}</span>${pfLabel(key)}<span class="pf-num them">${b}</span></div>`;
  const count = (n) => num(n || 0);
  const secs = (v) => esc(pfW("num.seconds", { n: pfSecs(v) }));
  const big = (b) => (b ? `${b.sp ? pvIcon(o.icons?.[b.sp], b.sp) : pvIcon(PVP_ICONS.melee)}${num(b.a)}` : esc(pfW("num.none")));
  const most = Math.max(1, ...[you.school, them.school].map((s) => Object.values(s).reduce((a, n) => a + n, 0)));
  const spent = (n) => (n.spent ? money(n.spent) : esc(pfW("num.none")));
  return `<div class="pf-numbers"><div class="pf-num-row pf-num-head"><span class="pf-num you">${esc(pfW("num.you"))}</span><span></span><span class="pf-num them">${esc(pfW("num.them"))}</span></div>
    ${row("num.damage", count(you.damage), count(them.damage))}${row("num.healing", count(you.healing), count(them.healing))}
    ${row("num.biggest", big(you.biggest), big(them.biggest))}${row("num.burst", count(you.burst), count(them.burst), pfW("num.burst.tip"))}
    ${row("num.held", secs(you.held), secs(them.held), pfW("num.held.tip"))}${row("num.interrupts", count(you.interrupts), count(them.interrupts))}
    ${row("num.dispels", count(you.dispels), count(them.dispels))}${row("num.purges", count(you.purges), count(them.purges))}
    ${row("num.immune", count(you.immune), count(them.immune), pfW("num.immune.tip"))}
    ${row("num.school", pfSchools(you.school, most), pfSchools(them.school, most))}
    ${row("num.used", pfUsed(o, you.used), pfUsed(o, them.used), pfW("num.used.tip"))}${row("num.spent", spent(you), spent(them), pfW("num.spent.tip"))}</div>`;
}

function pfRecapHtml(o) {
  if (!o.recap?.lines.length) return "";
  const rows = o.recap.lines.map((i) => o.lines[i]).map((x) => `<div class="pf-recap-row${x.kb ? " kb" : ""}">
    <span class="pf-s">${esc(pfW("recap.before", { secs: pfSecs(x.s - o.recap.s) }))}</span><span class="pf-recap-who">${pfWho(o, x.by, true)}</span>
    <span class="pf-recap-spell">${pfSpell(o, x.sp)}</span><b class="pf-a${x.cr ? " crit" : ""}">${num(x.a || 0)}</b>
    <span class="pf-recap-hp">${x.h != null ? pfHealth(o, x.on, x.h, x.mh) : ""}</span>${x.kb ? pvIcon(PVP_ICONS.skull, pfW("seq.kb.tip"), "pf-kb") : ""}</div>`).join("");
  return `<div class="pf-recap" title="${esc(pfW("recap.tip"))}">${pfLabel("recap")}${rows}</div>`;
}


function pfAct(o, x, names) {
  if (x.k === "death") {
    const said = x.on === o.me ? pfW("seq.died.you") : pfW("seq.died", { name: o.people?.[x.on]?.name });
    return `${pvIcon(PVP_ICONS.skull)}<span class="pf-died">${esc(said)}</span>`;
  }
  const parts = [];
  if (names && x.by) parts.push(pfWho(o, x.by, true));
  parts.push(pfSpell(o, x.sp));
  if (names && x.on && x.on !== x.by) parts.push(`<span class="pf-on">${esc(pfW("seq.on"))}${pfWho(o, x.on, true)}</span>`);
  if (x.k === "hit" && x.a != null) {
    parts.push(`<b class="pf-a${x.cr ? " crit" : ""}">${num(x.a)}</b>`);
    if (x.cr) parts.push(`<span class="pf-crit" title="${esc(pfW("seq.crit.tip"))}">${esc(pfW("seq.crit"))}</span>`);
  } else if (x.k === "heal") {
    parts.push(`<b class="pf-heal">+${num(x.a || 0)}</b>`);
    if (x.oh) parts.push(`<span class="pf-dim" title="${esc(pfW("seq.overheal.tip"))}">${esc(pfW("seq.overheal", { n: num(x.oh) }))}</span>`);
  } else if (x.k === "miss") {
    parts.push(`<span class="pf-miss">${esc(pfW(`miss.${String(x.m || "miss").toLowerCase()}`) || x.m)}</span>`);
  } else if (x.k === "cc") {
    parts.push(`<span class="pf-cc">${esc(pfW(`cc.${x.cc}`))}</span>`);
    parts.push(x.held != null ? `<b class="pf-held">${esc(pfW("seq.cc.held", { secs: pfSecs(x.held) }))}</b>`
      : `<span class="pf-dim" title="${esc(pfW("seq.cc.end.tip"))}">${esc(pfW("seq.cc.end"))}</span>`);
    if (x.broke) parts.push(`<span class="pf-dim">${pvIcon(o.icons?.[x.broke], x.broke)}${esc(pfW("seq.cc.broke", { spell: x.broke }))}</span>`);
    else if (x.broke === "") parts.push(`<span class="pf-dim">${esc(pfW("seq.cc.broke.hit"))}</span>`);
  } else if (x.k === "interrupt" || x.k === "dispel" || x.k === "purge") {
    parts.push(`<span class="pf-dim">${pvIcon(o.icons?.[x.x], x.x || "")}${esc(pfW(`seq.${x.k}`, { spell: x.x }))}</span>`);
  }
  if (x.ab) parts.push(`<span class="pf-dim">${esc(pfW("seq.absorb", { spell: x.ab[0], n: num(x.ab[1] || 0) }))}</span>`);
  if (x.h != null) parts.push(pfHealth(o, x.on, x.h, x.mh));
  if (x.kb) parts.push(pvIcon(PVP_ICONS.skull, pfW("seq.kb.tip"), "pf-kb"));
  return parts.join("");
}

function pfSequenceHtml(o) {
  const names = !o.one || new Set(o.lines.flatMap((x) => [x.by, x.on]).filter(Boolean)).size > 2;
  const lines = pvpSequence(o.lines, pv.autos);
  let html = lines.length && lines[0].s < 0 ? `<div class="pf-mark" title="${esc(pfW("seq.lead.tip"))}">${esc(pfW("seq.lead"))}</div>` : "";
  let began = false;
  for (const x of lines) {
    if (!began && x.s >= 0) {
      began = true;
      if (html) html += `<div class="pf-mark">${esc(pfW("seq.start"))}</div>`;
    }
    const act = pfAct(o, x, names);
    html += `<div class="pf-line ${x.k}${x.s < 0 ? " lead" : ""}${x.kb ? " kb" : ""}"><div class="pf-side you">${x.c === "you" ? act : ""}</div>
      <span class="pf-s">${pfSecs(x.s)}</span><div class="pf-side them">${x.c === "them" ? act : ""}</div></div>`;
  }
  return html;
}


function pfBodyHtml() {
  const o = pv.shown;
  if (!o) return `<p class="muted">${esc(pv.fightFailed ? pfW("failed") : pfW("loading"))}</p>`;
  const missing = o.missing?.length ? `<p class="pf-missing">${pvIcon(PVP_ICONS.notice)}${esc(pfW("seq.missing", { what: andList(o.missing.map((k) => pfW(`seq.missing.${k}`))) }))}</p>` : "";
  return `<div class="pf-top"><div class="pf-card">${pfCardHtml(o)}</div>
    <div class="pf-main">${pfLineHtml(o)}${pfStripHtml(o)}<div class="pf-under">${pfNumbersHtml(o)}${pfRecapHtml(o)}</div></div></div>
    <div class="pf-seq-bar"><label class="pv-check" title="${esc(pfW("seq.auto.tip"))}"><input type="checkbox" id="pf-autos"${pv.autos ? " checked" : ""}>${esc(pfW("seq.auto"))}</label>${missing}</div>
    <div class="pf-seq">${pfSequenceHtml(o)}</div>`;
}

function pfOpen(id) {
  pv.scroll = document.querySelector("#pvp .pv-scroll")?.scrollTop || 0;
  pv.fight = id;
  pv.shown = null;
  pv.fightFailed = false;
  renderPvp();
  const url = `/api/pvp/fight?char=${encodeURIComponent(pv.data?.char || "")}&id=${encodeURIComponent(id)}`;
  getJson(url, { force: true })?.then((j) => { if (pv.fight === id) { pv.shown = j; renderPvp(); } },
    () => { if (pv.fight === id) { pv.fightFailed = true; renderPvp(); } });
}

function pfBack() {
  pv.fight = null;
  pv.shown = null;
  renderPvp();
  const table = document.querySelector("#pvp .pv-scroll");
  if (table) table.scrollTop = pv.scroll;
}

$("pvp").addEventListener("click", (e) => {
  const b = e.target.closest("button");
  if (b?.dataset.back) return pfBack();
  const row = !b && e.target.closest("tr.pv-row");
  if (row) pfOpen(row.dataset.fight);
});
$("pvp").addEventListener("change", (e) => {
  if (e.target.id === "pf-autos") { pv.autos = e.target.checked; keepPvp(); renderPvp(); }
});
