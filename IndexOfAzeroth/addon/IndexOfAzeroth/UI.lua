-- The Index of Azeroth. Copyright 2026 Index Case <indexofazeroth@pm.me>. PolyForm Strict 1.0.0, see LICENSE.md.
local ADDON, ns = ...

local WHITE = "Interface\\Buttons\\WHITE8X8"

local C = {
  bg = { 0.031, 0.090, 0.129, 0.9 }, panel = { 0.051, 0.141, 0.208, 1 }, row = { 0.063, 0.161, 0.235, 1 },
  rowOn = { 0.22, 0.34, 0.41, 1 }, edge = { 0.61, 0.44, 0.24, 1 }, dim = { 0.25, 0.25, 0.27, 1 },
  gold = { 1, 0.82, 0, token = "gold" }, cyan = { 0.32, 0.8, 0.93 }, ivory = { 0.97, 0.93, 0.85 },
  muted = { 0.62, 0.62, 0.62 }, green = { 0.4, 0.85, 0.35 }, red = { 1, 0.29, 0.24 }, yellow = { 1, 0.82, 0.25 },
  blue = { 0, 0.71, 1, token = "forever-blue" },
  kill = { 0.694, 0.247, 0.302, token = "kill-crimson" }, bone = { 0.945, 0.914, 0.863, token = "bone-white" },
  mining = { 0.247, 0.525, 0.839, token = "mining-blue" }, herbalism = { 0.490, 1, 0.561, token = "herbalism-leaf" },
  fishing = { 0.980, 0.541, 0.447, token = "fishing-salmon" }, treasure = { 0.659, 0.471, 0.047, token = "treasure-gold" },
  gather = { 0.702, 0.420, 1, token = "gather-purple" },
  skin = { 0.059, 0.541, 0.478, token = "skin-teal" },
}
local COLOUR_NAMES = ns.WordsOf("both.colours")
local function ColourName(colour) return COLOUR_NAMES[colour.token] end
local GUIDE = { go = C.gold, e = C.blue, g = C.kill, h = C.gather, k = C.skin,
                corpse = C.bone, npc = C.kill, xp = C.kill, farm = C.kill,
                mining = C.mining, herbalism = C.herbalism, fishing = C.fishing, treasure = C.treasure }

local MARKS = { farm = { art = "Interface\\MoneyFrame\\UI-GoldIcon" },
                npc = { spell = 1130, art = "Interface\\Icons\\Ability_Hunter_SniperShot" },
                xp = { words = "XP" } }

local function Skin(f, bg, edge)
  f:SetBackdrop({ bgFile = WHITE, edgeFile = WHITE, edgeSize = 1 })
  f:SetBackdropColor(unpack(bg or C.panel))
  f:SetBackdropBorderColor(unpack(edge or C.dim))
  return f
end

local function Panel(f) return Skin(f, C.bg, C.edge) end

local function Box(parent, bg, edge, strata)
  local f = Skin(CreateFrame("Frame", nil, parent, "BackdropTemplate"), bg, edge)
  if strata then f:SetFrameStrata(strata) end
  return f
end

local function Colored(c, words)
  local function byte(v) return math.floor(v * 255 + 0.5) end
  return string.format("|cff%02x%02x%02x%s|r", byte(c[1]), byte(c[2]), byte(c[3]), words)
end

local function Text(parent, font, color, justify)
  local t = parent:CreateFontString(nil, "OVERLAY", font or "GameFontHighlight")
  if color then t:SetTextColor(unpack(color)) end
  t:SetJustifyH(justify or "LEFT")
  t:SetWordWrap(true)
  return t
end

local function Cursor()
  local Plain, Call = ns.Plain, ns.Call
  local x, y = Call(GetCursorPosition)
  local scale = Plain(Call(UIParent.GetEffectiveScale, UIParent)) or 1
  x, y = Plain(x), Plain(y)
  if not (x and y) then return nil end
  return x / scale, y / scale
end

local function FlatButton(parent, label, width, onClick)
  local b = CreateFrame("Button", nil, parent, "BackdropTemplate")
  b:SetSize(width or 100, 24)
  b:SetBackdrop({ bgFile = WHITE, edgeFile = WHITE, edgeSize = 1 })
  b.label = Text(b, "GameFontNormal", C.gold, "CENTER")
  b.label:SetPoint("CENTER")
  b.label:SetText(label)
  function b:SetSelected(on)
    self.selected = on
    self:SetBackdropColor(unpack(on and C.rowOn or C.row))
    self:SetBackdropBorderColor(unpack(on and C.cyan or C.edge))
    self.label:SetTextColor(unpack(on and C.ivory or C.gold))
  end
  b:SetSelected(false)
  b:SetScript("OnEnter", function(self) if not self.selected then self:SetBackdropColor(0.18, 0.18, 0.19, 1) end end)
  b:SetScript("OnLeave", function(self) self:SetSelected(self.selected) end)
  b:SetScript("OnClick", onClick)
  return b
end

local function Scroller(parent)
  local s = CreateFrame("ScrollFrame", nil, parent)
  s.child = CreateFrame("Frame", nil, s)
  s.child:SetSize(1, 1)
  s:SetScrollChild(s.child)
  local bar = s:CreateTexture(nil, "OVERLAY")
  bar:SetColorTexture(C.edge[1], C.edge[2], C.edge[3], 0.8)
  bar:SetWidth(3)
  s:EnableMouseWheel(true)
  local function Update()
    local range = math.max(0, s.child:GetHeight() - s:GetHeight())
    local v = math.min(s:GetVerticalScroll() or 0, range)
    s:SetVerticalScroll(v)
    if range <= 0 then return bar:Hide() end
    local h = s:GetHeight()
    local size = math.max(20, h * h / s.child:GetHeight())
    bar:ClearAllPoints()
    bar:SetPoint("TOPRIGHT", s, "TOPRIGHT", 0, -(h - size) * v / range)
    bar:SetHeight(size)
    bar:Show()
  end
  s:SetScript("OnMouseWheel", function(self, delta)
    self:SetVerticalScroll(math.max(0, (self:GetVerticalScroll() or 0) - delta * 50))
    Update()
  end)
  s:SetScript("OnSizeChanged", function(self, w) self.child:SetWidth(w); Update() end)
  function s:Reset(height)
    self.child:SetHeight(math.max(1, height))
    self:SetVerticalScroll(0)
    Update()
  end
  function s:Fit(height)
    self.child:SetHeight(math.max(1, height))
    Update()
  end
  function s:ScrollTo(y)
    self:SetVerticalScroll(math.max(0, y))
    Update()
  end
  return s
end

local function SlideAlong(st, over, dt, how)
  st.phase, st.t, st.x = st.phase or "rest", (st.t or 0) + dt, st.x or 0
  if st.phase == "rest" then
    st.x = 0
    if st.t >= how.rest then st.phase, st.t = "out", 0 end
  elseif st.phase == "out" then
    st.x = math.min(over, st.x + how.speed * dt)
    if st.x >= over then st.phase, st.t = "hold", 0 end
  elseif st.phase == "hold" then
    st.x = math.min(st.x, over)
    if st.t >= how.hold then
      if how.back then st.phase, st.t = "home", 0 else st.phase, st.t, st.x = "rest", 0, 0 end
    end
  else
    st.x = math.max(0, st.x - how.speed * dt)
    if st.x <= 0 then st.phase, st.t = "rest", 0 end
  end
  return st.x
end

local Line = { HOW = { rest = 3, speed = 20, hold = 2, back = true }, ICON = 12, ICON_GAP = 4, KEY_GAP = 4 }
function Line.New(parent, font, color)
  local box = CreateFrame("Frame", nil, parent)
  local clip = CreateFrame("Frame", nil, box)
  if clip.SetClipsChildren then clip:SetClipsChildren(true) end
  local fs = Text(clip, font, color)
  fs:SetWordWrap(false)
  fs.icon = box:CreateTexture(nil, "ARTWORK")
  fs.icon:SetSize(Line.ICON, Line.ICON)
  fs.icon:Hide()
  fs.box, fs.clip, fs.slide = box, clip, { over = 0 }
  local show, hide = fs.Show, fs.Hide
  function fs:Show() box:Show(); show(self) end
  function fs:Hide() box:Hide(); hide(self) end
  function fs:SetShown(on) if on then self:Show() else self:Hide() end end
  return fs
end
function Line.Beside(fs, key, at, y)
  fs.key, fs.keyAt, fs.keyY = key, at, y or 0
end
function Line.Wrap(fs, on)
  fs.wraps = on and true or nil
  fs:SetWordWrap(on and true or false)
end
function Line.Icon(fs, art)
  if art then fs.icon:SetTexture(art) end
  fs.icon:SetShown(art ~= nil)
  fs.iconArt = art
end
function Line.Fit(fs)
  local box, clip, st = fs.box, fs.clip, fs.slide
  local inset = 0
  if fs.iconArt then
    local size = ns.PlainNumber((select(2, ns.Call(fs.GetFont, fs)))) or Line.ICON
    fs.icon:ClearAllPoints()
    fs.icon:SetPoint("TOPLEFT", box, "TOPLEFT", 0, -math.max(0, math.floor((size - Line.ICON) / 2)))
    inset = Line.ICON + Line.ICON_GAP
  end
  local room = 0
  if fs.key then
    fs.key:ClearAllPoints()
    fs.key:SetPoint(fs.keyAt, box, fs.keyAt, 0, fs.keyY)
    room = (ns.PlainNumber(ns.Call(fs.key.GetWidth, fs.key)) or 0) + Line.KEY_GAP
  end
  clip:ClearAllPoints()
  clip:SetPoint("TOPLEFT", box, "TOPLEFT", inset, 0)
  clip:SetPoint("TOPRIGHT", box, "TOPRIGHT", -room, 0)
  fs:ClearAllPoints()
  if fs.wraps then
    st.x, st.placed = 0, nil
    fs:SetPoint("TOPLEFT", clip, "TOPLEFT", 0, 0)
    fs:SetPoint("TOPRIGHT", clip, "TOPRIGHT", 0, 0)
  else
    fs:SetWidth(0)
    st.placed = st.x or 0
    fs:SetPoint("TOPLEFT", clip, "TOPLEFT", -st.placed, 0)
  end
  Line.High(fs)
end
function Line.High(fs)
  local Number, Call = ns.PlainNumber, ns.Call
  local high = Number(Call(fs.GetStringHeight, fs)) or 0
  if not fs.wraps then high = math.max(high, Number((select(2, Call(fs.GetFont, fs)))) or 0) end
  high = math.max(Line.ICON, math.ceil(high))
  fs.clip:SetHeight(high)
  fs.box:SetHeight(high)
end
function Line.Measure(fs)
  local st, Plain, Number, Call = fs.slide, ns.Plain, ns.PlainNumber, ns.Call
  local text = ns.PlainText(Call(fs.GetText, fs))
  if text ~= st.text then st.text, st.phase, st.t, st.x = text, "rest", 0, 0 end
  if fs.wraps or not Plain(Call(fs.IsVisible, fs)) then st.over = 0; return 0 end
  Line.High(fs)
  local full = Number(Call(fs.GetUnboundedStringWidth, fs)) or Number(Call(fs.GetStringWidth, fs)) or 0
  local box = Number(Call(fs.clip.GetWidth, fs.clip)) or 0
  st.over = box > 0 and math.max(0, full - box) or 0
  return st.over
end
function Line.Step(fs, dt, still)
  local st = fs.slide
  local x = 0
  if not still and st.over > 0 then x = SlideAlong(st, st.over, dt, Line.HOW) else st.phase, st.t, st.x = "rest", 0, 0 end
  if fs.wraps or st.placed == x then return end
  st.placed = x
  fs:SetPoint("TOPLEFT", fs.clip, "TOPLEFT", -x, 0)
end

local function Icon(art) return "|T" .. art .. ":12:12|t " end
local WARN_ART = (ns.Plain(ns.Call(GetFileIDFromPath, "Interface\\DialogFrame\\UI-Dialog-Icon-AlertNew")) or 0) > 0
  and "Interface\\DialogFrame\\UI-Dialog-Icon-AlertNew" or "Interface\\GossipFrame\\BattleMasterGossipIcon"

local function Circle(frame, segments, r, thickness)
  local lines = {}
  for k = 1, segments do
    local a1, a2 = (k - 1) / segments * 2 * math.pi, k / segments * 2 * math.pi
    local line = frame:CreateLine(nil, "OVERLAY")
    line:SetThickness(thickness)
    line:SetStartPoint("CENTER", frame, r * math.sin(a1), r * math.cos(a1))
    line:SetEndPoint("CENTER", frame, r * math.sin(a2), r * math.cos(a2))
    lines[k] = line
  end
  return lines
end

local function Pulse(f, colour, size)
  local p = CreateFrame("Frame", nil, f)
  p:SetPoint("CENTER", f, "CENTER")
  p:SetSize(size, size)
  p:SetFrameLevel(f:GetFrameLevel() + 1)
  p.glow = p:CreateTexture(nil, "OVERLAY")
  p.glow:SetAllPoints()
  p.glow:SetTexture("Interface\\Buttons\\UI-ActionButton-Border")
  p.glow:SetBlendMode("ADD")
  p.glow:SetVertexColor(colour[1], colour[2], colour[3])
  p.t = 0
  ns.OnTick(p, "a key's glow", nil, function(self, dt)
    self.t = self.t + dt
    self.glow:SetAlpha(0.2 + 0.8 * (1 + math.sin(self.t * 6)) / 2)
  end)
  p:Hide()
  return p
end

local function Mark(f, look, size, parent)
  local h = f.mark
  if not h then
    h = CreateFrame("Frame", nil, parent or f)
    h.art = h:CreateTexture(nil, "OVERLAY")
    h.art:SetAllPoints()
    h.words = h:CreateFontString(nil, "OVERLAY", "GameFontNormal")
    h.words:SetPoint("CENTER")
    h.words:SetTextColor(C.gold[1], C.gold[2], C.gold[3])
    f.mark = h
  end
  if h.look ~= look or h.size ~= size then
    h.look, h.size = look, size
    local m = MARKS[look]
    h:ClearAllPoints()
    h:SetPoint("CENTER", f, "TOPRIGHT", -size * 0.15, -size * 0.15)
    h:SetSize(size, size)
    h:SetFrameLevel((parent or f):GetFrameLevel() + 5)
    local art = m and (m.spell and ns.Plain(ns.Call(C_Spell and C_Spell.GetSpellTexture, m.spell)) or m.art)
    h.art:SetTexture(art)
    if m and m.spell then h.art:SetTexCoord(0.08, 0.92, 0.08, 0.92) else h.art:SetTexCoord(0, 1, 0, 1) end
    h.art:SetShown(art ~= nil)
    h.words:SetFontObject(size >= 12 and "GameFontNormal" or "GameFontNormalSmall")
    h.words:SetText(m and m.words or "")
    h.words:SetShown(m ~= nil and m.words ~= nil)
    h:SetShown(m ~= nil)
  end
  return h
end

local markTexts = {}
local function MarkText(look)
  local m = look and MARKS[look]
  if not m then return nil end
  if not markTexts[look] then
    local art = m.spell and ns.Plain(ns.Call(C_Spell and C_Spell.GetSpellTexture, m.spell)) or m.art
    markTexts[look] = m.words and Colored(C.gold, m.words) .. " " or "|T" .. tostring(art) .. ":0|t "
  end
  return markTexts[look]
end

local STOP_WORDS = {
  go = { colour = "go",
    "The trip is over. A dwarf asks if you need directions.",
    "The guide is done. A goblin is asking for a tip.",
    "You are here, or near enough. A gnome knew a shortcut.",
    "The road ends here. An orc asks what took you so long.",
    "The guide is over. A night elf says she knew the way." },
  corpse = { colour = "corpse",
    "You are alive again. The spirit healer sighs.",
    "You are back in your body. A Forsaken wants to know how.",
    "You live again. A priest of Stormwind wants a donation.",
    "You are on your feet again. A ghoul nearby looks let down.",
    "You are back. The Scourge will have to wait for you." },
  npc = { colour = "npc",
    "The hunt is over. A guard takes down the Wanted poster.",
    "You found your quarry. An SI:7 agent says he saw it first.",
    "The hunt is done. A troll hunter nods, which is praise.",
    "The stalking is over. A gnoll asks if he is next.",
    "The hunt is called off. Somewhere a murloc stops hiding." },
  xp = { colour = "xp",
    "The grind is done. The local wildlife holds a funeral.",
    "The killing is over. An orc thinks that is a pity.",
    "The loop is closed. The survivors tell their grandchildren.",
    "The grind is over. A gnoll is filing a complaint.",
    "Everything is killed. A troll says the respawns are lazy." },
  farm = { colour = "farm",
    "Your pockets are full. A goblin vendor rubs his hands.",
    "The farming is over. The auctioneers can smell you coming.",
    "The harvest is in. A banker in Ironforge clears a shelf.",
    "That is enough for today. A goblin counts your coin.",
    "The farm is done. A kobold eyes your bags hopefully." },
  mining = { colour = "mining",
    "The seam is worked out. A kobold wants his candle back.",
    "Your pick is shouldered. A dwarf says you missed a vein.",
    "The mining is done. A goblin wants to buy the lot.",
    "That is enough stone. The earthen will not miss it.",
    "Mining is over. The Venture Company wants its hill back." },
  herbalism = { colour = "herbalism",
    "Your basket is full. A druid looks at the meadow and sighs.",
    "The herbing is done. An alchemist is counting vials.",
    "The weeds are picked. A gnome gardener is relieved.",
    "You have enough leaves. The druids were starting to stare.",
    "Herbalism is over. A Tauren thanks you for leaving some." },
  fishing = { colour = "fishing",
    "Your line is in. The fish are telling tales about you.",
    "The fishing is over. Nat Pagle says he has seen bigger.",
    "You have stopped casting. The murlocs can come out now.",
    "The fishing is done. The one that got away sends regards.",
    "Your rod is away. A goblin says dynamite is quicker." },
  treasure = { colour = "treasure",
    "The chests are empty. A pirate is digging a new hole.",
    "The treasure hunt is over. A goblin wants his cut.",
    "Nothing is left to loot. A kobold checks behind you anyway.",
    "The hunt is done. A rogue says you missed one.",
    "The chests are all open. The Bloodsail will bury more." },
  h = { colour = "h",
    "The gathering is done. A druid asks the land to grow back.",
    "Your bags are full of bits. A goblin offers to buy the lot.",
    "That is enough picking. A Tauren says the earth needs rest.",
    "You are done gathering. A gnome asks what all that is for.",
    "The gathering is over. A kobold is taking the leftovers." },
  k = { colour = "k",
    "Your knife is away. A tanner in Thunder Bluff is pleased.",
    "The skinning is over. A Tauren asks you to wash your hands.",
    "That is the last pelt. A boar is glad to be ugly.",
    "You have enough hides. A leatherworker is already cutting.",
    "The skinning is done. The wolves of Elwynn hold a meeting." },
  dungeon = { colour = "e",
    "The dungeon is behind you. A boss respawns, bitter.",
    "The run is finished. The kobolds are already restocking.",
    "You are out of the dark. A dwarf asks if the sun hurts.",
    "The bosses are dealt with. The trash is filing a complaint.",
    "The dungeon is done. The innkeeper has your ale ready." },
  zone = { colour = "e",
    "The zone is done. The locals can solve their own problems.",
    "Every errand is run. The quest givers find new worries.",
    "The zone is seen to. A farmer already has a new problem.",
    "Nothing is left to fetch here. A murloc is relieved.",
    "The zone is wrapped up. The next mayor has a long list." },
  quest = { colour = "e",
    "Your quest log is clear. A quest giver looks worried.",
    "The quests are done. The innkeeper says to enjoy the quiet.",
    "Questing is over. Somewhere a farmer lost another sheep.",
    "The epic is closed. Even heroes need a sit down.",
    "That is the tale told. A bard is already making it longer." },
  camp = { colour = "e",
    "The camp is struck. A night elf wants the fire out.",
    "The fire is out. The wolves can have the clearing back.",
    "Camping is over. A Tauren says the stars will keep watch.",
    "Your tent is folded. A dwarf says it never fits the bag.",
    "The camp is gone. A gnoll moves into your spot." },
}
STOP_WORDS.g = STOP_WORDS.xp
local function EpicLook(key)
  key = tostring(key or "")
  if key:find("^zone:") then return "zone" end
  if key:find("^camp:") then return "camp" end
  if key ~= "" and key ~= "epic" and not key:find(":") then return "dungeon" end
  return "quest"
end
local lastStop = {}
local function SayStop(kind)
  local words = STOP_WORDS[kind]
  if not words then return nil end
  local n, last = #words, lastStop[words]
  local i = math.random(last and n - 1 or n)
  if last and i >= last then i = i + 1 end
  lastStop[words] = i
  if ns.Print then ns.Print(Colored(GUIDE[words.colour], words[i])) end
  return words[i]
end

ns.UI = { C = C, GUIDE = GUIDE, ColourName = ColourName, MARKS = MARKS, MarkText = MarkText, WHITE = WHITE, Skin = Skin, Panel = Panel, Box = Box,
          STOP_WORDS = STOP_WORDS, EpicLook = EpicLook, SayStop = SayStop,
          Text = Text, Colored = Colored, Cursor = Cursor,
          FlatButton = FlatButton, Scroller = Scroller, SlideAlong = SlideAlong, Line = Line, Circle = Circle, Icon = Icon, Mark = Mark, WARN_ART = WARN_ART,
          Pulse = Pulse }
