-- The Index of Azeroth. Copyright 2026 Index Case <indexofazeroth@pm.me>. PolyForm Strict 1.0.0, see LICENSE.md.
local ADDON, ns = ...

local Plain, Call, PlainText = ns.Plain, ns.Call, ns.PlainText
local Dist = ns.Geo.Dist
local Rules = ns.Rules

local C = { camps = {}, here = nil, PACE_LEAST = 0.5, PACE_MOST = 4, STEPS_MOST = 8 }
ns.Camps = C

function C.Measured(s) return s ~= nil and s.kind == "O" and (s.kh or 0) > 0 end

function C.Mine(s, name, key)
  if type(name) ~= "string" or name == "" then return false end
  local sets = s.campSets
  if not sets then
    local keys, names = {}, {}
    for _, id in ipairs(type(s.mi) == "table" and s.mi or {}) do keys[id] = true end
    if type(s.target) == "string" then names[s.target] = true end
    for _, m in ipairs(type(s.mobs) == "table" and s.mobs or {}) do names[m] = true end
    sets = { keys = next(keys) and keys or nil, names = names }
    s.campSets = sets
  end
  return ns.Geo.Is(key, name, sets.keys, sets.names, not sets.keys and sets.names or nil)
end

local function KillsShow()
  if Plain(Call(IsXPUserDisabled)) then return false end
  if Plain(Call(IsPlayerAtEffectiveMaxLevel)) then return false end
  return true
end


local function Active(c, px, py)
  local moved = c.px ~= nil and px ~= nil and Dist(c.px, c.py, px, py) >= Rules.camps.move
  c.px, c.py = px, py
  if ns.InFight() then
    local t = PlainText(Call(UnitName, "target"))
    return t == nil or C.Mine(c.s, t, ns.Geo.UnitKey("target"))
  end
  return moved
end

local function Count(t)
  local n = 0
  for _ in pairs(t) do n = n + 1 end
  return n
end

function C.Others(c)
  local r = Rules.camps
  if Count(c.tapped) >= r.tapped then return true end
  local plates = Plain(Call(C_CVar and C_CVar.GetCVarBool, "nameplateShowEnemies"))
  return plates == true and (c.kn or 0) > 0 and c.at >= r.least_s and Count(c.alive) <= r.empty * c.kn
end

function C.Judge(c)
  local r = Rules.camps
  local from = c.at - r.window
  local keep = {}
  for _, t in ipairs(c.kills) do if t > from then keep[#keep + 1] = t end end
  c.kills = keep
  for _, list in ipairs({ c.alive, c.tapped }) do
    for guid, t in pairs(list) do if t <= from and from > 0 then list[guid] = nil end end
  end
  local span = math.min(r.window, c.at)
  if c.at < r.least_s or span * c.kh / 3600 < r.least_n then return nil end
  c.rate = #c.kills * 3600 / span
  local share, others = c.rate / c.kh, C.Others(c)
  if not c.busy and share < r.busy and others then
    c.busy = true
    return "busy"
  elseif c.busy and (share >= r.quiet or not others) then
    c.busy = false
    return "quiet"
  end
  return nil
end

function C.Look(s, key, here, now, px, py)
  local r = Rules.camps
  local at = here and C.Measured(s) and not (ns.Ghost and ns.Ghost()) and KillsShow()
  for k, c in pairs(C.camps) do
    if not (at and k == key) and c.left and now - c.left >= r.stays then C.camps[k] = nil end
  end
  local was = C.here and C.camps[C.here]
  if was and not (at and C.here == key) then
    was.seen, was.px, was.py = nil, nil, nil
    if was.busy and ns.MarkChanged then ns.MarkChanged("camps") end
  end
  if not at then
    C.here = nil
    return nil
  end
  local c = C.camps[key]
  if not c then
    c = { at = 0, kills = {}, alive = {}, tapped = {} }
    C.camps[key] = c
  end
  c.s, c.kh, c.kn = s, s.kh, s.kn
  if Active(c, px, py) and c.seen then c.at = c.at + math.min(now - c.seen, r.gap_most) end
  c.seen, c.left = now, now
  C.here = key
  local turned = C.Judge(c)
  if turned and ns.MarkChanged then ns.MarkChanged("camps") end
  return turned == "busy" and "camp_busy" or nil
end

function ns.CampKilled(name)
  local c = C.here and C.camps[C.here]
  if not c then return end
  if C.Mine(c.s, name) or ((name == nil or name == "") and ns.InFight()) then c.kills[#c.kills + 1] = c.at end
end

function ns.CampSaw(unit, guid, name)
  local c = C.here and C.camps[C.here]
  if not (c and guid and C.Mine(c.s, name, ns.Geo.UnitKey(unit))) then return end
  local other = Plain(Call(UnitIsTapDenied, unit)) and true or false
  if not other then
    local t = unit .. "target"
    other = Plain(Call(UnitIsPlayer, t)) and not Plain(Call(UnitIsUnit, t, "player"))
      and not Plain(Call(UnitInParty, t)) and not Plain(Call(UnitInRaid, t)) and true or false
  end
  if other then
    c.tapped[guid], c.alive[guid] = c.at, nil
  elseif not c.tapped[guid] then
    c.alive[guid] = c.at
  end
end

function C.Busy(key)
  local c = key and C.camps[key]
  return c ~= nil and c.busy == true
end

function C.Pace()
  local c = C.here and C.camps[C.here]
  if not (c and c.rate) then return nil end
  if c.rate <= 0 then return C.PACE_MOST end
  return math.max(C.PACE_LEAST, math.min(C.PACE_MOST, c.kh / c.rate))
end

function C.Gap(c)
  local gaps = {}
  for k = 2, #c.kills do gaps[#gaps + 1] = c.kills[k] - c.kills[k - 1] end
  if #gaps == 0 then return nil end
  table.sort(gaps)
  return gaps[math.ceil(#gaps / 2)]
end

function C.Of(key) return key and C.camps[key] or nil end

function C.Reset() C.camps, C.here = {}, nil end

function ns.EncodeCamps()
  local g = ns.GuideInfo and ns.GuideInfo()
  if not g then return nil end
  local list = {}
  for key, c in pairs(C.camps) do
    if c.rate then list[#list + 1] = { key = key, c = c } end
  end
  if #list == 0 then return nil end
  table.sort(list, function(a, b)
    if (a.key == C.here) ~= (b.key == C.here) then return a.key == C.here end
    return a.key < b.key
  end)
  local w = ns.NewWriter()
  w:u8(42)
  local v = tonumber(g.version) or 0
  w:u16(v % 65536); w:u16(math.floor(v / 65536))
  local n = math.min(#list, C.STEPS_MOST)
  w:u8(n)
  for k = 1, n do
    local key, c = list[k].key, list[k].c
    w:u16(c.s.p or 0)
    w:u24(c.s.ids and c.s.ids[1] or 0)
    w:u16(math.floor(c.rate + 0.5))
    w:u16(c.kh)
    w:u16(c.at)
    w:u16(C.Gap(c) or 0)
    w:u8((c.busy and 1 or 0) + (key == C.here and 2 or 0))
  end
  return w.bytes
end
