import unittest

from wizardtraining.policy import (ACCEPT, DECLINE, GO_BACK, STOP, Card, Cast, Combatant, MainQuestsOnly, RoundView,
                                   SpellTypePolicy, problem_with)

HEAL = Card("Fairy", "Heal", True)
BOLT = Card("Fire Cat", "Damage", True)
STORM = Card("Firestorm", "AOE", True)
TOO_DEAR = Card("Big Spell", "Damage", False)
SHIELD = Card("Tower Shield", "Ward", True)
ONE_ENEMY = (Combatant("Ghost", 200),)


def view(cards, health=500, max_health=500, enemies=ONE_ENEMY):
    return RoundView(round_number=1, health=health, max_health=max_health, pips=3, power_pips=0, cards=tuple(cards),
                     enemies=enemies)


class SpellTypePolicyTest(unittest.TestCase):
    policy = SpellTypePolicy()

    def test_attacks_the_first_enemy_with_the_first_affordable_attack(self):
        self.assertEqual(self.policy.choose(view([SHIELD, TOO_DEAR, BOLT])), Cast(2, "enemy"))

    def test_spells_that_hit_every_enemy_take_no_target(self):
        self.assertEqual(self.policy.choose(view([STORM])), Cast(0, "all enemies"))

    def test_heals_itself_when_health_is_low(self):
        self.assertEqual(self.policy.choose(view([BOLT, HEAL], health=100)), Cast(1, "self"))

    def test_attacks_when_low_without_a_heal(self):
        self.assertEqual(self.policy.choose(view([BOLT], health=100)), Cast(0, "enemy"))

    def test_passes_without_an_affordable_attack(self):
        self.assertIsNone(self.policy.choose(view([SHIELD, TOO_DEAR])))

    def test_passes_with_no_living_enemy(self):
        self.assertIsNone(self.policy.choose(view([BOLT], enemies=())))

    def test_unknown_health_is_not_low(self):
        self.assertEqual(self.policy.choose(view([HEAL, BOLT], health=None)), Cast(1, "enemy"))


class ProblemWithTest(unittest.TestCase):
    def test_a_valid_choice_has_no_problem(self):
        self.assertIsNone(problem_with(Cast(0, "enemy"), view([BOLT])))

    def test_refuses_cards_that_cannot_be_cast(self):
        self.assertIn("not castable", problem_with(Cast(0, "enemy"), view([TOO_DEAR])))
        self.assertIn("not castable", problem_with(Cast(5, "enemy"), view([BOLT])))

    def test_refuses_missing_enemies_and_unknown_targets(self):
        self.assertIn("not there", problem_with(Cast(0, "enemy", enemy=3), view([BOLT])))
        self.assertIn("unknown target", problem_with(Cast(0, "the boss"), view([BOLT])))


class MainQuestsOnlyTest(unittest.TestCase):
    policy = MainQuestsOnly()

    def test_declines_side_quests(self):
        self.assertEqual(self.policy.decide(["Hello.", "I am Offering You A Side Quest."], can_go_back=True), DECLINE)

    def test_goes_back_once_to_read_the_offer(self):
        self.assertEqual(self.policy.decide(["Will you help?"], can_go_back=True), GO_BACK)

    def test_stops_rather_than_guess(self):
        self.assertEqual(self.policy.decide(["Will you help?"], can_go_back=False), STOP)


class ServicesMenuTest(unittest.TestCase):
    menu = ["Trouble on Triton Avenue ", "A Good Day to Cyclops", "Putting Out the Fire!"]

    def test_takes_the_option_for_the_active_quest(self):
        self.assertEqual(MainQuestsOnly().choose_service(self.menu, active_quest="putting out the fire!"), 2)

    def test_takes_the_first_approved_title_in_the_operators_order(self):
        policy = MainQuestsOnly(approved_titles=["Putting Out the Fire!", "Trouble on Triton Avenue"])
        self.assertEqual(policy.choose_service(self.menu, active_quest=None), 2)

    def test_leaves_unapproved_menus_to_the_operator(self):
        self.assertIsNone(MainQuestsOnly().choose_service(self.menu, active_quest=None))
        self.assertIsNone(MainQuestsOnly(approved_titles=["Other"]).choose_service(self.menu, active_quest="Else"))

    def test_accepts_the_offer_of_an_approved_title_once(self):
        policy = MainQuestsOnly(approved_titles=["A Good Day to Cyclops"])
        policy.choose_service(self.menu, active_quest=None)
        self.assertEqual(policy.decide(["Help the city?"], can_go_back=True), ACCEPT)
        self.assertEqual(policy.decide(["Help again?"], can_go_back=True), GO_BACK)

    def test_an_approved_title_that_calls_itself_a_side_quest_is_declined(self):
        policy = MainQuestsOnly(approved_titles=["A Good Day to Cyclops"])
        policy.choose_service(self.menu, active_quest=None)
        self.assertEqual(policy.decide(["I am offering you a side quest."], can_go_back=True), DECLINE)


if __name__ == "__main__":
    unittest.main()
