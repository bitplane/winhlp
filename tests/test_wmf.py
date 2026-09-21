"""WMF rendering through the real Pillow backend and display entry points."""

import base64
import io
from pathlib import Path

import pytest
from pillow_wmf import Recorder

from winhlp.lib.hlp import HelpFile
from winhlp.lib.document import HelpDocument, parse_embedded_resource
from winhlp.lib.html import HtmlExporter, _to_png
from winhlp.lib.raster import decode_image
from winhlp.tui import TopicView


@pytest.fixture
def wmf():
    recorder = Recorder()
    brush = recorder.create_brush(0, 0x0000FF, 0)
    recorder.select_object(brush)
    recorder.rectangle(2, 2, 18, 8)
    return recorder.to_bytes()


def test_wmf_raster_uses_container_size_and_colors(wmf):
    image = decode_image(wmf, "wmf", (20, 10))
    assert (image.width, image.height) == (20, 10)
    assert image.pixel(5, 5) == (255, 0, 0)
    assert image.pixel(0, 0) == (255, 255, 255)


def test_terminal_view_decodes_wmf_resource(wmf):
    hlp = HelpFile(filepath=str(Path(__file__).parent / "data/win311/SOL.HLP"))
    picture = hlp.bitmaps["|bm0"].bitmaps[0]
    picture.format_type = "ready:wmf"
    picture.bitmap_data = wmf
    picture.header.width, picture.header.height = 20, 10
    view = TopicView(HelpDocument(hlp))
    resource = parse_embedded_resource("bitmap:inline:0")
    *_, image = view._bitmap_resource(resource, 20)
    assert (image.width, image.height) == (20, 10)
    assert image.pixel(5, 5) == (255, 0, 0)


@pytest.mark.parametrize("mode", ["embed", "extract"])
def test_html_wmf_is_rendered_as_png(wmf, mode, tmp_path):
    from PIL import Image

    hlp = HelpFile(filepath=str(Path(__file__).parent / "data/win311/SOL.HLP"))
    bitmap = hlp.bitmaps["|bm0"]
    picture = bitmap.bitmaps[0]
    picture.format_type = "ready:wmf"
    picture.bitmap_data = wmf
    picture.header.width, picture.header.height = 20, 10
    exporter = HtmlExporter(hlp, images=mode, image_dir=str(tmp_path))
    src = exporter._image_src(bitmap, "|bm0")
    if mode == "embed":
        assert src.startswith("data:image/png;base64,")
        data = base64.b64decode(src.split(",", 1)[1])
    else:
        assert src.endswith("/bm0.png")
        data = (tmp_path / "bm0.png").read_bytes()
    with Image.open(io.BytesIO(data)) as image:
        assert image.size == (20, 10)
        assert image.getpixel((5, 5)) == (255, 0, 0)
    assert bitmap.extract_image(0) == ("wmf", wmf)


def test_bad_wmf_falls_back():
    data = b"invalid metafile"
    assert decode_image(data, "wmf", (20, 10)) is None
    assert _to_png(data, "wmf", (20, 10)) == (data, "wmf")
