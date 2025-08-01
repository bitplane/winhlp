"""Parser for keyword-related internal files."""

from .base import InternalFile
from pydantic import BaseModel
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
    This is a B+ tree implementation (basic placeholder).
    """

    title_entries: list = []

    def __init__(self, **data):
        super().__init__(**data)
        # Note: Full B+ tree parsing would require implementing btree.py navigation
        # This is a basic placeholder that would need the B+ tree infrastructure
        pass


class RoseBTreeFile(InternalFile):
    """
    Parses |Rose files - macro definitions from [MACROS] section.
    This is a B+ tree implementation (basic placeholder).
    """

    macro_entries: list = []

    def __init__(self, **data):
        super().__init__(**data)
        # Note: Full B+ tree parsing would require implementing btree.py navigation
        # This is a basic placeholder that would need the B+ tree infrastructure
        pass


class KeywordsFile(InternalFile):
    """
    Parses keyword indices (|xWBTREE, |xWDATA, etc.).
    This is a B+ tree implementation (basic placeholder).
    """

    keyword_entries: list = []

    def __init__(self, **data):
        super().__init__(**data)
        # Note: Full B+ tree parsing would require implementing btree.py navigation
        # This is a basic placeholder that would need the B+ tree infrastructure
        pass
