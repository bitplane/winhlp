"""Parser for the |xWMAP internal file."""

from .base import InternalFile
from pydantic import BaseModel
from typing import List, Optional
import struct


class XWMapEntry(BaseModel):
    """
    Structure for |xWMAP entries.
    From helpfile.md and helldeco.h: KWMAPREC
    """

    keyword_number: int  # FirstRec - number of first keyword on leaf-page
    page_number: int  # PageNum - B+ tree page number
    raw_data: dict


class XWMapFile(InternalFile):
    """
    Parses the |xWMAP file, which contains keyword map for faster scrolling.

    From helpfile.md:
    The |xWMAP contains an array that tells you where to find the n-th keyword in
    the |xWBTREE. You don't need to use this file but it allows for faster
    scrolling lists of alphabetically ordered Keywords. (WinHelp search dialog).

    struct {
        long KeywordNumber        number of first keyword on leaf-page
        unsigned short PageNum    B+ tree page number
    } xWMAP[UsedSpace/6]

    From helldeco.h: KWMAPREC
    typedef struct KWMAPREC {
        int32_t FirstRec;         /* index number of first keyword on leaf page */
        uint16_t PageNum;         /* page number that keywords are associated with */
    } KWMAPREC;
    """

    entries: List[XWMapEntry] = []
    keyword_page_map: dict = {}  # keyword_number -> page_number

    def __init__(self, **data):
        super().__init__(**data)
        self.entries = []
        self.keyword_page_map = {}
        self._parse()

    def _parse(self):
        """
        Parses the |xWMAP file data.
        """
        if len(self.raw_data) < 9:  # Need at least file header
            return

        # Skip the file header (9 bytes: reserved_space + used_space + file_flags)
        data_start = 9
        xwmap_data = self.raw_data[data_start:]

        # From C code: n = my_getw(HelpFile); (reads number of entries)
        if len(xwmap_data) < 2:
            return

        # Read number of entries (2 bytes)
        n_entries = struct.unpack_from("<H", xwmap_data, 0)[0]
        offset = 2

        # Parse entries (6 bytes each: 4 bytes long + 2 bytes short)
        for i in range(n_entries):
            if offset + 6 > len(xwmap_data):
                break

            # Read KWMAPREC structure
            keyword_number = struct.unpack_from("<l", xwmap_data, offset)[0]  # FirstRec (4 bytes)
            offset += 4

            page_number = struct.unpack_from("<H", xwmap_data, offset)[0]  # PageNum (2 bytes)
            offset += 2

            parsed_entry = {
                "keyword_number": keyword_number,
                "page_number": page_number,
            }

            # Create structured entry
            entry = XWMapEntry(
                **parsed_entry, raw_data={"raw": xwmap_data[offset - 6 : offset], "parsed": parsed_entry}
            )
            self.entries.append(entry)

            # Store in map for quick lookup
            self.keyword_page_map[keyword_number] = page_number

    def get_page_for_keyword_number(self, keyword_number: int) -> Optional[int]:
        """
        Gets the B+ tree page number for a keyword number.

        Args:
            keyword_number: The keyword number to look up

        Returns:
            B+ tree page number, or None if not found
        """
        return self.keyword_page_map.get(keyword_number)

    def find_page_for_keyword_range(self, keyword_number: int) -> Optional[int]:
        """
        Finds the appropriate page for a keyword number using range lookup.
        This handles cases where the exact keyword number isn't in the map.

        Args:
            keyword_number: The keyword number to find a page for

        Returns:
            B+ tree page number, or None if no suitable page found
        """
        if keyword_number in self.keyword_page_map:
            return self.keyword_page_map[keyword_number]

        # Find the largest keyword_number that is <= the target
        best_match = None
        best_page = None

        for kw_num, page_num in self.keyword_page_map.items():
            if kw_num <= keyword_number:
                if best_match is None or kw_num > best_match:
                    best_match = kw_num
                    best_page = page_num

        return best_page

    def get_all_entries(self) -> List[XWMapEntry]:
        """
        Returns all xWMAP entries.

        Returns:
            List of all xWMAP entries
        """
        return self.entries.copy()

    def get_entry_count(self) -> int:
        """
        Returns the total number of xWMAP entries.

        Returns:
            Number of entries
        """
        return len(self.entries)

    def get_keyword_number_range(self) -> tuple:
        """
        Gets the range of keyword numbers covered by this map.

        Returns:
            Tuple of (min_keyword_number, max_keyword_number), or (0, 0) if empty
        """
        if not self.keyword_page_map:
            return (0, 0)

        keyword_numbers = list(self.keyword_page_map.keys())
        return (min(keyword_numbers), max(keyword_numbers))

    def get_page_numbers(self) -> List[int]:
        """
        Gets all unique page numbers referenced in the map.

        Returns:
            List of unique page numbers
        """
        return list(set(self.keyword_page_map.values()))

    def get_entries_for_page(self, page_number: int) -> List[XWMapEntry]:
        """
        Gets all entries that reference a specific page number.

        Args:
            page_number: The page number to search for

        Returns:
            List of entries referencing the page
        """
        return [entry for entry in self.entries if entry.page_number == page_number]

    def get_entries_sorted_by_keyword_number(self) -> List[XWMapEntry]:
        """
        Gets all entries sorted by keyword number.

        Returns:
            List of entries sorted by keyword number
        """
        return sorted(self.entries, key=lambda e: e.keyword_number)

    def get_entries_sorted_by_page_number(self) -> List[XWMapEntry]:
        """
        Gets all entries sorted by page number.

        Returns:
            List of entries sorted by page number
        """
        return sorted(self.entries, key=lambda e: e.page_number)

    def get_statistics(self) -> dict:
        """
        Returns statistics about the xWMAP data.

        Returns:
            Dictionary with xWMAP statistics
        """
        if not self.entries:
            return {
                "total_entries": 0,
                "unique_pages": 0,
                "keyword_number_range": (0, 0),
                "data_size": len(self.raw_data),
            }

        keyword_numbers = list(self.keyword_page_map.keys())
        page_numbers = list(self.keyword_page_map.values())
        unique_pages = set(page_numbers)

        return {
            "total_entries": len(self.entries),
            "unique_pages": len(unique_pages),
            "keyword_number_range": (min(keyword_numbers), max(keyword_numbers)),
            "page_number_range": (min(page_numbers), max(page_numbers)),
            "data_size": len(self.raw_data),
            "average_keywords_per_page": len(self.entries) / len(unique_pages) if unique_pages else 0,
        }
