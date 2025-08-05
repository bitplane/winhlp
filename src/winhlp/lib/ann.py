"""Parser for Windows Help Annotation (.ANN) files.

Based on helpfile.md documentation:
"An annotation file created by WinHelp uses the same basic file format as
a Windows help file. The first 16 bytes contain the same header as a help
file, with same Magic."

ANN files contain user annotations for help topics and follow this structure:
- @VERSION: Contains version info (0x08 0x62 0x6D 0x66 0x01 0x00)
- @LINK: Contains number of annotations and TOPICOFFSET for each annotation
- n!0: Individual annotation text files (e.g., "12345!0") containing plain ANSI text
"""

from typing import List, Dict, Optional
from pydantic import BaseModel
import struct

from .hlp import HelpFile
from .internal_files.base import InternalFile


class AnnotationReference(BaseModel):
    """Reference to an annotation in the @LINK file."""

    topic_offset: int
    unknown1: int  # always 0 according to docs
    unknown2: int  # always 0 according to docs
    raw_data: dict


class VersionFile(InternalFile):
    """Parser for @VERSION internal file in ANN files."""

    version_bytes: bytes = b""

    def __init__(self, **data):
        super().__init__(**data)
        self.version_bytes = b""
        self._parse()

    def _parse(self):
        """Parse the @VERSION file structure."""
        # Expected: 0x08 0x62 0x6D 0x66 0x01 0x00 (6 bytes)
        if len(self.raw_data) >= 6:
            self.version_bytes = self.raw_data[:6]


class LinkFile(InternalFile):
    """Parser for @LINK internal file in ANN files."""

    number_of_annotations: int = 0
    annotation_references: List[AnnotationReference] = []

    def __init__(self, **data):
        super().__init__(**data)
        self.number_of_annotations = 0
        self.annotation_references = []
        self._parse()

    def _parse(self):
        """Parse the @LINK file structure."""
        if len(self.raw_data) < 2:
            return

        # Read number of annotations (2 bytes)
        self.number_of_annotations = struct.unpack_from("<H", self.raw_data, 0)[0]
        offset = 2

        # Read annotation references
        for i in range(self.number_of_annotations):
            if offset + 12 > len(self.raw_data):  # Each reference is 12 bytes
                break

            topic_offset, unknown1, unknown2 = struct.unpack_from("<LLL", self.raw_data, offset)
            offset += 12

            parsed_ref = {
                "topic_offset": topic_offset,
                "unknown1": unknown1,
                "unknown2": unknown2,
            }

            ref = AnnotationReference(**parsed_ref, raw_data={"parsed": parsed_ref})
            self.annotation_references.append(ref)


class AnnotationTextFile(InternalFile):
    """Parser for individual annotation text files (e.g., "12345!0")."""

    text: str = ""
    topic_offset: int = 0

    def __init__(self, topic_offset: int = 0, **data):
        super().__init__(**data)
        self.topic_offset = topic_offset
        self.text = ""
        self._parse()

    def _parse(self):
        """Parse annotation text (plain ANSI characters, not NUL terminated)."""
        try:
            # Decode as ANSI (cp1252) plain text
            self.text = self.raw_data.decode("cp1252", errors="replace")
        except Exception:
            # Fallback to latin-1 if cp1252 fails
            self.text = self.raw_data.decode("latin-1", errors="replace")


class AnnotationFile:
    """
    Parser for Windows Help Annotation (.ANN) files.

    ANN files use the same basic file format as Windows help files but contain
    user annotations for help topics instead of help content.
    """

    def __init__(self, filepath: str):
        """
        Initialize ANN file parser.

        Args:
            filepath: Path to the .ANN annotation file
        """
        self.filepath = filepath
        self.hlp_parser: Optional[HelpFile] = None
        self.version_file: Optional[VersionFile] = None
        self.link_file: Optional[LinkFile] = None
        self.annotation_texts: Dict[int, AnnotationTextFile] = {}  # topic_offset -> AnnotationTextFile

        self._parse()

    def _parse(self):
        """Parse the ANN file using HLP parser infrastructure."""
        try:
            # Parse as HLP file since ANN files use the same basic format
            self.hlp_parser = HelpFile(filepath=self.filepath)

            # Parse ANN-specific internal files
            self._parse_version()
            self._parse_link()
            self._parse_annotation_texts()

        except Exception as e:
            raise ValueError(f"Failed to parse ANN file: {e}")

    def _parse_version(self):
        """Parse the @VERSION internal file."""
        if not self.hlp_parser or "@VERSION" not in self.hlp_parser.directory.files:
            return

        version_offset = self.hlp_parser.directory.files["@VERSION"]
        file_header_data = self.hlp_parser.data[version_offset : version_offset + 9]
        if len(file_header_data) < 9:
            return

        reserved_space, used_space, file_flags = struct.unpack("<llB", file_header_data)
        version_data = self.hlp_parser.data[version_offset + 9 : version_offset + 9 + used_space]

        self.version_file = VersionFile(filename="@VERSION", raw_data=version_data)

    def _parse_link(self):
        """Parse the @LINK internal file."""
        if not self.hlp_parser or "@LINK" not in self.hlp_parser.directory.files:
            return

        link_offset = self.hlp_parser.directory.files["@LINK"]
        file_header_data = self.hlp_parser.data[link_offset : link_offset + 9]
        if len(file_header_data) < 9:
            return

        reserved_space, used_space, file_flags = struct.unpack("<llB", file_header_data)
        link_data = self.hlp_parser.data[link_offset + 9 : link_offset + 9 + used_space]

        self.link_file = LinkFile(filename="@LINK", raw_data=link_data)

    def _parse_annotation_texts(self):
        """Parse individual annotation text files (e.g., "12345!0")."""
        if not self.hlp_parser or not self.link_file:
            return

        # Parse each annotation text file referenced in @LINK
        for ref in self.link_file.annotation_references:
            topic_offset = ref.topic_offset
            annotation_filename = f"{topic_offset}!0"

            if annotation_filename not in self.hlp_parser.directory.files:
                continue

            ann_offset = self.hlp_parser.directory.files[annotation_filename]
            file_header_data = self.hlp_parser.data[ann_offset : ann_offset + 9]
            if len(file_header_data) < 9:
                continue

            reserved_space, used_space, file_flags = struct.unpack("<llB", file_header_data)
            ann_data = self.hlp_parser.data[ann_offset + 9 : ann_offset + 9 + used_space]

            annotation_text = AnnotationTextFile(
                filename=annotation_filename, raw_data=ann_data, topic_offset=topic_offset
            )
            self.annotation_texts[topic_offset] = annotation_text

    def get_annotations(self) -> List[Dict]:
        """
        Get all annotations with their topic offsets and text.

        Returns:
            List of annotation dictionaries with 'topic_offset' and 'text' keys
        """
        annotations = []
        for topic_offset, annotation_text in self.annotation_texts.items():
            annotations.append(
                {"topic_offset": topic_offset, "text": annotation_text.text, "filename": annotation_text.filename}
            )
        return annotations

    def get_annotation_for_topic(self, topic_offset: int) -> Optional[str]:
        """
        Get annotation text for a specific topic offset.

        Args:
            topic_offset: The topic offset to look up

        Returns:
            Annotation text or None if not found
        """
        annotation = self.annotation_texts.get(topic_offset)
        return annotation.text if annotation else None

    def get_statistics(self) -> Dict:
        """
        Get statistics about the annotation file.

        Returns:
            Dictionary with annotation file statistics
        """
        return {
            "total_annotations": len(self.annotation_texts),
            "version_info": self.version_file.version_bytes.hex() if self.version_file else None,
            "annotation_topics": list(self.annotation_texts.keys()),
            "has_version_file": self.version_file is not None,
            "has_link_file": self.link_file is not None,
        }
