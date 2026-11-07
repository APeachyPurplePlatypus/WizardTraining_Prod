# Retro: level 20 to 25

One character, all of it in Krokotopia, the second world. It ran from level 20 (2026-11-02 05:34 UTC) to level 25 (2026-11-07 19:39 UTC), with WizWalker 1.8.2 as vendored in Deimos. Level 21 came on 2026-11-03 at 05:18 UTC, 22 at 07:43, 23 at 09:12, and 24 on 2026-11-04 at 07:30. Play stopped from 2026-11-04 16:48 to 2026-11-07 15:25 for a weekly usage limit, apart from a short run on 2026-11-05. The event logs record 172 battles over the stretch: 160 won, 6 lost and 6 fled. The general rules drawn from it are in [lessons-learned.md](../lessons-learned.md).

## What worked

- **Two dungeons cleared alone, by their puzzles.** The first dungeon's doors opened on four braziers that step through three schools and on obelisks that turn after each use. Reading each object's state from the game, pressing until it showed the one wanted and waiting out a turn opened every door, and its last boss fell just before level 21. The second dungeon's frost door opened after three locks, each broken by a fight and a riddle in a corner room. Keeping the done locks across refill trips cleared it on 2026-11-04.
- **An outside game database for planning.** Quests, enemies, spells and items were looked up before choosing gear, quests and the route on to level 50. Gear bought for gold by its list raised health from 1,350 to about 1,650 and resist to 8%.
- **A per-zone log of stuck walks.** Started at the operator's request on 2026-11-07. A hub quest stuck for an hour on two days was solved within the session: the log showed every walk ending at the same wall, the waypoint graph's link through it was set aside, and the next walk took a longer loop and reached the goal.
- **The operator's lever tip.** A tower room held the character for two runs: its exit volume never prompted. The way on was what the operator suggested looking for: a lever one floor below the volume, whose interact prompt the walk found the same minute, and the next room loaded.
- **Side quests by the journal's Quest Finder,** while the main quest waited at a door: several side quests in the last two days, a few hundred to about 900 XP each.
- **Fight fixes from the operator's words and the round logs:** stun-immune enemies left alone, enemy absorbs and burns counted, mana wisps taken inside dungeons, and a second trap cast instead of a pass.
- **A grind loop for the last few hundred XP.** It restarted the run after each stall in a tower room with enemies, stopped at the level, and won its last three runs without a loss.

## What didn't

- **The hub's raised levels.** Walks to goals on a ledge or up a ramp in the world's hub looped for up to half an hour with "no route onto the destination's level". One was a waypoint link through a wall; a library door that worked in the morning failed in the afternoon.
- **Quests set aside at level 24 for doors and props:** a goal behind the frost door taken up before the door opened, a crypt behind a large lizard the character can't get past, and two quests at a keyed door in a third dungeon.
- **One side room's enemies beat the character twice.** A group with a strong healer won both tries at level 24. Set aside.
- **Long fights from a small deck.** The 14-card starter deck, three heals held back, gave fights of 10 to 13 rounds with passes and fizzles.
- **Quests switched by the game.** After a hand-in the game made a quest active that pointed to another world, while a new quest's offer box was still open, so the switch to another quest found nothing. The run now stops for the operator in that case.
- **Crashes from bad readings.** An enemy read mid-spawn had no position (not a number) and broke the patrol lookup; a walk to a gap's edge called itself until it crashed.
- **Restarts that ran the full test suite** took six minutes each, which the operator found too slow. With the code unchanged since the last good run, the suites are now skipped.
- **Still not working:** the potion minigame refill and fishing.

## Open at the time

- Krokotopia's main quest at the keyed door in its third dungeon, and the quests set aside to level 25.
- A deck review, and training points at level 25 planned with the outside database.
- The release of this framework at 0.5.0, then the route on toward level 50.
