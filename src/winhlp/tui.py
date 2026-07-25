"""Interactive terminal viewer for parsed Windows Help files."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Iterable, Optional

from rich import box
from rich.console import Group, RenderableType
from rich.panel import Panel
from rich.style import Style
from rich.table import Table as RichTable
from rich.text import Text
from textual import on
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.screen import ModalScreen
from textual.theme import Theme
from textual.widgets import Footer, Header, Input, Label, ListItem, ListView, Static

from .lib.document import (
    HelpDocument,
    HelpNavigator,
    NavigationEntry,
    ResolvedTarget,
    help_title,
    parse_embedded_resource,
)
from .lib.hlp import HelpFile
from .lib.internal_files.topic import ParsedTopic, TextSpan, TopicTableBlock, TopicTextBlock
from .lib.raster import HalfBlockRasterizer, RasterHotspot, TerminalRasterizer, decode_bmp


WINHELP_THEME = Theme(
    name="winhelp",
    primary="#000080",
    secondary="#008080",
    warning="#808000",
    error="#800000",
    success="#008000",
    accent="#008000",
    foreground="#000000",
    background="#c0c0c0",
    surface="#ffffff",
    panel="#c0c0c0",
    boost="#000080",
    dark=False,
    luminosity_spread=0.12,
)


def _span_style(span: TextSpan) -> Style:
    """Preserve document emphasis while allowing the active theme to own colour."""
    return Style(
        italic=span.is_italic,
        underline=span.is_underline,
        underline2=span.is_double_underline,
        strike=span.is_strikethrough,
        bold=span.is_bold or bool(span.font_half_points and span.font_half_points >= 28),
        dim=bool(span.font_half_points and span.font_half_points <= 14),
    )


_SUPERSCRIPT = str.maketrans("0123456789+-=()", "⁰¹²³⁴⁵⁶⁷⁸⁹⁺⁻⁼⁽⁾")
_SUBSCRIPT = str.maketrans("0123456789+-=()", "₀₁₂₃₄₅₆₇₈₉₊₋₌₍₎")


def _span_text(span: TextSpan) -> str:
    text = span.text.upper() if span.is_small_caps else span.text
    if span.is_superscript:
        return text.translate(_SUPERSCRIPT)
    if span.is_subscript:
        return text.translate(_SUBSCRIPT)
    return text


def topic_label(topic: ParsedTopic, position: int) -> str:
    if topic.title:
        return topic.title
    if topic.topic_number is not None:
        return f"Topic {topic.topic_number}"
    return f"Topic {position + 1}"


class TopicView(Static):
    """A Rich-backed topic renderer with keyboard-selectable inline hotspots."""

    can_focus = True

    def __init__(
        self,
        document: HelpDocument,
        topic: Optional[ParsedTopic] = None,
        *,
        interactive: bool = True,
        action_namespace: str = "app",
        start_block: int = 0,
        show_heading: bool = True,
        id: Optional[str] = None,
    ):
        super().__init__(id=id)
        self.document = document
        self.topic = topic
        self.interactive = interactive
        self.action_namespace = action_namespace
        self.start_block = start_block
        self.show_heading = show_heading
        self.targets: list[ResolvedTarget] = []
        self.image_placeholders: list[str] = []
        self.rasterizer: TerminalRasterizer = HalfBlockRasterizer()
        self.selected_link = -1

    def on_mount(self) -> None:
        self.refresh_topic()

    def set_topic(self, topic: Optional[ParsedTopic]) -> None:
        self.topic = topic
        self.selected_link = -1
        self.refresh_topic()

    def select_next_link(self, direction: int) -> bool:
        if not self.interactive or not self.targets:
            return False
        self.selected_link = (self.selected_link + direction) % len(self.targets)
        self.refresh_topic()
        self.focus()
        return True

    def selected_target(self) -> Optional[ResolvedTarget]:
        if 0 <= self.selected_link < len(self.targets):
            return self.targets[self.selected_link]
        return None

    def refresh_topic(self) -> None:
        self.targets = []
        self.image_placeholders = []
        renderables: list[RenderableType] = []
        if self.topic is None:
            renderables.append(Text("This help file contains no parsed topics.", style="italic dim"))
            self.update(Group(*renderables))
            return

        if self.show_heading:
            renderables.append(Text(self.topic.title or "Untitled topic", style="bold"))
        metadata = []
        if self.topic.context_names:
            metadata.append("id: " + ", ".join(self.topic.context_names[:6]))
        if self.topic.keywords:
            metadata.append("keywords: " + ", ".join(self.topic.keywords[:8]))
        if metadata:
            renderables.append(Text(" · ".join(metadata), style="dim"))
        renderables.append(Text())

        blocks = self.topic.content_blocks
        if not blocks:
            blocks = [TopicTextBlock(text_spans=self.topic.text_spans)]
            blocks.extend(TopicTableBlock(table=table) for table in self.topic.tables)
        for block in blocks[self.start_block :]:
            if isinstance(block, TopicTextBlock):
                renderables.extend(self._render_text_block(block))
            else:
                renderables.append(self._render_table(block))
        if self.topic.annotations:
            notes = Text()
            for annotation in self.topic.annotations:
                notes.append(f"• {annotation}\n")
            renderables.append(Panel(notes, title="Annotations"))
        self.update(Group(*renderables))

    def _render_text_block(self, block: TopicTextBlock) -> Iterable[RenderableType]:
        text = Text()
        mappings = {mapping.text_span_index: mapping for mapping in block.hotspot_mappings}
        last_image_marker = None

        def flush_text():
            nonlocal text
            if not text.plain:
                return None
            rendered = self._apply_paragraph_layout(text, block)
            text = Text()
            return rendered

        for index, span in enumerate(block.text_spans):
            start = len(text)
            text.append(_span_text(span), _span_style(span))
            end = len(text)
            target = None
            if span.hyperlink_target:
                target = self.document.resolve_target(span.hyperlink_target)
            elif index in mappings:
                target = self.document.resolve_hotspot(mappings[index])
            if target is not None and self.interactive and end > start:
                link_index = len(self.targets)
                self.targets.append(target)
                selected = link_index == self.selected_link
                style = Style(
                    underline=True,
                    reverse=selected,
                    meta={"@click": f"{self.action_namespace}.follow_link({link_index})"},
                )
                text.stylize(style, start, end)
            if span.embedded_image and span.embedded_image != last_image_marker:
                pending = flush_text()
                if pending is not None:
                    yield pending
                resource = parse_embedded_resource(span.embedded_image)
                if resource is not None:
                    yield self._render_image(resource)
                last_image_marker = span.embedded_image
            elif not span.embedded_image:
                last_image_marker = None
        pending = flush_text()
        if pending is not None:
            yield pending
        yield Text()

    def _apply_paragraph_layout(self, text: Text, block: TopicTextBlock) -> RenderableType:
        paragraph = block.paragraph_info
        if paragraph is None:
            return text
        if paragraph.bits.center_aligned_paragraph:
            text.justify = "center"
        elif paragraph.bits.right_aligned_paragraph:
            text.justify = "right"
        indent = max(0, min(12, (paragraph.left_indent or 0) // 120))
        if indent:
            text = Text(" " * indent) + text
        if paragraph.tab_info and paragraph.tab_info.tabs:
            first_stop = max(2, min(16, paragraph.tab_info.tabs[0].position // 120))
            text.expand_tabs(first_stop)
        above = 1 if paragraph.spacing_above else 0
        below = 1 if paragraph.spacing_below else 0
        if above:
            text = Text("\n" * above) + text
        if below:
            text.append("\n" * below)
        border = paragraph.border_info
        if border and any(
            (border.border_box, border.border_top, border.border_left, border.border_bottom, border.border_right)
        ):
            return Panel(text, box=box.DOUBLE if border.border_double else box.SQUARE, padding=(0, 1))
        return text

    def _render_image(self, resource) -> RenderableType:
        label = resource.resource_name or resource.reference
        bitmaps = self.document.helpfile.bitmaps
        key = label
        bitmap_file = bitmaps.get(key)
        if bitmap_file is None and key.startswith("|"):
            bitmap_file = bitmaps.get(key[1:])
        if bitmap_file is None and not key.startswith("|"):
            bitmap_file = bitmaps.get("|" + key)
        extracted = bitmap_file.extract_image(0) if bitmap_file is not None else None
        image = decode_bmp(extracted[1]) if extracted and extracted[0] == "bmp" else None
        if image is None:
            placeholder = f"[image: {label}, {resource.alignment}]"
            self.image_placeholders.append(placeholder)
            return Text(placeholder, style="italic dim")

        source_hotspots = bitmap_file.bitmaps[0].hotspots if bitmap_file.bitmaps else []
        raster_hotspots = []
        labels = Text()
        selected_raster_hotspot = -1
        for hotspot_number, hotspot in enumerate(source_hotspots, start=1):
            target = self.document.resolve_context_hash(hotspot.hash_value)
            link_index = len(self.targets)
            self.targets.append(target)
            if link_index == self.selected_link:
                selected_raster_hotspot = hotspot_number - 1
            action = f"{self.action_namespace}.follow_link({link_index})"
            raster_hotspots.append(RasterHotspot(hotspot.x, hotspot.y, hotspot.width, hotspot.height, action))
            start = len(labels)
            labels.append(f"[{hotspot_number}] {target.topic.title if target.topic else target.original}\n")
            labels.stylize(
                Style(underline=True, reverse=link_index == self.selected_link, meta={"@click": action}),
                start,
                len(labels),
            )
        rendered = self.rasterizer.render(
            image,
            max_width=max(8, (self.size.width or 64) - 2),
            hotspots=raster_hotspots,
            selected_hotspot=selected_raster_hotspot,
        )
        return Group(rendered, labels) if labels.plain else rendered

    @staticmethod
    def _render_table(block: TopicTableBlock) -> RichTable:
        parsed = block.table
        columns = max(parsed.column_count, max((len(row.cells) for row in parsed.rows), default=0), 1)
        table = RichTable(show_header=False, box=box.SIMPLE, pad_edge=False)
        widths = parsed.column_widths[:columns]
        width_total = sum(max(width, 1) for width in widths) or columns
        for column in range(columns):
            ratio = max(widths[column], 1) if column < len(widths) else max(1, width_total // columns)
            table.add_column(ratio=ratio)
        for row in parsed.rows:
            cells = []
            for cell in row.cells:
                cell_text = Text()
                for span in cell.text_spans:
                    cell_text.append(_span_text(span), _span_style(span))
                cell_text.justify = cell.alignment
                if cell.column_span > 1 or cell.row_span > 1:
                    cell_text.append(f" [span {cell.column_span}×{cell.row_span}]", style="dim")
                cells.append(cell_text)
            cells.extend(Text() for _ in range(columns - len(cells)))
            table.add_row(*cells[:columns])
        return table


class TopicPopup(ModalScreen):
    BINDINGS = [
        Binding("escape", "dismiss", "Close"),
        Binding("q", "dismiss", "Close"),
        Binding("tab", "next_link", "Next link", priority=True),
        Binding("shift+tab", "previous_link", "Previous link", priority=True),
        Binding("enter", "activate_link", "Open link", priority=True),
    ]

    def __init__(self, document: HelpDocument, topic: ParsedTopic):
        super().__init__()
        self.document = document
        self.topic = topic

    def compose(self) -> ComposeResult:
        with Vertical(id="popup"):
            yield VerticalScroll(
                TopicView(self.document, self.topic, interactive=True, action_namespace="screen", id="popup-topic")
            )
            yield Label("Esc: close", id="popup-hint")

    def action_dismiss(self) -> None:
        self.dismiss()

    def action_follow_link(self, index: int) -> None:
        view = self.query_one("#popup-topic", TopicView)
        if 0 <= index < len(view.targets):
            self._activate(view.targets[index])

    def action_next_link(self) -> None:
        self.query_one("#popup-topic", TopicView).select_next_link(1)

    def action_previous_link(self) -> None:
        self.query_one("#popup-topic", TopicView).select_next_link(-1)

    def action_activate_link(self) -> None:
        target = self.query_one("#popup-topic", TopicView).selected_target()
        if target is not None:
            self._activate(target)

    def _activate(self, target: ResolvedTarget) -> None:
        if target.topic is not None and target.kind in ("topic", "popup"):
            self.topic = target.topic
            self.query_one("#popup-topic", TopicView).set_topic(target.topic)
        elif target.kind == "external":
            self.dismiss()
            self.app._activate_external_target(target)
        else:
            self.app.push_screen(DiagnosticPopup(target.detail or f"Unsupported target: {target.original}"))


class DiagnosticPopup(ModalScreen):
    BINDINGS = [Binding("escape", "dismiss", "Close"), Binding("q", "dismiss", "Close")]

    def __init__(self, message: str):
        super().__init__()
        self.message = message

    def compose(self) -> ComposeResult:
        with Vertical(id="diagnostic"):
            yield Static(self.message)
            yield Label("Esc: close", id="popup-hint")

    def action_dismiss(self) -> None:
        self.dismiss()


class InformationPopup(ModalScreen):
    BINDINGS = [Binding("escape", "dismiss", "Close"), Binding("q", "dismiss", "Close")]

    def __init__(self, title: str, content: RenderableType):
        super().__init__()
        self.popup_title = title
        self.content = content

    def compose(self) -> ComposeResult:
        with Vertical(id="popup"):
            yield Label(self.popup_title, classes="popup-title")
            yield VerticalScroll(Static(self.content))
            yield Label("Esc: close", id="popup-hint")

    def action_dismiss(self) -> None:
        self.dismiss()


class WinHlpApp(App):
    """Browse a parsed Windows Help file in the terminal."""

    CSS = """
    Screen { layout: vertical; background: $background; color: $text; }
    #body { height: 1fr; }
    #sidebar { width: 30; border-right: solid $primary; background: $panel; }
    #search { dock: top; }
    #topics { height: 1fr; }
    #topic-pane { width: 1fr; background: $surface; }
    #topic-scroll { width: 1fr; padding: 1 2; background: $surface; }
    #fixed-header {
        display: none;
        height: auto;
        max-height: 12;
        padding: 1 2;
        border-bottom: solid $primary;
        background: $surface;
        color: $text;
    }
    #topic-view { width: 1fr; height: auto; background: $surface; color: $text; }
    TopicView {
        link-color: $accent;
        link-color-hover: $accent-lighten-2;
        link-style: underline;
        link-style-hover: bold underline;
    }
    TopicPopup, DiagnosticPopup { align: center middle; background: $background 70%; }
    #popup, #diagnostic { width: 80%; height: 80%; padding: 1 2; border: heavy $accent; background: $surface; }
    #diagnostic { height: auto; max-height: 16; }
    #popup-hint { dock: bottom; height: 1; color: $text-muted; }
    .popup-title { height: 2; text-style: bold; color: $primary; }
    #sidebar-title { height: 1; text-style: bold; padding-left: 1; }
    """

    BINDINGS = [
        Binding("q", "quit", "Quit"),
        Binding("b,alt+left", "history_back", "Back"),
        Binding("f,alt+right", "history_forward", "Forward"),
        Binding("[", "browse_previous", "Browse prev"),
        Binding("]", "browse_next", "Browse next"),
        Binding("/", "focus_search", "Search"),
        Binding("t", "toggle_sidebar", "Topics"),
        Binding("o", "show_topics", "Topics list"),
        Binding("c", "show_contents", "Contents"),
        Binding("k", "show_index", "Index"),
        Binding("i", "file_information", "File info"),
        Binding("d", "topic_details", "Topic details"),
        Binding("e", "parse_errors", "Errors"),
        Binding("tab", "next_link", "Next link", priority=True),
        Binding("shift+tab", "previous_link", "Previous link", priority=True),
        Binding("enter", "activate_link", "Open link", priority=True),
    ]

    def __init__(self, helpfile):
        super().__init__()
        self.register_theme(WINHELP_THEME)
        self.theme = WINHELP_THEME.name
        self.helpfile = helpfile
        self.document = helpfile.get_document()
        self.navigator = HelpNavigator(self.document)
        self.document_back_stack: list[tuple[HelpFile, HelpDocument, HelpNavigator]] = []
        self.document_forward_stack: list[tuple[HelpFile, HelpDocument, HelpNavigator]] = []
        self.sidebar_mode = "topics"
        self.visible_topics = list(self.document.topics)
        self.sidebar_entries = [
            NavigationEntry(topic_label(topic, index), topic) for index, topic in enumerate(self.document.topics)
        ]
        self.title = help_title(helpfile)
        self.sub_title = os.path.basename(helpfile.filepath)

    def compose(self) -> ComposeResult:
        yield Header()
        with Horizontal(id="body"):
            with Vertical(id="sidebar"):
                yield Label("Topics", id="sidebar-title")
                yield Input(placeholder="Search topics…", id="search")
                yield ListView(*self._topic_items(self.sidebar_entries), id="topics")
            with Vertical(id="topic-pane"):
                yield Static(id="fixed-header")
                with VerticalScroll(id="topic-scroll"):
                    yield TopicView(self.document, self.navigator.current, id="topic-view")
        yield Footer()

    def on_mount(self) -> None:
        self._update_subtitle()
        self._show_current()
        self.query_one(TopicView).focus()

    @staticmethod
    def _topic_items(entries) -> list[ListItem]:
        return [ListItem(Label("  " * entry.level + entry.label)) for entry in entries]

    def _show_current(self) -> None:
        topic = self.navigator.current
        fixed_count, fixed_text = self._fixed_topic_header(topic)
        fixed = self.query_one("#fixed-header", Static)
        fixed.display = bool(fixed_text)
        fixed.update(fixed_text)
        view = self.query_one("#topic-view", TopicView)
        view.document = self.document
        view.start_block = fixed_count
        view.show_heading = not fixed_text
        view.set_topic(topic)
        self.query_one("#topic-scroll", VerticalScroll).scroll_home(animate=False)
        self._update_subtitle()

    @staticmethod
    def _fixed_topic_header(topic: Optional[ParsedTopic]) -> tuple[int, Text]:
        """Approximate WinHelp's non-scrolling region from paragraph offsets."""
        if topic is None or topic.non_scroll_offset is None or topic.topic_offset is None:
            return 0, Text()
        if topic.non_scroll_offset <= topic.topic_offset:
            return 0, Text()
        offset = topic.topic_offset
        count = 0
        body = Text()
        has_links = False
        for block in topic.content_blocks:
            if offset >= topic.non_scroll_offset:
                break
            if isinstance(block, TopicTextBlock):
                for span in block.text_spans:
                    body.append(_span_text(span), _span_style(span))
                    has_links = has_links or bool(span.hyperlink_target)
                has_links = has_links or bool(block.hotspot_mappings)
                length = block.paragraph_info.topic_length if block.paragraph_info else 0
            else:
                body.append("[table]\n", style="dim")
                length = 0
            count += 1
            offset += max(length, 1)
        # Keep interactive fixed-region content in the main TopicView until a
        # future composite view can share one keyboard target list.
        if not count or has_links:
            return 0, Text()
        heading = Text(topic.title or "Untitled topic", style="bold")
        heading.append("\n")
        heading.append_text(body)
        return count, heading

    def _update_subtitle(self) -> None:
        current = self.navigator.current
        if current is None:
            self.sub_title = os.path.basename(self.helpfile.filepath)
            return
        position = self.document.topics.index(current) + 1
        warning = f" · ⚠ {len(self.helpfile.parse_errors)}" if self.helpfile.parse_errors else ""
        self.sub_title = f"{os.path.basename(self.helpfile.filepath)} · {position}/{len(self.document.topics)}{warning}"

    def action_follow_link(self, index: int) -> None:
        view = self.query_one("#topic-view", TopicView)
        if 0 <= index < len(view.targets):
            self._activate_target(view.targets[index])

    def _activate_target(self, target: ResolvedTarget) -> None:
        if target.kind == "topic" and target.topic is not None:
            self.navigator.go_to(target.topic)
            self._show_current()
        elif target.kind == "popup" and target.topic is not None:
            self.push_screen(TopicPopup(self.document, target.topic))
        elif target.kind == "external":
            self._activate_external_target(target)
        else:
            self.push_screen(DiagnosticPopup(target.detail or f"Unsupported target: {target.original}"))

    def _activate_external_target(self, target: ResolvedTarget) -> None:
        fields = {}
        for field in target.original.split("|"):
            key, separator, value = field.partition(":")
            if separator:
                fields[key] = value
        try:
            offset = int(fields["topic_offset"], 0)
        except (KeyError, ValueError):
            offset = None

        filename = fields.get("file")
        if not filename:
            topic = self.document.topic_for_offset(offset)
            if topic is not None:
                if target.open_as_popup or "window" in fields or "window_number" in fields:
                    self.push_screen(TopicPopup(self.document, topic))
                else:
                    self.navigator.go_to(topic)
                    self._show_current()
                return
            self.push_screen(DiagnosticPopup(target.detail or f"Could not resolve target: {target.original}"))
            return

        candidate = self._sibling_help_path(filename)
        if candidate is None:
            self.push_screen(DiagnosticPopup(f"Sibling help file was not found: {filename}"))
            return
        try:
            helpfile = HelpFile(filepath=str(candidate))
            document = helpfile.get_document()
        except Exception as error:
            self.push_screen(DiagnosticPopup(f"Could not open {candidate.name}: {error}"))
            return
        topic = document.topic_for_offset(offset) if offset is not None else document.initial_topic
        if topic is None:
            self.push_screen(DiagnosticPopup(f"{candidate.name} does not contain the requested topic."))
            return
        if target.open_as_popup or "window" in fields or "window_number" in fields:
            self.push_screen(TopicPopup(document, topic))
            return
        self.document_back_stack.append((self.helpfile, self.document, self.navigator))
        self.document_forward_stack.clear()
        self._switch_document(helpfile, document, HelpNavigator(document, topic))

    def _sibling_help_path(self, filename: str) -> Optional[Path]:
        """Find a named sibling HLP without allowing the target to escape its directory."""
        requested = Path(filename.replace("\\", "/")).name
        directory = Path(self.helpfile.filepath).resolve().parent
        exact = directory / requested
        if exact.is_file():
            return exact
        folded = requested.casefold()
        try:
            return next(path for path in directory.iterdir() if path.is_file() and path.name.casefold() == folded)
        except (OSError, StopIteration):
            return None

    def _switch_document(self, helpfile: HelpFile, document: HelpDocument, navigator: HelpNavigator) -> None:
        self.helpfile = helpfile
        self.document = document
        self.navigator = navigator
        self.title = help_title(helpfile)
        self.sidebar_entries = self._filter_sidebar_entries("")
        self.visible_topics = [entry.topic for entry in self.sidebar_entries if entry.topic is not None]
        self.run_worker(self._replace_sidebar_items(), group="document-sidebar", exclusive=True)
        self._show_current()

    async def _replace_sidebar_items(self) -> None:
        topics = self.query_one("#topics", ListView)
        await topics.clear()
        if self.sidebar_entries:
            await topics.extend(self._topic_items(self.sidebar_entries))

    def action_next_link(self) -> None:
        if self.focused is self.query_one("#search", Input):
            self.query_one("#topics", ListView).focus()
            return
        self.query_one("#topic-view", TopicView).select_next_link(1)

    def action_previous_link(self) -> None:
        self.query_one("#topic-view", TopicView).select_next_link(-1)

    def action_activate_link(self) -> None:
        if self.focused is self.query_one("#search", Input):
            if self.visible_topics:
                self.navigator.go_to(self.visible_topics[0])
                self._show_current()
                self.query_one("#topic-view", TopicView).focus()
            return
        target = self.query_one("#topic-view", TopicView).selected_target()
        if target is not None:
            self._activate_target(target)

    def action_history_back(self) -> None:
        current = self.navigator.current
        self.navigator.back()
        if self.navigator.current is not current:
            self._show_current()
        elif self.document_back_stack:
            previous = self.document_back_stack.pop()
            self.document_forward_stack.append((self.helpfile, self.document, self.navigator))
            self._switch_document(*previous)

    def action_history_forward(self) -> None:
        current = self.navigator.current
        self.navigator.forward()
        if self.navigator.current is not current:
            self._show_current()
        elif self.document_forward_stack:
            following = self.document_forward_stack.pop()
            self.document_back_stack.append((self.helpfile, self.document, self.navigator))
            self._switch_document(*following)

    def action_browse_previous(self) -> None:
        current = self.navigator.current
        self.navigator.browse_previous()
        if self.navigator.current is not current:
            self._show_current()

    def action_browse_next(self) -> None:
        current = self.navigator.current
        self.navigator.browse_next()
        if self.navigator.current is not current:
            self._show_current()

    def action_focus_search(self) -> None:
        self.query_one("#search", Input).focus()

    def action_toggle_sidebar(self) -> None:
        sidebar = self.query_one("#sidebar")
        sidebar.display = not sidebar.display

    async def action_show_topics(self) -> None:
        await self._set_sidebar_mode("topics")

    async def action_show_contents(self) -> None:
        await self._set_sidebar_mode("contents")

    async def action_show_index(self) -> None:
        await self._set_sidebar_mode("index")

    async def _set_sidebar_mode(self, mode: str) -> None:
        self.sidebar_mode = mode
        self.query_one("#sidebar-title", Label).update(mode.title())
        search = self.query_one("#search", Input)
        search.placeholder = f"Search {mode}…"
        self.sidebar_entries = self._filter_sidebar_entries(search.value)
        self.visible_topics = [entry.topic for entry in self.sidebar_entries if entry.topic is not None]
        topics = self.query_one("#topics", ListView)
        await topics.clear()
        if self.sidebar_entries:
            await topics.extend(self._topic_items(self.sidebar_entries))
        topics.focus()

    def _filter_sidebar_entries(self, query: str):
        folded = query.casefold().strip()
        if self.sidebar_mode == "topics":
            topics = self.document.search(query)
            positions = {id(topic): index for index, topic in enumerate(self.document.topics)}
            return [NavigationEntry(topic_label(topic, positions[id(topic)]), topic) for topic in topics]
        entries = self.document.contents_entries() if self.sidebar_mode == "contents" else self.document.index_entries()
        return [entry for entry in entries if not folded or folded in entry.label.casefold()]

    def action_file_information(self) -> None:
        system = self.helpfile.system
        lines = [
            f"File: {self.helpfile.filepath}",
            f"Title: {help_title(self.helpfile)}",
            f"Topics: {len(self.document.topics)}",
            f"Format: {system.header.major}.{system.header.minor}" if system and system.header else "Format: unknown",
            f"Encoding: {system.encoding}" if system else "Encoding: unknown",
            f"LCID: {system.lcid:#06x}" if system and system.lcid is not None else "LCID: unavailable",
            f"Charset: {system.charset}" if system and system.charset is not None else "Charset: unavailable",
            f"Compression flags: {system.header.flags:#06x}" if system and system.header else "",
            f"Generated: {system.header.gen_date}" if system and system.header else "",
            f"Copyright: {system.copyright}" if system and system.copyright else "",
            f"Internal files: {len(self.helpfile.directory.files) if self.helpfile.directory else 0}",
            f"Parsed with warnings: {len(self.helpfile.parse_errors)}",
        ]
        if system:
            window_records = [
                record for record in system.records if isinstance(record, dict) and record.get("type") == "WINDOW"
            ]
            lines.append(f"Window definitions: {len(window_records)}")
        if self.helpfile.gmacros:
            lines.append("\nGlobal macros:")
            for macro in self.helpfile.gmacros.entries:
                lines.append(f"  enter: {macro.entry_macro}")
                lines.append(f"  exit:  {macro.exit_macro}")
        for config_number in sorted(self.helpfile.config_files):
            macros = self.helpfile.get_config_macros(config_number)
            if macros:
                lines.append(f"\nConfiguration {config_number} macros:")
                lines.extend(f"  {macro}" for macro in macros)
        definitions = self.helpfile.get_all_macro_definitions()
        if definitions:
            lines.append("\nIndexed macro definitions:")
            lines.extend(f"  {macro} [{title}]" for _, macro, title in definitions)
        if self.helpfile.directory and self.helpfile.directory.files:
            lines.append("\nInternal files:")
            lines.extend(f"  {name}" for name in sorted(self.helpfile.directory.files))
        if self.helpfile.parse_errors:
            lines.append("\nInternal-file diagnostics:")
            lines.extend(
                f"  {error.get('file', 'unknown')}: {error.get('error', error)}" for error in self.helpfile.parse_errors
            )
        self.push_screen(InformationPopup("Help File Information", Text("\n".join(line for line in lines if line))))

    def action_topic_details(self) -> None:
        topic = self.navigator.current
        if topic is None:
            return
        lines = [
            f"Title: {topic.title or '(untitled)'}",
            f"Topic number: {topic.topic_number}",
            f"Topic offset: {topic.topic_offset}",
            f"Non-scrolling offset: {topic.non_scroll_offset}",
            "Context IDs: " + (", ".join(topic.context_names) or "(none)"),
            "Keywords: " + (", ".join(topic.keywords) or "(none)"),
            "Entry macros: " + (", ".join(topic.entry_macros) or "(none)"),
            "Annotations: " + (str(len(topic.annotations))),
        ]
        self.push_screen(InformationPopup("Topic Details", Text("\n".join(lines))))

    def action_parse_errors(self) -> None:
        errors = self.helpfile.parse_errors
        if not errors:
            content = Text("No nonfatal parser errors were recorded.")
        else:
            content = Text(
                "\n\n".join(f"{error.get('file', 'unknown')}: {error.get('error', error)}" for error in errors)
            )
        self.push_screen(InformationPopup("Parser Diagnostics", content))

    @on(Input.Changed, "#search")
    async def search_changed(self, event: Input.Changed) -> None:
        self.sidebar_entries = self._filter_sidebar_entries(event.value)
        self.visible_topics = [entry.topic for entry in self.sidebar_entries if entry.topic is not None]
        topics = self.query_one("#topics", ListView)
        await topics.clear()
        if self.sidebar_entries:
            await topics.extend(self._topic_items(self.sidebar_entries))

    @on(Input.Submitted, "#search")
    def search_submitted(self) -> None:
        if self.visible_topics:
            self.navigator.go_to(self.visible_topics[0])
            self._show_current()
            self.query_one("#topic-view", TopicView).focus()

    @on(ListView.Selected, "#topics")
    def topic_selected(self, event: ListView.Selected) -> None:
        if event.list_view.index is None or event.list_view.index >= len(self.sidebar_entries):
            return
        topic = self.sidebar_entries[event.list_view.index].topic
        if topic is None:
            return
        self.navigator.go_to(topic)
        self._show_current()
        self.query_one("#topic-view", TopicView).focus()


def run_tui(helpfile) -> None:
    """Run the terminal viewer for a parsed HelpFile."""
    WinHlpApp(helpfile).run()
