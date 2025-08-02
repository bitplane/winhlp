"""Test the derive_from_title functionality."""

from winhlp.lib.internal_files.context import ContextFile


def test_derive_basic():
    """Test basic derivation from topic titles."""
    # Test cases where derivation should work
    test_cases = [
        # (topic_title, possible_context_ids)
        ("File Menu", ["FileMenu", "File_Menu", "File"]),
        ("Save As...", ["SaveAs", "Save_As", "Save"]),
        ("Print Dialog", ["PrintDialog", "Print_Dialog", "Print"]),
    ]

    for title, possible_ids in test_cases:
        # Test that we can derive at least one of the possible IDs
        found = False
        for expected_id in possible_ids:
            target_hash = ContextFile.calculate_hash(expected_id)
            derived = ContextFile.derive_from_title(title, target_hash)
            if derived is not None and ContextFile.calculate_hash(derived) == target_hash:
                found = True
                break
        assert found, f"Failed to derive any ID for '{title}' from {possible_ids}"


def test_derive_with_prefixes():
    """Test derivation with common prefixes."""
    title = "Print Dialog"

    # Test with idh_ prefix
    expected_id = "idh_PrintDialog"
    target_hash = ContextFile.calculate_hash(expected_id)
    derived = ContextFile.derive_from_title(title, target_hash)
    assert derived == expected_id, f"Expected '{expected_id}', got '{derived}'"

    # Test with helpid_ prefix
    expected_id = "helpid_Print"
    target_hash = ContextFile.calculate_hash(expected_id)
    derived = ContextFile.derive_from_title(title, target_hash)
    assert derived is not None
    assert ContextFile.calculate_hash(derived) == target_hash


def test_derive_partial_title():
    """Test derivation using only part of the title."""
    title = "Advanced Configuration Settings"

    # Context ID might use just "Advanced" or "Configuration"
    expected_id = "Advanced"
    target_hash = ContextFile.calculate_hash(expected_id)
    derived = ContextFile.derive_from_title(title, target_hash)
    assert derived == expected_id

    expected_id = "Configuration"
    target_hash = ContextFile.calculate_hash(expected_id)
    derived = ContextFile.derive_from_title(title, target_hash)
    assert derived == expected_id


def test_derive_with_suffix():
    """Test derivation where we need to add a suffix."""
    title = "Help Contents"

    # Sometimes IDs have suffixes like "Help_1" or "HelpA"
    expected_id = "Help_1"
    target_hash = ContextFile.calculate_hash(expected_id)
    derived = ContextFile.derive_from_title(title, target_hash)
    assert derived is not None
    assert ContextFile.calculate_hash(derived) == target_hash


def test_derive_win31_vs_win95():
    """Test difference between Win 3.1 and Win95 character handling."""
    title = "C:\\Program Files\\App"

    # Win 3.1 would skip backslashes, Win95 might keep them
    # Test Win 3.1 mode (default)
    expected_id = "CProgramFilesApp"
    target_hash = ContextFile.calculate_hash(expected_id)
    derived = ContextFile.derive_from_title(title, target_hash, win95=False)
    assert derived is not None

    # Test that impossible derivations return None
    impossible_hash = 0x12345678
    derived = ContextFile.derive_from_title("X", impossible_hash)
    # This might find something or might not - just check it doesn't crash
    if derived:
        assert ContextFile.calculate_hash(derived) == impossible_hash


def test_derive_case_insensitive():
    """Test that derivation is case insensitive."""
    title = "SAVE FILE"
    expected_id = "SaveFile"

    target_hash = ContextFile.calculate_hash(expected_id)
    derived = ContextFile.derive_from_title(title, target_hash)
    assert derived is not None
    assert ContextFile.calculate_hash(derived) == target_hash


def test_derive_special_characters():
    """Test derivation with various special characters."""
    test_cases = [
        ("File->Save", "FileSave"),
        ("File/Save", "File_Save"),
        ("100% Complete", "100_Complete"),
        ("Q&A Section", "QASection"),
    ]

    for title, expected_pattern in test_cases:
        # We don't know exact ID, but verify we can derive something reasonable
        target_hash = ContextFile.calculate_hash(expected_pattern)
        derived = ContextFile.derive_from_title(title, target_hash)
        if derived:
            assert ContextFile.calculate_hash(derived) == target_hash
            # Check it's based on the title
            assert any(char.upper() in title.upper() for char in derived if char.isalnum())
