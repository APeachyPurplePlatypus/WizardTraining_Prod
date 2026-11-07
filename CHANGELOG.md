# Changelog

What changed in this guidance, and why. Say what was seen in the game and what wasn't.

Entries up to 0.3.0, when this repository also held an implementation, are in [CHANGELOG.md at v0.3.0](https://github.com/APeachyPurplePlatypus/WizardTraining_Prod/blob/v0.3.0/CHANGELOG.md).

## 0.5.0 (2026-11-07)

### Added

- **The level 20 to 25 retro** (docs/retros/level-20-to-25.md).
  - **What:** two dungeons cleared alone by their door puzzles, planning with an outside game database, a per-zone log of stuck walks, and the quests set aside for doors and props.
  - **Why:** each five-level step ends with its findings.
- **Lessons from the second world's dungeons and hub** (lessons learned: Moving, Quests and dialogs, Fighting, Health and refills, Travel and marks, Dungeons, Gear and mounts).
  - **What:**
    - Doors that open on objects are puzzles with state: read each object's state, press until it shows the one wanted, and wait out a turn in progress. A door's openers can be fights, and a refill trip must not start them over.
    - If you can't leave a room, look for a lever or switch. A goal behind a door waits for the door.
    - A nav link that keeps failing at the same spot runs through something solid: set it aside for the zone. Reach a goal across a gap from the gap's edge, and a door on another level by the nav graph's heights. A quest arrow on a teleport volume is a door. Rides take the keyboard; wait them out.
    - Keep a log of every stuck walk per zone, and read it before a fix.
    - A Quest Finder giver may only run a shop. A quest set aside must not lead out of the world or back into a dungeon. A prop can shut a goal off.
    - Read absorbs and damage over time on enemies; don't stun the stun-immune; stack a second trap rather than pass; never pass with a shield of every school in hand; leave out hits a cheaper one outdoes; a small deck makes long fights.
    - Use a dungeon's own wisps, mana ones too; go into a walk-in side room refilled; mark only at the goal zone's own door; train from another world by its world door.
    - Extra starting pips come early only from paid packs; an outside database helps plan but may not cover drops or shops.
  - **Why:** each came from play on 2026-11-02 to 07 in Krokotopia, several from the operator's own words (stuck walks, levers, stuns, shields, wisps).
  - **Seen in the game:** the door puzzles in both dungeons, the set-aside nav link (the goal reached at the first try), the lever's floor below (the next room loaded) and the dungeon wisps. Not checked one by one in play: the fight rules and the ride wait. Not yet built: the goal that waits for its door, and the retry of a quest switch after an offer box.

## 0.4.0 (2026-11-02)

### Removed

- **The implementation.**
  - **What:** the implementation that played these runs (the play loop, its scripts, its tests and examples, and the zone-specific logic) has been removed from this repository and is no longer maintained here. The tags of earlier releases still hold it as it was.
  - **Why:** the operator, 2026-10-29: the framework "was going to be light wight and allow the agents to determine their own implimentation", and "we give general advice and guidelines that we have learned though our playing and development mistakes. but it isn't meant to be a configuration or implementation guide, An agent is supposed to be able to read it, and problem solve on their own how they would come complete the goal."

### Changed

- **Every document is rewritten as guidance** (README, lessons learned, safety, game data, architecture, the level 10 to 15 retro).
  - **What:**
    - Module, function and constant names, command-line flags and local paths are gone.
    - Lessons say what happened, what it taught and what to try.
    - Safety is a set of principles to agree with an operator, without one account's approvals.
    - Game data describes what the game exposes and where to look, without exact offsets or window paths, which change with game updates.
    - Architecture is design advice.
  - **Why:** an agent building its own bot, in any language, should be able to use every line without a particular codebase in hand.
- **The pull request template** asks what a change teaches and what was seen in the game, instead of about tests.

### Added

- **The level 15 to 20 retro, and lessons from the second world's first dungeon** (docs/retros/level-15-to-20.md; lessons learned: Dungeons).
  - **What:**
    - A return button can land at the dungeon's start; compare enemies only near the exit spot.
    - A gate the walk data calls open can be shut by a script; read the trigger file for its opener.
    - A dungeon's side quest can hold the key to its main quest.
    - Leaving a dungeon can change the active quest; a quest set aside must stay aside everywhere.
  - **Why:** each came from play on 2026-11-02 in Krokotopia. A refill waited in place after a misread reset, then lost a fight. The run stopped three times at a scripted gate. A parked quest was played again from the hub. A dungeon exit sent a restart toward another world. The return-button fix was seen working in the game. The obelisk door comes from the zone files and is not yet played.
- **Lessons from finishing the first world and starting the second** (lessons learned: Moving, Quests and dialogs, The zone graph, Fighting, Teams).
  - **What:**
    - In a world's hub, Go Home moves a stuck character to the hub's landing ground with no load; watch for the jump, not a zone change.
    - Fill up before walking into a zone whose quest starts over on entry, and count its side rooms as part of it.
    - Remember which worlds were cleared across restarts.
    - Don't route between streets through a dungeon.
    - A prism turns a resisted hit into the opposite school; price it by the shares, and give the deck planner a rule for it.
    - Call a fight by what it paid, not by the health left; cast a likely kill rather than flee.
    - Some enemies out-heal a lone character: set the quest aside for later levels or a team.
    - Boss credit goes to those in the fight: walk onto the boss's combat spot from the zone data, and join at the circle's edge.
    - Never press a chest that costs real money.
  - **Why:** each came from play on 2026-11-01 and 02: a sewer quest lost four times to a healing boss and once to a flee, a team boss beaten twice without the character, a deck that left out a card the operator asked for ("use ice prism on ice enemies"), a won fight logged as lost, restarts that walked back to a cleared world, and two stuck walks in the second world's hub.
  - **Seen in the game:** all of the above. After the fixes: the hub escape by itself (3 s to landing), the prism (135 against about 91 straight), the cleared world left alone on restart, the boss proof with the fifth team, and the fill-up before the sewer (20 to 107 mana in 74 s). Not yet seen: a sewer boss beaten; it is set aside for later levels.

- **Lessons from the Olde Town sewers** (docs/lessons-learned.md). Two lessons. A quest can live in one zone only: the journal lists it only inside that zone and it starts over on each entry, so don't call a world cleared from a journal read elsewhere, and finish such a quest in one visit. And walk into an enemy standing alone, waiting a while for one where fights have been costly. Both were seen in play. Refilling inside the zone kept the quest's progress, and a wait got a lone target.

- **Lessons from seven towers in one quest** (lessons learned: Moving, Health and refills, Dungeons, Stopping).
  - **What:**
    - Learned keep-outs (hidden doors, walk-in trigger volumes) are soft: walk past them when they leave no way that exists without them.
    - Blame enemies for a missing route only when there is one without them.
    - After a few waits for blocking enemies at good health, take the plain route and accept the fight.
    - Set aside a teleporter that no route reaches from where the character is.
    - A door learned at an arrival spot is pushed through along the way the walk came.
    - Finish a goal that needs no fight before a refill trip.
    - A dungeon's return button can go before its timer does, perhaps when another instance is entered.
    - With several goals and no arrow, check the dungeon left before picking the nearest goal.
    - Count actions taken toward a run limit, not checks made.
  - **Why:** on 2026-11-01 one side quest asked for a book read in each of seven towers, with no quest arrow. Each lesson above was a stall or a lost trip on the way: twelve minutes with no route out of a street, three minutes waiting on four enemies, two minutes on an unreachable teleporter, a run ended at full health by a count of looks, and a tower done twice after a refill trip before its last step.
  - **Seen in the game:** every stall above, and the quest finished after the fixes: the book was read straight after the boss's second defeat with no trip home, and the street was walked out of once the learned keep-out was gone. The plain-route rule fired after four waits, but that walk was still closed by the keep-out, so a walk past blocking enemies has not been seen through yet. Also not yet seen: whether entering another instance is what drops a return button.

- **Lesson: a stuck point marks a whole obstacle** (lessons learned: Moving).
  - **What:** when the character gets stuck at a point inside a solid the collision data knows, keep the waypoint graph out of that whole solid, not just a small circle around the point; don't keep it out of every solid in advance.
  - **Why:** on 2026-11-01 routes by the game's waypoint graph got stuck twice in ten minutes at the same object, 1,000 units across, with four waypoints inside it: the learned stuck point kept only a small circle clear, so the next route moved over one waypoint. Across nine zones' game files, a tenth to a fifth of the waypoints lie inside some solid, and excluding them all broke one zone's graph into three pieces.
  - **Seen in the game:** the two stuck walks at the same spot. Measured offline against the zone's game files: the same walks keep out of the object at the same length. Not yet seen in play with the change.

- **Lesson: a talk prompt can show far from its NPC, so answer it as soon as it shows** (lessons learned: Quests and dialogs; symptoms: Movement and keys).
  - **What:** on the way to an NPC, check the talk prompt before the walk and on every step; when it offers a talk and that NPC is the nearest person to the character, with nobody else close by, press interact from there, without stepping closer; look for other people by name as well as among the friendly NPCs; fall back to walking right up if the talk opens nothing, opens a menu instead, or reaches someone else.
  - **Why:** the operator, 2026-11-01: "sometimes you are on a ledge for example and the entiy is floating in the air, i might walk twoards the wall on the ledge and loop because I think I am not close enough when in reality the dialog box is loaded and ready to be pressed". A quest NPC floating about 2,600 units past a ledge's edge and 1,900 below it had his prompt showing at the edge, while the bot walked on toward him.
  - **Seen in the game:** the prompt at the edge, and one interact key there opening the dialog (pressed by hand). The first try by the bot itself, elsewhere, pressed at a prompt about 1,500 units from the quest NPC with no one within 600, and it was someone else's: nothing opened, and walking up finished the talk. So the lesson now asks that the NPC be the nearest person, and counts a menu in place of a dialog as a miss. Not yet seen in play: the bot pressing at the floating NPC.

- **Lesson: rank safety over distance, and price the whole way** (lessons learned: Moving).
  - **What:** make danger the route cost and distance the tie-breaker; price a waypoint graph's links along their length; never let smoothing a route into straight legs add time in the street; when two kinds of walk data both give a route, walk the clearly safer one.
  - **Why:** the operator, 2026-11-01: "for path finding prioritize safety and side walks above shortest path routing". The run preferred the game's waypoint graph in most streets, and its routes ran down the street beside the enemy paths: one walk met two fights, each right after backing away from an enemy close to the route.
  - **Seen in the game:** the two fights on one walk. Measured offline against eight streets' game files: the share of the way on paving and the extra length. Not yet seen in play with the change.

- **Lessons on teams, two decks and a full backpack** (lessons learned: Fighting, Teams, Gear and mounts).
  - **What:**
    - keep a mob deck that ends fights fast and a boss deck for long fights, switched out of battle, and value an area attack by its share over every enemy;
    - a dungeon's matchmaking search may show only on the HUD; quest while it runs; never search with a run of that dungeon open; join the team's fights, since credit needs presence; never flee with teammates; count teammates without naming them;
    - when every route fails, test the bot's own keep-outs first;
    - a full backpack refuses purchases and loot, so agree a selling order with the operator.
  - **Why:** on 2026-10-29 a dungeon boss beat the wizard with every combat strategy at levels 16 and 17. The operator approved matchmaking and a bigger deck, and asked for two decks: "Mobs would focus on AOE attacks, basically trying to fight as fast as possible. you don't have AOE but you can add this to the framework for later. Boss would focus on strats and longer battles". The first matchmaking try formed a team, but the wizard went in alone while searching, then stood at the entrance unable to route to its team.
  - **Seen in the game:** the HUD search, the countdown and the teleport; the refused purchase at a full bag; every route failing until the keep-outs were dropped (offline, against the zone's data). Not yet seen in play: the deck switch, an area attack, and joining a teammate's fight.

- **Lessons from 2026-10-28 and 29**, written as advice:
  - closed-loop steering at 100 Hz (look-ahead cornering, braking by measured speed, the turning circle, live pursuit of moving targets, a nearer horizon in crowded streets);
  - discarding to dig for better cards;
  - acting promptly after a battle;
  - "a miss is not immunity" and spending idle pips;
  - never marking where a fight just happened, and reading the Recall timer;
  - learning where travel lands with care;
  - stopping only where no enemy walks;
  - checking that waiting gives something back;
  - mounts;
  - spotting opportunities, and the Quest Friend Finder.
  - **Why:** each came from a real failure or measurement in play. The fight-length and mark lessons followed seabed fights of 11 to 12 rounds costing 43 to 53% of health, and two Recalls that landed in fights.
- **A page of symptoms and their likely causes** (`docs/symptoms.md`).
  - **What:** what a run going wrong looks like (keys that change nothing, creeping toward a target, turns that repeat at once, a use that "did nothing", numbers that jump, doors that aren't there), with the causes found in play for each, and what to check first.
  - **Why:** the same few causes came back again and again in two days of play, and each took a stop and a read of the logs to find. An agent starting from nothing gets there faster from the symptom.
- **Dungeon lessons from Sunken City**, in the lessons' Dungeons section and the symptoms page:
  - side rooms are the same dungeon;
  - walking back in through the door can start a new instance;
  - a flee's move to the hub comes after the battle ends;
  - a walk-up that crosses a door.
  - **Why:** in one afternoon, Sunken City's progress was lost twice: after a defeat in a side room, and after a flee. Both times the run walked in through the door instead of using the return button.
- **Lessons from level 16 in Wizard City**, written as advice:
  - a stats read can be another player's, and tools that hook the game share its hooks;
  - walk data is flat, so compare heights before closing in on a target;
  - other players' fights are obstacles that move on: back off and wait;
  - the game counts goals late and step by step, so judge a use by which goal closed;
  - an arrow at a door means the target is behind it;
  - retry set-aside quests before leaving a world;
  - a goal's tag can be in an object's template rather than its name;
  - a flee can move the character, so learn doors only from walks;
  - read the turn order, count damage over time, know when a fight is lost on heals, and when a shield beats an attack;
  - heals left in hand at a fight's end are wasted.
  - **Why:** each came from a stall, a loss or a measurement in play on 2026-10-29: a four-minute creep under a balcony NPC, eleven refused approaches in a second beside another player's duel, shells and a book pedestal that worked but were logged as misses, a door learned from a flee, three losses to stronger groups in Sunken City, and a heal left unused in 32 of 38 wins.
  - **Verified:** in play, except the shield ordering, which is not yet seen in play.
- **What patrol and spawn data say about safe ground** (game data, lessons learned).
  - **What:** spawn data tells enemy paths from wisp, reagent and chest paths better than path names do; a path's nodes come from its own list, in any order; sidewalks are safer than streets but not safe; wisp paths are where to look for wisps.
  - **Why:** a proposal to treat sidewalks and wisp paths as safe was checked against the game files of 19 zones. The spawn data part held and cut the ground priced as near enemies by 33 to 59% in the five streets measured; the safe-sidewalk part didn't, since in four busy streets a quarter to half of the sidewalk lay within 600 units of an enemy path.
  - **Verified:** against the installed game files and offline route planning in nine zones. Not yet seen in play.
- **A check that no path from someone's own machine is committed** (`.github/workflows/no-local-paths.yml`).
  - **What:** on every push and pull request, the tracked files are searched for Windows user folders, home folders and cloud-synced document folders. Any match fails the check and is listed.
  - **Why:** a path from a contributor's machine tells readers their user name and how their machine is laid out, and helps no one else.
  - **Verified:** the pattern passes the current files and flags a sample Windows user folder.
