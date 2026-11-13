// The Index of Azeroth. Copyright 2026 Index Case <indexofazeroth@pm.me>. PolyForm Strict 1.0.0, see LICENSE.md.
"use strict";


const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));

class Html {
  constructor(markup) { this.markup = markup; }
  toString() { return this.markup; }
}
const raw = (markup) => new Html(String(markup ?? ""));
const htmlPart = (v) => (v instanceof Html ? v.markup : Array.isArray(v) ? v.map(htmlPart).join("") : v == null || v === false ? "" : esc(v));
function html(strings, ...parts) {
  let out = strings[0];
  parts.forEach((p, i) => { out += htmlPart(p) + strings[i + 1]; });
  return new Html(out);
}
const num = (n) => Math.round(n).toLocaleString("en-US");
const andList = (names, and = "and") => (names.length > 1 ? `${names.slice(0, -1).join(", ")} ${and} ${names[names.length - 1]}` : names[0] || "");
const planReasons = (reasons) => {
  const verbs = reasons.filter((r) => /^[a-z]/.test(r)), whole = reasons.filter((r) => !/^[a-z]/.test(r));
  return [...whole, ...(verbs.length ? [word("page.format.reasons", { reasons: andList(verbs) })] : [])].join(". ");
};
const pct = (a, b) => (b > 0 ? Math.round((a / b) * 100) : 0);
function mobLevelText(levels, mob) {
  if (levels) return levels[1] == null || levels[1] === levels[0] ? word("page.format.level", { level: levels[0] })
    : word("page.format.level.range", { lo: levels[0], hi: levels[1] });
  if (mob) noteGap("mob-level", mob.id, mob.where, mob.name);
  return word("page.format.level.none");
}


const charName = (c) => [c?.name, c?.surname].filter(Boolean).join(" ");
function charSame(a, b) {
  if (!a?.name || !b?.name) return false;
  if (a.guid && b.guid) return a.guid === b.guid;
  return a.name === b.name && (a.surname == null || b.surname == null || a.surname === b.surname)
    && (!a.realm || !b.realm || a.realm === b.realm);
}
function charLabel(c, chars) {
  const full = charName(c), realm = c?.realm || "";
  const twin = [...(chars || [])].some((o) => charName(o) === full && (o?.realm || "") !== realm);
  return twin && realm ? `${full}-${c.realmName}` : full;
}

function itemNamed(text, id, name) {
  const line = String(text ?? ""), at = id && name ? line.toLowerCase().indexOf(String(name).toLowerCase()) : -1;
  if (at < 0) return esc(line);
  const end = at + String(name).length;
  return `${esc(line.slice(0, at))}<span class="item-named" data-tip="${esc(id)}">${esc(line.slice(at, end))}</span>${esc(line.slice(end))}`;
}

const itemKey = (v) => (/^\d+$/.test(String(v ?? "")) ? Number(v) : String(v ?? ""));
const baseItem = (key) => parseInt(key, 10) || 0;


const MONEY_COINS = { g: "gold", s: "silver", c: "copper" };
const coinPicture = (n, letter) => `${n}<img class="coin" src="/ui/${MONEY_COINS[letter]}.png" alt="${letter}">`;
function moneyParts(copper) {
  const v = Math.round(copper), g = Math.floor(v / 10000), s = Math.floor(v / 100) % 100, c = v % 100;
  const parts = [];
  if (g) parts.push([num(g), "g"]);
  if (s) parts.push([s, "s"]);
  if (c || !parts.length) parts.push([c, "c"]);
  return parts;
}
const money = (copper) => moneyParts(copper).map(([n, letter]) => coinPicture(n, letter)).join(" ");
const moneyText = (copper) => moneyParts(copper).map(([n, letter]) => `${n}${letter}`).join(" ");
function signedMoney(copper) {
  if (!copper) return "0";
  return `<span class="${copper > 0 ? "gain" : "loss"}">${copper > 0 ? "+" : "&minus;"}${money(Math.abs(copper))}</span>`;
}
const lineHtml = (line) => (Array.isArray(line) ? line.map((p) => (typeof p === "string" ? esc(p) : money(p.money))).join("") : esc(line));


function clock(sec) {
  sec = Math.max(0, Math.round(sec));
  const h = Math.floor(sec / 3600), m = Math.floor(sec / 60) % 60;
  if (h) return `${h} h ${m} min`;
  if (m) return `${m} min`;
  return `${sec} s`;
}
function playedText(sec) {
  const d = Math.floor(sec / 86400);
  return d ? `${d} d ${Math.floor(sec % 86400 / 3600)} h` : clock(sec);
}
function duration(sec) {
  const whole = Math.max(1, Math.round(sec));
  if (whole < 60) return `${whole} s`;
  const m = Math.floor(whole / 60), s = whole % 60;
  return s ? `${m} min ${s} s` : `${m} min`;
}
function hms(sec) {
  sec = Math.max(0, Math.round(sec));
  const h = Math.floor(sec / 3600), m = Math.floor(sec / 60) % 60, s = String(sec % 60).padStart(2, "0");
  return h ? `${h}:${String(m).padStart(2, "0")}:${s}` : `${m}:${s}`;
}
const hmsTurns = (sec) => (sec < 0.5 ? Infinity : sec - Math.round(sec) + 0.5);
function questClock(sec) {
  const s = Math.max(0, Math.floor(sec));
  return `${s >= 600 ? clock(s) : hms(s)} left`;
}
function restDuration(h) {
  if (h < 1) return `${Math.max(1, Math.round(h * 60))} min`;
  if (h < 48) return `${Math.round(h)} h`;
  return `${Math.round(h / 24)} days`;
}
const ROUGH_STEPS = [[5400, 60, "min"], [129600, 3600, "h"], [Infinity, 86400, "days"]];
const roughStep = (s) => ROUGH_STEPS.find(([below]) => s < below) ?? ROUGH_STEPS[ROUGH_STEPS.length - 1];
function roughSpan(s) {
  const [, unit, word] = roughStep(s);
  return `${Math.round(s / unit)} ${word}`;
}
function roughSpanTurns(s) {
  const [below, unit] = roughStep(s);
  return Math.min(below, (Math.round(s / unit) + 0.5) * unit) - s;
}
const JUST_NOW = 90;
function ago(t, now = Date.now() / 1000) {
  if (!t) return word("page.format.ago.never");
  const s = now - t;
  return s < JUST_NOW ? word("page.format.ago.now") : word("page.format.ago", { span: roughSpan(s) });
}
function agoTurns(t, now = Date.now() / 1000) {
  if (!t) return Infinity;
  const s = now - t;
  return s < JUST_NOW ? JUST_NOW - s : roughSpanTurns(s);
}
function dueText(due, now) {
  const s = due - now;
  return s <= 60 ? word("page.format.due.now") : word("page.format.due", { span: roughSpan(s) });
}
const timeOfDay = (t) => new Date(t * 1000).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", second: "2-digit" });


const sizeText = (n) => (n >= 1048576 ? `${(n / 1048576).toFixed(1)} MB` : n >= 1024 ? `${Math.round(n / 1024)} KB` : `${n} B`);


const searchBox = (id, placeholder, query) => `<input id="${esc(id)}" class="find-box" type="search" placeholder="${esc(placeholder)}"
  autocomplete="off" spellcheck="false" value="${esc(query)}">`;
function matchesSearch(text, query) {
  const searched = String(text ?? "").toLowerCase();
  return String(query ?? "").toLowerCase().split(/\s+/).every((word) => searched.includes(word));
}
const nothingMatches = () => `<p class="find-none">${esc(word("page.format.nothing"))} <button class="src-link" data-find-all>${
  esc(word("page.format.nothing.all"))}</button></p>`;

if (typeof module === "object") {
  module.exports = { esc, Html, raw, html, num, andList, planReasons, pct, mobLevelText, charName, charSame, charLabel,
                     itemNamed, itemKey, baseItem, MONEY_COINS, coinPicture, moneyParts, money, moneyText, signedMoney, lineHtml,
                     clock, playedText, duration, hms, hmsTurns, questClock, restDuration, roughSpan, roughSpanTurns, ago,
                     agoTurns, dueText, timeOfDay, sizeText,
                     searchBox, matchesSearch, nothingMatches };
}
