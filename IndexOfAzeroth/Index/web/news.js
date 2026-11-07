// The Index of Azeroth. Copyright 2026 Index Case <indexofazeroth@pm.me>. PolyForm Strict 1.0.0, see LICENSE.md.
"use strict";

app.started = 0;
app.freshSince = {};
const newsOf = { link: (since) => newsRows().some((s) => (s.changed || 0) > since) };
let newsKey = "";

function seenAt(name) {
  let t = 0;
  try { t = +localStorage.getItem(`cc.seen.${name}`) || 0; } catch (e) {   }
  return t || app.started;
}
function markSeen(name) {
  try { localStorage.setItem(`cc.seen.${name}`, String(Math.round(Date.now() / 1000))); } catch (e) {   }
}
const freshAfter = (name) => app.freshSince[name] ?? seenAt(name);

const newsRows = () => [...(app.dataStatus?.sources || []), ...(app.addons?.list || [])];

function freshRow(changed) { return (changed || 0) > freshAfter("link") ? " fresh" : ""; }
function sourceName(label, url) {
  return url ? `<a class="src-link" href="${esc(url)}" target="_blank" rel="noopener noreferrer">${esc(label)}</a>` : esc(label);
}

function drawerOpened(name) {
  if (!newsOf[name]) return;
  app.freshSince[name] = seenAt(name);
  markSeen(name);
  renewNews();
}

function renewNews() {
  newsKey = "";
  updateNews();
}

function updateNews() {
  const names = Object.keys(newsOf);
  const news = Object.fromEntries(names.map((name) => [name, newsOf[name](seenAt(name))]));
  const key = `${names.map((name) => news[name]).join("|")}|${app.drawer}`;
  if (key === newsKey) return;
  newsKey = key;
  for (const name of names) {
    if (news[name] && app.drawer === name) markSeen(name);
    const on = news[name] && app.drawer !== name;
    document.querySelectorAll(`.key[data-drawer="${name}"] .key-news`).forEach((b) => { b.hidden = !on; });
  }
}

on("snapshot", (snap) => {
  if (snap?.started) app.started = snap.started;
  updateNews();
});
