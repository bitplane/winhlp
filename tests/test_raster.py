"""Tests for the replaceable terminal bitmap rasterizer."""

import struct
from pathlib import Path

from winhlp.lib.hlp import HelpFile
from winhlp.lib.raster import HalfBlockRasterizer, RasterHotspot, decode_bmp


def _bmp_24(width=2, height=2):
    row_size = ((width * 3 + 3) // 4) * 4
    rows = []
    colors = [[(255, 0, 0), (0, 255, 0)], [(0, 0, 255), (255, 255, 255)]]
    for row in reversed(colors):
        raw = b"".join(bytes((blue, green, red)) for red, green, blue in row)
        rows.append(raw + b"\x00" * (row_size - len(raw)))
    pixels = b"".join(rows)
    return (
        b"BM"
        + struct.pack("<IHHI", 54 + len(pixels), 0, 0, 54)
        + struct.pack("<IiiHHIIiiII", 40, width, height, 1, 24, 0, len(pixels), 0, 0, 0, 0)
        + pixels
    )


def test_decode_and_render_bmp_with_hotspot_action():
    image = decode_bmp(_bmp_24())
    assert image is not None
    assert image.pixel(0, 0) == (255, 0, 0)
    assert image.pixel(1, 1) == (255, 255, 255)

    rendered = HalfBlockRasterizer().render(
        image,
        max_width=2,
        hotspots=[RasterHotspot(0, 0, 1, 2, "app.follow_link(3)")],
        selected_hotspot=0,
    )
    assert rendered.plain == "▀▀"
    assert rendered.spans


def test_unsupported_or_truncated_bmp_returns_none():
    assert decode_bmp(b"not a bitmap") is None
    assert decode_bmp(_bmp_24()[:-2]) is None


def test_pixels_are_not_reversed_when_no_hotspot_is_selected():
    image = decode_bmp(_bmp_24())
    rendered = HalfBlockRasterizer().render(image, max_width=2)

    assert rendered.spans
    assert all(not span.style.reverse for span in rendered.spans)
    assert all(not span.style.bold for span in rendered.spans)


def test_selected_link_image_is_bold_but_not_reversed():
    image = decode_bmp(_bmp_24())
    rendered = HalfBlockRasterizer().render(
        image,
        max_width=2,
        hotspots=[RasterHotspot(0, 0, 2, 2, "follow", reverse_on_select=False)],
        selected_hotspot=0,
    )

    assert rendered.spans
    assert all(not span.style.reverse for span in rendered.spans)
    assert all(span.style.bold for span in rendered.spans)


def test_real_one_and_four_bit_help_bitmaps_decode():
    data = Path(__file__).parent / "data"
    fixtures = [
        (data / "win311" / "SOL.HLP", "|bm0", 1),
        (data / "SMARTTOP.HLP", "|bm0", 4),
    ]

    for path, resource, expected_bits in fixtures:
        bitmap = HelpFile(filepath=str(path)).bitmaps[resource]
        extension, payload = bitmap.extract_image(0)
        assert extension == "bmp"
        assert struct.unpack_from("<H", payload, 28)[0] == expected_bits
        assert decode_bmp(payload) is not None
