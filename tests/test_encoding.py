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


def test_90_byte_window_record_uses_secwindow_layout():
    header = struct.pack("<HHHlH", 0x036C, 33, 1, 0, 0)
    window = struct.pack(
        "<H10s9s51s5hII",
        0x0F7F,
        b"secondary",
        b"proc4",
        b"Properties",
        653,
        102,
        360,
        600,
        0x5100,
        0x00E2FFFF,
        0x00C0C0C0,
    )

    system = SystemFile(filename="|SYSTEM", raw_data=header + _record(6, window))

    info = system.records[0]["window_info"]
    assert info["window_type"] == "SECWINDOW"
    assert info["name"] == "proc4"
    assert (info["x"], info["y"], info["width"], info["height"]) == (653, 102, 360, 600)
    assert info["rgb"] == 0x00E2FFFF
    assert info["rgb_nsr"] == 0x00C0C0C0
