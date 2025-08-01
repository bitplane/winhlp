"""Main HLP file reader class."""

from pydantic import BaseModel, Field
from typing import Optional
from .directory import Directory
from .internal_files.system import SystemFile
from .internal_files.font import FontFile
from .internal_files.topic import TopicFile
from .internal_files.context import ContextFile
from .internal_files.phrase import PhraseFile
from .internal_files.ctxomap import CtxoMapFile
from .internal_files.catalog import CatalogFile
from .internal_files.viola import ViolaFile
from .internal_files.gmacros import GMacrosFile
from .internal_files.phrindex import PhrIndexFile
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

    def __init__(self, filepath: str, **data):
        super().__init__(filepath=filepath, **data)
        with open(self.filepath, "rb") as f:
            self.data = f.read()
        self.parse()

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
        self.ctxomap = self._parse_ctxomap()
        self.catalog = self._parse_catalog()
        self.viola = self._parse_viola()
        self.gmacros = self._parse_gmacros()
        self.phrindex = self._parse_phrindex()

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
            raise InvalidHLPFileError(f"Invalid magic number: {magic:#0x}")

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

    def _parse_system(self) -> SystemFile:
        """
        Parses the |SYSTEM internal file.
        """
        if "|SYSTEM" not in self.directory.files:
            return None

        system_offset = self.directory.files["|SYSTEM"]
        # We need to read the file header to know the size of the |SYSTEM file
        file_header_data = self.data[system_offset : system_offset + 9]
        reserved_space, used_space, file_flags = struct.unpack("<llB", file_header_data)

        system_data = self.data[system_offset + 9 : system_offset + 9 + used_space]
        return SystemFile(filename="|SYSTEM", raw_data=system_data)

    def _parse_font(self) -> FontFile:
        """
        Parses the |FONT internal file.
        """
        if "|FONT" not in self.directory.files:
            return None

        font_offset = self.directory.files["|FONT"]
        # We need to read the file header to know the size of the |FONT file
        file_header_data = self.data[font_offset : font_offset + 9]
        reserved_space, used_space, file_flags = struct.unpack("<llB", file_header_data)

        font_data = self.data[font_offset + 9 : font_offset + 9 + used_space]
        return FontFile(filename="|FONT", raw_data=font_data, system_file=self.system)

    def _parse_topic(self) -> TopicFile:
        """
        Parses the |TOPIC internal file.
        """
        if "|TOPIC" not in self.directory.files:
            return None

        topic_offset = self.directory.files["|TOPIC"]
        # We need to read the file header to know the size of the |TOPIC file
        file_header_data = self.data[topic_offset : topic_offset + 9]
        reserved_space, used_space, file_flags = struct.unpack("<llB", file_header_data)

        topic_data = self.data[topic_offset + 9 : topic_offset + 9 + used_space]
        return TopicFile(filename="|TOPIC", raw_data=topic_data, system_file=self.system)

    def _parse_context(self) -> ContextFile:
        """
        Parses the |CONTEXT internal file.
        """
        if "|CONTEXT" not in self.directory.files:
            return None

        context_offset = self.directory.files["|CONTEXT"]
        # We need to read the file header to know the size of the |CONTEXT file
        file_header_data = self.data[context_offset : context_offset + 9]
        reserved_space, used_space, file_flags = struct.unpack("<llB", file_header_data)

        context_data = self.data[context_offset + 9 : context_offset + 9 + used_space]
        return ContextFile(filename="|CONTEXT", raw_data=context_data)

    def _parse_phrase(self) -> PhraseFile:
        """
        Parses the |PHRASE internal file.
        """
        if "|PHRASE" not in self.directory.files:
            return None

        phrase_offset = self.directory.files["|PHRASE"]
        # We need to read the file header to know the size of the |PHRASE file
        file_header_data = self.data[phrase_offset : phrase_offset + 9]
        reserved_space, used_space, file_flags = struct.unpack("<llB", file_header_data)

        phrase_data = self.data[phrase_offset + 9 : phrase_offset + 9 + used_space]
        return PhraseFile(filename="|PHRASE", raw_data=phrase_data)

    def _parse_ctxomap(self) -> CtxoMapFile:
        """
        Parses the |CTXOMAP internal file.
        """
        if "|CTXOMAP" not in self.directory.files:
            return None

        ctxomap_offset = self.directory.files["|CTXOMAP"]
        # We need to read the file header to know the size of the |CTXOMAP file
        file_header_data = self.data[ctxomap_offset : ctxomap_offset + 9]
        reserved_space, used_space, file_flags = struct.unpack("<llB", file_header_data)

        ctxomap_data = self.data[ctxomap_offset + 9 : ctxomap_offset + 9 + used_space]
        return CtxoMapFile(filename="|CTXOMAP", raw_data=ctxomap_data)

    def _parse_catalog(self) -> CatalogFile:
        """
        Parses the |CATALOG internal file.
        """
        if "|CATALOG" not in self.directory.files:
            return None

        catalog_offset = self.directory.files["|CATALOG"]
        # We need to read the file header to know the size of the |CATALOG file
        file_header_data = self.data[catalog_offset : catalog_offset + 9]
        reserved_space, used_space, file_flags = struct.unpack("<llB", file_header_data)

        catalog_data = self.data[catalog_offset + 9 : catalog_offset + 9 + used_space]
        return CatalogFile(filename="|CATALOG", raw_data=catalog_data)

    def _parse_viola(self) -> ViolaFile:
        """
        Parses the |VIOLA internal file.
        """
        if "|VIOLA" not in self.directory.files:
            return None

        viola_offset = self.directory.files["|VIOLA"]
        # We need to read the file header to know the size of the |VIOLA file
        file_header_data = self.data[viola_offset : viola_offset + 9]
        reserved_space, used_space, file_flags = struct.unpack("<llB", file_header_data)

        viola_data = self.data[viola_offset + 9 : viola_offset + 9 + used_space]
        return ViolaFile(filename="|VIOLA", raw_data=viola_data)

    def _parse_gmacros(self) -> GMacrosFile:
        """
        Parses the |GMACROS internal file.
        """
        if "|GMACROS" not in self.directory.files:
            return None

        gmacros_offset = self.directory.files["|GMACROS"]
        # We need to read the file header to know the size of the |GMACROS file
        file_header_data = self.data[gmacros_offset : gmacros_offset + 9]
        reserved_space, used_space, file_flags = struct.unpack("<llB", file_header_data)

        gmacros_data = self.data[gmacros_offset + 9 : gmacros_offset + 9 + used_space]
        return GMacrosFile(filename="|GMACROS", raw_data=gmacros_data)

    def _parse_phrindex(self) -> PhrIndexFile:
        """
        Parses the |PhrIndex internal file.
        """
        if "|PhrIndex" not in self.directory.files:
            return None

        phrindex_offset = self.directory.files["|PhrIndex"]
        # We need to read the file header to know the size of the |PhrIndex file
        file_header_data = self.data[phrindex_offset : phrindex_offset + 9]
        reserved_space, used_space, file_flags = struct.unpack("<llB", file_header_data)

        phrindex_data = self.data[phrindex_offset + 9 : phrindex_offset + 9 + used_space]
        return PhrIndexFile(filename="|PhrIndex", raw_data=phrindex_data)
