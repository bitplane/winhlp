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
        """Parse the |Petra file structure."""
        if len(self.raw_data) < 4:
            return

        try:
            # Initialize B+ tree for Petra file
            self.btree = BTree(self.raw_data)

            # Parse all leaf nodes to extract topic offset -> filename mappings
            self._parse_leaf_nodes()

        except Exception:
            # If B+ tree parsing fails, try to parse as simple list
            self._parse_as_simple_list()

    def _parse_leaf_nodes(self):
        """Parse B+ tree leaf nodes to extract Petra entries."""
        if not self.btree:
            return

        try:
            # Get all leaf pages from the B+ tree
            leaf_pages = self.btree.get_leaf_pages()

            for page_data in leaf_pages:
                self._parse_leaf_page(page_data)

        except Exception:
            # Fall back to simple parsing if B+ tree traversal fails
            self._parse_as_simple_list()

    def _parse_leaf_page(self, page_data: bytes):
        """Parse a single leaf page containing Petra entries."""
        offset = 0

        while offset + 8 < len(page_data):  # Need at least 8 bytes for topic offset + length
            try:
                # Read topic offset (4 bytes)
                topic_offset = struct.unpack_from("<L", page_data, offset)[0]
                offset += 4

                # Read filename length (2 bytes) - assuming short length prefix
                if offset + 2 > len(page_data):
                    break

                filename_length = struct.unpack_from("<H", page_data, offset)[0]
                offset += 2

                # Read filename string
                if offset + filename_length > len(page_data):
                    break

                rtf_filename = page_data[offset : offset + filename_length].decode("cp1252", errors="replace")
                # Remove null terminator if present
                if rtf_filename.endswith("\x00"):
                    rtf_filename = rtf_filename[:-1]

                offset += filename_length

                # Store the mapping
                self.entries[topic_offset] = rtf_filename

                # Create structured entry
                petra_entry = PetraEntry(
                    topic_offset=topic_offset,
                    rtf_filename=rtf_filename,
                    raw_data={
                        "topic_offset": topic_offset,
                        "filename_length": filename_length,
                        "rtf_filename": rtf_filename,
                    },
                )
                self.petra_entries.append(petra_entry)

            except (struct.error, UnicodeDecodeError, IndexError):
                # Skip malformed entry
                offset += 1
                continue

    def _parse_as_simple_list(self):
        """Fallback parsing method for non-B+ tree Petra files."""
        offset = 0

        while offset + 8 < len(self.raw_data):
            try:
                # Try to find topic offset pattern (4 bytes)
                topic_offset = struct.unpack_from("<L", self.raw_data, offset)[0]

                # Skip obviously invalid offsets
                if topic_offset == 0 or topic_offset > 0x10000000:
                    offset += 1
                    continue

                offset += 4

                # Look for null-terminated string after offset
                filename_start = offset
                while offset < len(self.raw_data) and self.raw_data[offset] != 0x00:
                    offset += 1

                if offset > filename_start and offset < len(self.raw_data):
                    rtf_filename = self.raw_data[filename_start:offset].decode("cp1252", errors="replace")
                    offset += 1  # Skip null terminator

                    # Only add if filename looks reasonable
                    if rtf_filename and len(rtf_filename) < 256:
                        self.entries[topic_offset] = rtf_filename

                        petra_entry = PetraEntry(
                            topic_offset=topic_offset,
                            rtf_filename=rtf_filename,
                            raw_data={
                                "topic_offset": topic_offset,
                                "rtf_filename": rtf_filename,
                                "parsing_method": "simple_list",
                            },
                        )
                        self.petra_entries.append(petra_entry)
                else:
                    offset = filename_start + 1

            except (struct.error, UnicodeDecodeError, IndexError):
                offset += 1
                continue

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
