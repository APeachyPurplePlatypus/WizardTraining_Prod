# Changelog

Every change, enhancement or addition is listed with its rationale, so later contributors know why the framework is the way it is. Say what was verified in the game and what was not.

## Unreleased

### Added

- **Runs remember what earlier runs learned.**
  - **What:** `runtime/knowledge.json` keeps the zones where health does not come back while resting and where each teleport volume leads. A run starts with it, logs a one-line summary, and adds what it learned when it ends. Obstacles and "no effect" teleport verdicts are not kept: the players and enemies behind most obstacles move on, and a walk that fell short of a volume once looked like "no effect". Delete the file to start fresh.
  - **Why:** runs are bounded (an hour, a battle count), so a night of play is many runs. Each one started blank. After the rematch with The Harvest Lord, a new run rested a minute in his tower for nothing: the run before it had already found that health does not come back there. Each run also walked into Triton's teleporters to learn where they go.

- **A map of the game data you can read (`docs/game-data.md`).**
  - **What:** the live memory reads the framework uses (WizWalker 1.8.2 names), those available but not used yet (an enemy's level, school and boss status outside battle; caster stats; spell effects; the duel), and the zone files with their parsers.
  - **Why:** the operator pointed out that WizWalker shows what game data is available for solving problems. Most fixes in this release replaced a guess with a read: patrol paths instead of exploring, teleport volumes instead of walking at walls, wards and resistances instead of the first card in hand. The map makes the next read easy to find.

- **Cards chosen by each enemy's shields, wards, traps and resistances.**
  - **What:** each round, the battle code reads every card's magic school and pip cost, and two things about every enemy. One is its shields, wards and traps: "modify incoming damage" hanging effects, for one school or universal. The other is its own resistance or weakness to each school, from its stats (`dmg_reduce_percent` by school plus `dmg_reduce_percent_all`, as Deimos's damage maths reads them). The default policy attacks with the affordable card whose school lands best on the target. So it never plays a Myth card into a Myth ward while another attack is in hand, and it prefers a school the enemy is weak to, or one it has a trap for. On a tie it keeps the first card in hand, as before. The event log shows each enemy's modifiers and resistances ("The Harvest Lord 335 (Myth -50%; resists Myth 30%)"), and each cast's school.
  - **Why:** the operator watched the wizard play a Myth card on The Harvest Lord while he had a Myth ward, and pointed out that schools are weak and strong against some enemies. The game holds both: WizWalker reads a combatant's hanging effects and stats, and Deimos's damage maths applies them by school, with 80289 as the universal school. The wizard lost that fight, the first defeat of the level-10 runs.
  - **Not verified yet:** these reads in a live battle. They follow WizWalker's offsets and Deimos's use of them; the choice is tested offline. Deimos curves high resistances; the policy uses the raw values, which only matters for ordering cards when resistances are large. Blades, pierce and which enemy to hit first are still not considered.
- **Healing, and saving pips for a heal.**
  - **What:** below 40% health the wizard still heals when it can. Now, when the heal in hand needs more pips than it has (and no more than seven), it passes to save pips for it, instead of spending them on an attack. The pass is logged with its reason ("saving pips for Fairy (3 pips)"). A heal that is out of reach, or whose cost could not be read, is not waited for. Policies may now return `policy.Pass(reason)`.
  - **Why:** the operator asked for healing logic that saves up pips when needed. In the lost fight, the wizard went from 166 to 45 health while casting one-pip attacks every round, and never had the pips for a heal.
- **Entering towers and dungeons with X.**
  - **What:** at a door, the loop walks in as before. If the interact prompt shows, it presses X once, then waits for the zone change. The turn record says whether X was pressed.
  - **Why:** "The Enemy Revealed" leads into a building on Triton's upper level. Walking into its door did nothing, and the run stopped on turns without progress. The operator pointed out that towers and dungeons are entered by pressing X. X is already one of the allowed keys.

### Changed

- **The run stops before the main quest leaves the world.**
  - **What:** when the active main quest's goal is in another world (the first part of the zone path, such as `Krokotopia` after `WizardCity`), the run stops and says so, instead of travelling there. `--leave-world` (`Limits.stay_in_world=False`) follows the main quest anyway.
  - **Why:** the operator's rule: "before you move on to the next world, you must complete all available side quests in current world, as a general rule. There might be times where this is not always possible." The framework does not do side quests yet, so it stops at the boundary and leaves them to the operator, rather than leaving the world with them undone.
- **Longer battles.** The battle code now gives up after 30 rounds or 15 minutes, up from 12 rounds and 10 minutes. The rematch with The Harvest Lord took 11 rounds and almost four minutes. At 12 rounds the battle code stops and leaves the fight to the operator, which in an unattended run means an idle wizard in battle.

- **Answering the Endorse a Wizard window with Friendly.**
  - **What:** the window is now answered with its Friendly button (`WorldView/EndorsementWindow/MainLayout/FriendlyWindow/FriendlyButton`) instead of being closed. If that button is missing, the window is closed as before. The event log says "endorsed the other wizard as Friendly" and never the player's name.
  - **Why:** the operator asked: "endorse a wizard pop up again, always say friendly". The window appeared again after a shared battle. Friendly is the kindest of the three choices (Friendly, Savvy, Helpful) to give someone the wizard knows nothing else about. `docs/safety.md` says how to decline instead.

- **Enemies are always avoided.**
  - **What:** the wizard steps away from every enemy that comes within 450 units, every time, unless the quest needs the fight: the targets of a defeat goal are still walked into. The dodge limit, which made the wizard walk on past enemies after three step-aways in a minute, is gone. When enemies keep blocking the way (three step-aways in a minute), the wizard now stands back for up to eight seconds and lets them walk on along their patrol, stepping away again if one comes close, and then plans again. The run's step-away limit (40) stops a wait that never ends and leaves it for the operator.
  - **Why:** the operator's rule is to avoid enemies always, unless the quest or dungeon requires the fight to move forward. With the dodge limit, the level-6 wizard walked on past two level-12 Red Banshees on Triton's upper level. Enemies patrol, so a blocked way usually clears if the wizard waits.
  - **Not handled yet:** a dungeon whose way forward is blocked by enemies the quest does not name. The wizard waits there, and the run stops at the step-away limit.

### Fixed

- **No straight-line walks across patrol paths.**
  - **What:** the straight-line route, the last method tried, is now refused if it passes within 450 units of an enemy. Where the zone's walk data loaded, it is also refused if it is more dangerous than its two ends, the rule merged legs already follow. When no route method is left, the trip ends and the next turn plans again, around the obstacles found so far.
  - **Why:** the operator saw the wizard walk "right off the side walk into the mobs". The walk-data route to the door of "The Enemy Revealed" was blocked partway. The fallback was a straight line to the door, which checked only duel circles and obstacles. It cut across the Scarlet Screamers' street and started a fight. The walk-data routes keep to the sidewalks. A straight line has nothing to keep it there, so it may only go where it stays as safe as its ends.
- **Long routes are found.**
  - **What:** a route search may now visit 60,000 grid cells instead of 8,000, for up to four seconds instead of two. The patrol-distance check, made for every cell the search visits, is about three times faster: buckets are 250 units instead of 1,000, so each check scans about a third as many samples, and it compares squared distances over sample lists gathered once per bucket. The walkable-area test uses `shapely.contains_xy` and no longer builds a point object per cell.
  - **Why:** after the teleporter fix, the wizard stood on Triton's upper level about 22,000 units from the door of "The Enemy Revealed". The route there needs about 31,600 cells. The search gave up at 8,000, the straight line ran into a wall, and the run stopped. A first search in a zone also pays for Deimos measuring each new cell's ground height (about 1.2 seconds for this route; Deimos caches the heights). With that, the search still took 1.9 seconds after the speed-ups; a repeat takes 0.6. The cell cap was set when an unbounded search in a large interior stalled a walk for minutes. The time limit guards against that on its own; the cap now only stops runaway memory use.
- **Doors in walls are reached through teleporters.**
  - **What:** a goal now belongs to the nearest walkable piece within 600 units, not 150. When that piece is not the wizard's, the loop walks into a teleporter first, as it does for other goals on another level.
  - **Why:** "The Enemy Revealed" sends the wizard into a building on Triton's upper level. Its door stands in a wall, 150 to 300 units from the nearest walkable ground, so the planner judged the door to be in no walkable piece and never looked for a teleporter. The wizard was on the lower level; every route failed and the run stopped on turns without progress. Doors, NPCs behind counters and quest objects are often outside the walkable area; 600 units covers what was seen while staying well short of the distance between levels.

- **The dodge limit counts all step-aways, not each enemy's.**
  - **What:** after three step-aways of any kind within a minute, at half health or more, the wizard walks on. The exception is a group of three or more enemies, which it still steps away from.
  - **Why:** on the way to Triton's Tele Up, several Ghost-Blue-L02 stood around the path. The per-enemy count let the wizard walk past one, then step away from the next, and the run stopped on turns without progress again.
  - **Replaced before release** by "Enemies are always avoided": the wizard no longer walks on past enemies.

- **A potion before distant wisps when health is low.**
  - **What:** below the potion threshold (40%), with potions allowed, the wizard drinks before looking for wisps. Wisps are now only sought within 2,500 units, down from 4,000.
  - **Why:** at 31% health on Triton Avenue, the wizard walked to three health wisps 1,500 to 3,700 units away through eel territory. Two had been used up and one trip was interrupted, before a fourth gave +163. Used-up wisps stay among the loaded entities, so a far trip can come back empty, and at low health every extra walk risks a fight.

- **No endless dodging of an enemy that blocks the way.**
  - **What:** once the wizard has stepped away from the same enemy three times within a minute, and health is at least half, it stops stepping away from that enemy. It walks on, and passes it or fights it. The event log records the decision.
  - **Why:** a `Minion-Myth-00` stood about 371 units from the wizard, on the way to Triton's Tele Up. Every turn the route led toward it, the wizard stepped away, and it planned again: seven times in six seconds, until the run stopped on turns without progress. At 70% health, one minion is a fight worth taking. Below half health the wizard still dodges, as before.
  - **Replaced before release** by "Enemies are always avoided": the wizard no longer walks on past enemies.

- **Stepping away from enemies without turning first.**
  - **What:** a step-away now moves backward with S when the close enemies are within 90 degrees of where the wizard faces, and forward with W when they're behind. It never turns first, lasts 0.8 s, and the event log says which way it went.
  - **Why:** the operator saw that the wizard still got caught. Three of the first four battles of a Triton run began right after a step-away (at 384, 268 and 343 units). Measured in the game: reading the state takes about 1 ms and finding enemies about 1 ms, so the 20 Hz watcher does notice in time. But a 180-degree turn with A and D took 1.88 s, during which a chasing enemy closed in. S moved 380 units in 0.6 s, as fast as W (370), with no turn at all.

### Added

- **Going to the patrol path of a goal's enemy.**
  - **What:** when a defeat goal has no arrow and none of its enemies are in sight, the loop looks up the enemy's name from the goal (`WizardMobs_00000331` is "Scarlet Screamer") and matches it to the zone's patrol path names ("Path 10_Screamer", "Path 11_Screamer"). It then walks to the nearest point on those paths. Words match when they start with the same four letters, so "Rotting Fodder" finds "Path 06_Rotter". Exploring area by area remains the fallback when no path matches. Paths of seasonal events ("Path RedPageEvent - Spellwrit Screamer") are never chosen, because their enemies are there only while the event runs; they are still avoided.
  - **Why:** the operator asked to use game data as much as possible to complete goals. Exploring found the Scarlet Screamers only after a long, fight-filled walk through the wrong level. Their paths were in the zone's files all along.

- **Routes keep away from enemy patrol paths.**
  - **What:** each zone's patrol paths are read from its `pathNodeData.bin` (node positions) and `pathData.xml` (path names and their node ids), in `patrols.py`. Paths for wisps, reagents and chests are left out. Route steps within 700 units of an enemy path cost up to 4 more, so routes prefer the parts of a street enemies don't walk. A merged straight leg may not be more dangerous than the steps it replaces.
  - **Why:** the operator saw that the wizard still didn't keep to safe ground, such as sidewalks, and kept ending up in fights. Until now, routes only avoided enemies that were loaded and in sight, and merging routes into straight legs could cut back across a street. Triton's paths are named after what walks them ("Path 01_Eels", "Path 04_Minions", "Path 10_Screamer"). Their nodes lay 1 unit from where Rotting Fodder were met, 41 from the Haunted Minions, and 685 from the Electric Eels, which wander. The Tele Up landing is 2,683 units from any of them.
  - **How the files were read:** the layout was inferred. A node is a 92-byte record with x, y and z 36, 40 and 44 bytes in, and its id 68 bytes in. A path's name is followed by its node ids, 8 bytes apart. Triton gives 549 nodes and 40 paths, and 523 nodes belong to a path.
  - **Not verified:** other zones' files; whether paths with only a number (Triton's 15 to 24) are enemies (they are avoided to be safe); how far a given enemy strays from its path.

- **Exploring for a defeat goal's enemies.**
  - **What:** when a defeat goal has no quest arrow and none of the enemies it names are in sight, the loop walks to the nearest unexplored part of the zone and stops as soon as one shows up. The zone's walkable area is split into points about 2,500 units apart on every level (`FreeArea.exploration_points`), and the loop uses teleporters where needed. Once every point has been seen, it stops for the operator. The event log says where it is looking and how many areas are left.
  - **Why:** "Clear as Crystal" asks for Scarlet Screamers on Triton Avenue, and the goal has no quest helper. Enemies only load when the wizard is fairly close, and the zone's spawn data names "Spawn point 10_Screamer" and "11_Screamer" without positions that could be read. Looking around is what a player would do.
  - **Order:** with no arrow, the loop first works on any open goal whose target it can locate, such as the Cog, before searching for another goal's enemies. The search starts in the walkable pieces that hold the quest's other placed targets: a quest's targets tend to be near each other. The operator confirmed that the Scarlet Screamers are on Triton's upper level, where the quest's Cogs are. Searching nearest-first had sent the wizard through the eel-filled lower street.
  - **Not verified:** how long a full search takes in large zones. The run's time and turn limits still bound it.

- **Closing the Endorse a Wizard window.**
  - **What:** before each turn, and before concluding that a popup holds the keyboard, the loop closes known popups with their own close button. So far that's only the "Endorse a Wizard" window (`WorldView/EndorsementWindow/CloseEndorsementWindowButton`). It never picks an endorsement, and the event log never records the other player's name. Unknown popups still stop the run.
  - **Why:** after another player joined one of the wizard's battles, the game asked to endorse them. The window held the keyboard, and the run stopped on ignored turn keys. It's the same window the operator closed by hand after a restart. Closing it declines an optional social action; nothing is sent to anyone.
  - **Replaced before release** by "Answering the Endorse a Wizard window with Friendly".

- **Targets for goals the quest arrow doesn't point at.**
  - **What:** when the arrow reads (0, 0, 0), the loop now looks for the goal's target itself. It tries placed objects first: the zone's `gamedata.bin` gives every placed object's template and position (`placed.py`), and the goal's client tags name the objects it needs, so the loop walks to the nearest unused match. Otherwise it tries enemies: each goal now carries the language codes its text fills in for the item and the enemy, and each tracked enemy carries its template's display code, so the loop walks to the nearest loaded enemy whose code the goal names. A used object isn't visited again, and the event log says which target was chosen.
  - **Why:** "Clear as Crystal" asks the wizard to collect a Cog, then defeat Scarlet Screamers. The goal the game tracked had no quest helper, so the arrow read (0, 0, 0), and the Cog wasn't among the loaded entities. The goal's tags were `WC_TA_Cog` and `Ddl_WC_TA_Cogs`, and Triton's `gamedata.bin` places six `WC_TA_Cog instance` objects on the upper level. The defeat goal names its enemy as `WizardMobs_00000331`, "Scarlet Screamer".
  - **How the file was read:** the layout was inferred. An object's name is stored after a 2-byte length, and x, y and z are floats 54, 50 and 46 bytes before it. Triton's telepad 04 decodes to (-10536.5, -6778.9, 137.5), as the live entity reads, and its other telepads sit where its teleport volumes are.
  - **Goals in another zone:** with no arrow, the loop walks into the placed street gate whose name shares a word with the goal's zone (Olde Town's `WC-GateStreet_TritonLane` for `WC_Triton`), else the gate nearest where the wizard arrived from that zone, recorded on each zone change.
  - **Not verified:** other zones' files; goals whose tags name NPCs rather than objects; enemies not loaded yet.
- **A teleporter is judged only once reached.** A walk to a teleport volume that fails or is interrupted no longer records it as "no effect". On Triton, a walk to Tele Up timed out short of it, Tele Up was written off, and the loop walked out the Olde Town exit instead.

### Fixed

- **An arrow with no target stops the run instead of walking to the map's origin.**
  - **What:** a quest arrow reading (0, 0, 0) now stops the run with "the quest arrow shows no target for the ... goal", for the operator.
  - **Why:** in "Clear as Crystal" the open goal is to collect a Cog from Triton Avenue, and the arrow read (0, 0, 0). The loop walked the wizard to the origin and tried four times to use an object that wasn't there. The same reading means "no target" when no quest is active.
  - **Not verified:** where such goals' targets can be found by reading the game. The Cog isn't among the loaded entities.

### Added

- **Health and mana wisps.**
  - **What:** wisps are now tracked among the loaded entities (names containing "WispHealth" or "WispMana", such as `WC_WispHealth`). Below 65% health the wizard walks to the nearest health wisp within 4,000 units that has no enemy within 600 and isn't in someone's duel circle. With mana under half it does the same for a mana wisp. That comes before a potion or a rest. A wisp it reached that gave nothing isn't tried again, and the event log records each pickup with the stat before and after.
  - **Why:** the operator pointed out that the map's red and blue wisps restore health and mana. On Triton Avenue health didn't regenerate, and with mana at 4 of 24 the wizard could only cast free wand spells, so two Electric Eels took 136 s and left it at 99/624. Wisps are free and part of normal play, so they come before a scarce potion.

- **Teleport volumes between the walkable areas of a zone.**
  - **What:** each zone's teleport volumes (name, position, radius) are read from its `volumes.xml` (`teleports.py`). When the quest target lies in another piece of the zone's walkable area than the wizard, the loop walks into a volume in the wizard's piece, as into a door. It takes one already known to land in the target's piece, otherwise the untried one nearest the target. It records where it led (a piece of this zone, another zone, or nothing), so a volume that left the zone or did nothing isn't tried again, and logs each crossing.
  - **Why:** "Quest for Clues" sends the wizard to Rotting Fodder on Triton Avenue's upper level. That level sits about 1,100 units above the lower street, and the two halves of the walkable mesh meet only at sheer drops, so every route failed and the run stopped. The operator suggested a teleporter. The zone's volumes include "Tele Up" and "Tele Down", and walking into "Tele Up" at (-16336, 1176) put the wizard at (-17120, 880) on the upper level. Walking into the game's own teleporters is ordinary play, like a door; it is not the memory-writing teleport this framework never uses.
  - **How the file was read:** `volumes.xml` is KingsIsle's binary format, and its layout was inferred, not documented. After each volume's name, x, y and z are floats 8, 20 and 32 bytes on, and the radius 60 bytes on. All eight of Triton's volumes decode to sensible places: the exit to Olde Town matches where the wizard entered, and "High_Ledge" matches the `WC_Triton_Telepapad_04` entity. Values outside plausible ranges are dropped.
  - **Not verified:** other zones' files; volumes whose name leaves out the "TeleportVol_" prefix; and where the other volumes lead.

- **Health potions, opt-in (`--use-potions`).**
  - **What:** out of battle, below 40% health, with a full potion charge, the wizard clicks the HUD's potion button (`WorldView/windowHUD/btnPotions`) and the event log records health, mana and charges before and after. If health doesn't rise, the button isn't tried again that run. Potions are never bought.
  - **Why:** on Triton Avenue two Electric Eels left the wizard at 99/624. Health doesn't regenerate on that street, and it was too low to quest on safely, so the run stopped. The operator allowed drinking potions the wizard already has, but not buying any. It is off by default, because using consumables is a choice the operator makes. The threshold matches the combat policy's heal threshold, so a merely tired wizard still rests instead of using a scarce charge.

### Fixed

- **Talking to the quest NPC, not a neighbour.**
  - **What:** a talk that leaves the talk goal open counts as no progress, and the next try walks right up to the quest arrow instead of trusting the interact prompt. The event log says when this happens.
  - **Why:** on Triton Avenue the wizard stood 189 units from the arrow. The prompt check accepted that, because the friendly NPC nearest the arrow was the quest NPC, but X reached another NPC standing closer to the wizard. Each one-page reply counted as progress, so the run talked to the wrong NPC seven times until it was stopped by hand. Trusting the prompt is still tried first, because it is what lets the wizard talk across a counter (the Librarian in the Commons).
  - **Not verified:** a quest NPC behind a counter with another NPC closer to the wizard. The second try would fail to get within reach, and the run stops on turns without progress.

### Added

- **Live event log.**
  - **What:** each run writes `runtime/events-<started>.jsonl`, one JSON line per event with a readable summary that is also logged as it happens. Events cover:
    - the run starting and stopping;
    - zone, level and quest or goal changes;
    - each battle's start, every round (the wizard's health and pips, the card played, the enemies left), and its end (outcome, rounds, seconds, enemy names and count, health before and after, gold gained, level);
    - walks (distance, result, each route method's outcome, new obstacles);
    - rests (seconds and health before and after), step-aways (which enemies, how close);
    - dialogs (pages, follow-ups, offers) and NPC menus (options and choice).

    The state snapshot now includes gold, the turn line includes health, and the report names its event file. A battle's summary gives the most enemies seen at once, because enemies join after the first round (an Electric Eel fight on Triton Avenue grew from one eel to two), and same-named enemies can't be told apart.
  - **Why:** the operator asked for a way to describe the environment so the watcher stops making assumptions. While watching a run, a 90-second battle was reported as "probably a bigger group of enemies". The report later showed it was 5 rounds against a single Haunted Minion. The end-of-run report alone can't answer questions while a run is live, and timings invite guesses. WizWalker exposes no experience-points reading, so rewards are shown as gold, health and level.

- **NPC services menus, and quest titles from the game's language files.**
  - **What:** when an NPC opens its services menu (`NPCServicesWin`, a list of quests by title), the offer policy picks an option. `MainQuestsOnly` takes the option for the active quest, or else the first title the operator approved with `--approve-quest`, and otherwise stops and lists the options. The journal now carries each quest's display title, looked up in `Locale/en-US/*.lang` in Root.wad (`language.py`).
  - **Why:** after "Panic in Three Streets!", Sergeant Muldoon in Olde Town opens a menu of three quests instead of a dialog. The loop didn't recognise it and stalled. A quest's main-quest flag can be read only after accepting it, since the quest definitions are not in the installed files. So the framework never guesses: it needs the active quest's title or the operator's approval. On a non-main-quest offer, the loop still stops once the journal shows it.
  - **Menus that reopen:** Muldoon's menu reopens after every conversation. Choosing the active quest's option again only replays its dialog, and the open menu kept the wizard from walking away (four rounds, stopped by hand). Now the active quest's option is taken only when that quest has business with this NPC (ready to turn in, or a talk goal here); otherwise the menu is left with its Cancel button. An approved title is taken only when no quest is active, one main quest at a time. `Limits.max_menu_choices_without_quest_change` (3) stops a menu loop that slips past this, since dialogs count as progress.
  - **Two readings that misled:** `QuestData.ready_to_turn_in()` read true for quests whose goals were all still open, so "business with this NPC" relies only on a talk goal at the arrow. And the menu reopens a moment after each dialog, swallowing the turn keys of a turn that began free to move; the loop now checks for an open dialog or menu before concluding that a popup holds the keyboard.
  - **How the titles were checked:** the three options ("Trouble on Triton Avenue", "Putting Out the Fire!", "A Good Day to Cyclops") are listed as Wizard City mainline quests 133 to 135 on [Wizard404](https://wizard404.com/), an automated Wizard101 wiki. The site says its quest data may be incomplete, so the journal check after accepting stays the final word.
- **Waiting and window names when the wizard isn't free to move.**
  - **What:** such a turn now waits 3 s, and records the names of the visible windows under `WorldView`.
  - **Why:** the services menu set the game's dialog flag without the usual dialog window. The loop then used up its four no-progress turns within the same second, with nothing in the report to say why.
- **Walk trails and route logging.**
  - **What:** each route attempt records the wizard's position every 2 s (`trail`, up to 90 points) and logs a line when it starts.
  - **Why:** one walk in the Shopping District kept moving for the full 180 s without arriving or getting blocked. Without positions, its report couldn't show whether the wizard circled, slid along a wall or followed a bad route.

- **Door-loop guard and zones in the turn log.**
  - **What:** each turn's log line now shows the zone and the quest goal. The run stops after `Limits.max_zone_changes_without_quest_change` (10) zone changes in which the quest goal stayed the same.
  - **Why:** walking through a door counts as progress, so a wizard bouncing between two zones would never trip the stall limit. Without zones in the log, a watcher also can't tell a long door chain from a loop. On 2026-10-26 a run going from Ravenwood through the Commons and the Shopping District toward Olde Town was stopped by hand as a suspected loop; the report showed it was a real trip. Ten changes leaves room for chains like that one (about five doors) and still catches a back-and-forth well before the 200-turn limit.
  - **Not verified:** whether 10 is enough for the longest legitimate door chains later in the game.

### Fixed

- **Routes avoid collision walls.**
  - **What:** the "collision" method's free area is now the walkable navmesh minus Deimos's height-aware collision walls (`zone_bcd_walls`), padded by `navigation.WALL_CLEARANCE` (30 units). Grid cells outside it count as unwalkable, and merged legs, including "nav" legs, must stay inside it.
  - **Why:** Deimos's walk grid and `straight_path_walkable` check only the navmesh, on purpose: Deimos walks through some volumes that only block teleports. In the Commons, though, the walls are trees, fences and buildings. Every route to the Ravenwood door walked into them, and obstacle memory alone just boxed the wizard in. All 40 points where the wizard got blocked lay within 100 units of a collision wall. With the walls subtracted, the wizard's position and the door are in one connected free area, and the planned route goes around the east side.
  - **Verified:** offline, the route from the stuck spot (about -678, -786) to the door plans in under 0.1 s, and every leg stays in the free area. In the game, the next run walked from that spot to the Ravenwood door, went through it, and talked to the quest NPC.
  - **Not verified:** zones with several floors. The walls are flattened to the map, so a wall on another floor could block a route. A padding wider than 30 units cut the Commons' free area into pieces.

## 0.1.0 (2026-10-26)

First public release: the prototype scripts behind one character's unattended level 1 to 5 run, restructured into a package that other agents can build on.

### Added

- **`wizardtraining` package.**
  - **What:** session, state, movement, navigation, entities, quests, dialog, combat and loop modules; a command line (`probe`, `play`, `stop`); and three examples.
  - **Why:** the prototype was a folder of scripts with machine-specific paths. A package with one entry point is something others can install and extend.
- **Split between "decide" and "do" modules.**
  - **What:** route search, target choice, combat and offer policies, run limits and progress need no game access, and an import-boundary test keeps it that way.
  - **Why:** most bugs in the prototype were decision bugs: progress counting, threat judgement, card choice. Logic that runs without the game can be tested in seconds, on any OS, by any agent.
- **Replaceable policies.**
  - **What:** `CombatPolicy` (which card to play) and `OfferPolicy` (what to do with a quest offer), and goal handlers through `QuestLoop.goal_handlers()`.
  - **Why:** these are the parts other agents will most want to change. Keeping them separate means a new strategy cannot accidentally break walking, hooks or limits. The battle code validates a policy's choice and passes instead of acting on an invalid one.
- **Allowlist of keys.**
  - **What:** `keys.ALLOWED_KEYS` holds W, A, S, D, X and Space. Anything else raises `RefusedKey`.
  - **Why:** in the prototype, the forbidden keys (Q, End, Home, Escape, Ctrl+S, Ctrl+T) were only a convention, and Q was sent once and opened the quest book. An allowlist fails safe for keys nobody has thought about yet.
- **Settings from environment variables.**
  - **What:** `WIZARDTRAINING_DEIMOS` and `WIZARDTRAINING_RUNTIME`.
  - **Why:** the prototype hard-coded a local Deimos path and output folder.
- **Documentation:** README (setup, use, the rules to keep, where to extend, and an unofficial-project and terms-of-service notice), plus architecture, safety and lessons learned under `docs/`.
  - **Why:** the main value of this release is what was learned. The docs record each rule's reason, so nobody has to rediscover it the hard way.
- **Offline tests:** 67 tests on the standard library's `unittest`.
  - **Why:** they need no extra packages and run on the Python every contributor already has.

- **Obstacle memory.**
  - **What:** when walking stalls, the point just ahead is recorded as an obstacle for that zone. Later routes treat it as a small no-go area (`OBSTACLE_RADIUS`), and the next route method on the same trip already plans around it. Obstacles near a trip's destination are ignored, so bumping into an NPC never makes it unreachable. Finding one counts as progress, capped by `Limits.max_obstacles_per_zone`.
  - **Why:** the first smoke run of this package in the Commons walked into something the zone's walk data calls clear. Every route method then aimed at the same spot, sidestepped four times and gave up, until the run stopped on turns without progress. The prototype never met this because its routes in the Commons happened to avoid that spot. Walk data is a map, not the territory; the wizard has to learn from what it bumps into.
- **Smoke-run fix:** `progress.travel_outcome` takes the walk's stop reason rather than the trip, after a `trip=` detail clashed with its own parameter and crashed the first bounded run. A regression test covers it.

### Changed from the prototype

- **Reports keep dialog page lengths, not page text.**
  - **Why:** NPCs address the character by name, and reports get shared when people ask for help.
- **The collision route method always uses the framework's own bounded A* over Deimos's walk grid.** The prototype used Deimos's `find_walk_path` when there was nothing to avoid.
  - **Why:** one code path, always bounded by the 2 s planning limit, which the prototype added after an unbounded search stalled a walk.
- **An ignored turn key raises `KeysIgnored`.** The prototype searched each turn's report text for a phrase.
  - **Why:** a typed exception cannot be missed by a reworded message.
- **Turn calibration is kept per client, not in a module-wide class.**
  - **Why:** it is a property of the game window being driven.

### Verified, and not

- **Verified in the game with the prototype scripts:** everything in [docs/lessons-learned.md](docs/lessons-learned.md), from level 1 to level 5 in Wizard City.
- **Verified with this package:** the 67 offline tests (with and without WizWalker installed) and `python -m wizardtraining probe` against the live game. Three bounded smoke runs of `play` in the Commons, walking toward the Ravenwood door: the first found the `travel_outcome` crash, the second the walk-data blockage. In the third, with obstacle memory, five turns in a row made progress before it stalled again; it had not reached the door when this release was cut.
- **Known issue:** reaching the Ravenwood door from the south of the Commons still stalls. The next release will look into it.
- **Not verified:** zones beyond Wizard City's starting areas, goal types other than bounty, bountycollect, persona, waypoint and usage, group fights, and any game update after 2026-10-26.
