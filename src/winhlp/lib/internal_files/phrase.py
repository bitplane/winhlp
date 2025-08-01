"""Parser for the |PHRASE internal file."""

from .base import InternalFile
from pydantic import BaseModel
from typing import List, Optional
from ..compression import lz77_decompress
import struct


class PhraseHeader30(BaseModel):
    """
    Header for Windows 3.0 |PHRASE file.
    From `helpfile.md`.
    """

    num_phrases: int
    one_hundred: int  # Should be 0x0100
    phrase_offsets: List[int]
    raw_data: dict


class PhraseHeader31(BaseModel):
    """
    Header for Windows 3.1+ |PHRASE file.
    From `helpfile.md`.
    """

    num_phrases: int
    one_hundred: int  # Should be 0x0100
    decompressed_size: int
    phrase_offsets: List[int]
    raw_data: dict


class PhraseFile(InternalFile):
    """
    Parses the |PHRASE file, which contains phrase compression tables.

    From helpfile.md:
    If the help file is phrase compressed, it contains an internal file named
    |Phrases. Windows 3.0 help files generated with HC30 use uncompressed structure.
    Windows 3.1 help files generated using HC31 and later always LZ77 compress
    the Phrase character array.
    """

    header: Optional[PhraseHeader30 | PhraseHeader31] = None
    phrases: List[str] = []
    is_compressed: bool = False

    def __init__(self, **data):
        super().__init__(**data)
        self._parse()

    def _parse(self):
        """
        Parses the |PHRASE file data.
        """
        if len(self.raw_data) < 4:
            return

        self._parse_header()
        self._parse_phrases()

    def _parse_header(self):
        """
        Parses the phrase file header.
        """
        # Read the first 4 bytes to determine format
        num_phrases, one_hundred = struct.unpack("<HH", self.raw_data[:4])

        if len(self.raw_data) >= 10:
            # Check if this might be a WinHelp 3.1+ format with decompressed_size
            potential_decompressed_size = struct.unpack("<l", self.raw_data[4:8])[0]

            # If decompressed_size looks reasonable and we have enough data, assume 3.1+ format
            if potential_decompressed_size > 0 and potential_decompressed_size < 1000000:
                self.is_compressed = True
                decompressed_size = potential_decompressed_size

                # Read phrase offsets
                phrase_offsets = []
                offset = 8
                for i in range(num_phrases + 1):
                    if offset + 2 > len(self.raw_data):
                        break
                    phrase_offset = struct.unpack("<H", self.raw_data[offset : offset + 2])[0]
                    phrase_offsets.append(phrase_offset)
                    offset += 2

                parsed_header = {
                    "num_phrases": num_phrases,
                    "one_hundred": one_hundred,
                    "decompressed_size": decompressed_size,
                    "phrase_offsets": phrase_offsets,
                }

                self.header = PhraseHeader31(
                    **parsed_header, raw_data={"raw": self.raw_data[:offset], "parsed": parsed_header}
                )
            else:
                self._parse_header_30(num_phrases, one_hundred)
        else:
            self._parse_header_30(num_phrases, one_hundred)

    def _parse_header_30(self, num_phrases: int, one_hundred: int):
        """
        Parses Windows 3.0 format header.
        """
        # Read phrase offsets
        phrase_offsets = []
        offset = 4
        for i in range(num_phrases + 1):
            if offset + 2 > len(self.raw_data):
                break
            phrase_offset = struct.unpack("<H", self.raw_data[offset : offset + 2])[0]
            phrase_offsets.append(phrase_offset)
            offset += 2

        parsed_header = {
            "num_phrases": num_phrases,
            "one_hundred": one_hundred,
            "phrase_offsets": phrase_offsets,
        }

        self.header = PhraseHeader30(**parsed_header, raw_data={"raw": self.raw_data[:offset], "parsed": parsed_header})

    def _parse_phrases(self):
        """
        Parses the phrase strings.
        """
        if not self.header or not self.header.phrase_offsets:
            return

        if self.is_compressed and isinstance(self.header, PhraseHeader31):
            self._parse_phrases_compressed()
        else:
            self._parse_phrases_uncompressed()

    def _parse_phrases_uncompressed(self):
        """
        Parses uncompressed phrases (Windows 3.0 format).
        """
        if not isinstance(self.header, PhraseHeader30):
            return

        # Calculate offset to phrase data
        phrase_data_offset = 4 + 2 * (self.header.num_phrases + 1)
        phrase_data = self.raw_data[phrase_data_offset:]

        # Extract each phrase using the offsets
        for i in range(self.header.num_phrases):
            start_offset = self.header.phrase_offsets[i] - self.header.phrase_offsets[0]
            end_offset = self.header.phrase_offsets[i + 1] - self.header.phrase_offsets[0]

            if start_offset >= 0 and end_offset <= len(phrase_data) and start_offset < end_offset:
                phrase_bytes = phrase_data[start_offset:end_offset]
                # Phrases are not null-terminated, use the offset difference for length
                phrase = phrase_bytes.decode("latin-1", errors="ignore")
                self.phrases.append(phrase)

    def _parse_phrases_compressed(self):
        """
        Parses LZ77 compressed phrases (Windows 3.1+ format).
        """
        if not isinstance(self.header, PhraseHeader31):
            return

        # Calculate offset to compressed phrase data
        phrase_data_offset = 8 + 2 * (self.header.num_phrases + 1)
        compressed_data = self.raw_data[phrase_data_offset:]

        # Decompress the phrase data
        try:
            decompressed_data = lz77_decompress(compressed_data)
        except Exception:
            # If decompression fails, fall back to treating as uncompressed
            decompressed_data = compressed_data

        # Extract each phrase using the offsets
        for i in range(self.header.num_phrases):
            start_offset = self.header.phrase_offsets[i] - self.header.phrase_offsets[0]
            end_offset = self.header.phrase_offsets[i + 1] - self.header.phrase_offsets[0]

            if start_offset >= 0 and end_offset <= len(decompressed_data) and start_offset < end_offset:
                phrase_bytes = decompressed_data[start_offset:end_offset]
                phrase = phrase_bytes.decode("latin-1", errors="ignore")
                self.phrases.append(phrase)

    def get_phrase(self, phrase_number: int) -> Optional[str]:
        """
        Gets a phrase by its number.
        """
        if 0 <= phrase_number < len(self.phrases):
            return self.phrases[phrase_number]
        return None
