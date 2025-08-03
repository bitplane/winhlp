"""Parser for the |FONT internal file."""

from .base import InternalFile
from pydantic import BaseModel, Field
from typing import List, Tuple, Optional, Any
import struct


class FontHeader(BaseModel):
    """
    Structure at the beginning of the |FONT file.
    From `helpdeco.h`: FONTHEADER
    """

    num_facenames: int
    num_descriptors: int
    facenames_offset: int
    descriptors_offset: int
    num_formats: int
    formats_offset: int
    num_charmaps: int
    charmaps_offset: int
    raw_data: dict


class OldFont(BaseModel):
    """
    Font descriptor for older HLP files.
    From `helpdeco.h`: OLDFONT
    """

    attributes: int
    half_points: int
    font_family: int
    font_name_index: int
    fg_rgb: Tuple[int, int, int]
    bg_rgb: Tuple[int, int, int]
    raw_data: dict


class MVBFont(BaseModel):
    """
    Font descriptor for MultiMedia Viewer (MVP) files.
    From `helpdeco.h`: MVBFONT
    """

    font_name: int  # int16_t FontName
    expndtw: int  # int16_t expndtw
    style: int  # uint16_t style
    fg_rgb: Tuple[int, int, int]  # unsigned char FGRGB[3]
    bg_rgb: Tuple[int, int, int]  # unsigned char BGRGB[3]
    height: int  # int32_t Height
    mostly_zero: bytes  # unsigned char mostlyzero[12]
    weight: int  # int16_t Weight
    unknown10: int  # unsigned char unknown10
    unknown11: int  # unsigned char unknown11
    italic: int  # unsigned char Italic
    underline: int  # unsigned char Underline
    strike_out: int  # unsigned char StrikeOut
    double_underline: int  # unsigned char DoubleUnderline
    small_caps: int  # unsigned char SmallCaps
    unknown17: int  # unsigned char unknown17
    unknown18: int  # unsigned char unknown18
    pitch_and_family: int  # unsigned char PitchAndFamily
    unknown20: int  # unsigned char unknown20
    charset: int  # unsigned char Charset
    unknown22: int  # unsigned char unknown22
    unknown23: int  # unsigned char unknown23
    unknown24: int  # unsigned char unknown24
    up: int  # signed char up
    raw_data: dict


class NewFont(BaseModel):
    """
    Font descriptor for newer HLP files.
    From `helpdeco.h`: NEWFONT
    """

    unknown1: int
    font_name: int
    fg_rgb: Tuple[int, int, int]
    bg_rgb: Tuple[int, int, int]
    unknown5: int
    unknown6: int
    unknown7: int
    unknown8: int
    unknown9: int
    height: int
    mostly_zero: bytes = Field(..., max_length=12)
    weight: int
    unknown10: int
    unknown11: int
    italic: int
    underline: int
    strike_out: int
    double_underline: int
    small_caps: int
    unknown17: int
    unknown18: int
    pitch_and_family: int
    raw_data: dict


class MVBStyle(BaseModel):
    """
    Character style for MultiMedia Viewer (MVP) files.
    From `helpdeco.h`: MVBSTYLE
    """

    wStyleNum: int  # uint16_t StyleNum
    wBasedOn: int  # uint16_t BasedOn
    nf: MVBFont  # MVBFONT font
    bReserved: bytes = Field(..., max_length=35)  # char unknown[35]
    bStyleName: bytes = Field(..., max_length=65)  # char StyleName[65]
    raw_data: dict


class NewStyle(BaseModel):
    """
    Character style for newer HLP files.
    From `helpdeco.h`: NEWSTYLE
    """

    wStyleNum: int
    wBasedOn: int
    nf: NewFont
    bReserved: bytes = Field(..., max_length=35)
    bStyleName: bytes = Field(..., max_length=65)
    raw_data: dict


class CharMapHeader(BaseModel):
    """
    Header for a character mapping table (*.tbl file).
    From `helpdeco.h`: CHARMAPHEADER
    """

    magic: int
    size: int
    unknown1: int
    unknown2: int
    entries: int
    ligatures: int
    lig_len: int
    unknown: List[int] = Field(..., max_length=13)
    raw_data: dict


class CharMapEntry(BaseModel):
    """
    Entry in a character mapping table.
    From `helpfile.md`.
    """

    char_class: int
    order: int
    normal: int
    clipboard: int
    mac: int
    mac_clipboard: int
    unused: int
    raw_data: dict


class FontFile(InternalFile):
    """
    Parses the |FONT file and manages the font descriptors.
    """

    header: Optional[FontHeader] = None
    facenames: list = []
    descriptors: list = []
    styles: list = []
    charmaps: list = []
    parsed_charmaps: dict = {}
    system_file: Any = None

    def __init__(self, system_file: Any = None, **data):
        super().__init__(**data)
        self.system_file = system_file
        self.parsed_charmaps = {}
        self._parse()

    def _parse(self):
        """
        Parses the |FONT file data.
        """
        self._parse_header()
        self._parse_facenames()
        self._parse_descriptors()
        self._parse_styles()
        self._parse_charmaps()

    def _parse_header(self):
        """
        Parses the header of the |FONT file.
        """
        raw_bytes = self.raw_data[:16]
        if len(raw_bytes) < 16:
            raise ValueError("Invalid |FONT header size")

        (
            num_facenames,
            num_descriptors,
            facenames_offset,
            descriptors_offset,
            num_formats_raw,
            formats_offset_raw,
            num_charmaps_raw,
            charmaps_offset_raw,
        ) = struct.unpack("<HHHHHHHH", raw_bytes)

        num_formats = 0
        formats_offset = 0
        num_charmaps = 0
        charmaps_offset = 0

        if facenames_offset >= 12:
            num_formats = num_formats_raw
            formats_offset = formats_offset_raw

        if facenames_offset >= 16:
            num_charmaps = num_charmaps_raw
            charmaps_offset = charmaps_offset_raw

        parsed_header = {
            "num_facenames": num_facenames,
            "num_descriptors": num_descriptors,
            "facenames_offset": facenames_offset,
            "descriptors_offset": descriptors_offset,
            "num_formats": num_formats,
            "formats_offset": formats_offset,
            "num_charmaps": num_charmaps,
            "charmaps_offset": charmaps_offset,
        }

        self.header = FontHeader(**parsed_header, raw_data={"raw": raw_bytes, "parsed": parsed_header})

    def _parse_facenames(self):
        """
        Parses the font facenames.

        From helpdeco source: facenames are fixed-length entries, not null-terminated.
        Length of each entry = (DescriptorsOffset - FacenamesOffset) / NumFacenames
        """
        if self.header.num_facenames == 0:
            return

        # Calculate the length of each facename entry
        facenames_section_size = self.header.descriptors_offset - self.header.facenames_offset
        entry_length = facenames_section_size // self.header.num_facenames

        offset = self.header.facenames_offset
        for _ in range(self.header.num_facenames):
            facename_bytes = self.raw_data[offset : offset + entry_length]
            # Find the first null byte to trim the string
            null_pos = facename_bytes.find(b"\x00")
            if null_pos != -1:
                facename_bytes = facename_bytes[:null_pos]

            facename = facename_bytes.decode("ascii", errors="ignore")
            self.facenames.append(facename)
            offset += entry_length

    def _parse_descriptors(self):
        """
        Parses the font descriptors.
        """
        offset = self.header.descriptors_offset
        is_mvp = self.system_file and hasattr(self.system_file, "is_mvp") and self.system_file.is_mvp

        for _ in range(self.header.num_descriptors):
            if is_mvp:
                # MVBFont - parse according to helpdeco MVBFONT structure
                # sizeof_MVBFONT = 48 bytes
                raw_bytes = self.raw_data[offset : offset + 48]
                if len(raw_bytes) < 48:
                    break

                # Parse MVBFONT structure
                font_name = struct.unpack("<h", raw_bytes[0:2])[0]  # int16_t FontName
                expndtw = struct.unpack("<h", raw_bytes[2:4])[0]  # int16_t expndtw
                style = struct.unpack("<H", raw_bytes[4:6])[0]  # uint16_t style
                fg_r, fg_g, fg_b = raw_bytes[6], raw_bytes[7], raw_bytes[8]  # FGRGB[3]
                bg_r, bg_g, bg_b = raw_bytes[9], raw_bytes[10], raw_bytes[11]  # BGRGB[3]
                height = struct.unpack("<l", raw_bytes[12:16])[0]  # int32_t Height
                mostly_zero = raw_bytes[16:28]  # mostlyzero[12]
                weight = struct.unpack("<h", raw_bytes[28:30])[0]  # int16_t Weight
                unknown10 = raw_bytes[30]
                unknown11 = raw_bytes[31]
                italic = raw_bytes[32]
                underline = raw_bytes[33]
                strike_out = raw_bytes[34]
                double_underline = raw_bytes[35]
                small_caps = raw_bytes[36]
                unknown17 = raw_bytes[37]
                unknown18 = raw_bytes[38]
                pitch_and_family = raw_bytes[39]
                unknown20 = raw_bytes[40]
                charset = raw_bytes[41]
                unknown22 = raw_bytes[42]
                unknown23 = raw_bytes[43]
                unknown24 = raw_bytes[44]
                up = struct.unpack("b", raw_bytes[45:46])[0]  # signed char

                parsed_descriptor = {
                    "font_name": font_name,
                    "expndtw": expndtw,
                    "style": style,
                    "fg_rgb": (fg_r, fg_g, fg_b),
                    "bg_rgb": (bg_r, bg_g, bg_b),
                    "height": height,
                    "mostly_zero": mostly_zero,
                    "weight": weight,
                    "unknown10": unknown10,
                    "unknown11": unknown11,
                    "italic": italic,
                    "underline": underline,
                    "strike_out": strike_out,
                    "double_underline": double_underline,
                    "small_caps": small_caps,
                    "unknown17": unknown17,
                    "unknown18": unknown18,
                    "pitch_and_family": pitch_and_family,
                    "unknown20": unknown20,
                    "charset": charset,
                    "unknown22": unknown22,
                    "unknown23": unknown23,
                    "unknown24": unknown24,
                    "up": up,
                }
                self.descriptors.append(
                    MVBFont(**parsed_descriptor, raw_data={"raw": raw_bytes, "parsed": parsed_descriptor})
                )
                offset += 48
            elif self.system_file and self.system_file.header.minor > 16:
                # NewFont - parse according to helpdeco NEWFONT structure
                raw_bytes = self.raw_data[offset : offset + 42]
                if len(raw_bytes) < 42:
                    # Fallback for files with shorter structures (39 bytes)
                    raw_bytes = self.raw_data[offset : offset + 39]
                    if len(raw_bytes) < 39:
                        break

                # Parse all fields according to helpdeco.h NEWFONT structure
                unknown1 = raw_bytes[0]
                font_name = struct.unpack("<h", raw_bytes[1:3])[0]
                fg_r, fg_g, fg_b = raw_bytes[3], raw_bytes[4], raw_bytes[5]
                bg_r, bg_g, bg_b = raw_bytes[6], raw_bytes[7], raw_bytes[8]
                unknown5 = raw_bytes[9]
                unknown6 = raw_bytes[10]
                unknown7 = raw_bytes[11]
                unknown8 = raw_bytes[12]
                unknown9 = raw_bytes[13]
                height = struct.unpack("<l", raw_bytes[14:18])[0]
                mostly_zero = raw_bytes[18:30]  # 12 bytes
                weight = struct.unpack("<h", raw_bytes[30:32])[0]
                unknown10 = raw_bytes[32]
                unknown11 = raw_bytes[33]
                italic = raw_bytes[34]
                underline = raw_bytes[35]
                strike_out = raw_bytes[36]
                double_underline = raw_bytes[37]
                small_caps = raw_bytes[38]
                # Parse the remaining 3 bytes if available (full NEWFONT structure)
                if len(raw_bytes) >= 42:
                    unknown17 = raw_bytes[39]
                    unknown18 = raw_bytes[40]
                    pitch_and_family = raw_bytes[41]
                else:
                    # Fallback for shorter structures
                    unknown17 = 0
                    unknown18 = 0
                    pitch_and_family = 0

                parsed_descriptor = {
                    "unknown1": unknown1,
                    "font_name": font_name,
                    "fg_rgb": (fg_r, fg_g, fg_b),
                    "bg_rgb": (bg_r, bg_g, bg_b),
                    "unknown5": unknown5,
                    "unknown6": unknown6,
                    "unknown7": unknown7,
                    "unknown8": unknown8,
                    "unknown9": unknown9,
                    "height": height,
                    "mostly_zero": mostly_zero,
                    "weight": weight,
                    "unknown10": unknown10,
                    "unknown11": unknown11,
                    "italic": italic,
                    "underline": underline,
                    "strike_out": strike_out,
                    "double_underline": double_underline,
                    "small_caps": small_caps,
                    "unknown17": unknown17,
                    "unknown18": unknown18,
                    "pitch_and_family": pitch_and_family,
                }
                self.descriptors.append(
                    NewFont(**parsed_descriptor, raw_data={"raw": raw_bytes, "parsed": parsed_descriptor})
                )
                offset += len(raw_bytes)  # Advance by actual bytes read (39 or 42)
            else:
                # OldFont
                raw_bytes = self.raw_data[offset : offset + 8]
                if len(raw_bytes) < 8:
                    break

                attributes, half_points, font_family, font_name_index = struct.unpack("<BBBH", raw_bytes[:5])
                fg_r, fg_g, fg_b = struct.unpack("<BBB", raw_bytes[5:8])

                parsed_descriptor = {
                    "attributes": attributes,
                    "half_points": half_points,
                    "font_family": font_family,
                    "font_name_index": font_name_index,
                    "fg_rgb": (fg_r, fg_g, fg_b),
                    "bg_rgb": (0, 0, 0),  # Not present in OldFont
                }

                self.descriptors.append(
                    OldFont(**parsed_descriptor, raw_data={"raw": raw_bytes, "parsed": parsed_descriptor})
                )
                offset += 8

    def _parse_styles(self):
        """
        Parses the character styles.
        """
        if self.header.num_formats == 0:
            return

        offset = self.header.formats_offset
        is_mvp = self.system_file and hasattr(self.system_file, "is_mvp") and self.system_file.is_mvp

        for i in range(self.header.num_formats):
            if is_mvp:
                # MVBStyle - parse according to helpdeco MVBSTYLE structure
                # sizeof_MVBSTYLE = 152 bytes (2+2+48+35+65)
                raw_bytes = self.raw_data[offset : offset + 152]
                if len(raw_bytes) < 152:
                    break

                wStyleNum, wBasedOn = struct.unpack_from("<HH", raw_bytes)
                font_data = raw_bytes[4:52]  # MVBFont is 48 bytes
                bReserved = raw_bytes[52:87]  # 35 bytes
                bStyleName = raw_bytes[87:152]  # 65 bytes

                # Parse the embedded MVBFont data
                font_name = struct.unpack("<h", font_data[0:2])[0]
                expndtw = struct.unpack("<h", font_data[2:4])[0]
                style = struct.unpack("<H", font_data[4:6])[0]
                fg_r, fg_g, fg_b = font_data[6], font_data[7], font_data[8]
                bg_r, bg_g, bg_b = font_data[9], font_data[10], font_data[11]
                height = struct.unpack("<l", font_data[12:16])[0]
                mostly_zero = font_data[16:28]
                weight = struct.unpack("<h", font_data[28:30])[0]
                unknown10 = font_data[30]
                unknown11 = font_data[31]
                italic = font_data[32]
                underline = font_data[33]
                strike_out = font_data[34]
                double_underline = font_data[35]
                small_caps = font_data[36]
                unknown17 = font_data[37]
                unknown18 = font_data[38]
                pitch_and_family = font_data[39]
                unknown20 = font_data[40]
                charset = font_data[41]
                unknown22 = font_data[42]
                unknown23 = font_data[43]
                unknown24 = font_data[44]
                up = struct.unpack("b", font_data[45:46])[0]

                nf = MVBFont(
                    font_name=font_name,
                    expndtw=expndtw,
                    style=style,
                    fg_rgb=(fg_r, fg_g, fg_b),
                    bg_rgb=(bg_r, bg_g, bg_b),
                    height=height,
                    mostly_zero=mostly_zero,
                    weight=weight,
                    unknown10=unknown10,
                    unknown11=unknown11,
                    italic=italic,
                    underline=underline,
                    strike_out=strike_out,
                    double_underline=double_underline,
                    small_caps=small_caps,
                    unknown17=unknown17,
                    unknown18=unknown18,
                    pitch_and_family=pitch_and_family,
                    unknown20=unknown20,
                    charset=charset,
                    unknown22=unknown22,
                    unknown23=unknown23,
                    unknown24=unknown24,
                    up=up,
                    raw_data={
                        "raw": font_data,
                        "parsed": {
                            "font_name": font_name,
                            "expndtw": expndtw,
                            "style": style,
                            "fg_rgb": (fg_r, fg_g, fg_b),
                            "bg_rgb": (bg_r, bg_g, bg_b),
                            "height": height,
                            "mostly_zero": mostly_zero,
                            "weight": weight,
                            "unknown10": unknown10,
                            "unknown11": unknown11,
                            "italic": italic,
                            "underline": underline,
                            "strike_out": strike_out,
                            "double_underline": double_underline,
                            "small_caps": small_caps,
                            "unknown17": unknown17,
                            "unknown18": unknown18,
                            "pitch_and_family": pitch_and_family,
                            "unknown20": unknown20,
                            "charset": charset,
                            "unknown22": unknown22,
                            "unknown23": unknown23,
                            "unknown24": unknown24,
                            "up": up,
                        },
                    },
                )

                parsed_style = {
                    "wStyleNum": wStyleNum,
                    "wBasedOn": wBasedOn,
                    "nf": nf,
                    "bReserved": bReserved,
                    "bStyleName": bStyleName,
                }
                self.styles.append(MVBStyle(**parsed_style, raw_data={"raw": raw_bytes, "parsed": parsed_style}))
                offset += 152
            elif self.system_file and self.system_file.header.minor > 16:
                # NewStyle
                raw_bytes = self.raw_data[offset : offset + 146]
                if len(raw_bytes) < 146:
                    break

                wStyleNum, wBasedOn = struct.unpack_from("<HH", raw_bytes)
                font_data = raw_bytes[4:46]  # NewFont is 42 bytes, plus 4 bytes for wStyleNum and wBasedOn
                bReserved = raw_bytes[46:81]
                bStyleName = raw_bytes[81:146]

                # Parse the embedded font data
                (
                    unknown1,
                    font_name,
                    fg_r,
                    fg_g,
                    fg_b,
                    bg_r,
                    bg_g,
                    bg_b,
                    unknown5,
                    unknown6,
                    unknown7,
                    unknown8,
                    unknown9,
                    height,
                    mostly_zero,
                    weight,
                    unknown10,
                    unknown11,
                    italic,
                    underline,
                    strike_out,
                    double_underline,
                    small_caps,
                    unknown17,
                    unknown18,
                    pitch_and_family,
                ) = struct.unpack("<BhBBBBBBBBBi12shBBBBBBBBB", font_data)

                nf = NewFont(
                    unknown1=unknown1,
                    font_name=font_name,
                    fg_rgb=(fg_r, fg_g, fg_b),
                    bg_rgb=(bg_r, bg_g, bg_b),
                    unknown5=unknown5,
                    unknown6=unknown6,
                    unknown7=unknown7,
                    unknown8=unknown8,
                    unknown9=unknown9,
                    height=height,
                    mostly_zero=mostly_zero,
                    weight=weight,
                    unknown10=unknown10,
                    unknown11=unknown11,
                    italic=italic,
                    underline=underline,
                    strike_out=strike_out,
                    double_underline=double_underline,
                    small_caps=small_caps,
                    unknown17=unknown17,
                    unknown18=unknown18,
                    pitch_and_family=pitch_and_family,
                    raw_data={
                        "raw": font_data,
                        "parsed": {
                            "unknown1": unknown1,
                            "font_name": font_name,
                            "fg_rgb": (fg_r, fg_g, fg_b),
                            "bg_rgb": (bg_r, bg_g, bg_b),
                            "unknown5": unknown5,
                            "unknown6": unknown6,
                            "unknown7": unknown7,
                            "unknown8": unknown8,
                            "unknown9": unknown9,
                            "height": height,
                            "mostly_zero": mostly_zero,
                            "weight": weight,
                            "unknown10": unknown10,
                            "unknown11": unknown11,
                            "italic": italic,
                            "underline": underline,
                            "strike_out": strike_out,
                            "double_underline": double_underline,
                            "small_caps": small_caps,
                            "unknown17": unknown17,
                            "unknown18": unknown18,
                            "pitch_and_family": pitch_and_family,
                        },
                    },
                )

                parsed_style = {
                    "wStyleNum": wStyleNum,
                    "wBasedOn": wBasedOn,
                    "nf": nf,
                    "bReserved": bReserved,
                    "bStyleName": bStyleName,
                }
                self.styles.append(NewStyle(**parsed_style, raw_data={"raw": raw_bytes, "parsed": parsed_style}))
                offset += 146

    def _parse_charmaps(self):
        """
        Parses the character map names.
        """

        if self.header.num_charmaps == 0:
            return

        offset = self.header.charmaps_offset
        for i in range(self.header.num_charmaps):
            end_of_string = self.raw_data.find(b"\x00", offset)

            if end_of_string == -1:
                break
            self.charmaps.append(self.raw_data[offset:end_of_string].decode("ascii", errors="ignore"))
            offset = end_of_string + 1
        # Parse .tbl files referenced in charmaps
        # Based on helpdeco.c FontLoad function
        for charmap in self.charmaps:
            if not charmap or charmap == "|MVCHARTAB,0":
                continue

            # Extract the charmap name (before the comma)
            charmap_name = charmap.split(",")[0] if "," in charmap else charmap

            # Try to find this charmap as an internal file in the help file
            if self.parent_hlp and self.parent_hlp.directory is not None:
                charmap_data = self._get_internal_file_data(charmap_name)
                if charmap_data:
                    self._parse_charmap_file(charmap_name, charmap_data)

    def _get_internal_file_data(self, filename: str) -> Optional[bytes]:
        """
        Get the raw data for an internal file from the help file directory.
        """
        if not self.parent_hlp or self.parent_hlp.directory is None:
            return None

        # Search for the filename in the directory
        for entry in self.parent_hlp.directory.entries:
            if entry.filename == filename:
                # Calculate file offset and read the data
                file_offset = entry.file_offset
                if file_offset < len(self.parent_hlp.raw_data):
                    # Read FILEHEADER to get the actual size
                    header_data = self.parent_hlp.raw_data[file_offset : file_offset + 9]
                    if len(header_data) >= 9:
                        reserved_space, used_space, file_flags = struct.unpack("<LLB", header_data)
                        file_data_start = file_offset + 9
                        file_data_end = file_data_start + used_space
                        if file_data_end <= len(self.parent_hlp.raw_data):
                            return self.parent_hlp.raw_data[file_data_start:file_data_end]
        return None

    def _parse_charmap_file(self, filename: str, data: bytes):
        """
        Parse a character mapping .tbl file according to CHARMAPHEADER structure.
        Based on helpdeco.c FontLoad function.
        """
        if len(data) < 40:  # CHARMAPHEADER size (7 + 13 uint16s)
            return

        # Parse CHARMAPHEADER
        offset = 0
        magic, size, unknown1, unknown2, entries, ligatures, lig_len = struct.unpack_from("<HHHHHHH", data, offset)
        offset += 14

        unknown_fields = []
        for i in range(13):
            unknown_fields.append(struct.unpack_from("<H", data, offset)[0])
            offset += 2

        charmap_header = CharMapHeader(
            magic=magic,
            size=size,
            unknown1=unknown1,
            unknown2=unknown2,
            entries=entries,
            ligatures=ligatures,
            lig_len=lig_len,
            unknown=unknown_fields,
            raw_data={
                "raw": data[:offset],
                "parsed": {
                    "magic": magic,
                    "size": size,
                    "unknown1": unknown1,
                    "unknown2": unknown2,
                    "entries": entries,
                    "ligatures": ligatures,
                    "lig_len": lig_len,
                    "unknown": unknown_fields,
                },
            },
        )

        # Parse character mapping entries
        charmap_entries = []
        for i in range(entries):
            if offset + 10 > len(data):  # Each entry is 10 bytes (6 bytes + 2 padding)
                break

            char_class, order, normal, clipboard, mac, mac_clipboard = struct.unpack_from("<HHBBBB", data, offset)
            offset += 6
            unused = struct.unpack_from("<H", data, offset)[0]  # padding/unused
            offset += 2

            entry_raw_data = data[offset - 10 : offset]
            entry = CharMapEntry(
                char_class=char_class,
                order=order,
                normal=normal,
                clipboard=clipboard,
                mac=mac,
                mac_clipboard=mac_clipboard,
                unused=unused,
                raw_data={
                    "raw": entry_raw_data,
                    "parsed": {
                        "char_class": char_class,
                        "order": order,
                        "normal": normal,
                        "clipboard": clipboard,
                        "mac": mac,
                        "mac_clipboard": mac_clipboard,
                        "unused": unused,
                    },
                },
            )
            charmap_entries.append(entry)

        # Store the parsed charmap data
        self.parsed_charmaps[filename] = {"header": charmap_header, "entries": charmap_entries}
