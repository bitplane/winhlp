"""
GRP file parser for Windows HLP files.

GRP files handle MediaView group files (.GRP) that contain group+ footnotes
assigned to topics in MediaView files. These are used for organizing topics
into groups with optional bitmaps.

Based on the helpdeco C reference implementation and documentation.
"""

import struct
from typing import List, Optional, Dict
from pydantic import BaseModel

from .internal_file import InternalFile


class GroupHeader(BaseModel):
    """Header structure for GRP files."""

    magic: int  # Should be 0x000A3333
    bitmap_size: int  # max. 64000 equalling 512000 topics
    last_topic: int  # first topic in help file has topic number 0
    unknown_field: Optional[int] = None
    raw_data: dict


class TopicRange(BaseModel):
    """A range of topics in a group."""

    start_topic: int
    end_topic: int
    group_id: int
    raw_data: dict


class GRPFile(InternalFile):
    """
    Parses GRP (MediaView Group) files.

    GRP files contain group+ footnotes assigned to topics in MediaView files.
    They have a specific structure with a header containing magic number 0x000A3333,
    bitmap size, and topic ranges.

    Structure from documentation:
    - Magic: 0x000A3333
    - BitmapSize: max. 64000 equalling 512000 topics
    - LastTopic: first topic in help file has topic number 0
    - Topic ranges and group assignments
    - Optional bitmap data
    """

    def __init__(self, data: bytes, help_file=None):
        super().__init__(data, help_file)
        self.header: Optional[GroupHeader] = None
        self.topic_ranges: List[TopicRange] = []
        self.bitmap_data: Optional[bytes] = None
        self.topic_to_group: Dict[int, int] = {}  # Maps topic number to group ID
        self._parse()

    def _parse(self):
        """Parse the GRP file structure."""
        if len(self.data) < 12:  # Need at least header
            return

        try:
            self._parse_header()
            self._parse_topic_ranges()
            self._parse_bitmap_data()
            self._build_topic_mappings()

        except Exception:
            # If parsing fails, create minimal structure
            pass

    def _parse_header(self):
        """Parse the GROUP header structure."""
        if len(self.data) < 12:
            return

        try:
            # Read header fields
            magic = struct.unpack_from("<L", self.data, 0)[0]
            bitmap_size = struct.unpack_from("<L", self.data, 4)[0]
            last_topic = struct.unpack_from("<L", self.data, 8)[0]

            # Validate magic number
            if magic != 0x000A3333:
                # Not a valid GRP file, but continue parsing anyway
                pass

            self.header = GroupHeader(
                magic=magic,
                bitmap_size=bitmap_size,
                last_topic=last_topic,
                raw_data={
                    "magic": f"0x{magic:08X}",
                    "bitmap_size": bitmap_size,
                    "last_topic": last_topic,
                    "is_valid_magic": magic == 0x000A3333,
                },
            )

        except (struct.error, IndexError):
            # Create minimal header on error
            self.header = GroupHeader(
                magic=0, bitmap_size=0, last_topic=0, raw_data={"error": "Failed to parse header"}
            )

    def _parse_topic_ranges(self):
        """Parse topic ranges and group assignments."""
        if not self.header or len(self.data) < 16:
            return

        offset = 12  # After header

        try:
            # Parse topic ranges until we hit bitmap data or end of file
            while offset + 12 <= len(self.data):
                # Try to read what looks like a topic range entry
                # Format is not fully documented, so we make educated guesses

                start_topic = struct.unpack_from("<L", self.data, offset)[0]
                offset += 4

                end_topic = struct.unpack_from("<L", self.data, offset)[0]
                offset += 4

                group_id = struct.unpack_from("<L", self.data, offset)[0]
                offset += 4

                # Sanity check: topic numbers should be reasonable
                if start_topic > 0x10000000 or end_topic > 0x10000000 or start_topic > end_topic:
                    # Probably hit bitmap data or end of ranges
                    offset -= 12  # Back up
                    break

                # Create topic range entry
                topic_range = TopicRange(
                    start_topic=start_topic,
                    end_topic=end_topic,
                    group_id=group_id,
                    raw_data={
                        "start_topic": start_topic,
                        "end_topic": end_topic,
                        "group_id": group_id,
                        "topic_count": end_topic - start_topic + 1,
                    },
                )

                self.topic_ranges.append(topic_range)

        except (struct.error, IndexError):
            # Stop parsing ranges on error
            pass

    def _parse_bitmap_data(self):
        """Parse optional bitmap data at the end of the file."""
        if not self.header:
            return

        # Calculate where bitmap data might start
        # It comes after header + topic ranges
        header_size = 12
        ranges_size = len(self.topic_ranges) * 12  # Each range is 12 bytes
        bitmap_start = header_size + ranges_size

        if bitmap_start < len(self.data) and self.header.bitmap_size > 0:
            remaining_data = self.data[bitmap_start:]

            # Take up to bitmap_size bytes for bitmap data
            bitmap_size = min(self.header.bitmap_size, len(remaining_data))
            if bitmap_size > 0:
                self.bitmap_data = remaining_data[:bitmap_size]

    def _build_topic_mappings(self):
        """Build topic number to group ID mappings."""
        for topic_range in self.topic_ranges:
            for topic_num in range(topic_range.start_topic, topic_range.end_topic + 1):
                self.topic_to_group[topic_num] = topic_range.group_id

    def get_group_for_topic(self, topic_number: int) -> Optional[int]:
        """Get the group ID for a given topic number."""
        return self.topic_to_group.get(topic_number)

    def get_topics_in_group(self, group_id: int) -> List[int]:
        """Get all topic numbers in a given group."""
        topics = []
        for topic_num, grp_id in self.topic_to_group.items():
            if grp_id == group_id:
                topics.append(topic_num)
        return sorted(topics)

    def get_all_groups(self) -> List[int]:
        """Get all group IDs in the file."""
        return sorted(set(self.topic_to_group.values()))

    def has_bitmap(self) -> bool:
        """Check if the GRP file contains bitmap data."""
        return self.bitmap_data is not None and len(self.bitmap_data) > 0

    def get_statistics(self) -> dict:
        """Get statistics about the GRP file."""
        return {
            "is_valid": self.header and self.header.magic == 0x000A3333,
            "magic_number": f"0x{self.header.magic:08X}" if self.header else "None",
            "topic_ranges_count": len(self.topic_ranges),
            "total_topics_covered": len(self.topic_to_group),
            "group_count": len(set(self.topic_to_group.values())),
            "has_bitmap": self.has_bitmap(),
            "bitmap_size": len(self.bitmap_data) if self.bitmap_data else 0,
            "raw_data_size": len(self.data),
        }
