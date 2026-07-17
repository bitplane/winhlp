"""Tests for the single-file HTML export."""

import os
import re

import pytest
from winhlp.lib.hlp import HelpFile
from winhlp.lib.html import export_html

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
