# Retro: level 15 to 20

One character. It finished Wizard City, Sunken City's dungeon included, and then went on to Krokotopia. It ran from level 15 (2026-10-28 22:44 UTC) to level 20 (2026-11-02 05:34 UTC), with WizWalker 1.8.2 as vendored in Deimos. Level 17 came on 2026-10-29 at 17:44 UTC, 18 on 2026-11-01 at 10:41 and 19 at 19:46. Play stopped from 2026-10-29 21:29 to 2026-11-01 05:44 for a weekly usage limit. The event logs record 196 battles over the stretch: 172 won, 11 lost and 13 fled. The last 1,390 XP came from side quests in the second world, while its main quest waited at a door the bot can't open yet. The general rules drawn from it are in [lessons-learned.md](../lessons-learned.md).

## What worked

- **The dungeon helper for a boss beyond the character.** Sunken City's boss beat the wizard with every one of four combat strategies at levels 16 and 17. With the operator's approval, the game's matchmaking found a team in about two minutes at level 18, and the boss fell with the wizard at full health. The final boss fell with the fifth team.
- **Finishing a world's side quests from the game's own data.** One quest asked for a book read in each of seven towers, with no quest arrow. Others hid their goals in tower doors, glowing fish and trigger volumes. The zone files placed each one, and the journal's Quest Finder showed when the world's givers had run out.
- **The healing audit.** In 32 of 38 wins the heal was still in hand at the end, and nearly every costly fight was followed by a trip home. The fixes: fight on above about 60% of health, heal with one enemy left rather than wait for a sure kill, heal a round earlier when the enemies act first, and put up a shield in danger when no heal can be cast.
- **Answering a talk prompt as soon as it shows,** when its NPC is the nearest person. A quest NPC floating far past a ledge was reached this way.
- **Fixes seen working within minutes of the fault:**
  - topping up mana in the hub before walking into a zone whose quest starts over on entry (20 to 107 mana in 74 s);
  - Ice Prism on an enemy that resists Ice (135 against about 91 straight);
  - Go Home inside the hub to get out of a stuck spot (3 s);
  - a cleared world no longer cleared again on each restart.

## What didn't

- **A sewer quest chain was lost four times.** It starts over each time its zone is entered. Its boss healed itself five times in one fight, behind a strong shield, while fresh minions kept joining. One try was also lost to a flee with the last enemy nearly dead. The chain is set aside until level 25.
- **The team beat the dungeon's final boss twice without the wizard.** It was stopped once and stood aside once, and boss credit goes only to those in the fight. Standing on the boss's own combat spot, read from the zone data, fixed it.
- **The dungeon's gates opened only through the wizard's own quests,** so the team couldn't carry it past them. The dungeon's chain had to be played first.
- **Safety-first routing hugged the walls.** Pricing street paving as dangerous kept walks to the sidewalks. The operator found the wall-hugging too slow and asked for it to be removed. Live enemies and enemy paths still set the cost.
- **Small things blocked walks for minutes:** Halloween pumpkins in the streets, a door name glued to its neighbour's text, and a lower level of a hub that no route left.
- **A stop in a zone with patrols lost a fight.** Stopped in the sewer after a win, the wizard was pulled into a fight by a patrol and passed every round on the game's idle timer. Stop only where no enemy walks (the rule was already in the lessons; it was broken by hand).
- **Every fix needed a restart,** and most restarts were done from the supervisor's side. Restarts in the second world walked back to the first to clear it again until that was remembered.
- **The second world's first dungeon has a scripted door the bot can't open yet.** The main quest's boss sits behind a door that, by the zone's trigger file, opens only when a staff from the dungeon's side quest is used on four obelisks to leave a set pattern. The side quest's own walk stuck at a shut gate first, and was set aside. Then the main quest stuck at the obelisk door, and was set aside too, while side quests elsewhere paid for the rest of the level.
- **A quest set aside was still played.** The check for set-aside quests ran only while a world was being cleared. In the second world a quest set aside, made active again by the game after a hand-in, sent the character back to the dungeon door. Each exit from that dungeon also made a quest for a third world active.
- **A return to a large dungeon was read as a reset.** Its return button lands at the dungeon's start, far from the exit spot, so the enemies near the landing didn't match those near the exit. Refills then waited in place, and a fight was lost at under half health. Comparing only near the exit spot fixed it; the next return found the dungeon held.
- **Still not working:** the potion minigame refill (its board ignores messages sent to the window) and fishing (not in the loop yet).

## Open at the time

- Krokotopia's main quest: the dungeon's obelisk door (play its side quest for the staff first, then the obelisk pattern), its boss, then the rest of the world's quests and the Balance trainer.
- The sewer chain at level 25, the dueling tutorial quest, and the fishing quest.
- Grizzleheim, Marleybone and their quests, which wait for the operator's word.
- Better quest and card data, through an outside quest database, which is still waiting for access.
