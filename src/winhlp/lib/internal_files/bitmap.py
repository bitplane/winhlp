"""Parser for bitmap files (|bmN internal files)."""

from .base import InternalFile
from pydantic import BaseModel
from typing import List, Optional, Dict
import struct


class HotspotInfo(BaseModel):
    """
    Structure for hotspot information within bitmaps.
    From helpdeco.h: HOTSPOT
    """

    id0: int
    id1: int
    id2: int
    x: int
    y: int
    width: int
    height: int
    hash_value: int
    raw_data: dict


class BitmapHeader(BaseModel):
    """
    Structure for bitmap file headers.
    Based on the C code analysis.
    """

    x_pels: int
    y_pels: int
    planes: int
    bit_count: int
    width: int
    height: int
    colors_used: int
    colors_important: int
    data_size: int
    hotspot_size: int
    picture_offset: int
    hotspot_offset: int
    raw_data: dict


class ExtractedBitmap(BaseModel):
    """
    Represents an extracted bitmap with its data and metadata.
    """

    header: BitmapHeader
    bitmap_data: bytes
    hotspots: List[HotspotInfo] = []
    format_type: str  # "bmp", "wmf", "shg", etc.
    raw_data: dict


class BitmapFile(InternalFile):
    """
    Parses bitmap files (|bm0, |bm1, etc.) which contain images and hotspot data.

    Based on the analysis of helpdeco.c bitmap extraction code.
    """

    bitmaps: List[ExtractedBitmap] = []

    def __init__(self, **data):
        super().__init__(**data)
        self._parse()

    def _parse(self):
        """
        Parses the bitmap file data.
        """
        if len(self.raw_data) < 32:  # Need minimum header size
            return

        # Named MediaView bitmaps (e.g. bt_1.bmp) can be complete Windows BMP
        # files rather than the internal lP/SHG picture format. Detect that and
        # pass the bytes through verbatim; parsing them as lP yields garbage.
        if self.raw_data[:2] == b"BM":
            self._parse_raw_bmp()
            return

        # Proper lP/SHG/MRB picture decode (magic 0x506C/0x706C). The legacy
        # _parse_bitmap_data() reads the lP header as raw DIB fields and yields
        # garbage dimensions, so use the real decoder instead.
        magic = struct.unpack_from("<H", self.raw_data, 0)[0]
        if magic in (0x506C, 0x706C):
            from ..picture import decode_picture

            decoded = decode_picture(self.raw_data)
            if decoded:
                self._parse_decoded_picture(*decoded)
                return

        self._parse_bitmap_data()

    def _parse_decoded_picture(self, ext: str, data: bytes):
        """Store an already-decoded picture (complete .bmp or raw .wmf bytes)."""
        header = BitmapHeader(
            x_pels=0,
            y_pels=0,
            planes=1,
            bit_count=0,
            width=0,
            height=0,
            colors_used=0,
            colors_important=0,
            data_size=len(data),
            hotspot_size=0,
            picture_offset=0,
            hotspot_offset=0,
            raw_data={},
        )
        self.bitmaps.insert(
            0, ExtractedBitmap(header=header, bitmap_data=data, hotspots=[], format_type=f"ready:{ext}", raw_data={})
        )

    def _parse_raw_bmp(self):
        """Wrap an already-complete Windows .bmp so extract_image serves it as-is."""
        data = self.raw_data
        try:
            width = struct.unpack_from("<l", data, 18)[0]
            height = struct.unpack_from("<l", data, 22)[0]
            planes = struct.unpack_from("<H", data, 26)[0]
            bit_count = struct.unpack_from("<H", data, 28)[0]
        except struct.error:
            width = height = planes = bit_count = 0
        header = BitmapHeader(
            x_pels=0,
            y_pels=0,
            planes=planes,
            bit_count=bit_count,
            width=width,
            height=height,
            colors_used=0,
            colors_important=0,
            data_size=len(data),
            hotspot_size=0,
            picture_offset=0,
            hotspot_offset=0,
            raw_data={},
        )
        self.bitmaps = [
            ExtractedBitmap(header=header, bitmap_data=data, hotspots=[], format_type="rawbmp", raw_data={})
        ]

    def _parse_bitmap_data(self):
        """
        Parses bitmap data based on the format analysis from helldeco.c.
        """
        offset = 0
        data = self.raw_data

        try:
            # Read bitmap header - this is based on the C code structure
            if offset + 32 > len(data):
                return

            # Parse header fields (from helpdeco.c bitmap extraction)
            x_pels = struct.unpack_from("<L", data, offset)[0]
            offset += 4
            y_pels = struct.unpack_from("<L", data, offset)[0]
            offset += 4
            planes = struct.unpack_from("<H", data, offset)[0]
            offset += 2
            bit_count = struct.unpack_from("<H", data, offset)[0]
            offset += 2
            width = struct.unpack_from("<L", data, offset)[0]
            offset += 4
            height = struct.unpack_from("<L", data, offset)[0]
            offset += 4
            colors_used = struct.unpack_from("<L", data, offset)[0]
            offset += 4
            colors_important = struct.unpack_from("<L", data, offset)[0]
            offset += 4
            data_size = struct.unpack_from("<L", data, offset)[0]
            offset += 4
            hotspot_size = struct.unpack_from("<L", data, offset)[0]
            offset += 4
            picture_offset = struct.unpack_from("<L", data, offset)[0]
            offset += 4
            hotspot_offset = struct.unpack_from("<L", data, offset)[0]
            offset += 4

            header_data = {
                "x_pels": x_pels,
                "y_pels": y_pels,
                "planes": planes,
                "bit_count": bit_count,
                "width": width,
                "height": height,
                "colors_used": colors_used,
                "colors_important": colors_important,
                "data_size": data_size,
                "hotspot_size": hotspot_size,
                "picture_offset": picture_offset,
                "hotspot_offset": hotspot_offset,
            }

            header = BitmapHeader(**header_data, raw_data={"raw": data[:offset], "parsed": header_data})

            # Extract bitmap data
            bitmap_data = b""
            if picture_offset > 0 and data_size > 0:
                start = picture_offset
                end = min(start + data_size, len(data))
                bitmap_data = data[start:end]

            # Extract hotspot data
            hotspots = []
            if hotspot_offset > 0 and hotspot_size > 0:
                hotspots = self._parse_hotspots(data, hotspot_offset, hotspot_size)

            # Determine format type based on the bitmap characteristics
            format_type = self._determine_format_type(header, bitmap_data)

            bitmap = ExtractedBitmap(
                header=header,
                bitmap_data=bitmap_data,
                hotspots=hotspots,
                format_type=format_type,
                raw_data={"header": header_data, "data_size": len(bitmap_data), "hotspot_count": len(hotspots)},
            )

            self.bitmaps.append(bitmap)

        except struct.error:
            # Handle malformed bitmap data gracefully
            pass

    def _parse_hotspots(self, data: bytes, hotspot_offset: int, hotspot_size: int) -> List[HotspotInfo]:
        """
        Parses hotspot information from the bitmap.
        Based on the HOTSPOT structure from helpdeco.h.
        """
        hotspots = []

        if hotspot_offset + hotspot_size > len(data):
            return hotspots

        # Each hotspot is 15 bytes according to helpdeco.h
        hotspot_data = data[hotspot_offset : hotspot_offset + hotspot_size]
        offset = 0

        while offset + 15 <= len(hotspot_data):
            try:
                id0 = struct.unpack_from("<B", hotspot_data, offset)[0]
                offset += 1
                id1 = struct.unpack_from("<B", hotspot_data, offset)[0]
                offset += 1
                id2 = struct.unpack_from("<B", hotspot_data, offset)[0]
                offset += 1
                x = struct.unpack_from("<H", hotspot_data, offset)[0]
                offset += 2
                y = struct.unpack_from("<H", hotspot_data, offset)[0]
                offset += 2
                width = struct.unpack_from("<H", hotspot_data, offset)[0]
                offset += 2
                height = struct.unpack_from("<H", hotspot_data, offset)[0]
                offset += 2
                hash_value = struct.unpack_from("<L", hotspot_data, offset)[0]
                offset += 4

                hotspot_parsed = {
                    "id0": id0,
                    "id1": id1,
                    "id2": id2,
                    "x": x,
                    "y": y,
                    "width": width,
                    "height": height,
                    "hash_value": hash_value,
                }

                hotspot = HotspotInfo(
                    **hotspot_parsed, raw_data={"raw": hotspot_data[offset - 15 : offset], "parsed": hotspot_parsed}
                )
                hotspots.append(hotspot)

            except struct.error:
                break

        return hotspots

    def _determine_format_type(self, header: BitmapHeader, bitmap_data: bytes) -> str:
        """
        Determines the bitmap format type based on characteristics.
        Based on the bmpext array from helpdeco.c.
        """
        # From helpdeco.c: bit 0=multiresolution bit 1=bitmap, bit 2=metafile, bit 3=hotspot data, bit 4=embedded, bit 5=transparent
        # bmpext[] = { "???","mrb","bmp","mrb","wmf","mrb","mrb","mrb","shg","mrb","shg","mrb","shg","mrb","shg","mrb" };

        has_hotspots = len(self.bitmaps) > 0 and len(self.bitmaps[0].hotspots) > 0 if self.bitmaps else False

        # Check for common Windows metafile signatures
        if len(bitmap_data) >= 4:
            signature = bitmap_data[:4]
            if signature == b"\x01\x00\x09\x00":  # WMF signature
                return "wmf"
            elif signature == b"\xd7\xcd\xc6\x9a":  # EMF signature
                return "emf"

        # Check for SHG (Segmented Hypergraphics) format
        if has_hotspots and header.bit_count <= 8:
            return "shg"

        # Default to bitmap
        return "bmp"

    def extract_bitmap_as_bmp(self, bitmap_index: int = 0) -> Optional[bytes]:
        """
        Extracts a bitmap as a standard Windows BMP file.
        Returns the complete BMP file data including headers.
        """
        if bitmap_index >= len(self.bitmaps):
            return None

        bitmap = self.bitmaps[bitmap_index]
        header = bitmap.header

        # Only handle actual bitmap data (not metafiles)
        if bitmap.format_type not in ["bmp", "shg"]:
            return None

        try:
            # Create BMP file header (BITMAPFILEHEADER)
            colors = (
                header.colors_used
                if header.colors_used > 0
                else (1 << header.bit_count)
                if header.bit_count <= 8
                else 0
            )
            palette_size = colors * 4 if colors > 0 else 0

            bmp_file_header = struct.pack(
                "<HLhHL",
                0x4D42,  # bfType ("BM")
                54 + palette_size + len(bitmap.bitmap_data),  # bfSize
                0,
                0,  # bfReserved
                54 + palette_size,  # bfOffBits
            )

            # Create BMP info header (BITMAPINFOHEADER)
            bmp_info_header = struct.pack(
                "<LllHHLLllLL",
                40,  # biSize
                header.width,  # biWidth
                header.height,  # biHeight
                header.planes,  # biPlanes
                header.bit_count,  # biBitCount
                0,  # biCompression (BI_RGB)
                len(bitmap.bitmap_data),  # biSizeImage
                header.x_pels if header.x_pels > 0 else 2835,  # biXPelsPerMeter (72 DPI default)
                header.y_pels if header.y_pels > 0 else 2835,  # biYPelsPerMeter
                colors,  # biClrUsed
                header.colors_important,  # biClrImportant
            )

            # Combine headers and data
            bmp_data = bmp_file_header + bmp_info_header

            # Add palette if present (for <= 8-bit images)
            if palette_size > 0:
                # Extract palette from bitmap data if available
                palette = (
                    bitmap.bitmap_data[:palette_size]
                    if len(bitmap.bitmap_data) >= palette_size
                    else b"\x00" * palette_size
                )
                bmp_data += palette
                pixel_data = bitmap.bitmap_data[palette_size:] if len(bitmap.bitmap_data) > palette_size else b""
            else:
                pixel_data = bitmap.bitmap_data

            bmp_data += pixel_data
            return bmp_data

        except (struct.error, ValueError):
            return None

    def extract_image(self, bitmap_index: int = 0) -> Optional[tuple]:
        """Extract a picture as (extension, bytes), for any picture type.

        Bitmaps (DDB/DIB) are wrapped as a standard .bmp; metafiles (type 8) are
        returned as raw .wmf metafile bytes. helpdeco writes a placeable-metafile
        header for WMFs, but the bare metafile record stream is the portable form
        and is what the decompressed picture data already contains.
        Returns None if the index is out of range.
        """
        if bitmap_index >= len(self.bitmaps):
            return None
        bitmap = self.bitmaps[bitmap_index]
        if bitmap.format_type == "rawbmp":
            # Already a complete .bmp file; serve verbatim.
            return ("bmp", bitmap.bitmap_data)
        if bitmap.format_type.startswith("ready:"):
            # Decoded lP/SHG picture: bytes are a complete .bmp or raw metafile.
            return (bitmap.format_type.split(":", 1)[1], bitmap.bitmap_data)
        if bitmap.format_type in ("bmp", "shg"):
            data = self.extract_bitmap_as_bmp(bitmap_index)
            return ("bmp", data) if data is not None else None
        if bitmap.format_type in ("wmf", "mrb"):
            # Metafile / multi-resolution: the decompressed payload is the image.
            return ("wmf" if bitmap.format_type == "wmf" else "mrb", bitmap.bitmap_data)
        # DDB and anything else: return the decompressed bytes unwrapped.
        return (bitmap.format_type, bitmap.bitmap_data)

    def get_hotspot_context_names(self) -> Dict[int, str]:
        """
        Gets context names for all hotspots using reverse hashing.
        Returns a dictionary mapping hotspot hash values to context names.
        """
        from .context import ContextFile

        context_names = {}

        for bitmap in self.bitmaps:
            for hotspot in bitmap.hotspots:
                if hotspot.hash_value != 0:
                    context_name = ContextFile.reverse_hash(hotspot.hash_value)
                    context_names[hotspot.hash_value] = context_name

        return context_names
