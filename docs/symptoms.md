# Symptoms and likely causes

When an unattended run goes wrong, the same few causes come back again and again. This page starts from what you see in the bot's log or on screen, lists the causes found in play, roughly most likely first, and says what to check. The [lessons](lessons-learned.md) tell the full stories.

Check the cheap things first: whether a battle is showing, whether a window or game box is open, and what the game client's own log says.

## Movement and keys

- **Keys change nothing.**
  - A battle began between two steps.
  - A window holds the keyboard: an endorse window after a shared battle, a request from another player, or a game box.
  - A zone is loading.
  - Check the battle state first, then open windows. Don't stop the run for "keys ignored" before both are ruled out.
- **The character creeps toward a target for minutes and never reaches it.**
  - The target is on another floor or a balcony. The walk data is flat, so compare heights.
  - The target stands behind a counter and can be talked to from farther away.
  - The collision data is missing a ramp or stair.
- **The character walks straight back out of a zone it just entered.** The quest arrow still points where it pointed in the last zone. Wait for the arrow to update after a zone change before walking on it.
- **A walk keeps "arriving" without getting anywhere.** An arrival where the character already stood was counted as progress. Count only real movement or a change in state.

## Turns that repeat

- **Turns return almost at once and repeat many times.** Something is refusing the action:
  - an approach next to another player's fight;
  - a walk blocked by a duel;
  - a menu that won't switch;
  - the Quest Finder when the world has no quest givers left.
  - Guard against the whole family at once: when several turns in a row take almost no time and change nothing, back off and count a stall instead of trying again at full speed.
- **The Quest Finder answers "There are no available quests in this world".** The world's givers are used up. Retry any quests set aside in that world, then move on.

## Quests

- **A use or a talk "did nothing", but the game gave XP.**
  - The game counts the goal several seconds late.
  - One step closed and the next opened, so the number of open goals stayed the same. Check which goal closed.
- **A use fails at a door.** The object is behind the door. Go through it.
- **A goal names a tag that matches no object.** The tag is in the objects' template files, not their names.
- **A quest left the journal after a defeat in a dungeon.** Quests given inside an instance exist only inside it. Remember which quest led in, and go back through that one.

## Numbers

- **Maximum health jumps, or doesn't match the health globe.**
  - The stats read picked up another player's stats beside their fight.
  - A short end-of-fight effect.
  - Trust the wizard's own battle data and the client log's health-globe lines.
- **"Not in battle" or "ended" in the middle of a battle.** A failed duel lookup reads as ended. Confirm with two readings a second apart.

## Travel

- **The bot keeps walking to a door that isn't there.** It learned the door from a flee or a Go Home that moved the character, not from a walk. Forget learned doors that fail twice.
- **Recall lands in a fight.** The mark was set where a fight happened or near a patrol path.
- **Recall doesn't get back into a dungeon.** Use the dungeon's own return button, within its timer.
- **A zone load takes over a minute.** The connection probably dropped. Read the client's log, and leave logging back in to the operator.

## Health

- **Standing to regenerate gives nothing back.** The zone has enemies, is an instance or a tower, or is a small side room. Go to the hub.
- **The character went home after almost every fight.** Heals were left in hand at the fights' ends. Top up before the last kill, and fight on above a moderate health line.

## The bot itself

- **Hooking fails after a crash.** The last run died without removing its hooks. Restart the game.
- **Every hook vanished in the middle of a run.** Another tool attached to the game and removed all the hooks when it exited.
