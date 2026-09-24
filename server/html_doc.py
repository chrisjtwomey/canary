"""An Airium document that escapes the text and attribute values of every tag.

Airium writes ``_t`` as given and escapes only the quotes in an attribute,
and pages show text that boards post. Here each is escaped unless it is
:class:`~markupsafe.Markup`.
"""
from __future__ import annotations

from airium import Airium
from markupsafe import escape


class Html(Airium):
    def get_tag_(self, tag_name: str):
        tag = super().get_tag_(tag_name)

        def escaped(*p, _t=None, **k):
            return tag(*p, _t=None if _t is None else escape(_t),
                       **{key: escape(value) for key, value in k.items()})
        return escaped
