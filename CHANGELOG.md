# Changelog

What changed in this guidance, and why. Say what was seen in the game and what wasn't.

Entries up to 0.3.0, when this repository also held an implementation, are in [CHANGELOG.md at v0.3.0](https://github.com/APeachyPurplePlatypus/WizardTraining_Prod/blob/v0.3.0/CHANGELOG.md).

## Unreleased

### Removed

- **The implementation.**
  - **What:** the implementation that played these runs (the play loop, its scripts, its tests and examples, and the zone-specific logic) has been removed from this repository and is no longer maintained here. The tags of earlier releases still hold it as it was.
  - **Why:** the operator, 2026-10-29: the framework "was going to be light wight and allow the agents to determine their own implimentation", and "we give general advice and guidelines that we have learned though our playing and development mistakes. but it isn't meant to be a configuration or implementation guide, An agent is supposed to be able to read it, and problem solve on their own how they would come complete the goal."

### Changed

- **Every document is rewritten as guidance** (README, lessons learned, safety, game data, architecture, the level 10 to 15 retro).
  - **What:**
    - Module, function and constant names, command-line flags and local paths are gone.
    - Lessons say what happened, what it taught and what to try.
    - Safety is a set of principles to agree with an operator, without one account's approvals.
    - Game data describes what the game exposes and where to look, without exact offsets or window paths, which change with game updates.
    - Architecture is design advice.
  - **Why:** an agent building its own bot, in any language, should be able to use every line without a particular codebase in hand.
- **The pull request template** asks what a change teaches and what was seen in the game, instead of about tests.

### Added

- **Lessons from 2026-10-28 and 29**, written as advice:
  - closed-loop steering at 100 Hz (look-ahead cornering, braking by measured speed, the turning circle, live pursuit of moving targets, a nearer horizon in crowded streets);
  - discarding to dig for better cards;
  - acting promptly after a battle;
  - "a miss is not immunity" and spending idle pips;
  - never marking where a fight just happened, and reading the Recall timer;
  - learning where travel lands with care;
  - stopping only where no enemy walks;
  - checking that waiting gives something back;
  - mounts;
  - spotting opportunities, and the Quest Friend Finder.
  - **Why:** each came from a real failure or measurement in play. The fight-length and mark lessons followed seabed fights of 11 to 12 rounds costing 43 to 53% of health, and two Recalls that landed in fights.
- **A page of symptoms and their likely causes** (`docs/symptoms.md`).
  - **What:** what a run going wrong looks like (keys that change nothing, creeping toward a target, turns that repeat at once, a use that "did nothing", numbers that jump, doors that aren't there), with the causes found in play for each, and what to check first.
  - **Why:** the same few causes came back again and again in two days of play, and each took a stop and a read of the logs to find. An agent starting from nothing gets there faster from the symptom.
- **Dungeon lessons from Sunken City**, in the lessons' Dungeons section and the symptoms page:
  - side rooms are the same dungeon;
  - walking back in through the door can start a new instance;
  - a flee's move to the hub comes after the battle ends;
  - a walk-up that crosses a door.
  - **Why:** in one afternoon, Sunken City's progress was lost twice: after a defeat in a side room, and after a flee. Both times the run walked in through the door instead of using the return button.
- **Lessons from level 16 in Wizard City**, written as advice:
  - a stats read can be another player's, and tools that hook the game share its hooks;
  - walk data is flat, so compare heights before closing in on a target;
  - other players' fights are obstacles that move on: back off and wait;
  - the game counts goals late and step by step, so judge a use by which goal closed;
  - an arrow at a door means the target is behind it;
  - retry set-aside quests before leaving a world;
  - a goal's tag can be in an object's template rather than its name;
  - a flee can move the character, so learn doors only from walks;
  - read the turn order, count damage over time, know when a fight is lost on heals, and when a shield beats an attack;
  - heals left in hand at a fight's end are wasted.
  - **Why:** each came from a stall, a loss or a measurement in play on 2026-10-29: a four-minute creep under a balcony NPC, eleven refused approaches in a second beside another player's duel, shells and a book pedestal that worked but were logged as misses, a door learned from a flee, three losses to stronger groups in Sunken City, and a heal left unused in 32 of 38 wins.
  - **Verified:** in play, except the shield ordering, which is not yet seen in play.
- **What patrol and spawn data say about safe ground** (game data, lessons learned).
  - **What:** spawn data tells enemy paths from wisp, reagent and chest paths better than path names do; a path's nodes come from its own list, in any order; sidewalks are safer than streets but not safe; wisp paths are where to look for wisps.
  - **Why:** a proposal to treat sidewalks and wisp paths as safe was checked against the game files of 19 zones. The spawn data part held and cut the ground priced as near enemies by 33 to 59% in the five streets measured; the safe-sidewalk part didn't, since in four busy streets a quarter to half of the sidewalk lay within 600 units of an enemy path.
  - **Verified:** against the installed game files and offline route planning in nine zones. Not yet seen in play.
- **A check that no path from someone's own machine is committed** (`.github/workflows/no-local-paths.yml`).
  - **What:** on every push and pull request, the tracked files are searched for Windows user folders, home folders and cloud-synced document folders. Any match fails the check and is listed.
  - **Why:** a path from a contributor's machine tells readers their user name and how their machine is laid out, and helps no one else.
  - **Verified:** the pattern passes the current files and flags a sample Windows user folder.
