"""Parser for the |CFn internal file."""

from .base import InternalFile
from typing import List


class CFnFile(InternalFile):
    """
    Parses the |CFn file, which contains configuration macros.

    From helpfile.md:
    The |CFn (where n is integer) internal file lists the macros defined in
    [CONFIG:n] sections of the help project file (HCW 4.00). The file contains as
    many macro strings as were specified one after another:

    STRINGZ Macro[]

    This is a simple sequential format where macros are stored as null-terminated
    strings one after another.
    """

    macros: List[str] = []
    config_number: int = 0

    def __init__(self, **data):
        super().__init__(**data)
        self.macros = []
        self.config_number = 0
        self._extract_config_number()
        self._parse()

    def _extract_config_number(self):
        """
        Extract the config number from the filename (e.g., |CF0 -> 0, |CF1 -> 1).
        """
        if self.filename and self.filename.startswith("|CF"):
            try:
                self.config_number = int(self.filename[3:])
            except ValueError:
                self.config_number = 0

    def _parse(self):
        """
        Parses the |CFn file data.
        """
        if len(self.raw_data) < 9:  # Need at least file header
            return

        # Skip the file header (9 bytes: reserved_space + used_space + file_flags)
        data_start = 9
        cfn_data = self.raw_data[data_start:]

        # Parse null-terminated macro strings
        offset = 0
        while offset < len(cfn_data):
            # Find the next null terminator
            null_pos = cfn_data.find(b"\x00", offset)

            if null_pos == -1:
                # No more null terminators, read to end
                if offset < len(cfn_data):
                    macro_bytes = cfn_data[offset:]
                    macro = self._decode_string(macro_bytes)
                    if macro:  # Only add non-empty macros
                        self.macros.append(macro)
                break

            # Extract the macro string
            macro_bytes = cfn_data[offset:null_pos]
            macro = self._decode_string(macro_bytes)

            if macro:  # Only add non-empty macros
                self.macros.append(macro)

            # Move past the null terminator
            offset = null_pos + 1

    def _decode_string(self, data: bytes) -> str:
        """
        Decode string data using appropriate encoding.
        Falls back through multiple encodings to handle international text.
        """
        if not data:
            return ""

        # Try common Windows encodings
        encodings = ["cp1252", "cp1251", "utf-8", "latin-1"]

        for encoding in encodings:
            try:
                return data.decode(encoding)
            except UnicodeDecodeError:
                continue

        # Final fallback: decode with errors='replace' to avoid crashes
        return data.decode("cp1252", errors="replace")

    def get_macros(self) -> List[str]:
        """
        Returns all macros in the configuration file.

        Returns:
            List of macro strings
        """
        return self.macros.copy()

    def get_macro_count(self) -> int:
        """
        Returns the number of macros in the configuration file.

        Returns:
            Number of macros
        """
        return len(self.macros)

    def get_config_number(self) -> int:
        """
        Returns the configuration number extracted from the filename.

        Returns:
            Configuration number (0 if not determinable)
        """
        return self.config_number

    def get_macro_by_index(self, index: int) -> str:
        """
        Gets a macro by its index.

        Args:
            index: Zero-based index of the macro

        Returns:
            Macro string, or empty string if index is out of range
        """
        if 0 <= index < len(self.macros):
            return self.macros[index]
        return ""

    def find_macros_by_pattern(self, pattern: str) -> List[tuple]:
        """
        Find macros containing a pattern (case insensitive).

        Args:
            pattern: String pattern to search for

        Returns:
            List of (index, macro) tuples matching the pattern
        """
        pattern_lower = pattern.lower()
        matches = []

        for i, macro in enumerate(self.macros):
            if pattern_lower in macro.lower():
                matches.append((i, macro))

        return matches

    def get_macros_sorted(self) -> List[str]:
        """
        Get all macros sorted alphabetically.

        Returns:
            List of macro strings sorted alphabetically
        """
        return sorted(self.macros)

    def get_statistics(self) -> dict:
        """
        Returns statistics about the CFn data.

        Returns:
            Dictionary with CFn statistics
        """
        if not self.macros:
            return {
                "config_number": self.config_number,
                "total_macros": 0,
                "data_size": len(self.raw_data),
                "average_macro_length": 0,
                "max_macro_length": 0,
                "min_macro_length": 0,
                "longest_macro": "",
                "shortest_macro": "",
            }

        macro_lengths = [len(macro) for macro in self.macros]
        avg_macro_length = sum(macro_lengths) / len(macro_lengths)
        max_macro_length = max(macro_lengths)
        min_macro_length = min(macro_lengths)

        return {
            "config_number": self.config_number,
            "total_macros": len(self.macros),
            "data_size": len(self.raw_data),
            "average_macro_length": avg_macro_length,
            "max_macro_length": max_macro_length,
            "min_macro_length": min_macro_length,
            "longest_macro": max(self.macros, key=len),
            "shortest_macro": min(self.macros, key=len),
        }
