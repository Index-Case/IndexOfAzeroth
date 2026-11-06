-- The Index of Azeroth. Copyright 2026 Index Case <indexofazeroth@pm.me>. PolyForm Strict 1.0.0, see LICENSE.md.
local ADDON, ns = ...

local DEFAULTS = { strip = true, size = 4 }
local SIZE_LO, SIZE_HI = 2, 8
local INTERVAL = 0.1

local function SavedSize()
  local n = type(IndexOfAzerothDB) == "table" and tonumber(IndexOfAzerothDB.stripSize)
  return (n and n == math.floor(n) and n >= SIZE_LO and n <= SIZE_HI) and n or DEFAULTS.size
end

local db

local TAB_NAME, LOG_KEEP = "The Index of Azeroth", 500
local TAB_WAS = {}
local log = {}
local tab
local set = false

local function IsTab(i)
  if not (GetChatWindowInfo and i) then return false end
  local name, _, _, _, _, _, shown, _, docked = GetChatWindowInfo(i)
  return (name == TAB_NAME or TAB_WAS[name]) and (shown or docked) and true or false
end
local function FindTab()
  for i = 1, NUM_CHAT_WINDOWS or 10 do
    if IsTab(i) and _G["ChatFrame" .. i] then return _G["ChatFrame" .. i] end
  end
end

local function Out()
  if tab and not IsTab(tab:GetID()) then tab = nil end
  if not tab and not set and ns.Options().general.chatTab then tab = FindTab() end
  return tab or DEFAULT_CHAT_FRAME
end

local function Print(msg)
  local line = "|cff51ccecThe Index of Azeroth|r: " .. tostring(msg)
  log[#log + 1] = line
  if #log > LOG_KEEP then table.remove(log, 1) end
  Out():AddMessage(line)
end
ns.Print = Print

local UI = ns.UI
local copy = CreateFrame("Frame", "IndexOfAzerothCopyBox", UIParent, "BackdropTemplate")
copy:SetSize(620, 380)
copy:SetPoint("CENTER")
copy:SetFrameStrata("DIALOG")
copy:SetClampedToScreen(true)
copy:EnableMouse(true)
copy:SetMovable(true)
copy:RegisterForDrag("LeftButton")
copy:SetScript("OnDragStart", copy.StartMoving)
copy:SetScript("OnDragStop", copy.StopMovingOrSizing)
UI.Panel(copy)
copy:Hide()
tinsert(UISpecialFrames, "IndexOfAzerothCopyBox")

local copyHint = UI.Text(copy, "GameFontHighlightSmall", UI.C.ivory, "LEFT")
copyHint:SetPoint("TOPLEFT", 12, -10)
copyHint:SetText("These are the addon's lines. Ctrl+C copies what's selected and Escape closes this box.")
local copyClose = UI.FlatButton(copy, "Close", 60, function() copy:Hide() end)
copyClose:SetHeight(20)
copyClose:SetPoint("TOPRIGHT", -8, -6)

local copyScroll = CreateFrame("ScrollFrame", nil, copy)
copyScroll:SetPoint("TOPLEFT", 10, -32)
copyScroll:SetPoint("BOTTOMRIGHT", -10, 10)
local copyEdit = CreateFrame("EditBox", nil, copyScroll)
copyEdit:SetMultiLine(true)
copyEdit:SetAutoFocus(false)
copyEdit:SetFontObject(ChatFontNormal)
copyEdit:SetWidth(600)
copyEdit:SetTextInsets(2, 2, 2, 2)
copyScroll:SetScrollChild(copyEdit)
copyScroll:EnableMouseWheel(true)
copyScroll:SetScript("OnMouseWheel", function(self, delta)
  local most = math.max(0, copyEdit:GetHeight() - self:GetHeight())
  self:SetVerticalScroll(math.min(most, math.max(0, self:GetVerticalScroll() - delta * 60)))
end)
local copyText = ""
copyEdit:SetScript("OnEscapePressed", function() copy:Hide() end)
copyEdit:SetScript("OnTextChanged", function(self, userInput)
  if userInput then self:SetText(copyText); self:HighlightText() end
end)

local function PlainLine(s)
  return (s:gsub("|c%x%x%x%x%x%x%x%x", ""):gsub("|r", ""):gsub("|H.-|h(.-)|h", "%1"):gsub("|T.-|t", ""):gsub("|A.-|a", ""))
end

function ns.OpenCopy()
  if copy:IsShown() then return copy:Hide() end
  local lines = {}
  for i, line in ipairs(log) do lines[i] = PlainLine(line) end
  copyText = #lines > 0 and table.concat(lines, "\n") or "The addon hasn't printed anything yet this session."
  copy:Show()
  copyEdit:SetText(copyText)
  copyEdit:SetFocus()
  copyEdit:HighlightText()
  C_Timer.After(0, function()
    copyScroll:SetVerticalScroll(math.max(0, copyEdit:GetHeight() - copyScroll:GetHeight()))
  end)
end

local copyKey
local function CopyKey(frame)
  if not frame then return end
  copyKey = copyKey or UI.FlatButton(frame, "Copy", 46, function() ns.OpenCopy() end)
  copyKey:SetParent(frame)
  copyKey:SetHeight(18)
  copyKey:ClearAllPoints()
  copyKey:SetPoint("TOPRIGHT", frame, "TOPRIGHT", -2, -2)
  copyKey:SetFrameLevel(frame:GetFrameLevel() + 10)
  copyKey:Show()
end

local afterFight = false
local function SetUpTab()
  if InCombatLockdown() then afterFight = true end
  local on, found = ns.Options().general.chatTab, FindTab()
  if not afterFight then
    if on and not found and FCF_OpenNewWindow then
      found = FCF_OpenNewWindow(TAB_NAME, true) or FindTab()
      if found and found.RemoveAllMessageGroups then
        found:RemoveAllMessageGroups()
        if found.RemoveAllChannels then found:RemoveAllChannels() end
      end
    elseif not on and found and FCF_Close then
      FCF_Close(found)
      found = nil
    end
    if found and FCF_SetWindowName and TAB_WAS[GetChatWindowInfo(found:GetID()) or ""] then
      FCF_SetWindowName(found, TAB_NAME)
    end
  end
  tab = on and found or nil
  if tab then CopyKey(tab) elseif copyKey then copyKey:Hide() end
end
function ns.ShowTab()
  if tab and IsTab(tab:GetID()) and tab.isDocked and FCF_SelectDockFrame and not InCombatLockdown() then FCF_SelectDockFrame(tab) end
end
local function TabNow()
  if not pcall(SetUpTab) then tab = nil end
  set = true
end
ns.TabNow, ns.ChatTab, ns.copyBox = TabNow, function() return tab end, { frame = copy, edit = copyEdit }
ns.On("PLAYER_REGEN_ENABLED", function()
  if afterFight then afterFight = false; TabNow() end
end)
ns.On("PLAYER_ENTERING_WORLD", function(_, login, reload)
  if login or reload then C_Timer.After(1, TabNow) end
end)
ns.On("PLAYER_LOGIN", function() ns.OnOptions(TabNow) end)

local function Apply()
  ns.LayoutStrip(db.size)
  ns.ShowStrip(db.strip)
end

local SLOW_EVERY = 3
local SLOTS = { "status", "group", "bars", "status", "entrances", "group", "run", "status", "guide",
                "group", "quests", "addons", "kills", "gathers", "character", "taxi", "equipped", "bags", "bank", "warband", "rolls",
                "epic", "loopstops", "heights", "legacy", "director", "directortext", "camps" }

local Report = ns.Report

local ENCODERS = {
  bars = function() return ns.NextBarsFrame() end,
  entrances = function() return ns.EncodeEntrances() end,
  group = function() return ns.EncodeGroup() end,
  run = function() return ns.EncodeRun() end,
  guide = function() return ns.EncodeGuide() end,
  quests = function(said) return ns.EncodeQuests(said) end,
  addons = function() return ns.EncodeAddons() end,
  kills = function() return ns.EncodeKills() end,
  gathers = function() return ns.EncodeGathers() end,
  heights = function() return ns.EncodeHeights() end,
  xp = function() return ns.EncodeKillXP() end,
  watched = function() return ns.EncodeWatched() end,
  legacy = function() return ns.EncodeLegacy() end,
  hits = function() return ns.EncodeHits() end,
  regen = function() return ns.EncodeRegen() end,
  tracking = function() return ns.EncodeTracking() end,
  queue = function() return ns.Lfg.EncodeQueue() end,
  character = function() return ns.EncodeCharacter() end,
  characterNow = function() return ns.EncodeCharacter() end,
  taxi = function() return ns.EncodeTaxi() end,
  equipped = function() return ns.EncodeEquipped() end,
  rolls = function() return ns.EncodeRolls() end,
  rollsNow = function() return ns.EncodeRolls(true) end,
  epic = function() return ns.EncodeEpic() end,
  loopstops = function() return ns.EncodeLoopStops() end,
  director = function() return ns.EncodeDirector() end,
  directortext = function() return ns.EncodeDirectorText() end,
  camps = function() return ns.EncodeCamps() end,
  completed = function() return ns.NextCompletedFrame() end,
  questlog = function() return ns.NextQuestLogFrame() end,
  spells = function() return ns.NextSpellsFrame() end,
  petspells = function() return ns.NextPetSpellsFrame() end,
  trainer = function() return ns.NextTrainerFrame() end,
  proftrainer = function() return ns.NextProfTrainerFrame() end,
  recipes = function() return ns.NextRecipesFrame() end,
  explored = function() return ns.NextExploredFrame() end,
  bags = function() return ns.NextContainerFrame("bags") end,
  bank = function() return ns.NextContainerFrame("bank") end,
  warband = function() return ns.NextContainerFrame("warband") end,
}
ns.stripEncoders = ENCODERS
ns.stripSlots = SLOTS

local slot = 0
local ticker = CreateFrame("Frame")
ns.stripTicker = ticker
local elapsed, frameCount = 0, 0
local PAGES_RUNNING = 3
local pagesRun = 0

local CHANGED_ORDER = { "status", "director", "directortext", "queue", "quests", "loopstops","xp", "watched", "kills", "run",
                        "gathers", "equipped", "taxi", "character", "heights", "legacy", "camps", "bags" }
local CHANGE_EVENTS = {
  QUEST_LOG_UPDATE = { "quests" }, QUEST_ACCEPTED = { "quests" },
  QUEST_REMOVED = { "quests" }, QUEST_TURNED_IN = { "quests", "status" },
  QUEST_WATCH_UPDATE = { "quests" }, UNIT_QUEST_LOG_CHANGED = { "quests" },
  PLAYER_MONEY = { "status" }, PLAYER_XP_UPDATE = { "status" }, PLAYER_LEVEL_UP = { "status", "character" },
  BAG_UPDATE_DELAYED = { "status" }, UPDATE_INVENTORY_DURABILITY = { "status" },
  PLAYER_EQUIPMENT_CHANGED = { "equipped" }, TAXIMAP_OPENED = { "taxi" }, SKILL_LINES_CHANGED = { "character" },
}
local RESEND = { character = 5, addons = 15, taxi = 30, equipped = 30, legacy = 60 }
local SAME_KIND = { characterNow = "character", rollsNow = "rolls" }
local changed, lastSent, sentAt = {}, {}, {}
function ns.MarkChanged(kind) changed[kind] = true end
local function Heard(event)
  for _, kind in ipairs(CHANGE_EVENTS[event]) do changed[kind] = true end
end
for event in pairs(CHANGE_EVENTS) do ns.On(event, Heard, event:find("^UNIT_") and "player" or nil) end
local Said = ns.Said
local function Sendable(what, bytes, part)
  local kind = SAME_KIND[what] or what
  local said, every = Said(bytes, part), not SAME_KIND[what] and RESEND[kind]
  if every and said == lastSent[kind] and GetTime() - (sentAt[kind] or -math.huge) < every then return nil end
  lastSent[kind], sentAt[kind] = said, GetTime()
  return bytes
end
ns.StripSendable = Sendable
local function NextChanged()
  for _, kind in ipairs(CHANGED_ORDER) do
    if changed[kind] then
      changed[kind] = nil
      if kind == "status" then return "status" end
      local ok, bytes, part = pcall(ENCODERS[kind], lastSent[kind])
      if not ok then Report(kind, bytes)
      elseif bytes and Said(bytes, part) ~= lastSent[kind] then return kind, bytes, part end
    end
  end
end
ns.StripChanged = function() return changed end

local waiting = {}
function ns.SendFrame(bytes, copies, gap)
  local at = GetTime()
  if waiting[#waiting] then at = math.max(at, waiting[#waiting].at + gap) end
  for i = 0, copies - 1 do waiting[#waiting + 1] = { bytes = bytes, at = at + i * gap } end
end
ns.stripWaiting = waiting
function ns.StripLive() return db and db.strip and not ns.paused or false end

local RELOAD_FRAME, HELD, HOOKED = 43, 1, 2
local RELOAD_HOLD = 2
local reloadingAt
local function ReloadUp()
  return reloadingAt ~= nil and GetTime() < reloadingAt + RELOAD_HOLD
end
local function SayReloading(how)
  if ReloadUp() or not ns.StripLive() then return false end
  if not ns.DrawStrip({ RELOAD_FRAME, how }) then return false end
  reloadingAt = GetTime()
  return true
end
ns.RELOAD_HOLD = RELOAD_HOLD
function ns.Reloading() return ReloadUp() and reloadingAt or nil end
function ns.ReloadPressed()
  local ok, said = pcall(SayReloading, HELD)
  if not ok then Report("reload frame", said) end
end
function ns.Reload()
  if not ReloadUp() then ns.ReloadPressed() end
  ReloadUI()
end
local function Hooked() pcall(SayReloading, HOOKED) end
if C_UI and C_UI.Reload then hooksecurefunc(C_UI, "Reload", Hooked) end
hooksecurefunc("ReloadUI", Hooked)
local function HoldSlashReload()
  for key, fn in pairs(SlashCmdList) do
    for i = 1, 9 do
      local said = _G["SLASH_" .. key .. i]
      if not said then break end
      if type(fn) == "function" and said:lower() == "/reload" and key ~= "INDEXOFAZEROTH" then
        SlashCmdList[key] = function() ns.Reload() end
        if hash_SlashCmdList then
          for word, f in pairs(hash_SlashCmdList) do if f == fn then hash_SlashCmdList[word] = SlashCmdList[key] end end
        end
        return key
      end
    end
  end
end
ns.HoldSlashReload = HoldSlashReload

ns.OnTick(ticker, "the strip", nil, function(_, dt)
  elapsed = elapsed + dt
  if elapsed < INTERVAL or not db or ReloadUp() then return end
  elapsed = elapsed - INTERVAL
  if elapsed >= INTERVAL then elapsed = 0 end
  frameCount = frameCount + 1
  local live = db.strip and not ns.paused
  if frameCount % SLOW_EVERY == 0 then
    local what, paged, made, part = nil, false, nil, nil
    if live and ns.guideDirty then
      what = "guide"
    elseif live and ns.characterDirty then
      what, ns.characterDirty = "characterNow", false
    elseif live and ns.statusDirty then
      what, ns.statusDirty = "status", false
    elseif live and ns.rollsDirty then
      what, ns.rollsDirty = "rollsNow", false
    elseif live and ns.queueDirty then
      what, ns.queueDirty = "queue", false
    elseif live and ns.epicDirty then
      what = "epic"
    elseif live and pagesRun < PAGES_RUNNING and ns.CompletedPending and ns.CompletedPending() then
      what, paged = "completed", true
    elseif live and pagesRun < PAGES_RUNNING and ns.QuestLogPending and ns.QuestLogPending() then
      what, paged = "questlog", true
    elseif live and pagesRun < PAGES_RUNNING and ns.SpellsPending and ns.SpellsPending() then
      what, paged = "spells", true
    elseif live and pagesRun < PAGES_RUNNING and ns.PetSpellsPending and ns.PetSpellsPending() then
      what, paged = "petspells", true
    elseif live and pagesRun < PAGES_RUNNING and ns.TrainerPending and ns.TrainerPending() then
      what, paged = "trainer", true
    elseif live and pagesRun < PAGES_RUNNING and ns.ProfTrainerPending and ns.ProfTrainerPending() then
      what, paged = "proftrainer", true
    elseif live and pagesRun < PAGES_RUNNING and ns.RecipesPending and ns.RecipesPending() then
      what, paged = "recipes", true
    elseif live and pagesRun < PAGES_RUNNING and ns.ContainerPending and ns.ContainerPending() then
      what, paged = ns.ContainerPending(), true
    elseif live and pagesRun < PAGES_RUNNING and ns.ExploredPending and ns.ExploredPending() then
      what, paged = "explored", true
    end
    if not what and live then
      what, made, part = NextChanged()
    elseif not what and changed.status then
      what, changed.status = "status", nil
    end
    if not what then
      slot = slot % #SLOTS + 1
      what = SLOTS[slot]
    end
    pagesRun = paged and pagesRun + 1 or 0
    ns.lastSlow = what
    if what == "status" then
      local ok, st = pcall(ns.CollectStatus)
      if not ok then return Report("status", st) end
      local warned, err = pcall(ns.AnnounceWarnings, st)
      if not warned then Report("warnings", err) end
      if not live then return end
      local made, bytes = pcall(ns.EncodeStatus, st)
      if not made then Report("status frame", bytes) elseif ns.DrawStrip(bytes) then return end
    elseif live then
      local ok, bytes = true, made
      if not bytes then ok, bytes, part = pcall(ENCODERS[what]) end
      if not ok then Report(what, bytes)
      elseif bytes and Sendable(what, bytes, part) and ns.DrawStrip(bytes) then return end
    end
    if live and ns.KillXPDue and ns.KillXPDue() then
      local ok, bytes = pcall(ENCODERS.xp)
      if not ok then Report("xp", bytes) elseif bytes and Sendable("xp", bytes) and ns.DrawStrip(bytes) then return end
    end
    if live and ns.WatchedDue and ns.WatchedDue() then
      local ok, bytes = pcall(ENCODERS.watched)
      if not ok then Report("watched", bytes) elseif bytes and Sendable("watched", bytes) and ns.DrawStrip(bytes) then return end
    end
    if live and ns.Lfg.QueueDue() then
      local ok, bytes, queuePart = pcall(ENCODERS.queue)
      if not ok then Report("queue", bytes) elseif Sendable("queue", bytes, queuePart) and ns.DrawStrip(bytes) then return end
    end
  end
  if not live then return end
  if waiting[1] and GetTime() >= waiting[1].at then
    local f = table.remove(waiting, 1)
    if ns.DrawStrip(f.bytes) then return end
  end
  if ns.Auction and ns.Auction.Active() then
    local ok, bytes = pcall(ns.Auction.NextFrame)
    if not ok then Report("auction scan frame", bytes) elseif bytes and ns.DrawStrip(bytes, true) then return end
  end
  if ns.HitsDue() then
    local ok, bytes = pcall(ENCODERS.hits)
    if not ok then Report("hits", bytes) elseif ns.DrawStrip(bytes) then return end
  end
  if ns.RegenDue() then
    local ok, bytes = pcall(ENCODERS.regen)
    if not ok then Report("regen", bytes) elseif ns.DrawStrip(bytes) then return end
  end
  local due, isDue = pcall(ns.TrackingDue)
  if not due then Report("tracking", isDue)
  elseif isDue then
    local ok, bytes = pcall(ENCODERS.tracking)
    if not ok then Report("tracking", bytes) elseif ns.DrawStrip(bytes) then return end
  end
  local ok, bytes = pcall(ns.Collect)
  if ok then ns.DrawStrip(bytes) else Report("collect", bytes) end
end)

ns.On({ "ADDON_LOADED", "PLAYER_LOGIN", "PLAYER_ENTERING_WORLD", "DISPLAY_SIZE_CHANGED", "UI_SCALE_CHANGED" }, function(event, name)
  if event == "ADDON_LOADED" then
    if name ~= ADDON then return end
    db = {}
    for k, v in pairs(DEFAULTS) do db[k] = v end
    db.size = SavedSize()
    ns.db = db
    ns.ClaimCharDB()
    ns.Trace.Load()
    ns.InitCharDB()
    ns.GuideSaved()
    ns.Options()
  elseif event == "PLAYER_ENTERING_WORLD" then
    ns.characterDirty = true
    ns.statusDirty = true
  elseif db then
    Apply()
    if event == "PLAYER_LOGIN" then
      ns.PlaceButton()
      ns.PlaceMinimapButton()
      ns.InitRunTracking()
      ns.RefreshButton()
    end
  end
end)

ns.OnOptions(function() ns.statusDirty = true end)

function ns.SetStrip(on)
  db.strip = on
  ns.paused = false
  Apply()
  Print(ns.SwitchWords(ns.Word("game.chat.switch.name.strip"), on, "strip"))
  if ns.RefreshButton then ns.RefreshButton() end
end

function ns.Test()
  local bytes = {}
  for i = 0, 255 do bytes[#bytes + 1] = i end
  ns.paused = true
  ns.ShowStrip(true)
  ns.DrawStrip(bytes)
  Print("The addon drew the test pattern and paused live updates. The reader should report 'test pattern OK'. Ctrl+right-click the add-on button again to resume live updates.")
  if ns.RefreshButton then ns.RefreshButton() end
end

function ns.Debug()
  local ok, bytes, s = pcall(ns.Collect)
  if not ok then return Print("collect failed: " .. tostring(bytes)) end
  Print(string.format("map %s  pos %s, %s  facing %s  level %d  xp %d/%d  rested %d  speed %.1f",
    tostring(s.map), s.x and string.format("%.4f", s.x) or "nil", s.y and string.format("%.4f", s.y) or "nil",
    s.facing and string.format("%.2f", s.facing) or "nil", s.level, s.xp, s.xpMax, s.rested, s.speed))
  Print(string.format("zone %s / %s", s.zone, s.subzone))
  Print(string.format("actions %d%s, spirit %s, health events %d", s.acts, s.busy and " (busy)" or "",
    tostring(ns.regen.spirit or "hidden"), ns.regen.events))
  Print(string.format("payload %d of %d bytes, strip %s, block %d px", #bytes, ns.MAX_PAYLOAD,
    db.strip and "on" or "off", db.size))
end

ns.commands = ns.commands or {}

SLASH_INDEXOFAZEROTH1 = "/ioa"
SlashCmdList.INDEXOFAZEROTH = function(msg)
  pcall(ns.ShowTab)
  local goRest = (msg or ""):match("^%s*[Gg][Oo]%s*(.*)$")
  if goRest then return ns.GoCommand(goRest) end
  local routeRest = (msg or ""):match("^%s*[Rr]%s+(.+)$")
  if routeRest then return ns.RouteCommand(routeRest) end
  local targetRest = (msg or ""):match("^%s*[Tt][Aa][Rr][Gg][Ee][Tt]%s+(.+)$") or ((msg or ""):match("^%s*[Tt][Aa][Rr][Gg][Ee][Tt]%s*$") and "")
  if targetRest then return ns.TargetCommand(targetRest) end
  local track, trackRest = (msg or ""):match("^%s*([EeGgHhKk])%s+(.+)$")
  if track then return ns.TrackCommand(track:lower(), trackRest) end
  local cmd, arg, more = strsplit(" ", strtrim(msg or ""):lower())
  if ns.commands[cmd] then return ns.commands[cmd](strtrim((strtrim(msg or ""):lower():sub(#cmd + 1)))) end
  if cmd == "strip" and (arg == "on" or arg == "off" or not arg) then
    ns.SetStrip(arg == "on" or (arg ~= "off" and not db.strip))
  elseif cmd == "size" and tonumber(arg) then
    db.size = math.max(SIZE_LO, math.min(SIZE_HI, math.floor(tonumber(arg))))
    if type(IndexOfAzerothDB) ~= "table" then IndexOfAzerothDB = {} end
    IndexOfAzerothDB.stripSize = db.size
    Apply()
    Print("The strip's blocks are now " .. db.size .. " px.")
  elseif cmd == "debug" then
    ns.Debug()
  elseif cmd == "test" then
    ns.Test()
  elseif cmd == "bars" then
    ns.PrintBars()
  elseif cmd == "talents" then
    ns.PrintTalents()
  elseif cmd == "entrances" then
    ns.PrintEntrances()
  elseif cmd == "paste" then
    ns.OpenPaste()
  elseif cmd == "copy" then
    ns.OpenCopy()
  elseif cmd == "guide" and arg == "park" then
    ns.GuideParkQuest(tonumber(more))
  elseif cmd == "guide" and arg == "unpark" then
    ns.GuideUnparkQuest(tonumber(more))
  elseif cmd == "guide" and arg == "background" then
    ns.DrawerBackgroundQuest(tonumber(more))
  elseif cmd == "guide" and arg == "putback" then
    ns.GuidePutBackCommand(more, select(4, strsplit(" ", strtrim(msg or ""):lower())))
  elseif cmd == "guide" and arg == "stop" then
    ns.GuideStop()
  elseif cmd == "guide" and arg == "start" then
    ns.GuideStart()
  elseif cmd == "guide" and arg == "reset" then
    ns.ResetGuideCard()
  elseif cmd == "guide" then
    ns.ToggleGuideCard(arg == "on" or (arg ~= "off" and nil), true)
  elseif (cmd == "beacon" or cmd == "beacons") and arg == "debug" then
    ns.GuideBeaconTake(true)
  elseif cmd == "beacon" or cmd == "beacons" then
    if ns.Switch("beacons", arg) then ns.GuideBeaconTake() end
  elseif cmd == "compass" and arg == "reset" then
    ns.ResetCompass()
  elseif cmd == "compass" or cmd == "arrows" then
    ns.Switch(cmd, arg)
  elseif cmd == "dungeon" then
    ns.PrintDungeon()
  elseif cmd == "lfg" then
    ns.Lfg.Print()
  elseif cmd == "queue" then
    ns.Lfg.PrintQueue()
  elseif cmd == "button" then
    ns.ToggleButton(arg)
  elseif cmd == "minimap" then
    ns.ToggleMinimapButton(arg)
  elseif cmd == "options" then
    ns.ToggleOptions()
  elseif cmd == "pois" then
    local n, lines = 0, {}
    for id, p in pairs(ns.QuestPOIs()) do
      n = n + 1
      if #lines < 8 then lines[#lines + 1] = string.format("%d on map %d at %.1f, %.1f", id, p.map, p.x * 100, p.y * 100) end
    end
    Print(n .. " quest markers" .. (n > 0 and (": " .. table.concat(lines, " / ")) or ". The game's map has none."))
  elseif cmd == "prof" then
    ns.PrintProfessions()
  elseif cmd == "xp" then
    ns.PrintKillXP()
  elseif cmd == "legacy" then
    ns.PrintLegacy()
  elseif cmd == "camp" then
    ns.PrintCamp()
  elseif cmd == "ah" and ns.Auction then
    ns.Auction.Command(arg)
  elseif cmd == "ah" then
    Print("The auction house scan needs the game restarted once to load.")
  elseif cmd == "lines" and arg == "debug" then
    ns.PrintLines()
  elseif cmd == "lines" or cmd == "line" then
    ns.Switch("lines", arg)
  else
    Print("These commands switch something on or off. Add on or off, or nothing to flip the switch: /ioa guide (the quest epic's card, also stop, start, reset, park <quest ID> and unpark <quest ID>), /ioa compass (also reset), /ioa beacons (each guide's target marked in the world, also debug), /ioa arrows (the navigation arrows), /ioa lines (the guide lines on the maps, also debug), /ioa polaroid (the level-up picture, bare to take one now), /ioa strip, /ioa button (also reset) and /ioa minimap (the minimap button). "
      .. "These commands start a guide or open a window: /ioa go <map> <x> <y> <name> (or off), /ioa r (a route from the page), /ioa e (a quest epic's step), /ioa g (a grind or farm loop), /ioa h (a gathering loop), /ioa k (a skinning loop), /ioa target @Name, !Name or off (the Target key beside the add-on button), /ioa paste, /ioa copy (the addon's lines to copy) and /ioa options. /ioa size 2-8 sets the strip's block size. "
      .. "These commands print what the addon gets from the game: /ioa debug, /ioa test (the strip's test pattern), /ioa bars, /ioa talents, /ioa entrances, /ioa dungeon, /ioa lfg (what the card's LFG key posts and where), /ioa queue (the group finder), /ioa pois (the game's quest markers), /ioa xp (each kill's XP and the character's XP buffs), /ioa camp (the character's camping buffs, cooldowns, recipes and kits), /ioa legacy (the account's Legacy points), /ioa prof (what the game's profession calls give now) and /ioa ah (the auction house scan's numbers, also scan or stop).")
  end
end
