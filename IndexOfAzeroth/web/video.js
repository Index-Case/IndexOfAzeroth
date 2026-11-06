// The Index of Azeroth. Copyright 2026 Index Case <indexofazeroth@pm.me>. PolyForm Strict 1.0.0, see LICENSE.md.
"use strict";

const VIDEO_MIN = { w: 320, h: 200 };
const VIDEO_START = { w: 480, h: 326 };
const VIDEO_SAVED_MAX = 50;
const video = { open: false, link: "", x: null, y: null, w: VIDEO_START.w, h: VIDEO_START.h, saved: [], autoplay: true, showing: null,
  player: null, live: {}, seen: {}, checkedAt: 0, told: {}, saying: [], sayTimer: 0, volume: 100, muted: false, heard: false,
  askedAt: 0, sound: null, soundTimer: 0, at: null, started: false, keptAt: 0, back: null, left: null, held: false };
const VIDEO_KEEP_EVERY = 5000;

function videoSeconds(t) {
  const m = /^(?:(\d+)h)?(?:(\d+)m)?(?:(\d+)s?)?$/.exec(t || "");
  return m ? (+m[1] || 0) * 3600 + (+m[2] || 0) * 60 + (+m[3] || 0) : 0;
}

const TWITCH_PAGES = new Set(["directory", "downloads", "drops", "following", "inventory", "jobs", "login", "messages", "p",
  "prime", "search", "settings", "signup", "subscriptions", "turbo", "videos", "wallet"]);
const KICK_PAGES = new Set(["browse", "categories", "category", "dashboard", "following", "search", "settings", "subscriptions"]);

const youTubeLive = (channel) => `https://www.youtube.com/channel/${channel}/live`;
const youTubeChannel = (channel) => ({ site: "YouTube", what: "live", name: `channel ${channel}`, live: true, channel,
  src: `https://www.youtube.com/embed/live_stream?channel=${channel}` });

function youTubeSource(where, path, q) {
  if (path[0] === "channel" && /^UC[\w-]{22}$/.test(path[1] || "")) return youTubeChannel(path[1]);
  if (/^@[\w.-]{3,30}$/.test(path[0] || "") && (!path[1] || path[1] === "live")) {
    return { site: "YouTube", what: `${path[0]} live`, name: path[0], live: true, handle: path[0] };
  }
  const id = where === "youtu.be" ? path[0] : path[0] === "watch" ? q.get("v")
    : ["shorts", "live", "embed", "v", "e"].includes(path[0]) ? path[1] : null;
  const list = q.get("list");
  if (!/^[\w-]{11}$/.test(id || "")) {
    if (path[0] === "playlist" && list) {
      return { site: "YouTube", what: "a playlist", name: `playlist ${list}`, src: `https://www.youtube.com/embed/videoseries?list=${encodeURIComponent(list)}` };
    }
    return { error: word("page.video.orb.none", { site: "YouTube" }) };
  }
  const more = new URLSearchParams({ rel: "0" });
  const start = videoSeconds(q.get("t") || q.get("start"));
  if (start) more.set("start", String(start));
  if (list) more.set("list", list);
  const from = start ? ` from ${Math.floor(start / 60)}:${String(start % 60).padStart(2, "0")}` : "";
  return { site: "YouTube", what: list ? "a video in a playlist" : "a video", name: `video ${id}${from}`, id, src: `https://www.youtube.com/embed/${id}?${more}` };
}

function twitchSource(where, path, q, host) {
  const parent = `parent=${encodeURIComponent(host)}`;
  const clip = where === "clips.twitch.tv" ? path[0] : path[1] === "clip" ? path[2] : null;
  if (clip) {
    return { site: "Twitch", what: "a clip", name: `clip ${clip}`, clip: true, src: `https://clips.twitch.tv/embed?clip=${encodeURIComponent(clip)}&${parent}` };
  }
  if (path[0] === "videos" && /^\d+$/.test(path[1] || "")) {
    const s = videoSeconds(q.get("t"));
    const time = s ? `&time=${Math.floor(s / 3600)}h${Math.floor(s / 60) % 60}m${s % 60}s` : "";
    return { site: "Twitch", what: "a past broadcast", name: `broadcast ${path[1]}`, src: `https://player.twitch.tv/?video=${path[1]}${time}&${parent}` };
  }
  const channel = path[0] === "popout" ? path[1] : path[0];
  if (!/^\w{2,25}$/.test(channel || "") || TWITCH_PAGES.has(channel.toLowerCase())) return { error: word("page.video.orb.none", { site: "Twitch" }) };
  const id = channel.toLowerCase();
  return { site: "Twitch", what: `${channel} live`, name: channel, live: true, channel: id, src: `https://player.twitch.tv/?channel=${id}&${parent}` };
}

function kickSource(path, q) {
  if (path.length > 1 || q.has("clip")) return { error: word("page.video.orb.kick") };
  const channel = path[0];
  if (!/^[\w-]{2,30}$/.test(channel || "") || KICK_PAGES.has(channel.toLowerCase())) return { error: word("page.video.orb.none", { site: "Kick" }) };
  const id = channel.toLowerCase();
  return { site: "Kick", what: `${channel} live`, name: channel, live: true, channel: id, src: `https://player.kick.com/${id}` };
}

function videoSource(text, host) {
  let url;
  try {
    url = new URL(/^[a-z][\w+.-]*:\/\//i.test(text) ? text : `https://${text}`);
  } catch (e) {
    return { error: word("page.video.orb.unknown") };
  }
  if (!/^https?:$/.test(url.protocol)) return { error: word("page.video.orb.unknown") };
  const where = url.hostname.toLowerCase().replace(/^(?:www|m|music)\./, "");
  const path = url.pathname.split("/").filter(Boolean), q = url.searchParams;
  if (["youtube.com", "youtu.be", "youtube-nocookie.com"].includes(where)) return youTubeSource(where, path, q);
  if (where === "twitch.tv" || where === "clips.twitch.tv") return twitchSource(where, path, q, host);
  if (where === "kick.com") return kickSource(path, q);
  return { error: word("page.video.orb.unknown") };
}

const VIDEO_AUTOPLAY = { YouTube: ["autoplay=1", ""], Twitch: ["autoplay=true", "autoplay=false"], Kick: ["autoplay=true", "autoplay=false"] };
const VIDEO_MUTED = { YouTube: "mute=1", Twitch: "muted=true", Kick: "muted=true" };
function videoFrame(source, autoplay, origin = "", muted = false) {
  const talk = source.site === "YouTube" ? ["enablejsapi=1", origin && `origin=${encodeURIComponent(origin)}`] : [];
  const add = [VIDEO_AUTOPLAY[source.site][autoplay ? 0 : 1], muted && VIDEO_MUTED[source.site], ...talk].filter(Boolean).join("&");
  const src = add ? `${source.src}${source.src.includes("?") ? "&" : "?"}${add}` : source.src;
  return `<iframe${source.site === "Kick" ? ` class="vd-wide"` : ""} src="${esc(src)}" aria-label="${esc(`${source.site}: ${source.what}`)}"
    allow="autoplay; encrypted-media; fullscreen; picture-in-picture" referrerpolicy="strict-origin-when-cross-origin"></iframe>`;
}


function loadVideo() {
  let kept = {};
  try { kept = JSON.parse(localStorage.getItem("cc.video") || "{}") || {}; } catch (e) {   }
  video.link = typeof kept.link === "string" ? kept.link : "";
  for (const k of ["x", "y", "w", "h"]) if (Number.isFinite(kept[k])) video[k] = kept[k];
  const whole = (s) => ["link", "name", "site"].every((k) => typeof s?.[k] === "string");
  video.saved = (Array.isArray(kept.saved) ? kept.saved : []).filter(whole).slice(0, VIDEO_SAVED_MAX)
    .map(({ link, name, site, fav }) => (fav === true ? { link, name, site, fav } : { link, name, site }));
  video.autoplay = kept.autoplay !== false;
  video.volume = Number.isInteger(kept.volume) && kept.volume >= 0 && kept.volume <= 100 ? kept.volume : 100;
  video.muted = kept.muted === true;
  const links = (marks) => Object.fromEntries(Object.entries(marks && typeof marks === "object" ? marks : {}).filter(([, v]) => v === true));
  video.seen = links(kept.seen);
  video.told = links(kept.told);
  const at = kept.at && typeof kept.at === "object" ? kept.at : {};
  const time = Number.isFinite(at.time) && at.time > 0 ? at.time : 0, id = typeof at.id === "string" && /^[\w-]{11}$/.test(at.id) ? at.id : null;
  video.back = kept.open === true ? { time, playing: typeof at.playing === "boolean" ? at.playing : null, id } : null;
  video.left = kept.open !== true && time && video.link ? { link: video.link, time, id } : null;
}
function saveVideo() {
  const { link, x, y, w, h, saved, autoplay, volume, open } = video;
  const mine = (marks) => Object.fromEntries(saved.filter((s) => marks[s.link]).map((s) => [s.link, true]));
  const seen = mine(video.seen), told = mine(video.told), muted = video.held ? false : video.muted;
  const left = !open && video.left?.link === link ? video.left : null;
  const at = open && video.at?.link === link ? { time: video.at.time, playing: video.at.playing, id: video.at.id || undefined }
    : left ? { time: left.time, id: left.id || undefined } : undefined;
  video.keptAt = Date.now();
  try {
    localStorage.setItem("cc.video", JSON.stringify({ link, x, y, w, h, saved, autoplay, volume, muted, seen, told, open, at }));
  } catch (e) {   }
}

const videoRoom = () => { const stage = $("video").parentElement; return { W: stage.clientWidth, H: stage.clientHeight }; };

function placeVideo() {
  const { W, H } = videoRoom();
  if (!(W > 0 && H > 0)) return;
  const fit = (v, lo, hi, first) => Math.max(lo, Math.min(hi, v ?? first));
  video.w = fit(video.w, VIDEO_MIN.w, W, VIDEO_START.w);
  video.h = fit(video.h, VIDEO_MIN.h, H, VIDEO_START.h);
  video.x = fit(video.x, 0, W - video.w, W - video.w - 16);
  video.y = fit(video.y, 0, H - video.h, 60);
  Object.assign($("video").style, { left: `${video.x}px`, top: `${video.y}px`, width: `${video.w}px`, height: `${video.h}px` });
}

function openVideo(back = null) {
  const was = video.left?.link === video.link && !back ? { time: video.left.time, playing: null, id: video.left.id } : null;
  video.left = null;
  video.open = true;
  $("video").hidden = false;
  $("btn-video").setAttribute("aria-pressed", "true");
  placeVideo();
  if (Date.now() - video.checkedAt >= LIVE_EVERY) checkLive();
  sayOnline();
  const source = video.link ? videoSource(video.link, location.hostname) : null;
  if (source && !source.error) {
    if (back) resumeVideo(source, back);
    else if (was) showVideo(resumeAt(source, was), video.autoplay, was);
    else showVideo(source, video.autoplay);
    return saveVideo();
  }
  video.link = "";
  saveVideo();
  video.showing = null;
  renderSaved();
  renderCatchUp();
  renderSound();
  $("video-title").innerHTML = "Video";
  $("video-screen").innerHTML = `<p class="vd-idle">The orb waits for a link from YouTube, Twitch or Kick.</p>`;
  showVideoLink(true);
}
function closeVideo() {
  video.open = false;
  const at = video.at;
  video.left = at?.link === video.link && at.time > 0 ? { link: at.link, time: at.time, id: at.id } : null;
  video.showing = video.player = video.at = null;
  video.heard = false;
  if (video.held) video.held = video.muted = false;
  saveVideo();
  renderSound();
  clearTimeout(video.soundTimer);
  $("video").hidden = true;
  $("btn-video").setAttribute("aria-pressed", "false");
  $("video-screen").innerHTML = "";
  showVideoLink(false);
  showSaved(false);
  askKeep(false);
  stopSaying();
}
const toggleVideo = () => (video.open ? closeVideo() : openVideo());

function showVideo(source, autoplay, back = null) {
  if (!back && video.held) video.held = video.muted = false;
  video.showing = source;
  video.player = video.sound = null;
  video.heard = video.started = false;
  video.at = back && !source.live ? { link: video.link, time: back.time, playing: back.playing, id: back.id } : null;
  clearTimeout(video.soundTimer);
  askKeep(false);
  $("video-title").innerHTML = `${esc(source.site)}<small>${esc(source.what)}</small>`;
  $("video-screen").innerHTML = videoFrame(source, autoplay, location.origin, video.muted);
  const frame = playerFrame();
  if (source.site === "YouTube") frame?.addEventListener("load", () => youTubeSay(frame, { event: "listening" }));
  fitPlayer();
  renderSaved();
  renderCatchUp();
  renderSound();
}
const playerFrame = () => $("video-screen").querySelector("iframe");

function restoreVideo() {
  const back = video.back;
  video.back = null;
  if (!back) return;
  openVideo(back);
  askFrame(() => { if (video.open) placeVideo(); });
}
function resumeVideo(source, back) {
  const play = back.playing ?? video.autoplay;
  if (play && !video.muted && !soundAllowed()) video.held = video.muted = true;
  showVideo(resumeAt(source, back), play, back);
}
function soundAllowed() {
  try {
    return navigator.userActivation?.hasBeenActive === true || navigator.getAutoplayPolicy?.("mediaelement") === "allowed";
  } catch (e) {
    return false;
  }
}
function resumeAt(source, back) {
  if (source.live || source.clip || source.site === "Kick") return source;
  const url = new URL(source.src), t = Math.floor(back.time), q = url.searchParams;
  if (source.site === "YouTube") {
    if (back.id && back.id !== source.id && q.has("list")) url.pathname = `/embed/${back.id}`;
    if (t > 0) q.set("start", String(t));
  } else if (t > 0) {
    q.set("time", `${Math.floor(t / 3600)}h${Math.floor(t / 60) % 60}m${t % 60}s`);
  }
  return { ...source, src: url.href };
}

function playedTo(time, playing, id) {
  if (video.showing.live || video.player?.live) {
    if (video.at) { video.at = null; saveVideo(); }
    return;
  }
  if (typeof playing === "boolean") video.started = true;
  const was = video.at, at = video.at = { link: video.link, time: was?.time ?? 0, playing: was?.playing ?? null, id: was?.id ?? null };
  if (id) at.id = id;
  if (typeof playing === "boolean") at.playing = playing;
  if (video.started && Number.isFinite(time) && time >= 0) at.time = time;
  const moved = at.time !== (was?.time ?? 0) && Date.now() - video.keptAt >= VIDEO_KEEP_EVERY;
  if (at.playing !== (was?.playing ?? null) || at.id !== (was?.id ?? null) || moved) saveVideo();
}

function playerMessage(e) {
  if (e.source && e.source !== playerFrame()?.contentWindow) return;
  const site = video.showing?.site;
  if (site === "YouTube" && e.origin === "https://www.youtube.com") youTubeTold(e.data);
  else if (site === "Twitch" && e.origin === "https://player.twitch.tv") twitchTold(e.data);
}

const youTubeSay = (frame, msg) => frame?.contentWindow?.postMessage(JSON.stringify({ id: 1, channel: "widget", ...msg }), "https://www.youtube.com");
function youTubeTold(data) {
  let said;
  try { said = JSON.parse(data); } catch (err) { return; }
  if (said?.event === "onReady") return playerReady();
  const info = said?.info;
  if (!info || typeof info !== "object") return;
  const p = video.player ||= {};
  if (info.videoData) {
    if (info.videoData.title) p.title = info.videoData.title;
    if (info.videoData.author) p.author = info.videoData.author;
    p.live = !!info.videoData.isLive;
  }
  if (Number.isFinite(info.duration)) p.duration = info.duration;
  if (Number.isFinite(info.progressState?.seekableEnd)) p.end = info.progressState.seekableEnd;
  if (p.title) $("video-title").innerHTML = `YouTube<small>${esc(p.title)}</small>`;
  if ("volume" in info || "muted" in info) playerSound(info.volume, info.muted);
  const playing = [1, 3].includes(info.playerState) ? true : [0, 2].includes(info.playerState) ? false : null;
  const id = typeof info.videoData?.video_id === "string" && /^[\w-]{11}$/.test(info.videoData.video_id) ? info.videoData.video_id : null;
  if ("currentTime" in info || playing !== null || id || info.videoData) playedTo(info.currentTime, playing, id);
  renderCatchUp();
}

const TWITCH_PROXY = "twitch-embed-player-proxy";
const TWITCH_SET = { muted: 10, volume: 11 };
const twitchSay = (frame, eventName, params) => frame?.contentWindow?.postMessage({ eventName, params, namespace: TWITCH_PROXY }, "https://player.twitch.tv");
function twitchTold(data) {
  if (data?.namespace === "twitch-embed" && ["video.ready", "ready"].includes(data.eventName)) return playerReady();
  const state = data?.namespace === TWITCH_PROXY && data.eventName === "UPDATE_STATE" ? data.params : null;
  if (!state || typeof state !== "object") return;
  playerSound(Number.isFinite(state.volume) ? state.volume * 100 : null, state.muted);
  const idle = state.playback === "Idle" && video.started;
  const playing = ["Playing", "Buffering"].includes(state.playback) ? true : idle || ["Paused", "Ended"].includes(state.playback) ? false : null;
  playedTo(state.currentTime, playing, null);
}

function renderCatchUp() {
  const s = video.showing, yt = s?.site === "YouTube", live = yt ? !!video.player?.live : !!s?.live;
  const key = $("video-catch");
  key.hidden = !(yt || live);
  key.title = live ? "Catch up to where the stream is now" : "Skip to the end";
}
function catchUp() {
  const s = video.showing;
  if (!s) return;
  if (s.site !== "YouTube") return showVideo(s, true);
  const p = video.player || {}, to = p.live ? p.end ?? p.duration : p.duration;
  if (!to) return;
  const frame = playerFrame();
  youTubeSay(frame, { event: "command", func: "seekTo", args: [to, true] });
  if (p.live) youTubeSay(frame, { event: "command", func: "playVideo", args: [] });
}

const VOLUME_SETTLE = 1500;
const KICK_WIDE = 800;
const VIDEO_PLAYERS = {
  YouTube: { told: true },
  Twitch: { told: true },
  clip: { told: false, own: "clip" },
  Kick: { told: false, own: "kick", bar: true },
};
const videoPlayer = (source) => (source ? VIDEO_PLAYERS[source.clip ? "clip" : source.site] : VIDEO_PLAYERS.YouTube);
const SOUND_WORDS = wordsOf("page.video.sound");
function renderSound() {
  const player = videoPlayer(video.showing), key = $("video-mute"), slider = $("video-volume");
  key.setAttribute("data-level", video.muted ? "muted" : video.volume === 0 ? "none" : video.volume < 50 ? "low" : "high");
  key.setAttribute("aria-pressed", String(video.muted));
  key.disabled = slider.disabled = !player.told;
  key.title = player.told ? SOUND_WORDS[video.muted ? "unmute" : "mute"] : SOUND_WORDS[`${player.own}.key`];
  slider.value = String(video.volume);
  slider.style.setProperty("--level", `${video.muted ? 0 : video.volume}%`);
  slider.title = player.told ? fillWords(SOUND_WORDS[video.muted ? "volume-muted" : "volume"], { volume: video.volume })
    : SOUND_WORDS[`${player.own}.slider`];
  slider.hidden = !!player.bar;
  $("video-kick-volume").hidden = !player.bar;
  if (!video.muted) video.held = false;
  $("video-held").hidden = !video.held;
}
function toggleMute() {
  video.muted = !video.muted;
  soundSet();
}
function volumeMoved(e) {
  video.volume = Math.max(0, Math.min(100, Math.round(Number(e.target.value)) || 0));
  if (video.volume > 0) video.muted = false;
  soundSet();
}
function soundSet() {
  saveVideo();
  renderSound();
  if (video.heard && videoPlayer(video.showing).told) tellSound();
}
function tellSound() {
  const frame = playerFrame(), tellMuted = !(video.volume === 0 && !video.muted && video.sound?.muted === false);
  video.askedAt = Date.now();
  clearTimeout(video.soundTimer);
  if (video.showing.site === "YouTube") {
    youTubeSay(frame, { event: "command", func: "setVolume", args: [video.volume] });
    if (tellMuted) youTubeSay(frame, { event: "command", func: video.muted ? "mute" : "unMute", args: [] });
  } else {
    twitchSay(frame, TWITCH_SET.volume, video.volume / 100);
    if (tellMuted) twitchSay(frame, TWITCH_SET.muted, video.muted);
  }
}
function playerReady() {
  if (video.heard) return;
  video.heard = true;
  tellSound();
}
function playerSound(volume, muted) {
  video.sound = { volume, muted };
  if (!video.heard) return;
  clearTimeout(video.soundTimer);
  const wait = video.askedAt + VOLUME_SETTLE - Date.now();
  if (wait > 0) video.soundTimer = setTimeout(followPlayer, wait);
  else followPlayer();
}
function followPlayer() {
  const { volume, muted } = video.sound, was = `${video.volume} ${video.muted}`;
  if (typeof muted === "boolean") video.muted = muted;
  if (muted === false && Number.isFinite(volume)) video.volume = Math.max(0, Math.min(100, Math.round(volume)));
  if (`${video.volume} ${video.muted}` === was) return;
  saveVideo();
  renderSound();
}
function fitPlayer() {
  const screen = $("video-screen"), frame = screen.querySelector("iframe.vd-wide"), W = screen.clientWidth, H = screen.clientHeight;
  if (!frame || !(W > 0 && H > 0)) return;
  const k = Math.min(1, W / KICK_WIDE);
  Object.assign(frame.style, { width: `${Math.max(W, KICK_WIDE)}px`, height: `${H / k}px`, transform: k < 1 ? `scale(${k})` : "" });
}

function keepVideo() {
  const source = video.link ? videoSource(video.link, location.hostname) : null;
  if (!source || source.error || video.saved.some((s) => s.link === video.link)) return;
  if (source.site === "YouTube" && source.id && video.player?.live) return keepChannel(source, true);
  if (source.site === "YouTube" && source.id) return askKeep(true);
  keepAsIs(source);
}
function keepAsIs(source = videoSource(video.link, location.hostname)) {
  askKeep(false);
  const told = source.site === "YouTube" && (source.channel ? video.player?.author : video.player?.title);
  keepLink(video.link, told || source.name, source.site);
}
function keepChannel(source = videoSource(video.link, location.hostname), live = false) {
  askKeep(false);
  const was = video.link;
  findChannel(source.id, (c) => {
    if (live && video.link === was) video.link = youTubeLive(c.channel);
    keepLink(youTubeLive(c.channel), c.name, "YouTube");
  });
}
function askKeep(open) {
  $("video-ask").hidden = !open;
  if (!open) return;
  const author = video.player?.author;
  $("video-keep-live").textContent = author ? `${author} live` : "The channel live";
  $("video-keep-live").title = `This keeps the live stream of ${author || "the channel"}. Picking the stream plays whatever the channel streams then`;
}
function keepLink(link, name, site) {
  if (!video.saved.some((s) => s.link === link)) video.saved.unshift({ link, name, site });
  video.seen[link] = true;
  video.saved.splice(VIDEO_SAVED_MAX);
  saveVideo();
  renderSaved();
}
const videoAskFailed = (err) => (err?.status === 502 ? "unread" : "unreached");
function findChannel(ask, then) {
  const asked = getJson(`/api/youtube/channel?${ask.startsWith("@") ? "handle" : "video"}=${encodeURIComponent(ask)}`);
  if (!asked) return videoError(word("page.video.orb.unreached"));
  asked.then(then, (err) => videoError(err?.status === 404 ? word("page.video.orb.no-channel")
    : videoAskFailed(err) === "unread" ? word("page.video.orb.unread") : word("page.video.orb.unreached")));
}
function renderSaved() {
  const kept = video.saved.some((s) => s.link === video.link), any = video.saved.length > 0;
  $("video-save").hidden = !video.link || kept;
  $("video-saved-key").hidden = !any;
  if (!any) showSaved(false);
  const streams = video.saved.map(savedStream), dots = streams.some(Boolean);
  $("video-saved").innerHTML = video.saved.map((s, i) => `<div class="vd-row${s.link === video.link ? " on" : ""}">${favStar(s, i, streams[i])}
    <button class="vd-pick" data-vd-pick="${i}" title="${esc(s.link)}">${dots ? liveDot(s, streams[i]) : ""}${esc(s.name)}<small>${esc(s.site)}</small></button>
    <button class="vd-drop x-mark" data-vd-drop="${i}" title="Take ${esc(s.name)} off the list" aria-label="Take ${esc(s.name)} off the list">&times;</button></div>`).join("");
  const news = video.saved.filter((s) => wentLive(s.link)).map((s) => s.name), key = $("video-saved-key");
  key.setAttribute("data-went-live", String(news.length > 0));
  key.title = news.length ? `${andList(news)} went live. Open the list to see` : "The saved videos and streams";
}
function showSaved(open = $("video-saved").hidden) {
  const was = !$("video-saved").hidden;
  $("video-saved").hidden = !open;
  $("video-saved-key").setAttribute("aria-expanded", String(open));
  if (open) checkLive();
  else if (was) seeLive();
}

const LIVE_EVERY = 5 * 60 * 1000;
function savedStream(s) {
  const source = videoSource(s.link, location.hostname);
  return source.live && source.channel ? { site: source.site, channel: source.channel } : null;
}
const wentLive = (link) => video.live[link] === true && !video.seen[link];
const liveWords = (state, site, fresh) => (state === true ? (fresh ? word("page.video.live.new") : word("page.video.live.on"))
  : state === false ? word("page.video.live.off") : state === "unread" ? word("page.video.live.unread", { site })
    : state === "unreached" ? word("page.video.live.unreached", { site }) : word("page.video.live.asking"));
function liveDot(s, stream) {
  if (!stream) return `<span class="vd-live none"></span>`;
  const state = video.live[s.link], fresh = wentLive(s.link);
  return `<span class="vd-live${state === true ? " on" : ""}${fresh ? " new" : ""}" title="${esc(liveWords(state, stream.site, fresh))}"></span>`;
}
function checkLive() {
  video.checkedAt = Date.now();
  for (const s of video.saved) {
    const stream = savedStream(s);
    const asked = stream && getJson(`/api/video/live?site=${stream.site}&channel=${encodeURIComponent(stream.channel)}`, { share: true });
    asked?.then((a) => {
      video.live[s.link] = a.live === true;
      if (!video.live[s.link] && (video.seen[s.link] || video.told[s.link])) {
        delete video.seen[s.link];
        delete video.told[s.link];
        saveVideo();
      }
      renderSaved();
      sayOnline();
    }, (err) => { video.live[s.link] = videoAskFailed(err); renderSaved(); });
  }
}
function seeLive() {
  const news = video.saved.filter((s) => wentLive(s.link));
  if (!news.length) return;
  news.forEach((s) => { video.seen[s.link] = true; });
  saveVideo();
  renderSaved();
}

const VIDEO_STAR = `<svg viewBox="0 0 16 16" aria-hidden="true"><path d="M8 1.31L9.87 6.13L15.04 6.42L11.03 9.69L12.35 14.69L8 11.89L3.65 14.69L4.97 9.69L.96 6.42L6.13 6.13Z"/></svg>`;
function favStar(s, i, stream) {
  const words = s.fav ? "This is a favorite. Click to take its star off" : `Make this a favorite${stream ? ". The window flashes and says so when the stream goes live" : ""}`;
  return `<button class="vd-fav" data-vd-fav="${i}" aria-pressed="${s.fav === true}" title="${esc(words)}" aria-label="Favorite: ${esc(s.name)}">${VIDEO_STAR}</button>`;
}
function starSaved(i) {
  const s = video.saved[i];
  if (!s) return;
  if (s.fav) delete s.fav;
  else s.fav = true;
  saveVideo();
  renderSaved();
}

const VIDEO_ONLINE_MS = 8000;
function sayOnline() {
  if (!video.open || document.hidden) return;
  const fresh = video.saved.filter((s) => s.fav && wentLive(s.link) && !video.told[s.link]);
  if (!fresh.length) return;
  fresh.forEach((s) => { video.told[s.link] = true; });
  saveVideo();
  video.saying.push(...fresh.map((s) => s.name));
  const names = video.saying, el = $("video-online");
  $("video-online-words").innerHTML = `${andList(names.map((n) => `<b>${esc(n)}</b>`))} ${names.length > 1 ? "are" : "is"} online`;
  el.hidden = true;
  void el.offsetWidth;
  el.hidden = false;
  clearTimeout(video.sayTimer);
  video.sayTimer = setTimeout(stopSaying, VIDEO_ONLINE_MS);
}
function stopSaying() {
  clearTimeout(video.sayTimer);
  video.saying = [];
  $("video-online").hidden = true;
}

function savedClicked(e) {
  const pick = e.target.closest("[data-vd-pick]"), drop = e.target.closest("[data-vd-drop]"), star = e.target.closest("[data-vd-fav]");
  if (pick) {
    showSaved(false);
    return watchVideo(video.saved[+pick.dataset.vdPick]?.link);
  }
  if (star) return starSaved(+star.dataset.vdFav);
  if (!drop) return;
  video.saved.splice(+drop.dataset.vdDrop, 1);
  saveVideo();
  renderSaved();
}

function showVideoLink(open = $("video-link").hidden) {
  $("video-link").hidden = !open;
  $("video-link-key").setAttribute("aria-pressed", String(open));
  if (!open) return videoError("");
  $("video-url").focus();
  $("video-url").select();
}
function videoError(words) {
  $("video-error").textContent = words;
  $("video-error").hidden = !words;
}

function watchVideo(text) {
  const link = String(text ?? "").trim();
  if (!link) return $("video-url").focus();
  const source = videoSource(link, location.hostname);
  if (source.error) return videoError(source.error);
  if (source.handle) return findChannel(source.handle, (c) => watchVideo(youTubeLive(c.channel)));
  video.link = link;
  saveVideo();
  showVideo(source, video.autoplay);
  showVideoLink(false);
}

function videoDrag(e, move) {
  if (e.button !== 0 || e.target.closest("button, input, .vd-saved")) return;
  const el = e.currentTarget, from = { x: e.clientX, y: e.clientY, left: video.x, top: video.y, w: video.w, h: video.h };
  e.preventDefault();
  el.setPointerCapture(e.pointerId);
  $("video").classList.add("moving");
  const moved = (m) => { move(from, m.clientX - from.x, m.clientY - from.y); placeVideo(); };
  const done = () => {
    el.removeEventListener("pointermove", moved);
    el.removeEventListener("pointerup", done);
    el.removeEventListener("pointercancel", done);
    $("video").classList.remove("moving");
    saveVideo();
    lookAgain();
  };
  el.addEventListener("pointermove", moved);
  el.addEventListener("pointerup", done);
  el.addEventListener("pointercancel", done);
}
const videoMove = (from, dx, dy) => { video.x = from.left + dx; video.y = from.top + dy; };
const videoSize = (from, dx, dy) => {
  const { W, H } = videoRoom();
  video.w = Math.min(from.w + dx, W - video.x);
  video.h = Math.min(from.h + dy, H - video.y);
};

function videoClicked(e) {
  const b = e.target.closest("button[data-vd]");
  if (b?.dataset.vd === "close") closeVideo();
  else if (b?.dataset.vd === "link") showVideoLink();
  else if (b?.dataset.vd === "save") keepVideo();
  else if (b?.dataset.vd === "keep-video") keepAsIs();
  else if (b?.dataset.vd === "keep-live") keepChannel();
  else if (b?.dataset.vd === "saved") showSaved();
  else if (b?.dataset.vd === "catch") catchUp();
  else if (b?.dataset.vd === "mute") toggleMute();
  else if (b?.dataset.vd === "sound-on") soundBack();
}
function autoplayTicked(e) {
  video.autoplay = !!e.target.checked;
  saveVideo();
}

loadVideo();
$("video-url").value = video.link;
$("video-autoplay").checked = video.autoplay;
renderSaved();
renderCatchUp();
renderSound();
$("video-autoplay").addEventListener("change", autoplayTicked);
$("video-volume").addEventListener("input", volumeMoved);
new ResizeObserver(fitPlayer).observe($("video-screen"));
addEventListener("message", playerMessage);
$("btn-video").addEventListener("click", () => toggleVideo());
$("video").addEventListener("click", videoClicked);
$("video-saved").addEventListener("click", savedClicked);
document.addEventListener("click", (e) => { if (!e.target.closest?.("#video-saved, #video-saved-key")) showSaved(false); });
$("video-link").addEventListener("submit", (e) => { e.preventDefault(); watchVideo($("video-url").value); });
$("video-bar").addEventListener("pointerdown", (e) => videoDrag(e, videoMove));
$("video-grip").addEventListener("pointerdown", (e) => videoDrag(e, videoSize));
addEventListener("resize", () => { if (video.open) placeVideo(); });
addEventListener("pagehide", saveVideo);
function soundBackAt(e) {
  if (!video.held || e.type === "wheel" || e.target?.closest?.("#video-mute:enabled, #video-volume:enabled, [data-vd='sound-on']")) return;
  soundBack();
}
function soundBack() {
  video.held = video.muted = false;
  soundSet();
  if (!videoPlayer(video.showing).told) showVideo(video.showing, true);
}
on("acted", soundBackAt);
setInterval(() => { if (video.open && !document.hidden && Date.now() - video.checkedAt >= LIVE_EVERY) checkLive(); }, 30000);
document.addEventListener("visibilitychange", () => { if (!document.hidden) sayOnline(); });
hotkey(["v"], (e) => { e.preventDefault(); toggleVideo(); });
closable(LAYER.video, () => !$("video-saved").hidden, () => showSaved(false));
closable(LAYER.video, () => !$("video-ask").hidden, () => askKeep(false));
closable(LAYER.video, () => !$("video-link").hidden, () => showVideoLink(false));
restoreVideo();
