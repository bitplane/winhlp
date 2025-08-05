"""Parses the internal file directory of a HLP file."""

from pydantic import BaseModel, Field
from typing import Optional
from .btree import BTree
import struct


class FileHeader(BaseModel):
    """
    Structure at the start of each internal file.
    From `helpdeco.h`: FILEHEADER
    """

    reserved_space: int = Field(..., description="Size reserved including FILEHEADER")
    used_space: int = Field(..., description="Size of the internal file in bytes")
    file_flags: int = Field(..., description="Normally 4")
    raw_data: dict


class DirectoryLeafEntry(BaseModel):
    """
    The structure of directory leaf-pages.

    From `helpfile.md`:
    struct
    {
        STRINGZ FileName     varying length NUL-terminated string
        long FileOffset      offset of FILEHEADER of internal file FileName
                             relative to beginning of help file
    }
    DIRECTORYLEAFENTRY[NEntries]
    """

    filename: str
    file_offset: int
    raw_data: dict


class Directory(BaseModel):
    """
    The internal directory which is used to associate FileNames and FileOffsets.
    The directory is structured as a B+ tree.
    """

    file_header: Optional[FileHeader] = None
    btree: Optional[BTree] = None
    files: dict = {}

    def __init__(self, data: bytes, **kwargs):
        super().__init__(**kwargs)
        self._parse(data)

    def _parse(self, data: bytes):
        """
        Parses the directory from the given data.
        """
        self._parse_file_header(data)
        btree_data = data[9 : 9 + self.file_header.used_space]
        self.btree = BTree(data=btree_data)
        self._parse_files()

    def _parse_file_header(self, data: bytes):
        """
        Parses the file header of the directory.

        From `helpfile.md`:
        long ReservedSpace     size reserved including FILEHEADER
        long UsedSpace         size of internal file in bytes
        unsigned char FileFlags      normally 4

        From `helpdeco.h`:
        typedef struct FILEHEADER    /* structure at FileOffset of each internal file */
        {
            int32_t ReservedSpace;      /* reserved space in help file incl. FILEHEADER */
            int32_t UsedSpace;          /* used space in help file excl. FILEHEADER */
            unsigned char FileFlags; /* normally 4 */
        }
        FILEHEADER;

        From `helpdec1.c`:
        s(FILEHEADER)
        d(ReservedSpace)
        d(UsedSpace)
        b(FileFlags)
        e
        """
        raw_bytes = data[:9]
        if len(raw_bytes) < 9:
            raise ValueError(f"Invalid directory file header size: {len(raw_bytes)} < 9 bytes")
        reserved_space, used_space, file_flags = struct.unpack("<llB", raw_bytes)
        parsed_header = {
            "reserved_space": reserved_space,
            "used_space": used_space,
            "file_flags": file_flags,
        }
        self.file_header = FileHeader(**parsed_header, raw_data={"raw": raw_bytes, "parsed": parsed_header})

    def _parse_files(self):
        """
        Parses the files from the B-Tree leaf pages.

        From `helpfile.md`:
        struct
        {
            STRINGZ FileName     varying length NUL-terminated string
            long FileOffset      offset of FILEHEADER of internal file FileName
                                 relative to beginning of help file
        }
        DIRECTORYLEAFENTRY[NEntries]

        From `helpdec1.c`:
        // SearchFile function shows the logic for traversing the B-Tree
        // to find a file.
        """

        def parse_directory_entry(page_data, offset):
            """Parse a single directory entry from page data."""
            # Find null-terminated filename
            end_of_string = page_data.find(b"\x00", offset)
            if end_of_string == -1:
                return None, offset

            filename = page_data[offset:end_of_string].decode("ascii", errors="ignore")
            offset = end_of_string + 1

            # Read file offset
            if offset + 4 > len(page_data):
                return None, offset  # Not enough data for file offset

            file_offset = struct.unpack_from("<l", page_data, offset)[0]
            offset += 4

            return (filename, file_offset), offset

        # Use the new iterator pattern
        for filename, file_offset in self.btree.iterate_leaf_entries_with_parser(parse_directory_entry):
            self.files[filename] = file_offset
