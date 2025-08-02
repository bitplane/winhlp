"""Parser for the |CONTEXT internal file."""

from .base import InternalFile
from ..btree import BTree
from pydantic import BaseModel
from typing import Optional, Dict
import struct


class ContextIndexEntry(BaseModel):
    """
    Structure for |CONTEXT index-page entries.
    From `helpfile.md`: CONTEXTINDEXENTRY
    """

    hash_value: int
    page_number: int
    raw_data: dict


class ContextLeafEntry(BaseModel):
    """
    Structure for |CONTEXT leaf-page entries.
    From `helpfile.md`: CONTEXTLEAFENTRY
    """

    hash_value: int
    topic_offset: int
    raw_data: dict


class ContextFile(InternalFile):
    """
    Parses the |CONTEXT file, which contains context name hash values
    and their associated topic offsets. Used in WinHelp 3.1+.

    From helpfile.md:
    Windows 3.1 (HC31) uses hash values of context names to identify topics.
    To get the location of the topic, search the B+ tree of the internal file |CONTEXT.
    """

    btree: Optional[BTree] = None
    context_map: Dict[int, int] = {}  # hash_value -> topic_offset

    def __init__(self, **data):
        super().__init__(**data)
        self._parse()

    def _parse(self):
        """
        Parses the |CONTEXT file data using the B+ tree structure.
        """
        if len(self.raw_data) < 9:  # Need at least file header
            return

        # Skip the file header (parsed by Directory class)
        btree_data = self.raw_data
        self.btree = BTree(data=btree_data)
        self._parse_context_entries()

    def _parse_context_entries(self):
        """
        Parses context entries from the B+ tree leaf pages.
        """
        if not self.btree:
            return

        for page, n_entries in self.btree.iterate_leaf_pages():
            offset = 8  # Skip page header

            for _ in range(n_entries):
                if offset + 8 > len(page):
                    break

                hash_value, topic_offset = struct.unpack("<ll", page[offset : offset + 8])

                parsed_entry = {
                    "hash_value": hash_value,
                    "topic_offset": topic_offset,
                }

                # Create structured entry (validates data and maintains consistency)
                ContextLeafEntry(**parsed_entry, raw_data={"raw": page[offset : offset + 8], "parsed": parsed_entry})

                # Store in our hash map for quick lookup
                self.context_map[hash_value] = topic_offset
                offset += 8

    def get_topic_offset_for_hash(self, hash_value: int) -> Optional[int]:
        """
        Gets the topic offset for a given context name hash value.
        """
        return self.context_map.get(hash_value)

    @staticmethod
    def calculate_hash(context_name: str) -> int:
        """
        Calculates the hash value for a context name using the algorithm from helpfile.md.

        From helpfile.md:
        The hash value for an empty string is 1.
        Only 0-9, A-Z, a-z, _ and . are legal characters for context ids in Win 3.1 (HC31).

        Note: The hash table contains signed byte values. Values > 0x7F are negative.
        """
        # Hash table from helpfile.md - these are SIGNED byte values
        hash_table = [
            0x00,
            0xD1,
            0xD2,
            0xD3,
            0xD4,
            0xD5,
            0xD6,
            0xD7,
            0xD8,
            0xD9,
            0xDA,
            0xDB,
            0xDC,
            0xDD,
            0xDE,
            0xDF,
            0xE0,
            0xE1,
            0xE2,
            0xE3,
            0xE4,
            0xE5,
            0xE6,
            0xE7,
            0xE8,
            0xE9,
            0xEA,
            0xEB,
            0xEC,
            0xED,
            0xEE,
            0xEF,
            0xF0,
            0x0B,
            0xF2,
            0xF3,
            0xF4,
            0xF5,
            0xF6,
            0xF7,
            0xF8,
            0xF9,
            0xFA,
            0xFB,
            0xFC,
            0xFD,
            0x0C,
            0xFF,
            0x0A,
            0x01,
            0x02,
            0x03,
            0x04,
            0x05,
            0x06,
            0x07,
            0x08,
            0x09,
            0x0A,
            0x0B,
            0x0C,
            0x0D,
            0x0E,
            0x0F,
            0x10,
            0x11,
            0x12,
            0x13,
            0x14,
            0x15,
            0x16,
            0x17,
            0x18,
            0x19,
            0x1A,
            0x1B,
            0x1C,
            0x1D,
            0x1E,
            0x1F,
            0x20,
            0x21,
            0x22,
            0x23,
            0x24,
            0x25,
            0x26,
            0x27,
            0x28,
            0x29,
            0x2A,
            0x0B,
            0x0C,
            0x0D,
            0x0E,
            0x0D,
            0x10,
            0x11,
            0x12,
            0x13,
            0x14,
            0x15,
            0x16,
            0x17,
            0x18,
            0x19,
            0x1A,
            0x1B,
            0x1C,
            0x1D,
            0x1E,
            0x1F,
            0x20,
            0x21,
            0x22,
            0x23,
            0x24,
            0x25,
            0x26,
            0x27,
            0x28,
            0x29,
            0x2A,
            0x2B,
            0x2C,
            0x2D,
            0x2E,
            0x2F,
            0x50,
            0x51,
            0x52,
            0x53,
            0x54,
            0x55,
            0x56,
            0x57,
            0x58,
            0x59,
            0x5A,
            0x5B,
            0x5C,
            0x5D,
            0x5E,
            0x5F,
            0x60,
            0x61,
            0x62,
            0x63,
            0x64,
            0x65,
            0x66,
            0x67,
            0x68,
            0x69,
            0x6A,
            0x6B,
            0x6C,
            0x6D,
            0x6E,
            0x6F,
            0x70,
            0x71,
            0x72,
            0x73,
            0x74,
            0x75,
            0x76,
            0x77,
            0x78,
            0x79,
            0x7A,
            0x7B,
            0x7C,
            0x7D,
            0x7E,
            0x7F,
            0x80,
            0x81,
            0x82,
            0x83,
            0x0B,
            0x85,
            0x86,
            0x87,
            0x88,
            0x89,
            0x8A,
            0x8B,
            0x8C,
            0x8D,
            0x8E,
            0x8F,
            0x90,
            0x91,
            0x92,
            0x93,
            0x94,
            0x95,
            0x96,
            0x97,
            0x98,
            0x99,
            0x9A,
            0x9B,
            0x9C,
            0x9D,
            0x9E,
            0x9F,
            0xA0,
            0xA1,
            0xA2,
            0xA3,
            0xA4,
            0xA5,
            0xA6,
            0xA7,
            0xA8,
            0xA9,
            0xAA,
            0xAB,
            0xAC,
            0xAD,
            0xAE,
            0xAF,
            0xB0,
            0xB1,
            0xB2,
            0xB3,
            0xB4,
            0xB5,
            0xB6,
            0xB7,
            0xB8,
            0xB9,
            0xBA,
            0xBB,
            0xBC,
            0xBD,
            0xBE,
            0xBF,
            0xC0,
            0xC1,
            0xC2,
            0xC3,
            0xC4,
            0xC5,
            0xC6,
            0xC7,
            0xC8,
            0xC9,
            0xCA,
            0xCB,
            0xCC,
            0xCD,
            0xCE,
            0xCF,
        ]

        if not context_name:
            return 1

        hash_value = 0
        for char in context_name:
            char_code = ord(char)
            if char_code < 256:
                table_value = hash_table[char_code]
                # Convert to signed byte if necessary (values > 0x7F are negative)
                if table_value > 0x7F:
                    table_value = table_value - 256
                hash_value = hash_value * 43 + table_value
                # Keep as 32-bit signed integer
                if hash_value > 0x7FFFFFFF:
                    hash_value = hash_value - 0x100000000
                elif hash_value < -0x80000000:
                    hash_value = hash_value + 0x100000000

        # Return as unsigned 32-bit value
        return hash_value & 0xFFFFFFFF

    @staticmethod
    def reverse_hash(hash_value: int) -> str:
        """
        Attempts to reverse a hash value back to a context name.

        Based on the unhash() function from helpdeco.c.
        This generates a context ID that produces the given hash value.
        """
        # Character lookup table from helpdeco.c (untable)
        # Maps remainders to valid characters
        untable = [
            0,  # 0
            "1",  # 1
            "2",  # 2
            "3",  # 3
            "4",  # 4
            "5",  # 5
            "6",  # 6
            "7",  # 7
            "8",  # 8
            "9",  # 9
            "0",  # 10
            0,  # 11
            ".",  # 12
            "_",  # 13
            0,  # 14
            0,  # 15
            0,  # 16
            "A",  # 17
            "B",  # 18
            "C",  # 19
            "D",  # 20
            "E",  # 21
            "F",  # 22
            "G",  # 23
            "H",  # 24
            "I",  # 25
            "J",  # 26
            "K",  # 27
            "L",  # 28
            "M",  # 29
            "N",  # 30
            "O",  # 31
            "P",  # 32
            "Q",  # 33
            "R",  # 34
            "S",  # 35
            "T",  # 36
            "U",  # 37
            "V",  # 38
            "W",  # 39
            "X",  # 40
            "Y",  # 41
            "Z",  # 42
        ]

        if hash_value == 1:
            return ""  # Empty string hashes to 1

        # Try all possible starting remainders (0-42)
        for i in range(43):
            buffer = []
            # Work backwards from the end of a 14-char buffer
            j = 14

            # 64-bit division simulation using 32-bit parts
            hashlo = hash_value & 0xFFFFFFFF
            hashhi = i

            while True:
                # Divide by 43 using long division
                # 43 * 0x80000000 = 0x558000000 (divhi=21, divlo=0x80000000)
                divhi = 21
                divlo = 0x80000000
                result = 0

                # Perform 64-bit division bit by bit
                for bit in range(31, -1, -1):
                    mask = 1 << bit

                    # Check if we can subtract divisor
                    if hashhi > divhi or (hashhi == divhi and hashlo >= divlo):
                        result |= mask
                        hashhi -= divhi
                        if divlo > hashlo:
                            hashhi -= 1
                        hashlo = (hashlo - divlo) & 0xFFFFFFFF

                    # Shift divisor right by 1
                    divlo >>= 1
                    if divhi & 1:
                        divlo |= 0x80000000
                    divhi >>= 1

                # The remainder is in hashlo (0-42)
                if hashlo < len(untable):
                    ch = untable[hashlo]
                    if not ch:
                        break
                    buffer.insert(0, ch)
                    j -= 1
                else:
                    break

                # If quotient is 0, we found a valid string
                if result == 0:
                    return "".join(buffer)

                # Continue with quotient as new value
                hashlo = result
                hashhi = 0

        # Fallback: create a unique identifier based on the hash
        return f"CTX_{hash_value:08X}"

    @staticmethod
    def derive_from_title(title: str, desired_hash: int, win95: bool = False) -> Optional[str]:
        """
        Attempts to derive a context ID from a topic title that matches the desired hash.

        Based on the Derive() function from helpdeco.c.
        Many authoring systems create context IDs from topic titles by:
        - Replacing illegal characters with _ or . or leaving them out
        - Using only part of the topic title
        - Prefixing with idh_ or helpid_

        Args:
            title: The topic title to derive from
            desired_hash: The hash value we're trying to match
            win95: Whether to use Win95 character rules (allows more chars)

        Returns:
            A context ID that hashes to desired_hash, or None if not found
        """
        # Common prefixes used by authoring systems
        prefixes = ["", "idh_", "helpid_"]
        prefix_hashes = [0]
        for prefix in prefixes[1:]:
            prefix_hashes.append(ContextFile.calculate_hash(prefix))

        # Create oldtable for Win 3.1 valid characters (more restrictive)
        oldtable = [0] * 256
        # Numbers
        for i in range(9):
            oldtable[ord("1") + i] = i + 1
        oldtable[ord("0")] = 10
        # Special chars
        oldtable[ord(".")] = 12
        oldtable[ord("_")] = 13
        # Letters (case insensitive)
        for i in range(26):
            oldtable[ord("A") + i] = 17 + i
            oldtable[ord("a") + i] = 17 + i

        title_len = len(title)

        # Try three strategies for handling illegal characters
        strategies = []
        if not win95:
            strategies.append(1)  # Skip illegal chars
        strategies.append(0)  # Win95 mode - allow all chars
        if not win95:
            strategies.append(2)  # Replace illegal chars with _

        for strategy in strategies:
            for prefix_idx, prefix in enumerate(prefixes):
                k = 0  # Starting position in title

                while k < title_len:
                    hash_value = prefix_hashes[prefix_idx]
                    buffer = prefix

                    # Build candidate ID from title starting at position k
                    for m in range(k, title_len):
                        ch = title[m]
                        ch_code = ord(ch)

                        if strategy > 0:  # Win 3.1 mode
                            if ch_code < 256:
                                n = oldtable[ch_code]
                            else:
                                n = 0

                            if n == 0:
                                if strategy == 2:
                                    # Replace illegal char with _
                                    ch = "_"
                                    n = oldtable[ord("_")]
                                else:
                                    # Skip illegal char
                                    continue
                        else:  # Win95 mode
                            if ch_code < 256:
                                n = ContextFile._get_hash_table_value(ch_code)
                                if n == 0:
                                    continue
                            else:
                                continue

                        buffer += ch
                        hash_value = hash_value * 43 + n
                        # Keep as 32-bit signed like in calculate_hash
                        if hash_value > 0x7FFFFFFF:
                            hash_value = hash_value - 0x100000000
                        elif hash_value < -0x80000000:
                            hash_value = hash_value + 0x100000000
                        hash_value = hash_value & 0xFFFFFFFF

                        # Check if we can complete this to match desired_hash
                        # Try adding up to 6 more characters
                        for suffix_len in range(7):
                            if suffix_len == 0:
                                if hash_value == desired_hash:
                                    return buffer
                            else:
                                # Calculate what suffix would be needed
                                remaining = desired_hash - hash_value * (43**suffix_len)
                                if remaining >= 0 and remaining < 43**suffix_len:
                                    # Try to construct a valid suffix
                                    suffix = ContextFile._try_construct_suffix(remaining, suffix_len)
                                    if suffix and (
                                        ContextFile._find_substring_in_title(title, title_len, suffix)
                                        or len(suffix) < 3
                                    ):
                                        test_id = buffer + suffix
                                        if ContextFile.calculate_hash(test_id) == desired_hash:
                                            return test_id

                    # Move to next starting position
                    old_k = k
                    # Skip past characters based on strategy
                    if strategy > 0:  # Win 3.1
                        # Skip valid characters
                        while k < title_len and ord(title[k]) < 256 and oldtable[ord(title[k])] != 0:
                            k += 1
                        # Then skip invalid characters
                        while k < title_len and ord(title[k]) < 256 and oldtable[ord(title[k])] == 0:
                            k += 1
                    else:  # Win95
                        # Skip valid characters
                        while (
                            k < title_len
                            and ord(title[k]) < 256
                            and ContextFile._get_hash_table_value(ord(title[k])) != 0
                        ):
                            k += 1
                        # Then skip invalid characters
                        while (
                            k < title_len
                            and ord(title[k]) < 256
                            and ContextFile._get_hash_table_value(ord(title[k])) == 0
                        ):
                            k += 1

                    if k == old_k:  # Didn't advance, force increment
                        k += 1

        return None

    @staticmethod
    def _try_construct_suffix(remaining_hash: int, length: int) -> Optional[str]:
        """Try to construct a valid suffix of given length that produces remaining_hash."""
        untable = [
            0,
            "1",
            "2",
            "3",
            "4",
            "5",
            "6",
            "7",
            "8",
            "9",
            "0",
            0,
            ".",
            "_",
            0,
            0,
            0,
            "A",
            "B",
            "C",
            "D",
            "E",
            "F",
            "G",
            "H",
            "I",
            "J",
            "K",
            "L",
            "M",
            "N",
            "O",
            "P",
            "Q",
            "R",
            "S",
            "T",
            "U",
            "V",
            "W",
            "X",
            "Y",
            "Z",
        ]

        suffix = []
        h = remaining_hash

        for _ in range(length):
            if h == 0:
                break
            remainder = h % 43
            if remainder < len(untable) and untable[remainder] and untable[remainder] != 0:
                suffix.insert(0, untable[remainder])
                h //= 43
            else:
                return None

        return "".join(suffix) if h == 0 else None

    @staticmethod
    def _find_substring_in_title(title: str, title_len: int, substring: str) -> bool:
        """Check if substring appears in title (case insensitive using hash table)."""
        sub_len = len(substring)
        if sub_len > title_len:
            return False

        for i in range(title_len - sub_len + 1):
            match = True
            for j in range(sub_len):
                # Compare using hash table values for case-insensitive match
                title_char = ord(title[i + j]) if i + j < len(title) else 0
                sub_char = ord(substring[j]) if j < len(substring) else 0

                if title_char >= 256 or sub_char >= 256:
                    if title_char != sub_char:
                        match = False
                        break
                elif ContextFile._get_hash_table_value(title_char) != ContextFile._get_hash_table_value(sub_char):
                    match = False
                    break

            if match:
                return True

        return False

    @staticmethod
    def _get_hash_table_value(char_code: int) -> int:
        """Helper method to get hash table value for a character code.

        Returns the signed byte value from the hash table.
        """
        hash_table = [
            0x00,
            0xD1,
            0xD2,
            0xD3,
            0xD4,
            0xD5,
            0xD6,
            0xD7,
            0xD8,
            0xD9,
            0xDA,
            0xDB,
            0xDC,
            0xDD,
            0xDE,
            0xDF,
            0xE0,
            0xE1,
            0xE2,
            0xE3,
            0xE4,
            0xE5,
            0xE6,
            0xE7,
            0xE8,
            0xE9,
            0xEA,
            0xEB,
            0xEC,
            0xED,
            0xEE,
            0xEF,
            0xF0,
            0x0B,
            0xF2,
            0xF3,
            0xF4,
            0xF5,
            0xF6,
            0xF7,
            0xF8,
            0xF9,
            0xFA,
            0xFB,
            0xFC,
            0xFD,
            0x0C,
            0xFF,
            0x0A,
            0x01,
            0x02,
            0x03,
            0x04,
            0x05,
            0x06,
            0x07,
            0x08,
            0x09,
            0x0A,
            0x0B,
            0x0C,
            0x0D,
            0x0E,
            0x0F,
            0x10,
            0x11,
            0x12,
            0x13,
            0x14,
            0x15,
            0x16,
            0x17,
            0x18,
            0x19,
            0x1A,
            0x1B,
            0x1C,
            0x1D,
            0x1E,
            0x1F,
            0x20,
            0x21,
            0x22,
            0x23,
            0x24,
            0x25,
            0x26,
            0x27,
            0x28,
            0x29,
            0x2A,
            0x0B,
            0x0C,
            0x0D,
            0x0E,
            0x0D,
            0x10,
            0x11,
            0x12,
            0x13,
            0x14,
            0x15,
            0x16,
            0x17,
            0x18,
            0x19,
            0x1A,
            0x1B,
            0x1C,
            0x1D,
            0x1E,
            0x1F,
            0x20,
            0x21,
            0x22,
            0x23,
            0x24,
            0x25,
            0x26,
            0x27,
            0x28,
            0x29,
            0x2A,
            0x2B,
            0x2C,
            0x2D,
            0x2E,
            0x2F,
            0x50,
            0x51,
            0x52,
            0x53,
            0x54,
            0x55,
            0x56,
            0x57,
            0x58,
            0x59,
            0x5A,
            0x5B,
            0x5C,
            0x5D,
            0x5E,
            0x5F,
            0x60,
            0x61,
            0x62,
            0x63,
            0x64,
            0x65,
            0x66,
            0x67,
            0x68,
            0x69,
            0x6A,
            0x6B,
            0x6C,
            0x6D,
            0x6E,
            0x6F,
            0x70,
            0x71,
            0x72,
            0x73,
            0x74,
            0x75,
            0x76,
            0x77,
            0x78,
            0x79,
            0x7A,
            0x7B,
            0x7C,
            0x7D,
            0x7E,
            0x7F,
            0x80,
            0x81,
            0x82,
            0x83,
            0x0B,
            0x85,
            0x86,
            0x87,
            0x88,
            0x89,
            0x8A,
            0x8B,
            0x8C,
            0x8D,
            0x8E,
            0x8F,
            0x90,
            0x91,
            0x92,
            0x93,
            0x94,
            0x95,
            0x96,
            0x97,
            0x98,
            0x99,
            0x9A,
            0x9B,
            0x9C,
            0x9D,
            0x9E,
            0x9F,
            0xA0,
            0xA1,
            0xA2,
            0xA3,
            0xA4,
            0xA5,
            0xA6,
            0xA7,
            0xA8,
            0xA9,
            0xAA,
            0xAB,
            0xAC,
            0xAD,
            0xAE,
            0xAF,
            0xB0,
            0xB1,
            0xB2,
            0xB3,
            0xB4,
            0xB5,
            0xB6,
            0xB7,
            0xB8,
            0xB9,
            0xBA,
            0xBB,
            0xBC,
            0xBD,
            0xBE,
            0xBF,
            0xC0,
            0xC1,
            0xC2,
            0xC3,
            0xC4,
            0xC5,
            0xC6,
            0xC7,
            0xC8,
            0xC9,
            0xCA,
            0xCB,
            0xCC,
            0xCD,
            0xCE,
            0xCF,
        ]

        if char_code < len(hash_table):
            value = hash_table[char_code]
            # Convert to signed byte if necessary (values > 0x7F are negative)
            if value > 0x7F:
                value = value - 256
            return value
        return 0
