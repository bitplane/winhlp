"""Parser for the |Phrases internal file."""

from .base import InternalFile
from typing import List, Optional, Any
from ..compression import decompress
import struct


class PhraseFile(InternalFile):
    """
    Parses the |Phrases file, which contains phrase compression tables.

    Based on helldeco.c PhraseLoad function:
    - Read PhraseCount as WORD
    - Check for special VC4.0 format (PhraseCount == 0x0800)
    - Read magic number (must be 0x0100)
    - Read phrase offsets as WORDs
    - Decompress phrase data using LZ77 (WinHelp 3.1+) or uncompressed (WinHelp 3.0)
    """

    phrase_count: int = 0
    phrases: List[str] = []
    is_new_format: bool = False  # VC4.0 MSDEV format
    system_file: Any = None

    def __init__(self, system_file: Any = None, **data):
        super().__init__(**data)
        self.system_file = system_file
        self.phrases = []  # Initialize as instance variable
        self._parse()

    def _parse(self):
        """
        Parses the |Phrases file data following helldeco.c logic exactly.
        """
        if len(self.raw_data) < 6:  # Need at least count + magic
            return

        offset = 0

        # Read PhraseCount as WORD
        self.phrase_count = struct.unpack_from("<H", self.raw_data, offset)[0]
        offset += 2

        # Check for special VC4.0 format: MSDEV\HELP\MSDEV40.MVB
        self.is_new_format = self.phrase_count == 0x0800
        if self.is_new_format:
            # Read real PhraseCount
            if offset + 2 > len(self.raw_data):
                return
            self.phrase_count = struct.unpack_from("<H", self.raw_data, offset)[0]
            offset += 2

        # Validate magic number (must be 0x0100)
        if offset + 2 > len(self.raw_data):
            return
        magic = struct.unpack_from("<H", self.raw_data, offset)[0]
        offset += 2

        if magic != 0x0100:
            # Unknown |Phrases file structure - abort parsing
            return

        if self.phrase_count == 0:
            return

        # Determine version from system file
        before31 = True
        if self.system_file and self.system_file.header is not None:
            before31 = self.system_file.header.minor < 16

        # Calculate phrase data parameters
        if before31:
            # Windows 3.0: uncompressed
            phrase_offsets_size = (self.phrase_count + 1) * 2  # WORDs
            phrase_data_start = offset + phrase_offsets_size
            phrase_data_length = len(self.raw_data) - phrase_data_start
            _decompressed_size = phrase_data_length
        else:
            # Windows 3.1+: LZ77 compressed
            # Read decompressed size as DWORD
            if offset + 4 > len(self.raw_data):
                return
            _decompressed_size = struct.unpack_from("<L", self.raw_data, offset)[0]
            offset += 4

            phrase_offsets_size = (self.phrase_count + 1) * 2  # WORDs
            phrase_data_start = offset + phrase_offsets_size
            phrase_data_length = len(self.raw_data) - phrase_data_start

        # Read phrase offsets
        phrase_offsets = []
        base_offset = phrase_offsets_size + (0 if before31 else 4)  # Adjust for decompressed_size field

        for i in range(self.phrase_count + 1):
            if offset + 2 > len(self.raw_data):
                break
            phrase_offset = struct.unpack_from("<H", self.raw_data, offset)[0]
            phrase_offsets.append(phrase_offset - base_offset)  # Adjust relative to phrase data start
            offset += 2

        if len(phrase_offsets) < self.phrase_count + 1:
            return

        # Read and process phrase data
        phrase_data_raw = self.raw_data[phrase_data_start:]

        if before31:
            # No decompression needed
            phrase_data = phrase_data_raw
        else:
            # LZ77 decompression (method 2)
            phrase_data = decompress(method=2, data=phrase_data_raw)

        # Extract individual phrases
        for i in range(self.phrase_count):
            start_offset = phrase_offsets[i]
            end_offset = phrase_offsets[i + 1]

            if start_offset >= 0 and end_offset <= len(phrase_data) and start_offset < end_offset:
                phrase_bytes = phrase_data[start_offset:end_offset]
                # Decode using appropriate encoding from system file
                phrase = self._decode_text(phrase_bytes)
                self.phrases.append(phrase)
            else:
                self.phrases.append("")  # Invalid phrase

    def _decode_text(self, data: bytes) -> str:
        """
        Decode text data using the appropriate encoding from the system file.
        Falls back through multiple encodings to handle international text.
        """
        if not data:
            return ""

        # Get encoding from system file if available
        encoding = "cp1252"  # Default Windows Western European
        if self.system_file and self.system_file.encoding is not None:
            encoding = self.system_file.encoding

        # Try the determined encoding first
        try:
            return data.decode(encoding)
        except UnicodeDecodeError:
            pass

        # Fall back through common Windows encodings
        fallback_encodings = ["cp1252", "cp1251", "cp850", "iso-8859-1"]

        for fallback_encoding in fallback_encodings:
            if fallback_encoding != encoding:  # Don't retry the same encoding
                try:
                    return data.decode(fallback_encoding)
                except UnicodeDecodeError:
                    continue

        # Final fallback: decode with errors='replace' to avoid crashes
        return data.decode("cp1252", errors="replace")

    def get_phrase(self, phrase_number: int) -> Optional[str]:
        """
        Gets a phrase by its number.
        """
        if 0 <= phrase_number < len(self.phrases):
            return self.phrases[phrase_number]
        return None
