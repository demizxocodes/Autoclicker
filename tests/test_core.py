import json
import time

from autoclicker.model import ClickPoint, Profile, ProfileStore, RunSettings, next_point_name
from autoclicker.runner import ROUNDS_DONE, STOPPED, TIME_UP, ClickRunner


def points(*names, delay=0.01):
    return [ClickPoint(name=n, x=i, y=i * 10, delay=delay) for i, n in enumerate(names)]


def run(pts, settings, timeout=5):
    clicked, finished = [], []
    runner = ClickRunner(pts, settings, lambda p: clicked.append(p.name), on_finish=finished.append)
    runner.start()
    runner.join(timeout)
    return runner, clicked, finished


def test_rounds_alternate_in_order():
    _, clicked, finished = run(points("A", "B", "C"), RunSettings(mode="rounds", rounds=3))
    assert clicked == ["A", "B", "C"] * 3
    assert finished == [ROUNDS_DONE]


def test_each_point_waits_its_own_delay():
    pts = [ClickPoint("A", 0, 0, delay=0.05), ClickPoint("B", 0, 0, delay=0.3)]
    stamps = []
    start = time.monotonic()
    runner = ClickRunner(pts, RunSettings(mode="rounds", rounds=1),
                         lambda p: stamps.append((p.name, time.monotonic() - start)))
    runner.start()
    runner.join(5)
    (a, ta), (b, tb) = stamps
    assert (a, b) == ("A", "B")
    assert 0.04 <= ta < 0.25
    assert 0.29 <= tb - ta < 0.6


def test_time_limit_stops_without_late_click():
    settings = RunSettings(mode="time", duration=0.35, duration_unit="seconds")
    _, clicked, finished = run(points("A", "B", delay=0.1), settings)
    assert finished == [TIME_UP]
    assert clicked == ["A", "B", "A"]


def test_stop_interrupts_long_wait():
    runner = ClickRunner(points("A", delay=60), RunSettings(), lambda p: None,
                         on_finish=lambda r: finished.append(r))
    finished = []
    runner.start()
    time.sleep(0.05)
    t = time.monotonic()
    runner.stop()
    runner.join(2)
    assert not runner.running
    assert time.monotonic() - t < 0.5
    assert finished == [STOPPED]


def test_click_error_is_reported():
    def boom(p):
        raise RuntimeError("no mouse")

    finished = []
    runner = ClickRunner(points("A"), RunSettings(), boom, on_finish=finished.append)
    runner.start()
    runner.join(2)
    assert finished == ["error: no mouse"]


def test_next_point_name():
    assert next_point_name([]) == "A"
    assert next_point_name(points("A", "C")) == "B"
    many = [ClickPoint(chr(65 + i), 0, 0) for i in range(26)]
    assert next_point_name(many) == "P27"


def test_store_round_trip(tmp_path):
    path = tmp_path / "sub" / "profiles.json"
    store = ProfileStore(path)
    store.load()
    assert list(store.profiles) == ["Default"]
    store.profiles["Farm"] = Profile(
        points=[ClickPoint("A", 100, 200, 1.5, "right", 2)],
        settings=RunSettings(mode="time", duration=2, duration_unit="hours"),
    )
    store.last_profile = "Farm"
    store.save()

    again = ProfileStore(path)
    again.load()
    assert again.last_profile == "Farm"
    assert again.profiles["Farm"] == store.profiles["Farm"]
    assert again.profiles["Farm"].settings.duration_seconds == 7200


def test_corrupt_file_is_backed_up(tmp_path):
    path = tmp_path / "profiles.json"
    path.write_text("{not json")
    store = ProfileStore(path)
    store.load()
    assert list(store.profiles) == ["Default"]
    assert (tmp_path / "profiles.json.bak").read_text() == "{not json"


def test_bad_values_are_clamped(tmp_path):
    path = tmp_path / "profiles.json"
    path.write_text(json.dumps({"profiles": {"P": {
        "points": [{"name": "A", "x": 1, "y": 2, "delay": -5, "button": "huh", "clicks": 9}],
        "settings": {"mode": "weird", "rounds": 0},
    }}, "last_profile": "missing"}))
    store = ProfileStore(path)
    store.load()
    p = store.profiles["P"].points[0]
    assert (p.delay, p.button, p.clicks) == (0.01, "left", 1)
    assert store.profiles["P"].settings.mode == "forever"
    assert store.profiles["P"].settings.rounds == 1
    assert store.last_profile == "P"
