"""Regression tests for metadata-driven Windows code-page selection."""

import struct

from winhlp.lib.internal_files.system import SystemFile


def _record(record_type: int, data: bytes) -> bytes:
    return struct.pack("<HH", record_type, len(data)) + data


def test_japanese_metadata_is_applied_before_title_decoding():
    title = "メディア プレーヤーのヘルプ"
    header = struct.pack("<HHHlH", 0x036C, 33, 1, 0, 0)
    # TITLE deliberately precedes LCID and CHARSET, as it does in real files.
    raw = b"".join(
        [
            header,
            _record(1, title.encode("cp932") + b"\x00"),
            _record(9, b"\x00" * 8 + struct.pack("<H", 0x0411)),
            _record(11, struct.pack("<H", 0x0080)),
        ]
    )

    system = SystemFile(filename="|SYSTEM", raw_data=raw)

    assert system.encoding == "cp932"
    assert system.lcid == 0x0411
    assert system.charset == 0x0080
    assert system.title == title
