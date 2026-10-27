# Safety model

The framework acts in a live online game, on a real account, among real players. These rules keep it predictable and keep it from harming the account, other players, or the operator's privacy. Changing one is a deliberate decision: record why in [CHANGELOG.md](../CHANGELOG.md).

## The account and the operator

- **No credentials.** The operator logs in and picks an existing character. The framework never reads, stores or types a password, and it stops at any login, CAPTCHA or access challenge.
- **No spending or trading.** It never opens the Crown Shop (Ctrl+S is not an allowed key) and never trades, buys or sells.
- **Potions only with permission.** With `--use-potions`, the wizard drinks health potions it already has when out of battle and below 40% health. It never buys potions or refills. Without the flag it never touches them, because consumables stay off by default.
- **No chat.** The chat hook is never installed and nothing is typed into chat.
- **Your responsibility.** Automation may break Wizard101's terms of service. The README says so, and so should anything you build on this.

## How the character moves

- **Keyboard only:** W, A, S and D for walking and turning, X to interact, Space for dialogs (`keys.ALLOWED_KEYS`). Any other key raises `RefusedKey`.
- **No teleport and no speed changes.** No writes to position, facing or speed. WizWalker's `goto` writes the facing, so it is not used. The movement-teleport hook is never installed.
- **Clicks** use WizWalker's mouseless cursor, only for card, dialog and NPC-menu buttons, and for the HUD's potion button when potions are allowed. The real mouse does not move.
- **No detection evasion.** The framework does not try to look human. It is honest automation within the limits above.

## Other players

- **Duel circles are no-go areas.** Routes keep 900 units away from them, and straight lines through them are refused. Enemies standing in one are never targets.
- **No chat, no trades, no following.**

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
