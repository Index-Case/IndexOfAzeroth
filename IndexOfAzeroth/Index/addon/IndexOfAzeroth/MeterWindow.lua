-- The Index of Azeroth. Copyright 2026 Index Case <indexofazeroth@pm.me>. PolyForm Strict 1.0.0, see LICENSE.md.
local ADDON, ns = ...
local UI, M = ns.UI, ns.Meter
local C, S, F = UI.C, M.Stats, M.FIELD
local Plain, Call, Text, Number = ns.Plain, ns.Call, ns.PlainText, ns.PlainNumber
local T, Fill = ns.WordsOf("game.meter"), ns.Fill

local WIDTH, HEIGHT, BODY_W = 760, 560, 736
local TOP, KEYS_H = 46, 28

local win, parts
local views = {}
local state = { tab = "fight" }


local function Num(n, decimal)
  n = tonumber(n) or 0
  if decimal and n < 100 then return string.format("%.1f", n) end
  local s = string.format("%d", math.floor(n + 0.5))
  local k
  repeat s, k = s:gsub("^(%-?%d+)(%d%d%d)", "%1,%2") until k == 0
  return s
end
M.Num = Num
local function Clock(seconds)
  seconds = math.floor((tonumber(seconds) or 0) + 0.5)
  return string.format("%d:%02d", math.floor(seconds / 60), seconds % 60)
end
local function Share(part, whole)
  return string.format("%.0f%%", whole and whole > 0 and 100 * part / whole or 0)
end
local FIGHT_WORDS = { single = "game.meter.fights.single", multi = "game.meter.fights.multi", all = "game.meter.fights" }
local function Fights(n) return ns.Count(FIGHT_WORDS[M.Opts().foes] or FIGHT_WORDS.all, n) end

local function Heading(parent, words, x, y)
  local t = UI.Text(parent, "GameFontNormalSmall", C.gold)
  t:SetWordWrap(false)
  t:SetPoint("TOPLEFT", parent, "TOPLEFT", x, y)
  t:SetText(words)
  return t
end
local function Header(parent, y, columns)
  local row = CreateFrame("Frame", nil, parent)
  row:SetPoint("TOPLEFT", parent, "TOPLEFT", 0, y)
  row:SetSize(BODY_W, 16)
  row.cells = {}
  for n, col in ipairs(columns) do
    row.cells[n] = UI.Cell(row, col[2], col[3], C.gold, col[4], "GameFontNormalSmall")
    row.cells[n]:SetText(col[1])
  end
  return row
end
local function Bar(parent, x, color)
  local t = parent:CreateTexture(nil, "ARTWORK")
  t:SetColorTexture(color[1], color[2], color[3], 1)
  t:SetPoint("LEFT", parent, "LEFT", x, 0)
  return t
end
local function Back(row)
  local t = row:CreateTexture(nil, "BACKGROUND")
  t:SetAllPoints()
  return t
end
local function Stripe(row, odd) row.back:SetColorTexture(C.row[1], C.row[2], C.row[3], odd and 1 or 0) end
local function Wrapped(row, x, width)
  local t = UI.Text(row, "GameFontHighlightSmall", C.ivory)
  t:SetPoint("LEFT", row, "LEFT", x, 0)
  t:SetWidth(width)
  return t
end
local function Tall(row, least, ...)
  local high = least
  for i = 1, select("#", ...) do
    local t = select(i, ...)
    high = math.max(high, math.ceil(Number(Call(t.GetStringHeight, t)) or 0) + (least - 12))
  end
  row:SetHeight(high)
  return high
end
local function Under(row, parent, x, y)
  row:ClearAllPoints()
  row:SetPoint("TOPLEFT", parent, "TOPLEFT", x, -y)
end

local function ItemName(id)
  local name = Text(Call(C_Item and C_Item.GetItemNameByID, id))
  if not name then Call(C_Item and C_Item.RequestLoadItemDataByID, id) end
  return name or tostring(id)
end

local function SetupName(dim, place)
  local m = M.Store()
  local key = m and m.sets[dim] and m.sets[dim][place]
  if not key or key == M.OTHER then return T["setup.other"] end
  if dim == "w" then
    local names = {}
    for id in key:gmatch("%d+") do
      if tonumber(id) ~= 0 then names[#names + 1] = ItemName(tonumber(id)) end
    end
    return #names > 0 and table.concat(names, " + ") or T["setup.weapon.none"]
  elseif dim == "b" then
    return key:match("^(%S+)") or key
  end
  return Fill(T["setup.gear"], { n = place })
end

local function SpellName(id, by)
  local name = id == 0 and T["spell.swing"] or Text(Call(C_Spell and C_Spell.GetSpellName, id)) or Fill(T["spell.unknown"], { id = id })
  return by ~= "" and (name .. " (" .. by .. ")") or name
end
local function SpellIcon(id) return id ~= 0 and Plain(Call(C_Spell and C_Spell.GetSpellTexture, id)) or nil end

local function SpellRow(row)
  local numbers, by = row:match("^([^;]*);([^;]*)")
  local n = M.Unpack(numbers or row)
  return { id = n[1] or 0, dmg = n[2] or 0, hits = (n[3] or 0) + (n[5] or 0), crits = n[4] or 0, direct = n[3] or 0,
           hi = n[7] or 0, by = by or "" }
end


local OUT_COLORS = { hit = C.gold, crit = C.cyan, glance = C.debatable, crush = C.debatable, block = C.debatable }
local SPELL_ROWS, HIT_ROWS, FOE_ROWS = 8, 7, 5
local TILES = { "tile.dps", "tile.damage", "tile.length", "tile.taken", "tile.active", "tile.max" }
local ON_WORDS = { hit = "game.meter.fight.onyou.hit", crit = "game.meter.fight.onyou.crit", crush = "game.meter.fight.onyou.crush",
                   miss = "game.meter.fight.onyou.miss", dodge = "game.meter.fight.onyou.dodge",
                   parry = "game.meter.fight.onyou.parry", block = "game.meter.fight.onyou.block" }
local KIND_WORDS = { [2] = "fight.kind.elite", [3] = "fight.kind.rareelite", [4] = "fight.kind.rare", [5] = "fight.kind.boss" }

local Fight = {}
views.fight = Fight

function Fight.Build(body)
  local v = Fight
  v.title = UI.Text(body, "GameFontHighlight", C.ivory)
  v.title:SetPoint("TOPLEFT", body, "TOPLEFT", 0, 0)
  v.title:SetWidth(BODY_W - 170)
  v.setup = UI.Text(body, "GameFontHighlightSmall", C.muted)
  v.setup:SetPoint("TOPLEFT", v.title, "BOTTOMLEFT", 0, -4)
  v.setup:SetWidth(BODY_W - 170)
  v.older = UI.FlatButton(body, T["fight.older"], nil, function() Fight.Step(-1) end)
  v.newer = UI.FlatButton(body, T["fight.newer"], nil, function() Fight.Step(1) end)
  UI.LayKeys({ v.older, v.newer }, body, 0, 0, BODY_W, 72, 4, KEYS_H)
  v.newer:ClearAllPoints()
  v.newer:SetPoint("TOPRIGHT", body, "TOPRIGHT", 0, 0)
  v.older:ClearAllPoints()
  v.older:SetPoint("TOPRIGHT", v.newer, "TOPLEFT", -4, 0)

  local top = body
  body = CreateFrame("Frame", nil, top)
  body:SetPoint("TOPLEFT", v.setup, "BOTTOMLEFT", 0, 36)
  body:SetSize(BODY_W, 500)
  v.body = body

  v.tiles = {}
  for i, key in ipairs(TILES) do
    local tile = UI.Box(body, C.row, C.dim)
    tile:SetSize(118, 58)
    tile:SetPoint("TOPLEFT", body, "TOPLEFT", (i - 1) * 123.6, -44)
    local label = UI.Text(tile, "GameFontHighlightSmall", C.muted)
    label:SetPoint("TOPLEFT", tile, "TOPLEFT", 6, -5)
    label:SetWidth(106)
    label:SetText(T[key])
    tile.value = UI.Text(tile, "GameFontNormalLarge", C.ivory)
    tile.value:SetPoint("BOTTOMLEFT", tile, "BOTTOMLEFT", 6, 5)
    v.tiles[i] = tile
  end

  Heading(body, T["fight.spells"], 0, -114)
  v.spells = {}
  for i = 1, SPELL_ROWS do
    local row = CreateFrame("Frame", nil, body)
    row:SetPoint("TOPLEFT", body, "TOPLEFT", 0, -130 - (i - 1) * 18)
    row:SetSize(410, 18)
    row.icon = row:CreateTexture(nil, "ARTWORK")
    row.icon:SetSize(14, 14)
    row.icon:SetPoint("LEFT", row, "LEFT", 0, 0)
    row.name = Wrapped(row, 18, 156)
    row.bar = Bar(row, 178, C.gold)
    row.amount = UI.Cell(row, 304, 60, C.ivory, "RIGHT")
    row.share = UI.Cell(row, 368, 40, C.muted, "RIGHT")
    v.spells[i] = row
  end
  v.wait = UI.Text(body, "GameFontHighlightSmall", C.muted)
  v.wait:SetPoint("TOPLEFT", body, "TOPLEFT", 0, -132)
  v.wait:SetWidth(410)
  v.wait:SetText(T["fight.spells.wait"])

  v.hitsHead = Heading(body, T["fight.hits"], 436, -114)
  v.hitsHead:SetWidth(300)
  v.hits = {}
  for i = 1, HIT_ROWS do
    local row = CreateFrame("Frame", nil, body)
    row:SetPoint("TOPLEFT", body, "TOPLEFT", 436, -130 - (i - 1) * 18)
    row:SetSize(300, 18)
    row.name = UI.Cell(row, 0, 70)
    row.bar = Bar(row, 74, C.gold)
    row.count = UI.Cell(row, 208, 40, C.ivory, "RIGHT")
    row.share = UI.Cell(row, 252, 44, C.muted, "RIGHT")
    v.hits[i] = row
  end
  v.foesHead = Heading(body, T["fight.foes"], 436, -114)
  v.foesHead:SetWidth(300)
  v.foes = {}
  for i = 1, FOE_ROWS do
    local row = CreateFrame("Frame", nil, body)
    row:SetPoint("TOPLEFT", body, "TOPLEFT", 436, -130 - (i - 1) * 18)
    row:SetSize(300, 18)
    row.name = Wrapped(row, 0, 150)
    row.amount = UI.Cell(row, 152, 92, C.ivory, "RIGHT")
    row.share = UI.Cell(row, 252, 44, C.muted, "RIGHT")
    v.foes[i] = row
  end
  v.foesRest = CreateFrame("Frame", nil, body)
  v.foesRest:SetSize(300, 18)
  v.foesRest.name = Wrapped(v.foesRest, 0, 150)
  v.foesRest.amount = UI.Cell(v.foesRest, 152, 92, C.ivory, "RIGHT")
  v.foesRest.share = UI.Cell(v.foesRest, 252, 44, C.muted, "RIGHT")
  v.foesMain = UI.Text(body, "GameFontHighlightSmall", C.muted)
  v.foesMain:SetPoint("TOPLEFT", body, "TOPLEFT", 436, -134 - FOE_ROWS * 18)
  v.foesMain:SetWidth(300)
  v.onYou = UI.Text(body, "GameFontHighlightSmall", C.muted)
  v.onYou:SetPoint("TOPLEFT", body, "TOPLEFT", 436, -260)
  v.onYou:SetWidth(300)

  Heading(body, T["fight.line"], 0, -294)
  v.chart = UI.Chart(body, BODY_W, 100)
  v.chart:SetPoint("TOPLEFT", body, "TOPLEFT", 0, -310)
  v.to = UI.Text(body, "GameFontHighlightSmall", C.muted, "RIGHT")
  v.to:SetPoint("TOPRIGHT", body, "TOPRIGHT", 0, -413)
  v.mean = UI.Text(body, "GameFontHighlightSmall", C.cyan)
  v.mean:SetPoint("TOPLEFT", body, "TOPLEFT", 0, -413)
  v.mean:SetText(T["fight.line.mean"])
  v.note = UI.Text(body, "GameFontHighlightSmall", C.muted)
  v.note:SetPoint("TOPLEFT", body, "TOPLEFT", 0, -432)
  v.note:SetWidth(BODY_W)
end

function Fight.Step(by)
  local m = M.Store()
  local n = m and #m.f or 0
  local at = math.max(1, math.min(n, (state.fight or n) + by))
  state.fight = at < n and at or nil
  M.Draw()
end

function Fight.Foes(fields, detail)
  local v, rows = Fight, detail.en or {}
  local on = #rows >= 2
  v.hitsHead:SetShown(not on)
  for _, row in ipairs(v.hits) do
    if on then row:Hide() end
  end
  v.foesHead:SetShown(on)
  v.foesMain:SetShown(on)
  local whole, total = detail.ew, 0
  for _, raw in ipairs(rows) do total = total + (tonumber(raw:match("^(%d+)")) or 0) end
  if not whole and not M.Has(fields[F.flags], M.NO_DMG) then total = fields[F.dmg] end
  local all = (not whole and M.Foes(fields)) or #rows
  local y, shown, sum, foot = 130, 0, 0, 130 + FOE_ROWS * 18
  for i, row in ipairs(v.foes) do
    local raw = on and rows[i]
    if raw then
      local d, name = raw:match("^(%d+),%d+;(.*)$")
      row.name:SetText(name or "")
      local high = Tall(row, 18, row.name)
      if y + high + (all > i and 18 or 0) > foot or shown < i - 1 then
        raw = nil
      else
        Under(row, v.body, 436, y)
        y, shown, sum = y + high, i, sum + (tonumber(d) or 0)
      end
      row.amount:SetText(Num(tonumber(d) or 0))
      row.share:SetText(Share(tonumber(d) or 0, total))
    end
    row:SetShown(raw and true or false)
  end
  local rest = v.foesRest
  rest:SetShown(on and all > shown)
  if not on then return end
  if all > shown then
    rest.name:SetText(ns.Count("game.meter.fight.foes.rest", all - shown))
    rest.amount:SetText(Num(math.max(0, total - sum)))
    rest.share:SetText(Share(math.max(0, total - sum), total))
    Under(rest, v.body, 436, y)
    y = y + Tall(rest, 18, rest.name)
  end
  v.foesMain:ClearAllPoints()
  v.foesMain:SetPoint("TOPLEFT", v.body, "TOPLEFT", 436, -(y + 4))
  v.foesHead:SetText(whole and T["fight.foes.whole"] or T["fight.foes"])
  local n, main = M.Foes(fields), M.MainShare(fields)
  if whole then
    v.foesMain:SetText(T["fight.foes.whole.note"])
  elseif n and main then
    v.foesMain:SetText(Fill(T["fight.foes.main"], { pct = main, rest = 100 - main,
                                                    others = ns.Count("game.meter.foes.others", n - 1) }))
  else
    v.foesMain:SetText("")
  end
end

local function MobLevel(fields)
  local gap = fields[F.gap]
  if gap == 0 then return nil end
  gap = gap - M.GAP_BASE
  return gap >= 10 and "??" or tostring(fields[F.lvl] + gap)
end

local function FoeName(m, fields)
  local words = m.names[fields[F.name]]
  if not words or words == M.OTHER then words = T["fight.target.unknown"] end
  local n = M.Foes(fields)
  return n and n >= 2 and Fill(T["fight.foes.more"], { name = words, n = n - 1 }) or words
end

local function About(fields, full)
  local about = {}
  local level = full and MobLevel(fields)
  if level then
    about[#about + 1] = level == "??" and T["fight.moblevel.skull"] or Fill(T["fight.moblevel"], { n = level })
  end
  local kind = KIND_WORDS[fields[F.kind]]
  if kind and (full or fields[F.kind] == M.KINDS.worldboss) then about[#about + 1] = T[kind] end
  if M.Place(fields) == M.DUNGEON then about[#about + 1] = T["fight.place.dungeon"] end
  return #about > 0 and (" (" .. table.concat(about, ", ") .. ")") or ""
end

local function TargetWords(m, fields)
  return FoeName(m, fields) .. About(fields, true) .. "   " .. date("%d %b %H:%M", fields[F.t])
end

function Fight.Draw()
  local v, m = Fight, M.Store()
  local n = #m.f
  local at = math.min(state.fight or n, n)
  local fields = M.Unpack(m.f[at])
  local detail = m.d[fields[F.t]] or {}
  v.older:SetShown(at > 1)
  v.newer:SetShown(at < n)
  v.title:SetText(TargetWords(m, fields))
  v.setup:SetText(table.concat({ SetupName("w", fields[F.w]), Fill(T["fight.talents"], { points = SetupName("b", fields[F.b]) }),
                                 SetupName("g", fields[F.g]), Fill(T["fight.level"], { n = fields[F.lvl] }) }, "   "))

  local dps, len, flags = S.Dps(fields), fields[F.len] / 10, fields[F.flags]
  local function Known(bit, words) if M.Has(flags, bit) then return T["tile.unknown"] end return words end
  local values = { Known(M.NO_DMG, Num(dps, true)), Known(M.NO_DMG, Num(fields[F.dmg])), Clock(len),
                   Known(M.NO_TAKEN, Num(fields[F.taken])), Share(fields[F.act] / 10, len), Known(M.NO_MAX, Num(fields[F.max])) }
  for i, tile in ipairs(v.tiles) do tile.value:SetText(values[i]) end

  local spells = {}
  for i, row in ipairs(detail.sp or {}) do spells[i] = SpellRow(row) end
  table.sort(spells, function(a, b) return a.dmg > b.dmg end)
  local top = spells[1] and spells[1].dmg or 0
  local y = 130
  for i, row in ipairs(v.spells) do
    local sp = spells[i]
    if sp then
      row.name:SetText(SpellName(sp.id, sp.by))
      local high = Tall(row, 18, row.name)
      if y + high > 290 then sp = nil else Under(row, v.body, 0, y); y = y + high end
    end
    row:SetShown(sp ~= nil)
    if sp then
      row.icon:SetTexture(SpellIcon(sp.id))
      row.bar:SetSize(math.max(1, 120 * (top > 0 and sp.dmg / top or 0)), 10)
      row.bar:SetColorTexture(unpack(sp.by ~= "" and C.blue or C.gold))
      row.amount:SetText(Num(sp.dmg))
      row.share:SetText(Share(sp.dmg, fields[F.dmg]))
    end
  end
  v.wait:SetShown(#spells == 0)

  local shown, most = 0, 0
  for i = 1, #M.OUT do most = math.max(most, fields[F.out + i - 1]) end
  for i, kind in ipairs(M.OUT) do
    local count = fields[F.out + i - 1]
    if count > 0 and shown < HIT_ROWS then
      shown = shown + 1
      local row = v.hits[shown]
      row:Show()
      row.name:SetText(T["outcome." .. kind])
      row.bar:SetSize(math.max(1, 130 * count / most), 10)
      row.bar:SetColorTexture(unpack(OUT_COLORS[kind] or C.red))
      row.count:SetText(count)
      row.share:SetText(Share(count, fields[F.hits]))
    end
  end
  for i = shown + 1, HIT_ROWS do v.hits[i]:Hide() end
  v.hitsHead:SetText(M.Has(fields[F.flags], M.GROUPED) and T["fight.hits.grouped"] or T["fight.hits"])
  Fight.Foes(fields, detail)

  local on = {}
  for i, kind in ipairs(M.ON) do
    local count = fields[F.on + i - 1]
    if count > 0 then on[#on + 1] = ns.Count(ON_WORDS[kind], count) end
  end
  v.onYou:SetText(#on > 0 and Fill(T["fight.onyou"], { list = table.concat(on, ", ") }) or T["fight.onyou.none"])

  v.chart:Clear()
  local line = detail.ln and M.Unpack(detail.ln)
  local drawn = line ~= nil and #line > 0
  if drawn then
    local max = M.Has(flags, M.NO_DMG) and 0 or dps
    for _, amount in ipairs(line) do max = math.max(max, amount) end
    v.chart:Columns(line, max, C.gold)
    if not M.Has(flags, M.NO_DMG) then v.chart:Level(dps, max, C.cyan) end
    v.chart.top:SetText(Num(max))
    v.to:SetText(Clock(#line))
  else
    local words = "fight.line.gone"
    if at > n - M.LINES_KEPT then words = M.Has(flags, M.DETAIL) and "fight.line.none" or "fight.line.wait" end
    v.chart.top:SetText(Fill(T[words], { n = M.LINES_KEPT }))
    v.to:SetText("")
  end
  v.mean:SetShown(drawn and not M.Has(flags, M.NO_DMG))

  local notes = {}
  for _, note in ipairs({ { M.GAME, "note.game" }, { M.FROM_HITS, "note.fromhits" }, { M.NO_DMG, "note.nodamage" },
                          { M.NO_TAKEN, "note.notaken" }, { M.NO_MAX, "note.nomax" }, { M.CHANGED, "note.changed" },
                          { M.DIED, "note.died" } }) do
    if M.Has(flags, note[1]) then notes[#notes + 1] = T[note[2]] end
    if note[1] == M.NO_MAX and (M.Has(flags, M.NO_DMG) or M.Has(flags, M.NO_TAKEN) or M.Has(flags, M.NO_MAX)) then
      notes[#notes + 1] = T["note.index"]
    end
  end
  v.note:SetText(table.concat(notes, "\n"))
end


local History = { filtered = true, sums = true, COLS = 150, ROWS = 300 }
views.history = History

local HISTORY_COLS = { { T["col.when"], 0, 82 }, { T["col.target"], 86, 134 }, { T["col.level"], 224, 66, "RIGHT" },
                       { T["col.length"], 294, 60, "RIGHT" }, { T["col.dps"], 358, 50, "RIGHT" },
                       { T["col.damage"], 412, 94, "RIGHT" }, { T["col.taken"], 510, 94, "RIGHT" },
                       { T["col.weapons"], 608, 122 } }

function History.Build(body)
  local v = History
  v.head = Heading(body, T["history.title"], 0, 0)
  v.chart = UI.Chart(body, BODY_W, 120)
  v.chart:SetPoint("TOPLEFT", body, "TOPLEFT", 0, -16)
  local older = UI.Text(body, "GameFontHighlightSmall", C.muted)
  older:SetPoint("TOPLEFT", body, "TOPLEFT", 0, -139)
  older:SetText(T["history.older"])
  local newest = UI.Text(body, "GameFontHighlightSmall", C.muted, "RIGHT")
  newest:SetPoint("TOPRIGHT", body, "TOPRIGHT", 0, -139)
  newest:SetText(T["history.newest"])
  local mean = UI.Text(body, "GameFontHighlightSmall", C.cyan, "CENTER")
  mean:SetPoint("TOP", body, "TOP", 0, -139)
  mean:SetText(Fill(T["history.mean"], { n = M.ROLLING }))
  v.summary = UI.Text(body, "GameFontHighlight", C.ivory)
  v.summary:SetWordWrap(false)
  v.summary:SetPoint("TOPLEFT", body, "TOPLEFT", 0, -158)
  v.summary:SetWidth(BODY_W)
  Header(body, -182, HISTORY_COLS)
  v.body = body
  v.scroll = UI.Scroller(body)
  v.scroll:SetPoint("TOPLEFT", body, "TOPLEFT", 0, -200)
  v.scroll:SetWidth(BODY_W)
  v.Row, v.Rest = UI.Rows(function(i)
    local row = CreateFrame("Button", nil, v.scroll.child)
    row:SetPoint("TOPLEFT", v.scroll.child, "TOPLEFT", 0, -(i - 1) * 18)
    row:SetSize(BODY_W - 6, 18)
    row.back = Back(row)
    row.cells = {}
    for n, col in ipairs(HISTORY_COLS) do
      row.cells[n] = (n == 2 or n == 8) and Wrapped(row, col[2], col[3])
        or UI.Cell(row, col[2], col[3], n == 5 and C.gold or C.ivory, col[4])
    end
    row:SetScript("OnClick", function(self)
      state.fight = self.at
      M.Open("fight")
    end)
    row:SetScript("OnEnter", function(self) self.back:SetColorTexture(unpack(C.rowOn)) end)
    row:SetScript("OnLeave", function(self) Stripe(self, self.odd) end)
    return row
  end)
end

function History.Draw(st)
  local v, m = History, M.Store()
  local n = st.n
  local values, max = {}, 0
  for i = math.max(1, n - v.COLS + 1), n do
    values[#values + 1] = st.dps[i]
    max = math.max(max, st.dps[i])
  end
  v.chart:Clear()
  v.chart:Columns(values, max, C.gold)
  v.chart:Line(S.Rolling(values, M.ROLLING), max, C.cyan)
  v.chart.top:SetText(Num(max, true))
  v.head:SetText(n > v.COLS and Fill(T["history.title.newest"], { n = v.COLS }) or T["history.title"])
  v.summary:SetText(Fill(T["history.summary"], { count = Fights(n), dps = Num(st.sum / n, true),
                                                 dmg = Num(st.dmg), time = Clock(st.secs) }))
  local shown, y, stops = 0, 0, { 0 }
  for i = n, math.max(1, n - v.ROWS + 1), -1 do
    local at = st.at[i]
    local fields = m.f[at] and M.Unpack(m.f[at])
    if fields then
      shown = shown + 1
      local row = v.Row(shown)
      row.at, row.odd = at, shown % 2 == 1
      Stripe(row, row.odd)
      local cells = row.cells
      cells[1]:SetText(date("%d %b %H:%M", fields[F.t]))
      cells[2]:SetText(FoeName(m, fields) .. About(fields, false))
      cells[3]:SetText(MobLevel(fields) or "")
      cells[4]:SetText(Clock(fields[F.len] / 10))
      cells[5]:SetText(Num(st.dps[i], true))
      cells[6]:SetText(Num(fields[F.dmg]))
      cells[7]:SetText(M.Has(fields[F.flags], M.NO_TAKEN) and T["tile.unknown"] or Num(fields[F.taken]))
      cells[8]:SetText(SetupName("w", fields[F.w]))
      Under(row, v.scroll.child, 0, y)
      y = y + Tall(row, 18, cells[2], cells[8])
      stops[#stops + 1] = y
    end
  end
  v.Rest(shown)
  v.scroll:Fit(y, stops, (Number(Call(v.body.GetHeight, v.body)) or 0) - 200)
end


local Compare = { filtered = true, sums = true, splits = true, picked = {} }
views.compare = Compare

local BAR_X, BAR_W = 294, 70
local COMPARE_FOOT = 136
local COMPARE_HEAD = 28
local COMPARE_TOP = 34 + COMPARE_HEAD + 2
local COMPARE_COLS = { { "", 6, 172 }, { T["col.fights"], 182, 42, "RIGHT" }, { T["col.avg"], 228, 58, "RIGHT" },
                       { T["col.range"], BAR_X, BAR_W }, { T["col.kill"], 368, 66, "RIGHT" }, { T["col.avg.taken"], 438, 118, "RIGHT" },
                       { T["col.crit"], 560, 44, "RIGHT" }, { T["col.miss"], 608, 46, "RIGHT" }, { T["col.xp"], 658, 70, "RIGHT" } }
local DIMS = { { "w", T["compare.weapons"] }, { "b", T["compare.talents"] }, { "g", T["compare.gear"] } }
local ONE = { w = "verdict.one.weapons", b = "verdict.one.talents", g = "verdict.one.gear" }

function Compare.Build(body)
  local v = Compare
  v.dims = UI.Tabs(body, DIMS, function(dim)
    M.Opts().dim = dim
    v.picked = {}
    M.Draw()
  end, 320)
  v.dims:SetPoint("TOPLEFT", body, "TOPLEFT", 0, 0)
  local hint = UI.Text(body, "GameFontHighlightSmall", C.muted)
  hint:SetWordWrap(false)
  hint:SetPoint("LEFT", body, "TOPLEFT", 330, -12)
  hint:SetText(T["compare.hint"])
  v.split = CreateFrame("Frame", nil, body)
  v.split:SetPoint("TOPLEFT", body, "TOPLEFT", 0, -KEYS_H - 4)
  v.split.label = Heading(v.split, T["compare.split"], 0, -6)
  v.split.keys = {}
  v.body = body
  v.header = Header(body, -34, COMPARE_COLS)
  v.header:SetHeight(COMPARE_HEAD)
  for _, cell in ipairs(v.header.cells) do cell:SetWordWrap(true) end
  v.scroll = UI.Scroller(body)
  v.scroll:SetPoint("TOPLEFT", body, "TOPLEFT", 0, -COMPARE_TOP)
  v.scroll:SetWidth(BODY_W)
  v.Row, v.Rest = UI.Rows(function()
    local row = UI.Skin(CreateFrame("Button", nil, v.scroll.child, "BackdropTemplate"), C.row, C.dim)
    row:SetSize(BODY_W - 6, 24)
    row.cells = {}
    for n, col in ipairs(COMPARE_COLS) do
      if n == 1 then
        row.cells[n] = Wrapped(row, col[2], col[3])
      elseif n ~= 4 then
        row.cells[n] = UI.Cell(row, col[2], col[3], n == 3 and C.gold or C.ivory, col[4])
      end
    end
    row.bar = Bar(row, BAR_X, C.gold)
    row.range = row:CreateTexture(nil, "OVERLAY")
    row.range:SetColorTexture(C.ivory[1], C.ivory[2], C.ivory[3], 1)
    row:SetScript("OnClick", function(self)
      local picked = v.picked
      if picked[1] == self.key or picked[2] == self.key then return end
      picked[1], picked[2] = picked[2] or picked[1], self.key
      M.Draw()
    end)
    return row
  end)
  v.verdict = UI.Box(body, C.panel, C.edge)
  v.verdict:SetPoint("BOTTOMLEFT", body, "BOTTOMLEFT", 0, 0)
  v.verdict:SetSize(BODY_W, 92)
  v.verdict.head = UI.Text(v.verdict, "GameFontNormal", C.gold)
  v.verdict.head:SetPoint("TOPLEFT", v.verdict, "TOPLEFT", 10, -9)
  v.verdict.words = UI.Text(v.verdict, "GameFontHighlight", C.ivory)
  v.verdict.words:SetPoint("TOPLEFT", v.verdict, "TOPLEFT", 10, -29)
  v.verdict.words:SetWidth(BODY_W - 20)
  v.range = UI.Text(body, "GameFontHighlightSmall", C.muted)
  v.range:SetPoint("BOTTOMLEFT", v.verdict, "TOPLEFT", 0, 8)
  v.range:SetWidth(BODY_W)
  v.range:SetText(T["compare.range"])
end

local function GroupWord(group)
  local m = M.Store()
  local word = m and m.cw[group] or group
  return (word:gsub("^%l", string.upper))
end
local function RowName(dim, g, cell)
  local name = SetupName(dim, g.place)
  if g.cond then
    local cond = g.cond ~= 0 and g.condName or Fill(T["compare.nocond"], { group = GroupWord(M.Split()) })
    local line = Fill(T["compare.row.split"], { name = name, condition = cond })
    if cell then
      cell:SetText(line)
      local wide = Number(Call(cell.GetUnboundedStringWidth or cell.GetStringWidth, cell)) or 0
      if wide > (Number(Call(cell.GetWidth, cell)) or 0) then
        local head, tail = Fill(T["compare.row.split"], { name = name, condition = "\001" }):match("^(.-)%s*\001(.*)$")
        line = head and (head .. "\n" .. cond .. tail) or line
      end
    end
    name = line
  end
  if cell then cell:SetText(name) end
  return name
end

local function SplitRow(v)
  local groups, row = M.CondGroups(), v.split
  row:SetShown(#groups > 0)
  if #groups == 0 then return 0 end
  local picked, keys = M.Split(), {}
  for i = 1, #groups + 1 do
    local b = row.keys[i]
    if not b then
      b = UI.FlatButton(row, "", nil, function(self)
        M.Opts().split = self.group
        v.picked = {}
        M.Draw()
      end)
      b:HookScript("OnEnter", function(self)
        GameTooltip:SetOwner(self, "ANCHOR_TOP")
        GameTooltip:AddLine(T["compare.split.tip"], 1, 1, 1, true)
        GameTooltip:Show()
      end)
      b:HookScript("OnLeave", function() GameTooltip:Hide() end)
      row.keys[i] = b
    end
    b.group = i > 1 and groups[i - 1].key or nil
    b.label:SetText(i > 1 and GroupWord(b.group) or T["compare.split.none"])
    b:SetSelected(b.group == picked)
    keys[i] = b
  end
  for i = #keys + 1, #row.keys do row.keys[i]:Hide() end
  local x = math.ceil(Number(Call(row.label.GetStringWidth, row.label)) or 40) + 10
  local high = UI.LayKeys(keys, row, x, 0, BODY_W - x, 60, 4, KEYS_H) + KEYS_H
  row:SetSize(BODY_W, high)
  return high + 4
end

local function VerdictWords(dim, kind, a, b, more)
  local short = math.max(0, M.MIN_FIGHTS - a.n) + math.max(0, M.MIN_FIGHTS - b.n)
  local fill = { a = RowName(dim, a), b = RowName(dim, b), adps = Num(a.mean, true), bdps = Num(b.mean, true),
                 acount = Fights(a.n), bcount = Fights(b.n),
                 pct = b.mean > 0 and string.format("%.0f", 100 * (a.mean - b.mean) / b.mean) or "0",
                 more = more, min = Fights(M.MIN_FIGHTS), short = Fights(short) }
  if kind == "few" then return T["verdict.few.title"], C.muted, Fill(T["verdict.few"], fill) end
  if kind == "win" then return T["verdict.title"], C.green, Fill(T["verdict.win"], fill) end
  if kind == "same" then return T["verdict.title"], C.debatable, Fill(T["verdict.same"], fill) end
  return T["verdict.title"], C.debatable, Fill(T["verdict.close"], fill)
end

function Compare.Draw(st)
  local v = Compare
  local dim = M.Opts().dim
  v.dims:Pick(dim)
  for _, d in ipairs(DIMS) do
    if d[1] == dim then v.header.cells[1]:SetText(d[2]) end
  end
  local splitH = SplitRow(v)
  v.header:SetPoint("TOPLEFT", v.body, "TOPLEFT", 0, -34 - splitH)
  v.scroll:SetPoint("TOPLEFT", v.body, "TOPLEFT", 0, -COMPARE_TOP - splitH)
  local groups = S.Groups(st, dim)
  local by, top = {}, 0
  for _, g in ipairs(groups) do
    by[g.key] = g
    top = math.max(top, g.mean + 2 * g.se)
  end
  local picked = v.picked
  if not (by[picked[1]] and by[picked[2]]) then picked[1], picked[2] = groups[1] and groups[1].key, groups[2] and groups[2].key end
  local shown, y, stops = #groups, 0, { 0 }
  for i = 1, shown do
    local g = groups[i]
    local row = v.Row(i)
    row.key = g.key
    local on = g.key == picked[1] or g.key == picked[2]
    row:SetBackdropColor(unpack(on and C.rowOn or C.row))
    row:SetBackdropBorderColor(unpack(on and C.cyan or C.dim))
    local cells = row.cells
    RowName(dim, g, cells[1])
    cells[2]:SetText(g.n)
    cells[3]:SetText(Num(g.mean, true))
    cells[5]:SetText(Clock(g.kill))
    cells[6]:SetText(g.each and Num(g.each) or T["tile.unknown"])
    cells[7]:SetText(g.hits > 0 and Share(g.critShare, 1) or "")
    cells[8]:SetText(g.hits > 0 and Share(g.missShare, 1) or "")
    cells[9]:SetText(g.xp > 0 and Num(g.xpHour) or "")
    local scale = top > 0 and BAR_W / top or 0
    row.bar:SetSize(math.max(1, g.mean * scale), 10)
    local low, high = math.max(0, g.mean - 2 * g.se) * scale, (g.mean + 2 * g.se) * scale
    row.range:ClearAllPoints()
    row.range:SetPoint("LEFT", row, "LEFT", BAR_X + low, 0)
    row.range:SetSize(math.max(1, high - low), 2)
    row.range:SetShown(g.n > 1)
    Under(row, v.scroll.child, 0, y)
    y = y + Tall(row, 24, cells[1]) + 2
    stops[#stops + 1] = y
  end
  v.Rest(shown)
  v.scroll:Fit(y, stops, (Number(Call(v.body.GetHeight, v.body)) or 0) - COMPARE_TOP - splitH - COMPARE_FOOT)
  local a, b = by[picked[1]], by[picked[2]]
  local head, color, words
  if a and b then
    head, color, words = VerdictWords(dim, S.Verdict(a, b))
  else
    head, color, words = T["verdict.one.title"], C.muted, T[ONE[dim]]
  end
  v.verdict.head:SetText(head)
  v.verdict.head:SetTextColor(unpack(color))
  v.verdict.words:SetText(words)
end


local Spells = { filtered = true }
views.spells = Spells

local SPELL_BAR_X, SPELL_BAR_W = 374, 78
local SPELL_COLS = { { T["col.spell"], 18, 156 }, { T["col.damage"], 178, 94, "RIGHT" }, { T["col.share"], 276, 92, "RIGHT" },
                     { "", SPELL_BAR_X, SPELL_BAR_W }, { T["col.each.fight"], 456, 112, "RIGHT" }, { T["col.each.hit"], 572, 54, "RIGHT" },
                     { T["col.crit"], 630, 46, "RIGHT" }, { T["col.hits"], 680, 48, "RIGHT" } }

function Spells.Build(body)
  local v = Spells
  v.note = UI.Text(body, "GameFontHighlightSmall", C.muted)
  v.note:SetPoint("TOPLEFT", body, "TOPLEFT", 0, 0)
  v.note:SetWidth(BODY_W)
  v.header = Header(body, 0, SPELL_COLS)
  v.header:ClearAllPoints()
  v.header:SetPoint("TOPLEFT", v.note, "BOTTOMLEFT", 0, -6)
  v.body = body
  v.scroll = UI.Scroller(body)
  v.scroll:SetPoint("TOPLEFT", v.header, "BOTTOMLEFT", 0, -2)
  v.scroll:SetWidth(BODY_W)
  v.Row, v.Rest = UI.Rows(function(i)
    local row = CreateFrame("Frame", nil, v.scroll.child)
    row:SetPoint("TOPLEFT", v.scroll.child, "TOPLEFT", 0, -(i - 1) * 20)
    row:SetSize(BODY_W - 6, 20)
    row.back = Back(row)
    row.icon = row:CreateTexture(nil, "ARTWORK")
    row.icon:SetSize(14, 14)
    row.icon:SetPoint("LEFT", row, "LEFT", 0, 0)
    row.cells = {}
    for n, col in ipairs(SPELL_COLS) do
      if n == 1 then
        row.cells[n] = Wrapped(row, col[2], col[3])
      elseif n ~= 4 then
        row.cells[n] = UI.Cell(row, col[2], col[3], n == 2 and C.gold or C.ivory, col[4])
      end
    end
    row.bar = Bar(row, SPELL_BAR_X, C.gold)
    return row
  end)
end

function Spells.Draw()
  local v, m = Spells, M.Store()
  local probe = S.Begin()
  local by, spells, total, fights = {}, {}, 0, 0
  for at = #m.f, math.max(1, #m.f - M.SPELLS_KEPT + 1), -1 do
    local fields = M.Unpack(m.f[at])
    local detail = m.d[fields[F.t]]
    if detail and detail.sp and #detail.sp > 0 and S.Passes(probe, fields) then
      fights = fights + 1
      for _, raw in ipairs(detail.sp) do
        local sp = SpellRow(raw)
        local key = sp.by .. ":" .. sp.id
        local s = by[key]
        if not s then
          s = { id = sp.id, by = sp.by, dmg = 0, counted = 0, hits = 0, direct = 0, crits = 0, fights = 0 }
          by[key] = s
          spells[#spells + 1] = s
        end
        s.dmg, s.fights = s.dmg + sp.dmg, s.fights + 1
        if not detail.sg then
          s.counted, s.hits, s.direct, s.crits = s.counted + sp.dmg, s.hits + sp.hits, s.direct + sp.direct, s.crits + sp.crits
          s.logged = true
        end
        total = total + sp.dmg
      end
    end
  end
  table.sort(spells, function(a, b) return a.dmg > b.dmg end)
  v.left = probe
  v.note:SetText(fights > 0 and ns.Count("game.meter.spells.note", fights) or T["spells.none"])  v.header:SetShown(fights > 0)
  local top, y, stops = spells[1] and spells[1].dmg or 0, 0, { 0 }
  for i, s in ipairs(spells) do
    local row = v.Row(i)
    Stripe(row, i % 2 == 1)
    row.icon:SetTexture(SpellIcon(s.id))
    local cells = row.cells
    cells[1]:SetText(SpellName(s.id, s.by))
    cells[2]:SetText(Num(s.dmg))
    cells[3]:SetText(Share(s.dmg, total))
    cells[5]:SetText(Num(s.dmg / s.fights))
    cells[6]:SetText(s.hits > 0 and Num(s.counted / s.hits) or "")
    cells[7]:SetText(s.direct > 0 and Share(s.crits, s.direct) or "")
    cells[8]:SetText(s.logged and Num(s.hits) or "")
    row.bar:SetSize(math.max(1, SPELL_BAR_W * (top > 0 and s.dmg / top or 0)), 10)
    row.bar:SetColorTexture(unpack(s.by ~= "" and C.blue or C.gold))
    Under(row, v.scroll.child, 0, y)
    y = y + Tall(row, 20, cells[1])
    stops[#stops + 1] = y
  end
  v.Rest(#spells)
  v.high, v.stops = y, stops
  v.Fit()
end
function Spells.Fit()
  local v = Spells
  local over = (Number(Call(v.note.GetStringHeight, v.note)) or 0) + 6 + (Number(Call(v.header.GetHeight, v.header)) or 0) + 2
  v.scroll:Fit(v.high or 0, v.stops, (Number(Call(v.body.GetHeight, v.body)) or 0) - over)
end


local TAB_NAMES = { { "fight", T["tab.fight"] }, { "history", T["tab.history"] }, { "compare", T["tab.compare"] },
                    { "spells", T["tab.spells"] } }
local FILTERS = {
  { opt = "solo", values = { true, false }, words = { [true] = "filter.solo.on", [false] = "filter.solo.off" } },
  { opt = "gap", values = { "all", "lower", "even", "higher" },
    words = { all = "filter.gap.all", lower = "filter.gap.lower", even = "filter.gap.even", higher = "filter.gap.higher" } },
  { opt = "kind", values = { "all", "normal", "elite" },
    words = { all = "filter.kind.all", normal = "filter.kind.normal", elite = "filter.kind.elite" } },
  { opt = "when", values = { "all", "today", "week", "level" },
    words = { all = "filter.when.all", today = "filter.when.today", week = "filter.when.week", level = "filter.when.level" } },
  { opt = "foes", values = { "single", "multi", "all" },
    words = { single = "filter.foes.single", multi = "filter.foes.multi", all = "filter.foes.all" } },
  { opt = "place", values = { "all", "open", "dungeon" },
    words = { all = "filter.place.all", open = "filter.place.open", dungeon = "filter.place.dungeon" } },
}

local function Build()
  win = CreateFrame("Frame", "IndexOfAzerothMeter", UIParent, "BackdropTemplate")
  UI.Panel(win)
  win:SetSize(WIDTH, HEIGHT)
  win:SetPoint("CENTER")
  win:SetFrameStrata("HIGH")
  win:SetMovable(true)
  win:SetClampedToScreen(true)
  win:EnableMouse(true)
  win:RegisterForDrag("LeftButton")
  win:SetScript("OnDragStart", function(self) self:StartMoving() end)
  win:SetScript("OnDragStop", function(self)
    self:StopMovingOrSizing()
    local point, _, rel, x, y = Call(self.GetPoint, self)
    point, rel, x, y = Text(point), Text(rel), Number(x), Number(y)
    if point and rel and x and y and type(IndexOfAzerothCharDB) == "table" then
      IndexOfAzerothCharDB.meterWindow = { point, rel, x, y }
    end
  end)
  local at = type(IndexOfAzerothCharDB) == "table" and IndexOfAzerothCharDB.meterWindow
  if type(at) == "table" and at[1] and at[2] then
    win:ClearAllPoints()
    win:SetPoint(at[1], UIParent, at[2], at[3] or 0, at[4] or 0)
  end
  tinsert(UISpecialFrames, "IndexOfAzerothMeter")
  parts = { filters = {}, holders = {} }

  local title = UI.Text(win, "GameFontNormalLarge", C.gold)
  title:SetPoint("TOPLEFT", win, "TOPLEFT", 12, -12)
  title:SetText(T["title"])
  parts.tabs = UI.Tabs(win, TAB_NAMES, function(tab) M.Open(tab) end, 440)
  parts.tabs:SetPoint("TOPLEFT", win, "TOPLEFT", 170, -10)
  local close = UI.FlatButton(win, T["close"], nil, function() win:Hide() end)
  UI.LayKeys({ close }, win, 0, 10, WIDTH, 60, 0, KEYS_H)
  close:ClearAllPoints()
  close:SetPoint("TOPRIGHT", win, "TOPRIGHT", -12, -10)

  parts.filterRow = CreateFrame("Frame", nil, win)
  parts.filterRow:SetPoint("TOPLEFT", win, "TOPLEFT", 12, -TOP)
  for i, filter in ipairs(FILTERS) do
    parts.filters[i] = UI.FlatButton(parts.filterRow, "", nil, function()
      local o, now = M.Opts(), 1
      for n, value in ipairs(filter.values) do
        if value == o[filter.opt] then now = n end
      end
      o[filter.opt] = filter.values[now % #filter.values + 1]
      M.Draw()
    end)
  end

  parts.left = UI.Text(parts.filterRow, "GameFontHighlightSmall", C.muted)
  parts.left:SetWidth(BODY_W)
  parts.body = CreateFrame("Frame", nil, win)
  parts.empty = UI.Text(parts.body, "GameFontHighlight", C.ivory, "CENTER")
  parts.empty:SetPoint("TOP", parts.body, "TOP", 0, -160)
  parts.empty:SetWidth(BODY_W - 80)
  for name, view in pairs(views) do
    local holder = CreateFrame("Frame", nil, parts.body)
    holder:SetAllPoints(parts.body)
    view.Build(holder)
    holder:Hide()
    parts.holders[name] = holder
  end
  ns.OnTick(win, T["part.sums"], nil, function()
    local st = state.pass
    if not (st and not st.done and views[state.tab].sums) or ns.InFight() then return end
    S.Step(st, M.STEP)
    M.Draw()
  end)
  win:Hide()
  state.built = true
end

local function Layout(view, left)
  local keysY = 0
  parts.filterRow:SetShown(view.filtered or false)
  if view.filtered then
    local o = M.Opts()
    for i, filter in ipairs(FILTERS) do parts.filters[i].label:SetText(T[filter.words[o[filter.opt]]]) end
    keysY = UI.LayKeys(parts.filters, parts.filterRow, 0, 0, BODY_W, 120, 4, KEYS_H) + KEYS_H + 4
    local lines = {}
    if left and left.noFoes > 0 then
      lines[#lines + 1] = ns.Count("game.meter.left.foes", left.noFoes, { key = T["filter.foes.all"] })
    end
    if left and left.noPlace > 0 then
      lines[#lines + 1] = ns.Count("game.meter.left.place", left.noPlace, { key = T["filter.place.all"] })
    end
    if left and left.byKills > 0 then
      lines[#lines + 1] = ns.Count("game.meter.left.kills", left.byKills)
    end
    if view.splits and left and left.split and left.noCond > 0 then
      lines[#lines + 1] = ns.Count("game.meter.compare.split.left", left.noCond)
    end
    parts.left:SetShown(#lines > 0)
    if #lines > 0 then
      parts.left:SetText(table.concat(lines, "\n"))
      parts.left:ClearAllPoints()
      parts.left:SetPoint("TOPLEFT", parts.filterRow, "TOPLEFT", 0, -keysY)
      keysY = keysY + math.ceil(Number(Call(parts.left.GetStringHeight, parts.left)) or 12) + 6
    end
    parts.filterRow:SetSize(BODY_W, keysY)
  end
  parts.body:ClearAllPoints()
  parts.body:SetPoint("TOPLEFT", win, "TOPLEFT", 12, -(TOP + keysY))
  parts.body:SetPoint("BOTTOMRIGHT", win, "BOTTOMRIGHT", -12, 12)
end

function M.Draw()
  if not (state.built and win:IsShown()) then return end
  if ns.InFight() then state.stale = true; return end
  state.stale = false
  local m, view = M.Store(), views[state.tab]
  parts.tabs:Pick(state.tab)

  local words, st
  if not m or #m.f == 0 then
    words = T["empty.none"]
  elseif view.sums then
    if not S.Fresh(state.pass) then state.pass = S.Begin() end
    st = state.pass
    if not st.done then
      words = Fill(T["working"], { done = Num(st.i), all = Num(st.all) })
    elseif st.n == 0 then
      words = T["empty.filter"]
    end
  end
  for name, holder in pairs(parts.holders) do holder:SetShown(name == state.tab and not words) end
  parts.empty:SetShown(words ~= nil)
  view.left = nil
  Layout(view, st)
  if words then parts.empty:SetText(words) else view.Draw(st) end
  if view.left then
    Layout(view, view.left)
    if view.Fit then view.Fit() end
  end
end

function M.Open(tab)
  if not win then Build() end
  if not state.built then return end
  state.tab = views[tab] and tab or state.tab
  win:Show()
  M.Draw()
end
function M.Toggle()
  if state.built and win:IsShown() then win:Hide() else M.Open() end
end
ns.meterWindow = function() return win end
M.pass = function() return state.pass end
M.shownWords = function() return parts and parts.empty:IsShown() and parts.empty:GetText() or nil end
M.fightTiles = function()
  local out = {}
  for i, tile in ipairs(Fight.tiles) do out[i] = tile.value:GetText() end
  return out
end
M.fightGraphWords = function() return Fight.chart.top:GetText() end
M.leftWords = function() return parts.left:IsShown() and parts.left:GetText() or nil end
M.verdictWords = function() return Compare.verdict.words:GetText() end
M.historyTarget = function(i) return History.Row(i).cells[2]:GetText() end
M.fightFoes = function()
  local rest = Fight.foesRest
  local out = { title = Fight.title:GetText(), main = Fight.foesMain:IsShown() and Fight.foesMain:GetText() or nil,
                rest = rest:IsShown() and (rest.name:GetText() .. "|" .. rest.amount:GetText() .. "|" .. rest.share:GetText()) or nil }
  for i, row in ipairs(Fight.foes) do
    if row:IsShown() then out[i] = row.name:GetText() .. "|" .. row.amount:GetText() .. "|" .. row.share:GetText() end
  end
  return out
end
M.spellCells = function(i)
  local cells = Spells.Row(i).cells
  return cells[2]:GetText() .. "|" .. cells[8]:GetText() .. "|" .. cells[6]:GetText()
end
ns.commands.meter = function(rest)
  local live = rest and rest:match("^live%s*(%a*)$")
  if live and M.Live then return M.Live(live) end
  if rest == "probe" and M.Probe then return M.Probe() end
  if rest == "probe report" and M.ProbeReport then return M.ProbeReport() end
  M.Toggle()
end

ns.On("PLAYER_LOGIN", function() if not win then Build() end end)
ns.On("PLAYER_REGEN_ENABLED", function() M.Draw() end)
M.Listen(function() M.Draw() end, "figures")
