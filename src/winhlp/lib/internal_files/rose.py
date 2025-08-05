"""Parser for the |Rose internal file."""

from .base import InternalFile
from ..btree import BTree
from ..text_utils import decode_help_text
from pydantic import BaseModel
from typing import Optional, Dict, List
import struct


class RoseIndexEntry(BaseModel):
    """
    Structure for |Rose index-page entries.
    From helpfile.md: RoseINDEXENTRY
    """

    keyword_hash: int
    page_number: int
    raw_data: dict


class RoseLeafEntry(BaseModel):
    """
    Structure for |Rose leaf-page entries.
    From helpfile.md: RoseLEAFENTRY
    """

    keyword_hash: int
    macro: str
    topic_title: str  # Display string for search dialog
    raw_data: dict


class RoseFile(InternalFile):
    """
    Parses the |Rose file, which contains macro definitions from [MACROS] section.

    From helpfile.md:
    The |Rose internal file contains all definitions from the [MACROS] section of a
    Windows 95 (HCW 4.00) help project file. It is built using a B+ tree. Keywords
    only appear using hash values but are listed in the |KWBTREE with a TopicPos in
    the associated |KWDATA array of -1L.

    Structure of |Rose index page entries:
    struct {
        long KeywordHash
        short PageNumber
    } RoseINDEXENTRY[NEntries]

    Structure of |Rose leaf page entries:
    struct {
        long KeywordHash
        STRINGZ Macro
        STRINGZ TopicTitle      not a real topic title but the string
                               displayed in the search dialog where
                               normally topic titles are listed
    } RoseLEAFENTRY[NEntries]
    """

    btree: Optional[BTree] = None
    macro_map: Dict[int, RoseLeafEntry] = {}  # keyword_hash -> RoseLeafEntry
    entries: List[RoseLeafEntry] = []

    def __init__(self, **data):
        super().__init__(**data)
        self.macro_map = {}
        self.entries = []
        self._parse()

    def _parse(self):
        """
        Parses the |Rose file data using the B+ tree structure.
        """
        if len(self.raw_data) < 9:  # Need at least file header
            return

        # Skip the file header (parsed by Directory class)
        btree_data = self.raw_data
        try:
            self.btree = BTree(data=btree_data)
            self._parse_rose_entries()
        except Exception:
            # Some files may not have valid Rose structures
            # This is not critical for basic HLP parsing
            pass

    def _parse_rose_entries(self):
        """
        Parses Rose entries from the B+ tree leaf pages.
        """
        if not self.btree:
            return

        for page, n_entries in self.btree.iterate_leaf_pages():
            offset = 8  # Skip page header

            for _ in range(n_entries):
                if offset + 4 > len(page):
                    break

                # Read keyword hash (4 bytes)
                keyword_hash = struct.unpack_from("<l", page, offset)[0]
                offset += 4

                # Read null-terminated macro string
                macro_start = offset
                macro_end = page.find(b"\x00", offset)

                if macro_end == -1:
                    # No null terminator found, skip this entry
                    break

                macro_bytes = page[macro_start:macro_end]
                macro = decode_help_text(macro_bytes)

                # Move past the null terminator
                offset = macro_end + 1

                # Read null-terminated topic title string
                topic_title_start = offset
                topic_title_end = page.find(b"\x00", offset)

                if topic_title_end == -1:
                    # No null terminator found, read to end of page
                    topic_title_end = len(page)

                topic_title_bytes = page[topic_title_start:topic_title_end]
                topic_title = decode_help_text(topic_title_bytes)

                # Move past the null terminator (if found)
                offset = topic_title_end + (1 if topic_title_end < len(page) else 0)

                parsed_entry = {
                    "keyword_hash": keyword_hash,
                    "macro": macro,
                    "topic_title": topic_title,
                }

                # Create structured entry
                entry = RoseLeafEntry(
                    **parsed_entry, raw_data={"raw": page[macro_start - 4 : offset], "parsed": parsed_entry}
                )
                self.entries.append(entry)

                # Store in our map for quick lookup
                self.macro_map[keyword_hash] = entry

    def get_macro_by_hash(self, keyword_hash: int) -> Optional[RoseLeafEntry]:
        """
        Gets a macro entry by its keyword hash.

        Args:
            keyword_hash: The keyword hash to look up

        Returns:
            Rose entry, or None if not found
        """
        return self.macro_map.get(keyword_hash)

    def get_macro_string_by_hash(self, keyword_hash: int) -> Optional[str]:
        """
        Gets just the macro string by its keyword hash.

        Args:
            keyword_hash: The keyword hash to look up

        Returns:
            Macro string, or None if not found
        """
        entry = self.macro_map.get(keyword_hash)
        return entry.macro if entry else None

    def get_all_keyword_hashes(self) -> List[int]:
        """
        Returns a list of all keyword hashes in the file.

        Returns:
            List of keyword hash values
        """
        return list(self.macro_map.keys())

    def get_all_macros(self) -> List[str]:
        """
        Returns a list of all macro strings in the file.

        Returns:
            List of macro strings
        """
        return [entry.macro for entry in self.entries]

    def get_all_entries(self) -> List[RoseLeafEntry]:
        """
        Returns all Rose entries.

        Returns:
            List of all Rose entries
        """
        return self.entries.copy()

    def get_entry_count(self) -> int:
        """
        Returns the total number of Rose entries.

        Returns:
            Number of entries
        """
        return len(self.entries)

    def find_macros_by_pattern(self, pattern: str) -> List[RoseLeafEntry]:
        """
        Find macro entries where the macro string contains a pattern (case insensitive).

        Args:
            pattern: String pattern to search for

        Returns:
            List of Rose entries matching the pattern
        """
        pattern_lower = pattern.lower()
        matches = []

        for entry in self.entries:
            if pattern_lower in entry.macro.lower():
                matches.append(entry)

        return matches

    def find_by_topic_title_pattern(self, pattern: str) -> List[RoseLeafEntry]:
        """
        Find macro entries where the topic title contains a pattern (case insensitive).

        Args:
            pattern: String pattern to search for

        Returns:
            List of Rose entries matching the pattern
        """
        pattern_lower = pattern.lower()
        matches = []

        for entry in self.entries:
            if pattern_lower in entry.topic_title.lower():
                matches.append(entry)

        return matches

    def get_entries_sorted_by_hash(self) -> List[RoseLeafEntry]:
        """
        Get all entries sorted by keyword hash.

        Returns:
            List of entries sorted by keyword hash
        """
        return sorted(self.entries, key=lambda e: e.keyword_hash)

    def get_entries_sorted_by_macro(self) -> List[RoseLeafEntry]:
        """
        Get all entries sorted alphabetically by macro string.

        Returns:
            List of entries sorted by macro string
        """
        return sorted(self.entries, key=lambda e: e.macro.lower())

    def get_entries_sorted_by_topic_title(self) -> List[RoseLeafEntry]:
        """
        Get all entries sorted alphabetically by topic title.

        Returns:
            List of entries sorted by topic title
        """
        return sorted(self.entries, key=lambda e: e.topic_title.lower())

    def get_statistics(self) -> dict:
        """
        Returns statistics about the Rose data.

        Returns:
            Dictionary with Rose statistics
        """
        if not self.btree:
            return {"total_entries": 0, "unique_hashes": 0, "btree_pages": 0, "has_btree": False}

        # Calculate macro and title length statistics
        macro_lengths = [len(entry.macro) for entry in self.entries]
        title_lengths = [len(entry.topic_title) for entry in self.entries]

        avg_macro_length = sum(macro_lengths) / len(macro_lengths) if macro_lengths else 0
        max_macro_length = max(macro_lengths) if macro_lengths else 0
        min_macro_length = min(macro_lengths) if macro_lengths else 0

        avg_title_length = sum(title_lengths) / len(title_lengths) if title_lengths else 0
        max_title_length = max(title_lengths) if title_lengths else 0
        min_title_length = min(title_lengths) if title_lengths else 0

        return {
            "total_entries": len(self.entries),
            "unique_hashes": len(self.macro_map),
            "btree_pages": len(self.btree.get_all_pages()) if self.btree else 0,
            "has_btree": True,
            "average_macro_length": avg_macro_length,
            "max_macro_length": max_macro_length,
            "min_macro_length": min_macro_length,
            "longest_macro": max(self.entries, key=lambda e: len(e.macro)).macro if self.entries else "",
            "shortest_macro": min(self.entries, key=lambda e: len(e.macro)).macro if self.entries else "",
            "average_title_length": avg_title_length,
            "max_title_length": max_title_length,
            "min_title_length": min_title_length,
            "longest_title": max(self.entries, key=lambda e: len(e.topic_title)).topic_title if self.entries else "",
            "shortest_title": min(self.entries, key=lambda e: len(e.topic_title)).topic_title if self.entries else "",
        }
