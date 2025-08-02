"""Parser for the |xWDATA internal file."""

from .base import InternalFile
from typing import List, Optional
import struct


class XWDataFile(InternalFile):
    """
    Parses the |xWDATA file, which contains topic offsets for keywords.

    From helpfile.md:
    The |xWDATA contains an array of topic offsets. The KWDataOffset from the
    |xWBTREE tells you where to seek to in the |xWDATA file to read Count topic
    offsets.

    TOPICOFFSET KeywordTopicOffset[UsedSpace/4]

    And the topic offset retrieved tells you which location the Keyword was
    assigned to. It is -1L if the Keyword is assigned to a macro using the [MACROS]
    section of HCRTF 4.0 (see description of |Rose file).
    """

    topic_offsets: List[int] = []

    def __init__(self, **data):
        super().__init__(**data)
        self.topic_offsets = []
        self._parse()

    def _parse(self):
        """
        Parses the |xWDATA file data.
        """
        if len(self.raw_data) < 9:  # Need at least file header
            return

        # Skip the file header (9 bytes: reserved_space + used_space + file_flags)
        data_start = 9
        xwdata_data = self.raw_data[data_start:]

        # Parse topic offsets (4 bytes each)
        offset = 0
        while offset + 4 <= len(xwdata_data):
            topic_offset = struct.unpack_from("<l", xwdata_data, offset)[0]
            self.topic_offsets.append(topic_offset)
            offset += 4

    def get_topic_offset(self, index: int) -> Optional[int]:
        """
        Gets a topic offset by index.

        Args:
            index: Zero-based index into the topic offset array

        Returns:
            Topic offset, or None if index is out of range
        """
        if 0 <= index < len(self.topic_offsets):
            return self.topic_offsets[index]
        return None

    def get_topic_offsets_range(self, start_offset: int, count: int) -> List[int]:
        """
        Gets a range of topic offsets starting from a byte offset.
        This is used with KWDataOffset from |xWBTREE entries.

        Args:
            start_offset: Byte offset into the data (not index)
            count: Number of topic offsets to retrieve

        Returns:
            List of topic offsets
        """
        # Convert byte offset to index (each topic offset is 4 bytes)
        start_index = start_offset // 4
        end_index = start_index + count

        # Bounds check
        if start_index < 0 or start_index >= len(self.topic_offsets):
            return []

        end_index = min(end_index, len(self.topic_offsets))
        return self.topic_offsets[start_index:end_index]

    def get_all_topic_offsets(self) -> List[int]:
        """
        Returns all topic offsets in the file.

        Returns:
            List of all topic offsets
        """
        return self.topic_offsets.copy()

    def get_topic_offset_count(self) -> int:
        """
        Returns the total number of topic offsets.

        Returns:
            Number of topic offsets
        """
        return len(self.topic_offsets)

    def is_macro_offset(self, topic_offset: int) -> bool:
        """
        Checks if a topic offset represents a macro reference.

        Args:
            topic_offset: The topic offset to check

        Returns:
            True if the offset is -1 (macro reference), False otherwise
        """
        return topic_offset == -1

    def get_valid_topic_offsets(self) -> List[int]:
        """
        Returns only valid topic offsets (excludes macro references).

        Returns:
            List of topic offsets that are not -1
        """
        return [offset for offset in self.topic_offsets if offset != -1]

    def get_macro_count(self) -> int:
        """
        Returns the number of macro references (topic offsets that are -1).

        Returns:
            Number of macro references
        """
        return sum(1 for offset in self.topic_offsets if offset == -1)

    def find_offset_index(self, topic_offset: int) -> List[int]:
        """
        Find all indices where a specific topic offset appears.

        Args:
            topic_offset: The topic offset to search for

        Returns:
            List of indices where the topic offset appears
        """
        indices = []
        for i, offset in enumerate(self.topic_offsets):
            if offset == topic_offset:
                indices.append(i)
        return indices

    def get_unique_topic_offsets(self) -> List[int]:
        """
        Returns unique topic offsets (removes duplicates).

        Returns:
            List of unique topic offsets
        """
        return list(set(self.topic_offsets))

    def get_statistics(self) -> dict:
        """
        Returns statistics about the xWDATA data.

        Returns:
            Dictionary with xWDATA statistics
        """
        if not self.topic_offsets:
            return {
                "total_offsets": 0,
                "unique_offsets": 0,
                "macro_references": 0,
                "valid_topic_offsets": 0,
                "data_size": len(self.raw_data),
            }

        unique_offsets = set(self.topic_offsets)
        macro_count = sum(1 for offset in self.topic_offsets if offset == -1)
        valid_count = len(self.topic_offsets) - macro_count

        return {
            "total_offsets": len(self.topic_offsets),
            "unique_offsets": len(unique_offsets),
            "macro_references": macro_count,
            "valid_topic_offsets": valid_count,
            "data_size": len(self.raw_data),
            "min_offset": min(offset for offset in self.topic_offsets if offset != -1) if valid_count > 0 else 0,
            "max_offset": max(offset for offset in self.topic_offsets if offset != -1) if valid_count > 0 else 0,
        }
