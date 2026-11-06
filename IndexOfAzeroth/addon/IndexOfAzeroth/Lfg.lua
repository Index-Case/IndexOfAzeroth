-- The Index of Azeroth. Copyright 2026 Index Case <indexofazeroth@pm.me>. PolyForm Strict 1.0.0, see LICENSE.md.
local ADDON, ns = ...

local Plain, Call, PlainText, PlainNumber = ns.Plain, ns.Call, ns.PlainText, ns.PlainNumber
local G = ns.GUIDE

local lfg = {}
ns.Lfg = lfg

lfg.SAID = { tank = "Tank", healer = "Healer", damage = "DPS" }
lfg.GROUP_ROLE = { TANK = "tank", HEALER = "healer", DAMAGER = "damage" }
lfg.BEAR_FORMS = { [5] = true, [8] = true }
lfg.AGAIN = 15

function lfg.Trees(class)
  local sh = IndexOfAzerothShared
  local roles = type(sh) == "table" and type(sh.roles) == "table" and sh.roles[tostring(class)]
  return type(roles) == "table" and roles or nil
end

function lfg.Tree()
  local points, most, tree = ns.Talents().points, 0, nil
  for t, n in ipairs(points) do
    if n > most then most, tree = n, t elseif n == most and most > 0 then tree = nil end
  end
  if tree then return tree, "points", points end
  local spec = C_SpecializationInfo
  local primary = PlainNumber(Call(spec and spec.GetSpecialization))
  if primary and primary >= 1 and primary <= #points then return primary, "primary", points end
  return nil, nil, points
end

local function OneRole(roles)
  local one
  for _, r in ipairs(roles or {}) do
    if one and r ~= one then return nil end
    one = r
  end
  return one
end

function lfg.Role()
  local trees = lfg.Trees(PlainNumber(select(3, Call(UnitClass, "player"))) or 0)
  local group = lfg.GROUP_ROLE[PlainText(Call(UnitGroupRolesAssigned, "player")) or ""]
  local all = {}
  for _, roles in ipairs(trees or {}) do
    for _, r in ipairs(type(roles) == "table" and roles or {}) do all[#all + 1] = r end
  end
  local one = OneRole(all)
  if one then return lfg.SAID[one] end
  local tree = lfg.Tree()
  local roles = trees and tree and type(trees[tree]) == "table" and trees[tree] or {}
  local has = {}
  for _, r in ipairs(roles) do has[r] = true end
  if #roles == 0 then return group and lfg.SAID[group] end
  if OneRole(roles) then return lfg.SAID[roles[1]] end
  if group and has[group] then return lfg.SAID[group] end
  if has.tank and lfg.BEAR_FORMS[PlainNumber(Call(GetShapeshiftFormID)) or 0] then return lfg.SAID.tank end
  return lfg.SAID[has.damage and "damage" or roles[1]]
end

function lfg.DungeonName(s)
  local name = s.name ~= "" and s.name or nil
  if not name and not lfg.byQuest then
    lfg.byQuest = {}
    for _, d in ipairs(ns.Dungeons or {}) do
      for _, q in ipairs(d.quests or {}) do lfg.byQuest[q.id] = lfg.byQuest[q.id] or d.name end
    end
  end
  for _, id in ipairs(not name and s.ids or {}) do name = name or lfg.byQuest[id] end
  return name and (name:gsub("^The ", "")) or nil
end

function lfg.Next(g, i)
  local s = g and i and g.steps[i]
  if s and s.kind ~= "D" then
    s = nil
    for k = i + 1, #g.steps do
      if g.state[k] == G.TODO or g.state[k] == G.WAIT then
        if g.steps[k].kind == "D" then s = g.steps[k] end
        break
      end
    end
  end
  if not s or (ns.GuideBossTrack and ns.GuideBossTrack(g, s)) then return nil end
  return lfg.DungeonName(s)
end

function lfg.General()
  if Plain(Call(IsInInstance)) then return nil, "There's no General channel inside an instance" end
  local id = PlainNumber(Call(C_ChatInfo and C_ChatInfo.GetGeneralChannelLocalID))
  if not id then
    local list = { Call(GetChannelList) }
    for k = 1, #list - 1 do
      local n, name = PlainNumber(list[k]), PlainText(list[k + 1])
      if not id and n and name and name:match("^General") then id = n end
    end
  end
  if not id or id < 1 then return nil, "This zone has no General channel" end
  return id, id .. ". " .. (PlainText(select(2, Call(GetChannelName, id))) or "General")
end

function lfg.Message(dungeon)
  local words = { "LFG", dungeon }
  local class, level, role = PlainText(Call(UnitClass, "player")), PlainNumber(Call(UnitLevel, "player")), lfg.Role()
  if class then words[#words + 1] = class end
  if level then words[#words + 1] = tostring(level) end
  if role then words[#words + 1] = role end
  return table.concat(words, " ")
end

function lfg.Post(dungeon)
  local now = GetTime()
  if lfg.postedAt and now - lfg.postedAt < lfg.AGAIN then
    return string.format("The addon posted %d s ago and can post again after %d s", math.floor(now - lfg.postedAt), lfg.AGAIN)
  end
  local id, where = lfg.General()
  if not id then return where .. ", so the addon posted nothing" end
  if Plain(Call(C_ChatInfo and C_ChatInfo.InChatMessagingLockdown)) then return "The game is holding chat right now, so the addon posted nothing" end
  local msg = lfg.Message(dungeon)
  local ok, err = pcall((C_ChatInfo and C_ChatInfo.SendChatMessage) or SendChatMessage, msg, "CHANNEL", nil, id)
  if not ok then return "The game didn't post the message: " .. tostring(err) end
  lfg.postedAt = now
  return string.format("The addon posted in %s: %s", where, msg)
end

function lfg.Tip(owner, dungeon)
  local C = ns.UI.C
  local id, where = lfg.General()
  GameTooltip:SetOwner(owner, "ANCHOR_BOTTOM")
  GameTooltip:AddLine("Looking for group: " .. dungeon, C.gold[1], C.gold[2], C.gold[3])
  if id then
    GameTooltip:AddLine("Click to post this in " .. where .. ":", C.muted[1], C.muted[2], C.muted[3])
    GameTooltip:AddLine(lfg.Message(dungeon), C.ivory[1], C.ivory[2], C.ivory[3], true)
  else
    GameTooltip:AddLine(where .. ", so a click posts nothing.", C.yellow[1], C.yellow[2], C.yellow[3], true)
  end
  GameTooltip:Show()
end

function lfg.Print()
  local g = ns.GuideInfo() or (ns.PastedGuide and ns.PastedGuide())
  local dungeon = g and ns.GuideShown and lfg.Next(g, select(2, ns.GuideShown(g)))
  local id, where = lfg.General()
  ns.Print(dungeon and ("The card's LFG key is up for " .. dungeon .. ".") or "The card has no LFG key, because the quest epic doesn't lead into a dungeon next.")
  ns.Print(id and ("The key posts in " .. where .. ": " .. lfg.Message(dungeon or "<dungeon>"))
    or (where .. ". The key would post: " .. lfg.Message(dungeon or "<dungeon>")))
  local tree, from, points = lfg.Tree()
  ns.Print(string.format("talent points %s, tree %s%s, shapeshift form %s, group role %s, role %s",
    #points > 0 and table.concat(points, "/") or "none", tostring(tree), from and (" (" .. from .. ")") or "",
    tostring(PlainNumber(Call(GetShapeshiftFormID))), tostring(PlainText(Call(UnitGroupRolesAssigned, "player"))),
    tostring(lfg.Role())))
  ns.Print("The talent calls gave: " .. ns.Talents().read)
end


function lfg.QuestDungeon(id)
  return id and lfg.DungeonName({ ids = { id } }) or nil
end

function lfg.LogShow(id)
  local key = lfg.logKey
  if not key then return end
  key.dungeon = lfg.QuestDungeon(PlainNumber(id))
  key:SetShown(key.dungeon ~= nil)
end

function lfg.LogSetUp()
  local details = QuestMapFrame and QuestMapFrame.DetailsFrame
  if lfg.logKey or not details or not hooksecurefunc or type(QuestMapFrame_ShowQuestDetails) ~= "function" then return end
  local key = ns.UI.FlatButton(details, "LFG", 52, function(self) if self.dungeon then ns.Print(lfg.Post(self.dungeon)) end end)
  local back = details.BackFrame and details.BackFrame.BackButton
  if back then key:SetPoint("LEFT", back, "RIGHT", 6, 0) else key:SetPoint("TOPRIGHT", details, "TOPRIGHT", -6, -4) end
  key:SetFrameLevel(details:GetFrameLevel() + 10)
  key:HookScript("OnEnter", function(self) if self.dungeon then lfg.Tip(self, self.dungeon) end end)
  key:HookScript("OnLeave", function() GameTooltip:Hide() end)
  key:Hide()
  lfg.logKey = key
  hooksecurefunc("QuestMapFrame_ShowQuestDetails", lfg.LogShow)
end
ns.On("PLAYER_LOGIN", lfg.LogSetUp)
ns.On("ADDON_LOADED", function(_, name) if name == "Blizzard_WorldMap" then lfg.LogSetUp() end end)


local Q_LISTED, Q_APPLIED, Q_QUEUED, Q_INVITE, Q_MATCH, Q_GROUP, Q_LEAD = 1, 2, 4, 8, 16, 32, 64
local Q_FINDER = Q_LISTED + Q_APPLIED + Q_QUEUED
local E_INVITE, E_JOINED, E_FORMED, E_FULL, E_GONE = 1, 2, 3, 4, 5
local S_INVITE, S_LISTING, S_FINDER = 1, 2, 3
lfg.Q = { listed = Q_LISTED, applied = Q_APPLIED, queued = Q_QUEUED, invite = Q_INVITE, match = Q_MATCH, group = Q_GROUP,
          lead = Q_LEAD }
lfg.QUEUE_EVERY = 10
lfg.QUEUE_LINGER = 120
lfg.FINDER_RECENT = 180
lfg.INVITE_OPEN = 120
lfg.JOIN_SAID = 10
lfg.CATEGORIES = 7
lfg.NO_TIME = 65535

local queue = { n = 0, inGroup = false, ready = false, finderAt = nil, since = nil, activeAt = -math.huge,
                sentAt = -math.huge, changed = false, names = {} }
lfg.queue = queue

local function Has(flags, bit) return flags % (bit * 2) >= bit end

local function Activities(entry, names)
  local ids, most = {}, 0
  if type(entry) ~= "table" then return most end
  local list = Plain(entry.activityIDs)
  if type(list) == "table" then for _, id in ipairs(list) do ids[#ids + 1] = id end end
  if #ids == 0 and PlainNumber(entry.activityID) then ids[1] = entry.activityID end
  for _, id in ipairs(ids) do
    local info = Plain(Call(C_LFGList.GetActivityInfoTable, id))
    info = type(info) == "table" and info or {}
    local name = PlainText(info.fullName)
    if name then names[#names + 1] = name end
    most = math.max(most, PlainNumber(info.maxNumPlayers) or 0)
  end
  return most
end

local function Queued(cat, names)
  local mine = {}
  local list = Plain(Call(GetLFGQueuedList, cat, mine))
  for k, v in pairs(type(list) == "table" and list or mine) do
    local id = v == true and k or v
    local name = PlainText(Call(GetLFGDungeonInfo, id))
    if name then names[#names + 1] = name end
  end
end

local function Leader()
  for i = 1, 4 do
    if Plain(Call(UnitIsGroupLeader, "party" .. i)) then return PlainText(Call(UnitName, "party" .. i)) end
  end
end

function lfg.QueueState()
  local now, L, flags, names, most, queuedAt = GetTime(), C_LFGList, 0, {}, 0, nil
  local entry = L and Plain(Call(L.HasActiveEntryInfo)) and Plain(Call(L.GetActiveEntryInfo))
  if type(entry) == "table" then flags, most = flags + Q_LISTED, Activities(entry, names) end
  local apps = L and Plain(Call(L.GetApplications))
  local applied, invited = false, false
  for _, id in ipairs(type(apps) == "table" and apps or {}) do
    local _, status, pending = Call(L.GetApplicationInfo, id)
    status, pending = PlainText(status), PlainText(pending)
    if status == "invited" then invited = true elseif status == "applied" or pending then applied = true end
    if status == "invited" or status == "applied" or pending then Activities(Plain(Call(L.GetSearchResultInfo, id)), names) end
  end
  local queued, match = false, Plain(Call(GetLFGProposal)) and true or false
  for cat = 1, lfg.CATEGORIES do
    local mode = PlainText(Call(GetLFGMode, cat))
    if mode == "queued" or mode == "rolecheck" or mode == "suspended" then
      queued = true
      Queued(cat, names)
      local at = PlainNumber(select(17, Call(GetLFGQueueStats, cat)))
      if at and at > 0 then queuedAt = math.min(queuedAt or at, at) end
    elseif mode == "proposal" then
      match = true
    end
  end
  if queue.invite and now - queue.invite.at >= lfg.INVITE_OPEN then queue.invite = nil end
  if applied then flags = flags + Q_APPLIED end
  if queued then flags = flags + Q_QUEUED end
  if invited or queue.invite then flags = flags + Q_INVITE end
  if match then flags = flags + Q_MATCH end
  local inGroup = Plain(Call(IsInGroup)) and true or false
  if inGroup then flags = flags + Q_GROUP end
  if inGroup and Plain(Call(UnitIsGroupLeader, "player")) then flags = flags + Q_LEAD end
  queue.since = flags % (Q_FINDER + 1) > 0 and (queuedAt or queue.since or now) or nil
  if flags % (Q_MATCH * 2) > 0 then queue.finderAt, queue.activeAt = now, now end
  local seen, what = {}, {}
  for _, name in ipairs(names) do
    if not seen[name] then seen[name], what[#what + 1] = true, name end
  end
  return { flags = flags, what = table.concat(what, ", "), most = most, members = inGroup and (PlainNumber(Call(GetNumGroupMembers)) or 0) or 0,
           since = queue.since }
end

local function Changed()
  queue.changed = true
  if ns.MarkChanged then ns.MarkChanged("queue") end
end

local function Happened(kind, source, name)
  queue.n = queue.n % 255 + 1
  queue.event = { kind = kind, source = source, name = name or "", at = GetTime() }
  queue.activeAt = queue.event.at
  Changed()
  ns.queueDirty = true
end

local function InFinder(now)
  return queue.finderAt ~= nil and now - queue.finderAt < lfg.FINDER_RECENT
end

function lfg.QueueRefresh()
  local s, now = lfg.QueueState(), GetTime()
  local inGroup, e = Has(s.flags, Q_GROUP), queue.event
  if inGroup and not queue.inGroup and queue.ready and (queue.invite or InFinder(now)) then
    if not (e and e.kind == E_FORMED and now - e.at < lfg.JOIN_SAID) then
      local invite = queue.invite or {}
      Happened(E_JOINED, invite.source or S_LISTING, invite.name or queue.joinName or Leader())
    end
  end
  if inGroup then queue.invite, queue.joinName = nil, nil end
  queue.inGroup, queue.ready = inGroup, true
  if Has(s.flags, Q_LEAD) and Has(s.flags, Q_LISTED) and s.most > 0 and s.members >= s.most then
    if not queue.fullSaid then
      queue.fullSaid = true
      Happened(E_FULL, S_LISTING, s.what)
    end
  else
    queue.fullSaid = false
  end
  if now - queue.activeAt < lfg.QUEUE_LINGER then Changed() end
end

function lfg.EncodeQueue()
  local s, now, e = lfg.QueueState(), GetTime(), queue.event
  local w = ns.NewWriter()
  w:u8(30); w:u8(s.flags); w:str(s.what, 60); w:u8(s.members); w:u8(s.most); w:u8(queue.n)
  if queue.n > 0 then w:u8(e.kind); w:u8(e.source); w:str(e.name, 40) end
  local part = #w.bytes
  w:u16(s.since and math.min(lfg.NO_TIME - 1, now - s.since) or lfg.NO_TIME)
  if queue.n > 0 then w:u16(math.min(lfg.NO_TIME - 1, now - e.at)) end
  queue.changed, queue.sentAt = false, now
  return w.bytes, part
end

function lfg.QueueDue()
  local now = GetTime()
  return queue.changed or (now - queue.sentAt >= lfg.QUEUE_EVERY and now - queue.activeAt < lfg.QUEUE_LINGER)
end

local function Refreshed() lfg.QueueRefresh() end
ns.On({ "PLAYER_ENTERING_WORLD", "GROUP_ROSTER_UPDATE", "GROUP_JOINED", "GROUP_FORMED", "GROUP_LEFT", "LFG_UPDATE",
        "LFG_QUEUE_STATUS_UPDATE", "LFG_ROLE_CHECK_SHOW", "LFG_ROLE_CHECK_HIDE", "LFG_LIST_ACTIVE_ENTRY_UPDATE",
        "LFG_LIST_ENTRY_EXPIRED_TIMEOUT", "LFG_LIST_ENTRY_EXPIRED_TOO_MANY_PLAYERS" }, Refreshed)

ns.On("PARTY_INVITE_REQUEST", function(_, name)
  local now, e = GetTime(), queue.event
  lfg.QueueState()
  if not InFinder(now) then return end
  queue.invite = { name = PlainText(name), at = now, source = S_INVITE }
  if e and e.kind == E_INVITE and now - e.at < 5 then
    if e.name == "" then e.name = PlainText(name) or "" end
    return Changed()
  end
  Happened(E_INVITE, S_INVITE, PlainText(name))
end)
ns.On("PARTY_INVITE_CANCEL", function()
  local invite = queue.invite
  if not invite then return end
  queue.invite = nil
  Happened(E_GONE, S_INVITE, invite.name)
end)
if hooksecurefunc then
  pcall(hooksecurefunc, "DeclineGroup", function()
    if queue.invite then queue.invite = nil; Changed() end
  end)
end

local GONE = { declined = true, declined_full = true, declined_delisted = true, timedout = true }
ns.On("LFG_LIST_APPLICATION_STATUS_UPDATED", function(_, id, new, _, groupName)
  new, groupName = PlainText(new), PlainText(groupName) or queue.names[id]
  queue.names[id] = groupName
  if new == "invited" then Happened(E_INVITE, S_LISTING, groupName)
  elseif new == "inviteaccepted" then queue.joinName = groupName
  elseif GONE[new] then Happened(E_GONE, S_LISTING, groupName) end
  lfg.QueueRefresh()
end)
ns.On("LFG_LIST_JOINED_GROUP", function(_, _, groupName)
  queue.joinName = PlainText(groupName) or queue.joinName
  lfg.QueueRefresh()
end)

local function MatchName() return PlainText(select(5, Call(GetLFGProposal))) or queue.matchName end
ns.On("LFG_PROPOSAL_SHOW", function()
  queue.matchName = MatchName()
  Happened(E_INVITE, S_FINDER, queue.matchName)
  lfg.QueueRefresh()
end)
ns.On("LFG_PROPOSAL_SUCCEEDED", function()
  Happened(E_FORMED, S_FINDER, MatchName())
  lfg.QueueRefresh()
end)
ns.On("LFG_PROPOSAL_FAILED", function()
  Happened(E_GONE, S_FINDER, MatchName())
  lfg.QueueRefresh()
end)

local EVENT_WORDS = { "an invite to answer", "a group joined", "the dungeon finder's group formed", "your group full", "gone" }
local SOURCE_WORDS = { "a party invite", "a listed group", "the dungeon finder" }

function lfg.PrintQueue()
  local L, I = C_LFGList, C_LFGInfo
  local style = PlainNumber(Call(L and L.GetPremadeGroupFinderStyle))
  ns.Print(string.format("group finder style %s (0 off, 1 retail, 2 vanilla), its window %s, dungeon finder %s, listing allowed %s",
    tostring(style), GroupFinderVanillaStyle_LoadUI and "vanilla style" or "none known",
    tostring(Plain(Call(I and I.IsLFDEnabled))), tostring(Plain(Call(L and L.IsPlayerAuthenticatedForLFG)))))
  local s, now, said = lfg.QueueState(), GetTime(), {}
  for name, bit in pairs(lfg.Q) do if Has(s.flags, bit) then said[#said + 1] = name end end
  table.sort(said)
  ns.Print(string.format("now: %s%s%s", #said > 0 and table.concat(said, ", ") or "nothing",
    s.what ~= "" and (" for " .. s.what) or "", s.since and string.format(", %d s waiting", now - s.since) or ""))
  local e = queue.event
  ns.Print(e and string.format("last: %s from %s%s, %d s ago", EVENT_WORDS[e.kind], SOURCE_WORDS[e.source],
    e.name ~= "" and (" (" .. e.name .. ")") or "", now - e.at) or "last: nothing since the addon loaded")
end
