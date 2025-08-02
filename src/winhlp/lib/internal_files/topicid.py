"""Parser for the |TopicId internal file."""

from .base import InternalFile
from ..btree import BTree
from pydantic import BaseModel
from typing import Optional, Dict, List
import struct


class TopicIdIndexEntry(BaseModel):
    """
    Structure for |TopicId index-page entries.
    From helpfile.md: TopicIdINDEXENTRY
    """

    topic_offset: int
    page_number: int
    raw_data: dict


class TopicIdLeafEntry(BaseModel):
    """
    Structure for |TopicId leaf-page entries.
    From helpfile.md: TopicIdLEAFENTRY
    """

    topic_offset: int
    context_name: str
    raw_data: dict


class TopicIdFile(InternalFile):
    """
    Parses the |TopicId file, which contains context name mappings.

    From helpfile.md:
    The |TopicId internal file lists the ContextName assigned to a specific topic
    offset if the help file was created using the /a option of HCRTF and is built
    using a B+ tree.

    Structure of |TopicId index-page entries:
    struct {
        TOPICOFFSET TopicOffset
        short PageNumber
    } TopicIdINDEXENTRY[NEntries]

    Structure of |TopicId leaf-page entries:
    struct {
        TOPICOFFSET TopicOffset
        STRINGZ ContextName
    } TopicIdLEAFENTRY[NEntries]
    """

    btree: Optional[BTree] = None
    topic_context_map: Dict[int, str] = {}  # topic_offset -> context_name
    context_topic_map: Dict[str, int] = {}  # context_name -> topic_offset
    entries: List[TopicIdLeafEntry] = []

    def __init__(self, **data):
        super().__init__(**data)
        self.topic_context_map = {}
        self.context_topic_map = {}
        self.entries = []
        self._parse()

    def _parse(self):
        """
        Parses the |TopicId file data using the B+ tree structure.
        """
        if len(self.raw_data) < 9:  # Need at least file header
            return

        # Skip the file header (parsed by Directory class)
        btree_data = self.raw_data
        try:
            self.btree = BTree(data=btree_data)
            self._parse_topicid_entries()
        except Exception:
            # Some files may not have valid TopicId structures
            # This is not critical for basic HLP parsing
            pass

    def _parse_topicid_entries(self):
        """
        Parses TopicId entries from the B+ tree leaf pages.
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

                # Read null-terminated context name string
                context_name_start = offset
                context_name_end = page.find(b"\x00", offset)

                if context_name_end == -1:
                    # No null terminator found, read to end of page
                    context_name_end = len(page)

                context_name_bytes = page[context_name_start:context_name_end]
                context_name = self._decode_string(context_name_bytes)

                # Move past the null terminator (if found)
                offset = context_name_end + (1 if context_name_end < len(page) else 0)

                parsed_entry = {
                    "topic_offset": topic_offset,
                    "context_name": context_name,
                }

                # Create structured entry
                entry = TopicIdLeafEntry(
                    **parsed_entry, raw_data={"raw": page[context_name_start - 4 : offset], "parsed": parsed_entry}
                )
                self.entries.append(entry)

                # Store in our maps for quick lookup
                self.topic_context_map[topic_offset] = context_name
                self.context_topic_map[context_name] = topic_offset

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

    def get_context_name_for_topic(self, topic_offset: int) -> Optional[str]:
        """
        Gets the context name for a given topic offset.

        Args:
            topic_offset: The topic offset to look up

        Returns:
            Context name string, or None if not found
        """
        return self.topic_context_map.get(topic_offset)

    def get_topic_offset_for_context(self, context_name: str) -> Optional[int]:
        """
        Gets the topic offset for a given context name.

        Args:
            context_name: The context name to look up

        Returns:
            Topic offset, or None if not found
        """
        return self.context_topic_map.get(context_name)

    def get_all_context_names(self) -> List[str]:
        """
        Returns a list of all context names in the file.

        Returns:
            List of context name strings
        """
        return list(self.context_topic_map.keys())

    def get_all_topic_offsets(self) -> List[int]:
        """
        Returns a list of all topic offsets in the file.

        Returns:
            List of topic offsets
        """
        return list(self.topic_context_map.keys())

    def get_entry_count(self) -> int:
        """
        Returns the total number of TopicId entries.

        Returns:
            Number of entries
        """
        return len(self.entries)

    def find_contexts_by_pattern(self, pattern: str) -> List[tuple]:
        """
        Find context names matching a pattern (case insensitive).

        Args:
            pattern: String pattern to search for

        Returns:
            List of (context_name, topic_offset) tuples matching the pattern
        """
        pattern_lower = pattern.lower()
        matches = []

        for context_name, topic_offset in self.context_topic_map.items():
            if pattern_lower in context_name.lower():
                matches.append((context_name, topic_offset))

        return sorted(matches)

    def get_statistics(self) -> dict:
        """
        Returns statistics about the TopicId data.

        Returns:
            Dictionary with TopicId statistics
        """
        if not self.btree:
            return {"total_entries": 0, "unique_topics": 0, "unique_contexts": 0, "btree_pages": 0, "has_btree": False}

        return {
            "total_entries": len(self.entries),
            "unique_topics": len(self.topic_context_map),
            "unique_contexts": len(self.context_topic_map),
            "btree_pages": len(self.btree.get_all_pages()) if self.btree else 0,
            "has_btree": True,
            "average_context_length": sum(len(name) for name in self.context_topic_map.keys())
            / len(self.context_topic_map)
            if self.context_topic_map
            else 0,
        }
