"""Interactive terminal viewer for parsed Windows Help files."""

from __future__ import annotations

import os
from typing import Iterable, Optional

from rich.console import Group, RenderableType
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
    ResolvedTarget,
    help_title,
    parse_embedded_resource,
)
from .lib.internal_files.topic import ParsedTopic, TextSpan, TopicTableBlock, TopicTextBlock


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
        bold=span.is_bold,
        italic=span.is_italic,
        underline=span.is_underline,
        strike=span.is_strikethrough,
    )


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
        id: Optional[str] = None,
    ):
        super().__init__(id=id)
        self.document = document
        self.topic = topic
        self.interactive = interactive
        self.targets: list[ResolvedTarget] = []
        self.image_placeholders: list[str] = []
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
        for block in blocks:
            if isinstance(block, TopicTextBlock):
                renderables.extend(self._render_text_block(block))
            else:
                renderables.append(self._render_table(block))
        self.update(Group(*renderables))

    def _render_text_block(self, block: TopicTextBlock) -> Iterable[RenderableType]:
        text = Text()
        mappings = {mapping.text_span_index: mapping for mapping in block.hotspot_mappings}
        for index, span in enumerate(block.text_spans):
            start = len(text)
            text.append(span.text, _span_style(span))
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
                    meta={"@click": f"app.follow_link({link_index})"},
                )
                text.stylize(style, start, end)
            if span.embedded_image:
                resource = parse_embedded_resource(span.embedded_image)
                if resource is not None:
                    label = resource.resource_name or resource.reference
                    placeholder = f"[image: {label}, {resource.alignment}]"
                    self.image_placeholders.append(placeholder)
                    text.append(f"\n{placeholder}\n", style="italic dim")
        if text.plain:
            yield text
            yield Text()

    @staticmethod
    def _render_table(block: TopicTableBlock) -> RichTable:
        parsed = block.table
        columns = max(parsed.column_count, max((len(row.cells) for row in parsed.rows), default=0), 1)
        table = RichTable(show_header=False, box=None, pad_edge=False)
        for _ in range(columns):
            table.add_column()
        for row in parsed.rows:
            cells = []
            for cell in row.cells:
                cell_text = Text()
                for span in cell.text_spans:
                    cell_text.append(span.text, _span_style(span))
                cells.append(cell_text)
            cells.extend(Text() for _ in range(columns - len(cells)))
            table.add_row(*cells[:columns])
        return table


class TopicPopup(ModalScreen):
    BINDINGS = [Binding("escape", "dismiss", "Close"), Binding("q", "dismiss", "Close")]

    def __init__(self, document: HelpDocument, topic: ParsedTopic):
        super().__init__()
        self.document = document
        self.topic = topic

    def compose(self) -> ComposeResult:
        with Vertical(id="popup"):
            yield VerticalScroll(TopicView(self.document, self.topic, interactive=False))
            yield Label("Esc: close", id="popup-hint")

    def action_dismiss(self) -> None:
        self.dismiss()


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


class WinHlpApp(App):
    """Browse a parsed Windows Help file in the terminal."""

    CSS = """
    Screen { layout: vertical; background: $background; color: $text; }
    #body { height: 1fr; }
    #sidebar { width: 30; border-right: solid $primary; background: $panel; }
    #search { dock: top; }
    #topics { height: 1fr; }
    #topic-scroll { width: 1fr; padding: 1 2; background: $surface; }
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
    """

    BINDINGS = [
        Binding("q", "quit", "Quit"),
        Binding("b,alt+left", "history_back", "Back"),
        Binding("f,alt+right", "history_forward", "Forward"),
        Binding("[", "browse_previous", "Browse prev"),
        Binding("]", "browse_next", "Browse next"),
        Binding("/", "focus_search", "Search"),
        Binding("t", "toggle_sidebar", "Topics"),
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
        self.visible_topics = list(self.document.topics)
        self.title = help_title(helpfile)
        self.sub_title = os.path.basename(helpfile.filepath)

    def compose(self) -> ComposeResult:
        yield Header()
        with Horizontal(id="body"):
            with Vertical(id="sidebar"):
                yield Input(placeholder="Search topics…", id="search")
                yield ListView(*self._topic_items(self.visible_topics), id="topics")
            with VerticalScroll(id="topic-scroll"):
                yield TopicView(self.document, self.navigator.current, id="topic-view")
        yield Footer()

    def on_mount(self) -> None:
        self._update_subtitle()
        self.query_one(TopicView).focus()

    def _topic_items(self, topics) -> list[ListItem]:
        positions = {id(topic): index for index, topic in enumerate(self.document.topics)}
        return [ListItem(Label(topic_label(topic, positions[id(topic)]))) for topic in topics]

    def _show_current(self) -> None:
        self.query_one("#topic-view", TopicView).set_topic(self.navigator.current)
        self.query_one("#topic-scroll", VerticalScroll).scroll_home(animate=False)
        self._update_subtitle()

    def _update_subtitle(self) -> None:
        current = self.navigator.current
        if current is None:
            self.sub_title = os.path.basename(self.helpfile.filepath)
            return
        position = self.document.topics.index(current) + 1
        self.sub_title = f"{os.path.basename(self.helpfile.filepath)} · {position}/{len(self.document.topics)}"

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
        else:
            self.push_screen(DiagnosticPopup(target.detail or f"Unsupported target: {target.original}"))

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

    def action_history_forward(self) -> None:
        current = self.navigator.current
        self.navigator.forward()
        if self.navigator.current is not current:
            self._show_current()

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

    @on(Input.Changed, "#search")
    async def search_changed(self, event: Input.Changed) -> None:
        self.visible_topics = self.document.search(event.value)
        topics = self.query_one("#topics", ListView)
        await topics.clear()
        if self.visible_topics:
            await topics.extend(self._topic_items(self.visible_topics))

    @on(Input.Submitted, "#search")
    def search_submitted(self) -> None:
        if self.visible_topics:
            self.navigator.go_to(self.visible_topics[0])
            self._show_current()
            self.query_one("#topic-view", TopicView).focus()

    @on(ListView.Selected, "#topics")
    def topic_selected(self, event: ListView.Selected) -> None:
        if event.list_view.index is None or event.list_view.index >= len(self.visible_topics):
            return
        self.navigator.go_to(self.visible_topics[event.list_view.index])
        self._show_current()
        self.query_one("#topic-view", TopicView).focus()


def run_tui(helpfile) -> None:
    """Run the terminal viewer for a parsed HelpFile."""
    WinHlpApp(helpfile).run()
