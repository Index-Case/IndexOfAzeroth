-- The Index of Azeroth. Copyright 2026 Index Case <indexofazeroth@pm.me>. PolyForm Strict 1.0.0, see LICENSE.md.
local ADDON, ns = ...

local Plain, Call = ns.Plain, ns.Call
local Geo = {}
ns.Geo = Geo

local point = CreateVector2D(0, 0)
local function At(x, y)
  point.x, point.y = x, y
  return point
end

function Geo.Vector(x, y) return CreateVector2D(x, y) end

function Geo.WorldPos(mapID, x, y)
  local continent, world = Call(C_Map.GetWorldPosFromMapPos, mapID, At(x, y))
  if continent and world then return continent, world.x, world.y end
end

function Geo.MapPos(continent, wx, wy, mapID)
  local map, pos = Call(C_Map.GetMapPosFromWorldPos, continent, At(wx, wy), mapID)
  if pos then return pos.x, pos.y, map end
  return nil, nil, map
end

function Geo.ZoneAt(continent, wx, wy)
  local x, y, map = Geo.MapPos(continent, wx, wy)
  local info = x and map and Call(C_Map.GetMapInfoAtPosition, map, x, y)
  local id = info and Plain(info.mapID)
  if id then return id, Plain(info.name) end
end

local MOVE_STEP, MOVE_WINDOW, MOVE_LEAST = 0.25, 2, 4
local moves = {}
local function Fresh(now)
  while moves[1] and now - moves[1][1] > MOVE_WINDOW do table.remove(moves, 1) end
end
local function Moved(continent, x, y)
  local now, last = GetTime(), moves[#moves]
  if last and now - last[1] < MOVE_STEP then return end
  if last and last[2] ~= continent then moves = {} end
  moves[#moves + 1] = { now, continent, x, y }
  Fresh(now)
end
function Geo.Speed()
  Fresh(GetTime())
  if #moves <= MOVE_LEAST then return nil end
  local speeds = {}
  for i = 2, #moves do
    local a, b = moves[i - 1], moves[i]
    speeds[i - 1] = Geo.Dist(a[3], a[4], b[3], b[4]) / (b[1] - a[1])
  end
  table.sort(speeds)
  return speeds[math.ceil(#speeds / 2)]
end

function Geo.PlayerWorldPos()
  local mapID = C_Map.GetBestMapForUnit("player")
  local pos = mapID and Call(C_Map.GetPlayerMapPosition, mapID, "player")
  if not pos or (issecretvalue and issecretvalue(pos.x)) then return end
  local continent, x, y = Geo.WorldPos(mapID, pos.x, pos.y)
  if continent then Moved(continent, x, y) end
  return continent, x, y
end
ns.WorldPos, ns.PlayerWorldPos = Geo.WorldPos, Geo.PlayerWorldPos

function Geo.Dist(ax, ay, bx, by) return math.sqrt((ax - bx) ^ 2 + (ay - by) ^ 2) end

function Geo.NearestOnSegment(ax, ay, bx, by, px, py)
  local dx, dy = bx - ax, by - ay
  local len2 = dx * dx + dy * dy
  local t = len2 > 0 and math.max(0, math.min(1, ((px - ax) * dx + (py - ay) * dy) / len2)) or 0
  local qx, qy = ax + dx * t, ay + dy * t
  return t, qx, qy, math.sqrt((qx - px) ^ 2 + (qy - py) ^ 2), len2
end

function Geo.NearLine(line, x, y)
  local n, best = #(line or {}), math.huge
  if n == 1 then return Geo.Dist(line[1][1], line[1][2], x, y) end
  for k = 2, n do
    local a, b = line[k - 1], line[k]
    best = math.min(best, (select(4, Geo.NearestOnSegment(a[1], a[2], b[1], b[2], x, y))))
  end
  return best
end

function Geo.Creature(guid)
  if type(guid) ~= "string" then return end
  local kind, _, _, map, uid, npc, spawn = strsplit("-", guid)
  if kind ~= "Creature" and kind ~= "Vehicle" then return end
  return kind, tonumber(map), uid, tonumber(npc), spawn and tonumber(spawn:sub(-8), 16)
end

function Geo.UnitKey(unit)
  local guid = Plain(Call(UnitGUID, unit))
  if guid == nil then
    if Plain(Call(UnitExists, unit)) then return nil end
    return false
  end
  local kind, _, _, _, _, id = strsplit("-", guid)
  if kind == "Creature" or kind == "Vehicle" then return tonumber(id) end
  if kind == "GameObject" then return tonumber(id) and ("o" .. id) or nil end
  return false
end
function Geo.GiverKey(s)
  if s.ni then return s.ni end
  if s.oi then return "o" .. s.oi end
end
function Geo.Is(key, name, keys, names, loose)
  if key == false then return false end
  if key ~= nil and keys and keys[key] then return true end
  if name == nil then return false end
  if key == nil then return (names and names[name]) == true end
  return (loose and loose[name]) == true
end
function Geo.UnitIs(unit, keys, names, loose)
  return Geo.Is(Geo.UnitKey(unit), Plain(Call(UnitName, unit)), keys, names, loose)
end
function Geo.IsOne(key, name, own, npc)
  if key == false or not (own or npc) then return false end
  if key ~= nil and own then return key == own end
  return name ~= nil and name == npc
end
function Geo.IsGiver(s, key, name) return Geo.IsOne(key, name, Geo.GiverKey(s), s.npc) end
