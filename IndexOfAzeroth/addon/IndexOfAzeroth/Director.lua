-- The Index of Azeroth. Copyright 2026 Index Case <indexofazeroth@pm.me>. PolyForm Strict 1.0.0, see LICENSE.md.
local ADDON, ns = ...

local Plain, Call = ns.Plain, ns.Call
local Dist = ns.Geo.Dist
local Rules = ns.Rules
local UI = ns.UI
local C = UI.C

local D = { asks = {}, open = nil, goneAt = nil, breakAt = nil, rewardAt = nil, offered = {}, working = false,
            fighting = false, resting = nil, lookedAt = nil, xp = nil, counted = nil, left = nil, leftShown = false,
            SLIDE = 0.25, PAD = 10, W = 300, LEFT_MOST = 200, LEFT_LEAST = 40, ASKED_MOST = 12, BACKGROUND_MOST = 6,
            LOOK_GAP_MOST = 10, ASKED_FOR = 600, slideId = 0 }
ns.Director = D

local KIND_CODE = { drift = 1, nextzone = 2, levelup = 3, classquest = 4 }
local PAGE_ONLY = { levelup = true }

function D.Now() return time() end

function D.Saved()
  if type(IndexOfAzerothCharDB) ~= "table" then IndexOfAzerothCharDB = {} end
  local sv = IndexOfAzerothCharDB.director
  if type(sv) ~= "table" then
    sv = {}
    IndexOfAzerothCharDB.director = sv
  end
  for _, k in ipairs({ "closed", "told", "background", "classq" }) do sv[k] = type(sv[k]) == "table" and sv[k] or {} end
  sv.quips = tonumber(sv.quips) or 0
  return sv
end


local function Since(at) return at and (D.Now() - at) or nil end
function D.Moment()
  if Plain(Call(UnitIsDeadOrGhost, "player")) then return false end
  return Rules.Moment(D.fighting, D.working, Since(D.breakAt), Since(D.rewardAt))
end
function D.Break(event)
  for _, e in ipairs(Rules.director.breaks) do
    if e == event then D.breakAt = D.Now(); return true end
  end
  return false
end
function D.Reward() D.rewardAt = D.Now() end

function D.Xp()
  local level, xp = Plain(Call(UnitLevel, "player")), Plain(Call(UnitXP, "player"))
  if not (level and xp) then return end
  local was = D.xp
  D.xp = { level = level, xp = xp }
  if was and (level > was.level or xp > was.xp) then D.Reward() end
end
function D.Counted(g)
  local n = 0
  for i, s in ipairs(g and g.steps or {}) do
    if s.kind == "O" and g.state[i] ~= ns.GUIDE.DONE then
      local o = ns.StepObjective and ns.StepObjective(s)
      n = n + (o and Plain(o.numFulfilled) or 0)
    end
  end
  if D.counted and n > D.counted then D.Reward() end
  D.counted = n
end


function D.Ask(kind, ask)
  ask.kind, ask.at = kind, ask.at or D.Now()
  D.asks[kind] = ask
  if D.open and D.open.kind == kind and not PAGE_ONLY[kind] then
    D.slideId = D.slideId % 255 + 1
    ask.shown, ask.id = D.open.shown, D.slideId
    D.open = ask
    D.Draw()
  end
  D.Changed()
end
function D.Changed()
  ns.MarkChanged("director")
  ns.MarkChanged("directortext")
end
function D.Drop(kind)
  D.asks[kind] = nil
  if D.open and D.open.kind == kind then D.Gone(false) end
end
function D.Best()
  local best = nil
  for kind, a in pairs(D.asks) do
    if a ~= D.open then
      local p, bp = Rules.asks[kind] or 0, best and (Rules.asks[best.kind] or 0)
      if not best or p > bp or (p == bp and a.at < best.at) then best = a end
    end
  end
  return best
end
function D.MayShow(a)
  local closed = D.Saved().closed[a.kind]
  return D.Moment() and Rules.MayShow(D.open and 1 or 0, Since(D.goneAt), Since(closed))
end
function D.Tick()
  local now = D.Now()
  local moment = string.format("%s%s%s%s", tostring(D.working), tostring(D.fighting),
    tostring(D.breakAt ~= nil and now - D.breakAt <= Rules.director.break_for),
    tostring(D.rewardAt ~= nil and now - D.rewardAt >= Rules.director.dry))
  if moment ~= D.moment then D.moment = moment; D.Changed() end
  if D.open then
    local page = PAGE_ONLY[D.open.kind]
    if now - D.open.shown >= (page and Rules.director.page_for or Rules.director.linger) then D.Gone(not page) end
    return
  end
  local a = D.Best()
  if a and D.MayShow(a) then D.Show(a) end
end
function D.Show(a)
  a.shown = D.Now()
  D.slideId = D.slideId % 255 + 1
  a.id = D.slideId
  D.open = a
  if a.onShow then a.onShow(a) end
  D.Draw()
  D.Changed()
end
function D.Gone(closed)
  local a = D.open
  if not a then return end
  D.open = nil
  D.asks[a.kind] = nil
  D.goneAt = D.Now()
  if closed then D.Saved().closed[a.kind] = D.goneAt end
  D.Draw()
  D.Changed()
end


local slide = UI.Box(UIParent, C.bg, C.edge, "MEDIUM")
slide:SetSize(D.W, 60)
slide:SetClampedToScreen(true)
slide:EnableMouse(true)
slide:Hide()
slide.text = UI.Text(slide, "GameFontHighlight", C.ivory)
slide.text:SetPoint("TOPLEFT", D.PAD, -D.PAD)
slide.text:SetWidth(D.W - D.PAD - 30)
slide.text:SetWordWrap(true)
slide.close = UI.FlatButton(slide, "x", 20, function()
  local a = D.open
  if a and a.onClose then a.onClose(a) end
  D.Gone(true)
end)
slide.close:SetSize(20, 20)
slide.close:SetPoint("TOPRIGHT", -6, -6)
slide.close:HookScript("OnEnter", function(self)
  GameTooltip:SetOwner(self, "ANCHOR_BOTTOM")
  GameTooltip:AddLine(D.open and D.open.closeTip or Rules.Line("buttons", "close_tip"), 1, 1, 1, true)
  GameTooltip:Show()
end)
slide.close:HookScript("OnLeave", function() GameTooltip:Hide() end)
slide.replan = UI.FlatButton(slide, Rules.Line("buttons", "replan"), 88, function()
  local a = D.open
  if a and a.buttons and a.buttons.replan then a.buttons.replan(a) end
end)
slide.replan:SetHeight(20)
slide.replan:HookScript("OnEnter", function(self)
  GameTooltip:SetOwner(self, "ANCHOR_BOTTOM")
  GameTooltip:AddLine(D.open and D.open.tip or Rules.Line("buttons", "replan_tip"), 1, 1, 1, true)
  GameTooltip:Show()
end)
slide.replan:HookScript("OnLeave", function() GameTooltip:Hide() end)
D.slide = slide

function D.Anchor()
  local card = ns.guideCard
  local from = (card and card:IsShown() and card) or (IndexOfAzerothButton and IndexOfAzerothButton:IsShown() and IndexOfAzerothButton) or nil
  if not from then return nil, false end
  local _, y = from:GetCenter()
  local h = UIParent:GetHeight()
  return from, (y and h and y > h * 2 / 3) and true or false
end
function D.Draw()
  local a = D.open
  if not a or PAGE_ONLY[a.kind] or D.fighting then return slide:Hide() end
  slide.text:SetText(a.text)
  slide.replan.label:SetText(a.label or Rules.Line("buttons", "replan"))
  local replan = a.buttons and a.buttons.replan and true or false
  slide.replan:SetShown(replan)
  slide.replan:ClearAllPoints()
  slide.replan:SetPoint("TOPLEFT", slide.text, "BOTTOMLEFT", 0, -6)
  slide:SetHeight(D.PAD + (slide.text:GetStringHeight() or 14) + (replan and 6 + 20 or 0) + D.PAD)
  slide.from, slide.down = D.Anchor()
  slide.out = 0
  slide:Show()
  D.Place()
end
function D.Place()
  slide:ClearAllPoints()
  local from, out, h = slide.from, slide.out or 1, slide:GetHeight() or 60
  if not from then return slide:SetPoint("TOP", UIParent, "TOP", 0, -120) end
  if from.GetFrameLevel then slide:SetFrameLevel(math.max(0, (from:GetFrameLevel() or 1) - 1)) end
  if slide.down then slide:SetPoint("TOP", from, "BOTTOM", 0, (1 - out) * h - 4 * out)
  else slide:SetPoint("BOTTOM", from, "TOP", 0, -(1 - out) * h + 4 * out) end
  slide:SetAlpha(math.min(1, out * 1.5))
end
ns.OnTick(slide, "the card's sliding notice", nil, function(_, dt)
  if (slide.out or 1) >= 1 then return end
  slide.out = math.min(1, (slide.out or 0) + dt / D.SLIDE)
  D.Place()
end)


D.rowGone = {}
local function StillDue(g, s)
  for i, t in ipairs(g.steps) do if t == s then return g.state[i] == ns.GUIDE.TODO end end
  return false
end
function D.Rows(g)
  local list, keep, offered, now = g.choresDue or {}, {}, {}, D.Now()
  local may = D.Moment()
  for _, i in ipairs(list) do
    local s = g.steps[i]
    local key = s and ns.Trace.Key(s)
    local rested = key and (not D.rowGone[key] or now - D.rowGone[key] >= Rules.director.cooldown)
    if key and (D.offered[key] or (may and rested)) then
      offered[key] = s
      keep[#keep + 1] = i
    end
  end
  local putOff = ns.Arbiter and ns.Arbiter.PutOff() or {}
  for key, s in pairs(D.offered) do
    if not offered[key] then
      local walked = type(s) == "table" and not putOff[ns.Arbiter.PutKey(s)] and StillDue(g, s)
      D.rowGone[key] = walked and now or nil
    end
  end
  D.offered = offered
  g.choresDue = keep
end


function D.Drift()
  local sv = D.Saved()
  sv.drift = type(sv.drift) == "table" and sv.drift or {}
  local dr = sv.drift
  dr.parts = type(dr.parts) == "table" and dr.parts or {}
  dr.log = type(dr.log) == "table" and dr.log or {}
  dr.seen = type(dr.seen) == "table" and dr.seen or {}
  return dr
end
function D.Points() return Rules.Drift(D.Drift().parts) end
function D.Log()
  local out = {}
  for i = 1, Plain(Call(C_QuestLog.GetNumQuestLogEntries)) or 0 do
    local info = Call(C_QuestLog.GetInfo, i)
    local id = type(info) == "table" and not Plain(info.isHeader) and Plain(info.questID)
    if id then out[#out + 1] = id end
  end
  return out
end
function D.Loaded(g)
  local dr, sv = D.Drift(), ns.GuideSaved and ns.GuideSaved() or {}
  if dr.key == g.key and dr.version == g.version then return end
  local fresh = sv.freshFor == g.version or dr.key ~= g.key
  if fresh then
    dr.parts, dr.seen, dr.shownAt, dr.log = {}, {}, nil, {}
    for _, id in ipairs(D.Log()) do dr.log[id] = true end
  else
    dr.parts.replan = (dr.parts.replan or 0) + 1
  end
  dr.key, dr.version = g.key, g.version
  D.Drop("drift")
end
local function Add(part, n)
  local dr = D.Drift()
  dr.parts[part] = (dr.parts[part] or 0) + n
end
function D.Picked(g)
  local dr = D.Drift()
  for _, id in ipairs(D.Log()) do
    if not (dr.log[id] or g.quests[id] or dr.seen["q" .. id]) then
      dr.seen["q" .. id] = true
      Add("extra", 1)
    end
  end
end
function D.HandedIn(g, id)
  local cur = g.cur and g.steps[g.cur]
  local led = cur and cur.kind == "T" and cur.ids[1] == id
  for _, s in ipairs(g.steps) do
    if s.kind == "T" and s.ids[1] == id and not s.extra then
      if not led then Add("order", 1) end
      return
    end
  end
end
function D.Served(g)
  local name = Plain(Call(UnitName, "npc"))
  if not name then return end
  local cur = g.cur and g.steps[g.cur]
  if cur and ns.Geo.IsGiver(cur, ns.Geo.UnitKey("npc"), name) then return end
  for _, i in ipairs(g.choresDue or {}) do if g.steps[i] and g.steps[i].npc == name then return end end
  local dr = D.Drift()
  if dr.seen["n" .. name] then return end
  dr.seen["n" .. name] = true
  Add("chore", 1)
end
local function LineYards(px, py, ax, ay, bx, by)
  local dx, dy = bx - ax, by - ay
  local len = dx * dx + dy * dy
  local t = len > 0 and math.max(0, math.min(1, ((px - ax) * dx + (py - ay) * dy) / len)) or 0
  return Dist(px, py, ax + t * dx, ay + t * dy)
end
function D.OffLine(g, continent, px, py)
  local now, was = D.Now(), D.lookedAt
  D.lookedAt = now
  local s = g.cur and g.steps[g.cur]
  if not (s and s.wx and px and s.inst == continent) then D.leg = nil; return end
  local key = ns.Trace.Key(s)
  if not D.leg or D.leg.key ~= key then D.leg = { key = key, x = px, y = py } end
  if not was or Plain(Call(UnitOnTaxi, "player")) or Plain(Call(IsInInstance)) then return end
  local reach = ns.Arbiter.Reach("walked_away")
  local d = s.kind == "O" and math.max(0, (ns.Arbiter.FromArea(s, px, py))) or Dist(s.wx, s.wy, px, py)
  d = math.min(d, LineYards(px, py, D.leg.x, D.leg.y, s.wx, s.wy))
  local bends = ns.StepBends and ns.StepBends(s, px, py)
  if bends and #bends > 0 and ns.Arbiter.H and ns.Arbiter.H.NearWay then d = math.min(d, ns.Arbiter.H.NearWay(bends, px, py)) end
  local w = Rules.OffWeight(d, reach)
  if w > 0 then Add("off", math.min(D.LOOK_GAP_MOST, now - was) * w) end
end
function D.Nudge()
  local dr = D.Drift()
  local points = Rules.Drift(dr.parts)
  if D.asks.drift or not Rules.Nudge(points, dr.shownAt) then return end
  local sv = D.Saved()
  sv.quips = sv.quips + 1
  D.Ask("drift", { text = Rules.Pick("drift", sv.quips), tip = Rules.Line("buttons", "replan_tip"),
                   buttons = { replan = function() D.Replan(1) end },
                   onShow = function() D.Drift().shownAt = Rules.Drift(D.Drift().parts) end })
end


local function Mid(name) return (name:gsub("^The ", "the ")) end
function D.NextTable()
  local sh = IndexOfAzerothShared
  local nx = type(sh) == "table" and type(sh.next) == "table" and sh.next or nil
  local who = nx and type(nx.char) == "table" and nx.char
  if not who then return nil end
  if not ns.IsMe(who) then return nil end
  return nx
end
local function StillOpen(ids)
  local out = {}
  for _, id in ipairs(ids or {}) do
    if Plain(Call(C_QuestLog.GetLogIndexForQuestID, id)) or not Plain(Call(C_QuestLog.IsQuestFlaggedCompleted, id)) then
      out[#out + 1] = id
    end
  end
  return out
end
function D.NextWords(level, zones, continent, here, side)
  local near, far = {}, {}
  for _, z in ipairs(zones) do
    if z.i == continent then near[#near + 1] = z else far[#far + 1] = z end
  end
  local ride = side == "Horde" and "zeppelin" or "boat"
  local news = {}
  if #near > 0 then
    news[1] = Rules.Line("lines", "next_news", { level = level, zone = Mid(near[1].n) })
    for k = 2, #near do news[#news + 1] = Rules.Line("lines", "next_also", { zone = Mid(near[k].n) }) end
    for _, z in ipairs(far) do news[#news + 1] = Rules.Line("lines", "next_far_" .. ride, { zone = z.n }) end
  else
    news[1] = Rules.Line("lines", "next_news_" .. ride, { level = level, zone = Mid(far[1].n) })
    for k = 2, #far do news[#news + 1] = Rules.Line("lines", "next_far_" .. ride, { zone = far[k].n }) end
  end
  local text = table.concat(news, " ")
  if not here then return text, nil, nil end
  local leads, ids = nil, nil
  for _, z in ipairs(#near > 0 and near or far) do
    local open = StillOpen(z.q)
    if #open > 0 then leads, ids = z, open; break end
  end
  if not leads and #near > 0 then
    for _, z in ipairs(far) do
      local open = StillOpen(z.q)
      if #open > 0 then leads, ids = z, open; break end
    end
  end
  if leads then
    local one = #ids == 1
    return text .. "\n" .. Rules.Line("lines", one and "next_leads_one" or "next_leads", { zone = Mid(leads.n) }) .. " "
      .. Rules.Line("lines", one and "next_ask_one" or "next_ask"), leads, ids
  end
  local first = near[1] or far[1]
  local sv = D.Saved()
  sv.quips = sv.quips + 1
  return text .. "\n" .. Rules.Line("lines", "next_none", { zone = Mid(first.n) }) .. " "
    .. Rules.Pick("stay", sv.quips, { here = here }), nil, nil
end
function D.Dinged(level)
  local nx = D.NextTable()
  if not nx or type(nx.zones) ~= "table" then return end
  local told, zones = D.Saved().told, {}
  for _, z in ipairs(nx.zones) do
    if type(z) == "table" and z.m and z.n and (tonumber(z.lv) or 999) <= level and not told[z.m] then zones[#zones + 1] = z end
  end
  if #zones == 0 then return end
  local continent = ns.PlayerWorldPos()
  local here = nx.here and Plain(Call(GetZoneText)) == nx.here and nx.here or nil
  local text, leads, ids = D.NextWords(level, zones, continent, here, Plain(Call(UnitFactionGroup, "player")))
  local ask = { text = text, level = level, zones = zones,
                onShow = function() for _, z in ipairs(zones) do D.Saved().told[z.m] = true end end }
  if leads then
    ask.tip, ask.zone, ask.quests = Rules.Line("buttons", "zone_tip"), leads.m, ids
    ask.buttons = { replan = function() D.Replan(2, leads.m, ids, leads.n) end }
  end
  D.Ask("nextzone", ask)
end


D.classOffered, D.classAt = {}, nil
D.CLASS_EVERY = 5
function D.ClassLook(level)
  local now = D.Now()
  if D.classAt and now - D.classAt < D.CLASS_EVERY then return end
  D.classAt = now
  local nx = D.NextTable()
  local list = nx and type(nx.cq) == "table" and nx.cq or nil
  level = level or Plain(Call(UnitLevel, "player"))
  if not (list and level) or D.asks.classquest then return end
  local sv, g = D.Saved(), ns.GuideInfo()
  for _, c in ipairs(list) do
    local id = type(c) == "table" and tonumber(c.c)
    if id and (tonumber(c.lv) or 999) <= level and not sv.classq[id] and not D.classOffered[id]
       and not (g and g.key == "class:" .. id) and #StillOpen(c.q) > 0 then
      D.classOffered[id] = true
      local class = Plain(Call(UnitClass, "player")) or "class"
      local fill = { class = class, chain = c.n or "", unlocks = c.u }
      local text = Rules.Line("lines", (c.u and c.u ~= "") and "class_news" or "class_news_plain", fill) .. "\n"
        .. Rules.Line("lines", "class_ask")
      D.Ask("classquest", { text = text, chain = id, label = Rules.Line("buttons", "start"),
                            tip = Rules.Line("buttons", "class_tip"), closeTip = Rules.Line("buttons", "class_close_tip"),
                            buttons = { replan = function() sv.classq[id] = "started"; D.Replan(3, 0, { id }, c.n) end },
                            onClose = function() sv.classq[id] = "dismissed" end })
      return
    end
  end
end


function D.Replan(mode, zone, ids, zoneName)
  local sv = D.Saved()
  local was = type(sv.asked) == "table" and sv.asked.n or 0
  local g = ns.GuideInfo and ns.GuideInfo()
  sv.asked = { n = was % 255 + 1, mode = mode, zone = zone or 0, ids = ids or {}, at = D.Now(), v = g and g.version or 0 }
  D.quip.text, D.quip.held = nil, false
  ns.Print(mode == 2 and Rules.Line("lines", "replan_zone_asked", { zone = Mid(zoneName or "the next zone") })
    or mode == 3 and Rules.Line("lines", "class_asked", { chain = zoneName or "your class quest" })
    or Rules.Line("lines", "replan_asked"))
  D.Gone(true)
  D.Changed()
  if ns.CardRender then ns.CardRender() end
end


function D.Doing(s)
  local name = ns.Arbiter.Name(s) or s.text or ""
  if s.kind == "S" then return ((s.text or ""):gsub("^%u", string.lower)) end
  local has = s.npc and s.npc ~= ""
  if s.kind == "P" then return Rules.Line("phrases", has and "do_P" or "do_P_alone", { name = name, npc = s.npc }) end
  if s.kind == "T" then return Rules.Line("phrases", has and "do_T" or "do_T_alone", { name = name, npc = s.npc }) end
  return Rules.Line("phrases", s.kind == "D" and "do_D" or "do_O", { name = name })
end
function D.LeftLine(g)
  local s = g and g.cur and g.steps[g.cur]
  if not s then return nil end
  local G, nxt = ns.GUIDE, g.planCur and g.planCur ~= g.cur and g.steps[g.planCur] or nil
  for i = g.cur + 1, nxt and 0 or #g.steps do
    if g.state[i] == G.TODO or g.state[i] == G.WAIT then nxt = g.steps[i]; break end
  end
  local left = s.kind == "O" and ns.Arbiter.Begun(s) and ns.Arbiter.Left(s)
  local fill = { quest = ns.Arbiter.Name(s), n = left, doing = D.Doing(s), next = nxt and D.Doing(nxt) }
  if left then return Rules.Line("lines", nxt and "left_work" or "left_work_last", fill) end
  return Rules.Line("lines", nxt and "left_go" or "left_go_last", fill)
end
function D.KeepLeft(g)
  local text = D.LeftLine(g)
  if text then D.Saved().left = { key = g.key, text = text, at = D.Now(), step = ns.Trace.Key(g.steps[g.cur]) } end
end
function D.ShowLeft(g)
  if D.leftShown then return end
  D.leftShown = true
  local kept = D.Saved().left
  local lead = g.cur and ns.Trace.Key(g.steps[g.cur])
  if lead and type(kept) == "table" and kept.key == g.key and kept.text and (kept.step == nil or kept.step == lead) then
    D.left = { text = kept.text, till = D.Now() + Rules.director.left_for, lead = lead }
    D.Changed()
  end
end
function D.LeftNow(g)
  local l = D.left
  if not l then return nil end
  local lead = g and g.cur and ns.Trace.Key(g.steps[g.cur])
  if D.Now() > l.till or not lead or lead ~= l.lead then
    D.left = nil
    D.Changed()
    return nil
  end
  return l.text
end

D.quip = { shown = {}, last = nil, text = nil, at = nil, held = false }
local function QuipClock() return Plain(Call(GetTime)) or 0 end
local function QuipFill(t, facts)
  local missing = false
  local out = t:gsub("{(%w+)}", function(k)
    local v = facts[k]
    if v == nil or v == "" then missing = true; return "" end
    return tostring(v)
  end)
  return not missing and out or nil
end
D.QuipFill = QuipFill
function D.QuipPart(o)
  local text = type(o) == "table" and Plain(o.text)
  local done, need = type(o) == "table" and Plain(o.numFulfilled), type(o) == "table" and Plain(o.numRequired)
  if type(text) ~= "string" or Plain(o.finished) or type(done) ~= "number" or type(need) ~= "number" or done >= need then return nil end
  local thing = text:match("^%d+/%d+ (.+)$") or text:match("^(.-): %d+/%d+$")
  if not thing or thing == "" then return nil end
  return { done = done, need = need, thing = thing }
end
function D.QuipLog()
  local out = {}
  for i = 1, Plain(Call(C_QuestLog.GetNumQuestLogEntries)) or 0 do
    local info = Call(C_QuestLog.GetInfo, i)
    local id = type(info) == "table" and not Plain(info.isHeader) and not Plain(info.isHidden) and Plain(info.questID)
    local title = id and (Plain(info.title) or Plain(Call(C_QuestLog.GetTitleForQuestID, id)))
    if id and title and title ~= "" then
      local q = { id = id, title = title, complete = Plain(Call(C_QuestLog.IsComplete, id)) and true or false, parts = {} }
      for _, o in ipairs(ns.QuestObjectives(id)) do q.parts[#q.parts + 1] = D.QuipPart(o) end
      out[#out + 1] = q
    end
  end
  return out
end
function D.QuipMe()
  return { race = Plain(Call(UnitRace, "player")), cls = Plain(Call(UnitClass, "player")), zone = Plain(Call(GetZoneText)),
           log = D.QuipLog() }
end
function D.QuipsAboutYou(me)
  local Q, out, cls = ns.QuipLines, {}, me.cls and me.cls:lower() or ""
  local function Add(list, facts)
    for _, t in ipairs(list or {}) do out[#out + 1] = QuipFill(t, facts) end
  end
  if cls ~= "" then Add(Q.race[me.race or ""], { class = cls, classes = cls .. "s" }) end
  Add(Q.class[me.cls or ""], {})
  if me.zone and me.zone ~= "" then Add(Q.start[me.zone] or Q.zone, { zone = me.zone }) end
  return out
end
function D.QuipFinds(me, g)
  local Q, f = ns.QuipLines, { quest = {}, done = {}, part = {}, count = {}, helping = {}, handin = {} }
  local function Put(kind, facts) if #f[kind] < Q.each then f[kind][#f[kind] + 1] = facts end end
  local back = {}
  for _, s in ipairs(g and g.steps or {}) do
    local id = s.ids and s.ids[1]
    if s.kind == "T" and id and s.npc and s.npc ~= "" and not back[id] then back[id] = s.npc end
  end
  for _, q in ipairs(me.log or {}) do
    Put(q.complete and "done" or "quest", { quest = q.title })
    if not q.complete then for _, p in ipairs(q.parts) do Put("part", p) end end
    if back[q.id] then Put(q.complete and "handin" or "helping", { quest = q.title, npc = back[q.id] }) end
  end
  if #(me.log or {}) >= 2 then Put("count", { count = #me.log }) end
  return f
end
function D.QuipLines(me, g)
  local Q, finds, out = ns.QuipLines, D.QuipFinds(me, g), {}
  local function Add(s) if s then out[#out + 1] = s end end
  local facts = { class = me.cls and me.cls:lower() or "", zone = me.zone }
  Add(QuipFill(Q.doing.game[1], facts))
  for _, kind in ipairs(Q.uses.game) do
    local templates = Q.log[kind] or Q.found[kind]
    for k, found in ipairs(finds[kind] or {}) do
      if k > #templates then break end
      Add(QuipFill(templates[k], found))
    end
  end
  for k = 2, #Q.doing.game do Add(QuipFill(Q.doing.game[k], facts)) end
  for _, s in ipairs(D.QuipsAboutYou(me)) do Add(s) end
  return out
end
function D.QuipNext(lines)
  local q = D.quip
  if #lines == 0 then return nil end
  local fresh = {}
  for _, l in ipairs(lines) do if not q.shown[l] then fresh[#fresh + 1] = l end end
  if #fresh == 0 then
    q.shown = {}
    for _, l in ipairs(lines) do if #lines == 1 or l ~= q.last then fresh[#fresh + 1] = l end end
  end
  q.shown[fresh[1]] = true
  q.last = fresh[1]
  return fresh[1]
end
function D.Planning(g)
  local a = D.Saved().asked
  return type(a) == "table" and type(a.at) == "number" and D.Now() - a.at <= D.ASKED_FOR
    and (a.v or 0) == (g and g.version or 0)
end
function D.QuipNow(g)
  local q, Q = D.quip, ns.QuipLines
  if not D.Planning(g) then
    q.text, q.at, q.held, q.shown, q.last = nil, nil, false, {}, nil
    return nil
  end
  if q.held then return q.text end
  local now = QuipClock()
  if not q.text or now - (q.at or 0) >= Q.ms / 1000 then
    q.text = D.QuipNext(D.QuipLines(D.QuipMe(), g)) or q.text
    q.at = now
  end
  return q.text
end
function D.QuipHold(down)
  local q, Q = D.quip, ns.QuipLines
  if down then
    if q.text then q.held = true end
    return
  end
  if not q.held then return end
  q.held = false
  q.at = QuipClock() - Q.ms / 1000 + Q.resume / 1000
end

D.leftLine, D.quipHold = nil, nil
function ns.DirectorCardLine(lay, body)
  if not D.leftLine then
    D.leftLine = UI.Text(body, "GameFontHighlightSmall", C.cyan)
    D.leftLine:SetWordWrap(true)
    D.quipHold = CreateFrame("Frame", nil, body)
    D.quipHold:SetAllPoints(D.leftLine)
    D.quipHold:EnableMouse(true)
    D.quipHold:SetScript("OnMouseDown", function() D.QuipHold(true) end)
    D.quipHold:SetScript("OnMouseUp", function() D.QuipHold(false) end)
    D.quipHold:SetScript("OnLeave", function() D.QuipHold(false) end)
  end
  local g = ns.GuideInfo()
  local quip = D.QuipNow(g)
  local text = quip or D.LeftNow(g)
  D.quipHold:SetShown(quip ~= nil)
  if not text then return D.leftLine:Hide() end
  D.leftLine:SetText(text)
  lay.Place(D.leftLine, nil, 2)
  lay.Part()
end


function D.Look(g, d)
  D.working = d and d.won and d.won.kind == "progress" or false
  D.fighting = ns.InFight()
  if d and d.event then D.Break(d.event) end
  D.Counted(g)
  D.Picked(g)
  local continent, px, py = ns.PlayerWorldPos()
  D.OffLine(g, continent, px, py)
  D.Nudge()
  D.Rows(g)
  D.ShowLeft(g)
  D.KeepLeft(g)
  D.Tick()
end
function D.Second()
  local resting = Plain(Call(IsResting)) and true or false
  if resting and D.resting == false then D.Break("town") end
  D.resting = resting
  D.fighting = ns.InFight()
  D.ClassLook()
  D.Tick()
end
if C_Timer.NewTicker then C_Timer.NewTicker(1, function() pcall(D.Second) end) end

ns.On("PLAYER_XP_UPDATE", function() D.Xp() end)
ns.On("PLAYER_LEVEL_UP", function(_, level)
  level = tonumber(level) or Plain(Call(UnitLevel, "player"))
  if not level then return end
  D.Ask("levelup", { level = level, text = "" })
  D.Dinged(level)
  D.classAt = nil
  D.ClassLook(level)
end)
ns.On("QUEST_TURNED_IN", function(_, id)
  D.Reward()
  D.Break("handed_in")
  local g = ns.GuideInfo()
  if g and tonumber(id) then D.HandedIn(g, tonumber(id)) end
end)
ns.On({ "MERCHANT_SHOW", "TRAINER_SHOW" }, function()
  local g = ns.GuideInfo()
  if g then D.Served(g) end
end)
ns.On({ "PLAYER_REGEN_DISABLED", "PLAYER_REGEN_ENABLED" }, function(event)
  D.fighting = event == "PLAYER_REGEN_DISABLED"
  if D.open and not PAGE_ONLY[D.open.kind] then D.Draw() end
end)
ns.OnGuide(function(what)
  if what == "loaded" then
    local g = ns.GuideInfo()
    if g then D.Loaded(g) end
  end
end)
ns.On("PLAYER_ENTERING_WORLD", function(_, login, reload)
  if login or reload then D.leftShown, D.xp, D.resting = false, nil, nil end
  D.rewardAt = D.rewardAt or D.Now()
  D.Xp()
end)

function ns.EncodeDirector()
  local w = ns.NewWriter()
  w:u8(38)
  local sv, now = D.Saved(), D.Now()
  local brk = D.breakAt and now - D.breakAt <= Rules.director.break_for
  local dry = D.rewardAt and now - D.rewardAt >= Rules.director.dry
  local a = D.open
  local asked = type(sv.asked) == "table" and now - (sv.asked.at or 0) <= D.ASKED_FOR and sv.asked or nil
  local bg = ns.DrawerBackground and ns.DrawerBackground() or {}
  local left = D.left and D.LeftNow(ns.GuideInfo())
  local flags = (D.working and 1 or 0) + (D.fighting and 2 or 0) + (brk and 4 or 0) + (dry and 8 or 0) + (a and 16 or 0)
    + (asked and 64 or 0) + (#bg > 0 and 128 or 0)
  local at = #w.bytes + 1
  w:u8(flags)
  w:u16(math.floor(D.Points() * 10 + 0.5))
  if a then
    local zone = a.zone and a.quests and #a.quests > 0
    w:u8(a.id or 0)
    w:u8(KIND_CODE[a.kind] or 0)
    w:u8(((a.buttons and a.buttons.replan) and 1 or 0) + (zone and 2 or 0) + (a.chain and 4 or 0))
    w:u16(now - (a.shown or now))
    if zone then
      local n = math.min(#a.quests, D.ASKED_MOST)
      w:u16(a.zone); w:u8(n)
      for k = 1, n do w:u24(a.quests[k]) end
    end
    if a.chain then w:u24(a.chain) end
  end
  if asked then
    w:u8(asked.n); w:u8(asked.mode); w:u16(asked.zone or 0); w:u16(now - asked.at)
    local n = math.min(#(asked.ids or {}), D.ASKED_MOST)
    w:u8(n)
    for k = 1, n do w:u24(asked.ids[k]) end
  end
  if #bg > 0 then
    local n = math.min(#bg, D.BACKGROUND_MOST)
    w:u8(n)
    for k = 1, n do local b = bg[k]; w:u24(b.quest); w:u16(b.line); w:u16(b.have); w:u16(b.need) end
  end
  local room = ns.MAX_PAYLOAD - #w.bytes - 1
  if left and room >= D.LEFT_LEAST then
    w.bytes[at] = flags + 32
    w:str(left, math.min(D.LEFT_MOST, room))
  end
  return w.bytes
end
function ns.EncodeDirectorText()
  local a = D.open
  if not a or PAGE_ONLY[a.kind] then return nil end
  local w = ns.NewWriter()
  w:u8(39)
  w:u8(a.id or 0)
  local text = a.text or ""
  local most = ns.MAX_PAYLOAD - 4
  if #text > most then text = text:sub(1, most):gsub("[\192-\255][\128-\191]*$", "") end
  w:u16(#text)
  for i = 1, #text do w:u8(text:byte(i)) end
  return w.bytes
end
