-- The Index of Azeroth. Copyright 2026 Index Case <indexofazeroth@pm.me>. PolyForm Strict 1.0.0, see LICENSE.md.
local ADDON, ns = ...
local UI, M = ns.UI, ns.Meter
local C, S = UI.C, M.Stats
local Plain, Call, Number, Text = ns.Plain, ns.Call, ns.PlainNumber, ns.PlainText
local T, Fill = ns.WordsOf("game.meter"), ns.Fill

local G = {
  SPAN = 60,
  W = 260, H = 130,
  LEAST_W = 240, LEAST_H = 96, MOST_W = 640, MOST_H = 400, FLOOR = 0.25,
  PAD = 8,
  INSET = 4,
  NUMBER_W = 44,
  BACK_ALPHA = 0.92,
  GHOST_ALPHA = 0.45,
  WORDS_AT = 0.6,
  CEILING_OF_AVG = 2, RECENT_FIGHTS = 20, CEILING_LEAST = 10, SCANNED = 500,
  LINGER = 5, FADE = 0.5,
}
M.Graph = G

local win, parts
local live = { ring = {}, fed = {}, kind = {}, alpha = 0 }

local function Num(n) return M.Num(n, true) end
local ONE = "%.1f"
local function One(n) return string.format(ONE, n) end

function G.Ceiling()
  local m, F = M.Store(), M.FIELD
  local level = Number(Call(UnitLevel, "player"))
  local at, any, nAt, nAny = 0, 0, 0, 0
  for i = m and #m.f or 0, math.max(1, (m and #m.f or 0) - G.SCANNED + 1), -1 do
    local fields = M.Unpack(m.f[i])
    if not M.Has(fields[F.flags], M.NO_DMG) and fields[F.len] >= M.SHORT then
      local dps = S.Dps(fields)
      if nAny < G.RECENT_FIGHTS then any, nAny = math.max(any, dps), nAny + 1 end
      if fields[F.lvl] == level and nAt < G.RECENT_FIGHTS then at, nAt = math.max(at, dps), nAt + 1 end
    end
  end
  return math.max(G.CEILING_LEAST, G.CEILING_OF_AVG * (nAt > 0 and at or any))
end
function G.Height(dps, ceiling)
  return math.min(1, math.max(0, dps / ceiling))
end

function G.Fit(w, h)
  w = math.max(G.LEAST_W * G.FLOOR, math.min(G.MOST_W, w))
  h = math.max(G.LEAST_H * G.FLOOR, math.min(G.MOST_H, h))
  local scale = math.max(G.FLOOR, math.min(1, w / G.LEAST_W, h / G.LEAST_H))
  return w, h, w / scale, h / scale, scale
end
local function Place(left, top, w, h)
  local _, _, ownW, ownH, scale = G.Fit(w, h)
  win:SetScale(scale)
  win:SetSize(ownW, ownH)
  win:ClearAllPoints()
  win:SetPoint("TOPLEFT", UIParent, "BOTTOMLEFT", left / scale, top / scale)
end
local function OnScreen()
  local scale = Number(Call(win.GetScale, win)) or 1
  local left, top = Number(Call(win.GetLeft, win)), Number(Call(win.GetTop, win))
  local w, h = Number(Call(win.GetWidth, win)), Number(Call(win.GetHeight, win))
  if not (left and top and w and h) then return nil end
  return left * scale, top * scale, w * scale, h * scale
end
local function Kept()
  local at = type(IndexOfAzerothCharDB) == "table" and IndexOfAzerothCharDB.meterGraph
  if type(at) ~= "table" then return nil end
  local left, top, w, h = tonumber(at[1]), tonumber(at[2]), tonumber(at[3]), tonumber(at[4])
  if not (left and top and w and h) then return nil end
  return left, top, w, h
end
local function Keep()
  local left, top, w, h = OnScreen()
  if not left or type(IndexOfAzerothCharDB) ~= "table" then return end
  w, h = G.Fit(w, h)
  Place(left, top, w, h)
  IndexOfAzerothCharDB.meterGraph = { math.floor(left + 0.5), math.floor(top + 0.5), math.floor(w + 0.5), math.floor(h + 0.5) }
end

function G.Shown(o, now)
  if not o.live then return false end
  if not o.combat or (live.fight and not live.over) then return true end
  return live.ended ~= nil and now - live.ended < G.LINGER
end
local function Wanted() return G.Shown(ns.Options().meter, Number(Call(GetTime)) or 0) end
local function Hold(want)
  parts.want, parts.mouse = want, want and not ns.Options().meter.lock
  win:EnableMouse(parts.mouse)
  win:SetMovable(parts.mouse)
  if not parts.mouse then parts.close:Hide(); parts.grip:Hide() end
end
local function Back()
  local a = ns.Options().meter.opacity / 100
  for _, s in ipairs({ { win, C.bg, C.edge }, { parts.chart, C.row, C.dim } }) do
    local f, bg, edge = s[1], s[2], s[3]
    f:SetBackdropColor(bg[1], bg[2], bg[3], (bg[4] or 1) * a)
    f:SetBackdropBorderColor(edge[1], edge[2], edge[3], (edge[4] or 1) * a)
  end
end

local function Draw()
  if not (win and win:IsShown()) then return end
  local w = Number(Call(win.GetWidth, win)) or G.W
  local h = Number(Call(win.GetHeight, win)) or G.H
  local chart = parts.chart
  chart:Resize(w - 2, h - 2)
  chart:Clear()
  local ghost = live.ghost
  local now = live.avg ~= nil or live.now ~= nil
  if live.avg then parts.avg:SetText(Fill(T["live.avg"], { dps = One(live.avg) })) end
  if ghost then parts.ghost:SetText(Fill(T["live.ghost"], { dps = One(ghost) })) end
  parts.avg:SetShown(now)
  parts.ghost:SetShown(ghost ~= nil)
  parts.ghost:ClearAllPoints()
  if now then
    parts.ghost:SetPoint("TOPRIGHT", parts.avg, "BOTTOMRIGHT", 0, -2)
  else
    parts.ghost:SetPoint("TOPRIGHT", chart, "TOPRIGHT", -G.INSET, -G.INSET)
  end
  local done, ceiling = live.done or 0, live.ceiling or G.CEILING_LEAST
  local n = math.min(done, G.SPAN)
  local values, fed, any = {}, {}, false
  for i = 1, n do
    local second = done - n + i
    values[i], fed[i] = live.ring[second], live.fed[second] == true
    any = any or fed[i]
  end
  local empty = live.fight == nil
  local x = any and chart:Bars(values, fed, n, G.SPAN, ceiling, 1, C.gold, C.gold) or 0
  local low = ghost and chart:Level(G.Height(ghost, ceiling), 1, C.ivory, 0.9, C.bg) or nil
  parts.lastLine:SetShown(low ~= nil)
  if low then
    local labelH = math.ceil(Number(Call(parts.lastLine.GetStringHeight, parts.lastLine)) or 10)
    local titleH = math.ceil(Number(Call(parts.title.GetStringHeight, parts.title)) or 10)
    parts.lastLine:ClearAllPoints()
    if low + 2 + labelH > h - 2 - G.INSET - titleH - 2 then
      parts.lastLine:SetPoint("TOPLEFT", chart, "BOTTOMLEFT", G.INSET, low - 3)
    else
      parts.lastLine:SetPoint("BOTTOMLEFT", chart, "BOTTOMLEFT", G.INSET, low + 2)
    end
  end
  local at = (h - 2) * G.WORDS_AT
  parts.empty:SetShown(empty)
  parts.none:SetShown(not empty and not any)
  for _, t in ipairs({ parts.empty, parts.none }) do
    t:ClearAllPoints()
    t:SetPoint("TOPLEFT", chart, "BOTTOMLEFT", G.INSET, at)
    t:SetPoint("TOPRIGHT", chart, "BOTTOMRIGHT", -G.INSET, at)
  end
  parts.number:SetShown(any and fed[n] == true)
  if fed[n] then
    parts.number:ClearAllPoints()
    if x + G.NUMBER_W <= w - 2 then
      parts.number:SetPoint("TOPLEFT", chart, "BOTTOMLEFT", x + 4, at)
    else
      parts.number:SetPoint("TOPRIGHT", chart, "BOTTOMLEFT", x - (w - 2) / G.SPAN - 3, at)
    end
    if live.kind[done] == "game" then
      parts.number:SetFormattedText(ONE, values[n])
    else
      parts.number:SetText(One(values[n]))
    end
  end
  for _, t in ipairs(parts.labels) do t.back:SetShown(t:IsShown()) end
end

local function Got(v) return (issecretvalue and issecretvalue(v)) or v ~= nil end
function G.Sealed()
  local types, kinds = Enum and Enum.DamageMeterSessionType, Enum and Enum.DamageMeterType
  if not (live.meter and C_DamageMeter and types and kinds) then return nil end
  return Call(function()
    local session = C_DamageMeter.GetCombatSessionFromType(types.Current, kinds.Dps)
    for _, source in ipairs(session.combatSources) do
      if Plain(source.isLocalPlayer) == true then return source.amountPerSecond, source.totalAmount end
    end
  end)
end
local function GameDps()
  if live.meter then
    local value = G.Sealed()
    if Got(value) then return value end
  end
end

local function Figure(f, elapsed)
  if live.due then
    live.due = false
    live.game = GameDps()
  end
  if Got(live.game) then return live.game, "game" end
  if f.hidden == 0 then return S.Rate(f.seen, elapsed), "own" end
end

local function Second(f, done)
  local elapsed = (Number(Call(GetTime)) or f.t0) - f.t0
  local value, kind = Figure(f, elapsed)
  live.ring[done], live.fed[done], live.kind[done] = value, kind ~= nil, kind
  live.ring[done - G.SPAN], live.fed[done - G.SPAN], live.kind[done - G.SPAN] = nil, nil, nil
  live.now = kind
  if kind == "game" then
    parts.avg:SetFormattedText(Fill(T["live.now"], { dps = ONE }), value)
  elseif kind then
    parts.avg:SetText(Fill(T["live.now"], { dps = One(value) }))
  end
end

local function Build()
  win = UI.Panel(CreateFrame("Frame", "IndexOfAzerothMeterGraph", UIParent, "BackdropTemplate"))
  win:SetFrameStrata("MEDIUM")
  win:SetClampedToScreen(true)
  win:RegisterForDrag("LeftButton")
  win:SetScript("OnDragStart", function(self) self:StartMoving() end)
  win:SetScript("OnDragStop", function(self) self:StopMovingOrSizing(); Keep() end)
  local left, top, w, h = Kept()
  if left then
    Place(left, top, w, h)
  else
    win:SetSize(G.W, G.H)
    win:SetPoint("CENTER", UIParent, "CENTER", 0, -220)
  end
  parts = { labels = {} }
  parts.chart = UI.Chart(win, G.W - 2, G.H - 2)
  parts.chart:SetPoint("TOPLEFT", win, "TOPLEFT", 1, -1)
  local over = CreateFrame("Frame", nil, parts.chart)
  over:SetAllPoints(parts.chart)
  over:SetFrameLevel((Number(Call(parts.chart.GetFrameLevel, parts.chart)) or 1) + 5)
  parts.over = over
  local function Label(font, color, justify, wrap)
    local t = UI.Text(over, font, color, justify)
    t:SetWordWrap(wrap == true)
    t.back = over:CreateTexture(nil, "BACKGROUND")
    t.back:SetColorTexture(C.row[1], C.row[2], C.row[3], G.BACK_ALPHA)
    t.back:SetPoint("TOPLEFT", t, "TOPLEFT", -2, 1)
    t.back:SetPoint("BOTTOMRIGHT", t, "BOTTOMRIGHT", 2, -1)
    parts.labels[#parts.labels + 1] = t
    return t
  end
  parts.title = Label("GameFontNormalSmall", C.gold)
  parts.title:SetPoint("TOPLEFT", parts.chart, "TOPLEFT", G.INSET, -G.INSET)
  parts.title:SetText(T["live.title"])
  parts.avg = Label("GameFontHighlightSmall", C.ivory, "RIGHT")
  parts.avg:SetPoint("TOPRIGHT", parts.chart, "TOPRIGHT", -G.INSET, -G.INSET)
  parts.ghost = Label("GameFontHighlightSmall", C.muted, "RIGHT")
  parts.ghost:SetAlpha(G.GHOST_ALPHA + 0.25)
  parts.number = Label("GameFontNormal", C.gold)
  parts.lastLine = Label("GameFontHighlightSmall", C.muted)
  parts.lastLine:SetAlpha(G.GHOST_ALPHA + 0.25)
  parts.lastLine:SetText(T["live.line.last"])
  parts.none = Label("GameFontHighlightSmall", C.muted, "CENTER", true)
  parts.none:SetText(T["live.none"])
  parts.empty = Label("GameFontHighlightSmall", C.muted, "CENTER", true)
  parts.empty:SetText(T["live.empty"])

  local close = UI.FlatButton(win, "x", 14, function() M.Live("off") end)
  close:SetSize(14, 14)
  close:SetPoint("TOPRIGHT", win, "TOPRIGHT", -1, -1)
  close:SetFrameLevel((Number(Call(win.GetFrameLevel, win)) or 1) + 10)
  close:HookScript("OnEnter", function(self)
    GameTooltip:SetOwner(self, "ANCHOR_TOP")
    GameTooltip:AddLine(T["live.close"], 1, 1, 1, true)
    GameTooltip:Show()
  end)
  close:HookScript("OnLeave", function() GameTooltip:Hide() end)
  parts.close = close
  local grip = CreateFrame("Button", nil, win)
  grip:SetSize(14, 14)
  grip:SetPoint("BOTTOMRIGHT", win, "BOTTOMRIGHT", -1, 1)
  grip:SetFrameLevel((Number(Call(win.GetFrameLevel, win)) or 1) + 10)
  grip:SetNormalTexture("Interface\\ChatFrame\\UI-ChatIM-SizeGrabber-Up")
  grip:SetHighlightTexture("Interface\\ChatFrame\\UI-ChatIM-SizeGrabber-Highlight")
  grip:SetPushedTexture("Interface\\ChatFrame\\UI-ChatIM-SizeGrabber-Down")
  grip:SetScript("OnMouseDown", function()
    local x, y = UI.Cursor()
    local left0, top0, w0, h0 = OnScreen()
    if not (x and left0) then return end
    parts.sizing = true
    ns.OnTick(grip, T["part.live"], nil, function()
      local cx, cy = UI.Cursor()
      if cx then Place(left0, top0, G.Fit(w0 + cx - x, h0 + y - cy)) end
    end)
  end)
  grip:SetScript("OnMouseUp", function()
    grip:SetScript("OnUpdate", nil)
    parts.sizing = nil
    Keep()
    Draw()
  end)
  parts.grip = grip
  close:Hide()
  grip:Hide()
  win:SetScript("OnSizeChanged", function() Draw() end)

  ns.OnTick(win, T["part.live"], nil, function(_, dt)
    local want = Wanted()
    if want ~= parts.want then Hold(want) end
    local alpha = math.max(0, math.min(1, live.alpha + (want and dt or -dt) / G.FADE))
    if alpha ~= live.alpha then
      live.alpha = alpha
      win:SetAlpha(alpha)
    end
    if alpha == 0 and not want then win:Hide(); return end
    local hover = parts.mouse and (parts.sizing or Plain(Call(win.IsMouseOver, win)) == true)
    close:SetShown(hover)
    grip:SetShown(hover)
    local f = live.fight
    if not f or live.over then return end
    local done = math.max(0, math.floor((Number(Call(GetTime)) or f.t0) - f.t0))
    if done == live.done then return end
    live.done = done
    if done > 0 then Second(f, done) end
    Draw()
  end)
  win:Hide()
end

local function Follow()
  local o, want = ns.Options().meter, Wanted()
  if want and not win then Build() end
  if not win then return end
  Back()
  Hold(want)
  if want and not win:IsShown() then
    live.alpha = 0
    win:SetAlpha(0)
    win:Show()
    Draw()
  elseif not o.live then
    win:Hide()
  end
end
ns.OnOptions(Follow)
function M.Live(arg)
  local o = ns.Options().meter
  o.live = arg == "on" or (arg ~= "off" and not o.live)
  ns.OptionsChanged()
  ns.Print(ns.SwitchWords(ns.Word("game.chat.switch.name.live"), o.live, T["live.command"]))
end
local function Meter() return Plain(Call(C_DamageMeter and C_DamageMeter.IsDamageMeterAvailable)) == true end
ns.On("PLAYER_LOGIN", function()
  live.meter, live.ceiling = Meter(), G.Ceiling()
  Follow()
end)
ns.On("DAMAGE_METER_COMBAT_SESSION_UPDATED", function() live.due = true end)

M.Listen(function(what, f, a, b)
  if what == "start" then
    live.ghost = live.last and live.last > 0 and live.last or nil
    live.fight, live.avg, live.last, live.over, live.done, live.now, live.due, live.game = f, nil, nil, false, nil, nil, false, nil
    live.ring, live.fed, live.kind = {}, {}, {}
    live.meter = Meter()
    live.ceiling = G.Ceiling()
    live.ended = nil
    Follow()
    Draw()
  elseif what == "finish" and f == live.fight then
    live.over, live.now, live.ended = true, nil, Number(Call(GetTime))
    Draw()
  elseif what == "figures" and f == live.fight then
    live.avg = a and S.Rate(a, b) or nil
    live.last = live.avg
    Draw()
  end
end, "start", "finish", "figures")

local P = { BARS = 20, BAR_H = 100, ring = {}, n = 0, kept = 0, ok = 0, threw = 0, reads = {}, since = 0,
            RING = 2000,
            POLL_MS = 10000,
            CLAMP = { 1, 10, 100, 1000, 10000 },
            BIG = 2147483647,
            PLATES = 40,
            CAST_MS = 3000,
            KEYS_SHOWN = 4, SPELLS_SHOWN = 5, CHANGES_SHOWN = 6,
            RECENT = 5,
            fired = 0, minmaxed = 0, sized = 0 }
G.probe = P
P.WAYS = { "value", "height", "edges", "rect", "texcoord" }
P.EVENTS = { "UNIT_THREAT_LIST_UPDATE", "UNIT_COMBAT", "PLAYER_SWING", "UNIT_SPELLCAST_SUCCEEDED",
             "DAMAGE_METER_COMBAT_SESSION_UPDATED", "DAMAGE_METER_CURRENT_SESSION_UPDATED",
             "ADDON_RESTRICTION_STATE_CHANGED", "COMBAT_LOG_MESSAGE" }
P.FIELDS = { "clock", "session", "length", "sources", "row", "total", "death", "creature", "spells", "spell",
             "spelltotal", "sessions", "last", "before" }

local function Ceiling(f)
  local top = 0
  for _, amount in pairs(f.line) do top = math.max(top, amount) end
  return top > 0 and 2 * top or 100, f.seen > 0 and 2 * f.seen or 1000
end

local function Kind(ok, v)
  if not ok then return "error", nil, (tostring(v):match("^[^\n]*")) end
  if issecretvalue and issecretvalue(v) then return "secret" end
  if type(v) == "number" then return "plain", v end
  return "none"
end
local READ = {
  value = function(bar) return Kind(pcall(bar.GetValue, bar)) end,
  height = function(_, fill, ceiling)
    local kind, h, err = Kind(pcall(fill.GetHeight, fill))
    return kind, kind == "plain" and h / P.BAR_H * ceiling or nil, err
  end,
  edges = function(_, fill, ceiling)
    local kind, top, err = Kind(pcall(fill.GetTop, fill))
    if kind ~= "plain" then return kind, nil, err end
    local kind2, bottom, err2 = Kind(pcall(fill.GetBottom, fill))
    if kind2 ~= "plain" then return kind2, nil, err2 end
    return "plain", (top - bottom) / P.BAR_H * ceiling
  end,
  rect = function(_, fill, ceiling)
    local ok, first, _, _, h = pcall(fill.GetRect, fill)
    if not ok then return Kind(false, first) end
    local kind, high = Kind(true, h)
    return kind, kind == "plain" and high / P.BAR_H * ceiling or nil
  end,
  texcoord = function(_, fill, ceiling)
    local ok, first, top = pcall(fill.GetTexCoord, fill)
    if not ok then return Kind(false, first) end
    local kind, y = Kind(true, top)
    return kind, kind == "plain" and (1 - y) * ceiling or nil
  end,
}
local function ReadBack(what, bar, ceiling)
  local got = Call(bar.GetStatusBarTexture, bar)
  local reads = {}
  for _, way in ipairs(P.WAYS) do
    if got == nil and way ~= "value" then
      reads[way] = { "error", nil, T["probe.nofill"] }
    else
      local ok, kind, n, err = pcall(READ[way], bar, got, ceiling)
      reads[way] = ok and { kind, n, err } or { "error", nil, (tostring(kind):match("^[^\n]*")) }
    end
  end
  P.reads[what] = reads
end

function P.Lines()
  local lines = { Fill(T["probe.result"], { kept = P.kept, ok = P.ok, threw = P.threw }) }
  if P.err then lines[#lines + 1] = Fill(T["probe.error"], { err = P.err }) end
  for _, what in ipairs({ "dps", "total" }) do
    local got = P.reads[what]
    if got then
      local ways = {}
      for _, way in ipairs(P.WAYS) do
        local r = got[way]
        ways[#ways + 1] = r and Fill(T["probe.read." .. r[1]], { way = T["probe.way." .. way], n = r[2] and Num(r[2]),
                                                               err = r[3] or "?" }) or nil
      end
      lines[#lines + 1] = Fill(T["probe.readback"], { what = T["probe.what." .. what], ways = table.concat(ways, ", ") })
    end
  end
  return lines
end

function P.Step(f)
  local value, total = G.Sealed()
  if Got(value) then
    P.ring[P.n % P.BARS + 1] = value
    P.n, P.kept = P.n + 1, P.kept + 1
  end
  local ceiling, totalCeiling = Ceiling(f)
  local filled = math.min(P.n, P.BARS)
  for i, bar in ipairs(P.bars) do
    local at = i <= filled and ((P.n - filled + i - 1) % P.BARS + 1) or nil
    pcall(bar.SetMinMaxValues, bar, 0, ceiling)
    local ok, err = pcall(bar.SetValue, bar, at and P.ring[at] or 0)
    if ok then P.ok = P.ok + 1 else
      P.threw = P.threw + 1
      P.err = P.err or tostring(err)
    end
  end
  if filled > 0 then ReadBack("dps", P.bars[filled], ceiling) end
  if Got(total) then
    pcall(P.total.SetMinMaxValues, P.total, 0, totalCeiling)
    if pcall(P.total.SetValue, P.total, total) then ReadBack("total", P.total, totalCeiling) end
  end
  if Got(value) and Got(total) then
    pcall(P.game.SetFormattedText, P.game, Fill(T["probe.game"], { dps = "%s", total = "%s" }),
          Call(AbbreviateNumbers, value), Call(AbbreviateNumbers, total))
  end
  P.line:SetText(table.concat(P.Lines(), "\n"))
  return total
end

local function BuildProbe()
  local f = UI.Panel(CreateFrame("Frame", "IndexOfAzerothMeterProbe", UIParent, "BackdropTemplate"))
  f:SetSize(2 * G.PAD + (P.BARS + 2) * 10 + 160, 250)
  f:SetPoint("CENTER", UIParent, "CENTER", 0, 120)
  f:SetFrameStrata("MEDIUM")
  f:SetMovable(true)
  f:EnableMouse(true)
  f:RegisterForDrag("LeftButton")
  f:SetScript("OnDragStart", function(self) self:StartMoving() end)
  f:SetScript("OnDragStop", function(self) self:StopMovingOrSizing() end)
  local title = UI.Text(f, "GameFontNormalSmall", C.gold)
  title:SetPoint("TOPLEFT", f, "TOPLEFT", G.PAD, -7)
  title:SetText(T["probe.title"])
  P.bars = {}
  for i = 1, P.BARS do
    local bar = CreateFrame("StatusBar", nil, f)
    bar:SetOrientation("VERTICAL")
    bar:SetStatusBarTexture(UI.WHITE)
    bar:SetStatusBarColor(C.gold[1], C.gold[2], C.gold[3])
    bar:SetSize(8, P.BAR_H)
    bar:SetPoint("TOPLEFT", f, "TOPLEFT", G.PAD + (i - 1) * 10, -24)
    P.bars[i] = bar
  end
  P.total = CreateFrame("StatusBar", nil, f)
  P.total:SetOrientation("VERTICAL")
  P.total:SetStatusBarTexture(UI.WHITE)
  P.total:SetStatusBarColor(C.cyan[1], C.cyan[2], C.cyan[3])
  P.total:SetSize(8, P.BAR_H)
  P.total:SetPoint("TOPLEFT", f, "TOPLEFT", G.PAD + (P.BARS + 1) * 10, -24)
  P.game = UI.Text(f, "GameFontHighlightSmall", C.gold)
  P.game:SetPoint("TOPLEFT", f, "TOPLEFT", G.PAD + (P.BARS + 3) * 10, -24)
  P.game:SetWidth(150)
  P.line = UI.Text(f, "GameFontHighlightSmall", C.ivory)
  P.line:SetPoint("TOPLEFT", f, "TOPLEFT", G.PAD, -30 - P.BAR_H)
  P.line:SetWidth((P.BARS + 2) * 10 + 150)
  P.line:SetText(T["probe.waiting"])

  local x0 = G.PAD + (P.BARS + 3) * 10
  P.digits = UI.Text(f, "GameFontHighlightSmall", C.ivory)
  P.fontKind = pcall(P.digits.SetFont, P.digits, "Fonts\\ARIALN.TTF", 14, "MONOCHROME") and "ok" or "error"
  P.digits:SetPoint("TOPLEFT", f, "TOPLEFT", x0, -54)
  local key = UI.Text(f, "GameFontHighlightSmall", C.ivory)
  pcall(key.SetFont, key, "Fonts\\ARIALN.TTF", 14, "MONOCHROME")
  key:SetPoint("TOPLEFT", f, "TOPLEFT", x0, -70)
  key:SetText("0123456789")
  P.sprite = f:CreateTexture(nil, "ARTWORK")
  P.sprite:SetTexture("Interface\\Icons\\INV_Misc_QuestionMark")
  P.sprite:SetSize(14, 14)
  P.sprite:SetPoint("TOPLEFT", f, "TOPLEFT", x0, -90)
  P.sizeText = UI.Text(f, "GameFontHighlightSmall", C.muted)
  P.sizeText:SetPoint("TOPLEFT", f, "TOPLEFT", x0 + 20, -90)
  local box = CreateFrame("Frame", nil, f)
  box:SetPoint("TOPLEFT", P.sizeText, "TOPLEFT")
  box:SetPoint("BOTTOMRIGHT", P.sizeText, "BOTTOMRIGHT")
  box:SetScript("OnSizeChanged", function() P.sized = P.sized + 1 end)
  P.zero = UI.Text(f, "GameFontHighlightSmall", C.muted)
  P.zero:Hide()
  P.bitBar = CreateFrame("StatusBar", nil, f)
  P.bitBar:SetStatusBarTexture(UI.WHITE)
  P.bitBar:SetStatusBarColor(C.muted[1], C.muted[2], C.muted[3])
  P.bitBar:SetSize(40, 6)
  P.bitBar:SetPoint("TOPLEFT", f, "TOPLEFT", x0 + 100, -94)
  P.bitBar:SetScript("OnValueChanged", function() P.fired = P.fired + 1 end)
  P.bitBar:SetScript("OnMinMaxChanged", function() P.minmaxed = P.minmaxed + 1 end)
  P.logText = UI.Text(f, "GameFontHighlightSmall", C.muted)
  P.logText:SetPoint("BOTTOMLEFT", f, "BOTTOMLEFT", G.PAD, G.PAD)
  P.logText:SetWidth((P.BARS + 2) * 10 + 150)
  Call(P.logText.SetMaxLines, P.logText, 2)

  ns.OnTick(f, T["part.probe"], nil, function(_, dt)
    local q = P.q
    if q and q.polling then P.Poll(q) end
    if q and not q.over then P.Threat(q, Number(Call(GetTime)) or 0, Number(Call(debugprofilestop)) or 0) end
    P.since = P.since + (dt or 0)
    if P.since < 1 then return end
    P.since = 0
    local fight = live.fight
    if not fight or live.over then return end
    local total = P.Step(fight)
    if q and not q.over then P.Second(q, total) end
  end)
  P.frame = f
end


local function Secret(v) return (issecretvalue and issecretvalue(v)) and true or false end
local function KindOf(ok, v)
  if not ok then return "error", nil, (tostring(v):match("^[^\n]*")) end
  if Secret(v) then return "secret" end
  if v == nil then return "none" end
  return "plain", v
end
local function Tick(t, kind) t[kind] = (t[kind] or 0) + 1 end
local function Note(q, t, ok, v)
  local kind, plain, err = KindOf(ok, v)
  Tick(t, kind)
  if err and not q.err then q.err = err end
  return kind, plain
end
local function Tally(t)
  local kinds = {}
  for kind in pairs(t) do kinds[#kinds + 1] = kind end
  if #kinds == 0 then return T["probe.unread"] end
  table.sort(kinds)
  local out = {}
  for i, kind in ipairs(kinds) do out[i] = (T["probe.kind." .. kind] or kind) .. " " .. t[kind] end
  return table.concat(out, " / ")
end
local function Median(list)
  if #list == 0 then return nil end
  local sorted = {}
  for i, v in ipairs(list) do sorted[i] = v end
  table.sort(sorted)
  return sorted[math.floor((#sorted + 1) / 2)]
end
local function Ms(v) return v and string.format("%d", math.floor(v + 0.5)) or T["probe.na"] end
local function Ratio(v) return v and string.format("%.2f", v) or T["probe.na"] end
local function Exists(unit) return Plain(Call(UnitExists, unit)) and true or false end
local function TokenKind(unit)
  if Secret(unit) then return "secret" end
  if type(unit) ~= "string" then return "none" end
  return unit:match("^(%a-)%d+$") or unit
end

function P.Fresh()
  local q = { t0 = Number(Call(GetTime)) or 0, ring = {}, rn = 0, counts = {}, most = {}, sec = {}, at = {},
              th = { target = {}, plates = {}, boss = {}, pet = {}, pred = {} }, meter = {}, last = {},
              rise = 0, dmg = 0, hits = 0, casts = 0, changes = 0, tokens = {}, secretAmounts = 0, restr = {},
              log = { n = 0 }, trunc = {}, zeroGet = {}, zeroTruth = {}, changed = {}, minmax = {}, anchorFill = {},
              anchorText = {}, str = {}, fmt = {}, round = {}, breakup = {}, sprite = {}, bitSecs = 0, sized0 = P.sized,
              recent = {}, cond = {} }
  for _, field in ipairs(P.FIELDS) do q.meter[field] = {} end
  return q
end

local function Ring(q, e)
  q.rn = q.rn + 1
  q.ring[(q.rn - 1) % P.RING + 1] = e
end

local function ThreatRead(q, t, unit, mob)
  local ok, a, b, c, d, raw = pcall(UnitDetailedThreatSituation, unit, mob)
  if ok and not Secret(raw) and raw ~= nil and (Secret(a) or Secret(b) or Secret(c) or Secret(d)) then
    Tick(t, "mixed")
    return
  end
  if ok then Note(q, t, true, raw) else Note(q, t, false, a) end
end

function P.Threat(q, now, ms)
  local ok, _, _, _, _, raw = pcall(UnitDetailedThreatSituation, "player", "target")
  raw = ok and Number(raw) or nil
  if not raw then return end
  local guid = Text(Call(UnitGUID, "target")) or "?"
  if guid ~= q.guid then
    q.guid, q.base = guid, raw
    return
  end
  if raw == q.base then return end
  local rise = raw - q.base
  q.base = raw
  if rise > 0 then q.rise = q.rise + rise end
  q.changes = q.changes + 1
  Ring(q, { k = "threat", t = now, p = ms, n = rise })
end

local HEARD = {
  UNIT_THREAT_LIST_UPDATE = function(q, now, ms, unit)
    unit = Text(unit)
    if not unit or q.over then return end
    local kind = TokenKind(unit)
    local t = (kind == "target" and q.th.target) or (kind == "nameplate" and q.th.plates) or (kind == "boss" and q.th.boss)
    if t then ThreatRead(q, t, "player", unit) end
    if unit == "target" then P.Threat(q, now, ms) end
  end,
  UNIT_COMBAT = function(q, now, ms, unit, action, flag, amount, school)
    Tick(q.tokens, TokenKind(unit))
    if Secret(amount) then q.secretAmounts = q.secretAmounts + 1 end
    if q.over or Text(unit) ~= "target" or not Plain(Call(UnitCanAttack, "player", "target")) then return end
    local n = Number(amount) or 0
    action, flag = Text(action) or "?", Text(flag)
    q.hits = q.hits + 1
    if action == "WOUND" then q.dmg = q.dmg + n end
    Ring(q, { k = "hit", t = now, p = ms, a = action, f = flag ~= "" and flag or nil, n = n, s = Number(school) })
  end,
  PLAYER_SWING = function(q, now, ms, _, swingType)
    if not q.over then Ring(q, { k = "swing", t = now, p = ms, st = Number(swingType) }) end
  end,
  UNIT_SPELLCAST_SUCCEEDED = function(q, now, ms, unit, _, spellID)
    if q.over or Text(unit) ~= "player" then return end
    q.casts = q.casts + 1
    local id = Number(spellID)
    Ring(q, { k = "cast", t = now, p = ms, id = id })
    if not id then return end
    for i = #q.recent, 1, -1 do
      if q.recent[i] == id then table.remove(q.recent, i) end
    end
    table.insert(q.recent, 1, id)
    q.recent[P.RECENT + 1] = nil
  end,
  ADDON_RESTRICTION_STATE_CHANGED = function(q, _, ms, kind, state)
    if #q.restr < 20 then q.restr[#q.restr + 1] = { Number(kind), Number(state), ms } end
  end,
  COMBAT_LOG_MESSAGE = function(q, _, _, message)
    local log = q.log
    log.n = log.n + 1
    pcall(P.logText.SetText, P.logText, message)
    if log.n > 1 then return end
    local ok, kind = pcall(type, message)
    log.type, log.secret = ok and kind or "?", Secret(message)
    local text = not log.secret and Text(message)
    if text then log.len, log.text = #text, (text:sub(1, 60):gsub("|", "||")) end
  end,
}
local function Heard(event, ...)
  local q = P.q
  if not q then return end
  local now, ms = Number(Call(GetTime)) or 0, Number(Call(debugprofilestop)) or 0
  if not q.over then
    q.counts[event] = (q.counts[event] or 0) + 1
    local sec = math.floor(now - q.t0)
    if q.sec[event] ~= sec then q.sec[event], q.at[event] = sec, 0 end
    q.at[event] = q.at[event] + 1
    if q.at[event] > (q.most[event] or 0) then q.most[event] = q.at[event] end
  end
  local fn = HEARD[event]
  if fn then fn(q, now, ms, ...) end
end
function P.Listen()
  if P.listening then return end
  P.listening = true
  local events = {}
  for _, event in ipairs(P.EVENTS) do
    if event ~= "UNIT_SPELLCAST_SUCCEEDED" then events[#events + 1] = event end
  end
  P.refused = ns.On(events, Heard) or {}
  for event, err in pairs(ns.On("UNIT_SPELLCAST_SUCCEEDED", Heard, "player") or {}) do P.refused[event] = err end
end
function P.Quiet()
  if not P.listening then return end
  P.listening = false
  ns.Off(P.EVENTS, Heard)
end

local function Sweep(q)
  local target = Exists("target")
  if target then ThreatRead(q, q.th.target, "player", "target") end
  for i = 1, P.PLATES do
    local token = "nameplate" .. i
    if Exists(token) and Plain(Call(UnitCanAttack, "player", token)) then ThreatRead(q, q.th.plates, "player", token) end
  end
  if Exists("boss1") then ThreatRead(q, q.th.boss, "player", "boss1") else Tick(q.th.boss, "none") end
  if target and Exists("pet") then ThreatRead(q, q.th.pet, "pet", "target") end
  local ok, said = pcall(function() return C_Secrets.ShouldUnitThreatValuesBeSecret("player", "target") end)
  local kind = KindOf(ok, said)
  if kind == "plain" then kind = said and "true" or "false" end
  Tick(q.th.pred, kind)
end

local function MeterFields(q)
  local types, kinds = Enum and Enum.DamageMeterSessionType, Enum and Enum.DamageMeterType
  local current, done = types and types.Current, kinds and kinds.DamageDone
  local meter = C_DamageMeter or {}
  local function Ask(field, fn)
    local kind, v = Note(q, q.meter[field], pcall(fn))
    if kind == "plain" and type(v) == "number" then q.last[field] = v end
    return kind == "plain" and v or nil
  end
  Ask("clock", function() return meter.GetSessionDurationSeconds(current) end)
  local session = Ask("session", function() return meter.GetCombatSessionFromType(current, done) end)
  if type(session) == "table" then
    Ask("length", function() return session.durationSeconds end)
    Ask("sources", function() return #session.combatSources end)
    local row
    Ask("row", function()
      for i, source in ipairs(session.combatSources) do
        if Plain(source.isLocalPlayer) == true then row = source return i end
      end
    end)
    if row then
      Ask("total", function() return row.totalAmount end)
      Ask("death", function() return row.deathTimeSeconds end)
      Ask("creature", function() return row.sourceCreatureID end)
    end
  end
  local source
  Ask("spells", function()
    source = meter.GetCombatSessionSourceFromType(current, done, UnitGUID("player"))
    return #source.combatSpells
  end)
  if not Secret(source) and type(source) == "table" then
    local spells = source.combatSpells
    local first = not Secret(spells) and type(spells) == "table" and spells[1] or nil
    if Secret(first) or type(first) ~= "table" then first = nil end
    Ask("spell", function() return first and first.spellID end)
    Ask("spelltotal", function() return first and first.totalAmount end)
  end
  local list
  Ask("sessions", function() list = meter.GetAvailableCombatSessions() return #list end)
  if not Secret(list) and type(list) == "table" and #list > 0 then
    Ask("last", function() return list[#list].durationSeconds end)
    if #list > 1 then
      Ask("before", function() return meter.GetCombatSessionFromID(list[#list - 1].sessionID, done).totalAmount end)
    end
  end
end

local function Anchoring(q, t, region)
  local ok, v = pcall(region.IsAnchoringSecret, region)
  local kind = KindOf(ok, v)
  if kind == "plain" then kind = v and "true" or "false" end
  Tick(t, kind)
  if not ok and not q.err then q.err = tostring(v):match("^[^\n]*") end
end
local FIRED = { [0] = "quiet", "once", "twice", "more" }

local function Bits(q, s)
  q.bitSecs = q.bitSecs + 1
  local ok, z = pcall(function() return C_StringUtil.TruncateWhenZero(s) end)
  Note(q, q.trunc, ok, z)
  if ok then
    if pcall(P.zero.SetText, P.zero, z) then
      local okGet, got = pcall(P.zero.GetText, P.zero)
      Tick(q.zeroGet, (not okGet and "error") or (Secret(got) and "secret") or (got == nil and "nil") or "text")
      local okTruth, truth = pcall(function() if got then return "true" end return "false" end)
      Tick(q.zeroTruth, okTruth and truth or "error")
    else
      Tick(q.zeroGet, "error")
    end
  end
  local bar = P.bitBar
  pcall(bar.SetMinMaxValues, bar, 0, P.BIG)
  P.fired = 0
  pcall(bar.SetValue, bar, s)
  pcall(bar.SetValue, bar, s)
  Tick(q.changed, FIRED[math.min(P.fired, 3)])
  local bits = {}
  for i, top in ipairs(P.CLAMP) do
    pcall(bar.SetMinMaxValues, bar, 0, top)
    pcall(bar.SetValue, bar, top)
    P.fired = 0
    bits[i] = pcall(bar.SetValue, bar, s) and (P.fired > 0 and "1" or "0") or "e"
  end
  q.clamp = table.concat(bits)
  P.minmaxed = 0
  local okRange = pcall(bar.SetMinMaxValues, bar, 0, s)
  Tick(q.minmax, (not okRange and "error") or (P.minmaxed > 0 and "fired") or "quiet")
  pcall(P.sizeText.SetText, P.sizeText, s)
  Anchoring(q, q.anchorFill, Call(bar.GetStatusBarTexture, bar) or bar)
  Anchoring(q, q.anchorText, P.sizeText)
  local str = q.str
  local okFormat, text = pcall(string.format, "%d", s)
  str.format = KindOf(okFormat, text)
  if okFormat then
    str.len = KindOf(pcall(string.len, text))
    str.find = KindOf(pcall(string.find, text, "1"))
    str.sub = KindOf(pcall(string.sub, text, 1, 1))
    str.tonumber = KindOf(pcall(tonumber, text))
  end
  str.tostring = KindOf(pcall(tostring, s))
  Tick(q.fmt, pcall(P.digits.SetFormattedText, P.digits, "%d", s) and "ok" or "error")
  Note(q, q.round, pcall(function() return C_StringUtil.RoundToNearestString(s) end))
  Note(q, q.breakup, pcall(BreakUpLargeNumbers, s))
  Tick(q.sprite, pcall(P.sprite.SetSpriteSheetCell, P.sprite, s, 256, 256) and "ok" or "error")
end

function P.AuraFields(aura)
  if Secret(aura) or type(aura) ~= "table" then return aura end
  return aura, aura.spellId, aura.duration, aura.expirationTime
end
function P.Slot(name)
  return C_Item and C_Item.GetWeaponEnchantInfo and Enum and Enum.WeaponSlot and Enum.WeaponSlot[name]
end
function P.Enchant(slot)
  local list = C_Item.GetWeaponEnchantInfo(slot)
  if Secret(list) or type(list) ~= "table" then return list end
  local entry = list[#list]
  for _, e in ipairs(list) do
    if not Secret(e) and type(e) == "table" and Plain(e.hasEnchant) == true then
      entry = e
      break
    end
  end
  if Secret(entry) or type(entry) ~= "table" then return list end
  return list, entry.enchantID, entry.timeLeft
end
P.CONDS = {
  { name = "GetShapeshiftForm", values = { "index" }, has = function() return GetShapeshiftForm ~= nil end,
    read = function() return GetShapeshiftForm() end,
    after = function(c, index) c.form = Number(index) end },
  { name = "GetShapeshiftFormID", values = { "id" }, has = function() return GetShapeshiftFormID ~= nil end,
    read = function() return GetShapeshiftFormID() end },
  { name = "GetShapeshiftFormInfo", values = { "icon", "active", "castable", "spellID" },
    has = function() return GetShapeshiftFormInfo ~= nil end,
    args = function(c) return (c.form and c.form > 0) and { c.form } or {} end,
    read = function(_, index) return GetShapeshiftFormInfo(index) end },
  { name = "GetPlayerAuraBySpellID", values = { "aura", "spellId", "duration", "expirationTime" },
    has = function() return C_UnitAuras and C_UnitAuras.GetPlayerAuraBySpellID ~= nil end,
    args = function(c) return c.casts end,
    read = function(_, id) return P.AuraFields(C_UnitAuras.GetPlayerAuraBySpellID(id)) end },
  { name = "GetAuraDataByIndex", values = { "aura", "spellId" },
    has = function() return C_UnitAuras and C_UnitAuras.GetAuraDataByIndex ~= nil end,
    read = function() return P.AuraFields(C_UnitAuras.GetAuraDataByIndex("player", 1, "HELPFUL")) end },
  { name = "GetWeaponEnchantInfo(MainHand)", values = { "list", "enchantID", "timeLeft" },
    has = function() return P.Slot("MainHand") ~= nil end,
    read = function() return P.Enchant(P.Slot("MainHand")) end },
  { name = "GetWeaponEnchantInfo(OffHand)", values = { "list", "enchantID", "timeLeft" },
    has = function() return P.Slot("OffHand") ~= nil end,
    read = function() return P.Enchant(P.Slot("OffHand")) end },
  { name = "UnitExists(pet)", values = { "exists" }, has = function() return UnitExists ~= nil end,
    read = function() return UnitExists("pet") end },
  { name = "UnitCreatureFamily(pet)", values = { "family" }, has = function() return UnitCreatureFamily ~= nil end,
    read = function() return UnitCreatureFamily("pet") end },
  { name = "IsStealthed", values = { "stealthed" }, has = function() return IsStealthed ~= nil end,
    read = function() return IsStealthed() end },
  { name = "GetTotemInfo(1)", values = { "haveTotem", "totemName", "startTime", "duration" },
    has = function() return GetTotemInfo ~= nil end,
    read = function() return GetTotemInfo(1) end },
}
function P.Conditions(rec, c)
  for _, read in ipairs(P.CONDS) do
    local r = rec[read.name]
    if not r then
      r = { calls = 0, threw = 0, kinds = {}, first = {} }
      for i = 1, #read.values do r.kinds[i] = {} end
      rec[read.name] = r
    end
    if not Call(read.has) then
      r.missing = true
    else
      for _, arg in ipairs(read.args and read.args(c) or { false }) do
        local got = { pcall(read.read, c, arg) }
        r.calls = r.calls + 1
        if not got[1] then
          r.threw = r.threw + 1
        else
          for i = 1, #read.values do
            local kind, v = KindOf(true, got[i + 1])
            Tick(r.kinds[i], kind)
            if kind == "plain" and r.first[i] == nil then
              r.first[i] = type(v) == "table" and "table" or (tostring(v):gsub("|", "||"))
            end
          end
          if read.after then read.after(c, got[2]) end
        end
      end
    end
  end
end
function P.CondText(read, rec)
  local r = rec and rec[read.name]
  if r and r.missing then return T["probe.cond.missing"] end
  if not r or r.calls == 0 then return T["probe.unread"] end
  local parts = {}
  if r.threw > 0 then parts[1] = Fill(T["probe.cond.threw"], { n = r.threw }) end
  if r.calls > r.threw then
    for i, name in ipairs(read.values) do
      local fill = { name = name, kinds = Tally(r.kinds[i]), text = r.first[i] }
      parts[#parts + 1] = r.first[i] and Fill(T["probe.cond.first"], fill) or Fill(T["probe.cond.value"], fill)
    end
  end
  return Fill(T["probe.cond.phase"], { calls = r.calls, values = table.concat(parts, ", ") })
end
function P.ConditionsOut()
  P.condOut = nil
  if ns.InFight() then return end
  P.condOut = {}
  P.Conditions(P.condOut, { casts = {} })
end

function P.Second(q, s)
  Sweep(q)
  MeterFields(q)
  if Got(s) then Bits(q, s) end
  P.Conditions(q.cond, { casts = q.recent })
end

function P.Poll(q)
  local _, total = G.Sealed()
  q.polls = q.polls + 1
  local ms = (Number(Call(debugprofilestop)) or q.regen) - q.regen
  local n = Number(total)
  if n then
    q.total, q.plainMs = n, ms
    P.Report(q)
  elseif ms >= P.POLL_MS then
    q.stillMs = ms
    P.Report(q)
  end
end

local function From(list, p)
  local lo, hi = 1, #list
  while lo <= hi do
    local mid = math.floor((lo + hi) / 2)
    if list[mid] < p then lo = mid + 1 else hi = mid - 1 end
  end
  return lo
end
local function AddTo(keys, key, v)
  local k = keys[key]
  if not k then
    k = { key = key, list = {}, low = v, high = v }
    keys[key] = k
  end
  k.list[#k.list + 1] = v
  k.low, k.high = math.min(k.low, v), math.max(k.high, v)
end
local function Top(map, size, most)
  local list = {}
  for _, v in pairs(map) do list[#list + 1] = v end
  table.sort(list, function(a, b)
    if size(a) ~= size(b) then return size(a) > size(b) end
    return tostring(a.key or a.id) < tostring(b.key or b.id)
  end)
  local out = {}
  for i = 1, math.min(most, #list) do out[i] = list[i] end
  return out
end

local function Matched(q)
  local events = {}
  for i = math.max(1, q.rn - P.RING + 1), q.rn do events[#events + 1] = q.ring[(i - 1) % P.RING + 1] end
  local frames, hits, at = {}, {}, {}
  for _, e in ipairs(events) do
    local frame = frames[e.t] or { hits = {} }
    frames[e.t] = frame
    if e.k == "hit" then
      frame.hits[#frame.hits + 1] = e
      hits[#hits + 1], at[#at + 1] = e, e.p
    elseif e.k == "swing" then
      frame.swing = true
    end
  end
  local out = { gaps = {}, same = 0, keys = {}, swings = 0, swingSame = 0, swingGaps = {}, types = {}, outcomes = {},
                spells = {} }
  local lastP, lastSpell
  for _, e in ipairs(events) do
    local frame = frames[e.t]
    if e.k == "cast" then
      lastSpell = e.id
      local h = hits[From(at, e.p)]
      if e.id and h and h.p - e.p <= P.CAST_MS then
        local s = out.spells[e.id] or { id = e.id, delays = {}, schools = {} }
        out.spells[e.id] = s
        s.delays[#s.delays + 1] = h.p - e.p
        Tick(s.schools, tostring(h.s or "?"))
      end
    elseif e.k == "threat" then
      if lastP then out.gaps[#out.gaps + 1] = e.p - lastP end
      lastP = e.p
      if #frame.hits > 0 then out.same = out.same + 1 end
      local wounds = {}
      for _, h in ipairs(frame.hits) do
        if h.a == "WOUND" and h.n > 0 then wounds[#wounds + 1] = h end
      end
      if e.n > 0 and #wounds == 1 then
        local ratio = e.n / wounds[1].n
        AddTo(out.keys, Fill(T["probe.4.school"], { n = wounds[1].s or "?" }), ratio)
        AddTo(out.keys, (frame.swing and T["probe.4.swing"]) or (lastSpell and Fill(T["probe.4.spell"], { n = lastSpell }))
                        or T["probe.na"], ratio)
      end
    elseif e.k == "swing" then
      out.swings = out.swings + 1
      Tick(out.types, tostring(e.st or "?"))
      if #frame.hits > 0 then
        out.swingSame = out.swingSame + 1
        for _, h in ipairs(frame.hits) do Tick(out.outcomes, h.f or h.a) end
      end
      local i, best = From(at, e.p), nil
      for _, j in ipairs({ i - 1, i }) do
        if at[j] and (not best or math.abs(at[j] - e.p) < best) then best = math.abs(at[j] - e.p) end
      end
      if best then out.swingGaps[#out.swingGaps + 1] = best end
    end
  end
  return out
end

function P.Results(q)
  local lines, m = {}, Matched(q)
  local function Add(key, fill) lines[#lines + 1] = Fill(T[key], fill) end
  local function Count(n) return tostring(math.floor((n or 0) + 0.5)) end
  local parts = {}
  for _, event in ipairs(P.EVENTS) do
    parts[#parts + 1] = (P.refused and P.refused[event]) and Fill(T["probe.1.refused"], { name = event })
      or Fill(T["probe.1.event"], { name = event, n = q.counts[event] or 0, most = q.most[event] or 0 })
  end
  Add("probe.1", { events = table.concat(parts, ", ") })
  Add("probe.2", { target = Tally(q.th.target), plates = Tally(q.th.plates), boss = Tally(q.th.boss),
                   pet = Tally(q.th.pet), pred = Tally(q.th.pred) })
  Add("probe.3", { changes = q.changes, hits = q.hits, gap = Ms(Median(m.gaps)), same = m.same })
  local keys = {}
  for _, k in ipairs(Top(m.keys, function(k) return #k.list end, P.KEYS_SHOWN)) do
    keys[#keys + 1] = Fill(T["probe.4.key"], { key = k.key, n = #k.list, median = Ratio(Median(k.list)),
                                               low = Ratio(k.low), high = Ratio(k.high) })
  end
  Add("probe.4", { rise = Count(q.rise), dmg = Count(q.dmg), ratio = Ratio(q.dmg > 0 and q.rise / q.dmg or nil),
                   keys = #keys > 0 and table.concat(keys, ", ") or T["probe.na"],
                   game = Ratio(q.total and q.total > 0 and q.rise / q.total or nil) })
  Add("probe.5", { swings = m.swings, same = m.swingSame, gap = Ms(Median(m.swingGaps)), types = Tally(m.types),
                   outcomes = Tally(m.outcomes) })
  local spells = {}
  for _, s in ipairs(Top(m.spells, function(s) return #s.delays end, P.SPELLS_SHOWN)) do
    local school, most = "?", 0
    for k, n in pairs(s.schools) do
      if n > most then school, most = k, n end
    end
    spells[#spells + 1] = Fill(T["probe.6.spell"], { id = s.id, n = #s.delays, delay = Ms(Median(s.delays)), school = school })
  end
  Add("probe.6", { casts = q.casts, spells = #spells > 0 and table.concat(spells, ", ") or T["probe.na"] })
  local fields = {}
  for _, field in ipairs(P.FIELDS) do
    fields[field] = Tally(q.meter[field]) .. (q.last[field] and " (" .. tostring(q.last[field]) .. ")" or "")
  end
  Add("probe.7", fields)
  local secs = q.len and q.len > 0 and q.len or 1
  local function Rate(n) return string.format("%.1f", (n or 0) / secs) end
  Add("probe.8", { secs = string.format("%.1f", secs), session = Rate(q.counts.DAMAGE_METER_COMBAT_SESSION_UPDATED),
                   current = Rate(q.counts.DAMAGE_METER_CURRENT_SESSION_UPDATED), hits = Rate(q.hits) })
  local changes = {}
  for i = 1, math.min(#q.restr, P.CHANGES_SHOWN) do
    local r = q.restr[i]
    changes[i] = Fill(T["probe.9.change"], { type = r[1] or "?", state = r[2] or "?", ms = Ms(r[3] - (q.regen or r[3])) })
  end
  local meter = (q.plainMs and Fill(T["probe.9.plain"], { ms = Ms(q.plainMs), polls = q.polls }))
    or (q.stillMs and Fill(T["probe.9.still"], { ms = Ms(q.stillMs), polls = q.polls })) or T["probe.9.nometer"]
  Add("probe.9", { meter = meter, changes = #changes > 0 and table.concat(changes, ", ") or T["probe.kind.none"] })
  local clamp = T["probe.unread"]
  if q.clamp then
    local agree, asked = 0, 0
    for i, top in ipairs(P.CLAMP) do
      local bit = q.clamp:sub(i, i)
      if q.total and bit ~= "e" then
        asked = asked + 1
        if (bit == "1") == (q.total < top) then agree = agree + 1 end
      end
    end
    clamp = Fill(T["probe.10.clamp"], { bits = q.clamp, oracle = q.total and Fill(T["probe.10.agree"], { k = agree, n = asked })
                                                            or T["probe.10.nototal"] })
  end
  Add("probe.10", { zero = Fill(T["probe.10.zero"], { get = Tally(q.zeroGet), truth = Tally(q.zeroTruth) }),
                    trunc = Tally(q.trunc), changed = Tally(q.changed), clamp = clamp, minmax = Tally(q.minmax),
                    size = Fill(T["probe.10.size"], { n = P.sized - q.sized0, secs = q.bitSecs }),
                    anchor = Fill(T["probe.10.anchor"], { fill = Tally(q.anchorFill), text = Tally(q.anchorText) }) })
  local str = {}
  for _, call in ipairs({ "format", "len", "find", "sub", "tonumber", "tostring" }) do
    str[call] = q.str[call] and T["probe.kind." .. q.str[call]] or T["probe.unread"]
  end
  Add("probe.10s", str)
  Add("probe.11", { font = T["probe.kind." .. (P.fontKind or "error")], fmt = Tally(q.fmt), round = Tally(q.round),
                    breakup = Tally(q.breakup), sprite = Tally(q.sprite) })
  local log = q.log
  if log.n == 0 then
    Add("probe.12.none", {})
  elseif log.text then
    Add("probe.12.text", { n = log.n, type = log.type, len = log.len, text = log.text ~= "" and log.text or "?" })
  else
    Add("probe.12", { n = log.n, type = log.type, kind = T["probe.kind." .. (log.secret and "secret" or "none")] })
  end
  Add("probe.13", { tokens = Tally(q.tokens), secret = q.secretAmounts })
  for _, read in ipairs(P.CONDS) do
    Add("probe.cond", { name = read.name, out = P.CondText(read, P.condOut), fight = P.CondText(read, q.cond) })
  end
  if q.err then Add("probe.firsterror", { err = q.err }) end
  return lines
end

function P.Report(q)
  q.polling = false
  P.q = nil
  P.Quiet()
  local lines = {}
  if P.kept + P.ok + P.threw > 0 then
    for _, line in ipairs(P.Lines()) do lines[#lines + 1] = line end
  end
  local ok, results = pcall(P.Results, q)
  if ok then
    for _, line in ipairs(results) do lines[#lines + 1] = line end
  else
    lines[#lines + 1] = Fill(T["probe.broke"], { err = tostring(results):match("^[^\n]*") })
  end
  P.last, P.done = lines, q
  for _, line in ipairs(lines) do ns.Print(line) end
end

function M.Probe()
  if P.frame then
    P.frame:SetShown(not P.frame:IsShown())
  else
    BuildProbe()
  end
  if not P.frame:IsShown() then
    P.q = nil
    P.Quiet()
  else
    P.ConditionsOut()
  end
end
function M.ProbeReport()
  if not P.last then return ns.Print(T["probe.report.none"]) end
  for _, line in ipairs(P.last) do ns.Print(line) end
end

M.Listen(function(what, _, len)
  if not (P.frame and P.frame:IsShown()) then return end
  local q = P.q
  if what == "start" then
    if q and q.polling then P.Report(q) end
    P.ring, P.n, P.kept, P.ok, P.threw, P.err, P.reads = {}, 0, 0, 0, 0, nil, {}
    P.q = P.Fresh()
    P.Listen()
  elseif q and not q.over then
    q.over, q.len, q.regen, q.polls = true, len, Number(Call(debugprofilestop)) or 0, 0
    if live.meter then q.polling = true else P.Report(q) end
  elseif P.kept + P.ok + P.threw > 0 then
    P.last = P.Lines()
    for _, line in ipairs(P.last) do ns.Print(line) end
  end
end)

ns.meterGraph = function() return win end
G.live = function() return live end
G.parts = function() return parts end
