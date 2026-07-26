"""Decoder for the internal lP/SHG/MRB picture format.

Pictures embedded in |bmN files and MediaView named bitmap resources are stored
in the SHG/MRB "lP"/"lp" container (doc/helpfile.md:1266-1323): a magic + a table
of picture offsets, each pointing at a DDB/DIB bitmap or a metafile whose
dimension header is written as *compressed* integers and whose pixels are packed
with RunLen and/or LZ77. This module decodes every picture into a ready-to-serve
Windows .bmp (bitmaps) or raw metafile (.wmf).
"""

import struct
from dataclasses import dataclass
from typing import Optional, Tuple

from .compression import lz77_decompress

LP_MAGIC = (0x506C, 0x706C)  # "lP" (SHG) / "lp" (MRB)


@dataclass(frozen=True)
class DecodedPicture:
    """One decoded member of an SHG/MRB picture container."""

    extension: str
    data: bytes
    picture_type: int
    packing: int
    x_dpi: int = 0
    y_dpi: int = 0
    planes: int = 1
    bit_count: int = 0
    width: int = 0
    height: int = 0
    colors_used: int = 0
    colors_important: int = 0
    picture_offset: int = 0
    hotspot_offset: int = 0
    hotspot_data: bytes = b""


def _cword(data: bytes, pos: int) -> Tuple[int, int]:
    """Read a compressed unsigned short: 1 byte if LSB clear, else 2."""
    if data[pos] & 1:
        return struct.unpack_from("<H", data, pos)[0] >> 1, pos + 2
    return data[pos] >> 1, pos + 1


def _cdword(data: bytes, pos: int) -> Tuple[int, int]:
    """Read a compressed unsigned long: 2 bytes if LSB clear, else 4."""
    w = struct.unpack_from("<H", data, pos)[0]
    if w & 1:
        return struct.unpack_from("<L", data, pos)[0] >> 1, pos + 4
    return w >> 1, pos + 2


def _shg_runlen(data: bytes) -> bytes:
    """SHG RunLen: n; if n&0x80 copy n&0x7F literal bytes, else repeat next byte n times."""
    out = bytearray()
    i, n = 0, len(data)
    while i < n:
        c = data[i]
        i += 1
        if c & 0x80:
            count = c & 0x7F
            out += data[i : i + count]
            i += count
        elif i < n:
            out += bytes([data[i]]) * c
            i += 1
    return bytes(out)


def _unpack(method: int, data: bytes) -> bytes:
    if method == 1:
        return _shg_runlen(data)
    if method == 2:
        return lz77_decompress(data)
    if method == 3:  # doc: "first use LZ77, then RunLen"
        return _shg_runlen(lz77_decompress(data))
    return data  # 0 = uncompressed


def _build_bmp(width, height, planes, bit_count, n_colors, palette, pixels) -> bytes:
    header_size = 14 + 40 + len(palette)
    file_header = struct.pack("<2sIHHI", b"BM", header_size + len(pixels), 0, 0, header_size)
    info_header = struct.pack(
        "<IiiHHIIiiII", 40, width, height, planes or 1, bit_count, 0, len(pixels), 0, 0, n_colors, 0
    )
    return file_header + info_header + palette + pixels


def _decode_one(raw: bytes, off: int) -> Optional[DecodedPicture]:
    p = off
    picture_type = raw[p]
    packing = raw[p + 1]
    p += 2

    if picture_type in (5, 6):  # DDB / DIB
        x_dpi, p = _cdword(raw, p)
        y_dpi, p = _cdword(raw, p)
        planes, p = _cword(raw, p)
        bit_count, p = _cword(raw, p)
        width, p = _cdword(raw, p)
        height, p = _cdword(raw, p)
        colors_used, p = _cdword(raw, p)
        colors_important, p = _cdword(raw, p)
        comp_size, p = _cdword(raw, p)
        hotspot_size, p = _cdword(raw, p)
        comp_offset = struct.unpack_from("<L", raw, p)[0]
        hotspot_offset = struct.unpack_from("<L", raw, p + 4)[0]
        p += 8

        n_colors = colors_used or (1 << bit_count if bit_count <= 8 else 0)
        palette = b""
        if picture_type == 6 and n_colors:
            # Stored as COLORREF (0x00BBGGRR); BMP wants RGBQUAD (B,G,R,0) - swap R/B.
            raw_pal = raw[p : p + n_colors * 4]
            pal = bytearray(raw_pal)
            for i in range(0, len(pal) - 3, 4):
                pal[i], pal[i + 2] = pal[i + 2], pal[i]
            palette = bytes(pal)

        comp = raw[off + comp_offset : off + comp_offset + comp_size]
        pixels = _unpack(packing, comp)
        if width <= 0 or height <= 0 or width > 20000 or height > 20000:
            return None
        hotspot_data = raw[off + hotspot_offset : off + hotspot_offset + hotspot_size] if hotspot_offset else b""
        return DecodedPicture(
            "bmp",
            _build_bmp(width, height, planes, bit_count, n_colors, palette, pixels),
            picture_type,
            packing,
            x_dpi,
            y_dpi,
            planes,
            bit_count,
            width,
            height,
            colors_used,
            colors_important,
            comp_offset,
            hotspot_offset,
            hotspot_data,
        )

    if picture_type == 8:  # metafile
        _mm, p = _cword(raw, p)
        width, height = struct.unpack_from("<HH", raw, p)
        p += 4
        _decompressed_size, p = _cdword(raw, p)
        comp_size, p = _cdword(raw, p)
        hotspot_size, p = _cdword(raw, p)
        comp_offset = struct.unpack_from("<L", raw, p)[0]
        hotspot_offset = struct.unpack_from("<L", raw, p + 4)[0]
        comp = raw[off + comp_offset : off + comp_offset + comp_size]
        hotspot_data = raw[off + hotspot_offset : off + hotspot_offset + hotspot_size] if hotspot_offset else b""
        return DecodedPicture(
            "wmf",
            _unpack(packing, comp),
            picture_type,
            packing,
            width=width,
            height=height,
            picture_offset=comp_offset,
            hotspot_offset=hotspot_offset,
            hotspot_data=hotspot_data,
        )

    return None


def decode_pictures(raw: bytes) -> list[DecodedPicture]:
    """Decode every valid picture in an lP/SHG/MRB container."""
    if len(raw) < 8 or struct.unpack_from("<H", raw, 0)[0] not in LP_MAGIC:
        return []
    num = struct.unpack_from("<H", raw, 2)[0]
    if num < 1 or 4 + num * 4 > len(raw):
        return []
    pictures = []
    for index in range(num):
        off = struct.unpack_from("<L", raw, 4 + index * 4)[0]
        if not (0 < off < len(raw)):
            continue
        try:
            picture = _decode_one(raw, off)
        except (struct.error, IndexError):
            picture = None
        if picture is not None:
            pictures.append(picture)
    return pictures


def decode_picture(raw: bytes) -> Optional[Tuple[str, bytes]]:
    """Compatibility wrapper returning the first decoded picture."""
    pictures = decode_pictures(raw)
    return (pictures[0].extension, pictures[0].data) if pictures else None
