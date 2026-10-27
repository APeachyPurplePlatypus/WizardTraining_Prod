"""Command line.

    python -m wizardtraining probe
    python -m wizardtraining play --level 7 --minutes 25 --battles 20 [--approve-quest TITLE ...] [--use-potions] [--wear-gear]
    python -m wizardtraining stop

Start the game and log in yourself first. Stop a running `play` with `stop` from a second terminal,
not with Ctrl+C or by closing the window: a run that dies without removing its hooks leaves them in
the game until it is restarted.
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import sys

from .config import Settings
from .policy import MainQuestsOnly, TakeAllQuests
from .progress import Limits


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(prog="wizardtraining", description="A starting framework for Wizard101 agents.")
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("probe", help="read the game state once, without sending keys, and save it")
    play = commands.add_parser("play", help="play main quests up to a level")
    play.add_argument("--level", type=int, default=Limits.target_level, help="stop on reaching this level")
    play.add_argument("--minutes", type=float, default=Limits.minutes, help="stop after this long")
    play.add_argument("--battles", type=int, default=Limits.max_battles, help="stop after this many battles")
    play.add_argument("--approve-quest", action="append", default=[], metavar="TITLE",
                      help="a quest title an NPC's menu may offer that you have checked is a main quest; repeatable, "
                           "earlier titles are preferred")
    play.add_argument("--side-quests", action="store_true",
                      help="accept every quest offer, side quests included, and play whichever quest is active")
    play.add_argument("--leave-world", action="store_true",
                      help="follow the main quest into the next world; by default the run stops first, because "
                           "the side quests of the current world come first")
    play.add_argument("--use-potions", action="store_true",
                      help="drink health potions the wizard already has when health is low out of battle; "
                           "potions are never bought")
    play.add_argument("--wear-gear", action="store_true",
                      help="wear the best gear in the backpack, checked after each level-up or new loot, only in "
                           "zones without enemies; nothing is bought, sold or thrown away")
    commands.add_parser("stop", help="ask a running loop to stop, by creating the STOP file")
    args = parser.parse_args(argv)
    settings = Settings.from_environment()

    if args.command == "stop":
        print(f"created {settings.request_stop()}; the run stops at its next check")
        return 0

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s", datefmt="%H:%M:%S")
    if args.command == "probe":
        from .probe import probe
        report, path = asyncio.run(probe(settings))
        print(f"report: {path}")
        return 1 if "error" in report else 0

    from .loop import play as play_quests
    limits = Limits(target_level=args.level, minutes=args.minutes, max_battles=args.battles,
                    stay_in_world=not args.leave_world)
    offers = (TakeAllQuests if args.side_quests else MainQuestsOnly)(approved_titles=args.approve_quest)
    report, path = asyncio.run(play_quests(settings, limits, offer_policy=offers, use_potions=args.use_potions,
                                            wear_gear=args.wear_gear))
    print(f"stopped: {report['stopped']}\nreport: {path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
