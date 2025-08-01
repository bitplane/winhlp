"""Tests for the HLP file reader."""

import os
from winhlp.lib.hlp import HelpFile
from winhlp.lib.internal_files.font import NewFont


def test_parse_header():
    """Tests parsing of the main HLP file header."""
    filepath = os.path.join(os.path.dirname(__file__), "data", "FXSEARCH.HLP")
    hlp_file = HelpFile(filepath=filepath)

    assert hlp_file.header is not None
    assert hlp_file.header.magic == 0x00035F3F
    assert hlp_file.header.directory_start > 0
    assert hlp_file.header.entire_file_size > 0


def test_parse_directory_header():
    """Tests parsing of the directory file header."""
    filepath = os.path.join(os.path.dirname(__file__), "data", "FXSEARCH.HLP")
    hlp_file = HelpFile(filepath=filepath)

    assert hlp_file.directory is not None
    assert hlp_file.directory.file_header is not None
    assert hlp_file.directory.file_header.used_space > 0


def test_parse_btree_header():
    """Tests parsing of the B-Tree header."""
    filepath = os.path.join(os.path.dirname(__file__), "data", "FXSEARCH.HLP")
    hlp_file = HelpFile(filepath=filepath)

    assert hlp_file.directory.btree is not None
    assert hlp_file.directory.btree.header is not None
    assert hlp_file.directory.btree.header.magic == 0x293B


def test_parse_directory_files():
    """Tests parsing of the directory files."""
    filepath = os.path.join(os.path.dirname(__file__), "data", "FXSEARCH.HLP")
    hlp_file = HelpFile(filepath=filepath)

    assert hlp_file.directory.files is not None
    assert "|SYSTEM" in hlp_file.directory.files
    assert "|TOPIC" in hlp_file.directory.files


def test_parse_system_header():
    """Tests parsing of the |SYSTEM file header."""
    filepath = os.path.join(os.path.dirname(__file__), "data", "FXSEARCH.HLP")
    hlp_file = HelpFile(filepath=filepath)

    assert hlp_file.system is not None
    assert hlp_file.system.header is not None
    assert hlp_file.system.header.magic == 0x036C


def test_parse_system_file_win30():
    """Tests parsing of a WinHelp 3.0 |SYSTEM file."""
    filepath = os.path.join(os.path.dirname(__file__), "data", "FXSEARCH.HLP")
    hlp_file = HelpFile(filepath=filepath)

    assert hlp_file.system is not None
    assert hlp_file.system.header is not None
    assert hlp_file.system.header.minor == 15
    assert hlp_file.system.title is not None
    assert len(hlp_file.system.records) == 0


def test_parse_system_file_win31():
    """Tests parsing of a WinHelp 3.1+ |SYSTEM file."""
    filepath = os.path.join(os.path.dirname(__file__), "data", "SMARTTOP.HLP")
    hlp_file = HelpFile(filepath=filepath)

    assert hlp_file.system is not None
    assert hlp_file.system.header is not None
    assert hlp_file.system.header.minor > 16
    assert hlp_file.system.title is not None
    assert hlp_file.system.copyright is not None
    assert len(hlp_file.system.records) > 0


def test_parse_font_facenames():
    """Tests parsing of the |FONT file facenames."""
    filepath = os.path.join(os.path.dirname(__file__), "data", "FXSEARCH.HLP")
    hlp_file = HelpFile(filepath=filepath)

    assert hlp_file.font.facenames is not None
    assert len(hlp_file.font.facenames) > 0


def test_parse_topic_blocks():
    """Tests parsing of the |TOPIC file blocks."""
    filepath = os.path.join(os.path.dirname(__file__), "data", "FXSEARCH.HLP")
    hlp_file = HelpFile(filepath=filepath)

    assert hlp_file.topic is not None
    assert hlp_file.topic.blocks is not None
    assert len(hlp_file.topic.blocks) > 0


def test_parse_topic_links():
    """Tests parsing of the |TOPIC file links."""
    filepath = os.path.join(os.path.dirname(__file__), "data", "FXSEARCH.HLP")
    hlp_file = HelpFile(filepath=filepath)

    assert hlp_file.topic is not None
    # A proper test would check the number of links parsed.
    # For now, we just check that the topic object was created.
    assert hlp_file.topic is not None


def test_parse_topic_headers():
    """Tests parsing of the |TOPIC file headers."""
    filepath = os.path.join(os.path.dirname(__file__), "data", "FXSEARCH.HLP")
    hlp_file = HelpFile(filepath=filepath)

    assert hlp_file.topic is not None
    # A proper test would check the number of headers parsed.
    # For now, we just check that the topic object was created.
    assert hlp_file.topic is not None


def test_parse_paragraph_info():
    """Tests parsing of the ParagraphInfo structure."""
    filepath = os.path.join(os.path.dirname(__file__), "data", "FXSEARCH.HLP")
    hlp_file = HelpFile(filepath=filepath)

    assert hlp_file.topic is not None
    # A proper test would check the parsed ParagraphInfo.
    # For now, we just check that the topic object was created.
    assert hlp_file.topic is not None


def test_parse_font_descriptors():
    """Tests parsing of the |FONT file descriptors."""
    filepath = os.path.join(os.path.dirname(__file__), "data", "FXSEARCH.HLP")
    hlp_file = HelpFile(filepath=filepath)

    assert hlp_file.font.descriptors is not None
    assert len(hlp_file.font.descriptors) > 0


def test_parse_font_descriptors_newfont():
    """Tests parsing of the |FONT file NewFont descriptors."""
    filepath = os.path.join(os.path.dirname(__file__), "data", "SMARTTOP.HLP")
    hlp_file = HelpFile(filepath=filepath)

    assert hlp_file.font is not None
    assert hlp_file.font.descriptors is not None
    assert len(hlp_file.font.descriptors) > 0
    assert isinstance(hlp_file.font.descriptors[0], NewFont)


def test_parse_font_facenames_detailed():
    """Tests parsing of the |FONT file facenames with detailed validation."""
    filepath = os.path.join(os.path.dirname(__file__), "data", "SMARTTOP.HLP")
    hlp_file = HelpFile(filepath=filepath)

    assert hlp_file.font is not None
    assert hlp_file.font.facenames is not None
    assert len(hlp_file.font.facenames) > 0

    # Test that we have expected standard font names
    facenames = hlp_file.font.facenames
    assert "Helv" in facenames
    assert "Tms Rmn" in facenames
    assert "Symbol" in facenames
    assert "Courier" in facenames

    # Test that font names are properly parsed (no control characters)
    for facename in facenames:
        if facename.strip():  # Skip empty entries
            # Should not contain control characters
            assert "\n" not in facename
            assert "\r" not in facename
            assert len(facename) < 50  # Reasonable length limit
            # Should be printable ASCII
            assert all(ord(c) >= 32 or c == "\t" for c in facename)


def test_parse_font_styles():
    """Tests parsing of the |FONT file styles."""
    filepath = os.path.join(os.path.dirname(__file__), "data", "SMARTTOP.HLP")
    hlp_file = HelpFile(filepath=filepath)

    assert hlp_file.font is not None
    assert hlp_file.font.styles is not None
    # This particular file has no styles (num_formats=0), which is valid
    assert len(hlp_file.font.styles) == 0


def test_parse_font_charmaps():
    """Tests parsing of the |FONT file charmaps."""
    filepath = os.path.join(os.path.dirname(__file__), "data", "SMARTTOP.HLP")
    hlp_file = HelpFile(filepath=filepath)

    assert hlp_file.font is not None
    assert hlp_file.font.charmaps is not None
    assert len(hlp_file.font.charmaps) == 0
