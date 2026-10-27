import tempfile
import unittest
from pathlib import Path

from wizardtraining.connection import LOG, client_log_tail, lost_connection

DROPPED = """10/27/26 02:06:29 [ERRO] ClientCinematic  HandleAnimationEvent: 'end'
10/27/26 02:06:35 [DBGM] GameClient      AppCloseConnection() called, connection state is 6
10/27/26 02:06:38 [DBGM] GameClient      HandleReconnectTimeout() called.
10/27/26 02:06:49 [DBGM] CORE_SEER       GameClient::ConnectComplete destination Zone=WizardCity/WC_Streets/WC_Cyclops
10/27/26 02:06:49 [DBGM] GameClient      AppCloseConnection() called, connection state is 5
10/27/26 02:10:54 [STAT] CORE_SEER       PROCESS MEMORY USAGE at 425 min(s) 0 sec(s)
"""


class ConnectionTest(unittest.TestCase):
    def test_a_close_with_no_connection_after_it_is_a_lost_connection(self):
        self.assertEqual(lost_connection(DROPPED), "10/27/26 02:06:49")

    def test_a_close_followed_by_a_reconnect_is_not(self):
        reconnected = "\n".join(DROPPED.splitlines()[:4])
        self.assertIsNone(lost_connection(reconnected))
        self.assertIsNone(lost_connection("10/27/26 01:00:00 [STAT] nothing about connections"))

    def test_reads_the_tail_of_the_client_log(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / LOG
            path.parent.mkdir(parents=True)
            path.write_text("x" * 1000 + DROPPED, encoding="utf-8")
            self.assertEqual(lost_connection(client_log_tail(Path(folder), size=len(DROPPED) + 10)), "10/27/26 02:06:49")
            self.assertEqual(client_log_tail(Path(folder) / "missing"), "")


if __name__ == "__main__":
    unittest.main()
