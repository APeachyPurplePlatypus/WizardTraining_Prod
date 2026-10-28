# WizardTraining

A starting framework for Wizard101 agents. It reads the game through [WizWalker](https://github.com/Deimos-Wizard101/Deimos-Wizard101/tree/main/libs/wizwalker) and plays main quests the way a player does: walking with the keyboard, talking to NPCs, and fighting the battles quests require.

It comes out of one character's unattended run from level 1 to level 5 in Wizard City. Every rule and limit in it was added because something went wrong in the real game; [docs/lessons-learned.md](docs/lessons-learned.md) records what and why. It is meant as a base for other agents and models to build on, not a finished bot.

> **Unofficial, and at your own risk.** This project is not affiliated with or endorsed by KingsIsle Entertainment. Wizard101's terms of service restrict third-party programs and automation, and using this framework may break them and put your account at risk. You are responsible for how you use it. It does not bypass access controls, CAPTCHAs or anti-cheat, does not log in for you, and does not buy, trade or chat.

## What it does

- **Reads state:** zone, level, health, mana, position, battle/dialog/loading flags, the quest journal (main quests told apart from side quests), the active goal and the quest arrow, and nearby enemies, friendly NPCs and other players' duels.
- **Moves like a player:** turns with A/D and walks with W, steering on the move under a 20 Hz watcher. No teleport by the framework, no speed changes, no writes to position or facing.
- **Plans routes** over the zone's walk data: Deimos's collision walk grid, then the zone.nav waypoint graph, then a straight line. Routes cost more near enemies and never cross another player's duel circle.
- **Plays main quests:** goal types bounty, persona (talk), waypoint (including doors to other zones) and usage (use an object). Follow-up dialogs hand out the next main quest.
- **Fights** with a replaceable combat policy. The default heals when low, saving pips for a heal it cannot afford yet; otherwise it casts the affordable attack whose school the target's shields, wards, traps and resistances let through best.
- **Stops for the operator** whenever it is unsure: a non-main quest, an unknown goal type, an optional quest offer, a defeat, a popup holding the keyboard, turns without progress, or any limit.

## Status

Version 0.3.0. Played on Windows 11 with one character from level 5 to 15 in Wizard City (the Commons, Olde Town, Unicorn Way, Triton Avenue and its underwater zone, Cyclops Lane, Firecat Alley, Colossus Boulevard, Golem Court and their houses, towers and instances) and in Krokotopia's Pyramid on 2026-10-26 to 28, with WizWalker 1.8.2 as vendored in Deimos at commit `d7ef56eb`. The game updates often, and memory layouts and window paths can change with it. See [CHANGELOG.md](CHANGELOG.md) for what each release changed and why.

## Setup

You need Windows, an installed Wizard101 client, Python 3.13 and Git.

```powershell
git clone https://github.com/Deimos-Wizard101/Deimos-Wizard101.git
python -m venv .venv
.venv\Scripts\python -m pip install .\Deimos-Wizard101\libs\wizwalker numpy shapely
git clone https://github.com/APeachyPurplePlatypus/WizardTraining_Prod.git
.venv\Scripts\python -m pip install -e .\WizardTraining_Prod
$env:WIZARDTRAINING_DEIMOS = "$PWD\Deimos-Wizard101"
```

- **WizWalker** comes from the copy vendored in Deimos (`libs/wizwalker`), which tracks the current game better than the old PyPI release.
- **Deimos** is not installed as a package. `WIZARDTRAINING_DEIMOS` points at the checkout so the collision route method can use its walk grid (`src/collision.py`, `src/collision_math.py`), which needs numpy and shapely. Without it, routes use the zone.nav graph.
- **Placed objects (optional, recommended).** Tents, trees and crates are not in a zone's `collision.bcd`, so routes walk into them. Deimos can read their footprints from the game's models if `katsuba` 0.4, `wiztype` and Deimos's own `kinif` are installed. `kinif` is a Rust extension with no published wheel: build it with [rustup](https://rustup.rs) (the GNU toolchain needs no Visual Studio) and `maturin`:

  ```powershell
  .venv\Scripts\python -m pip install "katsuba==0.4.0" "wiztype>=0.1.12" "maturin>=1,<2"
  cd Deimos-Wizard101\libs\kinif
  ..\..\..\.venv\Scripts\maturin build --release --target x86_64-pc-windows-gnu -i ..\..\..\.venv\Scripts\python.exe
  ..\..\..\.venv\Scripts\python -m pip install (Get-ChildItem target\wheels\kinif-*.whl)
  ```

  The first time, `wiztype` reads a type list from the running game client (read-only, about 20 s) and caches it for that game version. Without these packages, the framework works as before.
- **Reports** go to `./runtime`, or to the folder in `WIZARDTRAINING_RUNTIME`.

## Use

Start the game, log in yourself, choose an existing character, and stand somewhere quiet. Then:

```powershell
python -m wizardtraining probe
python -m wizardtraining play --level 7 --minutes 25 --battles 20
```

- `probe` reads once without sending keys. Run it first.
- `play` plays main quests until the level, the time or the battle limit is reached, or until something needs you. At a level, time or battle limit it plays on, for up to 15 minutes, until no enemy is nearby, so the wizard is not left idle where a passing enemy can pull it into a fight. The STOP file stops it at once. With `--side-quests` it accepts every quest offer, side quests included, and plays whichever quest is active. When the main quest would lead to another world, it first switches to the current world's side quests through the spellbook's quest page, the one ready to hand in first, and stops when none is left, because the current world's side quests come first; `--leave-world` follows the main quest instead.
- Defeats and stuck walks do not stop a run by a count: each time something fails again in the same situation, the next strategy not yet tried there is used (`strategies.py`: for a lost fight, heal earlier, the most dangerous enemy first, or saving pips for bigger cards, each starting with full health and mana; for a stuck walk, the nav graph or the collision data first, forgetting recorded obstacles, waiting for the way to clear, or the Commons and back). The run stops for you only when every strategy has failed there. `--max-defeats N` puts a cap back on defeats.
- `--approve-quest "<title>"` lets it accept a quest an NPC's menu offers by title, once you have checked it is a main quest.
- `--use-travel-buttons` lets a mana refill in a street use the game's own buttons: Mark Location before leaving, Go to The Commons (the world's hub, where mana comes back), and Recall Location back to the mark once mana is up. Each costs a few mana (Mark and Recall about 5), nothing is moved by the framework, and a button that is cooling down is not pressed.
- `--use-potions` lets it drink health potions it already has when health is low out of battle. It never buys any.
- `--wear-gear` lets it wear the best gear in its backpack. It checks after each level-up or new loot, and only with no enemy nearby, because the spellbook stays open a few seconds per item. What counts as best is `gear.py`: max health first, then max mana, then resistance to every school, then the wizard's own school's damage and accuracy. It equips only hats, robes, shoes, athames, amulets and rings; wands, decks, pets and mounts are left alone. It never sells, recycles or throws anything away.
- `--edit-deck` lets it put spell cards into the equipped deck and take them out by the deck rules (`decks.py`): an Extract spell while a quest needs an essence, then heals, the strongest hits, and stuns, up to each card's copy limit and the deck's capacity, which it learns from the Deck page. Only out of battle with no enemy nearby; every card moved is logged with its reason in `runtime/deck-changes.jsonl`.

To stop a run, run this from a second terminal:

```powershell
python -m wizardtraining stop
```

Do not use Ctrl+C, close the window, or kill the process. A run that dies without removing its hooks leaves them patched into the game, and nothing can hook again until the game is restarted.

Every run saves a JSON report in the runtime folder, and its `stopped` field says why the run ended. While it runs, `events-<started>.jsonl` in the same folder records each battle, round, walk, rest, dialog and zone, level or quest change as it happens, so you can follow it from facts.

## Building on it

Read [docs/architecture.md](docs/architecture.md) for how a turn works, [docs/safety.md](docs/safety.md) for the rules, [docs/game-data.md](docs/game-data.md) for the game data you can read, and [docs/lessons-learned.md](docs/lessons-learned.md) for the pitfalls already paid for.

### Rules it keeps

Keep these in anything you build on it:

- **The operator logs in.** Never handle passwords or account details. Stop at any login, CAPTCHA or access challenge.
- **Move like a player.** Send only the keys in `keys.ALLOWED_KEYS`. No teleport by the framework, no speed changes, no writes to game values, and no Deimos feature that teleports. Check its source before enabling one. The game's own travel buttons are another matter (see [docs/safety.md](docs/safety.md)): with `--use-travel-buttons`, a mana refill may press Mark Location, Go to The Commons and Recall Location.
- **No detection evasion.** Nothing that tries to look human or hide automation.
- **Main quests by default.** Leave other players alone: never enter a duel circle, never chat, trade or buy.
- **Stop instead of guessing.** Raise `progress.StopRun` with a clear reason.
- **Bound every loop.** Add limits to `progress.Limits`.
- **Never kill a run.** Use `python -m wizardtraining stop`.
- **Keep reports, screenshots and dialog text out of Git.** They can name the character and other players.

### Where to extend

- **Combat:** write a `policy.CombatPolicy` and pass it as `loop.play(..., combat_policy=...)`. See [examples/custom_combat_policy.py](examples/custom_combat_policy.py).
- **Quest offers:** write a `policy.OfferPolicy`, for example to take side quests.
- **New goal types:** subclass `loop.QuestLoop` and extend `goal_handlers()`. See [examples/custom_goal_handler.py](examples/custom_goal_handler.py). First learn what the goal needs with `probe` and [examples/read_state.py](examples/read_state.py).

Put new logic in the modules that never touch the game (`routes`, `targets`, `policy`, `progress`, `state`, `geometry`) whenever you can. The offline tests need neither the game nor WizWalker:

```powershell
python -m unittest discover -s tests
```

### Before you call a change done

Work on a branch and open a pull request into `main`. CI runs the offline tests on it, and the pull request template asks for the points below.

1. Run the offline tests.
2. Run `probe` against the game, to check the reads still work on the current game build.
3. Run a short, bounded `play` and read its report.
4. Add the change to [CHANGELOG.md](CHANGELOG.md) with its rationale: why it was needed, and what was and was not verified in the game. The next person needs to know why the framework is the way it is.

## Credits and licence

- Built on [Deimos-Wizard101](https://github.com/Deimos-Wizard101/Deimos-Wizard101) (GPL-3.0) and its vendored [WizWalker](https://github.com/Deimos-Wizard101/Deimos-Wizard101/tree/main/libs/wizwalker) (GPL-3.0-or-later). The enemy test, dialog window paths and spell-type card reading follow Deimos; the walk grid is Deimos's, used at run time from your checkout, not copied here.
- Licensed under the GNU General Public License v3.0 or later. See [LICENSE](LICENSE).
