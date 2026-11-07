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

const minutes = (s) => `${Math.round(s / 60)} min`;
const span = (s) => (s >= 3600 && s % 3600 === 0 ? `${s / 3600} hour${s === 3600 ? "" : "s"}` : s >= 60 ? minutes(s) : `${s} s`);

function campState(r) {
  const bp = r.blueprint;
  switch (r.state) {
    case "ready": return `You can place ${r.name} now`;
    case "place": return `You have learnt ${r.name}. You need ${r.prof} ${r.place} to place it`;
    case "learn": return r.how === "blueprint" ? `Learn ${r.name} from ${bp.name} in your bags` : `Learn ${r.name} at a ${r.prof} trainer`;
    case "skill": return `You need ${r.prof} ${r.learn} to learn ${r.name}`;
    case "blueprint": {
      const who = bp.drops.find((d) => d.name);
      return `Find ${bp.name}. ${who ? `${who.name}${who.level ? ` (level ${who.level})` : ""} drops the blueprint${who.chance ? ` ${who.chance}% of the time` : ""}`
        : "We have no information yet on where the blueprint drops"}`;
    }
    default: return `You need ${r.prof} for ${r.name}`;
  }
}

function campRow(r, sub) {
  return `<tr class="camp-${esc(r.state)}"><th><span class="item-named" data-tip="${r.item}">${esc(r.name)}</span></th>
    <td>${sub}<small>${esc(campState(r))}</small></td></tr>`;
}

function campNow(c) {
  const now = [];
  if (c.benefitsLeft) now.push(`You have Camp Benefits with ${minutes(c.benefitsLeft)} left`);
  else if (c.benefitsLeft === null) now.push("You have Camp Benefits");
  if (c.cooldownLeft) now.push(`Your camp features are on cooldown for ${minutes(c.cooldownLeft)} more`);
  else if (c.cooldownLeft === false) now.push("Your camp features are ready");
  return now.join(". ");
}

function campLine(c) {
  const parts = [];
  if (c.sit && c.benefits) {
    parts.push(`Sitting or crafting by a campfire for ${span(c.sit)} gives Camp Benefits for ${span(c.benefits)}`,
      "Camp Benefits gives the buff of every feature placed round the campfire");
  }
  if (c.fire) parts.push(`A campfire and its features stand for ${span(c.fire)}`);
  if (c.cooldown) parts.push(`All camp features share a ${span(c.cooldown)} cooldown`);
  const now = campNow(c);
  return `${esc(parts.join(". "))}.${now ? ` <b>${esc(now)}.</b>` : ""}`;
}

const campFold = { open: keptOr("cc.campOpen", false) };
function campFolded(c) {
  const now = campNow(c), on = c.benefitsLeft || c.benefitsLeft === null;
  const line = on ? now : ["You have no Camp Benefits", now].filter(Boolean).join(". ");
  return `<p class="muted camp-now">${esc(line[0].toUpperCase() + line.slice(1))}.</p>`;
}
function toggleCamp() {
  campFold.open = !campFold.open;
  keepIn("cc.campOpen", campFold.open);
  renderDrawer();
}
$("drawer").addEventListener("click", (e) => { if (e.target.closest("button[data-camp-fold]")) toggleCamp(); });

const campSentences = (s) => (s || "").match(/[^.!?]+[.!?]+/g)?.map((x) => x.trim()) || [];
const CAMP_SENTENCE_ALIKE = [[/^May be placed over an? .+ to replace it\.$/, "An upgraded feature may be placed over the one it builds on to replace it."]];
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
  const fires = d.fires.map((f) => campRow(f, `This campfire needs Cooking ${f.place}.${
    f.holds ? ` The campfire holds ${f.holds} features${f.how === "skill" ? " and comes with Cooking" : ""}.` : f.how === "skill" ? " The campfire comes with Cooking." : ""
    } Placing the campfire takes ${esc(f.takes.map(([, n, name]) => `${n} ${name}`).join(" and "))}`)).join("");
  const features = d.features.map((p) => `<h4>${esc(p.prof)} ${p.rank}</h4><table class="facts camp-table">${
    p.tiers.map((t) => campRow(t, `${campNeedSaid(t) ? "" : `This feature needs ${esc(p.prof)} ${t.place}. `}${esc(campOwnSentences(t.use, shared))}`)).join("")}</table>`).join("");
  const none = d.features.length ? "" : `<p class="muted">None of your professions can place a camp feature yet. Every profession gets camp features from skill 20.</p>`;
  return `<p class="muted">${campLine(d.camp)}</p>${general.length ? `
    <p class="muted camp-all">Every camp feature: ${esc(general.join(" "))}</p>` : ""}
    <h4>Campfires</h4><table class="facts camp-table">${fires}</table>
    ${features || none}${d.others ? `<p class="muted">${d.others} other profession${d.others === 1 ? " has" : "s have"} camp features too.</p>` : ""}
    ${d.known ? "" : `<p class="muted">The known recipes show here after the addon's next /reload.</p>`}`;
}

on("playerDrawer", () => {
  askCamp(false);
  const d = camp.data;
  const open = campFold.open;
  const head = `<h3 class="camp-head${open ? " open" : ""}"><span class="with-help"><button class="camp-fold" data-camp-fold aria-expanded="${open}"
    title="${open ? "Collapse Camping" : "Show the campfires and the character's camp features"}"><img class="camp-ic" src="/icon/${CAMP_ICON}.jpg" alt="">Camping</button>${helpButton("camp")}</span></h3>`;
  return head + (!d ? `<p class="muted">${askNote("/api/camp", { what: "the camping data", again: () => { askCamp(true); renderDrawer(); } })}</p>`
    : open ? campHtml(d) : campFolded(d.camp));
});
