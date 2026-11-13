-- The Index of Azeroth. Copyright 2026 Index Case <indexofazeroth@pm.me>. PolyForm Strict 1.0.0, see LICENSE.md.
local ADDON, ns = ...

ns.LINE_FORMAT = 19

local ARRIVE_YARDS = ns.Rules.guide.arrive
local function AtSpot(yards, there) return there and yards <= ARRIVE_YARDS end
local BEND_YARDS = 12
local CUT_YARDS = 4
local ONPATH_YARDS = 25
local REJOIN_COST = 2
local SAME_YARDS = 10
local ICON = "Interface\\AddOns\\IndexOfAzeroth\\Media\\arrow"
local UI = ns.UI

function ns.NewGuideArrow(kind, spec)
  local frame = CreateFrame("Button", spec.frame, UIParent)
  frame:SetSize(spec.size, spec.size)
  frame:SetPoint("TOP", UIParent, "TOP", 0, spec.y)
  frame:SetMovable(true)
  frame:SetClampedToScreen(true)
  frame:RegisterForDrag("LeftButton")
  frame:RegisterForClicks(unpack(spec.clicks))
  frame:SetScript("OnDragStart", frame.StartMoving)
  frame:SetScript("OnDragStop", frame.StopMovingOrSizing)
  frame:Hide()
  local layers, c = {}, spec.text
  for i, a in ipairs(spec.art or {}) do
    local tex = frame:CreateTexture(nil, "ARTWORK", nil, i)
    tex:SetPoint("CENTER")
    tex:SetSize(spec.size * a[1], spec.size * a[1])
    tex:SetTexture(a[3] or ICON)
    tex:SetDesaturated(not a[3])
    tex:SetVertexColor(a[2][1], a[2][2], a[2][3])
    layers[i] = tex
  end
  if not spec.art then
    layers[1] = frame:CreateTexture(nil, "ARTWORK")
    layers[1]:SetAllPoints()
    layers[1]:SetTexture(ICON)
  end
  local label = nil
  if spec.label then
    label = frame:CreateFontString(nil, "OVERLAY", "GameFontNormalSmall")
    label:SetPoint("BOTTOM", frame, "TOP", 0, 2)
    label:SetText(spec.label)
    label:SetTextColor(c[1], c[2], c[3])
  end
  local name = frame:CreateFontString(nil, "OVERLAY", "GameFontNormal")
  name:SetPoint("TOP", frame, "BOTTOM", 0, -2)
  if c then name:SetTextColor(c[1], c[2], c[3]) end
  local dist = frame:CreateFontString(nil, "OVERLAY", "GameFontHighlightSmall")
  dist:SetPoint("TOP", name, "BOTTOM", 0, -2)
  local heightIcon = frame:CreateTexture(nil, "OVERLAY")
  heightIcon:SetSize(16, 16)
  heightIcon:SetPoint("LEFT", frame, "RIGHT", 2, 0)
  heightIcon:SetTexture(ICON)
  if c then
    heightIcon:SetDesaturated(true)
    heightIcon:SetVertexColor(c[1], c[2], c[3])
  end
  heightIcon:Hide()
  local heightText = frame:CreateFontString(nil, "OVERLAY", "GameFontNormalSmall")
  heightText:SetPoint("LEFT", heightIcon, "RIGHT", 2, 0)
  if c then heightText:SetTextColor(c[1], c[2], c[3]) end
  local close = CreateFrame("Button", nil, frame)
  close:SetSize(16, 16)
  close:SetPoint("TOPRIGHT", frame, "TOPRIGHT", 10, 6)
  local closeText = close:CreateFontString(nil, "OVERLAY", "GameFontNormal")
  closeText:SetAllPoints()
  closeText:SetText("x")
  closeText:SetTextColor(0.8, 0.8, 0.8)
  if spec.closeHover then
    close:SetScript("OnEnter", function() closeText:SetTextColor(unpack(UI.C.gold)) end)
    close:SetScript("OnLeave", function() closeText:SetTextColor(0.8, 0.8, 0.8) end)
  end
  local a = { kind = kind, frame = frame, layers = layers, name = name, dist = dist, label = label, close = close }
  function a:Alpha(v)
    for _, t in ipairs(self.layers) do t:SetAlpha(v) end
    if v < 1 then self:Glow(nil) end
  end
  function a:Glow(turn)
    local s = ns.guideSlots and ns.guideSlots[kind]
    if s and s.Glow then s.Glow(turn) end
  end
  function a:Turn(r) for _, t in ipairs(self.layers) do t:SetRotation(r) end end
  function a:Point(facing, px, py, goal, toward)
    local function At(p) return math.atan2(p[2] - py, p[1] - px) - facing end
    local glowGoal = not (ns.Options and ns.Options().nav.aim == "arrow")
    self:Turn(At(glowGoal and toward or goal))
    if toward[1] ~= goal[1] or toward[2] ~= goal[2] then self:Glow(At(glowGoal and goal or toward)) end
  end
  function a:Colour(c, tint, art)
    if self.colour == c and self.art == art then return end
    self.colour, self.art = c, art
    for _, t in ipairs(self.layers) do
      if art then t:SetTexture(art) end
      t:SetDesaturated(tint and true or false)
      t:SetVertexColor(tint and c[1] or 1, tint and c[2] or 1, tint and c[3] or 1)
    end
    name:SetTextColor(c[1], c[2], c[3])
    heightIcon:SetVertexColor(c[1], c[2], c[3])
    heightText:SetTextColor(c[1], c[2], c[3])
    local s = ns.guideSlots[kind]
    s.colour = c
    if art then s.art = art end
    if s.Recolour then s.Recolour(c) end
  end
  function a:Height(words, turn)
    heightIcon:SetShown(words ~= nil)
    if words then heightIcon:SetRotation(turn) end
    heightText:SetText(words or "")
  end
  ns.guideSlots = ns.guideSlots or {}
  ns.guideSlots[kind] = { frame = frame, arrows = layers, name = name, dist = dist, heightIcon = heightIcon,
                          heightText = heightText, close = close, label = label, colour = spec.slot.colour,
                          hint = spec.slot.hint, art = spec.slot.art }
  return a
end

local target
local SOURCE_TYPED, SOURCE_CORPSE = 2, 3
local resume

local function GuideLine(text)
  text = strtrim(text or "")
  local route = text:match("^/ioa%s+[Rr]%s+(.+=.*)$")
  if route then return "r", route end
  local target = text:match("^/ioa%s+[Tt][Aa][Rr][Gg][Ee][Tt]%s+(.+)$")
  if target then return "target", target end
  local kind, track = text:match("^/ioa%s+([EeGgHhKk])%s+(%d+%s+.+)$")
  if kind then return kind:lower(), track end
  local rest = text:match("^/ioa%s+[Gg][Oo]%s+(.+)$") or text:match("^[Gg][Oo]%s+(.+)$")
  if rest and (rest:match("^%d+%s+[%d%.]+[,%s]+[%d%.]+") or rest:match("^%d+%s+%^")) then return "go", rest end
end

function ns.LineCheck(kind, rest)
  local s, check = kind .. " " .. strtrim(rest or ""), 0
  for i = 1, #s do check = (check * 31 + s:byte(i)) % 65536 end
  return check
end

local function PendingGuides()
  local p = IndexOfAzerothPending
  if type(p) ~= "table" then return {} end
  if p.line then return { p } end
  local out = {}
  for _, slot in ipairs({ "go", "loop", "target" }) do
    if type(p[slot]) == "table" and p[slot].line then out[#out + 1] = p[slot] end
  end
  return out
end
local function PendingClosed(char, id)
  return type(char) == "table" and type(char.pendingClosed) == "table" and char.pendingClosed[id] == true
end
local function GoCheck(t) return t and (t.route and t.route.check or t.check) end

local declined = nil
local function Settle(check)
  local char = IndexOfAzerothCharDB
  if type(char) ~= "table" then return end
  local keep = {}
  for _, p in ipairs(PendingGuides()) do
    local kind, rest = GuideLine(p.line)
    if PendingClosed(char, p.id) or (check and kind and ns.LineCheck(kind, rest) == check) then keep[p.id] = true end
  end
  char.pendingClosed = keep
  declined = nil
end
local function Declined()
  if declined then return declined end
  declined = { go = 0, loop = 0, target = 0 }
  for _, p in ipairs(PendingGuides()) do
    local kind, rest = GuideLine(p.line)
    if kind and PendingClosed(IndexOfAzerothCharDB, p.id) then
      declined[(kind == "g" or kind == "h" or kind == "k") and "loop" or kind == "target" and "target" or "go"] = ns.LineCheck(kind, rest)
    end
  end
  return declined
end
ns.PendingSettle = function(check) Settle(check) end

local closed = { n = 0, kind = 0, name = "" }
local CLOSED_KINDS = { go = 1, loop = 2, epic = 3 }
function ns.GuideClosed(kind, name)
  closed.n, closed.kind, closed.name = (closed.n + 1) % 256, CLOSED_KINDS[kind] or 1, name or ""
  ns.guideDirty = true
  if kind == "epic" then return end
  local check = nil
  if kind == "loop" then
    if ns.LoopRunning then check = select(3, ns.LoopRunning()) end
  else
    check = GoCheck(target)
  end
  Settle(check)
end

function ns.DecodeCareful(text)
  local notes = {}
  for note in (text or ""):gmatch("[^;]+") do notes[#notes + 1] = (note:gsub("_", " ")) end
  return #notes > 0 and notes or nil
end
function ns.SayCareful(notes)
  for _, note in ipairs(notes or {}) do ns.Print("|cffff4a3d" .. UI.Icon(UI.WARN_ART) .. note .. "|r") end
end
function ns.CarefulTip(tip, notes)
  if not notes then return end
  for _, note in ipairs(notes) do tip:AddLine(UI.Icon(UI.WARN_ART) .. note, UI.C.red[1], UI.C.red[2], UI.C.red[3], true) end
end

local gold = ns.NewGuideArrow("go", { frame = "IndexOfAzerothArrow", size = 64, y = -140, clicks = { "RightButtonUp" },
  closeHover = true, slot = { colour = UI.GUIDE.go, hint = "Right-click or click the x to close the guide.",
                              art = "Interface\\AddOns\\IndexOfAzeroth\\Media\\slot_guide" } })
local frame, nameText, distText, close = gold.frame, gold.name, gold.dist, gold.close
ns.guideSlots.go.Careful = function() return target and (target.route and target.route.careful or target.careful) end

local function TravelWho(t)
  local route = t and t.route
  if not route then return t and t.npc, t and t.hostile end
  if t.riding then return nil end
  local leg, nxt = route.legs[route.i], route.legs[route.i + 1]
  if leg.npc then return leg.npc, false, true end
  if nxt then return nxt.npc, false, nxt.npc ~= nil end
  return route.npc, route.hostile
end
function ns.GuideNpc(t)
  local who, hostile = TravelWho(t)
  if not hostile then return who end
end
local function PointTarget()
  if not ns.TargetWant then return end
  local who, hostile, flight = TravelWho(target)
  ns.TargetWant("travel", who and { who = who, mobs = hostile and { who } or nil, talk = not hostile, anchor = frame,
    flight = flight, tip = hostile and "Press this to target the mob the guide leads to. A live mob comes first."
      or (flight and ns.FLIGHT_MASTER_TIP or ns.TALK_TIP) } or nil)
end
local function WhoIn(name)
  local mark, rest = (name or ""):match("^([@!])(.+)$")
  if not mark then return name end
  return rest, rest, mark == "!"
end

local Call = ns.Call
local Geo = ns.Geo
local WorldPos, PlayerWorldPos, Dist = Geo.WorldPos, Geo.PlayerWorldPos, Geo.Dist

ns.AFTER_CORPSE = "after your corpse run"
ns.NOT_WHOLE = "That line didn't come through whole. Copy the line from the page again."
function ns.Ghost() return ns.Plain(Call(UnitIsGhost, "player")) and true or false end
function ns.InDungeon()
  local _, kind = Call(IsInInstance)
  kind = ns.Plain(kind)
  return kind == "party" or kind == "raid"
end
function ns.CorpseRun() return target and target.source == SOURCE_CORPSE and ns.Ghost() and target or nil end
function ns.NavLook(t)
  t = t or target
  if not t then return "go" end
  if t.source == SOURCE_CORPSE then return "corpse" end
  local who = t.route and t.route.npc or t.npc
  if who and ns.TargetKeyHolds and ns.TargetKeyHolds() == who then return "npc" end
  return "go"
end
local LOOK_CODES = { go = 0, corpse = 1, npc = 2 }
local LOOP_LOOKS = { g = 1, h = 2, k = 3, xp = 4, farm = 5, mining = 6, herbalism = 7, fishing = 8, treasure = 9 }

local function Behind(t, name)
  resume = t
  ns.guideDirty = true
  ns.Print("Guiding you to " .. (name or t.name) .. " " .. ns.AFTER_CORPSE .. ". The arrow leads you back to your body first.")
  return t
end

local function MapSpot(mapID, continent, wx, wy)
  local x, y = Geo.MapPos(continent, wx, wy, mapID)
  if x then return x * 100, y * 100 end
  return 0, 0
end

local RISE_SHOW = 40
local RISE_LEAST = 4
local CLIMB_YARDS = 3

function ns.RiseHere(path, leg, px, py)
  local a, b = path[leg - 1], path[leg]
  if not (b and b.rise) then return nil end
  if not (a and a.rise) then return b.rise end
  local u, _, _, _, len2 = Geo.NearestOnSegment(a[1], a[2], b[1], b[2], px, py)
  if not (len2 > 0) then u = 1 end
  return a.rise + (b.rise - a.rise) * u
end

local ON_WAY, WAY_BACK, WAY_AHEAD = 12, 20, 45
function ns.HeightAlong(pts, px, py, state)
  if #pts < 2 then return nil end
  local along = { 0 }
  for i = 2, #pts do
    local a, b = pts[i - 1], pts[i]
    local rise = (a[3] and b[3]) and (b[3] - a[3]) or 0
    along[i] = along[i - 1] + math.sqrt((b[1] - a[1]) ^ 2 + (b[2] - a[2]) ^ 2 + rise ^ 2)
  end
  local was = state and (state.along or 0)
  local function Best(lo, hi)
    local best = nil
    for i = 1, #pts - 1 do
      if along[i + 1] >= lo and along[i] <= hi then
        local a, b = pts[i], pts[i + 1]
        local t, _, _, d = Geo.NearestOnSegment(a[1], a[2], b[1], b[2], px, py)
        local at = along[i] + t * (along[i + 1] - along[i])
        local score = d + (was and math.abs(at - was) * 0.1 or 0)
        if d <= ON_WAY and (not best or score < best.score) then
          best = { score = score, at = at, h = (a[3] and b[3]) and (a[3] + t * (b[3] - a[3])) or a[3] or b[3] }
        end
      end
    end
    return best
  end
  local hit = (was and Best(was - WAY_BACK, was + WAY_AHEAD)) or Best(-math.huge, math.huge)
  if not hit then return nil end
  if state then state.along = hit.at end
  return hit.h
end

function ns.RiseWords(rise, yards)
  if not rise or yards > RISE_SHOW or math.abs(rise) < RISE_LEAST then return nil end
  if rise > 0 then return ns.Word("both.rise.above"), 0 end
  return ns.Word("both.rise.below"), math.pi
end

function ns.HeightHint(path, leg, px, py, yards, state)
  if not path or yards > RISE_SHOW then return nil end
  local pts = {}
  for i, p in ipairs(path) do pts[i] = { p[1], p[2], p.rise } end
  local rise = (state and ns.HeightAlong(pts, px, py, state)) or ns.RiseHere(path, leg, px, py)
  return ns.RiseWords(rise, yards)
end

function ns.RiseAlong(t, px, py)
  local path = t and t.path
  if not path then return nil end
  if t.risesOf ~= path then
    local first = #path + 1
    for i = #path, 1, -1 do if path[i].rise then first = i end end
    local pts = {}
    for i = math.max(1, first - 1), #path do pts[#pts + 1] = { path[i][1], path[i][2], path[i].rise } end
    t.risesOf, t.rises, t.risesAt = path, pts, {}
  end
  return ns.HeightAlong(t.rises, px, py, t.risesAt)
end

function ns.CoverStop(path, leg)
  if not path or ns.Plain(Call(IsIndoors)) then return nil end
  for i = math.max(1, leg or 1), #path do
    if path[i].cov then return i end
  end
  return nil
end

function ns.NotBack(path, leg, px, py, level)
  local stop = ns.CoverStop(path, leg) or #path
  while leg < stop do
    local b, c = path[leg], path[leg + 1]
    if level and b.rise and math.abs(b.rise - level) >= RISE_LEAST then break end
    if (b[1] - px) * (c[1] - b[1]) + (b[2] - py) * (c[2] - b[2]) >= 0 then break end
    leg = leg + 1
  end
  return leg
end

function ns.FollowPath(path, leg, px, py)
  local function dist(a, bx, by) return Dist(a[1], a[2], bx, by) end
  local level = ns.RiseHere(path, leg, px, py)
  local function onLevel(p) return not (level and p.rise) or math.abs(p.rise - level) < RISE_LEAST end
  local function climbs(i, j) return path[i] and path[j] and path[i].rise and path[j].rise and math.abs(path[i].rise - path[j].rise) >= 2 end
  local function reach(i)
    if climbs(i - 1, i) or climbs(i, i + 1) then return CLIMB_YARDS end
    local a, b, c = path[i - 1], path[i], path[i + 1]
    if not (a and c) then return BEND_YARDS end
    local ux, uy, vx, vy = b[1] - a[1], b[2] - a[2], c[1] - b[1], c[2] - b[2]
    local lu, lv = math.sqrt(ux * ux + uy * uy), math.sqrt(vx * vx + vy * vy)
    if lu == 0 or lv == 0 then return BEND_YARDS end
    local turn = math.acos(math.max(-1, math.min(1, (ux * vx + uy * vy) / (lu * lv))))
    local s = math.sin(math.min(turn, math.pi / 2))
    return s > 0 and math.min(BEND_YARDS, CUT_YARDS / s) or BEND_YARDS
  end
  local stop = ns.CoverStop(path, leg)
  local best, near, last = leg, dist(path[leg], px, py), #path
  for i = math.max(2, leg), #path do
    if stop and i >= stop then last = i - 1 break end
    if not (onLevel(path[i - 1]) or onLevel(path[i])) then last = i - 1 break end
    local _, _, _, d = Geo.NearestOnSegment(path[i - 1][1], path[i - 1][2], path[i][1], path[i][2], px, py)
    if d < near then best, near = i, d end
  end
  local at, toward, off
  local gi = stop and (stop > leg and stop - 1 or stop) or #path
  local g = path[gi]
  if near <= ONPATH_YARDS or (best == 1 and (path[1][1] - px) * (g[1] - px) + (path[1][2] - py) * (g[2] - py) >= 0) then
    leg = best
    while leg < (stop or #path) and dist(path[leg], px, py) <= reach(leg) and onLevel(path[leg]) do leg = leg + 1 end
    leg = ns.NotBack(path, leg, px, py, level)
    at, toward, off = leg, path[leg], false
  else
    local wx, wy, slope = g[1] - px, g[2] - py, 1 / math.sqrt(REJOIN_COST * REJOIN_COST - 1)
    local cost, rest, jx, jy = REJOIN_COST * dist(g, px, py), 0, nil, nil
    for i = gi + 1, #path do
      cost = cost + dist(path[i], path[i - 1][1], path[i - 1][2])
    end
    at, toward, off = gi, g, true
    for i = #path, math.max(2, leg), -1 do
      local a, b = path[i - 1], path[i]
      local ux, uy = b[1] - a[1], b[2] - a[2]
      local len = math.sqrt(ux * ux + uy * uy)
      if i <= last and len > 0 then
        ux, uy = ux / len, uy / len
        local ox, oy = px - a[1], py - a[2]
        local lo, hi, uw, c = 0, len, ux * wx + uy * wy, ox * wx + oy * wy
        if uw > 0 then lo = math.max(lo, c / uw) elseif uw < 0 then hi = math.min(hi, c / uw) elseif c > 0 then hi = -1 end
        if lo <= hi then
          local t = math.max(lo, math.min(hi, ox * ux + oy * uy + math.abs(ox * uy - oy * ux) * slope))
          local qx, qy = a[1] + ux * t, a[2] + uy * t
          local here = REJOIN_COST * Dist(qx, qy, px, py) + (len - t) + rest
          if here < cost then cost, at, jx, jy = here, i, qx, qy end
        end
      end
      rest = rest + len
    end
    if jx then toward, leg = { jx, jy }, at end
  end
  local along = dist(toward, px, py) + dist(path[at], toward[1], toward[2])
  for i = at + 1, #path do along = along + dist(path[i], path[i - 1][1], path[i - 1][2]) end
  return toward, along, off, leg
end

function ns.ClearArrow(message)
  local look = target and ns.NavLook(target)
  target = nil
  frame:Hide()
  ns.guideDirty = true
  if ns.BeaconFollow then ns.BeaconFollow() end
  PointTarget()
  if message then ns.Print(message) end
  if look then UI.SayStop(look) end
end

local function TakenOver(name)
  if target and (target.route and target.route.name or target.name) ~= name then UI.SayStop(ns.NavLook(target)) end
end

function ns.GuideSource() return target and target.source or 0 end
function ns.GuideTarget() return target end

local function Reached(where)
  Settle(GoCheck(target))
  ns.ClearArrow("You arrived at " .. where .. ".")
end

function ns.ClearArrowTo(dungeonName)
  local name = target and target.name
  if name == dungeonName .. " entrance" or name == dungeonName .. " portal" or name == "Back to " .. dungeonName then
    Reached(dungeonName)
  end
end

function ns.ClearArrowSource(source)
  if target and target.source == source then ns.ClearArrow() end
  if source == SOURCE_CORPSE then
    if resume and not target then
      target = resume
      nameText:SetText(target.name)
      frame:Show()
      ns.guideDirty = true
      ns.Print("Back to guiding you to " .. target.name .. ".")
    end
    resume = nil
  end
end

function ns.SetArrow(mapID, x, y, name, source)
  local continent, wx, wy = WorldPos(mapID, x / 100, y / 100)
  if not continent then return ns.Print(string.format("Map %d has no position for %.1f, %.1f.", mapID, x, y)) end
  local t = { map = mapID, x = x, y = y, name = name ~= "" and name or string.format("%.1f, %.1f", x, y),
              continent = continent, wx = wx, wy = wy, source = source or SOURCE_TYPED }
  if t.source ~= SOURCE_CORPSE and ns.CorpseRun() then return Behind(t) end
  if source == SOURCE_CORPSE and target and target.source ~= SOURCE_CORPSE then resume = target end
  if source ~= SOURCE_CORPSE then TakenOver(t.name) end
  target = t
  nameText:SetText(target.name)
  frame:Show()
  ns.guideDirty = true
  ns.Print("Guiding you to " .. target.name .. ". Right-click the arrow or type /ioa go off to stop the guide.")
  return t
end


local LEG_ARRIVE_YARDS = ns.Rules.guide.board
local JOIN_YARDS = ns.Rules.guide.landed
local WAIT_LEAVE_YARDS = 60
local RIDE_SPEED = 24
local CUT_SHORT = "then copy the line again for the rest"
local RIDES = {
  F = { "Fly to %s", "the flight master", "flight" }, B = { "Take the boat to %s", "the boat to %s", "boat" },
  Z = { "Take the zeppelin to %s", "the zeppelin to %s", "zeppelin" },
  A = { "Take the airship to %s", "the airship to %s", "airship" }, T = { "Take the tram to %s", "the tram to %s", "tram" },
  H = { "Use your Hearthstone (%s)", "%s", "hearth" }, D = { "%s", "%s" }, w = { "Walk to %s", "%s" },
}
function ns.RideText(ride, name) return RIDES[ride.kind][1]:format(ride.text ~= "" and ride.text or name or "") end
function ns.RideWord(ride) return ride and RIDES[ride.kind] and RIDES[ride.kind][3] end
local function Yards(p, px, py) return Dist(p[1], p[2], px, py) end
function ns.RideNowText(ride, route, continent, px, py)
  local _, _, yards = route:Destination(continent, px, py)
  return ns.RideText(ride, route.name) .. " now" .. (yards and string.format(", %d yd left", yards) or "")
end

local Route = {}
Route.__index = Route
function ns.NewRoute(legs) return setmetatable({ legs = legs, i = 1 }, Route) end
function Route:Waiting() return self.legs[self.i].kind ~= "W" end
function Route:RideAt()
  if self.legs[self.i].kind ~= "W" then return self.i end
  local nxt = self.legs[self.i + 1]
  return nxt and nxt.kind ~= "W" and self.i + 1 or nil
end
function Route:NextRide()
  local j = self:RideAt()
  return j and self.legs[j] or nil
end
local CARRIES = { F = true, B = true, Z = true, A = true, T = true }
function Route:UnderWay(continent, px, py)
  local ride = self.legs[self.i]
  if not CARRIES[ride.kind] then return nil end
  if ride.kind == "F" then return ns.Plain(Call(UnitOnTaxi, "player")) and ride or nil end
  local walk = self.legs[self.i - 1]
  local from = walk and walk.kind == "W" and walk.path[#walk.path]
  if not (from and px and continent == walk.continent) then return ride end
  if Yards(from, px, py) <= WAIT_LEAVE_YARDS then
    ride.carried = nil
    return nil
  end
  if not ride.carried and not ns.Plain(Call(IsSwimming)) and not ns.Plain(Call(UnitOnTaxi, "player"))
     and (ns.Geo.Speed() or 0) > RIDE_SPEED then
    ride.carried = true
  end
  return ride.carried and ride or nil
end
function Route:RideNow(continent, px, py)
  local ride = self.legs[self.i]
  if ride.kind == "W" or ride.kind == "F" and not self:UnderWay(continent, px, py) then return nil end
  return ride
end
function ns.RideTurn(route, continent, px, py)
  local lx, ly, lc = route:Landing()
  local facing = ns.Plain(Call(GetPlayerFacing))
  if not (lx and px and facing and lc == continent) then return 0 end
  return math.atan2(ly - py, lx - px) - facing
end
function Route:Boarded(continent, px, py)
  local walk, ride = self.legs[self.i], self.legs[self.i + 1]
  if walk.kind ~= "W" or not ride or ride.kind ~= "F" or not ns.Plain(Call(UnitOnTaxi, "player")) then return false end
  local master = walk.path[#walk.path]
  if not (master and px and continent == walk.continent) or Yards(master, px, py) > WAIT_LEAVE_YARDS then return false end
  self.i = self.i + 1
  return true
end
function Route:Landing()
  local j = self:RideAt()
  local walk = j and self.legs[j + 1]
  if walk and walk.kind == "W" and walk.start then return walk.start[1], walk.start[2], walk.continent end
  local lands = j and self.legs[j].lands
  if lands then return lands[1], lands[2], lands.continent end
end
function Route:Destination(continent, px, py)
  local j = self:RideAt()
  local ride = j and self.legs[j]
  if not ride then return nil end
  local name = ride.text ~= "" and ride.text or self.name or ""
  local lx, ly, lc = self:Landing()
  if ride.landsIn == nil then
    local zone = lx and select(2, Geo.ZoneAt(lc, lx, ly))
    if zone and name ~= "" and (zone:lower():find(name:lower(), 1, true) or name:lower():find(zone:lower(), 1, true)) then
      zone = nil
    end
    ride.landsIn = zone or false
  end
  return name, ride.landsIn or nil, (lx and px and continent == lc) and Dist(lx, ly, px, py) or nil
end
function Route:NextFlight()
  for j = self.i, #self.legs do
    local leg = self.legs[j]
    if leg.kind ~= "W" then return leg.kind == "F" and leg or nil end
  end
end
local function Walks(leg) return leg.kind == "W" or leg.kind == "w" end
function Route:Join(continent, px, py)
  if ns.Plain(Call(UnitOnTaxi, "player")) then return false end
  local upto = #self.legs
  for m = self.i + 1, #self.legs do
    if self.legs[m - 1].kind == "W" and Walks(self.legs[m]) then upto = m; break end
  end
  for j = upto, self.i + 1, -1 do
    local leg = self.legs[j]
    if leg.start and leg.continent == continent and self.legs[j - 1].kind ~= "W" and Yards(leg.start, px, py) <= JOIN_YARDS then
      self.i = j
      return true
    end
  end
  return false
end
function Route:WalkedOff(continent, px, py)
  local walk = self.legs[self.i - 1]
  if self.legs[self.i].kind ~= "F" or self.legs[self.i].carried or not walk or walk.kind ~= "W" or walk.continent ~= continent
     or ns.Plain(Call(UnitOnTaxi, "player")) or Yards(walk.path[#walk.path], px, py) <= WAIT_LEAVE_YARDS then
    return false
  end
  self.i = self.i - 1
  return true
end
function Route:Arrive(yards, there)
  local leg = self.legs[self.i]
  if leg.kind ~= "W" or self.i >= #self.legs then return false end
  if leg.stop and not AtSpot(yards, there) or not leg.stop and yards > LEG_ARRIVE_YARDS then return false end
  self.i = self.i + 1
  return true
end

local B64 = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-_"
local B64V = {}
for i = 1, 64 do B64V[B64:sub(i, i)] = i - 1 end

local function Point(s)
  local v = 0
  for i = 1, 5 do
    local d = B64V[s:sub(i, i)]
    if not d then return end
    v = v * 64 + d
  end
  return math.floor(v / 32768) / 32767, (v % 32768) / 32767
end

local function LegLabel(route, i)
  local nxt = route.legs[i + 1]
  if route.legs[i].stop then return string.format("stop %d of %d", route.legs[i].stop, route.stops) end
  if not nxt or nxt.kind == "W" then return route.name end
  if nxt.kind == "D" then return (nxt.text:gsub("^Enter ", "the way into "):gsub("^Leave ", "the way out of "):gsub("^Take the portal", "the portal")) end
  return RIDES[nxt.kind][2]:format(nxt.text ~= "" and nxt.text or route.name)
end

local function StepText(route, i) return ns.RideText(route.legs[i], route.name) end

local function StepsAhead(route, from)
  local words = {}
  for j = from, #route.legs do
    if route.legs[j].kind == "W" then break end
    words[#words + 1] = StepText(route, j)
  end
  return table.concat(words, ", then ")
end

local function LegTarget(route, i)
  route.i = i
  local leg = route.legs[i]
  if leg.kind == "W" then
    local path = {}
    for k, p in ipairs(leg.path) do path[k] = { p[1], p[2], leg.continent, rise = p.rise, cov = p.cov } end
    local last = leg.path[#leg.path]
    return { map = leg.map, x = last[3], y = last[4], name = LegLabel(route, i), continent = leg.continent,
             wx = last[1], wy = last[2], source = SOURCE_TYPED, path = path, leg = 1, route = route, under = leg.under,
             top = leg.top }
  end
  return { map = 0, x = 0, y = 0, name = StepText(route, i), wait = true, source = SOURCE_TYPED, route = route }
end

local function ActivateLeg(route, i)
  target = LegTarget(route, i)
  local ahead = target.wait and StepsAhead(route, i + 1) or ""
  distText:SetText(ahead ~= "" and ("then " .. ahead) or "")
  gold:Alpha(target.wait and 0.3 or 1)
  nameText:SetText(target.name)
  frame:Show()
  ns.guideDirty = true
end

ns.PackedPoint = Point

local DELTA_YARDS = 2
function ns.DecodeWay(mapID, text)
  local out, i, n, w, continent = {}, 1, nil, nil, nil
  while i <= #text do
    if not n or text:sub(i, i) == "_" then
      local at = n and i + 1 or i
      local x, y = Point(text:sub(at, at + 4))
      if not x then return nil end
      local c, wx, wy = WorldPos(mapID, x, y)
      if not c then return nil end
      continent, n, w = continent or c, wx, wy
      i = at + 5
    else
      local a, b = B64V[text:sub(i, i)], B64V[text:sub(i + 1, i + 1)]
      if not a or not b then return nil end
      n, w = n + (a - 32) * DELTA_YARDS, w + (b - 32) * DELTA_YARDS
      i = i + 2
    end
    out[#out + 1] = { n, w }
  end
  return out, continent
end

local UNDER, HEIGHT_MARK = "*", ":"
function ns.DecodeRise(pts, letters)
  letters = letters or ""
  local cover
  letters, cover = letters:match("^([^%.]*)%.?(.*)$")
  local at, inside = 1, false
  for k = 1, #cover do
    local v = B64V[cover:sub(k, k)]
    if not v then break end
    for j = at, inside and at + v - 1 or 0 do
      if pts[j] then pts[j].cov = true end
    end
    at, inside = at + v, not inside
  end
  local under = letters:sub(1, 1) == UNDER
  if under then letters = letters:sub(2) end
  local top = nil
  if letters:sub(1, 1) == HEIGHT_MARK then
    local a, b, c = B64V[letters:sub(2, 2)], B64V[letters:sub(3, 3)], B64V[letters:sub(4, 4)]
    if a and b and c then top = (a * 4096 + b * 64 + c) / 8 - 4096 end
    letters = letters:sub(5)
  end
  local first = #pts - #letters
  for k = 1, #letters do
    local v, p = B64V[letters:sub(k, k)], pts[first + k]
    if v and p then p.rise = (v - 32) * DELTA_YARDS end
  end
  return under, top
end

function ns.RouteCommand(payload)
  local body, name = strtrim(payload or ""):match("^(.-)=(.*)$")
  local parts = body and { strsplit("~", body) }
  if not parts or #parts < 2 then return ns.Print(ns.NOT_WHOLE) end
  local route = ns.NewRoute({})
  route.name, route.npc, route.hostile = WhoIn(strtrim(name))
  local gmap, gpt = parts[1]:match("^(%d+)%.(%S*)$")
  if gmap and #gpt == 5 then
    local gx, gy = Point(gpt)
    if gx then route.goal = { map = tonumber(gmap), x = gx * 100, y = gy * 100 } end
  end
  for k = 2, #parts do
    local p, kind = parts[k], parts[k]:sub(1, 1)
    if kind == "W" then
      local cmap, cway = p:match("^W(%d+)%^(.*)$")
      local map, pts = p:match("^W(%d+)%.(.*)$")
      local leg
      if cmap then
        local body, letters = cway:match("^([^!]*)!?(.*)$")
        local way, continent = ns.DecodeWay(tonumber(cmap), body)
        if not way or #way == 0 then return ns.Print(ns.NOT_WHOLE) end
        local under, top = ns.DecodeRise(way, letters)
        leg = { kind = "W", map = tonumber(cmap), path = {}, continent = continent, under = under or nil, top = top }
        for i, b in ipairs(way) do leg.path[i] = { b[1], b[2], rise = b.rise, cov = b.cov } end
        local last = leg.path[#leg.path]
        last[3], last[4] = MapSpot(leg.map, continent, last[1], last[2])
      else
        if not map or #pts == 0 or #pts % 5 ~= 0 then return ns.Print(ns.NOT_WHOLE) end
        leg = { kind = "W", map = tonumber(map), path = {} }
        for i = 1, #pts, 5 do
          local x, y = Point(pts:sub(i, i + 4))
          local continent, wx, wy
          if x then continent, wx, wy = WorldPos(leg.map, x, y) end
          if not continent then return ns.Print(string.format("map %s has no position for a point of the route", map)) end
          leg.continent = continent
          leg.path[#leg.path + 1] = { wx, wy, x * 100, y * 100 }
        end
      end
      if #route.legs > 0 and #leg.path > 1 then leg.start = table.remove(leg.path, 1) end
      route.legs[#route.legs + 1] = leg
    elseif RIDES[kind] then
      local text, npc = strtrim(p:sub(2)):match("^(.-)@(.+)$")
      route.legs[#route.legs + 1] = { kind = kind, text = text or strtrim(p:sub(2)), npc = npc }
    elseif kind == "?" then
      route.careful = ns.DecodeCareful(p:sub(2))
    else
      return ns.Print(ns.NOT_WHOLE)
    end
  end
  for j = 1, #route.legs - 1 do
    if Walks(route.legs[j]) and Walks(route.legs[j + 1]) then
      route.stops = (route.stops or 0) + 1
      route.legs[j].stop = route.stops
    end
  end
  if route.stops then
    route.stops = route.stops + 1
    route.legs[#route.legs].stop = route.stops
  end
  route.check = ns.LineCheck("r", payload)
  if ns.CorpseRun() then
    local t = Behind(LegTarget(route, 1), route.name)
    ns.SayCareful(route.careful)
    return t
  end
  resume = nil
  TakenOver(route.name)
  ActivateLeg(route, 1)
  local more = route.stops and route.stops - 1 or 0
  ns.Print("Guiding you to " .. route.name .. (more > 0 and string.format(" and %d more stop%s", more, more > 1 and "s" or "") or "")
    .. " in " .. #route.legs .. " steps. Right-click the arrow or type /ioa go off to stop the guide.")
  ns.SayCareful(route.careful)
end

local elapsed = 0
local followed = nil
local function Goal(route, continent)
  for j = route and #route.legs or 0, route and route.i or 1, -1 do
    local leg = route.legs[j]
    if leg.kind == "W" and leg.continent == continent and leg.path and #leg.path > 0 then
      return { leg.path[#leg.path][1], leg.path[#leg.path][2] }
    end
  end
end

ns.OnTick(frame, "the guide arrow", nil, function(_, dt)
  if target ~= followed then
    followed = target
    if ns.BeaconFollow then ns.BeaconFollow() end
    PointTarget()
  end
  elapsed = elapsed + dt
  if elapsed < 0.05 or not target then return end
  elapsed = 0
  local look = ns.NavLook(target)
  gold:Colour(UI.GUIDE[look], look ~= "go")
  if look ~= target.look then target.look, ns.guideDirty = look, true end
  target.along = nil
  gold:Height(nil)
  gold:Glow(nil)
  if target.source ~= SOURCE_CORPSE and ns.Ghost() then
    gold:Alpha(0.3)
    distText:SetText(ns.AFTER_CORPSE)
    return
  end
  local continent, px, py = PlayerWorldPos()
  local route = target.route
  if route then
    if continent then
      if route:Join(continent, px, py) or route:Boarded(continent, px, py) then ActivateLeg(route, route.i) end
    elseif target.wait and route.legs[route.i].kind == "D" and route.legs[route.i].text:find("^Enter") and route.i < #route.legs then
      ActivateLeg(route, route.i + 1)
    end
    if target.wait and continent and route:WalkedOff(continent, px, py) then ActivateLeg(route, route.i) end
    local riding = route:UnderWay(continent, px, py) ~= nil
    if riding then route.legs[route.i].carried = true end
    if riding ~= (target.riding or false) then
      target.riding = riding
      PointTarget()
    end
    if target.wait or not continent then
      gold:Alpha(0.3)
      if riding then gold:Turn(ns.RideTurn(route, continent, px, py)) end
      local ahead = StepsAhead(route, target.wait and route.i + 1 or route.i)
      local cut = target.wait and route.i == #route.legs and route.legs[route.i].kind ~= "w"
      distText:SetText(ahead ~= "" and ("then " .. ahead) or cut and CUT_SHORT or (continent and "" or "position unknown here"))
      return
    end
  end
  local facing = ns.Plain(Call(GetPlayerFacing))
  if not continent or not facing then
    gold:Alpha(0.3)
    distText:SetText("position unknown here")
    return
  end
  if continent ~= target.continent then
    gold:Alpha(0.3)
    distText:SetText("on another continent")
    return
  end
  local north, west = target.wx - px, target.wy - py
  local yards = math.sqrt(north * north + west * west)
  local toward, along = { target.wx, target.wy }, yards
  local path, off = target.path, false
  if path then
    toward, along, off, target.leg = ns.FollowPath(path, target.leg, px, py)
  end
  target.join = off and toward or nil
  target.along = along
  target.rising = target.rising or {}
  local words, turn = ns.HeightHint(path, target.leg, px, py, yards, target.rising)
  local there = not words and not (path and ns.CoverStop(path, target.leg))
  if route and route.i < #route.legs then
    if route:Arrive(yards, there) then return ActivateLeg(route, route.i) end
  elseif AtSpot(yards, there) then
    return Reached(target.name)
  end
  gold:Height(words, turn)
  gold:Alpha(1)
  local after = route and route.legs[route.i + 1]
  local goal = (not after and Goal(route, continent)) or { target.wx, target.wy }
  gold:Point(facing, px, py, goal, toward)
  distText:SetText(path and (off and string.format("%d yd, back to the route", along)
    or string.format("%d yd, bend %d of %d", along, target.leg, #path)) or string.format("%d yd", yards))
end)

local function CloseByHand()
  if target then ns.GuideClosed("go", target.route and target.route.name or target.name) end
  ns.ClearArrow("You stopped the Navigation Guide.")
end
frame:SetScript("OnClick", CloseByHand)
close:SetScript("OnClick", CloseByHand)

local SOURCE_PIN = 4
local function MapPin()
  if not (C_Map.HasUserWaypoint and C_Map.HasUserWaypoint()) then return end
  local ok, point = pcall(C_Map.GetUserWaypoint)
  local pos = ok and point and point.position
  if not (pos and point.uiMapID) or (ns.BeaconPin and ns.BeaconPin(point.uiMapID, pos.x, pos.y)) then return end
  return point.uiMapID, pos.x * 100, pos.y * 100
end

function ns.EncodeGuide()
  ns.guideDirty = false
  local w = ns.NewWriter()
  w:u8(7)
  if target then
    local goal = target.route and target.route.goal
    w:u8(target.source or 0)
    w:u16(goal and goal.map or target.map); w:u16((goal or target).x * 100); w:u16((goal or target).y * 100)
    w:str(goal and target.route.name or target.name or "", 40)
  else
    local map, x, y = MapPin()
    w:u8(map and SOURCE_PIN or 0)
    w:u16(map or 0); w:u16((x or 0) * 100); w:u16((y or 0) * 100)
    w:str("", 40)
  end
  local _, loopName, loopCheck, loopLook
  if ns.LoopRunning then _, loopName, loopCheck, loopLook = ns.LoopRunning() end
  w:u8(LOOP_LOOKS[loopLook] or 0)
  w:str(loopName or "", 40)
  w:u8(closed.n); w:u8(closed.kind); w:str(closed.name, 40)
  w:u16(GoCheck(((ns.CorpseRun() or not target) and resume) or target) or 0)
  w:u16(loopCheck or 0)
  local kept = Declined()
  w:u16(kept.go); w:u16(kept.loop)
  local findCheck = ns.TargetFinding and select(2, ns.TargetFinding())
  w:u16(findCheck or 0); w:u16(kept.target)
  w:u8(LOOK_CODES[ns.NavLook(target)])
  return w.bytes
end

ns.On({ "USER_WAYPOINT_UPDATED", "SUPER_TRACKING_CHANGED" }, function() ns.guideDirty = true end)

function ns.SetPath(mapID, pts, name)
  local path = {}
  for i, p in ipairs(pts) do
    local continent, wx, wy = WorldPos(mapID, p[1] / 100, p[2] / 100)
    if not continent then return ns.Print(string.format("Map %d has no position for %.2f, %.2f.", mapID, p[1], p[2])) end
    path[i] = { wx, wy, continent }
  end
  local last = pts[#pts]
  local continent, fx, fy = path[#path][3], path[#path][1], path[#path][2]
  if target and target.continent == continent and Dist(target.wx, target.wy, fx, fy) <= SAME_YARDS then
    target.path, target.leg = path, 1
    ns.Print("Following a walkable path to " .. target.name .. ".")
    return
  end
  local t = ns.SetArrow(mapID, last[1], last[2], name)
  if t then t.path, t.leg = path, 1 end
end

function ns.SetWorldPath(mapID, pts, continent, name, under, top)
  local path = {}
  for i, p in ipairs(pts) do path[i] = { p[1], p[2], continent, rise = p.rise, cov = p.cov } end
  local fx, fy = path[#path][1], path[#path][2]
  if target and target.continent == continent and Dist(target.wx, target.wy, fx, fy) <= SAME_YARDS then
    target.path, target.leg, target.under, target.top = path, 1, under or nil, top
    ns.Print("Following a walkable path to " .. target.name .. ".")
    return
  end
  local x, y = MapSpot(mapID, continent, fx, fy)
  local t = { map = mapID, x = x, y = y, name = name ~= "" and name or string.format("%.1f, %.1f", x, y),
              continent = continent, wx = fx, wy = fy, source = SOURCE_TYPED, path = path, leg = 1, under = under or nil,
              top = top }
  if ns.CorpseRun() then return Behind(t) end
  TakenOver(t.name)
  target = t
  nameText:SetText(target.name)
  distText:SetText("")
  gold:Alpha(1)
  frame:Show()
  ns.guideDirty = true
  ns.Print("Guiding you to " .. target.name .. ". Right-click the arrow or type /ioa go off to stop the guide.")
end

local goWho = nil
local goCareful = nil
local function Named(name)
  local clean, npc, hostile = WhoIn(name)
  goWho = npc and { npc, hostile } or nil
  return clean
end
local function GoLine(rest)
  rest = strtrim(rest or "")
  goWho, goCareful = nil, nil
  if rest == "" or rest:lower() == "off" then
    if target then ns.GuideClosed("go", target.route and target.route.name or target.name) end
    return ns.ClearArrow(target and "You stopped the Navigation Guide." or nil)
  end
  local cmap, cway, cname = rest:match("^(%d+)%s+%^(%S+)%s*(.*)$")
  if cmap then
    local body, letters = cway:match("^([^!]*)!?(.*)$")
    local pts, continent = ns.DecodeWay(tonumber(cmap), body)
    if not pts or #pts == 0 then return ns.Print(ns.NOT_WHOLE) end
    local under, top = ns.DecodeRise(pts, letters)
    local said, named = cname:match("^%?(%S*)%s*(.*)$")
    if said then goCareful, cname = ns.DecodeCareful(said), named end
    return ns.SetWorldPath(tonumber(cmap), pts, continent, Named(cname), under, top)
  end
  local pathMap, tail = rest:match("^(%d+)%s+(.+)$")
  if pathMap then
    local pts, remaining = {}, tail
    while true do
      local px, py, after = remaining:match("^([%d%.]+),([%d%.]+)%s*(.*)$")
      if not px then break end
      pts[#pts + 1] = { tonumber(px), tonumber(py) }
      remaining = after
    end
    if #pts >= 2 then return ns.SetPath(tonumber(pathMap), pts, Named(remaining)) end
  end
  local mapID, x, y, name = rest:match("^(%d+)%s+([%d%.]+)[,%s]+([%d%.]+)%s*(.*)$")
  if not mapID then return ns.Print("Type /ioa go <mapID> <x> <y> <name> to start a guide, or /ioa go off to stop it.") end
  ns.SetArrow(tonumber(mapID), tonumber(x), tonumber(y), Named(name))
end

function ns.GoCommand(rest)
  local was, wasPath, waiting = target, target and target.path, resume
  GoLine(rest)
  local took = (target and (target ~= was or target.path ~= wasPath) and target) or (resume ~= waiting and resume) or nil
  if took then
    took.check = ns.LineCheck("go", rest)
    if goWho then took.npc, took.hostile = goWho[1], goWho[2] end
    took.careful = goCareful
    ns.SayCareful(goCareful)
    ns.guideDirty = true
  end
end


local paste = CreateFrame("Frame", "IndexOfAzerothPasteBox", UIParent, "BackdropTemplate")
paste:SetSize(260, 56)
paste:SetPoint("TOP", UIParent, "TOP", 0, -90)
paste:SetFrameStrata("DIALOG")
UI.Panel(paste)
paste:Hide()
tinsert(UISpecialFrames, "IndexOfAzerothPasteBox")

local hint = UI.Text(paste, "GameFontHighlightSmall", UI.C.ivory, "CENTER")
hint:SetPoint("TOP", 0, -6)
hint:SetText("Press Ctrl+V to paste the guide you copied on the page.")

local input = UI.Skin(CreateFrame("EditBox", nil, paste, "BackdropTemplate"), UI.C.row, UI.C.edge)
input:SetSize(230, 20)
input:SetPoint("BOTTOM", 0, 8)
input:SetFontObject(ChatFontNormal)
input:SetTextInsets(6, 6, 0, 0)
input:SetAutoFocus(true)
input:SetScript("OnEscapePressed", function() paste:Hide() end)
input:SetScript("OnTextChanged", function(self, userInput)
  if not userInput then return end
  local text = strtrim(self:GetText() or "")
  local kind, rest = GuideLine(text)
  if kind == "r" then
    paste:Hide()
    ns.RouteCommand(rest)
  elseif kind == "go" then
    paste:Hide()
    ns.GoCommand(rest)
  elseif kind == "target" then
    paste:Hide()
    ns.TargetCommand(rest)
  elseif kind then
    paste:Hide()
    ns.TrackCommand(kind, rest)
  elseif #text > 3 and not ("/ioa go"):find(text:lower(), 1, true) and not ("/ioa r"):find(text:lower(), 1, true) then
    hint:SetText("|cffff4a3dThat isn't a guide from the page|r")
  end
end)
paste:SetScript("OnShow", function()
  input:SetText("")
  hint:SetText("Press Ctrl+V to paste the guide you copied on the page.")
  input:SetFocus()
end)

local function MapPasteButton()
  if not WorldMapFrame or ns.mapPasteButton then return end
  local b = UI.FlatButton(WorldMapFrame, "Paste guide", 110, function() ns.OpenPaste() end)
  ns.mapPasteButton = b
  b:SetHeight(22)
  b:SetPoint("BOTTOM", WorldMapFrame.ScrollContainer or WorldMapFrame, "BOTTOM", 0, 10)
  b:SetFrameLevel((WorldMapFrame:GetFrameLevel() or 0) + 20)
  b:HookScript("OnEnter", function(self)
    GameTooltip:SetOwner(self, "ANCHOR_RIGHT")
    GameTooltip:AddLine("Paste a guide")
    GameTooltip:AddLine("Copy a guide on the page, click this button and press Ctrl+V. The arrow starts at once.", 0.8, 0.8, 0.8, true)
    GameTooltip:Show()
  end)
  b:HookScript("OnLeave", function() GameTooltip:Hide() end)
end
local function ShowMapPaste()
  if ns.mapPasteButton then ns.mapPasteButton:SetShown(ns.Options().general.mapPaste) end
end
ns.On({ "PLAYER_LOGIN", "ADDON_LOADED" }, function(event, name)
  if event == "PLAYER_LOGIN" or name == "Blizzard_WorldMap" then pcall(MapPasteButton); ShowMapPaste() end
end)
ns.On("PLAYER_LOGIN", function() ns.OnOptions(ShowMapPaste) end)


local PENDING_HOURS = 12
local PICKED_UP = { gold = "The game picked up the guide you started on the page.", loop = "The game picked up the loop you "
  .. "started on the page.", find = "The game picked up the Target key you set on the page." }
function ns.StartPending()
  local char, started = IndexOfAzerothCharDB, false
  for _, p in ipairs(PendingGuides()) do
    local kind, rest = GuideLine(p.line)
    local gold, loop, find = kind == "go" or kind == "r", kind == "g" or kind == "h" or kind == "k", kind == "target"
    local running = (gold and target and not ns.CorpseRun()) or (loop and ns.LoopRunning and ns.LoopRunning())
      or (find and ns.TargetFinding and ns.TargetFinding())
    local mine = (p.name or "") == "" or ns.IsMe(p)
    if (gold or loop or find) and not running and mine and not PendingClosed(char, p.id)
        and (tonumber(p.at) or 0) >= time() - PENDING_HOURS * 3600 then
      ns.Print(PICKED_UP[gold and "gold" or loop and "loop" or "find"])
      if kind == "r" then ns.RouteCommand(rest) elseif kind == "go" then ns.GoCommand(rest)
      elseif find then ns.TargetCommand(rest) else ns.TrackCommand(kind, rest) end
      started = true
    end
  end
  return started
end

ns.On("PLAYER_ENTERING_WORLD", function(_, login, reload)
  if login or reload then C_Timer.After(3, function() pcall(ns.StartPending) end) end
end)

function ns.OpenPaste()
  if paste:IsShown() then paste:Hide() else paste:Show() end
end
IndexOfAzerothPasteBox_Toggle = ns.OpenPaste

BINDING_HEADER_INDEXOFAZEROTH = "The Index of Azeroth"
BINDING_NAME_INDEXOFAZEROTH_PASTE = "Paste a guide from the page"
