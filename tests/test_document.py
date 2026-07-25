"""Tests for the presentation-neutral document and navigation layer."""

import os

from winhlp.lib.document import HelpNavigator
from winhlp.lib.hlp import HelpFile

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
    assert popup.topic.title == "How to get support"


def test_topic_content_blocks_preserve_table_position_and_legacy_lists():
    hlp = HelpFile(filepath=os.path.join(DATA, "coverage", "ELSA_DE.HLP"))
    topic = next(topic for topic in hlp.get_topics() if topic.tables)
    kinds = [block.kind for block in topic.content_blocks]

    assert "table" in kinds
    assert kinds.index("table") < max(i for i, kind in enumerate(kinds) if kind == "text")
    assert sum(kind == "table" for kind in kinds) == len(topic.tables)
    assert [
        span for block in topic.content_blocks if block.kind == "text" for span in block.text_spans
    ] == topic.text_spans
