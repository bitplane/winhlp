"""Parser for the |TOPIC internal file."""

from .base import InternalFile
from pydantic import BaseModel
from typing import List, Any, Optional
import struct
from ..compression import lz77_decompress


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
    raw_data: dict


class ExternalJumpCommand(BaseModel):
    jump_type: int
    topic_offset: int
    window_number: int = None
    external_file: str = None
    window_name: str = None
    raw_data: dict


class PictureCommand(BaseModel):
    picture_type: int
    picture_size: int
    data: bytes
    raw_data: dict


class MacroCommand(BaseModel):
    macro_string: str
    raw_data: dict


class TopicFile(InternalFile):
    """
    Parses the |TOPIC file, which holds the actual help content,
    including text, formatting, and links.
    """

    blocks: list = []
    system_file: Any = None  # To be replaced with SystemFile object
    formatting_commands: List[Any] = []

    def __init__(self, system_file: Any = None, **data):
        super().__init__(**data)
        self.system_file = system_file
        self._parse()

    def _parse(self):
        """
        Parses the |TOPIC file data.
        """
        self._parse_blocks()

    def _parse_blocks(self):
        """
        Parses the topic blocks.

        This logic is based on the `DecompressIntoBuffer` function in `helpdec1.c`,
        which handles LZ77 decompression and variable block sizes.

        From `helpdec1.c`:
        long DecompressIntoBuffer(int method, FILE* HelpFile, long bytes, char* ptr, long size)
        {
            MFILE* f;
            MFILE* mf;

            f = CreateMap(ptr, size);
            mf = CreateVirtual(HelpFile);
            bytes = decompress(method, mf, bytes, f);
            CloseMap(mf);
            CloseMap(f);
            return bytes;
        }
        """
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

            # Determine compression and block size from SystemFile
            # Simplified for now, assuming LZ77 and 4k block size if compressed
            # and 2k if not compressed (based on helpfile.md)
            is_lz_compressed = False
            if self.system_file and self.system_file.header.minor > 16:
                if self.system_file.header.flags == 4 or self.system_file.header.flags == 8:
                    is_lz_compressed = True

            # For now, we'll assume a fixed block size for simplicity
            # A more robust implementation would use the TopicBlockSize from SystemFile
            # and handle phrase compression.
            block_data_size = 4096 - 12  # A common block size
            block_data_raw = self.raw_data[offset + 12 : offset + 12 + block_data_size]

            if is_lz_compressed:
                # This is a placeholder. Actual LZ77 decompression is complex.
                # We'll need to implement the LZ77 algorithm from helpdec1.c
                block_data = lz77_decompress(block_data_raw)
            else:
                block_data = block_data_raw

            self._parse_links(block_data)

            offset += 4096  # A common block size

    def _parse_links(self, block_data: bytes):
        """
        Parses the topic links within a topic block.
        """
        offset = 0
        while offset < len(block_data):
            # Check which structure format to use based on the file version
            # The confusion comes from different sizes in Win 3.0 vs 3.1
            if self.system_file and self.system_file.header.minor <= 16:
                # Win 3.0 uses smaller structure
                raw_bytes = block_data[offset : offset + 19]
                if len(raw_bytes) < 19:
                    break
                block_size, data_len2, prev_block, next_block, data_len1, record_type = struct.unpack(
                    "<llllHb", raw_bytes
                )
                link_offset = 19
            else:
                # Win 3.1+ uses full 21-byte structure
                raw_bytes = block_data[offset : offset + 21]
                if len(raw_bytes) < 21:
                    break
                block_size, data_len2, prev_block, next_block, data_len1, record_type = struct.unpack(
                    "<LLLLLb", raw_bytes
                )
                link_offset = 21

            parsed_link = {
                "block_size": block_size,
                "data_len2": data_len2,
                "prev_block": prev_block,
                "next_block": next_block,
                "data_len1": data_len1,
                "record_type": record_type,
            }

            link = TopicLink(**parsed_link, raw_data={"raw": raw_bytes, "parsed": parsed_link})

            # DataLen1 includes the size of TOPICLINK in Win 3.1+
            if self.system_file and self.system_file.header.minor <= 16:
                link_data1 = block_data[offset + link_offset : offset + link_offset + data_len1]
                link_data2 = block_data[offset + link_offset + data_len1 : offset + block_size]
            else:
                link_data1 = block_data[offset + link_offset : offset + data_len1]
                link_data2 = block_data[offset + data_len1 : offset + block_size]

            self._parse_link_data(link, link_data1, link_data2)

            if block_size == 0:
                break

            offset += block_size

    def _parse_link_data(self, link: TopicLink, link_data1: bytes, link_data2: bytes):
        """
        Parses the data within a topic link.
        """
        if link.record_type == 0x02:  # TL_TOPICHDR
            self._parse_topic_header(link_data1)
        elif link.record_type == 0x20:  # TL_DISPLAY
            self._parse_paragraph_info(link_data1)
            link.text_content = self._parse_link_data2(link_data2)
        elif link.record_type == 0x23:  # TL_TABLE
            self._parse_paragraph_info(link_data1)
            link.text_content = self._parse_link_data2(link_data2)

    def _parse_topic_header(self, data: bytes):
        """
        Parses a topic header.
        """
        # For now, we only support the WinHelp 3.1+ format
        raw_bytes = data[:28]
        if len(raw_bytes) < 28:
            return

        block_size, browse_bck, browse_for, topic_num, non_scroll, scroll, next_topic = struct.unpack(
            "<lllllll", raw_bytes
        )

        # Create structured header (validates data and maintains consistency)
        TopicHeader(
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

    def _parse_link_data2(self, data: bytes) -> str:
        """
        Decompresses and parses LinkData2 (text content).
        """
        decompressed_data = lz77_decompress(data)
        return decompressed_data.decode("latin-1")

    def _parse_formatting_commands(self, data: bytes):
        """
        Parses the formatting commands that follow ParagraphInfo.
        """
        offset = 0
        while offset < len(data):
            start_command_offset = offset
            command_byte = struct.unpack_from("<B", data, offset)[0]
            offset += 1

            if command_byte == 0x01:  # TextFormatCommand
                font_number = struct.unpack_from("<B", data, offset)[0]
                offset += 1
                command = TextFormatCommand(
                    font_number=font_number,
                    raw_data={"raw": data[start_command_offset:offset], "parsed": {"font_number": font_number}},
                )
                self.formatting_commands.append(command)
            elif command_byte == 0x02:  # JumpCommand
                topic_offset = struct.unpack_from("<l", data, offset)[0]
                offset += 4
                command = JumpCommand(
                    topic_offset=topic_offset,
                    raw_data={"raw": data[start_command_offset:offset], "parsed": {"topic_offset": topic_offset}},
                )
                self.formatting_commands.append(command)
            elif command_byte == 0x03:  # ExternalJumpCommand
                jump_type = struct.unpack_from("<B", data, offset)[0]
                offset += 1
                topic_offset = struct.unpack_from("<l", data, offset)[0]
                offset += 4
                window_number = None
                external_file = None
                window_name = None

                if jump_type == 0x01:  # JUMP_TYPE_WINDOW
                    window_number = struct.unpack_from("<B", data, offset)[0]
                    offset += 1
                elif jump_type == 0x02:  # JUMP_TYPE_EXTERNAL
                    # Read null-terminated string for external_file
                    external_file_start = offset
                    while data[offset] != 0x00:
                        offset += 1
                    external_file = data[external_file_start:offset].decode("ascii")
                    offset += 1  # for null terminator

                    # Read null-terminated string for window_name
                    window_name_start = offset
                    while data[offset] != 0x00:
                        offset += 1
                    window_name = data[window_name_start:offset].decode("ascii")
                    offset += 1  # for null terminator

                command = ExternalJumpCommand(
                    jump_type=jump_type,
                    topic_offset=topic_offset,
                    window_number=window_number,
                    external_file=external_file,
                    window_name=window_name,
                    raw_data={
                        "raw": data[start_command_offset:offset],
                        "parsed": {
                            "jump_type": jump_type,
                            "topic_offset": topic_offset,
                            "window_number": window_number,
                            "external_file": external_file,
                            "window_name": window_name,
                        },
                    },
                )
                self.formatting_commands.append(command)
            elif command_byte == 0x04:  # PictureCommand
                picture_type = struct.unpack_from("<B", data, offset)[0]
                offset += 1
                picture_size = struct.unpack_from("<l", data, offset)[0]
                offset += 4
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
                # TODO: Parse the picture data using the Picture class (validates structure)
                # Picture(data=picture_data)
            elif command_byte == 0x05:  # MacroCommand
                macro_string_start = offset
                while data[offset] != 0x00:
                    offset += 1
                macro_string = data[macro_string_start:offset].decode("ascii")
                offset += 1  # for null terminator
                command = MacroCommand(
                    macro_string=macro_string,
                    raw_data={"raw": data[start_command_offset:offset], "parsed": {"macro_string": macro_string}},
                )
                self.formatting_commands.append(command)
            elif command_byte == 0x00:  # End of commands
                break
            else:
                # Unknown command byte - stop parsing
                break

    def _parse_paragraph_info(self, data: bytes):
        """
        Parses the ParagraphInfo structure.
        """
        offset = 0
        start_offset = offset

        topic_size = struct.unpack_from("<l", data, offset)[0]
        offset += 4

        topic_length = struct.unpack_from("<H", data, offset)[0]
        offset += 2

        bits_raw = struct.unpack_from("<H", data, offset)[0]
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
            unknown = struct.unpack_from("<l", data, offset)[0]
            offset += 4

        if bits.spacing_above_follows:
            spacing_above = struct.unpack_from("<h", data, offset)[0]
            offset += 2

        if bits.spacing_below_follows:
            spacing_below = struct.unpack_from("<h", data, offset)[0]
            offset += 2

        if bits.spacing_lines_follows:
            spacing_lines = struct.unpack_from("<h", data, offset)[0]
            offset += 2

        if bits.left_indent_follows:
            left_indent = struct.unpack_from("<h", data, offset)[0]
            offset += 2

        if bits.right_indent_follows:
            right_indent = struct.unpack_from("<h", data, offset)[0]
            offset += 2

        if bits.firstline_indent_follows:
            firstline_indent = struct.unpack_from("<h", data, offset)[0]
            offset += 2

        if bits.borderinfo_follows:
            border_info_raw = struct.unpack_from("<H", data, offset)[0]
            offset += 2
            border_width = struct.unpack_from("<h", data, offset)[0]
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
            if offset + 2 <= len(data):
                number_of_tab_stops = struct.unpack_from("<H", data, offset)[0]
                offset += 2
                tabs = []
                for _ in range(number_of_tab_stops):
                    if offset + 2 > len(data):
                        break
                    tab_stop = struct.unpack_from("<H", data, offset)[0]
                    offset += 2
                    tab_type = 0
                    if tab_stop & 0x4000:
                        if offset + 2 <= len(data):
                            tab_type = struct.unpack_from("<H", data, offset)[0]
                            offset += 2
                        else:
                            # Not enough data for tab type
                            pass
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
        self._parse_formatting_commands(data[offset:])
