-- The Index of Azeroth. Copyright 2026 Index Case <indexofazeroth@pm.me>. PolyForm Strict 1.0.0, see LICENSE.md.
local ADDON, ns = ...

local Plain, Call = ns.Plain, ns.Call
local Dist = ns.Geo.Dist
local Rules = ns.Rules

local A = { last = nil, held = {}, done = {}, ready = {}, fighting = false, landed = false, run = nil, decision = nil,
            kept = nil, looked = false, out = {}, chosen = nil, givers = {}, escort = {}, FAR = Rules.cost.far }
ns.Arbiter = A

function A.Key(s) return ns.Trace.Key(s) end

function A.Plan(s, putOff)
  return s.kind ~= "S" or ((s.trip ~= nil or not s.own) and not (putOff or A.PutOff())[A.PutKey(s)])
end

function A.Reach(name) return Rules.Reach(name, A.run) end
function A.Safe() return A.fighting or Plain(Call(UnitIsDeadOrGhost, "player")) == true end

function A.Name(s)
  if not s then return nil end
  if s.name and s.name ~= "" then return s.name end
  local id = s.ids and s.ids[1]
  local title = id and Plain(Call(C_QuestLog.GetTitleForQuestID, id))
  return title or s.text
end

local function InLog(id) return id ~= nil and A.H ~= nil and A.H.InLog(id) and true or false end

function A.FromArea(s, px, py) return Rules.Among({ ar = s.ar, loop = s.loop, x = s.wx, y = s.wy }, px, py) end
function A.Here(s, px, py)
  return Rules.Here({ ar = s.ar, hr = s.hr, loop = s.loop, x = s.wx, y = s.wy }, px, py, A.run)
end

function A.Left(s)
  local o = ns.StepObjective and ns.StepObjective(s)
  if not o then return nil, false end
  local left = (Plain(o.numRequired) or 0) - (Plain(o.numFulfilled) or 0)
  local text = Plain(o.text)
  return left > 0 and left or nil, type(text) == "string" and text:find("slain", 1, true) ~= nil
end

local function Begun(s)
  local o = ns.StepObjective and ns.StepObjective(s)
  return o ~= nil and (Plain(o.numFulfilled) or 0) > 0 and not Plain(o.finished)
end
A.Begun = Begun

function A.HasArea(s) return type(s.ar) == "table" and #s.ar > 0 end
function A.Inside(s, fromArea, reach)
  return fromArea <= (A.HasArea(s) and 0 or reach.area)
end
function A.InArea(s, px, py)
  return A.HasArea(s) and A.Inside(s, (A.FromArea(s, px, py))) or false
end

function A.Stays(key, inside, fromArea, mid, reach)
  if inside then A.out[key] = nil; return true end
  if mid > reach.walked_away then A.out[key] = nil; return false end
  local now, out = GetTime(), A.out[key]
  if not out then out = { at = now, left = 0 }; A.out[key] = out end
  if fromArea >= reach.left then out.left = out.left + (now - out.at) end
  out.at = now
  if out.left >= Rules.no_flap.left_for then A.out[key] = nil; return false end
  return true
end

function A.Working(s, key, fromArea, mid, reach)
  if not Begun(s) then A.out[key] = nil; return false end
  local inside = A.Inside(s, fromArea, reach)
  if not (inside or A.held[key]) then return false end
  return A.Stays(key, inside, fromArea, mid, reach)
end
function A.Escorting(s, key, todo, mark)
  if not (s.en and s.kind == "O" and todo) then A.escort[key] = nil; return false end
  if A.escort[key] then return true end
  if not (ns.SeenLately and ns.SeenLately(s.en)) then return false end
  if mark then A.escort[key] = true end
  return true
end
function A.Now(i, P, key, leading)
  return i == P or (leading ~= nil and key == leading)
end
function A.Evidence(s, key)
  if A.escort[key or A.Key(s)] then return true end
  local o = ns.StepObjective and ns.StepObjective(s)
  return o ~= nil and (Plain(o.numFulfilled) or 0) > 0
end


function A.PutKey(s) return (s.what or "chore") .. ":" .. (s.npc or s.text or "") end
function A.MayPutOff(s) return s ~= nil and s.kind == "S" end
function A.PutOff()
  local sv = ns.GuideSaved()
  sv.putOff = type(sv.putOff) == "table" and sv.putOff or {}
  return sv.putOff
end
function A.Where(s, at)
  at = (at and at.wx) and at or s or {}
  local npc = (at.npc ~= "" and at.npc) or (s and s.npc ~= "" and s.npc) or nil
  return { town = ns.TownAt(at.inst, at.wx, at.wy), npc = npc, place = (s and s.place) or at.place }
end
function A.PutOffWhy(s)
  local off = A.MayPutOff(s) and ns.GuideSaved and A.PutOff()[A.PutKey(s)]
  return off and Rules.Back("words", "put_off", A.Where(s, off)) or nil
end
function A.NextVisit(g, s, from) return A.VisitFor(g, s, from, { [s] = true }) end
function A.VisitFor(g, at, from, moving)
  local G, reach = ns.GUIDE, A.Reach("walked_away")
  for k = (from or 1) + 1, #g.steps do
    local t, st = g.steps[k], g.state[k]
    if not moving[t] and t.kind ~= "S" and (st == G.TODO or st == G.WAIT) and t.wx and at.wx and t.inst == at.inst
       and Dist(t.wx, t.wy, at.wx, at.wy) <= reach then
      return t
    end
  end
  return nil
end
function A.Later(i)
  local g = ns.GuideInfo()
  local s = g and g.steps[i]
  if not A.MayPutOff(s) then return end
  local continent, px, py = ns.PlayerWorldPos()
  local far = not (px and s.wx and s.inst == continent) or Dist(s.wx, s.wy, px, py) > A.Reach("walked_away")
  local after = g.steps[i + 1]
  A.PutOff()[A.PutKey(s)] = { npc = s.npc, inst = s.inst, wx = s.wx, wy = s.wy, out = far, at = time(),
                              after = after and A.Key(after) or false, led = g.cur == i or nil }
  local plan = g.planCur and g.steps[g.planCur]
  local from = 0
  for k, t in ipairs(g.steps) do if t == plan then from = k end end
  local before = A.NextVisit(g, s, from)
  if ns.GuideMoveStep then ns.GuideMoveStep(s.i, before) end
  ns.Print(Rules.Back("words", "put_off_said", A.Where(s), { chore = s.text ~= "" and s.text or ns.StepLabel(s) }))
  if ns.GuideEvaluate then ns.GuideEvaluate() end
end
function A.PutOffLook(g, continent, px, py)
  local list = A.PutOff()
  if not next(list) then return end
  local G, open = ns.GUIDE, {}
  for i, s in ipairs(g.steps) do
    if A.MayPutOff(s) and g.state[i] ~= G.DONE and g.state[i] ~= G.SKIPPED then open[A.PutKey(s)] = s end
  end
  for key, off in pairs(list) do
    if not open[key] then
      list[key] = nil
    elseif px and off.wx and off.inst == continent then
      local d = Dist(off.wx, off.wy, px, py)
      if d > A.Reach("walked_away") then off.out = true end
      if A.BackAt(off, d) then
        list[key], open[key].cameBack = nil, true
      end
    end
  end
  if px then A.TripBack(g, list, continent, px, py) end
end
function A.BackAt(off, d) return off.out == true and d <= A.Reach("back") end
function A.TripBack(g, list, continent, px, py)
  local G, R, data = ns.GUIDE, ns.ChoreRules, ns.ClassTrainers
  local class = Plain(select(3, Call(UnitClass, "player")))
  local side = ({ Alliance = 1, Horde = 2 })[Plain(Call(UnitFactionGroup, "player")) or ""]
  if not (R and data and data.trainers and class) then return end
  local here = { continent, px, py }
  for i, s in ipairs(g.steps) do
    local off = list[A.PutKey(s)]
    if s.trip and s.what == "train" and off and g.state[i] == G.TODO then
      local teaches = ns.Chores and ns.Chores.Teaches and ns.Chores.Teaches() or {}
      local goesOn
      for k, o in ipairs(g.steps) do
        if k ~= i and g.state[k] == G.TODO and A.Plan(o, list) then
          goesOn = o.wx and { o.inst, o.wx, o.wy } or nil
          break
        end
      end
      local t, least = nil, nil
      for _, p in ipairs(R.Places(data.trainers, { class = true }, side, class)) do
        if R.Teaches(teaches, p.id, s.need and s.need.spells) and p.at[1] == continent
           and A.BackAt(off, Dist(p.at[2], p.at[3], px, py)) then
          local added = R.Detour(here, p.at, goesOn)
          if not least or added < least then t, least = p, added end
        end
      end
      if t then
        list[A.PutKey(s)] = nil
        s.cameBack = true
        if t.name ~= s.npc then
          if s.text == "Go train at " .. tostring(s.npc) then s.text = "Go train at " .. t.name end
          s.name, s.npc, s.inst, s.wx, s.wy, s.z, s.map = s.text, t.name, t.at[1], t.at[2], t.at[3], t.at[4], t.at[5] or s.map
          s.bends, s.alt, s.route, s.hearth, s.hw, s.ground, s.guess = nil, nil, nil, nil, nil, nil, nil
          s.easy, s.easyPicked = nil, nil
        end
        for k, o in ipairs(g.steps) do
          if k ~= i and g.state[k] == G.TODO and A.Plan(o, list) then
            if k < i and ns.GuideMoveStep then ns.GuideMoveStep(i, o) end
            break
          end
        end
        return
      end
    end
  end
end


function A.Away()
  local sv = ns.GuideSaved()
  sv.awayLed = type(sv.awayLed) == "table" and sv.awayLed or {}
  return sv.awayLed
end
function A.MarkAway(key, led) A.Away()[key] = led and true or nil end
function A.AwayLook(g)
  local away = A.Away()
  if not next(away) then return end
  local G, still = ns.GUIDE, {}
  for i, s in ipairs(g.steps) do
    if g.state[i] == G.PARKED and s.ids and s.ids[1] then still["q:" .. s.ids[1]] = true end
    if g.state[i] == G.SKIPPED and s.key then still["skip:" .. s.key] = true end
  end
  for key in pairs(away) do if not still[key] then away[key] = nil end end
end

function A.BackSteps(g, b)
  local G, out = ns.GUIDE, {}
  for i, s in ipairs(g.steps) do
    local st = g.state[i]
    local mine
    if b.kind == "later" then
      mine = A.MayPutOff(s) and A.PutKey(s) == b.key and st ~= G.DONE and st ~= G.SKIPPED
    elseif b.kind == "skipped" then
      mine = s == b.s and st == G.SKIPPED
    else
      mine = s.kind ~= "D" and s.kind ~= "S" and s.ids[1] == b.id and st == G.PARKED
    end
    if mine then out[#out + 1] = s end
  end
  return out
end
local function NextOf(g, moving)
  local G = ns.GUIDE
  for i, s in ipairs(g.steps) do
    if g.state[i] == G.TODO and not moving[s] and A.Plan(s) then return i end
  end
  return nil
end
function A.BackHow(g, b)
  local steps = A.BackSteps(g, b)
  local off = b.kind == "later" and A.PutOff()[b.key] or nil
  local spot = (off and off.wx) and off or nil
  for _, s in ipairs(steps) do if not spot and s.wx then spot = s end end
  local out = { steps = steps, spot = spot, npc = (spot and spot.npc ~= "" and spot.npc) or nil }
  local continent, px, py = ns.PlayerWorldPos()
  if spot and px and spot.inst == continent and Dist(spot.wx, spot.wy, px, py) <= A.Reach("back") then
    out.how = "here"
    return out
  end
  local moving = {}
  for _, s in ipairs(steps) do moving[s] = true end
  local N = NextOf(g, moving)
  for _, s in ipairs(steps) do out.move = out.move or (N ~= nil and s.i < N) end
  if out.move then out.before = spot and A.VisitFor(g, spot, N, moving) or nil end
  out.how = (b.kind == "later" or out.move) and "visit" or "place"
  out.npc = out.npc or (out.before and out.before.npc ~= "" and out.before.npc) or nil
  out.where = A.Where(steps[1], spot)
  out.where.npc = out.npc
  return out
end
function A.BackThing(s)
  if not s then return "this step" end
  if s.kind == "S" then return ns.StepLabel(s) end
  return A.Name(s) or s.text
end
function A.BackTip(g, b)
  local w = A.BackHow(g, b)
  return Rules.Back("buttons", "putback_" .. w.how .. "_tip", w.where, { thing = A.BackThing(w.steps[1]) })
end
function A.PutBack(b)
  local g = ns.GuideInfo()
  if not (g and b) then return end
  local w = A.BackHow(g, b)
  local first = w.steps[1]
  if not first then return end
  local led
  if b.kind == "later" then
    local off = A.PutOff()[b.key]
    A.PutOff()[b.key] = nil
    led = off and off.led
    if w.how == "here" and off and off.after ~= nil and first.kind == "S" and ns.GuideMoveStep then
      local to = nil
      for _, t in ipairs(g.steps) do if t ~= first and off.after and A.Key(t) == off.after then to = t end end
      if to or off.after == false then ns.GuideMoveStep(first.i, to) end
    end
  else
    local key = b.kind == "skipped" and ("skip:" .. tostring(first.key)) or ("q:" .. tostring(b.id))
    led = A.Away()[key]
    A.Away()[key] = nil
    if b.kind == "skipped" then
      ns.GuideUnskip(first.i)
    else
      if b.kind == "background" and ns.Drawer then ns.Drawer.Kept()[b.id] = nil end
      ns.GuideRelease(b.id)
    end
  end
  if w.move and ns.GuideMoveStep then
    for _, s in ipairs(w.steps) do
      if not w.before or s.i < w.before.i then ns.GuideMoveStep(s.i, w.before) end
    end
  end
  if w.how == "here" and led then A.Pick(first) end
  ns.Print(Rules.Back("lines", "putback_" .. w.how .. "_said", w.where, { thing = A.BackThing(first) }))
  if ns.MarkChanged then ns.MarkChanged("director") end
  if ns.GuideEvaluate then ns.GuideEvaluate() end
end


function A.Arrived() A.landed = true end
function A.Look(g, H)
  local G, event = ns.GUIDE, nil
  local done, ready, first = {}, {}, not A.looked
  A.looked = true
  for i, s in ipairs(g.steps) do
    local key = A.Key(s)
    if g.state[i] == G.DONE then
      done[key] = true
      if not first and not A.done[key] then event = event or (s.kind == "T" and "handed_in" or "objective_done") end
    elseif s.kind == "T" and s.ids[1] and H.Ready(s.ids[1]) then
      ready[s.ids[1]] = true
      if not first and not A.ready[s.ids[1]] then event = event or "quest_done" end
    end
  end
  A.done, A.ready = done, ready
  local fighting = ns.InFight()
  if A.fighting and not fighting then event = event or "fight_over" end
  A.fighting = fighting
  if A.landed then event, A.landed = event or "arrived", false end
  return event
end

function A.Open(H, s, st, base)
  return st ~= ns.GUIDE.PARKED and (s.kind == "T" or s.kind == "P") and not s.maybe and not s.group and not s.limit
    and H.Takes(s, st, base) and true or false
end

function A.TriedLater(g, i, s)
  if s.kind ~= "P" or not s.maybe or not (ns.GuideBack and ns.GuideBack.WithGiver) then return false end
  local G = ns.GUIDE
  for j = 1, i - 1 do
    local t, st = g.steps[j], g.state[j]
    if (t.kind == "P" or t.kind == "T") and (st == G.TODO or st == G.WAIT) and not t.maybe
       and ns.GuideBack.WithGiver(s, { t }) then
      return true
    end
  end
  return false
end

local function Part(c)
  if not c then return nil end
  return { key = c.key, text = ns.StepLabel and ns.StepLabel(c.s) or c.s.text, kind = c.kind, tier = Rules.Tier(c.kind),
           yards = c.walk and math.floor(c.walk + 0.5) or nil }
end

function A.ToDo(g, H, i)
  local st = g.state[i]
  return st == ns.GUIDE.TODO or (st == ns.GUIDE.WAIT and H.Takes(g.steps[i], st, g.base[i]) and true or false)
end

function A.Pick(s) A.chosen = s and A.Key(s) or nil end

function A.From(key, px, py, continent, arrived)
  local f = A.from
  if arrived or not (f and f.key == key and f.inst == continent) then
    f = { key = key, x = px, y = py, inst = continent }
    A.from = f
  end
  return f
end

function A.Gone(g, H, key)
  for i = 1, H.Count() do
    if A.Key(g.steps[i]) == key then return not A.ToDo(g, H, i) end
  end
  return not (A.last and A.last.key == key and A.last.quest and InLog(A.last.quest))
end

function A.OnWay(g, H, P, px, py, continent)
  local s, f = g.steps[P], A.from
  if not (s and s.wx and s.inst == continent and f and f.key == A.Key(s) and f.inst == continent) then return false end
  local line = { { f.x, f.y } }
  for _, b in ipairs(H.Bends and H.Bends(s, px, py) or {}) do line[#line + 1] = b end
  line[#line + 1] = { s.wx, s.wy }
  if s.kind == "O" and A.FromArea(s, px, py) <= A.Reach("area") then return true end
  return ns.Geo.NearLine(line, px, py) <= A.Reach("corridor")
end

function A.PlanStep(g, H, N, putOff)
  local function held(key)
    if not key then return nil end
    for i = 1, H.Count() do
      local s = g.steps[i]
      if A.Key(s) == key then return (A.Plan(s, putOff) and A.ToDo(g, H, i)) and i or nil end
    end
    return nil
  end
  local clocks = ns.QuestTimers and ns.QuestTimers() or {}
  local chosen, main = held(A.chosen), held(A.main)
  if not chosen then A.chosen = nil end
  if A.timed and not (clocks[A.timed] and A.ClockStep(g, H, A.timed, putOff)) then A.timed = nil end
  local started = {}
  for q, left in pairs(clocks) do if not (A.clocks and A.clocks[q]) then started[q] = left end end
  A.clocks = {}
  for q in pairs(clocks) do A.clocks[q] = true end
  local q = A.ClockPick(g, H, started, chosen or main or N, putOff)
  if q then A.timed, A.chosen, chosen = q, nil, nil end
  if not (chosen or main or A.timed) then A.timed = A.ClockPick(g, H, clocks, N, putOff) end
  local P = chosen or (A.timed and A.ClockStep(g, H, A.timed, putOff)) or main or N
  A.main = A.Key(g.steps[P])
  return P
end


function A.ClockStep(g, H, q, putOff, skip, ahead)
  for i = 1, H.Count() do
    local s = g.steps[i]
    if s.kind ~= "S" and A.Key(s) ~= skip and A.Plan(s, putOff)
       and (A.ToDo(g, H, i) or (ahead and g.state[i] == ns.GUIDE.WAIT)) then
      for _, id in ipairs(s.ids) do if id == q then return i end end
    end
  end
  return nil
end

function A.InTime(g, H, i, q, left, putOff)
  local G, sum = ns.GUIDE, 0
  for k = i or H.Count() + 1, H.Count() do
    local s, st = g.steps[k], g.state[k]
    if A.Plan(s, putOff) and (st == G.TODO or st == G.WAIT) then
      if not s.sec then return false end
      sum = sum + s.sec
      if s.kind == "T" and s.ids[1] == q then return sum <= left end
    end
  end
  return false
end

function A.ClockPick(g, H, clocks, from, putOff)
  local pick, least = nil, math.huge
  for q, left in pairs(clocks) do
    if (not pick or left < least or (left == least and q < pick)) and A.ClockStep(g, H, q, putOff)
       and not A.InTime(g, H, from, q, left, putOff) then
      pick, least = q, left
    end
  end
  return pick
end

function A.BusyLine(g, H, best, continent, putOff)
  if not (ns.Camps and best.s.kind == "O" and best.i and ns.Camps.Busy(best.key)) then return nil end
  local G, name = ns.GUIDE, A.Name(best.s)
  for i = best.i + 1, H.Count() do
    local s = g.steps[i]
    if g.state[i] == G.TODO and s.kind == "O" and A.Plan(s, putOff) and s.wx and s.inst == continent and A.Name(s) ~= name then
      local fill = { won = name, wonNpc = best.s.npc, lost = A.Name(s), lostNpc = s.npc }
      if type(best.s.things) == "string" and best.s.things ~= "" then
        fill.things = best.s.things
        return "busy_thing", fill, s
      end
      return "busy", fill, s
    end
  end
  return nil
end

function A.Reason(won, plan, w)
  local fill = { won = A.Name(won.s), wonNpc = won.s.npc }
  local function lost(s)
    fill.lost, fill.lostNpc = A.Name(s), s.npc
    if fill.lost == fill.won then fill.same = true end
    return s
  end
  local rival = nil
  for _, c in ipairs(w.offs) do if c ~= won and not rival then rival = c end end
  rival = rival or w.near[1]
  if won.kind == "progress" then
    rival = rival or (plan ~= won and plan or nil)
    local g = not rival and won.i and ns.GuideInfo and ns.GuideInfo()
    for i = (won.i or 0) + 1, g and #g.steps or 0 do
      if not rival and g.state[i] == ns.GUIDE.TODO and A.Plan(g.steps[i]) then rival = { s = g.steps[i] } end
    end
    if not rival then return nil end
    local left, kills = A.Left(won.s)
    if not left then return nil end
    fill.n = left
    local giver = (rival.s.kind == "P" or rival.s.kind == "T") and (rival.walk or math.huge) <= A.Reach("walked_away")
    local key = (giver and "progress_giver" or "progress_step")
    local things = won.s.things
    if type(things) == "string" and things ~= "" and type(won.s.target) == "string" and won.s.target ~= "" then
      fill.thing, fill.things = won.s.target, things
      key = key .. "_thing" .. (left == 1 and "_one" or "")
    else
      key = key .. (not kills and "_more" or left == 1 and "_one" or "")
    end
    return key, fill, lost(rival.s)
  end
  if won ~= plan then
    local named = won.s.npc ~= nil and won.s.npc ~= ""
    local key = nil
    if won.kind == "handin" then
      local n = 1
      for _, c in ipairs(w.offs) do
        if c ~= won and c.kind == "handin" and Dist(c.x, c.y, won.x, won.y) <= A.Reach("giver") then n = n + 1 end
      end
      key = n > 1 and "handins" or named and "handin" or "handin_here"
      if key == "handins" then fill.n = n end
    elseif won.kind == "pickup" then
      key = named and "pickup" or "pickup_here"
    elseif won.kind == "errand" and named then
      key = "errand"
    end
    if not key then return nil end
    return key, fill, lost(plan.s)
  end
  local named = rival and (rival.kind == "area" or (rival.s.npc ~= nil and rival.s.npc ~= ""))
  if named and rival.i and plan.i and rival.i > plan.i and Dist(rival.x, rival.y, won.x, won.y) >= Rules.run.hop then
    local G, g, at = ns.GUIDE, ns.GuideInfo and ns.GuideInfo(), 0
    for i = plan.i + 1, rival.i - 1 do
      local st = g and g.state[i]
      if (st == G.TODO or st == G.WAIT) and A.Plan(g.steps[i]) then at = at + 1 end
    end
    if not Rules.Said("order", at, ns.GuidePlay and ns.GuidePlay() or 1) then return nil end
    return rival.kind == "area" and "wait_area" or "wait_giver", fill, lost(rival.s)
  end
  return nil
end

A.passSaid = {}
function A.Pass(g, best, H, px, py, continent, nKey, stretchKeys)
  local G, here = ns.GUIDE, best.s.place
  if best.kind ~= "next" or not best.i or not here or not best.s.wx then return nil end
  local far, reach, putOff = Dist(best.s.wx, best.s.wy, px, py), A.Reach("pass"), A.PutOff()
  local way = H.WayOn(best.s, px, py)
  local before, first, near, comes = {}, {}, {}, nil
  for i, s in ipairs(g.steps) do
    local st, pl = g.state[i], s.place
    if (st == G.TODO or st == G.WAIT) and s.kind ~= "S" and A.Plan(s, putOff) and i ~= best.i then
      if i < best.i then
        if pl then before[pl] = true end
      else
        if comes == nil and pl ~= here then comes = pl or false end
        if pl and pl ~= here then
          first[pl] = first[pl] or s
          if s.wx and s.inst == continent then
            local d = Dist(s.wx, s.wy, px, py)
            if d < far and d < (near[pl] or math.huge) and H.NearWay(way, s.wx, s.wy) <= reach then near[pl] = d end
          end
        end
      end
    end
  end
  local pick, yards = nil, math.huge
  for pl, d in pairs(near) do
    if not before[pl] and pl ~= comes and d < yards then pick, yards = pl, d end
  end
  if not pick then return nil end
  local was = A.passSaid[pick]
  if was and was[nKey] then return nil end
  local said = {}
  for _, k in ipairs(stretchKeys) do said[k] = true end
  said[nKey] = true
  A.passSaid[pick] = said
  return pick:sub(-1) == "s" and "pass_s" or "pass",
    { place = here, nearer = pick, won = A.Name(best.s), lost = A.Name(first[pick]) }, first[pick]
end

function A.Next(g, H, putOff)
  local G = ns.GUIDE
  local N, firstChore, chores = nil, nil, {}
  for i = 1, H.Count() do
    local s = g.steps[i]
    if not A.Plan(s, putOff) then
      if g.state[i] == G.TODO then
        firstChore = firstChore or i
        if not N and not putOff[A.PutKey(s)] then chores[#chores + 1] = i end
      end
    elseif not N and A.ToDo(g, H, i) then
      N = i
    end
  end
  return N, firstChore, chores
end

function A.Lead(g, H)
  local G = ns.GUIDE
  A.H = H
  local continent, px, py = ns.PlayerWorldPos()
  local landed = A.landed
  local event = A.Look(g, H)
  A.PutOffLook(g, continent, px, py)
  A.AwayLook(g)
  local putOff = A.PutOff()
  local N, firstChore, chores = A.Next(g, H, putOff)
  A.givers = {}
  if not N and not firstChore then
    g.choresDue = chores
    return nil
  end
  A.run = ns.Trace.Stretch(g, N or firstChore)
  for i = (N or H.Count()) + 1, H.Count() do
    local s = g.steps[i]
    if not A.Plan(s, putOff) and g.state[i] == G.TODO and not putOff[A.PutKey(s)] and px and s.wx and s.inst == continent
       and Dist(s.wx, s.wy, px, py) <= A.Reach("back") then
      chores[#chores + 1] = i
    end
  end
  g.choresDue = chores
  local now = GetTime()
  if not N then
    local s = g.steps[firstChore]
    local c = { i = firstChore, s = s, key = A.Key(s), kind = "chore",
                walk = (px and s.wx and s.inst == continent) and Dist(s.wx, s.wy, px, py) or nil }
    local quests = false
    for _, t in ipairs(g.steps) do quests = quests or t.kind ~= "S" end
    local say = quests and s.npc and s.npc ~= "" and "only" or nil
    return A.Decided(c, nil, { c }, say, { wonNpc = s.npc }, event, nil, now, firstChore)
  end
  local sN, P = g.steps[N], A.PlanStep(g, H, N, putOff)
  if not (continent and px) then
    local c = { i = P, s = g.steps[P], key = A.Key(g.steps[P]), kind = "next", plan = true }
    return A.Decided(c, nil, { c }, nil, nil, event, nil, now, P)
  end
  if A.off and A.Gone(g, H, A.off) then A.off, A.from = nil, nil end
  A.From(A.Key(g.steps[P]), px, py, continent, landed)
  local leading = A.last and A.last.key
  local w = A.Weigh(g, H, P, px, py, continent, putOff, A.held, leading, nil, nil, event, now)
  event = w.event
  if w.gone then event = event or "walked_away" end
  if ns.Camps and not w.camped then ns.Camps.Look(nil, nil, false, now) end
  A.held, A.cands, A.N, A.P = w.held, w.all, N, P
  for _, c in ipairs(w.offs) do if not c.train then A.givers[#A.givers + 1] = c.s end end
  local L = A.last and w.byKey[A.last.key]
  local best = (L and A.Safe()) and L or nil
  if not best then
    for _, c in ipairs(w.progress) do
      if c.escort and (not best or c == L) then best = c end
    end
  end
  if not best and w.plan.kind ~= "progress" then
    local held = A.off and w.byKey[A.off]
    local sP = g.steps[P]
    if held and sP.wx and sP.inst == continent and (held.walk or 0) > A.Reach("giver")
       and Rules.Arrived({ x = sP.wx, y = sP.wy, ar = sP.ar, loop = sP.loop }, px, py, A.run) then
      held = nil
    end
    if held and held.kind ~= "progress" and held ~= w.plan then
      best = held
    else
      A.off = nil
      for _, c in ipairs(w.offs) do if c.takes and not best then best = c end end
      if best then A.off = best.key end
    end
  end
  best = best or w.plan
  local key, fill, other = A.Reason(best, w.plan, w)
  if fill and fill.same then key, fill, other = nil, nil, nil end
  local bk, bf, bo = A.BusyLine(g, H, best, continent, putOff)
  if bk then key, fill, other = bk, bf, bo end
  if not key or Rules.Quiet(key) then
    local pk, pf, po = A.Pass(g, best, H, px, py, continent, A.Key(sN), A.Stretch(g, H, N, continent, putOff))
    if pk then key, fill, other = pk, pf, po end
  end
  local cur, onPlan, extra, decision = A.Decided(best, w.plan, w.all, key, fill, event, L ~= nil, now, P, other)
  local ok, after = pcall(A.Then, g, H, best, w.plan, putOff, continent)
  decision.after = ok and after and Part(after) or nil
  decision.afterStep = ok and after and after.s or nil
  decision.afterOf = ok and after and best.s or nil
  return cur, onPlan, extra, decision
end

function A.Stretch(g, H, N, continent, putOff)
  local G, keys = ns.GUIDE, { A.Key(g.steps[N]) }
  for i = N + 1, H.Count() do
    if #keys > Rules.run.steps then break end
    local s, st = g.steps[i], g.state[i]
    if A.Plan(s, putOff) and (st == G.TODO or st == G.WAIT) and s.wx and s.inst == continent then keys[#keys + 1] = A.Key(s) end
  end
  return keys
end

function A.Then(g, H, best, plan, putOff, continent)
  if not (best and best.s) then return nil end
  if not (best.x and best.y) then return (plan and best ~= plan) and plan or nil end
  local G, skip = ns.GUIDE, best.key
  local opens = best.s.kind == "T" and best.s.ids and best.s.ids[1] or nil
  local function Open(i, s)
    if A.ToDo(g, H, i) then return true end
    if not (opens and g.state[i] == G.WAIT and s.kind == "P" and ns.GuideNeedsFirst) then return false end
    local needs = ns.GuideNeedsFirst(s)
    return #needs == 1 and needs[1] == opens
  end
  if plan and best ~= plan then
    if not plan.i then return plan end
    local w = A.Weigh(g, H, plan.i, best.x, best.y, continent, putOff, {}, nil, skip, Open, nil, GetTime())
    for _, c in ipairs(w.offs) do
      if (c.open or (c.i and Open(c.i, c.s))) and Rules.Apart(c, w.plan) then return c end
    end
    return plan
  end
  local P2 = nil
  for i = 1, H.Count() do
    local s = g.steps[i]
    if not P2 and Open(i, s) and A.Plan(s, putOff) and A.Key(s) ~= skip then P2 = i end
  end
  local q = A.timed or (P2 and A.ClockPick(g, H, ns.QuestTimers and ns.QuestTimers() or {}, P2, putOff))
  P2 = (q and A.ClockStep(g, H, q, putOff, skip, true)) or P2
  if not P2 then return nil end
  local w = A.Weigh(g, H, P2, best.x, best.y, continent, putOff, {}, nil, skip, Open, nil, GetTime())
  for _, c in ipairs(w.offs) do
    if c.open and Rules.Apart(c, w.plan) then return c end
  end
  return w.plan
end

function A.Weigh(g, H, P, px, py, continent, putOff, keep, leading, skip, opened, event, now)
  local G = ns.GUIDE
  local reach = {}
  for _, name in ipairs({ "giver", "area", "walked_away", "left", "back" }) do reach[name] = A.Reach(name) end
  local w = { progress = {}, offs = {}, near = {}, all = {}, byKey = {}, held = {}, gone = nil, event = event,
              camped = false }
  local function Add(list, c)
    c.key, c.ar = c.key or A.Key(c.s), c.s.ar
    if w.byKey[c.key] then return w.byKey[c.key] end
    w.byKey[c.key] = c
    w.all[#w.all + 1] = c
    if list then list[#list + 1] = c end
    return c
  end
  local taken = not skip and A.off or nil
  local function Near(key, s, within)
    local d = Dist(s.wx, s.wy, px, py)
    return d <= (within or reach.giver) or (key == taken and d <= reach.back)
  end
  for i = 1, H.Count() do
    local s, st = g.steps[i], g.state[i]
    local opens = opened and st ~= G.TODO and opened(i, s)
    if opens then st = G.TODO end
    local key = A.Key(s)
    if s.en and st ~= G.TODO and not skip then A.escort[key] = nil end
    if s.wx and s.inst == continent and not (skip and key == skip) and A.Plan(s, putOff) then
      if s.kind == "O" and st == G.TODO and InLog(s.ids[1]) then
        local fromArea, bx, by, mid, mx, my = A.FromArea(s, px, py)
        if key == leading and ns.Camps and not skip then
          w.event = w.event or ns.Camps.Look(s, key, fromArea <= 0, now, px, py)
          w.camped = true
        end
        local working = A.Escorting(s, key, true, not skip)
        if not working and skip then working = Begun(s) and A.Inside(s, fromArea, reach) end
        if not working and not skip then
          working = A.Now(i, P, key, leading) and A.Working(s, key, fromArea, mid, reach)
        end
        local c = { i = i, s = s, walk = math.max(0, fromArea), x = bx, y = by, ox = mx, oy = my }
        local hereAt, hx, hy, _, hmx, hmy = A.Here(s, px, py)
        if not working and hereAt then c.walk, c.x, c.y, c.ox, c.oy = math.max(0, hereAt), hx, hy, hmx, hmy end
        if working then
          w.held[key] = true
          c.kind, c.escort = "progress", A.escort[key] or (skip and s.en ~= nil) or nil
          Add(w.progress, c)
        elseif i ~= P and hereAt then
          c.kind = "area"
          w.near[#w.near + 1] = c
        end
        if keep[key] and not w.held[key] then w.gone = w.gone or s end
      elseif (s.kind == "T" or s.kind == "P") and i ~= P and (opens or H.Takes(s, st, g.base[i]))
             and Near(key, s) and not A.TriedLater(g, i, s) then
        Add(w.offs, { i = i, s = s, kind = s.kind == "T" and "handin" or "pickup", walk = Dist(s.wx, s.wy, px, py),
                      x = s.wx, y = s.wy, open = A.Open(H, s, st, g.base[i]) })
      end
    end
    if s.kind == "S" and s.what == "train" and st == G.TODO and i ~= P and s.wx and s.inst == continent
       and not (skip and key == skip) and not putOff[A.PutKey(s)] and Near(key, s, s.cameBack and reach.back or nil) then
      Add(w.offs, { i = i, s = s, kind = "errand", walk = Dist(s.wx, s.wy, px, py), x = s.wx, y = s.wy, train = true })
    end
  end
  for _, e in ipairs(g.ends or {}) do
    local x = type(e) == "table" and not g.handIns[e.q] and H.Ready(e.q) and H.Extra(e)
    if x and x.inst == continent and x.wx and not (skip and A.Key(x) == skip) then
      x.name = x.name or A.Name(x) or ("quest " .. tostring(x.ids[1]))
      x.text = x.text or ("Turn in " .. x.name .. ((x.npc and x.npc ~= "") and (" to " .. x.npc) or ""))
      if Near(A.Key(x), x) then
        Add(w.offs, { s = x, extra = x, kind = "handin", walk = Dist(x.wx, x.wy, px, py), x = x.wx, y = x.wy, open = true })
      end
    end
  end
  local function Goes(i, plan)
    local s = g.steps[i]
    local c = { i = i, s = s, kind = "next", plan = plan }
    if s.wx and s.inst == continent then
      if s.kind == "O" then
        local fromArea, bx, by, _, mx, my = A.FromArea(s, px, py)
        c.walk, c.x, c.y, c.ox, c.oy = math.max(0, fromArea), bx, by, mx, my
      else
        c.walk, c.x, c.y = Dist(s.wx, s.wy, px, py), s.wx, s.wy
      end
    else
      local off = s.wx ~= nil
      c.walk, c.x, c.y = off and A.FAR or 0, off and px + A.FAR or px, py
    end
    return Add(nil, c)
  end
  w.plan = w.byKey[A.Key(g.steps[P])] or Goes(P, true)
  local onWay = not skip and A.OnWay(g, H, P, px, py, continent)
  for _, c in ipairs(w.offs) do
    if c.key == taken then
      c.takes = true
    elseif c.train then
      c.takes = (c.i or 0) < P or c.s.cameBack == true or (not c.s.trip and Rules.Apart(c, w.plan))
    elseif c.open then
      c.takes = onWay and Rules.Apart(c, w.plan)
    end
  end
  if leading and not skip and not w.byKey[leading] and A.Safe() then
    for i = 1, H.Count() do
      if A.Key(g.steps[i]) == leading and A.Plan(g.steps[i], putOff) and A.ToDo(g, H, i) then Goes(i, false) end
    end
  end
  return w
end

function A.Decided(best, planC, cands, key, fill, event, stayed, now, P, other)
  local was = A.last
  local changed = not was or was.key ~= best.key
  local over = nil
  if planC and best ~= planC then over = planC end
  if not over then
    for _, c in ipairs(cands) do if c ~= best and (not over or Rules.Wins(c, over)) then over = c end end
  end
  local said = key and Rules.Say(key, fill) or nil
  local line = not Rules.Quiet(key) and said or nil
  local rule = key or "same"
  if changed then
    local handed = was and was.quest and not InLog(was.quest)
    rule = (not was and "start") or key or ((A.done[was.key] or handed) and "plan") or (not stayed and "left") or best.kind
    A.kept = nil
  end
  if type(key) == "string" and (key == "pass" or key == "pass_s" or key:sub(1, 4) == "busy") then
    A.kept = { step = best.key, key = key, fill = fill, line = line, said = said, other = other }
  end
  local k = (not line and A.kept and A.kept.step == best.key) and A.kept or nil
  if k then key, fill, line, other, said = k.key, k.fill, k.line, k.other, k.said end
  A.decision = { won = Part(best), over = Part(over), key = key, fill = fill, line = line, said = said, rule = rule,
                 run = A.run, event = event, changed = changed, at = now, lostStep = other }
  A.last = { key = best.key, quest = best.extra and best.extra.ids[1] or nil, s = best.s }
  return best.i, P or best.i, best.extra, A.decision
end

function A.Settle(s)
  local key = s and A.Key(s) or "none"
  local was = A.last
  local changed = not was or was.key ~= key
  A.decision = { won = s and { key = key, text = ns.StepLabel and ns.StepLabel(s) or s.text, kind = "next", tier = 4 } or nil,
                 key = s and "back" or nil, line = s and Rules.Say("back") or nil, rule = s and "back" or "stop",
                 run = A.run, changed = changed, at = GetTime() }
  A.last = { key = key, s = s }
  return A.decision
end

function A.Reset()
  A.last, A.held, A.done, A.ready, A.kept, A.decision, A.run, A.main = nil, {}, {}, {}, nil, nil, nil, nil
  A.passSaid, A.out, A.chosen, A.givers, A.escort, A.off, A.from = {}, {}, nil, {}, {}, nil, nil
  A.timed, A.clocks = nil, nil
  A.looked = false
end
