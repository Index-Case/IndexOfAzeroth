// The Index of Azeroth. Copyright 2026 Index Case <indexofazeroth@pm.me>. PolyForm Strict 1.0.0, see LICENSE.md.
"use strict";

(() => {
  const wrap = document.getElementById("zone-wrap"), line = document.getElementById("expedition");
  if (!wrap || !line) return;
  const WORDS = ["Hemet Nesingwary is drawing the map between shots", "A dwarf surveyor is pacing out the hills",
    "A gnome cartographer is measuring the ridge with a ruler", "Nesingwary's porters are carrying the maps uphill",
    "A night elf scout is sketching the trees one at a time", "A goblin is measuring the land and charging by the yard",
    "A troll tracker is reading the ground for you", "A Tauren pathfinder is walking the land to learn its shape",
    "Hemet's apprentice is inking the coastline and his sleeve", "The Explorers' League stopped mapping to dig something up"];
  const SOURCES = [
    [/(github\.com|githubusercontent\.com)$/, "GitHub", ["A scribe is copying scrolls from GitHub's library",
      "A dwarf archivist at GitHub is fetching the scrolls", "A gnome is carrying the scrolls back from GitHub"]],
  ];
  const AHEAD = ["Nesingwary's scouts are riding on ahead of you", "A dwarf outrider is mapping the road past your next waypoint",
    "A night elf scout went ahead to look at the next leg", "Hemet's trackers are a little way ahead of you on the trail",
    "A goblin surveyor went ahead to measure the next leg. He will bill you later", "A troll scout is sniffing out the trail ahead of you"];
  const WAIT_NOTED = 1.5, SLOW = 20;
  let pool = WORDS;
  function linesFor(waiting) {
    const [host, secs] = Object.entries(waiting || {}).sort((a, b) => b[1] - a[1])[0] || [];
    if (!host || secs < WAIT_NOTED) return WORDS;
    const [, name, lines] = SOURCES.find(([re]) => re.test(host)) || [];
    if (!lines) return WORDS;
    return secs >= SLOW ? [`${name} is slow today. Hemet's porters are sitting on their packs`, ...lines] : lines;
  }
  const ASK_EVERY = 1000, HOLD = 1500, WORD_EVERY = 4000;
  const still = window.matchMedia?.("(prefers-reduced-motion: reduce)").matches;

  const scene = document.createElement("div"), strip = document.createElement("div");
  scene.className = "scenery"; strip.className = "scenery-strip";
  scene.setAttribute("aria-hidden", "true");
  scene.append(strip);
  wrap.prepend(scene);
  let slide = null;
  const art = new Image();
  art.onload = () => {
    const w = art.naturalWidth / 2, h = art.naturalHeight / 2;
    strip.style.backgroundSize = `${w}px ${h}px`;
    scene.style.height = `${h}px`;
    strip.style.width = `calc(100% + ${w}px)`;
    if (!still && strip.animate) {
      slide = strip.animate([{ transform: "translateX(0)" }, { transform: `translateX(${-w}px)` }],
        { duration: w * 60, iterations: Infinity });
      if (!on) slide.pause();
    }
  };
  art.src = "img/expedition.png";

  let on = false, lastBusy = 0, word = 0, wordTimer = 0;
  function show(want) {
    if (want === on) return;
    on = want;
    wrap.classList.toggle("exploring", on);
    line.hidden = !on;
    if (slide) { if (on) slide.play(); else setTimeout(() => { if (!on) slide.pause(); }, 900); }
    clearInterval(wordTimer);
    if (on) {
      word = pool === WORDS ? Math.floor(Math.random() * pool.length) : 0;
      line.firstChild.textContent = pool[word % pool.length];
      if (!still) wordTimer = setInterval(() => {
        line.classList.add("turning");
        setTimeout(() => { word = (word + 1) % pool.length; line.firstChild.textContent = pool[word]; line.classList.remove("turning"); }, 300);
      }, WORD_EVERY);
    }
  }
  function usePool(lines) {
    if (lines === pool || lines.join() === pool.join()) return;
    pool = lines;
    word = 0;
    if (on) line.firstChild.textContent = pool[0];
  }
  async function ask() {
    const asked = getJson("/api/activity", { quiet: true });
    try {
      const a = asked ? await asked : null;
      if (a && (a.downloading + a.working > 0 || Object.values(a.waiting || {}).some((secs) => secs >= WAIT_NOTED))) {
        lastBusy = Date.now();
        usePool(linesFor(a.waiting));
      } else if (a?.ahead > 0) {
        lastBusy = Date.now();
        usePool(AHEAD);
      }
    } catch (e) {   }
    show(Date.now() - lastBusy < HOLD);
  }
  setInterval(() => { if (!document.hidden) ask(); }, ASK_EVERY);
  document.addEventListener("visibilitychange", () => { if (!document.hidden) ask(); });
})();
