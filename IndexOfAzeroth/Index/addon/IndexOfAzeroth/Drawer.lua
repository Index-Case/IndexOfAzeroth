-- The Index of Azeroth. Copyright 2026 Index Case <indexofazeroth@pm.me>. PolyForm Strict 1.0.0, see LICENSE.md.
local ADDON, ns = ...

local Plain, Call = ns.Plain, ns.Call
local Rules = ns.Rules
local UI = ns.UI
local C = UI.C

local W = { W = 250, PAD = 8, MOST_H = 320, SLIDE = 0.2, TAB_W = 14, TAB_H = 44, open = false, out = 0 }
ns.Drawer = W

local function Hex(c) return string.format("ff%02x%02x%02x", c[1] * 255, c[2] * 255, c[3] * 255) end


function W.Kept() return ns.Director.Saved().background end
function W.Background(id) return id ~= nil and W.Kept()[id] ~= nil end
function W.Rank(line)
  for _, s in ipairs(ns.SkillLines()) do
    if s.line == line then return s.rank, s.name end
  end
  return 0, nil
end
function W.Need(s)
  for _, o in ipairs(ns.QuestObjectives(s.ids[1])) do
    if o.skill ~= nil and o.skill == s.sk[1] then return o.numRequired end
  end
  return s.sk[2] or 1
end
function W.CanBackground(s)
  if not (s and s.sk and s.ids and s.ids[1]) or s.kind == "D" or s.kind == "S" or s.extra then return false end
  local id = s.ids[1]
  if W.Background(id) or Plain(Call(C_QuestLog.IsComplete, id)) then return false end
  for _, q in ipairs(ns.GuideParked()) do if q.id == id then return false end end
  return W.Rank(s.sk[1]) < W.Need(s)
end
local function Quiet(f, ...)
  local say = ns.Print
  ns.Print = function() end
  local ok, err = pcall(f, ...)
  ns.Print = say
  if not ok then ns.Report("the put-off menu", err) end
end
function W.SetAside(s)
  local id = s.ids[1]
  local rank, skill = W.Rank(s.sk[1])
  local need = W.Need(s)
  W.Kept()[id] = { line = s.sk[1], need = need, name = ns.Arbiter.Name(s), skill = skill or "skill" }
  local said = Rules.Line("lines", "background_said", { quest = ns.Arbiter.Name(s), skill = skill or "skill", need = need })
  local ok, err = pcall(ns.GuideParkQuest, id, said)
  if not ok then ns.Report("the put-off menu", err) end
  ns.MarkChanged("director")
  W.Render()
  return rank
end
function W.Check()
  local kept = W.Kept()
  for id, b in pairs(kept) do
    local inLog = Plain(Call(C_QuestLog.GetLogIndexForQuestID, id))
    local rank = W.Rank(b.line)
    if not inLog then
      kept[id] = nil
    elseif rank >= (b.need or 1) or Plain(Call(C_QuestLog.IsComplete, id)) then
      kept[id] = nil
      Quiet(ns.GuideUnparkQuest, id)
      ns.Print(Rules.Line("lines", "background_back", { quest = b.name or ("quest " .. id), skill = b.skill, need = b.need }))
      ns.MarkChanged("director")
    end
  end
end
function ns.DrawerBackground()
  local out = {}
  for id, b in pairs(W.Kept()) do out[#out + 1] = { quest = id, line = b.line, have = W.Rank(b.line), need = b.need or 1 } end
  table.sort(out, function(a, b) return a.quest < b.quest end)
  return out
end
local function BackgroundKey(parent)
  local b = UI.FlatButton(parent, Rules.Line("buttons", "background"), 88, function(self)
    if self.step then W.SetAside(self.step) end
  end)
  b:HookScript("OnEnter", function(self)
    GameTooltip:SetOwner(self, "ANCHOR_BOTTOM")
    GameTooltip:AddLine(Rules.Line("buttons", "background_tip"), 1, 1, 1, true)
    GameTooltip:Show()
  end)
  b:HookScript("OnLeave", function() GameTooltip:Hide() end)
  return b
end
W.button = nil
function ns.DirectorButton(cur, g, body)
  W.button = W.button or BackgroundKey(body)
  W.button:Hide()
  if not (cur and g and W.CanBackground(cur)) then return nil end
  W.button.step = cur
  return W.button
end
W.rowButton = nil
function ns.DirectorRowButton(row, s)
  if W.rowButton then W.rowButton:Hide(); W.rowButton.step = nil end
  if not (row and s and W.CanBackground(s)) then return nil end
  W.rowButton = W.rowButton or BackgroundKey(row:GetParent())
  local b = W.rowButton
  b.step = s
  b:ClearAllPoints()
  b:SetPoint("RIGHT", row, "RIGHT", -2, 0)
  b:SetSize(88, row:GetHeight())
  if b.SetFrameLevel and row.GetFrameLevel then b:SetFrameLevel((row:GetFrameLevel() or 1) + 2) end
  b:Show()
  return b
end
function ns.DrawerBackgroundQuest(id)
  if not id then return ns.Print("Type /ioa guide background <quest ID> to set a quest aside until its skill is up.") end
  local g = ns.GuideInfo()
  if not g then return ns.Print("No quest epic is running, so there's no quest to set aside.") end
  for _, s in ipairs(g.steps) do
    if s.ids and s.ids[1] == id and W.CanBackground(s) then return W.SetAside(s) end
  end
  ns.Print(string.format("Quest %d can't go in the background now. A quest goes there only while the epic's plan holds it, "
    .. "its skill is short and it isn't parked.", id))
end

function ns.TownAt(inst, wx, wy)
  return Rules.Town(type(IndexOfAzerothShared) == "table" and IndexOfAzerothShared.towns or nil, inst, wx, wy)
end


function W.Lines(g)
  local G, out = ns.GUIDE, {}
  if not g then return out end
  local function head(text) out[#out + 1] = { head = true, text = text } end
  local function row(text, back) out[#out + 1] = { text = text, back = back } end
  local byHead, order = {}, {}
  for i, s in ipairs(g.steps) do
    if g.state[i] ~= G.DONE and g.state[i] ~= G.SKIPPED and ns.Arbiter.PutOffWhy(s) then
      local key = ns.Arbiter.PutKey(s)
      local text = Rules.Back("heads", "drawer_later", ns.Arbiter.Where(s, ns.Arbiter.PutOff()[key]))
      if not byHead[text] then byHead[text] = {}; order[#order + 1] = text end
      table.insert(byHead[text], { ns.StepLabel(s), { kind = "later", key = key, s = s } })
    end
  end
  for _, text in ipairs(order) do
    head(text)
    for _, r in ipairs(byHead[text]) do row(r[1], r[2]) end
  end
  local parked = {}
  for _, q in ipairs(ns.GuideParked()) do if not W.Background(q.id) then parked[#parked + 1] = q end end
  if #parked > 0 then
    head(Rules.Line("heads", "drawer_parked"))
    for _, q in ipairs(parked) do row(q.name, { kind = "parked", id = q.id }) end
  end
  local bg = ns.DrawerBackground()
  if #bg > 0 then
    head(Rules.Line("heads", "drawer_background"))
    for _, b in ipairs(bg) do
      local k = W.Kept()[b.quest]
      row(Rules.Line("heads", "drawer_row_background", { quest = k.name or ("quest " .. b.quest), skill = k.skill,
                                                       have = b.have, need = b.need }), { kind = "background", id = b.quest })
    end
  end
  local short = {}
  for _, q in ipairs(type(g.skillShort) == "table" and g.skillShort or {}) do
    local have, name = W.Rank(q.line)
    if q.id and not W.Background(q.id) and Plain(Call(C_QuestLog.GetLogIndexForQuestID, q.id)) and have < (q.need or 1) then
      short[#short + 1] = Rules.Line("heads", "drawer_row_background", { quest = q.name or ("quest " .. q.id),
        skill = q.skill or name or "skill", have = have, need = q.need or 1 })
    end
  end
  if #short > 0 then
    head(Rules.Line("heads", "drawer_short"))
    for _, text in ipairs(short) do row(text, nil) end
  end
  local good, level = {}, {}
  local keep = ns.ChoreRules and ns.ChoreRules.KEEP or {}
  for i, s in ipairs(g.steps) do
    if s.kind == "S" and g.state[i] == G.SKIPPED then
      table.insert(keep[s.what] and good or level, { ns.StepLabel(s), { kind = "skipped", s = s } })
    end
  end
  if #good > 0 then head(Rules.Line("heads", "drawer_skipped")); for _, r in ipairs(good) do row(r[1], r[2]) end end
  if #level > 0 then head(Rules.Line("heads", "drawer_skipped_level")); for _, r in ipairs(level) do row(r[1], r[2]) end end
  return out
end
function W.Find(g, kind, a, b)
  if not (g and a) then return nil end
  local codes = ns.ChoresCodes and ns.ChoresCodes() or {}
  for _, l in ipairs(W.Lines(g)) do
    local back, s = l.back, l.back and l.back.s
    if back and ((kind == "quest" and back.id == a)
        or (kind == "step" and s and s.p == a)
        or (kind == "chore" and s and s.own and codes[s.what] == a and (s.npcID or 0) == (b or 0))) then
      return back
    end
  end
  return nil
end


local tab = CreateFrame("Button", nil, UIParent, "BackdropTemplate")
tab:SetSize(W.TAB_W, W.TAB_H)
UI.Skin(tab, C.bg, C.edge)
tab.arrow = tab:CreateTexture(nil, "ARTWORK")
tab.arrow:SetPoint("CENTER")
tab.arrow:SetSize(12, 12)
tab.arrow:SetTexture("Interface\\ChatFrame\\ChatFrameExpandArrow")
tab:Hide()
tab:SetScript("OnClick", function() W.open = not W.open; W.Render() end)
tab:SetScript("OnEnter", function(self)
  GameTooltip:SetOwner(self, "ANCHOR_TOP")
  GameTooltip:AddLine(Rules.Line("buttons", "drawer_tip"), 1, 1, 1, true)
  GameTooltip:Show()
end)
tab:SetScript("OnLeave", function() GameTooltip:Hide() end)
W.tab = tab

local box = UI.Box(UIParent, C.bg, C.edge, "MEDIUM")
box:SetWidth(W.W)
box:Hide()
box.scroll = UI.Scroller(box)
box.scroll:SetPoint("TOPLEFT", W.PAD, -W.PAD)
box.scroll:SetPoint("BOTTOMRIGHT", -W.PAD, W.PAD)
W.box = box

W.rows, W.KEY, W.HEAD_H, W.ROW_H = {}, 16, 16, 18
function W.Row(k)
  if W.rows[k] then return W.rows[k] end
  local child = box.scroll.child
  local r = { text = UI.Text(child, "GameFontHighlightSmall", C.ivory) }
  r.text:SetWordWrap(false)
  r.key = UI.FlatButton(child, "", W.KEY, function(self)
    if self.back then ns.Arbiter.PutBack(self.back) end
    W.Render()
  end)
  r.key:SetSize(W.KEY, W.KEY)
  r.key.arrow = r.key:CreateTexture(nil, "ARTWORK")
  r.key.arrow:SetPoint("CENTER")
  r.key.arrow:SetSize(10, 10)
  r.key.arrow:SetTexture("Interface\\ChatFrame\\ChatFrameExpandArrow")
  r.key:HookScript("OnEnter", function(self)
    local g = ns.GuideInfo()
    if not (g and self.back) then return end
    GameTooltip:SetOwner(self, "ANCHOR_TOP")
    GameTooltip:AddLine(ns.Arbiter.BackTip(g, self.back), 1, 1, 1, true)
    GameTooltip:Show()
  end)
  r.key:HookScript("OnLeave", function() GameTooltip:Hide() end)
  W.rows[k] = r
  return r
end
function W.Lay(lines, side)
  local child, width, y = box.scroll.child, W.W - 2 * W.PAD - 6, 0
  for _, r in ipairs(W.rows) do r.text:Hide(); r.key:Hide() end
  for n, l in ipairs(lines) do
    local r = W.Row(n)
    r.text:ClearAllPoints()
    if l.head then
      r.text:SetText(string.format("|c%s%s|r", Hex(C.gold), l.text))
      r.text:SetPoint("TOPLEFT", child, "TOPLEFT", 0, -y - 2)
      r.text:SetWidth(width)
      y = y + W.HEAD_H
    else
      r.text:SetText(l.text)
      r.key.back, r.key.toward = l.back, side == "right" and "left" or "right"
      r.key:ClearAllPoints()
      if side == "right" then
        r.key.arrow:SetTexCoord(1, 0, 0, 1)
        r.key:SetPoint("TOPLEFT", child, "TOPLEFT", 0, -y)
        r.text:SetPoint("TOPLEFT", child, "TOPLEFT", W.KEY + 4, -y - 2)
      else
        r.key.arrow:SetTexCoord(0, 1, 0, 1)
        r.key:SetPoint("TOPLEFT", child, "TOPLEFT", width - W.KEY, -y)
        r.text:SetPoint("TOPLEFT", child, "TOPLEFT", 8, -y - 2)
      end
      r.text:SetWidth(width - W.KEY - 8)
      if l.back then r.key:Show() end
      y = y + W.ROW_H
    end
    r.text:Show()
  end
  return y
end

function W.Side(card)
  local x = card and card:GetCenter()
  local w = UIParent:GetWidth()
  return (x and w and x < w / 2) and "right" or "left"
end
function W.Place()
  local card = ns.guideCard
  local side = W.Side(card)
  tab:ClearAllPoints()
  box:ClearAllPoints()
  local slid = (1 - W.out) * W.W
  if side == "right" then
    tab:SetPoint("TOPLEFT", card, "TOPRIGHT", -1, -12)
    tab.arrow:SetTexCoord(0, 1, 0, 1)
    box:SetPoint("TOPLEFT", card, "TOPRIGHT", W.TAB_W - 2 - slid, 0)
  else
    tab:SetPoint("TOPRIGHT", card, "TOPLEFT", 1, -12)
    tab.arrow:SetTexCoord(1, 0, 0, 1)
    box:SetPoint("TOPRIGHT", card, "TOPLEFT", -(W.TAB_W - 2) + slid, 0)
  end
  if card and card.GetFrameLevel then box:SetFrameLevel(math.max(0, (card:GetFrameLevel() or 1) - 1)) end
  box:SetAlpha(math.min(1, W.out * 1.5))
end
function W.Render()
  local card, g = ns.guideCard, ns.GuideInfo()
  local lines = (card and card:IsShown() and g) and W.Lines(g) or {}
  tab:SetShown(#lines > 0)
  if #lines == 0 then W.open = false end
  local y = W.Lay(lines, W.Side(card))
  box:SetHeight(math.min(W.MOST_H, y + 2 * W.PAD))
  box.scroll:Fit(y + 2)
  if W.open and not box:IsShown() then W.out = 0; box:Show() end
  if not W.open then box:Hide(); W.out = 0 end
  if #lines > 0 then W.Place() end
end
ns.OnTick(box, "the card's menu", nil, function(_, dt)
  if W.out >= 1 then return end
  W.out = math.min(1, W.out + dt / W.SLIDE)
  W.Place()
end)

if ns.OnGuide then ns.OnGuide(function() pcall(W.Render) end) end
ns.On({ "SKILL_LINES_CHANGED", "QUEST_LOG_UPDATE", "CHAT_MSG_SKILL" }, function() pcall(W.Check) end)
if C_Timer.NewTicker then C_Timer.NewTicker(1, function() pcall(W.Render) end) end
