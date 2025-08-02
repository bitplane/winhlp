"""Parser for the |TOMAP internal file."""

from .base import InternalFile
from pydantic import BaseModel
from typing import List, Optional
import struct


class TopicPosition(BaseModel):
    """
    Structure for a single topic position entry.
    From helpfile.md: TOPICPOS entries in |TOMAP file.
    """

    topic_number: int
    topic_position: int
    raw_data: dict


class ToMapFile(InternalFile):
    """
    Parses the |TOMAP file, which contains topic position mappings for Windows 3.0 help files.

    From helpfile.md:
    Windows 3.0 (HC30) uses topic numbers that start at 16 for the first topic
    to identify topics. To retrieve the location of the TOPICLINK for the TOPIC-
    HEADER of a certain topic (in |TOPIC explained later), use the |TOMAP file.
    It contains an array of topic positions. Index with TopicNumber (do not
    subtract 16). TopicPos[0] points to the topic specified as INDEX in the help
    project.

    Structure: TOPICPOS TopicPos[UsedSpace/4]
    """

    topic_positions: List[int] = []  # Array of TOPICPOS values
    topic_map: dict = {}  # topic_number -> topic_position mapping

    def __init__(self, **data):
        super().__init__(**data)
        self.topic_positions = []
        self.topic_map = {}
        self._parse()

    def _parse(self):
        """
        Parses the |TOMAP file data as an array of 32-bit topic positions.

        From helpfile.md and helldeco.c:
        - Contains array of TOPICPOS values (32-bit integers)
        - Index directly with topic number (don't subtract 16)
        - TopicPos[0] points to INDEX topic
        """
        if len(self.raw_data) < 9:  # Need at least file header
            return

        # Skip the file header (9 bytes: reserved_space + used_space + file_flags)
        data_start = 9
        topic_data = self.raw_data[data_start:]

        # Calculate number of topic positions (each is 4 bytes)
        num_positions = len(topic_data) // 4

        if num_positions == 0:
            return

        # Parse array of 32-bit topic positions
        for i in range(num_positions):
            offset = i * 4
            if offset + 4 > len(topic_data):
                break

            topic_position = struct.unpack_from("<L", topic_data, offset)[0]
            self.topic_positions.append(topic_position)

            # Build mapping: topic_number -> topic_position
            # Topic numbers start at 16 for first topic, but array is 0-indexed
            topic_number = i + 16
            self.topic_map[topic_number] = topic_position

    def get_topic_position(self, topic_number: int) -> Optional[int]:
        """
        Get the topic position for a given topic number.

        Args:
            topic_number: Topic number (starts at 16 for first topic)

        Returns:
            Topic position or None if not found
        """
        return self.topic_map.get(topic_number)

    def get_index_topic_position(self) -> Optional[int]:
        """
        Get the position of the INDEX topic.

        From helpfile.md: TopicPos[0] points to the topic specified as INDEX
        in the help project.

        Returns:
            Position of INDEX topic or None if no topics
        """
        if len(self.topic_positions) > 0:
            return self.topic_positions[0]
        return None

    def get_topic_count(self) -> int:
        """Get the total number of topics in the |TOMAP file."""
        return len(self.topic_positions)
