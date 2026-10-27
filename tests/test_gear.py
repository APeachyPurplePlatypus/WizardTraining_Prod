import unittest

from wizardtraining.gear import (Item, Requirement, Stat, Wizard, describe_stats, meets, stat_of, upgrades, wearable,
                                 worth)

ICE_LEVEL_8 = Wizard(school="Ice", level=8, max_health=717, max_mana=30)
LEVEL_10 = Requirement("list", parts=(Requirement("level at least", 10),))
LEVEL_5_ICE = Requirement("list", parts=(Requirement("level at least", 5), Requirement("school", "Ice")))
MYTH_ONLY = Requirement("list", parts=(Requirement("school", "Myth"),))


def item(id_, name, slot, effects, requirement=None, equipped=False):
    return Item(id_, name, slot, tuple(effects), requirement, equipped)


SAPPHIRE_CLOAK = item(1, "Sapphire Studded Cloak", "Robe", [("CanonicalMaxHealth", 58)], LEVEL_5_ICE)
NOVICE_ROBE = item(2, "Novice's Robe", "Robe", [("CanonicalMaxHealth", 21)])
FORESIGHT = item(3, "Cloak of Foresight", "Robe", [("CanonicalBalanceReduceDamage", 102)])
STURDY_BLADE = item(4, "Sturdy Blade", "Athame", [("CanonicalMaxHealth", 19)], LEVEL_5_ICE)
CHIPPED_KNIFE = item(5, "Chipped Knife", "Athame", [("CanonicalMaxMana", 25)], LEVEL_10)
EXPLORER_BOOTS = item(6, "Explorer Boots", "Shoes", [("CanonicalAllReduceDamage", 100)])
ROUGHSPUN = item(7, "Roughspun Shoes", "Shoes", [("CanonicalMaxHealth", 2)])
WONDERSHROUD = item(8, "Wondershroud", "Hat", [("CanonicalMaxHealth", 39)], MYTH_ONLY)
FROST_CAP = item(9, "Frost-touched Cap", "Hat", [("CanonicalIceReduceDamage", 101)])
SOFT_HOOD = item(10, "Soft Hood", "Hat", [("CanonicalMaxHealth", 4)])
STORM_HOOD = item(11, "Hood of Storms", "Hat", [("CanonicalStormFlatDamage", 3)], LEVEL_10)
BROOM = item(12, "Enchanted Broom (1 Day)", "Mount", [])
BACKPACK = [SAPPHIRE_CLOAK, NOVICE_ROBE, FORESIGHT, STURDY_BLADE, CHIPPED_KNIFE, EXPLORER_BOOTS, ROUGHSPUN,
            WONDERSHROUD, FROST_CAP, SOFT_HOOD, STORM_HOOD, BROOM]


class StatTest(unittest.TestCase):
    def test_flat_stats_are_the_index_plus_one(self):
        self.assertEqual(stat_of("CanonicalMaxHealth", 58), Stat("MaxHealth", None, 59.0))
        self.assertEqual(stat_of("CanonicalStormFlatDamage", 3), Stat("FlatDamage", "Storm", 4.0))

    def test_percentages_count_from_index_100(self):
        self.assertEqual(stat_of("CanonicalAllReduceDamage", 100), Stat("ReduceDamage", None, 1.0))
        self.assertEqual(stat_of("CanonicalIceReduceDamage", 101), Stat("ReduceDamage", "Ice", 2.0))

    def test_unknown_effects_and_percentages_below_the_base_give_nothing(self):
        self.assertIsNone(stat_of("ProvideSpell", 0))
        self.assertIsNone(stat_of("CanonicalIceDamage", 3))

    def test_describes_the_stats(self):
        self.assertEqual(describe_stats(SAPPHIRE_CLOAK), "+59 max health")
        self.assertEqual(describe_stats(EXPLORER_BOOTS), "+1% resistance (every school)")


class RequirementTest(unittest.TestCase):
    def test_level_and_school(self):
        self.assertTrue(meets(LEVEL_5_ICE, ICE_LEVEL_8))
        self.assertFalse(meets(LEVEL_10, ICE_LEVEL_8))
        self.assertFalse(meets(MYTH_ONLY, ICE_LEVEL_8))
        self.assertTrue(meets(None, ICE_LEVEL_8))

    def test_negation_and_either(self):
        not_myth = Requirement("list", parts=(Requirement("school", "Myth", negate=True),))
        ice_or_fire = Requirement("list", parts=(Requirement("school", "Fire"), Requirement("school", "Ice", either=True)))
        self.assertTrue(meets(not_myth, ICE_LEVEL_8))
        self.assertTrue(meets(ice_or_fire, ICE_LEVEL_8))

    def test_an_unknown_requirement_is_not_worn(self):
        badge = Requirement("list", parts=(Requirement("ReqHasBadge"),))
        self.assertIsNone(meets(badge, ICE_LEVEL_8))
        self.assertFalse(wearable(item(13, "Badge Hat", "Hat", [("CanonicalMaxHealth", 99)], badge), ICE_LEVEL_8))

    def test_mounts_decks_and_wands_are_left_alone(self):
        self.assertFalse(wearable(BROOM, ICE_LEVEL_8))
        self.assertFalse(wearable(item(14, "Wand", "Weapon", [("CanonicalMaxHealth", 50)]), ICE_LEVEL_8))


class UpgradeTest(unittest.TestCase):
    def test_level_8_ice_wizard_with_nothing_worn(self):
        chosen = upgrades(BACKPACK, ICE_LEVEL_8)
        self.assertEqual([gear.name for gear in chosen],
                         ["Soft Hood", "Sapphire Studded Cloak", "Explorer Boots", "Sturdy Blade"])

    def test_health_beats_another_schools_resistance(self):
        self.assertGreater(worth(SOFT_HOOD, ICE_LEVEL_8), worth(FROST_CAP, ICE_LEVEL_8) - 0.1)
        self.assertGreater(worth(NOVICE_ROBE, ICE_LEVEL_8), worth(FORESIGHT, ICE_LEVEL_8))

    def test_at_level_10_mana_replaces_the_health_athame(self):
        level_10 = Wizard(school="Ice", level=10, max_health=801, max_mana=30)
        worn = [SAPPHIRE_CLOAK, STURDY_BLADE, EXPLORER_BOOTS, SOFT_HOOD]
        items = [Item(gear.id, gear.name, gear.slot, gear.effects, gear.requirement, gear in worn) for gear in BACKPACK]
        self.assertEqual([gear.name for gear in upgrades(items, level_10)], ["Chipped Knife"])

    def test_nothing_to_change_when_the_best_is_worn(self):
        items = [Item(gear.id, gear.name, gear.slot, gear.effects, gear.requirement, gear is SAPPHIRE_CLOAK)
                 for gear in (SAPPHIRE_CLOAK, NOVICE_ROBE)]
        self.assertEqual(upgrades(items, ICE_LEVEL_8), [])

    def test_another_schools_damage_is_worth_nothing(self):
        self.assertEqual(worth(STORM_HOOD, Wizard("Ice", 10, 801, 30)), 0.0)


if __name__ == "__main__":
    unittest.main()
