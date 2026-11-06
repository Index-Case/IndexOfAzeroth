-- The Index of Azeroth. Copyright 2026 Index Case <indexofazeroth@pm.me>. PolyForm Strict 1.0.0, see LICENSE.md.
local ADDON, ns = ...

local function Plain(v)
  if (issecretvalue and issecretvalue(v)) or v == nil then return nil end
  return v
end
local function Pass(ok, ...)
  if ok then return ... end
end
local function Call(f, ...)
  if f then return Pass(pcall(f, ...)) end
end
ns.Plain, ns.Pass, ns.Call = Plain, Pass, Call
function ns.InFight() return Plain(Call(UnitAffectingCombat, "player")) and true or false end
local function PlainText(v)
  v = Plain(v)
  if type(v) == "string" then return v end
end
local function PlainNumber(v)
  v = Plain(v)
  if type(v) == "number" then return v end
end
ns.PlainText, ns.PlainNumber = PlainText, PlainNumber

local failed = {}
function ns.Report(what, err)
  if failed[what] then return end
  failed[what] = true
  if ns.Print then ns.Print("The addon hit an error (" .. what .. "): " .. tostring(err)) end
end

function ns.OnTick(frame, what, every, fn)
  local since = 0
  frame:SetScript("OnUpdate", function(self, dt)
    if every then
      since = since + dt
      if since < every then return end
      dt, since = since, 0
    end
    local ok, err = pcall(fn, self, dt)
    if not ok then ns.Report(what, err) end
  end)
end

local hub = CreateFrame("Frame")
local heard = {}
ns.eventListeners = heard
local function Listening(event)
  local units, n, any = {}, 0, false
  for _, l in ipairs(heard[event]) do
    if not l.unit then any = true elseif not units[l.unit] then units[l.unit], n = true, n + 1; units[n] = l.unit end
  end
  pcall(hub.UnregisterEvent, hub, event)
  local ok, err
  if any or n > 2 or not hub.RegisterUnitEvent then
    ok, err = pcall(hub.RegisterEvent, hub, event)
  else
    ok, err = pcall(hub.RegisterUnitEvent, hub, event, units[1], units[2])
  end
  if not ok then ns.Report("listening to " .. event, err) end
end
function ns.On(events, fn, unit)
  local info = debug and debug.getinfo and debug.getinfo(fn, "S")
  local where = info and string.format(" (%s %d)", tostring(info.source):match("([^/\\@]+)$") or "?", info.linedefined or 0) or ""
  for _, event in ipairs(type(events) == "table" and events or { events }) do
    heard[event] = heard[event] or {}
    table.insert(heard[event], { fn = fn, unit = unit, what = event .. " listener" .. where })
    Listening(event)
  end
end
hub:SetScript("OnEvent", function(_, event, ...)
  local list = heard[event]
  if not list then return end
  for i = 1, #list do
    local l = list[i]
    if not l.unit or l.unit == ... then
      local ok, err = pcall(l.fn, event, ...)
      if not ok then ns.Report(l.what, err) end
    end
  end
end)

local VERSION = 4
local HEADER_BLOCKS = 13
local MAX_BLOCKS = 128
ns.MAX_PAYLOAD = (MAX_BLOCKS - HEADER_BLOCKS) * 3
local MAX_ROWS = 8
ns.MAX_ROWS = MAX_ROWS
ns.MAX_WIDE_PAYLOAD = ns.MAX_PAYLOAD + (MAX_ROWS - 1) * MAX_BLOCKS * 3
local CALIBRATION = { 0, 36, 73, 109, 146, 182, 219 }

local frame = CreateFrame("Frame", "IndexOfAzerothStrip")
frame:SetFrameStrata("TOOLTIP")
frame:SetFrameLevel(9000)
frame:SetPoint("TOPLEFT", 0, 0)
frame:SetSize(1, 1)
frame:Hide()

local blocks, shown = {}, {}
local seq = 0
local blockPixels = 4
local unit = 1
local rowsMade, rowsUp = 1, 1

local hover = CreateFrame("Frame", nil, frame)
hover:SetHeight(16)
hover:EnableMouse(true)
local function PlaceHover()
  hover:ClearAllPoints()
  hover:SetPoint("TOPLEFT", frame, "BOTTOMLEFT", 0, -(rowsUp - 1) * unit)
  hover:SetWidth(MAX_BLOCKS * unit)
end
PlaceHover()

local function Place(tex, i)
  tex:ClearAllPoints()
  tex:SetPoint("TOPLEFT", frame, "TOPLEFT", (i % MAX_BLOCKS) * unit, -math.floor(i / MAX_BLOCKS) * unit)
  tex:SetSize(unit, unit)
end

local function Block(i)
  local tex = blocks[i]
  if not tex then
    tex = frame:CreateTexture(nil, "OVERLAY")
    if tex.SetSnapToPixelGrid then tex:SetSnapToPixelGrid(false) end
    if tex.SetTexelSnappingBias then tex:SetTexelSnappingBias(0) end
    blocks[i] = tex
    Place(tex, i)
  end
  return tex
end

local function PixelSize()
  local _, physicalHeight = GetPhysicalScreenSize()
  return 768 / physicalHeight / frame:GetEffectiveScale()
end

function ns.LayoutStrip(size)
  blockPixels = size or blockPixels
  unit = PixelSize() * blockPixels
  for i = 0, rowsMade * MAX_BLOCKS - 1 do Place(Block(i), i) end
  frame:SetSize(MAX_BLOCKS * unit, unit)
  PlaceHover()
  wipe(shown)
end

function ns.StripRows(n)
  n = math.max(1, math.min(MAX_ROWS, math.floor(n)))
  if n == rowsUp then return end
  for r = 1, math.max(n, rowsMade) - 1 do
    for c = 0, MAX_BLOCKS - 1 do Block(r * MAX_BLOCKS + c):SetShown(r < n) end
  end
  rowsMade, rowsUp = math.max(rowsMade, n), n
  PlaceHover()
end
function ns.StripRowsUp() return rowsUp end

local function Paint(i, r, g, b)
  local key = r * 65536 + g * 256 + b
  if shown[i] == key then return end
  shown[i] = key
  Block(i):SetColorTexture(r / 255, g / 255, b / 255, 1)
end

local CHECK_PRIME, CHECK_BASE = 4294967291, 1048583
local function Check(n, s, bytes)
  local p, m = CHECK_PRIME, CHECK_BASE
  local h = ((n % 256) * m + math.floor(n / 256)) % p
  h = (h * m + s) % p
  for i = 1, n do h = (h * m + bytes[i]) % p end
  return h
end
ns.FrameCheck = Check

function ns.DrawStrip(bytes, wide)
  local n = #bytes
  local most = wide and ns.MAX_WIDE_PAYLOAD or ns.MAX_PAYLOAD
  if n > most then
    ns.Report("strip frame " .. tostring(bytes[1]), string.format("the frame is %d bytes and the strip takes %d", n, most))
    return false
  end
  local rows = n > ns.MAX_PAYLOAD and 1 + math.ceil((n - ns.MAX_PAYLOAD) / (MAX_BLOCKS * 3)) or 1
  if rows > rowsUp then ns.StripRows(rows) end
  seq = (seq + 1) % 256
  local check = Check(n, seq, bytes)
  Paint(0, 255, 0, 255)
  Paint(1, 0, 255, 0)
  Paint(2, 255, 0, 255)
  for i, level in ipairs(CALIBRATION) do Paint(2 + i, level, level, level) end
  Paint(10, math.floor(check / 65536) % 256, math.floor(check / 16777216), 0)
  Paint(11, n % 256, math.floor(n / 256), seq)
  Paint(12, check % 256, math.floor(check / 256) % 256, VERSION)
  for block = 0, rows * MAX_BLOCKS - HEADER_BLOCKS - 1 do
    local at = block * 3
    Paint(HEADER_BLOCKS + block, bytes[at + 1] or 0, bytes[at + 2] or 0, bytes[at + 3] or 0)
  end
  return true
end

function ns.WriteU32(w, v)
  v = math.max(0, math.min(4294967295, math.floor(tonumber(Plain(v)) or 0)))
  w:u16(v % 65536)
  w:u16(math.floor(v / 65536))
end

function ns.ShowStrip(on)
  frame:SetShown(on)
end

hover:SetScript("OnEnter", function(self)
  GameTooltip:SetOwner(self, "ANCHOR_NONE")
  GameTooltip:SetPoint("TOPLEFT", self, "BOTTOMLEFT", 0, -4)
  GameTooltip:AddLine("Index strip")
  GameTooltip:AddLine("These coloured pixels send the character's position and progress to the Index of Azeroth.", 0.8, 0.8, 0.8, true)
  GameTooltip:AddLine("Keep this corner of the game window uncovered so the Index can read them.", 0.8, 0.8, 0.8, true)
  GameTooltip:Show()
end)
hover:SetScript("OnLeave", function() GameTooltip:Hide() end)

local PICTURE = { "Brightness", "Contrast", "Gamma" }
local off = {}

local function Shown(v)
  local n = tonumber(v)
  if not n then return tostring(v) end
  return (string.format("%.2f", n):gsub("%.?0+$", ""))
end

local warn = CreateFrame("Frame", nil, hover)
warn:SetSize(16, 16)
warn:SetPoint("LEFT", hover, "LEFT", 2, 0)
warn:EnableMouse(true)
local mark = warn:CreateFontString(nil, "OVERLAY", "GameFontNormalLarge")
mark:SetPoint("CENTER")
mark:SetText("!")
mark:SetTextColor(1, 0.3, 0.2)
warn:Hide()
warn:SetScript("OnEnter", function(self)
  GameTooltip:SetOwner(self, "ANCHOR_NONE")
  GameTooltip:SetPoint("TOPLEFT", self, "BOTTOMLEFT", 0, -4)
  GameTooltip:AddLine("The Index may not be able to read the strip", 1, 0.3, 0.2)
  for _, line in ipairs(off) do GameTooltip:AddLine(line, 1, 1, 1, true) end
  GameTooltip:AddLine("Set it back to its default in the game's options.", 0.8, 0.8, 0.8, true)
  GameTooltip:Show()
end)
warn:SetScript("OnLeave", function() GameTooltip:Hide() end)

function ns.CheckPicture()
  wipe(off)
  if GetCVar and GetCVarDefault then
    for _, s in ipairs(PICTURE) do
      local now, default = GetCVar(s), GetCVarDefault(s)
      if now ~= nil and default ~= nil and Shown(now) ~= Shown(default) then
        off[#off + 1] = string.format("%s is %s, its default is %s", s, Shown(now), Shown(default))
      end
    end
  end
  warn:SetShown(#off > 0)
end
ns.On({ "PLAYER_LOGIN", "CVAR_UPDATE" }, ns.CheckPicture)

function ns.Said(bytes, part)
  return string.char(unpack(bytes, 1, math.min(part or #bytes, #bytes)))
end


local Writer = {}
Writer.__index = Writer

function ns.NewWriter() return setmetatable({ bytes = {} }, Writer) end

function ns.WriteFitting(w, list, write, most)
  local at = #w.bytes + 1
  w:u8(0)
  local n = 0
  for _, entry in ipairs(list) do
    local part = ns.NewWriter()
    write(part, entry)
    if #w.bytes + #part.bytes > (most or ns.MAX_PAYLOAD) or n == 255 then break end
    for _, b in ipairs(part.bytes) do w.bytes[#w.bytes + 1] = b end
    n = n + 1
  end
  w.bytes[at] = n
  return n
end

local function Num(v)
  v = tonumber(Plain(v))
  if not v or v ~= v or v == math.huge or v == -math.huge then return 0 end
  return v
end

function Writer:u8(v)
  v = math.floor(Num(v))
  if v < 0 then v = 0 elseif v > 255 then v = 255 end
  self.bytes[#self.bytes + 1] = v
end

function Writer:u16(v)
  v = math.floor(Num(v))
  if v < 0 then v = 0 elseif v > 65535 then v = 65535 end
  self:u8(v % 256); self:u8(math.floor(v / 256))
end

function Writer:i16(v)
  v = math.floor(Num(v) + 0.5)
  if v < -32768 then v = -32768 elseif v > 32767 then v = 32767 end
  if v < 0 then v = v + 65536 end
  self:u16(v)
end

function Writer:u24(v)
  v = math.floor(Num(v))
  if v < 0 then v = 0 elseif v > 16777215 then v = 16777215 end
  self:u8(v % 256); self:u8(math.floor(v / 256) % 256); self:u8(math.floor(v / 65536))
end

function Writer:var(v)
  v = math.max(0, math.floor(Num(v)))
  while v >= 128 do
    self:u8(v % 128 + 128)
    v = math.floor(v / 128)
  end
  self:u8(v)
end

function ns.VarSize(v)
  local n = 1
  v = math.max(0, math.floor(Num(v)))
  while v >= 128 do n, v = n + 1, math.floor(v / 128) end
  return n
end

function Writer:str(s, max)
  s = PlainText(s) or ""
  if #s > max then
    s = s:sub(1, max)
    s = s:gsub("[\192-\255][\128-\191]*$", "")
  end
  self:u8(#s)
  for i = 1, #s do self:u8(s:byte(i)) end
end

function ns.Pager(spec)
  local p, pages, sent, gen, sig, built = {}, nil, 0, 0, nil, GetTime()
  local measure = ns.NewWriter()
  local function Size(e, before)
    wipe(measure.bytes)
    spec.entry(measure, e, before)
    return #measure.bytes + (spec.tailSize and spec.tailSize(e) or 0)
  end
  function p.Offer(list, said, again)
    if said == sig and not again then return end
    if said ~= sig then gen, sig = gen % 255 + 1, said end
    local room, page, bytes = ns.MAX_PAYLOAD - 4 - spec.head, nil, 0
    pages = {}
    for _, e in ipairs(list) do
      local size = page and Size(e, page[#page])
      if not page or bytes + size > room then
        page, size = {}, Size(e, nil)
        pages[#pages + 1], bytes = page, 0
      end
      page[#page + 1], bytes = e, bytes + size
    end
    if #pages == 0 then pages[1] = {} end
    sent, built = 0, GetTime()
  end
  function p.Pending()
    if not pages and spec.every and p.refill and GetTime() - built >= spec.every then
      built = GetTime()
      p.refill(true)
    end
    return pages ~= nil
  end
  function p.Next()
    if not pages then return nil end
    sent = sent + 1
    local page, all = pages[sent], #pages
    if sent >= all then pages = nil end
    local w = ns.NewWriter()
    w:u8(spec.type); w:u8(gen); w:u8(sent); w:u8(all)
    spec.writeHead(w, page)
    for k, e in ipairs(page) do spec.entry(w, e, page[k - 1]) end
    if spec.tail then spec.tail(w, page) end
    return w.bytes
  end
  return p
end

function ns.IdPager(frameType, every)
  return ns.Pager({ type = frameType, head = 2, every = every,
                    writeHead = function(w, page) w:u16(#page) end,
                    entry = function(w, id, before) if before then w:var(id - before) else w:u24(id) end end })
end
