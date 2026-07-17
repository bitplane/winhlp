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
