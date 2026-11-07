-- The Index of Azeroth. Copyright 2026 Index Case <indexofazeroth@pm.me>. PolyForm Strict 1.0.0, see LICENSE.md.
local ADDON, ns = ...


local ARRIVE_YARDS = ns.Rules.guide.arrive
local ON_LOOP_YARDS = 25
local LOOP_AHEAD_YARDS = 30
local RideText = ns.RideText
local GUIDE, CREAM = ns.UI.GUIDE, ns.UI.C.ivory
local EPIC_ICON = "Interface\\AddOns\\IndexOfAzeroth\\Media\\arrow_epic"
local KINDS = {
  e = { frame = "IndexOfAzerothEpicArrow", label = "Quest epic", text = CREAM, y = -250,
        art = { { 1.0, { 1, 1, 1 }, EPIC_ICON } } },
  g = { frame = "IndexOfAzerothGrindArrow", label = "Loop", text = GUIDE.g, y = -350, art = { { 1.0, GUIDE.g } } },
  h = { frame = "IndexOfAzerothGatherArrow", label = "Gathering", text = GUIDE.h, y = -350, art = { { 1.0, GUIDE.h } } },
  k = { frame = "IndexOfAzerothSkinArrow", label = "Skinning", text = GUIDE.k, y = -350, art = { { 1.0, GUIDE.k } } },
}
local LOOPS = { "g", "h", "k" }
local LOOKS = {
  tokens = { g = { x = "xp", g = "farm" }, h = { m = "mining", h = "herbalism", f = "fishing", t = "treasure" } },
  art = { g = "grind", xp = "grind", farm = "grind", h = "gather", k = "skin", mining = "mining", herbalism = "herbalism",
          fishing = "fishing", treasure = "treasure" },
  slot = "Interface\\AddOns\\IndexOfAzeroth\\Media\\slot_",
}
local tracks = {}
local guide = nil

local Dist, NearestOnSegment = ns.Geo.Dist, ns.Geo.NearestOnSegment
local function dist(a, bx, by) return Dist(a[1], a[2], bx, by) end

local Plain, Call = ns.Plain, ns.Call

local function LineWords(s) return strtrim((tostring(s or ""):gsub("_", " "))) end
local choreDealt = {}

local known = { turned = {}, inLog = {}, complete = {}, failed = {}, log = {} }
local function Kept(list, id, ask)
  local v = list[id]
  if v == nil then
    local raw = Call(ask, id)
    if issecretvalue and issecretvalue(raw) then return false end
    v = raw and true or false
    list[id] = v
  end
  return v
end
local function Turned(id) return Kept(known.turned, id, C_QuestLog.IsQuestFlaggedCompleted) end
local function InLog(id) return Kept(known.inLog, id, C_QuestLog.GetLogIndexForQuestID) end
local function Complete(id) return InLog(id) and Kept(known.complete, id, C_QuestLog.IsComplete) end
local function Failed(id) return InLog(id) and Kept(known.failed, id, C_QuestLog.IsFailed) end
local function Forget() for _, list in pairs(known) do wipe(list) end end
ns.On({ "QUEST_LOG_UPDATE", "QUEST_ACCEPTED", "QUEST_REMOVED", "QUEST_TURNED_IN", "QUEST_WATCH_UPDATE", "PLAYER_ENTERING_WORLD" },
      Forget)
ns.On("UNIT_QUEST_LOG_CHANGED", Forget, "player")
function ns.SkillLines()
  local out = {}
  for i = 1, Plain(Call(C_SkillInfo and C_SkillInfo.GetNumSkillLines)) or 0 do
    local s = Call(C_SkillInfo.GetSkillLineInfo, i)
    local name = type(s) == "table" and not Plain(s.isHeader) and Plain(s.name)
    if type(name) == "string" and name ~= "" then
      out[#out + 1] = { line = Plain(s.skillID), name = name, rank = Plain(s.rank) or 0 }
    end
  end
  return out
end
function ns.SkillObjective(text)
  if type(text) ~= "string" then return nil end
  local lower = text:lower()
  if not lower:find(" skill", 1, true) then return nil end
  for _, s in ipairs(ns.SkillLines()) do
    local _, e = lower:find(s.name:lower() .. " skill", 1, true)
    local need = e and tonumber(lower:match("^%D*(%d+)", e + 1))
    if need then return s.line, s.rank, need, s.name end
  end
  return nil
end
function ns.QuestObjectives(id)
  local list = id and Call(C_QuestLog.GetQuestObjectives, id)
  if type(list) ~= "table" then return {} end
  local complete, out = Complete(id), list
  for k, o in ipairs(list) do
    if type(o) == "table" then
      local finished = Plain(o.finished) and true or false
      local done = complete and true or finished
      local said = Plain(o.numFulfilled) or 0
      local line, rank, asked = ns.SkillObjective(Plain(o.text))
      local have, need = line and rank or said, line and asked or Plain(o.numRequired) or 0
      have = done and need or math.max(math.min(have, need - 1), 0)
      if line or done ~= finished or have ~= said then
        if out == list then out = {}; for j, each in ipairs(list) do out[j] = each end end
        local copy = {}
        for key, v in pairs(o) do copy[key] = v end
        copy.numFulfilled, copy.numRequired, copy.finished, copy.skill = have, need, done, line
        out[k] = copy
      end
    end
  end
  return out
end
function ns.StepObjective(step)
  local id, target = step.ids and step.ids[1], step.target
  if not (id and type(target) == "string" and target ~= "") then return nil end
  if step.get then return nil end
  local want, first, firstK = ns.ObjectiveThing(target):lower(), nil, nil
  for k, o in ipairs(ns.QuestObjectives(id)) do
    local text = type(o) == "table" and Plain(o.text)
    if type(text) == "string" and text:find(target, 1, true) then
      if ns.ObjectiveThing(text):lower() == want then return o, k end
      if not first then first, firstK = o, k end
    end
  end
  return first, firstK
end

function ns.ObjectiveThing(text)
  if type(text) ~= "string" then return "" end
  local t = text:gsub("%d+%s*/%s*%d+", ""):gsub("^%s*:%s*", ""):gsub("%s*:%s*$", "")
  t = t:gsub("%s+slain%s*$", ""):gsub("^%s+", ""):gsub("%s+$", "")
  return t ~= "" and t or text
end

function ns.ObjectiveLeft(o)
  if type(o) ~= "table" or Plain(o.finished) then return nil end
  local left = (Plain(o.numRequired) or 0) - (Plain(o.numFulfilled) or 0)
  return left > 0 and string.format("%d left", left) or "wanted"
end

local mobColour = { places = {}, left = {} }
function mobColour.Of(place)
  local hex = ns.Rules.badges.mobs[place]
  return { tonumber(hex:sub(2, 3), 16) / 255, tonumber(hex:sub(4, 5), 16) / 255, tonumber(hex:sub(6, 7), 16) / 255 }
end
function ns.RowColours(rows, lefts)
  local was, wasLeft, left = mobColour.places, mobColour.left, {}
  local got, changed = ns.Rules.Colours(rows, was), false
  for n, keys in ipairs(rows) do
    for _, k in ipairs(keys) do left[k] = left[k] or lefts[n] end
  end
  for k, p in pairs(got.kept) do changed = changed or was[k] ~= p or wasLeft[k] ~= left[k] end
  for k in pairs(was) do changed = changed or got.kept[k] == nil end
  mobColour.places, mobColour.left = got.kept, left
  local out = {}
  for n, p in ipairs(got.rows) do out[n] = mobColour.Of(p) end
  return out, changed
end
function ns.MobColour(name)
  local p = name and mobColour.places[name]
  return p and mobColour.Of(p) or nil
end
function ns.MobLeft(name)
  return name and mobColour.left[name] or nil
end

function ns.ObjectiveTitle(o)
  local raw = type(o) == "table" and o.text or nil
  local thing = ns.ObjectiveThing(ns.PlainText and ns.PlainText(raw) or Plain(raw))
  local n = type(o) == "table" and Plain(o.numRequired) or nil
  if not n or n < 1 then return thing end
  local have = Plain(o.numFulfilled) or (Plain(o.finished) and n or 0)
  return string.format("%d/%d %s", math.min(have, n), n, thing)
end

function ns.GetStepHas(step)
  local function Has(id, n)
    return (Plain(Call(C_Item and C_Item.GetItemCount or GetItemCount, id)) or 0) >= (n or 1)
  end
  if type(step.gi) ~= "table" or #step.gi == 0 then return step.get ~= nil and Has(step.get, step.count) end
  for _, id in ipairs(step.gi) do
    local has = Has(id, 1)
    if step.ga and has then return true end
    if not step.ga and not has then return false end
  end
  return not step.ga
end

function ns.EpicStepDone(step)
  if step.kind == "S" then return ns.PastedChoreDone(step) end
  local q = step.ids and step.ids[1]
  if step.kind == "O" and step.get and q then
    local sv = ns.GuideSaved and ns.GuideSaved()
    local got, key = sv and sv.gotten, q .. ":" .. step.get
    if ns.GetStepHas(step) then
      if got and InLog(q) then got[key] = true end
      return true
    end
    if got and got[key] and InLog(q) then return true end
  end
  if step.kind == "O" and step.ids and #step.ids == 1 and InLog(step.ids[1]) then
    local o = ns.StepObjective(step)
    if o and Plain(o.finished) then return true end
  end
  for _, id in ipairs(step.ids or {}) do
    local done = Turned(id) or (step.kind == "P" and InLog(id)) or ((step.kind == "O" or step.kind == "D") and Complete(id))
    if not done then return false end
  end
  return true
end

local naming = {
  verbs = { P = "Pick up", O = "Do", T = "Turn in", D = "Do the dungeon for" },
  errand = { train = "train", repair = "repair", sell = "sell", restock = "buy what you're low on",
             bind = "set your hearth", flightpath = "learn the flight path", learn = "learn", supplies = "buy supplies",
             craft = "craft", camp = "make camp", wall = "what comes next waits" },
}
function naming.Chore(step)
  if step.text and step.text ~= "" then return step.text end
  local what = naming.errand[step.what] or "errand"
  return step.npc and step.npc ~= "" and (step.npc .. ": " .. what) or (what:gsub("^%l", string.upper))
end
local function StepName(step)
  if step.text and step.text ~= "" then return step.text end
  if step.kind == "S" then return naming.Chore(step) end
  local title = Plain(Call(C_QuestLog.GetTitleForQuestID, step.ids[1])) or ("quest " .. step.ids[1])
  return naming.verbs[step.kind] .. " " .. title .. (#step.ids > 1 and string.format(" and %d more", #step.ids - 1) or "")
end

local function Refused(step)
  local g = type(IndexOfAzerothCharDB) == "table" and IndexOfAzerothCharDB.guide
  local n = type(g) == "table" and g.notOffered
  return step.kind == "P" and step.ids and type(n) == "table" and n[step.ids[1]] and true or false
end

local function NextEpicStep(tr)
  local t = tr.target
  t.handIn = nil
  while t.queue and #t.queue > 0 do
    local step = table.remove(t.queue, 1)
    if not ns.EpicStepDone(step) and not Refused(step) then
      t.step, t.wx, t.wy, t.path, t.leg = step, step.wx, step.wy, nil, 1
      if step.bends then
        t.path = {}
        for i, b in ipairs(step.bends) do t.path[i] = b end
        t.path[#t.path + 1] = { step.wx, step.wy, rise = step.bends[#step.bends].rise and 0 or nil }
      end
      t.route = nil
      t.loop, t.round = nil, nil
      local back = step.back
      if back then t.path, t.loop, t.walks, t.lap = back.path, back.loop, back.walks, 1 end
      t.name = StepName(step)
      tr.name:SetText(t.name)
      ns.Print("The quest epic's next step: " .. t.name .. ".")
      if ns.PastedChanged then ns.PastedChanged() end
      return true
    end
  end
  t.step = nil
  t.name = "Copy the next steps from the page"
  tr.name:SetText(t.name)
  if ns.PastedChanged then ns.PastedChanged() end
  return false
end

function ns.NearestOnLoop(t, px, py)
  local loop = t.loop
  local best, bx, by, seg, at, round = math.huge, nil, nil, nil, 0, 0
  for i = 2, #loop do
    local u, qx, qy, d, len2 = NearestOnSegment(loop[i - 1][1], loop[i - 1][2], loop[i][1], loop[i][2], px, py)
    if d < best then best, bx, by, seg, at = d, qx, qy, i, round + math.sqrt(len2) * u end
    round = round + math.sqrt(len2)
  end
  return bx, by, best, seg, at, round
end

local function OnRound(t, x, y, seg, ahead)
  local loop = t.loop
  local n = #loop
  for _ = 1, n do
    local to = loop[seg]
    local d = dist(to, x, y)
    if d >= ahead then return x + (to[1] - x) * ahead / d, y + (to[2] - y) * ahead / d end
    ahead, x, y = ahead - d, to[1], to[2]
    seg = seg < n and seg + 1 or 2
  end
  return x, y
end

do
local EACH_RESPAWN = 300
local EACH_SAME = 1
local function EachKey(s) return tostring(s.ids and s.ids[1] or 0) .. ":" .. tostring(s.target or "") end
local function EachOut(s)
  local sv = ns.GuideSaved and ns.GuideSaved()
  if not sv then return {} end
  sv.eachDone = type(sv.eachDone) == "table" and sv.eachDone or {}
  local key, now, out = EachKey(s), time(), {}
  for _, d in ipairs(type(sv.eachDone[key]) == "table" and sv.eachDone[key] or {}) do
    if type(d) == "table" and tonumber(d[3]) and d[3] > now then out[#out + 1] = d end
  end
  sv.eachDone[key] = #out > 0 and out or nil
  return out
end
function ns.EachLoop(s)
  local stops, loop = s and s.each and s.stops, s and s.loop
  if not (stops and loop) then return {} end
  local out, done, left = EachOut(s), {}, #stops
  for k, p in ipairs(stops) do
    for _, d in ipairs(out) do
      if dist(p, d[1], d[2]) <= EACH_SAME then done[k], left = true, left - 1; break end
    end
  end
  local keep, gone = {}, {}
  for k, p in ipairs(stops) do
    if done[k] and left > 0 then gone[#gone + 1] = k
    else keep[#keep + 1] = { p[1], p[2] }; left = math.max(left, 1) end
  end
  for i = #loop, 1, -1 do loop[i] = nil end
  for i, p in ipairs(keep) do loop[i] = p end
  loop[#loop + 1] = { keep[1][1], keep[1][2] }
  return gone
end
function ns.EachSpawnDone(s, px, py)
  local loop = s and s.each and s.loop
  if not loop then return end
  local o = ns.StepObjective(s)
  local got = o and Plain(o.numFulfilled)
  if type(got) ~= "number" then return end
  local was = s.got
  s.got = got
  if not was or got <= was or #loop <= 2 then return end
  local best, at = 30, nil
  for i = 1, #loop - 1 do
    local d = dist(loop[i], px, py)
    if d <= best then best, at = d, i end
  end
  if not at then return end
  local sv = ns.GuideSaved()
  local out = EachOut(s)
  out[#out + 1] = { loop[at][1], loop[at][2], time() + (tonumber(s.respawn) or EACH_RESPAWN) }
  sv.eachDone[EachKey(s)] = out
  ns.EachLoop(s)
  if ns.MarkChanged then ns.MarkChanged("loopstops") end
end
ns.On({ "QUEST_LOG_UPDATE", "QUEST_WATCH_UPDATE" }, function()
  local s = guide and guide.cur and guide.steps[guide.cur]
  if not (s and s.each) then return end
  ns.EachLoop(s)
  local continent, px, py = ns.PlayerWorldPos()
  if px and continent == s.inst then ns.EachSpawnDone(s, px, py) end
end)
local LOOP_STOPS_MOST = 30
function ns.EncodeLoopStops()
  if not guide then return nil end
  local rows, any = {}, false
  for _, s in ipairs(guide.steps) do
    if s.each and s.p and s.stops then
      any = true
      local gone = ns.EachLoop(s)
      if #gone > 0 and #rows < LOOP_STOPS_MOST then rows[#rows + 1] = { s.p, gone, math.ceil(math.min(#s.stops, 40) / 8) } end
    end
  end
  if not any then return nil end
  local w = ns.NewWriter()
  w:u8(41)
  w:var(guide.version or 0)
  w:u8(#rows)
  for _, r in ipairs(rows) do
    w:u16(r[1])
    w:u8(r[3])
    local bytes = {}
    for b = 1, r[3] do bytes[b] = 0 end
    for _, k in ipairs(r[2]) do
      local b = math.floor((k - 1) / 8) + 1
      if bytes[b] then bytes[b] = bytes[b] + 2 ^ ((k - 1) % 8) end
    end
    for b = 1, r[3] do w:u8(bytes[b]) end
  end
  return w.bytes
end
end

ns.FLIGHT_MASTER_TIP = "Press this to target the flight master and put the purple diamond over them. Once they're "
  .. "in reach, press it again to talk to them (their map of flights opens)."
ns.TALK_TIP = "Press this to target the NPC to talk to, with the purple diamond over a vendor, trainer, flight master or "
  .. "innkeeper and the moon over anyone else. Once the NPC is in reach, press it again to talk to them."
local function LoopWant(tr)
  local t = tr.target
  local route = t and t.route
  local ride = route and route:NextRide()
  local master = ride and ride.npc and not route:UnderWay(ns.PlayerWorldPos()) and ride.npc
  local button = _G.IndexOfAzerothButton
  local mobs = not ride and t and t.mobs
  local want = master and { who = master, talk = true, flight = true, anchor = tr.frame, tip = ns.FLIGHT_MASTER_TIP,
                            keys = ride.ni and { [ride.ni] = true } or nil }
    or (mobs and { who = mobs[1], mobs = mobs, cycle = #mobs > 1 or nil, anchor = button or tr.frame,
      tip = "Press this to target the camp's mobs, a live mob first."
        .. (#mobs > 1 and string.format(" Each press that picks up a mob goes on to the next mob on the list, %d in all.", #mobs) or "") })
  local key = want and ((want.talk and "@" or "!") .. (want.mobs and table.concat(want.mobs, ";") or want.who)) or ""
  if key == tr.wantKey then return end
  tr.wantKey = key
  if ns.TargetWant then ns.TargetWant("loop", want) end
end
local function EpicRideKey(tr)
  local who = ns.EpicRideWho()
  if who == tr.rideWho then return end
  tr.rideWho = who
  if ns.GuideKeysAgain then ns.GuideKeysAgain() end
end
local function Clear(tr, message)
  if tr.kind == "e" and guide and tr.target and tr.target.guided then
    guide.arrowOff = guide.cur
    if message then message = "The blue arrow is hidden until the next step. The card stays, and /ioa guide shows or hides it." end
  end
  if tr.kind ~= "e" and tr.target then ns.guideDirty = true end
  local pasted = tr.target and tr.target.pasted
  if message then ns.Print(message) end
  tr:SayStop()
  tr.target = nil
  if tr.kind ~= "e" then LoopWant(tr) end
  tr:Height(nil)
  tr.frame:Hide()
  if pasted and ns.PastedChanged then ns.PastedChanged() end
end

local function Update(tr, dt)
  tr.elapsed = tr.elapsed + dt
  local t = tr.target
  if tr.elapsed < 0.05 or not t then return end
  tr.elapsed = 0
  if tr.kind ~= "e" then LoopWant(tr) else EpicRideKey(tr) end
  tr:Height(nil)
  tr:Glow(nil)
  if ns.Ghost() then
    tr:Alpha(0.3)
    tr.dist:SetText(ns.AFTER_CORPSE)
    return
  end
  if t.step then
    t.checked = (t.checked or 0) + 1
    if t.checked % 10 == 0 and ns.EpicStepDone(t.step) then NextEpicStep(tr)
    elseif t.checked % 10 == 5 and ns.PastedHandIn then ns.PastedHandIn(tr) end
  elseif t.queue then
    tr:Alpha(0.3)
    tr.dist:SetText("every step is done here")
    return
  end
  local continent, px, py = ns.PlayerWorldPos()
  local facing = Plain(Call(GetPlayerFacing))
  if not continent or not facing then
    tr:Alpha(0.3)
    tr.dist:SetText("position unknown here")
    return
  end
  if continent ~= t.continent then
    tr:Alpha(0.3)
    tr.dist:SetText("on another continent")
    return
  end
  local each = tr.kind == "e" and t.loop and (t.step or (t.guided and guide and guide.cur and guide.steps[guide.cur]))
  each = each and each.each and each.loop == t.loop
  local toward, along, off = { t.wx, t.wy }, Dist(t.wx, t.wy, px, py), false
  local goal = nil
  local roam = tr.kind == "e" and ns.GuideInArea()
  if t.loop then
    local nx, ny, near, seg, at, round = ns.NearestOnLoop(t, px, py)
    goal = { nx, ny }
    if near <= ON_LOOP_YARDS then t.path, t.route = nil, nil end
    if not (t.path or t.route) then
      if near <= ON_LOOP_YARDS then
        if t.round and t.round > round * 0.75 and at < round * 0.25 then t.lap = t.lap + 1 end
        t.round = at
        toward = { OnRound(t, nx, ny, seg, LOOP_AHEAD_YARDS) }
      else
        toward = { nx, ny }
      end
      tr:Alpha((tr.kind ~= "e" and near <= ON_LOOP_YARDS) and 0 or 1)
      tr:Turn(math.atan2(toward[2] - py, toward[1] - px) - facing)
      if tr.kind == "e" and t.walks ~= false then
        tr.dist:SetText(near > ON_LOOP_YARDS and string.format("%d yd to where it walks", near) or "along where it walks")
      elseif each then
        tr.dist:SetText(near > ON_LOOP_YARDS and string.format("%d yd to the loop", near)
          or string.format("round the loop, %d spawns left", #t.loop - 1))
      elseif tr.kind == "e" then
        tr.dist:SetText(near <= ON_LOOP_YARDS and string.format("round the camp, lap %d", t.lap)
          or roam and "here" or string.format("%d yd to the camp", near))
      else
        tr.dist:SetText(near > ON_LOOP_YARDS and string.format("%d yd to the loop, lap %d", near, t.lap)
          or string.format("on the loop, %d%% round, lap %d", math.floor(at / math.max(round, 1) * 100), t.lap))
      end
      return
    end
  end
  local nxt = nil
  local route = t.route
  t.join = nil
  if route then
    if route:Join(continent, px, py) then
      local p = route.legs[route.i].path
      t.path, t.leg = #p > 1 and p or nil, 1
      t.wx, t.wy = p[#p][1], p[#p][2]
      toward, along = { t.wx, t.wy }, Dist(t.wx, t.wy, px, py)
    end
    route:Boarded(continent, px, py)
    nxt = route:NextRide()
    route:WalkedOff(continent, px, py)
    if nxt and (route:Waiting() or route:Arrive(along)) then
      tr:Alpha(0.3)
      tr.dist:SetText(RideText(nxt))
      if route:UnderWay(continent, px, py) then tr:Turn(ns.RideTurn(route, continent, px, py)) end
      return
    end
    if nxt then goal = { t.wx, t.wy } end
  end
  if t.path and not roam then
    toward, along, off, t.leg = ns.FollowPath(t.path, t.leg, px, py)
    t.join = off and toward or nil
  end
  t.along = along
  local s = tr.kind == "e" and guide and guide.cur and guide.steps[guide.cur]
  local here = s and s.z and s.inst == continent and ns.BeaconHeight and ns.BeaconHeight(s, continent, px, py)
  local words, turn
  if here then words, turn = ns.RiseWords(s.z - here, Dist(s.wx, s.wy, px, py))
  else
    t.rising = t.rising or {}
    words, turn = ns.HeightHint(t.path, t.leg, px, py, Dist(t.wx, t.wy, px, py), t.rising)
  end
  tr:Height(words, turn)
  tr:Alpha(1)
  if not goal and s and s.wx and s.inst == continent then goal = { s.wx, s.wy } end
  goal = goal or { t.wx, t.wy }
  tr:Point(facing, px, py, goal, toward)
  if along <= ARRIVE_YARDS or roam then
    tr.dist:SetText(words and (turn == 0 and "up from here" or "down from here") or "here")
  else
    tr.dist:SetText(string.format("%d yd%s%s", along, off and ", back to the route" or "", nxt and (", then " .. RideText(nxt)) or ""))
  end
end

for kind, k in pairs(KINDS) do
  local tr = ns.NewGuideArrow(kind, { frame = k.frame, size = 52, y = k.y, clicks = { "LeftButtonUp", "RightButtonUp" },
    art = k.art, label = k.label, text = k.text,
    slot = { colour = kind == "e" and GUIDE.e or k.text,
             hint = kind == "e" and "Click to open the quest epic's card. Right-click or click the x to close the guide."
               or "Right-click or click the x to close the guide.",
             art = LOOKS.slot .. (kind == "e" and "epic" or LOOKS.art[kind]) } })
  tr.elapsed = 0
  function tr:SayStop()
    local t = self.target
    if t and kind ~= "e" then return ns.UI.SayStop(t.look or kind) end
    if t and t.pasted then return ns.UI.SayStop(ns.UI.EpicLook(type(t.epic) == "table" and t.epic.key)) end
  end
  local function Close()
    if tr.target and tr.target.guided and ns.GuideStop then return ns.GuideStop() end
    if kind ~= "e" and tr.target and ns.GuideClosed then ns.GuideClosed("loop", tr.target.name) end
    if kind == "e" and tr.target and ns.PastedClosed then ns.PastedClosed() end
    Clear(tr, k.label:lower() .. " stopped")
  end
  tr.close:SetScript("OnClick", Close)
  tr.frame:SetScript("OnClick", function(_, which)
    if which ~= "RightButton" then
      if tr.target and (tr.target.guided or tr.target.pasted) and ns.ToggleGuideCard then ns.ToggleGuideCard(true) end
      return
    end
    Close()
  end)
  ns.OnTick(tr.frame, "a guide arrow", nil, function(_, dt) Update(tr, dt) end)
  ns.guideSlots[kind].Careful = function()
    local t = tr.target
    if kind == "e" and t and t.guided then
      local s = guide and guide.cur and guide.steps[guide.cur]
      if not (s and s.careful) then return nil end
      local notes = {}
      for note in s.careful:gmatch("[^;]+") do notes[#notes + 1] = note:match("^%s*(.-)%s*$") end
      return #notes > 0 and notes or nil
    end
    return t and t.careful
  end
  tracks[kind] = tr
end

function ns.TrackTarget(kind) return tracks[kind] and tracks[kind].target end

function ns.LoopRunning()
  for _, k in ipairs(LOOPS) do
    local tr = tracks[k]
    if tr and tr.target then return k, tr.target.name, tr.target.check, tr.target.look end
  end
end

function ns.TrackCommand(kind, rest)
  local tr = tracks[kind]
  rest = strtrim(rest or "")
  if not tr then return end
  if kind ~= "e" and rest:lower() ~= "off" then
    for _, o in ipairs(LOOPS) do
      if o ~= kind and tracks[o] and tracks[o].target then Clear(tracks[o]) end
    end
  end
  if kind == "e" and guide and (rest == "" or rest:lower() == "off") then return ns.GuideStop() end
  if kind == "e" and guide then
    return ns.Print("The quest epic is running the blue arrow from its plan. Type /ioa guide stop first if you want to paste a line.")
  end
  if rest == "" or rest:lower() == "off" then
    if kind ~= "e" and tr.target and ns.GuideClosed then ns.GuideClosed("loop", tr.target.name) end
    if kind == "e" and tr.target and ns.PastedClosed then ns.PastedClosed() end
    return Clear(tr, tr.target and (KINDS[kind].label:lower() .. " stopped") or nil)
  end
  local mapID, tail = rest:match("^(%d+)%s+(.+)$")
  if not mapID then return ns.Print("usage: /ioa " .. kind .. " <mapID> <x,y> <x,y> ... <name>, or /ioa " .. kind .. " off") end
  mapID = tonumber(mapID)
  local pts, loopFrom, remaining = {}, nil, tail
  local step, queue, rides = nil, {}, {}
  local sharedAt = nil
  local sharedEpic = nil
  local accepts = nil
  local mobs = nil
  local careful = nil
  local attachTo = nil
  local look = kind ~= "e" and kind or nil
  local function Ids(s) local ids = {} for id in s:gmatch("%d+") do ids[#ids + 1] = tonumber(id) end return ids end
  if kind == "e" then wipe(choreDealt) end
  while true do
    local mark, after = remaining:match("^(@)%s*(.*)$")
    local sk, sids, safter = remaining:match("^=([POTD])([%d%.]+)%s*(.*)$")
    local ck, cnpc, cafter = remaining:match("^=S(%a+):(.-)%s+(%^.*)$")
    if not ck then ck, cnpc, cafter = remaining:match("^=S(%a+):(%S*)%s*(.*)$") end
    local qck, qcnpc, qcspot, qcafter = remaining:match("^S(%a+):([^@]-)@([%w%-_][%w%-_][%w%-_][%w%-_][%w%-_])%s*(.*)$")
    local qk, qids, qx, qy, qafter = remaining:match("^([POTD])([%d%.]+):([%d%.]+),([%d%.]+)%s*(.*)$")
    local pk, pids, pspot, pafter2 = remaining:match("^([POTD])([%d%.]+)@([%w%-_][%w%-_][%w%-_][%w%-_][%w%-_])%s*(.*)$")
    if pk and ns.PackedPoint then
      local x, y = ns.PackedPoint(pspot)
      if x then qk, qids, qx, qy, qafter = pk, pids, tostring(x * 100), tostring(y * 100), pafter2 end
    end
    local rk, rtext, rafter = remaining:match("^>([ABZTFHD])(%S+)%s*(.*)$")
    local packed, pafter = remaining:match("^~([%w%-_]+)%s*(.*)$")
    local way, rise, wafter = remaining:match("^%^([%w%-_]+)!?([%w%-_%*:%.]*)%s*(.*)$")
    local sv, si, sharedAfter = remaining:match("^#(%d+):(%d+)%s*(.*)$")
    local takes, tafter = remaining:match("^%+([%w%.]+)%s*(.*)$")
    local mobList, mafter = remaining:match("^!(%S+)%s+(.*)$")
    local notes, nafter = remaining:match("^%?(%S*)%s*(.*)$")
    local said, safter2 = remaining:match("^&(%a)%s*(.*)$")
    local justQueued = attachTo
    attachTo = nil
    if said then
      look, remaining = LOOKS.tokens[kind] and LOOKS.tokens[kind][said:lower()] or look, safter2
    elseif mark then
      loopFrom, remaining = #pts + 1, after
    elseif sk then
      step, remaining = { kind = sk, ids = Ids(sids) }, safter
    elseif qk then
      local _, wx, wy = ns.WorldPos(mapID, tonumber(qx) / 100, tonumber(qy) / 100)
      if wx then
        queue[#queue + 1] = { kind = qk, ids = Ids(qids), wx = wx, wy = wy }
        attachTo = queue[#queue]
      end
      remaining = qafter
    elseif ck then
      step, remaining = { kind = "S", ids = {}, what = ck, npc = LineWords(cnpc) }, cafter
    elseif qck then
      local x, y, _, wx, wy
      if ns.PackedPoint then x, y = ns.PackedPoint(qcspot) end
      if x then _, wx, wy = ns.WorldPos(mapID, x, y) end
      if wx then
        queue[#queue + 1] = { kind = "S", ids = {}, what = qck, npc = LineWords(qcnpc), wx = wx, wy = wy }
        attachTo = queue[#queue]
      end
      remaining = qcafter
    elseif rk then
      local where, npc = rtext:match("^([^@]*)@(.+)$")
      rides[#pts + 1] = { kind = rk, text = LineWords(where or rtext), npc = npc and LineWords(npc) or nil }
      remaining = rafter
    elseif mobList then
      mobs = {}
      for m in mobList:gmatch("[^;]+") do mobs[#mobs + 1] = LineWords(m) end
      remaining = mafter
    elseif notes then
      careful, remaining = ns.DecodeCareful(notes), nafter
    elseif takes then
      accepts = {}
      for id in takes:gmatch("[^%.]+") do accepts[#accepts + 1] = tonumber(id, 36) end
      remaining = tafter
    elseif sv then
      local sh = IndexOfAzerothShared
      if not (type(sh) == "table" and tostring(sh.version) == sv and sh.epic and sh.epic.steps[tonumber(si)]) then
        return ns.Print("That line uses the Index's shared table, which the game hasn't loaded yet. Type /reload (or restart the game once after an update), then copy the line again.")
      end
      local steps = sh.epic.steps
      local st = steps[tonumber(si)]
      step = { kind = st.k, ids = st.ids, text = st.text, what = st.what, npc = st.npc, entry = st }
      sharedAt, sharedEpic = st, sh.epic
      for j = tonumber(si) + 1, #steps do
        local q = steps[j]
        local bends = nil
        if q.way then
          bends = {}
          for k, b in ipairs(q.way) do bends[k] = { b[1], b[2], rise = (q.at[3] and b[3]) and q.at[3] - b[3] or nil } end
          for _, k in ipairs(type(q.cov) == "table" and q.cov or {}) do if bends[k] then bends[k].cov = true end end
        end
        queue[#queue + 1] = { kind = q.k, ids = q.ids, text = q.text, wx = q.at[1], wy = q.at[2], bends = bends, inst = q.inst,
                              what = q.what, npc = q.npc, entry = q }
      end
      remaining = sharedAfter
    elseif way and ns.DecodeWay then
      local to = justQueued
      local bends = ns.DecodeWay(mapID, way) or {}
      if ns.DecodeRise then ns.DecodeRise(bends, rise) end
      for _, b in ipairs(bends) do
        if to then
          to.bends = to.bends or {}
          to.bends[#to.bends + 1] = b
        else
          pts[#pts + 1] = { world = b }
        end
      end
      remaining = wafter
    elseif packed and ns.PackedPoint then
      local to = justQueued
      for i = 1, #packed - 4, 5 do
        local x, y = ns.PackedPoint(packed:sub(i, i + 4))
        if x and to then
          local _, wx, wy = ns.WorldPos(mapID, x, y)
          if wx then to.bends = to.bends or {}; to.bends[#to.bends + 1] = { wx, wy } end
        elseif x then
          pts[#pts + 1] = { x * 100, y * 100 }
        end
      end
      remaining = pafter
    else
      local x, y, after2 = remaining:match("^([%d%.]+),([%d%.]+)%s*(.*)$")
      if not x then break end
      pts[#pts + 1] = { tonumber(x), tonumber(y) }
      remaining = after2
    end
  end
  local name = strtrim(remaining)
  if sharedAt then
    if not loopFrom then pts[#pts + 1] = { world = { sharedAt.at[1], sharedAt.at[2], rise = sharedAt.at[3] and 0 or nil } } end
    if name == "" then name = sharedAt.text or "" end
  end
  if #pts == 0 then
    local x, y, n = (tail:gsub("^&%a%s+", "")):match("^([%d%.]+)%s+([%d%.]+)%s*(.*)$")
    if not x then return ns.Print(ns.NOT_WHOLE) end
    pts, name = { { tonumber(x), tonumber(y) } }, strtrim(n)
  end
  local path, continent = {}, nil
  for i, p in ipairs(pts) do
    if p.world then
      path[i] = p.world
      continent = continent or select(1, ns.WorldPos(mapID, 0.5, 0.5))
    else
      local c, wx, wy = ns.WorldPos(mapID, p[1] / 100, p[2] / 100)
      if not c then return ns.Print(string.format("Map %d has no position for %.2f, %.2f.", mapID, p[1], p[2])) end
      continent = continent or c
      path[i] = { wx, wy }
    end
  end
  for i = #path, 2, -1 do
    if (not loopFrom or i < loopFrom) and math.abs(path[i][1] - path[i - 1][1]) < 1 and math.abs(path[i][2] - path[i - 1][2]) < 1 then
      if path[i].rise and not path[i - 1].rise then path[i - 1].rise = path[i].rise end
      table.remove(path, i)
      if loopFrom then loopFrom = loopFrom - 1 end
    end
  end
  local loop = nil
  if loopFrom and loopFrom <= #path then
    loop = {}
    for i = loopFrom, #path do loop[#loop + 1] = path[i] end
    loop[#loop + 1] = { loop[1][1], loop[1][2] }
    for i = #path, loopFrom, -1 do path[i] = nil end
    if #path == 0 then path[1] = loop[1] end
  end
  local route = nil
  if next(rides) then
    local legs = { { kind = "W", path = {}, continent = continent } }
    for i, p in ipairs(path) do
      if rides[i] and #legs[#legs].path > 0 then
        legs[#legs + 1] = rides[i]
        legs[#legs + 1] = { kind = "W", path = {}, continent = continent, start = p }
      end
      local cur = legs[#legs].path
      cur[#cur + 1] = p
    end
    if rides[#path + 1] then legs[#legs + 1] = rides[#path + 1] end
    route = ns.NewRoute(legs)
  end
  local first = route and route.legs[1].path or path
  local last = first[#first]
  if tr.target and tr.target.name ~= (name ~= "" and name or KINDS[kind].label) then tr:SayStop() end
  tr.target = { continent = continent, wx = last[1], wy = last[2], name = name ~= "" and name or KINDS[kind].label,
                path = #first > 1 and first or nil, leg = 1, loop = loop, lap = 1,
                step = step, queue = step and queue or nil, route = route, mobs = kind ~= "e" and mobs or nil, careful = careful,
                look = look }
  if kind == "e" then
    local t = tr.target
    t.pasted, t.spot, t.lineName, t.epic = true, path[#path], name, sharedEpic
    t.steps = step and { step, unpack(queue) } or nil
  end
  tr.name:SetText(tr.target.name)
  if kind ~= "e" then
    tr.target.check = ns.LineCheck and ns.LineCheck(kind, rest)
    ns.guideDirty = true
    tr:Colour(GUIDE[look], false, LOOKS.slot .. LOOKS.art[look])
  end
  tr.dist:SetText("")
  tr.frame:Show()
  if kind == "e" then
    ns.EpicAccept(accepts)
    local give = {}
    for _, q in ipairs(step and { step, unpack(queue) } or {}) do
      if q.kind == "T" then for _, id in ipairs(q.ids) do give[#give + 1] = id end end
    end
    ns.EpicHandIn(give)
  end
  if step and ns.EpicStepDone(step) then NextEpicStep(tr) end
  if kind == "e" and ns.PastedChanged then ns.PastedChanged(true) end
  ns.Print(string.format("%s: %s. Right-click the %s arrow or type /ioa %s off to stop the guide.", KINDS[kind].label, tr.target.name,
    ns.UI.ColourName(GUIDE[look or kind]), kind))
  ns.SayCareful(careful)
end

local accepting, handing = {}, {}
local listed = {}
local LISTED_SECONDS = 30
listed.giver = { event = nil, n = 0, asked = false }
function ns.GiverAsked() listed.giver.asked = listed.giver.event or true end
function listed.giver.Window(event)
  if listed.giver.asked and event ~= listed.giver.asked then listed.giver.asked = false end
  listed.giver.event, listed.giver.n = event, listed.giver.n + 1
end
function listed.giver.Ask(f, arg, after)
  local n = listed.giver.n
  C_Timer.After(0, function()
    if listed.giver.n ~= n or listed.giver.asked then return end
    listed.giver.asked = listed.giver.event or true
    Call(f, arg)
    if after then after() end
  end)
end
for _, f in ipairs({ { _G, "SelectActiveQuest" }, { _G, "SelectAvailableQuest" }, { _G, "AcceptQuest" },
                     { _G, "CompleteQuest" }, { _G, "GetQuestReward" }, { C_GossipInfo, "SelectActiveQuest" },
                     { C_GossipInfo, "SelectAvailableQuest" } }) do
  if hooksecurefunc and type(f[1]) == "table" and type(f[1][f[2]]) == "function" then
    pcall(hooksecurefunc, f[1], f[2], function() ns.GiverAsked() end)
  end
end
ns.On({ "QUEST_FINISHED", "GOSSIP_CLOSED" }, function() listed.giver.Window(nil) end)
function ns.EpicAccept(ids)
  wipe(accepting)
  for _, id in ipairs(ids or {}) do accepting[id] = true end
end
function ns.EpicHandIn(ids)
  wipe(handing)
  for _, id in ipairs(ids or {}) do handing[id] = true end
end
function ns.EpicHold(ids)
  listed.held = {}
  for _, id in ipairs(ids or {}) do listed.held[id] = true end
end
ns.EpicHold(nil)
function ns.AnyRewardPick(tr)
  local id = Plain(Call(GetQuestID))
  if ((tr and tr.target) or guide) and not IsShiftKeyDown() and handing[id] then return end
  if (Plain(Call(GetNumQuestChoices)) or 0) <= 1 or not ns.Options().general.rewardMark then return end
  local pick, why = ns.GuideRewardPick(id)
  if not pick then return end
  ns.GuideMarkReward(pick.index, pick.vendor, pick.want)
  ns.GuideToast(string.format("%s: our pick is %s, %s", Plain(Call(GetTitleText)) or "the quest", pick.name, why))
end

ns.On({ "GOSSIP_SHOW", "QUEST_GREETING", "QUEST_DETAIL", "QUEST_ACCEPT_CONFIRM", "QUEST_PROGRESS", "QUEST_COMPLETE" },
      function(event, ...)
  local tr = tracks.e
  if event ~= "QUEST_ACCEPT_CONFIRM" then listed.giver.Window(event) end
  if event == "QUEST_COMPLETE" then ns.AnyRewardPick(tr) end
  if IsShiftKeyDown() then return end
  local running = (tr and tr.target) or guide
  local general = ns.Options().general
  local npc, take, give = Plain(Call(UnitGUID, "npc")), general.accept, general.handIn
  if not (running or take or give) then return end
  if event == "GOSSIP_SHOW" or event == "QUEST_GREETING" or event == "QUEST_COMPLETE" then
    listed.guid, listed.at = npc, GetTime()
  end
  if event == "GOSSIP_SHOW" then
    local gossip = C_GossipInfo or {}
    local offered, order = {}, {}
    for _, q in ipairs(Call(gossip.GetAvailableQuests) or {}) do
      local id = Plain(q.questID)
      if id then offered[id] = true end
      if id and not listed.held[id] then order[#order + 1] = id end
    end
    if running and ns.GuideCheckOffered then ns.GuideCheckOffered(offered) end
    if give then
      for _, q in ipairs(Call(gossip.GetActiveQuests) or {}) do
        local id = Plain(q.questID)
        if id and Plain(q.isComplete) then return listed.giver.Ask(gossip.SelectActiveQuest, id) end
      end
    end
    if take and order[1] then return listed.giver.Ask(gossip.SelectAvailableQuest, order[1]) end
    return
  elseif event == "QUEST_GREETING" then
    local offered, first = {}, nil
    for i = 1, Call(GetNumAvailableQuests) or 0 do
      local id = Plain(select(5, Call(GetAvailableQuestInfo, i)))
      if id then offered[id] = true end
      if not (first or listed.held[id]) then first = i end
    end
    if running and ns.GuideCheckOffered then ns.GuideCheckOffered(offered) end
    if give then
      for i = 1, Call(GetNumActiveQuests) or 0 do
        local _, complete = Call(GetActiveTitle, i)
        if Plain(complete) then return listed.giver.Ask(SelectActiveQuest, i) end
      end
    end
    if take and first then return listed.giver.Ask(SelectAvailableQuest, first) end
    return
  end
  if running and (event == "QUEST_DETAIL" or event == "QUEST_PROGRESS") and npc and ns.GuideCheckOffered
     and not (listed.guid == npc and GetTime() - listed.at < LISTED_SECONDS) then
    local id = event == "QUEST_DETAIL" and Plain(Call(GetQuestID))
    ns.GuideCheckOffered(id and { [id] = true } or {})
  end
  if running and event == "QUEST_DETAIL" and ns.GuideOfferedNow then ns.GuideOfferedNow(Plain(Call(GetQuestID))) end
  if event == "QUEST_DETAIL" then
    if take and not listed.held[Plain(Call(GetQuestID))] and not Call(QuestGetAutoAccept) then
      local title = Plain(Call(GetTitleText)) or "the quest"
      listed.giver.Ask(AcceptQuest, nil, function()
        ns.GuideToast("The addon took " .. title .. ". Hold Shift as you talk to the quest giver to decide yourself.")
      end)
    end
  elseif event == "QUEST_ACCEPT_CONFIRM" then
    if take and not listed.held[Plain(select(3, ...))] then Call(ConfirmAcceptQuest) end
  elseif event == "QUEST_PROGRESS" then
    if give and Plain(Call(IsQuestCompletable)) then listed.giver.Ask(CompleteQuest) end
  elseif event == "QUEST_COMPLETE" then
    local id = Plain(Call(GetQuestID))
    local title = Plain(Call(GetTitleText)) or "the quest"
    if (Plain(Call(GetNumQuestChoices)) or 0) <= 1 then
      if give then
        listed.giver.Ask(GetQuestReward, 1, function() ns.GuideToast("The addon handed in " .. title .. ".") end)
      end
    elseif running and handing[id] then
      local pick, why = nil, ""
      if ns.GuideRewardPick and ns.Options().general.rewardMark then pick, why = ns.GuideRewardPick(id) end
      if pick then
        ns.GuideMarkReward(pick.index, pick.vendor, pick.want)
        ns.GuideToast(string.format("%s: our pick is %s, %s", title, pick.name, why))
      else
        ns.GuideToast(title .. ": pick your reward" .. (why or ""))
      end
    end
  end
end)

ns.On({ "QUEST_ACCEPTED", "QUEST_TURNED_IN", "QUEST_LOG_UPDATE", "QUEST_REMOVED" }, function()
  local tr = tracks.e
  if tr and tr.target and tr.target.step and ns.EpicStepDone(tr.target.step) then NextEpicStep(tr) end
end)


local rings = { COLORS = {}, SEGMENTS = 28, RADIUS = 15, STEP = 5, holder = nil, lines = {} }
for kind, c in pairs(GUIDE) do rings.COLORS[kind] = { c[1], c[2], c[3], 1 } end

function rings.Wanted()
  local out = {}
  local g = ns.GuideTarget and ns.GuideTarget()
  local flight = g and g.route and g.route:NextFlight()
  if flight then out[#out + 1] = { place = flight.text, node = flight.node, color = rings.COLORS.go } end
  for _, kind in ipairs({ "e", "g", "h", "k" }) do
    local e = tracks[kind] and tracks[kind].target
    local ride = e and e.route and e.route:NextRide()
    if ride and ride.kind == "F" then out[#out + 1] = { place = ride.text, node = ride.node, color = rings.COLORS[kind] } end
  end
  return out
end

function rings.Hide(from)
  for k = from or 1, #rings.lines do rings.lines[k]:Hide() end
end

function rings.Draw(n, anchor, radius, color)
  for pass = 1, 2 do
    for k = 1, rings.SEGMENTS do
      local a1, a2 = (k - 1) / rings.SEGMENTS * 2 * math.pi, k / rings.SEGMENTS * 2 * math.pi
      n = n + 1
      local line = rings.lines[n]
      if not line then
        line = rings.holder:CreateLine(nil, "OVERLAY")
        rings.lines[n] = line
      end
      line:SetThickness(pass == 1 and 4.5 or 2.5)
      if pass == 1 then line:SetColorTexture(0, 0, 0, 0.8) else line:SetColorTexture(color[1], color[2], color[3], color[4]) end
      line:SetStartPoint("CENTER", anchor, radius * math.cos(a1), radius * math.sin(a1))
      line:SetEndPoint("CENTER", anchor, radius * math.cos(a2), radius * math.sin(a2))
      line:Show()
    end
  end
  return n
end

function rings.PlaceOf(name) return strtrim((name or ""):match("^([^,]+)") or ""):lower() end

function rings.AtFlightMaster()
  rings.Hide()
  local wanted = rings.Wanted()
  if #wanted == 0 or not NumTaxiNodes then return end
  local slots, order = {}, {}
  local nodeOf = {}
  if C_TaxiMap and C_TaxiMap.GetAllTaxiNodes then
    local mapID = (GetTaxiMapID and Plain(Call(GetTaxiMapID))) or (C_Map and Plain(Call(C_Map.GetBestMapForUnit, "player")))
    local nodes = mapID and Call(C_TaxiMap.GetAllTaxiNodes, mapID)
    for _, n in ipairs(type(nodes) == "table" and nodes or {}) do
      local slot, id = Plain(n.slotIndex), Plain(n.nodeID)
      if slot and id then nodeOf[slot] = id end
    end
  end
  for i = 1, Plain(Call(NumTaxiNodes)) or 0 do
    local place = rings.PlaceOf(Plain(Call(TaxiNodeName, i)))
    for _, w in ipairs(wanted) do
      local there
      if w.node and nodeOf[i] then there = w.node == nodeOf[i] else there = place ~= "" and place == w.place:lower() end
      if there then
        if not slots[i] then slots[i], order[#order + 1] = {}, i end
        table.insert(slots[i], w)
      end
    end
  end
  if TaxiFrame and not rings.holder then
    rings.holder = CreateFrame("Frame", nil, TaxiFrame)
    rings.holder:SetAllPoints()
    rings.holder:SetFrameLevel((TaxiFrame:GetFrameLevel() or 1) + 20)
  end
  local n = 0
  for _, i in ipairs(order) do
    local button = _G["TaxiButton" .. i]
    if rings.holder and button and button:IsShown() then
      for k, w in ipairs(slots[i]) do n = rings.Draw(n, button, rings.RADIUS - (k - 1) * rings.STEP, w.color) end
    end
  end
  rings.Hide(n + 1)
  if #order == 1 and #slots[order[1]] == #wanted then
    local i = order[1]
    local name = Plain(Call(TaxiNodeName, i)) or "the guide's flight"
    if IsShiftKeyDown() then
      ns.Print(name .. " is ringed for your guide. You held Shift, so pick the flight yourself.")
    elseif not ns.Options().general.flights then
      ns.Print(name .. " is ringed for your guide.")
    elseif Plain(Call(TaxiNodeGetType, i)) == "REACHABLE" then
      ns.Print("Flying to " .. name .. " for your guide. Hold Shift at the flight master to pick the flight yourself.")
      TakeTaxiNode(i)
    end
  elseif #order > 1 then
    ns.Print("Your guides fly to different places, so each place is ringed in its guide's colour.")
  end
end

ns.On({ "TAXIMAP_OPENED", "TAXIMAP_CLOSED" }, function(event)
  if event == "TAXIMAP_CLOSED" then return rings.Hide() end
  C_Timer.After(0, function() pcall(rings.AtFlightMaster) end)
end)


local G = { TODO = 0, DONE = 1, WAIT = 2, BLOCKED = 3, PARKED = 4, SKIPPED = 5 }
ns.GUIDE = G

local function NearWay(bends, px, py)
  local near = math.huge
  for k, b in ipairs(bends) do
    near = math.min(near, Dist(b[1], b[2], px, py))
    local a = bends[k - 1]
    if a then
      local _, _, _, d = NearestOnSegment(a[1], a[2], b[1], b[2], px, py)
      near = math.min(near, d)
    end
  end
  return near
end
local function StepBends(s, px, py)
  local way = (s.easyPicked and s.easy) or s.bends
  if s.alt and px and (not way or NearWay(s.alt, px, py) < NearWay(way, px, py)) then way = s.alt end
  if s.hw and px and #s.hw > 1 and (not way or NearWay(s.hw, px, py) < NearWay(way, px, py)) then way = s.hw end
  return way
end
ns.StepBends = StepBends

local ways = { ROUTE_FROM = 1200 }
function ways.To(s, bends)
  local path = {}
  for k = 1, #bends do path[#path + 1] = bends[k] end
  path[#path + 1] = { s.wx, s.wy, rise = s.z and 0 or nil, cov = bends.endCov }
  return path
end
function ways.Open(continent, px, py)
  local s = guide and guide.cur and guide.steps[guide.cur]
  if not (s and s.easy and s.bends and s.wx and px and continent == s.inst) then return false end
  if ns.Ghost() or guide.hearthFor == s or ns.GuideAtLoop() then return false end
  local way = StepBends(s, px, py)
  return way == s.bends or way == s.easy
end
function ways.Length(path)
  local n = 0
  for k = 2, #path do n = n + Dist(path[k][1], path[k][2], path[k - 1][1], path[k - 1][2]) end
  return n
end
function ways.Take()
  local continent, px, py = ns.PlayerWorldPos()
  if not ways.Open(continent, px, py) then return false end
  local s = guide.steps[guide.cur]
  local quick, easy = ways.To(s, s.bends), ways.To(s, s.easy)
  local _, leftQuick = ns.FollowPath(quick, 1, px, py)
  local _, leftEasy = ns.FollowPath(easy, 1, px, py)
  local kept = ns.Rules.Ways(NearWay(quick, px, py), NearWay(easy, px, py), leftQuick, leftEasy,
                             { ways.Length(quick), ways.Length(easy) })
  if kept == "both" then return false end
  if kept == "easy" then s.bends = s.easy end
  s.easy, s.easyPicked = nil, nil
  if ns.MarkChanged then ns.MarkChanged("status") end
  return true
end
function ns.GuideEasyOpen() return ways.Open(ns.PlayerWorldPos()) end
function ns.GuideWay()
  local s = guide and guide.cur and guide.steps[guide.cur]
  local continent, px, py = ns.PlayerWorldPos()
  if not (s and s.p and px and continent == s.inst) then return nil end
  local way = StepBends(s, px, py)
  for k, name in ipairs(ns.Rules.guide.ways) do
    if way and (way.kind or "way") == name then return k end
  end
  return nil
end
local listeners = {}

function ns.OnGuide(f) listeners[#listeners + 1] = f end
local cardFailed = false
local function Changed(what, ...)
  for _, f in ipairs(listeners) do
    local ok, err = pcall(f, what, ...)
    if not ok and not cardFailed then
      cardFailed = true
      ns.Print("The quest epic's card hit an error: " .. tostring(err))
    end
  end
end

local SAVED_SCHEMA = 3
local savedChecked = nil
local function Saved()
  local char = type(IndexOfAzerothCharDB) == "table" and IndexOfAzerothCharDB or {}
  local g = char.guide
  if g ~= nil and g == savedChecked then return g end
  g = type(g) == "table" and g or {}
  char.guide = g
  if (tonumber(g.schema) or 0) < SAVED_SCHEMA then
    if type(g.parked) ~= "table" and type(g.left) == "table" then g.parked = g.left end
    local nav = ns.Options and ns.Options().nav
    if nav and g.compassOff then
      nav.compass = false
      ns.Print("Options, Navigation now keeps the compass you switched off with /ioa compass, so the compass is off on every character.")
    end
    if nav and g.beacon == false then
      nav.beacons = false
      ns.Print("Options, Navigation now keeps the beacons you switched off with /ioa beacon, so beacons are off on every character.")
    end
    g.left, g.hidden, g.compassOff, g.beacon, g.schema = nil, nil, nil, nil, SAVED_SCHEMA
  end
  g.parked = type(g.parked) == "table" and g.parked or {}
  g.notOffered = type(g.notOffered) == "table" and g.notOffered or {}
  g.skippedErrands = type(g.skippedErrands) == "table" and g.skippedErrands or {}
  g.skippedAt = type(g.skippedAt) == "table" and g.skippedAt or {}
  g.ticked = type(g.ticked) == "table" and g.ticked or {}
  g.gotten = type(g.gotten) == "table" and g.gotten or {}
  savedChecked = g
  return g
end
ns.GuideSaved = Saved
local function BeaconOn() return ns.NavOn("beacons") end

local function Event(kind, i)
  local e, s = guide.events, guide.steps[i]
  if s and s.own then return end
  e[#e + 1] = { kind = kind, step = s and s.p or i, at = time() }
  if #e > 8 then table.remove(e, 1) end
end

local function Parked(id) local p = Saved().parked[guide.key]; return p and p[id] or false end
local back = {}

local function ErrandDone(s)
  local need, st, cdb = s.need or {}, ns.lastStatus, type(IndexOfAzerothCharDB) == "table" and IndexOfAzerothCharDB or {}
  local declared = ns.NeedMet and ns.NeedMet(need)
  if declared == false then return false end
  if s.what == "wall" then
    return declared == true or (declared == nil and need.level ~= nil and (Plain(Call(UnitLevel, "player")) or 0) >= need.level)
  end
  local nums = st and st.nums or {}
  if s.what == "bind" then
    local here = Plain(Call(GetBindLocation))
    if type(need.bind) ~= "table" then return need.bind ~= nil and here == need.bind end
    for _, name in ipairs(need.bind) do if here == name then return true end end
    return false
  end
  if s.what == "flightpath" then
    return (need.node and cdb.taxi and cdb.taxi[need.node]) or (need.name and cdb.taxiNames and cdb.taxiNames[need.name]) or false
  end
  if s.what == "train" then
    if type(need.spells) == "table" and #need.spells > 0 then
      local all, some = true, false
      for _, id in ipairs(need.spells) do
        if Plain(Call(C_SpellBook and C_SpellBook.IsSpellKnown, id, 0)) or Plain(Call(IsSpellKnown, id)) then some = true else all = false end
      end
      return all or (some and not ns.atTrainer)
    end
    return need.level ~= nil and (cdb.trainedLevel or 0) >= need.level
  end
  if s.what == "repair" or s.what == "sell" then
    return st ~= nil and (not need.durability or (nums.durability or 100) >= need.durability)
      and (not need.bags or (nums.bagFree or 0) >= need.bags or ns.bagJunk == 0)
      and (not need.junk or ns.bagJunk == 0)
  end
  if s.what == "restock" and type(need.warning) == "table" and #need.warning > 0 then
    if not st then return false end
    for _, w in ipairs(st.warns or {}) do
      for _, want in ipairs(need.warning) do if w.name == want then return false end end
    end
    return true
  end
  return declared == true
end

local KEEP_SKIP = { train = true, bind = true, flightpath = true }
local chore = { SKIP = 3600 }
function chore.SkipLeft(key)
  local at = Saved().skippedAt[key]
  return at and chore.SKIP - (time() - at) or 0
end
local function Skipped(s)
  local lv = s.key and Saved().skippedErrands[s.key]
  if not lv then return false end
  if s.what == "camp" then return chore.SkipLeft(s.key) > 0 end
  return KEEP_SKIP[s.what] or lv == (Plain(Call(UnitLevel, "player")) or 0)
end

function chore.Ticked(s)
  local t = Saved().ticked
  return guide ~= nil and t.version == guide.version and s.i ~= nil and t[s.i] == true
end
function chore.Tick(s)
  local t = Saved().ticked
  local bind = s.what == "bind"
  if not (guide and s.i) or not (bind or (ns.NeedMet and ns.NeedMet(s.need or {}) == true)) then return end
  if bind then chore.Bound(s) end
  if t.version ~= guide.version then
    wipe(t)
    t.version = guide.version
  end
  t[s.i] = true
end

function chore.Bound(s)
  Saved().bound = { key = s.key, bind = (s.need or {}).bind }
end
function chore.Names(b) return type(b) == "table" and b or { b } end
function chore.BindMoved()
  local sv = Saved()
  local b = sv.bound
  local here = Plain(Call(GetBindLocation))
  if type(b) ~= "table" or not b.key or not here or here == "" then return end
  for _, name in ipairs(chore.Names(b.bind)) do if here == name then return end end
  for _, s in ipairs(guide and guide.steps or {}) do
    for _, name in ipairs(s.what == "bind" and chore.Names((s.need or {}).bind) or {}) do
      if here == name then return chore.Bound(s) end
    end
  end
  sv.skippedErrands[b.key] = Plain(Call(UnitLevel, "player")) or 0
  sv.bound = nil
  ns.epicDirty = true
end
ns.On("HEARTHSTONE_BOUND", function() if guide then pcall(chore.BindMoved) end end)
ns.GuideBindMoved = chore.BindMoved

function chore.SoldOut()
  local name = Plain(Call(UnitName, "npc"))
  if not (guide and name) then return end
  local listed = {}
  for i = 1, Plain(Call(GetMerchantNumItems)) or 0 do
    local id = Plain(Call(GetMerchantItemID, i))
    if id then listed[id] = true end
  end
  local sv = Saved()
  for _, s in ipairs(guide.steps) do
    local limited = s.what == "supplies" and s.npc == name and s.key and (s.need or {}).limited
    for _, id in ipairs(type(limited) == "table" and limited or {}) do
      if not listed[tonumber(id)] and not sv.skippedErrands[s.key] and ns.NeedMet(s.need) ~= true then
        sv.skippedErrands[s.key] = Plain(Call(UnitLevel, "player")) or 0
        ns.epicDirty = true
      end
    end
  end
end
ns.On({ "MERCHANT_SHOW", "MERCHANT_UPDATE" }, function() if guide then pcall(chore.SoldOut) end end)
ns.GuideSoldOut = chore.SoldOut

chore.HEARTH = { ITEM = 6948, CAST = 20, LEAST = 30, DETOUR = 1.25, RUN = 7, COOLDOWN = 3600, FAR = 600 }
function chore.HearthReady()
  local H = chore.HEARTH
  local count = Plain(Call(C_Item and C_Item.GetItemCount or GetItemCount, H.ITEM)) or 0
  if count < 1 then return false end
  local start, duration = Call(C_Container and C_Container.GetItemCooldown or GetItemCooldown, H.ITEM)
  start, duration = Plain(start), Plain(duration)
  return start ~= nil and (start == 0 or start + (duration or 0) - GetTime() <= 0)
end
function chore.HearthSaves(s, continent, px, py)
  local H, h = chore.HEARTH, s.hearth
  local inn = h.inst == s.inst and Dist(h.wx, h.wy, s.wx, s.wy) * H.DETOUR / H.RUN or H.FAR
  local you = (continent == s.inst and px) and Dist(s.wx, s.wy, px, py) * H.DETOUR / H.RUN or H.FAR
  return math.min(you, H.FAR) - math.min(inn, H.FAR) - H.CAST
end
function chore.HearthLater(i, saves)
  local t, cd = 0, guide.steps[i].hearth.cd or chore.HEARTH.COOLDOWN
  for k = i + 1, #guide.steps do
    local s, st = guide.steps[k], guide.state[k]
    if st == G.TODO or st == G.WAIT then
      t = t + (s.sec or 0) * ns.GuidePace()
      if t >= cd then return false end
      if s.hearth and s.hearth.picked and s.hearth.saves > saves then return true end
    end
  end
  return false
end
function chore.TripForward()
  local lead, level = guide.planCur, Plain(Call(UnitLevel, "player")) or 0
  local P = lead and guide.steps[lead]
  if not (P and P.wl) then return end
  local hand = lead
  for i = lead + 1, #guide.steps do
    local s = guide.steps[i]
    if P.kind == "O" and s.kind == "O" and s.ids[1] == P.ids[1] then hand = i end
  end
  for i = lead + 1, #guide.steps do
    local s, st = guide.steps[i], guide.state[i]
    if s.trip and s.what == "train" and not s.forward and (s.min or 0) <= level and (s.min or 0) > P.wl
       and st ~= G.DONE and st ~= G.SKIPPED and not (ns.Arbiter and ns.Arbiter.PutOffWhy(s)) then
      s.forward = true
      if i > hand + 1 then back.Move(i, guide.steps[hand + 1]) end
      return
    end
  end
end
function ns.GuideHearth(i)
  local s = guide and guide.steps[i or guide.cur or 0]
  local h = s and s.hearth
  if not (h and s.wx) or ns.Ghost() or ns.InFight() then return nil end
  local here, mine = Plain(Call(GetBindLocation)), false
  for _, name in ipairs(chore.Names(h.bind)) do mine = mine or (here ~= nil and here == name) end
  if not mine or not chore.HearthReady() then return nil end
  local continent, px, py = ns.PlayerWorldPos()
  local saves = chore.HearthSaves(s, continent, px, py)
  if saves < chore.HEARTH.LEAST / ((guide.hearthFor == s) and 2 or 1) then return nil end
  if not h.picked and chore.HearthLater(i or guide.cur, saves) then return nil end
  return h, saves
end

local function NeedsFirst(s)
  local named, out, open = guide.handIns or {}, {}, false
  for _, p in ipairs(s.any or {}) do open = open or Turned(p) end
  for _, list in ipairs({ s.pre or {}, open and {} or s.any or {} }) do
    for _, p in ipairs(list) do
      if named[p] ~= nil and not Turned(p) then out[#out + 1] = p end
    end
  end
  return out
end
local function WaitsOn(s)
  local needs = NeedsFirst(s)
  for _, p in ipairs(needs) do if Parked(p) then return p end end
  return needs[1]
end
ns.GuideWaitsOn = WaitsOn
ns.GuideNeedsFirst = NeedsFirst
local function AfterWords(p)
  local fill = { quest = guide.handIns[p] }
  return Parked(p) and ns.Word("both.step-why.after.parked", fill) or ns.Word("both.step-why.after", fill)
end

local function Needs(s)
  if s.min and (Plain(UnitLevel("player")) or 0) < s.min then
    return ns.Word("both.step-why.level", { level = s.min }), { level = s.min }
  end
  local id = (s.kind == "T" or (s.kind == "O" and not s.get)) and s.ids[1]
  if not (id and InLog(id)) then return nil end
  local own = s.kind == "O" and ns.StepObjective(s)
  for _, o in ipairs(own and { own } or ns.QuestObjectives(id)) do
    if o.skill ~= nil and not Plain(o.finished) then
      local _, rank, need, skill = ns.SkillObjective(Plain(o.text))
      if need and rank < need then
        local short = { skill = skill, rank = need }
        return ns.Word("both.step-why.skill", short), short
      end
    end
  end
  return nil
end

function chore.TakesFrom(s, t)
  if s.kind ~= "S" or t.kind ~= "S" or type(s.takes) ~= "table" or type(t.need) ~= "table" then return false end
  local function List(v) return type(v) == "table" and v or {} end
  local got = { items = {}, recipes = {}, skills = {} }
  for _, row in ipairs(List(t.need.items)) do
    if type(row) == "table" and row[1] ~= nil then got.items[tostring(row[1])] = true end
  end
  for _, v in ipairs(List(t.need.recipes)) do got.recipes[tostring(v)] = true end
  for _, row in ipairs(List(t.need.skills)) do
    if type(row) == "table" and row[1] ~= nil and row[2] == 1 then got.skills[tostring(row[1])] = true end
  end
  for kind, have in pairs(got) do
    for _, v in ipairs(List(s.takes[kind])) do if have[tostring(v)] then return true end end
  end
  return false
end

local function BaseState(s)
  if s.kind == "S" then
    if chore.Ticked(s) then return G.DONE end
    if ErrandDone(s) then chore.Tick(s); return G.DONE end
    if Skipped(s) then return G.SKIPPED, ns.Word("both.step-why.skipped") end
    if s.what == "wall" then return G.WAIT, s.text end
    for _, t in ipairs(type(s.takes) == "table" and guide and guide.steps or {}) do
      if t ~= s and chore.TakesFrom(s, t) then
        local st = BaseState(t)
        if st == G.TODO or st == G.WAIT then return G.WAIT, ns.Word("both.step-why.takes", { step = t.text }) end
      end
    end
    local short = Needs(s)
    if short then return G.WAIT, short end
    local pay = type(s.need) == "table" and tonumber(s.need.pay)
    local have = pay and Plain(Call(GetMoney))
    if pay and have and have < pay then return G.WAIT, ns.Word("both.step-why.money", { money = ns.ChoreRules.Coins(pay) }) end
    return G.TODO, ns.Arbiter and ns.Arbiter.PutOffWhy(s) or nil
  end
  local ids = s.ids
  if s.kind == "D" then
    local have, open = false, false
    for _, q in ipairs(ids) do
      if InLog(q) then have = true; open = open or not Complete(q) elseif Turned(q) then have = true end
    end
    if have and not open then return G.DONE end
    if have then return G.TODO end
    return G.WAIT, ns.Word("both.step-why.run")
  end
  if ns.EpicStepDone({ kind = s.kind, ids = ids, target = s.target, get = s.get, gi = s.gi, ga = s.ga, count = s.count }) then
    return G.DONE
  end
  local id = ids[1]
  if s.kind == "P" then
    if Saved().notOffered[id] then
      return G.BLOCKED, ns.Word("both.step-why.not-offered", { npc = s.npc }) or ns.Word("both.step-why.not-offered.giver")
    end
    local after = WaitsOn(s)
    if after then return G.WAIT, AfterWords(after) end
    local short = Needs(s)
    if short then return G.WAIT, short end
    return G.TODO
  end
  if Failed(id) then return G.BLOCKED, ns.Word("both.step-why.failed") end
  if not InLog(id) then return G.WAIT, ns.Word("both.step-why.pickup") end
  local short = Needs(s)
  if short then return G.WAIT, short end
  if s.kind == "O" and not s.get then
    for _, t in ipairs(guide and guide.steps or {}) do
      if t.get and t.kind == "O" and t.ids[1] == id then
        local st = BaseState(t)
        if st == G.TODO or st == G.WAIT then return G.WAIT, ns.Word("both.step-why.takes", { step = t.text }) end
      end
    end
  end
  if s.kind == "T" and not Complete(id) then return G.WAIT, ns.Word("both.step-why.objectives") end
  return G.TODO
end

local function Expected(s)
  for _, p in ipairs(s.pre or {}) do if not Turned(p) then return false end end
  if s.any and #s.any > 0 then
    local one = false
    for _, p in ipairs(s.any) do if Turned(p) then one = true; break end end
    if not one then return false end
  end
  if s.par and not InLog(s.par) then return false end
  if s.dis and InLog(s.dis) then return false end
  return true
end

local function StepState(s)
  local st, why = BaseState(s)
  if st ~= G.DONE and s.kind ~= "D" and Parked(s.ids[1]) then
    return G.PARKED, st == G.WAIT and ns.Word("both.step-why.parked.waiting", { why = why }) or ns.Word("both.step-why.parked"), st
  end
  return st, why, st
end

local function WhyLine(state, why)
  if not why then return nil end
  if state == G.WAIT then return ns.Word("both.step-why.waiting", { why = why }) end
  if state == G.BLOCKED then return ns.Word("both.step-why.blocked", { why = why }) end
  return (why:gsub("^%l", string.upper))
end
ns.GuideWhyLine = WhyLine

local function GuideStep(e, i)
  local s = { i = i, p = i, kind = e.k, ids = e.ids or {}, inst = e.inst, text = e.text or "", name = e.name, npc = e.npc,
              zone = e.zone, min = e.min, req = e.req, target = e.target, count = e.count, mobs = e.mobs, bosses = e.bosses,
              lv = type(e.lv) == "table" and e.lv or nil,
              things = type(e.things) == "string" and e.things or nil,
              qmobs = e.qmobs, face = e.face, map = e.map, ground = e.ground, limit = e.limit,
              careful = type(e.careful) == "string" and e.careful or nil,
              xp = tonumber(e.xp), sec = tonumber(e.sec),
              wl = tonumber(e.wl),
              kh = tonumber(e.kh), kn = tonumber(e.kn),
              along = e.along and true or nil,
              al = type(e.al) == "table" and e.al or nil, sp = type(e.sp) == "table" and e.sp or nil,
              ic = type(e.ic) == "string" and e.ic or nil,
              en = tonumber(e.en),
              ni = tonumber(e.ni), oi = tonumber(e.oi), mi = type(e.mi) == "table" and e.mi or nil,
              ar = type(e.ar) == "table" and e.ar or nil,
              hr = type(e.hr) == "table" and e.hr or nil,
              fr = e.fr and true or nil,
              talk = e.talk and true or nil,
              mv = type(e.mv) == "string" and e.mv or nil,
              under = e.under and true or nil,
              guess = e.guess and true or nil,
              pre = e.pre, any = e.any, par = e.par, dis = e.dis,
              what = e.what, need = type(e.need) == "table" and e.need or {}, key = e.key, cost = e.cost,
              takes = type(e.takes) == "table" and e.takes or nil,
              cash = tonumber(e.cash), spend = tonumber(e.spend), gain = tonumber(e.gain),
              group = e.grp and true or nil,
              grind = tonumber(e.grind),
              maybe = e.maybe and true or nil,
              rw = type(e.rw) == "table" and e.rw or nil,
              it = tonumber(e.it),
              get = tonumber(e.get), gi = type(e.gi) == "table" and e.gi or nil, ga = e.ga and true or nil,
              sk = type(e.sk) == "table" and e.sk or nil,
              trip = tonumber(e.trip), why = type(e.why) == "string" and e.why or nil,
              cq = tonumber(e.cq) }
  if type(e.at) == "table" then s.wx, s.wy, s.z = e.at[1], e.at[2], e.at[3] end
  local h = e.hearth
  if type(h) == "table" and type(h.b) == "table" and type(h.at) == "table" then
    s.hearth = { town = h.t, bind = h.b, inst = h.i, wx = h.at[1], wy = h.at[2], saves = tonumber(h.s) or 0, picked = h.p and true or nil,
                 cd = tonumber(h.cd) }
    s.hw = { { h.at[1], h.at[2] }, kind = "hw" }
    for _, b in ipairs(type(h.w) == "table" and h.w or {}) do s.hw[#s.hw + 1] = { b[1], b[2], rise = (s.z and b[3]) and s.z - b[3] or nil } end
  end
  local covs = { way = "cov", alt = "acov", ez = "ecov" }
  for key, into in pairs({ way = "bends", alt = "alt", ez = "easy" }) do
    if type(e[key]) == "table" then
      s[into] = { kind = key }
      for k, b in ipairs(e[key]) do s[into][k] = { b[1], b[2], rise = (s.z and b[3]) and s.z - b[3] or nil } end
      for _, k in ipairs(type(e[covs[key]]) == "table" and e[covs[key]] or {}) do
        if s[into][k] then s[into][k].cov = true elseif k == #s[into] + 1 then s[into].endCov = true end
      end
    end
  end
  if type(e.also) == "table" then
    s.also = {}
    for _, a in ipairs(e.also) do
      if type(a.l) == "table" and type(a.at) == "table" and a.npc then
        local o = { l = { a.l[2], a.l[3], c = a.l[1] }, npc = a.npc, inst = a.inst, wx = a.at[1], wy = a.at[2], z = a.at[3],
                    map = a.map, zone = a.zone, cost = a.cost, text = a.text }
        if type(a.way) == "table" then
          o.bends = {}
          for k, b in ipairs(a.way) do o.bends[k] = { b[1], b[2], rise = (o.z and b[3]) and o.z - b[3] or nil } end
        end
        s.also[#s.also + 1] = o
      end
    end
  end
  if type(e.route) == "table" then
    s.route = {}
    for k, p in ipairs(e.route) do
      local path = {}
      for j, b in ipairs(p.w or {}) do path[j] = { b[1], b[2], z = b[3] } end
      s.route[k] = { path = path, inst = p.i, ride = p.r and { kind = p.r, text = p.t or "", npc = p.n, ni = tonumber(p.ni),
                                                               node = tonumber(p.d),
                                                               lands = path[1] and { path[1][1], path[1][2], continent = p.i } } or nil }
    end
  end
  local around = e.walk or e.loop
  if type(around) == "table" and #around > 1 then
    s.loop, s.walks = {}, e.walk ~= nil
    s.each = (e.each and e.walk == nil) and true or nil
    for k, p in ipairs(around) do s.loop[k] = { p[1], p[2] } end
    s.loop[#s.loop + 1] = { around[1][1], around[1][2] }
    if s.each then
      s.stops, s.respawn = {}, tonumber(e.rs)
      for k, p in ipairs(around) do s.stops[k] = { p[1], p[2] } end
      ns.EachLoop(s)
    end
  end
  return s
end

local paste = {}
function paste.Who(kind, words)
  local verb = ({ P = "^Pick up (.+)$", T = "^Turn in (.+)$" })[kind]
  local quest = verb and (words or ""):gsub(", if offered$", ""):match(verb)
  if not quest then return nil end
  local named, who = quest:match("^(.+)" .. (kind == "P" and " from " or " to ") .. "(.+)$")
  return named or quest, who
end
ns.PastedWho = paste.Who
function paste.Step(t, st, k)
  if st.entry then return GuideStep(st.entry, k) end
  local words = (k == 1 and t.lineName ~= "" and t.lineName) or (st.kind and StepName(st)) or t.name
  local quest, who = paste.Who(st.kind, words)
  local spot = k == 1 and t.spot or { st.wx, st.wy }
  return { i = k, kind = st.kind, ids = st.ids or {}, text = words, name = quest, npc = who or st.npc, what = st.what,
           inst = t.continent, wx = spot[1], wy = spot[2], loop = k == 1 and t.loop or nil, walks = (k == 1 and t.loop) and true or nil }
end
function paste.Guide()
  local t = not guide and tracks.e and tracks.e.target
  if not (t and t.pasted) then return nil end
  local g = t.guide
  if not g then
    local e = t.epic
    g = { pasted = true, key = e and e.key or nil, name = e and e.name or KINDS.e.label, steps = {}, state = {}, why = {},
          notes = {}, missing = {} }
    for k, st in ipairs(t.steps or { {} }) do g.steps[k] = paste.Step(t, st, k) end
    t.guide = g
  end
  if g.stepWas == t.step and g.at and GetTime() - g.at < 0.25 then return g end
  g.stepWas, g.at, g.done = t.step, GetTime(), 0
  local at = nil
  if not t.steps then at = 1 end
  for k, st in ipairs(t.steps or {}) do if st == t.step then at = k end end
  g.cur, g.handIn = at, t.handIn
  local queued = {}
  for _, st in ipairs(t.queue or {}) do queued[st] = true end
  for k in ipairs(g.steps) do
    local st = t.steps and t.steps[k]
    local done = st and k ~= at and ((not queued[st] and (not at or k < at)) or ns.EpicStepDone(st))
    g.state[k] = done and G.DONE or G.TODO
    if done then g.done = g.done + 1 end
  end
  g.all = #g.steps
  return g
end
local function EpicNow()
  local g = guide or paste.Guide()
  return g and g.cur and g.steps[g.cur] or nil
end
ns.PastedGuide = paste.Guide
function ns.PastedChanged(started)
  Changed(started and "loaded" or "state")
  if ns.BeaconFollow then ns.BeaconFollow() end
end
function paste.Code(st)
  local e = st.entry
  local kind, ids = e and e.k or st.kind, e and e.ids or st.ids
  if kind == "S" then
    local what, npc = e and e.what or st.what, e and e.npc or st.npc
    return what and ("S" .. tostring(what) .. ":" .. tostring(npc)) or nil
  end
  if not kind or type(ids) ~= "table" or #ids == 0 then return nil end
  return kind .. table.concat(ids, ".")
end

local CHORE_DONE_BY = { train = "TRAINER_CLOSED", repair = "MERCHANT_CLOSED", sell = "MERCHANT_CLOSED",
                        restock = "MERCHANT_CLOSED", flightpath = "TAXIMAP_CLOSED", bind = "HEARTHSTONE_BOUND" }
local choreWith = nil
ns.On({ "GOSSIP_SHOW", "MERCHANT_SHOW", "TRAINER_SHOW", "TAXIMAP_OPENED" }, function()
  choreWith = Plain(Call(UnitName, "npc")) or choreWith
end)
ns.On({ "TRAINER_CLOSED", "MERCHANT_CLOSED", "TAXIMAP_CLOSED", "HEARTHSTONE_BOUND" }, function(event)
  if not choreWith then return end
  choreDealt[event] = choreDealt[event] or {}
  choreDealt[event][choreWith] = true
  local tr = tracks.e
  if tr and tr.target and tr.target.step and ns.EpicStepDone(tr.target.step) then NextEpicStep(tr) end
end)
function paste.ChoreDone(st)
  if st.entry then return ErrandDone(GuideStep(st.entry, 0)) end
  if not st.npc or st.npc == "" then return true end
  local by = CHORE_DONE_BY[st.what]
  if by then return (choreDealt[by] or {})[st.npc] == true end
  for _, names in pairs(choreDealt) do if names[st.npc] then return true end end
  return false
end
ns.PastedChoreDone = paste.ChoreDone
function ns.PastedClosed()
  local t = tracks.e.target
  if not (t and t.pasted and ns.GuideClosed) then return end
  local said, seen = "", {}
  for _, st in ipairs({ t.step or false, unpack(t.steps or {}) }) do
    local code = st and paste.Code(st)
    local with = code and (said == "" and code or (said .. "," .. code))
    if with and not seen[code] and #with <= 40 then seen[code], said = true, with end
  end
  if said ~= "" then ns.GuideClosed("epic", said) end
end

local function PointArrow()
  local tr = tracks.e
  local s = guide and guide.cur and guide.steps[guide.cur]
  if not s or not s.wx or guide.arrowOff == guide.cur then
    if tr.target and tr.target.guided then Clear(tr) end
    return
  end
  local path = nil
  local continent, px, py = ns.PlayerWorldPos()
  guide.pointedOn = continent
  local h = guide.hearthFor == s and s.hearth
  if h then
    local walk = {}
    for k = 2, #(s.hw or {}) do walk[#walk + 1] = s.hw[k] end
    walk[#walk + 1] = { s.wx, s.wy, rise = s.z and 0 or nil }
    tr.target = { continent = continent, wx = s.wx, wy = s.wy, name = ns.StepLabel(s), leg = 1, lap = 1, guided = true,
                  route = ns.NewRoute({ { kind = "H", text = h.town or "" },
                                        { kind = "W", path = walk, continent = h.inst, start = { h.wx, h.wy } } }) }
    tr.name:SetText(ns.StepLabel(s))
    tr.dist:SetText("")
    tr.frame:Show()
    return
  end
  if s.route and continent and (continent ~= s.inst or not px or Dist(s.wx, s.wy, px, py) >= ways.ROUTE_FROM) then
    local legs = {}
    for _, p in ipairs(s.route) do
      if #legs == 0 and p.inst == continent and #p.path > 0 then
        legs[1] = { kind = "W", path = p.path, continent = continent }
      elseif #legs > 0 then
        if p.ride then legs[#legs + 1] = p.ride end
        if p.inst ~= continent or #p.path == 0 then break end
        legs[#legs + 1] = { kind = "W", path = p.path, continent = continent, start = p.path[1] }
      end
    end
    if #legs > 0 then
      local first = legs[1].path
      tr.target = { continent = continent, wx = first[#first][1], wy = first[#first][2], name = ns.StepLabel(s),
                    path = #first > 1 and first or nil, leg = 1, lap = 1, route = ns.NewRoute(legs), guided = true }
      tr.name:SetText(ns.StepLabel(s))
      tr.dist:SetText("")
      tr.frame:Show()
      return
    end
  end
  local bends = continent == s.inst and StepBends(s, px, py)
  if bends and px and #bends > 0 then path = ways.To(s, bends) end
  tr.target = { continent = s.inst, wx = s.wx, wy = s.wy, name = ns.StepLabel(s), path = path, leg = 1, loop = s.loop, lap = 1,
                walks = s.walks, guided = true }
  tr.name:SetText(ns.StepLabel(s))
  tr.dist:SetText("")
  tr.frame:Show()
end

function ns.GuidePickWay(i, easy)
  local s = guide and guide.steps[i]
  if not s or not s.easy or (s.easyPicked and true or false) == (easy and true or false) then return false end
  s.easyPicked = easy and true or nil
  if ns.MarkChanged then ns.MarkChanged("status") end
  if i == guide.cur then
    guide.arrowOff = nil
    PointArrow()
    if ns.BeaconFollow then ns.BeaconFollow() end
  end
  Changed("state")
  return true
end

function ns.StepLabel(s)
  if (s.kind == "P" or s.kind == "T") and s.npc and s.npc ~= "" then
    return string.format("%s: %s %s", s.npc, s.kind == "P" and "pick up" or "turn in", s.name or s.text)
  end
  if s.kind == "S" then return naming.Chore(s) end
  return s.text
end

local handin = {}
function handin.Count() return guide and (#guide.steps - (guide.extra and 1 or 0)) or 0 end
function handin.OnPlan() return guide.planCur or guide.cur end
handin.NearWay = NearWay
handin.Bends = StepBends
handin.InLog = InLog
function handin.Drop()
  local x, n = guide.extra, #guide.steps
  if not x then return end
  if guide.steps[n] == x then
    guide.steps[n], guide.state[n], guide.why[n], guide.base[n], guide.doneAt[n] = nil, nil, nil, nil, nil
  end
  guide.extra = nil
end
function handin.Ready(id) return id ~= nil and InLog(id) and Complete(id) and not Failed(id) end
function handin.WayOn(s, px, py)
  local bends, near, k = StepBends(s, px, py) or {}, math.huge, 0
  for j, b in ipairs(bends) do
    local d = Dist(b[1], b[2], px, py)
    if d < near then near, k = d, j end
  end
  local way = { { px, py } }
  for j = k + 1, #bends do way[#way + 1] = bends[j] end
  way[#way + 1] = { s.wx, s.wy }
  return way
end
function handin.Extra(e)
  guide.extras[e] = guide.extras[e] or (type(e.at) == "table" and e.at[1] and e.at[2] and
    { kind = "T", ids = { e.q }, inst = e.i, wx = e.at[1], wy = e.at[2], z = e.at[3], npc = e.npc, need = {}, extra = true })
    or false
  return guide.extras[e] or nil
end
function handin.Takes(t, st, base)
  if t.kind == "T" then return st == G.TODO or (st == G.PARKED and base == G.TODO) end
  if t.kind ~= "P" or t.limit or not Expected(t) then return false end
  if st == G.TODO then return true end
  return st == G.WAIT and t.req ~= nil and not WaitsOn(t) and (Plain(UnitLevel("player")) or 0) >= t.req
end
function handin.Place(x)
  local n = #guide.steps + 1
  local id = x.ids[1]
  x.i, x.name = n, Plain(Call(C_QuestLog.GetTitleForQuestID, id)) or ("quest " .. id)
  x.text = "Turn in " .. x.name .. ((x.npc and x.npc ~= "") and (" to " .. x.npc) or "")
  guide.steps[n], guide.state[n], guide.base[n], guide.extra = x, G.TODO, G.TODO, x
  return n
end
ns.GuideHandIn = handin
function ns.PastedHandIn(tr)
  local t = tr.target
  local continent, px, py = ns.PlayerWorldPos()
  if not (t and t.step and t.queue and px and continent == t.continent) or t.handIn then return end
  local best, k = t.wx and Dist(t.wx, t.wy, px, py) or math.huge, nil
  for j, st in ipairs(t.queue) do
    local d = st.kind == "T" and st.wx and handin.Ready(st.ids and st.ids[1]) and Dist(st.wx, st.wy, px, py)
    if d and d <= ns.Rules.Reach("giver") and d < best then best, k = d, j end
  end
  if not k then return end
  local st, was = table.remove(t.queue, k), t.step
  was.wx, was.wy = was.wx or t.wx, was.wy or t.wy
  was.back = was.back or { path = t.path, loop = t.loop, walks = t.walks }
  table.insert(t.queue, 1, was)
  table.insert(t.queue, 1, st)
  NextEpicStep(tr)
  local key = (st.npc and st.npc ~= "") and "handin" or "handin_here"
  t.path, t.handIn = nil, not ns.Rules.Quiet(key) and ns.Rules.Say(key, { won = ns.Arbiter.Name(st) or "the quest",
                                                                         wonNpc = st.npc }) or true
  if t.guide then t.guide.at = nil end
  if ns.PastedChanged then ns.PastedChanged() end
end

local play = { last = nil }
function play.Log()
  local seen = known.log
  if not seen.read then
    seen.read, seen.ids = true, {}
    for i = 1, Plain(Call(C_QuestLog.GetNumQuestLogEntries)) or 0 do
      local info = Call(C_QuestLog.GetInfo, i)
      local id = type(info) == "table" and not Plain(info.isHeader) and Plain(info.questID)
      if id then seen.ids[#seen.ids + 1] = id end
    end
  end
  return seen.ids
end
function play.Saved()
  local sv = Saved()
  local p = sv.live
  if type(p) ~= "table" or p.version ~= guide.version or type(p.log) ~= "table" then
    p = { version = guide.version, log = {}, gained = 0, reckoned = 0 }
    for _, id in ipairs(play.Log()) do p.log[id] = true end
    sv.live = p
  end
  return p
end
function play.Mark()
  local level, xp, full = Plain(Call(UnitLevel, "player")), Plain(Call(UnitXP, "player")), Plain(Call(UnitXPMax, "player"))
  play.last = (level and xp and full) and { level = level, xp = xp, full = full } or nil
end
function play.Xp()
  if not guide then return end
  local last = play.last
  play.Mark()
  local now = play.last
  if not (last and now) then return end
  local gain = (now.level > last.level or now.xp < last.xp) and (last.full - last.xp + now.xp) or (now.xp - last.xp)
  if gain > 0 and guide.cur then
    local p = play.Saved()
    p.gained = p.gained + gain
  end
  play.Check()
end
function play.Code() return guide and math.max(20, math.min(255, math.floor(play.Raw() * 20 + 0.5))) or 20 end
function play.Check()
  if guide and play.Code() ~= (play.sent or 20) then ns.epicDirty = true end
end
ns.On("PLAYER_XP_UPDATE", play.Xp)
ns.On({ "QUEST_ACCEPTED", "QUEST_REMOVED", "QUEST_LOG_UPDATE" }, function() play.Check() end)
function play.Done(s)
  local p = play.Saved()
  p.reckoned = p.reckoned + (s.xp or 0)
end
function play.Off()
  local p, n = play.Saved(), 0
  for _, id in ipairs(play.Log()) do
    if not (p.log[id] or guide.quests[id]) then n = n + 1 end
  end
  return n
end
function play.Raw()
  local p = play.Saved()
  local full = Plain(Call(UnitXPMax, "player"))
  local own = (full and full > 0) and (p.gained - p.reckoned) / full or 0
  return ns.Rules.Play(play.Off(), own, (ns.Camps and ns.Camps.Pace()) or ns.GuidePace())
end
function ns.GuidePlay()
  if not guide then return 1 end
  return play.Code() / 20
end
ns.GuidePlayKept = play

local function Evaluate()
  if not guide then return end
  local changed, wasExtra = false, guide.extra
  handin.Drop()
  pcall(chore.TripForward)
  local sv = Saved()
  for id in pairs(sv.notOffered) do
    if InLog(id) or Turned(id) then sv.notOffered[id] = nil end
  end
  for key in pairs(sv.gotten) do
    local q = tonumber(tostring(key):match("^(%d+):"))
    if not q or not InLog(q) then sv.gotten[key] = nil end
  end
  local marks = sv.parked[guide.key] or {}
  for id in pairs(marks) do if Turned(id) then marks[id] = nil end end
  for i, s in ipairs(guide.steps) do
    local line = ns.ItemStepLine and ns.ItemStepLine(s)
    if line and line ~= s.text then s.text, s.name, changed = line, line, true end
    local st, why, base = StepState(s)
    guide.base[i] = base
    if guide.state[i] ~= st or guide.why[i] ~= why then
      local was = guide.state[i]
      guide.state[i], guide.why[i], changed = st, why, true
      if was ~= nil and st == G.DONE then
        guide.doneAt[i] = time()
        play.Done(s)
        Event("done", i)
        Changed("done", i)
      elseif was ~= nil and st == G.BLOCKED then
        Event("blocked", i)
      end
    end
  end
  pcall(chore.BindMoved)
  if type(sv.run) == "table" and sv.run.version == guide.version then
    local n = 0
    for i = 1, #guide.steps do if guide.state[i] == G.DONE then n = n + 1 end end
    sv.run.done = n
  end
  guide.backToParked = false
  local ok, cur, onPlan, extra, d = pcall(ns.Arbiter.Lead, guide, handin)
  if not ok then
    if not guide.arbiterSaid then
      guide.arbiterSaid = true
      ns.Print("The quest epic's arbiter hit an error, so the guide follows the plan's order: " .. tostring(cur))
    end
    cur, extra = nil, nil
    for i = 1, #guide.steps do
      if guide.state[i] == G.TODO then
        cur = i
        break
      end
    end
    onPlan = cur
    d = cur and { won = { key = ns.Trace.Key(guide.steps[cur]), text = guide.steps[cur].text }, rule = "plan" } or nil
  end
  if not d then
    for i = 1, #guide.steps do
      if guide.state[i] == G.PARKED and guide.base[i] == G.TODO and not (ns.Drawer and ns.Drawer.Background(guide.steps[i].ids[1])) then
        cur, guide.backToParked = i, true; break
      end
    end
    onPlan, d = cur, ns.Arbiter.Settle(cur and guide.steps[cur])
  end
  cur = extra and handin.Place(extra) or cur
  guide.planCur, guide.decision = onPlan, d
  local lead = cur and guide.steps[cur]
  local ahead = lead and cur ~= onPlan and (lead.extra or lead.kind == "T" or lead.kind == "P") and (d.line or true) or nil
  if d.line ~= guide.reason or ahead ~= guide.handIn then guide.reason, guide.handIn, changed = d.line, ahead, true end
  local afterKey = d.after and d.after.key or nil
  if afterKey ~= guide.afterKey then guide.afterKey, changed = afterKey, true end
  local over = not cur
  for i = 1, over and #guide.steps or 0 do
    if guide.state[i] == G.TODO or guide.state[i] == G.WAIT then over = false; break end
  end
  if over and guide.over == false and not guide.stopSaid then guide.stopSaid = ns.UI.SayStop(ns.UI.EpicLook(guide.key)) end
  guide.over = over
  if cur ~= guide.cur or extra ~= wasExtra then
    guide.cur, guide.arrowOff = cur, nil
    if ns.TraceLead then pcall(ns.TraceLead, guide, d) end
    guide.hearthFor = cur and ns.GuideHearth(cur) and guide.steps[cur] or nil
    PointArrow()
    if ns.BeaconFollow then ns.BeaconFollow() end
    changed = true
  else
    local offer = cur and ns.GuideHearth(cur) and guide.steps[cur] or nil
    if offer ~= guide.hearthFor then
      guide.hearthFor = offer
      PointArrow()
      changed = true
    end
  end
  if ways.Take() then
    PointArrow()
    changed = true
  end
  if ns.Director then
    local looked, err = pcall(ns.Director.Look, guide, d)
    if not looked then ns.Report("the director", err) end
  end
  local take, give, hold = {}, {}, {}
  for i, s in ipairs(guide.steps) do
    local st = guide.state[i]
    if st ~= G.BLOCKED and st ~= G.DONE then
      if s.kind == "P" and (st ~= G.PARKED or i == cur) and (not s.limit or i == cur) then
        for _, id in ipairs(s.ids) do take[#take + 1] = id end
      elseif s.kind == "P" and s.limit then
        for _, id in ipairs(s.ids) do hold[#hold + 1] = id end
      end
      if s.kind == "T" then for _, id in ipairs(s.ids) do give[#give + 1] = id end end
    end
  end
  for _, id in ipairs(guide.maybe or {}) do take[#take + 1] = id end
  ns.EpicAccept(take)
  ns.EpicHandIn(give)
  ns.EpicHold(hold)
  if changed then Changed("state") end
end
ns.GuideEvaluate = Evaluate
if C_Timer.NewTicker then
  C_Timer.NewTicker(2, function()
    if guide then pcall(Evaluate) end
  end)
end

local landed = { JUMP = 300, WALK_MOST = 14 * 1.25, RIDE = 60, EVERY = 1, SETTLED = 3, NEAR = 150, HERE = 120,
                 spots = {}, away = false, ride = nil }
function landed.Pick(also, c, x, y)
  local best, near = nil, landed.NEAR
  for _, e in ipairs(also or {}) do
    if e.l and e.l.c == c then
      local d = Dist(e.l[1], e.l[2], x, y)
      if d <= near and (not best or d < near) then best, near = e, d end
    end
  end
  return best
end
ns.LandedPick = landed.Pick
function landed.Start(c, x, y, now)
  local spots = landed.spots
  local last = spots[#spots]
  local function yards(p) return Dist(p.x, p.y, x, y) end
  local function fast(p) return yards(p) / math.max(now - p.t, 0.001) > landed.WALK_MOST end
  if last.c ~= c then return last end
  if landed.away then return yards(last) >= landed.JUMP and last or nil end
  if yards(last) >= landed.JUMP and fast(last) then return last end
  if not landed.ride then
    for _, p in ipairs(spots) do
      if yards(p) >= landed.JUMP and fast(p) then landed.ride = p; break end
    end
  end
  local back = nil
  for _, p in ipairs(spots) do if now - p.t >= landed.SETTLED then back = p end end
  if not landed.ride or not back or fast(back) then return nil end
  local from = landed.ride
  landed.ride = nil
  return yards(from) >= landed.JUMP and from or nil
end
function landed.See(c, x, y, flags, now)
  if flags.taxi or flags.instance or flags.dead then
    landed.away = #landed.spots > 0
    return false
  end
  if not c or not x then return false end
  local spots = landed.spots
  local from = #spots > 0 and landed.Start(c, x, y, now) or nil
  if from then
    landed.spots, landed.ride = {}, nil
    spots = landed.spots
  end
  local spot = { c = c, x = x, y = y, t = now }
  if #spots > 1 and now - spots[#spots - 1].t < landed.EVERY then spots[#spots] = spot else spots[#spots + 1] = spot end
  while #spots > 2 and now - spots[1].t > landed.RIDE do table.remove(spots, 1) end
  landed.away = false
  if from then landed.Move(c, x, y) end
  if from and ns.Arbiter then ns.Arbiter.Arrived() end
  return from ~= nil
end
ns.EpicJumpSee = landed.See
function landed.Move(c, x, y)
  if not guide then return end
  local moved = false
  for i, s in ipairs(guide.steps) do
    local st = guide.state[i]
    if st ~= G.DONE and st ~= G.SKIPPED then
      if s.kind ~= "S" then break end
      local e = s.also and not (s.inst == c and s.wx and Dist(s.wx, s.wy, x, y) <= landed.HERE) and landed.Pick(s.also, c, x, y)
      if e and e.npc ~= s.npc then
        local function swap(words)
          if not (words and s.npc) then return words end
          local a, b = string.find(words, " at " .. s.npc, 1, true)
          return a and (words:sub(1, a - 1) .. " at " .. e.npc .. words:sub(b + 1)) or words
        end
        s.text, s.name = e.text or swap(s.text), e.text or swap(s.name)
        s.npc, s.inst, s.wx, s.wy, s.z, s.map, s.zone = e.npc, e.inst, e.wx, e.wy, e.z, e.map or s.map, e.zone or s.zone
        s.cost, s.bends, s.alt, s.route, s.easy, s.easyPicked = e.cost or s.cost, e.bends, nil, nil, nil, nil
        s.ground, s.under, s.guess, s.careful = nil, nil, nil, nil
        moved = true
      end
    end
  end
  if not moved then return end
  guide.arrowOff = nil
  PointArrow()
  if ns.BeaconFollow then ns.BeaconFollow() end
  Changed("state")
end
ns.EpicLandedMove = landed.Move
function landed.Tick()
  if not guide then landed.spots, landed.ride = {}, nil; return end
  local c, x, y = ns.PlayerWorldPos()
  pcall(landed.See, c, x, y, { taxi = Plain(Call(UnitOnTaxi, "player")), instance = Plain(Call(IsInInstance)),
                               dead = Plain(Call(UnitIsDeadOrGhost, "player")) }, GetTime())
end
ns.EpicJumpTick = landed.Tick
if C_Timer.NewTicker then C_Timer.NewTicker(landed.EVERY, landed.Tick) end

function ns.GuidePace()
  local done, ratios = {}, {}
  for i, at in pairs(guide and guide.doneAt or {}) do
    local s = guide.steps[i]
    if s and (s.sec or 0) > 0 then done[#done + 1] = { at = at, sec = s.sec } end
  end
  table.sort(done, function(a, b) return a.at < b.at end)
  for k = math.max(2, #done - 8), #done do
    local r = (done[k].at - done[k - 1].at) / done[k].sec
    if r > 0.1 and r < 10 then ratios[#ratios + 1] = r end
  end
  if #ratios < 3 then return 1 end
  table.sort(ratios)
  return math.max(0.5, math.min(4, ratios[math.ceil(#ratios / 2)]))
end

function ns.GuideLevelPace()
  local C = ns.Camps
  local camp = C and not (C.here and C.Busy(C.here)) and C.Pace()
  return camp or ns.GuidePace()
end

function ns.GuideLevelIn()
  if not guide or not guide.cur then return nil end
  local have, full = Plain(Call(UnitXP, "player")), Plain(Call(UnitXPMax, "player"))
  if not have or not full or full <= have then return nil end
  local xp, sec, before = 0, 0, 0
  for i = handin.OnPlan(), handin.Count() do
    local s, st = guide.steps[i], guide.state[i]
    if st == G.TODO or st == G.WAIT then
      xp, sec = xp + (s.xp or 0), sec + (s.sec or 0)
      if s.xp and xp >= full - have then
        if not ns.Rules.Said("reckoned", before, ns.GuidePlay()) then return nil end
        return sec * ns.GuideLevelPace(), i, (Plain(Call(UnitLevel, "player")) or 0) + 1
      end
      before = before + 1
    end
  end
  return nil
end

function ns.GuideGrind()
  if not guide then return nil end
  local level, at, before = Plain(Call(UnitLevel, "player")) or 0, nil, 0
  for i, s in ipairs(guide.steps) do
    local st = guide.state[i]
    if st ~= G.DONE and st ~= G.SKIPPED and s.grind and s.grind > level then
      at = i
      break
    end
    if st == G.TODO or st == G.WAIT then before = before + 1 end
  end
  local wall = nil
  for i = 1, guide.cur and 0 or #guide.steps do
    if guide.state[i] == G.WAIT and not (guide.steps[i].kind == "P" and WaitsOn(guide.steps[i])) then wall = i; break end
  end
  local short = nil
  if wall then short = select(2, Needs(guide.steps[wall])) end
  if short and not (at and at <= wall) then
    if short.level then return short.level, 0, wall end
    return nil, 0, wall, short
  end
  if at and ns.Rules.Said("reckoned", before, ns.GuidePlay()) then return guide.steps[at].grind, before, at end
end

function ns.GuideLoad(force)
  ns.guideDecided = true
  if guide then
    guide = nil
    if tracks.e.target and tracks.e.target.guided then Clear(tracks.e) end
  end
  local sh = IndexOfAzerothShared
  local epic = type(sh) == "table" and type(sh.epic) == "table" and sh.epic or nil
  ns.guideOther = nil
  local who = epic and type(epic.char) == "table" and epic.char or nil
  if not epic then
    local sv = Saved()
    sv.stopped, sv.stoppedAt, sv.version, sv.notOffered, sv.parked, sv.hiddenFor, sv.run = nil, nil, nil, {}, {}, nil, nil
    sv.unparking, sv.order = nil, nil
    return Changed("state")
  end
  if type(epic.steps) ~= "table" or #epic.steps == 0 or not who or (who.name or "") == "" then
    return Changed("state")
  end
  local sv = Saved()
  if not ns.IsMe(who) then
    local full = (who.surname or "") ~= "" and (who.name .. " " .. who.surname) or who.name
    ns.guideOther = full
    return Changed("state")
  end
  if not force then
    local opened = type(epic.opened) == "table" and tonumber(epic.opened.at) or 0
    local fresh = epic.fresh and (tonumber(sh.version) or 0) > (tonumber(sv.stopped) or 0)
    if epic.closed or (sv.stopped and not fresh and opened <= (tonumber(sv.stoppedAt) or 0)) then
      if not sv.stopped then
        sv.stoppedAt = time()
        ns.Print(string.format("%s is closed. Its plan and your progress are kept. Type /ioa guide start to pick it up again.",
          epic.name or "The quest epic"))
      end
      sv.stopped = sh.version
      return Changed("state")
    end
  end
  sv.version = sh.version
  local starting = epic.fresh and sv.freshFor ~= sh.version
  if starting then
    sv.freshFor, sv.parked, sv.notOffered, sv.hiddenFor = sh.version, {}, {}, nil
    sv.bound = nil
  end
  sv.stopped, sv.stoppedAt = nil, nil
  local steps, dungeon, handIns = {}, nil, {}
  local places = type(epic.places) == "table" and epic.places or {}
  for i, e in ipairs(epic.steps) do
    steps[i] = GuideStep(e, i)
    steps[i].place = type(places[tonumber(e.pl) or 0]) == "string" and places[tonumber(e.pl)] or nil
    if e.k == "D" and not dungeon then dungeon = i end
    if e.k == "T" and steps[i].ids[1] then handIns[steps[i].ids[1]] = e.name or e.text or ns.Word("both.step-why.quest-before") end
  end
  guide = { key = epic.key or "epic", name = epic.name or "Quest epic", plan = epic.plan, version = sh.version,
            steps = steps, dungeon = dungeon, state = {}, why = {}, base = {}, doneAt = {}, events = {},
            handIns = handIns,
            ends = type(epic.ends) == "table" and epic.ends or {}, extras = {},
            maybe = type(epic.maybe) == "table" and epic.maybe or {},
            notes = type(epic.notes) == "table" and epic.notes or {}, missing = type(epic.missing) == "table" and epic.missing or {},
            brief = type(epic.brief) == "table" and epic.brief or {},
            hidden = type(epic.hidden) == "table" and epic.hidden or {},
            skillShort = type(epic.skillShort) == "table" and epic.skillShort or {},
            later = type(epic.later) == "table" and epic.later or {} }
  guide.quests = {}
  for _, s in ipairs(steps) do for _, id in ipairs(s.ids) do guide.quests[id] = true end end
  for _, e in ipairs(guide.ends) do if type(e) == "table" and e.q then guide.quests[e.q] = true end end
  for _, id in ipairs(guide.maybe) do guide.quests[id] = true end
  for _, q in ipairs(guide.missing) do
    local id = type(q) == "table" and q.id or nil
    if id then guide.quests[id] = true end
  end
  play.Mark()
  play.Saved()
  sv.parked[guide.key] = type(sv.parked[guide.key]) == "table" and sv.parked[guide.key] or {}
  if starting then
    for _, id in ipairs(type(epic.parked) == "table" and epic.parked or {}) do sv.parked[guide.key][id] = true end
  end
  local order = sv.order
  if type(order) == "table" and order.version == sh.version and order.key == guide.key and type(order.moves) == "table" then
    back.Reorder(order.moves)
  else
    sv.order = nil
  end
  local asked = type(sv.unparking) == "table" and sv.unparking[guide.key]
  sv.unparking = nil
  local run = type(sv.run) == "table" and sv.run or {}
  if starting or run.key ~= guide.key then
    run = { key = guide.key, before = 0 }
  elseif run.version ~= sh.version then
    run.before = (run.before or 0) + (run.done or 0)
  end
  run.version, run.done = sh.version, 0
  sv.run = run
  if ns.Arbiter then ns.Arbiter.Reset() end
  Evaluate()
  ns.Print(string.format("%s: the plan loaded with %d steps. /ioa guide shows or hides the card.", guide.name, #steps))
  for id in pairs(type(asked) == "table" and asked or {}) do
    if Parked(id) then back.Unpark(id) end
  end
  Changed("loaded")
end

function ns.GuideInfo() return guide end

function ns.GuideStage(i)
  local d = guide and guide.dungeon
  if not d or not i then return "prep" end
  if i < d then return "prep" end
  if i > d then return "turnin" end
  return Plain(Call(IsInInstance)) and "inside" or "travel"
end

local AT_LOOP = { stay = 15 }
function ns.GuideAtLoop(reach)
  reach = reach or 1
  local s = EpicNow()
  local by = AT_LOOP[reach] or {}
  AT_LOOP[reach] = by
  if not (s and s.loop and ns.AtRing) or ns.Ghost() then by.step = nil; return false end
  local continent, px, py = ns.PlayerWorldPos()
  local was = by.step == s and by.was
  local at = continent == s.inst and px and ns.AtRing(s.loop, px, py, was and AT_LOOP.stay or 0, s.walks, reach) or false
  by.step, by.was = s, at
  return at
end

function ns.GuideInArea()
  local s = EpicNow()
  if not s or ns.Ghost() then return false end
  local continent, px, py = ns.PlayerWorldPos()
  return continent == s.inst and px ~= nil and ns.Arbiter.InArea(s, px, py)
end

function ns.GuideProgress()
  if not guide then return 0, 0 end
  local done, all = 0, 0
  for i = 1, handin.Count() do
    local st = guide.state[i]
    if st == G.DONE then done = done + 1 end
    if st ~= G.SKIPPED then all = all + 1 end
  end
  return done, all
end

function ns.GuideRunProgress()
  local done, all = ns.GuideProgress()
  local run = guide and Saved().run
  local before = type(run) == "table" and run.version == guide.version and run.before or 0
  return before + done, before + all
end

function ns.GuidePark(i, said)
  local s = guide and guide.steps[i]
  if not s or s.kind == "D" or s.kind == "S" or s.extra then return end
  Saved().parked[guide.key][s.ids[1]] = true
  ns.Arbiter.MarkAway("q:" .. s.ids[1], guide.cur == i)
  Event("parked", i)
  ns.Print(said or string.format("You parked %s. The quest is still to do, and the guide comes back to it.", s.name or ("quest " .. s.ids[1])))
  Evaluate()
end

function ns.GuideParkQuest(id, said)
  if not id then return ns.Print("Type /ioa guide park <quest ID> to park a quest.") end
  if not guide then return ns.Print("No quest epic is running, so there's nothing to park a quest in.") end
  for i, s in ipairs(guide.steps) do
    if s.kind ~= "D" and s.kind ~= "S" and s.ids[1] == id then
      if Parked(id) then return ns.Print(string.format("%s is parked already.", s.name or ("quest " .. id))) end
      return ns.GuidePark(i, said)
    end
  end
  ns.Print(string.format("Quest %d isn't in the epic's plan.", id))
end

back.DOUBLE_BACK = 150
back.MOST = 16
back.FAR = 1e6

function back.Spot(s) return s.wx and { s.inst, s.wx, s.wy } or nil end
function back.Gap(a, b)
  if not a or not b then return back.FAR / 2 end
  return a[1] == b[1] and Dist(a[2], a[3], b[2], b[3]) or back.FAR
end
function back.Detour(prev, at, nxt)
  return back.Gap(prev, at) + (nxt and back.Gap(at, nxt) - back.Gap(prev, nxt) or 0)
end

function back.Fit(steps, route, here, after)
  local line, out = {}, {}
  for _, s in ipairs(route) do line[#line + 1] = { spot = back.Spot(s), step = s } end
  local now = line[1]
  for _, s in ipairs(steps) do
    local at, nowAt, best, lo = back.Spot(s), nil, {}, 1
    for k, e in ipairs(line) do
      if e == now then nowAt = k end
      if e.placed and (not after or after(s, e.step)) then lo = k + 1 end
    end
    for k = lo, #line + 1 do
      local prev, nxt = here, nil
      for j = k - 1, 1, -1 do if line[j].spot then prev = line[j].spot; break end end
      for j = k, #line do if line[j].spot then nxt = line[j].spot; break end end
      local cost, when = back.Detour(prev, at, nxt), (nowAt and k <= nowAt) and "now" or "later"
      if not best[when] or cost < best[when].cost - 1e-6 then best[when] = { cost = cost, k = k } end
    end
    local pick = best.later
    if best.now and (not pick or here and pick.cost - best.now.cost > back.DOUBLE_BACK) then pick = best.now end
    table.insert(line, pick.k, { spot = at, step = s, placed = true })
  end
  for k, e in ipairs(line) do
    if e.placed then out[#out + 1] = { step = e.step, before = back.Next(line, k) } end
  end
  return out
end
function back.Next(list, k, mark)
  for j = k + 1, #list do if not list[j][mark or "placed"] and not list[j].own then return list[j].step or list[j].p end end
end
function back.Add(run, front, s)
  for _, m in ipairs(front or {}) do run[#run + 1] = m end
  run[#run + 1] = s
end

function back.SetRun(run)
  local at, state, why, base, doneAt = {}, {}, {}, {}, {}
  for k = #run, 1, -1 do if run[k].extra then table.remove(run, k) end end
  handin.Drop()
  for k, s in ipairs(run) do
    at[s.i] = k
    state[k], why[k], base[k], doneAt[k] = guide.state[s.i], guide.why[s.i], guide.base[s.i], guide.doneAt[s.i]
  end
  guide.state, guide.why, guide.base, guide.doneAt = state, why, base, doneAt
  guide.cur = guide.cur and at[guide.cur]
  guide.planCur = guide.planCur and at[guide.planCur]
  guide.arrowOff = guide.arrowOff and at[guide.arrowOff]
  guide.steps, guide.dungeon = run, nil
  for k, s in ipairs(run) do
    s.i = k
    if s.kind == "D" and not guide.dungeon then guide.dungeon = k end
  end
end

function back.Order()
  local out, steps = {}, guide.steps
  for k, s in ipairs(steps) do
    if s.moved then out[#out + 1] = { s.p, back.Next(steps, k, "moved") or 0 } end
  end
  return out
end
function back.Keep()
  local moves = back.Order()
  Saved().order = #moves > 0 and { key = guide.key, version = guide.version, moves = moves } or nil
end
function back.Reorder(moves)
  local byPlan, before, run = {}, {}, {}
  for _, s in ipairs(guide.steps) do byPlan[s.p] = s end
  for _, m in ipairs(moves) do
    local s = type(m) == "table" and byPlan[m[1]]
    if s then s.moved = true end
  end
  for _, m in ipairs(moves) do
    local s = type(m) == "table" and byPlan[m[1]]
    if s and not s.placed then back.Front(before, s, byPlan[m[2]]) end
  end
  for _, s in ipairs(guide.steps) do
    s.placed = nil
    if not s.moved then back.Add(run, before[s], s) end
  end
  for _, m in ipairs(before[0] or {}) do run[#run + 1] = m end
  back.SetRun(run)
end
function back.Front(before, s, a)
  local key = (a and not a.moved) and a or 0
  s.placed = true
  before[key] = before[key] or {}
  table.insert(before[key], s)
end

function back.Held(id)
  local held, more = { [id] = true }, true
  while more do
    more = false
    for i, s in ipairs(guide.steps) do
      local q = s.kind == "P" and guide.state[i] ~= G.DONE and s.ids[1]
      if q and not held[q] and back.Needs(s, held) then held[q], more = true, true end
    end
  end
  return held
end
function back.Needs(s, quests)
  for _, p in ipairs(NeedsFirst(s)) do if quests[p] then return true end end
  return false
end

function back.WithGiver(s, steps)
  local own = ns.Geo.GiverKey(s)
  if not own then return false end
  local near = ns.Rules.guide.with_giver
  for _, t in ipairs(steps) do
    if ns.Geo.GiverKey(t) == own and t.inst == s.inst and t.wx and s.wx and Dist(t.wx, t.wy, s.wx, s.wy) <= near then return true end
  end
  return false
end
function back.After(s, t)
  if s.ids[1] ~= nil and s.ids[1] == t.ids[1] then return true end
  if s.kind == "P" and t.kind == "T" then
    for _, p in ipairs(NeedsFirst(s)) do if p == t.ids[1] then return true end end
  end
  if chore.TakesFrom(s, t) then return true end
  return s.maybe and back.WithGiver(s, { t }) or false
end

function back.Steps(id)
  local held, groups, quests, room, maybes = back.Held(id), {}, {}, back.MOST, {}
  for _, s in ipairs(guide.steps) do
    local q = s.kind ~= "D" and s.kind ~= "S" and s.ids[1]
    local st = q and (StepState(s))
    local mine = held[q] and (st == G.TODO or st == G.WAIT) or false
    local maybe = not mine and s.maybe and s.kind == "P" and st == G.TODO or false
    if mine and not groups[q] then groups[q] = {}; quests[#quests + 1] = q end
    if mine then table.insert(groups[q], s) end
    if maybe then maybes[#maybes + 1] = s end
    if s.moved and not mine and not maybe then room = room - 1 end
  end
  local own = groups[id] or {}
  for _, s in ipairs(maybes) do
    if back.WithGiver(s, own) then own[#own + 1] = s elseif s.moved then room = room - 1 end
  end
  local pick = {}
  local function Take(q)
    local list = q == id and own or groups[q]
    if #list == 0 or #list > room then return false end
    room = room - #list
    for _, s in ipairs(list) do pick[s] = true end
    return true
  end
  if not Take(id) then return {} end
  for _, q in ipairs(quests) do if q ~= id then Take(q) end end
  local out = {}
  for _, s in ipairs(guide.steps) do if pick[s] then out[#out + 1] = s end end
  return out
end

function back.Place(id)
  Saved().parked[guide.key][id] = nil
  local steps = back.Steps(id)
  if #steps == 0 then return false end
  local moving, route, first = {}, {}, false
  for _, s in ipairs(steps) do moving[s] = true end
  for _, s in ipairs(guide.steps) do
    local st = not moving[s] and (StepState(s))
    first = first or st == G.TODO
    if first and (st == G.TODO or st == G.WAIT) then route[#route + 1] = s end
  end
  local continent, px, py = ns.PlayerWorldPos()
  local fit = back.Fit(steps, route, px and { continent, px, py } or nil, back.After)
  local front, run = {}, {}
  for _, f in ipairs(fit) do
    local key = f.before or 0
    front[key] = front[key] or {}
    table.insert(front[key], f.step)
    f.step.moved = true
  end
  for _, s in ipairs(guide.steps) do
    if not moving[s] then back.Add(run, front[s], s) end
  end
  for _, m in ipairs(front[0] or {}) do run[#run + 1] = m end
  back.SetRun(run)
  back.Keep()
  return (route[1] ~= nil and fit[1].before == route[1]) and fit[1].step or nil
end

function back.Find(id)
  for i, s in ipairs(guide.steps) do if s.kind ~= "D" and s.kind ~= "S" and s.ids[1] == id then return i end end
end

function back.Unpark(id)
  local i = back.Find(id)
  if not i then Saved().parked[guide.key][id] = nil; return end
  local s = guide.steps[i]
  Event("unparked", i)
  local now = back.Place(id)
  if now and ns.Arbiter then ns.Arbiter.Pick(now) end
  ns.Print(string.format("%s is back in the guide %s.", s.name or ("quest " .. id),
    now and "as the next step, because you'd come back for it otherwise" or "where it adds the least walking"))
  Evaluate()
end

function ns.GuideUnpark(i)
  local s = guide and guide.steps[i]
  if s and s.kind ~= "D" and s.kind ~= "S" and Parked(s.ids[1]) then back.Unpark(s.ids[1]) end
end
ns.GuideBack = back

function back.Put(run)
  local tk, was = Saved().ticked, {}
  for _, t in ipairs(guide.steps) do was[t] = t.i end
  back.SetRun(run)
  if tk.version ~= guide.version then return end
  local moved = {}
  for t, i in pairs(was) do if tk[i] and t.i then moved[t.i] = true end end
  for k in pairs(tk) do if k ~= "version" then tk[k] = nil end end
  for k in pairs(moved) do tk[k] = true end
end
function ns.GuidePutChore(before, e)
  if not guide then return nil end
  local s = GuideStep(e, 0)
  s.p, s.own = nil, true
  local run, placed = {}, false
  for _, t in ipairs(guide.steps) do
    if t == before and not placed then run[#run + 1], placed = s, true end
    run[#run + 1] = t
  end
  if not placed then run[#run + 1] = s end
  back.Put(run)
  return s
end
function ns.GuideDropChore(i)
  local s = guide and guide.steps[i]
  if not (s and s.own) then return end
  local run = {}
  for k, t in ipairs(guide.steps) do if k ~= i then run[#run + 1] = t end end
  back.Put(run)
end
function back.Move(i, before)
  local s = guide and guide.steps[i]
  if not s or s == before then return end
  local run = {}
  for k, t in ipairs(guide.steps) do
    if k ~= i then
      if t == before then run[#run + 1] = s end
      run[#run + 1] = t
    end
  end
  if not before then run[#run + 1] = s end
  if s.p then s.moved = true end
  back.Put(run)
  if s.p then back.Keep() end
end
ns.GuideMoveStep = back.Move
function ns.GuidePlanStep(i)
  for k = i or 1, #(guide and guide.steps or {}) do
    local p = guide.steps[k].p
    if p then return p end
  end
  return 0
end
function handin.PlanCount()
  local n = 0
  for _, s in ipairs(guide and guide.steps or {}) do if s.p and s.p > n then n = s.p end end
  return n
end

function ns.GuideUnparkQuest(id)
  if not id then return ns.Print("Type /ioa guide unpark <quest ID> to put a parked quest back in the guide.") end
  if not guide then return ns.Print("No quest epic is running, so there's nothing to put a quest back in.") end
  local i = back.Find(id)
  if not i then return ns.Print(string.format("Quest %d isn't in the epic's plan.", id)) end
  if not Parked(id) then return ns.Print(string.format("%s isn't parked.", guide.steps[i].name or ("quest " .. id))) end
  back.Unpark(id)
end

function ns.GuideRelease(id)
  local i = guide and back.Find(id)
  if not i then return end
  Saved().parked[guide.key][id] = nil
  Event("unparked", i)
end
function ns.GuideUnskip(i)
  local s = guide and guide.steps[i]
  if not (s and s.key) then return end
  Saved().skippedErrands[s.key], Saved().skippedAt[s.key] = nil, nil
end
function ns.GuidePutBackCommand(kind, a, b)
  if not guide then return ns.Print("No quest epic is running, so there's nothing to put back.") end
  local row = ns.Drawer and ns.Drawer.Find(ns.GuideInfo(), kind, tonumber(a), tonumber(b))
  if not row then return ns.Print("That step isn't put off, parked or skipped any more, so there's nothing to put back.") end
  ns.Arbiter.PutBack(row)
end

function ns.GuideHolds(id)
  local held, names = back.Held(id), {}
  for _, s in ipairs(guide.steps) do
    if s.kind == "P" and s.ids[1] ~= id and held[s.ids[1]] then names[#names + 1] = s.name or s.text end
  end
  return names
end

function ns.GuideParked()
  local out, seen = {}, {}
  for _, s in ipairs(guide and guide.steps or {}) do
    local id = s.kind ~= "D" and s.kind ~= "S" and s.ids[1]
    local new = id and not seen[id] and Parked(id)
    if new then out[#out + 1] = { id = id, name = s.name or s.text, holds = ns.GuideHolds(id) } end
    if id then seen[id] = true end
  end
  return out
end

function ns.GuideStop()
  if not guide and tracks.e.target and tracks.e.target.pasted then
    ns.PastedClosed()
    return Clear(tracks.e, "You stopped the quest epic.")
  end
  if not guide then return ns.Print("No quest epic is running, so there's nothing to stop.") end
  Saved().stopped, Saved().stoppedAt = guide.version, time()
  local look = not guide.stopSaid and ns.UI.EpicLook(guide.key)
  guide = nil
  ns.epicDirty = true
  ns.EpicAccept(nil)
  ns.EpicHandIn(nil)
  ns.EpicHold(nil)
  if tracks.e.target and tracks.e.target.guided then Clear(tracks.e) end
  if ns.BeaconFollow then ns.BeaconFollow() end
  ns.Print("You closed the quest epic. Its plan and your progress are kept. Type /ioa guide start to pick it up again.")
  if look then ns.UI.SayStop(look) end
  Changed("state")
end

function ns.GuideStart()
  Saved().stopped = nil
  ns.GuideLoad(true)
  if not guide then ns.Print("The Index's table has no quest epic for this character. Start a quest epic on the page, then /reload.") end
end

local function OfferedNow(id, who)
  local sv = Saved()
  if not id or not sv.notOffered[id] then return false end
  sv.notOffered[id] = nil
  local name = nil
  for i, s in ipairs(guide.steps) do
    if s.kind == "P" and s.ids[1] == id then Event("offered", i); name = s.name; break end
  end
  ns.GuideToast(string.format("%s offers %s now", who or "the giver", name or "a quest the plan wanted"))
  return true
end
function ns.GuideOfferedNow(id)
  if guide and OfferedNow(id, Plain(Call(UnitName, "npc"))) then Evaluate() end
end

function ns.GuideCheckOffered(offered, key, who)
  if who == nil then key, who = ns.Geo.UnitKey("npc"), Plain(Call(UnitName, "npc")) end
  if not guide or not who then return end
  local level, sv, missed, back = Plain(Call(UnitLevel, "player")) or 1, Saved(), {}, false
  for id in pairs(offered) do back = OfferedNow(id, who) or back end
  for i, s in ipairs(guide.steps) do
    local id = s.kind == "P" and ns.Geo.IsGiver(s, key, who) and s.ids[1]
    if id and not offered[id] and not InLog(id) and not Turned(id) and not sv.notOffered[id] and (s.min or 0) <= level
       and Expected(s) then
      sv.notOffered[id] = time()
      Event("notOffered", i)
      missed[#missed + 1] = s.name or "a quest"
    end
  end
  if #missed == 0 then
    if back then Evaluate() end
    return
  end
  ns.Print(string.format("%s didn't offer %s, so the guide parks %s for now.", who, ns.AndList(missed),
                         #missed > 1 and "them" or "it"))
  Evaluate()
end

do
  local NO_WINDOW = 1.5
  local CLICK_SECONDS = 0.4
  local WINDOWS = { "MERCHANT_SHOW", "TRAINER_SHOW", "TAXIMAP_OPENED", "BANKFRAME_OPENED", "AUCTION_HOUSE_SHOW",
                    "PET_STABLE_SHOW", "GUILDBANKFRAME_OPENED", "MAIL_SHOW", "ITEM_TEXT_BEGIN", "PETITION_SHOW",
                    "TABARD_FRAME_OPENED", "GOSSIP_SHOW", "QUEST_GREETING", "QUEST_DETAIL", "QUEST_PROGRESS",
                    "QUEST_COMPLETE", "UI_ERROR_MESSAGE", "PLAYER_REGEN_DISABLED" }
  local talked = { n = 0, seen = 0, down = nil }
  ns.On(WINDOWS, function() talked.seen = talked.seen + 1 end)
  function ns.GuideTalked(unit)
    if not guide or IsShiftKeyDown() or InCombatLockdown() then return end
    if not Plain(Call(UnitExists, unit)) or Plain(Call(UnitIsPlayer, unit)) or Plain(Call(UnitCanAttack, "player", unit))
       or not Plain(Call(CheckInteractDistance, unit, 3)) then return end
    local key, who = ns.Geo.UnitKey(unit), Plain(Call(UnitName, unit))
    if not who then return end
    talked.n = talked.n + 1
    local n, seen = talked.n, talked.seen
    C_Timer.After(NO_WINDOW, function()
      if talked.n == n and talked.seen == seen then ns.GuideCheckOffered({}, key, who) end
    end)
  end
  if hooksecurefunc then
    pcall(hooksecurefunc, "InteractUnit", function(unit) ns.GuideTalked(unit or "target") end)
    pcall(hooksecurefunc, "TurnOrActionStart", function() talked.down = GetTime() end)
    pcall(hooksecurefunc, "TurnOrActionStop", function()
      local down = talked.down
      talked.down = nil
      if down and GetTime() - down <= CLICK_SECONDS then ns.GuideTalked("mouseover") end
    end)
  end
end

function ns.GuideToast(text)
  if not (guide or paste.Guide()) then return ns.Print(text) end
  Changed("toast", text)
end

function ns.GuideSkip(i)
  local s = guide and guide.steps[i]
  if not s or s.kind ~= "S" or not s.key then return end
  Saved().skippedErrands[s.key] = Plain(Call(UnitLevel, "player")) or 0
  if s.what == "camp" then Saved().skippedAt[s.key] = time() end
  ns.Arbiter.MarkAway("skip:" .. s.key, guide.cur == i)
  Event("skipped", i)
  ns.Print(string.format("You skipped %s.", s.text or "the errand"))
  Evaluate()
end
local errandsWait = false
ns.On({ "MERCHANT_CLOSED", "BAG_UPDATE_DELAYED", "UPDATE_INVENTORY_DURABILITY", "PLAYER_MONEY" }, function()
  if not guide then return end
  for i, s in ipairs(guide.steps) do
    if s.kind == "S" and guide.state[i] == G.TODO then
      errandsWait = true
      return ns.MarkChanged and ns.MarkChanged("status")
    end
  end
end)
function ns.StatusRead()
  if not errandsWait then return end
  errandsWait = false
  if guide then Evaluate() end
end

local guideWatch = CreateFrame("Frame")
local guideDirty, guideSince = false, 0
function ns.GuideLook() guideDirty = true end
ns.On({ "QUEST_ACCEPTED", "QUEST_TURNED_IN", "QUEST_REMOVED", "QUEST_LOG_UPDATE", "PLAYER_LEVEL_UP", "ZONE_CHANGED_NEW_AREA",
        "PLAYER_ENTERING_WORLD" }, function(event, login, reload)
  if event == "PLAYER_ENTERING_WORLD" and (login or reload) then
    return C_Timer.After(2, function() pcall(ns.GuideLoad) end)
  end
  guideDirty = true
end)
ns.On("BAG_UPDATE_DELAYED", function()
  if not guide then return end
  for i, s in ipairs(guide.steps) do
    if s.get and guide.state[i] == G.TODO then guideDirty = true; return end
  end
end)
ns.OnTick(guideWatch, "the epic's watch", nil, function(_, dt)
  guideSince = guideSince + dt
  if not guide or guideSince < (guideDirty and 0.3 or 2) then return end
  guideSince, guideDirty = 0, false
  Evaluate()
  if guide and guide.cur and guide.arrowOff ~= guide.cur and (ns.PlayerWorldPos()) ~= guide.pointedOn then PointArrow() end
end)


local EVENT_CODE = { done = 1, blocked = 2, notOffered = 3, parked = 4, unparked = 5, offered = 6, skipped = 7 }
local SKIP_KIND = { train = 1, bind = 2, flightpath = 3, sell = 4, repair = 5, restock = 6, camp = 7 }
local SKIP_THING = { water = 1, ammo = 2, ankh = 3, camp = 4 }
local SKIPS_MOST = 8
local function SkipValue(key)
  local what, rest = key:match("^(%a+):?(.*)$")
  if what == "camp" then
    local left = chore.SkipLeft(key)
    if left <= 0 then
      Saved().skippedErrands[key], Saved().skippedAt[key] = nil, nil
      return nil
    end
    return SKIP_KIND.camp, math.floor((chore.SKIP - left) / 60)
  end
  if what == "train" or what == "flightpath" then return SKIP_KIND[what], tonumber(rest) or 0 end
  if what == "bind" then return SKIP_KIND.bind, ns.NameHash and ns.NameHash(rest) or 0 end
  if what == "restock" then return SKIP_KIND.restock, SKIP_THING[rest] or 0 end
  return SKIP_KIND[what], 0
end
local UNOFFERED_MOST = 60
function ns.EncodeEpic()
  ns.epicDirty = false
  local w = ns.NewWriter()
  w:u8(20)
  local sv = Saved()
  if not ns.guideDecided then return nil end
  if not guide then
    w:u8(ns.guideOther and 4 or (sv.stopped and 2 or 0))
    w:var(sv.stopped or 0)
    return w.bytes
  end
  local lead = guide.cur and guide.steps[guide.cur]
  local chores, said = ns.EncodeChores(), ns.EncodeLead()
  if said and not chores then chores = { 0 } end
  w:u8(1 + (guide.handIn and lead and 2 or 0) + (chores and 4 or 0) + (sv.hiddenFor == guide.version and 8 or 0) + 16 + 32 + 64 + 128)
  w:var(guide.version)
  w:var(guide.plan or 0)
  local at = {}
  for k, s in ipairs(guide.steps) do if s.p then at[s.p] = k end end
  local onPlan = guide.planCur and guide.steps[guide.planCur]
  w:u16((lead and lead.extra and (onPlan and onPlan.p or 0)) or (lead and lead.own and ns.GuidePlanStep(guide.cur))
        or (lead and lead.p) or 0)
  if guide.handIn and lead then w:u24(lead.ids[1] or 0) end
  local from = handin.OnPlan()
  local anchor = from and guide.steps[from] and guide.steps[from].p or 1
  while from and guide.steps[from] and guide.steps[from].moved do from = from + 1 end
  if from and guide.steps[from] and guide.steps[from].p then anchor = guide.steps[from].p end
  local first = math.max(1, anchor - 20)
  local n = math.max(0, math.min(handin.PlanCount() - first + 1, 200))
  w:u16(first)
  w:u8(n)
  for i = first, first + n - 1, 2 do
    w:u8((guide.state[at[i]] or 0) + 16 * (i + 1 <= first + n - 1 and guide.state[at[i + 1]] or 0))
  end
  local parked, unoffered = {}, {}
  for id in pairs(sv.parked[guide.key] or {}) do parked[#parked + 1] = id end
  for id in pairs(sv.notOffered) do unoffered[#unoffered + 1] = id end
  local parkedPart = ns.NewWriter()
  parkedPart:u8(math.min(#parked, 20)); for i = 1, math.min(#parked, 20) do parkedPart:u24(parked[i]) end
  local moves, movesPart = back.Order(), ns.NewWriter()
  if #moves > 0 or chores then movesPart:u8(#moves) end
  for _, m in ipairs(moves) do movesPart:u16(m[1]); movesPart:u16(m[2]); movesPart:u8(guide.state[at[m[1]]] or 0) end
  table.sort(unoffered)
  local skips = {}
  for key, lv in pairs(sv.skippedErrands) do
    local kind, value = SkipValue(key)
    if kind and #skips < SKIPS_MOST then skips[#skips + 1] = { kind, value, lv } end
  end
  local room = ns.MAX_PAYLOAD - #w.bytes - #parkedPart.bytes - 2 - (1 + 4 * #skips) - 1 - #movesPart.bytes - #(chores or {})
    - #(said or {})
  local nu = 0
  for i = 1, math.min(#unoffered, UNOFFERED_MOST) do
    local size = i == 1 and 3 or ns.VarSize(unoffered[i] - unoffered[i - 1])
    if size > room then break end
    nu, room = i, room - size
  end
  local events = guide.events
  local ne = math.min(#events, math.floor(room / 5))
  w:u8(ne)
  for k = #events - ne + 1, #events do
    local e = events[k]
    w:u8(EVENT_CODE[e.kind] or 0); w:u16(e.step or 0); w:u16(math.min(65535, math.max(0, time() - e.at)))
  end
  for _, b in ipairs(parkedPart.bytes) do w.bytes[#w.bytes + 1] = b end
  w:u8(nu)
  if nu > 0 then w:u24(unoffered[1]) end
  for i = 2, nu do w:var(unoffered[i] - unoffered[i - 1]) end
  w:u8(#skips)
  for _, s in ipairs(skips) do w:u8(s[1]); w:u16(s[2] % 65536); w:u8(math.min(255, s[3])) end
  w:u8(math.floor(ns.GuideLevelPace() * 50 + 0.5))
  for _, b in ipairs(movesPart.bytes) do w.bytes[#w.bytes + 1] = b end
  for _, b in ipairs(chores or {}) do w.bytes[#w.bytes + 1] = b end
  for _, b in ipairs(said or {}) do w.bytes[#w.bytes + 1] = b end
  return w.bytes
end
function ns.EncodeLead()
  local w, d = ns.NewWriter(), guide and guide.decision
  local factor = play.Code()
  play.sent = factor
  local code = d and d.key and ns.Rules.Code(d.key) or 0
  local other = code > 0 and d.lostStep or nil
  local extra = other and other.extra and other.ids[1] or nil
  w:u8(code + (extra and 128 or 0))
  if code > 0 then
    w:u16(other and other.p or 0)
    w:u8(math.max(0, math.min(255, d.fill and tonumber(d.fill.n) or 0)))
    if extra then w:u24(extra) end
  end
  local off = {}
  for _, s in ipairs(guide and guide.steps or {}) do
    if s.p and ns.Arbiter.PutOffWhy(s) and #off < 16 then off[#off + 1] = s.p end
  end
  w:u8(#off)
  for _, p in ipairs(off) do w:u16(p) end
  local after = ns.NextAfter and ns.NextAfter(guide)
  local afterP = after and after.p or nil
  if factor ~= 20 then w:u8(factor) end
  if afterP then w:u16(afterP) end
  if code == 0 and #off == 0 and factor == 20 and not afterP then return nil end
  return w.bytes
end
ns.OnGuide(function() ns.epicDirty = true end)

local COMPLETED_EVERY = 90
local completed = ns.IdPager(21, COMPLETED_EVERY)
local function BuildCompleted()
  local ids = {}
  for _, id in ipairs(Call(C_QuestLog.GetAllCompletedQuestIDs) or {}) do
    if Plain(id) then ids[#ids + 1] = id end
  end
  if #ids == 0 then return false end
  table.sort(ids)
  completed.Offer(ids, table.concat(ids, ","), true)
  return true
end
completed.refill = BuildCompleted
ns.CompletedPending, ns.NextCompletedFrame = completed.Pending, completed.Next

ns.On({ "PLAYER_ENTERING_WORLD", "QUEST_TURNED_IN" }, function(event, login, reload)
  if event == "PLAYER_ENTERING_WORLD" and not (login or reload) then return end
  C_Timer.After(event == "QUEST_TURNED_IN" and 2 or 5, function()
    if not BuildCompleted() then C_Timer.After(10, BuildCompleted) end
  end)
end)


local DOOR_YARDS, NEAR_YARDS = 80, 100

local function PlanQuests()
  local ids, seen = {}, {}
  for _, s in ipairs(guide.steps) do
    if s.kind ~= "D" then
      for _, id in ipairs(s.ids) do
        if not seen[id] then seen[id] = true; ids[#ids + 1] = id end
      end
    end
  end
  return ids
end

function ns.GuideParty()
  if not guide then return nil end
  local units = ns.GroupUnits()
  if #units == 0 then return nil end
  local mine = {}
  for _, id in ipairs(PlanQuests()) do if InLog(id) then mine[#mine + 1] = id end end
  local members, missing = {}, {}
  for _, unit in ipairs(units) do
    local m = ns.MemberInfo(unit)
    local on = 0
    for _, id in ipairs(mine) do
      if ns.MemberOnQuest(unit, id) then on = on + 1 else missing[id] = true end
    end
    members[#members + 1] = { name = m.name, class = m.class, on = on, of = #mine }
  end
  local share = {}
  for _, id in ipairs(mine) do
    if missing[id] and Plain(Call(C_QuestLog.IsPushableQuest, id)) then share[#share + 1] = id end
  end
  return { members = members, share = share }
end

function ns.GuideShareNext()
  local party = ns.GuideParty()
  local id = party and party.share[1]
  if not id then return ns.Print("There's nothing from the epic to share. Your party has the quests you have, or those quests can't be shared.") end
  Call(C_QuestLog.SetSelectedQuest, id)
  Call(QuestLogPushQuest)
  ns.GuideToast("You shared " .. (Plain(Call(C_QuestLog.GetTitleForQuestID, id)) or ("quest " .. id)) .. ".")
end

function ns.GuideAtDoor()
  local s = guide and guide.cur and guide.steps[guide.cur]
  if not s or s.kind ~= "D" or not s.wx then return nil end
  local continent, px, py = ns.PlayerWorldPos()
  if continent ~= s.inst or not px or Dist(s.wx, s.wy, px, py) > DOOR_YARDS then return nil end
  local away, units = {}, {}
  for _, unit in ipairs(ns.GroupUnits()) do
    local north, west, _, inst = Call(UnitPosition, unit)
    north, west, inst = Plain(north), Plain(west), Plain(inst)
    if not north or inst ~= continent or Dist(north, west, px, py) > NEAR_YARDS then
      away[#away + 1] = Plain(UnitName(unit)) or "?"
      units[unit] = true
    end
  end
  return away, units
end


local BEACON_ART = "Interface\\AddOns\\IndexOfAzeroth\\Media\\beacon_"
local beacon = nil
local navBeacon = nil
local tracked = nil
local view = { switched = 0, CLOSER_BY = 0.9 }
function view.Settled() return GetTime() - view.switched > 0.15 end
local EPIC_BLUE, NAV_GOLD = GUIDE.e, GUIDE.go
local function Track(name) return C_SuperTrack and C_SuperTrack[name] end
local function Nav(name) return C_Navigation and C_Navigation[name] end

local function Near(map, x, y, m, px, py)
  return map == m and x ~= nil and y ~= nil and px ~= nil and py ~= nil and math.abs(x - px) < 0.0005 and math.abs(y - py) < 0.0005
end
local function OursAt(map, x, y)
  local pin = Saved().beaconPin
  return type(pin) == "table" and Near(map, x, y, pin.map, pin.x, pin.y)
end
local function PinNow()
  if not Plain(Call(C_Map.HasUserWaypoint)) then return nil end
  local point = Call(C_Map.GetUserWaypoint)
  local pos = point and point.position
  local map, x, y = point and Plain(point.uiMapID), pos and Plain(pos.x), pos and Plain(pos.y)
  return OursAt(map, x, y) and true or false, map, x, y
end
function ns.BeaconPin(map, x, y) return OursAt(map, x, y) end

local function BeaconSpot(s)
  local tries = {}
  if s.map then tries[#tries + 1] = s.map end
  local cx, cy, cont = ns.Geo.MapPos(s.inst, s.wx, s.wy)
  local info = cont and cx and Call(C_Map.GetMapInfoAtPosition, cont, cx, cy)
  if info and Plain(info.mapID) then tries[#tries + 1] = Plain(info.mapID) end
  if cont then tries[#tries + 1] = cont end
  for _, m in ipairs(tries) do
    local x, y = ns.Geo.MapPos(s.inst, s.wx, s.wy, m)
    x, y = Plain(x), Plain(y)
    if x and y and x >= 0 and x <= 1 and y >= 0 and y <= 1 and Plain(Call(C_Map.CanSetUserWaypointOnMap, m)) ~= false then
      return m, x, y
    end
  end
end

local function Waypoint(s, map, x, y)
  return { uiMapID = map, position = ns.Geo.Vector(x, y), z = s.z }
end
ns.BeaconWaypoint = Waypoint

local function LoopGuide()
  if ns.Ghost() then return nil end
  for _, kind in ipairs(LOOPS) do
    local tr = tracks[kind]
    local t = tr and tr.target
    if t and t.loop and t.continent then return t, GUIDE[t.look or kind], kind, t.look or kind end
  end
end

local function RideSpot(t, continent, px, py)
  local route = t and t.route
  if not route then return nil end
  if route:UnderWay(continent, px, py) then return false end
  local ride = t.wx and t.continent and route:NextRide()
  return ride and { inst = t.continent, wx = t.wx, wy = t.wy, name = RideText(ride), ride = true, master = ride.npc,
                    masterKey = ride.ni } or nil
end

local function EpicSpot(s, continent, px, py)
  local t = tracks.e and tracks.e.target
  local spot = t and (t.guided or t.pasted) and RideSpot(t, continent, px, py)
  if spot == false then return nil end
  return spot or s
end
ns.GuideBeaconSpot = function()
  local s = EpicNow()
  return s and EpicSpot(s, ns.PlayerWorldPos())
end

local function LoopSpot(lt, continent, px, py)
  local spot = RideSpot(lt, continent, px, py)
  if spot ~= nil then return spot or nil end
  local cx, cy = 0, 0
  for _, p in ipairs(lt.loop) do cx, cy = cx + p[1], cy + p[2] end
  return { inst = lt.continent, wx = cx / #lt.loop, wy = cy / #lt.loop, name = lt.name }
end

function ns.EpicRideWho()
  local t = tracks.e and tracks.e.target
  local route = t and (t.guided or t.pasted) and t.route
  local ride = route and route:NextRide()
  if not ride then return nil end
  if route:UnderWay(ns.PlayerWorldPos()) then return true end
  return ride.npc or true, ride.ni
end

local function Spots(continent, px, py)
  local list = {}
  local ghost = ns.Ghost()
  local s = not ghost and EpicNow()
  local epic = s and s.wx and EpicSpot(s, continent, px, py)
  if epic then list[#list + 1] = { epic, "epic" } end
  local t = ns.GuideTarget and ns.GuideTarget()
  if ghost then t = ns.CorpseRun() end
  if t and t.wx and t.continent and not t.wait then
    list[#list + 1] = { { inst = t.continent, wx = t.wx, wy = t.wy, map = t.map, name = t.name }, "nav" }
  end
  local lt = LoopGuide()
  local loop = lt and LoopSpot(lt, continent, px, py)
  if loop then list[#list + 1] = { loop, "loop" } end
  return list
end

local function Primary()
  local continent, px, py = ns.PlayerWorldPos()
  local list = Spots(continent, px, py)
  if #list == 0 then return nil end
  local function far(c)
    return (px and c[1].inst == continent) and Dist(c[1].wx, c[1].wy, px, py) or math.huge
  end
  local best, held = nil, nil
  for _, c in ipairs(list) do
    if not (continent and c[1].inst ~= continent) then
      if not best or far(c) < far(best) then best = c end
      if tracked and c[2] == tracked.kind then held = c end
    end
  end
  if not best then return nil end
  if held and far(best) > far(held) * view.CLOSER_BY then best = held end
  return best[1], best[2]
end
ns.BeaconPrimary = Primary

local SLOT_OF = { epic = "e", nav = "go" }
local function LoopSlot()
  for _, k in ipairs(LOOPS) do
    if tracks[k] and tracks[k].target and tracks[k].target.loop then return k end
  end
end
function ns.BeaconOwnerSlot()
  if not (tracked and BeaconOn()) then return nil end
  return SLOT_OF[tracked.kind] or (tracked.kind == "loop" and LoopSlot()) or nil
end
function ns.GuideDistances()
  local out, continent, px, py = {}, ns.PlayerWorldPos()
  for _, c in ipairs(Spots(continent, px, py)) do
    local slot = SLOT_OF[c[2]] or (c[2] == "loop" and LoopSlot())
    if slot then out[slot] = (px and c[1].inst == continent) and Dist(c[1].wx, c[1].wy, px, py) or math.huge end
  end
  return out
end
function ns.BeaconBreath() return 0.25 + 0.5 * (1 + math.sin(GetTime() * 2.5)) / 2 end

local function PointBeacon(take)
  local s, kind = Primary()
  local sv = Saved()
  local now, pm, px, py = PinNow()
  if not s then
    if now then Call(C_Map.ClearUserWaypoint) end
    sv.beaconPin, tracked = nil, nil
    return nil, "There is nothing to mark. No epic step, Navigation Guide or loop has a spot."
  end
  local map, x, y = BeaconSpot(s)
  if not map then return nil, "The addon has no map that holds the step's spot." end
  if now == false and not take and not Near(map, x, y, pm, px, py) then
    return nil, "Another map pin is set (yours or another addon's). The beacon waits until that pin is gone, or /ioa beacon puts the beacon in its place."
  end
  local ok, set = pcall(C_Map.SetUserWaypoint, Waypoint(s, map, x, y))
  if ok and set ~= false then
    sv.beaconPin = { map = map, x = x, y = y }
    if tracked and tracked.kind ~= kind then view.switched = GetTime() end
    tracked = { kind = kind, inst = s.inst, wx = s.wx, wy = s.wy }
  end
  Call(Track("SetSuperTrackedUserWaypoint"), true)
  return map, ok and tostring(set) or ("refused (" .. tostring(set) .. ")"), x, y
end

local RECLAIM_EVERY = 1
local reclaimedAt = nil
local function Reclaim()
  local ours = PinNow()
  if ours == false or ours and Plain(Call(Track("IsSuperTrackingUserWaypoint"))) then return end
  if Plain(Call(Track("IsSuperTrackingCorpse"))) then return end
  local now = GetTime()
  if reclaimedAt and now - reclaimedAt < RECLAIM_EVERY then return end
  reclaimedAt = now
  if ours then Call(Track("SetSuperTrackedUserWaypoint"), true) else PointBeacon() end
end

view.LIFT_MOST = 0.7
view.wayAt = nil

function view.WayPoints(s, continent)
  local pts = {}
  if continent ~= s.inst then return pts end
  local _, px, py = ns.PlayerWorldPos()
  local bends = StepBends(s, px, py)
  if bends and #bends > 0 then
    for _, b in ipairs(bends) do pts[#pts + 1] = { b[1], b[2], s.z and b.rise and s.z - b.rise } end
  elseif s.route then
    local last = nil
    for _, piece in ipairs(s.route) do if piece.inst == continent and #piece.path > 0 then last = piece end end
    for _, b in ipairs(last and last.path or {}) do pts[#pts + 1] = { b[1], b[2], b.z } end
  end
  pts[#pts + 1] = { s.wx, s.wy, s.z }
  return pts
end

function view.HeightOnWay(s, continent, px, py)
  if not (view.wayAt and view.wayAt.step == s) then view.wayAt = { step = s } end
  return ns.HeightAlong(view.WayPoints(s, continent), px, py, view.wayAt)
end

function view.HeightOfGround(s, px, py)
  local g = s.ground
  if type(g) ~= "table" or type(g.h) ~= "table" or not g.c or not g.s then return nil end
  local rows = math.floor(#g.h / g.c)
  local fi, fj = (g.n - px) / g.s, (g.w - py) / g.s
  local i0, j0 = math.floor(fi), math.floor(fj)
  if i0 < 0 or j0 < 0 or i0 + 1 >= rows or j0 + 1 >= g.c then return nil end
  local function H(i, j) local v = g.h[i * g.c + j + 1]; return type(v) == "number" and v or nil end
  local a, b, c, d = H(i0, j0), H(i0, j0 + 1), H(i0 + 1, j0), H(i0 + 1, j0 + 1)
  if not (a and b and c and d) then return a or b or c or d end
  local u, v = fi - i0, fj - j0
  return a * (1 - u) * (1 - v) + b * (1 - u) * v + c * u * (1 - v) + d * u * v
end

function view.HeightHere(s, continent, px, py)
  local z = view.HeightOnWay(s, continent, px, py)
  if z then return z, "the way" end
  z = continent == s.inst and view.HeightOfGround(s, px, py)
  if z then return z, "the ground" end
  return nil
end
ns.BeaconHeight = view.HeightHere

view.fov = { value = 90 }
ns.On("CVAR_UPDATE", function() view.fov.at = nil end)
function view.Focal()
  local fov, now = view.fov, GetTime()
  if not fov.at or now - fov.at >= 2 then
    fov.at, fov.value = now, tonumber(Plain(Call(C_CVar and C_CVar.GetCVar, "cameraFov"))) or 90
  end
  return UIParent:GetHeight() / 2 / (math.tan(math.rad(math.max(30, math.min(fov.value, 120))) / 2) * 9 / 16)
end

function ns.ViewAcross()
  return math.deg(2 * math.atan(UIParent:GetWidth() / 2 / view.Focal()))
end

function view.Project(u0, v0, d, dz, f)
  local pitch = -math.atan(v0 / f)
  local depth = d / math.sqrt(u0 * u0 + v0 * v0 + f * f)
  local z = depth * f + dz * math.sin(pitch)
  if z <= depth * f * 0.1 then return nil end
  return f * depth * u0 / z, f * (depth * v0 + dz * math.cos(pitch)) / z
end
ns.BeaconProject = view.Project

function view.NavOffset(nav)
  local x, y = nav:GetCenter()
  if not (x and y) then return nil end
  local scale = (nav:GetEffectiveScale() or 1) / (UIParent:GetEffectiveScale() or 1)
  return x * scale - UIParent:GetWidth() / 2, y * scale - UIParent:GetHeight() / 2
end

view.camWas = nil
view.leftSince = nil
view.lostAt = nil

function ns.BeaconsLost() return view.lostAt ~= nil and GetTime() - view.lostAt < 0.5 end

function view.Swinging()
  local left = Plain(Call(IsMouseButtonDown, "LeftButton")) and not Plain(Call(IsMouseButtonDown, "RightButton"))
  local foci = left and Call(GetMouseFoci)
  local top = type(foci) == "table" and foci[1]
  if not left or (top and top ~= WorldFrame) then view.leftSince = nil; return false end
  local now = GetTime()
  view.leftSince = view.leftSince or now
  return now - view.leftSince >= 0.2
end

function view.Camera(nav, continent, px, py)
  if not (tracked and px and tracked.inst == continent) then return nil end
  local facing = Plain(Call(GetPlayerFacing))
  local f = view.Focal()
  local u0, v0
  if nav and view.Settled() and not Plain(Call(Nav("WasClampedToScreen"))) and Plain(Call(Nav("HasValidScreenPosition"))) then
    u0, v0 = view.NavOffset(nav)
  end
  if u0 then
    local pitch = -math.atan(v0 / f)
    local toward = math.atan2(tracked.wy - py, tracked.wx - px)
    local yaw = toward - math.atan(-u0 * math.cos(pitch) / f)
    if facing then view.camWas = { off = yaw - facing, pitch = pitch } end
    view.lostAt = nil
    return { yaw = yaw, pitch = pitch, f = f }
  end
  view.lostAt = GetTime()
  if not (view.camWas and facing) then return nil end
  if view.Swinging() then view.camWas.lost, view.camWas.facing = true, facing; return nil end
  if view.camWas.lost then
    if math.abs((facing - view.camWas.facing + math.pi) % (2 * math.pi) - math.pi) < 0.02 then return nil end
    view.camWas.lost, view.camWas.off = nil, 0
  end
  view.lostAt = nil
  return { yaw = facing + view.camWas.off, pitch = view.camWas.pitch, f = f, rough = true }
end

function view.ScreenOf(cam, dn, dw, dz)
  local d = math.max(math.sqrt(dn * dn + dw * dw), 1)
  local turn, rise = math.atan2(dw, dn) - cam.yaw, math.atan2(dz or 0, d)
  local ahead = math.cos(rise) * math.cos(turn)
  local z = ahead * math.cos(cam.pitch) + math.sin(rise) * math.sin(cam.pitch)
  if z <= 0.05 then return nil end
  local x = -math.cos(rise) * math.sin(turn)
  local y = -ahead * math.sin(cam.pitch) + math.sin(rise) * math.cos(cam.pitch)
  return cam.f * x / z, cam.f * y / z
end
ns.BeaconCamera, ns.BeaconScreenOf = view.Camera, view.ScreenOf

ns.BeaconView = view

ns.BeaconTracked = function() return tracked end

function view.Lift(nav, d, dz)
  if not (nav and d and dz) then return 0, 0 end
  local u0, v0 = view.NavOffset(nav)
  if not u0 then return 0, 0 end
  local u, v = view.Project(u0, v0, math.max(d, 5), dz, view.Focal())
  if not u then return 0, 0 end
  local most = UIParent:GetHeight() * view.LIFT_MOST
  return math.max(-most, math.min(most, u - u0)), math.max(-most, math.min(most, v - v0))
end

function view.BeaconOffset(s, continent, px, py, nav)
  if not (s and s.z and px and nav and continent == s.inst) then return 0, 0 end
  local ground = view.HeightHere(s, continent, px, py)
  return view.Lift(nav, Dist(s.wx, s.wy, px, py), ground and s.z - ground)
end
ns.BeaconOffset = view.BeaconOffset

view.FADE_HALF, view.FADE_GONE = 1000, 3000
function view.DistanceFade(d, sameZone)
  if d >= view.FADE_GONE then return 0 end
  if sameZone then return 1 end
  if d <= view.FADE_HALF then return 1 - 0.5 * d / view.FADE_HALF end
  return 0.5 * (view.FADE_GONE - d) / (view.FADE_GONE - view.FADE_HALF)
end
ns.BeaconFade = view.DistanceFade

view.NEAR = { fade = 30, gone = 10 }
function view.NearFade(d)
  return d and math.max(0, math.min(1, (d - view.NEAR.gone) / (view.NEAR.fade - view.NEAR.gone))) or 1
end
ns.BeaconNearFade = view.NearFade
function view.GiveWay(v, away, dt) return math.max(0, math.min(1, (v or 1) + (away and -1 or 4) * dt)) end

function view.Prefer()
  local o = ns.Options and ns.Options().nav
  return o and o.declutter and (o.prefer == "arrows" and "arrows" or "beacons") or nil
end
function ns.BeaconCentred(x)
  if not x then return false end
  local cone = math.min((ns.Options and ns.Options().nav.cone) or 90, ns.ViewAcross())
  return math.abs(math.atan(x / view.Focal())) <= math.rad(cone) / 2
end
function view.ConeFade(self, dt, x)
  local arrows = view.Prefer() == "arrows"
  if arrows and x == nil then return self.cone or 1 end
  local gone = arrows and ns.BeaconCentred(x)
  self.cone = math.max(0, math.min(1, (self.cone or 1) + (gone and -4 or 4) * dt))
  return self.cone
end
view.inConeAt = nil
function view.Showed(alpha, x) if alpha > 0.05 and ns.BeaconCentred(x) then view.inConeAt = GetTime() end end
function ns.BeaconInCone() return view.inConeAt ~= nil and GetTime() - view.inConeAt < 0.3 end

view.zone = {}
function view.ZoneOf(m)
  for _ = 1, 6 do
    local info = m and Call(C_Map.GetMapInfo, m)
    local kind = info and Plain(info.mapType)
    if not kind or kind <= 3 then return m, kind end
    m = Plain(info.parentMapID)
  end
  return m
end
function view.SpotZone(s)
  local zone, kind = view.ZoneOf(s.map)
  if zone and not (kind and kind < 3) then return zone end
  local at = s.wx and ns.Geo.ZoneAt(s.inst or s.continent, s.wx, s.wy)
  return at and (view.ZoneOf(at)) or nil
end
local function InStepZone(s)
  local m, was = Plain(Call(C_Map.GetBestMapForUnit, "player")), view.zone
  if m ~= was.map or s.map ~= was.spotMap or s.wx ~= was.wx or s.wy ~= was.wy then
    local zone = view.SpotZone(s)
    was.map, was.spotMap, was.wx, was.wy, was.answer = m, s.map, s.wx, s.wy, nil
    if zone and m then was.answer = view.ZoneOf(m) == zone end
  end
  if was.answer ~= nil then return was.answer end
  return s.zone ~= nil and (Plain(Call(GetRealZoneText)) == s.zone or Plain(Call(GetZoneText)) == s.zone)
end
ns.BeaconInZone = InStepZone

function view.Say(fs, words)
  if fs.said ~= words then
    fs.said = words
    fs:SetText(words)
  end
end
function view.Yards(mark, d)
  local whole = d and math.floor(d)
  if whole ~= mark.yards then
    mark.yards = whole
    mark.dist:SetText(whole and string.format("%d yd", whole) or "")
  end
end

view.MARK_SIZE = 15
function view.Paint(f, color, art, tint, look)
  f.icon:SetTexture(BEACON_ART .. art)
  f.icon:SetDesaturated(tint ~= nil)
  f.icon:SetVertexColor(tint and tint[1] or 1, tint and tint[2] or 1, tint and tint[3] or 1)
  for _, line in ipairs(f.ring) do line:SetColorTexture(color[1], color[2], color[3], 1) end
  f.dist:SetTextColor(color[1], color[2], color[3])
  f.color = color
  if look or f.mark then ns.UI.Mark(f, look, view.MARK_SIZE) end
end

function view.Layer()
  if not view.layer then
    view.layer = CreateFrame("Frame", nil, UIParent)
    view.layer:SetAllPoints(UIParent)
    local function Strength() view.layer:SetAlpha(ns.Options().nav.beaconStrength / 100) end
    Strength()
    ns.OnOptions(Strength)
  end
  return view.layer
end

local function MakeMark(color, art)
  local f = CreateFrame("Frame", nil, view.Layer())
  f:SetSize(40, 40)
  f.icon = f:CreateTexture(nil, "ARTWORK")
  f.icon:SetAllPoints()
  f.ring = ns.UI.Circle(f, 32, 24, 1.5)
  f.dist = f:CreateFontString(nil, "OVERLAY", "GameFontNormal")
  f.dist:SetPoint("TOPLEFT", f, "TOPRIGHT", 8, -2)
  f.who = f:CreateFontString(nil, "OVERLAY", "GameFontHighlightSmall")
  f.who:SetPoint("TOPLEFT", f.dist, "BOTTOMLEFT", 0, -2)
  f.who:SetTextColor(CREAM[1], CREAM[2], CREAM[3])
  f.t = 0
  view.Paint(f, color, art)
  view.AddStop(f, "BOTTOMLEFT", f, "TOPRIGHT", -2, -2)
  return f
end

function view.AddStop(f, ...)
  local x = CreateFrame("Button", nil, f)
  x:SetSize(16, 16)
  x:SetPoint(...)
  x.text = x:CreateFontString(nil, "OVERLAY", "GameFontNormal")
  x.text:SetAllPoints()
  x.text:SetText("x")
  x.text:SetTextColor(0.8, 0.8, 0.8)
  x:SetScript("OnEnter", function(self)
    self.text:SetTextColor(unpack(ns.UI.C.gold))
    GameTooltip:SetOwner(self, "ANCHOR_RIGHT")
    GameTooltip:SetText("Stops the guide this beacon marks.")
    GameTooltip:Show()
  end)
  x:SetScript("OnLeave", function(self)
    self.text:SetTextColor(0.8, 0.8, 0.8)
    GameTooltip:Hide()
  end)
  x:SetScript("OnClick", function(self)
    local s = self.slot and ns.guideSlots and ns.guideSlots[self.slot]
    local stop = s and s.close:GetScript("OnClick")
    if stop then stop(s.close) end
  end)
  x:Hide()
  f.stop = x
end
function view.StopSlot(f, alpha, other)
  if not (tracked and tracked.kind == f.stopKind) then return nil end
  local k = ns.BeaconOwnerSlot and ns.BeaconOwnerSlot()
  if not (k and ns.GuideArrowGivenWay and ns.GuideArrowGivenWay(k)) or alpha <= 0.05 then return nil end
  if other and (other:GetAlpha() or 0) > 0.05 then return nil end
  return k
end
function view.StopOnBeacon(f, alpha, other)
  local x = f.stop
  local k = view.StopSlot(f, alpha or f:GetAlpha() or 0, other)
  if x.slot and x.slot ~= k then
    local s = ns.guideSlots[x.slot]
    if s and s.onBeacon == f then s.onBeacon = nil; s.close:Show() end
  end
  x.slot = k
  x:SetShown(k ~= nil)
  local s = k and ns.guideSlots[k]
  if s then s.onBeacon = f; s.close:Hide() end
end
function view.StopsOff()
  for _, f in ipairs({ beacon, navBeacon, view.loopMark, ns.bracketsFrame and ns.bracketsFrame.span }) do
    if f and f.stop then view.StopOnBeacon(f, 0) end
  end
end

view.PLATE = { yards = 3, edge = 0.12, most = 80, range = 45, every = 0.2, keep = 9, settle = 5, moved = 0.5, per = 6,
               learnt = 20, reach = 15, known = 300, ask = 0.5 }
view.sightings, view.learnt, view.learntAt = {}, {}, 0

function view.FrameOffset(f)
  local x, y = Call(f.GetCenter, f)
  x, y = Plain(x), Plain(y)
  if not (x and y) then return nil end
  local scale = (Plain(Call(f.GetEffectiveScale, f)) or 1) / (UIParent:GetEffectiveScale() or 1)
  return x * scale - UIParent:GetWidth() / 2, y * scale - UIParent:GetHeight() / 2
end

function view.PlateRise(u0, v0, u1, v1, d)
  local P, f = view.PLATE, view.Focal()
  if math.abs(u1) > UIParent:GetWidth() * (0.5 - P.edge) or math.abs(v1) > UIParent:GetHeight() * (0.5 - P.edge) then return nil end
  d = math.max(d, 5)
  local pitch = -math.atan(v0 / f)
  local depth = d / math.sqrt(u0 * u0 + v0 * v0 + f * f)
  local dz = f * depth * (v1 - v0) / (f * math.cos(pitch) - v1 * math.sin(pitch))
  if math.abs(dz) > P.most then return nil end
  local u = view.Project(u0, v0, d, dz, f)
  if not u or math.abs(u - u1) > f * P.yards / (depth * f + dz * math.sin(pitch)) then return nil end
  return dz
end

function view.PlateOf(name, nav, d, key)
  if not (name and nav and d and d <= view.PLATE.range and ns.PlateUnits) then return nil end
  local u0, v0 = view.NavOffset(nav)
  if not u0 then return nil end
  for unit in pairs(ns.PlateUnits()) do
    local plate = ns.Geo.IsOne(ns.Geo.UnitKey(unit), Plain(Call(UnitName, unit)), key, name) and not Plain(Call(UnitIsDead, unit))
      and Call(C_NamePlate and C_NamePlate.GetNamePlateForUnit, unit)
    local u1, v1 = nil, nil
    if plate then u1, v1 = view.FrameOffset(plate) end
    local dz = u1 and view.PlateRise(u0, v0, u1, v1, d)
    if dz then return plate, u1, dz, unit end
  end
end

function view.Learn(name, unit, spot, zYou, dz)
  if not (zYou and dz) or Plain(Call(IsFalling)) or Plain(Call(IsSwimming)) or Plain(Call(UnitOnTaxi, "player")) then return end
  local P, inst = view.PLATE, spot.inst or spot.continent
  local wx, wy = math.floor(spot.wx + 0.5), math.floor(spot.wy + 0.5)
  local seen = nil
  for _, h in ipairs(view.sightings) do
    if h.name == name and h.inst == inst and h.wx == wx and h.wy == wy then seen = h; break end
  end
  if not seen then
    seen = { name = name, inst = inst, wx = wx, wy = wy, samples = {} }
    table.insert(view.sightings, seen)
    if #view.sightings > P.learnt then table.remove(view.sightings, 1) end
  end
  local s = seen.samples
  s[#s + 1] = zYou + dz
  if #s > P.keep then table.remove(s, 1) end
  if not seen.npc then seen.npc = select(4, ns.Geo.Creature(Plain(Call(UnitGUID, unit)))) end
  if #s < P.settle then return end
  local sorted = {}
  for i, z in ipairs(s) do sorted[i] = z end
  table.sort(sorted)
  local mid = sorted[math.floor(#sorted / 2) + 1]
  if seen.z and math.abs(mid - seen.z) < P.moved then return end
  seen.z, seen.n = mid, #s
  view.Remember(seen)
  local list = view.learnt
  for i, h in ipairs(list) do if h == seen then table.remove(list, i); break end end
  list[#list + 1] = seen
  if #list > P.learnt then table.remove(list, 1) end
  view.learntAt = math.max(0, #list - P.per)
  if ns.MarkChanged then ns.MarkChanged("heights") end
end

function ns.EncodeHeights()
  local list = view.learnt
  if #list == 0 then return nil end
  local w = ns.NewWriter()
  w:u8(27)
  local n = math.min(view.PLATE.per, #list)
  w:u8(n)
  for i = 1, n do
    local h = list[(view.learntAt + i - 1) % #list + 1]
    w:str(h.name, 40); w:u24(h.npc or 0); w:u16(h.inst); w:i16(h.wx); w:i16(h.wy); w:i16(h.z * 10); w:u8(h.n)
  end
  view.learntAt = (view.learntAt + n) % #list
  return w.bytes
end

function view.StepNpc(s)
  if s.ride then return s.master end
  if s.kind == "P" or s.kind == "T" or s.kind == "S" then return s.npc end
end
function view.StepKey(s)
  if s.ride then return s.masterKey end
  if s.kind == "P" or s.kind == "T" then return ns.Geo.GiverKey(s) end
end

function view.SeePlate(self, npc, nav, d, spot, px, py, yours, walker, key)
  local plate, u1, dz, unit = view.PlateOf(npc, nav, d, key)
  self.plate, self.plateX, self.plateAway = plate, u1, nil
  if not plate and walker then
    self.plate, self.plateX = view.WalkerPlate(walker, key)
    self.plateAway = self.plate and true or nil
    return
  end
  if plate and (not self.sampled or GetTime() - self.sampled >= view.PLATE.every) then
    self.sampled = GetTime()
    view.Learn(npc, unit, spot, yours(spot, px, py), dz)
  end
end

function view.Walker(s)
  local npc = s and s.walks and s.loop and view.StepNpc(s)
  return npc or nil
end

function view.WalkNear(s, continent, px, py)
  if not (px and continent == s.inst and s.loop) then return nil end
  local best = nil
  for k = 1, #s.loop - 1 do
    local a, b = s.loop[k], s.loop[k + 1]
    local _, _, _, off = NearestOnSegment(a[1], a[2], b[1], b[2], px, py)
    if not best or off < best then best = off end
  end
  return best
end

function view.WalkerPlate(name, key)
  if not (name and ns.PlateUnits) then return nil end
  local units = Plain(Call(ns.PlateUnits))
  if type(units) ~= "table" then return nil end
  local w, h, edge = UIParent:GetWidth(), UIParent:GetHeight(), view.PLATE.edge
  for unit in pairs(units) do
    local plate = ns.Geo.IsOne(ns.Geo.UnitKey(unit), Plain(Call(UnitName, unit)), key, name) and not Plain(Call(UnitIsDead, unit))
      and Plain(Call(C_NamePlate and C_NamePlate.GetNamePlateForUnit, unit))
    local ok, u1, v1 = false, nil, nil
    if plate then ok, u1, v1 = pcall(view.FrameOffset, plate) end
    u1, v1 = ok and Plain(u1), ok and Plain(v1)
    if u1 and v1 and math.abs(u1) <= w * (0.5 - edge) and math.abs(v1) <= h * (0.5 - edge) then return plate, u1 end
  end
  return nil
end

function view.Remember(seen)
  if type(IndexOfAzerothDB) ~= "table" then return end
  if view.Known(seen.name, { inst = seen.inst, wx = seen.wx, wy = seen.wy }) then return end
  local list = type(IndexOfAzerothDB.platesLearnt) == "table" and IndexOfAzerothDB.platesLearnt or {}
  IndexOfAzerothDB.platesLearnt = list
  list[#list + 1] = { name = seen.name, inst = seen.inst, wx = seen.wx, wy = seen.wy }
  if #list > view.PLATE.known then table.remove(list, 1) end
end

function view.Known(name, spot)
  local list = type(IndexOfAzerothDB) == "table" and IndexOfAzerothDB.platesLearnt
  if type(list) ~= "table" then return false end
  local inst, reach = spot.inst or spot.continent, view.PLATE.reach
  for _, h in ipairs(list) do
    if h.name == name and h.inst == inst and Dist(h.wx, h.wy, spot.wx, spot.wy) <= reach then return true end
  end
  return false
end

function view.AskPlates(self, npc, d, spot, px, py, yours, walker)
  local now = GetTime()
  if self.askedAt and now - self.askedAt < 0.2 then return end
  self.askedAt = now
  local asks = npc and d and d <= view.PLATE.range and (walker or yours(spot, px, py) and not view.Known(npc, spot))
  self.platesAsked = asks and now or nil
end
function ns.FriendPlatesWanted()
  for _, f in ipairs({ beacon, navBeacon }) do
    if f and f:IsShown() and f.platesAsked and GetTime() - f.platesAsked < view.PLATE.ask then return true end
  end
  return false
end

function view.StepHeight(s, px, py)
  if not s.guess then return nil end
  local bends = StepBends(s, px, py)
  if not (bends and #bends > 1) then return nil end
  local pts = {}
  for i, b in ipairs(bends) do pts[i] = { b[1], b[2], s.z and b.rise and s.z - b.rise } end
  if not (view.alongBends and view.alongBends.of == bends) then view.alongBends = { of = bends } end
  return ns.HeightAlong(pts, px, py, view.alongBends)
end
function view.LineHeight(t, px, py)
  local rise = t.top and ns.RiseAlong(t, px, py)
  return rise and t.top - rise
end

function view.Anchor(self, nav, side, lift)
  local on = self.plate or nav
  if self.onNav == on and self.atSide == side and self.atLift == lift then return end
  self:ClearAllPoints()
  if self.plate and not pcall(self.SetPoint, self, "BOTTOM", self.plate, "TOP", 0, 2) then
    self.plate, self.plateX, on = nil, nil, nav
  end
  if on == nav then self:SetPoint("CENTER", nav, "CENTER", side, lift) end
  self.onNav, self.atSide, self.atLift = on, side, lift
end

local function HoldMark(self, dt)
  if not self.held then
    local x, y = self:GetCenter()
    self.held = true
    self:ClearAllPoints()
    if x and y then self:SetPoint("CENTER", UIParent, "BOTTOMLEFT", x, y) else self.faded = 0 end
  end
  self.faded = math.max(0, (self.faded or 1) - dt * 2)
  return self.faded
end

function view.MarkOn(self, dt, kind, spot, who, npc, key)
  if not spot then self:SetAlpha(0); return end
  if not (tracked and tracked.kind == kind) then
    self.held, self.faded = nil, nil
    self:SetAlpha(0); return
  end
  self.pinAge = (self.pinAge or 1) + dt
  if self.pinAge >= 0.1 then
    self.pinAge = 0
    self.pinOurs = PinNow() and Plain(Call(Track("IsSuperTrackingUserWaypoint"))) and true or false
  end
  if not self.pinOurs then self.held, self.faded = nil, nil; self:SetAlpha(0); return end
  local nav = Call(Nav("GetFrame"))
  local placed = nav and view.Settled() and not Plain(Call(Nav("WasClampedToScreen"))) and Plain(Call(Nav("HasValidScreenPosition")))
  self.hereAge = (self.hereAge or 1) + dt
  if self.hereAge >= 1 / 30 then
    self.hereAge = 0
    local continent, px, py = ns.PlayerWorldPos()
    self.d = px and continent == (spot.continent or spot.inst) and not Plain(Call(IsInInstance)) and Dist(spot.wx, spot.wy, px, py) or nil
    local near = (spot.under and not Plain(Call(IsIndoors))) and 1 or view.NearFade(self.d)
    self.far = self.d and view.DistanceFade(self.d, InStepZone(spot)) * near or 0
    self.side, self.lift, self.plate = 0, 0, nil
    view.AskPlates(self, npc, self.d, spot, px, py, view.LineHeight)
    if placed and self.d then
      self.side, self.lift = view.Lift(nav, self.d, ns.RiseAlong(spot, px, py))
      view.SeePlate(self, npc, nav, self.d, spot, px, py, view.LineHeight, nil, key)
    end
  end
  if not self.d then self:SetAlpha(0); return end
  local x = nil
  if placed then x = view.NavOffset(nav) end
  if x then x = self.plateX or x + self.side end
  local seen = self.far * view.ConeFade(self, dt, x)
  if x then
    self.held, self.faded = nil, 1
    view.Anchor(self, nav, self.side, self.lift)
    self:SetAlpha(seen)
    view.Showed(seen, x)
  else
    self.onNav = nil
    self:SetAlpha(HoldMark(self, dt) * seen)
  end
  local breath = ns.BeaconBreath()
  for _, line in ipairs(self.ring) do line:SetAlpha(breath) end
  view.Yards(self, self.d)
  view.Say(self.who, who or spot.name or "")
end

local function NavBeaconUpdate(self, dt)
  self.t = self.t + dt
  if not BeaconOn() then self:SetAlpha(0); return end
  self.lookAge = (self.lookAge or 1) + dt
  if self.lookAge >= 0.25 then
    self.lookAge = 0
    local s, kind = Primary()
    if s and (not tracked or tracked.kind ~= kind or tracked.wx ~= s.wx or tracked.wy ~= s.wy) or not s and tracked then
      PointBeacon()
    elseif tracked then
      Reclaim()
    end
  end
  local t = ns.GuideTarget and ns.GuideTarget()
  local look = ns.NavLook(t)
  if look ~= self.look then
    self.look = look
    view.Paint(self, GUIDE[look], view.NAV_ART[look], nil, look)
  end
  local ride = t and not t.wait and t.route and t.route:NextRide() or nil
  if ride ~= self.rideFor then self.rideFor, self.rideWords = ride, ride and RideText(ride, t.route.name) end
  view.MarkOn(self, dt, "nav", t and t.wx and not t.wait and t or nil, self.rideWords, t and ns.GuideNpc and ns.GuideNpc(t))
end

view.LOOP_ART = LOOKS.art
view.NAV_ART = { go = "guide", corpse = "corpse", npc = "npc" }
local function LoopMarkUpdate(self, dt)
  self.t = self.t + dt
  if not BeaconOn() then self:SetAlpha(0); return end
  self.spotAge = (self.spotAge or 1) + dt
  if self.spotAge >= 0.1 then
    self.spotAge = 0
    local lt, colour, _, look = LoopGuide()
    local spot = lt and LoopSpot(lt, ns.PlayerWorldPos())
    self.spot = spot and spot.ride and spot or nil
    if look and look ~= self.look then
      self.look = look
      view.Paint(self, colour, LOOKS.art[look], nil, look)
    end
  end
  view.MarkOn(self, dt, "loop", self.spot, nil, self.spot and self.spot.master,
              self.spot and self.spot.masterKey)
end

view.BRACKET_ART = "Interface\\AddOns\\IndexOfAzeroth\\Media\\bracket_"
view.BRACKET_USED = 218 / 256
view.BRACKET_W, view.BRACKET_H = 48, 56
view.brackets = nil

function view.LoopEdges(loop, px, py)
  local cn, cw = 0, 0
  for _, p in ipairs(loop) do cn, cw = cn + p[1], cw + p[2] end
  cn, cw = cn / #loop, cw / #loop
  local mid = math.atan2(cw - py, cn - px)
  local left, right, most, least
  for _, p in ipairs(loop) do
    local a = (math.atan2(p[2] - py, p[1] - px) - mid + math.pi) % (2 * math.pi) - math.pi
    if not most or a > most then most, left = a, p end
    if not least or a < least then least, right = a, p end
  end
  return left, right
end
ns.BeaconLoopEdges = view.LoopEdges

view.OFF_SCREEN = 100000
function view.LoopBox(cam, loop, px, py)
  if not loop or #loop == 0 then return nil end
  local left, right = view.LoopEdges(loop, px, py)
  local xl, yl = view.ScreenOf(cam, left[1] - px, left[2] - py, 0)
  local xr, yr = view.ScreenOf(cam, right[1] - px, right[2] - py, 0)
  if not xl and not xr then return nil end
  local hi, lo = math.max(yl or yr, yr or yl), math.min(yl or yr, yr or yl)
  return xl or -view.OFF_SCREEN, hi + view.BRACKET_H / 2, xr or view.OFF_SCREEN, lo - view.BRACKET_H / 2, not xl, not xr
end
ns.BeaconLoopBox = view.LoopBox

function view.MakeBracket(side)
  local f = CreateFrame("Frame", nil, view.Layer())
  f:SetSize(view.BRACKET_W, view.BRACKET_H)
  f.glow = f:CreateTexture(nil, "BACKGROUND")
  f.glow:SetPoint("TOPLEFT", -4, 4)
  f.glow:SetPoint("BOTTOMRIGHT", 4, -4)
  f.glow:SetTexture(view.BRACKET_ART .. side)
  f.glow:SetTexCoord(0, view.BRACKET_USED, 0, 1)
  f.glow:SetBlendMode("ADD")
  f.glow:SetVertexColor(CREAM[1], CREAM[2], CREAM[3], 0.16)
  f.tex = f:CreateTexture(nil, "ARTWORK")
  f.tex:SetAllPoints()
  f.tex:SetTexture(view.BRACKET_ART .. side)
  f.tex:SetTexCoord(0, view.BRACKET_USED, 0, 1)
  f:SetAlpha(0)
  return f
end

view.SPAN = { glow = 0.22, reach = 0.4 }
view.SPAN_ART = "Interface\\AddOns\\IndexOfAzeroth\\Media\\span_glow"
function view.SpanGlow(f, from)
  local t = f:CreateTexture(nil, "BACKGROUND")
  t:SetPoint("TOP"); t:SetPoint("BOTTOM"); t:SetPoint(from)
  t:SetTexture(view.SPAN_ART)
  if from == "RIGHT" then t:SetTexCoord(1, 0, 0, 1) end
  t:SetBlendMode("ADD")
  t.from = from
  return t
end
function view.MakeSpan()
  local f = CreateFrame("Frame", nil, view.Layer())
  f.glows = { view.SpanGlow(f, "LEFT"), view.SpanGlow(f, "RIGHT") }
  f.dist = f:CreateFontString(nil, "OVERLAY", "GameFontNormal")
  f.dist:SetPoint("TOP", f, "BOTTOM", 0, -4)
  f.who = f:CreateFontString(nil, "OVERLAY", "GameFontHighlightSmall")
  f.who:SetPoint("TOP", f.dist, "BOTTOM", 0, -2)
  f.who:SetTextColor(CREAM[1], CREAM[2], CREAM[3])
  view.AddStop(f, "LEFT", f.dist, "RIGHT", 4, 0)
  f:SetAlpha(0)
  return f
end
function view.PaintSpan(f, c)
  if f.color == c then return end
  f.color = c
  for _, t in ipairs(f.glows) do t:SetVertexColor(c[1], c[2], c[3], view.SPAN.glow) end
  f.dist:SetTextColor(c[1], c[2], c[3])
end
function view.PlaceSpan(f, l, top, r, bottom)
  f:ClearAllPoints()
  f:SetPoint("TOPLEFT", UIParent, "CENTER", l, top)
  f:SetPoint("BOTTOMRIGHT", UIParent, "CENTER", r, bottom)
  for _, t in ipairs(f.glows) do t:SetWidth(math.max(1, (r - l) * view.SPAN.reach)) end
end

view.LOOP_NEAR = { fade = 100, gone = 50 }
function view.InLoop(loop, x, y)
  local inside, n = false, #loop
  for i = 1, n do
    local a, b = loop[i], loop[i == 1 and n or i - 1]
    if (a[2] > y) ~= (b[2] > y) and x < (b[1] - a[1]) * (y - a[2]) / (b[2] - a[2]) + a[1] then inside = not inside end
  end
  return inside
end
function view.LoopFade(d, inside)
  if inside then return 0 end
  if not d then return 1 end
  local n = view.LOOP_NEAR
  local f = math.max(0, math.min(1, (d - n.gone) / (n.fade - n.gone)))
  return f * f
end

function view.BracketsUpdate(self, dt)
  local left, right = self.left, self.right
  local t, colour = LoopGuide()
  if t and t.route and t.route:NextRide() then t = nil end
  if not t or not BeaconOn() or not ns.NavOn("brackets")
     or (not (tracked and tracked.kind == "loop") and (self.faded or 1) <= 0) then
    left:SetAlpha(0); right:SetAlpha(0); self.span:SetAlpha(0); view.StopOnBeacon(self.span, 0); return
  end
  local continent, px, py = ns.PlayerWorldPos()
  if not px or continent ~= t.continent or Plain(Call(IsInInstance)) then
    left:SetAlpha(0); right:SetAlpha(0); self.span:SetAlpha(0); view.StopOnBeacon(self.span, 0); return
  end
  left.tex:SetVertexColor(colour[1], colour[2], colour[3])
  right.tex:SetVertexColor(colour[1], colour[2], colour[3])
  view.PaintSpan(self.span, colour)
  local cam = tracked and tracked.kind == "loop" and view.Camera(Call(Nav("GetFrame")), continent, px, py)
  local l, top, r, bottom, leftGone, rightGone
  if cam and not cam.rough then l, top, r, bottom, leftGone, rightGone = view.LoopBox(cam, t.loop, px, py) end
  local _, _, near = ns.NearestOnLoop(t, px, py)
  local near_fade = view.LoopFade(near, view.InLoop(t.loop, px, py))
  local w = UIParent:GetWidth() / 2
  local sl, sr = l and math.max(l, -w), r and math.min(r, w)
  local mid = l and (math.max(math.min(l, w), -w) + math.max(math.min(r, w), -w)) / 2
  local seen = view.DistanceFade(near or 0, false) * near_fade * view.ConeFade(self, dt, mid)
  if l then
    self.faded, self.leftGone, self.rightGone = 1, leftGone, rightGone
    left:ClearAllPoints(); left:SetPoint("TOPLEFT", UIParent, "CENTER", l, top)
    right:ClearAllPoints(); right:SetPoint("BOTTOMRIGHT", UIParent, "CENTER", r, bottom)
    view.PlaceSpan(self.span, math.min(sl, sr), top, math.max(sl, sr), bottom)
    view.Showed(seen, mid)
  else
    self.faded = math.max(0, (self.faded or 1) - dt * 2)
  end
  view.Yards(self.span, near)
  view.Say(self.span.who, t.name or "")
  local a = self.faded * seen
  left:SetAlpha(self.leftGone and 0 or a); right:SetAlpha(self.rightGone and 0 or a); self.span:SetAlpha(a)
  view.StopOnBeacon(self.span, a, view.loopMark)
end

local function BeaconFrame()
  if not view.brackets then
    view.brackets = CreateFrame("Frame", nil, view.Layer())
    view.brackets.left, view.brackets.right = view.MakeBracket("left"), view.MakeBracket("right")
    view.brackets.span = view.MakeSpan()
    ns.OnTick(view.brackets, "the loop's brackets", nil, view.BracketsUpdate)
    view.brackets.span.stopKind = "loop"
    ns.bracketsFrame = view.brackets
  end
  view.brackets:Show()
  if not navBeacon then
    navBeacon = MakeMark(NAV_GOLD, "guide")
    navBeacon:SetAlpha(0)
    navBeacon.stopKind = "nav"
    ns.OnTick(navBeacon, "the Navigation Guide's beacon", nil, function(self, dt) NavBeaconUpdate(self, dt); view.StopOnBeacon(self) end)
    ns.navBeaconFrame = navBeacon
  end
  navBeacon:Show()
  if not view.loopMark then
    view.loopMark = MakeMark(GUIDE.g, "grind")
    view.loopMark:SetAlpha(0)
    view.loopMark.stopKind = "loop"
    ns.OnTick(view.loopMark, "the loop's beacon", nil, function(self, dt) LoopMarkUpdate(self, dt); view.StopOnBeacon(self) end)
    ns.loopBeaconFrame = view.loopMark
  end
  view.loopMark:Show()
  if not beacon then
    beacon = MakeMark(EPIC_BLUE, "epic")
    beacon.stopKind = "epic"
    ns.OnTick(beacon, "the epic's beacon", nil, function(self, dt) view.EpicBeaconUpdate(self, dt); view.StopOnBeacon(self) end)
    function view.EpicBeaconUpdate(self, dt)
      self.t = self.t + dt
      local s = EpicNow()
      if not s or ns.Ghost() then self:SetAlpha(0); return end
      local own = not tracked or tracked.kind == "epic"
      if not own then self.held, self.faded = nil, nil; self:SetAlpha(0); return end
      self.pinAge = (self.pinAge or 1) + dt
      if self.pinAge >= 0.1 then
        self.pinAge = 0
        self.pinOurs = PinNow() and Plain(Call(Track("IsSuperTrackingUserWaypoint"))) and true or false
      end
      local nav = Call(Nav("GetFrame"))
      if not nav or not self.pinOurs then self:SetAlpha(0); return end
      if Plain(Call(IsInInstance)) then self:SetAlpha(0); return end
      local continent, px, py = ns.PlayerWorldPos()
      s = EpicSpot(s, continent, px, py)
      if not s then self:SetAlpha(0); return end
      local pinned = Plain(Call(Nav("WasClampedToScreen"))) or not Plain(Call(Nav("HasValidScreenPosition")))
        or not view.Settled()
      local d = continent == s.inst and px and Dist(s.wx, s.wy, px, py)
      local walker = view.Walker(s)
      view.AskPlates(self, view.StepNpc(s), (walker and view.WalkNear(s, continent, px, py) or d) or nil, s, px, py,
        view.StepHeight, walker)
      if walker and pinned then
        self.walkAge = (self.walkAge or 1) + dt
        if self.walkAge >= 1 / 30 then
          self.walkAge = 0
          self.plate, self.plateX = view.WalkerPlate(walker, view.StepKey(s))
          self.plateAway = self.plate and true or nil
        end
        if self.plate then pinned = false end
      end
      local x = nil
      if not pinned then
        self.liftAge = (self.liftAge or 1) + dt
        if self.liftAge >= 1 / 30 or not self.side then
          self.liftAge = 0
          self.side, self.lift = view.BeaconOffset(s, continent, px, py, nav)
          view.SeePlate(self, view.StepNpc(s), nav, d or nil, s, px, py, view.StepHeight, walker, view.StepKey(s))
        end
        local u0 = view.NavOffset(nav)
        x = self.plateX or (u0 and u0 + self.side)
      end
      if self.plateAway and not walker then self.plate, self.plateX, self.plateAway = nil, nil, nil end
      local away = self.plateAway and self.plate and true or false
      if away then d = nil end
      local A = ns.Arbiter
      local area = not away and A.HasArea(s)
      self.there = view.GiveWay(self.there, area and d and A.InArea(s, px, py), dt)
      local near = (s.under and not Plain(Call(IsIndoors))) and 1 or area and self.there or view.NearFade(d)
      self.camp = view.GiveWay(self.camp, ns.GuideAtLoop(), dt)
      local seen = (d and view.DistanceFade(d, InStepZone(s)) * near or 1) * view.ConeFade(self, dt, x) * self.camp
      if pinned then
        if not self.held then
          local x, y = self:GetCenter()
          self.held, self.onNav = true, nil
          self:ClearAllPoints()
          if x and y then self:SetPoint("CENTER", UIParent, "BOTTOMLEFT", x, y) else self.faded = 0 end
        end
        self.faded = math.max(0, (self.faded or 1) - dt * 2)
        self:SetAlpha(self.faded * seen)
      else
        self.held, self.faded = nil, 1
        view.Anchor(self, nav, self.side, self.lift)
        self:SetAlpha(seen)
        view.Showed(seen, x)
      end
      local breath = ns.BeaconBreath()
      for _, line in ipairs(self.ring) do line:SetAlpha(breath) end
      view.Yards(self, not away and Plain(Call(Nav("GetDistance"))) or nil)
      view.Say(self.who, s.npc or s.target or s.name or "")
    end
  end
  beacon:SetAlpha(0)
  beacon:Show()
  ns.beaconFrame = beacon
end

function ns.BeaconFollow()
  if not BeaconOn() then return end
  local pointed = PointBeacon()
  BeaconFrame()
  if not pointed and beacon then beacon:SetAlpha(0) end
end

local function BeaconsOff()
  if PinNow() then
    Call(C_Map.ClearUserWaypoint)
    Call(Track("SetSuperTrackedUserWaypoint"), false)
  end
  Saved().beaconPin = nil
  view.StopsOff()
  if beacon then beacon:Hide() end
  if navBeacon then navBeacon:Hide() end
  if view.loopMark then view.loopMark:Hide() end
  if view.brackets then view.brackets.left:SetAlpha(0); view.brackets.right:SetAlpha(0); view.brackets.span:SetAlpha(0); view.brackets:Hide() end
  tracked = nil
end

function ns.BeaconsApply()
  if BeaconOn() then ns.BeaconFollow() else BeaconsOff() end
end

function ns.GuideBeaconTake(debug)
  if not BeaconOn() then return ns.Print(ns.SwitchWords("beacons", false, "beacons")) end
  local map, said, x, y = PointBeacon(true)
  if not map then return ns.Print("The beacon isn't set. " .. said) end
  BeaconFrame()
  if not debug then return end
  C_Timer.After(0.5, function()
    if not BeaconOn() then return end
    local nav = Call(Nav("GetFrame"))
    local s = EpicNow()
    local continent, px, py = ns.PlayerWorldPos()
    local straight = s and s.wx and continent == s.inst and px and Dist(s.wx, s.wy, px, py)
    local ground, from = nil, nil
    if s then ground, from = view.HeightHere(s, continent, px, py) end
    local under = s and s.ground and s.ground.h and s.ground.c and s.ground.h[((s.ground.c - 1) / 2) * s.ground.c + (s.ground.c - 1) / 2 + 1]
    ns.Print(string.format("beacon: map %s at %.1f, %.1f, waypoint %s, tracked %s (%s first), navigation frame %s, on screen %s, %s yd (the step %s yd), the step %s up from you, lifted %d, %s, the step at %s, the ground under it %s",
      tostring(map), x * 100, y * 100, said, tostring(Plain(Call(Track("IsSuperTrackingUserWaypoint")))),
      tostring(Plain(Call(Track("GetHighestPrioritySuperTrackingType")))), nav and "yes" or "no",
      tostring(Plain(Call(Nav("HasValidScreenPosition")))), tostring(Plain(Call(Nav("GetDistance")))),
      straight and string.format("%d", straight) or "?",
      (s and s.z and ground) and string.format("%.0f yd (your height from %s)", s.z - ground, from) or "? (your height can't be told here)",
      nav and select(2, view.BeaconOffset(s, continent, px, py, nav)) or 0,
      Plain(Call(IsIndoors)) and "indoors" or "outdoors", s and s.z and string.format("%.1f", s.z) or "?",
      type(under) == "number" and tostring(under) or "?"))
    BeaconFrame()
  end)
end



function ns.QuestRewards()
  local sh = IndexOfAzerothShared
  local r = type(sh) == "table" and type(sh.rewards) == "table" and sh.rewards or nil
  local who = r and type(r.char) == "table" and r.char or nil
  if not (who and type(r.quests) == "table") then return nil end
  if not ns.IsMe(who) then return nil end
  return r.quests
end

function ns.GuideRewardPick(qid)
  local byPrice = ns.Options().general.sellPrice
  local rw = nil
  for _, s in ipairs(guide and guide.steps or {}) do
    if s.kind == "T" and s.rw and s.ids[1] == qid then rw = s.rw end
  end
  if not rw then
    local quests = ns.QuestRewards()
    rw = quests and type(quests[qid]) == "table" and quests[qid] or nil
  end
  if not rw and not byPrice then return nil, "" end
  rw = rw or {}
  local changed = false
  for _, worn in ipairs(type(rw.worn) == "table" and rw.worn or {}) do
    changed = changed or (Plain(Call(GetInventoryItemID, "player", worn[1])) or 0) ~= worn[2]
  end
  if changed and not byPrice then return nil, ", because you wear other gear than the Index's verdicts went by" end
  local judged, choices, dear, price, all, priced = {}, {}, nil, -1, rw.known, true
  for _, id in ipairs(type(rw.ids) == "table" and rw.ids or {}) do judged[id] = true end
  for i = 1, Plain(Call(GetNumQuestChoices)) or 0 do
    local link = Plain(Call(GetQuestItemLink, "choice", i))
    local name, _, _, _, usable = Call(GetQuestItemInfo, "choice", i)
    local id = link and tonumber(link:match("item:(%d+)"))
    local sells = link and Plain(select(11, Call(C_Item.GetItemInfo, link)))
    priced = priced and sells ~= nil
    sells = sells or 0
    local c = { index = i, name = Plain(name) or "?", usable = Plain(usable) ~= false }
    choices[id or 0] = c
    all = all and id and judged[id]
    if sells > price then dear, price = c, sells end
  end
  local vendor = nil
  for _, p in ipairs(type(rw.picks) == "table" and rw.picks or {}) do
    local c = choices[p.id]
    if p.sell then vendor = vendor or (c and { c, p.sell })
    elseif c and (p.want or (c.usable and not byPrice)) then c.want = p.want; return c, p.v end
  end
  if all and vendor and not priced then dear, price = vendor[1], vendor[2] end
  if (all or (byPrice and priced)) and dear and price > 0 then
    dear.vendor = true
    local coins = ns.Coins and ns.Coins(price) or (price .. "c")
    if byPrice then return dear, "the reward that sells for the most: " .. coins end
    return dear, "a vendor pick, since no reward is an upgrade and this one sells for the most: " .. coins
  end
  if byPrice then return nil, ", because no vendor price is known" end
  if all then return nil, ", because no reward is an upgrade and no vendor price is known" end
  return nil, ", because the Index couldn't judge every reward when the plan was written"
end

local rewardMark = nil
local PICK = { silver = { 0.78, 0.80, 0.84 },
  why = { wear = "Index pick: best upgrade", vendor = "Index pick: no upgrade, best sell price", want = "Index pick: the item you asked for",
    price = "Index pick: best sell price" } }
function ns.GuideMarkReward(i, vendor, want)
  local rf = _G.QuestInfoRewardsFrame
  local button = (rf and rf.RewardButtons and rf.RewardButtons[i]) or _G["QuestInfoRewardsFrameQuestInfoItem" .. i]
    or _G["QuestInfoItem" .. i]
  if not button then return end
  if not rewardMark then
    rewardMark = CreateFrame("Frame", nil, UIParent, "BackdropTemplate")
    rewardMark:SetBackdrop({ edgeFile = ns.UI.WHITE, edgeSize = 2 })
  end
  local edge = vendor and PICK.silver or EPIC_BLUE
  rewardMark:SetBackdropBorderColor(edge[1], edge[2], edge[3], 1)
  rewardMark.why = (want and PICK.why.want) or (vendor and (ns.Options().general.sellPrice and PICK.why.price or PICK.why.vendor))
    or PICK.why.wear
  rewardMark.vendor, rewardMark.edge = vendor or false, edge
  if not button.ccPickHooked and button.HookScript then
    button.ccPickHooked = true
    button:HookScript("OnEnter", function(self)
      if rewardMark and rewardMark:IsShown() and rewardMark:GetParent() == self and GameTooltip:IsShown() then
        GameTooltip:AddLine(rewardMark.why, EPIC_BLUE[1], EPIC_BLUE[2], EPIC_BLUE[3])
        GameTooltip:Show()
      end
    end)
  end
  rewardMark:SetParent(button)
  rewardMark:ClearAllPoints()
  rewardMark:SetPoint("TOPLEFT", button, "TOPLEFT", -2, 2)
  rewardMark:SetPoint("BOTTOMRIGHT", button, "BOTTOMRIGHT", 2, -2)
  rewardMark:SetFrameLevel((button:GetFrameLevel() or 1) + 5)
  rewardMark:Show()
  ns.rewardMark = rewardMark
end
ns.On("QUEST_FINISHED", function() if rewardMark then rewardMark:Hide() end end)
