-- The Index of Azeroth. Copyright 2026 Index Case <indexofazeroth@pm.me>. PolyForm Strict 1.0.0, see LICENSE.md.
local ADDON, ns = ...

local COLORS = {}
for kind, c in pairs(ns.UI.GUIDE) do COLORS[kind] = { c[1], c[2], c[3], 0.9 } end
local DIMMED, DIM_ALPHA = {}, 0.35
for kind, c in pairs(COLORS) do
  local grey = (c[1] + c[2] + c[3]) / 3
  DIMMED[kind] = { (c[1] + grey) / 2, (c[2] + grey) / 2, (c[3] + grey) / 2, DIM_ALPHA }
end
ns.GUIDE_LINE_DIM_ALPHA = DIM_ALPHA
local WORLD_THICKNESS, MINIMAP_THICKNESS = 3, 2.5
local EDGE = 2
local MINIMAP_YARDS = {
  indoor = { [0] = 300, 240, 180, 120, 80, 50 },
  outdoor = { [0] = 466 + 2 / 3, 400, 333 + 1 / 3, 266 + 2 / 6, 200, 133 + 1 / 3 },
}

local Plain, Call = ns.Plain, ns.Call

local function Enabled(key)
  return ns.Options().nav[key]
end

local TRACK_KINDS, LOOP_KINDS = { "e", "g", "h", "k" }, { "g", "h", "k" }
local function Running()
  if ns.GuideTarget and ns.GuideTarget() then return true end
  for _, kind in ipairs(TRACK_KINDS) do
    if ns.TrackTarget and ns.TrackTarget(kind) then return true end
  end
end

local function Drawings(key)
  if not Enabled(key) or not Running() then return end
  local continent, px, py = ns.PlayerWorldPos()
  if not continent then return end
  local out = {}
  local function along(t, color)
    if not t or t.continent ~= continent then return end
    if t.route and t.route:UnderWay(continent, px, py) then return end
    local pts = { { px, py } }
    if t.path and t.join and t.leg then
      pts[2] = t.join
      local b, from = t.path[t.leg], t.leg
      if t.join == t.path[#t.path] then from = #t.path + 1
      elseif b and b[1] == t.join[1] and b[2] == t.join[2] then from = t.leg + 1 end
      for i = from, #t.path do
        pts[#pts + 1] = t.path[i]
      end
    elseif t.path then
      for i = ns.NotBack(t.path, t.leg or 1, px, py, ns.RiseHere(t.path, t.leg or 1, px, py)), #t.path do
        pts[#pts + 1] = t.path[i]
      end
    else
      pts[2] = { t.wx, t.wy }
    end
    out[#out + 1] = { pts, color }
  end
  local corpse = ns.Ghost() and ns.CorpseRun()
  local colors = ns.Ghost() and DIMMED or COLORS
  local nav = ns.GuideTarget and ns.GuideTarget()
  if nav and nav ~= corpse then along(nav, colors[ns.NavLook(nav)]) end
  local e = ns.TrackTarget and ns.TrackTarget("e")
  along(e, colors.e)
  local epic = (ns.GuideInfo and ns.GuideInfo()) or (ns.PastedGuide and ns.PastedGuide())
  local s = epic and epic.cur and epic.steps[epic.cur]
  if s and s.loop and s.inst == continent then out[#out + 1] = { s.loop, colors.e } end
  for _, kind in ipairs(LOOP_KINDS) do
    local g = ns.TrackTarget and ns.TrackTarget(kind)
    local c = g and colors[g.look or kind]
    if g and g.continent == continent and g.loop then
      out[#out + 1] = { g.loop, c }
      if g.path or g.route then
        along(g, c)
      else
        local nx, ny = ns.NearestOnLoop(g, px, py)
        if nx then out[#out + 1] = { { { px, py }, { nx, ny } }, c } end
      end
    end
  end
  along(corpse, COLORS.corpse)
  return continent, out, px, py
end
ns.GuideDrawings = Drawings

local function Pool(parent)
  local pool = { lines = {} }
  function pool:Get(i, color)
    local line = self.lines[i]
    if not line then
      line = parent:CreateLine(nil, "OVERLAY")
      self.lines[i] = line
    end
    line:SetColorTexture(color[1], color[2], color[3], color[4])
    line:Show()
    return line
  end
  function pool:HideFrom(i)
    for k = i, #self.lines do self.lines[k]:Hide() end
  end
  return pool
end


function ns.MinimapOffset(north, west, facing, rotate, pixelsPerYard)
  local east = -west
  local x, y = east, north
  if rotate then
    x = east * math.cos(facing) + north * math.sin(facing)
    y = -east * math.sin(facing) + north * math.cos(facing)
  end
  return x * pixelsPerYard, y * pixelsPerYard
end

local function Side(p, q, t0, t1)
  if p == 0 then
    if q < 0 then return nil end
    return t0, t1
  end
  local t = q / p
  if p < 0 then return math.max(t0, t), t1 end
  return t0, math.min(t1, t)
end

function ns.ClipSegment(ax, ay, bx, by, r, square)
  local dx, dy = bx - ax, by - ay
  local t0, t1 = 0, 1
  if square then
    t0, t1 = Side(-dx, ax + r, t0, t1)
    if t0 then t0, t1 = Side(dx, r - ax, t0, t1) end
    if t0 then t0, t1 = Side(-dy, ay + r, t0, t1) end
    if t0 then t0, t1 = Side(dy, r - ay, t0, t1) end
    if not t0 then return nil end
  else
    local a = dx * dx + dy * dy
    local b = 2 * (ax * dx + ay * dy)
    local c = ax * ax + ay * ay - r * r
    if a == 0 then
      if c > 0 then return nil end
    else
      local disc = b * b - 4 * a * c
      if disc < 0 then return nil end
      local s = math.sqrt(disc)
      t0 = math.max(t0, (-b - s) / (2 * a))
      t1 = math.min(t1, (-b + s) / (2 * a))
    end
  end
  if t0 > t1 then return nil end
  return ax + dx * t0, ay + dy * t0, ax + dx * t1, ay + dy * t1
end

function ns.MinimapReach()
  local zoom = Minimap and Plain(Call(Minimap.GetZoom, Minimap)) or 0
  local yards = MINIMAP_YARDS[Plain(Call(IsIndoors)) and "indoor" or "outdoor"][zoom] or MINIMAP_YARDS.outdoor[0]
  local square = GetMinimapShape and Plain(Call(GetMinimapShape)) == "SQUARE"
  return yards / 2, square and true or false, Plain(Call(GetCVar, "rotateMinimap")) == "1", Plain(Call(GetPlayerFacing)) or 0
end

function ns.AtRing(ring, px, py, margin, open, reach)
  if not ring or #ring < 2 then return false end
  local last = #ring - (open and #ring > 2 and 2 or 1)
  if not open then
    local inside = false
    for k = 1, last do
      local a, b = ring[k], ring[k + 1]
      if (a[2] > py) ~= (b[2] > py) and px < a[1] + (py - a[2]) * (b[1] - a[1]) / (b[2] - a[2]) then inside = not inside end
    end
    if inside then return true end
  end
  local r, square, rotate, facing = ns.MinimapReach()
  r = r * (reach or 1) + (margin or 0)
  for k = 1, last do
    local ax, ay = ns.MinimapOffset(ring[k][1] - px, ring[k][2] - py, facing, rotate, 1)
    local bx, by = ns.MinimapOffset(ring[k + 1][1] - px, ring[k + 1][2] - py, facing, rotate, 1)
    if ns.ClipSegment(ax, ay, bx, by, r, square) then return true end
  end
  return false
end


local miniFrame, miniPool
local function DrawMinimap()
  if not Minimap then return end
  if not miniFrame then
    miniFrame = CreateFrame("Frame", nil, Minimap)
    miniFrame:SetAllPoints(Minimap)
    miniFrame:SetFrameLevel((Plain(Call(Minimap.GetFrameLevel, Minimap)) or 1) + 5)
    miniPool = Pool(miniFrame)
  end
  local n = 0
  local continent, drawings, px, py = Drawings("line")
  local width = continent and Plain(Call(Minimap.GetWidth, Minimap))
  if continent and width and width > 0 and Plain(Call(Minimap.IsVisible, Minimap)) then
    local reach, square, rotate, facing = ns.MinimapReach()
    local scale, half = width / (2 * reach), width / 2 - EDGE
    for _, d in ipairs(drawings) do
      local x0, y0
      for _, p in ipairs(d[1]) do
        local x, y = ns.MinimapOffset(p[1] - px, p[2] - py, facing, rotate, scale)
        if x0 then
          local x1, y1, x2, y2 = ns.ClipSegment(x0, y0, x, y, half, square)
          if x1 then
            n = n + 1
            local line = miniPool:Get(n, d[2])
            line:SetThickness(MINIMAP_THICKNESS)
            line:SetStartPoint("CENTER", miniFrame, x1, y1)
            line:SetEndPoint("CENTER", miniFrame, x2, y2)
          end
        end
        x0, y0 = x, y
      end
    end
  end
  if miniPool then miniPool:HideFrom(n + 1) end
end


local worldFrame, worldPool
local worldInfo = {}

local bounds = {}
local function MapBounds(mapID)
  if bounds[mapID] == nil then
    local c0, ax, ay = ns.Geo.WorldPos(mapID, 0, 0)
    local c1, bx, by = ns.Geo.WorldPos(mapID, 1, 1)
    ax, ay, bx, by = Plain(ax), Plain(ay), Plain(bx), Plain(by)
    bounds[mapID] = (c0 and c0 == c1 and ax and bx and ax ~= bx and ay ~= by) and { c0, ax, ay, bx, by } or false
  end
  return bounds[mapID] or nil
end

function ns.WorldToMap(mapID, continent, north, west)
  local m = MapBounds(mapID)
  if not m or m[1] ~= continent then return nil end
  return (m[3] - west) / (m[3] - m[5]), (m[2] - north) / (m[2] - m[4])
end

local function DrawWorld()
  if not (WorldMapFrame and WorldMapFrame:IsShown() and WorldMapFrame.GetCanvas) then
    if worldPool then worldPool:HideFrom(1) end
    return
  end
  local canvas = WorldMapFrame:GetCanvas()
  if not worldFrame then
    worldFrame = CreateFrame("Frame", nil, canvas)
    worldFrame:SetAllPoints(canvas)
    worldPool = Pool(worldFrame)
  end
  worldFrame:SetFrameStrata(Plain(Call(canvas.GetFrameStrata, canvas)) or "HIGH")
  worldFrame:SetFrameLevel(math.min(9000, (Plain(Call(canvas.GetFrameLevel, canvas)) or 1) + 2000))
  local n = 0
  local continent, drawings = Drawings("mapLine")
  local pts = continent and drawings[1] and drawings[1][1]
  local mapID = Plain(Call(WorldMapFrame.GetMapID, WorldMapFrame))
  local w, h = canvas:GetWidth(), canvas:GetHeight()
  local scale = Plain(Call(WorldMapFrame.GetCanvasScale, WorldMapFrame)) or 1
  worldInfo = { map = mapID, continent = continent, points = pts and #pts or 0, w = w, h = h, scale = scale,
                bounds = mapID and MapBounds(mapID), level = worldFrame:GetFrameLevel() }
  if continent and mapID then
    for k, d in ipairs(drawings) do
      local x0, y0
      for i, p in ipairs(d[1]) do
        local x, y = ns.WorldToMap(mapID, continent, p[1], p[2])
        if k == 1 and i == 1 then worldInfo.first = x and string.format("%.3f, %.3f", x, y) or "off this map" end
        if x and x0 then
          n = n + 1
          local line = worldPool:Get(n, d[2])
          line:SetThickness(WORLD_THICKNESS / scale)
          line:SetStartPoint("TOPLEFT", worldFrame, x0 * w, -y0 * h)
          line:SetEndPoint("TOPLEFT", worldFrame, x * w, -y * h)
        end
        x0, y0 = x, y
      end
    end
  end
  worldInfo.lines = n
  worldPool:HideFrom(n + 1)
end

function ns.PrintLines()
  local i = worldInfo
  local t = ns.GuideTarget and ns.GuideTarget()
  if not Enabled("mapLine") then ns.Print("The world map line is off. Type /ioa lines on to turn both lines back on.") end
  ns.Print(t and string.format("guiding to %s, %s", t.name, t.path and (#t.path .. " bends") or "no path, straight")
    or "No guide is running in the game.")
  ns.Print(string.format("world map: %s, map %s, continent %s, %d points, %d lines, first %s",
    WorldMapFrame and WorldMapFrame:IsShown() and "open" or "closed (open it and try again)", tostring(i.map),
    tostring(i.continent), i.points or 0, i.lines or 0, tostring(i.first)))
  ns.Print(string.format("canvas %.0f x %.0f, scale %.2f, line frame level %s, map bounds %s", i.w or 0, i.h or 0, i.scale or 0,
    tostring(i.level), i.bounds and string.format("continent %d, %.0f %.0f to %.0f %.0f", unpack(i.bounds)) or "none"))
end

if WorldMapFrame and WorldMapFrame.AddDataProvider and MapCanvasDataProviderMixin and CreateFromMixins then
  local provider = CreateFromMixins(MapCanvasDataProviderMixin)
  function provider:RefreshAllData() DrawWorld() end
  function provider:RemoveAllData() if worldPool then worldPool:HideFrom(1) end end
  function provider:OnCanvasScaleChanged() DrawWorld() end
  pcall(WorldMapFrame.AddDataProvider, WorldMapFrame, provider)
end

ns.OnTick(CreateFrame("Frame"), "the guide line on the minimap", 0.05, function() DrawMinimap() end)
ns.OnTick(CreateFrame("Frame"), "the guide line on the world map", 0.2, function() DrawWorld() end)

ns.On("PLAYER_LOGIN", function()
  if type(IndexOfAzerothCharDB) == "table" and IndexOfAzerothCharDB.noLines then
    IndexOfAzerothCharDB.noLines = nil
    local nav = ns.Options().nav
    nav.line, nav.mapLine = false, false
    ns.Print("Options, Navigation now keeps the lines you switched off with /ioa lines, so the minimap and world map lines are off on every character.")
  end
  ns.OnOptions(function() DrawMinimap(); DrawWorld() end)
end)

ns.DrawGuideLines = function() DrawMinimap(); DrawWorld() end
