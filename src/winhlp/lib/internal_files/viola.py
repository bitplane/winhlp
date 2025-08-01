"""Parser for the |VIOLA internal file."""

from .base import InternalFile
from pydantic import BaseModel
from typing import List
from ..btree import BTree
import struct


class ViolaEntry(BaseModel):
    """
    Single entry in the |VIOLA file.
    From `helpdeco.h`: VIOLAREC
    """

    topic_offset: int  # TOPICOFFSET
    window_number: int  # Window number assigned to topic
    raw_data: dict


class ViolaFile(InternalFile):
    """
    Parses the |VIOLA file, which contains window assignments for topics.

    The VIOLA file is structured as a B+ tree where leaf pages contain
    VIOLAREC entries that map topic offsets to window numbers.

    From helpdeco.c:
    - Uses GetFirstPage/GetNextPage to iterate through B+ tree leaf pages
    - Each leaf page contains n VIOLAREC entries
    - Each VIOLAREC is 8 bytes: TopicOffset (4) + WindowNumber (4)
    """

    btree: BTree = None
    entries: List[ViolaEntry] = []

    def __init__(self, **data):
        super().__init__(**data)
        self.entries = []  # Initialize as instance variable
        self._parse()

    def _parse(self):
        """Parses the |VIOLA file data."""
        if len(self.raw_data) < 40:  # Need at least space for BTree header
            return

        # Parse as B+ tree
        self.btree = BTree(data=self.raw_data)
        self._parse_entries()

    def _parse_entries(self):
        """Parses VIOLAREC entries from B+ tree leaf pages."""
        if not self.btree:
            return

        # Iterate through leaf pages using the BTree
        for page, n_entries in self.btree.iterate_leaf_pages():
            offset = 8  # Skip page header (BTREENODEHEADER)

            for _ in range(n_entries):
                if offset + 8 > len(page):
                    break

                # Parse VIOLAREC structure
                raw_bytes = page[offset : offset + 8]
                topic_offset, window_number = struct.unpack_from("<LL", page, offset)
                offset += 8

                parsed_entry = {
                    "topic_offset": topic_offset,
                    "window_number": window_number,
                }

                entry = ViolaEntry(**parsed_entry, raw_data={"raw": raw_bytes, "parsed": parsed_entry})

                self.entries.append(entry)
