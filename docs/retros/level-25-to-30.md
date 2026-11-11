# Retro: level 25 to 30

One character, from the last dungeons of Krokotopia, the second world, into Marleybone, the third. It ran from level 25 (2026-11-07 19:39 UTC) to level 30 (2026-11-11 00:54 UTC), with WizWalker 1.8.2 as vendored in Deimos. Level 26 came on 2026-11-08, 27 by 2026-11-10, 28 on 2026-11-10 at 20:34, and 29 at 22:06 the same evening, by then in Marleybone. The battle tally for this stretch was not gathered for this release. The general rules drawn from it are in [lessons-learned.md](../lessons-learned.md).

## What worked

- **Puzzle doors solved from the room's own clues.** The second world's last temple held a door of moon and sun objects and a room of braziers and obelisks. The book pedestals in those rooms said what each door wanted. Read first, then pressed in order, both doors opened, and each solution was kept as an opener for the next visit. The world's final boss fell with 51 health left.
- **A boss eight levels up.** At level 29 a level 38 boss in Marleybone was beaten on the second try, in 20 rounds, with 967 health left.
- **A map of each zone's levels.** Built from the heights in the game's nav graph: which links are ramps, drops, cliffs or rides. A walk onto the lower level of the second world's hub, which had looped for days, went straight down the one real ramp once the map named it.
- **Boarding a ride when no walk reaches the arrow.** A quest arrow on an island, with no door learned toward it, had the character walking into the water. Taking the ride line from the nav graph and boarding the ride there worked on the first live try.
- **Door maps from the zone files.** Reading every zone's trigger files offline (about 500 zones across two worlds) listed each door and what opens it. The maps matched the doors solved by hand in three dungeons.
- **An area attack that clears mob groups.** With the first area attack trained at 26 and its real damage read from the game (250 to 290 per enemy here), a damage estimate before each cast picked a blade or a trap first when one would make the attack finish every enemy.
- **Deciding instead of stopping.** From 2026-11-09, when no quest could be played, the bot fought where XP came fastest instead of stopping for the operator, and logged each choice.

## What didn't

- **About three hours with no deck worn.** After a deck switch went wrong, no deck was equipped, so each hand held only the item cards that gear gives. The hand read as empty, and three easy fights were lost passing. The cause was found only after two wrong fixes aimed at reading the hand.
- **A deck check that read nothing.** Every spell lookup came back blank, and the check still called the deck as wanted and saved that. The first area attack stayed out of the deck until the operator asked where it was.
- **A sale of 57 combat treasure cards,** about 4,000 gold, read as housing items. The shop files treasure cards under categories named after the schools, and a sell visit took them for something else.
- **A boss deck with no area attack.** Area attacks came last in its list, and its 30 slots filled first, so boss fights with minions ran long. The operator: "aoe attacaks in boss fights probably would have made some battles go quicker".
- **Too few discards.** One day's logs had no discard in 172 of 201 rounds, with spare blades, prisms, traps and a reshuffle held in hand. The operator: "the bot is too conservative when discarding cards today".
- **A boss read as a mob.** A boss with 800 health and a guard was taken for a mob fight by its health, so the stacking rule for bosses never fired. The game's own boss flag was read from then on.
- **Braziers lit twice before reading the pedestal** beside them, which gave the order.
- **A hint logged and not acted on.** The door maps named a book pedestal as the one press that opened a tower's door, and the bot logged that and walked on. The operator found it in the log.
- **Shop windows.** A shop window opened beside a quest NPC and took every key. Another quest's arrow stood on an NPC, and the walk treated it as a door into the zone the goal named.
- **The third world's door home not found.** The trip back to the first world to train a spell waits until the third world's world door is known.
- **A pair of strong casters in a side area** won one fight and forced two flees at level 26. The quest was set aside.

## Open at the time

- Not yet seen in play: area attacks in boss fights, the looser discards, stacking before a boss's big hit, and a timed crossing of a hub's obelisks.
- Training the next spell, which waits on the third world's world door.
- A gear farm in a later dungeon, planned by the operator for level 30, then questing on toward 35.
- The release of this framework at 0.6.0.
