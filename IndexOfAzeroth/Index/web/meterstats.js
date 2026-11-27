// The Index of Azeroth. Copyright 2026 Index Case <indexofazeroth@pm.me>. PolyForm Strict 1.0.0, see LICENSE.md.
"use strict";

const METER_SHOWN = 200;

const meterUrl = (char) => `/api/meter?char=${encodeURIComponent(char || "")}`;
const meterFightUrl = (char, t) => `/api/meter/fight?char=${encodeURIComponent(char || "")}&t=${encodeURIComponent(t)}`;

const meterSpellsUrl = (char) => `/api/meter/spells?char=${encodeURIComponent(char || "")}`;

const meterMoment = (m) => (m ? { t: m.t, dps: m.dps || 0 } : null);

function meterAnswer(j) {
  const fight = (f) => ({ t: f.t, len: f.len || 0, dmg: f.dmg || 0, dps: f.dps || 0, taken: f.taken || 0, name: f.name || null,
    lvl: f.lvl || null, kills: f.kills || 0, gear: f.gear || null, weapons: f.weapons || null, talents: f.talents || null,
    ne: f.ne || 0, multi: !!f.multi, main: f.main ?? null, ttk: f.ttk ?? null, dg: f.dg || null, boss: !!f.boss });
  return { char: j.char, building: j.building || 0, fighting: !!j.fighting, now: meterMoment(j.now), last: meterMoment(j.last),
    fights: (j.fights || []).map(fight), cut: j.cut || 0, events: j.events || [] };
}

function meterFightAnswer(j) {
  const spell = (s) => ({ id: s.id || null, name: s.name || null, by: s.by || null, dmg: s.dmg || 0, casts: s.casts || 0,
    hits: (s.hits || 0) + (s.ticks || 0), crits: s.crits || 0, misses: s.misses || 0, foes: s.foes || 0, volleys: s.volleys || 0,
    blows: s.blows || 0 });
  const enemy = (e) => ({ npc: e.npc ?? null, name: e.name || null, dmg: e.dmg || 0, died: e.died ?? null, kind: e.kind || null });
  return { t: j.t, len: j.len || 0, dmg: j.dmg || 0, spells: (j.spells || []).map(spell), up: j.up || [], down: j.down || [],
    line: j.line || [], enemies: (j.enemies || []).map(enemy), multi: !!j.multi, ttk: j.ttk ?? null, dg: j.dg || null, boss: !!j.boss };
}

const meterPerCast = (x) => (x.foes > 1 && x.volleys ? x.blows / x.volleys : null);

function meterEnemies(fight) {
  const total = fight.enemies.reduce((s, e) => s + e.dmg, 0);
  return fight.enemies.map((e) => ({ ...e, share: meterShare(e.dmg, total) }));
}

const meterSpellKey = (id, name, by) => JSON.stringify([id ?? null, name ?? null, by ?? null]);

function meterSpellsAnswer(j) {
  const spells = (j.spells || []).map(([id, name, by]) => ({ key: meterSpellKey(id, name, by), id: id ?? null, name: name ?? null, by: by ?? null }));
  const auras = (j.auras || []).map(([id, name]) => ({ key: JSON.stringify([id, name ?? null]), id, name: name ?? null }));
  const part = ([a, dmg, h, c, tk]) => ({ aura: auras[a].key, dmg, hits: h + tk, direct: h, crits: c });
  const spell = ([s, dmg, casts, h, c, misses, tk, split, foes, volleys, blows]) => ({ ...spells[s], dmg, casts, hits: h + tk, direct: h, crits: c, misses,
    split: (split || []).map(part), foes: foes || 0, volleys: volleys || 0, blows: blows || 0 });
  const aura = ([a, secs, times, whole]) => ({ ...auras[a], secs, times, whole: !!whole });
  return { char: j.char ?? null, building: j.building || 0, cut: j.cut || 0, fights: (j.fights || []).map(([t, len, dmg, dps, sp, up]) => ({
    t, len, dmg, dps, spells: sp ? sp.map(spell) : null, auras: up ? up.map(aura) : null })) };
}

const METER_KINDS = ["single", "multi", "all"];
const METER_PLACES = ["world", "dungeon", "both"];
const METER_CHOICE = { kind: "single", place: "both" };

const meterOfChoice = (f, c) => (c.kind === "all" || (c.kind === "multi") === f.multi) && (c.place === "both" || (c.place === "dungeon") === !!f.dg);

const meterChosen = (m, c) => ({ ...m, fights: m.fights.filter((f) => meterOfChoice(f, c)) });

function meterGlance(m) {
  if (m.fighting && m.now) return { dps: m.now.dps, open: true };
  return m.last ? { dps: m.last.dps, open: false } : null;
}

function meterShown(m) {
  const rows = [...m.fights].sort((a, b) => b.t - a.t);
  return { rows: rows.slice(0, METER_SHOWN), more: Math.max(0, rows.length - METER_SHOWN) + m.cut };
}

function meterSpells(fight) {
  const total = fight.spells.reduce((s, x) => s + x.dmg, 0);
  return [...fight.spells].sort((a, b) => b.dmg - a.dmg || String(a.name ?? "").localeCompare(String(b.name ?? "")))
    .map((s) => ({ ...s, share: meterShare(s.dmg, total) }));
}

const meterShare = (part, total) => (total ? Math.round((part / total) * 1000) / 10 : 0);

if (typeof module === "object") {
  module.exports = { METER_SHOWN, meterUrl, meterFightUrl, meterSpellsUrl, meterAnswer, meterFightAnswer, meterSpellKey, meterSpellsAnswer,
    METER_KINDS, METER_PLACES, METER_CHOICE, meterOfChoice, meterChosen, meterPerCast, meterEnemies, meterGlance, meterShown, meterSpells, meterShare };
}
