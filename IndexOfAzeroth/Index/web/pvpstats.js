// The Index of Azeroth. Copyright 2026 Index Case <indexofazeroth@pm.me>. PolyForm Strict 1.0.0, see LICENSE.md.
"use strict";

const PVP_FILTERS = ["all", "one", "group", "wins", "losses", "away"];
const PVP_GROUPINGS = ["class", "race", "both"];
const PVP_SCHOOLS = [1, 2, 4, 8, 16, 32, 64];
const PVP_GAP = 5;
const PVP_HOURS = [[0, 6, "night"], [6, 12, "morning"], [12, 18, "afternoon"], [18, 24, "evening"]];
const PVP_TOP = 6;

const pvpWon = (r) => !r.duel && r.outcome === "won";
const pvpLost = (r) => !r.duel && r.outcome === "lost";
const pvpAway = (r) => r.outcome === "fled" || r.outcome === "escaped";

const pvpCounted = (rows, bgs) => rows.filter((r) => bgs || !r.bg);

function pvpShown(rows, { filter, search, bgs }, textOf, matches) {
  const keep = { all: () => true, one: (r) => r.one, group: (r) => !r.one, wins: pvpWon, losses: pvpLost, away: pvpAway };
  return pvpCounted(rows, bgs).filter((r) => keep[filter](r) && matches(textOf(r), search)).sort((a, b) => b.t - a.t);
}

function pvpRecord(rows) {
  const wins = rows.filter(pvpWon).length, losses = rows.filter(pvpLost).length;
  return { wins, losses, n: wins + losses };
}

const pvpRate = (rec) => (rec.n ? Math.round((rec.wins / rec.n) * 100) : null);

function pvpMost(rows) {
  const by = new Map();
  for (const r of rows) {
    const g = r.opp?.guid;
    if (!g) continue;
    const was = by.get(g) || { opp: r.opp, n: 0, t: 0 };
    by.set(g, { opp: r.opp, n: was.n + 1, t: Math.max(was.t, r.t) });
  }
  return [...by.values()].sort((a, b) => b.n - a.n || b.t - a.t)[0] || null;
}

function pvpGrouped(rows, keyOf) {
  const by = new Map();
  for (const r of rows) {
    if (!pvpWon(r) && !pvpLost(r)) continue;
    const k = keyOf(r);
    if (!k) continue;
    const g = by.get(k.key) || { ...k, wins: 0, losses: 0, n: 0 };
    if (pvpWon(r)) g.wins += 1; else g.losses += 1;
    g.n += 1;
    by.set(k.key, g);
  }
  return [...by.values()].sort((a, b) => b.n - a.n || b.wins - a.wins || String(a.key).localeCompare(String(b.key)));
}

function pvpMatchup(r, by) {
  const o = r.opp;
  if (!o) return null;
  const cls = o.cls ? { cls: o.cls, clsName: o.clsName } : null, race = o.race ? { race: o.race } : null;
  if (by === "class") return cls && { key: `c${o.cls}`, ...cls };
  if (by === "race") return race && { key: `r${o.race.name}`, ...race };
  return cls && race && { key: `c${o.cls}r${o.race.name}`, ...cls, ...race };
}

function pvpGap(r) {
  const yours = r.you?.level, theirs = r.opp?.level, least = r.opp?.least;
  if (!yours) return null;
  if (theirs) return theirs - yours >= PVP_GAP ? "above" : yours - theirs >= PVP_GAP ? "below" : "near";
  return least && least - yours >= PVP_GAP ? "above" : null;
}

function pvpPartOfDay(t) {
  const h = new Date(t * 1000).getHours();
  return PVP_HOURS.find(([a, b]) => h >= a && h < b)[2];
}

function pvpStats(rows, zoneOf, now = Date.now() / 1000) {
  const fights = rows.filter((r) => !r.duel).sort((a, b) => a.t - b.t);
  const record = pvpRecord(fights), one = pvpRecord(fights.filter((r) => r.one));
  let streak = 0, best = 0;
  for (const r of fights) {
    if (pvpWon(r)) best = Math.max(best, ++streak);
    else if (pvpLost(r)) streak = 0;
  }
  const midnight = new Date(now * 1000).setHours(0, 0, 0, 0) / 1000;
  const dealt = {};
  for (const r of fights) for (const [spell, n] of Object.entries(r.dealt)) dealt[spell] = (dealt[spell] || 0) + n;
  const spells = Object.entries(dealt).sort((a, b) => b[1] - a[1] || a[0].localeCompare(b[0]));
  const school = {};
  for (const r of fights) for (const [bits, n] of Object.entries(r.taken)) school[bits] = (school[bits] || 0) + n;
  const times = fights.filter((r) => pvpWon(r) && r.ttk != null).map((r) => r.ttk);
  return {
    record, rate: pvpRate(record), one,
    kbs: fights.reduce((s, r) => s + (r.kbs || 0), 0),
    assists: fights.reduce((s, r) => s + (r.assists || 0), 0),
    honour: fights.reduce((s, r) => s + (r.honour || 0), 0),
    today: fights.filter((r) => r.t >= midnight).reduce((s, r) => s + (r.honour || 0), 0),
    streak, best,
    nemesis: pvpMost(fights.filter((r) => pvpLost(r) && r.kb?.by === "them")),
    favourite: pvpMost(fights.filter(pvpWon)),
    most: spells.length ? { spell: spells[0][0], n: spells[0][1] } : null,
    least: spells.length > 1 ? { spell: spells[spells.length - 1][0], n: spells[spells.length - 1][1] } : null,
    matchups: Object.fromEntries(PVP_GROUPINGS.map((by) => [by, pvpGrouped(fights, (r) => pvpMatchup(r, by))])),
    outnumbered: pvpGrouped(fights.filter((r) => r.ours === 1), (r) => ({ key: Math.min(r.theirs, 3) }))
      .sort((a, b) => a.key - b.key),
    ganks: fights.filter((r) => pvpLost(r) && r.skull === "them").length,
    gap: pvpGrouped(fights, (r) => (pvpGap(r) ? { key: pvpGap(r) } : null)),
    zones: pvpGrouped(fights, (r) => (zoneOf(r) ? { key: zoneOf(r) } : null)).slice(0, PVP_TOP),
    hours: pvpGrouped(fights, (r) => ({ key: pvpPartOfDay(r.t) })),
    school: Object.entries(school).map(([bits, n]) => ({ school: +bits, n })).sort((a, b) => b.n - a.n),
    ttk: times.length ? Math.round((times.reduce((s, x) => s + x, 0) / times.length) * 10) / 10 : null,
  };
}

function pvpAgainst(rows, guid) {
  const met = rows.filter((r) => r.opp?.guid === guid || r.foes?.some((f) => f.guid === guid)).map((r) => r.t);
  return { ...pvpRecord(rows.filter((r) => r.opp?.guid === guid)),
    first: met.length ? Math.min(...met) : null, last: met.length ? Math.max(...met) : null };
}

const pvpSequence = (lines, autos) => (autos ? lines : lines.filter((x) => !x.auto));

if (typeof module === "object") {
  module.exports = { PVP_FILTERS, PVP_GROUPINGS, PVP_SCHOOLS, PVP_GAP, PVP_HOURS, pvpWon, pvpLost, pvpAway, pvpCounted,
    pvpShown, pvpRecord, pvpRate, pvpMost, pvpGrouped, pvpMatchup, pvpGap, pvpPartOfDay, pvpStats, pvpAgainst,
    pvpSequence };
}
