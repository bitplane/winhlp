"""Text decoding utilities for Windows Help files.

This module provides centralized text decoding functionality with encoding
fallbacks to handle international character sets correctly across different
Windows Help file parsers.
"""

from typing import Optional


def decode_help_text(data: bytes, primary_encoding: Optional[str] = None) -> str:
    """
    Decode byte string to text using Windows Help file appropriate encodings.

    This function provides a centralized implementation of the text decoding
    logic that was previously duplicated across multiple parser classes
    (RoseFile, GMacrosFile, TopicIdFile, TTLBTreeFile, PhraseFile, etc.).

    Args:
        data: Byte data to decode
        primary_encoding: Optional primary encoding to try first (e.g., from |SYSTEM file)
                         If None, uses cp1252 as primary

    Returns:
        Decoded string; undecodable bytes become U+FFFD
    """
    if not data:
        return ""

    # Primary encoding (from system file or default)
    primary = primary_encoding or "cp1252"

    # Stay in the file's code page and replace only the undecodable bytes;
    # switching code pages garbles the rest of the string.
    try:
        return data.decode(primary, errors="replace")
    except LookupError:
        return data.decode("cp1252", errors="replace")


def decode_help_text_with_system(data: bytes, system_file=None) -> str:
    """
    Decode byte string using encoding information from |SYSTEM file.

    Convenience wrapper around decode_help_text that extracts encoding
    from the system file if available.

    Args:
        data: Byte data to decode
        system_file: SystemFile instance with encoding information

    Returns:
        Decoded string
    """
    primary_encoding = None
    if system_file and hasattr(system_file, "encoding") and system_file.encoding:
        primary_encoding = system_file.encoding

    return decode_help_text(data, primary_encoding)
