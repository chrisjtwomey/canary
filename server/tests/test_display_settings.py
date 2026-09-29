"""Whether the display runs the saved Display and Image settings."""
from epd_server.timeranges import TimeRanges, parse_hhmm

from display_settings import DISPLAY, DisplaySync, display_version
from tests.conftest import AT, TZ

CONFIG = {"display": {"sync": {"every": 900}}, "image": {"width": 1280, "height": 720},
          "dock": {"pm": {"warmup_s": 35}}}


def test_the_version_changes_with_the_display_or_image_block_alone():
    same = display_version(CONFIG)

    assert display_version({**CONFIG, "dock": {"pm": {"warmup_s": 60}}}) == same
    assert display_version({**CONFIG, "display": {"sync": {"every": 600}}}) != same
    assert display_version({**CONFIG, "image": {"width": 1200, "height": 825}}) != same
    assert len(same) == 8


def sync_of(doc, offline=False):
    return DisplaySync("3f2a9c1e", TimeRanges([(parse_hhmm("00:00"), 900)], TZ),
                       lambda device: ({"doc": doc, "age_s": 60, "offline": offline}
                                       if device == DISPLAY and doc else None),
                       now=lambda: AT)


def test_the_display_runs_the_settings_its_newest_report_was_stamped_with():
    assert sync_of({"ts": 1, "settings_version": "3f2a9c1e"}).applied() is True
    assert sync_of({"ts": 1, "settings_version": "0b1c2d3e"}).applied() is False
    assert sync_of({"ts": 1}).applied() is False
    assert sync_of(None).applied() is None


def test_it_says_when_the_display_syncs_next_and_whether_it_is_offline():
    """AT is 21:45, a slot of its own; the next is a quarter of an hour on."""
    display = sync_of({"ts": 1}, offline=True)

    assert display.offline() == (True, 60)
    assert display.next_sync() == "22:00"
