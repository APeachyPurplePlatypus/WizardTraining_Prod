import asyncio
import unittest
from types import SimpleNamespace
from unittest import mock

from wizardtraining import gametravel, worldgate


class StandIn:
    def __init__(self, name, children=(), text="", visible=True):
        self._name, self._children, self._text, self._visible = name, list(children), text, visible

    async def name(self):
        return self._name

    async def is_visible(self):
        return self._visible

    async def maybe_text(self):
        return self._text

    async def children(self):
        return self._children


class SpiralDoor:
    """The Spiral Map as the game showed it in the Ravenwood teleporter room: Wizard City and Krokotopia available."""

    def __init__(self):
        self.zone, self.clicked, self.chosen = "WizardCity/WC_Ravenwood_Teleporter", [], None
        options = StandIn("optionWindow", [StandIn("wbtnKrokotopia"), StandIn("wbtnWizardCity"),
                                           StandIn("wbtnMooShu", visible=False)])
        controls = StandIn("ControlSprite", [StandIn("title", text="Spiral Map"), StandIn("teleportButton", text="Go To World"),
                                             StandIn("cancelButton", text="Exit"), options])
        self.root = StandIn("root", [StandIn("WorldView", [StandIn("", [StandIn("messageBoxBG", [controls])])])])

    def client(self):
        door = self

        async def zone_name():
            return door.zone

        async def is_loading():
            return False

        return SimpleNamespace(root_window=self.root, zone_name=zone_name, is_loading=is_loading)

    async def click(self, client, path):
        self.clicked.append(path[-1])
        if path[-1].startswith("wbtn"):
            self.chosen = path[-1][4:]
        if path[-1] == "teleportButton" and self.chosen:
            self.zone = f"{self.chosen}/KT_WorldTeleporter"


def run(door, function, *args):
    patches = (mock.patch.object(worldgate, "click", door.click), mock.patch.object(worldgate, "CHOOSE_SETTLE_SECONDS", 0),
               mock.patch.object(gametravel, "ZONE_CHANGE_WAIT_SECONDS", 0.2),
               mock.patch.object(gametravel, "ZONE_CHANGE_POLL_SECONDS", 0.01))
    for patch in patches:
        patch.start()
    try:
        return asyncio.run(function(door.client(), *args))
    finally:
        for patch in patches:
            patch.stop()


class WorldGateTest(unittest.TestCase):
    def test_the_spiral_map_is_recognised_by_its_title(self):
        self.assertTrue(run(SpiralDoor(), worldgate.spiral_map_open))

    def test_the_quests_world_is_chosen_and_go_to_world_pressed(self):
        door = SpiralDoor()
        self.assertIsNone(run(door, worldgate.go_to_world, "Krokotopia"))
        self.assertEqual(door.clicked, ["wbtnKrokotopia", "teleportButton"])
        self.assertEqual(door.zone, "Krokotopia/KT_WorldTeleporter")

    def test_a_world_not_yet_open_is_not_clicked(self):
        door = SpiralDoor()
        self.assertEqual(run(door, worldgate.go_to_world, "MooShu"), "MooShu is not among the available worlds")
        self.assertEqual(door.clicked, [])


if __name__ == "__main__":
    unittest.main()
