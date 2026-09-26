import io
import struct

import pytest
from winhlp.lib.picture import decode_pictures

Image = pytest.importorskip("PIL.Image")


def _cword(value):
    return bytes([value << 1])


def _cdword(value):
    return struct.pack("<H", value << 1)


def _lp_ddb(width, height, rows):
    pixels = b"".join(rows)
    header = (
        bytes([5, 0])  # DDB, uncompressed
        + _cdword(96)
        + _cdword(96)
        + _cword(1)
        + _cword(1)
        + _cdword(width)
        + _cdword(height)
        + _cdword(0)
        + _cdword(0)
        + _cdword(len(pixels))
        + _cdword(0)
    )
    picture_offset = 8  # from the start of this picture
    body = header + struct.pack("<LL", len(header) + picture_offset, 0) + pixels
    return struct.pack("<HHL", 0x506C, 1, 8) + body


def test_ddb_converts_to_upright_monochrome_bmp():
    # 10x3 monochrome DDB, WORD-aligned rows stored top-down; top row is white.
    raw = _lp_ddb(10, 3, [b"\xff\xc0", b"\x00\x00", b"\x00\x00"])
    (picture,) = decode_pictures(raw)

    image = Image.open(io.BytesIO(picture.data))
    image.load()
    assert image.size == (10, 3)
    rgb = image.convert("RGB")
    assert rgb.getpixel((0, 0)) == (255, 255, 255)
    assert rgb.getpixel((9, 0)) == (255, 255, 255)
    assert rgb.getpixel((0, 2)) == (0, 0, 0)


def test_runlen_zero_count_reads_next_byte_as_count():
    from winhlp.lib.picture import _shg_runlen

    # 0x00 is an empty run; helpdeco treats the following byte as the next count.
    assert _shg_runlen(b"\x00\x03\xaa\x82\x01\x02") == b"\xaa\xaa\xaa\x01\x02"
