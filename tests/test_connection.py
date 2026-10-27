import datetime
import tempfile
import unittest
from pathlib import Path

from wizardtraining.connection import (LOG, client_log_tail, log_reaches, log_starts_by, lost_connection,
                                       moves_by_round, moves_sent_between)

DROPPED = """10/27/26 02:06:29 [ERRO] ClientCinematic  HandleAnimationEvent: 'end'
10/27/26 02:06:35 [DBGM] GameClient      AppCloseConnection() called, connection state is 6
10/27/26 02:06:38 [DBGM] GameClient      HandleReconnectTimeout() called.
10/27/26 02:06:49 [DBGM] CORE_SEER       GameClient::ConnectComplete destination Zone=WizardCity/WC_Streets/WC_Cyclops
10/27/26 02:06:49 [DBGM] GameClient      AppCloseConnection() called, connection state is 5
10/27/26 02:10:54 [STAT] CORE_SEER       PROCESS MEMORY USAGE at 425 min(s) 0 sec(s)
"""


ROUNDS = """10/27/26 09:28:02 [STAT] ClientDuel      Local Player Sending Move: Unready  time left:-1
10/27/26 09:28:04 [STAT] ClientDuel      Local Player Sending Move: Cast Spell  time left:-1
10/27/26 09:28:24 [STAT] ClientDuel      Local Player Sending Move: Unready  time left:-1
10/27/26 09:28:54 [STAT] ClientDuel      Duel 6124866: MSG_CombatPhase(kPhase_Execution) PlayerID:0
"""


def at(seconds_past_9_28):
    return datetime.datetime(2026, 10, 27, 9, 28) + datetime.timedelta(seconds=seconds_past_9_28)


class MovesTest(unittest.TestCase):
    def test_lists_the_moves_sent_in_a_stretch(self):
        self.assertEqual(moves_sent_between(ROUNDS, at(4)), ["Cast Spell", "Unready"])
        self.assertEqual(moves_sent_between(ROUNDS, at(0), at(10)), ["Unready", "Cast Spell"])
        self.assertEqual(moves_sent_between(ROUNDS, at(25)), [])
        self.assertEqual(moves_sent_between("garbage\n" + ROUNDS, at(0)), ["Unready", "Cast Spell", "Unready"])

    def test_a_buffered_log_may_not_reach_a_moment_yet(self):
        self.assertTrue(log_reaches(ROUNDS, at(54)))
        self.assertFalse(log_reaches(ROUNDS, at(55)))

    def test_each_rounds_moves_or_none_where_the_log_does_not_reach(self):
        self.assertEqual(moves_by_round([at(3), at(24)], ROUNDS), [["Cast Spell"], []])
        self.assertEqual(moves_by_round([at(3), at(24), at(50)], ROUNDS), [["Cast Spell"], [], None])

    def test_rounds_before_the_log_text_begins_are_unknown(self):
        self.assertFalse(log_starts_by(ROUNDS, at(1)))
        self.assertTrue(log_starts_by(ROUNDS, at(2)))
        self.assertEqual(moves_by_round([at(1), at(24)], ROUNDS), [None, []])


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
