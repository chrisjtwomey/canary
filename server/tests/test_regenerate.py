"""The whole pipeline, with a fake renderer in place of Chromium."""
from PIL import Image

from epd_server import grey_levels, regenerate
from server import make_pages


class FakeRenderer:
    def __init__(self):
        self.calls = []

    def render(self, html_path, width, height):
        self.calls.append((html_path, width, height))
        img = Image.new("RGB", (width, height), (255, 255, 255))
        img.paste((120, 120, 120), (0, 0, width // 2, height))
        return img


def test_regenerate_writes_eight_grey_pngs_for_every_page(tmp_path, source, tz):
    renderer = FakeRenderer()
    pages = make_pages(tz, width=1280, height=720)
    for page in pages:
        page.html_dir = str(tmp_path / "static")
        page.png_dir = str(tmp_path)
        page.renderer = renderer

    rendered = regenerate(pages, source)

    assert [p.name for p in rendered] == [
        "breathe", "comfort", "dust", "air", "day", "diagnostics",
        "co2-trace", "co2-delta", "comfort-trace", "comfort-delta", "dust-trace", "dust-delta",
        "air-trace", "air-delta", "barometer-trace", "barometer-delta"]
    assert [c[1:] for c in renderer.calls] == [(1280, 720)] * 16
    for page in pages:
        html = (tmp_path / "static" / f"{page.name}.html").read_text()
        assert "charts.js" in html and f"page-{page.css_class}" in html
        img = Image.open(tmp_path / f"{page.name}.png")
        assert img.mode == "L" and img.size == (1280, 720)
        assert set(img.tobytes()) <= set(grey_levels(8))


def test_the_example_config_schedules_only_pages_the_server_makes(tz):
    import os
    from epd_server.config import load_core_config, load_yaml
    from epd_server.scheduling import PoolSchedule
    here = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    core = load_core_config(load_yaml(os.path.join(here, "config.example.yaml")))
    sched = core.server.display_schedule
    assert isinstance(sched, PoolSchedule) and sched.every == 300
    assert sched.names == ["co2", "comfort", "dust", "air", "pressure", "day", "diagnostics"]
    assert sched.pages() <= {p.png_filename for p in make_pages(tz, width=1280, height=720)}
