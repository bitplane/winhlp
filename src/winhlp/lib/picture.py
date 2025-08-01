"""Parses embedded pictures in HLP files."""

from pydantic import BaseModel, Field
from typing import List
import struct


class PictureHeader(BaseModel):
    """
    Header for an embedded picture (SHG/MRB).
    """

    magic: int = Field(..., description="0x506C (SHG) or 0x706C (MRB)")
    num_pictures: int
    picture_offsets: List[int]
    raw_data: dict


class BitmapPicture(BaseModel):
    """
    Header for a bitmap within a picture.
    """

    picture_type: int = Field(..., description="5=DDB, 6=DIB")
    packing_method: int
    xdpi: int
    ydpi: int
    planes: int
    bit_count: int
    width: int
    height: int
    colors_used: int
    colors_important: int
    compressed_size: int
    hotspot_size: int
    compressed_offset: int
    hotspot_offset: int
    palette: bytes = b""
    decompressed_data: bytes = b""
    raw_data: dict


class MetafilePicture(BaseModel):
    """
    Header for a metafile within a picture.
    """

    picture_type: int = Field(..., description="8=metafile")
    packing_method: int
    mapping_mode: int
    width: int
    height: int
    decompressed_size: int
    compressed_size: int
    hotspot_size: int
    compressed_offset: int
    hotspot_offset: int
    decompressed_data: bytes = b""
    raw_data: dict


class Hotspot(BaseModel):
    """
    Structure for a single hotspot in a picture.
    From helpdeco.h and splitmrb.c: HOTSPOT (15 bytes packed)
    """

    binding_type: int  # Derived from c1: 1=Jump, 2=Pop-up, 3=Macro
    visible: bool  # Derived from c2: True if c2==0, False if c2!=0
    x: int  # Left border
    y: int  # Top border
    w: int  # Width
    h: int  # Height
    hash_value: int  # Hash for topic lookup
    name: str = ""  # Hotspot name string
    context: str = ""  # Context/macro string
    raw_data: dict


class HotspotStringData(BaseModel):
    """
    String data associated with a hotspot.
    From `helpfile.md`.
    """

    hotspot_name: str
    context_name_or_macro: str
    raw_data: dict


class Picture(BaseModel):
    """
    Represents a picture (SHG or MRB format) embedded in a HLP file.
    """

    header: PictureHeader
    bitmaps: list[BitmapPicture] = []
    metafiles: list[MetafilePicture] = []
    hotspots: list[Hotspot] = []
    hotspot_strings: list[HotspotStringData] = []

    def __init__(self, data: bytes, **kwargs):
        super().__init__(**kwargs)
        self._parse(data)

    def _parse(self, data: bytes):
        """
        Parses the picture data.
        """
        self._parse_header(data)
        self._parse_pictures(data)
        self._parse_hotspots(data)

    def _parse_header(self, data: bytes):
        """
        Parses the main picture header.
        """
        offset = 0
        start_offset = offset

        magic = struct.unpack_from("<H", data, offset)[0]
        offset += 2

        num_pictures = struct.unpack_from("<H", data, offset)[0]
        offset += 2

        picture_offsets = []
        for _ in range(num_pictures):
            picture_offset = struct.unpack_from("<L", data, offset)[0]
            offset += 4
            picture_offsets.append(picture_offset)

        parsed_header = {
            "magic": magic,
            "num_pictures": num_pictures,
            "picture_offsets": picture_offsets,
        }

        self.header = PictureHeader(
            **parsed_header, raw_data={"raw": data[start_offset:offset], "parsed": parsed_header}
        )

    def _parse_pictures(self, data: bytes):
        """
        Parses the individual pictures (bitmaps or metafiles).
        """
        for offset in self.header.picture_offsets:
            picture_type = struct.unpack_from("<H", data, offset)[0]
            if picture_type == 5 or picture_type == 6:  # Bitmap
                self.bitmaps.append(self._parse_bitmap_picture(data, offset))
            elif picture_type == 8:  # Metafile
                self.metafiles.append(self._parse_metafile_picture(data, offset))

    def _parse_bitmap_picture(self, data: bytes, offset: int) -> BitmapPicture:
        """
        Parses a BitmapPicture structure.
        """
        start_offset = offset
        (
            picture_type,
            packing_method,
            xdpi,
            ydpi,
            planes,
            bit_count,
            width,
            height,
            colors_used,
            colors_important,
            compressed_size,
            hotspot_size,
            compressed_offset,
            hotspot_offset,
        ) = struct.unpack_from("<HHHHHHHHHHLLL", data, offset)
        offset += 40  # Size of the structure

        palette = b""
        if colors_used > 0:
            palette = data[offset : offset + colors_used * 4]
            offset += colors_used * 4

        parsed_bitmap = {
            "picture_type": picture_type,
            "packing_method": packing_method,
            "xdpi": xdpi,
            "ydpi": ydpi,
            "planes": planes,
            "bit_count": bit_count,
            "width": width,
            "height": height,
            "colors_used": colors_used,
            "colors_important": colors_important,
            "compressed_size": compressed_size,
            "hotspot_size": hotspot_size,
            "compressed_offset": compressed_offset,
            "hotspot_offset": hotspot_offset,
            "palette": palette,
        }
        bitmap = BitmapPicture(**parsed_bitmap, raw_data={"raw": data[start_offset:offset], "parsed": parsed_bitmap})

        # Add decompressed bitmap data if compression is used
        if bitmap.packing_method > 0 and bitmap.compressed_size > 0:
            bitmap.decompressed_data = self._decompress_picture_data(
                data, bitmap.compressed_offset, bitmap.compressed_size, bitmap.packing_method
            )

        return bitmap

    def _parse_metafile_picture(self, data: bytes, offset: int) -> MetafilePicture:
        """
        Parses a MetafilePicture structure.
        """
        start_offset = offset
        (
            picture_type,
            packing_method,
            mapping_mode,
            width,
            height,
            decompressed_size,
            compressed_size,
            hotspot_size,
            compressed_offset,
            hotspot_offset,
        ) = struct.unpack_from("<HHHHHHLLL", data, offset)
        offset += 32  # Size of the structure

        parsed_metafile = {
            "picture_type": picture_type,
            "packing_method": packing_method,
            "mapping_mode": mapping_mode,
            "width": width,
            "height": height,
            "decompressed_size": decompressed_size,
            "compressed_size": compressed_size,
            "hotspot_size": hotspot_size,
            "compressed_offset": compressed_offset,
            "hotspot_offset": hotspot_offset,
        }
        metafile = MetafilePicture(
            **parsed_metafile, raw_data={"raw": data[start_offset:offset], "parsed": parsed_metafile}
        )

        # Add decompressed metafile data if compression is used
        if metafile.packing_method > 0 and metafile.compressed_size > 0:
            metafile.decompressed_data = self._decompress_picture_data(
                data, metafile.compressed_offset, metafile.compressed_size, metafile.packing_method
            )

        return metafile

    def _parse_hotspots(self, data: bytes):
        """
        Parses the hotspot data, if present.
        """
        # Hotspot data follows the picture data. The offset is relative to the start of the picture data.
        # The number of hotspots is not explicitly stored in the PictureHeader, but rather
        # inferred from the hotspot_size in BitmapPicture/MetafilePicture.
        # Parse hotspot data at the specific offsets indicated by the picture headers

        # Parse hotspot data following C implementation in splitmrb.c PrintHotspotInfo
        if self.bitmaps:
            for bitmap in self.bitmaps:
                if bitmap.hotspot_size > 0 and bitmap.hotspot_offset > 0:
                    self._parse_hotspot_data(data, bitmap.hotspot_offset)

        if self.metafiles:
            for metafile in self.metafiles:
                if metafile.hotspot_size > 0 and metafile.hotspot_offset > 0:
                    self._parse_hotspot_data(data, metafile.hotspot_offset)

    def _parse_hotspot_data(self, data: bytes, hotspot_offset: int):
        """Parse hotspot data following C implementation in splitmrb.c PrintHotspotInfo"""
        if hotspot_offset >= len(data):
            return

        offset = hotspot_offset

        # Read format byte (should be 1)
        if offset >= len(data):
            return
        format_byte = data[offset]
        offset += 1

        if format_byte != 1:
            return

        # Read number of hotspots
        if offset + 2 > len(data):
            return
        num_hotspots = struct.unpack_from("<H", data, offset)[0]
        offset += 2

        if num_hotspots == 0:
            return

        # Read macro data size
        if offset + 2 > len(data):
            return
        macro_data_size = struct.unpack_from("<H", data, offset)[0]
        offset += 2

        # Skip ignored word
        if offset + 2 > len(data):
            return
        offset += 2

        # Read hotspot structures (15 bytes each: 3 bytes + 4 words + 4 bytes)
        hotspot_structs = []
        for i in range(num_hotspots):
            if offset + 15 > len(data):
                break
            c1, c2, c3, x, y, w, h, hash_value = struct.unpack_from("<BBBhhhhL", data, offset)
            hotspot_structs.append((c1, c2, c3, x, y, w, h, hash_value))
            offset += 15

        # Skip macro data
        offset += macro_data_size

        # Read null-terminated strings for each hotspot
        for i, (c1, c2, c3, x, y, w, h, hash_value) in enumerate(hotspot_structs):
            if offset >= len(data):
                break

            # Read hotspot name (null-terminated)
            name_start = offset
            while offset < len(data) and data[offset] != 0:
                offset += 1
            if offset >= len(data):
                break
            name = data[name_start:offset].decode("latin-1", errors="ignore")
            offset += 1  # skip null terminator

            # Read context/buffer string (null-terminated)
            buffer_start = offset
            while offset < len(data) and data[offset] != 0:
                offset += 1
            if offset >= len(data):
                break
            context = data[buffer_start:offset].decode("latin-1", errors="ignore")
            offset += 1  # skip null terminator

            # Determine hotspot type from C code logic
            if (c1 & 0xF0) == 0xC0:
                binding_type = 3  # Macro
            elif c1 & 1:
                binding_type = 1  # Jump
            else:
                binding_type = 2  # Pop-up

            visible = c2 == 0  # c2=0 means visible, c2!=0 means invisible

            hotspot = Hotspot(
                binding_type=binding_type,
                visible=visible,
                x=x,
                y=y,
                w=w,
                h=h,
                hash_value=hash_value,
                name=name,
                context=context,
                raw_data={
                    "parsed": {
                        "c1": c1,
                        "c2": c2,
                        "c3": c3,
                        "binding_type": binding_type,
                        "visible": visible,
                        "x": x,
                        "y": y,
                        "w": w,
                        "h": h,
                        "hash_value": hash_value,
                        "name": name,
                        "context": context,
                    }
                },
            )
            self.hotspots.append(hotspot)

    def _decompress_picture_data(
        self, data: bytes, compressed_offset: int, compressed_size: int, packing_method: int
    ) -> bytes:
        """
        Decompress picture data using the appropriate method.

        From helldeco.c and the file format documentation:
        - packing_method 0: No compression
        - packing_method 1: RunLen compression
        - packing_method 2: LZ77 compression
        - packing_method 3: ZLIB compression (rarely used)
        """
        if packing_method == 0:
            # No compression - return raw data
            return data[compressed_offset : compressed_offset + compressed_size]

        # Get compressed data
        compressed_data = data[compressed_offset : compressed_offset + compressed_size]

        if packing_method == 1:
            # RunLen compression
            from .compression import decompress

            return decompress(method=1, data=compressed_data)
        elif packing_method == 2:
            # LZ77 compression
            from .compression import decompress

            return decompress(method=2, data=compressed_data)
        elif packing_method == 3:
            # ZLIB compression
            from .compression import decompress

            return decompress(method=3, data=compressed_data)
        else:
            # Unknown compression method - return raw data
            return compressed_data
