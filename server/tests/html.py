"""Reading a rendered page in a test.

BeautifulSoup answers a lookup with a tag, a bare string, or nothing, so a
missing element is only discovered one line later as an attribute error on
``None``. These narrow it to a tag and say which selector found nothing.
"""
from __future__ import annotations

from bs4 import BeautifulSoup, Tag


def one(node: Tag | BeautifulSoup, selector: str) -> Tag:
    """The element that must match this selector."""
    found = node.select_one(selector)
    assert found is not None, selector
    return found


def attr(node: Tag, name: str) -> str:
    """An attribute, as the string a test compares against."""
    value = node.get(name)
    if value is None:
        return ""
    return " ".join(value) if isinstance(value, list) else value
