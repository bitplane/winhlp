"""Parser for the |GMACROS internal file."""

from .base import InternalFile
from pydantic import BaseModel
from typing import List
import struct


class GMacroEntry(BaseModel):
    """
    Single macro entry in the |GMACROS file.
    From helpdeco.c GMACROS parsing logic.
    """

    length: int  # Length of the record
    offset: int  # Offset of second string (exit macro)
    entry_macro: str  # Entry macro string
    exit_macro: str  # Exit macro string
    raw_data: dict


class GMacrosFile(InternalFile):
    """
    Parses the |GMACROS file, which contains global macros.

    Global macros are executed when entering or exiting help contexts.

    From helldeco.c parsing logic:
    - First 4 bytes: count or group number
    - Followed by records, each containing:
      - len (4 bytes): length of record
      - off (4 bytes): offset of second string in record
      - First string at position 8: entry macro
      - Second string at position off: exit macro
    """

    count: int = 0
    entries: List[GMacroEntry] = []

    def __init__(self, **data):
        super().__init__(**data)
        self.entries = []  # Initialize as instance variable
        self._parse()

    def _parse(self):
        """Parses the |GMACROS file data."""
        if len(self.raw_data) < 4:
            return

        offset = 0

        # Read count/group number
        self.count = struct.unpack_from("<l", self.raw_data, offset)[0]
        offset += 4

        # Parse records
        while offset < len(self.raw_data):
            if offset + 8 > len(self.raw_data):
                break

            record_start = offset

            # Read record header
            length = struct.unpack_from("<l", self.raw_data, offset)[0]
            offset += 4

            string_offset = struct.unpack_from("<l", self.raw_data, offset)[0]
            offset += 4

            if length < 8:
                break

            # Validate string_offset
            if string_offset <= 0:
                string_offset = length

            if length < string_offset:
                break

            # Read entry macro (first string at position 8, length = string_offset - 8)
            entry_macro = ""
            if string_offset > 8:
                entry_len = string_offset - 8
                if record_start + 8 + entry_len <= len(self.raw_data):
                    entry_bytes = self.raw_data[record_start + 8 : record_start + 8 + entry_len]
                    # Find null terminator
                    null_pos = entry_bytes.find(b"\x00")
                    if null_pos != -1:
                        entry_bytes = entry_bytes[:null_pos]
                    entry_macro = self._decode_text(entry_bytes)

            # Read exit macro (second string at string_offset, length = length - string_offset)
            exit_macro = ""
            if length > string_offset:
                exit_len = length - string_offset
                if record_start + string_offset + exit_len <= len(self.raw_data):
                    exit_bytes = self.raw_data[record_start + string_offset : record_start + string_offset + exit_len]
                    # Find null terminator
                    null_pos = exit_bytes.find(b"\x00")
                    if null_pos != -1:
                        exit_bytes = exit_bytes[:null_pos]
                    exit_macro = self._decode_text(exit_bytes)

            # Create entry
            parsed_entry = {
                "length": length,
                "offset": string_offset,
                "entry_macro": entry_macro,
                "exit_macro": exit_macro,
            }

            entry = GMacroEntry(
                **parsed_entry,
                raw_data={"raw": self.raw_data[record_start : record_start + length], "parsed": parsed_entry},
            )
            self.entries.append(entry)

            # Advance by full record length (C code: pos += len)
            offset = record_start + length

    def _decode_text(self, data: bytes) -> str:
        """
        Decode text data using appropriate encoding.
        Falls back through multiple encodings to handle international text.
        """
        if not data:
            return ""

        # Try common Windows encodings
        fallback_encodings = ["cp1252", "cp1251", "cp850", "iso-8859-1"]

        for encoding in fallback_encodings:
            try:
                return data.decode(encoding)
            except UnicodeDecodeError:
                continue

        # Final fallback: decode with errors='replace' to avoid crashes
        return data.decode("cp1252", errors="replace")
