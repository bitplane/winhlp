# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

winhlp is a Python library for parsing Windows HLP (Help) files. It's based on the helpdeco utility by Manfred Winterhoff and implements a pure Python parser for the binary HLP file format used by Windows Help systems from Windows 3.0 through Windows 95.

## Development Commands

- `make test` - Run all tests using pytest
- `make dev` - Set up development environment with pre-commit hooks
- `make coverage` - Generate HTML coverage report in htmlcov/
- `make clean` - Clean up caches and virtual environment
- `pytest tests/test_hlp.py::test_function_name` - Run a single test function
- `pytest tests/test_hlp.py -k "keyword"` - Run tests matching keyword

## Architecture Overview

### Main Components

The library follows a hierarchical parsing approach:

1. **HelpFile** (`src/winhlp/lib/hlp.py`) - Main entry point that loads entire HLP file into memory and orchestrates parsing of all components
2. **Directory** (`src/winhlp/lib/directory.py`) - Parses the internal file directory using B+ tree structures to map internal filenames to file offsets
3. **BTree** (`src/winhlp/lib/btree.py`) - Generic B+ tree implementation for navigating the directory and other indexed structures
4. **Internal File Parsers** (`src/winhlp/lib/internal_files/`) - Specialized parsers for each type of internal file

### Internal File Types

HLP files contain multiple internal files, each with specific purposes:

- **|SYSTEM** - Contains metadata: version, compression flags, title, copyright, window definitions
- **|FONT** - Font descriptors, face names, and style information for text rendering
- **|TOPIC** - The actual help content, organized in compressed blocks with rich text formatting
- **|CONTEXT** - Maps context names to topic offsets using hash values and B+ trees
- **|PHRASE** - Phrase compression tables for reducing file size (WinHelp 3.1+)

### Binary Format Parsing

The library uses Python's `struct` module extensively to parse binary data according to the documented HLP file format. Key patterns:

- All parsers inherit from `InternalFile` base class and use Pydantic for data validation
- Header structures are parsed first to determine data layout and sizes
- B+ tree navigation follows the reference C implementation from helpdeco
- Compressed data (LZ77) is decompressed before parsing content
- Different WinHelp versions (3.0 vs 3.1+) have different structures that are handled conditionally

### Data Flow

1. `HelpFile.__init__()` loads entire file into memory
2. Main header is parsed to locate directory offset
3. Directory B+ tree is parsed to build filename -> offset mapping
4. Each internal file is parsed based on its specific format
5. Cross-references between files are resolved (e.g., FONT data used by TOPIC parsing)

## Testing

Tests use real HLP files stored in `tests/data/`:
- `FXSEARCH.HLP` - Windows 3.0 format help file
- `SMARTTOP.HLP` - Windows 3.1+ format with advanced features
- `FXUNDEL.HLP` - Additional test cases

Tests follow pytest patterns and verify both structure parsing and data extraction from these reference files.

## Key Implementation Notes

- The library prioritizes correctness over performance, loading entire files into memory
- Pydantic models provide data validation and structured access to parsed data
- The implementation closely follows the original C reference code structure
- Binary format documentation in `doc/helpfile.md` is the authoritative reference
- Support for different compression methods and file format versions is handled throughout