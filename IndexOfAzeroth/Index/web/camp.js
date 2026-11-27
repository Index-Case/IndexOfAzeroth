// The Index of Azeroth. Copyright 2026 Index Case <indexofazeroth@pm.me>. PolyForm Strict 1.0.0, see LICENSE.md.
"use strict";

const camp = { data: null, at: 0, version: null };
const CAMP_FRESH = 30000;
const CAMP_ICON = "spell_fire_fire";

function askCamp(force) {
  const v = alts.want;
  if (!force && camp.data && camp.version === v && Date.now() - camp.at < CAMP_FRESH) return;
  getJson("/api/camp")?.then((d) => {
    camp.data = d;
    camp.at = Date.now();
    camp.version = v;
    if (app.drawer === "player") renderDrawer();
  }, () => { if (app.drawer === "player") renderDrawer(); });
}

const minutes = (s) => word("page.camp.min", { n: String(Math.round(s / 60)) });
const span = (s) => (s >= 3600 && s % 3600 === 0 ? wordCount("page.camp.hours", s / 3600) : s >= 60 ? minutes(s)
  : word("page.camp.sec", { n: String(s) }));

function campState(r) {
  const bp = r.blueprint, name = r.name, prof = r.prof;
  switch (r.state) {
    case "ready": return word("page.camp.ready", { name });
    case "place": return word("page.camp.place", { name, prof, skill: r.place });
    case "learn": return r.how === "blueprint" ? word("page.camp.learn.blueprint", { name, item: bp.name }) : word("page.camp.learn", { name, prof });
    case "skill": return word("page.camp.skill", { name, prof, skill: r.learn });
    case "blueprint": {
      const d = bp.drops.find((x) => x.name);
      if (!d) return word("page.camp.find.none", { item: bp.name });
      const who = d.level ? word("page.camp.who.level", { who: d.name, level: d.level }) : d.name;
      return d.chance ? word("page.camp.find.chance", { item: bp.name, who, chance: d.chance }) : word("page.camp.find", { item: bp.name, who });
    }
    default: return word("page.camp.need", { name, prof });
  }
}

function campRow(r, sub) {
  return `<tr class="camp-${esc(r.state)}"><th><span class="item-named" data-tip="${r.item}">${esc(r.name)}</span></th>
    <td>${sub}<small>${esc(campState(r))}</small></td></tr>`;
}

function campNow(c) {
  const now = [];
  if (c.benefitsLeft) now.push(word("page.camp.now.benefits.left", { span: minutes(c.benefitsLeft) }));
  else if (c.benefitsLeft === null) now.push(word("page.camp.now.benefits"));
  if (c.cooldownLeft) now.push(word("page.camp.now.cooldown", { span: minutes(c.cooldownLeft) }));
  else if (c.cooldownLeft === false) now.push(word("page.camp.now.ready"));
  return now.join(". ");
}

function campLine(c) {
  const parts = [];
  if (c.sit && c.benefits) {
    parts.push(word("page.camp.sit", { sit: span(c.sit), span: span(c.benefits) }), word("page.camp.sit.buff"));
  }
  if (c.fire) parts.push(word("page.camp.fire", { span: span(c.fire) }));
  if (c.cooldown) parts.push(word("page.camp.cooldown", { span: span(c.cooldown) }));
  const now = campNow(c);
  return `${esc(parts.join(". "))}.${now ? ` <b>${esc(now)}.</b>` : ""}`;
}

const campFold = { open: keptOr("cc.campOpen", false) };
function campFolded(c) {
  const now = campNow(c), on = c.benefitsLeft || c.benefitsLeft === null;
  const line = on ? now : [word("page.camp.now.none"), now].filter(Boolean).join(". ");
  return `<p class="muted camp-now">${esc(line[0].toUpperCase() + line.slice(1))}.</p>`;
}
function toggleCamp() {
  campFold.open = !campFold.open;
  keepIn("cc.campOpen", campFold.open);
  renderDrawer();
}
$("drawer").addEventListener("click", (e) => { if (e.target.closest("button[data-camp-fold]")) toggleCamp(); });

const campSentences = (s) => (s || "").match(/[^.!?]+[.!?]+/g)?.map((x) => x.trim()) || [];
const CAMP_SENTENCE_ALIKE = [[/^May be placed over an? .+ to replace it\.$/, word("page.camp.upgrade")]];
const CAMP_PAGE_SAYS = [/share a cooldown/i];
const campSentenceKey = (s) => CAMP_SENTENCE_ALIKE.find(([re]) => re.test(s))?.[1] || s;
function campSharedSentences(features) {
  const profs = new Map();
  for (const p of features) for (const t of p.tiers) for (const s of campSentences(t.use)) {
    const k = campSentenceKey(s);
    if (!profs.has(k)) profs.set(k, new Set());
    profs.get(k).add(p.prof);
  }
  return new Set([...profs].filter(([, ps]) => ps.size > 1).map(([k]) => k));
}
const campOwnSentences = (use, shared) => campSentences(use).filter((s) => !shared.has(campSentenceKey(s))).join(" ");

const campNeedSaid = (t) => t.state === "place" || (t.state === "skill" && t.learn === t.place);

function campHtml(d) {
  const shared = campSharedSentences(d.features);
  const general = [...shared].filter((s) => !CAMP_PAGE_SAYS.some((re) => re.test(s)));
  const holds = (f) => (f.holds ? ` ${f.how === "skill" ? word("page.camp.campfire.holds.cooking", { n: f.holds }) : word("page.camp.campfire.holds", { n: f.holds })}`
    : f.how === "skill" ? ` ${word("page.camp.campfire.cooking")}` : "");
  const fires = d.fires.map((f) => campRow(f, `${word("page.camp.campfire.needs", { skill: f.place })}${holds(f)} ${word("page.camp.campfire.takes",
    { items: esc(f.takes.map(([, n, name]) => `${n} ${name}`).join(` ${word("page.camp.and")} `)) })}`)).join("");
  const features = d.features.map((p) => `<h4>${esc(p.prof)} ${p.rank}</h4><table class="facts camp-table">${
    p.tiers.map((t) => campRow(t, `${campNeedSaid(t) ? "" : `${word("page.camp.feature.needs", { prof: esc(p.prof), skill: t.place })} `}${esc(campOwnSentences(t.use, shared))}`)).join("")}</table>`).join("");
  const none = d.features.length ? "" : `<p class="muted">${word("page.camp.none")}</p>`;
  return `<p class="muted">${campLine(d.camp)}</p>${general.length ? `
    <p class="muted camp-all">${word("page.camp.every", { lines: esc(general.join(" ")) })}</p>` : ""}
    <h4>${word("page.camp.campfires")}</h4><table class="facts camp-table">${fires}</table>
    ${features || none}${d.others ? `<p class="muted">${wordCount("page.camp.others", d.others)}</p>` : ""}
    ${d.known ? "" : `<p class="muted">${word("page.camp.known")}</p>`}`;
}

on("playerDrawer", () => {
  askCamp(false);
  const d = camp.data;
  const open = campFold.open;
  const head = `<h3 class="camp-head${open ? " open" : ""}"><span class="with-help"><button class="camp-fold" data-camp-fold aria-expanded="${open}"
    title="${open ? word("page.camp.fold.close") : word("page.camp.fold.open")}"><img class="camp-ic" src="/icon/${CAMP_ICON}.jpg" alt="">${word("page.camp.title")}</button>${helpButton("camp")}</span></h3>`;
  return head + (!d ? `<p class="muted">${askNote("/api/camp", { what: word("page.camp.what"), again: () => { askCamp(true); renderDrawer(); } })}</p>`
    : open ? campHtml(d) : campFolded(d.camp));
});
