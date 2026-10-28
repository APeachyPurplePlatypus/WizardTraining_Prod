# Retro: level 10 to 15

One character, Wizard City with visits to Krokotopia, from level 10 (2026-10-27 14:12) to level 15 (2026-10-28 18:44), with WizWalker as vendored in Deimos. Levels came at 20:47, 22:31 and 23:44 on the 27th, then 14:16 and 18:44 on the 28th. On the 28th the event logs record 108 battles won and 3 lost. Each finding below links to where its fix lives; the general rules are in [lessons-learned.md](../lessons-learned.md) and every change, with its reason, in [CHANGELOG.md](../../CHANGELOG.md).

## What worked

- **Clearing a world with the Quest Finder and the school professors** found side quests the main story never points at: The Looking Glass, Pesky Pirates, All the Eels, Wayward Barrels, Better Get Kraken, Decease the Kraken! and Odd Tidings in one evening, each a few hundred XP. Hand-ins carried the last two levels; street fights gave 10 to 50 XP each.
- **Reading the game's own files for what the quest arrow does not show.** The Cogs came from the goal's tags and the zone's placed objects; the Smiths of "Find the Smiths" from trigger volumes in `volumes.xml` named after the quest, each on the zone's Explore object. This is now one lookup for every goal without an arrow (`untracked.py`). 9 of 10 Smiths were found; the tenth, on Colossus Boulevard, is next.
- **Ramps and stairs the collision data misses** are climbed by the game's nav graph, from the foot of the ramp to the top (`ramps.py`). The Commons and Olde Town Smiths, Triton's lower street and the Kraken were reached this way.
- **Combat by the numbers seen.** Each enemy kind's biggest hit is learned and kept, and the danger estimate uses it instead of a flat damage per pip; traps go on whenever the round would otherwise play no card, and wands of unresisted schools go before resisted hits (the operator's rules).
- **Refill trips with the game's own buttons.** Mark, Go Home and Recall, with the trip state kept across restarts, and a push on to a goal that is close instead of a refill.
- **The XP bar is read** (`experience.py`), so every report says how far the next level is and what each fight or hand-in gave.

## What did not

- **Colossus Boulevard cost about an hour and a half** of Snowman fights for "No More Mr. Ice Guy": every fight was heavy, every refill trip came back by Recall into the same crowd. Fixed by pushing on toward a near goal, comparing refill trips for headway, and walking in by the entrance instead.
- **Missing zone knowledge stalled the run five times:** Colossus Boulevard and Triton Avenue's underwater zone were not in the hand-kept zone tree; Kraken Isle was reached only through a volume not named as a teleport; the isle's way off could not be placed on the flat walk grid; a misspelt gate ("Collossus"). The client's zone files do not say where street doors lead, so the doors learned walking now fill the gaps (`RunRecord.zone_doors`).
- **A refill mark can trap the wizard.** One set where the Kraken fight ended put every Recall back on the isle. A mark that no route leaves is forgotten and never set there again.
- **An instance was entered at 45% health** and the next fight was lost: health and mana do not come back inside (measured, 90 s gave nothing). Doors known to open on an instance now wait for a refill.
- **"Heal earlier" was too careful** until the danger estimate used the hits seen: it passed rounds at 94% health to save pips for a heal.
- **Restarts by the supervisor cost time and twice went wrong:** a STOP written right after an "approached" turn left a boss fight unplayed for 17 seconds, and once during a fresh battle. The rule is now: read the log, then write STOP as a separate step.
- **Mark Location failed four times** with no message; the cause is still not known (each failure now logs what the buttons showed).

## Open

- The Colossus Boulevard Smith, "Curfew!" (an instance) and the rest of Wizard City's Quest Finder pass; then Krokotopia: Gather the Troops, its side quests, and Elemental Blade and Elemental Trap at the Balance Tree (the only training the operator allows for now).
- Quests held until the wizard404 API is connected: Wizards in the Mist and Strange Brew. "To Sunken City" waits on the operator's word at its dungeon-entry box.
- Not yet seen working in the game: the doors learned walking, the narrowed refill before instance doors, the height-judged "From <place>" exit, and the top-of-ramp step.
- A dungeon's own return button (`ResumeInstanceButton`) may allow refill trips out of dungeons within their 30-minute timer; it is not to be pressed until the operator approves it.
