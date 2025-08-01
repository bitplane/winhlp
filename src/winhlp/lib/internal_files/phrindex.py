"""Parser for the |PhrIndex internal file."""

from .base import InternalFile
from pydantic import BaseModel
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

    def __init__(self, **data):
        super().__init__(**data)
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

        # Note: The actual phrase index data follows the header, but parsing
        # that would require implementing the full phrase compression system
        # which is quite complex. For now, we just parse the header.
