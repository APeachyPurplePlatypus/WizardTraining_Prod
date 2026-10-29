# Architecture

Design advice that held up over one bot's first fifteen levels. None of it depends on a language or a library. Take what fits your design.

## Keep decisions apart from game access

Split the bot into code that touches the game (reading memory, sending keys, clicking) and code that decides (routes, targets, card choice, refill rules, limits). The deciding code takes plain values and returns decisions, so it runs and is tested anywhere, without the game or the game library installed. Enforce the split with a test, or it erodes.

Most bugs worth catching are in the decisions, and a test suite that runs in a second catches them before a live run does. One that slipped through: a logging helper lived on the game side, so the tests never ran it, and it stopped the first live run that hit it. Move anything that can be pure to the pure side.

## One decision per turn

A main loop that reads the state once and picks exactly one action keeps the bot understandable. Check the stop signal and the limits first, then:

1. loading: wait;
2. a battle: fight it;
3. a dialog: read it;
4. not clearly free to move: wait, and count it;
5. short of health or mana: refill;
6. otherwise: the quest's next goal.

Each turn reports whether it made progress. Several turns in a row without progress are a stall, so change strategy or stop.

## Steer in a closed loop

Walking is a control problem. A fast loop (100 Hz worked) reads position and heading and sets the keys from them, aiming at a point sliding ahead on the route and braking by the measured speed. Planning, entity scans and UI reads run beside it, never inside it. See the steering lessons in [lessons-learned.md](lessons-learned.md).

## Route planning in layers

No single source of walk data was enough:

1. **A walk grid from the collision data,** with A* and string-pulling into straight legs. It's accurate, but it misses props and some ramps.
2. **The game's nav graph,** which links levels the grid leaves apart.
3. **A straight line,** refused when it crosses something dangerous.

Add costs near enemies and keep a hard keep-out from duel circles. Add the obstacles the character actually bumped into, so every later route avoids them. Bound each search in nodes and time, and fall back to the next layer when one fails. When a whole street is sealed by projected patrols, plan around the near ones only.

## Remember what's learned

Keep a small store that survives restarts: doors and the zones they lead to, where travel buttons landed, which zones' fights are heavy, where marks were safe or led into fights, each enemy kind's biggest hit, and the deck's size. A restart then costs seconds, not the knowledge of an evening.

## Log why, and measure every rule

- **Log each decision with its reason** (a discard, a refill, a skipped mark), as events you can read back. Then "why did it do that?" has an answer.
- **Make every rule measurable.** Rounds per fight, health per fight, fights per walk, the gap after a battle, wisp success. Record the numbers before and after a change, so you can tell whether it helped.
- **Keep run output out of version control.** It names the character and other players.

## Supervision

The operator decides what the bot may do. Keep the allow-list of keys and clicks in one place, with a test that the code can't go beyond it. Give the bot a stop signal it checks often, and a way to report what it's doing in plain facts. See [safety.md](safety.md).
