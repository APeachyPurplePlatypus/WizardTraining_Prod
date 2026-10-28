import unittest

from wizardtraining.policy import (ACCEPT, DECLINE, GO_BACK, LEAVE_MENU, STOP, UNIVERSAL, Card, Cast, Combatant,
                                   DamageModifier, Enchant, Flee, MainQuestsOnly, Pass, RoundView, SpellTypePolicy,
                                   TakeAllQuests, problem_with)

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


class StrategyPolicyTest(unittest.TestCase):
    """The same round played by each combat strategy (strategies.py)."""

    def test_heal_earlier_heals_at_half_health(self):
        from wizardtraining.strategies import COMBAT_STRATEGIES
        half = view([BOLT, HEAL], health=250)
        self.assertEqual(SpellTypePolicy().choose(half), Cast(0, "enemy"))
        self.assertEqual(SpellTypePolicy(COMBAT_STRATEGIES[1]).choose(half), Cast(1, "self"))

    def test_most_dangerous_first_attacks_the_boss_not_the_guard(self):
        from wizardtraining.strategies import COMBAT_STRATEGIES
        boss_and_guard = (Combatant("Lord Nightshade", 690, pips=3), Combatant("Field Guard", 395, pips=1))
        self.assertEqual(SpellTypePolicy().choose(view([BOLT], enemies=boss_and_guard)), Cast(0, "enemy", 1))
        self.assertEqual(SpellTypePolicy(COMBAT_STRATEGIES[2]).choose(view([BOLT], enemies=boss_and_guard)),
                         Cast(0, "enemy", 0))

    def test_the_strategy_is_chosen_from_the_enemies_at_each_fights_first_round(self):
        from wizardtraining.strategies import COMBAT_STRATEGIES
        asked = []

        def strategy_for(situation):
            asked.append(situation)
            return COMBAT_STRATEGIES[1] if situation == "Flame Servant" else COMBAT_STRATEGIES[2]

        policy = SpellTypePolicy(strategy_for=strategy_for)
        servants = (Combatant("Flame Servant", 310), Combatant("Flame Servant", 310))
        policy.new_fight()
        policy.choose(view([BOLT], enemies=servants))
        policy.choose(view([BOLT], enemies=servants[:1]))
        self.assertEqual((policy.strategy, asked), (COMBAT_STRATEGIES[1], ["Flame Servant"]))
        policy.new_fight()
        policy.choose(view([BOLT], enemies=(Combatant("Nirini Sentry", 285),)))
        self.assertEqual((policy.strategy, asked), (COMBAT_STRATEGIES[2], ["Flame Servant", "Nirini Sentry"]))

    def test_heal_earlier_attacks_rather_than_passing_for_a_heal_out_of_danger(self):
        from wizardtraining.strategies import COMBAT_STRATEGIES
        pixie = Card("Pixie", "Heal", False, "Life", pips=2)
        beetle = Card("Frost Beetle", "Damage", True, "Ice", pips=1)
        sentry = (Combatant("Nirini Sentry", 220, pips=1),)
        half = view([beetle, pixie], health=539, max_health=1102, enemies=sentry, pips=1)
        self.assertEqual(SpellTypePolicy(COMBAT_STRATEGIES[1]).choose(half), Cast(0, "enemy", 0))
        low = view([beetle, pixie], health=321, max_health=1102, enemies=sentry, pips=1)
        self.assertIsInstance(SpellTypePolicy(COMBAT_STRATEGIES[1]).choose(low), Pass)

    def test_save_pips_for_bigger_cards_passes_for_a_two_pip_wait(self):
        from wizardtraining.strategies import COMBAT_STRATEGIES
        beetle = Card("Frost Beetle", "Damage", True, "Ice", pips=1)
        snowman = Card("Evil Snowman", "Damage", False, "Ice", pips=3)
        round_one = view([beetle, snowman], pips=1)
        self.assertEqual(SpellTypePolicy().choose(round_one), Cast(0, "enemy", 0))
        self.assertIsInstance(SpellTypePolicy(COMBAT_STRATEGIES[3]).choose(round_one), Pass)


class QuestFinderMenuTest(unittest.TestCase):
    def test_at_the_quest_finders_giver_the_first_quest_is_taken_not_a_shop(self):
        policy = TakeAllQuests()
        menu = ["Wizards in the Mist", "Recipe Shop", "Rematch Trading"]
        self.assertEqual(policy.choose_service(menu, active_quest="Quest Finder", business_here=False), 0)
        self.assertEqual(policy.choose_service(["Recipe Shop", "Wizards in the Mist"], active_quest="Quest Finder",
                                               business_here=False), 1)
        self.assertEqual(policy.choose_service(["Recipe Shop", "Rematch Trading"], active_quest="Quest Finder",
                                               business_here=False), LEAVE_MENU)
        self.assertEqual(policy.choose_service(menu, active_quest="Looking Sharp!", business_here=False), LEAVE_MENU)


class SpellTypePolicyTest(unittest.TestCase):
    def setUp(self):
        self.policy = SpellTypePolicy()

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
        other = TakeAllQuests()
        self.assertEqual(other.choose_service(options, active_quest="Other", business_here=False), 0)
        self.assertEqual(other.choose_service(options, active_quest="Other", business_here=False), 1)
        self.assertEqual(other.choose_service(options, active_quest="Other", business_here=False), LEAVE_MENU)


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


class TrapTest(unittest.TestCase):
    TRAP = Card("Ice Trap", "Trap", True, "Ice", 0)
    SNOWMAN = Card("Evil Snowman", "Damage", False, "Ice", 3)
    BEETLE = Card("Frost Beetle", "Damage", True, "Ice", 1)

    def test_a_trap_goes_on_the_target_before_a_big_hit(self):
        snowmen = (Combatant("Evil Snowman", 310), Combatant("Evil Snowman", 310))
        self.assertEqual(SpellTypePolicy().choose(view([self.BEETLE, self.TRAP, self.SNOWMAN], pips=2, enemies=snowmen)),
                         Cast(1, "enemy", 0))

    def test_no_second_trap_on_a_trapped_enemy_and_none_without_a_big_hit(self):
        trapped = (Combatant("Evil Snowman", 310, incoming=(DamageModifier("Ice", 40),)),)
        self.assertNotEqual(SpellTypePolicy().choose(view([self.BEETLE, self.TRAP, self.SNOWMAN], pips=2,
                                                          enemies=trapped)).card, 1)
        self.assertNotEqual(SpellTypePolicy().choose(view([self.BEETLE, self.TRAP], pips=1,
                                                          enemies=(Combatant("Ghost", 300),))).card, 1)


class NoEffectTest(unittest.TestCase):
    SNAKE = Card("Thunder Snake - Starter Wand", "Damage", True, "Storm", 1, accuracy=70)
    CAT = Card("Fire Cat - Starter Wand", "Damage", True, "Fire", 1, accuracy=75)

    def test_the_most_accurate_of_the_cheapest_finishers(self):
        guard = (Combatant("Field Guard", 45),)
        self.assertEqual(SpellTypePolicy().choose(view([self.SNAKE, self.CAT], enemies=guard)), Cast(1, "enemy", 0))

    def test_a_card_that_left_the_target_as_it_was_is_not_played_again_this_fight(self):
        policy = SpellTypePolicy()
        guard = (Combatant("Field Guard", 300),)
        first = policy.choose(view([self.SNAKE, self.CAT], enemies=guard))
        played = [self.SNAKE, self.CAT][first.card].name
        second = policy.choose(view([self.SNAKE, self.CAT], enemies=guard))
        self.assertNotEqual([self.SNAKE, self.CAT][second.card].name, played)
        policy.new_fight()
        self.assertEqual(policy.choose(view([self.SNAKE, self.CAT], enemies=guard)), first)

    def test_finishing_one_of_two_alike_enemies_is_an_effect(self):
        policy = SpellTypePolicy()
        two = (Combatant("Lost Soul", 55), Combatant("Lost Soul", 55))
        first = policy.choose(view([self.CAT, self.SNAKE], enemies=two))
        self.assertEqual(policy.choose(view([self.CAT, self.SNAKE], enemies=two[:1])).card, first.card)


class MenuQuestTest(unittest.TestCase):
    def test_a_world_is_not_a_quest_of_this_world(self):
        from wizardtraining.policy import names_a_quest
        self.assertTrue(names_a_quest("Colossal Trouble"))
        self.assertFalse(names_a_quest("Grizzleheim"))
        self.assertFalse(names_a_quest("Housing Shop"))

    def test_a_new_quest_in_a_menu_is_taken_once_while_another_quest_is_active(self):
        policy = TakeAllQuests()
        options = ["Colossal Trouble", "Grizzleheim"]
        self.assertEqual(policy.choose_service(options, active_quest="Hey, Penny", business_here=False), 0)
        self.assertEqual(policy.choose_service(options, active_quest="Hey, Penny", business_here=False), LEAVE_MENU)
        self.assertEqual(policy.choose_service(["Grizzleheim"], active_quest="Quest Finder", business_here=True),
                         LEAVE_MENU)


class ExtractTest(unittest.TestCase):
    """Gilda Burke ("Know Thine Enemy"): an Extract spell enchants a damage spell, whose hit takes the essence."""
    EXTRACT = Card("Extract Undead", "Enchantment", True, "Myth", 0)
    BEETLE = Card("Frost Beetle", "Damage", True, "Ice", 1)
    SERPENT = Card("Snow Serpent", "Damage", True, "Ice", 2)
    SOULS = (Combatant("Ghoul", 300), Combatant("Lost Soul", 200))

    def policy(self, wanted=("Lost Soul",)):
        return SpellTypePolicy(essence_from=lambda: set(wanted))

    def test_the_cheapest_attack_is_enchanted_while_an_essence_is_needed(self):
        round_view = view([self.SERPENT, self.EXTRACT, self.BEETLE], enemies=self.SOULS)
        self.assertEqual(self.policy().choose(round_view), Enchant(1, 2))

    def test_the_enchanted_attack_hits_the_enemy_whose_essence_is_needed_once_a_fight(self):
        enchanted = Card("Frost Beetle", "Damage", True, "Ice", 1, enchanted=True)
        policy = self.policy()
        self.assertEqual(policy.choose(view([self.SERPENT, enchanted], enemies=self.SOULS)), Cast(1, "enemy", 1))
        self.assertEqual(policy.choose(view([self.SERPENT, self.EXTRACT, self.BEETLE], enemies=self.SOULS)),
                         Cast(0, "enemy", 1))

    def test_no_essence_needed_or_no_such_enemy_plays_as_usual(self):
        round_view = view([self.EXTRACT, self.BEETLE], enemies=(Combatant("Ghoul", 300),))
        self.assertEqual(self.policy().choose(round_view), Cast(1, "enemy", 0))
        self.assertEqual(self.policy(wanted=()).choose(view([self.EXTRACT, self.BEETLE], enemies=self.SOULS)),
                         Cast(1, "enemy", 1))

    def test_without_an_extract_another_enemy_is_hit_or_the_victim_stunned(self):
        freeze = Card("Freeze", "Manipulation", True, "Ice", 0, effects=("stun",))
        self.assertEqual(self.policy().choose(view([self.BEETLE], enemies=self.SOULS)), Cast(0, "enemy", 0))
        alone = (Combatant("Lost Soul", 55),)
        self.assertEqual(self.policy().choose(view([self.BEETLE, freeze], enemies=alone)), Cast(1, "enemy", 0))
        self.assertEqual(self.policy().choose(view([self.BEETLE], enemies=alone)), Cast(0, "enemy", 0))

    def test_an_item_card_or_a_refused_card_is_not_enchanted(self):
        wand = Card("Dark Sprite - Starter Wand", "Damage", True, "Death", 1, item_card=True)
        souls = (Combatant("Lost Soul", 55),)
        self.assertEqual(self.policy().choose(view([wand, self.EXTRACT, self.SERPENT], enemies=souls)), Enchant(1, 2))
        policy = self.policy()
        policy.enchant_refused("Snow Serpent")
        self.assertEqual(policy.choose(view([wand, self.EXTRACT, self.SERPENT], enemies=souls)), Cast(0, "enemy", 0))

    def test_pips_are_saved_while_the_decks_attacks_cost_more_than_the_wizard_has(self):
        wand = Card("Frost Beetle - Starter Wand", "Damage", True, "Ice", 1)
        serpent = Card("Snow Serpent", "Damage", False, "Ice", 2)
        choice = self.policy().choose(view([wand, self.EXTRACT, serpent], pips=1, enemies=(Combatant("Lost Soul", 55),)))
        self.assertIsInstance(choice, Pass)
        self.assertIn("Snow Serpent", choice.reason)

    def test_low_health_heals_before_extracting(self):
        round_view = view([self.EXTRACT, self.BEETLE, HEAL], health=100, enemies=self.SOULS)
        self.assertEqual(self.policy().choose(round_view), Cast(2, "self"))

    def test_an_enchantment_onto_itself_or_an_uncastable_card_is_refused(self):
        round_view = view([self.EXTRACT, TOO_DEAR])
        self.assertIsNotNone(problem_with(Enchant(0, 1), round_view))
        self.assertIsNotNone(problem_with(Enchant(0, 0), round_view))

if __name__ == "__main__":
    unittest.main()
