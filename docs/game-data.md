# Game data

Decide from the game's own data before guessing or exploring. This is a map of what the game exposes and where to look for it, as found with the Windows client in October 2026. It names places, not values: the game updates often, and memory layouts, offsets and window paths change with it. Check everything against the client you have.

Everything here is read-only. Reading is enough to play; writing memory (position, facing, speed) is teleporting or speed-hacking. See [safety.md](safety.md).

## Tools

- **WizWalker,** as vendored in Deimos-Wizard101 (version 1.8.2 at the time), reads live memory and sends keys and mouseless clicks. Its memory objects are the best index of what can be read; check its source before relying on a reader.
- **Deimos-Wizard101** reads the zone files: collision, the nav graph, placed objects. It has a walk grid and a combat damage estimate worth reading even if you write your own.
- **wiztype** dumps the running client's type layout, with every class and field offset for that game version. Use it for anything WizWalker has no reader for, and dump again after a game update.
- **katsuba** reads the game's archives and binary data, including placed objects and their models.

## Live memory

What a bot can read while playing, and what it was used for:

- **Where the character is:** zone name, position and facing, and the loading, battle, dialog and "in NPC range" states. These drive every turn.
- **The character's numbers:** level, health and maximum, mana, gold, potion charges, and damage, resistance, critical, block and pierce by school. The reference level lags behind a level-up until the next zone change; the school behaviour on the client object holds the real one.
- **Experience:** the XP bar's own values, read without clicks, so each fight or hand-in can be credited.
- **Quests:** the quest manager lists the journal. Each quest has a title key, a main-line flag and a ready-to-turn-in flag. Each goal has a type (bounty, talk, waypoint, use an object, collect, explore and so on), a destination zone, tag lists naming its targets, and a flag for goals the quest helper doesn't point at.
- **The quest arrow:** a position, for goals the helper points at.
- **Entities:** the loaded entity list gives each one's name, position and template. Enemies, friendly NPCs, wisps and other players' duel circles can all be told apart. Distant ones are placeholders until they load in full. Before a fight, an enemy's behaviour template says its level, school, whether it's a boss, and its starting health.
- **The UI:** the root window's tree, each window with a name, a visible flag, a disabled flag and often text. Dialogs, NPC menus, message boxes, the spellbook's pages, the HUD's buttons (and their tooltips and cooldown timers) are all in it, by name. A window's visible flag ignores its parents.
- **Battle:** the combat members (health, alive or dead, name, school, pips), their hanging effects (shields, wards, traps, with school and size), their resistances by school, and the cards in hand (name, spell type, school, pip cost, whether castable). Accuracy and full effects are on each card's spell template.
- **Items:** worn equipment and the backpack are behaviours on the client object, each item with a template giving its name, slot, stats and requirements. WizWalker has no readers for these, so find the fields with a wiztype dump. Item stat values are lookups the game resolves; measure a few to learn the mapping.
- **The deck and the spellbook:** the deck behaviour, and the spellbook's tabs (character, inventory, deck, quests, maps and more) as UI windows. The quest page can switch the active quest without the Q key.

## The client's own log

The client writes a log file in its folder, large and growing, so read only its end. It says what memory doesn't:

- the server connection dropping and reconnecting;
- every move the character sends in battle, so a click that didn't take shows as a round with no move;
- combat damage and health as they happen, written up to a minute late in buffered blocks, so read it after a battle, not during.

## Message boxes

- **In battle, the game's message boxes open under the planning window,** not on top, and take every click while open. The flee confirmation and the idle warning are among them.
- **Requests from other players** (friend, trade, duel and so on) are message boxes with their own titles and Yes and No buttons. Tell them apart by title before answering anything.
- **The game's own notices** have a single OK button.

## Zone files

Each zone's data is in the game's archives:

- **Collision data:** walls and walkable surfaces, from which a walk grid can be built. It misses some ramps and stairs, and props placed in the zone (tents, trees, crates) aren't in it.
- **Placed objects:** the zone's objects (gates, quest objects, signs, props), with names and tags that match quest goals. Their models give the props' footprints.
- **The nav graph:** waypoints over walkable ground, which link levels the collision data leaves apart.
- **Volumes:** trigger and teleport volumes. Shop and house doors are among them, and some quest visits count when the character walks into one named after the quest.
- **Patrol paths and spawn data:** named after their enemies, and present for friendly NPCs too.
- **Locale files:** turn title, goal and enemy keys into display text.

The zone files don't say where street doors lead. Learn those links by walking.
