# Game data

Decide from the game's own data before guessing or exploring. There are two sources:

- **Live memory**, read through WizWalker (version 1.8.2, vendored in Deimos). The names below are WizWalker's; check them against the vendored source (`libs/wizwalker/wizwalker/memory/memory_objects/`) before relying on one this framework does not use yet.
- **Zone files** in the game's WAD archives, read with Deimos's readers or this package's own parsers.

Everything here is read-only. WizWalker can also write memory (teleport, `goto`, speed, freecam) and send chat; the framework never does. See [safety.md](safety.md).

## Live memory: used now

| Data | WizWalker | Used for |
|---|---|---|
| Zone | `client.zone_name()` | planners per zone, door loops, zone changes in the log |
| Position, facing | `client.body.position()`, `yaw()` | walking, turning, arrival |
| Level, health, mana, gold, potions | `client.stats.reference_level()`, `current_hitpoints()`, `max_hitpoints()`, `current_mana()`, `current_gold()`, `potion_charge()` | resting, wisps, potions, stopping at the target level |
| States | `client.is_loading()`, `in_battle()`, `is_in_dialog()`, `is_in_npc_range()` | turn choice, doors (X), talking |
| Quests | `client.quest_manager()` → quest data: `name_lang_key`, `mainline`, `ready_to_turn_in`, goals: `goal_type`, `goal_destination_zone`, `client_tag_list`, `no_quest_helper`, `madlib_block` | main quests only, goal handlers, targets without an arrow |
| Quest arrow | `client.quest_position.position()` | where to go |
| Entities | `client.get_base_entity_list()` → `object_name()`, `location()`, `object_template().display_name()` | enemies, wisps, NPCs, duel circles |
| UI windows | `client.root_window` → `children()`, `name()`, `is_visible()`, `maybe_text()` | dialogs, NPC menus, popups, the potion button |
| Battle | `CombatHandler`: members' `health()`, `is_dead()`, `name()`; cards' `name()`, `type_name()`, `is_castable()` | the combat policy |
| Card school and cost | card → `wait_for_graphical_spell()` → `magic_school_id()`, `pip_cost().spell_rank()` | wards, resistances, saving pips to heal |
| Enemy shields, wards, traps | member → `get_participant().hanging_effects()` → `effect_type()`, `effect_param()`, `damage_type()` | card choice |
| Enemy resistances | member → `get_stats()` → `dmg_reduce_percent()` (one value per school, in the order Fire, Ice, Storm, Myth, Life, Death, Balance, Star, Sun, Moon, Gardening, Shadow) and `dmg_reduce_percent_all()` | card choice |

| The wizard's school and real level | `client_object.search_behavior_by_name("BasicMagicSchoolBehavior")`, offsets 128 (`m_schoolOfFocus`, a school id) and 132 (`m_level`); `reference_level()` lags behind a level-up until the next zone change | gear requirements |
| Items, worn and in the backpack | behaviors `WizardEquipmentBehavior` and `WizardInventoryBehavior`, `m_itemList` at 120 and 112 → each item's template (offset 88, a `WizItemTemplate`): `m_displayName` 168, `m_adjectiveList` 248 (the slot word), `m_equipRequirements` 280, `m_equipEffects` 296 | `--wear-gear` (`equipment.py`) |
| An item's stats | each `StatisticEffectInfo` in `m_equipEffects`: `m_effectName` 72 (such as `CanonicalMaxHealth`, `CanonicalIceReduceDamage`) and `m_lookupIndex` 104 | `gear.py` |
| An item's requirements | `RequirementList` (`m_requirements` 80); each has `m_applyNOT` 72 and `m_operator` 76 (0 AND, 1 OR); `ReqMagicLevel` `m_numericValue` 80, `m_operatorType` 84 (3 is "at least"); `ReqSchoolOfFocus` `m_magicSchool` 80 | `gear.py` |

These offsets come from the type dump `wiztype` makes of the running client (`%APPDATA%\Deimos\types\Wizard_1_610.json` for this game version), not from WizWalker, which has no item readers. Check them against a new dump after a game update. The canonical stat effects are defined in Root.wad's `GameEffectData/CanonicalStatEffects.xml`, each naming a stat table (`Damage_Ice`, `MaxHealth_AllSchools`, ...). The tables themselves were not found in the installed files, so values come from the lookup index as measured in the game: a flat stat gives index + 1 (58, 19 and 4 gave +59, +20 and +5 health), a percentage index - 99 (100 gave 1%).

School ids, such as `2448141` for Myth and `80289` for universal, come from WizWalker's `conditionals.school_id_to_names` and Deimos's damage maths (`src/combat_math.py`).

## Live memory: available, not used yet

Worth reaching for before adding guesswork:

- **An enemy's behavior template, outside battle:** entity → `fetch_npc_behavior_template()` → `level()`, `boss_mob()`, `school_of_focus()`, `starting_health()`, `aggressive_factor()`, `mob_title()`. Enemy level, school and boss status before a fight: for avoiding enemies far above the wizard, or picking a deck.
- **More of a combatant:** `primary_magic_school_id()`, `num_pips()`, `num_power_pips()`, `stunned()`, `is_minion()`, and the caster side of `get_stats()`: `dmg_bonus_percent()`, `critical_hit_rating_by_school()`, `ap_bonus_percent()` (pierce), `block_rating_by_school()`. Deimos's `src/combat_math.py` shows how they combine into a damage estimate.
- **Spell details:** `spell_template()` → `description()`, `accuracy()`, `effects()`; `spell_effects()` on a graphical spell gives each effect's type and parameter (damage, heal amount, rounds).
- **The duel:** `client.duel` → `round_num()`, `planning_timer()`, `execution_order()`.
- **The character:** `character_registry()` → `active_quest_id()`, `active_goal_id()`; the deck behavior on `client.client_object` (`try_get_deck_behavior()`). Equipment and inventory are used now (above).
- **The spellbook's pages:** the HUD's `btnSpellbook` opens `WorldView/DeckConfiguration`, whose tabs are `CharStats`, `Inventory`, `Deck`, `Quest`, `Maps`, `Crafting`, `Preferences` and `Help`. The Quest tab could let the framework choose the active quest without the Q key, which hides the NPC range prompt.
- **The wizard's own stats:** `client.stats` also holds `potion_max()`, damage, resistance, critical, block and pierce by school.

## Zone files

| File | Reader | Used for |
|---|---|---|
| `collision.bcd` | Deimos `CollisionWorld`, `get_walk_grid`, `walkable_union`, `zone_bcd_walls` | the walk grid, walls, walkable pieces |
| `gamedata.bin` plus each placed object's model | Deimos `entity_collision.build_zone_static_shapes` (needs `katsuba` 0.4, `kinif`, `wiztype`) | footprints of tents, trees and crates, taken out of the walkable area |
| `zone.nav` | Deimos | the nav waypoint graph |
| `volumes.xml` | `teleports.parse_teleport_volumes` (layout inferred) | teleport volumes between walkable pieces; each shop or building door in a street is one too |
| `gamedata.bin` | `placed.parse_placed_objects` (layout inferred) | placed objects: gates, quest objects, signs |
| `pathNodeData.bin`, `pathData.xml` | `patrols.parse_nodes`, `parse_paths` (layout inferred) | enemy patrol paths, named after their enemies |
| `Root.wad` `Locale/en-US/*.lang` | `language.LanguageFiles` | quest titles and enemy names from codes such as `QuestTitle_1625D8` and `WizardMobs_00000331` |

The inferred layouts are described in each parser's module docstring with the evidence that confirmed them.
