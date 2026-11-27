// The Index of Azeroth. Copyright 2026 Index Case <indexofazeroth@pm.me>. PolyForm Strict 1.0.0, see LICENSE.md.
"use strict";

const QUEUE_NEWS_MS = 120000;
const QUEUE_INVITE_MS = 120000;
const QUEUE_BEEP_MS = 15000;
const QUEUE_TOAST_MS = 30000;
const QUEUE_ICON = "inv_misc_groupneedmore";
const queueSeen = { key: null, beepAt: 0, dismissed: new Set() };

function queueLine(q, now = Date.now()) {
  if (!q) return null;
  const state = q.match ? word("page.queue.state.match") : q.invite ? word("page.queue.state.invite")
    : q.queued ? word("page.queue.state.queued") : q.listed ? word("page.queue.state.listed")
    : q.applied ? word("page.queue.state.applied") : null;
  if (!state) return null;
  return { state, what: q.what || "", minutes: q.since == null ? null : Math.max(0, Math.floor((now / 1000 - q.since) / 60)) };
}

function queueLineHtml(q = app.queue, now = Date.now()) {
  const line = queueLine(q, now);
  if (!line) return "";
  const waited = line.minutes == null ? "" : ` <small>${word("page.queue.minutes", { n: String(line.minutes) })}</small>`;
  return `<div class="st-head st-queue"><img class="st-hic" src="/icon/${QUEUE_ICON}.jpg" alt="">${word("page.queue.line", { state: esc(line.state) })}${waited}</div>${
    line.what ? `<div class="st-queue-what">${esc(line.what)}</div>` : ""}`;
}

function queueWords(q) {
  const e = q.event, name = e.name || "";
  const size = !q.members ? "" : `, ${q.most ? word("page.queue.size.most", { n: q.members, most: q.most }) : word("page.queue.size", { n: q.members })}`;
  if (e.kind === "invite" && e.source === "finder") {
    return [word("page.queue.found"), name ? word("page.queue.found.line.for", { name }) : word("page.queue.found.line")];
  }
  if (e.kind === "invite" && e.source === "listing") {
    return [word("page.queue.invite"), name ? word("page.queue.invite.listing.named", { name }) : word("page.queue.invite.listing")];
  }
  if (e.kind === "invite") return [word("page.queue.invite"), name ? word("page.queue.invite.line.named", { name }) : word("page.queue.invite.line")];
  if (e.kind === "joined") {
    const joined = e.source === "invite" && name ? word("page.queue.joined.invite", { name })
      : name ? word("page.queue.joined", { name }) : word("page.queue.joined.group");
    return [word("page.queue.formed"), joined + size];
  }
  if (e.kind === "formed") {
    return [word("page.queue.formed"), (name ? word("page.queue.formed.line.for", { name }) : word("page.queue.formed.line")) + size];
  }
  if (e.kind === "full") return [word("page.queue.full"), (name ? word("page.queue.full.line.for", { name }) : word("page.queue.full.line")) + size];
  return null;
}

function queueGoneWords(q) {
  const e = q.event, name = e.name || "";
  if (e.source === "finder") return q.queued ? word("page.queue.gone.finder.queued") : word("page.queue.gone.finder");
  if (e.source === "listing") return name ? word("page.queue.gone.listing.named", { name }) : word("page.queue.gone.listing");
  return name ? word("page.queue.gone.invite.from", { name }) : word("page.queue.gone.invite");
}

const queueKey = (e) => `queue:${e.n}:${e.at}`;

function queueNotices(q = app.queue, now = Date.now(), dismissed = queueSeen.dismissed) {
  const e = q?.event;
  if (!e || e.at == null || dismissed.has(queueKey(e))) return [];
  const age = now - e.at * 1000, words = queueWords(q);
  if (!words) return [];
  if (e.kind === "invite" ? !(q.invite || q.match) || age > QUEUE_INVITE_MS : age > QUEUE_NEWS_MS) return [];
  return [{ key: queueKey(e), level: "news", text: words[0], detail: words[1], queue: true, invite: e.kind === "invite" }];
}

function applyQueue(now = Date.now()) {
  const q = app.queue, e = q?.event;
  const key = e?.at == null ? null : queueKey(e);
  if (key && key !== queueSeen.key && now - e.at * 1000 < QUEUE_TOAST_MS) {
    const words = queueWords(q);
    showToast(words ? `${words[0][0]}${words[0].slice(1).toLowerCase()}: ${words[1]}` : queueGoneWords(q));
    queueSeen.beepAt = now;
  }
  queueSeen.key = key;
  const open = queueNotices(q, now).find((n) => n.invite);
  if (open && now - queueSeen.beepAt >= QUEUE_BEEP_MS) {
    queueSeen.beepAt = now;
    beep(false);
  }
}

function dismissQueue(key) {
  queueSeen.dismissed.add(key);
  renderWarnings();
}

if (typeof module === "object") {
  module.exports = { QUEUE_NEWS_MS, QUEUE_INVITE_MS, QUEUE_BEEP_MS, QUEUE_TOAST_MS, QUEUE_ICON, queueSeen, queueLine, queueLineHtml,
    queueWords, queueGoneWords, queueNotices, applyQueue, dismissQueue };
}
