-- The Index of Azeroth. Copyright 2026 Index Case <indexofazeroth@pm.me>. PolyForm Strict 1.0.0, see LICENSE.md.
local ADDON, ns = ...

local N = {
  money = 1, moneyStart = 2, bagFree = 3, bagSlots = 4, specialFree = 5, durability = 6, hearth = 7,
  quests = 8, questsMax = 9, questsDone = 10, serverMinutes = 11, sessionSeconds = 12, sessionXP = 13,
  lastKillXP = 14, lastKillRested = 15, repReaction = 16, repValue = 17, repMax = 18,
  food = 19, water = 20, bandages = 21, specialSlots = 22,
  miningSkill = 23, herbalismSkill = 24, skinningSkill = 25, fishingSkill = 26,
  tree1Points = 27, tree2Points = 28, tree3Points = 29,
  petActive = 30, petHappiness = 31, petDamage = 32, petTraining = 33, ammo = 34, rangedSpeed = 35, ammoMax = 36, petFood = 37, talentPoints = 38,
  shards = 40, healthstones = 41, soulstones = 42,
  arcanePowder = 45, runeTeleport = 46, runePortals = 47, lightFeather = 48, manaGems = 49,
  poisons = 55, mhPoisonSec = 56, mhPoisonCharges = 57, ohPoisonSec = 58, ohPoisonCharges = 59,
  flashPowder = 60, blindingPowder = 61, mhEnchanted = 62, ohEnchanted = 63,
  holyCandles = 65, sacredCandles = 66,
  rebirthSeeds = 70, giftReagents = 71,
  divinitySymbols = 75, kingsSymbols = 76,
  ankhs = 80, reincarnation = 81, earthTotem = 82, fireTotem = 83, waterTotem = 84, airTotem = 85,
  totem1 = 86, totem2 = 87, totem3 = 88, totem4 = 89,
  ammoKind = 111, ammoGrade = 112, waterGrade = 113,
  sharedVersion = 90,
  lineFormat = 91,
  weaponKinds = 92, armorKinds = 93,
  playedSeconds = 94, levelSeconds = 95,
  epicStep = 96, epicDone = 97,
  durabilityItem = 98,
  trainedLevel = 99,
  epicBefore = 100,
  maxLevel = 101,
  epicItem = 102, epicUse = 103,
  bagJunk = 104,
  addonChores = 105,
  bagJunkValue = 106,
  camps = 107, campWood = 108, campTool = 109,
  addonOptions = 110,
  epicWay = 114,
}
local S = { bind = 1, repName = 2, petLoyalty = 3, ammoName = 4, demon = 5, faction = 6, petDiet = 7, ammoBetter = 8,
  talentRead = 9,
  totem1 = 10, totem2 = 11, totem3 = 12, totem4 = 13 }
local W = {
  ammo = 1, petUnhappy = 2, shards = 3, mhPoison = 4, ohPoison = 5, poisons = 6, water = 7, ankh = 8,
  earthTotem = 9, fireTotem = 10, waterTotem = 11, airTotem = 12, durability = 13,
}
local LOW, OUT = 1, 2
local QUIET = 4
local OPTION_BITS = { warningSound = 1 }
ns.StatusKeys = { N = N, S = S, W = W }

local HEARTHSTONE, SOUL_SHARD = 6948, 6265
local HEALTHSTONES = { 5512, 19004, 19005, 5511, 19006, 19007, 5509, 19008, 19009, 5510, 19010, 19011, 9421, 19012, 19013 }
local SOULSTONES = { 5232, 16892, 16893, 16895, 16896 }
local MANA_GEMS = { 5514, 5513, 8007, 8008 }
local POISON_ITEMS = { 6947, 6949, 6950, 8926, 8927, 8928, 2892, 2893, 8984, 8985, 20844, 3775, 3776, 5237, 6951, 9186,
  10918, 10920, 10921, 10922 }
local TELEPORTS = { 3561, 3562, 3565, 3567, 3563, 3566 }
local PORTALS = { 10059, 11416, 11419, 11417, 11418, 11420 }
local CONJURE_GEM = { 759, 3552, 10053, 10054 }
local REBIRTH = { { 20748, 17038 }, { 20747, 17037 }, { 20742, 17036 }, { 20739, 17035 }, { 20484, 17034 } }
local GIFT = { { 21850, 17026 }, { 21849, 17021 } }
local GREATER_BLESSINGS = { 25782, 25894, 25898, 25895, 25890, 25899 }
local TOTEMS = {
  { key = "earthTotem", item = 5175, spells = { 8071, 2484, 8075, 5730, 8143 } },
  { key = "fireTotem", item = 5176, spells = { 3599, 1535, 8181, 8190, 8227 } },
  { key = "waterTotem", item = 5177, spells = { 5394, 5675, 8184, 8166, 8170 } },
  { key = "airTotem", item = 5178, spells = { 8177, 8512, 8835, 10595, 6495, 15107 } },
}
local MANA_CLASSES = { [2] = true, [3] = true, [5] = true, [7] = true, [8] = true, [9] = true, [11] = true }
local AMMO_FOR = { [2] = 2, [18] = 2, [3] = 3 }
local AMMO_CLASS, AMMO_KINDS = 6, { [2] = true, [3] = true }
local WEAPON_SKILL = { [0] = "Axes", [1] = "Two-Handed Axes", [2] = "Bows", [3] = "Guns", [4] = "Maces",
  [5] = "Two-Handed Maces", [6] = "Polearms", [7] = "Swords", [8] = "Two-Handed Swords", [10] = "Staves",
  [13] = "Fist Weapons", [15] = "Daggers", [16] = "Thrown", [18] = "Crossbows", [19] = "Wands" }
local ARMOR_SKILL = { [1] = "Cloth", [2] = "Leather", [3] = "Mail", [4] = "Plate Mail", [6] = "Shield" }
local INVSLOT_AMMO, INVSLOT_MH, INVSLOT_OH, INVSLOT_RANGED = 0, 16, 17, 18

local Plain, Call = ns.Plain, ns.Call
local PlainText, PlainNumber = ns.PlainText, ns.PlainNumber


local SPELL_BANK = Enum and Enum.SpellBookSpellBank and Enum.SpellBookSpellBank.Player or 0
local function Known(spellID)
  if C_SpellBook and C_SpellBook.IsSpellKnown and Call(C_SpellBook.IsSpellKnown, spellID, SPELL_BANK) then return true end
  if IsPlayerSpell and Call(IsPlayerSpell, spellID) then return true end
  return IsSpellKnown and Call(IsSpellKnown, spellID) or false
end

local function AnyKnown(list)
  for _, id in ipairs(list) do if Known(id) then return true end end
  return false
end

local function Count(itemID) return Plain(Call(C_Item.GetItemCount, itemID, false, false)) or 0 end

local function CountAll(list)
  local n = 0
  for _, id in ipairs(list) do n = n + Count(id) end
  return n
end


local bags = { dirty = true }
local itemKind = {}

local function KindOf(itemID)
  if itemKind[itemID] ~= nil then return itemKind[itemID] end
  local spell = Call(C_Item.GetItemSpell, itemID)
  if not spell then return nil end
  local kind = false
  if spell == "Food" then kind = "food"
  elseif spell == "Drink" then kind = "water"
  elseif spell == "Refreshment" or spell == "Food & Drink" then kind = "both"
  elseif spell == "First Aid" then kind = "bandage" end
  itemKind[itemID] = kind
  return kind
end

local function Grade(itemID)
  local level = Plain(select(5, Call(C_Item.GetItemInfo, itemID)))
  if level == nil then bags.dirty = true end
  return level or 0
end

local function ScanBags()
  local free, slots, special, specialSlots, ammoSlots, food, water, bandages, junk = 0, 0, 0, 0, 0, 0, 0, 0, 0
  local junkValue = 0
  local items = {}
  local ammo, drinks = {}, {}
  for bag = 0, 4 do
    local numSlots = Plain(Call(C_Container.GetContainerNumSlots, bag)) or 0
    local bagFree, family = Call(C_Container.GetContainerNumFreeSlots, bag)
    bagFree, family = Plain(bagFree) or 0, Plain(family) or 0
    if family == 0 then
      free, slots = free + bagFree, slots + numSlots
    else
      special, specialSlots = special + bagFree, specialSlots + numSlots
      if family % 4 > 0 then ammoSlots = ammoSlots + numSlots end
    end
    for slot = 1, numSlots do
      local itemID = Plain(Call(C_Container.GetContainerItemID, bag, slot))
      if itemID then
        local info = Call(C_Container.GetContainerItemInfo, bag, slot)
        items[itemID] = (items[itemID] or 0) + (info and Plain(info.stackCount) or 1)
        if info and Plain(info.quality) == 0 then
          junk = junk + 1
          local price = Plain(select(11, Call(C_Item.GetItemInfo, itemID)))
          if price == nil then bags.dirty = true end
          junkValue = junkValue + (tonumber(price) or 0) * (info and Plain(info.stackCount) or 1)
        end
        local kind = KindOf(itemID)
        local stack = info and Plain(info.stackCount) or 1
        if kind then
          if kind == "food" or kind == "both" then food = food + stack end
          if kind == "water" or kind == "both" then
            water = water + stack
            drinks[itemID] = Grade(itemID)
          end
          if kind == "bandage" then bandages = bandages + stack end
        elseif kind == nil then
          bags.dirty = true
        end
        local itemClass, sub = select(6, Call(C_Item.GetItemInfoInstant, itemID))
        if Plain(itemClass) == AMMO_CLASS and AMMO_KINDS[Plain(sub)] then
          local a = ammo[itemID] or { count = 0, sub = Plain(sub), level = Grade(itemID) }
          a.count = a.count + stack
          ammo[itemID] = a
        end
      end
    end
  end
  bags.free, bags.slots, bags.special = free, slots, special
  bags.specialSlots, bags.ammoSlots = specialSlots, ammoSlots
  bags.items, bags.ammo, bags.drinks = items, ammo, drinks
  bags.food, bags.water, bags.bandages = food, water, bandages
  bags.junk, ns.bagJunk = junk, junk
  bags.junkValue, ns.bagJunkValue = junkValue, junkValue
end


local function Skills()
  local byName = {}
  local n = Plain(Call(C_SkillInfo.GetNumSkillLines)) or 0
  for i = 1, n do
    local info = Call(C_SkillInfo.GetSkillLineInfo, i)
    local name = info and not Plain(info.isHeader) and PlainText(info.name)
    if name then byName[name] = info end
  end
  return byName
end

local function Kinds(byName, names)
  local mask = 0
  for sub, name in pairs(names) do
    if byName[name] then mask = mask + 2 ^ sub end
  end
  return mask
end

local function WeaponSkills(byName)
  local out, seen = {}, {}
  for _, slot in ipairs({ INVSLOT_MH, INVSLOT_OH, INVSLOT_RANGED }) do
    local itemID = Call(GetInventoryItemID, "player", slot)
    if itemID then
      local _, _, _, _, _, classID, subClassID = Call(C_Item.GetItemInfoInstant, itemID)
      local skill = classID == 2 and WEAPON_SKILL[subClassID]
      local info = skill and byName[skill]
      if info and not seen[skill] then
        seen[skill] = true
        out[#out + 1] = { name = skill, rank = Plain(info.rank) or 0, max = Plain(info.maxRank) or 0 }
      end
    end
  end
  return out
end


local played = { total = nil, level = nil, at = nil, hushed = {} }

local function Unhush()
  for _, f in ipairs(played.hushed) do pcall(f.RegisterEvent, f, "TIME_PLAYED_MSG") end
  played.hushed = {}
end

function ns.AskPlayed()
  if #played.hushed > 0 then return end
  for i = 1, NUM_CHAT_WINDOWS or 10 do
    local f = _G["ChatFrame" .. i]
    if f and f.IsEventRegistered and Plain(Call(f.IsEventRegistered, f, "TIME_PLAYED_MSG")) then
      pcall(f.UnregisterEvent, f, "TIME_PLAYED_MSG")
      played.hushed[#played.hushed + 1] = f
    end
  end
  Call(RequestTimePlayed)
  if C_Timer and C_Timer.After then C_Timer.After(10, Unhush) end
end

local session = { start = nil, moneyStart = 0, xp = 0, lastXP = nil, lastMax = nil, lastRested = 0,
  lastKillXP = 0, lastKillRested = false, combatEnded = 0, questTurnedIn = 0 }

local watch = { from = false, list = nil, counts = {}, cooldowns = {}, known = {}, changed = false, sentAt = -math.huge,
  hurry = false, asked = false,
  EVERY = 20,
  GCD = 1.5 }
ns.watch = watch

local kxp = { gains = {}, next = 1, load = math.floor(time()) % 65536, heard = {}, lines = 0, auras = {}, changed = false,
  sentAt = -math.huge,
  KEEP = 600,
  MOST = 40,
  SENDS = 2,
  LINE_NEAR = 1,
  AURAS_EVERY = 20,
  OTHERS_MOST = 9, POINTS_MOST = 4,
  AURAS = { 1243969, 429959, 1225490 },
  WELL_FED = 19705,
  isXP = {} }
for _, id in ipairs(kxp.AURAS) do kxp.isXP[id] = true end
ns.killXP = kxp

function kxp.Wording(format)
  return "^" .. format:gsub("[%^%$%(%)%.%[%]%*%+%-%?]", "%%%0"):gsub("%%s", "(.-)"):gsub("%%d", "(%%d+)")
end
local function Words(name, english) return type(_G[name]) == "string" and _G[name] or english end
kxp.KILL = kxp.Wording(Words("COMBATLOG_XPGAIN_FIRSTPERSON", "%s dies, you gain %d experience."))
kxp.OTHER = kxp.Wording(Words("COMBATLOG_XPGAIN_FIRSTPERSON_UNNAMED", "You gain %d experience."))
kxp.RESTED = "%(%+(%d+) exp "

ns.On("CHAT_MSG_COMBAT_XP_GAIN", function(_, text)
  text = PlainText(text)
  if not text then return end
  kxp.lines = kxp.lines + 1
  local name, xp = text:match(kxp.KILL)
  if not name then xp = text:match(kxp.OTHER) end
  xp = tonumber(xp)
  if not xp then return end
  if #kxp.heard >= 20 then table.remove(kxp.heard, 1) end
  kxp.heard[#kxp.heard + 1] = { t = GetTime(), xp = xp, name = name, rested = name and tonumber(text:match(kxp.RESTED)) }
end)

function kxp.Party()
  local units = ns.GroupUnits and ns.GroupUnits() or {}
  if #units == 0 then return 1, {} end
  local levels = {}
  for _, unit in ipairs(units) do
    if not Plain(Call(UnitIsUnit, unit, "player")) and #levels < kxp.OTHERS_MOST then
      local inRange, checked = Call(UnitInRange, unit)
      if not Plain(Call(UnitIsDeadOrGhost, unit)) and Plain(Call(UnitIsConnected, unit)) ~= false
          and not (Plain(checked) and Plain(inRange) == false) then
        levels[#levels + 1] = PlainNumber(Call(UnitLevel, unit)) or 0
      end
    end
  end
  return #units + (Plain(Call(IsInRaid)) and 0 or 1), levels
end

function kxp.Queue(xp, rested, level, name)
  local inInstance, kind = Call(IsInInstance)
  inInstance, kind = Plain(inInstance), Plain(kind)
  local size, levels = kxp.Party()
  kxp.gains[#kxp.gains + 1] = { id = kxp.next, t = GetTime(), xp = xp, rested = math.min(rested, xp), level = level,
    inside = inInstance and (kind == "party" or kind == "raid") or false, size = size, levels = levels, name = name,
    sent = 0 }
  kxp.next = kxp.next % 65535 + 1
  if #kxp.gains > kxp.MOST then table.remove(kxp.gains, 1) end
  if ns.CampKilled then ns.CampKilled(name) end
  if ns.MarkChanged then ns.MarkChanged("xp") end
end

function kxp.Gained(gained, rested, kill, level)
  local now, kills, sum, killed, parsed = GetTime(), {}, 0, 0, true
  for _, l in ipairs(kxp.heard) do
    if now - l.t <= kxp.LINE_NEAR then
      sum = sum + l.xp
      if l.name then
        kills[#kills + 1], killed = l, killed + l.xp
        parsed = parsed and l.rested ~= nil
      end
    end
  end
  wipe(kxp.heard)
  if sum ~= gained then
    if kill then kxp.Queue(gained, rested, level, "") end
    return
  end
  for _, l in ipairs(kills) do kxp.Queue(l.xp, parsed and l.rested or rested * l.xp / killed, level, l.name) end
end

function kxp.Aura(id, bare)
  local ok, a = pcall(C_UnitAuras.GetPlayerAuraBySpellID, id)
  if not ok or (issecretvalue and issecretvalue(a)) then return nil end
  if a == nil then return false end
  if type(a) ~= "table" then return nil end
  local stacks, ends, values = PlainNumber(a.applications), PlainNumber(a.expirationTime), nil
  if not bare then values = a.points end
  if not (stacks and ends) or (issecretvalue and issecretvalue(values)) then return nil end
  local points = {}
  if type(values) == "table" then
    for k = 1, math.min(#values, kxp.POINTS_MOST) do
      points[k] = PlainNumber(values[k])
      if not points[k] then return nil end
    end
  end
  if ends == 0 and id == kxp.AURAS[1] then ends = kxp.WellFedEnds() end
  return { stacks = math.max(1, stacks), ends = ends, points = points }
end

function kxp.WellFedEnds()
  local name = PlainText(Call(C_Spell and C_Spell.GetSpellName, kxp.WELL_FED))
  if not (name and C_UnitAuras.GetAuraDataBySpellName) then return 0 end
  local ok, fed = pcall(C_UnitAuras.GetAuraDataBySpellName, "player", name, "HELPFUL")
  if not ok or (issecretvalue and issecretvalue(fed)) or type(fed) ~= "table" then return 0 end
  return PlainNumber(fed.expirationTime) or 0
end

function kxp.Same(a, b)
  if not (a and b) then return a == b end
  if a.stacks ~= b.stacks or math.abs(a.ends - b.ends) > 1.5 or #a.points ~= #b.points then return false end
  for k, p in ipairs(a.points) do
    if p ~= b.points[k] then return false end
  end
  return true
end

function kxp.ReadList(ids, bare, skip)
  local changed = false
  for k = 1, #ids do
    local id, read = ids[k], nil
    if not (skip and skip[id]) then read = kxp.Aura(id, bare) end
    if read ~= nil then
      read = read or nil
      changed = changed or not kxp.Same(kxp.auras[id], read)
      kxp.auras[id] = read
    end
  end
  return changed
end

function kxp.ReadAuras()
  if not (C_UnitAuras and C_UnitAuras.GetPlayerAuraBySpellID) or Plain(Call(InCombatLockdown)) then return end
  local xp, list = kxp.ReadList(kxp.AURAS), watch.List()
  if xp then
    kxp.changed = true
    if ns.MarkChanged then ns.MarkChanged("xp") end
  end
  if kxp.ReadList(list.auras, true, kxp.isXP) or (xp and list.xp) then watch.Moved() end
end
ns.On("UNIT_AURA", kxp.ReadAuras, "player")
ns.On({ "PLAYER_ENTERING_WORLD", "PLAYER_REGEN_ENABLED" }, kxp.ReadAuras)

function kxp.Current(now)
  local out = {}
  for _, id in ipairs(kxp.AURAS) do
    local a = kxp.auras[id]
    if a and (a.ends == 0 or a.ends > now) then
      out[#out + 1] = { id = id, stacks = a.stacks, points = a.points,
                        left = a.ends == 0 and 0 or math.min(65535, math.ceil(a.ends - now)) }
    end
  end
  return out
end

function kxp.AnyOn(now)
  for _, id in ipairs(kxp.AURAS) do
    local a = kxp.auras[id]
    if a and (a.ends == 0 or a.ends > now) then return true end
  end
  return false
end

function ns.EncodeKillXP()
  local now = GetTime()
  while kxp.gains[1] and now - kxp.gains[1].t > kxp.KEEP do table.remove(kxp.gains, 1) end
  local first = #kxp.gains + 1
  while first > 1 and kxp.gains[first - 1].sent < kxp.SENDS do first = first - 1 end
  local auras = kxp.Current(now)
  if first > #kxp.gains and #auras == 0 and not kxp.changed then return nil end
  local w = ns.NewWriter()
  w:u8(28); w:u16(kxp.load)
  w:u8(#auras)
  for _, a in ipairs(auras) do
    w:u24(a.id); w:u8(a.stacks); w:u16(a.left); w:u8(#a.points)
    for _, p in ipairs(a.points) do w:i16(p) end
  end
  w:u16(kxp.gains[first] and kxp.gains[first].id or kxp.next)
  local list = {}
  for i = first, #kxp.gains do list[#list + 1] = kxp.gains[i] end
  local n = ns.WriteFitting(w, list, function(e, g)
    e:u16(math.min(65535, now - g.t)); e:u8(g.level); e:var(g.xp); e:var(g.rested)
    e:u8(g.inside and 1 or 0); e:u8(g.size); e:u8(#g.levels)
    for _, level in ipairs(g.levels) do e:u8(level) end
    e:str(g.name, 20)
  end)
  for i = 1, n do list[i].sent = list[i].sent + 1 end
  kxp.changed, kxp.sentAt = false, now
  return w.bytes
end

function ns.KillXPDue()
  local last, now = kxp.gains[#kxp.gains], GetTime()
  return (last ~= nil and last.sent < kxp.SENDS) or kxp.changed or (now - kxp.sentAt >= kxp.AURAS_EVERY and kxp.AnyOn(now))
end

function ns.PrintKillXP()
  local now = GetTime()
  ns.Print(kxp.lines > 0 and string.format("The addon has read %d of the game's XP lines since the addon loaded.", kxp.lines)
    or "The addon has read none of the game's XP lines since the addon loaded, so the addon reads each kill's XP off your XP bar.")
  for i = #kxp.gains, math.max(1, #kxp.gains - 4), -1 do
    local g = kxp.gains[i]
    ns.Print(string.format("kill %d, %d s ago: %d XP, %d of it rested, at level %d%s%s, %s", g.id, now - g.t, g.xp, g.rested,
      g.level, g.inside and ", in a dungeon or a raid" or "", g.size > 1 and string.format(", a group of %d, %s", g.size,
        #g.levels > 0 and "the others in range at levels " .. ns.AndList(g.levels) or "nobody else in range") or "",
      g.name ~= "" and g.name or "read off your XP bar"))
  end
  for _, a in ipairs(kxp.Current(now)) do
    ns.Print(string.format("%s: %d %s, %s, its values %s", PlainText(Call(C_Spell and C_Spell.GetSpellName, a.id)) or a.id,
      a.stacks, a.stacks == 1 and "stack" or "stacks", a.left > 0 and string.format("%d min left", math.ceil(a.left / 60))
      or "no end given", #a.points > 0 and table.concat(a.points, ", ") or "not given"))
  end
  if #kxp.gains == 0 and not kxp.AnyOn(now) then ns.Print("The addon has seen no kill XP since the addon loaded, and none of the XP buffs are on.") end
end


function watch.List()
  local sh = IndexOfAzerothShared
  local from = type(sh) == "table" and type(sh.watch) == "table" and sh.watch or nil
  if watch.list and from == watch.from then return watch.list end
  local l = { loaded = from ~= nil, check = from and tonumber(from.check) or 0, auras = {}, recipes = {}, items = {},
    listed = {}, profession = {}, xp = false }
  local function Each(key) return from and type(from[key]) == "table" and from[key] or {} end
  for _, id in ipairs(Each("auras")) do
    id = tonumber(id)
    if id then l.auras[#l.auras + 1], l.listed[id], l.xp = id, true, l.xp or kxp.isXP[id] == true end
  end
  for _, r in ipairs(Each("recipes")) do
    local id = type(r) == "table" and tonumber(r[1])
    if id then l.recipes[#l.recipes + 1], l.profession[id] = id, type(r[2]) == "string" and r[2] or "" end
  end
  for _, id in ipairs(Each("items")) do
    if tonumber(id) then l.items[#l.items + 1] = tonumber(id) end
  end
  l.fires = {}
  for _, f in ipairs(Each("fires")) do
    local id = type(f) == "table" and tonumber(f[1])
    if id then l.fires[id] = true end
  end
  local camps = from and type(from.camps) == "table" and from.camps or {}
  l.campFires, l.campItems = {}, {}
  for _, f in ipairs(type(camps.fires) == "table" and camps.fires or {}) do
    if type(f) == "table" and tonumber(f[1]) and tonumber(f[3]) then l.campFires[#l.campFires + 1] = f end
  end
  for _, e in ipairs(type(camps.items) == "table" and camps.items or {}) do
    local id = type(e) == "table" and tonumber(e[1])
    if id then
      local set = {}
      for _, npc in ipairs(type(e[4]) == "table" and e[4] or {}) do set[npc] = true end
      l.campItems[id] = { name = e[2], price = tonumber(e[3]) or 0, sellers = set }
    end
  end
  watch.from, watch.list = from, l
  return l
end

function watch.Moved()
  watch.changed = true
  if ns.MarkChanged then ns.MarkChanged("watched") end
  if ns.GuideLook then ns.GuideLook() end
end

function watch.Seen()
  local cdb = IndexOfAzerothCharDB
  if type(cdb) ~= "table" then return {} end
  if type(cdb.recipesSeen) ~= "table" then cdb.recipesSeen = {} end
  return cdb.recipesSeen
end

function watch.Saw(id, learnt)
  if not (id and learnt ~= nil and watch.List().profession[id]) then return end
  local seen = watch.Seen()
  if (seen[id] == true) ~= (learnt == true) then
    seen[id] = learnt == true or nil
    watch.Soon()
  end
end

function watch.Spellbook(id)
  return Plain(Call(C_SpellBook and C_SpellBook.IsSpellKnown, id, SPELL_BANK)) == true or Plain(Call(IsPlayerSpell, id)) == true
    or Plain(Call(IsSpellKnown, id)) == true
end

function watch.Known(id, skills)
  if not id then return false end
  if watch.Spellbook(id) then return true end
  if not watch.Seen()[id] then return false end
  local prof = watch.List().profession[id]
  return not prof or prof == "" or (skills or Skills())[prof] ~= nil
end

function watch.Recipes()
  local skills, out = Skills(), {}
  for _, id in ipairs(watch.List().recipes) do
    if watch.Known(id, skills) then out[#out + 1] = id end
  end
  table.sort(out)
  local said = table.concat(out, ",")
  if said ~= watch.recipesSaid then
    watch.recipesSaid, watch.known = said, out
    watch.Moved()
  end
end

function ns.CampNumbers(nums, skills)
  local camps, wood, tool, any = 0, nil, nil, false
  for _, f in ipairs(watch.List().campFires) do
    local info = skills[f[6]]
    if watch.Known(tonumber(f[1]), skills) and info and (Plain(info.rank) or 0) >= (tonumber(f[5]) or 0) then
      local hasTool = not tonumber(f[7]) or Count(tonumber(f[7])) > 0
      camps = camps + Count(tonumber(f[2]) or 0) + (hasTool and math.floor(Count(tonumber(f[3])) / math.max(1, tonumber(f[4]) or 1)) or 0)
      if not any then wood, tool = tonumber(f[3]), not hasTool and tonumber(f[7]) or nil end
      any = true
    end
  end
  if any then nums.camps, nums.campWood, nums.campTool = camps, wood, tool end
end

function ns.CampList()
  local l = watch.List()
  return { fires = l.campFires, items = l.campItems }
end

function watch.Soon()
  if watch.asked then return end
  watch.asked = true
  C_Timer.After(0.5, function()
    watch.asked = false
    local ok, err = pcall(watch.Recipes)
    if not ok then ns.Report("watched recipes", err) end
  end)
end

function watch.Cooldowns()
  local now, out, seen, said, items = GetTime(), {}, {}, {}, watch.List().items
  for k = 1, #items do
    local id, start, duration = items[k], nil, nil
    if (watch.counts[id] or 0) > 0 then start, duration = Call(C_Container.GetItemCooldown, id) end
    start, duration = PlainNumber(start), PlainNumber(duration)
    local key = start and duration and start .. ":" .. duration
    if key and start > 0 and duration > watch.GCD and start + duration > now and not seen[key] then
      seen[key] = true
      out[#out + 1] = { id = id, ends = start + duration }
      said[#said + 1] = id .. ":" .. key
    end
  end
  said = table.concat(said, ",")
  if said ~= watch.cooldownsSaid then
    watch.cooldownsSaid, watch.cooldowns = said, out
    watch.Moved()
  end
end

function watch.Bags()
  local moved = false
  for _, id in ipairs(watch.List().items) do
    local n = Count(id)
    if (watch.counts[id] or 0) ~= n then watch.counts[id], moved = n, true end
  end
  if moved then
    watch.hurry = true
    if ns.MarkChanged then ns.MarkChanged("bags") end
    if ns.GuideLook then ns.GuideLook() end
  end
  watch.Cooldowns()
end

function watch.OnNow(id, now)
  if not id then return false end
  if not (watch.List().listed[id] or kxp.isXP[id]) and C_UnitAuras and C_UnitAuras.GetPlayerAuraBySpellID
      and not Plain(Call(InCombatLockdown)) then
    local read = kxp.Aura(id, true)
    if read ~= nil then kxp.auras[id] = read or nil end
  end
  local a = kxp.auras[id]
  return a ~= nil and (a.ends == 0 or a.ends > now)
end

function ns.NeedMet(need)
  if type(need) ~= "table" then return nil end
  local function Each(key) return type(need[key]) == "table" and need[key] or {} end
  local any, now = false, GetTime()
  for _, e in ipairs(Each("items")) do
    local id = type(e) == "table" and tonumber(e[1])
    any = true
    if not id or Count(id) < (tonumber(e[2]) or 1) then return false end
  end
  for _, id in ipairs(Each("recipes")) do
    any = true
    if not watch.Known(tonumber(id)) then return false end
  end
  for _, id in ipairs(Each("auras")) do
    any = true
    if not watch.OnNow(tonumber(id), now) then return false end
  end
  local skills = (#Each("skills") > 0 or #Each("caps") > 0) and Skills() or {}
  for _, e in ipairs(Each("skills")) do
    local info = type(e) == "table" and skills[e[1]]
    any = true
    if not info or (Plain(info.rank) or 0) < (tonumber(e[2]) or 1) then return false end
  end
  for _, e in ipairs(Each("caps")) do
    local info = type(e) == "table" and skills[e[1]]
    any = true
    if not info or (Plain(info.maxRank) or 0) < (tonumber(e[2]) or 1) then return false end
  end
  if any then return true end
end

function ns.FarmObjective(s)
  local e = type(s) == "table" and s.kind == "S" and s.what == "farm" and type(s.need) == "table"
    and type(s.need.items) == "table" and s.need.items[1]
  local id, need = type(e) == "table" and tonumber(e[1]), type(e) == "table" and tonumber(e[2]) or 1
  if not id then return nil end
  local have = math.min(Count(id), need)
  return { text = string.format("%s: %d/%d", s.target or s.text or "", have, need), numFulfilled = have, numRequired = need,
           finished = have >= need }
end

function ns.EncodeWatched()
  local l, now = watch.List(), GetTime()
  if not l.loaded then return nil end
  local auras, cools, recipes = {}, {}, {}
  for k = 1, #l.auras do
    local id = l.auras[k]
    local a = kxp.auras[id]
    if a and (a.ends == 0 or a.ends > now) then
      auras[#auras + 1] = { id = id, stacks = a.stacks, left = a.ends == 0 and 0 or math.min(65535, math.ceil(a.ends - now)) }
    end
  end
  for _, c in ipairs(watch.cooldowns) do
    if c.ends > now then cools[#cools + 1] = { id = c.id, left = math.min(65535, math.ceil(c.ends - now)) } end
  end
  for k, id in ipairs(watch.known) do recipes[k] = { id = id, before = watch.known[k - 1] } end
  local w = ns.NewWriter()
  w:u8(29); w:u16(l.check); w:u8(0)
  local whole = 0
  if ns.WriteFitting(w, auras, function(e, a) e:u24(a.id); e:u8(a.stacks); e:u16(a.left) end) == #auras then whole = 1 end
  if ns.WriteFitting(w, cools, function(e, c) e:u24(c.id); e:u16(c.left) end) == #cools then whole = whole + 2 end
  local n = ns.WriteFitting(w, recipes, function(e, r) if r.before then e:var(r.id - r.before) else e:u24(r.id) end end,
    ns.MAX_PAYLOAD - 6)
  w.bytes[4] = whole + (n == #recipes and 4 or 0)
  local fire, ago = watch.fire, watch.fire and math.floor(now - watch.fire.at)
  ns.WriteFitting(w, fire and ago <= 65535 and { fire } or {}, function(e, f) e:u24(f.id); e:u16(ago) end)
  watch.changed, watch.sentAt = false, now
  return w.bytes
end

ns.On("UNIT_SPELLCAST_SUCCEEDED", function(_, _, _, spell)
  spell = Plain(spell)
  if spell and watch.List().fires[spell] then
    watch.fire = { id = spell, at = GetTime() }
    watch.Moved()
  end
end, "player")

function ns.WatchedDue()
  return watch.List().loaded and (watch.changed or GetTime() - watch.sentAt >= watch.EVERY)
end

function ns.PrintCamp()
  local l, now, Say = watch.List(), GetTime(), ns.Print
  if not l.loaded then
    return Say("The addon isn't watching anything for camping yet. The Index writes the addon's list into Shared.lua, and a /reload loads the list.")
  end
  local function Spell(id) return PlainText(Call(C_Spell and C_Spell.GetSpellName, id)) or tostring(id) end
  local function Item(id) return PlainText(Call(C_Item.GetItemNameByID, id)) or tostring(id) end
  local function Left(ends) return ends == 0 and "no end given" or string.format("%d min left", math.ceil((ends - now) / 60)) end
  Say(string.format("The addon is watching %d buffs, %d recipes and %d items for camping (the list's check %d).", #l.auras, #l.recipes,
    #l.items, l.check))
  local said = {}
  for _, id in ipairs(l.auras) do
    local a = kxp.auras[id]
    if a and (a.ends == 0 or a.ends > now) then said[#said + 1] = string.format("%s (%s)", Spell(id), Left(a.ends)) end
  end
  Say("buffs on: " .. (#said > 0 and ns.AndList(said) or "none"))
  said = {}
  for _, c in ipairs(watch.cooldowns) do
    if c.ends > now then said[#said + 1] = string.format("%s (%s)", Item(c.id), Left(c.ends)) end
  end
  Say("cooldowns running: " .. (#said > 0 and ns.AndList(said) or "none"))
  said = {}
  for _, id in ipairs(watch.known) do
    said[#said + 1] = string.format("%s (%s)", Spell(id), watch.Spellbook(id) and "your spellbook" or "the game's last word")
  end
  Say("recipes you know: " .. (#said > 0 and ns.AndList(said) or "none"))
  said = {}
  for _, id in ipairs(l.items) do
    if (watch.counts[id] or 0) > 0 then said[#said + 1] = string.format("%s x%d", Item(id), watch.counts[id]) end
  end
  Say("carried: " .. (#said > 0 and ns.AndList(said) or "none"))
end

ns.On("BAG_UPDATE_DELAYED", watch.Bags)
ns.On("BAG_UPDATE_COOLDOWN", watch.Cooldowns)
ns.On({ "NEW_RECIPE_LEARNED", "SPELLS_CHANGED", "LEARNED_SPELL_IN_SKILL_LINE", "SKILL_LINES_CHANGED" }, function(event, id)
  if event == "NEW_RECIPE_LEARNED" then watch.Saw(Plain(id), true) end
  watch.Soon()
end)
ns.On("PLAYER_ENTERING_WORLD", function(_, login, reload)
  if not (login or reload) then return end
  C_Timer.After(3, function()
    local ok, err = pcall(function() watch.Bags(); watch.Recipes(); watch.Moved() end)
    if not ok then ns.Report("reading what the chores tick by", err) end
  end)
end)

local legacy = { NAME_MOST = 24, TREES = { "LEGACY_TREE_ADVENTURE_ID", "LEGACY_TREE_PROFESSIONS_ID", "LEGACY_TREE_PROGRESSION_ID" } }
ns.legacy = legacy

function legacy.Consts()
  local c = type(Constants) == "table" and Constants.LegacyConsts
  return type(c) == "table" and tonumber(c.LEGACY_POINTS_TRAIT_CURRENCY_ID) and c or nil
end

function legacy.List()
  local sh, out = IndexOfAzerothShared, {}
  for _, id in ipairs(type(sh) == "table" and type(sh.legacy) == "table" and sh.legacy or {}) do
    if tonumber(id) then out[#out + 1] = tonumber(id) end
  end
  return out
end

function legacy.Mine(c, currency)
  local found
  local function Mine(info) return type(info) == "table" and PlainNumber(info.traitCurrencyID) == currency end
  if not (C_Traits and C_Traits.GetConfigIDByTreeID and C_Traits.GetTreeCurrencyInfo) then return nil, nil end
  for _, key in ipairs(legacy.TREES) do
    local tree = tonumber(c[key])
    local config = tree and PlainNumber(Call(C_Traits.GetConfigIDByTreeID, tree))
    local infos = config and Call(C_Traits.GetTreeCurrencyInfo, config, tree, true)
    for _, info in ipairs(type(infos) == "table" and infos or {}) do found = found or (Mine(info) and info) end
  end
  if not found then return nil, nil end
  return PlainNumber(found.quantity), PlainNumber(found.spent)
end

function legacy.Max(currency, limit)
  return C_Traits and PlainNumber(Call(C_Traits.GetMaxAvailableTraitCurrency, currency, limit)) or nil
end

function ns.EncodeLegacy()
  local c = legacy.Consts()
  if not c then return nil end
  local currency = tonumber(c.LEGACY_POINTS_TRAIT_CURRENCY_ID)
  local unspent, spent = legacy.Mine(c, currency)
  local names, at, done = {}, {}, {}
  local list = legacy.List()
  table.sort(list)
  local function Add(id, earnedBy)
    local amount = PlainNumber(Call(C_Traits and C_Traits.GetTraitCurrencyForAchievement, currency, id)) or 0
    local who = PlainText(earnedBy)
    who = who and who ~= "" and who:sub(1, legacy.NAME_MOST) or nil
    if who and not at[who] then names[#names + 1], at[who] = who, #names + 1 end
    local before = done[#done] and done[#done].id
    done[#done + 1] = { id = id, amount = amount, who = who and at[who] or 0, before = before }
  end
  for _, id in ipairs(list) do
    local _, _, _, completed, _, _, _, _, _, _, _, _, _, earnedBy = Call(GetAchievementInfo, id)
    if Plain(completed) == true then Add(id, earnedBy) end
  end
  local w = ns.NewWriter()
  w:u8(36); w:u16(currency)
  for _, v in ipairs({ legacy.Max(currency, false) or -1, legacy.Max(currency, true) or -1, unspent or -1, spent or -1 }) do
    w:var(v + 1)
  end
  w:u8(0)
  local flags = #w.bytes
  ns.WriteFitting(w, names, function(e, s) e:str(s, legacy.NAME_MOST) end, ns.MAX_PAYLOAD - 40)
  local n = ns.WriteFitting(w, done, function(e, d)
    if d.before then e:var(d.id - d.before) else e:u24(d.id) end
    e:u8(d.amount); e:u8(d.who)
  end)
  w.bytes[flags] = n == #done and 1 or 0
  return w.bytes
end

ns.On({ "ACHIEVEMENT_EARNED", "TRAIT_CONFIG_UPDATED", "TRAIT_TREE_CURRENCY_INFO_UPDATED" }, function()
  if ns.MarkChanged then ns.MarkChanged("legacy") end
end)

function ns.PrintLegacy()
  local c, Say = legacy.Consts(), ns.Print
  if not c then return Say("This client has no Legacy points.") end
  local currency = tonumber(c.LEGACY_POINTS_TRAIT_CURRENCY_ID)
  local unspent, spent = legacy.Mine(c, currency)
  local function Said(v) return v and tostring(v) or "not given" end
  Say(string.format("Legacy points: %s on the account, %s to spend at most, %s spent and %s not spent here",
    Said(legacy.Max(currency, false)), Said(legacy.Max(currency, true)), Said(spent), Said(unspent)))
  local list, n = legacy.List(), 0
  for _, id in ipairs(list) do
    local _, _, _, completed = Call(GetAchievementInfo, id)
    if Plain(completed) == true then n = n + 1 end
  end
  Say(string.format("%d of the %d Legacy achievements in Shared.lua done", n, #list))
end

local function OnXP()
  local xp, max = Plain(UnitXP("player")), Plain(UnitXPMax("player"))
  if not xp or not max then return end
  local rested = Plain(GetXPExhaustion()) or 0
  if session.lastXP then
    local gained = xp - session.lastXP
    if gained < 0 and session.lastMax then gained = session.lastMax - session.lastXP + xp end
    if gained > 0 then
      session.xp = session.xp + gained
      local now = GetTime()
      local fromKill = (ns.InFight() or now - session.combatEnded < 1.5) and now - session.questTurnedIn > 1
      if fromKill then
        session.lastKillXP = gained
        session.lastKillRested = session.lastRested > 0
      end
      kxp.Gained(gained, math.max(0, session.lastRested - rested), fromKill, session.level or Plain(UnitLevel("player")) or 0)
    end
  end
  session.lastXP, session.lastMax, session.lastRested = xp, max, rested
  session.level = Plain(UnitLevel("player"))
end


local function Weapon(slot)
  local itemID = Call(GetInventoryItemID, "player", slot)
  if not itemID then return end
  local _, _, _, _, _, classID, subClassID = Call(C_Item.GetItemInfoInstant, itemID)
  if classID == 2 then return itemID, subClassID end
end

local function TempEnchant(slot)
  if C_PaperDollInfo and C_PaperDollInfo.GetTemporaryEnchantmentInfo then
    local info = Call(C_PaperDollInfo.GetTemporaryEnchantmentInfo, slot)
    if info then return true, Plain(info.remainingTimeMs) or 0, Plain(info.chargesRemaining) or 0 end
    return false
  end
  local hasMH, mhMs, mhCharges, _, hasOH, ohMs, ohCharges = Call(GetWeaponEnchantInfo)
  if slot == INVSLOT_MH then return hasMH, mhMs or 0, mhCharges or 0 end
  return hasOH, ohMs or 0, ohCharges or 0
end

function ns.CollectStatus()
  if bags.dirty then bags.dirty = false; ScanBags() end
  local _, _, classID = UnitClass("player")
  classID = Plain(classID) or 0
  local nums, strs, warns = {}, {}, {}
  local function Warn(key, level)
    warns[#warns + 1] = { key = W[key], level = level, name = key }
  end
  local function Level(count, low) if count == 0 then return OUT elseif count < low then return LOW end end

  nums.sharedVersion = type(IndexOfAzerothShared) == "table" and tonumber(IndexOfAzerothShared.version) or 0
  nums.trainedLevel = type(IndexOfAzerothCharDB) == "table" and IndexOfAzerothCharDB.trainedLevel or nil
  nums.lineFormat = ns.LINE_FORMAT or 0
  local cap = PlainNumber(Call(GetMaxPlayerLevel))
  if cap and cap > 0 then nums.maxLevel = cap end
  local guide = ns.GuideInfo and ns.GuideInfo()
  if guide then
    local done = ns.GuideProgress()
    nums.epicStep, nums.epicDone = guide.cur and ns.GuidePlanStep(guide.cur) or 0, done
    local before = ns.GuideRunProgress() - done
    if before > 0 then nums.epicBefore = before end
    nums.epicWay = ns.GuideWay and ns.GuideWay() or nil
  end
  local useItem, useNow
  if ns.GuideUseItem then useItem, useNow = ns.GuideUseItem() end
  if useItem then nums.epicItem, nums.epicUse = useItem, useNow end
  nums.money = Plain(GetMoney()) or 0
  nums.moneyStart = session.moneyStart
  nums.bagFree, nums.bagSlots, nums.specialFree = bags.free, bags.slots, bags.special
  nums.bagJunk = bags.junk
  nums.bagJunkValue = bags.junkValue
  nums.addonChores = ns.ChoreRules and ns.ChoreRules.MASK or nil
  local general, options = ns.Options().general, 0
  for name, bit in pairs(OPTION_BITS) do if general[name] then options = options + bit end end
  nums.addonOptions = options
  if bags.specialSlots > 0 then nums.specialSlots = bags.specialSlots end
  local lowest, lowestItem
  for slot = 1, 18 do
    local cur, max = Call(GetInventoryItemDurability, slot)
    cur, max = Plain(cur), Plain(max)
    if cur and max and max > 0 then
      local pct = math.floor(cur / max * 100)
      if not lowest or pct < lowest then lowest, lowestItem = pct, Plain(Call(GetInventoryItemID, "player", slot)) end
    end
  end
  if lowest then
    nums.durability = lowest
    nums.durabilityItem = lowestItem
    if lowest == 0 then Warn("durability", OUT) elseif lowest < 20 then Warn("durability", LOW) end
  end
  strs.bind = PlainText(Call(GetBindLocation))
  if Count(HEARTHSTONE) > 0 then
    local start, duration = Call(C_Container.GetItemCooldown, HEARTHSTONE)
    start, duration = Plain(start) or 0, Plain(duration) or 0
    nums.hearth = start > 0 and math.max(0, math.ceil(start + duration - GetTime())) or 0
  end
  local shown, quests = Call(C_QuestLog.GetNumQuestLogEntries)
  shown, quests = PlainNumber(shown), PlainNumber(quests)
  if quests then
    local done = 0
    for i = 1, shown or 0 do
      local info = Call(C_QuestLog.GetInfo, i)
      local id = info and not Plain(info.isHeader) and PlainNumber(info.questID)
      if id and Plain(Call(C_QuestLog.IsComplete, id)) then done = done + 1 end
    end
    nums.quests, nums.questsDone = quests, done
    nums.questsMax = PlainNumber(Call(C_QuestLog.GetMaxNumQuestsCanAccept)) or 20
  end
  local rep = C_Reputation and Plain(Call(C_Reputation.GetWatchedFactionData))
  local repName = type(rep) == "table" and PlainText(rep.name)
  if repName and repName ~= "" then
    local base = PlainNumber(rep.currentReactionThreshold) or 0
    strs.repName = repName
    nums.repReaction = PlainNumber(rep.reaction) or 0
    nums.repValue = math.max(0, (PlainNumber(rep.currentStanding) or 0) - base)
    nums.repMax = math.max(0, (PlainNumber(rep.nextReactionThreshold) or 0) - base)
  end
  local hour, minute = Call(GetGameTime)
  hour, minute = PlainNumber(hour), PlainNumber(minute)
  if hour and minute then nums.serverMinutes = hour * 60 + minute end
  nums.sessionSeconds = session.start and math.floor(GetTime() - session.start) or 0
  if played.total then
    local since = GetTime() - played.at
    nums.playedSeconds = math.floor(played.total + since)
    nums.levelSeconds = math.floor((played.level or 0) + since)
  end
  nums.sessionXP = session.xp
  nums.lastKillXP = session.lastKillXP
  nums.lastKillRested = session.lastKillRested and 1 or 0

  local skills = Skills()
  if skills["First Aid"] then nums.bandages = bags.bandages end
  ns.CampNumbers(nums, skills)
  nums.weaponKinds, nums.armorKinds = Kinds(skills, WEAPON_SKILL), Kinds(skills, ARMOR_SKILL)
  local unspent = ns.UnspentTalents()
  if unspent then nums.talentPoints = unspent end
  local talentsNow = ns.Talents()
  for tree = 1, talentsNow.from and 3 or 0 do nums["tree" .. tree .. "Points"] = talentsNow.points[tree] or 0 end
  strs.talentRead = talentsNow.read
  for name, key in pairs({ Mining = "miningSkill", Herbalism = "herbalismSkill", Skinning = "skinningSkill", Fishing = "fishingSkill" }) do
    if skills[name] then nums[key] = Plain(skills[name].rank) or 0 end
  end
  strs.faction = PlainText((UnitFactionGroup("player")))
  if MANA_CLASSES[classID] then
    nums.food, nums.water = bags.food, bags.water
    local myLevel, grade = Plain(UnitLevel("player")) or 1, 0
    for _, g in pairs(bags.drinks) do if g <= myLevel and g > grade then grade = g end end
    nums.waterGrade = grade
    local level = Level(bags.water, 5)
    if level then Warn("water", level) end
  end

  local _, rangedSub = Weapon(INVSLOT_RANGED)
  local ammoKind = rangedSub and AMMO_FOR[rangedSub]
  if ammoKind then
    local ammoID = Plain(Call(GetInventoryItemID, "player", INVSLOT_AMMO))
    local inSlot, myLevel = ammoID and bags.ammo[ammoID], Plain(UnitLevel("player")) or 1
    local count, bestID, best = 0, nil, nil
    for id, a in pairs(bags.ammo) do
      if a.sub == ammoKind and a.level <= myLevel then
        count = count + a.count
        if not best or a.level > best or (a.level == best and id == ammoID) then bestID, best = id, a.level end
      end
    end
    nums.ammo, nums.ammoKind, nums.ammoGrade = count, ammoKind, best or 0
    strs.ammoName = inSlot and PlainText(Call(C_Item.GetItemNameByID, ammoID)) or nil
    if bestID and bestID ~= ammoID and not (inSlot and inSlot.level >= best) then
      strs.ammoBetter = PlainText(Call(C_Item.GetItemNameByID, bestID))
    end
    local shot = ammoID or bestID
    if shot and bags.ammoSlots > 0 then
      local stack = select(8, Call(C_Item.GetItemInfo, shot))
      nums.ammoMax = bags.ammoSlots * (Plain(stack) or 200)
    end
    local speed = Plain(Call(UnitRangedDamage, "player"))
    if speed then nums.rangedSpeed = math.floor(speed * 1000) end
    if classID == 3 then
      local level = Level(nums.ammo, 200)
      if level then Warn("ammo", level) end
    end
  end

  if classID == 3 then
    if UnitExists("pet") then
      nums.petActive = 1
      local happiness, damage = Call(C_PetInfo.GetPetHappiness)
      if Plain(happiness) then
        nums.petHappiness, nums.petDamage = happiness, Plain(damage) or 100
        if happiness == 1 then Warn("petUnhappy", LOW) end
      end
      strs.petLoyalty = PlainText(Call(C_PetInfo.GetPetLoyalty))
      local total, used = Call(C_PetInfo.GetPetTrainingPoints)
      if Plain(total) and Plain(used) then nums.petTraining = math.max(0, total - used) end
      if C_PetInfo.CanPetEatItem then
        local count = 0
        for itemID, n in pairs(bags.items or {}) do
          if Call(C_PetInfo.CanPetEatItem, itemID) then count = count + n end
        end
        nums.petFood = count
      end
      local diet = Plain(Call(C_PetInfo.GetPetFoodTypes))
      if type(diet) == "table" then
        local foods = {}
        for _, food in ipairs(diet) do foods[#foods + 1] = PlainText(food) end
        if #foods > 0 then strs.petDiet = table.concat(foods, ", ") end
      end
    end
  elseif classID == 9 then
    if Known(1120) or Known(697) then
      nums.shards = Count(SOUL_SHARD)
      local level = Level(nums.shards, 3)
      if level then Warn("shards", level) end
    end
    if Known(6201) then nums.healthstones = CountAll(HEALTHSTONES) end
    if Known(693) then nums.soulstones = CountAll(SOULSTONES) end
    if UnitExists("pet") then strs.demon = PlainText(Call(UnitCreatureFamily, "pet")) end
  elseif classID == 8 then
    if Known(23028) then nums.arcanePowder = Count(17020) end
    if AnyKnown(TELEPORTS) then nums.runeTeleport = Count(17031) end
    if AnyKnown(PORTALS) then nums.runePortals = Count(17032) end
    if Known(130) then nums.lightFeather = Count(17056) end
    if AnyKnown(CONJURE_GEM) then nums.manaGems = CountAll(MANA_GEMS) end
  elseif classID == 4 then
    if Known(2842) then
      nums.poisons = CountAll(POISON_ITEMS)
      local level = Level(nums.poisons, 5)
      if level then Warn("poisons", level) end
      for _, hand in ipairs({ { INVSLOT_MH, "mh" }, { INVSLOT_OH, "oh" } }) do
        if Weapon(hand[1]) then
          local has, ms, charges = TempEnchant(hand[1])
          nums[hand[2] .. "Enchanted"] = has and 1 or 0
          if has then
            nums[hand[2] .. "PoisonSec"] = math.floor(ms / 1000)
            nums[hand[2] .. "PoisonCharges"] = charges
            if ms < 300000 or (charges > 0 and charges < 20) then Warn(hand[2] .. "Poison", LOW) end
          else
            Warn(hand[2] .. "Poison", OUT)
          end
        end
      end
    end
    if Known(1856) then nums.flashPowder = Count(5140) end
    if Known(2094) then nums.blindingPowder = Count(5530) end
  elseif classID == 5 then
    if Known(21562) then nums.holyCandles = Count(17028) end
    if Known(21564) or Known(27681) or Known(27683) then nums.sacredCandles = Count(17029) end
  elseif classID == 11 then
    for _, pair in ipairs(REBIRTH) do
      if Known(pair[1]) then nums.rebirthSeeds = Count(pair[2]); break end
    end
    for _, pair in ipairs(GIFT) do
      if Known(pair[1]) then nums.giftReagents = Count(pair[2]); break end
    end
  elseif classID == 2 then
    if Known(19752) then nums.divinitySymbols = Count(17033) end
    if AnyKnown(GREATER_BLESSINGS) then nums.kingsSymbols = Count(21177) end
  elseif classID == 7 then
    if Known(20608) then
      nums.ankhs = Count(17030)
      local level = Level(nums.ankhs, 2)
      if level then Warn("ankh", level) end
      local start, duration = Call(GetSpellCooldown, 20608)
      if C_Spell and C_Spell.GetSpellCooldown then
        local info = Call(C_Spell.GetSpellCooldown, 20608)
        if info then start, duration = info.startTime, info.duration end
      end
      start, duration = Plain(start), Plain(duration)
      if start and duration then nums.reincarnation = start > 0 and math.max(0, math.ceil(start + duration - GetTime())) or 0 end
    end
    for _, totem in ipairs(TOTEMS) do
      if AnyKnown(totem.spells) then
        nums[totem.key] = Count(totem.item)
        if nums[totem.key] == 0 then Warn(totem.key, OUT) end
      end
    end
    for slot = 1, 4 do
      local have, name, start, duration = Call(GetTotemInfo, slot)
      name = Plain(have) and PlainText(name)
      if name and name ~= "" then
        strs["totem" .. slot] = name
        nums["totem" .. slot] = math.max(0, math.ceil((PlainNumber(start) or 0) + (PlainNumber(duration) or 0) - GetTime()))
      end
    end
  end

  ns.MarkQuiet(warns)
  local s = { classID = classID, nums = nums, strs = strs, warns = warns, skills = WeaponSkills(skills),
    ranks = ns.OutdatedRanks and ns.OutdatedRanks() or {} }
  if classID == 4 and skills.Lockpicking then
    s.skills[#s.skills + 1] = { name = "Lockpicking", rank = Plain(skills.Lockpicking.rank) or 0, max = Plain(skills.Lockpicking.maxRank) or 0 }
  end
  ns.lastStatus = s
  if ns.StatusRead then
    local ok, err = pcall(ns.StatusRead, s)
    if not ok then ns.Report("errands", err) end
  end
  return s
end

local WEAPON_SKILLS = { Swords = true, Axes = true, Maces = true, Daggers = true, Staves = true, Polearms = true, Bows = true,
  Guns = true, Crossbows = true, Thrown = true, ["Fist Weapons"] = true, ["Two-Handed Swords"] = true,
  ["Two-Handed Axes"] = true, ["Two-Handed Maces"] = true, Wands = true }
function ns.SawTrainer()
  if Plain(Call(IsTradeskillTrainer)) then return false end
  local kind = C_Trainer and Plain(Call(C_Trainer.GetTrainerType))
  if kind and Enum and Enum.TrainerType and kind ~= Enum.TrainerType.General then return false end
  if GetTrainerServiceTypeFilter and Plain(Call(GetTrainerServiceTypeFilter, "available")) == false then return false end
  for i = 1, math.min(Plain(Call(GetNumTrainerServices)) or 0, 60) do
    if WEAPON_SKILLS[Plain(Call(GetTrainerServiceSkillLine, i)) or ""] then return false end
    if Plain(select(3, Call(GetTrainerServiceInfo, i))) == "available" then return false end
  end
  if type(IndexOfAzerothCharDB) ~= "table" then return false end
  IndexOfAzerothCharDB.trainedLevel = Plain(Call(UnitLevel, "player"))
  return true
end
local SERVICE_KINDS = { "available", "unavailable", "used" }
local function EveryService(read)
  if not (GetTrainerServiceTypeFilter and SetTrainerServiceTypeFilter) then return read() end
  local hidden = {}
  ns.readingTrainer = true
  for _, kind in ipairs(SERVICE_KINDS) do
    local on = Plain(Call(GetTrainerServiceTypeFilter, kind))
    if not (on == true or on == 1) then
      hidden[#hidden + 1] = kind
      Call(SetTrainerServiceTypeFilter, kind, 1)
    end
  end
  local ok, got = pcall(read)
  for _, kind in ipairs(hidden) do Call(SetTrainerServiceTypeFilter, kind, 0) end
  ns.readingTrainer = false
  if not ok then error(got, 0) end
  return got
end
ns.EveryTrainerService = EveryService

local trainerNpc = 0
local trainer = ns.Pager({ type = 24, head = 5,
  writeHead = function(w, page) w:u24(trainerNpc); w:u16(#page) end,
  entry = function(w, r, before)
    if before then w:var(r[1] - before[1]) else w:u24(r[1]) end
    w:var(r[2]); w:u8(r[3])
  end })
local function BuildTrainer()
  if Plain(Call(IsTradeskillTrainer)) then return false end
  local kind = C_Trainer and Plain(Call(C_Trainer.GetTrainerType))
  if kind and Enum and Enum.TrainerType and kind ~= Enum.TrainerType.General then return false end
  if not (C_TooltipInfo and C_TooltipInfo.GetTrainerService) then return false end
  local who, _, _, npcID = ns.Geo.Creature(Plain(Call(UnitGUID, "npc")))
  local npc = who == "Creature" and npcID or 0
  local rows = EveryService(function()
    local got = {}
    for i = 1, math.min(Plain(Call(GetNumTrainerServices)) or 0, 400) do
      if WEAPON_SKILLS[Plain(Call(GetTrainerServiceSkillLine, i)) or ""] then return nil end
      if Plain(select(3, Call(GetTrainerServiceInfo, i))) ~= "header" then
        local tip = Call(C_TooltipInfo.GetTrainerService, i)
        local id = type(tip) == "table" and Plain(tip.id)
        if type(id) == "number" and id > 0 then
          got[#got + 1] = { id, math.max(0, math.floor(Plain(Call(GetTrainerServiceCost, i)) or 0)),
                            math.max(0, math.min(255, Plain(Call(GetTrainerServiceLevelReq, i)) or 0)) }
        end
      end
    end
    return got
  end)
  if not rows or #rows == 0 then return false end
  table.sort(rows, function(a, b) return a[1] < b[1] end)
  local said = { npc }
  for _, r in ipairs(rows) do said[#said + 1] = r[1] .. ":" .. r[2] .. ":" .. r[3] end
  trainerNpc = npc
  trainer.Offer(rows, table.concat(said, ","))
  if ns.ChoresTrainerSeen then ns.ChoresTrainerSeen(npc, rows) end
  return true
end
ns.TrainerPending, ns.NextTrainerFrame = trainer.Pending, trainer.Next

ns.On({ "TRAINER_SHOW", "TRAINER_UPDATE", "TRAINER_CLOSED" }, function(event)
  if ns.readingTrainer then return end
  ns.atTrainer = event ~= "TRAINER_CLOSED"
  if ns.atTrainer then pcall(BuildTrainer) end
  local saw = ns.atTrainer and ns.SawTrainer()
  if (saw or not ns.atTrainer) and ns.GuideEvaluate then ns.GuideEvaluate() end
end)

local talents = { dirty = true }

local function TraitTrees()
  local CT, T = C_ClassTalents, C_Traits
  if not (CT and T and CT.GetActiveConfigID and T.GetConfigInfo and T.GetGroupDisplayInfoByTreeID) then return nil, "no trait calls" end
  local config = PlainNumber(Call(CT.GetActiveConfigID))
  if not config then return nil, "no config" end
  local info = Plain(Call(T.GetConfigInfo, config))
  local tree = type(info) == "table" and type(info.treeIDs) == "table" and PlainNumber(info.treeIDs[1]) or nil
  if not tree then return nil, "config " .. config .. " no tree" end
  local groups = {}
  local shown = Plain(Call(T.GetGroupDisplayInfoByTreeID, tree))
  for _, g in ipairs(type(shown) == "table" and shown or {}) do
    local id = type(g) == "table" and PlainNumber(g.groupID)
    if id then groups[#groups + 1] = { id = id, order = PlainNumber(g.orderIndex) or #groups, name = PlainText(g.displayName) or "" } end
  end
  if #groups == 0 then return nil, "tree " .. tree .. " no groups" end
  table.sort(groups, function(a, b) return a.order < b.order end)
  local ids, counted, bought, held = {}, {}, {}, {}
  for i, g in ipairs(groups) do ids[i] = g.id end
  local spent = T.GetGroupCurrencyInfo and Plain(Call(T.GetGroupCurrencyInfo, config, ids))
  for _, c in ipairs(type(spent) == "table" and spent or {}) do
    local id = type(c) == "table" and PlainNumber(c.traitNodeGroupID)
    for _, cur in ipairs(id and type(c.currencyInfos) == "table" and c.currencyInfos or {}) do
      local n = type(cur) == "table" and PlainNumber(cur.spent)
      if n then counted[id] = (counted[id] or 0) + n end
    end
  end
  local nodes = T.GetTreeNodes and Plain(Call(T.GetTreeNodes, tree))
  for _, node in ipairs(type(nodes) == "table" and nodes or {}) do
    local n = T.GetNodeInfo and Plain(Call(T.GetNodeInfo, config, node))
    local ranks = type(n) == "table" and PlainNumber(n.ranksPurchased) or 0
    local nodeID = PlainNumber(node)
    if ranks > 0 and nodeID then held[nodeID] = ranks end
    for _, id in ipairs(ranks > 0 and type(n.groupIDs) == "table" and n.groupIDs or {}) do
      id = PlainNumber(id)
      if id then bought[id] = (bought[id] or 0) + ranks end
    end
  end
  local out, read = { points = {}, names = {}, from = "traits", ranks = held }, {}
  for i, g in ipairs(groups) do
    out.points[i], out.names[i] = counted[g.id] or bought[g.id] or 0, g.name
    read[i] = (counted[g.id] or "-") .. "/" .. (bought[g.id] or 0)
  end
  out.read = "traits " .. table.concat(read, " ")
  return out
end

local function KeepRanks(now)
  local key = ns.CharKey and ns.CharKey()
  if not (key and now.ranks) then return end
  if type(IndexOfAzerothDB) ~= "table" then IndexOfAzerothDB = {} end
  if type(IndexOfAzerothDB.talents) ~= "table" then IndexOfAzerothDB.talents = {} end
  IndexOfAzerothDB.talents[key] = { at = time(), ranks = now.ranks }
end

function ns.Talents()
  if not talents.dirty and talents.now then return talents.now end
  local now, why = TraitTrees()
  if not now then
    local spec = C_SpecializationInfo
    now = { points = {}, names = {}, read = "none: " .. why }
    if spec and spec.GetSpecializationInfo then
      for t = 1, 3 do
        local _, name, _, _, _, _, spent = Call(spec.GetSpecializationInfo, t, false, false)
        now.points[t], now.names[t] = PlainNumber(spent) or 0, PlainText(name) or ""
      end
      now.from, now.read = "spec", "spec " .. table.concat(now.points, " ") .. " (" .. why .. ")"
    end
  end
  talents.now, talents.dirty = now, false
  KeepRanks(now)
  return now
end
ns.On({ "PLAYER_ENTERING_WORLD", "TRAIT_CONFIG_UPDATED", "TRAIT_TREE_CURRENCY_INFO_UPDATED", "PLAYER_TALENT_UPDATE",
        "ACTIVE_TALENT_GROUP_CHANGED" }, function() talents.dirty = true end)

local function TalentSources()
  local level = Plain(UnitLevel("player")) or 0
  local sources, now = {}, ns.Talents()
  if C_ClassTalents and C_ClassTalents.HasUnspentTalentPoints then
    local has, classPoints, specPoints = Call(C_ClassTalents.HasUnspentTalentPoints)
    if has ~= nil then sources.traits = has and ((Plain(classPoints) or 0) + (Plain(specPoints) or 0)) or 0 end
  end
  sources.unspentGlobal = Plain(Call(GetUnspentTalentPoints, false, false))
  sources.characterPoints = Plain(Call(UnitCharacterPoints, "player"))
  if level >= 10 and now.from then
    local spent = 0
    for _, n in ipairs(now.points) do spent = spent + n end
    sources.fromSpent = math.max(0, level - 9 - spent)
  end
  return sources, level
end

function ns.UnspentTalents()
  local sources, level = TalentSources()
  local own = sources.traits or sources.unspentGlobal or sources.characterPoints
  if own then return own end
  if level >= 10 then return sources.fromSpent end
  return nil
end

function ns.PrintTalents()
  local sources = TalentSources()
  for _, key in ipairs({ "traits", "unspentGlobal", "characterPoints", "fromSpent" }) do
    ns.Print(string.format("%s: %s", key, tostring(sources[key])))
  end
  ns.Print("using: " .. tostring(ns.UnspentTalents()))
  local now, trees = ns.Talents(), {}
  for t, n in ipairs(now.points) do trees[t] = string.format("%s %d", now.names[t] ~= "" and now.names[t] or ("tree " .. t), n) end
  ns.Print("points per tree: " .. (#trees > 0 and table.concat(trees, ", ") or "none") .. ". The calls gave: " .. now.read)
end

function ns.EncodeStatus(s)
  local function Build(withText)
    local w = ns.NewWriter()
    w:u8(2)
    w:u8(s.classID)
    local keys = {}
    for name in pairs(s.nums) do keys[#keys + 1] = name end
    table.sort(keys, function(a, b) return N[a] < N[b] end)
    w:u8(#keys)
    for _, name in ipairs(keys) do w:u8(N[name]); w:var(s.nums[name]) end
    local strKeys = {}
    if withText then for name in pairs(s.strs) do strKeys[#strKeys + 1] = name end end
    w:u8(#strKeys)
    for _, name in ipairs(strKeys) do w:u8(S[name]); w:str(s.strs[name], 32) end
    local skills = withText and s.skills or {}
    w:u8(#skills)
    for _, skill in ipairs(skills) do w:str(skill.name, 24); w:u16(skill.rank); w:u16(skill.max) end
    w:u8(#s.warns)
    for _, warn in ipairs(s.warns) do w:u8(warn.key); w:u8(warn.level + (warn.quiet and QUIET or 0)) end
    return w.bytes
  end
  local bytes = Build(true)
  if #bytes > ns.MAX_PAYLOAD then bytes = Build(false) end
  return bytes
end


local TEXT = {
  ammo = { "Ammo low: %d left", "OUT OF AMMO" },
  petUnhappy = { "Your pet is unhappy (75%% damage). Feed your pet.", "Your pet is unhappy (75%% damage). Feed your pet." },
  shards = { "Soul shards low: %d left", "OUT OF SOUL SHARDS" },
  mhPoison = { "Main hand poison running out", "NO POISON ON MAIN HAND" },
  ohPoison = { "Off hand poison running out", "NO POISON ON OFF HAND" },
  poisons = { "Poisons low: %d left in bags", "NO POISONS LEFT IN BAGS" },
  water = { "Water low: %d left", "OUT OF WATER" },
  ankh = { "Ankhs low: %d left", "NO ANKH, REINCARNATION WON'T WORK" },
  earthTotem = { "", "EARTH TOTEM MISSING" },
  fireTotem = { "", "FIRE TOTEM MISSING" },
  waterTotem = { "", "WATER TOTEM MISSING" },
  airTotem = { "", "AIR TOTEM MISSING" },
  durability = { "Gear durability at %d%%", "BROKEN GEAR, REPAIR" },
}
local COUNT_OF = { ammo = "ammo", shards = "shards", poisons = "poisons", water = "water", ankh = "ankhs", durability = "durability" }

local announced = {}

function ns.QuietWarnings()
  local sh = IndexOfAzerothShared
  local q = type(sh) == "table" and type(sh.quiet) == "table" and sh.quiet or {}
  return type(q.ranks) == "table" and q.ranks or {}, type(q.low) == "table" and q.low or {}
end

local QUIET_GONE = 10
local moveSeen, moveGone, moveEnded = {}, {}, {}
local function MoveLasts(key, present, now)
  if moveEnded[key] then return false end
  if present then
    moveSeen[key], moveGone[key] = true, nil
  elseif moveSeen[key] then
    moveGone[key] = moveGone[key] or now
    if now - moveGone[key] >= QUIET_GONE then moveEnded[key] = true; return false end
  end
  return true
end

function ns.MarkQuiet(warns)
  local now, present, quietLow = GetTime(), {}, select(2, ns.QuietWarnings())
  for _, warn in ipairs(warns) do present[warn.name] = true end
  local lasts = {}
  for key, on in pairs(quietLow) do lasts[key] = on == true and MoveLasts(key, present[key], now) end
  for _, warn in ipairs(warns) do warn.quiet = warn.level == LOW and lasts[warn.name] == true or nil end
end

function ns.WarningSound()
  if not ns.Options().general.warningSound then return end
  if PlaySound and SOUNDKIT and SOUNDKIT.RAID_WARNING then PlaySound(SOUNDKIT.RAID_WARNING) end
end

function ns.AnnounceWarnings(s)
  local now, active = GetTime(), {}
  for _, warn in ipairs(s.warns) do
    if not warn.quiet then
      active[warn.name] = true
      local last = announced[warn.name]
      local every = warn.level == OUT and 60 or 300
      if not last or warn.level > last.level or now - last.at >= every then
        local text = TEXT[warn.name][warn.level]
        local count = COUNT_OF[warn.name] and s.nums[COUNT_OF[warn.name]]
        text = text:format(count or 0)
        if ns.Banner then ns.Banner(text) end
        ns.WarningSound()
        announced[warn.name] = { level = warn.level, at = now }
      elseif warn.level < last.level then
        last.level = warn.level
      end
    end
  end
  local quietRanks, outdated = ns.QuietWarnings(), {}
  for _, r in ipairs(s.ranks or {}) do outdated[r.name] = r.best end
  local moved = {}
  for name, best in pairs(quietRanks) do
    if best ~= 0 then moved[name] = MoveLasts("rank:" .. name, outdated[name] == best, now) end
  end
  for _, r in ipairs(s.ranks or {}) do
    local key, quiet = "rank:" .. r.name, quietRanks[r.name]
    if quiet ~= 0 and not (quiet == r.best and moved[r.name]) then
      active[key] = true
      if not announced[key] then
        if ns.Banner then ns.Banner(string.format("%s Rank %d isn't on your bars. Your bars have Rank %d.", r.name, r.best, r.have)) end
        ns.WarningSound()
        announced[key] = { level = LOW, at = now }
      end
    end
  end
  for name in pairs(announced) do
    if not active[name] then announced[name] = nil end
  end
end

local BANNER_LINES, BANNER_WIDTH, BANNER_HOLD, BANNER_FADE = 4, 800, 10, 3
local BANNER_FADE_IN, BANNER_GROW, BANNER_SHRINK = 0.2, 0.2, 0.4
local BANNER_HEIGHT, BANNER_POP = 20, 30
local banner = CreateFrame("Frame", "IndexOfAzerothBanner", UIParent)
banner:SetSize(BANNER_WIDTH, BANNER_HEIGHT * BANNER_LINES)
banner:SetPoint("TOP", UIParent, "TOP", 0, -182)
banner:SetFrameStrata("HIGH")
banner:Hide()
local bannerShown, bannerSpare = {}, {}

local function BannerLayout()
  for i, line in ipairs(bannerShown) do
    line.text:ClearAllPoints()
    if i == 1 then line.text:SetPoint("TOP", banner, "TOP") else line.text:SetPoint("TOP", bannerShown[i - 1].text, "BOTTOM") end
  end
end

local function BannerDrop(i)
  local line = table.remove(bannerShown, i)
  line.text:Hide()
  bannerSpare[#bannerSpare + 1] = line.text
end

local function BannerTick(self)
  local now, dropped = GetTime(), false
  for i = #bannerShown, 1, -1 do
    local line = bannerShown[i]
    local age = now - line.at
    if age >= BANNER_HOLD + BANNER_FADE then
      BannerDrop(i)
      dropped = true
    else
      local alpha = 1
      if age < BANNER_FADE_IN then alpha = age / BANNER_FADE_IN
      elseif age > BANNER_HOLD then alpha = 1 - (age - BANNER_HOLD) / BANNER_FADE end
      line.text:SetAlpha(alpha)
      local height = BANNER_HEIGHT
      if age < BANNER_GROW then height = BANNER_HEIGHT + (BANNER_POP - BANNER_HEIGHT) * age / BANNER_GROW
      elseif age < BANNER_GROW + BANNER_SHRINK then
        height = BANNER_POP - (BANNER_POP - BANNER_HEIGHT) * (age - BANNER_GROW) / BANNER_SHRINK
      end
      line.text:SetTextHeight(height)
    end
  end
  if dropped then BannerLayout() end
  if #bannerShown == 0 then self:Hide() end
end
ns.OnTick(banner, "the warnings' banner", nil, BannerTick)

function ns.Banner(text)
  if #bannerShown >= BANNER_LINES then BannerDrop(1) end
  local fontString = table.remove(bannerSpare) or banner:CreateFontString(nil, "ARTWORK", "GameFontNormalHuge")
  local color = ChatTypeInfo and ChatTypeInfo.RAID_WARNING
  fontString:SetWidth(BANNER_WIDTH)
  fontString:SetJustifyH("CENTER")
  fontString:SetTextColor(color and color.r or 1, color and color.g or 0.28, color and color.b or 0, 1)
  fontString:SetTextHeight(BANNER_HEIGHT)
  fontString:SetAlpha(0)
  fontString:SetText(text)
  fontString:Show()
  bannerShown[#bannerShown + 1] = { text = fontString, at = GetTime() }
  BannerLayout()
  banner:Show()
end


ns.LEVELS_KEPT = 30
local STAT_KEYS = { "str", "agi", "sta", "int", "spi" }

local function BookOfMine(book)
  local list = type(book.list) == "table" and book.list or {}
  local newest = list[#list]
  local _, raceFile = Call(UnitRace, "player")
  local race, was = PlainText(raceFile), type(newest) == "table" and newest.race or nil
  return not race or (was or "") == "" or was == race
end

local function LevelBook()
  local key = ns.CharKey()
  if not key then return end
  if type(IndexOfAzerothDB) ~= "table" then IndexOfAzerothDB = {} end
  if type(IndexOfAzerothDB.levels) ~= "table" then IndexOfAzerothDB.levels = {} end
  local levels = IndexOfAzerothDB.levels
  local old = ns.NameKey()
  if old ~= key and type(levels[key]) ~= "table" and type(levels[old]) == "table" and BookOfMine(levels[old]) then
    levels[key], levels[old] = levels[old], nil
  end
  local mine = levels[key]
  if type(mine) ~= "table" then mine = {}; levels[key] = mine end
  if type(mine.list) ~= "table" then mine.list = {} end
  return mine
end

local function BaseStats()
  local out = {}
  for i = 1, 5 do
    local base = PlainNumber(Call(UnitStat, "player", i))
    if not base then return nil end
    out[i] = base
  end
  return out
end

local function LevelStart()
  local mine = LevelBook()
  if not mine then return end
  local level = PlainNumber(UnitLevel("player"))
  if type(mine.start) ~= "table" or mine.start.level ~= level then
    mine.start = { level = level, money = PlainNumber(GetMoney()), seen = false, base = BaseStats() }
  elseif not mine.start.base then
    mine.start.base = BaseStats()
  end
end

function ns.LevelUp(level, health, power, talents)
  local mine = LevelBook()
  level = PlainNumber(level)
  if not mine or not level then return end
  local money = PlainNumber(GetMoney())
  local start = type(mine.start) == "table" and mine.start or {}
  local since = played.at and (GetTime() - played.at) or nil
  local _, raceFile = Call(UnitRace, "player")
  local _, _, classId = Call(UnitClass, "player")
  local rec = { level = level, at = time(), money = money, zone = PlainText(Call(GetZoneText)) or "",
    played = played.total and since and math.floor(played.total + since) or nil,
    levelPlayed = played.level and since and math.floor(played.level + since) or nil,
    gold = (start.seen and start.level == level - 1 and start.money and money) and (money - start.money) or nil,
    health = PlainNumber(health), mana = PlainNumber(power), talents = PlainNumber(talents),
    race = PlainText(raceFile), class = PlainNumber(classId) }
  local list = mine.list
  list[#list + 1] = rec
  while #list > ns.LEVELS_KEPT do table.remove(list, 1) end
  local was = start.level == level - 1 and start.base or nil
  mine.start = { level = level, money = money, seen = true }
  local function Gains()
    local now = BaseStats()
    if now and was then
      for i, k in ipairs(STAT_KEYS) do rec[k] = now[i] - was[i] end
    end
    mine.start.base = now
  end
  if C_Timer and C_Timer.After then C_Timer.After(2, Gains) else Gains() end
  return rec
end


ns.POLAROID_GLOW = 4
ns.POLAROID_COMBAT = 120
ns.POLAROID_BACK = 3
ns.POLAROID_SETTLE = 0.1

local snap = { rec = nil, waitUntil = nil, hidden = false, mine = false, token = 0 }
ns.polaroid = snap

local function Fighting()
  return (InCombatLockdown and InCombatLockdown()) or ns.InFight()
end

local function InterfaceBack()
  if not snap.hidden then return end
  snap.hidden = false
  if snap.mine then pcall(SetUIVisibility, true) end
  snap.mine = false
end

function ns.PolaroidShoot(rec)
  if snap.hidden or type(Screenshot) ~= "function" or type(SetUIVisibility) ~= "function" then return false end
  snap.token = snap.token + 1
  local token = snap.token
  snap.hidden, snap.rec = true, rec
  snap.mine = not UIParent or UIParent:IsShown() and true or false
  if snap.mine then pcall(SetUIVisibility, false) end
  local function Shoot()
    if snap.token ~= token or not snap.hidden then return end
    if not pcall(Screenshot) then return InterfaceBack() end
    if C_Timer and C_Timer.After then
      C_Timer.After(ns.POLAROID_BACK, function() if snap.token == token then InterfaceBack() end end)
    end
  end
  if C_Timer and C_Timer.After then C_Timer.After(ns.POLAROID_SETTLE, Shoot) else Shoot() end
  return true
end

local function PolaroidReady(rec)
  if Plain(Call(UnitIsDeadOrGhost, "player")) == true then return end
  if Fighting() then
    snap.waitUntil, snap.waiting = GetTime() + ns.POLAROID_COMBAT, rec
    return
  end
  snap.waitUntil, snap.waiting = nil, nil
  ns.PolaroidShoot(rec)
end

function ns.PolaroidAfterLevelUp(rec)
  local o = ns.Options and ns.Options().polaroid
  if o and not o.on then return end
  if C_Timer and C_Timer.After then C_Timer.After(ns.POLAROID_GLOW, function() PolaroidReady(rec) end) else PolaroidReady(rec) end
end

ns.On({ "SCREENSHOT_SUCCEEDED", "SCREENSHOT_FAILED", "PLAYER_REGEN_ENABLED" }, function(event)
  if event == "PLAYER_REGEN_ENABLED" then
    if snap.waitUntil then
      local late, rec = GetTime() > snap.waitUntil, snap.waiting
      snap.waitUntil, snap.waiting = nil, nil
      if not late then PolaroidReady(rec) end
    end
    return
  end
  if not snap.hidden then return end
  if event == "SCREENSHOT_SUCCEEDED" and type(snap.rec) == "table" then snap.rec.shot = time() end
  snap.rec = nil
  InterfaceBack()
end)

ns.commands = ns.commands or {}
ns.commands.polaroid = function(arg)
  if arg == "on" or arg == "off" then
    ns.Options().polaroid.on = arg == "on"
    if ns.OptionsChanged then ns.OptionsChanged() end
    return ns.Print(ns.SwitchWords(ns.Word("game.chat.switch.name.polaroid"), arg == "on", "polaroid"))
  end
  if Fighting() then return ns.Print("The level-up picture waits until you are out of combat. Try /ioa polaroid again after the fight.") end
  if ns.PolaroidShoot(nil) then
    ns.Print("The addon hides the interface for a moment and takes a screenshot. You find the screenshot in the game's Screenshots folder.")
  else
    ns.Print("The game didn't take the screenshot. The addon tries again with your next /ioa polaroid.")
  end
end


ns.On({ "PLAYER_LOGIN", "BAG_UPDATE_DELAYED", "GET_ITEM_INFO_RECEIVED", "PLAYER_XP_UPDATE", "PLAYER_REGEN_ENABLED",
        "QUEST_TURNED_IN", "TIME_PLAYED_MSG", "PLAYER_LEVEL_UP" }, function(event, ...)
  if event == "PLAYER_LOGIN" then
    session.start = GetTime()
    session.moneyStart = Plain(GetMoney()) or 0
    LevelStart()
    OnXP()
    bags.dirty = true
    if C_Timer and C_Timer.After then C_Timer.After(5, ns.AskPlayed) end
  elseif event == "TIME_PLAYED_MSG" then
    local total, level = ...
    played.total, played.level, played.at = Plain(total), Plain(level), GetTime()
    Unhush()
  elseif event == "PLAYER_LEVEL_UP" then
    local rec = ns.LevelUp(...)
    if rec then ns.PolaroidAfterLevelUp(rec) end
    if C_Timer and C_Timer.After then C_Timer.After(2, ns.AskPlayed) end
  elseif event == "BAG_UPDATE_DELAYED" or event == "GET_ITEM_INFO_RECEIVED" then
    bags.dirty = true
  elseif event == "PLAYER_XP_UPDATE" then
    OnXP()
  elseif event == "PLAYER_REGEN_ENABLED" then
    session.combatEnded = GetTime()
  elseif event == "QUEST_TURNED_IN" then
    session.questTurnedIn = GetTime()
  end
end)


local MANAGED = { "IndexOfAzeroth", "AtlasLoot" }
local ADDON_LOADED, ADDON_MISSING, ADDON_DISABLED, ADDON_NOT_LOADED = 1, 2, 3, 4

local function AddonState(name)
  local loaded = C_AddOns and C_AddOns.IsAddOnLoaded and Call(C_AddOns.IsAddOnLoaded, name)
  local getMeta = C_AddOns and C_AddOns.GetAddOnMetadata or GetAddOnMetadata
  if loaded then return ADDON_LOADED, Call(getMeta, name, "Version") or "" end
  local getInfo = C_AddOns and C_AddOns.GetAddOnInfo or GetAddOnInfo
  local _, _, _, _, reason = Call(getInfo, name)
  reason = Plain(reason)
  if reason == "MISSING" then return ADDON_MISSING, "" end
  if reason == "DISABLED" or reason == "DEP_DISABLED" then return ADDON_DISABLED, reason end
  return ADDON_NOT_LOADED, reason or ""
end

function ns.EncodeAddons()
  local w = ns.NewWriter()
  w:u8(10)
  w:u8(#MANAGED)
  for _, name in ipairs(MANAGED) do
    local state, text = AddonState(name)
    w:str(name, 16); w:u8(state); w:str(text or "", 24)
  end
  return w.bytes
end


local PROFESSIONS = { Alchemy = true, Blacksmithing = true, Enchanting = true, Engineering = true, Herbalism = true,
  Leatherworking = true, Mining = true, Skinning = true, Tailoring = true, Jewelcrafting = true, Inscription = true,
  Cooking = true, ["First Aid"] = true, Fishing = true, Lockpicking = true }

function ns.NameParts()
  local first, second = Call(UnitFullName, "player")
  first, second = Plain(first), Plain(second)
  if not first then first, second = Call(UnitName, "player"); first, second = Plain(first), Plain(second) end
  first = first or ""
  if not second and first:find("-", 1, true) then first, second = first:match("^([^-]+)%-(.+)$") end
  local realm = Plain(Call(GetRealmName)) or ""
  local normalized = Plain(Call(GetNormalizedRealmName)) or realm:gsub("[%s%-]", "")
  local surname = second
  if surname then surname = surname:match("^([^-]+)") end
  if surname == realm or surname == normalized then surname = nil end
  return first, surname or "", realm
end


local playerGuid

function ns.PlayerGuid()
  if (playerGuid or "") == "" then playerGuid = Plain(Call(UnitGUID, "player")) or "" end
  return playerGuid or ""
end

function ns.NameKey()
  local first, surname, realm = ns.NameParts()
  if first == "" then return nil end
  local full = surname ~= "" and (first .. " " .. surname) or first
  return realm ~= "" and (full .. "-" .. realm) or full
end

function ns.CharKey()
  local guid = ns.PlayerGuid()
  return guid ~= "" and guid or ns.NameKey()
end

function ns.IsMe(who)
  if type(who) ~= "table" or (who.name or "") == "" then return false end
  local first, surname, realm = ns.NameParts()
  local guid = ns.PlayerGuid()
  if (who.guid or "") ~= "" and guid ~= "" then return who.guid == guid end
  return who.name == first and (who.surname == nil or who.surname == surname)
    and ((who.realm or "") == "" or realm == "" or who.realm == realm)
end

function ns.ClaimCharDB()
  if type(IndexOfAzerothCharDB) ~= "table" then IndexOfAzerothCharDB = {} end
  local guid = ns.PlayerGuid()
  if guid == "" then return end
  if (IndexOfAzerothCharDB.guid or "") ~= "" and IndexOfAzerothCharDB.guid ~= guid then IndexOfAzerothCharDB = {} end
  IndexOfAzerothCharDB.guid = guid
end

function ns.EncodeCharacter()
  local name, surname, realm = ns.NameParts()
  local profs = {}
  for skill, info in pairs(Skills()) do
    if PROFESSIONS[skill] then profs[#profs + 1] = { name = skill, rank = Plain(info.rank) or 0, max = Plain(info.maxRank) or 0 } end
  end
  table.sort(profs, function(a, b) return a.name < b.name end)
  local _, raceFile = Call(UnitRace, "player")
  local w = ns.NewWriter()
  w:u8(13)
  w:str(name, 24); w:str(surname, 24); w:str(realm, 32); w:str(Plain(raceFile) or "", 16)
  w:u8(math.min(#profs, 8))
  for i = 1, math.min(#profs, 8) do
    local p = profs[i]
    w:str(p.name, 16); w:u16(p.rank); w:u16(p.max)
  end
  w:str(ns.PlayerGuid(), 40)
  return w.bytes
end


local UNREACHABLE = 2

local function NameHash(name)
  local h = 0
  for i = 1, #name do h = (h * 31 + name:byte(i)) % 65521 end
  return h
end
ns.NameHash = NameHash

local function ReadTaxi()
  local cdb = IndexOfAzerothCharDB
  if not cdb then return end
  local found = false
  if C_TaxiMap and C_TaxiMap.GetAllTaxiNodes then
    local mapID = (GetTaxiMapID and Plain(Call(GetTaxiMapID))) or (C_Map and Plain(Call(C_Map.GetBestMapForUnit, "player")))
    local ok, nodes = pcall(C_TaxiMap.GetAllTaxiNodes, mapID)
    if ok and type(nodes) == "table" and #nodes > 0 then
      cdb.taxi = cdb.taxi or {}
      for _, n in ipairs(nodes) do
        local id = Plain(n.nodeID)
        if id then cdb.taxi[id] = (Plain(n.state) ~= UNREACHABLE) or nil end
      end
      found = true
    end
  end
  if not found and NumTaxiNodes then
    cdb.taxiNames = cdb.taxiNames or {}
    for i = 1, Plain(Call(NumTaxiNodes)) or 0 do
      local name, kind = Plain(Call(TaxiNodeName, i)), Plain(Call(TaxiNodeGetType, i))
      if name then cdb.taxiNames[name] = (kind ~= "NONE") or nil end
    end
  end
end

ns.On("TAXIMAP_OPENED", function() pcall(ReadTaxi) end)

function ns.EncodeTaxi()
  local cdb = IndexOfAzerothCharDB
  if not cdb or not (cdb.taxi or cdb.taxiNames) then return nil end
  local ids, hashes = {}, {}
  for id in pairs(cdb.taxi or {}) do ids[#ids + 1] = id end
  for name in pairs(cdb.taxiNames or {}) do hashes[#hashes + 1] = NameHash(name) end
  table.sort(ids); table.sort(hashes)
  local w = ns.NewWriter()
  w:u8(14)
  w:u8(math.min(#ids, 80))
  for i = 1, math.min(#ids, 80) do w:u16(ids[i]) end
  w:u8(math.min(#hashes, 80))
  for i = 1, math.min(#hashes, 80) do w:u16(hashes[i]) end
  return w.bytes
end


local MAX_BONUSES = 4
ns.MAX_BONUSES = MAX_BONUSES

function ns.ItemBonuses(link)
  local body = PlainText(link)
  body = body and body:match("item:([%-%d:]*)")
  local out = {}
  if not body then return out end
  local fields, at = {}, 1
  while true do
    local stop = body:find(":", at, true)
    fields[#fields + 1] = tonumber(body:sub(at, stop and stop - 1 or #body)) or 0
    if not stop then break end
    at = stop + 1
  end
  for i = 14, 13 + math.min(fields[13] or 0, MAX_BONUSES) do
    if (fields[i] or 0) > 0 then out[#out + 1] = fields[i] end
  end
  return out
end

function ns.ItemKey(id, bonuses)
  if not bonuses or #bonuses == 0 then return tostring(id) end
  local sorted = {}
  for i, b in ipairs(bonuses) do sorted[i] = b end
  table.sort(sorted)
  return id .. ":" .. table.concat(sorted, ":")
end

function ns.WriteBonuses(w, bonuses)
  w:u8(#bonuses)
  for _, b in ipairs(bonuses) do w:var(b) end
end


function ns.EncodeEquipped()
  local w = ns.NewWriter()
  w:u8(15)
  w:u8(18)
  local bonuses = {}
  for slot = 1, 18 do
    local id = Plain(Call(GetInventoryItemID, "player", slot)) or 0
    w:u24(id)
    bonuses[slot] = id > 0 and ns.ItemBonuses(Call(GetInventoryItemLink, "player", slot)) or {}
  end
  for slot = 1, 18 do ns.WriteBonuses(w, bonuses[slot]) end
  return w.bytes
end


local CONTAINER_EVERY = 60
local PAGE_HEAD = 13
local WHERE = { bags = 1, bank = 2, warband = 3 }
local BI = Enum and Enum.BagIndex or {}
local function Range(first, last)
  local t = {}
  for i = first, last do t[#t + 1] = i end
  return t
end
local LISTS = {
  bags = Range(BI.Backpack or 0, BI.ReagentBag or 5),
  bank = Range(BI.CharacterBankTab_1 or 6, BI.CharacterBankTab_9 or 14),
  warband = Range(BI.AccountBankTab_1 or 15, BI.AccountBankTab_9 or 23),
}

local function ReadContainers(list, withBags)
  local items, free, slots, each, sfx = {}, 0, 0, withBags and {} or nil, {}
  for _, bag in ipairs(list) do
    local n = Plain(Call(C_Container.GetContainerNumSlots, bag)) or 0
    slots = slots + n
    local empty = 0
    for slot = 1, n do
      local id = Plain(Call(C_Container.GetContainerItemID, bag, slot))
      if id then
        local info = Call(C_Container.GetContainerItemInfo, bag, slot)
        local count = (info and Plain(info.stackCount)) or 1
        items[id] = (items[id] or 0) + count
        local link = info and PlainText(info.hyperlink) or Call(C_Container.GetContainerItemLink, bag, slot)
        local bonuses = ns.ItemBonuses(link)
        if #bonuses > 0 then
          local key = ns.ItemKey(id, bonuses)
          sfx[key] = (sfx[key] or 0) + count
        end
      else
        free, empty = free + 1, empty + 1
      end
    end
    if each and n > 0 then
      local inv = bag > 0 and Plain(Call(C_Container.ContainerIDToInventoryID, bag))
      local _, family = Call(C_Container.GetContainerNumFreeSlots, bag)
      each[#each + 1] = { id = inv and Plain(Call(GetInventoryItemID, "player", inv)) or 0, slots = n, free = empty,
                          family = Plain(family) or 0 }
    end
  end
  return { at = time(), items = items, free = free, slots = slots, each = each, sfx = next(sfx) and sfx or nil }
end

local bankOpen = false
local fresh = {}
local function ReadBank()
  local cdb = IndexOfAzerothCharDB
  if not cdb or not bankOpen then return end
  for _, which in ipairs({ "bank", "warband" }) do
    local snap = ReadContainers(LISTS[which])
    if snap.slots > 0 then cdb[which] = snap; fresh[which] = true end
  end
end

ns.On({ "BANKFRAME_OPENED", "BANKFRAME_CLOSED", "BAG_UPDATE_DELAYED", "PLAYERBANKSLOTS_CHANGED",
        "PLAYER_ACCOUNT_BANK_TAB_SLOTS_CHANGED", "BANK_TABS_CHANGED" }, function(event)
  if event == "BANKFRAME_CLOSED" then bankOpen = false; return end
  if event == "BANKFRAME_OPENED" then
    bankOpen = true
    if C_Timer then C_Timer.After(1, function() pcall(ReadBank) end) end
  end
  pcall(ReadBank)
end)

local out = {}

local function SuffixedById(snap)
  local out = {}
  for key, n in pairs(snap.sfx or {}) do
    local id, rest = tostring(key):match("^(%d+):([%d:]+)$")
    if id then
      local bonuses = {}
      for b in rest:gmatch("%d+") do bonuses[#bonuses + 1] = tonumber(b) end
      id = tonumber(id)
      out[id] = out[id] or {}
      table.insert(out[id], { key = key, bonuses = bonuses, n = n })
    end
  end
  for _, list in pairs(out) do table.sort(list, function(a, b) return a.key < b.key end) end
  return out
end

local SUFFIX_HEAD = 2

local function Pages(which, snap)
  local ids = {}
  for id in pairs(snap.items) do ids[#ids + 1] = id end
  table.sort(ids)
  local bagLines = 0
  if snap.each then
    bagLines = 1
    for _, b in ipairs(snap.each) do bagLines = bagLines + 5 + ns.VarSize(b.family) end
  end
  local sfx = SuffixedById(snap)
  local function SuffixSize(id)
    local size = 0
    for _, e in ipairs(sfx[id] or {}) do
      size = size + 4 + ns.VarSize(e.n)
      for _, b in ipairs(e.bonuses) do size = size + ns.VarSize(b) end
    end
    return size, #(sfx[id] or {})
  end
  local full = ns.MAX_PAYLOAD - PAGE_HEAD - SUFFIX_HEAD
  local groups, group, room, marked = {}, {}, full - bagLines, 0
  for _, id in ipairs(ids) do
    local extra, k = SuffixSize(id)
    local size = 3 + ns.VarSize(snap.items[id]) + extra
    if #group == 255 or size > room or marked + k > 255 then groups[#groups + 1], group, room, marked = group, {}, full, 0 end
    group[#group + 1] = id
    room, marked = room - size, marked + k
  end
  groups[#groups + 1] = group
  local pages = {}
  for p, list in ipairs(groups) do
    local w = ns.NewWriter()
    w:u8(16); w:u8(WHERE[which])
    w:u16(snap.at % 65536); w:u16(math.floor(snap.at / 65536))
    w:u8(p); w:u8(#groups); w:u16(snap.free); w:u16(snap.slots)
    w:u8(#list)
    for _, id in ipairs(list) do w:u24(id); w:var(snap.items[id]) end
    local suffixed = {}
    for _, id in ipairs(list) do
      for _, e in ipairs(sfx[id] or {}) do suffixed[#suffixed + 1] = { id = id, e = e } end
    end
    if p == 1 and snap.each then
      w:u8(#snap.each)
      for _, b in ipairs(snap.each) do w:u24(b.id); w:u8(b.slots); w:u8(b.free); w:var(b.family) end
    elseif #suffixed > 0 then
      w:u8(0)
    end
    if #suffixed > 0 then
      w:u8(#suffixed)
      for _, s in ipairs(suffixed) do w:u24(s.id); ns.WriteBonuses(w, s.e.bonuses); w:var(s.e.n) end
    end
    pages[p] = w.bytes
  end
  return pages
end

function ns.ContainerPending()
  for _, which in ipairs({ "bank", "warband" }) do
    if fresh[which] then return which end
  end
end

function ns.NextContainerFrame(which)
  local cdb = IndexOfAzerothCharDB
  local snap = which == "bags" and ReadContainers(LISTS.bags, true) or cdb and cdb[which]
  if not snap or not snap.items then return nil end
  local o = out[which] or {}
  out[which] = o
  local parts = { snap.free, snap.slots }
  for id, n in pairs(snap.items) do parts[#parts + 1] = id .. "x" .. n end
  for key, n in pairs(snap.sfx or {}) do parts[#parts + 1] = "s" .. key .. "x" .. n end
  for i, b in ipairs(snap.each or {}) do parts[#parts + 1] = "b" .. i .. ":" .. b.id .. ":" .. b.free end
  table.sort(parts, function(a, b) return tostring(a) < tostring(b) end)
  local key = table.concat(parts, ",")
  if key ~= o.key then
    o.key, o.pages, o.next = key, Pages(which, snap), 1
  elseif o.next > #o.pages then
    if GetTime() - (o.sent or 0) < CONTAINER_EVERY then
      fresh[which] = nil
      if which == "bags" then watch.hurry = false end
      return nil
    end
    o.next = 1
  end
  local bytes = o.pages[o.next]
  o.next = o.next + 1
  if o.next > #o.pages then o.sent = GetTime(); fresh[which] = nil end
  if which == "bags" and watch.hurry then
    if o.next <= #o.pages then ns.MarkChanged("bags") else watch.hurry = false end
  end
  return bytes
end


local prof = { npc = 0, line = "", reads = {}, turn = 0, open = false, asked = false, fresh = false, last = nil,
  RANK = 1, TRAINED = 2, NOT_YET = 4, NO_COLOUR = 4, EVERY = 60,
  COLOURS = { "orange", "yellow", "green", "grey", "without a colour" } }

function prof.And(list)
  if #list < 2 then return list[1] or "" end
  return table.concat(list, ", ", 1, #list - 1) .. " and " .. list[#list]
end
ns.AndList = prof.And

prof.trainer = ns.Pager({ type = 25, head = 30,
  writeHead = function(w, page) w:u24(prof.npc); w:str(prof.line, 24); w:u16(#page) end,
  entry = function(w, r, before)
    if before then w:var(r[1] - before[1]) else w:u24(r[1]) end
    w:var(r[2]); w:u8(r[3]); w:var(r[4]); w:u8(r[5])
    if r[5] % 2 == prof.RANK then w:str(r[6], 16) end
  end })

function prof.Service(i)
  local name, sub, state = Call(GetTrainerServiceInfo, i)
  state = Plain(state)
  local tip = state ~= "header" and Call(C_TooltipInfo.GetTrainerService, i)
  local id = type(tip) == "table" and PlainNumber(tip.id)
  if not id or id <= 0 then return nil end
  local _, skill = Call(GetTrainerServiceSkillReq, i)
  return { id, math.max(0, math.floor(PlainNumber(Call(GetTrainerServiceCost, i)) or 0)),
    math.max(0, math.min(255, PlainNumber(Call(GetTrainerServiceLevelReq, i)) or 0)), math.max(0, math.floor(PlainNumber(skill) or 0)),
    (state == "used" and prof.TRAINED or 0) + (state == "unavailable" and prof.NOT_YET or 0), PlainText(sub) or "",
    name = PlainText(name), line = PlainText(Call(GetTrainerServiceSkillLine, i)) }
end

function prof.Trainer()
  if ns.readingTrainer then return false end
  local kind = C_Trainer and PlainNumber(Call(C_Trainer.GetTrainerType))
  local tradeskill = Enum and Enum.TrainerType and kind == Enum.TrainerType.Tradeskills
  if not (tradeskill or Plain(Call(IsTradeskillTrainer)) == true) or not (C_TooltipInfo and C_TooltipInfo.GetTrainerService) then
    return false
  end
  local who, _, _, npcID = ns.Geo.Creature(Plain(Call(UnitGUID, "npc")))
  local rows, count, main = {}, {}, nil
  ns.EveryTrainerService(function()
    for i = 1, math.min(PlainNumber(Call(GetNumTrainerServices)) or 0, 400) do
      local r = prof.Service(i)
      if r then
        rows[#rows + 1] = r
        if r.line then
          count[r.line] = (count[r.line] or 0) + 1
          if not main or count[r.line] > count[main] then main = r.line end
        end
      end
    end
  end)
  if #rows == 0 then return false end
  table.sort(rows, function(a, b) return a[1] < b[1] end)
  for _, r in ipairs(rows) do
    if r[5] % (2 * prof.TRAINED) >= prof.TRAINED then watch.Saw(r[1], true) end
  end
  local npc = who == "Creature" and npcID or 0
  local said = { npc, main or "" }
  for _, r in ipairs(rows) do
    if main and r.name == main then r[5] = r[5] + prof.RANK end
    said[#said + 1] = table.concat(r, ":")
  end
  prof.npc, prof.line, prof.last = npc, main or "", rows
  prof.trainer.Offer(rows, table.concat(said, ","))
  return true
end
ns.ProfTrainerPending, ns.NextProfTrainerFrame = prof.trainer.Pending, prof.trainer.Next
ns.On({ "TRAINER_SHOW", "TRAINER_UPDATE" }, prof.Trainer)

prof.book = ns.Pager({ type = 26, head = 43, every = prof.EVERY,
  writeHead = function(w, page)
    local h = prof.head
    w:u16(h.line); w:u16(h.skill); w:u16(h.max); w:u16(h.second); w:u16(h.secondSkill); w:u16(h.secondMax)
    w:u16(h.at % 65536); w:u16(math.floor(h.at / 65536)); w:str(h.name, 24); w:u16(#page)
  end,
  entry = function(w, r, before)
    if before then w:var(r[1] - before[1]) else w:u24(r[1]) end
    w:u8(r[2])
  end })

function prof.Colour(info)
  local c = PlainNumber(info.relativeDifficulty)
  return c and c >= 0 and c < prof.NO_COLOUR and c or prof.NO_COLOUR
end

function prof.Recipes()
  local ui = C_TradeSkillUI
  if not (prof.open and ui) or Plain(Call(ui.IsTradeSkillReady)) == false or Plain(Call(ui.IsDataSourceChanging))
      or Plain(Call(ui.IsTradeSkillLinked)) or Plain(Call(ui.IsTradeSkillGuild)) or Plain(Call(ui.IsNPCCrafting)) then
    return false
  end
  local base, second = Call(ui.GetBaseProfessionInfo), Call(ui.GetChildProfessionInfo)
  second = type(second) == "table" and second or {}
  local head = type(base) == "table" and { name = PlainText(base.professionName), line = PlainNumber(base.professionID),
    skill = PlainNumber(base.skillLevel), max = PlainNumber(base.maxSkillLevel), second = PlainNumber(second.professionID) or 0,
    secondSkill = PlainNumber(second.skillLevel) or 0, secondMax = PlainNumber(second.maxSkillLevel) or 0, at = time() }
  local ids = Call(ui.GetAllRecipeIDs)
  if not (head and head.name and head.line and head.skill and head.max) or type(ids) ~= "table" then return false end
  local rows = {}
  for _, id in ipairs(ids) do
    id = PlainNumber(id)
    local info, learnt = id and Call(ui.GetRecipeInfo, id), nil
    if type(info) == "table" then learnt = Plain(info.learned) end
    if learnt == true then rows[#rows + 1] = { id, prof.Colour(info) } end
    watch.Saw(id, learnt)
  end
  table.sort(rows, function(a, b) return a[1] < b[1] end)
  local said = { head.name, head.line, head.skill, head.max, head.second, head.secondSkill, head.secondMax }
  for _, r in ipairs(rows) do said[#said + 1] = r[1] .. ":" .. r[2] end
  local read = { rows = rows, said = table.concat(said, ","), head = head }
  prof.reads[head.name], prof.head = read, head
  prof.book.Offer(rows, read.said, prof.fresh)
  prof.fresh = false
  return true
end

prof.book.refill = function()
  local names = {}
  for name in pairs(prof.reads) do names[#names + 1] = name end
  if #names == 0 then return end
  table.sort(names)
  prof.turn = prof.turn % #names + 1
  local read = prof.reads[names[prof.turn]]
  prof.head = read.head
  prof.book.Offer(read.rows, read.said, true)
end
ns.RecipesPending, ns.NextRecipesFrame = prof.book.Pending, prof.book.Next

ns.On({ "TRADE_SKILL_SHOW", "TRADE_SKILL_DATA_SOURCE_CHANGED", "TRADE_SKILL_LIST_UPDATE", "NEW_RECIPE_LEARNED",
        "TRADE_SKILL_CLOSE" }, function(event)
  if event == "TRADE_SKILL_CLOSE" then prof.open = false; return end
  if event == "TRADE_SKILL_SHOW" or event == "TRADE_SKILL_DATA_SOURCE_CHANGED" then prof.open, prof.fresh = true, true end
  if prof.asked then return end
  prof.asked = true
  C_Timer.After(0.5, function()
    prof.asked = false
    local ok, err = pcall(prof.Recipes)
    if not ok then ns.Report("recipes", err) end
  end)
end)


function prof.Info(info)
  if type(info) ~= "table" then return "nothing" end
  return string.format("%s, line %s, profession %s, skill %s of %s", tostring((PlainText(info.professionName))),
    tostring((PlainNumber(info.professionID))), tostring((PlainNumber(info.profession))), tostring((PlainNumber(info.skillLevel))),
    tostring((PlainNumber(info.maxSkillLevel))))
end

function prof.Count(list, known)
  if type(list) ~= "table" then return "nothing" end
  local n = 0
  for _, id in ipairs(list) do if known[PlainNumber(id) or 0] then n = n + 1 end end
  return string.format("a list of %d, %d of them known in the window", #list, n)
end

function ns.PrintProfessions()
  local ui, Say = C_TradeSkillUI or {}, ns.Print
  Say(string.format("window %s: ready %s, someone else's %s, a guild's %s, an NPC's %s", prof.open and "open" or "closed",
    tostring(Plain(Call(ui.IsTradeSkillReady))), tostring(Plain(Call(ui.IsTradeSkillLinked))),
    tostring(Plain(Call(ui.IsTradeSkillGuild))), tostring(Plain(Call(ui.IsNPCCrafting)))))
  Say("its profession: " .. prof.Info(Call(ui.GetBaseProfessionInfo)) .. ". Its second line: " .. prof.Info(Call(ui.GetChildProfessionInfo)))
  local ids, known, colours, n = Call(ui.GetAllRecipeIDs), {}, { 0, 0, 0, 0, 0 }, 0
  ids = type(ids) == "table" and ids or {}
  for k = 1, #ids do
    local id = ids[k]
    local info = PlainNumber(id) and Call(ui.GetRecipeInfo, id)
    if type(info) == "table" and Plain(info.learned) == true then
      local c = prof.Colour(info) + 1
      known[id], colours[c], n = true, colours[c] + 1, n + 1
    end
  end
  local by = {}
  for k, count in ipairs(colours) do by[k] = count .. " " .. prof.COLOURS[k] end
  Say(string.format("recipes: %d listed, you know %d: %s", #ids, n, prof.And(by)))
  for i = 1, PlainNumber(Call(C_SkillInfo.GetNumSkillLines)) or 0 do
    local s = Call(C_SkillInfo.GetSkillLineInfo, i)
    local name = type(s) == "table" and not Plain(s.isHeader) and PlainText(s.name)
    local line = name and PROFESSIONS[name] and PlainNumber(s.skillID)
    if line then
      local info = Call(ui.GetProfessionInfoBySkillLineID, line)
      local enum = type(info) == "table" and PlainNumber(info.profession) or nil
      Say(string.format("%s, line %d: GetProfessionSpells(%d) gives %s. GetProfessionSpells(%s, %d) gives %s", name, line, line,
        prof.Count(Call(ui.GetProfessionSpells, line), known), tostring(enum), line,
        enum and prof.Count(Call(ui.GetProfessionSpells, enum, line), known) or "nothing"))
    end
  end
  if ns.atTrainer then
    Say(string.format("at a trainer: a profession's %s, its type %s, %d services", tostring(Plain(Call(IsTradeskillTrainer))),
      tostring(C_Trainer and PlainNumber(Call(C_Trainer.GetTrainerType))), PlainNumber(Call(GetNumTrainerServices)) or 0))
  end
  local sent, ranks = {}, {}
  for name, read in pairs(prof.reads) do sent[#sent + 1] = string.format("%s %d", name, #read.rows) end
  table.sort(sent)
  for _, r in ipairs(prof.last or {}) do
    if r[5] % 2 == prof.RANK then ranks[#ranks + 1] = string.format("%s (skill %d, level %d)", r[6], r[4], r[3]) end
  end
  Say("sent: recipes " .. (#sent > 0 and prof.And(sent) or "none yet") .. ". The last profession trainer: "
    .. (prof.last and string.format("%s, NPC %d, %d services, ranks %s", prof.line, prof.npc, #prof.last,
      #ranks > 0 and prof.And(ranks) or "none") or "none yet"))
end
