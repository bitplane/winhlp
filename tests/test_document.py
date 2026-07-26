"""Tests for the presentation-neutral document and navigation layer."""

import os
from pathlib import Path
from types import SimpleNamespace

from winhlp.lib.cnt import load_cnt
from winhlp.lib.document import HelpDocument, HelpNavigator
from winhlp.lib.hlp import HelpFile
from winhlp.lib.internal_files.topic import ParsedTopic, TextSpan, TopicTextBlock
from winhlp.lib.layout import layout_topic

DATA = os.path.join(os.path.dirname(__file__), "data")


def test_smarttop_context_hash_link_resolves_to_intended_topic():
    hlp = HelpFile(filepath=os.path.join(DATA, "SMARTTOP.HLP"))
    document = hlp.get_document()

    target = document.resolve_target("topic:00000427")

    assert target.kind == "topic"
    assert target.topic is not None
    assert target.topic.title == "How to use SmartTop"
    assert hlp.get_document() is document


def test_full_text_search_is_case_insensitive_and_uses_all_terms():
    document = HelpFile(filepath=os.path.join(DATA, "SMARTTOP.HLP")).get_document()

    results = document.search("VERY easy USE")

    assert [topic.title for topic in results] == ["How to use SmartTop"]
    assert document.search("") == list(document.topics)


def test_navigation_history_and_popup_resolution():
    document = HelpFile(filepath=os.path.join(DATA, "SMARTTOP.HLP")).get_document()
    navigator = HelpNavigator(document)
    first = navigator.current
    second = document.resolve_target("topic:00000427").topic

    navigator.go_to(second)
    assert navigator.current is second
    assert navigator.back() is first
    assert navigator.forward() is second

    popup = document.resolve_target("popup:193ADDD8")
    assert popup.kind == "popup"
    assert popup.topic is not None
    assert "Shareware is copyrighted software" in popup.topic.get_plain_text()


def test_topic_content_blocks_preserve_table_position_and_legacy_lists():
    hlp = HelpFile(filepath=os.path.join(DATA, "win95", "MSNINT.HLP"))
    topic = next(topic for topic in hlp.get_topics() if topic.tables)
    kinds = [block.kind for block in topic.content_blocks]

    assert "table" in kinds
    assert kinds.index("table") < max(i for i, kind in enumerate(kinds) if kind == "text")
    assert sum(kind == "table" for kind in kinds) == len(topic.tables)
    assert [
        span for block in topic.content_blocks if block.kind == "text" for span in block.text_spans
    ] == topic.text_spans


def test_system_contents_offset_selects_initial_topic():
    helpfile = HelpFile(filepath=os.path.join(DATA, "SMARTTOP.HLP"))
    intended = helpfile.get_topics()[2]
    helpfile.system.records = [
        record
        for record in helpfile.system.records
        if not (isinstance(record, dict) and record.get("type") == "CONTENTS")
    ]
    helpfile.system.records.append({"type": "CONTENTS", "contents_offset": intended.topic_offset})

    assert HelpDocument(helpfile).initial_topic is intended


def test_cnt_parser_preserves_books_levels_targets_and_diagnostics(tmp_path: Path):
    path = tmp_path / "sample.cnt"
    path.write_text(
        ":Title Example Help\n:Base SAMPLE.HLP\n1 Introduction=CTX_INTRO\n"
        "1 Tasks\n2 First task=CTX_TASK\n:Include unsafe.cnt\n",
        encoding="cp1252",
    )

    contents = load_cnt(path)

    assert contents.title == "Example Help"
    assert contents.base_file == "SAMPLE.HLP"
    assert [(entry.label, entry.level, entry.kind) for entry in contents.entries] == [
        ("Introduction", 0, "topic"),
        ("Tasks", 0, "book"),
        ("First task", 1, "topic"),
    ]
    assert "not followed" in contents.diagnostics[0]


def test_real_index_preserves_keyword_type_hierarchy_and_multiple_targets():
    document = HelpFile(filepath=os.path.join(DATA, "win95", "WINDOWS.HLP")).get_document()
    entries = document.index_entries()

    assert entries
    assert all(entry.keyword_type for entry in entries)
    assert any(entry.level == 1 for entry in entries)
    assert any(len(entry.topics) > 1 for entry in entries)
    assert all(entry.label for entry in entries)


def test_allowlisted_navigation_macros_resolve_but_arbitrary_macros_do_not():
    document = HelpFile(filepath=os.path.join(DATA, "SMARTTOP.HLP")).get_document()
    context = document.topics[1].context_names[0]

    safe = document.resolve_target(f'macro:JumpID("", "{context}")')
    unsafe = document.resolve_target('macro:ExecFile("calc.exe")')

    assert safe.kind == "topic"
    assert safe.topic is document.topics[1]
    assert unsafe.kind == "macro"
    assert "not supported" in unsafe.detail


def test_layout_uses_record_offsets_for_fixed_boundary():
    fixed = TopicTextBlock(text_spans=[TextSpan(text="fixed", raw_data={})], source_offset=100, source_end_offset=110)
    scrolling = TopicTextBlock(
        text_spans=[TextSpan(text="scrolling", raw_data={})], source_offset=110, source_end_offset=120
    )
    topic = ParsedTopic(
        topic_offset=100,
        non_scroll_offset=110,
        content_blocks=[fixed, scrolling],
        text_spans=[*fixed.text_spans, *scrolling.text_spans],
        raw_data={},
    )

    layout = layout_topic(topic)

    assert layout.fixed_blocks == (fixed,)
    assert layout.scrolling_blocks == (scrolling,)


def test_gid_contents_preserves_hierarchy_and_unresolved_books():
    topic = ParsedTopic(topic_number=1, title="Child", context_names=["CTX_CHILD"], topic_offset=100, raw_data={})
    fake = SimpleNamespace(
        filepath="sample.gid",
        system=None,
        get_topics=lambda: [topic],
        cnttext=SimpleNamespace(topic_titles=["Book", "  Child"]),
        cntjump=SimpleNamespace(jump_references=["", "CTX_CHILD"]),
        keyword_search_files={},
        keyword_index_files={},
    )

    entries = HelpDocument(fake).contents_entries()

    assert [(entry.label, entry.level, entry.kind) for entry in entries] == [
        ("Book", 0, "unresolved"),
        ("Child", 1, "topic"),
    ]
    assert entries[1].topic is topic
