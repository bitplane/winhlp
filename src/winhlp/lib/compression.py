"""Decompression algorithms for HLP files."""

import struct
from typing import List


def lz77_decompress(data: bytes) -> bytes:
    """
    Decompresses LZ77 compressed data from a HLP file.

    Optimized implementation based on helldec1.c from helpdeco.
    Uses circular buffer and efficient bit processing like the C version.
    """
    if not data:
        return b""

    # Circular buffer like C version (4KB)
    lz_buffer = bytearray(0x1000)
    output = bytearray()

    data_len = len(data)
    offset = 0
    pos = 0  # Position in circular buffer
    mask = 0
    bits = 0

    while offset < data_len:
        if mask == 0:
            # Need new control byte
            if offset >= data_len:
                break
            bits = data[offset]
            offset += 1
            mask = 1

        if bits & mask:
            # Compressed data: back-reference
            if offset + 1 >= data_len:
                break

            # Use struct.unpack_from for efficiency
            word = struct.unpack_from("<H", data, offset)[0]
            offset += 2

            # Extract fields
            length = ((word >> 12) & 0x0F) + 3
            back_pos = pos - (word & 0x0FFF) - 1

            # Copy from circular buffer - direct slice when possible
            if length <= 16:  # Small copies - use individual operations
                for _ in range(length):
                    char = lz_buffer[back_pos & 0x0FFF]
                    lz_buffer[pos & 0x0FFF] = char
                    output.append(char)
                    back_pos += 1
                    pos += 1
            else:  # Larger copies - batch them
                copy_chars = bytearray(length)
                for i in range(length):
                    char = lz_buffer[back_pos & 0x0FFF]
                    lz_buffer[pos & 0x0FFF] = char
                    copy_chars[i] = char
                    back_pos += 1
                    pos += 1
                output.extend(copy_chars)
        else:
            # Literal byte
            if offset >= data_len:
                break
            char = data[offset]
            offset += 1
            lz_buffer[pos & 0x0FFF] = char
            output.append(char)
            pos += 1

        mask <<= 1

    return bytes(output)


def phrase_decompress(data: bytes, phrases: List[str]) -> bytes:
    """
    Decompresses phrase-compressed data.

    From helpfile.md:
    Take the next character. If it's value is 0 or above 15 emit it. Else
    multiply it with 256, subtract 256 and add the value of the next character.
    Divide by 2 to get the phrase number. Emit the phrase from the |Phrase file
    and append a space if the division had a remainder (the number was odd).
    """
    if not data or not phrases:
        return data

    output = bytearray()
    offset = 0

    while offset < len(data):
        ch = data[offset]
        offset += 1

        if ch == 0 or ch >= 15:
            # Literal character
            output.append(ch)
        else:
            # Phrase reference
            if offset >= len(data):
                break

            next_ch = data[offset]
            offset += 1

            # Calculate phrase number
            phrase_code = ch * 256 - 256 + next_ch
            phrase_num = phrase_code // 2
            add_space = phrase_code % 2 == 1

            # Emit the phrase if it exists
            if 0 <= phrase_num < len(phrases):
                phrase = phrases[phrase_num]
                output.extend(phrase.encode("latin-1"))
                if add_space:
                    output.append(ord(" "))

    return bytes(output)


def hall_decompress(data: bytes, phrases: List[str]) -> bytes:
    """
    Decompresses Hall-compressed data (Windows 95 HCW 4.00).

    From helpfile.md:
    Take the next character (ch). If ch is even emit the phrase number ch/2.
    Else if the least two bits are 01 multiply by 64, add 64 and the value of
    the next character. Emit the Phrase using this number. If the least three
    bits are 011 copy the next ch/8+1 characters. If the least four bits are
    0111 emit ch/16+1 spaces. If the least four bits are 1111 emit ch/16+1 NUL's.
    """
    if not data:
        return data

    output = bytearray()
    offset = 0

    while offset < len(data):
        ch = data[offset]
        offset += 1

        if ch & 0x01 == 0:
            # Even: phrase number ch/2
            phrase_num = ch // 2
            if 0 <= phrase_num < len(phrases):
                phrase = phrases[phrase_num]
                output.extend(phrase.encode("latin-1"))
        elif ch & 0x03 == 0x01:
            # Least two bits are 01
            if offset >= len(data):
                break
            next_ch = data[offset]
            offset += 1
            phrase_num = 128 + (ch // 4) * 256 + next_ch
            if 0 <= phrase_num < len(phrases):
                phrase = phrases[phrase_num]
                output.extend(phrase.encode("latin-1"))
        elif ch & 0x07 == 0x03:
            # Least three bits are 011: copy literal characters
            count = ch // 8 + 1
            for _ in range(count):
                if offset >= len(data):
                    break
                output.append(data[offset])
                offset += 1
        elif ch & 0x0F == 0x07:
            # Least four bits are 0111: emit spaces
            count = ch // 16 + 1
            output.extend(b" " * count)
        elif ch & 0x0F == 0x0F:
            # Least four bits are 1111: emit NULs
            count = ch // 16 + 1
            output.extend(b"\x00" * count)

    return bytes(output)


def runlen_decompress(data: bytes) -> bytes:
    """
    Decompresses run-length compressed data.

    Based on helpdeco's DeRun function. The algorithm works with a global
    count variable that tracks run-length state:
    - If count & 0x7F is non-zero, we're in a run
    - If count & 0x80 is set, emit characters one by one
    - Otherwise emit the full run at once
    - When count reaches 0, read next signed byte as new count
    """
    if not data:
        return b""

    output = bytearray()
    offset = 0
    count = 0  # Global state variable

    while offset < len(data):
        char = data[offset]
        offset += 1

        if count & 0x7F:
            # We're in a run
            if count & 0x80:
                # Emit one character and decrement
                output.append(char)
                count -= 1
            else:
                # Emit full run
                for _ in range(count & 0x7F):
                    output.append(char)
                count = 0
        else:
            # Start new run - char is the signed count
            count = char if char < 128 else char - 256  # Convert to signed byte
            if count < 0:
                count = 256 + count  # Convert back to unsigned for bit operations

    return bytes(output)


def decompress(method: int, data: bytes, phrases: List[str] = None) -> bytes:
    """
    Decompresses data using the specified method, matching helpdeco's approach.

    Method values:
    - 0: copy (no decompression)
    - 1: runlen decompression
    - 2: LZ77 decompression
    - 3: runlen and LZ77 decompression
    """
    if method == 0:
        # No compression - copy as-is
        return data
    elif method == 1:
        # Runlen only
        return runlen_decompress(data)
    elif method == 2:
        # LZ77 only
        return lz77_decompress(data)
    elif method == 3:
        # Combined runlen + LZ77
        # First apply runlen, then LZ77
        temp = runlen_decompress(data)
        return lz77_decompress(temp)
    else:
        raise ValueError("Unknown compression type")
        # Unknown method, return as-is
        # return data
