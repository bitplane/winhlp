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
    fg_rgb: bytes = Field(..., max_length=3)
    bg_rgb: bytes = Field(..., max_length=3)
    unknown5_9: bytes = Field(..., max_length=5)
    height: int
    mostly_zero: bytes = Field(..., max_length=12)
    weight: int
    remaining_bytes: bytes = Field(..., max_length=7)
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
            num_formats,
            formats_offset,
            num_charmaps,
            charmaps_offset,
        ) = struct.unpack("<HHHHHHHH", raw_bytes)

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
        """
        offset = self.header.facenames_offset
        for _ in range(self.header.num_facenames):
            facename = b""
            while self.raw_data[offset] != 0x00:
                facename += self.raw_data[offset : offset + 1]
                offset += 1
            self.facenames.append(facename.decode("ascii", errors="ignore"))
            offset += 1

    def _parse_descriptors(self):
        """
        Parses the font descriptors.
        """
        offset = self.header.descriptors_offset
        for _ in range(self.header.num_descriptors):
            if self.system_file and self.system_file.header.minor > 16:
                # NewFont
                raw_bytes = self.raw_data[offset : offset + 39]
                if len(raw_bytes) < 39:
                    break
                (
                    unknown1,
                    font_name,
                    fg_rgb,
                    bg_rgb,
                    unknown5_9,
                    height,
                    mostly_zero,
                    weight,
                    remaining_bytes,
                ) = struct.unpack("<Bh3s3s5si12sh7s", raw_bytes)

                parsed_descriptor = {
                    "unknown1": unknown1,
                    "font_name": font_name,
                    "fg_rgb": fg_rgb,
                    "bg_rgb": bg_rgb,
                    "unknown5_9": unknown5_9,
                    "height": height,
                    "mostly_zero": mostly_zero,
                    "weight": weight,
                    "remaining_bytes": remaining_bytes,
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
        for _ in range(self.header.num_formats):
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
                    mostly_zero_1,
                    mostly_zero_2,
                    mostly_zero_3,
                    mostly_zero_4,
                    mostly_zero_5,
                    mostly_zero_6,
                    mostly_zero_7,
                    mostly_zero_8,
                    mostly_zero_9,
                    mostly_zero_10,
                    mostly_zero_11,
                    mostly_zero_12,
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
                ) = struct.unpack("<BhBBBBBBBBBiBBBBBBBBBBBBhBBBBBBBBB", font_data)

                nf = NewFont(
                    unknown1=unknown1,
                    font_name=font_name,
                    fg_r=fg_r,
                    fg_g=fg_g,
                    fg_b=fg_b,
                    bg_r=bg_r,
                    bg_g=bg_g,
                    bg_b=bg_b,
                    unknown5=unknown5,
                    unknown6=unknown6,
                    unknown7=unknown7,
                    unknown8=unknown8,
                    unknown9=unknown9,
                    height=height,
                    mostly_zero_1=mostly_zero_1,
                    mostly_zero_2=mostly_zero_2,
                    mostly_zero_3=mostly_zero_3,
                    mostly_zero_4=mostly_zero_4,
                    mostly_zero_5=mostly_zero_5,
                    mostly_zero_6=mostly_zero_6,
                    mostly_zero_7=mostly_zero_7,
                    mostly_zero_8=mostly_zero_8,
                    mostly_zero_9=mostly_zero_9,
                    mostly_zero_10=mostly_zero_10,
                    mostly_zero_11=mostly_zero_11,
                    mostly_zero_12=mostly_zero_12,
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
                            "fg_r": fg_r,
                            "fg_g": fg_g,
                            "fg_b": fg_b,
                            "bg_r": bg_r,
                            "bg_g": bg_g,
                            "bg_b": bg_b,
                            "unknown5": unknown5,
                            "unknown6": unknown6,
                            "unknown7": unknown7,
                            "unknown8": unknown8,
                            "unknown9": unknown9,
                            "height": height,
                            "mostly_zero_1": mostly_zero_1,
                            "mostly_zero_2": mostly_zero_2,
                            "mostly_zero_3": mostly_zero_3,
                            "mostly_zero_4": mostly_zero_4,
                            "mostly_zero_5": mostly_zero_5,
                            "mostly_zero_6": mostly_zero_6,
                            "mostly_zero_7": mostly_zero_7,
                            "mostly_zero_8": mostly_zero_8,
                            "mostly_zero_9": mostly_zero_9,
                            "mostly_zero_10": mostly_zero_10,
                            "mostly_zero_11": mostly_zero_11,
                            "mostly_zero_12": mostly_zero_12,
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
            else:
                # MVBStyle (or other older style, not implemented yet)
                # For now, we'll just skip these.
                break

    def _parse_charmaps(self):
        """
        Parses the character map names.
        """
        if self.header.num_charmaps == 0:
            return

        offset = self.header.charmaps_offset
        for _ in range(self.header.num_charmaps):
            end_of_string = self.raw_data.find(b"\x00", offset)
            if end_of_string == -1:
                break
            self.charmaps.append(self.raw_data[offset:end_of_string].decode("ascii", errors="ignore"))
            offset += 1
