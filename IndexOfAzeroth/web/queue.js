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
  const state = q.match ? "Group found" : q.invite ? "Invited" : q.queued ? "Queued" : q.listed ? "Listed"
    : q.applied ? "Asked to join" : null;
  if (!state) return null;
  return { state, what: q.what || "", minutes: q.since == null ? null : Math.max(0, Math.floor((now / 1000 - q.since) / 60)) };
}

function queueLineHtml(q = app.queue, now = Date.now()) {
  const line = queueLine(q, now);
  if (!line) return "";
  const waited = line.minutes == null ? "" : ` <small>${line.minutes} min</small>`;
  return `<div class="st-head st-queue"><img class="st-hic" src="/icon/${QUEUE_ICON}.jpg" alt="">Group finder: ${esc(line.state)}${waited}</div>${
    line.what ? `<div class="st-queue-what">${esc(line.what)}</div>` : ""}`;
}

function queueWords(q) {
  const e = q.event, name = e.name || "";
  const size = q.members ? `, ${q.members} in it${q.most ? ` of ${q.most}` : ""}` : "";
  if (e.kind === "invite" && e.source === "finder") {
    return ["GROUP FOUND", `The dungeon finder has a group${name ? ` for ${name}` : ""}. Accept the group in game`];
  }
  if (e.kind === "invite" && e.source === "listing") {
    return ["GROUP INVITE", `${name || "A group you asked to join"} invites you. Answer the invite in game`];
  }
  if (e.kind === "invite") return ["GROUP INVITE", `${name || "Someone"} invites you to a group. Answer the invite in game`];
  if (e.kind === "joined") {
    return ["GROUP FORMED", `${e.source === "invite" && name ? `You're in ${name}'s group` : `You joined ${name || "a group"}`}${size}`];
  }
  if (e.kind === "formed") return ["GROUP FORMED", `The dungeon finder's group${name ? ` for ${name}` : ""} is ready${size}`];
  if (e.kind === "full") return ["GROUP FULL", `Your group${name ? ` for ${name}` : ""} is full${size}`];
  return null;
}

function queueGoneWords(q) {
  const e = q.event, name = e.name || "";
  if (e.source === "finder") return `The dungeon finder's group fell through${q.queued ? ". You're back in the queue" : ""}`;
  if (e.source === "listing") return `${name || "A group you asked to join"} turned you down, or your ask ran out`;
  return `The group invite${name ? ` from ${name}` : ""} ran out or was taken back`;
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
