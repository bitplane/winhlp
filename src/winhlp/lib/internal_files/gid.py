"""Parsers for GID-specific internal files.

Based on helpfile.md documentation, GID files created by WinHlp32 contain
several specific internal files that are not present in regular HLP files.
"""

from .base import InternalFile
import struct
from typing import Dict, List, Optional
from ..btree import BTree

# |CntText keys for the CNT's :Title and :Base lines.
_TITLE_KEY = 70000
_BASE_KEY = 70001
_FLAGS_CONTENTS_OFFSET = 757


class WinPosFile(InternalFile):
    """
    Parser for |WinPos internal file found in GID files.

    From helpfile.md:
    "This file has been seen in WinHlp32 GID files, but always contained an empty
    Btree (with an unknown 'a' in the BTREEHEADER structure)."
    """

    btree: Optional[BTree] = None

    def __init__(self, **data):
        super().__init__(**data)
        self.btree = None
        self._parse()

    def _parse(self):
        """Parse the |WinPos file structure."""
        if len(self.raw_data) < 38:  # Minimum size for B-tree header
            return

        try:
            # Parse as B-tree structure as documented
            self.btree = BTree(data=self.raw_data)
        except Exception:
            # Expected to often be empty or malformed according to docs
            pass


class PeteFile(InternalFile):
    """
    Parser for |Pete internal file found in GID files.

    From helpfile.md:
    "This file has been seen in WinHlp32 GID files but is currently not understood."
    """

    def __init__(self, **data):
        super().__init__(**data)
        self._parse()

    def _parse(self):
        """Parse the |Pete file structure."""
        # Structure not understood according to reference documentation
        # Store raw data for potential future analysis
        pass


class FlagsFile(InternalFile):
    """
    Parser for |Flags internal file found in GID files.

    Undocumented in helpfile.md. Across the corpus GIDs, the DWORD at offset 12
    is the Contents entry count + 1 and one byte per entry starts at offset 757:
    the high nibble is the nesting level (1-based) and the low nibble the kind
    (0 = book, 2 = topic), matching the |CntText/|CntJump keys 1..N.
    """

    contents_flags: List[int] = []

    def __init__(self, **data):
        super().__init__(**data)
        self.contents_flags = []
        self._parse()

    def _parse(self):
        """Parse the per-entry Contents flags."""
        if len(self.raw_data) < _FLAGS_CONTENTS_OFFSET:
            return
        count = struct.unpack_from("<l", self.raw_data, 12)[0] - 1
        if count > 0:
            self.contents_flags = list(self.raw_data[_FLAGS_CONTENTS_OFFSET : _FLAGS_CONTENTS_OFFSET + count])


class CntJumpFile(InternalFile):
    """
    Parser for |CntJump internal file found in GID files.

    From helpfile.md:
    "This B+ tree stored in WinHlp32 GID files contains the jump references of
    the *.CNT file."

    ``jumps`` maps a Contents entry number to its ``context[@file][>window]``
    reference; books have no entry.
    """

    btree: Optional[BTree] = None
    jumps: Dict[int, str] = {}

    def __init__(self, **data):
        super().__init__(**data)
        self.btree = None
        self.jumps = {}
        self._parse()

    def _parse(self):
        """Parse the |CntJump B+ tree structure."""
        if len(self.raw_data) < 38:  # Minimum size for B-tree header
            return
        try:
            self.btree = BTree(data=self.raw_data)
            self.jumps = _extract_btree_entries(self.btree)
        except Exception:
            pass


class CntTextFile(InternalFile):
    """
    Parser for |CntText internal file found in GID files.

    From helpfile.md:
    "This B+ tree stored in WinHlp32 GID files contains the topic titles of the
    jumps from the *.CNT file."

    ``titles`` maps entry numbers 1..N to labels. Keys 70000 and 70001 hold the
    CNT's :Title and :Base lines.
    """

    btree: Optional[BTree] = None
    titles: Dict[int, str] = {}

    def __init__(self, **data):
        super().__init__(**data)
        self.btree = None
        self.titles = {}
        self._parse()

    def _parse(self):
        """Parse the |CntText B+ tree structure."""
        if len(self.raw_data) < 38:  # Minimum size for B-tree header
            return
        try:
            self.btree = BTree(data=self.raw_data)
            self.titles = _extract_btree_entries(self.btree)
        except Exception:
            pass

    @property
    def title(self) -> str:
        return self.titles.get(_TITLE_KEY, "")

    @property
    def base_file(self) -> str:
        return self.titles.get(_BASE_KEY, "")


def _extract_btree_entries(btree) -> Dict[int, str]:
    """Read the leaf entries of an ``Lz`` B+ tree: a 4-byte key then a NUL-terminated string."""
    entries: Dict[int, str] = {}
    for page, n_entries in btree.iterate_leaf_pages():
        offset = 8  # leaf-page header
        for _ in range(n_entries):
            end = page.find(b"\x00", offset + 4)
            if end == -1:
                break
            key = struct.unpack_from("<l", page, offset)[0]
            entries[key] = page[offset + 4 : end].decode("cp1252", errors="replace")
            offset = end + 1
    return entries


def gid_contents(cnttext: Optional[CntTextFile], cntjump: Optional[CntJumpFile], flags: Optional[FlagsFile]):
    """Rebuild the Contents tree a GID caches, in the same shape as a parsed .CNT."""
    from ..cnt import CntDocument, CntEntry

    if cnttext is None or not cnttext.titles:
        return None
    jumps = cntjump.jumps if cntjump is not None else {}
    levels = flags.contents_flags if flags is not None else []
    entries = []
    for number in sorted(key for key in cnttext.titles if 0 < key < _TITLE_KEY):
        reference = jumps.get(number, "")
        flag = levels[number - 1] if number <= len(levels) else 0
        entries.append(
            CntEntry(
                cnttext.titles[number],
                max(0, (flag >> 4) - 1),
                reference,
                "topic" if reference else "book",
                cnttext.base_file,
            )
        )
    return CntDocument(cnttext.title, cnttext.base_file, tuple(entries))
