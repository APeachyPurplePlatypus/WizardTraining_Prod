import enum
import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from wizardtraining.config import DEIMOS_VARIABLE, RUNTIME_VARIABLE, Settings
from wizardtraining.keys import RefusedKey, check_allowed
from wizardtraining.reports import plain, save_report, with_text_keys
from wizardtraining.state import battle_showing, free_to_move, health_fraction, mana_fraction


class Key(enum.Enum):
    W = 0x57
    Q = 0x51
    E = 0x45
    END = 0x23
    HOME = 0x24
    ESC = 0x1B
    SPACEBAR = 0x20


class KeysTest(unittest.TestCase):
    def test_refuses_keys_outside_the_allowed_set(self):
        for key in (Key.Q, Key.E, Key.END, Key.HOME, Key.ESC):
            with self.assertRaises(RefusedKey):
                check_allowed(key)

    def test_allows_walking_and_dialog_keys(self):
        check_allowed(Key.W)
        check_allowed(Key.SPACEBAR)


class StateTest(unittest.TestCase):
    calm = {"in_battle": False, "loading": False, "in_dialog": False, "duel_phase": "ended", "health": 400,
            "max_health": 500}

    def test_free_to_move_needs_explicit_readings(self):
        self.assertTrue(free_to_move(self.calm))
        self.assertFalse(free_to_move(dict(self.calm, loading="<unavailable: ReadingError>")))
        self.assertFalse(free_to_move(dict(self.calm, in_dialog=True)))

    def test_battle_shows_by_flag_or_phase(self):
        self.assertFalse(battle_showing(self.calm))
        self.assertTrue(battle_showing(dict(self.calm, duel_phase="planning")))
        self.assertTrue(battle_showing(dict(self.calm, in_battle=True)))

    def test_health_fraction(self):
        self.assertEqual(health_fraction(self.calm), 0.8)
        self.assertEqual(mana_fraction({"mana": 4, "max_mana": 24}), 4 / 24)
        self.assertIsNone(mana_fraction({"mana": 4}))
        self.assertIsNone(health_fraction(dict(self.calm, health="<unavailable: ReadingError>")))


class ConfigTest(unittest.TestCase):
    def test_defaults_without_environment(self):
        settings = Settings.from_environment({})
        self.assertIsNone(settings.deimos_root)
        self.assertEqual(settings.runtime_folder, Path("runtime"))

    def test_reads_environment(self):
        settings = Settings.from_environment({DEIMOS_VARIABLE: "deimos", RUNTIME_VARIABLE: "out"})
        self.assertEqual(settings.deimos_root, Path("deimos"))
        self.assertEqual(settings.stop_file, Path("out") / "STOP")

    def test_stop_file_round_trip(self):
        with tempfile.TemporaryDirectory() as folder:
            settings = Settings(deimos_root=None, runtime_folder=Path(folder) / "runtime")
            self.assertFalse(settings.stop_requested())
            settings.request_stop()
            self.assertTrue(settings.stop_requested())
            settings.clear_stop()
            self.assertFalse(settings.stop_requested())


class ReportsTest(unittest.TestCase):
    def test_plain_values(self):
        self.assertEqual(plain(SimpleNamespace(x=1.04, y=2.06, z=3.0)), {"x": 1.0, "y": 2.1, "z": 3.0})
        self.assertEqual(plain(Key.W), "W")
        self.assertEqual(plain(0.12345), 0.123)
        self.assertEqual(plain([1, 2]), "[1, 2]")

    def test_report_keys_become_text(self):
        report = {"arrivals": {None: {"from": "A"}, "WizardCity/WC_Hub": {"from": None}}}
        self.assertEqual(with_text_keys(report), {"arrivals": {"None": {"from": "A"}, "WizardCity/WC_Hub": {"from": None}}})
        with tempfile.TemporaryDirectory() as folder:
            self.assertTrue(save_report("quest-loop", report, Path(folder)).exists())

    def test_save_report_writes_json(self):
        with tempfile.TemporaryDirectory() as folder:
            path = save_report("probe", {"position": SimpleNamespace(x=1.0, y=2.0, z=3.0)}, Path(folder))
            self.assertEqual(json.loads(path.read_text(encoding="utf-8"))["position"]["x"], 1.0)


if __name__ == "__main__":
    unittest.main()
