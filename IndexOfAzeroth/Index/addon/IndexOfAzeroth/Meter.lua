-- The Index of Azeroth. Copyright 2026 Index Case <indexofazeroth@pm.me>. PolyForm Strict 1.0.0, see LICENSE.md.
local ADDON, ns = ...
local Plain, Call, Number, Text = ns.Plain, ns.Call, ns.PlainNumber, ns.PlainText

local M = {
  FIGHTS_MOST = 10000,
  LINES_KEPT = 150,
  SPELLS_KEPT = 150,
  NAMES_MOST = 20000,
  SETS_MOST = 5000,
  OTHER = "*",
  LINE_MOST = 600,
  IDLE = 3,
  JOIN_SLACK = 10,
  POLL_STEP = 0.3, POLL_TRIES = 30, MATCH = 2, AFTER = 1, SAME = 2,
  SWING_SPELL = 6603,
  ENEMIES_KEPT = 12,
  FIELD = { t = 1, len = 2, dmg = 3, taken = 4, act = 5, max = 6, hits = 7, lvl = 8, gap = 9, kind = 10, flags = 11,
            w = 12, b = 13, g = 14, name = 15, xp = 16, kills = 17, out = 18, on = 28, foes = 35, main = 36,
            place = 37, cd = 38, n = 38 },
  OPEN_WORLD = 1, DUNGEON = 2,
  OUT = { "hit", "crit", "glance", "crush", "block", "miss", "dodge", "parry", "resist", "other" },
  ON = { "hit", "crit", "crush", "miss", "dodge", "parry", "block" },
  GROUPED = 1, CHANGED = 2, DIED = 4, FROM_HITS = 8, DETAIL = 16, GAME = 32, NO_DMG = 64, NO_TAKEN = 128, NO_MAX = 256,
  GAP_BASE = 100,
  KINDS = { normal = 1, elite = 2, rareelite = 3, rare = 4, worldboss = 5, minus = 6, trivial = 6 },
}
ns.Meter = M

local function Has(flags, bit) return flags % (bit * 2) >= bit end

function M.Foes(fields)
  local kept = fields[M.FIELD.foes] or 0
  if kept == 0 then return nil end
  return kept - 1
end
function M.FoesField(n) return n and n + 1 or 0 end
function M.Multi(fields)
  local n = M.Foes(fields)
  if n then return n >= 2, false end
  local kills = fields[M.FIELD.kills]
  if kills == nil then return nil end
  return kills >= 2, true
end
function M.MainShare(fields)
  local share = fields[M.FIELD.main] or 0
  return share > 0 and share or nil
end
function M.Place(fields)
  local place = fields[M.FIELD.place] or 0
  return place > 0 and place or nil
end

local WOUND = { CRITICAL = "crit", GLANCING = "glance", CRUSHING = "crush", BLOCK_REDUCED = "block" }
local MISSED = { MISS = "miss", DODGE = "dodge", PARRY = "parry", BLOCK = "block", RESIST = "resist" }
local function Outcome(action, flag)
  if action == "WOUND" then return WOUND[flag or ""] or "hit" end
  if action == "HEAL" or type(action) ~= "string" then return nil end
  return MISSED[action] or "other"
end


local store
local places = {}

local function Store()
  if type(IndexOfAzerothCharDB) ~= "table" then return nil end
  local m = IndexOfAzerothCharDB.meter
  if store and m == store then return store end
  if type(m) ~= "table" or m.v ~= 1 then
    m = { v = 1 }
    IndexOfAzerothCharDB.meter = m
  end
  for _, key in ipairs({ "names", "sets", "f", "d" }) do
    if type(m[key]) ~= "table" then m[key] = {} end
  end
  for _, kind in ipairs({ "w", "b", "g", "c" }) do
    if type(m.sets[kind]) ~= "table" then m.sets[kind] = {} end
  end
  if type(m.cw) ~= "table" then m.cw = {} end
  for kind, list in pairs({ names = m.names, w = m.sets.w, b = m.sets.b, g = m.sets.g, c = m.sets.c }) do
    places[kind] = {}
    for i, key in ipairs(list) do places[kind][key] = i end
  end
  store = m
  return m
end

local function Place(kind, key)
  local m = Store()
  if not (m and key and key ~= "") then return 0 end
  local at = places[kind][key]
  if not at then
    local list = kind == "names" and m.names or m.sets[kind]
    if #list >= (kind == "names" and M.NAMES_MOST or M.SETS_MOST) then key = M.OTHER end
    at = places[kind][key]
    if not at then
      at = #list + 1
      list[at], places[kind][key] = key, at
    end
  end
  return at
end

function M.Pack(fields)
  local parts = {}
  for i = 1, M.FIELD.n do
    local v = fields[i]
    parts[i] = (v and v ~= 0) and tostring(v) or ""
  end
  return table.concat(parts, ",")
end
function M.Unpack(row)
  local fields, n = {}, 0
  for v in (row .. ","):gmatch("([^,]*),") do
    n = n + 1
    fields[n] = tonumber(v) or 0
  end
  return fields
end
local function StartOf(row) return tonumber(row:match("^(%d+)")) or 0 end

local PET = "pet"
local hands
local function Hands()
  local slots = Enum and Enum.WeaponSlot
  if not hands and type(slots) == "table" then
    hands = {}
    for name, slot in pairs(slots) do
      if type(name) == "string" then hands[name:lower()] = slot end
    end
  end
  return hands or {}
end
local function Owned(group) return group == PET or Hands()[group] ~= nil end

local function CondField(reading, index)
  local held, groups, parts = {}, {}, {}
  for group, c in pairs(reading or {}) do
    if Owned(group) then held[group] = c end
  end
  for group, c in pairs(index or {}) do
    if not Owned(group) then held[group] = c end
  end
  for group in pairs(held) do groups[#groups + 1] = group end
  if #groups == 0 and index then return 1 end
  table.sort(groups)
  for i, group in ipairs(groups) do
    local c = held[group]
    parts[i] = group .. ";" .. c.spell .. ";" .. (c.swap and 1 or 0) .. ";" .. c.name
  end
  if not index then table.insert(parts, 1, "~") end
  return Place("c", table.concat(parts, "|")) + 1
end
local NONE, parsed = {}, {}
function M.Conds(fields, group)
  local at = fields[M.FIELD.cd] or 0
  if at == 0 then return nil end
  if at == 1 then return NONE end
  local m = Store()
  local key = m and m.sets.c[at - 1]
  if not key or key == M.OTHER then return nil end
  local got = parsed[key]
  if not got then
    got = { {}, key:sub(1, 1) == "~" }
    for part in key:gmatch("[^|]+") do
      local name, spell, swap, word = part:match("^([^;]*);(%d+);(%d);(.*)$")
      if name then got[1][name] = { spell = tonumber(spell), name = word, swap = swap == "1" } end
    end
    parsed[key] = got
  end
  if group and got[2] and not Owned(group) then return nil end
  return got[1]
end
function M.CondGroups()
  local m, out, seen = Store(), {}, {}
  if not m then return out end
  for at = 1, #m.sets.c do
    for group in pairs(M.Conds({ [M.FIELD.cd] = at + 1 }) or NONE) do
      local word = m.cw[group]
      if not seen[group] and type(word) == "string" and word ~= "" then
        seen[group] = true
        out[#out + 1] = { key = group, word = word }
      end
    end
  end
  table.sort(out, function(a, b) return a.word:lower() < b.word:lower() end)
  return out
end

local function Trim(m)
  local f, d = m.f, m.d
  while #f > M.FIGHTS_MOST do
    d[StartOf(table.remove(f, 1))] = nil
  end
  local line, spells = f[#f - M.LINES_KEPT], f[#f - M.SPELLS_KEPT]
  local detail = line and d[StartOf(line)]
  if detail then detail.ln = nil end
  detail = spells and d[StartOf(spells)]
  if detail then
    detail.sp, detail.sg, detail.up, detail.down, detail.en, detail.ew = nil, nil, nil, nil, nil, nil
    if detail.ln == nil then d[StartOf(spells)] = nil end
  end
end


local setup = { dirty = true }

local function Hash(s)
  local h = 5381
  for i = 1, #s do h = (h * 33 + s:byte(i)) % 2147483647 end
  return string.format("%x", h)
end

local function Setup()
  if not setup.dirty and setup.w then return setup end
  local ids = {}
  for slot = 1, 19 do ids[slot] = Number(Call(GetInventoryItemID, "player", slot)) or 0 end
  setup.w = ids[16] .. ":" .. ids[17] .. ":" .. ids[18]
  setup.g = Hash(table.concat(ids, ":"))
  local talents = ns.Talents and ns.Talents() or {}
  local parts = {}
  for node, ranks in pairs(type(talents.ranks) == "table" and talents.ranks or {}) do
    parts[#parts + 1] = tostring(node) .. ":" .. tostring(ranks)
  end
  table.sort(parts)
  local points = table.concat(type(talents.points) == "table" and talents.points or {}, "/")
  setup.b = #parts > 0 and (points .. " " .. Hash(table.concat(parts, ","))) or points
  setup.dirty = false
  return setup
end

local reading = {}

local function HandRead(map, slot, now)
  local list = Plain(Call(C_Item and C_Item.GetWeaponEnchantInfo, slot))
  if type(list) ~= "table" then return nil end
  for _, e in ipairs(list) do
    e = Plain(e)
    if type(e) ~= "table" then return nil end
    if Plain(e.hasEnchant) == true then
      local id = Number(e.enchantID)
      if not id then return nil end
      local hit = map[id]
      if type(hit) == "table" then
        local left = Number(e.timeLeft)
        return { spell = hit[1], name = hit[2], ends = left and now + left / 1000 or nil }
      end
    end
  end
  return false
end

local function PetRead()
  local out = Plain(Call(UnitExists, PET))
  if out == nil then return nil end
  if not out then return false end
  local family, id = Call(UnitCreatureFamily, PET)
  family, id = Text(family), Number(id)
  if not (family and id) then return false end
  return { spell = id, name = family }
end

local function Read()
  local m = Store()
  if not m then return end
  local now, ench = Number(Call(GetTime)) or 0, type(m.cr) == "table" and m.cr.e
  for group, slot in pairs(Hands()) do
    if m.cw[group] and type(ench) == "table" then
      local got = HandRead(ench, slot, now)
      if got ~= nil then reading[group] = got end
    end
  end
  if m.cw[PET] then
    local got = PetRead()
    if got ~= nil then reading[PET] = got end
  end
end

local function Readings()
  Read()
  local now, out = Number(Call(GetTime)) or 0, {}
  for group, c in pairs(reading) do
    if c and not (c.ends and c.ends <= now) then out[group] = { spell = c.spell, name = c.name } end
  end
  return out
end


local cur
local ended
local kept
local asking
local function Missed()
  asking = nil
  if kept then kept.stale = true end
end

local listeners = {}
function M.Listen(fn, ...)
  local wants = {}
  for _, what in ipairs(select("#", ...) > 0 and { ... } or { "start", "finish" }) do wants[what] = true end
  listeners[#listeners + 1] = { fn = fn, wants = wants }
end
local function Tell(what, ...)
  for _, l in ipairs(listeners) do
    if l.wants[what] then
      local ok, err = pcall(l.fn, what, ...)
      if not ok then ns.Report(ns.Word("game.meter.part.listener"), err) end
    end
  end
end

local function Acted(f, now)
  if f.lastAct and now - f.lastAct <= M.IDLE then f.act = f.act + (now - f.lastAct) end
  f.lastAct = now
end

local function Target(f)
  if f.name or not Plain(Call(UnitExists, "target")) or not Plain(Call(UnitCanAttack, "player", "target")) then return end
  f.name = Text(Call(UnitName, "target"))
  local level = Number(Call(UnitLevel, "target"))
  if level then f.gap = level < 0 and 10 or level - f.lvl end
  f.kind = Plain(Call(UnitIsBossMob, "target")) == true and M.KINDS.worldboss
    or M.KINDS[Text(Call(UnitClassification, "target")) or ""]
end

local function XP() return Number(Call(UnitXP, "player")), Number(Call(UnitXPMax, "player")) end

local function Start()
  if cur or not Store() then return end
  if asking then Missed() end
  local now = Number(Call(GetTime)) or 0
  local s = Setup()
  local inside, kind = Call(IsInInstance)
  inside, kind = Plain(inside), Text(kind)
  cur = { t0 = now, at = time(), lvl = Number(Call(UnitLevel, "player")) or 0, w = s.w, b = s.b, g = s.g,
          grouped = Plain(Call(IsInGroup)) and true or false,
          place = inside == false and M.OPEN_WORLD or inside and (kind == "party" or kind == "raid") and M.DUNGEON or nil,
          out = {}, on = {}, line = {}, seen = 0, hits = 0, max = 0, taken = 0, act = 0, xp = 0, casts = 0,
          hidden = 0, hiddenOn = 0, rd = Readings(), idle = ended and math.max(0, now - ended) or nil,
          gains = ns.killXP and ns.killXP.next or 0 }
  cur.xpAt, cur.xpMax = XP()
  Target(cur)
  Tell("start", cur)
end

local function Combat(_, unit, action, flag, amount)
  local f = cur
  if not f then return end
  unit, action, flag = Text(unit), Text(action), Text(flag)
  local plain = Number(amount) or action ~= "WOUND"
  amount = Number(amount) or 0
  local kind = Outcome(action, flag)
  if not kind then return end
  if unit == "target" then
    if not Plain(Call(UnitCanAttack, "player", "target")) then return end
    Target(f)
    local now = Number(Call(GetTime)) or f.t0
    f.out[kind] = (f.out[kind] or 0) + 1
    f.hits, f.seen = f.hits + 1, f.seen + amount
    if not plain then f.hidden = f.hidden + 1 end
    if amount > f.max then f.max = amount end
    local second = math.max(1, math.min(M.LINE_MOST, math.floor(now - f.t0) + 1))
    f.line[second] = (f.line[second] or 0) + amount
    Acted(f, now)
  elseif unit == "player" then
    if kind == "glance" or kind == "resist" or kind == "other" then kind = "hit" end
    f.on[kind] = (f.on[kind] or 0) + 1
    f.taken = f.taken + amount
    if not plain then f.hiddenOn = f.hiddenOn + 1 end
  end
end

local function Cast(_, unit)
  local f = cur
  if not f or Text(unit) ~= "player" then return end
  f.casts = f.casts + 1
  Acted(f, Number(Call(GetTime)) or f.t0)
end

local function GainedXP()
  local f = cur
  if not f then return end
  local xp, max = XP()
  if not (xp and f.xpAt) then return end
  local gain = xp - f.xpAt
  if gain < 0 then gain = (f.xpMax or 0) - f.xpAt + xp end
  f.xp, f.xpAt, f.xpMax = f.xp + gain, xp, max
end


function M.Covers(len, idle)
  local types = Enum and Enum.DamageMeterSessionType
  local secs = Number(Call(C_DamageMeter and C_DamageMeter.GetSessionDurationSeconds, types and types.Current))
  local now = Number(Call(GetTime))
  if secs == nil or now == nil then return nil end
  local start = now - secs
  if kept and start < kept.ended - M.AFTER and math.abs(start - kept.start) <= M.SAME then
    return kept.stale and "other" or "share", secs, now
  end
  local whole = secs >= len - M.MATCH and (secs <= len + M.MATCH or (idle ~= nil and len + idle - secs >= M.AFTER))
  return whole and "whole" or "other", secs, now
end

function M.GameMeter()
  return C_DamageMeter ~= nil and Enum ~= nil and Enum.DamageMeterSessionType ~= nil and Enum.DamageMeterType ~= nil
    and Plain(Call(C_DamageMeter.IsDamageMeterAvailable)) == true
end

local function Session(kind)
  return Call(C_DamageMeter.GetCombatSessionFromType, Enum.DamageMeterSessionType.Current, kind)
end
local function Mine(session)
  local sources = type(session) == "table" and session.combatSources
  for _, source in ipairs(type(sources) == "table" and sources or {}) do
    if type(source) == "table" and Plain(source.isLocalPlayer) == true then return source end
  end
end

local function Yours(who, me, pet)
  return who == me or (me ~= nil and who:sub(1, #me + 1) == me .. "-") or (pet ~= nil and who == pet)
end

local function GameFoes(kinds)
  if kinds.EnemyDamageTaken == nil then return nil end
  local session = Session(kinds.EnemyDamageTaken)
  local sources = type(session) == "table" and session.combatSources
  if type(sources) ~= "table" then return nil end
  local me, pet = Text(Call(UnitName, "player")), Text(Call(UnitName, "pet"))
  local mine, whole = {}, {}
  for _, src in ipairs(sources) do
    local name, total = type(src) == "table" and Text(src.name), type(src) == "table" and Number(src.totalAmount)
    if not (name and total) then return nil end
    local kind, guid = M.KINDS[Text(src.classification) or ""] or 0, Text(src.sourceGUID)
    whole[#whole + 1] = { name = name, d = total, kind = kind, key = guid or name }
    local read = mine and Call(C_DamageMeter.GetCombatSessionSourceFromType, Enum.DamageMeterSessionType.Current,
                                kinds.EnemyDamageTaken, guid, Number(src.sourceCreatureID))
    local by = type(read) == "table" and read.combatSpells
    local yours = type(by) == "table" and 0 or nil
    for _, row in ipairs(yours and by or {}) do
      local details = type(row) == "table" and row.combatSpellDetails
      local who, d = type(details) == "table" and Text(details.unitName), type(row) == "table" and Number(row.totalAmount)
      if not (who and d) then yours = nil; break end
      if Yours(who, me, pet) then yours = yours + d end
    end
    if yours == nil then mine = nil end
    if mine and yours > 0 then mine[#mine + 1] = { name = name, d = yours, kind = kind, key = guid or name } end
  end
  return { rows = mine or whole, whole = mine == nil }
end

local function Reading()
  local kinds = Enum.DamageMeterType
  local done = Session(kinds.DamageDone)
  local me = Mine(done)
  local dmg = Number(type(done) == "table" and done.totalAmount) and (me and Number(me.totalAmount) or (not me and 0))
  if not dmg then return nil end
  local read = { dmg = dmg, spells = {}, foes = GameFoes(kinds) }
  local hurt = Session(kinds.DamageTaken)
  local row = Mine(hurt)
  read.taken = Number(type(hurt) == "table" and hurt.totalAmount) and (row and Number(row.totalAmount) or (not row and 0)) or nil
  local guid = me and Text(me.sourceGUID)
  local source = guid and Call(C_DamageMeter.GetCombatSessionSourceFromType, Enum.DamageMeterSessionType.Current, kinds.DamageDone, guid)
  local spells = type(source) == "table" and source.combatSpells
  for _, sp in ipairs(type(spells) == "table" and spells or {}) do
    local id, d = type(sp) == "table" and Number(sp.spellID), type(sp) == "table" and Number(sp.totalAmount)
    if id and d then
      read.spells[#read.spells + 1] = { id = id == M.SWING_SPELL and 0 or id, d = d, ok = Number(sp.overkillAmount) or 0,
                                        by = Text(sp.creatureName) }
    end
  end
  return read
end

local function ByKey(rows, key)
  local out = {}
  for _, r in ipairs(rows) do
    local k = key(r)
    local sum = out[k] or { d = 0, ok = 0 }
    sum.d, sum.ok, out[k] = sum.d + r.d, sum.ok + (r.ok or 0), sum
  end
  return out
end
local function Less(rows, before, key)
  local was, out, seen = ByKey(before, key), {}, {}
  for k, now in pairs(ByKey(rows, key)) do
    local old = was[k] or { d = 0, ok = 0 }
    local d, ok = now.d - old.d, now.ok - old.ok
    if d < 0 or ok < 0 then return nil end
    seen[k] = true
    if d > 0 then out[#out + 1] = { k = k, d = d, ok = ok } end
  end
  for k, old in pairs(was) do
    if not seen[k] and (old.d > 0 or old.ok > 0) then return nil end
  end
  table.sort(out, function(a, b) return a.d > b.d or (a.d == b.d and tostring(a.k) < tostring(b.k)) end)
  return out
end
local function SpellKey(sp) return sp.id .. ";" .. (sp.by or "") end
local function FoeKey(foe) return foe.key end

local function Share(now, was)
  local dmg = now.dmg - was.dmg
  local taken = now.taken and was.taken and now.taken - was.taken or nil
  local spells = Less(now.spells, was.spells, SpellKey)
  if dmg < 0 or (taken and taken < 0) or not spells then return nil end
  local share = { dmg = dmg, taken = taken, spells = {} }
  local info = {}
  for _, sp in ipairs(now.spells) do info[SpellKey(sp)] = sp end
  for i, row in ipairs(spells) do
    local sp = info[row.k]
    share.spells[i] = { id = sp.id, d = row.d, ok = row.ok, by = sp.by }
  end
  if now.foes and was.foes and now.foes.whole == was.foes.whole then
    local foes = Less(now.foes.rows, was.foes.rows, FoeKey)
    if not foes then return nil end
    local about = {}
    for _, foe in ipairs(now.foes.rows) do about[foe.key] = foe end
    share.foes = { rows = {}, whole = now.foes.whole }
    for i, row in ipairs(foes) do
      share.foes.rows[i] = { name = about[row.k].name, d = row.d, kind = about[row.k].kind, key = row.k }
    end
  end
  return share
end

local function Pull(fig)
  local foes = fig.foes
  if not foes then return { dmg = fig.dmg, taken = fig.taken, spells = fig.spells } end
  local rows, sum = {}, 0
  for i, foe in ipairs(foes.rows) do rows[i] = foe; sum = sum + foe.d end
  table.sort(rows, function(a, b) return a.d > b.d end)
  local n = not foes.whole and #rows or nil
  local main = n and rows[1] and sum > 0 and math.max(1, math.floor(100 * rows[1].d / sum + 0.5)) or nil
  while #rows > M.ENEMIES_KEPT do table.remove(rows) end
  return { dmg = fig.dmg, taken = fig.taken, spells = fig.spells,
           foes = { n = n, rows = rows, whole = foes.whole, main = main } }
end

local function GameFigures(len, idle, ended)
  local how, secs, now = M.Covers(len, idle)
  if how == nil then return "wait" end
  local read = Reading()
  if not read then return "wait" end
  local was = kept
  read.at, read.start, read.ended = now, now - secs, ended
  kept = read
  local fig = how == "whole" and read or how == "share" and Share(read, was) or nil
  return fig and Pull(fig) or "other"
end

local function Named(fields, foes)
  local main = foes and foes.n and not foes.whole and foes.rows and foes.rows[1]
  if not main then return end
  local F, before = M.FIELD, fields[M.FIELD.name]
  fields[F.name] = Place("names", main.name)
  local boss = fields[F.name] == before and fields[F.kind] == M.KINDS.worldboss
  if (main.kind or 0) > 0 and not boss then fields[F.kind] = main.kind end
end

local function Figures(fields, f, game)
  local F = M.FIELD
  local dmg = game and game.dmg or (f.hidden == 0 and f.seen or nil)
  local taken = game and game.taken or (f.hiddenOn == 0 and f.taken or nil)
  local max = f.hidden == 0 and f.max or nil
  local foes = game and game.foes or {}
  fields[F.dmg], fields[F.taken], fields[F.max] = dmg or 0, taken or 0, max or 0
  fields[F.foes], fields[F.main], fields[F.place] = M.FoesField(foes.n), foes.main or 0, f.place or 0
  Named(fields, foes)
  fields[F.flags] = (f.grouped and M.GROUPED or 0) + (f.changed and M.CHANGED or 0) + (f.died and M.DIED or 0)
    + (game and M.GAME or dmg and M.FROM_HITS or M.NO_DMG) + (taken and 0 or M.NO_TAKEN) + (max and 0 or M.NO_MAX)
  return dmg
end

local function Poll(job)
  if asking ~= job then return end
  local m = Store()
  local last = m and m.f[#m.f]
  if ns.InFight() or not last or StartOf(last) ~= job.t then return Missed() end
  local game = GameFigures(job.len, job.idle, job.ended)
  if game == "wait" then
    job.tries = job.tries + 1
    if job.tries < M.POLL_TRIES then return M.After(job) end
    return Missed()
  end
  asking = nil
  if game == "other" then return end
  local fields = M.Unpack(last)
  local dmg = Figures(fields, job.f, game)
  m.f[#m.f] = M.Pack(fields)
  local foes = game.foes and game.foes.rows or {}
  if #game.spells > 0 or #foes > 0 then
    local d = m.d[job.t] or {}
    if #game.spells > 0 then
      local rows = {}
      for i, sp in ipairs(game.spells) do rows[i] = M.SpellRow(sp) end
      d.sp, d.sg = rows, true
    end
    if #foes > 0 then
      local rows = {}
      for i, foe in ipairs(foes) do rows[i] = M.EnemyRow(foe) end
      d.en, d.ew = rows, game.foes.whole or nil
    end
    m.d[job.t] = d
  end
  M.added = (M.added or 0) + 1
  Tell("figures", job.f, dmg, job.len)
end
function M.After(job)
  Call(C_Timer and C_Timer.After, M.POLL_STEP, function()
    local ok, err = pcall(Poll, job)
    if not ok then ns.Report(ns.Word("game.meter.part.poll"), err) end
  end)
end

local function Finish()
  local f, m = cur, Store()
  cur = nil
  if not f then return end
  local len = math.max(0.1, (Number(Call(GetTime)) or f.t0) - f.t0)
  ended = f.t0 + len
  Tell("finish", f, len)
  if not m or (f.hits == 0 and f.casts == 0) then return Missed() end
  local F = M.FIELD
  local fields = {}
  fields[F.t], fields[F.len] = f.at, math.floor(len * 10 + 0.5)
  fields[F.act], fields[F.hits], fields[F.lvl] = math.floor(math.min(len, f.act) * 10 + 0.5), f.hits, f.lvl
  fields[F.gap], fields[F.kind] = f.gap and f.gap + M.GAP_BASE or 0, f.kind or 0
  local dmg = Figures(fields, f, nil)
  fields[F.w], fields[F.b], fields[F.g] = Place("w", f.w), Place("b", f.b), Place("g", f.g)
  fields[F.name], fields[F.xp] = Place("names", f.name), f.xp
  fields[F.cd] = CondField(f.rd, nil)
  fields[F.kills] = math.max(0, (ns.killXP and ns.killXP.next or 0) - f.gains)
  for i, kind in ipairs(M.OUT) do fields[F.out + i - 1] = f.out[kind] or 0 end
  for i, kind in ipairs(M.ON) do fields[F.on + i - 1] = f.on[kind] or 0 end
  local last = m.f[#m.f]
  if last and StartOf(last) >= fields[F.t] then fields[F.t] = StartOf(last) + 1 end
  m.f[#m.f + 1] = M.Pack(fields)
  if f.hidden == 0 then
    local line = {}
    for second = 1, math.min(M.LINE_MOST, math.ceil(len)) do line[second] = f.line[second] or 0 end
    m.d[fields[F.t]] = { ln = table.concat(line, ",") }
  end
  Trim(m)
  M.added = (M.added or 0) + 1
  Tell("figures", f, dmg, len)
  if not M.GameMeter() then return Missed() end
  asking = { t = fields[F.t], len = len, idle = f.idle, ended = ended, f = f, tries = 0 }
  M.After(asking)
end


local function SpellRow(sp)
  local misses = {}
  for kind, n in pairs(type(sp.m) == "table" and sp.m or {}) do misses[#misses + 1] = tostring(kind) .. "=" .. tostring(n) end
  table.sort(misses)
  return table.concat({ sp.id or 0, sp.d or 0, sp.h or 0, sp.c or 0, sp.tk or 0, sp.lo or 0, sp.hi or 0, sp.ok or 0 }, ",")
    .. ";" .. tostring(sp.by or "") .. ";" .. table.concat(misses, " ")
end
M.SpellRow = SpellRow
function M.EnemyRow(foe)
  return (tonumber(foe.d) or 0) .. "," .. (tonumber(foe.kind) or 0) .. ";" .. tostring(foe.name or "")
end
local function AuraRows(list)
  local rows = {}
  for i, a in ipairs(type(list) == "table" and list or {}) do
    rows[i] = table.concat({ a.id or 0, a.s or 0, a.x or 0 }, ",")
  end
  return rows
end

local function Foes(entries)
  local n, rows, by = nil, {}, {}
  for at, e in ipairs(entries) do
    if type(e.ne) == "number" then
      n = math.max(n or 0, e.ne)
      for _, foe in ipairs(type(e.en) == "table" and e.en or {}) do
        local name = type(foe) == "table" and type(foe.n) == "string" and foe.n
        if name then
          local row = at > 1 and by[name] or nil
          if not row then
            row = { name = name, d = 0, kind = M.KINDS[foe.c or ""] or 0 }
            by[name], rows[#rows + 1] = row, row
          end
          row.d = row.d + (tonumber(foe.d) or 0)
        end
      end
    end
  end
  if not n then return nil end
  table.sort(rows, function(a, b) return a.d > b.d end)
  n = math.max(n, #rows)
  while #rows > M.ENEMIES_KEPT do table.remove(rows) end
  return { n = n, rows = rows }
end

local function Held(entries)
  local by
  for _, e in ipairs(entries) do
    if type(e.cd) == "table" then
      by = by or {}
      for _, r in ipairs(e.cd) do
        local ok = type(r) == "table" and type(r[1]) == "string" and tonumber(r[2]) and type(r[3]) == "string"
        if ok then
          local g = by[r[1]] or { spells = {}, swap = false }
          by[r[1]] = g
          local spell = tonumber(r[2])
          local c = g.spells[spell] or { secs = 0, name = r[3] }
          g.spells[spell], c.secs = c, c.secs + (tonumber(r[4]) or 0)
          g.swap = g.swap or r[5] == 1
        end
      end
    end
  end
  if not by then return nil end
  local held = {}
  for group, g in pairs(by) do
    local best, kinds
    for spell, c in pairs(g.spells) do
      kinds = (kinds or 0) + 1
      if not best or c.secs > best.secs or c.secs == best.secs and spell < best.spell then
        best = { spell = spell, name = c.name, secs = c.secs }
      end
    end
    held[group] = { spell = best.spell, name = best.name, swap = g.swap or kinds > 1 }
  end
  return held
end

function M.Join(detail)
  local m = Store()
  local key = ns.CharKey and ns.CharKey()
  if not (m and type(detail) == "table" and type(detail.fights) == "table" and detail.char == key) then return 0 end
  local F, f = M.FIELD, m.f
  for group, word in pairs(type(detail.words) == "table" and detail.words or {}) do
    if type(group) == "string" and type(word) == "string" then m.cw[group] = word end
  end
  if type(detail.ench) == "table" then m.cr = { e = detail.ench } end
  local first = math.huge
  for _, e in ipairs(detail.fights) do
    if type(e) == "table" and type(e.t) == "number" then first = math.min(first, e.t) end
  end
  local newest, from = {}, #f
  while from >= 1 do
    local fields = M.Unpack(f[from])
    local start, stop = fields[F.t], fields[F.t] + fields[F.len] / 10
    if stop + M.JOIN_SLACK < first then break end
    newest[#newest + 1] = { at = from, t = start, stop = stop, fields = fields }
    from = from - 1
  end
  local spans, n = {}, #newest
  for i = 1, n do spans[i] = newest[n + 1 - i] end
  local taken = {}
  for _, e in ipairs(detail.fights) do
    if type(e) == "table" and type(e.t) == "number" then
      local lo, hi = 1, n
      while lo <= hi do
        local mid = math.floor((lo + hi) / 2)
        if spans[mid].t <= e.t + M.JOIN_SLACK then lo = mid + 1 else hi = mid - 1 end
      end
      local best
      for i = math.max(1, hi - 2), hi do
        local s = spans[i]
        if e.t >= s.t - M.JOIN_SLACK and e.t <= s.stop + M.JOIN_SLACK
          and (not best or math.abs(e.t - s.t) < math.abs(e.t - best.t)) then
          best = s
        end
      end
      if best then
        taken[best] = taken[best] or {}
        table.insert(taken[best], e)
      end
    end
  end
  local joined = 0
  for s, entries in pairs(taken) do
    local fields, dmg, taken, max = s.fields, 0, nil, nil
    for _, e in ipairs(entries) do
      dmg = dmg + (tonumber(e.dmg) or 0) - (tonumber(e.ok) or 0)
      if type(e.on) == "table" then taken = (taken or 0) + (tonumber(e.on.d) or 0) end
      for _, sp in ipairs(type(e.sp) == "table" and e.sp or {}) do max = math.max(max or 0, tonumber(sp.hi) or 0) end
    end
    local flags = fields[F.flags]
    for _, bit in ipairs({ M.FROM_HITS, M.GAME, M.NO_DMG }) do
      if Has(flags, bit) then flags = flags - bit end
    end
    if Has(flags, M.NO_TAKEN) and taken then flags, fields[F.taken] = flags - M.NO_TAKEN, taken end
    if Has(flags, M.NO_MAX) and max then flags, fields[F.max] = flags - M.NO_MAX, max end
    if not Has(flags, M.DETAIL) then flags = flags + M.DETAIL end
    fields[F.dmg], fields[F.flags] = dmg, flags
    local foes = Foes(entries)
    if foes then
      fields[F.foes] = M.FoesField(foes.n)
      fields[F.main] = foes.rows[1] and dmg > 0 and math.max(1, math.floor(100 * foes.rows[1].d / dmg + 0.5)) or 0
      Named(fields, foes)
    end
    local held = Held(entries)
    if held then fields[F.cd] = CondField(M.Conds(fields), held) end
    f[s.at] = M.Pack(fields)
    if s.at > #f - M.LINES_KEPT then
      local line, seconds, any = {}, math.min(M.LINE_MOST, math.ceil(fields[F.len] / 10)), false
      for second = 1, seconds do line[second] = 0 end
      for _, e in ipairs(entries) do
        if type(e.ln) == "string" then
          any = true
          local from = e.t - fields[F.t]
          for i, amount in ipairs(M.Unpack(e.ln)) do
            local second = math.max(1, math.min(seconds, from + i))
            line[second] = line[second] + amount
          end
        end
      end
      if any and seconds > 0 then
        local d = m.d[fields[F.t]] or {}
        d.ln = table.concat(line, ",")
        m.d[fields[F.t]] = d
      end
    end
    if s.at > #f - M.SPELLS_KEPT then
      local rows, up, down = {}, {}, {}
      for _, e in ipairs(entries) do
        for _, sp in ipairs(type(e.sp) == "table" and e.sp or {}) do rows[#rows + 1] = SpellRow(sp) end
        for _, row in ipairs(AuraRows(e.up)) do up[#up + 1] = row end
        for _, row in ipairs(AuraRows(e.down)) do down[#down + 1] = row end
      end
      local d = m.d[fields[F.t]] or {}
      d.sp, d.sg, d.up, d.down = rows, nil, up, down
      if foes then
        d.en, d.ew = {}, nil
        for i, foe in ipairs(foes.rows) do d.en[i] = M.EnemyRow(foe) end
      end
      m.d[fields[F.t]] = d
    end
    joined = joined + 1
  end
  if joined > 0 then M.added = (M.added or 0) + 1 end
  return joined
end


local S = {}
M.Stats = S
M.STEP = 500
M.SHORT = 50
M.MIN_FIGHTS = 5
M.ROLLING = 10

function M.Opts()
  local m = Store()
  if not m then return { solo = true, gap = "all", kind = "all", when = "all", foes = "single", place = "all", dim = "w" } end
  if type(m.opts) ~= "table" then m.opts = {} end
  local o = m.opts
  if o.solo == nil then o.solo = true end
  o.gap, o.kind, o.when, o.dim = o.gap or "all", o.kind or "all", o.when or "all", o.dim or "w"
  o.foes, o.place = o.foes or "single", o.place or "all"
  return o
end
function M.Split()
  local split = M.Opts().split
  if not split then return nil end
  for _, g in ipairs(M.CondGroups()) do
    if g.key == split then return split end
  end
  return nil
end

M.Has = Has
local ELITE = { [2] = true, [3] = true, [5] = true }

function S.Rate(dmg, secs) return secs > 0 and dmg / secs or 0 end
function S.Dps(fields) return S.Rate(fields[M.FIELD.dmg], fields[M.FIELD.len] / 10) end

function S.Begin()
  local m, o = Store(), M.Opts()
  local now = time()
  local midnight = date("*t", now)
  midnight.hour, midnight.min, midnight.sec = 0, 0, 0
  return { i = 0, all = m and #m.f or 0, done = not m or #m.f == 0, added = M.added, split = M.Split(),
           solo = o.solo, gap = o.gap, kind = o.kind, when = o.when, foes = o.foes, place = o.place, noFoes = 0, noPlace = 0, byKills = 0, noCond = 0,
           since = o.when == "today" and time(midnight) or o.when == "week" and now - 7 * 86400 or 0,
           level = o.when == "level" and (Number(Call(UnitLevel, "player")) or 0) or nil,
           at = {}, dps = {}, n = 0, sum = 0, dmg = 0, secs = 0, groups = { w = {}, b = {}, g = {} } }
end

function S.Fresh(st)
  local o = M.Opts()
  return st ~= nil and st.added == M.added and st.solo == o.solo and st.gap == o.gap and st.kind == o.kind and st.when == o.when
    and st.foes == o.foes and st.place == o.place and st.split == M.Split()
end

local function Passes(st, fields)
  local F = M.FIELD
  if Has(fields[F.flags], M.NO_DMG) then return false end
  if st.solo and Has(fields[F.flags], M.GROUPED) then return false end
  if fields[F.len] < M.SHORT or fields[F.t] < st.since then return false end
  if st.level and fields[F.lvl] ~= st.level then return false end
  if st.kind ~= "all" and (st.kind == "elite") ~= (ELITE[fields[F.kind]] or false) then return false end
  if st.gap ~= "all" then
    local gap = fields[F.gap]
    if gap == 0 then return false end
    gap = gap - M.GAP_BASE
    if st.gap == "lower" and gap > -3 or st.gap == "even" and (gap < -2 or gap > 1) or st.gap == "higher" and gap < 2 then
      return false
    end
  end
  if st.foes ~= "all" then
    local multi, byKills = M.Multi(fields)
    if multi == nil then st.noFoes = st.noFoes + 1; return false end
    if (st.foes == "multi") ~= multi then return false end
    if byKills then st.byKills = st.byKills + 1 end
  end
  if st.place ~= "all" then
    local place = M.Place(fields)
    if not place then st.noPlace = st.noPlace + 1; return false end
    if (st.place == "dungeon") ~= (place == M.DUNGEON) then return false end
  end
  return true
end

S.Passes = Passes

function S.Step(st, most)
  local m = Store()
  if not m or st.done then st.done = true; return end
  local F, f = M.FIELD, m.f
  local upto = math.min(st.all, #f, st.i + (most or M.STEP))
  for i = st.i + 1, upto do
    local fields = M.Unpack(f[i])
    if Passes(st, fields) then
      local dps, len = S.Dps(fields), fields[F.len] / 10
      st.n, st.sum, st.dmg, st.secs = st.n + 1, st.sum + dps, st.dmg + fields[F.dmg], st.secs + len
      st.at[st.n], st.dps[st.n] = i, dps
      local conds = st.split and M.Conds(fields, st.split)
      local held = conds and conds[st.split]
      local changed = Has(fields[F.flags], M.CHANGED)
      if st.split and not conds and not changed then st.noCond = st.noCond + 1 end
      if not changed and (conds or not st.split) then
        for _, dim in ipairs({ "w", "b", "g" }) do
          local place = fields[F[dim]]
          local key = st.split and (place .. ";" .. (held and held.spell or 0)) or place
          local g = st.groups[dim][key]
          if not g then
            g = { key = key, place = place, n = 0, sum = 0, sq = 0, secs = 0, taken = 0, tookN = 0, hits = 0, crit = 0, miss = 0, xp = 0, last = 0 }
            if st.split then g.cond, g.condName = held and held.spell or 0, held and held.name end
            st.groups[dim][key] = g
          end
          g.n, g.sum, g.sq = g.n + 1, g.sum + dps, g.sq + dps * dps
          g.secs, g.xp, g.last = g.secs + len, g.xp + fields[F.xp], fields[F.t]
          if not Has(fields[F.flags], M.NO_TAKEN) then g.taken, g.tookN = g.taken + fields[F.taken], g.tookN + 1 end
          g.hits, g.crit, g.miss = g.hits + fields[F.hits], g.crit + fields[F.out + 1], g.miss + fields[F.out + 5]
        end
      end
    end
  end
  st.i = upto
  st.done = upto >= math.min(st.all, #f)
end

function S.Groups(st, dim)
  local out, setups = {}, {}
  for _, g in pairs(st.groups[dim] or {}) do
    local s = setups[g.place] or { n = 0, last = 0 }
    s.n, s.last = s.n + g.n, math.max(s.last, g.last)
    setups[g.place] = s
  end
  for _, g in pairs(st.groups[dim] or {}) do
    g.mean = g.sum / g.n
    g.sd = g.n > 1 and math.sqrt(math.max(0, (g.sq - g.n * g.mean * g.mean) / (g.n - 1))) or 0
    g.se = g.n > 1 and g.sd / math.sqrt(g.n) or 0
    g.kill, g.each = g.secs / g.n, g.tookN > 0 and g.taken / g.tookN or nil
    g.critShare, g.missShare = g.hits > 0 and g.crit / g.hits or 0, g.hits > 0 and g.miss / g.hits or 0
    g.xpHour = g.secs > 0 and g.xp / g.secs * 3600 or 0
    out[#out + 1] = g
  end
  table.sort(out, function(a, b)
    local sa, sb = setups[a.place], setups[b.place]
    if sa.n ~= sb.n then return sa.n > sb.n end
    if sa.last ~= sb.last then return sa.last > sb.last end
    if a.place ~= b.place then return a.place < b.place end
    if a.n ~= b.n then return a.n > b.n end
    return a.last > b.last
  end)
  return out
end

function S.Verdict(a, b)
  if a.n < M.MIN_FIGHTS or b.n < M.MIN_FIGHTS then return "few", a, b end
  if b.mean > a.mean then a, b = b, a end
  local gap = a.mean - b.mean
  local se = math.sqrt(a.sd * a.sd / a.n + b.sd * b.sd / b.n)
  if gap > 2 * se and b.mean > 0 then return "win", a, b end
  if gap < 0.01 * a.mean then return "same", a, b end
  local need = math.ceil(4 * (a.sd * a.sd + b.sd * b.sd) / (gap * gap))
  return "close", a, b, math.max(1, need - math.min(a.n, b.n))
end

function S.Rolling(values, span)
  local out, sum = {}, 0
  for i, v in ipairs(values) do
    sum = sum + v
    if i > span then sum = sum - values[i - span] end
    out[i] = sum / math.min(i, span)
  end
  return out
end

function M.Store() return Store() end

ns.On("PLAYER_REGEN_DISABLED", Start)
ns.On("PLAYER_REGEN_ENABLED", Finish)
ns.On("UNIT_COMBAT", Combat)
ns.On("UNIT_SPELLCAST_SUCCEEDED", Cast, "player")
ns.On("PLAYER_XP_UPDATE", GainedXP)
ns.On("PLAYER_DEAD", function() if cur then cur.died = true end end)
ns.On("PLAYER_TARGET_CHANGED", function() if cur then Target(cur) end end)
ns.On({ "PLAYER_EQUIPMENT_CHANGED", "TRAIT_CONFIG_UPDATED", "PLAYER_TALENT_UPDATE", "ACTIVE_TALENT_GROUP_CHANGED" }, function()
  setup.dirty = true
  if cur then cur.changed = true end
end)
ns.On("PLAYER_LOGIN", function()
  if Store() then
    M.Join(IndexOfAzerothMeterDetail)
    Read()
  end
end)
ns.On({ "UNIT_INVENTORY_CHANGED", "UNIT_PET" }, function() if not cur then Read() end end, "player")
ns.On({ "PLAYER_EQUIPMENT_CHANGED", "WEAPON_ENCHANT_CHANGED", "PLAYER_REGEN_ENABLED" }, function()
  if not cur then Read() end
end)
