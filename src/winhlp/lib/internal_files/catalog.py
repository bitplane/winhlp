"""Parser for the |CATALOG internal file."""

from .base import InternalFile
from pydantic import BaseModel
from typing import List
import struct


class CatalogHeader(BaseModel):
    """
    Header for the |CATALOG file.
    From `helpdeco.h`: CATALOGHEADER
    """

    magic: int  # Should be 0x1111
    always8: int  # Should always be 8
    always4: int  # Should always be 4
    entries: int  # Number of topic entries
    zero: bytes  # 30 zero bytes padding
    raw_data: dict


class CatalogFile(InternalFile):
    """
    Parses the |CATALOG file, which contains sequential topic mapping.

    The CATALOG file maps topic numbers (1, 2, 3...) to topic offsets.
    This provides a simple sequential access mechanism for topics.

    From `helpdec1.c` CatalogDump function:
    - CATALOGHEADER (40 bytes): magic, always8, always4, entries, zero[30]
    - Followed by entries number of 32-bit topic offsets
    """

    header: CatalogHeader = None
    topic_offsets: List[int] = []

    def __init__(self, **data):
        super().__init__(**data)
        self.topic_offsets = []  # Initialize as instance variable
        self._parse()

    def _parse(self):
        """Parses the |CATALOG file data."""
        if len(self.raw_data) < 40:  # CATALOGHEADER is 40 bytes
            return

        self._parse_header()
        self._parse_topic_offsets()

    def _parse_header(self):
        """Parses the CATALOGHEADER structure."""
        offset = 0
        start_offset = offset

        # Parse header fields
        magic = struct.unpack_from("<H", self.raw_data, offset)[0]
        offset += 2

        always8 = struct.unpack_from("<H", self.raw_data, offset)[0]
        offset += 2

        always4 = struct.unpack_from("<H", self.raw_data, offset)[0]
        offset += 2

        entries = struct.unpack_from("<l", self.raw_data, offset)[0]
        offset += 4

        zero = self.raw_data[offset : offset + 30]
        offset += 30

        parsed_header = {
            "magic": magic,
            "always8": always8,
            "always4": always4,
            "entries": entries,
            "zero": zero,
        }

        self.header = CatalogHeader(
            **parsed_header, raw_data={"raw": self.raw_data[start_offset:offset], "parsed": parsed_header}
        )

    def _parse_topic_offsets(self):
        """Parses the array of topic offsets."""
        if not self.header:
            return

        offset = 40  # Start after CATALOGHEADER

        for _ in range(self.header.entries):
            if offset + 4 > len(self.raw_data):
                break

            topic_offset = struct.unpack_from("<L", self.raw_data, offset)[0]
            offset += 4

            self.topic_offsets.append(topic_offset)
