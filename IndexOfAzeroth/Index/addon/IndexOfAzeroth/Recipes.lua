-- The Index of Azeroth. Copyright 2026 Index Case <indexofazeroth@pm.me>. PolyForm Strict 1.0.0, see LICENSE.md.
local ADDON, ns = ...

local PlainNumber = ns.PlainNumber
local UI = ns.UI
local C = UI.C

local OUTLINE = { clear = C.green, weak = C.gold, debatable = C.debatable }
local recipes = { hooked = false }

function recipes.Marks()
  local sh = IndexOfAzerothShared
  local r = type(sh) == "table" and type(sh.rewards) == "table" and sh.rewards or nil
  if not (r and type(r.recipes) == "table" and ns.IsMe(r.char)) then return nil end
  return r.recipes
end

function recipes.Mark(frame, node)
  local data = type(node) == "table" and node.GetData and node:GetData() or nil
  local info = type(data) == "table" and type(data.recipeInfo) == "table" and data.recipeInfo or nil
  local id = info and PlainNumber(info.recipeID)
  local marks = id and recipes.Marks()
  local colour = marks and OUTLINE[marks[id]]
  local o = frame.ccOutline
  if not colour then
    if o then o:Hide() end
    return
  end
  if not o then
    o = CreateFrame("Frame", nil, frame, "BackdropTemplate")
    o:SetBackdrop({ edgeFile = UI.WHITE, edgeSize = 1 })
    o:SetAllPoints(frame)
    frame.ccOutline = o
  end
  o:SetBackdropBorderColor(colour[1], colour[2], colour[3], 1)
  o.kind = marks[id]
  o:Show()
end

function recipes.Hook()
  local frame, util = _G.ProfessionsFrame, _G.ScrollUtil
  local page = not recipes.hooked and frame and frame.CraftingPage
  local box = page and page.RecipeList and page.RecipeList.ScrollBox
  if not (box and util and util.AddInitializedFrameCallback) then return false end
  recipes.hooked = true
  util.AddInitializedFrameCallback(box, function(_, row, node) recipes.Mark(row, node) end, recipes)
  box:ForEachFrame(recipes.Mark)
  return true
end

ns.On({ "ADDON_LOADED", "PLAYER_LOGIN" }, function(event, name)
  if event == "PLAYER_LOGIN" or name == "Blizzard_Professions" then recipes.Hook() end
end)
ns.Recipes = recipes
