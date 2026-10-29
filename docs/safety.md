# Safety

A Wizard101 bot acts in a live online game, on a real account, among real players. These principles kept one such bot predictable, kept it from harming the account or other players, and kept the operator in charge. They're written for an agent designing its own bot. Agree the details with your operator before the bot touches the game, and record every change to them with its reason.

## The operator decides

- **Default-deny, with an allow-list the operator grows.** Start with the smallest set of keys and clicks the bot needs. Each new kind of action (a new button, a new key, a new kind of box answered) is the operator's call, recorded with their words and the date.
- **Approval is specific.** "Yes" to answering one kind of box isn't "yes" to every box. Keep each approval as narrow as it was given, and widen it only when the operator does.
- **Stop instead of guessing.** When something unknown happens (an unrecognised window, a goal type never seen, a quest it can't classify) the bot should stop with a clear reason, or park that work and move on, rather than improvise.
- **Measure, then report.** The operator can't watch every minute. Log what the bot did and why, in facts (battles, walks, zone changes, XP), so a run can be followed and judged afterwards.

## The account

- **No credentials, ever.** The operator logs in and picks an existing character. The bot never reads, stores or types a password, and stops at any login, CAPTCHA or access challenge.
- **No spending or trading** without the operator's explicit approval: no Crown Shop, no trades, no buying, selling or renting. Treat gold and crowns as the operator's.
- **Consumables and gear off by default.** Drinking potions it already has, wearing better gear it already owns, editing its deck, or spending training points are each a separate permission. When they're allowed, use only the clicks they need, check each click's result, and never touch trash, recycle, quick-sell or discard-item buttons.
- **No chat.** Don't install a chat hook, and don't type into chat.
- **Your responsibility.** Automation may break the game's terms of service. Say so in anything you publish.

## How the character moves

- **Like a player, by keyboard.** Walk and turn with the movement keys, and interact and page through dialogs with their keys. Refuse any key not on the allow-list. Beware keys that open windows: Q opens the quest book.
- **No teleport by the bot, and no speed changes.** Never write position, facing or speed to memory, and don't use a tool feature that does (check a library's source before enabling one). Walking into the game's own teleporters, doors and zone gates is what a player does, so it's allowed.
- **The game's own travel buttons are the player's tools.** Mark, Recall, Go Home, a dungeon's return button and the world gate's map are ordinary play, used by clicking them as a player would, once the operator agrees. Check a button is the one you mean (by its tooltip, for instance) and that it isn't cooling down before pressing it.
- **Clicks without the real mouse.** A mouseless cursor that clicks named windows keeps the operator's mouse free and makes every click a deliberate, listed action.
- **No detection evasion.** Don't try to look human. Be honest automation within the limits above.

## Other players

- **Leave them alone.** Never enter another player's duel circle (keep routes well clear of them), never target an enemy standing in one, and don't follow, chat with or trade with anyone.
- **Never answer another player's request.** Friend, trade, duel, group and teleport requests are the operator's. Decline or leave them, as agreed.
- **Features that bring in other players wait for the operator.** Group help such as the Quest Friend Finder could speed progress, but it involves real people.
- **Shared battles end with an endorsement window** that holds the keyboard. Answer it as agreed with the operator, without reading or logging the other player's name.

## Boxes and popups

- **A game box whose only button is OK can be closed with it,** with its title and text logged, once the operator agrees. A box with Yes and No is a decision. Answer one kind only when the operator has said how (a dungeon-entry box, for instance).
- **Popups can hold the keyboard or take every click.** If keys stop working, look for an open window before anything else.

## The game client

- **Install only the hooks you read from,** and always remove them on the way out, however the run ends.
- **Never kill a run.** A process killed with its hooks in leaves them patched into the client until the game restarts. Give the bot a stop signal it checks every tick and between turns, and stop it at a turn's boundary in a zone with no enemies.

## Bounded runs

- **Bound everything:** time, turns, battles, rounds, waits, searches, and turns without progress. A loop without a bound is a bot standing still for hours.
- **When something fails, change strategy.** Repeating the same failed action doesn't converge. Try the next approach not yet tried in that situation, log it, and stop for the operator when every approach has failed there.

## Towers and dungeons

- **Know what leaving costs.** A dungeon in this game keeps its progress for 30 minutes after leaving. A tower loses its progress when left partway. Plan refills around that, and don't leave a tower partway.

## Privacy

- **Keep run output local and out of version control.** Reports, logs and screenshots hold positions, zone names, and often the character's name. NPCs say it in dialog, so keep dialog page counts, not text, in reports.
- **No paths from your own machine** in anything you publish. Use placeholders or settings instead.
- **Screenshots only when nothing else works.** Capture the game window only, keep the images local, and never commit them: they can show other players' names and chat.
