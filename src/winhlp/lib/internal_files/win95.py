"""Parser for Win95/HCRTF specific internal files."""

from .base import InternalFile
from pydantic import BaseModel
from ..btree import BTree
from ..exceptions import BTreeError
import struct


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
    """

    topic_entries: list = []

    def __init__(self, **data):
        super().__init__(**data)
        self.topic_entries = []
        self._parse()

    def _parse(self):
        """Parse |TopicId using B+ tree structure"""
        try:
            btree = BTree(self.raw_data)

            # Iterate through all leaf pages to extract topic ID entries
            for page_data, n_entries in btree.iterate_leaf_pages():
                self._parse_leaf_page(page_data, n_entries)

        except BTreeError as e:
            # Handle B+ tree parsing errors gracefully
            print(f"Warning: Failed to parse B+ tree in TopicIdFile: {e}")

    def _parse_leaf_page(self, page_data: bytes, n_entries: int):
        """Parse TopicIdLEAFENTRY structures from leaf page"""
        # Skip page header (8 bytes for leaf pages)
        offset = 8

        for i in range(n_entries):
            if offset >= len(page_data):
                break

            try:
                # TopicIdLEAFENTRY structure from helpfile.md:
                # TOPICOFFSET TopicOffset
                # STRINGZ ContextName

                # Read topic offset (4 bytes)
                if offset + 4 > len(page_data):
                    break
                topic_offset = struct.unpack_from("<L", page_data, offset)[0]
                offset += 4

                # Read null-terminated context name string
                context_end = page_data.find(b"\x00", offset)
                if context_end == -1:
                    break
                context_id = page_data[offset:context_end].decode("latin-1", errors="replace")
                offset = context_end + 1

                entry = TopicIdLeafEntry(
                    topic_offset=topic_offset,
                    context_id=context_id,
                    raw_data={"raw": page_data[offset - 4 - len(context_id) - 1 : offset]},
                )
                self.topic_entries.append(entry)

            except (struct.error, UnicodeDecodeError):
                break


class PetraFile(InternalFile):
    """
    Parses |Petra files - maps topic offsets to source RTF filenames.
    Used for tracking which RTF file each topic came from.
    """

    source_entries: list = []

    def __init__(self, **data):
        super().__init__(**data)
        self.source_entries = []
        self._parse()

    def _parse(self):
        """Parse |Petra using B+ tree structure"""
        try:
            btree = BTree(self.raw_data)

            # Iterate through all leaf pages to extract source filename entries
            for page_data, n_entries in btree.iterate_leaf_pages():
                self._parse_leaf_page(page_data, n_entries)

        except BTreeError as e:
            # Handle B+ tree parsing errors gracefully
            print(f"Warning: Failed to parse B+ tree in PetraFile: {e}")

    def _parse_leaf_page(self, page_data: bytes, n_entries: int):
        """Parse PetraLEAFENTRY structures from leaf page"""
        # Skip page header (8 bytes for leaf pages)
        offset = 8

        for i in range(n_entries):
            if offset >= len(page_data):
                break

            try:
                # PetraLEAFENTRY structure from helpfile.md:
                # TOPICOFFSET TopicOffset
                # STRINGZ RTFSourceFileName

                # Read topic offset (4 bytes)
                if offset + 4 > len(page_data):
                    break
                topic_offset = struct.unpack_from("<L", page_data, offset)[0]
                offset += 4

                # Read null-terminated source filename string
                filename_end = page_data.find(b"\x00", offset)
                if filename_end == -1:
                    break
                source_filename = page_data[offset:filename_end].decode("latin-1", errors="replace")
                offset = filename_end + 1

                entry = PetraLeafEntry(
                    topic_offset=topic_offset,
                    source_filename=source_filename,
                    raw_data={"raw": page_data[offset - 4 - len(source_filename) - 1 : offset]},
                )
                self.source_entries.append(entry)

            except (struct.error, UnicodeDecodeError):
                break
