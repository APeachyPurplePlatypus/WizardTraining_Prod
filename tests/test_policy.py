import unittest

from wizardtraining.policy import (ACCEPT, DECLINE, GO_BACK, LEAVE_MENU, STOP, UNIVERSAL, Card, Cast, Combatant,
                                   DamageModifier, MainQuestsOnly, Pass, RoundView, SpellTypePolicy, problem_with)

HEAL = Card("Fairy", "Heal", True)
BOLT = Card("Fire Cat", "Damage", True)
STORM = Card("Firestorm", "AOE", True)
TOO_DEAR = Card("Big Spell", "Damage", False)
SHIELD = Card("Tower Shield", "Ward", True)
MYTH_BOLT = Card("Blood Bat", "Damage", True, "Myth")
ICE_BOLT = Card("Frost Beetle", "Damage", True, "Ice")
ONE_ENEMY = (Combatant("Ghost", 200),)


def view(cards, health=500, max_health=500, enemies=ONE_ENEMY, pips=3):
    return RoundView(round_number=1, health=health, max_health=max_health, pips=pips, power_pips=0, cards=tuple(cards),
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

    def test_plays_around_a_ward(self):
        warded = (Combatant("The Harvest Lord", 510, (DamageModifier("Myth", -50),)),)
        self.assertEqual(self.policy.choose(view([MYTH_BOLT, ICE_BOLT], enemies=warded)), Cast(1, "enemy"))

    def test_plays_into_a_trap(self):
        trapped = (Combatant("Ghost", 200, (DamageModifier("Ice", 25),)),)
        self.assertEqual(self.policy.choose(view([MYTH_BOLT, ICE_BOLT], enemies=trapped)), Cast(1, "enemy"))

    def test_a_shield_on_every_school_keeps_the_hand_order(self):
        shielded = (Combatant("Ghost", 200, (DamageModifier(UNIVERSAL, -30),)),)
        self.assertEqual(self.policy.choose(view([MYTH_BOLT, ICE_BOLT], enemies=shielded)), Cast(0, "enemy"))

    def test_damage_factor_combines_school_and_universal_modifiers(self):
        enemy = Combatant("Ghost", 200, (DamageModifier("Myth", -50), DamageModifier(UNIVERSAL, -20)))
        self.assertAlmostEqual(enemy.damage_factor("Myth"), 0.4)
        self.assertAlmostEqual(enemy.damage_factor("Ice"), 0.8)
        self.assertAlmostEqual(enemy.damage_factor(None), 0.8)

    def test_plays_the_school_the_enemy_is_weak_to(self):
        resists_myth = (Combatant("Ghost", 200, resistances={"Myth": 0.3, "Ice": -0.15}),)
        self.assertEqual(self.policy.choose(view([MYTH_BOLT, ICE_BOLT], enemies=resists_myth)), Cast(1, "enemy"))

    def test_resistance_to_every_school_applies_to_unlisted_schools(self):
        enemy = Combatant("Ghost", 200, resistances={UNIVERSAL: 0.1, "Myth": 0.4})
        self.assertAlmostEqual(enemy.damage_factor("Ice"), 0.9)
        self.assertAlmostEqual(enemy.damage_factor("Myth"), 0.6)

    def test_saves_pips_for_a_heal_when_low(self):
        dear_heal = Card("Fairy", "Heal", False, "Life", pips=3)
        choice = self.policy.choose(view([BOLT, dear_heal], health=100, pips=1))
        self.assertIsInstance(choice, Pass)
        self.assertIn("Fairy", choice.reason)

    def test_attacks_when_low_and_the_heal_is_out_of_reach(self):
        shadow_heal = Card("Big Heal", "Heal", False, "Life", pips=9)
        unknown_cost = Card("Odd Heal", "Heal", False, "Life")
        self.assertEqual(self.policy.choose(view([BOLT, shadow_heal, unknown_cost], health=100, pips=1)),
                         Cast(0, "enemy"))

    def test_does_not_save_pips_when_healthy(self):
        dear_heal = Card("Fairy", "Heal", False, "Life", pips=3)
        self.assertEqual(self.policy.choose(view([BOLT, dear_heal], health=400, pips=1)), Cast(0, "enemy"))

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

    def choose(self, policy=None, *, active_quest=None, business_here=False):
        policy = policy or MainQuestsOnly()
        return policy.choose_service(self.menu, active_quest=active_quest, business_here=business_here)

    def test_takes_the_active_quests_option_when_it_has_business_here(self):
        self.assertEqual(self.choose(active_quest="putting out the fire!", business_here=True), 2)

    def test_leaves_the_menu_when_the_active_quest_has_no_business_here(self):
        self.assertEqual(self.choose(active_quest="Trouble on Triton Avenue", business_here=False), LEAVE_MENU)
        approved = MainQuestsOnly(approved_titles=["A Good Day to Cyclops"])
        self.assertEqual(self.choose(approved, active_quest="Trouble on Triton Avenue"), LEAVE_MENU)

    def test_leaves_the_menu_when_it_does_not_list_the_active_quest(self):
        self.assertEqual(self.choose(active_quest="Another Quest", business_here=True), LEAVE_MENU)

    def test_takes_the_first_approved_title_in_the_operators_order(self):
        policy = MainQuestsOnly(approved_titles=["Putting Out the Fire!", "Trouble on Triton Avenue"])
        self.assertEqual(self.choose(policy), 2)

    def test_leaves_unapproved_menus_to_the_operator(self):
        self.assertIsNone(self.choose())
        self.assertIsNone(self.choose(MainQuestsOnly(approved_titles=["Other"])))

    def test_accepts_the_offer_of_an_approved_title_once(self):
        policy = MainQuestsOnly(approved_titles=["A Good Day to Cyclops"])
        self.choose(policy)
        self.assertEqual(policy.decide(["Help the city?"], can_go_back=True), ACCEPT)
        self.assertEqual(policy.decide(["Help again?"], can_go_back=True), GO_BACK)

    def test_an_approved_title_that_calls_itself_a_side_quest_is_declined(self):
        policy = MainQuestsOnly(approved_titles=["A Good Day to Cyclops"])
        self.choose(policy)
        self.assertEqual(policy.decide(["I am offering you a side quest."], can_go_back=True), DECLINE)


if __name__ == "__main__":
    unittest.main()
