"""Golden-content tests: guard that topic extraction actually yields content.

These complement the structural tests in test_hlp.py and the "doesn't crash"
checks in test_e2e.py. The bug they lock down: LZ77-compressed topic blocks
(WinHelp 3.1 / Win95) previously decompressed to garbage, so `parsed_topics`
came back empty and no text was extracted even though parsing "succeeded".
"""

import os
import re
import struct

import pytest
from winhlp.lib.compression import hall_decompress
from winhlp.lib.hlp import HelpFile
from winhlp.lib.internal_files.phrindex import PhrIndexFile

DATA = os.path.join(os.path.dirname(__file__), "data")


def _topics_text(path):
    hlp = HelpFile(filepath=os.path.join(DATA, path))
    topics = hlp.topic.get_all_topics() if hlp.topic else []
    return topics, "".join(t.get_plain_text() for t in topics)


def _normalized_text(path):
    _, text = _topics_text(path)
    return re.sub(r"\s+", " ", text).strip()


# WinHelp 3.0 files (SYSTEM minor 15) never used LZ77. Topic counts match
# helpdeco; a per-block link walker used to find only 19 and 3 of them.
@pytest.mark.parametrize(
    "path, n_topics, snippet",
    [
        ("FXSEARCH.HLP", 84, "F/X Text Search Help Index"),
        ("FXUNDEL.HLP", 31, "F/X File Undelete Help Index"),
    ],
)
def test_win30_topic_content(path, n_topics, snippet):
    topics, text = _topics_text(path)
    assert len(topics) == n_topics
    assert snippet in text


# WinHelp 3.1 (minor 21) and Win95 (minor 33) files exercise LZ77 topic-block
# decompression plus phrase (|Phrases) or Hall (|PhrIndex/|PhrImage) text
# decompression. Before those fixes these produced zero (or garbled) topics.
# Assert exact topic counts and a real, readable text snippet.
@pytest.mark.parametrize(
    "path, n_topics, snippet",
    [
        ("SMARTTOP.HLP", 7, "Welcome to SmartTop"),  # 3.1, |Phrases compression
        ("win311/SOL.HLP", 7, "Solitaire is a card game that combines skill and luck"),
        ("win95/MSNINT.HLP", 102, "To view a list of topics, click Help Topics"),  # 95, Hall
        ("win95/WINDOWS.HLP", 1550, "software available on the network for installation"),
    ],
)
def test_lz77_topic_content(path, n_topics, snippet):
    topics = _topics_text(path)[0]
    assert len(topics) == n_topics
    assert snippet in _normalized_text(path)


def test_hall_bitcount_zero_preserves_dbcs_phrase_boundaries():
    """CP932 phrases may split multibyte characters and must remain bytes."""
    # Two one-byte phrases contain the two halves of CP932 "あ". With
    # BitCount=0, each unary phrase length is encoded by one clear bit.
    header = struct.pack("<llllllHH", 1, 2, 4, 2, 2, 0, 0, 0x4A00)
    phrindex = PhrIndexFile(filename="|PhrIndex", raw_data=header + b"\x00\x00\x00\x00")
    phrindex._parse_hall_phrase_offsets(b"\x82\xa0")

    assert phrindex.header.bits == 0
    assert phrindex.phrase_bytes == [b"\x82", b"\xa0"]
    assert hall_decompress(b"\x00\x02", phrindex.phrase_bytes).decode("cp932") == "あ"


def test_zero_width_macro_button_is_retained_as_embedded_object():
    hlp = HelpFile(filepath=os.path.join(DATA, "win95", "WINDOWS.HLP"))
    topic = hlp.get_topics()[164]

    objects = [
        span
        for span in topic.text_spans
        if span.raw_data.get("type") == "embedded_object" and span.embedded_image == "bitmap:inline:0"
    ]
    assert len(objects) == 1
    assert objects[0].text == ""
    assert objects[0].hyperlink_target == "macro:EF(`Desk.cpl',`Display,0')\x00"


# Character formatting is resolved from the |FONT descriptor referenced by each
# span's font_number (bold/italic/underline/size/facename), not the command
# stream. Guard that spans in 3.0/3.1/95 files carry resolved attributes.
@pytest.mark.parametrize("path", ["FXUNDEL.HLP", "SMARTTOP.HLP", "win311/SOL.HLP", "win95/WINDOWS.HLP"])
def test_font_attributes_resolved(path):
    topics = _topics_text(path)[0]
    spans = [s for t in topics for s in t.text_spans]
    assert any(s.is_bold for s in spans), "expected at least one bold span"
    # Every span with a font should resolve a real facename and a sane size.
    faced = [s for s in spans if s.facename]
    assert faced, "expected resolved facenames"
    assert all(8 <= s.font_half_points <= 200 for s in faced if s.font_half_points)


def test_win30_display_records_carry_formatting_and_links():
    # TL_DISPLAY30 records share TL_DISPLAY's command stream (minus TopicLength),
    # so 3.0 topics get fonts, paragraphs and hotspots like 3.1 ones.
    spans = _topics_text("FXUNDEL.HLP")[0][0].text_spans
    assert spans[0].text == "F/X File Undelete Help Index\n\n"
    assert spans[0].is_bold and spans[0].facename == "Helv"
    link = next(s for s in spans if s.text == "Menu and Command Keys")
    assert link.is_hyperlink and link.hyperlink_target.startswith("topic:")


def test_paragraph_infos_retained_per_paragraph():
    """Each display record contributes a ParagraphInfo, not just the first."""
    hlp = HelpFile(filepath=os.path.join(DATA, "win311/SOL.HLP"))
    multi = [t for t in hlp.topic.get_all_topics() if len(t.paragraph_infos) > 1]
    assert multi, "expected at least one topic with multiple paragraph infos"


# --- Phase 3: derived cross-references ---------------------------------------


@pytest.mark.parametrize(
    "path, expected_title",
    [
        ("win311/SOL.HLP", "Rules of the Game"),
        ("SMARTTOP.HLP", "How to use SmartTop"),
        ("win95/WINDOWS.HLP", "Removing a program from your computer"),
    ],
)
def test_topic_titles_extracted(path, expected_title):
    """Topic titles come from the first LinkData2 string of the topic header."""
    hlp = HelpFile(filepath=os.path.join(DATA, path))
    titles = {t.title for t in hlp.topic.get_all_topics() if t.title}
    assert expected_title in titles


def test_topic_offsets_align_with_context_map():
    """Tracked TOPICOFFSETs should match the |CONTEXT hash->offset table."""
    hlp = HelpFile(filepath=os.path.join(DATA, "win311/SOL.HLP"))
    ctx_offsets = set(hlp.context.context_map.values())
    topic_offsets = [t.topic_offset for t in hlp.topic.get_all_topics()]
    assert topic_offsets and all(o in ctx_offsets for o in topic_offsets)


def test_context_names_and_keywords_attached():
    """WINDOWS.HLP has a populated keyword index; topics get names and keywords."""
    hlp = HelpFile(filepath=os.path.join(DATA, "win95/WINDOWS.HLP"))
    topics = hlp.topic.get_all_topics()
    # Every located topic should resolve at least one context name.
    assert any(t.context_names for t in topics)
    # The |KWBTREE parses (regression: it used to be silently empty).
    assert len(hlp.keyword_search_files["K"]["btree"].keyword_map) > 100
    assert any(t.keywords for t in topics)


def test_keyword_cross_references_use_byte_offsets():
    hlp = HelpFile(filepath=os.path.join(DATA, "FXUNDEL.HLP"))
    index = hlp._keyword_offset_index()

    assert [offset for offset, keywords in index.items() if "K:Application window" in keywords] == [4623]


@pytest.mark.parametrize(
    "count, bits, bitstream, image, error",
    [
        (0x7FFFFFFF, 0, b"\0" * 4, b"x", "phrase count"),
        (-1, 0, b"\0" * 4, b"x", "phrase count"),
        (33, 0, b"\0" * 4, b"x" * 33, "phrase count"),
        (1, 0, b"\xff" * 4, b"x" * 100, "bitstream"),
        (1, 0, b"\x01\0\0\0", b"x", "extends past"),
    ],
)
def test_hall_rejects_counts_and_offsets_beyond_input(count, bits, bitstream, image, error, monkeypatch):
    original_get_bit = PhrIndexFile._get_bit
    reads = 0

    def bounded_get_bit(self):
        nonlocal reads
        reads += 1
        assert reads <= 1024, "Parser kept reading beyond the small test input"
        return original_get_bit(self)

    monkeypatch.setattr(PhrIndexFile, "_get_bit", bounded_get_bit)
    header = struct.pack("<llllllHH", 0x4A01, count, 28 + len(bitstream), len(image), len(image), 0, bits, 0x4A00)
    index = PhrIndexFile(filename="|PhrIndex", raw_data=header + bitstream)
    with pytest.raises(ValueError, match=error):
        index._parse_hall_phrase_offsets(image)
    assert index.phrase_bytes == []
    assert index.phrases == []


def test_corrupt_hall_index_is_reported_without_aborting_help_file(tmp_path):
    original = HelpFile(filepath=os.path.join(DATA, "win95", "MSNINT.HLP"))
    data = bytearray(original.data)
    struct.pack_into("<l", data, original.directory.files["|PhrIndex"] + 9 + 4, -1)
    path = tmp_path / "corrupt.hlp"
    path.write_bytes(data)

    damaged = HelpFile(filepath=str(path))

    assert damaged.phrindex is None
    assert any(error["file"] == "|PhrIndex" and "phrase count" in error["error"] for error in damaged.parse_errors)
    assert damaged.get_topic_count() == original.get_topic_count()


def test_btree_internal_files_are_loaded_without_file_header():
    # |TTLBTREE, |TopicId and |Rose used to receive the 9-byte FILEHEADER, so
    # their B-trees never parsed.
    hlp = HelpFile(filepath=os.path.join(DATA, "SMARTTOP.HLP"))
    assert hlp.ttlbtree.btree is not None
    assert len(hlp.ttlbtree.entries) == 8


def test_topicid_supplies_real_context_names():
    hlp = HelpFile(filepath=os.path.join(DATA, "topicid", "ICQPhPl.hlp"))
    assert list(hlp.topicid.context_topic_map) == ["ICQ_Version_2000b"]
    assert "ICQ_Version_2000b" in hlp.topic.get_all_topics()[0].context_names


def test_win30_topic_offsets_are_header_topicpos():
    # HC30 |CTXOMAP entries address topics by the TOPICPOS of their header.
    hlp = HelpFile(filepath=os.path.join(DATA, "FXSEARCH.HLP"))
    offsets = {t.topic_offset for t in hlp.topic.get_all_topics()}
    assert all(entry.topic_offset in offsets for entry in hlp.ctxomap.entries)
