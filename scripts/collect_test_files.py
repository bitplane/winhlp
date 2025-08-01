#!/usr/bin/env python3
"""
Collect test files that cause parsing errors.

This script scans a directory for HLP files, attempts to parse them,
and copies failing files to ./tests/data/errors/ organized by error type.
"""

import os
import sys
import shutil
from pathlib import Path
from collections import defaultdict
import json
import struct

# Add src to path so we can import winhlp
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

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


def get_error_signature(exc_info):
    """Extract a unique signature from an exception."""
    exc_type, exc_value, exc_traceback = exc_info

    # Get the deepest traceback frame that's in our code
    tb = exc_traceback
    while tb.tb_next is not None:
        tb = tb.tb_next

    # Extract source file, line number, and error message
    filename = os.path.basename(tb.tb_frame.f_code.co_filename)
    line_number = tb.tb_lineno
    error_message = str(exc_value).split("\n")[0]  # First line only

    return f"{filename}:{line_number}:{type(exc_value).__name__}:{error_message}"


def has_hlp_magic_number(file_path):
    """Check if file has the correct HLP magic number (0x00035F3F)."""
    try:
        with open(file_path, "rb") as f:
            data = f.read(4)
            if len(data) < 4:
                return False
            magic = struct.unpack("<L", data)[0]
            return magic == 0x00035F3F
    except (IOError, struct.error):
        return False


def collect_hlp_files(search_path):
    """Find all HLP files recursively in the given path that have valid HLP magic numbers."""
    hlp_files = []
    skipped_files = []

    for root, dirs, files in os.walk(search_path):
        for file in files:
            if file.upper().endswith(".HLP"):
                file_path = os.path.join(root, file)
                if has_hlp_magic_number(file_path):
                    hlp_files.append(file_path)
                else:
                    skipped_files.append(file_path)

    if skipped_files:
        print(f"Skipped {len(skipped_files)} files with invalid HLP magic numbers:")
        for f in skipped_files[:5]:  # Show first 5
            print(f"  - {os.path.basename(f)}")
        if len(skipped_files) > 5:
            print(f"  ... and {len(skipped_files) - 5} more")

    return hlp_files


def main():
    if len(sys.argv) != 2:
        print("Usage: ./scripts/collect_test_files.py <path_to_search>")
        sys.exit(1)

    search_path = sys.argv[1]
    if not os.path.exists(search_path):
        print(f"Error: Path '{search_path}' does not exist")
        sys.exit(1)

    # Set up error directory with atomic operation
    script_dir = Path(__file__).parent
    project_root = script_dir.parent
    error_dir = project_root / "tests" / "data" / "errors"
    error_dir_new = project_root / "tests" / "data" / "errors.new"

    # Create new directory (clean slate)
    if error_dir_new.exists():
        shutil.rmtree(error_dir_new)
    error_dir_new.mkdir(parents=True, exist_ok=True)

    print(f"Searching for HLP files in: {search_path}")
    hlp_files = collect_hlp_files(search_path)
    print(f"Found {len(hlp_files)} HLP files")

    # Track errors by signature
    error_files = defaultdict(list)
    successful_files = []

    for i, file_path in enumerate(hlp_files):
        basename = os.path.basename(file_path)
        print(f"[{i+1:3d}/{len(hlp_files):3d}] Processing {basename}...", end=" ")

        try:
            # Try to parse the file
            hlp = HelpFile(file_path)

            # Try to serialize to JSON
            data = json_serializable(hlp.model_dump())
            json.dumps(data)

            print("✓")
            successful_files.append(file_path)

        except Exception:
            print("✗")

            # Get error signature
            signature = get_error_signature(sys.exc_info())
            error_files[signature].append(file_path)

    print("\nResults:")
    print(f"  Successful: {len(successful_files)}")
    print(f"  Failed: {len(hlp_files) - len(successful_files)}")
    print(f"  Unique error types: {len(error_files)}")

    # Copy one example file for each unique error type
    for signature, files in error_files.items():
        # Use the first file as the representative
        src_file = files[0]
        basename = os.path.basename(src_file)

        # Create a safe filename from the signature
        safe_signature = signature.replace(":", "_").replace("/", "_").replace(" ", "_")
        safe_signature = "".join(c for c in safe_signature if c.isalnum() or c in "_-.")

        # Copy the file
        dst_file = error_dir / f"{safe_signature}_{basename}"
        shutil.copy2(src_file, dst_file)

        print(f"\nError: {signature}")
        print(f"  Example file: {basename}")
        print(f"  Total files with this error: {len(files)}")
        print(f"  Will copy to: {basename}")

    print(f"\nError files copied to: {error_dir.relative_to(project_root)}")


if __name__ == "__main__":
    main()
