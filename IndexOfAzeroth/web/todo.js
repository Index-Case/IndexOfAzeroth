// The Index of Azeroth. Copyright 2026 Index Case <indexofazeroth@pm.me>. PolyForm Strict 1.0.0, see LICENSE.md.
"use strict";

const todo = { silenced: {}, dismissed: loadDismissed(), loaded: false, inDrawer: null, drawerItems: [], pulsedAt: 0, html: "" };
const NOTICE_SOURCES = [];

function loadTodo() {
  fetchUntil("/api/todo", (t) => { takeTodo(t); todo.loaded = true; sendOldDismissals(); renderTodo(); renderWarnings(); });
}
function refreshTodo(snap) {
  const v = todo.want = snap ? snap.versions?.todo : todo.want;
  if (v == null || v === todo.version) return;
  if (todo.version === undefined) { todo.version = v; return; }
  getJson("/api/todo", { key: "todo" })?.then((t) => {
    todo.version = v;
    takeTodo(t);
    renderTodo();
    renderWarnings();
  }, () => {});
}
function takeTodo(t) {
  todo.silenced = t.silenced || {};
  dismissed = t.dismissed || {};
}

function sendOldDismissals() {
  let old = {};
  try { old = JSON.parse(localStorage.getItem("cc.dismissed") || "{}") || {}; } catch (e) {   }
  const send = {};
  for (const [key, sig] of Object.entries(old)) {
    if (!dismissed[key] && String(sig).startsWith("low|") && todoIdOf(key)) send[key] = { sig, todo: todoIdOf(key) };
  }
  const forget = () => { try { localStorage.removeItem("cc.dismissed"); } catch (e) {   } };
  if (Object.keys(send).length) postTodo({ dismiss: send }, (t) => t.dismissed && forget());
  else forget();
}

function loadDismissed() {
  try { return JSON.parse(localStorage.getItem("cc.todoDismissed") || "{}"); } catch (e) { return {}; }
}
function saveDismissed() {
  try { localStorage.setItem("cc.todoDismissed", JSON.stringify(todo.dismissed)); } catch (e) {   }
}
function dismissTodo(id) { todo.dismissed[id] = true; saveDismissed(); renderTodo(); }
function undismissTodo(id) { delete todo.dismissed[id]; saveDismissed(); renderTodo(); }

function postTodo(body, after = null) {
  postJson("/api/todo", body).then((t) => { takeTodo(t); after?.(t); renderTodo(); renderWarnings(); },
    (e) => askFailed("The to-do list wasn't changed", e));
}

function isSilencedWarning(w) {
  return !!(w.spell && todo.silenced[`bars:${w.spell.name}`]);
}

const WARNING_TODO = { ammo: "restock:ammo", petUnhappy: "character:feedPet", shards: "restock:shards",
  mhPoison: "restock:mhPoison", ohPoison: "restock:ohPoison", poisons: "restock:poisons", water: "restock:water",
  ankh: "restock:ankhs", earthTotem: "restock:earthTotem", fireTotem: "restock:fireTotem", waterTotem: "restock:waterTotem",
  airTotem: "restock:airTotem", durability: "character:repair" };

const todoIdOf = (key) => (key.startsWith("rank:") ? `bars:${key.slice(5)}` : WARNING_TODO[key]);

function todoForWarning(w) {
  const id = todoIdOf(w.key);
  if (!id || todo.silenced[id] || !app.status) return null;
  return generatedLists(app.status).some(([, items]) => items.some((i) => i.id === id)) ? id : null;
}


const MAGE = 8, MANA_CLASSES = new Set([2, 3, 5, 7, 8, 9, 11]);
const REAGENTS = [
  { key: "arcanePowder", words: "Arcane Powder", item: "Arcane Powder" },
  { key: "runeTeleport", words: "Runes of Teleportation", item: "Rune of Teleportation" },
  { key: "runePortals", words: "Runes of Portals", item: "Rune of Portals" },
  { key: "lightFeather", words: "Light Feathers", item: "Light Feather" },
  { key: "holyCandles", words: "Holy Candles", item: "Holy Candle" },
  { key: "sacredCandles", words: "Sacred Candles", item: "Sacred Candle" },
  { key: "rebirthSeeds", words: "seeds for Rebirth", buys: ["Maple Seed", "Stranglethorn Seed", "Ashwood Seed", "Hornbeam Seed", "Ironwood Seed"] },
  { key: "giftReagents", words: "reagents for Gift of the Wild", buys: ["Wild Berries", "Wild Thornroot"] },
  { key: "divinitySymbols", words: "Symbols of Divinity", item: "Symbol of Divinity" },
  { key: "kingsSymbols", words: "Symbols of Kings", item: "Symbol of Kings" },
  { key: "flashPowder", words: "Flash Powder", item: "Flash Powder", cats: ["poisons", "reagents"] },
  { key: "ankhs", words: "Ankhs", item: "Ankh" },
];
const TOTEMS = [["earthTotem", "Earth Totem"], ["fireTotem", "Fire Totem"], ["waterTotem", "Water Totem"], ["airTotem", "Air Totem"]];

function campRestock(n) {
  const line = DirectorRules.line;
  if (!("camps" in n) || !n.campWood || n.camps >= DirectorRules.table.restock.camp_low) return null;
  const detail = n.camps === 0 ? line("heads", "camp_left_none") : n.camps === 1 ? line("heads", "camp_left_one")
    : line("heads", "camp_left", { n: n.camps });
  return { id: "restock:camp", text: line("heads", "camp_restock"), detail, goods: [n.campWood, ...(n.campTool ? [n.campTool] : [])] };
}

function generatedLists(st) {
  const n = st.nums || {}, s = st.strs || {}, restock = [], character = [], bars = [];
  const add = (list, id, text, detail = "", item = null) => list.push({ id, text, detail, ...(item && { item }) });
  const named = (name, words = name) => (name ? { name, words } : null);

  const gradeLine = (id, g, detail) => ({ id, text: word("both.restock.buy", { item: g.name, npc: g.npc }), detail,
    item: { name: g.name, words: g.name, id: g.item }, goods: [g.item], ...(g.to && { to: g.to }) });
  const asks = (g, low) => !!g && (low || !g.planned);

  if ("ammo" in n && st.classId === 3) {
    const low = n.ammoMax ? n.ammo < n.ammoMax / 2 : n.ammo < 1000;
    const held = s.ammoBetter || s.ammoName, grade = app.grades?.ammo;
    const kind = { 2: word("page.todo.ammo.kind.arrows"), 3: word("page.todo.ammo.kind.bullets") }[n.ammoKind]
      || word("page.todo.ammo.kind.any");
    const left = n.ammoMax ? word("page.todo.ammo.left-of", { n: num(n.ammo), max: num(n.ammoMax) }) : word("page.todo.ammo.left", { n: num(n.ammo) });
    if (asks(grade, low)) restock.push(gradeLine("restock:ammo", grade, low || !held ? left : word("page.todo.grade.ammo", { item: grade.name, held })));
    else if (low && !grade) add(restock, "restock:ammo", held ? word("page.todo.ammo.buy", { item: held }) : word("page.todo.ammo.buy-kind", { kind }), left, named(held));
  }
  if (s.ammoBetter) {
    add(character, "character:ammoSlot", word("page.todo.ammo.use", { better: s.ammoBetter }),
      s.ammoName ? word("page.todo.ammo.use.why", { better: s.ammoBetter, used: s.ammoName }) : word("page.todo.ammo.use.empty", { better: s.ammoBetter }),
      named(s.ammoBetter));
  }
  if (n.petActive && "petFood" in n && n.petFood < 10) {
    add(restock, "restock:petFood", "Buy food your pet eats", `${n.petFood} in bags${s.petDiet ? `, and your pet eats ${s.petDiet.toLowerCase()}` : ""}`);
  }
  if ("poisons" in n && n.poisons < 5) add(restock, "restock:poisons", "Buy poisons", `${n.poisons} left in bags`);
  for (const [hand, label] of [["mh", "main hand"], ["oh", "off hand"]]) {
    if (!(`${hand}Enchanted` in n)) continue;
    const sec = n[`${hand}PoisonSec`] || 0, charges = n[`${hand}PoisonCharges`] || 0;
    if (!n[`${hand}Enchanted`]) add(restock, `restock:${hand}Poison`, `Put poison on your ${label}`);
    else if (sec < 300 || (charges > 0 && charges < 20)) add(restock, `restock:${hand}Poison`, `Reapply poison on your ${label}`, `${clock(sec)} left`);
  }
  if ("shards" in n && n.shards < 3) add(restock, "restock:shards", "Collect soul shards", `${n.shards} left, so cast Drain Soul as a mob dies`);
  if (n.healthstones === 0) add(restock, "restock:healthstone", "Create a Healthstone");
  if (n.soulstones === 0) add(restock, "restock:soulstone", "Create a Soulstone");
  if (n.manaGems === 0) add(restock, "restock:manaGem", "Conjure a mana gem");
  if (MANA_CLASSES.has(st.classId)) {
    const verb = st.classId === MAGE ? "Conjure" : "Buy";
    const low = "water" in n && n.water < 5, grade = app.grades?.water;
    if (asks(grade, low)) restock.push(gradeLine("restock:water", grade, low ? `${n.water} left` : word("page.todo.grade.water", { item: grade.name })));
    else if (low && !grade) add(restock, "restock:water", `${verb} water`, `${n.water} left`);
    if ("food" in n && n.food < 5) add(restock, "restock:food", `${verb} food`, `${n.food} left`);
  }
  for (const { key, words, item } of REAGENTS) {
    if (n[key] === 0) add(restock, `restock:${key}`, `Buy ${words}`, "none in bags", named(item, words));
  }
  if (n.blindingPowder === 0) add(restock, "restock:blindingPowder", "Make Blinding Powder", "none in bags. You make it from Fadeleaf with your Poisons skill", named("Blinding Powder"));
  if (n.ankhs === 1) add(restock, "restock:ankhs", "Buy Ankhs", "1 left", named("Ankh", "Ankhs"));
  for (const [key, label] of TOTEMS) {
    if (n[key] === 0) add(restock, `restock:${key}`, `Get an ${label}`, `your ${label.split(" ")[0]} totems won't cast without the ${label}. Your shaman class quest gives the ${label}, and no vendor sells one`, named(label));
  }
  const campLine = campRestock(n);
  if (campLine) restock.push(campLine);
  if (n.petHappiness === 1) add(character, "character:feedPet", "Feed your pet", "your pet is unhappy and does 75% damage");
  if ("durability" in n && n.durability < 20) add(character, "character:repair", "Repair your gear", `lowest item at ${n.durability}%`);
  if (n.talentPoints > 0) {
    add(character, "character:talents", `Spend ${n.talentPoints} talent point${n.talentPoints > 1 ? "s" : ""}`);
  }
  const legacy = app.legacyPoints?.unspent;
  if (legacy > 0) add(character, "character:legacy", `Spend ${legacy} Legacy point${legacy > 1 ? "s" : ""}`);
  for (const r of app.bars?.ranks || []) {
    add(bars, `bars:${r.name}`, `Put ${r.name} Rank ${r.best} on your bars`, `Rank ${r.have} is on your bars now`);
  }
  for (const name of app.bars?.missing || []) {
    add(bars, `newspell:${name}`, `Put ${name} on your bars`, "the spell isn't on any bar or in any macro");
  }
  const crates = (app.crates || []).map((c) => ({ ...c }));
  return [["Restock", restock], ["Character", character], ["Action bars", bars], ["Merchant's Favor", crates], ...emit("todoLists", st)];
}


const TODO_HEAD_ICONS = { Restock: "inv_misc_bag_08", "Action bars": "inv_misc_book_07", "Auction house": "inv_misc_coin_02",
  "Merchant's Favor": "inv_crate_05" };
const CRATE_ICONS = { open: "inv_crate_05", fill: "inv_crate_07", handin: "inv_crate_08" };
const TODO_ICONS = {
  "restock:petFood": "inv_misc_food_14", "restock:healthstone": "inv_stone_04", "restock:soulstone": "spell_shadow_soulgem",
  "restock:manaGem": "inv_misc_gem_emerald_01", "character:feedPet": "ability_hunter_beasttraining",
  "character:repair": "trade_blacksmithing", "character:talents": "inv_misc_book_11",
  "character:legacy": "spell_holy_championsbond",
  "restock:camp": "spell_fire_fire",
};
function todoIcon(id, st) {
  if (TODO_ICONS[id]) return TODO_ICONS[id];
  const [kind, key] = id.split(":");
  if (kind === "restock") return rowIcon(key, st) || ROW_ICONS[key];
  if (kind === "bars" || kind === "newspell") return todo.spellIcons[key] || "inv_misc_book_07";
  if (kind === "crate") return CRATE_ICONS[key];
  return kind === "auction" ? "inv_misc_coin_02" : null;
}

todo.spellIcons = {};
const spellAsked = new Set();
function wantSpellIcons(names) {
  const need = [...new Set(names.filter((n) => n && !spellAsked.has(n)))];
  const asked = need.length && getJson(`/api/spellicons?names=${encodeURIComponent(need.join("|"))}`, { key: "spellicons" });
  if (!asked) return;
  need.forEach((n) => spellAsked.add(n));
  asked.then((j) => {
    Object.assign(todo.spellIcons, j);
    renderTodo();
  }, () => need.forEach((n) => spellAsked.delete(n)));
}
todo.itemIds = {};
const itemIdAsked = new Set();
function wantItemIds(names) {
  const need = [...new Set(names.filter((n) => n && !itemIdAsked.has(n)))];
  const asked = need.length && getJson(`/api/itemids?names=${encodeURIComponent(need.join("|"))}`, { key: "itemids" });
  if (!asked) return;
  need.forEach((n) => itemIdAsked.add(n));
  asked.then((j) => {
    Object.assign(todo.itemIds, j);
    renderTodo();
  }, () => need.forEach((n) => itemIdAsked.delete(n)));
}
const todoText = (i) => itemNamed(i.text, i.item && (i.item.id ?? todo.itemIds[i.item.name]), i.item?.words);

function todoHeadIcon(title, st) {
  return title === "Character" ? `classicon_${(st?.className || "").toLowerCase()}` : TODO_HEAD_ICONS[title];
}


function renderTodo() {
  const st = app.status, box = $("todo");
  const lists = st ? generatedLists(st) : [];
  const active = lists.flatMap(([, items]) => items);
  wantSpellIcons(active.map((i) => i.id).filter((id) => /^(bars|newspell):/.test(id)).map((id) => id.split(":")[1]));
  wantItemIds(active.filter((i) => i.item?.id == null).map((i) => i.item?.name));
  if (st) {
    const gone = Object.keys(todo.dismissed).filter((id) => !active.some((i) => i.id === id));
    gone.forEach((id) => delete todo.dismissed[id]);
    if (gone.length) saveDismissed();
  }
  const away = (i) => !!(todo.silenced[i.id] || todo.dismissed[i.id]);
  const body = lists.map(([title, items]) => {
    const shown = items.filter((i) => !away(i));
    if (!shown.length) return "";
    return `<div class="todo-list"><h4>${stIcon(todoHeadIcon(title, st), "st-hic")}${title}</h4>${shown.map((i) => `<div class="todo-item">
      ${stIcon(todoIcon(i.id, st), "st-ic todo-ic")}<span class="todo-text">${todoText(i)}${i.detail ? `<small>${esc(i.detail)}</small>` : ""}</span>
      ${guideCats(i.id) ? `<button class="guide-me" data-guide="${esc(i.id)}" title="This starts the Navigation Guide to the nearest vendor or repairer for this to-do item and copies the line for the in-game arrow">Guide me</button>`
        : i.to ? `<button class="guide-me" data-guide-to="${esc(i.id)}" title="This starts the Navigation Guide to ${esc(i.to.name)} and copies the line for the in-game arrow">Guide me</button>` : ""}
      <button data-dismiss="${esc(i.id)}" title="This takes the item out of the list while it applies. The item waits under Dismissed">Dismiss</button>
      ${i.once ? "" : `<button data-silence="${esc(i.id)}" data-label="${esc(i.text)}" title="This keeps the item out of the list for good. The item waits under Dismissed whenever it applies">Never show</button>`}</div>`).join("")}</div>`;
  }).join("");
  if (app.guide?.todoId && !active.some((i) => i.id === app.guide.todoId)) {
    endGuide(app.guide.none ? null : `The guide to ${app.guide.name} is over, because its To do item is done`, { stillInGame: true });
  }
  const html = body ? `<div class="todo-head"><span class="with-help"><span class="todo-title">To do</span>${helpButton("todo")}</span></div>${body}` : "";
  box.hidden = !body;
  setHtml(box, html);
  notices([...active.filter(away), ...movedWarnings().map(moveNotice), ...NOTICE_SOURCES.flatMap((f) => f())], !!st);
}
function moveNotice(w) {
  const icon = w.spell ? todo.spellIcons[w.spell.name] || "inv_misc_book_07" : rowIcon(WARNING_ROW[w.key] || w.key, app.status);
  return { id: `move:${w.key}`, move: w.key, icon, text: warningText(w, app.status?.nums || {})[0] };
}

$("todo").addEventListener("click", (e) => {
  const b = e.target.closest("button");
  if (!b) return;
  if (b.dataset.guide) startGuide(b.dataset.guide);
  else if (b.dataset.guideTo) guideToLine(b.dataset.guideTo);
  else if (b.dataset.dismiss) dismissTodo(b.dataset.dismiss);
  else if (b.dataset.silence) postTodo({ silence: b.dataset.silence, label: b.dataset.label });
});

function guideToLine(id) {
  const to = (app.crates || []).find((c) => c.id === id)?.to;
  if (to) guideToSpot(to.map, to.x, to.y, to.name, ["Trade representative", to.zone].filter(Boolean).join(", "));
}


const NOTICE_PULSE_MS = 4200;
function notices(items, known) {
  todo.drawerItems = items;
  $("btn-notices").hidden = !items.length;
  if (!items.length && app.drawer === "notices") openDrawer("notices");
  if (known && todo.loaded) {
    const now = new Set(items.map((i) => i.id));
    if (todo.inDrawer && [...now].some((id) => !todo.inDrawer.has(id))) pulseNotices();
    todo.inDrawer = now;
  }
  if (app.drawer === "notices") renderDrawer();
}
function pulseNotices() {
  const key = $("btn-notices");
  todo.pulsedAt = Date.now();
  key.classList.remove("notice-pulse");
  void key.offsetWidth;
  key.classList.add("notice-pulse");
  clearTimeout(todo.pulseTimer);
  todo.pulseTimer = setTimeout(() => key.classList.remove("notice-pulse"), NOTICE_PULSE_MS);
}
DRAWER_TITLES.notices = "Dismissed";
DRAWERS.notices = function () {
  const st = app.status;
  return `<p class="muted">These are the To do items dismissed or set to never show, and the warnings moved off
    the band, while they apply. Show again puts an item back.</p><div class="todo notices">${todo.drawerItems.map((i) => (i.again ? `<div class="todo-item">
    ${stIcon(i.icon, "st-ic todo-ic")}<span class="todo-text">${esc(i.text)}
    <small class="notice-why">${esc(i.why)}</small></span>
    <button data-again="${esc(i.id)}" title="This shows it again">Show again</button>
    </div>` : i.move ? `<div class="todo-item">
    ${stIcon(i.icon, "st-ic todo-ic")}<span class="todo-text">${esc(i.text)}
    <small class="notice-why">This warning stays off the band until it clears</small></span>
    <button data-unmove="${esc(i.move)}" title="This puts the warning back on the band, and in game from the next /reload">Show again</button>
    </div>` : `<div class="todo-item">
    ${stIcon(todoIcon(i.id, st), "st-ic todo-ic")}<span class="todo-text">${todoText(i)}${i.detail ? `<small>${esc(i.detail)}</small>` : ""}
    <small class="notice-why">${todo.silenced[i.id] ? "Never shown in To do" : "Dismissed while it applies"}</small></span>
    <button ${todo.silenced[i.id] ? `data-unsilence="${esc(i.id)}"` : `data-undismiss="${esc(i.id)}"`} title="This puts the item back in the To do list">Show again</button>
    </div>`)).join("")}</div>`;
};
$("drawer").addEventListener("click", (e) => {
  const b = e.target.closest("button[data-undismiss], button[data-unsilence], button[data-unmove], button[data-again]");
  if (!b) return;
  if (b.dataset.again) todo.drawerItems.find((i) => i.id === b.dataset.again)?.again();
  else if (b.dataset.undismiss) undismissTodo(b.dataset.undismiss);
  else if (b.dataset.unmove) moveBack(b.dataset.unmove);
  else postTodo({ unsilence: b.dataset.unsilence });
});

on("start", loadTodo);
on("snapshot", refreshTodo);
on("auction", () => renderTodo());
