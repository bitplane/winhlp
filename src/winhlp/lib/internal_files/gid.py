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
            # TODO: Parse jump references from B+ tree entries
            # This would require understanding the specific entry format
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
            # TODO: Parse topic titles from B+ tree entries
            # This would require understanding the specific entry format
        except Exception:
            pass
