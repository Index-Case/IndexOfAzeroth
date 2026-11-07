-- The Index of Azeroth. Copyright 2026 Index Case <indexofazeroth@pm.me>. PolyForm Strict 1.0.0, see LICENSE.md.
local ADDON, ns = ...

local CAP, CAP_WINDOW = 5, 3600
local RUN_GAP = 30 * 60
local MAX_LOOT = 12
local MAX_STARS = 40
local SOURCE_CORPSE = 3

local Plain, Call = ns.Plain, ns.Call
local PlainText = ns.PlainText
local Geo = ns.Geo


local byInstance, byKey = {}, {}
for _, d in ipairs(ns.Dungeons or {}) do
  byInstance[d.instance] = byInstance[d.instance] or {}
  table.insert(byInstance[d.instance], d)
  byKey[d.key] = d
end
ns.DungeonByKey = byKey

local char
local run
local here
local deadIn

local function Entries()
  if type(IndexOfAzerothDB) ~= "table" then IndexOfAzerothDB = {} end
  if type(IndexOfAzerothDB.entries) ~= "table" then IndexOfAzerothDB.entries = {} end
  return IndexOfAzerothDB.entries
end

local function PruneEntries()
  local now, keep = time(), {}
  for _, e in ipairs(Entries()) do
    if type(e) == "table" and type(e.t) == "number" and now - e.t < CAP_WINDOW then keep[#keep + 1] = e end
  end
  IndexOfAzerothDB.entries = keep
  return keep
end

local function Counted(list, e)
  for _, k in ipairs(list) do
    if k.map == e.map and (k.t == e.t or (k.uid ~= nil and k.uid == e.uid)) then return true end
  end
end

function ns.InitCharDB()
  IndexOfAzerothCharDB = type(IndexOfAzerothCharDB) == "table" and IndexOfAzerothCharDB or {}
  char = IndexOfAzerothCharDB
  if type(char.wish) ~= "table" then char.wish = nil end
  if type(char.entries) == "table" then
    local list = Entries()
    for _, e in ipairs(char.entries) do
      if type(e) == "table" and type(e.t) == "number" and not Counted(list, e) then list[#list + 1] = e end
    end
    table.sort(PruneEntries(), function(a, b) return a.t < b.t end)
  end
  char.entries = nil
  if type(char.run) == "table" and byKey[char.run.key] then run = char.run end
  if run and run.ended and not run.over and run.outFor == nil then run.outFor, run.outSince = 0, run.ended end
  deadIn = byKey[char.deadIn]
end


local function PickWing(list)
  if #list == 1 then return list[1] end
  if run and run.instance == list[1].instance and not run.ended and byKey[run.key] then return byKey[run.key] end
  local floor = Plain(Call(C_Map.GetBestMapForUnit, "player"))
  for _, d in ipairs(list) do
    for _, f in ipairs(d.floors or {}) do
      if f == floor then return d end
    end
  end
  local sub = PlainText(GetMinimapZoneText()) or ""
  for _, d in ipairs(list) do
    for _, name in ipairs(d.subAreas or {}) do
      if name == sub then return d end
    end
    for _, b in ipairs(d.bosses or {}) do
      if b.sub == sub then return d end
    end
  end
  if run and run.instance == list[1].instance and byKey[run.key] then return byKey[run.key] end
  return list[1]
end

local function CurrentDungeon()
  local _, kind, difficulty, _, _, _, _, instanceID = GetInstanceInfo()
  instanceID = Plain(instanceID)
  if (kind == "party" or kind == "raid") and instanceID and byInstance[instanceID] then
    return (here and here.instance == instanceID) and here or PickWing(byInstance[instanceID]), instanceID, difficulty
  end
end
ns.CurrentDungeon = function() return here end

local function ZoneUID(unit)
  local kind, map, uid, npc = Geo.Creature(Plain(Call(UnitGUID, unit)))
  if kind and uid then return map, uid, npc end
end


function ns.CapEntries() return PruneEntries() end

function ns.CapWords()
  local list = PruneEntries()
  if #list < CAP - 1 then return #list end
  local wait = math.max(1, math.ceil((CAP_WINDOW - (time() - list[1].t)) / 60))
  if #list >= CAP then return #list, "Instance cap reached", string.format("The next instance frees up in %d min.", wait) end
  return #list, string.format("%d of %d instances this hour", #list, CAP),
    string.format("You can enter one more new instance, then you have to wait. The oldest instance frees up in %d min.", wait)
end

local function CapWarning()
  local _, text, detail = ns.CapWords()
  if not text then return end
  ns.Banner(text .. ". " .. detail)
  ns.WarningSound()
  ns.Print(text .. ". " .. detail)
end

local function NoteEntry(instanceID, uid)
  local list = PruneEntries()
  local pending
  for i = #list, 1, -1 do
    if list[i].map == instanceID and list[i].pending then pending = i; break end
  end
  if uid then
    for _, e in ipairs(list) do
      if e.map == instanceID and e.uid == uid then
        if pending then table.remove(list, pending) end
        return false
      end
    end
    if pending then
      list[pending].uid, list[pending].pending = uid, nil
      return false
    end
  end
  list[#list + 1] = { t = time(), map = instanceID, uid = uid, pending = not uid or nil }
  return true
end


local function Starred()
  local sh, out = IndexOfAzerothShared, {}
  local all = type(sh) == "table" and type(sh.stars) == "table" and sh.stars or nil
  local key = all and ns.CharKey()
  local mine = key and all[key]
  if type(mine) == "table" then
    if char then char.wish = nil end
  else
    mine = {}
    for id in pairs(char and char.wish or {}) do mine[#mine + 1] = id end
  end
  for _, id in ipairs(mine) do
    if type(id) == "number" then out[id] = true end
  end
  return out
end


local function ItemName(id) return PlainText(Call(C_Item.GetItemNameByID, id)) or ("item " .. id) end

local function NewRun(d, instanceID)
  run = { key = d.key, instance = instanceID, started = time(), kills = {}, deaths = 0, xp = 0, money = 0, loot = {} }
  if char then char.run = run end
  ns.guideDirty = true
end

local function EndRun()
  if not run or run.over then return end
  run.over, run.ended = true, run.ended or time()
  run.outFor, run.outSince = nil, nil
  if ns.MarkChanged then ns.MarkChanged("run") end
end

local function RunClock()
  if not run or run.over or here or not run.ended then return end
  local now = time()
  run.outFor = (run.outFor or 0) + (run.outSince and math.max(0, now - run.outSince) or 0)
  run.outSince = not UnitIsDeadOrGhost("player") and now or nil
  if run.outFor >= RUN_GAP then EndRun() end
end

local function Enter(d, instanceID)
  RunClock()
  local same = run and not run.over and run.instance == instanceID and not run.reset
  if not same then
    EndRun()
    NewRun(d, instanceID)
    if NoteEntry(instanceID, nil) then CapWarning() end
  else
    run.key = d.key
  end
  run.ended, run.outFor, run.outSince = nil, nil, nil
  here = d
  if ns.ClearArrowTo then ns.ClearArrowTo(d.name) end
  local starred, mine = {}, Starred()
  for _, b in ipairs(d.bosses or {}) do
    for _, id in ipairs(b.loot or {}) do
      if mine[id] then starred[#starred + 1] = ItemName(id) .. " (" .. b.name .. ")" end
    end
  end
  if #starred > 0 then ns.Print("You have starred loot in " .. d.name .. ": " .. table.concat(starred, ", ") .. ".") end
end

local function Leave()
  if run and not run.over and not run.ended then run.ended, run.outFor = time(), 0 end
  here = nil
  RunClock()
end

local function IsEncounter(b, id)
  if b.encounter == id then return true end
  for _, e in ipairs(b.encounters or {}) do
    if e == id then return true end
  end
end

local function BossIndex(d, encounterID, npcID, name)
  for i, b in ipairs(d and d.bosses or {}) do
    if (encounterID and IsEncounter(b, encounterID)) or (npcID and b.npc == npcID) or (name and b.name == name) then return i end
  end
end

local bossByNpc = {}
local function AddBosses(list, d)
  for i, b in ipairs(d.bosses or {}) do
    if b.npc and not list[b.npc] then list[b.npc] = { wing = d, index = i } end
  end
end
local function InstanceBosses(instance)
  local list = bossByNpc[instance]
  if not list then
    list = {}
    for _, d in ipairs(byInstance[instance] or {}) do AddBosses(list, d) end
    bossByNpc[instance] = list
  end
  return list
end

local function HereBoss(npc)
  local boss = InstanceBosses(here.instance)[npc]
  if boss then return boss.index, boss.wing end
end

local function WingKills(r, d)
  if not (r and d) then return {} end
  if d.key == r.key then return r.kills or {} end
  return r.also and r.also[d.key] or {}
end

local function RunWings(d)
  local out = { d }
  for _, w in ipairs(d and byInstance[d.instance] or {}) do
    if w ~= d then out[#out + 1] = w end
  end
  return out
end

local function EncounterBoss(encounterID, name)
  for _, w in ipairs(RunWings(here)) do
    local i = BossIndex(w, encounterID, nil, name)
    if i then return i, w end
  end
end

local function Killed(index, wing)
  if not (run and here) or WingKills(run, wing)[index] then return end
  if wing.key == run.key then
    run.kills[index] = true
  else
    run.also = run.also or {}
    run.also[wing.key] = run.also[wing.key] or {}
    run.also[wing.key][index] = true
  end
  if ns.MarkChanged then ns.MarkChanged("run") end
  local boss = wing.bosses[index]
  local drops, mine = {}, Starred()
  for _, id in ipairs(boss.loot or {}) do
    if mine[id] then drops[#drops + 1] = ItemName(id) end
  end
  if #drops > 0 then
    local text = boss.name .. " is down and can drop this starred loot: " .. table.concat(drops, ", ") .. "."
    ns.Banner(text)
    ns.WarningSound()
    ns.Print(text)
  end
  if ns.RefreshButton then ns.RefreshButton() end
end

local function KilledNpc(npc)
  local i, wing = HereBoss(npc)
  if i then Killed(i, wing) end
end

function ns.RunState() return run, here end

function ns.RunBosses(r, d)
  local down, all, rares = 0, 0, {}
  for _, w in ipairs(RunWings(d)) do
    local kills = w == d and (r and r.kills or {}) or WingKills(r, w)
    for i, b in ipairs((w == d or next(kills)) and w.bosses or {}) do
      local killed, rare = kills[i], type(b) == "table" and b.rare
      if rare and killed then rares[#rares + 1] = b.name end
      if not rare then all = all + 1 end
      if not rare and killed then down = down + 1 end
    end
  end
  return down, all, rares
end
function ns.RunKilledByName(r, d, name)
  local found = false
  for _, w in ipairs(RunWings(d)) do
    local kills = w == d and (r and r.kills or {}) or WingKills(r, w)
    for i, b in ipairs(w.bosses or {}) do found = found or (b.name == name and kills[i] and true or false) end
  end
  return found
end


function ns.NearestEntrance(d)
  local mapID = Plain(C_Map.GetBestMapForUnit("player"))
  local pc, px, py = Geo.PlayerWorldPos()
  local candidates = {}
  for _, e in ipairs(d.entrances or {}) do candidates[#candidates + 1] = { map = e.map, x = e.x, y = e.y } end
  if #candidates == 0 and mapID and C_EncounterJournal and C_EncounterJournal.GetDungeonEntrancesForMap then
    local info = Call(C_Map.GetMapInfo, mapID)
    local journal = d.instance and C_EncounterJournal.GetInstanceForGameMap
      and Plain(Call(C_EncounterJournal.GetInstanceForGameMap, d.instance))
    for _, source in ipairs({ mapID, info and info.parentMapID }) do
      for _, e in ipairs(Call(C_EncounterJournal.GetDungeonEntrancesForMap, source) or {}) do
        local id = Plain(e.journalInstanceID)
        local ours
        if journal and id then ours = id == journal else ours = e.name == d.name or ("The " .. (e.name or "")) == d.name end
        if ours and e.position then
          candidates[#candidates + 1] = { map = source, x = e.position.x * 100, y = e.position.y * 100 }
        end
      end
    end
  end
  local best, bestD
  for _, e in ipairs(candidates) do
    local c, wx, wy = Geo.WorldPos(e.map, e.x / 100, e.y / 100)
    local dist = (pc and c == pc) and Geo.Dist(wx, wy, px, py) or math.huge
    if not best or dist < bestD then best, bestD = e, dist end
  end
  return best
end

local function CorpseSpot()
  local start = Plain(C_Map.GetBestMapForUnit("player"))
  if not (start and C_DeathInfo and C_DeathInfo.GetCorpseMapPosition) then return end
  local id = start
  for _ = 1, 4 do
    if not id or id == 0 then return end
    local pos = Call(C_DeathInfo.GetCorpseMapPosition, id)
    local x, y = pos and Plain(pos.x), pos and Plain(pos.y)
    if x and y and x > 0 and y > 0 and x < 1 and y < 1 then
      local zone = id ~= start and Call(C_Map.GetMapInfoAtPosition, id, x, y)
      zone = zone and zone.mapID ~= id and zone.mapID
      local zpos = zone and Call(C_DeathInfo.GetCorpseMapPosition, zone)
      if zpos and Plain(zpos.x) then return zone, zpos.x * 100, zpos.y * 100 end
      return id, x * 100, y * 100
    end
    local info = Call(C_Map.GetMapInfo, id)
    id = info and info.parentMapID
  end
end

local corpseGuided
local function StartCorpseRun()
  if corpseGuided or Plain(Call(IsInInstance)) or not Plain(Call(UnitIsGhost, "player")) or not ns.SetArrow then return end
  if deadIn then
    local e = ns.NearestEntrance(deadIn)
    if e then corpseGuided = true; ns.SetArrow(e.map, e.x, e.y, "Back to " .. deadIn.name, SOURCE_CORPSE) end
    return
  end
  local map, x, y = CorpseSpot()
  if map then corpseGuided = true; ns.SetArrow(map, x, y, "Your corpse", SOURCE_CORPSE) end
end

local function EndCorpseRun()
  deadIn, corpseGuided = nil, nil
  if char then char.deadIn = nil end
  if ns.ClearArrowSource then ns.ClearArrowSource(SOURCE_CORPSE) end
end


local lastXP, lastMax, lastMoney
local lootPattern
local function LootPattern()
  if lootPattern == nil then
    local fmt = LOOT_ITEM_SELF or "You receive loot: %s."
    lootPattern = "^" .. fmt:gsub("([%(%)%.%%%+%-%*%?%[%]%^%$])", "%%%1"):gsub("%%%%s", "(.+)")
  end
  return lootPattern
end
local resetPattern
local function ResetPattern()
  if resetPattern == nil then
    local fmt = INSTANCE_RESET_SUCCESS or "%s has been reset."
    resetPattern = "^" .. fmt:gsub("([%(%)%.%%%+%-%*%?%[%]%^%$])", "%%%1"):gsub("%%%%s", "(.+)")
  end
  return resetPattern
end

local function Refresh()
  local d, instanceID = CurrentDungeon()
  if d then
    if not here or here.instance ~= instanceID then Enter(d, instanceID) end
    if deadIn and ns.ClearArrowSource then ns.ClearArrowSource(SOURCE_CORPSE) end
    corpseGuided = nil
  elseif here then
    Leave()
  else
    RunClock()
  end
  if not UnitIsDeadOrGhost("player") then deadIn, corpseGuided, char.deadIn = nil, nil, nil end
  if not d then StartCorpseRun() end
  if ns.RefreshButton then ns.RefreshButton() end
end

local function LookAt(unit)
  if not here then return end
  local map, uid, npc = ZoneUID(unit)
  if uid and run and map == run.instance then
    if not run.uid then
      run.uid = uid
      NoteEntry(run.instance, uid)
    end
  end
  if npc and Plain(UnitIsDead(unit)) then KilledNpc(npc) end
end

local deathsHeard = { UNIT_DIED = 0, PARTY_KILL = 0, hidden = 0 }
local function Died(event, guid)
  if not here then return end
  deathsHeard[event] = deathsHeard[event] + 1
  if issecretvalue and issecretvalue(guid) then deathsHeard.hidden = deathsHeard.hidden + 1; return end
  local _, _, _, npc = Geo.Creature(guid)
  if npc then KilledNpc(npc) end
end

local function EncounterDead(units)
  units = Plain(units)
  if type(units) ~= "table" then return end
  for _, u in ipairs(units) do
    local npc = type(u) == "table" and ns.PlainNumber(u.creatureID)
    local left = npc and ns.PlainNumber(u.remainingHealthPercent)
    if npc and (not left or left <= 0) then KilledNpc(npc) end
  end
end

ns.On({ "START_LOOT_ROLL", "CANCEL_LOOT_ROLL", "CANCEL_ALL_LOOT_ROLLS" }, function(event, a1, a2) return ns.OnRoll(event, a1, a2) end)
local WHERE_EVENTS = { PLAYER_ENTERING_WORLD = true, ZONE_CHANGED_NEW_AREA = true, ZONE_CHANGED = true, ZONE_CHANGED_INDOORS = true }
ns.On({ "PLAYER_ENTERING_WORLD", "ZONE_CHANGED_NEW_AREA", "ZONE_CHANGED", "ZONE_CHANGED_INDOORS", "ENCOUNTER_END",
        "BOSS_KILL", "PLAYER_DEAD", "PLAYER_UNGHOST", "PLAYER_ALIVE", "PLAYER_XP_UPDATE", "PLAYER_MONEY", "CHAT_MSG_LOOT",
        "CHAT_MSG_SYSTEM", "PLAYER_TARGET_CHANGED", "NAME_PLATE_UNIT_ADDED" }, function(event, a1, a2, _, _, a5, a6)
  if not char then return end
  if WHERE_EVENTS[event] then
    Refresh()
  elseif event == "ENCOUNTER_END" or event == "BOSS_KILL" then
    local success = event == "BOSS_KILL" or a5 == 1
    if success and here then
      local i, wing = EncounterBoss(Plain(a1), Plain(a2))
      if i then Killed(i, wing) end
    end
    if success and here and event == "ENCOUNTER_END" then EncounterDead(a6) end
  elseif event == "PLAYER_DEAD" then
    Refresh()
    corpseGuided = nil
    deadIn = here
    char.deadIn = here and here.key
    if here and run then run.deaths = run.deaths + 1 end
  elseif event == "PLAYER_UNGHOST" or event == "PLAYER_ALIVE" then
    RunClock()
    if not UnitIsDeadOrGhost("player") then
      EndCorpseRun()
    else
      StartCorpseRun()
      if not corpseGuided then C_Timer.After(2, StartCorpseRun) end
    end
  elseif event == "PLAYER_XP_UPDATE" then
    local xp, max = Plain(UnitXP("player")), Plain(UnitXPMax("player"))
    if xp and lastXP and here and run then
      local gained = xp >= lastXP and xp - lastXP or (lastMax - lastXP) + xp
      run.xp = run.xp + math.max(0, gained)
    end
    lastXP, lastMax = xp, max
  elseif event == "PLAYER_MONEY" then
    local money = Plain(GetMoney())
    if money and lastMoney and here and run then run.money = run.money + (money - lastMoney) end
    lastMoney = money
  elseif event == "CHAT_MSG_LOOT" then
    local text = Plain(a1)
    local id = here and run and text and text:match(LootPattern()) and text:match("|Hitem:(%d+)")
    if id then
      table.insert(run.loot, tonumber(id))
      while #run.loot > MAX_LOOT do table.remove(run.loot, 1) end
    end
  elseif event == "CHAT_MSG_SYSTEM" then
    local text = Plain(a1)
    if text and text:match(ResetPattern()) and run then
      run.reset = true
      if not here then EndRun() end
    end
  elseif event == "PLAYER_TARGET_CHANGED" then
    LookAt("target")
  elseif event == "NAME_PLATE_UNIT_ADDED" then
    LookAt(a1)
  end
end)
ns.On("UNIT_HEALTH", function() if char then LookAt("target") end end, "target")
ns.On("UNIT_DIED", function(event, guid) Died(event, guid) end)
ns.On("PARTY_KILL", function(event, _, guid) Died(event, guid) end)

function ns.InitRunTracking()
  lastXP, lastMax, lastMoney = Plain(UnitXP("player")), Plain(UnitXPMax("player")), Plain(GetMoney())
  Refresh()
end


function ns.EquippedLevel(slot)
  local link = Plain(GetInventoryItemLink("player", slot))
  if not link then return 0 end
  local _, _, _, level = Call(C_Item.GetItemInfo, link)
  return Plain(level) or 0
end


local rolls = {}
local MAX_ROLLS = 4
local INV_TYPE = { INVTYPE_HEAD = 1, INVTYPE_NECK = 2, INVTYPE_SHOULDER = 3, INVTYPE_BODY = 4, INVTYPE_CHEST = 5,
  INVTYPE_WAIST = 6, INVTYPE_LEGS = 7, INVTYPE_FEET = 8, INVTYPE_WRIST = 9, INVTYPE_HAND = 10, INVTYPE_FINGER = 11,
  INVTYPE_TRINKET = 12, INVTYPE_WEAPON = 13, INVTYPE_SHIELD = 14, INVTYPE_RANGED = 15, INVTYPE_CLOAK = 16,
  INVTYPE_2HWEAPON = 17, INVTYPE_ROBE = 20, INVTYPE_WEAPONMAINHAND = 21, INVTYPE_WEAPONOFFHAND = 22,
  INVTYPE_HOLDABLE = 23, INVTYPE_THROWN = 25, INVTYPE_RANGEDRIGHT = 26, INVTYPE_RELIC = 28 }

function ns.OnRoll(event, rollID, rollTime)
  rollID = Plain(rollID)
  if event == "START_LOOT_ROLL" then
    local link = rollID and Plain(Call(GetLootRollItemLink, rollID))
    local item = tonumber(link and link:match("item:(%d+)"))
    if item then
      rolls[rollID] = { item = item, bonuses = ns.ItemBonuses(link), ends = GetTime() + (Plain(rollTime) or 60000) / 1000 }
    end
  elseif event == "CANCEL_LOOT_ROLL" then
    if rollID then rolls[rollID] = nil end
  else
    for id in pairs(rolls) do rolls[id] = nil end
  end
  ns.rollsDirty = true
end

if hooksecurefunc and RollOnLoot then
  hooksecurefunc("RollOnLoot", function(rollID)
    rollID = Plain(rollID)
    if rollID and rolls[rollID] then
      rolls[rollID] = nil
      ns.rollsDirty = true
    end
  end)
end

function ns.EncodeRolls(force)
  local now, open = GetTime(), {}
  for id, r in pairs(rolls) do
    if r.ends <= now then rolls[id] = nil else open[#open + 1] = r end
  end
  if #open == 0 and not force then return nil end
  table.sort(open, function(a, b) return a.ends < b.ends end)
  local w = ns.NewWriter()
  w:u8(18)
  w:u8(math.min(#open, MAX_ROLLS))
  for i = 1, math.min(#open, MAX_ROLLS) do
    local r = open[i]
    local _, _, _, level, minLevel, _, _, _, equipLoc, icon, _, classID, subclassID = Call(C_Item.GetItemInfo, r.item)
    if not classID then
      local _, _, _, loc, ic, c, s = Call(C_Item.GetItemInfoInstant, r.item)
      equipLoc, icon, classID, subclassID = loc, ic, c, s
    end
    local inv = Plain(Call(C_Item.GetItemInventoryTypeByID, r.item)) or INV_TYPE[Plain(equipLoc) or ""] or 0
    local usable = Plain(Call(C_PlayerInfo and C_PlayerInfo.CanUseItem, r.item))
    w:u24(r.item)
    w:u8(math.min(255, math.ceil(r.ends - now)))
    w:u8(Plain(classID) or 0); w:u8(Plain(subclassID) or 0); w:u8(inv)
    w:u16(Plain(level) or 0); w:u8(Plain(minLevel) or 0)
    w:u24(Plain(icon) or 0)
    w:u8(usable == nil and 2 or usable and 1 or 0)
  end
  for i = 1, math.min(#open, MAX_ROLLS) do ns.WriteBonuses(w, open[i].bonuses or {}) end
  return w.bytes
end


function ns.EncodeRun()
  RunClock()
  local w = ns.NewWriter()
  w:u8(6)
  local flags = 0
  if here then flags = flags + 1 end
  if ns.GuideSource and ns.GuideSource() == SOURCE_CORPSE then flags = flags + 2 end
  if UnitIsDeadOrGhost("player") then flags = flags + 4 end
  if run and not run.over then flags = flags + 8 end
  w:u8(flags)
  w:str(run and run.key or "", 40)
  w:u16(run and ((run.ended or time()) - run.started) or 0)
  w:u8(run and run.deaths or 0)
  w:u24(run and run.xp or 0)
  w:u24(run and math.max(0, run.money) or 0)
  local kills = {}
  for i in pairs(run and run.kills or {}) do kills[#kills + 1] = i end
  table.sort(kills)
  w:u8(#kills)
  for _, i in ipairs(kills) do w:u8(i) end
  local loot = run and run.loot or {}
  w:u8(#loot)
  for _, id in ipairs(loot) do w:u24(id) end
  local entries = PruneEntries()
  w:u8(#entries)
  for _, e in ipairs(entries) do w:u8(math.floor((time() - e.t) / 60)) end
  w:u8(18)
  for slot = 1, 18 do w:u16(ns.EquippedLevel(slot)) end
  local starred = {}
  for id in pairs(Starred()) do starred[#starred + 1] = id end
  table.sort(starred)
  local n = math.min(#starred, MAX_STARS)
  w:u8(n)
  for i = 1, n do w:u24(starred[i]) end
  local keys = {}
  for key, kills in pairs(run and run.also or {}) do
    if byKey[key] and next(kills) then keys[#keys + 1] = key end
  end
  table.sort(keys)
  w:u8(#keys)
  for _, key in ipairs(keys) do
    local down = {}
    for i in pairs(run.also[key]) do down[#down + 1] = i end
    table.sort(down)
    w:str(key, 40)
    w:u8(#down)
    for _, i in ipairs(down) do w:u8(i) end
  end
  return w.bytes
end

local questCursor = 0
function ns.EncodeQuests(unless)
  local w = ns.NewWriter()
  w:u8(9)
  local log = {}
  local n = ns.PlainNumber(Call(C_QuestLog.GetNumQuestLogEntries)) or 0
  for i = 1, n do
    local info = Call(C_QuestLog.GetInfo, i)
    local id = info and not Plain(info.isHeader) and ns.PlainNumber(info.questID)
    if id and #log < 40 then
      log[#log + 1] = { id = id, done = Plain(Call(C_QuestLog.IsComplete, id)) and 1 or 0 }
    end
  end
  w:u8(#log)
  for _, q in ipairs(log) do w:u24(q.id); w:u8(q.done) end
  local said = #w.bytes
  if unless and ns.Said(w.bytes) == unless then return nil end
  local list = ns.Dungeons or {}
  local sent = 0
  local budget = ns.MAX_PAYLOAD - #w.bytes - 2
  local chunks = {}
  while sent < #list do
    questCursor = questCursor % #list + 1
    local d = list[questCursor]
    local quests, chain = d.quests or {}, d.chain or {}
    local total = #quests + #chain
    local bytes = math.ceil(total / 8)
    if bytes + 2 > budget then questCursor = questCursor - 1; break end
    local bits = {}
    for b = 1, bytes do bits[b] = 0 end
    for qi = 1, total do
      local id = qi <= #quests and quests[qi].id or chain[qi - #quests]
      if Plain(Call(C_QuestLog.IsQuestFlaggedCompleted, id)) then
        local b = math.floor((qi - 1) / 8) + 1
        bits[b] = bits[b] + 2 ^ ((qi - 1) % 8)
      end
    end
    chunks[#chunks + 1] = { index = questCursor, bits = bits }
    budget = budget - bytes - 2
    sent = sent + 1
    if sent >= 12 then break end
  end
  w:u8(#chunks)
  for _, c in ipairs(chunks) do
    w:u8(c.index); w:u8(#c.bits)
    for _, b in ipairs(c.bits) do w:u8(b) end
  end
  return w.bytes, said
end


function ns.PrintDungeon()
  local name, kind, difficulty, _, _, _, _, instanceID = GetInstanceInfo()
  ns.Print(string.format("instance: %s (%s), map %s, difficulty %s", tostring(name), tostring(kind), tostring(instanceID), tostring(difficulty)))
  ns.Print("subzone: " .. tostring(Plain(GetMinimapZoneText())))
  if here then
    local down, all = ns.RunBosses(run, here)
    ns.Print(string.format("dungeon: %s, run %d s, %d deaths, %d XP, %d of %d bosses down", here.name,
      run and (time() - run.started) or 0, run and run.deaths or 0, run and run.xp or 0, down, all))
    for i, b in ipairs(here.bosses or {}) do
      ns.Print(string.format("  %d %s%s%s", i, b.name, b.rare and " (rare)" or "", run and run.kills[i] and " (down)" or ""))
    end
    for k, w in ipairs(RunWings(here)) do
      local kills, say = k > 1 and WingKills(run, w) or {}, "  %s: %d %s (down)"
      for i, b in ipairs(w.bosses or {}) do if kills[i] then ns.Print(string.format(say, w.name, i, b.name)) end end
    end
    ns.Print(string.format("creature deaths received in dungeons: %d UNIT_DIED, %d PARTY_KILL, %d hidden by the game",
      deathsHeard.UNIT_DIED, deathsHeard.PARTY_KILL, deathsHeard.hidden))
  else
    ns.Print("You aren't in a dungeon that the addon's data has.")
  end
  local entries = PruneEntries()
  ns.Print(string.format("instance cap: %d of %d this hour for the account", #entries, CAP))
  for _, e in ipairs(entries) do
    ns.Print(string.format("  map %d, %d min ago%s", e.map or 0, math.floor((time() - e.t) / 60), e.uid and (" copy " .. e.uid) or ""))
  end
  local tiers = Call(EJ_GetNumTiers)
  ns.Print("encounter journal tiers: " .. tostring(tiers))
end
