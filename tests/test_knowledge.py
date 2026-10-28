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

    def test_remembers_a_step_across_a_gap_that_ended_where_it_began(self):
        run = RunRecord(limits=Limits())
        run.failed_gaps[TRITON] = [(18, 0), (0, 18)]
        knowledge = Knowledge()
        knowledge.learn_from(run)
        knowledge.learn_from(run)
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "knowledge.json"
            knowledge.save(path)
            fresh = RunRecord(limits=Limits())
            Knowledge.load(path).give_to(fresh)
        self.assertEqual(fresh.failed_gaps, {TRITON: [(18, 0), (0, 18)]})

    def test_keeps_zones_routed_by_the_nav_graph_first(self):
        run = RunRecord(limits=Limits())
        run.nav_first_zones.append("WizardCity/WC_Streets/WC_Cyclops")
        knowledge = Knowledge()
        knowledge.learn_from(run)
        fresh = RunRecord(limits=Limits())
        knowledge.give_to(fresh)
        self.assertEqual(fresh.nav_first_zones, ["WizardCity/WC_Streets/WC_Cyclops"])

    def test_keeps_zones_where_enemies_were_met(self):
        run = RunRecord(limits=Limits())
        run.zones_with_enemies.append("WizardCity/WC_Streets/WC_Cyclops")
        knowledge = Knowledge()
        knowledge.learn_from(run)
        knowledge.learn_from(run)
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "knowledge.json"
            knowledge.save(path)
            fresh = RunRecord(limits=Limits())
            Knowledge.load(path).give_to(fresh)
        self.assertEqual(fresh.zones_with_enemies, ["WizardCity/WC_Streets/WC_Cyclops"])

    def test_keeps_patrol_path_sightings_without_counting_twice(self):
        knowledge = Knowledge()
        run = RunRecord(limits=Limits())
        knowledge.give_to(run)
        run.path_views[TRITON] = {"Path 3m": 200}
        run.path_sightings[TRITON] = {"Path 3": 12}
        knowledge.learn_from(run)
        knowledge.learn_from(run)
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "knowledge.json"
            knowledge.save(path)
            later = RunRecord(limits=Limits())
            Knowledge.load(path).give_to(later)
        self.assertEqual(later.path_views, {TRITON: {"Path 3m": 200}})
        self.assertEqual(later.path_sightings, {TRITON: {"Path 3": 12}})
        later.path_views[TRITON]["Path 3m"] += 100
        self.assertEqual(knowledge.path_views, {TRITON: {"Path 3m": 200}})

    def test_keeps_the_spells_the_wizard_knows(self):
        knowledge = Knowledge()
        run = RunRecord(limits=Limits())
        knowledge.give_to(run)
        run.known_spells = [74836240, 1887199642]
        knowledge.learn_from(run)
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "knowledge.json"
            knowledge.save(path)
            later = RunRecord(limits=Limits())
            Knowledge.load(path).give_to(later)
        self.assertEqual(later.known_spells, [74836240, 1887199642])

    def test_keeps_zones_entered_with_x_and_the_level_last_trained_at(self):
        knowledge = Knowledge(trained_at_level=8)
        run = RunRecord(limits=Limits())
        knowledge.give_to(run)
        self.assertEqual(run.trained_at_level, 8)
        run.entered_with_x.append("WizardCity/WC_Streets/Interiors/WC_OldeTown_T2")
        run.trained_at_level = 10
        knowledge.learn_from(run)
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "knowledge.json"
            knowledge.save(path)
            later = RunRecord(limits=Limits())
            Knowledge.load(path).give_to(later)
        self.assertEqual(later.entered_with_x, ["WizardCity/WC_Streets/Interiors/WC_OldeTown_T2"])
        self.assertEqual(later.trained_at_level, 10)

    def test_keeps_the_combat_strategies_lost_with_against_each_group_of_enemies(self):
        knowledge = Knowledge(combat_strategies_tried={"Flame Servant": ["default"]})
        run = RunRecord(limits=Limits())
        knowledge.give_to(run)
        run.combat_strategies_tried.setdefault("Nirini Sentry", []).append("heal earlier")
        run.recharging = True
        run.marked_in, run.mark_tip = "Krokotopia/KT_Pyramid/KT_Chamber", "Chamber of Fire"
        run.zone_links = {"Krokotopia/KT_Hub": ["Krokotopia/KT_Pyramid/KT_AltarOfKings"]}
        run.travel_costs = {"walk_speed": 359.0}
        run.hubs = {"Krokotopia": "Krokotopia/KT_Hub"}
        run.leaving_resets = ["WizardCity/WC_Streets/Interiors/WC_OldeTown_T2"]
        run.clearing_world, run.paused_quest = "WizardCity", "Gather the Troops"
        run.hidden_doors = {"WizardCity/WC_Streets/WC_Cyclops": [(-50, 13621)]}
        run.mark_door_for, run.parked_quests = "WizardCity/WC_Streets/Interiors/WC_Cyclops_T1", {"Mad Maximus": 13}
        run.reagent_zones = {"Mist Wood": ["WizardCity/WC_Streets/WC_Unicorn"]}
        run.reagent_searched = {"Mist Wood": ["WizardCity/WC_Hub"]}
        run.wanted_reagents = {"Mist Wood": "Wizards in the Mist"}
        run.deck_capacity = {"Starter Deck": 14}
        run.enemy_zones = {"Lost Soul": ["WizardCity/WC_Streets/WC_Unicorn"]}
        run.essence_quests = {"Know Thine Enemy": "Lost Soul Essence"}
        knowledge.learn_from(run)
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "knowledge.json"
            knowledge.save(path)
            later = RunRecord(limits=Limits())
            Knowledge.load(path).give_to(later)
        self.assertEqual(later.combat_strategies_tried, {"Flame Servant": ["default"], "Nirini Sentry": ["heal earlier"]})
        self.assertTrue(later.recharging)
        self.assertEqual((later.marked_in, later.mark_tip), ("Krokotopia/KT_Pyramid/KT_Chamber", "Chamber of Fire"))
        self.assertEqual(later.zone_links, {"Krokotopia/KT_Hub": ["Krokotopia/KT_Pyramid/KT_AltarOfKings"],
                                            "Krokotopia/KT_Pyramid/KT_AltarOfKings": ["Krokotopia/KT_Hub"]})
        self.assertEqual((later.travel_costs, later.hubs), ({"walk_speed": 359.0}, {"Krokotopia": "Krokotopia/KT_Hub"}))
        self.assertEqual(later.leaving_resets, ["WizardCity/WC_Streets/Interiors/WC_OldeTown_T2"])
        self.assertEqual((later.clearing_world, later.paused_quest), ("WizardCity", "Gather the Troops"))
        self.assertEqual(later.hidden_doors, {"WizardCity/WC_Streets/WC_Cyclops": [(-50, 13621)]})
        self.assertEqual((later.mark_door_for, later.parked_quests),
                         ("WizardCity/WC_Streets/Interiors/WC_Cyclops_T1", {"Mad Maximus": 13}))
        self.assertEqual(later.reagent_zones, {"Mist Wood": ["WizardCity/WC_Streets/WC_Unicorn"]})
        self.assertEqual(later.reagent_searched, {"Mist Wood": ["WizardCity/WC_Hub"]})
        self.assertEqual(later.wanted_reagents, {"Mist Wood": "Wizards in the Mist"})
        self.assertEqual(later.deck_capacity, {"Starter Deck": 14})
        self.assertEqual(later.enemy_zones, {"Lost Soul": ["WizardCity/WC_Streets/WC_Unicorn"]})
        self.assertEqual(later.essence_quests, {"Know Thine Enemy": "Lost Soul Essence"})

    def test_a_new_run_starts_with_it(self):
        run = RunRecord(limits=Limits())
        Knowledge({TRITON: {"Tele Up": 0}}).give_to(run)
        self.assertEqual(run.teleport_outcomes, {TRITON: {"Tele Up": 0}})


if __name__ == "__main__":
    unittest.main()
