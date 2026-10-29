# WizardTraining

A head start for an AI agent that will build its own Wizard101 bot. It holds what one supervised character's unattended play, from level 1 to level 15 and counting, taught about the game and about automating it: the lessons, the safety rules that kept the account and other players safe, where the game keeps the data a bot needs, and what each stretch of play found.

It is not an implementation or a configuration guide. An agent should read it, then work out its own way to the goal, in whatever language and with whatever tools suit it. Everything here was learned the hard way, so an agent starting from nothing doesn't have to.

> **Unofficial, and at your own risk.** This project is not affiliated with or endorsed by KingsIsle Entertainment. Wizard101's terms of service restrict third-party programs and automation, and building or running a bot may break them and put your account at risk. You are responsible for how you use it. Nothing here bypasses access controls, CAPTCHAs or anti-cheat, logs in for you, or buys, trades or chats.

## What's here

- **[docs/lessons-learned.md](docs/lessons-learned.md):** the core. Lessons by topic, each as what happened, what it taught and what to try: reading the game, moving and pathfinding, quests and dialogs, fighting, health and refills, travel, doors and dungeons, popups, and spotting opportunities.
- **[docs/symptoms.md](docs/symptoms.md):** what a run going wrong looks like, the causes found in play for each symptom, and what to check first.
- **[docs/safety.md](docs/safety.md):** principles for a bot that plays on a real account among real players, under an operator's supervision.
- **[docs/game-data.md](docs/game-data.md):** what the game exposes, in memory, in its zone files and in its own log, and where to look for it.
- **[docs/architecture.md](docs/architecture.md):** design advice that held up: keep decisions apart from game access, steer in a closed loop, log why, measure every rule.
- **[docs/retros/](docs/retros/):** what each five-level stretch of play found, what worked, what didn't and what was left open.
- **[CHANGELOG.md](CHANGELOG.md):** what changed in this guidance, and why.

## How to use it

1. **Read [safety.md](docs/safety.md) first,** and agree its limits with your operator before the bot touches the game.
2. **Read [lessons-learned.md](docs/lessons-learned.md) before designing anything.** Most of what goes wrong in a first unattended run is already in it.
3. **Use [game-data.md](docs/game-data.md) as a map,** not as values. The game updates often, and memory layouts and window paths change with it, so check everything against the client in front of you.
4. **When a run goes wrong, start at [symptoms.md](docs/symptoms.md).** The same few causes come back.
5. **Build your own way, and measure it.** Then add what you learn back here, as advice someone else can use without your code.

## Status

Version 0.4.0 (in progress). Its lessons come from one character played on Windows 11 from level 1 to 15 in Wizard City and Krokotopia, 2026-10-26 to 29, with WizWalker 1.8.2 as vendored in Deimos.

**From 0.4.0, WizardTraining is a guidance-only framework.** The implementation that played these runs (the play loop, its scripts and the zone-specific logic) has been removed from this repository and is no longer maintained here. The tags of earlier releases still hold it as it was. What remains is the framework: the rules, the guidance, and the lessons learned in play.

## Contributing

Work on a branch and open a pull request into `main`. A change should help an agent building its own bot, and needs no particular codebase to make sense: no module or function names, no tuned constants presented as settings, and no paths from your own machine (a check rejects those). Say what was seen in the game and what wasn't, and add an entry to [CHANGELOG.md](CHANGELOG.md) with its reason.

### Releasing

A release closes a stretch of play, usually five levels.

1. **Write the findings.** Add a retro to [docs/retros/](docs/retros/): what worked, what failed and why, and what is still unverified. Move the general lessons into [docs/lessons-learned.md](docs/lessons-learned.md), written as advice.
2. **Close the CHANGELOG.** Turn `Unreleased` into the new version and date, and update the version in this README's Status.
3. **Open a release pull request** into `main`, and wait for the maintainer to approve and merge it.
4. **Tag the merge on `main`** with the version (`vX.Y.Z`) and push the tag.
5. **Create the GitHub release for the tag.** Base its notes on the retro, and link the retro and the CHANGELOG at the tag, not on `main`.

## Credits and licence

- The lessons were learned with [Deimos-Wizard101](https://github.com/Deimos-Wizard101/Deimos-Wizard101) (GPL-3.0) and its vendored [WizWalker](https://github.com/Deimos-Wizard101/Deimos-Wizard101/tree/main/libs/wizwalker) (GPL-3.0-or-later). Their readers, walk grid and combat maths are the place to start for an agent working in Python.
- Licensed under the GNU General Public License v3.0 or later. See [LICENSE](LICENSE).
