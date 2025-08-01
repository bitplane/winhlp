"""Parser for Win95/HCRTF specific internal files."""

from .base import InternalFile
from pydantic import BaseModel


class TopicIdIndexEntry(BaseModel):
    """
    Index entry for |TopicId B-Tree.
    From helpfile.md.
    """

    topic_offset: int
    page_number: int
    raw_data: dict


class TopicIdLeafEntry(BaseModel):
    """
    Leaf entry for |TopicId B-Tree.
    From helpfile.md.
    """

    topic_offset: int
    context_id: str
    raw_data: dict


class PetraIndexEntry(BaseModel):
    """
    Index entry for |Petra B-Tree.
    From helpfile.md.
    """

    topic_offset: int
    page_number: int
    raw_data: dict


class PetraLeafEntry(BaseModel):
    """
    Leaf entry for |Petra B-Tree.
    From helpfile.md.
    """

    topic_offset: int
    source_filename: str
    raw_data: dict


class TopicIdFile(InternalFile):
    """
    Parses |TopicId files - maps topic offsets to context names.
    Created using /a option of HCRTF. Uses B+ tree structure.
    This is a basic placeholder.
    """

    topic_entries: list = []

    def __init__(self, **data):
        super().__init__(**data)
        # Note: Full B+ tree parsing would require implementing btree.py navigation
        # This is a basic placeholder that would need the B+ tree infrastructure
        pass


class PetraFile(InternalFile):
    """
    Parses |Petra files - maps topic offsets to source RTF filenames.
    Used for tracking which RTF file each topic came from.
    This is a basic placeholder.
    """

    source_entries: list = []

    def __init__(self, **data):
        super().__init__(**data)
        # Note: Full B+ tree parsing would require implementing btree.py navigation
        # This is a basic placeholder that would need the B+ tree infrastructure
        pass
