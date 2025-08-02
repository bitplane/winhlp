"""Parser for the |PhrIndex internal file."""

from .base import InternalFile
from pydantic import BaseModel
from typing import Any
import struct


class PhrIndexHeader(BaseModel):
    """
    Header for the |PhrIndex file.
    From `helpdeco.h`: PHRINDEXHDR
    """

    always_4a01: int  # Sometimes 0x0001, usually 0x4A01
    entries: int  # Number of phrases
    compressed_size: int  # Size of PhrIndex file
    phr_image_size: int  # Size of decompressed PhrImage file
    phr_image_compressed_size: int  # Size of PhrImage file
    always_0: int  # Should be 0
    bits: int  # 4-bit field
    unknown: int  # 12-bit field
    always_4a00: int  # Sometimes 0x4A01, 0x4A02, usually 0x4A00
    raw_data: dict


class PhrIndexFile(InternalFile):
    """
    Parses the |PhrIndex file, which contains phrase compression index.

    The PhrIndex file is used for phrase compression in WinHelp 3.1+.
    It contains an index of phrases that can be referenced to save space
    in the actual help content.

    From `helpdeco.h` PHRINDEXHDR structure:
    - always4A01 (4 bytes): Magic number, sometimes 0x0001
    - entries (4 bytes): Number of phrases
    - compressedsize (4 bytes): Size of PhrIndex file
    - phrimagesize (4 bytes): Size of decompressed PhrImage file
    - phrimagecompressedsize (4 bytes): Size of PhrImage file
    - always0 (4 bytes): Should be 0
    - Combined 16-bit field with bits (4 bits) and unknown (12 bits)
    - always4A00 (2 bytes): Magic number, sometimes 0x4A01, 0x4A02
    """

    header: PhrIndexHeader = None
    phrases: list = []
    system_file: Any = None

    def __init__(self, system_file: Any = None, **data):
        super().__init__(**data)
        self.system_file = system_file
        self.phrases = []
        self._parse()

    def _parse(self):
        """Parses the |PhrIndex file data."""
        if len(self.raw_data) < 30:  # PHRINDEXHDR is 30 bytes
            return

        self._parse_header()

    def _parse_header(self):
        """Parses the PHRINDEXHDR structure."""
        offset = 0
        start_offset = offset

        # Parse header fields
        always_4a01 = struct.unpack_from("<l", self.raw_data, offset)[0]
        offset += 4

        entries = struct.unpack_from("<l", self.raw_data, offset)[0]
        offset += 4

        compressed_size = struct.unpack_from("<l", self.raw_data, offset)[0]
        offset += 4

        phr_image_size = struct.unpack_from("<l", self.raw_data, offset)[0]
        offset += 4

        phr_image_compressed_size = struct.unpack_from("<l", self.raw_data, offset)[0]
        offset += 4

        always_0 = struct.unpack_from("<l", self.raw_data, offset)[0]
        offset += 4

        # Combined 16-bit field with bits (4) and unknown (12)
        combined = struct.unpack_from("<H", self.raw_data, offset)[0]
        offset += 2
        bits = combined & 0x0F  # Lower 4 bits
        unknown = (combined >> 4) & 0x0FFF  # Upper 12 bits

        always_4a00 = struct.unpack_from("<H", self.raw_data, offset)[0]
        offset += 2

        parsed_header = {
            "always_4a01": always_4a01,
            "entries": entries,
            "compressed_size": compressed_size,
            "phr_image_size": phr_image_size,
            "phr_image_compressed_size": phr_image_compressed_size,
            "always_0": always_0,
            "bits": bits,
            "unknown": unknown,
            "always_4a00": always_4a00,
        }

        self.header = PhrIndexHeader(
            **parsed_header, raw_data={"raw": self.raw_data[start_offset:offset], "parsed": parsed_header}
        )

        # Parse phrase index data following helldeco.c implementation
        self._parse_phrase_data()

    def _parse_phrase_data(self):
        """Parse phrase data following helldeco.c PhraseLoad implementation"""
        if not self.header:
            return

        # Get PhrImage file data
        if self.system_file and self.system_file.parent_hlp is not None:
            hlp_file = self.system_file.parent_hlp
            if "|PhrImage" not in hlp_file.directory.files:
                return

            phrimage_offset = hlp_file.directory.files["|PhrImage"]
            # Read file header to get the size
            file_header_data = hlp_file.data[phrimage_offset : phrimage_offset + 9]
            if len(file_header_data) < 9:
                return
            reserved_space, used_space, file_flags = struct.unpack("<llB", file_header_data)

            phrimage_data = hlp_file.data[phrimage_offset + 9 : phrimage_offset + 9 + used_space]

            # Decompress if needed (following helldeco.c logic)
            if self.header.phr_image_size == self.header.phr_image_compressed_size:
                # No compression
                phrase_data = phrimage_data[: self.header.phr_image_size]
            else:
                # LZ77 compressed (method 2)
                from ..compression import decompress

                phrase_data = decompress(method=2, data=phrimage_data)[: self.header.phr_image_size]

            # For Hall compression, we need to parse phrase offsets from PhrIndex data
            # following the bit-stream algorithm in helldeco.c
            self._parse_hall_phrase_offsets(phrase_data)

    def _parse_hall_phrase_offsets(self, phrase_data: bytes):
        """Parse Hall compression phrase offsets using bit-stream algorithm from helldeco.c"""
        # Initialize GetBit state to match helldeco.c exactly
        self._init_getbit()
        self._current_dword_pos = 30  # Skip past header (30 bytes)

        # Calculate phrase offsets using exact algorithm from helldeco.c PhraseLoad()
        phrase_offsets = [0]  # PhraseOffsets[0] = offset; (offset starts at 0)
        offset = 0

        for entry_index in range(self.header.entries):
            # Exact algorithm from helldeco.c:
            # for (n = 1; GetBit(HelpFile); n += 1 << PhrIndexHdr.bits);
            n = 1
            while self._get_bit():
                n += 1 << self.header.bits

            # if (GetBit(HelpFile)) n += 1;
            if self._get_bit():
                n += 1

            # if (PhrIndexHdr.bits > 1) if (GetBit(HelpFile)) n += 2;
            if self.header.bits > 1 and self._get_bit():
                n += 2

            # if (PhrIndexHdr.bits > 2) if (GetBit(HelpFile)) n += 4;
            if self.header.bits > 2 and self._get_bit():
                n += 4

            # if (PhrIndexHdr.bits > 3) if (GetBit(HelpFile)) n += 8;
            if self.header.bits > 3 and self._get_bit():
                n += 8

            # if (PhrIndexHdr.bits > 4) if (GetBit(HelpFile)) n += 16;
            if self.header.bits > 4 and self._get_bit():
                n += 16

            # offset += n; PhraseOffsets[(int)l + 1] = offset;
            offset += n
            phrase_offsets.append(offset)

        # Extract phrases using calculated offsets
        for i in range(self.header.entries):
            start_offset = phrase_offsets[i]
            end_offset = phrase_offsets[i + 1]

            # Bounds check
            if start_offset >= len(phrase_data) or end_offset > len(phrase_data):
                # Add empty phrase for consistency
                self.phrases.append("")
                continue

            phrase_bytes = phrase_data[start_offset:end_offset]
            # Decode using latin-1 as per helldeco.c which treats bytes as chars
            phrase = phrase_bytes.decode("latin-1", errors="replace")
            self.phrases.append(phrase)

    def _init_getbit(self):
        """Initialize GetBit state, called with None parameter in C code"""
        self._mask = 0  # mask = 0L; /* initialize */
        self._value = 0

    def _get_dword(self) -> int:
        """Get 32-bit word from raw_data, equivalent to getdw(f) in C"""
        if self._current_dword_pos + 4 > len(self.raw_data):
            return 0

        # Read little-endian 32-bit word: getdw reads two 16-bit words
        word1 = struct.unpack_from("<H", self.raw_data, self._current_dword_pos)[0]
        word2 = struct.unpack_from("<H", self.raw_data, self._current_dword_pos + 2)[0]
        self._current_dword_pos += 4

        # Combine as: ((uint32_t)my_getw(f) << 16) | (uint32_t)w;
        return (word2 << 16) | word1

    def _get_bit(self) -> bool:
        """Get next bit from PhrIndex data (exact implementation of helldeco.c GetBit)"""
        # static uint32_t mask; static uint32_t value;
        # if (f) {
        self._mask <<= 1  # mask <<= 1;
        if not self._mask:  # if (!mask) {
            self._value = self._get_dword()  # value = getdw(f);
            self._mask = 1  # mask = 1L;
        # }
        # return (value & mask) != 0L;
        return (self._value & self._mask) != 0
