"""Parser for the |SYSTEM internal file."""

from .base import InternalFile
from pydantic import BaseModel, Field, model_serializer
from typing import Tuple, Optional, Any
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
    encoding: str = "cp1252"  # Default Windows Western European
    lcid: Optional[int] = None
    charset: Optional[int] = None
    icon: Optional[bytes] = None  # Type 5: ICON file data
    cnt_filename: Optional[str] = None  # Type 10: CNT filename
    groups: list = []  # Type 13: GROUPS definitions
    dllmaps: list = []  # Type 19: DLLMAPS definitions
    keyword_indices: list = []  # Characters that have keyword index files (from type 14 records)
    parent_hlp: Any = None
    is_mvp: bool = False  # Is this a MultiMedia Viewer file?

    def __init__(self, parent_hlp=None, **data):
        super().__init__(**data)
        self.parent_hlp = parent_hlp
        self.is_mvp = self._detect_mvp()
        self._parse()

    @model_serializer
    def serialize_model(self):
        """Custom serializer to exclude parent_hlp circular reference"""
        data = self.__dict__.copy()
        data.pop("parent_hlp", None)  # Remove circular reference
        return data

    def _detect_mvp(self) -> bool:
        """
        Detects if this is a MultiMedia Viewer (MVP) file.
        MVP files have extensions starting with 'M' (e.g., .MVB).
        """
        if self.parent_hlp and hasattr(self.parent_hlp, "filepath"):
            import os

            ext = os.path.splitext(self.parent_hlp.filepath)[1].upper()
            # MVP files have extensions starting with 'M'
            return len(ext) > 1 and ext[1] == "M"
        return False

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
                self.title = self._decode_text(record_data.split(b"\x00")[0])
            elif record_type == 2:  # COPYRIGHT
                self.copyright = self._decode_text(record_data.split(b"\x00")[0])
            elif record_type == 3:  # CONTENTS
                self._parse_contents(record_data)
            elif record_type == 4:  # MACRO
                self._parse_macro(record_data)
            elif record_type == 5:  # ICON
                self._parse_icon(record_data)
            elif record_type == 6:  # WINDOW
                self._parse_window(record_data)
            elif record_type == 8:  # CITATION
                self._parse_citation(record_data)
            elif record_type == 9:  # LCID (Locale ID)
                self._parse_lcid(record_data)
            elif record_type == 10:  # CNT
                self._parse_cnt(record_data)
            elif record_type == 11:  # CHARSET
                self._parse_charset(record_data)
            elif record_type == 12:  # DEFFONT
                self._parse_def_font(record_data)
            elif record_type == 13:  # GROUPS
                self._parse_groups(record_data)
            elif record_type == 14:  # KeyIndex
                self._parse_key_index(record_data)
            elif record_type == 18:  # LANGUAGE (0x0012)
                self._parse_language(record_data)
            elif record_type == 19:  # DLLMAPS
                self._parse_dllmaps(record_data)
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
        Parses a KeyIndex record (record type 14).

        Can be either INDEX_SEPARATORS (string) or KEYINDEX (struct)
        depending on whether it's a multimedia file.

        From C code: keyindex[SysRec->Data[1] - '0'] = TRUE;
        This tracks which characters (A-Z, a-z) have keyword index files.
        """
        # Check if it's likely a KEYINDEX struct (110 bytes) or INDEX_SEPARATORS (string)
        if len(data) == 110:
            # KEYINDEX structure format from helldeco.h:
            # char btreename[10], mapname[10], dataname[10], title[80]
            btree_name = data[0:10].decode("ascii", errors="ignore").split("\x00")[0]
            map_name = data[10:20].decode("ascii", errors="ignore").split("\x00")[0]
            data_name = data[20:30].decode("ascii", errors="ignore").split("\x00")[0]
            title = data[30:110].decode("ascii", errors="ignore").split("\x00")[0]

            parsed_record = {
                "format": "KEYINDEX",
                "btree_name": btree_name,
                "map_name": map_name,
                "data_name": data_name,
                "title": title,
            }
        else:
            # INDEX_SEPARATORS - null-terminated string of separator characters
            separators = self._decode_text(data.split(b"\x00")[0])
            parsed_record = {
                "format": "INDEX_SEPARATORS",
                "separators": separators,
            }

            # Track keyword index character from C logic: keyindex[SysRec->Data[1] - '0'] = TRUE
            # In MVP files, the second character indicates which keyword index this is
            if len(data) >= 2 and self.is_mvp:
                char = chr(data[1]) if 32 <= data[1] <= 126 else None
                if char and char.isalnum() and char not in self.keyword_indices:
                    self.keyword_indices.append(char)

        self.records.append(
            {"type": "KEYINDEX", "key_index_info": parsed_record, "raw_data": {"raw": data, "parsed": parsed_record}}
        )

    def _parse_def_font(self, data: bytes):
        """
        Parses a DefFont record (type 12).
        In MVP files, this is FTINDEX data instead.
        """
        if self.is_mvp:
            # FTINDEX format in MVP files
            # From C code: printf("[FTINDEX] dtype %s\n", SysRec->Data);
            ftindex_data = self._decode_text(data.split(b"\x00")[0])
            parsed_record = {"ftindex_dtype": ftindex_data}
            self.records.append(
                {"type": "FTINDEX", "ftindex_dtype": ftindex_data, "raw_data": {"raw": data, "parsed": parsed_record}}
            )
        else:
            # Regular DEFFONT format
            # From C code: printf("DEFFONT=%s,%d,%d\n", SysRec->Data+2, *(unsigned char*)SysRec->Data, *(unsigned char*)(SysRec->Data+1));
            if len(data) >= 2:
                font_size = data[0] if len(data) > 0 else 0
                charset = data[1] if len(data) > 1 else 0
                font_name = self._decode_text(data[2:].split(b"\x00")[0]) if len(data) > 2 else ""
            else:
                font_size = 0
                charset = 0
                font_name = ""

            parsed_record = {
                "height_in_points": font_size,
                "charset": charset,
                "font_name": font_name,
            }
            self.records.append(DefFont(**parsed_record, raw_data={"raw": data, "parsed": parsed_record}))

    def _decode_text(self, data: bytes) -> str:
        """
        Decode text data using the appropriate encoding for this help file.
        Falls back through multiple encodings to handle international text.
        """
        if not data:
            return ""

        # Try the determined encoding first
        try:
            return data.decode(self.encoding)
        except UnicodeDecodeError:
            pass

        # Fall back through common Windows encodings
        fallback_encodings = ["cp1252", "cp1251", "cp850", "iso-8859-1"]

        for encoding in fallback_encodings:
            if encoding != self.encoding:  # Don't retry the same encoding
                try:
                    return data.decode(encoding)
                except UnicodeDecodeError:
                    continue

        # Final fallback: decode with errors='replace' to avoid crashes
        return data.decode("cp1252", errors="replace")

    def _parse_contents(self, data: bytes):
        """Parses a CONTENTS record (record type 3)."""
        contents_offset = struct.unpack("<l", data[:4])[0] if len(data) >= 4 else 0
        parsed_record = {"contents_offset": contents_offset}
        self.records.append(
            {"type": "CONTENTS", "contents_offset": contents_offset, "raw_data": {"raw": data, "parsed": parsed_record}}
        )

    def _parse_macro(self, data: bytes):
        """Parses a MACRO record (record type 4)."""
        macro_text = self._decode_text(data.split(b"\x00")[0])
        parsed_record = {"macro_text": macro_text}
        self.records.append(
            {"type": "MACRO", "macro_text": macro_text, "raw_data": {"raw": data, "parsed": parsed_record}}
        )

    def _parse_citation(self, data: bytes):
        """Parses a CITATION record (record type 8)."""
        citation_text = self._decode_text(data.split(b"\x00")[0])
        parsed_record = {"citation_text": citation_text}
        self.records.append(
            {"type": "CITATION", "citation_text": citation_text, "raw_data": {"raw": data, "parsed": parsed_record}}
        )

    def _parse_lcid(self, data: bytes):
        """Parses a LCID (Locale ID) record (record type 9)."""
        if len(data) >= 10:
            lcid1 = struct.unpack("<h", data[8:10])[0] if len(data) >= 10 else 0
            lcid2 = struct.unpack("<h", data[0:2])[0] if len(data) >= 2 else 0
            lcid3 = struct.unpack("<h", data[2:4])[0] if len(data) >= 4 else 0

            self.lcid = lcid1  # Primary locale ID

            # Update encoding based on LCID
            self._update_encoding_from_lcid(lcid1)

            parsed_record = {"lcid1": lcid1, "lcid2": lcid2, "lcid3": lcid3}
            self.records.append(
                {"type": "LCID", "lcids": [lcid1, lcid2, lcid3], "raw_data": {"raw": data, "parsed": parsed_record}}
            )

    def _parse_charset(self, data: bytes):
        """Parses a CHARSET record (record type 11)."""
        if len(data) >= 2:
            charset = struct.unpack("<H", data[:2])[0]
            self.charset = charset

            # Update encoding based on charset
            self._update_encoding_from_charset(charset)

            parsed_record = {"charset": charset}
            self.records.append(
                {"type": "CHARSET", "charset": charset, "raw_data": {"raw": data, "parsed": parsed_record}}
            )

    def _update_encoding_from_lcid(self, lcid: int):
        """Update encoding based on Windows LCID."""
        # Common Windows LCIDs and their codepages
        lcid_to_encoding = {
            0x0409: "cp1252",  # English (US)
            0x0809: "cp1252",  # English (UK)
            0x040C: "cp1252",  # French
            0x0407: "cp1252",  # German
            0x0410: "cp1252",  # Italian
            0x040A: "cp1252",  # Spanish
            0x0419: "cp1251",  # Russian
            0x0411: "cp932",  # Japanese
            0x0412: "cp949",  # Korean
            0x0804: "cp936",  # Chinese Simplified
            0x0404: "cp950",  # Chinese Traditional
        }

        if lcid in lcid_to_encoding:
            self.encoding = lcid_to_encoding[lcid]

    def _update_encoding_from_charset(self, charset: int):
        """Update encoding based on Windows charset."""
        # Common Windows charsets and their codepages
        charset_to_encoding = {
            0: "cp1252",  # ANSI_CHARSET
            1: "cp1252",  # DEFAULT_CHARSET
            2: "cp1252",  # SYMBOL_CHARSET
            128: "cp932",  # SHIFTJIS_CHARSET
            129: "cp949",  # HANGEUL_CHARSET
            134: "cp936",  # GB2312_CHARSET
            136: "cp950",  # CHINESEBIG5_CHARSET
            161: "cp1253",  # GREEK_CHARSET
            162: "cp1254",  # TURKISH_CHARSET
            177: "cp1255",  # HEBREW_CHARSET
            178: "cp1256",  # ARABIC_CHARSET
            186: "cp1257",  # BALTIC_CHARSET
            204: "cp1251",  # RUSSIAN_CHARSET
            222: "cp874",  # THAI_CHARSET
            238: "cp1250",  # EASTEUROPE_CHARSET
        }

        if charset in charset_to_encoding:
            self.encoding = charset_to_encoding[charset]

    def _parse_icon(self, data: bytes):
        """Parses an ICON record (record type 5)."""
        # The data is a complete Windows .ICO file format
        self.icon = data
        parsed_record = {"icon_size": len(data)}
        self.records.append({"type": "ICON", "icon_data": data, "raw_data": {"raw": data, "parsed": parsed_record}})

    def _parse_window(self, data: bytes):
        """Parses a WINDOW record (record type 6)."""
        # Determine window type based on data size
        # SECWINDOW = 89 bytes, MVBWINDOW = 90 bytes (has extra MoreFlags byte)
        if len(data) == 89:
            self._parse_secwindow(data)
        elif len(data) == 90:
            self._parse_mvbwindow(data)
        else:
            # Unknown window format, store as raw data
            parsed_record = {"window_type": "unknown", "size": len(data)}
            self.records.append(
                {"type": "WINDOW", "window_data": data, "raw_data": {"raw": data, "parsed": parsed_record}}
            )

    def _parse_secwindow(self, data: bytes):
        """Parse SECWINDOW structure (WinHelp 3.1)."""
        offset = 0

        flags = struct.unpack_from("<H", data, offset)[0]
        offset += 2

        type_str = data[offset : offset + 10].rstrip(b"\x00").decode("latin-1", errors="replace")
        offset += 10

        name = data[offset : offset + 9].rstrip(b"\x00").decode("latin-1", errors="replace")
        offset += 9

        caption = data[offset : offset + 51].rstrip(b"\x00").decode("latin-1", errors="replace")
        offset += 51

        x, y, width, height, maximize = struct.unpack_from("<hhhhh", data, offset)
        offset += 10

        rgb, unknown1, rgb_nsr = struct.unpack_from("<LHL", data, offset)
        offset += 10

        unknown2 = 0
        if flags & 0x800:
            unknown2 = struct.unpack_from("<H", data, offset)[0]
            offset += 2

        parsed_record = {
            "window_type": "SECWINDOW",
            "flags": flags,
            "type": type_str,
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

        self.records.append(
            {"type": "WINDOW", "window_info": parsed_record, "raw_data": {"raw": data, "parsed": parsed_record}}
        )

    def _parse_mvbwindow(self, data: bytes):
        """Parse MVBWINDOW structure (Multimedia Viewer 2.0)."""
        # MVBWINDOW structure is actually much larger (132 bytes) than what we typically see
        # Most files seem to have truncated or different structures, so handle gracefully
        offset = 0

        if len(data) < 73:  # Minimum required for basic fields
            # Store as unknown window format
            parsed_record = {"window_type": "unknown_mvb", "size": len(data)}
            self.records.append(
                {"type": "WINDOW", "window_data": data, "raw_data": {"raw": data, "parsed": parsed_record}}
            )
            return

        flags = struct.unpack_from("<H", data, offset)[0]
        offset += 2

        type_str = data[offset : offset + 10].rstrip(b"\x00").decode("latin-1", errors="replace")
        offset += 10

        name = data[offset : offset + 9].rstrip(b"\x00").decode("latin-1", errors="replace")
        offset += 9

        caption = data[offset : offset + 51].rstrip(b"\x00").decode("latin-1", errors="replace")
        offset += 51

        more_flags = data[offset] if offset < len(data) else 0
        offset += 1

        # Parse remaining fields if available
        x = y = width = height = maximize = 0
        if offset + 10 <= len(data):
            x, y, width, height, maximize = struct.unpack_from("<hhhhh", data, offset)
            offset += 10

        # Parse color fields if available (simplified - just extract what we can)
        rgb = unknown1 = rgb_nsr = unknown2 = 0
        if offset + 4 <= len(data):
            rgb = struct.unpack_from("<L", data, offset)[0]
            offset += 4
        if offset + 2 <= len(data):
            unknown1 = struct.unpack_from("<H", data, offset)[0]
            offset += 2
        if offset + 4 <= len(data):
            rgb_nsr = struct.unpack_from("<L", data, offset)[0]
            offset += 4
        if offset + 2 <= len(data):
            unknown2 = struct.unpack_from("<H", data, offset)[0]
            offset += 2

        parsed_record = {
            "window_type": "MVBWINDOW",
            "flags": flags,
            "type": type_str,
            "name": name,
            "caption": caption,
            "more_flags": more_flags,
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

        self.records.append(
            {"type": "WINDOW", "window_info": parsed_record, "raw_data": {"raw": data, "parsed": parsed_record}}
        )

    def _parse_cnt(self, data: bytes):
        """Parses a CNT record (record type 10)."""
        # CNT filename - null-terminated string
        cnt_filename = self._decode_text(data.split(b"\x00")[0])
        self.cnt_filename = cnt_filename
        parsed_record = {"cnt_filename": cnt_filename}
        self.records.append(
            {"type": "CNT", "cnt_filename": cnt_filename, "raw_data": {"raw": data, "parsed": parsed_record}}
        )

    def _parse_groups(self, data: bytes):
        """Parses a GROUPS record (record type 13)."""
        # GROUP definition - null-terminated string
        group_definition = self._decode_text(data.split(b"\x00")[0])
        self.groups.append(group_definition)
        parsed_record = {"group_definition": group_definition}
        self.records.append(
            {"type": "GROUPS", "group_definition": group_definition, "raw_data": {"raw": data, "parsed": parsed_record}}
        )

    def _parse_language(self, data: bytes):
        """
        Parses a LANGUAGE record (type 18/0x0012).
        From C code: if (SysRec->Data[0]) printf("LANGUAGE=%s\n", SysRec->Data);
        """
        if data and data[0]:  # Only process if first byte is non-zero
            language = self._decode_text(data.split(b"\x00")[0])
            parsed_record = {"language": language}
            self.records.append(
                {"type": "LANGUAGE", "language": language, "raw_data": {"raw": data, "parsed": parsed_record}}
            )

    def _parse_dllmaps(self, data: bytes):
        """Parses a DLLMAPS record (record type 19)."""
        # DLLMAPS structure: four null-terminated strings
        # Win16RetailDLL, Win16DebugDLL, Win32RetailDLL, Win32DebugDLL
        strings = []
        offset = 0

        # Parse up to 4 null-terminated strings
        for i in range(4):
            if offset >= len(data):
                break
            string_start = offset
            while offset < len(data) and data[offset] != 0:
                offset += 1
            if offset < len(data):
                string_value = self._decode_text(data[string_start:offset])
                strings.append(string_value)
                offset += 1  # Skip null terminator
            else:
                break

        # Pad with empty strings if needed
        while len(strings) < 4:
            strings.append("")

        dllmap = DLLMaps(
            win16_retail_dll=strings[0],
            win16_debug_dll=strings[1],
            win32_retail_dll=strings[2],
            win32_debug_dll=strings[3],
            raw_data={"raw": data, "parsed": {"strings": strings}},
        )

        self.dllmaps.append(dllmap)
        parsed_record = {
            "win16_retail_dll": strings[0],
            "win16_debug_dll": strings[1],
            "win32_retail_dll": strings[2],
            "win32_debug_dll": strings[3],
        }
        self.records.append({"type": "DLLMAPS", "dllmap": dllmap, "raw_data": {"raw": data, "parsed": parsed_record}})
