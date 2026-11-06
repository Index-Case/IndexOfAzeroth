-- The Index of Azeroth. Copyright 2026 Index Case <indexofazeroth@pm.me>. PolyForm Strict 1.0.0, see LICENSE.md.
local ADDON, ns = ...

local KEEP_SECONDS = 20 * 60
local MAX_KEPT = 40
local PER_FRAME = 8
local ALIVE_SECONDS = 10 * 60
local ALIVE_YARDS = 300
local BACK_YARDS = 120
local LIFE_GAP = 5
local WITNESS_SECONDS = 10
local HEALTH_EVERY = 1
local MAX_BACKS = 20
local BACKS_PER_FRAME = 3

local Plain, Call = ns.Plain, ns.Call

local kills = {}
local seen = {}
local backs = {}
local backSeen = {}
local alive = {}
local healthSeen = {}
local offset, backOffset, pruned = 0, 0, 0

local function Parse(guid)
  local kind, map, _, npc, spawn = ns.Geo.Creature(guid)
  if kind == "Creature" and npc and spawn then return map, npc, spawn end
end

local function Where()
  local ok, north, west = pcall(UnitPosition, "player")
  if not ok then return end
  return Plain(north), Plain(west)
end

local function Prune(now)
  if now - pruned < 60 then return end
  pruned = now
  for npc, spawns in pairs(alive) do
    for s, a in pairs(spawns) do
      if now - a.t > ALIVE_SECONDS then spawns[s] = nil end
    end
    if next(spawns) == nil then alive[npc] = nil end
  end
  for guid, t in pairs(healthSeen) do
    if now - t >= HEALTH_EVERY then healthSeen[guid] = nil end
  end
end

local function Back(map, npc, spawn, north, west)
  local key = npc .. "-" .. spawn
  if backSeen[key] or seen[key] then return end
  for i = #kills, 1, -1 do
    local k = kills[i]
    if k.npc == npc and (not (north and k.north) or (north - k.north) ^ 2 + (west - k.west) ^ 2 < BACK_YARDS ^ 2) then
      backSeen[key] = true
      backs[#backs + 1] = { npc = npc, spawn = spawn, map = map or k.map, north = north, west = west, t = GetTime() }
      while #backs > MAX_BACKS do
        backSeen[backs[1].npc .. "-" .. backs[1].spawn] = nil
        table.remove(backs, 1)
      end
      return
    end
  end
end

local function Saw(npc, spawn, north, west, map, living)
  local now = GetTime()
  Prune(now)
  alive[npc] = alive[npc] or {}
  local a = alive[npc][spawn]
  local new = not a
  if new then a = {}; alive[npc][spawn] = a end
  a.t, a.north, a.west = now, north, west
  if living then
    a.living = now
    if not a.first then a.first = now end
  end
  if new and map then Back(map, npc, spawn, north, west) end
  return a
end

local function Others(npc, spawn, north, west)
  local now, n = GetTime(), 0
  local me = alive[npc] and alive[npc][spawn]
  local since = me and me.first
  for s, a in pairs(alive[npc] or {}) do
    if now - a.t > ALIVE_SECONDS then
      alive[npc][s] = nil
    elseif s ~= spawn and not (since and a.died and a.died + LIFE_GAP <= since)
        and (not (north and a.north) or (north - a.north) ^ 2 + (west - a.west) ^ 2 < ALIVE_YARDS ^ 2) then
      n = n + 1
    end
  end
  return n
end

local function Level(unit)
  local level = ns.PlainNumber(Call(UnitLevel, unit))
  if level == -1 then return 255 end
  if level and level >= 1 then return math.min(254, math.floor(level)) end
end

local function Alive(guid, unit)
  local map, npc, spawn = Parse(guid)
  if npc and spawn then
    local north, west = Where()
    local a = Saw(npc, spawn, north, west, map or 0, true)
    if not a.level then a.level = Level(unit) end
    if not a.name then a.name = ns.PlainText(Call(UnitName, unit)) end
    if ns.CampSaw then ns.CampSaw(unit, guid, a.name) end
  end
end

local function Note(guid, name, level)
  local map, npc, spawn = Parse(guid)
  if not npc or not spawn then return end
  local key = npc .. "-" .. spawn
  if seen[key] then return end
  seen[key] = true
  local north, west = Where()
  local a = alive[npc] and alive[npc][spawn]
  kills[#kills + 1] = { npc = npc, spawn = spawn, map = map or 0, north = north, west = west,
                        t = GetTime(), name = name or (a and a.name) or "", others = Others(npc, spawn, north, west),
                        level = (a and a.level) or level }
  Saw(npc, spawn, north, west).died = GetTime()
  while #kills > MAX_KEPT do
    seen[kills[1].npc .. "-" .. kills[1].spawn] = nil
    table.remove(kills, 1)
  end
  offset = math.max(0, #kills - PER_FRAME)
  if ns.MarkChanged then ns.MarkChanged("kills") end
  return true
end

local function Look(unit)
  if not Plain(Call(UnitExists, unit)) then return end
  local guid = Plain(Call(UnitGUID, unit))
  if Plain(Call(UnitIsDead, unit)) then
    local _, npc, spawn = Parse(guid)
    local a = npc and spawn and alive[npc] and alive[npc][spawn]
    if a and a.living and GetTime() - a.living <= WITNESS_SECONDS then
      Note(guid, Plain(Call(UnitName, unit)), a.level or Level(unit))
    end
  else
    Alive(guid, unit)
  end
end

local function Loot()
  for slot = 1, Plain(Call(GetNumLootItems)) or 0 do
    local sources = { Call(GetLootSourceInfo, slot) }
    for i = 1, #sources, 2 do Note(Plain(sources[i])) end
  end
end

local function Health(unit)
  local guid = Plain(Call(UnitGUID, unit))
  if not guid then return end
  if not Plain(Call(UnitIsDead, unit)) then
    local now = GetTime()
    if healthSeen[guid] and now - healthSeen[guid] < HEALTH_EVERY then return end
    healthSeen[guid] = now
  end
  Look(unit)
end

function ns.SeenLately(npc)
  local now = GetTime()
  for _, a in pairs(npc and alive[npc] or {}) do
    if a.living and now - a.living <= WITNESS_SECONDS then return true end
  end
  return false
end

local LOOKED = { target = true, mouseover = true }
ns.On({ "PLAYER_TARGET_CHANGED", "UNIT_HEALTH", "NAME_PLATE_UNIT_ADDED", "UPDATE_MOUSEOVER_UNIT", "LOOT_OPENED" }, function(event, unit)
  if event == "PLAYER_TARGET_CHANGED" then Look("target")
  elseif event == "UPDATE_MOUSEOVER_UNIT" then Look("mouseover")
  elseif event == "LOOT_OPENED" then Loot()
  elseif type(unit) ~= "string" or not (LOOKED[unit] or unit:find("^nameplate")) then return
  elseif event == "UNIT_HEALTH" then Health(unit)
  else Look(unit)
  end
end)

local deathHeard = { UNIT_DIED = 0, PARTY_KILL = 0 }
local deathCounted = { UNIT_DIED = 0, PARTY_KILL = 0 }

local function Died(event, guid)
  deathHeard[event] = deathHeard[event] + 1
  guid = Plain(guid)
  local _, npc, spawn = Parse(guid)
  if not npc or not spawn then return end
  local a = alive[npc] and alive[npc][spawn]
  local unit = ns.PlainText(Call(UnitTokenFromGUID, guid))
  local name = unit and ns.PlainText(Call(UnitName, unit))
  if Note(guid, name, (a and a.level) or (unit and Level(unit))) then deathCounted[event] = deathCounted[event] + 1 end
end

ns.On("UNIT_DIED", function(event, guid) Died(event, guid) end)
ns.On("PARTY_KILL", function(event, _, guid) Died(event, guid) end)

ns.commands = ns.commands or {}
ns.commands.deaths = function()
  if not ns.Print then return end
  ns.Print(string.format("death events this session: UNIT_DIED %d received, %d kills counted first. PARTY_KILL %d received, %d kills counted first",
    deathHeard.UNIT_DIED, deathCounted.UNIT_DIED, deathHeard.PARTY_KILL, deathCounted.PARTY_KILL))
end

local NAME_MOST = 20
local KILL_BYTES = 18
local BACK_BYTES = 15

local function NameRoom(n, nb)
  local most = NAME_MOST
  while most > 0 do
    local size = 3 + nb * BACK_BYTES
    for i = 1, n do
      local name = kills[(offset + i - 1) % #kills + 1].name
      size = size + KILL_BYTES + math.min(type(name) == "string" and #name or 0, most)
    end
    if size <= ns.MAX_PAYLOAD then return most end
    most = most - 1
  end
  return 0
end

function ns.EncodeKills()
  local now = GetTime()
  Prune(now)
  while kills[1] and now - kills[1].t > KEEP_SECONDS do
    seen[kills[1].npc .. "-" .. kills[1].spawn] = nil
    table.remove(kills, 1)
  end
  while backs[1] and now - backs[1].t > KEEP_SECONDS do
    backSeen[backs[1].npc .. "-" .. backs[1].spawn] = nil
    table.remove(backs, 1)
  end
  if #kills == 0 then return nil end
  local w = ns.NewWriter()
  w:u8(17)
  local n = math.min(PER_FRAME, #kills)
  local nb = math.min(BACKS_PER_FRAME, #backs)
  local room = NameRoom(n, nb)
  w:u8(n)
  for i = 1, n do
    local k = kills[(offset + i - 1) % #kills + 1]
    w:u24(k.npc); w:u16(k.spawn % 65536); w:u16(math.floor(k.spawn / 65536))
    w:u16(math.min(65535, math.floor(now - k.t)))
    w:u16(k.map)
    w:i16(k.north or -32768); w:i16(k.west or -32768)
    w:u8(math.min(255, k.others))
    w:str(k.name, room)
  end
  local first = offset
  offset = (offset + n) % #kills
  w:u8(nb)
  for i = 1, nb do
    local b = backs[(backOffset + i - 1) % #backs + 1]
    w:u24(b.npc); w:u16(b.spawn % 65536); w:u16(math.floor(b.spawn / 65536))
    w:u16(math.min(65535, math.floor(now - b.t)))
    w:u16(b.map)
    w:i16(b.north or -32768); w:i16(b.west or -32768)
  end
  if nb > 0 then backOffset = (backOffset + nb) % #backs end
  for i = 1, n do w:u8(kills[(first + i - 1) % #kills + 1].level or 0) end
  return w.bytes
end

local GATHER_SPELLS = { ["Mining"] = true, ["Herb Gathering"] = true }
local GATHER_KEEP = 20 * 60
local MAX_GATHERS = 30
local GATHERS_PER_FRAME = 6
local gathers = {}
local casting = {}
local started, gatherOffset = 0, 0

local function Gathering(spell)
  local name = Call(C_Spell and C_Spell.GetSpellName, spell)
  return type(name) == "string" and (GATHER_SPELLS[name] or name:find("^Opening") ~= nil)
end

ns.On({ "UNIT_SPELLCAST_SENT", "UNIT_SPELLCAST_SUCCEEDED", "UNIT_SPELLCAST_FAILED", "UNIT_SPELLCAST_INTERRUPTED" }, function(event, _, a, b, c)
  if event == "UNIT_SPELLCAST_SENT" then
    local target, guid, spell = Plain(a), Plain(b), Plain(c)
    if type(target) ~= "string" or target == "" or not guid or not spell or not Gathering(spell) then return end
    if started >= 20 then wipe(casting); started = 0 end
    casting[guid] = target
    started = started + 1
    return
  end
  local guid = Plain(a)
  local target = guid and casting[guid]
  if not target then return end
  casting[guid] = nil
  if event ~= "UNIT_SPELLCAST_SUCCEEDED" then return end
  local north, west, _, map = Call(UnitPosition, "player")
  north, west, map = Plain(north), Plain(west), Plain(map)
  if not (north and west) then return end
  gathers[#gathers + 1] = { name = target, map = map or 0, north = north, west = west, t = GetTime() }
  while #gathers > MAX_GATHERS do table.remove(gathers, 1) end
  gatherOffset = math.max(0, #gathers - GATHERS_PER_FRAME)
  if ns.MarkChanged then ns.MarkChanged("gathers") end
end, "player")

function ns.EncodeGathers()
  local now = GetTime()
  while gathers[1] and now - gathers[1].t > GATHER_KEEP do table.remove(gathers, 1) end
  if #gathers == 0 then return nil end
  local w = ns.NewWriter()
  w:u8(19)
  local n = math.min(GATHERS_PER_FRAME, #gathers)
  w:u8(n)
  for i = 1, n do
    local g = gathers[(gatherOffset + i - 1) % #gathers + 1]
    w:u16(math.min(65535, math.floor(now - g.t)))
    w:u16(g.map)
    w:i16(g.north); w:i16(g.west)
    w:str(g.name, 24)
  end
  gatherOffset = (gatherOffset + n) % #gathers
  return w.bytes
end
