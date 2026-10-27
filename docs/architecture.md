# Architecture

## Layers

```
loop        QuestLoop: one decision per turn; goal handlers; limits; report
 ├─ combat      approach an enemy; play rounds with a CombatPolicy
 ├─ dialog      walk up, X, Space through pages; quest offers via an OfferPolicy
 ├─ movement    calibrated A/D turns; walking with W held under a watcher; route following
 │   └─ navigation  load zone walk data into a RoutePlanner
 ├─ entities    classify loaded entities; enemies, NPCs, duel circles; step away
 ├─ quests      journal, active main quest, goals, quest arrow
 ├─ ui          windows by path; mouseless clicks
 └─ session     attach; reading hooks in; hooks always out

decide (no game access): routes, targets, policy, progress, state, geometry, keys, reports, config
```

The "do" modules talk to the game through WizWalker. The "decide" modules take plain values (tuples, dicts, dataclasses) and return decisions, so they run and test anywhere. `tests/test_import_boundary.py` enforces the split.

## One turn of the loop

`QuestLoop.run_turns` checks the limits and the STOP file, reads a `state.snapshot`, and stops if the target level is reached. Then `play_turn` picks exactly one action:

1. **Loading:** wait, up to a limit of waits in a row.
2. **Battle showing:** `combat.fight` with the combat policy. A defeat stops the run (`Limits.max_defeats` is 0).
3. **Dialog open:** `dialog.read_conversation`, including follow-ups.
4. **Not clearly free to move:** a stalled turn.
5. **Low health:** rest, unless the zone is known not to regenerate.
6. **Otherwise the quest:**
   - read the active quest, and stop if it is not a main quest;
   - take its first open goal and read the arrow;
   - a goal in another zone goes to `waypoint_turn`, which walks to the door;
   - every other goal goes to its handler in `goal_handlers()`.

Each turn returns `progressed(...)` or `stalled(...)`. Several stalled turns in a row stop the run.

## Walking

`movement.travel` asks the `RoutePlanner` for a route by each method in turn (collision grid, nav graph, straight line), and follows the first that works with `follow_route`:

- **W is held** (`keys.HeldKey`) while a watcher runs every 50 ms.
- **The watcher** is `QuestLoop.watcher`. It stops the walk for the STOP file, a battle, loading, a dialog or the handler's own arrival check. It steps away from a close enemy. It ends the trip when a duel circle, or an enemy the route did not already account for (`progress.PlannedRoute`), is near the next 2000 units of path.
- **Steering** uses short A/D taps sized by the turn calibration. Sharp corners stop and turn in place.
- **Blockages:** no progress while W is held means blocked. The point just ahead is recorded as an obstacle for the zone, and the wizard sidesteps by turning off its bearing. The next route method, and every later route in that zone, plans around recorded obstacles.

An interrupted trip returns to the loop, which re-plans on the next turn with fresh enemy positions.

Some zones' walkable areas come in separate pieces, such as Triton Avenue's lower street and upper level. When the target is in another piece, `QuestLoop.teleport_turn` walks into one of the zone's teleport volumes (`teleports.py`, read from the zone's `volumes.xml`) and remembers where it led.

## Route planning

`routes.RoutePlanner.route(method, start, goal, hazards)`:

- **collision:** A* over Deimos's hex walk grid, built from the zone's collision.bcd. It is bounded by `MAX_GRID_NODES` and `PLANNING_SECONDS`, then string-pulled into straight legs that Deimos's `straight_path_walkable` accepts.
- **nav:** A* over the zone.nav waypoint graph, string-pulled into legs that stay within one nav cell of a waypoint.
- **straight:** one leg, refused if it crosses a duel circle or passes close to an enemy. When walk data loaded, it is also refused if it is more dangerous than its ends, so it never cuts across a patrol path.

`Hazards` adds cost near enemies (`ENEMY_AVOID_RADIUS`, `ENEMY_AVOID_WEIGHT`), and keeps merged legs `LEG_ENEMY_CLEARANCE` from enemies. It forbids duel circles (`DUEL_CIRCLE_NO_GO`) and recorded obstacles (`OBSTACLE_RADIUS`).

## Battles

`combat.fight` waits for each planning phase. It builds a `policy.RoundView` (health, pips, cards by spell type, living enemies) and asks the policy for a `Cast`. It validates the choice, casts through the mouseless cursor or passes, and waits for the next round. The battle code stops on timeouts, a round limit or any error, leaving the battle to the operator.

## Dialogs

X opens a dialog once the wizard is close enough to the arrow's NPC, or the interact prompt belongs to it. Space pages through, except on a page with a DECLINE button, which is a quest offer: there the `OfferPolicy` decides. After a dialog ends, the code waits up to 10 s for a follow-up dialog, which is how the next main quest arrives.

## Reports

`progress.RunRecord` collects every turn, battle and conversation (page counts and lengths, not text), the planner status per zone, the start and end state, and why the run stopped. `loop.play` saves it to the runtime folder however the run ends. Reports are labelled `"simulated": false`: they are real game observations.
