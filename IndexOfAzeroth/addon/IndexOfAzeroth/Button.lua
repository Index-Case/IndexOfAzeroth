-- The Index of Azeroth. Copyright 2026 Index Case <indexofazeroth@pm.me>. PolyForm Strict 1.0.0, see LICENSE.md.
local ADDON, ns = ...

local ICON = "Interface\\AddOns\\IndexOfAzeroth\\Media\\icon"
local SIZE = 40
local UI, C = ns.UI, ns.UI.C

local button = CreateFrame("Button", "IndexOfAzerothButton", UIParent, "BackdropTemplate")
button:SetSize(SIZE, SIZE)
button:SetPoint("TOP", UIParent, "TOP", 0, -60)
button:SetFrameStrata("MEDIUM")
button:SetFrameLevel(button:GetFrameLevel() + 2)
button:SetMovable(true)
button:SetClampedToScreen(true)
button:RegisterForDrag("LeftButton")
button:RegisterForClicks("LeftButtonUp", "RightButtonUp", "MiddleButtonUp")
UI.Panel(button)

local icon = button:CreateTexture(nil, "ARTWORK")
icon:SetPoint("TOPLEFT", 3, -3)
icon:SetPoint("BOTTOMRIGHT", -3, 3)
icon:SetTexture(ICON)

local hover = button:CreateTexture(nil, "HIGHLIGHT")
hover:SetAllPoints(icon)
hover:SetColorTexture(C.gold[1], C.gold[2], C.gold[3], 0.15)

local runMark = button:CreateTexture(nil, "OVERLAY")
runMark:SetSize(8, 8)
runMark:SetPoint("BOTTOMRIGHT", -2, 2)
runMark:SetColorTexture(C.cyan[1], C.cyan[2], C.cyan[3], 1)
runMark:Hide()

local reload = CreateFrame("Button", nil, button)
reload:SetSize(18, 18)
reload:SetPoint("CENTER", button, "TOPRIGHT", -2, -2)
reload:SetFrameLevel(button:GetFrameLevel() + 3)
reload:SetNormalTexture("Interface\\PaperDollInfoFrame\\UI-GearManager-Undo")
reload:SetHighlightTexture("Interface\\Buttons\\ButtonHilight-Square", "ADD")
reload:SetScript("OnMouseDown", function() ns.ReloadPressed() end)
reload:SetScript("OnClick", function() ns.Reload() end)
reload:SetScript("OnEnter", function(self)
  GameTooltip:SetOwner(self, "ANCHOR_BOTTOMLEFT")
  GameTooltip:AddLine(ns.Word("game.button.reload.tip"))
  GameTooltip:Show()
end)
reload:SetScript("OnLeave", function() GameTooltip:Hide() end)
ns.reloadButton = reload

local cogButton = CreateFrame("Button", nil, button)
cogButton:SetSize(16, 16)
cogButton:SetPoint("CENTER", button, "BOTTOMLEFT", 2, 2)
cogButton:SetFrameLevel(button:GetFrameLevel() + 3)
cogButton:SetNormalTexture("Interface\\Icons\\INV_Misc_Gear_01")
cogButton:SetHighlightTexture("Interface\\Buttons\\ButtonHilight-Square", "ADD")
cogButton:SetScript("OnClick", function() if ns.ToggleOptions then ns.ToggleOptions() end end)
cogButton:SetScript("OnEnter", function(self)
  GameTooltip:SetOwner(self, "ANCHOR_BOTTOMLEFT")
  GameTooltip:AddLine(ns.Word("game.options.window.title"))
  GameTooltip:Show()
end)
cogButton:SetScript("OnLeave", function() GameTooltip:Hide() end)
ns.optionsCog = cogButton

local function StripStatus()
  if not ns.db then return "|cff9d9d9d" .. ns.Word("game.button.strip.loading") .. "|r" end
  if ns.paused then return "|cffffd100" .. ns.Word("game.button.strip.test") .. "|r" end
  return ns.db.strip and "|cff51ccec" .. ns.Word("game.button.strip.sending") .. "|r"
    or "|cff9d9d9d" .. ns.Word("game.button.strip.off") .. "|r"
end

button:SetScript("OnEnter", function(self)
  GameTooltip:SetOwner(self, "ANCHOR_BOTTOMLEFT")
  GameTooltip:AddLine(ns.Word("game.button.name"))
  GameTooltip:AddDoubleLine(ns.Word("game.button.strip"), StripStatus(), 0.8, 0.8, 0.8)
  local ok, _, s = pcall(ns.Collect)
  if ok and s then
    if s.x then GameTooltip:AddDoubleLine(s.zone, string.format("%.1f, %.1f", s.x * 100, s.y * 100), 0.8, 0.8, 0.8, 1, 1, 1) end
  end
  local run, here = ns.RunState()
  if here and run then
    local down, all, rares = ns.RunBosses(run, here)
    GameTooltip:AddDoubleLine(here.name, ns.Word("game.button.bosses", { down = down, all = all }), 0.8, 0.8, 0.8, 1, 1, 1)
    if #rares > 0 then
      GameTooltip:AddLine(ns.Word("game.button.rares", { names = table.concat(rares, ", ") }), 0.8, 0.8, 0.8, true)
    end
  end
  local guide = ns.GuideInfo and ns.GuideInfo()
  if guide then
    local done, all = ns.GuideRunProgress()
    GameTooltip:AddDoubleLine(guide.name, guide.cur and ns.Word("game.button.guide", { cur = guide.cur, done = done, all = all })
      or ns.Word("game.button.guide.done", { done = done, all = all }), 0.8, 0.8, 0.8, unpack(C.gold))
  end
  local cap, text, detail = 0, nil, nil
  if ns.CapWords then cap, text, detail = ns.CapWords() end
  if cap > 0 then
    local g, b = cap >= 4 and 0.29 or 1, cap >= 4 and 0.24 or 1
    GameTooltip:AddDoubleLine(ns.Word("game.button.cap"), ns.Word("game.button.cap.count", { n = cap }), 0.8, 0.8, 0.8, 1, g, b)
    if text == "Instance cap reached" then GameTooltip:AddLine(text, 1, g, b) end
    if detail then GameTooltip:AddLine(detail, 0.8, 0.8, 0.8, true) end
  end
  GameTooltip:AddLine(" ")
  GameTooltip:AddLine(ns.Word("game.button.click"), 0.6, 0.6, 0.6)
  GameTooltip:AddLine(ns.Word("game.button.middle-click"), 0.6, 0.6, 0.6)
  GameTooltip:AddLine(ns.Word("game.button.shift-click"), 0.6, 0.6, 0.6)
  GameTooltip:AddLine(ns.Word("game.button.ctrl-right-click"), 0.6, 0.6, 0.6)
  GameTooltip:AddLine(ns.Word("game.button.cog"), 0.6, 0.6, 0.6)
  GameTooltip:AddLine(ns.Word("game.button.drag"), 0.6, 0.6, 0.6)
  GameTooltip:Show()
end)
button:SetScript("OnLeave", function() GameTooltip:Hide() end)

button:SetScript("OnClick", function(_, which)
  if not ns.db then return end
  if IsShiftKeyDown() then
    ns.Debug()
  elseif which == "RightButton" and IsControlKeyDown() then
    if ns.paused then ns.SetStrip(true) else ns.Test() end
  elseif which == "RightButton" then
    return
  elseif which == "MiddleButton" then
    if ns.OpenPaste then ns.OpenPaste() end
  else
    ns.ToggleGuideCard()
  end
end)

button:SetScript("OnDragStart", function(self)
  self:StartMoving()
  if ns.FollowButton then ns.FollowButton(true) end
end)
button:SetScript("OnDragStop", function(self)
  self:StopMovingOrSizing()
  self:SetUserPlaced(true)
  local point, _, rel, x, y = self:GetPoint()
  if IndexOfAzerothCharDB then IndexOfAzerothCharDB.button = { point, rel, x, y } end
  if ns.FollowButton then ns.FollowButton(false) end
end)

local function KeysAgain() if ns.GuideKeysAgain then ns.GuideKeysAgain() end end

function ns.PlaceButton()
  local saved = IndexOfAzerothCharDB and IndexOfAzerothCharDB.button
  if saved and not button:IsUserPlaced() then
    button:ClearAllPoints()
    button:SetPoint(saved[1], UIParent, saved[2], saved[3], saved[4])
  end
  if IndexOfAzerothCharDB and IndexOfAzerothCharDB.buttonHidden then
    IndexOfAzerothCharDB.buttonHidden = nil
    ns.Options().general.button = false
    ns.Print(ns.Word("game.button.folded"))
  end
  button:SetShown(ns.Options().general.button)
  KeysAgain()
end
ns.OnOptions(function() button:SetShown(ns.Options().general.button); KeysAgain() end)

function ns.ToggleButton(arg)
  local general = ns.Options().general
  if arg == "reset" then
    button:ClearAllPoints()
    button:SetPoint("TOP", UIParent, "TOP", 0, -60)
    button:SetUserPlaced(false)
    if IndexOfAzerothCharDB then IndexOfAzerothCharDB.button = nil end
    general.button = true
    button:Show()
    KeysAgain()
    return ns.Print(ns.Word("game.button.reset"))
  end
  general.button = arg == "on" or (arg ~= "off" and not button:IsShown())
  button:SetShown(general.button)
  KeysAgain()
  ns.Print(ns.SwitchWords(ns.Word("game.chat.switch.name.button"), general.button, "button"))
end

function ns.RefreshButton()
  icon:SetDesaturated(not (ns.db and ns.db.strip) or ns.paused or false)
  local _, here = ns.RunState()
  runMark:SetShown(here ~= nil)
end

local page = CreateFrame("Frame", "IndexOfAzerothSettingsPage")
page:Hide()
page.name = ns.Word("game.button.name")
local pageTitle = UI.Text(page, "GameFontNormalLarge", C.gold)
pageTitle:SetPoint("TOPLEFT", 16, -16)
pageTitle:SetText(page.name)
local pageWords = UI.Text(page, "GameFontHighlight", C.ivory)
pageWords:SetPoint("TOPLEFT", pageTitle, "BOTTOMLEFT", 0, -10)
pageWords:SetWidth(560)
pageWords:SetText(ns.Word("game.settings.words"))
local resetKey = UI.FlatButton(page, ns.Word("game.settings.reset"), 200, function() ns.ToggleButton("reset") end)
resetKey:SetPoint("TOPLEFT", pageWords, "BOTTOMLEFT", 0, -16)
local optionsKey = UI.FlatButton(page, ns.Word("game.settings.options"), 200, function()
  if SettingsPanel and HideUIPanel then HideUIPanel(SettingsPanel) end
  ns.ToggleOptions()
end)
optionsKey:SetPoint("LEFT", resetKey, "RIGHT", 12, 0)
local minimapKey = UI.FlatButton(page, "", 200, function() ns.ToggleMinimapButton() end)
minimapKey:SetPoint("TOPLEFT", resetKey, "BOTTOMLEFT", 0, -12)
local function ShowMinimapKey()
  local on = ns.Options().general.minimap
  minimapKey.label:SetText(on and ns.Word("game.settings.minimap.hide") or ns.Word("game.settings.minimap.show"))
end
page:SetScript("OnShow", ShowMinimapKey)
ns.settingsPage, ns.settingsResetKey, ns.settingsOptionsKey, ns.settingsMinimapKey = page, resetKey, optionsKey, minimapKey

local category
function ns.RegisterSettingsPage()
  if category or not (Settings and Settings.RegisterCanvasLayoutCategory) then return end
  category = Settings.RegisterCanvasLayoutCategory(page, page.name)
  Settings.RegisterAddOnCategory(category)
end
ns.RegisterSettingsPage()

function ns.OpenSettingsPage()
  if InCombatLockdown() then return ns.Print(ns.Word("game.settings.in-combat")) end
  if category and Settings.OpenToCategory then return Settings.OpenToCategory(category:GetID()) end
  ns.ToggleOptions()
end

local MINI = 31
local mini = CreateFrame("Button", "IndexOfAzerothMinimapButton", Minimap)
mini:SetSize(MINI, MINI)
mini:SetFrameStrata("MEDIUM")
mini:SetFrameLevel(8)
mini:RegisterForClicks("LeftButtonUp")
mini:RegisterForDrag("LeftButton")
mini:SetHighlightTexture("Interface\\Minimap\\UI-Minimap-ZoomButton-Highlight")
local miniBack = mini:CreateTexture(nil, "BACKGROUND")
miniBack:SetSize(20, 20)
miniBack:SetPoint("CENTER")
miniBack:SetTexture("Interface\\Minimap\\UI-Minimap-Background")
local miniIcon = mini:CreateTexture(nil, "ARTWORK")
miniIcon:SetSize(18, 18)
miniIcon:SetPoint("CENTER")
miniIcon:SetTexture(ICON)
local miniRing = mini:CreateTexture(nil, "OVERLAY")
miniRing:SetSize(53, 53)
miniRing:SetPoint("TOPLEFT")
miniRing:SetTexture("Interface\\Minimap\\MiniMap-TrackingBorder")

local ROUND_QUARTERS = { ROUND = { true, true, true, true }, SQUARE = { false, false, false, false } }
local function PlaceMini()
  local a = math.rad(ns.Options().general.minimapAngle)
  local x, y, q = math.cos(a), math.sin(a), 1
  if x < 0 then q = q + 1 end
  if y > 0 then q = q + 2 end
  local shape = GetMinimapShape and GetMinimapShape() or "ROUND"
  local round = (ROUND_QUARTERS[shape] or ROUND_QUARTERS.ROUND)[q]
  local w, h = Minimap:GetWidth() / 2 + 5, Minimap:GetHeight() / 2 + 5
  if round then
    x, y = x * w, y * h
  else
    x = math.max(-w, math.min(x * (math.sqrt(2 * w * w) - 10), w))
    y = math.max(-h, math.min(y * (math.sqrt(2 * h * h) - 10), h))
  end
  mini:ClearAllPoints()
  mini:SetPoint("CENTER", Minimap, "CENTER", x, y)
end

local function FollowCursor()
  local mx, my = Minimap:GetCenter()
  local px, py = GetCursorPosition()
  local scale = Minimap:GetEffectiveScale()
  ns.Options().general.minimapAngle = math.deg(math.atan2(py / scale - my, px / scale - mx)) % 360
  PlaceMini()
end
mini:SetScript("OnDragStart", function(self) ns.OnTick(self, ns.Word("game.button.error.drag"), nil, FollowCursor) end)
mini:SetScript("OnDragStop", function(self) self:SetScript("OnUpdate", nil) end)
mini:SetScript("OnClick", function() ns.OpenSettingsPage() end)
mini:SetScript("OnEnter", function(self)
  GameTooltip:SetOwner(self, "ANCHOR_LEFT")
  GameTooltip:AddLine(ns.Word("game.button.name"))
  GameTooltip:AddLine(ns.Word("game.settings.minimap.click"), 0.6, 0.6, 0.6, true)
  GameTooltip:AddLine(ns.Word("game.settings.minimap.drag"), 0.6, 0.6, 0.6)
  GameTooltip:Show()
end)
mini:SetScript("OnLeave", function() GameTooltip:Hide() end)
ns.minimapButton = mini

local function ShowMini()
  mini:SetShown(ns.Options().general.minimap)
  PlaceMini()
  ShowMinimapKey()
end
ns.OnOptions(ShowMini)

function ns.ToggleMinimapButton(arg)
  local general = ns.Options().general
  general.minimap = arg == "on" or (arg ~= "off" and not general.minimap)
  ShowMini()
  ns.Print(ns.SwitchWords(ns.Word("game.chat.switch.name.minimap"), general.minimap, "minimap"))
end

ns.PlaceMinimapButton = ShowMini
