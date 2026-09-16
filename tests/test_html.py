"""Tests for the single-file HTML export."""

import os
import re

import pytest
from winhlp.lib.hlp import HelpFile
from winhlp.lib.html import export_html
from winhlp.lib.internal_files.topic import Table, TableCell, TableRow, TextSpan, TopicTableBlock, TopicTextBlock

DATA = os.path.join(os.path.dirname(__file__), "data")


@pytest.mark.parametrize(
    "path, snippet",
    [
        ("win311/SOL.HLP", "Solitaire is a card game that combines skill and luck"),
        ("win95/WINDOWS.HLP", "software available on the network for installation"),
        ("FXSEARCH.HLP", "F/X Text Search Help Index"),
    ],
)
def test_html_export_structure_and_content(path, snippet):
    hlp = HelpFile(filepath=os.path.join(DATA, path))
    out = export_html(hlp, images="embed")

    # Well-formed single-file document with a TOC and one section per topic.
    assert out.startswith("<!DOCTYPE html>")
    assert "<nav>" in out and "</html>" in out
    n_topics = len(hlp.topic.get_all_topics())
    assert out.count("<section ") == n_topics
    # Every section id is referenced by a TOC link.
    ids = set(re.findall(r'<section id="([^"]+)"', out))
    hrefs = set(re.findall(r'href="#([^"]+)"', out))
    assert ids and ids <= hrefs

    # Content is present and HTML-escaped (no raw angle brackets from text).
    assert snippet in out
    assert "<script" not in out.lower()


def test_html_images_embedded_as_data_uri():
    hlp = HelpFile(filepath=os.path.join(DATA, "win311/SOL.HLP"))
    out = export_html(hlp, images="embed")
    # SOL uses a |bm0 bullet bitmap; embed mode inlines it as a data URI. It is
    # a PNG when Pillow is installed (the [html] extra), else the source BMP.
    assert "data:image/png;base64," in out or "data:image/bmp;base64," in out


def test_html_extract_writes_image_files(tmp_path):
    hlp = HelpFile(filepath=os.path.join(DATA, "win311/SOL.HLP"))
    img_dir = str(tmp_path / "imgs")
    out = export_html(hlp, images="extract", image_dir=img_dir)
    # Extract mode references files by path, not data URIs, and writes them.
    assert "data:image" not in out
    assert os.path.isdir(img_dir)
    assert any(f.endswith((".png", ".bmp")) for f in os.listdir(img_dir))


def test_html_images_are_png_when_pillow_available():
    pytest.importorskip("PIL")
    hlp = HelpFile(filepath=os.path.join(DATA, "win311/SOL.HLP"))
    out = export_html(hlp, images="embed")
    assert "data:image/png;base64," in out
    assert "data:image/bmp;base64," not in out


def test_html_context_hash_links_use_shared_document_resolution():
    hlp = HelpFile(filepath=os.path.join(DATA, "SMARTTOP.HLP"))
    out = export_html(hlp)

    assert '<a class="jump" href="#topic-1">' in out


@pytest.mark.parametrize("font_number", [None, 0])
def test_html_preserves_each_span_style(font_number):
    hlp = HelpFile(filepath=os.path.join(DATA, "SMARTTOP.HLP"))
    hlp.font = None
    spans = [
        TextSpan(text="first bold", font_number=font_number, is_bold=True, raw_data={}),
        TextSpan(text="italic", font_number=font_number, is_italic=True, raw_data={}),
        TextSpan(text="second bold", font_number=font_number, is_bold=True, raw_data={}),
        TextSpan(text="plain", font_number=font_number, raw_data={}),
    ]
    hlp.get_topics()[0].content_blocks = [TopicTextBlock(text_spans=spans)]

    out = export_html(hlp)
    for text, rule in (
        ("first bold", "font-weight: bold"),
        ("italic", "font-style: italic"),
        ("second bold", "font-weight: bold"),
    ):
        match = re.search(r'<span class="([^"]+)">' + text + r"</span>", out)
        assert match is not None
        assert f".{match.group(1)} {{ {rule} }}" in out
    assert not re.search(r"<span[^>]*>plain</span>", out)


@pytest.mark.parametrize(
    "face, escaped",
    [
        ("</style><svg onload=alert(1)>", r"\3c /style>\3c svg onload=alert(1)>"),
        ('Font"\\\n\r\fName', r"Font\22 \5c \a \d \c Name"),
        ("Times New Roman", "Times New Roman"),
    ],
)
def test_html_font_names_are_safe_css_strings(face, escaped):
    from html.parser import HTMLParser

    class TagCollector(HTMLParser):
        def __init__(self):
            super().__init__()
            self.tags = []

        def handle_starttag(self, tag, attrs):
            self.tags.append(tag)

    hlp = HelpFile(filepath=os.path.join(DATA, "win311/SOL.HLP"))
    hlp.font.facenames = [face] * len(hlp.font.facenames)
    out = export_html(hlp)
    parser = TagCollector()
    parser.feed(out)

    assert f'font-family: "{escaped}", serif' in out
    assert out.count("</style>") == 1
    assert "svg" not in parser.tags


def test_html_table_preserves_links_images_and_styled_paragraphs():
    hlp = HelpFile(filepath=os.path.join(DATA, "win311/SOL.HLP"))
    topics = hlp.get_document().topics
    target = f"topic:TOPIC{topics[1].topic_number}"
    spans = [
        TextSpan(text="Open topic", is_hyperlink=True, hyperlink_target=target, raw_data={}),
        TextSpan(text="", embedded_image="bitmap:inline:0", raw_data={}),
        TextSpan(text="Bold <text>\nline", is_bold=True, raw_data={}),
        TextSpan(text="\n\nParagraph", raw_data={}),
    ]
    table = Table(
        rows=[
            TableRow(cells=[TableCell(text_spans=spans, alignment="center", column_span=2, raw_data={})], raw_data={})
        ],
        raw_data={},
    )
    topics[0].content_blocks = [TopicTableBlock(table=table)]

    out = export_html(hlp)
    cell = re.search(r'<td style="text-align: center" colspan="2">(.*?)</td>', out, re.S).group(1)

    assert '<a class="jump" href="#topic-1">Open topic</a>' in cell
    assert '<img src="data:image/' in cell
    assert 'alt="bitmap 0"' in cell
    styled = re.search(r'<span class="([^"]+)">Bold &lt;text&gt;<br>line</span>', cell)
    assert styled is not None
    assert "<p>Paragraph</p>" in cell
    assert f".{styled.group(1)} {{ font-weight: bold }}" in out


@pytest.mark.parametrize("directory", ["manual#1_images", 'manual" onerror="test_images', "help ?&% café_images"])
def test_extracted_image_urls_round_trip_special_directory_names(tmp_path, directory):
    from html.parser import HTMLParser
    from urllib.parse import unquote, urlsplit

    class Images(HTMLParser):
        def __init__(self):
            super().__init__()
            self.images = []

        def handle_starttag(self, tag, attrs):
            if tag == "img":
                self.images.append(dict(attrs))

    hlp = HelpFile(filepath=os.path.join(DATA, "win311/SOL.HLP"))
    output = export_html(hlp, images="extract", image_dir=str(tmp_path / directory))
    parser = Images()
    parser.feed(output)
    assert parser.images
    for attributes in parser.images:
        assert set(attributes) <= {"src", "alt", "style"}
        url = urlsplit(attributes["src"])
        assert not url.scheme and not url.netloc and not url.query and not url.fragment
        path = tmp_path / unquote(url.path)
        assert path.parent == tmp_path / directory
        assert path.is_file()
