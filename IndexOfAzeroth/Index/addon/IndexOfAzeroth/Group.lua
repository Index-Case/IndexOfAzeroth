-- The Index of Azeroth. Copyright 2026 Index Case <indexofazeroth@pm.me>. PolyForm Strict 1.0.0, see LICENSE.md.
local ADDON, ns = ...

local ROLES = { TANK = 1, HEALER = 2, DAMAGER = 3 }
local FLAG_DEAD, FLAG_GHOST, FLAG_OFFLINE, FLAG_FAR, FLAG_LEADER, FLAG_COMBAT = 1, 2, 4, 8, 16, 32
local FLAG_ME = 64

local Plain, Call = ns.Plain, ns.Call

function ns.GroupUnits()
  local units = {}
  if IsInRaid() then
    for i = 1, Plain(GetNumGroupMembers()) or 0 do units[#units + 1] = "raid" .. i end
  elseif IsInGroup() then
    for i = 1, 4 do
      if UnitExists("party" .. i) then units[#units + 1] = "party" .. i end
    end
  end
  return units
end

local function Percent(cur, max)
  cur, max = Plain(cur), Plain(max)
  if not cur or not max or max <= 0 then return 255 end
  return math.floor(cur / max * 100 + 0.5)
end

function ns.MemberInfo(unit)
  local _, _, classID = UnitClass(unit)
  local flags = 0
  if Plain(UnitIsDead(unit)) then flags = flags + FLAG_DEAD end
  if Plain(UnitIsGhost(unit)) then flags = flags + FLAG_GHOST end
  if not Plain(UnitIsConnected(unit)) then flags = flags + FLAG_OFFLINE end
  local inRange, checked = Call(UnitInRange, unit)
  if Plain(checked) and not Plain(inRange) then flags = flags + FLAG_FAR end
  if Plain(Call(UnitIsGroupLeader, unit)) then flags = flags + FLAG_LEADER end
  if Plain(UnitAffectingCombat(unit)) then flags = flags + FLAG_COMBAT end
  if Plain(Call(UnitIsUnit, unit, "player")) then flags = flags + FLAG_ME end
  return {
    name = Plain(UnitName(unit)) or "?", class = Plain(classID) or 0, level = Plain(UnitLevel(unit)) or 0,
    health = Percent(UnitHealth(unit), UnitHealthMax(unit)), power = Percent(UnitPower(unit), UnitPowerMax(unit)),
    powerType = Plain(UnitPowerType(unit)) or 0, flags = flags,
    role = ROLES[Plain(Call(UnitGroupRolesAssigned, unit)) or ""] or 0,
  }
end

local function QuestDungeon()
  local guide = ns.GuideInfo and ns.GuideInfo()
  return ns.CurrentDungeon() or (guide and ns.DungeonByKey and ns.DungeonByKey[guide.key])
end

function ns.MemberOnQuest(unit, questID)
  return Plain(Call(C_QuestLog.IsUnitOnQuest, unit, questID)) and true or false
end

local PARTY_SECTION = 1

function ns.EncodeGroup()
  local units = ns.GroupUnits()
  if #units == 0 then return end
  local w = ns.NewWriter()
  w:u8(8)
  local d = QuestDungeon()
  w:str(d and d.key or "", 40)
  local quests = d and d.quests or {}
  local bytes = math.min(8, math.ceil(#quests / 8))
  local shown = {}
  for i = 1, math.min(#units, 10) do shown[i] = units[i] end
  local party = ns.GuideParty and ns.GuideParty()
  local n = ns.WriteFitting(w, shown, function(e, unit)
    local m = ns.MemberInfo(unit)
    e:str(m.name, 18)
    e:u8(m.class); e:u8(m.level); e:u8(m.health); e:u8(m.power); e:u8(m.powerType); e:u8(m.flags); e:u8(m.role)
    e:u8(bytes)
    for b = 1, bytes do
      local v = 0
      for bit = 0, 7 do
        local q = quests[(b - 1) * 8 + bit + 1]
        if q and ns.MemberOnQuest(unit, q.id) then v = v + 2 ^ bit end
      end
      e:u8(v)
    end
  end, party and ns.MAX_PAYLOAD - (4 + #shown) or nil)
  if party then
    local _, away = ns.GuideAtDoor()
    local bits = 0
    w:u8(PARTY_SECTION)
    w:u8(party.members[1].of)
    for k = 1, n do
      w:u8(party.members[k].on)
      if away and away[shown[k]] then bits = bits + 2 ^ (k - 1) end
    end
    w:u16(bits)
  end
  return w.bytes
end
