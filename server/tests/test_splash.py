"""The splash screen the head holds in its firmware: the logo alone, in black
and white, which the head's partial updates need."""
import os

from bs4 import BeautifulSoup
from PIL import Image

from pages.splash import SplashPage
from tests.html import one

WIDTH, HEIGHT = 1280, 720
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
LOGO = '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 2 1"><path d="M 0 0 L 2 1 Z"/></svg>'


def splash(**kwargs):
    return SplashPage(LOGO, width=WIDTH, height=HEIGHT, **kwargs)


def test_the_splash_needs_no_data():
    assert splash().requires == ()


def test_the_splash_is_the_logo_itself():
    page = splash()
    page.template()
    soup = BeautifulSoup(str(page.airium), "html.parser")

    assert one(soup, ".page-splash .logo svg path").get("d") == "M 0 0 L 2 1 Z"


def test_the_splash_is_black_and_white_with_no_dither():
    dark, light = Image.new("L", (8, 8), 100), Image.new("L", (8, 8), 160)
    quantiser = splash().quantiser

    assert quantiser.apply(dark).getcolors() == [(64, 0)]
    assert quantiser.apply(light).getcolors() == [(64, 255)]


def test_the_splash_is_rendered_and_built_into_the_head():
    with open(os.path.join(ROOT, "platformio.ini")) as f:
        ini = f.read()
    path = "include/head/splash.png"
    assert os.path.isfile(os.path.join(ROOT, path)), f"{path}: run scripts/notices.py"
    assert path in ini, f"{path} is not in board_build.embed_files"


def test_the_splash_renders_to_its_own_file(tmp_path):
    assert splash(png_dir=tmp_path).png_path == str(tmp_path / "splash.png")
