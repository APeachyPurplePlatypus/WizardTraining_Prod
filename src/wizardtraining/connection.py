"""Whether the game client lost its connection to the server, read from its own log. No game memory access.

The client writes Bin/WizardClient.log in the game folder. When the server connection drops, it logs
"AppCloseConnection() called", tries to reconnect, and logs "ConnectComplete" when that works. On 2026-10-27 the
connection closed during a battle and stayed closed: the client froze in the battle's execution phase, and the run
could only report that no planning phase came. Logging in again is the operator's job.
"""

from __future__ import annotations

import datetime
from pathlib import Path

LOG = Path("Bin") / "WizardClient.log"
LOG_TAIL_BYTES = 200_000
CLOSED = "AppCloseConnection() called"
CONNECTED = "ConnectComplete"
TIMESTAMP_LENGTH = 17
TIMESTAMP_FORMAT = "%m/%d/%y %H:%M:%S"
MOVE_SENT = "Local Player Sending Move: "
ROUND_OPENING_MOVE = "Unready"
MOVE_LOGGED_WITHIN_SECONDS = 5


def lost_connection(log_tail: str) -> str | None:
    """The time of the last connection close ("10/27/26 02:06:49") when no connection completed after it, else
    None."""
    lines = log_tail.splitlines()
    last_close = max((index for index, line in enumerate(lines) if CLOSED in line), default=None)
    if last_close is None or any(CONNECTED in line for line in lines[last_close + 1:]):
        return None
    return lines[last_close][:TIMESTAMP_LENGTH].strip()


def stamp_of(line: str) -> datetime.datetime | None:
    try:
        return datetime.datetime.strptime(line[:TIMESTAMP_LENGTH], TIMESTAMP_FORMAT)
    except ValueError:
        return None


def moves_sent_between(log_tail: str, start: datetime.datetime, end: datetime.datetime | None = None) -> list[str]:
    """The battle moves the client sent ("Cast Spell", "Pass", "Unready") in lines stamped from `start` up to, not
    including, `end`. A round whose card click sent no move did not take: after a click on Flee, rounds went by
    with no move sent at all."""
    moves = []
    for line in log_tail.splitlines():
        if MOVE_SENT not in line or (stamped := stamp_of(line)) is None:
            continue
        if stamped >= start and (end is None or stamped < end):
            moves.append(line.split(MOVE_SENT, 1)[1].split("  ", 1)[0].strip())
    return moves


def log_reaches(log_tail: str, moment: datetime.datetime) -> bool:
    """The log has a line stamped at `moment` or later. The client writes its log in buffered blocks, up to a minute
    behind, so a move not found before then may still be on its way."""
    return any((stamped := stamp_of(line)) is not None and stamped >= moment
               for line in reversed(log_tail.splitlines()[-200:]))


def moves_by_round(starts: list[datetime.datetime], log_tail: str) -> list[list[str] | None]:
    """For rounds in which the wizard acted at `starts`, the moves the client logged from each until the next,
    other than the "Unready" it sends as a round's planning opens: empty when the click did not take, None while
    the buffered log does not yet reach MOVE_LOGGED_WITHIN_SECONDS past the moment the wizard acted."""
    found = []
    for start, end in zip(starts, [*starts[1:], None]):
        if not log_reaches(log_tail, start + datetime.timedelta(seconds=MOVE_LOGGED_WITHIN_SECONDS)):
            found.append(None)
            continue
        found.append([move for move in moves_sent_between(log_tail, start, end) if move != ROUND_OPENING_MOVE])
    return found


def client_log_tail(game_folder: Path, size: int = LOG_TAIL_BYTES) -> str:
    """The last `size` bytes of the client's log, or "" when it cannot be read."""
    path = Path(game_folder) / LOG
    try:
        with open(path, "rb") as log:
            log.seek(max(0, path.stat().st_size - size))
            return log.read().decode("utf-8", "replace")
    except OSError:
        return ""
