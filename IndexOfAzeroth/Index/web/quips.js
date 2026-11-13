// The Index of Azeroth. Copyright 2026 Index Case <indexofazeroth@pm.me>. PolyForm Strict 1.0.0, see LICENSE.md.
"use strict";

const QUIP_TABLE = QuipLines;

const QUIP_STAGES = QUIP_TABLE.stages;
const QUIP_DOING = QUIP_TABLE.doing, QUIP_NOW = QUIP_TABLE.now;
const QUIP_RACE = QUIP_TABLE.race, QUIP_CLASS = QUIP_TABLE.class, QUIP_START = QUIP_TABLE.start, QUIP_ZONE = QUIP_TABLE.zone;
const QUIP_LOG = QUIP_TABLE.log, QUIP_FOUND = QUIP_TABLE.found, QUIP_USES = QUIP_TABLE.uses;
const QUIP_EACH = QUIP_TABLE.each;

function quipFill(template, facts) {
  let missing = false;
  const text = template.replace(/\{(\w+)\}/g, (m, k) => {
    const v = facts[k];
    if (v == null || v === "") { missing = true; return m; }
    return String(v);
  });
  return missing ? null : text;
}

function quipStage(said) {
  if (QUIP_STAGES.includes(said?.stage)) return said.stage;
  return said?.of ? "ways" : "log";
}

const quipDoing = (stage, me) => QUIP_DOING[stage]
  .map((t) => quipFill(t, { class: (me.cls || "").toLowerCase(), zone: me.zone })).filter(Boolean);

function quipsAboutYou(me) {
  const cls = (me.cls || "").toLowerCase(), out = [];
  const add = (list, facts) => { for (const t of list || []) { const s = quipFill(t, facts); if (s) out.push(s); } };
  if (cls) add(QUIP_RACE[me.race], { class: cls, classes: `${cls}s` });
  add(QUIP_CLASS[me.cls], {});
  if (me.zone) add(QUIP_START[me.zone] || QUIP_ZONE, { zone: me.zone });
  return out;
}

const quipKey = (facts) => JSON.stringify(Object.keys(facts).sort().map((k) => [k, String(facts[k])]));

const QUIP_KINDS = { ...QUIP_LOG, ...QUIP_FOUND };

function quipFinds(me, kinds = QUIP_KINDS) {
  const out = {};
  for (const f of me.found || []) {
    if (!f?.k || !kinds[f.k]) continue;
    const { k, ...facts } = f, list = (out[k] ||= []);
    if (list.length < QUIP_EACH && !list.some((x) => quipKey(x) === quipKey(facts))) list.push(facts);
  }
  return out;
}

function quipsOfKinds(order, kinds, finds) {
  const out = [];
  for (const kind of order) {
    (finds[kind] || []).slice(0, kinds[kind].length).forEach((facts, k) => {
      const s = quipFill(kinds[kind][k], facts);
      if (s) out.push(s);
    });
  }
  return out;
}

const quipsFound = (stage, me) => quipsOfKinds(QUIP_USES[stage], QUIP_KINDS, quipFinds(me));

function quipReagentPools() {
  const out = {};
  for (const [key, text] of Object.entries(wordsOf("page.reagents"))) (out[key.split(".")[0]] ||= []).push(text);
  return out;
}

function quipsMaterials(me) {
  const pools = quipReagentPools(), finds = quipFinds(me, pools);
  return quipsOfKinds(Object.keys(finds), pools, finds);
}

function quipRecipeLines(me) {
  const doing = quipReagentPools().doing;
  return [...doing.slice(0, 1), ...quipsMaterials(me), ...doing.slice(1)];
}

function quipNow(now) {
  const templates = QUIP_NOW[now?.k];
  return templates ? quipFill(templates[(now.n || 0) % templates.length], now) : null;
}

function quipLines(stage, me) {
  const doing = quipDoing(stage, me);
  return [...doing.slice(0, 1), ...quipsFound(stage, me), ...quipsMaterials(me), ...doing.slice(1), ...quipsAboutYou(me)];
}

function quipNext(lines, shown, last, now = null, nowLast = false) {
  if (now && !nowLast && !shown.has(now)) {
    shown.add(now);
    return now;
  }
  if (!lines.length) return null;
  let fresh = lines.filter((l) => !shown.has(l));
  if (!fresh.length) {
    shown.clear();
    fresh = lines.length > 1 ? lines.filter((l) => l !== last) : lines;
  }
  const next = fresh[0];
  shown.add(next);
  return next;
}

const QUIP_TEMPLATES = () => [...Object.values(QUIP_DOING), ...Object.values(QUIP_NOW), ...Object.values(QUIP_RACE),
  ...Object.values(QUIP_CLASS), ...Object.values(QUIP_START), QUIP_ZONE, ...Object.values(QUIP_LOG), ...Object.values(QUIP_FOUND)].flat();

if (typeof module === "object") {
  module.exports = { QUIP_STAGES, QUIP_DOING, QUIP_NOW, QUIP_RACE, QUIP_CLASS, QUIP_START, QUIP_ZONE, QUIP_LOG, QUIP_FOUND,
    QUIP_USES, QUIP_EACH, QUIP_TEMPLATES, quipFill, quipStage, quipDoing, quipsAboutYou, quipKey, quipFinds, quipsFound,
    quipReagentPools, quipsMaterials, quipRecipeLines, quipNow, quipLines, quipNext };
}
