-- The Index of Azeroth. Copyright 2026 Index Case <indexofazeroth@pm.me>. PolyForm Strict 1.0.0, see LICENSE.md.
local ADDON, ns = ...

local UI = ns.UI
local C, Text, Circle = UI.C, UI.Text, UI.Circle
local Plain, Call = ns.Plain, ns.Call
local ui = ns.guideUI

local COMPASS_W, COMPASS_H, COMPASS_FADE = 420, 30, 64
local COMPASS_SPAN = math.rad(126)
local COMPASS_TICK = math.rad(15)
local COMPASS_WORDS = { "N", "NE", "E", "SE", "S", "SW", "W", "NW" }
local ARROW_ART = "Interface\\AddOns\\IndexOfAzeroth\\Media\\arrow"

local compass = CreateFrame("Frame", "IndexOfAzerothCompass", UIParent)
compass:SetSize(COMPASS_W, COMPASS_H + 22)
compass:SetPoint("TOP", UIParent, "TOP", 0, -6)
compass:SetClampedToScreen(true)
compass:EnableMouse(true)
compass:RegisterForDrag("LeftButton")
compass:Hide()
local drag = { NEAR = 120, PULL = 24, LINE_W = 2, LINE_ALPHA = 0.6 }
drag.line = CreateFrame("Frame", "IndexOfAzerothCompassLine", UIParent)
drag.line:SetFrameStrata("LOW")
drag.line:SetWidth(drag.LINE_W)
drag.line:SetPoint("TOP", UIParent, "TOP", 0, 0)
drag.line:SetPoint("BOTTOM", UIParent, "BOTTOM", 0, 0)
drag.line.art = drag.line:CreateTexture(nil, "ARTWORK")
drag.line.art:SetAllPoints()
drag.line.art:SetColorTexture(C.ivory[1], C.ivory[2], C.ivory[3], drag.LINE_ALPHA)
drag.line:Hide()
function drag.Place(left, top)
  local off = math.abs(left + compass:GetWidth() / 2 - UIParent:GetWidth() / 2)
  compass:ClearAllPoints()
  if off <= drag.PULL then
    compass:SetPoint("TOP", UIParent, "BOTTOM", 0, top)
  else
    compass:SetPoint("TOPLEFT", UIParent, "BOTTOMLEFT", left, top)
  end
  drag.line:SetShown(off <= drag.NEAR)
  return off <= drag.PULL
end
function drag.Follow()
  local x, y = UI.Cursor()
  if x and drag.from then drag.on = drag.Place(x - drag.from[1], y - drag.from[2]) end
end
compass:SetScript("OnDragStart", function(self)
  local x, y = UI.Cursor()
  local left, top = self:GetLeft(), self:GetTop()
  if not (x and left and top) then return end
  drag.from, drag.on = { x - left, y - top }, false
  drag.Follow()
end)
compass:SetScript("OnDragStop", function(self)
  if not drag.from then return end
  drag.Follow()
  drag.from = nil
  drag.line:Hide()
  local left, top = self:GetLeft(), self:GetTop()
  if not (left and top) then return end
  ns.GuideSaved().compassPos = { left, top, center = drag.on or nil }
  ui.PlaceCompass()
end)
function drag.Tick()
  if not drag.from then return end
  if compass:IsShown() then drag.Follow() else compass:GetScript("OnDragStop")(compass) end
end
ns.compassDrag = drag
function ui.PlaceCompass()
  local pos = ns.GuideSaved().compassPos
  if type(pos) ~= "table" then return end
  compass:ClearAllPoints()
  if pos.center then
    compass:SetPoint("TOP", UIParent, "BOTTOM", 0, pos[2] or 0)
  else
    compass:SetPoint("TOPLEFT", UIParent, "BOTTOMLEFT", pos[1] or 0, pos[2] or 0)
  end
end

local function Band(x, w, from, to)
  local t = compass:CreateTexture(nil, "BACKGROUND")
  t:SetPoint("TOPLEFT", x, 0)
  t:SetSize(w, COMPASS_H)
  t:SetColorTexture(1, 1, 1, 1)
  if not pcall(t.SetGradient, t, "HORIZONTAL", CreateColor(0, 0, 0, from), CreateColor(0, 0, 0, to)) then
    t:SetColorTexture(0, 0, 0, (from + to) / 2)
  end
end
Band(0, COMPASS_FADE, 0, 0.55)
Band(COMPASS_FADE, COMPASS_W - 2 * COMPASS_FADE, 0.55, 0.55)
Band(COMPASS_W - COMPASS_FADE, COMPASS_FADE, 0.55, 0)
local ticks, words = {}, {}
for k = 1, 12 do
  ticks[k] = compass:CreateTexture(nil, "ARTWORK")
  ticks[k]:SetColorTexture(C.muted[1], C.muted[2], C.muted[3], 0.9)
end
for k, w in ipairs(COMPASS_WORDS) do
  words[k] = Text(compass, "GameFontNormalSmall", C.ivory, "CENTER")
  words[k]:SetText(w)
end
local function Mark(color, tinted, font)
  local m = compass:CreateTexture(nil, "OVERLAY")
  m:SetSize(14, 14)
  m:SetTexture(ARROW_ART)
  m:SetRotation(math.pi)
  if tinted then m:SetDesaturated(true); m:SetVertexColor(color[1], color[2], color[3]) end
  return m, Text(compass, font, color, "CENTER")
end
local stepMark, stepWords = Mark(C.blue, true, "GameFontNormal")
local rideMark, rideWords = Mark(C.cyan, true, "GameFontNormalSmall")
local more = { alpha = 0.5, fade = 24 }
more.MARK_SIZE = 10
more.navMark, more.navWords = Mark(C.gold, false, "GameFontNormal")
more.NAV_MARK_ART = "Interface\\AddOns\\IndexOfAzeroth\\Media\\beacon_"
function more.NavMarkLook(look)
  if look ~= more.navLook then
    more.navLook = look
    local c, own = UI.GUIDE[look], look ~= "go"
    more.navMark:SetTexture(own and (more.NAV_MARK_ART .. look) or ARROW_ART)
    more.navMark:SetRotation(own and 0 or math.pi)
    more.navMark:SetSize(own and 18 or 14, own and 18 or 14)
    more.navWords:SetTextColor(c[1], c[2], c[3])
    UI.Mark(more.navMark, look, more.MARK_SIZE, compass)
  end
  return look
end
function more.MarkWith(mark, shown)
  local h = mark.mark
  if not h then return end
  h:SetShown(shown and UI.MARKS[h.look] ~= nil)
  h:SetAlpha(shown and (mark:GetAlpha() or 1) or 0)
end
ns.GuideCompassNav = function() return more.navMark, more.navWords end
more.loopRideMark, more.loopRideWords = Mark(C.cyan, true, "GameFontNormalSmall")
more.rideName = Text(compass, "GameFontNormal", C.gold, "CENTER")
more.rideName:SetPoint("CENTER", compass, "TOP", 0, -COMPASS_H / 2)
more.rideLine = Text(compass, "GameFontHighlightSmall", C.ivory, "CENTER")
more.rideLine:SetPoint("TOP", compass, "TOP", 0, -COMPASS_H - 3)
more.rideName:Hide(); more.rideLine:Hide()
function more.NewGlow()
  return { compass:CreateTexture(nil, "BORDER"), compass:CreateTexture(nil, "BORDER"), compass:CreateTexture(nil, "BORDER"),
           words = Text(compass, "GameFontNormalSmall", C.ivory, "CENTER") }
end
more.glow, more.campGlow = more.NewGlow(), more.NewGlow()
more.lostLines = {
  "A night elf scout says your beacons are behind you. Turn round to see them again.",
  "A dwarf rifleman lost sight of your beacons too. Turn round and they show again.",
  "A gnome is looking for your beacons the wrong way as well. Turn round to find them.",
  "An orc grunt says your beacons are where you aren't looking. Turn round.",
  "A Tauren elder asks you to face the road. Your beacons are on it.",
  "A troll says your beacons are over your shoulder, mon. Turn round to see them.",
  "A goblin will sell you directions. Turning round to find your beacons is free.",
  "A Stormwind guard has seen your beacons behind you. Turn round to see them.",
  "A kobold went looking for your beacons with his candle. Turn round and you will find them first.",
  "Brann Bronzebeard never reads a map standing still. Turn round and your beacons come back.",
}
more.lostFrame = CreateFrame("Frame", nil, UIParent)
more.lostFrame:SetAllPoints(compass)
more.lostFrame:Hide()
more.lostText = Text(more.lostFrame, "GameFontHighlightSmall", C.ivory, "CENTER")
ns.GuideLostText = more.lostText
more.lostText:SetPoint("TOP", compass, "TOP", 0, -COMPASS_H - 20)
more.lostText:SetAlpha(0.8)
more.lostText:Hide()
function more.HideGlow(set)
  for _, t in ipairs(set) do t:Hide() end
  set.words:Hide()
end
function more.Glow(set, x0, x1, colour, alpha)
  if set.x0 == x0 and set.x1 == x1 and set.colour == colour and set.alpha == alpha and set[1]:IsShown() then return end
  set.x0, set.x1, set.colour, set.alpha = x0, x1, colour, alpha
  local fade = math.min(more.fade, (x1 - x0) / 3)
  local r, g, b = colour[1], colour[2], colour[3]
  if not set.from then
    set.from, set.to = {}, {}
    for k = 1, 3 do set.from[k], set.to[k] = CreateColor(r, g, b, 0), CreateColor(r, g, b, 0) end
  end
  for k = 1, 3 do
    local at, w, a0, a1 = x0, fade, 0, alpha
    if k == 2 then
      at, w, a0 = x0 + fade, x1 - x0 - 2 * fade, alpha
    elseif k == 3 then
      at, a0, a1 = x1 - fade, alpha, 0
    end
    local t = set[k]
    t:ClearAllPoints()
    t:SetPoint("TOPLEFT", compass, "TOPLEFT", COMPASS_W / 2 + at, 0)
    t:SetSize(math.max(w, 1), COMPASS_H)
    t:SetColorTexture(1, 1, 1, 1)
    set.from[k]:SetRGBA(r, g, b, a0)
    set.to[k]:SetRGBA(r, g, b, a1)
    if not pcall(t.SetGradient, t, "HORIZONTAL", set.from[k], set.to[k]) then
      t:SetColorTexture(r, g, b, (a0 + a1) / 2)
    end
    t:Show()
  end
end
more.HideGlow(more.glow); more.HideGlow(more.campGlow)

local function Wrap(a) return (a + math.pi) % (2 * math.pi) - math.pi end

function more.LoopBand(set, ring, colour, px, py, mid, words, look)
  local half, per = COMPASS_SPAN / 2, COMPASS_W / COMPASS_SPAN
  local cx, cy = 0, 0
  for _, p in ipairs(ring.loop) do cx, cy = cx + p[1], cy + p[2] end
  cx, cy = cx / #ring.loop, cy / #ring.loop
  local toMid = math.atan2(-(cy - py), cx - px)
  local lo, hi = 0, 0
  for _, p in ipairs(ring.loop) do
    local a = Wrap(math.atan2(-(p[2] - py), p[1] - px) - toMid)
    lo, hi = math.min(lo, a), math.max(hi, a)
  end
  local l, r, alpha = -half, half, more.alpha
  if hi - lo <= math.pi then
    local at = Wrap(toMid - mid)
    l, r = at + lo, at + hi
    if r < -half or l > half then
      local side = (r < -half) and -1 or 1
      l, r, alpha = side * half - (side > 0 and 16 / per or 0), side * half + (side < 0 and 16 / per or 0), more.alpha / 2
    end
    l, r = math.max(-half, l), math.min(half, r)
  end
  more.Glow(set, l * per, r * per, colour, alpha)
  if words then
    local _, _, near = ns.NearestOnLoop(ring, px, py)
    set.words:ClearAllPoints()
    set.words:SetPoint("TOP", compass, "TOPLEFT", COMPASS_W / 2 + (l + r) / 2 * per, -COMPASS_H - 3)
    more.Say(set.words, near and near > 25 and near or "on it", UI.MarkText(look))
    set.words:SetTextColor(unpack(colour))
    set.words:Show()
  else
    set.words:Hide()
  end
  return { l * per, r * per }
end

function more.Say(label, words, pre)
  if type(words) == "number" then words = math.floor(words) end
  if label.said ~= words or label.saidPre ~= pre then
    label.said, label.saidPre = words, pre
    label:SetText((pre or "") .. (type(words) == "number" and string.format("%d", words) or words))
  end
end

function more.Place(mark, label, px, py, mid, wx, wy, words)
  local half, per = COMPASS_SPAN / 2, COMPASS_W / COMPASS_SPAN
  local a = Wrap(math.atan2(-(wy - py), wx - px) - mid)
  local x = math.max(-half, math.min(half, a)) * per
  local seen = math.abs(a) <= half
  mark:ClearAllPoints()
  mark:SetPoint("TOP", compass, "TOPLEFT", COMPASS_W / 2 + x, 2)
  mark:SetAlpha(seen and 1 or 0.5)
  mark:Show()
  label:ClearAllPoints()
  label:SetPoint("TOP", compass, "TOPLEFT", COMPASS_W / 2 + x, -COMPASS_H - 3)
  more.Say(label, words)
  label:SetAlpha(seen and 1 or 0.5)
  label:Show()
  return x, seen
end

more.RIDERS = { "e", "g", "h", "k" }
function more.RideOn(continent, px, py)
  if ns.Ghost() then return nil end
  local g = ns.GuideTarget and ns.GuideTarget()
  local ride = g and g.route and g.route:UnderWay(continent, px, py)
  if ride then return ride, g.route end
  for _, kind in ipairs(more.RIDERS) do
    local t = ns.TrackTarget(kind)
    ride = t and t.route and t.route:UnderWay(continent, px, py)
    if ride then return ride, t.route end
  end
end

more.PLACE_SIZE, more.PLACE_LOOK = 16, 1
more.PLACE_ART = "Interface\\AddOns\\IndexOfAzeroth\\Media\\compass_"
more.PLACE_KIND = { city = "capital", town = "town", dungeon = "dungeon", raid = "raid", area = "area" }
more.FACED = math.rad(7.5)
more.NAME_ROOM = 70
more.placeMarks, more.markXs = {}, {}
more.placeName = Text(compass, "GameFontNormalSmall", C.ivory, "CENTER")
more.placeName:Hide()
ns.GuideCompassPlaces = function() return more.placeMarks, more.placeName end

function more.ZonePlaces(continent, px, py)
  if not ns.Options().nav.places then return nil end
  local all = type(IndexOfAzerothShared) == "table" and IndexOfAzerothShared.places
  if type(all) ~= "table" then return nil end
  local now = GetTime()
  if more.zoneSeen == nil or now - more.zoneSeen >= more.PLACE_LOOK or more.zoneOn ~= continent then
    more.zoneSeen, more.zoneOn = now, continent
    local zone = ns.Geo.ZoneAt(continent, px, py)
    more.zoneKey = zone and tostring(zone)
  end
  local here = more.zoneKey and all[more.zoneKey]
  if type(here) ~= "table" or here.inst ~= continent or type(here.at) ~= "table" or not here.at[1] then return nil end
  return here.at
end

function more.PlaceArt(t, p)
  local art = more.PLACE_KIND[p.k] or more.PLACE_KIND.area
  t:SetSize(more.PLACE_SIZE, more.PLACE_SIZE)
  t:SetTexture(more.PLACE_ART .. art)
  return art
end

function more.HidePlaces()
  for _, m in ipairs(more.placeMarks) do m:Hide() end
  more.placeName:Hide()
end

function more.Places(list, px, py, mid, marks)
  local half, per = COMPASS_SPAN / 2, COMPASS_W / COMPASS_SPAN
  local n, faced, near, at = 0, nil, more.FACED, 0
  for _, p in ipairs(list) do
    if type(p) == "table" and type(p.x) == "number" and type(p.y) == "number" then
      local a = Wrap(math.atan2(-(p.y - py), p.x - px) - mid)
      if math.abs(a) <= half then
        n = n + 1
        local m = more.placeMarks[n]
        if not m then
          m = compass:CreateTexture(nil, "ARTWORK")
          more.placeMarks[n] = m
        end
        if m.place ~= p then m.place, m.art = p, more.PlaceArt(m, p) end
        m.x = a * per
        m:ClearAllPoints()
        m:SetPoint("CENTER", compass, "TOPLEFT", COMPASS_W / 2 + m.x, -COMPASS_H / 2 - 4)
        m:Show()
        if math.abs(a) <= near then faced, near, at = p, math.abs(a), m.x end
      end
    end
  end
  for k = n + 1, #more.placeMarks do more.placeMarks[k]:Hide() end
  for _, x in pairs(marks) do
    if faced and math.abs(x - at) < more.NAME_ROOM then faced = nil end
  end
  if faced then
    more.placeName:ClearAllPoints()
    more.placeName:SetPoint("TOP", compass, "TOPLEFT", COMPASS_W / 2 + at, -COMPASS_H - 3)
    more.Say(more.placeName, faced.n)
    more.placeName:Show()
  else
    more.placeName:Hide()
  end
  return n
end

more.MARKS = { stepMark, stepWords, rideMark, rideWords, more.navMark, more.navWords, more.loopRideMark, more.loopRideWords }
function more.Riding(ride, route, continent, px, py, lost)
  compass:Show()
  for _, t in ipairs(ticks) do t:Hide() end
  for _, w in ipairs(words) do w:Hide() end
  for _, m in ipairs(more.MARKS) do m:Hide() end
  more.MarkWith(more.navMark, false); more.MarkWith(more.loopRideMark, false)
  more.HideGlow(more.glow); more.HideGlow(more.campGlow)
  more.HidePlaces()
  local name, zone, yards = route:Destination(continent, px, py)
  local whole = yards and math.floor(yards)
  if name ~= more.rideTo or zone ~= more.rideIn or whole ~= more.rideLeft then
    more.rideTo, more.rideIn, more.rideLeft = name, zone, whole
    more.rideName:SetText(name or "")
    more.rideLine:SetText((zone or "") .. ((zone and whole) and "  |  " or "") .. (whole and string.format("%d yd", whole) or ""))
  end
  more.rideName:Show(); more.rideLine:Show()
  return { riding = name, rideKind = ride.kind, rideZone = zone, rideYards = whole, lost = lost }
end

function ui.Compass()
  local g = ns.GuideInfo() or (ns.PastedGuide and ns.PastedGuide())
  local s = g and g.cur and g.steps[g.cur]
  local continent, px, py = ns.PlayerWorldPos()
  local facing = Plain(Call(GetPlayerFacing))
  local nav = ns.GuideTarget and ns.GuideTarget()
  local loopKind = (ns.TrackTarget("g") and "g") or (ns.TrackTarget("h") and "h") or (ns.TrackTarget("k") and "k") or nil
  local loop = loopKind and ns.TrackTarget(loopKind)
  local t = ns.TrackTarget("e")
  if ns.Ghost() then s, loop, t, nav = nil, nil, nil, ns.CorpseRun() end
  local lost = more.Lost()
  local riding, route = more.RideOn(continent, px, py)
  if riding and ns.NavOn("compass") then return more.Riding(riding, route, continent, px, py, lost) end
  more.rideName:Hide(); more.rideLine:Hide()
  local places = continent and not ns.Ghost() and more.ZonePlaces(continent, px, py)
  if not (s or (nav and nav.wx) or (loop and loop.loop) or places) or not continent or not facing
      or not ns.NavOn("compass") then
    compass:Hide()
    more.MarkWith(more.navMark, false); more.MarkWith(more.loopRideMark, false)
    more.HidePlaces()
    return nil
  end
  compass:Show()
  local half, per = COMPASS_SPAN / 2, COMPASS_W / COMPASS_SPAN
  local mid = -facing
  local out = {}
  local n = 0
  for k = math.ceil((mid - half) / COMPASS_TICK), math.floor((mid + half) / COMPASS_TICK) do
    local x = Wrap(k * COMPASS_TICK - mid) * per
    n = n + 1
    local t = ticks[n]
    if not t then break end
    local big = k % 3 == 0
    t:SetSize(big and 2 or 1, big and 10 or 6)
    t:ClearAllPoints()
    t:SetPoint("BOTTOM", compass, "TOPLEFT", COMPASS_W / 2 + x, -COMPASS_H)
    t:Show()
  end
  for k = n + 1, #ticks do ticks[k]:Hide() end
  for k, w in ipairs(words) do
    local a = Wrap((k - 1) * math.pi / 4 - mid)
    w:SetShown(math.abs(a) <= half - math.rad(4))
    w:ClearAllPoints()
    w:SetPoint("TOP", compass, "TOPLEFT", COMPASS_W / 2 + a * per, -3)
    local facingIt = math.abs(a) <= math.rad(7.5)
    w:SetTextColor(unpack(facingIt and C.gold or C.ivory))
    if facingIt then out.word = COMPASS_WORDS[k] end
  end
  local camp = ns.GuideAtLoop and ns.GuideAtLoop()
  out.atCamp = camp
  local arrow = t and (t.guided or t.pasted) and t
  if s and s.wx and continent == s.inst and not camp and not (ns.GuideInArea and ns.GuideInArea()) then
    local here = arrow and not arrow.route and arrow.along or ns.Geo.Dist(s.wx, s.wy, px, py)
    out.step, out.stepSeen = more.Place(stepMark, stepWords, px, py, mid, s.wx, s.wy, here)
  else
    stepMark:Hide(); stepWords:Hide()
  end
  local ride = arrow and arrow.route and arrow.route:NextRide()
  local word = ns.RideWord(ride)
  if word and t.continent == continent then
    out.ride, out.rideSeen = more.Place(rideMark, rideWords, px, py, mid, t.wx, t.wy, word)
    out.rideWord = word
  else
    rideMark:Hide(); rideWords:Hide()
  end
  if nav and nav.wx and not nav.wait and nav.continent == continent then
    out.navLook = more.NavMarkLook(ns.NavLook(nav))
    local navWord = ns.RideWord(nav.route and nav.route:NextRide())
    local yards = not navWord and (nav.along or ns.Geo.Dist(nav.wx, nav.wy, px, py)) or nil
    out.nav, out.navSeen = more.Place(more.navMark, more.navWords, px, py, mid, nav.wx, nav.wy, navWord or yards)
    out.navWord, out.navYards = navWord, yards
    more.MarkWith(more.navMark, true)
  else
    more.navMark:Hide(); more.navWords:Hide()
    more.MarkWith(more.navMark, false)
  end
  local look = loop and (loop.look or loopKind)
  local colour = look and UI.GUIDE[look] or C.cyan
  if loop and loop.loop and #loop.loop > 1 and loop.continent == continent then
    out.loop = more.LoopBand(more.glow, loop, colour, px, py, mid, true, look)
  else
    more.HideGlow(more.glow)
  end
  local loopWord = loop and loop.route and loop.wx and loop.continent == continent and ns.RideWord(loop.route:NextRide())
  if loopWord then
    more.loopRideMark:SetVertexColor(colour[1], colour[2], colour[3])
    more.loopRideWords:SetTextColor(colour[1], colour[2], colour[3])
    out.loopRide, out.loopRideSeen = more.Place(more.loopRideMark, more.loopRideWords, px, py, mid, loop.wx, loop.wy, loopWord)
    out.loopRideWord = loopWord
    UI.Mark(more.loopRideMark, look, more.MARK_SIZE, compass)
    more.MarkWith(more.loopRideMark, true)
  else
    more.loopRideMark:Hide(); more.loopRideWords:Hide()
    more.MarkWith(more.loopRideMark, false)
  end
  if s and s.loop and #s.loop > 1 and continent == s.inst then
    out.camp = more.LoopBand(more.campGlow, s, C.blue, px, py, mid, camp)
  else
    more.HideGlow(more.campGlow)
  end
  if places then
    local xs = more.markXs
    xs[1], xs[2], xs[3], xs[4] = out.step, out.ride, out.nav, out.loopRide
    out.places = more.Places(places, px, py, mid, xs)
  else
    more.HidePlaces()
  end
  out.lost = lost
  return out
end

function more.Lost()
  if ns.BeaconsLost and ns.BeaconsLost() then
    more.lostLine = more.lostLine or more.lostLines[math.random(#more.lostLines)]
    more.lostText:SetText(more.lostLine)
    more.lostText:Show()
    more.lostFrame:Show()
    return more.lostLine
  end
  more.lostLine = nil
  more.lostText:Hide()
  more.lostFrame:Hide()
end
ns.GuideCompass = ui.Compass

more.SLOT_W, more.BAND_H, more.ART_SIZE = 140, 74, 40
more.SIZES, more.CLOSER = { 1, 0.84, 0.76 }, 0.95
more.GLOW_ART = "Interface\\AddOns\\IndexOfAzeroth\\Media\\rim_glow"

function more.Slot(s)
  local f, c = s.frame, s.colour
  f:SetParent(more.band)
  f:SetUserPlaced(false)
  f:SetSize(more.SLOT_W, more.BAND_H)
  f:SetScale(1)
  local plate = s.arrows[1]
  for _, t in ipairs(s.arrows) do
    t:ClearAllPoints()
    t:SetPoint("TOP", f, "TOP", 0, 0)
    t:SetSize(more.ART_SIZE, more.ART_SIZE)
    t:SetTexture(s.art)
    t:SetDesaturated(false)
    t:SetVertexColor(1, 1, 1)
  end
  s.glow = f:CreateTexture(nil, "OVERLAY")
  s.glow:SetTexture(more.GLOW_ART)
  s.glow:SetSize(more.ART_SIZE * 1.3, more.ART_SIZE * 1.3)
  s.glow:SetPoint("CENTER", plate, "CENTER")
  s.glow:SetBlendMode("ADD")
  s.glow:SetVertexColor(c[1], c[2], c[3])
  s.glow:Hide()
  function s.Glow(turn)
    if turn then s.glow:SetRotation(turn) end
    s.glow:SetShown(turn ~= nil)
  end
  s.pulse = CreateFrame("Frame", nil, f)
  s.pulse:SetSize(more.ART_SIZE, more.ART_SIZE)
  s.pulse:SetPoint("CENTER", plate, "CENTER")
  s.pulseLines = Circle(s.pulse, 32, 24, 1.5)
  for _, line in ipairs(s.pulseLines) do line:SetColorTexture(c[1], c[2], c[3], 1) end
  s.pulse:Hide()
  function s.Recolour(colour)
    s.glow:SetVertexColor(colour[1], colour[2], colour[3])
    for _, line in ipairs(s.pulseLines) do line:SetColorTexture(colour[1], colour[2], colour[3], 1) end
    s.name:SetTextColor(colour[1], colour[2], colour[3])
  end
  local w = more.SLOT_W - 16
  s.nameBox = s.nameBox or CreateFrame("Frame", nil, f)
  s.nameBox:SetSize(w, 16)
  s.nameBox:ClearAllPoints()
  s.nameBox:SetPoint("TOP", plate, "BOTTOM", 0, 1)
  if s.nameBox.SetClipsChildren then s.nameBox:SetClipsChildren(true) end
  s.nameW = w
  s.name:SetParent(s.nameBox)
  s.name:ClearAllPoints()
  s.name:SetPoint("CENTER", s.nameBox, "CENTER", 0, 0)
  s.name:SetWidth(0)
  s.name:SetWordWrap(false)
  s.name:SetTextColor(c[1], c[2], c[3])
  ns.OnTick(s.nameBox, "a compass mark's name", nil, function(_, dt) more.ScrollName(s, dt) end)
  s.dist:ClearAllPoints()
  s.dist:SetPoint("TOP", s.nameBox, "BOTTOM", 0, -1)
  s.dist:SetWidth(w)
  s.dist:SetJustifyH("CENTER")
  s.dist:SetWordWrap(false)
  if s.label then s.label:Hide() end
  s.heightText:ClearAllPoints()
  s.heightText:SetPoint("RIGHT", plate, "LEFT", -4, 0)
  s.heightIcon:ClearAllPoints()
  s.heightIcon:SetPoint("RIGHT", s.heightText, "LEFT", -1, 0)
  s.heightIcon:SetSize(12, 12)
  s.close:ClearAllPoints()
  s.close:SetPoint("CENTER", plate, "TOPRIGHT", -2, -4)
  s.close:SetSize(14, 14)
  f:SetScript("OnDragStart", function()
    local start = compass:GetScript("OnDragStart")
    if start then start(compass) end
  end)
  f:SetScript("OnDragStop", function()
    local stop = compass:GetScript("OnDragStop")
    if stop then stop(compass) end
  end)
  f:HookScript("OnShow", function() more.LayoutBand() end)
  f:HookScript("OnHide", function() more.LayoutBand() end)
  f:HookScript("OnEnter", function(self)
    GameTooltip:SetOwner(self, "ANCHOR_BOTTOM")
    local now = s.colour
    GameTooltip:AddLine(s.name:GetText() or "", now[1], now[2], now[3], true)
    local d, h = s.dist:GetText() or "", s.heightText:GetText() or ""
    if d ~= "" then GameTooltip:AddLine(d, 1, 1, 1, true) end
    if h ~= "" then GameTooltip:AddLine(h, now[1], now[2], now[3]) end
    ns.CarefulTip(GameTooltip, s.Careful and s.Careful())
    GameTooltip:AddLine(s.hint, unpack(C.muted))
    GameTooltip:Show()
  end)
  f:HookScript("OnLeave", function() GameTooltip:Hide() end)
end

more.NAME_HOW = { rest = 3, speed = 30, hold = 1.5, back = false }
function more.ScrollName(s, dt)
  local text = s.name:GetText() or ""
  local full = (s.name.GetUnboundedStringWidth and s.name:GetUnboundedStringWidth()) or s.name:GetStringWidth() or 0
  if text ~= s.scrollText then
    s.scrollText, s.scrollSlide, s.scrollX = text, {}, 0
  end
  local over = full - (s.nameW or full)
  if over <= 0 then
    if s.scrollX ~= nil and not s.scrollFits then
      s.name:ClearAllPoints()
      s.name:SetPoint("CENTER", s.nameBox, "CENTER", 0, 0)
    end
    s.scrollFits, s.scrollSlide, s.scrollX = true, {}, 0
    return
  end
  s.scrollFits = nil
  s.scrollX = UI.SlideAlong(s.scrollSlide, over, dt, more.NAME_HOW)
  s.name:ClearAllPoints()
  s.name:SetPoint("LEFT", s.nameBox, "LEFT", -s.scrollX, 0)
end

function more.ByDistance(on)
  local d = ns.GuideDistances and ns.GuideDistances() or {}
  local far = function(k) return d[k] or math.huge end
  local order = {}
  for _, k in ipairs(on) do order[#order + 1] = k end
  table.sort(order, function(a, b)
    if far(a) ~= far(b) then return far(a) < far(b) end
    return a < b
  end)
  local was = more.rankOf or {}
  for i = 2, #order do
    local a, b = order[i - 1], order[i]
    if was[a] and was[b] and was[b] < was[a] and far(a) > far(b) * more.CLOSER then order[i - 1], order[i] = b, a end
  end
  local owner = ns.BeaconOwnerSlot and ns.BeaconOwnerSlot()
  for i, k in ipairs(order) do
    if k == owner and i > 1 then table.remove(order, i); table.insert(order, 1, k); break end
  end
  return order
end

function more.Pulse()
  local owner = ns.BeaconOwnerSlot and ns.BeaconOwnerSlot()
  local breath = ns.BeaconBreath and ns.BeaconBreath() or 0.5
  for k, s in pairs(ns.guideSlots or {}) do
    if s.pulse then
      s.pulse:SetShown(k == owner)
      if k == owner then for _, line in ipairs(s.pulseLines) do line:SetAlpha(breath) end end
    end
  end
end
ns.GuideBandPulse = function() more.Pulse() end

function more.LayoutBand()
  local band, slots = more.band, ns.guideSlots or {}
  if not band then return end
  local on = {}
  for _, k in ipairs({ "go", "e", "g", "h", "k" }) do
    if slots[k] and slots[k].frame:IsShown() then on[#on + 1] = k end
  end
  local order = more.ByDistance(on)
  local arrows = ns.Options().nav.arrows and not ns.InDungeon()
  local sig = table.concat(on, ",") .. "|" .. table.concat(order, ",") .. (arrows and "" or "|off")
  if sig == more.bandSig then return end
  more.bandSig = sig
  local scale = {}
  more.rankOf = {}
  for i, k in ipairs(order) do scale[k], more.rankOf[k] = more.SIZES[i] or more.SIZES[#more.SIZES], i end
  local at, epic = {}, slots.e and slots.e.frame:IsShown()
  for i, k in ipairs(on) do
    if epic then at[k] = k == "e" and 0 or k == "go" and -more.SLOT_W or more.SLOT_W
    else at[k] = (i - (#on + 1) / 2) * (COMPASS_W / #on) end
  end
  for k, x in pairs(at) do
    local f = slots[k].frame
    f:ClearAllPoints()
    f:SetScale(scale[k])
    f:SetPoint("TOP", band, "TOP", x / scale[k], 0)
    f:EnableMouse(arrows)
    slots[k].close:EnableMouse(arrows)
  end
  band:SetShown(#on > 0)
  band:SetAlpha(arrows and 1 or 0)
  more.lostText:ClearAllPoints()
  if #on > 0 and arrows then more.lostText:SetPoint("TOP", band, "BOTTOM", 0, -10)
  else more.lostText:SetPoint("TOP", compass, "TOP", 0, -COMPASS_H - 20) end
  more.bandAt, more.bandScale = at, scale
end
ns.GuideBandLayout = function() more.bandSig = nil; more.LayoutBand(); return more.bandAt, more.bandScale end

more.DECLUTTER_OUT, more.DECLUTTER_IN = 1.5, 0.5
more.CAMP_REACH = 0.5
more.FAR_MARGIN = 100
function more.FarOff(k, line)
  local d = ns.GuideDistances and ns.GuideDistances()[k]
  local far = d ~= nil and d > line + (more.nearSlot == k and more.FAR_MARGIN or 0)
  more.nearSlot = not far and k or nil
  return far
end
function more.Declutter(dt)
  more.giveAge = (more.giveAge or 1) + dt
  if more.giveAge >= 0.1 then
    more.giveAge = 0
    local o = ns.Options().nav
    local owner = o.declutter and o.prefer ~= "arrows" and ns.BeaconInCone and ns.BeaconInCone()
      and ns.BeaconOwnerSlot and ns.BeaconOwnerSlot() or nil
    more.giveOwner = owner and not more.FarOff(owner, o.arrowPast) and owner or nil
    more.giveCamp = ns.GuideAtLoop and (ns.GuideAtLoop(more.CAMP_REACH) or ns.GuideInArea())
  end
  local owner, camp = more.giveOwner, more.giveCamp
  for k, s in pairs(ns.guideSlots or {}) do
    local want, a = (k == owner or (camp and k == "e")) and 0 or 1, s.declutter or 1
    if a ~= want then
      a = want < a and math.max(want, a - dt / more.DECLUTTER_OUT) or math.min(want, a + dt / more.DECLUTTER_IN)
      s.declutter = a
      s.frame:SetAlpha(a)
    end
  end
end
ns.GuideDeclutter = function(dt) more.Declutter(dt) end
function ns.GuideArrowGivenWay(k)
  local s = ns.guideSlots and ns.guideSlots[k]
  if s == nil then return false end
  if not ns.Options().nav.arrows then return true end
  return k == more.giveOwner and (s.declutter or 1) < 0.5
end
function more.BuildBand()
  local band = CreateFrame("Frame", "IndexOfAzerothGuideBand", UIParent)
  band:SetSize(COMPASS_W, more.BAND_H)
  band:SetPoint("TOP", compass, "BOTTOM", 0, -4)
  band:Hide()
  ns.OnTick(band, "the guide arrows under the compass", nil, function(_, dt) more.Declutter(dt) end)
  more.band = band
  ns.guideBand = band
  for _, s in pairs(ns.guideSlots or {}) do more.Slot(s) end
  more.LayoutBand()
end
more.BuildBand()
ns.OnOptions(function()
  more.bandSig = nil
  more.LayoutBand()
  ui.Compass()
  if ns.BeaconsApply then ns.BeaconsApply() end
end)

local compassWatch, compassSince = CreateFrame("Frame"), 0
ns.OnTick(compassWatch, "the compass", nil, function(_, dt)
  drag.Tick()
  compassSince = compassSince + dt
  if compassSince < (compass:IsShown() and 0.03 or 0.5) then return end
  more.bandAge = (more.bandAge or 1) + compassSince
  compassSince = 0
  ui.Compass()
  if more.bandAge >= 0.25 then
    more.bandAge = 0
    more.LayoutBand()
  end
  more.Pulse()
end)

function ns.ResetCompass()
  ns.GuideSaved().compassPos = nil
  compass:ClearAllPoints()
  compass:SetPoint("TOP", UIParent, "TOP", 0, -6)
  more.bandSig = nil
  more.LayoutBand()
  ns.Print("The compass is back at the top of the screen.")
end
