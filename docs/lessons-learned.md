# Lessons learned

These come from one character's first unattended play, level 1 to level 5 in Wizard City, on 2026-10-26. The code was a set of prototype scripts at the time; this framework is those scripts restructured. Each lesson gives what happened, what it taught, and where the fix lives now.

## Reading the game

- **Hooks are patches to the game.** A run stopped with Ctrl+C while its output was piped through another program died before cleanup. Every later hook attempt failed with `PatternFailed` until the game was restarted. Now `session.attached()` always removes hooks, and the STOP file is the way to stop a run.
- **Install only what you read.** The player, player stats, client and root-window hooks are enough for state, and the quest hook for the arrow. `activate_all_hooks` would add the movement/teleport hook, which nothing here needs.
- **The quest arrow lags behind its hook.** Right after hooking, or while no quest is active, reading it fails with `AddressOutOfRange`. `quests.read_quest_arrow` retries for a few seconds.
- **`QuestData.mainline()` separates main quests from side quests.** It was true for every main quest seen and false for "Quest Finder" and side quests.
- **Quest and goal names are language keys** (`QuestTitle_...`, `WizardQuestGoals_TalkNPC`), not display text.
- **Battle readings can lie.** `in_battle()` and `duel_phase()` sometimes read "not in battle" or `ended` mid-battle, because a failed duel lookup is reported as `ended`. The end of a battle is now confirmed with two readings 1 s apart.
- **Enemies only show up close by.** Distant entities are "StandIn" placeholders without NPC data. The Deimos test (the `NPCBehavior` flag at offset 288) works once they load in full.
- **Entity addresses are reused,** notably after zone changes. A stale classification once made a friendly position look like a ghost at the wizard's feet, causing endless step-aways. Classifications are now keyed by address and name, and cleared per zone.

## Moving

- **Keys go to the window by message,** so the game window does not need focus. WizWalker's `send_key` always sends the key-up, even when cancelled.
- **Q is not strafe.** It opened the quest book, which hid the NPC prompt until it was closed. Q and E are not allowed keys.
- **Turning is learned.** A first A tap measures which way A turns and how fast (about 2.2 to 2.7 rad/s), and later turns are sized from that. Walking speed is about 600 units/s.
- **Stop-and-go walking walked into mobs.** Blind 0.6 s steps with scans in between were the problem; sensing was fine (an enemy scan takes about 31 ms). Holding W continuously under a 20 Hz watcher fixed it: 5,054 units in 9.1 s with no unwanted battles.
- **A watcher that fights the planner stands still.** Stopping for every enemy near the path, including ones the route had already planned around, produced 99 immobile stops in a row. `progress.PlannedRoute` now stops only for new enemies or ones that came closer.
- **Unbounded planning stalls.** A* over the walk grid in a large interior expanded up to 40,000 nodes. Planning now gives up after 8,000 nodes or 2 s and falls back to the next method.
- **Walk data:** in Unicorn Way, zone.nav had 1,079 waypoints on a 480-unit grid over walkable ground. Deimos's collision walk grid matched live ground heights to within 0.1 units and planned in 0.1 to 0.4 s.
- **Standing still while planning gets the wizard caught.** In Cyclops Lane each turn stood still 4 to 6 seconds before its route was ready, and the patrolling Trolls and Cyclopes walked into it. Profiling put 99% of a nav route's time in one check comparing every shortcut sample with all 1,141 waypoints; bucketing the waypoints made a route take under 0.25 s.
- **Patrol paths are not enemy paths.** The Commons, Ravenwood, the Shopping District and Olde Town have patrol paths for their friendly NPCs, and General Akilles' tower has none. Whether a place is safe is told by the enemies loaded, not by the zone files.
- **Walk data can be wrong.** In the Commons, a straight line that Deimos's walk grid and `straight_path_walkable` both call clear was blocked in the game. Every route method aimed at the same spot until the run gave up. The wizard now records where it gets blocked and plans around those points (found by the framework's first smoke run, 2026-10-26).
- **There is no safe-zone flag** in the collision data. Spawn and patrol data exist (spawnData.xml, pathData.xml) but need extra tools to decode. Instead, routes cost more near the enemies currently seen, and merged legs keep clear of them.

## Quests and dialogs

- **The next main quest arrives by itself.** A follow-up dialog opens a few seconds after the quest-completing talk ends. The dialog code now waits up to 10 s for follow-ups.
- **Offer pages have DECLINE.** On them, Space presses ACCEPT. Side-quest offers said so in their text, and are now declined. Main-quest dialogs seen so far had no DECLINE button.
- **Talk to the right NPC.** With several NPCs nearby, X went to the wrong one. The wizard now walks within 80 units of the arrow's NPC with the prompt showing.
- **Counters.** One NPC stood in a booth the wizard could not walk around. X is now accepted when the prompt shows and the nearest friendly NPC is the one at the arrow; it worked from 266 units away.
- **Doors.** A waypoint goal still open with the wizard at its arrow is a door. The zone change starts a few seconds after walking in, so the loop pushes in and waits up to 15 s. Towers and dungeons open only with X once the interact prompt shows; walking into them does nothing.
- **"Arrived" is not progress.** Counting arrival where the wizard already stood as progress kept one run looping for 200 turns. Progress now needs real movement or a state change.

## Fighting

- **Match cards by spell type.** Matching on spell effects never matched, so the wizard passed every round. Deimos's approach, reading the game's own spell type, worked at once.
- **Clicking needs two hooks:** the mouseless cursor hook, and the render-context hook for UI scale.
- **A defeat came from planning too early.** The route was planned before nearby enemies had loaded, and the wizard waited in place as they arrived. The loop now re-plans when threats appear, steps away from close enemies, rests below 65% health, and stops on any defeat.
- **Every spell costs mana, wand spells too.** Each pip costs a mana: the starter wand's Scarab, Imp and Frost Beetle each took 1. The pool is 30 at level 8 and a Warhorn fight took 6 to 10. Mana does not come back by standing (it stayed 0 for minutes in a tower); it comes from mana wisps (+3 to +6 each), potions and level-ups. A defeat sends the wizard to the Commons with some back. Health does not come back by standing either (263 stayed 263 for over two minutes); a health wisp gave about 200 of 801. After a lost connection, logging back in put the wizard straight back into the battle it was in, with 1 health.
- **WizWalker's Pass and Flee clicked the wrong buttons in this client.** `pass_button` and `flee_button` click the `DoneWindow`'s Defeated buttons whenever `DoneWindow` says it is visible, and here it always does. The real ones are `PlanningPhaseSubWindow/SpellSelection/ActionButtons/Focus` (Pass) and `.../Flee`.
- **A flee that does not take leaves the hand unusable.** After the real Flee click, the battle went on, and the planning window's "Waiting for Other Players..." panel stayed up, into the next battle too; no card click landed until its Change button was clicked. No flee has ended a battle yet.
- **A window's visible flag is its own.** `is_visible()` does not look at parents: hidden battle windows still say visible outside battle. WizWalker's `WindowFlags.disabled` (bit 31) is set on the action buttons while they cannot be used.
- **Results:** after the spell-type fix, every automated battle (about 12) was won, most in 1 or 2 rounds, with starter cards against Skeletal Pirates, Lost Souls and Dark Fairies.

## Health

- **Health regenerates outdoors** (about 1.6 HP/s in the Commons) **but not in every interior**, nor on Triton Avenue or Cyclops Lane. Resting in one froze the run. Resting was later dropped altogether as too slow: health comes from potions, wisps, in-battle heals and level-ups.

## The connection

- **The game can drop its server connection mid-battle.** At 02:06 on 2026-10-27 the client logged "AppCloseConnection() called", reconnected, and was closed again. It froze in the battle's execution phase with the duel unchanged for minutes, and nothing in memory said why. The client's own log (`Bin/WizardClient.log`) did; the framework now reads it when a battle stalls. Logging back in is the operator's.

## Popups

- **The Endorse Wizard window held the keyboard** after a game restart: A, D and W did nothing. The loop now stops with that diagnosis (`movement.KeysIgnored`) when the first A tap changes nothing while it should be free to move. It answers the window before each turn: its buttons are `MainLayout/FriendlyWindow/FriendlyButton`, `KnowledgeableWindow/KnowledgeableButton` (shown as "Savvy") and `HelpfulWindow/HelpfulButton`, and `NameText` holds the other player's name.

## Screenshots

- **They do not work yet, and are not needed often.** GDI `PrintWindow` returns a blank client area for this DirectX client, and an F12 sent as a window message saved nothing. Memory reads and the UI window tree answered every question so far.
