-- The Index of Azeroth. Copyright 2026 Index Case <indexofazeroth@pm.me>. PolyForm Strict 1.0.0, see LICENSE.md.
local _, ns = ...
local Plain, Call, PlainNumber, PlainText = ns.Plain, ns.Call, ns.PlainNumber, ns.PlainText

local L = {}
ns.Ledger = L

local FRAME = 50
local WINDOW = 2
local KEEP = 3000
local COPIES = 2
local FLOOR = 10
local NAME_MOST = 24
local LONG_NAME = 48

local CAUSE = { stood = 0, loot = 1, quest = 2, vendor = 3, repair = 4, training = 5, flight = 6, unexplained = 7,
                auction = 8, mail = 9, trade = 10 }
local LOOT = { corpse = 1, alive = 2, object = 3, item = 4, share = 5, unknown = 6 }
local VENDOR = { sell = 1, buy = 2, buyback = 3 }
local REPAIR = { seen = 0, all = 1 }
local WHY = { none = 1, two = 2, unseen = 3 }
local AUCTION = { deposit = 1, buyout = 2, bid = 3, commodity = 4, cancel = 5 }
local MAIL = { sale = 1, refund = 2, player = 3, cod = 4, sent = 5, postage = 6, game = 7 }
local TRADE = { received = 1, given = 2, both = 3 }
local KIND = { post = 32, owned = 33, listed = 34, cancel = 35, notice = 36, mail = 37, take = 38 }
local WINDOWS = { merchant = 1, trainer = 2, taxi = 4, loot = 8, mail = 16, auction = 32, trade = 64 }
L.CAUSE, L.LOOT, L.VENDOR, L.REPAIR, L.WHY, L.WINDOWS, L.WINDOW = CAUSE, LOOT, VENDOR, REPAIR, WHY, WINDOWS, WINDOW
L.AUCTION, L.MAIL, L.TRADE, L.KIND, L.LONG_NAME = AUCTION, MAIL, TRADE, KIND, LONG_NAME

local open = {}
local closes = {}
local heard = {}
local pending = {}
local queue = {}
local rec, last
local sentAt = -math.huge
local buyback

local function DB()
  if type(IndexOfAzerothDB) ~= "table" then IndexOfAzerothDB = {} end
  if type(IndexOfAzerothDB.ledger) ~= "table" then IndexOfAzerothDB.ledger = {} end
  return IndexOfAzerothDB.ledger
end

local function Money() return PlainNumber(Call(GetMoney)) end

local function Reaches(w, at)
  return w ~= nil and w.at <= at + WINDOW and (w.shut == nil or w.shut >= at - WINDOW)
end

local function Opened(name, extra)
  local w = extra or {}
  w.at = GetTime()
  open[name] = w
end
local function Shut(name)
  if open[name] and not open[name].shut then open[name].shut = GetTime() end
end

local function Heard(kind, said)
  local now = GetTime()
  for i = #heard, 1, -1 do
    if heard[i].at < now - 4 * WINDOW then table.remove(heard, i) end
  end
  local e = said or {}
  e.kind, e.at = kind, now
  heard[#heard + 1] = e
  return e
end
L.Heard = Heard

local function Near(kinds, at)
  local out = {}
  for _, e in ipairs(heard) do
    if kinds[e.kind] and not e.used and math.abs(e.at - at) <= WINDOW then out[#out + 1] = e end
  end
  return out
end

local function Pick(list, d)
  for _, e in ipairs(list) do
    if e.price == math.abs(d) then return e end
  end
  return list[1]
end

local function Size(t)
  local n = 0
  for _ in pairs(t) do n = n + 1 end
  return n
end

local FAMILY = { buy = "buy", buyback = "buyback", shrink = "buyback", repairall = "repair", durability = "repair" }
local DETAILED = { buy = true, buyback = true, repairall = true }
local function VendorLoss(at, d)
  local list = Near(FAMILY, at)
  local families = {}
  for _, e in ipairs(list) do families[FAMILY[e.kind]] = true end
  if Size(families) > 1 then
    local priced = {}
    for _, e in ipairs(list) do if e.price == -d then priced[FAMILY[e.kind]] = true end end
    if Size(priced) ~= 1 then return "two" end
    families = priced
  end
  local family = next(families)
  if not family then return nil end
  local detailed, bare = {}, nil
  for _, e in ipairs(list) do
    if FAMILY[e.kind] == family then
      if DETAILED[e.kind] then detailed[#detailed + 1] = e elseif not bare then bare = e end
    end
  end
  local chosen = Pick(detailed, d)
  return family, chosen, { chosen, bare }
end

local SOLD, TRAIN, TAXI, QUEST, COIN = { sold = true }, { train = true }, { taxi = true }, { quest = true }, { coin = true }
local AUCTION_OUT, BOUGHT = { post = true, bid = true, cbuy = true, cancel = true }, { bought = true }
local MAIL_IN, MAIL_OUT = { mailmoney = true }, { cod = true, send = true }
local AUCTION_PART = { post = AUCTION.deposit, cbuy = AUCTION.commodity, cancel = AUCTION.cancel }

local function BidPart(ev, at)
  if ev.buyout then return AUCTION.buyout end
  for _, e in ipairs(Near(BOUGHT, at)) do
    if e.id2 and e.id2 == ev.id2 then
      e.used = true
      return AUCTION.buyout
    end
  end
  return AUCTION.bid
end

local function TradePart(w)
  local mine, theirs = w.player or 0, w.target or 0
  if mine > 0 and theirs > 0 then return TRADE.both end
  if theirs > 0 then return TRADE.received end
  if mine > 0 then return TRADE.given end
  return 0
end

function L.Windows(at)
  local bits = 0
  for name, bit in pairs(WINDOWS) do
    if Reaches(open[name], at) then bits = bits + bit end
  end
  return bits
end

function L.Cause(c)
  local at, d = c.at, c.d
  local found, n, taken = nil, 0, {}
  local function Seen(cause, sub, ev, name, used)
    n = n + 1
    ev = ev or {}
    found = { cause = cause, sub = sub, id = ev.id, id2 = ev.id2, count = ev.count, part = ev.part, name = name,
              bonus = ev.bonus }
    for _, e in pairs(used or {}) do taken[#taken + 1] = e end
  end
  local bid = d < 0 and Pick(Near(AUCTION_OUT, at), d)
  if bid then
    Seen(CAUSE.auction, bid.kind == "bid" and BidPart(bid, at) or AUCTION_PART[bid.kind], bid, nil, { bid })
  elseif Reaches(open.auction, at) then
    Seen(CAUSE.auction, 0, nil, nil, nil)
  end
  local mail = Pick(Near(d > 0 and MAIL_IN or MAIL_OUT, at), d)
  if mail then
    Seen(CAUSE.mail, mail.sub, mail, mail.name, { mail })
  elseif Reaches(open.mail, at) then
    Seen(CAUSE.mail, 0, nil, nil, nil)
  end
  if Reaches(open.trade, at) then
    local w = open.trade
    Seen(CAUSE.trade, TradePart(w), { part = w.target }, w.name, nil)
  end
  local vendor = open.merchant and open.merchant.name
  if d > 0 then
    local coin = Near(COIN, at)[1]
    local loot = open.loot
    if Reaches(loot, at) then
      Seen(CAUSE.loot, loot.kind or LOOT.unknown, loot, nil, { coin })
    elseif coin and closes.loot then
      Seen(CAUSE.loot, LOOT.share, nil, nil, { coin })
    end
    local quest = Pick(Near(QUEST, at), d)
    if quest then Seen(CAUSE.quest, nil, quest, nil, { quest }) end
    local sold = Pick(Near(SOLD, at), d)
    if Reaches(open.merchant, at) or sold then Seen(CAUSE.vendor, VENDOR.sell, sold, vendor, { sold }) end
  else
    local family, ev, used = VendorLoss(at, d)
    if family == "two" then
      n = n + 2
    elseif family == "repair" then
      Seen(CAUSE.repair, ev and ev.all and REPAIR.all or REPAIR.seen, nil, vendor, used)
    elseif family == "buyback" then
      Seen(CAUSE.vendor, VENDOR.buyback, ev, vendor, used)
    elseif family == "buy" or Reaches(open.merchant, at) then
      Seen(CAUSE.vendor, VENDOR.buy, ev, vendor, used)
    end
    local train = Pick(Near(TRAIN, at), d)
    if Reaches(open.trainer, at) or train then
      Seen(CAUSE.training, nil, train, open.trainer and open.trainer.name, { train })
    end
    local flight = Pick(Near(TAXI, at), d)
    if Reaches(open.taxi, at) or flight then Seen(CAUSE.flight, nil, flight, nil, { flight }) end
  end
  if n == 1 then
    for _, e in ipairs(taken) do e.used = true end
    return found
  end
  return { cause = CAUSE.unexplained, sub = n >= 2 and WHY.two or WHY.none, windows = L.Windows(at) }
end

local function Escaped(s)
  s = PlainText(s)
  if not s then return "" end
  return (s:gsub("[%%,\n]", { ["%"] = "%25", [","] = "%2C", ["\n"] = "%0A" }))
end
L.Escaped = Escaped

local TEXT = {
  [KIND.post] = { "P", "auction", "item", "bonus", "units", "buyout", "bid", "duration", "deposit", "commodity", "name" },
  [KIND.owned] = { "O", "auction", "item", "bonus", "units", "buyout", "bid", "left", "sold", "name" },
  [KIND.listed] = { "L", "ids" },
  [KIND.cancel] = { "C", "auction" },
  [KIND.notice] = { "N", "what", "auction", "from", "name" },
  [KIND.mail] = { "A", "what", "money", "bid", "buyout", "deposit", "cut", "units", "item", "bonus", "expires", "name",
                  "other" },
  [KIND.take] = { "T", "what", "item", "bonus", "units", "mail", "cod", "sender" },
}
local TEXTS = { name = true, other = true, sender = true }
local LISTS = { ids = true, bonus = true }

local function Text(e)
  if not e.kind then
    local out = { "M", e.seq, e.t, e.cause, e.sub or 0, e.d, e.b, e.id or "", e.windows or "", e.id2 or "",
                  e.count or "", e.part or "", Escaped(e.name) }
    if e.bonus then out[#out + 1] = #e.bonus > 0 and table.concat(e.bonus, ";") or "0" end
    return table.concat(out, ",")
  end
  local spec = TEXT[e.kind]
  local out = { spec[1], e.seq, e.t }
  for i = 2, #spec do
    local k, v = spec[i], e[spec[i]]
    if LISTS[k] then v = table.concat(v or {}, ";")
    elseif TEXTS[k] then v = Escaped(v)
    elseif v == true then v = 1
    elseif v == false then v = nil end
    out[#out + 1] = v == nil and "" or v
  end
  return table.concat(out, ",")
end
L.Text = Text

local function Add(e)
  if not rec then return end
  rec.seq = rec.seq + 1
  e.seq = rec.seq
  if e.b then rec.money = e.b end
  if not queue[1] then sentAt = math.max(sentAt, GetTime()) end
  local kept = rec.entries
  kept[#kept + 1] = Text(e)
  if #kept > KEEP + 100 then
    local trimmed = {}
    for i = #kept - KEEP + 1, #kept do trimmed[#trimmed + 1] = kept[i] end
    rec.entries = trimmed
  end
  queue[#queue + 1] = { entry = e, sent = 0 }
end
L.Add = Add

local function Decide(all)
  local now = GetTime()
  while pending[1] and (all or now >= pending[1].at + WINDOW) do
    local c = table.remove(pending, 1)
    local e = L.Cause(c)
    e.t, e.d, e.b = c.t, c.d, c.b
    Add(e)
  end
end
L.Decide = Decide

function L.Start()
  local money = Money()
  local key = ns.CharKey and ns.CharKey()
  if not money or not key or key == "" then return end
  local db = DB()
  rec = db[key]
  if type(rec) ~= "table" or type(rec.entries) ~= "table" then
    rec = { series = time(), seq = 0, entries = {} }
    db[key] = rec
  end
  rec.series, rec.seq = tonumber(rec.series) or time(), tonumber(rec.seq) or 0
  local was = tonumber(rec.money)
  if not was then
    Add({ t = time(), cause = CAUSE.stood, d = 0, b = money })
  elseif was ~= money then
    Add({ t = time(), cause = CAUSE.unexplained, sub = WHY.unseen, d = money - was, b = money })
  end
  last = money
end

local function MoneyChanged()
  if not rec then return end
  local money = Money()
  if not money or not last or money == last then return end
  pending[#pending + 1] = { at = GetTime(), t = time(), d = money - last, b = money }
  last = money
end

local function LootSource()
  local kinds, ids = {}, {}
  local target = PlainText(Call(UnitGUID, "target"))
  local alive = target and not Plain(Call(UnitIsDead, "target"))
  for slot = 1, PlainNumber(Call(GetNumLootItems)) or 0 do
    local sources = { Call(GetLootSourceInfo, slot) }
    for i = 1, #sources, 2 do
      local guid = PlainText(sources[i])
      local head, thing
      if guid then head, thing = guid:match("^(%a+)%-%d+%-%d+%-%d+%-%d+%-(%d+)%-") end
      local kind
      if head == "Creature" or head == "Vehicle" then kind = alive and guid == target and LOOT.alive or LOOT.corpse
      elseif head == "GameObject" then kind = LOOT.object
      elseif guid and guid:match("^Item%-") then kind = LOOT.item end
      if kind then kinds[kind] = true end
      if tonumber(thing) then ids[tonumber(thing)] = true end
    end
  end
  local kind, n, id, m = nil, 0, nil, 0
  for k in pairs(kinds) do kind, n = k, n + 1 end
  for k in pairs(ids) do id, m = k, m + 1 end
  return n == 1 and kind or LOOT.unknown, m == 1 and id or nil
end

local function NpcName() return PlainText(Call(UnitName, "npc")) end

local function Known(event)
  if C_EventUtils and C_EventUtils.IsEventValid then return Plain(Call(C_EventUtils.IsEventValid, event)) and true or false end
  local f = CreateFrame("Frame")
  local ok = pcall(f.RegisterEvent, f, event)
  if ok then pcall(f.UnregisterEvent, f, event) end
  return ok
end
L.Known = Known

local function ItemOf(link)
  link = PlainText(link)
  return link and tonumber(link:match("item:(%d+)"))
end

local backList = {}
local function ReadBuyback()
  wipe(backList)
  for i = 1, PlainNumber(Call(GetNumBuybackItems)) or 0 do
    local _, _, price, count = Call(GetBuybackItemInfo, i)
    backList[i] = { id = ItemOf(Call(GetBuybackItemLink, i)), count = PlainNumber(count), price = PlainNumber(price) }
  end
  return #backList
end
local repairCost

local taxiNodes, taxiFrom = {}, nil
local function ReadTaxi()
  wipe(taxiNodes)
  taxiFrom = nil
  if not (C_TaxiMap and C_TaxiMap.GetAllTaxiNodes) then return end
  local mapID = (GetTaxiMapID and PlainNumber(Call(GetTaxiMapID))) or (C_Map and PlainNumber(Call(C_Map.GetBestMapForUnit, "player")))
  local nodes = mapID and Call(C_TaxiMap.GetAllTaxiNodes, mapID)
  for _, n in ipairs(type(nodes) == "table" and nodes or {}) do
    local slot, id = PlainNumber(n.slotIndex), PlainNumber(n.nodeID)
    if slot and id then taxiNodes[slot] = id end
  end
  for slot, id in pairs(taxiNodes) do
    if PlainText(Call(TaxiNodeGetType, slot)) == "CURRENT" then taxiFrom = id end
  end
end

ns.On("PLAYER_ENTERING_WORLD", function() if not rec then L.Start() end end)
ns.On("PLAYER_MONEY", MoneyChanged)
ns.On("PLAYER_LOGOUT", function() Decide(true) end)
ns.On({ "MERCHANT_SHOW", "MERCHANT_CLOSED", "MERCHANT_UPDATE" }, function(event)
  if event == "MERCHANT_SHOW" then
    Opened("merchant", { name = NpcName() })
    buyback = ReadBuyback()
    repairCost = PlainNumber(Call(GetRepairAllCost))
  elseif event == "MERCHANT_CLOSED" then
    Shut("merchant")
  else
    local was = buyback
    buyback = ReadBuyback()
    if was and buyback < was then Heard("shrink") end
    repairCost = PlainNumber(Call(GetRepairAllCost)) or repairCost
  end
end)
ns.On("UPDATE_INVENTORY_DURABILITY", function()
  if open.merchant and not open.merchant.shut then Heard("durability") end
end)
ns.On({ "TRAINER_SHOW", "TRAINER_CLOSED" }, function(event)
  if event == "TRAINER_SHOW" then Opened("trainer", { name = NpcName() }) else Shut("trainer") end
end)
ns.On({ "TAXIMAP_OPENED", "TAXIMAP_CLOSED" }, function(event)
  if event == "TAXIMAP_OPENED" then Opened("taxi"); pcall(ReadTaxi) else Shut("taxi") end
end)

local function Hook(owner, name, fn)
  local function Safe(...) pcall(fn, ...) end
  if not hooksecurefunc then return false end
  if owner then
    return type(owner) == "table" and type(owner[name]) == "function" and pcall(hooksecurefunc, owner, name, Safe) or false
  end
  return type(_G[name]) == "function" and pcall(hooksecurefunc, name, Safe) or false
end
L.Hook = Hook

local lastUse = {}
local function Sold(bag, slot)
  if not (open.merchant and not open.merchant.shut) then return end
  bag, slot = PlainNumber(bag), PlainNumber(slot)
  if lastUse.bag == bag and lastUse.slot == slot and lastUse.at == GetTime() then return end
  lastUse.bag, lastUse.slot, lastUse.at = bag, slot, GetTime()
  local e = Heard("sold")
  local info = C_Container and Call(C_Container.GetContainerItemInfo, bag, slot)
  if type(info) ~= "table" then return end
  e.id, e.count = PlainNumber(info.itemID), PlainNumber(info.stackCount)
  local each = e.id and ns.SellPrice(PlainText(info.hyperlink) or e.id)
  e.price = each and e.count and each * e.count or nil
end

function L.Hooks()
  Hook(nil, "BuyMerchantItem", function(index, quantity)
    local e = Heard("buy")
    index, quantity = PlainNumber(index), PlainNumber(quantity)
    e.id = PlainNumber(Call(GetMerchantItemID, index))
    local _, _, price, lot = Call(GetMerchantItemInfo, index)
    price, lot = PlainNumber(price), PlainNumber(lot)
    e.count = quantity or lot
    e.price = price and (quantity and lot and lot > 0 and math.floor(price * quantity / lot) or price)
  end)
  Hook(nil, "BuybackItem", function(index)
    local e = Heard("buyback")
    local was = backList[PlainNumber(index) or 0]
    if was then e.id, e.count, e.price = was.id, was.count, was.price end
  end)
  Hook(C_Container, "UseContainerItem", Sold)
  if UseContainerItem ~= (C_Container and C_Container.UseContainerItem) then Hook(nil, "UseContainerItem", Sold) end
  Hook(nil, "RepairAllItems", function(guild)
    if Plain(guild) then return end
    local e = Heard("repairall")
    e.all = true
    local cost = PlainNumber(Call(GetRepairAllCost))
    e.price = cost and cost > 0 and cost or repairCost
  end)
  Hook(nil, "BuyTrainerService", function(index)
    local e = Heard("train")
    index = PlainNumber(index)
    local tip = C_TooltipInfo and Call(C_TooltipInfo.GetTrainerService, index)
    e.id = type(tip) == "table" and PlainNumber(tip.id) or nil
    e.price = PlainNumber(Call(GetTrainerServiceCost, index))
  end)
  Hook(nil, "TakeTaxiNode", function(slot)
    local e = Heard("taxi")
    slot = PlainNumber(slot)
    e.id, e.id2 = slot and taxiNodes[slot], taxiFrom
    e.price = PlainNumber(Call(TaxiNodeCost, slot))
  end)
end
L.Hooks()
ns.On({ "AUCTION_HOUSE_SHOW", "AUCTION_HOUSE_CLOSED" }, function(event)
  if event == "AUCTION_HOUSE_SHOW" then Opened("auction") else Shut("auction") end
end)
ns.On("MAIL_SHOW", function() Opened("mail") end)
ns.On("LOOT_OPENED", function()
  local kind, id = LootSource()
  Opened("loot", { kind = kind, id = id })
end)
ns.On("QUEST_TURNED_IN", function(_, id, _, money)
  money = PlainNumber(money)
  if money == 0 then return end
  Heard("quest", { price = money, id = PlainNumber(id) })
end)
local SPANS = { { "loot", "LOOT_OPENED", "LOOT_CLOSED" }, { "mail", "MAIL_SHOW", "MAIL_CLOSED" },
                { "trade", "TRADE_SHOW", "TRADE_CLOSED" } }
local function TradeMoney()
  local w = open.trade
  if not w or w.shut then return end
  pcall(function()
    w.player = PlainNumber(Call(GetPlayerTradeMoney)) or w.player
    w.target = PlainNumber(Call(GetTargetTradeMoney)) or w.target
    w.name = PlainText(Call(UnitName, "NPC")) or w.name
  end)
end
L.TradeMoney = TradeMoney
function L.Listen()
  for _, span in ipairs(SPANS) do
    local name, opens, shuts = span[1], span[2], span[3]
    if name == "trade" and Known(opens) then ns.On(opens, function() Opened("trade"); TradeMoney() end) end
    closes[name] = Known(shuts)
    if closes[name] then ns.On(shuts, function() Shut(name) end)
    elseif name ~= "trade" or Known(opens) then ns.On(opens, function() Shut(name) end) end
  end
  if Known("CHAT_MSG_MONEY") then ns.On("CHAT_MSG_MONEY", function() Heard("coin") end) end
  for _, event in ipairs({ "TRADE_MONEY_CHANGED", "TRADE_ACCEPT_UPDATE" }) do
    if Known(event) then ns.On(event, TradeMoney) end
  end
end
L.Listen()

ns.OnTick(CreateFrame("Frame"), ns.Word("game.ledger.error.tick"), 0.25, function()
  if pending[1] then Decide(false) end
end)


local function KeyHash(key)
  local h = 0
  for i = 1, #key do h = (h * 31 + key:byte(i)) % 65536 end
  return h
end
L.KeyHash = KeyHash

local function MoneyBody(w, e, most)
  local name = PlainText(e.name)
  local flags = (e.d < 0 and 1 or 0) + (e.id and 2 or 0) + (name and name ~= "" and 4 or 0) + (e.windows and 8 or 0)
                + (e.count and 16 or 0) + (e.id2 and 32 or 0) + (e.part and 64 or 0) + (e.bonus and 128 or 0)
  w:u8(flags)
  w:var(math.abs(e.d))
  w:var(e.b)
  if e.id then w:var(e.id) end
  if e.id2 then w:var(e.id2) end
  if e.count then w:var(e.count) end
  if e.part then w:var(e.part) end
  if e.windows then w:u8(e.windows) end
  if name and name ~= "" then w:str(name, most) end
  if e.bonus then
    w:var(#e.bonus)
    for i, b in ipairs(e.bonus) do w:var(i == 1 and b or b - e.bonus[i - 1]) end
  end
end

local BODY = {
  [KIND.post] = { "auction", "item", "units", "buyout", "bonus:ids", "bid", "deposit", "duration:u8", "commodity:flag",
                  "name:str" },
  [KIND.owned] = { "auction!", "units!", "sold:flag", "item", "buyout", "bonus:ids", "bid", "left", "commodity:flag",
                   "name:str" },
  [KIND.listed] = { "ids:ids!" },
  [KIND.cancel] = { "auction!" },
  [KIND.notice] = { "what:u8!", "auction", "from:u8", "name:str" },
  [KIND.mail] = { "what:u8!", "money!", "expires!", "bid", "buyout", "deposit", "cut", "units", "item", "bonus:ids",
                  "name:str", "other:str" },
  [KIND.take] = { "what:u8!", "item", "units", "bonus:ids", "mail", "cod:flag", "sender:str" },
}
local function Spec(f)
  local key, how = f:match("^(%w+):?(%w*)")
  return key, how ~= "" and how or "var", f:sub(-1) == "!"
end
L.BODY, L.Spec = BODY, Spec

local function EventBody(w, e)
  local fields, flags, bit = BODY[e.kind], 0, 1
  for _, f in ipairs(fields) do
    local key, how, always = Spec(f)
    if not always then
      if e[key] ~= nil and e[key] ~= false and not (how == "str" and (PlainText(e[key]) or "") == "") then flags = flags + bit end
      bit = bit * 2
    end
  end
  if bit > 256 then w:u16(flags) elseif bit > 1 then w:u8(flags) end
  bit = 1
  for _, f in ipairs(fields) do
    local key, how, always = Spec(f)
    local here = always or flags % (bit * 2) >= bit
    if not always then bit = bit * 2 end
    local v = e[key]
    if here and how == "var" then w:var(v or 0)
    elseif here and how == "u8" then w:u8(v or 0)
    elseif here and how == "str" then w:str(v, LONG_NAME)
    elseif here and how == "ids" then
      local ids = v or {}
      w:var(#ids)
      for i, id in ipairs(ids) do w:var(i == 1 and id or id - ids[i - 1]) end
    end
  end
end

local function Entry(w, e, base)
  local dt = e.t - base
  w:var(e.seq)
  w:var(dt >= 0 and dt * 2 or -dt * 2 - 1)
  if not e.kind and e.cause < 8 and not e.part then
    w:u8(e.cause + 8 * math.min(15, e.sub or 0))
    MoneyBody(w, e, NAME_MOST)
  elseif not e.kind then
    w:u8(128 + e.cause)
    w:u8(e.sub or 0)
    MoneyBody(w, e, LONG_NAME)
  else
    w:u8(128 + e.kind)
    EventBody(w, e)
  end
end
L.Entry = Entry

function ns.LedgerIdle()
  return queue[1] ~= nil and rec ~= nil
end

function ns.LedgerDue()
  return ns.LedgerIdle() and GetTime() - sentAt >= FLOOR
end

function ns.EncodeLedger()
  if not queue[1] or not rec then return nil end
  local key = ns.CharKey and ns.CharKey() or ""
  local w = ns.NewWriter()
  local base = queue[1].entry.t
  w:u8(FRAME); w:u16(KeyHash(key)); ns.WriteU32(w, rec.series); ns.WriteU32(w, base)
  local countAt = #w.bytes + 1
  w:u8(0)
  local n, again = 0, {}
  while queue[1] and n < 255 do
    local part = ns.NewWriter()
    Entry(part, queue[1].entry, base)
    if #w.bytes + #part.bytes > ns.MAX_PAYLOAD then
      if n == 0 then table.remove(queue, 1) else break end
    else
      for _, b in ipairs(part.bytes) do w.bytes[#w.bytes + 1] = b end
      local q = table.remove(queue, 1)
      q.sent = q.sent + 1
      if q.sent < COPIES then again[#again + 1] = q end
      n = n + 1
    end
  end
  for _, q in ipairs(again) do queue[#queue + 1] = q end
  if n == 0 then return nil end
  w.bytes[countAt] = n
  sentAt = GetTime()
  return w.bytes
end

L.queue, L.pending, L.open, L.heard = queue, pending, open, heard
function L.Record() return rec end
function L.Reset()
  wipe(queue); wipe(pending); wipe(open); wipe(heard)
  rec, last, sentAt, buyback = nil, nil, -math.huge, nil
end
