// The Index of Azeroth. Copyright 2026 Index Case <indexofazeroth@pm.me>. PolyForm Strict 1.0.0, see LICENSE.md.
"use strict";

const cbt = { pvp: null, pvpFailed: false, meter: null, meterFailed: false, for: null };
const CB_WORDS = wordsOf("page.combat.menu");
const cbW = (key, fill) => fillWords(CB_WORDS[key], fill) ?? "";
const combatMenu = $("combat-menu");

function combatPvpGlance() {
  if (!cbt.pvp) return cbt.pvpFailed ? esc(pvW("window.failed")) : "";
  const counted = pvpCounted(cbt.pvp.fights || [], pv.bgs);
  const r = pvpLatest(counted);
  if (!r) return esc(cbW("pvp.none"));
  const outcome = pvW(`table.${r.duel ? `duel.${r.outcome}` : r.outcome}`), when = pvWhen(r.t);
  const latest = r.opp?.name ? cbW("pvp.latest", { outcome, name: r.opp.name, when }) : cbW("pvp.latest.nobody", { outcome, when });
  const rec = pvpRecord(counted), rate = pvpRate(rec);
  return `<span class="cb-line">${esc(latest)}</span><span class="cb-line">${pvWL(rec)}${rate == null ? "" : ` <span class="cb-rate">${esc(cbW("pvp.rate", { rate }))}</span>`}</span>`;
}

function combatMeterGlance() {
  if (!cbt.meter) return cbt.meterFailed ? esc(mtW("window.failed")) : "";
  const g = meterGlance(cbt.meter);
  return esc(g ? cbW(g.open ? "meter.now" : "meter.last", { dps: num(g.dps) }) : cbW("meter.none"));
}

const combatEntry = (name, icon, glance) => `<div class="cb-entry"><button class="key" data-combat="${name}" style="--icon:url(/icon/${esc(icon)}.jpg)"
  title="${esc(cbW(`${name}.tip`))}">${esc(cbW(name))}</button><span class="cb-glance">${glance}</span></div>`;

function renderCombatMenu() {
  if (combatMenu.hidden) return;
  $("combat-list").innerHTML = `<div class="cb-entries">${combatEntry("pvp", pvBanner(), combatPvpGlance())}${combatEntry("meter", METER_ICONS.meter, combatMeterGlance())}</div>`;
}

function askCombat() {
  if (!app.character) return;
  cbt.for = app.character;
  getJson("/api/pvp", { force: true })?.then((j) => { cbt.pvp = j; cbt.pvpFailed = false; renderCombatMenu(); },
    () => { cbt.pvpFailed = true; renderCombatMenu(); });
  askMeter()?.then((d) => { cbt.meter = d; cbt.meterFailed = false; renderCombatMenu(); },
    () => { cbt.meterFailed = true; renderCombatMenu(); });
}

const toggleCombatMenu = dropdown($("btn-pvp"), combatMenu, "b", () => { askCombat(); renderCombatMenu(); },
  { el: $("combat-bar"), title: cbW("title") });

on("snapshot", () => {
  if (combatMenu.hidden || !app.character || cbt.for === app.character) return;
  Object.assign(cbt, { pvp: null, pvpFailed: false, meter: null, meterFailed: false });
  askCombat();
  renderCombatMenu();
});

function combatClicked(e) {
  const b = e.target.closest?.("button[data-combat]");
  if (!b) return;
  (b.dataset.combat === "pvp" ? openPvp : openMeter)();
  toggleCombatMenu(false);
}
combatMenu.addEventListener("click", combatClicked);

(function combatKey() {
  const key = $("btn-pvp");
  key.title = cbW("key.tip");
  key.querySelector(".key-word").textContent = cbW("key");
  let shown = null;
  const icon = () => {
    if (pvBanner() === shown) return;
    shown = pvBanner();
    key.style.setProperty("--icon", `url(/icon/${shown}.jpg)`);
  };
  icon();
  on("snapshot", icon);
})();
