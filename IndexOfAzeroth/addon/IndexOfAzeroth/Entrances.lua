-- The Index of Azeroth. Copyright 2026 Index Case <indexofazeroth@pm.me>. PolyForm Strict 1.0.0, see LICENSE.md.
local ADDON, ns = ...

local MAX_ENTRIES = 10

local Call = ns.Call

local function EntrancesFor(mapID)
  local get = C_EncounterJournal and C_EncounterJournal.GetDungeonEntrancesForMap
  local list = mapID and Call(get, mapID)
  return type(list) == "table" and list or {}
end

function ns.CollectEntrances()
  local mapID = C_Map.GetBestMapForUnit("player")
  local out, seen = {}, {}
  if not mapID or (issecretvalue and issecretvalue(mapID)) then return mapID, out end
  local info = Call(C_Map.GetMapInfo, mapID)
  local sources = { mapID }
  if info and info.parentMapID and info.parentMapID > 0 then sources[#sources + 1] = info.parentMapID end
  for _, source in ipairs(sources) do
    for _, e in ipairs(EntrancesFor(source)) do
      local x, y = e.position and e.position.x, e.position and e.position.y
      if source ~= mapID and x then
        local continent, wx, wy = ns.Geo.WorldPos(source, x, y)
        if continent then x, y = ns.Geo.MapPos(continent, wx, wy, mapID) else x, y = nil, nil end
      end
      if x and e.name and not seen[e.name] and #out < MAX_ENTRIES then
        seen[e.name] = true
        out[#out + 1] = { name = e.name, x = x, y = y, raid = (e.atlasName or ""):lower():find("raid") and 1 or 0 }
      end
    end
  end
  return mapID, out
end

function ns.EncodeEntrances()
  local mapID, list = ns.CollectEntrances()
  local w = ns.NewWriter()
  w:u8(5)
  w:u16(mapID or 0)
  ns.WriteFitting(w, list, function(p, e)
    p:str(e.name, 32)
    p:i16(math.max(-32767, math.min(32767, e.x * 10000)))
    p:i16(math.max(-32767, math.min(32767, e.y * 10000)))
    p:u8(e.raid)
  end)
  return w.bytes
end

function ns.PrintEntrances()
  local mapID = C_Map.GetBestMapForUnit("player")
  local info = mapID and Call(C_Map.GetMapInfo, mapID)
  if not (C_EncounterJournal and C_EncounterJournal.GetDungeonEntrancesForMap) then
    return ns.Print("This client has no C_EncounterJournal.GetDungeonEntrancesForMap.")
  end
  for _, source in ipairs({ mapID, info and info.parentMapID }) do
    if source and source > 0 then
      local list = EntrancesFor(source)
      ns.Print(string.format("map %d: %d entrances", source, #list))
      for _, e in ipairs(list) do
        ns.Print(string.format("  %s at %.1f, %.1f (%s)", tostring(e.name), (e.position and e.position.x or 0) * 100,
          (e.position and e.position.y or 0) * 100, tostring(e.atlasName)))
      end
    end
  end
end
