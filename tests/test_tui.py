"""Headless interaction tests for the terminal viewer."""

import os
import shutil
from io import StringIO
from types import SimpleNamespace

import pytest
from rich.console import Console
from rich.text import Text
from textual.widgets import Input, ListView
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
    HelpTopicsScreen,
    InformationPopup,
    OptionsScreen,
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


@pytest.mark.asyncio
async def test_startup_opens_help_topics_and_palette_command_reopens_it():
    app = WinHlpApp(HelpFile(filepath=os.path.join(DATA, "SMARTTOP.HLP")))

    async with app.run_test(size=(100, 30)) as pilot:
        await pilot.pause()
        assert isinstance(app.screen, HelpTopicsScreen)
        assert app.screen.mode == "contents"
        assert app.screen.show_all_topics

        await pilot.press("escape")
        commands = list(app.get_system_commands(app.screen))
        help_topics = next(command for command in commands if command.title == "Help Topics")
        help_topics.callback()
        await pilot.pause()

        assert isinstance(app.screen, HelpTopicsScreen)


@pytest.mark.asyncio
async def test_toolbar_help_back_and_options_actions():
    app = WinHlpApp(
        HelpFile(filepath=os.path.join(DATA, "SMARTTOP.HLP")),
        show_help_topics_on_start=False,
    )

    async with app.run_test(size=(60, 25)) as pilot:
        back = app.query_one("#toolbar-back")
        assert back.disabled

        original = app.navigator.current
        app.navigator.go_to(app.document.topics[1])
        app._show_current()
        assert not back.disabled

        await pilot.click("#toolbar-back")
        await pilot.pause()
        assert app.navigator.current is original
        assert back.disabled

        await pilot.click("#toolbar-help")
        await pilot.pause()
        assert isinstance(app.screen, HelpTopicsScreen)
        await pilot.press("escape")

        await pilot.click("#toolbar-options")
        await pilot.pause()
        assert isinstance(app.screen, OptionsScreen)
        app.screen.query_one("#option-entries", ListView).index = 1
        await pilot.press("enter")
        await pilot.pause()
        assert isinstance(app.screen, InformationPopup)


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
    app = WinHlpApp(helpfile, show_help_topics_on_start=False)
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
    app = WinHlpApp(HelpFile(filepath=os.path.join(DATA, "SMARTTOP.HLP")), show_help_topics_on_start=False)

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
    app = WinHlpApp(HelpFile(filepath=os.path.join(DATA, "SMARTTOP.HLP")), show_help_topics_on_start=False)

    async with app.run_test(size=(100, 30)) as pilot:
        assert not app.query_one("#sidebar").display
        await pilot.press("/")
        assert app.query_one("#sidebar").display
        await pilot.press(*"very easy use")
        await pilot.pause()
        assert [topic.title for topic in app.visible_topics] == ["How to use SmartTop"]

        await pilot.press("enter")
        await pilot.pause()
        assert app.navigator.current.title == "How to use SmartTop"


@pytest.mark.asyncio
async def test_popup_and_diagnostic_screens_do_not_change_history():
    app = WinHlpApp(HelpFile(filepath=os.path.join(DATA, "SMARTTOP.HLP")), show_help_topics_on_start=False)

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
    app = WinHlpApp(HelpFile(filepath=os.path.join(DATA, "win311", "SOL.HLP")), show_help_topics_on_start=False)

    async with app.run_test(size=(100, 30)) as pilot:
        await pilot.pause()
        view = app.query_one("#topic-view", TopicView)
        view.set_topic(app.document.topics[1])
        assert not view.image_placeholders


@pytest.mark.asyncio
async def test_mediaview_button_is_a_macro_target_not_an_image():
    app = WinHlpApp(HelpFile(filepath=os.path.join(DATA, "SMARTTOP.HLP")), show_help_topics_on_start=False)
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
    app = WinHlpApp(HelpFile(filepath=os.path.join(DATA, "SMARTTOP.HLP")), show_help_topics_on_start=False)

    async with app.run_test(size=(100, 30)) as pilot:
        await pilot.press("c")
        await pilot.pause()
        assert isinstance(app.screen, HelpTopicsScreen)
        assert app.screen.mode == "contents"
        assert app.screen.entries

        await pilot.press("escape")
        await pilot.press("k")
        await pilot.pause()
        assert isinstance(app.screen, HelpTopicsScreen)
        assert app.screen.mode == "index"
        assert app.screen.entries

        await pilot.press("escape")
        await pilot.press("i")
        await pilot.pause()
        assert isinstance(app.screen, InformationPopup)
        await pilot.press("escape", "e")
        await pilot.pause()
        assert isinstance(app.screen, InformationPopup)


@pytest.mark.asyncio
async def test_help_topics_contents_selection_opens_topic():
    app = WinHlpApp(HelpFile(filepath=os.path.join(DATA, "SMARTTOP.HLP")), show_help_topics_on_start=False)
    target = app.document.topics[1]
    app.document.cnt = SimpleNamespace(
        entries=[
            SimpleNamespace(
                label=target.title,
                reference=target.context_names[0],
                level=0,
                kind="topic",
            )
        ],
        indices=[],
        base_file="",
    )

    async with app.run_test(size=(100, 30)) as pilot:
        await pilot.press("c")
        await pilot.pause()
        screen = app.screen
        assert isinstance(screen, HelpTopicsScreen)
        assert not screen.show_all_topics
        index = next(index for index, entry in enumerate(screen.entries) if entry.topic is target)
        screen.query_one("#help-entries", ListView).index = index

        await pilot.press("enter")
        await pilot.pause()

        assert not isinstance(app.screen, HelpTopicsScreen)
        assert app.navigator.current is target


@pytest.mark.asyncio
async def test_help_topics_index_typeahead_and_multiple_topic_choice():
    app = WinHlpApp(
        HelpFile(filepath=os.path.join(DATA, "win95", "WINDOWS.HLP")),
        show_help_topics_on_start=False,
    )

    async with app.run_test(size=(100, 30)) as pilot:
        await pilot.press("k")
        await pilot.pause()
        screen = app.screen
        assert isinstance(screen, HelpTopicsScreen)
        search = screen.query_one("#help-index-search", Input)
        search.value = "access control"
        await pilot.pause()

        entry = next(entry for entry in screen.entries if entry.target.casefold() == "access control")
        screen.query_one("#help-entries", ListView).index = screen.entries.index(entry)
        await pilot.press("enter")
        await pilot.pause()

        assert isinstance(app.screen, TopicChoicePopup)
        assert len(app.screen.topics) > 1


@pytest.mark.asyncio
async def test_external_navigation_rejects_missing_or_non_sibling_file():
    app = WinHlpApp(HelpFile(filepath=os.path.join(DATA, "SMARTTOP.HLP")), show_help_topics_on_start=False)

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
    app = WinHlpApp(HelpFile(filepath=os.path.join(DATA, "SMARTTOP.HLP")), show_help_topics_on_start=False)
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
    app = WinHlpApp(HelpFile(filepath=os.path.join(DATA, "SMARTTOP.HLP")), show_help_topics_on_start=False)

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
    app = WinHlpApp(HelpFile(filepath=str(source)), show_help_topics_on_start=False)
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
    app = WinHlpApp(HelpFile(filepath=os.path.join(DATA, "SMARTTOP.HLP")), show_help_topics_on_start=False)
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
    app = WinHlpApp(HelpFile(filepath=os.path.join(DATA, "SMARTTOP.HLP")), show_help_topics_on_start=False)

    async with app.run_test(size=(100, 30)) as pilot:
        await pilot.press("/")
        await pilot.pause()
        await pilot.click("#topics", offset=(5, 1))
        await pilot.pause()

        assert app.navigator.current is app.document.topics[1]


@pytest.mark.asyncio
async def test_multiple_index_targets_open_topic_chooser():
    app = WinHlpApp(HelpFile(filepath=os.path.join(DATA, "SMARTTOP.HLP")), show_help_topics_on_start=False)
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
    app = WinHlpApp(HelpFile(filepath=os.path.join(DATA, "win311", "SOL.HLP")), show_help_topics_on_start=False)

    async with app.run_test(size=(30, 10)) as pilot:
        view = app.query_one("#topic-view", TopicView)
        view.set_topic(app.document.topics[1])
        await pilot.pause()

        assert view.topic is app.document.topics[1]
        assert not view.image_placeholders
        options = app.query_one("#toolbar-options")
        assert options.region.width > 0
        assert options.region.right <= 30


@pytest.mark.asyncio
@pytest.mark.parametrize("command", [0xEA, 0xEB, 0xEE, 0xEF])
@pytest.mark.parametrize("type_field", [4, 6])
async def test_parsed_external_jump_resolves_destination_context_hash(tmp_path, command, type_field):
    import struct

    fixture = os.path.join(DATA, "SMARTTOP.HLP")
    sibling = tmp_path / "sibling.hlp"
    shutil.copyfile(fixture, sibling)
    source = HelpFile(filepath=fixture)
    payload = struct.pack("<Bl", type_field, 0x427)
    if type_field == 6:
        payload += b"secondary\0"
    payload += b"sibling.hlp\0"
    commands = bytes([command]) + struct.pack("<h", len(payload)) + payload + b"\x89\xff"
    text = b"\0Follow\0\0"
    _, mappings = source.topic._parse_topic_content_interleaved(commands, text, len(text), len(text), 0)
    source.filepath = str(tmp_path / "source.hlp")
    app = WinHlpApp(source, show_help_topics_on_start=False)
    target = app.document.resolve_hotspot(mappings[0])
    assert "file:sibling.hlp" in target.original
    if type_field == 6:
        assert "window:secondary" in target.original

    async with app.run_test(size=(100, 30)) as pilot:
        app._activate_target(target)
        await pilot.pause()
        if command in (0xEA, 0xEE) or type_field == 6:
            assert isinstance(app.screen, TopicPopup)
            assert app.screen.topic.title == "How to use SmartTop"
            assert app.screen.document.helpfile.filepath == str(sibling)
        else:
            assert app.helpfile.filepath == str(sibling)
            assert app.navigator.current.title == "How to use SmartTop"


@pytest.mark.asyncio
@pytest.mark.parametrize("filename", ["", "sibling.hlp"])
@pytest.mark.parametrize("map_id", [42, 999])
async def test_jumpcontext_resolves_map_ids_in_destination(tmp_path, monkeypatch, filename, map_id):
    import struct
    from winhlp.lib.internal_files.ctxomap import CtxoMapFile

    fixture = os.path.join(DATA, "SMARTTOP.HLP")
    sibling = tmp_path / "sibling.hlp"
    shutil.copyfile(fixture, sibling)

    def load_with_map(filepath):
        helpfile = HelpFile(filepath=filepath)
        intended = helpfile.get_document().resolve_target("topic:00000427").topic
        helpfile.ctxomap = CtxoMapFile(filename="|CTXOMAP", raw_data=struct.pack("<Hll", 1, 42, intended.topic_offset))
        return helpfile

    monkeypatch.setattr("winhlp.tui.HelpFile", load_with_map)
    source = load_with_map(fixture)
    source.filepath = str(tmp_path / "source.hlp")
    app = WinHlpApp(source, show_help_topics_on_start=False)
    target = app.document.resolve_target(f'macro:JumpContext("{filename}", {map_id})')

    async with app.run_test(size=(100, 30)) as pilot:
        app._activate_target(target)
        await pilot.pause()
        if map_id == 999:
            assert isinstance(app.screen, DiagnosticPopup)
        else:
            assert app.navigator.current.title == "How to use SmartTop"
            assert app.helpfile.filepath == str(sibling if filename else tmp_path / "source.hlp")


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "reference, base, destination, popup",
    [
        ("HO@sibling.hlp", "", "sibling.hlp", False),
        ("HO>secondary@sibling.hlp", "", "sibling.hlp", True),
        ("HO>secondary", "", "source.hlp", True),
        ("HO", "sibling.hlp", "sibling.hlp", False),
        ("HO@missing.hlp", "", None, False),
    ],
)
async def test_contents_selection_preserves_file_and_window(tmp_path, reference, base, destination, popup):
    from winhlp.lib.cnt import load_cnt

    fixture = os.path.join(DATA, "SMARTTOP.HLP")
    for filename in ("source.hlp", "sibling.hlp"):
        shutil.copyfile(fixture, tmp_path / filename)
    contents = tmp_path / "source.cnt"
    contents.write_text(f":Base {base}\n1 Destination={reference}\n", encoding="cp1252")
    app = WinHlpApp(HelpFile(filepath=str(tmp_path / "source.hlp")), show_help_topics_on_start=False)
    app.document.cnt = load_cnt(contents)
    entry = app.document.contents_entries()[0]
    # Both files contain HO; an external entry must not bind to the local match.
    assert entry.topic is None

    async with app.run_test(size=(100, 30)) as pilot:
        await pilot.press("c")
        await pilot.pause()
        assert isinstance(app.screen, HelpTopicsScreen)
        app.screen.query_one("#help-entries", ListView).index = 0
        await pilot.press("enter")
        await pilot.pause()
        if destination is None:
            assert isinstance(app.screen, DiagnosticPopup)
        elif popup:
            assert isinstance(app.screen, TopicPopup)
            assert app.screen.document.helpfile.filepath == str(tmp_path / destination)
            assert app.screen.topic.title == "How to use SmartTop"
        else:
            assert app.helpfile.filepath == str(tmp_path / destination)
            assert app.navigator.current.title == "How to use SmartTop"


@pytest.mark.asyncio
async def test_external_cnt_index_opens_target_help_file(tmp_path):
    from winhlp.lib.cnt import load_cnt

    fixture = os.path.join(DATA, "SMARTTOP.HLP")
    source = tmp_path / "source.hlp"
    sibling = tmp_path / "sibling.hlp"
    shutil.copyfile(fixture, source)
    shutil.copyfile(fixture, sibling)
    cnt_path = tmp_path / "source.cnt"
    cnt_path.write_text(":Index Sibling index=sibling.hlp\n", encoding="cp1252")
    app = WinHlpApp(HelpFile(filepath=str(source)), show_help_topics_on_start=False)
    app.document.cnt = load_cnt(cnt_path)

    async with app.run_test(size=(100, 30)) as pilot:
        await pilot.press("k")
        await pilot.pause()
        assert isinstance(app.screen, HelpTopicsScreen)
        assert app.screen.entries[0].kind == "external_index"
        await pilot.press("enter")
        await pilot.pause()

        assert app.helpfile.filepath == str(sibling)
        assert app.navigator.current is app.document.initial_topic


@pytest.mark.asyncio
@pytest.mark.parametrize("action", ["link", "entry", "choice", "search", "search_enter", "browse", "local_external"])
async def test_new_local_navigation_clears_cross_file_forward_history(tmp_path, action):
    from winhlp.lib.document import NavigationEntry

    fixture = os.path.join(DATA, "SMARTTOP.HLP")
    for filename in ("source.hlp", "sibling.hlp"):
        shutil.copyfile(fixture, tmp_path / filename)
    app = WinHlpApp(HelpFile(filepath=str(tmp_path / "source.hlp")), show_help_topics_on_start=False)

    async with app.run_test(size=(100, 30)) as pilot:
        app._activate_target(ResolvedTarget("external", "context_hash:1063|file:sibling.hlp", document=app.document))
        await pilot.pause()
        app.action_history_back()
        await pilot.pause()
        assert app.document_forward_stack
        # No-op selections must preserve Forward.
        app._activate_target(ResolvedTarget("topic", "current", topic=app.navigator.current))
        assert app.document_forward_stack
        destination = app.document.topics[2]
        if action == "link":
            app._activate_target(ResolvedTarget("topic", "new", topic=destination))
        elif action == "entry":
            app._activate_navigation_entry(NavigationEntry("New topic", destination))
        elif action == "choice":
            app._topic_chosen(destination)
        elif action in ("search", "search_enter"):
            app.visible_topics = [destination]
            if action == "search":
                app.search_submitted()
            else:
                app.action_focus_search()
                await pilot.pause()
                app.action_activate_link()
        elif action == "browse":
            app.navigator.current.browse_next_topic = destination.topic_number
            app.action_browse_next()
        else:
            app._activate_target(ResolvedTarget("external", f"topic_offset:{destination.topic_offset}"))
        await pilot.pause()
        assert app.navigator.current is destination
        assert not app.document_forward_stack
        assert not app.navigator.forward_stack
        app.action_history_forward()
        assert app.helpfile.filepath == str(tmp_path / "source.hlp")
        assert app.navigator.current is destination


@pytest.mark.asyncio
async def test_new_cross_file_navigation_discards_old_local_forward_branch(tmp_path):
    fixture = os.path.join(DATA, "SMARTTOP.HLP")
    for filename in ("source.hlp", "sibling.hlp"):
        shutil.copyfile(fixture, tmp_path / filename)
    app = WinHlpApp(HelpFile(filepath=str(tmp_path / "source.hlp")), show_help_topics_on_start=False)

    async with app.run_test(size=(100, 30)) as pilot:
        app._activate_target(ResolvedTarget("topic", "old branch", topic=app.document.topics[2]))
        app.action_history_back()
        assert app.navigator.forward_stack
        app._activate_target(ResolvedTarget("external", "context_hash:1063|file:sibling.hlp", document=app.document))
        await pilot.pause()
        app.action_history_back()
        await pilot.pause()
        assert not app.navigator.forward_stack
        assert app.document_forward_stack
        app.action_history_forward()
        await pilot.pause()
        assert app.helpfile.filepath == str(tmp_path / "sibling.hlp")
        assert app.navigator.current.title == "How to use SmartTop"
