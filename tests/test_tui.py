"""Headless interaction tests for the terminal viewer."""

import os

import pytest
from rich.text import Text
from winhlp.lib.hlp import HelpFile
from winhlp.lib.internal_files.topic import ParsedTopic, TextSpan, TopicTextBlock
from winhlp.tui import DiagnosticPopup, InformationPopup, TopicPopup, TopicView, WinHlpApp, _span_style, _span_text

DATA = os.path.join(os.path.dirname(__file__), "data")


def test_terminal_font_approximations_preserve_semantics_without_source_colours():
    span = TextSpan(
        text="x2",
        is_double_underline=True,
        is_small_caps=True,
        is_superscript=True,
        font_half_points=30,
        fg_rgb=(255, 0, 0),
        raw_data={},
    )

    assert _span_text(span) == "X²"
    style = _span_style(span)
    assert style.underline2
    assert style.bold
    assert style.color is None


def test_subline_paragraph_spacing_does_not_become_a_full_terminal_row():
    document = HelpFile(filepath=os.path.join(DATA, "win95", "WINDOWS.HLP")).get_document()
    topic = document.topics[164]
    view = TopicView(document, topic)

    rendered = view._apply_paragraph_layout(Text("heading"), topic.content_blocks[0])

    assert isinstance(rendered, Text)
    assert not rendered.plain.startswith("\n")


@pytest.mark.asyncio
async def test_link_keyboard_navigation_and_history():
    app = WinHlpApp(HelpFile(filepath=os.path.join(DATA, "SMARTTOP.HLP")))

    async with app.run_test(size=(100, 30)) as pilot:
        view = app.query_one("#topic-view", TopicView)
        assert app.theme == "winhelp"
        assert view.topic.title == "Index"
        assert len(view.targets) == 5

        await pilot.press("tab", "enter")
        await pilot.pause()
        assert view.topic.title == "How to use SmartTop"

        await pilot.press("b")
        await pilot.pause()
        assert view.topic.title == "Index"


@pytest.mark.asyncio
async def test_sidebar_full_text_search_and_selection():
    app = WinHlpApp(HelpFile(filepath=os.path.join(DATA, "SMARTTOP.HLP")))

    async with app.run_test(size=(100, 30)) as pilot:
        await pilot.press("/")
        await pilot.press(*"very easy use")
        await pilot.pause()
        assert [topic.title for topic in app.visible_topics] == ["How to use SmartTop"]

        await pilot.press("enter")
        await pilot.pause()
        assert app.navigator.current.title == "How to use SmartTop"


@pytest.mark.asyncio
async def test_popup_and_diagnostic_screens_do_not_change_history():
    app = WinHlpApp(HelpFile(filepath=os.path.join(DATA, "SMARTTOP.HLP")))

    async with app.run_test(size=(100, 30)) as pilot:
        current = app.navigator.current
        popup = app.document.resolve_target("popup:193ADDD8")
        app._activate_target(popup)
        await pilot.pause()
        assert isinstance(app.screen, TopicPopup)
        assert app.navigator.current is current

        await pilot.press("escape")
        app._activate_target(app.document.resolve_target("macro:About()"))
        await pilot.pause()
        assert isinstance(app.screen, DiagnosticPopup)
        assert app.navigator.current is current


@pytest.mark.asyncio
async def test_indexed_bitmap_resources_are_rendered_inline():
    app = WinHlpApp(HelpFile(filepath=os.path.join(DATA, "win311", "SOL.HLP")))

    async with app.run_test(size=(100, 30)) as pilot:
        await pilot.pause()
        view = app.query_one("#topic-view", TopicView)
        view.set_topic(app.document.topics[1])
        assert not view.image_placeholders


@pytest.mark.asyncio
async def test_mediaview_button_is_a_macro_target_not_an_image():
    app = WinHlpApp(HelpFile(filepath=os.path.join(DATA, "SMARTTOP.HLP")))
    marker = 'window:inline:!,AL("RELATED_ONE;RELATED_TWO")'
    topic = ParsedTopic(
        title="Synthetic MediaView button",
        text_spans=[TextSpan(text="", embedded_image=marker, raw_data={})],
        content_blocks=[TopicTextBlock(text_spans=[TextSpan(text="", embedded_image=marker, raw_data={})])],
        raw_data={},
    )

    async with app.run_test(size=(100, 30)) as pilot:
        view = app.query_one("#topic-view", TopicView)
        view.set_topic(topic)
        await pilot.pause()

        assert not any("AL(" in placeholder for placeholder in view.image_placeholders)
        assert any(target.kind == "macro" and "AL(" in target.original for target in view.targets)


@pytest.mark.asyncio
async def test_contents_index_information_and_diagnostics_views():
    app = WinHlpApp(HelpFile(filepath=os.path.join(DATA, "SMARTTOP.HLP")))

    async with app.run_test(size=(100, 30)) as pilot:
        await pilot.press("c")
        await pilot.pause()
        assert app.sidebar_mode == "contents"
        assert app.sidebar_entries

        await pilot.press("k")
        await pilot.pause()
        assert app.sidebar_mode == "index"

        await pilot.press("i")
        await pilot.pause()
        assert isinstance(app.screen, InformationPopup)
        await pilot.press("escape", "e")
        await pilot.pause()
        assert isinstance(app.screen, InformationPopup)


@pytest.mark.asyncio
async def test_external_navigation_rejects_missing_or_non_sibling_file():
    app = WinHlpApp(HelpFile(filepath=os.path.join(DATA, "SMARTTOP.HLP")))

    async with app.run_test(size=(100, 30)) as pilot:
        target = app.document.resolve_hotspot(
            app.document.topics[0]
            .hotspot_mappings[0]
            .model_copy(update={"hotspot_type": "external_jump", "target": "topic_offset:1|file:../missing.hlp"})
        )
        app._activate_target(target)
        await pilot.pause()
        assert isinstance(app.screen, DiagnosticPopup)
        assert app.navigator.current.title == "Index"
