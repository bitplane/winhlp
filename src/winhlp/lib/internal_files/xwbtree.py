"""Parser for the |xWBTREE internal file."""

from .base import InternalFile
from ..btree import BTree
from pydantic import BaseModel
from typing import Optional, Dict, List, Union
import struct


class XWBTreeIndexEntry(BaseModel):
    """
    Structure for |xWBTREE index-page entries.
    From helpfile.md: xWBTREEINDEXENTRY
    """

    keyword: str
    page_number: int
    raw_data: dict


class XWBTreeLeafEntry(BaseModel):
    """
    Structure for |xWBTREE leaf-page entries.
    From helpfile.md: xWBTREELEAFENTRY
    """

    keyword: str
    count: int
    kw_data_offset: int
    raw_data: dict


class XWBTreeGIDLeafEntry(BaseModel):
    """
    Structure for |xWBTREE leaf-page entries in Win95 GID files.
    From helpfile.md: Different structure for GID files
    """

    keyword: str
    size: int
    records: List[Dict[str, int]]  # List of {'file_number': int, 'topic_offset': int}
    raw_data: dict


class XWBTreeFile(InternalFile):
    """
    Parses the |xWBTREE file, which contains keyword search index.

    From helpfile.md:
    To locate a keyword assigned using a x-footnote (x may be A-Z, a-z), use the
    |xWDATA, |xWBTREE and |xWMAP internal files. |xWBTREE tells you how often a
    certain Keyword is defined in the help file.

    Structure of |xWBTREE index page entries:
    struct {
        STRINGZ Keyword
        short PageNumber
    } xWBTREEINDEXENTRY[NEntries]

    Structure of |xWBTREE leaf page entries:
    struct {
        STRINGZ Keyword
        short Count             number of times keyword is referenced
        long KWDataOffset       this is the offset into |xWDATA
    } xWBTREELEAFENTRY[NEntries]

    For Win95 GID files, the structure is different:
    struct {
        STRINGZ Keyword
        long Size               size of following record
        struct {
            long FileNumber     ?
            long TopicOffset    this is the offset into |xWDATA
        } record[Size/8]
    } xWBTREELEAFENTRY[NEntries]
    """

    btree: Optional[BTree] = None
    keyword_map: Dict[str, Union[XWBTreeLeafEntry, XWBTreeGIDLeafEntry]] = {}
    entries: List[Union[XWBTreeLeafEntry, XWBTreeGIDLeafEntry]] = []
    is_gid_format: bool = False

    def __init__(self, **data):
        super().__init__(**data)
        self.keyword_map = {}
        self.entries = []
        self.is_gid_format = False
        self._parse()

    def _parse(self):
        """
        Parses the |xWBTREE file data using the B+ tree structure.
        """
        if len(self.raw_data) < 9:  # Need at least file header
            return

        # Skip the file header (parsed by Directory class)
        btree_data = self.raw_data
        try:
            self.btree = BTree(data=btree_data)

            # Determine format by checking structure field
            if self.btree and self.btree.header:
                structure = self.btree.header.structure.decode("ascii", errors="ignore")
                # GID format has '!' in structure field for count/8 * record format
                self.is_gid_format = "!" in structure

            self._parse_xwbtree_entries()
        except Exception:
            # Some files may not have valid xWBTREE structures
            # This is not critical for basic HLP parsing
            pass

    def _parse_xwbtree_entries(self):
        """
        Parses xWBTREE entries from the B+ tree leaf pages.
        """
        if not self.btree:
            return

        for page, n_entries in self.btree.iterate_leaf_pages():
            offset = 8  # Skip page header

            for _ in range(n_entries):
                if offset >= len(page):
                    break

                # Read null-terminated keyword string
                keyword_start = offset
                keyword_end = page.find(b"\x00", offset)

                if keyword_end == -1:
                    # No null terminator found, read to end of page
                    keyword_end = len(page)

                keyword_bytes = page[keyword_start:keyword_end]
                keyword = self._decode_string(keyword_bytes)

                # Move past the null terminator
                offset = keyword_end + (1 if keyword_end < len(page) else 0)

                if self.is_gid_format:
                    entry = self._parse_gid_entry(page, offset, keyword, keyword_start)
                    if entry:
                        offset = entry["next_offset"]
                        self.entries.append(entry["entry"])
                        self.keyword_map[keyword] = entry["entry"]
                else:
                    entry = self._parse_standard_entry(page, offset, keyword, keyword_start)
                    if entry:
                        offset = entry["next_offset"]
                        self.entries.append(entry["entry"])
                        self.keyword_map[keyword] = entry["entry"]

    def _parse_standard_entry(self, page: bytes, offset: int, keyword: str, keyword_start: int) -> Optional[dict]:
        """Parse standard |xWBTREE leaf entry."""
        if offset + 6 > len(page):
            return None

        # Read count (2 bytes) and KWDataOffset (4 bytes)
        count = struct.unpack_from("<h", page, offset)[0]
        offset += 2

        kw_data_offset = struct.unpack_from("<l", page, offset)[0]
        offset += 4

        parsed_entry = {
            "keyword": keyword,
            "count": count,
            "kw_data_offset": kw_data_offset,
        }

        entry = XWBTreeLeafEntry(**parsed_entry, raw_data={"raw": page[keyword_start:offset], "parsed": parsed_entry})

        return {"entry": entry, "next_offset": offset}

    def _parse_gid_entry(self, page: bytes, offset: int, keyword: str, keyword_start: int) -> Optional[dict]:
        """Parse GID format |xWBTREE leaf entry."""
        if offset + 4 > len(page):
            return None

        # Read size (4 bytes)
        size = struct.unpack_from("<l", page, offset)[0]
        offset += 4

        # Read records (size/8 records, each 8 bytes)
        records = []
        records_count = size // 8

        for _ in range(records_count):
            if offset + 8 > len(page):
                break

            file_number = struct.unpack_from("<l", page, offset)[0]
            offset += 4

            topic_offset = struct.unpack_from("<l", page, offset)[0]
            offset += 4

            records.append({"file_number": file_number, "topic_offset": topic_offset})

        parsed_entry = {
            "keyword": keyword,
            "size": size,
            "records": records,
        }

        entry = XWBTreeGIDLeafEntry(
            **parsed_entry, raw_data={"raw": page[keyword_start:offset], "parsed": parsed_entry}
        )

        return {"entry": entry, "next_offset": offset}

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

    def get_keyword_info(self, keyword: str) -> Optional[Union[XWBTreeLeafEntry, XWBTreeGIDLeafEntry]]:
        """
        Gets keyword information by keyword string.

        Args:
            keyword: The keyword to look up

        Returns:
            Keyword entry, or None if not found
        """
        return self.keyword_map.get(keyword)

    def get_all_keywords(self) -> List[str]:
        """
        Returns a list of all keywords in the file.

        Returns:
            List of keyword strings
        """
        return list(self.keyword_map.keys())

    def get_keyword_count(self) -> int:
        """
        Returns the total number of keywords.

        Returns:
            Number of keywords
        """
        return len(self.keyword_map)

    def find_keywords_by_pattern(self, pattern: str) -> List[str]:
        """
        Find keywords matching a pattern (case insensitive).

        Args:
            pattern: String pattern to search for

        Returns:
            List of matching keyword strings
        """
        pattern_lower = pattern.lower()
        matches = []

        for keyword in self.keyword_map.keys():
            if pattern_lower in keyword.lower():
                matches.append(keyword)

        return sorted(matches)

    def get_keywords_sorted(self) -> List[str]:
        """
        Get all keywords sorted alphabetically.

        Returns:
            List of keyword strings sorted alphabetically
        """
        return sorted(self.keyword_map.keys())

    def get_topic_offsets_for_keyword(self, keyword: str) -> List[int]:
        """
        Get topic offsets for a keyword (requires |xWDATA for standard format).
        For GID format, returns topic offsets directly.

        Args:
            keyword: The keyword to look up

        Returns:
            List of topic offsets, empty if not found or requires |xWDATA
        """
        entry = self.keyword_map.get(keyword)
        if not entry:
            return []

        if isinstance(entry, XWBTreeGIDLeafEntry):
            # GID format has topic offsets directly
            return [record["topic_offset"] for record in entry.records]
        else:
            # Standard format requires |xWDATA lookup
            # Return empty list - caller needs to use |xWDATA with kw_data_offset
            return []

    def get_statistics(self) -> dict:
        """
        Returns statistics about the xWBTREE data.

        Returns:
            Dictionary with xWBTREE statistics
        """
        if not self.btree:
            return {
                "total_keywords": 0,
                "unique_keywords": 0,
                "btree_pages": 0,
                "has_btree": False,
                "is_gid_format": False,
            }

        # Calculate keyword statistics
        total_references = 0
        if self.is_gid_format:
            for entry in self.entries:
                if isinstance(entry, XWBTreeGIDLeafEntry):
                    total_references += len(entry.records)
        else:
            for entry in self.entries:
                if isinstance(entry, XWBTreeLeafEntry):
                    total_references += entry.count

        keyword_lengths = [len(kw) for kw in self.keyword_map.keys()]
        avg_keyword_length = sum(keyword_lengths) / len(keyword_lengths) if keyword_lengths else 0
        max_keyword_length = max(keyword_lengths) if keyword_lengths else 0
        min_keyword_length = min(keyword_lengths) if keyword_lengths else 0

        return {
            "total_keywords": len(self.entries),
            "unique_keywords": len(self.keyword_map),
            "total_references": total_references,
            "btree_pages": len(self.btree.get_all_pages()) if self.btree else 0,
            "has_btree": True,
            "is_gid_format": self.is_gid_format,
            "average_keyword_length": avg_keyword_length,
            "max_keyword_length": max_keyword_length,
            "min_keyword_length": min_keyword_length,
            "longest_keyword": max(self.keyword_map.keys(), key=len) if self.keyword_map else "",
            "shortest_keyword": min(self.keyword_map.keys(), key=len) if self.keyword_map else "",
        }
