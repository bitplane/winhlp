"""Parser for the |PhrImage internal file."""

from .base import InternalFile
from typing import List, Optional, Any
from ..compression import decompress


class PhrImageFile(InternalFile):
    """
    Parses the |PhrImage file, which contains phrase strings for Hall compression.

    Based on helldeco.c PhraseLoad function:
    The |PhrImage file stores the actual phrase strings used in Hall compression.
    It works with |PhrIndex to provide phrase compression in Windows 95 help files.

    From helpfile.md:
    The |PhrImage file stores the phrases. A phrase is not NUL-terminated. Use
    PhraseOffset[NumPhrase] and PhraseOffset[NumPhrase+1] to locate beginning
    and end of the phrase string. |PhrImage is LZ77 compressed if
    PhrImageCompressedSize is not equal to PhrImageSize.
    """

    decompressed_data: bytes = b""
    phrases: List[str] = []
    system_file: Any = None
    phr_index_file: Any = None

    def __init__(self, system_file: Any = None, phr_index_file: Any = None, **data):
        super().__init__(**data)
        self.system_file = system_file
        self.phr_index_file = phr_index_file
        self.phrases = []
        self.decompressed_data = b""
        self._parse()

    def _parse(self):
        """
        Parses the |PhrImage file data following helldeco.c logic.
        """
        if len(self.raw_data) < 9:  # Need at least file header
            return

        # Skip the file header (9 bytes: reserved_space + used_space + file_flags)
        data_start = 9
        phrimage_data = self.raw_data[data_start:]

        if not self.phr_index_file or not self.phr_index_file.header:
            # Without PhrIndex header info, store raw data
            self.decompressed_data = phrimage_data
            return

        header = self.phr_index_file.header

        # Decompress if needed (following helldeco.c logic)
        if header.phr_image_size == header.phr_image_compressed_size:
            # No compression
            self.decompressed_data = phrimage_data[: header.phr_image_size]
        else:
            # LZ77 compressed (method 2)
            try:
                self.decompressed_data = decompress(method=2, data=phrimage_data)
                # Truncate to expected size
                if len(self.decompressed_data) > header.phr_image_size:
                    self.decompressed_data = self.decompressed_data[: header.phr_image_size]
            except Exception:
                # Fallback to raw data if decompression fails
                self.decompressed_data = phrimage_data

        # Extract phrases using offsets from PhrIndex
        if self.phr_index_file and hasattr(self.phr_index_file, "phrases"):
            # Use phrases already parsed by PhrIndex
            self.phrases = self.phr_index_file.phrases
        else:
            # Try to parse phrases directly if we have phrase count info
            self._parse_phrases_direct()

    def _parse_phrases_direct(self):
        """
        Parse phrases directly from decompressed data if possible.
        This is a fallback when PhrIndex information is not available.
        """
        if not self.phr_index_file or not self.phr_index_file.header:
            return

        # Without proper phrase offsets, we can't reliably parse phrases
        # This would require the bit-stream algorithm from PhrIndex
        # For now, store empty phrases list - proper parsing happens in PhrIndex
        self.phrases = []

    def get_phrase(self, phrase_number: int) -> Optional[str]:
        """
        Gets a phrase by its number.

        Args:
            phrase_number: Zero-based phrase index

        Returns:
            The phrase string, or None if not found
        """
        if 0 <= phrase_number < len(self.phrases):
            return self.phrases[phrase_number]
        return None

    def get_phrase_count(self) -> int:
        """
        Returns the total number of phrases stored.
        """
        return len(self.phrases)

    def get_raw_phrase_data(self, start_offset: int, end_offset: int) -> bytes:
        """
        Gets raw phrase data between two offsets.

        Args:
            start_offset: Starting byte offset in decompressed data
            end_offset: Ending byte offset in decompressed data

        Returns:
            Raw phrase bytes, or empty bytes if invalid range
        """
        if (
            start_offset < 0
            or end_offset < start_offset
            or start_offset >= len(self.decompressed_data)
            or end_offset > len(self.decompressed_data)
        ):
            return b""

        return self.decompressed_data[start_offset:end_offset]

    def decode_phrase_bytes(self, phrase_bytes: bytes) -> str:
        """
        Decode phrase bytes to string using appropriate encoding.

        Args:
            phrase_bytes: Raw phrase bytes

        Returns:
            Decoded phrase string
        """
        if not phrase_bytes:
            return ""

        # Get encoding from system file if available
        encoding = "cp1252"  # Default Windows Western European
        if self.system_file and hasattr(self.system_file, "encoding") and self.system_file.encoding:
            encoding = self.system_file.encoding

        # Try the determined encoding first
        try:
            return phrase_bytes.decode(encoding)
        except UnicodeDecodeError:
            pass

        # Fall back through common Windows encodings
        fallback_encodings = ["cp1252", "cp1251", "cp850", "iso-8859-1", "latin-1"]

        for fallback_encoding in fallback_encodings:
            if fallback_encoding != encoding:  # Don't retry the same encoding
                try:
                    return phrase_bytes.decode(fallback_encoding)
                except UnicodeDecodeError:
                    continue

        # Final fallback: decode with errors='replace' to avoid crashes
        return phrase_bytes.decode("cp1252", errors="replace")

    def get_statistics(self) -> dict:
        """
        Returns statistics about the phrase data.

        Returns:
            Dictionary with phrase statistics
        """
        if not self.phr_index_file or not self.phr_index_file.header:
            return {
                "total_phrases": len(self.phrases),
                "raw_data_size": len(self.raw_data),
                "decompressed_size": len(self.decompressed_data),
                "compression_ratio": 0.0,
                "has_phr_index": False,
            }

        header = self.phr_index_file.header
        compression_ratio = 0.0
        if header.phr_image_compressed_size > 0:
            compression_ratio = header.phr_image_size / header.phr_image_compressed_size

        return {
            "total_phrases": header.entries,
            "raw_data_size": len(self.raw_data),
            "decompressed_size": len(self.decompressed_data),
            "expected_decompressed_size": header.phr_image_size,
            "compressed_size": header.phr_image_compressed_size,
            "compression_ratio": compression_ratio,
            "is_compressed": header.phr_image_size != header.phr_image_compressed_size,
            "has_phr_index": True,
            "bits": header.bits,
        }
