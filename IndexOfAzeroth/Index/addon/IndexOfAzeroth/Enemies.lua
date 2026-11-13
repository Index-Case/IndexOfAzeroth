-- The Index of Azeroth. Copyright 2026 Index Case <indexofazeroth@pm.me>. PolyForm Strict 1.0.0, see LICENSE.md.
local ADDON, ns = ...

local Plain, Call, PlainText, PlainNumber = ns.Plain, ns.Call, ns.PlainText, ns.PlainNumber

local FRAME = 48
local LOOK_AGAIN = 60
local MOST_WAITING = 60
local SENDS = 2
local TEXT_MOST = 24
local MOST_KNOWN = 2000

local looked = {}
local said = {}
local known = 0
local waiting = {}
local seen = 0

local function Title(unit)
  local shown, name = PlainText(Call(UnitPVPName, unit)), PlainText(Call(UnitName, unit))
  if not shown or not name or shown == name then return nil end
  local at = shown:find(name, 1, true)
  if not at then return nil end
  local title = (shown:sub(1, at - 1) .. shown:sub(at + #name)):gsub("^[%s,]+", ""):gsub("[%s,]+$", "")
  return title ~= "" and title or nil
end

local function Read(unit)
  if not Plain(Call(UnitIsPlayer, unit)) then return end
  if not (Plain(Call(UnitIsEnemy, "player", unit)) or Plain(Call(UnitCanAttack, "player", unit))) then return end
  local guid = PlainText(Call(UnitGUID, unit))
  if not guid then return end
  local server, number = guid:match("^Player%-(%d+)%-(%x+)$")
  if not server then return end
  local now = GetTime()
  if looked[guid] and now - looked[guid] < LOOK_AGAIN then return end
  if known >= MOST_KNOWN then wipe(looked); wipe(said); known = 0 end
  looked[guid] = now
  local level, least = PlainNumber(Call(UnitLevel, unit)), nil
  if level == -1 then
    local mine = PlainNumber(Call(UnitLevel, "player"))
    level, least = nil, mine and mine + 10
  elseif level and level < 1 then
    level = nil
  end
  local _, _, class = Call(UnitClass, unit)
  local _, _, race = Call(UnitRace, unit)
  local sex = PlainNumber(Call(UnitSex, unit))
  local s = { server = tonumber(server), number = tonumber(number, 16), t = now, level = level, least = least,
              class = PlainNumber(class), race = PlainNumber(race), sex = (sex == 2 or sex == 3) and sex or nil,
              guild = PlainText(Call(GetGuildInfo, unit)), title = Title(unit), sent = 0 }
  local now_said = table.concat({ tostring(s.level), tostring(s.least), tostring(s.class), tostring(s.race),
                                  tostring(s.sex), s.guild or "", s.title or "" }, "|")
  if said[guid] == now_said then return end
  if not said[guid] then seen, known = seen + 1, known + 1 end
  said[guid] = now_said
  for i = #waiting, 1, -1 do
    if waiting[i].server == s.server and waiting[i].number == s.number then table.remove(waiting, i) end
  end
  waiting[#waiting + 1] = s
  while #waiting > MOST_WAITING do table.remove(waiting, 1) end
end

ns.On({ "PLAYER_TARGET_CHANGED", "UPDATE_MOUSEOVER_UNIT", "NAME_PLATE_UNIT_ADDED" }, function(event, unit)
  if event == "PLAYER_TARGET_CHANGED" then Read("target")
  elseif event == "UPDATE_MOUSEOVER_UNIT" then Read("mouseover")
  elseif type(unit) == "string" and unit:find("^nameplate") then Read(unit)
  end
end)

function ns.EnemiesDue() return #waiting > 0 end

function ns.EncodeEnemies()
  if #waiting == 0 then return nil end
  local now = GetTime()
  local w = ns.NewWriter()
  w:u8(FRAME)
  local n = ns.WriteFitting(w, waiting, function(part, s)
    part:u16(s.server)
    ns.WriteU32(part, s.number)
    part:u16(math.min(65535, math.floor(now - s.t)))
    if s.least then
      part:u8(255); part:u8(math.min(254, s.least))
    else
      part:u8(s.level and math.min(254, s.level) or 0)
    end
    part:u8(s.class or 0); part:u8(s.race or 0); part:u8(s.sex or 0)
    part:str(s.guild, TEXT_MOST); part:str(s.title, TEXT_MOST)
  end)
  for i = n, 1, -1 do
    local s = waiting[i]
    s.sent = s.sent + 1
    if s.sent >= SENDS then table.remove(waiting, i) end
  end
  return w.bytes
end

ns.commands = ns.commands or {}
ns.commands.enemies = function()
  if not ns.Print then return end
  ns.Print(ns.Count("game.chat.enemies.seen", seen))
  if #waiting > 0 then ns.Print(ns.Count("game.chat.enemies.waiting", #waiting)) end
end
