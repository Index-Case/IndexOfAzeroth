# The Index of Azeroth. Copyright 2026 Index Case <indexofazeroth@pm.me>. PolyForm Strict 1.0.0, see LICENSE.md.
import math

import words


class Start:

    def __init__(self, value, came_from):
        self.value, self.came_from = value, came_from


TIERS = {
    "safety": 1,
    "progress": 2,
    "handin": 3,
    "pickup": 3,
    "errand": 3,
    "area": 3,
    "next": 4,
    "chore": None,
}

RUN = {
    "typical": Start(500.0, "the walked-away midpoint (CC-813): a reach's yards hold at it"),
    "least": Start(200.0, "a new number, a stretch's runs counted no shorter, so a packed hub keeps a usable close by"),
    "most": Start(1500.0, "a new number, a stretch's runs counted no longer, so a flight or a far jump stays out of it"),
    "steps": Start(8, "a new number, the plan's steps from the lead whose runs make the stretch"),
    "hop": Start(100.0, "a new number, steps nearer each other than this are one place (two NPCs at a camp, two areas side "
                        "by side) and the walk between them no run, so a hub's short hops don't shrink its reaches: the "
                        "giver reach at a typical stretch (CC-807's 100 yards)"),
    "follow": Start(0.5, "a new number, how closely a reach follows the stretch's run (1 in step with it, 0 fixed yards): "
                         "half-way, so Seeking Refuge's 638 yd run gives Bareth Dawnstone's pickup 113 yd, short of the "
                         "120 yd the replay case holds him off at, and Deathknell's 200 yd stretch gives 63 yd, short of "
                         "The Damned's 95 yd"),
}

REACH = {
    "giver": Start(100.0 / 500, "CC-807: a pickup or hand-in within 100 yards (Tracks.lua "
                                "handin.PICK_NEAR 100, CC-759), ready hand-ins up from handin.NEAR 40: an offshoot's "
                                "giver or chore's NPC this near you (CC-954)"),
    "way": Start(20.0 / 500, "Tracks.lua handin.WAY 20: a giver this near your way to the plan's step is passed "
                             "(the planner's walked past, planunits.walked_past)"),
    "visit": Start(100.0 / 500, "RUN hop at a typical stretch (questplan.NOW_NEAR 40 before step 7): a later step this near "
                                "where you stand is done in this visit when it's open and it walks little more, and a walk "
                                "further than this leaves the place you stand at (passes, the planner's visits)"),
    "corridor": Start(30.0 / 500, "a new number, CC-866: Along the way lists an objective whose place lies this near your "
                                  "way from where you stand to the step that leads, between the two ends. 30 yd at a "
                                  "typical stretch, 19 yd in a packed hub and 52 yd at the longest, so a step a few yards "
                                  "off the way counts and a camp 100 yards to the side never does"),
    "area": Start(100.0 / 500, "CC-802 comment 7: inside a quest's area or within 100 yd of its edge, the same reach as "
                               "the close-by pickups (CC-759). The one measure of near enough to do now (here), for the "
                               "card and the plan alike: it took the place of Card.lua's ALONG_NEAR and questplan's "
                               "DOING_NEAR, 150 yd from a step's spot or spawns"),
    "walked_away": Start(500.0 / 500, "CC-813 and CC-803: 500 yd out at a typical stretch. Out past it from the way to "
                                      "the step that leads, you've left the plan's way (CC-954), and out past it from an "
                                      "offshoot you've walked away from it"),
    "left": Start(30.0 / 500, "a new number: a step in progress you step out of stays in progress "
                              "until leaving is clearly meant, this far past its area's edge for NO_FLAP left_for seconds "
                              "(or past the walked-away reach at once). An area's patches already reach 40 yd past their "
                              "furthest spawn, so 30 yd more is past any pull or chase, and Brakk's spot in Razor Hill, 25 "
                              "to 35 yd past the Razormane Scouts' edge, is out (19 yd there, at a 208 yd stretch)"),
    "back": Start(150.0 / 500, "CC-803's Later: a chore offered again within 150 yd of its NPC, and back within 150 yd"),
    "pass": Start(200.0 / 500, "a new number, CC-860's far before near: a nearer place counts as passed when one of its steps "
                               "stands within this of your way to the step that leads. Twice the giver reach, so Sen'jin "
                               "Village's Lar Prowltusk, some 160 yd off the fork on the Valley of Trials' way to Razor "
                               "Hill, is passed and a village two hills off your way isn't"),
    "choose": Start(100.0 / 500, "the design (CC-954): your choice of another step of the plan is a walk that closes on it "
                                 "by at least this much in all, about the giver reach, while not closing on the step that "
                                 "leads"),
}

COST = {
    "far": Start(1e5, "Arbiter.lua FAR: yards to the plan's next step on another continent, a far walk off, so what's here "
                      "is now or never on this visit"),
    "ridden": Start(1200.0, "shared.WAY_MOST, in yards (no reach): a walk this long or longer is ridden (a flight, a boat, "
                            "the Hearthstone) where no way on foot says otherwise, so the givers along its straight line "
                            "aren't passed on the way"),
}

NO_FLAP = {
    "hold": Start(30.0, "a new number, the replays' and the simulator's window for a flip back: the lead back on a step it "
                        "left within this many seconds fails a case"),
    "choose_for": Start(30.0, "the design (CC-954): your choice of another step of the plan is a walk toward it kept up "
                              "this many seconds in all, half a minute, never a stride or two. The Razor Hill walk heads "
                              "west past the Razormane camp for 19 s before it turns north to Furl Scornbrow's "
                              "watchtower, which stays the lead"),
    "left_for": Start(30.0, "a new number, seconds in all out past REACH left since you were last inside its area (the time "
                            "nearer its edge, coming back or pulling there, not counted) before a step in progress you "
                            "stepped out of is in progress no more: a short detour, a chase or a pull past the edge "
                            "never ends it. The simulator's drifting player "
                            "wanders up to 19 s out and back: at 20 s one of Kast's three Durotar seeds lost a step in "
                            "progress that way (seed 3 at 2,298 s), at 30 s none did, the same as the hold"),
}

CAMPS = {
    "least_s": Start(300.0, "a new number, active seconds at a camp before its rate says anything: at a reckoned 112 "
                            "kills an hour (a mob of your level at your pace, 32 s a kill) five minutes expect 9 kills, "
                            "and 4 or fewer of them come about 1 time in 20 when the camp is as quiet as reckoned"),
    "least_n": Start(6.0, "a new number, kills the reckoning expects in your active time at the camp before its rate "
                          "says anything, so a camp whose spawns give back slowly is watched longer than five minutes"),
    "window": Start(900.0, "a new number, the last active seconds at a camp its rate and what you saw there are measured "
                           "over, so a camp that empties or fills is seen within minutes"),
    "busy": Start(0.5, "well below the reckoned rate: a camp may be busy under half its reckoned kills an hour, "
                       "and only with other players seen at it (tapped, empty)"),
    "quiet": Start(0.8, "a new number, a busy camp is quiet again at this share of its reckoned rate, a gap above busy "
                        "so a camp on the edge doesn't flip. It's quiet at once when no other player is seen at it in "
                        "the window any more"),
    "tapped": Start(2.0, "a new number, the camp's mobs seen tagged by someone else or fighting another player in the "
                         "window that show other players at it: two, so one passer-by's pull isn't a busy camp"),
    "empty": Start(0.25, "a new number, a camp's spawns found empty: the camp's mobs seen alive and free to tag in the "
                         "window are this share of its spawns or fewer, with your nameplates on (a mob only you target "
                         "says nothing of the rest)"),
    "move": Start(3.0, "a new number, yards you move between two looks (2 s apart) that count as moving among the "
                       "spawns: a step or two, so standing still, eating and drinking and being away don't count"),
    "stays": Start(900.0, "a new number, seconds a busy camp stays busy after you were last at it: about three respawns "
                          "of a 5 minute camp, time for the other players to move on. Then it's measured afresh"),
    "gap_most": Start(10.0, "a new number, seconds between two looks that count as time at the camp at most: the guide "
                            "looks every 2 s, so a longer gap is a loading screen or the game away. Your choice's clock "
                            "counts no more between two looks either"),
}

CLAIMS = {
    "reckoned": Start(0.065, "CC-833: a claim on the plan's reckoning of your XP and time (a grind point, "
                             "the time to your next level, the level a plan takes you to) is said three steps ahead and not "
                             "four, so a grind point a step or two ahead still shows and Kast's 92 steps on doesn't"),
    "order": Start(0.024, "a new number, a claim on the plan's own order (you come back past a giver later) is said nine "
                          "steps ahead and not ten: the arbiter's stretch, run.steps and the step after it, which it "
                          "weighs that walk over"),
}

SURE = {
    "least": Start(0.8, "a claim is said only when it holds this sure"),
    "off": Start(0.2, "a new number, each quest in your log the plan hasn't got that you picked up since it loaded adds this "
                      "to the play factor (the epic director's quests outside the plan), so five double each step's chance"),
    "own": Start(1.0, "a new number, each level of XP you've had off the plan's reckoning since it loaded adds this to the "
                      "play factor (grinding of your own, kills on the way, a quest outside the plan handed in)"),
    "pace": Start(0.5, "a new number, each doubling of your pace off the plan's reckoning adds this to the play factor "
                       "(Tracks.lua GuidePace, the kill rate in it)"),
}

DIRECTOR = {
    "at_once": Start(1, "the design: never two slide-outs at once"),
    "cooldown": Start(90.0, "a new number, seconds after a slide-out has gone before the next may show: a level up's "
                            "report on the page and its next-zone news in game come a minute and a half apart"),
    "closed_quiet": Start(900.0, "a new number, seconds a slide-out you closed stays away, its kind's next one too"),
    "linger": Start(60.0, "a new number, seconds a slide-out stays out with no answer before it slides back in by itself, "
                          "taken as closed: an answer is never needed (CC-798: closing it is always fine)"),
    "break_for": Start(20.0, "a new number, seconds after a natural break (a hand-in, a step done, arriving in town or "
                             "landing) an interruption may still come with a step in progress again: the time you stand "
                             "at a giver after a hand-in"),
    "dry": Start(240.0, "a new number, seconds since your last reward (XP, an objective counted, a hand-in) that make a "
                        "dry spell: a step in progress then holds nothing back, since four minutes with nothing to show "
                        "is the tedium the director is paced on (the epic director's design, Paced on rhythm)"),
    "left_for": Start(45.0, "a new number, seconds the card says where you left off after a load, unless the lead moves "
                            "on first"),
    "page_for": Start(15.0, "a new number, seconds a slide-out only the page draws (the level report, CC-694) holds the "
                            "budget: the game can't hear the page shut it, so its turn is held a moment and given back"),
    "breaks": ["handed_in", "objective_done", "quest_done", "arrived", "town"],
}

DRIFT = {
    "replan": Start(1.0, "a new number, each plan the Index wrote again for a change in your game (a quest picked up or "
                         "dropped, a refusal) that the game loaded: your own Replan starts the count again"),
    "extra": Start(1.0, "a new number, each quest in your log the plan hasn't got that you picked up since it loaded "
                        "(CC-795: quests the plan didn't have)"),
    "chore": Start(0.5, "a new number, each vendor, trainer or repairer you used while no step led you to them (CC-795: "
                        "chores off the plan), half a quest's worth, since a stop at a vendor you pass is ordinary"),
    "order": Start(1.0, "a new number, each of the plan's quests you handed in while its turn-in wasn't the step that led "
                        "(CC-795: hand-ins out of order)"),
    "off": Start(180.0, "a new number, the seconds off the line that count as one: three minutes about with the lead's "
                        "spot and your way to it both further than the walked-away reach (CC-795: time and distance off "
                        "the line)"),
    "off_most": Start(2.0, "a new number, how far off the line counts at most, in walked-away reaches: twice as far off "
                           "counts twice as fast, further no faster"),
    "nudge": Start(4.0, "CC-795's test: two quests the plan didn't have, one hand-in out of order and a walk off the line "
                        "bring the nudge, and following the plan never does"),
    "again": Start(4.0, "a new number, how much more drift brings the nudge again after it showed: as much as brought it "
                        "first (CC-795: closed, it stays away until the drift grows a good deal further)"),
}

ASKS = {
    "levelup": Start(3, "a new number, the level report on the page first: it's the level's own news (CC-694)"),
    "classquest": Start(2.5, "a new number, a class quest chain your level opened after the level report and before the "
                             "next zones, since a class quest weighs more than a zone quest (CC-848)"),
    "nextzone": Start(2, "a new number, the next zones your level reached next (CC-798)"),
    "drift": Start(1, "a new number, the drift nudge last: it keeps until you've a moment (CC-795)"),
}

NEXT = {
    "ahead": Start(3, "a new number, the levels ahead of yours the Index writes your next zones for, so a ding three "
                      "levels on with no /reload since still has its news"),
}

RESTOCK = {
    "camp_low": Start(2, "camping.KITS: a kit for this camp and one for the next, the camping epic's own count (settled "
                         "with the coordinator, 17 Oct 2026)"),
    "camp_stock": Start(5, "a camp at most once an hour (the features' shared cooldown in professions.json), so five hours "
                           "of camping between restocks (settled with the coordinator, 17 Oct 2026)"),
}

GUIDE = {
    "arrive": Start(8.0, "CC-929: the page's Navigation Guide, its You're there and the epic's blue arrow (Tracks.lua) "
                         "said 8 yards, the gold arrow alone 5 (Arrow.lua), and a stop 12 on the page and 15 in game: "
                         "the number most of them already used"),
    "board": Start(15.0, "CC-984: the arrows said 15 yards (Arrow.lua), the page 40 (guide.js): the arrow's, the one a "
                         "player follows to the ride"),
    "landed": Start(150.0, "CC-984: the arrows (Arrow.lua) and the page (guide.js) both said 150 yards"),
    "with_giver": Start(40.0, "CC-687: the card (Tracks.lua), the plan (plansteps.py) and planlead.py each said 40 yards. "
                              "The quest data puts "
                              "one giver's spots within 8 yards of each other and two givers of one name on a "
                              "continent 200 yards and more apart (1 Oct 2026)"),
    "ways": ["way", "alt", "ez", "hw"],
}

BADGES = {
    "mobs": ["#00b5ff", "#ff3392", "#cc8800", "#59ffe9", "#ffb2a6", "#d5a6ff", "#738ae6", "#29c1cc", "#ccaf85",
             "#e695b5", "#a6c3ff", "#ff9c59", "#a6e7ff", "#ff00dd", "#e66b00", "#ff80e5"],
}

LINES = {
    "next_news": "You're level {level}, so {zone} is at your level now.",
    "next_news_zeppelin": "You're level {level}, so {zone} is at your level now, if you fancy a zeppelin and a longer journey.",
    "next_news_boat": "You're level {level}, so {zone} is at your level now, if you fancy a boat and a longer journey.",
    "next_also": "So is {zone}.",
    "next_far_zeppelin": "{zone} is open too, if you fancy a zeppelin and a longer journey.",
    "next_far_boat": "{zone} is open too, if you fancy a boat and a longer journey.",
    "next_leads": "A few quests here end up in {zone} anyway.",
    "next_leads_one": "One quest here ends up in {zone} anyway.",
    "next_ask": "Replan for only those, so you can be on your way?",
    "next_ask_one": "Replan for only that one, so you can be on your way?",
    "next_none": "Nothing here leads to {zone}, so replan in the Index whenever you want to move on.",
    "left_work": "You were working on {quest} with {n} left to do. After that you {next}.",
    "left_work_last": "You were working on {quest} with {n} left to do, the last step of the plan.",
    "left_go": "You were on your way to {doing}. After that you {next}.",
    "left_go_last": "You were on your way to {doing}, the last step of the plan.",
    "replan_asked": "The Index is writing a new plan from where you stand. When the plan is ready, the Index asks you to "
                    "/reload.",
    "replan_zone_asked": "The Index is writing a plan for the quests that lead to {zone}. When the plan is ready, the Index "
                         "asks you to /reload.",
    "background_said": "You put {quest} in the background until your {skill} reaches {need}.",
    "background_back": "{quest} is back in your steps, since your {skill} reached {need}.",
    "putback_here_said": "{thing} is back where it was in your plan.",
    "putback_visit_said": "{thing} is back in your plan for when you're next in town.",
    "putback_visit_said_town": "{thing} is back in your plan for your next visit to {town}.",
    "putback_visit_said_npc": "{thing} is back in your plan for your next visit to {npc}.",
    "putback_visit_said_place": "{thing} is back in your plan for your next visit to {place}.",
    "putback_place_said": "{thing} is back at its place in your plan.",
    "class_news": "Your {class} class quest {chain} is open now. It teaches you {unlocks}.",
    "class_news_plain": "Your {class} class quest {chain} is open now.",
    "class_ask": "Start an epic that plans the whole class quest for you?",
    "class_asked": "The Index is writing a class quest epic for {chain}. When the plan is ready, the Index asks you to "
                   "/reload.",
}

PHRASES = {
    "do_P": "pick up {name} from {npc}",
    "do_P_alone": "pick up {name}",
    "do_T": "hand in {name} to {npc}",
    "do_T_alone": "hand in {name}",
    "do_O": "work on {name}",
    "do_D": "run {name}",
}

HEADS = {
    "drawer_later": "Next time we're in town",
    "drawer_later_town": "Next time we're in {town}",
    "drawer_later_npc": "Next time we're near {npc}",
    "drawer_later_place": "Next time we're in {place}",
    "drawer_parked": "Parked quests, back when you unpark them",
    "drawer_skipped": "Chores skipped for good",
    "drawer_skipped_level": "Chores skipped until your next level",
    "drawer_background": "Quests in the background, back when your skill is up",
    "drawer_row_background": "{quest}: {skill} {have} of {need}",
    "drawer_short": "Quests in your log, planned when your skill is up",
    "class_quest": "Class quest",
    "bag_slot": "1 Free bag slot",
    "bag_slots": "{n} Free bag slots",
    "camp_restock": "Buy wood for campfire kits",
    "camp_left_none": "No wood or kits left for a camp",
    "camp_left_one": "Wood for 1 more camp in your bags",
    "camp_left": "Wood for {n} more camps in your bags",
    "camp_wood": "{n} {wood}",
    "camp_wood_tool": "{n} {wood} and a {tool}",
    "camp_buy": "Buy {buy} at {npc}",
    "camp_short": "Buying {buy} costs {cost}, and you have {have}",
    "no_vendor": "No vendor of yours in reach sells {thing}",
}

BUTTONS = {
    "replan": "Replan",
    "background": "Background",
    "close_tip": "Closing this is always fine.",
    "replan_tip": "Replan asks the Index for a new plan that fits the character's spot now.",
    "zone_tip": "Replan asks the Index for a plan of only the quests that lead on to the next zone.",
    "drawer_tip": "The steps put off, parked or skipped, and when each one comes back. The arrow on a row puts that step "
                  "back in the plan.",
    "background_tip": "Background sets this quest aside until the skill reaches its level. The quest comes back by itself.",
    "background_row_tip": "A click on this step shows its Background key, which sets the quest aside until the skill "
                          "reaches its level.",
    "background_copy_tip": "Copies the line that sets this quest aside in game until the skill reaches its level. The "
                           "quest comes back by itself.",
    "putback_here_tip": "This puts {thing} back where it was in the plan, since the character is still close by.",
    "putback_visit_tip": "This puts {thing} back in the plan for when the character is next in town.",
    "putback_visit_tip_town": "This puts {thing} back in the plan for the next visit to {town}.",
    "putback_visit_tip_npc": "This puts {thing} back in the plan for the next visit to {npc}.",
    "putback_visit_tip_place": "This puts {thing} back in the plan for the next visit to {place}.",
    "putback_place_tip": "This puts {thing} back at its place in the plan.",
    "start": "Start",
    "class_tip": "Start asks the Index for a class quest epic, a plan of every step of the class quest in order.",
    "class_close_tip": "Closing this dismisses the to-do for good. Zone epics still put the class quest first.",
}

POOLS = {
    "drift": [
        "Heroes who stick to the map end up in very short ballads. Replan when you want the next verse.",
        "The prophecy didn't mention this bit, which is the best thing a prophecy can say about anyone. Replan to update "
        "the prophecy.",
        "The plan was a suggestion, and you've made a counter-offer. Replan to settle on terms.",
        "Nobody ever bought a round for someone who followed the instructions. Replan when you're thirsty for more.",
        "The bards of Goldshire have abandoned rhyme to keep up with you. Replan to give the bards a chorus.",
        "Legends are mostly people who went the wrong way on purpose. Replan for the next chapter.",
        "Your deeds have run out of margin. Replan for a fresh page.",
        "Maps are drawn by people who stayed at home. Replan to draw your own.",
        "The bronze dragons have started taking notes on you. Replan to give the dragons a tidy copy.",
        "You took the road less travelled. Replan for the road back.",
        "Somewhere an innkeeper is telling your story and getting the route wrong. Replan to put the route right.",
        "The goblins of Booty Bay couldn't have priced this detour. Replan for an honest quote on the rest.",
        "Off the map is where the good stories live. Replan when you want to visit the plot.",
        "You wrote your own quest. Replan to fit your quest into the book.",
        "The quest givers can wait, and some have been waiting since the Second War. Replan when you're ready.",
        "History is written by people who wandered off. Replan to write the next part.",
    ],
    "stay": [
        "Or stay and turn over every last rock. {here} has plenty of rocks.",
        "Or stay until {here} runs out of things to ask of you. That may take a while.",
        "Or stay and talk to every villager twice. Somebody in {here} has to.",
        "Or stay and check that barrel too. {here} has been saving the barrel for you.",
        "Or stay and finish your chores. Evil can wait, and in {here} evil usually does.",
        "Or stay and collect every single spoon. {here} notices a missing spoon.",
        "Or stay and see to the last exclamation marks. {here} still has a few.",
        "Or stay a while. The world isn't ending, whatever the posters in {here} say.",
        "Or stay and finish {here} properly. Bards are paid by the verse.",
        "Or stay and take your time. {here} isn't going anywhere, being a place.",
    ],
}

WORDS = {
    "progress_giver": "{lost} can wait: its giver stays here, and you're {n} kills from finishing {won}.",
    "progress_giver_one": "{lost} can wait: its giver stays here, and you're 1 kill from finishing {won}.",
    "progress_giver_more": "{lost} can wait: its giver stays here, and you need {n} more for {won}.",
    "progress_step": "{lost} can wait: you're {n} kills from finishing {won}.",
    "progress_step_one": "{lost} can wait: you're 1 kill from finishing {won}.",
    "progress_step_more": "{lost} can wait: you need {n} more for {won}.",
    "handin": "{wonNpc} is close by, so you hand in {won} now and save a walk back for it later.",
    "handins": "{n} quests are ready to hand in close by, so you hand them in now and save a walk back later.",
    "pickup": "{wonNpc} is close by, so you pick up {won} now and save a walk back for it later.",
    "handin_here": "{won} is ready to hand in close by, so you hand it in now and save a walk back later.",
    "pickup_here": "The giver of {won} is close by, so you pick it up now and save a walk back later.",
    "area": "You're in the area for {won}, so you do that quest now and save a walk back later.",
    "errand": "{wonNpc} is close by, so you stop there now and save a walk back later.",
    "chose": "You headed for {won}, so the guide goes there with you.",
    "wait_giver": "{lost} can wait: you come back past {lostNpc} later anyway.",
    "wait_area": "{lost} can wait: you come back this way later anyway.",
    "walked": "You walked away from {lost}, so the guide goes on with {won}.",
    "only": "Nothing else is left to do now, so the guide takes you to {wonNpc}.",
    "back": "The guide goes back to this parked quest, since every other step is done or waiting.",
    "later": "Later",
    "put_off": "You put this chore off until you're next in town.",
    "put_off_said": "You put off {chore} until you're next in town.",
    "trace_start": "The plan loaded, and its first step to do leads.",
    "trace_plan": "The step before is done, so the plan's next step leads.",
    "trace_left": "The step that led can't lead any more, so the plan's step leads.",
    "trace_progress": "You're working this step, so it leads.",
    "trace_stop": "Every step of the plan is done, so nothing leads.",
    "hearth": "Your Hearthstone takes you to {town}, which saves you about {n} minutes.",
    "hearth_one": "Your Hearthstone takes you to {town}, which saves you about a minute.",
    "train_way": "{spells} are trained on the way.",
    "train_way_one": "{spells} is trained on the way.",
    "put_off_npc": "You put this chore off until you're next near {npc}.",
    "put_off_said_npc": "You put off {chore} until you're next near {npc}.",
    "progress_giver_thing": "{lost} can wait: its giver stays here, and you're {n} {things} from finishing them.",
    "progress_giver_thing_one": "{lost} can wait: its giver stays here, and you're 1 {thing} from finishing it.",
    "progress_step_thing": "{lost} can wait: you're {n} {things} from finishing them.",
    "progress_step_thing_one": "{lost} can wait: you're 1 {thing} from finishing it.",
    "pass": "{place} first. {nearer}'s quests come later in the plan.",
    "pass_s": "{place} first. {nearer}' quests come later in the plan.",
    "busy": "Other players seem to be camping the spawns for {won}. {lost} is a better option.",
    "busy_thing": "Other players seem to be camping the {things}. {lost} is a better option.",
    "put_off_town": "You put this chore off until you're next in {town}.",
    "put_off_said_town": "You put off {chore} until you're next in {town}.",
    "put_off_place": "You put this chore off until you're next in {place}.",
    "put_off_said_place": "You put off {chore} until you're next in {place}.",
    "core_now": "{spells} are core: train now.",
    "core_now_one": "{spells} is core: train now.",
}

BACK = {
    "order": ["town", "npc", "place"],
}

QUIET = {
    "words": ["handin", "handins", "pickup", "handin_here", "pickup_here", "area", "wait_giver", "wait_area",
              "progress_giver", "progress_giver_one", "progress_giver_more", "progress_step", "progress_step_one",
              "progress_step_more", "progress_giver_thing", "progress_giver_thing_one", "progress_step_thing",
              "progress_step_thing_one", "errand"],
}

PLAN = {
    "slack": Start(20.0 / 500, "questplan.NOW_SLACK 20: the yards a step done now rather than in a later visit may add"),
    "far": Start(250.0 / 500, "planscore FAR_LEAST: a trip away from a place goes at least this far to be a trip away and back"),
    "back_share": Start(0.5, "planscore BACK_SHARE: back where you were is within this share of the farthest the trip went"),
    "back_most": Start(600.0 / 500, "planscore BACK_MOST: and within this many yards"),
    "lone": Start(2, "planscore LONE_MOST: a trip away holding this many talk steps or fewer, and nothing else, is a lone jaunt"),
    "reorder": Start(200.0 / 500, "a new number, a repair from where you stand after a death (planrepair.from_here) reorders "
                                  "the plan only when that walks at least this much less: twice the giver reach, so a "
                                  "graveyard beside the town with the next hand-ins comes first and a few yards never "
                                  "reshuffle the plan (CC-806: it keeps your order unless changing it saves a lot)"),
}

RULES = {"tiers": TIERS, "run": RUN, "reach": REACH, "cost": COST, "no_flap": NO_FLAP, "claims": CLAIMS,
         "sure": SURE, "camps": CAMPS, "director": DIRECTOR, "words": WORDS, "quiet": QUIET, "drift": DRIFT,
         "asks": ASKS, "next": NEXT, "lines": LINES, "phrases": PHRASES, "heads": HEADS, "buttons": BUTTONS,
         "pools": POOLS, "back": BACK, "restock": RESTOCK, "guide": GUIDE, "badges": BADGES}
TEXT_PARTS = ("words", "lines", "phrases", "heads", "buttons")


def plain(value=RULES):
    if isinstance(value, Start):
        return value.value
    if isinstance(value, dict):
        return {k: plain(v) for k, v in value.items()}
    if isinstance(value, list):
        return [plain(v) for v in value]
    return value


def starts(value=RULES, at=()):
    out = []
    if isinstance(value, Start):
        out.append((".".join(at), value.came_from))
    elif isinstance(value, dict):
        for k, v in value.items():
            out.extend(starts(v, at + (k,)))
    return out


def held(run):
    return max(RUN["least"].value, min(RUN["most"].value, run))


def run(lengths):
    some = [x for x in lengths or () if isinstance(x, (int, float)) and not isinstance(x, bool) and x > 0]
    if not some:
        return RUN["typical"].value
    runs = sorted(x for x in some if x >= RUN["hop"].value)
    if not runs:
        return RUN["least"].value
    n = len(runs)
    return held(runs[n // 2] if n % 2 else (runs[n // 2 - 1] + runs[n // 2]) / 2)


def reach(name, at=None):
    m = REACH.get(name) or PLAN.get(name)
    if m is None:
        return None
    t = RUN["typical"].value
    return m.value * t * (held(at if at is not None else t) / t) ** RUN["follow"].value


def tier(kind):
    return TIERS.get(kind)


def wins(a, b):
    ta, tb = tier(a.get("kind")), tier(b.get("kind"))
    if ta is None:
        return False
    return tb is None or ta < tb


def _or(v, default):
    return default if v is None else v


def _dist(ax, ay, bx, by):
    return math.sqrt((ax - bx) ** 2 + (ay - by) ** 2)


def reached(t, x, y):
    ar = t.get("ar")
    if isinstance(ar, list) and ar:
        best, mx, my = math.inf, t.get("x"), t.get("y")
        for p in ar:
            d = _dist(p[0], p[1], x, y) - _or(p[2] if len(p) > 2 else None, 0)
            if d < best:
                best, mx, my = d, p[0], p[1]
        return max(0, best), mx, my
    return _dist(x, y, t["x"], t["y"]), _or(t.get("ox"), t["x"]), _or(t.get("oy"), t["y"])


def among(t, x, y):
    ar = t.get("ar")
    if isinstance(ar, list) and ar:
        def radius(p):
            return _or(p[2] if len(p) > 2 else None, 0)
        p = min(ar, key=lambda p: _dist(p[0], p[1], x, y) - radius(p))
        full, r = _dist(p[0], p[1], x, y), radius(p)
        d = full - r
        bx, by = (x, y) if d <= 0 or full <= 0 else (p[0] + (x - p[0]) * r / full, p[1] + (y - p[1]) * r / full)
        return d, bx, by, min(_dist(q[0], q[1], x, y) for q in ar), p[0], p[1]
    best, bx, by = _dist(t["x"], t["y"], x, y), t["x"], t["y"]
    loop = t.get("loop")
    for a, c in zip(loop, loop[1:]) if isinstance(loop, list) else ():
        dx, dy = c[0] - a[0], c[1] - a[1]
        len2 = dx * dx + dy * dy
        u = max(0, min(1, ((x - a[0]) * dx + (y - a[1]) * dy) / len2)) if len2 > 0 else 0
        qx, qy = a[0] + u * dx, a[1] + u * dy
        d = _dist(qx, qy, x, y)
        if d < best:
            best, bx, by = d, qx, qy
    return best, bx, by, best, t["x"], t["y"]


def here(t, x, y, run=None):
    more = t.get("hr")
    if isinstance(more, list) and more:
        t = {**t, "ar": list(t.get("ar") or []) + more}
    got = among(t, x, y)
    return got if got[0] <= reach("area", run) else None


def arrived(t, x, y, run=None):
    d = among(t, x, y)[0]
    ar = t.get("ar")
    return d <= 0 if isinstance(ar, list) and ar else d <= reach("giver", run)


def along(line, px, py, first):
    best, at, start = math.inf, 0.0, 0.0
    for k in range(1, len(line)):
        ax, ay, bx, by = line[k - 1][0], line[k - 1][1], line[k][0], line[k][1]
        size = _dist(ax, ay, bx, by)
        u = max(0.0, min(1.0, ((px - ax) * (bx - ax) + (py - ay) * (by - ay)) / (size * size))) if size > 0 else 0.0
        d = _dist(ax + u * (bx - ax), ay + u * (by - ay), px, py)
        if d < best:
            best, at = d, start + u * size
        start = start + size
    to, done, hx, hy = min(first, start), 0.0, line[-1][0] - line[0][0], line[-1][1] - line[0][1]
    for k in range(1, len(line)):
        ax, ay, bx, by = line[k - 1][0], line[k - 1][1], line[k][0], line[k][1]
        size = _dist(ax, ay, bx, by)
        if done + size >= to or k == len(line) - 1:
            u = (to - done) / size if size > 0 else 0.0
            hx, hy = ax + u * (bx - ax) - line[0][0], ay + u * (by - ay) - line[0][1]
            break
        done = done + size
    return best, at, start, (px - line[0][0]) * hx + (py - line[0][1]) * hy


def passes(a, b, p, run=None, way=None):
    giver, near, visit = reach("giver", run), reach("way", run), reach("visit", run)
    ax, ay, bx, by, px, py = a["x"], a["y"], b["x"], b["y"], p["x"], p["y"]
    dap, dab, dpb = _dist(ax, ay, px, py), _dist(ax, ay, bx, by), _dist(px, py, bx, by)
    if dab > visit and dap <= giver and dpb > giver:
        return True
    if dpb <= RUN["hop"].value:
        return False
    if way is not None:
        off, at, length, ahead = along([[ax, ay]] + [q[:2] for q in way] + [[bx, by]], px, py, giver)
        if dap <= giver and length > giver and dap + dpb - length <= giver and (dap <= near or ahead >= 0):
            return True
        return at > 0 and off <= giver and length - at > giver and off + dpb - (length - at) <= giver
    dot = (px - ax) * (bx - ax) + (py - ay) * (by - ay)
    if dap <= giver and dab > giver and dap + dpb - dab <= giver and (dap <= near or dot >= 0):
        return True
    if dab <= 0 or dab >= COST["ridden"].value:
        return False
    t = min(1.0, dot / (dab * dab))
    if t <= 0:
        return False
    dqp, dqb = _dist(ax + t * (bx - ax), ay + t * (by - ay), px, py), (1 - t) * dab
    return dqp <= giver and dqb > giver and dqp + dpb - dqb <= giver


def leg_way(t, x, y):
    best, out = math.inf, None
    for w in t.get("ways") or ():
        for k in range(1, len(w)):
            ax, ay, bx, by = w[k - 1][0], w[k - 1][1], w[k][0], w[k][1]
            size = _dist(ax, ay, bx, by)
            u = max(0.0, min(1.0, ((x - ax) * (bx - ax) + (y - ay) * (by - ay)) / (size * size))) if size > 0 else 0.0
            d = _dist(ax + u * (bx - ax), ay + u * (by - ay), x, y)
            if d < best:
                best, out = d, w[k:]
    return out if best <= RUN["hop"].value else None


def fit(first, stops, anchor=None, here=None, run=None):
    if anchor is not None and anchor.get("key") == first.get("key"):
        anchor = None
    route = [first] + [t for t in stops if t.get("key") != first.get("key")
                       and (anchor is None or t.get("key") != anchor.get("key"))]
    if anchor is not None:
        route.append(anchor)
    cost, outs = 0, [{"x": _or(first.get("ox"), first["x"]), "y": _or(first.get("oy"), first["y"])}]
    for k in range(1, len(route)):
        d, x, y = reached(route[k], outs[k - 1]["x"], outs[k - 1]["y"])
        cost = cost + d
        outs.append({"x": x, "y": y})
    walk = ([{"x": here["x"], "y": here["y"]}] if here is not None else []) + outs
    lead = len(walk) - len(outs)
    ways = [None] + [leg_way(route[j - lead], walk[j - 1]["x"], walk[j - 1]["y"]) for j in range(1, len(walk))]
    for k in range(1, len(route)):
        t = route[k]
        if t.get("open"):
            for j in range(1, k + lead):
                if passes(walk[j - 1], walk[j], t, run, ways[j]):
                    cost = cost + 2 * _dist(walk[j]["x"], walk[j]["y"], t["x"], t["y"])
                    break
    return {"cost": cost, "route": route}


def apart(t, first):
    _, mx, my = reached(first, t["x"], t["y"])
    return _dist(t["x"], t["y"], mx, my) > RUN["hop"].value


def sooner(t, first, stops, anchor=None, here=None, run=None):
    k = next((j for j, s in enumerate(stops) if s.get("key") == t.get("key")), None)
    visit = [s for s in stops[:k] if s.get("open") and _dist(s["x"], s["y"], t["x"], t["y"]) <= RUN["hop"].value] \
        if k is not None else []
    for s in stops[k + 1:] if k is not None else ():
        if _dist(s["x"], s["y"], t["x"], t["y"]) > RUN["hop"].value:
            break
        visit.append(s)
    keys = {t.get("key")} | {s.get("key") for s in visit}
    now = t["walk"] + fit(t, visit + [first] + [s for s in stops if s.get("key") not in keys], anchor, here, run)["cost"]
    later = first["walk"] + fit(first, stops, anchor, here, run)["cost"]
    return {"now": now, "later": later, "yes": apart(t, first) and now < later - 1e-6}


def codes():
    return list(WORDS)


def quiet(key):
    return key in QUIET["words"]


def play(off=None, own=None, pace=None):
    import math
    s = SURE
    return (1 + s["off"].value * max(0, off or 0) + s["own"].value * abs(own or 0)
            + s["pace"].value * (abs(math.log2(pace)) if pace and pace > 0 else 0))


def sure(kind, steps, factor=None):
    base = CLAIMS.get(kind)
    if base is None or steps is None or steps < 0:
        return 0
    return (1 - min(1, base.value * max(1, factor or 1))) ** steps


def said(kind, steps, factor=None):
    return sure(kind, steps, factor) >= SURE["least"].value


def say(key, fill=None):
    return _filled(WORDS.get(key), fill)


def _filled(text, fill):
    return words.fill(text, fill)


def line(part, key, fill=None):
    words = RULES.get(part) if part in TEXT_PARTS else None
    return _filled(words.get(key), fill) if words else None


def town(towns, inst, x, y):
    number = (int, float)
    if not isinstance(towns, dict) or not isinstance(towns.get("list"), list) or inst is None \
            or not isinstance(x, number) or not isinstance(y, number):
        return None
    near, best, out = towns.get("near") or 0, math.inf, None
    for t in towns["list"]:
        if isinstance(t, list) and len(t) >= 4 and t[1] == inst and all(isinstance(v, (int, float)) for v in t[2:4]):
            d = math.hypot(t[2] - x, t[3] - y)
            if d <= near and d < best:
                best, out = d, t[0]
    return out if isinstance(out, str) and out else None


def back(part, key, where=None, fill=None):
    fill, words = dict(fill or {}), (RULES.get(part) if part in TEXT_PARTS else None) or {}
    for name in BACK["order"]:
        v = (where or {}).get(name)
        if v not in (None, "") and f"{key}_{name}" in words:
            return line(part, f"{key}_{name}", {**fill, name: v})
    return line(part, key, fill)


def pick(name, n, fill=None):
    pool = POOLS.get(name)
    if not pool or not isinstance(n, (int, float)) or isinstance(n, bool) or not float(n).is_integer():
        return None
    return _filled(pool[(int(n) - 1) % len(pool)], fill)


def moment(fighting, working, since_break=None, since_reward=None):
    d = DIRECTOR
    if fighting:
        return False
    if not working:
        return True
    return (since_break is not None and since_break <= d["break_for"].value) or \
        (since_reward is not None and since_reward >= d["dry"].value)


def off_weight(yards, reach):
    if not reach or reach <= 0 or yards is None or yards <= reach:
        return 0
    return min(DRIFT["off_most"].value, yards / reach)


def drift(parts=None):
    p, w = parts or {}, DRIFT
    return (w["replan"].value * (p.get("replan") or 0) + w["extra"].value * (p.get("extra") or 0)
            + w["chore"].value * (p.get("chore") or 0) + w["order"].value * (p.get("order") or 0)
            + (p.get("off") or 0) / w["off"].value)


def nudge(points, shown_at=None):
    w = DRIFT
    if points is None or points < w["nudge"].value:
        return False
    return shown_at is None or points >= shown_at + w["again"].value


def slots(objectives, free):
    if free is None:
        return 0
    want = sum(1 for o in objectives or () if o.get("item") and not o.get("finished")
               and (o.get("need") or 0) > 0 and (o.get("have") or 0) == 0)
    return want if free < want else 0


def on_card(shown_kind, shown_ids, kind, quest):
    return shown_kind != "P" and kind == "O" and quest is not None and quest in (shown_ids or ())
