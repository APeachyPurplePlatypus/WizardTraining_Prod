# Retro: level 10 to 15

One character, Wizard City with visits to Krokotopia, from level 10 (2026-10-27 14:12) to level 15 (2026-10-28 18:44), with WizWalker 1.8.2 as vendored in Deimos. Levels came at 20:47, 22:31 and 23:44 on the 27th, then 14:16 and 18:44 on the 28th. On the 28th the event logs record 108 battles won and 3 lost. The general rules drawn from it are in [lessons-learned.md](../lessons-learned.md).

## What worked

- **Clearing a world with the Quest Finder and the school professors** found side quests the main story never points at: The Looking Glass, Pesky Pirates, All the Eels, Wayward Barrels, Better Get Kraken, Decease the Kraken! and Odd Tidings in one evening, each worth a few hundred XP. Hand-ins carried the last two levels; street fights gave 10 to 50 XP each.
- **Reading the game's own files for what the quest arrow doesn't show.** The Cogs came from the goal's tags and the zone's placed objects. The Smiths of "Find the Smiths" came from trigger volumes named after the quest, each on the zone's Explore object. 9 of 10 Smiths were found this way.
- **Climbing ramps and stairs the collision data misses** by the game's nav graph, from the foot of the ramp to the top. The Commons and Olde Town Smiths, Triton's lower street and the Kraken were reached this way.
- **Combat by the numbers seen.** Each enemy kind's biggest hit was learned and kept, and the danger estimate used it instead of a flat damage per pip. Traps went on whenever the round would otherwise play no card. Wand spells of unresisted schools went before resisted hits.
- **Refill trips with the game's own buttons:** Mark, Go Home and Recall, with the trip's state kept across restarts, and pushing on to a goal that's close instead of refilling.
- **Reading the XP bar,** so every report said how far the next level was and what each fight or hand-in gave.

## What didn't

- **Colossus Boulevard cost about an hour and a half** of Snowman fights for one quest. Every fight was heavy, and every refill trip came back by Recall into the same crowd. Pushing on toward a near goal, comparing refill trips by headway, and walking in by the entrance fixed it.
- **Missing zone knowledge stalled the run five times.** Two zones weren't on the hand-kept map. One island was reached only through a volume not named as a teleport, and its way off couldn't be placed on the flat walk grid. A gate name was misspelt. The zone files don't say where street doors lead, so doors learned by walking now fill the gaps.
- **A refill mark trapped the wizard.** One set where the Kraken fight ended put every Recall back on the island. A mark no route leaves is now forgotten and never set there again.
- **An instance was entered at 45% health,** and the next fight was lost. Health and mana don't come back inside (90 s gave nothing). Doors known to open on an instance now wait for a refill.
- **"Heal earlier" was too careful** until the danger estimate used the hits seen: it passed rounds at 94% health to save pips for a heal.
- **Restarts by the supervisor cost time, and twice went wrong.** A stop signalled right after the bot approached a boss left the fight unplayed for 17 seconds, and once it happened in a fresh battle. The rule now: read what the bot is doing, then signal the stop as a separate step.
- **Mark Location failed four times** with no message. The cause is still unknown.

## Open at the time

- The Colossus Boulevard Smith, "Curfew!" (an instance) and the rest of Wizard City's quests; then Krokotopia's main quest, its side quests, and the Balance trainer.
- Quests held until better quest and card data is available, and Sunken City's dungeon, which waited for the operator's word at its entry box.
- Not yet seen working in the game: doors learned while walking, the narrower refill before instance doors, and the top-of-ramp step.
- A dungeon's own return button might allow refill trips out of dungeons within their 30-minute timer. It was not to be pressed until the operator approved it, which came later that night.
