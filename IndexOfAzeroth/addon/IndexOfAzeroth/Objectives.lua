-- The Index of Azeroth. Copyright 2026 Index Case <indexofazeroth@pm.me>. PolyForm Strict 1.0.0, see LICENSE.md.
local ADDON, ns = ...

local OBJECTIVE_TYPES = { monster = 1, item = 2, object = 3, event = 4, log = 5, reputation = 6, player = 7, progressbar = 8 }

local Plain = ns.Plain

local QUESTLOG_EVERY = 15
local QUEST_OBJECTIVES_MOST = 6
local Call = ns.Call

local POI_MAPS_MOST = 40
function ns.QuestPOIs()
  local out, maps = {}, {}
  local here = Plain(Call(C_Map.GetBestMapForUnit, "player"))
  if here then
    maps[1] = here
    local info = Call(C_Map.GetMapInfo, here)
    local parent = info and Plain(info.parentMapID)
    local zoneType = Enum and Enum.UIMapType and Enum.UIMapType.Zone or 3
    for _, child in ipairs(parent and Call(C_Map.GetMapChildrenInfo, parent, zoneType) or {}) do
      local id = type(child) == "table" and Plain(child.mapID)
      if id and id ~= here and #maps < POI_MAPS_MOST then maps[#maps + 1] = id end
    end
  end
  for _, m in ipairs(maps) do
    for _, p in ipairs(Call(C_QuestLog.GetQuestsOnMap, m) or {}) do
      local id, x, y = type(p) == "table" and Plain(p.questID), Plain(p.x), Plain(p.y)
      if id and x and y and not out[id] then out[id] = { map = m, x = x, y = y } end
    end
  end
  return out
end

function ns.QuestTimers()
  local out = {}
  for _, t in ipairs(Call(C_QuestLog.GetQuestTimers) or {}) do
    local id, left = type(t) == "table" and Plain(t.questID), type(t) == "table" and Plain(t.questTimer)
    if id and left then out[id] = left end
  end
  return out
end

local TIMER_SLACK = 5
local timerEnds = {}
function ns.QuestTimerEnds()
  local now, ends = Plain(Call(GetServerTime)), {}
  for id, left in pairs(now and ns.QuestTimers() or {}) do
    local was = timerEnds[id]
    ends[id] = (was and math.abs(was - (now + left)) <= TIMER_SLACK) and was or math.floor(now + left + 0.5)
  end
  timerEnds = ends
  return ends
end

local function LogEntries()
  local out = {}
  local pois = ns.QuestPOIs()
  local ends = ns.QuestTimerEnds()
  for i = 1, Plain(Call(C_QuestLog.GetNumQuestLogEntries)) or 0 do
    local info = Call(C_QuestLog.GetInfo, i)
    if type(info) == "table" and Plain(info.isHeader) then
      out[#out + 1] = { header = Plain(info.title) or "", folded = Plain(info.isCollapsed) and true or false }
    elseif type(info) == "table" and Plain(info.questID) and not Plain(info.isHidden) then
      local id = info.questID
      local complete = Plain(Call(C_QuestLog.IsComplete, id))
      local areas = pois[id] and not complete and ns.QuestAreas and ns.QuestAreas(id, pois[id].map) or nil
      if areas and #areas == 0 then areas = nil end
      local q = { id = id, index = i, level = Plain(info.level) or 0, title = Plain(info.title) or "", objectives = {}, poi = pois[id],
                  flags = (complete and 1 or 0) + (Plain(Call(C_QuestLog.IsFailed, id)) and 2 or 0)
                        + ((Plain(info.suggestedGroup) or 0) > 1 and 4 or 0) + (ends[id] and 8 or 0) + (areas and 16 or 0),
                  ends = ends[id], areas = areas }
      for _, o in ipairs(ns.QuestObjectives(id)) do
        if type(o) == "table" and #q.objectives < QUEST_OBJECTIVES_MOST then
          q.objectives[#q.objectives + 1] = { done = Plain(o.numFulfilled) or 0, need = Plain(o.numRequired) or 0,
                                              finished = Plain(o.finished) and 1 or 0, text = Plain(o.text) or "",
                                              type = OBJECTIVE_TYPES[Plain(o.type) or ""] or 0 }
        end
      end
      out[#out + 1] = q
    end
  end
  return out
end

function ns.QuestLogWants()
  local out, done = {}, {}
  for i = 1, Plain(Call(C_QuestLog.GetNumQuestLogEntries)) or 0 do
    local info = Call(C_QuestLog.GetInfo, i)
    local id = type(info) == "table" and not Plain(info.isHeader) and Plain(info.questID)
    for _, o in ipairs(ns.QuestObjectives(id)) do
      local text = type(o) == "table" and Plain(o.text)
      local name = type(text) == "string" and (text:match("^(.-) slain: %d+/%d+$") or text:match("^%d+/%d+ (.-) slain$")
        or Plain(o.type) == "monster" and text:match("^(.-): %d+/%d+$"))
      if name and name ~= "" and Plain(o.finished) then
        done[name] = true
      elseif name and name ~= "" and not out[name] then
        local left = (Plain(o.numRequired) or 0) - (Plain(o.numFulfilled) or 0)
        out[name] = left > 0 and string.format("%d left", left) or "wanted"
      end
    end
  end
  return out, done
end

local function WriteLogEntry(w, e)
  if e.header then
    w:u8(e.folded and 3 or 1); w:str(e.header, 40)
    return
  end
  w:u8(e.poi and 4 or 2); w:u24(e.id); w:u8(e.level); w:u8(e.flags); w:str(e.title, 48)
  w:u8(#e.objectives)
  for _, o in ipairs(e.objectives) do w:u8(o.done); w:u8(o.need); w:u8(o.finished); w:str(o.text, 40) end
  if e.poi then w:u16(e.poi.map); w:u16(e.poi.x * 10000); w:u16(e.poi.y * 10000) end
  if e.ends then w:var(e.ends) end
end

local questLog = ns.Pager({ type = 22, head = 1, every = QUESTLOG_EVERY,
  writeHead = function(w, page) w:u8(#page) end,
  entry = function(w, bytes) for _, b in ipairs(bytes) do w.bytes[#w.bytes + 1] = b end end,
  tailSize = function(bytes) return math.ceil(#bytes.types / 2) + (bytes.areas and 1 + 7 * #bytes.areas or 0) end,
  tail = function(w, page)
    for _, bytes in ipairs(page) do
      local t = bytes.types
      for k = 1, #t, 2 do w:u8(t[k] + (t[k + 1] or 0) * 16) end
    end
    for _, bytes in ipairs(page) do
      if bytes.areas then
        w:u8(#bytes.areas)
        for _, a in ipairs(bytes.areas) do w:u8(a.obj); w:u16(a.x * 10000); w:u16(a.y * 10000); w:u16(a.r) end
      end
    end
  end })
local TEXT_AGAIN = 30
local textTried = {}
local function QuestLogText(index, id)
  if not (GetQuestLogQuestText and C_QuestLog.SetSelectedQuest) then return end
  local was = Plain(Call(C_QuestLog.GetSelectedQuest))
  Call(C_QuestLog.SetSelectedQuest, id)
  local d, o = Call(GetQuestLogQuestText, index)
  if was ~= id then Call(C_QuestLog.SetSelectedQuest, was or 0) end
  d, o = ns.PlainText(d), ns.PlainText(o)
  return d ~= "" and d or nil, o ~= "" and o or nil
end
ns.QuestLogText = QuestLogText
function ns.KeepQuestText(entries)
  local db = IndexOfAzerothCharDB
  if type(db) ~= "table" then return end
  local was = type(db.questText) == "table" and db.questText or {}
  local kept = {}
  for _, e in ipairs(entries) do
    if e.id and e.index then
      local old = was[e.id]
      local now = GetTime()
      if type(old) == "table" then
        kept[e.id] = old
      elseif not textTried[e.id] or now - textTried[e.id] >= TEXT_AGAIN then
        local d, o = QuestLogText(e.index, e.id)
        if d or o then kept[e.id], textTried[e.id] = { d = d, o = o }, nil else textTried[e.id] = now end
      end
    end
  end
  db.questText = kept
end

local function BuildQuestLog(force)
  local parts, said = {}, {}
  local entries = LogEntries()
  for _, e in ipairs(entries) do
    local part = ns.NewWriter()
    WriteLogEntry(part, e)
    local types = {}
    for k, o in ipairs(e.objectives or {}) do types[k] = o.type end
    part.bytes.types, part.bytes.areas = types, e.areas
    local placed = {}
    for _, a in ipairs(e.areas or {}) do
      placed[#placed + 1] = string.format("%d:%d:%d:%d", a.obj, math.floor(a.x * 10000), math.floor(a.y * 10000), a.r)
    end
    parts[#parts + 1], said[#said + 1] = part.bytes, string.char(unpack(part.bytes)) .. string.char(unpack(types))
      .. table.concat(placed, ",")
  end
  questLog.Offer(parts, table.concat(said), force)
  ns.KeepQuestText(entries)
end
questLog.refill = BuildQuestLog

local AREA_GRID, AREA_MOST, AREA_EVERY = 48, 6, 0.5
local areaKept, areaWanted, areaFrame = {}, {}, nil

local function AreaFrame()
  if areaFrame == nil then
    local ok, f = pcall(CreateFrame, "QuestPOIFrame", nil, UIParent)
    areaFrame = ok and type(f) == "table" and f.UpdateMouseOverTooltip and f.DrawBlob and f or false
    if areaFrame then
      areaFrame:SetSize(512, 512)
      areaFrame:SetPoint("TOPLEFT", UIParent, "TOPLEFT", -4096, 4096)
      areaFrame:SetAlpha(0)
      areaFrame:Show()
    end
  end
  return areaFrame or nil
end

local function AreaHit(f, id, index, x, y)
  local ok, hit, n = pcall(f.UpdateMouseOverTooltip, f, x, y)
  if not ok or hit == nil or (hit ~= id and hit ~= index) then return nil end
  local objs = {}
  for k = 1, Plain(n) or 0 do
    local okk, o = pcall(f.GetTooltipIndex, f, k)
    if okk and Plain(o) then objs[#objs + 1] = Plain(o) end
  end
  if #objs == 0 then objs[1] = 0 end
  return objs
end

local function WorkAreas(id, map)
  local f = AreaFrame()
  if not f then return {} end
  pcall(f.SetMapID, f, map)
  pcall(f.DrawNone, f)
  pcall(f.DrawBlob, f, id, true)
  local index = C_QuestLog.GetLogIndexForQuestID and Plain(Call(C_QuestLog.GetLogIndexForQuestID, id))
  local cells = {}
  for gy = 0, AREA_GRID - 1 do
    for gx = 0, AREA_GRID - 1 do
      for _, o in ipairs(AreaHit(f, id, index, (gx + 0.5) / AREA_GRID, (gy + 0.5) / AREA_GRID) or {}) do
        cells[o] = cells[o] or {}
        cells[o][gy * AREA_GRID + gx] = true
      end
    end
  end
  pcall(f.DrawNone, f)
  local out = {}
  for o, held in pairs(cells) do
    local seen = {}
    for cell in pairs(held) do
      if not seen[cell] then
        local group, todo = {}, { cell }
        seen[cell] = true
        while #todo > 0 do
          local c = table.remove(todo)
          group[#group + 1] = c
          local gx, gy = c % AREA_GRID, math.floor(c / AREA_GRID)
          for _, d in ipairs({ { 1, 0 }, { -1, 0 }, { 0, 1 }, { 0, -1 } }) do
            local nx, ny = gx + d[1], gy + d[2]
            local nc = ny * AREA_GRID + nx
            if nx >= 0 and ny >= 0 and nx < AREA_GRID and ny < AREA_GRID and held[nc] and not seen[nc] then
              seen[nc] = true
              todo[#todo + 1] = nc
            end
          end
        end
        local sx, sy = 0, 0
        for _, c in ipairs(group) do sx, sy = sx + (c % AREA_GRID + 0.5) / AREA_GRID, sy + (math.floor(c / AREA_GRID) + 0.5) / AREA_GRID end
        local mx, my = sx / #group, sy / #group
        local cont, mn, mw = ns.Geo.WorldPos(map, mx, my)
        local reach = 0
        for _, c in ipairs(group) do
          local _, n, w = ns.Geo.WorldPos(map, (c % AREA_GRID + 0.5) / AREA_GRID, (math.floor(c / AREA_GRID) + 0.5) / AREA_GRID)
          if cont and n then reach = math.max(reach, ns.Geo.Dist(mn, mw, n, w)) end
        end
        local _, cn, cw = ns.Geo.WorldPos(map, 0, 0)
        local _, dn, dw = ns.Geo.WorldPos(map, 1 / AREA_GRID, 0)
        local half = cn and dn and ns.Geo.Dist(cn, cw, dn, dw) / 2 or 0
        out[#out + 1] = { obj = o, x = mx, y = my, r = math.min(65535, math.floor(reach + half + 0.5)), n = #group }
      end
    end
  end
  table.sort(out, function(a, b) return a.n > b.n end)
  while #out > AREA_MOST do table.remove(out) end
  return out
end

local areaWorker = CreateFrame("Frame")
areaWorker:Hide()
ns.areaWorker = areaWorker
ns.OnTick(areaWorker, "the quests' areas", AREA_EVERY, function(self)
  local id, map = next(areaWanted)
  if not id then return self:Hide() end
  areaWanted[id] = nil
  areaKept[id] = { map = map, list = WorkAreas(id, map) }
  if #areaKept[id].list > 0 then BuildQuestLog() end
end)

function ns.QuestAreas(id, map)
  local kept = areaKept[id]
  if kept and kept.map == map then return kept.list end
  if not AreaFrame() then return nil end
  areaWanted[id] = map
  areaWorker:Show()
  return nil
end
ns.QuestLogPending, ns.NextQuestLogFrame = questLog.Pending, questLog.Next
local LOG_SETTLE = 0.5
local logAsked = false
ns.On({ "QUEST_LOG_UPDATE", "QUEST_ACCEPTED", "QUEST_REMOVED", "QUEST_TURNED_IN", "PLAYER_ENTERING_WORLD" }, function()
  if logAsked then return end
  logAsked = true
  C_Timer.After(LOG_SETTLE, function() logAsked = false; BuildQuestLog() end)
end)
