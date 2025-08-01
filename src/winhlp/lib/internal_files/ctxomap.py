"""Parser for the |CTXOMAP internal file."""

from .base import InternalFile
from pydantic import BaseModel
from typing import List
import struct


class CtxoMapEntry(BaseModel):
    """
    Single entry in the |CTXOMAP file.
    From `helpdeco.h`: CTXOMAPREC
    """

    map_id: int
    topic_offset: int
    raw_data: dict


class CtxoMapFile(InternalFile):
    """
    Parses the |CTXOMAP file, which contains a simple array of
    MapID -> TopicOffset mappings for Windows 3.0 help files.

    From `helpdec1.c` CTXOMAPDump function:
    - First 2 bytes: number of entries (uint16)
    - Followed by entries, each 8 bytes:
      - MapID (int32)
      - TopicOffset (int32)
    """

    entries: List[CtxoMapEntry] = []

    def __init__(self, **data):
        super().__init__(**data)
        self.entries = []  # Initialize as instance variable
        self._parse()

    def _parse(self):
        """Parses the |CTXOMAP file data."""
        if len(self.raw_data) < 2:
            return

        offset = 0

        # Read number of entries (16-bit word)
        num_entries = struct.unpack_from("<H", self.raw_data, offset)[0]
        offset += 2

        # Read each CTXOMAPREC entry
        for _ in range(num_entries):
            if offset + 8 > len(self.raw_data):
                break

            raw_bytes = self.raw_data[offset : offset + 8]
            map_id, topic_offset = struct.unpack_from("<ll", self.raw_data, offset)
            offset += 8

            parsed_entry = {
                "map_id": map_id,
                "topic_offset": topic_offset,
            }

            entry = CtxoMapEntry(**parsed_entry, raw_data={"raw": raw_bytes, "parsed": parsed_entry})

            self.entries.append(entry)
