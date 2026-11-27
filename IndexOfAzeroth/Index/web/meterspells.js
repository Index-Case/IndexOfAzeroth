// The Index of Azeroth. Copyright 2026 Index Case <indexofazeroth@pm.me>. PolyForm Strict 1.0.0, see LICENSE.md.
"use strict";

const MS_SUMS = typeof module === "object" ? { ...require("./meterstats.js"), ...require("./timechart.js"), ...require("./metertime.js") }
  : { meterShare, meterPerCast, rollingMedian, METER_SMOOTH_HALF };

const METER_SIDE_LEAST = 8;

function spellFights(fights) {
  const kept = fights.filter((f) => f.spells);
  return { kept, unrecorded: fights.length - kept.length };
}

const spellFigures = (x) => ({ hits: x.hits, dmg: x.dmg, avg: x.hits ? x.dmg / x.hits : null, crit: x.direct ? (x.crits / x.direct) * 100 : null });

function spellSides(fights, used) {
  const yes = fights.filter((f) => used.has(f)), no = fights.filter((f) => !used.has(f));
  const mean = (list) => list.reduce((s, f) => s + f.dps, 0) / list.length;
  const ok = yes.length >= METER_SIDE_LEAST && no.length >= METER_SIDE_LEAST;
  return { withDps: ok ? mean(yes) : null, withoutDps: ok ? mean(no) : null,
    need: { with: Math.max(0, METER_SIDE_LEAST - yes.length), without: Math.max(0, METER_SIDE_LEAST - no.length) } };
}

function spellTable(fights) {
  const by = new Map();
  let total = 0;
  for (const f of fights) {
    for (const s of f.spells) {
      if (!by.has(s.key)) {
        by.set(s.key, { key: s.key, id: s.id, name: s.name, by: s.by, dmg: 0, casts: 0, hits: 0, direct: 0, crits: 0, foes: 0, volleys: 0, blows: 0, used: new Set() });
      }
      const r = by.get(s.key);
      r.dmg += s.dmg; r.casts += s.casts; r.hits += s.hits; r.direct += s.direct; r.crits += s.crits;
      r.foes = Math.max(r.foes, s.foes); r.volleys += s.volleys; r.blows += s.blows;
      r.used.add(f);
      total += s.dmg;
    }
  }
  return [...by.values()].map((r) => ({ key: r.key, id: r.id, name: r.name, by: r.by, dmg: r.dmg, share: MS_SUMS.meterShare(r.dmg, total), casts: r.casts || null,
    perFight: r.casts ? r.casts / fights.length : null, ...spellFigures(r), perCast: MS_SUMS.meterPerCast(r), fights: r.used.size, ...spellSides(fights, r.used) }));
}

const SPELL_SORTS = { dmg: (r) => r.dmg, casts: (r) => r.casts, perFight: (r) => r.perFight, hits: (r) => r.hits, crit: (r) => r.crit, avg: (r) => r.avg,
  perCast: (r) => r.perCast,
  dps: (r) => (r.withDps == null ? null : r.withDps - r.withoutDps) };

function spellSorted(rows, sort) {
  const of = SPELL_SORTS[sort] || SPELL_SORTS.dmg, name = (r) => `${r.name ?? ""} ${r.by ?? ""}`;
  return [...rows].sort((a, b) => {
    const x = of(a), y = of(b);
    return (x == null) - (y == null) || (x == null ? 0 : y - x) || name(a).localeCompare(name(b));
  });
}

function spellSeries(fights, key) {
  const got = [];
  for (const f of [...fights].sort((a, b) => a.t - b.t)) {
    const s = f.spells.find((x) => x.key === key);
    if (s) got.push({ t: f.t, len: f.len, dmg: s.dmg, casts: s.casts, share: MS_SUMS.meterShare(s.dmg, f.dmg) });
  }
  const dmg = MS_SUMS.rollingMedian(got.map((p) => p.dmg), MS_SUMS.METER_SMOOTH_HALF);
  const casts = MS_SUMS.rollingMedian(got.map((p) => p.casts), MS_SUMS.METER_SMOOTH_HALF);
  return got.map((p, i) => ({ ...p, smoothDmg: dmg[i], smoothCasts: casts[i] }));
}

function spellAuras(fights, key) {
  const add = (to, x) => { to.dmg += x.dmg; to.hits += x.hits; to.direct += x.direct; to.crits += x.crits; return to; };
  const none = () => ({ dmg: 0, hits: 0, direct: 0, crits: 0 });
  const total = none(), under = new Map();
  for (const f of fights) {
    const row = f.spells.find((s) => s.key === key);
    if (!row) continue;
    add(total, row);
    for (const a of f.auras) {
      const part = a.whole ? row : row.split.find((p) => p.aura === a.key);
      if (!part) continue;
      if (!under.has(a.key)) under.set(a.key, { key: a.key, id: a.id, name: a.name, fights: 0, sums: none() });
      const u = under.get(a.key);
      add(u.sums, part);
      u.fights++;
    }
  }
  const minus = (a, b) => ({ dmg: a.dmg - b.dmg, hits: a.hits - b.hits, direct: a.direct - b.direct, crits: a.crits - b.crits });
  return [...under.values()].filter((u) => u.sums.hits > 0)
    .map((u) => ({ key: u.key, id: u.id, name: u.name, fights: u.fights, under: spellFigures(u.sums), without: spellFigures(minus(total, u.sums)) }))
    .sort((a, b) => b.under.hits - a.under.hits || String(a.name ?? "").localeCompare(String(b.name ?? "")));
}

function procTable(fights) {
  const by = new Map(), own = new Map();
  let len = 0;
  for (const f of fights) {
    len += f.len;
    for (const a of f.auras) {
      if (!by.has(a.key)) by.set(a.key, { key: a.key, id: a.id, name: a.name, times: 0, secs: 0 });
      const p = by.get(a.key);
      p.times += a.times;
      p.secs += a.secs;
    }
    for (const s of f.spells) {
      if (s.id == null || s.by || !s.hits) continue;
      if (!own.has(s.key)) own.set(s.key, { id: s.id, name: s.name, dmg: 0 });
      own.get(s.key).dmg += s.dmg;
    }
  }
  const done = (p) => {
    const hit = [...own.values()].filter((s) => s.id === p.id || (p.name != null && s.name === p.name));
    return hit.length ? hit.reduce((sum, s) => sum + s.dmg, 0) : null;
  };
  return [...by.values()].filter((p) => p.times > 0)
    .map((p) => ({ key: p.key, id: p.id, name: p.name, times: p.times, perFight: p.times / fights.length, uptime: MS_SUMS.meterShare(p.secs, len),
      dmg: done(p) }))
    .sort((a, b) => b.times - a.times || String(a.name ?? "").localeCompare(String(b.name ?? "")));
}

function procSeries(fights, key) {
  const got = [];
  for (const f of [...fights].sort((a, b) => a.t - b.t)) {
    const a = f.auras.find((x) => x.key === key);
    if (a) got.push({ t: f.t, len: f.len, uptime: MS_SUMS.meterShare(a.secs, f.len) });
  }
  return got;
}

if (typeof module === "object") {
  module.exports = { METER_SIDE_LEAST, spellFights, spellFigures, spellSides, spellTable, spellSorted, spellSeries, spellAuras, procTable, procSeries };
}
