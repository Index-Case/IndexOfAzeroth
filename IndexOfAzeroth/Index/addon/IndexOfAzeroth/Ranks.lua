-- The Index of Azeroth. Copyright 2026 Index Case <indexofazeroth@pm.me>. PolyForm Strict 1.0.0, see LICENSE.md.
local ADDON, ns = ...

local MAX_ACTION_SLOTS = 120
local PAGE_BYTES = 300
local BANK = Enum and Enum.SpellBookSpellBank and Enum.SpellBookSpellBank.Player or 0
local SPELL_ITEM = Enum and Enum.SpellBookItemType and Enum.SpellBookItemType.Spell or 1
local KIND_RANK, KIND_MISSING = 1, 2
local FEED_PET = 6991
local RESCAN = 30
local WALK_EACH = 200

local Call = ns.Call

local function RankOf(subtext)
  return type(subtext) == "string" and tonumber(subtext:match("(%d+)")) or nil
end

local function SpellIDs(id)
  local ids = { id }
  local base, override = Call(FindBaseSpellByID, id), Call(FindSpellOverrideByID, id)
  if base and base ~= id then ids[#ids + 1] = base end
  if override and override ~= id then ids[#ids + 1] = override end
  return ids
end

local function KnownSpells()
  local best, active = {}, {}
  for line = 1, Call(C_SpellBook.GetNumSpellBookSkillLines) or 0 do
    local info = Call(C_SpellBook.GetSpellBookSkillLineInfo, line)
    if info and not info.shouldHide then
      for i = info.itemIndexOffset + 1, info.itemIndexOffset + info.numSpellBookItems do
        local item = Call(C_SpellBook.GetSpellBookItemInfo, i, BANK)
        if item and item.name and item.itemType == SPELL_ITEM and not item.isPassive then
          local rank = RankOf(item.subName)
          if rank and rank > (best[item.name] or 0) then best[item.name] = rank end
          if line > 1 then active[item.name] = item.spellID and SpellIDs(item.spellID) or {} end
        end
      end
    end
  end
  return best, active
end

local CAST_COMMANDS = { ["/cast"] = true, ["/spell"] = true, ["/castsequence"] = true, ["/castrandom"] = true,
  ["/use"] = true, ["/userandom"] = true, ["#showtooltip"] = true, ["#show"] = true }

local function NoteSpellText(spell, note)
  local name, rank = spell:match("^(.-)%s*%(%s*[Rr]ank%s+(%d+)%s*%)$")
  name = name or spell
  if name ~= "" then note(name, tonumber(rank)) end
end

local function MacroSpells(body, note)
  for line in (body or ""):gmatch("[^\r\n]+") do
    local command, rest = line:match("^%s*([/#]%a+)%s+(.*)$")
    if command and CAST_COMMANDS[command:lower()] then
      rest = rest:gsub("%b[]", ""):gsub("reset=%S+", "")
      for part in rest:gmatch("[^;,]+") do
        NoteSpellText((strtrim(part):gsub("^!", "")), note)
      end
    end
  end
end

local function MacroAt(slot, id)
  local label = Call(GetActionText, slot)
  local index = label and label ~= "" and Call(GetMacroIndexByName, label)
  if not (index and index > 0) then index = id end
  local macroName, _, body = Call(GetMacroInfo, index)
  return macroName or label, body, index
end


local MODIFIERS = { "", "shift-", "ctrl-", "alt-", "ctrl-shift-", "alt-ctrl-", "alt-shift-", "alt-ctrl-shift-" }
local GAME_TYPES, GAME_TYPE = {}, {}
for _, mod in ipairs(MODIFIERS) do
  for _, button in ipairs({ "", "1" }) do
    GAME_TYPES[#GAME_TYPES + 1] = mod .. "type" .. button
    GAME_TYPE[mod .. "type" .. button] = true
  end
end
local learnt = setmetatable({}, { __mode = "k" })
local function Learn(frame, name)
  if type(name) ~= "string" or GAME_TYPE[name] or not name:find("type", 1, true) then return end
  local names = learnt[frame]
  if not names then names = {}; learnt[frame] = names end
  names[name] = true
end
do
  local hooked = {}
  for _, kind in ipairs({ "Button", "CheckButton" }) do
    local probe = CreateFrame(kind)
    probe:Hide()
    local meta = getmetatable(probe)
    local methods = meta and meta.__index
    if type(methods) == "table" and not hooked[methods] then
      hooked[methods] = true
      for _, method in ipairs({ "SetAttribute", "SetAttributeNoHandler" }) do
        if type(methods[method]) == "function" then hooksecurefunc(methods, method, Learn) end
      end
    end
  end
end
local function EachAction(frame, fn)
  local function Read(typeName)
    local before, after = typeName:match("^(.*)type(.-)$")
    local function Part(part) return Call(frame.GetAttribute, frame, before .. part .. after) end
    fn(ns.Plain(Call(frame.GetAttribute, frame, typeName)), Part, typeName)
  end
  for _, name in ipairs(GAME_TYPES) do Read(name) end
  for name in pairs(learnt[frame] or {}) do Read(name) end
end
local addonButtons = { list = {}, at = nil, said = nil, frames = 0 }
local walk = nil
local cache = { dirty = true, report = { ranks = {}, missing = {} }, version = 0, page = 0 }

local shownSlots = {}
ns.barsShownSlots = shownSlots

local STANCE_PAGES = 4
local function Shows(slot, forms)
  if shownSlots[slot] then return true end
  if not forms then return false end
  local i
  if slot <= 12 then i = slot elseif slot > 72 then i = (slot - 73) % 12 + 1 else return false end
  if shownSlots[i] then return true end
  for page = 1, STANCE_PAGES do
    if shownSlots[72 + (page - 1) * 12 + i] then return true end
  end
  return false
end

local function ShownSlots(frame, shown)
  if not ns.Plain(Call(frame.IsVisible, frame)) then return end
  local function Add(slot)
    if slot and slot >= 1 and slot <= MAX_ACTION_SLOTS then shown[slot] = true end
  end
  Add(ns.PlainNumber(frame.action))
  if not frame.GetAttribute then return end
  EachAction(frame, function(kind, Part, typeName)
    if kind == "action" or (typeName == "type" and kind == nil) then Add(ns.PlainNumber(Part("action"))) end
  end)
end

local function LookAt(frame, list, shown)
  local ok, isButton = pcall(frame.IsObjectType, frame, "Button")
  if not (ok and isButton) or (frame.IsForbidden and frame:IsForbidden()) then return end
  if shown then
    local into = {}
    if pcall(ShownSlots, frame, into) then
      for slot in pairs(into) do shown[slot] = true end
    end
  end
  if not frame.GetAttribute then return end
  EachAction(frame, function(kind, Part)
    if kind == "spell" then
      local spell = Part("spell")
      local id = tonumber(spell)
      local name = id and ns.PlainText(Call(C_Spell.GetSpellName, id)) or (type(spell) == "string" and spell or nil)
      if name then list[#list + 1] = { name = name, id = id, label = frame:GetName() or "addon button" } end
    elseif kind == "macro" then
      local text = Part("macrotext")
      if type(text) ~= "string" then
        local macro = Part("macro")
        text = macro and select(3, Call(GetMacroInfo, macro)) or nil
      end
      if type(text) == "string" then list[#list + 1] = { macro = text } end
    end
  end)
end

local function WalkOn(most)
  local w = walk
  for _ = 1, most or math.huge do
    local frame
    if w.frame then frame = Call(EnumerateFrames, w.frame) else frame = Call(EnumerateFrames) end
    if not frame then
      local said = {}
      for k, b in ipairs(w.list) do said[k] = b.macro or ((b.name or "") .. ":" .. tostring(b.id)) end
      for slot in pairs(w.shown) do
        if not shownSlots[slot] then shownSlots[slot] = true; cache.dirty = true end
      end
      said = table.concat(said, "\n")
      if said ~= addonButtons.said then cache.dirty = true end
      addonButtons.list, addonButtons.at, addonButtons.said, addonButtons.frames = w.list, GetTime(), said, w.frames
      walk = nil
      return true
    end
    w.frame, w.frames = frame, w.frames + 1
    LookAt(frame, w.list, w.shown)
  end
  return false
end

local walker = CreateFrame("Frame")
ns.barsWalker = walker
walker:Hide()
ns.OnTick(walker, "the action bars' walk", nil, function(self)
  if not walk or InCombatLockdown() then return self:Hide() end
  if WalkOn(WALK_EACH) then self:Hide() end
end)
local function StartWalk()
  if walk or InCombatLockdown() then return end
  walk = { list = {}, shown = {}, frame = nil, frames = 0 }
  if not WalkOn(WALK_EACH) then walker:Show() end
end

local function ScanBars(best, listing)
  local onBars, ranks, canon = {}, {}, {}
  for name in pairs(best) do canon[name:lower()] = name end
  local function Note(name, rank)
    if not name then return end
    name = canon[name:lower()] or name
    onBars[name:lower()] = true
    if best[name] then
      rank = rank or best[name]
      if rank > (ranks[name] or 0) then ranks[name] = rank end
    end
  end
  if _G.PetFeedButton then
    Note(Call(C_Spell.GetSpellName, FEED_PET) or "Feed Pet")
    for _, spellID in ipairs(SpellIDs(FEED_PET)) do onBars[spellID] = true end
    if listing then listing[#listing + 1] = "PetFeed button: Feed Pet" end
  end
  for _, b in ipairs(addonButtons.list) do
    if b.macro then
      MacroSpells(b.macro, Note)
    else
      NoteSpellText(b.name, Note)
      if b.id then for _, spellID in ipairs(SpellIDs(b.id)) do onBars[spellID] = true end end
      if listing then listing[#listing + 1] = string.format("%s: %s", b.label, b.name) end
    end
  end
  for form = 1, ns.PlainNumber(Call(GetNumShapeshiftForms)) or 0 do
    local spellID = ns.PlainNumber((select(4, Call(GetShapeshiftFormInfo, form))))
    if spellID then
      Note(Call(C_Spell.GetSpellName, spellID))
      for _, id in ipairs(SpellIDs(spellID)) do onBars[id] = true end
    end
  end
  local anyShown = next(shownSlots) ~= nil
  local forms = (ns.PlainNumber(Call(GetNumShapeshiftForms)) or 0) > 0
  for slot = 1, MAX_ACTION_SLOTS do
    local kind, id, subType = Call(GetActionInfo, slot)
    if anyShown and not Shows(slot, forms) then
      if kind and listing then
        local name = kind == "spell" and Call(C_Spell.GetSpellName, id) or (tostring(kind) .. " " .. tostring(id))
        listing[#listing + 1] = string.format("%d: %s (no bar on screen shows this slot)", slot, tostring(name))
      end
      kind = nil
    end
    if kind == "spell" and id then
      local name, rank = Call(C_Spell.GetSpellName, id), RankOf(Call(C_Spell.GetSpellSubtext, id))
      Note(name, rank)
      for _, spellID in ipairs(SpellIDs(id)) do onBars[spellID] = true end
      if listing then listing[#listing + 1] = string.format("%d: %s%s", slot, name or ("spell " .. id), rank and (" (Rank " .. rank .. ")") or "") end
    elseif kind == "macro" and id then
      local macroName, body, index = MacroAt(slot, id)
      MacroSpells(body, Note)
      local shown = (subType == "spell" and id) or Call(GetMacroSpell, index)
      if shown then
        Note(Call(C_Spell.GetSpellName, shown))
        for _, spellID in ipairs(SpellIDs(shown)) do onBars[spellID] = true end
      end
      if listing then listing[#listing + 1] = string.format("%d: macro %s: %s", slot, macroName or id, (body or ""):gsub("\n", " | ")) end
    elseif kind and listing then
      listing[#listing + 1] = string.format("%d: %s %s", slot, kind, tostring(id))
    end
  end
  return onBars, ranks
end

local function Build()
  cache.dirty = false
  local best, active = KnownSpells()
  local onBars, barRanks = ScanBars(best)
  local report = { ranks = {}, missing = {} }
  for name, rank in pairs(barRanks) do
    if rank < best[name] then report.ranks[#report.ranks + 1] = { name = name, have = rank, best = best[name] } end
  end
  for name, ids in pairs(active) do
    local found = onBars[name:lower()]
    for _, id in ipairs(ids) do found = found or onBars[id] end
    if not found then report.missing[#report.missing + 1] = name end
  end
  table.sort(report.ranks, function(a, b) return a.name < b.name end)
  table.sort(report.missing)
  local said = {}
  for _, r in ipairs(report.ranks) do said[#said + 1] = r.name .. ":" .. r.have .. ":" .. r.best end
  said[#said + 1] = "|" .. table.concat(report.missing, ",")
  said = table.concat(said, ",")
  if said ~= cache.said then
    cache.said = said
    cache.version = (cache.version + 1) % 256
    cache.pages = nil
  end
  cache.report = report
end

function ns.BarReport()
  if not addonButtons.at or GetTime() - addonButtons.at >= RESCAN then StartWalk() end
  if cache.dirty and addonButtons.at and not InCombatLockdown() then Build() end
  return cache.report
end
ns.OutdatedRanks = function() return ns.BarReport().ranks end

function ns.NextBarsFrame()
  local report = ns.BarReport()
  if not addonButtons.at then return nil end
  if not cache.pages then
    local entries = {}
    for _, r in ipairs(report.ranks) do entries[#entries + 1] = { kind = KIND_RANK, name = r.name, have = r.have, best = r.best } end
    for _, name in ipairs(report.missing) do entries[#entries + 1] = { kind = KIND_MISSING, name = name } end
    local pages, page, size = {}, {}, 0
    for _, e in ipairs(entries) do
      local cost = 2 + math.min(#e.name, 24) + (e.kind == KIND_RANK and 2 or 0)
      if size + cost > PAGE_BYTES and #page > 0 then pages[#pages + 1], page, size = page, {}, 0 end
      page[#page + 1], size = e, size + cost
    end
    pages[#pages + 1] = page
    cache.pages, cache.page = pages, 0
  end
  cache.page = cache.page % #cache.pages + 1
  local w = ns.NewWriter()
  w:u8(4)
  w:u8(cache.version); w:u8(cache.page); w:u8(#cache.pages)
  local page = cache.pages[cache.page]
  w:u8(#page)
  for _, e in ipairs(page) do
    w:u8(e.kind); w:str(e.name, 24)
    if e.kind == KIND_RANK then w:u8(e.have); w:u8(e.best) end
  end
  return w.bytes
end

local SPELLS_EVERY = 90
local spells = ns.IdPager(23, SPELLS_EVERY)
local function BuildSpells(again)
  local ids, seen = {}, {}
  for line = 1, Call(C_SpellBook.GetNumSpellBookSkillLines) or 0 do
    local info = Call(C_SpellBook.GetSpellBookSkillLineInfo, line)
    if info then
      for i = info.itemIndexOffset + 1, info.itemIndexOffset + info.numSpellBookItems do
        local item = Call(C_SpellBook.GetSpellBookItemInfo, i, BANK)
        local id = item and item.itemType == SPELL_ITEM and ns.Plain(item.spellID)
        if id and not seen[id] then seen[id] = true; ids[#ids + 1] = id end
      end
    end
  end
  if #ids == 0 then return false end
  table.sort(ids)
  spells.Offer(ids, table.concat(ids, ","), again)
  return true
end
spells.refill = BuildSpells
ns.SpellsPending, ns.NextSpellsFrame = spells.Pending, spells.Next
local spellAsked = false
ns.On({ "PLAYER_ENTERING_WORLD", "SPELLS_CHANGED", "LEARNED_SPELL_IN_SKILL_LINE" }, function(event, login, reload)
  if event == "PLAYER_ENTERING_WORLD" and not (login or reload) then return end
  if spellAsked then return end
  spellAsked = true
  C_Timer.After(event == "PLAYER_ENTERING_WORLD" and 3 or 1, function()
    spellAsked = false
    if not BuildSpells(event == "PLAYER_ENTERING_WORLD") then C_Timer.After(5, function() BuildSpells(true) end) end
  end)
end)
ns.BuildSpells = BuildSpells

local PET_BANK = Enum and Enum.SpellBookSpellBank and Enum.SpellBookSpellBank.Pet or 1
local PET_ACTION = Enum and Enum.SpellBookItemType and Enum.SpellBookItemType.PetAction or 3
local petSpells = ns.IdPager(31, SPELLS_EVERY)
local function BuildPetSpells(again)
  local ids, seen = {}, {}
  for i = 1, ns.PlainNumber(Call(C_SpellBook.HasPetSpells)) or 0 do
    local item = Call(C_SpellBook.GetSpellBookItemInfo, i, PET_BANK)
    local id = item and (item.itemType == SPELL_ITEM or item.itemType == PET_ACTION) and ns.PlainNumber(item.spellID)
    if id and id > 0 and not seen[id] then seen[id] = true; ids[#ids + 1] = id end
  end
  if #ids == 0 then return false end
  table.sort(ids)
  petSpells.Offer(ids, table.concat(ids, ","), again)
  return true
end
petSpells.refill = BuildPetSpells
ns.PetSpellsPending, ns.NextPetSpellsFrame = petSpells.Pending, petSpells.Next
local petAsked = false
ns.On({ "PLAYER_ENTERING_WORLD", "SPELLS_CHANGED", "PET_BAR_UPDATE" }, function(event, login, reload)
  if event == "PLAYER_ENTERING_WORLD" and not (login or reload) then return end
  if petAsked then return end
  petAsked = true
  C_Timer.After(event == "PLAYER_ENTERING_WORLD" and 3 or 1, function()
    petAsked = false
    BuildPetSpells(event == "PLAYER_ENTERING_WORLD")
  end)
end)
ns.On("UNIT_PET", function()
  C_Timer.After(1, function() BuildPetSpells() end)
end, "player")
ns.BuildPetSpells = BuildPetSpells

local function Ms() return debugprofilestop and debugprofilestop() or GetTime() * 1000 end
function ns.PrintBars()
  walk = { list = {}, shown = {}, frame = nil, frames = 0 }
  local started = Ms()
  WalkOn()
  local ms = Ms() - started
  local listing = {}
  ScanBars((KnownSpells()), listing)
  ns.Print(string.format("%d action slots in use:", #listing))
  for _, line in ipairs(listing) do ns.Print("  " .. line) end
  Build()
  local report = cache.report
  for _, o in ipairs(report.ranks) do
    ns.Print(string.format("%s: you have Rank %d on your bars and know Rank %d.", o.name, o.have, o.best))
  end
  if #report.missing > 0 then ns.Print("These spells aren't on your bars: " .. table.concat(report.missing, ", ") .. ".") end
  if #report.ranks == 0 and #report.missing == 0 then ns.Print("Every spell you know is on your bars at its highest rank.") end
  ns.Print(string.format("The addon looked through %d frames for other addons' buttons in %.1f ms and found %d. In the "
    .. "background the addon looks through %d frames per game frame and never in a fight.", addonButtons.frames, ms, #addonButtons.list, WALK_EACH))
end

ns.On({ "PLAYER_LOGIN", "ACTIONBAR_SLOT_CHANGED", "SPELLS_CHANGED", "LEARNED_SPELL_IN_SKILL_LINE", "UPDATE_MACROS" },
      function() cache.dirty = true end)
ns.On("PLAYER_REGEN_ENABLED", function() if walk then walker:Show() end end)
