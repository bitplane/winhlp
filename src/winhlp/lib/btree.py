"""Generic B+ tree implementation for HLP files."""

from pydantic import BaseModel, Field
from typing import Optional, Iterator, Tuple
from .exceptions import BTreeError
import struct


class BTreeHeader(BaseModel):
    """
    A B+ tree starts with a BTREEHEADER.
    From `helpdeco.h`: BTREEHEADER
    """

    magic: int = Field(..., description="Should be 0x293B")
    flags: int
    page_size: int
    structure: bytes = Field(..., description="String describing format of data")
    must_be_zero: int
    page_splits: int
    root_page: int
    must_be_neg_one: int
    total_pages: int
    n_levels: int
    total_btree_entries: int
    raw_data: dict


class BTreeNodeHeader(BaseModel):
    """
    B+ tree leaf-page header.
    From `helpdeco.h`: BTREENODEHEADER
    """

    unknown: int
    n_entries: int
    previous_page: int
    next_page: int
    raw_data: dict


class BTreeIndexHeader(BaseModel):
    """
    B+ tree index-page header.
    From `helpdeco.h`: BTREEINDEXHEADER
    """

    unknown: int
    n_entries: int
    previous_page: int
    raw_data: dict


class BTreeBuffer(BaseModel):
    """
    State management for B+ tree iteration.
    Based on helpdeco's BUFFER struct used with GetFirstPage/GetNextPage.

    From `helpdeco.h`:
    typedef struct
    {
        int32_t FirstLeaf;
        uint16_t PageSize;
        int16_t NextPage;
    }
    BUFFER;
    """

    first_leaf: int = Field(..., description="Starting position of B+ tree data")
    page_size: int = Field(..., description="Size of each page")
    next_page: int = Field(..., description="Index of next page to read (-1 if done)")
    current_offset: int = Field(default=0, description="Current position in data stream")


class BTree(BaseModel):
    """
    A B+ tree is made from leaf-pages and index-pages of fixed size, one of which
    is the root-page. All entries are contained in leaf-pages. If more entries
    are required than fit into a single leaf-page, index-pages are used to locate
    the leaf-page which contains the required entry.
    """

    header: Optional[BTreeHeader] = None
    pages: list = []

    def __init__(self, data: bytes, **kwargs):
        super().__init__(header=None, **kwargs)
        self._parse(data)

    def _parse(self, data: bytes):
        """
        Parses the B-Tree from the given data.
        """
        self._parse_header(data)
        self._parse_pages(data)

    def _parse_header(self, data: bytes):
        """
        Parses the B-Tree header.

        From `helpfile.md`:
        unsigned short Magic        0x293B
        unsigned short Flags        bit 0x0002 always 1, bit 0x0400 1 if directory
        unsigned short PageSize     0x0400=1k if directory, 0x0800=2k else, or 4k
        char Structure[16]      string describing format of data
        short MustBeZero        0
        short PageSplits        number of page splits B+ tree has suffered
        short RootPage          page number of B+ tree root page
        short MustBeNegOne      0xFFFF
        short TotalPages        number of B+ tree pages
        short NLevels           number of levels of B+ tree
        long TotalBtreeEntries  number of entries in B+ tree

        From `helpdeco.h`:
        typedef struct BTREEHEADER   /* structure after FILEHEADER of each Btree */
        {
            uint16_t Magic;    /* 0x293B */
            uint16_t Flags;    /* bit 0x0002 always 1, bit 0x0400 1 if direcory */
            uint16_t PageSize; /* 0x0400=1k if directory, 0x0800=2k else */
            unsigned char Structure[16]; /* string describing structure of data */
            int16_t MustBeZero;        /* 0 */
            int16_t PageSplits;        /* number of page splits Btree has suffered */
            int16_t RootPage;          /* page number of Btree root page */
            int16_t MustBeNegOne;      /* 0xFFFF */
            int16_t TotalPages;        /* number of Btree pages */
            int16_t NLevels;           /* number of levels of Btree */
            int32_t TotalBtreeEntries;  /* number of entries in Btree */
        }
        BTREEHEADER;

        From `helpdec1.c`:
        s(BTREEHEADER)
        w(Magic)
        w(Flags)
        w(PageSize)
        a(Structure, 0x10)
        w(MustBeZero)
        w(PageSplits)
        w(RootPage)
        w(MustBeNegOne)
        w(TotalPages)
        w(NLevels)
        d(TotalBtreeEntries)
        e
        """
        raw_bytes = data[:38]
        if len(raw_bytes) < 38:
            raise BTreeError("Invalid B-Tree header size.")

        offset = 0

        magic, flags, page_size = struct.unpack_from("<HHH", raw_bytes, offset)
        offset += struct.calcsize("<HHH")

        structure = struct.unpack_from("<16s", raw_bytes, offset)[0]
        offset += 16

        (
            must_be_zero,
            page_splits,
            root_page,
            must_be_neg_one,
            total_pages,
            n_levels,
        ) = struct.unpack_from("<hhhhhh", raw_bytes, offset)
        offset += struct.calcsize("<hhhhhh")

        total_btree_entries = struct.unpack_from("<l", raw_bytes, offset)[0]

        if magic != 0x293B:
            raise BTreeError(f"Invalid B-Tree magic number: {magic:#0x}")

        parsed_header = {
            "magic": magic,
            "flags": flags,
            "page_size": page_size,
            "structure": structure,
            "must_be_zero": must_be_zero,
            "page_splits": page_splits,
            "root_page": root_page,
            "must_be_neg_one": must_be_neg_one,
            "total_pages": total_pages,
            "n_levels": n_levels,
            "total_btree_entries": total_btree_entries,
        }

        self.header = BTreeHeader(**parsed_header, raw_data={"raw": raw_bytes, "parsed": parsed_header})

    def _parse_pages(self, data: bytes):
        """
        Parses the B-Tree pages.

        The logic for parsing pages involves iterating through the pages based on the
        B-Tree header information and parsing each page as either a leaf or an index
        page.
        """
        page_data = data[38:]
        for i in range(self.header.total_pages):
            page_start = i * self.header.page_size
            page_end = page_start + self.header.page_size
            self.pages.append(page_data[page_start:page_end])

    def get_first_page(self) -> Tuple[int, BTreeBuffer]:
        """
        Finds the first leaf page in the B+ tree and returns its entry count.
        Based on helpdeco's GetFirstPage function.

        Returns:
            Tuple of (number of entries, buffer state for iteration)
        """
        if not self.header.total_btree_entries:
            return 0, None

        # Create buffer to track iteration state
        buffer = BTreeBuffer(
            first_leaf=38,  # After B+ tree header
            page_size=self.header.page_size,
            next_page=-1,
            current_offset=38,
        )

        # Navigate from root to first leaf
        page_index = self.header.root_page

        # Go down through index levels to reach leaf level
        for curr_level in range(1, self.header.n_levels):
            if page_index < 0 or page_index >= len(self.pages):
                raise BTreeError(f"Invalid page index: {page_index}")

            page = self.pages[page_index]
            # Read index header
            if len(page) < 6:
                raise BTreeError(f"Invalid index page size: {len(page)} < 6 bytes")
            unknown, n_entries, prev_page = struct.unpack("<hhh", page[:6])
            page_index = prev_page

        # Now we're at the leaf level
        if page_index < 0 or page_index >= len(self.pages):
            raise BTreeError(f"Invalid leaf page index: {page_index}")

        page = self.pages[page_index]
        # Read leaf header
        if len(page) < 8:
            raise BTreeError(f"Invalid leaf page size: {len(page)} < 8 bytes")
        unknown, n_entries, prev_page, next_page = struct.unpack("<hhhh", page[:8])

        buffer.next_page = next_page
        buffer.current_offset = buffer.first_leaf + page_index * buffer.page_size + 8

        return n_entries, buffer

    def get_next_page(self, buffer: BTreeBuffer) -> int:
        """
        Gets the next leaf page in the B+ tree.
        Based on helpdeco's GetNextPage function.

        Args:
            buffer: State from previous get_first_page or get_next_page call

        Returns:
            Number of entries in the page (0 if no more pages)
        """
        if buffer.next_page == -1:
            return 0

        if buffer.next_page < 0 or buffer.next_page >= len(self.pages):
            raise BTreeError(f"Invalid next page index: {buffer.next_page}")

        page = self.pages[buffer.next_page]
        # Read leaf header
        if len(page) < 8:
            raise BTreeError(f"Invalid next page size: {len(page)} < 8 bytes")
        unknown, n_entries, prev_page, next_page = struct.unpack("<hhhh", page[:8])

        buffer.next_page = next_page
        buffer.current_offset = buffer.first_leaf + buffer.next_page * buffer.page_size + 8

        return n_entries

    def iterate_leaf_pages(self) -> Iterator[Tuple[bytes, int]]:
        """
        Iterates through all leaf pages using the GetFirstPage/GetNextPage approach.

        Yields:
            Tuple of (page data, number of entries)
        """
        n_entries, buffer = self.get_first_page()

        if n_entries == 0 or buffer is None:
            return

        # Find the page index from current offset
        page_idx = (buffer.current_offset - buffer.first_leaf - 8) // buffer.page_size
        yield self.pages[page_idx], n_entries

        while True:
            # Store current page index before getting next
            current_page_idx = buffer.next_page
            n_entries = self.get_next_page(buffer)

            if n_entries == 0:
                break

            yield self.pages[current_page_idx], n_entries

    def iterate_leaf_entries_with_parser(self, parse_entry_func):
        """
        Iterates through all entries in B+ tree leaf pages with a custom parser function.

        This method provides a higher-level iterator that abstracts away the page-by-page
        iteration and header skipping, allowing callers to focus on their specific
        entry parsing logic.

        Based on the C reference's GetFirstPage/GetNextPage pattern but provides
        a cleaner, more Pythonic interface.

        Args:
            parse_entry_func: Function that takes (page_data, offset) and returns
                             (parsed_entry, new_offset). Should return (None, offset)
                             to skip invalid entries.

        Yields:
            Parsed entries from parse_entry_func (excluding None results)
        """
        for page, n_entries in self.iterate_leaf_pages():
            offset = 8  # Skip 8-byte page header (BTREENODEHEADER)

            for _ in range(n_entries):
                if offset >= len(page):
                    break

                try:
                    entry, new_offset = parse_entry_func(page, offset)
                    if entry is not None:
                        yield entry
                    offset = new_offset
                except (struct.error, IndexError, ValueError):
                    # Skip malformed entries
                    break
