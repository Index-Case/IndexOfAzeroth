-- The Index of Azeroth. Copyright 2026 Index Case <indexofazeroth@pm.me>. PolyForm Strict 1.0.0, see LICENSE.md.
local ADDON, ns = ...

local UI = ns.UI
local WHITE, C, Skin, Box, Text = UI.WHITE, UI.C, UI.Skin, UI.Box, UI.Text
local FlatButton, Scroller, Circle = UI.FlatButton, UI.Scroller, UI.Circle
local Plain, Call = ns.Plain, ns.Call
local G = ns.GUIDE
local function Epic() return ns.GuideInfo() or (ns.PastedGuide and ns.PastedGuide()) end
local CARD_W, CARD_PAD, HEAD_H = 300, 10, 58
local ICON = "Interface\\AddOns\\IndexOfAzeroth\\Media\\icon"
local KIND_ICON = {
  P = "Interface\\GossipFrame\\AvailableQuestIcon", T = "Interface\\GossipFrame\\ActiveQuestIcon",
  O = "Interface\\Cursor\\Attack", D = "Interface\\TargetingFrame\\UI-TargetingFrame-Skull",
}
local KIND_VERB = { P = "Pick up", T = "Turn in", O = "Objective", D = "The dungeon" }
local OBJECTIVE_ICON = { kill = "Interface\\Cursor\\Attack", loot = "Interface\\Icons\\INV_Misc_Bag_12",
  grab = "Interface\\Cursor\\OpenHand", use = "Interface\\Cursor\\Interact", talk = "Interface\\GossipFrame\\GossipGossipIcon",
  heal = "Interface\\Cursor\\Cast", event = "Interface\\Cursor\\QuestInteract",
  explore = "Interface\\Cursor\\Directions", escort = "Interface\\GossipFrame\\BattleMasterGossipIcon",
  buy = "Interface\\GossipFrame\\VendorGossipIcon", pickpocket = "Interface\\Icons\\INV_Misc_Bag_11" }
local ERRAND_ICON = { train = "Interface\\GossipFrame\\TrainerGossipIcon", repair = "Interface\\GossipFrame\\BankerGossipIcon",
  sell = "Interface\\GossipFrame\\BankerGossipIcon", restock = "Interface\\GossipFrame\\VendorGossipIcon",
  bind = "Interface\\Minimap\\Tracking\\Innkeeper", flightpath = "Interface\\GossipFrame\\TaxiGossipIcon",
  learn = "Interface\\GossipFrame\\TrainerGossipIcon", supplies = "Interface\\GossipFrame\\VendorGossipIcon",
  craft = "Interface\\GossipFrame\\TrainerGossipIcon", camp = "Interface\\Minimap\\Tracking\\Food",
  wall = "Interface\\DialogFrame\\UI-Dialog-Icon-AlertNew", farm = "Interface\\Cursor\\Attack" }
local function ItemIcon(s)
  if not (s.it and (s.ic == "grab" or s.ic == "loot" or s.what == "farm")) then return nil end
  return Plain(Call(C_Item and C_Item.GetItemIconByID, s.it)) or Plain(Call(GetItemIcon, s.it))
end
local function StepIcon(s)
  return (s.kind == "S" and (ItemIcon(s) or ERRAND_ICON[s.what])) or (s.kind == "O" and (ItemIcon(s) or OBJECTIVE_ICON[s.ic]))
    or KIND_ICON[s.kind] or ICON
end
local STAGES = { { "prep", "Prep" }, { "travel", "Travel" }, { "inside", "Inside" }, { "turnin", "Turn in" } }
local RING_SEGMENTS, RING_R = 40, 21
local BRONZE_DARK = { 0.35, 0.25, 0.12 }
local TOAST_SECONDS, OBJECTIVES_MOST, LIST_ROW = 4, 4, 18
local STATE_COLOR = { [G.TODO] = C.ivory, [G.DONE] = C.muted, [G.SKIPPED] = C.muted, [G.BLOCKED] = C.red, [G.PARKED] = C.cyan }
local HOLD_WORD = { [G.BLOCKED] = "Blocked", [G.PARKED] = "Parked", [G.SKIPPED] = "Skipped" }
local LIST_TICK, LIST_ARROW = "Interface\\Buttons\\UI-CheckBox-Check", "Interface\\ChatFrame\\ChatFrameExpandArrow"
local function ListHold(s, state, level)
  if state == G.WAIT then
    if (s.min or 0) > level then return "Level " .. s.min, C.yellow end
    return nil, C.ivory
  end
  return HOLD_WORD[state], STATE_COLOR[state] or C.ivory
end

local CARD_X, CARD_Y = -60, -200
local card = Box(UIParent, C.bg, C.edge, "MEDIUM")
card:SetSize(CARD_W, 120)
card:SetPoint("TOPRIGHT", UIParent, "TOPRIGHT", CARD_X, CARD_Y)
card:SetMovable(true)
card:SetClampedToScreen(true)
card:EnableMouse(true)
card:Hide()
ns.guideCard = card

local cardHead = CreateFrame("Frame", nil, card)
cardHead:SetPoint("TOPLEFT", 1, -1)
cardHead:SetPoint("TOPRIGHT", -1, -1)
cardHead:SetHeight(HEAD_H)
cardHead:EnableMouse(true)
cardHead:RegisterForDrag("LeftButton")
cardHead:SetScript("OnDragStart", function() if not InCombatLockdown() then card:StartMoving() end end)
cardHead:SetScript("OnDragStop", function()
  card:StopMovingOrSizing()
  local left, top = card:GetLeft(), card:GetTop()
  if not (left and top) then return end
  card:ClearAllPoints()
  card:SetPoint("TOPLEFT", UIParent, "BOTTOMLEFT", left, top)
  ns.GuideSaved().pos = { "TOPLEFT", "BOTTOMLEFT", left, top }
  if ns.PlaceGuideKeys then ns.PlaceGuideKeys() end
end)

local WIDE_MOST = 600
local grip = CreateFrame("Button", nil, card)
grip:SetSize(16, 16)
grip:SetPoint("BOTTOMRIGHT", -2, 2)
grip:SetFrameLevel(card:GetFrameLevel() + 10)
grip:SetNormalTexture("Interface\\ChatFrame\\UI-ChatIM-SizeGrabber-Up")
grip:SetHighlightTexture("Interface\\ChatFrame\\UI-ChatIM-SizeGrabber-Highlight")
grip:SetPushedTexture("Interface\\ChatFrame\\UI-ChatIM-SizeGrabber-Down")
ns.guideGrip = grip
local size = { w = CARD_W, h = nil, shown = 0 }
local function CardSize(w, h)
  local tall = Plain(Call(UIParent.GetHeight, UIParent))
  size.w = math.max(CARD_W, math.min(WIDE_MOST, math.floor((tonumber(w) or CARD_W) + 0.5)))
  size.h = tonumber(h) and math.max(0, math.min(tall or h, math.floor(h + 0.5))) or nil
  if ns.CardRender then ns.CardRender() end
end
ns.GuideCardSize = CardSize
local Cursor = UI.Cursor
grip:SetScript("OnMouseDown", function(self)
  if InCombatLockdown() then return end
  local x, y = Cursor()
  local left, top = Plain(Call(card.GetLeft, card)), Plain(Call(card.GetTop, card))
  local high = Plain(Call(card.GetHeight, card))
  if not (x and left and top and high) then return end
  card:ClearAllPoints()
  card:SetPoint("TOPLEFT", UIParent, "BOTTOMLEFT", left, top)
  self.from, self.was = { x, y }, { size.w, high }
end)
ns.OnTick(grip, "the card's size grip", nil, function(self)
  if not self.from then return end
  local x, y = Cursor()
  if not x then return end
  local w, h = self.was[1] + (x - self.from[1]), self.was[2] - (y - self.from[2])
  if w ~= self.at or h ~= self.atH then
    self.at, self.atH = w, h
    CardSize(w, h)
  end
end)
grip:SetScript("OnMouseUp", function(self)
  if not self.from then return end
  self.from, self.at, self.atH = nil, nil, nil
  if size.h and size.h <= size.shown then size.h = nil end
  ns.GuideSaved().size = (size.w ~= CARD_W or size.h) and { w = size.w, h = size.h } or nil
  ns.CardRender()
  local left, top = Plain(Call(card.GetLeft, card)), Plain(Call(card.GetTop, card))
  if left and top then ns.GuideSaved().pos = { "TOPLEFT", "BOTTOMLEFT", left, top } end
  if ns.PlaceGuideKeys then ns.PlaceGuideKeys() end
end)

local ring = CreateFrame("Frame", nil, cardHead)
ring:SetSize(46, 46)
ring:SetPoint("LEFT", 8, 0)
local ringIcon = ring:CreateTexture(nil, "ARTWORK")
ringIcon:SetSize(36, 36)
ringIcon:SetPoint("CENTER")
ringIcon:SetTexture(ICON)
local ringLines = Circle(ring, RING_SEGMENTS, RING_R, 3)
local function SetRing(share)
  local lit = math.floor(share * RING_SEGMENTS + 0.5)
  for k, line in ipairs(ringLines) do
    local c = k <= lit and C.gold or BRONZE_DARK
    line:SetColorTexture(c[1], c[2], c[3], 1)
  end
end

local folded, combatFolded, listShown = false, false, false
local ui = {}
ns.guideUI, ui.CARD_W, ui.CARD_X, ui.CARD_Y = ui, CARD_W, CARD_X, CARD_Y
ui.lines = {}
function ui.Line(parent, font, color)
  local fs = UI.Line.New(parent, font, color)
  ui.lines[#ui.lines + 1] = fs
  return fs
end
function ui.Span(fs, at, on, x, y, right, rightX)
  fs.box:ClearAllPoints()
  fs.box:SetPoint("TOPLEFT", on, at, x, y)
  fs.box:SetPoint("RIGHT", right, "RIGHT", rightX, 0)
  UI.Line.Fit(fs)
end

local cardTitle = ui.Line(cardHead, "GameFontHighlightLarge", C.ivory)
ui.Span(cardTitle, "TOPRIGHT", ring, 8, -2, cardHead, -76)
local cardSub = ui.Line(cardHead, "GameFontDisableSmall", C.muted)
ui.Span(cardSub, "BOTTOMLEFT", cardTitle.box, 0, -3, cardHead, -8)
ns.guideCardSub = cardSub
ui.levelLine = ui.Line(cardHead, "GameFontDisableSmall", C.muted)
ui.Span(ui.levelLine, "BOTTOMLEFT", cardSub.box, 0, -2, cardHead, -8)
ns.guideLevelLine = ui.levelLine

ui.rules, ui.RULE_W, ui.RULE_ALPHA = {}, 220, 0.7
function ui.NewRule(parent)
  local e, halves = C.edge, {}
  for k = 1, 2 do
    local t = parent:CreateTexture(nil, "ARTWORK")
    t:SetSize(ui.RULE_W / 2, 1)
    t:SetColorTexture(1, 1, 1, 1)
    local mid, ends = CreateColor(e[1], e[2], e[3], ui.RULE_ALPHA), CreateColor(e[1], e[2], e[3], 0)
    if not pcall(t.SetGradient, t, "HORIZONTAL", k == 1 and ends or mid, k == 1 and mid or ends) then
      t:SetColorTexture(e[1], e[2], e[3], ui.RULE_ALPHA / 2)
    end
    halves[k] = t
  end
  return halves
end
function ui.PlaceRule(r, on, y)
  r[1]:ClearAllPoints(); r[1]:SetPoint("TOPRIGHT", on, "TOP", 0, -y); r[1]:Show()
  r[2]:ClearAllPoints(); r[2]:SetPoint("TOPLEFT", on, "TOP", 0, -y); r[2]:Show()
end

ui.WARN_ART, ui.Icon = UI.WARN_ART, UI.Icon
ns.GuideIcon, ns.guideWarnArt = ui.Icon, ui.WARN_ART
ns.GuideStepIcon = StepIcon
local foldButton = FlatButton(cardHead, "-", 20, function() folded = not folded; ui.Render() end)
foldButton:SetSize(20, 20)
foldButton:SetPoint("TOPRIGHT", -28, -6)
local closeButton = FlatButton(cardHead, "x", 20, function() ns.GuideStop() end)
closeButton:SetSize(20, 20)
closeButton:SetPoint("TOPRIGHT", -6, -6)
closeButton:HookScript("OnEnter", function(self)
  GameTooltip:SetOwner(self, "ANCHOR_BOTTOM")
  GameTooltip:AddLine("Stop the quest epic, here and on the page")
  GameTooltip:Show()
end)
closeButton:HookScript("OnLeave", function() GameTooltip:Hide() end)
do
  local b = CreateFrame("Button", nil, cardHead, "BackdropTemplate")
  b:SetSize(20, 20)
  b:SetPoint("TOPRIGHT", -50, -6)
  Skin(b, C.row, C.edge)
  local cog = b:CreateTexture(nil, "ARTWORK")
  cog:SetPoint("TOPLEFT", 2, -2)
  cog:SetPoint("BOTTOMRIGHT", -2, 2)
  cog:SetTexture("Interface\\Icons\\INV_Misc_Gear_01")
  cog:SetTexCoord(0.08, 0.92, 0.08, 0.92)
  local lit = b:CreateTexture(nil, "HIGHLIGHT")
  lit:SetAllPoints(cog)
  lit:SetColorTexture(C.gold[1], C.gold[2], C.gold[3], 0.2)
  b:SetScript("OnClick", function() if ns.ToggleOptions then ns.ToggleOptions() end end)
  b:SetScript("OnEnter", function(self)
    GameTooltip:SetOwner(self, "ANCHOR_BOTTOM")
    GameTooltip:AddLine("Options")
    GameTooltip:Show()
  end)
  b:SetScript("OnLeave", function() GameTooltip:Hide() end)
  ns.cardOptionsButton = b
end

local stageRow = CreateFrame("Frame", nil, card)
stageRow:SetPoint("TOPLEFT", cardHead, "BOTTOMLEFT", CARD_PAD - 1, -2)
stageRow:SetHeight(16)
local stageParts = {}
for k, st in ipairs(STAGES) do
  local part = CreateFrame("Frame", nil, stageRow)
  local back = part:CreateTexture(nil, "ARTWORK")
  back:SetColorTexture(C.dim[1], C.dim[2], C.dim[3], 1)
  back:SetPoint("TOPLEFT")
  back:SetPoint("TOPRIGHT")
  back:SetHeight(3)
  local fill = part:CreateTexture(nil, "OVERLAY")
  fill:SetColorTexture(C.gold[1], C.gold[2], C.gold[3], 1)
  fill:SetPoint("TOPLEFT")
  fill:SetSize(1, 3)
  local label = Text(part, "GameFontDisableSmall", C.muted)
  label:SetPoint("TOPLEFT", 0, -5)
  label:SetText(st[2]:upper())
  stageParts[k] = { key = st[1], part = part, fill = fill, label = label }
end
function ui.BodyW() return size.w - 2 * CARD_PAD end
function ui.StageW() return (ui.BodyW() - 3 * 4) / 4 end

local cardBody = CreateFrame("Frame", nil, card)
cardBody:SetPoint("TOPLEFT", stageRow, "BOTTOMLEFT", 0, -6)
cardBody:SetSize(CARD_W - 2 * CARD_PAD, 10)
ui.headRule = ui.NewRule(cardBody)
function ui.Stages(g, open)
  local staged = g.dungeon ~= nil
  stageRow:SetShown(open and staged)
  cardBody:ClearAllPoints()
  cardBody:SetPoint("TOPLEFT", cardHead, "BOTTOMLEFT", CARD_PAD - 1, staged and -24 or -11)
  if staged then ui.headRule[1]:Hide(); ui.headRule[2]:Hide() else ui.PlaceRule(ui.headRule, cardBody, -5) end
  ui.faceDrop = 1 + HEAD_H + (staged and 24 or 11)
  return staged and 24 or 11
end
local FACE = 44
ui.FACE, ui.FACE_IN, ui.faceDrop = FACE, CARD_PAD, 1 + HEAD_H + 11
local face = CreateFrame("Frame", nil, cardBody)
face:SetSize(FACE, FACE)
face:SetPoint("TOPRIGHT", cardBody, "TOPRIGHT", 0, 0)
face.tex = face:CreateTexture(nil, "ARTWORK")
face.tex:SetPoint("TOPLEFT", 3, -3)
face.tex:SetPoint("BOTTOMRIGHT", -3, 3)
for _, line in ipairs(Circle(face, 32, FACE / 2 - 1, 2)) do line:SetColorTexture(C.gold[1], C.gold[2], C.gold[3], 1) end
face:Hide()
ns.guideFace = face
local parts = { stages = stageRow, rules = ui.rules, headRule = ui.headRule }
ns.guideCardParts = parts
parts.kind = cardBody:CreateTexture(nil, "ARTWORK")
parts.kind:SetSize(12, 12)
parts.name = Text(cardBody, "GameFontNormalLarge", C.gold)
parts.who = Text(cardBody, "GameFontHighlight", C.ivory)
parts.money = ui.Line(cardBody, "GameFontHighlightSmall", C.ivory)
parts.where = Text(cardBody, "GameFontHighlightSmall", C.cyan)
parts.why = Text(cardBody, "GameFontHighlightSmall", C.yellow)
parts.nextLabel = Text(cardBody, "GameFontDisableSmall", C.muted)
parts.nextLabel:SetText("NEXT")
local CLASS_HEX = { [1] = "c79c6e", [2] = "f58cba", [3] = "abd473", [4] = "fff569", [5] = "ffffff", [7] = "0070de",
                    [8] = "69ccf0", [9] = "9482c9", [11] = "ff7d0a" }
parts.partyLabel = Text(cardBody, "GameFontDisableSmall", C.muted)
parts.partyLabel:SetText("PARTY")
parts.party = Text(cardBody, "GameFontHighlightSmall", C.ivory)
parts.door = Text(cardBody, "GameFontHighlightSmall", C.cyan)
parts.next = Text(cardBody, "GameFontHighlightSmall", C.ivory)
local objRows = {}
ns.guideObjRows = objRows
local function ObjBadge(parent)
  local b = CreateFrame("Frame", nil, parent, "BackdropTemplate")
  b:SetSize(56, 14)
  b:SetBackdrop({ bgFile = WHITE, edgeFile = WHITE, edgeSize = 1 })
  b:SetBackdropBorderColor(0, 0, 0, 1)
  b.text = b:CreateFontString(nil, "OVERLAY", "GameFontNormalSmall")
  b.text:SetPoint("CENTER")
  b.text:SetTextColor(0.06, 0.06, 0.06)
  return b
end
local function ObjBar(parent)
  local bar = CreateFrame("StatusBar", nil, parent)
  bar:SetStatusBarTexture(WHITE)
  bar:SetStatusBarColor(C.gold[1], C.gold[2], C.gold[3], 1)
  bar:SetSize(CARD_W - 2 * CARD_PAD, 4)
  bar.spans = true
  local bg = bar:CreateTexture(nil, "BACKGROUND")
  bg:SetAllPoints()
  bg:SetColorTexture(C.dim[1], C.dim[2], C.dim[3], 1)
  return bar
end
local function SayBadge(badge, words, c)
  badge.text:SetText(words or "")
  badge:SetBackdropColor(c[1], c[2], c[3], 0.95)
  badge:SetWidth(math.max(40, (badge.text:GetStringWidth() or 40) + 10))
  badge:SetShown(words ~= nil)
end
local function BadgeRow(parent)
  local fs = ui.Line(parent, "GameFontHighlightSmall", C.ivory)
  fs.badge = ObjBadge(parent)
  UI.Line.Beside(fs, fs.badge, "BOTTOMRIGHT", -1)
  return fs
end
local function ShowObjective(badge, bar, o, c)
  SayBadge(badge, ns.ObjectiveLeft(o), c)
  local finished = Plain(o.finished)
  local fill = finished and C.green or c
  bar:SetStatusBarColor(fill[1], fill[2], fill[3], 1)
  local need = math.max(1, Plain(o.numRequired) or 1)
  bar:SetMinMaxValues(0, need)
  bar:SetValue(math.min(need, Plain(o.numFulfilled) or (finished and need or 0)))
end
local function ObjRow(k)
  if objRows[k] then return objRows[k] end
  local text = BadgeRow(cardBody)
  local r = { text = text, left = text.badge, bar = ObjBar(cardBody) }
  objRows[k] = r
  return r
end

local bossRows = {}
ns.guideBossRows = bossRows
local function BossRow(k)
  if bossRows[k] then return bossRows[k] end
  local r = { dot = cardBody:CreateTexture(nil, "ARTWORK"), name = Text(cardBody, "GameFontHighlight", C.ivory),
              quests = Text(cardBody, "GameFontHighlightSmall", C.gold) }
  r.dot:SetSize(8, 8)
  bossRows[k] = r
  return r
end

local function BossTrack(g, s)
  local run, here = ns.RunState()
  local d = ns.DungeonByKey and ns.DungeonByKey[g.key]
  if s.kind ~= "D" or not s.bosses or not here then return nil end
  if here.key ~= g.key and not (d and d.instance == here.instance) then return nil end
  local out, found = {}, false
  for _, b in ipairs(s.bosses) do
    local down = ns.RunKilledByName(run, here, b.n)
    out[#out + 1] = { name = b.n, quests = b.q, down = down, now = not down and not found, face = b.f }
    found = found or not down
  end
  return out
end

ns.GuideBossTrack = BossTrack

local function FaceOf(g, s)
  if s.kind ~= "D" then return s.face end
  local track = BossTrack(g, s)
  if track then
    for _, b in ipairs(track) do if b.now then return b.face end end
    return nil
  end
  local last = nil
  for _, b in ipairs(s.bosses or {}) do if b.q then last = b.f end end
  return last or (s.bosses and #s.bosses > 0 and s.bosses[#s.bosses].f) or nil
end

ns.GuideFace = FaceOf

local stepsButton = FlatButton(cardBody, "Steps", 88, function() listShown = not listShown; ui.Render() end)
local parkButton = FlatButton(cardBody, "Park", 88, function()
  local g = ns.GuideInfo()
  if g and g.cur then ns.GuidePark(g.cur) end
end)
local shareButton = FlatButton(cardBody, "Share", 88, function() ns.GuideShareNext() end)
ui.skipButton = FlatButton(cardBody, "Skip", 88, function()
  local g = ns.GuideInfo()
  if g and g.cur then ns.GuideSkip(g.cur) end
end)
ui.laterButton = FlatButton(cardBody, ns.Rules.Say("later"), 88, function()
  local g = ns.GuideInfo()
  if g and g.cur then ns.Arbiter.Later(g.cur) end
end)

ui.easyButton = FlatButton(cardBody, "Take the easy way", 160, function()
  local g = ns.GuideInfo()
  local s = g and g.cur and g.steps[g.cur]
  if s then ns.GuidePickWay(g.cur, not s.easyPicked) end
end)
ui.easyButton:Hide()
ns.guideEasyButton = ui.easyButton
function ui.RenderEasy(g, s, i, lay)
  if g.pasted or i ~= g.cur or not ns.GuideEasyOpen() then return ui.easyButton:Hide() end
  ui.easyButton.label:SetText(s.easyPicked and "Take the quick way" or "Take the easy way")
  ui.easyButton:SetWidth(lay.Width())
  lay.Place(ui.easyButton, 22, 4)
end

local list = Box(card, C.panel, C.dim)
list:SetPoint("TOPLEFT", card, "BOTTOMLEFT", 0, -2)
list:SetPoint("TOPRIGHT", card, "BOTTOMRIGHT", 0, -2)
list:SetHeight(220)
list:Hide()
local listScroll = Scroller(list)
listScroll:SetPoint("TOPLEFT", 6, -6)
listScroll:SetPoint("BOTTOMRIGHT", -6, 6)
local listRows = {}
ns.guideListRows = listRows
local function ListRow(k)
  if listRows[k] then return listRows[k] end
  local r = CreateFrame("Frame", nil, listScroll.child)
  r:SetHeight(LIST_ROW)
  r:SetPoint("TOPLEFT", 0, -(k - 1) * LIST_ROW)
  r:SetPoint("RIGHT", listScroll.child, "RIGHT", -4, 0)
  r.back = r:CreateTexture(nil, "BACKGROUND")
  r.back:SetAllPoints()
  r.mark = r:CreateTexture(nil, "ARTWORK")
  r.mark:SetSize(12, 12)
  r.mark:SetPoint("LEFT", 2, 0)
  r.mark:SetDesaturated(true)
  r.icon = r:CreateTexture(nil, "ARTWORK")
  r.icon:SetSize(14, 14)
  r.icon:SetPoint("LEFT", 18, 0)
  r.tag = Text(r, "GameFontHighlightSmall", C.ivory)
  r.tag:SetPoint("RIGHT", -4, 0)
  r.text = Text(r, "GameFontHighlightSmall", C.ivory)
  r.text:SetPoint("LEFT", 36, 0)
  r.text:SetPoint("RIGHT", r.tag, "LEFT", -4, 0)
  r.text:SetWordWrap(false)
  r:EnableMouse(true)
  r:SetScript("OnMouseUp", function(self)
    if self.parked then return ns.GuideUnpark(k) end
    if self.aside then
      ui.asidePick = ui.asidePick ~= k and k or nil
      ui.Render()
    end
  end)
  r:SetScript("OnEnter", function(self)
    if not self.parked and not self.detail and not self.aside then return end
    GameTooltip:SetOwner(self, "ANCHOR_RIGHT")
    if self.parked then
      GameTooltip:AddLine("This step is parked and still to do. Click it to put the step back in the guide now, fitted in from the character's spot.")
    elseif self.aside then
      GameTooltip:AddLine(ns.Rules.Line("buttons", "background_row_tip"), 1, 1, 1, true)
    end
    if self.detail then GameTooltip:AddLine(self.detail, 1, 1, 1, true) end
    GameTooltip:Show()
  end)
  r:SetScript("OnLeave", function() GameTooltip:Hide() end)
  listRows[k] = r
  return r
end

local toast = Box(UIParent, C.bg, C.edge, "MEDIUM")
toast:SetHeight(24)
toast:SetPoint("BOTTOMLEFT", card, "TOPLEFT", 0, 4)
toast:SetPoint("BOTTOMRIGHT", card, "TOPRIGHT", 0, 4)
toast:Hide()
local toastEdge = toast:CreateTexture(nil, "ARTWORK")
toastEdge:SetColorTexture(C.gold[1], C.gold[2], C.gold[3], 1)
toastEdge:SetPoint("TOPLEFT")
toastEdge:SetPoint("BOTTOMLEFT")
toastEdge:SetWidth(2)
local toastText = Text(toast, "GameFontHighlightSmall", C.ivory)
toastText:SetPoint("LEFT", 10, 0)
toastText:SetPoint("RIGHT", -8, 0)
toastText:SetWordWrap(false)
ui.toastText = toastText
local toastLeft = 0
local function Toast(text)
  if not card:IsShown() or not ns.Options().card.did then return ns.Print(text) end
  toastText:SetText((text:gsub("^%l", string.upper)))
  toastLeft = TOAST_SECONDS
  toast:SetAlpha(1)
  toast:Show()
end

ui.lfgButton = FlatButton(cardBody, "LFG", 88, function() if ui.lfgFor then Toast(ns.Lfg.Post(ui.lfgFor)) end end)
ui.lfgButton:HookScript("OnEnter", function(self) if ui.lfgFor then ns.Lfg.Tip(self, ui.lfgFor) end end)
ui.lfgButton:HookScript("OnLeave", function() GameTooltip:Hide() end)
ns.guideLfgButton = ui.lfgButton

local function Shown(g)
  if g.cur then return g.steps[g.cur], g.cur end
  for i, s in ipairs(g.steps) do
    if g.state[i] == G.WAIT or g.state[i] == G.BLOCKED then return s, i end
  end
  for i, s in ipairs(g.steps) do
    if g.state[i] == G.PARKED then return s, i end
  end
end
ns.GuideShown = Shown

local function StageFills(g)
  local d = g.dungeon
  local count = { prep = { 0, 0 }, turnin = { 0, 0 } }
  for k = 1, #g.steps do
    local key = (not d or k < d) and "prep" or (k > d and "turnin" or nil)
    if key and g.state[k] ~= G.SKIPPED then
      count[key][2] = count[key][2] + 1
      if g.state[k] == G.DONE then count[key][1] = count[key][1] + 1 end
    end
  end
  local function share(c) return c[2] > 0 and c[1] / c[2] or 0 end
  local out = { prep = share(count.prep), turnin = share(count.turnin), travel = 0, inside = 0 }
  if d then
    local ran = g.state[d] == G.DONE
    out.travel = (ran or Plain(Call(IsInInstance)) or count.turnin[1] > 0) and 1 or 0
    out.inside = ran and 1 or 0
  end
  return out
end
ns.GuideStageFills = StageFills

local function Zone(s) return s.zone and not (ns.BeaconInZone and ns.BeaconInZone(s)) and ("  |  " .. s.zone) or "" end

local function WhereText(g, s)
  local track = BossTrack(g, s)
  if track then
    local down = 0
    for _, b in ipairs(track) do if b.down then down = down + 1 end end
    return string.format("Inside, %d of %d bosses down", down, #track)
  end
  if ns.Ghost() then return "Your corpse run comes first" end
  if not s.wx then return "The addon has no place on the map for this step, so do the step wherever it is." end
  if g.cur == s.i and ns.GuideAtLoop and ns.GuideAtLoop() then
    return s.walks and "The step's path is on your minimap, in blue." or "You're at the camp. Follow the blue loop."
  end
  if g.cur == s.i and ns.GuideInArea and ns.GuideInArea() then return ns.Word("game.card.in-area") end
  local continent, px, py = ns.PlayerWorldPos()
  local t = ns.TrackTarget("e")
  t = t and (t.guided or t.pasted) and t or nil
  local riding = t and g.cur == s.i and t.route and t.route:UnderWay(continent, px, py)
  if riding then return ns.RideNowText(riding, t.route, continent, px, py) .. Zone(s) end
  if t and t.along and g.cur == s.i then
    local ride = t.route and t.route:NextRide()
    if ride then return string.format("%d yd, then %s", t.along, ns.RideText(ride)) end
    return string.format("%d yd%s", t.along, Zone(s))
  end
  if not continent then return s.zone or "" end
  if continent ~= s.inst then return "on another continent" .. Zone(s) end
  return string.format("%d yd%s", ns.Geo.Dist(s.wx, s.wy, px, py), Zone(s))
end
ns.GuideWhere = WhereText

local function MobLevel(s, k)
  if type(s.lv) ~= "table" then return nil end
  local lv = s.lv[k]
  if type(lv) ~= "table" or lv[1] == nil then return "Level not known" end
  local lo, hi = tostring(lv[1]), tostring(lv[2] or lv[1])
  return "Level " .. (lo == hi and lo or (lo .. "-" .. hi))
end
ns.GuideMobLevel = MobLevel

local function WhoText(s)
  if s.kind == "P" or s.kind == "T" or s.kind == "S" then return s.npc end
  if s.kind == "D" then return string.format("%d quest%s inside", #s.ids, #s.ids == 1 and "" or "s") end
  if s.mobs and #s.mobs > 0 then
    local names = {}
    for k, name in ipairs(s.mobs) do
      local lv = MobLevel(s, k)
      names[k] = lv and (name .. " (" .. lv .. ")") or name
    end
    return table.concat(names, ", ")
  end
  return s.target
end

local function RowText(s, text)
  for k, name in ipairs(s.kind == "O" and s.mobs or {}) do
    local lv = MobLevel(s, k)
    if lv and text:find(name, 1, true) then return text .. "  |cff9e9e9e" .. lv .. "|r" end
  end
  return text
end

local function NextWords(s)
  local words = s.kind == "D" and (s.name or "the dungeon") or (s.kind == "S" or s.kind == "O") and s.text
    or ((KIND_VERB[s.kind] or "") .. " " .. (s.name or s.text))
  return ui.Icon(StepIcon(s)) .. words
end
local function AfterOf(g, from)
  local d = g.decision
  local after = from and d and d.afterOf and d.afterOf == g.steps[from] and d.afterStep or nil
  if not after or after == g.steps[from] then return nil end
  local back = g.planCur and g.planCur < from and g.planCur or nil
  for k = (back or from) + (back and 0 or 1), #g.steps do
    if k ~= from and (g.state[k] == G.TODO or g.state[k] == G.WAIT) then return g.steps[k] ~= after and after or nil end
  end
  return after
end
function ns.NextAfter(g) return g and g.cur and AfterOf(g, g.cur) or nil end

local function ThenText(g, from)
  local lines, shown, rows = {}, g.steps[from or 0], {}
  for _, s in ipairs(ui.AlongShown(g, from)) do rows[s] = true end
  for _, s in ipairs(ui.ChoreSteps(g)) do rows[s] = true end
  local function OnCard(s)
    return rows[s] or (shown ~= nil and ns.Rules.OnCard(shown.kind, shown.ids, s.kind, s.ids and s.ids[1]))
  end
  local after = AfterOf(g, from)
  if after and not OnCard(after) then lines[1] = NextWords(after) end
  local back = g.planCur and from and g.planCur < from and g.planCur or nil
  for k = (back or from or 0) + (back and 0 or 1), #g.steps do
    if #lines == 2 then break end
    local s = g.steps[k]
    if k ~= from and s ~= after and not OnCard(s) and (g.state[k] == G.TODO or g.state[k] == G.WAIT) then
      lines[#lines + 1] = NextWords(s)
    end
  end
  return table.concat(lines, "\n")
end

local function Objectives(s)
  local out, from = {}, {}
  if s.kind == "P" then return out, from end
  local items = ns.ItemObjectives(s)
  if items then
    for k = 1, #items do from[k] = { id = s.key, k = k } end
    return items, from
  end
  for _, id in ipairs(s.ids or {}) do
    for k, o in ipairs(ns.QuestObjectives(id)) do
      if #out < OBJECTIVES_MOST and type(o) == "table" then
        local n = #out + 1
        out[n], from[n] = o, { id = id, k = k }
      end
    end
  end
  return out, from
end

local function Height(fs) return math.max(12, fs:GetStringHeight() or 12) end

local COIN = "%d|TInterface\\MoneyFrame\\UI-%sIcon:0:0:2:0|t"
local function Coins(c)
  c = math.max(0, math.floor(c or 0))
  local s = Plain(Call(GetMoneyString, c)) or Plain(Call(C_CurrencyInfo and C_CurrencyInfo.GetCoinTextureString, c))
  if type(s) == "string" and s ~= "" then return s end
  local g, si, co, parts = math.floor(c / 10000), math.floor(c / 100) % 100, c % 100, {}
  if g > 0 then parts[#parts + 1] = COIN:format(g, "Gold") end
  if si > 0 then parts[#parts + 1] = COIN:format(si, "Silver") end
  if co > 0 or #parts == 0 then parts[#parts + 1] = COIN:format(co, "Copper") end
  return table.concat(parts, " ")
end
ns.Coins = Coins

ui.timerRows, ui.timerFull = {}, {}
ns.guideTimerRows = ui.timerRows
function ui.TimeLeft(sec)
  sec = math.max(0, math.floor(sec))
  if sec >= 3600 then return string.format("%d h %d min left", math.floor(sec / 3600), math.floor(sec % 3600 / 60)) end
  if sec >= 600 then return string.format("%d min left", math.floor(sec / 60)) end
  return string.format("%d:%02d left", math.floor(sec / 60), sec % 60)
end
function ui.TimerRow(k)
  local r = ui.timerRows[k]
  if r then return r end
  r = { text = Text(cardBody, "GameFontHighlightSmall", C.cyan) }
  r.bar = CreateFrame("StatusBar", nil, cardBody)
  r.bar:SetStatusBarTexture(WHITE)
  r.bar:SetSize(CARD_W - 2 * CARD_PAD, 3)
  r.bar.spans = true
  local bg = r.bar:CreateTexture(nil, "BACKGROUND")
  bg:SetAllPoints()
  bg:SetColorTexture(C.dim[1], C.dim[2], C.dim[3], 1)
  ui.timerRows[k] = r
  return r
end
function ui.Timers(place)
  for _, r in ipairs(ui.timerRows) do r.text:Hide(); r.bar:Hide() end
  if not place then return end
  local g, mine, limits, list = Epic(), {}, {}, {}
  for _, st in ipairs(g and g.steps or {}) do
    for _, id in ipairs(st.ids or {}) do
      mine[id] = true
      if st.limit then limits[id] = st.limit end
    end
  end
  for id, left in pairs(ns.QuestTimers()) do list[#list + 1] = { id = id, left = left, rank = mine[id] and 0 or 1 } end
  table.sort(list, function(a, b)
    if a.rank ~= b.rank then return a.rank < b.rank end
    if a.left ~= b.left then return a.left < b.left end
    return a.id < b.id
  end)
  for k, t in ipairs(list) do
    local r = ui.TimerRow(k)
    local full = math.max(ui.timerFull[t.id] or 0, t.left, limits[t.id] or 0)
    ui.timerFull[t.id] = full
    local late = t.left < full / 5
    local c = late and C.red or C.cyan
    r.text:SetText((Plain(Call(C_QuestLog.GetTitleForQuestID, t.id)) or "A timed quest") .. ": " .. ui.TimeLeft(t.left))
    r.text:SetTextColor(c[1], c[2], c[3])
    place(r.text, nil, 2)
    r.bar:SetStatusBarColor(c[1], c[2], c[3], 1)
    r.bar:SetMinMaxValues(0, full)
    r.bar:SetValue(t.left)
    place(r.bar, 3, 5)
  end
end

ui.alongRows = {}
ns.guideAlongRows = ui.alongRows
function ui.AlongYards(s, continent, px, py)
  if not (px and s.wx and s.inst == continent) then return math.huge end
  local d = ns.Geo.Dist(s.wx, s.wy, px, py)
  if s.loop then d = math.min(d, (select(3, ns.NearestOnLoop(s, px, py)))) end
  return d
end
function ui.AlongSteps(g, i)
  local out = {}
  if not g then return out end
  local continent, px, py = ns.PlayerWorldPos()
  local shown = g.steps[i or 0]
  if not (shown and px and shown.wx and shown.inst == continent) then return out end
  local leg = {}
  for _, p in ipairs(shown.al or {}) do leg[p] = true end
  local seen, yards, at = {}, {}, {}
  for j, s in ipairs(g.steps) do
    local key = (s.ids[1] or "") .. "\n" .. (s.target or s.text)
    if j ~= i and not seen[key] and s.kind == "O" and g.state[j] == G.TODO and s.wx and s.inst == continent
       and not ns.Rules.OnCard(shown.kind, shown.ids, s.kind, s.ids[1])
       and ((s.p and leg[s.p]) or ns.Rules.SpawnedNear(s.sp, px, py)) then
      seen[key], yards[s], at[s] = true, ui.AlongYards(s, continent, px, py), j
      out[#out + 1] = s
    end
  end
  local after = g.decision and g.decision.afterStep
  for _, s in ipairs(ns.Arbiter.givers or {}) do
    if s ~= shown and s ~= after and not at[s] and s.wx and s.inst == continent then
      yards[s], at[s] = ui.AlongYards(s, continent, px, py), s.i or math.huge
      out[#out + 1] = s
    end
  end
  table.sort(out, function(a, b) if yards[a] ~= yards[b] then return yards[a] < yards[b] end return at[a] < at[b] end)
  return out
end
function ui.AlongShown(g, i)
  return ns.Options().card.along and ui.AlongSteps(g, i) or {}
end
function ui.AlongObjective(s)
  if s.get then return nil end
  local own, ownK = nil, nil
  if s.kind == "O" and ns.StepObjective then own, ownK = ns.StepObjective(s) end
  if own then
    if not Plain(own.finished) then return own, s.ids[1], ownK end
    return nil
  end
  local objs, from = Objectives(s)
  for j, each in ipairs(objs) do
    if not Plain(each.finished) and Plain(each.text) then return each, from[j].id, from[j].k end
  end
  return nil
end
function ui.RowKeys(g, id, k, o)
  for _, t in ipairs(g and g.steps or {}) do
    local mobs = type(t.mobs) == "table" and #t.mobs > 0 and t.mobs
    if mobs and t.kind == "O" and t.ids and t.ids[1] == id and select(2, ns.StepObjective(t)) == k then return mobs end
    if mobs and t.kind == "S" and t.key == id then return mobs end
  end
  return { ns.ObjectiveThing(ns.PlainText and ns.PlainText(o.text) or Plain(o.text)) }
end
function ui.RowColours(g, s, along)
  local keys, at, lefts = {}, {}, {}
  local function add(id, k, o)
    local n = #keys + 1
    keys[n], at[n], lefts[n] = ui.RowKeys(g, id, k, o), id .. ":" .. k, ns.ObjectiveLeft(o)
  end
  if s then
    local objs, from = Objectives(s)
    for n, o in ipairs(objs) do add(from[n].id, from[n].k, o) end
  end
  for _, a in ipairs(along or {}) do
    local o, id, k = ui.AlongObjective(a)
    if o then add(id, k, o) end
  end
  local colours, changed = ns.RowColours(keys, lefts)
  local out = {}
  for n, where in ipairs(at) do out[where] = colours[n] end
  if changed and ui.Badges then ui.Badges() end
  return out
end
ui.ALONG_SHOWN = 4
ui.alongBox = Scroller(cardBody)
ui.alongBox:Hide()
ns.guideAlongBox = ui.alongBox
ui.alongShown = {}
ui.ALONG_TAG = UI.Colored(C.cyan, "Along the way")
local function AlongItems()
  if ui.AlongItems then ui.AlongItems() end
end
function ui.Along(steps, colours, place, width)
  for _, r in ipairs(ui.alongRows) do r:Hide(); r.badge:Hide(); r.bar:Hide() end
  ui.alongBox:Hide()
  ui.alongShown = {}
  if not place or not steps or #steps == 0 then return AlongItems() end
  local box, w = ui.alongBox, width or ui.BodyW()
  box:SetWidth(w)
  box.child:SetWidth(w)
  local y, seen = 0, 0
  for n, s in ipairs(steps) do
    local r = ui.alongRows[n]
    if not r then
      r = BadgeRow(box.child)
      r.bar = ObjBar(box.child)
      r.box:EnableMouse(true)
      r.box:SetScript("OnEnter", ui.QuestTip)
      r.box:SetScript("OnLeave", ui.QuestTipGone)
      r.box:SetScript("OnMouseUp", ui.QuestClicked)
      ui.alongRows[n] = r
    end
    local o, id, k = ui.AlongObjective(s)
    r.box.quest = id or s.ids[1]
    r.box.name = Plain(Call(C_QuestLog.GetTitleForQuestID, r.box.quest)) or s.name or s.text
    UI.Line.Icon(r, StepIcon(s))
    r:SetText((o and ns.ObjectiveTitle(o) or s.text) .. " " .. ui.ALONG_TAG)
    if o then ShowObjective(r.badge, r.bar, o, colours[id .. ":" .. k]) else r.badge:Hide() end
    r.box:ClearAllPoints()
    r.box:SetPoint("TOPLEFT", box.child, "TOPLEFT", 0, -y)
    r.box:SetWidth(w - 6)
    r:Show()
    UI.Line.Fit(r)
    if s.kind == "O" then ui.alongShown[#ui.alongShown + 1] = { s = s, row = r } end
    y = y + Height(r) + 2
    if o then
      r.bar:ClearAllPoints()
      r.bar:SetPoint("TOPLEFT", box.child, "TOPLEFT", 0, -y)
      r.bar:SetWidth(w - 6)
      r.bar:Show()
      y = y + 4 + 4
    else
      r.bar:Hide()
    end
    if n <= ui.ALONG_SHOWN then seen = y end
  end
  box:SetHeight(seen)
  box:Fit(y)
  place(box, seen, 0)
  AlongItems()
end

ui.choreRows, ui.CHORES_SHOWN, ui.LATER_W = {}, 3, 60
ns.guideChoreRows = ui.choreRows
function ui.ChoreRow(k)
  if ui.choreRows[k] then return ui.choreRows[k] end
  local r = { text = ui.Line(cardBody, "GameFontHighlightSmall", C.ivory), spells = {} }
  r.side = CreateFrame("Frame", nil, r.text.box)
  r.far = Text(r.side, "GameFontHighlightSmall", C.muted, "RIGHT")
  r.later = FlatButton(r.side, ns.Rules.Say("later"), ui.LATER_W, function(self)
    local g = ns.GuideInfo()
    for i, s in ipairs(g and g.steps or {}) do if s == self.step then return ns.Arbiter.Later(i) end end
  end)
  r.later:SetHeight(18)
  r.later:SetPoint("RIGHT", r.side, "RIGHT", 0, 0)
  UI.Line.Beside(r.text, r.side, "TOPRIGHT", 0)
  r.money = ui.Line(cardBody, "GameFontHighlightSmall", C.ivory)
  ui.choreRows[k] = r
  return r
end
function ui.ChoreSteps(g)
  local out = {}
  if not g or g.pasted then return out end
  for _, i in ipairs(g.choresDue or {}) do
    local s = g.steps[i]
    if s and i ~= g.cur and #out < ui.CHORES_SHOWN then out[#out + 1] = s end
  end
  return out
end
function ui.ChoresHere(g)
  local out = {}
  local continent, px, py = ns.PlayerWorldPos()
  if not px then return out end
  for _, s in ipairs(ui.ChoreSteps(g)) do
    if s.wx and s.inst == continent then
      local d = ns.Geo.Dist(s.wx, s.wy, px, py)
      if d <= ns.Arbiter.Reach("back") then out[#out + 1] = { s = s, d = d } end
    end
  end
  table.sort(out, function(a, b) return a.d < b.d end)
  return out
end
function ui.LeadYards(g, s)
  local t = ns.TrackTarget and ns.TrackTarget("e")
  if t and (t.guided or t.pasted) and t.along and g.cur == s.i then return t.along end
  local continent, px, py = ns.PlayerWorldPos()
  if px and s.wx and continent == s.inst then return ns.Geo.Dist(s.wx, s.wy, px, py) end
  return nil
end
function ui.CostText(s)
  if s.kind ~= "S" or not s.cost then return nil end
  local cost = ns.Word("both.chore.cost", { coins = Coins(s.cost) })
  local have = Plain(Call(GetMoney))
  if not have then return cost end
  return ns.Word("both.chore.money", { cost = cost, have = (have < s.cost and "|cffff1919" or "|cff19ff19")
    .. ns.Word("both.chore.have", { coins = Coins(have) }) .. "|r" })
end
function ui.Chores(g, lay, now)
  if not (g and lay) then
    for _, r in ipairs(ui.choreRows) do
      r.text:Hide()
      r.later:Hide()
      r.money:Hide()
      ui.Spells(nil, nil, r.spells)
    end
    ui.choreUsed = 0
    return
  end
  local continent, px, py = ns.PlayerWorldPos()
  local list, beside = {}, {}
  for _, c in ipairs(ui.ChoresHere(g)) do beside[c.s] = true end
  if now then
    for _, c in ipairs(ui.ChoresHere(g)) do list[#list + 1] = c.s end
  else
    for _, s in ipairs(ui.ChoreSteps(g)) do if not beside[s] then list[#list + 1] = s end end
  end
  for _, s in ipairs(list) do
    ui.choreUsed = (ui.choreUsed or 0) + 1
    local r = ui.ChoreRow(ui.choreUsed)
    local font = now and "GameFontNormalLarge" or "GameFontHighlightSmall"
    r.text:SetFontObject(font)
    r.text:SetTextColor(unpack(now and C.gold or C.ivory))
    UI.Line.Wrap(r.text, now)
    UI.Line.Icon(r.text, StepIcon(s))
    local title, spells = ui.Titled(s)
    if not now then title, spells = ns.StepLabel(s), nil end
    r.text:SetText(title)
    r.far:SetText((px and s.wx and s.inst == continent)
      and ns.Word("both.chore.far", { n = math.floor(ns.Geo.Dist(s.wx, s.wy, px, py)) }) or "")
    local key = now and (ui.LATER_W + UI.Line.KEY_GAP) or 0
    r.far:ClearAllPoints()
    r.far:SetPoint("RIGHT", r.side, "RIGHT", -key, 0)
    local line = ns.PlainNumber((select(2, Call(r.text.GetFont, r.text)))) or 12
    r.side:SetSize(math.ceil(ns.PlainNumber(Call(r.far.GetStringWidth, r.far)) or 0) + key, line)
    r.later.step = s
    r.later:SetShown(now and true or false)
    lay.Rule()
    local right = ui.BodyW() - lay.Width()
    lay.Place(r.text, 0, 0, nil, right)
    lay.y = lay.y + math.max(now and 18 or 12, Height(r.text)) + 2
    local cost = ui.CostText(s)
    local indent = r.text.iconArt and (UI.Line.ICON + UI.Line.ICON_GAP) or 0
    if cost then
      r.money:SetText(cost)
      lay.Place(r.money, nil, 2, indent, right)
    else
      r.money:Hide()
    end
    ui.Spells(spells, lay, r.spells, indent)
    lay.y = lay.y + 2
  end
end

function ui.LevelIn()
  local sec, _, level = ns.GuideLevelIn()
  if not sec then return "" end
  local m = math.floor(sec / 60 + 0.5)
  return string.format("Level %d in %s", level, m < 1 and "under a minute" or m < 60 and ("about " .. m .. " min")
    or string.format("about %d h %d min", math.floor(m / 60), m % 60))
end

function ui.Head(s, done, all)
  cardSub:SetText(s and string.format("%d of %d steps done", done, all) or "All done")
  local level = ui.LevelIn()
  ui.levelLine:SetText(level)
  cardTitle.box:SetPoint("TOPLEFT", ring, "TOPRIGHT", 8, level ~= "" and -2 or -8)
end

ui.carefulLine = Text(cardBody, "GameFontHighlightSmall", C.red)
ns.guideCareful = ui.carefulLine
function ui.Careful(s, place)
  if s and s.careful then
    local warn = ui.Icon(ui.WARN_ART)
    ui.carefulLine:SetText(warn .. (s.careful:gsub("; ", "\n" .. warn)))
    place(ui.carefulLine, nil, 3)
  else
    ui.carefulLine:Hide()
  end
end

ui.movesLine = Text(cardBody, "GameFontHighlightSmall", C.cyan)
ns.guideMoves = ui.movesLine
function ui.Moves(s, place)
  if s and s.mv then
    ui.movesLine:SetText(s.mv)
    place(ui.movesLine, nil, 3)
  else
    ui.movesLine:Hide()
  end
end

function ui.Said(s)
  local names, words = s.mobs and #s.mobs > 0 and s.mobs or { s.target }, {}
  for _, o in ipairs(Objectives(s)) do words[#words + 1] = Plain(o.text) or "" end
  local all = table.concat(words, "\n")
  for _, name in ipairs(names) do
    if not all:find(name, 1, true) then return false end
  end
  return #names > 0 and #words > 0
end


function ui.RenderHead(g, s, i)
  local done, all = g.done, g.all
  if not g.pasted then done, all = ns.GuideRunProgress() end
  SetRing(all > 0 and done / all or 0)
  cardTitle:SetText(g.name)
  ui.Head(s, done, all)
  local stage = ns.GuideStage(i or #g.steps)
  local fills = StageFills(g)
  local stageW = ui.StageW()
  stageRow:SetWidth(ui.BodyW())
  for k, part in ipairs(stageParts) do
    local f = fills[part.key] or 0
    part.part:SetSize(stageW, 16)
    part.part:SetPoint("TOPLEFT", (k - 1) * (stageW + 4), 0)
    part.fill:SetWidth(math.max(1, stageW * f))
    part.fill:SetShown(f > 0)
    part.label:SetTextColor(unpack(part.key == stage and C.gold or C.muted))
  end
end

function ui.RenderFace(g, s)
  local faceId = s and FaceOf(g, s)
  local painted = faceId and SetPortraitTextureFromCreatureDisplayID
    and (face.painted == faceId or pcall(SetPortraitTextureFromCreatureDisplayID, face.tex, faceId))
  face.painted = painted and faceId or nil
  face:SetShown(painted and true or false)
  return painted and FACE + 4 or 0
end

function ui.Layout(faceBottom)
  local lay = { y = 0, placed = false, due = false, rules = 0 }
  for _, r in ipairs(ui.rules) do r[1]:Hide(); r[2]:Hide() end
  function lay.Rule()
    if not lay.due then return end
    lay.due, lay.rules = false, lay.rules + 1
    ui.rules[lay.rules] = ui.rules[lay.rules] or ui.NewRule(cardBody)
    ui.PlaceRule(ui.rules[lay.rules], cardBody, lay.y + 3)
    lay.y = lay.y + 11
  end
  function lay.Part() if lay.placed then lay.due, lay.placed = true, false end end
  function lay.Width() return ui.BodyW() - (lay.y < faceBottom and FACE + 6 or 0) end
  function lay.Place(region, height, gap, x, right)
    lay.Rule()
    local at = region.box or region
    at:ClearAllPoints()
    at:SetPoint("TOPLEFT", cardBody, "TOPLEFT", x or 0, -lay.y)
    if region.SetWordWrap then
      at:SetPoint("RIGHT", cardBody, "RIGHT", -(right or (lay.y < faceBottom and FACE + 6 or 0)), 0)
    elseif region.spans then
      at:SetPoint("RIGHT", cardBody, "RIGHT", 0, 0)
    end
    region:Show()
    if region.box then UI.Line.Fit(region) end
    lay.placed = true
    lay.y = lay.y + (height or Height(region)) + (gap or 3)
  end
  function lay.Label(label)
    lay.Rule()
    label:ClearAllPoints()
    label:SetPoint("TOPLEFT", cardBody, "TOPLEFT", 0, -lay.y - 1)
    label:Show()
  end
  return lay
end

ui.KIND_GAP = 3
function ui.KindBefore(fs, lay, height, gap)
  local _, size = fs:GetFont()
  size = math.floor(tonumber(size) or 12)
  lay.Place(fs, height, gap, size + ui.KIND_GAP)
  parts.kind:SetSize(size, size)
  parts.kind:ClearAllPoints()
  parts.kind:SetPoint("TOPRIGHT", fs.box or fs, "TOPLEFT", -ui.KIND_GAP, 0)
  parts.kind:Show()
  parts.kindOn = fs
end

ui.PAGE_ART = "Interface\\Icons\\INV_Misc_Note_01"
ui.PAGE_SIZE, ui.TEXT_W, ui.TEXT_MOST_H = 16, 320, 420
parts.page = CreateFrame("Button", nil, cardBody)
parts.page:SetSize(ui.PAGE_SIZE, ui.PAGE_SIZE)
parts.page.art = parts.page:CreateTexture(nil, "ARTWORK")
parts.page.art:SetAllPoints()
parts.page.art:SetTexture(ui.PAGE_ART)
parts.page:SetHighlightTexture("Interface\\Buttons\\ButtonHilight-Square", "ADD")
function ui.QuestTip(self)
  if SetCursor then SetCursor(ui.HAND) end
  if not ui.HasQuestText(self.quest) then return end
  GameTooltip:SetOwner(self, "ANCHOR_RIGHT")
  local head = self ~= parts.page and ns.Word("game.card.quest", { quest = self.name }) or "Quest text"
  GameTooltip:AddLine(head, C.gold[1], C.gold[2], C.gold[3])
  GameTooltip:AddLine(ui.textBox and ui.textBox:IsShown() and ui.textBox.quest == self.quest
    and "Click to close the quest's text." or "Click to read the quest's full text.", C.muted[1], C.muted[2], C.muted[3], true)
  GameTooltip:Show()
end
function ui.QuestTipGone()
  if ResetCursor then ResetCursor() end
  GameTooltip:Hide()
end
function ui.QuestClicked(self)
  GameTooltip:Hide()
  ui.ToggleQuestText(self.quest, self.name)
  ui.SayQuestClicked(self.quest)
end
parts.page:SetScript("OnEnter", ui.QuestTip)
parts.page:SetScript("OnLeave", ui.QuestTipGone)
parts.page:SetScript("OnClick", ui.QuestClicked)
parts.page:Hide()

ui.CLICK_FRAME, ui.CLICK_COPIES, ui.CLICK_GAP = 45, 3, 0.1
ui.clicks = 0
function ui.SayQuestClicked(id)
  id = tonumber(id)
  if not (id and ns.StripLive and ns.StripLive()) then return end
  ui.clicks = ui.clicks % 255 + 1
  local w = ns.NewWriter()
  w:u8(ui.CLICK_FRAME); w:u24(id); w:u8(ui.clicks)
  ns.SendFrame(w.bytes, ui.CLICK_COPIES, ui.CLICK_GAP)
end

function ui.PlanText(id)
  local sh = IndexOfAzerothShared
  local qt = type(sh) == "table" and type(sh.epic) == "table" and type(sh.epic.qt) == "table" and sh.epic.qt or nil
  if not qt then return nil end
  if ui.planTextOf ~= qt then
    ui.planTextOf, ui.planTexts = qt, {}
    for _, q in ipairs(qt) do
      if type(q) == "table" and tonumber(q[1]) then ui.planTexts[tonumber(q[1])] = { text = q[2] or "", todo = q[3] or "" } end
    end
  end
  return ui.planTexts[id]
end

function ui.PlayerWords(text)
  local fill = { name = Plain(Call(UnitName, "player")), race = Plain(Call(UnitRace, "player")),
                 class = Plain(Call(UnitClass, "player")) }
  local female = Plain(Call(UnitSex, "player")) == 3
  text = text:gsub("<([%a ]+)/([%a ]+)>", function(he, she) return female and she or he end)
  return (text:gsub("<(%a+)>", function(k) return fill[k:lower()] or nil end))
end

function ui.HasQuestText(id)
  return id and (Plain(Call(C_QuestLog.GetLogIndexForQuestID, id)) ~= nil or ui.PlanText(id) ~= nil) or false
end

function ui.QuestText(id)
  local index = Plain(Call(C_QuestLog.GetLogIndexForQuestID, id))
  if index and ns.QuestLogText then
    local d, o = ns.QuestLogText(index, id)
    if d or o then
      local rows = {}
      for _, ob in ipairs(ns.QuestObjectives(id)) do
        local t = type(ob) == "table" and ns.PlainText(ob.text)
        if t and t ~= "" then rows[#rows + 1] = t end
      end
      return { todo = o or "", rows = rows, text = d or "", game = true }
    end
  end
  local mine = ui.PlanText(id)
  if not mine then return nil end
  return { todo = ui.PlayerWords(mine.todo), rows = {}, text = ui.PlayerWords(mine.text), game = false }
end

function ui.TextBox()
  if ui.textBox then return ui.textBox end
  local box = UI.Panel(CreateFrame("Frame", "IndexOfAzerothQuestText", UIParent, "BackdropTemplate"))
  ui.textBox, ns.guideTextBox = box, box
  box:SetFrameStrata("DIALOG")
  box:SetToplevel(true)
  box:SetClampedToScreen(true)
  box:EnableMouse(true)
  box:SetWidth(ui.TEXT_W)
  tinsert(UISpecialFrames, "IndexOfAzerothQuestText")
  box.title = Text(box, "GameFontNormal", C.gold)
  box.title:SetPoint("TOPLEFT", 10, -10)
  box.title:SetPoint("RIGHT", box, "RIGHT", -30, 0)
  box.close = FlatButton(box, "x", 18, function() box:Hide() end)
  box.close:SetSize(18, 18)
  box.close:SetPoint("TOPRIGHT", -6, -6)
  box.keys = CreateFrame("Frame", nil, box)
  box.keys:SetPoint("BOTTOMLEFT", 10, 10)
  box.keys:SetPoint("BOTTOMRIGHT", -8, 10)
  box.keys:SetHeight(0)
  box.scroll = Scroller(box)
  box.scroll:SetPoint("TOPLEFT", 10, -34)
  box.lines = {}
  for k, look in ipairs({ { "GameFontDisableSmall", C.muted }, { "GameFontHighlight", C.ivory },
                          { "GameFontHighlightSmall", C.ivory }, { "GameFontDisableSmall", C.muted },
                          { "GameFontHighlight", C.ivory }, { "GameFontDisableSmall", C.muted } }) do
    box.lines[k] = Text(box.scroll.child, look[1], look[2])
    box.lines[k]:SetWidth(ui.TEXT_W - 30)
  end
  box:SetScript("OnHide", function(self) self.quest = nil end)
  box:Hide()
  return box
end

function ui.ToggleQuestText(id, name)
  local box = ui.TextBox()
  if box:IsShown() and box.quest == id then return box:Hide() end
  local q = id and ui.QuestText(id)
  if not q then return box:Hide() end
  box.title:SetText((name or "") .. (q.game and "" or " |cff9d9d9d(not picked up yet)|r"))
  box.scroll.child:SetAlpha(q.game and 1 or 0.72)
  box.dimmed = not q.game
  local words = { q.todo ~= "" and "QUEST OBJECTIVES" or "", q.todo, table.concat(q.rows, "\n"),
                  q.text ~= "" and "DESCRIPTION" or "", q.text,
                  q.game and "The game's text from your quest log." or "This quest isn't in your log. The text comes from the Index's quest data." }
  local y = 0
  for k, fs in ipairs(box.lines) do
    fs:SetText(words[k])
    fs:ClearAllPoints()
    if words[k] ~= "" then
      fs:SetPoint("TOPLEFT", box.scroll.child, "TOPLEFT", 0, -y)
      fs:Show()
      y = y + Height(fs) + ((k == 1 or k == 4) and 3 or 10)
    else
      fs:Hide()
    end
  end
  local keys = tonumber(box.keys:GetHeight()) or 0
  box:SetHeight(math.min(ui.TEXT_MOST_H, y + 44 + keys))
  box.scroll:SetPoint("BOTTOMRIGHT", box, "BOTTOMRIGHT", -8, 10 + keys)
  box.scroll:Reset(y)
  box:ClearAllPoints()
  local x = card:GetCenter()
  local right = (tonumber(x) or 0) < (tonumber(UIParent:GetWidth()) or 0) / 2
  if right then box:SetPoint("TOPLEFT", card, "TOPRIGHT", 6, 0) else box:SetPoint("TOPRIGHT", card, "TOPLEFT", -6, 0) end
  box.quest = id
  box:Show()
end

function ui.KeepQuestText()
  local box = ui.textBox
  if not (box and box:IsShown()) then return end
  if parts.page:IsShown() and parts.page.quest == box.quest then return end
  for _, r in ipairs(ui.alongRows) do
    if r:IsShown() and r.box.quest == box.quest then return end
  end
  box:Hide()
end

function ui.Titled(s)
  local own = ns.StepLabel(s)
  local list = s.kind == "S" and s.what == "train" and type(s.spells) == "table" and s.spells or {}
  if #list == 1 and own:find(tostring(list[1].name), 1, true) then return own, {} end
  if #list > 1 and (s.npc or "") ~= "" then return ns.Word("both.chore.train", { npc = s.npc }), list end
  return own, list
end
ui.SPELLS_MOST, ui.spellRows = 8, {}
function ui.Spells(list, lay, rows, x)
  rows = rows or ui.spellRows
  list = list or {}
  local shown = math.min(#list, ui.SPELLS_MOST)
  for k = 1, math.max(shown + 1, #rows) do
    local text
    if k <= shown then
      local e = list[k]
      text = tostring(e.name) .. ((e.rank or "") ~= "" and (" (" .. e.rank .. ")") or "") .. ": " .. Coins(e.cost or 0)
    elseif k == shown + 1 and #list > shown then
      text = string.format("and %d more spells", #list - shown)
    end
    local row = rows[k]
    if text then
      row = row or Text(cardBody, "GameFontHighlightSmall", C.ivory)
      rows[k] = row
      row:SetText(text)
      lay.Place(row, nil, 1, x or 10)
    elseif row then
      row:Hide()
    end
  end
end

function ui.RenderStep(g, s, i, lay)
  parts.kind:SetTexture(StepIcon(s))
  parts.kind:Hide()
  parts.kindOn = nil
  local title, spells = ui.Titled(s)
  parts.name:SetText(s.kind == "S" and title or (s.name or s.text))
  local quest = (s.kind == "P" or s.kind == "O" or s.kind == "T") and s.ids[1] or nil
  if ui.HasQuestText(quest) then
    lay.Place(parts.name, nil, 2, ui.PAGE_SIZE + 4)
    parts.page.quest, parts.page.name = quest, s.name or s.text
    parts.page:ClearAllPoints()
    parts.page:SetPoint("TOPRIGHT", parts.name, "TOPLEFT", -4, 0)
    parts.page:Show()
  else
    lay.Place(parts.name, nil, 2)
    parts.page.quest = nil
    parts.page:Hide()
  end
  local who = WhoText(s)
  if s.kind == "O" and ui.Said(s) then who = nil end
  parts.who:SetText(who or "")
  if not who or who == "" then
    parts.who:Hide()
  elseif #Objectives(s) == 0 then
    ui.KindBefore(parts.who, lay, nil, 2)
  else
    lay.Place(parts.who, nil, 2)
  end
  local cost = ui.CostText(s)
  if cost then
    local _, size = parts.who:GetFont()
    parts.money:SetText(cost)
    lay.Place(parts.money, nil, 2, parts.kindOn == parts.who and (math.floor(tonumber(size) or 12) + ui.KIND_GAP) or 0)
  else
    parts.money:Hide()
  end
  ui.Spells(spells, lay)
  parts.where:SetText(WhereText(g, s))
  lay.Place(parts.where, nil, 3)
  ui.RenderEasy(g, s, i, lay)
  ui.Careful(s, lay.Place)
  ui.Moves(s, lay.Place)
  local why = ns.GuideWhyLine(g.state[i], g.why[i])
  local said = g.reason or (type(g.handIn) == "string" and g.handIn) or nil
  if said and i == g.cur then why = said end
  if not said and i == g.cur and g.handIn then why = nil end
  parts.why:SetText(why or "")
  parts.why:SetTextColor(unpack(g.state[i] == G.BLOCKED and C.red or g.state[i] == G.PARKED and C.cyan or C.yellow))
  if why then lay.Place(parts.why, nil, 3) else parts.why:Hide() end
  if s.group and g.state[i] ~= G.PARKED then
    parts.group = parts.group or Text(cardBody, "GameFontHighlightSmall", C.cyan)
    parts.group:SetText("This is a group quest. If you're on your own, park it and the guide comes back to the quest later.")
    lay.Place(parts.group, nil, 3)
  elseif parts.group then
    parts.group:Hide()
  end
  ui.TripLines(g, s, i, lay)
end

parts.trip = Text(cardBody, "GameFontHighlightSmall", C.cyan)
ns.guideTripLine = parts.trip
function ui.ClassIcon(size)
  local file = Plain(select(2, Call(UnitClass, "player")))
  local c = type(file) == "string" and type(CLASS_ICON_TCOORDS) == "table" and CLASS_ICON_TCOORDS[file]
  if type(c) ~= "table" then return "" end
  size = size or 14
  return string.format("|TInterface\\GLUES\\CHARACTERCREATE\\UI-CHARACTERCREATE-CLASSES:%d:%d:0:0:256:256:%d:%d:%d:%d|t ",
    size, size, c[1] * 256, c[2] * 256, c[3] * 256, c[4] * 256)
end
function ui.ClassLine(s)
  if not s.cq then return nil end
  return ui.ClassIcon() .. ns.Rules.Line("heads", "class_quest")
end
function ui.TripLines(g, s, i, lay)
  local lines = {}
  local class = ui.ClassLine(s)
  if class then lines[#lines + 1] = class end
  if s.why then lines[#lines + 1] = s.why end
  local h, saves = nil, nil
  if i == g.cur and ns.GuideHearth then h, saves = ns.GuideHearth(i) end
  if h then
    local n = math.max(1, math.floor(saves / 60 + 0.5))
    lines[#lines + 1] = ns.Rules.Say(n == 1 and "hearth_one" or "hearth", { town = h.town, n = n })
  end
  parts.trip:SetText(table.concat(lines, "\n"))
  if #lines > 0 then lay.Place(parts.trip, nil, 3) else parts.trip:Hide() end
end

function ui.RenderProgress(g, s, lay, colours)
  for k, b in ipairs(BossTrack(g, s) or {}) do
    lay.Rule()
    local r = BossRow(k)
    local color = b.down and C.muted or b.now and C.gold or C.ivory
    r.dot:SetColorTexture(color[1], color[2], color[3], 1)
    r.dot:ClearAllPoints()
    r.dot:SetPoint("TOPLEFT", cardBody, "TOPLEFT", 2, -lay.y - 4)
    r.dot:Show()
    r.name:SetText(b.name)
    r.name:SetTextColor(color[1], color[2], color[3])
    lay.Place(r.name, Height(r.name), 1, 14)
    if b.quests then
      r.quests:SetText(table.concat(b.quests, ", "))
      lay.Place(r.quests, Height(r.quests), 3, 14)
    end
  end
  local said = s.kind == "O" and ui.Said(s)
  local objs, from = Objectives(s)
  for k, o in ipairs(objs) do
    local r = ObjRow(k)
    local text = ns.ObjectiveTitle(o)
    r.text:SetText(said and RowText(s, text) or text)
    local finished = Plain(o.finished)
    r.text:SetTextColor(unpack(finished and C.muted or C.ivory))
    ShowObjective(r.left, r.bar, o, colours[from[k].id .. ":" .. from[k].k])
    if k == 1 then ui.KindBefore(r.text, lay, nil, 2) else lay.Place(r.text, nil, 2) end
    lay.Place(r.bar, 4, 4)
  end
  ui.BagSlots(s, lay)
  ui.Timers(lay.Place)
end

function ui.BagSlots(s, lay)
  if s.kind ~= "O" then return end
  local nums = ns.lastStatus and ns.lastStatus.nums
  local free, objs = nums and nums.bagFree, {}
  for _, o in ipairs(Objectives(s)) do
    objs[#objs + 1] = { item = Plain(o.type) == "item", have = Plain(o.numFulfilled) or 0, need = Plain(o.numRequired) or 0,
                        finished = Plain(o.finished) and true or false }
  end
  local want = ns.Rules.Slots(objs, free)
  if want == 0 then return end
  local r = ObjRow(#objs + 1)
  r.text:SetText(ns.Rules.Line("heads", want == 1 and "bag_slot" or "bag_slots", { n = want }))
  r.text:SetTextColor(unpack(C.ivory))
  SayBadge(r.left, string.format("%d left", want - free), C.red)
  lay.Place(r.text, nil, 2)
  r.bar:SetStatusBarColor(C.red[1], C.red[2], C.red[3], 1)
  r.bar:SetMinMaxValues(0, want)
  r.bar:SetValue(free)
  lay.Place(r.bar, 4, 4)
end

function ui.RenderParty(party, lay)
  if not party then
    parts.partyLabel:Hide(); parts.party:Hide(); parts.door:Hide()
    return
  end
  local chips = {}
  for _, m in ipairs(party.members) do
    chips[#chips + 1] = string.format("|cff%s%s|r %d/%d", CLASS_HEX[m.class] or "ffffff", m.name, m.on, m.of)
  end
  lay.Label(parts.partyLabel)
  parts.party:SetText(table.concat(chips, "   "))
  lay.Place(parts.party, Height(parts.party), 3, 44)
  local away = ns.GuideAtDoor and ns.GuideAtDoor()
  if away and #away > 0 then
    parts.door:SetText("You're at the door, waiting for " .. ns.AndList(away) .. ".")
    lay.Place(parts.door, Height(parts.door), 3)
  else
    parts.door:Hide()
  end
end

function ui.RenderNext(g, i, lay)
  local after = ThenText(g, i)
  if after == "" then
    parts.nextLabel:Hide(); parts.next:Hide()
    return
  end
  lay.Label(parts.nextLabel)
  parts.next:SetText(after)
  lay.Place(parts.next, Height(parts.next), 6, 36)
end

ui.noteRows, ui.noteMore, ui.noteOpen, ui.GRIND = {}, {}, {}, { 1, 0.70, 0.28 }
ui.LATER_MOST = 3
ns.guideNoteRows, ns.guideNoteMore, ns.guideNoteOpen = ui.noteRows, ui.noteMore, ui.noteOpen
ui.HAND = "Interface\\CURSOR\\OpenHand"
ui.PASTED = "This card comes from the line you pasted. A /reload loads the epic's whole plan, with Park, Skip and the party."
function ui.GrindText()
  local level, before, i, short = ns.GuideGrind()
  if not (level or short) then return nil end
  local s = ns.GuideInfo().steps[i]
  local after = s.text ~= "" and (" (then " .. s.text .. ")") or ""
  if not level then
    local line = ns.Word("both.wall.skill", short)
    return line, line .. after
  end
  local line = before == 0 and ns.Word("both.wall.level", { level = level })
    or string.format("Grind to %d in %d step%s", level, before, before == 1 and "" or "s")
  return line, string.format("Grind to level %d %s%s", level, before == 0 and "now, because the next quests open at that level"
    or string.format("after the next %d step%s", before, before == 1 and "" or "s"), after)
end
function ui.MissingText(g)
  local n, way, quests, names = #(g.missing or {}), 0, true, {}
  if n == 0 then return nil end
  for _, q in ipairs(g.missing) do
    local quest = type(q) ~= "table" and { name = q, kind = "thing" } or q
    if quest.onWay then way = way + 1 end
    if quest.kind and quest.kind ~= "quest" then quests = false end
    if quest.name then names[#names + 1] = tostring(quest.name) end
  end
  local them = n == 1 and "it" or "them"
  local what = quests and string.format("%d quest%s", n, n == 1 and "" or "s") or string.format("%d thing%s", n, n == 1 and "" or "s")
  return quests and "Some quests have no data yet" or "Some things have no data yet",
    string.format("Forever added %s, and the Index has no information yet on what opens %s. %s%s", what, them,
      way > 0 and string.format("The plan picks up %d of them on the way if a giver offers them. The rest are left out, "
        .. "and the addon takes one for you when a giver you talk to offers it.", way)
        or string.format("The plan leaves %s out, and the addon takes one for you when a giver you talk to offers it.", them),
      #names > 0 and " " .. (n == 1 and "It is " or "They are ") .. ns.AndList(names) .. "." or "")
end
function ui.LaterText(e)
  local text = tostring(type(e) == "table" and e.text or e)
  local what, wall = text:match("^(.-): (.+)$")
  if what then return "Later: " .. what, wall end
  return "Later: " .. text
end
local function NoteRow(k)
  local r = Text(cardBody, "GameFontHighlightSmall", C.ivory)
  local hit = CreateFrame("Frame", nil, cardBody)
  hit:EnableMouse(true)
  hit.line = hit:CreateTexture(nil, "ARTWORK")
  hit.line:SetHeight(1)
  hit.line:SetPoint("TOPLEFT", r, "BOTTOMLEFT", 0, -1)
  hit:SetScript("OnEnter", function(self)
    if SetCursor then SetCursor(ui.HAND) end
    GameTooltip:SetOwner(self, "ANCHOR_RIGHT")
    GameTooltip:AddLine(self.label, C.gold[1], C.gold[2], C.gold[3], true)
    GameTooltip:AddLine(self.detail, C.ivory[1], C.ivory[2], C.ivory[3], true)
    GameTooltip:AddLine(ui.noteOpen[self.key] and "Click to collapse it on the card." or "Click to open it on the card.",
      C.muted[1], C.muted[2], C.muted[3], true)
    GameTooltip:Show()
  end)
  hit:SetScript("OnLeave", function()
    if ResetCursor then ResetCursor() end
    GameTooltip:Hide()
  end)
  hit:SetScript("OnMouseUp", function(self)
    ui.noteOpen[self.key] = not ui.noteOpen[self.key] or nil
    GameTooltip:Hide()
    ui.Render()
  end)
  r.hit = hit
  ui.noteMore[k] = Text(cardBody, "GameFontHighlightSmall", C.ivory)
  return r
end
function ui.NoteLines(g, left)
  local lines = {}
  local function Add(words, color, detail, key) lines[#lines + 1] = { words, color, detail, key or words } end
  if left then ui.PlanNotes(g, Add) end
  local later = g.later or {}
  for k = 1, math.min(#later, ui.LATER_MOST) do
    local words, wall = ui.LaterText(later[k])
    Add(words, wall and C.cyan or C.muted, wall, "later:" .. k)
  end
  if #later > ui.LATER_MOST then Add(string.format("and %d more later, listed on the page", #later - ui.LATER_MOST), C.muted) end
  return lines
end
function ui.PlanNotes(g, Add)
  if g.pasted then Add("From the line you pasted", C.cyan, ui.PASTED, "pasted") end
  local grind, grindAll = ui.GrindText()
  if grind then Add(grind, ui.GRIND, grindAll, "grind") end
  local missing, missingAll = ui.MissingText(g)
  if missing then Add(missing, C.cyan, missingAll, "missing") end
  for k, note in ipairs(g.notes or {}) do
    local brief = g.brief and g.brief[k]
    local short = type(brief) == "string" and brief ~= "" and brief
    Add(short and "Not planned: " .. short or "Not planned yet: " .. tostring(note), short and C.cyan or C.muted,
      short and tostring(note) or nil, "note:" .. k)
  end
  for _, name in ipairs(g.hidden or {}) do Add("Hidden by you: " .. tostring(name), C.muted) end
  for _, note in ipairs(g.ownNotes or {}) do
    Add((note.hidden and "Hidden by you: " or "Not planned yet: ") .. tostring(note.text), C.muted)
  end
end
function ui.RenderNotes(g, lay, left)
  local lines = ui.NoteLines(g, left)
  for k = #lines + 1, #ui.noteRows do ui.noteRows[k]:Hide(); ui.noteRows[k].hit:Hide(); ui.noteMore[k]:Hide() end
  for k, line in ipairs(lines) do
    ui.noteRows[k] = ui.noteRows[k] or NoteRow(k)
    local r, more = ui.noteRows[k], ui.noteMore[k]
    r:SetText(line[1])
    r:SetTextColor(unpack(line[2]))
    local open = line[3] and ui.noteOpen[line[4]]
    lay.Place(r, nil, open and 2 or 3)
    if line[3] then
      local w = math.min(r:GetStringWidth() or 0, lay.Width())
      r.hit.label, r.hit.detail, r.hit.key = line[1], line[3], line[4]
      r.hit:ClearAllPoints()
      r.hit:SetPoint("TOPLEFT", r, "TOPLEFT")
      r.hit:SetSize(w, Height(r) + 2)
      r.hit.line:SetWidth(w)
      r.hit.line:SetColorTexture(line[2][1], line[2][2], line[2][3], 0.9)
      r.hit:Show()
    else
      r.hit:Hide()
    end
    more:SetText(open and line[3] or "")
    more:SetTextColor(unpack(C.ivory))
    if open then lay.Place(more, nil, 4, 10) else more:Hide() end
  end
end

ui.parked = CreateFrame("Frame", nil, cardBody)
ui.parked.text = Text(ui.parked, "GameFontHighlightSmall", C.cyan)
ui.parked.text:SetPoint("TOPLEFT")
ui.parked:EnableMouse(true)
ui.parked:SetScript("OnEnter", function(self)
  GameTooltip:SetOwner(self, "ANCHOR_RIGHT")
  GameTooltip:AddLine("Parked, still to do", C.gold[1], C.gold[2], C.gold[3])
  for _, q in ipairs(ns.GuideParked()) do
    GameTooltip:AddLine(q.name, C.ivory[1], C.ivory[2], C.ivory[3], true)
    if #q.holds > 0 then GameTooltip:AddLine("  This quest holds back " .. ns.AndList(q.holds) .. ".", C.muted[1], C.muted[2], C.muted[3], true) end
  end
  GameTooltip:AddLine("Click a quest's row in the Steps list to put that quest back in the guide now.", C.muted[1], C.muted[2], C.muted[3], true)
  GameTooltip:Show()
end)
ui.parked:SetScript("OnLeave", function() GameTooltip:Hide() end)
ns.guideParkedLine = ui.parked
function ui.RenderParked(lay)
  local n = #ns.GuideParked()
  if n == 0 then return ui.parked:Hide() end
  ui.parked.text:SetText("Parked: " .. n)
  ui.parked:SetSize(ui.BodyW(), 14)
  lay.Place(ui.parked, 14, 4)
end

function ui.RenderButtons(g, party, lay, i)
  local cur = not g.pasted and g.cur and g.steps[g.cur]
  local buttons = { stepsButton }
  if cur and cur.kind ~= "S" and g.state[g.cur] ~= G.PARKED then buttons[#buttons + 1] = parkButton end
  if cur and cur.kind == "S" and cur.key then buttons[#buttons + 1] = ui.skipButton end
  if cur and ns.Arbiter.MayPutOff(cur) and not ns.Arbiter.PutOffWhy(cur) then
    buttons[#buttons + 1] = ui.laterButton
  end
  local aside = ns.DirectorButton and ns.DirectorButton(cur, g, cardBody)
  if aside then buttons[#buttons + 1] = aside end
  if party and #party.share > 0 then
    shareButton.label:SetText(#party.share > 1 and ("Share " .. #party.share) or "Share")
    buttons[#buttons + 1] = shareButton
  end
  ui.lfgFor = ns.Lfg.Next(g, i)
  if ui.lfgFor then buttons[#buttons + 1] = ui.lfgButton end
  parkButton:Hide(); shareButton:Hide(); ui.skipButton:Hide(); ui.lfgButton:Hide(); ui.laterButton:Hide()
  for k, b in ipairs(buttons) do
    b:ClearAllPoints()
    b:SetPoint("TOPLEFT", cardBody, "TOPLEFT", (k - 1) * (#buttons > 3 and 70 or 94), -lay.y)
    b:SetWidth(#buttons > 3 and 66 or 88)
    b:Show()
  end
  stepsButton:SetSelected(listShown)
  lay.y = lay.y + ui.BUTTONS_H
end
ui.BUTTONS_H = 28

function ui.RenderList(g)
  local opening = listShown and not list:IsShown()
  list:SetShown(listShown)
  if not listShown then return end
  local level = Plain(Call(UnitLevel, "player")) or 0
  for k, st in ipairs(g.steps) do
    local r = ListRow(k)
    local state, here = g.state[k], k == g.cur
    local hold, color = ListHold(st, state, level)
    r.back:SetColorTexture(unpack(k % 2 == 0 and C.row or C.panel))
    if here or state == G.DONE then
      local tint = here and C.gold or C.green
      r.mark:SetTexture(here and LIST_ARROW or LIST_TICK)
      r.mark:SetVertexColor(tint[1], tint[2], tint[3])
      r.mark:Show()
    else
      r.mark:Hide()
    end
    r.icon:SetTexture(StepIcon(st))
    local tag = here and "You are here" or hold
    r.tag:SetText(tag and tag:upper() or "")
    local tc = here and C.gold or color
    r.tag:SetTextColor(tc[1], tc[2], tc[3])
    r.mark.word, r.tag.word = here and "here" or state == G.DONE and "done" or nil, tag
    r.parked = state == G.PARKED
    r.aside = not g.pasted and (state == G.WAIT or state == G.TODO) and ns.Drawer and ns.Drawer.CanBackground(st) or nil
    local why = state ~= G.SKIPPED and g.why[k]
    r.detail = (why or st.mv) and ((why and (why:sub(1, 1):upper() .. why:sub(2)) or "")
      .. (why and st.mv and "\n" or "") .. (st.mv or "")) or nil
    r.text:SetText(st.text .. (st.group and "  (group quest)" or ""))
    r.text:SetTextColor(color[1], color[2], color[3])
    r:Show()
  end
  for k = #g.steps + 1, #listRows do listRows[k]:Hide() end
  local pick = ui.asidePick and listRows[ui.asidePick]
  if not (pick and pick.aside) then ui.asidePick, pick = nil, nil end
  if ns.DirectorRowButton then ns.DirectorRowButton(pick, pick and g.steps[ui.asidePick]) end
  if opening then
    listScroll:Reset(#g.steps * LIST_ROW)
    listScroll:ScrollTo(((g.cur or 1) - 3) * LIST_ROW)
  else
    listScroll:Fit(#g.steps * LIST_ROW)
  end
end

function ui.Draw()
  local g = Epic()
  if not g or (g.pasted and g.hidden) or (not g.pasted and ns.GuideSaved().hiddenFor == g.version) then
    card:Hide(); toast:Hide(); list:Hide()
    return ui.Follow()
  end
  card:Show()
  ui.Follow()
  local s, i = Shown(g)
  ui.RenderHead(g, s, i)
  local along = s and ui.AlongShown(g, i) or {}
  local colours = ui.RowColours(g, s, along)
  ui.still = combatFolded and (not ns.Options or ns.Options().card.foldInCombat) and true or false
  local open = not folded and not ui.still
  local top = ui.Stages(g, open)
  cardBody:SetShown(open)
  ui.cardOpen = open
  if not open then
    card:SetHeight(HEAD_H + 2)
    list:Hide()
    return
  end
  local faceBottom = ui.RenderFace(g, s)
  local lay = ui.Layout(faceBottom)
  for _, r in ipairs(objRows) do r.text:Hide(); r.left:Hide(); r.bar:Hide() end
  for _, r in ipairs(bossRows) do r.dot:Hide(); r.name:Hide(); r.quests:Hide() end
  ui.Timers()
  ui.Careful()
  ui.Along()
  ui.Chores(g)
  ui.easyButton:Hide()
  local party = ns.GuideParty and ns.GuideParty()
  if ns.DirectorCardLine then ns.DirectorCardLine(lay, cardBody) end
  if not s then
    parts.kind:Hide(); parts.kindOn = nil; parts.page:Hide(); parts.who:Hide(); parts.money:Hide(); parts.where:Hide(); parts.why:Hide()
    if parts.group then parts.group:Hide() end
    for _, r in ipairs(ui.spellRows) do r:Hide() end
    parts.nextLabel:Hide(); parts.next:Hide(); parts.partyLabel:Hide(); parts.party:Hide(); parts.door:Hide()
    parts.name:SetText("All done")
    lay.Place(parts.name, nil, 6)
  else
    ui.RenderStep(g, s, i, lay)
    lay.Part()
    ui.RenderProgress(g, s, lay, colours)
    lay.Part()
    ui.Chores(g, lay, true)
    lay.Part()
    ui.Along(along, colours, lay.Place, lay.Width())
    lay.Part()
    ui.Chores(g, lay, false)
    lay.Part()
    ui.RenderParty(party, lay)
    lay.Part()
    ui.RenderNext(g, i, lay)
  end
  ui.KeepQuestText()
  lay.Part()
  ui.RenderNotes(g, lay, s ~= nil)
  ui.RenderParked(lay)
  lay.y = math.max(lay.y, faceBottom)
  local around = HEAD_H + 1 + top + ui.BUTTONS_H + 6
  size.shown = around + lay.y
  lay.y = math.max(lay.y, (size.h or 0) - around)
  ui.RenderButtons(g, party, lay, i)
  cardBody:SetHeight(lay.y)
  card:SetHeight(HEAD_H + 1 + top + lay.y + 6)
  ui.RenderList(g)
end
function ui.Render()
  card:SetWidth(size.w)
  cardBody:SetWidth(ui.BodyW())
  ui.Draw()
  for _, fs in ipairs(ui.lines) do UI.Line.Measure(fs) end
end
ns.CardRender = function() ui.Render() end

card:SetScript("OnHide", function() if ui.textBox then ui.textBox:Hide() end end)

local cardTick, cardFull = 0, 0
ns.OnTick(card, "the epic card", nil, function(_, dt)
  cardTick, cardFull = cardTick + dt, cardFull + dt
  for _, fs in ipairs(ui.lines) do UI.Line.Step(fs, dt, ui.still) end
  if toastLeft > 0 then
    toastLeft = toastLeft - dt
    toast:SetAlpha(math.max(0, math.min(1, toastLeft)))
    if toastLeft <= 0 then toast:Hide() end
  end
  if cardTick < 0.25 then return end
  cardTick = 0
  if cardFull >= 1 then cardFull = 0; return ui.Render() end
  local g = Epic()
  local s = g and Shown(g)
  if s and parts.where:IsShown() then parts.where:SetText(WhereText(g, s)) end
end)

ns.On({ "PLAYER_REGEN_DISABLED", "PLAYER_REGEN_ENABLED" }, function(event)
  combatFolded = event == "PLAYER_REGEN_DISABLED"
  ui.Render()
end)

local told = nil
ns.OnGuide(function(what, arg)
  local g = ns.GuideInfo()
  if what == "toast" then return Toast(arg) end
  if what == "done" and g and g.steps[arg] then
    local s = g.steps[arg]
    if s.kind == "O" then Toast("Done: " .. (s.name or s.text)) elseif s.kind == "D" then Toast((s.name or "the dungeon") .. " done") end
  end
  if what == "loaded" then
    local sv = ns.GuideSaved()
    if type(sv.scale) == "number" then
      sv.size = sv.scale > 1 and { w = math.min(WIDE_MOST, math.floor(CARD_W * sv.scale + 0.5)) } or nil
      if type(sv.pos) == "table" and tonumber(sv.pos[3]) and tonumber(sv.pos[4]) then
        sv.pos[3], sv.pos[4] = sv.pos[3] * sv.scale, sv.pos[4] * sv.scale
      end
      sv.scale = nil
    end
    local pos, kept = sv.pos, type(sv.size) == "table" and sv.size or {}
    size.w, size.h = CARD_W, nil
    CardSize(kept.w, kept.h)
    if type(pos) == "table" and pos[1] == "TOPLEFT" and not InCombatLockdown() then
      card:ClearAllPoints()
      card:SetPoint(pos[1], UIParent, pos[2] or pos[1], pos[3] or 0, pos[4] or 0)
    end
    if ui.PlaceCompass then ui.PlaceCompass() end
  end
  if ns.guideOther and told ~= ns.guideOther then
    told = ns.guideOther
    ns.Print("The quest epic in the Index's table belongs to " .. ns.guideOther .. ". Start a quest epic on the page for this character, then /reload.")
  end
  ui.Render()
end)

local toldHow = false
function ns.ToggleGuideCard(show, command)
  local sv = ns.GuideSaved()
  local g = ns.GuideInfo()
  local pasted = not g and ns.PastedGuide and ns.PastedGuide()
  if show == nil then show = not card:IsShown() end
  if pasted then pasted.hidden = not show else sv.hiddenFor = not show and g and g.version or nil end
  ns.epicDirty = true
  if command and (not show or g or pasted) then
    ns.Print(ns.SwitchWords(ns.Word("game.chat.switch.name.card"), show, "guide"))
  elseif not show and (g or pasted) and not toldHow then
    toldHow = true
    ns.Print("The quest epic's card is hidden. Click the blue arrow or the add-on button, or type /ioa guide, to bring the card back.")
  end
  if show and not (ns.GuideInfo() or pasted) then
    ns.Print("No quest epic is running. Start a quest epic on the page and /reload, or type /ioa guide start.")
  end
  ui.Render()
end

function ns.ResetGuideCard()
  if InCombatLockdown() then return ns.Print("The card's spot is reset after the fight, because the keys beside the card can't move during a fight.") end
  ns.GuideSaved().pos = nil
  card:ClearAllPoints()
  card:SetPoint("TOPRIGHT", UIParent, "TOPRIGHT", CARD_X, CARD_Y)
  if ns.PlaceGuideKeys then ns.PlaceGuideKeys() end
  ns.Print("The quest epic's card is back at its first spot.")
end

local side = { wins = {}, W = 240, HEAD = 30, PAD = 8, GAP = 8, LOWER = 110 }

function side.Kept(g)
  local sv = ns.GuideSaved()
  sv.sideWins = sv.sideWins or {}
  local k = tostring(g.line or g.key)
  sv.sideWins[k] = sv.sideWins[k] or {}
  return sv.sideWins[k]
end

function side.Window(slot)
  if side.wins[slot] then return side.wins[slot] end
  local w = Box(UIParent, C.bg, C.edge, "MEDIUM")
  w:SetSize(side.W, side.HEAD)
  w:SetMovable(true)
  w:SetClampedToScreen(true)
  w:EnableMouse(true)
  w:Hide()
  local head = CreateFrame("Frame", nil, w)
  head:SetPoint("TOPLEFT", 1, -1)
  head:SetPoint("TOPRIGHT", -1, -1)
  head:SetHeight(side.HEAD - 2)
  head:EnableMouse(true)
  head:RegisterForDrag("LeftButton")
  head:SetScript("OnDragStart", function() w:StartMoving() end)
  head:SetScript("OnDragStop", function()
    w:StopMovingOrSizing()
    local left, top = w:GetLeft(), w:GetTop()
    if not (left and top and w.g) then return end
    side.Kept(w.g).pos = { left, top }
    side.Place(w, 1)
  end)
  w.icon = head:CreateTexture(nil, "ARTWORK")
  w.icon:SetSize(20, 20)
  w.icon:SetPoint("LEFT", 6, 0)
  w.fold = FlatButton(head, "-", 20, function()
    if not w.g then return end
    local kept = side.Kept(w.g)
    kept.folded = not kept.folded or nil
    side.Render()
  end)
  w.fold:SetSize(20, 20)
  w.close = FlatButton(head, "x", 20, function() if w.g and ns.SideClose then ns.SideClose(w.g.slot) end end)
  w.close:SetSize(20, 20)
  w.close:SetPoint("RIGHT", -4, 0)
  w.fold:SetPoint("RIGHT", w.close, "LEFT", -4, 0)
  w.title = Text(head, "GameFontNormal", C.gold)
  w.title:SetPoint("LEFT", w.icon, "RIGHT", 6, 0)
  w.title:SetPoint("RIGHT", w.fold, "LEFT", -6, 0)
  w.head = head
  local wide = side.W - side.PAD * 2 - 22
  w.kind = w:CreateTexture(nil, "ARTWORK")
  w.kind:SetSize(16, 16)
  w.kind:SetPoint("TOPLEFT", head, "BOTTOMLEFT", side.PAD - 1, -4)
  w.step = Text(w, "GameFontHighlight", C.ivory)
  w.step:SetPoint("TOPLEFT", w.kind, "TOPRIGHT", 6, 1)
  w.step:SetWidth(wide)
  w.who = Text(w, "GameFontNormalSmall", C.muted)
  w.who:SetPoint("TOPLEFT", w.step, "BOTTOMLEFT", 0, -3)
  w.who:SetWidth(wide)
  w.why = Text(w, "GameFontNormalSmall", C.yellow)
  w.why:SetPoint("TOPLEFT", w.who, "BOTTOMLEFT", 0, -3)
  w.why:SetWidth(wide)
  ns.OnTick(w, "a profession epic's window", 0.5, function() side.Who(w) end)
  side.wins[slot] = w
  return w
end

function side.Place(w, i)
  local pos = side.Kept(w.g).pos
  w:ClearAllPoints()
  if type(pos) == "table" and tonumber(pos[1]) and tonumber(pos[2]) then
    return w:SetPoint("TOPLEFT", UIParent, "BOTTOMLEFT", pos[1], pos[2])
  end
  local x, down = card:GetCenter(), -(i - 1) * side.LOWER
  if x and x < UIParent:GetWidth() / 2 then w:SetPoint("TOPLEFT", card, "TOPRIGHT", side.GAP, down)
  else w:SetPoint("TOPRIGHT", card, "TOPLEFT", -side.GAP, down) end
end

function side.Who(w)
  local g = w.g
  local s = g and g.cur and g.steps[g.cur]
  if not s then return end
  local t = ns.TrackTarget(g.slot)
  local yards = t and t.along and string.format("%d yd", t.along)
  local who = WhoText(s)
  if who == "" then who = nil end
  w.who:SetText((who and yards) and (who .. "  |  " .. yards) or who or yards or "")
end

function side.Waiting(g)
  for k = 1, #g.steps do
    if g.state[k] == G.WAIT then return g.steps[k] end
  end
end

function side.Render()
  for _, w in pairs(side.wins) do w.g = nil end
  for i, g in ipairs(ns.SideGuides and ns.SideGuides() or {}) do
    local w = side.Window(g.slot)
    w.g = g
    local kept = side.Kept(g)
    local mark = g.look and UI.MARKS[g.look]
    w.icon:SetTexture(mark and mark.art or ICON)
    w.title:SetText((g.key:find("^craft:") and g.name) or g.prof or g.name)
    w.fold.label:SetText(kept.folded and "+" or "-")
    local open, s = not kept.folded, g.cur and g.steps[g.cur]
    local shown = s or side.Waiting(g)
    w.kind:SetShown(open and shown ~= nil)
    w.step:SetShown(open)
    w.who:SetShown(open and s ~= nil)
    w.why:SetShown(open)
    local headH = math.max(side.HEAD, (w.title:GetStringHeight() or 14) + 14)
    w.head:SetHeight(headH - 2)
    local high = headH
    if open then
      if shown then w.kind:SetTexture(StepIcon(shown)) end
      w.step:SetText(shown and (shown.name or shown.text) or ns.Word("game.card.side-done"))
      w.why:SetText(shown and ns.GuideWhyLine(g.state[shown.i], g.why[shown.i]) or "")
      side.Who(w)
      high = headH + 8 + (w.step:GetStringHeight() or 14) + (s and (w.who:GetStringHeight() or 0) + 3 or 0)
        + ((w.why:GetText() or "") ~= "" and (w.why:GetStringHeight() or 0) + 3 or 0) + side.PAD
    end
    w:SetHeight(high)
    side.Place(w, i)
    w:Show()
  end
  for _, w in pairs(side.wins) do if not w.g then w:Hide() end end
end
ns.SideWindowsRender = side.Render
ns.sideWindows = side.wins
function ns.SideWindowOpen(slot)
  for _, g in ipairs(ns.SideGuides and ns.SideGuides() or {}) do
    if g.slot == slot then side.Kept(g).folded = nil end
  end
  side.Render()
end

IndexOfAzerothGuideCard_Toggle = function() ns.ToggleGuideCard() end
BINDING_NAME_INDEXOFAZEROTH_GUIDE = "Show or hide the quest epic's card"
