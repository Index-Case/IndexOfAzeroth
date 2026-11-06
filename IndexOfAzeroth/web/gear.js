// The Index of Azeroth. Copyright 2026 Index Case <indexofazeroth@pm.me>. PolyForm Strict 1.0.0, see LICENSE.md.
"use strict";

const gear = { data: null, more: new Set(), why: new Set(), worn: {}, wornAsked: new Set() };
keptOr("cc.gearMore", []).forEach((key) => { if (typeof key === "string") gear.more.add(key); });
const MIN_GAIN = 0.5;
const SLIGHT = 0.05;
const CLEAR_MIN = 2;
const CLEAR_OF = 0.1;
const CHASE_SHARE = 0.5;
const CLEAR_LOSS = 0.5;
const CHASE_OF = 0.4;
const OURS_OF = 0.15;
const OTHERS_SHARE = 0.4;
const WEAPON_OWN = 1;
const EVERYONE = new Set(["sta", "armor", "hp5", "resist", "resfire", "resfrost", "resarcane", "resshadow", "resnature"]);
const PAIR = { hit: "spellhit", spellhit: "hit", crit: "spellcrit", spellcrit: "crit" };
const KIND_RANK = { clear: 0, weak: 1, debatable: 2 };
const SOON = 3;
const RUNNERS_UP = 2;

const statWeights = { data: null };
function loadStatWeights(again) {
  if (statWeights.data && !again) return;
  getJson(`/api/statweights${again ? `?v=${Date.now()}` : ""}`, { key: "statweights", force: !!again })?.then((j) => {
    statWeights.data = j;
    renderJournal();
    renderRolls(true);
    if (app.drawer === "alts") renderDrawer();
  }, () => renderJournal());
}
const LEVELING_TREE = { 1: 1, 2: 3, 3: 1, 4: 2, 5: 3, 7: 2, 8: 3, 9: 1, 11: 2 };
const CLASS_NAMES = { 1: "Warrior", 2: "Paladin", 3: "Hunter", 4: "Rogue", 5: "Priest", 7: "Shaman", 8: "Mage", 9: "Warlock", 11: "Druid" };
const STAT_WORDS = wordsOf("page.stats.short");
const PERCENT_STATS = new Set(["hit", "crit", "spellhit", "spellcrit", "dodge", "parry", "block"]);
const WEAPON_DAMAGE = new Set(["dps", "ohdps", "rdps", "wdps"]);
const NO_PLUS = new Set([...WEAPON_DAMAGE, "armor"]);

function statWords(k, v, change, bare) {
  const n = +(+v).toFixed(2), sign = !bare && n > 0 && (change || !NO_PLUS.has(k) && !PERCENT_STATS.has(k)) ? "+" : "";
  return PERCENT_STATS.has(k) ? `${sign}${n}${STAT_WORDS[k]}` : `${sign}${n} ${STAT_WORDS[k] || k}`;
}
const GEAR_SLOTS = [[1, "Head"], [2, "Neck"], [3, "Shoulder"], [15, "Back"], [5, "Chest"], [9, "Wrist"], [10, "Hands"],
  [6, "Waist"], [7, "Legs"], [8, "Feet"], [11, "Finger"], [12, "Finger"], [13, "Trinket"], [14, "Trinket"],
  [16, "Main hand"], [17, "Off hand"], [18, "Ranged"]];
const DUAL_WIELD = new Set([1, 3, 4]);

function loadGear() {
  loadStatWeights();
  if (!gear.data) getJson("/api/gear")?.then((j) => { gear.data = j; renderJournal(); }, () => renderJournal());
}
function gearAgain() {
  loadGear();
  renderJournal();
}

const wearLevel = (it) => Math.max(it.rl || Math.max(1, it.il - 5), usability(it).level || 0);

const SPEC_AFTER = 5;
function spec() {
  const n = app.status?.nums || {}, trees = [n.tree1Points || 0, n.tree2Points || 0, n.tree3Points || 0];
  const most = Math.max(...trees);
  return most >= SPEC_AFTER ? trees.indexOf(most) + 1 : 0;
}
function specsFor(cls, tree, role) {
  const specs = statWeights.data?.classes?.[cls]?.specs || [];
  if (tree) {
    const inTree = specs.filter((s) => s.tree === tree);
    const asRole = inTree.filter((s) => s.role === (role === "tank" ? "tank" : "damage"));
    return (asRole.length ? asRole : inTree).slice(0, 1);
  }
  const asRole = role ? specs.filter((s) => s.role === role) : [];
  return asRole.length ? asRole : specs;
}
function myRole() {
  return (app.group?.members || []).find((m) => m.me)?.role || null;
}
function specInfo() {
  const cls = app.status?.classId, s = specsFor(cls, spec() || LEVELING_TREE[cls], myRole())[0];
  return { name: s?.name || "", w: s?.w || {}, leveling: !spec() };
}
const weights = () => specInfo().w;
const specLabel = () => [specInfo().name, CLASS_NAMES[app.status?.classId]].filter(Boolean).join(" ") || word("page.gear.verdicts.you");
const PRIO_WORDS = wordsOf("page.stats.long");
const PER_BUDGET = { ap: 2, rap: 2.5, fap: 2.5, sp: 1.17, heal: 2.2, spfire: 1.4, spfrost: 1.4, sparcane: 1.4, spshadow: 1.4,
  spnature: 1.4, spholy: 1.4, hit: 0.1, spellhit: 0.1, crit: 0.071, spellcrit: 0.071, dodge: 0.083, parry: 0.05, block: 0.2,
  def: 0.83, blockvalue: 1.5, mp5: 0.4, hp5: 0.33, armor: 10, resist: 0.25, dps: 0.2, ohdps: 0.2, rdps: 0.2, wdps: 0.2 };
function priorityText() {
  const { name, w, leveling } = specInfo();
  if (!name) return "";
  const order = Object.entries(w).filter(([k]) => k !== "ohdps").map(([k, v]) => [k, v * (PER_BUDGET[k] ?? 1)])
    .sort((a, b) => b[1] - a[1]).slice(0, 6);
  const cls = String(app.status?.classId);
  const fixed = (statWeights.data.fixes || []).filter((f) => f.class === cls && f.spec === name)
    .map((f) => word("page.gear.verdicts.prio.fix", { stat: PRIO_WORDS[f.stat] || f.stat, ours: f.ours, pawn: f.pawn }));
  const who = { who: specLabel(), order: order.map(([k]) => PRIO_WORDS[k] || k).join(" > "), after: SPEC_AFTER };
  const source = { source: statWeights.data.source || "Pawn", fixes: fixed.join(", ") };
  return [leveling ? word("page.gear.verdicts.prio.leveling", who) : word("page.gear.verdicts.prio", who),
    fixed.length ? word("page.gear.verdicts.prio.source.fixed", source) : word("page.gear.verdicts.prio.source", source)].join(" ");
}

function gearScore(it, w = weights()) {
  return Object.entries(it.st || {}).reduce((sum, [k, v]) => sum + (w[k] || 0) * (v || 0), 0);
}

const perBudget = (w, k) => (w[k] || 0) * (PER_BUDGET[k] ?? 1);
const bestPerBudget = (w) => Math.max(0, ...Object.keys(w).filter((k) => !WEAPON_DAMAGE.has(k)).map((k) => perBudget(w, k)));
const chaseCache = new WeakMap();
function chaseStats(w) {
  if (chaseCache.has(w)) return chaseCache.get(w);
  const best = bestPerBudget(w);
  const chase = new Set(Object.keys(w).filter((k) => !WEAPON_DAMAGE.has(k) && perBudget(w, k) >= best * CHASE_OF));
  for (const k of WEAPON_DAMAGE) if ((w[k] || 0) >= WEAPON_OWN) chase.add(k);
  chaseCache.set(w, chase);
  return chase;
}
const KIN_OF = 0.075;
function othersStats(st, w) {
  const classes = Object.values(statWeights.data?.classes || {}), kin = classes.find((c) => c.specs.some((s) => s.w === w));
  const best = bestPerBudget(w), specs = classes.filter((c) => c !== kin).flatMap((c) => c.specs);
  const own = (k) => perBudget(w, k) >= best * OURS_OF || (PAIR[k] && st[PAIR[k]] === st[k] && perBudget(w, PAIR[k]) >= best * OURS_OF)
    || (perBudget(w, k) >= best * KIN_OF && (kin?.specs || []).some((s) => chaseStats(s.w).has(k)));
  return Object.keys(st).filter((k) => st[k] > 0 && !EVERYONE.has(k) && !WEAPON_DAMAGE.has(k) && !own(k)
    && specs.some((s) => chaseStats(s.w).has(k)));
}
function classWeaponBudget(st, w) {
  const classes = Object.values(statWeights.data?.classes || {}), kin = classes.find((c) => c.specs.some((s) => s.w === w));
  const k = [...WEAPON_DAMAGE].find((d) => st[d] > 0 && chaseStats(w).has(d)
    && !classes.some((c) => c !== kin && c.specs.some((s) => chaseStats(s.w).has(d))));
  return k ? st[k] / PER_BUDGET[k] : 0;
}
function budgetOf(st, keys) {
  return keys.filter((k) => st[k] > 0 && k !== "armor" && !WEAPON_DAMAGE.has(k) && !(k.startsWith("spell") && PAIR[k] && st[PAIR[k]] === st[k]))
    .reduce((sum, k) => sum + st[k] / (PER_BUDGET[k] ?? 1), 0);
}

const ownCache = new WeakMap();
function ownStats(w) {
  if (ownCache.has(w)) return ownCache.get(w);
  const best = bestPerBudget(w);
  const own = new Set(Object.keys(w).filter((k) => !WEAPON_DAMAGE.has(k) && perBudget(w, k) >= best * OURS_OF));
  for (const k of WEAPON_DAMAGE) if ((w[k] || 0) >= WEAPON_OWN) own.add(k);
  ownCache.set(w, own);
  return own;
}

function compareGear(item, worn, w = weights(), who = specLabel()) {
  if (!statWeights.data) return null;
  const a = item?.st || {}, b = worn?.st || {}, gains = [], losses = [];
  for (const k of new Set([...Object.keys(a), ...Object.keys(b)])) {
    const d = (a[k] || 0) - (b[k] || 0), v = (w[k] || 0) * d;
    if (v > 0.001) gains.push([k, d, v]); else if (v < -0.001) losses.push([k, d, -v]);
  }
  const gain = gains.reduce((s, g) => s + g[2], 0), loss = losses.reduce((s, l) => s + l[2], 0), net = gain - loss;
  const chase = chaseStats(w), chased = gains.filter((g) => chase.has(g[0])).reduce((s, g) => s + g[2], 0);
  const own = ownStats(w), owned = gains.filter((g) => own.has(g[0])).reduce((s, g) => s + g[2], 0)
    - losses.filter((l) => own.has(l[0])).reduce((s, l) => s + l[2], 0);
  const others = othersStats(a, w), othersShare = budgetOf(a, others) / ((budgetOf(a, Object.keys(a)) + classWeaponBudget(a, w)) || 1);
  const base = Math.max(0, gearScore(worn || {}, w)), real = Math.max(MIN_GAIN, base * SLIGHT);
  let kind = null, why = null;
  if (net >= real && owned >= 0) {
    const holder = gains.filter((g) => !own.has(g[0])).sort((x, y) => y[2] - x[2])[0]?.[0];
    if (othersShare >= OTHERS_SHARE) [kind, why] = ["debatable", "others"];
    else if (owned < real) [kind, why] = ["debatable", WEAPON_DAMAGE.has(holder) ? "holder" : "barely"];
    else if (owned >= Math.max(CLEAR_MIN, base * CLEAR_OF) && chased >= gain * CHASE_SHARE && loss <= gain * CLEAR_LOSS) kind = "clear";
    else [kind, why] = ["weak", chased < gain * CHASE_SHARE ? "offstats" : loss > gain * CLEAR_LOSS ? "trade" : "small"];
  }
  const byWorth = (l) => oneHit(l).sort((x, y) => y[2] - x[2]);
  return { kind, why, others, gain, loss, net, gains: byWorth(gains), losses: byWorth(losses), who };
}
function oneHit(list) {
  for (const [melee, spell] of [["hit", "spellhit"], ["crit", "spellcrit"]]) {
    const a = list.find((e) => e[0] === melee), b = list.find((e) => e[0] === spell);
    if (a && b && Math.abs(a[1] - b[1]) < 0.01) { a[2] += b[2]; list.splice(list.indexOf(b), 1); }
  }
  return list;
}
function compareWords(cmp) {
  const gains = cmp.gains.slice(0, 4).map(([k, d]) => statWords(k, d, true)).join(", ");
  const losses = cmp.losses.slice(0, 4).map(([k, d]) => statWords(k, -d, false, true)).join(", ");
  const verdict = { clear: word("both.upgrades.clear"), weak: word("both.upgrades.weak"), debatable: word("both.upgrades.debatable") };
  const fill = { verdict: verdict[cmp.kind] || verdict.weak, who: cmp.who, gains, losses };
  const also = losses ? [word("page.gear.verdicts.gives-up", fill)] : [];
  const said = (head, ...more) => [head, ...more].join(". ");
  if (cmp.kind === "clear") {
    return said(word("page.gear.verdicts.head", fill), ...(losses ? [word("page.gear.verdicts.gives-up-only", fill)] : []));
  }
  if (cmp.kind === "debatable" && cmp.why === "holder") {
    return said(word("page.gear.verdicts.head", fill), ...also, word("page.gear.verdicts.holder", fill));
  }
  if (cmp.kind === "debatable" && cmp.why === "barely") {
    return said(word("page.gear.verdicts.head", fill), ...also, word("page.gear.verdicts.barely", fill));
  }
  if (cmp.kind === "debatable") {
    const lines = cmp.others.filter((k) => !(k.startsWith("spell") && PAIR[k] && cmp.others.includes(PAIR[k])));
    const stats = lines.map((k) => PRIO_WORDS[k] || k).join(" and ");
    return said(word("page.gear.verdicts.head", fill), ...also, wordCount("page.gear.verdicts.others", lines.length, { stats }));
  }
  if (cmp.why === "trade") return word("page.gear.verdicts.weak.trade", fill);
  return said(cmp.why === "offstats" ? word("page.gear.verdicts.weak.offstats", fill) : word("page.gear.verdicts.weak.slight", fill), ...also);
}

function replaced(inv) {
  const slots = inv === 13 && !wornIn(17)?.st?.ohdps ? [16] : SLOTS_FOR[inv] || [];
  const worn = slots.map((s) => wornIn(s));
  if (!worn.length || worn.some((w) => w === undefined)) return { known: false, against: null };
  const weakest = worn.map((w, i) => ({ w, slot: slots[i], score: w ? gearScore(w) : -Infinity })).sort((x, y) => x.score - y.score)[0];
  return { known: true, against: weakest.w, againstId: weakest.w ? app.equipped[weakest.slot - 1] : null, slot: weakest.slot };
}
function inSlot(st, slot) {
  return slot === 18 ? asRanged(st) : slot === 17 ? damageAs(st, "ohdps") : st;
}

function wornIn(slot) {
  if (app.equipped == null) return undefined;
  const id = app.equipped[slot - 1];
  if (!id) return null;
  if (!gear.worn[id] && !gear.wornAsked.has(id)) askWorn();
  const it = gear.worn[id];
  if (!it) return undefined;
  return slot === 17 || slot === 18 ? { ...it, st: inSlot(it.st, slot) } : it;
}
function askWorn() {
  const ids = (app.equipped || []).filter((id) => id && !gear.worn[id] && !gear.wornAsked.has(id));
  for (const id of ids) if (statCache[id]) gear.worn[id] = statCache[id];
  const rest = ids.filter((id) => !gear.worn[id]);
  const asked = rest.length ? loadStats(rest) : null;
  if (!asked) return;
  rest.forEach((id) => gear.wornAsked.add(id));
  asked.then(() => {
    const got = rest.filter((id) => statCache[id]);
    got.forEach((id) => { gear.worn[id] = statCache[id]; });
    rest.filter((id) => !statCache[id]).forEach((id) => gear.wornAsked.delete(id));
    if (got.length) renderJournal();
  });
}

function gainText(it, worn) {
  const c = compareGear(it, worn);
  return c ? [...c.gains.slice(0, 3), ...c.losses.slice(0, 2)].slice(0, 4).map(([k, d]) => statWords(k, d, true)).join(", ") : "";
}

function inRange(key) {
  const d = dungeon.byKey[key];
  if (!d || d.kind !== jr.kind || d.notOpen) return false;
  const lvl = app.state?.level || 1, [min, lo, hi] = d.levels || [0, 0, 0];
  return jr.kind === "raid" ? lvl >= (min || 60) - 2 : lvl >= Math.max(min, lo) - 3 && lvl <= hi + 5;
}

function ahead(key) {
  const d = dungeon.byKey[key];
  if (!d || d.kind !== jr.kind || d.notOpen) return false;
  const lvl = app.state?.level || 1, [min, lo] = d.levels || [0, 0];
  return jr.kind === "raid" ? lvl < (min || 60) - 2 : lvl < Math.max(min, lo) - 3;
}

function openLevel(d) {
  return Math.max(d.levels?.[0] || (d.kind === "raid" ? 60 : 0), d.openFrom || 0);
}
function tooLow(key) {
  const d = dungeon.byKey[key];
  return !!d && (app.state?.level || 1) < openLevel(d);
}

function sourcesOf(id) {
  const rank = (s) => (inRange(s.key) ? 0 : 10 + openLevel(dungeon.byKey[s.key]) * 10) + (tooLow(s.key) ? 3 : 0) + (s.boss ? 0 : s.quest ? 1 : 2);
  return (gear.data.from[id] || []).filter((s) => inRange(s.key) || ahead(s.key)).sort((a, b) => rank(a) - rank(b));
}
const reachLevel = (c) => Math.max(openLevel(dungeon.byKey[sourcesOf(c.id)[0].key]), wearLevel(c.it));

function fitsSlot(it, slot) {
  if (slot === 17) {
    if (it.inv === 13) return DUAL_WIELD.has(app.status?.classId) && (app.state?.level || 1) >= 10;
    return [14, 22, 23].includes(it.inv);
  }
  return (SLOTS_FOR[it.inv] || []).includes(slot);
}

const bestFirst = (a, b) => a.lower - b.lower || b.score - a.score || b.it.il - a.it.il;

function gearHtml() {
  loadGear();
  const raid = jr.kind === "raid";
  const prio = statWeights.data ? esc(priorityText()) : askNote("statweights", { what: word("page.gear.upgrades.asked.weights"), again: gearAgain });
  const top = `<div class="j-top"><div><h2>${word("page.gear.upgrades.title")}</h2>
      <p class="muted">${raid ? word("page.gear.upgrades.about.raid") : word("page.gear.upgrades.about.dungeon")}</p>
      ${prio ? `<p class="g-prio">${prio}</p>` : ""}</div>
    <div class="j-tabs">${KIND_TABS.filter(([k]) => GEAR_KINDS.includes(k)).map(kindKey).join("")}</div></div>`;
  if (!gear.data) return `${top}<p class="muted">${askNote("/api/gear", { what: word("page.gear.upgrades.asked.gear"), again: gearAgain })}</p>`;
  if (!statWeights.data) return top;
  const lvl = app.state?.level || 1, worn = app.run?.gear || [];
  const knowWorn = worn.some((v) => v > 0) || !!app.equipped;
  const pool = Object.entries(gear.data.items)
    .filter(([id, it]) => canUse(it) && sourcesOf(id).length)
    .map(([id, it]) => ({ id, it, score: gearScore(it), lower: usability(it).lower ? 1 : 0,
      near: inRange(sourcesOf(id)[0].key) && wearLevel(it) <= lvl + SOON }))
    .sort(bestFirst);
  const placed = (c, slot) => {
    const st = inSlot(c.it.st, slot);
    return st === c.it.st ? c : { ...c, it: { ...c.it, st }, score: gearScore({ st }) };
  };
  const taken = new Set();
  const plan = {};
  const slotRows = GEAR_SLOTS.map(([slot, label]) => {
    const wearing = worn[slot - 1] || 0, item = wornIn(slot), wornKey = app.equipped?.[slot - 1];
    const verdict = (c) => (item !== undefined ? compareGear(c.it, item)?.kind : c.it.il > wearing && "level");
    const later = (c) => (tooLow(sourcesOf(c.id)[0].key) || wearLevel(c.it) > lvl ? 1 : 0);
    const ups = pool.filter((c) => fitsSlot(c.it, slot) && !taken.has(c.id)).map((c) => placed(c, slot)).sort(bestFirst)
      .map((c) => ({ ...c, kind: verdict(c) })).filter((c) => c.kind);
    const near = ups.filter((c) => c.near)
      .sort((x, y) => x.lower - y.lower || later(x) - later(y) || (KIND_RANK[x.kind] ?? 3) - (KIND_RANK[y.kind] ?? 3));
    const fits = near.length ? near : ups.map((c) => ({ ...c, reach: reachLevel(c) }))
      .sort((x, y) => x.lower - y.lower || x.reach - y.reach || (KIND_RANK[x.kind] ?? 3) - (KIND_RANK[y.kind] ?? 3));
    if (fits[0] && (slot === 11 || slot === 13)) taken.add(fits[0].id);
    const base = item ? gearScore(item) : 0;
    for (const c of near) {
      for (const src of sourcesOf(c.id).filter((s) => inRange(s.key))) {
        const p = plan[src.key] ||= { gain: 0, slots: {} };
        const gain = Math.max(c.score - base, 0.1);
        if (gain > (p.slots[slot]?.gain || 0)) p.slots[slot] = { gain, label, name: c.it.n };
      }
    }
    const key = `${jr.kind}:${slot}`, open = gear.more.has(key);
    const shown = fits.slice(0, open ? 1 + RUNNERS_UP : 1);
    const pieces = shown.map((c, n) => gearRow(c, n > 0, item, wornKey, `${key}:${c.id}`)).join("");
    const more = fits.length > 1 ? `<button class="g-more fold-plus" data-gear-more="${key}" aria-expanded="${open}">${open ? word("page.gear.upgrades.fewer") : word("page.gear.upgrades.more", { n: Math.min(RUNNERS_UP, fits.length - 1) })}</button>` : "";
    const now = item ? `<small>${word("page.gear.upgrades.wearing", {
      item: `<span style="color:${QUALITY[item.q] || tint("white")}">${itemNamed(item.n, wornKey, item.n)}</span>` })}</small>`
      : item === null ? `<small>${word("page.gear.upgrades.wearing.nothing")}</small>`
      : wearing ? `<small>${word("page.gear.upgrades.wearing.level", { level: wearing })}</small>` : "";
    const gain = !fits[0] ? 0 : item !== undefined ? fits[0].score - base : Math.max(fits[0].it.il - wearing, 0) + fits[0].score / 100;
    return { slot, gain, far: fits[0] && !fits[0].near ? 1 : 0, reach: fits[0]?.reach || 0, html: (rank) => `<div class="g-slot"><div class="g-slot-name">${rank ? `<span class="g-rank">${rank}</span>` : ""}${label}${now}</div>
      <div class="g-slot-items">${pieces || `<p class="muted">${jr.kind === "raid" ? word("page.gear.upgrades.none.raid") : word("page.gear.upgrades.none.dungeon")}</p>`}${more}</div></div>` };
  });
  const sorted = slotRows.map((r, n) => ({ ...r, n }))
    .sort((a, b) => (b.gain > 0) - (a.gain > 0) || a.far - b.far || a.reach - b.reach || b.gain - a.gain || a.n - b.n);
  const rows = sorted.map((r, i) => r.html(r.gain > 0 ? i + 1 : 0)).join("");
  const ranks = {};
  sorted.forEach((r, i) => { if (r.gain > 0) ranks[r.slot] = [i + 1, r.gain]; });
  const note = knowWorn ? "" : `<p class="muted">${word("page.gear.upgrades.unknown")}</p>`;
  const none = jr.kind === "raid" && !Object.keys(dungeon.byKey).some((k) => inRange(k))
    ? `<p class="muted">${word("page.gear.upgrades.no-raid")}</p>` : "";
  return `${top}${note}${none}${planHtml(plan, ranks)}<div class="g-list j-single">${rows}</div>`;
}

const PLAN_TOP = 4;
function planHtml(plan, ranks) {
  const n = Object.keys(ranks).length;
  const ranked = Object.entries(plan).map(([key, p]) => {
    const slots = Object.entries(p.slots).filter(([slot]) => ranks[slot])
      .map(([slot, s]) => ({ ...s, rank: ranks[slot][0], share: Math.min(1, s.gain / ranks[slot][1]) }));
    return { key, slots, value: slots.reduce((sum, s) => sum + (n - s.rank + 1) * s.share, 0) };
  }).filter((p) => p.slots.length).sort((a, b) => b.value - a.value).slice(0, PLAN_TOP);
  if (!ranked.length) return "";
  const rows = ranked.map((p) => {
    const d = dungeon.byKey[p.key], [fitText, fitClass] = fit(d);
    const names = p.slots.sort((a, b) => a.rank - b.rank).map((s) => `#${s.rank} ${s.label}`);
    return `<div class="g-plan-row"><button class="key small" data-open="${p.key}">${esc(d.name)}</button>
      <span>${wordCount("page.gear.upgrades.plan.slots", p.slots.length, { slot: esc(names.join(", ")) })}</span>
      ${fitText ? `<span class="fit ${fitClass}">${fitText}</span>` : ""}</div>`;
  }).join("");
  return `<div class="g-plan"><div class="g-plan-title">${word("page.gear.upgrades.plan")}</div>${rows}</div>`;
}

function gearRow({ id, it }, runnerUp, worn, wornId, whyKey) {
  const src = sourcesOf(id), s = src[0], d = dungeon.byKey[s.key];
  const where = s.boss ? esc(s.boss) : s.quest ? esc(word("page.gear.upgrades.quest", { quest: s.quest })) : word("page.gear.upgrades.trash");
  const others = src.length > 1 ? ` <small>${word("page.gear.upgrades.others", { n: src.length - 1 })}</small>` : "";
  const lvl = app.state?.level || 1, low = tooLow(s.key), wearAt = wearLevel(it) > lvl ? wearLevel(it) : 0;
  const [, fitClass] = fit(d), lo = d.levels?.[1] || 0;
  const from = low ? `<span class="fit red">${SKULL} ${word("page.gear.upgrades.from-level", { name: where, level: openLevel(d) })}</span>`
    : `${where}${fitClass === "yellow" ? ` <span class="fit yellow">${word("page.gear.upgrades.stretch", { level: lo })}</span>` : ""}`;
  const w = weights();
  const stats = oneHit(Object.entries(it.st || {}).filter(([k]) => w[k] && k !== "armor").map(([k, v]) => [k, v, 0]))
    .map(([k, v]) => statWords(k, v)).join(", ");
  const cmp = worn !== undefined ? compareGear(it, worn) : null;
  const u = usability(it);
  const warn = [wearAt ? `<span class="fit red">${SKULL} ${word("page.gear.upgrades.worn-from", { level: wearAt })}</span>` : "",
    u.use === "train" ? `<b>${esc(word("page.gear.upgrades.train", { skill: u.skill }))}</b>`
      : u.lower ? `<b>${word("page.gear.upgrades.lower")}</b> ${word("page.gear.upgrades.lower.wear", { wear: ARMOR_NAME[u.lower] })}` : ""]
    .filter(Boolean).join(", ");
  const open = gear.why.has(whyKey);
  const over = worn && { gain: esc(gainText(it, worn)), item: itemNamed(worn.n, wornId, worn.n) };
  const details = `${esc(it.kind && it.kind !== it.slot ? `${it.slot}, ${it.kind}` : it.slot || "")}, ${word("page.gear.upgrades.item-level", { il: it.il })}${
    stats ? `<br>${esc(stats)}` : ""}${over ? `<br><small class="g-gain">${over.gain ? word("page.gear.upgrades.gain-over", over)
      : word("page.gear.upgrades.over", over)}</small>` : ""}`;
  const fold = `<button class="g-why fold-plus" data-gear-why="${esc(whyKey)}" aria-expanded="${open}">${word("page.gear.upgrades.details")}</button>`;
  const row = itemRowHtml({ id, icon: itemIcon(it), q: it.q, name: it.n,
    line: `${warn ? `${warn}<br>` : ""}${fold}${open ? `<br>${details}` : ""}`,
    after: cmp?.kind ? upgradeTag(it, { use: "yes" }, true, cmp) : "" });
  return `<div class="g-item${runnerUp ? " runner-up" : ""}${low || wearAt ? " later" : ""}">
    ${row}
    <div class="g-from">${from}${others}</div>
    <button class="key small" data-go-item="${s.key}" data-pick="${esc(JSON.stringify(s.boss ? { boss: s.boss } : s.quest ? { quest: s.quest } : { trash: true }))}"
      title="${esc(s.boss ? word("page.gear.upgrades.boss.tip", { boss: s.boss, dungeon: d.name }) : s.quest
        ? word("page.gear.upgrades.quest.tip", { quest: s.quest }) : word("page.gear.upgrades.trash.tip", { dungeon: d.name }))}">${esc(d.name)}</button>
  </div>`;
}

const GEAR_KINDS = ["dungeon", "raid"];

function openGear() {
  pushView();
  jr.key = "@gear";
  if (!GEAR_KINDS.includes(jr.kind)) jr.kind = GEAR_KINDS[0];
  renderJournal();
}

function gearClicked(e) {
  const b = e.target.closest("button");
  if (!b) return;
  if (b.dataset.gear) return openGear();
  if (b.dataset.goItem) {
    pushView();
    try { jr.pick = JSON.parse(b.dataset.pick); } catch (err) { jr.pick = null; }
    jr.tab = jr.pick?.quest ? "quests" : "bosses";
    return openJournal(b.dataset.goItem);
  }
  if (b.dataset.gearWhy) {
    if (gear.why.has(b.dataset.gearWhy)) gear.why.delete(b.dataset.gearWhy); else gear.why.add(b.dataset.gearWhy);
    return renderJournal();
  }
  if (b.dataset.gearMore) {
    if (gear.more.has(b.dataset.gearMore)) gear.more.delete(b.dataset.gearMore); else gear.more.add(b.dataset.gearMore);
    keepIn("cc.gearMore", [...gear.more]);
    renderJournal();
  }
}
$("journal").addEventListener("click", gearClicked);
