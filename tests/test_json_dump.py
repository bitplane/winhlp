"""Test JSON serialization of HLP files."""

import os
import json
import pytest
from winhlp.lib.hlp import HelpFile


def json_serializable(obj):
    """Convert object to JSON-serializable format by handling bytes."""
    if isinstance(obj, bytes):
        return f"<bytes: {len(obj)} bytes>"
    elif isinstance(obj, dict):
        return {k: json_serializable(v) for k, v in obj.items()}
    elif isinstance(obj, list):
        return [json_serializable(item) for item in obj]
    else:
        return obj


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
def test_json_dump(hlp_file):
    """Test that each HLP file can be dumped to JSON."""
    # Get relative path for better test output
    rel_path = os.path.relpath(hlp_file, os.path.dirname(__file__))

    try:
        hlp = HelpFile(filepath=hlp_file)

        # Try to convert to JSON (handle bytes fields)
        data = json_serializable(hlp.model_dump())
        json_str = json.dumps(data, indent=2)

        # Basic checks
        assert json_str is not None
        assert len(json_str) > 0

        # Ensure it's valid JSON by parsing it back
        parsed = json.loads(json_str)
        assert isinstance(parsed, dict)
        assert "filepath" in parsed
        assert "header" in parsed

    except Exception as e:
        pytest.fail(f"Failed to dump {rel_path} to JSON: {type(e).__name__}: {e}")
