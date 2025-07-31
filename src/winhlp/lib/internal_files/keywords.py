"""Parser for keyword-related internal files."""

from .base import InternalFile
from pydantic import BaseModel


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


class KeywordsFile(InternalFile):
    """
    Parses keyword indices (|xWBTREE, |xWDATA, etc.).
    """

    pass
