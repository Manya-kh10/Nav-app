import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "backend"))

from app.schemas.route import Step
from app.services.routing.deviation import DeviationTracker, next_maneuver, project

# ~1085 m straight east-west line at Bangalore's latitude
LINE = [[12.97, 77.60], [12.97, 77.61]]


def test_on_route_point():
    d, along = project(LINE, 12.97, 77.605)
    assert d < 2
    assert 520 < along < 565


def test_off_route_point_about_50m():
    d, _ = project(LINE, 12.97045, 77.605)
    assert 45 < d < 55


def _step(dist, man="turn"):
    return Step(maneuver=man, modifier="left", road="", distance_m=dist,
                duration_s=0, lat=0, lon=0)


def test_next_maneuver():
    steps = [_step(100, "depart"), _step(200), _step(300), _step(0, "arrive")]
    assert next_maneuver(steps, 50) == (1, 50)
    assert next_maneuver(steps, 150) == (2, 150)
    assert next_maneuver(steps, 650) is None


def test_deviation_debounce():
    t = DeviationTracker()
    assert [t.update(60, 10, ts) for ts in (0, 2, 4, 6)] == [False, False, False, True]


def test_bad_accuracy_ignored_and_return_resets():
    t = DeviationTracker()
    assert t.update(60, 10, 0) is False
    assert t.update(60, 80, 10) is False   # inaccurate fix is ignored
    assert t.update(10, 10, 11) is False   # back on route resets the timer
    assert t.update(60, 10, 12) is False
    assert t.update(60, 10, 18) is True