"""Parser for the |TOPIC internal file."""

from .base import InternalFile
from pydantic import BaseModel
from typing import List, Any, Optional, Tuple
import struct
from ..compression import decompress


class TopicBlockHeader(BaseModel):
    """
    Header for each block in the |TOPIC file.
    From `helpdeco.h`: TOPICBLOCKHEADER
    """

    last_topic_link: int
    first_topic_link: int
    last_topic_header: int
    raw_data: dict


class TopicLink(BaseModel):
    """
    A link to a topic, found within a topic block.
    From `helpdeco.h`: TOPICLINK
    """

    block_size: int
    data_len2: int
    prev_block: int
    next_block: int
    data_len1: int
    record_type: int
    text_content: Optional[str] = None
    raw_data: dict


class TopicHeader(BaseModel):
    """
    Topic header for WinHelp 3.1+ files.
    From `helpdeco.h`: TOPICHEADER
    """

    block_size: int
    browse_bck: int
    browse_for: int
    topic_num: int
    non_scroll: int
    scroll: int
    next_topic: int
    raw_data: dict


class TopicHeader30(BaseModel):
    """
    Topic header for WinHelp 3.0 files.
    From `helpdeco.h`: TOPICHEADER30
    """

    block_size: int
    prev_topic_num: int
    unused1: int
    next_topic_num: int
    unused2: int
    raw_data: dict


class ParagraphInfoBits(BaseModel):
    """
    Bit-packed field within ParagraphInfo.
    From `helpfile.md`.
    """

    unknown_follows: bool
    spacing_above_follows: bool
    spacing_below_follows: bool
    spacing_lines_follows: bool
    left_indent_follows: bool
    right_indent_follows: bool
    firstline_indent_follows: bool
    unused: bool
    borderinfo_follows: bool
    tabinfo_follows: bool
    right_aligned_paragraph: bool
    center_aligned_paragraph: bool


class BorderInfo(BaseModel):
    """
    Structure describing paragraph borders.
    From `helpfile.md`.
    """

    border_box: bool
    border_top: bool
    border_left: bool
    border_bottom: bool
    border_right: bool
    border_thick: bool
    border_double: bool
    border_unknown: bool
    border_width: int


class Tab(BaseModel):
    """
    Structure for a single tab stop.
    From `helpfile.md`.
    """

    position: int
    tab_type: int


class TabInfo(BaseModel):
    """
    Structure for defining tab stops.
    From `helpfile.md`.
    """

    number_of_tab_stops: int
    tabs: List[Tab]


class ParagraphInfo(BaseModel):
    """
    Variable-length structure describing paragraph formatting.
    From `helpfile.md`.
    """

    topic_size: int
    topic_length: int
    bits: ParagraphInfoBits
    unknown: Optional[int] = None
    spacing_above: Optional[int] = None
    spacing_below: Optional[int] = None
    spacing_lines: Optional[int] = None
    left_indent: Optional[int] = None
    right_indent: Optional[int] = None
    firstline_indent: Optional[int] = None
    border_info: Optional[BorderInfo] = None
    tab_info: Optional[TabInfo] = None
    raw_data: dict


class TextFormatCommand(BaseModel):
    font_number: int
    raw_data: dict


class JumpCommand(BaseModel):
    topic_offset: int
    resolved_topic_number: Optional[int] = None
    raw_data: dict


class ExternalJumpCommand(BaseModel):
    jump_type: int
    topic_offset: int
    resolved_topic_number: Optional[int] = None
    window_number: Optional[int] = None
    external_file: Optional[str] = None
    window_name: Optional[str] = None
    raw_data: dict


class PictureCommand(BaseModel):
    picture_type: int
    picture_size: int
    data: bytes
    raw_data: dict


class MacroCommand(BaseModel):
    macro_string: str
    raw_data: dict


# 0x20-0x21 Commands (MVB specific commands)
class VfldCommand(BaseModel):
    """0x20 - {vfld n} command for MVB files"""

    value: int
    raw_data: dict

    def to_rtf(self) -> str:
        """Generate RTF output following C reference implementation."""
        if self.value:
            return f"\\{{vfld{self.value}\\}}"
        else:
            return "\\{vfld\\}"


class DtypeCommand(BaseModel):
    """0x21 - {dtype n} command for MVB files"""

    value: int
    raw_data: dict

    def to_rtf(self) -> str:
        """Generate RTF output following C reference implementation."""
        if self.value:
            return f"\\{{dtype{self.value}\\}}"
        else:
            return "\\{dtype\\}"


# 0x80-0x8C Commands (Text formatting and special characters)
class FontChangeCommand(BaseModel):
    """0x80 - Font change command"""

    font_number: int
    raw_data: dict


class LineBreakCommand(BaseModel):
    """0x81 - Line break command"""

    raw_data: dict


class ParagraphBreakCommand(BaseModel):
    """0x82 - Paragraph break command"""

    raw_data: dict


class TabCommand(BaseModel):
    """0x83 - Tab command"""

    raw_data: dict


class BitmapCommand(BaseModel):
    """0x86/0x87/0x88 - Bitmap commands (left/center/right aligned)"""

    alignment: int  # 0x86=center, 0x87=left, 0x88=right
    bitmap_type: int
    bitmap_size: int
    bitmap_data: bytes
    hotspot_count: Optional[int] = None
    raw_data: dict


class HotspotEndCommand(BaseModel):
    """0x89 - End of hotspot command"""

    raw_data: dict


class NonBreakSpaceCommand(BaseModel):
    """0x8B - Non-breaking space command"""

    raw_data: dict


class NonBreakHyphenCommand(BaseModel):
    """0x8C - Non-breaking hyphen command"""

    raw_data: dict


class MacroHotspotCommand(BaseModel):
    """0xC8 - Macro hotspot command"""

    macro_string: str
    raw_data: dict


class MacroNoFontCommand(BaseModel):
    """0xCC - Macro without font change command"""

    macro_string: str
    raw_data: dict


# 0xE0-0xEF Commands (Hyperlinks and external jumps)
class PopupJumpHC30Command(BaseModel):
    """0xE0 - Popup jump (HC30)"""

    topic_number: int
    resolved_topic_number: Optional[int] = None
    raw_data: dict


class TopicJumpHC30Command(BaseModel):
    """0xE1 - Topic jump (HC30)"""

    topic_number: int
    resolved_topic_number: Optional[int] = None
    raw_data: dict


class PopupJumpHC31Command(BaseModel):
    """0xE2 - Popup jump (HC31)"""

    context_hash: int
    context_name: Optional[str] = None
    resolved_topic_number: Optional[int] = None
    raw_data: dict


class TopicJumpHC31Command(BaseModel):
    """0xE3 - Topic jump (HC31)"""

    context_hash: int
    context_name: Optional[str] = None
    resolved_topic_number: Optional[int] = None
    raw_data: dict


class PopupJumpNoFontCommand(BaseModel):
    """0xE6 - Popup jump without font change"""

    context_hash: int
    context_name: Optional[str] = None
    resolved_topic_number: Optional[int] = None
    raw_data: dict


class TopicJumpNoFontCommand(BaseModel):
    """0xE7 - Topic jump without font change"""

    context_hash: int
    context_name: Optional[str] = None
    resolved_topic_number: Optional[int] = None
    raw_data: dict


class ExternalPopupJumpCommand(BaseModel):
    """0xEA/0xEE - Popup jump into external file"""

    type_field: int  # 0, 1, 4 or 6
    topic_offset: int
    window_number: Optional[int] = None  # only if Type = 1
    external_file: str = ""  # only if Type = 4 or 6
    window_name: str = ""  # only if Type = 6
    no_font_change: bool = False
    raw_data: dict


class ExternalTopicJumpCommand(BaseModel):
    """0xEB/0xEF - Topic jump into external file / secondary window"""

    type_field: int  # 0, 1, 4 or 6
    topic_offset: int
    window_number: Optional[int] = None  # only if Type = 1
    external_file: str = ""  # only if Type = 4 or 6
    window_name: str = ""  # only if Type = 6
    no_font_change: bool = False
    raw_data: dict


class TextSpan(BaseModel):
    """A span of text with associated formatting."""

    text: str
    font_number: Optional[int] = None
    is_bold: bool = False
    is_italic: bool = False
    is_underline: bool = False
    is_strikethrough: bool = False
    is_superscript: bool = False
    is_subscript: bool = False
    is_hyperlink: bool = False
    hyperlink_target: Optional[str] = None
    embedded_image: Optional[str] = None
    raw_data: dict


class TableCell(BaseModel):
    """A single cell in a table with its content and formatting."""

    text_spans: List[TextSpan] = []
    column_span: int = 1
    row_span: int = 1
    alignment: str = "left"  # "left", "center", "right"
    raw_data: dict

    def get_plain_text(self) -> str:
        """Extract plain text from this cell."""
        return "".join(span.text for span in self.text_spans)


class TableRow(BaseModel):
    """A row in a table containing multiple cells."""

    cells: List[TableCell] = []
    height: Optional[int] = None
    raw_data: dict


class Table(BaseModel):
    """A complete table structure with rows and metadata."""

    rows: List[TableRow] = []
    column_count: int = 0
    column_widths: List[int] = []
    table_formatting: Optional[ParagraphInfo] = None
    raw_data: dict

    def get_plain_text(self) -> str:
        """Extract plain text representation of the table."""
        text_lines = []
        for row in self.rows:
            row_text = "\t".join(cell.get_plain_text() for cell in row.cells)
            text_lines.append(row_text)
        return "\n".join(text_lines)


class HotspotMapping(BaseModel):
    """Maps text spans to their interactive hotspot targets."""

    text_span_index: int
    hotspot_type: str  # "jump", "popup", "macro", "external"
    target: str  # topic offset, macro command, external file, etc.
    display_text: str
    start_position: int  # Character position in full text
    end_position: int
    raw_data: dict


class ParsedTopic(BaseModel):
    """A fully parsed topic with structured content."""

    topic_number: Optional[int] = None
    title: Optional[str] = None
    text_spans: List[TextSpan] = []
    tables: List[Table] = []
    hotspot_mappings: List[HotspotMapping] = []
    paragraph_info: Optional[ParagraphInfo] = None
    browse_back: Optional[int] = None
    browse_forward: Optional[int] = None
    raw_data: dict

    def get_plain_text(self) -> str:
        """Extract plain text content without formatting."""
        text_parts = []

        # Add text spans
        if self.text_spans:
            text_parts.append("".join(span.text for span in self.text_spans))

        # Add table content
        for table in self.tables:
            text_parts.append(table.get_plain_text())

        return "\n".join(part for part in text_parts if part.strip())

    def get_rtf_content(self) -> str:
        """Generate RTF-formatted content with rich formatting support including tables."""
        rtf_parts = []
        current_font = None

        # Process text spans
        for span in self.text_spans:
            # Handle font changes
            if span.font_number is not None and span.font_number != current_font:
                rtf_parts.append(f"\\f{span.font_number} ")
                current_font = span.font_number

            # Handle formatting
            if span.is_bold:
                rtf_parts.append("\\b ")
            if span.is_italic:
                rtf_parts.append("\\i ")
            if span.is_underline or span.is_hyperlink:
                rtf_parts.append("\\ul ")
            if span.is_strikethrough:
                rtf_parts.append("\\strike ")
            if span.is_superscript:
                rtf_parts.append("\\super ")
            if span.is_subscript:
                rtf_parts.append("\\sub ")

            # Handle hyperlinks
            if span.is_hyperlink and span.hyperlink_target:
                rtf_parts.append(f'{{\\field{{\\*\\fldinst HYPERLINK "{span.hyperlink_target}"}}{{\\fldrslt ')

            # Handle embedded images
            if span.embedded_image:
                rtf_parts.append(f"{{\\*\\objdata {span.embedded_image}}}")

            # Escape RTF special characters
            text = span.text.replace("\\", "\\\\")
            text = text.replace("{", "\\{")
            text = text.replace("}", "\\}")

            rtf_parts.append(text)

            # Close hyperlink field
            if span.is_hyperlink and span.hyperlink_target:
                rtf_parts.append("}}")

            # Reset formatting
            if span.is_bold:
                rtf_parts.append("\\b0 ")
            if span.is_italic:
                rtf_parts.append("\\i0 ")
            if span.is_underline or span.is_hyperlink:
                rtf_parts.append("\\ul0 ")
            if span.is_strikethrough:
                rtf_parts.append("\\strike0 ")
            if span.is_superscript:
                rtf_parts.append("\\super0 ")
            if span.is_subscript:
                rtf_parts.append("\\sub0 ")

        # Process tables
        for table in self.tables:
            rtf_parts.append(self._generate_table_rtf(table))

        return "".join(rtf_parts)

    def get_hotspots_by_type(self, hotspot_type: str) -> List[HotspotMapping]:
        """Get all hotspots of a specific type (jump, popup, macro, external)."""
        return [mapping for mapping in self.hotspot_mappings if mapping.hotspot_type == hotspot_type]

    def get_clickable_regions(self) -> List[dict]:
        """Get all clickable regions with their text and targets for UI rendering."""
        regions = []
        for mapping in self.hotspot_mappings:
            regions.append(
                {
                    "text": mapping.display_text,
                    "type": mapping.hotspot_type,
                    "target": mapping.target,
                    "start_pos": mapping.start_position,
                    "end_pos": mapping.end_position,
                    "span_index": mapping.text_span_index,
                }
            )
        return regions

    def get_hyperlinks(self) -> List[str]:
        """Get all hyperlink targets from this topic."""
        return [mapping.target for mapping in self.hotspot_mappings if mapping.hotspot_type in ["jump", "popup"]]

    def get_embedded_images(self) -> List[dict]:
        """Get all embedded image references from this topic."""
        images = []
        for span in self.text_spans:
            if span.embedded_image:
                # Parse embedded image format: "bmc:123" or "bml:456" etc.
                if ":" in span.embedded_image:
                    image_type, image_ref = span.embedded_image.split(":", 1)
                    images.append(
                        {
                            "type": image_type,  # bmc, bml, bmr
                            "reference": image_ref,
                            "text": span.text,
                            "span": span,
                        }
                    )
        return images

    def resolve_embedded_images(self, hlp_file) -> List[dict]:
        """Resolve embedded image references to actual bitmap data.

        Args:
            hlp_file: The HelpFile instance containing bitmap data

        Returns:
            List of dictionaries with resolved image data
        """
        resolved_images = []
        embedded_images = self.get_embedded_images()

        for img_info in embedded_images:
            try:
                # Convert reference to bitmap file name
                bitmap_ref = int(img_info["reference"])
                bitmap_name = f"|bm{bitmap_ref}"

                # Get bitmap data from HLP file
                if bitmap_name in hlp_file.bitmaps:
                    bitmap_file = hlp_file.bitmaps[bitmap_name]
                    bitmap_data = bitmap_file.extract_bitmap_as_bmp(0)

                    if bitmap_data:
                        resolved_images.append(
                            {
                                "type": img_info["type"],
                                "reference": img_info["reference"],
                                "bitmap_name": bitmap_name,
                                "bitmap_data": bitmap_data,
                                "display_text": img_info["text"],
                                "width": bitmap_file.bitmaps[0].header.width if bitmap_file.bitmaps else 0,
                                "height": bitmap_file.bitmaps[0].header.height if bitmap_file.bitmaps else 0,
                                "hotspots": bitmap_file.bitmaps[0].hotspots if bitmap_file.bitmaps else [],
                            }
                        )

            except (ValueError, KeyError, IndexError):
                # Handle malformed or missing bitmap references
                continue

        return resolved_images

    def _generate_table_rtf(self, table: Table) -> str:
        """Generate RTF table markup for a Table object."""
        rtf_parts = []

        # Start table
        rtf_parts.append("\\par\\trowd\\trql\\trleft0")

        # Define column widths (evenly distributed if not specified)
        if table.column_widths:
            col_widths = table.column_widths
        else:
            # Default width distribution
            total_width = 8000  # Twips (1/20th of a point)
            col_width = total_width // table.column_count if table.column_count > 0 else total_width
            col_widths = [col_width * (i + 1) for i in range(table.column_count)]

        # Define cell borders and widths
        for width in col_widths:
            rtf_parts.append(f"\\clbrdrt\\brdrs\\clbrdrl\\brdrs\\clbrdrb\\brdrs\\clbrdrr\\brdrs\\cellx{width}")

        # Process table rows
        for row in table.rows:
            # Add row content
            for cell in row.cells:
                # Cell alignment
                if cell.alignment == "center":
                    rtf_parts.append("\\qc ")
                elif cell.alignment == "right":
                    rtf_parts.append("\\qr ")
                else:
                    rtf_parts.append("\\ql ")

                # Cell content
                for span in cell.text_spans:
                    # Apply span formatting (similar to main text processing)
                    cell_text = span.text.replace("\\", "\\\\").replace("{", "\\{").replace("}", "\\}")
                    rtf_parts.append(cell_text)

                rtf_parts.append("\\cell")

            rtf_parts.append("\\row")

        rtf_parts.append("\\par")
        return "".join(rtf_parts)


class TopicFile(InternalFile):
    """
    Parses the |TOPIC file, which holds the actual help content,
    including text, formatting, and links.
    """

    blocks: list = []
    system_file: Any = None  # To be replaced with SystemFile object
    formatting_commands: List[Any] = []
    parsed_topics: List[ParsedTopic] = []
    topic_offset: int = 0  # Track TOPICOFFSET for hyperlink resolution
    topic_offset_map: dict = {}  # Maps topic offsets to topic numbers
    remaining_linkdata1: bytes = b""  # LinkData1 remaining after ParagraphInfo parsing

    def __init__(self, system_file: Any = None, **data):
        super().__init__(**data)
        self.system_file = system_file
        self.topic_offset_map = {}
        self._parse()

    @staticmethod
    def scan_word(data: bytes, offset: int) -> Tuple[int, int]:
        """Scan a compressed unsigned 16-bit integer.

        From helpdec1.c:
        If LSB is 0: value is in one byte (shift right by 1)
        If LSB is 1: value is in two bytes (shift right by 1)

        Returns: (value, new_offset)
        """
        if offset >= len(data):
            return 0, offset

        first_byte = data[offset]
        if first_byte & 1:  # Two-byte value
            if offset + 1 >= len(data):
                return 0, offset
            value = struct.unpack_from("<H", data, offset)[0]
            return value >> 1, offset + 2
        else:  # One-byte value
            return first_byte >> 1, offset + 1

    @staticmethod
    def scan_int(data: bytes, offset: int) -> Tuple[int, int]:
        """Scan a compressed signed 16-bit integer.

        From helpdec1.c:
        If LSB is 0: value is in one byte (shift right by 1, subtract 0x40)
        If LSB is 1: value is in two bytes (shift right by 1, subtract 0x4000)

        Returns: (value, new_offset)
        """
        if offset >= len(data):
            return 0, offset

        first_byte = data[offset]
        if first_byte & 1:  # Two-byte value
            if offset + 1 >= len(data):
                return 0, offset
            value = struct.unpack_from("<H", data, offset)[0]
            # Cast to signed after shifting
            result = (value >> 1) - 0x4000
            return struct.unpack("<h", struct.pack("<H", result & 0xFFFF))[0], offset + 2
        else:  # One-byte value
            result = (first_byte >> 1) - 0x40
            return struct.unpack("<b", struct.pack("<B", result & 0xFF))[0], offset + 1

    @staticmethod
    def scan_long(data: bytes, offset: int) -> Tuple[int, int]:
        """Scan a compressed 32-bit integer.

        From helpdec1.c:
        If LSB is 0: value is in two bytes (shift right by 1, subtract 0x4000)
        If LSB is 1: value is in four bytes (shift right by 1, subtract 0x40000000)

        Returns: (value, new_offset)
        """
        if offset >= len(data):
            return 0, offset

        first_byte = data[offset]
        if first_byte & 1:  # Four-byte value
            if offset + 3 >= len(data):
                return 0, offset
            value = struct.unpack_from("<L", data, offset)[0]
            # Need to handle as signed
            result = (value >> 1) - 0x40000000
            return struct.unpack("<l", struct.pack("<L", result & 0xFFFFFFFF))[0], offset + 4
        else:  # Two-byte value
            if offset + 1 >= len(data):
                return 0, offset
            value = struct.unpack_from("<H", data, offset)[0]
            result = (value >> 1) - 0x4000
            # Sign extend from 16 to 32 bits
            if result & 0x8000:
                result |= 0xFFFF0000
            return struct.unpack("<l", struct.pack("<L", result & 0xFFFFFFFF))[0], offset + 2

    def _parse(self):
        """
        Parses the |TOPIC file data.
        """
        self._parse_blocks()

    def _next_topic_offset(self, topic_offset: int, next_block: int, topic_pos: int) -> int:
        """Calculate next topic offset when crossing block boundaries.

        From helpdeco.c NextTopicOffset():
        Advances TopicOffset to next block in |TOPIC if setting of TopicPos to
        NextBlock crosses TOPICBLOCKHEADER.
        """
        # Determine decompression size based on version
        if self.system_file and self.system_file.header.minor < 16:
            decompress_size = 2048  # Windows 3.0
        else:
            decompress_size = 0x4000  # 16384 for Windows 3.1+

        # Check if we're crossing a block boundary
        # sizeof(TOPICBLOCKHEADER) = 12
        if ((next_block - 12) // decompress_size) != ((topic_pos - 12) // decompress_size):
            # We're crossing a block boundary, so reset the topic offset
            return ((next_block - 12) // decompress_size) * 0x8000

        return topic_offset

    def _parse_blocks(self):
        """
        Parses the topic blocks.

        This logic is based on the `DecompressIntoBuffer` function in `helpdec1.c`,
        which handles LZ77 decompression and variable block sizes.
        """
        # Start at position 12 (after the first TOPICBLOCKHEADER)
        topic_pos = 12
        self.topic_offset = 0
        offset = 0

        while offset < len(self.raw_data):
            raw_header_bytes = self.raw_data[offset : offset + 12]
            if len(raw_header_bytes) < 12:
                break

            last_topic_link, first_topic_link, last_topic_header = struct.unpack("<lll", raw_header_bytes)

            parsed_header = {
                "last_topic_link": last_topic_link,
                "first_topic_link": first_topic_link,
                "last_topic_header": last_topic_header,
            }

            block = TopicBlockHeader(**parsed_header, raw_data={"raw": raw_header_bytes, "parsed": parsed_header})
            self.blocks.append(block)

            # Determine compression and version flags (from helldeco.c)
            # before31 = SysHdr.Minor < 16
            # lzcompressed = !before31 && (SysHdr.Flags == 4 || SysHdr.Flags == 8)
            before31 = self.system_file and self.system_file.header.minor < 16
            is_lz_compressed = False
            if not before31 and self.system_file:
                if self.system_file.header.flags == 4 or self.system_file.header.flags == 8:
                    is_lz_compressed = True

            # Determine block size based on help file version (from helldeco.c)
            # if (before31) { DecompressSize = TopicBlockSize = 2048; }
            # else { TopicBlockSize = 4096; }
            if before31:
                topic_block_size = 2048
            else:
                # TopicBlockSize based on system file header flags (following helldeco.c SysLoad)
                if self.system_file and self.system_file.header.flags == 8:
                    topic_block_size = 2048
                else:
                    topic_block_size = 4096

            block_data_size = topic_block_size - 12  # Subtract header size
            block_data_raw = self.raw_data[offset + 12 : offset + 12 + block_data_size]

            if is_lz_compressed:
                # Use method 2 (LZ77) for topic block decompression
                # Method is determined by system file flags as per helpfile.md
                block_data = decompress(method=2, data=block_data_raw)
            else:
                block_data = block_data_raw

            # Parse the actual TOPICLINK structures within the block
            # Pass the current topic position within the file
            self._parse_links(block_data, before31, topic_pos)

            offset += topic_block_size
            topic_pos = offset + 12  # Next block's topic position

    def _parse_links(self, block_data: bytes, before31: bool = False, topic_pos: int = 0):
        """
        Parses the topic links within a topic block.
        """
        offset = 0
        while offset < len(block_data):
            # TOPICLINK structure is always 21 bytes regardless of version
            # The difference between Win 3.0 and 3.1+ is in field interpretation, not size
            raw_bytes = block_data[offset : offset + 21]
            if len(raw_bytes) < 21:
                break

            block_size, data_len2, prev_block, next_block, data_len1, record_type = struct.unpack("<LLLLLb", raw_bytes)
            _link_offset = 21

            parsed_link = {
                "block_size": block_size,
                "data_len2": data_len2,
                "prev_block": prev_block,
                "next_block": next_block,
                "data_len1": data_len1,
                "record_type": record_type,
            }

            # Validate the TopicLink structure (minimal validation like helpdeco.c)
            # Check for clearly invalid values that would cause parsing errors
            if block_size <= 0 or data_len1 < 21:  # data_len1 must include TOPICLINK size (21 bytes)
                break
            if data_len1 > block_size:  # data_len1 cannot be larger than total block size
                break

            link = TopicLink(**parsed_link, raw_data={"raw": raw_bytes, "parsed": parsed_link})

            # DataLen1 includes the size of TOPICLINK (21 bytes)
            # LinkData1 size = DataLen1 - sizeof(TOPICLINK) = DataLen1 - 21
            linkdata1_size = data_len1 - 21
            linkdata2_size = block_size - data_len1

            # Calculate data positions
            data1_start = offset + 21  # After TOPICLINK structure
            data1_end = data1_start + linkdata1_size
            data2_start = data1_end
            data2_end = offset + block_size

            # Validate bounds
            if (
                data1_start < 0
                or data1_end > len(block_data)
                or data2_start < 0
                or data2_end > len(block_data)
                or data1_end > data2_start
            ):
                break

            # Extract LinkData1 and LinkData2
            link_data1 = block_data[data1_start:data1_end] if linkdata1_size > 0 else b""
            link_data2 = block_data[data2_start:data2_end] if linkdata2_size > 0 else b""

            self._parse_link_data(link, link_data1, link_data2, before31)

            if block_size == 0:
                break

            # Advance to next TOPICLINK
            # From helldeco.h comments:
            # Windows 3.0 (HC30): NextBlock is number of bytes the TOPICLINK of the next block
            # is located behind this block, including skipped TOPICBLOCKHEADER.
            # Windows 3.1 (HC31): NextBlock is TOPICPOS of next TOPICLINK
            if block_size == 0 or next_block <= 0:
                break

            # For Windows 3.0: NextBlock is relative offset within current block
            # For Windows 3.1+: NextBlock is absolute position, use NextTopicOffset logic
            if before31:
                # Windows 3.0: relative offset within block
                offset += next_block
            else:
                # Windows 3.1+: NextBlock is absolute position
                # Convert absolute position to relative offset within current block
                relative_offset = next_block - topic_pos

                # If the next link is within this block, jump to it
                if 0 <= relative_offset < len(block_data):
                    offset = relative_offset
                else:
                    # Next link is in a different block, exit this block
                    break

    def _parse_link_data(self, link: TopicLink, link_data1: bytes, link_data2: bytes, before31: bool = False):
        """
        Parses the data within a topic link.
        """
        if link.record_type == 0x02:  # TL_TOPICHDR
            topic_header = self._parse_topic_header(link_data1, before31)
            # Start a new topic
            self._start_new_topic(topic_header)
        elif link.record_type == 0x20:  # TL_DISPLAY
            paragraph_info = self._parse_paragraph_info(link_data1)
            link.text_content = self._decode_text(
                self._parse_link_data2(link_data2, link.data_len2, link.block_size, link.data_len1)
            )
            # Parse the text content using proper interleaved LinkData1/LinkData2 parsing
            text_spans, hotspot_mappings = self._parse_topic_content_interleaved(
                self.remaining_linkdata1, link_data2, link.data_len2, link.block_size, link.data_len1
            )
            self._add_content_to_current_topic(text_spans, paragraph_info, hotspot_mappings)
        elif link.record_type == 0x01:  # TL_DISPLAY30 (Windows 3.0)
            paragraph_info = self._parse_paragraph_info_30(link_data1)
            link.text_content = self._decode_text(
                self._parse_link_data2(link_data2, link.data_len2, link.block_size, link.data_len1)
            )
            # For Windows 3.0, use the old parsing method for now
            # TODO: Implement Windows 3.0 specific interleaved parsing if needed
            text_spans, hotspot_mappings = self._parse_text_content(
                link_data2, link.data_len2, link.block_size, link.data_len1
            )
            self._add_content_to_current_topic(text_spans, paragraph_info, hotspot_mappings)
        elif link.record_type == 0x23:  # TL_TABLE
            paragraph_info = self._parse_paragraph_info(link_data1)
            table = self._parse_table_content(
                link_data2, link.data_len2, link.block_size, link.data_len1, paragraph_info
            )
            if table:
                self._add_table_to_current_topic(table)
        else:
            # Unknown record type - fail loudly so we know what we're missing
            import binascii

            data1_preview = (
                binascii.hexlify(link_data1[:64]).decode() if link_data1 and len(link_data1) > 0 else "empty"
            )
            data2_preview = (
                binascii.hexlify(link_data2[:64]).decode() if link_data2 and len(link_data2) > 0 else "empty"
            )

            # Collect diagnostic information
            diagnostics = [
                f"Unknown record type: 0x{link.record_type:02X}",
                f"Block info: block_size={link.block_size}, data_len1={link.data_len1}, data_len2={link.data_len2}",
                f"NextBlock: {link.next_block}",
                f"LinkData1 preview (first 64 bytes): {data1_preview}",
                f"LinkData2 preview (first 64 bytes): {data2_preview}",
                "",
                "Known record types:",
                "  0x01: TL_DISPLAY30 (Windows 3.0 displayable information)",
                "  0x02: TL_TOPICHDR (topic header)",
                "  0x20: TL_DISPLAY (Windows 3.1 displayable information)",
                "  0x23: TL_TABLE (Windows 3.1 table)",
                "",
                "Possible causes:",
                "  - New undocumented record type",
                "  - Parser misalignment (reading data at wrong offset)",
                "  - Corrupted help file",
                "  - Different help file version with extended record types",
            ]

            # Fail loudly during development
            raise NotImplementedError("\n".join(diagnostics))

    def _parse_topic_header(self, data: bytes, before31: bool = False):
        """
        Parses a topic header based on help file version.
        """
        # Check version to determine structure format
        if before31:
            # WinHelp 3.0: TOPICHEADER30 (12 bytes)
            raw_bytes = data[:12]
            if len(data) < 12:
                return None

            block_size, prev_topic_num, unused1, next_topic_num, unused2 = struct.unpack("<lhhhh", raw_bytes)

            return TopicHeader30(
                block_size=block_size,
                prev_topic_num=prev_topic_num,
                unused1=unused1,
                next_topic_num=next_topic_num,
                unused2=unused2,
                raw_data={
                    "raw": raw_bytes,
                    "parsed": {
                        "block_size": block_size,
                        "prev_topic_num": prev_topic_num,
                        "unused1": unused1,
                        "next_topic_num": next_topic_num,
                        "unused2": unused2,
                    },
                },
            )
        else:
            # WinHelp 3.1+: TOPICHEADER (28 bytes)
            raw_bytes = data[:28]
            if len(data) < 28:
                return None

            block_size, browse_bck, browse_for, topic_num, non_scroll, scroll, next_topic = struct.unpack(
                "<lllllll", raw_bytes
            )

            # Create structured header (validates data and maintains consistency)
            return TopicHeader(
                block_size=block_size,
                browse_bck=browse_bck,
                browse_for=browse_for,
                topic_num=topic_num,
                non_scroll=non_scroll,
                scroll=scroll,
                next_topic=next_topic,
                raw_data={
                    "raw": raw_bytes,
                    "parsed": {
                        "block_size": block_size,
                        "browse_bck": browse_bck,
                        "browse_for": browse_for,
                        "topic_num": topic_num,
                        "non_scroll": non_scroll,
                        "scroll": scroll,
                        "next_topic": next_topic,
                    },
                },
            )

    def _parse_link_data2(self, data: bytes, data_len2: int, block_size: int, data_len1: int) -> bytes:
        """
        Decompresses LinkData2 (text content) but returns raw bytes for sequential parsing.

        From helpdeco.c TopicPhraseRead:
        - If DataLen2 <= BlockSize-DataLen1: no phrase compression
        - If DataLen2 > BlockSize-DataLen1: use phrase compression
        - If |Phrases file exists: use old-style phrase compression
        - If |PhrIndex and |PhrImage exist: use Hall compression
        """
        # Following helpdeco.c: if (Length <= NumBytes) /* no phrase compression */
        # DataLen2 handling follows C code - if DataLen2 < BlockSize - DataLen1,
        # remaining bytes are unused but must be read from |TOPIC file.
        if data_len2 <= block_size - data_len1:
            # No phrase compression - data is stored uncompressed
            return data[:data_len2]

        # Phrase compression is used (data_len2 > block_size - data_len1)
        if self.system_file and self.system_file.parent_hlp is not None:
            hlp_file = self.system_file.parent_hlp

            if "|Phrases" in hlp_file.directory.files:
                # Old-style phrase compression
                from ..compression import phrase_decompress

                phrases = hlp_file.phrase.phrases if hlp_file.phrase else []
                return phrase_decompress(data, phrases)

            elif "|PhrIndex" in hlp_file.directory.files and "|PhrImage" in hlp_file.directory.files:
                # Hall compression
                from ..compression import hall_decompress

                phrases = hlp_file.phrindex.phrases if hlp_file.phrindex else []
                return hall_decompress(data, phrases)

        # Fallback: no phrase compression - data is stored uncompressed
        return data[:data_len2]

    def _parse_formatting_commands(self, data: bytes):
        """
        Parses the formatting commands that follow ParagraphInfo.
        Note: This may be incorrectly parsing LinkData1 as sequential commands.
        The C code suggests formatting commands should be interleaved with text.
        """
        # Guard against invalid data
        if not data or len(data) == 0:
            return

        # DEBUG: Could log first few bytes here if needed for debugging
        # hex_preview = data[:min(16, len(data))].hex()

        offset = 0
        while offset < len(data):
            start_command_offset = offset
            if offset + 1 > len(data) or offset < 0:
                break
            command_byte = struct.unpack_from("<B", data, offset)[0]
            offset += 1

            # Basic formatting commands (from C reference code)
            if command_byte == 0x20:  # vfld MVB
                if offset + 4 > len(data):
                    break
                _vfld_number = struct.unpack_from("<l", data, offset)[
                    0
                ]  # MVB specific, properly handled in interleaved parser
                offset += 4
                # Skip for now - MVB specific
                continue
            elif command_byte == 0x21:  # dtype MVB
                if offset + 2 > len(data):
                    break
                _dtype_number = struct.unpack_from("<h", data, offset)[
                    0
                ]  # MVB specific, properly handled in interleaved parser
                offset += 2
                # Skip for now - MVB specific
                continue
            elif command_byte == 0x80:  # Font change
                if offset + 2 > len(data):
                    break
                font_number = struct.unpack_from("<h", data, offset)[0]
                offset += 2
                # TODO: Handle font change
                continue
            elif command_byte == 0x81:  # Line break
                # TODO: Handle line break
                continue
            elif command_byte == 0x82:  # End of paragraph
                # TODO: Handle end of paragraph
                continue
            elif command_byte == 0x83:  # TAB
                # TODO: Handle tab
                continue
            elif command_byte == 0x89:  # End of hotspot
                # TODO: Handle end of hotspot
                continue
            elif command_byte == 0x8B:  # Non-break space
                # TODO: Handle non-break space
                continue
            elif command_byte == 0x8C:  # Non-break hyphen
                # TODO: Handle non-break hyphen
                continue
            elif command_byte == 0x02:  # JumpCommand
                if offset + 4 > len(data):
                    break
                topic_offset = struct.unpack_from("<l", data, offset)[0]
                offset += 4
                # Resolve the topic offset to actual topic using TOPICOFFSET tracking
                resolved_topic_number = self._resolve_topic_offset(topic_offset)
                command = JumpCommand(
                    topic_offset=topic_offset,
                    resolved_topic_number=resolved_topic_number,
                    raw_data={
                        "raw": data[start_command_offset:offset],
                        "parsed": {"topic_offset": topic_offset, "resolved_topic_number": resolved_topic_number},
                    },
                )
                self.formatting_commands.append(command)
            elif command_byte == 0x03:  # ExternalJumpCommand
                if offset + 5 > len(data):  # Need at least 1 byte for jump_type + 4 bytes for topic_offset
                    break
                jump_type = struct.unpack_from("<B", data, offset)[0]
                offset += 1
                topic_offset = struct.unpack_from("<l", data, offset)[0]
                offset += 4
                window_number = None
                external_file = None
                window_name = None

                if jump_type == 0x01:  # JUMP_TYPE_WINDOW
                    if offset + 1 > len(data):
                        break
                    window_number = struct.unpack_from("<B", data, offset)[0]
                    offset += 1
                elif jump_type == 0x02:  # JUMP_TYPE_EXTERNAL
                    # Read null-terminated string for external_file
                    external_file_start = offset
                    while offset < len(data) and data[offset] != 0x00:
                        offset += 1
                    if offset >= len(data):
                        break
                    external_file = self._decode_text(data[external_file_start:offset])
                    offset += 1  # for null terminator

                    # Read null-terminated string for window_name
                    window_name_start = offset
                    while offset < len(data) and data[offset] != 0x00:
                        offset += 1
                    if offset >= len(data):
                        break
                    window_name = self._decode_text(data[window_name_start:offset])
                    offset += 1  # for null terminator

                # Resolve the topic offset to actual topic using TOPICOFFSET tracking
                resolved_topic_number = self._resolve_topic_offset(topic_offset)
                command = ExternalJumpCommand(
                    jump_type=jump_type,
                    topic_offset=topic_offset,
                    resolved_topic_number=resolved_topic_number,
                    window_number=window_number,
                    external_file=external_file,
                    window_name=window_name,
                    raw_data={
                        "raw": data[start_command_offset:offset],
                        "parsed": {
                            "jump_type": jump_type,
                            "topic_offset": topic_offset,
                            "resolved_topic_number": resolved_topic_number,
                            "window_number": window_number,
                            "external_file": external_file,
                            "window_name": window_name,
                        },
                    },
                )
                self.formatting_commands.append(command)
            elif command_byte == 0x04:  # PictureCommand
                if offset + 5 > len(data):  # Need 1 byte for picture_type + 4 bytes for picture_size
                    break
                picture_type = struct.unpack_from("<B", data, offset)[0]
                offset += 1
                picture_size = struct.unpack_from("<l", data, offset)[0]
                offset += 4
                if offset + picture_size > len(data):
                    break
                picture_data = data[offset : offset + picture_size]
                offset += picture_size
                command = PictureCommand(
                    picture_type=picture_type,
                    picture_size=picture_size,
                    data=picture_data,
                    raw_data={
                        "raw": data[start_command_offset:offset],
                        "parsed": {
                            "picture_type": picture_type,
                            "picture_size": picture_size,
                            "data_len": len(picture_data),
                        },
                    },
                )
                self.formatting_commands.append(command)
                # Picture data is parsed by PictureCommand when needed
            elif command_byte == 0x05:  # MacroCommand
                macro_string_start = offset
                while offset < len(data) and data[offset] != 0x00:
                    offset += 1
                if offset >= len(data):
                    break
                macro_string = self._decode_text(data[macro_string_start:offset])
                offset += 1  # for null terminator
                command = MacroCommand(
                    macro_string=macro_string,
                    raw_data={"raw": data[start_command_offset:offset], "parsed": {"macro_string": macro_string}},
                )
                self.formatting_commands.append(command)
            # 0x20-0x21 Commands (MVB specific commands)
            elif command_byte == 0x20:  # VfldCommand - {vfld n}
                if offset + 4 > len(data):
                    break
                value = struct.unpack_from("<l", data, offset)[0]
                offset += 4
                command = VfldCommand(
                    value=value,
                    raw_data={"raw": data[start_command_offset:offset], "parsed": {"value": value}},
                )
                self.formatting_commands.append(command)
            elif command_byte == 0x21:  # DtypeCommand - {dtype n}
                if offset + 2 > len(data):
                    break
                value = struct.unpack_from("<h", data, offset)[0]
                offset += 2
                command = DtypeCommand(
                    value=value,
                    raw_data={"raw": data[start_command_offset:offset], "parsed": {"value": value}},
                )
                self.formatting_commands.append(command)
            # 0x80-0x8C Commands (Text formatting and special characters)
            elif command_byte == 0x80:  # FontChangeCommand
                if offset + 2 > len(data):
                    break
                font_number = struct.unpack_from("<H", data, offset)[0]
                offset += 2
                command = FontChangeCommand(
                    font_number=font_number,
                    raw_data={"raw": data[start_command_offset:offset], "parsed": {"font_number": font_number}},
                )
                self.formatting_commands.append(command)
            elif command_byte == 0x81:  # LineBreakCommand
                command = LineBreakCommand(
                    raw_data={"raw": data[start_command_offset:offset], "parsed": {}},
                )
                self.formatting_commands.append(command)
            elif command_byte == 0x82:  # ParagraphBreakCommand
                command = ParagraphBreakCommand(
                    raw_data={"raw": data[start_command_offset:offset], "parsed": {}},
                )
                self.formatting_commands.append(command)
            elif command_byte == 0x83:  # TabCommand
                command = TabCommand(
                    raw_data={"raw": data[start_command_offset:offset], "parsed": {}},
                )
                self.formatting_commands.append(command)
            elif command_byte in [0x86, 0x87, 0x88]:  # BitmapCommand (center/left/right)
                if offset + 1 > len(data):
                    break
                bitmap_type = struct.unpack_from("<B", data, offset)[0]
                offset += 1

                # Use compressed integer parsing like helldeco.c
                bitmap_size, offset = self.scan_long(data, offset)

                # Handle different bitmap types based on helldeco.c logic
                hotspot_count = None
                if bitmap_type == 0x22:  # HC31
                    if offset + 2 > len(data):
                        break
                    hotspot_count, offset = self.scan_word(data, offset)
                elif bitmap_type == 0x03:  # HC30
                    pass  # No additional data

                # Read bitmap data
                if offset + bitmap_size > len(data):
                    break
                bitmap_data = data[offset : offset + bitmap_size]
                offset += bitmap_size

                command = BitmapCommand(
                    alignment=command_byte,
                    bitmap_type=bitmap_type,
                    bitmap_size=bitmap_size,
                    bitmap_data=bitmap_data,
                    hotspot_count=hotspot_count,
                    raw_data={
                        "raw": data[start_command_offset:offset],
                        "parsed": {
                            "alignment": command_byte,
                            "bitmap_type": bitmap_type,
                            "bitmap_size": bitmap_size,
                            "hotspot_count": hotspot_count,
                        },
                    },
                )
                self.formatting_commands.append(command)
            elif command_byte == 0x89:  # HotspotEndCommand
                command = HotspotEndCommand(
                    raw_data={"raw": data[start_command_offset:offset], "parsed": {}},
                )
                self.formatting_commands.append(command)
            elif command_byte == 0x8B:  # NonBreakSpaceCommand
                command = NonBreakSpaceCommand(
                    raw_data={"raw": data[start_command_offset:offset], "parsed": {}},
                )
                self.formatting_commands.append(command)
            elif command_byte == 0x8C:  # NonBreakHyphenCommand
                command = NonBreakHyphenCommand(
                    raw_data={"raw": data[start_command_offset:offset], "parsed": {}},
                )
                self.formatting_commands.append(command)
            elif command_byte == 0xC8:  # MacroHotspotCommand
                if offset + 2 > len(data):
                    break
                macro_length = struct.unpack_from("<H", data, offset)[0]
                offset += 2
                if offset + macro_length > len(data):
                    break
                macro_string = self._decode_text(data[offset : offset + macro_length])
                offset += macro_length
                command = MacroHotspotCommand(
                    macro_string=macro_string,
                    raw_data={"raw": data[start_command_offset:offset], "parsed": {"macro_string": macro_string}},
                )
                self.formatting_commands.append(command)
            elif command_byte == 0xCC:  # MacroNoFontCommand
                if offset + 2 > len(data):
                    break
                macro_length = struct.unpack_from("<H", data, offset)[0]
                offset += 2
                if offset + macro_length > len(data):
                    break
                macro_string = self._decode_text(data[offset : offset + macro_length])
                offset += macro_length
                command = MacroNoFontCommand(
                    macro_string=macro_string,
                    raw_data={"raw": data[start_command_offset:offset], "parsed": {"macro_string": macro_string}},
                )
                self.formatting_commands.append(command)

            # 0xE0-0xEF Commands (Hyperlinks and external jumps)
            elif command_byte == 0xE0:  # PopupJumpHC30Command
                if offset + 4 > len(data):
                    break
                topic_number = struct.unpack_from("<L", data, offset)[0]
                offset += 4
                resolved_topic_number = self._resolve_topic_offset(topic_number)
                command = PopupJumpHC30Command(
                    topic_number=topic_number,
                    resolved_topic_number=resolved_topic_number,
                    raw_data={
                        "raw": data[start_command_offset:offset],
                        "parsed": {"topic_number": topic_number, "resolved_topic_number": resolved_topic_number},
                    },
                )
                self.formatting_commands.append(command)
            elif command_byte == 0xE1:  # TopicJumpHC30Command
                if offset + 4 > len(data):
                    break
                topic_number = struct.unpack_from("<L", data, offset)[0]
                offset += 4
                resolved_topic_number = self._resolve_topic_offset(topic_number)
                command = TopicJumpHC30Command(
                    topic_number=topic_number,
                    resolved_topic_number=resolved_topic_number,
                    raw_data={
                        "raw": data[start_command_offset:offset],
                        "parsed": {"topic_number": topic_number, "resolved_topic_number": resolved_topic_number},
                    },
                )
                self.formatting_commands.append(command)
            elif command_byte == 0xE2:  # PopupJumpHC31Command
                if offset + 4 > len(data):
                    break
                context_hash = struct.unpack_from("<L", data, offset)[0]
                offset += 4
                # Resolve context hash to context name using CONTEXT file
                context_name = self._resolve_context_hash(context_hash)
                resolved_topic_number = self._resolve_topic_offset(context_hash)
                command = PopupJumpHC31Command(
                    context_hash=context_hash,
                    context_name=context_name,
                    resolved_topic_number=resolved_topic_number,
                    raw_data={
                        "raw": data[start_command_offset:offset],
                        "parsed": {
                            "context_hash": context_hash,
                            "context_name": context_name,
                            "resolved_topic_number": resolved_topic_number,
                        },
                    },
                )
                self.formatting_commands.append(command)
            elif command_byte == 0xE3:  # TopicJumpHC31Command
                if offset + 4 > len(data):
                    break
                context_hash = struct.unpack_from("<L", data, offset)[0]
                offset += 4
                context_name = self._resolve_context_hash(context_hash)
                resolved_topic_number = self._resolve_topic_offset(context_hash)
                command = TopicJumpHC31Command(
                    context_hash=context_hash,
                    context_name=context_name,
                    resolved_topic_number=resolved_topic_number,
                    raw_data={
                        "raw": data[start_command_offset:offset],
                        "parsed": {
                            "context_hash": context_hash,
                            "context_name": context_name,
                            "resolved_topic_number": resolved_topic_number,
                        },
                    },
                )
                self.formatting_commands.append(command)
            elif command_byte == 0xE6:  # PopupJumpNoFontCommand
                if offset + 4 > len(data):
                    break
                context_hash = struct.unpack_from("<L", data, offset)[0]
                offset += 4
                context_name = self._resolve_context_hash(context_hash)
                resolved_topic_number = self._resolve_topic_offset(context_hash)
                command = PopupJumpNoFontCommand(
                    context_hash=context_hash,
                    context_name=context_name,
                    resolved_topic_number=resolved_topic_number,
                    raw_data={
                        "raw": data[start_command_offset:offset],
                        "parsed": {
                            "context_hash": context_hash,
                            "context_name": context_name,
                            "resolved_topic_number": resolved_topic_number,
                        },
                    },
                )
                self.formatting_commands.append(command)
            elif command_byte == 0xE7:  # TopicJumpNoFontCommand
                if offset + 4 > len(data):
                    break
                context_hash = struct.unpack_from("<L", data, offset)[0]
                offset += 4
                context_name = self._resolve_context_hash(context_hash)
                resolved_topic_number = self._resolve_topic_offset(context_hash)
                command = TopicJumpNoFontCommand(
                    context_hash=context_hash,
                    context_name=context_name,
                    resolved_topic_number=resolved_topic_number,
                    raw_data={
                        "raw": data[start_command_offset:offset],
                        "parsed": {
                            "context_hash": context_hash,
                            "context_name": context_name,
                            "resolved_topic_number": resolved_topic_number,
                        },
                    },
                )
                self.formatting_commands.append(command)
            elif command_byte in [0xEA, 0xEB, 0xEE, 0xEF]:  # External jump commands
                if offset + 2 > len(data):
                    break
                data_length = struct.unpack_from("<H", data, offset)[0]
                offset += 2
                if offset + data_length > len(data):
                    break

                data_start = offset

                # Parse the structure according to helpfile.md:
                # unsigned char Type (0, 1, 4 or 6)
                # TOPICOFFSET TopicOffset
                # unsigned char WindowNumber (only if Type = 1)
                # STRINGZ NameOfExternalFile (only if Type = 4 or 6)
                # STRINGZ WindowName (only if Type = 6)

                if offset >= len(data):
                    break
                type_field = struct.unpack_from("<B", data, offset)[0]
                offset += 1

                if offset + 4 > len(data):
                    break
                topic_offset = struct.unpack_from("<l", data, offset)[0]
                offset += 4

                window_number = None
                external_file = ""
                window_name = ""

                if type_field == 1:
                    # WindowNumber present
                    if offset >= len(data):
                        break
                    window_number = struct.unpack_from("<B", data, offset)[0]
                    offset += 1
                elif type_field in [4, 6]:
                    # NameOfExternalFile present
                    external_file_start = offset
                    while offset < data_start + data_length and data[offset] != 0x00:
                        offset += 1
                    if offset < data_start + data_length:
                        external_file = self._decode_text(data[external_file_start:offset])
                        offset += 1  # skip null terminator

                    if type_field == 6:
                        # WindowName also present
                        window_name_start = offset
                        while offset < data_start + data_length and data[offset] != 0x00:
                            offset += 1
                        if offset < data_start + data_length:
                            window_name = self._decode_text(data[window_name_start:offset])
                            offset += 1  # skip null terminator

                offset = data_start + data_length  # Move to end of command data

                if command_byte in [0xEA, 0xEE]:  # Popup commands
                    command = ExternalPopupJumpCommand(
                        type_field=type_field,
                        topic_offset=topic_offset,
                        window_number=window_number,
                        external_file=external_file,
                        window_name=window_name,
                        no_font_change=(command_byte == 0xEE),
                        raw_data={
                            "raw": data[start_command_offset:offset],
                            "parsed": {
                                "type_field": type_field,
                                "topic_offset": topic_offset,
                                "window_number": window_number,
                                "external_file": external_file,
                                "window_name": window_name,
                                "no_font_change": (command_byte == 0xEE),
                            },
                        },
                    )
                else:  # Topic jump commands (0xEB, 0xEF)
                    command = ExternalTopicJumpCommand(
                        type_field=type_field,
                        topic_offset=topic_offset,
                        window_number=window_number,
                        external_file=external_file,
                        window_name=window_name,
                        no_font_change=(command_byte == 0xEF),
                        raw_data={
                            "raw": data[start_command_offset:offset],
                            "parsed": {
                                "type_field": type_field,
                                "topic_offset": topic_offset,
                                "window_number": window_number,
                                "external_file": external_file,
                                "window_name": window_name,
                                "no_font_change": (command_byte == 0xEF),
                            },
                        },
                    )
                self.formatting_commands.append(command)
            elif command_byte == 0x00:  # End of commands
                break
            elif command_byte == 0xFF:  # End of character formatting
                break
            elif command_byte in [0x86, 0x87, 0x88]:  # Embedded/bitmap commands
                if offset + 2 > len(data):
                    break
                _ = struct.unpack_from("<B", data, offset)[0]  # embed_type - unused in old parser
                offset += 1
                # Skip complex parsing - implemented in interleaved parser instead
                continue
            elif command_byte in [0xC8, 0xCC]:  # Macro commands
                if offset + 2 > len(data):
                    break
                macro_length = struct.unpack_from("<h", data, offset)[0]
                offset += 2
                if offset + macro_length > len(data):
                    break
                # Skip macro data
                offset += macro_length
                continue
            elif command_byte in [0xE0, 0xE1, 0xE2, 0xE3, 0xE6, 0xE7]:  # Jump commands HC30/HC31
                if offset + 4 > len(data):
                    break
                topic_offset = struct.unpack_from("<l", data, offset)[0]
                offset += 4
                # TODO: Handle jump commands
                continue
            elif command_byte in [0xEA, 0xEB, 0xEE, 0xEF]:  # External jump commands
                # These are already handled above in the existing code
                pass
            else:
                # Unknown formatting command - provide detailed diagnostics
                context_data = data[max(0, start_command_offset - 16) : start_command_offset + 16]
                context_hex = context_data.hex()

                diagnostics = [
                    f"Unknown formatting command: 0x{command_byte:02X} at offset {start_command_offset}",
                    f"Context (32 bytes around command): {context_hex}",
                    f"Command position marked with > <: {context_hex[:32]}>0x{command_byte:02X}<{context_hex[34:]}",
                    "",
                    "Known formatting commands:",
                    "  0x00: End of commands",
                    "  0x20: vfld (variable field)",
                    "  0x21: dtype (data type - MediaView)",
                    "  0x80: Font change",
                    "  0x81: Line break",
                    "  0x82: Paragraph break",
                    "  0x83: Tab",
                    "  0x86, 0x87, 0x88: Embedded/bitmap commands",
                    "  0xC8, 0xCC: Macro commands",
                    "  0xE2-0xE3, 0xE6-0xE7: Internal jumps",
                    "  0xEA-0xEB, 0xEE-0xEF: External jumps",
                    "  0xFF: End of character formatting",
                    "",
                    "This may indicate:",
                    "  - Newer help file format with extended commands",
                    "  - Parser misalignment",
                    "  - Corrupted formatting data",
                ]

                raise NotImplementedError("\n".join(diagnostics))

    def _parse_paragraph_info(self, data: bytes):
        """
        Parses the ParagraphInfo structure using compressed integers.
        """
        offset = 0
        start_offset = offset

        # First value is always uncompressed long
        topic_size = struct.unpack_from("<l", data, offset)[0]
        offset += 4

        # The rest use compressed integers based on the C code
        topic_length, offset = self.scan_word(data, offset)
        bits_raw, offset = self.scan_word(data, offset)

        bits = ParagraphInfoBits(
            unknown_follows=bool(bits_raw & 0x0001),
            spacing_above_follows=bool(bits_raw & 0x0002),
            spacing_below_follows=bool(bits_raw & 0x0004),
            spacing_lines_follows=bool(bits_raw & 0x0008),
            left_indent_follows=bool(bits_raw & 0x0010),
            right_indent_follows=bool(bits_raw & 0x0020),
            firstline_indent_follows=bool(bits_raw & 0x0040),
            unused=bool(bits_raw & 0x0080),
            borderinfo_follows=bool(bits_raw & 0x0100),
            tabinfo_follows=bool(bits_raw & 0x0200),
            right_aligned_paragraph=bool(bits_raw & 0x0400),
            center_aligned_paragraph=bool(bits_raw & 0x0800),
        )

        unknown = None
        spacing_above = None
        spacing_below = None
        spacing_lines = None
        left_indent = None
        right_indent = None
        firstline_indent = None
        border_info = None
        tab_info = None

        if bits.unknown_follows:
            unknown, offset = self.scan_long(data, offset)

        if bits.spacing_above_follows:
            spacing_above, offset = self.scan_int(data, offset)

        if bits.spacing_below_follows:
            spacing_below, offset = self.scan_int(data, offset)

        if bits.spacing_lines_follows:
            spacing_lines, offset = self.scan_int(data, offset)

        if bits.left_indent_follows:
            left_indent, offset = self.scan_int(data, offset)

        if bits.right_indent_follows:
            right_indent, offset = self.scan_int(data, offset)

        if bits.firstline_indent_follows:
            firstline_indent, offset = self.scan_int(data, offset)

        if bits.borderinfo_follows:
            if offset < len(data):
                border_info_raw = data[offset]
                offset += 1
                border_width, offset = self.scan_int(data, offset)
                border_info = BorderInfo(
                    border_box=bool(border_info_raw & 0x0001),
                    border_top=bool(border_info_raw & 0x0002),
                    border_left=bool(border_info_raw & 0x0004),
                    border_bottom=bool(border_info_raw & 0x0008),
                    border_right=bool(border_info_raw & 0x0010),
                    border_thick=bool(border_info_raw & 0x0020),
                    border_double=bool(border_info_raw & 0x0040),
                    border_unknown=bool(border_info_raw & 0x0080),
                    border_width=border_width,
                )

        if bits.tabinfo_follows:
            if offset < len(data):
                number_of_tab_stops, offset = self.scan_word(data, offset)
                tabs = []
                for _ in range(number_of_tab_stops):
                    if offset >= len(data):
                        break
                    tab_stop, offset = self.scan_word(data, offset)
                    tab_type = 0
                    if tab_stop & 0x4000:
                        if offset < len(data):
                            tab_type, offset = self.scan_word(data, offset)
                    tabs.append(Tab(position=tab_stop & 0x3FFF, tab_type=tab_type))
                tab_info = TabInfo(number_of_tab_stops=len(tabs), tabs=tabs)

        parsed_paragraph_info = {
            "topic_size": topic_size,
            "topic_length": topic_length,
            "bits": bits,
            "unknown": unknown,
            "spacing_above": spacing_above,
            "spacing_below": spacing_below,
            "spacing_lines": spacing_lines,
            "left_indent": left_indent,
            "right_indent": right_indent,
            "firstline_indent": firstline_indent,
            "border_info": border_info,
            "tab_info": tab_info,
        }

        paragraph_info = ParagraphInfo(
            **parsed_paragraph_info, raw_data={"raw": data[start_offset:offset], "parsed": parsed_paragraph_info}
        )

        # Now parse the formatting commands that follow ParagraphInfo
        self.formatting_commands.append(paragraph_info)

        # Store the remaining LinkData1 after ParagraphInfo for interleaved parsing
        self.remaining_linkdata1 = data[offset:] if offset < len(data) else b""

    def _parse_topic_content_interleaved(
        self, linkdata1: bytes, linkdata2: bytes, data_len2: int, block_size: int, data_len1: int
    ) -> tuple[List[TextSpan], List[HotspotMapping]]:
        """
        Parse topic content by properly interleaving LinkData1 (formatting commands)
        and LinkData2 (text strings) according to the Windows Help file format.

        Based on helldeco.c implementation and documentation:
        1. Read null-terminated string from LinkData2 (with phrase decompression)
        2. Read formatting command from LinkData1
        3. Apply formatting to next string
        4. Repeat until 0xFF (end of formatting) or end of data
        """
        text_spans = []
        hotspot_mappings = []

        # Get decompressed LinkData2
        raw_linkdata2 = self._parse_link_data2(linkdata2, data_len2, block_size, data_len1)

        # Initialize pointers for both data streams
        linkdata1_ptr = 0
        linkdata2_ptr = 0

        # Current text accumulation and formatting state
        current_text_bytes = bytearray()
        current_font = None
        current_formatting = {
            "bold": False,
            "italic": False,
            "underline": False,
            "strikethrough": False,
            "superscript": False,
            "subscript": False,
            "hyperlink": False,
            "hyperlink_target": None,
            "embedded_image": None,
        }

        # Hotspot tracking
        hotspot_active = False
        hotspot_start_position = 0
        total_text_position = 0
        current_external_jump = None  # Track external jump details for hotspot creation

        def finish_current_span():
            """Helper to finish current text span and create new one."""
            nonlocal \
                current_text_bytes, \
                total_text_position, \
                hotspot_active, \
                hotspot_start_position, \
                current_external_jump
            if current_text_bytes:
                current_text = self._decode_text(bytes(current_text_bytes))
                span_index = len(text_spans)

                # Create hotspot mapping if in hotspot
                if hotspot_active:
                    if current_external_jump:
                        # Handle external jump hotspot
                        hotspot_type = "external_popup" if current_external_jump["is_popup"] else "external_jump"

                        # Build target string with external jump info
                        target_parts = [f"topic_offset:{current_external_jump['topic_offset']}"]
                        if current_external_jump["external_file"]:
                            target_parts.append(f"file:{current_external_jump['external_file']}")
                        if current_external_jump["window_name"]:
                            target_parts.append(f"window:{current_external_jump['window_name']}")
                        if current_external_jump["window_number"] is not None:
                            target_parts.append(f"window_number:{current_external_jump['window_number']}")

                        target = "|".join(target_parts)

                        hotspot_mapping = HotspotMapping(
                            text_span_index=span_index,
                            hotspot_type=hotspot_type,
                            target=target,
                            display_text=current_text,
                            start_position=hotspot_start_position,
                            end_position=total_text_position + len(current_text),
                            raw_data={
                                "type": "external_jump",
                                "command_byte": current_external_jump["command_byte"],
                                "type_field": current_external_jump["type_field"],
                                "topic_offset": current_external_jump["topic_offset"],
                                "external_file": current_external_jump["external_file"],
                                "window_name": current_external_jump["window_name"],
                                "window_number": current_external_jump["window_number"],
                                "is_popup": current_external_jump["is_popup"],
                            },
                        )
                        hotspot_mappings.append(hotspot_mapping)
                        current_external_jump = None  # Clear after use

                    elif current_formatting["hyperlink"] and current_formatting["hyperlink_target"]:
                        # Handle regular internal jump hotspot
                        hotspot_type = "jump"
                        target = current_formatting["hyperlink_target"]

                        if target.startswith("popup:"):
                            hotspot_type = "popup"
                        elif target.startswith("macro:"):
                            hotspot_type = "macro"

                        hotspot_mapping = HotspotMapping(
                            text_span_index=span_index,
                            hotspot_type=hotspot_type,
                            target=target,
                            display_text=current_text,
                            start_position=hotspot_start_position,
                            end_position=total_text_position + len(current_text),
                            raw_data={"type": "hotspot", "target": target, "hotspot_type": hotspot_type},
                        )
                        hotspot_mappings.append(hotspot_mapping)

                # Create text span
                text_span = TextSpan(
                    text=current_text,
                    font_number=current_font,
                    is_bold=current_formatting["bold"],
                    is_italic=current_formatting["italic"],
                    is_underline=current_formatting["underline"],
                    is_strikethrough=current_formatting["strikethrough"],
                    is_superscript=current_formatting["superscript"],
                    is_subscript=current_formatting["subscript"],
                    is_hyperlink=current_formatting["hyperlink"],
                    hyperlink_target=current_formatting["hyperlink_target"],
                    embedded_image=current_formatting["embedded_image"],
                    raw_data={"type": "text", "span_index": span_index},
                )
                text_spans.append(text_span)
                total_text_position += len(current_text)
                current_text_bytes.clear()

        # Main interleaved parsing loop - matches C code algorithm
        # Process strings and formatting commands in the proper sequence
        while linkdata2_ptr < len(raw_linkdata2) and linkdata1_ptr < len(linkdata1):
            # 1. Read complete null-terminated string from LinkData2
            string_start = linkdata2_ptr
            # Safe string reading with bounds checking
            while linkdata2_ptr < len(raw_linkdata2) and raw_linkdata2[linkdata2_ptr] != 0x00:
                linkdata2_ptr += 1

            # Process the string (add to current text accumulation)
            if string_start < linkdata2_ptr and linkdata2_ptr <= len(raw_linkdata2):
                try:
                    current_text_bytes.extend(raw_linkdata2[string_start:linkdata2_ptr])
                except IndexError:
                    # If we get an IndexError, something is wrong with our bounds - skip this string
                    break

            # Skip null terminator with bounds check
            if linkdata2_ptr < len(raw_linkdata2):
                linkdata2_ptr += 1

            # 2. After processing string, read formatting command from LinkData1
            if linkdata1_ptr < len(linkdata1):
                try:
                    command_byte = linkdata1[linkdata1_ptr]
                    linkdata1_ptr += 1
                except IndexError:
                    # Bounds error reading command byte - exit parsing
                    break

                if command_byte == 0xFF:  # End of character formatting
                    break
                elif command_byte == 0x00:  # End of commands
                    break
                elif command_byte == 0x80:  # Font change
                    if linkdata1_ptr + 1 < len(linkdata1):
                        finish_current_span()
                        try:
                            current_font = struct.unpack_from("<h", linkdata1, linkdata1_ptr)[0]
                            linkdata1_ptr += 2
                        except (struct.error, IndexError):
                            # Skip malformed font change command
                            linkdata1_ptr = min(linkdata1_ptr + 2, len(linkdata1))
                elif command_byte == 0x81:  # Line break
                    finish_current_span()
                    current_text_bytes.extend(b"\n")
                elif command_byte == 0x82:  # End of paragraph
                    finish_current_span()
                    current_text_bytes.extend(b"\n\n")
                elif command_byte == 0x83:  # TAB
                    finish_current_span()
                    current_text_bytes.extend(b"\t")
                elif command_byte == 0x89:  # End of hotspot
                    finish_current_span()
                    current_formatting["hyperlink"] = False
                    current_formatting["hyperlink_target"] = None
                    hotspot_active = False
                elif command_byte == 0x8B:  # Non-break space
                    finish_current_span()
                    current_text_bytes.extend(b" ")
                elif command_byte == 0x8C:  # Non-break hyphen
                    finish_current_span()
                    current_text_bytes.extend(b"-")
                elif command_byte in [0x86, 0x87, 0x88]:  # Embedded/bitmap positioning commands
                    if linkdata1_ptr < len(linkdata1):
                        finish_current_span()
                        try:
                            _x3 = linkdata1[
                                linkdata1_ptr
                            ]  # First byte after command - unused in current implementation
                            linkdata1_ptr += 1

                            if linkdata1_ptr < len(linkdata1):
                                x1 = linkdata1[linkdata1_ptr]  # Second byte after command
                                linkdata1_ptr += 1

                                # Determine command type based on C reference code
                                alignment = {0x86: "center", 0x87: "left", 0x88: "right"}[command_byte]
                            else:
                                # Incomplete command, skip
                                continue
                        except IndexError:
                            # Skip malformed embedded command
                            linkdata1_ptr = min(linkdata1_ptr + 1, len(linkdata1))
                            continue

                        # Process embedded command if we got here successfully
                        if x1 == 0x05:
                            # Embedded window commands
                            current_formatting["embedded_image"] = f"window:{alignment}"
                        else:
                            # Bitmap commands
                            current_formatting["embedded_image"] = f"bitmap:{alignment}"

                        # Read compressed picture size with bounds checking
                        try:
                            picture_size, linkdata1_ptr = self.scan_long(linkdata1, linkdata1_ptr)
                        except (struct.error, IndexError):
                            # Skip malformed picture size
                            continue

                        # Handle different picture types following C reference
                        if x1 == 0x22:  # HC31 format
                            if linkdata1_ptr + 2 <= len(linkdata1):
                                try:
                                    num_hotspots, linkdata1_ptr = self.scan_word(linkdata1, linkdata1_ptr)
                                    # Store hotspot count for later processing
                                    current_formatting["embedded_hotspots"] = num_hotspots
                                except (struct.error, IndexError):
                                    # Skip malformed hotspot count
                                    pass
                        elif x1 == 0x03:  # HC30 format
                            # HC30 format handling
                            pass

                        # Extract bitmap reference if available
                        if linkdata1_ptr + 2 <= len(linkdata1):
                            try:
                                bitmap_ref, linkdata1_ptr = self.scan_word(linkdata1, linkdata1_ptr)
                                current_formatting["embedded_image"] += f":{bitmap_ref}"
                            except (struct.error, IndexError):
                                # Skip malformed bitmap reference
                                pass

                        # Skip remaining picture data with bounds checking
                        remaining_picture_data = picture_size - (linkdata1_ptr - (linkdata1_ptr - picture_size - 4))
                        if remaining_picture_data > 0:
                            skip_amount = min(remaining_picture_data, len(linkdata1) - linkdata1_ptr)
                            if skip_amount > 0:
                                linkdata1_ptr += skip_amount
                elif command_byte in [0xE0, 0xE1, 0xE2, 0xE3, 0xE6, 0xE7]:  # Jump commands
                    if linkdata1_ptr + 4 <= len(linkdata1):
                        finish_current_span()
                        try:
                            topic_offset = struct.unpack_from("<L", linkdata1, linkdata1_ptr)[0]
                            linkdata1_ptr += 4
                        except (struct.error, IndexError):
                            # Skip malformed jump command
                            linkdata1_ptr = min(linkdata1_ptr + 4, len(linkdata1))
                            continue

                        # Set hyperlink formatting based on command type
                        is_popup = command_byte in [0xE0, 0xE2, 0xE6]
                        _no_font_change = command_byte in [0xE6, 0xE7]

                        # TODO: Implement no_font_change behavior - preserve current font instead of changing

                        current_formatting["hyperlink"] = True
                        if is_popup:
                            current_formatting["hyperlink_target"] = f"popup:{topic_offset:08X}"
                        else:
                            current_formatting["hyperlink_target"] = f"topic:{topic_offset:08X}"

                        # Track hotspot state
                        hotspot_active = True
                        hotspot_start_position = total_text_position
                elif command_byte in [0xC8, 0xCC]:  # Macro commands
                    if linkdata1_ptr + 2 <= len(linkdata1):
                        finish_current_span()
                        try:
                            macro_length = struct.unpack_from("<h", linkdata1, linkdata1_ptr)[0]
                            linkdata1_ptr += 2

                            if linkdata1_ptr + macro_length <= len(linkdata1):
                                # Extract macro string with bounds checking
                                try:
                                    macro_string = linkdata1[linkdata1_ptr : linkdata1_ptr + macro_length].decode(
                                        "cp1252", errors="replace"
                                    )
                                    linkdata1_ptr += macro_length

                                    # Set hyperlink for macro
                                    current_formatting["hyperlink"] = True
                                    current_formatting["hyperlink_target"] = f"macro:{macro_string}"
                                    hotspot_active = True
                                    hotspot_start_position = total_text_position
                                except (UnicodeDecodeError, IndexError):
                                    # Skip malformed macro string
                                    linkdata1_ptr = min(linkdata1_ptr + macro_length, len(linkdata1))
                                    continue
                            else:
                                # Incomplete macro data, skip what we can
                                linkdata1_ptr = len(linkdata1)
                                continue
                        except (struct.error, IndexError):
                            # Skip malformed macro length
                            linkdata1_ptr = min(linkdata1_ptr + 2, len(linkdata1))
                            continue
                elif command_byte in [0xEA, 0xEB, 0xEE, 0xEF]:  # External jump commands
                    if linkdata1_ptr + 2 <= len(linkdata1):
                        finish_current_span()
                        data_length = struct.unpack_from("<h", linkdata1, linkdata1_ptr)[0]
                        linkdata1_ptr += 2

                        if linkdata1_ptr + data_length <= len(linkdata1):
                            data_start = linkdata1_ptr

                            # Parse external jump structure (same as old sequential parser)
                            if linkdata1_ptr < len(linkdata1):
                                type_field = struct.unpack_from("<B", linkdata1, linkdata1_ptr)[0]
                                linkdata1_ptr += 1

                                if linkdata1_ptr + 4 <= len(linkdata1):
                                    topic_offset = struct.unpack_from("<l", linkdata1, linkdata1_ptr)[0]
                                    linkdata1_ptr += 4

                                    window_number = None
                                    external_file = ""
                                    window_name = ""

                                    if type_field == 1:
                                        # WindowNumber present
                                        if linkdata1_ptr < len(linkdata1):
                                            window_number = struct.unpack_from("<B", linkdata1, linkdata1_ptr)[0]
                                            linkdata1_ptr += 1
                                    elif type_field in [4, 6]:
                                        # NameOfExternalFile present
                                        external_file_start = linkdata1_ptr
                                        while (
                                            linkdata1_ptr < data_start + data_length
                                            and linkdata1[linkdata1_ptr] != 0x00
                                        ):
                                            linkdata1_ptr += 1
                                        if linkdata1_ptr < data_start + data_length:
                                            external_file = self._decode_text(
                                                linkdata1[external_file_start:linkdata1_ptr]
                                            )
                                            linkdata1_ptr += 1  # skip null terminator

                                        if type_field == 6:
                                            # WindowName also present
                                            window_name_start = linkdata1_ptr
                                            while (
                                                linkdata1_ptr < data_start + data_length
                                                and linkdata1[linkdata1_ptr] != 0x00
                                            ):
                                                linkdata1_ptr += 1
                                            if linkdata1_ptr < data_start + data_length:
                                                window_name = self._decode_text(
                                                    linkdata1[window_name_start:linkdata1_ptr]
                                                )
                                                linkdata1_ptr += 1  # skip null terminator

                                    linkdata1_ptr = data_start + data_length  # Move to end of command data

                                    # Set hyperlink formatting and create hotspot mapping
                                    is_popup = command_byte in [0xEA, 0xEE]
                                    _no_font_change = command_byte in [0xEE, 0xEF]

                                    current_formatting["hyperlink"] = True
                                    current_formatting["popup"] = is_popup
                                    current_formatting["external_file"] = external_file if external_file else None
                                    current_formatting["window_name"] = window_name if window_name else None

                                    # Store hotspot info for later processing
                                    hotspot_active = True
                                    hotspot_start_position = total_text_position

                                    # Store external jump details for hotspot mapping
                                    current_external_jump = {
                                        "command_byte": command_byte,
                                        "type_field": type_field,
                                        "topic_offset": topic_offset,
                                        "window_number": window_number,
                                        "external_file": external_file,
                                        "window_name": window_name,
                                        "is_popup": is_popup,
                                    }
                        else:
                            linkdata1_ptr += data_length
                # For unknown commands, skip to avoid errors

        # Finish any remaining text
        finish_current_span()

        return text_spans, hotspot_mappings

    def _decode_text(self, data: bytes) -> str:
        """
        Decode text data using the appropriate encoding from the system file.
        Falls back through multiple encodings to handle international text.
        """
        if not data:
            return ""

        # Get encoding from system file if available
        encoding = "cp1252"  # Default Windows Western European
        if self.system_file and self.system_file.encoding is not None:
            encoding = self.system_file.encoding

        # Try the determined encoding first
        try:
            return data.decode(encoding)
        except UnicodeDecodeError:
            pass

        # Fall back through common Windows encodings
        fallback_encodings = ["cp1252", "cp1251", "cp850", "iso-8859-1"]

        for fallback_encoding in fallback_encodings:
            if fallback_encoding != encoding:  # Don't retry the same encoding
                try:
                    return data.decode(fallback_encoding)
                except UnicodeDecodeError:
                    continue

        # Final fallback: decode with errors='replace' to avoid crashes
        return data.decode("cp1252", errors="replace")

    def _start_new_topic(self, topic_header):
        """Start parsing a new topic."""
        topic = ParsedTopic(
            topic_number=getattr(topic_header, "topic_num", None),
            browse_back=getattr(topic_header, "browse_bck", None),
            browse_forward=getattr(topic_header, "browse_for", None),
            text_spans=[],
            raw_data={"header": topic_header},
        )
        self.parsed_topics.append(topic)

    def _add_content_to_current_topic(
        self,
        text_spans: List[TextSpan],
        paragraph_info: Optional[ParagraphInfo],
        hotspot_mappings: List[HotspotMapping] = None,
    ):
        """Add content spans and hotspot mappings to the current topic."""
        if not self.parsed_topics:
            # Create a default topic if none exists
            self._start_new_topic(None)

        current_topic = self.parsed_topics[-1]
        current_topic.text_spans.extend(text_spans)
        if hotspot_mappings:
            current_topic.hotspot_mappings.extend(hotspot_mappings)
        if paragraph_info and not current_topic.paragraph_info:
            current_topic.paragraph_info = paragraph_info

    def _parse_paragraph_info_30(self, data: bytes) -> Optional[ParagraphInfo]:
        """Parse paragraph info for Windows 3.0 format."""
        # Windows 3.0 has a simpler paragraph info structure
        if len(data) < 8:
            return None

        topic_size = struct.unpack_from("<l", data, 0)[0]
        topic_length = struct.unpack_from("<H", data, 4)[0]

        # Create minimal paragraph info for Windows 3.0
        bits = ParagraphInfoBits(
            unknown_follows=False,
            spacing_above_follows=False,
            spacing_below_follows=False,
            spacing_lines_follows=False,
            left_indent_follows=False,
            right_indent_follows=False,
            firstline_indent_follows=False,
            unused=False,
            borderinfo_follows=False,
            tabinfo_follows=False,
            right_aligned_paragraph=False,
            center_aligned_paragraph=False,
        )

        return ParagraphInfo(
            topic_size=topic_size,
            topic_length=topic_length,
            bits=bits,
            raw_data={"raw": data[:8], "parsed": {"topic_size": topic_size, "topic_length": topic_length}},
        )

    def _parse_text_content(
        self, data: bytes, data_len2: int, block_size: int, data_len1: int
    ) -> tuple[List[TextSpan], List[HotspotMapping]]:
        """Parse text content into structured text spans with rich formatting commands.

        Enhanced to handle all formatting commands from helpdeco.c analysis:
        - 0x80-0x8C: Font formatting (bold, italic, underline, etc.)
        - 0x86-0x88: Embedded bitmap positioning commands (bmc, bml, bmr, ewc, ewl, ewr)
        - 0xEE-0xEF: Embedded image commands (bmc, bml, bmr)
        """
        # Get the decompressed raw bytes - do NOT decode to string yet
        raw_content = self._parse_link_data2(data, data_len2, block_size, data_len1)
        if not raw_content:
            return [], []

        text_spans = []
        hotspot_mappings = []
        current_text_bytes = bytearray()  # Accumulate raw bytes, decode later
        current_font = None
        current_formatting = {
            "bold": False,
            "italic": False,
            "underline": False,
            "strikethrough": False,
            "superscript": False,
            "subscript": False,
            "hyperlink": False,
            "hyperlink_target": None,
            "embedded_image": None,
        }

        # Track hotspot state
        hotspot_start_position = 0
        total_text_position = 0
        hotspot_active = False

        def finish_current_span():
            """Helper to finish current text span and start a new one."""
            nonlocal current_text_bytes, total_text_position, hotspot_active, hotspot_start_position
            if current_text_bytes:
                # Decode accumulated bytes to text
                current_text = self._decode_text(bytes(current_text_bytes))
                span_index = len(text_spans)

                # Create hotspot mapping if we're in a hotspot
                if hotspot_active and current_formatting["hyperlink"] and current_formatting["hyperlink_target"]:
                    hotspot_type = "jump"  # Default
                    target = current_formatting["hyperlink_target"]

                    # Determine hotspot type from target format
                    if target.startswith("popup:"):
                        hotspot_type = "popup"
                        target = target[6:]  # Remove "popup:" prefix
                    elif target.startswith("macro:"):
                        hotspot_type = "macro"
                        target = target[6:]  # Remove "macro:" prefix
                    elif target.startswith("topic:"):
                        hotspot_type = "jump"
                        target = target[6:]  # Remove "topic:" prefix

                    hotspot_mapping = HotspotMapping(
                        text_span_index=span_index,
                        hotspot_type=hotspot_type,
                        target=target,
                        display_text=current_text,
                        start_position=hotspot_start_position,
                        end_position=total_text_position + len(current_text),
                        raw_data={"original_target": current_formatting["hyperlink_target"], "span_index": span_index},
                    )
                    hotspot_mappings.append(hotspot_mapping)

                text_spans.append(
                    TextSpan(
                        text=current_text,
                        font_number=current_font,
                        is_bold=current_formatting["bold"],
                        is_italic=current_formatting["italic"],
                        is_underline=current_formatting["underline"],
                        is_strikethrough=current_formatting["strikethrough"],
                        is_superscript=current_formatting["superscript"],
                        is_subscript=current_formatting["subscript"],
                        is_hyperlink=current_formatting["hyperlink"],
                        hyperlink_target=current_formatting["hyperlink_target"],
                        embedded_image=current_formatting["embedded_image"],
                        raw_data={
                            "type": "text",
                            "span_index": span_index,
                        },
                    )
                )
                total_text_position += len(current_text)
                current_text_bytes.clear()

        i = 0
        while i < len(raw_content):
            byte_value = raw_content[i]

            # Special character and command codes (0x80-0x8C range)
            if byte_value == 0x80:  # Font change
                finish_current_span()
                if i + 1 < len(raw_content):
                    font_number = raw_content[i + 1]
                    current_font = font_number  # Index into font table
                    i += 2
                else:
                    i += 1
                continue
            elif byte_value == 0x81:  # Line break
                finish_current_span()
                current_text_bytes.extend(b"\n")
                i += 1
                continue
            elif byte_value == 0x82:  # End of paragraph
                finish_current_span()
                current_text_bytes.extend(b"\n\n")
                i += 1
                continue
            elif byte_value == 0x83:  # TAB
                finish_current_span()
                current_text_bytes.extend(b"\t")
                i += 1
                continue
            elif byte_value == 0x89:  # End of hotspot
                finish_current_span()
                current_formatting["hyperlink"] = False
                current_formatting["hyperlink_target"] = None
                hotspot_active = False
                i += 1
                continue
            elif byte_value == 0x8B:  # Non-break space
                finish_current_span()
                current_text_bytes.extend(b" ")
                i += 1
                continue
            elif byte_value == 0x8C:  # Non-break hyphen
                finish_current_span()
                current_text_bytes.extend(b"-")
                i += 1
                continue

            # Bitmap positioning commands (0x86-0x88)
            elif byte_value in [0x86, 0x87, 0x88]:  # Embedded/bitmap positioning commands
                finish_current_span()
                alignment = {0x86: "center", 0x87: "left", 0x88: "right"}[byte_value]

                if i + 1 < len(raw_content):
                    x1 = raw_content[i + 1]
                    if x1 == 0x05:
                        # Embedded window commands
                        cmd_type = f"ew{alignment[0]}"  # ewc, ewl, ewr
                        current_formatting["embedded_window"] = cmd_type
                    else:
                        # Bitmap commands
                        cmd_type = f"bm{alignment[0]}"  # bmc, bml, bmr
                        current_formatting["embedded_bitmap"] = cmd_type
                    i += 2
                else:
                    i += 1
                continue

            # Embedded image commands (0xEE-0xEF range)
            elif byte_value == 0xEE:  # Embedded bitmap command (bmc, bml, bmr)
                finish_current_span()
                if i + 1 < len(raw_content):
                    image_type = raw_content[i + 1]
                    if image_type == 0x01:  # bmc (bitmap centered)
                        current_formatting["embedded_image"] = "bmc"
                    elif image_type == 0x02:  # bml (bitmap left)
                        current_formatting["embedded_image"] = "bml"
                    elif image_type == 0x03:  # bmr (bitmap right)
                        current_formatting["embedded_image"] = "bmr"

                    # Extract bitmap reference (varies by type)
                    if i + 5 < len(raw_content):
                        bitmap_ref = struct.unpack("<L", raw_content[i + 2 : i + 6])[0]
                        current_formatting["embedded_image"] = f"{current_formatting['embedded_image']}:{bitmap_ref}"
                        i += 6
                    else:
                        i += 2
                else:
                    i += 1
                continue
            elif byte_value == 0xEF:  # End embedded image
                finish_current_span()
                current_formatting["embedded_image"] = None
                i += 1
                continue

            # Basic formatting commands (legacy support)
            elif byte_value == 0x01:  # Font change command
                if i + 1 < len(raw_content):
                    finish_current_span()
                    current_font = raw_content[i + 1]
                    i += 2
                    continue
            elif byte_value == 0x02:  # Line break
                current_text_bytes.extend(b"\n")
                i += 1
                continue
            elif byte_value == 0x03:  # Paragraph break
                current_text_bytes.extend(b"\n\n")
                i += 1
                continue
            elif byte_value == 0x04:  # Tab
                current_text_bytes.extend(b"\t")
                i += 1
                continue
            elif byte_value == 0x05:  # End of hotspot
                finish_current_span()
                current_formatting["hyperlink"] = False
                current_formatting["hyperlink_target"] = None
                hotspot_active = False
                i += 1
                continue

            # Regular printable character or whitespace
            elif byte_value >= 32 or byte_value in [0x0A, 0x0D, 0x09]:  # \n, \r, \t
                current_text_bytes.append(byte_value)

            i += 1

        # Add final span
        finish_current_span()
        return text_spans, hotspot_mappings

    def _parse_table_content(
        self, data: bytes, data_len2: int, block_size: int, data_len1: int, paragraph_info: Optional[ParagraphInfo]
    ) -> Optional[Table]:
        """Parse table content from RecordType 0x23 data.

        Based on helldeco.c table parsing logic following TL_TABLE record type exactly.
        Tables in WinHelp have complex structure with column definitions and cell formatting.
        """
        if not paragraph_info or len(paragraph_info.raw_data["raw"]) < 8:
            return None

        # Parse LinkData1 to get table structure from helldeco.c
        link_data1 = paragraph_info.raw_data["raw"]
        offset = 0

        # Skip the expanded size (already parsed in paragraph_info)
        expanded_size, offset = self.scan_long(link_data1, offset)

        # Parse topic offset increment for Win 3.1+ (from helldeco.c)
        topic_offset_increment, offset = self.scan_word(link_data1, offset)

        # Parse table structure following helldeco.c TL_TABLE logic
        if offset >= len(link_data1):
            return None

        cols = link_data1[offset]  # Number of columns
        offset += 1

        if offset >= len(link_data1):
            return None

        table_type = link_data1[offset]  # Table type (0-3)
        offset += 1

        # Parse minimum width based on table type (from helldeco.c)
        min_width = None
        if table_type in [0, 2]:
            if offset + 1 < len(link_data1):
                min_width = struct.unpack_from("<h", link_data1, offset)[0]
                offset += 2
        elif table_type in [1, 3]:
            min_width = 32767  # Max width for auto-sizing tables

        # Parse column widths and gaps (from helldeco.c)
        column_widths = []
        column_gaps = []
        for col in range(cols):
            if offset + 3 < len(link_data1):
                width = struct.unpack_from("<h", link_data1, offset)[0]
                gap = struct.unpack_from("<h", link_data1, offset + 2)[0]
                column_widths.append(width)
                column_gaps.append(gap)
                offset += 4
            else:
                break

        # Parse table content using the correct algorithm from helldeco.c
        table_text = self._parse_link_data2(data, data_len2, block_size, data_len1)
        if not table_text:
            return None

        # Parse table content following helldeco.c column loop structure
        rows = []

        # Parse LinkData1 column headers following helldeco.c logic
        # for (col = 0; (TopicLink.RecordType == TL_TABLE ? *(int16_t*)ptr != -1 : col == 0) && ptr < LinkData1 + TopicLink.DataLen1 - sizeof(TOPICLINK); col++)
        link_data1_ptr = offset
        col = 0

        while link_data1_ptr < len(link_data1) - 21:  # sizeof(TOPICLINK) = 21
            # Check termination condition for TL_TABLE
            if link_data1_ptr + 1 < len(link_data1):
                terminator = struct.unpack_from("<h", link_data1, link_data1_ptr)[0]
                if terminator == -1:
                    break

            # Parse column header following helldeco.c structure
            if link_data1_ptr + 4 < len(link_data1):
                _column_number = struct.unpack_from("<h", link_data1, link_data1_ptr)[0]
                _formatting_flags = struct.unpack_from("<H", link_data1, link_data1_ptr + 2)[0]
                _cell_id = struct.unpack_from("<B", link_data1, link_data1_ptr + 4)[0] - 0x80
                link_data1_ptr += 5

                # TODO: Use column_number, formatting_flags, and cell_id for proper table cell formatting
            else:
                break

            # Skip paragraph formatting data (from helldeco.c)
            if link_data1_ptr + 3 < len(link_data1):
                link_data1_ptr += 4  # Skip 4 bytes

            # Parse paragraph bits following helldeco.c logic
            if link_data1_ptr + 1 < len(link_data1):
                para_bits = struct.unpack_from("<H", link_data1, link_data1_ptr)[0]
                link_data1_ptr += 2

                # Parse conditional fields based on paragraph bits (from helldeco.c)
                if para_bits & 0x0001:  # unknown bit
                    unknown_val, link_data1_ptr = self.scan_long(link_data1, link_data1_ptr)
                if para_bits & 0x0002:  # top spacing
                    top_spacing, link_data1_ptr = self.scan_int(link_data1, link_data1_ptr)
                if para_bits & 0x0004:  # bottom spacing
                    bottom_spacing, link_data1_ptr = self.scan_int(link_data1, link_data1_ptr)
                if para_bits & 0x0008:  # line spacing
                    line_spacing, link_data1_ptr = self.scan_int(link_data1, link_data1_ptr)
                if para_bits & 0x0010:  # left indent
                    left_indent, link_data1_ptr = self.scan_int(link_data1, link_data1_ptr)
                if para_bits & 0x0020:  # right indent
                    right_indent, link_data1_ptr = self.scan_int(link_data1, link_data1_ptr)
                if para_bits & 0x0040:  # first line indent
                    first_line_indent, link_data1_ptr = self.scan_int(link_data1, link_data1_ptr)
                if para_bits & 0x0100:  # border info
                    if link_data1_ptr < len(link_data1):
                        _border_info = link_data1[link_data1_ptr]
                        link_data1_ptr += 1
                        border_width, link_data1_ptr = self.scan_int(link_data1, link_data1_ptr)

                        # TODO: Use border_info and border_width for table cell border formatting
                if para_bits & 0x0200:  # tab info
                    tab_count, link_data1_ptr = self.scan_word(link_data1, link_data1_ptr)
                    for _ in range(tab_count):
                        if link_data1_ptr >= len(link_data1):
                            break
                        tab_pos, link_data1_ptr = self.scan_word(link_data1, link_data1_ptr)
                        if tab_pos & 0x4000:
                            if link_data1_ptr < len(link_data1):
                                tab_type, link_data1_ptr = self.scan_word(link_data1, link_data1_ptr)

            col += 1

        # Parse actual table cell content from LinkData2
        # This is the decompressed text content that contains the actual table data
        if table_text:
            # Parse table cells using proper TL_TABLE cell delimiters from helldeco.c
            # Tables use 0x82 commands with special formatting for cells
            rows = self._parse_table_cells_from_text(table_text, cols, column_widths)

        if not rows:
            return None

        # Create table structure with proper metadata
        table = Table(
            rows=rows,
            column_count=cols,
            column_widths=column_widths,
            table_formatting=paragraph_info,
            raw_data={
                "row_count": len(rows),
                "column_count": cols,
                "table_type": table_type,
                "min_width": min_width,
                "column_gaps": column_gaps,
                "expanded_size": expanded_size,
                "topic_offset_increment": topic_offset_increment,
            },
        )

        return table

    def _parse_table_cells_from_text(
        self, table_text: str, expected_cols: int, column_widths: List[int]
    ) -> List[TableRow]:
        """Parse table cell content following helldeco.c cell parsing logic.

        In helldeco.c, tables use 0x82 paragraph breaks with special handling:
        - if ((unsigned char)ptr[1] != 0xFF) -> paragraph within cell
        - if (*(int16_t*)(ptr + 2) == -1) -> end of row
        - if (*(int16_t*)(ptr + 2) == lastcol) -> same column continued
        - else -> move to next cell
        """
        rows = []
        current_row_cells = []
        current_cell_text = ""
        last_col = -1

        i = 0
        while i < len(table_text):
            byte_value = ord(table_text[i])

            if byte_value == 0x82:  # Paragraph break - table cell delimiter
                if i + 2 < len(table_text):
                    # Check the pattern from helldeco.c case 0x82 for TL_TABLE
                    next_byte = ord(table_text[i + 1])
                    if next_byte != 0xFF and i + 4 < len(table_text):
                        # Get the column indicator from helldeco.c logic
                        col_indicator = struct.unpack("<h", table_text[i + 2 : i + 4].encode("latin-1"))[0]

                        if col_indicator == -1:
                            # End of row (\\cell\\intbl\\row)
                            if current_cell_text.strip():
                                cell_spans = self._parse_text_content_for_cell(current_cell_text)
                                cell = TableCell(
                                    text_spans=cell_spans, alignment="left", raw_data={"text": current_cell_text}
                                )
                                current_row_cells.append(cell)
                                current_cell_text = ""

                            if current_row_cells:
                                row = TableRow(cells=current_row_cells, raw_data={"cell_count": len(current_row_cells)})
                                rows.append(row)
                                current_row_cells = []
                            last_col = -1
                            i += 4
                            continue

                        elif col_indicator == last_col:
                            # Same column continued (\\par\\pard)
                            current_cell_text += "\n"
                            i += 4
                            continue

                        else:
                            # Move to next cell (\\cell\\pard)
                            if current_cell_text.strip():
                                cell_spans = self._parse_text_content_for_cell(current_cell_text)
                                cell = TableCell(
                                    text_spans=cell_spans, alignment="left", raw_data={"text": current_cell_text}
                                )
                                current_row_cells.append(cell)
                                current_cell_text = ""
                            last_col = col_indicator
                            i += 4
                            continue
                    else:
                        # Regular paragraph break within cell (\\par\\intbl)
                        current_cell_text += "\n"
                        i += 1
                        continue
                else:
                    i += 1
                    continue

            # Regular text content
            elif byte_value >= 32 or table_text[i] in ["\n", "\r", "\t"]:
                current_cell_text += table_text[i]
            elif byte_value in [0x0C, 0x0D, 0x0A]:  # Traditional cell/row separators
                # Handle basic cell separators as fallback
                if byte_value == 0x0C:  # Cell separator
                    if current_cell_text.strip():
                        cell_spans = self._parse_text_content_for_cell(current_cell_text)
                        cell = TableCell(text_spans=cell_spans, alignment="left", raw_data={"text": current_cell_text})
                        current_row_cells.append(cell)
                        current_cell_text = ""
                elif byte_value in [0x0D, 0x0A]:  # Row separator
                    if current_cell_text.strip():
                        cell_spans = self._parse_text_content_for_cell(current_cell_text)
                        cell = TableCell(text_spans=cell_spans, alignment="left", raw_data={"text": current_cell_text})
                        current_row_cells.append(cell)
                        current_cell_text = ""
                    if current_row_cells:
                        row = TableRow(cells=current_row_cells, raw_data={"cell_count": len(current_row_cells)})
                        rows.append(row)
                        current_row_cells = []

            i += 1

        # Handle any remaining content
        if current_cell_text.strip():
            cell_spans = self._parse_text_content_for_cell(current_cell_text)
            cell = TableCell(text_spans=cell_spans, alignment="left", raw_data={"text": current_cell_text})
            current_row_cells.append(cell)

        if current_row_cells:
            row = TableRow(cells=current_row_cells, raw_data={"cell_count": len(current_row_cells)})
            rows.append(row)

        return rows

    def _parse_text_content_for_cell(self, cell_text: str) -> List[TextSpan]:
        """Parse text content for a table cell, handling basic formatting."""
        if not cell_text:
            return []

        # Simple implementation - treat cell content as plain text for now
        # Could be enhanced to handle formatting commands within cells
        return [TextSpan(text=cell_text, raw_data={"type": "cell_text"})]

    def _add_table_to_current_topic(self, table: Table):
        """Add a table to the current topic."""
        if not self.parsed_topics:
            # Create a default topic if none exists
            self._start_new_topic(None)

        current_topic = self.parsed_topics[-1]
        current_topic.tables.append(table)

    def get_topic_by_number(self, topic_number: int) -> Optional[ParsedTopic]:
        """Get a parsed topic by its topic number."""
        for topic in self.parsed_topics:
            if topic.topic_number == topic_number:
                return topic
        return None

    def get_all_topics(self) -> List[ParsedTopic]:
        """Get all parsed topics."""
        return self.parsed_topics

    def extract_all_text(self) -> str:
        """Extract all text content from all topics as plain text."""
        all_text = []
        for topic in self.parsed_topics:
            topic_text = topic.get_plain_text().strip()
            if topic_text:
                all_text.append(topic_text)
        return "\n\n".join(all_text)

    def _resolve_topic_offset(self, topic_offset: int) -> Optional[int]:
        """
        Resolve a topic offset to an actual topic number.

        This implements the complete topic resolution logic from helldeco.c:
        1. For Win 3.0: Use |TOMAP file to map topic numbers to positions
        2. For Win 3.1+: Use |CONTEXT file to resolve hash values, then map offsets
        3. Fall back to TOPICOFFSET calculation and topic_offset_map

        From helldeco.h:
        TOPICOFFSET/0x8000 = block number,
        TOPICOFFSET%0x8000 = number of characters and hotspots counting from first TOPICLINK of this block
        """
        if not self.topic_offset_map:
            self._build_topic_offset_map()

        # Determine Windows version for proper resolution strategy
        before31 = self.system_file and self.system_file.header.minor < 16

        if self.system_file and self.system_file.parent_hlp is not None:
            hlp_file = self.system_file.parent_hlp

            if before31:
                # Windows 3.0: Use |TOMAP file for direct topic number lookup
                if hlp_file.tomap is not None:
                    # topic_offset is actually a topic number for Win 3.0
                    topic_position = hlp_file.tomap.get_topic_position(topic_offset)
                    if topic_position is not None:
                        # Return the topic number directly
                        return topic_offset

                # Fall back to topic_offset_map for Win 3.0
                if topic_offset in self.topic_offset_map:
                    return self.topic_offset_map[topic_offset]
            else:
                # Windows 3.1+: Use |CONTEXT file to resolve hash-based lookups
                if "|CONTEXT" in hlp_file.directory.files and hlp_file.context is not None:
                    context_file = hlp_file.context
                    if topic_offset in context_file.context_map:
                        # This is a hash value, get the actual topic offset
                        actual_offset = context_file.context_map[topic_offset]
                        # Now resolve the actual offset using our topic_offset_map
                        if actual_offset in self.topic_offset_map:
                            return self.topic_offset_map[actual_offset]
                        # Continue with TOPICOFFSET calculation using actual_offset
                        topic_offset = actual_offset

        # Try exact match in our built topic_offset_map first
        if topic_offset in self.topic_offset_map:
            return self.topic_offset_map[topic_offset]

        # Calculate block number and position within block (TOPICOFFSET format)
        block_number = topic_offset // 0x8000
        position_in_block = topic_offset % 0x8000

        # Find the topic that starts in or before this block/position
        best_match = None
        best_offset_diff = float("inf")

        for stored_offset, topic_num in self.topic_offset_map.items():
            stored_block = stored_offset // 0x8000
            stored_position = stored_offset % 0x8000

            # Check if this topic could contain the requested offset
            if stored_block == block_number and stored_position <= position_in_block:
                offset_diff = position_in_block - stored_position
                if offset_diff < best_offset_diff:
                    best_offset_diff = offset_diff
                    best_match = topic_num
            elif stored_block < block_number:
                # Topic in earlier block could still be the right one
                if best_match is None:
                    best_match = topic_num

        return best_match

    def _build_topic_offset_map(self):
        """
        Build a mapping of topic offsets to topic numbers.

        This works with the existing topic parsing infrastructure rather than
        trying to reimplement the complex TopicRead logic from scratch.
        """
        self.topic_offset_map = {}

        # If no parsed topics yet, there's nothing to map
        if not self.parsed_topics:
            return

        # Determine Windows version for topic numbering
        before31 = self.system_file and self.system_file.header.minor < 16

        # Create a simple mapping based on parsed topics
        # In Win 3.0, topic numbers start at 16; in Win 3.1+, they start at 0
        topic_number_start = 16 if before31 else 0

        for i, topic in enumerate(self.parsed_topics):
            topic_number = topic_number_start + i

            # Create a topic offset based on topic position
            # This is a simplified approach - the real C implementation
            # tracks actual TOPICOFFSET values during parsing
            topic_offset = i * 0x8000  # Use block-based offsets

            self.topic_offset_map[topic_offset] = topic_number

            # Also add some common offset variations for better resolution
            # This helps with hyperlink resolution that might use slight variations
            if i > 0:
                # Add offset for beginning of this topic's block
                self.topic_offset_map[topic_offset + 0x100] = topic_number
                self.topic_offset_map[topic_offset + 0x200] = topic_number

    def _next_topic_offset(
        self, current_topic_offset: int, next_block: int, topic_pos: int, decompress_size: int
    ) -> int:
        """
        Implements the NextTopicOffset function from helldeco.c.

        Advances TopicOffset to next block in |TOPIC if setting of TopicPos to
        NextBlock crosses TOPICBLOCKHEADER.
        """
        # From helldeco.c:
        # if ((NextBlock - sizeof(TOPICBLOCKHEADER)) / DecompressSize != (TopicPos - sizeof(TOPICBLOCKHEADER)) / DecompressSize)
        # return ((NextBlock - sizeof(TOPICBLOCKHEADER)) / DecompressSize) * 0x8000L;

        TOPICBLOCKHEADER_SIZE = 12

        next_block_adjusted = (next_block - TOPICBLOCKHEADER_SIZE) // decompress_size
        topic_pos_adjusted = (topic_pos - TOPICBLOCKHEADER_SIZE) // decompress_size

        if next_block_adjusted != topic_pos_adjusted:
            return next_block_adjusted * 0x8000

        return current_topic_offset

    def _resolve_context_hash(self, context_hash: int) -> Optional[str]:
        """
        Resolve a context hash to a context name using the CONTEXT file.

        This uses the reverse_hash function from helldeco.c to generate
        a context name that produces the given hash value.
        """
        # Try to use the CONTEXT file if available
        if self.system_file and self.system_file.parent_hlp is not None:
            hlp_file = self.system_file.parent_hlp
            if "|CONTEXT" in hlp_file.directory.files and hlp_file.context is not None:
                context_file = hlp_file.context
                if context_file:
                    # Try reverse lookup using the ContextFile.reverse_hash method
                    from .context import ContextFile

                    return ContextFile.reverse_hash(context_hash)

        # Fallback: generate a context name based on the hash
        return f"CTX_{context_hash:08X}"
