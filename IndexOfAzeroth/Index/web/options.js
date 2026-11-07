// The Index of Azeroth. Copyright 2026 Index Case <indexofazeroth@pm.me>. PolyForm Strict 1.0.0, see LICENSE.md.
"use strict";

const optionWords = typeof module === "object" ? require("./words.js") : { word, wordCount, wordsOf };
const CHARACTER_WORDS = optionWords.wordsOf("page.options.character");
const OPTIONS = [
  { id: "map", name: optionWords.word("page.options.map.name"), icon: "inv_misc_map_01", settings: [
    { id: "lighting", kind: "toggle", name: optionWords.word("page.options.map.lighting"), key: "cc.relief", start: true,
      text: optionWords.word("page.options.map.lighting.text"), none: optionWords.word("page.options.map.lighting.none") },
    { id: "night", kind: "toggle", name: optionWords.word("page.options.map.night"), key: "cc.night", start: true, text: optionWords.word("page.options.map.night.text") },
    { id: "zoneglow", kind: "toggle", name: optionWords.word("page.options.map.zone-glow"), key: "cc.zoneglow", start: true, text: optionWords.word("page.options.map.zone-glow.text") },
    { id: "continentnames", kind: "toggle", name: optionWords.word("page.options.map.continent-names"), key: "cc.continentnames", start: true,
      text: optionWords.word("page.options.map.continent-names.text") },
    { id: "zonenames", kind: "toggle", name: optionWords.word("page.options.map.zone-names"), key: "cc.zonenames", start: true,
      text: optionWords.word("page.options.map.zone-names.text") },
    { id: "citybanners", kind: "toggle", name: optionWords.word("page.options.map.city-banners"), key: "cc.citybanners", start: true,
      text: optionWords.word("page.options.map.city-banners.text") },
    { id: "placenames", kind: "toggle", name: optionWords.word("page.options.map.place-names"), key: "cc.placenames", start: true,
      text: optionWords.word("page.options.map.place-names.text") },
    { id: "replay", kind: "toggle", name: optionWords.word("page.options.map.replay"), key: "cc.replay", start: false, text: optionWords.word("page.options.map.replay.text") },
    { id: "gauntlet", kind: "toggle", name: optionWords.word("page.options.map.gauntlet"), key: "cc.gauntlet", start: true, text: optionWords.word("page.options.map.gauntlet.text") },
    { id: "travellers", kind: "toggle", name: optionWords.word("page.options.map.travellers"), key: "cc.travellers", start: true,
      text: optionWords.word("page.options.map.travellers.text") },
    { id: "mapkinds", kind: "choice", name: optionWords.word("page.options.map.maps-shown"), key: "cc.mapkinds", start: "both", text: optionWords.word("page.options.map.maps-shown.text"),
      choices: [{ value: "paper", name: optionWords.word("page.options.map.maps-shown.paper") },
        { value: "both", name: optionWords.word("page.options.map.maps-shown.both") },
        { value: "detailed", name: optionWords.word("page.options.map.maps-shown.detailed") }] },
    { id: "hotspots", kind: "slider", name: optionWords.word("page.options.map.hotspots"), key: "cc.hotspots", start: 100, min: 0, max: 100, step: 5, unit: "%",
      text: optionWords.word("page.options.map.hotspots.text") },
  ] },
  { id: "trees", name: optionWords.word("page.options.trees.name"), icon: "inv_misc_herb_07", settings: [
    { id: "trees", kind: "toggle", name: optionWords.word("page.options.trees.trees"), key: "cc.trees", start: false, text: optionWords.word("page.options.trees.trees.text") },
    { id: "treesThin", kind: "toggle", name: optionWords.word("page.options.trees.tree-transparency"), key: "cc.treesThin", start: true,
      text: optionWords.word("page.options.trees.tree-transparency.text") },
    { id: "canopy", kind: "checks", name: optionWords.word("page.options.trees.canopy"), key: "cc.canopyOff", start: [],
      text: optionWords.word("page.options.trees.canopy.text"), count: (n) => optionWords.wordCount("page.options.trees.canopy.shown", n),
      empty: optionWords.word("page.options.trees.canopy.none") },
  ] },
  { id: "guides", name: optionWords.word("page.options.guides.name"), icon: "inv_misc_spyglass_02", settings: [
    { id: "planmap", kind: "toggle", name: optionWords.word("page.options.guides.planning"), key: "cc.planmap", start: true,
      text: optionWords.word("page.options.guides.planning.text") },
    { id: "routeweigh", kind: "toggle", name: optionWords.word("page.options.guides.candidates"), key: "cc.routeweigh", start: true,
      text: optionWords.word("page.options.guides.candidates.text") },
  ] },
  { id: "combat", name: optionWords.word("page.options.combat.name"), icon: "ability_dualwield", settings: [
    { id: "bloodscreen", kind: "toggle", name: optionWords.word("page.options.combat.blood-screen"), key: "cc.bloodscreen", start: true,
      text: optionWords.word("page.options.combat.blood-screen.text") },
    { id: "bloodmap", kind: "toggle", name: optionWords.word("page.options.combat.blood-map"), key: "cc.bloodmap", start: true,
      text: optionWords.word("page.options.combat.blood-map.text") },
    { id: "deathpool", kind: "toggle", name: optionWords.word("page.options.combat.death-pool"), key: "cc.deathpool", start: true,
      text: optionWords.word("page.options.combat.death-pool.text") },
    { id: "combatwords", kind: "toggle", name: optionWords.word("page.options.combat.combat-words"), key: "cc.combatwords", start: true,
      text: optionWords.word("page.options.combat.combat-words.text") },
    { id: "idlewarning", kind: "toggle", name: optionWords.word("page.options.combat.idle-warning"), key: "cc.idlewarning", start: true,
      under: ["combatwords"], text: optionWords.word("page.options.combat.idle-warning.text") },
    { id: "edgeglow", kind: "toggle", name: optionWords.word("page.options.combat.edge-glow"), key: "cc.edgeglow", start: true,
      text: optionWords.word("page.options.combat.edge-glow.text") },
    { id: "duelflag", kind: "toggle", name: optionWords.word("page.options.combat.duel-flag"), key: "cc.duelflag", start: true,
      text: optionWords.word("page.options.combat.duel-flag.text") },
    { id: "mapshake", kind: "toggle", name: optionWords.word("page.options.combat.map-shake"), key: "cc.mapshake", start: true,
      under: ["duelflag"], text: optionWords.word("page.options.combat.map-shake.text") },
    { id: "bloodscreenstrength", kind: "slider", name: optionWords.word("page.options.combat.screen-blood-strength"), key: "cc.bloodscreenstrength",
      start: 100, min: 10, max: 100, step: 5, unit: "%", under: ["bloodscreen"], text: optionWords.word("page.options.combat.screen-blood-strength.text") },
    { id: "bloodmapstrength", kind: "slider", name: optionWords.word("page.options.combat.map-blood-strength"), key: "cc.bloodmapstrength",
      start: 100, min: 10, max: 100, step: 5, unit: "%", under: ["bloodmap", "deathpool"], text: optionWords.word("page.options.combat.map-blood-strength.text") },
  ] },
  { id: "character", name: optionWords.word("page.options.character.name"), icon: "inv_misc_head_human_01",
    settings: ["class", "supplies", "gold", "gear", "weapon", "skills", "leveling", "travel", "time", "party", "finder"].map((h) => ({
      id: `rows${h}`, kind: "checks", name: CHARACTER_WORDS[h], key: `cc.rows${h}`, start: [], text: CHARACTER_WORDS[`${h}.text`],
      count: (n) => optionWords.wordCount("page.options.character.shown", n), empty: optionWords.word("page.options.character.none") })) },
  { id: "levels", name: optionWords.word("page.options.level-report.name"), icon: "inv_scroll_03", settings: [
    { id: "levelreport", kind: "toggle", name: optionWords.word("page.options.level-report.level-report"), key: "cc.levelreport", start: true,
      text: optionWords.word("page.options.level-report.level-report.text") },
    { id: "polaroid", kind: "toggle", name: optionWords.word("page.options.level-report.polaroid"), key: "cc.polaroid", start: true,
      help: "polaroid", text: optionWords.word("page.options.level-report.polaroid.text") },
    { id: "xpglow", kind: "toggle", name: optionWords.word("page.options.level-report.xp-glow"), key: "cc.xpglow", start: true,
      text: optionWords.word("page.options.level-report.xp-glow.text") },
    { id: "skillglow", kind: "toggle", name: optionWords.word("page.options.level-report.skill-glow"), key: "cc.skillglow", start: true,
      text: optionWords.word("page.options.level-report.skill-glow.text") },
    { id: "levelflare", kind: "toggle", name: optionWords.word("page.options.level-report.flare"), key: "cc.levelflare", start: true,
      text: optionWords.word("page.options.level-report.flare.text") },
    { id: "glowstrength", kind: "slider", name: optionWords.word("page.options.level-report.glow-strength"), key: "cc.glowstrength", start: 100,
      min: 10, max: 100, step: 5, unit: "%", under: ["xpglow", "skillglow", "levelflare"], text: optionWords.word("page.options.level-report.glow-strength.text") },
  ] },
  { id: "topbar", name: optionWords.word("page.options.top-bar.name"), icon: "inv_misc_key_03", settings: [
    { id: "keynames", kind: "choice", name: optionWords.word("page.options.top-bar.key-names"), key: "cc.keynames", start: "turning",
      text: optionWords.word("page.options.top-bar.key-names.text"),
      choices: [{ value: "turning", name: optionWords.word("page.options.top-bar.key-names.turning") },
        { value: "fixed", name: optionWords.word("page.options.top-bar.key-names.fixed") }] },
  ] },
  { id: "importexport", name: optionWords.word("page.options.import-export.name"), icon: "inv_crate_01", panel: true, settings: [] },
];
const OPTIONS_KEPT = "cc.options";
const checkValue = (x) => Number.isFinite(x) || typeof x === "string";

class OptionsWindow {
  constructor({ box, key, list = OPTIONS, kept, keep, send = () => {}, hooks = {}, esc, help, put = (el, html) => { el.innerHTML = html; } }) {
    Object.assign(this, { box, key, list, kept, keep, send, hooks, esc, help, put });
    this.cat = kept(OPTIONS_KEPT, list[0].id);
    this.isOpen = false;
    this.dropped = null;
  }

  stored(s) { return this.kept(s.key, s.start); }

  store(s, v) {
    this.keep(s.key, v);
    this.send({ [s.key]: v });
  }

  keyed() { return this.list.flatMap((cat) => cat.settings.filter((s) => s.key)); }

  took(saved) {
    const told = [], missing = {};
    for (const s of this.keyed()) {
      const here = this.kept(s.key, null);
      if (!Object.hasOwn(saved, s.key)) {
        if (here != null) missing[s.key] = here;
      } else if (JSON.stringify(saved[s.key]) !== JSON.stringify(here)) {
        this.keep(s.key, saved[s.key]);
        told.push(s);
      }
    }
    if (Object.keys(missing).length) this.send(missing);
    for (const s of told) this.hooks[s.id]?.changed?.(this.get(s.id));
    if (told.length) this.refresh();
  }

  shownValue(s, v) { return s.format ? s.format(v) : `${v}${s.unit || ""}`; }

  find(id) {
    for (const cat of this.list) for (const s of cat.settings) if (s.id === id) return s;
    return null;
  }

  can(s) { return this.hooks[s.id]?.can?.() ?? true; }

  works(s) { return !s.under || s.under.some((id) => this.get(id)); }

  settable(s) { return this.can(s) && this.works(s); }

  shown(s) { return this.hooks[s.id]?.shown?.() ?? true; }

  choices(s) { return this.hooks[s.id]?.choices?.() ?? []; }

  value(s) {
    const v = this.stored(s);
    if (s.kind === "choice") return s.choices.some((c) => c.value === v) ? v : s.start;
    if (s.kind === "checks") return Array.isArray(v) ? v.filter(checkValue) : s.start;
    if (s.kind !== "slider") return v;
    const stepped = s.min + Math.round((v - s.min) / s.step) * s.step;
    return Math.min(s.max, Math.max(s.min, stepped));
  }

  get(id) {
    const s = this.find(id);
    if (s.kind === "choice") return this.can(s) ? this.value(s) : s.start;
    return s.kind === "toggle" ? this.settable(s) && !!this.value(s) : this.value(s);
  }

  set(id, v) {
    const s = this.find(id);
    const fits = s.kind === "choice" ? s.choices.some((c) => c.value === v) : s.kind !== "checks" || Array.isArray(v);
    if (this.settable(s) && fits) {
      this.store(s, s.kind === "toggle" ? !!v : s.kind === "checks" ? v.filter(checkValue) : s.kind === "choice" ? v : Number(v));
    }
    this.hooks[id]?.changed?.(this.get(id));
    for (const below of this.keyed().filter((x) => x.under?.includes(id))) this.hooks[below.id]?.changed?.(this.get(below.id));
    if (this.isOpen) this.draw();
  }

  start() {
    for (const id of Object.keys(this.hooks)) this.hooks[id].changed?.(this.get(id));
  }

  open(cat = this.cat) {
    this.isOpen = true;
    this.show(cat);
  }

  refresh() {
    if (this.isOpen) this.draw();
  }

  close() {
    this.isOpen = false;
    this.dropped = null;
    this.box.hidden = true;
    this.key.setAttribute("aria-pressed", "false");
  }

  toggle() {
    if (this.isOpen) this.close();
    else this.open();
  }

  show(id) {
    this.cat = this.list.some((c) => c.id === id) ? id : this.list[0].id;
    this.keep(OPTIONS_KEPT, this.cat);
    this.draw();
  }

  draw() {
    const e = this.esc, cat = this.list.find((c) => c.id === this.cat);
    const cats = this.list.map((c) => `<button class="key small opt-cat" data-opt-cat="${e(c.id)}" aria-pressed="${c.id === cat.id}">`
      + `<img src="/icon/${e(c.icon)}.jpg" alt="">${e(c.name)}</button>`).join("");
    const body = cat.panel ? `<div class="opt-panel">${this.hooks[cat.id]?.panel?.() ?? ""}</div>`
      : cat.settings.filter((s) => this.shown(s)).map((s) => this.row(s)).join("");
    this.put(this.box, `<div class="rd-bar opt-bar"><span class="rd-title">Options</span><span class="rd-keys">`
      + `<button class="key small square x-mark" data-opt-close="1" title="Close (Escape)">&times;</button></span></div>`
      + `<div class="opt-main"><nav class="opt-cats" aria-label="Categories">${cats}</nav>`
      + `<div class="opt-page"><h3 class="opt-head">${e(cat.name)}</h3>${body}</div></div>`);
    this.box.hidden = false;
    this.key.setAttribute("aria-pressed", "true");
  }

  row(s) {
    const e = this.esc, can = this.can(s), works = this.works(s), off = can && works ? "" : " disabled", why = can ? "" : ` title="${e(s.none)}"`;
    const help = s.help ? this.help(s.help) : "";
    let control;
    if (s.kind === "toggle") {
      const on = this.get(s.id);
      control = `<span class="opt-pair"><button class="key small" data-opt-set="${e(s.id)}" data-opt-to="1" aria-pressed="${on}"${off}${why}>On</button>`
        + `<button class="key small" data-opt-set="${e(s.id)}" data-opt-to="0" aria-pressed="${!on}"${off}${why}>Off</button></span>`;
    } else if (s.kind === "choice") {
      const v = this.get(s.id);
      control = `<span class="opt-pair">${s.choices.map((c) => `<button class="key small" data-opt-set="${e(s.id)}" data-opt-to="${e(c.value)}"`
        + ` aria-pressed="${c.value === v}"${off}${why}>${e(c.name)}</button>`).join("")}</span>`;
    } else if (s.kind === "checks") {
      const unticked = new Set(this.get(s.id)), choices = this.choices(s);
      const ticked = choices.filter((c) => !unticked.has(c.value)).length;
      const boxes = choices.map((c) => `<label class="opt-check"><input type="checkbox" data-opt-check="${e(s.id)}" value="${e(c.value)}"`
        + `${unticked.has(c.value) ? "" : " checked"}${off}>${e(c.name)}</label>`).join("");
      const open = this.dropped === s.id && choices.length && can ? " open" : "";
      control = `<details class="opt-drop" data-opt-drop="${e(s.id)}"${open}><summary class="key small"${why}>`
        + `${e(choices.length ? s.count(ticked) : s.empty)}</summary><div class="opt-checks">${boxes}</div></details>`;
    } else {
      const v = this.value(s), shown = this.shownValue(s, v);
      control = `<span class="opt-slide"><input type="range" data-opt-slide="${e(s.id)}" min="${s.min}" max="${s.max}" step="${s.step}" value="${v}"`
        + ` aria-label="${e(s.name)}" title="${e(shown)}"${off}${why}><output>${e(shown)}</output></span>`;
    }
    const wide = (s.kind === "choice" && s.choices.length > 2) || s.kind === "checks" ? " wide" : "";
    return `<div class="opt-row${wide}${can && works ? "" : " off"}"><div class="opt-words"><div class="opt-name with-help">${e(s.name)}${help}</div>`
      + `<div class="opt-text">${e(s.text)}</div>${can ? "" : `<div class="opt-why">${e(s.none)}</div>`}</div>${control}</div>`;
  }

  click(ev) {
    const t = ev.target;
    const cat = t.closest("[data-opt-cat]");
    if (cat) return this.show(cat.dataset.optCat);
    const check = t.closest("[data-opt-check]");
    if (check) {
      const id = check.dataset.optCheck, v = this.choices(this.find(id)).find((c) => String(c.value) === check.value)?.value;
      if (v === undefined) return;
      const rest = this.get(id).filter((x) => x !== v);
      this.dropped = id;
      return this.set(id, check.checked ? rest : [...rest, v]);
    }
    const drop = t.closest("[data-opt-drop] > summary");
    if (drop) {
      const box = drop.parentElement;
      this.dropped = box.open ? null : box.dataset.optDrop;
      return;
    }
    const set = t.closest("[data-opt-set]");
    if (set) {
      const to = set.dataset.optTo;
      return this.set(set.dataset.optSet, this.find(set.dataset.optSet).kind === "choice" ? to : to === "1");
    }
    if (t.closest("[data-opt-close]")) return this.close();
    this.panelHook()?.click?.(ev);
  }

  panelHook() {
    return this.list.find((c) => c.id === this.cat).panel ? this.hooks[this.cat] : null;
  }

  input(ev) {
    const t = ev.target.closest("[data-opt-slide]");
    if (!t) return this.panelHook()?.input?.(ev);
    const s = this.find(t.dataset.optSlide);
    this.store(s, Number(t.value));
    this.hooks[s.id]?.changed?.(this.get(s.id));
    const shown = this.shownValue(s, this.value(s));
    t.title = shown;
    t.closest(".opt-slide").querySelector("output").textContent = shown;
  }
}

if (typeof module === "object") {
  module.exports = { OPTIONS, OPTIONS_KEPT, OptionsWindow };
}
