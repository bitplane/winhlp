"""Headless interaction tests for the terminal viewer."""

import os
import shutil
from io import StringIO

import pytest
from rich.console import Console
from rich.text import Text
from winhlp.lib.document import ResolvedTarget
from winhlp.lib.hlp import HelpFile
from winhlp.lib.internal_files.topic import (
    ParsedTopic,
    Table,
    TableCell,
    TableRow,
    TextSpan,
    TopicTableBlock,
    TopicTextBlock,
)
from winhlp.tui import (
    DiagnosticPopup,
    InformationPopup,
    TopicChoicePopup,
    TopicPopup,
    TopicView,
    WinHlpApp,
    _span_style,
    _span_text,
)


def test_topic_view_does_not_apply_text_link_styles_to_image_pixels():
    view = object.__new__(TopicView)

    assert not view.link_style
    assert view.link_style_hover.reverse
    assert view.link_style_hover.color is None
    assert view.link_style_hover.bgcolor is None
    assert view.link_style_hover.underline is None
    assert view.link_style_hover.bold is None


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
async def test_windows_topic_is_compact_inline_and_has_no_default_metadata():
    helpfile = HelpFile(filepath=os.path.join(DATA, "win95", "WINDOWS.HLP"))
    app = WinHlpApp(helpfile)
    topic = next(topic for topic in app.document.topics if topic.title == "Creating a startup disk")
    app.navigator.current = topic

    async with app.run_test(size=(100, 35)) as pilot:
        await pilot.pause()
        fixed = app.query_one("#fixed-header", TopicView)
        view = app.query_one("#topic-view", TopicView)
        output = StringIO()
        Console(file=output, width=100, color_system=None).print(view._Static__content)
        rendered = output.getvalue()

        assert not fixed.display
        assert "id:" not in rendered
        assert "keywords:" not in rendered
        assert rendered.count("To create a startup disk") == 1
        assert any("Click here" in line and "to open the Add/Remove" in line for line in rendered.splitlines())
        assert "▪" in rendered


@pytest.mark.asyncio
async def test_link_keyboard_navigation_and_history():
    app = WinHlpApp(HelpFile(filepath=os.path.join(DATA, "SMARTTOP.HLP")))

    async with app.run_test(size=(100, 30)) as pilot:
        view = app.query_one("#topic-view", TopicView)
        assert app.theme == "winhelp"
        assert view.topic.title == "Index"
        assert len(app._all_targets()) == 5

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


@pytest.mark.asyncio
async def test_fixed_and_scrolling_regions_share_keyboard_target_order():
    app = WinHlpApp(HelpFile(filepath=os.path.join(DATA, "SMARTTOP.HLP")))
    topic = app.navigator.current
    assert topic is not None
    boundary = topic.content_blocks[2].source_record_offset
    topic.non_scroll_offset = boundary

    async with app.run_test(size=(100, 30)) as pilot:
        fixed = app.query_one("#fixed-header", TopicView)
        scrolling = app.query_one("#topic-view", TopicView)
        assert fixed.display
        assert fixed.targets and scrolling.targets

        await pilot.press("shift+tab")
        await pilot.pause()

        assert scrolling.selected_link == len(app._all_targets()) - 1


@pytest.mark.asyncio
async def test_popup_has_local_back_and_forward_history():
    app = WinHlpApp(HelpFile(filepath=os.path.join(DATA, "SMARTTOP.HLP")))

    async with app.run_test(size=(100, 30)) as pilot:
        popup = TopicPopup(app.document, app.document.topics[0])
        app.push_screen(popup)
        await pilot.pause()
        popup._activate(ResolvedTarget("topic", "test", topic=app.document.topics[1], document=app.document))
        assert popup.topic is app.document.topics[1]

        await pilot.press("b")
        assert popup.topic is app.document.topics[0]
        await pilot.press("f")
        assert popup.topic is app.document.topics[1]


@pytest.mark.asyncio
async def test_successful_external_navigation_uses_source_document_directory(tmp_path):
    source = tmp_path / "source.hlp"
    sibling = tmp_path / "sibling.hlp"
    fixture = os.path.join(DATA, "SMARTTOP.HLP")
    shutil.copyfile(fixture, source)
    shutil.copyfile(fixture, sibling)
    app = WinHlpApp(HelpFile(filepath=str(source)))
    offset = app.document.topics[1].topic_offset
    target = ResolvedTarget(
        "external",
        f"topic_offset:{offset}|file:sibling.hlp",
        document=app.document,
    )

    async with app.run_test(size=(100, 30)) as pilot:
        app._activate_target(target)
        await pilot.pause()

        assert app.helpfile.filepath == str(sibling)
        assert app.navigator.current.topic_offset == offset
        await pilot.press("b")
        assert app.helpfile.filepath == str(source)


@pytest.mark.asyncio
async def test_table_cell_links_join_topic_target_order_without_span_markers():
    app = WinHlpApp(HelpFile(filepath=os.path.join(DATA, "SMARTTOP.HLP")))
    destination = app.document.topics[1]
    context = destination.context_names[0]
    table = Table(
        column_count=2,
        column_widths=[1, 2],
        rows=[
            TableRow(
                cells=[
                    TableCell(
                        text_spans=[TextSpan(text="Open", hyperlink_target=f"topic:{context}", raw_data={})],
                        column_span=2,
                        raw_data={},
                    )
                ],
                raw_data={},
            )
        ],
        raw_data={},
    )
    topic = ParsedTopic(
        title="Table",
        content_blocks=[TopicTableBlock(table=table)],
        tables=[table],
        raw_data={},
    )

    async with app.run_test(size=(60, 20)) as pilot:
        view = app.query_one("#topic-view", TopicView)
        view.set_topic(topic)
        await pilot.pause()

        assert len(view.targets) == 1
        console = Console(record=True, width=60, file=StringIO())
        console.print(view.render())
        assert "[span" not in console.export_text()


@pytest.mark.asyncio
async def test_mouse_selects_sidebar_topics():
    app = WinHlpApp(HelpFile(filepath=os.path.join(DATA, "SMARTTOP.HLP")))

    async with app.run_test(size=(100, 30)) as pilot:
        await pilot.click("#topics", offset=(5, 1))
        await pilot.pause()

        assert app.navigator.current is app.document.topics[1]


@pytest.mark.asyncio
async def test_multiple_index_targets_open_topic_chooser():
    app = WinHlpApp(HelpFile(filepath=os.path.join(DATA, "SMARTTOP.HLP")))
    topics = (app.document.topics[1], app.document.topics[2])

    async with app.run_test(size=(100, 30)) as pilot:
        app._activate_target(ResolvedTarget("choice", "keyword", topics=topics, document=app.document))
        await pilot.pause()
        assert isinstance(app.screen, TopicChoicePopup)

        await pilot.press("enter")
        await pilot.pause()
        assert app.navigator.current is topics[0]


@pytest.mark.asyncio
async def test_narrow_terminal_and_resize_keep_topic_renderable():
    app = WinHlpApp(HelpFile(filepath=os.path.join(DATA, "win311", "SOL.HLP")))

    async with app.run_test(size=(30, 10)) as pilot:
        view = app.query_one("#topic-view", TopicView)
        view.set_topic(app.document.topics[1])
        await pilot.pause()

        assert view.topic is app.document.topics[1]
        assert not view.image_placeholders
