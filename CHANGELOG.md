<!-- The Index of Azeroth. Copyright 2026 Index Case <indexofazeroth@pm.me>. PolyForm Strict 1.0.0, see LICENSE.md. -->
# Changelog

## 0.1.16-alpha

### Planning
- New: The Index works out the ways for your next plans while you play. A plan for a zone of your level, or after a level-up, can be ready in seconds.
- Faster planning.

### Fixes
- Fixed: The Index could keep running after its window was closed while it finished an update.

### Data
- Quest data brought up to date.

## 0.1.15-alpha

### Dungeons
- New: The nine dungeons WoW Forever added show bosses and loot in the journal.
- New: A dungeon with several levels has a map for each level.
- Dungeons with no drawn map now have a map.
- Quest givers inside a dungeon are placed inside the dungeon.

### Planning
- New: A quest epic plans a run of another dungeon when a quest is done there. The card marks that run with a warning.
- Quests a plan leaves out are listed under Later with the reason.
- Faster planning.
- Fixed: Ways from a cave, a tunnel or an upper floor could start on the ground above or below.

### Gathering
- A gathering loop shows the fights with mobs near the nodes.

### Map
- New: Hide in the Overlays and Places menus clears the map and keeps the ticks.

## 0.1.14-alpha

### Auction House
- Fixed: Some full scans were not counted, so recommendations used an older scan.
- Fixed: Sales between a night scan and a day scan were not counted, so sales figures read low.
- Fixed: Sell recommended a vendor for many items that sell on the auction house.
- Fixed: A scan could keep reading until the auction house closed.
- Fixed: Search on the shopping list finds an item with a random suffix.
- Clearer wording in the Market and the recommendations.

### Planning
- Faster planning.

### Data
- More vendor goods are confirmed for items WoW Forever added.

## 0.1.13-alpha

### Auction House
- New: The Auction House window recommends what to buy and sell from your auction house scans.
- New: Market, Item, Crafting, Your auctions, Inventory and Auction history panels.
- New: Financials shows gold earned and spent by cause, for one character or the account.
- New: Prediction accuracy shows how past price ranges and sale chances held.
- Each random suffix of an item is priced and recommended separately.
- Buy recommendations can go on a shopping list that copies to the game.
- Purchases, posts and cancels change the recommendations at once.
- The Show switch filters the panels to this character or all alts.
- Sell and Inventory show where each item is: Bags, Bank or Mail.
- An incomplete scan says what share of the auctions arrived.

### The guide
- A step waits for a level only where the game requires that level.
- The route line and the arrow work in cities under rock and a floor above or below.
- Crafting epics plan from your bags, and every sale chore can be skipped.

### Planning
- Faster planning.
- Routes can use ways that a quest hand-in opens and flight paths learned earlier in the plan.
- Routes count travel speed and avoid long walks through the other faction's zones.

### Data
- Loot tables and quests for the dungeons WoW Forever added.
- Quests, spawns and vendor prices follow the November hotfixes.
- Next upgrades ranks gear by stat weights for your spec and level.

### Map
- The Undercity shows over the lake above it.
- Smoother map dragging when zoomed far out.

## 0.1.12-alpha

### Damage meter
- New: A damage meter in game opens with /ioa meter, with Fight, History, Compare and Spells tabs.
- New: The live DPS graph can stay on screen and show DPS as each fight goes, beside the last fight.
- The live DPS graph has background opacity, lock and show only in combat options.
- Fights can be picked by single or multi enemy, open world or dungeons, mob level and date.
- A fight against several enemies lists each enemy and the damage you did to each.
- Compare can split fights by a fighting condition, such as a stance, a seal, a weapon enchant or a pet.
- The live DPS graph and the Fight tab work in a group and over chain pulls.
- New: The Combat key on the page opens PvP and the damage meter.
- The page's damage meter shows fights over time by session or by time, with zoom and Normalize.
- The Spells view shows each spell's casts, share of damage and DPS with and without that spell.

### The guide
- New: At a step that waits for a level, Quest instead can lead the quests in your quest log until then.
- The route line and the arrow start where you stand, also indoors or a floor away.
- A training stop no longer leads you out of a city that has your trainer.
- After a flight or hearth outside the plan, the guide leads on from where you arrive.

### Planning
- New: Starting an epic or a Re-plan asks whether to Carry on with the kept plan or Start fresh.
- A zone epic keeps you in the zone and takes steps in another zone together on one trip.
- Each trip to another zone says why on the first step.
- A chain of quests in another zone stays whole on one trip.
- A quest picked up early says that the quest's work comes later.
- Training is taken on a trip that passes the trainer, as one stop.
- Removed: Prefer close in the Quests drawer.

### Quests
- New: The Finished key in the Quests drawer lists every quest you have turned in, searchable by name.
- Quest marks have separate switches for available quests and hand-ins.

### Map
- Zone level ranges are corrected and closer to the mobs found in each zone.
- Thinner quest mark outlines and a faint graph behind each per hour figure in the live panel.

### Player
- Stat weights follow the talents you have, rank by rank.
- New: Stat weights have a levelling set and a level 60 set, with new priorities for paladin, warrior and rogue.
- Next upgrades lists clear upgrades first, then weak, then debatable.
- Next upgrades rows show the drop chance.

### Fixes
- Plans no longer take both quests of a pair where the game lets you pick only one.
- A plan no longer places a quest before you reach the level the quest needs.
- Two objectives of one quest no longer show the same words on the step card.
- Menus on the top bar no longer run past the edge of a narrow window.

## 0.1.11-alpha

### Dungeons
- Every dungeon that opened with the game's launch is open in the Index. Their quests are back in your plans and their loot counts again for Next upgrades and Where to run.
- Raids stay closed until they open, and a closed place with a known day says when it opens.
- Re-plan a running epic to get those quests back.

### Player
- Stat priorities for every spec are up to date, so Next upgrades ranks gear by what your spec looks for.
- Haste and expertise on gear are read and weighed.
- The talent planner has a build for every spec.

### The guide
- Routes use the ways your character has opened, such as a transporter or a teleport from an item.

## 0.1.10-alpha

### The guide
- Safest keeps clear of mobs that would attack you and takes a detour only when it is at most a quarter longer.
- A way that mobs can reach glows red on every planned step.
- A Safest step whose way still passes close to mobs says so on the card.
- A step that waits for a level or a skill leads until you can do it, and a later step leads only when it is close by.
- A far step with no route says so on the card and the page.
- Hearthstone lines show only while that trip is still ahead of you.
- Labels on the compass stack instead of overlapping.

### Map
- The weather where you stand shows on the map over your zone.
- Thousands more herbs, veins, chests and fishing schools on the gathering layers.

### Quests
- More than 200 more quests are planned, and quests with no zone of their own are offered in their giver's zone.
- Items the game no longer offers are gone from vendors, drops, rewards and recipes.

### Player
- Next upgrades ranks rares by how often they are up and weighs each piece by how long you would wear it.

### Fixes
- A far hand-in flies when a flight is quicker than the walk.
- Declutter lists every gray quest.
- An errand placed on your way waits while its step waits.
- A quest item the quest hands you is no longer planned as loot.

## 0.1.9-alpha

### Fixes
- An update no longer downloads the navigation again when it hasn't changed, so updates are much smaller.

## 0.1.8-alpha

### The guide
- Every epic now leads with what to do next as one plain sentence, such as "Pick up Rig Wars from Nogg" or "Speak to Jandia".
- A step that would surprise you says why in one short line: a quest that opens another, a hearth set for the trip back, a quest done inside the dungeon.
- A hearth step draws its trip: where you set it, where you go and where you come back.
- At a dungeon's door the guide says which of its quests are in your log and which are not.
- The next two steps show where they take you.
- Many clarity and readability improvements to the guide in game and on the page.

### PvP
- The new PvP window (B) lists every fight you've had with another player, with your wins and losses, filters and stats. Click a fight to see it in order: every spell from both sides, the damage, the crowd control and the killing blow.
- Hovering a zone on the map shows whether it's safe, contested or open to attack for your faction.

### Quests
- Zone epics let you pick which quest colours to plan, from Trivial to Impossible, all ticked at first.
- A quest taken only to unlock one you picked says which quest it leads to.
- The add-on's Options have a Declutter key that abandons the gray and green quests you tick, zone by zone.
- Quests in the newer zones show the experience they give.
- A timed quest is planned as one run: picked up, done and handed in with nothing in between.
- Quests that start from an item you find are planned.

### Professions
- Profession epics can be closed and reopened as they were, with two running at once and any number kept closed.
- Craft it asks how to plan the item: Cheapest, Fastest or Best of both.
- A crafting epic counts the materials in your bank and adds a step to take them out.
- A crafting epic sells the items you crafted only for skill at a vendor on your way and counts that money.
- Selling an item a later craft needs shows a warning, and buying it back clears the warning.
- Every step of a profession epic shows a progress bar with how many are left.
- Auction house steps go to your own faction's auction house.

### Dungeons
- Each dungeon shows its level range and the level it opens from.
- More dungeon quests show what starts them.

### Player
- Spell and talent tooltips work out the numbers that depend on your stats.

### Map
- Contour lines on the detailed map, with a Contours key.
- At night, light spills out of doorways and windows.
- The way into the Drowned City.

### Fixes
- A turn-in next to where you finish is handed in before a trip to town.
- Zone epics leave out quests far above the zone and quests with nowhere to hand them in.
- A group quest inside an enemy town waits until you reach its level, and a step that waits says why.
- Profession epics no longer send you to a trainer who won't teach you.
- After the Index restarts, your epic's step and way show on the page at once.
- A quest item both factions collect is planned at your own faction's spot.
- Druids fly out of Moonglade instead of walking.
- A profession lesson is planned at the trainer quickest to reach.
- A dungeon's quest epic opens at the level its first quest is offered.
- A PvP fight you died in no longer reads as one you got away from.
- A profession epic beside your quest epic no longer repeats its chores.
- A warning set to Never show stays silent.

## 0.1.7-alpha

### Professions
- Profession epics can run side by side with your quest epic, up to two, one for each profession. Each has its own window in game and its own panel on the page, and your quest epic keeps the beacon.

### Map
- Quest givers and hand-ins can show on the map with the game's quest marks, and a click on a mark guides you there. Turn them on in the Quests drawer.
- The character column can sit on either side of the page.

### Dungeons
- The roll card says whether to roll Need, Greed or make your own call.

### Guides
- Arrow to objective is the default aim.
- Many clarity and readability improvements.

### Fixes
- The dungeon part of an epic can be parked.
- A zone with its canopy turned off no longer shades the ground with trees.
- Mark the best reward no longer picks armour your class can't wear.
- The corpse beacon shows when you die, with no /reload.

## 0.1.6-alpha

### Fixes
- The Index tells you when an update is downloaded and waiting for you to close World of Warcraft.
- A newer update is found while an older one waits, so you always get the newest.

## 0.1.5-alpha

### Fixes
- Caves and buildings show on the map the first time you walk into them.

## 0.1.4-alpha

### Fixes
- Plans and guides follow the ground again everywhere, where they could draw straight lines.

## 0.1.3-alpha

### Fixes
- The Index tells you to close World of Warcraft when its addon is waiting to go into the game.
- The game no longer shows an error loading the Index's addon on its first start.

## 0.1.2-alpha

### Options
- The Options window has new sections for Map, Combat, Guides, Character and Levelling, and the add-on has new options for its card, guidance and nameplates.

### Crafting
- Buy and gather steps count what's in your bags right now.
- A vendor's limited stock is planned as a maybe, with vendors who always stock the item first.
- Gathering spots are picked by the trip there, so a common ore no longer sends you to another continent.
- Recipe and class training prices match what the trainers charge since launch.
- Mark the best reward can pick by sell price.

### Places and NPCs
- The Places menu lists your own class's trainers, with a + to pick another class's, and weapon masters by the weapon skill they teach.
- Clicking an NPC or mob in the NPCs menu moves the map to it.

### Planning
- Grind loops never target rares or mobs that spawn only once.
- My Next Upgrades marks an item from a rare or a single-spawn mob as a one-off kill.
- A quest you can finish where you stand is finished before the plan moves on.

### Fixes
- A new install no longer stops on a download the Index refuses.
- Blood spatters show again in fights.
- Quests with launch changes to their levels and hand-ins are planned correctly.

## 0.1.1-alpha

### Crafting
- The Player menu lists the recipes you could learn that would be an upgrade for you, and guides you to the trainer or vendor who teaches them.
- Level it now levels a profession to the skill you pick, gathering or buying the materials your way, and a craft that needs more skill levels it first.

### Fixes
- A plan waiting for a /reload shows each far step's route instead of a straight line.

## 0.1.0-alpha

**Early days.** This is version 0.1 alpha. The Index works, but it still has rough edges, and updates come often while they're smoothed out.

### Map
- A map of Azeroth with a day and night cycle and a moving sea, with your character on it live as you play.
- Overlays for mob densities and the best places to grind.
- The world's places: inns, flight masters, vendors and trainers.

### Planning
- Quest epics: a plan for the quests of a zone, a dungeon or quests you choose, redone whenever your quest log changes.
- An arrow and a step card in the game for each step of the plan.
- Your road to 60: the spells, talents and training each level unlocks.

### Characters
- The Alts board, with each character's gear and bags as they were at your last logout.
- A log of your play, saved on your PC, to replay on the map.

### Live panel
- Your supplies, gold, bags, gear, weapon skills, levelling pace, travel and time, beside the map.

### Updates
- Small updates install by themselves, and the Index shows what changed.
