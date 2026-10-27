# Changelog

Every change, enhancement or addition is listed with its rationale, so later contributors know why the framework is the way it is. Say what was verified in the game and what was not.

## Unreleased

### Added

- **The cheapest attack that surely finishes the target.** When an attack in hand surely finishes the first enemy (at least 60 damage per pip, `policy.SURE_DAMAGE_PER_PIP`, after its shields, wards, traps and resistances), the policy plays the one with the fewest pips. Otherwise it still plays the attack expected to do the most. A Warhorn with 15 health left took a 2-pip Snow Serpent where a 1-pip Frost Beetle would do, and mana, a pip each, is the scarcest thing at this level.

- **Stuns, and the enemy closest to defeat first.**
  - **What:** each card now carries its spell effects from the game (`Card.effects`, such as "stun"), and each enemy whether a stun or a stun block hangs on it (`Combatant.stunnable`). When a stronger attack in hand needs one pip more than the wizard has, `SpellTypePolicy` casts a stun on the enemy with the most health that can be stunned, instead of a weak 1-pip attack (`stun_while_saving_a_pip`). Freeze costs no pips, so the next round has the pip for the stronger attack. A stun also replaces the pass while saving pips for a heal. Attacks go to the enemy with the least health, and the cheapest attack that surely finishes any enemy comes first. The round event names the enemy a card was cast on, and marks enemies that cannot be stunned.
  - **Why:** General Akilles (470) and his Cyclops Legionnaire (235) took the wizard from 801 health to 0 in six rounds, 100 to 200 a round. The hand held two Freezes (Ice, 0 pips, "Stun target 1 round" in the game's spell data) every round, and the policy never played them, because it knew only damage and heal cards. Every attack went to Akilles while the Cyclops kept hitting. The wizard cast 1-pip wand spells (about 55 to 95) round after round, so its pips never built up to the 2-pip Snow Serpent (about 175). Over two rounds, a stun and then a Snow Serpent do about 175 against two wand hits' 140, and the stunned enemy misses its turn.
  - **Not verified yet:** in the game, including whether stunned enemies get stun blocks in this fight.

- **Healing before a saved-up hit.**
  - **What:** each enemy's pips are read in battle (`Combatant.pips`, a power pip counting two) and shown in the round event. The wizard heals not only below 40% health but also when its health is no more than what the enemies could deal next round if each spent all its pips, at 100 damage a pip (`policy.ENEMY_DAMAGE_PER_PIP`, `within_reach_of_a_big_hit`). With no heal castable then, it stuns the enemy holding the most pips. Stuns in general now go to the enemy holding the most pips, the one whose next spell is biggest, and to the one with the most health on a tie.
  - **Why:** in the rematch, stuns and attacks on the Cyclops first worked: the Cyclops fell in round 3, and General Akilles was down to 145 of 470. Then, at 357 of 801 health (45%), the wizard attacked with a 245 heal in hand, and Akilles took all of it in one round, where his hits had been 100 to 140. Stunned in the first round, he had saved his pips.
  - **Not verified yet:** in the game; the 100 a pip is an estimate from that hit.

- **Mana topped up in a zone without enemies.**
  - **What:** when mana is short for a quest fight and no safe mana wisp is in sight, the wizard leaves a street through its exit volume, which leads back toward the hub (from Cyclops Lane, to Olde Town), as it already left interiors. In a zone where no enemy has been met, it searches the zone once for mana wisps, then stands still (`QuestLoop.wait_for_mana_turn`, up to 90 seconds a turn, so battles, popups and the STOP file are still checked) until mana is at 90% (`progress.TOP_UP_MANA_FRACTION`), and goes back to the quest. Health alone is still never waited for. Zones where enemies were met, in a battle or nearby, are kept in the knowledge file (`Knowledge.zones_with_enemies`), so a run that starts in Cyclops Lane, or meets no enemy at its entrance, does not take it for a place to wait.
  - **Why:** the operator: "You can wait in olde town or look for wisps". In Cyclops Lane, mana wisps give 3 to 6, but reaching them through nine to thirteen enemies led into fights costing 5 to 10 mana each: five minutes of searching netted -9 mana, and both of the morning's defeats came at 1 mana. In zones without enemies mana comes back about 2 a minute (0 to 30 within 17 idle minutes in the Commons) and health about 2.4 a second; the hub zones also have mana wisps with no fights around them. In Cyclops Lane neither came back.
  - **Topping up starts with the first wisp.** The refill to 90% is set as soon as a mana refill begins in a zone without enemies. Set only once the zone's search began, it missed the first wisp in Olde Town, which brought mana from 11 to 14, over the 12 a fight needs, and the wizard went straight back to Cyclops Lane.
  - **Exits are walked into from anywhere inside their radius.** The walk aims for the exit volume's middle, and the door step starts anywhere within the volume's radius. In the first run the wizard reached the edge of Cyclops Lane's exit, 336 units across, which counted as arrived, while the door step waited for 150 units from the middle; it stood there until the run stopped for turns without progress.
  - **Not verified yet:** in the game. The out-of-battle mana reading once seemed to stay at 9 for six minutes before a battle read 24, so a wait that sees no gain four times in a row ends the run rather than waiting on.

- **No fight the quest asks for without the health for it.**
  - **What:** a bounty goal, and the walk toward its zone, also need 60% of the wizard's max health (`progress.ENGAGE_HEALTH_FRACTION`). `progress.short_for_a_fight` names what is short, health before mana, and `refill_turn` (formerly `mana_turn`) fetches that kind of wisp the same way mana was fetched: the nearest safe one in sight, else out of an interior through its exit, else exploring the street. In a zone where no enemy has shown up during the run, such as the Commons, it goes on toward the quest instead, since wisps come with the enemies (`RunRecord.zones_with_enemies`).
  - **Why:** after the game server closed the connection mid-battle, the operator logged back in and the game put the wizard straight back into that battle with 1 health. It lost in a round and woke in the Commons with 1 of 801 health, and the next goal was General Akilles and his Cyclops, which beat the wizard from full health the night before. Only mana was checked before a quest fight. Won fights at level 8 cost up to 435 health of 717, so 60% leaves a margin for one. Health wisps gave about 200 each. In the streets health did not come back by itself (402 stayed 402 through a minute of walking in Cyclops Lane); in the Commons it rose from 1 to 625 in the four minutes after the defeat: zones without enemies give health back, about 2.4 a second. Resting for health is not used, as the operator asked.
  - **Not verified yet:** in the game.

- **No fight the quest asks for without the mana for it.**
  - **What:** a bounty goal, and the walk toward its zone, need 40% of the wizard's mana (`progress.ENGAGE_MANA_FRACTION`). Below that, `mana_turn` fetches the nearest safe mana wisp in the zone, however far. In an interior with none in sight, such as General Akilles' tower, it walks out through the interior's exit volume (the one whose name says "Exit") to the street's wisps. In a street it explores instead, walking to the nearest part not yet looked at and stopping when an untried mana wisp loads: wisps are spawned, not placed in the zone files, and load only nearby, so a first version saw none on arriving in Cyclops Lane and headed for the lane's own exit. A wisp that gave nothing counts again after 3 minutes (`WISP_RESPAWN_SECONDS`), since used-up wisps come back, so the wizard can go round a zone's wisps. Out of battle, low mana (below 20%) now comes before middling health when choosing a wisp, and a mana wisp counts in any direction.
  - **Why:** every spell costs a mana per pip, wand spells too: the round log shows Scarab, Imp and Frost Beetle from the starter wand each taking 1 mana. The pool is 30 at level 8, and a Warhorn fight took 6 to 10. With 1 mana the wizard walked into General Akilles and his Cyclops, could not flee, and was defeated.
  - **Mana does not come back in the streets or the tower.** A first version waited for it at the zone's entrance; in the tower it stayed at 0 for minutes. It does come back in zones without enemies (see "Mana topped up in a zone without enemies"). Health is never waited for, as the operator asked.
  - **Not verified yet:** leaving an interior for mana, and the rounds of the street's wisps, in the game.

- **Runs end in a zone without enemies.**
  - **What:** the target level and the time, turn and battle limits are now `LimitReached`, a planned end. At one, the run logs it and plays on, for up to 15 minutes (`loop.FINISH_SAFELY_MINUTES`), until it is out of battle with no enemy loaded nearby (`QuestLoop.safe_here`, which the gear turn uses too; enemies are recognised up to about 4,000 units away). Then it stops, saying so. The STOP file and the stops that mean something is wrong still stop at once.
  - **Why:** the operator: "ur in a fight because you didnt go to a safe area". A run stopped in Cyclops Lane left the wizard standing among the enemies, and one walked into it. The level-10 stop would have ended the same way wherever the last fight happened.
  - **Not verified yet:** a planned end in the game.

- **Wearing the best gear, opt-in (`--wear-gear`).**
  - **What:** `equipment.py` reads the worn and backpack items from memory, with each one's slot, equip effects and equip requirements, plus the wizard's school and real level. `gear.py` turns each canonical stat effect into a stat, scores it, and picks for each slot (hat, robe, shoes, athame, amulet, ring) the best item the wizard surely may wear. The loop equips upgrades through the spellbook's Inventory page, only with no enemy loaded nearby. It checks again after a level-up or new loot. Each item equipped is logged with its stats, then the change in max health and mana. Wands, decks, pets and mounts are left alone, and a requirement it does not understand counts as unmet.
  - **What counts as best:** max health first, the buffer that saves heal rounds and defeats; max mana at half weight, since every school spell costs it; then resistance to every school; resistance to one school at a quarter weight; then the wizard's own school's damage and accuracy. Stats of other schools count for nothing.
  - **Why:** the operator noticed the wizard had loot it could wear and said to choose the stats to maximise. At level 8 it wore only the Starter Deck and the Wand of the Seven Schools, with 16 wearable items in the backpack. Equipped by hand with the same rules, max health went from 717 to 801. The operator then asked for the choice and the equipping to be automatic, in safe zones only.
  - **How values are known:** the stat tables were not found in the installed files, so values come from each effect's lookup index as measured in the game: a flat stat gives index + 1, a percentage index - 99. Only health (three items) and resistance (one) were measured.
  - **Not verified yet:** an equip by the loop itself. The reads and the clicks were checked by hand at level 8.

- **Fleeing a battle when out of mana.**
  - **What:** with less than 2 mana (`policy.FLEE_BELOW_MANA`), `SpellTypePolicy` returns the new `Flee` choice, and the battle code clicks the battle's Flee button (WizWalker's `CombatHandler.flee_button`). The battle event says "fled", which counts as neither a win nor a defeat. A mana wisp then counts in any direction, not only on the way.
  - **Why:** the operator's rule, "if no mana you have to flee". Below 2 mana the wizard cannot cast its 2-pip attack and has at most one 1-pip spell left. With 0 mana and no free wand spell in hand, it passed four rounds and was defeated by a Cyclops Legionnaire it could not hurt.
  - **Not verified yet:** a flee in the game.

- **The hand in each round's event.** Each round line now ends with the cards in hand and their pip costs ("hand: Frost Beetle x2 (1 pips), Snow Serpent (2 pips)"). After the wizard learned Snow Serpent and Volcanic Shield at the Ice school, the operator wanted to see whether new spells reach the deck by themselves before deck editing is built. The cast alone does not show it, because the policy may hold a card it does not pick.

- **Dialog text in the event log.** Each "dialog" event now carries the conversation's text, one page per line, with the game's markup removed (up to 4,000 characters). The report still keeps page lengths only. The operator suggested reading the dialog for context: it says where the quest goes next ("Go see Professor Drake in the Myth School"), which neither the goal data nor the quest arrow always does. The text can include the wizard's own name; the event log stays in the ignored `runtime/` folder.

- **Side quests, opt-in (`--side-quests`).**
  - **What:** `policy.TakeAllQuests` accepts every quest offer, side quests included, and the loop plays whichever quest the game has active instead of stopping at a side quest. In an NPC's services menu with no quest active, it takes the approved titles first, then the first quest listed. The event log marks side quests ("(side quest)"). Before the main quest leaves the world, the run still stops, and now lists the open side quests from the journal. The default stays main quests only.
  - **Why:** the operator's rules during the level-10 runs: "you can take all side quests as you see them now", and "main quests are priority, but side quests need to be completed before moving on to the next world if possible". The run had just stopped in the Headmaster's house at a quest offer the main-quests-only policy could not classify.
  - **Not done yet:** choosing the active quest. That takes the quest book, which the framework does not open, so when the game makes a newly accepted side quest active, the wizard plays it before returning to the main quest. Doing the remaining side quests at the world boundary is left to the operator for the same reason.
  - **Not verified yet:** a side quest played in the game.
- **Placed objects are obstacles.**
  - **What:** when Deimos's model reader is available, the footprints of a zone's placed objects (tents, trees, crates: `entity_collision.build_zone_static_shapes`) are taken out of the walkable area along with the collision walls. On Cyclops Lane that is 25 footprints; a fairground tent's centre is no longer walkable, and the collision route to the quest NPC takes 7 legs. The planner status names the count. The reader needs `katsuba` 0.4 (0.6 removed an API it uses), `wiztype`, and Deimos's `kinif` Rust extension, which has no published wheel; the README shows how to build it with the GNU Rust toolchain and `maturin`. The first time, `wiztype` reads a type list from the running client (read-only, about 20 seconds) and caches it per game version. Without these packages, nothing changes.
  - **Why:** the operator saw the wizard walk into Cyclops Lane's fairground tents, and asked for the tools to be installed. `collision.bcd` leaves placed objects out. The nav-graph-first fallback works around them; this removes the cause.

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

- **Walk events say why a route method failed**, as in "nav: failed (turn failed: facing did not converge)". Several fights with enemies the quest did not ask for began right after a "nav: failed", and the event did not say why.

- **Stronger attacks first.** The default policy now ranks attacks by pip cost times what lands (the target's wards, traps and resistances) times accuracy. At these levels damage grows with pips: Frost Beetle (1 pip) does about 85, Snow Serpent (2 pips) about 175. With 2 pips and two Snow Serpents in hand, the wizard cast 1-pip wand spells instead, the first card in hand on a tie; one of them missed. The round log's new hand list showed it.

- **No resting.** The wizard no longer stands still to regain health, and no longer stops the run when health is low in a zone where it does not regenerate. Health comes from potions (if allowed), health wisps (sought below 65%), heals in battle and level-ups. `runtime/knowledge.json` no longer keeps zones without regeneration. The operator: "never use "resting" as a way to gain hp, it is not time efficient". A rest gains about 1.6 HP a second where health regenerates at all, and nothing on Triton Avenue, on Cyclops Lane or in most interiors; the last one cost 30 seconds for nothing before a battle interrupted it.

- **Cards are weighed by their accuracy too.** The default policy now ranks attacks by the share of damage that lands after wards, traps and resistances, times the card's accuracy (`card.accuracy()`, 70% for Storm's Thunder Snake, for example). On a Lumbering Troll, Thunder Snake fizzled twice in a row; a slightly weaker school that hits more often is the better play unless the enemy's weakness makes up for it.

- **Rerouting while walking.**
  - **What:** when an enemy's predicted course will come near the next stretch of the path, the watcher no longer ends the trip. It plans the next 2,500 units again from where the wizard is, around where enemies are going, within a quarter of a second, and joins the rest of the route. The wizard keeps walking: W stays held and the new legs replace the old ones. The trip ends, and the next turn plans everything again, only when no such way is found, or when a reroute less than 0.3 s earlier did not clear the threat. A duel near the path still ends the trip. The walk log counts reroutes ("collision: arrived after 3 reroutes").
  - **Why:** the operator wanted pathing that tracks enemies live, "aim bot" precise. Before, every threat on the path stopped the wizard: release W, end the trip, read the state and quest again, and plan the whole route anew. That takes a second or more each time, standing still, while the enemy keeps coming.

- **Mana wisps only when mana is low.** The wizard now walks to a mana wisp below 20% mana, not 50%. One evening it walked to five mana wisps, about 2,000 units each, between Olde Town and the Storm school, for no mana at all: used-up wisps still load as entities. A fresh one gave only +3 of 28. Health wisps are unchanged.

- **Routes and the watcher predict where enemies are going; a few seconds' grace after each battle.**
  - **What:** the loop keeps the last second and a half of each enemy's positions and turns them into a velocity (`motion.MotionTracker`). Routes now treat every enemy that is not a quest target as a no-go area 520 units wide, just outside the 450 at which the wizard steps away. The area sits where the enemy will be when the wizard reaches that part of the route, assumed to be no further than four seconds along its current course. So a route can pass behind an enemy walking away, and keeps clear of where one is heading. Enemies already that close to the wizard or to the destination are left out. While walking, the watcher stops the trip only if an enemy's course will bring it near the next stretch of the path (its closest approach), not merely because it stands near the path now. When enemies leave no route, the wizard waits four seconds for them to move, logged as "enemies leave no route". That counts toward the existing limit on waiting for threats (eight in a row), after which the run stops for the operator. Walks into teleporters and to wisps plan the same way. For six seconds after a battle, enemies are not avoided at all: routes may pass through them and the wizard does not step away.
  - **Why:** the operator found the pathfinding "still too reactive" and asked for "some predictive features". "Avoid enemies always" was enforced only by stepping away, and routes merely cost more near where enemies stood when planning began. So the planner led the wizard toward a level-12 Red Banshee and patrolling ghouls on Triton's upper level again and again: eighteen step-aways on one walk to an NPC, and a loop of step-aways at the TempestNexus teleporter. On the grace period, the operator said that after a fight "a wizard has invisible frames for like 10 seconds, and so can move through mobs without worring about agro. to be save, assume 6 seconds". The margin keeps the wizard from standing next to an enemy when the protection ends.
  - **Not verified yet:** enemy speeds and how well a straight-line guess follows a patrol in the game. The predictions are tested offline with steady movement.
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

- **A cast that did not take is cast again.**
  - **What:** after casting, the battle code waits up to 3 seconds (`combat.CAST_TAKES_WITHIN_SECONDS`) for the duel to leave planning, as it does at once when the wizard battles alone, or for the planning window to say it is waiting for other players. When neither happens, it reads the hand again and casts the same card once more, and the round event says "cast again: the first did not take".
  - **Why:** of 110 casts followed by another round, 25 spent no mana and did nothing. Seven were the first cast of a battle, and the client's log for the latest shows no move sent and the planning window in another selection state (0, not 8) for that round; the second round's cast worked. The rest followed clicks on Flee. The wizard lost a round to its enemies each time.
  - **Not verified yet:** in the game.

- **A spell the wizard can pay for before fleeing, and whether each move took.**
  - **What:** the flee rule now waits until no castable attack in hand costs at most the mana left (a mana a pip), so with 1 mana a 1-pip spell is still played. Once a battle is over, each round's entry records the moves the client logged after the wizard acted (`connection.moves_by_round`, from `Bin/WizardClient.log`), and the battle event names any round in which the game logged no move. It is read after the battle because the client writes its log in buffered blocks, up to a minute behind: read a second after each cast, a cast that took showed as "no move". It reads the last 4 MB (`connection.BATTLE_LOG_TAIL_BYTES`) and judges only rounds the text covers from the moment the wizard acted: read from the 200 KB used for connection checks, the first five rounds of a long won battle seemed to have no move. A flee click that brings no confirmation box now reports the visible windows of the planning window, of the whole planning phase and at the top (`ui.visible_tree`). The first such report showed only the planning timer left in the planning window: the click hid the hand, and whatever it waits for is elsewhere.
  - **Why:** a Cyclops Legionnaire was down to 60 health and a 1-pip Fire Cat in hand would surely have finished it, but with 1 mana the policy clicked Flee. The client's log shows that the click sent no move: the round ran out its 30-second timer, and from then on the planning window stayed in another selection state, in which the next two Fire Cat casts sent no move at all. Mana stayed at 1, the Cyclops at 60, and the wizard was defeated. Every flee so far has ended this way.
  - **Not verified yet:** the window report after a flee click, in the game.

- **A lost server connection is named as such.** When no planning phase comes in a battle, the battle code reads the end of the game client's own log (`Bin/WizardClient.log` in the game folder, `connection.py`). If the last "AppCloseConnection() called" has no "ConnectComplete" after it, the run stops with "the game lost its connection to the server at <time>; a login is needed". On 2026-10-27 the connection closed at 02:06 in the middle of a battle: the client froze in the execution phase, and two runs stopped with "no planning phase within the timeout" before the log showed why. The framework never logs in; that stays with the operator.

- **The hand is taken back when the planning window is stuck waiting.** At the start of each of the wizard's turns to choose, if the planning window still shows its "waiting for others" panel (`PlanningPhaseSubWindow/WaitingForOthers`), the battle code clicks its Change button to get the hand back, and the round's event says "reopened the card choice". A click on Flee that did not end the battle left that panel up. From then on no card click landed, into the next battle too: a Warhorn stayed at 285 for 13 rounds while the wizard's attacks and Pixie heals did nothing, and the wizard was defeated. A dump of the planning window after that battle showed the panel still flagged visible.

- **A battle is logged as fled only when a flee ended it.** A Warhorn fight in which the flee did not work, and the Warhorn then fell, was logged "fled" with its gold. Now only a battle that ends right after a flee counts as fled.

- **Pass and Flee click the real buttons.**
  - **What:** the battle code clicks `ActionButtons/Focus` (Pass) and `ActionButtons/Flee` under `WorldView/PlanningPhase/Alignment/PlanningPhaseSubWindow/SpellSelection` by their paths, instead of WizWalker's `pass_button` and `flee_button`. After Flee it waits a second and answers Yes to a message box whose caption mentions fleeing, if one appears; any other box is left alone, and the round's event says what followed.
  - **Why:** WizWalker clicks the `DoneWindow`'s `DefeatedPassButton` or `DefeatedFleeButton`, meant for a wizard knocked out in battle, whenever `DoneWindow` says it is visible. In this client it always does, even outside battle. So no flee ever took: against General Akilles and twice against Warhorns, the battle went on after the flee, and after it the wizard's casts stopped landing (a Warhorn stayed at 285 for six rounds). Passes probably never took either; the round timer ran out instead.
  - **A disabled Flee button is not chosen.** Before the policy chooses, the battle code checks that the Flee button is there and not disabled (WizWalker's `WindowFlags.disabled`); if it is, the round view says the battle cannot be fled and the wizard plays its cards. With the new click, a flee from a Warhorn fight shared with another player still did not end the battle; whether the game refused it or the click did not land is not known yet.
  - **Not verified yet:** a flee that ends a battle in the game. Passes with the new click look right: the next round came 14 seconds after one.

- **Safe places are told by the enemies loaded, not by patrol paths.** The gear turn and the end of a run first required a zone whose files show no patrol paths. But the Commons, Ravenwood, the Shopping District and Olde Town have patrol paths for their friendly NPCs (120 segments in the Commons), and General Akilles' tower has none although he stands in it. A run starting in the Commons never checked its gear. `safe_here` now asks only that no enemy be loaded nearby.

- **A battle that cannot be fled is fought on.** When the wizard flees and the battle goes on to another round, it does not try again in that battle (`RoundView.can_flee`) and plays its cards instead. With 1 mana against General Akilles in his tower, the Flee click did not end the battle; the wizard chose to flee each round, which passed, while the General and his Cyclops took its health from 801 to 486 in three rounds.

- **Routes are planned in a fraction of a second, so the wizard no longer stands still among patrolling enemies.**
  - **What:** straightening a nav route checks each sample of each shortcut against only the waypoints in nearby buckets (`NavGraph.near_a_waypoint`), not against all of them. The walk grid remembers each cell's floor height, and the patrol map each point's distance to a patrol path; both are fixed within a zone. On Cyclops Lane, with patrol paths as hazards, a nav route from the lane's start took 5.8 to 7.1 s and now takes 0.14 to 0.25 s, with the same legs. A collision route took 1.2 to 1.5 s and now takes 0.2 to 0.8 s.
  - **Why:** the operator saw the wizard "still attacking wrong mobs" on its way to the Warhorns the quest asked for. The run log showed why. Each turn stood still for 4 to 6 seconds before "route by nav", and before two of the fights a failed nav route was followed by a collision route planned for about 16 more seconds. In one of those, the wizard moved 40 units in 19 seconds before a Cyclops walked into it. Profiling put 99% of a nav route's time in the waypoint check: 65 million distance calls.
  - **Not verified yet:** fewer fights with bystanders in the game.

- **Wisps are fetched only on the way, and a failed wisp trip is not repeated.**
  - **What:** a wisp now counts only when the detour through it toward the quest arrow is at most 1,200 units (`targets.WISP_DETOUR`). Below 35% health (`progress.WISP_ANY_DIRECTION_BELOW_FRACTION`) any wisp in reach still counts. With no wisp on the way, the quest goes on. A wisp trip that gains nothing is marked tried even when it was cut short. Before, only a trip that arrived was marked.
  - **Why:** the operator saw the wizard "keeps going back and forth" in Cyclops Lane and "isn't going to the right mobs". The bounty's targets were at the far end of the lane. Below 65% health, every turn walked back up to 2,500 units to the nearest wisp. Two of those were used up ("health 263 -> 263"), and interrupted trips were tried again. On the way back, the Cyclopes and Trolls the quest did not ask for pulled the wizard into fights.
  - **Not verified yet:** in the game.

- **An NPC menu option whose label cannot be read no longer crashes the run.** A school professor's services menu has a spell-training option whose label text cannot be read from memory. Reading it raised a memory error, and a run that started beside the professor stopped at once. Such a label now reads as empty, so the option is never chosen.

- **An empty hand is read again before passing.** When the hand reads empty in a planning phase and the wizard is alive, the battle code reads it again every half second, up to six times. If it is still empty it passes, logged as "pass: the hand read empty". Round lines now show mana too. In a fight with two Warhorns, the hand read empty in round 3 although the wizard had cast from a full hand in rounds 1 and 2: it passed with 107 health and three pips, and was defeated. The operator noticed it as "you stopped selecting cards". The hand was most likely read before the round's cards were drawn.

- **Walls at the wizard's height.**
  - **What:** the walkable area now subtracts every box, cylinder and sphere collider that stands in the wizard's way: its bottom less than 180 units above the floor beneath it, and its top above that floor. Deimos's own wall builder, used until now, counts only colliders that start within 50 units of the floor. That suits its teleporting but not walking.
  - **Why:** the operator saw the wizard keep walking into Cyclops Lane's fairground tents, even after placed objects were added: the tents are not placed objects. At every point where the wizard got stuck there, the floor is at height 1 and two cylinders cover the spot, from 59 to 436 and from 109 to 340. Those are the tents, left out as "overhead".

- **Wall clearance matches the wizard's body.** The walkable area now keeps 45 units from collision walls, not 30, which is the body radius Deimos's walk grid uses. With 30, a gap of about 77 units between two boxes in the Myth school stayed walkable, though the wizard cannot fit through it. Routes on Triton Avenue, Cyclops Lane, in Ravenwood and in the Shopping District were checked and still found. The operator noticed the wizard "always" walks into props in the Myth school. Some of those props seem not to be box colliders at all: no collision route reaches the quest NPC there, and the nav and straight-line fallbacks still bump into them.

- **A zone read during loading no longer breaks the report.** The zone reads as empty for a moment during some loading screens. The loop recorded an "arrival" in that empty zone, and saving the report then failed, because JSON keys could not be sorted with an empty one among zone names; the report of that run was lost. Arrivals now need a zone name, and reports turn every key into text before sorting.

- **A short settle after arriving in a zone.** The loop now waits 1.5 s on its first turn after every loading screen, and on its first turn in a zone, before acting; it waits on until two zone readings agree. Right after one load, the zone read as the zone just left, and the loop walked toward that zone's door coordinates inside the Myth school, straight back out through its exit. Settling only on a zone change missed this, because the stale reading matched the zone already settled in. Each turn record in the report also holds the zone, position, goal and quest arrow. Twice the wizard entered the Myth school and was back in Ravenwood within three seconds, on a "travel to waypoint" turn, as if the goal were still in another zone. The likeliest cause is a zone or quest-arrow reading that had not caught up after loading; the third entry, a few seconds later, stayed and finished the talk. The new turn fields will show whether that was it.

- **A door just come through stays out of routes.**
  - **What:** a teleport volume the wizard stands beside, as it does after coming through it, is now kept out of routes at its own radius instead of being left out entirely. Only a volume the wizard stands in is left out. Nav routes no longer start or end at a waypoint inside a no-go area.
  - **Why:** in the Myth school, the collision data had no route to the quest NPC, so the nav route was used. Its nearest waypoint lay past the school's exit, which was not kept out because the wizard had just come through it. Every walk to the NPC led back out to Ravenwood, and the goal led back in, until the door-loop guard stopped the run.

- **The nav graph first where the collision data misses obstacles.**
  - **What:** when a trip's collision route gets stuck on the way and the nav route then walks on, the zone is marked: its routes try the zone's nav graph first from then on, and `runtime/knowledge.json` remembers it for later runs. The event log says so once per zone.
  - **Why:** the operator noticed the wizard "seem[s] to like to walk into the fairground tents" on Cyclops Lane. The tents are placed objects whose footprints are not in the collision walls the framework subtracts. Every collision route there got stuck at a tent, recorded five obstacles and fell back to the nav route, which walks around them because the zone's nav waypoints were laid out on walkable paths. Deimos can build the placed objects' footprints (`entity_collision.build_zone_static_shapes`), but it needs the `katsuba`, `kinif` and `wiztype` packages, which are not installed here; with them, the tents could join the walls instead.

- **No teleporter for a goal the wizard's own area reaches.**
  - **What:** a goal in another walkable piece no longer calls for a teleporter when the wizard's piece also comes within 600 units of it, or when the zone's nav graph has a path from near the wizard to near the goal. The wizard walks there instead, by the nav route if the collision data has none.
  - **Why:** Ravenwood's walkway to the Commons is missing from its collision mesh. So the gate lay in a walkable sliver of its own (about 400 by 130 units), 1,053 units from the main area. The planner looked for a teleporter into that sliver: it walked into the Ice school's door, then headed for the Myth school's, before the run was stopped. The nav graph walks straight to the gate. Triton, whose levels really are joined only by teleporters, has no nav graph that loads, so its crossings are unchanged.

- **A run that starts facing its target walks.**
  - **What:** before its first turn a run does not know how A and D turn the wizard, so the walking loop turned in place first. Now it does that only when the facing is off. A wizard already facing its target walks straight away, and steers only once turning has been learned.
  - **Why:** a run started in the Storm school facing the exit. The turn needed no tap, so it taught nothing, and the loop asked for it again and again: the wizard stood still for a minute, with no log line, until the run was stopped. The operator noticed it as "no movement".

- **Chains of teleporters.**
  - **What:** to reach another walkable piece of a zone, the loop now follows the shortest chain of teleport volumes known to lead piece to piece, not just one volume. When no known chain reaches the goal's piece and nothing is left to try where the wizard stands, it follows a known chain to a piece that still has an untried volume.
  - **Why:** after a talk in Triton's TempestNexus area, the next goal was the street's exit, two hops away: High_Ledge to the upper level, then Tele Down. The only volume in the TempestNexus area, High_Ledge, had already been tried and was known to lead to the upper level, not the exit's piece. So no crossing was chosen, every route failed, and the run stopped on turns without progress.

- **Walks keep out of teleport volumes they are not going to.**
  - **What:** every route now treats the zone's teleport volumes as no-go circles 60 units wider than the volume. Each shop and building door in a street is one. Left out are a volume at the destination, which may be the door the walk is for; one the wizard stands at, as it does after coming through it; and volumes on another walkable piece, such as another level.
  - **Why:** in one run the wizard walked into the Jeweler's shop on its way across the Shopping District. Later it walked out of The Harvest Lord's tower on its way to a health wisp, while its next goal was to talk to someone inside. Both doors were in the zone's `volumes.xml` all along.

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
