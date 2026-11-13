// The Index of Azeroth. Copyright 2026 Index Case <indexofazeroth@pm.me>. PolyForm Strict 1.0.0, see LICENSE.md.
"use strict";

const ROLL_INV_NAME = { 1: "Head", 2: "Neck", 3: "Shoulder", 5: "Chest", 20: "Chest", 6: "Waist", 7: "Legs", 8: "Feet",
  9: "Wrist", 10: "Hands", 11: "Finger", 12: "Trinket", 13: "One-Hand", 14: "Off Hand", 15: "Ranged", 16: "Back",
  17: "Two-Hand", 21: "Main Hand", 22: "Off Hand", 23: "Held In Off-hand", 25: "Thrown", 26: "Ranged", 28: "Relic" };
const RANGED_INV = new Set([15, 25, 26]);
const rollCard = { list: [], at: 0, sig: "", names: {}, asked: new Set(), key: "", timer: null };

function applyRolls(snap) {
  const list = snap.rolls?.rolls || [];
  const sig = JSON.stringify(list);
  if (sig !== rollCard.sig) { rollCard.sig = sig; rollCard.list = list; rollCard.at = Date.now(); }
  renderRolls();
}

function rollNames(ids) {
  const need = ids.filter((id) => !rollCard.names[id] && !rollCard.asked.has(id));
  const asked = need.length && getJson(`/api/iteminfo?ids=${need.join(",")}`, { key: "roll names" });
  if (!asked) return;
  need.forEach((id) => rollCard.asked.add(id));
  asked.then((got) => {
    Object.assign(rollCard.names, got);
    renderRolls(true);
  }, () => need.forEach((id) => rollCard.asked.delete(id)));
}

const rollLeft = (r) => Math.max(0, r.left - (Date.now() - rollCard.at) / 1000);
const rollKey = (r) => r.key ?? r.item;

function rollVerdict(r) {
  const it = { cls: r.cls, sub: r.sub, inv: r.inv, il: r.il, rl: r.rl };
  let u = usability(it);
  if (u.use === "yes" && r.usable === false) u = { use: "never" };
  const stats = statCache[rollKey(r)];
  const mine = stats && RANGED_INV.has(r.inv) ? { ...stats, st: asRanged(stats.st) } : stats;
  const { known, against, againstId, slot } = replaced(r.inv), usable = u.use === "yes" || u.use === "train";
  const cmp = usable && mine?.st && known ? compareGear({ ...mine, st: inSlot(mine.st, slot) }, against) : null;
  const up = usable && (cmp ? !!cmp.kind : isUpgrade(it));
  return { u, it, up, cmp, against, againstId, mine, known };
}

const ROLL_CALL = { clear: "need", "": "greed" };
const rollCall = (kind) => ROLL_CALL[kind] ?? "maybe";
const ROLL_ICON = { need: "/ui/need.png", greed: "/ui/greed.png", maybe: "/icon/inv_misc_questionmark.jpg" };
const ROLL_WORDS = wordsOf("page.rolls.call");
function rollCallHtml(v) {
  const kind = upgradeKind(v.u, v.up, v.cmp), call = rollCall(kind);
  return `<div class="rc-call j-tag ${UPGRADE_COLOUR[kind] || "grey"}"><img src="${ROLL_ICON[call]}" alt="">${esc(ROLL_WORDS[call])}</div>`;
}

const CLEARLY_FOR = 1.5;
function rollRanking(r, v) {
  const st = v.mine?.st;
  if (!statWeights.data || !st) return [];
  const it = { cls: r.cls, sub: r.sub, inv: r.inv }, cls = app.status?.classId;
  const people = v.up ? [{ you: true, cls, u: v.u, specs: specsFor(cls, spec() || LEVELING_TREE[cls], myRole()) }] : [];
  for (const m of app.group?.members || []) {
    const name = m.name.split("-")[0];
    if (m.me) continue;
    people.push({ name, cls: m.classId, role: m.role, u: usabilityFor(it, m.classId, m.level || 1), specs: specsFor(m.classId, 0, m.role) });
  }
  const order = (x) => KIND_RANK[x.kind] ?? 3;
  return people.filter((p) => p.cls && p.u.use !== "never").map((p) => {
    const best = p.specs.map((s) => ({ s, worth: gearScore({ st }, s.w), kind: compareGear({ st }, null, s.w, s.name)?.kind }))
      .sort((a, b) => order(a) - order(b) || b.worth - a.worth)[0];
    return best && { ...p, spec: best.s.name, worth: best.worth, kind: best.kind };
  }).filter((p) => p && p.kind).sort((a, b) => order(a) - order(b) || b.worth - a.worth);
}
const KIND_WORDS = wordsOf("page.rolls.kind");
function rankingHtml(rank) {
  if (!app.group?.members?.length || !rank.length) return "";
  const who = (p) => {
    const cls = CLASS_NAMES[p.cls] || "";
    const why = p.you ? word("page.rolls.why.you") : p.role ? word("page.rolls.why.role", { role: p.role }) : word("page.rolls.why.spec");
    const tip = word("page.rolls.tip", { spec: p.spec, class: cls, why, kind: KIND_WORDS[p.kind], worth: p.worth.toFixed(1) }) + (
      p.u.use !== "later" ? "" : `. ${p.you ? word("page.rolls.tip.later.you", { level: p.u.level }) : word("page.rolls.tip.later", { name: p.name, level: p.u.level })}`);
    return `<b style="color:${CLASS_COLORS[cls] || tint("class-other")}" title="${esc(tip)}">${esc(p.you ? word("page.rolls.you") : p.name)}</b> (${esc(`${p.spec} ${cls}`)})`;
  };
  if (rank.length === 1) return `<small class="rc-for">${word("page.rolls.only", { who: who(rank[0]) })}</small>`;
  const clearly = KIND_RANK[rank[0].kind] < KIND_RANK[rank[1].kind] || rank[0].worth >= rank[1].worth * CLEARLY_FOR;
  const fill = { who: who(rank[0]), others: rank.slice(1).map(who).join(", ") };
  return `<small class="rc-for">${clearly ? word("page.rolls.clearly", fill) : word("page.rolls.best", fill)}</small>`;
}

function renderRolls(force) {
  const box = $("roll-card");
  if (!box) return;
  const open = rollCard.list.filter((r) => rollLeft(r) > 0);
  if (!open.length) {
    box.hidden = true;
    clearInterval(rollCard.timer);
    rollCard.timer = null;
    rollCard.key = "";
    return;
  }
  const ids = open.map((r) => r.item), keys = open.map(rollKey);
  rollNames(ids);
  const need = keys.filter((id) => !(id in statCache));
  if (need.length) loadStats(need)?.then(() => renderRolls(true));
  const key = JSON.stringify([rollCard.sig, keys.map((id) => statCache[id] ? 1 : 0), ids.map((id) => rollCard.names[id] ? 1 : 0),
    (app.equipped || []).join(","), Object.keys(gear.worn).length, app.status?.nums?.armorKinds, app.status?.nums?.weaponKinds,
    app.state?.level, !!statWeights.data, (app.group?.members || []).map((m) => [m.name, m.classId, m.role, m.level])]);
  if (!force && key === rollCard.key && !box.hidden) return;
  rollCard.key = key;
  const rows = open.map((r) => {
    const v = rollVerdict(r), info = rollCard.names[r.item] || {}, st = statCache[rollKey(r)];
    const name = st?.n || info.n || word("page.rolls.item", { id: r.item }), q = st?.q ?? info.q ?? 1;
    const kind = r.cls === 4 ? ARMOR_NAME[r.sub] : r.cls === 2 ? WEAPON_SKILL[r.sub] : "";
    const line = [st?.slot || ROLL_INV_NAME[r.inv], kind && kind[0].toUpperCase() + kind.slice(1),
      r.il ? word("page.rolls.item-level", { il: r.il }) : "", r.rl > 1 ? word("page.journal.items.requires", { level: r.rl }) : ""]
      .filter(Boolean).join(", ");
    const note = v.u.use === "never" ? word("page.rolls.never")
      : v.u.use === "later" ? word("page.journal.items.later", { skill: esc(v.u.skill), level: v.u.level })
      : !v.up && (v.u.use === "yes" || v.u.use === "train") ? word("page.rolls.no-better") : "";
    const gain = v.against && v.mine?.st ? esc(gainText(v.mine, v.against)) : "";
    const over = v.against && { item: itemNamed(v.against.n, v.againstId, v.against.n), il: v.against.il, gain };
    const vs = v.u.use === "never" || !v.known ? ""
      : !over ? word("page.rolls.nothing")
      : over.il ? (gain ? word("page.rolls.over.level.gain", over) : word("page.rolls.over.level", over))
      : gain ? word("page.rolls.over.gain", over) : word("page.rolls.over", over);
    const icon = r.icon ? `/fileicon/${esc(r.icon)}.jpg` : `/icon/${esc(info.icon || "inv_misc_questionmark")}.jpg`;
    return rollCallHtml(v) + itemRowHtml({ id: rollKey(r), icon, q, name, cls: `rc-item${v.u.use === "never" ? " unusable" : ""}`, line: `${esc(line)}${note ? `, ${note}` : ""}`,
      more: `${vs ? `<small class="rc-vs">${vs}</small>` : ""}${rankingHtml(rollRanking(r, v))}`, after: upgradeTag(v.it, v.u, v.up, v.cmp) });
  }).join("");
  box.innerHTML = `<div class="rc-head"><span>${wordCount("page.rolls.head", open.length)}</span>
      <span class="rc-end"><span class="rc-left"></span>${helpButton("rolls")}</span></div>${rows}<div class="rc-foot">${esc(word("page.rolls.foot"))}</div>`;
  box.hidden = false;
  tickRolls();
  if (!rollCard.timer) rollCard.timer = setInterval(tickRolls, 250);
}

function tickRolls() {
  const box = $("roll-card"), open = rollCard.list.filter((r) => rollLeft(r) > 0);
  if (!box || !open.length) return renderRolls();
  const left = Math.min(...open.map(rollLeft));
  const el = box.querySelector(".rc-left");
  if (el) el.textContent = `${Math.ceil(left)} s`;
}
