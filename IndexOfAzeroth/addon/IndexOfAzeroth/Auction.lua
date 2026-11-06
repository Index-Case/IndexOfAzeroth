-- The Index of Azeroth. Copyright 2026 Index Case <indexofazeroth@pm.me>. PolyForm Strict 1.0.0, see LICENSE.md.
local ADDON, ns = ...

local Plain, Call, PlainText, PlainNumber = ns.Plain, ns.Call, ns.PlainText, ns.PlainNumber
local UI = ns.UI
local C = UI.C

local A = {}
ns.Auction = A

local HEAD, CHUNK = 32, 33
local STATES = { asking = 1, reading = 2, done = 3, stopped = 4, failed = 5 }
local F_SOLD, F_MIN_BID, F_BID, F_PART = 8, 16, 32, 64
A.READ_MS = 4
A.ASK_WAIT = 60
A.INFO_WAIT = 8
A.OWNER_PROBE = 2
A.SETTLE = 1
A.HEAD_EVERY = 1
A.START_BURST = 1.5
A.END_BURST = 1.5
A.STALE = 24 * 3600
A.KEEP = 2
A.COOLDOWN = 15 * 60
local F_SILENT = 2
local SELLER_MAX = 48
local BAND_LEAST = { 0, 1800, 7200, 28800 }


local function DB()
  if type(IndexOfAzerothDB) ~= "table" then IndexOfAzerothDB = {} end
  local a = IndexOfAzerothDB.auction
  if type(a) ~= "table" then a = {}; IndexOfAzerothDB.auction = a end
  if type(a.last) ~= "table" then a.last = {} end
  if type(a.scans) ~= "table" then a.scans = {} end
  if type(a.asked) ~= "table" then a.asked = {} end
  return a
end
A.DB = DB

local houseSide
local function Realm() return PlainText(Call(GetRealmName)) or "" end
local function Side() return houseSide or PlainText(Call(UnitFactionGroup, "player")) or "Neutral" end
function A.House() return Realm() .. "|" .. Side() end

local function AuctionatorState()
  local atr = Auctionator
  if type(atr) ~= "table" or type(atr.SavedState) ~= "table" then return nil end
  if type(atr.Constants) == "table" and atr.Constants.IsLegacyAH then return nil end
  local asked = atr.SavedState.TimeOfLastReplicateScan
  if asked ~= nil and type(asked) ~= "number" then return nil end
  return atr.SavedState, asked
end

function A.LastAsked(house)
  local own = DB().asked[house or A.House()]
  local _, theirs = AuctionatorState()
  if theirs and (not own or theirs > own) then return theirs, "Auctionator" end
  return own
end

function A.NextAt(house)
  local asked = A.LastAsked(house)
  return asked and asked + A.COOLDOWN or nil
end
function A.Wait(house)
  local at = A.NextAt(house)
  return at and math.min(A.COOLDOWN, math.max(0, at - time())) or 0
end
local function Clock(seconds)
  seconds = math.ceil(seconds)
  return string.format("%d:%02d", math.floor(seconds / 60), seconds % 60)
end
A.Clock = Clock

local function Num(n)
  local s, k = tostring(math.floor(n or 0)), 1
  while k > 0 do s, k = s:gsub("^(%d+)(%d%d%d)", "%1,%2") end
  return s
end
A.Num = Num

local function Ago(seconds)
  local hours = math.floor(seconds / 3600)
  if hours < 48 then return hours .. " hours" end
  return math.floor(hours / 24) .. " days"
end

function A.StripLive() return ns.db and ns.db.strip and not ns.paused and true or false end


function A.Running() local s = A.scan; return s and (s.state == "asking" or s.state == "reading") or false end
function A.Active() local s = A.scan; return s and (A.Running() or s.ending) or false end

local function Bands()
  local out, AH = {}, C_AuctionHouse
  for b = 0, 3 do out[b + 1] = PlainNumber(Call(AH and AH.GetTimeLeftBandInfo, b)) or BAND_LEAST[b + 1] end
  return out
end

function A.Start(theirs)
  if A.Running() then return end
  if not A.open then return ns.Print("Open the auction house first. Scan reads the auction house while its window is open.") end
  local wait = A.Wait()
  if wait > 0 and not theirs then
    return ns.Print("Your next scan is in " .. Clock(wait) .. ". The auction house allows one full scan about every 15 minutes.")
  end
  local now, db = GetTime(), DB()
  local house = A.House()
  local known = db.asked[house] ~= nil
  db.asked[house] = theirs or time()
  local id = PlainNumber(Call(GetServerTime)) or time()
  if A.scan and A.scan.id >= id then id = A.scan.id + 1 end
  local record = { id = id, realm = Realm(), faction = Side(), state = "asking", complete = false, sent = 0,
                   chunks = {}, bands = Bands() }
  record.started = time()
  record.nextAt = db.asked[house] + A.COOLDOWN
  table.insert(db.scans, 1, record)
  while #db.scans > A.KEEP do table.remove(db.scans) end
  A.scan = { id = id, realm = record.realm, faction = record.faction, state = "asking", began = now, news = now,
             total = 0, read = 0, sent = 0, chunks = 0, queued = 0, next = 0, waiting = 0, pending = {}, sellers = {},
             order = {}, at = 1, record = record, bands = record.bands, bytes = 0, readMs = 0, raw = {}, parts = {},
             known = known, nextAt = record.nextAt, waitList = {}, waitAt = 1, unowned = {},
             owners = { given = 0, late = 0, none = 0, nolink = 0 } }
  record.owners = A.scan.owners
  A.session = A.session or {}
  table.insert(A.session, A.scan)
  while #A.session > A.KEEP do table.remove(A.session, 1) end
  if theirs then
    local s = A.scan
    s.state, s.readStart, s.recheck, s.atr = "reading", now, true, "theirs"
  else
    local atr, asked = AuctionatorState()
    if atr then atr.TimeOfLastReplicateScan = math.max(asked or 0, record.started) end
    Call(C_AuctionHouse and C_AuctionHouse.ReplicateItems)
  end
  A.runner:Show()
  A.Refresh()
end

function A.Theirs()
  if A.Running() or not A.open then return end
  local _, theirs = AuctionatorState()
  if not theirs or time() - theirs > A.COOLDOWN then return end
  local own = DB().asked[A.House()]
  if own and theirs <= own then return end
  A.Start(theirs)
end

function A.Stop()
  if A.Running() then A.scan.stopping = true; A.Refresh() end
end

function A.Toggle()
  local s = A.scan
  if not A.Running() then
    if A.Wait() > 0 then return end
    return A.Start()
  end
  if not (s.stopping or s.closed or s.whole) then A.Stop() end
end

local function Queue(s, e)
  local list = s.sellers[e.seller]
  if not list then list = { from = 1 }; s.sellers[e.seller] = list end
  list[#list + 1] = e
  list.sorted = false
  if not list.listed then list.listed = true; s.order[#s.order + 1] = e.seller end
  s.queued, s.read = s.queued + 1, s.read + 1
end

local function Suffix(link)
  return tonumber(link and link:match("item:%-?%d+:[^:]*:[^:]*:[^:]*:[^:]*:[^:]*:(%-?%d+)") or nil) or 0
end
A.Suffix = Suffix

local function Owner(owner, ownerFull)
  ownerFull, owner = PlainText(ownerFull), PlainText(owner)
  if ownerFull and ownerFull ~= "" then return ownerFull end
  if owner and owner ~= "" then return owner end
end
A.Owner = Owner

local function OwnersCome(s, now)
  if s.noLate then return false end
  s.ownerWait = s.ownerWait or now
  if s.owners.late == 0 and now - s.ownerWait > A.OWNER_PROBE then
    s.noLate = true
    return false
  end
  return true
end

local function Take(s, i, force)
  local AH = C_AuctionHouse or {}
  local name, icon, count, quality, _, _, _, minBid, _, buyout, bidAmount, _, _, owner, ownerFull, saleStatus, itemID,
        hasAll = Call(AH.GetReplicateItemInfo, i)
  itemID = PlainNumber(itemID)
  local seller = Owner(owner, ownerFull)
  local waited = s.pending[i]
  if itemID and itemID > 0 and not force then
    local info = Plain(hasAll)
    if not info or (not seller and OwnersCome(s, GetTime())) then
      if not waited then
        s.pending[i], s.waiting = GetTime(), s.waiting + 1
        s.waitList[#s.waitList + 1] = i
        if not seller then s.unowned[i] = true end
        if not info then Call(C_Item and C_Item.RequestLoadItemDataByID, itemID) end
      end
      return false
    end
  end
  if waited then s.pending[i], s.waiting = nil, s.waiting - 1 end
  if not itemID or itemID <= 0 then s.unowned[i] = nil; return true end
  local o = s.owners
  if not seller then o.none = o.none + 1 elseif s.unowned[i] then o.late = o.late + 1 else o.given = o.given + 1 end
  s.unowned[i] = nil
  local link = PlainText(Call(AH.GetReplicateItemLink, i))
  if not link then o.nolink = o.nolink + 1 end
  local band = PlainNumber(Call(AH.GetReplicateItemTimeLeft, i))
  band = band and math.max(0, math.min(6, math.floor(band))) or 7
  s.raw[band] = true
  buyout = math.max(0, math.floor(PlainNumber(buyout) or 0))
  minBid, bidAmount = math.max(0, math.floor(PlainNumber(minBid) or 0)), PlainNumber(bidAmount) or 0
  local flags = band + ((PlainNumber(saleStatus) or 0) ~= 0 and F_SOLD or 0)
                + ((buyout == 0 and minBid > 0) and F_MIN_BID or 0) + (bidAmount > 0 and F_BID or 0)
                + ((not seller or not link) and F_PART or 0)
  Queue(s, { item = math.floor(itemID), sfx = Suffix(link), count = math.max(1, math.floor(PlainNumber(count) or 1)), buy = buyout,
             bid = minBid, flags = flags, seller = ((seller or ""):gsub("[~%^/,]", "")):sub(1, SELLER_MAX),
             name = PlainText(name), icon = Plain(icon), q = PlainNumber(quality) })
  return true
end

local function Recheck(s, t0, now, force, ms)
  local list, k = s.waitList, ms and s.waitAt or 1
  while k <= #list do
    if ms and debugprofilestop() - t0 > ms then s.waitAt = k; return true end
    local i = list[k]
    local since = s.pending[i]
    if since then Take(s, i, force or now - since > A.INFO_WAIT) end
    k = k + 1
  end
  local keep = {}
  for _, i in ipairs(list) do if s.pending[i] then keep[#keep + 1] = i end end
  s.waitList, s.waitAt = keep, 1
  return false
end
A.Recheck = Recheck

local function Read(s, t0, now)
  local n = PlainNumber(Call((C_AuctionHouse or {}).GetNumReplicateItems)) or 0
  if n > s.total then s.total, s.news = n, now end
  if s.waiting > 0 and (s.recheck or now - (s.recheckAt or 0) > 0.5) then
    s.recheck, s.recheckAt = false, now
    s.recheck = Recheck(s, t0, now, false, s.next < n and A.READ_MS / 2 or A.READ_MS)
  end
  while s.next < n and debugprofilestop() - t0 < A.READ_MS do
    Take(s, s.next, false)
    s.next = s.next + 1
  end
  if s.next >= n and s.waiting == 0 and now - s.news >= A.SETTLE then
    s.whole, s.readEnd = true, now
  end
end

local function ByItem(a, b)
  if a.item ~= b.item then return a.item < b.item end
  return a.sfx < b.sfx
end
local function Zig(v) return v >= 0 and v * 2 or -v * 2 - 1 end
local function HasMinBid(flags) return math.floor(flags / F_MIN_BID) % 2 == 1 end
local floor = math.floor
local function VarLen(v)
  local n = 1
  while v >= 128 do n, v = n + 1, floor(v / 128) end
  return n
end
local function PutVar(t, v)
  while v >= 128 do
    t[#t + 1] = v % 128 + 128
    v = floor(v / 128)
  end
  t[#t + 1] = v
end
local function AuctionSize(e)
  return 1 + VarLen(e.count) + VarLen(e.buy) + (HasMinBid(e.flags) and VarLen(e.bid) or 0)
end

local function Sorted(list)
  if list.sorted then return end
  local rest = {}
  for k = list.from, #list do rest[#rest + 1] = list[k] end
  table.sort(rest, ByItem)
  for k = 1, #rest do list[list.from + k - 1] = rest[k] end
  list.sorted = true
end

local function WriteRuns(list, body, free, texts, items)
  local runs, prev, k = 0, nil, list.from
  while k <= #list do
    local e = list[k]
    local step = (prev and e.item - prev or e.item) * 2 + (e.sfx ~= 0 and 1 or 0)
    local size = VarLen(step) + (e.sfx ~= 0 and VarLen(Zig(e.sfx)) or 0) + 3
    local n, j = 0, k
    while j <= #list and list[j].item == e.item and list[j].sfx == e.sfx do
      local more = AuctionSize(list[j])
      if #body + size + more > free then break end
      size, n, j = size + more, n + 1, j + 1
    end
    if n == 0 then return runs, k, true end
    PutVar(body, step)
    if e.sfx ~= 0 then PutVar(body, Zig(e.sfx)) end
    PutVar(body, n)
    for m = k, j - 1 do
      local a = list[m]
      local bid = HasMinBid(a.flags) and a.bid or 0
      body[#body + 1] = a.flags
      PutVar(body, a.count)
      PutVar(body, a.buy)
      if HasMinBid(a.flags) then PutVar(body, bid) end
      texts[#texts + 1] = a
    end
    items[#items + 1] = { name = e.name, icon = e.icon, q = e.q, n = n }
    runs, prev, k = runs + 1, e.item, j
    if j <= #list and list[j].item == e.item and list[j].sfx == e.sfx then return runs, k, true end
  end
  return runs, k, false
end

local function PartText(groups)
  local out = {}
  for g, group in ipairs(groups) do
    local rows = {}
    for k, a in ipairs(group.auctions) do
      rows[k] = a.item .. "," .. a.sfx .. "," .. a.count .. "," .. a.buy .. "," .. (HasMinBid(a.flags) and a.bid or 0)
                .. "," .. a.flags
    end
    out[g] = group.seller .. "^" .. table.concat(rows, "/")
  end
  return table.concat(out, "~")
end

function A.Keep()
  for _, s in ipairs(A.session or {}) do
    for n = 1, s.chunks do
      if not s.record.chunks[n] then s.record.chunks[n] = PartText(s.parts[n]) end
    end
  end
end

function A.Chunk(room)
  local s = A.scan
  room = room or ns.MAX_WIDE_PAYLOAD
  local w = ns.NewWriter()
  w:u8(CHUNK); ns.WriteU32(w, s.id); w:var(s.chunks + 1)
  local groupsAt = #w.bytes + 1
  w:u8(0)
  local groups, taken, groupTexts, items = 0, 0, {}, {}
  while s.at <= #s.order and groups < 255 do
    local seller = s.order[s.at]
    local list = s.sellers[seller]
    if list.from > #list then
      list.listed, s.at = false, s.at + 1
    else
      Sorted(list)
      local head, body, texts = ns.NewWriter(), {}, {}
      head:str(seller, SELLER_MAX)
      local runs, upto, full = WriteRuns(list, body, room - #w.bytes - #head.bytes - 3, texts, items)
      if runs > 0 then
        head:var(runs)
        local out = w.bytes
        for _, b in ipairs(head.bytes) do out[#out + 1] = b end
        for _, b in ipairs(body) do out[#out + 1] = b end
        groups, taken = groups + 1, taken + (upto - list.from)
        groupTexts[#groupTexts + 1] = { seller = seller, auctions = texts }
        list.from = upto
      end
      if full then break end
    end
  end
  if groups == 0 then return nil end
  w.bytes[groupsAt] = groups
  s.chunks, s.sent, s.queued, s.bytes = s.chunks + 1, s.sent + taken, s.queued - taken, s.bytes + #w.bytes
  s.firstChunk = s.firstChunk or GetTime()
  s.parts[s.chunks] = groupTexts
  s.record.sent = s.sent
  A.Launch(items)
  return w.bytes
end

function A.Head()
  local s = A.scan
  local w = ns.NewWriter()
  w:u8(HEAD); ns.WriteU32(w, s.id); w:u8(STATES[s.state]); w:u8((s.whole and 1 or 0) + (s.silent and F_SILENT or 0))
  w:var(s.total); w:var(s.read); w:var(s.sent); w:var(s.chunks)
  w:var((s.endedAt or GetTime()) - s.began)
  for b = 1, 4 do w:var(s.bands[b]) end
  w:str(s.realm, 48); w:str(s.faction, 16)
  ns.WriteU32(w, s.nextAt)
  s.headAt = GetTime()
  return w.bytes
end

function A.NextFrame()
  local s, now = A.scan, GetTime()
  if not A.Running() then
    if now - s.endedAt >= A.END_BURST then
      s.ending = false
      ns.StripRows(1)
    end
    return A.Head()
  end
  if now - s.began < A.START_BURST or not s.headAt or now - s.headAt >= A.HEAD_EVERY then return A.Head() end
  return A.Chunk()
end

function A.End(state)
  local s = A.scan
  s.state, s.endedAt = state, GetTime()
  local r = s.record
  r.state, r.ended, r.total, r.read, r.sent, r.whole = state, time(), s.total, s.read, s.sent, s.whole or nil
  r.complete = state == "done" and s.whole or false
  if state == "failed" and s.known then s.silent, r.silent = true, true end
  if s.sent > 0 then DB().last[s.realm .. "|" .. s.faction] = time() end
  if s.atr == "wait" then s.atr = "noframe" end
  s.ending, s.headAt = A.StripLive(), nil
  if not s.ending then ns.StripRows(1) end
  s.sellers, s.order, s.pending, s.waitList, s.unowned = {}, {}, {}, {}, {}
  A.Refresh()
  ns.Print(A.StateWords())
end

function A.Step()
  local s = A.scan
  if not A.Running() then return end
  local t0, now = debugprofilestop(), GetTime()
  if s.state == "asking" then
    if (PlainNumber(Call((C_AuctionHouse or {}).GetNumReplicateItems)) or 0) > 0 then
      s.state, s.readStart = "reading", now
    elseif s.stopping or s.closed then
      return A.End("stopped")
    elseif now - s.began > A.ASK_WAIT then
      return A.End("failed")
    else
      return
    end
  end
  if s.atr == nil or s.atr == "wait" then A.Feed(s) end
  if not (s.stopping or s.closed or s.whole) then
    Read(s, t0, now)
  elseif s.waiting > 0 then
    Recheck(s, t0, now, true, A.READ_MS)
  end
  if not A.StripLive() then
    while s.queued > 0 and A.Chunk() do end
  end
  s.readMs = s.readMs + debugprofilestop() - t0
  if (s.whole or s.stopping or s.closed) and s.waiting == 0 and s.queued == 0 then
    A.End(s.whole and "done" or "stopped")
  end
end

function A.Logout()
  if A.Running() then
    if A.scan.waiting > 0 then Recheck(A.scan, debugprofilestop(), GetTime(), true) end
    while A.scan.queued > 0 and A.Chunk() do end
    A.End("stopped")
  end
  A.Keep()
end


local function AuctionatorFrame()
  local atr = Auctionator
  if type(atr) ~= "table" then return nil, "absent" end
  if type(atr.State) ~= "table" or type(atr.Constants) == "table" and atr.Constants.IsLegacyAH then
    return nil, "changed"
  end
  local f = atr.State.FullScanFrameRef
  if f == nil then return nil, "wait" end
  if type(f) ~= "table" or type(f.CacheScanData) ~= "function" or type(f.state) ~= "table" then return nil, "changed" end
  if f.inProgress then return nil, "own" end
  return f
end

function A.Feed(s)
  if not (s.atr == nil or s.atr == "wait") then return end
  if not A.open then s.atr = "closed"; return end
  local f, why = AuctionatorFrame()
  if not f then s.atr = why; return end
  f.inProgress = true
  f.state.TimeOfLastReplicateScan = math.max(tonumber(f.state.TimeOfLastReplicateScan) or 0, s.record.started)
  Call(f.RegisterEvent, f, "AUCTION_HOUSE_CLOSED")
  s.atrCount = PlainNumber(Call((C_AuctionHouse or {}).GetNumReplicateItems)) or 0
  local ok, err = pcall(f.CacheScanData, f)
  if ok then s.atr = "fed"; return end
  f.inProgress = false
  Call(f.UnregisterEvent, f, "AUCTION_HOUSE_CLOSED")
  s.atr, s.atrError = "error", tostring(err)
end

function A.SellerWords(s)
  local o = s.owners
  local all = o.given + o.late + o.none
  if all == 0 then return "Sellers: the addon hasn't read an auction yet." end
  local words = string.format("Sellers: %s of %s auctions came with their seller at once, %s got their seller later and %s came without a seller.",
    Num(o.given), Num(all), Num(o.late), Num(o.none))
  if o.given + o.late == 0 then
    words = words .. " The house gave no sellers at all, so the Index tells a sale from a cancelled auction by the"
      .. " item, count, price and time left alone."
  end
  if o.nolink > 0 then words = words .. " " .. Num(o.nolink) .. " auctions came without their item link." end
  return words
end

function A.AuctionatorWords(s)
  local atr = s.atr
  if atr == "fed" then
    return "The addon fed Auctionator this scan's answer, " .. Num(s.atrCount)
      .. " auctions. Auctionator stores their prices with its own code and says in chat when it's done."
  elseif atr == "theirs" then
    return "Auctionator asked the house for this scan. Auctionator's own scan reads the answer, and our scan sent the"
      .. " same answer to the Index."
  elseif atr == "own" then
    return "The addon didn't feed Auctionator, because Auctionator's own scan was reading the house's answer."
  elseif atr == "changed" then
    return "The addon didn't feed Auctionator, because Auctionator's full scan isn't the one the addon was built on (Auctionator 340)."
  elseif atr == "wait" then
    return "Auctionator's full scan isn't set up yet. Auctionator gets this scan's answer once its full scan is set up."
  elseif atr == "noframe" then
    return "The addon didn't feed Auctionator, because Auctionator's full scan wasn't set up. Auctionator sets it up when the auction house window opens."
  elseif atr == "closed" then
    return "The addon didn't feed Auctionator, because the auction house window closed before the answer came."
  elseif atr == "error" then
    return "The addon didn't feed Auctionator, because Auctionator's full scan stopped with an error: " .. s.atrError
  elseif atr == "absent" or select(2, AuctionatorFrame()) == "absent" then
    return "Auctionator isn't loaded, so the addon didn't feed Auctionator."
  elseif A.Running() then
    return "Auctionator gets this scan's answer when the house sends it."
  end
  return "The addon didn't feed Auctionator, because the scan ended before the house answered."
end


local anim = { pool = {}, flying = {}, waiting = {}, last = {}, due = 0, cap = 80, most = 120, cost = 0, peak = 0,
  checked = 0 }
A.anim = anim
A.FLIGHT = { speed = 2000, depth = 220, floor = 0.08, width = 160, budget = 0.8, rate = 25, sample = 12, least = 6,
  jitter = { start = 14, radius = 12, exit = 24 } }

function A.Launch(items)
  if not (A.panel and A.panel:IsVisible()) or not items[1] then return end
  local step = math.ceil(#items / A.FLIGHT.sample)
  local picked = {}
  for i = 1, #items, step do
    local it, more = items[i], -1
    for j = i, math.min(#items, i + step - 1) do more = more + items[j].n end
    picked[#picked + 1] = { name = it.name, icon = it.icon, q = it.q, more = more }
  end
  anim.waiting, anim.last = picked, picked
end

local function NextItem()
  local it = table.remove(anim.waiting, 1)
  if it then return it end
  if A.Running() and anim.last[1] then
    for i, v in ipairs(anim.last) do anim.waiting[i] = v end
    return table.remove(anim.waiting, 1)
  end
end

local function Sprite()
  local sp = table.remove(anim.pool)
  if sp then return sp end
  sp = CreateFrame("Frame", nil, UIParent)
  sp:SetFrameStrata("HIGH")
  sp:SetSize(220, 20)
  sp.icon = sp:CreateTexture(nil, "ARTWORK")
  sp.icon:SetSize(18, 18)
  sp.icon:SetPoint("LEFT")
  sp.text = UI.Text(sp, "GameFontHighlightSmall", C.ivory)
  sp.text:SetPoint("LEFT", sp.icon, "RIGHT", 4, 0)
  sp.text:SetWordWrap(false)
  return sp
end

local CURVE_STEPS = 80
local function Cubic(pts, len, ax, ay, bx, by, cx, cy, dx, dy)
  local px, py = ax, ay
  for i = 1, CURVE_STEPS do
    local t = i / CURVE_STEPS
    local u = 1 - t
    local x = u * u * u * ax + 3 * u * u * t * bx + 3 * u * t * t * cx + t * t * t * dx
    local y = u * u * u * ay + 3 * u * u * t * by + 3 * u * t * t * cy + t * t * t * dy
    len = len + math.sqrt((x - px) ^ 2 + (y - py) ^ 2)
    pts[#pts + 1], px, py = { x, y, len }, x, y
  end
  return len
end

function A.Course(p, sway)
  sway = sway or {}
  local k = (p:GetEffectiveScale() or 1) / (UIParent:GetEffectiveScale() or 1)
  local left, right = (p:GetLeft() or 0) * k, (p:GetRight() or 0) * k
  local top, bottom = (p:GetTop() or 0) * k, (p:GetBottom() or 0) * k
  local H = UIParent:GetHeight() or 768
  local x0, y0 = (left + right) / 2 - 40 + (sway.start or 0), top - 90
  local mx = (UIParent:GetWidth() or 1024) / 2 + (sway.exit or 0)
  local yT = H + 40
  local yB = math.max(H * A.FLIGHT.floor, math.min(bottom - A.FLIGHT.depth, y0 - 120)) + (sway.radius or 0)
  local dir = mx >= x0 and 1 or -1
  local half = math.max(math.abs(mx - x0) / 2, A.FLIGHT.width)
  local bx = (x0 + mx) / 2
  local K = 0.5523
  local pts = { { x0, y0, 0 } }
  local len = Cubic(pts, 0, x0, y0, x0, y0 - (y0 - yB) * K, bx - dir * half * K, yB, bx, yB)
  len = Cubic(pts, len, bx, yB, bx + dir * half * K, yB, mx, yT - (yT - yB) * K, mx, yT)
  return { x0 = x0, y0 = y0, mx = mx, yB = yB, pts = pts, len = len }
end

function A.Spot(c, d)
  local pts = c.pts
  if d <= 0 then return pts[1][1], pts[1][2] end
  if d >= c.len then return pts[#pts][1], pts[#pts][2] end
  local lo, hi = 1, #pts
  while hi - lo > 1 do
    local m = math.floor((lo + hi) / 2)
    if pts[m][3] < d then lo = m else hi = m end
  end
  local o, q = pts[lo], pts[hi]
  local f = q[3] > o[3] and (d - o[3]) / (q[3] - o[3]) or 1
  return o[1] + (q[1] - o[1]) * f, o[2] + (q[2] - o[2]) * f
end

local function Fly(sp, dt)
  sp.d = sp.d + A.FLIGHT.speed * dt
  if sp.d >= sp.course.len then return false end
  local x, y = A.Spot(sp.course, sp.d)
  sp:ClearAllPoints()
  sp:SetPoint("LEFT", UIParent, "BOTTOMLEFT", x, y)
  return true
end
A.Fly = Fly

function A.Sway()
  local j = A.FLIGHT.jitter
  local function r(n) return (math.random() * 2 - 1) * n end
  return { start = r(j.start), radius = r(j.radius), exit = r(j.exit) }
end

local function LaunchOne()
  local it = NextItem()
  if not it then return false end
  local sp = Sprite()
  sp.course, sp.d = A.Course(A.panel, A.Sway()), 0
  sp.icon:SetTexture(it.icon or 134400)
  local color = ITEM_QUALITY_COLORS and it.q and ITEM_QUALITY_COLORS[it.q]
  sp.text:SetTextColor(color and color.r or C.ivory[1], color and color.g or C.ivory[2], color and color.b or C.ivory[3])
  sp.text:SetText((it.name or "") .. (it.more > 0 and ("  +" .. Num(it.more)) or ""))
  Fly(sp, 0)
  sp:Show()
  anim.flying[#anim.flying + 1] = sp
  anim.launched = (anim.launched or 0) + 1
  return true
end

function A.Animate(dt)
  local t0 = debugprofilestop()
  local f = A.FLIGHT
  for k = #anim.flying, 1, -1 do
    local sp = anim.flying[k]
    if not Fly(sp, dt) then
      sp:Hide()
      table.remove(anim.flying, k)
      anim.pool[#anim.pool + 1] = sp
    end
  end
  anim.due = math.min(anim.due + dt * f.rate, 3)
  if A.panel and A.panel:IsVisible() then
    while anim.due >= 1 and #anim.flying < anim.cap and LaunchOne() do anim.due = anim.due - 1 end
  end
  if not anim.waiting[1] and not A.Running() then anim.due = 0 end
  local ms = debugprofilestop() - t0
  anim.cost, anim.peak = anim.cost * 0.9 + ms * 0.1, math.max(anim.peak, ms)
  local now = GetTime()
  if now - anim.checked >= 1 then
    anim.checked = now
    if anim.cost > f.budget then
      anim.cap = math.max(f.least, math.floor(anim.cap * 0.75))
    elseif anim.cost < f.budget / 2 and anim.cap < anim.most then
      anim.cap = anim.cap + 4
    end
  end
end


function A.StateWords()
  local s = A.scan
  if not s then return "Scan reads every auction in this house and sends the auctions to the Index." end
  local words
  if s.state == "asking" then
    words = "Asking the auction house for every auction"
  elseif s.state == "reading" and (s.stopping or s.closed or s.whole) then
    words = string.format("Sending the last %s of %s auctions", Num(s.queued), Num(s.read))
  elseif s.state == "reading" then
    words = string.format("Read %s of %s auctions, %s sent", Num(s.read), Num(s.total), Num(s.sent))
  elseif s.state == "done" then
    words = string.format("Done. The addon sent %s auctions in %d seconds", Num(s.sent), math.floor(s.endedAt - s.began + 0.5))
  elseif s.state == "stopped" then
    words = string.format("Stopped. The Index kept %s auctions", Num(s.sent))
  elseif s.silent then
    words = "The house didn't answer though 15 minutes had passed since the last scan's request"
  else
    words = "The auction house sent nothing back. The house lets you read it whole about once in 15 minutes, so try again later."
  end
  if s.state ~= "failed" and not A.StripLive() then
    words = words .. ". The strip is off, so the Index gets the auctions at your next /reload"
  end
  return words
end

function A.StaleWords(now)
  local last = DB().last[A.House()]
  if not last then return "You haven't scanned this auction house yet. Scan reads the house's prices for the Index." end
  local age = (now or time()) - last
  if age <= A.STALE then return nil end
  return "The last scan was " .. Ago(age) .. " ago, so the Index's prices for this house are out of date. Scan brings the prices up to date."
end

function A.Refresh()
  local p = A.panel
  if not p then return end
  local s = A.scan
  local wait = not A.Running() and A.Wait() or 0
  p.key.locked = wait > 0
  p.key:SetEnabled(not p.key.locked)
  p.key:SetAlpha(p.key.locked and 0.6 or 1)
  p.key.label:SetText(p.key.locked and ("Next scan in " .. Clock(wait)) or not A.Running() and "Scan"
    or (s.stopping or s.closed or s.whole) and "Sending" or "Stop")
  p.key:SetSelected(A.Running())
  p.state:SetText(A.StateWords())
  local stale = A.StaleWords()
  p.stale:SetText(stale or "")
  p.stale:SetShown(stale ~= nil)
end

A.BG, A.BG_SHAPE = "Interface\\AddOns\\IndexOfAzeroth\\Media\\ah_bg", 3440 / 1440
A.ICON, A.ICON_SIZE = "Interface\\AddOns\\IndexOfAzeroth\\Media\\icon", 64

function A.Cover(tex, w, h)
  if not (w and h and w > 0 and h > 0) then return end
  local frame = w / h
  if frame < A.BG_SHAPE then
    local cut = (1 - frame / A.BG_SHAPE) / 2
    tex:SetTexCoord(cut, 1 - cut, 0, 1)
  else
    local cut = (1 - A.BG_SHAPE / frame) / 2
    tex:SetTexCoord(0, 1, cut, 1 - cut)
  end
end

local function MakePanel(parent)
  local p = CreateFrame("Frame", "IndexOfAzerothAuctionPanel", parent, "BackdropTemplate")
  p:SetPoint("TOPLEFT", parent, "TOPLEFT", 8, -62)
  p:SetPoint("BOTTOMRIGHT", parent, "BOTTOMRIGHT", -8, 28)
  UI.Panel(p)
  p.bg = p:CreateTexture(nil, "BORDER", nil, -8)
  p.bg:SetAllPoints(p)
  p.bg:SetTexture(A.BG)
  p:SetScript("OnSizeChanged", function(self, w, h) A.Cover(self.bg, w, h) end)
  p.title = UI.Text(p, "GameFontNormalLarge", C.gold)
  p.title:SetPoint("TOPLEFT", 14, -12)
  p.title:SetText("Auction house scan")
  p.key = UI.FlatButton(p, "Scan", 160, function() A.Toggle() end)
  p.key:SetPoint("TOPLEFT", 14, -40)
  p.state = UI.Text(p, "GameFontHighlight", C.ivory)
  p.state:SetPoint("LEFT", p.key, "RIGHT", 12, 0)
  p.state:SetPoint("RIGHT", p, "RIGHT", -14, 0)
  p.stale = UI.Text(p, "GameFontNormal", C.yellow)
  p.stale:SetPoint("TOPLEFT", p.key, "BOTTOMLEFT", 0, -10)
  p.stale:SetPoint("RIGHT", p, "RIGHT", -14, 0)
  p.icon = p:CreateTexture(nil, "ARTWORK")
  p.icon:SetTexture(A.ICON)
  p.icon:SetSize(A.ICON_SIZE, A.ICON_SIZE)
  p.icon:SetPoint("BOTTOMRIGHT", p, "BOTTOMRIGHT", -12, 12)
  p:SetScript("OnShow", function()
    if parent.SetTitle then pcall(parent.SetTitle, parent, "The Index of Azeroth") end
    A.Cover(p.bg, p:GetSize())
    A.Refresh()
  end)
  ns.OnTick(p, "the auction tab's countdown", nil, function()
    if time() == p.ticked then return end
    p.ticked = time()
    if p.key.locked or not A.Running() and A.Wait() > 0 then A.Refresh() end
  end)
  return p
end

function A.AddTab()
  local f = AuctionHouseFrame
  if A.panel or not f then return end
  A.panel = MakePanel(f)
  A.panel:Hide()
  f.IndexOfAzerothPanel = A.panel
  local mode = { "IndexOfAzerothPanel" }
  local ok = pcall(function()
    AuctionHouseFrameDisplayMode.IndexOfAzeroth = mode
    local tab = CreateFrame("Button", "AuctionHouseFrameIndexOfAzerothTab", f, "AuctionHouseFrameDisplayModeTabTemplate")
    tab.displayMode = mode
    tab:SetText("The Index of Azeroth")
    if PanelTemplates_TabResize then PanelTemplates_TabResize(tab, 0) end
    if f.Tabs[#f.Tabs] ~= tab then f.Tabs[#f.Tabs + 1] = tab end
    tab:SetPoint("LEFT", f.Tabs[#f.Tabs - 1], "RIGHT", -15, 0)
    PanelTemplates_SetNumTabs(f, #f.Tabs)
    f.tabsForDisplayMode[mode] = #f.Tabs
    A.tab = tab
  end)
  if ok then return end
  A.panel:SetFrameLevel(f:GetFrameLevel() + 20)
  A.tab = UI.FlatButton(f, "The Index of Azeroth", 170, function() A.panel:SetShown(not A.panel:IsShown()) end)
  A.tab:SetHeight(20)
  A.tab:SetPoint("TOPRIGHT", f, "TOPRIGHT", -30, -2)
end


ns.On("ADDON_LOADED", function(_, name) if name == "Blizzard_AuctionHouseUI" then A.AddTab() end end)
ns.On("PLAYER_LOGIN", function() if AuctionHouseFrame then A.AddTab() end end)
ns.On("AUCTION_HOUSE_SHOW", function()
  A.open = true
  houseSide = Call(UnitExists, "npc") and (PlainText(Call(UnitFactionGroup, "npc")) or "Neutral") or nil
  A.AddTab()
  A.Refresh()
end)
ns.On("AUCTION_HOUSE_CLOSED", function()
  A.open = false
  if A.Running() then A.scan.closed = true end
end)
ns.On("REPLICATE_ITEM_LIST_UPDATE", function()
  local s = A.scan
  if not A.Running() then return A.Theirs() end
  if s.state == "asking" then s.state, s.readStart = "reading", GetTime() end
  s.news, s.recheck = GetTime(), true
  A.Feed(s)
end)
ns.On("ITEM_DATA_LOAD_RESULT", function() if A.Running() then A.scan.recheck = true end end)
ns.On("PLAYER_LOGOUT", function() A.Logout() end)

A.runner = CreateFrame("Frame")
A.runner:Hide()
ns.OnTick(A.runner, "the auction scan's frame", nil, function(self, dt)
  local ok, err = pcall(A.Step)
  if not ok then ns.Report("auction scan", err) end
  ok, err = pcall(A.Animate, dt)
  if not ok then ns.Report("auction scan's animation", err) end
  if A.panel and A.Running() and GetTime() - (A.refreshed or 0) > 0.25 then
    A.refreshed = GetTime()
    A.Refresh()
  end
  if not A.Running() and not anim.flying[1] and not anim.waiting[1] then
    anim.last = {}
    self:Hide()
  end
end)


function A.Command(arg)
  if arg == "scan" then return A.Start() end
  if arg == "stop" then return A.Stop() end
  local s = A.scan
  local wait = A.Wait()
  local nextWords = wait > 0 and "Your next scan is in " .. Clock(wait) .. "." or "You can scan now."
  if wait > 0 and select(2, A.LastAsked()) then nextWords = "Your next scan is in " .. Clock(wait) .. ", counted from Auctionator's request." end
  if not s then
    ns.Print("You haven't scanned an auction house this session. " .. (A.StaleWords() or "The last scan of this house was within a day.") .. " "
      .. nextWords)
    return
  end
  ns.Print(nextWords)
  ns.Print(string.format("Scan %d of %s (%s): %s", s.id, s.realm, s.faction, A.StateWords()))
  local now = s.endedAt or GetTime()
  local reading = (s.readEnd or now) - (s.readStart or s.began)
  local sending = now - (s.firstChunk or now)
  ns.Print(string.format("Read %s of %s auctions in %.1f s (%s a second, %.1f ms of reading in all). Sent %s in %d parts, %.1f bytes an auction, %s a second on the strip",
    Num(s.read), Num(s.total), reading, Num(reading > 0 and s.read / reading or 0), s.readMs, Num(s.sent), s.chunks,
    s.sent > 0 and s.bytes / s.sent or 0, Num(sending > 0 and s.sent / sending or 0)))
  local raw = {}
  for b = 0, 7 do if s.raw[b] then raw[#raw + 1] = tostring(b) end end
  ns.Print(A.SellerWords(s))
  ns.Print(string.format("Time left bands the game gave: %s. Their least seconds: %s", table.concat(raw, " "),
    table.concat(s.bands, " ")))
  ns.Print(string.format("Animation: %.2f ms a frame on average, %.2f at most, %d flown, up to %d in the air",
    anim.cost, anim.peak, anim.launched or 0, anim.cap))
  ns.Print(A.AuctionatorWords(s))
end
