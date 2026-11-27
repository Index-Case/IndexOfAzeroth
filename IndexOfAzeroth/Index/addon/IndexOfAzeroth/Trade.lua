-- The Index of Azeroth. Copyright 2026 Index Case <indexofazeroth@pm.me>. PolyForm Strict 1.0.0, see LICENSE.md.
local ADDON, ns = ...

local Plain, Call, PlainText, PlainNumber = ns.Plain, ns.Call, ns.PlainText, ns.PlainNumber
local UI = ns.UI
local C = UI.C
local LINES = ns.WordsOf("game.trade")
local function W(key, fill) return ns.Fill(LINES[key], fill) end
local function Counted(key, n, fill)
  local f = { n = n }
  for k, v in pairs(fill or {}) do f[k] = v end
  return W(n == 1 and LINES[key .. ".one"] and key .. ".one" or key, f)
end

local T = {}
ns.Trade = T

T.FORMAT = "A"
T.CHECK = "B"
T.HOURS = "C"
T.SUFFIX = "D"
T.WIDTH = 400
T.ICON = 28
T.PAD = 12
T.KEY_W = 72
T.ROOM = 0.6


local B64 = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-_"
local V = {}
for i = 1, 64 do V[B64:sub(i, i)] = i - 1 end
local ACTS = { b = "buy", p = "post", c = "cancel", v = "vendor" }
local SUFFIX, SUFFIX_LEN = ":", 3

local function Num(s, i, n)
  local v = 0
  for k = i, i + n - 1 do
    local d = V[s:sub(k, k)]
    if not d then return nil end
    v = v * 64 + d
  end
  return v
end

function T.Decode(text)
  text = strtrim(text or "")
  local format = text:sub(1, 1)
  if format ~= T.FORMAT and format ~= T.CHECK and format ~= T.HOURS and format ~= T.SUFFIX then
    return nil, V[format] and "format" or "bad"
  end
  local check = format ~= T.FORMAT
  local byHours = format == T.HOURS or format == T.SUFFIX
  local bySuffix = format == T.SUFFIX
  local stamp, part, of = text:sub(2, 3), V[text:sub(4, 4)], V[text:sub(5, 5)]
  if #stamp < 2 or not (V[stamp:sub(1, 1)] and V[stamp:sub(2, 2)] and part and of) or part < 1 or part > of then
    return nil, "bad"
  end
  local steps, i, scanned = {}, 6, nil
  if check then
    scanned = Num(text, 6, 5)
    if not scanned then return nil, "bad" end
    scanned, i = scanned > 0 and scanned * 60 or nil, 11
  end
  while i <= #text do
    local lead = text:sub(i, i)
    local act = ACTS[lead:lower()]
    if not act then return nil, "bad" end
    local idn = lead == lead:upper() and 3 or 4
    local item = Num(text, i + 1, idn)
    local at, suffix = i + 1 + idn, nil
    if bySuffix and text:sub(at, at) == SUFFIX then
      suffix = Num(text, at + 1, SUFFIX_LEN)
      if not suffix or suffix < 1 then return nil, "bad" end
      at = at + 1 + SUFFIX_LEN
    end
    local units, price = Num(text, at, 2), Num(text, at + 2, 5)
    local duration, floor, hours
    at = at + 7
    if act == "post" then
      duration = V[text:sub(at, at)]
      at = at + 1
      if check then
        floor = Num(text, at, 5)
        if not floor then return nil, "bad" end
        floor, at = floor > 0 and floor or nil, at + 5
      end
    elseif act == "buy" and byHours then
      hours = Num(text, at, 5)
      if not hours then return nil, "bad" end
      hours, at = hours > 0 and hours or nil, at + 5
    end
    if not (item and units and price) or item < 1 or units < 1 or price < 1
        or (act == "post" and not (duration and duration >= 1 and duration <= 3)) then
      return nil, "bad"
    end
    steps[#steps + 1] = { act = act, item = item, suffix = suffix, units = units, price = price, duration = duration,
      floor = floor, hours = hours }
    i = at
  end
  if #steps == 0 then return nil, "bad" end
  return { stamp = stamp, part = part, of = of, scanned = scanned, steps = steps }
end


local function Find(path)
  local v = _G
  for part in path:gmatch("[^%.]+") do
    if type(v) ~= "table" then return nil end
    local t = v
    v = Plain(Call(function() return t[part] end))
  end
  return v
end
T.Find = Find

local EVENTS = { "AUCTION_HOUSE_SHOW", "AUCTION_HOUSE_CLOSED", "COMMODITY_SEARCH_RESULTS_UPDATED",
  "ITEM_SEARCH_RESULTS_UPDATED", "COMMODITY_PRICE_UPDATED", "COMMODITY_PRICE_UNAVAILABLE", "COMMODITY_PURCHASE_SUCCEEDED",
  "COMMODITY_PURCHASE_FAILED", "AUCTION_HOUSE_PURCHASE_COMPLETED", "AUCTION_HOUSE_AUCTION_CREATED",
  "AUCTION_HOUSE_THROTTLED_SYSTEM_READY", "GET_ITEM_INFO_RECEIVED", "BAG_UPDATE_DELAYED" }
T.hears = {}

local NEEDS = {
  search = { "C_AuctionHouse.MakeItemKey", "C_AuctionHouse.SendSearchQuery", "COMMODITY_SEARCH_RESULTS_UPDATED",
    "ITEM_SEARCH_RESULTS_UPDATED" },
  commodities = { "C_AuctionHouse.GetNumCommoditySearchResults", "C_AuctionHouse.GetCommoditySearchResultInfo" },
  items = { "C_AuctionHouse.GetNumItemSearchResults", "C_AuctionHouse.GetItemSearchResultInfo" },
  buyCommodity = { "C_AuctionHouse.StartCommoditiesPurchase", "C_AuctionHouse.ConfirmCommoditiesPurchase",
    "C_AuctionHouse.CancelCommoditiesPurchase", "COMMODITY_PRICE_UPDATED" },
  buyItem = { "C_AuctionHouse.PlaceBid" },
  bags = { "C_Container.GetContainerNumSlots", "C_Container.GetContainerItemInfo", "ItemLocation.CreateFromBagAndSlot",
    "C_AuctionHouse.GetItemCommodityStatus" },
  postCommodity = { "C_AuctionHouse.PostCommodity" },
  postItem = { "C_AuctionHouse.PostItem" },
}
function T.Lacks(key)
  for _, need in ipairs(NEEDS[key]) do
    if need:find("^[A-Z_]+$") then
      if not T.hears[need] then return need end
    elseif type(Find(need)) ~= "function" then
      return need
    end
  end
end

local function Ah(name, ...)
  local ah = Find("C_AuctionHouse")
  return Call(ah and ah[name], ...)
end
local function Act(name, ...)
  local f = Find("C_AuctionHouse." .. name)
  return type(f) == "function" and pcall(f, ...) or false
end

function T.AtHouse()
  if T.open ~= nil then return T.open end
  local f = Find("AuctionHouseFrame")
  return f and Plain(Call(f.IsShown, f)) and true or false
end

local function Ready()
  local f = Find("C_AuctionHouse.IsThrottledMessageSystemReady")
  return type(f) ~= "function" or Plain(Call(f)) ~= false
end


function T.List()
  if not T.list and type(IndexOfAzerothCharDB) == "table" and type(IndexOfAzerothCharDB.trade) == "table" then
    T.list = IndexOfAzerothCharDB.trade
  end
  return T.list
end

function T.Paste(text)
  local got, why = T.Decode(text)
  if not got then return ns.Print(W(why == "format" and "paste.format" or "paste.bad")) end
  local list = T.List()
  if not (list and list.stamp == got.stamp and list.of == got.of) then
    list = { stamp = got.stamp, of = got.of, parts = {}, steps = {} }
  end
  list.scanned = got.scanned or list.scanned
  if not list.parts[got.part] then
    list.parts[got.part] = true
    for _, s in ipairs(got.steps) do
      s.part = got.part
      list.steps[#list.steps + 1] = s
    end
    local order = {}
    for i, s in ipairs(list.steps) do order[s] = i end
    table.sort(list.steps, function(a, b)
      if a.part ~= b.part then return a.part < b.part end
      return order[a] < order[b]
    end)
  end
  if type(IndexOfAzerothCharDB) == "table" then IndexOfAzerothCharDB.trade = list end
  T.Show(list)
end

function T.Command(text)
  if strtrim(text or "") ~= "" then return T.Paste(text) end
  if not T.List() then return ns.Print(W("paste.none")) end
  T.Show()
end


local function StepKey(step)
  return step.suffix and (step.item .. ":" .. step.suffix) or step.item
end

T.found = {}
T.wait = nil
T.said = setmetatable({}, { __mode = "k" })
local function Say(step, key, fill, warn) T.said[step] = { text = W(key, fill), warn = warn or nil } end

local function Field(t, k) return t and Plain(Call(function() return t[k] end)) end

local BonusText = ns.Auction.BonusText
local function Fits(suffix, link)
  if not suffix then return true end
  local text = PlainText(link)
  return text ~= nil and BonusText(text) == tostring(suffix)
end

local function ReadCommodities(id)
  local rows = {}
  for i = 1, PlainNumber(Ah("GetNumCommoditySearchResults", id)) or 0 do
    local r = Ah("GetCommoditySearchResultInfo", id, i)
    local price, units = PlainNumber(Field(r, "unitPrice")), PlainNumber(Field(r, "quantity"))
    local own = PlainNumber(Field(r, "numOwnerItems")) or 0
    if price and units and units - own > 0 then rows[#rows + 1] = { price = price, units = units - own } end
  end
  table.sort(rows, function(a, b) return a.price < b.price end)
  return rows
end

local function ReadItems(key, suffix)
  local rows, link = {}, nil
  for i = 1, PlainNumber(Ah("GetNumItemSearchResults", key)) or 0 do
    local r = Ah("GetItemSearchResultInfo", key, i)
    local l = suffix and Field(r, "itemLink")
    if Fits(suffix, l) then
      link = link or PlainText(l)
      local buyout, units, id = PlainNumber(Field(r, "buyoutAmount")), PlainNumber(Field(r, "quantity")),
        PlainNumber(Field(r, "auctionID"))
      if buyout and units and units > 0 and id and not Field(r, "containsOwnerItem") then
        rows[#rows + 1] = { price = buyout / units, units = units, buyout = buyout, id = id }
      end
    end
  end
  table.sort(rows, function(a, b) return a.price < b.price end)
  return rows, link
end

local function Refresh(gkey)
  local f = T.found[gkey]
  if not (f and f.kind) then return end
  if f.kind == "commodity" then
    local id = PlainNumber(Field(f.key, "itemID"))
    if id and not T.Lacks("commodities") then f.rows = ReadCommodities(id) end
  elseif not T.Lacks("items") then
    local rows, link = ReadItems(f.key, f.suffix)
    f.rows, f.link = rows, link or f.link
  end
end

local function UnderLimit(rows, limit)
  local units = 0
  for _, r in ipairs(rows or {}) do
    if r.price <= limit then units = units + r.units end
  end
  return units
end
local function CostOf(rows, n)
  local cost, left = 0, n
  for _, r in ipairs(rows) do
    local take = math.min(left, r.units)
    cost, left = cost + take * r.price, left - take
    if left <= 0 then return cost end
  end
end

local function Pick(rows, limit, left)
  local big
  for _, r in ipairs(rows or {}) do
    if r.price > limit then break end
    if r.units <= left then return r, big end
    big = big or r
  end
  return nil, big
end

local function Lower(step)
  local f = T.found[StepKey(step)]
  local r = f and f.rows and f.rows[1]
  if not (r and r.price < step.price) then return nil end
  local at = f.kind == "commodity" and math.floor(r.price) or math.ceil(r.price) - 1
  return { lowest = r.price, at = at, under = at < 1 or (step.floor ~= nil and at < step.floor) }
end
T.Lower = Lower


local function InBags(step)
  local first, single, units = nil, nil, 0
  for bag = 0, PlainNumber(Find("NUM_BAG_SLOTS")) or 4 do
    for slot = 1, PlainNumber(Call(C_Container.GetContainerNumSlots, bag)) or 0 do
      local info = Call(C_Container.GetContainerItemInfo, bag, slot)
      if PlainNumber(Field(info, "itemID")) == step.item and not Field(info, "isBound")
        and Fits(step.suffix, step.suffix and Field(info, "hyperlink")) then
        local n = PlainNumber(Field(info, "stackCount")) or 1
        units = units + n
        first = first or { bag, slot }
        if n == 1 then single = single or { bag, slot } end
      end
    end
  end
  return first, single, units
end
local function Location(at)
  local il = Find("ItemLocation")
  return at and il and Call(il.CreateFromBagAndSlot, il, at[1], at[2])
end
local COMMODITY, ITEM = 2, 1
local function Status(loc)
  local s = loc and PlainNumber(Ah("GetItemCommodityStatus", loc))
  if s and s == (Find("Enum.ItemCommodityStatus.Commodity") or COMMODITY) then return "commodity" end
  if s and s == (Find("Enum.ItemCommodityStatus.Item") or ITEM) then return "item" end
end


local function DropQuote()
  local w = T.wait
  if w and (w.what == "quote" or w.what == "asked") then
    Act("CancelCommoditiesPurchase")
    T.wait = nil
  end
end
T.DropQuote = DropQuote

function T.Search(step)
  if not T.AtHouse() or T.Lacks("search") or not Ready() then return end
  DropQuote()
  local key = Ah("MakeItemKey", step.item)
  if not key then return end
  local sorts = {}
  local order = Find("Enum.AuctionHouseSortOrder.Price")
  if order then sorts[1] = { sortOrder = order, reverseSort = false } end
  T.found[StepKey(step)] = { key = key, item = step.item, suffix = step.suffix, searching = true }
  if not Act("SendSearchQuery", key, sorts, false) then T.found[StepKey(step)] = nil end
  T.Render()
end

function T.Buy(step)
  local f, left = T.found[StepKey(step)], step.units - step.done
  if not T.AtHouse() or not (f and f.rows) or left <= 0 then return end
  if f.kind == "commodity" then
    if T.Lacks("buyCommodity") then return end
    local w = T.wait
    if w and w.what == "quote" and w.step == step then
      if Act("ConfirmCommoditiesPurchase", step.item, w.n) then
        T.wait = { step = step, what = "buy", n = w.n }
      else
        T.wait = nil
        Say(step, "note.buy-failed", nil, true)
      end
      return T.Render()
    end
    DropQuote()
    Refresh(StepKey(step))
    local n = math.min(left, UnderLimit(f.rows, step.price))
    local expect = n > 0 and CostOf(f.rows, n)
    if expect and Act("StartCommoditiesPurchase", step.item, n) then
      T.wait = { step = step, what = "asked", n = n, expect = expect }
      T.said[step] = nil
    end
    return T.Render()
  end
  if T.Lacks("buyItem") then return end
  DropQuote()
  Refresh(StepKey(step))
  local r = Pick(f.rows, step.price, left)
  if r and r.buyout <= step.price * r.units then
    if Act("PlaceBid", r.id, r.buyout) then
      T.wait = { step = step, what = "buy", n = r.units, auction = r.id }
      T.said[step] = nil
    else
      Say(step, "note.buy-failed", nil, true)
    end
  end
  T.Render()
end

function T.Post(step, lower)
  local f = T.found[StepKey(step)]
  if not T.AtHouse() or T.Lacks("bags") or step.units - step.done <= 0 or not (f and f.rows) then return end
  local price = step.price
  if lower then
    local low = Lower(step)
    if not low or low.under then return T.Render() end
    price = low.at
  end
  DropQuote()
  local first, single, units = InBags(step)
  local kind = Status(Location(first))
  local n, ok
  if kind == "commodity" and not T.Lacks("postCommodity") then
    n = math.min(step.units - step.done, units)
    ok = n > 0 and Act("PostCommodity", Location(first), step.duration, n, price)
  elseif kind == "item" and single and not T.Lacks("postItem") then
    n = 1
    ok = Act("PostItem", Location(single), step.duration, 1, nil, price)
  else
    return T.Render()
  end
  if ok then
    T.wait = { step = step, what = "post", n = n }
    T.said[step] = nil
  else
    Say(step, "note.post-failed", nil, true)
  end
  T.Render()
end


local function Done(step, n, said)
  step.done = math.min(step.units, (step.done or 0) + n)
  Say(step, said, { n = n })
end

local hear = {}
hear.AUCTION_HOUSE_SHOW = function() T.open = true end
hear.AUCTION_HOUSE_CLOSED = function()
  T.open, T.wait = false, nil
  wipe(T.found)
end
hear.COMMODITY_SEARCH_RESULTS_UPDATED = function(id)
  id = PlainNumber(id)
  local f = id and T.found[id]
  if not f then return end
  f.kind, f.searching = "commodity", nil
  Refresh(id)
end
hear.ITEM_SEARCH_RESULTS_UPDATED = function(key)
  local id = PlainNumber(Field(key, "itemID"))
  for gkey, f in pairs(T.found) do
    if f.key == key or (id and f.item == id) then
      f.kind, f.searching, f.key = "item", nil, key
      Refresh(gkey)
    end
  end
end
hear.COMMODITY_PRICE_UPDATED = function(_, total)
  local w = T.wait
  if not (w and w.what == "asked") then return end
  total = PlainNumber(total)
  if total and total <= w.expect then
    w.what = "quote"
    Say(w.step, "note.quoted", { total = ns.Coins(total), n = w.n })
  else
    Act("CancelCommoditiesPurchase")
    T.wait = nil
    Say(w.step, "note.refused", { total = ns.Coins(total or 0), n = w.n }, true)
    local f = T.found[StepKey(w.step)]
    if f then f.rows = nil end
  end
end
hear.COMMODITY_PRICE_UNAVAILABLE = function()
  local w = T.wait
  if not (w and w.what == "asked") then return end
  T.wait = nil
  Say(w.step, "note.no-price", nil, true)
end
hear.COMMODITY_PURCHASE_SUCCEEDED = function()
  local w = T.wait
  if not (w and w.what == "buy" and not w.auction) then return end
  T.wait = nil
  Done(w.step, w.n, "note.bought")
  Refresh(StepKey(w.step))
end
hear.COMMODITY_PURCHASE_FAILED = function()
  local w = T.wait
  if not (w and w.what == "buy" and not w.auction) then return end
  T.wait = nil
  Say(w.step, "note.buy-failed", nil, true)
end
hear.AUCTION_HOUSE_PURCHASE_COMPLETED = function(id)
  local w = T.wait
  if not (w and w.what == "buy") then return end
  id = PlainNumber(id)
  if w.auction and id ~= w.auction then return end
  T.wait = nil
  Done(w.step, w.n, "note.bought")
  local f = T.found[StepKey(w.step)]
  if f and f.rows and w.auction then
    for i, r in ipairs(f.rows) do
      if r.id == id then table.remove(f.rows, i) break end
    end
  end
end
hear.AUCTION_HOUSE_AUCTION_CREATED = function()
  local w = T.wait
  if not (w and w.what == "post") then return end
  T.wait = nil
  Done(w.step, w.n, "note.posted")
end
local function Nothing() end
hear.GET_ITEM_INFO_RECEIVED, hear.BAG_UPDATE_DELAYED, hear.AUCTION_HOUSE_THROTTLED_SYSTEM_READY = Nothing, Nothing, Nothing

local function Heard(event, ...)
  local ok, err = pcall(hear[event], ...)
  if not ok then ns.Report("Trade.lua:" .. event, err) end
  if T.win and T.win:IsShown() then
    ok, err = pcall(T.Render)
    if not ok then ns.Report("Trade.lua:Render", err) end
  end
end
local refused = ns.On(EVENTS, Heard) or {}
for _, e in ipairs(EVENTS) do
  T.hears[e] = not refused[e] or nil
end


local function VariantLink(step)
  local f = step.suffix and T.found[StepKey(step)]
  return f and f.link
end

local function Name(step)
  local id, suffix = step.item, step.suffix
  local plain = PlainText(Call(GetItemInfo, id))
  local link = VariantLink(step)
  local name = link and PlainText(Call(GetItemInfo, link)) or plain
  if name then
    if suffix and name == plain then return W("item.variant", { item = name }) end
    return name
  end
  Call(C_Item and C_Item.RequestLoadItemDataByID, id)
  return W("item.loading", { id = id })
end
local function Icon(id)
  return Plain(Call(C_Item and C_Item.GetItemIconByID, id)) or Plain(Call(GetItemIcon, id))
end
local DURATIONS = { "AUCTION_DURATION_ONE", "AUCTION_DURATION_TWO", "AUCTION_DURATION_THREE" }
local function Duration(d)
  return PlainText(Find(DURATIONS[d] or "")) or W("duration." .. d)
end

local function PostPlan(step)
  local lacks = T.Lacks("bags")
  if lacks then return nil, W("note.missing", { call = lacks }) end
  local first, single, units = InBags(step)
  if not first then return nil, W("note.no-bags") end
  local kind = Status(Location(first))
  if not kind then return nil, W("note.status-unknown") end
  lacks = T.Lacks(kind == "commodity" and "postCommodity" or "postItem")
  if lacks then return nil, W("note.missing", { call = lacks }) end
  if kind == "commodity" then return { kind = kind, n = math.min(step.units - step.done, units), at = first } end
  if not single then return nil, W("note.stacked") end
  return { kind = kind, n = 1, at = single }
end

function T.State(step)
  step.done = step.done or 0
  local left, item = step.units - step.done, Name(step)
  local verb = step.act
  local s = {}
  if left <= 0 then
    s.title = W(verb == "buy" and "step.bought" or "step.posted", { n = step.units, item = item })
  elseif step.done > 0 then
    s.title = W("step." .. verb .. ".part", { n = left, item = item, done = step.done })
  else
    s.title = W("step." .. verb, { n = left, item = item })
  end
  local price = ns.Coins(step.price)
  s.detail = verb == "buy" and W(step.hours and "detail.buy.hours" or "detail.buy", { limit = price, hours = step.hours })
    or verb == "post" and W("detail.post", { price = price, duration = Duration(step.duration) })
    or verb == "vendor" and W("detail.vendor", { price = price })
    or W("detail.cancel", { price = price })
  if verb == "vendor" then
    s.note = W("note.vendor")
    return s
  end
  s.actLabel = W("key." .. verb)
  if left <= 0 then
    s.note, s.done = W("note.done"), true
    return s
  end
  local here, ready = T.AtHouse(), Ready()
  local lackSearch = T.Lacks("search")
  s.search = here and ready and not lackSearch
  local f, w = T.found[StepKey(step)], T.wait
  local mine = w and w.step == step
  local seen
  if f and f.searching then
    seen = W("note.searching")
  elseif f and f.rows and #f.rows == 0 then
    seen = W("note.found.empty")
  elseif f and f.rows then
    local cheapest = ns.Coins(f.rows[1].price)
    local under = verb == "buy" and UnderLimit(f.rows, step.price) or 0
    seen = verb ~= "buy" and W("note.cheapest", { price = cheapest })
      or under > 0 and Counted("note.found", under, { price = cheapest })
      or W("note.found.none", { price = cheapest })
  end
  local why, info, alert
  local lacks
  if verb == "cancel" then
    why = W("note.cancel")
  elseif verb == "buy" then
    lacks = lackSearch or f and f.kind and (T.Lacks(f.kind == "commodity" and "commodities" or "items")
      or T.Lacks(f.kind == "commodity" and "buyCommodity" or "buyItem"))
    if lacks then
      why = W("note.missing", { call = lacks })
    elseif mine and w.what == "asked" then
      info = W("note.asking", { n = w.n })
    elseif mine and w.what == "quote" then
      s.actLabel, s.act = W("key.confirm"), here
    elseif mine and w.what == "buy" then
      info = W("note.buying")
    elseif not (f and (f.rows or f.searching)) then
      local said = T.said[step]
      if not (said and said.warn) then info = W("note.search-first") end
    elseif f.rows and f.kind == "commodity" then
      s.act = here and UnderLimit(f.rows, step.price) > 0
    elseif f.rows then
      local r, big = Pick(f.rows, step.price, step.units - step.done)
      s.act = here and r ~= nil
      if not r and big then why = W("note.stack-big", { q = big.units, n = left }) end
    end
    if not lacks and f and f.rows and not (mine and w.what ~= "asked") then
      local have = UnderLimit(f.rows, step.price)
      if have < left then
        if have > 0 then seen = W("note.cheapest", { price = ns.Coins(f.rows[1].price) }) end
        alert =have == 0 and Counted("note.counted.gone", left) or W("note.counted", { n = left, have = have })
        local list, now = T.List(), PlainNumber(Call(time))
        local age = list and list.scanned and now and math.max(0, math.floor((now - list.scanned) / 60))
        if age then
          alert = alert .. " " .. (age < 120 and Counted("note.scanned.minutes", age)
            or Counted("note.scanned.hours", math.floor(age / 60)))
        end
      end
    end
  elseif mine and w.what == "post" then
    info = W("note.posting")
  else
    local plan, whyNot = PostPlan(step)
    why = whyNot
    if plan and not (f and f.rows) then
      if not (f and f.searching) then info = W("note.search-post") end
    elseif plan then
      s.act = here and plan.n > 0
      local deposit = plan.kind == "commodity"
        and PlainNumber(Ah("CalculateCommodityDeposit", step.item, step.duration, plan.n))
        or plan.kind == "item" and PlainNumber(Ah("CalculateItemDeposit", Location(plan.at), step.duration, 1))
      if deposit then info = W("note.deposit", { coins = ns.Coins(deposit) }) end
      local low = Lower(step)
      if low then
        seen = nil
        local fill = { lowest = ns.Coins(low.lowest), price = price, at = ns.Coins(low.at),
          floor = ns.Coins(step.floor or 0) }
        if low.under then
          alert = W(step.floor and "note.lower.floor" or "note.lower", fill)
        else
          local match = f.kind == "commodity"
          s.lower, s.lowerLabel = here and plan.n > 0, W(match and "key.match" or "key.undercut")
          alert = W("note.lower", fill) .. " " .. W(match and "note.lower.match" or "note.lower.undercut", fill)
        end
      end
    end
  end
  if here and not ready then why = why or W("note.busy") end
  local said = T.said[step]
  local lines, parts = { said and said.text or false, seen or false, alert or false, info or false, why or false }, {}
  for _, p in ipairs(lines) do
    if p and p ~= "" then parts[#parts + 1] = p end
  end
  s.note = table.concat(parts, " ")
  s.warn = why ~= nil or alert ~= nil or (said and said.warn) or false
  return s
end


local rowsMade = {}

local function Key(parent, label, onClick)
  local b = UI.FlatButton(parent, label, T.KEY_W, onClick)
  function b:Lit(on)
    self:SetEnabled(on and true or false)
    self:SetAlpha(on and 1 or 0.4)
  end
  return b
end

local function Row(i)
  if rowsMade[i] then
    rowsMade[i]:Show()
    return rowsMade[i]
  end
  local r = CreateFrame("Frame", nil, T.scroll.child)
  r.icon = r:CreateTexture(nil, "ARTWORK")
  r.icon:SetSize(T.ICON, T.ICON)
  r.icon:SetPoint("TOPLEFT", r, "TOPLEFT", 0, -2)
  r.x = T.ICON + 8
  local w = T.WIDTH - 2 * T.PAD - r.x - 6
  r.title = UI.Text(r, "GameFontNormal", C.ivory)
  r.title:SetPoint("TOPLEFT", r, "TOPLEFT", r.x, 0)
  r.title:SetWidth(w)
  r.detail = UI.Text(r, "GameFontHighlightSmall", C.muted)
  r.detail:SetWidth(w)
  r.note = UI.Text(r, "GameFontHighlightSmall", C.muted)
  r.note:SetWidth(w)
  r.search = Key(r, W("key.search"), function() if r.step then T.Search(r.step) end end)
  r.act = Key(r, W("key.buy"), function()
    local st = r.step
    if st and st.act == "buy" then T.Buy(st) elseif st and st.act == "post" then T.Post(st) end
  end)
  r.lower = Key(r, W("key.undercut"), function()
    if r.step and r.step.act == "post" then T.Post(r.step, true) end
  end)
  r:EnableMouse(true)
  r:SetScript("OnEnter", function(self)
    if not self.step then return end
    Call(GameTooltip.SetOwner, GameTooltip, self, "ANCHOR_RIGHT")
    local link = VariantLink(self.step)
    if link then
      Call(GameTooltip.SetHyperlink, GameTooltip, link)
    else
      Call(GameTooltip.SetItemByID, GameTooltip, self.step.item)
    end
    Call(GameTooltip.Show, GameTooltip)
  end)
  r:SetScript("OnLeave", function() Call(GameTooltip.Hide, GameTooltip) end)
  rowsMade[i] = r
  return r
end
T.rows = rowsMade

local function Lay(r, step, y)
  local s = T.State(step)
  r.step, r.state = step, s
  r:ClearAllPoints()
  r:SetPoint("TOPLEFT", T.scroll.child, "TOPLEFT", 0, -y)
  r:SetWidth(T.WIDTH - 2 * T.PAD - 6)
  r.icon:SetTexture(Icon(step.item))
  r.icon:SetDesaturated(s.done and true or false)
  r.title:SetText(s.title)
  r.title:SetTextColor(unpack(s.done and C.muted or C.ivory))
  local h = math.ceil(r.title:GetStringHeight() or 14) + 2
  r.detail:ClearAllPoints()
  r.detail:SetPoint("TOPLEFT", r, "TOPLEFT", r.x, -h)
  r.detail:SetText(s.detail)
  h = h + math.ceil(r.detail:GetStringHeight() or 12) + 2
  r.note:ClearAllPoints()
  r.note:SetPoint("TOPLEFT", r, "TOPLEFT", r.x, -h)
  r.note:SetText(s.note)
  r.note:SetTextColor(unpack(s.warn and C.yellow or C.muted))
  r.note:SetShown(s.note ~= "")
  if s.note ~= "" then h = h + math.ceil(r.note:GetStringHeight() or 12) + 2 end
  local acts = step.act ~= "vendor"
  local keys = acts and { r.search, r.act } or {}
  if acts then
    r.act.label:SetText(s.actLabel)
    if s.lowerLabel then
      r.lower.label:SetText(s.lowerLabel)
      keys[3] = r.lower
    end
  end
  r.search:SetShown(acts)
  r.act:SetShown(acts)
  r.lower:SetShown(acts and s.lowerLabel ~= nil)
  local used = acts and UI.LayKeys(keys, r, r.x, h + 4, T.WIDTH - 2 * T.PAD - r.x - 6, T.KEY_W, 6, 28) + 24 or 0
  h = h + 4 + used
  r.search:Lit(acts and s.search and not s.done)
  r.act:Lit(acts and s.act and not s.done)
  r.lower:Lit(acts and s.lower and not s.done)
  r:SetHeight(h)
  return h + 10
end

local function Build()
  local win = CreateFrame("Frame", "IndexOfAzerothTrade", UIParent, "BackdropTemplate")
  UI.Panel(win)
  win:SetWidth(T.WIDTH)
  win:SetPoint("CENTER", UIParent, "CENTER", 320, 60)
  win:SetFrameStrata("HIGH")
  win:SetMovable(true)
  win:SetClampedToScreen(true)
  win:EnableMouse(true)
  win:RegisterForDrag("LeftButton")
  win:SetScript("OnDragStart", function(self) self:StartMoving() end)
  win:SetScript("OnDragStop", function(self)
    self:StopMovingOrSizing()
    local point, _, rel, x, y = Call(self.GetPoint, self)
    point, rel, x, y = PlainText(point), PlainText(rel), PlainNumber(x), PlainNumber(y)
    if point and rel and x and y and type(IndexOfAzerothCharDB) == "table" then
      IndexOfAzerothCharDB.tradeWindow = { point, rel, x, y }
    end
  end)
  win:SetScript("OnHide", function() DropQuote() end)
  local at = type(IndexOfAzerothCharDB) == "table" and IndexOfAzerothCharDB.tradeWindow
  if type(at) == "table" and at[1] and at[2] then
    win:ClearAllPoints()
    win:SetPoint(at[1], UIParent, at[2], at[3] or 0, at[4] or 0)
  end
  tinsert(UISpecialFrames, "IndexOfAzerothTrade")
  win.title = UI.Text(win, "GameFontNormalLarge", C.gold)
  win.title:SetPoint("TOPLEFT", win, "TOPLEFT", T.PAD, -T.PAD)
  win.title:SetText(W("title"))
  win.close = UI.FlatButton(win, W("close"), nil, function() win:Hide() end)
  UI.LayKeys({ win.close }, win, 0, 10, T.WIDTH, 60, 0, 24)
  win.close:ClearAllPoints()
  win.close:SetPoint("TOPRIGHT", win, "TOPRIGHT", -T.PAD, -10)
  win.head = UI.Text(win, "GameFontHighlightSmall", C.muted)
  win.head:SetPoint("TOPLEFT", win, "TOPLEFT", T.PAD, -42)
  win.head:SetWidth(T.WIDTH - 2 * T.PAD)
  T.scroll = UI.Scroller(win)
  T.scroll:SetWidth(T.WIDTH - 2 * T.PAD)
  T.scroll.child:SetWidth(T.WIDTH - 2 * T.PAD)
  T.win = win
  return win
end

function T.Render()
  local win, list = T.win, T.List()
  if not (win and list) then return end
  local left = 0
  for _, st in ipairs(list.steps) do
    if (st.done or 0) < st.units and st.act ~= "cancel" then left = left + 1 end
  end
  win.head:SetText(left == 0 and W("head.done")
    or not T.AtHouse() and W("head.closed") or Counted("head.left", left))
  local top = 42 + math.ceil(win.head:GetStringHeight() or 12) + 10
  T.scroll:ClearAllPoints()
  T.scroll:SetPoint("TOPLEFT", win, "TOPLEFT", T.PAD, -top)
  local y, stops = 0, { 0 }
  for i, st in ipairs(list.steps) do
    y = y + Lay(Row(i), st, y)
    stops[#stops + 1] = y
  end
  for i = #list.steps + 1, #rowsMade do rowsMade[i]:Hide() end
  local screen = PlainNumber(Call(UIParent.GetHeight, UIParent)) or 768
  local room = math.max(120, math.floor(screen * T.ROOM))
  T.scroll:Fit(y, stops, room)
  win:SetHeight(top + math.min(y, PlainNumber(Call(T.scroll.GetHeight, T.scroll)) or room) + T.PAD)
end

function T.Show(list)
  if list then
    for _, st in ipairs(list.steps or {}) do st.done = st.done or 0 end
    T.list = list
  end
  if not T.List() then return end
  if not T.win then Build() end
  T.win:Show()
  T.Render()
end

function T.Hide()
  if T.win then T.win:Hide() end
end
