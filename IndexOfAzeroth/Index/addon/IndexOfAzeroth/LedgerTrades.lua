-- The Index of Azeroth. Copyright 2026 Index Case <indexofazeroth@pm.me>. PolyForm Strict 1.0.0, see LICENSE.md.
local _, ns = ...
local Call = ns.Call
local function Guarded(read)
  return function(v)
    local ok, x = pcall(read, v)
    if ok then return x end
  end
end
local Plain, PlainNumber, PlainText = Guarded(ns.Plain), Guarded(ns.PlainNumber), Guarded(ns.PlainText)
local L = ns.Ledger
local KIND, MAIL = L.KIND, L.MAIL

local T = {}
ns.LedgerTrades = T

local PAIR = 30
local TAKE_WAIT = 10
local MAIL_SAME = 300
local LISTED_MOST = 40
local LIST_LAG = 60
local ATTACHMENTS = 16

local NOTICE = { sold = 1, expired = 2, won = 3, outbid = 4, removed = 5, bid = 6 }
local MAILKIND = { sold = 1, pending = 2, won = 3, expired = 4, cancelled = 5, outbid = 6, player = 8, game = 9 }
local FROM = { event = 1, chat = 2, both = 3 }
T.NOTICE, T.MAILKIND, T.FROM = NOTICE, MAILKIND, FROM

local function AH(name) return C_AuctionHouse and C_AuctionHouse[name] end

local function State(key)
  local rec = L.Record()
  if not rec then return nil end
  if type(rec[key]) ~= "table" then rec[key] = {} end
  return rec[key]
end

local function LinkParts(link)
  link = PlainText(link)
  if not link then return nil end
  return tonumber(link:match("item:(%d+)")), T.Sorted(ns.ItemBonuses(link)), link:match("%[(.-)%]")
end

function T.Sorted(ids)
  if not ids or #ids == 0 then return nil end
  local out = {}
  for i, b in ipairs(ids) do out[i] = b end
  table.sort(out)
  return out
end
T.LinkParts = LinkParts

local function Pattern(fmt)
  fmt = PlainText(fmt)
  if not fmt or not fmt:find("%%s") then return nil end
  local p = fmt:gsub("%%s", "\1"):gsub("[%^%$%(%)%%%.%[%]%*%+%-%?]", "%%%0"):gsub("\1", "(.+)")
  return "^" .. p .. "$"
end
T.Pattern = Pattern

local function NameAndUnits(s)
  if not s then return nil end
  local name, n = s:match("^(.-) %((%d+)%)$")
  if name then return name, tonumber(n) end
  return s
end


local NOTICE_NAMES = { AuctionSold = "sold", AuctionExpired = "expired", AuctionWon = "won", AuctionOutbid = "outbid",
                       AuctionRemoved = "removed", BidPlaced = "bid" }
local LINES = { sold = "ERR_AUCTION_SOLD_S", expired = "ERR_AUCTION_EXPIRED_S", won = "ERR_AUCTION_WON_S",
                outbid = "ERR_AUCTION_OUTBID_S", removed = "ERR_AUCTION_REMOVED_S" }
local noticeOf
local linePatterns
local notices = {}

local function NoticeOf(v)
  if not noticeOf then
    noticeOf = {}
    local enum = Plain(Enum and Enum.AuctionHouseNotification)
    if type(enum) == "table" then
      for name, kind in pairs(NOTICE_NAMES) do
        local value = PlainNumber(Call(function() return enum[name] end))
        if value then noticeOf[value] = kind end
      end
    end
  end
  return noticeOf[PlainNumber(v) or -1]
end

local function LinePatterns()
  if not linePatterns then
    linePatterns = {}
    for kind, global in pairs(LINES) do
      local p = Pattern(_G[global])
      if p then linePatterns[#linePatterns + 1] = { kind = kind, pattern = p } end
    end
  end
  return linePatterns
end

local function NoticeHeard(kind, name, auction, from)
  local now = GetTime()
  for _, n in ipairs(notices) do
    if n.what == kind and n.from ~= from and n.from ~= FROM.both and (n.name == name or not n.name or not name)
       and math.abs(n.at - now) <= L.WINDOW then
      n.from, n.name, n.auction = FROM.both, n.name or name, n.auction or auction
      return n
    end
  end
  local n = { at = now, t = time(), what = kind, name = name, auction = auction, from = from }
  notices[#notices + 1] = n
  return n
end

function T.Notification(_, notification, text, auctionID)
  local kind = NoticeOf(notification)
  if not kind then return end
  text = PlainText(text)
  local name = text
  for _, p in ipairs(LinePatterns()) do
    local got = text and text:match(p.pattern)
    if got then name = got break end
  end
  NoticeHeard(kind, name ~= "" and name or nil, PlainNumber(auctionID), FROM.event)
end

function T.System(_, text)
  text = PlainText(text)
  if not text then return end
  for _, p in ipairs(LinePatterns()) do
    local got = text:match(p.pattern)
    if got then return NoticeHeard(p.kind, got, nil, FROM.chat) end
  end
end

local function WriteNotice(n)
  L.Add({ kind = KIND.notice, t = n.t, what = NOTICE[n.what], auction = n.auction, from = n.from, name = n.name })
end


local posts = {}

local function ItemAt(place)
  local id = PlainNumber(Call(C_Item and C_Item.GetItemID, place))
  local link = Call(C_Item and C_Item.GetItemLink, place)
  local lid, bonus, name = LinkParts(link)
  return id or lid, bonus, name
end

local function WritePost(p)
  for i, x in ipairs(posts) do if x == p then table.remove(posts, i) break end end
  L.Add({ kind = KIND.post, t = p.t, auction = p.auction, item = p.item, units = p.units, buyout = p.buyout, bonus = p.bonus,
          bid = p.bid, deposit = p.deposit, duration = p.duration, commodity = p.commodity, name = p.name })
  local owned = State("owned")
  if owned and p.auction then owned[p.auction] = (p.units or 0) .. ":0:0:" .. time() end
end

function T.Posted(commodity, confirm, place, duration, units, a, b)
  duration, units = PlainNumber(duration), PlainNumber(units)
  local item, bonus, name = ItemAt(place)
  local bid, buyout
  if commodity then
    local unit = PlainNumber(a)
    buyout = unit and units and unit * units
  else
    bid, buyout = PlainNumber(a), PlainNumber(b)
  end
  local last = posts[#posts]
  if confirm and last and not last.auction and last.item == item and last.units == units and last.buyout == buyout
     and GetTime() - last.at < PAIR then
    return
  end
  local deposit = commodity and PlainNumber(Call(AH("CalculateCommodityDeposit"), item, duration, units))
                  or PlainNumber(Call(AH("CalculateItemDeposit"), place, duration, units))
  local p = { at = GetTime(), t = time(), item = item, bonus = bonus, name = name, units = units, buyout = buyout,
              bid = bid and bid > 0 and bid or nil, duration = duration, deposit = deposit, commodity = commodity or nil }
  p.ev = L.Heard("post", { price = deposit, id = item, count = units })
  posts[#posts + 1] = p
end

function T.Created(_, auctionID)
  local id = PlainNumber(auctionID)
  for _, p in ipairs(posts) do
    if not p.auction and GetTime() - p.at < PAIR then
      p.auction = id
      if p.ev then p.ev.id2 = id end
      return WritePost(p)
    end
  end
  WritePost({ t = time(), auction = id })
end

local list

function T.TakeOwned(kept)
  local owned, A = State("owned"), ns.Auction
  if not owned or type(kept) ~= "table" or type(kept.list) ~= "table" then return end
  local now, active = {}, {}
  for _, o in ipairs(kept.list) do
    if o.id and o.id ~= 0 and o.q then
      local sold = bit.band(o.flags or 0, A.OWNED_SOLD) ~= 0
      local commodity = bit.band(o.flags or 0, A.OWNED_COMMODITY) ~= 0 or nil
      local was = owned[o.id]
      local units, wasSold, seen = (was or ""):match("^(%d+):(%d):(%d)")
      local left = not sold and o.left and o.left > 0 and math.floor(o.left / 60) or nil
      if not was then
        L.Add({ kind = KIND.owned, t = time(), auction = o.id, units = o.q, sold = sold or nil, item = o.item,
                buyout = o.buy and o.buy > 0 and o.buy or nil, bonus = T.Sorted(o.bonuses),
                bid = o.bid and o.bid > 0 and o.bid or nil, left = left, commodity = commodity, name = o.name })
      elseif seen ~= "1" or tonumber(units) ~= o.q or (wasSold == "1") ~= sold then
        L.Add({ kind = KIND.owned, t = time(), auction = o.id, units = o.q, sold = sold or nil, left = left })
      end
      now[o.id] = o.q .. ":" .. (sold and 1 or 0) .. ":1"
      if not sold then active[#active + 1] = o.id end
    end
  end
  for id, v in pairs(owned) do
    local at = tonumber(type(v) == "string" and v:match("^%d+:0:0:(%d+)$"))
    if not now[id] and at and time() - at < LIST_LAG then now[id] = v end
  end
  local rec = L.Record()
  rec.owned = now
  table.sort(active)
  list = { t = time(), ids = active }
end

function T.WriteListed()
  if not list then return end
  local ids = list.ids
  for from = 1, math.max(1, #ids), LISTED_MOST do
    local part = {}
    for i = from, math.min(#ids, from + LISTED_MOST - 1) do part[#part + 1] = ids[i] end
    L.Add({ kind = KIND.listed, t = list.t, ids = part })
  end
  list = nil
end

local function Units(key, auction)
  for i = 1, PlainNumber(Call(AH("GetNumItemSearchResults"), key)) or 0 do
    local r = Call(AH("GetItemSearchResultInfo"), key, i)
    local id, units = Call(function() return PlainNumber(r.auctionID), PlainNumber(r.quantity) end)
    if id == auction then return units end
  end
end

function T.Bid(auctionID, amount)
  local id = PlainNumber(auctionID)
  amount = PlainNumber(amount)
  local e = L.Heard("bid", { price = amount, id2 = id })
  local info = Call(AH("GetAuctionInfoByID"), id)
  if type(info) ~= "table" then return end
  local buyout, link, key = Call(function() return PlainNumber(info.buyoutAmount), info.itemLink, Plain(info.itemKey) end)
  local item, bonus = LinkParts(link)
  e.id = item or (type(key) == "table" and PlainNumber(Call(function() return key.itemID end)) or nil)
  e.bonus = item and (bonus or {}) or nil
  e.buyout = buyout and amount and amount >= buyout or nil
  e.count = type(key) == "table" and Units(key, id) or nil
end


local SUBJECTS = { expired = "AUCTION_EXPIRED_MAIL_SUBJECT", cancelled = "AUCTION_REMOVED_MAIL_SUBJECT",
                   outbid = "AUCTION_OUTBID_MAIL_SUBJECT", sold = "AUCTION_SOLD_MAIL_SUBJECT", won = "AUCTION_WON_MAIL_SUBJECT" }
local INVOICE = { seller = "sold", seller_temp_invoice = "pending", buyer = "won" }
local subjects
local inbox = {}
local takes = {}

local function Subjects()
  if not subjects then
    subjects = {}
    for what, global in pairs(SUBJECTS) do
      local p = Pattern(_G[global])
      if p then subjects[#subjects + 1] = { what = what, pattern = p } end
    end
  end
  return subjects
end

local function Attachments(i, has)
  local items = {}
  if not has then return items end
  for a = 1, PlainNumber(ATTACHMENTS_MAX_RECEIVE) or ATTACHMENTS do
    local item, bonus = LinkParts(Call(GetInboxItemLink, i, a))
    if item then
      local r = { Call(GetInboxItem, i, a) }
      local units = PlainNumber(r[2]) == item and PlainNumber(r[4]) or PlainNumber(r[3])
      items[a] = { item = item, bonus = bonus, units = units or 1 }
    end
  end
  return items
end

function T.ReadMail(i)
  local h = { Call(GetInboxHeaderInfo, i) }
  local sender, subject = PlainText(h[3]), PlainText(h[4])
  if not sender or not subject or subject == "" then return nil end
  local m = { sender = sender, subject = subject, money = PlainNumber(h[5]) or 0, cod = PlainNumber(h[6]) or 0,
              expires = time() + math.floor((PlainNumber(h[7]) or 0) * 86400) }
  m.items = Attachments(i, Plain(h[8]))
  local what, name, said
  for _, s in ipairs(Subjects()) do
    local got = subject:match(s.pattern)
    if got then what, said = s.what, got break end
  end
  local inv = { Call(GetInboxInvoiceInfo, i) }
  local invoice = INVOICE[PlainText(inv[1]) or ""]
  if invoice then
    what, name, m.other = invoice, PlainText(inv[2]), PlainText(inv[3])
    m.bid, m.buyout, m.deposit, m.cut, m.units = PlainNumber(inv[4]), PlainNumber(inv[5]), PlainNumber(inv[6]),
                                                 PlainNumber(inv[7]), PlainNumber(inv[11])
  end
  local _, first = next(m.items)
  if what then
    local saidName, units = NameAndUnits(said)
    m.name = NameAndUnits(name) or saidName
    m.units = m.units or units or (first and first.units)
    m.item, m.bonus = first and first.item, first and first.bonus
    m.what, m.auction = MAILKIND[what], true
  else
    m.what = Plain(h[12]) and MAILKIND.player or MAILKIND.game
  end
  m.id = table.concat({ sender, subject, m.auction and table.concat({ m.money, m.bid or "", m.buyout or "",
                        m.deposit or "", m.cut or "", m.units or "" }, ":") or "" }, "|")
  return m
end

local function Nearest(mails, id, expires, taken)
  local best, by
  for k, m in pairs(mails) do
    local off = math.abs(m.expires - expires)
    if m.id == id and off <= MAIL_SAME and not (taken and taken[k]) and (not by or off < by) then best, by = k, off end
  end
  return best
end

local function UnitsOf(m, item)
  local n = 0
  for _, x in pairs(m and m.items or {}) do if x.item == item then n = n + (x.units or 1) end end
  return n
end

function T.ReadInbox()
  local kept = State("mails")
  if not kept then return end
  local n, total = Call(GetInboxNumItems)
  n, total = PlainNumber(n) or 0, PlainNumber(total)
  local now, partial = {}, total ~= nil and total > n
  for i = 1, n do
    local ok, m = pcall(T.ReadMail, i)
    if ok and m then now[i] = m else partial = true end
  end
  local matched, fresh = {}, {}
  for i = 1, n do
    local m = now[i]
    if m and m.auction then
      local k = Nearest(kept, m.id, m.expires, matched)
      if k then
        matched[k], m.seq = true, kept[k].seq
      else
        local e = { kind = KIND.mail, t = time(), what = m.what, money = m.money, expires = math.floor(m.expires / 60),
                    bid = m.bid, buyout = m.buyout, deposit = m.deposit, cut = m.cut, units = m.units, item = m.item,
                    bonus = m.bonus, name = m.name, other = m.other }
        L.Add(e)
        m.seq = e.seq
      end
      fresh[#fresh + 1] = { id = m.id, expires = m.expires, seq = m.seq }
    end
  end
  for k, m in ipairs(kept) do
    if partial and not matched[k] and m.expires > time() then fresh[#fresh + 1] = m end
  end
  L.Record().mails = fresh
  for i = #takes, 1, -1 do
    local tk = takes[i]
    local k = Nearest(now, tk.id, tk.expires)
    if UnitsOf(k and now[k], tk.item) <= tk.before - (tk.units or 1) then
      table.remove(takes, i)
      L.Add({ kind = KIND.take, t = time(), what = tk.what, item = tk.item, units = tk.units, bonus = tk.bonus, mail = tk.seq,
              cod = tk.cod, sender = tk.sender })
    end
  end
  inbox = now
end

function T.TakeItems(index, only)
  local m = inbox[PlainNumber(index) or 0]
  if not m then return end
  only = PlainNumber(only)
  for a, x in pairs(m.items) do
    if not only or a == only then
      takes[#takes + 1] = { at = GetTime(), id = m.id, expires = m.expires, item = x.item, bonus = x.bonus, units = x.units,
                            before = UnitsOf(m, x.item), what = m.what, seq = m.seq, cod = m.cod > 0 or nil,
                            sender = not m.auction and m.sender or nil }
    end
  end
  if m.cod > 0 then L.Heard("cod", { price = m.cod, sub = MAIL.cod, name = m.sender, id2 = m.seq }) end
end

function T.TakeMoney(index)
  local m = inbox[PlainNumber(index) or 0]
  if not m or m.money <= 0 then return end
  local sub = (m.what == MAILKIND.sold or m.what == MAILKIND.pending) and MAIL.sale
              or m.what == MAILKIND.outbid and MAIL.refund or m.what == MAILKIND.player and MAIL.player or MAIL.game
  L.Heard("mailmoney", { price = m.money, sub = sub, id2 = m.auction and m.seq or nil, name = not m.auction and m.sender or nil })
end

local sendMoney = 0

function T.Sent(recipient)
  local money = PlainNumber(Call(GetSendMailMoney)) or sendMoney or 0
  local postage = PlainNumber(Call(GetSendMailPrice))
  L.Heard("send", { price = postage and money + postage or nil, part = money > 0 and money or nil,
                    sub = money > 0 and MAIL.sent or MAIL.postage, name = PlainText(recipient) })
end


function T.Settle(all)
  local now = GetTime()
  while notices[1] and (all or now - notices[1].at > L.WINDOW) do WriteNotice(table.remove(notices, 1)) end
  for i = #posts, 1, -1 do
    local p = posts[i]
    if all or now - p.at >= PAIR then
      if p.ev and p.ev.used then WritePost(p) else table.remove(posts, i) end
    end
  end
  for i = #takes, 1, -1 do
    if all or now - takes[i].at >= TAKE_WAIT then table.remove(takes, i) end
  end
end

T.notices, T.posts, T.takes = notices, posts, takes
function T.Reset()
  wipe(notices); wipe(posts); wipe(takes)
  inbox, list, noticeOf, linePatterns, subjects, sendMoney = {}, nil, nil, nil, nil, 0
end


L.Hook(C_AuctionHouse, "PostItem", function(...) T.Posted(false, false, ...) end)
L.Hook(C_AuctionHouse, "PostCommodity", function(...) T.Posted(true, false, ...) end)
L.Hook(C_AuctionHouse, "ConfirmPostItem", function(...) T.Posted(false, true, ...) end)
L.Hook(C_AuctionHouse, "ConfirmPostCommodity", function(...) T.Posted(true, true, ...) end)
L.Hook(C_AuctionHouse, "CancelAuction", function(id) L.Heard("cancel", { id2 = PlainNumber(id) }) end)
L.Hook(C_AuctionHouse, "PlaceBid", T.Bid)
L.Hook(C_AuctionHouse, "ConfirmCommoditiesPurchase", function(item, units)
  L.Heard("cbuy", { id = PlainNumber(item), count = PlainNumber(units) })
end)
L.Hook(nil, "TakeInboxMoney", T.TakeMoney)
L.Hook(nil, "TakeInboxItem", T.TakeItems)
L.Hook(nil, "AutoLootMailItem", function(index) T.TakeMoney(index); T.TakeItems(index) end)
L.Hook(nil, "SetSendMailMoney", function(v) sendMoney = PlainNumber(v) or 0 end)
L.Hook(nil, "SendMail", T.Sent)

ns.On("AUCTION_HOUSE_AUCTION_CREATED", T.Created)
ns.On("AUCTION_CANCELED", function(_, id)
  id = PlainNumber(id)
  if id then L.Add({ kind = KIND.cancel, t = time(), auction = id }) end
end)
ns.On("AUCTION_HOUSE_PURCHASE_COMPLETED", function(_, id) L.Heard("bought", { id2 = PlainNumber(id) }) end)
ns.On("AUCTION_HOUSE_CLOSED", function() T.WriteListed() end)
ns.On("MAIL_INBOX_UPDATE", function() T.ReadInbox() end)
ns.On("MAIL_SEND_SUCCESS", function() sendMoney = 0 end)
ns.On("PLAYER_LOGOUT", function() T.WriteListed(); T.Settle(true) end)
if L.Known("AUCTION_HOUSE_SHOW_FORMATTED_NOTIFICATION") then
  ns.On("AUCTION_HOUSE_SHOW_FORMATTED_NOTIFICATION", T.Notification)
elseif L.Known("AUCTION_HOUSE_SHOW_NOTIFICATION") then
  ns.On("AUCTION_HOUSE_SHOW_NOTIFICATION", function(_, notification) T.Notification(nil, notification) end)
end
if L.Known("CHAT_MSG_SYSTEM") then ns.On("CHAT_MSG_SYSTEM", T.System) end

ns.OnTick(CreateFrame("Frame"), ns.Word("game.ledger.error.trades"), 0.5, function() T.Settle(false) end)
