-- The Index of Azeroth. Copyright 2026 Index Case <indexofazeroth@pm.me>. PolyForm Strict 1.0.0, see LICENSE.md.
local ADDON, ns = ...
local Word = ns.Word

local DEFAULTS = {
  general = { button = true, mapPaste = true, warningSound = true, chatTab = true, accept = true, handIn = true, flights = true,
              rewardMark = true, sellPrice = false, minimap = true, minimapAngle = 225 },
  card = { foldInCombat = true, along = true, did = true, drift = true, nextZones = true, classQuest = true },
  world = { sparkles = false },
  polaroid = { on = true },
  plateCount = { on = true, x = 0, y = 0 },
  plates = { far = true, friends = true, loopMarks = true },
  targetKey = { mark = true, world = true, dungeons = false, cardHidden = true, flights = true },
  nav = { compass = true, arrows = true, beacons = true, line = true, mapLine = true, declutter = false, prefer = "beacons",
          cone = 90, arrowPast = 1500, aim = "arrow",
          places = false,
          brackets = true, beaconStrength = 100, compassSize = 100 },
}
local CONE_LO, CONE_STEP = 10, 5
local PAST_LO, PAST_HI, PAST_STEP = 500, 3000, 100
local RANGE_X, RANGE_Y = 150, 80

local function ConeHi()
  local view = ns.ViewAcross and ns.ViewAcross() or 90
  return math.max(CONE_LO, math.floor(view / CONE_STEP + 1e-6) * CONE_STEP)
end

local checked = nil
function ns.Options()
  local o = type(IndexOfAzerothDB) == "table" and IndexOfAzerothDB.options
  if o ~= nil and o == checked then return o end
  if type(IndexOfAzerothDB) ~= "table" then IndexOfAzerothDB = {} end
  o = type(o) == "table" and o or {}
  IndexOfAzerothDB.options = o
  if type(o.nav) == "table" and o.nav.mapLine == nil and type(o.nav.line) == "boolean" then o.nav.mapLine = o.nav.line end
  local gen = o.general
  if type(gen) == "table" and type(gen.quests) == "boolean" then
    if gen.accept == nil then gen.accept = gen.quests end
    if gen.handIn == nil then gen.handIn = gen.quests end
    gen.quests = nil
  end
  for group, d in pairs(DEFAULTS) do
    local g = type(o[group]) == "table" and o[group] or {}
    o[group] = g
    for k, v in pairs(d) do if type(g[k]) ~= type(v) then g[k] = v end end
  end
  checked = o
  return o
end

function ns.NavOn(key)
  return ns.Options().nav[key]
end

local listeners = {}
function ns.OnOptions(fn) listeners[#listeners + 1] = fn end
local function Changed()
  for _, fn in ipairs(listeners) do pcall(fn) end
end
ns.OptionsChanged = Changed

local Plain, Call = ns.Plain, ns.Call
local SPARKLE_CVARS = { { "outlineModeShowLootEffectWhenDisabled", "1" }, { "graphicsOutlineMode", "0" },
  { "OutlineEngineMode", "0" }, { "raidGraphicsOutlineMode", "0" }, { "RAIDOutlineEngineMode", "0" } }
local sparkleReady, sparkleBusy = false, false
local function Sparkles()
  if not sparkleReady or sparkleBusy or not C_CVar then return end
  sparkleBusy = true
  local on, kept = ns.Options().world.sparkles, IndexOfAzerothDB.ownSparkle
  for _, s in ipairs(SPARKLE_CVARS) do
    local name, ours = s[1], s[2]
    local now = Plain(Call(C_CVar.GetCVarInfo, name)) ~= nil and Plain(Call(C_CVar.GetCVar, name))
    if now and on then
      if type(kept) ~= "table" then kept = {}; IndexOfAzerothDB.ownSparkle = kept end
      if kept[name] == nil then kept[name] = now end
      if now ~= ours then Call(C_CVar.SetCVar, name, ours) end
    elseif now and type(kept) == "table" and kept[name] ~= nil and now == ours and kept[name] ~= ours then
      Call(C_CVar.SetCVar, name, kept[name]) end
  end
  if not on then IndexOfAzerothDB.ownSparkle = nil end
  sparkleBusy = false
end
ns.Sparkles = Sparkles
ns.On({ "VARIABLES_LOADED", "PLAYER_ENTERING_WORLD", "CVAR_UPDATE", "GX_RESTARTED" }, function(event)
  if event == "VARIABLES_LOADED" or Plain(Call(C_CVar and C_CVar.AreCVarsLoaded)) then sparkleReady = true end
  Sparkles()
end)
ns.OnOptions(Sparkles)

local TREE = {
  { name = Word("game.options.window.general"), pages = { { key = "general", name = Word("game.options.window.general.general") },
    { key = "world", name = Word("game.options.window.general.graphics") },
    { key = "polaroid", name = Word("game.options.window.general.level-up-picture") } } },
  { name = Word("game.options.window.quest-epic"), pages = { { key = "card", name = Word("game.options.window.quest-epic.card") } } },
  { name = Word("game.options.window.navigation"),
    pages = { { key = "navigation", name = Word("game.options.window.navigation.guidance") } } },
  { name = Word("game.options.window.targets"), pages = { { key = "nameplates", name = Word("game.options.window.targets.nameplates") },
    { key = "targetkey", name = Word("game.options.window.targets.target-key") } } },
}
local W, H, TREE_W, ROW_H, HEAD_H = 560, 620, 140, 22, 34
local PAGE_W = W - TREE_W - 30
local CONTROL_X = 172
local VALUE_W = 34
local SLIDER_W = PAGE_W - (CONTROL_X + 22) - (4 + 18 + 2 + VALUE_W)
local BUILD = {}
local win, current
local rows, pages = {}, {}

local function Toggle(p, ui, y, label, get, set, words)
  local t = ui.Text(p, "GameFontHighlight", ui.C.ivory)
  t:SetPoint("TOPLEFT", 0, y)
  t:SetWidth(CONTROL_X - 8)
  t:SetText(label)
  if words then
    local help = ui.Text(p, "GameFontHighlightSmall", ui.C.muted)
    help:SetPoint("TOPLEFT", 0, y - 24)
    help:SetWidth(PAGE_W)
    help:SetText(words)
  end
  local on, off
  local function Show(v) on:SetSelected(v); off:SetSelected(not v) end
  on = ui.FlatButton(p, Word("game.options.window.on"), 52, function() set(true); Show(true) end)
  off = ui.FlatButton(p, Word("game.options.window.off"), 52, function() set(false); Show(false) end)
  on:SetHeight(20); off:SetHeight(20)
  on:SetPoint("TOPLEFT", CONTROL_X, y + 3)
  off:SetPoint("LEFT", on, "RIGHT", 4, 0)
  return function() Show(get() and true or false) end, on, off
end

local function Check(p, ui, x, y, label, get, set, words, round)
  local C = ui.C
  local row = CreateFrame("Button", nil, p)
  row:SetPoint("TOPLEFT", x, y)
  row:SetSize(PAGE_W - x, 18)
  local box = CreateFrame("Frame", nil, row, "BackdropTemplate")
  box:SetSize(14, 14)
  box:SetPoint("LEFT", 0, 0)
  ui.Skin(box, C.row, C.edge)
  local tick = box:CreateTexture(nil, "OVERLAY")
  if round then
    tick:SetColorTexture(C.gold[1], C.gold[2], C.gold[3], 1)
    tick:SetSize(6, 6)
    tick:SetPoint("CENTER")
  else
    tick:SetTexture("Interface\\Buttons\\UI-CheckBox-Check")
    tick:SetSize(20, 20)
    tick:SetPoint("CENTER", 1, 0)
  end
  local t = ui.Text(row, "GameFontHighlight", C.ivory)
  t:SetPoint("LEFT", box, "RIGHT", 8, 0)
  t:SetText(label)
  row.label = t
  local help
  if words then
    help = ui.Text(p, "GameFontHighlightSmall", C.muted)
    help:SetPoint("TOPLEFT", row, "BOTTOMLEFT", 22, -1)
    help:SetWidth(PAGE_W - x - 22)
    help:SetText(words)
  end
  local function Show() tick:SetShown(get() and true or false) end
  row:SetScript("OnClick", function() set(not get()); Show() end)
  row:SetScript("OnEnter", function() box:SetBackdropBorderColor(C.gold[1], C.gold[2], C.gold[3], 1) end)
  row:SetScript("OnLeave", function() box:SetBackdropBorderColor(unpack(C.edge)) end)
  row.help = help
  return Show, row
end

local function Slider(p, ui, y, label, lo, hi, get, set, opts)
  opts = opts or {}
  local C, x, step = ui.C, opts.x or 0, opts.step or 1
  local function Hi() return type(hi) == "function" and hi() or hi end
  local function Cur() return math.max(lo, math.min(Hi(), get())) end
  local row = CreateFrame("Frame", nil, p)
  row:SetPoint("TOPLEFT", x, y)
  row:SetSize(PAGE_W - x, 20)
  local t = ui.Text(row, "GameFontHighlight", C.ivory)
  t:SetPoint("TOPLEFT", 0, 0)
  t:SetText(label)
  local s = CreateFrame("Slider", nil, row, "BackdropTemplate")
  s:SetOrientation("HORIZONTAL")
  s:SetSize(SLIDER_W, 10)
  s:SetPoint("TOPLEFT", CONTROL_X + 22 - x, -3)
  ui.Skin(s, C.row, C.edge)
  s:SetThumbTexture(ui.WHITE)
  local thumb = s:GetThumbTexture()
  if thumb then thumb:SetSize(8, 16); thumb:SetVertexColor(C.gold[1], C.gold[2], C.gold[3], 1) end
  s:SetMinMaxValues(lo, Hi())
  s:SetValueStep(step)
  s:SetObeyStepOnDrag(true)
  local value = ui.Text(row, "GameFontHighlightSmall", C.gold, "RIGHT")
  value:SetWidth(VALUE_W)
  local function Show(v) value:SetText(opts.fmt and opts.fmt(v) or (v > 0 and ("+" .. v) or tostring(v))) end
  local function Step(d)
    local v = math.max(lo, math.min(Hi(), Cur() + d * step))
    set(v)
    s:SetValue(v)
    Show(v)
  end
  s:EnableMouseWheel(true)
  s:SetScript("OnMouseWheel", function(_, d) Step(d) end)
  local minus = ui.FlatButton(row, "-", 18, function() Step(-1) end)
  minus:SetSize(18, 18)
  minus:SetPoint("RIGHT", s, "LEFT", -4, 0)
  local plus = ui.FlatButton(row, "+", 18, function() Step(1) end)
  plus:SetSize(18, 18)
  plus:SetPoint("LEFT", s, "RIGHT", 4, 0)
  value:SetPoint("LEFT", plus, "RIGHT", 2, 0)
  if opts.words then
    row.help = ui.Text(row, "GameFontHighlightSmall", C.muted)
    row.help:SetPoint("TOPLEFT", t, "BOTTOMLEFT", 0, -3)
    row.help:SetWidth(PAGE_W - x)
    row.help:SetText(opts.words)
  end
  s:SetScript("OnValueChanged", function(_, v)
    v = math.floor((v or 0) / step + 0.5) * step
    Show(v)
    if v ~= get() then set(v) end
  end)
  row.value = value
  return function() s:SetMinMaxValues(lo, Hi()); s:SetValue(Cur()); Show(Cur()) end, row
end

local function Heading(p, ui, title, words, y)
  y = y or 0
  local h = ui.Text(p, "GameFontNormal", ui.C.gold)
  h:SetPoint("TOPLEFT", 0, y)
  h:SetText(title)
  if not words then return end
  local help = ui.Text(p, "GameFontHighlightSmall", ui.C.muted)
  help:SetPoint("TOPLEFT", 0, y - 18)
  help:SetWidth(W - TREE_W - 40)
  help:SetText(words)
end

BUILD.general = function(p, ui)
  local function o() return ns.Options().general end
  local shows = {}
  local function Add(y, key, label, words, x)
    local show, row = Check(p, ui, x or 0, y, label, function() return o()[key] end,
      function(v) o()[key] = v; Changed(); p.Refresh() end, words)
    shows[#shows + 1] = show
    return row
  end
  Heading(p, ui, Word("game.options.general.on-screen"), Word("game.options.general.on-screen.help"))
  Add(-52, "button", Word("game.options.general.button"), Word("game.options.general.button.help"))
  Add(-138, "mapPaste", Word("game.options.general.map-paste"), Word("game.options.general.map-paste.help"))
  Add(-174, "warningSound", Word("game.options.general.warning-sound"), Word("game.options.general.warning-sound.help"))
  Add(-222, "chatTab", Word("game.options.general.chat-tab"), Word("game.options.general.chat-tab.help"))
  Heading(p, ui, Word("game.options.general.guides"), Word("game.options.general.guides.help"), -274)
  Add(-326, "accept", Word("game.options.general.accept"), Word("game.options.general.accept.help"))
  Add(-374, "handIn", Word("game.options.general.hand-in"), Word("game.options.general.hand-in.help"))
  Add(-410, "flights", Word("game.options.general.flights"), Word("game.options.general.flights.help"))
  Add(-446, "rewardMark", Word("game.options.general.reward-mark"), Word("game.options.general.reward-mark.help"))
  local priceRow = Add(-482, "sellPrice", Word("game.options.general.sell-price"), Word("game.options.general.sell-price.help"), 22)
  ns.optionsPriceRow = priceRow
  return function()
    for _, show in ipairs(shows) do show() end
    local lit = o().rewardMark and 1 or 0.5
    priceRow:SetAlpha(lit)
    priceRow.help:SetAlpha(lit)
  end
end

local GROUND = {
  { cvar = "groundEffectDensity", value = 256, label = Word("game.options.graphics.ground.density") },
  { cvar = "groundEffectFade", value = 370, label = Word("game.options.graphics.ground.fade") },
  { cvar = "groundEffectDist", value = 500, label = Word("game.options.graphics.ground.distance") },
}

BUILD.world = function(p, ui)
  local function o() return ns.Options().world end
  Heading(p, ui, Word("game.options.graphics.quest-items"))
  local label = Word("game.options.graphics.sparkles")
  local show, row = Check(p, ui, 0, -28, label, function() return o().sparkles end,
    function(v) o().sparkles = v; Changed() end, Word("game.options.graphics.sparkles.help"))
  row:HookScript("OnEnter", function(self)
    GameTooltip:SetOwner(self, "ANCHOR_RIGHT")
    GameTooltip:AddLine(label)
    GameTooltip:AddLine(Word("game.options.graphics.sparkles.tip"), 0.8, 0.8, 0.8, true)
    GameTooltip:Show()
  end)
  row:HookScript("OnLeave", function() GameTooltip:Hide() end)
  ns.optionsSparkleRow = row
  local top = -122
  Heading(p, ui, Word("game.options.graphics.ground"), Word("game.options.graphics.ground.help"), top)
  local shows = { show }
  for i, g in ipairs(GROUND) do
    shows[#shows + 1] = Check(p, ui, 0, top - 48 - (i - 1) * 24, g.label .. " " .. g.value,
      function() return tonumber(C_CVar.GetCVar(g.cvar)) == g.value end,
      function(v)
        local was = o().groundWas or {}
        o().groundWas = was
        if v then
          was[g.cvar] = was[g.cvar] or C_CVar.GetCVar(g.cvar)
          C_CVar.SetCVar(g.cvar, g.value)
        else
          C_CVar.SetCVar(g.cvar, was[g.cvar] or C_CVar.GetCVarDefault(g.cvar))
          was[g.cvar] = nil
        end
        Changed()
      end)
  end
  return function() for _, s in ipairs(shows) do s() end end
end

BUILD.polaroid = function(p, ui)
  Heading(p, ui, Word("game.options.level-up-picture.heading"), Word("game.options.level-up-picture.heading.help"))
  local shown = Toggle(p, ui, -74, Word("game.options.level-up-picture.take"), function() return ns.Options().polaroid.on end,
    function(v) ns.Options().polaroid.on = v; Changed() end)
  local how = ui.Text(p, "GameFontHighlightSmall", ui.C.muted)
  how:SetPoint("TOPLEFT", 0, -106)
  how:SetWidth(PAGE_W)
  how:SetText(Word("game.options.level-up-picture.try"))
  return function() shown() end
end

BUILD.card = function(p, ui)
  local function o() return ns.Options().card end
  local shows = {}
  local function Add(y, key, label, words)
    shows[#shows + 1] = Toggle(p, ui, y, label, function() return o()[key] end, function(v) o()[key] = v; Changed() end, words)
  end
  Add(-4, "along", Word("game.options.card.along"), Word("game.options.card.along.help"))
  Add(-54, "did", Word("game.options.card.did"), Word("game.options.card.did.help"))
  Heading(p, ui, Word("game.options.card.heading"), nil, -112)
  Add(-142, "foldInCombat", Word("game.options.card.fold"))
  Heading(p, ui, Word("game.options.card.slide-outs"), nil, -186)
  Add(-216, "drift", Word("game.options.card.drift"), Word("game.options.card.drift.help"))
  Add(-266, "nextZones", Word("game.options.card.next-zones"), Word("game.options.card.next-zones.help"))
  Add(-316, "classQuest", Word("game.options.card.class-quest"), Word("game.options.card.class-quest.help"))
  return function() for _, show in ipairs(shows) do show() end end
end

BUILD.navigation = function(p, ui)
  local function o() return ns.Options().nav end
  Heading(p, ui, Word("game.options.guidance.heading"), Word("game.options.guidance.heading.help"))
  local shows = {}
  local function Add(y, label, get, set, x, words, round)
    local show, row = Check(p, ui, x or 0, y, label, get, function(v) set(v); Changed(); p.Refresh() end, words, round)
    shows[#shows + 1] = show
    return row
  end
  Add(-52, Word("game.options.guidance.compass"), function() return ns.NavOn("compass") end, function(v) o().compass = v end)
  local placesRow = Add(-74, Word("game.options.guidance.places"), function() return o().places end,
    function(v) o().places = v end, 22)
  placesRow:HookScript("OnEnter", function(self)
    GameTooltip:SetOwner(self, "ANCHOR_RIGHT")
    GameTooltip:AddLine(Word("game.options.guidance.places"))
    GameTooltip:AddLine(Word("game.options.guidance.places.tip"), 0.8, 0.8, 0.8, true)
    GameTooltip:Show()
  end)
  placesRow:HookScript("OnLeave", function() GameTooltip:Hide() end)
  ns.optionsPlacesRow = placesRow
  Add(-96, Word("game.options.guidance.arrows"), function() return o().arrows end, function(v) o().arrows = v end)
  local aims = {}
  local function Aim(x, label, aim, words)
    local row = Add(-118, label, function() return o().aim == aim end, function() o().aim = aim end, x, nil, true)
    row:SetWidth(150)
    row:HookScript("OnEnter", function(self)
      GameTooltip:SetOwner(self, "ANCHOR_RIGHT")
      GameTooltip:AddLine(label)
      GameTooltip:AddLine(words, 0.8, 0.8, 0.8, true)
      GameTooltip:Show()
    end)
    row:HookScript("OnLeave", function() GameTooltip:Hide() end)
    aims[aim] = row
  end
  Aim(22, Word("game.options.guidance.glow"), "glow", Word("game.options.guidance.glow.tip"))
  Aim(182, Word("game.options.guidance.arrow"), "arrow", Word("game.options.guidance.arrow.tip"))
  ns.optionsAimRows = aims
  Add(-140, Word("game.options.guidance.beacons"), function() return ns.NavOn("beacons") end, function(v) o().beacons = v end)
  Add(-162, Word("game.options.guidance.minimap-line"), function() return o().line end, function(v) o().line = v end)
  Add(-184, Word("game.options.guidance.map-line"), function() return o().mapLine end, function(v) o().mapLine = v end)
  Add(-206, Word("game.options.guidance.brackets"), function() return o().brackets end, function(v) o().brackets = v end, 0,
    Word("game.options.guidance.brackets.help"))
  local warn = ui.Text(p, "GameFontHighlight", ui.C.red)
  warn:SetPoint("TOPLEFT", 0, -246)
  warn:SetWidth(PAGE_W)
  warn:SetText(Word("game.options.guidance.all-off"))
  ns.optionsNavWarn = warn
  Add(-278, Word("game.options.guidance.declutter"), function() return o().declutter end, function(v) o().declutter = v end, 0,
    Word("game.options.guidance.declutter.help"))
  local arrows = Add(-326, Word("game.options.guidance.prefer-arrows"), function() return o().prefer == "arrows" end,
    function() o().prefer = "arrows" end, 22, Word("game.options.guidance.prefer-arrows.help"), true)
  local beacons = Add(-364, Word("game.options.guidance.prefer-beacons"), function() return o().prefer ~= "arrows" end,
    function() o().prefer = "beacons" end, 22, Word("game.options.guidance.prefer-beacons.help"), true)
  local cone, coneRow = Slider(p, ui, -416, Word("game.options.guidance.cone"), CONE_LO, ConeHi, function() return o().cone end,
    function(v) o().cone = v; Changed() end, { x = 22, step = CONE_STEP, fmt = function(v) return v .. "°" end })
  shows[#shows + 1] = cone
  ns.optionsConeRow = coneRow
  local past, pastRow = Slider(p, ui, -446, Word("game.options.guidance.past"), PAST_LO, PAST_HI, function() return o().arrowPast end,
    function(v) o().arrowPast = v; Changed() end, { x = 22, step = PAST_STEP, fmt = tostring,
      words = Word("game.options.guidance.past.help") })
  shows[#shows + 1] = past
  ns.optionsPastRow = pastRow
  local pct = function(v) return v .. "%" end
  shows[#shows + 1] = Slider(p, ui, -486, Word("game.options.guidance.beacon-strength"), 20, 100, function() return o().beaconStrength end,
    function(v) o().beaconStrength = v; Changed() end, { step = 5, fmt = pct, words = Word("game.options.guidance.beacon-strength.help") })
  shows[#shows + 1] = Slider(p, ui, -522, Word("game.options.guidance.compass-size"), 50, 150, function() return o().compassSize end,
    function(v) o().compassSize = v; Changed() end, { step = 5, fmt = pct, words = Word("game.options.guidance.compass-size.help") })
  return function()
    for _, show in ipairs(shows) do show() end
    local n = o()
    warn:SetShown(not (ns.NavOn("compass") or n.arrows or ns.NavOn("beacons") or n.line or n.mapLine))
    placesRow:SetAlpha(ns.NavOn("compass") and 1 or 0.5)
    for _, row in ipairs({ arrows, beacons, coneRow }) do
      row:SetShown(n.declutter)
      if row.help then row.help:SetShown(n.declutter) end
    end
    pastRow:SetShown(n.declutter and n.prefer ~= "arrows")
  end
end

BUILD.nameplates = function(p, ui)
  local function o() return ns.Options().plateCount end
  Heading(p, ui, Word("game.options.nameplates.count"), Word("game.options.nameplates.count.help"))
  local shown = Toggle(p, ui, -74, Word("game.options.nameplates.shown"), function() return o().on end,
    function(v) o().on = v; Changed() end)
  local across = Slider(p, ui, -106, Word("game.options.nameplates.across"), -RANGE_X, RANGE_X, function() return o().x end,
    function(v) o().x = v; Changed() end)
  local up = Slider(p, ui, -136, Word("game.options.nameplates.up"), -RANGE_Y, RANGE_Y, function() return o().y end,
    function(v) o().y = v; Changed() end)
  local back = ui.FlatButton(p, Word("game.options.nameplates.reset"), 130, function() o().x, o().y = 0, 0; Changed(); p.Refresh() end)
  back:SetHeight(22)
  back:SetPoint("TOPLEFT", 0, -170)
  Heading(p, ui, Word("game.options.nameplates.far"), Word("game.options.nameplates.far.help"), -212)
  local far, farOn, farOff = Toggle(p, ui, -274, Word("game.options.nameplates.far.on"), function() return ns.Options().plates.far end,
    function(v) ns.Options().plates.far = v; Changed() end)
  ns.optionsFar = { on = farOn, off = farOff }
  Heading(p, ui, Word("game.options.nameplates.friends"), Word("game.options.nameplates.friends.help"), -316)
  local friends, friendsOn, friendsOff = Toggle(p, ui, -390, Word("game.options.nameplates.friends.on"),
    function() return ns.Options().plates.friends end, function(v) ns.Options().plates.friends = v; Changed() end)
  ns.optionsFriends = { on = friendsOn, off = friendsOff }
  local loop = Toggle(p, ui, -432, Word("game.options.nameplates.loop-marks"), function() return ns.Options().plates.loopMarks end,
    function(v) ns.Options().plates.loopMarks = v; Changed() end, Word("game.options.nameplates.loop-marks.help"))
  p.preview = true
  return function() shown(); across(); up(); far(); friends(); loop() end
end

BUILD.targetkey = function(p, ui)
  local function o() return ns.Options().targetKey end
  local shows = {}
  local function Add(y, key, label, words)
    shows[#shows + 1] = Check(p, ui, 0, y, label, function() return o()[key] end,
      function(v) o()[key] = v; Changed(); p.Refresh() end, words)
  end
  Heading(p, ui, Word("game.options.target-key.where"), Word("game.options.target-key.where.help"))
  Add(-52, "world", Word("game.options.target-key.world"))
  Add(-74, "dungeons", Word("game.options.target-key.dungeons"), Word("game.options.target-key.dungeons.help"))
  Add(-122, "cardHidden", Word("game.options.target-key.card-hidden"), Word("game.options.target-key.card-hidden.help"))
  Add(-158, "flights", Word("game.options.target-key.flights"), Word("game.options.target-key.flights.help"))
  local warn = ui.Text(p, "GameFontHighlight", ui.C.red)
  warn:SetPoint("TOPLEFT", 0, -196)
  warn:SetWidth(PAGE_W)
  warn:SetText(Word("game.options.target-key.none"))
  ns.optionsKeyWarn = warn
  Heading(p, ui, Word("game.options.target-key.talk"), Word("game.options.target-key.talk.help"), -236)
  Add(-326, "mark", Word("game.options.target-key.mark"))
  return function()
    for _, show in ipairs(shows) do show() end
    warn:SetShown(not (o().world or o().dungeons))
  end
end

local function Preview(on)
  if (ns.platePreview or false) == on then return end
  ns.platePreview = on
  Changed()
end

local function Build()
  local ui = ns.UI
  local C = ui.C
  win = ui.Panel(CreateFrame("Frame", "IndexOfAzerothOptions", UIParent, "BackdropTemplate"))
  win:SetFrameStrata("DIALOG")
  win:SetToplevel(true)
  win:SetSize(W, H)
  win:SetPoint("CENTER", UIParent, "CENTER", 0, 60)
  win:SetMovable(true)
  win:SetClampedToScreen(true)
  win:EnableMouse(true)
  win:Hide()
  win:SetScript("OnHide", function() Preview(false) end)
  tinsert(UISpecialFrames, "IndexOfAzerothOptions")
  local head = CreateFrame("Frame", nil, win)
  head:SetPoint("TOPLEFT")
  head:SetPoint("TOPRIGHT")
  head:SetHeight(HEAD_H)
  head:EnableMouse(true)
  head:RegisterForDrag("LeftButton")
  head:SetScript("OnDragStart", function() win:StartMoving() end)
  head:SetScript("OnDragStop", function() win:StopMovingOrSizing() end)
  local title = ui.Text(head, "GameFontHighlightLarge", C.ivory)
  title:SetPoint("LEFT", 12, 0)
  title:SetText(Word("game.options.window.title"))
  local close = ui.FlatButton(head, "x", 20, function() win:Hide() end)
  close:SetSize(20, 20)
  close:SetPoint("TOPRIGHT", -6, -6)
  local y = -HEAD_H - 6
  for _, cat in ipairs(TREE) do
    local label = ui.Text(win, "GameFontNormalSmall", C.muted)
    label:SetPoint("TOPLEFT", 12, y)
    label:SetText(cat.name:upper())
    y = y - 16
    for _, pg in ipairs(cat.pages) do
      local row = ui.FlatButton(win, pg.name, TREE_W - 12, function() ns.ShowOptionsPage(pg.key) end)
      row:SetHeight(ROW_H)
      row:SetPoint("TOPLEFT", 10, y)
      row.label:ClearAllPoints()
      row.label:SetPoint("LEFT", 10, 0)
      rows[pg.key] = row
      y = y - ROW_H - 4
    end
    y = y - 8
  end
  local rule = win:CreateTexture(nil, "ARTWORK")
  rule:SetColorTexture(C.dim[1], C.dim[2], C.dim[3], 1)
  rule:SetWidth(1)
  rule:SetPoint("TOPLEFT", TREE_W + 4, -HEAD_H - 6)
  rule:SetPoint("BOTTOMLEFT", TREE_W + 4, 10)
end

local function Page(key)
  if pages[key] then return pages[key] end
  local p = CreateFrame("Frame", nil, win)
  p:SetPoint("TOPLEFT", TREE_W + 18, -HEAD_H - 6)
  p:SetPoint("BOTTOMRIGHT", -12, 10)
  p:Hide()
  pages[key] = p
  p.Refresh = BUILD[key](p, ns.UI)
  return p
end

function ns.ShowOptionsPage(key)
  if not BUILD[key] then key = "nameplates" end
  if not win then Build() end
  current = key
  if type(IndexOfAzerothDB) == "table" then IndexOfAzerothDB.optionsPage = key end
  for k, row in pairs(rows) do row:SetSelected(k == key) end
  for k, p in pairs(pages) do if k ~= key then p:Hide() end end
  local p = Page(key)
  p.Refresh()
  win:Show()
  p:Show()
  Preview(p.preview or false)
end

function ns.ToggleOptions(key)
  if win and win:IsShown() and (not key or key == current) then return win:Hide() end
  ns.ShowOptionsPage(key or current or (type(IndexOfAzerothDB) == "table" and IndexOfAzerothDB.optionsPage) or "nameplates")
end
ns.optionsWindow = function() return win end
ns.OptionsLayout = function() return PAGE_W, CONTROL_X, SLIDER_W, VALUE_W end

local NAV_SWITCHES = { compass = { { "compass" }, Word("game.chat.switch.name.compass") },
  beacons = { { "beacons" }, Word("game.chat.switch.name.beacons") }, arrows = { { "arrows" }, Word("game.chat.switch.name.arrows") },
  lines = { { "line", "mapLine" }, Word("game.chat.switch.name.lines") } }
function ns.SwitchWords(name, on, command)
  if on then return Word("game.chat.switch.on", { name = name }) end
  return Word("game.chat.switch.off", { name = name, command = command })
end
function ns.Switch(command, arg)
  local nav, s = ns.Options().nav, NAV_SWITCHES[command]
  local any = false
  for _, key in ipairs(s[1]) do any = any or nav[key] end
  local on = arg == "on" or (arg ~= "off" and not any)
  for _, key in ipairs(s[1]) do nav[key] = on end
  Changed()
  if win and win:IsShown() and current and pages[current] then pages[current].Refresh() end
  ns.Print(ns.SwitchWords(s[2], on, command))
  return on
end
IndexOfAzerothOptions_Toggle = function() ns.ToggleOptions() end
IndexOfAzerothSwitch = function(command) ns.Switch(command) end
BINDING_NAME_INDEXOFAZEROTH_OPTIONS = Word("game.key-bindings.options")
BINDING_NAME_INDEXOFAZEROTH_COMPASS = Word("game.key-bindings.compass")
BINDING_NAME_INDEXOFAZEROTH_BEACONS = Word("game.key-bindings.beacons")
BINDING_NAME_INDEXOFAZEROTH_ARROWS = Word("game.key-bindings.arrows")
BINDING_NAME_INDEXOFAZEROTH_LINES = Word("game.key-bindings.lines")
