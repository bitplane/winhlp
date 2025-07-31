"""Generic B+ tree implementation for HLP files."""

from pydantic import BaseModel, Field
from typing import Optional
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

    def get_leaf_pages(self):
        """
        Traverses the B-Tree to find and yield each leaf page in order.

        This logic is based on the GetFirstPage and GetNextPage functions in
        the reference C code.

        From `helpdec1.c`:
        int16_t GetFirstPage(FILE* HelpFile, BUFFER* buf, long* TotalEntries)
        {
            int CurrLevel;
            BTREEHEADER BTreeHdr;
            BTREENODEHEADER CurrNode;

            read_BTREEHEADER(&BTreeHdr, HelpFile);
            if (TotalEntries) *TotalEntries = BTreeHdr.TotalBtreeEntries;
            if (!BTreeHdr.TotalBtreeEntries) return 0;
            buf->FirstLeaf = ftell(HelpFile);
            buf->PageSize = BTreeHdr.PageSize;
            fseek(HelpFile, buf->FirstLeaf + BTreeHdr.RootPage * (long)BTreeHdr.PageSize, SEEK_SET);
            for (CurrLevel = 1; CurrLevel < BTreeHdr.NLevels; CurrLevel++)
            {
                read_BTREEINDEXHEADER_to_BTREENODEHEADER(&CurrNode, HelpFile);
                fseek(HelpFile, buf->FirstLeaf + CurrNode.PreviousPage * (long)BTreeHdr.PageSize, SEEK_SET);
            }
            read_BTREENODEHEADER(&CurrNode, HelpFile);
            buf->NextPage = CurrNode.NextPage;
            return CurrNode.NEntries;
        }

        int16_t GetNextPage(FILE* HelpFile, BUFFER* buf) /* walk Btree */
        {
            BTREENODEHEADER CurrNode;

            if (buf->NextPage == -1) return 0;
            fseek(HelpFile, buf->FirstLeaf + buf->NextPage * (long)buf->PageSize, SEEK_SET);
            read_BTREENODEHEADER(&CurrNode, HelpFile);
            buf->NextPage = CurrNode.NextPage;
            return CurrNode.NEntries;
        }
        """
        if not self.header.total_btree_entries:
            return

        # Navigate from the root to the first leaf page
        page_index = self.header.root_page
        for _ in range(1, self.header.n_levels):
            page = self.pages[page_index]
            unknown, n_entries, prev_page = struct.unpack("<hhh", page[:6])
            index_header = BTreeIndexHeader(
                unknown=unknown, n_entries=n_entries, previous_page=prev_page, raw_data={"raw": page[:6], "parsed": {}}
            )
            page_index = index_header.previous_page

        # Iterate through the doubly-linked list of leaf pages
        while page_index != -1:
            yield self.pages[page_index]
            node_header_data = self.pages[page_index][:8]
            unknown, n_entries, prev_page, next_page = struct.unpack("<hhhh", node_header_data)
            node_header = BTreeNodeHeader(
                unknown=unknown,
                n_entries=n_entries,
                previous_page=prev_page,
                next_page=next_page,
                raw_data={"raw": node_header_data, "parsed": {}},
            )
            page_index = node_header.next_page
