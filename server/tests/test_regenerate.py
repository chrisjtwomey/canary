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
        "breathe", "comfort", "day", "dust", "air", "barometer-trace", "barometer-delta", "diagnostics"]
    assert [c[1:] for c in renderer.calls] == [(1280, 720)] * 8
    for page in pages:
        html = (tmp_path / "static" / f"{page.name}.html").read_text()
        assert "charts.js" in html and f"page-{page.css_class}" in html
        img = Image.open(tmp_path / f"{page.name}.png")
        assert img.mode == "L" and img.size == (1280, 720)
        assert set(img.tobytes()) <= set(grey_levels(8))
