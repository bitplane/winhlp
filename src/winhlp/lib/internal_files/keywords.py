"""Parser for keyword-related internal files."""

from .base import InternalFile
from pydantic import BaseModel
from ..btree import BTree
from ..exceptions import BTreeError
import struct


class KeywordIndexEntry(BaseModel):
    """
    Index entry for a |xWBTREE B-Tree.
    From `helpfile.md`.
    """

    keyword: str
    page_number: int
    raw_data: dict


class KeywordLeafEntry(BaseModel):
    """
    Leaf entry for a |xWBTREE B-Tree.
    From `helpfile.md`.
    """

    keyword: str
    count: int
    kw_data_offset: int
    raw_data: dict


class TitleLeafEntry(BaseModel):
    """
    Leaf entry for the |TTLBTREE B-Tree.
    From `helpfile.md`.
    """

    topic_offset: int
    topic_title: str
    raw_data: dict


class RoseLeafEntry(BaseModel):
    """
    Leaf entry for the |Rose B-Tree.
    From `helpfile.md`.
    """

    keyword_hash: int
    macro: str
    topic_title: str
    raw_data: dict


class KWMapRec(BaseModel):
    """
    Map record for |xWMAP files.
    From helldeco.h: KWMAPREC
    """

    first_rec: int
    page_num: int
    raw_data: dict


class KeywordDataFile(InternalFile):
    """
    Parses |xWDATA files - array of topic offsets.
    """

    topic_offsets: list = []

    def __init__(self, **data):
        super().__init__(**data)
        self._parse()

    def _parse(self):
        """Parse topic offsets from raw data"""
        offset = 0
        while offset + 4 <= len(self.raw_data):
            topic_offset = struct.unpack_from("<l", self.raw_data, offset)[0]
            self.topic_offsets.append(topic_offset)
            offset += 4


class KeywordMapFile(InternalFile):
    """
    Parses |xWMAP files - maps keyword numbers to B+ tree pages.
    """

    map_records: list = []

    def __init__(self, **data):
        super().__init__(**data)
        self._parse()

    def _parse(self):
        """Parse keyword map records"""
        offset = 0
        while offset + 6 <= len(self.raw_data):
            first_rec, page_num = struct.unpack_from("<lH", self.raw_data, offset)
            record = KWMapRec(
                first_rec=first_rec,
                page_num=page_num,
                raw_data={
                    "raw": self.raw_data[offset : offset + 6],
                    "parsed": {"first_rec": first_rec, "page_num": page_num},
                },
            )
            self.map_records.append(record)
            offset += 6


class TTLBTreeFile(InternalFile):
    """
    Parses |TTLBTREE files - topic titles indexed by topic offset.
    Uses B+ tree structure for title lookup.
    """

    title_entries: list = []

    def __init__(self, **data):
        super().__init__(**data)
        self.title_entries = []
        self._parse()

    def _parse(self):
        """Parse |TTLBTREE using B+ tree structure"""
        try:
            btree = BTree(self.raw_data)

            # Iterate through all leaf pages to extract title entries
            for page_data, n_entries in btree.iterate_leaf_pages():
                self._parse_leaf_page(page_data, n_entries)

        except BTreeError as e:
            # Handle B+ tree parsing errors gracefully
            print(f"Warning: Failed to parse B+ tree in TTLBTreeFile: {e}")

    def _parse_leaf_page(self, page_data: bytes, n_entries: int):
        """Parse TTLBTREELEAFENTRY structures from leaf page"""
        # Skip page header (8 bytes for leaf pages)
        offset = 8

        for i in range(n_entries):
            if offset >= len(page_data):
                break

            try:
                # TTLBTREELEAFENTRY structure from helpfile.md:
                # TOPICOFFSET TopicOffset
                # STRINGZ TopicTitle

                # Read topic offset (4 bytes)
                if offset + 4 > len(page_data):
                    break
                topic_offset = struct.unpack_from("<L", page_data, offset)[0]
                offset += 4

                # Read null-terminated title string
                title_end = page_data.find(b"\x00", offset)
                if title_end == -1:
                    break
                topic_title = page_data[offset:title_end].decode("latin-1", errors="replace")
                offset = title_end + 1

                entry = TitleLeafEntry(
                    topic_offset=topic_offset,
                    topic_title=topic_title,
                    raw_data={"raw": page_data[offset - 4 - len(topic_title) - 1 : offset]},
                )
                self.title_entries.append(entry)

            except (struct.error, UnicodeDecodeError):
                break


class RoseBTreeFile(InternalFile):
    """
    Parses |Rose files - macro definitions from [MACROS] section.
    Uses B+ tree structure for macro lookup.
    """

    macro_entries: list = []

    def __init__(self, **data):
        super().__init__(**data)
        self.macro_entries = []
        self._parse()

    def _parse(self):
        """Parse |Rose using B+ tree structure"""
        try:
            btree = BTree(self.raw_data)

            # Iterate through all leaf pages to extract macro entries
            for page_data, n_entries in btree.iterate_leaf_pages():
                self._parse_leaf_page(page_data, n_entries)

        except BTreeError as e:
            # Handle B+ tree parsing errors gracefully
            print(f"Warning: Failed to parse B+ tree in RoseBTreeFile: {e}")

    def _parse_leaf_page(self, page_data: bytes, n_entries: int):
        """Parse RoseLEAFENTRY structures from leaf page"""
        # Skip page header (8 bytes for leaf pages)
        offset = 8

        for i in range(n_entries):
            if offset >= len(page_data):
                break

            try:
                # RoseLEAFENTRY structure from helpfile.md:
                # long KeywordHash
                # STRINGZ Macro
                # STRINGZ TopicTitle

                # Read keyword hash (4 bytes)
                if offset + 4 > len(page_data):
                    break
                keyword_hash = struct.unpack_from("<L", page_data, offset)[0]
                offset += 4

                # Read null-terminated macro string
                macro_end = page_data.find(b"\x00", offset)
                if macro_end == -1:
                    break
                macro = page_data[offset:macro_end].decode("latin-1", errors="replace")
                offset = macro_end + 1

                # Read null-terminated topic title string
                title_end = page_data.find(b"\x00", offset)
                if title_end == -1:
                    break
                topic_title = page_data[offset:title_end].decode("latin-1", errors="replace")
                offset = title_end + 1

                entry = RoseLeafEntry(
                    keyword_hash=keyword_hash,
                    macro=macro,
                    topic_title=topic_title,
                    raw_data={"raw": page_data[offset - 4 - len(macro) - len(topic_title) - 2 : offset]},
                )
                self.macro_entries.append(entry)

            except (struct.error, UnicodeDecodeError):
                break


class KeywordsFile(InternalFile):
    """
    Parses keyword indices (|xWBTREE, |xWDATA, etc.).
    Uses B+ tree structure for keyword lookup.
    """

    keyword_entries: list = []

    def __init__(self, **data):
        super().__init__(**data)
        self.keyword_entries = []
        self._parse()

    def _parse(self):
        """Parse |xWBTREE using B+ tree structure"""
        try:
            btree = BTree(self.raw_data)

            # Iterate through all leaf pages to extract keyword entries
            for page_data, n_entries in btree.iterate_leaf_pages():
                self._parse_leaf_page(page_data, n_entries)

        except BTreeError as e:
            # Handle B+ tree parsing errors gracefully
            print(f"Warning: Failed to parse B+ tree in KeywordsFile: {e}")

    def _parse_leaf_page(self, page_data: bytes, n_entries: int):
        """Parse xWBTREELEAFENTRY structures from leaf page"""
        # Skip page header (8 bytes for leaf pages)
        offset = 8

        for i in range(n_entries):
            if offset >= len(page_data):
                break

            try:
                # xWBTREELEAFENTRY structure from helpfile.md:
                # STRINGZ Keyword
                # short Count (number of times keyword is referenced)
                # long KWDataOffset (offset into |xWDATA)

                # Read null-terminated keyword string
                keyword_end = page_data.find(b"\x00", offset)
                if keyword_end == -1:
                    break
                keyword = page_data[offset:keyword_end].decode("latin-1", errors="replace")
                offset = keyword_end + 1

                # Read count (2 bytes) and kw_data_offset (4 bytes)
                if offset + 6 > len(page_data):
                    break
                count, kw_data_offset = struct.unpack_from("<hL", page_data, offset)
                offset += 6

                entry = KeywordLeafEntry(
                    keyword=keyword,
                    count=count,
                    kw_data_offset=kw_data_offset,
                    raw_data={"raw": page_data[offset - 6 - len(keyword) - 1 : offset]},
                )
                self.keyword_entries.append(entry)

            except (struct.error, UnicodeDecodeError):
                break
