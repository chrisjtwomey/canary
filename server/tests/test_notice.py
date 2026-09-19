"""The notices the head holds in its firmware: set like a page, with the
bottom left free for what the head writes at run time."""
from bs4 import BeautifulSoup

from pages.notice import NoticePage, notices
from tests.html import one

WIDTH, HEIGHT = 1280, 720


def soup_of(page):
    page.template()
    return BeautifulSoup(str(page.airium), "html.parser")


def test_a_notice_needs_no_data():
    for page in notices(width=WIDTH, height=HEIGHT):
        assert page.requires == ()


def test_a_notice_is_a_label_a_verdict_and_detail():
    page = NoticePage("notice-test", "NO CONNECTION", "The server is offline.",
                      "Unable to connect to server.", width=WIDTH, height=HEIGHT)
    soup = soup_of(page)

    assert one(soup, ".page-notice .label").get_text(strip=True) == "NO CONNECTION"
    assert one(soup, ".page-notice .verdict").get_text(strip=True) == "The server is offline."
    assert one(soup, ".page-notice .detail").get_text(strip=True) == "Unable to connect to server."


def test_the_three_notices_the_head_holds():
    names = {p.name for p in notices(width=WIDTH, height=HEIGHT)}
    assert names == {"notice-unreachable", "notice-version", "notice-no-firmware"}


def test_each_notice_is_rendered_and_built_into_the_head():
    import os
    root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    with open(os.path.join(root, "platformio.ini")) as f:
        ini = f.read()
    for page in notices(width=WIDTH, height=HEIGHT):
        path = f"include/head/notices/{page.name}.png"
        assert os.path.isfile(os.path.join(root, path)), f"{path}: run scripts/notices.py"
        assert path in ini, f"{path} is not in board_build.embed_files"


def test_a_notice_renders_to_its_own_file(tmp_path):
    page = notices(width=WIDTH, height=HEIGHT, png_dir=tmp_path)[0]
    assert page.png_path == str(tmp_path / "notice-unreachable.png")
