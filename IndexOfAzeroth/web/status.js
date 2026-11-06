// The Index of Azeroth. Copyright 2026 Index Case <indexofazeroth@pm.me>. PolyForm Strict 1.0.0, see LICENSE.md.
"use strict";

const CLASS_COLORS = { Warrior: tint("class-warrior"), Paladin: tint("class-paladin"), Hunter: tint("class-hunter"),
  Rogue: tint("class-rogue"), Priest: tint("white"), Shaman: tint("quality-rare"), Mage: tint("class-mage"),
  Warlock: tint("class-warlock"), Druid: tint("class-druid") };
const REACTIONS = ["", "Hated", "Hostile", "Unfriendly", "Neutral", "Friendly", "Honored", "Revered", "Exalted"];
const HAPPINESS = ["", "Unhappy", "Content", "Happy"];
const WARNING_ROW = { ammo: "ammo", petUnhappy: "petHappiness", shards: "shards", mhPoison: "mhPoison", ohPoison: "ohPoison",
  poisons: "poisons", water: "water", ankh: "ankhs", earthTotem: "earthTotem", fireTotem: "fireTotem",
  waterTotem: "waterTotem", airTotem: "airTotem", durability: "durability" };
const BEEP_REPEAT_MS = 60000;
const ZERO_IS_FINE = new Set(["tree1Points", "tree2Points", "tree3Points", "hearth", "reincarnation", "petTraining", "special", "specialFree", "totem1", "totem2", "totem3", "totem4"]);

const ammoLabel = (s) => s.ammoName || s.ammoBetter || "Ammo";

function shootingTime(n) {
  const speed = n.rangedSpeed ? n.rangedSpeed / 1000 : 0;
  return speed ? `about ${clock(n.ammo * speed)} of shooting` : "";
}

function poisonText(n, hand) {
  if (!n[`${hand}Enchanted`]) return "None";
  const sec = n[`${hand}PoisonSec`] || 0, charges = n[`${hand}PoisonCharges`] || 0;
  return clock(sec) + (charges ? ` <small>${charges} charges</small>` : "");
}

function warningText(w, n) {
  if (w.text) return [w.text, w.detail || ""];
  const low = w.level === "low";
  if (w.spell) {
    return [`${w.spell.name} Rank ${w.spell.best} isn't on your bars`,
      `Your bars have Rank ${w.spell.have}. Drag the new rank from your spellbook, or cast the spell by name in the macro.`];
  }
  switch (w.key) {
    case "ammo": return low ? [`Ammo low: ${num(n.ammo)} left`, shootingTime(n)] : ["OUT OF AMMO", "Buy arrows or bullets"];
    case "petUnhappy": return ["Pet is unhappy", "Your pet does 75% damage and may run away. Feed your pet."];
    case "shards": return low ? [`Soul shards low: ${n.shards} left`, "Use Drain Soul on a few kills"] : ["OUT OF SOUL SHARDS", "Drain Soul to get more"];
    case "mhPoison": return low ? ["Main hand poison running out", poisonText(n, "mh").replace(/<[^>]+>/g, "")] : ["NO POISON ON MAIN HAND", ""];
    case "ohPoison": return low ? ["Off hand poison running out", poisonText(n, "oh").replace(/<[^>]+>/g, "")] : ["NO POISON ON OFF HAND", ""];
    case "poisons": return low ? [`Poisons low: ${n.poisons} left in bags`, ""] : ["NO POISONS LEFT IN BAGS", "Buy or craft more"];
    case "water": return low ? [`Water low: ${n.water} left`, ""] : ["OUT OF WATER", ""];
    case "ankh": return low ? [`Ankhs low: ${n.ankhs} left`, ""] : ["NO ANKH", "Reincarnation won't work"];
    case "earthTotem": return ["EARTH TOTEM MISSING", "Earth totems won't cast"];
    case "fireTotem": return ["FIRE TOTEM MISSING", "Fire totems won't cast"];
    case "waterTotem": return ["WATER TOTEM MISSING", "Water totems won't cast"];
    case "airTotem": return ["AIR TOTEM MISSING", "Air totems won't cast"];
    case "durability": return low ? [`Gear durability at ${n.durability}%`, "Repair soon"] : ["BROKEN GEAR", "Repair now"];
    default: return [w.key, ""];
  }
}


const sound = { ctx: null, heard: {}, lastOutBeep: 0 };

function unlockSound() {
  if (sound.ctx) return;
  try {
    sound.ctx = new AudioContext();
  } catch (e) { return; }
  renderWarnings();
}
["pointerdown", "keydown"].forEach((ev) => document.addEventListener(ev, unlockSound, { once: false, passive: true }));

function beep(urgent) {
  const ctx = sound.ctx;
  if (!ctx) return;
  if (ctx.state === "suspended") ctx.resume();
  const tones = urgent ? [880, 660, 880, 660] : [660, 880];
  tones.forEach((freq, i) => {
    const osc = ctx.createOscillator(), gain = ctx.createGain();
    const t = ctx.currentTime + i * 0.18;
    osc.type = "square";
    osc.frequency.value = freq;
    gain.gain.setValueAtTime(0.0001, t);
    gain.gain.exponentialRampToValueAtTime(0.12, t + 0.02);
    gain.gain.exponentialRampToValueAtTime(0.0001, t + 0.16);
    osc.connect(gain).connect(ctx.destination);
    osc.start(t);
    osc.stop(t + 0.17);
  });
}

function soundWarnings(warnings) {
  const now = Date.now(), current = {};
  let fresh = false, urgent = false;
  for (const w of warnings) {
    current[w.key] = w.level;
    if (!sound.heard[w.key] || (w.level === "out" && sound.heard[w.key] === "low")) fresh = true;
    if (w.level === "out") urgent = true;
  }
  sound.heard = current;
  if (app.options?.warningSound === false) return;
  if (fresh || (urgent && now - sound.lastOutBeep > BEEP_REPEAT_MS)) {
    beep(urgent);
    if (urgent) sound.lastOutBeep = now;
  }
}


let dismissed = {};
const warningSignature = (w) => `${w.level}|${w.spell ? w.spell.best : ""}`;

function dismissable(w) {
  return w.level !== "out" && !!todoForWarning(w);
}
const movedToTodo = (w) => dismissed[w.key]?.sig === warningSignature(w) && dismissable(w);

function activeWarnings() {
  const rankWarnings = (app.bars?.ranks || []).map((r) => ({ key: `rank:${r.name}`, level: "low", spell: r }));
  const dungeonOnes = dungeonWarnings();
  return [...queueNotices(), ...(app.status?.warnings || []), ...rankWarnings, ...dungeonOnes]
    .filter((w) => !isSilencedWarning(w) && !movedToTodo(w));
}

function moveToTodo(key, sig, todoId) {
  postTodo({ dismiss: { [key]: { sig, todo: todoId } } });
}
function moveBack(key) {
  postTodo({ unmove: key });
}
function movedWarnings() {
  const rankWarnings = (app.bars?.ranks || []).map((r) => ({ key: `rank:${r.name}`, level: "low", spell: r }));
  return [...(app.status?.warnings || []), ...rankWarnings].filter((w) => !isSilencedWarning(w) && movedToTodo(w));
}
function bandClicked(e) {
  const news = e.target.closest(".warn[data-queue]");
  if (news) return dismissQueue(news.dataset.queue);
  const el = e.target.closest(".warn[data-key]");
  if (el) moveToTodo(el.dataset.key, el.dataset.sig, el.dataset.todo);
}
$("warnings").addEventListener("click", bandClicked);

function loudInGame() {
  return (app.status?.warnings || []).filter((w) => !w.quiet && movedToTodo(w));
}
function quietInGame() {
  return (app.status?.warnings || []).filter((w) => w.quiet && w.level === "low" && !movedToTodo(w) && !isSilencedWarning(w));
}

const WARN_ORDER = { news: 0, out: 1 };
function renderWarnings() {
  const st = app.status;
  const warnings = activeWarnings();
  let html = warnings
    .slice().sort((a, b) => (WARN_ORDER[a.level] ?? 2) - (WARN_ORDER[b.level] ?? 2))
    .map((w) => {
      const [title, detail] = warningText(w, st?.nums || {});
      const click = w.queue ? ` data-queue="${esc(w.key)}"` : dismissable(w) ? ` data-key="${esc(w.key)}" data-sig="${esc(warningSignature(w))}" data-todo="${esc(todoForWarning(w))}"
        title="Click to move this warning to the To do list. The game keeps the warning quiet from the next /reload"` : "";
      return `<div class="warn ${w.level}${w.invite ? " invite" : ""}${click && !w.queue ? " dismissable" : ""}"${click}>${esc(title)}${detail ? `<small>${esc(detail)}</small>` : ""}</div>`;
    }).join("");
  if (warnings.length && !sound.ctx) html += `<div class="warn sound">Click anywhere on the page once to turn on warning sounds</div>`;
  setHtml($("warnings"), html);
}


function row(key, label, value, state = "", bar = null) {
  return { key, label, value, state, bar };
}

const AMMO_STACK = 200;
function hoverHtml(name, pinned = false) {
  const other = window.HOVERS?.[name] || window.HOVERS?.[`${name.split(":")[0]}:`];
  if (other) return other(pinned, name);
  const d = alts.data, b = d?.chars?.[d.current]?.bags;
  if (!b) return `<div class="hv"><div class="hv-note">Your bags show here after the addon next reads them</div></div>`;
  wantItemInfo([...Object.keys(b.items), ...(b.each || []).map((x) => x.id)], () => refreshHover());
  const info = (id) => app.itemInfo?.[baseItem(id)] || {};
  const icon = (i) => (i.icon ? `<img src="/icon/${esc(i.icon)}.jpg" alt="">` : "");
  const line = (i, label, right, id) => `<div class="hv-row"${id ? ` data-tip="${id}"` : ""}>${icon(i)}<span class="hv-name${
    i.quest ? " hv-quest" : ""}">${label}</span><span class="hv-n">${right}</span></div>`;
  const foot = pinned ? "" : `<div class="hv-foot">Click to keep this list open</div>`;
  const bag = (x) => {
    const i = x.id ? info(x.id) : { icon: "inv_misc_bag_08", n: "Backpack" };
    const kind = x.family & 1 ? "quiver" : x.family & 2 ? "ammo pouch" : x.family ? "special" : "";
    return line(i, `${esc(i.n || "A bag")}${kind ? ` <small>${kind}</small>` : ""}`, `${x.free} <small>free of ${x.slots}</small>`, x.id || null);
  };
  if (name === "ammo") {
    const called = app.status?.strs?.ammoName, better = app.status?.strs?.ammoBetter;
    const ammo = Object.entries(b.items).filter(([id]) => info(id).n && [called, better].includes(info(id).n))
      .map(([id, n]) => line(info(id), esc(info(id).n), `${num(n)} <small>in ${Math.ceil(n / AMMO_STACK)} stack${n > AMMO_STACK ? "s" : ""}</small>`, id));
    const holders = (b.each || []).filter((x) => x.family & 3).map(bag);
    return `<div class="hv"><div class="hv-head">Ammo</div>${ammo.join("") || `<div class="hv-note">${esc(called || "No ammo")} isn't in your bags</div>`}
      ${holders.length ? `<div class="hv-head">Quiver or pouch</div>${holders.join("")}` : ""}${foot}</div>`;
  }
  const items = Object.entries(heldItems(b)).sort(([x], [y]) => (info(x).n || "").localeCompare(info(y).n || ""));
  const cap = pinned ? items.length : 24;
  const shown = items.slice(0, cap).map(([id, n]) => line(info(id), esc(info(id).n || `Item ${id}`), num(n), id)).join("");
  const more = items.length > cap ? `<div class="hv-note">and ${items.length - cap} more</div>` : "";
  const each = (b.each || []).map(bag).join("");
  return `<div class="hv">${each ? `<div class="hv-head">Bags</div>${each}` : ""}<div class="hv-head">In them</div>
    ${shown || `<div class="hv-note">Nothing</div>`}${more}${foot}</div>`;
}

function durabilityItem(n) {
  const id = n.durabilityItem;
  if (!id) return "";
  wantItemInfo([id], () => renderStatus());
  const name = app.itemInfo?.[id]?.n;
  return name ? ` <small class="st-item" data-tip="${id}">(${esc(name)})</small>` : "";
}

const BAR_START = tintRgb("low");
const BAR_END = tintRgb("error");

const BAR_PROGRESS = tintRgb("cyan-deep");

function barHot(bar) {
  if (!bar?.heat || !(bar.max > 0) || bar.dir !== "progress") return false;
  const stage = heatStage(Math.min(1, bar.value / bar.max), 1 / bar.max);
  return stage === "glow" || stage === "fire";
}

function barHtml(bar) {
  if (!bar || !(bar.max > 0)) return "";
  const frac = Math.max(0, Math.min(1, bar.value / bar.max));
  if (bar.dir === "progress") {
    const age = bar.heat ? heatLevelled(`${bar.heat}:${heatWho()}:${bar.max}`, frac >= 1 ? 1 : 0) : null;
    if (frac >= 1 && age == null) return "";
    const [r, g, b] = BAR_PROGRESS;
    const heat = bar.heat ? heatEdgeHtml(frac, 1 / bar.max) + heatBurstHtml(age) : "";
    return `<span class="st-bar" style="width:${Math.max(frac * 100, 3)}%;background:rgba(${r},${g},${b},0.4);box-shadow:inset -2px 0 0 ${tint("cyan", 0.9)}">${heat}</span>`;
  }
  const toBad = bar.dir === "fill" ? (frac - 0.5) / 0.5 : (0.5 - frac) / 0.5;
  if (toBad <= 0) return "";
  const t = Math.min(1, toBad);
  const [r, g, b] = BAR_START.map((c, i) => Math.round(c + (BAR_END[i] - c) * t));
  return `<span class="st-bar" style="width:${Math.max(frac * 100, 3)}%;background:rgba(${r},${g},${b},0.34);box-shadow:inset -2px 0 0 rgba(${r},${g},${b},0.9)"></span>`;
}

function sections(st, pos) {
  const n = st.nums || {}, s = st.strs || {}, out = [];
  const counted = (key, label) => (key in n ? row(key, label, num(n[key])) : null);

  const cls = [];
  if (st.classId === 3) {
    if (n.petActive) {
      if ("petHappiness" in n) cls.push(row("petHappiness", "Pet", `${HAPPINESS[n.petHappiness] || "?"} <small>${n.petDamage}% damage</small>`, "",
        { value: n.petHappiness, max: 3, dir: "empty" }));
      if (s.petLoyalty) cls.push(row("petLoyalty", "Loyalty", esc(s.petLoyalty)));
      if ("petTraining" in n) cls.push(row("petTraining", "Training points", num(n.petTraining)));
    } else {
      cls.push(row("petNone", "Pet", "Not out"));
    }
    if ("ammo" in n) cls.push(Object.assign(row("ammo", esc(ammoLabel(s)), `${num(n.ammo)}${n.ammo ? ` <small>${shootingTime(n).replace("about ", "")}</small>` : ""}`, "",
      n.ammoMax ? { value: n.ammo, max: n.ammoMax, dir: "empty" } : null), { hover: "ammo" }));
  }
  if (st.classId === 9) {
    cls.push(counted("shards", "Soul shards"), counted("healthstones", "Healthstones"), counted("soulstones", "Soulstones"));
    if (s.demon) cls.push(row("demon", "Demon", esc(s.demon)));
  }
  if (st.classId === 8) {
    cls.push(counted("arcanePowder", "Arcane Powder"), counted("runeTeleport", "Runes of Teleportation"),
      counted("runePortals", "Runes of Portals"), counted("lightFeather", "Light Feathers"), counted("manaGems", "Mana gems"));
  }
  if (st.classId === 4) {
    if ("mhEnchanted" in n) cls.push(row("mhPoison", "Main hand poison", poisonText(n, "mh"), "", { value: n.mhPoisonSec || 0, max: 1800, dir: "empty" }));
    if ("ohEnchanted" in n) cls.push(row("ohPoison", "Off hand poison", poisonText(n, "oh"), "", { value: n.ohPoisonSec || 0, max: 1800, dir: "empty" }));
    cls.push(counted("poisons", "Poisons in bags"), counted("flashPowder", "Flash Powder"), counted("blindingPowder", "Blinding Powder"));
  }
  if (st.classId === 5) cls.push(counted("holyCandles", "Holy Candles"), counted("sacredCandles", "Sacred Candles"));
  if (st.classId === 11) cls.push(counted("rebirthSeeds", "Rebirth seeds"), counted("giftReagents", "Gift of the Wild reagents"));
  if (st.classId === 2) cls.push(counted("divinitySymbols", "Symbols of Divinity"), counted("kingsSymbols", "Symbols of Kings"));
  if (st.classId === 7) {
    cls.push(counted("ankhs", "Ankhs"));
    if ("reincarnation" in n) cls.push(row("reincarnation", "Reincarnation", n.reincarnation ? clock(n.reincarnation) : "Ready"));
    for (const [key, label] of [["earthTotem", "Earth Totem"], ["fireTotem", "Fire Totem"], ["waterTotem", "Water Totem"], ["airTotem", "Air Totem"]]) {
      if (key in n) cls.push(row(key, label, n[key] ? "In bags" : "Missing"));
    }
    for (let i = 1; i <= 4; i++) {
      if (s[`totem${i}`]) cls.push(row(`totem${i}`, esc(s[`totem${i}`]), clock(n[`totem${i}`] || 0)));
    }
  }
  const classRows = cls.filter(Boolean);
  if (classRows.length) out.push({ title: st.className || "Class", classColor: CLASS_COLORS[st.className], rows: classRows });

  const supplies = [counted("food", "Food"), counted("water", "Water"), counted("bandages", "Bandages")].filter(Boolean);
  if (supplies.length) out.push({ title: "Supplies", rows: supplies });

  const hours = (n.sessionSeconds || 0) / 3600;
  const gold = [row("money", "Gold", money(n.money || 0))];
  if ("moneyStart" in n) gold.push(row("moneySession", "This session", signedMoney((n.money || 0) - n.moneyStart)));
  if (hours > 0.05 && "moneyStart" in n) gold.push(row("moneyHour", "Per hour", signedMoney(Math.round(((n.money || 0) - n.moneyStart) / hours))));
  gold.push(Object.assign(row("bags", "Free bag slots", `${n.bagFree ?? "?"} <small>of ${n.bagSlots ?? "?"}</small>`, n.bagFree === 0 ? "zero" : "",
    { value: (n.bagSlots || 0) - (n.bagFree || 0), max: n.bagSlots, dir: "fill" }), { hover: "bags" }));
  if (n.specialFree) gold.push(row("special", "Quiver or pouch free", num(n.specialFree)));
  out.push({ title: "Gold and bags", rows: gold });

  const gear = [];
  if ("durability" in n) gear.push(row("durability", "Lowest durability", `${n.durability}%${durabilityItem(n)}`, "", { value: n.durability, max: 100, dir: "empty" }));
  if ("ammo" in n && st.classId !== 3) gear.push(row("ammo", esc(ammoLabel(s)), num(n.ammo), "", n.ammoMax ? { value: n.ammo, max: n.ammoMax, dir: "empty" } : null));
  if (gear.length) out.push({ title: "Gear", rows: gear });
  const profs = app.professions || [];
  const skills = (st.skills || []).filter((sk) => !profs.some((p) => p.name === sk.name))
    .map((sk) => row(`skill-${sk.name}`, esc(sk.name), `${sk.rank} <small>/ ${sk.max}</small>`, "",
      { value: sk.rank, max: sk.max, dir: "progress", heat: `skill:${sk.name}` }));
  if (skills.length) out.push({ title: "Weapon skill", rows: skills });
  const levelled = profs.map((p) => {
    const up = skillRise(p.name, p.rank, n.sessionSeconds);
    return row(`skill-${p.name}`, esc(p.name), `${p.rank} <small>/ ${p.max}</small>${up > 0 ? ` <small class="st-up">+${up}</small>` : ""}`,
      skillRose(p.name, p.rank) ? "rose" : "", { value: p.rank, max: p.max, dir: "progress", heat: `skill:${p.name}` });
  });
  if (levelled.length) out.push({ title: "Skills", rows: levelled });

  if (pos && pos.xpMax && !(app.maxLevel != null && pos.level >= app.maxLevel)) {
    const left = pos.xpMax - pos.xp;
    const lvl = [];
    const perHour = hours > 0.03 ? n.sessionXP / hours : 0;
    lvl.push(row("xpHour", "XP per hour", perHour ? num(perHour) : "<small>measuring</small>"));
    if (perHour) lvl.push(row("toLevel", "Time to level", clock(left / perHour * 3600)));
    if (n.lastKillXP) {
      lvl.push(row("kills", "Kills to level", `${num(Math.ceil(left / n.lastKillXP))} <small>at ${num(n.lastKillXP)} XP</small>`));
      if (n.lastKillRested && pos.rested) lvl.push(row("restedKills", "Rested lasts", `${num(Math.ceil(pos.rested / (n.lastKillXP / 2)))} kills`));
    }
    out.push({ title: "Leveling", rows: lvl });
  }

  const travel = [];
  if (s.bind || "hearth" in n) travel.push(row("hearth", "Hearthstone", `${esc(s.bind || "")}${"hearth" in n ? ` <small>${n.hearth ? clock(n.hearth) : "ready"}</small>` : ""}`));
  if ("quests" in n) travel.push(row("quests", "Quests", `${n.quests} <small>of ${n.questsMax}</small>${n.questsDone ? ` <small>${n.questsDone} done</small>` : ""}`,
    n.quests >= n.questsMax ? "zero" : "", { value: n.quests, max: n.questsMax, dir: "fill" }));
  if (s.repName) travel.push(row("rep", esc(s.repName), `${REACTIONS[n.repReaction] || ""} <small>${num(n.repValue || 0)} / ${num(n.repMax || 0)}</small>`, "",
    { value: n.repValue || 0, max: n.repMax || 0, dir: "progress" }));
  if (travel.length) out.push({ title: "Travel and quests", rows: travel });

  const time = [];
  if ("serverMinutes" in n) time.push(row("server", "Server time", `${String(Math.floor(n.serverMinutes / 60)).padStart(2, "0")}:${String(n.serverMinutes % 60).padStart(2, "0")}`));
  if ("sessionSeconds" in n) time.push(row("session", "Session", clock(n.sessionSeconds)));
  if ("playedSeconds" in n) time.push(row("played", "Played", playedText(n.playedSeconds)));
  if ("levelSeconds" in n) time.push(row("levelPlayed", "This level", playedText(n.levelSeconds)));
  if (time.length) out.push({ title: "Time", rows: time });
  return out;
}

const skillStart = { key: null, at: 0, ranks: {} };
function skillRise(name, rank, session) {
  const key = charStore("skillStart", app.character), at = session != null ? Math.round(Date.now() / 60000 - session / 60) : 0;
  if (skillStart.key !== key) {
    let kept = null;
    try { kept = JSON.parse(localStorage.getItem(key) || "null"); } catch (e) {   }
    Object.assign(skillStart, { key, at: kept?.at ?? at, ranks: kept?.ranks || {} });
  }
  if (Math.abs(skillStart.at - at) > 2) { skillStart.at = at; skillStart.ranks = {}; }
  if (!(name in skillStart.ranks)) {
    skillStart.ranks[name] = rank;
    try { localStorage.setItem(key, JSON.stringify({ at: skillStart.at, ranks: skillStart.ranks })); } catch (e) {   }
  }
  return rank - skillStart.ranks[name];
}
const SKILL_LIT = 4000, skillSeen = {};
function skillRose(name, rank) {
  const key = `${app.character}|${name}`, seen = skillSeen[key];
  const at = seen && rank > seen.rank ? Date.now() : seen?.at || 0;
  skillSeen[key] = { rank, at };
  return Date.now() - at < SKILL_LIT;
}


const SECTION_ICONS = {
  Supplies: "inv_misc_bag_08", "Gold and bags": "inv_misc_coin_01", Gear: "inv_chest_chain_05", "Weapon skill": "inv_sword_04",
  Skills: "inv_misc_book_11",
  Leveling: "achievement_level_10", "Travel and quests": "inv_misc_map_01", Time: "inv_misc_pocketwatch_01", Party: "inv_misc_groupneedmore",
};
const ROW_ICONS = {
  petHappiness: "ability_hunter_beastcall", petNone: "ability_hunter_beastcall", petLoyalty: "ability_hunter_beastsoothe",
  petTraining: "ability_hunter_beasttraining", shards: "inv_misc_gem_amethyst_02", healthstones: "inv_stone_04",
  soulstones: "spell_shadow_soulgem", demon: "spell_shadow_summonimp", arcanePowder: "inv_misc_dust_01",
  runeTeleport: "inv_misc_rune_06", runePortals: "inv_misc_rune_08", lightFeather: "inv_feather_04", manaGems: "inv_misc_gem_emerald_01",
  mhPoison: "ability_poisons", ohPoison: "ability_poisons", poisons: "trade_brewpoison", flashPowder: "inv_misc_powder_purple",
  blindingPowder: "inv_misc_powder_green", holyCandles: "inv_misc_candle_02", sacredCandles: "inv_misc_candle_03",
  rebirthSeeds: "inv_misc_food_19", giftReagents: "inv_misc_herb_07", divinitySymbols: "inv_stone_weightstone_05",
  kingsSymbols: "inv_misc_symbolofkings_01", ankhs: "inv_jewelry_talisman_06", reincarnation: "spell_nature_reincarnation",
  earthTotem: "spell_nature_stoneskintotem", fireTotem: "spell_fire_searingtotem", waterTotem: "spell_frost_summonwaterelemental",
  airTotem: "spell_nature_windfury", food: "inv_misc_food_15", water: "inv_drink_07", bandages: "inv_misc_bandage_15",
  money: "inv_misc_coin_01", moneySession: "inv_misc_coin_02", moneyHour: "inv_misc_coin_03", bags: "inv_misc_bag_07",
  special: "inv_misc_quiver_03", durability: "trade_blacksmithing", xpHour: "spell_holy_surgeoflight",
  toLevel: "inv_misc_pocketwatch_02", kills: "ability_dualwield", restedKills: "spell_nature_sleep", hearth: "inv_misc_rune_01",
  quests: "inv_misc_note_06", rep: "achievement_reputation_01", server: "inv_misc_pocketwatch_01", session: "spell_holy_borrowedtime",
  played: "inv_misc_pocketwatch_03", levelPlayed: "spell_nature_timestop",
};
const SKILL_ICONS = {
  Axes: "inv_axe_01", "Two-Handed Axes": "inv_axe_09", Bows: "inv_weapon_bow_01", Guns: "inv_weapon_rifle_01", Maces: "inv_mace_01",
  "Two-Handed Maces": "inv_hammer_05", Polearms: "inv_spear_06", Swords: "inv_sword_04", "Two-Handed Swords": "inv_sword_06",
  Staves: "inv_staff_08", "Fist Weapons": "inv_gauntlets_04", Daggers: "inv_weapon_shortblade_01", Thrown: "inv_throwingknife_02",
  Crossbows: "inv_weapon_crossbow_01", Wands: "inv_wand_01", Lockpicking: "inv_misc_key_03",
  Alchemy: "trade_alchemy", Blacksmithing: "trade_blacksmithing", Enchanting: "trade_engraving", Engineering: "trade_engineering",
  Herbalism: "spell_nature_naturetouchgrow", Leatherworking: "trade_leatherworking", Mining: "trade_mining",
  Skinning: "inv_misc_pelt_wolf_01", Tailoring: "trade_tailoring", Jewelcrafting: "inv_misc_gem_01",
  Inscription: "inv_inscription_tradeskill01", Cooking: "inv_misc_food_15", "First Aid": "spell_holy_sealofsacrifice",
  Fishing: "trade_fishing",
};
function rowIcon(key, st) {
  if (key === "ammo") return st.nums?.ammoKind === 2 ? "inv_ammo_arrow_01" : "inv_ammo_bullet_01";
  if (key.startsWith("totem")) return "spell_nature_stoneskintotem";
  if (key.startsWith("skill-")) return SKILL_ICONS[key.slice(6)] || "inv_sword_04";
  return ROW_ICONS[key];
}
const stIcon = (name, cls = "st-ic") => name ? `<img class="${cls}" src="/icon/${esc(name)}.jpg" alt="">` : `<span class="${cls} none"></span>`;

function renderStatus() {
  const st = app.status;
  const box = $("status");
  if (!st?.nums) { box.hidden = true; return; }
  const levels = {};
  for (const w of st.warnings || []) levels[WARNING_ROW[w.key]] = w.level;
  const zeroKeys = new Set(Object.keys(st.nums).filter((k) => st.nums[k] === 0 && !ZERO_IS_FINE.has(k)));
  const help = helpButton("status"), party = partySection(help);
  const html = queueLineHtml() + party + sections(st, app.state).map((sec, i) => {
    const mine = !party && i === 0 ? help : "";
    const head = sec.classColor
      ? `<div class="st-head class" style="color:${sec.classColor}">${stIcon(`classicon_${(st.className || "").toLowerCase()}`, "st-hic")}${esc(sec.title)}${mine}</div>`
      : `<div class="st-head">${stIcon(SECTION_ICONS[sec.title], "st-hic")}${esc(sec.title)}${mine}</div>`;
    const rows = sec.rows.map((r) => {
      const state = `${levels[r.key] || r.state || (zeroKeys.has(r.key) ? "zero" : "")}${barHot(r.bar) ? " hot" : ""}`;
      return `<div class="st-row ${state}"${r.hover ? ` data-hover="${r.hover}"` : ""}>${barHtml(r.bar)}<span class="st-label">${stIcon(rowIcon(r.key, st))}${r.label}</span><span class="st-value">${r.value}</span></div>`;
    }).join("");
    return head + rows;
  }).join("");
  box.hidden = false;
  setHtml(box, html);
  renderWarnings();
  soundWarnings(activeWarnings());
  renderTodo();
  renderGuide();
}
