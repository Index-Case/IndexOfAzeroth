// The Index of Azeroth. Copyright 2026 Index Case <indexofazeroth@pm.me>. PolyForm Strict 1.0.0, see LICENSE.md.
"use strict";

const books = { data: null, at: 0, version: null, timer: 0, statsAsked: false, weighed: false, onMap: false };
try { books.onMap = localStorage.getItem("cc.booksOnMap") === "1"; } catch (e) {   }
const BOOKS_FRESH = 15000;
const BOOKS_LOOK = 2000;
const BOOK_ICON = "inv_misc_book_08";
const BOOK_HAD = { turned: "Turned in", bags: "In your bags, ready to hand in", bank: "In your bank" };
POI_LABEL.book = "A library book you haven't got. Click the book to start the Navigation Guide to it";

function askBooks(force) {
  const v = alts.want;
  if (!force && books.data && books.version === v && Date.now() - books.at < BOOKS_FRESH) return;
  getJson("/api/books")?.then((d) => {
    books.data = d;
    books.at = Date.now();
    books.version = v;
    askRingStats();
    booksShown();
  }, booksShown);
}
function booksShown() {
  if (!$("books").hidden) renderBooks();
  if (app.drawer === "player") renderDrawer();
  redraw();
}
function askRingStats() {
  loadStatWeights();
  const ids = books.data.rewards.flatMap((r) => [...r.choice, ...r.items]);
  const asked = !books.statsAsked && ids.length ? loadStats(ids) : null;
  if (!asked) return;
  books.statsAsked = true;
  asked.then(() => { books.statsAsked = false; if (!$("books").hidden) renderBooks(); });
}


const mySide = () => app.status?.strs?.faction || null;
const forMe = (b) => b.side === "Both" || !mySide() || b.side === mySide();
function spotWorld([map, x, y]) {
  const w = app.maps?.[map]?.world;
  return w ? { inst: app.maps[map].instance, ...toWorld(w, x / 100, y / 100) } : null;
}
function nearestSpot(b) {
  if (!b.spots.length) return null;
  const me = playerWorld(true);
  let best = { spot: b.spots[0], yards: null };
  for (const spot of b.spots) {
    const p = spotWorld(spot);
    if (!me || !p || p.inst !== me.inst) continue;
    const yards = Math.hypot(p.n - me.n, p.w - me.w);
    if (best.yards == null || yards < best.yards) best = { spot, yards };
  }
  return best;
}
const zoneOf = (spot) => app.maps?.[spot[0]]?.name || "";
function toFind() {
  return (books.data?.books || []).filter((b) => !b.had && forMe(b)).map((b) => ({ b, near: nearestSpot(b) }))
    .sort((x, y) => (x.near == null) - (y.near == null) || (x.near?.yards ?? Infinity) - (y.near?.yards ?? Infinity));
}
function guideToBook(b) {
  const [map, x, y] = nearestSpot(b).spot;
  guideToSpot(map, x, y, b.name, ["Library book", zoneOf([map])].filter(Boolean).join(", "));
}
const myLibrarian = () => (books.data?.librarians || []).find((l) => l.map && forMe(l)) || null;
function guideToLibrarian() {
  const l = myLibrarian();
  guideToSpot(l.map, l.x, l.y, l.name, ["Librarian", zoneOf([l.map])].filter(Boolean).join(", "));
}


on("playerDrawer", () => {
  askBooks(false);
  const d = books.data, ring = d?.rewards.find((r) => r.ring);
  const line = !d ? askNote("/api/books", { what: "the library books", again: () => { askBooks(true); renderDrawer(); } })
    : !d.known ? "The page shows which books you have once the game has sent the quests you've turned in."
      : `You have turned in ${num(d.count)} book${d.count === 1 ? "" : "s"}${ring?.books ? ` of the ${ring.books} the ring needs` : ""}${
        ring?.done ? ", and you have done the ring's quest" : ""}`;
  return `<h3>Library books</h3><p><button class="key" data-books="open" style="--icon:url(/icon/${BOOK_ICON}.jpg)"
      title="Opens Forever's library books. The window shows the books the character has, where the books still to find are and what 10 and 20 books give">Library books</button></p>
    <p class="muted">${line}</p>`;
});
$("drawer").addEventListener("click", (e) => { if (e.target.closest("button[data-books='open']")) openBooks(); });


function openBooks() {
  askBooks(true);
  renderBooks();
  clearInterval(books.timer);
  books.timer = setInterval(booksLook, BOOKS_LOOK);
}
function booksLook() {
  askBooks(false);
  if (books.weighed !== !!statWeights.data) renderBooks();
}
function closeBooks() {
  clearInterval(books.timer);
  $("books").hidden = true;
}

function rewardRow(id) {
  const [name, q, icon] = books.data.items[id] || [`Item ${id}`, 1, null];
  const it = statCache[id], u = it ? usability(it) : null;
  const r = it?.inv ? replaced(it.inv) : null, cmp = r?.known && u.use !== "never" ? compareGear({ ...it, st: inSlot(it.st, r.slot) }, r.against) : null;
  const words = !it ? "" : u.use === "never" ? "your class can't use this item" : cmp && !cmp.kind ? "not an upgrade for you" : "";
  return itemRowHtml({ id, icon: `/icon/${esc(icon || "inv_misc_questionmark")}.jpg`, q, name, line: esc(words),
    after: cmp?.kind ? upgradeTag(it, u, true, cmp) : "" });
}
function rewardHtml(r, count) {
  const takes = r.books ? `${r.books} books turned in` : "the number of books this reward takes isn't known yet";
  const state = r.done ? "Done" : r.open ? "You can take this reward at the librarian"
    : r.books && count != null ? `${r.books - count} more books to go` : "";
  const who = r.classes ? `, ${andList(Object.entries(CLASS_NAMES).filter(([id]) => r.classes & CLASS_BIT(+id)).map(([, n]) => n))} only` : "";
  const items = [...r.choice, ...r.items];
  return `<div class="bk-reward${r.done ? " done" : r.open ? " open" : ""}"><div class="bk-reward-head">
      <b>${esc(r.name)}</b><small>${esc(takes)}, level ${r.level}${r.req > 1 ? `, from level ${r.req}` : ""}${esc(who)}</small>
      ${state ? `<span class="bk-state">${esc(state)}</span>` : ""}</div>
    ${items.length ? `<div class="bk-items">${r.choice.length > 1 ? `<small class="muted">Choose one</small>` : ""}${items.map(rewardRow).join("")}</div>` : ""}</div>`;
}
function bookRow({ b, near }, shown = "find") {
  const [, q, icon] = books.data.items[b.item] || [b.name, 1, null];
  const where = near ? `${esc(zoneOf(near.spot))}${near.yards != null ? `, ${num(near.yards)} yd` : ""}` : "We have no information yet on where this book is";
  const from = b.from.length ? `. From ${esc(andList([...new Set(b.from.map((f) => f.name))]))}` : "";
  const state = shown === "had" ? `<span class="bk-state">${esc(BOOK_HAD[b.had])}</span>` : "";
  const go = shown === "find" ? `<button class="key small" data-book-go="${b.item}"${near ? "" : " disabled"}
      title="${near ? "Starts the Navigation Guide to the nearest spot of this book. Paste the line the page copies into the game's chat, as with every guide"
        : "We have no information yet on where this book is"}">Guide me</button>` : "";
  return `<div class="bk-row${shown === "other" ? " other" : ""}">${itemRowHtml({ id: b.item, icon: `/icon/${esc(icon || BOOK_ICON)}.jpg`, q, name: b.name,
    line: `${where}${from}. Opens <b>${esc(b.questName)}</b>, level ${b.level}${shown === "other" ? `, ${esc(b.side)} only` : ""}` })}${state}${go}</div>`;
}

function booksBody() {
  const d = books.data;
  if (!d) return `<p class="muted">${askNote("/api/books", { what: "the library books", again: () => { askBooks(true); renderBooks(); } })}</p>`;
  const lib = myLibrarian(), find = toFind(), had = d.books.filter((b) => b.had);
  const other = d.books.filter((b) => !b.had && !forMe(b));
  const steps = d.rewards.filter((r) => r.books).map((r) => r.books), top = Math.max(0, ...steps);
  const carried = had.filter((b) => b.had !== "turned").length;
  const head = !d.known ? `<p class="muted">The list of books shows once the game has sent
      the quests turned in, within a minute and a half of logging in.</p>`
    : `<div class="bk-meter" style="--fill:${top ? Math.min(100, (d.count / top) * 100).toFixed(1) : 0}%">${steps.map((n) =>
      `<span class="bk-step" style="left:${((n / top) * 100).toFixed(1)}%">${n}</span>`).join("")}</div>
      <p>You have turned in ${num(d.count)} book${d.count === 1 ? "" : "s"}${carried ? `, and ${carried} more ${carried === 1 ? "is" : "are"} in your bags or bank to hand in` : ""}.${lib
        ? ` Hand the books in to ${esc(lib.name)}${zoneOf([lib.map]) ? ` in ${esc(zoneOf([lib.map]))}` : ""}.` : ""}</p>`;
  const keys = `<div class="bk-keys"><button class="key small" data-book-near="1"${find.some((f) => f.near) ? "" : " disabled"}
      title="Starts the Navigation Guide to the nearest book still to find. Paste the line the page copies into the game's chat, as with every guide">Guide me to the nearest</button>
    ${lib ? `<button class="key small" data-book-librarian="1" title="Starts the Navigation Guide to ${esc(lib.name)}, the librarian who takes the books. Paste the line the page copies into the game's chat, as with every guide">Guide me to the librarian</button>` : ""}
    <label class="bk-onmap"><input type="checkbox" data-books-map="1"${books.onMap ? " checked" : ""}> On the map</label></div>`;
  const bank = had.some((b) => b.had === "bank") && d.bankAt ? `<p class="muted">The books in your bank are as you last saw the bank, ${ago(d.bankAt)}.</p>` : "";
  const later = d.noQuest.length ? `<h3>No quest takes these books yet</h3><p class="muted">The game has these books, but no source
      has a librarian's quest that takes them yet. Most of these books come from Forever's later levels. They don't count
      toward the rewards until a quest takes them.</p>
    <p>${esc(d.noQuest.map((b) => b.name).join(", "))}</p>` : "";
  return `${head}${keys}<h3>What the books give</h3>${d.rewards.map((r) => rewardHtml(r, d.count)).join("")}
    <h3>To find <small>${find.length}</small></h3>${find.map((f) => bookRow(f)).join("") || `<p class="muted">You have every book for your side.</p>`}
    ${had.length ? `<h3>Yours <small>${had.length}</small></h3>${bank}${had.map((b) => bookRow({ b, near: nearestSpot(b) }, "had")).join("")}` : ""}
    ${other.length ? `<h3>The other side's <small>${other.length}</small></h3>${other.map((b) => bookRow({ b, near: nearestSpot(b) }, "other")).join("")}` : ""}
    ${later}`;
}

function renderBooks() {
  const box = $("books"), scroller = box.querySelector(".rd-scroll"), kept = scroller ? scroller.scrollTop : 0;
  books.weighed = !!statWeights.data;
  setHtml(box, `<div class="rd-bar"><span class="rd-keys"></span>
    <span class="rd-title">Library books<small>The books the librarian takes, where they are and what 10 and 20 books give</small></span>
    <span class="rd-keys">${helpButton("books")}<button class="key small square x-mark" data-books-close="1" title="Close (Escape)">&times;</button></span></div>
    <div class="rd-scroll"><div class="bk-body">${booksBody()}</div></div>`);
  box.hidden = false;
  box.querySelector(".rd-scroll").scrollTop = kept;
}

function booksClicked(e) {
  const b = e.target.closest("button");
  if (!b || b.disabled) return;
  if (b.dataset.booksClose) return closeBooks();
  if (b.dataset.bookLibrarian) return guideToLibrarian();
  if (b.dataset.bookNear) return guideToBook(toFind()[0].b);
  const book = b.dataset.bookGo && books.data.books.find((x) => x.item === +b.dataset.bookGo);
  if (book) guideToBook(book);
}
$("books").addEventListener("click", booksClicked);
function booksOnMap(on) {
  books.onMap = on;
  try { localStorage.setItem("cc.booksOnMap", on ? "1" : "0"); } catch (e) {   }
  if (on) askBooks(false);
  if (!$("books").hidden) renderBooks();
  redraw();
}
function booksBoxChanged(e) {
  if (e.target.dataset.booksMap) booksOnMap(e.target.checked);
}
$("books").addEventListener("change", booksBoxChanged);
function layerRowChanged(e) {
  if (e.target.dataset.own !== "books") return;
  e.stopPropagation();
  booksOnMap(e.target.checked);
}
$("layer-menu").addEventListener("change", layerRowChanged, true);
on("layerMenu", () => `<div class="layer-group">Collecting</div><label><input type="checkbox" data-own="books"${books.onMap ? " checked" : ""}>
  Library books <small>the books still to find</small></label>`);
closable(LAYER.reader, () => !$("books").hidden, closeBooks);


function drawBooks(s, size, scale) {
  if (!books.onMap || app.dungeon) return;
  if (!books.data) return askBooks(false);
  const half = POI_SIZE / 2;
  for (const b of books.data.books) {
    if (b.had || !forMe(b)) continue;
    const icon = books.data.items[b.item]?.[2] || BOOK_ICON;
    for (const [map, px, py] of b.spots) {
      const [x, y] = toScreen(px / 100, py / 100, size, scale, map);
      if (!(x > -half && y > -half && x < W + half && y < H + half)) continue;
      drawPoiIcon(x, y, iconImage(icon));
      const sub = b.questName === b.name ? "" : `Opens ${b.questName}`;
      poi.drawn.push({ x, y, map, p: { name: b.name, sub, cat: "book", icon, x: px / 100, y: py / 100 } });
    }
  }
}
