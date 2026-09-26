"""Parser for the |TOPIC internal file."""

from .base import InternalFile
from pydantic import BaseModel
from typing import List, Any, Literal, Optional, Tuple, Union
import codecs
import struct
from ..compression import decompress
import warnings

# Topic formatting command bytes we have already warned about, so an unknown
# command in a large corpus produces one warning per byte value, not thousands.
_WARNED_TOPIC_COMMANDS: set = set()
_WARNED_RECORD_TYPES: set = set()
_ASCII_LOWER = str.maketrans("ABCDEFGHIJKLMNOPQRSTUVWXYZ", "abcdefghijklmnopqrstuvwxyz")


def safe_unpack_from(format_str: str, data: bytes, offset: int, default_value=None):
    """Safely unpack struct data with bounds checking.

    Args:
        format_str: struct format string (e.g., "<H", "<L")
        data: bytes to unpack from
        offset: offset in data to start from
        default_value: value to return if unpacking fails (None means raise exception)

    Returns:
        tuple: unpacked values or default_value on error

    Raises:
        struct.error: if bounds check fails and no default_value provided
    """
    required_size = struct.calcsize(format_str)
    if offset + required_size > len(data):
        if default_value is not None:
            return default_value if isinstance(default_value, tuple) else (default_value,)
        raise struct.error(f"Not enough data: need {required_size} bytes at offset {offset}, have {len(data) - offset}")

    return struct.unpack_from(format_str, data, offset)


def safe_unpack_single(format_str: str, data: bytes, offset: int, default_value=None):
    """Safely unpack a single value with bounds checking.

    Args:
        format_str: struct format string (e.g., "<H", "<L")
        data: bytes to unpack from
        offset: offset in data to start from
        default_value: value to return if unpacking fails (None means raise exception)

    Returns:
        single value or default_value on error

    Raises:
        struct.error: if bounds check fails and no default_value provided
    """
    result = safe_unpack_from(format_str, data, offset, default_value)
    return result[0] if result else None


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
    is_double_underline: bool = False
    is_small_caps: bool = False
    is_superscript: bool = False
    is_subscript: bool = False
    # Font metrics resolved from the |FONT descriptor referenced by font_number.
    font_half_points: Optional[int] = None
    facename: Optional[str] = None
    fg_rgb: Optional[Tuple[int, int, int]] = None
    bg_rgb: Optional[Tuple[int, int, int]] = None
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
    column_number: Optional[int] = None
    cell_id: Optional[int] = None
    formatting_flags: int = 0
    paragraph_info: Optional[ParagraphInfo] = None
    border_info: Optional[BorderInfo] = None
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


class TopicTextBlock(BaseModel):
    """One display record, retained in its original position within a topic."""

    kind: Literal["text"] = "text"
    text_spans: List[TextSpan] = []
    paragraph_info: Optional[ParagraphInfo] = None
    hotspot_mappings: List[HotspotMapping] = []
    source_offset: Optional[int] = None
    source_end_offset: Optional[int] = None
    source_record_offset: Optional[int] = None


class TopicTableBlock(BaseModel):
    """One table record, retained in its original position within a topic."""

    kind: Literal["table"] = "table"
    table: Table
    source_offset: Optional[int] = None
    source_end_offset: Optional[int] = None
    source_record_offset: Optional[int] = None


TopicContentBlock = Union[TopicTextBlock, TopicTableBlock]


class ParsedTopic(BaseModel):
    """A fully parsed topic with structured content."""

    topic_number: Optional[int] = None
    title: Optional[str] = None
    text_spans: List[TextSpan] = []
    tables: List[Table] = []
    hotspot_mappings: List[HotspotMapping] = []
    content_blocks: List[TopicContentBlock] = []
    # paragraph_info is the FIRST paragraph's formatting (kept for compatibility);
    # paragraph_infos holds every display record's ParagraphInfo in order.
    paragraph_info: Optional[ParagraphInfo] = None
    paragraph_infos: List[ParagraphInfo] = []
    browse_back: Optional[int] = None
    browse_forward: Optional[int] = None
    # Derived cross-reference data (populated during/after parsing).
    topic_offset: Optional[int] = None  # this topic's TOPICOFFSET
    non_scroll_offset: Optional[int] = None  # start of scrolling region, or None
    entry_macros: List[str] = []  # macros run on entry (! footnotes)
    context_names: List[str] = []  # context ids resolving to this topic
    keywords: List[str] = []  # K/A keywords attached to this topic
    annotations: List[str] = []  # user annotation text (from a sibling .ANN file)
    user_note: str = ""  # editable note from the winhlp user-state sidecar
    browse_prev_topic: Optional[int] = None  # resolved browse-sequence neighbours
    browse_next_topic: Optional[int] = None
    raw_data: dict

    def get_plain_text(self) -> str:
        """Extract plain text content without formatting, in reading order."""
        if self.content_blocks:
            parts = []
            for block in self.content_blocks:
                if block.kind == "table":
                    parts.append("\n" + block.table.get_plain_text() + "\n")
                else:
                    parts.append("".join(span.text for span in block.text_spans))
            return "".join(parts)

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


class _TopicReader:
    """Read |TOPIC by TOPICPOS across block boundaries (helpdeco.c TopicRead)."""

    def __init__(self, raw: bytes, block_size: int, decompress_size: int, lz_compressed: bool):
        self.raw = raw
        self.block_size = block_size
        self.decompress_size = decompress_size
        self.lz_compressed = lz_compressed
        self.position = 12
        self._cache: dict = {}

    def _block(self, number: int) -> Optional[bytes]:
        if number not in self._cache:
            start = number * self.block_size
            if number < 0 or start >= len(self.raw):
                return None
            data = self.raw[start + 12 : start + self.block_size]
            if self.lz_compressed:
                data = decompress(method=2, data=data)[: self.decompress_size]
            self._cache = {number: data}  # helpdeco keeps one block buffer too
        return self._cache[number]

    def read(self, position: int, count: int) -> bytes:
        out = bytearray()
        while count > 0:
            number, offset = divmod(position - 12, self.decompress_size)
            data = self._block(number)
            if data is None:
                break
            chunk = data[offset : offset + count]
            out += chunk
            count -= len(chunk)
            position += len(chunk)
            if count > 0:
                position = (number + 1) * self.decompress_size + 12
        self.position = position
        return bytes(out)


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
    remaining_linkdata1: bytes = b""  # LinkData1 remaining after ParagraphInfo parsing

    def __init__(self, system_file: Any = None, **data):
        super().__init__(**data)
        self.system_file = system_file
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
        Walk the TOPICLINK chain through |TOPIC, following helpdeco.c TopicDump.

        Links are read through a virtual TOPICPOS stream (``_TopicReader``, a port
        of helpdeco's TopicRead) so a link, or its LinkData, may span any number
        of topic blocks. HC30 NextBlock is relative to the current TOPICPOS;
        HC31+ NextBlock is the absolute TOPICPOS of the next link.
        """
        header = self.system_file.header if self.system_file else None
        before31 = bool(header and header.minor < 16)
        lz_compressed = bool(header and not before31 and header.flags in (4, 8))
        if before31:
            block_size = decompress_size = 2048
        else:
            block_size = 2048 if header and header.flags == 8 else 4096
            decompress_size = 0x4000

        for start in range(0, len(self.raw_data) - 11, block_size):
            raw = self.raw_data[start : start + 12]
            last_link, first_link, last_header = struct.unpack("<lll", raw)
            parsed = {"last_topic_link": last_link, "first_topic_link": first_link, "last_topic_header": last_header}
            self.blocks.append(TopicBlockHeader(**parsed, raw_data={"raw": raw, "parsed": parsed}))

        reader = _TopicReader(self.raw_data, block_size, decompress_size, lz_compressed)
        self.topic_offset = 0
        topic_pos = 12
        seen = set()
        while topic_pos not in seen:
            seen.add(topic_pos)
            raw_link = reader.read(topic_pos, 21)
            if len(raw_link) < 21:
                break
            block_size_, data_len2, prev_block, next_block, data_len1, record_type = struct.unpack("<lllllB", raw_link)
            if before31:
                if topic_pos + next_block >= len(self.raw_data):
                    break
            elif next_block == 0:
                # TOPICPOS is unsigned in helpdeco, so only 0 stops the walk
                # here; a final NextBlock of -1 is still emitted.
                break
            elif next_block < 0 and record_type == 0x02:
                # HC31+ ends |TOPIC with an empty sentinel topic header.
                break
            if data_len1 < 21 or block_size_ < data_len1:
                break

            link_data1 = reader.read(reader.position, data_len1 - 21) if data_len1 > 21 else b""
            link_data2 = reader.read(reader.position, block_size_ - data_len1) if data_len1 < block_size_ else b""

            parsed_link = {
                "block_size": block_size_,
                "data_len2": data_len2,
                "prev_block": prev_block,
                "next_block": next_block,
                "data_len1": data_len1,
                "record_type": record_type,
                "record_offset": topic_pos,
            }
            link = TopicLink(**parsed_link, raw_data={"raw": raw_link, "parsed": parsed_link})
            if before31 and record_type == 0x02:
                # HC30 addresses topics by the TOPICPOS of their header
                # (helpdeco.c: `if (before31) TopicOffset = TopicPos;`).
                self.topic_offset = topic_pos
            self._parse_link_data(link, link_data1, link_data2, before31, topic_pos)

            if before31:
                topic_pos += next_block
            else:
                if next_block < 0:
                    break
                self.topic_offset = self._next_topic_offset(self.topic_offset, next_block, topic_pos)
                topic_pos = next_block

    def _parse_link_data(
        self,
        link: TopicLink,
        link_data1: bytes,
        link_data2: bytes,
        before31: bool = False,
        record_offset: Optional[int] = None,
    ):
        """
        Parses the data within a topic link.
        """
        if link.record_type == 0x02:  # TL_TOPICHDR
            topic_header = self._parse_topic_header(link_data1, before31)
            # LinkData2 of a topic header holds NUL-separated strings: the first
            # is the topic title, the rest are entry (!) macros (helpdeco.c:3317).
            title = None
            entry_macros = []
            if link_data2:
                raw2 = self._parse_link_data2(link_data2, link.data_len2, link.block_size, link.data_len1)
                strings = raw2.split(b"\x00")
                if strings and strings[0]:
                    title = self._decode_text(strings[0])
                for s in strings[1:]:
                    if s:
                        entry_macros.append(self._decode_text(s))
            self._start_new_topic(topic_header, title=title, entry_macros=entry_macros)
        elif link.record_type == 0x20:  # TL_DISPLAY
            paragraph_info = self._parse_paragraph_info(link_data1)
            source_offset = self.topic_offset
            # A display record advances the running TOPICOFFSET by its character
            # count (helpdeco.c:3359-3362 `x1 = scanword; TopicOffset += x1`).
            if paragraph_info and paragraph_info.topic_length:
                self.topic_offset += paragraph_info.topic_length
            link.text_content = self._decode_text(
                self._parse_link_data2(link_data2, link.data_len2, link.block_size, link.data_len1)
            )
            # Parse the text content using proper interleaved LinkData1/LinkData2 parsing
            text_spans, hotspot_mappings = self._parse_topic_content_interleaved(
                self.remaining_linkdata1, link_data2, link.data_len2, link.block_size, link.data_len1
            )
            self._add_content_to_current_topic(
                text_spans,
                paragraph_info,
                hotspot_mappings,
                source_offset,
                self.topic_offset,
                record_offset,
            )
        elif link.record_type == 0x01:  # TL_DISPLAY30 (Windows 3.0)
            # Same layout as TL_DISPLAY minus the TopicLength word, so it goes
            # through the same command/text interleaving (helpdeco.c:3352-3362).
            paragraph_info = self._parse_paragraph_info(link_data1, has_topic_length=False)
            link.text_content = self._decode_text(
                self._parse_link_data2(link_data2, link.data_len2, link.block_size, link.data_len1)
            )
            text_spans, hotspot_mappings = self._parse_topic_content_interleaved(
                self.remaining_linkdata1, link_data2, link.data_len2, link.block_size, link.data_len1
            )
            self._add_content_to_current_topic(
                text_spans,
                paragraph_info,
                hotspot_mappings,
                source_record_offset=record_offset,
            )
        elif link.record_type == 0x23:  # TL_TABLE
            source_offset = self.topic_offset
            table = self._parse_table_record(link, link_data1, link_data2)
            if table:
                self._add_table_to_current_topic(table, source_offset, self.topic_offset, record_offset)
        else:
            # Unknown record type. _parse_links only dispatches 0x01/0x02/0x20/0x23
            # so this is normally unreachable, but degrade gracefully rather than
            # crash the whole file if a new/undocumented type ever reaches here.
            if link.record_type not in _WARNED_RECORD_TYPES:
                _WARNED_RECORD_TYPES.add(link.record_type)
                warnings.warn(f"Skipping unknown TOPICLINK record type 0x{link.record_type:02X}")

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
        - If |PhrIndex and |PhrImage exist: use Hall compression
        - Else if |Phrases exists: use old-style phrase compression
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

            # helpdeco's PhraseLoad prefers Hall compression: some files carry a
            # stale |Phrases next to the |PhrIndex/|PhrImage pair actually used.
            if "|PhrIndex" in hlp_file.directory.files and "|PhrImage" in hlp_file.directory.files:
                from ..compression import hall_decompress

                phrases = hlp_file.phrindex.phrase_bytes if hlp_file.phrindex else []
                return hall_decompress(data, phrases, self.system_file.encoding)

            if "|Phrases" in hlp_file.directory.files:
                from ..compression import phrase_decompress

                phrases = hlp_file.phrase.phrase_bytes if hlp_file.phrase else []
                return phrase_decompress(data, phrases, self.system_file.encoding)

        # Fallback: no phrase compression - data is stored uncompressed
        return data[:data_len2]

    def _parse_paragraph_info(self, data: bytes, has_topic_length: bool = True):
        """
        Parses the ParagraphInfo structure using compressed integers.

        TL_DISPLAY30 records have no TopicLength word (``has_topic_length=False``).
        """
        offset = 0
        start_offset = offset

        # TopicSize is a COMPRESSED long and TopicLength a compressed word
        # (helpdeco.c: `scanlong(&ptr); x1 = scanword(&ptr);`). Reading TopicSize
        # as a raw 4-byte long over-consumes and desyncs the whole command stream.
        topic_size, offset = self.scan_long(data, offset)
        topic_length = 0
        if has_topic_length:
            topic_length, offset = self.scan_word(data, offset)

        fields, offset = self._parse_paragraph_attributes(data, offset)
        parsed_paragraph_info = {"topic_size": topic_size, "topic_length": topic_length, **fields}

        paragraph_info = ParagraphInfo(
            **parsed_paragraph_info, raw_data={"raw": data[start_offset:offset], "parsed": parsed_paragraph_info}
        )

        # Now parse the formatting commands that follow ParagraphInfo
        self.formatting_commands.append(paragraph_info)

        # Store the remaining LinkData1 after ParagraphInfo for interleaved parsing
        self.remaining_linkdata1 = data[offset:] if offset < len(data) else b""

        return paragraph_info

    def _parse_paragraph_attributes(self, data: bytes, offset: int) -> tuple[dict, int]:
        """Parse the paragraph attributes shared by display records and table columns."""
        # Four raw bytes precede the attribute bits (helpdeco.c `ptr += 4`):
        #   unsigned char unknownUnsignedChar
        #   char          unknownBiasedChar
        #   unsigned short id
        offset += 4

        # The paragraph attribute bits are a RAW uint16, not a compressed word.
        bits_raw = struct.unpack_from("<H", data, offset)[0] if offset + 2 <= len(data) else 0
        offset += 2

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
                # BorderWidth is a raw signed short (helpdeco.c: `ptr += 2`), not
                # a compressed short.
                border_width = struct.unpack_from("<h", data, offset)[0] if offset + 2 <= len(data) else 0
                offset += 2
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
                # NumberOfTabStops is a compressed *signed* short (helpdeco.c uses
                # scanint here). Reading it as an unsigned word inflates the count
                # (e.g. byte 0x82 -> 65 instead of 1), so the tab loop devours the
                # following character-formatting commands and no text is emitted.
                number_of_tab_stops, offset = self.scan_int(data, offset)
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

        return {
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
        }, offset

    def _parse_topic_content_interleaved(
        self,
        linkdata1: bytes,
        linkdata2: bytes,
        data_len2: int,
        block_size: int,
        data_len1: int,
        raw_text: Optional[bytes] = None,
        start_p2: int = 0,
        initial_font: Optional[int] = None,
        table_mode: bool = False,
    ) -> tuple[List[TextSpan], List[HotspotMapping]]:
        """
        Parse topic content by interleaving LinkData1 (formatting commands) with
        LinkData2 (phrase-decompressed text), following helpdeco.c's TopicDump loop
        (doc/ref/helpdeco.c lines ~3459-3797):

            do { output *str } while (*str++);   # emit one NUL-terminated segment
            switch (*ptr) { ...advance ptr per command... }

        The loop runs until a 0xFF command (end of character formatting) or until
        the command stream is exhausted. Unknown command bytes advance the pointer
        by one (helpdeco's `default: ptr++`) rather than aborting, so a single
        unrecognized byte can no longer swallow the rest of a record.
        """
        text_spans: List[TextSpan] = []
        hotspot_mappings: List[HotspotMapping] = []

        if raw_text is None:
            raw_text = self._parse_link_data2(linkdata2, data_len2, block_size, data_len1)
        raw_linkdata2 = raw_text

        n1 = len(linkdata1)
        n2 = len(raw_linkdata2)
        p1 = 0  # pointer into linkdata1 (formatting commands)
        p2 = start_p2  # pointer into raw_linkdata2 (text)

        current_text = bytearray()
        current_font: Optional[int] = initial_font
        encoding = getattr(self.system_file, "encoding", None) or "cp1252"
        decoder = codecs.getincrementaldecoder(encoding)(errors="replace")
        fmt = {
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
        hotspot_active = False
        hotspot_start_position = 0
        total_text_position = 0
        current_external_jump = None

        def flush_span():
            """Emit the accumulated text as a TextSpan (and a hotspot mapping)."""
            nonlocal total_text_position, hotspot_active, current_external_jump
            if not current_text:
                return
            # Incremental, so a double-byte character split by a formatting
            # command is completed from the next segment.
            text = decoder.decode(bytes(current_text))
            if not text:
                current_text.clear()
                return
            if self._font_attributes(current_font).get("small_caps"):
                # The compiler stores small-caps text uppercased; helpdeco
                # restores the authored case with strlwr() (ASCII only).
                text = text.translate(_ASCII_LOWER)
            span_index = len(text_spans)

            if hotspot_active and current_external_jump:
                is_popup = current_external_jump["is_popup"]
                target_parts = [f"context_hash:{current_external_jump['topic_offset']}"]
                if current_external_jump["external_file"]:
                    target_parts.append(f"file:{current_external_jump['external_file']}")
                if current_external_jump["window_name"]:
                    target_parts.append(f"window:{current_external_jump['window_name']}")
                if current_external_jump["window_number"] is not None:
                    target_parts.append(f"window_number:{current_external_jump['window_number']}")
                hotspot_mappings.append(
                    HotspotMapping(
                        text_span_index=span_index,
                        hotspot_type="external_popup" if is_popup else "external_jump",
                        target="|".join(target_parts),
                        display_text=text,
                        start_position=hotspot_start_position,
                        end_position=total_text_position + len(text),
                        raw_data={"type": "external_jump", **current_external_jump},
                    )
                )
                current_external_jump = None
            elif hotspot_active and fmt["hyperlink"] and fmt["hyperlink_target"]:
                target = fmt["hyperlink_target"]
                hotspot_type = "jump"
                if target.startswith("popup:"):
                    hotspot_type = "popup"
                elif target.startswith("macro:"):
                    hotspot_type = "macro"
                hotspot_mappings.append(
                    HotspotMapping(
                        text_span_index=span_index,
                        hotspot_type=hotspot_type,
                        target=target,
                        display_text=text,
                        start_position=hotspot_start_position,
                        end_position=total_text_position + len(text),
                        raw_data={"type": "hotspot", "target": target, "hotspot_type": hotspot_type},
                    )
                )

            # Character emphasis (bold/italic/...) is a property of the |FONT
            # descriptor referenced by the active font, not of the command stream.
            attrs = self._font_attributes(current_font)
            text_spans.append(
                TextSpan(
                    text=text,
                    font_number=current_font,
                    is_bold=attrs.get("bold", fmt["bold"]),
                    is_italic=attrs.get("italic", fmt["italic"]),
                    is_underline=attrs.get("underline", fmt["underline"]),
                    is_strikethrough=attrs.get("strikethrough", fmt["strikethrough"]),
                    is_double_underline=attrs.get("double_underline", False),
                    is_small_caps=attrs.get("small_caps", False),
                    is_superscript=fmt["superscript"],
                    is_subscript=fmt["subscript"],
                    font_half_points=attrs.get("half_points"),
                    facename=attrs.get("facename"),
                    fg_rgb=attrs.get("fg_rgb"),
                    bg_rgb=attrs.get("bg_rgb"),
                    is_hyperlink=fmt["hyperlink"],
                    hyperlink_target=fmt["hyperlink_target"],
                    embedded_image=fmt["embedded_image"],
                    raw_data={"type": "text", "span_index": span_index},
                )
            )
            total_text_position += len(text)
            current_text.clear()

        def read_text_segment():
            """Accumulate one NUL-terminated text segment (C: do{}while(*str++))."""
            nonlocal p2
            while p2 < n2:
                c = raw_linkdata2[p2]
                p2 += 1
                if c == 0:
                    break
                current_text.append(c)

        def append_embedded_object(marker: str):
            """Retain a picture/window command even when no text follows it."""
            attrs = self._font_attributes(current_font)
            text_spans.append(
                TextSpan(
                    text="",
                    font_number=current_font,
                    is_bold=attrs.get("bold", fmt["bold"]),
                    is_italic=attrs.get("italic", fmt["italic"]),
                    is_underline=attrs.get("underline", fmt["underline"]),
                    is_strikethrough=attrs.get("strikethrough", fmt["strikethrough"]),
                    is_double_underline=attrs.get("double_underline", False),
                    is_small_caps=attrs.get("small_caps", False),
                    is_superscript=fmt["superscript"],
                    is_subscript=fmt["subscript"],
                    font_half_points=attrs.get("half_points"),
                    facename=attrs.get("facename"),
                    fg_rgb=attrs.get("fg_rgb"),
                    bg_rgb=attrs.get("bg_rgb"),
                    is_hyperlink=fmt["hyperlink"],
                    hyperlink_target=fmt["hyperlink_target"],
                    embedded_image=marker,
                    raw_data={"type": "embedded_object", "span_index": len(text_spans)},
                )
            )

        # Guard against pathological/corrupt streams that fail to reach a 0xFF.
        max_iterations = n1 + n2 + 16
        iterations = 0

        while iterations < max_iterations:
            iterations += 1

            # 1. Emit the next text segment before processing its formatting command.
            read_text_segment()

            # 2. Read the following formatting command from LinkData1.
            if p1 >= n1:
                break
            command = linkdata1[p1]

            if command == 0xFF:  # end of character formatting
                p1 += 1
                break
            elif command == 0x80:  # font change
                flush_span()
                if p1 + 3 <= n1:
                    current_font = struct.unpack_from("<h", linkdata1, p1 + 1)[0]
                p1 += 3
            elif command == 0x81:  # line break
                current_text.extend(b"\n")
                p1 += 1
            elif command == 0x82:  # end of paragraph
                # In a table, 0x82 followed by 0xFF ends the cell paragraph; the
                # caller decides between next paragraph, next cell or end of row.
                if not (table_mode and p1 + 1 < n1 and linkdata1[p1 + 1] == 0xFF):
                    current_text.extend(b"\n\n")
                p1 += 1
            elif command == 0x83:  # tab
                current_text.extend(b"\t")
                p1 += 1
            elif command == 0x8B:  # non-break space
                current_text.extend(b" ")
                p1 += 1
            elif command == 0x8C:  # non-break hyphen
                current_text.extend(b"-")
                p1 += 1
            elif command == 0x20:  # vfld (MVB), long argument
                p1 += 5
            elif command == 0x21:  # dtype (MVB), short argument
                p1 += 3
            elif command in (0x86, 0x87, 0x88):  # embedded picture/window
                flush_span()
                alignment = {0x86: "inline", 0x87: "left", 0x88: "right"}[command]
                x1 = linkdata1[p1 + 1] if p1 + 2 <= n1 else 0
                p1 += 2
                picture_size, p1 = self.scan_long(linkdata1, p1)
                if x1 == 0x22:  # HC31: number of hotspots precedes the union
                    _num_hotspots, p1 = self.scan_word(linkdata1, p1)
                marker = f"{'window' if x1 == 0x05 else 'bitmap'}:{alignment}"
                if x1 in (0x03, 0x22) and p1 + 4 <= n1:
                    picture_is_embedded = struct.unpack_from("<H", linkdata1, p1)[0]
                    if picture_is_embedded == 0:
                        picture_number = struct.unpack_from("<H", linkdata1, p1 + 2)[0]
                        marker += f":{picture_number}"
                elif x1 == 0x05 and p1 + 6 < n1:
                    # Embedded window (ewc/ewl/ewr): union is 3 shorts then a
                    # STRINGZ "DLLName,WindowClass,Param" (helpdeco.c:3634). For
                    # MediaView pictures Param names the resource (e.g. a bitmap).
                    end = linkdata1.find(b"\x00", p1 + 6)
                    if end == -1:
                        end = min(p1 + 6 + 255, n1)
                    embedded = self._decode_text(linkdata1[p1 + 6 : end])
                    if embedded:
                        marker += f":{embedded}"
                append_embedded_object(marker)
                p1 += max(0, picture_size)  # skip the picture union
            elif command == 0x89:  # end of hotspot
                flush_span()
                fmt["hyperlink"] = False
                fmt["hyperlink_target"] = None
                fmt["embedded_image"] = None
                hotspot_active = False
                p1 += 1
            elif command in (0xC8, 0xCC):  # macro hotspot
                flush_span()
                if p1 + 3 <= n1:
                    macro_length = struct.unpack_from("<h", linkdata1, p1 + 1)[0]
                    macro = self._decode_text(linkdata1[p1 + 3 : p1 + 3 + max(0, macro_length)])
                    fmt["hyperlink"] = True
                    fmt["hyperlink_target"] = f"macro:{macro}"
                    hotspot_active = True
                    hotspot_start_position = total_text_position
                    p1 += macro_length + 3
                else:
                    p1 = n1
            elif command in (0xE0, 0xE1, 0xE2, 0xE3, 0xE6, 0xE7):  # jumps / popups
                flush_span()
                target = struct.unpack_from("<l", linkdata1, p1 + 1)[0] if p1 + 5 <= n1 else 0
                is_popup = command in (0xE0, 0xE2, 0xE6)
                kind = "popup" if is_popup else "topic"
                if command in (0xE0, 0xE1):  # HC30: argument is a topic number
                    fmt["hyperlink_target"] = f"{kind}:TOPIC{target}"
                else:  # HC31: argument is a topic offset
                    fmt["hyperlink_target"] = f"{kind}:{target & 0xFFFFFFFF:08X}"
                fmt["hyperlink"] = True
                hotspot_active = True
                hotspot_start_position = total_text_position
                p1 += 5
            elif command in (0xEA, 0xEB, 0xEE, 0xEF):  # jump into external file / window
                flush_span()
                data_length = struct.unpack_from("<h", linkdata1, p1 + 1)[0] if p1 + 3 <= n1 else 0
                data_start = p1 + 3
                data_end = min(data_start + max(0, data_length), n1)
                type_field = linkdata1[data_start] if data_start < n1 else 0
                topic_offset = struct.unpack_from("<l", linkdata1, data_start + 1)[0] if data_start + 5 <= n1 else 0
                window_number = None
                external_file = ""
                window_name = ""
                q = data_start + 5
                if type_field == 1:
                    if q < data_end:
                        window_number = linkdata1[q]
                elif type_field in (4, 6):
                    start = q
                    while q < data_end and linkdata1[q] != 0x00:
                        q += 1
                    external_file = self._decode_text(linkdata1[start:q])
                    q += 1
                    if type_field == 6:
                        # Type 6 stores WindowName before NameOfExternalFile
                        # (helpdeco.c's label3 and FirstPass).
                        window_name = external_file
                        start = q
                        while q < data_end and linkdata1[q] != 0x00:
                            q += 1
                        external_file = self._decode_text(linkdata1[start:q])
                is_popup = command in (0xEA, 0xEE)
                fmt["hyperlink"] = True
                hotspot_active = True
                hotspot_start_position = total_text_position
                current_external_jump = {
                    "command_byte": command,
                    "type_field": type_field,
                    "topic_offset": topic_offset,
                    "external_file": external_file or None,
                    "window_name": window_name or None,
                    "window_number": window_number,
                    "is_popup": is_popup,
                }
                p1 = data_end
            elif not any(linkdata1[p1:]):
                # Some compilers omit the 0xFF terminator and pad with NULs.
                break
            else:
                # Unknown command byte: advance by one, matching helpdeco's
                # `default: ptr++;`. Warn once per byte value so gaps are visible.
                if command not in _WARNED_TOPIC_COMMANDS:
                    _WARNED_TOPIC_COMMANDS.add(command)
                    warnings.warn(f"Unknown topic formatting command 0x{command:02X}; skipping one byte")
                p1 += 1

        # Emit any text left in the buffer once the command stream ends,
        # including a dangling lead byte.
        flush_span()
        tail = decoder.decode(b"", final=True)
        if tail and text_spans:
            text_spans[-1].text += tail

        self._interleave_state = (p1, p2, current_font)
        return text_spans, hotspot_mappings

    def _font_attributes(self, font_index: Optional[int]) -> dict:
        """Look up character attributes for a font index via the |FONT file.

        The |FONT file is parsed before |TOPIC, so it is reachable through the
        parent HelpFile. Returns {} when unavailable so parsing degrades cleanly.
        """
        if font_index is None:
            return {}
        parent = getattr(self.system_file, "parent_hlp", None) if self.system_file else None
        font_file = getattr(parent, "font", None) if parent else None
        if font_file is None:
            return {}
        return font_file.get_font_attributes(font_index)

    def _decode_text(self, data: bytes) -> str:
        """
        Decode text data using the appropriate encoding from the system file.
        """
        if not data:
            return ""

        # Get encoding from system file if available
        encoding = "cp1252"  # Default Windows Western European
        if self.system_file and self.system_file.encoding is not None:
            encoding = self.system_file.encoding

        # Stay in the file's code page: switching a whole segment to another
        # code page because of one stray byte garbles it ("Même" -> "Mкme").
        return data.decode(encoding, errors="replace")

    def _start_new_topic(self, topic_header, title=None, entry_macros=None):
        """Start parsing a new topic."""
        # NonScroll points at the first fixed record and Scroll at the first
        # scrolling record. If NonScroll is absent, the topic has no fixed
        # region at all; using Scroll unconditionally pins ordinary topics.
        has_non_scroll = getattr(topic_header, "non_scroll", -1) not in (-1, 0xFFFFFFFF)
        non_scroll = getattr(topic_header, "scroll", None) if has_non_scroll else None
        topic = ParsedTopic(
            topic_number=getattr(topic_header, "topic_num", None),
            title=title,
            entry_macros=entry_macros or [],
            browse_back=getattr(topic_header, "browse_bck", None),
            browse_forward=getattr(topic_header, "browse_for", None),
            topic_offset=self.topic_offset,
            non_scroll_offset=non_scroll,
            text_spans=[],
            raw_data={"header": topic_header},
        )
        self.parsed_topics.append(topic)

    def _add_content_to_current_topic(
        self,
        text_spans: List[TextSpan],
        paragraph_info: Optional[ParagraphInfo],
        hotspot_mappings: List[HotspotMapping] = None,
        source_offset: Optional[int] = None,
        source_end_offset: Optional[int] = None,
        source_record_offset: Optional[int] = None,
    ):
        """Add content spans and hotspot mappings to the current topic."""
        if not self.parsed_topics:
            # Create a default topic if none exists
            self._start_new_topic(None)

        current_topic = self.parsed_topics[-1]
        current_topic.content_blocks.append(
            TopicTextBlock(
                text_spans=text_spans,
                paragraph_info=paragraph_info,
                hotspot_mappings=hotspot_mappings or [],
                source_offset=source_offset,
                source_end_offset=source_end_offset,
                source_record_offset=source_record_offset,
            )
        )
        span_base = len(current_topic.text_spans)
        character_base = sum(len(span.text) for span in current_topic.text_spans)
        current_topic.text_spans.extend(text_spans)
        if hotspot_mappings:
            current_topic.hotspot_mappings.extend(
                mapping.model_copy(
                    update={
                        "text_span_index": mapping.text_span_index + span_base,
                        "start_position": mapping.start_position + character_base,
                        "end_position": mapping.end_position + character_base,
                    }
                )
                for mapping in hotspot_mappings
            )
        if paragraph_info:
            current_topic.paragraph_infos.append(paragraph_info)
            if not current_topic.paragraph_info:
                current_topic.paragraph_info = paragraph_info

    def _parse_table_record(self, link: TopicLink, data: bytes, link_data2: bytes) -> Optional[Table]:
        """Parse one TL_TABLE record (a table row), following helpdeco.c TopicDump.

        After the column layout, LinkData1 repeats [column number, unknown word,
        byte, paragraph attributes, formatting commands up to 0xFF] until the
        column number is -1. The text pointer runs on across columns; a repeated
        column number continues the same cell with a new paragraph.
        """
        topic_size, offset = self.scan_long(data, 0)
        topic_length, offset = self.scan_word(data, offset)
        self.topic_offset += topic_length
        if offset + 2 > len(data):
            return None
        cols, table_type = data[offset], data[offset + 1]
        offset += 2
        min_width = None
        if table_type in (0, 2) and offset + 2 <= len(data):
            min_width = struct.unpack_from("<h", data, offset)[0]
            offset += 2
        column_widths, column_gaps = [], []
        for _ in range(cols):
            if offset + 4 > len(data):
                return None
            width, gap = struct.unpack_from("<hh", data, offset)
            column_widths.append(width)
            column_gaps.append(gap)
            offset += 4

        raw_text = self._parse_link_data2(link_data2, link.data_len2, link.block_size, link.data_len1)
        cells: List[TableCell] = []
        last_col = None
        text_pos = 0
        font = None
        while offset + 2 <= len(data):
            column = struct.unpack_from("<h", data, offset)[0]
            if column == -1 or offset + 5 > len(data):
                break
            fields, offset = self._parse_paragraph_attributes(data, offset + 5)
            paragraph_info = ParagraphInfo(
                topic_size=topic_size, topic_length=topic_length, **fields, raw_data={"column": column}
            )
            spans, _ = self._parse_topic_content_interleaved(
                data[offset:], b"", 0, 0, 0, raw_text=raw_text, start_p2=text_pos, initial_font=font, table_mode=True
            )
            consumed, text_pos, font = self._interleave_state
            offset += consumed
            bits = fields["bits"]
            alignment = (
                "center" if bits.center_aligned_paragraph else "right" if bits.right_aligned_paragraph else "left"
            )
            if column == last_col and cells:
                cells[-1].text_spans.extend([TextSpan(text="\n\n", raw_data={"type": "text"}), *spans])
            else:
                cells.append(
                    TableCell(
                        text_spans=spans,
                        alignment=alignment,
                        column_number=column,
                        paragraph_info=paragraph_info,
                        border_info=fields["border_info"],
                        raw_data={},
                    )
                )
            last_col = column

        if not cells:
            return None
        return Table(
            rows=[TableRow(cells=cells, raw_data={"cell_count": len(cells)})],
            column_count=cols,
            column_widths=column_widths,
            raw_data={"table_type": table_type, "min_width": min_width, "column_gaps": column_gaps},
        )

    def _add_table_to_current_topic(
        self,
        table: Table,
        source_offset: Optional[int] = None,
        source_end_offset: Optional[int] = None,
        source_record_offset: Optional[int] = None,
    ):
        """Add a table to the current topic."""
        if not self.parsed_topics:
            # Create a default topic if none exists
            self._start_new_topic(None)

        current_topic = self.parsed_topics[-1]
        # Each TL_TABLE record is one row; consecutive rows with the same column
        # layout belong to one table.
        last = current_topic.content_blocks[-1] if current_topic.content_blocks else None
        if (
            isinstance(last, TopicTableBlock)
            and last.table.column_count == table.column_count
            and last.table.column_widths == table.column_widths
        ):
            last.table.rows.extend(table.rows)
            last.source_end_offset = source_end_offset
            return
        current_topic.tables.append(table)
        current_topic.content_blocks.append(
            TopicTableBlock(
                table=table,
                source_offset=source_offset,
                source_end_offset=source_end_offset,
                source_record_offset=source_record_offset,
            )
        )

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
