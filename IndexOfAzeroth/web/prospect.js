// The Index of Azeroth. Copyright 2026 Index Case <indexofazeroth@pm.me>. PolyForm Strict 1.0.0, see LICENSE.md.
"use strict";

const PROSPECT_PICTURES = ["img/prospecting1.jpeg", "img/prospecting2.jpg"];
const PICTURE_EVERY = 5000, PICTURE_FADE = 600;
let prospectPictures = PROSPECT_PICTURES;
on("start", () => getJson("/api/prospectpictures")?.then((l) => { if (l?.length) prospectPictures = l; }, () => {}));
const pickPicture = (not) => {
  const pool = prospectPictures.filter((p) => p !== not);
  return (pool.length ? pool : prospectPictures)[Math.floor(Math.random() * (pool.length || prospectPictures.length))];
};

const PROSPECT_LINES = [
  "You are about to prospect {n} zones. A dwarf miner heard the number and sat down for a while. If you didn't mean it, pick a zone and try again.",
  "{n} zones of rock and root is a lot to sift. Brann Bronzebeard has packed a lunch for the trip. Zoom in on one zone to keep it short.",
  "You want to prospect {n} zones at once. The Explorers' League has written 'ambitious' in the margin. Pick one zone for a quicker look.",
  "{n} zones will take a while. A Tauren prospector said the earth is patient and then lay down. Zoom to a single zone if you'd rather not wait.",
  "A gnome built a surveying machine for {n} zones. The gnome is still looking for the pieces. Pick one zone and try again for a faster search.",
  "{n} zones is a lot to walk and weigh. A kobold looked at the list and said you no take candle, you take time. Zoom in on one zone to hurry it.",
  "Surveying {n} zones is a long dig. Magni Bronzebeard heard about the dig and ordered an ale for halfway. Pick a zone to search just there.",
  "The Venture Company would send a shredder crew for {n} zones. You have one prospector and a pick. Zoom to a zone for speed.",
  "{n} zones of veins and blooms is a lot to weigh. A dwarf waiting for the boat at Menethil says the boat will come sooner. Pick a zone to go quicker.",
  "Prospecting across {n} zones will take a while. An innkeeper in Goldshire has offered you a room for the wait. Zoom in on one zone if you meant just that.",
];
const PROSPECT_NO = ["Nay", "Belay that", "Stay my pick", "Not today", "Hold, friend", "Another time", "Back to camp", "Leave it be"];
const PROSPECT_GO = ["Onward", "Dig deep", "Strike the earth", "To the veins", "Swing the pick", "Lead the way", "Let it be done", "For the ore"];
const SEARCH_WORDS = {
  gather: {
    title: { world: "Prospect the whole world?", continent: "Prospect all of {c}?", zones: "Prospect {n} zones?" },
    world: [
      "This is the whole world, every vein and bloom from Stormwind to Orgrimmar. Brann Bronzebeard asked for a month and a mule. Zoom in to a continent to keep it sane.",
      "You want to prospect all of Azeroth at once. The Explorers' League has asked for that in writing. Zoom in to a continent, or better, to the zones you want.",
      "Every zone in the world is a lot to sift. A dwarf miner looked at the list and went to buy a second pick. Zoom in to a continent to narrow it.",
      "All of Azeroth is a lot of rock. The earthen surveyed all of Azeroth once, and that took them an age. Zoom in to a continent first, then to the zones you mean.",
      "A world of ore and herbs is a lot to weigh. A goblin has already opened a tab for your supplies. Zoom in to a continent and then the zones you want.",
      "A magus of the Kirin Tor looked at the whole world on one map and asked for a chair. Zoom in to a continent, then to the zones you want.",
    ],
    continent: [
      "All {n} zones of {c} is a long walk. A Tauren said so, and a Tauren walks everywhere. Zoom in until the zone names show over the zones you want.",
      "Sifting the whole of {c} will take a while. A gnome offered to help and has already lost his sieve. Zoom in till the zone names show, with only the ones you care about in view.",
      "{c} from end to end is {n} zones of veins and blooms. A goblin offered to count them for a copper apiece. Zoom in on the zones you want, or all the way into one.",
      "The Explorers' League digs {c} one site at a time and has been at it for years. Zoom in till the names show over the zones you want.",
      "Every corner of {c} is a lot to prospect. The blacksmith is already measuring your mount for new shoes. Zoom in so only the zones you want are named.",
      "{n} zones across {c} is a big dig for one prospector. The Venture Company would send fifty and a shredder. Zoom in on the zones you want to make it quicker.",
    ],
    zones: PROSPECT_LINES, no: PROSPECT_NO, go: PROSPECT_GO,
  },
  hunt: {
    title: { world: "Hunt the whole world?", continent: "Hunt all of {c}?", zones: "Hunt {n} zones?" },
    world: [
      "Every camp in the world would be weighed up at once. A Stormwind guard tried to pin every bounty in the world on one board, and the board fell over. Zoom in to a continent to narrow the hunt.",
      "You want to scout all of Azeroth for a camp. SI:7 sent back a note asking which continent you meant. Zoom in to one first.",
      "The whole world's camps is a lot to test your blade on. An orc blademaster says to sharpen your axe for a week first. Zoom in to a continent and then the zones you want.",
      "Every bounty in the world at once is a long read. The clerk at the bounty board has gone for a lie down. Zoom in to a continent, then to the zones you'd hunt.",
      "A world of camps and bounties is a big survey. The goblins have quoted you for the survey alone. Zoom in to a continent to keep it short.",
      "Hunting the whole world is a long hunt. Hemet Nesingwary hunted the whole world once and still tells the story. Zoom in to a continent, or right down to the zones you want.",
    ],
    continent: [
      "All {n} zones of {c} would have every camp sized up. A troll hunter has started on the first one. Zoom in till the zone names show over the zones you'd hunt.",
      "Scouting {c} from end to end takes a while. An orc grunt has sharpened his axe twice already. Zoom in on the zones you want.",
      "{c} has {n} zones of bounties. A night elf huntress is asking which ones you meant. Zoom in till the names show over the zones you want.",
      "Every camp in {c} is a lot to size up. A Defias thug asked why you don't just rob the nearest caravan. Zoom in on the zones you want.",
      "A bounty board for all of {c} is a long read. The guard who pins up the posters has run out of pins. Zoom in so only the zones you'd hunt are named.",
      "Weighing {n} zones of {c} takes a while. A dwarf hunter has gone for an ale to pass the time. Zoom in on the zones you want to hurry it.",
    ],
    zones: [
      "{n} zones of camps is a lot to weigh. An orc is oiling his axe while he waits. Zoom in on one zone for a quicker look.",
      "Scouting {n} zones for the best bounty takes a while. The guard at the Stormwind bounty board says his list is shorter. Zoom in on one zone to keep it quick.",
      "{n} hunting grounds is a lot to size up. A goblin has offered to size them up and charge by the zone. Zoom in on one zone for a faster look.",
      "Every camp in {n} zones will be sized up for you. A troll hunter says this may take a moment and has sat down. Zoom in on one zone if you meant just that.",
      "Collecting bounties across {n} zones is a long hunt. A dwarf rifleman suggests one zone at a time. Zoom in on one zone and try again.",
      "{n} zones of mobs is a lot to weigh up. A Tauren hunter is counting them on his fingers and has run out. Zoom in on one zone to look just there.",
    ],
    no: ["Sheathe it", "Not today", "Stay my blade", "Hold, friend", "Back to camp", "Another time", "Leave it be"],
    go: ["Blades out", "To the hunt", "Collect the bounty", "Sharpen up", "Lead the way", "Let it be done", "For glory"],
  },
};
const pickWord = (list) => list[Math.floor(Math.random() * list.length)];

function askSearch(kind, area, go) {
  const words = SEARCH_WORDS[kind], n = area.zones.length;
  const fill = (t) => t.replaceAll("{n}", n).replaceAll("{c}", area.name || "the continent");
  const shown = area.zones.slice(0, 6).map(mapName);
  const which = area.scope === "world" ? `All ${n} zones in the world` : area.scope === "continent" ? `All ${n} zones of ${area.name}`
    : `In view: ${n > shown.length ? `${shown.join(", ")} and ${n - shown.length} more` : andList(shown)}`;
  ask({ title: fill(words.title[area.scope]), text: fill(pickWord(words[area.scope])), more: which, yes: pickWord(words.go),
        no: pickWord(words.no), onYes: go });
}
const PROSPECT_POLL = 400;
const PROSPECT_FADE = 2500;
const PROSPECT_CLIENT = Math.random().toString(36).slice(2, 10);
app.prospect = null;

function startProspecting(query, meta) {
  stopProspecting(true);
  stopScout(true);
  const p = app.prospect = { ...meta, tested: [], best: null, doneAt: null, timer: null, query, meta };
  glassStart();
  renderTracks();
  getJson(`/api/gathersearch?${query}&client=${PROSPECT_CLIENT}`, { key: null }).then((r) => {
    if (app.prospect !== p) return;
    p.id = r.id;
    pollProspecting(p);
  }, (e) => {
    if (app.prospect === p) stopProspecting(true);
    loopFailed(e);
  });
}

const PROSPECT_ASK = "prospect poll";
function pollProspecting(p) {
  const asked = getJson(`/api/gathersearch?id=${p.id}&since=${p.tested.length}`, { key: PROSPECT_ASK });
  if (!asked) {
    p.timer = setTimeout(() => pollProspecting(p), Math.max(PROSPECT_POLL, askWait(PROSPECT_ASK)));
    return;
  }
  asked.then((s) => {
    if (app.prospect !== p) return;
    const now = performance.now();
    for (const r of s.tested) {
      r.at = now;
      r.inst = app.maps[r.map]?.instance ?? p.inst;
      p.tested.push(r);
    }
    p.best = s.best;
    if (s.state === "running") {
      renderTracks();
      p.timer = setTimeout(() => pollProspecting(p), PROSPECT_POLL);
      return;
    }
    p.doneAt = now;
    const c = s.loop;
    if (!c?.stops?.length) {
      stopProspecting(true);
      return showToast((s.state === "failed" ? `The Index couldn't work out the loop (${s.error || "an unknown error"})` : "This map has nothing to gather for that resource")
        + (p.was && app.tracks.loop === p.was ? `, so ${p.was.name} runs on as it was` : ""));
    }
    const cut = c.whole === false ? " before the search ran out of time" : "";
    const tried = p.tested.length > 1 ? `, the best of ${p.tested.length} routes tried${cut}` : cut ? `, the one route tried${cut}` : "";
    const risk = p.daredevil ? ", Daredevil on, so the loop takes every spawn point and goes straight through, avoiding no mob"
      : c.unsafe ? `, ${num(c.unsafe)} spawn points left out where a mob would attack you` : "";
    const name = `Gather ${c.name}${p.many && c.map ? ` in ${mapName(c.map)}` : ""}`;
    const sub = `${num(c.nodes)} spawn points passed, about ${upText(c.up)} up a lap, ${c.stops.length} stops${tried}` + lapText(c) + risk;
    if (p.was && app.tracks.loop !== p.was) return endProspect(p);
    seedWays(p, c.ways ? { inst: app.maps[c.map]?.instance ?? p.inst, stops: c.stops, ways: c.ways }
      : p.tested.find((r) => sameLoop({ what: "gather", name, stops: r.stops }, "gather", name, c.stops)));
    if (p.was && sameLoop(p.was, "gather", name, c.stops)) keepLoop(p.was, sub);
    else {
      startLoopTrack("gather", name, sub, c.stops, app.maps[c.map]?.instance ?? p.inst,
                     { layer: p.layer, types: p.types, glass: glassLand(), zone: c.map || p.map, daredevil: p.daredevil,
                       zones: p.searched, all: p.all }, !!p.was);
    }
    endProspect(p);
  }, (e) => {
    if (app.prospect !== p) return;
    if (e?.status === 404) {
      showToast("The Index restarted during the search and is prospecting again");
      p.done = null;
      return startProspecting(p.query, p.meta);
    }
    p.timer = setTimeout(() => pollProspecting(p), askWait(PROSPECT_ASK));
  });
}

function seedWays(p, r) {
  const n = r?.stops.length;
  r?.stops.forEach((a, i) => {
    const b = r.stops[(i + 1) % n], way = r.ways?.[i];
    const whole = Array.isArray(way) ? { points: way, partial: false } : way;
    const key = wayKey(r.inst, a, b, p.mode);
    if (whole?.points?.length > 1 && !app.ways.get(key)) app.ways.set(key, whole);
  });
}

function stopProspecting(quiet) {
  const p = app.prospect;
  if (!p) return;
  clearTimeout(p.timer);
  if (p.id && !p.doneAt) getJson(`/api/gathersearch?id=${p.id}&stop=1`, { key: null }).catch(() => {});
  app.prospect = null;
  glassStop();
  renderTracks();
  if (!quiet) showToast("Prospecting stopped");
  endProspect(p);
}
function endProspect(p) {
  const done = p.done;
  p.done = null;
  renderTracks();
  done?.();
}

function prospectHtml() {
  const p = app.prospect, best = p.best != null ? p.tested[p.best] : null;
  const head = panelHead("Prospecting", "loop", `<button data-prospect-stop title="Stop looking">Stop</button>`, { track: true });
  const trying = p.tested.length ? `Walking route ${p.tested.length + 1}` : "Looking for where the nodes lie thickest";
  const so = best ? `Best so far: ${num(best.passed)} spawn points passed, about ${upText(best.nodes)} up a lap, a lap about ${Math.round(best.lap / 60)} min`
    : "Each route the search tries shows on the map";
  return html`${raw(head)}<div class="guide-name">${p.name}</div><div class="guide-line">${trying}</div><div class="guide-line">${so}</div>`;
}
const prospecting = () => !!app.prospect && !app.prospect.doneAt;

document.querySelector(".sidestack")?.addEventListener("click", (e) => {
  if (e.target.closest("button[data-prospect-stop]")) stopProspecting();
});

const LOOP_ZONE_GLOW = 0.4;
function loopZone(t) {
  if (t.zone) return t.zone;
  const ns = t.stops.map((p) => p[0]), ws = t.stops.map((p) => p[1]);
  return zoneNamed({ inst: t.inst, n: (Math.min(...ns) + Math.max(...ns)) / 2, w: (Math.min(...ws) + Math.max(...ws)) / 2 });
}
function drawLoopZone(size, scale) {
  const t = app.tracks?.loop;
  if (!t?.stops?.length || t.what !== "gather" || app.maps[app.displayMap]?.type !== 2 || !zoomedOut()) return;
  const id = loopZone(t), z = id && continentZones(app.displayMap, size).find((q) => q.id === id);
  const color = trackStyle("loop", t).color, shape = z && zoneShape(id, hex(color));
  if (!shape) return;
  const label = `Gathering loop: ${app.maps[id]?.name || "the loop's zone"}`;
  noteOverlay(label, color);
  drawLit(label, color, () => inMapSpace(size, scale, () => {
    paintGlow((g) => g.drawImage(shape, z.x0 * size.w, z.y0 * size.h, z.w * size.w, z.h * size.h), { alpha: ctx.globalAlpha * LOOP_ZONE_GLOW });
  }));
}

const PROSPECT_IN = 600;
function drawProspects(s, size, scale) {
  const p = app.prospect;
  if (!p?.tested.length) return;
  const now = performance.now(), fade = p.doneAt ? 1 - (now - p.doneAt) / PROSPECT_FADE : 1;
  if (fade <= 0) return;
  const color = tint(LOOP_LOOKS[loopLook({ what: "gather", layer: p.layer })]);
  p.tested.forEach((r, k) => {
    const screen = screenIn(r.inst, size, scale);
    const pts = [];
    r.stops.forEach((a, i) => { pts.push(a); for (const q of (r.ways?.[i] || []).slice(1, -1)) pts.push(q); });
    pts.push(r.stops[0]);
    const line = pts.map(screen).filter(Boolean);
    if (line.length < 2) return;
    const best = k === p.best;
    ctx.save();
    ctx.globalAlpha = fade * Math.min(1, (now - r.at) / PROSPECT_IN) * (best ? 0.95 : 0.45);
    ctx.setLineDash(best ? [0.01, 8] : [5, 7]);
    ctx.lineCap = "round";
    ctx.lineWidth = best ? 5.5 : 3; ctx.strokeStyle = tint("black", 0.55); strokePath(line);
    ctx.lineWidth = best ? 3 : 1.5; ctx.strokeStyle = color; strokePath(line);
    ctx.restore();
  });
}
function fadeProspects(now) {
  const p = app.prospect;
  if (!p?.tested.length) return false;
  if (p.doneAt && now - p.doneAt >= PROSPECT_FADE) { app.prospect = null; return false; }
  return !!p.doneAt || p.tested.some((r) => now - r.at < PROSPECT_IN);
}
on("animate", fadeProspects);


const GLASS_MS = { land: 900, zoom: 900, focus: 1000, open: 1000 };
const GLASS_EDGE = 4;
const glass = { img: null, src: "", phase: "off", t0: 0, raf: 0, last: null, land: null, view: null,
  next: null, prev: null, shownAt: 0, fadeAt: 0 };
const reducedMotion = () => window.matchMedia?.("(prefers-reduced-motion: reduce)").matches;
const glassCanvas = () => $("track-loop")?.querySelector(":scope > .prospect-glass");

function glassLoad(src, then) {
  if (glass.src === src && glass.img?.complete) return then();
  const img = new Image();
  img.onload = () => { glass.img = img; glass.src = src; then(); };
  img.src = src;
}

function glassStart() {
  glass.view = null;
  glass.land = null;
  glass.next = glass.prev = null;
  glassLoad(pickPicture(), () => {
    glass.phase = "search";
    glass.t0 = glass.shownAt = performance.now();
    glassAhead();
    glassRun();
  });
}

function glassAhead() {
  const src = pickPicture(glass.src), img = new Image();
  img.onload = () => { if (glass.phase === "search") glass.next = { img, src }; };
  img.src = src;
}

function glassLand() {
  if (!glass.img) return null;
  glass.next = glass.prev = null;
  glass.land = { tx: 0.15 + Math.random() * 0.7, ty: 0.55 + Math.random() * 0.22 };
  glass.view = { src: glass.src, ...glass.land };
  glass.phase = reducedMotion() ? "shown" : "land";
  glass.t0 = performance.now();
  glassRun();
  return glass.view;
}

function glassEnsure(view) {
  if (!view?.src || (glass.view?.src === view.src && glass.phase !== "off")) return;
  glass.view = view;
  glass.land = { tx: view.tx, ty: view.ty };
  glassLoad(view.src, () => { glass.phase = "shown"; glassRun(); });
}

function glassStop() {
  dropFrame(glass.raf);
  glass.phase = "off";
  glass.view = null;
  const c = glassCanvas();
  if (c) c.hidden = true;
}

function glassRun() {
  dropFrame(glass.raf);
  const tick = (now) => { if (glassDraw(now)) glass.raf = askFrame(tick); };
  glass.raf = askFrame(tick);
}

const glassEase = (u) => (u <= 0 ? 0 : u >= 1 ? 1 : u * u * (3 - 2 * u));
const glassLerp = (a, b, u) => a + (b - a) * u;

function glassDraw(now) {
  const c = glassCanvas(), img = glass.img;
  if (glass.phase === "off" || !img) return false;
  if (!c) return true;
  c.hidden = false;
  const dpr = window.devicePixelRatio || 1, W = c.clientWidth, H = c.clientHeight;
  if (!W || !H) return true;
  if (c.width !== Math.round(W * dpr) || c.height !== Math.round(H * dpr)) { c.width = Math.round(W * dpr); c.height = Math.round(H * dpr); }
  const g = c.getContext("2d");
  g.setTransform(dpr, 0, 0, dpr, 0, 0);
  g.clearRect(0, 0, W, H);
  const iw = img.naturalWidth, ih = img.naturalHeight, s0 = Math.max(W / iw, H / ih);
  const ox = (W - iw * s0) / 2, oy = (H - ih * s0) / 2, r0 = H * 0.3, big = Math.hypot(W, H);
  let lx, ly, px, py, r = r0, mag = 1.6, blur = 0, veil = 0, more = true;
  let fading = null;
  if (glass.phase === "search") {
    const t = (now - glass.t0) / 1000;
    lx = W * (0.5 + 0.36 * Math.sin(t * 0.55) + 0.06 * Math.sin(t * 1.9));
    ly = H * (0.56 + 0.2 * Math.sin(t * 0.83 + 1.3));
    if (glass.next && now - glass.shownAt >= PICTURE_EVERY) {
      glass.prev = img;
      glass.img = glass.next.img; glass.src = glass.next.src; glass.next = null;
      glass.fadeAt = glass.shownAt = now;
      glassAhead();
      return true;
    }
    px = (lx - ox) / s0; py = (ly - oy) / s0;
    glass.last = { lx, ly, px, py };
    const u = (now - glass.fadeAt) / PICTURE_FADE;
    if (glass.prev && u < 1) {
      const q = glass.prev, qs = Math.max(W / q.naturalWidth, H / q.naturalHeight), qox = (W - q.naturalWidth * qs) / 2, qoy = (H - q.naturalHeight * qs) / 2;
      const qpx = (lx - qox) / qs, qpy = (ly - qoy) / qs, sc = qs * mag;
      fading = { img: q, x: lx - qpx * sc, y: ly - qpy * sc, w: q.naturalWidth * sc, h: q.naturalHeight * sc, alpha: 1 - u };
    } else glass.prev = null;
  } else {
    const L = glass.land, tpx = L.tx * iw, tpy = L.ty * ih;
    const cx = Math.min(W - r0, Math.max(r0, ox + tpx * s0)), cy = Math.min(H - r0, Math.max(r0, oy + tpy * s0));
    const from = glass.last || { lx: cx, ly: cy, px: tpx, py: tpy };
    let e = now - glass.t0;
    if (glass.phase === "land") {
      const u = glassEase(e / GLASS_MS.land);
      lx = glassLerp(from.lx, cx, u); ly = glassLerp(from.ly, cy, u); px = glassLerp(from.px, tpx, u); py = glassLerp(from.py, tpy, u);
      if (e >= GLASS_MS.land) { glass.phase = "zoom"; glass.t0 = now; }
    } else {
      px = tpx; py = tpy; lx = cx; ly = cy;
      if (glass.phase === "zoom") {
        mag = glassLerp(1.6, 2.6, glassEase(e / GLASS_MS.zoom));
        if (e >= GLASS_MS.zoom) { glass.phase = "focus"; glass.t0 = now; }
      } else if (glass.phase === "focus") {
        mag = 2.6;
        blur = 5 * Math.sin(Math.PI * Math.min(1, e / GLASS_MS.focus));
        if (e >= GLASS_MS.focus) { glass.phase = "open"; glass.t0 = now; }
      } else if (glass.phase === "open") {
        const u = glassEase(e / GLASS_MS.open);
        mag = 2.6; r = glassLerp(r0, big, u); veil = u;
        lx = glassLerp(cx, W / 2, u); ly = glassLerp(cy, H / 2, u);
        if (e >= GLASS_MS.open) { glass.phase = "shown"; glass.t0 = now; }
      } else {
        mag = 2.6; r = big; veil = 1; lx = W / 2; ly = H / 2; more = false;
      }
    }
  }
  const scale = s0 * mag;
  if (blur > 0.05) g.filter = `blur(${blur.toFixed(2)}px)`;
  if (fading) {
    g.globalAlpha = fading.alpha; g.drawImage(fading.img, fading.x, fading.y, fading.w, fading.h);
    g.globalAlpha = 1 - fading.alpha;
  }
  g.drawImage(img, lx - px * scale, ly - py * scale, iw * scale, ih * scale);
  g.globalAlpha = 1;
  g.filter = "none";
  const edge = g.createRadialGradient(lx, ly, 0, lx, ly, r);
  edge.addColorStop(Math.max(0, 1 - GLASS_EDGE / r), tint("black"));
  edge.addColorStop(1, tint("black", 0));
  g.globalCompositeOperation = "destination-in";
  g.fillStyle = edge;
  g.fillRect(0, 0, W, H);
  g.globalCompositeOperation = "source-over";
  if (veil > 0) {
    const v = g.createLinearGradient(0, 0, W, 0);
    v.addColorStop(0, tint("vignette", 0.82)); v.addColorStop(0.6, tint("vignette", 0.62)); v.addColorStop(1, tint("vignette", 0.38));
    g.globalAlpha = veil; g.fillStyle = v; g.fillRect(0, 0, W, H); g.globalAlpha = 1;
  }
  return more;
}
