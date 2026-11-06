-- The Index of Azeroth. Copyright 2026 Index Case <indexofazeroth@pm.me>. PolyForm Strict 1.0.0, see LICENSE.md.
local ADDON, ns = ...

local Plain, PlainText, PlainNumber, Call = ns.Plain, ns.PlainText, ns.PlainNumber, ns.Call
local InFight = ns.InFight

local INSTANCE_KINDS = { party = 1, raid = 2, pvp = 3, arena = 3, scenario = 4 }
local FLAG_POS, FLAG_FACING, FLAG_COMBAT, FLAG_GHOST, FLAG_RESTING, FLAG_INSTANCE, FLAG_TAXI = 1, 2, 8, 16, 32, 64, 128

local idle = { acts = 0, turning = false, swinging = false, repeating = false }
ns.idle = idle

local function Acted() idle.acts = (idle.acts + 1) % 256 end

local EVENTS_KEPT = 4
local HIT, HEAL = 1, 2
local hits = { count = 0, last = {}, changed = false, sentAt = -math.huge }
local HITS_EVERY = 1
ns.hits = hits
ns.On("UNIT_COMBAT", function(_, _, what, _, amount)
  what, amount = PlainText(what), PlainNumber(amount)
  local kind = what == "WOUND" and HIT or what == "HEAL" and HEAL or nil
  if not (kind and amount and amount > 0) then return end
  hits.count = (hits.count + 1) % 65536
  table.insert(hits.last, { kind, math.min(65535, math.floor(amount)) })
  if #hits.last > EVENTS_KEPT then table.remove(hits.last, 1) end
  hits.changed = true
end, "player")

function ns.EncodeHits()
  local w = ns.NewWriter()
  w:u8(34)
  w:u24(math.max(0, math.min(16777215, PlainNumber(Call(UnitHealthMax, "player")) or 0)))
  w:u16(hits.count)
  w:u8(#hits.last)
  for _, h in ipairs(hits.last) do w:u8(h[1]); w:u16(h[2]) end
  hits.changed, hits.sentAt = false, GetTime()
  return w.bytes
end

function ns.HitsDue()
  return hits.changed or (InFight() and GetTime() - hits.sentAt >= HITS_EVERY)
end

local FOOD, EVERY = 1, 2
local REGEN_EVERY = 10
local BUFFS_MOST = 8
local regen = { events = 0, buffs = {}, spirit = nil, changed = true, sentAt = -math.huge }
ns.regen = regen
local RESTORES = { { "(%d+) health over (%d+) sec", FOOD }, { "(%d+) health per (%d+) sec", EVERY },
                   { "(%d+) health every (%d+) sec", EVERY }, { "(%d+) health per second", EVERY, 1 } }

ns.On("UNIT_HEALTH", function()
  regen.events = (regen.events + 1) % 65536
  if not InFight() then regen.changed = true end
end, "player")

local function Restores(tip)
  if type(tip) ~= "table" or type(tip.lines) ~= "table" then return nil end
  for n = 1, #tip.lines do
    local line = tip.lines[n]
    local text = type(line) == "table" and PlainText(line.leftText)
    for k = 1, text and #RESTORES or 0 do
      local p = RESTORES[k]
      local amount, period = text:match(p[1])
      if amount then return { kind = p[2], amount = tonumber(amount), period = p[3] or tonumber(period) } end
    end
  end
end

local function RegenBuffs()
  local out = {}
  local byIndex, tipOf = C_UnitAuras and C_UnitAuras.GetAuraDataByIndex, C_TooltipInfo and C_TooltipInfo.GetUnitBuffByAuraInstanceID
  if not (byIndex and tipOf) then return out end
  for i = 1, 40 do
    local a = Plain(Call(byIndex, "player", i, "HELPFUL"))
    if type(a) ~= "table" then break end
    local id = PlainNumber(a.auraInstanceID)
    local heal = id and Restores(Plain(Call(tipOf, "player", id)))
    if heal and #out < BUFFS_MOST then
      heal.ends = PlainNumber(a.expirationTime) or 0
      out[#out + 1] = heal
    end
  end
  return out
end

local function SameBuffs(a, b)
  if #a ~= #b then return false end
  for k, x in ipairs(a) do
    local y = b[k]
    if x.kind ~= y.kind or x.amount ~= y.amount or x.period ~= y.period or math.abs(x.ends - y.ends) > 1.5 then return false end
  end
  return true
end

function ns.ReadRegen()
  if InFight() then return end
  local spirit, buffs = PlainNumber(Call(UnitStat, "player", 5)), RegenBuffs()
  if spirit ~= regen.spirit or not SameBuffs(buffs, regen.buffs) then regen.changed = true end
  regen.spirit, regen.buffs = spirit, buffs
end
ns.On({ "UNIT_AURA", "UNIT_STATS" }, ns.ReadRegen, "player")
ns.On({ "PLAYER_LOGIN", "PLAYER_ENTERING_WORLD", "PLAYER_REGEN_ENABLED" }, ns.ReadRegen)

function ns.EncodeRegen()
  local w, now = ns.NewWriter(), GetTime()
  w:u8(35)
  w:u24(math.max(0, math.min(16777215, PlainNumber(Call(UnitHealthMax, "player")) or 0)))
  w:u16(regen.spirit and math.min(65534, math.max(0, math.floor(regen.spirit))) or 65535)
  w:u16(regen.events)
  local on = {}
  for _, b in ipairs(regen.buffs) do
    if b.ends == 0 or b.ends > now then on[#on + 1] = b end
  end
  w:u8(#on)
  for _, b in ipairs(on) do
    w:u8(b.kind); w:u16(math.min(65535, b.amount)); w:u16(math.min(65535, b.period))
    w:u16(b.ends == 0 and 0 or math.min(65535, math.ceil(b.ends - now)))
  end
  regen.changed, regen.sentAt = false, now
  return w.bytes
end

function ns.RegenDue()
  return regen.changed or GetTime() - regen.sentAt >= REGEN_EVERY
end

local GOES_ON = { PLAYER_STARTED_TURNING = { "turning", true }, PLAYER_STOPPED_TURNING = { "turning", false },
                  PLAYER_ENTER_COMBAT = { "swinging", true }, PLAYER_LEAVE_COMBAT = { "swinging", false },
                  START_AUTOREPEAT_SPELL = { "repeating", true }, STOP_AUTOREPEAT_SPELL = { "repeating", false } }
local function Doing(event)
  local s = GOES_ON[event]
  if s then idle[s[1]] = s[2] end
  if event == "PLAYER_ENTERING_WORLD" then idle.turning, idle.swinging, idle.repeating = false, false, false end
  if not s or s[2] then Acted() end
end
ns.On({ "PLAYER_STARTED_MOVING", "PLAYER_STARTED_TURNING", "PLAYER_STOPPED_TURNING", "PLAYER_STARTED_LOOKING",
        "PLAYER_TARGET_CHANGED", "PLAYER_ENTER_COMBAT", "PLAYER_LEAVE_COMBAT", "START_AUTOREPEAT_SPELL",
        "STOP_AUTOREPEAT_SPELL", "PLAYER_ENTERING_WORLD" }, Doing)
ns.On({ "UNIT_SPELLCAST_SENT", "UNIT_SPELLCAST_START", "UNIT_SPELLCAST_CHANNEL_START", "UNIT_SPELLCAST_FAILED" }, Acted, "player")
for _, f in ipairs({ { _G, "UseAction" }, { _G, "CastPetAction" }, { _G, "JumpOrAscendStart" }, { _G, "UseInventoryItem" },
                     { C_Container, "UseContainerItem" } }) do
  if hooksecurefunc and type(f[1]) == "table" and type(f[1][f[2]]) == "function" then pcall(hooksecurefunc, f[1], f[2], Acted) end
end

local function Busy()
  if idle.turning or idle.swinging or idle.repeating or Plain(Call(IsPlayerMoving)) then return true end
  local cast, channel = Call(UnitCastingInfo, "player"), Call(UnitChannelInfo, "player")
  return (issecretvalue and (issecretvalue(cast) or issecretvalue(channel))) or cast ~= nil or channel ~= nil
end

local TRACKING_MOST, TRACKING_AGAIN = 4, 5
local tracking = { at = nil, list = nil, more = false }
ns.On({ "MINIMAP_UPDATE_TRACKING", "PLAYER_ENTERING_WORLD" }, function() tracking.at = nil end)

local function ReadTracking()
  local api = C_Minimap
  if not (api and api.GetNumTrackingTypes and api.GetTrackingInfo) then return nil, false end
  local count = Plain(Call(api.GetNumTrackingTypes))
  if type(count) ~= "number" then return nil, false end
  local list, more = {}, false
  for i = 1, count do
    local info = Call(api.GetTrackingInfo, i)
    if type(info) ~= "table" then return nil, false end
    if Plain(info.active) then
      local id, kind = Plain(info.spellID), Plain(info.type)
      if #list >= TRACKING_MOST then more = true
      else list[#list + 1] = { spell = kind == "spell" or (type(id) == "number" and id > 0), id = type(id) == "number" and id or 0 } end
    end
  end
  return list, more
end

local function MinimapTracking()
  local now = GetTime()
  if not tracking.at or now - tracking.at > TRACKING_AGAIN then
    local ok, list, more = pcall(ReadTracking)
    tracking.list, tracking.more, tracking.at = ok and list or nil, ok and more or false, now
  end
  local radius = C_Minimap and C_Minimap.GetViewRadius and Plain(Call(C_Minimap.GetViewRadius))
  local shape = GetMinimapShape and Plain(Call(GetMinimapShape))
  return type(radius) == "number" and radius or nil, type(shape) == "string" and shape or nil, tracking.list, tracking.more
end

local TRACKING_EVERY = 3
local trackingSent = { bytes = nil, at = -math.huge, next = nil }
local function EncodeTrackingNow()
  local radius, shape, list, more = MinimapTracking()
  local mm = _G.Minimap
  local w = ns.NewWriter()
  w:u8(40)
  w:u16(math.min(65535, (radius or 0) * 10))
  w:u8(mm and Plain(Call(mm.GetZoom, mm)) or 0)
  local flags = 0
  if shape == "SQUARE" then flags = flags + 1 end
  if shape then flags = flags + 2 end
  if list then flags = flags + 4 end
  if more then flags = flags + 8 end
  if Plain(Call(IsIndoors)) then flags = flags + 16 end
  w:u8(flags)
  w:u8(list and #list or 0)
  for _, t in ipairs(list or {}) do
    w:u8(t.spell and 1 or 0)
    w:u24(t.id or 0)
  end
  return w.bytes
end

function ns.TrackingDue()
  local bytes = EncodeTrackingNow()
  local same = trackingSent.bytes and #bytes == #trackingSent.bytes
  if same then
    for i = 1, #bytes do if bytes[i] ~= trackingSent.bytes[i] then same = false; break end end
  end
  trackingSent.next = bytes
  return not same or GetTime() - trackingSent.at >= TRACKING_EVERY
end

function ns.EncodeTracking()
  local bytes = trackingSent.next or EncodeTrackingNow()
  trackingSent.bytes, trackingSent.at, trackingSent.next = bytes, GetTime(), nil
  return bytes
end

local logs = { combat = nil, advanced = nil, chat = nil }
ns.logs = logs
local function LogsOn()
  if C_CVar and C_CVar.GetCVar and Plain(Call(C_CVar.GetCVar, "advancedCombatLogging")) == "0" then
    Call(C_CVar.SetCVar, "advancedCombatLogging", "1")
  end
  local info = C_ChatInfo or {}
  if LoggingCombat and info.IsLoggingCombat and not Plain(Call(info.IsLoggingCombat)) then Call(LoggingCombat, true) end
  if LoggingChat and info.IsLoggingChat and not Plain(Call(info.IsLoggingChat)) then Call(LoggingChat, true) end
  local combat, advanced = Call(info.IsLoggingCombat)
  logs.combat, logs.advanced = Plain(combat), Plain(advanced)
  logs.chat = Plain(Call(info.IsLoggingChat))
end
ns.LogsOn = LogsOn
ns.On("PLAYER_ENTERING_WORLD", LogsOn)

ns.commands = ns.commands or {}
ns.commands.logs = function()
  LogsOn()
  local function say(name, on)
    ns.Print(on == nil and "The game doesn't say whether its " .. name .. " is on." or
             "The game's " .. name .. " is " .. (on and "on" or "off") .. ".")
  end
  say("combat log", logs.combat)
  say("advanced combat logging", logs.advanced)
  say("chat log", logs.chat)
end

function ns.Collect()
  local s = {}
  s.map = Plain(C_Map.GetBestMapForUnit("player"))
  local pos = s.map and Plain(C_Map.GetPlayerMapPosition(s.map, "player"))
  if pos then s.x, s.y = Plain(pos.x), Plain(pos.y) end
  s.facing = Plain(GetPlayerFacing())
  s.level = Plain(UnitLevel("player")) or 0
  s.xp, s.xpMax = Plain(UnitXP("player")) or 0, Plain(UnitXPMax("player")) or 0
  s.rested = Plain(GetXPExhaustion()) or 0
  s.speed = Plain((GetUnitSpeed("player"))) or 0
  s.zone = PlainText(GetZoneText()) or ""
  s.subzone = PlainText(GetMinimapZoneText()) or ""

  local flags, fighting = 0, InFight()
  if s.x then flags = flags + FLAG_POS end
  if s.facing then flags = flags + FLAG_FACING end
  if fighting then flags = flags + FLAG_COMBAT end
  if Plain(Call(UnitIsGhost, "player")) then flags = flags + FLAG_GHOST end
  if Plain(Call(IsResting)) then flags = flags + FLAG_RESTING end
  if Plain(Call(IsInInstance)) then flags = flags + FLAG_INSTANCE end
  if Plain(Call(UnitOnTaxi, "player")) then flags = flags + FLAG_TAXI end

  local w = ns.NewWriter()
  w:u8(1)
  w:u8(flags)
  w:u16(s.map or 0)
  w:u16((s.x or 0) * 65535)
  w:u16((s.y or 0) * 65535)
  w:u16((s.facing or 0) / (2 * math.pi) * 65535)
  w:u8(s.level)
  w:u24(s.xp); w:u24(s.xpMax); w:u24(s.rested)
  w:u8(s.speed * 10)
  w:u16(0)
  w:str("", 40)
  w:str(s.zone, 32)
  w:str(s.subzone, 32)
  w:str("", 120)
  w:u8(0)
  w:u16(65535)

  local _, kind, _, _, _, _, _, instanceID = GetInstanceInfo()
  local ok, north, west, z = pcall(UnitPosition, "player")
  if not ok then north, west, z = nil, nil, nil end
  north, west, z = Plain(north), Plain(west), Plain(z)
  s.instanceID = Plain(instanceID)
  w:u8(1)
  w:u16(s.instanceID or 0)
  w:u8(INSTANCE_KINDS[kind] or 0)
  w:u8(north and 1 or 0)
  w:i16(north or 0); w:i16(west or 0); w:i16(z or 0)

  local mm = _G.Minimap
  if mm and mm.GetLeft and mm:GetLeft() then
    local _, physicalHeight = GetPhysicalScreenSize()
    local k = mm:GetEffectiveScale() * physicalHeight / 768
    local flags = 0
    if IsIndoors() then flags = flags + 1 end
    if GetCVar("rotateMinimap") == "1" then flags = flags + 2 end
    if mm:IsVisible() then flags = flags + 4 end
    w:u8(2)
    w:u16(mm:GetLeft() * k); w:u16(physicalHeight - mm:GetTop() * k)
    w:u16(mm:GetWidth() * k); w:u16(mm:GetHeight() * k)
    w:u8(Plain(mm:GetZoom()) or 0)
    w:u8(flags)
  end

  w:u8(3)
  w:u8(UnitIsDeadOrGhost("player") and 1 or 0)

  s.acts, s.busy = idle.acts, fighting and Busy() or false
  s.vendor = MerchantFrame and MerchantFrame.IsShown and MerchantFrame:IsShown() and true or false
  w:u8(5)
  w:u8(s.acts)
  w:u8((s.busy and 1 or 0) + (s.vendor and 2 or 0))

  return w.bytes, s
end

local EXPLORED_FRAME, EXPLORED_EVERY = 44, 120
local explored = ns.IdPager(EXPLORED_FRAME, EXPLORED_EVERY)
local zones
local function Zones()
  if zones then return zones end
  local top, climbed = PlainNumber(Call(C_Map.GetBestMapForUnit, "player")), {}
  while top and not climbed[top] do
    climbed[top] = true
    local info = Call(C_Map.GetMapInfo, top)
    local parent = type(info) == "table" and PlainNumber(info.parentMapID)
    if not parent or parent == 0 then break end
    top = parent
  end
  local zoneType = Enum and Enum.UIMapType and Enum.UIMapType.Zone or 3
  local list = {}
  for _, child in ipairs(top and Call(C_Map.GetMapChildrenInfo, top, zoneType, true) or {}) do
    local id = type(child) == "table" and PlainNumber(child.mapID)
    if id then list[#list + 1] = id end
  end
  if #list > 0 then zones = list end
  return zones
end
local function BuildExplored(again)
  local read = C_MapExplorationInfo and C_MapExplorationInfo.GetExploredMapTextures
  local list = read and Zones()
  if not list then return false end
  local ids, seen = {}, {}
  for _, zone in ipairs(list) do
    for _, part in ipairs(Call(read, zone) or {}) do
      local files = type(part) == "table" and Plain(part.fileDataIDs)
      local id = type(files) == "table" and PlainNumber(files[1])
      if id and id > 0 and not seen[id] then seen[id] = true; ids[#ids + 1] = id end
    end
  end
  if #ids == 0 then return false end
  table.sort(ids)
  explored.Offer(ids, table.concat(ids, ","), again)
  return true
end
explored.refill = BuildExplored
ns.ExploredPending, ns.NextExploredFrame = explored.Pending, explored.Next
local exploredAsked = false
ns.On({ "PLAYER_ENTERING_WORLD", "MAP_EXPLORATION_UPDATED" }, function(event, login, reload)
  if event == "PLAYER_ENTERING_WORLD" and not (login or reload) then return end
  if exploredAsked then return end
  exploredAsked = true
  C_Timer.After(event == "PLAYER_ENTERING_WORLD" and 4 or 2, function()
    exploredAsked = false
    if not BuildExplored(event == "PLAYER_ENTERING_WORLD") then C_Timer.After(5, function() BuildExplored(true) end) end
  end)
end)
ns.BuildExplored = BuildExplored
