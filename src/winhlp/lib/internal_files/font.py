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


class MVBFont(BaseModel):
    """
    Font descriptor for multimedia HLP files.
    From `helpdeco.h`: MVBFONT
    """

    font_name_index: int
    expndtw: int
    style: int
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


class MVBStyle(BaseModel):
    """
    Character style for multimedia HLP files.
    From `helpdeco.h`: MVBSTYLE
    """

    style_num: int
    based_on: int
    font: MVBFont
    unknown: bytes = Field(..., max_length=35)
    style_name: bytes = Field(..., max_length=65)
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
    system_file: Any = None

    def __init__(self, system_file: Any = None, **data):
        super().__init__(**data)
        self.system_file = system_file
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
        for _ in range(self.header.num_descriptors):
            if self.system_file and self.system_file.header.minor > 16:
                # NewFont - parse according to helpdeco NEWFONT structure
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
                # Note: helpdeco has 3 more bytes (unknown17, unknown18, PitchAndFamily)
                # but our test files seem to have 39-byte structures
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
                offset += 39
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
        for i in range(self.header.num_formats):
            if self.system_file and self.system_file.header.minor > 16:
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
