"""Test the reverse hash implementation against known context IDs."""

from winhlp.lib.internal_files.context import ContextFile


def test_hash_function():
    """Test that the hash function matches expected values."""
    # Test cases from documentation
    assert ContextFile.calculate_hash("") == 1
    assert ContextFile.calculate_hash("A") == 0x11
    assert ContextFile.calculate_hash("B") == 0x12

    # Some known context IDs and their hashes (verified with C implementation)
    test_cases = [
        ("INDEX", 0x053D24A6),
        ("CONTENTS", 0x25F4558A),
        ("HELP", 0x001DBA49),
        ("A", 0x00000011),
        ("TEST", 0x002C4A5E),
    ]

    for context_id, expected_hash in test_cases:
        actual_hash = ContextFile.calculate_hash(context_id)
        assert (
            actual_hash == expected_hash
        ), f"Hash mismatch for '{context_id}': expected 0x{expected_hash:08X}, got 0x{actual_hash:08X}"


def test_reverse_hash_basic():
    """Test that reverse_hash produces IDs that hash to the original value."""
    # Test simple cases
    test_hashes = [
        0x00000001,  # Empty string
        0x00000011,  # "A"
        0x053D24A6,  # "INDEX"
        0x25F4558A,  # "CONTENTS"
        0x001DBA49,  # "HELP"
        0x002C4A5E,  # "TEST"
    ]

    for hash_value in test_hashes:
        reversed_id = ContextFile.reverse_hash(hash_value)
        # The reversed ID should hash back to the original value
        rehashed = ContextFile.calculate_hash(reversed_id)
        assert (
            rehashed == hash_value
        ), f"Reverse hash failed for 0x{hash_value:08X}: '{reversed_id}' hashes to 0x{rehashed:08X}"


def test_reverse_hash_edge_cases():
    """Test edge cases for reverse hash."""
    # Test hash value 1 (empty string)
    assert ContextFile.reverse_hash(1) == ""

    # Test that hash 0 produces a valid ID (not CTX_ fallback)
    # The C implementation produces "21KSYK5" for hash 0
    zero_hash = 0x00000000
    result = ContextFile.reverse_hash(zero_hash)
    # Verify it's a valid context ID that hashes back to 0
    assert ContextFile.calculate_hash(result) == zero_hash, f"'{result}' doesn't hash back to 0"


def test_reverse_hash_special_values():
    """Test special hash values that have known meanings."""
    # Test special values from the C code comments
    special_cases = [
        (0xFFFFFFFF, "21KSYK4"),  # -1 hash value
        (0x00000000, "21KSYK5"),  # 0 hash value
        (0x00000001, ""),  # Empty string
    ]

    for hash_value, expected_id in special_cases:
        result = ContextFile.reverse_hash(hash_value)
        # Special case: empty string returns "" but "21KSYK6" also hashes to 1
        if hash_value == 1:
            assert result == "" or ContextFile.calculate_hash(result) == 1
        else:
            assert result == expected_id, f"Expected '{expected_id}' for hash 0x{hash_value:08X}, got '{result}'"


def test_reverse_hash_produces_valid_chars():
    """Test that reverse_hash only produces valid context ID characters."""
    valid_chars = set("0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz_.")

    # Test a range of hash values
    for i in range(100, 200):
        hash_value = i * 0x1000
        reversed_id = ContextFile.reverse_hash(hash_value)

        # Skip CTX_ prefixed fallback IDs
        if reversed_id.startswith("CTX_"):
            continue

        # Check all characters are valid
        for char in reversed_id:
            assert (
                char in valid_chars
            ), f"Invalid character '{char}' in reversed ID '{reversed_id}' for hash 0x{hash_value:08X}"
