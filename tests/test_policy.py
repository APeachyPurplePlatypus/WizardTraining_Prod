import unittest

from wizardtraining.policy import (ACCEPT, DECLINE, GO_BACK, LEAVE_MENU, STOP, UNIVERSAL, Card, Cast, Combatant,
                                   DamageModifier, Flee, MainQuestsOnly, Pass, RoundView, SpellTypePolicy, TakeAllQuests,
                                   problem_with)

HEAL = Card("Fairy", "Heal", True)
BOLT = Card("Fire Cat", "Damage", True)
STORM = Card("Firestorm", "AOE", True)
TOO_DEAR = Card("Big Spell", "Damage", False)
SHIELD = Card("Tower Shield", "Ward", True)
MYTH_BOLT = Card("Blood Bat", "Damage", True, "Myth")
ICE_BOLT = Card("Frost Beetle", "Damage", True, "Ice")
ONE_ENEMY = (Combatant("Ghost", 200),)


def view(cards, health=500, max_health=500, enemies=ONE_ENEMY, pips=3, mana=None):
    return RoundView(round_number=1, health=health, max_health=max_health, pips=pips, power_pips=0, cards=tuple(cards),
                     enemies=enemies, mana=mana)


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

    def test_flees_when_out_of_mana(self):
        dear_bolt = Card("Snow Serpent", "Damage", True, "Ice", pips=2)
        self.assertEqual(self.policy.choose(view([dear_bolt, HEAL], health=100, mana=1)), Flee("out of mana (1 left)"))
        self.assertEqual(self.policy.choose(view([BOLT], mana=0)), Flee("out of mana (0 left)"))

    def test_casts_a_spell_it_can_still_pay_for_before_fleeing(self):
        fire_cat = Card("Fire Cat - Starter Wand", "Damage", True, "Fire", pips=1)
        nearly_dead = (Combatant("Cyclops Legionnaire", 60),)
        self.assertEqual(self.policy.choose(view([fire_cat], mana=1, enemies=nearly_dead)), Cast(0, "enemy"))
        self.assertEqual(self.policy.choose(view([fire_cat], mana=1)), Cast(0, "enemy"))

    def test_fights_on_when_the_battle_cannot_be_fled(self):
        stuck = RoundView(round_number=2, health=500, max_health=500, pips=3, power_pips=0, cards=(BOLT,),
                          enemies=ONE_ENEMY, mana=1, can_flee=False)
        self.assertEqual(self.policy.choose(stuck), Cast(0, "enemy"))

    def test_fights_with_enough_mana_or_when_mana_is_unknown(self):
        self.assertEqual(self.policy.choose(view([BOLT], mana=2)), Cast(0, "enemy"))
        self.assertEqual(self.policy.choose(view([BOLT])), Cast(0, "enemy"))

    def test_finishes_a_weak_enemy_with_the_cheapest_sure_attack(self):
        serpent = Card("Snow Serpent", "Damage", True, "Ice", pips=2)
        beetle = Card("Frost Beetle", "Damage", True, "Ice", pips=1)
        nearly_dead = (Combatant("Warhorn", 15),)
        self.assertEqual(self.policy.choose(view([serpent, beetle], enemies=nearly_dead)), Cast(1, "enemy"))
        healthy = (Combatant("Warhorn", 285),)
        self.assertEqual(self.policy.choose(view([serpent, beetle], enemies=healthy)), Cast(0, "enemy"))

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

    def test_prefers_the_stronger_attack_when_affordable(self):
        wand = Card("Imp - Starter Wand", "Damage", True, "Life", pips=1, accuracy=80)
        serpent = Card("Snow Serpent", "Damage", True, "Ice", pips=2, accuracy=80)
        dear_serpent = Card("Snow Serpent", "Damage", False, "Ice", pips=2, accuracy=80)
        self.assertEqual(self.policy.choose(view([wand, serpent])), Cast(1, "enemy"))
        self.assertEqual(self.policy.choose(view([wand, dear_serpent])), Cast(0, "enemy"))

    def test_prefers_the_card_more_likely_to_hit(self):
        storm = Card("Thunder Snake", "Damage", True, "Storm", accuracy=70)
        fire = Card("Fire Cat", "Damage", True, "Fire", accuracy=75)
        self.assertEqual(self.policy.choose(view([storm, fire])), Cast(1, "enemy"))
        weak_to_storm = (Combatant("Troll", 135, resistances={"Storm": -0.15}),)
        self.assertEqual(self.policy.choose(view([storm, fire], enemies=weak_to_storm)), Cast(0, "enemy"))

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


AKILLES_AND_CYCLOPS = (Combatant("General Akilles", 470), Combatant("Cyclops Legionnaire", 235))
WAND = Card("Fire Cat - Starter Wand", "Damage", True, "Fire", pips=1, accuracy=75)
SERPENT_NEXT_ROUND = Card("Snow Serpent", "Damage", False, "Ice", pips=2, accuracy=80)
FREEZE = Card("Freeze", "Manipulation", True, "Ice", pips=0, accuracy=70, effects=("stun",))


class SeveralEnemiesTest(unittest.TestCase):
    policy = SpellTypePolicy()

    def test_attacks_the_enemy_with_the_least_health(self):
        self.assertEqual(self.policy.choose(view([BOLT], enemies=AKILLES_AND_CYCLOPS)), Cast(0, "enemy", 1))

    def test_finishes_any_enemy_it_surely_can(self):
        enemies = (Combatant("General Akilles", 470), Combatant("Warhorn", 15), Combatant("Cyclops", 235))
        self.assertEqual(self.policy.choose(view([WAND], enemies=enemies)), Cast(0, "enemy", 1))

    def test_stuns_the_healthiest_enemy_while_saving_a_pip_for_a_stronger_attack(self):
        hand = [WAND, SERPENT_NEXT_ROUND, FREEZE]
        self.assertEqual(self.policy.choose(view(hand, enemies=AKILLES_AND_CYCLOPS, pips=1, mana=15)),
                         Cast(2, "enemy", 0))

    def test_stuns_another_enemy_when_one_cannot_be_stunned(self):
        blocked = (Combatant("General Akilles", 470, stunnable=False), Combatant("Cyclops Legionnaire", 235))
        self.assertEqual(self.policy.choose(view([WAND, SERPENT_NEXT_ROUND, FREEZE], enemies=blocked, pips=1)),
                         Cast(2, "enemy", 1))

    def test_attacks_when_no_enemy_can_be_stunned(self):
        blocked = tuple(Combatant(enemy.name, enemy.health, stunnable=False) for enemy in AKILLES_AND_CYCLOPS)
        self.assertEqual(self.policy.choose(view([WAND, SERPENT_NEXT_ROUND, FREEZE], enemies=blocked, pips=1)),
                         Cast(0, "enemy", 1))

    def test_attacks_when_no_stronger_attack_is_a_pip_away(self):
        far_off = Card("Evil Snowman", "Damage", False, "Ice", pips=4)
        self.assertEqual(self.policy.choose(view([WAND, far_off, FREEZE], enemies=AKILLES_AND_CYCLOPS, pips=1)),
                         Cast(0, "enemy", 1))
        self.assertEqual(self.policy.choose(view([WAND, FREEZE], enemies=AKILLES_AND_CYCLOPS, pips=1)),
                         Cast(0, "enemy", 1))

    def test_attacks_when_the_stronger_attack_needs_more_mana_than_is_left(self):
        stuck = RoundView(round_number=3, health=500, max_health=500, pips=1, power_pips=0,
                          cards=(WAND, SERPENT_NEXT_ROUND, FREEZE), enemies=AKILLES_AND_CYCLOPS, mana=1, can_flee=False)
        self.assertEqual(self.policy.choose(stuck), Cast(0, "enemy", 1))

    def test_a_stun_also_saves_a_pip_against_one_enemy(self):
        self.assertEqual(self.policy.choose(view([WAND, SERPENT_NEXT_ROUND, FREEZE], pips=1)), Cast(2, "enemy", 0))

    def test_stuns_rather_than_passes_while_saving_pips_for_a_heal(self):
        pixie = Card("Pixie", "Heal", False, "Life", pips=2)
        self.assertEqual(self.policy.choose(view([WAND, pixie, FREEZE], health=100, enemies=AKILLES_AND_CYCLOPS,
                                                 pips=1)), Cast(2, "enemy", 0))

    def test_heals_when_an_enemy_holds_the_pips_to_take_what_is_left(self):
        heartbeat = Card("Heartbeat", "Heal", True, "Life", pips=1)
        beetle = Card("Frost Beetle", "Damage", True, "Ice", pips=1)
        saved_up = (Combatant("General Akilles", 145, pips=5),)
        self.assertEqual(self.policy.choose(view([beetle, heartbeat], health=357, max_health=801, enemies=saved_up,
                                                 pips=1)), Cast(1, "self"))
        spent = (Combatant("General Akilles", 145, pips=1),)
        self.assertEqual(self.policy.choose(view([beetle, heartbeat], health=357, max_health=801, enemies=spent,
                                                 pips=1)), Cast(0, "enemy", 0))

    def test_finishes_the_enemy_holding_the_pips_before_saving_for_a_heal(self):
        beetle = Card("Frost Beetle", "Damage", True, "Ice", pips=1)
        pixie = Card("Pixie", "Heal", False, "Life", pips=2)
        alicane = (Combatant("Alicane Swiftarrow", 16, pips=3),)
        self.assertEqual(self.policy.choose(view([beetle, pixie], health=288, max_health=832, enemies=alicane, pips=1)),
                         Cast(0, "enemy", 0))

    def test_heals_when_finishing_one_enemy_still_leaves_a_big_hit(self):
        beetle = Card("Frost Beetle", "Damage", True, "Ice", pips=1)
        heartbeat = Card("Heartbeat", "Heal", True, "Life", pips=1)
        enemies = (Combatant("Magma Man", 16, pips=1), Combatant("Alicane Swiftarrow", 480, pips=4))
        self.assertEqual(self.policy.choose(view([beetle, heartbeat], health=300, max_health=832, enemies=enemies,
                                                 pips=1)), Cast(1, "self"))

    def test_stuns_the_enemy_holding_the_pips_when_there_is_no_heal(self):
        beetle = Card("Frost Beetle", "Damage", True, "Ice", pips=1)
        saved_up = (Combatant("General Akilles", 145, pips=5),)
        self.assertEqual(self.policy.choose(view([beetle, FREEZE], health=357, max_health=801, enemies=saved_up,
                                                 pips=1)), Cast(1, "enemy", 0))

    def test_stuns_the_enemy_holding_the_most_pips(self):
        enemies = (Combatant("General Akilles", 470, pips=1), Combatant("Cyclops Legionnaire", 235, pips=3))
        self.assertEqual(self.policy.choose(view([WAND, SERPENT_NEXT_ROUND, FREEZE], enemies=enemies, pips=1)),
                         Cast(2, "enemy", 1))

    def test_heals_before_stunning_when_low(self):
        hand = [WAND, SERPENT_NEXT_ROUND, FREEZE, HEAL]
        self.assertEqual(self.policy.choose(view(hand, health=100, enemies=AKILLES_AND_CYCLOPS, pips=1)),
                         Cast(3, "self"))


class ProblemWithTest(unittest.TestCase):
    def test_a_valid_choice_has_no_problem(self):
        self.assertIsNone(problem_with(Cast(0, "enemy"), view([BOLT])))

    def test_refuses_cards_that_cannot_be_cast(self):
        self.assertIn("not castable", problem_with(Cast(0, "enemy"), view([TOO_DEAR])))
        self.assertIn("not castable", problem_with(Cast(5, "enemy"), view([BOLT])))

    def test_refuses_missing_enemies_and_unknown_targets(self):
        self.assertIn("not there", problem_with(Cast(0, "enemy", enemy=3), view([BOLT])))
        self.assertIn("unknown target", problem_with(Cast(0, "the boss"), view([BOLT])))


class TakeAllQuestsTest(unittest.TestCase):
    def test_accepts_every_offer(self):
        policy = TakeAllQuests()
        self.assertTrue(policy.side_quests)
        self.assertFalse(MainQuestsOnly().side_quests)
        self.assertEqual(policy.decide(["Will you help? I'm offering you a side quest."], can_go_back=True), ACCEPT)
        self.assertEqual(policy.decide(["Will you help me?"], can_go_back=False), ACCEPT)

    def test_takes_a_menus_first_quest_with_none_active(self):
        policy = TakeAllQuests(approved_titles=["Putting Out the Fire!"])
        options = ["A Good Day to Cyclops", "Putting Out the Fire!"]
        self.assertEqual(policy.choose_service(options, active_quest=None, business_here=False), 1)
        self.assertEqual(TakeAllQuests().choose_service(options, active_quest=None, business_here=False), 0)
        self.assertEqual(TakeAllQuests().choose_service(options, active_quest="Other", business_here=False), LEAVE_MENU)


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
