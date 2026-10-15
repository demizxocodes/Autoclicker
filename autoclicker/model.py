"""Click points, run settings, and the on-disk profile store."""

from __future__ import annotations

import json
import os
import string
import sys
from dataclasses import asdict, dataclass, field
from pathlib import Path

BUTTONS = ("left", "right", "middle")
CLICK_TYPES = {1: "Single", 2: "Double"}
MODES = ("forever", "rounds", "time")
TIME_UNITS = {"seconds": 1, "minutes": 60, "hours": 3600}

# Shortest allowed wait before a click, so a sequence can never spin the CPU.
MIN_DELAY = 0.01

FILE_VERSION = 1
DEFAULT_PROFILE = "Default"


@dataclass
class ClickPoint:
    name: str
    x: int
    y: int
    delay: float = 1.0  # seconds to wait before this click
    button: str = "left"
    clicks: int = 1  # 1 = single click, 2 = double click
    # Window this point belongs to, for background clicking (Windows only).
    window_title: str = ""
    window_class: str = ""
    rel_x: int = 0  # position inside that window's client area
    rel_y: int = 0

    @classmethod
    def from_dict(cls, data: dict) -> "ClickPoint":
        button = data.get("button", "left")
        clicks = int(data.get("clicks", 1))
        return cls(
            name=str(data.get("name", "?")),
            x=int(data["x"]),
            y=int(data["y"]),
            delay=max(MIN_DELAY, float(data.get("delay", 1.0))),
            button=button if button in BUTTONS else "left",
            clicks=clicks if clicks in CLICK_TYPES else 1,
            window_title=str(data.get("window_title", "")),
            window_class=str(data.get("window_class", "")),
            rel_x=int(data.get("rel_x", 0)),
            rel_y=int(data.get("rel_y", 0)),
        )


@dataclass
class RunSettings:
    mode: str = "forever"  # forever | rounds | time
    rounds: int = 10
    duration: float = 1.0
    duration_unit: str = "minutes"
    background: bool = True  # click without moving the real mouse

    @property
    def duration_seconds(self) -> float:
        return self.duration * TIME_UNITS[self.duration_unit]

    @classmethod
    def from_dict(cls, data: dict) -> "RunSettings":
        mode = data.get("mode", "forever")
        unit = data.get("duration_unit", "minutes")
        return cls(
            mode=mode if mode in MODES else "forever",
            rounds=max(1, int(data.get("rounds", 10))),
            duration=max(0.0, float(data.get("duration", 1.0))),
            duration_unit=unit if unit in TIME_UNITS else "minutes",
            background=bool(data.get("background", True)),
        )


@dataclass
class Profile:
    points: list[ClickPoint] = field(default_factory=list)
    settings: RunSettings = field(default_factory=RunSettings)

    def to_dict(self) -> dict:
        return {
            "points": [asdict(p) for p in self.points],
            "settings": asdict(self.settings),
        }

    @classmethod
    def from_dict(cls, data: dict) -> "Profile":
        return cls(
            points=[ClickPoint.from_dict(p) for p in data.get("points", [])],
            settings=RunSettings.from_dict(data.get("settings", {})),
        )


def next_point_name(points: list[ClickPoint]) -> str:
    """First unused letter A..Z, then P27, P28, ..."""
    used = {p.name for p in points}
    for letter in string.ascii_uppercase:
        if letter not in used:
            return letter
    n = 27
    while f"P{n}" in used:
        n += 1
    return f"P{n}"


def default_store_path() -> Path:
    if sys.platform == "win32":
        base = Path(os.environ.get("APPDATA") or Path.home() / "AppData" / "Roaming")
        return base / "Autoclicker" / "profiles.json"
    base = Path(os.environ.get("XDG_CONFIG_HOME") or Path.home() / ".config")
    return base / "autoclicker" / "profiles.json"


class ProfileStore:
    """All profiles live in one JSON file, rewritten atomically on every save."""

    def __init__(self, path: Path | None = None):
        self.path = Path(path) if path else default_store_path()
        self.profiles: dict[str, Profile] = {}
        self.last_profile = DEFAULT_PROFILE

    def load(self) -> None:
        self.profiles = {}
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
            for name, raw in data.get("profiles", {}).items():
                self.profiles[name] = Profile.from_dict(raw)
            self.last_profile = data.get("last_profile", DEFAULT_PROFILE)
        except FileNotFoundError:
            pass
        except (ValueError, KeyError, TypeError, AttributeError):
            # Keep the unreadable file for the user instead of overwriting it.
            self.path.replace(self.path.with_suffix(".json.bak"))
            self.profiles = {}
        if not self.profiles:
            self.profiles[DEFAULT_PROFILE] = Profile()
        if self.last_profile not in self.profiles:
            self.last_profile = next(iter(self.profiles))

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        data = {
            "version": FILE_VERSION,
            "last_profile": self.last_profile,
            "profiles": {name: p.to_dict() for name, p in self.profiles.items()},
        }
        tmp = self.path.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(data, indent=2), encoding="utf-8")
        os.replace(tmp, self.path)
