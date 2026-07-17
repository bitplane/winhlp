"""Golden-content tests: guard that topic extraction actually yields content.

These complement the structural tests in test_hlp.py and the "doesn't crash"
checks in test_e2e.py. The bug they lock down: LZ77-compressed topic blocks
(WinHelp 3.1 / Win95) previously decompressed to garbage, so `parsed_topics`
came back empty and no text was extracted even though parsing "succeeded".
"""

import os
import re
import pytest
from winhlp.lib.hlp import HelpFile

DATA = os.path.join(os.path.dirname(__file__), "data")


def _topics_text(path):
    hlp = HelpFile(filepath=os.path.join(DATA, path))
    topics = hlp.topic.get_all_topics() if hlp.topic else []
    return topics, "".join(t.get_plain_text() for t in topics)


def _normalized_text(path):
    _, text = _topics_text(path)
    return re.sub(r"\s+", " ", text).strip()


# WinHelp 3.0 files (SYSTEM minor 15) never used LZ77 and have always worked.
# They pin exact topic counts and a known text snippet.
@pytest.mark.parametrize(
    "path, n_topics, snippet",
    [
        ("FXSEARCH.HLP", 19, "F/X Text Search Help Index"),
        ("FXUNDEL.HLP", 3, "F/X File Undelete Help Index"),
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
        ("SMARTTOP.HLP", 4, "Welcome to SmartTop"),  # 3.1, |Phrases compression
        ("win311/SOL.HLP", 5, "Solitaire is a card game that combines skill and luck"),
        ("win95/MSNINT.HLP", 10, "To view a list of topics, click Help Topics"),  # 95, Hall
        ("win95/WINDOWS.HLP", 24, "software available on the network for installation"),
    ],
)
def test_lz77_topic_content(path, n_topics, snippet):
    topics = _topics_text(path)[0]
    assert len(topics) == n_topics
    assert snippet in _normalized_text(path)


# Character formatting is resolved from the |FONT descriptor referenced by each
# span's font_number (bold/italic/underline/size/facename), not the command
# stream. Guard that spans in 3.1/95 files carry resolved attributes.
@pytest.mark.parametrize("path", ["SMARTTOP.HLP", "win311/SOL.HLP", "win95/WINDOWS.HLP"])
def test_font_attributes_resolved(path):
    topics = _topics_text(path)[0]
    spans = [s for t in topics for s in t.text_spans]
    assert any(s.is_bold for s in spans), "expected at least one bold span"
    # Every span with a font should resolve a real facename and a sane size.
    faced = [s for s in spans if s.facename]
    assert faced, "expected resolved facenames"
    assert all(8 <= s.font_half_points <= 200 for s in faced if s.font_half_points)


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
