"""Synthetic-data tests for Phase 4 sidecar / picture support.

The test corpus contains no .ANN/.BMK/.GID sidecars and no WMF/DDB bitmaps, so
these exercise the parsers with hand-built byte streams instead of real files.
"""

import os
import struct

from winhlp.lib.ann import LinkFile, AnnotationTextFile
from winhlp.lib.internal_files.bitmap import BitmapFile, ExtractedBitmap, BitmapHeader
from winhlp.lib.internal_files.grp import GRPFile


def test_grp_file_constructs_and_parses():
    """GRPFile (MediaView .GRP) must construct via the InternalFile convention.

    Regression: it used to call super().__init__() positionally and reference a
    non-existent self.data, raising TypeError and aborting the whole .MVB parse.
    """
    # GROUPHEADER: magic 0x000A3333, bitmap_size, last_topic, then one 12-byte range.
    data = struct.pack("<LLL", 0x000A3333, 0, 5) + struct.pack("<LLL", 0, 5, 1)
    grp = GRPFile(data, help_file=None, filename="GUIDE2.GRP")
    assert grp.header is not None
    assert grp.header.magic == 0x000A3333
    assert grp.get_group_for_topic(3) == 1  # topics 0..5 -> group 1


def test_ann_link_file_parses_references():
    # @LINK: uint16 count, then count * (topic_offset, unknown1, unknown2) u32.
    payload = struct.pack("<H", 2) + struct.pack("<LLL", 12345, 0, 0) + struct.pack("<LLL", 67890, 0, 0)
    link = LinkFile(filename="@LINK", raw_data=payload)
    assert link.number_of_annotations == 2
    assert [r.topic_offset for r in link.annotation_references] == [12345, 67890]


def test_ann_text_file_is_plain_ansi():
    ann = AnnotationTextFile(filename="12345!0", raw_data=b"a user note", topic_offset=12345)
    assert ann.text == "a user note"
    assert ann.topic_offset == 12345


def _blank_bitmap(format_type, data):
    header = BitmapHeader(
        x_pels=0,
        y_pels=0,
        planes=1,
        bit_count=8,
        width=4,
        height=4,
        colors_used=0,
        colors_important=0,
        data_size=len(data),
        hotspot_size=0,
        picture_offset=0,
        hotspot_offset=0,
        raw_data={},
    )
    return ExtractedBitmap(header=header, bitmap_data=data, format_type=format_type, raw_data={})


def test_extract_image_wmf_passthrough():
    """Metafiles are returned as raw .wmf bytes rather than None."""
    bf = BitmapFile(filename="|bm0", raw_data=b"")
    bf.bitmaps = [_blank_bitmap("wmf", b"\x01\x00\x09\x00metafile-bytes")]
    result = bf.extract_image(0)
    assert result is not None
    ext, data = result
    assert ext == "wmf"
    assert data == b"\x01\x00\x09\x00metafile-bytes"


def test_extract_image_bmp_wraps_bitmap():
    bf = BitmapFile(filename="|bm0", raw_data=b"")
    bf.bitmaps = [_blank_bitmap("bmp", b"\x00" * 64)]
    result = bf.extract_image(0)
    assert result is not None
    ext, data = result
    assert ext == "bmp"
    assert data[:2] == b"BM"  # BITMAPFILEHEADER magic


def test_lp_picture_decodes_to_sane_bmp():
    """|bmN pictures use the lP/SHG container; decode to a valid, sanely-sized BMP.

    Regression: the old bitmap parser read the lP header as raw DIB fields and
    produced garbage dimensions (e.g. an 800x502 cover image came out as a 50MB
    blob). extract_image must yield a real BMP with plausible dimensions.
    """
    from winhlp.lib.hlp import HelpFile

    hlp = HelpFile(filepath=os.path.join(os.path.dirname(__file__), "data", "win311", "SOL.HLP"))
    bf = hlp.bitmaps["|bm0"]
    ext, data = bf.extract_image(0)
    assert ext == "bmp"
    assert data[:2] == b"BM"
    width = struct.unpack_from("<i", data, 18)[0]
    height = struct.unpack_from("<i", data, 22)[0]
    assert 0 < width < 10000 and 0 < abs(height) < 10000
    # Header + pixels must match the declared file size (a well-formed BMP).
    assert struct.unpack_from("<I", data, 2)[0] == len(data)


def _cword(value):
    return bytes((value << 1,))


def _cdword(value):
    return struct.pack("<H", value << 1)


def _lp_dib(rgb, hotspot=b""):
    pixels = bytes((rgb[2], rgb[1], rgb[0], 0))
    fields = (
        bytes((6, 0))
        + _cdword(96)
        + _cdword(96)
        + _cword(1)
        + _cword(24)
        + _cdword(1)
        + _cdword(1)
        + _cdword(0)
        + _cdword(0)
        + _cdword(len(pixels))
        + _cdword(len(hotspot))
    )
    data_offset = len(fields) + 8
    hotspot_offset = data_offset + len(pixels) if hotspot else 0
    return fields + struct.pack("<II", data_offset, hotspot_offset) + pixels + hotspot


def test_lp_container_preserves_all_pictures_and_typed_hotspots():
    hotspot = (
        struct.pack("<BHI", 1, 1, 0)
        + struct.pack("<BBBHHHHI", 0xE2, 0, 0, 0, 0, 1, 1, 0x12345678)
        + b"Details\x00CTX_DETAILS\x00"
    )
    first = _lp_dib((255, 0, 0), hotspot)
    second = _lp_dib((0, 255, 0))
    first_offset = 12
    second_offset = first_offset + len(first)
    raw = struct.pack("<HHII", 0x706C, 2, first_offset, second_offset) + first + second

    bitmap_file = BitmapFile(filename="|bm0", raw_data=raw)

    assert len(bitmap_file.bitmaps) == 2
    assert bitmap_file.bitmaps[0].header.width == 1
    parsed = bitmap_file.bitmaps[0].hotspots[0]
    assert parsed.hotspot_type == "popup"
    assert parsed.target == "CTX_DETAILS"
    assert parsed.name == "Details"
    assert bitmap_file.extract_image(1)[0] == "bmp"


def test_hotspot_strings_use_help_file_encoding():
    hotspot = (
        struct.pack("<BHI", 1, 1, 0)
        + struct.pack("<BBBHHHHI", 0xE3, 0, 0, 0, 0, 1, 1, 0)
        + "詳細\x00コンテキスト\x00".encode("cp932")
    )
    picture = _lp_dib((0, 0, 0), hotspot)
    raw = struct.pack("<HHI", 0x506C, 1, 8) + picture

    parsed = BitmapFile(filename="|bm0", raw_data=raw, encoding="cp932").bitmaps[0].hotspots[0]

    assert parsed.name == "詳細"
    assert parsed.target == "コンテキスト"


def _annotation_container(topic_offset):
    files = {
        "@VERSION": b"\x08bmf\x01\0",
        "@LINK": struct.pack("<HIII", 1, topic_offset, 0, 0),
        f"{topic_offset}!0": b"A user note",
    }
    page_size = 128
    first_file = 16 + 9 + 38 + page_size
    entries = b""
    body = b""
    for name, data in sorted(files.items()):
        entries += name.encode("ascii") + b"\0" + struct.pack("<l", first_file + len(body))
        body += struct.pack("<llB", len(data) + 9, len(data), 4) + data
    leaf = struct.pack("<hhhh", 0, len(files), -1, -1) + entries
    tree = struct.pack("<HHH16shhhhhhi", 0x293B, 0x402, page_size, b"z4", 0, 0, 0, -1, 1, 1, len(files))
    tree += leaf.ljust(page_size, b"\0")
    directory = struct.pack("<llB", len(tree) + 9, len(tree), 4) + tree
    return struct.pack("<llll", 0x35F3F, 16, -1, 16 + len(directory) + len(body)) + directory + body


def test_annotation_container_is_opened_once_and_attached_to_help_topic(tmp_path, monkeypatch):
    import builtins
    from winhlp.lib.ann import AnnotationFile
    from winhlp.lib.hlp import HelpFile

    original = HelpFile(filepath=os.path.join(os.path.dirname(__file__), "data", "SMARTTOP.HLP"))
    topic = original.get_topics()[1]
    help_path = tmp_path / "sample.hlp"
    help_path.write_bytes(original.data)
    ann_path = tmp_path / "sample.ANN"
    ann_path.write_bytes(_annotation_container(topic.topic_offset))
    original_open = builtins.open
    ann_opens = 0

    def count_annotation_opens(path, *args, **kwargs):
        nonlocal ann_opens
        if str(path).lower().endswith(".ann"):
            ann_opens += 1
            assert ann_opens <= 2, "Annotation parsing recursively reopened its own sidecar"
        return original_open(path, *args, **kwargs)

    monkeypatch.setattr(builtins, "open", count_annotation_opens)
    standalone = AnnotationFile(filepath=str(ann_path))
    assert standalone.get_annotation_for_topic(topic.topic_offset) == "A user note"
    assert not standalone.hlp_parser.parse_errors
    assert ann_opens == 1

    # Exercise lowercase discovery as well as standalone uppercase parsing.
    ann_path.rename(ann_path.with_suffix(".ann"))
    ann_opens = 0
    helpfile = HelpFile(filepath=str(help_path))
    assert helpfile.get_topics()[1].annotations == ["A user note"]
    assert not helpfile.parse_errors
    assert ann_opens == 1
