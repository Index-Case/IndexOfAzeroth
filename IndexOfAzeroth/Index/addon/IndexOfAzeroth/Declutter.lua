-- The Index of Azeroth. Copyright 2026 Index Case <indexofazeroth@pm.me>. PolyForm Strict 1.0.0, see LICENSE.md.
local ADDON, ns = ...
local Plain, Call, Word = ns.Plain, ns.Call, ns.Word

local D = {}
ns.Declutter = D

local KINDS = { gray = "trivial", green = "standard" }
local function Colour(level, id)
  local colours = QuestDifficultyColors
  if type(colours) ~= "table" or type(level) ~= "number" or level <= 0 then return nil end
  local c = Call(GetQuestDifficultyColor, level, false, id)
  if c == nil then return nil end
  for colour, kind in pairs(KINDS) do
    if c == colours[kind] then return colour, c end
  end
end

function D.Shade(colour)
  local c = type(QuestDifficultyColors) == "table" and QuestDifficultyColors[KINDS[colour]]
  if type(c) == "table" and c.r then return { c.r, c.g, c.b } end
  return colour == "gray" and ns.UI.C.muted or ns.UI.C.green
end

function D.Zones()
  local out, byName, zone = {}, {}, nil
  for i = 1, Plain(Call(C_QuestLog.GetNumQuestLogEntries)) or 0 do
    local info = Call(C_QuestLog.GetInfo, i)
    if type(info) == "table" and Plain(info.isHeader) then
      zone = Plain(info.title)
    elseif type(info) == "table" and zone and not Plain(info.isHidden) and Plain(info.questID) then
      local id, level = info.questID, Plain(info.level)
      local colour, c = Colour(level, id)
      if colour and Plain(Call(C_QuestLog.CanAbandonQuest, id)) ~= false then
        local z = byName[zone]
        if not z then
          z = { name = zone, gray = {}, green = {} }
          byName[zone] = z
          out[#out + 1] = z
        end
        table.insert(z[colour], { id = id, title = Plain(info.title) or "", level = level, colour = { c.r, c.g, c.b } })
      end
    end
  end
  return out
end

local ticks = {}
function D.Ticks(zone)
  ticks[zone] = ticks[zone] or {}
  return ticks[zone]
end
function D.Untick() ticks = {} end

local changed = {}
function D.OnChange(fn) changed[#changed + 1] = fn end

local function Rewards(id)
  local was = Plain(Call(C_QuestLog.GetSelectedQuest))
  Call(C_QuestLog.SetSelectedQuest, id)
  local r = { money = Plain(Call(GetQuestLogRewardMoney, id)) or 0, items = {} }
  local function Add(kind, n, Info)
    for i = 1, n do
      local _, icon, count, _, _, item = Call(Info, i, id)
      icon, count, item = Plain(icon), Plain(count), Plain(item)
      if icon or item then
        r.items[#r.items + 1] = { icon = icon, count = count or 1, item = item, link = Plain(Call(GetQuestLogItemLink, kind, i, id)) }
      end
    end
  end
  Add("reward", Plain(Call(GetNumQuestLogRewards, id)) or 0, GetQuestLogRewardInfo)
  Add("choice", Plain(Call(GetNumQuestLogChoices, id)) or 0, GetQuestLogChoiceInfo)
  if was ~= id then Call(C_QuestLog.SetSelectedQuest, was or 0) end
  return r
end

local function Abandon(id)
  local was = Plain(Call(C_QuestLog.GetSelectedQuest))
  Call(C_QuestLog.SetSelectedQuest, id)
  Call(C_QuestLog.SetAbandonQuest)
  Call(C_QuestLog.AbandonQuest)
  if was and was ~= id then Call(C_QuestLog.SetSelectedQuest, was) end
end

local oneAClick, turnedAway = false, false
ns.On({ "ADDON_ACTION_BLOCKED", "ADDON_ACTION_FORBIDDEN" }, function(_, addon, fn)
  if addon == ADDON and tostring(fn):find("AbandonQuest", 1, true) then oneAClick, turnedAway = true, true end
end)

local W, H, HEAD_H, ROW_H, ICON = 480, 460, 34, 42, 18
local SENT_WAIT = 1
local win, review = nil, nil

local Draw
local function Build()
  local ui = ns.UI
  local C = ui.C
  win = ui.Panel(CreateFrame("Frame", "IndexOfAzerothDeclutter", UIParent, "BackdropTemplate"))
  win:SetFrameStrata("DIALOG")
  win:SetToplevel(true)
  win:SetSize(W, H)
  win:SetPoint("CENTER", UIParent, "CENTER", 40, 40)
  win:SetMovable(true)
  win:SetClampedToScreen(true)
  win:EnableMouse(true)
  win:Hide()
  win:SetScript("OnHide", function() review = nil end)
  tinsert(UISpecialFrames, "IndexOfAzerothDeclutter")
  local head = CreateFrame("Frame", nil, win)
  head:SetPoint("TOPLEFT")
  head:SetPoint("TOPRIGHT")
  head:SetHeight(HEAD_H)
  head:EnableMouse(true)
  head:RegisterForDrag("LeftButton")
  head:SetScript("OnDragStart", function() win:StartMoving() end)
  head:SetScript("OnDragStop", function() win:StopMovingOrSizing() end)
  win.title = ui.Text(head, "GameFontHighlightLarge", C.ivory)
  win.title:SetPoint("LEFT", 12, 0)
  win.title:SetPoint("RIGHT", -34, 0)
  local close = ui.FlatButton(head, "x", 20, function() win:Hide() end)
  close:SetSize(20, 20)
  close:SetPoint("TOPRIGHT", -6, -6)
  local help = ui.Text(win, "GameFontHighlightSmall", C.muted)
  help:SetPoint("TOPLEFT", 12, -HEAD_H - 2)
  help:SetWidth(W - 24)
  help:SetText(Word("game.declutter.help"))
  win.list = ui.Scroller(win)
  win.list:SetPoint("TOPLEFT", 12, -HEAD_H - 36)
  win.list:SetPoint("BOTTOMRIGHT", -12, 92)
  win.rows = {}
  win.line = ui.Text(win, "GameFontHighlightSmall", C.ivory)
  win.line:SetPoint("BOTTOMLEFT", 12, 62)
  win.line:SetWidth(W - 24)
  win.typed = ui.Skin(CreateFrame("EditBox", nil, win, "BackdropTemplate"), C.row, C.edge)
  win.typed:SetSize(160, 22)
  win.typed:SetPoint("BOTTOMLEFT", 12, 14)
  win.typed:SetFontObject(ChatFontNormal)
  win.typed:SetTextInsets(6, 6, 0, 0)
  win.typed:SetAutoFocus(false)
  win.typed:SetScript("OnEscapePressed", function() win:Hide() end)
  win.typed:SetScript("OnTextChanged", function() Draw() end)
  win.typed:SetScript("OnEnterPressed", function() D.Click() end)
  win.key = ui.FlatButton(win, Word("game.declutter.abandon"), 120, function() D.Click() end)
  win.key:SetPoint("BOTTOMRIGHT", -12, 12)
end

local function ItemIcon(parent)
  local b = CreateFrame("Button", nil, parent)
  b:SetSize(ICON, ICON)
  b.icon = b:CreateTexture(nil, "ARTWORK")
  b.icon:SetAllPoints()
  b.count = ns.UI.Text(b, "NumberFontNormalSmall", ns.UI.C.ivory, "RIGHT")
  b.count:SetPoint("BOTTOMRIGHT", 2, -2)
  b:SetScript("OnEnter", function(self)
    GameTooltip:SetOwner(self, "ANCHOR_RIGHT")
    if self.link then GameTooltip:SetHyperlink(self.link) elseif self.item then GameTooltip:SetItemByID(self.item) end
    GameTooltip:Show()
  end)
  b:SetScript("OnLeave", function() GameTooltip:Hide() end)
  return b
end

local function Row(i)
  local ui = ns.UI
  local r = CreateFrame("Frame", nil, win.list.child)
  r:SetSize(W - 30, ROW_H)
  r:SetPoint("TOPLEFT", 0, -(i - 1) * ROW_H)
  r.box = ui.TickBox(r)
  r.box:SetPoint("TOPLEFT", 2, -3)
  r.box:SetScript("OnClick", function()
    if r.quest then r.quest.ticked = not r.quest.ticked; Draw() end
  end)
  r.box:SetScript("OnEnter", function(self) self:Lit(true) end)
  r.box:SetScript("OnLeave", function(self) self:Lit(false) end)
  r.name = ui.Text(r, "GameFontHighlight")
  r.name:SetPoint("TOPLEFT", 24, -2)
  r.name:SetWidth(W - 60)
  r.name:SetWordWrap(false)
  r.money = ui.Text(r, "GameFontHighlightSmall", ui.C.ivory)
  r.money:SetPoint("TOPLEFT", 24, -20)
  r.icons = {}
  win.rows[i] = r
  return r
end

Draw = function()
  if not (win and review) then return end
  local ui = ns.UI
  local shown = 0
  for _, q in ipairs(review.quests) do
    if not q.gone then
      shown = shown + 1
      local r = win.rows[shown] or Row(shown)
      r.quest = q
      r.box:SetTicked(q.ticked)
      r.name:SetText(Word("game.declutter.quest", { level = q.level, quest = q.title }))
      r.name:SetTextColor(q.colour[1], q.colour[2], q.colour[3])
      local rw = q.rewards
      r.money:SetText(rw.money > 0 and ns.Coins(rw.money) or (#rw.items == 0 and ui.Colored(ui.C.muted, Word("game.declutter.no-reward")) or ""))
      r.money:Show()
      local x = rw.money > 0 and (r.money:GetStringWidth() or 0) + 32 or 24
      for k, it in ipairs(rw.items) do
        local b = r.icons[k] or ItemIcon(r)
        r.icons[k] = b
        b.link, b.item = it.link, it.item
        b.icon:SetTexture(it.icon or 134400)
        b.count:SetText(it.count > 1 and it.count or "")
        b:ClearAllPoints()
        b:SetPoint("TOPLEFT", x + (k - 1) * (ICON + 4), -19)
        b:Show()
      end
      for k = #rw.items + 1, #r.icons do r.icons[k]:Hide() end
      r:Show()
    end
  end
  for k = shown + 1, #win.rows do win.rows[k]:Hide(); win.rows[k].quest = nil end
  win.list:Fit(shown * ROW_H)
  local ticked, word = 0, Word("game.declutter.word")
  for _, q in ipairs(review.quests) do if q.ticked and not q.gone and not q.sent then ticked = ticked + 1 end end
  local ready
  if review.sure then
    win.typed:Hide()
    win.line:SetText(review.clicked and ticked > 0 and ns.Count("game.declutter.left", ticked) or "")
    ready = ticked > 0
  else
    win.typed:Show()
    win.line:SetText(ns.Count("game.declutter.type", ticked, { word = word }))
    ready = ticked > 0 and strtrim(win.typed:GetText() or "") == word
  end
  win.key.off = not ready
  win.key:SetEnabled(ready)
  win.key:SetAlpha(ready and 1 or 0.5)
end

function D.Click()
  if not (win and review) or win.key.off then return end
  review.sure, review.clicked = true, true
  for _, q in ipairs(review.quests) do
    if q.ticked and not q.gone and not q.sent then
      turnedAway = false
      Abandon(q.id)
      if turnedAway then break end
      q.sent = GetTime()
      if oneAClick then break end
    end
  end
  Draw()
end

function D.Review(zone, colours)
  if not win then Build() end
  local quests = {}
  for _, z in ipairs(D.Zones()) do
    if z.name == zone then
      for _, colour in ipairs({ "gray", "green" }) do
        if colours[colour] then
          for _, q in ipairs(z[colour]) do
            q.ticked, q.rewards = true, Rewards(q.id)
            quests[#quests + 1] = q
          end
        end
      end
    end
  end
  if #quests == 0 then return win:Hide() end
  table.sort(quests, function(a, b) if a.level ~= b.level then return a.level < b.level end return a.title < b.title end)
  win:Hide()
  review = { zone = zone, quests = quests }
  win.title:SetText(Word("game.declutter.title", { zone = zone }))
  win.typed:SetText("")
  win:Show()
  win.list:Reset(#quests * ROW_H)
  Draw()
end
ns.declutterWindow = function() return win, review end

ns.On({ "QUEST_LOG_UPDATE", "QUEST_REMOVED" }, function(event, id)
  if review then
    local now = GetTime()
    for _, q in ipairs(review.quests) do
      if (event == "QUEST_REMOVED" and q.id == id) or not Plain(Call(C_QuestLog.GetLogIndexForQuestID, q.id)) then
        q.gone = true
      elseif q.sent and now - q.sent >= SENT_WAIT then
        q.sent = nil
      end
    end
    local any = false
    for _, q in ipairs(review.quests) do any = any or (q.ticked and not q.gone) end
    if not any then win:Hide() else Draw() end
  end
  for _, fn in ipairs(changed) do pcall(fn) end
end)
