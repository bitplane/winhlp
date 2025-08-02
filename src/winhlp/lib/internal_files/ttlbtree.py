"""Parser for the |TTLBTREE internal file."""

from .base import InternalFile
from ..btree import BTree
from pydantic import BaseModel
from typing import Optional, Dict, List
import struct


class TTLBTreeIndexEntry(BaseModel):
    """
    Structure for |TTLBTREE index-page entries.
    From helpfile.md: TTLBTREEINDEXENTRY
    """

    topic_offset: int
    page_number: int
    raw_data: dict


class TTLBTreeLeafEntry(BaseModel):
    """
    Structure for |TTLBTREE leaf-page entries.
    From helpfile.md: TTLBTREELEAFENTRY
    """

    topic_offset: int
    topic_title: str
    raw_data: dict


class TTLBTreeFile(InternalFile):
    """
    Parses the |TTLBTREE file, which contains topic title mappings.

    From helpfile.md:
    If you want to know the topic title assigned using the $-footnote, take a look
    into the |TTLBTREE internal file, which contains topic titles ordered by topic
    offsets in a B+ tree. (It is used by WinHelp to display the topic titles in
    the search dialog).

    Structure of |TTLBTREE index page entries:
    struct {
        TOPICOFFSET TopicOffset
        short PageNumber
    } TTLBTREEINDEXENTRY[NEntries]

    Structure of |TTLBTREE leaf page entries:
    struct {
        TOPICOFFSET TopicOffset
        STRINGZ TopicTitle
    } TTLBTREELEAFENTRY[NEntries]
    """

    btree: Optional[BTree] = None
    topic_title_map: Dict[int, str] = {}  # topic_offset -> topic_title
    title_topic_map: Dict[str, int] = {}  # topic_title -> topic_offset
    entries: List[TTLBTreeLeafEntry] = []

    def __init__(self, **data):
        super().__init__(**data)
        self.topic_title_map = {}
        self.title_topic_map = {}
        self.entries = []
        self._parse()

    def _parse(self):
        """
        Parses the |TTLBTREE file data using the B+ tree structure.
        """
        if len(self.raw_data) < 9:  # Need at least file header
            return

        # Skip the file header (parsed by Directory class)
        btree_data = self.raw_data
        try:
            self.btree = BTree(data=btree_data)
            self._parse_ttlbtree_entries()
        except Exception:
            # Some files may not have valid TTLBTREE structures
            # This is not critical for basic HLP parsing
            pass

    def _parse_ttlbtree_entries(self):
        """
        Parses TTLBTREE entries from the B+ tree leaf pages.
        """
        if not self.btree:
            return

        for page, n_entries in self.btree.iterate_leaf_pages():
            offset = 8  # Skip page header

            for _ in range(n_entries):
                if offset + 4 > len(page):
                    break

                # Read topic offset (4 bytes)
                topic_offset = struct.unpack_from("<l", page, offset)[0]
                offset += 4

                # Read null-terminated topic title string
                title_start = offset
                title_end = page.find(b"\x00", offset)

                if title_end == -1:
                    # No null terminator found, read to end of page
                    title_end = len(page)

                title_bytes = page[title_start:title_end]
                topic_title = self._decode_string(title_bytes)

                # Move past the null terminator (if found)
                offset = title_end + (1 if title_end < len(page) else 0)

                parsed_entry = {
                    "topic_offset": topic_offset,
                    "topic_title": topic_title,
                }

                # Create structured entry
                entry = TTLBTreeLeafEntry(
                    **parsed_entry, raw_data={"raw": page[title_start - 4 : offset], "parsed": parsed_entry}
                )
                self.entries.append(entry)

                # Store in our maps for quick lookup
                self.topic_title_map[topic_offset] = topic_title
                self.title_topic_map[topic_title] = topic_offset

    def _decode_string(self, data: bytes) -> str:
        """
        Decode string data using appropriate encoding.
        Falls back through multiple encodings to handle international text.
        """
        if not data:
            return ""

        # Try common Windows encodings
        encodings = ["cp1252", "cp1251", "utf-8", "latin-1"]

        for encoding in encodings:
            try:
                return data.decode(encoding)
            except UnicodeDecodeError:
                continue

        # Final fallback: decode with errors='replace' to avoid crashes
        return data.decode("cp1252", errors="replace")

    def get_topic_title_for_offset(self, topic_offset: int) -> Optional[str]:
        """
        Gets the topic title for a given topic offset.

        Args:
            topic_offset: The topic offset to look up

        Returns:
            Topic title string, or None if not found
        """
        return self.topic_title_map.get(topic_offset)

    def get_topic_offset_for_title(self, topic_title: str) -> Optional[int]:
        """
        Gets the topic offset for a given topic title.

        Args:
            topic_title: The topic title to look up

        Returns:
            Topic offset, or None if not found
        """
        return self.title_topic_map.get(topic_title)

    def get_all_topic_titles(self) -> List[str]:
        """
        Returns a list of all topic titles in the file.

        Returns:
            List of topic title strings
        """
        return list(self.title_topic_map.keys())

    def get_all_topic_offsets(self) -> List[int]:
        """
        Returns a list of all topic offsets in the file.

        Returns:
            List of topic offsets
        """
        return list(self.topic_title_map.keys())

    def get_entry_count(self) -> int:
        """
        Returns the total number of TTLBTREE entries.

        Returns:
            Number of entries
        """
        return len(self.entries)

    def find_titles_by_pattern(self, pattern: str) -> List[tuple]:
        """
        Find topic titles matching a pattern (case insensitive).

        Args:
            pattern: String pattern to search for

        Returns:
            List of (topic_title, topic_offset) tuples matching the pattern
        """
        pattern_lower = pattern.lower()
        matches = []

        for topic_title, topic_offset in self.title_topic_map.items():
            if pattern_lower in topic_title.lower():
                matches.append((topic_title, topic_offset))

        return sorted(matches)

    def get_titles_sorted_by_offset(self) -> List[tuple]:
        """
        Get all titles sorted by topic offset.

        Returns:
            List of (topic_offset, topic_title) tuples sorted by offset
        """
        return sorted(self.topic_title_map.items())

    def get_titles_sorted_alphabetically(self) -> List[tuple]:
        """
        Get all titles sorted alphabetically.

        Returns:
            List of (topic_title, topic_offset) tuples sorted by title
        """
        return sorted(self.title_topic_map.items())

    def get_statistics(self) -> dict:
        """
        Returns statistics about the TTLBTREE data.

        Returns:
            Dictionary with TTLBTREE statistics
        """
        if not self.btree:
            return {"total_entries": 0, "unique_topics": 0, "unique_titles": 0, "btree_pages": 0, "has_btree": False}

        # Calculate title length statistics
        title_lengths = [len(title) for title in self.title_topic_map.keys()]
        avg_title_length = sum(title_lengths) / len(title_lengths) if title_lengths else 0
        max_title_length = max(title_lengths) if title_lengths else 0
        min_title_length = min(title_lengths) if title_lengths else 0

        return {
            "total_entries": len(self.entries),
            "unique_topics": len(self.topic_title_map),
            "unique_titles": len(self.title_topic_map),
            "btree_pages": len(self.btree.get_all_pages()) if self.btree else 0,
            "has_btree": True,
            "average_title_length": avg_title_length,
            "max_title_length": max_title_length,
            "min_title_length": min_title_length,
            "longest_title": max(self.title_topic_map.keys(), key=len) if self.title_topic_map else "",
            "shortest_title": min(self.title_topic_map.keys(), key=len) if self.title_topic_map else "",
        }
