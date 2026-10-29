# Real-Time Closed-Loop Pathfinding & Steering Upgrade (`update_pathfinding.md`)

## 1. Summary of What Changed & Why

Previously, keyboard movement and enemy avoidance suffered from five compounding sources of control lag ("aiming at past state values"):

1. **Open-Loop Timed Key Taps (`send_key` + sleeps)**:
   - `turn_toward` and `steer` computed a tap duration `seconds = undershoot * abs(error) / radians_per_second`, called `await client.send_key(key, seconds)` (which slept blindly without reading memory), and in `turn_toward` slept an additional `TURN_SETTLE_SECONDS = 0.12s`.
   - While `steer()` was sleeping for `20–120ms`, the wizard kept moving at `600–840 u/s` (`50–100` units per tap) without reading position or yaw.
2. **Dead-Stop Cornering (`STOP_TO_TURN_RADIANS = 50°`)**:
   - At every bend $> 50^\circ$, `follow_route` released `W`, came to a dead stop, ran a multi-tap `turn_toward` loop, and only then resumed walking.
3. **Point-to-Point Static Waypoint Snapping**:
   - The wizard aimed strictly at `remaining[0]` until within `WAYPOINT_RADIUS = 120`, causing late sharp turns at vertices and turning backward if a corner was rounded slightly wider than `120` units.
4. **1.5-Second Secant Velocity Lag (`MotionTracker`)**:
   - `MotionTracker.track()` computed enemy velocity from `(samples[-1] - samples[0]) / (last_time - first_time)` across the entire `MOTION_WINDOW_SECONDS = 1.5s` deque. When a patrolling enemy reversed direction, its estimated velocity lagged by `~0.75s` (smearing pre-turn and post-turn positions).
5. **Synchronous Perception & A* Stalls in the Steering Loop**:
   - `watch(path_ahead)` was awaited inline on every steering iteration (`snapshot()`, UI tree traversal for `dialog_open()` and `interact_prompt_text()`, entity list scans, and synchronous `planner.reroute()` A* searches up to `250ms`), dropping the effective steering loop rate to `4–15 Hz`.

---

## 2. New Architecture: 100 Hz Closed-Loop Reflex Controller

Both the active production framework (`<framework>/src/wizardtraining/`) and the standalone live scripts (`<live scripts folder>/`) now use a two-tier real-time architecture:

- **Tier 1 — 100 Hz (`TICK_SECONDS = 0.01s`) Reflex Steering Loop**:
  - Reads only `client.body.position()` and `client.body.yaw()` (~20 µs via `ReadProcessMemory` on the player hook struct).
  - Updates `KeyChord` (`WM_KEYDOWN` / `WM_KEYUP` state machine for `W`, `A`, `S`, `D`) on every 10ms tick with **zero blocking sleeps**.
  - Tracks a **Pure-Pursuit ("sliding carrot") lookahead point** along the polyline (`geometry.lookahead_point`), holding `W` + `A`/`D` simultaneously around bends up to `85°` (`PIVOT_IN_PLACE_RADIANS`) so the wizard carves smooth arcs at full speed.
  - Applies a **Proportional-Derivative (PD) yaw controller** (`motion.pd_steer_command`) using live angular velocity $\omega = \Delta\text{yaw}/\Delta t$ and key-release lead prediction (`TURN_LEAD_SECONDS = 0.035s`) so turns stop dead on the target bearing without overshoot or oscillation.
  - Evaluates a **real-time local vector field / velocity-obstacle deflection** (`motion.reactive_bearing`) on every tick around active enemy `Track`s, biasing the tangential component **behind** moving enemies' velocity vectors ($-\vec{v}_{\text{enemy}}$) while verifying collision walkability (`planner.walls_allow`).
  - Uses **velocity-predicted arrival braking** (`motion.should_release_forward`) to release `W` at `distance <= radius + speed * STOP_LEAD_SECONDS` so the wizard coasts directly into small target radii.
- **Tier 2 — Concurrent Non-Blocking Perception & Worker-Thread A* Rerouting (`WATCH_SECONDS = 0.05s`)**:
  - `follow_route` launches `watch(path_ahead)` as a background `asyncio.Task` every `0.05s` while the 100 Hz reflex loop continues ticking uninterrupted in the foreground.
  - In `loop.py`, `QuestLoop.watcher` offloads `reroute(path_ahead, threats, now)` to a worker thread via `await asyncio.to_thread(reroute, path_ahead, threats, now)` and updates `self._active_tracks` for the 100 Hz reflex loop.

---

## 3. File-by-File Changes

### A. `<framework>` (`wizardtraining` package)

1. **`src/wizardtraining/geometry.py`** (pure math, `NO_GAME_ACCESS`):
   - `bearing(origin, target) -> float`: Pure-Python equivalent of WizWalker's `calculate_perfect_yaw` (`math.atan2(-dx, -dy) % (2 * math.pi)`), usable in offline `NO_GAME_ACCESS` modules.
   - `project_onto_segment(point, a, b) -> tuple[Point, float, float]`: Returns `(foot, along_fraction, distance)` on segment `a -> b`.
   - `lookahead_point(point, polyline, lookahead, line_walkable=None) -> tuple[Point, int]`: Projects `point` onto `polyline` (`[leg_start, *remaining]`), slides `lookahead` units ahead along the polyline for smooth cornering, returns `(carrot, active_segment_index)` so rounded vertices are automatically pruned, and falls back to the corner vertex if `line_walkable(me, carrot)` rejects cutting an indoor wall corner.

2. **`src/wizardtraining/motion.py`** (pure math, `NO_GAME_ACCESS`):
   - `MotionTracker`:
     - Instead of computing secant velocity across the entire `1.5s` window (`samples[0]` to `samples[-1]`), selects the **newest** anchor sample spanning at least `MIN_MOTION_SPAN_SECONDS = 0.3s`.
     - Detects instantaneous step direction reversals (`len(samples) >= 3`, `dt >= 0.02s`, `cosine < 0.5`) so when a patrolling enemy turns around, `track()` reports the new velocity vector on the very next sample with zero window lag.
   - `pd_steer_command(off_course, angular_velocity=0.0, *, deadband, lead_seconds, pivot_radians) -> tuple[int, bool]`:
     - Computes predicted error `predicted = off_course - angular_velocity * lead_seconds`.
     - Returns `(turn_sign, hold_forward)` where `turn_sign` is `-1 | 0 | 1` and `hold_forward` is `True` for `abs(off_course) <= PIVOT_IN_PLACE_RADIANS` (`85°`).
   - `should_release_forward(distance, radius, speed, stop_lead_seconds=STOP_LEAD_SECONDS) -> bool`:
     - Velocity-predicted braking check (`distance <= radius + speed * stop_lead_seconds`).
   - `lookahead_distance(speed) -> float`:
     - Scales Pure-Pursuit lookahead with walking/mount speed (`clamp(speed * 0.45, 180.0, 480.0)`).
   - `reactive_bearing(me, carrot, tracks=(), *, speed, avoid_radius, line_walkable=None) -> float`:
     - Combines unit goal attraction toward `carrot` with quadratic radial repulsion + tangential pass-behind vectors (`-track.velocity` for moving enemies, goal-aligned tangent for stationary enemies) and verifies `line_walkable` before applying deflection.

3. **`src/wizardtraining/keys.py`** (`NO_GAME_ACCESS`):
   - Added `KeyChord`: Non-blocking state machine managing simultaneous held keys (`W`, `A`, `S`, `D`) via `SendMessageW(window, WM_KEYDOWN/WM_KEYUP, ...)`. Enforces `check_allowed(key)` (never sends `Q` or `E`), repeats `WM_KEYDOWN` only when `KEY_REPEAT_SECONDS = 0.05s` has elapsed, and immediately sends `WM_KEYUP` when a key is dropped or the context exits.

4. **`src/wizardtraining/entities.py`**:
   - Added optional `refresh: bool = True` parameter to `EntityTracker._located()`, `EntityTracker.enemies_and_duel_circles()`, and `surroundings()` so cached entity addresses can be queried without forcing a full entity-list scan.

5. **`src/wizardtraining/movement.py`**:
   - Upgraded `turn_toward(client, target_yaw)` to use `KeyChord` + `pd_steer_command` at `100 Hz` (`TICK_SECONDS = 0.01s`) after the first calibration tap.
   - Upgraded `follow_route(client, legs, *, final_radius, watch=None, line_walkable=None, live_tracks=None)` to run at `100 Hz` with `KeyChord`, Pure-Pursuit `lookahead_point`, `reactive_bearing`, `should_release_forward`, and concurrent `watch_task` execution.
   - Updated `travel(...)` to pass `line_walkable=planner.walls_allow` and `live_tracks` into `follow_route`.

6. **`src/wizardtraining/loop.py`**:
   - Added `self._active_tracks` updated in `hazards_for()` and `watcher()`.
   - Passed `live_tracks=lambda: self._active_tracks` into `travel(...)`.
   - Offloaded `reroute(path_ahead, threats, now)` in `watcher()` to `await asyncio.to_thread(reroute, path_ahead, threats, now)`.

7. **`tests/test_geometry.py` & `tests/test_motion.py`**:
   - Added offline unit tests (`LookaheadPointTest`, `ClosedLoopReflexTest`, `test_bearing_matches_wizwalker_yaw_convention`, `test_patrol_reversal_is_detected_immediately_without_window_lag`). All 507 unit tests pass.

---

### B. `<live scripts folder>` (standalone live scripts)

1. **`live/common.py`**:
   - Added `KeyChord`, `pd_steer_command`, and upgraded `turn_toward` to 100 Hz closed-loop PD control.
2. **`live/pathing.py`**:
   - Added `lookahead_point`, `path_beyond`, spatial bucket hash acceleration (`Planner._near_waypoint`) for `zone.nav` string pulling, `Planner.walls_allow`, and upgraded `follow_route` to 100 Hz closed-loop PD steering + Pure Pursuit + concurrent non-blocking `watch` task execution.

---

## 4. Key Tuning Constants

| Constant | Location | Value | Purpose |
| :--- | :--- | :--- | :--- |
| `TICK_SECONDS` | `movement.py` | `0.01` (100 Hz) | Inner closed-loop steering & position/yaw read period |
| `WATCH_SECONDS` | `movement.py` | `0.05` (20 Hz) | Concurrent background perception (`watch`) period |
| `STEER_DEADBAND_RADIANS` | `motion.py` | `rad(1.8°)` | Yaw deadband within which `A`/`D` are released |
| `TURN_LEAD_SECONDS` | `motion.py` | `0.035s` | PD derivative lead time (`off_course - omega * lead`) |
| `PIVOT_IN_PLACE_RADIANS` | `motion.py` | `rad(85°)` | Max bend angle where `W` stays held while turning (`W+A`/`W+D`) |
| `STOP_LEAD_SECONDS` | `motion.py` | `0.035s` | Velocity-predicted braking lead time before `final_radius` |
| `PURE_PURSUIT_LOOKAHEAD_SECONDS` | `motion.py` | `0.45s` | Lookahead carrot time horizon (`180–480` units) |
| `REACTIVE_AVOID_RADIUS` | `motion.py` | `950.0` units | Local potential-field & pass-behind deflection radius |
