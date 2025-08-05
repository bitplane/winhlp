"""Main HLP file reader class."""

from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any
from .directory import Directory
from .internal_files.system import SystemFile
from .internal_files.font import FontFile
from .internal_files.topic import TopicFile, ParsedTopic
from .internal_files.context import ContextFile
from .internal_files.phrase import PhraseFile
from .internal_files.ctxomap import CtxoMapFile
from .internal_files.catalog import CatalogFile
from .internal_files.viola import ViolaFile
from .internal_files.gmacros import GMacrosFile
from .internal_files.phrindex import PhrIndexFile
from .internal_files.phrimage import PhrImageFile
from .internal_files.topicid import TopicIdFile
from .internal_files.ttlbtree import TTLBTreeFile
from .internal_files.xwbtree import XWBTreeFile
from .internal_files.xwdata import XWDataFile
from .internal_files.xwmap import XWMapFile
from .internal_files.cfn import CFnFile
from .internal_files.rose import RoseFile
from .internal_files.bitmap import BitmapFile
from .internal_files.tomap import ToMapFile
from .internal_files.petra import PetraFile
from .internal_files.grp import GRPFile
from .internal_files.chartab import ChartabFile
from .internal_files.gid import WinPosFile, PeteFile, FlagsFile, CntJumpFile, CntTextFile
from .exceptions import InvalidHLPFileError
import struct


class HLPHeader(BaseModel):
    """
    A help file starts with a header, the only structure at a fixed place.
    From `helpdeco.h`: HELPHEADER
    """

    magic: int = Field(..., description="Magic number, should be 0x00035F3F")
    directory_start: int = Field(..., description="Offset of the internal directory")
    free_chain_start: int = Field(..., description="Offset of the first free block, or -1")
    entire_file_size: int = Field(..., description="Size of the entire help file in bytes")
    raw_data: dict


class HelpFile(BaseModel):
    """
    The main class for reading and parsing a HLP file.

    This class represents a HLP file and provides methods to parse its contents.
    It loads the entire file into memory for parsing.
    """

    filepath: str
    data: bytes = b""
    header: Optional[HLPHeader] = None
    directory: Optional[Directory] = None
    system: Optional[SystemFile] = None
    font: Optional[FontFile] = None
    topic: Optional[TopicFile] = None
    context: Optional[ContextFile] = None
    phrase: Optional[PhraseFile] = None
    ctxomap: Optional[CtxoMapFile] = None
    catalog: Optional[CatalogFile] = None
    viola: Optional[ViolaFile] = None
    gmacros: Optional[GMacrosFile] = None
    phrindex: Optional[PhrIndexFile] = None
    phrimage: Optional[PhrImageFile] = None
    topicid: Optional[TopicIdFile] = None
    ttlbtree: Optional[TTLBTreeFile] = None
    tomap: Optional[ToMapFile] = None
    bitmaps: Dict[str, BitmapFile] = {}
    keyword_search_files: Dict[
        str, Dict[str, Any]
    ] = {}  # Maps 'A' -> {'btree': XWBTreeFile, 'data': XWDataFile, 'map': XWMapFile}
    keyword_index_files: Dict[
        str, Dict[str, Any]
    ] = {}  # Maps 'A' -> {'btree': XWBTreeFile, 'data': XWDataFile, 'map': XWMapFile} for |xKWBTREE files
    config_files: Dict[int, CFnFile] = {}  # Maps config number -> CFnFile
    rose: Optional[RoseFile] = None
    petra: Optional[PetraFile] = None
    grp_files: Dict[str, GRPFile] = {}  # Maps filename -> GRPFile for .GRP files
    chartab_files: Dict[str, ChartabFile] = {}  # Maps filename -> ChartabFile for .tbl files
    is_gid_file: bool = False  # True if this is a GID file created by WinHlp32

    # GID-specific internal files
    winpos: Optional[WinPosFile] = None
    pete: Optional[PeteFile] = None
    flags: Optional[FlagsFile] = None
    cntjump: Optional[CntJumpFile] = None
    cnttext: Optional[CntTextFile] = None

    def __init__(self, filepath: str, **data):
        super().__init__(filepath=filepath, **data)
        with open(self.filepath, "rb") as f:
            self.data = f.read()

        # Detect if this is a GID file based on extension
        self.is_gid_file = filepath.lower().endswith(".gid")

        self.parse()

    def get_topics(self) -> List[ParsedTopic]:
        """Get all parsed topics with structured content."""
        if self.topic:
            return self.topic.get_all_topics()
        return []

    def get_topic_by_number(self, topic_number: int) -> Optional[ParsedTopic]:
        """Get a specific topic by its number."""
        if self.topic:
            return self.topic.get_topic_by_number(topic_number)
        return None

    def get_topic_by_context_name(self, context_name: str) -> Optional[ParsedTopic]:
        """Get a topic by its context name using hash lookup."""
        if not self.context or not self.topic:
            return None

        # Calculate hash for the context name
        hash_value = ContextFile.calculate_hash(context_name)

        # Get topic offset from context mapping
        topic_offset = self.context.get_topic_offset_for_hash(hash_value)
        if topic_offset is None:
            return None

        # Find the topic with this offset (simplified - would need proper topic offset resolution)
        for topic in self.topic.get_all_topics():
            if topic.topic_number is not None:  # Basic matching - needs improvement
                return topic

        return None

    def extract_bitmap(self, bitmap_name: str) -> Optional[bytes]:
        """Extract a bitmap as BMP file data."""
        if bitmap_name not in self.bitmaps:
            return None

        bitmap_file = self.bitmaps[bitmap_name]
        return bitmap_file.extract_bitmap_as_bmp(0)

    def get_topic_with_resolved_images(self, topic_number: int) -> Optional[dict]:
        """Get a topic with all embedded images resolved to bitmap data."""
        topic = self.get_topic_by_number(topic_number)
        if not topic:
            return None

        return {
            "topic": topic,
            "embedded_images": topic.resolve_embedded_images(self),
            "hotspots": topic.get_clickable_regions(),
            "hyperlinks": topic.get_hyperlinks(),
        }

    def get_all_hotspots(self) -> Dict[str, List]:
        """Get all hotspots from all bitmaps with their context names."""
        all_hotspots = {}

        for bitmap_name, bitmap_file in self.bitmaps.items():
            hotspots_with_context = []

            for bitmap in bitmap_file.bitmaps:
                for hotspot in bitmap.hotspots:
                    context_name = ContextFile.reverse_hash(hotspot.hash_value)
                    hotspot_info = {
                        "x": hotspot.x,
                        "y": hotspot.y,
                        "width": hotspot.width,
                        "height": hotspot.height,
                        "hash": hotspot.hash_value,
                        "context_name": context_name,
                        "topic_offset": self.context.get_topic_offset_for_hash(hotspot.hash_value)
                        if self.context
                        else None,
                    }
                    hotspots_with_context.append(hotspot_info)

            if hotspots_with_context:
                all_hotspots[bitmap_name] = hotspots_with_context

        return all_hotspots

    def extract_all_text(self) -> str:
        """Extract all text content as plain text."""
        if self.topic:
            return self.topic.extract_all_text()
        return ""

    def get_topic_count(self) -> int:
        """Get the total number of topics in the help file."""
        if self.topic:
            return len(self.topic.get_all_topics())
        return 0

    def parse(self):
        """
        Parses the HLP file from the loaded data.
        """
        self.header = self._parse_header()
        self.directory = self._parse_directory()
        self.system = self._parse_system()
        self.font = self._parse_font()
        self.topic = self._parse_topic()
        self.context = self._parse_context()
        self.phrase = self._parse_phrase()
        self.tomap = self._parse_tomap()
        self.ctxomap = self._parse_ctxomap()
        self.catalog = self._parse_catalog()
        self.viola = self._parse_viola()
        self.gmacros = self._parse_gmacros()
        self.phrindex = self._parse_phrindex()
        self.phrimage = self._parse_phrimage()

        # Complete phrase parsing after both PhrIndex and PhrImage are available
        if self.phrindex and self.phrimage:
            self.phrindex.complete_phrase_parsing(self.phrimage)

        self.topicid = self._parse_topicid()
        self.ttlbtree = self._parse_ttlbtree()
        self.keyword_search_files = self._parse_keyword_search_files()
        self.keyword_index_files = self._parse_keyword_index_files()
        self.config_files = self._parse_config_files()
        self.rose = self._parse_rose()
        self.petra = self._parse_petra()
        self.grp_files = self._parse_grp_files()

        # Parse GID-specific files if this is a GID file
        if self.is_gid_file:
            self.winpos = self._parse_winpos()
            self.pete = self._parse_pete()
            self.flags = self._parse_flags()
            self.cntjump = self._parse_cntjump()
            self.cnttext = self._parse_cnttext()
        self.chartab_files = self._parse_chartab_files()
        self.bitmaps = self._parse_bitmaps()

    def _parse_header(self) -> HLPHeader:
        """
        Parses the main HLP file header.

        From `helpfile.md`:
        long Magic           0x00035F3F
        long DirectoryStart  offset of FILEHEADER of internal directory
        long FirstFreeBlock  offset of FREEHEADER or -1L if no free list
        long EntireFileSize  size of entire help file in bytes

        From `helpdeco.h`:
        typedef struct               /* structure at beginning of help file */
        {
            int32_t Magic;              /* 0x00035F3F */
            int32_t DirectoryStart;     /* offset of FILEHEADER of internal direcory */
            int32_t FreeChainStart;     /* offset of FILEHEADER or -1L */
            int32_t EntireFileSize;     /* size of entire help file in bytes */
        }
        HELPHEADER;

        From `helpdec1.c`:
        s(HELPHEADER)
        d(Magic)
        d(DirectoryStart)
        d(FreeChainStart)
        d(EntireFileSize)
        e
        """
        raw_bytes = self.data[:16]
        if len(raw_bytes) < 16:
            raise InvalidHLPFileError("File is too small to be a HLP file.")

        magic, dir_start, free_block, file_size = struct.unpack("<Llll", raw_bytes)

        if magic != 0x00035F3F:
            # Check if it looks like text data (common mistake)
            first_bytes = self.data[:16]
            if all(32 <= b <= 126 or b in [9, 10, 13] for b in first_bytes):
                raise InvalidHLPFileError(f"File appears to be text data, not a binary HLP file (magic: {magic:#0x})")
            else:
                raise InvalidHLPFileError(f"Invalid HLP magic number: {magic:#0x} (expected 0x00035F3F)")

        parsed_header = {
            "magic": magic,
            "directory_start": dir_start,
            "free_chain_start": free_block,
            "entire_file_size": file_size,
        }

        return HLPHeader(**parsed_header, raw_data={"raw": raw_bytes, "parsed": parsed_header})

    def _parse_directory(self) -> Directory:
        """
        Parses the internal file directory.

        The directory is a B+ tree that maps internal filenames to their data.
        The parsing logic will be implemented in the Directory class.
        """
        dir_data = self.data[self.header.directory_start :]
        return Directory(data=dir_data)

    def _load_internal_file(self, filename: str, parser_class, **kwargs):
        """
        Helper method to load and parse an internal file.

        Centralizes the common pattern of:
        1. Check if file exists in directory
        2. Read file offset
        3. Parse 9-byte FILEHEADER (reserved_space, used_space, file_flags)
        4. Extract file content using used_space
        5. Instantiate parser class with extracted data

        Based on the C reference's SearchFile pattern in helldec1.c.

        Args:
            filename: Internal filename (e.g., "|SYSTEM", "|TOPIC")
            parser_class: Parser class to instantiate
            **kwargs: Additional arguments to pass to parser constructor

        Returns:
            Instantiated parser object or None if file doesn't exist
        """
        if filename not in self.directory.files:
            return None

        # Get file offset from directory
        file_offset = self.directory.files[filename]

        # Read and validate 9-byte FILEHEADER
        file_header_data = self.data[file_offset : file_offset + 9]
        if len(file_header_data) < 9:
            return None

        # Parse FILEHEADER structure
        reserved_space, used_space, file_flags = struct.unpack("<llB", file_header_data)

        # Extract file content
        file_data = self.data[file_offset + 9 : file_offset + 9 + used_space]

        # Instantiate parser with extracted data
        return parser_class(filename=filename, raw_data=file_data, **kwargs)

    def _parse_system(self) -> SystemFile:
        """
        Parses the |SYSTEM internal file.
        """
        return self._load_internal_file("|SYSTEM", SystemFile, parent_hlp=self)

    def _parse_font(self) -> FontFile:
        """
        Parses the |FONT internal file.
        """
        return self._load_internal_file("|FONT", FontFile, system_file=self.system)

    def _parse_topic(self) -> TopicFile:
        """
        Parses the |TOPIC internal file.
        """
        return self._load_internal_file("|TOPIC", TopicFile, system_file=self.system)

    def _parse_context(self) -> ContextFile:
        """
        Parses the |CONTEXT internal file.
        """
        return self._load_internal_file("|CONTEXT", ContextFile)

    def _parse_petra(self) -> PetraFile:
        """
        Parses the |Petra internal file.

        The |Petra file maps topic offsets to original RTF source filenames.
        It's created when using HCRTF /a option.
        """
        if "|Petra" not in self.directory.files:
            return None

        petra_offset = self.directory.files["|Petra"]
        # We need to read the file header to know the size of the |Petra file
        file_header_data = self.data[petra_offset : petra_offset + 9]
        if len(file_header_data) < 9:
            return None
        reserved_space, used_space, file_flags = struct.unpack("<llB", file_header_data)

        petra_data = self.data[petra_offset + 9 : petra_offset + 9 + used_space]
        return PetraFile(petra_data, help_file=self)

    def _parse_phrase(self) -> PhraseFile:
        """
        Parses the |Phrases internal file.
        """
        if "|Phrases" not in self.directory.files:
            return None

        phrase_offset = self.directory.files["|Phrases"]
        # We need to read the file header to know the size of the |Phrases file
        file_header_data = self.data[phrase_offset : phrase_offset + 9]
        if len(file_header_data) < 9:
            return None
        reserved_space, used_space, file_flags = struct.unpack("<llB", file_header_data)

        phrase_data = self.data[phrase_offset + 9 : phrase_offset + 9 + used_space]
        return PhraseFile(filename="|Phrases", raw_data=phrase_data, system_file=self.system)

    def _parse_tomap(self) -> ToMapFile:
        """
        Parses the |TOMAP internal file for Windows 3.0 help files.
        """
        return self._load_internal_file("|TOMAP", ToMapFile)

    def _parse_ctxomap(self) -> CtxoMapFile:
        """
        Parses the |CTXOMAP internal file.
        """
        return self._load_internal_file("|CTXOMAP", CtxoMapFile)

    def _parse_catalog(self) -> CatalogFile:
        """
        Parses the |CATALOG internal file.
        """
        if "|CATALOG" not in self.directory.files:
            return None

        return self._load_internal_file("|CATALOG", CatalogFile)

    def _parse_viola(self) -> ViolaFile:
        """
        Parses the |VIOLA internal file.
        """
        return self._load_internal_file("|VIOLA", ViolaFile)

    def _parse_gmacros(self) -> GMacrosFile:
        """
        Parses the |GMACROS internal file.
        """
        return self._load_internal_file("|GMACROS", GMacrosFile)

    def _parse_phrindex(self) -> PhrIndexFile:
        """
        Parses the |PhrIndex internal file.
        """
        return self._load_internal_file("|PhrIndex", PhrIndexFile, system_file=self.system)

    def _parse_phrimage(self) -> PhrImageFile:
        """
        Parses the |PhrImage internal file.

        Note: Uses full raw_data including file header for PhrImageFile.
        """
        if "|PhrImage" not in self.directory.files:
            return None

        phrimage_offset = self.directory.files["|PhrImage"]
        file_header_data = self.data[phrimage_offset : phrimage_offset + 9]
        if len(file_header_data) < 9:
            return None

        reserved_space, used_space, file_flags = struct.unpack("<llB", file_header_data)
        phrimage_data = self.data[phrimage_offset : phrimage_offset + 9 + used_space]
        return PhrImageFile(
            filename="|PhrImage", raw_data=phrimage_data, system_file=self.system, phr_index_file=self.phrindex
        )

    def _parse_topicid(self) -> TopicIdFile:
        """
        Parses the |TopicId internal file.

        Note: Uses full raw_data including file header for TopicIdFile.
        """
        if "|TopicId" not in self.directory.files:
            return None

        topicid_offset = self.directory.files["|TopicId"]
        file_header_data = self.data[topicid_offset : topicid_offset + 9]
        if len(file_header_data) < 9:
            return None

        reserved_space, used_space, file_flags = struct.unpack("<llB", file_header_data)
        topicid_data = self.data[topicid_offset : topicid_offset + 9 + used_space]
        return TopicIdFile(filename="|TopicId", raw_data=topicid_data)

    def _parse_ttlbtree(self) -> TTLBTreeFile:
        """
        Parses the |TTLBTREE internal file.

        Note: Uses full raw_data including file header for TTLBTreeFile.
        """
        if "|TTLBTREE" not in self.directory.files:
            return None

        ttlbtree_offset = self.directory.files["|TTLBTREE"]
        file_header_data = self.data[ttlbtree_offset : ttlbtree_offset + 9]
        if len(file_header_data) < 9:
            return None

        reserved_space, used_space, file_flags = struct.unpack("<llB", file_header_data)
        ttlbtree_data = self.data[ttlbtree_offset : ttlbtree_offset + 9 + used_space]
        return TTLBTreeFile(filename="|TTLBTREE", raw_data=ttlbtree_data)

    def _parse_bitmaps(self) -> Dict[str, BitmapFile]:
        """
        Parses all bitmap files (|bm0, |bm1, |bm2, etc.) in the directory.
        """
        bitmaps = {}

        # Look for all bitmap files in the directory
        for filename, offset in self.directory.files.items():
            if filename.startswith("|bm") and len(filename) > 3:
                # Extract bitmap number (e.g., |bm0 -> 0, |bm123 -> 123)
                bitmap_num = filename[3:]
                if bitmap_num.isdigit():
                    try:
                        # Read the file header to know the size
                        file_header_data = self.data[offset : offset + 9]
                        if len(file_header_data) >= 9:
                            reserved_space, used_space, file_flags = struct.unpack("<llB", file_header_data)

                            # Extract bitmap data
                            bitmap_data = self.data[offset + 9 : offset + 9 + used_space]
                            bitmap_file = BitmapFile(filename=filename, raw_data=bitmap_data)
                            bitmaps[filename] = bitmap_file

                    except (struct.error, IndexError):
                        # Skip malformed bitmap files
                        continue

        return bitmaps

    def _parse_keyword_search_files(self) -> Dict[str, Dict[str, Any]]:
        """
        Parses all keyword search files (|xWBTREE, |xWDATA, |xWMAP) where x is A-Z, a-z.
        """
        keyword_files = {}

        # Check for all possible keyword search file sets (A-Z, a-z)
        for char_code in range(ord("A"), ord("Z") + 1):
            char = chr(char_code)
            keyword_files.update(self._parse_keyword_search_set(char))

        for char_code in range(ord("a"), ord("z") + 1):
            char = chr(char_code)
            keyword_files.update(self._parse_keyword_search_set(char))

        return keyword_files

    def _parse_keyword_search_set(self, char: str) -> Dict[str, Dict[str, Any]]:
        """
        Parse a complete keyword search set for a given character.

        Args:
            char: The character identifier (A-Z, a-z)

        Returns:
            Dictionary mapping char to parsed files, or empty dict if files don't exist
        """
        btree_name = f"|{char}WBTREE"
        data_name = f"|{char}WDATA"
        map_name = f"|{char}WMAP"

        # Check if all three files exist
        if (
            btree_name not in self.directory.files
            or data_name not in self.directory.files
            or map_name not in self.directory.files
        ):
            return {}

        try:
            # Parse |xWBTREE file
            btree_offset = self.directory.files[btree_name]
            file_header_data = self.data[btree_offset : btree_offset + 9]
            if len(file_header_data) < 9:
                return {}
            reserved_space, used_space, file_flags = struct.unpack("<llB", file_header_data)

            btree_data = self.data[btree_offset : btree_offset + 9 + used_space]
            btree_file = XWBTreeFile(filename=btree_name, raw_data=btree_data)

            # Parse |xWDATA file
            data_offset = self.directory.files[data_name]
            file_header_data = self.data[data_offset : data_offset + 9]
            if len(file_header_data) < 9:
                return {}
            reserved_space, used_space, file_flags = struct.unpack("<llB", file_header_data)

            data_data = self.data[data_offset : data_offset + 9 + used_space]
            data_file = XWDataFile(filename=data_name, raw_data=data_data)

            # Parse |xWMAP file
            map_offset = self.directory.files[map_name]
            file_header_data = self.data[map_offset : map_offset + 9]
            if len(file_header_data) < 9:
                return {}
            reserved_space, used_space, file_flags = struct.unpack("<llB", file_header_data)

            map_data = self.data[map_offset : map_offset + 9 + used_space]
            map_file = XWMapFile(filename=map_name, raw_data=map_data)

            return {char: {"btree": btree_file, "data": data_file, "map": map_file}}

        except (struct.error, IndexError):
            # Skip malformed keyword search files
            return {}

    def search_keywords(self, char: str, keyword: str) -> List[int]:
        """
        Search for topic offsets associated with a keyword.

        Args:
            char: The character identifier (A-Z, a-z) for the keyword type
            keyword: The keyword to search for

        Returns:
            List of topic offsets where the keyword appears
        """
        if char not in self.keyword_search_files:
            return []

        files = self.keyword_search_files[char]
        btree_file = files["btree"]
        data_file = files["data"]

        # Get keyword info from btree
        keyword_info = btree_file.get_keyword_info(keyword)
        if not keyword_info:
            return []

        # For GID format, topic offsets are stored directly in btree
        if btree_file.is_gid_format:
            return btree_file.get_topic_offsets_for_keyword(keyword)

        # For standard format, use data file with offset and count
        if hasattr(keyword_info, "kw_data_offset") and hasattr(keyword_info, "count"):
            return data_file.get_topic_offsets_range(keyword_info.kw_data_offset, keyword_info.count)

        return []

    def get_all_keywords(self, char: str) -> List[str]:
        """
        Get all keywords for a specific character type.

        Args:
            char: The character identifier (A-Z, a-z) for the keyword type

        Returns:
            List of all keywords for the character type
        """
        if char not in self.keyword_search_files:
            return []

        btree_file = self.keyword_search_files[char]["btree"]
        return btree_file.get_all_keywords()

    def get_keyword_search_statistics(self) -> Dict[str, Any]:
        """
        Get statistics about all keyword search files.

        Returns:
            Dictionary with keyword search statistics
        """
        stats = {
            "available_characters": list(self.keyword_search_files.keys()),
            "total_character_sets": len(self.keyword_search_files),
            "character_stats": {},
        }

        total_keywords = 0
        total_references = 0

        for char, files in self.keyword_search_files.items():
            btree_stats = files["btree"].get_statistics()
            data_stats = files["data"].get_statistics()
            map_stats = files["map"].get_statistics()

            char_stats = {
                "keywords": btree_stats["total_keywords"],
                "references": btree_stats.get("total_references", 0),
                "data_offsets": data_stats["total_offsets"],
                "map_entries": map_stats["total_entries"],
                "is_gid_format": btree_stats["is_gid_format"],
            }

            stats["character_stats"][char] = char_stats
            total_keywords += char_stats["keywords"]
            total_references += char_stats["references"]

        stats["total_keywords"] = total_keywords
        stats["total_references"] = total_references

        return stats

    def _parse_config_files(self) -> Dict[int, CFnFile]:
        """
        Parses all configuration files (|CFn) where n is an integer.
        """
        config_files = {}

        # Check for all possible |CFn files (CF0, CF1, CF2, etc.)
        for filename, offset in self.directory.files.items():
            if filename.startswith("|CF") and len(filename) > 3:
                # Extract config number (e.g., |CF0 -> 0, |CF123 -> 123)
                config_num_str = filename[3:]
                if config_num_str.isdigit():
                    try:
                        config_num = int(config_num_str)

                        # Parse the |CFn file
                        file_header_data = self.data[offset : offset + 9]
                        if len(file_header_data) >= 9:
                            reserved_space, used_space, file_flags = struct.unpack("<llB", file_header_data)

                            # Extract config data
                            config_data = self.data[offset + 9 : offset + 9 + used_space]
                            config_file = CFnFile(filename=filename, raw_data=config_data)
                            config_files[config_num] = config_file

                    except (struct.error, IndexError, ValueError):
                        # Skip malformed config files
                        continue

        return config_files

    def _parse_keyword_index_files(self) -> Dict[str, Dict[str, Any]]:
        """
        Parses all keyword index files (|xKWBTREE, |xKWDATA, |xKWMAP) where x is A-Z, a-z.
        These are different from regular keyword search files - they're used for keyword indices.
        From C code: when keyindex[char] is TRUE, use |xKWBTREE instead of |xWBTREE.
        """
        keyword_index_files = {}

        # Only parse keyword index files for characters marked as keyword indices in SystemFile
        if self.system and hasattr(self.system, "keyword_indices"):
            for char in self.system.keyword_indices:
                keyword_index_files.update(self._parse_keyword_index_set(char))

        return keyword_index_files

    def _parse_keyword_index_set(self, char: str) -> Dict[str, Dict[str, Any]]:
        """
        Parse a complete keyword index set for a given character.

        Args:
            char: The character identifier (A-Z, a-z)

        Returns:
            Dictionary mapping char to parsed files, or empty dict if files don't exist
        """
        btree_name = f"|{char}KWBTREE"
        data_name = f"|{char}KWDATA"
        map_name = f"|{char}KWMAP"

        # Check if all three files exist
        if (
            btree_name not in self.directory.files
            or data_name not in self.directory.files
            or map_name not in self.directory.files
        ):
            return {}

        try:
            # Parse |xKWBTREE file
            btree_offset = self.directory.files[btree_name]
            file_header_data = self.data[btree_offset : btree_offset + 9]
            if len(file_header_data) < 9:
                return {}
            reserved_space, used_space, file_flags = struct.unpack("<llB", file_header_data)

            btree_data = self.data[btree_offset : btree_offset + 9 + used_space]
            btree_file = XWBTreeFile(filename=btree_name, raw_data=btree_data)

            # Parse |xKWDATA file
            data_offset = self.directory.files[data_name]
            file_header_data = self.data[data_offset : data_offset + 9]
            if len(file_header_data) < 9:
                return {}
            reserved_space, used_space, file_flags = struct.unpack("<llB", file_header_data)

            data_data = self.data[data_offset : data_offset + 9 + used_space]
            data_file = XWDataFile(filename=data_name, raw_data=data_data)

            # Parse |xKWMAP file
            map_offset = self.directory.files[map_name]
            file_header_data = self.data[map_offset : map_offset + 9]
            if len(file_header_data) < 9:
                return {}
            reserved_space, used_space, file_flags = struct.unpack("<llB", file_header_data)

            map_data = self.data[map_offset : map_offset + 9 + used_space]
            map_file = XWMapFile(filename=map_name, raw_data=map_data)

            return {char: {"btree": btree_file, "data": data_file, "map": map_file}}

        except (struct.error, IndexError):
            # Skip malformed keyword index files
            return {}

    def get_config_macros(self, config_number: int) -> List[str]:
        """
        Get all macros for a specific configuration number.

        Args:
            config_number: The configuration number (0, 1, 2, etc.)

        Returns:
            List of macro strings for the configuration
        """
        if config_number in self.config_files:
            return self.config_files[config_number].get_macros()
        return []

    def get_all_config_numbers(self) -> List[int]:
        """
        Get all available configuration numbers.

        Returns:
            List of configuration numbers that have associated files
        """
        return list(self.config_files.keys())

    def get_config_statistics(self) -> Dict[str, Any]:
        """
        Get statistics about all configuration files.

        Returns:
            Dictionary with configuration file statistics
        """
        if not self.config_files:
            return {"total_config_files": 0, "total_macros": 0, "config_numbers": [], "config_stats": {}}

        total_macros = 0
        config_stats = {}

        for config_num, config_file in self.config_files.items():
            file_stats = config_file.get_statistics()
            config_stats[config_num] = file_stats
            total_macros += file_stats["total_macros"]

        return {
            "total_config_files": len(self.config_files),
            "total_macros": total_macros,
            "config_numbers": sorted(self.config_files.keys()),
            "config_stats": config_stats,
        }

    def search_keyword_indices(self, char: str, keyword: str) -> List[int]:
        """
        Search for topic offsets associated with a keyword in keyword index files.

        Args:
            char: The character identifier (A-Z, a-z) for the keyword index type
            keyword: The keyword to search for

        Returns:
            List of topic offsets where the keyword appears
        """
        if char not in self.keyword_index_files:
            return []

        files = self.keyword_index_files[char]
        btree_file = files["btree"]
        data_file = files["data"]

        # Get keyword info from btree
        keyword_info = btree_file.get_keyword_info(keyword)
        if not keyword_info:
            return []

        # For GID format, topic offsets are stored directly in btree
        if btree_file.is_gid_format:
            return btree_file.get_topic_offsets_for_keyword(keyword)

        # For standard format, use data file with offset and count
        if hasattr(keyword_info, "kw_data_offset") and hasattr(keyword_info, "count"):
            return data_file.get_topic_offsets_range(keyword_info.kw_data_offset, keyword_info.count)

        return []

    def get_all_keyword_indices(self, char: str) -> List[str]:
        """
        Get all keywords for a specific keyword index character type.

        Args:
            char: The character identifier (A-Z, a-z) for the keyword index type

        Returns:
            List of all keywords for the character type
        """
        if char not in self.keyword_index_files:
            return []

        btree_file = self.keyword_index_files[char]["btree"]
        return btree_file.get_all_keywords()

    def get_keyword_index_statistics(self) -> Dict[str, Any]:
        """
        Get statistics about all keyword index files.

        Returns:
            Dictionary with keyword index statistics
        """
        stats = {
            "available_characters": list(self.keyword_index_files.keys()),
            "total_character_sets": len(self.keyword_index_files),
            "character_stats": {},
        }

        total_keywords = 0
        total_references = 0

        for char, files in self.keyword_index_files.items():
            btree_stats = files["btree"].get_statistics()
            data_stats = files["data"].get_statistics()
            map_stats = files["map"].get_statistics()

            char_stats = {
                "keywords": btree_stats["total_keywords"],
                "references": btree_stats.get("total_references", 0),
                "data_offsets": data_stats["total_offsets"],
                "map_entries": map_stats["total_entries"],
                "is_gid_format": btree_stats["is_gid_format"],
            }

            stats["character_stats"][char] = char_stats
            total_keywords += char_stats["keywords"]
            total_references += char_stats["references"]

        stats["total_keywords"] = total_keywords
        stats["total_references"] = total_references

        return stats

    def _parse_rose(self) -> RoseFile:
        """
        Parses the |Rose internal file.
        """
        if "|Rose" not in self.directory.files:
            return None

        rose_offset = self.directory.files["|Rose"]
        # We need to read the file header to know the size of the |Rose file
        file_header_data = self.data[rose_offset : rose_offset + 9]
        if len(file_header_data) < 9:
            return None
        reserved_space, used_space, file_flags = struct.unpack("<llB", file_header_data)

        rose_data = self.data[rose_offset : rose_offset + 9 + used_space]
        return RoseFile(filename="|Rose", raw_data=rose_data)

    def get_macro_by_hash(self, keyword_hash: int) -> Optional[str]:
        """
        Get a macro string by its keyword hash from the |Rose file.

        Args:
            keyword_hash: The keyword hash to look up

        Returns:
            Macro string, or None if not found or no Rose file
        """
        if self.rose:
            return self.rose.get_macro_string_by_hash(keyword_hash)
        return None

    def get_all_macro_definitions(self) -> List[tuple]:
        """
        Get all macro definitions from the |Rose file.

        Returns:
            List of (keyword_hash, macro, topic_title) tuples
        """
        if not self.rose:
            return []

        return [(entry.keyword_hash, entry.macro, entry.topic_title) for entry in self.rose.get_all_entries()]

    def find_macros_by_pattern(self, pattern: str) -> List[tuple]:
        """
        Find macro definitions containing a pattern.

        Args:
            pattern: String pattern to search for in macro strings

        Returns:
            List of (keyword_hash, macro, topic_title) tuples matching the pattern
        """
        if not self.rose:
            return []

        matches = self.rose.find_macros_by_pattern(pattern)
        return [(entry.keyword_hash, entry.macro, entry.topic_title) for entry in matches]

    def get_rose_statistics(self) -> Dict[str, Any]:
        """
        Get statistics about the Rose file.

        Returns:
            Dictionary with Rose file statistics, or empty dict if no Rose file
        """
        if not self.rose:
            return {"has_rose_file": False, "total_macros": 0}

        stats = self.rose.get_statistics()
        stats["has_rose_file"] = True
        return stats

    def _parse_grp_files(self) -> Dict[str, GRPFile]:
        """
        Parse all GRP (MediaView Group) files in the directory.

        GRP files end with .GRP extension and contain group+ footnotes
        assigned to topics in MediaView files.
        """
        grp_files = {}

        if not self.directory:
            return grp_files

        # Find all files ending with .GRP
        for filename in self.directory.files:
            if filename.upper().endswith(".GRP"):
                try:
                    file_offset = self.directory.files[filename]

                    # Read file header to get size
                    file_header_data = self.data[file_offset : file_offset + 9]
                    if len(file_header_data) < 9:
                        continue

                    reserved_space, used_space, file_flags = struct.unpack("<llB", file_header_data)

                    # Extract GRP file data
                    grp_data = self.data[file_offset + 9 : file_offset + 9 + used_space]

                    # Create GRP file instance
                    grp_file = GRPFile(grp_data, help_file=self)
                    grp_files[filename] = grp_file

                except (struct.error, IndexError, ValueError):
                    # Skip malformed GRP files
                    continue

        return grp_files

    def _parse_chartab_files(self) -> Dict[str, ChartabFile]:
        """
        Parse all CHARTAB (Character Mapping Table) files in the directory.

        CHARTAB files end with .tbl extension and contain character mapping
        information for fonts in MediaView files.
        """
        chartab_files = {}

        if not self.directory:
            return chartab_files

        # Find all files ending with .tbl
        for filename in self.directory.files:
            if filename.upper().endswith(".TBL"):
                try:
                    file_offset = self.directory.files[filename]

                    # Read file header to get size
                    file_header_data = self.data[file_offset : file_offset + 9]
                    if len(file_header_data) < 9:
                        continue

                    reserved_space, used_space, file_flags = struct.unpack("<llB", file_header_data)

                    # Extract CHARTAB file data
                    chartab_data = self.data[file_offset + 9 : file_offset + 9 + used_space]

                    # Create CHARTAB file instance
                    chartab_file = ChartabFile(chartab_data, help_file=self)
                    chartab_files[filename] = chartab_file

                except (struct.error, IndexError, ValueError):
                    # Skip malformed CHARTAB files
                    continue

        return chartab_files

    def get_character_mapping(self, filename: str, char_code: int) -> Optional[dict]:
        """
        Get character mapping information for a specific character code from a CHARTAB file.

        Args:
            filename: The CHARTAB filename (e.g., "ANSI.TBL")
            char_code: The character code to look up

        Returns:
            Dictionary with character mapping information, or None if not found
        """
        if filename in self.chartab_files:
            return self.chartab_files[filename].get_character_mapping(char_code)
        return None

    def get_all_character_mappings(self, filename: str) -> Dict[int, dict]:
        """
        Get all character mappings from a CHARTAB file.

        Args:
            filename: The CHARTAB filename (e.g., "ANSI.TBL")

        Returns:
            Dictionary mapping character codes to mapping information
        """
        if filename in self.chartab_files:
            return self.chartab_files[filename].get_all_mappings()
        return {}

    def get_chartab_statistics(self) -> Dict[str, Any]:
        """
        Get statistics about all CHARTAB files.

        Returns:
            Dictionary with CHARTAB file statistics
        """
        if not self.chartab_files:
            return {"total_chartab_files": 0, "files": {}}

        stats = {"total_chartab_files": len(self.chartab_files), "files": {}}

        for filename, chartab_file in self.chartab_files.items():
            file_stats = chartab_file.get_statistics()
            stats["files"][filename] = file_stats

        return stats

    def get_available_chartab_files(self) -> List[str]:
        """
        Get list of available CHARTAB filenames.

        Returns:
            List of CHARTAB filenames
        """
        return list(self.chartab_files.keys())

    # GID-specific file parsing methods

    def _parse_winpos(self) -> Optional[WinPosFile]:
        """Parse the |WinPos internal file (GID files only)."""
        if "|WinPos" not in self.directory.files:
            return None

        winpos_offset = self.directory.files["|WinPos"]
        file_header_data = self.data[winpos_offset : winpos_offset + 9]
        if len(file_header_data) < 9:
            return None

        reserved_space, used_space, file_flags = struct.unpack("<llB", file_header_data)
        winpos_data = self.data[winpos_offset + 9 : winpos_offset + 9 + used_space]

        return WinPosFile(filename="|WinPos", raw_data=winpos_data)

    def _parse_pete(self) -> Optional[PeteFile]:
        """Parse the |Pete internal file (GID files only)."""
        if "|Pete" not in self.directory.files:
            return None

        pete_offset = self.directory.files["|Pete"]
        file_header_data = self.data[pete_offset : pete_offset + 9]
        if len(file_header_data) < 9:
            return None

        reserved_space, used_space, file_flags = struct.unpack("<llB", file_header_data)
        pete_data = self.data[pete_offset + 9 : pete_offset + 9 + used_space]

        return PeteFile(filename="|Pete", raw_data=pete_data)

    def _parse_flags(self) -> Optional[FlagsFile]:
        """Parse the |Flags internal file (GID files only)."""
        if "|Flags" not in self.directory.files:
            return None

        flags_offset = self.directory.files["|Flags"]
        file_header_data = self.data[flags_offset : flags_offset + 9]
        if len(file_header_data) < 9:
            return None

        reserved_space, used_space, file_flags = struct.unpack("<llB", file_header_data)
        flags_data = self.data[flags_offset + 9 : flags_offset + 9 + used_space]

        return FlagsFile(filename="|Flags", raw_data=flags_data)

    def _parse_cntjump(self) -> Optional[CntJumpFile]:
        """Parse the |CntJump internal file (GID files only)."""
        return self._load_internal_file("|CntJump", CntJumpFile)

    def _parse_cnttext(self) -> Optional[CntTextFile]:
        """Parse the |CntText internal file (GID files only)."""
        return self._load_internal_file("|CntText", CntTextFile)
