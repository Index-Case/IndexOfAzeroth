-- The Index of Azeroth. Copyright 2026 Index Case <indexofazeroth@pm.me>. PolyForm Strict 1.0.0, see LICENSE.md.
local ADDON, ns = ...

local UI = ns.UI
local WHITE, C, Box, Text = UI.WHITE, UI.C, UI.Box, UI.Text
local Plain, Call = ns.Plain, ns.Call
local ui, card = ns.guideUI, ns.guideCard
local CARD_W, CARD_X, CARD_Y = ui.CARD_W, ui.CARD_X, ui.CARD_Y

local KEY_SIZE = 28
local function SecureButton(name, kind, icon)
  local b = CreateFrame("Button", name, UIParent, "SecureActionButtonTemplate")
  b:SetSize(KEY_SIZE, KEY_SIZE)
  b:RegisterForClicks("AnyUp", "AnyDown")
  b:SetAttribute("useOnKeyDown", false)
  b:SetAttribute("type", kind)
  b:SetAttribute("ctrl-type1", "setkey")
  b.bindName = name
  b.icon = b:CreateTexture(nil, "ARTWORK")
  b.icon:SetAllPoints()
  b.icon:SetTexture(icon)
  b.keyText = b:CreateFontString(nil, "OVERLAY", "NumberFontNormalSmallGray")
  b.keyText:SetPoint("TOPRIGHT", -1, -2)
  b.edge = b:CreateTexture(nil, "OVERLAY")
  b.edge:SetPoint("TOPLEFT", -1, 1)
  b.edge:SetPoint("BOTTOMRIGHT", 1, -1)
  b.edge:SetColorTexture(C.edge[1], C.edge[2], C.edge[3], 0.9)
  b.edge:SetDrawLayer("BACKGROUND")
  b:Hide()
  return b
end
local targetButton = SecureButton("IndexOfAzerothGuideTarget", "macro", "Interface\\Icons\\Ability_Hunter_SniperShot")
targetButton:SetPoint("TOPRIGHT", UIParent, "TOPRIGHT", CARD_X - CARD_W - 4, CARD_Y)
targetButton.anchor, targetButton.below = card, 0
targetButton.baseStrata, targetButton.baseLevel = targetButton:GetFrameStrata(), targetButton:GetFrameLevel()
targetButton.awayOn = false
ui.targetWants, ui.TARGET_OWNERS = {}, { "find", "travel", "epic", "loop" }
local function KeyOptions() return ns.Options().targetKey end
function ui.KeyHere()
  local _, kind = Call(IsInInstance)
  kind = Plain(kind)
  if kind == "party" or kind == "raid" then return KeyOptions().dungeons end
  return KeyOptions().world
end
function ui.TargetNow()
  if not ui.KeyHere() then return nil end
  local flights = KeyOptions().flights
  for _, owner in ipairs(ui.TARGET_OWNERS) do
    local want = ui.targetWants[owner]
    if want and want.who and (flights or not want.flight) then return want, owner end
  end
end
local KEY_BUTTON = "Keybind"
local function KeyAction(b) return "CLICK " .. b.bindName .. ":" .. KEY_BUTTON end
local function KeyLine(b)
  local key = Call(GetBindingKey, KeyAction(b))
  GameTooltip:AddLine("Ctrl+click: set this button's key" .. (key and (" (now " .. key .. ")") or ""), C.muted[1], C.muted[2], C.muted[3])
end
targetButton:SetScript("OnEnter", function(self)
  GameTooltip:SetOwner(self, "ANCHOR_LEFT")
  GameTooltip:AddLine("Target " .. (self.who or "the step's NPC"))
  GameTooltip:AddLine(self.want and self.want.tip
    or ("Press this to target your objective, once in range and targeted, it will activate the target and "
        .. "accept any quest you might have that they offer. So if someone wanted to they could press it again, "
        .. "and again... and again, over and over ;)"), C.muted[1], C.muted[2], C.muted[3], true)
  if self.want and self.want.item then
    GameTooltip:AddLine(self.want.friendly
      and "Each press takes the next one not yet given the step's quest item and uses the item on them."
      or "Once the right target is picked, a press also uses the step's quest item on the target.", C.muted[1], C.muted[2], C.muted[3], true)
  end
  KeyLine(self)
  if ui.TargetSpellLine then ui.TargetSpellLine() end
  if ui.TargetTipWho then ui.TargetTipWho(self) end
  GameTooltip:Show()
end)
targetButton:SetScript("OnLeave", function() GameTooltip:Hide() end)
local itemButton = SecureButton("IndexOfAzerothGuideItem", "item", 134400)
itemButton:SetPoint("TOPRIGHT", UIParent, "TOPRIGHT", CARD_X - CARD_W - 4, CARD_Y)
itemButton.anchor, itemButton.below = card, 0
itemButton:SetScript("OnEnter", function(self)
  if not self.link then return end
  GameTooltip:SetOwner(self, self.onRight and not self.along and "ANCHOR_RIGHT" or "ANCHOR_LEFT")
  GameTooltip:SetHyperlink(self.link)
  KeyLine(self)
  GameTooltip:Show()
end)
itemButton:SetScript("OnLeave", function() GameTooltip:Hide() end)

local find = {}
local SLIDE_SECONDS, SLIDE_GAP = 0.25, 10
local function CCButton() return _G.IndexOfAzerothButton end
targetButton.plate = targetButton:CreateTexture(nil, "BACKGROUND", nil, 1)
targetButton.plate:SetPoint("TOPLEFT", 1, -1)
targetButton.plate:SetPoint("BOTTOMRIGHT", -1, 1)
targetButton.plate:SetColorTexture(C.bg[1], C.bg[2], C.bg[3], 1)
targetButton.plate:Hide()
local away = CreateFrame("Button", nil, targetButton)
away:SetSize(16, 16)
away.text = away:CreateFontString(nil, "OVERLAY", "GameFontNormal")
away.text:SetAllPoints()
away.text:SetText("x")
away.text:SetTextColor(0.8, 0.8, 0.8)
away:SetScript("OnEnter", function(self) self.text:SetTextColor(C.gold[1], C.gold[2], C.gold[3]) end)
away:SetScript("OnLeave", function(self) self.text:SetTextColor(0.8, 0.8, 0.8) end)
away:Hide()
targetButton.away = away

local function Look(b, beside, away)
  b.size = beside and (beside:GetWidth() or KEY_SIZE) or KEY_SIZE
  b:SetSize(b.size, b.size)
  b.edge:ClearAllPoints()
  b.icon:ClearAllPoints()
  if beside then
    b.edge:SetAllPoints()
    b.icon:SetPoint("TOPLEFT", 3, -3)
    b.icon:SetPoint("BOTTOMRIGHT", -3, 3)
  else
    b.edge:SetPoint("TOPLEFT", -1, 1)
    b.edge:SetPoint("BOTTOMRIGHT", 1, -1)
    b.icon:SetAllPoints()
  end
  b.awayOn = beside ~= nil and away or false
  b.plate:SetShown(beside ~= nil)
  b.away:SetShown(b.awayOn)
  b:SetAttribute("type2", b.awayOn and "putaway" or nil)
  b:SetFrameStrata(beside and beside:GetFrameStrata() or b.baseStrata)
  b:SetFrameLevel(beside and math.max(1, beside:GetFrameLevel() - 1) or b.baseLevel)
  b.away:SetFrameLevel(b:GetFrameLevel() + 3)
  b.placedX, b.side = nil, nil
end

local function BesideSpot(b, on, screen)
  local left, right, top, scale = on:GetLeft(), on:GetRight(), on:GetTop(), on:GetEffectiveScale()
  if not (left and right and top and scale and screen) then return end
  local l, r = left * scale / screen, right * scale / screen
  local out = l - SLIDE_GAP - b.size >= 0 and l - SLIDE_GAP or r + SLIDE_GAP + b.size
  return out, top * scale / screen, r, out > r
end
local function Slid(now)
  local s = find.slide
  if not s then return 1, true end
  local p = math.min(1, math.max(0, (now - s.at) / SLIDE_SECONDS))
  local e = 1 - (1 - p) ^ 3
  return s.out and e or 1 - e, p >= 1
end

local ITEM_GAP = 4
local function ItemSpot(b, screen)
  local on = b.anchor
  local left, top, scale = on:GetLeft(), on:GetTop(), on:GetEffectiveScale()
  if not (left and top and scale and screen) then return end
  local k, size = scale / screen, b.size or KEY_SIZE
  local y = (top - ui.faceDrop - ui.FACE / 2) * k + size / 2
  local x = (left + on:GetWidth()) * k + ITEM_GAP + size
  local edge = UIParent:GetRight()
  b.onRight = not (edge and x > edge)
  if not b.onRight then x = left * k - ITEM_GAP end
  return x, y
end

function ui.PlaceSecure()
  if InCombatLockdown() then return end
  local screen = UIParent:GetEffectiveScale()
  for _, b in ipairs({ targetButton, itemButton }) do
    local x, y, out, top, behind, right
    if b.beside then out, top, behind, right = BesideSpot(b, b.beside, screen) end
    local k = b.along
    if k then
      if k.placedX then
        x, y = k.side and k.placedX + SLIDE_GAP + (b.size or KEY_SIZE) or k.placedX - k.size - SLIDE_GAP, k.placedY
        b:SetAlpha(k.slideAlpha or 1)
      end
    elseif out then
      local f = Slid(GetTime())
      x, y = behind + (out - behind) * f, top
      b.slideAlpha = math.min(1, f * 1.5)
      b:SetAlpha(b.slideAlpha)
      if right ~= b.side then
        b.side = right
        b.away:ClearAllPoints()
        b.away:SetPoint("CENTER", b, right and "BOTTOMRIGHT" or "TOPLEFT", right and -2 or 2, right and 2 or -2)
      end
    elseif b == itemButton then
      x, y = ItemSpot(b, screen)
    else
      local on = b.anchor
      if b.beside then b.slideAlpha = 1; b:SetAlpha(1) end
      local left, t, scale = on:GetLeft(), on:GetTop(), on:GetEffectiveScale()
      if left and t and scale and screen then x, y = left * scale / screen - 4, t * scale / screen - b.below end
    end
    if x and (b.placedX ~= x or b.placedY ~= y) then
      b.placedX, b.placedY = x, y
      b:ClearAllPoints()
      b:SetPoint("TOPRIGHT", UIParent, "BOTTOMLEFT", x, y)
    end
  end
  ui.PlaceAlongItems(screen)
end
ns.PlaceGuideKeys = ui.PlaceSecure

local slider = CreateFrame("Frame")
slider:Hide()
ns.targetSlider = slider
function ui.SlideStep()
  ui.PlaceSecure()
  local s = find.slide
  if s and select(2, Slid(GetTime())) then
    find.slide = nil
    if not s.out then
      Look(targetButton, nil)
      targetButton.beside = nil
      targetButton:Hide()
    end
  end
  if not find.slide and not find.moving then slider:Hide() end
end
ns.OnTick(slider, "the keys' slide", nil, function() if not InCombatLockdown() then ui.SlideStep() end end)
local function Slide(out)
  local now, at = GetTime(), GetTime()
  local s = find.slide
  if s and s.out ~= out then
    local x = Slid(now)
    local d = out and 1 - x or x
    at = now - (1 - d ^ (1 / 3)) * SLIDE_SECONDS
  end
  find.slide = { out = out, at = at }
  slider:Show()
end
function ui.SlideDone()
  if find.slide then
    find.slide.at = GetTime() - SLIDE_SECONDS
    ui.SlideStep()
  end
end
function ns.FollowButton(on)
  find.moving = on or nil
  if on then slider:Show() else ui.SlideStep() end
end

function ui.KeyLabels()
  for _, b in ipairs({ targetButton, itemButton }) do
    if b == targetButton and ns.guideTalking then break end
    local key = Plain(Call(GetBindingKey, KeyAction(b)))
    b.keyText:SetText(key and (key:gsub("CTRL%-", "c-"):gsub("SHIFT%-", "s-"):gsub("ALT%-", "a-")) or "")
  end
end

local HELD_KEYS = { LSHIFT = true, RSHIFT = true, LCTRL = true, RCTRL = true, LALT = true, RALT = true, LMETA = true, RMETA = true }
local KEY_WAIT = 8
local keyPrompt = Box(UIParent, C.bg, C.edge, "DIALOG")
keyPrompt:SetSize(250, 40)
keyPrompt:EnableKeyboard(true)
keyPrompt:Hide()
keyPrompt.text = Text(keyPrompt, "GameFontHighlightSmall", C.ivory)
keyPrompt.text:SetPoint("TOPLEFT", 10, -7)
keyPrompt.text:SetPoint("RIGHT", -10, 0)
ns.keyPrompt = keyPrompt
local function AskKey(b, what)
  if InCombatLockdown() then return ns.Print("Set the key after the fight. The game won't change keys in combat.") end
  keyPrompt.button, keyPrompt.what = b, what
  local key = Plain(Call(GetBindingKey, KeyAction(b)))
  keyPrompt.text:SetText(string.format("Press a key for %s%s. Escape leaves the key as it is.", what, key and (" (now " .. key .. ")") or ""))
  keyPrompt:ClearAllPoints()
  keyPrompt:SetPoint("TOPRIGHT", b, "TOPLEFT", -6, 0)
  keyPrompt:Show()
  keyPrompt:SetPropagateKeyboardInput(false)
  local asked = {}
  keyPrompt.asked = asked
  C_Timer.After(KEY_WAIT, function()
    if keyPrompt:IsShown() and keyPrompt.asked == asked then
      keyPrompt:Hide()
      ns.Print((what:gsub("^%l", string.upper)) .. ": you pressed no key, so the key stays as it was.")
    end
  end)
end
keyPrompt:SetScript("OnKeyDown", function(self, key)
  if HELD_KEYS[key] then return end
  self:Hide()
  if key == "ESCAPE" then return ns.Print((self.what:gsub("^%l", string.upper)) .. ": the key stays as it was.") end
  if InCombatLockdown() then return ns.Print("Set the key after the fight. The game won't change keys in combat.") end
  local combo = (IsAltKeyDown() and "ALT-" or "") .. (IsControlKeyDown() and "CTRL-" or "") .. (IsShiftKeyDown() and "SHIFT-" or "") .. key
  local action = KeyAction(self.button)
  local was = Plain(Call(GetBindingAction, combo))
  for _, old in ipairs({ Call(GetBindingKey, action) }) do Call(SetBinding, old) end
  if not Call(SetBindingClick, combo, self.button.bindName, KEY_BUTTON) then return ns.Print("The game didn't take " .. combo .. ".") end
  Call(SaveBindings, Call(GetCurrentBindingSet))
  local before = was and was ~= "" and was ~= action and (_G["BINDING_NAME_" .. was] or was)
  ns.Print(string.format("%s is now on %s%s.", (self.what:gsub("^%l", string.upper)), combo, before and (", which no longer does " .. before) or ""))
  ui.KeyLabels()
end)
targetButton.setkey = function(self) AskKey(self, "Target") end
itemButton.setkey = function(self) AskKey(self, "the quest item") end
local movedLater = false
local function MoveKey(key, b)
  key = Plain(key)
  return (key and Call(SetBindingClick, key, b.bindName, KEY_BUTTON)) and true or false
end
local function MoveOldKeys()
  if InCombatLockdown() then movedLater = true; return end
  movedLater = false
  local moved = false
  for _, b in ipairs({ targetButton, itemButton }) do
    local keys = { Call(GetBindingKey, "CLICK " .. b.bindName .. ":LeftButton") }
    for _, key in ipairs(keys) do moved = MoveKey(key, b) or moved end
  end
  if moved then Call(SaveBindings, Call(GetCurrentBindingSet)) end
end
ns.MoveOldKeys = MoveOldKeys
ns.On({ "UPDATE_BINDINGS", "PLAYER_REGEN_DISABLED", "PLAYER_REGEN_ENABLED" }, function(event)
  if event == "PLAYER_REGEN_ENABLED" then
    if movedLater then MoveOldKeys() end
    return
  end
  if event == "PLAYER_REGEN_DISABLED" then
    if keyPrompt:IsShown() then keyPrompt:Hide(); ns.Print((keyPrompt.what:gsub("^%l", string.upper)) .. ": the key stays as it was. Set the key after the fight.") end
    return
  end
  MoveOldKeys()
  ui.KeyLabels()
end)
ui.KeyLabels()

local BANK = Enum and Enum.SpellBookSpellBank and Enum.SpellBookSpellBank.Player or 0
local SPELL_ITEM = Enum and Enum.SpellBookItemType and Enum.SpellBookItemType.Spell or 1
local PICK_W, PICK_ROW, PICK_ROWS = 240, 22, 12
local PICK_TOP = 52

local function HarmfulSpells()
  local out = {}
  for line = 1, Call(C_SpellBook.GetNumSpellBookSkillLines) or 0 do
    local info = Call(C_SpellBook.GetSpellBookSkillLineInfo, line)
    if info and not info.shouldHide then
      for i = info.itemIndexOffset + 1, info.itemIndexOffset + info.numSpellBookItems do
        local item = Call(C_SpellBook.GetSpellBookItemInfo, i, BANK)
        if item and item.name and item.itemType == SPELL_ITEM and not item.isPassive
           and Plain(Call(C_SpellBook.IsSpellBookItemHarmful, i, BANK)) then
          out[#out + 1] = { name = item.name, rank = tonumber((item.subName or ""):match("(%d+)")), id = item.spellID, icon = item.iconID }
        end
      end
    end
  end
  return out
end
ns.HarmfulSpells = HarmfulSpells

local function Picked()
  local sp = IndexOfAzerothCharDB and IndexOfAzerothCharDB.targetSpell
  return type(sp) == "table" and type(sp.name) == "string" and sp or nil
end
local function SpellWords(sp) return sp.name .. (sp.rank and (" (Rank " .. sp.rank .. ")") or "") end

function ns.ItemIsObjective(questID)
  for _, o in ipairs(ns.QuestObjectives(questID)) do
    local text = type(o) == "table" and not Plain(o.finished) and Plain(o.text)
    if type(text) == "string" and Plain(o.type) ~= "item"
       and not (text:match("^.- slain: %d+/%d+$") or text:match("^%d+/%d+ .- slain$")) then return true end
  end
  return false
end

local function UseLine(want)
  local item = want and not want.talk and want.mobs and want.item
  if not item then return "", false end
  return "/use [@target,harm,nodead] item:" .. item.id .. "\n", not Picked() or ns.ItemIsObjective(item.quest)
end
function ns.TargetCastLines(want)
  if not want or want.talk or not want.mobs then return "" end
  local sp = Picked()
  local cast = sp and ("/cast [@target,harm,nodead] " .. sp.name .. (sp.rank and ("(Rank " .. sp.rank .. ")") or "") .. "\n") or ""
  local use, leads = UseLine(want)
  if cast == "" and use == "" then return "" end
  return (leads and (use .. cast) or (cast .. use)) .. "/stopmacro [@target,harm,nodead]\n"
end
function ns.TargetTakeUse(want)
  local use, leads = UseLine(want)
  return leads and use or ""
end

targetButton.spellIcon = targetButton:CreateTexture(nil, "OVERLAY")
targetButton.spellIcon:SetSize(13, 13)
targetButton.spellIcon:SetPoint("BOTTOMLEFT", 1, 1)
local function ShowPicked()
  local sp = Picked()
  targetButton.spellIcon:SetTexture(sp and sp.icon or nil)
  targetButton.spellIcon:SetShown(sp ~= nil and sp.icon ~= nil)
end
ns.On("PLAYER_LOGIN", ShowPicked)
function ui.KeyCorner(text)
  local id = tonumber((text or ""):match("/use %[@target,help,nodead%] item:(%d+)"))
  targetButton.cornerItem = id
  if not id then return ShowPicked() end
  local icon = Plain(Call(C_Item and C_Item.GetItemIconByID, id)) or Plain(Call(GetItemIcon, id))
  targetButton.spellIcon:SetTexture(icon or 134400)
  targetButton.spellIcon:Show()
end
function ui.TargetSpellLine()
  local sp = Picked()
  GameTooltip:AddLine("Ctrl+right-click: pick a spell for this key to cast at the mob it picks up" .. (sp and (" (now " .. SpellWords(sp) .. ")") or ""),
    C.muted[1], C.muted[2], C.muted[3], true)
end

local picker = nil
local function Pick(sp)
  IndexOfAzerothCharDB.targetSpell = sp and { name = sp.name, rank = sp.rank, id = sp.id, icon = sp.icon } or nil
  picker:Hide()
  ShowPicked()
  ns.Print(sp and ("The Target key casts " .. SpellWords(sp) .. " at the mob it picks up"
    .. (InCombatLockdown() and ", once this fight is over" or "") .. ".") or "The Target key casts nothing now.")
  ui.Secure()
end
local function OpenPicker()
  if not picker then
    picker = UI.Panel(CreateFrame("Frame", "IndexOfAzerothTargetSpells", UIParent, "BackdropTemplate"))
    picker:SetFrameStrata("DIALOG")
    picker:SetToplevel(true)
    picker:SetClampedToScreen(true)
    picker:EnableMouse(true)
    picker:SetWidth(PICK_W)
    tinsert(UISpecialFrames, "IndexOfAzerothTargetSpells")
    local title = Text(picker, "GameFontNormal", C.gold)
    title:SetPoint("TOPLEFT", 8, -8)
    title:SetText("Cast with the Target key")
    local words = Text(picker, "GameFontHighlightSmall", C.muted)
    words:SetPoint("TOPLEFT", 8, -24)
    words:SetWidth(PICK_W - 16)
    words:SetText("The key's first press picks up the mob, and each press after that casts the spell picked here at the mob.")
    local close = UI.FlatButton(picker, "x", 18, function() picker:Hide() end)
    close:SetSize(18, 18)
    close:SetPoint("TOPRIGHT", -5, -5)
    picker.scroll = UI.Scroller(picker)
    picker.scroll:SetPoint("TOPLEFT", 6, -PICK_TOP)
    picker.scroll:SetPoint("BOTTOMRIGHT", -6, 6)
    picker.rows = {}
    ns.targetSpellPicker = picker
  end
  local list, chosen = HarmfulSpells(), Picked()
  table.insert(list, 1, false)
  for i, sp in ipairs(list) do
    local row = picker.rows[i]
    if not row then
      row = UI.FlatButton(picker.scroll.child, "", PICK_W - 18)
      row:SetHeight(PICK_ROW)
      row:SetPoint("TOPLEFT", 0, -(i - 1) * (PICK_ROW + 2))
      row.icon = row:CreateTexture(nil, "ARTWORK")
      row.icon:SetSize(16, 16)
      row.icon:SetPoint("LEFT", 4, 0)
      row.label:ClearAllPoints()
      row.label:SetPoint("LEFT", 26, 0)
      row.label:SetJustifyH("LEFT")
      picker.rows[i] = row
    end
    row.label:SetText(sp and SpellWords(sp) or "None")
    row.icon:SetTexture(sp and sp.icon or nil)
    row:SetScript("OnClick", function() Pick(sp or nil) end)
    row:SetSelected(sp and chosen ~= nil and chosen.name == sp.name and chosen.rank == sp.rank or (not sp and chosen == nil))
    row:Show()
  end
  for i = #list + 1, #picker.rows do picker.rows[i]:Hide() end
  picker:SetHeight(PICK_TOP + math.min(#list, PICK_ROWS) * (PICK_ROW + 2) + 6)
  picker.scroll:Reset(#list * (PICK_ROW + 2))
  picker:ClearAllPoints()
  picker:SetPoint("TOPRIGHT", targetButton, "TOPLEFT", -6, 0)
  picker:Show()
end
targetButton:SetAttribute("ctrl-type2", "pickspell")
targetButton.pickspell = function() OpenPicker() end

local function Keyed(keys, loose, names, ids, keyed)
  if type(ids) == "table" and #ids > 0 then
    for _, k in ipairs(ids) do keys[k] = true end
    for _, n in ipairs(names or {}) do
      loose[n] = nil
      if keyed then keyed[n] = true end
    end
  else
    for _, n in ipairs(names or {}) do
      if not (keyed and keyed[n]) then loose[n] = true end
    end
  end
end
function ui.Wanted(want, unit)
  if not want then return false end
  local names = {}
  if want.who then names[want.who] = true end
  for _, n in ipairs(want.mobs or {}) do names[n] = true end
  for n in pairs(want.talks or {}) do names[n] = true end
  if not want.keys then return ns.Geo.UnitIs(unit, nil, names, names) end
  return ns.Geo.UnitIs(unit, want.keys, names, want.loose)
end
function ui.StepWanted(g, s, unit)
  local targets = ui.StepTargets(g, s)
  local names = targets and targets.names or s.mobs or {}
  local keys, loose, set = {}, {}, {}
  for _, n in ipairs(names) do set[n] = true end
  Keyed(keys, loose, names, not targets and s.mi or nil)
  return ns.Geo.UnitIs(unit, keys, set, loose)
end

function ui.EpicWant(g, s, shown)
  if not s or not (shown or KeyOptions().cardHidden) then return nil end
  local arrow = ns.guideSlots and ns.guideSlots.e and ns.guideSlots.e.frame
  local anchor = (shown or not (arrow and arrow:IsShown())) and card or arrow
  local ride, rideKey = nil, nil
  if ns.EpicRideWho then ride, rideKey = ns.EpicRideWho() end
  if ride == true then return nil end
  if ride then
    return { who = ride, talk = true, flight = true, service = true, anchor = anchor, tip = ns.FLIGHT_MASTER_TIP,
             keys = rideKey and { [rideKey] = true } or nil }
  end
  if s.kind == "D" then return ui.RunWant(g, s, anchor) end
  local farm = s.kind == "S" and s.what == "farm"
  local talk = s.kind == "P" or s.kind == "T" or (s.kind == "S" and not farm)
  if talk then
    local key = ns.Geo.GiverKey(s)
    return s.npc and { who = s.npc, talk = true, service = s.kind == "S", anchor = anchor, keys = key and { [key] = true } }
      or nil
  end
  local names = type(s.mobs) == "table" and #s.mobs > 0 and s.mobs or (s.talk and s.npc and { s.npc }) or nil
  if s.kind == "O" and (s.fr or s.talk) and names then
    local spots, any = {}, #names > 1 or nil
    for _, n in ipairs(names) do spots[n] = s end
    local keys, loose = {}, {}
    Keyed(keys, loose, names, s.mi)
    return { who = names[1], mobs = names, foes = {}, talk = s.talk, own = not s.talk or nil, cycle = any,
             anchor = anchor, targets = { names = names, spots = spots, any = any }, friendly = s.fr or nil,
             keys = keys, loose = loose }
  end
  local open, done = ui.LogKills()
  local mobs, seen, keys, loose, keyed = {}, {}, {}, {}, {}
  local function add(list, ids)
    for _, n in ipairs(list or {}) do
      if not seen[n] and not (done[n] and not open[n]) then seen[n], mobs[#mobs + 1] = true, n end
    end
    Keyed(keys, loose, list, ids, keyed)
  end
  local targets = s.kind == "O" and ui.StepTargets(g, s) or nil
  if targets then add(targets.names) elseif s.kind == "O" or farm then add(s.mobs, s.mi) end
  local own = #mobs
  for j, t in ipairs(g and g.steps or {}) do
    if t ~= s and g.state and g.state[j] == ns.GUIDE.TODO and ns.Rules.OnCard(s.kind, s.ids, t.kind, t.ids and t.ids[1]) then
      add(t.mobs, t.mi)
    end
  end
  for _, a in ipairs(ui.AlongSteps(g, s.i)) do add(a.mobs, a.mi) end
  if #mobs == 0 then return nil end
  add(ui.Sorted(open))
  return { who = mobs[1], mobs = mobs, own = own > 0 or nil, cycle = (#mobs > own or (targets and own > 1)) or nil, anchor = anchor,
           targets = targets, friendly = (targets and s.fr) or nil, keys = keys, loose = loose }
end

local function TargetOnly(s)
  return s.kind == "O" and type(s.target) == "string" and s.target ~= "" and not (s.mobs and #s.mobs > 0)
end
local targetOrder = { key = nil, names = nil }
function ui.StepTargets(g, s)
  if not (s and TargetOnly(s)) then return nil end
  local spots, list = {}, {}
  for j, t in ipairs(g and g.steps or {}) do
    if TargetOnly(t) and t.ids[1] == s.ids[1] and (t == s or (g.state and g.state[j] == ns.GUIDE.TODO))
       and not spots[t.target] then
      spots[t.target], list[#list + 1] = t, t.target
    end
  end
  table.sort(list)
  local key = table.concat(list, "\n")
  if targetOrder.key ~= key then
    local continent, px, py = ns.PlayerWorldPos()
    local function far(n)
      local t = spots[n]
      if not (px and t.wx and t.inst == continent) then return math.huge end
      return ns.Geo.Dist(t.wx, t.wy, px, py)
    end
    local yards = {}
    for _, n in ipairs(list) do yards[n] = far(n) end
    table.sort(list, function(a, b) if yards[a] ~= yards[b] then return yards[a] < yards[b] end return a < b end)
    targetOrder.key, targetOrder.names = key, list
  end
  return { names = targetOrder.names, spots = spots }
end

local function Tagged(unit) return Plain(Call(UnitIsTapDenied, unit)) == true end

local usedOn = {}
function ui.UsedOn(quest, unit)
  local guid = Plain(Call(UnitGUID, unit))
  return guid ~= nil and usedOn[quest] ~= nil and usedOn[quest][guid] == true
end
local function ItemsSpell(itemID, spellID)
  local name, id = Call((C_Item and C_Item.GetItemSpell) or GetItemSpell, itemID)
  name, id = Plain(name), Plain(id)
  if id and spellID then return id == spellID end
  local cast = spellID and Plain(Call(C_Spell and C_Spell.GetSpellName, spellID))
  return type(name) == "string" and name == cast
end
ns.On("UNIT_SPELLCAST_SUCCEEDED", function(_, unit, _, spellID)
  local want = targetButton.want
  local item = want and want.item
  spellID = Plain(spellID)
  if unit ~= "player" or not (item and want.mobs and spellID and ItemsSpell(item.id, spellID)) then return end
  local guid = Plain(Call(UnitGUID, "target"))
  if not (guid and Plain(Call(UnitCanAttack, "player", "target")) == false and ui.Wanted(want, "target")) then return end
  usedOn[item.quest] = usedOn[item.quest] or {}
  usedOn[item.quest][guid] = true
  if not InCombatLockdown() then ui.Secure() end
end, "player")

local STAY = "/stopmacro [@target,harm,nodead]\n"
local serviceSet, serviceFrom = {}, nil
function ns.ServiceNpc(name)
  local sh = IndexOfAzerothShared
  local list = type(sh) == "table" and type(sh.services) == "table" and sh.services or nil
  if list ~= serviceFrom then
    serviceSet, serviceFrom = {}, list
    for _, n in ipairs(list or {}) do serviceSet[n] = true end
  end
  return name ~= nil and serviceSet[name] == true
end
function ui.WantMark(want)
  if not want.talk then return nil end
  local service = want.service
  if service == nil then service = want.flight or ns.ServiceNpc(want.who) end
  return service and 3 or 5
end
function ui.TargetMacro(want)
  local exists = Plain(Call(UnitExists, "target"))
  local name = exists and Plain(Call(UnitName, "target"))
  local alive = exists and not Plain(Call(UnitIsDead, "target"))
  local kind = KeyOptions().mark and ui.WantMark(want)
  local mark = kind and ("\n/tm [exists,nodead] ~" .. kind) or ""
  local live, tagged, alone = {}, {}, nil
  if want.mobs and ui.LivePlates then live, tagged, alone = ui.LivePlates(want) end
  local ours = exists and ui.Wanted(want, "target")
  local targetTagged = ours and alive and want.mobs and Tagged("target")
  if targetTagged then tagged[name] = true end
  local lines = {}
  for _, unit in ipairs(live) do lines[#lines + 1] = "/target [@" .. unit .. ",exists,nodead,harm]\n" end
  local got = not want.friendly and ns.TargetTakeUse(want) or ""
  local first = alone and not tagged[alone] and ("/targetexact " .. alone .. "\n/cleartarget [dead]\n" .. got .. STAY) or ""
  local byName = first == "" and (#lines > 0 and "/targetexact [noexists] " or not next(tagged) and "/targetexact ") or nil
  local named = byName and (byName .. want.who .. "\n/cleartarget [dead]") or ""
  local after = (first == "" and got ~= "" and (#lines > 0 or named ~= ""))
    and ((named ~= "" and "\n" or "") .. (got:gsub("\n$", ""))) or ""
  local take = first .. table.concat(lines) .. named .. after .. mark
  local friendly = exists and Plain(Call(UnitCanAttack, "player", "target")) == false
  local fight = ns.InFight()
  local item = want.item
  local used = item and ours and alive and friendly and ui.UsedOn(item.quest, "target")
  if want.targets and want.targets.spots[want.who] then
    local use = (item and want.friendly and not fight) and ("/use [@target,help,nodead] item:" .. item.id .. "\n") or got
    take = ((used and name == want.who) and "" or "/cleartarget\n") .. "/targetexact " .. want.who
      .. "\n/cleartarget [dead]\n" .. use .. "/stopmacro [@target,exists]\n" .. take
  end
  local passOn = want.targets and ours and friendly and ((want.cycle and not item) or used)
  local holds = want.mobs and not want.talk and ours and alive and not targetTagged and not passOn
  if item and ours and alive and not fight and friendly and not passOn then
    return "/use [@target,help,nodead] item:" .. item.id .. "\n/stopmacro [@target,help,nodead]", nil, false
  end
  local text = ""
  if want.mobs and not want.talk and not targetTagged and (holds or fight or not alive) then
    local cast = (item and want.friendly and not fight) and "" or ns.TargetCastLines(want)
    text = text .. (cast ~= "" and cast or STAY) .. "/cleartarget\n" .. take
  else
    local clear = want.talk or (exists and not ours) or (targetTagged and #lines > 0)
    text = text .. (clear and "/cleartarget\n" or "/cleartarget [dead]\n") .. take
  end
  local onlyTagged = #lines == 0 and next(tagged) and not holds and tagged or nil
  return (text:gsub("\n$", "")), onlyTagged, holds and true or false
end

local rounds = {}
local function RoundAt(owner, names)
  local key = table.concat(names, "\n")
  local r = rounds[owner]
  if not (r and r.key == key) then
    r = { key = key, n = #names, at = 1 }
    rounds[owner] = r
  end
  return r.at
end
local function MobsRound(want, owner)
  want.who, want.round = want.mobs[RoundAt(owner, want.mobs)], owner
end

local function KeySpot(want)
  local button = CCButton()
  local anchor = want.anchor or card
  if anchor == button then anchor = card end
  return (button and button:IsShown()) and button or nil, anchor
end

local secureLater = false
function ui.Secure()
  if InCombatLockdown() then secureLater = true; return end
  secureLater = false
  local g = ns.GuideInfo() or (ns.PastedGuide and ns.PastedGuide())
  local s = g and g.cur and g.steps[g.cur]
  local shown = card:IsShown()
  local ghost = ns.Ghost()
  ui.targetWants.epic = ui.EpicWant(g, s, shown)
  local want, owner = nil, nil
  if not ghost then want, owner = ui.TargetNow() end
  if want and want.cycle then MobsRound(want, owner) end
  targetButton.owner = owner
  local link, tex = nil, nil
  if s and s.kind ~= "P" and not ghost then
    local index = Plain(Call(C_QuestLog.GetLogIndexForQuestID, s.ids[1]))
    if index then link, tex = Call(GetQuestLogSpecialItemInfo, index) end
    link, tex = Plain(link), Plain(tex)
  end
  local itemID = type(link) == "string" and tonumber(link:match("item:(%d+)"))
  if want and owner == "epic" and itemID and want.own then
    want.item = { id = itemID, quest = s.ids[1] }
  end
  if s and g and not g.pasted and ns.GuideHearth and ns.GuideHearth(g.cur) then
    link = "item:6948"
    tex = Plain(Call(C_Item and C_Item.GetItemIconByID or GetItemIcon, 6948)) or 134414
  end
  if want then
    local text, onlyTagged = ui.TargetMacro(want)
    targetButton:SetAttribute("macrotext", text)
    ui.KeyCorner(text)
    targetButton.who, targetButton.want, targetButton.onlyTagged = want.who, want, onlyTagged
    local beside
    beside, targetButton.anchor = KeySpot(want)
    local away = beside ~= nil and want.putaway or false
    if beside ~= targetButton.beside then
      local was = targetButton.beside
      targetButton.beside = beside
      Look(targetButton, beside, away)
      if beside then Slide(true) elseif was then find.slide = nil end
    else
      if away ~= targetButton.awayOn then Look(targetButton, beside, away) end
      if beside and ((find.slide and not find.slide.out) or targetButton.faded) then Slide(true) end
    end
    if not find.slide then targetButton:SetAlpha(1) end
    targetButton.faded = nil
    targetButton:Show()
  else
    targetButton.want = nil
    local sliding = find.slide and not find.slide.out
    local into = targetButton.beside and BesideSpot(targetButton, targetButton.beside, UIParent:GetEffectiveScale())
    if into and targetButton:IsShown() and not sliding then
      Slide(false)
    elseif not sliding then
      if targetButton.beside then targetButton.beside = nil; Look(targetButton, nil) end
      targetButton:Hide()
    end
  end
  local along = not shown and targetButton.want and targetButton.owner == "epic" and targetButton.beside and targetButton or nil
  itemButton.along = link and along or nil
  if link and (shown or along) then
    itemButton:SetAttribute("item", link)
    itemButton.link = link
    itemButton.icon:SetTexture(tex or 134400)
    itemButton:SetAlpha(along and (targetButton.slideAlpha or 1) or 1)
    itemButton:Show()
  else
    itemButton:Hide()
  end
  ui.AlongItems()
  ui.PlaceSecure()
end

local SAID_FOR = 2
local said = { at = -math.huge }
local function SayOnScreen(text)
  local now = GetTime()
  if said.text == text and now - said.at < SAID_FOR then return end
  said.text, said.at = text, now
  local line = UIErrorsFrame
  if not (line and pcall(line.AddMessage, line, text, 1, 0.1, 0.1)) then ns.Print(text) end
end
local function TaggedWords(want, tagged)
  local names = {}
  for _, n in ipairs(want.mobs) do if tagged[n] then names[#names + 1] = n end end
  local last = table.remove(names)
  return "Every " .. (#names > 0 and (table.concat(names, ", ") .. " and ") or "") .. last
    .. " near you is tagged by someone else"
end
local function TaggedTarget(want)
  if not (want and want.mobs) or not Plain(Call(UnitExists, "target")) or Plain(Call(UnitIsDead, "target")) then return nil end
  local name = Plain(Call(UnitName, "target"))
  if not (name and Tagged("target")) then return nil end
  return ui.Wanted(want, "target") and name or nil
end
local function HeldWords(name)
  return name .. " is tagged by someone else. In a fight the Target key can't let go of it, so target another one yourself."
end
local HOLD = "/stopmacro [@target,harm,nodead]"
local function HoldsTarget(macro)
  return type(macro) == "string" and (macro:match("^(.-)/cleartarget") or macro):find(HOLD, 1, true) ~= nil
end

local PRESS_SECONDS = 0.5
targetButton:SetScript("PreClick", function(self, button, down)
  local want = self.want
  if not want or (IsControlKeyDown() and button ~= KEY_BUTTON) or (button == "RightButton" and self.awayOn) then return end
  self.pressed = GetTime()
  if not InCombatLockdown() then
    local text, onlyTagged, stays = ui.TargetMacro(want)
    self:SetAttribute("macrotext", text)
    ui.KeyCorner(text)
    self.onlyTagged = onlyTagged
    if down then self.stays = stays end
  elseif down and HoldsTarget(self:GetAttribute("macrotext")) then
    local held = TaggedTarget(want)
    if held then SayOnScreen(HeldWords(held)) end
  end
  if down and self.onlyTagged then SayOnScreen(TaggedWords(want, self.onlyTagged)) end
end)
local EPIC_LEADS_YARDS = 40
function ui.GuideToTarget(want)
  if want.targets.any then return end
  if Plain(Call(UnitExists, "target")) and ui.Wanted(want, "target") then return end
  local near = want.targets.names[1]
  local s = near and want.targets.spots[near]
  if not (s and s.wx and s.map and s.inst) or InCombatLockdown() then return end
  local guiding = ns.GuideTarget and ns.GuideTarget()
  if guiding and guiding.name == near then return end
  local epic = ns.TrackTarget and ns.TrackTarget("e")
  if epic and epic.wx and epic.continent == s.inst
     and (epic.wx - s.wx) ^ 2 + (epic.wy - s.wy) ^ 2 <= EPIC_LEADS_YARDS ^ 2 then
    SayOnScreen(near .. " is out of reach. The blue arrow already leads you to " .. near)
    return
  end
  SayOnScreen(near .. " is out of reach. The gold arrow leads you to " .. near)
  if ns.SetWorldPath then ns.SetWorldPath(s.map, { { s.wx, s.wy } }, s.inst, near) end
end

targetButton:SetScript("PostClick", function(self, button, down)
  if down then return end
  local want, stays = self.want, self.stays
  self.stays = nil
  if want and want.targets and not (IsControlKeyDown() and button ~= KEY_BUTTON) then ui.GuideToTarget(want) end
  local r = want and want.round and rounds[want.round]
  if not (r and r.n > 1) or stays or InCombatLockdown() or (IsControlKeyDown() and button ~= KEY_BUTTON) then return end
  r.at = r.at % r.n + 1
  ui.Secure()
end)

ns.On("PLAYER_TARGET_CHANGED", function()
  local want = targetButton.want
  local name = GetTime() - (targetButton.pressed or -math.huge) <= PRESS_SECONDS and TaggedTarget(want)
  if name then
    local held = InCombatLockdown() and HoldsTarget(targetButton:GetAttribute("macrotext"))
    SayOnScreen(held and HeldWords(name) or (name .. " is tagged by someone else"))
  end
  if targetButton:IsShown() then ui.Secure() end
  ui.UseCue()
end)
local ATTACK_KEPT = 600
local canAttack, attackPruned = {}, 0
ns.canAttack = canAttack
local function SeeAttack(unit)
  local now = GetTime()
  if now - attackPruned >= 60 then
    attackPruned = now
    for name, seen in pairs(canAttack) do
      if now - seen.t > ATTACK_KEPT then canAttack[name] = nil end
    end
  end
  if not ns.Geo.Creature(Plain(Call(UnitGUID, unit))) then return end
  local name = Plain(Call(UnitName, unit))
  local can = Plain(Call(UnitCanAttack, "player", unit))
  if name and can ~= nil then canAttack[name] = { can = can and true or false, t = now } end
end
ns.On({ "PLAYER_TARGET_CHANGED", "NAME_PLATE_UNIT_ADDED" }, function(event, unit)
  SeeAttack(event == "PLAYER_TARGET_CHANGED" and "target" or unit)
end)
function ns.TargetKeyHolds()
  local who = targetButton.who
  if not (who and targetButton.owner == "find" and targetButton.want and targetButton.want == ui.targetWants.find
          and targetButton.beside and targetButton:IsShown() and not (find.slide and not find.slide.out)) then return nil end
  local seen = canAttack[who]
  local can = seen and seen.can
  if can == nil then can = find.hostile end
  return can and who or nil
end
function ns.GuideKeysAgain() ui.Secure() end
ns.On({ "PLAYER_DEAD", "PLAYER_ALIVE", "PLAYER_UNGHOST" }, function() ui.Secure(); ui.Render() end)
ns.On({ "PLAYER_ENTERING_WORLD", "ZONE_CHANGED_NEW_AREA", "ENCOUNTER_END" }, function() ui.Secure() end)

function ns.TargetWant(owner, want)
  local was = ui.targetWants[owner]
  ui.targetWants[owner] = want
  if not want and was and targetButton.want == was and InCombatLockdown() then
    targetButton:SetAlpha(0)
    targetButton.faded = true
  end
  ui.Secure()
end

local function PutAway(typed)
  if not find.who then
    if typed then ns.Print("No Target key is out beside the add-on button.") end
    return
  end
  local check = find.check
  find.who, find.hostile, find.check = nil, nil, nil
  ns.guideDirty = true
  if ns.PendingSettle then ns.PendingSettle(check) end
  ns.TargetWant("find", nil)
  ns.Print("You put the Target key away.")
end
away:SetScript("OnClick", function() PutAway() end)
targetButton.putaway = function() PutAway() end

function ns.TargetCommand(rest)
  rest = strtrim(rest or "")
  if rest == "" or rest:lower() == "off" then return PutAway(true) end
  local mark, who = rest:match("^([@!])%s*(.-)%s*$")
  if not who or who == "" then
    return ns.Print("Type /ioa target @Name for someone to talk to, /ioa target !Name for a mob or /ioa target off to put the key away.")
  end
  local hostile = mark == "!"
  find.who, find.hostile, find.check = who, hostile, ns.LineCheck("target", rest)
  ns.guideDirty = true
  local button = CCButton()
  ns.TargetWant("find", { who = who, mobs = hostile and { who } or nil, talk = not hostile, anchor = button or card,
    putaway = true, tip = (hostile and "Press this to target that mob. A live mob comes first." or ns.TALK_TIP)
      .. " Right-click the key or click its x to put the key away." })
  ns.Print("The Target key for " .. who .. " is out beside the add-on button. Right-click the key or click its x to put it away.")
end
function ns.TargetFinding()
  if find.who then return find.who, find.check end
end

local followed = nil
function ui.Follow()
  local shown = card:IsShown() and true or false
  if shown == followed then return end
  followed = shown
  if not shown then
    itemButton:SetAlpha(0)
    if targetButton.owner == "epic" and not KeyOptions().cardHidden and InCombatLockdown() then
      targetButton:SetAlpha(0)
      targetButton.faded = true
    end
  end
  ui.Secure()
end

local CUE = { SEGMENTS = 20, GROW = 0.45, AGAIN = 2.4, RISE = 30, LIFT = 9, HEAD = 9, WORDS = "Use this", SPACE = 4,
              AT_YARDS = 20 }
local PLACE_KINDS = { use = true, explore = true, grab = true, event = true }
local cue = CreateFrame("Frame", nil, UIParent)
cue:SetFrameStrata("HIGH")
cue:SetSize(1, 1)
cue:SetPoint("BOTTOMLEFT", UIParent, "BOTTOMLEFT", 0, 0)
cue:EnableMouse(false)
cue:Hide()
ns.useCue = cue
do
  local Y = C.yellow
  local function CueLine(level, thick, r, g, b, a)
    local l = cue:CreateLine(nil, "OVERLAY", nil, level)
    l:SetThickness(thick)
    l:SetColorTexture(r, g, b, a)
    return l
  end
  cue.shade, cue.lines = {}, {}
  for k = 1, CUE.SEGMENTS + 2 do
    cue.shade[k] = CueLine(1, 5, 0, 0, 0, 0.6)
    cue.lines[k] = CueLine(2, 3, Y[1], Y[2], Y[3], 1)
  end
  cue.letters = {}
  for k = 1, #CUE.WORDS do
    local fs = cue:CreateFontString(nil, "OVERLAY", "GameFontNormal")
    fs:SetText(CUE.WORDS:sub(k, k))
    fs:SetTextColor(Y[1], Y[2], Y[3])
    fs:SetShadowColor(0, 0, 0, 1)
    fs:SetShadowOffset(1, -1)
    cue.letters[k] = fs
  end
  cue.glowAt = CreateFrame("Frame", nil, UIParent)
  cue.glowAt:SetFrameStrata("HIGH")
  cue.glowAt:SetSize(KEY_SIZE, KEY_SIZE)
  cue.glowAt:EnableMouse(false)
  cue.glow = UI.Pulse(cue.glowAt, Y, KEY_SIZE * 1.9)
  cue.glow:Show()
  cue.glowAt:Hide()
end
local function Bez(c, t)
  local u = 1 - t
  return u * u * c[1] + 2 * u * t * c[3] + t * t * c[5], u * u * c[2] + 2 * u * t * c[4] + t * t * c[6]
end
local function Heading(c, t)
  local u = 1 - t
  return math.atan2(2 * u * (c[4] - c[2]) + 2 * t * (c[6] - c[4]), 2 * u * (c[3] - c[1]) + 2 * t * (c[5] - c[3]))
end
local function Stroke(k, x1, y1, x2, y2)
  for _, l in ipairs({ cue.shade[k], cue.lines[k] }) do
    l:SetStartPoint("BOTTOMLEFT", cue, x1, y1)
    l:SetEndPoint("BOTTOMLEFT", cue, x2, y2)
    l:Show()
  end
end
local function DrawCue(p)
  local c, n = cue.curve, CUE.SEGMENTS
  for k = 1, n do
    local a = (k - 1) / n
    if a < p then
      local x1, y1 = Bez(c, a)
      local x2, y2 = Bez(c, math.min(k / n, p))
      Stroke(k, x1, y1, x2, y2)
    else
      cue.shade[k]:Hide()
      cue.lines[k]:Hide()
    end
  end
  local hx, hy = Bez(c, p)
  local back = Heading(c, p) + math.pi
  for side = 1, 2 do
    local a = back + (side == 1 and 0.5 or -0.5)
    Stroke(n + side, hx, hy, hx + CUE.HEAD * math.cos(a), hy + CUE.HEAD * math.sin(a))
  end
  for _, fs in ipairs(cue.letters) do fs:SetAlpha(p) end
end
local function PlaceWords(c)
  local pts, lens, flip = {}, { 0 }, c[1] > c[5]
  for i = 0, 40 do
    local x, y = Bez(c, flip and 1 - i / 40 or i / 40)
    pts[i + 1] = { x, y }
    if i > 0 then lens[i + 1] = lens[i] + math.sqrt((x - pts[i][1]) ^ 2 + (y - pts[i][2]) ^ 2) end
  end
  local widths, total = {}, 0
  for k, fs in ipairs(cue.letters) do
    widths[k] = math.max(fs:GetStringWidth() or 0, CUE.SPACE)
    total = total + widths[k]
  end
  local at = (lens[#lens] - total) / 2
  for k, fs in ipairs(cue.letters) do
    local s = at + widths[k] / 2
    at = at + widths[k]
    local i = 2
    while i < #lens and lens[i] < s do i = i + 1 end
    local f = math.min(1, math.max(0, (s - lens[i - 1]) / math.max(lens[i] - lens[i - 1], 1e-6)))
    local a, b = pts[i - 1], pts[i]
    local turn = math.atan2(b[2] - a[2], b[1] - a[1])
    fs:ClearAllPoints()
    fs:SetPoint("CENTER", cue, "BOTTOMLEFT", a[1] + (b[1] - a[1]) * f - math.sin(turn) * CUE.LIFT,
      a[2] + (b[2] - a[2]) * f + math.cos(turn) * CUE.LIFT)
    fs:SetRotation(turn)
  end
end
ns.OnTick(cue, "the quest item's cue", nil, function(self, dt)
  if not self.curve then return end
  self.t = (self.t or 0) + dt
  local t = self.t % CUE.AGAIN
  local p = math.min(1, t / CUE.GROW)
  DrawCue(1 - (1 - p) ^ 3)
  self:SetAlpha(t < CUE.GROW and 1 or 0.6 + 0.4 * (1 + math.cos((t - CUE.GROW) * 5)) / 2)
end)

function ui.UseNow()
  if not (itemButton:IsShown() and itemButton.link and not itemButton.along and card:IsShown() and ui.cardOpen ~= false)
     or ns.Ghost() then
    return 0
  end
  local g = ns.GuideInfo() or (ns.PastedGuide and ns.PastedGuide())
  local s = g and g.cur and g.steps[g.cur]
  if not (s and s.kind == "O") then return 0 end
  if Plain(Call(UnitExists, "target")) and not Plain(Call(UnitIsDead, "target")) and ui.StepWanted(g, s, "target") then
    return 1
  end
  if (s.mobs and #s.mobs > 0) or not s.wx or (s.ic and not PLACE_KINDS[s.ic]) then return 0 end
  local continent, px, py = ns.PlayerWorldPos()
  if continent ~= s.inst or not px or ns.Geo.Dist(s.wx, s.wy, px, py) > CUE.AT_YARDS then return 0 end
  return 2
end
function ui.UseCue()
  local state, b = ui.UseNow(), itemButton
  if state == 0 then
    b = ui.AlongUseNow()
    state, b = b and 1 or 0, b or itemButton
  end
  local bx, by, size = b.placedX, b.placedY, b.size or KEY_SIZE
  local left, top, scale, screen = card:GetLeft(), card:GetTop(), card:GetEffectiveScale(), UIParent:GetEffectiveScale()
  if state == 0 or not (bx and left and top and scale and screen) then
    ui.useState = 0
    cue.state, cue.key, cue.button = nil, nil, nil
    cue:Hide()
    cue.glowAt:Hide()
    return
  end
  ui.useState = b == itemButton and state or 0
  local k = scale / screen
  local fx, ftop = (left + card:GetWidth() - ui.FACE_IN - ui.FACE / 2) * k, (top - ui.faceDrop) * k + 2
  local cx, btop = bx - size / 2, by + 2
  local x0, y0, x1, y1 = cx, btop, fx, ftop
  if state == 2 then x0, y0, x1, y1 = fx, ftop, cx, btop end
  local curve = { x0, y0, (x0 + x1) / 2, math.max(y0, y1) + CUE.RISE + math.abs(x1 - x0) * 0.2, x1, y1 }
  local key = table.concat(curve, ",")
  if state ~= cue.state or b ~= cue.button then cue.t = 0 end
  cue.button = b
  if key ~= cue.key then
    cue.key, cue.curve = key, curve
    PlaceWords(curve)
  end
  cue.state = state
  cue:Show()
  if state == 2 then
    cue.glowAt:ClearAllPoints()
    cue.glowAt:SetPoint("CENTER", UIParent, "BOTTOMLEFT", cx, by - size / 2)
    cue.glowAt:Show()
  else
    cue.glowAt:Hide()
  end
end
ui.alongItems = {}
ns.guideAlongItems = ui.alongItems
local alongKey = nil
function ui.AlongItemLines()
  local out, seen = {}, {}
  if not (card:IsShown() and ui.cardOpen ~= false) or ns.Ghost() then return out end
  if itemButton:IsShown() and not itemButton.along and itemButton.link then seen[itemButton.link] = true end
  for _, a in ipairs(ui.alongShown or {}) do
    local index = Plain(Call(C_QuestLog.GetLogIndexForQuestID, a.s.ids[1]))
    local link, tex = nil, nil
    if index then link, tex = Call(GetQuestLogSpecialItemInfo, index) end
    link, tex = Plain(link), Plain(tex)
    if type(link) == "string" and not seen[link] then
      seen[link] = true
      out[#out + 1] = { s = a.s, row = a.row, link = link, tex = tex }
    end
  end
  return out
end
function ui.AlongItems()
  local list = ui.AlongItemLines()
  local links = {}
  for n, a in ipairs(list) do links[n] = a.link end
  local key = table.concat(links, "\n")
  if InCombatLockdown() then
    if key ~= alongKey then
      for _, b in ipairs(ui.alongItems) do b:SetAlpha(0); b.faded = true end
      alongKey = nil
    end
    return
  end
  for n, a in ipairs(list) do
    local b = ui.alongItems[n]
    if not b then
      b = SecureButton("IndexOfAzerothGuideAlongItem" .. n, "item", 134400)
      b:SetAttribute("ctrl-type1", nil)
      b:SetScript("OnEnter", function(self)
        if not self.link then return end
        GameTooltip:SetOwner(self, self.onRight and "ANCHOR_RIGHT" or "ANCHOR_LEFT")
        GameTooltip:SetHyperlink(self.link)
        GameTooltip:Show()
      end)
      b:SetScript("OnLeave", function() GameTooltip:Hide() end)
      ui.alongItems[n] = b
    end
    b.s, b.row = a.s, a.row
    if b.link ~= a.link then
      b:SetAttribute("item", a.link)
      b.link = a.link
      b.icon:SetTexture(a.tex or 134400)
    end
    b:SetAlpha(1)
    b.faded = nil
    b:Show()
  end
  for n = #list + 1, #ui.alongItems do
    local b = ui.alongItems[n]
    b.s, b.row, b.link = nil, nil, nil
    b:Hide()
  end
  alongKey = key
  ui.PlaceSecure()
end
function ui.PlaceAlongItems(screen)
  local first = ui.alongItems[1]
  if not (first and first:IsShown() and first.row) then return end
  local row, box = first.row, ns.guideAlongBox
  local top, h = row:GetTop(), row:GetHeight()
  local left, edge = card:GetLeft(), card:GetEffectiveScale()
  local scale = edge
  if not (top and scale and left and edge and screen) then return end
  local size = first.size or KEY_SIZE
  local mid = top - (h or 0) / 2
  local boxTop, boxBottom = box:GetTop(), box:GetBottom()
  if boxTop and boxBottom then mid = math.max(math.min(mid, boxTop), boxBottom) end
  local y = mid * scale / screen + size / 2
  local x = (left + card:GetWidth()) * edge / screen + ITEM_GAP + size
  local shown = 0
  for _, b in ipairs(ui.alongItems) do if b:IsShown() then shown = shown + 1 end end
  local right = UIParent:GetRight()
  local onRight = not (right and x + (shown - 1) * (size + ITEM_GAP) > right)
  for n = 1, shown do
    local b = ui.alongItems[n]
    local bx = x + (n - 1) * (size + ITEM_GAP)
    if not onRight then bx = left * edge / screen - ITEM_GAP - (n - 1) * (size + ITEM_GAP) end
    b.onRight = onRight
    if b.placedX ~= bx or b.placedY ~= y then
      b.placedX, b.placedY = bx, y
      b:ClearAllPoints()
      b:SetPoint("TOPRIGHT", UIParent, "BOTTOMLEFT", bx, y)
    end
  end
end
function ui.AlongUseNow()
  if not (card:IsShown() and ui.cardOpen ~= false) or ns.Ghost() then return nil end
  if not Plain(Call(UnitExists, "target")) or Plain(Call(UnitIsDead, "target")) then return nil end
  local g = ns.GuideInfo() or (ns.PastedGuide and ns.PastedGuide())
  for _, b in ipairs(ui.alongItems) do
    if b:IsShown() and b.link and b.s and not b.faded and ui.StepWanted(g, b.s, "target") then return b end
  end
end

function ns.GuideUseItem()
  local id = itemButton:IsShown() and not itemButton.along and type(itemButton.link) == "string"
    and tonumber(itemButton.link:match("item:(%d+)"))
  return id or nil, id and ui.useState or 0
end

do
  local REACH_EVERY = 0.2
  local talk = CreateFrame("Frame")
  ns.guideTalk = talk
  local function TalkKey(on, fight)
    if on == (ns.guideTalking or false) or (InCombatLockdown() and not fight) then return end
    Call(ClearOverrideBindings, talk)
    ns.guideTalking = false
    if on then
      for _, key in ipairs({ Call(GetBindingKey, KeyAction(targetButton)) }) do
        if Plain(key) then Call(SetOverrideBinding, talk, true, key, "INTERACTTARGET"); ns.guideTalking = true end
      end
    end
  end
  ns.On({ "PLAYER_REGEN_DISABLED" }, function() TalkKey(false, true) end)
  ns.OnTick(talk, "the Target key's reach", REACH_EVERY, function()
    local want = targetButton:IsShown() and targetButton.want
    local ours = want and (want.talk or want.talks) and Plain(Call(UnitExists, "target"))
      and not Plain(Call(UnitIsPlayer, "target")) and ui.Wanted(want, "target")
    TalkKey(ours and Plain(Call(CheckInteractDistance, "target", 3)) and true or false)
    local alongOn = ui.alongItems[1] and ui.alongItems[1]:IsShown()
    if alongOn and not (card:IsShown() and ui.cardOpen ~= false) then ui.AlongItems() end
    if targetButton:IsShown() or itemButton:IsShown() or alongOn then ui.PlaceSecure() end
    ui.UseCue()
  end)
end

local plates = {}
local plateUnits = {}
function ns.PlateUnits() return plateUnits end
local wanted, wantedFresh = {}, false
local logWanted = {}
local logDone = {}
local function Wanted()
  if wantedFresh then return end
  wantedFresh = true
  wipe(wanted)
  logWanted, logDone = {}, {}
  if ns.QuestLogWants then logWanted, logDone = ns.QuestLogWants() end
  logWanted, logDone = logWanted or {}, logDone or {}
  local g = ns.GuideInfo() or (ns.PastedGuide and ns.PastedGuide())
  local s = g and g.cur and g.steps[g.cur]
  if not s then return end
  local function add(questID, names)
    local open, named = {}, {}
    for _, o in ipairs(ns.QuestObjectives(questID)) do
      if type(o) == "table" then
        local text = Plain(o.text)
        local left = (Plain(o.numRequired) or 0) - (Plain(o.numFulfilled) or 0)
        local words = left > 0 and string.format("%d left", left) or "wanted"
        for _, n in ipairs(names or {}) do
          if type(text) == "string" and text:find(n, 1, true) then
            named[n] = true
            if not Plain(o.finished) and not wanted[n] then wanted[n] = words end
          end
        end
        if not Plain(o.finished) then open[#open + 1] = words end
      end
    end
    if #open == 1 then
      for _, n in ipairs(names or {}) do
        if not named[n] then wanted[n] = wanted[n] or open[1] end
      end
    end
  end
  if s.kind == "O" then
    local o = ns.StepObjective(s)
    if o then
      local words = ns.ObjectiveLeft(o)
      if words then
        for _, n in ipairs(s.mobs or {}) do
          if not wanted[n] then wanted[n] = words end
        end
      end
    else
      add(s.ids[1], s.mobs)
    end
  end
  if s.kind == "D" then
    for _, qm in ipairs(s.qmobs or {}) do add(qm.q, qm.m) end
    for _, b in ipairs(s.bosses or {}) do if b.q then wanted[b.n] = wanted[b.n] or "quest" end end
  end
end
function ui.LogKills()
  Wanted()
  return logWanted, logDone
end
function ui.Sorted(set)
  local out = {}
  for n in pairs(set or {}) do out[#out + 1] = n end
  table.sort(out)
  return out
end
ui.RUN_TIP = "Press this to target the run's quest mobs, a live mob first. If no quest mobs are left, the key targets the run's next boss."
function ui.RunWant(g, s, anchor)
  local track = ns.GuideBossTrack(g, s)
  if not track then return nil end
  Wanted()
  local mobs, taken, boss = {}, {}, nil
  local function take(name) if name and not taken[name] then taken[name], mobs[#mobs + 1] = true, name end end
  for _, qm in ipairs(s.qmobs or {}) do
    for _, name in ipairs(qm.m or {}) do if wanted[name] then take(name) end end
  end
  for _, b in ipairs(track) do if b.now then boss = b.name end end
  take(boss)
  local who = boss or mobs[1]
  return who and { who = who, mobs = mobs, boss = boss, anchor = anchor, tip = ui.RUN_TIP } or nil
end
local function Badge(plate)
  local b = plates[plate]
  if b then return b end
  b = CreateFrame("Frame", nil, plate, "BackdropTemplate")
  b:SetSize(56, 14)
  b:SetPoint("BOTTOM", plate, "TOP", 0, 2)
  b:SetBackdrop({ bgFile = WHITE, edgeFile = WHITE, edgeSize = 1 })
  b:SetBackdropColor(C.gold[1], C.gold[2], C.gold[3], 0.95)
  b:SetBackdropBorderColor(0, 0, 0, 1)
  b.text = b:CreateFontString(nil, "OVERLAY", "GameFontNormalSmall")
  b.text:SetPoint("CENTER")
  b.text:SetTextColor(0.06, 0.06, 0.06)
  plates[plate] = b
  return b
end
local function PlateOf(unit)
  return Call((C_NamePlate or {}).GetNamePlateForUnit, unit)
end
local grindMarks = {}
local GRIND_W, GRIND_H, GRIND_MORE = 40, 14, 6
local function GrindMark(plate)
  local m = grindMarks[plate]
  if m then return m end
  m = CreateFrame("Frame", nil, plate, "BackdropTemplate")
  m:SetBackdrop({ bgFile = WHITE, edgeFile = WHITE, edgeSize = 1 })
  m:SetBackdropColor(C.kill[1], C.kill[2], C.kill[3], 0.95)
  m:SetBackdropBorderColor(0, 0, 0, 1)
  m.text = m:CreateFontString(nil, "OVERLAY", "GameFontNormalSmall")
  m.text:SetPoint("CENTER")
  m.text:SetTextColor(C.bone[1], C.bone[2], C.bone[3])
  grindMarks[plate] = m
  return m
end
local grindWants, grindKey = {}, ""
local function GrindWants()
  local t = ns.TrackTarget and ns.TrackTarget("g")
  local mobs = t and t.mobs or {}
  local key = table.concat(mobs, ";")
  if key ~= grindKey then
    grindKey, grindWants = key, {}
    for _, n in ipairs(mobs) do grindWants[n] = true end
  end
  return grindWants
end
local function BadgeUnit(unit)
  local plate = PlateOf(unit)
  if not plate then return end
  local name = Plain(Call(UnitName, unit))
  local epic = not ns.platePreview and name and (wanted[name] or ns.MobLeft(name))
  local words = ns.platePreview and "4 left" or epic or (name and logWanted[name])
  local o = ns.Options and ns.Options().plateCount or { on = true, x = 0, y = 0 }
  local live = o.on and not Plain(Call(UnitIsDead, unit))
  local b = nil
  if words and live then
    b = Badge(plate)
    local c = epic and (ns.MobColour(name) or C.blue) or C.gold
    b:SetBackdropColor(c[1], c[2], c[3], 0.95)
    b:ClearAllPoints()
    b:SetPoint("BOTTOM", plate, "TOP", o.x, 2 + o.y)
    b.text:SetText(words)
    b:SetWidth(math.max(40, (b.text:GetStringWidth() or 40) + 10))
    b:Show()
  elseif plates[plate] then
    plates[plate]:Hide()
  end
  if live and (ns.platePreview or (name and GrindWants()[name])) then
    local m = GrindMark(plate)
    m:ClearAllPoints()
    if b then
      local level = b:GetFrameLevel() or 1
      m:SetFrameLevel(level); b:SetFrameLevel(level + 1)
      m.text:SetText("")
      m:SetSize(b:GetWidth() + GRIND_MORE, GRIND_H + GRIND_MORE)
      m:SetPoint("BOTTOM", plate, "TOP", o.x, 2 + o.y - GRIND_MORE / 2)
    else
      m.text:SetText("grind")
      m:SetSize(GRIND_W, GRIND_H)
      m:SetPoint("BOTTOM", plate, "TOP", o.x, 2 + o.y)
    end
    m:Show()
  elseif grindMarks[plate] then
    grindMarks[plate]:Hide()
  end
end
ns.grindMarks = grindMarks
function ui.Badges()
  Wanted()
  for unit in pairs(plateUnits) do BadgeUnit(unit) end
end
local INTERACT_REACH = { { 3, 10 }, { 2, 11 }, { 4, 28 } }
local MELEE_YARDS = 5
local spellReach = nil
local function SpellReach()
  if spellReach then return spellReach end
  spellReach = {}
  local seen = {}
  for _, sp in ipairs(HarmfulSpells()) do
    local info = sp.id and Call(C_Spell and C_Spell.GetSpellInfo, sp.id)
    local yards = type(info) == "table" and Plain(info.maxRange)
    if type(yards) == "number" then
      if yards <= 0 then yards = MELEE_YARDS end
      if not seen[yards] then
        seen[yards] = true
        spellReach[#spellReach + 1] = { id = sp.id, name = sp.name, yards = yards }
      end
    end
  end
  table.sort(spellReach, function(a, b) return a.yards < b.yards end)
  return spellReach
end
ns.On({ "SPELLS_CHANGED", "LEARNED_SPELL_IN_SKILL_LINE" }, function() spellReach = nil end)
local function SpellReaches(sp, unit)
  local r = Plain(Call(C_Spell and C_Spell.IsSpellInRange, sp.id, unit))
  if r == nil then r = Plain(Call(IsSpellInRange, sp.name, unit)) end
  return r == true or r == 1
end
function ui.MobYards(unit)
  if InCombatLockdown() then return math.huge end
  local best = math.huge
  for _, c in ipairs(INTERACT_REACH) do
    if c[2] < best and Plain(Call(CheckInteractDistance, unit, c[1])) then best = c[2] end
  end
  for _, sp in ipairs(SpellReach()) do
    if sp.yards >= best then break end
    if SpellReaches(sp, unit) then best = sp.yards end
  end
  return best
end
function ui.LivePlates(want)
  local found, tagged = {}, {}
  local cx, cy = UIParent:GetCenter()
  for unit in pairs(plateUnits) do
    local name = Plain(Call(UnitName, unit)) or ""
    if ui.Wanted(want, unit) and not Plain(Call(UnitIsDead, unit)) and Plain(Call(UnitCanAttack, "player", unit)) ~= false then
      if Tagged(unit) then
        tagged[name] = true
      else
        local plate = PlateOf(unit)
        local x, y = Call(plate and plate.GetCenter, plate)
        x, y = Plain(x), Plain(y)
        found[#found + 1] = { unit = unit, name = name, yards = ui.MobYards(unit), y = y or math.huge,
                              d = (x and y and cx) and ((x - cx) ^ 2 + (y - cy) ^ 2) or math.huge }
      end
    end
  end
  table.sort(found, function(a, b)
    if a.yards ~= b.yards then return a.yards > b.yards end
    if a.y ~= b.y then return a.y > b.y end
    if a.d ~= b.d then return a.d > b.d end
    return a.unit < b.unit
  end)
  local out = {}
  for k = math.max(1, #found - 2), #found do out[#out + 1] = found[k].unit end
  local near = found[#found]
  local alone = near and near.name
  for _, f in ipairs(found) do
    if f.yards == near.yards and f.name ~= alone then alone = nil end
  end
  return out, tagged, alone
end

do
  local MARK_WORDS = { [3] = "purple diamond", [5] = "moon" }
  local function PlateCounts(mobs, of)
    local want, live, tagged = {}, {}, {}
    for _, n in ipairs(mobs) do want[n] = true end
    for unit in pairs(plateUnits) do
      local name = Plain(Call(UnitName, unit))
      if name and want[name] and ui.Wanted(of, unit) and not Plain(Call(UnitIsDead, unit))
         and Plain(Call(UnitCanAttack, "player", unit)) ~= false then
        if Tagged(unit) then tagged[name] = (tagged[name] or 0) + 1 else live[name] = (live[name] or 0) + 1 end
      end
    end
    return live, tagged
  end
  local function MobWords(n, live, tagged)
    if live[n] then return string.format("%d in sight", live[n]) end
    if tagged[n] then return "tagged by someone else" end
    return "none in sight"
  end
  local function ItemName(id)
    local name = Plain(Call(C_Item and C_Item.GetItemNameByID, id)) or Plain(Call(GetItemInfo, id))
    return type(name) == "string" and name or ("item " .. id)
  end
  function ui.PressCasts(text)
    local out = {}
    for line in (text or ""):gmatch("[^\n]+") do
      local spell = line:match("^/cast %b[]%s*(.+)$") or line:match("^/cast%s+([^%[].*)$")
      local item = line:match("^/use %b[]%s*item:(%d+)") or line:match("^/use%s+item:(%d+)")
      if spell then out[#out + 1] = { "casts", (spell:gsub("%s*%(", " (")) } end
      if item then out[#out + 1] = { "uses", ItemName(tonumber(item)) } end
    end
    return out
  end
  function ui.TargetTipWho(b)
    local want = b.want
    if not want then return end
    local names = want.all or want.mobs or { want.who }
    local foes, enemy = want.foes or want.mobs or {}, {}
    for _, n in ipairs(foes) do enemy[n] = true end
    local live, tagged = PlateCounts(foes, want)
    local mark = KeyOptions().mark and ui.WantMark(want)
    local W, M = C.ivory, C.muted
    GameTooltip:AddLine(" ")
    GameTooltip:AddLine("Who the Target key targets", C.gold[1], C.gold[2], C.gold[3])
    for _, n in ipairs(names) do
      local words
      local step = want.targets and want.targets.spots[n]
      if step and want.targets.any then
        words = want.talk and "to talk to" or ""
      elseif step then
        local continent, px, py = ns.PlayerWorldPos()
        local yards = px and step.wx and step.inst == continent and ns.Geo.Dist(step.wx, step.wy, px, py)
        words = "still to do" .. (yards and string.format(", about %d yd", yards) or "")
      elseif enemy[n] then
        words = MobWords(n, live, tagged)
        if n == want.boss then words = "next boss, " .. words end
      else
        local over = n == want.who and MARK_WORDS[mark]
        words = "to talk to" .. (over and (", the " .. over) or "")
      end
      if #names > 1 and n == want.who then words = words ~= "" and ("next press, " .. words) or "next press" end
      GameTooltip:AddDoubleLine(n, words, W[1], W[2], W[3], M[1], M[2], M[3])
    end
    local casts = ui.PressCasts(b:GetAttribute("macrotext"))
    if #casts > 0 then
      GameTooltip:AddLine(" ")
      GameTooltip:AddLine("What the Target key casts", C.gold[1], C.gold[2], C.gold[3])
      for _, c in ipairs(casts) do
        GameTooltip:AddDoubleLine(c[2], c[1] == "casts" and "a spell, at the target" or "an item, on the target",
          W[1], W[2], W[3], M[1], M[2], M[3])
      end
    end
  end
end
local plateWatch = CreateFrame("Frame")
ns.plateWatch = plateWatch
local badgesLater = false
ns.On({ "NAME_PLATE_UNIT_ADDED", "NAME_PLATE_UNIT_REMOVED", "PLAYER_REGEN_ENABLED", "PLAYER_REGEN_DISABLED", "QUEST_LOG_UPDATE" },
      function(event, unit)
  if event == "PLAYER_REGEN_ENABLED" then
    if secureLater then ui.Secure() end
    return
  end
  if event == "PLAYER_REGEN_DISABLED" then
    ui.SlideDone()
    return ui.Secure()
  end
  if event == "QUEST_LOG_UPDATE" then wantedFresh, badgesLater = false, true; return end
  ui.platesMoved = true
  if event == "NAME_PLATE_UNIT_REMOVED" then
    plateUnits[unit or ""] = nil
    local plate = PlateOf(unit)
    if plate and plates[plate] then plates[plate]:Hide() end
    if plate and grindMarks[plate] then grindMarks[plate]:Hide() end
    return
  end
  if unit then plateUnits[unit] = true; Wanted(); BadgeUnit(unit) end
end)
ns.On({ "UNIT_FLAGS", "UNIT_FACTION" }, function(_, unit)
  if plateUnits[unit or ""] then ui.platesMoved = true end
end)
ns.OnTick(plateWatch, "the nameplates' marks", 0.5, function()
  local was = grindKey
  GrindWants()
  if grindKey ~= was then badgesLater = true end
  if badgesLater then
    badgesLater = false
    ui.Badges()
  end
  if ui.platesMoved and not InCombatLockdown() then
    ui.platesMoved = false
    if targetButton:IsShown() then ui.Secure() end
  end
end)
ns.OnGuide(function() wantedFresh = false; ui.Secure(); ui.Badges() end)
if ns.OnOptions then ns.OnOptions(function() ui.Badges(); ui.Render(); ui.Secure() end) end
ns.guideTarget, ns.guideItem = targetButton, itemButton

local PLATE_CVAR, PLATE_YARDS = "nameplateMaxDistance", 41
local distanceLater = false
local function PlateDistance()
  if not ns.plateReady then return end
  if InCombatLockdown() then distanceLater = true; return end
  distanceLater = false
  local cvar = C_CVar or {}
  local now = tonumber(Plain(Call(cvar.GetCVar, PLATE_CVAR)) or "")
  if not now then return end
  if ns.Options().plates.far then
    if now < PLATE_YARDS then
      IndexOfAzerothDB.ownPlateYards = now
      Call(cvar.SetCVar, PLATE_CVAR, tostring(PLATE_YARDS))
    end
  elseif IndexOfAzerothDB.ownPlateYards then
    if now == PLATE_YARDS then Call(cvar.SetCVar, PLATE_CVAR, tostring(IndexOfAzerothDB.ownPlateYards)) end
    IndexOfAzerothDB.ownPlateYards = nil
  end
end
ns.PlateDistance = PlateDistance
ns.On({ "PLAYER_ENTERING_WORLD", "VARIABLES_LOADED", "PLAYER_REGEN_ENABLED" }, function(event)
  if event == "VARIABLES_LOADED" then ns.plateReady = true end
  if event ~= "PLAYER_REGEN_ENABLED" or distanceLater then PlateDistance() end
end)
if ns.OnOptions then ns.OnOptions(PlateDistance) end

local FRIEND_CVARS = { { "nameplateShowFriends", "nameplateShowFriendlyPlayers" }, { "nameplateShowFriendlyNPCs" },
                       { "nameplateShowAll" } }
local FRIEND_ON = "1"
local friendTaken = false
local function FriendKept(name)
  local db = IndexOfAzerothDB
  if Plain(select(4, Call(C_CVar.GetCVarInfo, name))) then
    if type(IndexOfAzerothCharDB) ~= "table" then IndexOfAzerothCharDB = {} end
    db = IndexOfAzerothCharDB
  end
  if type(db.ownFriendPlates) ~= "table" then db.ownFriendPlates = {} end
  return db.ownFriendPlates
end
local function FriendOn()
  for _, names in ipairs(FRIEND_CVARS) do
    local name, now = nil, nil
    for _, n in ipairs(names) do
      now = Plain(Call(C_CVar.GetCVar, n))
      if now then name = n; break end
    end
    if now and now ~= FRIEND_ON then
      local kept = FriendKept(name)
      if kept[name] then
        kept[name], friendTaken = nil, true
      else
        kept[name] = now
        Call(C_CVar.SetCVar, name, FRIEND_ON)
        if Plain(Call(C_CVar.GetCVar, name)) ~= FRIEND_ON then kept[name] = nil end
      end
    end
  end
end
local function FriendBack()
  for _, db in ipairs({ IndexOfAzerothDB, IndexOfAzerothCharDB }) do
    local kept = type(db) == "table" and db.ownFriendPlates
    if type(kept) == "table" then
      for name, own in pairs(kept) do
        if Plain(Call(C_CVar.GetCVar, name)) == FRIEND_ON then Call(C_CVar.SetCVar, name, own) end
        if Plain(Call(C_CVar.GetCVar, name)) ~= FRIEND_ON then kept[name] = nil end
      end
      if next(kept) == nil then db.ownFriendPlates = nil end
    end
  end
end
local friendReady = false
local function FriendPlates(event)
  if event == "VARIABLES_LOADED" then friendReady = true end
  if not (friendReady and C_CVar) or InCombatLockdown() then return end
  local wanted = ns.FriendPlatesWanted and ns.FriendPlatesWanted()
  if not wanted then friendTaken = false end
  if wanted and not friendTaken and event ~= "PLAYER_LOGOUT" and ns.Options().plates.friends then FriendOn() else FriendBack() end
end
local friendWatch = CreateFrame("Frame")
ns.friendWatch = friendWatch
ns.OnTick(friendWatch, "the friendly nameplates", 0.2, function() FriendPlates() end)
ns.On({ "VARIABLES_LOADED", "PLAYER_LOGOUT" }, FriendPlates)
if ns.OnOptions then ns.OnOptions(FriendPlates) end

_G["BINDING_NAME_" .. KeyAction(targetButton)] = "Target any guide's NPC or mob"
_G["BINDING_NAME_" .. KeyAction(itemButton)] = "Use the quest epic's quest item"
