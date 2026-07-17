"""Parsers for GID-specific internal files.

Based on helpfile.md documentation, GID files created by WinHlp32 contain
several specific internal files that are not present in regular HLP files.
"""

from .base import InternalFile
from typing import Optional, List, Any
from ..btree import BTree


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

    From helpfile.md:
    "This file has been seen in WinHlp32 GID files but is currently not understood."
    """

    def __init__(self, **data):
        super().__init__(**data)
        self._parse()

    def _parse(self):
        """Parse the |Flags file structure."""
        # Structure not understood according to reference documentation
        # Store raw data for potential future analysis
        pass


class CntJumpFile(InternalFile):
    """
    Parser for |CntJump internal file found in GID files.

    From helpfile.md:
    "This B+ tree stored in WinHlp32 GID files contains the jump references of
    the *.CNT file."
    """

    btree: Optional[BTree] = None
    jump_references: List[Any] = []

    def __init__(self, **data):
        super().__init__(**data)
        self.btree = None
        self.jump_references = []
        self._parse()

    def _parse(self):
        """Parse the |CntJump B+ tree structure."""
        if len(self.raw_data) < 38:  # Minimum size for B-tree header
            return

        try:
            self.btree = BTree(data=self.raw_data)
            self.jump_references = _extract_btree_string_keys(self.btree)
        except Exception:
            pass


class CntTextFile(InternalFile):
    """
    Parser for |CntText internal file found in GID files.

    From helpfile.md:
    "This B+ tree stored in WinHlp32 GID files contains the topic titles of the
    jumps from the *.CNT file."
    """

    btree: Optional[BTree] = None
    topic_titles: List[str] = []

    def __init__(self, **data):
        super().__init__(**data)
        self.btree = None
        self.topic_titles = []
        self._parse()

    def _parse(self):
        """Parse the |CntText B+ tree structure."""
        if len(self.raw_data) < 38:  # Minimum size for B-tree header
            return

        try:
            self.btree = BTree(data=self.raw_data)
            self.topic_titles = _extract_btree_string_keys(self.btree)
        except Exception:
            pass


def _extract_btree_string_keys(btree) -> List[str]:
    """Extract the NUL-terminated string key of each leaf entry from a B+ tree.

    The precise leaf record layout of |CntJump/|CntText is undocumented, but in
    every WinHelp B+ tree the entry begins with a NUL-terminated key string
    (here the jump reference / topic title) followed by a value. We read the key
    and skip a 4-byte value (the common stride); a malformed page just stops that
    page early. Best-effort: no corpus GID files exist to validate against.
    """
    keys: List[str] = []
    try:
        for page, n_entries in btree.iterate_leaf_pages():
            offset = 8  # leaf-page header
            for _ in range(n_entries):
                if offset >= len(page):
                    break
                end = page.find(b"\x00", offset)
                if end == -1:
                    break
                key = page[offset:end].decode("cp1252", errors="replace")
                if key:
                    keys.append(key)
                offset = end + 1 + 4  # skip NUL + assumed 4-byte value
    except Exception:
        pass
    return keys
