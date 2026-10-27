import tempfile
import unittest
from pathlib import Path

from wizardtraining.knowledge import Knowledge
from wizardtraining.progress import Limits, RunRecord
from wizardtraining.teleports import LEFT_ZONE, NO_EFFECT

TRITON = "WizardCity/WC_Streets/WC_Triton"


class KnowledgeTest(unittest.TestCase):
    def test_a_missing_or_broken_file_is_no_knowledge(self):
        with tempfile.TemporaryDirectory() as folder:
            self.assertEqual(Knowledge.load(Path(folder) / "knowledge.json"), Knowledge())
            broken = Path(folder) / "broken.json"
            broken.write_text("{not json", encoding="utf-8")
            self.assertEqual(Knowledge.load(broken), Knowledge())

    def test_saves_and_loads(self):
        knowledge = Knowledge({TRITON: {"Tele Up": 0}}, ["WizardCity/WC_Streets/WC_Cyclops"])
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "runtime" / "knowledge.json"
            knowledge.save(path)
            self.assertEqual(Knowledge.load(path), knowledge)

    def test_learns_from_a_run_but_not_no_effect_verdicts(self):
        run = RunRecord(limits=Limits())
        run.teleport_outcomes[TRITON] = {"Tele Up": 0, "Olde Town exit": LEFT_ZONE, "Tele Down": NO_EFFECT}
        knowledge = Knowledge()
        knowledge.learn_from(run)
        self.assertEqual(knowledge.teleport_outcomes, {TRITON: {"Tele Up": 0, "Olde Town exit": LEFT_ZONE}})

    def test_keeps_zones_routed_by_the_nav_graph_first(self):
        run = RunRecord(limits=Limits())
        run.nav_first_zones.append("WizardCity/WC_Streets/WC_Cyclops")
        knowledge = Knowledge()
        knowledge.learn_from(run)
        fresh = RunRecord(limits=Limits())
        knowledge.give_to(fresh)
        self.assertEqual(fresh.nav_first_zones, ["WizardCity/WC_Streets/WC_Cyclops"])

    def test_a_new_run_starts_with_it(self):
        run = RunRecord(limits=Limits())
        Knowledge({TRITON: {"Tele Up": 0}}).give_to(run)
        self.assertEqual(run.teleport_outcomes, {TRITON: {"Tele Up": 0}})


if __name__ == "__main__":
    unittest.main()
