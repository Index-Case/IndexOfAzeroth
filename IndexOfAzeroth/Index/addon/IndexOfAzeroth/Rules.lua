-- The Index of Azeroth. Copyright 2026 Index Case <indexofazeroth@pm.me>. PolyForm Strict 1.0.0, see LICENSE.md.
local ADDON, ns = ...

local R = {
  tiers = {
    safety = 1,
    progress = 2,
    handin = 3,
    pickup = 3,
    errand = 3,
    area = 3,
    next = 4,
  },
  run = {
    typical = 500,
    least = 200,
    most = 1500,
    steps = 8,
    hop = 100,
    follow = 0.5,
  },
  reach = {
    giver = 0.2,
    way = 0.04,
    visit = 0.2,
    corridor = 0.06,
    area = 0.2,
    walked_away = 1,
    left = 0.06,
    back = 0.3,
    pass = 0.4,
    choose = 0.2,
  },
  cost = {
    far = 100000,
    ridden = 1200,
  },
  along = {
    reach = 50,
  },
  no_flap = {
    hold = 30,
    choose_for = 30,
    left_for = 30,
  },
  claims = {
    reckoned = 0.065,
    order = 0.024,
  },
  sure = {
    least = 0.8,
    off = 0.2,
    own = 1,
    pace = 0.5,
  },
  camps = {
    least_s = 300,
    least_n = 6,
    window = 900,
    busy = 0.5,
    quiet = 0.8,
    tapped = 2,
    empty = 0.25,
    move = 3,
    stays = 900,
    gap_most = 10,
  },
  director = {
    at_once = 1,
    cooldown = 90,
    closed_quiet = 900,
    linger = 60,
    break_for = 20,
    dry = 240,
    left_for = 45,
    page_for = 15,
    breaks = { "handed_in", "objective_done", "quest_done", "arrived", "town" },
  },
  words = {
    progress_giver = "{lost} can wait: its giver stays here, and you're {n} kills from finishing {won}.",
    progress_giver_one = "{lost} can wait: its giver stays here, and you're 1 kill from finishing {won}.",
    progress_giver_more = "{lost} can wait: its giver stays here, and you need {n} more for {won}.",
    progress_step = "{lost} can wait: you're {n} kills from finishing {won}.",
    progress_step_one = "{lost} can wait: you're 1 kill from finishing {won}.",
    progress_step_more = "{lost} can wait: you need {n} more for {won}.",
    handin = "{wonNpc} is close by, so you hand in {won} now and save a walk back for it later.",
    handins = "{n} quests are ready to hand in close by, so you hand them in now and save a walk back later.",
    pickup = "{wonNpc} is close by, so you pick up {won} now and save a walk back for it later.",
    handin_here = "{won} is ready to hand in close by, so you hand it in now and save a walk back later.",
    pickup_here = "The giver of {won} is close by, so you pick it up now and save a walk back later.",
    area = "You're in the area for {won}, so you do that quest now and save a walk back later.",
    errand = "{wonNpc} is close by, so you stop there now and save a walk back later.",
    chose = "You headed for {won}, so the guide goes there with you.",
    wait_giver = "{lost} can wait: you come back past {lostNpc} later anyway.",
    wait_area = "{lost} can wait: you come back this way later anyway.",
    walked = "You walked away from {lost}, so the guide goes on with {won}.",
    only = "Nothing else is left to do now, so the guide takes you to {wonNpc}.",
    back = "The guide goes back to this parked quest, since every other step is done or waiting.",
    later = "Later",
    put_off = "You put this chore off until you're next in town.",
    put_off_said = "You put off {chore} until you're next in town.",
    trace_start = "The plan loaded, and its first step to do leads.",
    trace_plan = "The step before is done, so the plan's next step leads.",
    trace_left = "The step that led can't lead any more, so the plan's step leads.",
    trace_progress = "You're working this step, so it leads.",
    trace_stop = "Every step of the plan is done, so nothing leads.",
    hearth = "Your Hearthstone takes you to {town}, which saves you about {n} minutes.",
    hearth_one = "Your Hearthstone takes you to {town}, which saves you about a minute.",
    train_way = "{spells} are trained on the way.",
    train_way_one = "{spells} is trained on the way.",
    put_off_npc = "You put this chore off until you're next near {npc}.",
    put_off_said_npc = "You put off {chore} until you're next near {npc}.",
    progress_giver_thing = "{lost} can wait: its giver stays here, and you're {n} {things} from finishing them.",
    progress_giver_thing_one = "{lost} can wait: its giver stays here, and you're 1 {thing} from finishing it.",
    progress_step_thing = "{lost} can wait: you're {n} {things} from finishing them.",
    progress_step_thing_one = "{lost} can wait: you're 1 {thing} from finishing it.",
    pass = "{place} first. {nearer}'s quests come later in the plan.",
    pass_s = "{place} first. {nearer}' quests come later in the plan.",
    busy = "Other players seem to be camping the spawns for {won}. {lost} is a better option.",
    busy_thing = "Other players seem to be camping the {things}. {lost} is a better option.",
    put_off_town = "You put this chore off until you're next in {town}.",
    put_off_said_town = "You put off {chore} until you're next in {town}.",
    put_off_place = "You put this chore off until you're next in {place}.",
    put_off_said_place = "You put off {chore} until you're next in {place}.",
    core_now = "{spells} are core: train now.",
    core_now_one = "{spells} is core: train now.",
    only_wait = "{lost} waits, because {why}. Until then, the guide takes you to {wonNpc}.",
  },
  quiet = {
    words = { "handin", "handins", "pickup", "handin_here", "pickup_here", "area", "wait_giver", "wait_area", "progress_giver", "progress_giver_one", "progress_giver_more", "progress_step", "progress_step_one", "progress_step_more", "progress_giver_thing", "progress_giver_thing_one", "progress_step_thing", "progress_step_thing_one", "errand" },
  },
  drift = {
    replan = 1,
    extra = 1,
    chore = 0.5,
    order = 1,
    off = 180,
    off_most = 2,
    nudge = 4,
    again = 4,
  },
  asks = {
    levelup = 3,
    classquest = 2.5,
    nextzone = 2,
    drift = 1,
  },
  next = {
    ahead = 3,
  },
  lines = {
    next_news = "You're level {level}, so {zone} is at your level now.",
    next_news_zeppelin = "You're level {level}, so {zone} is at your level now, if you fancy a zeppelin and a longer journey.",
    next_news_boat = "You're level {level}, so {zone} is at your level now, if you fancy a boat and a longer journey.",
    next_also = "So is {zone}.",
    next_far_zeppelin = "{zone} is open too, if you fancy a zeppelin and a longer journey.",
    next_far_boat = "{zone} is open too, if you fancy a boat and a longer journey.",
    next_leads = "A few quests here end up in {zone} anyway.",
    next_leads_one = "One quest here ends up in {zone} anyway.",
    next_ask = "Replan for only those, so you can be on your way?",
    next_ask_one = "Replan for only that one, so you can be on your way?",
    next_none = "Nothing here leads to {zone}, so replan in the Index whenever you want to move on.",
    left_work = "You were working on {quest} with {n} left to do. After that you {next}.",
    left_work_last = "You were working on {quest} with {n} left to do, the last step of the plan.",
    left_go = "You were on your way to {doing}. After that you {next}.",
    left_go_last = "You were on your way to {doing}, the last step of the plan.",
    replan_asked = "The Index is writing a new plan from where you stand. When the plan is ready, the Index asks you to /reload.",
    replan_zone_asked = "The Index is writing a plan for the quests that lead to {zone}. When the plan is ready, the Index asks you to /reload.",
    background_said = "You put {quest} in the background until your {skill} reaches {need}.",
    background_back = "{quest} is back in your steps, since your {skill} reached {need}.",
    putback_here_said = "{thing} is back where it was in your plan.",
    putback_visit_said = "{thing} is back in your plan for when you're next in town.",
    putback_visit_said_town = "{thing} is back in your plan for your next visit to {town}.",
    putback_visit_said_npc = "{thing} is back in your plan for your next visit to {npc}.",
    putback_visit_said_place = "{thing} is back in your plan for your next visit to {place}.",
    putback_place_said = "{thing} is back at its place in your plan.",
    class_news = "Your {class} class quest {chain} is open now. It teaches you {unlocks}.",
    class_news_plain = "Your {class} class quest {chain} is open now.",
    class_ask = "Start an epic that plans the whole class quest for you?",
    class_asked = "The Index is writing a class quest epic for {chain}. When the plan is ready, the Index asks you to /reload.",
  },
  phrases = {
    do_P = "pick up {name} from {npc}",
    do_P_alone = "pick up {name}",
    do_T = "hand in {name} to {npc}",
    do_T_alone = "hand in {name}",
    do_O = "work on {name}",
    do_D = "run {name}",
  },
  heads = {
    drawer_later = "Next time we're in town",
    drawer_later_town = "Next time we're in {town}",
    drawer_later_npc = "Next time we're near {npc}",
    drawer_later_place = "Next time we're in {place}",
    drawer_parked = "Parked quests, back when you unpark them",
    drawer_skipped = "Chores skipped for good",
    drawer_skipped_level = "Chores skipped until your next level",
    drawer_background = "Quests in the background, back when your skill is up",
    drawer_row_background = "{quest}: {skill} {have} of {need}",
    drawer_short = "Quests in your log, planned when your skill is up",
    class_quest = "Class quest",
    bag_slot = "1 Free bag slot",
    bag_slots = "{n} Free bag slots",
    camp_restock = "Buy wood for campfire kits",
    camp_left_none = "No wood or kits left for a camp",
    camp_left_one = "Wood for 1 more camp in your bags",
    camp_left = "Wood for {n} more camps in your bags",
    camp_wood = "{n} {wood}",
    camp_wood_tool = "{n} {wood} and a {tool}",
    camp_buy = "Buy {buy} at {npc}",
    camp_short = "Buying {buy} costs {cost}, and you have {have}",
    no_vendor = "No vendor of yours in reach sells {thing}",
  },
  buttons = {
    replan = "Replan",
    background = "Background",
    close_tip = "Closing this is always fine.",
    replan_tip = "Replan asks the Index for a new plan that fits the character's spot now.",
    zone_tip = "Replan asks the Index for a plan of only the quests that lead on to the next zone.",
    drawer_tip = "The steps put off, parked or skipped, and when each one comes back. The arrow on a row puts that step back in the plan.",
    background_tip = "Background sets this quest aside until the skill reaches its level. The quest comes back by itself.",
    background_row_tip = "A click on this step shows its Background key, which sets the quest aside until the skill reaches its level.",
    background_copy_tip = "Copies the line that sets this quest aside in game until the skill reaches its level. The quest comes back by itself.",
    putback_here_tip = "This puts {thing} back where it was in the plan, since the character is still close by.",
    putback_visit_tip = "This puts {thing} back in the plan for when the character is next in town.",
    putback_visit_tip_town = "This puts {thing} back in the plan for the next visit to {town}.",
    putback_visit_tip_npc = "This puts {thing} back in the plan for the next visit to {npc}.",
    putback_visit_tip_place = "This puts {thing} back in the plan for the next visit to {place}.",
    putback_place_tip = "This puts {thing} back at its place in the plan.",
    start = "Start",
    class_tip = "Start asks the Index for a class quest epic, a plan of every step of the class quest in order.",
    class_close_tip = "Closing this dismisses the to-do for good. Zone epics still put the class quest first.",
  },
  pools = {
    drift = { "Heroes who stick to the map end up in very short ballads. Replan when you want the next verse.", "The prophecy didn't mention this bit, which is the best thing a prophecy can say about anyone. Replan to update the prophecy.", "The plan was a suggestion, and you've made a counter-offer. Replan to settle on terms.", "Nobody ever bought a round for someone who followed the instructions. Replan when you're thirsty for more.", "The bards of Goldshire have abandoned rhyme to keep up with you. Replan to give the bards a chorus.", "Legends are mostly people who went the wrong way on purpose. Replan for the next chapter.", "Your deeds have run out of margin. Replan for a fresh page.", "Maps are drawn by people who stayed at home. Replan to draw your own.", "The bronze dragons have started taking notes on you. Replan to give the dragons a tidy copy.", "You took the road less travelled. Replan for the road back.", "Somewhere an innkeeper is telling your story and getting the route wrong. Replan to put the route right.", "The goblins of Booty Bay couldn't have priced this detour. Replan for an honest quote on the rest.", "Off the map is where the good stories live. Replan when you want to visit the plot.", "You wrote your own quest. Replan to fit your quest into the book.", "The quest givers can wait, and some have been waiting since the Second War. Replan when you're ready.", "History is written by people who wandered off. Replan to write the next part." },
    stay = { "Or stay and turn over every last rock. {here} has plenty of rocks.", "Or stay until {here} runs out of things to ask of you. That may take a while.", "Or stay and talk to every villager twice. Somebody in {here} has to.", "Or stay and check that barrel too. {here} has been saving the barrel for you.", "Or stay and finish your chores. Evil can wait, and in {here} evil usually does.", "Or stay and collect every single spoon. {here} notices a missing spoon.", "Or stay and see to the last exclamation marks. {here} still has a few.", "Or stay a while. The world isn't ending, whatever the posters in {here} say.", "Or stay and finish {here} properly. Bards are paid by the verse.", "Or stay and take your time. {here} isn't going anywhere, being a place." },
  },
  back = {
    order = { "town", "npc", "place" },
  },
  restock = {
    camp_low = 2,
    camp_stock = 5,
  },
  guide = {
    arrive = 8,
    board = 15,
    landed = 150,
    with_giver = 40,
    ways = { "way", "alt", "ez", "hw" },
    closer_by = 0.9,
  },
  lead = {
    epic = 1,
    nav = 1,
    loop = 1,
    prof = 2,
  },
  badges = {
    mobs = { "#00b5ff", "#ff3392", "#cc8800", "#59ffe9", "#ffb2a6", "#d5a6ff", "#738ae6", "#29c1cc", "#ccaf85", "#e695b5", "#a6c3ff", "#ff9c59", "#a6e7ff", "#ff00dd", "#e66b00", "#ff80e5" },
  },
  codes = { "progress_giver", "progress_giver_one", "progress_giver_more", "progress_step", "progress_step_one", "progress_step_more", "handin", "handins", "pickup", "handin_here", "pickup_here", "area", "errand", "chose", "wait_giver", "wait_area", "walked", "only", "back", "later", "put_off", "put_off_said", "trace_start", "trace_plan", "trace_left", "trace_progress", "trace_stop", "hearth", "hearth_one", "train_way", "train_way_one", "put_off_npc", "put_off_said_npc", "progress_giver_thing", "progress_giver_thing_one", "progress_step_thing", "progress_step_thing_one", "pass", "pass_s", "busy", "busy_thing", "put_off_town", "put_off_said_town", "put_off_place", "put_off_said_place", "core_now", "core_now_one", "only_wait" },
}

function R.Tier(kind) return R.tiers[kind] end
function R.Wins(a, b)
  local ta, tb = R.Tier(a.kind), R.Tier(b.kind)
  if ta == nil then return false end
  return tb == nil or ta < tb
end
local function Held(run) return math.max(R.run.least, math.min(R.run.most, run)) end
function R.Run(lengths)
  local list, any = {}, false
  for _, l in ipairs(lengths or {}) do
    if type(l) == "number" and l > 0 then
      any = true
      if l >= R.run.hop then list[#list + 1] = l end
    end
  end
  if not any then return R.run.typical end
  if #list == 0 then return R.run.least end
  table.sort(list)
  local n = #list
  local mid = n % 2 == 1 and list[(n + 1) / 2] or (list[n / 2] + list[n / 2 + 1]) / 2
  return Held(mid)
end
function R.Reach(name, run)
  local m = R.reach[name]
  if m == nil then return nil end
  local t = R.run.typical
  return m * t * (Held(run or t) / t) ^ R.run.follow
end
local function Dist(ax, ay, bx, by) return math.sqrt((ax - bx) ^ 2 + (ay - by) ^ 2) end
function R.Reached(t, x, y)
  if type(t.ar) == "table" and #t.ar > 0 then
    local best, mx, my = math.huge, t.x, t.y
    for _, p in ipairs(t.ar) do
      local d = Dist(p[1], p[2], x, y) - (p[3] or 0)
      if d < best then best, mx, my = d, p[1], p[2] end
    end
    return math.max(0, best), mx, my
  end
  return Dist(x, y, t.x, t.y), t.ox or t.x, t.oy or t.y
end
function R.Among(t, x, y)
  local best, bx, by, mid, mx, my
  local patches = type(t.ar) == "table" and #t.ar > 0
  if patches then
    best, mid = math.huge, math.huge
    for _, p in ipairs(t.ar) do
      local full, r = Dist(p[1], p[2], x, y), p[3] or 0
      local d = full - r
      mid = math.min(mid, full)
      if d < best then
        best, mx, my = d, p[1], p[2]
        if d <= 0 or full <= 0 then bx, by = x, y
        else bx, by = p[1] + (x - p[1]) * r / full, p[2] + (y - p[2]) * r / full end
      end
    end
  else
    best, bx, by, mx, my = Dist(t.x, t.y, x, y), t.x, t.y, t.x, t.y
  end
  local loop = t.loop
  if not patches and type(loop) == "table" and #loop > 1 then
    for i = 2, #loop do
      local ax, ay, qx, qy = loop[i - 1][1], loop[i - 1][2], loop[i][1], loop[i][2]
      local dx, dy = qx - ax, qy - ay
      local len2 = dx * dx + dy * dy
      local u = len2 > 0 and math.max(0, math.min(1, ((x - ax) * dx + (y - ay) * dy) / len2)) or 0
      qx, qy = ax + u * dx, ay + u * dy
      local d = Dist(qx, qy, x, y)
      if d < best then best, bx, by = d, qx, qy end
    end
  end
  return best, bx, by, mid or best, mx, my
end
function R.Here(t, x, y, run)
  if type(t.hr) == "table" and #t.hr > 0 then
    local all = {}
    for _, p in ipairs(type(t.ar) == "table" and t.ar or {}) do all[#all + 1] = p end
    for _, p in ipairs(t.hr) do all[#all + 1] = p end
    t = { ar = all, loop = t.loop, x = t.x, y = t.y }
  end
  local best, bx, by, mid, mx, my = R.Among(t, x, y)
  if best > R.Reach("area", run) then return nil end
  return best, bx, by, mid, mx, my
end
function R.Arrived(t, x, y, run)
  local d = R.Among(t, x, y)
  if type(t.ar) == "table" and #t.ar > 0 then return d <= 0 end
  return d <= R.Reach("giver", run)
end
function R.Along(line, px, py, first)
  local best, at, start = math.huge, 0, 0
  for k = 2, #line do
    local ax, ay, bx, by = line[k - 1][1], line[k - 1][2], line[k][1], line[k][2]
    local size = Dist(ax, ay, bx, by)
    local u = size > 0 and math.max(0, math.min(1, ((px - ax) * (bx - ax) + (py - ay) * (by - ay)) / (size * size))) or 0
    local d = Dist(ax + u * (bx - ax), ay + u * (by - ay), px, py)
    if d < best then best, at = d, start + u * size end
    start = start + size
  end
  local to, done = math.min(first, start), 0
  local hx, hy = line[#line][1] - line[1][1], line[#line][2] - line[1][2]
  for k = 2, #line do
    local ax, ay, bx, by = line[k - 1][1], line[k - 1][2], line[k][1], line[k][2]
    local size = Dist(ax, ay, bx, by)
    if done + size >= to or k == #line then
      local u = size > 0 and (to - done) / size or 0
      hx, hy = ax + u * (bx - ax) - line[1][1], ay + u * (by - ay) - line[1][2]
      break
    end
    done = done + size
  end
  return best, at, start, (px - line[1][1]) * hx + (py - line[1][2]) * hy
end
function R.Passes(a, b, p, run, bends)
  local giver, way, visit = R.Reach("giver", run), R.Reach("way", run), R.Reach("visit", run)
  local dap, dab, dpb = Dist(a.x, a.y, p.x, p.y), Dist(a.x, a.y, b.x, b.y), Dist(p.x, p.y, b.x, b.y)
  if dab > visit and dap <= giver and dpb > giver then return true end
  if dpb <= R.run.hop then return false end
  if bends then
    local line = { { a.x, a.y } }
    for _, q in ipairs(bends) do line[#line + 1] = { q[1], q[2] } end
    line[#line + 1] = { b.x, b.y }
    local off, at, length, ahead = R.Along(line, p.x, p.y, giver)
    if dap <= giver and length > giver and dap + dpb - length <= giver and (dap <= way or ahead >= 0) then return true end
    return at > 0 and off <= giver and length - at > giver and off + dpb - (length - at) <= giver
  end
  local dot = (p.x - a.x) * (b.x - a.x) + (p.y - a.y) * (b.y - a.y)
  if dap <= giver and dab > giver and dap + dpb - dab <= giver and (dap <= way or dot >= 0) then return true end
  if dab <= 0 or dab >= R.cost.ridden then return false end
  local t = math.min(1, dot / (dab * dab))
  if t <= 0 then return false end
  local dqp, dqb = Dist(a.x + t * (b.x - a.x), a.y + t * (b.y - a.y), p.x, p.y), (1 - t) * dab
  return dqp <= giver and dqb > giver and dqp + dpb - dqb <= giver
end
function R.LegWay(t, x, y)
  local best, way, from = math.huge, nil, nil
  for _, w in ipairs(t.ways or {}) do
    for k = 2, #w do
      local ax, ay, bx, by = w[k - 1][1], w[k - 1][2], w[k][1], w[k][2]
      local size = Dist(ax, ay, bx, by)
      local u = size > 0 and math.max(0, math.min(1, ((x - ax) * (bx - ax) + (y - ay) * (by - ay)) / (size * size))) or 0
      local d = Dist(ax + u * (bx - ax), ay + u * (by - ay), x, y)
      if d < best then best, way, from = d, w, k end
    end
  end
  if not way or best > R.run.hop then return nil end
  local out = {}
  for k = from, #way do out[#out + 1] = way[k] end
  return out
end
function R.Fit(first, stops, anchor, here, run)
  local route = { first }
  if anchor and anchor.key == first.key then anchor = nil end
  for _, t in ipairs(stops) do
    if t.key ~= first.key and not (anchor and t.key == anchor.key) then route[#route + 1] = t end
  end
  if anchor then route[#route + 1] = anchor end
  local cost, outs = 0, { { x = first.ox or first.x, y = first.oy or first.y } }
  for k = 2, #route do
    local d, x, y = R.Reached(route[k], outs[k - 1].x, outs[k - 1].y)
    cost, outs[k] = cost + d, { x = x, y = y }
  end
  local walk = {}
  if here then walk[1] = { x = here.x, y = here.y } end
  local lead = #walk
  for k = 1, #outs do walk[lead + k] = outs[k] end
  local ways = {}
  for j = 2, #walk do ways[j] = R.LegWay(route[j - lead], walk[j - 1].x, walk[j - 1].y) or false end
  for k = 2, #route do
    local t = route[k]
    if t.open then
      for j = 2, k - 1 + lead do
        if R.Passes(walk[j - 1], walk[j], t, run, ways[j] or nil) then
          cost = cost + 2 * Dist(walk[j].x, walk[j].y, t.x, t.y)
          break
        end
      end
    end
  end
  return { cost = cost, route = route }
end
function R.Apart(t, first)
  local _, mx, my = R.Reached(first, t.x, t.y)
  return Dist(t.x, t.y, mx, my) > R.run.hop
end
function R.Sooner(t, first, stops, anchor, here, run)
  local at = nil
  for k, s in ipairs(stops) do if s.key == t.key and not at then at = k end end
  local with, route = { [t.key] = true }, {}
  for k = 1, (at or 1) - 1 do
    local s = stops[k]
    if s.open and Dist(s.x, s.y, t.x, t.y) <= R.run.hop then route[#route + 1], with[s.key] = s, true end
  end
  for k = (at or #stops) + 1, #stops do
    if Dist(stops[k].x, stops[k].y, t.x, t.y) > R.run.hop then break end
    route[#route + 1], with[stops[k].key] = stops[k], true
  end
  route[#route + 1] = first
  for _, s in ipairs(stops) do if not with[s.key] then route[#route + 1] = s end end
  local now = t.walk + R.Fit(t, route, anchor, here, run).cost
  local later = first.walk + R.Fit(first, stops, anchor, here, run).cost
  return { now = now, later = later, yes = R.Apart(t, first) and now < later - 1e-6 }
end
function R.MayShow(open, sinceLast, sinceClosed)
  local d = R.director
  return open < d.at_once and (sinceLast == nil or sinceLast >= d.cooldown)
    and (sinceClosed == nil or sinceClosed >= d.closed_quiet)
end
function R.Play(off, own, pace)
  local s = R.sure
  local doublings = (type(pace) == "number" and pace > 0) and math.abs(math.log(pace) / math.log(2)) or 0
  return 1 + s.off * math.max(0, off or 0) + s.own * math.abs(own or 0) + s.pace * doublings
end
function R.Sure(kind, steps, factor)
  local base = R.claims[kind]
  if base == nil or type(steps) ~= "number" or steps < 0 then return 0 end
  return (1 - math.min(1, base * math.max(1, factor or 1))) ^ steps
end
function R.Said(kind, steps, factor) return R.Sure(kind, steps, factor) >= R.sure.least end
local Filled = ns.Fill
function R.Say(key, fill) return Filled(R.words[key], fill) end
function R.Quiet(key)
  for _, k in ipairs(R.quiet.words) do if k == key then return true end end
  return false
end
local TEXT = { words = true, lines = true, phrases = true, heads = true, buttons = true }
function R.Line(part, key, fill)
  local t = TEXT[part] and R[part]
  if not t then return nil end
  return Filled(t[key], fill)
end
function R.Town(towns, inst, x, y)
  if type(towns) ~= "table" or type(towns.list) ~= "table" or inst == nil or type(x) ~= "number" or type(y) ~= "number" then
    return nil
  end
  local near, best, out = tonumber(towns.near) or 0, math.huge, nil
  for _, t in ipairs(towns.list) do
    if type(t) == "table" and t[2] == inst and type(t[3]) == "number" and type(t[4]) == "number" then
      local d = math.sqrt((t[3] - x) ^ 2 + (t[4] - y) ^ 2)
      if d <= near and d < best then best, out = d, t[1] end
    end
  end
  return type(out) == "string" and out ~= "" and out or nil
end
function R.Back(part, key, where, fill)
  local f, t = {}, TEXT[part] and R[part] or {}
  for k, v in pairs(fill or {}) do f[k] = v end
  for _, name in ipairs(R.back.order) do
    local v = where and where[name]
    if v ~= nil and v ~= "" and t[key .. "_" .. name] then
      f[name] = v
      return R.Line(part, key .. "_" .. name, f)
    end
  end
  return R.Line(part, key, f)
end
function R.Pick(name, n, fill)
  local pool = R.pools[name]
  if type(pool) ~= "table" or #pool == 0 or type(n) ~= "number" or n ~= math.floor(n) then return nil end
  return Filled(pool[(n - 1) % #pool + 1], fill)
end
function R.Moment(fighting, working, sinceBreak, sinceReward)
  local d = R.director
  if fighting then return false end
  if not working then return true end
  return (sinceBreak ~= nil and sinceBreak <= d.break_for) or (sinceReward ~= nil and sinceReward >= d.dry)
end
function R.OffWeight(yards, reach)
  if type(reach) ~= "number" or reach <= 0 or type(yards) ~= "number" or yards <= reach then return 0 end
  return math.min(R.drift.off_most, yards / reach)
end
function R.Drift(p)
  local w = R.drift
  p = p or {}
  return w.replan * (p.replan or 0) + w.extra * (p.extra or 0) + w.chore * (p.chore or 0) + w.order * (p.order or 0)
    + (p.off or 0) / w.off
end
function R.Nudge(points, shownAt)
  local w = R.drift
  if type(points) ~= "number" or points < w.nudge then return false end
  return shownAt == nil or points >= shownAt + w.again
end
function R.Slots(objs, free)
  if type(free) ~= "number" then return 0 end
  local want = 0
  for _, o in ipairs(objs or {}) do
    if o.item and not o.finished and (o.need or 0) > 0 and (o.have or 0) == 0 then want = want + 1 end
  end
  return free < want and want or 0
end
function R.OnCard(shownKind, shownIds, kind, quest)
  if shownKind == "P" or kind ~= "O" or quest == nil then return false end
  for _, id in ipairs(shownIds or {}) do if id == quest then return true end end
  return false
end
function R.SpawnedNear(spots, x, y)
  local r = R.along.reach
  for _, p in ipairs(spots or {}) do
    if Dist(p[1], p[2], x, y) <= r then return true end
  end
  return false
end
function R.Ways(offQuick, offEasy, leftQuick, leftEasy, lengths)
  local run = R.Run(lengths)
  local on, away = R.Reach("way", run), R.Reach("walked_away", run)
  if offQuick <= on and offEasy <= on and math.abs(leftEasy - leftQuick) <= on then
    return offEasy < offQuick and "easy" or "quick"
  end
  if offEasy <= on and offQuick > away then return "easy" end
  if offQuick <= on and offEasy > away then return "quick" end
  return "both"
end
function R.Colours(rows, kept)
  local n, top, owner = #rows, {}, {}
  local function root(i) while top[i] ~= i do i = top[i] end return i end
  for i = 1, n do top[i] = i end
  for i, keys in ipairs(rows) do
    for _, k in ipairs(keys) do
      local j = owner[k]
      if j == nil then
        owner[k] = i
      else
        local a, b = root(i), root(j)
        if a ~= b then top[math.max(a, b)] = math.min(a, b) end
      end
    end
  end
  local most, groups, place, taken = #R.badges.mobs, {}, {}, {}
  for i = 1, n do if root(i) == i then groups[#groups + 1] = i end end
  for _, g in ipairs(groups) do
    for i = g, n do
      for _, k in ipairs(root(i) == g and rows[i] or {}) do
        local p = kept and kept[k]
        if not place[g] and type(p) == "number" and p >= 1 and p <= most and not taken[p] then place[g], taken[p] = p, true end
      end
    end
  end
  for x, g in ipairs(groups) do
    if not place[g] then
      local p = nil
      for q = 1, most do
        if not taken[q] then
          p = q
          break
        end
      end
      p = p or (x - 1) % most + 1
      place[g], taken[p] = p, true
    end
  end
  local out = { rows = {}, kept = {} }
  for i, keys in ipairs(rows) do
    local p = place[root(i)]
    out.rows[i] = p
    for _, k in ipairs(keys) do out.kept[k] = p end
  end
  return out
end
function R.Beacon(spots, running, held)
  local top = nil
  for _, kind in ipairs(running or {}) do
    local t = R.lead[kind]
    if t and (not top or t < top) then top = t end
  end
  local best, keep = nil, nil
  for _, s in ipairs(spots or {}) do
    if top and s.yards ~= nil and R.lead[s.kind] == top then
      if not best or s.yards < best.yards then best = s end
      if held ~= nil and s.id == held then keep = s end
    end
  end
  if keep and best.yards > keep.yards * R.guide.closer_by then best = keep end
  return best and best.id or nil
end
function R.Code(key)
  for i, k in ipairs(R.codes) do if k == key then return i end end
  return 0
end

ns.Rules = R
