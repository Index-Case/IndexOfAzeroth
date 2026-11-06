// The Index of Azeroth. Copyright 2026 Index Case <indexofazeroth@pm.me>. PolyForm Strict 1.0.0, see LICENSE.md.
"use strict";

const REPLAY_SPEEDS = [0.5, 1, 2, 5, 10, 20, 50, 100, 200, 500, 1000, 2000, 5000, 10000];
const REPLAY_PAUSES = [{ id: "dungeon", name: "Dungeon" }, { id: "combat", name: "Combat" }, { id: "duel", name: "Duel" },
  { id: "flight", name: "Flight" }, { id: "zone", name: "New Zone" }];
const TRACK_JOIN = 30;
const MOB_LEAD = 3;
const MOB_IDLE = 20;
const MOB_LINGER = 6;
const MOB_DEATH = 1.5;
const FADED = 0.35;
const FLY_MS = 650, SCT_MS = 1400, BUBBLE_MS = 4500;
const EFFECTS_MOST = 40;
const BUBBLES_MOST = 3;
const PICK_LEAST = 5;
const STEP_KINDS = new Set(["c", "m", "z", "i"]);
const COMBAT_BIT = 1, TAXI_BIT = 4;
const RP_MINE = 0x1, RP_PLAYER = 0x400, RP_HOSTILE = 0x40;
const SCHOOL_NATURE = 8;
const RP_DAMAGE = new Set(["SWING_DAMAGE", "RANGE_DAMAGE", "SPELL_DAMAGE", "SPELL_PERIODIC_DAMAGE", "ENVIRONMENTAL_DAMAGE",
  "DAMAGE_SHIELD", "SPELL_BUILDING_DAMAGE"]);
const RP_HEAL = new Set(["SPELL_HEAL", "SPELL_PERIODIC_HEAL"]);
const RP_MISSED = new Set(["SWING_MISSED", "RANGE_MISSED", "SPELL_MISSED", "SPELL_PERIODIC_MISSED", "DAMAGE_SHIELD_MISSED"]);
const RP_EVENTS = {
  death: { icon: "inv_misc_bone_humanskull_01", rank: 10, ring: "crimson" },
  level: { icon: "spell_holy_surgeoflight", rank: 9, ring: "gold" },
  dungeon: { icon: "spell_arcane_portalironforge", rank: 8, ring: "violet" },
  duel: { icon: "ability_warrior_challange", rank: 7, ring: "crimson" },
  flight: { icon: "ability_mount_gryphon_01", rank: 7, ring: "blue" },
  combat: { icon: "ability_dualwield", rank: 6, ring: "crimson" },
  zone: { icon: "inv_misc_map02", rank: 6, ring: "gold" },
  hearth: { icon: "inv_misc_rune_01", rank: 5, ring: "blue" },
  handin: { icon: "achievement_quests_completed_01", rank: 5, ring: "gold" },
  quest: { icon: "inv_scroll_03", rank: 5, ring: "gold" },
  train: { icon: "inv_misc_book_11", rank: 5, ring: "jade" },
  sell: { icon: "inv_misc_coin_02", rank: 4, ring: "gold" },
  buy: { icon: "inv_misc_bag_10", rank: 4, ring: "gold" },
  mention: { icon: "ui_chat", rank: 4, ring: "gold" },
  herb: { icon: "trade_herbalism", rank: 3, ring: "herb" },
  ore: { icon: "trade_mining", rank: 3, ring: "ore" },
  skin: { icon: "inv_misc_pelt_wolf_01", rank: 3, ring: "skin" },
  loot: { icon: "inv_misc_bag_07", rank: 2, ring: "bronze" },
  chat: { icon: "ui_chat", rank: 1, ring: "bronze" },
};
const RP_GATHERS = { "Herb Gathering": "herb", Mining: "ore", Skinning: "skin" };
const GATHER_LOOT = 8;
const REWARD_AFTER = 5;
const VISIT_JOIN = 60;
const TRAIN_JOIN = 20;
const RP_FIGHT_TAIL = 4;
const DEATH_JOIN = 10;
const DUNGEON_NAME = 5;
const RP_DEAD_BIT = 8, RP_GHOST_BIT = 2, RP_VENDOR_BIT = 32;
const RP_INDOORS_BIT = 64;
const RP_STILL = 0.8, RP_MOUNT = 9.5;
const RP_HELD = 45;
const RP_BAND = {
  dead: { rank: 8, weight: 8, words: "Dead" },
  ghost: { rank: 7, weight: 4, words: "Running back as a ghost" },
  fight: { rank: 6, weight: 6, words: "In a fight" },
  flight: { rank: 5, weight: 2, words: "On a flight" },
  dungeon: { rank: 4, weight: 2, words: "In a dungeon" },
  ride: { rank: 3, weight: 1.2, words: "Riding a mount" },
  walk: { rank: 2, weight: 1, words: "Walking" },
  still: { rank: 1, weight: 0.8, words: "Standing still" },
  none: { rank: 0, weight: 0.3, words: "No position recorded" },
};
const RP_BAND_KINDS = Object.keys(RP_BAND).sort((a, b) => RP_BAND[b].rank - RP_BAND[a].rank);
const SCT_TINTS = { hit: "white", crit: "gold", hurt: "combat-red", heal: "leaf-green", miss: "text-dim" };
const isMine = (flags) => !!((flags || 0) & RP_MINE);
const isMe = (flags) => isMine(flags) && !!(flags & RP_PLAYER);

function lastAt(list, t) {
  let lo = 0, hi = list.length - 1, at = -1;
  while (lo <= hi) {
    const mid = (lo + hi) >> 1;
    if (list[mid].t <= t) { at = mid; lo = mid + 1; } else hi = mid - 1;
  }
  return at;
}

const rpPlainText = (text) => String(text || "").replace(/\|c[0-9a-fA-F]{8}|\|r|\|H[^|]*\|h|\|h/g, "");
const rpItemName = (text) => String(text).replace(/\.$/, "").replace(/\[([^\]]*)\]/g, "$1").replace(/x(\d+)$/, " x$1").trim();

function systemLine(raw) {
  const text = rpPlainText(raw);
  let m;
  if ((m = /^Quest accepted: (.+)$/.exec(text))) return { kind: "quest", name: m[1].trim() };
  if ((m = /reached \[?level (\d+)/i.exec(text))) return { kind: "level", n: +m[1] };
  if ((m = /^You have learned (?:a new (?:spell|ability): |how to create a new item: )(.+?)\.?$/.exec(text))) return { kind: "train", name: m[1] };
  if ((m = /^You receive loot: (.+)$/.exec(text))) return { kind: "loot", name: rpItemName(m[1]) };
  if ((m = /^(?:You loot |Your share of the loot is )(.+?)\.?$/.exec(text))) return { kind: "loot", name: m[1].toLowerCase() };
  if ((m = /^You receive item: (.+)$/.exec(text))) return { kind: "item", name: rpItemName(m[1]) };
  if (/\bduel\b/i.test(text)) return { kind: "duel", name: text };
  if ((m = /^(.+) completed\.$/.exec(text))) return { kind: "handin", name: m[1].trim() };
  return null;
}

function fightSpans(evs, me) {
  const spans = [];
  let from = null;
  for (const e of evs) {
    if (e.k === "p" || e.k === "g") {
      const on = e.k === "p" && !!((e.fl || 0) & COMBAT_BIT);
      if (on && from == null) from = e.t;
      else if (!on && from != null) { spans.push([from, e.t]); from = null; }
    } else if (e.k === "c" && (RP_DAMAGE.has(e.e) || RP_MISSED.has(e.e))) {
      const toMe = e.dg === me || isMine(e.df), fromMine = e.sg === me || isMine(e.sf);
      if (toMe !== fromMine) spans.push([e.t, e.t + RP_FIGHT_TAIL]);
    }
  }
  if (from != null) spans.push([from, Math.max(from, evs[evs.length - 1].t)]);
  spans.sort((a, b) => a[0] - b[0]);
  const out = [];
  for (const [a, b] of spans) {
    if (out.length && a <= out[out.length - 1][1]) out[out.length - 1][1] = Math.max(out[out.length - 1][1], b);
    else out.push([a, b]);
  }
  return out;
}

function paceOf(p) {
  const fl = p.fl || 0;
  if (fl & RP_DEAD_BIT) return "dead";
  if (fl & RP_GHOST_BIT) return "ghost";
  if (fl & TAXI_BIT) return "flight";
  const v = p.s ?? p.v;
  if (v == null || v < RP_STILL) return "still";
  return v >= RP_MOUNT ? "ride" : "walk";
}

function flattenBand(spans) {
  const edges = [];
  for (const s of spans) if (s.to > s.t) edges.push([s.t, 1, s.kind], [s.to, -1, s.kind]);
  edges.sort((a, b) => a[0] - b[0] || a[1] - b[1]);
  const count = Object.fromEntries(RP_BAND_KINDS.map((k) => [k, 0])), out = [];
  let at = null;
  for (let i = 0; i < edges.length;) {
    const t = edges[i][0];
    if (at != null && t > at) {
      const kind = RP_BAND_KINDS.find((k) => count[k] > 0);
      if (kind) {
        const last = out[out.length - 1];
        if (last && last.kind === kind && last.to === at) last.to = t;
        else out.push({ t: at, to: t, kind });
      }
    }
    for (; i < edges.length && edges[i][0] === t; i++) count[edges[i][2]] += edges[i][1];
    at = t;
  }
  return out;
}

function replayTimeline(events, me) {
  const evs = (events || []).filter((e) => Number.isFinite(e?.t)).sort((a, b) => a.t - b.t);
  const track = [], units = new Map(), marks = [], fx = [], steps = [], spans = [];
  let lastFl = 0, lastZone = null, zoneMark = null, inside = null, flight = null, gather = null, visit = null, train = null, handin = -1e9;
  let lastSub = "";
  const from = evs.length ? evs[0].t : null, to = evs.length ? evs[evs.length - 1].t : null;
  const fights = fightSpans(evs, me), nextAt = new Array(evs.length);
  for (let i = evs.length - 1, at = to; i >= 0; i--) {
    nextAt[i] = at;
    if (evs[i].k === "p" || evs[i].k === "g") at = evs[i].t;
  }
  for (const [a, b] of fights) {
    marks.push({ t: a, kind: "combat", foes: [], to: b });
    spans.push({ t: a, to: b, kind: "fight" });
  }
  const fightAt = (t) => marks.find((m) => m.kind === "combat" && m.t <= t && t <= m.to);
  const died = (t) => {
    if (!marks.some((m) => m.kind === "death" && Math.abs(m.t - t) <= DEATH_JOIN)) marks.push({ t, kind: "death" });
  };
  const atVendor = (t, kind, d, item) => {
    if (!visit || visit.kind !== kind || t - visit.last > VISIT_JOIN) { visit = { t, kind, money: 0, items: [], last: t }; marks.push(visit); }
    visit.money += Math.abs(d || 0);
    if (item) visit.items.push(item);
    visit.last = t;
  };
  for (let i = 0; i < evs.length; i++) {
    const e = evs[i];
    if (STEP_KINDS.has(e.k)) steps.push(e.t);
    if (e.k === "p") {
      track.push({ t: e.t, m: e.m, x: e.x, y: e.y, f: e.f ?? null, fl: e.fl || 0, sub: lastSub });
      const fl = e.fl || 0;
      if (fl & TAXI_BIT && !(lastFl & TAXI_BIT)) { flight = { t: e.t, kind: "flight", to: null }; marks.push(flight); }
      if (!(fl & TAXI_BIT) && lastFl & TAXI_BIT && flight) flight.to = e.t;
      if (fl & RP_DEAD_BIT && !(lastFl & RP_DEAD_BIT)) died(e.t);
      lastFl = fl;
      spans.push({ t: e.t, to: Math.min(nextAt[i], e.t + RP_HELD), kind: paceOf(e) });
    } else if (e.k === "g") {
      track.push({ t: e.t, gone: true });
      if (lastFl & TAXI_BIT && flight) flight.to = e.t;
      lastFl = 0;
    } else if (e.k === "z") {
      const going = inside && e.t - inside.t <= DUNGEON_NAME && !inside.name;
      if (going) inside.name = e.zone;
      else if (lastZone !== null && e.zone !== lastZone) { zoneMark = { t: e.t, kind: "zone", name: e.zone }; marks.push(zoneMark); }
      lastZone = e.zone;
      lastSub = e.sub || "";
    } else if (e.k === "i") {
      if (inside) { spans.push({ t: inside.t, to: e.t, kind: "dungeon" }); inside = null; }
      if (e.kind === "party" || e.kind === "raid") {
        inside = { t: e.t, kind: "dungeon", raid: e.kind === "raid" };
        if (zoneMark && e.t - zoneMark.t <= DUNGEON_NAME) { inside.name = zoneMark.name; marks.splice(marks.indexOf(zoneMark), 1); }
        zoneMark = null;
        marks.push(inside);
      }
    } else if (e.k === "$") {
      if (e.v && e.d > 0) atVendor(e.t, "sell", e.d);
      else if (e.v && e.d < 0) atVendor(e.t, "buy", e.d);
    } else if (e.k === "m") {
      fx.push(e);
      if (e.ch !== "system") { marks.push({ t: e.t, kind: e.at ? "mention" : "chat", who: e.who, ch: e.ch, chan: e.chan, text: e.text }); continue; }
      const s = systemLine(e.text);
      if (!s) { if (e.at) marks.push({ t: e.t, kind: "mention", ch: "system", text: e.text }); continue; }
      if (s.kind === "handin") handin = e.t;
      if (s.kind === "loot" && gather && e.t - gather.t <= GATHER_LOOT) { gather.items.push(s.name); continue; }
      if (s.kind === "train") {
        if (train && e.t - train.last <= TRAIN_JOIN) { train.names.push(s.name); train.last = e.t; continue; }
        train = { t: e.t, kind: "train", names: [s.name], last: e.t };
        marks.push(train);
        continue;
      }
      if (s.kind === "item") {
        if (e.t - handin <= REWARD_AFTER) continue;
        if (lastFl & RP_VENDOR_BIT) atVendor(e.t, "buy", 0, s.name);
        else marks.push({ t: e.t, kind: "loot", name: s.name, given: true });
        continue;
      }
      marks.push({ t: e.t, ...s });
    } else if (e.k === "c") {
      fx.push(e);
      const fromMe = e.sg === me || isMe(e.sf);
      if (e.e === "UNIT_DIED" && (e.dg === me || isMe(e.df))) died(e.t);
      if (e.e === "SPELL_CAST_SUCCESS" && fromMe && RP_GATHERS[e.spn]) {
        gather = { t: e.t, kind: RP_GATHERS[e.spn], items: [], from: e.dn || null };
        marks.push(gather);
      }
      if (e.e === "SPELL_CAST_SUCCESS" && fromMe && e.spn === "Hearthstone") marks.push({ t: e.t, kind: "hearth" });
      if (RP_DAMAGE.has(e.e) || RP_MISSED.has(e.e)) {
        const fight = fightAt(e.t), toMe = e.dg === me || isMine(e.df), foe = toMe ? e.sn : e.dn;
        if (fight && foe && toMe !== (fromMe || isMine(e.sf)) && !fight.foes.includes(foe)) fight.foes.push(foe);
      }
      if (e.at && e.ig && e.ig !== me) {
        const u = units.get(e.ig) || { guid: e.ig, name: null, flags: 0, pts: [], died: null };
        if (e.sg === e.ig) { u.name = u.name || e.sn || null; u.flags = e.sf || u.flags; }
        if (e.dg === e.ig) { u.name = u.name || e.dn || null; u.flags = e.df || u.flags; }
        u.pts.push({ t: e.t, at: e.at });
        units.set(e.ig, u);
      }
      if ((e.e === "UNIT_DIED" || e.kill) && e.dg && units.has(e.dg)) units.get(e.dg).died = e.t;
    }
  }
  for (const e of evs) {
    if (e.k === "c" && e.e === "UNIT_DIED" && e.dg && units.has(e.dg) && units.get(e.dg).died == null) units.get(e.dg).died = e.t;
  }
  if (inside) spans.push({ t: inside.t, to, kind: "dungeon" });
  if (from != null) spans.push({ t: from, to, kind: "none" });
  marks.sort((a, b) => a.t - b.t);
  return { track, units, marks, fx, steps, from, to, band: flattenBand(spans) };
}

function rpBandAt(band, t) {
  const i = lastAt(band, t);
  return i >= 0 && t <= band[i].to ? band[i] : null;
}

function bandShown(band, from, to, px = 1000) {
  const span = Math.max(1e-6, to - from), bins = Math.max(1, Math.floor(px / 2)), w = span / bins;
  const inside = band.filter((s) => s.to > from && s.t < to).map((s) => ({ t: Math.max(from, s.t), to: Math.min(to, s.to), kind: s.kind }));
  if (!inside.length || inside.every((s) => s.to - s.t >= w)) return inside;
  const out = [];
  let j = 0;
  for (let b = 0; b < bins; b++) {
    const a = from + b * w, z = a + w, got = {};
    while (j < inside.length && inside[j].to <= a) j++;
    for (let k = j; k < inside.length && inside[k].t < z; k++) {
      const s = inside[k], cover = Math.min(z, s.to) - Math.max(a, s.t);
      if (cover > 0) got[s.kind] = (got[s.kind] || 0) + cover * RP_BAND[s.kind].weight;
    }
    const kind = Object.keys(got).sort((p, q) => got[q] - got[p] || RP_BAND[q].rank - RP_BAND[p].rank)[0];
    if (!kind) continue;
    const last = out[out.length - 1];
    if (last && last.kind === kind && Math.abs(last.to - a) < 1e-9) last.to = z;
    else out.push({ t: a, to: z, kind });
  }
  return out;
}

function trackAt(track, t) {
  const firstSpot = track.find((p) => !p.gone);
  if (!firstSpot) return null;
  const i = lastAt(track, t);
  if (i < 0) return { map: firstSpot.m, x: firstSpot.x, y: firstSpot.y, f: firstSpot.f, fl: 0, hidden: true };
  const a = track[i];
  if (a.gone) {
    for (let j = i - 1; j >= 0; j--) if (!track[j].gone) return { map: track[j].m, x: track[j].x, y: track[j].y, f: track[j].f, fl: 0, hidden: true };
    return { map: firstSpot.m, x: firstSpot.x, y: firstSpot.y, f: firstSpot.f, fl: 0, hidden: true };
  }
  const b = track[i + 1];
  if (!b || b.gone || b.m !== a.m || b.t - a.t > TRACK_JOIN || b.t === a.t) return { map: a.m, x: a.x, y: a.y, f: a.f, fl: a.fl, sub: a.sub };
  const k = (t - a.t) / (b.t - a.t);
  const f = a.f == null || b.f == null ? a.f ?? b.f : a.f + Math.atan2(Math.sin(b.f - a.f), Math.cos(b.f - a.f)) * k;
  return { map: a.m, x: a.x + (b.x - a.x) * k, y: a.y + (b.y - a.y) * k, f, fl: a.fl, sub: a.sub };
}

function unitAt(u, t) {
  const pts = u.pts;
  if (!pts.length || t < pts[0].t - MOB_LEAD) return null;
  if (u.died != null && t >= u.died + MOB_DEATH) return null;
  const dying = u.died != null && t >= u.died ? 1 - (t - u.died) / MOB_DEATH : 1;
  if (t < pts[0].t) return { at: pts[0].at, alpha: dying * (1 - (pts[0].t - t) / MOB_LEAD) };
  const i = lastAt(pts, t), a = pts[i], b = pts[i + 1];
  if (!b) {
    if (u.died != null) return { at: a.at, alpha: dying };
    const gone = t - a.t;
    return gone > MOB_LINGER ? null : { at: a.at, alpha: 1 - gone / MOB_LINGER };
  }
  const gap = b.t - a.t;
  if (gap <= MOB_IDLE && a.at[0] === b.at[0]) {
    const k = (t - a.t) / gap;
    return { at: [a.at[0], a.at[1] + (b.at[1] - a.at[1]) * k, a.at[2] + (b.at[2] - a.at[2]) * k], alpha: dying };
  }
  if (t >= b.t - MOB_LEAD) return { at: b.at, alpha: dying * Math.max(FADED, 1 - (b.t - t) / MOB_LEAD) };
  return { at: a.at, alpha: dying * FADED };
}

function pauseAt(marks, a, b, on) {
  if (!on || !on.size || a === b) return null;
  const hits = marks.filter((m) => on.has(m.kind) && (b > a ? m.t > a && m.t <= b : m.t < a && m.t >= b));
  if (!hits.length) return null;
  return b > a ? Math.min(...hits.map((m) => m.t)) : Math.max(...hits.map((m) => m.t));
}

function stepFrom(steps, t, dir) {
  if (dir > 0) return steps.find((s) => s > t + 1e-6) ?? t;
  for (let i = steps.length - 1; i >= 0; i--) if (steps[i] < t - 1e-6) return steps[i];
  return t;
}

const fasterThan = (speed) => REPLAY_SPEEDS.find((s) => s > speed) ?? REPLAY_SPEEDS[REPLAY_SPEEDS.length - 1];
const slowerThan = (speed) => [...REPLAY_SPEEDS].reverse().find((s) => s < speed) ?? REPLAY_SPEEDS[0];

function effectsOf(e, me, icons) {
  if (e.k === "m") {
    if (e.ch === "system" && !e.at) return [];
    const who = e.ch === "to" ? `To ${e.who}` : e.who;
    return [{ kind: "bubble", text: who ? `${who}: ${e.text}` : e.text, at: !!e.at, ch: e.ch }];
  }
  if (e.k !== "c") return [];
  const out = [], icon = e.spn ? icons?.[e.spn] : null;
  const toMe = e.dg === me || isMe(e.df), fromMe = e.sg === me || isMe(e.sf), fromMine = fromMe || isMine(e.sf);
  if (e.e === "SPELL_CAST_SUCCESS" && fromMe && icon) out.push({ kind: "card", icon, from: "me", to: e.dg && e.dg !== me ? e.dg : "ahead" });
  if (RP_DAMAGE.has(e.e) && e.a > 0) {
    if (toMe && !fromMine) {
      if (icon && e.e !== "SPELL_PERIODIC_DAMAGE") out.push({ kind: "card", icon, from: e.sg || "around", to: "me" });
      out.push({ kind: "sct", at: "me", text: `-${e.a}`, look: "hurt", crit: !!e.cr });
    } else if (fromMine && !toMe) {
      out.push({ kind: "sct", at: e.dg || "ahead", text: e.cr ? `${e.a}!` : `${e.a}`, look: e.cr ? "crit" : "hit", crit: !!e.cr });
    }
  }
  if (RP_HEAL.has(e.e) && e.a > 0 && toMe) {
    if (icon && e.e !== "SPELL_PERIODIC_HEAL") out.push({ kind: "card", icon, from: e.sc === SCHOOL_NATURE ? "below" : "above", to: "me" });
    out.push({ kind: "sct", at: "me", text: `+${e.a - (e.oh || 0) > 0 ? e.a - (e.oh || 0) : e.a}`, look: "heal", crit: !!e.cr });
  }
  if (RP_MISSED.has(e.e) && e.m && (toMe || fromMine)) {
    const word = e.m.charAt(0) + e.m.slice(1).toLowerCase();
    out.push({ kind: "sct", at: toMe ? "me" : e.dg || "ahead", text: word, look: "miss", crit: false });
  }
  return out;
}

const ICON_GAP = 20;
function marksShown(marks, from, to, px = 1000, gap = ICON_GAP) {
  const room = gap * Math.max(1e-6, to - from) / Math.max(1, px), kept = [], more = new Map();
  const order = marks.filter((m) => m.t >= from && m.t <= to)
    .sort((a, b) => RP_EVENTS[b.kind].rank - RP_EVENTS[a.kind].rank || a.t - b.t);
  for (const m of order) {
    const i = lastAt(kept, m.t), near = [kept[i], kept[i + 1]].filter((k) => k && Math.abs(k.t - m.t) < room);
    if (!near.length) { kept.splice(i + 1, 0, m); continue; }
    const by = near.sort((a, b) => Math.abs(a.t - m.t) - Math.abs(b.t - m.t))[0];
    more.set(by, (more.get(by) || 0) + 1);
  }
  return kept.map((m) => ({ ...m, more: more.get(m) || 0 }));
}

const rpTwo = (n) => String(n).padStart(2, "0");
function clockOf(t) {
  const d = new Date(t * 1000);
  return `${rpTwo(d.getHours())}:${rpTwo(d.getMinutes())}:${rpTwo(d.getSeconds())}`;
}
function minuteOf(t) {
  const d = new Date(t * 1000);
  return `${rpTwo(d.getHours())}:${rpTwo(d.getMinutes())}`;
}
function lengthWords(s) {
  const n = Math.max(0, Math.round(s)), h = Math.floor(n / 3600), m = Math.floor(n % 3600 / 60), sec = n % 60;
  const one = (v, word) => `${v} ${word}${v === 1 ? "" : "s"}`;
  if (h) return m ? `${one(h, "hour")} and ${one(m, "minute")}` : one(h, "hour");
  if (m) return sec ? `${one(m, "minute")} and ${one(sec, "second")}` : one(m, "minute");
  return one(sec, "second");
}
function rpAndList(names) {
  const list = names.length > 3 ? [...names.slice(0, 2), `${names.length - 2} more`] : names;
  return list.length > 1 ? `${list.slice(0, -1).join(", ")} and ${list[list.length - 1]}` : list[0];
}
const CHANNEL_WORDS = { say: "said", yell: "yelled", party: "said in party chat", raid: "said in raid chat",
  guild: "said in guild chat", officer: "said in officer chat", whisper: "whispered" };

function markWords(m) {
  const at = clockOf(m.t);
  const more = m.more ? ` Zoom in to see ${m.more} more ${m.more === 1 ? "event" : "events"} close by.` : "";
  return `${markLine(m, at)}${more}`;
}
function markLine(m, at) {
  switch (m.kind) {
    case "combat": return m.foes?.length ? `A fight with ${rpAndList(m.foes)} began at ${at}.` : `A fight began at ${at}.`;
    case "death": return `The character died at ${at}.`;
    case "level": return `The character reached level ${m.n} at ${at}.`;
    case "flight": return m.to ? `A flight took off at ${at} and landed at ${clockOf(m.to)}.` : `A flight took off at ${at}.`;
    case "zone": return `The character came into ${m.name} at ${at}.`;
    case "dungeon": return `The character went into ${m.name || (m.raid ? "a raid" : "a dungeon")} at ${at}.`;
    case "duel": return `A duel at ${at}: ${m.name}`;
    case "hearth": return `The character used the Hearthstone at ${at}.`;
    case "quest": return `The character accepted the quest ${m.name} at ${at}.`;
    case "handin": return `The character handed in the quest ${m.name} at ${at}.`;
    case "train": return `The character learnt ${rpAndList(m.names)} at ${at}.`;
    case "sell": return `The character sold to a vendor for ${moneyText(m.money)} at ${at}.`;
    case "buy": return m.items.length ? `The character bought ${rpAndList(m.items)}${m.money ? ` for ${moneyText(m.money)}` : ""} at ${at}.`
      : `The character paid a vendor ${moneyText(m.money)} at ${at}.`;
    case "herb": return `The character picked ${m.items.length ? rpAndList(m.items) : "an herb"} at ${at}.`;
    case "ore": return `The character mined ${m.items.length ? rpAndList(m.items) : "ore"} at ${at}.`;
    case "skin": return `The character skinned ${m.from || "a beast"}${m.items.length ? ` for ${rpAndList(m.items)}` : ""} at ${at}.`;
    case "loot": return m.given ? `The character received ${m.name} at ${at}.` : `The character looted ${m.name} at ${at}.`;
    case "chat": case "mention": {
      const text = m.text ? `: ${m.text.length > 80 ? `${m.text.slice(0, 79)}…` : m.text}` : ".";
      const named = m.kind === "mention" ? " The line names the character." : "";
      if (m.ch === "to") return `The character whispered to ${m.who} at ${at}${text}${named}`;
      if (m.ch === "system") return `The game said at ${at}${text}${named}`;
      const said = CHANNEL_WORDS[m.ch] || (m.chan ? `said in ${m.chan.replace(/^\d+\.\s*/, "")}` : "said");
      return `${m.who || "Someone"} ${said} at ${at}${text}${named}`;
    }
    default: return `Something happened at ${at}.`;
  }
}
function bandWords(s) {
  return s ? `${RP_BAND[s.kind].words} from ${clockOf(s.t)} to ${clockOf(s.to)}, for ${lengthWords(s.to - s.t)}.` : "";
}

const TICK_STEPS = [1, 2, 5, 10, 15, 30, 60, 120, 300, 600, 900, 1800, 3600, 7200, 10800, 21600];
const LABEL_GAP = 52, LABEL_GAP_SECONDS = 72, MINOR_GAP = 8;
const ZOOM_LEAST = 10;
function ticksFor(from, to, px = 1000) {
  const span = Math.max(1e-6, to - from), per = px / span;
  const step = TICK_STEPS.find((s) => s * per >= (s < 60 ? LABEL_GAP_SECONDS : LABEL_GAP)) ?? TICK_STEPS[TICK_STEPS.length - 1];
  const minor = [...TICK_STEPS].reverse().find((s) => s < step && step % s === 0 && s * per >= MINOR_GAP) ?? step;
  const off = -new Date(from * 1000).getTimezoneOffset() * 60, ticks = [], edge = (step < 60 ? 24 : 16) / per;
  for (let t = Math.ceil((from + off) / minor) * minor - off; t <= to + 1e-9 && ticks.length < 2000; t += minor) {
    const major = ((Math.round(t + off) % step) + step) % step === 0, room = t - from >= edge && to - t >= edge;
    ticks.push({ t, major, label: major && room ? (step < 60 ? clockOf(t) : minuteOf(t)) : null });
  }
  return { step, minor, ticks };
}

function zoomAbout(view, t, factor, whole) {
  const all = Math.max(1e-6, whole.to - whole.from), span = view.to - view.from;
  const next = Math.min(all, Math.max(Math.min(ZOOM_LEAST, all), span * factor));
  const k = span > 0 ? (t - view.from) / span : 0.5;
  let from = t - k * next;
  from = Math.min(whole.to - next, Math.max(whole.from, from));
  return { from, to: from + next };
}
function panBy(view, dt, whole) {
  const span = view.to - view.from, from = Math.min(whole.to - span, Math.max(whole.from, view.from + dt));
  return { from, to: from + span };
}
function dayName(day) {
  const [y, m, d] = day.split("-").map(Number), at = new Date(y, m - 1, d);
  return at.toLocaleDateString("en-GB", { weekday: "long", day: "numeric", month: "short" });
}

const FOOT_GAP = 16;
function footRight(keys, cards, me, width) {
  let right = keys?.width ? width - keys.left + FOOT_GAP : 440;
  if (cards?.width && me && cards.bottom > me.top && cards.left < width - right) right = Math.max(right, width - cards.left + FOOT_GAP / 2);
  return Math.round(right);
}

const FADE_LEAST = 0.1, FADE_BANDS = 24;
function fadePieces(runs, bands = FADE_BANDS) {
  const len = (a, b) => Math.hypot(b[0] - a[0], b[1] - a[1]);
  let total = 0;
  for (const run of runs) for (let i = 1; i < run.length; i++) total += len(run[i - 1], run[i]);
  const out = [];
  if (!(total > 0)) return out;
  const alpha = (band) => (bands > 1 ? FADE_LEAST + (1 - FADE_LEAST) * band / (bands - 1) : 1);
  let d = 0;
  for (const run of runs) {
    let piece = null;
    for (let i = 1; i < run.length; i++) {
      const a = run[i - 1], b = run[i], step = len(a, b);
      if (!step) continue;
      const from = d;
      d += step;
      let band = Math.min(bands - 1, Math.floor(from / total * bands)), at = a;
      for (;;) {
        if (!piece || piece.band !== band) out.push(piece = { band, alpha: alpha(band), pts: [at] });
        const edge = (band + 1) * total / bands;
        if (band >= bands - 1 || d <= edge + 1e-9) { piece.pts.push(b); break; }
        const k = (edge - from) / step;
        at = [a[0] + (b[0] - a[0]) * k, a[1] + (b[1] - a[1]) * k];
        piece.pts.push(at);
        band++;
      }
    }
  }
  return out.map((p) => ({ alpha: p.alpha, pts: p.pts }));
}

if (typeof module === "object") {
  module.exports = { REPLAY_SPEEDS, REPLAY_PAUSES, MOB_LEAD, MOB_IDLE, MOB_LINGER, MOB_DEATH, FADED, TRACK_JOIN, RP_EVENTS,
    RP_BAND, SCT_TINTS, RP_HELD, ZOOM_LEAST, ICON_GAP, GATHER_LOOT, VISIT_JOIN, REWARD_AFTER,
    FOOT_GAP, PICK_LEAST, EFFECTS_MOST, BUBBLES_MOST, FLY_MS, SCT_MS, BUBBLE_MS, lastAt, replayTimeline, trackAt, footRight,
    unitAt, pauseAt, stepFrom, fasterThan, slowerThan, effectsOf, marksShown, clockOf, dayName, systemLine,
    rpPlainText, rpItemName, fightSpans, paceOf, flattenBand, rpBandAt, bandShown, markWords, bandWords, lengthWords,
    rpAndList, ticksFor, zoomAbout, panBy, FADE_LEAST, FADE_BANDS, fadePieces };
}
