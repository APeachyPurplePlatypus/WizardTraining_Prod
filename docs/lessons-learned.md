# Lessons learned

These come from one character's unattended play from level 1 to 15, in Wizard City and Krokotopia, from 2026-10-26 on. An operator supervised it, and the agent that built and ran it changed it after every surprise. Each lesson says what happened, what it taught, and what to try. Each run's findings are summed up in the [retros](retros/), the latest [level 10 to 15](retros/level-10-to-15.md).

The numbers are from one character on one game build. Use them as a scale, not as settings, and measure your own.

## Reading the game

- **Hooks are patches to the game client.** A run killed while its output was piped through another program died before it could remove its hooks. Every later attempt to hook failed until the game was restarted. Always remove hooks on the way out, and give the bot a stop signal it checks often, such as a file it looks for, instead of killing it.
- **Install only the hooks you read from.** Player, stats, client, root window and the quest arrow were enough for play, plus the mouseless cursor and render context for clicks. Anything that can move or teleport the character isn't needed and shouldn't be installed.
- **The quest arrow lags behind its hook.** Right after hooking, or while no quest is active, reading it fails for a few seconds. Retry briefly before deciding there's no arrow.
- **Main quests can be told from side quests.** The quest data carries a main-line flag. It was set on every main quest seen, and not on side quests or on "Quest Finder".
- **Quest, goal and enemy names are language keys,** not display text. The game's locale files turn them into the words a player sees.
- **Battle readings can lie.** "Not in battle" or "ended" sometimes read mid-battle, because a failed duel lookup can be reported as ended. Confirm a battle's end with two readings a second apart.
- **Enemies only show their details close by.** Distant entities are placeholders without NPC data. Classify them once they load in full.
- **Entity addresses get reused,** especially after zone changes. A stale classification once made a friendly NPC look like a ghost at the wizard's feet, and the wizard stepped away from it forever. Key what you know about an entity by more than its address, and clear it on each zone change.
- **A stats read can be another player's.** Beside another player's fight, the player-stats read gave a maximum health of 1,487 for several minutes, while the wizard's own was 1,226. The wizard's own battle member and the client log's health-globe lines had it right, and a fresh hook read correctly again. Check a surprising number against a second source before acting on it.
- **Tools that hook the game share its hooks.** A second reader attached to check something during a run, and when it exited it removed every hook, the running bot's included. While the bot plays, check things through its own log and the client's log. Attach other tools only while it's stopped.

## Moving

- **Keys can go to the game window by message,** so the window doesn't need focus. Make sure every key-down gets its key-up, even when the action is cancelled.
- **Q is not strafe.** It opens the quest book, which then hides the NPC interact prompt until it's closed. Keep an explicit list of allowed keys, and refuse everything else.
- **Turning has to be learned.** Measure which way a turn key turns and how fast before relying on it (about 2.2 to 2.7 rad/s here). Walking speed was about 600 units/s, and much faster on a mount.
- **Stop-and-go walking walks into enemies.** Blind steps with scans in between were the problem, not slow sensing: an enemy scan took about 31 ms. Holding forward continuously under a fast watcher fixed it, with 5,054 units in 9 seconds and no unwanted battles.
- **A watcher that fights the planner stands still.** Stopping for every enemy near the path, including ones the route already planned around, produced 99 stops in a row. Stop only for new enemies, or ones that came closer than the plan allowed.
- **Bound every search.** A* over a large interior's walk grid once expanded 40,000 nodes. Cap the nodes and the time, then fall back to the next method.
- **Standing still to plan gets the wizard caught.** In Cyclops Lane each turn stood still 4 to 6 seconds before its route was ready, and patrols walked into it. One check comparing every sample with every waypoint took 99% of that time; indexing the waypoints spatially brought a route under 0.25 s. Profile before guessing.
- **Walk data can be wrong.** A straight line the collision data called clear was blocked in the game, and every route method aimed at the same spot until the run gave up. Record where the character actually gets blocked, and plan around those points from then on.
- **Some ramps and stairs are missing from the collision data.** A raised terrace then reads as its own walkable piece with no way onto it, though players walk up. The game's nav graph links the levels, but its waypoints can be far apart. Walk by the collision data to the foot of the ramp, climb the nav graph's short legs to the top, then plan again from there. This applies to every walk, whatever its target.
- **There is no safe-zone flag.** Patrol paths exist for friendly NPCs too (the Commons and Olde Town have them), and an enemy tower had none. Whether a place is safe is told by the enemies loaded right now, not by the zone files.
- **A path's name doesn't say what walks it; the spawn data does.** Many street paths are numbered or misspelt, and most of those turned out to be wisp or reagent paths. Judged by name, 80% of one street's walkable ground was priced as near an enemy path; judged by what spawns on each path, 52%. Routes planned with the corrected map spent half as much of their length near enemy paths, or less, for routes up to 17% longer. Sightings from earlier runs hadn't cleared the wisp paths, because enemies walking beside them counted for them.
- **Read every node of a path, in the order listed.** Paths list node ids out of order (15, 14, 16, 13, ...). Read as runs of increasing ids, two of one street's enemy paths had no nodes, and routes walked that street as if nothing patrolled it. Single-node bosses went missing the same way.
- **Sidewalks are safer, not safe.** The collision meshes are named after their textures, so street and sidewalk can be told apart, and most enemy path nodes lie on the street. But 4 to 16% lie on sidewalks, and in several streets a quarter to half of the sidewalk is within a short walk of an enemy path. Wisp paths are no guide to sidewalks either: in some zones most of their nodes are on the street. Keep avoiding live enemies wherever the character walks, and check a proposed safe zone against the game files before trusting it.
- **Walk data is flat.** The walk grid and the nav graph have no floors. A quest NPC stood on a balcony 550 units above the wizard and 81 away on the map, and the talk turn crept closer on the ground floor for four minutes before the run gave up. Compare heights before closing in. When the target is on another level, look for that level's way up (a stair, a door, a teleport), or set the goal aside rather than creeping.
- **Other players' fights are obstacles that move on.** A target enemy stood next to another player's duel, and every approach was refused because it would come within the duel's reach. Each refusal returned at once, and eleven turns in one second used up every fallback. Back out of the duel's reach and wait for it to end, and count the wait as waiting, not as a failure.

## Steering

From walks with a mount, with crowds of patrols, and with the operator's own work on steering (2026-10-28 and 29):

- **Steer in a closed loop.** Read position and heading on every tick, and choose the keys from what is read. Timed taps run blind: while a tap sleeps, a walking or mounted character covers 50 to 100 units it doesn't see.
- **Corner by looking ahead.** Aim at a point that slides ahead along the path, its distance growing with the speed. Hold forward through bends with a turn key at the same time, instead of stopping and turning in place at every corner.
- **Brake from the measured speed, and size arrival to it.** Measure speed from the change in position, not from a constant: a mount, a slow or a fast zone changes it. Release forward a little before the target, by that speed. Never ask for an arrival circle smaller than one check can carry the character past. A wisp walk aiming within 10 units, with a broom mount worn, went back and forth around the wisp for three full minutes.
- **Mind the turning circle.** When a close target sits inside the character's minimum turning circle (speed divided by turn rate), holding forward and a turn key only orbits it. Drop forward for a moment until the target is outside the circle, then go on.
- **Chase moving targets live.** A wisp or an enemy walked to by a snapshot of its position is walked to where it used to be. Re-read its position as you go, lead it a little by its velocity, and end the chase when it disappears.
- **Keep an oscillation guard as a backstop.** When the target keeps turning up behind the character on the way in, it's as near as it will get. Accept arrival, or give up in seconds, not minutes.
- **Read enemy velocity from a short, recent window,** and from their facing when they turn. A long window smears a patrol's turn into a wrong velocity for most of a second.
- **Crowded streets need a nearer horizon.** Projecting ten or more patrolling enemies several seconds ahead can seal every route through a narrow street. When nothing gets through, plan around the nearby enemies only, start moving, and let the fast local steering deal with the far ones as they come.
- **Keep perception and planning off the steering loop.** Position and heading are cheap to read; the entity list, the UI tree and route searches are not. Run them beside the steering so it never waits on them, and give a worker thread its own copy of the data it plans from.
- **A 100 Hz steering loop is cheap.** It used 1 to 2% of one CPU core.

## Quests and dialogs

- **The next main quest arrives by itself.** A follow-up dialog opens a few seconds after the quest-completing talk ends. Wait for it before moving on.
- **Offer pages have a DECLINE button,** and on them Space presses ACCEPT. Read the page before paging through it. Main-quest dialogs seen so far had no DECLINE.
- **Talk to the right NPC.** With several NPCs nearby, the interact key went to the wrong one. Walk close to the NPC the quest names, with the prompt showing, before pressing it.
- **NPCs behind counters can be talked to from farther away.** One stood in a booth the wizard couldn't walk around. The interact key worked from 266 units once the prompt showed and the nearest friendly NPC was the right one.
- **Doors differ.** A walk-in door changes zone a few seconds after the character walks in, so push in and wait. Towers and dungeons open only with the interact key once its prompt shows.
- **"Arrived" is not progress.** Counting an arrival where the character already stood as progress kept one run looping for 200 turns. Progress needs real movement or a change in state.
- **Side quests pay.** Quests the main story never points at (found through the journal's Quest Finder and the school professors) gave a few hundred XP each, against 10 to 50 for a street fight. Clear a world's side quests before leaving it.
- **The game counts late, and step by step.** A collect goal stayed open until about 10 s after the last pickup, and a bot checking at once logged every pickup as a miss. When one step of a quest finishes, the next often opens at the same moment, so the number of open goals doesn't change. Wait a few seconds, and judge a use by which goal closed (the game also reports XP for the step), not by how many are open.
- **An arrow at a door means the target is behind it,** whatever the goal type. A quest object's arrow pointed at the door to the next hall, where the object stood. Pressing interact there walked the character through, and the use was logged as failed, twice. When the arrow stands at a zone door, go through it.
- **Before leaving a world, retry what was set aside.** Quests set aside until the next level can still be waiting when a world's quest givers run out. The journal's Quest Finder then answers with a notice that there are no available quests in this world, and trying it again does nothing. Try the set-aside quests once more, dungeons first, before moving on.

## Goals without a quest arrow

- **The game files say where untracked targets are.** Things to collect and hidden spots to visit can show no quest arrow. The goal still names its zone, and the zone's files hold the targets: placed objects named by the goal's tags, trigger volumes named after the quest (walking into one counts the visit), and the zone's Explore object. Go to the goal's zone, then try the nearest untried spot from those sources. Don't try a spot that didn't move the goal on again, and park the quest when none is left. Triton Avenue's Cogs were found by tag, and 9 of 10 Smiths of "Find the Smiths" by trigger volume.
- **A goal's tag can sit in the template, not the name.** Six glowing fish a goal asked for carried no tag in their names, but the template file each was built from, in the game's data archive, did. Look in the templates before deciding a tag names nothing.

## The zone graph

- **The zone files don't say where street doors lead.** A zone's data names some interiors it opens onto, but street-to-street links and some hidden sub-zones are known only by walking them. Learn links as you walk: the spot where the character arrives from a zone is the door back to it. Use a hand-kept map where you have one, and the learned links where you don't.
- **Learn where travel lands with care.** Go Home pressed while standing in a house's walk-in door loaded the house first. The bot credited that zone change to Go Home, learned the house as the world's hub, and later chose Go Home over a faster Recall because it seemed to land at the goal. A house is never a hub, and an interior only links to zones in its own place.
- **A flee can move the character.** Fleeing a fight in an underwater street sent the wizard to the world's hub with no key pressed. The bot learned that as a door it had walked, and later walked again and again to a door that didn't exist. Learn a door only from a walk the character made, and forget one that fails twice.

## Fighting

- **Match cards by the game's spell type.** Matching on spell effects never matched, so the wizard passed every round. Reading the game's own spell type worked at once, as Deimos does.
- **Every spell costs mana, wand spells too:** a mana a pip. At level 8 the pool was 30, and a fight took 6 to 10.
- **Don't trust a library's button lookup blindly.** WizWalker's Pass and Flee clicked the Defeated window's buttons in this client, because that window always reads visible. The real ones are in the planning window's action buttons. A window's visible flag is its own and ignores its parents, and the action buttons carry a disabled flag while they can't be used.
- **A flee that doesn't take leaves the hand unusable.** The flee confirmation box opens under the planning window, not on top, and while unanswered no card click lands. No flee ended a battle in this run.
- **Unresisted attacks first.** Choose by expected damage after resistances, weaknesses, shields and traps, and prefer attacks the target takes in full, even small ones, over bigger resisted ones.
- **Traps go on before a big hit of their school,** and whenever the round would otherwise play nothing: they cost no pips.
- **Estimate danger from the hits seen.** A flat damage-per-pip guess made the wizard pass rounds at 94% health to save pips for a heal. Learn each enemy kind's biggest hit and use that.
- **Read the turn order.** When the enemies act first, their next hits land before the wizard's next card, so a heal has to come a round earlier, and the danger estimate has to cover two of their rounds, not one. The client log shows who resolves first. Two Wailing Wraiths that acted first took the wizard from full health to 0 while it waited one round too long to heal.
- **Count damage over time.** A burn ticks before the next cast, and once took the last health. Add the ticks due before your next turn to the danger estimate.
- **Know when a fight is lost on heals, and leave.** Four stronger enemies joined one by one and won while the wizard healed most rounds. When most recent rounds went on heals, health stays low and the enemies' health isn't falling, flee: a flee keeps what health is left, and a defeat costs a full recharge.
- **In danger with no heal to cast, a shield can beat an attack.** An attack that kills nothing takes nothing off the next hits, while a shield halves one, and the next draw may bring the heal. A close fight went down to 15% of health with attacks cast at 35% and 21% while no heal was castable. One order to try in danger is heal, stun, sure kill, shield, then attack. (Not yet seen in play.)
- **A miss is not immunity.** A spell that left its target's health unchanged once most likely fizzled: an 80% accurate spell fizzles one cast in five. One fizzle barred Snow Serpent for the rest of a fight, and the wizard chipped with one-pip spells for four rounds with three pips held. The fight took 12 rounds and 43% of its health. Set a card aside only after it fails again on the same target.
- **Pips held beyond what a card needs are worth nothing until spent.** With a trap of its school waiting, or with three or more pips unspent, play the bigger hit over a one-pip spell that only roughly ties it. A fight that drags on costs more health than the pips saved.
- **Discard cards that won't help soon.** Right-clicking a card in hand during your own planning discards it, and the hand refills from the deck next round. A stun when nothing needs stunning, an attack every enemy resists, or a second heal while health is safe, is a slot for a better draw. Keep the best castable attack, a heal the next two enemy turns may call for, traps, and anything used up when cast. Discard one card at a time and read the hand again after each, because the hand closes up: a second click by position took the wrong card. Keep enough in the deck to finish the fight, and log each discard's reason.

## After a battle

- **Wait for the signal, not for a time.** Flat sleeps after each battle (to confirm the end, for the duel circle, after Mark Location) plus a big log read made the gap from a battle's end to the first move 6 s at the median and often 9 to 24 s. The operator noticed. Poll for what you're waiting for, with a short cap, and do diagnostics off the critical path: the gap fell to under 4 s.
- **Time it.** Log a timeline of each step from a battle's end to the first move, so the gap is measured, not guessed.

## Health and refills

- **Health and mana come back by themselves only in zones without enemies.** In the Commons, mana came back at about 2 a minute and health at about 2 a second. They don't come back in streets with enemies, in towers or inside instances (90 s standing gave nothing). Wisps help: about +3 to +6 mana each, and a health wisp gave about 200 of 801.
- **Wisps near other players are usually taken.** In the Commons about half the wisp walks gave nothing. Keep looking while regenerating, but don't count on wisps. The spawn data names the paths wisps spawn on, so a hunt can walk those instead of searching (not yet tried in play).
- **Check that waiting gives something back.** A refill walk wandered through a door into a small room off the Commons, where standing gave nothing. The bot walked to the spot it stood on and stood for 90 seconds, again and again, for three minutes. If health doesn't rise while standing, go to the hub.
- **Count what fights cost.** In Triton's underwater street each fight cost 40 to 65% of health and gave 30 to 45 XP, and every one meant a refill trip. After a fight that costs a third of health or more, refill before going on, and remember which zones are heavy.
- **Weigh a refill trip against the goal.** A trip costs mana and minutes. When the goal is close and safe, push on; when health is just short of the refill line in a quiet zone, walk on.
- **Heals left in hand at a fight's end are wasted.** In 32 of 38 wins the heal stayed in hand, and nearly every costly fight was followed by a trip home. Top up before the last kill rather than waiting for a sure win, and fight on with heals in the deck above about 60% of health: a refill trip after every costly fight was slower.
- **Go into instances refilled.** A door can open on a tower or an instance that can't be left partway, and inside, nothing comes back. Learn which doors open on instances, and refill before those. One instance entered at 45% health lost its next fight.

## Travel and marks

- **The game's own travel buttons beat walking.** Mark Location, Recall Location, Go Home (to the world's hub, where health and mana come back) and a dungeon's return button cut the way back after a refill or a defeat to seconds. Treat them as route steps with costs (time, mana, cooldowns), and compare them with walking.
- **Never mark where a fight just happened.** Patrols cross there, so the Recall back lands in the next fight: four of five Recalls did, one night. Mark at the goal's door, or at a spot where earlier Recalls landed with no fight, or walk back instead.
- **A mark can trap the character.** One set where a boss fight ended put every Recall back on an island with no way off. If no route leaves a mark, forget it and never mark there again.
- **Read the Recall timer.** When Recall is cooling down and is still the quickest way, wait out its timer instead of walking off.
- **Mark Location can fail silently.** It failed four times with no message; log what the buttons showed each time.

## Dungeons

- **What is a dungeon isn't always in its name.** Interiors named with "_T" and a number are instances, but Sunken City is named like a street, and Triton Avenue's underwater zone opens like a door yet is a street. A zone behind the game's dungeon-entry box is a dungeon, and so are the zones under it.
- **A dungeon keeps its progress for 30 minutes after leaving.** Its entry box says so. Leave by Go Home, refill, and come back with the dungeon's return button on the HUD within the timer, with a margin. Recall doesn't take the character back in. Check on landing that the enemies killed stayed down.
- **A dungeon's side rooms are the same dungeon.** A side room can have its own zone name, filed apart from the dungeon's main zone. Compare zones as "same dungeon or not", not as equal names. Otherwise a defeat or a flee in a side room doesn't match the goal's zone, the way back is dropped, and the run walks into a fresh instance.
- **Walking back in through the door can start a new instance.** All its progress is gone. After any exit from a dungeon (defeat, flee or a refill trip), use the return button while its timer runs, and keep the record of the exit across restarts.
- **A flee's move to the hub comes after the battle ends.** A zone read right at the end still shows the dungeon. Record a flee from a dungeon as leaving it whatever the zone reads, and drop the record if the character turns out to be still inside.
- **Towers lose their progress when left partway.** Refill in place in a tower.
- **Count loops from the last travel button,** not from the goal's start, so a long walk with refill trips isn't taken for a door loop.

## Stopping

- **A stopped character among enemies can be pulled into a fight it can't play.** Stopped in Triton's underwater street with an enemy about 400 units away, the wizard was in a battle within minutes, passed every round with no one at the keys, and was defeated. Stop where no enemy walks.
- **Stop at a turn's boundary.** Two stops written right after the bot approached an enemy left a fight unplayed. Read what the bot is doing first, then signal the stop.

## The connection

- **The server connection can drop mid-battle.** The client froze in the battle's execution phase for minutes, and nothing in memory said why. The client's own log did. Read it when a battle stalls or a zone takes over a minute to load, and leave logging back in to the operator.

## Popups

- **Some windows hold the keyboard.** The Endorse Wizard window, after a shared battle, made the walking keys do nothing. If a turn key changes nothing while the character should be free to move, look for an open window before anything else.
- **Single-button game boxes can open over a battle.** The "Quest Friend Finder" tip did, and took every click for three minutes. A game box whose only button is OK can be closed with it; a box from another player can't.

## Gear and mounts

- **Wear a mount when there is one.** A rented mount can be worn as soon as it arrives if none is worn. Mounts drop off indoors and come back outside, and the game asks before starting a rental's timer.
- **Gear can be compared by its stats** (health, mana, resistances, then the school's damage and accuracy) once the item data is read. Only equip in a zone without enemies, because the spellbook stays open a few seconds per item.

## Opportunities

- **Watch for what could speed progress, and record it.** An MMO is full of features, tips and patterns a bot doesn't need yet. The operator: "there is a lot going on in mmorpgs, you are going to need to decide when to add something to your memory bank ... See if you can reconize these patterns". Watch the game's text (tip boxes, NPC pages that name a feature), numbers you measure (XP per activity, fight cost, wisp success), and HUD buttons never pressed. Keep each with how often it was seen, and gate anything that involves other players, gold or crowns behind the operator.
- **Quests pay, street fights don't.** One hand-in gave 270 to 315 XP, about nine fights' worth in the underwater street, without their health cost. Avoid fights on the way to goals rather than farm them.
- **The game offers help from other players.** The Quest Friend Finder's tip says its HUD button asks friendly players in the world to join, and those who accept are grouped and teleported to you. It could help with bosses or zones too hard alone, but it brings in other players, so it waits for the operator.

## Screenshots

- **Plain window capture doesn't work for this client.** GDI capture returns a blank client area for its DirectX view, and an F12 sent as a window message saved nothing. Memory reads and the UI window tree answered every question so far.
