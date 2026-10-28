# Safety model

The framework acts in a live online game, on a real account, among real players. These rules keep it predictable and keep it from harming the account, other players, or the operator's privacy. Changing one is a deliberate decision: record why in [CHANGELOG.md](../CHANGELOG.md).

## The account and the operator

- **No credentials.** The operator logs in and picks an existing character. The framework never reads, stores or types a password, and it stops at any login, CAPTCHA or access challenge.
- **No spending or trading.** It never opens the Crown Shop (Ctrl+S is not an allowed key) and never trades, buys or sells.
- **Potions only with permission.** With `--use-potions`, the wizard drinks health potions it already has when out of battle and below 40% health. It never buys potions or refills. Without the flag it never touches them, because consumables stay off by default.
- **Gear only with permission.** With `--wear-gear`, the wizard equips better items it already has, in zones without enemies. It clicks only the HUD's spellbook button, the book's Inventory tab, a category tab, the item, Equip and the book's Close button: never the trash, recycle or quick-sell buttons. If a message box appears, the run stops and leaves it for you. Without the flag the wizard's outfit stays as you left it.
- **No chat.** The chat hook is never installed and nothing is typed into chat.
- **Your responsibility.** Automation may break Wizard101's terms of service. The README says so, and so should anything you build on this.

## How the character moves

- **Keyboard only:** W, A, S and D for walking and turning, X to interact, Space for dialogs (`keys.ALLOWED_KEYS`). Any other key raises `RefusedKey`.
- **No teleport by the framework, and no speed changes.** No writes to position, facing or speed. The game's own teleporters (doors, zone gates, in-zone teleport volumes such as Triton Avenue's "Tele Up") are walked into like a player would; that is not a teleport the framework performs. WizWalker's `goto` writes the facing, so it is not used. The movement-teleport hook is never installed.
- **The game's own travel buttons are allowed (operator's decision, 2026-10-28: "Teleporting only refers to using deimos, you are allow to teleport using in game tools").** The ban above is on Deimos and WizWalker moving the character. With `--use-travel-buttons`, a mana refill in a street may press, on the HUD, Mark Location (`MarkButton`), Go to The Commons, the world's hub (`GoHomeButton`), and Recall Location (`RecallButton`), by the mouseless cursor, and nothing else there: never `GotoDormButton` or `ResumeInstanceButton`. Each press is checked by the tooltip the button shows (`gametravel.py`), Recall is used only once mana is back, and a button that is cooling down (its timer shows) is not pressed. In the game, Mark and Recall each cost about 5 mana and Go to The Commons is free.
- **Clicks** use WizWalker's mouseless cursor, only for card, dialog and NPC-menu buttons, the HUD's potion button when potions are allowed, and the spellbook's inventory buttons listed above when gear is allowed. The real mouse does not move.
- **The world gate (operator's instruction, 2026-10-28: "move on to krok"):** at the Spiral Door, X opens the Spiral Map; with `--leave-world` the framework clicks the button of the world the active quest leads to (`wbtn<World>`) and Go To World, and otherwise Exit (`worldgate.py`). Going through world gates was always part of natural navigation (AGENTS.md); these are the clicks it takes.
- **Quest book clicks (operator's decision, 2026-10-28):** with `--side-quests` the framework may click the HUD's spellbook button, the book's Quest tab, the quest page's Previous and Next buttons, a quest's Activate button and Close; never Hide or abandon; no keys. The code is `questbook.py`, and a test keeps the clicks to this list.
- **No detection evasion.** The framework does not try to look human. It is honest automation within the limits above.

## Other players

- **Duel circles are no-go areas.** Routes keep 900 units away from them, and straight lines through them are refused. Enemies standing in one are never targets.
- **No chat, no trades, no following.**
- **Endorsements are Friendly.** After another player shares a battle, the game asks to endorse them, and the window holds the keyboard until answered. The framework answers Friendly, never reads the player's name, and logs only that it endorsed. To decline instead, point the "Endorse a Wizard" entry of `ui.KNOWN_POPUPS` at the close button.

## The game client

- **Only the hooks that reading needs** are installed: player, player stats, client, root window and quest arrow. Clicks add the render-context and mouseless-cursor hooks.
- **Hooks are always removed** (`session.attached`). A killed process cannot remove them, so stop runs with the STOP file only.

## Bounded runs

`progress.Limits` bounds every run:
- time, turns and battles;
- turns without progress, step-aways, loading waits and immobile waits for enemies;
- defeats, of which none are allowed by default.

Battles have their own round, phase and total time limits. Route planning gives up after 2 s, and a route after 180 s. Unexpected situations raise `StopRun` with a reason in the report.

## Privacy

- **Reports stay local.** They are saved under `runtime/`, which Git ignores. They hold positions, zone names, quest keys and card names.
- **No dialog text in reports.** NPCs often say the character's name, so reports keep page counts and lengths only.
- **No screenshots.** The framework takes none. If you add them for troubleshooting, capture only the game window, keep the images local and never commit them: they can show other players' names and chat.
