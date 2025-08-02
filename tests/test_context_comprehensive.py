"""Comprehensive test of context ID functionality."""

from winhlp.lib.internal_files.context import ContextFile


def test_hash_reverse_derive_integration():
    """Test that hash, reverse_hash, and derive_from_title work together."""

    # Test a typical workflow:
    # 1. We have a topic title "File Operations"
    # 2. An authoring system might create various context IDs from it
    # 3. We should be able to derive the correct ID given the hash

    title = "File Operations"

    # Various IDs that might be generated from this title
    possible_ids = [
        "FileOperations",
        "File_Operations",
        "idh_FileOperations",
        "helpid_File",
        "File",
        "Operations",
        "FileOps",
    ]

    for context_id in possible_ids:
        # Calculate hash
        hash_value = ContextFile.calculate_hash(context_id)

        # Verify reverse_hash can reconstruct something that hashes correctly
        reversed_id = ContextFile.reverse_hash(hash_value)
        assert ContextFile.calculate_hash(reversed_id) == hash_value

        # Try to derive from title
        derived_id = ContextFile.derive_from_title(title, hash_value)
        if derived_id:
            # If we can derive it, it should hash correctly
            assert ContextFile.calculate_hash(derived_id) == hash_value
            # And ideally match or be similar to the original
            print(f"Original: '{context_id}', Derived: '{derived_id}', Reversed: '{reversed_id}'")


def test_special_hash_values():
    """Test handling of special hash values."""
    # These are special values mentioned in the C code
    special_hashes = {
        0xFFFFFFFF: "21KSYK4",  # -1
        0x00000000: "21KSYK5",  # 0
        0x00000001: "",  # 1 = empty string
    }

    for hash_value, expected in special_hashes.items():
        result = ContextFile.reverse_hash(hash_value)
        if hash_value == 1:
            # Empty string or any string that hashes to 1
            assert ContextFile.calculate_hash(result) == 1
        else:
            assert result == expected


def test_derive_handles_unicode():
    """Test that derive_from_title handles unicode gracefully."""
    # Unicode title that would be common in international help files
    title = "Файл Меню"  # "File Menu" in Russian

    # Try to derive a simple ASCII ID
    target_id = "FileMenu"
    target_hash = ContextFile.calculate_hash(target_id)

    # This might not find anything (unicode chars have no hash values)
    # but it shouldn't crash
    ContextFile.derive_from_title(title, target_hash)
    # Result depends on implementation details, just verify no crash


def test_derive_performance():
    """Test that derive_from_title completes in reasonable time."""
    import time

    # Long title with many special characters
    title = "Advanced Configuration Settings - System Parameters & Options (Version 2.0)"

    # Try to derive a simple ID
    target_id = "AdvancedConfig"
    target_hash = ContextFile.calculate_hash(target_id)

    start = time.time()
    derived = ContextFile.derive_from_title(title, target_hash)
    elapsed = time.time() - start

    # Should complete within 1 second even for complex titles
    assert elapsed < 1.0, f"Derivation took {elapsed:.2f} seconds"

    if derived:
        assert ContextFile.calculate_hash(derived) == target_hash


def test_real_world_patterns():
    """Test patterns commonly seen in real help files."""
    # Common patterns from Windows help files
    patterns = [
        # (title, common_id_pattern)
        ("Contents", "IDH_CONTENTS"),
        ("Index", "HID_INDEX"),
        ("Using Help", "HIDD_USING_HELP"),
        ("About Dialog Box", "IDD_ABOUTBOX"),
        ("File Open", "ID_FILE_OPEN"),
        ("Edit Menu", "IDM_EDIT"),
    ]

    success_count = 0
    for title, common_id in patterns:
        target_hash = ContextFile.calculate_hash(common_id)

        # Try basic derivation
        derived = ContextFile.derive_from_title(title, target_hash)
        if not derived:
            # Try with common prefixes
            for prefix in ["", "IDH_", "HID_", "HIDD_", "IDD_", "ID_", "IDM_"]:
                test_title = prefix + title
                derived = ContextFile.derive_from_title(test_title, target_hash)
                if derived:
                    break

        if derived:
            success_count += 1
            print(f"Successfully derived '{derived}' from '{title}' (target: '{common_id}')")

    # We should be able to derive at least some of these
    assert success_count > 0, "Could not derive any real-world patterns"
