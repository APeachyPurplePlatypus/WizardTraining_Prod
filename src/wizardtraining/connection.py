"""Whether the game client lost its connection to the server, read from its own log. No game memory access.

The client writes Bin/WizardClient.log in the game folder. When the server connection drops, it logs
"AppCloseConnection() called", tries to reconnect, and logs "ConnectComplete" when that works. On 2026-10-27 the
connection closed during a battle and stayed closed: the client froze in the battle's execution phase, and the run
could only report that no planning phase came. Logging in again is the operator's job.
"""

from __future__ import annotations

from pathlib import Path

LOG = Path("Bin") / "WizardClient.log"
LOG_TAIL_BYTES = 200_000
CLOSED = "AppCloseConnection() called"
CONNECTED = "ConnectComplete"
TIMESTAMP_LENGTH = 17


def lost_connection(log_tail: str) -> str | None:
    """The time of the last connection close ("10/27/26 02:06:49") when no connection completed after it, else
    None."""
    lines = log_tail.splitlines()
    last_close = max((index for index, line in enumerate(lines) if CLOSED in line), default=None)
    if last_close is None or any(CONNECTED in line for line in lines[last_close + 1:]):
        return None
    return lines[last_close][:TIMESTAMP_LENGTH].strip()


def client_log_tail(game_folder: Path, size: int = LOG_TAIL_BYTES) -> str:
    """The last `size` bytes of the client's log, or "" when it cannot be read."""
    path = Path(game_folder) / LOG
    try:
        with open(path, "rb") as log:
            log.seek(max(0, path.stat().st_size - size))
            return log.read().decode("utf-8", "replace")
    except OSError:
        return ""
