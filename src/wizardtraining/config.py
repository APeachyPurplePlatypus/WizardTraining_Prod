"""Where the framework finds the optional Deimos checkout, and where it keeps reports and the STOP file.

Both come from environment variables, so no machine's paths are written into the code:
- WIZARDTRAINING_DEIMOS: a Deimos-Wizard101 checkout. Enables the "collision" route method.
- WIZARDTRAINING_RUNTIME: the folder for reports and the STOP file. Defaults to ./runtime.

The STOP file is the only safe way to end a run early: the loop checks for it on every walking tick
and between turns, then removes its hooks from the game before exiting.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

DEIMOS_VARIABLE = "WIZARDTRAINING_DEIMOS"
RUNTIME_VARIABLE = "WIZARDTRAINING_RUNTIME"
DEFAULT_RUNTIME_FOLDER = "runtime"
STOP_FILE_NAME = "STOP"
KNOWLEDGE_FILE_NAME = "knowledge.json"
DEFAULT_DEIMOS_CHECKOUT = Path(__file__).resolve().parents[3] / "wiz101-live" / "Deimos-Wizard101"


@dataclass(frozen=True)
class Settings:
    deimos_root: Path | None
    runtime_folder: Path

    @classmethod
    def from_environment(cls, environment=None) -> "Settings":
        use_default_deimos = environment is None
        environment = os.environ if environment is None else environment
        deimos = environment.get(DEIMOS_VARIABLE)
        if deimos:
            deimos_root = Path(deimos)
        elif use_default_deimos and DEFAULT_DEIMOS_CHECKOUT.exists():
            deimos_root = DEFAULT_DEIMOS_CHECKOUT
        else:
            deimos_root = None
        runtime = environment.get(RUNTIME_VARIABLE) or DEFAULT_RUNTIME_FOLDER
        return cls(deimos_root=deimos_root, runtime_folder=Path(runtime))

    @property
    def stop_file(self) -> Path:
        return self.runtime_folder / STOP_FILE_NAME

    @property
    def knowledge_file(self) -> Path:
        return self.runtime_folder / KNOWLEDGE_FILE_NAME

    def stop_requested(self) -> bool:
        return self.stop_file.exists()

    def request_stop(self) -> Path:
        self.runtime_folder.mkdir(parents=True, exist_ok=True)
        self.stop_file.touch()
        return self.stop_file

    def clear_stop(self) -> None:
        self.stop_file.unlink(missing_ok=True)
