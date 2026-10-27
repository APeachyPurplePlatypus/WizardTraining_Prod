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

School ids, such as `2448141` for Myth and `80289` for universal, come from WizWalker's `conditionals.school_id_to_names` and Deimos's damage maths (`src/combat_math.py`).

## Live memory: available, not used yet

Worth reaching for before adding guesswork:

- **An enemy's behavior template, outside battle:** entity → `fetch_npc_behavior_template()` → `level()`, `boss_mob()`, `school_of_focus()`, `starting_health()`, `aggressive_factor()`, `mob_title()`. Enemy level, school and boss status before a fight: for avoiding enemies far above the wizard, or picking a deck.
- **More of a combatant:** `primary_magic_school_id()`, `num_pips()`, `num_power_pips()`, `stunned()`, `is_minion()`, and the caster side of `get_stats()`: `dmg_bonus_percent()`, `critical_hit_rating_by_school()`, `ap_bonus_percent()` (pierce), `block_rating_by_school()`. Deimos's `src/combat_math.py` shows how they combine into a damage estimate.
- **Spell details:** `spell_template()` → `description()`, `accuracy()`, `effects()`; `spell_effects()` on a graphical spell gives each effect's type and parameter (damage, heal amount, rounds).
- **The duel:** `client.duel` → `round_num()`, `planning_timer()`, `execution_order()`.
- **The character:** `character_registry()` → `active_quest_id()`, `active_goal_id()`; deck, equipment and inventory behaviors on `client.client_object` (`try_get_deck_behavior()`, and so on).
- **The wizard's own stats:** `client.stats` also holds `potion_max()`, damage, resistance, critical, block and pierce by school.

## Zone files

| File | Reader | Used for |
|---|---|---|
| `collision.bcd` | Deimos `CollisionWorld`, `get_walk_grid`, `walkable_union`, `zone_bcd_walls` | the walk grid, walls, walkable pieces |
| `zone.nav` | Deimos | the nav waypoint graph |
| `volumes.xml` | `teleports.parse_teleport_volumes` (layout inferred) | teleport volumes between walkable pieces; each shop or building door in a street is one too |
| `gamedata.bin` | `placed.parse_placed_objects` (layout inferred) | placed objects: gates, quest objects, signs |
| `pathNodeData.bin`, `pathData.xml` | `patrols.parse_nodes`, `parse_paths` (layout inferred) | enemy patrol paths, named after their enemies |
| `Root.wad` `Locale/en-US/*.lang` | `language.LanguageFiles` | quest titles and enemy names from codes such as `QuestTitle_1625D8` and `WizardMobs_00000331` |

The inferred layouts are described in each parser's module docstring with the evidence that confirmed them.
