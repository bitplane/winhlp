"""Parser for the |SYSTEM internal file."""

from .base import InternalFile
from pydantic import BaseModel, Field
from typing import Tuple, Optional
import struct


class SystemHeader(BaseModel):
    """
    Structure at the beginning of the |SYSTEM file.
    From `helpdeco.h`: SYSTEMHEADER
    """

    magic: int = Field(..., description="Should be 0x036C")
    minor: int = Field(..., description="Help file format version number")
    major: int
    gen_date: int = Field(..., description="Date/time the help file was generated")
    flags: int = Field(..., description="Tells how the help file is compressed")
    raw_data: dict


class SecWindow(BaseModel):
    """
    Structure for a secondary window definition in the |SYSTEM file.
    From `helpdeco.h`: SECWINDOW
    """

    flags: int
    type: bytes = Field(..., max_length=10)
    name: bytes = Field(..., max_length=9)
    caption: bytes = Field(..., max_length=51)
    x: int
    y: int
    width: int
    height: int
    maximize: int
    rgb: Tuple[int, int, int]
    unknown1: int
    rgb_nsr: Tuple[int, int, int]
    unknown2: int
    raw_data: dict


class KeyIndex(BaseModel):
    """
    Defines a keyword index.
    From `helpdeco.h`: KEYINDEX
    """

    btree_name: bytes = Field(..., max_length=10)
    map_name: bytes = Field(..., max_length=10)
    data_name: bytes = Field(..., max_length=10)
    title: bytes = Field(..., max_length=80)
    raw_data: dict


class DLLMaps(BaseModel):
    """
    Defines mappings for 16-bit and 32-bit DLLs.
    From `helpfile.md`.
    """

    win16_retail_dll: str
    win16_debug_dll: str
    win32_retail_dll: str
    win32_debug_dll: str
    raw_data: dict


class DefFont(BaseModel):
    """
    Default dialog font, Windows 95 (HCW 4.00)
    From `helpfile.md`.
    """

    height_in_points: int
    charset: int
    font_name: str
    raw_data: dict


class SystemFile(InternalFile):
    """
    Parses the |SYSTEM file, which contains crucial metadata about the
    help file's version, compression, and configuration.
    """

    header: Optional[SystemHeader] = None
    title: Optional[str] = None
    copyright: Optional[str] = None
    records: list = []

    def __init__(self, **data):
        super().__init__(**data)
        self._parse()

    def _parse(self):
        """
        Parses the |SYSTEM file data.
        """
        self._parse_header()
        if self.header.minor <= 16:
            self._parse_title()
        else:
            self._parse_records()

    def _parse_header(self):
        """
        Parses the header of the |SYSTEM file.
        """
        raw_bytes = self.raw_data[:12]
        magic, minor, major, gen_date, flags = struct.unpack("<HHHlH", raw_bytes)
        parsed_header = {
            "magic": magic,
            "minor": minor,
            "major": major,
            "gen_date": gen_date,
            "flags": flags,
        }
        self.header = SystemHeader(**parsed_header, raw_data={"raw": raw_bytes, "parsed": parsed_header})

    def _parse_title(self):
        """
        Parses the title from a WinHelp 3.0 |SYSTEM file.
        """
        title_data = self.raw_data[12:]
        end_of_string = title_data.find(b"\x00")
        if end_of_string != -1:
            self.title = title_data[:end_of_string].decode("ascii", errors="ignore")

    def _parse_records(self):
        """
        Parses the records from the |SYSTEM file.

        From `helpfile.md`:
        struct
        {
            unsigned short RecordType       type of data in record
            unsigned short DataSize         size of data
            ----
            char Data[DataSize]            dependent on RecordType
        }
        SYSTEMREC[]
        """
        offset = 12  # Start after the header
        while offset < len(self.raw_data):
            record_type, data_size = struct.unpack_from("<HH", self.raw_data, offset)
            offset += 4
            record_data = self.raw_data[offset : offset + data_size]

            if record_type == 1:  # TITLE
                self.title = record_data.split(b"\x00")[0].decode("ascii", errors="ignore")
            elif record_type == 2:  # COPYRIGHT
                self.copyright = record_data.split(b"\x00")[0].decode("ascii", errors="ignore")
            elif record_type == 6:  # SecWindow
                self._parse_sec_window(record_data)
            elif record_type == 14:  # KeyIndex
                self._parse_key_index(record_data)
            elif record_type == 3:  # DLLMaps
                self._parse_dll_maps(record_data)
            elif record_type == 4:  # DefFont
                self._parse_def_font(record_data)
            else:
                # For unknown record types, just store the raw data
                self.records.append({"type": record_type, "size": data_size, "data": record_data})

            offset += data_size

    def _parse_sec_window(self, data: bytes):
        """
        Parses a SecWindow record.
        """
        offset = 0
        flags = struct.unpack_from("<H", data, offset)[0]
        offset += 2

        type = b""
        if flags & 0x01:
            type = struct.unpack_from("<10s", data, offset)[0]
            offset += 10

        name = b""
        if flags & 0x02:
            name = struct.unpack_from("<9s", data, offset)[0]
            offset += 9

        caption = b""
        if flags & 0x04:
            caption = struct.unpack_from("<51s", data, offset)[0]
            offset += 51

        x = 0
        if flags & 0x08:
            x = struct.unpack_from("<h", data, offset)[0]
            offset += 2

        y = 0
        if flags & 0x10:
            y = struct.unpack_from("<h", data, offset)[0]
            offset += 2

        width = 0
        if flags & 0x20:
            width = struct.unpack_from("<h", data, offset)[0]
            offset += 2

        height = 0
        if flags & 0x40:
            height = struct.unpack_from("<h", data, offset)[0]
            offset += 2

        maximize = 0
        if flags & 0x80:
            maximize = struct.unpack_from("<H", data, offset)[0]
            offset += 2

        rgb = (0, 0, 0)
        if flags & 0x100:
            r, g, b = struct.unpack_from("<BBB", data, offset)
            offset += 3
            rgb = (r, g, b)

        unknown1 = 0
        if flags & 0x200:
            unknown1 = struct.unpack_from("<H", data, offset)[0]
            offset += 2

        rgb_nsr = (0, 0, 0)
        if flags & 0x400:
            r, g, b = struct.unpack_from("<BBB", data, offset)
            offset += 3
            rgb_nsr = (r, g, b)

        unknown2 = 0
        if flags & 0x800:
            unknown2 = struct.unpack_from("<H", data, offset)[0]
            offset += 2

        parsed_record = {
            "flags": flags,
            "type": type,
            "name": name,
            "caption": caption,
            "x": x,
            "y": y,
            "width": width,
            "height": height,
            "maximize": maximize,
            "rgb": rgb,
            "unknown1": unknown1,
            "rgb_nsr": rgb_nsr,
            "unknown2": unknown2,
        }
        self.records.append(SecWindow(**parsed_record, raw_data={"raw": data, "parsed": parsed_record}))

    def _parse_key_index(self, data: bytes):
        """
        Parses a KeyIndex record.
        """
        btree_name, map_name, data_name, title = struct.unpack("<10s10s10s80s", data)
        parsed_record = {
            "btree_name": btree_name,
            "map_name": map_name,
            "data_name": data_name,
            "title": title,
        }
        self.records.append(KeyIndex(**parsed_record, raw_data={"raw": data, "parsed": parsed_record}))

    def _parse_dll_maps(self, data: bytes):
        """
        Parses a DLLMaps record.
        """
        # The DLLMaps record is a series of null-terminated strings.
        parts = data.split(b"\x00")
        parsed_record = {
            "win16_retail_dll": parts[0].decode("ascii"),
            "win16_debug_dll": parts[1].decode("ascii"),
            "win32_retail_dll": parts[2].decode("ascii"),
            "win32_debug_dll": parts[3].decode("ascii"),
        }
        self.records.append(DLLMaps(**parsed_record, raw_data={"raw": data, "parsed": parsed_record}))

    def _parse_def_font(self, data: bytes):
        """
        Parses a DefFont record.
        """
        height_in_points, charset, font_name = struct.unpack("<HB32s", data)
        parsed_record = {
            "height_in_points": height_in_points,
            "charset": charset,
            "font_name": font_name.split(b"\x00")[0].decode("ascii"),
        }
        self.records.append(DefFont(**parsed_record, raw_data={"raw": data, "parsed": parsed_record}))
