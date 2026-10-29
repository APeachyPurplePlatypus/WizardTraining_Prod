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
- **A check that no path from someone's own machine is committed** (`.github/workflows/no-local-paths.yml`).
  - **What:** on every push and pull request, the tracked files are searched for Windows user folders, home folders and cloud-synced document folders. Any match fails the check and is listed.
  - **Why:** a path from a contributor's machine tells readers their user name and how their machine is laid out, and helps no one else.
  - **Verified:** the pattern passes the current files and flags a sample Windows user folder.
