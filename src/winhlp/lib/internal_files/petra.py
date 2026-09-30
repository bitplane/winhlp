"""
|Petra file parser for Windows HLP files.

The |Petra file maps topic offsets to original RTF source filenames.
It's created when using HCRTF /a option and follows a B+ tree structure
similar to |CONTEXT files.

Based on the helpdeco C reference implementation and documentation.
"""

import struct
from typing import Dict, List, Optional
from pydantic import BaseModel, Field

from .base import InternalFile
from ..btree import BTree


class PetraEntry(BaseModel):
    """A single entry in the Petra mapping table."""

    topic_offset: int
    rtf_filename: str
    raw_data: dict


class PetraFile(InternalFile):
    """
    Parses the |Petra internal file which maps topic offsets to RTF source filenames.

    The |Petra file is created when help files are compiled with HCRTF /a option.
    It contains a B+ tree structure that maps TopicOffset -> RTFSourceFileName.

    Structure:
    - Uses B+ tree for efficient lookup
    - Each leaf node contains topic offset to filename mappings
    - Similar structure to |CONTEXT but with different data payload
    """

    help_file: Optional[object] = Field(default=None, exclude=True)
    entries: Dict[int, str] = {}  # topic_offset -> rtf_filename
    btree: Optional[BTree] = None
    petra_entries: List[PetraEntry] = []

    def __init__(self, data: bytes, help_file=None, **kwargs):
        super().__init__(raw_data=data, filename="|Petra", **kwargs)
        self.help_file = help_file
        self.entries = {}
        self.btree = None
        self.petra_entries = []
        self._parse()

    def _parse(self):
        """Parse the |Petra B+ tree and its NUL-terminated leaf entries."""
        if len(self.raw_data) < 38:
            return
        try:
            self.btree = BTree(self.raw_data)
            for page, n_entries in self.btree.iterate_leaf_pages():
                self._parse_leaf_page(page, n_entries)
        except Exception:
            # A malformed optional index should not abort the whole help file.
            self.entries.clear()
            self.petra_entries.clear()

    def _parse_leaf_page(self, page_data: bytes, n_entries: int):
        offset = 8  # BTREENODEHEADER
        for _ in range(n_entries):
            if offset + 4 > len(page_data):
                break
            start = offset
            topic_offset = struct.unpack_from("<L", page_data, offset)[0]
            offset += 4
            end = page_data.find(b"\x00", offset)
            if end < 0:
                break
            rtf_filename = page_data[offset:end].decode("cp1252", errors="replace")
            offset = end + 1
            self.entries[topic_offset] = rtf_filename
            self.petra_entries.append(
                PetraEntry(
                    topic_offset=topic_offset, rtf_filename=rtf_filename, raw_data={"raw": page_data[start:offset]}
                )
            )

    def get_rtf_filename(self, topic_offset: int) -> Optional[str]:
        """Get the RTF source filename for a given topic offset."""
        return self.entries.get(topic_offset)

    def get_all_mappings(self) -> Dict[int, str]:
        """Get all topic offset to RTF filename mappings."""
        return self.entries.copy()

    def get_statistics(self) -> dict:
        """Get statistics about the Petra file."""
        return {
            "total_mappings": len(self.entries),
            "has_btree": self.btree is not None,
            "raw_data_size": len(self.raw_data),
            "unique_filenames": len(set(self.entries.values())),
            "topic_offset_range": {
                "min": min(self.entries.keys()) if self.entries else None,
                "max": max(self.entries.keys()) if self.entries else None,
            },
        }
