"""
CHARTAB parser for Windows HLP files.

CHARTAB files (*.tbl) contain character mapping tables for fonts.
They are created by MediaView compilers and stored as internal files
using a specific binary structure.

Based on the helpdeco C reference implementation and documentation.
"""

import struct
from typing import List, Optional, Dict
from pydantic import BaseModel

from .base import InternalFile


class ChartabHeader(BaseModel):
    """Header structure for CHARTAB files."""

    magic: int  # Should be 0x5555
    size: int
    unknown1: int
    unknown2: int
    entries: int
    ligatures: int
    lig_len: int
    unknown_fields: List[int]  # Unknown fields array
    raw_data: dict


class ChartabCharEntry(BaseModel):
    """A character entry in the CHARTAB table."""

    char_class: int
    order: int
    normal: int
    clipboard: int
    mac: int
    mac_clipboard: int
    unused: int
    raw_data: dict


class ChartabLigature(BaseModel):
    """A ligature entry in the CHARTAB table."""

    ligature_data: bytes
    raw_data: dict


class ChartabFile(InternalFile):
    """
    Parses CHARTAB (Character Mapping Table) files.

    From documentation:
    MediaView compilers store character mapping tables listed in the [CHARTAB]
    section in internal *.tbl files using the following binary structure:

    struct {
        unsigned short Magic /* 0x5555 */
        unsigned short Size
        unsigned short Unknown1[2]
        unsigned short Entries
        unsigned short Ligatures
        unsigned short LigLen
        unsigned short Unknown[13]
    } CHARTAB
    charentry[Entries]
    unsigned char Ligature[Ligatures][LigLen]
    """

    def __init__(self, data: bytes, help_file=None):
        super().__init__(data, help_file)
        self.header: Optional[ChartabHeader] = None
        self.char_entries: List[ChartabCharEntry] = []
        self.ligatures: List[ChartabLigature] = []
        self.character_mapping: Dict[int, dict] = {}  # Maps character codes to mapping info
        self._parse()

    def _parse(self):
        """Parse the CHARTAB file structure."""
        if len(self.data) < 40:  # Minimum size for header (20 shorts = 40 bytes)
            return

        try:
            self._parse_header()
            if self.header and self.header.magic == 0x5555:
                self._parse_char_entries()
                self._parse_ligatures()
                self._build_character_mappings()

        except Exception:
            # If parsing fails, create minimal structure
            pass

    def _parse_header(self):
        """Parse the CHARTAB header structure."""
        if len(self.data) < 40:
            return

        try:
            # Read header fields (20 unsigned shorts = 40 bytes)
            header_data = struct.unpack("<20H", self.data[:40])

            magic = header_data[0]
            size = header_data[1]
            unknown1 = header_data[2]
            unknown2 = header_data[3]
            entries = header_data[4]
            ligatures = header_data[5]
            lig_len = header_data[6]
            unknown_fields = list(header_data[7:20])  # 13 unknown fields

            self.header = ChartabHeader(
                magic=magic,
                size=size,
                unknown1=unknown1,
                unknown2=unknown2,
                entries=entries,
                ligatures=ligatures,
                lig_len=lig_len,
                unknown_fields=unknown_fields,
                raw_data={
                    "magic": f"0x{magic:04X}",
                    "size": size,
                    "entries": entries,
                    "ligatures": ligatures,
                    "lig_len": lig_len,
                    "is_valid_magic": magic == 0x5555,
                },
            )

        except struct.error:
            # Create minimal header on error
            self.header = ChartabHeader(
                magic=0,
                size=0,
                unknown1=0,
                unknown2=0,
                entries=0,
                ligatures=0,
                lig_len=0,
                unknown_fields=[],
                raw_data={"error": "Failed to parse header"},
            )

    def _parse_char_entries(self):
        """Parse character entries from the CHARTAB file."""
        if not self.header or self.header.entries == 0:
            return

        offset = 40  # After header
        entry_size = 14  # Size of charentry structure (7 shorts = 14 bytes)

        for i in range(self.header.entries):
            if offset + entry_size > len(self.data):
                break

            try:
                # Read charentry structure
                entry_data = struct.unpack("<7H", self.data[offset : offset + entry_size])

                char_class = entry_data[0]
                order = entry_data[1]
                normal = entry_data[2]
                clipboard = entry_data[3]
                mac = entry_data[4]
                mac_clipboard = entry_data[5]
                unused = entry_data[6]

                char_entry = ChartabCharEntry(
                    char_class=char_class,
                    order=order,
                    normal=normal,
                    clipboard=clipboard,
                    mac=mac,
                    mac_clipboard=mac_clipboard,
                    unused=unused,
                    raw_data={
                        "char_class": char_class,
                        "order": order,
                        "normal": normal,
                        "clipboard": clipboard,
                        "mac": mac,
                        "mac_clipboard": mac_clipboard,
                        "unused": unused,
                    },
                )

                self.char_entries.append(char_entry)
                offset += entry_size

            except struct.error:
                # Skip malformed entry
                offset += entry_size
                continue

    def _parse_ligatures(self):
        """Parse ligature data from the CHARTAB file."""
        if not self.header or self.header.ligatures == 0 or self.header.lig_len == 0:
            return

        # Calculate offset: header + char_entries
        offset = 40 + (self.header.entries * 14)

        for i in range(self.header.ligatures):
            if offset + self.header.lig_len > len(self.data):
                break

            try:
                ligature_data = self.data[offset : offset + self.header.lig_len]

                ligature = ChartabLigature(
                    ligature_data=ligature_data,
                    raw_data={"length": self.header.lig_len, "index": i, "data": ligature_data.hex()},
                )

                self.ligatures.append(ligature)
                offset += self.header.lig_len

            except Exception:
                # Skip malformed ligature
                offset += self.header.lig_len
                continue

    def _build_character_mappings(self):
        """Build character code to mapping mappings."""
        for i, entry in enumerate(self.char_entries):
            # Use the character class as the key
            self.character_mapping[entry.char_class] = {
                "entry_index": i,
                "order": entry.order,
                "normal": entry.normal,
                "clipboard": entry.clipboard,
                "mac": entry.mac,
                "mac_clipboard": entry.mac_clipboard,
                "unused": entry.unused,
            }

    def get_character_mapping(self, char_code: int) -> Optional[dict]:
        """Get character mapping information for a given character code."""
        return self.character_mapping.get(char_code)

    def get_all_mappings(self) -> Dict[int, dict]:
        """Get all character mappings."""
        return self.character_mapping.copy()

    def has_ligatures(self) -> bool:
        """Check if the CHARTAB file contains ligature data."""
        return len(self.ligatures) > 0

    def get_statistics(self) -> dict:
        """Get statistics about the CHARTAB file."""
        return {
            "is_valid": self.header and self.header.magic == 0x5555,
            "magic_number": f"0x{self.header.magic:04X}" if self.header else "None",
            "character_entries": len(self.char_entries),
            "ligature_count": len(self.ligatures),
            "ligature_length": self.header.lig_len if self.header else 0,
            "total_characters_mapped": len(self.character_mapping),
            "raw_data_size": len(self.data),
        }
