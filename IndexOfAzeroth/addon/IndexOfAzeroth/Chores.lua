-- The Index of Azeroth. Copyright 2026 Index Case <indexofazeroth@pm.me>. PolyForm Strict 1.0.0, see LICENSE.md.
local ADDON, ns = ...
local Plain, Call = ns.Plain, ns.Call

local R = { SOON = 6, HERE = 120, TRAIN_CLOSE = 150, TRAIN_HORIZON = 20, TRAIN_WITHIN = 8, BAGS_LOW = 2,
            DURABILITY_LOW = 25, FAR = 1e6, TIE = 1e-6, NEAR_MOST = 12 }
R.MERCHANT = { general = true, food = true, ammo = true, reagents = true, poisons = true, trade = true, bags = true,
               weaponvendor = true, armor = true, repair = true }
R.RESTOCK = { water = { "water", { food = true }, 10 }, ammo = { "ammo", { ammo = true }, 400 },
              ankh = { "Ankhs", { reagents = true }, 1 } }
R.RESTOCK.camp = { "wood for campfire kits", R.MERCHANT, ns.Rules.restock.camp_stock }
R.COUNTED = { camp = true }
R.KEEP = { train = true, bind = true, flightpath = true }
R.TODO_LINES = { ["restock:water"] = true, ["restock:ammo"] = true, ["restock:ankh"] = true, ["restock:camp"] = true,
                 repair = true }
R.HIDDEN_NAMES = { ["restock:water"] = "Buy water", ["restock:ammo"] = "Buy ammo", ["restock:ankh"] = "Buy Ankhs",
                   ["restock:camp"] = ns.Rules.Line("heads", "camp_restock"), repair = "Repair your gear" }
R.MADE_BY = { water = "Conjure Water" }
R.KINDS = { train = 1, sell = 2, repair = 4, restock = 8 }
R.MASK = 15
ns.ChoreRules = R


function R.Round(x)
  local f = math.floor(x)
  local d = x - f
  if d > 0.5 then return f + 1 elseif d < 0.5 then return f end
  return f % 2 == 0 and f or f + 1
end
function R.Sorted(list, key)
  local d = {}
  for k, e in ipairs(list) do d[k] = { key(e), k, e } end
  table.sort(d, function(a, b) if a[1] ~= b[1] then return a[1] < b[1] end return a[2] < b[2] end)
  local out = {}
  for k, x in ipairs(d) do out[k] = x[3] end
  return out
end
function R.Least(list, key)
  local best, bk = nil, nil
  for _, e in ipairs(list) do
    local k = key(e)
    if bk == nil or k < bk then best, bk = e, k end
  end
  return best
end
function R.Spot(s)
  return s and s.n and s.inst ~= nil and { s.inst, s.n, s.w } or nil
end
function R.Gap(a, b)
  if not a or not b then return R.FAR / 2 end
  if a[1] ~= b[1] then return R.FAR end
  local dn, dw = a[2] - b[2], a[3] - b[3]
  return math.sqrt(dn * dn + dw * dw)
end
function R.Around(steps, i, start)
  local prev, nxt = start, nil
  for k = i, 1, -1 do local p = R.Spot(steps[k]); if p then prev = p; break end end
  for k = i + 1, #steps do local p = R.Spot(steps[k]); if p then nxt = p; break end end
  return prev, nxt
end
function R.Detour(prev, at, nxt)
  return R.Gap(prev, at) + (nxt and (R.Gap(at, nxt) - R.Gap(prev, nxt)) or 0)
end
function R.Cheapest(steps, spots, lo, hi, start, ok)
  local best
  for i = lo, hi do
    local prev, nxt = R.Around(steps, i, start)
    for k, at in ipairs(spots) do
      if not ok or ok(i, k) then
        local c = R.Detour(prev, at, nxt)
        if not best or c < best[1] - R.TIE then best = { c, i, k } end
      end
    end
  end
  return best
end
function R.Insert(steps, i, s) table.insert(steps, i + 1, s) end
function R.InHand(steps, i)
  local before = i > 0 and steps[i] or nil
  local q = before and before.kind == "O" and before.quest or nil
  local j = i
  while q ~= nil and steps[j + 1] and steps[j + 1].kind == "O" and steps[j + 1].quest == q do j = j + 1 end
  if q ~= nil and steps[j + 1] and steps[j + 1].kind == "T" and steps[j + 1].quest == q then j = j + 1 end
  return j
end

R.placesKept = setmetatable({}, { __mode = "k" })
function R.Places(list, cats, side, detail, keep)
  local kept, ask
  if not keep and list then
    local names = {}
    for c in pairs(cats) do names[#names + 1] = c end
    table.sort(names)
    ask = table.concat(names, ",") .. "|" .. tostring(side) .. "|" .. tostring(detail)
    kept = R.placesKept[list] or {}
    R.placesKept[list] = kept
    if kept[ask] then return kept[ask] end
  end
  local out = R.Serving(list, cats, side, detail, keep)
  if kept then kept[ask] = out end
  return out
end
function R.Teaches(teaches, npc, spells)
  local has = teaches and teaches[npc]
  if not has then return true end
  for _, id in ipairs(spells or {}) do if not has[id] then return false end end
  return true
end
function R.Serving(list, cats, side, detail, keep)
  local found, standing = {}, {}
  for _, sv in ipairs(list or {}) do
    if not side or bit.band(sv.f or 3, side) ~= 0 then
      local kind
      for _, k in ipairs(sv.k or {}) do
        if cats[k[1]] and (detail == nil or k[2] == detail) then kind = k[1]; break end
      end
      if kind and (not keep or keep(sv, kind)) then
        found[#found + 1] = sv
        if not sv.w then for _, s in ipairs(sv.s) do standing[#standing + 1] = s end end
      end
    end
  end
  local out = {}
  for _, sv in ipairs(found) do
    for _, s in ipairs(sv.s) do
      local keepIt = true
      if sv.w then
        for _, t in ipairs(standing) do
          local dn, dw = t[2] - s[2], t[3] - s[3]
          if t[1] == s[1] and math.sqrt(dn * dn + dw * dw) <= sv.w then keepIt = false; break end
        end
      end
      if keepIt then
        out[#out + 1] = { name = sv.n, at = { s[1], s[2], s[3], sv.z, s[4] ~= 0 and s[4] or nil }, prices = sv.p or {}, id = sv.id }
      end
    end
  end
  return out
end
function R.NearRoute(places, spots)
  local have = {}
  for k = 1, #spots do if spots[k] then have[#have + 1] = spots[k] end end
  local list = places
  if #have > 0 then
    list = R.Sorted(places, function(p)
      local d = math.huge
      for _, s in ipairs(have) do d = math.min(d, R.Gap(s, p.at)) end
      return d
    end)
  end
  local out = {}
  for k = 1, math.min(R.NEAR_MOST, #list) do out[k] = list[k] end
  return out
end
function R.Fit(steps, lo, hi, places, anchor, make, ok)
  if lo <= 0 and anchor then
    local here = {}
    for _, p in ipairs(places) do
      if R.Gap(anchor, p.at) <= R.HERE and (not ok or ok(0, p)) then here[#here + 1] = p end
    end
    if #here > 0 then
      R.Insert(steps, 0, make(R.Least(here, function(p) return R.Gap(anchor, p.at) end)))
      return 0
    end
  end
  local window = { anchor or false }
  for k = math.max(0, lo - 1) + 1, math.min(math.min(hi, #steps) + 1, #steps) do window[#window + 1] = R.Spot(steps[k]) or false end
  local near = R.NearRoute(places, window)
  local spots = {}
  for k, p in ipairs(near) do spots[k] = p.at end
  local best = R.Cheapest(steps, spots, math.max(0, lo), math.min(hi, #steps), anchor,
                          ok and function(i, k) return ok(i, near[k]) end)
  if not best or best[1] >= R.FAR / 2 then return nil end
  R.Insert(steps, best[2], make(near[best[3]]))
  return best[2]
end
function R.FitPaid(steps, lo, hi, places, anchor, make, ok)
  local at = R.Fit(steps, lo, hi, places, anchor, make, ok)
  if at ~= nil then return at end
  local copy = {}
  for k, s in ipairs(steps) do copy[k] = s end
  if R.Fit(copy, lo, hi, places, anchor, function() return {} end) == nil then return nil, "far" end
  return nil, "short"
end
function R.Step(what, key, text, place, need, cost)
  return { kind = "S", what = what, key = key, text = text, npc = place.name, npcID = place.id, inst = place.at[1],
           n = place.at[2], w = place.at[3], z = place.at[4], map = place.at[5], need = need,
           cost = (cost and cost ~= 0) and R.Round(cost) or nil, own = true }
end

function R.Learnable(levels, known, race, upto)
  local have, byId, order = {}, {}, {}
  for lv in pairs(levels) do order[#order + 1] = lv end
  table.sort(order)
  for _, lv in ipairs(order) do for _, s in ipairs(levels[lv]) do byId[s.id] = s end end
  for id in pairs(known) do have[id] = true end
  for id in pairs(known) do
    local s = byId[id]
    while s and s.p and not have[s.p] do
      have[s.p] = true
      s = byId[s.p]
    end
  end
  local function raceOk(s)
    if not s.ra then return true end
    for _, b in ipairs(s.ra) do if b == race then return true end end
    return false
  end
  local function needOk(s)
    if not s.ne then return true end
    for _, id in ipairs(s.ne) do if have[id] then return true end end
    return false
  end
  local out = {}
  for _, lv in ipairs(order) do
    if lv > upto then break end
    for _, s in ipairs(levels[lv]) do
      if not have[s.id] and raceOk(s) and not s.x and not (s.p and not have[s.p]) and needOk(s) then
        out[#out + 1] = { lv, s }
      end
    end
  end
  return out
end
function R.Price(class, game)
  return function(lv, s)
    if game and game[s.id] then return game[s.id] end
    if s.c then return s.c end
    local n = 0
    for _, x in ipairs(class.levels[lv]) do if not x.ra and not x.ne then n = n + 1 end end
    return ((class.cost or {})[lv] or 0) / math.max(n, 1)
  end
end
function R.SpellWords(names)
  local n = #names
  if n <= 2 then return table.concat(names, " and ") end
  if n <= 4 then return table.concat(names, ", ", 1, n - 1) .. " and " .. names[n] end
  return table.concat(names, ", ", 1, 3) .. " and " .. (n - 3) .. " more"
end

function R.Training(steps, me, data, moneyAt, atLevel, anchor, skippedUpto, junk, notes)
  local class = data.trainers and data.trainers.classes and data.trainers.classes[me.class]
  if not class then return end
  local known, todo = {}, {}
  for id in pairs(me.known) do known[id] = true end
  while true do
    local more = {}
    for _, e in ipairs(R.Learnable(class.levels, known, me.race, me.level)) do
      if e[1] > skippedUpto and not known[e[2].id] then more[#more + 1] = e end
    end
    if #more == 0 then break end
    for _, e in ipairs(more) do todo[#todo + 1] = e; known[e[2].id] = true end
  end
  local trainers = R.Places(data.trainers.trainers, { class = true }, me.side, me.class)
  if #trainers == 0 or #todo == 0 then return end
  todo = R.Sorted(todo, function(e) return e[1] * 2 + (e[2].d and 0 or 1) end)
  local price = R.Price(class, me.prices)
  local listed, haveNow = {}, me.known

  local function offer(i)
    local out, ids, level = {}, {}, atLevel(i)
    for _, e in ipairs(todo) do
      local s = e[2]
      if not listed[s.id] and e[1] <= level and (not s.p or haveNow[s.p] or listed[s.p] or ids[s.p]) then
        out[#out + 1] = e
        ids[s.id] = true
      end
    end
    return out
  end
  local function teaches(place, spells)
    local ids = {}
    for k, e in ipairs(spells) do ids[k] = e[2].id end
    return R.Teaches(me.teaches, place.id, ids)
  end
  local function cheapestOf(o)
    local m
    for _, e in ipairs(o) do local p = price(e[1], e[2]); if not m or p < m then m = p end end
    return m
  end
  local function canPay(j)
    local o = offer(j)
    return #o > 0 and cheapestOf(o) <= moneyAt(j)
  end
  local function paysAll(j)
    local t = 0
    for _, e in ipairs(offer(j)) do t = t + price(e[1], e[2]) end
    return moneyAt(j) >= t
  end
  local function make(p) return R.Step("train", "train", "Train at " .. p.name, p, {}) end
  local function passing(lo, hi, want)
    for j = lo, math.min(hi, #steps) do
      if want(j) then
        local prev, nxt = R.Around(steps, j, anchor)
        local spells = offer(j)
        local by = {}
        for _, t in ipairs(trainers) do
          if teaches(t, spells) then
            local d = R.Gap(prev, t.at) + (nxt and (R.Gap(t.at, nxt) - R.Gap(prev, nxt)) or 0)
            if d <= R.TRAIN_CLOSE then by[#by + 1] = { d, t } end
          end
        end
        if #by > 0 then
          R.Insert(steps, j, make(R.Least(by, function(b) return b[1] end)[2]))
          return j
        end
      end
    end
    return nil
  end
  local sold, named = nil, false
  for _, s in ipairs(steps) do if s.what == "sell" and s.gain then sold = false end end
  if not (junk and junk > 0) then sold = false end
  local unplaced, any = false, false
  local i = 0
  while i <= #steps do
    if not canPay(i) then
      local o = offer(i)
      local again = false
      if sold == nil and #o > 0 and cheapestOf(o) <= moneyAt(i) + junk then
        local at = R.Fit(steps, i, i + R.TRAIN_WITHIN, R.Places(data.vendors, R.MERCHANT, me.side), anchor, function(p)
          local s = R.Step("sell", "sell", "Sell your junk at " .. p.name, p, { junk = true })
          s.gain = junk
          return s
        end)
        if at then sold, again = steps[at + 1], true end
      end
      if not again then i = i + 1 end
    else
      local spells = offer(i)
      local teachers = {}
      for _, t in ipairs(trainers) do if teaches(t, spells) then teachers[#teachers + 1] = t end end
      local where = R.Around(steps, i, anchor)
      local close = {}
      for _, t in ipairs(teachers) do if R.Gap(where, t.at) <= R.TRAIN_CLOSE then close[#close + 1] = t end end
      local at
      if #close > 0 then
        at = R.Fit(steps, i, R.InHand(steps, i), close, anchor, make, function(j) return canPay(j) end)
      else
        at = passing(i, i + R.TRAIN_HORIZON, function(j) return canPay(j) and paysAll(j) end)
        if at == nil then at = passing(i, i + R.TRAIN_HORIZON, canPay) end
        if at == nil then
          at = R.Fit(steps, i, i + R.TRAIN_WITHIN, teachers, anchor, make,
                     function(j, p) return canPay(j) and teaches(p, offer(j)) end)
        end
      end
      if at == nil then
        unplaced = true
        i = i + 1
      else
        spells = offer(at)
        local names, seen, ids, total, last, list = {}, {}, {}, 0, 0, {}
        for _, e in ipairs(spells) do
          local s, p = e[2], price(e[1], e[2])
          if not seen[s.n] then seen[s.n] = true; names[#names + 1] = s.n end
          ids[#ids + 1] = s.id
          total, last = total + p, math.max(last, e[1])
          list[#list + 1] = { name = s.n, rank = s.r, cost = R.Round(p) }
        end
        local have = math.max(moneyAt(at), 0)
        local what = R.SpellWords(names)
        local step = steps[at + 1]
        step.key, step.need, step.text = "train:" .. last, { spells = ids, level = last }, "Train at " .. step.npc .. ": " .. what
        step.why = ns.Rules.Say(#names == 1 and "train_way_one" or "train_way", { spells = what })
        step.spells = list
        if total ~= 0 then step.cost = R.Round(total) end
        if have < total then
          local prices, spend = {}, 0
          for _, e in ipairs(spells) do prices[#prices + 1] = price(e[1], e[2]) end
          table.sort(prices)
          for _, p in ipairs(prices) do
            if spend + p > have then break end
            spend = spend + p
          end
          step.short, step.spend = R.Round(have), R.Round(spend)
        end
        if sold and not named then
          for k = 1, at do
            if steps[k] == sold then
              sold.text = "Sell your junk at " .. sold.npc .. ", then train: " .. what
              named = true
              break
            end
          end
        end
        for _, id in ipairs(ids) do listed[id] = true end
        any = true
        i = at + 1
      end
    end
  end
  if sold and not named then
    for k = #steps, 1, -1 do if steps[k] == sold then table.remove(steps, k) end end
  end
  if not any and unplaced then
    notes[#notes + 1] = { what = "train", text = "No trainer of yours on this side of the world teaches " .. todo[1][2].n }
  elseif not any then
    local e = R.Least(todo, function(x) return price(x[1], x[2]) end)
    notes[#notes + 1] = { what = "train", text = "Training " .. e[2].n .. " costs " .. R.Coins(price(e[1], e[2]))
                                                 .. ", which is more than the plan's quests bring you" }
  end
end

function R.Coins(copper)
  copper = R.Round(copper)
  local g, s, c = math.floor(copper / 10000), math.floor(copper / 100) % 100, copper % 100
  local out = {}
  for _, v in ipairs({ { g, "g" }, { s, "s" }, { c, "c" } }) do if v[1] ~= 0 then out[#out + 1] = v[1] .. v[2] end end
  return #out > 0 and table.concat(out, " ") or "0c"
end
function R.RestockBuy(prices, thing, level, me)
  if thing == "ankh" then
    if prices.ankh == nil then return nil end
    return nil, prices.ankh
  end
  local kind, held = me.ammoKind, (me.grades or {})[thing] or 0
  local best
  for _, r in ipairs(prices[thing] or {}) do
    if held <= r[1] and r[1] <= level and (thing ~= "ammo" or not kind or r[4] == kind) then
      if not best or r[1] > best[1] or (r[1] == best[1] and r[2] < best[2]) then best = r end
    end
  end
  if not best then return nil end
  return best[3], best[2]
end
function R.RestockText(warning, item, npc)
  local name = item and ns.RestockItems and ns.RestockItems[item] or R.RESTOCK[warning][1]
  return ns.Word("both.restock.buy", { item = name, npc = npc })
end
function R.CampLow(me)
  return me.camps ~= nil and me.campWood ~= nil and me.camps < ns.Rules.restock.camp_low
end
function R.LowOn(me)
  local out = {}
  for _, w in ipairs(me.warnings or {}) do
    if R.RESTOCK[w] and not R.COUNTED[w] then out[#out + 1] = w end
  end
  if R.CampLow(me) then out[#out + 1] = "camp" end
  return out
end
function R.CampBuy(me, camp)
  if not R.CampLow(me) or not camp then return nil end
  local fire
  for _, f in ipairs(camp.fires or {}) do
    if tonumber(f[3]) == me.campWood then fire = f; break end
  end
  if not fire then return nil end
  local items, wood, tool = camp.items or {}, me.campWood, me.campTool
  local n = (ns.Rules.restock.camp_stock - me.camps) * tonumber(fire[4])
  local function Name(i) return items[i] and items[i].name or ("item " .. i) end
  local function Price(i) return items[i] and items[i].price or 0 end
  local words = tool and ns.Rules.Line("heads", "camp_wood_tool", { n = n, wood = Name(wood), tool = Name(tool) })
    or ns.Rules.Line("heads", "camp_wood", { n = n, wood = Name(wood) })
  local need = { items = { { wood, (me.campHave or 0) + n } } }
  if tool then need.items[2] = { tool, 1 } end
  return { wood = wood, n = n, tool = tool, items = tool and { wood, tool } or { wood }, words = words, need = need,
           cost = n * Price(wood) + (tool and Price(tool) or 0) }
end
function R.Sells(camp, npc, items)
  for _, i in ipairs(items) do
    local e = camp.items and camp.items[i]
    if not (e and e.sellers and e.sellers[npc]) then return false end
  end
  return #items > 0
end
function R.CampRestock(steps, me, data, anchor, moneyAt, notes)
  local buy = R.CampBuy(me, data.camp)
  if not buy then return end
  local sellers = R.Places(data.vendors, R.RESTOCK.camp[2], me.side, nil, function(sv) return R.Sells(data.camp, sv.id, buy.items) end)
  local _, why = R.FitPaid(steps, 0, R.SOON, sellers, anchor, function(p)
    return R.Step("restock", "restock:camp", ns.Rules.Line("heads", "camp_buy", { buy = buy.words, npc = p.name }), p, buy.need, buy.cost)
  end, function(i) return moneyAt(i) >= buy.cost end)
  if why == "short" and #sellers > 0 then
    notes[#notes + 1] = { what = "restock", text = ns.Rules.Line("heads", "camp_short",
      { buy = buy.words, cost = R.Coins(buy.cost), have = R.Coins(me.money or 0) }) }
  elseif why and #sellers > 0 then
    notes[#notes + 1] = { what = "restock", text = ns.Rules.Line("heads", "no_vendor", { thing = R.RESTOCK.camp[1] }) }
  end
end

function R.Makes(me, data, warning)
  local name = R.MADE_BY[warning]
  local class = data.trainers and data.trainers.classes and data.trainers.classes[me.class]
  if not name or not class then return false end
  for _, row in pairs(class.levels) do
    for _, s in ipairs(row) do if s.n == name and me.known[s.id] then return true end end
  end
  return false
end

function R.Plan(stepsIn, me, data, anchor)
  local steps, notes = {}, {}
  for k, s in ipairs(stepsIn) do steps[k] = s end
  local level, skipped, silenced = me.level or 1, me.skipped or {}, me.silenced or {}
  local function want(kind) return not me.only or me.only[kind] end
  local function gone(key)
    local lv = skipped[key]
    return lv ~= nil and (R.KEEP[key:match("^(%a+)")] == true or lv == level)
  end
  local function atLevel() return level end
  local function moneyAt(i)
    local m = me.money or 0
    for k = 1, i do
      local s = steps[k]
      if s.kind == "T" then m = m + (s.cash or 0)
      else m = m + (s.gain or 0) - ((s.spend ~= nil and s.spend or s.cost) or 0) end
    end
    return m
  end
  local junk = me.junkValue or 0
  local repair = want("repair") and me.durability ~= nil and me.durability <= R.DURABILITY_LOW and not gone("repair")
  local sell = want("sell") and me.bagFree ~= nil and me.bagFree <= R.BAGS_LOW and not gone("sell") and me.junk ~= 0
  if repair and silenced.repair then
    notes[#notes + 1] = { what = "repair", key = "repair", hidden = true, text = R.HIDDEN_NAMES.repair }
    repair = false
  end
  if repair and (me.money or 0) == 0 then
    notes[#notes + 1] = { what = "repair", text = "Your gear is worn and you have no money to repair it" }
    repair = false
  end
  if repair or sell then
    local what = repair and "repair" or "sell"
    local words = (sell and repair) and "Sell and repair" or sell and "Sell" or "Repair"
    local need = { durability = repair and (R.DURABILITY_LOW + 1) or nil, bags = sell and (R.BAGS_LOW + 1) or nil }
    R.Fit(steps, 0, R.SOON, R.Places(data.vendors, repair and { repair = true } or R.MERCHANT, me.side), anchor, function(p)
      local s = R.Step(what, what, words .. " at " .. p.name, p, need)
      if sell and junk ~= 0 then s.gain = junk end
      return s
    end)
  end
  for _, warning in ipairs(R.LowOn(me)) do
    local r = R.RESTOCK[warning]
    local key = "restock:" .. warning
    if r and not gone(key) and want("restock") and not R.Makes(me, data, warning) then
      if silenced[key] then
        notes[#notes + 1] = { what = "restock", key = key, hidden = true, text = R.HIDDEN_NAMES[key] }
      elseif R.COUNTED[warning] then
        R.CampRestock(steps, me, data, anchor, moneyAt, notes)
      else
        local thing, cats, units = r[1], r[2], r[3]
        local function price(prices, lv) return select(2, R.RestockBuy(prices, warning, lv, me)) end
        local sellers = R.Places(data.vendors, cats, me.side, nil, function(sv) return price(sv.p or {}, level) ~= nil end)
        local _, why = R.FitPaid(steps, 0, R.SOON, sellers, anchor, function(p)
          local item, each = R.RestockBuy(p.prices, warning, level, me)
          return R.Step("restock", key, R.RestockText(warning, item, p.name), p, { warning = { warning } }, each * units)
        end, function(i, p) return moneyAt(i) >= (price(p.prices, atLevel(i)) or 0) * units end)
        if why == "far" and #sellers > 0 then
          notes[#notes + 1] = { what = "restock", text = ns.Rules.Line("heads", "no_vendor", { thing = thing }) }
        elseif why then
          local cheapest
          for _, p in ipairs(sellers) do
            local v = price(p.prices, level)
            if v and (not cheapest or v < cheapest) then cheapest = v end
          end
          if cheapest then
            notes[#notes + 1] = { what = "restock", text = "Buying " .. units .. " " .. thing .. " costs " .. R.Coins(cheapest * units)
                                                          .. ", and you have " .. R.Coins(me.money or 0) }
          end
        end
      end
    end
  end
  local upto = 0
  for key in pairs(skipped) do
    local lv = tonumber(key:match("^train:(%d+)$"))
    if lv and lv > upto then upto = lv end
  end
  if want("train") and me.known then
    R.Training(steps, me, data, moneyAt, atLevel, anchor, upto,
               (want("sell") and not gone("sell") and me.junk ~= 0) and junk or 0, notes)
  end
  for _, s in ipairs(steps) do
    if s.own and s.need and s.need.level then s.min = s.need.level end
  end
  return steps, notes
end


local C = { dirty = false, since = 0, EVERY = 0.5 }
ns.Chores = C

local SIDE_BIT = { Alliance = 1, Horde = 2 }

function C.Saved()
  IndexOfAzerothDB = type(IndexOfAzerothDB) == "table" and IndexOfAzerothDB or {}
  local db = IndexOfAzerothDB
  db.trainerPrices = type(db.trainerPrices) == "table" and db.trainerPrices or {}
  db.trainerTeaches = type(db.trainerTeaches) == "table" and db.trainerTeaches or {}
  return db
end

function ns.ChoresTrainerSeen(npc, rows)
  local db = C.Saved()
  local list = npc and npc > 0 and (db.trainerTeaches[npc] or {}) or nil
  local have = {}
  for _, id in ipairs(list or {}) do have[id] = true end
  for _, r in ipairs(rows or {}) do
    db.trainerPrices[r[1]] = r[2]
    if list and not have[r[1]] then list[#list + 1] = r[1]; have[r[1]] = true end
  end
  if list then db.trainerTeaches[npc] = list end
  C.dirty, C.force, C.teaches = true, true, nil
end

function C.RaceBit(file, side)
  local r = ns.ClassTrainers and ns.ClassTrainers.races and ns.ClassTrainers.races[file or ""]
  if not r then return nil end
  if r[side or ""] then return r[side] end
  local only, n = nil, 0
  for _, b in pairs(r) do only, n = b, n + 1 end
  return n == 1 and only or nil
end

function C.Me()
  local st = ns.lastStatus
  local nums = st and st.nums or {}
  local class = Plain(select(3, Call(UnitClass, "player")))
  local side = Plain(Call(UnitFactionGroup, "player"))
  local raceFile = Plain(select(2, Call(UnitRace, "player")))
  local me = { level = Plain(Call(UnitLevel, "player")) or 1, class = class, side = SIDE_BIT[side or ""],
               money = Plain(Call(GetMoney)) or 0, bagFree = st and nums.bagFree or nil, durability = st and nums.durability or nil,
               junk = ns.bagJunk, junkValue = ns.bagJunkValue or 0, warnings = {},
               skipped = ns.GuideSaved and ns.GuideSaved().skippedErrands or {}, race = C.RaceBit(raceFile, side),
               known = {}, prices = C.Saved().trainerPrices, teaches = {}, silenced = {} }
  for _, w in ipairs(st and st.warns or {}) do me.warnings[#me.warnings + 1] = w.name end
  me.camps, me.campWood, me.campTool = nums.camps, nums.campWood, nums.campTool
  me.campHave = me.campWood and (Plain(Call(C_Item.GetItemCount, me.campWood, false, false)) or 0) or nil
  me.ammoKind = nums.ammoKind
  me.grades = { ammo = nums.ammoGrade or 0, water = nums.waterGrade or 0 }
  local quiet = type(IndexOfAzerothShared) == "table" and type(IndexOfAzerothShared.quiet) == "table" and IndexOfAzerothShared.quiet
  for key in pairs(quiet and type(quiet.chores) == "table" and quiet.chores or {}) do me.silenced[key] = true end
  local data = ns.ClassTrainers and ns.ClassTrainers.classes and ns.ClassTrainers.classes[class]
  for _, row in pairs(data and data.levels or {}) do
    for _, s in ipairs(row) do if C.Knows(s.id) then me.known[s.id] = true end end
  end
  me.teaches = C.Teaches()
  return me
end
function C.Teaches()
  if C.teaches then return C.teaches end
  C.teaches = setmetatable({}, { __index = function(out, npc)
    local ids = ns.ClassTrainers and ns.ClassTrainers.teaches and ns.ClassTrainers.teaches[npc]
    if not ids then return nil end
    local set = {}
    for _, id in ipairs(ids) do set[id] = true end
    for _, id in ipairs(C.Saved().trainerTeaches[npc] or {}) do set[id] = true end
    rawset(out, npc, set)
    return set
  end })
  return C.teaches
end
function C.Knows(id)
  return (Plain(Call(C_SpellBook and C_SpellBook.IsSpellKnown, id, 0)) or Plain(Call(IsSpellKnown, id))) and true or false
end

function C.Plain(s)
  return { kind = s.kind, inst = s.inst, n = s.wx, w = s.wy, cash = s.cash, cost = s.cost, spend = s.spend, gain = s.gain,
           what = s.what, key = s.key, need = s.need, quest = s.ids and s.ids[1], ref = s }
end

function C.Entry(s)
  return { k = "S", ids = {}, inst = s.inst, at = { s.n, s.w, s.z }, text = s.text, name = s.text, npc = s.npc, map = s.map,
           what = s.what, key = s.key, need = s.need, cost = s.cost, min = s.min, spend = s.spend, gain = s.gain, why = s.why }
end

function C.Open(g, i)
  local G = ns.GUIDE
  return g.state[i] ~= G.DONE and g.state[i] ~= G.SKIPPED
end

function C.Settle(g)
  local sv = ns.GuideSaved and ns.GuideSaved()
  for i, s in ipairs(g.steps) do
    if s.own and s.what == "train" and g.state[i] == ns.GUIDE.DONE and not s.settled then
      s.settled = true
      local level = s.need and s.need.level
      if sv and level and not sv.skippedErrands["train:" .. level] then
        for _, id in ipairs(s.need.spells or {}) do
          if not C.Knows(id) then
            sv.skippedErrands["train:" .. level] = Plain(Call(UnitLevel, "player")) or 0
            break
          end
        end
      end
    end
  end
end

function C.Key(g)
  local st = ns.lastStatus
  local parts = { Plain(Call(UnitLevel, "player")) or 0, Plain(Call(GetMoney)) or 0, ns.bagJunk or -1, ns.bagJunkValue or -1,
                  st and st.nums.bagFree or -1, st and st.nums.durability or -1, g.version or 0, #g.steps }
  for _, w in ipairs(st and st.warns or {}) do parts[#parts + 1] = w.name end
  parts[#parts + 1] = st and st.nums.camps or -1
  for i = 1, #g.steps do parts[#parts + 1] = g.state[i] or 9 end
  return table.concat(parts, ",")
end
function C.Decide()
  local g = ns.GuideInfo and ns.GuideInfo()
  if not g or not ns.GuidePutChore or not ns.ClassTrainers or not ns.Vendors then return 0 end
  local key = C.Key(g)
  if key == C.lastKey and not C.force then return 0 end
  C.lastKey, C.force = key, false
  C.Settle(g)
  local me = C.Me()
  local again, theirs = {}, false
  local function due(s) return s.own or (s.min or 0) <= me.level end
  for i, s in ipairs(g.steps) do
    if not s.extra and C.Open(g, i) and s.kind == "S" and s.what == "train" and due(s) then
      if s.own and (s.forLevel or 0) < me.level then again[#again + 1] = i elseif not s.own then theirs = true end
    end
  end
  if #again > 0 and not theirs then
    for i = #g.steps, 1, -1 do
      local s = g.steps[i]
      if s.own and C.Open(g, i) and (s.what == "train" or (s.need and s.need.junk)) then ns.GuideDropChore(i) end
    end
  end
  local only, skip, open = { train = true, sell = true, repair = true, restock = true }, {}, {}
  for i, s in ipairs(g.steps) do
    if not s.extra and C.Open(g, i) then
      open[#open + 1] = i
      if s.kind == "S" and s.what == "train" and due(s) then only.train = nil end
      if s.kind == "S" and (s.what == "sell" or s.what == "repair") then only.sell, only.repair = nil, nil end
      if s.kind == "S" and s.what == "restock" and s.key then skip[s.key] = true end
    end
  end
  local warnings = {}
  for _, w in ipairs(me.warnings) do if not skip["restock:" .. w] then warnings[#warnings + 1] = w end end
  if skip["restock:camp"] then me.camps = nil end
  me.warnings, me.only = warnings, only
  if not (only.train or only.sell or (#R.LowOn(me) > 0)) then return 0 end
  local steps = {}
  for k, i in ipairs(open) do steps[k] = C.Plain(g.steps[i]) end
  local c, x, y = ns.PlayerWorldPos()
  local out, notes = R.Plan(steps, me, { trainers = ns.ClassTrainers, vendors = ns.Vendors, camp = ns.CampList and ns.CampList() },
                            c and x and { c, x, y } or nil)
  g.ownNotes = notes
  local put = 0
  for k, s in ipairs(out) do
    if not s.ref then
      local before
      for j = k + 1, #out do if out[j].ref then before = out[j].ref; break end end
      local step = ns.GuidePutChore(before, C.Entry(s))
      if step then
        step.own, step.spells, step.short, step.npcID = true, s.spells, s.short, s.npcID
        step.forLevel = me.level
        put = put + 1
      end
    end
  end
  if put > 0 and ns.GuideEvaluate then ns.GuideEvaluate() end
  return put
end

function ns.ChoresLook() C.dirty, C.force = true, true end
C.frame = CreateFrame("Frame")
ns.OnTick(C.frame, "the chores", nil, function(_, dt)
  C.since = C.since + dt
  if not C.dirty or C.since < C.EVERY then return end
  C.since, C.dirty = 0, false
  C.Decide()
end)
ns.On({ "PLAYER_LEVEL_UP", "PLAYER_MONEY", "BAG_UPDATE_DELAYED", "UPDATE_INVENTORY_DURABILITY", "TRAINER_CLOSED",
        "MERCHANT_CLOSED" }, function() C.dirty = true end)
ns.On({ "LEARNED_SPELL_IN_SKILL_LINE", "SPELLS_CHANGED" }, function() C.dirty, C.force = true, true end)
if ns.OnGuide then ns.OnGuide(function(what) if what == "loaded" or what == "done" then C.dirty = true end end) end
C.statusRead = ns.StatusRead
function ns.StatusRead(...)
  C.dirty = true
  if C.statusRead then return C.statusRead(...) end
end

C.KIND_CODE, C.THING_CODE, C.CHORES_MOST = { train = 1, sell = 4, repair = 5, restock = 6 }, { water = 1, ammo = 2, ankh = 3, camp = 4 }, 6
function ns.ChoresCodes() return C.KIND_CODE end
function ns.EncodeChores()
  local g = ns.GuideInfo and ns.GuideInfo()
  if not g then return nil end
  local list = {}
  for i, s in ipairs(g.steps) do
    if s.own and C.KIND_CODE[s.what] and #list < C.CHORES_MOST then list[#list + 1] = i end
  end
  if #list == 0 then return nil end
  local w = ns.NewWriter()
  w:u8(#list)
  for _, i in ipairs(list) do
    local s, need = g.steps[i], g.steps[i].need or {}
    local thing = C.THING_CODE[(s.key or ""):match("^restock:(%a+)") or ""] or 0
    local flags = thing % 4 + (thing >= 4 and 64 or 0) + (need.junk and 4 or 0)
      + ((need.bags and need.durability) and 8 or 0) + (g.cur == i and 16 or 0)
      + ((ns.Arbiter and ns.Arbiter.PutOffWhy(s)) and 32 or 0)
    w:u8(C.KIND_CODE[s.what]); w:u8(flags); w:u16(ns.GuidePlanStep(i)); w:u8(g.state[i] or 0)
    w:u24(s.npcID or 0); w:u16(s.inst or 0)
    w:i16(math.floor((s.wx or 0) + 0.5)); w:i16(math.floor((s.wy or 0) + 0.5))
    w:var(s.cost or 0); w:u8(math.min(255, need.level or 0))
  end
  return w.bytes
end
