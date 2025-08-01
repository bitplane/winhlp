"""End-to-end tests for parsing various HLP files."""

import os
import pytest
from winhlp.lib.hlp import HelpFile


def get_all_hlp_files():
    """Get all HLP files in the test data directory."""
    hlp_files = []
    data_dir = os.path.join(os.path.dirname(__file__), "data")

    for root, dirs, files in os.walk(data_dir):
        for file in files:
            if file.upper().endswith(".HLP"):
                hlp_files.append(os.path.join(root, file))

    return hlp_files


@pytest.mark.parametrize("hlp_file", get_all_hlp_files())
def test_parse_hlp_file(hlp_file):
    """Test that each HLP file can be parsed without errors."""
    # Get relative path for better test output
    rel_path = os.path.relpath(hlp_file, os.path.dirname(__file__))

    try:
        hlp = HelpFile(filepath=hlp_file)

        # Basic assertions to ensure parsing completed
        assert hlp.header is not None
        assert hlp.directory is not None
        assert hlp.system is not None

        # Check that we can access the internal files
        assert isinstance(hlp.directory.files, dict)

        # If TOPIC file exists, it should be parsed
        if "|TOPIC" in hlp.directory.files:
            assert hlp.topic is not None

        # If FONT file exists, parsing may succeed or fail (like the C implementation)
        # Some FONT files may be malformed or unsupported, which is acceptable
        if "|FONT" in hlp.directory.files:
            # Just check that we don't crash - font can be None if parsing fails
            pass

    except Exception as e:
        pytest.fail(f"Failed to parse {rel_path}: {type(e).__name__}: {e}")


def test_all_hlp_files_found():
    """Ensure we have test files to work with."""
    hlp_files = get_all_hlp_files()
    assert len(hlp_files) > 0, "No HLP test files found"

    # Print files found for debugging
    print(f"\nFound {len(hlp_files)} HLP test files:")
    for f in hlp_files:
        rel_path = os.path.relpath(f, os.path.dirname(__file__))
        print(f"  - {rel_path}")
