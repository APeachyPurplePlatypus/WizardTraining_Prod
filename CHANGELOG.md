# Changelog

Every change, enhancement or addition is listed with its rationale, so later contributors know why the framework is the way it is. Say what was verified in the game and what was not.

## Unreleased

### Fixed

- **Routes avoid collision walls.**
  - **What:** the "collision" method's free area is now the walkable navmesh minus Deimos's height-aware collision walls (`zone_bcd_walls`), padded by `navigation.WALL_CLEARANCE` (30 units). Grid cells outside it count as unwalkable, and merged legs, including "nav" legs, must stay inside it.
  - **Why:** Deimos's walk grid and `straight_path_walkable` check only the navmesh, on purpose: Deimos walks through some volumes that only block teleports. In the Commons, though, the walls are trees, fences and buildings. Every route to the Ravenwood door walked into them, and obstacle memory alone just boxed the wizard in. All 40 points where the wizard got blocked lay within 100 units of a collision wall. With the walls subtracted, the wizard's position and the door are in one connected free area, and the planned route goes around the east side.
  - **Verified:** offline, the route from the stuck spot (about -678, -786) to the door plans in under 0.1 s, and every leg stays in the free area. In the game, the next run walked from that spot to the Ravenwood door, went through it, and talked to the quest NPC.
  - **Not verified:** zones with several floors. The walls are flattened to the map, so a wall on another floor could block a route. A padding wider than 30 units cut the Commons' free area into pieces.

## 0.1.0 (2026-10-26)

First public release: the prototype scripts behind one character's unattended level 1 to 5 run, restructured into a package that other agents can build on.

### Added

- **`wizardtraining` package.**
  - **What:** session, state, movement, navigation, entities, quests, dialog, combat and loop modules; a command line (`probe`, `play`, `stop`); and three examples.
  - **Why:** the prototype was a folder of scripts with machine-specific paths. A package with one entry point is something others can install and extend.
- **Split between "decide" and "do" modules.**
  - **What:** route search, target choice, combat and offer policies, run limits and progress need no game access, and an import-boundary test keeps it that way.
  - **Why:** most bugs in the prototype were decision bugs: progress counting, threat judgement, card choice. Logic that runs without the game can be tested in seconds, on any OS, by any agent.
- **Replaceable policies.**
  - **What:** `CombatPolicy` (which card to play) and `OfferPolicy` (what to do with a quest offer), and goal handlers through `QuestLoop.goal_handlers()`.
  - **Why:** these are the parts other agents will most want to change. Keeping them separate means a new strategy cannot accidentally break walking, hooks or limits. The battle code validates a policy's choice and passes instead of acting on an invalid one.
- **Allowlist of keys.**
  - **What:** `keys.ALLOWED_KEYS` holds W, A, S, D, X and Space. Anything else raises `RefusedKey`.
  - **Why:** in the prototype, the forbidden keys (Q, End, Home, Escape, Ctrl+S, Ctrl+T) were only a convention, and Q was sent once and opened the quest book. An allowlist fails safe for keys nobody has thought about yet.
- **Settings from environment variables.**
  - **What:** `WIZARDTRAINING_DEIMOS` and `WIZARDTRAINING_RUNTIME`.
  - **Why:** the prototype hard-coded a local Deimos path and output folder.
- **Documentation:** README (setup, use, the rules to keep, where to extend, and an unofficial-project and terms-of-service notice), plus architecture, safety and lessons learned under `docs/`.
  - **Why:** the main value of this release is what was learned. The docs record each rule's reason, so nobody has to rediscover it the hard way.
- **Offline tests:** 67 tests on the standard library's `unittest`.
  - **Why:** they need no extra packages and run on the Python every contributor already has.

- **Obstacle memory.**
  - **What:** when walking stalls, the point just ahead is recorded as an obstacle for that zone. Later routes treat it as a small no-go area (`OBSTACLE_RADIUS`), and the next route method on the same trip already plans around it. Obstacles near a trip's destination are ignored, so bumping into an NPC never makes it unreachable. Finding one counts as progress, capped by `Limits.max_obstacles_per_zone`.
  - **Why:** the first smoke run of this package in the Commons walked into something the zone's walk data calls clear. Every route method then aimed at the same spot, sidestepped four times and gave up, until the run stopped on turns without progress. The prototype never met this because its routes in the Commons happened to avoid that spot. Walk data is a map, not the territory; the wizard has to learn from what it bumps into.
- **Smoke-run fix:** `progress.travel_outcome` takes the walk's stop reason rather than the trip, after a `trip=` detail clashed with its own parameter and crashed the first bounded run. A regression test covers it.

### Changed from the prototype

- **Reports keep dialog page lengths, not page text.**
  - **Why:** NPCs address the character by name, and reports get shared when people ask for help.
- **The collision route method always uses the framework's own bounded A* over Deimos's walk grid.** The prototype used Deimos's `find_walk_path` when there was nothing to avoid.
  - **Why:** one code path, always bounded by the 2 s planning limit, which the prototype added after an unbounded search stalled a walk.
- **An ignored turn key raises `KeysIgnored`.** The prototype searched each turn's report text for a phrase.
  - **Why:** a typed exception cannot be missed by a reworded message.
- **Turn calibration is kept per client, not in a module-wide class.**
  - **Why:** it is a property of the game window being driven.

### Verified, and not

- **Verified in the game with the prototype scripts:** everything in [docs/lessons-learned.md](docs/lessons-learned.md), from level 1 to level 5 in Wizard City.
- **Verified with this package:** the 67 offline tests (with and without WizWalker installed) and `python -m wizardtraining probe` against the live game. Three bounded smoke runs of `play` in the Commons, walking toward the Ravenwood door: the first found the `travel_outcome` crash, the second the walk-data blockage. In the third, with obstacle memory, five turns in a row made progress before it stalled again; it had not reached the door when this release was cut.
- **Known issue:** reaching the Ravenwood door from the south of the Commons still stalls. The next release will look into it.
- **Not verified:** zones beyond Wizard City's starting areas, goal types other than bounty, bountycollect, persona, waypoint and usage, group fights, and any game update after 2026-10-26.
