from markupsafe import Markup

from html_doc import Html


def test_text_is_escaped_and_markup_is_written_as_it_is():
    a = Html()
    with a.div():
        a.p(_t="<b>Tom & Jerry</b>")
        a.p(_t=Markup("<b>bold</b>"))
        a.ul().li(_t=3)
    html = str(a)
    assert "<p>&lt;b&gt;Tom &amp; Jerry&lt;/b&gt;</p>" in html
    assert "<p><b>bold</b></p>" in html
    assert "<li>3</li>" in html


def test_attribute_values_are_escaped():
    a = Html()
    a.input(value='"><b> &lt;', checked=True)
    assert str(a) == '<input value="&#34;&gt;&lt;b&gt; &amp;lt;" checked="true" />'
