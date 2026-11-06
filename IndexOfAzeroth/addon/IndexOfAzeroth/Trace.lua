-- The Index of Azeroth. Copyright 2026 Index Case <indexofazeroth@pm.me>. PolyForm Strict 1.0.0, see LICENSE.md.
local ADDON, ns = ...

local Dist = ns.Geo.Dist
local T = { KEEP = 40, SHOW = 5, ring = {}, last = nil }
ns.Trace = T

function T.Key(s)
  if s.extra then return "x:" .. table.concat(s.ids or {}, ",") end
  return string.format("%s:%s:%s", s.kind or "?", table.concat(s.ids or {}, ","), s.text or "")
end

function T.Stretch(g, from)
  local lengths, prev, n = {}, nil, 0
  for i = from or 1, #g.steps do
    local s = g.steps[i]
    if not s.own then
      n = n + 1
      if n > ns.Rules.run.steps + 1 then break end
      if s.wx then
        if prev and prev.inst == s.inst then lengths[#lengths + 1] = Dist(prev.wx, prev.wy, s.wx, s.wy) end
        prev = s
      end
    end
  end
  return ns.Rules.Run(lengths)
end

function T.Keep(r)
  local ring = T.ring
  ring[#ring + 1] = r
  while #ring > T.KEEP do table.remove(ring, 1) end
end

function ns.TraceLead(g, d)
  local key = d and d.won and d.won.key or "none"
  if T.last and T.last.key == key then return end
  local why = d and (d.line or d.said or ns.Rules.Say("trace_" .. tostring(d.rule))) or ns.Rules.Say("trace_stop")
  T.Keep({ at = time(), t = GetTime(), plan = g and g.version, rule = d and d.rule or "stop", why = why,
           run = d and d.run and math.floor(d.run + 0.5) or nil, event = d and d.event, won = d and d.won,
           over = d and d.over })
  T.last = { key = key, rule = d and d.rule or "stop" }
end

function T.Line(r)
  local function part(p)
    if not p then return "nothing" end
    return string.format("%s (tier %s%s)", p.text or "?", p.tier and tostring(p.tier) or "never",
      p.yards and string.format(", %d yd", p.yards) or "")
  end
  local when = (date or os.date)("%H:%M:%S", r.at or 0)
  return string.format("%s %s over %s: %s", when, part(r.won), part(r.over), r.why or "")
end

function T.Print(n)
  local ring, k = T.ring, math.max(1, math.floor(tonumber(n) or T.SHOW))
  if #ring == 0 then return ns.Print("The epic's lead hasn't changed yet, so the trace is empty.") end
  ns.Print(string.format("The epic's last %d lead changes, newest last:", math.min(k, #ring)))
  for i = math.max(1, #ring - k + 1), #ring do ns.Print(T.Line(ring[i])) end
end
ns.commands = ns.commands or {}
ns.commands.trace = function(rest) T.Print(rest ~= "" and rest or nil) end

function T.Load()
  local kept = type(IndexOfAzerothCharDB) == "table" and IndexOfAzerothCharDB.trace
  if type(kept) ~= "table" then return end
  T.ring = {}
  for _, r in ipairs(kept) do if type(r) == "table" then T.Keep(r) end end
  local newest = T.ring[#T.ring]
  if newest then T.last = { key = newest.won and newest.won.key or "none", rule = newest.rule } end
end
ns.On("PLAYER_LOGOUT", function()
  if type(IndexOfAzerothCharDB) ~= "table" then IndexOfAzerothCharDB = {} end
  IndexOfAzerothCharDB.trace = T.ring
end)
