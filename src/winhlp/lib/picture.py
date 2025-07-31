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
    raw_data: dict


class Hotspot(BaseModel):
    """
    Structure for a single hotspot in a picture.
    From `helpdeco.h`: HOTSPOT
    """

    id0: int
    id1: int
    id2: int
    x: int
    y: int
    w: int
    h: int
    hash_or_macrodataindex: int
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
        return BitmapPicture(**parsed_bitmap, raw_data={"raw": data[start_offset:offset], "parsed": parsed_bitmap})

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
        return MetafilePicture(
            **parsed_metafile, raw_data={"raw": data[start_offset:offset], "parsed": parsed_metafile}
        )

    def _parse_hotspots(self, data: bytes):
        """
        Parses the hotspot data, if present.
        """
        # Hotspot data follows the picture data. The offset is relative to the start of the picture data.
        # The number of hotspots is not explicitly stored in the PictureHeader, but rather
        # inferred from the hotspot_size in BitmapPicture/MetafilePicture.
        # For now, we'll assume a simple case where hotspots are at the end of the picture data.
        # A more robust implementation would need to track the current offset more carefully.

        # This is a simplified placeholder. Real hotspot parsing is more complex.
        # It involves iterating through the hotspot data based on hotspot_size and parsing each Hotspot structure.
        # The HotspotStringData usually follows all Hotspot structures.

        # For demonstration, let's assume a single hotspot for now if hotspot_size > 0
        if self.bitmaps:
            for bitmap in self.bitmaps:
                if bitmap.hotspot_size > 0:
                    hotspot_offset = bitmap.hotspot_offset
                    # Assuming a fixed size for a single hotspot for now (20 bytes based on helpdeco.h)
                    if len(data) >= hotspot_offset + 20:
                        id0, id1, id2, x, y, w, h, hash_or_macrodataindex = struct.unpack_from(
                            "<HHHHllll", data, hotspot_offset
                        )
                        parsed_hotspot = {
                            "id0": id0,
                            "id1": id1,
                            "id2": id2,
                            "x": x,
                            "y": y,
                            "w": w,
                            "h": h,
                            "hash_or_macrodataindex": hash_or_macrodataindex,
                        }
                        hotspot = Hotspot(
                            **parsed_hotspot,
                            raw_data={"raw": data[hotspot_offset : hotspot_offset + 20], "parsed": parsed_hotspot},
                        )
                        self.hotspots.append(hotspot)

                        # Assuming hotspot string data immediately follows the hotspot structure
                        # This is a simplification; actual parsing might involve more complex offsets
                        hotspot_string_offset = hotspot_offset + 20
                        if len(data) > hotspot_string_offset:
                            # Read null-terminated strings
                            current_string_offset = hotspot_string_offset
                            hotspot_name_bytes = b""
                            while current_string_offset < len(data) and data[current_string_offset] != 0x00:
                                hotspot_name_bytes += data[current_string_offset : current_string_offset + 1]
                                current_string_offset += 1
                            hotspot_name = hotspot_name_bytes.decode("ascii")
                            current_string_offset += 1  # Skip null terminator

                            context_name_or_macro_bytes = b""
                            while current_string_offset < len(data) and data[current_string_offset] != 0x00:
                                context_name_or_macro_bytes += data[current_string_offset : current_string_offset + 1]
                                current_string_offset += 1
                            context_name_or_macro = context_name_or_macro_bytes.decode("ascii")
                            current_string_offset += 1  # Skip null terminator

                            parsed_hotspot_string = {
                                "hotspot_name": hotspot_name,
                                "context_name_or_macro": context_name_or_macro,
                            }
                            hotspot_string = HotspotStringData(
                                **parsed_hotspot_string,
                                raw_data={
                                    "raw": data[hotspot_string_offset:current_string_offset],
                                    "parsed": parsed_hotspot_string,
                                },
                            )
                            self.hotspot_strings.append(hotspot_string)
        elif self.metafiles:
            for metafile in self.metafiles:
                if metafile.hotspot_size > 0:
                    hotspot_offset = metafile.hotspot_offset
                    # Assuming a fixed size for a single hotspot for now (20 bytes based on helpdeco.h)
                    if len(data) >= hotspot_offset + 20:
                        id0, id1, id2, x, y, w, h, hash_or_macrodataindex = struct.unpack_from(
                            "<HHHHllll", data, hotspot_offset
                        )
                        parsed_hotspot = {
                            "id0": id0,
                            "id1": id1,
                            "id2": id2,
                            "x": x,
                            "y": y,
                            "w": w,
                            "h": h,
                            "hash_or_macrodataindex": hash_or_macrodataindex,
                        }
                        hotspot = Hotspot(
                            **parsed_hotspot,
                            raw_data={"raw": data[hotspot_offset : hotspot_offset + 20], "parsed": parsed_hotspot},
                        )
                        self.hotspots.append(hotspot)

                        # Assuming hotspot string data immediately follows the hotspot structure
                        # This is a simplification; actual parsing might involve more complex offsets
                        hotspot_string_offset = hotspot_offset + 20
                        if len(data) > hotspot_string_offset:
                            # Read null-terminated strings
                            current_string_offset = hotspot_string_offset
                            hotspot_name_bytes = b""
                            while current_string_offset < len(data) and data[current_string_offset] != 0x00:
                                hotspot_name_bytes += data[current_string_offset : current_string_offset + 1]
                                current_string_offset += 1
                            hotspot_name = hotspot_name_bytes.decode("ascii")
                            current_string_offset += 1  # Skip null terminator

                            context_name_or_macro_bytes = b""
                            while current_string_offset < len(data) and data[current_string_offset] != 0x00:
                                context_name_or_macro_bytes += data[current_string_offset : current_string_offset + 1]
                                current_string_offset += 1
                            context_name_or_macro = context_name_or_macro_bytes.decode("ascii")
                            current_string_offset += 1  # Skip null terminator

                            parsed_hotspot_string = {
                                "hotspot_name": hotspot_name,
                                "context_name_or_macro": context_name_or_macro,
                            }
                            hotspot_string = HotspotStringData(
                                **parsed_hotspot_string,
                                raw_data={
                                    "raw": data[hotspot_string_offset:current_string_offset],
                                    "parsed": parsed_hotspot_string,
                                },
                            )
                            self.hotspot_strings.append(hotspot_string)
